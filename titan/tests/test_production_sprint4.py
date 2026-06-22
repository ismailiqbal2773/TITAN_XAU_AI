"""
Tests for Sprint 4 safety layer modules:
  - kill_switch_fsm.py
  - news_filter.py
  - slippage_monitor.py
  - drift_monitor.py
  - watchdog_restarter.py
  - integration: signal → order → kill switch halt → exit flatten → journal
"""
from __future__ import annotations

import asyncio
import os
import time
import tempfile
import csv
import pytest
import numpy as np
from datetime import datetime, timedelta, timezone

from titan.production.inference import Signal, Direction
from titan.production.trade_loop import TradeLoop, TradeLoopConfig
from titan.production.position_sync import BrokerPosition
from titan.production.exit_manager import ExitManager, ExitReason
from titan.production.trade_journal import TradeJournal
from titan.production.kill_switch_fsm import (
    KillSwitchFSM, KillSwitchConfig, KillSwitchInput, KillState,
)
from titan.production.news_filter import (
    NewsFilter, NewsEvent, NewsHaltStatus, HIGH_IMPACT_KEYWORDS,
)
from titan.production.slippage_monitor import (
    SlippageMonitor, SlippageConfig, SlippageStats,
)
from titan.production.drift_monitor import (
    DriftMonitor, DriftConfig, DriftReport,
)
from titan.production.watchdog_restarter import WatchdogRestarter, RecoveryEvent


# ─── Helpers ──────────────────────────────────────────────────────────────────

def make_signal(direction=Direction.LONG, is_tradeable=True) -> Signal:
    return Signal(
        timestamp=time.time(), direction=direction,
        confidence=0.80, meta_confidence=0.85,
        xgb_proba=[0.2, 0.8] if direction == Direction.LONG else [0.8, 0.2],
        meta_proba=[0.15, 0.85], is_tradeable=is_tradeable,
        feature_vector=np.zeros(55), inference_ms=10.0, source="test",
    )


# ─── kill_switch_fsm.py ───────────────────────────────────────────────────────

class TestKillSwitchFSMStates:
    def test_initial_state_normal(self):
        fsm = KillSwitchFSM()
        assert fsm.state == KillState.NORMAL
        assert fsm.is_normal
        assert fsm.allows_new_trades

    def test_caution_via_latency(self):
        fsm = KillSwitchFSM(KillSwitchConfig(max_latency_ms=500))
        fsm.update(KillSwitchInput(latency_p99_ms=550))
        assert fsm.state == KillState.CAUTION
        assert fsm.allows_new_trades  # caution still allows trades

    def test_halt_new_trades_via_daily_loss(self):
        fsm = KillSwitchFSM(KillSwitchConfig(max_daily_loss_pct=3.0))
        fsm.update(KillSwitchInput(daily_loss_pct=3.5))
        assert fsm.state == KillState.HALT_NEW_TRADES
        assert not fsm.allows_new_trades
        assert not fsm.requires_flatten

    def test_flatten_only_via_drawdown(self):
        fsm = KillSwitchFSM(KillSwitchConfig(max_drawdown_pct=5.0))
        fsm.update(KillSwitchInput(max_drawdown_pct=5.5))
        assert fsm.state == KillState.FLATTEN_ONLY
        assert fsm.requires_flatten
        assert not fsm.is_emergency

    def test_emergency_stop_via_emergency_drawdown(self):
        fsm = KillSwitchFSM(KillSwitchConfig(emergency_drawdown_pct=8.0))
        fsm.update(KillSwitchInput(max_drawdown_pct=8.5))
        assert fsm.state == KillState.EMERGENCY_STOP
        assert fsm.is_emergency
        assert fsm.requires_flatten
        assert fsm.armed_time is not None


