"""TITAN XAU AI - Sprint v2.8.7-I Prop Yearly Consistency Tests

Verifies:
  - yearly audit script exists
  - prop audit config exists
  - no order_send
  - no token auto-create
  - live_trading false
  - funded_trading false
  - production_ready false
  - risk profiles capped
  - daily DD rule exists
  - total DD rule exists
  - target feasibility report generated
  - consistency score generated
  - prop shadow recommendation generated
"""
from __future__ import annotations
import sys, re, os, json
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

PROP_DIR = REPO_ROOT / "data" / "reports" / "prop_yearly_consistency"


class TestPropYearlyAuditScript:
    def test_audit_script_exists(self):
        path = REPO_ROOT / "scripts" / "research" / "run_prop_yearly_consistency_audit.py"
        assert path.exists()

    def test_audit_config_exists(self):
        path = REPO_ROOT / "config" / "prop_firm_yearly_audit.yaml"
        assert path.exists()
        import yaml
        with open(path) as f:
            config = yaml.safe_load(f)["prop_firm_audit"]
        assert config["account_balance"] == 100000
        assert config["leverage"] == 100
        assert config["external_daily_dd_limit"] == 0.03
        assert config["external_total_dd_limit"] == 0.08

    def test_risk_profiles_capped(self):
        """Risk profiles must not exceed 0.005."""
        import yaml
        path = REPO_ROOT / "config" / "prop_firm_yearly_audit.yaml"
        with open(path) as f:
            config = yaml.safe_load(f)["prop_firm_audit"]
        for name, risk in config["risk_profiles"].items():
            assert risk <= 0.005, f"risk profile {name}={risk} exceeds 0.005 cap"

    def test_daily_dd_rule_exists(self):
        import yaml
        path = REPO_ROOT / "config" / "prop_firm_yearly_audit.yaml"
        with open(path) as f:
            config = yaml.safe_load(f)["prop_firm_audit"]
        assert "external_daily_dd_limit" in config
        assert config["external_daily_dd_limit"] == 0.03

    def test_total_dd_rule_exists(self):
        import yaml
        path = REPO_ROOT / "config" / "prop_firm_yearly_audit.yaml"
        with open(path) as f:
            config = yaml.safe_load(f)["prop_firm_audit"]
        assert "external_total_dd_limit" in config
        assert config["external_total_dd_limit"] == 0.08


class TestPropYearlyOutputs:
    def test_monthly_consistency_csv_exists(self):
        path = PROP_DIR / "monthly_consistency_by_broker_year.csv"
        assert path.exists()

    def test_yearly_summary_csv_exists(self):
        path = PROP_DIR / "yearly_summary_by_broker.csv"
        assert path.exists()

    def test_risk_profile_comparison_csv_exists(self):
        path = PROP_DIR / "risk_profile_comparison.csv"
        assert path.exists()

    def test_prop_rule_breach_report_csv_exists(self):
        path = PROP_DIR / "prop_rule_breach_report.csv"
        assert path.exists()

    def test_monthly_target_hit_matrix_csv_exists(self):
        path = PROP_DIR / "monthly_target_hit_matrix.csv"
        assert path.exists()

    def test_consistency_score_md_exists(self):
        path = PROP_DIR / "consistency_score.md"
        assert path.exists()

    def test_consistency_score_json_exists(self):
        path = PROP_DIR / "consistency_score.json"
        assert path.exists()
        data = json.loads(path.read_text())
        assert "score" in data
        assert "verdict" in data

    def test_target_feasibility_md_exists(self):
        path = PROP_DIR / "target_feasibility.md"
        assert path.exists()

    def test_target_feasibility_json_exists(self):
        path = PROP_DIR / "target_feasibility.json"
        assert path.exists()
        data = json.loads(path.read_text())
        assert "target_10pct_feasible" in data
        assert "target_12pct_feasible" in data
        assert "target_15pct_feasible" in data
        assert "target_20pct_rejected" in data
        assert data["target_20pct_rejected"] is True

    def test_prop_shadow_recommendation_md_exists(self):
        path = PROP_DIR / "prop_shadow_recommendation.md"
        assert path.exists()
        text = path.read_text()
        assert "risk profile" in text.lower()
        assert "DD" in text
        assert "MetaQuotes-Demo" in text
        assert "CTO" in text


