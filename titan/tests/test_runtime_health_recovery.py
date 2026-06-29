"""
TITAN XAU AI — Sprint 9.9.3.26 Runtime Health & Recovery Tests
================================================================

Tests for RuntimeHealthMonitor and incident reporting.
All tests use mocks — no MT5 connection required.
"""
from __future__ import annotations
import json
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from titan.production.runtime_health import (
    RuntimeHealthMonitor, HealthEvent, HealthStatus, RecoveryAction,
    write_incident_report,
    MAX_CLOSE_RETRIES, STALE_TICK_THRESHOLD,
)


# ─── Mock helpers ─────────────────────────────────────────────────────────────

class MockAccount:
    def __init__(self, login=12345678, server="MetaQuotes-Demo", trade_mode=0,
                 balance=10000.0):
        self.login = login
        self.server = server
        self.trade_mode = trade_mode
        self.balance = balance
        self.equity = balance
        self.trade_expert = True
        self.trade_allowed = True


class MockTerminal:
    def __init__(self, connected=True):
        self.connected = connected
        self.name = "MetaTrader 5"
        self.trade_allowed = True
        self.tradeapi_disabled = False


class MockTick:
    def __init__(self, bid=2000.0, ask=2000.1, age_seconds=0):
        self.bid = bid
        self.ask = ask
        self.time = int(time.time() - age_seconds)
        self.time_msc = self.time * 1000
        self.volume = 100
        self.flags = 2


class MockSymbolInfo:
    def __init__(self, visible=True):
        self.name = "XAUUSD"
        self.visible = visible
        self.digits = 2
        self.point = 0.01
        self.spread = 10
        self.trade_mode = 4
        self.trade_exemode = 2
        self.filling_mode = 3
        self.volume_min = 0.01
        self.volume_max = 100.0
        self.volume_step = 0.01


class MockPosition:
    def __init__(self, ticket=1001, magic=20261993, symbol="XAUUSD"):
        self.ticket = ticket
        self.magic = magic
        self.symbol = symbol
        self.type = 0  # BUY
        self.volume = 0.01
        self.price_open = 2000.0
        self.profit = 0.0


class _Sentinel:
    """Sentinel to distinguish 'not provided' from 'provided as None'."""
    pass

_SENTINEL = _Sentinel()


class MockMT5:
    """Minimal mock for MT5 module."""
    def __init__(self, connected=True, account=None, terminal=None,
                 symbol_info=_SENTINEL, tick=None, positions=None,
                 initialize_returns=True):
        self._connected = connected
        self._account = account or MockAccount()
        self._terminal = terminal or MockTerminal(connected=connected)
        self._symbol_info = MockSymbolInfo() if symbol_info is _SENTINEL else symbol_info
        self._tick = tick or MockTick()
        self._positions = positions or []
        self._initialize_returns = initialize_returns
        self._initialized = False

    def initialize(self):
        self._initialized = self._initialize_returns
        return self._initialize_returns

    def shutdown(self):
        self._initialized = False

    def account_info(self):
        return self._account if self._initialized else None

    def terminal_info(self):
        return self._terminal if self._initialized else None

    def symbol_info(self, symbol):
        return self._symbol_info if self._initialized else None

    def symbol_info_tick(self, symbol):
        return self._tick if self._initialized else None

    def positions_get(self, symbol=None, ticket=None):
        if not self._initialized:
            return None
        return list(self._positions)


# ─── Tests ────────────────────────────────────────────────────────────────────

