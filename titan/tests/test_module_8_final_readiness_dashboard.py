"""TITAN XAU AI - Module 8 Final Readiness Dashboard Tests"""
from __future__ import annotations
import sys, re, json
from pathlib import Path
import pytest
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

class TestFinalReadinessDashboard:
    def test_dashboard_exists(self):
        assert (REPO_ROOT / "scripts" / "research" / "build_final_project_readiness_dashboard.py").exists()
    def test_output_exists(self):
        assert (REPO_ROOT / "data" / "reports" / "final_project_readiness" / "final_project_readiness_dashboard.json").exists()
    def test_verdict_valid(self):
        path = REPO_ROOT / "data" / "reports" / "final_project_readiness" / "final_project_readiness_dashboard.json"
        data = json.loads(path.read_text())
        assert data["final_verdict"] in ["READY_FOR_SUPERVISED_DEMO_REVIEW", "NEEDS_MORE_FORWARD_SHADOW_DATA", "NEEDS_PARAMETER_REVIEW", "SAFETY_FAIL"]
    def test_module_status_included(self):
        path = REPO_ROOT / "data" / "reports" / "final_project_readiness" / "final_project_readiness_dashboard.json"
        data = json.loads(path.read_text())
        assert "modules" in data
        assert len(data["modules"]) >= 8
    def test_safety_locked(self):
        path = REPO_ROOT / "data" / "reports" / "final_project_readiness" / "final_project_readiness_dashboard.json"
        data = json.loads(path.read_text())
        assert data["safety"]["live_trading"] is False
        assert data["safety"]["funded_trading"] is False
        assert data["safety"]["production_ready"] is False
    def test_matrix_csvs_exist(self):
        for name in ["module_status_matrix", "broker_status_matrix", "risk_status_matrix", "safety_status_matrix", "parameter_status_matrix"]:
            assert (REPO_ROOT / "data" / "reports" / "final_project_readiness" / f"{name}.csv").exists()
    def test_no_order_send(self):
        src = (REPO_ROOT / "scripts" / "research" / "build_final_project_readiness_dashboard.py").read_text()
        assert "order_send(" not in src