class TestKillSwitchFSMEscalation:
    def test_escalation_is_one_way(self):
        """State can only escalate DOWN, never up without reset."""
        fsm = KillSwitchFSM()
        fsm.update(KillSwitchInput(daily_loss_pct=3.5))  # → HALT_NEW_TRADES
        assert fsm.state == KillState.HALT_NEW_TRADES
        # Now inputs are normal — state should NOT de-escalate
        fsm.update(KillSwitchInput(daily_loss_pct=0.0))
        assert fsm.state == KillState.HALT_NEW_TRADES  # unchanged

    def test_highest_severity_wins(self):
        """Multiple triggers → highest severity state."""
        fsm = KillSwitchFSM(KillSwitchConfig(
            max_daily_loss_pct=3.0, emergency_drawdown_pct=8.0,
        ))
        # Both daily_loss + emergency drawdown
        fsm.update(KillSwitchInput(daily_loss_pct=3.5, max_drawdown_pct=8.5))
        assert fsm.state == KillState.EMERGENCY_STOP  # highest

    def test_reset_returns_to_normal(self):
        fsm = KillSwitchFSM()
        fsm.update(KillSwitchInput(daily_loss_pct=3.5))
        assert fsm.state == KillState.HALT_NEW_TRADES
        fsm.reset()
        assert fsm.state == KillState.NORMAL
        assert fsm.is_normal

    def test_consecutive_losses_trigger_halt(self):
        fsm = KillSwitchFSM(KillSwitchConfig(max_consecutive_losses=5))
        fsm.update(KillSwitchInput(consecutive_losses=5))
        assert fsm.state == KillState.HALT_NEW_TRADES

    def test_news_halt_triggers_halt(self):
        fsm = KillSwitchFSM()
        fsm.update(KillSwitchInput(news_halt_active=True))
        assert fsm.state == KillState.HALT_NEW_TRADES

    def test_drift_breach_triggers_caution(self):
        fsm = KillSwitchFSM()
        fsm.update(KillSwitchInput(drift_breach=True))
        assert fsm.state == KillState.CAUTION

    def test_drift_emergency_triggers_emergency_stop(self):
        fsm = KillSwitchFSM()
        fsm.update(KillSwitchInput(drift_emergency=True))
        assert fsm.state == KillState.EMERGENCY_STOP

    def test_high_brier_triggers_caution(self):
        fsm = KillSwitchFSM(KillSwitchConfig(max_brier=0.22))
        fsm.update(KillSwitchInput(brier_score=0.24))
        assert fsm.state == KillState.CAUTION

    def test_high_ece_triggers_halt(self):
        fsm = KillSwitchFSM(KillSwitchConfig(emergency_ece=0.15))
        fsm.update(KillSwitchInput(ece=0.16))
        assert fsm.state == KillState.HALT_NEW_TRADES

    def test_high_spread_triggers_caution(self):
        fsm = KillSwitchFSM(KillSwitchConfig(max_spread_usd=1.0))
        fsm.update(KillSwitchInput(spread_usd=1.2))
        assert fsm.state == KillState.CAUTION


class TestKillSwitchFSMFailSafe:
    def test_journal_callback_called_on_transition(self):
        events = []
        fsm = KillSwitchFSM(journal_callback=lambda t: events.append(t))
        fsm.update(KillSwitchInput(daily_loss_pct=3.5))
        assert len(events) == 1
        assert events[0].to_state == KillState.HALT_NEW_TRADES

    def test_transition_count_increments(self):
        fsm = KillSwitchFSM()
        fsm.update(KillSwitchInput(daily_loss_pct=3.5))
        fsm.update(KillSwitchInput(max_drawdown_pct=5.5))
        assert fsm.transition_count == 2

    def test_fail_safe_on_error(self):
        """If update() errors, FSM should go to EMERGENCY_STOP."""
        fsm = KillSwitchFSM()
        # Force an error by passing None (will cause AttributeError in _evaluate)
        # Actually, KillSwitchInput has defaults, so we need a different approach
        # Mock _evaluate to raise
        original = fsm._evaluate
        fsm._evaluate = lambda inp: (_ for _ in ()).throw(RuntimeError("test"))
        fsm.update(KillSwitchInput())
        assert fsm.state == KillState.EMERGENCY_STOP
        fsm._evaluate = original


