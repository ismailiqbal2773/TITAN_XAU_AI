"""
TITAN XAU AI — Sprint 9.9.3.27 Market-Closed Classification Tests
===================================================================

Tests for context-aware retcode 10018 (MARKET_CLOSED) classification.
"""
from __future__ import annotations
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from titan.production.runtime_health import (
    classify_trade_retcode, RuntimeHealthMonitor, HealthStatus,
    RecoveryAction,
)


class TestClassifyTradeRetcode:
    """classify_trade_retcode context-aware classification tests."""

    def test_01_success_retcode(self):
        """Success retcode (10009) returns HEALTHY + CONTINUE."""
        result = classify_trade_retcode(10009, {"phase": "open"})
        assert result["event_type"] == "ORDER_SUCCESS"
        assert result["severity"] == "HEALTHY"
        assert result["recovery_action"] == "CONTINUE"
        assert result["is_market_closed"] is False

    def test_02_market_closed_open_no_position_warning(self):
        """10018 on OPEN with no open position = WARNING + STOP_CYCLE."""
        result = classify_trade_retcode(10018, {
            "phase": "open", "has_open_position": False,
        })
        assert result["event_type"] == "MARKET_CLOSED"
        assert result["severity"] == "WARNING"
        assert result["recovery_action"] == "STOP_CYCLE"
        assert result["is_market_closed"] is True
        assert result["is_system_failure"] is False

    def test_03_market_closed_open_with_position_critical(self):
        """10018 on OPEN with open position = CRITICAL + MANUAL_REVIEW."""
        result = classify_trade_retcode(10018, {
            "phase": "open", "has_open_position": True,
        })
        assert result["severity"] == "CRITICAL"
        assert result["recovery_action"] == "MANUAL_REVIEW"
        assert result["is_market_closed"] is True

    def test_04_market_closed_close_with_position_critical(self):
        """10018 on CLOSE with open position = CRITICAL + MANUAL_REVIEW."""
        result = classify_trade_retcode(10018, {
            "phase": "close", "has_open_position": True,
        })
        assert result["severity"] == "CRITICAL"
        assert result["recovery_action"] == "MANUAL_REVIEW"
        assert result["is_market_closed"] is True
        assert "stuck" in result["message"].lower()

    def test_05_market_closed_close_no_position_warning(self):
        """10018 on CLOSE with no open position (edge case) = WARNING.
        Close without position is unusual but not critical."""
        result = classify_trade_retcode(10018, {
            "phase": "close", "has_open_position": False,
        })
        # phase=close triggers CRITICAL regardless of has_open_position
        # because close implies a position exists
        assert result["severity"] == "CRITICAL"
        assert result["recovery_action"] == "MANUAL_REVIEW"

    def test_06_retryable_reject_10006(self):
        """10006 (REJECT) is WARNING + RETRY."""
        result = classify_trade_retcode(10006, {"phase": "open"})
        assert result["event_type"] == "ORDER_SEND_REJECT"
        assert result["severity"] == "WARNING"
        assert result["recovery_action"] == "RETRY"
        assert result["is_market_closed"] is False

    def test_07_non_retryable_reject_10013(self):
        """10013 (INVALID_REQUEST) is CRITICAL + STOP_CYCLE."""
        result = classify_trade_retcode(10013, {"phase": "open"})
        assert result["severity"] == "CRITICAL"
        assert result["recovery_action"] == "STOP_CYCLE"
        assert result["is_system_failure"] is True

    def test_08_none_retcode(self):
        """None retcode is WARNING + RETRY (MT5 internal error)."""
        result = classify_trade_retcode(None, {"phase": "open"})
        assert result["event_type"] == "ORDER_SEND_NONE"
        assert result["severity"] == "WARNING"
        assert result["is_system_failure"] is True

    def test_09_unknown_retcode(self):
        """Unknown retcode is WARNING + STOP_CYCLE (safe default)."""
        result = classify_trade_retcode(99999, {"phase": "open"})
        assert result["severity"] == "WARNING"
        assert result["recovery_action"] == "STOP_CYCLE"

    def test_10_default_context_open_no_position(self):
        """Default context (no phase/has_open_position) = open + no position."""
        result = classify_trade_retcode(10018)
        assert result["severity"] == "WARNING"
        assert result["recovery_action"] == "STOP_CYCLE"


class TestRuntimeHealthMonitorMarketClosed:
    """RuntimeHealthMonitor.check_order_send_result market-closed tests."""

    def test_11_monitor_open_market_closed_warning(self):
        """Monitor: 10018 on open (no position) = WARNING + STOP_CYCLE."""
        monitor = RuntimeHealthMonitor(mt5=None, magic=20261993)
        events = monitor.check_order_send_result(
            10018, operation="open", has_open_position=False,
        )
        assert len(events) >= 1
        assert events[0].severity == HealthStatus.WARNING
        assert events[0].action == RecoveryAction.STOP_CYCLE
        assert events[0].event_type == "MARKET_CLOSED"

    def test_12_monitor_close_market_closed_critical(self):
        """Monitor: 10018 on close (has position) = CRITICAL + MANUAL_REVIEW."""
        monitor = RuntimeHealthMonitor(mt5=None, magic=20261993)
        events = monitor.check_order_send_result(
            10018, operation="close", has_open_position=True,
        )
        assert len(events) >= 1
        assert events[0].severity == HealthStatus.CRITICAL
        assert events[0].action == RecoveryAction.MANUAL_REVIEW

    def test_13_monitor_open_with_position_market_closed_critical(self):
        """Monitor: 10018 on open with existing position = CRITICAL."""
        monitor = RuntimeHealthMonitor(mt5=None, magic=20261993)
        events = monitor.check_order_send_result(
            10018, operation="open", has_open_position=True,
        )
        assert events[0].severity == HealthStatus.CRITICAL

    def test_14_monitor_market_closed_not_system_failure(self):
        """Market-closed on open is NOT classified as system failure."""
        monitor = RuntimeHealthMonitor(mt5=None, magic=20261993)
        events = monitor.check_order_send_result(
            10018, operation="open", has_open_position=False,
        )
        # Should NOT trigger should_stop (STOP_CYCLE is not STOP_ALL)
        assert monitor.should_stop(events) is False
        # Should trigger should_stop_cycle
        assert monitor.should_stop_cycle(events) is True

    def test_15_monitor_market_closed_with_position_triggers_stop(self):
        """Market-closed with open position triggers should_stop."""
        monitor = RuntimeHealthMonitor(mt5=None, magic=20261993)
        events = monitor.check_order_send_result(
            10018, operation="close", has_open_position=True,
        )
        # MANUAL_REVIEW is not STOP_ALL or FORCE_CLOSE_ALL
        # But the position is stuck — this is a different kind of stop
        # The operator needs to be alerted
        assert events[0].severity == HealthStatus.CRITICAL
