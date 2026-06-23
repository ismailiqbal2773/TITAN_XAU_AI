"""
Tests for Sprint 6 — Forward Testing Layer.

Verifies:
  - Demo account validation
  - Real account rejection
  - Metrics collection
  - Report generation
  - Runtime health monitoring
  - Daily checkpoint generation
  - Kill-switch event logging
  - Dashboard export
  - Journal persistence across restart
  - Journal append-only behavior
  - Journal recovery after crash
  - Journal complete trade lifecycle
"""
from __future__ import annotations

import asyncio
import json
import os
import time
import tempfile
import pytest
import numpy as np
from datetime import datetime, timezone, timedelta

from titan.production.inference import Signal, Direction
from titan.production.trade_loop import TradeLoop, TradeLoopConfig
from titan.production.trade_journal import TradeJournal, EventType
from titan.production.kill_switch_fsm import KillSwitchFSM, KillSwitchInput, KillState
from titan.forward_test.mt5_demo_adapter import MT5DemoAdapter, StubMT5DemoAdapter
from titan.forward_test.metrics_collector import MetricsCollector, MetricsSnapshot
from titan.forward_test.runtime_health import RuntimeHealthMonitor, HealthStatus
from titan.forward_test.report_generator import ReportGenerator, DailyReport, WeeklyReport
from titan.forward_test.forward_test_manager import ForwardTestManager


# ─── Helpers ──────────────────────────────────────────────────────────────────

def make_signal(direction=Direction.LONG, is_tradeable=True) -> Signal:
    return Signal(
        timestamp=time.time(), direction=direction,
        confidence=0.80, meta_confidence=0.85,
        xgb_proba=[0.2, 0.8] if direction == Direction.LONG else [0.8, 0.2],
        meta_proba=[0.15, 0.85], is_tradeable=is_tradeable,
        feature_vector=np.zeros(55), inference_ms=10.0, source="test",
    )


def setup_journal_with_lifecycle(tmp_path) -> str:
    """Create a journal with a complete trade lifecycle for testing."""
    journal_path = str(tmp_path / "lifecycle.jsonl")
    journal = TradeJournal(path=journal_path)

    # Startup
    journal.log_startup({"session_id": "test"})

    # Signal
    signal = make_signal()
    journal.log_signal(signal)

    # Decision (accepted)
    from titan.production.trade_loop import TradeDecision
    dec = TradeDecision(
        accepted=True, signal=signal, risk_decision="ALLOW",
        adjusted_volume=0.01, order_request={"symbol": "XAUUSD", "volume": 0.01, "sl": 1999.5, "tp": 2001.0},
        evaluation_ms=10.0, dry_run=True,
    )
    journal.log_decision(dec)
    journal.log_order(dec)

    # Position opened
    journal.log_event(EventType.POSITION_OPENED, {"ticket": 50001, "volume": 0.01})

    # Modify
    journal.log_modify(ticket=50001, old_sl=1999.5, old_tp=2001.0,
                       new_sl=2000.0, new_tp=2001.0, reason="trailing", dry_run=True)

    # Exit
    journal.log_exit(ticket=50001, exit_reason="TP_HIT",
                     entry_price=2000.0, exit_price=2001.0,
                     direction=1, volume=0.01, pnl_usd=10.0,
                     holding_time_seconds=3600.0)

    journal.log_event(EventType.POSITION_CLOSED, {"ticket": 50001, "pnl": 10.0})

    # Shutdown
    journal.log_shutdown(reason="test_complete")
    journal.flush()

    return journal_path


# ─── 1. MT5 Demo Adapter ─────────────────────────────────────────────────────