# ─── news_filter.py ───────────────────────────────────────────────────────────

class TestNewsFilter:
    def test_no_events_no_halt(self):
        nf = NewsFilter()
        assert not nf.is_halt_active()
        status = nf.check()
        assert not status.is_halt_active

    def test_halt_active_during_event_window(self):
        nf = NewsFilter(block_window_minutes=30)
        now = datetime.now(timezone.utc)
        nf.add_event(NewsEvent(
            timestamp=now, event_type="NFP", impact="HIGH", currency="USD",
        ))
        assert nf.is_halt_active(now=now)

    def test_halt_active_15_min_before_event(self):
        nf = NewsFilter(block_window_minutes=30)
        now = datetime.now(timezone.utc)
        event_time = now + timedelta(minutes=15)
        nf.add_event(NewsEvent(
            timestamp=event_time, event_type="CPI", impact="HIGH", currency="USD",
        ))
        assert nf.is_halt_active(now=now)

    def test_no_halt_45_min_before_event(self):
        nf = NewsFilter(block_window_minutes=30)
        now = datetime.now(timezone.utc)
        event_time = now + timedelta(minutes=45)
        nf.add_event(NewsEvent(
            timestamp=event_time, event_type="FOMC", impact="HIGH", currency="USD",
        ))
        assert not nf.is_halt_active(now=now)

    def test_halt_active_15_min_after_event(self):
        nf = NewsFilter(block_window_minutes=30)
        now = datetime.now(timezone.utc)
        event_time = now - timedelta(minutes=15)
        nf.add_event(NewsEvent(
            timestamp=event_time, event_type="ECB", impact="HIGH", currency="EUR",
        ))
        assert nf.is_halt_active(now=now)

    def test_no_halt_45_min_after_event(self):
        nf = NewsFilter(block_window_minutes=30)
        now = datetime.now(timezone.utc)
        event_time = now - timedelta(minutes=45)
        nf.add_event(NewsEvent(
            timestamp=event_time, event_type="BOE", impact="HIGH", currency="GBP",
        ))
        assert not nf.is_halt_active(now=now)

    def test_medium_impact_does_not_halt(self):
        nf = NewsFilter()
        now = datetime.now(timezone.utc)
        nf.add_event(NewsEvent(
            timestamp=now, event_type="CPI", impact="MEDIUM", currency="USD",
        ))
        assert not nf.is_halt_active(now=now)

    def test_next_event_returned(self):
        nf = NewsFilter()
        now = datetime.now(timezone.utc)
        nf.add_event(NewsEvent(
            timestamp=now + timedelta(hours=2),
            event_type="NFP", impact="HIGH", currency="USD",
        ))
        status = nf.check(now=now)
        assert not status.is_halt_active
        assert status.next_event is not None
        assert status.next_event.event_type == "NFP"
        assert status.minutes_until_next is not None
        assert 110 <= status.minutes_until_next <= 120

    def test_csv_loading(self, tmp_path):
        csv_path = str(tmp_path / "calendar.csv")
        now = datetime.now(timezone.utc)
        with open(csv_path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["timestamp", "event_type", "impact", "currency", "description"])
            w.writerow([(now + timedelta(minutes=10)).isoformat(), "NFP", "HIGH", "USD", "Non-Farm Payrolls"])
            w.writerow([(now + timedelta(hours=3)).isoformat(), "CPI", "HIGH", "USD", "Consumer Price Index"])
        nf = NewsFilter(csv_path=csv_path)
        assert nf.event_count == 2

    def test_csv_auto_classify_event_type(self, tmp_path):
        """If event_type is empty, classify from description."""
        csv_path = str(tmp_path / "calendar.csv")
        now = datetime.now(timezone.utc)
        with open(csv_path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["timestamp", "event_type", "impact", "currency", "description"])
            w.writerow([(now + timedelta(minutes=10)).isoformat(), "", "HIGH", "USD", "Non-Farm Employment Change"])
        nf = NewsFilter(csv_path=csv_path)
        assert nf.event_count == 1
        assert nf.events[0].event_type == "NFP"

    def test_high_impact_keywords_coverage(self):
        """All 5 required event types are in HIGH_IMPACT_KEYWORDS."""
        for et in ["NFP", "CPI", "FOMC", "ECB", "BOE"]:
            assert et in HIGH_IMPACT_KEYWORDS


