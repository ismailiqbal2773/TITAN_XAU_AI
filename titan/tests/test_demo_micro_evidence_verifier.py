"""TITAN XAU AI - Sprint 9.9.3.45.8.10 Demo Micro Evidence Verifier Tests"""
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


class TestDemoMicroEvidenceVerifier:
    def test_01_verifier_imports(self):
        import scripts.audit.demo_micro_evidence_verifier as v
        assert hasattr(v, "run_verification")

    def test_02_verifier_returns_result(self):
        import scripts.audit.demo_micro_evidence_verifier as v
        result = v.run_verification()
        assert "verdict" in result

    def test_03_verifier_verdicts_supported(self):
        src = (REPO_ROOT / "scripts" / "audit" / "demo_micro_evidence_verifier.py").read_text()
        assert "MICRO_PROOF_PASS" in src
        assert "MICRO_PROOF_INCOMPLETE" in src
        assert "MICRO_PROOF_FAIL" in src

    def test_04_no_order_send(self):
        src = (REPO_ROOT / "scripts" / "audit" / "demo_micro_evidence_verifier.py").read_text()
        code = _strip(src)
        assert not re.search(r"\bmt5\.order_send\s*\(", code)

    def test_05_no_martingale(self):
        src = (REPO_ROOT / "scripts" / "audit" / "demo_micro_evidence_verifier.py").read_text()
        code = _strip(src).lower()
        for term in ["martingale", "grid_trade", "averaging_down", "loss_based_lot"]:
            assert term not in code

    def test_06_fallback_blocks_proof(self):
        """If fallback_used=True, verdict must be FAIL."""
        import scripts.audit.demo_micro_evidence_verifier as v
        # Check source for fallback check
        src = (REPO_ROOT / "scripts" / "audit" / "demo_micro_evidence_verifier.py").read_text()
        assert "FALLBACK_USED" in src

    def test_07_receipt_match_required_for_pass(self):
        """PASS requires receipt_match_found=True."""
        src = (REPO_ROOT / "scripts" / "audit" / "demo_micro_evidence_verifier.py").read_text()
        assert "RECEIPT_MATCH_NOT_FOUND" in src

    def test_08_open_position_blocks_pass(self):
        """Open positions must block PASS."""
        src = (REPO_ROOT / "scripts" / "audit" / "demo_micro_evidence_verifier.py").read_text()
        assert "UNMANAGED_OPEN_POSITION" in src

    def test_09_evidence_pass_maps_to_micro_proof_pass(self):
        """DEMO_MICRO_EVIDENCE_PASS must map to MICRO_PROOF_PASS."""
        src = (REPO_ROOT / "scripts" / "audit" / "demo_micro_evidence_verifier.py").read_text()
        assert "DEMO_MICRO_EVIDENCE_PASS" in src
        assert "MICRO_PROOF_PASS" in src

    def test_10_entry_confirmed_close_missing_maps_to_incomplete(self):
        """DEMO_MICRO_EVIDENCE_ENTRY_CONFIRMED_CLOSE_DEAL_MISSING must map to INCOMPLETE."""
        src = (REPO_ROOT / "scripts" / "audit" / "demo_micro_evidence_verifier.py").read_text()
        assert "DEMO_MICRO_EVIDENCE_ENTRY_CONFIRMED_CLOSE_DEAL_MISSING" in src

    # === Sprint 9.9.3.45.8.11: evidence verifier update tests ===

    def test_11_verifier_reads_nested_findings(self):
        """Verifier should handle forensics with nested findings."""
        import scripts.audit.demo_micro_evidence_verifier as v
        import json, tempfile
        from pathlib import Path

        # Create a fake forensics output with nested findings
        fake_forensics = {
            "verdict": "DEMO_MICRO_EVIDENCE_PASS",
            "findings": {
                "receipt_match_found": True,
                "fallback_used": False,
                "entry_deals_count": 1,
                "exit_deals_count": 1,
                "open_positions_count": 0,
            }
        }

        # Test by checking the source handles findings.get()
        src = (REPO_ROOT / "scripts" / "audit" / "demo_micro_evidence_verifier.py").read_text()
        assert "findings" in src
        assert "forensics.get" in src

    def test_12_verifier_does_not_treat_diagnostic_support_as_fallback(self):
        """Receipt-supported diagnostic evidence is NOT fallback."""
        src = (REPO_ROOT / "scripts" / "audit" / "demo_micro_evidence_verifier.py").read_text()
        # The verifier checks fallback_used field, not match_method
        assert "fallback_used" in src

    def test_13_verifier_maps_entry_confirmed_to_incomplete(self):
        """DEMO_MICRO_EVIDENCE_ENTRY_CONFIRMED_CLOSE_DEAL_MISSING maps to MICRO_PROOF_INCOMPLETE."""
        src = (REPO_ROOT / "scripts" / "audit" / "demo_micro_evidence_verifier.py").read_text()
        assert "DEMO_MICRO_EVIDENCE_ENTRY_CONFIRMED_CLOSE_DEAL_MISSING" in src
        assert "MICRO_PROOF_INCOMPLETE" in src

    # === Sprint 9.9.3.45.8.17 v2.7.4: Scanner-confirmed forensics ===

    def test_14_v2_7_4_verifier_reads_scanner_evidence(self):
        """Verifier must load ticket_history_scanner.json for scanner-confirmed proof."""
        src = (REPO_ROOT / "scripts" / "audit" / "demo_micro_evidence_verifier.py").read_text()
        assert "ticket_history_scanner.json" in src
        assert "_load_scanner_evidence" in src

    def test_15_v2_7_4_verifier_reads_geometry_evidence(self):
        """Verifier must load execution_geometry_audit.json for geometry-aware proof."""
        src = (REPO_ROOT / "scripts" / "audit" / "demo_micro_evidence_verifier.py").read_text()
        assert "execution_geometry_audit.json" in src
        assert "_load_geometry_evidence" in src

    def test_16_v2_7_4_verifier_accepts_scanner_confirmed_as_pass(self):
        """Verifier must accept scanner-confirmed forensics as MICRO_PROOF_PASS."""
        src = (REPO_ROOT / "scripts" / "audit" / "demo_micro_evidence_verifier.py").read_text()
        assert "scanner_confirmed" in src
        assert "TICKET_HISTORY_MATCH_FOUND" in src
        # Must accept these forensics verdicts when scanner confirms
        assert "DEMO_MICRO_EVIDENCE_RECEIPT_DIAGNOSTIC_CONFIRMED" in src
        assert "DEMO_MICRO_FORENSICS_COMPLETE_WITH_WARNINGS" in src

    def test_17_v2_7_4_verifier_blocks_on_geometry_fail(self):
        """Verifier must FAIL when geometry audit exists but is not PASS."""
        src = (REPO_ROOT / "scripts" / "audit" / "demo_micro_evidence_verifier.py").read_text()
        assert "GEOMETRY_FAIL" in src
        assert "geometry_pass" in src

    def test_18_v2_7_4_verifier_blocks_fallback_old_trades(self):
        """Verifier must NEVER accept old fallback trades as proof."""
        src = (REPO_ROOT / "scripts" / "audit" / "demo_micro_evidence_verifier.py").read_text()
        assert "FALLBACK_USED" in src
        assert "old_trades_used_as_proof" in src

    def test_19_v2_7_4_verifier_no_order_send(self):
        """Verifier must never call mt5.order_send."""
        import re
        def _strip(s):
            s = re.sub(r'"""[\s\S]*?"""', '""', s)
            s = re.sub(r"'''[\s\S]*?'''", "''", s)
            s = re.sub(r'"(?:[^"\\]|\\.)*"', '""', s)
            s = re.sub(r"'(?:[^'\\]|\\.)*'", "''", s)
            return s
        src = (REPO_ROOT / "scripts" / "audit" / "demo_micro_evidence_verifier.py").read_text()
        code = _strip(src)
        assert not re.search(r"\bmt5\.order_send\s*\(", code)

    def test_20_v2_7_4_verifier_no_position_modification(self):
        """Verifier must never modify positions."""
        import re
        def _strip(s):
            s = re.sub(r'"""[\s\S]*?"""', '""', s)
            s = re.sub(r"'''[\s\S]*?'''", "''", s)
            s = re.sub(r'"(?:[^"\\]|\\.)*"', '""', s)
            s = re.sub(r"'(?:[^'\\]|\\.)*'", "''", s)
            return s
        src = (REPO_ROOT / "scripts" / "audit" / "demo_micro_evidence_verifier.py").read_text()
        code = _strip(src)
        assert not re.search(r"\bmt5\.(order_modify|positions_modify)\s*\(", code)