class TestMT5DemoAdapter:
    def test_stub_demo_account_accepted(self, tmp_path):
        journal = TradeJournal(path=str(tmp_path / "j.jsonl"))
        adapter = StubMT5DemoAdapter(journal=journal, simulate_demo=True)
        assert adapter.connect()
        assert adapter.is_connected
        assert adapter.verification.is_demo
        assert adapter.verification.verified

    def test_stub_real_account_rejected(self, tmp_path):
        journal = TradeJournal(path=str(tmp_path / "j.jsonl"))
        adapter = StubMT5DemoAdapter(journal=journal, simulate_demo=False)
        assert not adapter.connect()
        assert not adapter.is_connected
        assert not adapter.verification.is_demo
        # Verify journal logged the block
        journal.flush()
        blocks = journal.read_by_event_type(EventType.KILL_SWITCH_BLOCK)
        assert len(blocks) == 1
        assert blocks[0]["data"]["reason"] == "real_account_detected"

    def test_real_adapter_refuses_without_mt5(self, tmp_path):
        """Real adapter (not stub) fails gracefully without MetaTrader5 package."""
        journal = TradeJournal(path=str(tmp_path / "j.jsonl"))
        adapter = MT5DemoAdapter(journal=journal)
        # On Linux without MT5, this should return False
        result = adapter.connect(login=12345, password="test", server="test")
        assert result is False
        assert not adapter.is_connected

    def test_verification_journaled(self, tmp_path):
        journal = TradeJournal(path=str(tmp_path / "j.jsonl"))
        adapter = StubMT5DemoAdapter(journal=journal, simulate_demo=True)
        adapter.connect(login=34265693, server="FundedNext-Server 3")
        journal.flush()
        startups = journal.read_by_event_type(EventType.STARTUP)
        assert len(startups) == 1
        assert startups[0]["data"]["login"] == 34265693
        assert startups[0]["data"]["server"] == "FundedNext-Server 3"


# ─── 2. Metrics Collector ────────────────────────────────────────────────────

class TestMetricsCollector:
    def test_collect_from_empty_journal(self, tmp_path):
        journal_path = str(tmp_path / "empty.jsonl")
        TradeJournal(path=journal_path).flush()
        collector = MetricsCollector(journal_path=journal_path,
                                      output_dir=str(tmp_path / "metrics"))
        snap = collector.collect()
        assert snap.signals_generated == 0
        assert snap.trades_closed == 0
        assert snap.total_pnl_usd == 0.0

    def test_collect_from_lifecycle_journal(self, tmp_path):
        journal_path = setup_journal_with_lifecycle(tmp_path)
        collector = MetricsCollector(journal_path=journal_path,
                                      output_dir=str(tmp_path / "metrics"))
        snap = collector.collect()
        assert snap.signals_generated == 1
        assert snap.signals_accepted == 1
        assert snap.trades_closed == 1
        assert snap.winning_trades == 1
        assert snap.win_rate == 1.0
        assert snap.total_pnl_usd == 10.0
        assert snap.profit_factor == float("inf")  # no losses

    def test_save_json(self, tmp_path):
        journal_path = setup_journal_with_lifecycle(tmp_path)
        collector = MetricsCollector(journal_path=journal_path,
                                      output_dir=str(tmp_path / "metrics"))
        collector.collect()
        path = collector.save_json()
        assert os.path.exists(path)
        with open(path) as f:
            data = json.load(f)
        assert data["signals_generated"] == 1
        assert data["trades_closed"] == 1

    def test_save_csv(self, tmp_path):
        journal_path = setup_journal_with_lifecycle(tmp_path)
        collector = MetricsCollector(journal_path=journal_path,
                                      output_dir=str(tmp_path / "metrics"))
        collector.collect()
        path = collector.save_csv()
        assert os.path.exists(path)
        with open(path) as f:
            lines = f.readlines()
        assert len(lines) == 2  # header + 1 data row

    def test_no_in_memory_state(self, tmp_path):
        """Metrics must come from journal, not memory."""
        journal_path = str(tmp_path / "mem.jsonl")
        j = TradeJournal(path=journal_path)
        j.log_signal(make_signal())
        j.flush()

        # Create a NEW collector (no shared state)
        collector = MetricsCollector(journal_path=journal_path,
                                      output_dir=str(tmp_path / "m"))
        snap = collector.collect()
        assert snap.signals_generated == 1  # read from journal, not memory


# ─── 3. Runtime Health Monitor ───────────────────────────────────────────────