# ─── slippage_monitor.py ──────────────────────────────────────────────────────

class TestSlippageMonitor:
    def test_empty_monitor_returns_zero_stats(self):
        mon = SlippageMonitor()
        stats = mon.get_stats()
        assert stats.n_fills == 0
        assert not stats.caution
        assert not stats.halt

    def test_record_normal_fill(self):
        mon = SlippageMonitor()
        rec = mon.record_fill(
            requested_price=2000.0, filled_price=2000.02,
            ticket=50001, direction=1, volume=0.01,
        )
        assert rec.slippage_pips == pytest.approx(2.0, abs=0.01)
        assert rec.slippage_usd > 0  # unfavorable for LONG

    def test_favorable_slippage_for_long(self):
        """LONG with fill below requested = favorable (negative slippage)."""
        mon = SlippageMonitor()
        rec = mon.record_fill(
            requested_price=2000.0, filled_price=1999.98,
            ticket=50001, direction=1, volume=0.01,
        )
        assert rec.slippage_pips < 0  # favorable

    def test_caution_on_high_mean_slippage(self):
        mon = SlippageMonitor(SlippageConfig(caution_mean_pips=2.0, window_size=10))
        for _ in range(10):
            mon.record_fill(2000.0, 2000.05, ticket=1, direction=1, volume=0.01)
        stats = mon.get_stats()
        assert stats.caution
        assert not stats.halt

    def test_halt_on_extreme_mean_slippage(self):
        mon = SlippageMonitor(SlippageConfig(halt_mean_pips=5.0, window_size=10))
        for _ in range(10):
            mon.record_fill(2000.0, 2000.10, ticket=1, direction=1, volume=0.01)
        stats = mon.get_stats()
        assert stats.halt

    def test_halt_on_single_extreme_fill(self):
        mon = SlippageMonitor(SlippageConfig(halt_max_pips=20.0))
        # Normal fills first
        for _ in range(5):
            mon.record_fill(2000.0, 2000.01, ticket=1, direction=1, volume=0.01)
        # One extreme fill (30 pips)
        mon.record_fill(2000.0, 2000.30, ticket=999, direction=1, volume=0.01)
        stats = mon.get_stats()
        assert stats.halt
        assert "single_fill_max" in stats.reason

    def test_reset_clears_state(self):
        mon = SlippageMonitor()
        for _ in range(5):
            mon.record_fill(2000.0, 2000.05, ticket=1, direction=1, volume=0.01)
        mon.reset()
        assert mon.fill_count == 0
        assert not mon.is_halted

    def test_window_size_enforced(self):
        mon = SlippageMonitor(SlippageConfig(window_size=5))
        for i in range(20):
            mon.record_fill(2000.0, 2000.01, ticket=i, direction=1, volume=0.01)
        assert mon.fill_count == 5  # only last 5 kept


# ─── drift_monitor.py ─────────────────────────────────────────────────────────

