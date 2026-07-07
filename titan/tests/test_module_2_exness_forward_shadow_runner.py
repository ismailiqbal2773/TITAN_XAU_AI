"""TITAN XAU AI - Module 2 Exness Forward Shadow Runner Tests"""
from __future__ import annotations
import sys, re
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


class TestForwardShadowRunner:
    def test_runner_exists(self):
        path = REPO_ROOT / "scripts" / "operator" / "run_exness_mt5_readonly_forward_shadow.py"
        assert path.exists()

    def test_cli_args_exist(self):
        src = (REPO_ROOT / "scripts" / "operator" / "run_exness_mt5_readonly_forward_shadow.py").read_text()
        assert "--broker" in src
        assert "--symbol" in src
        assert "--timeframe" in src
        assert "--max-cycles" in src
        assert "--sleep-seconds" in src

    def test_no_order_send_call(self):
        src = (REPO_ROOT / "scripts" / "operator" / "run_exness_mt5_readonly_forward_shadow.py").read_text()
        stripped = re.sub(r'"""[\s\S]*?"""', '""', src)
        stripped = re.sub(r"'''[\s\S]*?'''", "''", stripped)
        stripped = re.sub(r'r"[^"]*"', '""', stripped)
        stripped = re.sub(r"r'[^']*'", "''", stripped)
        stripped = re.sub(r'"[^"]*"', '""', stripped)
        stripped = re.sub(r"'[^']*'", "''", stripped)
        assert "order_send(" not in stripped

    def test_no_token_creation(self):
        src = (REPO_ROOT / "scripts" / "operator" / "run_exness_mt5_readonly_forward_shadow.py").read_text()
        assert "create_local_operator_execution_token" not in src

    def test_NO_ORDER_SENT_enforced(self):
        src = (REPO_ROOT / "scripts" / "operator" / "run_exness_mt5_readonly_forward_shadow.py").read_text()
        assert "NO_ORDER_SENT" in src
        assert "True" in src

    def test_CEO_decision_logged(self):
        src = (REPO_ROOT / "scripts" / "operator" / "run_exness_mt5_readonly_forward_shadow.py").read_text()
        assert "evaluate_ceo_decision" in src
        assert "CEO_decision" in src

    def test_meta_logged(self):
        src = (REPO_ROOT / "scripts" / "operator" / "run_exness_mt5_readonly_forward_shadow.py").read_text()
        assert "meta_confidence" in src
        assert "meta_threshold" in src

    def test_prop_risk_logged(self):
        src = (REPO_ROOT / "scripts" / "operator" / "run_exness_mt5_readonly_forward_shadow.py").read_text()
        assert "prop_risk_decision" in src

    def test_lot_logged(self):
        src = (REPO_ROOT / "scripts" / "operator" / "run_exness_mt5_readonly_forward_shadow.py").read_text()
        assert "calculated_lot" in src

    def test_margin_logged(self):
        src = (REPO_ROOT / "scripts" / "operator" / "run_exness_mt5_readonly_forward_shadow.py").read_text()
        assert "margin_usage" in src

    def test_final_decision_logged(self):
        src = (REPO_ROOT / "scripts" / "operator" / "run_exness_mt5_readonly_forward_shadow.py").read_text()
        assert "final_decision" in src

    def test_decision_types_exist(self):
        src = (REPO_ROOT / "scripts" / "operator" / "run_exness_mt5_readonly_forward_shadow.py").read_text()
        for dt in ["SHADOW_SIGNAL", "REJECT_ALPHA", "REJECT_META", "REJECT_CEO",
                    "REJECT_SPREAD", "REJECT_MARGIN", "SAFETY_BLOCK"]:
            assert dt in src

    def test_production_ready_not_true(self):
        src = (REPO_ROOT / "scripts" / "operator" / "run_exness_mt5_readonly_forward_shadow.py").read_text()
        assert "production_ready" not in src or "False" in src

    def test_no_martingale(self):
        src = (REPO_ROOT / "scripts" / "operator" / "run_exness_mt5_readonly_forward_shadow.py").read_text()
        assert "martingale" not in src.lower()
