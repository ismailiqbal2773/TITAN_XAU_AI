"""
TITAN XAU AI — Sprint 9.9 Demo Micro Hard Gate Tests
"""
from __future__ import annotations
import pytest, os
from scripts.audit.demo_micro_hard_gate import evaluate


class TestHardGate:
    def test_blocks_non_demo(self):
        # On Linux without MT5, account is None → blocked
        result = evaluate()
        assert result["verdict"] in ("DEMO_MICRO_BLOCKED", "MARKET_CLOSED")

    def test_blocks_missing_arm_token(self):
        os.environ.pop("TITAN_DEMO_MICRO_ARMED", None)
        result = evaluate()
        assert result["checks"]["arm_token_present"] is False

    def test_dry_check_runs_without_arm(self):
        # evaluate() always runs — it's just a check
        result = evaluate()
        assert "verdict" in result
        assert "checks" in result

    def test_demo_micro_disabled_by_default(self):
        result = evaluate()
        assert result["checks"]["demo_micro_enabled"] is False

    def test_max_lot_ok(self):
        result = evaluate()
        assert result["checks"]["max_lot_ok"] is True

    def test_max_positions_ok(self):
        result = evaluate()
        assert result["checks"]["max_positions_ok"] is True

    def test_max_trades_ok(self):
        result = evaluate()
        assert result["checks"]["max_trades_ok"] is True

    def test_force_close_on_end(self):
        result = evaluate()
        assert result["checks"]["force_close_on_end"] is True

    def test_kill_switch_normal(self):
        result = evaluate()
        assert result["checks"]["kill_switch_normal"] is True

    def test_market_open_check_exists(self):
        result = evaluate()
        assert "market_open" in result["checks"]

    def test_not_real_account_check(self):
        result = evaluate()
        assert "not_real_account" in result["checks"]

    def test_hard_gate_json_generated(self, tmp_path):
        result = evaluate()
        # evaluate returns dict — verify it's serializable
        import json
        json.dumps(result, default=str)

    def test_blocks_on_linux(self):
        import platform
        if platform.system() != "Windows":
            result = evaluate()
            assert result["verdict"] in ("DEMO_MICRO_BLOCKED", "MARKET_CLOSED")
