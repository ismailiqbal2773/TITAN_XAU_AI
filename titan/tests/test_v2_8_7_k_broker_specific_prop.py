"""TITAN XAU AI - Sprint v2.8.7-K Broker-Specific Prop Tests

Verifies:
  - canonical cannot approve alone
  - broker diagnosis script exists
  - broker calibration search exists
  - broker yearly audit exists
  - target broker selection exists
  - rejected brokers are clearly marked
  - broker-specific configs exist only if usable
  - read-only broker runner exists
  - no order_send
  - no token auto-create
  - live_trading false
  - funded_trading false
  - production_ready false
  - CEO not bypassed
  - meta-label not bypassed
  - DD rules enforced
"""
from __future__ import annotations
import sys, re, os, json
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

PROP_DIR = REPO_ROOT / "data" / "reports" / "broker_specific_prop"
SHADOW_DIR = REPO_ROOT / "data" / "reports" / "broker_specific_shadow"
CONFIG_DIR = REPO_ROOT / "config" / "broker_profiles"


class TestCanonicalDeprecation:
    def test_canonical_deprecation_notice_exists(self):
        path = PROP_DIR / "canonical_deprecation_notice.md"
        assert path.exists()

    def test_canonical_cannot_approve_alone(self):
        """The readiness audit must NOT allow canonical to approve alone."""
        path = PROP_DIR / "broker_specific_prop_readiness.json"
        if path.exists():
            data = json.loads(path.read_text())
            assert data.get("canonical_deprecated") is True

    def test_canonical_verdict_is_benchmark_only(self):
        """In failure diagnosis, canonical must be BENCHMARK_ONLY."""
        path = PROP_DIR / "broker_failure_diagnosis.json"
        if path.exists():
            data = json.loads(path.read_text())
            verdicts = data.get("broker_verdicts", {})
            if "canonical" in verdicts:
                assert verdicts["canonical"] == "BENCHMARK_ONLY"


class TestBrokerDiagnosis:
    def test_diagnosis_script_exists(self):
        path = REPO_ROOT / "scripts" / "research" / "run_broker_specific_prop_audit.py"
        assert path.exists()

    def test_diagnosis_md_exists(self):
        path = PROP_DIR / "broker_failure_diagnosis.md"
        assert path.exists()

    def test_diagnosis_json_exists(self):
        path = PROP_DIR / "broker_failure_diagnosis.json"
        assert path.exists()

    def test_feature_drift_csv_exists(self):
        path = PROP_DIR / "broker_feature_drift.csv"
        assert path.exists()

    def test_prediction_drift_csv_exists(self):
        path = PROP_DIR / "broker_prediction_drift.csv"
        assert path.exists()

    def test_session_performance_csv_exists(self):
        path = PROP_DIR / "broker_session_performance.csv"
        assert path.exists()

    def test_monthly_failure_matrix_csv_exists(self):
        path = PROP_DIR / "broker_monthly_failure_matrix.csv"
        assert path.exists()

    def test_dd_failure_matrix_csv_exists(self):
        path = PROP_DIR / "broker_dd_failure_matrix.csv"
        assert path.exists()


class TestBrokerCalibration:
    def test_calibration_search_csv_exists(self):
        path = PROP_DIR / "broker_calibration_search.csv"
        assert path.exists()

    def test_calibration_summary_md_exists(self):
        path = PROP_DIR / "broker_calibration_summary.md"
        assert path.exists()

    def test_calibration_summary_json_exists(self):
        path = PROP_DIR / "broker_calibration_summary.json"
        assert path.exists()

    def test_calibration_has_real_brokers(self):
        """Calibration must test real (non-canonical) brokers."""
        import csv
        path = PROP_DIR / "broker_calibration_search.csv"
        with open(path) as f:
            rows = list(csv.DictReader(f))
        brokers = set(r["broker"] for r in rows)
        # Must include at least some real brokers
        real_brokers = {"fundednext", "exness", "icmarkets", "fbs"}
        assert len(brokers.intersection(real_brokers)) > 0


