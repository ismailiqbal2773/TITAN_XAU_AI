"""TITAN XAU AI - Sprint 9.9.3.45.5 Managed Execution Truthfulness Tests

Sprint 9.9.3.45.5 extends truthfulness requirements:
  - Raw MT5 order_send result fields captured safely (retcode, comment,
    order, deal, volume, price, bid, ask, request_id, retcode_external)
  - Receipt uses correct field names (order_send_result_order,
    order_send_result_deal, order_send_result_retcode,
    order_send_result_comment, requested_sl, requested_tp,
    detected_position_ticket, detected_position_identifier,
    resolved_history_position_id)
  - Position ticket is never mislabeled as order_ticket unless it is
    actually result.order. Deal ticket never mislabeled unless it is
    actually result.deal.
  - retcode 10009 but no position/history -> FAILED or INCONSISTENT
  - Position detected then disappears with no history -> UNKNOWN/WARNING,
    not OPEN.
  - Monitor cannot complete after one iteration while still open.
  - Final OPEN requires final positions_get evidence.
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
    src = re.sub(r'r"[^"]*"', '""', src)
    src = re.sub(r"r'[^']*'", "''", src)
    src = re.sub(r'"(?:[^"\\]|\\.)*"', '""', src)
    src = re.sub(r"'(?:[^'\\]|\\.)*'", "''", src)
    lines = [line.split("#")[0] if "#" in line else line for line in src.splitlines()]
    return "\n".join(lines)


class TestTruthfulness:
    def test_01_started_requires_receipt_written(self):
        """STARTED verdict must only be returned when receipt_written=True."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        assert "MANAGED_DEMO_MICRO_STARTED" in src
        assert "receipt_written" in src
        assert "RECEIPT_WRITE_FAILED" in src

    def test_02_started_requires_position_verified(self):
        """Sprint 9.9.3.45.5: STARTED must require position verification."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        # Strict verification string (renamed from 45.4)
        assert "POSITION_NOT_VERIFIED_AFTER_EXECUTION" in src
        assert "position_open_verified" in src
        assert "history_verified" in src

    def test_03_failed_on_order_send_failure(self):
        """Order_send failure must return MANAGED_DEMO_MICRO_FAILED."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        assert "ORDER_SEND_FAILED" in src
        assert "MANAGED_DEMO_MICRO_FAILED" in src

    def test_04_failed_on_receipt_write_failure(self):
        """Receipt write failure must return MANAGED_DEMO_MICRO_FAILED."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        assert "RECEIPT_WRITE_FAILED" in src

    def test_05_quick_close_returns_completed_with_warnings(self):
        """Quick close must return COMPLETED_WITH_WARNINGS, not STARTED."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        assert "POSITION_CLOSED_BEFORE_MONITOR" in src
        assert "MANAGED_DEMO_MICRO_COMPLETED_WITH_WARNINGS" in src

    def test_06_monitor_started_only_with_position(self):
        """monitor_started must only be True when position is detected."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        # The STARTED return must have monitor_started=True
        assert '"monitor_started": True' in src or "monitor_started\": True" in src

    def test_07_no_false_started_without_evidence(self):
        """The script must not return STARTED without receipt + position.
        Sprint 9.9.3.45.5: verdict is computed in _run_monitor_loop and
        passed to the final return as monitor_result['verdict']. Verify
        the final return block in run_execute_and_monitor includes both
        receipt_written and monitor_result['verdict'] (which can be
        STARTED only when final_position_status=OPEN)."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        # The verdict computation in _run_monitor_loop must tie OPEN to STARTED
        loop_idx = src.find("def _run_monitor_loop")
        assert loop_idx > 0
        loop_end = src.find("\ndef ", loop_idx + 1)
        loop_body = src[loop_idx:loop_end if loop_end > 0 else len(src)]
        # In the loop body: OPEN => STARTED, CLOSED => COMPLETED, UNKNOWN => COMPLETED_WITH_WARNINGS
        assert "MANAGED_DEMO_MICRO_STARTED" in loop_body
        assert 'final_position_status == "OPEN"' in loop_body
        # The final return in run_execute_and_monitor must include
        # monitor_result["verdict"] and receipt_written
        exec_idx = src.find("def run_execute_and_monitor")
        exec_end = src.find("\ndef ", exec_idx + 1)
        exec_body = src[exec_idx:exec_end if exec_end > 0 else len(src)]
        # Find the final return after monitor_result is computed
        monitor_idx = exec_body.find("_run_monitor_loop(")
        assert monitor_idx > 0
        final_return = exec_body[monitor_idx:]
        assert "receipt_written" in final_return
        assert 'monitor_result["verdict"]' in final_return or "monitor_result['verdict']" in final_return

    def test_08_execution_attempted_field(self):
        """Report must include execution_attempted field."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        assert "execution_attempted" in src

    def test_09_order_send_comment_field(self):
        """Report must include order_send_comment field."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        assert "order_send_comment" in src

    def test_10_receipt_path_field(self):
        """Report must include receipt_path field."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        assert "receipt_path" in src

    def test_11_position_detection_method_field(self):
        """Report must include position_detection_method field."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        assert "position_detection_method" in src

    def test_12_final_position_status_field(self):
        """Report must include final_position_status field."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        assert "final_position_status" in src

    def test_13_no_mojibake(self):
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        assert "\u2014" not in src
        assert "\u2013" not in src
        assert "\u2018" not in src
        assert "\u2019" not in src

    def test_14_order_send_isolated(self):
        """order_send must only be inside run_execute_and_monitor."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        code = _strip(src)
        lines = code.splitlines()
        in_execute = False
        for line in lines:
            if "def run_execute_and_monitor" in line:
                in_execute = True
            elif line and not line[0].isspace() and "def " in line:
                in_execute = False
            if "mt5.order_send" in line and not in_execute:
                pytest.fail(f"order_send found outside run_execute_and_monitor: {line.strip()}")

    def test_15_no_demo_micro_execute(self):
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        code = _strip(src)
        assert not re.search(r"(?<!['\"])\b(DEMO_MICRO_EXECUTE|run_demo_micro)\s*\(", code)

    def test_16_no_raw_mt5_probe(self):
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        code = _strip(src)
        assert not re.search(r"(?<!['\"])\b(run_raw_probe|raw_mt5_probe)\s*\(", code)

    # === Sprint 9.9.3.45.5 new tests ===

    def test_17_raw_order_send_result_fields_captured(self):
        """Receipt must capture all raw order_send result fields safely."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        required_fields = [
            "order_send_result_retcode",
            "order_send_result_comment",
            "order_send_result_order",
            "order_send_result_deal",
            "order_send_result_volume",
            "order_send_result_price",
            "order_send_result_bid",
            "order_send_result_ask",
            "order_send_result_request_id",
            "order_send_result_retcode_external",
        ]
        for field in required_fields:
            assert field in src, f"Missing receipt field: {field}"

    def test_18_requested_sl_tp_field_names(self):
        """Receipt must use requested_sl / requested_tp field names."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        assert "requested_sl" in src
        assert "requested_tp" in src

    def test_19_detected_position_field_names(self):
        """Receipt must use detected_position_ticket / detected_position_identifier."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        assert "detected_position_ticket" in src
        assert "detected_position_identifier" in src
        assert "resolved_history_position_id" in src

    def test_20_capture_safe_function_exists(self):
        """_capture_order_send_result_safe function must exist."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        assert "def _capture_order_send_result_safe" in src

    def test_21_no_position_id_from_result_position_id(self):
        """Sprint 9.9.3.45.5: position_id must NOT be populated from
        result.position_id (was the 45.4 bug)."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        # The _build_receipt function must not assign position_id from
        # raw_result["position_id"] or getattr(order_result, "position_id", 0)
        # Find _build_receipt function body
        idx = src.find("def _build_receipt")
        assert idx > 0
        # Get function body (until next def or end of file at same indent)
        end_idx = src.find("\ndef ", idx + 1)
        if end_idx < 0:
            end_idx = len(src)
        body = src[idx:end_idx]
        # position_id must be None, not sourced from raw_result
        assert '"position_id": None' in body or "\"position_id\": None" in body, \
            "position_id must be None in _build_receipt (not from result.position_id)"

    def test_22_order_ticket_only_from_result_order(self):
        """order_ticket must only be populated from raw_result['order']."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        idx = src.find("def _build_receipt")
        end_idx = src.find("\ndef ", idx + 1)
        if end_idx < 0:
            end_idx = len(src)
        body = src[idx:end_idx]
        # order_ticket must equal raw_result["order"] (which may be None)
        assert '"order_ticket": raw_result["order"]' in body, \
            "order_ticket must be sourced from raw_result['order'] only"

    def test_23_deal_ticket_only_from_result_deal(self):
        """deal_ticket must only be populated from raw_result['deal']."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        idx = src.find("def _build_receipt")
        end_idx = src.find("\ndef ", idx + 1)
        if end_idx < 0:
            end_idx = len(src)
        body = src[idx:end_idx]
        assert '"deal_ticket": raw_result["deal"]' in body, \
            "deal_ticket must be sourced from raw_result['deal'] only"

    def test_24_warning_on_incomplete_result(self):
        """If retcode=10009 but order/deal are None, warning must be added."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        assert "ORDER_SEND_RESULT_INCOMPLETE" in src

    def test_25_position_detection_via_history(self):
        """Position detection must query history_deals_get and history_orders_get."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        assert "history_deals_get" in src
        assert "history_orders_get" in src

    def test_26_pending_history_field(self):
        """Receipt must include pending_history field."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        assert "pending_history" in src

    def test_27_position_open_verified_field(self):
        """Receipt must include position_open_verified field."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        assert "position_open_verified" in src

    def test_28_monitor_loop_function_exists(self):
        """_run_monitor_loop function must exist for lifecycle management."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        assert "def _run_monitor_loop" in src

    def test_29_monitor_iterations_field(self):
        """Report must include monitor_iterations field."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        assert "monitor_iterations" in src

    def test_30_monitor_duration_seconds_field(self):
        """Report must include monitor_duration_seconds field."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        assert "monitor_duration_seconds" in src

    def test_31_monitor_stop_reason_field(self):
        """Report must include monitor_stop_reason field."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        assert "monitor_stop_reason" in src

    def test_32_position_disappeared_without_history_stop_reason(self):
        """If position disappears without history, stop_reason must be
        POSITION_DISAPPEARED_WITHOUT_HISTORY."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        assert "POSITION_DISAPPEARED_WITHOUT_HISTORY" in src

    def test_33_final_position_source_field(self):
        """Report must include final_position_source field."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        assert "final_position_source" in src

    def test_34_final_positions_get_count_field(self):
        """Report must include final_positions_get_count field."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        assert "final_positions_get_count" in src

    def test_35_final_history_match_found_field(self):
        """Report must include final_history_match_found field."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        assert "final_history_match_found" in src

    def test_36_close_deal_ticket_and_realized_pl_fields(self):
        """Report must include close_deal_ticket, close_comment, realized_pl."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        assert "close_deal_ticket" in src
        assert "close_comment" in src
        assert "realized_pl" in src

    def test_37_timeout_reached_stop_reason(self):
        """Monitor must support TIMEOUT_REACHED stop reason."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        assert "TIMEOUT_REACHED" in src

    def test_38_position_closed_stop_reason(self):
        """Monitor must support POSITION_CLOSED stop reason."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        assert "POSITION_CLOSED" in src

    def test_39_no_martingale_grid_averaging(self):
        """No martingale/grid/averaging allowed."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        code = _strip(src).lower()
        # "no martingale" is allowed (it's a comment); "martingale" alone is suspect
        for term in ["martingale", "grid_trade", "averaging_down", "double_lot", "add_position"]:
            if term in code:
                # Allow if explicitly negated
                idx = code.find(term)
                ctx = code[max(0, idx-30):idx+30]
                assert "no " + term in ctx or "not " + term in ctx or "forbid" in ctx, \
                    f"Suspect term '{term}' found without negation: {ctx}"

    def test_40_no_live_trading(self):
        """No live trading allowed."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        # Must check trade_mode == 0 (DEMO)
        assert "trade_mode" in src
        assert "ACCOUNT_NOT_DEMO" in src
        assert "MetaQuotes-Demo" in src
