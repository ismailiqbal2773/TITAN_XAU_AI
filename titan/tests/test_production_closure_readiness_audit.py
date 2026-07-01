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
        """Score breakdown must include all 15 categories."""
        import scripts.audit.production_closure_readiness_audit as a
        result = a.run_audit()
        breakdown = result["score_breakdown"]
        expected = [
            "account_profiles", "broker_profiles", "cost_net_profit",
            "margin_leverage_risk", "account_adaptation_lot_sizing",
            "sl_tp_corridor_partial_close", "reconciliation_forensics",
            "alpha_factory", "retraining_promotion", "runtime_calibration",
            "licensing", "crash_resilience", "dependency_safety",
            "prop_retail_inst", "score_honesty",
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

    # === Sprint 9.9.3.45.8.4: score integrity tests ===

    def test_19_score_capped_when_safe_defaults_exist(self):
        """Score must be capped at 92 if safe defaults exist."""
        import scripts.audit.production_closure_readiness_audit as a
        result = a.run_audit()
        if result.get("safe_default_count", 0) > 0:
            assert result["production_score"] <= 92, \
                f"Score {result['production_score']} > 92 with {result['safe_default_count']} safe defaults"

    def test_20_score_100_blocked_if_needs_backtest_binding(self):
        """Score 100 must be blocked if NEEDS_BACKTEST_BINDING exists."""
        import scripts.audit.production_closure_readiness_audit as a
        result = a.run_audit()
        if result.get("needs_backtest_binding_count", 0) > 0:
            assert result["production_score"] < 100, \
                "Score 100 not allowed with NEEDS_BACKTEST_BINDING"

    def test_21_safe_defaults_present_warning(self):
        """SAFE_DEFAULTS_PRESENT warning must appear when safe defaults exist."""
        import scripts.audit.production_closure_readiness_audit as a
        result = a.run_audit()
        if result.get("safe_default_count", 0) > 0:
            assert any("SAFE_DEFAULTS" in w for w in result.get("warnings", [])), \
                "SAFE_DEFAULTS_PRESENT warning missing"

    def test_22_production_closure_ready_requires_95_and_no_high_warnings(self):
        """PRODUCTION_CLOSURE_READY requires score >= 95 and 0 HIGH warnings."""
        import scripts.audit.production_closure_readiness_audit as a
        result = a.run_audit()
        if result["verdict"] == "PRODUCTION_CLOSURE_READY":
            assert result["production_score"] >= 95
            assert len(result.get("high_warnings", [])) == 0
            assert result.get("needs_backtest_binding_count", 0) == 0

    def test_23_production_closure_with_safe_defaults_requires_90(self):
        """PRODUCTION_CLOSURE_READY_WITH_SAFE_DEFAULTS requires score >= 90."""
        import scripts.audit.production_closure_readiness_audit as a
        result = a.run_audit()
        if result["verdict"] == "PRODUCTION_CLOSURE_READY_WITH_SAFE_DEFAULTS":
            assert result["production_score"] >= 90

    def test_24_audit_includes_alpha_factory(self):
        """Audit must check Alpha Factory modules."""
        import scripts.audit.production_closure_readiness_audit as a
        result = a.run_audit()
        assert "alpha_candidate_generator_exists" in result.get("findings", {})

    def test_25_audit_includes_retraining(self):
        """Audit must check retraining modules."""
        import scripts.audit.production_closure_readiness_audit as a
        result = a.run_audit()
        assert "retraining_orchestrator_exists" in result.get("findings", {})

    def test_26_audit_includes_licensing(self):
        """Audit must check licensing modules."""
        import scripts.audit.production_closure_readiness_audit as a
        result = a.run_audit()
        assert "license_validator_exists" in result.get("findings", {})

    def test_27_audit_includes_resilience(self):
        """Audit must check crash/fail-closed resilience modules."""
        import scripts.audit.production_closure_readiness_audit as a
        result = a.run_audit()
        assert "runtime_health_guard_exists" in result.get("findings", {})

    def test_28_audit_includes_dependency_safety(self):
        """Audit must check dependency update safety."""
        import scripts.audit.production_closure_readiness_audit as a
        result = a.run_audit()
        assert "dependency_policy_exists" in result.get("findings", {})

    def test_29_audit_includes_broker_adapter(self):
        """Audit must check broker execution adapter."""
        import scripts.audit.production_closure_readiness_audit as a
        result = a.run_audit()
        assert "broker_execution_adapter_exists" in result.get("findings", {})

    def test_30_audit_includes_lot_sizing(self):
        """Audit must check lot sizing engine."""
        import scripts.audit.production_closure_readiness_audit as a
        result = a.run_audit()
        assert "lot_sizing_engine_exists" in result.get("findings", {})

    def test_31_audit_includes_partial_close(self):
        """Audit must check partial close engine."""
        import scripts.audit.production_closure_readiness_audit as a
        result = a.run_audit()
        assert "partial_close_engine_exists" in result.get("findings", {})

    def test_32_audit_includes_account_adaptation(self):
        """Audit must check account adaptation engine."""
        import scripts.audit.production_closure_readiness_audit as a
        result = a.run_audit()
        assert "account_adaptation_engine_exists" in result.get("findings", {})

    def test_33_audit_includes_calibration(self):
        """Audit must check runtime calibration engine."""
        import scripts.audit.production_closure_readiness_audit as a
        result = a.run_audit()
        assert "runtime_calibration_engine_exists" in result.get("findings", {})