class TestStartupChecks:
    """Startup health check tests."""

    def test_01_healthy_startup(self):
        """Healthy startup produces no critical events."""
        mt5 = MockMT5()
        monitor = RuntimeHealthMonitor(mt5=mt5, magic=20261993, symbol="XAUUSD")
        events = monitor.check_startup()
        # Should have no critical events
        critical = [e for e in events if e.severity == HealthStatus.CRITICAL]
        assert len(critical) == 0, f"Unexpected critical events: {critical}"

    def test_02_mt5_unavailable_blocks_start(self):
        """MT5 module None blocks start."""
        monitor = RuntimeHealthMonitor(mt5=None, magic=20261993, symbol="XAUUSD")
        events = monitor.check_startup()
        assert monitor.should_block_start(events) is True

    def test_03_mt5_initialize_failure_blocks_start(self):
        """mt5.initialize() failure blocks start."""
        mt5 = MockMT5(initialize_returns=False)
        monitor = RuntimeHealthMonitor(mt5=mt5, magic=20261993, symbol="XAUUSD")
        events = monitor.check_startup()
        assert monitor.should_block_start(events) is True

    def test_04_terminal_closed_detected(self):
        """Terminal closed is detected."""
        mt5 = MockMT5(terminal=MockTerminal(connected=False))
        monitor = RuntimeHealthMonitor(mt5=mt5, magic=20261993, symbol="XAUUSD")
        events = monitor.check_startup()
        terminal_events = [e for e in events if e.event_type == "TERMINAL_CLOSED"]
        assert len(terminal_events) >= 1

    def test_05_account_not_demo_blocks_start(self):
        """Non-DEMO account blocks start."""
        mt5 = MockMT5(account=MockAccount(trade_mode=2))  # REAL
        monitor = RuntimeHealthMonitor(mt5=mt5, magic=20261993, symbol="XAUUSD")
        events = monitor.check_startup()
        assert monitor.should_block_start(events) is True
        not_demo = [e for e in events if e.event_type == "ACCOUNT_NOT_DEMO"]
        assert len(not_demo) >= 1

    def test_06_symbol_unavailable_detected(self):
        """Symbol unavailable is detected."""
        mt5 = MockMT5(symbol_info=None)
        monitor = RuntimeHealthMonitor(mt5=mt5, magic=20261993, symbol="XAUUSD")
        events = monitor.check_startup()
        sym_events = [e for e in events if e.event_type == "SYMBOL_UNAVAILABLE"]
        assert len(sym_events) >= 1

    def test_07_stale_tick_detected(self):
        """Stale tick is detected."""
        mt5 = MockMT5(tick=MockTick(age_seconds=120))  # 2 min old
        monitor = RuntimeHealthMonitor(mt5=mt5, magic=20261993, symbol="XAUUSD")
        events = monitor.check_startup()
        stale = [e for e in events if e.event_type == "STALE_TICK"]
        assert len(stale) >= 1
        assert stale[0].action == RecoveryAction.WAIT_RETRY

    def test_08_existing_position_blocks_start(self):
        """Existing TITAN position on startup blocks start."""
        pos = MockPosition(ticket=99999, magic=20261993)
        mt5 = MockMT5(positions=[pos])
        monitor = RuntimeHealthMonitor(mt5=mt5, magic=20261993, symbol="XAUUSD")
        events = monitor.check_startup()
        assert monitor.should_block_start(events) is True
        existing = [e for e in events if e.event_type == "EXISTING_POSITION"]
        assert len(existing) >= 1

    def test_09_journal_writable_check_passes(self, tmp_path):
        """Journal writable check passes for a valid path."""
        mt5 = MockMT5()
        monitor = RuntimeHealthMonitor(
            mt5=mt5, magic=20261993, symbol="XAUUSD",
            journal_path=str(tmp_path / "journal.jsonl"),
        )
        events = monitor.check_startup()
        journal_events = [e for e in events if e.event_type == "JOURNAL_WRITE_FAILURE"]
        assert len(journal_events) == 0

    def test_10_journal_writable_check_fails(self):
        """Journal writable check fails for invalid path."""
        mt5 = MockMT5()
        monitor = RuntimeHealthMonitor(
            mt5=mt5, magic=20261993, symbol="XAUUSD",
            journal_path="/nonexistent_root/path/journal.jsonl",
        )
        events = monitor.check_startup()
        journal_events = [e for e in events if e.event_type == "JOURNAL_WRITE_FAILURE"]
        assert len(journal_events) >= 1