class TestConsistencyScore:
    def test_score_is_valid(self):
        path = PROP_DIR / "consistency_score.json"
        data = json.loads(path.read_text())
        assert 0 <= data["score"] <= 100

    def test_verdict_is_valid(self):
        path = PROP_DIR / "consistency_score.json"
        data = json.loads(path.read_text())
        assert data["verdict"] in ["PROP_YEARLY_READY", "PROP_YEARLY_NEAR_PASS", "PROP_YEARLY_NOT_READY"]

    def test_no_dd_breach_in_score(self):
        """If verdict is PROP_YEARLY_READY, there must be no DD breaches."""
        path = PROP_DIR / "consistency_score.json"
        data = json.loads(path.read_text())
        if data["verdict"] == "PROP_YEARLY_READY":
            combined = data.get("combined_yearly", {})
            assert combined.get("daily_dd_breach_count", 0) == 0
            assert combined.get("total_dd_breach_count", 0) == 0


class TestTargetFeasibility:
    def test_20pct_always_rejected(self):
        path = PROP_DIR / "target_feasibility.json"
        data = json.loads(path.read_text())
        assert data["target_20pct_rejected"] is True

    def test_decision_is_valid(self):
        path = PROP_DIR / "target_feasibility.json"
        data = json.loads(path.read_text())
        assert data["decision"] in [
            "TARGET_10_12_FEASIBLE",
            "TARGET_10_12_NOT_FEASIBLE",
            "TARGET_10_15_FEASIBLE",
            "TARGET_15_TOO_AGGRESSIVE",
            "NEEDS_PROP_SPECIFIC_CALIBRATION",
        ]

    def test_best_broker_present(self):
        path = PROP_DIR / "target_feasibility.json"
        data = json.loads(path.read_text())
        assert "best_broker" in data
        assert data["best_broker"] != ""

    def test_safest_risk_profile_present(self):
        path = PROP_DIR / "target_feasibility.json"
        data = json.loads(path.read_text())
        assert "safest_risk_profile" in data
        assert data["safest_risk_profile"] in ["base", "cautious", "stretch"]


class TestSafety:
    def _strip(self, src):
        stripped = re.sub(r'"""[\s\S]*?"""', '""', src)
        stripped = re.sub(r"'''[\s\S]*?'''", "''", stripped)
        stripped = re.sub(r'r"[^"]*"', '""', stripped)
        stripped = re.sub(r"r'[^']*'", "''", stripped)
        stripped = re.sub(r'"[^"]*"', '""', stripped)
        stripped = re.sub(r"'[^']*'", "''", stripped)
        return stripped

    def test_no_order_send_in_audit_script(self):
        path = REPO_ROOT / "scripts" / "research" / "run_prop_yearly_consistency_audit.py"
        src = self._strip(path.read_text())
        assert "order_send(" not in src

    def test_no_token_in_audit_script(self):
        path = REPO_ROOT / "scripts" / "research" / "run_prop_yearly_consistency_audit.py"
        src = path.read_text()
        assert "create_local_operator_execution_token" not in src

    def test_no_martingale(self):
        path = REPO_ROOT / "scripts" / "research" / "run_prop_yearly_consistency_audit.py"
        src = self._strip(path.read_text())
        assert "martingale" not in src.lower()

    def test_live_trading_false_in_config(self):
        import yaml
        path = REPO_ROOT / "config" / "prop_firm_yearly_audit.yaml"
        with open(path) as f:
            config = yaml.safe_load(f)["prop_firm_audit"]
        assert config["safety"]["live_trading"] is False
        assert config["safety"]["funded_trading"] is False
        assert config["safety"]["production_ready"] is False
        assert config["safety"]["dry_run"] is True

    def test_production_ready_false_in_audit_config(self):
        """production_ready must be False in audit config."""
        import yaml
        path = REPO_ROOT / "config" / "prop_firm_yearly_audit.yaml"
        with open(path) as f:
            config = yaml.safe_load(f)["prop_firm_audit"]
        assert config["safety"]["production_ready"] is False

    def test_ceo_not_bypassed(self):
        path = REPO_ROOT / "scripts" / "research" / "run_prop_yearly_consistency_audit.py"
        src = path.read_text()
        assert "evaluate_ceo_decision" in src

    def test_meta_label_not_bypassed(self):
        path = REPO_ROOT / "scripts" / "research" / "run_prop_yearly_consistency_audit.py"
        src = path.read_text()
        assert "meta_threshold" in src
        assert "meta_confidence" in src

    def test_no_sma_proxy(self):
        path = REPO_ROOT / "scripts" / "research" / "run_prop_yearly_consistency_audit.py"
        src = self._strip(path.read_text())
        assert "sma_crossover" not in src.lower()
        assert "sma_proxy" not in src.lower()

    def test_metaquotes_demo_only(self):
        """Audit config must specify MetaQuotes-Demo only."""
        import yaml
        path = REPO_ROOT / "config" / "prop_firm_yearly_audit.yaml"
        with open(path) as f:
            config = yaml.safe_load(f)["prop_firm_audit"]
        assert config["safety"]["broker"] == "MetaQuotes-Demo"
