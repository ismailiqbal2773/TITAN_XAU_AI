"""TITAN XAU AI - Sprint 9.9.3.45.8.3 Backtest Parameter Binding Audit Tests"""
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


class TestBacktestParameterBindingAudit:
    def test_01_audit_imports(self):
        import scripts.audit.backtest_parameter_binding_audit as a
        assert hasattr(a, "run_audit")
        assert hasattr(a, "write_report")

    def test_02_audit_returns_result(self):
        import scripts.audit.backtest_parameter_binding_audit as a
        result = a.run_audit()
        assert "verdict" in result
        assert "findings" in result

    def test_03_audit_verdicts_supported(self):
        src = (REPO_ROOT / "scripts" / "audit" / "backtest_parameter_binding_audit.py").read_text()
        assert "BACKTEST_BINDING_COMPLETE" in src
        assert "BACKTEST_BINDING_PARTIAL" in src
        assert "BACKTEST_BINDING_MISSING" in src

    def test_04_audit_includes_parameter_details(self):
        import scripts.audit.backtest_parameter_binding_audit as a
        result = a.run_audit()
        params = result.get("findings", {}).get("parameters", [])
        assert len(params) > 0
        for p in params:
            assert "parameter_name" in p
            assert "source" in p
            assert "validation_status" in p

    def test_05_missing_params_labeled_honestly(self):
        """If no backtest artifacts, verdict should be MISSING or PARTIAL."""
        import scripts.audit.backtest_parameter_binding_audit as a
        result = a.run_audit()
        if result["findings"]["validated"] == 0:
            assert result["verdict"] == "BACKTEST_BINDING_MISSING"

    def test_06_no_order_send(self):
        src = (REPO_ROOT / "scripts" / "audit" / "backtest_parameter_binding_audit.py").read_text()
        code = _strip(src)
        assert not re.search(r"\bmt5\.order_send\s*\(", code)

    def test_07_no_martingale(self):
        src = (REPO_ROOT / "scripts" / "audit" / "backtest_parameter_binding_audit.py").read_text()
        code = _strip(src).lower()
        for term in ["martingale", "grid_trade", "averaging_down", "loss_based_lot"]:
            assert term not in code

    def test_08_writes_json_and_md(self, tmp_path, monkeypatch):
        import scripts.audit.backtest_parameter_binding_audit as a
        monkeypatch.setattr(a, "OUTPUT_DIR", tmp_path)
        result = a.run_audit()
        report = a.write_report(result)
        assert Path(report["json_path"]).exists()
        assert Path(report["md_path"]).exists()