class TestRuntimeChecks:
    """Runtime (mid-cycle) health check tests."""

    def test_11_account_switch_detected(self):
        """Account login change mid-cycle is detected."""
        mt5 = MockMT5()
        monitor = RuntimeHealthMonitor(mt5=mt5, magic=20261993, symbol="XAUUSD")
        monitor.check_startup()  # captures initial login
        # Simulate account switch
        mt5._account.login = 99999999
        events = monitor.check_account_switch()
        switch_events = [e for e in events if e.event_type == "ACCOUNT_SWITCHED"]
        assert len(switch_events) >= 1
        assert monitor.should_force_close(events) is True

    def test_12_server_switch_detected(self):
        """Server change mid-cycle is detected."""
        mt5 = MockMT5()
        monitor = RuntimeHealthMonitor(mt5=mt5, magic=20261993, symbol="XAUUSD")
        monitor.check_startup()
        mt5._account.server = "FBS-Demo"
        events = monitor.check_account_switch()
        switch_events = [e for e in events if e.event_type == "ACCOUNT_SWITCHED"]
        assert len(switch_events) >= 1

    def test_13_order_send_success_no_event(self):
        """Successful order_send produces no events."""
        mt5 = MockMT5()
        monitor = RuntimeHealthMonitor(mt5=mt5, magic=20261993, symbol="XAUUSD")
        events = monitor.check_order_send_result(10009, operation="open")
        assert len(events) == 0

    def test_14_order_send_reject_retryable(self):
        """Retryable reject (10006) produces RETRY action."""
        mt5 = MockMT5()
        monitor = RuntimeHealthMonitor(mt5=mt5, magic=20261993, symbol="XAUUSD")
        events = monitor.check_order_send_result(10006, operation="open")
        assert len(events) >= 1
        assert events[0].action == RecoveryAction.RETRY

    def test_15_order_send_market_closed_stops_cycle(self):
        """Sprint 9.9.3.27 — MARKET_CLOSED (10018) on open with no position
        produces WARNING + STOP_CYCLE (not CRITICAL STOP_ALL).
        This is a normal weekend/market-closed scenario, not a system failure."""
        mt5 = MockMT5()
        monitor = RuntimeHealthMonitor(mt5=mt5, magic=20261993, symbol="XAUUSD")
        events = monitor.check_order_send_result(10018, operation="open",
                                                   has_open_position=False)
        assert len(events) >= 1
        assert events[0].action == RecoveryAction.STOP_CYCLE
        assert events[0].severity == HealthStatus.WARNING
        assert events[0].event_type == "MARKET_CLOSED"

    def test_16_close_reject_escalates_to_force_close(self):
        """Close reject with non-retryable code escalates to FORCE_CLOSE_ALL."""
        mt5 = MockMT5()
        monitor = RuntimeHealthMonitor(mt5=mt5, magic=20261993, symbol="XAUUSD")
        events = monitor.check_close_result(10013)  # INVALID_REQUEST
        assert len(events) >= 1
        assert events[0].action == RecoveryAction.FORCE_CLOSE_ALL

    def test_17_stuck_position_detected(self):
        """Stuck position (still open after close attempts) is detected."""
        pos = MockPosition(ticket=88888, magic=20261993)
        mt5 = MockMT5(positions=[pos])
        mt5._initialized = True  # force initialized for position check
        monitor = RuntimeHealthMonitor(mt5=mt5, magic=20261993, symbol="XAUUSD")
        events = monitor.check_stuck_position(max_close_retries=3)
        stuck = [e for e in events if e.event_type == "STUCK_POSITION"]
        assert len(stuck) >= 1
        assert monitor.should_force_close(events) is True

    def test_18_loop_crash_recorded(self):
        """Loop crash is recorded with traceback."""
        mt5 = MockMT5()
        monitor = RuntimeHealthMonitor(mt5=mt5, magic=20261993, symbol="XAUUSD")
        try:
            raise ValueError("Test crash")
        except ValueError as e:
            events = monitor.check_loop_crash(e)
        assert len(events) >= 1
        assert events[0].event_type == "LOOP_CRASH"
        assert "Test crash" in events[0].message
        assert "traceback" in events[0].details

    def test_19_tick_health_fresh_tick_no_event(self):
        """Fresh tick produces no stale tick event."""
        mt5 = MockMT5(tick=MockTick(age_seconds=5))
        mt5._initialized = True  # force initialized for tick check
        monitor = RuntimeHealthMonitor(mt5=mt5, magic=20261993, symbol="XAUUSD")
        events = monitor.check_tick_health()
        stale = [e for e in events if e.event_type == "STALE_TICK"]
        assert len(stale) == 0


class TestRecoveryDecisions:
    """Recovery decision logic tests."""

    def test_20_should_block_start(self):
        """should_block_start returns True for BLOCK_START events."""
        mt5 = MockMT5(account=MockAccount(trade_mode=2))
        monitor = RuntimeHealthMonitor(mt5=mt5, magic=20261993, symbol="XAUUSD")
        events = monitor.check_startup()
        assert monitor.should_block_start(events) is True

    def test_21_should_stop_all(self):
        """should_stop returns True for STOP_ALL events."""
        event = HealthEvent("TEST", HealthStatus.CRITICAL, RecoveryAction.STOP_ALL, "test")
        monitor = RuntimeHealthMonitor(mt5=None, magic=20261993)
        assert monitor.should_stop([event]) is True

    def test_22_should_force_close(self):
        """should_force_close returns True for FORCE_CLOSE_ALL events."""
        event = HealthEvent("TEST", HealthStatus.CRITICAL, RecoveryAction.FORCE_CLOSE_ALL, "test")
        monitor = RuntimeHealthMonitor(mt5=None, magic=20261993)
        assert monitor.should_force_close([event]) is True

    def test_23_should_stop_cycle(self):
        """should_stop_cycle returns True for STOP_CYCLE events."""
        event = HealthEvent("TEST", HealthStatus.CRITICAL, RecoveryAction.STOP_CYCLE, "test")
        monitor = RuntimeHealthMonitor(mt5=None, magic=20261993)
        assert monitor.should_stop_cycle([event]) is True

    def test_24_continue_for_healthy(self):
        """No events = no stop, no block, no force close."""
        monitor = RuntimeHealthMonitor(mt5=None, magic=20261993)
        assert monitor.should_block_start([]) is False
        assert monitor.should_stop([]) is False
        assert monitor.should_force_close([]) is False
        assert monitor.should_stop_cycle([]) is False


