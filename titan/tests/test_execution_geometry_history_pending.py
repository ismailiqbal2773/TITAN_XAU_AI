"""TITAN XAU AI - Sprint 9.9.3.45.8.15 Forensics HISTORY_PENDING Tests

Verifies the new DEMO_MICRO_EVIDENCE_HISTORY_PENDING verdict added to
collect_demo_micro_trade_forensics.py:

  - When receipt has order_send_result_deal or deal_ticket non-zero AND
    the deal is NOT found in MT5 history_deals_get, the verdict must be
    DEMO_MICRO_EVIDENCE_HISTORY_PENDING (not DEMO_MICRO_EVIDENCE_INCOMPLETE).
  - The findings must include 'history_pending_reason' explaining possible
    causes (history not refreshed, timestamp mismatch, MT5 history delay).
  - When deal_ticket is zero/missing and trade not found, the verdict
    must remain DEMO_MICRO_EVIDENCE_INCOMPLETE (legacy behavior).
  - When deal is found in history, verdict must NOT be HISTORY_PENDING.
  - The forensics code must never call mt5.order_send.
"""
from __future__ import annotations
import ast, json, re, sys
from datetime import datetime, timezone
from pathlib import Path
import pytest
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


def _strip(src: str) -> str:
    src = re.sub(r'"""[\s\S]*?"""', '""', src)
    src = re.sub(r"'''[\s\S]*?'''", "''", src)
    src = re.sub(r'"(?:[^"\\]|\\.)*"', '""', src)
    src = re.sub(r"'(?:[^'\\]|\\.)*'", "''", src)
    return src


FORENSICS_PATH = REPO_ROOT / "scripts" / "operator" / "collect_demo_micro_trade_forensics.py"


def _install_mt5_stub(monkeypatch):
    """Install titan.mt5_stub as the MetaTrader5 module for the test.

    The titan/MetaTrader5.py stub lacks history_deals_get, so we replace
    it with the richer titan/mt5_stub.py module which supports the
    history_deals_get / history_orders_get / positions_get(symbol=...)
    interface needed by the forensics code.
    """
    from titan import mt5_stub
    monkeypatch.setitem(sys.modules, "MetaTrader5", mt5_stub)
    mt5_stub._reset_state()
    return mt5_stub


def _build_receipt(*, deal_ticket=0, order_send_result_deal=None,
                   detected_position_ticket=57344905358) -> dict:
    """Build a minimal receipt for the forensics test."""
    return {
        "success": True,
        "side": "BUY",
        "execution_mode": "execute_and_monitor",
        "detected_position_ticket": detected_position_ticket,
        "detected_position_identifier": detected_position_ticket,
        "order_ticket": detected_position_ticket,
        "deal_ticket": deal_ticket,
        "order_send_result_deal": (order_send_result_deal
                                    if order_send_result_deal is not None
                                    else deal_ticket),
        "position_id": None,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }


