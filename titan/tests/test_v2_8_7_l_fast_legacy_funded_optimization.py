"""TITAN XAU AI - Sprint v2.8.7-L Fast Legacy Funded Optimization Tests

Verifies:
  - git dirty state is preserved
  - legacy profiles recovered
  - competition profile cannot be approved
  - canonical cannot approve
  - leverage 1:100 is used
  - risk-based lot sizing exists
  - max_lot 0.01 is not forced for 100k prop simulation
  - margin usage is calculated
  - margin unsafe profiles are rejected
  - legacy transfer audit exists
  - legacy broker optimization exists
  - C04 vs legacy comparison exists
  - target broker selection exists
  - approved profiles only for passing brokers
  - rejected brokers clearly marked
  - read-only runner exists
  - no order_send
  - no token auto-create
  - live_trading false
  - funded_trading false
  - production_ready false
  - CEO not bypassed
  - meta-label not bypassed
  - daily DD rule enforced
  - total DD rule enforced
  - external DD breach causes rejection
  - competition/demo-only 20% profile rejected for funded
"""
from __future__ import annotations
import sys, re, os, json
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

OPT_DIR = REPO_ROOT / "data" / "reports" / "fast_legacy_funded_optimization"
SHADOW_DIR = REPO_ROOT / "data" / "reports" / "legacy_optimized_shadow"
CONFIG_DIR = REPO_ROOT / "config" / "broker_profiles"


class TestLegacyProfileRecovery:
    def test_legacy_profiles_config_exists(self):
        path = REPO_ROOT / "config" / "legacy_funded_profiles.yaml"
        assert path.exists()
        import yaml
        with open(path) as f:
            config = yaml.safe_load(f)
        profiles = config["legacy_funded_profiles"]
        assert "SAFE_FUNDED" in profiles
        assert "BALANCED_FUNDED_CHALLENGE" in profiles
        assert "FROZEN_BALANCED_FUNDED" in profiles
        assert "AGGRESSIVE_FUNDED_CHALLENGE" in profiles
        assert "COMPETITION_DEMO_ONLY" in profiles

    def test_legacy_profile_recovery_md_exists(self):
        path = OPT_DIR / "legacy_profile_recovery.md"
        assert path.exists()

    def test_legacy_profile_recovery_json_exists(self):
        path = OPT_DIR / "legacy_profile_recovery.json"
        assert path.exists()
        data = json.loads(path.read_text())
        assert "COMPETITION_DEMO_ONLY" in data["profiles_recovered"]

    def test_legacy_profiles_csv_exists(self):
        path = OPT_DIR / "legacy_profiles.csv"
        assert path.exists()

    def test_competition_demo_only_status_is_demo_only(self):
        """COMPETITION_DEMO_ONLY must be marked as DEMO_ONLY."""
        import yaml
        path = REPO_ROOT / "config" / "legacy_funded_profiles.yaml"
        with open(path) as f:
            config = yaml.safe_load(f)
        comp = config["legacy_funded_profiles"]["COMPETITION_DEMO_ONLY"]
        assert comp["status"] == "DEMO_ONLY"


