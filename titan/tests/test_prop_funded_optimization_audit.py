"""TITAN XAU AI - Sprint 9.9.3.45.8.8 Prop Funded Optimization Audit Tests"""
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


class TestPropFundedOptimizationAudit:
    def test_01_audit_imports(self):
        import scripts.audit.prop_funded_optimization_audit as a
        assert hasattr(a, "run_audit")
        assert hasattr(a, "write_report")

    def test_02_audit_returns_result(self):
        import scripts.audit.prop_funded_optimization_audit as a
        result = a.run_audit()
        assert "verdict" in result
        assert "optimization_result" in result

    def test_03_audit_has_3_profiles(self):
        import scripts.audit.prop_funded_optimization_audit as a
        result = a.run_audit()
        profiles = result["optimization_result"]["profiles"]
        assert len(profiles) == 3

    def test_04_audit_has_recommended_demo(self):
        import scripts.audit.prop_funded_optimization_audit as a
        result = a.run_audit()
        assert result["optimization_result"]["recommended_first_demo_profile"] != ""

    def test_05_audit_has_aggressive_20pct_status(self):
        import scripts.audit.prop_funded_optimization_audit as a
        result = a.run_audit()
        assert result["optimization_result"]["aggressive_20pct_status"] != ""

    def test_06_no_order_send(self):
        src = (REPO_ROOT / "scripts" / "audit" / "prop_funded_optimization_audit.py").read_text()
        code = _strip(src)
        assert not re.search(r"\bmt5\.order_send\s*\(", code)

    def test_07_no_martingale(self):
        src = (REPO_ROOT / "scripts" / "audit" / "prop_funded_optimization_audit.py").read_text()
        code = _strip(src).lower()
        for term in ["martingale", "grid_trade", "averaging_down", "loss_based_lot"]:
            assert term not in code or "no_" in code

    def test_08_writes_json_and_md(self, tmp_path, monkeypatch):
        import scripts.audit.prop_funded_optimization_audit as a
        monkeypatch.setattr(a, "OUTPUT_DIR", tmp_path)
        result = a.run_audit()
        report = a.write_report(result)
        assert Path(report["json_path"]).exists()
        assert Path(report["md_path"]).exists()
