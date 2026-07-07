"""TITAN XAU AI - Module 6 Supervised Demo Review Gate Tests"""
from __future__ import annotations
import sys, re, json
from pathlib import Path
import pytest
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

class TestSupervisedDemoReviewGate:
    def test_gate_exists(self):
        assert (REPO_ROOT / "scripts" / "audit" / "supervised_demo_review_gate.py").exists()
    def test_output_exists(self):
        assert (REPO_ROOT / "data" / "reports" / "supervised_demo_review_gate" / "supervised_demo_review_gate.json").exists()
    def test_verdict_valid(self):
        path = REPO_ROOT / "data" / "reports" / "supervised_demo_review_gate" / "supervised_demo_review_gate.json"
        data = json.loads(path.read_text())
        assert data["verdict"] in ["SUPERVISED_DEMO_REVIEW_ALLOWED", "NEEDS_MORE_FORWARD_SHADOW_DATA", "NEEDS_PARAMETER_REVIEW", "SAFETY_FAIL"]
    def test_does_not_enable_trading(self):
        path = REPO_ROOT / "data" / "reports" / "supervised_demo_review_gate" / "supervised_demo_review_gate.json"
        data = json.loads(path.read_text())
        assert data["safety"]["live_trading"] is False
        assert data["safety"]["funded_trading"] is False
        assert data["safety"]["production_ready"] is False
    def test_no_order_send(self):
        src = (REPO_ROOT / "scripts" / "audit" / "supervised_demo_review_gate.py").read_text()
        assert "order_send(" not in src
    def test_no_token(self):
        src = (REPO_ROOT / "scripts" / "audit" / "supervised_demo_review_gate.py").read_text()
        assert "create_local_operator_execution_token" not in src
    def test_supervised_demo_not_automatic(self):
        path = REPO_ROOT / "data" / "reports" / "supervised_demo_review_gate" / "supervised_demo_review_gate.json"
        data = json.loads(path.read_text())
        assert data["safety"]["supervised_demo_is_not_automatic"] is True