class TestHistoryPendingVerdict:
    def test_01_history_pending_when_deal_ticket_nonzero_and_not_in_history(
        self, tmp_path, monkeypatch,
    ):
        """Receipt with non-zero deal_ticket but deal NOT in history must
        return DEMO_MICRO_EVIDENCE_HISTORY_PENDING."""
        stub = _install_mt5_stub(monkeypatch)
        # No history deals populated - deal ticket 57001412567 not in history
        import scripts.operator.collect_demo_micro_trade_forensics as fc

        receipt_path = tmp_path / "receipt.json"
        receipt_path.write_text(json.dumps(_build_receipt(
            deal_ticket=57001412567,
        )))
        monkeypatch.setattr(fc, "RECEIPT_PATH", receipt_path)

        result = fc.collect_forensics()
        assert result["verdict"] == "DEMO_MICRO_EVIDENCE_HISTORY_PENDING"
        findings = result["findings"]
        assert findings["root_cause"] == "RECEIPT_DEAL_PENDING_HISTORY_PROPAGATION"
        assert "history_pending_reason" in findings
        reason = findings["history_pending_reason"]
        # Reason must mention at least one of the documented possible causes
        assert ("history" in reason.lower()
                and ("refresh" in reason.lower()
                     or "timestamp" in reason.lower()
                     or "delay" in reason.lower()))
        assert findings["receipt_deal_ticket_for_history"] == 57001412567
        assert findings["receipt_deal_in_history"] is False

    def test_02_history_pending_uses_order_send_result_deal(self, tmp_path, monkeypatch):
        """When receipt has order_send_result_deal (no deal_ticket), the
        HISTORY_PENDING logic must still trigger."""
        stub = _install_mt5_stub(monkeypatch)
        import scripts.operator.collect_demo_micro_trade_forensics as fc

        receipt = _build_receipt(deal_ticket=0, order_send_result_deal=9988776655)
        receipt_path = tmp_path / "receipt.json"
        receipt_path.write_text(json.dumps(receipt))
        monkeypatch.setattr(fc, "RECEIPT_PATH", receipt_path)

        result = fc.collect_forensics()
        assert result["verdict"] == "DEMO_MICRO_EVIDENCE_HISTORY_PENDING"
        findings = result["findings"]
        assert findings["receipt_deal_ticket_for_history"] == 9988776655
        assert "history_pending_reason" in findings

    def test_03_incomplete_when_deal_ticket_zero_and_not_in_history(
        self, tmp_path, monkeypatch,
    ):
        """When deal_ticket is zero/missing and trade not found, verdict
        must remain DEMO_MICRO_EVIDENCE_INCOMPLETE (legacy behavior)."""
        _install_mt5_stub(monkeypatch)
        import scripts.operator.collect_demo_micro_trade_forensics as fc

        receipt = _build_receipt(deal_ticket=0, order_send_result_deal=0)
        receipt_path = tmp_path / "receipt.json"
        receipt_path.write_text(json.dumps(receipt))
        monkeypatch.setattr(fc, "RECEIPT_PATH", receipt_path)

        result = fc.collect_forensics()
        assert result["verdict"] == "DEMO_MICRO_EVIDENCE_INCOMPLETE"
        findings = result["findings"]
        assert findings["root_cause"] == "RECEIPT_TRADE_NOT_FOUND_IN_HISTORY_OR_OPEN_POSITIONS"
        # history_pending_reason must NOT be set on the INCOMPLETE path
        assert "history_pending_reason" not in findings

    def test_04_history_pending_not_returned_when_deal_in_history(
        self, tmp_path, monkeypatch,
    ):
        """When deal IS found in history, verdict must NOT be HISTORY_PENDING."""
        stub = _install_mt5_stub(monkeypatch)
        import scripts.operator.collect_demo_micro_trade_forensics as fc

        now_ts = int(datetime.now(timezone.utc).timestamp())
        deal = stub._HistoryDeal(
            ticket=57001412567, order=57344905358,
            position_id=57344905358, magic=202619,
            comment="TITAN_DEMO_MICRO", symbol="XAUUSD",
            type_=0, entry=0, price=2000.0, profit=0.0,
            volume=0.01, time=now_ts,
        )
        stub._HISTORY_DEALS.append(deal)
        order = stub._HistoryOrder(
            ticket=57344905358, position_id=57344905358,
            magic=202619, comment="TITAN_DEMO_MICRO", symbol="XAUUSD",
            type_=0, sl=1990.0, tp=2010.0, price=2000.0,
            time_setup=now_ts, time_done=now_ts,
        )
        stub._HISTORY_ORDERS.append(order)
        close_deal = stub._HistoryDeal(
            ticket=57001412568, order=57344905359,
            position_id=57344905358, magic=202619,
            comment="[tp]", symbol="XAUUSD",
            type_=1, entry=1, price=2010.0, profit=10.0,
            volume=0.01, time=now_ts,
        )
        stub._HISTORY_DEALS.append(close_deal)

        receipt_path = tmp_path / "receipt.json"
        receipt_path.write_text(json.dumps(_build_receipt(
            deal_ticket=57001412567,
        )))
        monkeypatch.setattr(fc, "RECEIPT_PATH", receipt_path)

        result = fc.collect_forensics()
        assert result["verdict"] != "DEMO_MICRO_EVIDENCE_HISTORY_PENDING", \
            f"deal found in history but verdict is HISTORY_PENDING: {result}"
        # Should be PASS or COMPLETE since deal is found
        assert result["verdict"] in (
            "DEMO_MICRO_EVIDENCE_PASS",
            "DEMO_MICRO_FORENSICS_COMPLETE_WITH_WARNINGS",
        ), f"unexpected verdict {result['verdict']}"

    def test_05_history_pending_does_not_modify_existing_pass_logic(self):
        """DEMO_MICRO_EVIDENCE_PASS verdict code must be unchanged - the
        new HISTORY_PENDING branch must be in the receipt-not-found path
        only, not in the matched-deal path."""
        src = FORENSICS_PATH.read_text(encoding="utf-8")
        # PASS verdict must still be present
        assert '"DEMO_MICRO_EVIDENCE_PASS"' in src
        # ENTRY_CONFIRMED_CLOSE_DEAL_MISSING verdict must still be present
        assert "DEMO_MICRO_EVIDENCE_ENTRY_CONFIRMED_CLOSE_DEAL_MISSING" in src
        # New HISTORY_PENDING verdict must be present
        assert "DEMO_MICRO_EVIDENCE_HISTORY_PENDING" in src

    def test_06_history_pending_branch_precedes_incomplete_branch(self):
        """The HISTORY_PENDING branch must be checked BEFORE the
        DEMO_MICRO_EVIDENCE_INCOMPLETE return statement."""
        src = FORENSICS_PATH.read_text(encoding="utf-8")
        idx_history_pending = src.find("DEMO_MICRO_EVIDENCE_HISTORY_PENDING")
        # The INCOMPLETE return after the HISTORY_PENDING block:
        # find the second occurrence of "DEMO_MICRO_EVIDENCE_INCOMPLETE"
        # (the first is in the docstring; we need the one in the return
        # statement after the HISTORY_PENDING block)
        idx_incomplete_return = src.find(
            '"verdict": "DEMO_MICRO_EVIDENCE_INCOMPLETE"',
            idx_history_pending,
        )
        assert idx_history_pending > 0
        assert idx_incomplete_return > idx_history_pending, \
            "HISTORY_PENDING branch must precede INCOMPLETE return"

    def test_07_no_order_send_in_forensics_source(self):
        """Forensics source must not call mt5.order_send."""
        src = FORENSICS_PATH.read_text(encoding="utf-8")
        code = _strip(src)
        assert "mt5.order_send" not in code, \
            "forensics source must not call mt5.order_send"

    def test_08_no_martingale_in_forensics_source(self):
        """Forensics source must not contain martingale / grid / averaging /
        loss-based lot multiplier logic."""
        src = FORENSICS_PATH.read_text(encoding="utf-8")
        code = _strip(src).lower()
        for term in ["martingale", "grid_trade", "averaging_down",
                     "double_lot", "loss_based_lot_multiplier"]:
            assert term not in code, f"Forbidden term '{term}' in forensics source"

    def test_09_history_pending_includes_fallback_candidates_as_diagnostics(
        self, tmp_path, monkeypatch,
    ):
        """The HISTORY_PENDING branch must still include fallback_candidates
        as diagnostics only (fallback_used must remain False)."""
        _install_mt5_stub(monkeypatch)
        import scripts.operator.collect_demo_micro_trade_forensics as fc

        receipt_path = tmp_path / "receipt.json"
        receipt_path.write_text(json.dumps(_build_receipt(
            deal_ticket=57001412567,
        )))
        monkeypatch.setattr(fc, "RECEIPT_PATH", receipt_path)

        result = fc.collect_forensics()
        findings = result["findings"]
        assert findings.get("fallback_used") is False
        assert "fallback_candidates" in findings
        # Safety fields
        assert result["safety"]["order_send_called"] is False
        assert result["safety"]["position_modified"] is False

    def test_10_no_order_send_in_test_file(self):
        """The test file must not CALL mt5.order_send (AST-level check)."""
        src_path = REPO_ROOT / "titan" / "tests" / "test_execution_geometry_history_pending.py"
        tree = ast.parse(src_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if (isinstance(func, ast.Attribute)
                        and func.attr == "order_send"
                        and isinstance(func.value, ast.Name)
                        and func.value.id == "mt5"):
                    pytest.fail("test file must not call mt5.order_send")