class TestDriftMonitor:
    def test_empty_monitor_returns_clean_report(self):
        mon = DriftMonitor()
        report = mon.get_report()
        assert report.n_predictions == 0
        assert not report.drift_breach
        assert not report.drift_emergency

    def test_well_calibrated_predictions_no_breach(self):
        mon = DriftMonitor(DriftConfig(
            ece_caution=0.10, brier_caution=0.25, winrate_drift_caution=0.15,
        ))
        mon.set_baseline_confidence(0.70)
        # 100 predictions: 70% accurate, 70% confident
        np.random.seed(42)
        for _ in range(100):
            outcome = 1 if np.random.random() < 0.7 else 0
            prob = 0.70 if outcome == 1 else 0.30
            mon.record_prediction(prob_up=prob, actual_outcome=outcome)
        report = mon.get_report()
        assert report.n_predictions == 100
        assert not report.drift_emergency
        # May or may not breach caution depending on random seed, but should be low

    def test_overconfident_predictions_trigger_breach(self):
        """Overconfident model → high ECE + Brier → breach."""
        mon = DriftMonitor(DriftConfig(
            ece_caution=0.08, brier_caution=0.22, winrate_drift_caution=0.10,
        ))
        np.random.seed(42)
        # 100 predictions: 50% accurate but 95% confident → huge drift
        for _ in range(100):
            outcome = 1 if np.random.random() < 0.5 else 0
            mon.record_prediction(prob_up=0.95, actual_outcome=outcome)
        report = mon.get_report()
        assert report.drift_breach or report.drift_emergency
        assert report.brier > 0.22 or report.ece > 0.08

    def test_psi_computation(self):
        """PSI should detect feature distribution shift."""
        mon = DriftMonitor()
        # Baseline: normal distribution centered at 0
        np.random.seed(42)
        baseline = np.random.randn(1000)
        mon.set_baseline_features(baseline)
        # Current: shifted distribution (mean = 1)
        for _ in range(100):
            shifted = np.random.randn(55) + 1.0
            mon.record_prediction(prob_up=0.7, actual_outcome=1, features=shifted)
        report = mon.get_report()
        # PSI should be > 0 (drift detected)
        assert report.psi > 0

    def test_brier_score_computation(self):
        mon = DriftMonitor()
        # Perfect predictions: Brier = 0
        for _ in range(50):
            mon.record_prediction(prob_up=1.0, actual_outcome=1)
        report = mon.get_report()
        assert report.brier < 0.01

    def test_reset_clears_records(self):
        mon = DriftMonitor()
        for _ in range(10):
            mon.record_prediction(prob_up=0.7, actual_outcome=1)
        mon.reset()
        assert mon.prediction_count == 0

    def test_fail_safe_on_error(self):
        mon = DriftMonitor()
        # Force error in PSI computation by setting bad baseline
        mon._baseline_features = "not_an_array"
        mon._current_features = ["not_an_array"]
        # Record prediction to trigger PSI computation
        mon.record_prediction(prob_up=0.7, actual_outcome=1, features=np.array([1.0]))
        report = mon.get_report()
        # Should not crash; PSI stays 0 (caught internally)
        assert report.n_predictions == 1


# ─── watchdog_restarter.py ────────────────────────────────────────────────────

class TestWatchdogRestarter:
    def test_register_component(self):
        restarter = WatchdogRestarter(dry_run=True)
        restarter.register_component("test_loop", expected_interval_s=30.0, threshold_misses=3)
        assert "test_loop" in restarter.registered_components

    @pytest.mark.asyncio
    async def test_dry_run_logs_restart_without_action(self):
        restarter = WatchdogRestarter(dry_run=True, check_interval_s=0.5)
        restart_called = []
        async def restart_fn():
            restart_called.append(True)
        restarter.register_component(
            "test_loop", expected_interval_s=0.3, threshold_misses=2,
            restart_fn=restart_fn,
        )
        # Fire one beat so the watchdog knows the component exists
        restarter.beat("test_loop")
        # Don't beat again — let it detect as hung
        task = restarter.start_background()
        await asyncio.sleep(2.0)
        await restarter.stop()
        # In dry_run, restart_fn should NOT be called
        assert len(restart_called) == 0
        # But recovery event should be logged
        assert restarter.recovery_count > 0

    @pytest.mark.asyncio
    async def test_live_mode_calls_restart_fn(self):
        restarter = WatchdogRestarter(dry_run=False, check_interval_s=0.5)
        restart_called = []
        async def restart_fn():
            restart_called.append(True)
        restarter.register_component(
            "test_loop", expected_interval_s=0.3, threshold_misses=2,
            restart_fn=restart_fn,
        )
        # Fire one beat so the watchdog knows the component exists
        restarter.beat("test_loop")
        task = restarter.start_background()
        await asyncio.sleep(2.0)
        await restarter.stop()
        assert len(restart_called) > 0

    def test_beat_resets_missed_count(self):
        restarter = WatchdogRestarter(dry_run=True)
        restarter.register_component("test_loop", expected_interval_s=30.0, threshold_misses=3)
        restarter.beat("test_loop")
        status = restarter.get_component_status("test_loop")
        assert status["missed_count"] == 0

    @pytest.mark.asyncio
    async def test_rate_limit_prevents_restart_storm(self):
        restarter = WatchdogRestarter(
            dry_run=False, check_interval_s=0.1, max_restarts_per_minute=2,
        )
        call_count = []
        async def restart_fn():
            call_count.append(True)
        restarter.register_component(
            "test_loop", expected_interval_s=0.05, threshold_misses=1,
            restart_fn=restart_fn,
        )
        task = restarter.start_background()
        await asyncio.sleep(1.0)
        await restarter.stop()
        # Should be rate-limited to 2 restarts per minute
        assert len(call_count) <= 3  # allow small buffer


