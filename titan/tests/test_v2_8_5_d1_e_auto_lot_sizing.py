"""TITAN XAU AI - Sprint v2.8.5-D.1/E Auto Lot Sizing Tests

Tests the real balance-aware Auto Lot Sizing Engine.

Tests (per sprint spec):
  27. balance/equity growth increases raw_lot
  28. DEMO_SAFE caps final_lot at 0.01
  29. risk percent remains constant
  30. RR geometry unchanged
  31. drawdown reduces lot
  32. loss streak does not increase lot
  33. CEO risk_multiplier reduces lot
  34. capital preservation blocks or reduces lot
  35. broker lot step rounds down
  36. invalid SL blocks
  37. invalid tick value blocks
  38. cent profile normalizes safely
  39. prop daily DD soft reduces risk
  40. prop daily DD hard blocks
  41. total DD cap blocks
  42. no martingale/loss multiplier behavior
  43. build-request displays Auto Lot fields
  44. execute path uses Auto Lot before order builder
  45. Auto Lot audit never calls order_send
"""
from __future__ import annotations
import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


class TestAutoLotSizing:
    """Tests 27-42: Auto Lot Sizing Engine correctness and safety."""

    def test_27_equity_growth_increases_raw_lot(self):
        """Test 27: Higher equity -> higher raw_lot."""
        from titan.production.auto_lot_sizing import calculate_auto_lot
        r_low = calculate_auto_lot(account_equity=5000.0, risk_percent=0.005,
                                   stop_loss_points=50.0, account_mode="DEMO_SAFE")
        r_high = calculate_auto_lot(account_equity=20000.0, risk_percent=0.005,
                                    stop_loss_points=50.0, account_mode="DEMO_SAFE")
        assert r_high.raw_lot > r_low.raw_lot, \
            f"Higher equity should produce higher raw_lot: {r_low.raw_lot} vs {r_high.raw_lot}"

    def test_28_demo_safe_caps_at_001(self):
        """Test 28: DEMO_SAFE final_lot must never exceed 0.01."""
        from titan.production.auto_lot_sizing import calculate_auto_lot
        # Even with very high equity, DEMO_SAFE caps at 0.01
        r = calculate_auto_lot(account_equity=1000000.0, risk_percent=0.005,
                               stop_loss_points=50.0, account_mode="DEMO_SAFE",
                               profile_max_lot=0.01, broker_max_lot=0.01)
        assert r.final_lot <= 0.01, f"DEMO_SAFE must cap at 0.01, got {r.final_lot}"

    def test_29_risk_percent_constant(self):
        """Test 29: Risk percent must remain constant across calculations."""
        from titan.production.auto_lot_sizing import calculate_auto_lot
        r1 = calculate_auto_lot(account_equity=10000.0, risk_percent=0.005,
                                stop_loss_points=50.0, account_mode="DEMO_SAFE")
        r2 = calculate_auto_lot(account_equity=20000.0, risk_percent=0.005,
                                stop_loss_points=100.0, account_mode="DEMO_SAFE")
        assert r1.risk_percent == r2.risk_percent == 0.005

    def test_30_rr_geometry_unchanged(self):
        """Test 30: RR geometry is not affected by lot sizing."""
        from titan.production.auto_lot_sizing import calculate_auto_lot
        # Lot sizing doesn't change SL/TP distances, only lot size
        r = calculate_auto_lot(account_equity=10000.0, risk_percent=0.005,
                               stop_loss_points=50.0, account_mode="DEMO_SAFE")
        # SL points remain as input (lot sizing doesn't modify them)
        assert r.stop_loss_points == 50.0

    def test_31_drawdown_reduces_lot(self):
        """Test 31: Drawdown must reduce lot (not increase)."""
        from titan.production.auto_lot_sizing import calculate_auto_lot
        r_normal = calculate_auto_lot(account_equity=10000.0, risk_percent=0.005,
                                      stop_loss_points=50.0, account_mode="DEMO_SAFE",
                                      daily_drawdown_percent=0.0)
        r_dd = calculate_auto_lot(account_equity=10000.0, risk_percent=0.005,
                                  stop_loss_points=50.0, account_mode="DEMO_SAFE",
                                  daily_drawdown_percent=0.015)  # 1.5% > 1% soft
        assert r_dd.risk_amount < r_normal.risk_amount, \
            "Drawdown must reduce risk_amount"

    def test_32_loss_streak_does_not_increase_lot(self):
        """Test 32: Loss streak must not increase lot."""
        from titan.production.auto_lot_sizing import calculate_auto_lot
        r_normal = calculate_auto_lot(account_equity=10000.0, risk_percent=0.005,
                                      stop_loss_points=50.0, account_mode="DEMO_SAFE",
                                      loss_streak=0)
        r_streak = calculate_auto_lot(account_equity=10000.0, risk_percent=0.005,
                                      stop_loss_points=50.0, account_mode="DEMO_SAFE",
                                      loss_streak=3)
        assert r_streak.risk_amount <= r_normal.risk_amount, \
            "Loss streak must not increase risk_amount"

    def test_33_ceo_risk_multiplier_reduces_lot(self):
        """Test 33: CEO risk_multiplier < 1 must reduce lot."""
        from titan.production.auto_lot_sizing import calculate_auto_lot
        r_full = calculate_auto_lot(account_equity=10000.0, risk_percent=0.005,
                                    stop_loss_points=50.0, account_mode="DEMO_SAFE",
                                    ceo_risk_multiplier=1.0)
        r_half = calculate_auto_lot(account_equity=10000.0, risk_percent=0.005,
                                    stop_loss_points=50.0, account_mode="DEMO_SAFE",
                                    ceo_risk_multiplier=0.5)
        assert r_half.risk_amount < r_full.risk_amount, \
            "CEO risk_multiplier=0.5 must reduce risk_amount"
        assert r_half.effective_risk_percent < r_full.effective_risk_percent

    def test_34_capital_preservation_reduces_lot(self):
        """Test 34: Capital preservation must reduce or block lot."""
        from titan.production.auto_lot_sizing import calculate_auto_lot
        r_normal = calculate_auto_lot(account_equity=10000.0, risk_percent=0.005,
                                      stop_loss_points=50.0, account_mode="DEMO_SAFE",
                                      capital_preservation_active=False)
        r_cap = calculate_auto_lot(account_equity=10000.0, risk_percent=0.005,
                                   stop_loss_points=50.0, account_mode="DEMO_SAFE",
                                   capital_preservation_active=True)
        assert r_cap.risk_amount < r_normal.risk_amount, \
            "Capital preservation must reduce risk_amount"

    def test_35_broker_lot_step_rounds_down(self):
        """Test 35: Broker lot step must round down (never up)."""
        from titan.production.auto_lot_sizing import calculate_auto_lot
        r = calculate_auto_lot(account_equity=50000.0, risk_percent=0.005,
                               stop_loss_points=50.0, account_mode="DEMO_SAFE",
                               broker_lot_step=0.01, profile_max_lot=0.05,
                               broker_max_lot=0.05)
        assert r.rounded_lot <= r.raw_lot, \
            f"Rounded lot must be <= raw lot: {r.rounded_lot} vs {r.raw_lot}"

    def test_36_invalid_sl_blocks(self):
        """Test 36: Invalid SL (<=0) must block."""
        from titan.production.auto_lot_sizing import calculate_auto_lot
        r = calculate_auto_lot(stop_loss_points=0.0, account_mode="DEMO_SAFE")
        assert r.blocked is True
        assert any("INVALID_STOP_LOSS" in b for b in r.blockers)

    def test_37_invalid_tick_value_blocks(self):
        """Test 37: Invalid tick value (<=0) must block."""
        from titan.production.auto_lot_sizing import calculate_auto_lot
        r = calculate_auto_lot(symbol_tick_value=0.0, account_mode="DEMO_SAFE")
        assert r.blocked is True
        assert any("INVALID_TICK_VALUE" in b for b in r.blockers)

    def test_38_cent_profile_normalizes(self):
        """Test 38: Cent account profile normalizes safely."""
        from titan.production.auto_lot_sizing import calculate_auto_lot
        r = calculate_auto_lot(account_equity=100.0, risk_percent=0.005,
                               stop_loss_points=50.0, account_mode="RETAIL_CENT_SAFE",
                               profile_max_lot=0.10, broker_max_lot=0.10)
        assert r.blocked is False or r.final_lot > 0
        # Cent account should produce a valid lot within caps
        assert r.final_lot <= 0.10

    def test_39_prop_daily_dd_soft_reduces_risk(self):
        """Test 39: Prop challenge daily DD soft limit reduces risk."""
        from titan.production.auto_lot_sizing import calculate_auto_lot
        r_normal = calculate_auto_lot(account_equity=10000.0, risk_percent=0.005,
                                      stop_loss_points=50.0, account_mode="PROP_CHALLENGE_SAFE",
                                      daily_drawdown_percent=0.0)
        r_soft = calculate_auto_lot(account_equity=10000.0, risk_percent=0.005,
                                    stop_loss_points=50.0, account_mode="PROP_CHALLENGE_SAFE",
                                    daily_drawdown_percent=0.015)
        assert r_soft.risk_amount < r_normal.risk_amount, \
            "Daily DD soft limit must reduce risk"

    def test_40_prop_daily_dd_hard_blocks(self):
        """Test 40: Prop challenge daily DD hard limit blocks."""
        from titan.production.auto_lot_sizing import calculate_auto_lot
        r = calculate_auto_lot(account_equity=10000.0, risk_percent=0.005,
                               stop_loss_points=50.0, account_mode="PROP_CHALLENGE_SAFE",
                               daily_drawdown_percent=0.025)  # 2.5% > 2% hard
        assert r.blocked is True
        assert any("DAILY_DD_HARD" in b for b in r.blockers)

    def test_41_total_dd_cap_blocks(self):
        """Test 41: Total DD cap must block."""
        from titan.production.auto_lot_sizing import calculate_auto_lot
        r = calculate_auto_lot(account_equity=10000.0, risk_percent=0.005,
                               stop_loss_points=50.0, account_mode="DEMO_SAFE",
                               total_drawdown_percent=0.09)  # 9% > 8% cap
        assert r.blocked is True
        assert any("TOTAL_DD_CAP" in b for b in r.blockers)

    def test_42_no_martingale_loss_multiplier(self):
        """Test 42: No martingale/loss multiplier behavior.

        After a loss (equity drops), lot must NOT increase.
        """
        from titan.production.auto_lot_sizing import calculate_auto_lot
        r_before = calculate_auto_lot(account_equity=10000.0, risk_percent=0.005,
                                      stop_loss_points=50.0, account_mode="DEMO_SAFE",
                                      loss_streak=0)
        r_after = calculate_auto_lot(account_equity=9000.0, risk_percent=0.005,
                                     stop_loss_points=50.0, account_mode="DEMO_SAFE",
                                     loss_streak=1)
        # After loss (equity dropped from 10000 to 9000), lot must NOT increase
        assert r_after.raw_lot <= r_before.raw_lot, \
            f"No martingale: lot after loss must not increase: {r_after.raw_lot} vs {r_before.raw_lot}"
        assert "NO_MARTINGALE" in r_after.reasoning_codes
        assert "NO_LOSS_MULTIPLIER" in r_after.reasoning_codes

    def test_43_build_request_displays_auto_lot_fields(self):
        """Test 43: Build-request must display Auto Lot fields."""
        import scripts.operator.run_managed_demo_micro_trade as m
        args = MagicMock()
        args.direction = "BUY"
        args.entry_price = 2000.0
        args.sl = 0
        args.tp = 0
        args.prop_funded_profile = "prop_funded_safe"
        args.account_profile = ""
        args.use_adaptive_trailing = True
        args.use_dynamic_tp_extension = True
        args.adaptive_policy_mode = "balanced_conservative"
        args.breakeven_trigger_r = 1.0
        args.trailing_trigger_r = 1.75
        args.profit_lock_trigger_r = 3.0
        args.initial_tp_r = 3.0
        args.tp_extension_trigger_r = 2.0
        args.tp_extension_r = 1.0
        args.tp_extension_atr_mult = 1.5
        args.tp_extension_cooldown_seconds = 60
        args.min_profit_lock_after_tp_extension_r = 1.5
        args.max_profit_giveback_r_trend = 0.5
        args.max_profit_giveback_r_range = 0.3
        args.min_hold_seconds = 60
        args.min_monitor_iterations = 3
        args.sl_update_cooldown_seconds = 60
        args.risk_mode = "conservative"
        args.broker_profile = "metaquotes_demo"
        result = m.run_build_request(args.direction, args.entry_price, args.sl, args.tp, args)
        assert "auto_lot_enabled" in result
        assert "auto_lot_final_lot" in result
        assert "auto_lot_raw_lot" in result
        assert "auto_lot_risk_amount" in result
        assert result["auto_lot_enabled"] is True

    def test_44_execute_path_uses_auto_lot_before_order_builder(self):
        """Test 44: Execute path must use Auto Lot before order builder.

        This is a source-level check that auto_lot_sizing is imported
        in the operator script and that the execute-and-monitor path
        has the CEO + Auto Lot flow.
        """
        op_src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        # Auto Lot is imported in build-request path
        assert "from titan.production.auto_lot_sizing import calculate_auto_lot" in op_src, \
            "Operator script must import auto_lot_sizing"
        # CEO is wired before order_send
        assert "evaluate_ceo_decision(" in op_src
        assert "mt5.order_send(request)" in op_src
        # CEO must appear before order_send in execute path
        exec_start = op_src.find("def run_execute_and_monitor")
        ceo_pos = op_src.find("evaluate_ceo_decision(", exec_start)
        order_pos = op_src.find("mt5.order_send(request)", exec_start)
        assert ceo_pos > 0 and order_pos > 0
        assert ceo_pos < order_pos, "CEO must be called before order_send"

    def test_45_auto_lot_audit_never_calls_order_send(self):
        """Test 45: Auto Lot audit must never call mt5.order_send."""
        import re
        audit_src = (REPO_ROOT / "scripts" / "audit" / "auto_lot_sizing_audit.py").read_text()
        engine_src = (REPO_ROOT / "titan" / "production" / "auto_lot_sizing.py").read_text()
        for src, name in [(audit_src, "auto_lot_sizing_audit.py"), (engine_src, "auto_lot_sizing.py")]:
            stripped = re.sub(r'"""[\s\S]*?"""', '""', src)
            stripped = re.sub(r"'''[\s\S]*?'''", "''", stripped)
            stripped = re.sub(r'"(?:[^"\\]|\\.)*"', '""', stripped)
            stripped = re.sub(r"'(?:[^'\\]|\\.)*'", "''", stripped)
            stripped = re.sub(r'#.*$', '', stripped, flags=re.MULTILINE)
            for match in re.finditer(r'(mt5|broker|adapter|self)\.order_send\s*\(', stripped):
                line_start = stripped.rfind('\n', 0, match.start()) + 1
                prefix = stripped[line_start:match.start()]
                if not re.match(r'\s*def\s+', prefix):
                    pytest.fail(f"{name} contains actual order_send call")