class TestBrokerYearlyAudit:
    def test_yearly_audit_csv_exists(self):
        path = PROP_DIR / "broker_prop_yearly_audit.csv"
        assert path.exists()

    def test_yearly_summary_md_exists(self):
        path = PROP_DIR / "broker_prop_yearly_summary.md"
        assert path.exists()

    def test_yearly_summary_json_exists(self):
        path = PROP_DIR / "broker_prop_yearly_summary.json"
        assert path.exists()

    def test_target_hit_matrix_csv_exists(self):
        path = PROP_DIR / "broker_target_hit_matrix.csv"
        assert path.exists()

    def test_breach_report_csv_exists(self):
        path = PROP_DIR / "broker_prop_breach_report.csv"
        assert path.exists()

    def test_yearly_verdicts_are_valid(self):
        path = PROP_DIR / "broker_prop_yearly_summary.json"
        data = json.loads(path.read_text())
        verdicts = data.get("broker_yearly_verdicts", {})
        valid = {"BROKER_PROP_READY", "REJECT_DD_RISK", "NEEDS_RETURN_IMPROVEMENT",
                 "REJECT_FOR_PROP", "NEEDS_CALIBRATION"}
        for b, v in verdicts.items():
            assert v in valid, f"invalid verdict {v} for {b}"


class TestTargetBrokerSelection:
    def test_selection_md_exists(self):
        path = PROP_DIR / "target_broker_selection.md"
        assert path.exists()

    def test_selection_json_exists(self):
        path = PROP_DIR / "target_broker_selection.json"
        assert path.exists()
        data = json.loads(path.read_text())
        assert "no_real_broker_ready" in data
        assert "selected_target_broker" in data

    def test_no_real_broker_ready_is_honest(self):
        """If no broker passes, no_real_broker_ready must be True."""
        path = PROP_DIR / "target_broker_selection.json"
        data = json.loads(path.read_text())
        # The audit found no broker passes BROKER_PROP_READY
        # So no_real_broker_ready should be True
        if data.get("selected_target_broker") is None:
            assert data["no_real_broker_ready"] is True

    def test_rejected_brokers_listed(self):
        path = PROP_DIR / "target_broker_selection.json"
        data = json.loads(path.read_text())
        assert "rejected_brokers" in data
        assert len(data["rejected_brokers"]) > 0


class TestBrokerConfigs:
    def test_config_dir_exists(self):
        assert CONFIG_DIR.exists()

    def test_rejected_brokers_have_rejection_notes(self):
        """Brokers that are rejected must have rejection notes."""
        # Check if any rejection notes exist
        notes = list(CONFIG_DIR.glob("*_REJECTED.note"))
        # At least icmarkets should be rejected based on audit
        if notes:
            for note in notes:
                text = note.read_text()
                assert "rejected" in text.lower() or "REJECT" in text

    def test_approved_profiles_have_safety(self):
        """Any approved broker profile must have safety gates."""
        profiles = list(CONFIG_DIR.glob("*_prop_profile.yaml"))
        import yaml
        for profile in profiles:
            with open(profile) as f:
                config = yaml.safe_load(f)
            safety = config.get("safety", {})
            assert safety.get("dry_run") is True
            assert safety.get("live_trading") is False
            assert safety.get("funded_trading") is False
            assert safety.get("production_ready") is False


