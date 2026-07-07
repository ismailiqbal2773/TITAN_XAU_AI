"""TITAN XAU AI - Module 4 Exness Parameter Discovery Tests"""
from __future__ import annotations
import sys, re
from pathlib import Path
import pytest
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

class TestParameterDiscovery:
    def test_script_exists(self):
        assert (REPO_ROOT / "scripts" / "research" / "run_exness_parameter_discovery.py").exists()
    def test_summary_exists(self):
        assert (REPO_ROOT / "data" / "reports" / "exness_parameter_discovery" / "parameter_discovery_summary.md").exists()
    def test_results_csv_exists(self):
        assert (REPO_ROOT / "data" / "reports" / "exness_parameter_discovery" / "parameter_search_results.csv").exists()
    def test_overfit_audit_exists(self):
        assert (REPO_ROOT / "data" / "reports" / "exness_parameter_discovery" / "parameter_overfit_audit.md").exists()
    def test_no_order_send(self):
        src = (REPO_ROOT / "scripts" / "research" / "run_exness_parameter_discovery.py").read_text()
        stripped = re.sub(r'"""[\s\S]*?"""', '""', src)
        stripped = re.sub(r"'''[\s\S]*?'''", "''", stripped)
        stripped = re.sub(r'r"[^"]*"', '""', stripped)
        stripped = re.sub(r"r'[^']*'", "''", stripped)
        stripped = re.sub(r'"[^"]*"', '""', stripped)
        stripped = re.sub(r"'[^']*'", "''", stripped)
        assert "order_send(" not in stripped
    def test_no_token(self):
        src = (REPO_ROOT / "scripts" / "research" / "run_exness_parameter_discovery.py").read_text()
        assert "create_local_operator_execution_token" not in src
    def test_no_martingale(self):
        src = (REPO_ROOT / "scripts" / "research" / "run_exness_parameter_discovery.py").read_text()
        assert "martingale" not in src.lower()
    def test_ceo_used(self):
        src = (REPO_ROOT / "scripts" / "research" / "run_exness_parameter_discovery.py").read_text()
        assert "evaluate_ceo_decision" in src
    def test_dd_rules_enforced(self):
        src = (REPO_ROOT / "scripts" / "research" / "run_exness_parameter_discovery.py").read_text()
        assert "EXT_DAILY_DD" in src and "0.03" in src