class TestRuntimeHealthMonitor:
    def test_check_returns_status(self, tmp_path):
        journal = TradeJournal(path=str(tmp_path / "h.jsonl"))
        mon = RuntimeHealthMonitor(journal=journal)
        status = mon.check()
        assert isinstance(status, HealthStatus)
        assert status.uptime_seconds >= 0
        assert status.cpu_percent >= 0
        assert status.memory_percent >= 0

    def test_alert_on_high_cpu(self, tmp_path):
        journal = TradeJournal(path=str(tmp_path / "h.jsonl"))
        from titan.forward_test.runtime_health import HealthConfig
        mon = RuntimeHealthMonitor(journal=journal,
                                    config=HealthConfig(cpu_alert_pct=0.0))  # always alert
        status = mon.check()
        assert status.alert
        assert any("cpu" in r for r in status.alert_reasons)

    def test_record_heartbeat(self, tmp_path):
        journal = TradeJournal(path=str(tmp_path / "h.jsonl"))
        mon = RuntimeHealthMonitor(journal=journal)
        mon.record_heartbeat("test_component")
        status = mon.check()
        assert status.missed_heartbeats == 0  # just beat, not missed

    def test_record_restart(self, tmp_path):
        journal = TradeJournal(path=str(tmp_path / "h.jsonl"))
        mon = RuntimeHealthMonitor(journal=journal)
        mon.record_restart("test_component")
        mon.record_restart("test_component")
        status = mon.check()
        assert status.restart_count == 2

    def test_uptime_increases(self, tmp_path):
        journal = TradeJournal(path=str(tmp_path / "h.jsonl"))
        mon = RuntimeHealthMonitor(journal=journal)
        time.sleep(0.1)
        assert mon.uptime_seconds > 0.05


# ─── 4. Report Generator ─────────────────────────────────────────────────────

class TestReportGenerator:
    def test_daily_report_generated(self, tmp_path):
        journal_path = setup_journal_with_lifecycle(tmp_path)
        gen = ReportGenerator(journal_path=journal_path,
                               output_dir=str(tmp_path / "reports"))
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        report = gen.generate_daily_report(date=today)
        assert isinstance(report, DailyReport)
        assert report.date == today
        assert report.signals_generated == 1
        assert report.trades_closed == 1
        assert report.pnl_usd == 10.0
        assert report.winning_trades == 1
        # Verify file saved
        path = tmp_path / "reports" / f"daily_report_{today}.json"
        assert path.exists()

    def test_weekly_report_generated(self, tmp_path):
        journal_path = setup_journal_with_lifecycle(tmp_path)
        gen = ReportGenerator(journal_path=journal_path,
                               output_dir=str(tmp_path / "reports"))
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        report = gen.generate_weekly_report(week_start=today)
        assert isinstance(report, WeeklyReport)
        assert report.week_start == today
        assert len(report.daily_reports) == 7
        # Verify file saved
        path = tmp_path / "reports" / f"weekly_report_{today}.json"
        assert path.exists()

    def test_report_uses_journal_as_truth(self, tmp_path):
        """Reports must come from journal, not in-memory state."""
        journal_path = setup_journal_with_lifecycle(tmp_path)
        gen = ReportGenerator(journal_path=journal_path,
                               output_dir=str(tmp_path / "r"))
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        report = gen.generate_daily_report(date=today)
        # The journal had 1 signal, 1 trade, $10 PnL
        assert report.signals_generated == 1
        assert report.trades_closed == 1
        assert report.pnl_usd == 10.0


# ─── 5. Forward Test Manager ─────────────────────────────────────────────────

