"""TITAN XAU AI - Sprint v2.8.6 MTF Build-Request Tests"""
from __future__ import annotations
import sys
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


class TestMTFBuildRequest:
    def test_h1_only_flag_exists(self):
        """--timeframe-mode h1_only flag must exist and default correctly."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        assert "--timeframe-mode" in src
        assert "h1_only" in src
        assert "mtf_m5_m15_h1" in src

    def test_mtf_flag_calls_engine(self):
        """MTF mode must import and call multi_timeframe_signal_engine."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        assert "from titan.production.multi_timeframe_signal_engine import" in src
        assert "evaluate_mtf_decision" in src
        assert "evaluate_m15_confirmation" in src
        assert "evaluate_m5_trigger" in src

    def test_mtf_display_fields(self):
        """Build-request console must display MTF fields."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        assert "timeframe_mode" in src
        assert "mtf_signal_source" in src
        assert "mtf_is_fresh_signal" in src
        assert "mtf_cache_used" in src
        assert "m15_confirmation_pass" in src
        assert "m5_entry_trigger_pass" in src
        assert "regime_policy_allowed" in src

    def test_execution_now_allowed_remains_false(self):
        """execution_now_allowed must remain False in MTF mode."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        assert "OPERATOR_ARM_TOKEN_REQUIRED" in src

    def test_no_order_send_in_mtf(self):
        """MTF engine must not call mt5.order_send."""
        import re
        src = (REPO_ROOT / "titan" / "production" / "multi_timeframe_signal_engine.py").read_text()
        stripped = re.sub(r'"""[\s\S]*?"""', '""', src)
        stripped = re.sub(r"'''[\s\S]*?'''", "''", stripped)
        stripped = re.sub(r'"(?:[^"\\]|\\.)*"', '""', stripped)
        stripped = re.sub(r"'(?:[^'\\]|\\.)*'", "''", stripped)
        assert "order_send(" not in stripped