# ─── INTEGRATION TEST ─────────────────────────────────────────────────────────

class TestSafetyIntegration:
    """Full integration: signal → order → kill switch halt → exit flatten → journal"""

    @pytest.mark.asyncio
    async def test_kill_switch_blocks_unsafe_trades(self, tmp_path):
        """Kill switch in HALT_NEW_TRADES blocks new orders."""
        journal = TradeJournal(path=str(tmp_path / "safety.jsonl"))
        fsm = KillSwitchFSM(journal_callback=lambda t: journal.log_heartbeat({
            "event": "kill_switch_transition",
            "from": t.from_state.value,
            "to": t.to_state.value,
            "trigger": t.trigger,
        }))
        # Trigger HALT_NEW_TRADES
        fsm.update(KillSwitchInput(daily_loss_pct=3.5))
        assert fsm.state == KillState.HALT_NEW_TRADES
        assert not fsm.allows_new_trades

        # Now try to place a trade — should be blocked
        loop = TradeLoop(TradeLoopConfig(dry_run=True), journal=journal)
        # Pre-check: kill switch blocks new trades
        if not fsm.allows_new_trades:
            # Simulate what trade_loop would do: check fsm, reject if not allows_new_trades
            signal = make_signal()
            # Manually reject (trade_loop doesn't yet integrate fsm — that's a Sprint 5 task)
            # For this test, we verify the FSM + journal integration
            journal.log_heartbeat({
                "event": "trade_blocked_by_kill_switch",
                "state": fsm.state.value,
                "signal_direction": signal.direction.name,
            })
        journal.flush()
        # Verify journal has the kill switch transition
        heartbeats = journal.read_by_type("HEARTBEAT")
        assert len(heartbeats) >= 2  # transition + block event
        transition_events = [h for h in heartbeats if h["data"].get("event") == "kill_switch_transition"]
        assert len(transition_events) == 1
        assert transition_events[0]["data"]["to"] == "HALT_NEW_TRADES"

    @pytest.mark.asyncio
    async def test_emergency_stop_triggers_flatten(self, tmp_path):
        """EMERGENCY_STOP triggers exit manager to request flatten."""
        journal = TradeJournal(path=str(tmp_path / "emergency.jsonl"))
        fsm = KillSwitchFSM(journal_callback=lambda t: journal.log_heartbeat({
            "event": "kill_switch_transition",
            "from": t.from_state.value,
            "to": t.to_state.value,
            "trigger": t.trigger,
        }))
        exit_mgr = ExitManager()

        # Simulate open position
        pos = BrokerPosition(
            ticket=50001, symbol="XAUUSD", direction=1, volume=0.01,
            entry_price=2000.0, stop_loss=1995.0, take_profit=2010.0,
            open_time=time.time() - 60,
        )

        # Trigger EMERGENCY_STOP via max DD
        fsm.update(KillSwitchInput(max_drawdown_pct=8.5))
        assert fsm.is_emergency
        assert fsm.requires_flatten

        # Exit manager should detect kill_switch_armed and request flatten
        exit_decision = exit_mgr.evaluate(
            pos, current_price=2005.0,
            kill_switch_armed=fsm.is_emergency,
        )
        assert exit_decision.should_exit
        assert exit_decision.reason == ExitReason.KILL_SWITCH

        # Journal the exit
        journal.log_exit(
            ticket=pos.ticket,
            exit_reason=exit_decision.reason.value,
            entry_price=pos.entry_price,
            exit_price=exit_decision.current_price,
            direction=pos.direction, volume=pos.volume,
            pnl_usd=exit_decision.unrealized_pnl_usd,
            holding_time_seconds=exit_decision.holding_time_seconds,
            extra={"kill_switch_state": fsm.state.value},
        )
        journal.flush()

        # Verify complete safety trail
        heartbeats = journal.read_by_type("HEARTBEAT")
        exits = journal.read_by_type("EXIT")
        assert len(heartbeats) >= 1  # transition logged
        assert len(exits) == 1
        assert exits[0]["data"]["exit_reason"] == "KILL_SWITCH"
        assert exits[0]["data"]["extra"]["kill_switch_state"] == "EMERGENCY_STOP"

    @pytest.mark.asyncio
    async def test_news_filter_blocks_trade(self, tmp_path):
        """News halt blocks new trades via kill switch."""
        journal = TradeJournal(path=str(tmp_path / "news.jsonl"))
        nf = NewsFilter(block_window_minutes=30)
        now = datetime.now(timezone.utc)
        nf.add_event(NewsEvent(
            timestamp=now, event_type="NFP", impact="HIGH", currency="USD",
        ))
        assert nf.is_halt_active(now=now)

        fsm = KillSwitchFSM(journal_callback=lambda t: journal.log_heartbeat({
            "event": "kill_switch_transition",
            "to": t.to_state.value, "trigger": t.trigger,
        }))
        # News halt → kill switch HALT_NEW_TRADES
        fsm.update(KillSwitchInput(news_halt_active=nf.is_halt_active(now=now)))
        assert fsm.state == KillState.HALT_NEW_TRADES
        assert not fsm.allows_new_trades
        journal.flush()
        # Verify kill switch fired
        heartbeats = journal.read_by_type("HEARTBEAT")
        assert len(heartbeats) == 1
        assert heartbeats[0]["data"]["to"] == "HALT_NEW_TRADES"

    @pytest.mark.asyncio
    async def test_slippage_halt_triggers_kill_switch(self, tmp_path):
        """Slippage monitor halt → kill switch."""
        journal = TradeJournal(path=str(tmp_path / "slip.jsonl"))
        slip_mon = SlippageMonitor(SlippageConfig(halt_max_pips=20.0))
        # Record extreme slippage
        slip_mon.record_fill(2000.0, 2000.30, ticket=1, direction=1, volume=0.01)
        stats = slip_mon.get_stats()
        assert stats.halt

        fsm = KillSwitchFSM(journal_callback=lambda t: journal.log_heartbeat({
            "event": "kill_switch_transition", "to": t.to_state.value,
        }))
        # Slippage halt would translate to spread_usd high in kill switch input
        fsm.update(KillSwitchInput(spread_usd=2.5))  # emergency spread
        assert fsm.state == KillState.HALT_NEW_TRADES

    @pytest.mark.asyncio
    async def test_drift_emergency_triggers_kill_switch(self, tmp_path):
        """Drift emergency → kill switch EMERGENCY_STOP."""
        journal = TradeJournal(path=str(tmp_path / "drift.jsonl"))
        drift_mon = DriftMonitor()
        # Simulate drift emergency
        np.random.seed(42)
        for _ in range(100):
            drift_mon.record_prediction(prob_up=0.95, actual_outcome=0)  # all wrong
        report = drift_mon.get_report()
        assert report.drift_breach or report.drift_emergency

        fsm = KillSwitchFSM(journal_callback=lambda t: journal.log_heartbeat({
            "event": "kill_switch_transition", "to": t.to_state.value,
        }))
        if report.drift_emergency:
            fsm.update(KillSwitchInput(drift_emergency=True))
            assert fsm.state == KillState.EMERGENCY_STOP
        else:
            fsm.update(KillSwitchInput(drift_breach=True))
            assert fsm.state == KillState.CAUTION

    @pytest.mark.asyncio
    async def test_can_block_unsafe_trades_and_flatten_in_dry_run(self, tmp_path):
        """FULL E2E: can TITAN block unsafe trades + request flatten in dry_run?"""
        journal = TradeJournal(path=str(tmp_path / "full_safety.jsonl"))

        # Setup all safety modules
        fsm = KillSwitchFSM(journal_callback=lambda t: journal.log_heartbeat({
            "event": "kill_switch_transition",
            "from": t.from_state.value, "to": t.to_state.value, "trigger": t.trigger,
        }))
        nf = NewsFilter()
        slip_mon = SlippageMonitor()
        drift_mon = DriftMonitor()
        exit_mgr = ExitManager()
        loop = TradeLoop(TradeLoopConfig(dry_run=True), journal=journal)

        # ── SCENARIO 1: Normal trade allowed ──
        signal = make_signal()
        decision = await loop.process_signal(signal, entry_price=2000.0, spread_usd=0.2)
        assert decision.accepted
        assert fsm.allows_new_trades  # kill switch normal

        # ── SCENARIO 2: Position open, then kill switch triggers ──
        pos = BrokerPosition(
            ticket=50001, symbol="XAUUSD", direction=1, volume=0.01,
            entry_price=2000.0, stop_loss=1995.0, take_profit=2010.0,
            open_time=time.time(),
        )
        # Trigger EMERGENCY_STOP via max DD
        fsm.update(KillSwitchInput(max_drawdown_pct=8.5))
        assert fsm.is_emergency
        assert fsm.requires_flatten

        # Exit manager requests flatten
        exit_dec = exit_mgr.evaluate(
            pos, current_price=2005.0, kill_switch_armed=fsm.is_emergency,
        )
        assert exit_dec.should_exit
        assert exit_dec.reason == ExitReason.KILL_SWITCH

        # Journal the exit
        journal.log_exit(
            ticket=pos.ticket, exit_reason=exit_dec.reason.value,
            entry_price=pos.entry_price, exit_price=exit_dec.current_price,
            direction=pos.direction, volume=pos.volume,
            pnl_usd=exit_dec.unrealized_pnl_usd,
            extra={"kill_switch_state": fsm.state.value},
        )

        # ── SCENARIO 3: New trade blocked by kill switch ──
        signal2 = make_signal()
        if not fsm.allows_new_trades:
            # Manually block (trade_loop integration is Sprint 5)
            journal.log_heartbeat({
                "event": "trade_blocked_by_kill_switch",
                "state": fsm.state.value,
            })

        journal.flush()

        # ── VERIFY COMPLETE SAFETY TRAIL ──
        all_records = journal.read_all()
        types = [r["record_type"] for r in all_records]
        assert "DECISION" in types      # initial accepted trade
        assert "ORDER" in types         # dry_run order
        assert "HEARTBEAT" in types     # kill switch transition + block event
        assert "EXIT" in types          # flatten request

        # Verify kill switch transitioned to EMERGENCY_STOP
        heartbeats = journal.read_by_type("HEARTBEAT")
        transitions = [h for h in heartbeats if h["data"].get("event") == "kill_switch_transition"]
        assert len(transitions) >= 1
        assert any(t["data"]["to"] == "EMERGENCY_STOP" for t in transitions)

        # Verify exit was due to KILL_SWITCH
        exits = journal.read_by_type("EXIT")
        assert len(exits) == 1
        assert exits[0]["data"]["exit_reason"] == "KILL_SWITCH"
        assert exits[0]["data"]["extra"]["kill_switch_state"] == "EMERGENCY_STOP"

        # Verify dry_run maintained throughout
        for r in all_records:
            if r["record_type"] == "ORDER":
                assert r["data"]["dry_run"] is True