class TestForwardTestManager:
    def test_start_session(self, tmp_path):
        journal_path = str(tmp_path / "ft.jsonl")
        manager = ForwardTestManager(
            journal_path=journal_path,
            output_dir=str(tmp_path / "ft"),
            metrics_dir=str(tmp_path / "m"),
            reports_dir=str(tmp_path / "r"),
        )
        state = manager.start_session()
        assert state.session_id.startswith("ft_")
        assert state.days_completed == 0

    def test_end_day_creates_checkpoint(self, tmp_path):
        journal_path = str(tmp_path / "ft.jsonl")
        manager = ForwardTestManager(
            journal_path=journal_path,
            output_dir=str(tmp_path / "ft"),
            metrics_dir=str(tmp_path / "m"),
            reports_dir=str(tmp_path / "r"),
        )
        manager.start_session()
        checkpoint = manager.end_day()
        assert checkpoint.date is not None
        assert checkpoint.journal_records > 0  # at least startup event
        # Verify checkpoint file exists
        cp_path = tmp_path / "ft" / "checkpoints" / f"checkpoint_{checkpoint.date}.json"
        assert cp_path.exists()

    def test_end_session(self, tmp_path):
        journal_path = str(tmp_path / "ft.jsonl")
        manager = ForwardTestManager(
            journal_path=journal_path,
            output_dir=str(tmp_path / "ft"),
            metrics_dir=str(tmp_path / "m"),
            reports_dir=str(tmp_path / "r"),
        )
        manager.start_session()
        manager.end_day()
        manager.end_session(reason="test_complete")
        # Verify shutdown journaled
        journal = TradeJournal(path=journal_path)
        shutdowns = journal.read_by_event_type(EventType.SHUTDOWN)
        assert len(shutdowns) == 1
        assert shutdowns[0]["data"]["reason"] == "test_complete"

    def test_session_resume_after_restart(self, tmp_path):
        """Session state persists across restart."""
        journal_path = str(tmp_path / "ft.jsonl")
        manager1 = ForwardTestManager(
            journal_path=journal_path,
            output_dir=str(tmp_path / "ft"),
            metrics_dir=str(tmp_path / "m"),
            reports_dir=str(tmp_path / "r"),
        )
        state1 = manager1.start_session()
        manager1.end_day()
        manager1.end_session()
        days_after_1 = manager1._state.days_completed

        # Create new manager (simulates restart)
        manager2 = ForwardTestManager(
            journal_path=journal_path,
            output_dir=str(tmp_path / "ft"),
            metrics_dir=str(tmp_path / "m"),
            reports_dir=str(tmp_path / "r"),
        )
        state2 = manager2.start_session()
        # Should have resumed
        assert state2.session_id == state1.session_id
        assert state2.days_completed == days_after_1

    def test_get_status(self, tmp_path):
        journal_path = str(tmp_path / "ft.jsonl")
        manager = ForwardTestManager(
            journal_path=journal_path,
            output_dir=str(tmp_path / "ft"),
            metrics_dir=str(tmp_path / "m"),
            reports_dir=str(tmp_path / "r"),
        )
        manager.start_session()
        status = manager.get_status()
        assert status["status"] == "running"
        assert "session_id" in status
        assert "uptime_hours" in status


# ─── 6. Journal Audit-Grade Verification ─────────────────────────────────────