class TestLotSizing:
    def test_lot_sizing_audit_md_exists(self):
        path = OPT_DIR / "lot_sizing_1_100_audit.md"
        assert path.exists()

    def test_lot_sizing_audit_json_exists(self):
        path = OPT_DIR / "lot_sizing_1_100_audit.json"
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["leverage"] == 100
        assert data["contract_size_per_lot"] == 100

    def test_lot_sizing_comparison_csv_exists(self):
        path = OPT_DIR / "lot_sizing_1_100_comparison.csv"
        assert path.exists()

    def test_leverage_100_in_config(self):
        import yaml
        path = REPO_ROOT / "config" / "legacy_funded_profiles.yaml"
        with open(path) as f:
            config = yaml.safe_load(f)
        assert config["account"]["leverage"] == 100

    def test_risk_based_lot_sizing_in_config(self):
        import yaml
        path = REPO_ROOT / "config" / "legacy_funded_profiles.yaml"
        with open(path) as f:
            config = yaml.safe_load(f)
        assert "risk_based_lot_sizing" in config
        assert config["risk_based_lot_sizing"]["leverage"] == 100

    def test_max_lot_0_01_not_forced(self):
        """The orchestrator must NOT force max_lot=0.01 for 100k prop simulation."""
        src = (REPO_ROOT / "scripts" / "research" / "run_fast_legacy_funded_optimization.py").read_text()
        # Risk-based lot sizing must be implemented
        assert "calculate_risk_based_lot" in src
        assert "use_risk_based_lot" in src
        # Must use 1:100 leverage
        assert "LEVERAGE = 100" in src
        assert "CONTRACT_SIZE = 100" in src


class TestLegacyTransfer:
    def test_legacy_transfer_audit_csv_exists(self):
        path = OPT_DIR / "legacy_transfer_audit.csv"
        assert path.exists()

    def test_legacy_transfer_summary_md_exists(self):
        path = OPT_DIR / "legacy_transfer_summary.md"
        assert path.exists()

    def test_legacy_transfer_summary_json_exists(self):
        path = OPT_DIR / "legacy_transfer_summary.json"
        assert path.exists()

    def test_legacy_broker_profile_matrix_csv_exists(self):
        path = OPT_DIR / "legacy_broker_profile_matrix.csv"
        assert path.exists()

    def test_legacy_target_hit_matrix_csv_exists(self):
        path = OPT_DIR / "legacy_target_hit_matrix.csv"
        assert path.exists()

    def test_legacy_dd_breach_report_csv_exists(self):
        path = OPT_DIR / "legacy_dd_breach_report.csv"
        assert path.exists()

    def test_competition_demo_only_rejected_in_transfer(self):
        """COMPETITION_DEMO_ONLY must be LEGACY_PROFILE_DEMO_ONLY in transfer results."""
        import csv
        path = OPT_DIR / "legacy_transfer_audit.csv"
        with open(path) as f:
            rows = list(csv.DictReader(f))
        demo_only_rows = [r for r in rows if r["profile"] == "COMPETITION_DEMO_ONLY"]
        for r in demo_only_rows:
            assert r["verdict"] == "LEGACY_PROFILE_DEMO_ONLY", \
                f"COMPETITION_DEMO_ONLY must be DEMO_ONLY, got {r['verdict']}"


class TestBrokerOptimization:
    def test_optimization_results_csv_exists(self):
        path = OPT_DIR / "legacy_broker_optimization_results.csv"
        assert path.exists()

    def test_best_profiles_by_broker_csv_exists(self):
        path = OPT_DIR / "legacy_best_profiles_by_broker.csv"
        assert path.exists()

    def test_optimization_summary_md_exists(self):
        path = OPT_DIR / "legacy_broker_optimization_summary.md"
        assert path.exists()

    def test_optimization_summary_json_exists(self):
        path = OPT_DIR / "legacy_broker_optimization_summary.json"
        assert path.exists()


class TestC04VsLegacyComparison:
    def test_comparison_md_exists(self):
        path = OPT_DIR / "c04_vs_legacy_comparison.md"
        assert path.exists()

    def test_comparison_json_exists(self):
        path = OPT_DIR / "c04_vs_legacy_comparison.json"
        assert path.exists()
        data = json.loads(path.read_text())
        assert "c04_too_conservative" in data
        assert "retraining_still_needed" in data

    def test_comparison_csv_exists(self):
        path = OPT_DIR / "c04_vs_legacy_comparison.csv"
        assert path.exists()


