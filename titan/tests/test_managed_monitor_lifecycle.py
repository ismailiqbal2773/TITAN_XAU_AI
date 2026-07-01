"""TITAN XAU AI - Sprint 9.9.3.45.5 Managed Monitor Lifecycle Tests

Sprint 9.9.3.45.5: Monitor must not complete after one evaluation
unless position closed, timeout reached, gate blocked, or unrecoverable
error. Final OPEN requires final positions_get evidence. Position
disappearing without history => UNKNOWN/WARNING, not OPEN.

Tests mock MT5 (no real broker calls, no order_send).
"""
from __future__ import annotations
import re, sys
from pathlib import Path
import pytest
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


def _strip(src):
    src = re.sub(r'"""[\s\S]*?"""', '""', src)
    src = re.sub(r"'''[\s\S]*?'''", "''", src)
    src = re.sub(r'"(?:[^"\\]|\\.)*"', '""', src)
    src = re.sub(r"'(?:[^'\\]|\\.)*'", "''", src)
    return src


class TestMonitorLifecycle:
    def test_01_run_monitor_loop_function_exists(self):
        """_run_monitor_loop must exist in run_managed_demo_micro_trade."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        assert "def _run_monitor_loop" in src

    def test_02_monitor_loop_has_iterations_counter(self):
        """Loop must track monitor_iterations."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        assert "monitor_iterations" in src
        # Must be incremented in loop
        assert "monitor_iterations = iteration" in src or "monitor_iterations +=" in src

    def test_03_monitor_loop_has_duration(self):
        """Loop must track monitor_duration_seconds."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        assert "monitor_duration_seconds" in src
        assert "_time.time()" in src or "time.time()" in src

    def test_04_monitor_loop_has_stop_reason(self):
        """Loop must produce monitor_stop_reason."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        assert "monitor_stop_reason" in src

    def test_05_stop_reasons_supported(self):
        """All required stop reasons must be present in source."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        required_reasons = [
            "POSITION_CLOSED",
            "TIMEOUT_REACHED",
            "POSITION_DISAPPEARED_WITHOUT_HISTORY",
        ]
        for r in required_reasons:
            assert r in src, f"Missing stop reason: {r}"

    def test_06_final_position_status_unknown_when_disappeared(self):
        """If position disappears without history, final_position_status
        must be UNKNOWN."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        # Look for the assignment pattern: final_position_status = "UNKNOWN"
        # followed (within ~200 chars) by monitor_stop_reason = "POSITION_DISAPPEARED_WITHOUT_HISTORY"
        import re
        pattern = r'final_position_status\s*=\s*"UNKNOWN".{0,300}monitor_stop_reason\s*=\s*"POSITION_DISAPPEARED_WITHOUT_HISTORY"'
        assert re.search(pattern, src, re.DOTALL), \
            "Expected final_position_status=UNKNOWN assignment followed by POSITION_DISAPPEARED_WITHOUT_HISTORY"

    def test_07_final_position_status_open_requires_positions_get(self):
        """final_position_status=OPEN must require final positions_get check."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        # The timeout branch must do a final positions_get
        idx = src.find("TIMEOUT_REACHED")
        assert idx > 0
        # Look backwards for the verification logic
        before = src[max(0, idx-2000):idx]
        assert "still_open" in before or "final_positions" in before

    def test_08_monitor_loop_checks_positions_each_iteration(self):
        """Each iteration must poll positions_get to check if position
        still open."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        idx = src.find("def _run_monitor_loop")
        end_idx = src.find("\ndef ", idx + 1)
        body = src[idx:end_idx if end_idx > 0 else len(src)]
        # Must call mt5.positions_get inside the loop
        assert "mt5.positions_get" in body
        # Must check if position ticket matches
        assert "current_position" in body

    def test_09_monitor_loop_checks_history_on_disappear(self):
        """When position disappears, must check history_deals_get."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        idx = src.find("def _run_monitor_loop")
        end_idx = src.find("\ndef ", idx + 1)
        body = src[idx:end_idx if end_idx > 0 else len(src)]
        assert "history_deals_get" in body

    def test_10_monitor_loop_max_iterations_cap(self):
        """Loop must have a safety cap on max_iterations to prevent
        infinite loops in tests."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        idx = src.find("def _run_monitor_loop")
        end_idx = src.find("\ndef ", idx + 1)
        body = src[idx:end_idx if end_idx > 0 else len(src)]
        assert "max_iterations" in body
        # Must be capped (not unbounded)
        assert "10000" in body or "> 10000" in body or "max(1" in body

    def test_11_no_order_send_in_monitor_loop(self):
        """_run_monitor_loop must NOT call mt5.order_send."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        idx = src.find("def _run_monitor_loop")
        end_idx = src.find("\ndef ", idx + 1)
        body = src[idx:end_idx if end_idx > 0 else len(src)]
        assert "mt5.order_send" not in body

    def test_12_no_martingale_in_monitor_loop(self):
        """Monitor loop must NOT contain martingale/grid/averaging logic."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        idx = src.find("def _run_monitor_loop")
        end_idx = src.find("\ndef ", idx + 1)
        body = src[idx:end_idx if end_idx > 0 else len(src)].lower()
        for term in ["martingale", "grid_trade", "averaging_down", "double_lot", "add_position"]:
            assert term not in body, f"Forbidden term '{term}' in monitor loop"

    def test_13_no_position_modification_in_monitor_loop(self):
        """Monitor loop must NOT call order_modify or positions_modify
        (it only builds previews)."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        idx = src.find("def _run_monitor_loop")
        end_idx = src.find("\ndef ", idx + 1)
        body = _strip(src[idx:end_idx if end_idx > 0 else len(src)])
        assert not re.search(r"\bmt5\.(order_modify|positions_modify)\s*\(", body)

    def test_14_no_mojibake(self):
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        assert "\u2014" not in src
        assert "\u2013" not in src

    def test_15_orchestrator_import_in_loop(self):
        """Monitor loop must use ManagedTradeOrchestrator for evaluation."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        idx = src.find("def _run_monitor_loop")
        end_idx = src.find("\ndef ", idx + 1)
        body = src[idx:end_idx if end_idx > 0 else len(src)]
        assert "ManagedTradeOrchestrator" in body
        assert "monitor_position" in body

    def test_16_monitor_loop_returns_dict_with_required_fields(self):
        """_run_monitor_loop must return a dict with all required fields."""
        import scripts.operator.run_managed_demo_micro_trade as m
        import titan.mt5_stub as stub
        from datetime import datetime, timezone

        # Reset state and inject a TITAN position
        stub._reset_state()
        stub.initialize()  # Required so positions_get returns data
        position = stub._Position(
            ticket=77777, magic=202619, comment="TITAN_DEMO_MICRO",
            price_open=2000.0, price_current=2003.0, sl=1990.0, tp=2010.0,
        )
        stub._POSITIONS.append(position)

        detected = {
            "detected_position_ticket": 77777,
            "detected_position_identifier": 77777,
            "detected_position_direction": "BUY",
            "detected_position_entry_price": 2000.0,
            "detected_position_sl": 1990.0,
            "detected_position_tp": 2010.0,
            "detected_position_current_price": 2003.0,
            "detection_method": "positions_get_magic_comment",
            "position_open_verified": True,
            "history_verified": False,
            "pending_history": True,
            "resolved_history_position_id": None,
            "history_order_ticket": None,
            "history_deal_ticket": None,
            "warnings": [],
        }

        class FakeArgs:
            duration_minutes = 0  # min iterations
            interval_seconds = 0  # no sleep

        try:
            result = m._run_monitor_loop(
                mt5=stub, detected_position=detected,
                args=FakeArgs(), ok_checks=[],
            )
        finally:
            stub._reset_state()

        required_fields = [
            "verdict", "monitor_iterations", "monitor_duration_seconds",
            "monitor_stop_reason", "final_position_status",
            "final_position_source", "final_positions_get_count",
            "final_history_match_found", "close_deal_ticket",
            "close_comment", "realized_pl", "monitor_events",
        ]
        for f in required_fields:
            assert f in result, f"Missing field: {f}"

    def test_17_monitor_loop_open_position_timeout(self):
        """If position stays open until max_iterations, verdict must be
        STARTED with final_position_status=OPEN."""
        import scripts.operator.run_managed_demo_micro_trade as m
        import titan.mt5_stub as stub

        stub._reset_state()
        stub.initialize()  # Required so positions_get returns data
        position = stub._Position(
            ticket=66666, magic=202619, comment="TITAN_DEMO_MICRO",
            price_open=2000.0, price_current=2001.0, sl=1990.0, tp=2010.0,
        )
        stub._POSITIONS.append(position)

        detected = {
            "detected_position_ticket": 66666,
            "detected_position_identifier": 66666,
            "detected_position_direction": "BUY",
            "detected_position_entry_price": 2000.0,
            "detected_position_sl": 1990.0,
            "detected_position_tp": 2010.0,
            "detected_position_current_price": 2001.0,
            "detection_method": "positions_get_magic_comment",
            "position_open_verified": True,
            "history_verified": False,
            "pending_history": True,
            "resolved_history_position_id": None,
            "history_order_ticket": None,
            "history_deal_ticket": None,
            "warnings": [],
        }

        class FakeArgs:
            duration_minutes = 0
            interval_seconds = 0

        try:
            result = m._run_monitor_loop(
                mt5=stub, detected_position=detected,
                args=FakeArgs(), ok_checks=[],
            )
        finally:
            stub._reset_state()

        # With duration_minutes=0 and interval_seconds=0, max_iterations=1
        # Position still open at end of single iteration => OPEN, TIMEOUT_REACHED
        assert result["final_position_status"] == "OPEN", \
            f"Expected OPEN, got {result['final_position_status']} (stop={result['monitor_stop_reason']})"
        assert result["monitor_stop_reason"] == "TIMEOUT_REACHED"
        assert result["verdict"] == "MANAGED_DEMO_MICRO_STARTED"
        assert result["monitor_iterations"] >= 1

    def test_18_monitor_loop_position_disappeared_without_history(self):
        """If position disappears and history has no match, final_position_status
        must be UNKNOWN and stop_reason POSITION_DISAPPEARED_WITHOUT_HISTORY."""
        import scripts.operator.run_managed_demo_micro_trade as m
        import titan.mt5_stub as stub

        stub._reset_state()
        stub.initialize()  # Required so history/positions calls succeed
        # No positions in the stub (position has disappeared)
        # No history deals either

        detected = {
            "detected_position_ticket": 55555,
            "detected_position_identifier": 55555,
            "detected_position_direction": "BUY",
            "detected_position_entry_price": 2000.0,
            "detected_position_sl": 1990.0,
            "detected_position_tp": 2010.0,
            "detected_position_current_price": 2000.0,
            "detection_method": "positions_get_magic_comment",
            "position_open_verified": True,
            "history_verified": False,
            "pending_history": True,
            "resolved_history_position_id": None,
            "history_order_ticket": None,
            "history_deal_ticket": None,
            "warnings": [],
        }

        class FakeArgs:
            duration_minutes = 0
            interval_seconds = 0

        try:
            result = m._run_monitor_loop(
                mt5=stub, detected_position=detected,
                args=FakeArgs(), ok_checks=[],
            )
        finally:
            stub._reset_state()

        assert result["final_position_status"] == "UNKNOWN"
        assert result["monitor_stop_reason"] == "POSITION_DISAPPEARED_WITHOUT_HISTORY"
        assert result["verdict"] == "MANAGED_DEMO_MICRO_COMPLETED_WITH_WARNINGS"
        # Must NOT be STARTED
        assert result["verdict"] != "MANAGED_DEMO_MICRO_STARTED"

    def test_19_monitor_loop_position_closed_via_history(self):
        """If position disappears but history has matching deal,
        final_position_status must be CLOSED."""
        import scripts.operator.run_managed_demo_micro_trade as m
        import titan.mt5_stub as stub

        stub._reset_state()
        stub.initialize()  # Required so history_deals_get returns data
        # Add a history deal matching position 55555
        from datetime import datetime, timezone
        now_ts = int(datetime.now(timezone.utc).timestamp())
        close_deal = stub._HistoryDeal(
            ticket=50001, order=60001, position_id=55555,
            magic=202619, comment="[sl 1990.0]", symbol="XAUUSD",
            type_=1, entry=1, price=1990.0, profit=-3.0, volume=0.01,
            time=now_ts,
        )
        stub._HISTORY_DEALS.append(close_deal)

        detected = {
            "detected_position_ticket": 55555,
            "detected_position_identifier": 55555,
            "detected_position_direction": "BUY",
            "detected_position_entry_price": 2000.0,
            "detected_position_sl": 1990.0,
            "detected_position_tp": 2010.0,
            "detected_position_current_price": 1990.0,
            "detection_method": "positions_get_magic_comment",
            "position_open_verified": True,
            "history_verified": False,
            "pending_history": True,
            "resolved_history_position_id": None,
            "history_order_ticket": None,
            "history_deal_ticket": None,
            "warnings": [],
        }

        class FakeArgs:
            duration_minutes = 0
            interval_seconds = 0

        try:
            result = m._run_monitor_loop(
                mt5=stub, detected_position=detected,
                args=FakeArgs(), ok_checks=[],
            )
        finally:
            stub._reset_state()

        assert result["final_position_status"] == "CLOSED", \
            f"Expected CLOSED, got {result['final_position_status']} (stop={result['monitor_stop_reason']})"
        assert result["monitor_stop_reason"] == "POSITION_CLOSED"
        assert result["verdict"] == "MANAGED_DEMO_MICRO_COMPLETED"
        assert result["close_deal_ticket"] == 50001
        assert result["realized_pl"] == -3.0
        assert result["final_history_match_found"] is True