class TestJournalAuditGrade:
    def test_event_type_enum_has_all_20_types(self):
        """All 20 required event types must be in EventType enum."""
        required = {
            "SIGNAL_CREATED", "SIGNAL_REJECTED", "ORDER_CREATED", "ORDER_BLOCKED",
            "POSITION_OPENED", "POSITION_MODIFIED", "POSITION_CLOSED",
            "EXIT_TRIGGERED", "KILL_SWITCH_TRANSITION", "KILL_SWITCH_BLOCK",
            "NEWS_HALT", "DRIFT_ALERT", "DRIFT_EMERGENCY",
            "SLIPPAGE_ALERT", "SLIPPAGE_HALT", "WATCHDOG_RESTART",
            "STARTUP", "SHUTDOWN", "DAILY_SUMMARY", "WEEKLY_SUMMARY",
        }
        actual = {e.value for e in EventType}
        assert required == actual, f"Missing: {required - actual}"

    def test_every_record_has_utc_timestamp(self, tmp_path):
        journal_path = str(tmp_path / "audit.jsonl")
        journal = TradeJournal(path=journal_path)
        journal.log_startup({"test": True})
        journal.log_signal(make_signal())
        journal.log_shutdown()
        journal.flush()
        # Read raw lines + verify UTC timestamp
        records = journal.read_all()
        for r in records:
            assert "utc_timestamp" in r
            assert r["utc_timestamp"] != ""
            # Verify ISO format
            datetime.fromisoformat(r["utc_timestamp"])

    def test_every_record_has_event_id(self, tmp_path):
        journal_path = str(tmp_path / "audit.jsonl")
        journal = TradeJournal(path=journal_path)
        journal.log_startup({"test": True})
        journal.log_shutdown()
        journal.flush()
        records = journal.read_all()
        ids = [r["record_id"] for r in records]
        # All unique
        assert len(ids) == len(set(ids))
        # All non-empty
        assert all(id for id in ids)

    def test_every_record_has_event_type(self, tmp_path):
        journal_path = str(tmp_path / "audit.jsonl")
        journal = TradeJournal(path=journal_path)
        journal.log_startup({"test": True})
        journal.log_shutdown()
        journal.flush()
        records = journal.read_all()
        for r in records:
            assert "event_type" in r
            # Event records must have non-empty event_type
            if r.get("record_type") == "EVENT":
                assert r["event_type"] != ""

    def test_journal_append_only(self, tmp_path):
        """Journal must be append-only — existing records never modified."""
        journal_path = str(tmp_path / "append.jsonl")
        journal = TradeJournal(path=journal_path)
        journal.log_startup({"seq": 1})
        journal.flush()

        # Read first record
        records_before = journal.read_all()
        first_id = records_before[0]["record_id"]

        # Write more records
        journal.log_signal(make_signal())
        journal.log_shutdown()
        journal.flush()

        # Read again — first record must be unchanged
        records_after = journal.read_all()
        assert records_after[0]["record_id"] == first_id
        assert records_after[0]["data"]["seq"] == 1
        assert len(records_after) == 3

    def test_journal_persistence_across_restart(self, tmp_path):
        """Journal must survive runtime restart."""
        journal_path = str(tmp_path / "persist.jsonl")
        j1 = TradeJournal(path=journal_path, session_id="session_A")
        j1.log_startup({"session": "A"})
        j1.log_signal(make_signal())
        j1.log_shutdown()
        j1.flush()

        # Simulate restart — create NEW journal instance
        j2 = TradeJournal(path=journal_path, session_id="session_B")
        records = j2.read_all()
        assert len(records) == 3  # all records from session A survived

    def test_journal_recovery_after_crash(self, tmp_path):
        """Journal must recover from crash with partial write."""
        journal_path = str(tmp_path / "crash.jsonl")
        journal = TradeJournal(path=journal_path)
        journal.log_startup({"test": True})
        journal.log_signal(make_signal())
        journal.flush()

        # Simulate crash — append a corrupt partial line
        with open(journal_path, "a") as f:
            f.write('{"partial": "corrupt')  # no closing brace

        # Recover
        recovered = journal.recover_from_crash()
        assert recovered == 2  # 2 valid records preserved
        # Verify journal is now clean
        assert journal.verify_append_only()

    def test_journal_complete_lifecycle(self, tmp_path):
        """Journal must contain complete trade lifecycle."""
        journal_path = setup_journal_with_lifecycle(tmp_path)
        journal = TradeJournal(path=journal_path)
        verification = journal.verify_complete_lifecycle()
        assert verification["has_signal"] is True
        assert verification["has_decision"] is True
        assert verification["has_order"] is True
        assert verification["has_exit"] is True
        assert verification["has_modify"] is True
        assert verification["has_startup"] is True
        assert verification["has_shutdown"] is True

    def test_log_event_requires_enum(self, tmp_path):
        """log_event must reject non-EventType arguments."""
        journal = TradeJournal(path=str(tmp_path / "j.jsonl"))
        with pytest.raises(ValueError):
            journal.log_event("NOT_AN_ENUM", {"data": True})

    def test_read_by_event_type(self, tmp_path):
        journal = TradeJournal(path=str(tmp_path / "j.jsonl"))
        journal.log_startup({"test": 1})
        journal.log_shutdown()
        journal.log_startup({"test": 2})
        journal.flush()
        startups = journal.read_by_event_type(EventType.STARTUP)
        assert len(startups) == 2
        shutdowns = journal.read_by_event_type(EventType.SHUTDOWN)
        assert len(shutdowns) == 1


# ─── 7. Dashboard Export ─────────────────────────────────────────────────────

class TestDashboardExport:
    def test_forward_test_dashboard_exists(self):
        path = "monitoring/forward_test_dashboard.json"
        assert os.path.exists(path)

    def test_dashboard_valid_json(self):
        path = "monitoring/forward_test_dashboard.json"
        with open(path) as f:
            data = json.load(f)
        assert "dashboard" in data
        assert "panels" in data
        assert "alerts" in data
        assert "layout" in data

    def test_dashboard_has_required_panels(self):
        path = "monitoring/forward_test_dashboard.json"
        with open(path) as f:
            data = json.load(f)
        panel_ids = [p["id"] for p in data["panels"]]
        required = [
            "daily_pnl", "weekly_pnl", "win_rate", "profit_factor",
            "drawdown", "runtime_uptime", "kill_switch_events",
            "drift_events", "slippage_events", "mt5_connection",
        ]
        for req in required:
            assert req in panel_ids, f"Missing panel: {req}"