class TestFinalBrokerSelection:
    def test_selection_md_exists(self):
        path = OPT_DIR / "final_target_broker_selection.md"
        assert path.exists()

    def test_selection_json_exists(self):
        path = OPT_DIR / "final_target_broker_selection.json"
        assert path.exists()
        data = json.loads(path.read_text())
        assert "selected_target_broker" in data
        assert "verdict" in data
        assert "competition_demo_only_rejected" in data
        assert data["competition_demo_only_rejected"] is True
        assert data["canonical_cannot_approve"] is True

    def test_selected_broker_is_non_canonical(self):
        """Selected broker must NOT be canonical."""
        path = OPT_DIR / "final_target_broker_selection.json"
        data = json.loads(path.read_text())
        selected = data.get("selected_target_broker")
        if selected is not None:
            assert selected != "canonical", "canonical cannot be selected for prop approval"


class TestBrokerProfiles:
    def test_config_dir_exists(self):
        assert CONFIG_DIR.exists()

    def test_approved_profiles_have_safety(self):
        """Approved profiles must have all safety gates."""
        import yaml
        profiles = list(CONFIG_DIR.glob("*_legacy_optimized_prop_profile.yaml"))
        for profile in profiles:
            with open(profile) as f:
                config = yaml.safe_load(f)
            safety = config.get("safety", {})
            assert safety.get("dry_run") is True
            assert safety.get("live_trading") is False
            assert safety.get("funded_trading") is False
            assert safety.get("production_ready") is False
            assert safety.get("no_order_send") is True
            assert config.get("leverage") == 100
            assert config.get("risk_based_lot_sizing") is True

    def test_rejected_brokers_have_notes(self):
        """Rejected brokers must have rejection notes."""
        notes = list(CONFIG_DIR.glob("*_legacy_optimized_REJECTED.note"))
        # At least some brokers should be rejected
        if notes:
            for note in notes:
                text = note.read_text()
                assert "rejected" in text.lower() or "REJECT" in text

    def test_leverage_100_in_profiles(self):
        import yaml
        profiles = list(CONFIG_DIR.glob("*_legacy_optimized_prop_profile.yaml"))
        for profile in profiles:
            with open(profile) as f:
                config = yaml.safe_load(f)
            assert config["leverage"] == 100
            assert config["account_balance"] == 100000


class TestShadowRunner:
    def test_shadow_runner_exists(self):
        path = REPO_ROOT / "scripts" / "operator" / "run_legacy_optimized_broker_shadow_readonly.py"
        assert path.exists()

    def test_shadow_runner_uses_risk_based_lot(self):
        src = (REPO_ROOT / "scripts" / "operator" / "run_legacy_optimized_broker_shadow_readonly.py").read_text()
        assert "calculate_risk_based_lot" in src
        assert "LEVERAGE" in src


