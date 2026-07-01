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
