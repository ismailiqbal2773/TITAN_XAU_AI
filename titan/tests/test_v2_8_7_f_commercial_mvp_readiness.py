"""TITAN XAU AI - Sprint v2.8.7-F Commercial MVP Readiness Tests

Verifies commercial MVP readiness audit and skeleton.
"""
from __future__ import annotations
import sys, re, os, json
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


class TestCommercialMVPReadinessAudit:
    def test_audit_script_exists(self):
        path = REPO_ROOT / "scripts" / "audit" / "final_commercial_mvp_readiness_audit.py"
        assert path.exists()

    def test_audit_md_exists(self):
        path = REPO_ROOT / "data" / "reports" / "final_commercial_mvp_readiness" / "final_commercial_mvp_readiness.md"
        assert path.exists()

    def test_audit_json_exists(self):
        path = REPO_ROOT / "data" / "reports" / "final_commercial_mvp_readiness" / "final_commercial_mvp_readiness.json"
        assert path.exists()

    def test_verdict_present(self):
        path = REPO_ROOT / "data" / "reports" / "final_commercial_mvp_readiness" / "final_commercial_mvp_readiness.json"
        data = json.loads(path.read_text())
        assert "verdict" in data
        assert data["verdict"] in ["COMMERCIAL_MVP_READY", "DEMO_SHADOW_READY", "NOT_READY"]

    def test_live_ready_false(self):
        """live_ready must always be False — no live trading without explicit future approval."""
        path = REPO_ROOT / "data" / "reports" / "final_commercial_mvp_readiness" / "final_commercial_mvp_readiness.json"
        data = json.loads(path.read_text())
        assert data["live_ready"] is False

    def test_funded_ready_false(self):
        """funded_ready must always be False — no funded trading without explicit future approval."""
        path = REPO_ROOT / "data" / "reports" / "final_commercial_mvp_readiness" / "final_commercial_mvp_readiness.json"
        data = json.loads(path.read_text())
        assert data["funded_ready"] is False

    def test_production_ready_false(self):
        """production_ready must be False in the discovery script."""
        src = (REPO_ROOT / "scripts" / "research" / "run_safe_parameter_discovery.py").read_text()
        assert '"production_ready": False' in src

    def test_all_model_profiles_checked(self):
        path = REPO_ROOT / "data" / "reports" / "final_commercial_mvp_readiness" / "final_commercial_mvp_readiness.json"
        data = json.loads(path.read_text())
        assert data.get("v1_legacy_profile", False) is True
        assert data.get("v2_feature_normalized_profile", False) is True
        assert data.get("v2_multibroker_profile", False) is True

    def test_ceo_governance_wired(self):
        path = REPO_ROOT / "data" / "reports" / "final_commercial_mvp_readiness" / "final_commercial_mvp_readiness.json"
        data = json.loads(path.read_text())
        assert data.get("ceo_governance_wired", False) is True

    def test_meta_label_wired(self):
        path = REPO_ROOT / "data" / "reports" / "final_commercial_mvp_readiness" / "final_commercial_mvp_readiness.json"
        data = json.loads(path.read_text())
        assert data.get("meta_label_wired", False) is True

    def test_mtf_wired(self):
        path = REPO_ROOT / "data" / "reports" / "final_commercial_mvp_readiness" / "final_commercial_mvp_readiness.json"
        data = json.loads(path.read_text())
        assert data.get("mtf_wired", False) is True

    def test_demo_go_decision_present(self):
        path = REPO_ROOT / "data" / "reports" / "final_commercial_mvp_readiness" / "final_commercial_mvp_readiness.json"
        data = json.loads(path.read_text())
        assert data.get("demo_go_decision_present", False) is True


class TestCommercialSkeleton:
    def test_commercial_profile_yaml_exists(self):
        path = REPO_ROOT / "config" / "commercial_profile.yaml"
        assert path.exists()
        text = path.read_text()
        assert "dry_run: true" in text
        assert "live_trading: false" in text
        assert "funded_trading: false" in text
        assert "production_ready: false" in text
        assert "MetaQuotes-Demo" in text

    def test_license_policy_yaml_exists(self):
        path = REPO_ROOT / "config" / "license_policy.yaml"
        assert path.exists()
        text = path.read_text()
        assert "block_live_without_license: true" in text
        assert "block_funded_without_license: true" in text

    def test_commercial_mvp_runbook_exists(self):
        path = REPO_ROOT / "docs" / "operator" / "COMMERCIAL_MVP_RUNBOOK.md"
        assert path.exists()
        text = path.read_text()
        assert "production_ready" in text
        assert "DO NOT" in text

    def test_demo_shadow_runbook_exists(self):
        path = REPO_ROOT / "docs" / "operator" / "DEMO_SHADOW_RUNBOOK.md"
        assert path.exists()
        text = path.read_text()
        assert "DEMO_SHADOW_ALLOWED" in text
        assert "CTO" in text

    def test_installation_windows_exists(self):
        path = REPO_ROOT / "docs" / "operator" / "INSTALLATION_WINDOWS.md"
        assert path.exists()

    def test_commercial_demo_runner_exists(self):
        path = REPO_ROOT / "scripts" / "operator" / "run_commercial_demo_mvp.py"
        assert path.exists()
        src = path.read_text()
        assert "dry_run" in src
        assert "BLOCKED" in src or "NO_SAFE_PARAMETER_FOUND" in src

    def test_no_order_send_in_commercial_runner(self):
        path = REPO_ROOT / "scripts" / "operator" / "run_commercial_demo_mvp.py"
        src = path.read_text()
        stripped = re.sub(r'"""[\s\S]*?"""', '""', src)
        stripped = re.sub(r"'''[\s\S]*?'''", "''", stripped)
        assert "order_send(" not in stripped

    def test_no_token_in_commercial_runner(self):
        path = REPO_ROOT / "scripts" / "operator" / "run_commercial_demo_mvp.py"
        src = path.read_text()
        assert "create_local_operator_execution_token" not in src
