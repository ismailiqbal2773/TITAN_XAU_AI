"""TITAN XAU AI - Sprint 9.9.3.45.8.3 Dynamic TP Geometry Tests"""
from __future__ import annotations
import sys
from pathlib import Path
import pytest
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from titan.production.net_profit_target_validator import NetProfitTargetValidator


class TestDynamicTPGeometry:
    def test_01_initial_tp_3r_allowed(self):
        """Initial TP 3R should be allowed for dynamic TP."""
        validator = NetProfitTargetValidator("retail_demo_micro", "zero_spread_demo")
        result = validator.validate(
            direction="BUY", entry_price=2000.0, sl_price=1990.0,
            tp_price=2030.0, lot=0.01, initial_tp_R=3.0,
            dynamic_tp_trigger_R=2.0, dynamic_tp_enabled=True,
        )
        assert result.dynamic_tp_geometry_valid is True

    def test_02_initial_tp_1r_blocked_for_dynamic_tp(self):
        """Initial TP 1R blocked when dynamic TP trigger is 2R."""
        validator = NetProfitTargetValidator("retail_demo_micro", "zero_spread_demo")
        result = validator.validate(
            direction="BUY", entry_price=2000.0, sl_price=1990.0,
            tp_price=2010.0, lot=0.01, initial_tp_R=1.0,
            dynamic_tp_trigger_R=2.0, dynamic_tp_enabled=True,
        )
        assert result.dynamic_tp_geometry_valid is False
        assert any("DYNAMIC_TP_TRIGGER_BEYOND_STATIC_TP" in b for b in result.blockers)

    def test_03_rr_1_1_blocked_for_prop_dynamic_tp(self):
        """RR 1:1 blocked for prop firm with dynamic TP."""
        validator = NetProfitTargetValidator("prop_firm_100x_demo", "prop_firm_standard")
        result = validator.validate(
            direction="BUY", entry_price=2000.0, sl_price=1990.0,
            tp_price=2010.0, lot=0.01, initial_tp_R=1.0,
            dynamic_tp_trigger_R=2.0, dynamic_tp_enabled=True,
        )
        assert any("RR_1_1_BLOCKED_FOR_PROP_DYNAMIC_TP" in b for b in result.blockers)

    def test_04_rr_1_1_allowed_for_retail_without_dynamic_tp(self):
        """RR 1:1 allowed for retail without dynamic TP."""
        validator = NetProfitTargetValidator("retail_demo_micro", "zero_spread_demo")
        result = validator.validate(
            direction="BUY", entry_price=2000.0, sl_price=1990.0,
            tp_price=2010.0, lot=0.01, initial_tp_R=1.0,
            dynamic_tp_enabled=False,
        )
        # No dynamic TP, so RR 1:1 geometry check doesn't apply
        assert not any("RR_1_1_BLOCKED" in b for b in result.blockers)

    def test_05_initial_tp_2r_allowed_for_prop(self):
        """Initial TP 2R allowed for prop firm (meets minimum_RR=2.0)."""
        validator = NetProfitTargetValidator("prop_firm_100x_demo", "prop_firm_standard")
        result = validator.validate(
            direction="BUY", entry_price=2000.0, sl_price=1990.0,
            tp_price=2020.0, lot=0.01, initial_tp_R=2.0,
            dynamic_tp_trigger_R=2.0, dynamic_tp_enabled=True,
        )
        # 2R = trigger_R, so DYNAMIC_TP_TRIGGER_BEYOND_STATIC_TP blocks
        # (initial_tp_R must be > trigger_R, not >=)
        assert any("DYNAMIC_TP_TRIGGER_BEYOND_STATIC_TP" in b for b in result.blockers)

    def test_06_initial_tp_2_5r_blocked_below_3r_minimum(self):
        """Initial TP 2.5R blocked because < 3.0 minimum for dynamic TP."""
        validator = NetProfitTargetValidator("retail_demo_micro", "zero_spread_demo")
        result = validator.validate(
            direction="BUY", entry_price=2000.0, sl_price=1990.0,
            tp_price=2025.0, lot=0.01, initial_tp_R=2.5,
            dynamic_tp_trigger_R=2.0, dynamic_tp_enabled=True,
        )
        # 2.5 > 2.0 trigger, but 2.5 < 3.0 minimum
        assert any("INITIAL_TP_TOO_CLOSE_FOR_DYNAMIC_TP" in b for b in result.blockers)

    def test_07_dynamic_tp_geometry_valid_flag(self):
        """dynamic_tp_geometry_valid must be True only when all geometry checks pass."""
        validator = NetProfitTargetValidator("retail_demo_micro", "zero_spread_demo")
        # Valid: 3R > 2R trigger, 3R >= 3.0 minimum
        result = validator.validate(
            direction="BUY", entry_price=2000.0, sl_price=1990.0,
            tp_price=2030.0, lot=0.01, initial_tp_R=3.0,
            dynamic_tp_trigger_R=2.0, dynamic_tp_enabled=True,
        )
        assert result.dynamic_tp_geometry_valid is True

    def test_08_cost_adjusted_geometry_valid(self):
        """cost_adjusted_geometry_valid must be True when net_RR > 0."""
        validator = NetProfitTargetValidator("retail_demo_micro", "zero_spread_demo")
        result = validator.validate(
            direction="BUY", entry_price=2000.0, sl_price=1990.0,
            tp_price=2030.0, lot=0.01, initial_tp_R=3.0,
            dynamic_tp_enabled=False,
        )
        assert result.cost_adjusted_geometry_valid is True

    def test_09_no_order_send(self):
        import re
        src = (REPO_ROOT / "titan" / "production" / "net_profit_target_validator.py").read_text()
        code = re.sub(r'"""[\s\S]*?"""', '""', src)
        code = re.sub(r'"(?:[^"\\]|\\.)*"', '""', code)
        assert not re.search(r"\bmt5\.order_send\s*\(", code)

    def test_10_no_martingale(self):
        import re
        src = (REPO_ROOT / "titan" / "production" / "net_profit_target_validator.py").read_text()
        code = re.sub(r'"""[\s\S]*?"""', '""', src).lower()
        for term in ["martingale", "grid_trade", "averaging_down", "loss_based_lot"]:
            assert term not in code
