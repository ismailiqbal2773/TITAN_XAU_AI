"""TITAN XAU AI - Module 7 Demo Execution Preflight Tests"""
from __future__ import annotations
import sys, re, json
from pathlib import Path
import pytest
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

class TestDemoExecutionPreflight:
    def test_preflight_exists(self):
        assert (REPO_ROOT / "scripts" / "operator" / "demo_execution_preflight_readonly.py").exists()
    def test_output_exists(self):
        assert (REPO_ROOT / "data" / "reports" / "demo_execution_preflight" / "demo_execution_preflight_readonly.json").exists()
    def test_verdict_is_blocked(self):
        path = REPO_ROOT / "data" / "reports" / "demo_execution_preflight" / "demo_execution_preflight_readonly.json"
        data = json.loads(path.read_text())
        assert data["verdict"] == "DEMO_EXECUTION_BLOCKED_PENDING_CTO_APPROVAL"
    def test_no_token(self):
        src = (REPO_ROOT / "scripts" / "operator" / "demo_execution_preflight_readonly.py").read_text()
        assert "create_local_operator_execution_token" not in src
    def test_no_order_send(self):
        src = (REPO_ROOT / "scripts" / "operator" / "demo_execution_preflight_readonly.py").read_text()
        stripped = re.sub(r'"""[\s\S]*?"""', '""', src)
        assert "order_send(" not in stripped
    def test_production_ready_false(self):
        path = REPO_ROOT / "data" / "reports" / "demo_execution_preflight" / "demo_execution_preflight_readonly.json"
        data = json.loads(path.read_text())
        assert data["safety"]["production_ready"] is False
    def test_cto_approval_required(self):
        path = REPO_ROOT / "data" / "reports" / "demo_execution_preflight" / "demo_execution_preflight_readonly.json"
        data = json.loads(path.read_text())
        assert data["safety"]["cto_approval_required"] is True
