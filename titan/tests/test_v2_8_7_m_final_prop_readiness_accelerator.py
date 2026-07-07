"""TITAN XAU AI - Sprint v2.8.7-M Final Prop Readiness Accelerator Tests

Verifies:
  - final orchestrator exists
  - Exness profile exists
  - FBS backup profile exists or near-pass note exists
  - leverage = 100
  - risk-based lot sizing exists
  - lot size is not forced to 0.01
  - margin usage calculated
  - profile integrity output exists
  - shadow validation output exists
  - stress test output exists
  - prop rule audit output exists
  - final CTO decision output exists
  - operator commands output exists
  - no order_send
  - no token
  - dry_run true
  - live_trading false
  - funded_trading false
  - production_ready false
  - CEO not bypassed
  - meta-label not bypassed
  - DD rules enforced
  - margin unsafe rejected
  - COMPETITION_DEMO_ONLY rejected
  - canonical cannot approve
  - supervised demo is not automatic
  - funded/live remains blocked
"""
from __future__ import annotations
import sys, re, os, json
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

ACCEL_DIR = REPO_ROOT / "data" / "reports" / "final_prop_readiness_accelerator"


class TestOrchestrator:
    def test_orchestrator_exists(self):
        path = REPO_ROOT / "scripts" / "research" / "run_final_prop_readiness_accelerator.py"
        assert path.exists()

    def test_exness_profile_exists(self):
        path = REPO_ROOT / "config" / "broker_profiles" / "exness_legacy_optimized_prop_profile.yaml"
        assert path.exists()

    def test_fbs_profile_or_note_exists(self):
        """FBS must have either an approved profile or a rejection note."""
        profile = REPO_ROOT / "config" / "broker_profiles" / "fbs_legacy_optimized_prop_profile.yaml"
        note = REPO_ROOT / "config" / "broker_profiles" / "fbs_legacy_optimized_REJECTED.note"
        assert profile.exists() or note.exists(), "FBS must have profile or rejection note"

    def test_leverage_100_in_orchestrator(self):
        src = (REPO_ROOT / "scripts" / "research" / "run_final_prop_readiness_accelerator.py").read_text()
        assert "LEVERAGE = 100" in src

    def test_risk_based_lot_sizing_in_orchestrator(self):
        src = (REPO_ROOT / "scripts" / "research" / "run_final_prop_readiness_accelerator.py").read_text()
        assert "calculate_risk_based_lot" in src
        assert "CONTRACT_SIZE = 100" in src

    def test_lot_not_forced_001(self):
        """Orchestrator must NOT force lot=0.01."""
        src = (REPO_ROOT / "scripts" / "research" / "run_final_prop_readiness_accelerator.py").read_text()
        # The fallback 0.01 is only for edge cases (sl_distance <= 0)
        # Main path must use calculated lot
        assert "lot_size = risk_amount / estimated_loss_per_lot" in src


class TestProfileIntegrity:
    def test_output_exists(self):
        for ext in ["md", "json"]:
            path = ACCEL_DIR / f"exness_profile_integrity.{ext}"
            assert path.exists(), f"missing {path}"

    def test_verdict_is_pass(self):
        path = ACCEL_DIR / "exness_profile_integrity.json"
        data = json.loads(path.read_text())
        assert data["verdict"] == "PROFILE_INTEGRITY_PASS"

    def test_safety_gates_in_profile(self):
        import yaml
        path = REPO_ROOT / "config" / "broker_profiles" / "exness_legacy_optimized_prop_profile.yaml"
        with open(path) as f:
            config = yaml.safe_load(f)
        assert config["safety"]["dry_run"] is True
        assert config["safety"]["live_trading"] is False
        assert config["safety"]["funded_trading"] is False
        assert config["safety"]["production_ready"] is False
        assert config["safety"]["no_order_send"] is True
        assert config["safety"]["requires_cto_review"] is True
        assert config["leverage"] == 100


class TestLotSizing:
    def test_output_exists(self):
        for ext in ["md", "json"]:
            path = ACCEL_DIR / f"lot_sizing_1_100_math.{ext}"
            assert path.exists()

    def test_samples_csv_exists(self):
        path = ACCEL_DIR / "lot_sizing_1_100_samples.csv"
        assert path.exists()

    def test_verdict_is_pass(self):
        path = ACCEL_DIR / "lot_sizing_1_100_math.json"
        data = json.loads(path.read_text())
        assert data["verdict"] == "LOT_SIZING_PASS"
        assert data["leverage"] == 100

    def test_lot_not_fixed_001(self):
        """Lot sizes in samples must NOT all be 0.01."""
        import csv
        path = ACCEL_DIR / "lot_sizing_1_100_samples.csv"
        with open(path) as f:
            rows = list(csv.DictReader(f))
        for r in rows:
            assert float(r["lot_size"]) > 0.01, f"lot_size {r['lot_size']} is fixed at 0.01"

    def test_margin_usage_calculated(self):
        import csv
        path = ACCEL_DIR / "lot_sizing_1_100_samples.csv"
        with open(path) as f:
            rows = list(csv.DictReader(f))
        for r in rows:
            assert float(r["margin_usage"]) > 0, "margin_usage not calculated"


