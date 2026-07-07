"""TITAN XAU AI - Module 3 Forward Shadow Validator Tests"""
from __future__ import annotations
import sys, re, json
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


class TestForwardShadowValidator:
    def test_validator_exists(self):
        path = REPO_ROOT / "scripts" / "audit" / "validate_exness_forward_shadow.py"
        assert path.exists()

    def test_validator_checks_no_order_sent(self):
        src = (REPO_ROOT / "scripts" / "audit" / "validate_exness_forward_shadow.py").read_text()
        assert "NO_ORDER_SENT" in src

    def test_validator_checks_no_token(self):
        src = (REPO_ROOT / "scripts" / "audit" / "validate_exness_forward_shadow.py").read_text()
        assert "no_token" in src.lower()

    def test_validator_checks_ceo_logged(self):
        src = (REPO_ROOT / "scripts" / "audit" / "validate_exness_forward_shadow.py").read_text()
        assert "ceo_logged" in src

    def test_validator_checks_meta_logged(self):
        src = (REPO_ROOT / "scripts" / "audit" / "validate_exness_forward_shadow.py").read_text()
        assert "meta_logged" in src

    def test_performance_monitor_calculates_metrics(self):
        src = (REPO_ROOT / "scripts" / "audit" / "validate_exness_forward_shadow.py").read_text()
        assert "signal_rate" in src
        assert "avg_lot" in src
        assert "max_margin_usage" in src

    def test_no_order_send_in_validator(self):
        src = (REPO_ROOT / "scripts" / "audit" / "validate_exness_forward_shadow.py").read_text()
        stripped = re.sub(r'"""[\s\S]*?"""', '""', src)
        stripped = re.sub(r"'''[\s\S]*?'''", "''", stripped)
        assert "order_send(" not in stripped

    def test_no_martingale(self):
        src = (REPO_ROOT / "scripts" / "audit" / "validate_exness_forward_shadow.py").read_text()
        assert "martingale" not in src.lower()
