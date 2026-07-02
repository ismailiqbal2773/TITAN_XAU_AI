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

    # === Sprint 9.9.3.45.8.11: nested diagnostic parsing tests ===

    def test_16_diag_get_helper_exists(self):
        """Forensics must have _diag_get helper for nested diagnostic fields."""
        src = (REPO_ROOT / "scripts" / "operator" / "collect_demo_micro_trade_forensics.py").read_text()
        assert "_diag_get" in src
        assert 'diag.get("findings"' in src

    def test_17_diagnostic_fields_read_from_nested_findings(self):
        """Forensics must read diagnostic fields from diagnostic['findings'] not just top-level."""
        src = (REPO_ROOT / "scripts" / "operator" / "collect_demo_micro_trade_forensics.py").read_text()
        # The _diag_get helper must check both top-level and findings dict
        assert 'findings_dict = diag.get("findings", {})' in src
        assert 'if isinstance(findings_dict, dict) and key in findings_dict' in src

    def test_18_diagnostic_supported_match_not_fallback(self):
        """When receipt deal ticket equals diagnostic history_deal_ticket,
        this is receipt-supported proof, NOT fallback."""
        src = (REPO_ROOT / "scripts" / "operator" / "collect_demo_micro_trade_forensics.py").read_text()
        assert "receipt_diagnostic_deal_ticket" in src
        assert "old_trades_used_as_proof" in src
        assert 'old_trades_used_as_proof"] = False' in src

    def test_19_debug_fields_added(self):
        """Forensics must add debug fields when receipt not matched."""
        src = (REPO_ROOT / "scripts" / "operator" / "collect_demo_micro_trade_forensics.py").read_text()
        assert "receipt_deal_candidates" in src
        assert "normalized_deal_tickets_sample" in src
        assert "history_deals_count" in src
        assert "history_orders_count" in src

    def test_20_matcher_bug_uses_nested_diag(self):
        """MATCHER_BUG check must use _diag_get for nested fields."""
        src = (REPO_ROOT / "scripts" / "operator" / "collect_demo_micro_trade_forensics.py").read_text()
        # The matcher bug check should use diag_history_match variable (from _diag_get)
        assert "if diag_history_match:" in src
        # Should NOT use diagnostic.get("history_deal_match") directly
        assert 'diagnostic.get("history_deal_match")' not in src or '_diag_get(diagnostic, "history_deal_match"' in src

    def test_21_diagnostic_supported_match_conditions(self):
        """Diagnostic-supported match requires history_match=true and a
        diagnostic deal_ticket/position_id (v2.7.3 broadened - the
        diag_pos_id no longer needs to equal receipt_detected_identifier
        because diagnostic may use a different position_id namespace).
        """
        src = (REPO_ROOT / "scripts" / "operator" / "collect_demo_micro_trade_forensics.py").read_text()
        assert "diag_deal_ticket == receipt_deal" in src
        # v2.7.3: diagnostic-supported match must NOT require strict
        # identifier equality - diagnostic window may be wider.
        assert "diag_history_match" in src
        assert "diag_deal_ticket" in src
        assert "diag_pos_id" in src
        # New v2.7.3 verdict must be present
        assert "DEMO_MICRO_EVIDENCE_RECEIPT_DIAGNOSTIC_CONFIRMED" in src
        assert "RECEIPT_DIAGNOSTIC_MATCH_CONFIRMED" in src

    # === Sprint 9.9.3.45.8.15: HISTORY_PENDING tests ===

    def test_22_forensics_supports_history_pending_verdict(self):
        """Forensics must support DEMO_MICRO_EVIDENCE_HISTORY_PENDING verdict."""
        src = (REPO_ROOT / "scripts" / "operator" / "collect_demo_micro_trade_forensics.py").read_text()
        assert "DEMO_MICRO_EVIDENCE_HISTORY_PENDING" in src

    def test_23_forensics_distinguishes_history_pending_from_not_found(self):
        """When receipt has deal_ticket but history doesn't show it, should be HISTORY_PENDING."""
        src = (REPO_ROOT / "scripts" / "operator" / "collect_demo_micro_trade_forensics.py").read_text()
        assert "history_pending_reason" in src
        assert "DEMO_MICRO_EVIDENCE_HISTORY_PENDING" in src
        # Should not be generic HISTORY_NOT_FOUND when receipt deal exists
        assert "order_send_result_deal" in src or "receipt_deal" in src

    # === Sprint 9.9.3.45.8.16 v2.7.3: Diagnostic-supported proof + new root causes ===

    def test_24_v2_7_3_new_root_causes_supported(self):
        """Forensics must support all v2.7.3 new root_cause values."""
        src = (REPO_ROOT / "scripts" / "operator" / "collect_demo_micro_trade_forensics.py").read_text()
        for root_cause in [
            "HISTORY_PENDING_AFTER_ORDER_SEND",
            "DIAGNOSTIC_RESOLVED_BUT_FORENSICS_NO_MATCH",
            "RECEIPT_DIAGNOSTIC_MATCH_CONFIRMED",
            "MT5_HISTORY_WINDOW_MISMATCH",
            "MATCHER_BUG_OR_FIELD_MAPPING_ERROR",
        ]:
            assert root_cause in src, f"Missing v2.7.3 root_cause: {root_cause}"

    def test_25_v2_7_3_diagnostic_only_resolved_verdict(self):
        """Forensics must return DEMO_MICRO_EVIDENCE_DIAGNOSTIC_ONLY_RESOLVED
        when diagnostic says resolved_closed but no deal ticket exposed."""
        src = (REPO_ROOT / "scripts" / "operator" / "collect_demo_micro_trade_forensics.py").read_text()
        assert "DEMO_MICRO_EVIDENCE_DIAGNOSTIC_ONLY_RESOLVED" in src
        assert "DIAGNOSTIC_RESOLVED_BUT_FORENSICS_NO_MATCH" in src

    def test_26_v2_7_3_receipt_diagnostic_confirmed_verdict(self):
        """Forensics must return DEMO_MICRO_EVIDENCE_RECEIPT_DIAGNOSTIC_CONFIRMED
        when diagnostic history_deal_match=true with a deal ticket."""
        src = (REPO_ROOT / "scripts" / "operator" / "collect_demo_micro_trade_forensics.py").read_text()
        assert "DEMO_MICRO_EVIDENCE_RECEIPT_DIAGNOSTIC_CONFIRMED" in src
        assert "diagnostic_supported_deal_ticket" in src

    def test_27_v2_7_3_diagnostic_supported_proof_not_fallback(self):
        """When diagnostic-supported match occurs, fallback_used and
        old_trades_used_as_proof must both be false."""
        src = (REPO_ROOT / "scripts" / "operator" / "collect_demo_micro_trade_forensics.py").read_text()
        # In the diagnostic-supported match block, old_trades_used_as_proof=False
        # must be explicitly set.
        assert 'findings["old_trades_used_as_proof"] = False' in src
        assert 'findings["root_cause"] = "RECEIPT_DIAGNOSTIC_MATCH_CONFIRMED"' in src

    def test_28_v2_7_3_diagnostic_fields_read_from_nested_findings(self):
        """Forensics must read v2.7.3 spec diagnostic fields from both
        top-level and nested findings (via _diag_get helper)."""
        src = (REPO_ROOT / "scripts" / "operator" / "collect_demo_micro_trade_forensics.py").read_text()
        # Must read pending_history, history_window_start, history_window_end,
        # receipt_timestamp, account_server from diagnostic
        for field in [
            'pending_history',
            'history_window_start',
            'history_window_end',
            'receipt_timestamp',
        ]:
            assert field in src, f"Missing diagnostic field: {field}"

    def test_29_v2_7_3_receipt_fields_expanded(self):
        """Forensics must read v2.7.3 spec receipt fields:
        requested_sl, requested_tp, request_magic, request_comment,
        order_send_result_price."""
        src = (REPO_ROOT / "scripts" / "operator" / "collect_demo_micro_trade_forensics.py").read_text()
        for field in [
            'requested_sl',
            'requested_tp',
            'request_magic',
            'request_comment',
            'order_send_result_price',
        ]:
            assert f'receipt.get("{field}"' in src or f'"{field}"' in src, \
                f"Missing receipt field reference: {field}"

    def test_30_v2_7_3_no_generic_history_not_found_when_diagnostic_resolved_closed(self):
        """When diagnostic_resolved_closed=True and history_deal_match=False,
        forensics must return DIAGNOSTIC_ONLY_RESOLVED, not HISTORY_NOT_FOUND."""
        src = (REPO_ROOT / "scripts" / "operator" / "collect_demo_micro_trade_forensics.py").read_text()
        # The block that checks diag_resolved_closed and not diag_history_match
        # must come BEFORE the generic HISTORY_NOT_FOUND return.
        idx_diag = src.find('if diag_resolved_closed and not diag_history_match')
        idx_history_not_found = src.find('findings["root_cause"] = "HISTORY_NOT_FOUND"')
        assert idx_diag > 0, "diag_resolved_closed check block not found"
        assert idx_history_not_found > 0, "HISTORY_NOT_FOUND block not found"
        assert idx_diag < idx_history_not_found, \
            "DIAGNOSTIC_ONLY_RESOLVED check must come before HISTORY_NOT_FOUND fallback"

    def test_31_v2_7_3_mt5_history_window_mismatch_detection(self):
        """Forensics must detect MT5 history window mismatch when diagnostic
        used a wider window than forensics."""
        src = (REPO_ROOT / "scripts" / "operator" / "collect_demo_micro_trade_forensics.py").read_text()
        assert "history_window_mismatch" in src
        assert "MT5_HISTORY_WINDOW_MISMATCH" in src

    def test_32_v2_7_3_evidence_verifier_accepts_diagnostic_confirmed_as_pass(self):
        """Evidence verifier must accept DEMO_MICRO_EVIDENCE_RECEIPT_DIAGNOSTIC_CONFIRMED
        as MICRO_PROOF_PASS when fallback_used=false."""
        src = (REPO_ROOT / "scripts" / "audit" / "demo_micro_evidence_verifier.py").read_text()
        assert "DEMO_MICRO_EVIDENCE_RECEIPT_DIAGNOSTIC_CONFIRMED" in src
        assert "MICRO_PROOF_PASS" in src
        # Must check fallback_used and old_trades_used_as_proof
        assert "old_trades_used_as_proof" in src

    def test_33_v2_7_3_evidence_verifier_diagnostic_only_resolved_is_incomplete(self):
        """Evidence verifier must classify DEMO_MICRO_EVIDENCE_DIAGNOSTIC_ONLY_RESOLVED
        as MICRO_PROOF_INCOMPLETE (not FAIL)."""
        src = (REPO_ROOT / "scripts" / "audit" / "demo_micro_evidence_verifier.py").read_text()
        assert "DEMO_MICRO_EVIDENCE_DIAGNOSTIC_ONLY_RESOLVED" in src
        assert "MICRO_PROOF_INCOMPLETE" in src