class TestShadowValidation:
    def test_output_exists(self):
        for ext in ["md", "json"]:
            path = ACCEL_DIR / f"exness_shadow_validation.{ext}"
            assert path.exists()

    def test_verdict_is_pass(self):
        path = ACCEL_DIR / "exness_shadow_validation.json"
        data = json.loads(path.read_text())
        assert data["verdict"] == "SHADOW_PASS"

    def test_no_order_sent(self):
        path = ACCEL_DIR / "exness_shadow_validation.json"
        data = json.loads(path.read_text())
        assert data["checks"]["no_order_sent"] is True

    def test_margin_safe(self):
        path = ACCEL_DIR / "exness_shadow_validation.json"
        data = json.loads(path.read_text())
        assert data["checks"]["margin_usage_safe"] is True


class TestShadowPerformance:
    def test_output_exists(self):
        for ext in ["md", "json"]:
            path = ACCEL_DIR / f"exness_shadow_performance.{ext}"
            assert path.exists()

    def test_signal_outcomes_csv_exists(self):
        path = ACCEL_DIR / "exness_shadow_signal_outcomes.csv"
        assert path.exists()

    def test_monthly_progress_csv_exists(self):
        path = ACCEL_DIR / "exness_shadow_monthly_progress.csv"
        assert path.exists()


class TestStressTest:
    def test_output_exists(self):
        for ext in ["md", "json"]:
            path = ACCEL_DIR / f"exness_stress_test.{ext}"
            assert path.exists()

    def test_matrix_csv_exists(self):
        path = ACCEL_DIR / "exness_stress_test_matrix.csv"
        assert path.exists()

    def test_verdict_pass_or_warn(self):
        path = ACCEL_DIR / "exness_stress_test.json"
        data = json.loads(path.read_text())
        assert data["verdict"] in ["STRESS_PASS", "STRESS_WARN"]

    def test_no_dd_breach_in_stress(self):
        """No stress scenario should breach DD limits."""
        import csv
        path = ACCEL_DIR / "exness_stress_test_matrix.csv"
        with open(path) as f:
            rows = list(csv.DictReader(f))
        for r in rows:
            assert int(r["daily_dd_breaches"]) == 0, f"daily DD breach in {r['scenario']}"
            assert int(r["total_dd_breaches"]) == 0, f"total DD breach in {r['scenario']}"


class TestPropRuleAudit:
    def test_output_exists(self):
        for ext in ["md", "json"]:
            path = ACCEL_DIR / f"exness_prop_rule_audit.{ext}"
            assert path.exists()

    def test_verdict_pass_or_warn(self):
        path = ACCEL_DIR / "exness_prop_rule_audit.json"
        data = json.loads(path.read_text())
        assert data["verdict"] in ["PROP_RULE_PASS", "PROP_RULE_WARN"]

    def test_dd_rules_enforced(self):
        path = ACCEL_DIR / "exness_prop_rule_audit.json"
        data = json.loads(path.read_text())
        assert data["checks"]["daily_dd_below_3pct"] is True
        assert data["checks"]["total_dd_below_8pct"] is True


class TestFBSBackup:
    def test_output_exists(self):
        for ext in ["md", "json"]:
            path = ACCEL_DIR / f"fbs_backup_check.{ext}"
            assert path.exists()

    def test_verdict_valid(self):
        path = ACCEL_DIR / "fbs_backup_check.json"
        data = json.loads(path.read_text())
        assert data["verdict"] in ["FBS_BACKUP_READY", "FBS_BACKUP_NEAR_PASS", "FBS_BACKUP_REJECT"]