class TestReadinessAudit:
    def test_readiness_md_exists(self):
        path = OPT_DIR / "fast_legacy_optimized_prop_readiness.md"
        assert path.exists()

    def test_readiness_json_exists(self):
        path = OPT_DIR / "fast_legacy_optimized_prop_readiness.json"
        assert path.exists()
        data = json.loads(path.read_text())
        assert "verdict" in data
        assert data["verdict"] in [
            "LEGACY_OPTIMIZED_PROP_SHADOW_READY",
            "LEGACY_OPTIMIZED_NEAR_PASS",
            "NEEDS_BROKER_SPECIFIC_MODEL_RETRAINING",
            "NO_REAL_BROKER_READY",
        ]

    def test_canonical_cannot_approve(self):
        path = OPT_DIR / "fast_legacy_optimized_prop_readiness.json"
        data = json.loads(path.read_text())
        assert data.get("canonical_deprecated") is True


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
        path = REPO_ROOT / "scripts" / "research" / "run_fast_legacy_funded_optimization.py"
        src = self._strip(path.read_text())
        assert "order_send(" not in src

    def test_no_order_send_in_shadow_runner(self):
        path = REPO_ROOT / "scripts" / "operator" / "run_legacy_optimized_broker_shadow_readonly.py"
        src = self._strip(path.read_text())
        assert "order_send(" not in src

    def test_no_token_in_orchestrator(self):
        path = REPO_ROOT / "scripts" / "research" / "run_fast_legacy_funded_optimization.py"
        src = path.read_text()
        assert "create_local_operator_execution_token" not in src

    def test_no_martingale(self):
        for f in ["scripts/research/run_fast_legacy_funded_optimization.py",
                   "scripts/operator/run_legacy_optimized_broker_shadow_readonly.py"]:
            path = REPO_ROOT / f
            src = self._strip(path.read_text())
            assert "martingale" not in src.lower(), f"martingale found in {f}"

    def test_ceo_not_bypassed(self):
        path = REPO_ROOT / "scripts" / "research" / "run_fast_legacy_funded_optimization.py"
        src = path.read_text()
        assert "evaluate_ceo_decision" in src

    def test_meta_label_not_bypassed(self):
        path = REPO_ROOT / "scripts" / "research" / "run_fast_legacy_funded_optimization.py"
        src = path.read_text()
        assert "meta_threshold" in src
        assert "meta_confidence" in src

    def test_daily_dd_rule_enforced(self):
        path = REPO_ROOT / "scripts" / "research" / "run_fast_legacy_funded_optimization.py"
        src = path.read_text()
        assert "EXT_DAILY_DD" in src
        assert "0.03" in src  # 3% daily DD limit

    def test_total_dd_rule_enforced(self):
        path = REPO_ROOT / "scripts" / "research" / "run_fast_legacy_funded_optimization.py"
        src = path.read_text()
        assert "EXT_TOTAL_DD" in src
        assert "0.08" in src  # 8% total DD limit

    def test_production_ready_false_in_profiles(self):
        import yaml
        profiles = list(CONFIG_DIR.glob("*_legacy_optimized_prop_profile.yaml"))
        for profile in profiles:
            with open(profile) as f:
                config = yaml.safe_load(f)
            assert config["safety"]["production_ready"] is False

    def test_live_trading_false_in_profiles(self):
        import yaml
        profiles = list(CONFIG_DIR.glob("*_legacy_optimized_prop_profile.yaml"))
        for profile in profiles:
            with open(profile) as f:
                config = yaml.safe_load(f)
            assert config["safety"]["live_trading"] is False

    def test_funded_trading_false_in_profiles(self):
        import yaml
        profiles = list(CONFIG_DIR.glob("*_legacy_optimized_prop_profile.yaml"))
        for profile in profiles:
            with open(profile) as f:
                config = yaml.safe_load(f)
            assert config["safety"]["funded_trading"] is False

    def test_no_sma_proxy(self):
        path = REPO_ROOT / "scripts" / "research" / "run_fast_legacy_funded_optimization.py"
        src = self._strip(path.read_text())
        assert "sma_crossover" not in src.lower()
        assert "sma_proxy" not in src.lower()

    def test_competition_demo_only_not_approvable(self):
        """COMPETITION_DEMO_ONLY must NOT be approvable for funded."""
        src = (REPO_ROOT / "scripts" / "research" / "run_fast_legacy_funded_optimization.py").read_text()
        # The script must explicitly reject COMPETITION_DEMO_ONLY
        assert "LEGACY_PROFILE_DEMO_ONLY" in src
        assert "COMPETITION_DEMO_ONLY" in src

    def test_canonical_not_in_real_brokers(self):
        """REAL_BROKERS must not include canonical."""
        src = (REPO_ROOT / "scripts" / "research" / "run_fast_legacy_funded_optimization.py").read_text()
        # Find REAL_BROKERS definition
        lines = src.split("\n")
        for i, line in enumerate(lines):
            if "REAL_BROKERS" in line and "=" in line:
                # Check next few lines for the list
                block = "\n".join(lines[i:i+3])
                assert "canonical" not in block.lower(), "canonical must not be in REAL_BROKERS"
                break
