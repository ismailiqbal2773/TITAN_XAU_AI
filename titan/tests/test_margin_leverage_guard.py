"""TITAN XAU AI - Sprint 9.9.3.45.8.3 Margin Leverage Guard Tests"""
from __future__ import annotations
import sys
from pathlib import Path
import pytest
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from titan.production.margin_leverage_guard import MarginLeverageGuard, MarginRiskResult


class TestMarginLeverageGuard:
    def test_01_guard_imports(self):
        assert MarginLeverageGuard is not None

    def test_02_leverage_100_applied_for_prop_profile(self):
        """Prop firm 100x profile must use leverage=100."""
        guard = MarginLeverageGuard("prop_firm_100x_demo", "metaquotes_demo")
        result = guard.calculate(price=2000.0, sl_price=1990.0, lot=0.01)
        assert result.leverage == 100

    def test_03_required_margin_computed(self):
        """Required margin must be computed correctly."""
        guard = MarginLeverageGuard("prop_firm_100x_demo", "metaquotes_demo")
        result = guard.calculate(price=2000.0, sl_price=1990.0, lot=0.01)
        # notional = 2000 * 0.01 * 100 = 2000
        # required_margin = 2000 / 100 = 20
        assert result.notional == pytest.approx(2000.0, abs=0.01)
        assert result.required_margin == pytest.approx(20.0, abs=0.01)

    def test_04_risk_pct_computed(self):
        """Risk percentage must be computed."""
        guard = MarginLeverageGuard("prop_firm_100x_demo", "metaquotes_demo")
        result = guard.calculate(price=2000.0, sl_price=1990.0, lot=0.01,
                                  balance=10000.0)
        # max_loss = |2000 - 1990| * 0.01 * 100 = 10.0
        # risk_pct = 10.0 / 10000 = 0.001
        assert result.max_loss_if_SL == pytest.approx(10.0, abs=0.01)
        assert result.risk_pct == pytest.approx(0.001, abs=0.0001)

    def test_05_margin_usage_pct_computed(self):
        """Margin usage percentage must be computed."""
        guard = MarginLeverageGuard("prop_firm_100x_demo", "metaquotes_demo")
        result = guard.calculate(price=2000.0, sl_price=1990.0, lot=0.01,
                                  balance=10000.0, equity=10000.0)
        # margin_usage = 20 / 10000 = 0.002
        assert result.margin_usage_pct == pytest.approx(0.002, abs=0.0001)

    def test_06_profile_missing_blocks(self):
        """Missing account profile should block."""
        guard = MarginLeverageGuard("nonexistent_profile", "metaquotes_demo")
        result = guard.calculate(price=2000.0, sl_price=1990.0, lot=0.01)
        assert any("ACCOUNT_PROFILE_MISSING" in b for b in result.blockers)

    def test_07_prop_firm_safe(self):
        """Prop firm profile with safe parameters should be prop_firm_safe."""
        guard = MarginLeverageGuard("prop_firm_100x_demo", "metaquotes_demo")
        result = guard.calculate(price=2000.0, sl_price=1990.0, lot=0.01,
                                  balance=10000.0, equity=10000.0)
        assert result.prop_firm_safe is True

    def test_08_retail_safe(self):
        """Retail profile with safe parameters should be retail_safe."""
        guard = MarginLeverageGuard("retail_demo_micro", "metaquotes_demo")
        result = guard.calculate(price=2000.0, sl_price=1990.0, lot=0.01,
                                  balance=10000.0, equity=10000.0)
        assert result.retail_safe is True

    def test_09_institutional_safe(self):
        """Institutional profile with safe parameters should be institutional_safe."""
        guard = MarginLeverageGuard("institutional_low_risk", "metaquotes_demo")
        result = guard.calculate(price=2000.0, sl_price=1990.0, lot=0.01,
                                  balance=10000.0, equity=10000.0)
        assert result.institutional_safe is True

    def test_10_risk_per_trade_too_high_blocks(self):
        """Risk per trade above profile max should block."""
        guard = MarginLeverageGuard("prop_firm_100x_demo", "metaquotes_demo")
        # Use large lot to exceed risk_per_trade_pct
        result = guard.calculate(price=2000.0, sl_price=1900.0, lot=1.0,
                                  balance=10000.0)
        # max_loss = 100 * 1.0 * 100 = 10000
        # risk_pct = 10000 / 10000 = 1.0 (way above 0.005)
        assert any("RISK_PER_TRADE_TOO_HIGH" in b for b in result.blockers)

    def test_11_daily_dd_limit_risk_blocks(self):
        """Daily DD limit risk should block when max_loss exceeds daily_dd_remaining."""
        guard = MarginLeverageGuard("prop_firm_100x_demo", "metaquotes_demo")
        result = guard.calculate(price=2000.0, sl_price=1900.0, lot=1.0,
                                  balance=10000.0, daily_dd_used=250.0)
        # max_daily_dd = 0.03 * 10000 = 300
        # daily_dd_remaining = 300 - 250 = 50
        # max_loss = 10000 > 50 -> block
        assert any("DAILY_DD_LIMIT_RISK" in b for b in result.blockers)

    def test_12_no_order_send(self):
        import re
        src = (REPO_ROOT / "titan" / "production" / "margin_leverage_guard.py").read_text()
        code = re.sub(r'"""[\s\S]*?"""', '""', src)
        code = re.sub(r'"(?:[^"\\]|\\.)*"', '""', code)
        assert not re.search(r"\bmt5\.order_send\s*\(", code)

    def test_13_no_martingale(self):
        import re
        src = (REPO_ROOT / "titan" / "production" / "margin_leverage_guard.py").read_text()
        code = re.sub(r'"""[\s\S]*?"""', '""', src).lower()
        for term in ["martingale", "grid_trade", "averaging_down", "loss_based_lot"]:
            assert term not in code

    def test_14_result_has_all_fields(self):
        guard = MarginLeverageGuard("prop_firm_100x_demo", "metaquotes_demo")
        result = guard.calculate(price=2000.0, sl_price=1990.0, lot=0.01)
        required = [
            "notional", "leverage", "required_margin", "margin_usage_pct",
            "free_margin_after_trade", "max_loss_if_SL", "risk_pct",
            "risk_amount", "daily_dd_remaining", "total_dd_remaining",
            "prop_firm_safe", "retail_safe", "institutional_safe",
            "blockers",
        ]
        for f in required:
            assert hasattr(result, f), f"Missing field: {f}"
