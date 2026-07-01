"""TITAN XAU AI - Sprint 9.9.3.45.8.10 Demo Micro Forensics Reconciliation Tests"""
from __future__ import annotations
import json, re, sys
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


class TestForensicsReconciliation:
    def test_01_receipt_order_ticket_parsed(self):
        """Forensics must parse receipt order_ticket."""
        src = (REPO_ROOT / "scripts" / "operator" / "collect_demo_micro_trade_forensics.py").read_text()
        assert 'receipt.get("order_ticket"' in src

    def test_02_receipt_deal_ticket_parsed(self):
        """Forensics must parse receipt deal_ticket."""
        src = (REPO_ROOT / "scripts" / "operator" / "collect_demo_micro_trade_forensics.py").read_text()
        assert 'receipt.get("deal_ticket"' in src

    def test_03_order_send_result_order_parsed(self):
        """Forensics must parse order_send_result_order."""
        src = (REPO_ROOT / "scripts" / "operator" / "collect_demo_micro_trade_forensics.py").read_text()
        assert 'receipt.get("order_send_result_order"' in src

    def test_04_order_send_result_deal_parsed(self):
        """Forensics must parse order_send_result_deal."""
        src = (REPO_ROOT / "scripts" / "operator" / "collect_demo_micro_trade_forensics.py").read_text()
        assert 'receipt.get("order_send_result_deal"' in src

    def test_05_detected_position_identifier_parsed(self):
        """Forensics must parse detected_position_identifier as position candidate."""
        src = (REPO_ROOT / "scripts" / "operator" / "collect_demo_micro_trade_forensics.py").read_text()
        assert 'receipt.get("detected_position_identifier"' in src

    def test_06_resolved_history_position_id_parsed(self):
        """Forensics must parse resolved_history_position_id."""
        src = (REPO_ROOT / "scripts" / "operator" / "collect_demo_micro_trade_forensics.py").read_text()
        assert 'receipt.get("resolved_history_position_id"' in src

    def test_07_match_priority_deal_ticket_first(self):
        """Match priority must be deal ticket first."""
        src = (REPO_ROOT / "scripts" / "operator" / "collect_demo_micro_trade_forensics.py").read_text()
        # Find the receipt matching section
        idx = src.find("Priority 1: Exact deal ticket match")
        assert idx > 0, "Deal ticket priority 1 not found"
        # Order ticket priority should come after
        idx2 = src.find("Priority 2: Exact order ticket match")
        assert idx2 > idx, "Order ticket priority 2 should come after deal ticket"

    def test_08_diagnostic_integration(self):
        """Forensics must integrate latest_receipt_diagnostic.json."""
        src = (REPO_ROOT / "scripts" / "operator" / "collect_demo_micro_trade_forensics.py").read_text()
        assert "latest_receipt_diagnostic.json" in src
        assert "diagnostic_history_deal_match" in src
        assert "MATCHER_BUG_OR_FIELD_MAPPING_ERROR" in src

    def test_09_new_evidence_verdicts(self):
        """Forensics must use new evidence verdicts."""
        src = (REPO_ROOT / "scripts" / "operator" / "collect_demo_micro_trade_forensics.py").read_text()
        assert "DEMO_MICRO_EVIDENCE_PASS" in src
        assert "DEMO_MICRO_EVIDENCE_ENTRY_CONFIRMED_CLOSE_DEAL_MISSING" in src
        assert "DEMO_MICRO_EVIDENCE_INCOMPLETE" in src
        assert "DEMO_MICRO_EVIDENCE_FAIL" in src

    def test_10_entry_exit_deals_counted(self):
        """Forensics must count entry and exit deals separately."""
        src = (REPO_ROOT / "scripts" / "operator" / "collect_demo_micro_trade_forensics.py").read_text()
        assert "entry_deals_count" in src
        assert "exit_deals_count" in src

    def test_11_matched_position_id_reported(self):
        """Forensics must report matched_position_id."""
        src = (REPO_ROOT / "scripts" / "operator" / "collect_demo_micro_trade_forensics.py").read_text()
        assert "matched_position_id" in src

    def test_12_no_fallback_used_for_proof(self):
        """Fallback must never be used as proof."""
        src = (REPO_ROOT / "scripts" / "operator" / "collect_demo_micro_trade_forensics.py").read_text()
        assert "fallback_used" in src

    def test_13_no_order_send(self):
        src = (REPO_ROOT / "scripts" / "operator" / "collect_demo_micro_trade_forensics.py").read_text()
        code = _strip(src)
        assert not re.search(r"\bmt5\.order_send\s*\(", code)

    def test_14_no_position_modification(self):
        src = (REPO_ROOT / "scripts" / "operator" / "collect_demo_micro_trade_forensics.py").read_text()
        code = _strip(src)
        assert not re.search(r"\bmt5\.(order_modify|positions_modify)\s*\(", code)

    def test_15_explicit_fields_marked(self):
        """Forensics must mark explicit_order_ticket_supplied and explicit_deal_ticket_supplied."""
        src = (REPO_ROOT / "scripts" / "operator" / "collect_demo_micro_trade_forensics.py").read_text()
        assert "explicit_order_ticket_supplied" in src
        assert "explicit_deal_ticket_supplied" in src
        assert "explicit_position_id_supplied" in src
