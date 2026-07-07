"""TITAN XAU AI - Module 5 Multi-Day Forward Shadow Tests"""
from __future__ import annotations
import sys, re
from pathlib import Path
import pytest
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

class TestMultidayForwardShadow:
    def test_controller_exists(self):
        assert (REPO_ROOT / "scripts" / "operator" / "run_exness_multiday_forward_shadow.py").exists()
    def test_cli_args_exist(self):
        src = (REPO_ROOT / "scripts" / "operator" / "run_exness_multiday_forward_shadow.py").read_text()
        assert "--days" in src and "--sleep-seconds" in src
    def test_no_order_send(self):
        src = (REPO_ROOT / "scripts" / "operator" / "run_exness_multiday_forward_shadow.py").read_text()
        stripped = re.sub(r'"""[\s\S]*?"""', '""', src)
        assert "order_send(" not in stripped
    def test_no_token(self):
        src = (REPO_ROOT / "scripts" / "operator" / "run_exness_multiday_forward_shadow.py").read_text()
        assert "create_local_operator_execution_token" not in src
    def test_no_martingale(self):
        src = (REPO_ROOT / "scripts" / "operator" / "run_exness_multiday_forward_shadow.py").read_text()
        assert "martingale" not in src.lower()
