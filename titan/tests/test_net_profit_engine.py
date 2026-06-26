"""
TITAN XAU AI — Sprint 9.8 Net Profit Engine Tests
"""
from __future__ import annotations
import pytest
from titan.production.net_profit_engine import (
    NetProfitEngine, NetPnLResult, TradeCosts,
)


@pytest.fixture
def engine():
    return NetProfitEngine(
        contract_size=100.0,
        commission_per_lot=30.20,
        tick_value=1.0,
        tick_size=0.01,
        default_spread_usd=0.30,
        default_slippage_pips=2.0,
    )


class TestGrossPnL:
    def test_buy_profit(self, engine):
        r = engine.calculate("BUY", 2000, 2010, 0.01, 1990, spread_usd=0, slippage_pips=0, swap_cost=0)
        # (2010-2000) * 100 * 0.01 = 10.0
        assert r.gross_pnl == pytest.approx(10.0, abs=0.01)

    def test_buy_loss(self, engine):
        r = engine.calculate("BUY", 2000, 1990, 0.01, 1990, spread_usd=0, slippage_pips=0, swap_cost=0)
        assert r.gross_pnl == pytest.approx(-10.0, abs=0.01)

    def test_sell_profit(self, engine):
        r = engine.calculate("SELL", 2000, 1990, 0.01, 2010, spread_usd=0, slippage_pips=0, swap_cost=0)
        assert r.gross_pnl == pytest.approx(10.0, abs=0.01)

    def test_sell_loss(self, engine):
        r = engine.calculate("SELL", 2000, 2010, 0.01, 2010, spread_usd=0, slippage_pips=0, swap_cost=0)
        assert r.gross_pnl == pytest.approx(-10.0, abs=0.01)


class TestNetPnL:
    def test_net_subtracts_spread(self, engine):
        r = engine.calculate("BUY", 2000, 2010, 0.01, 1990, spread_usd=0.30, slippage_pips=0, swap_cost=0)
        assert r.costs.spread_cost == pytest.approx(0.30 * 0.01, abs=0.01)
        assert r.net_pnl < r.gross_pnl

    def test_net_subtracts_commission(self, engine):
        r = engine.calculate("BUY", 2000, 2010, 0.01, 1990, spread_usd=0, slippage_pips=0, swap_cost=0)
        # commission = 30.20 * 0.01 = 0.302
        assert r.costs.commission_cost == pytest.approx(0.302, abs=0.01)
        assert r.net_pnl < r.gross_pnl

    def test_net_subtracts_slippage(self, engine):
        r = engine.calculate("BUY", 2000, 2010, 0.01, 1990, spread_usd=0, slippage_pips=2.0, swap_cost=0)
        # slippage = 2.0 * 1.0 * 0.01 / 0.01 = 2.0
        assert r.costs.slippage_cost == pytest.approx(2.0, abs=0.01)
        assert r.net_pnl < r.gross_pnl

    def test_net_subtracts_swap(self, engine):
        r = engine.calculate("BUY", 2000, 2010, 0.01, 1990, spread_usd=0, slippage_pips=0, swap_cost=0.50)
        assert r.costs.swap_cost == pytest.approx(0.50, abs=0.01)
        assert r.net_pnl < r.gross_pnl

    def test_all_costs_combined(self, engine):
        r = engine.calculate("BUY", 2000, 2010, 0.01, 1990,
                              spread_usd=0.30, slippage_pips=2.0, swap_cost=0.50)
        expected_net = 10.0 - (0.30*0.01) - (30.20*0.01) - 2.0 - 0.50
        assert r.net_pnl == pytest.approx(expected_net, abs=0.01)


class TestGrossPositiveNetNegative:
    def test_gross_positive_net_negative(self, engine):
        # Small gross profit but high costs
        r = engine.calculate("BUY", 2000, 2000.5, 0.01, 1990,
                              spread_usd=0.30, slippage_pips=2.0, swap_cost=0.50)
        # gross = (2000.5-2000) * 100 * 0.01 = 0.50
        assert r.gross_pnl > 0
        assert r.net_pnl < 0  # costs > gross
        assert r.is_profitable_gross is True
        assert r.is_profitable_net is False


class TestRMultiple:
    def test_r_multiple_2r_profit(self, engine):
        # entry=2000, sl=1990, close=2020 → gross=20, risk=10, R=2.0
        r = engine.calculate("BUY", 2000, 2020, 0.01, 1990, spread_usd=0, slippage_pips=0, swap_cost=0)
        assert r.r_multiple == pytest.approx(2.0, abs=0.01)

    def test_r_multiple_1r_loss(self, engine):
        r = engine.calculate("BUY", 2000, 1990, 0.01, 1990, spread_usd=0, slippage_pips=0, swap_cost=0)
        assert r.r_multiple == pytest.approx(-1.0, abs=0.01)


class TestCostEstimation:
    def test_estimate_costs(self, engine):
        costs = engine.estimate_costs(lot=0.01, spread_usd=0.30, slippage_pips=2.0)
        assert costs.spread_cost > 0
        assert costs.commission_cost > 0
        assert costs.slippage_cost > 0
        assert costs.total_cost > 0

    def test_estimate_marked_when_defaults_used(self, engine):
        costs = engine.estimate_costs(lot=0.01)  # uses defaults
        assert costs.is_estimate is True
        assert "spread_estimated" in costs.estimate_reason


class TestCostDrag:
    def test_cost_drag_pct(self, engine):
        r = engine.calculate("BUY", 2000, 2010, 0.01, 1990,
                              spread_usd=0.30, slippage_pips=2.0, swap_cost=0.50)
        assert r.cost_drag_pct > 0
