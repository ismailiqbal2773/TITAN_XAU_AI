"""TITAN XAU AI - Sprint v2.8.7-H Candidate Lock + Demo Shadow Tests

Verifies:
  - candidate integrity audit exists
  - accepted candidate comparison exists
  - final locked candidate exists
  - demo_shadow_candidate.yaml exists
  - read-only runner exists
  - readiness audit exists
  - no order_send
  - no token auto-create
  - dry_run true
  - live_trading false
  - funded_trading false
  - production_ready false
  - MetaQuotes-Demo only
  - CEO not bypassed
  - meta-label not bypassed
"""
from __future__ import annotations
import sys, re, os, json
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

CANDIDATE_DIR = REPO_ROOT / "data" / "reports" / "candidate_lock"
SHADOW_DIR = REPO_ROOT / "data" / "reports" / "demo_shadow_readonly"
READINESS_DIR = REPO_ROOT / "data" / "reports" / "demo_shadow_readiness"


class TestCandidateIntegrityAudit:
    def test_integrity_audit_md_exists(self):
        path = CANDIDATE_DIR / "candidate_integrity_audit.md"
        assert path.exists()

    def test_integrity_audit_json_exists(self):
        path = CANDIDATE_DIR / "candidate_integrity_audit.json"
        assert path.exists()
        data = json.loads(path.read_text())
        assert "candidate_lock" in data
        assert "demo_shadow_ready" in data

    def test_integrity_candidate_lock_true(self):
        path = CANDIDATE_DIR / "candidate_integrity_audit.json"
        data = json.loads(path.read_text())
        assert data["candidate_lock"] is True

    def test_sharpe_bug_found_documented(self):
        """The Sharpe bug must be documented."""
        path = CANDIDATE_DIR / "candidate_integrity_audit.json"
        data = json.loads(path.read_text())
        assert "sharpe_bug_found" in data
        # The bug was found and documented
        assert data["sharpe_bug_found"] is True
        assert "sharpe_bug_explanation" in data

    def test_ceo_meta_wired(self):
        path = CANDIDATE_DIR / "candidate_integrity_audit.json"
        data = json.loads(path.read_text())
        assert data["ceo_meta_wired"] is True


class TestAcceptedCandidateComparison:
    def test_comparison_csv_exists(self):
        path = CANDIDATE_DIR / "accepted_candidate_comparison.csv"
        assert path.exists()

    def test_comparison_md_exists(self):
        path = CANDIDATE_DIR / "accepted_candidate_comparison.md"
        assert path.exists()

    def test_comparison_has_rank_score(self):
        import csv
        path = CANDIDATE_DIR / "accepted_candidate_comparison.csv"
        with open(path) as f:
            rows = list(csv.DictReader(f))
        assert len(rows) > 0
        assert "rank_score" in rows[0]


class TestFinalLockedCandidate:
    def test_locked_candidate_md_exists(self):
        path = CANDIDATE_DIR / "final_locked_candidate.md"
        assert path.exists()

    def test_locked_candidate_json_exists(self):
        path = CANDIDATE_DIR / "final_locked_candidate.json"
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["lock_id"] == "C04"
        assert data["safety"]["dry_run"] is True
        assert data["safety"]["live_trading"] is False
        assert data["safety"]["funded_trading"] is False
        assert data["safety"]["production_ready"] is False

    def test_demo_shadow_candidate_yaml_exists(self):
        path = REPO_ROOT / "config" / "demo_shadow_candidate.yaml"
        assert path.exists()
        import yaml
        with open(path) as f:
            config = yaml.safe_load(f)
        cl = config["candidate_lock"]
        assert cl["safety"]["dry_run"] is True
        assert cl["safety"]["live_trading"] is False
        assert cl["safety"]["funded_trading"] is False
        assert cl["safety"]["production_ready"] is False
        assert cl["safety"]["broker"] == "MetaQuotes-Demo"
        assert cl["safety"]["requires_operator_token"] is True
        assert cl["safety"]["requires_cto_review"] is True

    def test_locked_candidate_risk_within_limits(self):
        path = CANDIDATE_DIR / "final_locked_candidate.json"
        data = json.loads(path.read_text())
        assert data["parameters"]["risk_percent"] <= 0.0025
        assert data["parameters"]["max_lot"] <= 0.01


class TestReadOnlyShadowRunner:
    def test_shadow_runner_exists(self):
        path = REPO_ROOT / "scripts" / "operator" / "run_demo_shadow_readonly.py"
        assert path.exists()

    def test_shadow_outputs_exist(self):
        for name in ["shadow_session_summary.md", "shadow_session_summary.json",
                     "shadow_signals.csv", "shadow_journal.jsonl"]:
            path = SHADOW_DIR / name
            assert path.exists(), f"missing {path}"

    def test_shadow_no_order_sent(self):
        path = SHADOW_DIR / "shadow_session_summary.json"
        data = json.loads(path.read_text())
        assert data["no_order_sent"] is True
        assert data["dry_run"] is True
        assert data["live_trading"] is False

    def test_shadow_signals_have_no_order_sent_flag(self):
        import csv
        path = SHADOW_DIR / "shadow_signals.csv"
        with open(path) as f:
            rows = list(csv.DictReader(f))
        assert len(rows) > 0
        for r in rows:
            assert r["NO_ORDER_SENT"] == "True"