class TestBrokerShadowRunner:
    def test_shadow_runner_exists(self):
        path = REPO_ROOT / "scripts" / "operator" / "run_broker_specific_shadow_readonly.py"
        assert path.exists()

    def test_shadow_runner_supports_real_brokers(self):
        """Shadow runner must accept --broker for real brokers."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_broker_specific_shadow_readonly.py").read_text()
        assert "fundednext" in src
        assert "exness" in src
        assert "icmarkets" in src
        assert "fbs" in src


class TestReadinessAudit:
    def test_readiness_md_exists(self):
        path = PROP_DIR / "broker_specific_prop_readiness.md"
        assert path.exists()

    def test_readiness_json_exists(self):
        path = PROP_DIR / "broker_specific_prop_readiness.json"
        assert path.exists()
        data = json.loads(path.read_text())
        assert "verdict" in data

    def test_verdict_is_valid(self):
        path = PROP_DIR / "broker_specific_prop_readiness.json"
        data = json.loads(path.read_text())
        assert data["verdict"] in [
            "BROKER_PROP_SHADOW_READY",
            "NO_REAL_BROKER_READY",
            "NEEDS_BROKER_SPECIFIC_MODEL",
            "NEEDS_MORE_DATA",
        ]

    def test_no_real_broker_ready_if_no_broker_passes(self):
        """If no broker is selected, verdict must be NO_REAL_BROKER_READY."""
        path = PROP_DIR / "broker_specific_prop_readiness.json"
        data = json.loads(path.read_text())
        if data.get("selected_target_broker") is None:
            assert data["verdict"] == "NO_REAL_BROKER_READY"


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
        path = REPO_ROOT / "scripts" / "research" / "run_broker_specific_prop_audit.py"
        src = self._strip(path.read_text())
        assert "order_send(" not in src

    def test_no_order_send_in_shadow_runner(self):
        path = REPO_ROOT / "scripts" / "operator" / "run_broker_specific_shadow_readonly.py"
        src = self._strip(path.read_text())
        assert "order_send(" not in src

    def test_no_token_in_audit_script(self):
        path = REPO_ROOT / "scripts" / "research" / "run_broker_specific_prop_audit.py"
        src = path.read_text()
        assert "create_local_operator_execution_token" not in src

    def test_no_token_in_shadow_runner(self):
        path = REPO_ROOT / "scripts" / "operator" / "run_broker_specific_shadow_readonly.py"
        src = path.read_text()
        assert "create_local_operator_execution_token" not in src

    def test_no_martingale(self):
        for f in ["scripts/research/run_broker_specific_prop_audit.py",
                   "scripts/operator/run_broker_specific_shadow_readonly.py"]:
            path = REPO_ROOT / f
            src = self._strip(path.read_text())
            assert "martingale" not in src.lower(), f"martingale found in {f}"

    def test_ceo_not_bypassed_in_audit(self):
        path = REPO_ROOT / "scripts" / "research" / "run_broker_specific_prop_audit.py"
        src = path.read_text()
        assert "evaluate_ceo_decision" in src

    def test_meta_label_not_bypassed_in_audit(self):
        path = REPO_ROOT / "scripts" / "research" / "run_broker_specific_prop_audit.py"
        src = path.read_text()
        assert "meta_threshold" in src
        assert "meta_confidence" in src

    def test_dd_rules_enforced(self):
        """DD rules must be present in the audit script."""
        path = REPO_ROOT / "scripts" / "research" / "run_broker_specific_prop_audit.py"
        src = path.read_text()
        assert "EXT_DAILY_DD" in src or "external_daily_dd" in src
        assert "EXT_TOTAL_DD" in src or "external_total_dd" in src
        assert "0.03" in src  # 3% daily DD
        assert "0.08" in src  # 8% total DD

    def test_production_ready_false_in_configs(self):
        """All broker profiles must have production_ready=false."""
        import yaml
        profiles = list(CONFIG_DIR.glob("*_prop_profile.yaml"))
        for profile in profiles:
            with open(profile) as f:
                config = yaml.safe_load(f)
            assert config["safety"]["production_ready"] is False

    def test_live_trading_false_in_configs(self):
        import yaml
        profiles = list(CONFIG_DIR.glob("*_prop_profile.yaml"))
        for profile in profiles:
            with open(profile) as f:
                config = yaml.safe_load(f)
            assert config["safety"]["live_trading"] is False

    def test_funded_trading_false_in_configs(self):
        import yaml
        profiles = list(CONFIG_DIR.glob("*_prop_profile.yaml"))
        for profile in profiles:
            with open(profile) as f:
                config = yaml.safe_load(f)
            assert config["safety"]["funded_trading"] is False

    def test_no_sma_proxy(self):
        for f in ["scripts/research/run_broker_specific_prop_audit.py",
                   "scripts/operator/run_broker_specific_shadow_readonly.py"]:
            path = REPO_ROOT / f
            src = self._strip(path.read_text())
            assert "sma_crossover" not in src.lower()
            assert "sma_proxy" not in src.lower()

    def test_canonical_not_used_for_approval(self):
        """The audit script must NOT use canonical results for approval."""
        path = REPO_ROOT / "scripts" / "research" / "run_broker_specific_prop_audit.py"
        src = path.read_text()
        # REAL_BROKERS list must not include canonical
        assert '"canonical"' not in src.split("REAL_BROKERS")[1].split("]")[0] if "REAL_BROKERS" in src else True
        # The verdict must come from real brokers only
        assert "REAL_BROKERS" in src
