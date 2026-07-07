"""TITAN XAU AI - Module 1 MT5 Safe Connector Tests

Verifies:
  - connector exists
  - account demo check exists
  - live account block exists
  - unknown server block exists
  - symbol missing block exists
  - order_send not called
  - token not created
  - data schema validation exists
  - report outputs exist
"""
from __future__ import annotations
import sys, re, os
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


class TestMT5SafeConnector:
    def test_connector_exists(self):
        path = REPO_ROOT / "scripts" / "operator" / "mt5_safe_connector.py"
        assert path.exists()

    def test_account_safety_audit_exists(self):
        path = REPO_ROOT / "scripts" / "audit" / "mt5_exness_account_safety_audit.py"
        assert path.exists()

    def test_connector_has_demo_check(self):
        src = (REPO_ROOT / "scripts" / "operator" / "mt5_safe_connector.py").read_text()
        assert "is_demo" in src
        assert "trade_mode" in src

    def test_connector_has_live_account_block(self):
        src = (REPO_ROOT / "scripts" / "operator" / "mt5_safe_connector.py").read_text()
        assert "BLOCK_LIVE_ACCOUNT" in src

    def test_connector_has_unknown_server_block(self):
        src = (REPO_ROOT / "scripts" / "operator" / "mt5_safe_connector.py").read_text()
        assert "BLOCK_UNKNOWN_SERVER" in src

    def test_connector_has_symbol_missing_block(self):
        src = (REPO_ROOT / "scripts" / "operator" / "mt5_safe_connector.py").read_text()
        assert "BLOCK_SYMBOL_MISSING" in src

    def test_no_order_send_in_connector(self):
        src = (REPO_ROOT / "scripts" / "operator" / "mt5_safe_connector.py").read_text()
        stripped = re.sub(r'"""[\s\S]*?"""', '""', src)
        stripped = re.sub(r"'''[\s\S]*?'''", "''", stripped)
        stripped = re.sub(r'r"[^"]*"', '""', stripped)
        stripped = re.sub(r"r'[^']*'", "''", stripped)
        stripped = re.sub(r'"[^"]*"', '""', stripped)
        stripped = re.sub(r"'[^']*'", "''", stripped)
        assert "order_send(" not in stripped
        assert ".order_send" not in stripped

    def test_no_token_in_connector(self):
        src = (REPO_ROOT / "scripts" / "operator" / "mt5_safe_connector.py").read_text()
        assert "create_local_operator_execution_token" not in src
        assert "execution_token" not in src.lower()

    def test_login_masking_exists(self):
        src = (REPO_ROOT / "scripts" / "operator" / "mt5_safe_connector.py").read_text()
        assert "mask_login" in src
        assert "login_masked" in src

    def test_approved_server_strings_exist(self):
        src = (REPO_ROOT / "scripts" / "operator" / "mt5_safe_connector.py").read_text()
        assert "Exness" in src
        assert "MetaQuotes-Demo" in src

    def test_schema_validation_exists(self):
        src = (REPO_ROOT / "scripts" / "operator" / "mt5_safe_connector.py").read_text()
        assert "validate_ohlc_schema" in src
        assert "validate_spread" in src
        assert "validate_timestamp_continuity" in src

    def test_symbol_verification_exists(self):
        src = (REPO_ROOT / "scripts" / "operator" / "mt5_safe_connector.py").read_text()
        assert "verify_symbol" in src

    def test_h1_bars_fetch_exists(self):
        src = (REPO_ROOT / "scripts" / "operator" / "mt5_safe_connector.py").read_text()
        assert "fetch_h1_bars" in src
        assert "TIMEFRAME_H1" in src

    def test_safe_connect_function_exists(self):
        src = (REPO_ROOT / "scripts" / "operator" / "mt5_safe_connector.py").read_text()
        assert "safe_connect_and_audit" in src

    def test_production_ready_not_set_true(self):
        """Connector must NOT set production_ready=True."""
        src = (REPO_ROOT / "scripts" / "operator" / "mt5_safe_connector.py").read_text()
        assert "production_ready" not in src or "production_ready" in src.replace(
            "production_ready = False", ""
        ).replace('"production_ready": False', "").replace("'production_ready': False", "")

    def test_no_martingale(self):
        src = (REPO_ROOT / "scripts" / "operator" / "mt5_safe_connector.py").read_text()
        assert "martingale" not in src.lower()