class TestDemoShadowReadinessAudit:
    def test_readiness_audit_md_exists(self):
        path = READINESS_DIR / "demo_shadow_readiness.md"
        assert path.exists()

    def test_readiness_audit_json_exists(self):
        path = READINESS_DIR / "demo_shadow_readiness.json"
        assert path.exists()
        data = json.loads(path.read_text())
        assert "verdict" in data
        assert data["verdict"] in ["DEMO_SHADOW_READY", "NOT_READY"]

    def test_readiness_verdict_is_demo_shadow_ready(self):
        path = READINESS_DIR / "demo_shadow_readiness.json"
        data = json.loads(path.read_text())
        assert data["verdict"] == "DEMO_SHADOW_READY"

    def test_readiness_all_checks_pass(self):
        path = READINESS_DIR / "demo_shadow_readiness.json"
        data = json.loads(path.read_text())
        # All boolean checks that start with a known prefix must be True
        required_true = [
            "candidate_lock_exists", "integrity_audit_exists",
            "integrity_candidate_lock", "demo_shadow_allowed",
            "dry_run_true", "live_trading_false", "funded_trading_false",
            "production_ready_false", "metaquotes_demo_only",
            "no_token_auto_create", "no_order_send",
            "ceo_not_bypassed", "meta_label_not_bypassed",
            "ceo_wired", "meta_label_wired", "risk_gates_wired",
            "broker_gates_wired", "journal_path_writable",
            "model_profile_loads", "config_loads",
            "no_order_send_in_shadow_runner",
        ]
        for check in required_true:
            assert data.get(check) is True, f"check failed: {check}"


class TestSafety:
    def _strip(self, src):
        stripped = re.sub(r'"""[\s\S]*?"""', '""', src)
        stripped = re.sub(r"'''[\s\S]*?'''", "''", stripped)
        stripped = re.sub(r'r"[^"]*"', '""', stripped)
        stripped = re.sub(r"r'[^']*'", "''", stripped)
        stripped = re.sub(r'"[^"]*"', '""', stripped)
        stripped = re.sub(r"'[^']*'", "''", stripped)
        return stripped

    def test_no_order_send_in_shadow_runner(self):
        path = REPO_ROOT / "scripts" / "operator" / "run_demo_shadow_readonly.py"
        src = self._strip(path.read_text())
        assert "order_send(" not in src

    def test_no_order_send_in_integrity_audit(self):
        path = REPO_ROOT / "scripts" / "research" / "run_candidate_integrity_audit.py"
        src = self._strip(path.read_text())
        assert "order_send(" not in src

    def test_no_order_send_in_readiness_audit(self):
        path = REPO_ROOT / "scripts" / "audit" / "demo_shadow_readiness_audit.py"
        src = self._strip(path.read_text())
        assert "order_send(" not in src

    def test_no_token_in_shadow_runner(self):
        path = REPO_ROOT / "scripts" / "operator" / "run_demo_shadow_readonly.py"
        src = path.read_text()
        assert "create_local_operator_execution_token" not in src

    def test_no_martingale(self):
        for f in ["scripts/operator/run_demo_shadow_readonly.py",
                   "scripts/research/run_candidate_integrity_audit.py"]:
            path = REPO_ROOT / f
            src = self._strip(path.read_text())
            assert "martingale" not in src.lower(), f"martingale found in {f}"

    def test_ceo_not_bypassed_in_shadow_runner(self):
        path = REPO_ROOT / "scripts" / "operator" / "run_demo_shadow_readonly.py"
        src = path.read_text()
        assert "evaluate_ceo_decision" in src
        assert "ceo_decision.allowed_to_trade" in src or "if not ceo_decision" in src

    def test_meta_label_not_bypassed_in_shadow_runner(self):
        path = REPO_ROOT / "scripts" / "operator" / "run_demo_shadow_readonly.py"
        src = path.read_text()
        assert "meta_threshold" in src
        assert "meta_pass" in src or "meta_confidence" in src

    def test_production_ready_false_in_lock(self):
        path = REPO_ROOT / "config" / "demo_shadow_candidate.yaml"
        text = path.read_text()
        assert "production_ready: false" in text

    def test_dry_run_true_in_lock(self):
        path = REPO_ROOT / "config" / "demo_shadow_candidate.yaml"
        text = path.read_text()
        assert "dry_run: true" in text

    def test_live_trading_false_in_lock(self):
        path = REPO_ROOT / "config" / "demo_shadow_candidate.yaml"
        text = path.read_text()
        assert "live_trading: false" in text

    def test_funded_trading_false_in_lock(self):
        path = REPO_ROOT / "config" / "demo_shadow_candidate.yaml"
        text = path.read_text()
        assert "funded_trading: false" in text

    def test_metaquotes_demo_only(self):
        path = REPO_ROOT / "config" / "demo_shadow_candidate.yaml"
        text = path.read_text()
        assert "MetaQuotes-Demo" in text

    def test_no_sma_proxy(self):
        for f in ["scripts/operator/run_demo_shadow_readonly.py",
                   "scripts/research/run_candidate_integrity_audit.py"]:
            path = REPO_ROOT / f
            src = self._strip(path.read_text())
            assert "sma_crossover" not in src.lower()
            assert "sma_proxy" not in src.lower()