class TestHealthStatus:
    """Health status summary tests."""

    def test_25_healthy_status(self):
        """No events = HEALTHY status."""
        monitor = RuntimeHealthMonitor(mt5=None, magic=20261993)
        status = monitor.get_health_status()
        assert status["status"] == "HEALTHY"
        assert status["event_count"] == 0

    def test_26_critical_status(self):
        """Critical event = CRITICAL status."""
        monitor = RuntimeHealthMonitor(mt5=None, magic=20261993)
        monitor._record(HealthEvent("TEST", HealthStatus.CRITICAL,
                                      RecoveryAction.STOP_ALL, "test"))
        status = monitor.get_health_status()
        assert status["status"] == "CRITICAL"

    def test_27_warning_status(self):
        """Warning event = WARNING status."""
        monitor = RuntimeHealthMonitor(mt5=None, magic=20261993)
        monitor._record(HealthEvent("TEST", HealthStatus.WARNING,
                                      RecoveryAction.CONTINUE, "test"))
        status = monitor.get_health_status()
        assert status["status"] == "WARNING"


class TestIncidentReport:
    """Incident report writer tests."""

    def test_28_incident_report_json_and_md(self, tmp_path):
        """Incident report writes both JSON and MD files."""
        events = [
            HealthEvent("TEST_ERROR", HealthStatus.CRITICAL,
                        RecoveryAction.STOP_ALL, "Test critical error",
                        {"detail": "value"}),
        ]
        result = write_incident_report(events, context={"cycle": "test"},
                                         output_dir=tmp_path)
        assert Path(result["json_path"]).exists()
        assert Path(result["md_path"]).exists()

        with open(result["json_path"]) as f:
            data = json.load(f)
        assert data["event_count"] == 1
        assert data["max_severity"] == "CRITICAL"
        assert data["events"][0]["event_type"] == "TEST_ERROR"

        md = Path(result["md_path"]).read_text()
        assert "Incident Report" in md
        assert "TEST_ERROR" in md
        assert "CRITICAL" in md

    def test_29_incident_report_multiple_events(self, tmp_path):
        """Incident report handles multiple events."""
        events = [
            HealthEvent("EVENT_1", HealthStatus.WARNING, RecoveryAction.RETRY, "First"),
            HealthEvent("EVENT_2", HealthStatus.CRITICAL, RecoveryAction.STOP_ALL, "Second"),
            HealthEvent("EVENT_3", HealthStatus.WARNING, RecoveryAction.CONTINUE, "Third"),
        ]
        result = write_incident_report(events, output_dir=tmp_path)
        with open(result["json_path"]) as f:
            data = json.load(f)
        assert data["event_count"] == 3
        assert data["max_severity"] == "CRITICAL"

    def test_30_incident_report_empty_events(self, tmp_path):
        """Incident report handles empty events list."""
        result = write_incident_report([], output_dir=tmp_path)
        with open(result["json_path"]) as f:
            data = json.load(f)
        assert data["event_count"] == 0
        assert data["max_severity"] == "HEALTHY"


class TestHealthEventFields:
    """HealthEvent field tests."""

    def test_31_health_event_to_dict(self):
        """HealthEvent.to_dict() has all required fields."""
        event = HealthEvent(
            "TEST", HealthStatus.WARNING, RecoveryAction.RETRY,
            "test message", {"key": "value"},
        )
        d = event.to_dict()
        assert d["event_type"] == "TEST"
        assert d["severity"] == "WARNING"
        assert d["action"] == "RETRY"
        assert d["message"] == "test message"
        assert d["details"] == {"key": "value"}
        assert "timestamp_utc" in d

    def test_32_health_event_repr(self):
        """HealthEvent has a useful repr."""
        event = HealthEvent("TEST", HealthStatus.CRITICAL,
                            RecoveryAction.STOP_ALL, "test")
        r = repr(event)
        assert "TEST" in r
        assert "CRITICAL" in r
        assert "STOP_ALL" in r
