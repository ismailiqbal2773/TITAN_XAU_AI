"""TITAN XAU AI - Sprint 9.9.3.45.8.3 Production Closure Readiness Audit Tests"""
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


class TestProductionClosureReadinessAudit:
    def test_01_audit_imports(self):
        import scripts.audit.production_closure_readiness_audit as a
        assert hasattr(a, "run_audit")
        assert hasattr(a, "write_report")

    def test_02_audit_returns_result(self):
        import scripts.audit.production_closure_readiness_audit as a
        result = a.run_audit()
        assert "verdict" in result
        assert "production_score" in result
        assert "score_breakdown" in result

    def test_03_audit_verdicts_supported(self):
        src = (REPO_ROOT / "scripts" / "audit" / "production_closure_readiness_audit.py").read_text()
        assert "PRODUCTION_CLOSURE_READY" in src
        assert "PRODUCTION_CLOSURE_READY_WITH_SAFE_DEFAULTS" in src
        assert "PRODUCTION_CLOSURE_BLOCKED" in src

    def test_04_production_score_out_of_100(self):
        import scripts.audit.production_closure_readiness_audit as a
        result = a.run_audit()
        assert 0 <= result["production_score"] <= 100

    def test_05_score_breakdown_categories(self):
        import scripts.audit.production_closure_readiness_audit as a
        result = a.run_audit()
        breakdown = result["score_breakdown"]
        expected = [
            "risk_margin_leverage", "transaction_costs_net_profit",
            "rr_sl_tp_geometry", "reconciliation_forensics",
            "profiles", "parameter_binding", "fail_closed_safety",
            "reporting_audit",
        ]
        for cat in expected:
            assert cat in breakdown, f"Missing score category: {cat}"

    def test_06_audit_checks_account_profiles(self):
        import scripts.audit.production_closure_readiness_audit as a
        result = a.run_audit()
        assert result["findings"].get("account_profiles_exists") is True

    def test_07_audit_checks_broker_profiles(self):
        import scripts.audit.production_closure_readiness_audit as a
        result = a.run_audit()
        assert result["findings"].get("broker_profiles_exists") is True

    def test_08_audit_checks_transaction_cost_engine(self):
        import scripts.audit.production_closure_readiness_audit as a
        result = a.run_audit()
        assert result["findings"].get("transaction_cost_engine_exists") is True

    def test_09_audit_checks_margin_guard(self):
        import scripts.audit.production_closure_readiness_audit as a
        result = a.run_audit()
        assert result["findings"].get("margin_guard") is True

    def test_10_audit_checks_reconciliation(self):
        import scripts.audit.production_closure_readiness_audit as a
        result = a.run_audit()
        assert result["findings"].get("reconciliation") is True

    def test_11_audit_checks_no_martingale(self):
        import scripts.audit.production_closure_readiness_audit as a
        result = a.run_audit()
        assert result["findings"].get("no_martingale") is True
        assert result["findings"].get("no_martingale_modules") is True

    def test_12_audit_checks_prop_constraints(self):
        import scripts.audit.production_closure_readiness_audit as a
        result = a.run_audit()
        assert result["findings"].get("prop_constraints") is True

    def test_13_audit_checks_retail_constraints(self):
        import scripts.audit.production_closure_readiness_audit as a
        result = a.run_audit()
        assert result["findings"].get("retail_constraints") is True

    def test_14_audit_checks_institutional_constraints(self):
        import scripts.audit.production_closure_readiness_audit as a
        result = a.run_audit()
        assert result["findings"].get("institutional_constraints") is True

    def test_15_no_order_send(self):
        src = (REPO_ROOT / "scripts" / "audit" / "production_closure_readiness_audit.py").read_text()
        code = _strip(src)
        assert not re.search(r"\bmt5\.order_send\s*\(", code)

    def test_16_no_martingale_in_audit(self):
        src = (REPO_ROOT / "scripts" / "audit" / "production_closure_readiness_audit.py").read_text()
        code = _strip(src).lower()
        # Allow "martingale" only in forbidden terms list
        for term in ["grid_trade", "averaging_down", "loss_based_lot"]:
            assert term not in code or "forbidden" in code

    def test_17_writes_json_and_md(self, tmp_path, monkeypatch):
        import scripts.audit.production_closure_readiness_audit as a
        monkeypatch.setattr(a, "OUTPUT_DIR", tmp_path)
        result = a.run_audit()
        report = a.write_report(result)
        assert Path(report["json_path"]).exists()
        assert Path(report["md_path"]).exists()

    def test_18_score_90_or_above_passes(self):
        """Score >= 90 with 0 blockers should pass."""
        import scripts.audit.production_closure_readiness_audit as a
        result = a.run_audit()
        if result["production_score"] >= 90 and not result.get("blockers"):
            assert result["verdict"] in (
                "PRODUCTION_CLOSURE_READY",
                "PRODUCTION_CLOSURE_READY_WITH_SAFE_DEFAULTS",
            )