# ─── 8. Integration: Kill-Switch Event Logging ───────────────────────────────

class TestKillSwitchEventLogging:
    @pytest.mark.asyncio
    async def test_kill_switch_block_journaled_as_event(self, tmp_path):
        """Kill-switch blocks must be journaled as audit events."""
        journal = TradeJournal(path=str(tmp_path / "ks.jsonl"))
        fsm = KillSwitchFSM(journal_callback=lambda t: journal.log_event(
            EventType.KILL_SWITCH_TRANSITION, {
                "from": t.from_state.value,
                "to": t.to_state.value,
                "trigger": t.trigger,
            }
        ))
        fsm.update(KillSwitchInput(daily_loss_pct=3.5))  # → HALT
        loop = TradeLoop(TradeLoopConfig(dry_run=True), journal=journal, kill_switch=fsm)
        signal = make_signal()
        await loop.process_signal(signal, entry_price=2000.0, spread_usd=0.2)
        journal.flush()

        # Verify transition event
        transitions = journal.read_by_event_type(EventType.KILL_SWITCH_TRANSITION)
        assert len(transitions) == 1
        assert transitions[0]["data"]["to"] == "HALT_NEW_TRADES"

        # Verify block event (from trade_loop)
        blocks = journal.read_by_event_type(EventType.KILL_SWITCH_BLOCK)
        assert len(blocks) >= 1


# ─── 9. Integration: Full Forward Test Cycle ─────────────────────────────────

class TestForwardTestIntegration:
    def test_full_forward_test_cycle(self, tmp_path):
        """Full cycle: startup → trade → exit → daily report → shutdown."""
        journal_path = str(tmp_path / "full_ft.jsonl")
        manager = ForwardTestManager(
            journal_path=journal_path,
            output_dir=str(tmp_path / "ft"),
            metrics_dir=str(tmp_path / "m"),
            reports_dir=str(tmp_path / "r"),
        )

        # Start session
        manager.start_session()

        # Simulate a trade lifecycle in journal
        journal = manager.journal
        signal = make_signal()
        journal.log_signal(signal)
        journal.log_event(EventType.SIGNAL_CREATED, {"direction": signal.direction.name})

        from titan.production.trade_loop import TradeDecision
        dec = TradeDecision(
            accepted=True, signal=signal, risk_decision="ALLOW",
            adjusted_volume=0.01, order_request={"symbol": "XAUUSD", "volume": 0.01},
            evaluation_ms=10.0, dry_run=True,
        )
        journal.log_decision(dec)
        journal.log_order(dec)
        journal.log_event(EventType.ORDER_CREATED, {"volume": 0.01})
        journal.log_event(EventType.POSITION_OPENED, {"ticket": 50001})
        journal.log_exit(ticket=50001, exit_reason="TP_HIT",
                         entry_price=2000.0, exit_price=2001.0,
                         direction=1, volume=0.01, pnl_usd=10.0,
                         holding_time_seconds=3600.0)
        journal.log_event(EventType.POSITION_CLOSED, {"ticket": 50001, "pnl": 10.0})

        # End day + session
        checkpoint = manager.end_day()
        manager.end_session(reason="test_complete")

        # Verify
        assert checkpoint.metrics["trades_closed"] == 1
        assert checkpoint.metrics["total_pnl_usd"] == 10.0
        assert checkpoint.metrics["win_rate"] == 1.0

        # Verify daily report
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        report_path = tmp_path / "r" / f"daily_report_{today}.json"
        assert report_path.exists()
        with open(report_path) as f:
            report = json.load(f)
        assert report["trades_closed"] == 1
        assert report["pnl_usd"] == 10.0
        assert report["winning_trades"] == 1

        # Verify journal lifecycle
        journal = TradeJournal(path=journal_path)
        verification = journal.verify_complete_lifecycle()
        assert verification["has_signal"]
        assert verification["has_decision"]
        assert verification["has_order"]
        assert verification["has_exit"]
        assert verification["has_startup"]
        assert verification["has_shutdown"]