class TestFinalCTODecision:
    def test_output_exists(self):
        for ext in ["md", "json"]:
            path = ACCEL_DIR / f"final_cto_prop_readiness_decision.{ext}"
            assert path.exists()

    def test_verdict_valid(self):
        path = ACCEL_DIR / "final_cto_prop_readiness_decision.json"
        data = json.loads(path.read_text())
        assert data["verdict"] in [
            "EXNESS_READONLY_SHADOW_PASS",
            "EXNESS_READONLY_SHADOW_WARN",
            "EXNESS_READONLY_SHADOW_FAIL",
            "EXNESS_SUPERVISED_DEMO_REVIEW_ALLOWED",
            "NEEDS_MORE_SHADOW_DATA",
            "NEEDS_BROKER_SPECIFIC_MODEL_RETRAINING",
            "SAFETY_FAIL",
        ]

    def test_live_funded_blocked(self):
        """Live/funded must always be blocked."""
        path = ACCEL_DIR / "final_cto_prop_readiness_decision.json"
        data = json.loads(path.read_text())
        assert data["live_funded_allowed"] is False
        assert data["token_allowed"] is False
        assert data["order_send_allowed"] is False

    def test_production_ready_false(self):
        path = ACCEL_DIR / "final_cto_prop_readiness_decision.json"
        data = json.loads(path.read_text())
        assert data["safety"]["production_ready"] is False

    def test_canonical_cannot_approve(self):
        path = ACCEL_DIR / "final_cto_prop_readiness_decision.json"
        data = json.loads(path.read_text())
        assert data["safety"]["canonical_cannot_approve"] is True

    def test_competition_demo_only_rejected(self):
        path = ACCEL_DIR / "final_cto_prop_readiness_decision.json"
        data = json.loads(path.read_text())
        assert data["safety"]["competition_demo_only_rejected"] is True


class TestOperatorCommands:
    def test_output_exists(self):
        path = ACCEL_DIR / "operator_commands.md"
        assert path.exists()

    def test_commands_contain_pull(self):
        text = (ACCEL_DIR / "operator_commands.md").read_text()
        assert "git pull" in text

    def test_commands_contain_accelerator(self):
        text = (ACCEL_DIR / "operator_commands.md").read_text()
        assert "run_final_prop_readiness_accelerator" in text

    def test_commands_contain_shadow(self):
        text = (ACCEL_DIR / "operator_commands.md").read_text()
        assert "run_legacy_optimized_broker_shadow_readonly" in text


class TestSafety:
    def _strip(self, src):
        stripped = re.sub(r'"""[\s\S]*?"""', '""', src)
        stripped = re.sub(r"'''[\s\S]*?'''", "''", stripped)
        stripped = re.sub(r'r"[^"]*"', '""', stripped)
        stripped = re.sub(r"r'[^']*'", "''", stripped)
        stripped = re.sub(r'"[^"]*"', '""', stripped)
        stripped = re.sub(r"'[^']*'", "''", stripped)
        return stripped

    def test_no_order_send_in_orchestrator(self):
        path = REPO_ROOT / "scripts" / "research" / "run_final_prop_readiness_accelerator.py"
        src = self._strip(path.read_text())
        assert "order_send(" not in src

    def test_no_token_in_orchestrator(self):
        path = REPO_ROOT / "scripts" / "research" / "run_final_prop_readiness_accelerator.py"
        src = path.read_text()
        assert "create_local_operator_execution_token" not in src

    def test_no_martingale(self):
        path = REPO_ROOT / "scripts" / "research" / "run_final_prop_readiness_accelerator.py"
        src = self._strip(path.read_text())
        assert "martingale" not in src.lower()

    def test_ceo_not_bypassed(self):
        path = REPO_ROOT / "scripts" / "research" / "run_final_prop_readiness_accelerator.py"
        src = path.read_text()
        assert "evaluate_ceo_decision" in src

    def test_meta_label_not_bypassed(self):
        path = REPO_ROOT / "scripts" / "research" / "run_final_prop_readiness_accelerator.py"
        src = path.read_text()
        assert "meta_threshold" in src
        assert "meta_confidence" in src

    def test_dd_rules_enforced(self):
        path = REPO_ROOT / "scripts" / "research" / "run_final_prop_readiness_accelerator.py"
        src = path.read_text()
        assert "EXT_DAILY_DD" in src
        assert "0.03" in src
        assert "EXT_TOTAL_DD" in src
        assert "0.08" in src

    def test_supervised_demo_not_automatic(self):
        """Supervised demo review allowed does NOT mean automatic."""
        path = ACCEL_DIR / "final_cto_prop_readiness_decision.md"
        text = path.read_text()
        # The decision must mention CTO review required
        assert "CTO" in text

    def test_funded_live_remains_blocked(self):
        path = ACCEL_DIR / "final_cto_prop_readiness_decision.json"
        data = json.loads(path.read_text())
        assert data["live_funded_allowed"] is False

    def test_no_sma_proxy(self):
        path = REPO_ROOT / "scripts" / "research" / "run_final_prop_readiness_accelerator.py"
        src = self._strip(path.read_text())
        assert "sma_crossover" not in src.lower()
        assert "sma_proxy" not in src.lower()

    def test_competition_demo_only_rejected(self):
        """COMPETITION_DEMO_ONLY must be rejected for funded."""
        # Check legacy profiles config
        import yaml
        path = REPO_ROOT / "config" / "legacy_funded_profiles.yaml"
        with open(path) as f:
            config = yaml.safe_load(f)
        comp = config["legacy_funded_profiles"]["COMPETITION_DEMO_ONLY"]
        assert comp["status"] == "DEMO_ONLY"
