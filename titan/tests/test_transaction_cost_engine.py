"""TITAN XAU AI - Sprint 9.9.3.45.8.3 Transaction Cost Engine Tests"""
from __future__ import annotations
import sys
from pathlib import Path
import pytest
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from titan.production.transaction_cost_engine import TransactionCostEngine, TransactionCostResult


class TestTransactionCostEngine:
    def test_01_engine_imports(self):
        assert TransactionCostEngine is not None

    def test_02_gross_profit_computed(self):
        engine = TransactionCostEngine("zero_spread_demo")
        result = engine.calculate(
            direction="BUY", entry_price=2000.0, sl_price=1990.0,
            tp_price=2030.0, lot=0.01, current_price=2030.0,
        )
        # gross_profit = (2030 - 2000) * 0.01 * 100 = 30.0
        assert result.gross_profit == pytest.approx(30.0, abs=0.01)

    def test_03_spread_cost_included(self):
        engine = TransactionCostEngine("zero_spread_demo")
        result = engine.calculate(
            direction="BUY", entry_price=2000.0, sl_price=1990.0,
            tp_price=2030.0, lot=0.01, current_price=2030.0,
        )
        # spread_cost = spread * lot * contract_size
        assert result.spread_cost > 0

    def test_04_commission_cost_included(self):
        engine = TransactionCostEngine("standard_retail")
        result = engine.calculate(
            direction="BUY", entry_price=2000.0, sl_price=1990.0,
            tp_price=2030.0, lot=0.01, current_price=2030.0,
        )
        # commission = 7.0 * 0.01 = 0.07
        assert result.commission_cost == pytest.approx(0.07, abs=0.01)

    def test_05_slippage_cost_included(self):
        engine = TransactionCostEngine("zero_spread_demo")
        result = engine.calculate(
            direction="BUY", entry_price=2000.0, sl_price=1990.0,
            tp_price=2030.0, lot=0.01, current_price=2030.0,
        )
        assert result.slippage_cost > 0

    def test_06_swap_cost_included(self):
        engine = TransactionCostEngine("standard_retail")
        result = engine.calculate(
            direction="BUY", entry_price=2000.0, sl_price=1990.0,
            tp_price=2030.0, lot=0.01, current_price=2030.0,
            nights_held=3,
        )
        # swap = -4.20 * 0.01 * 3 = -0.126
        assert result.swap_cost < 0  # Swap is a cost (negative for long)

    def test_07_net_profit_computed(self):
        engine = TransactionCostEngine("zero_spread_demo")
        result = engine.calculate(
            direction="BUY", entry_price=2000.0, sl_price=1990.0,
            tp_price=2030.0, lot=0.01, current_price=2030.0,
        )
        # net = gross - total_cost
        assert result.net_profit < result.gross_profit
        assert result.net_profit == pytest.approx(
            result.gross_profit - result.total_transaction_cost, abs=0.01
        )

    def test_08_gross_R_and_net_R_computed(self):
        engine = TransactionCostEngine("zero_spread_demo")
        result = engine.calculate(
            direction="BUY", entry_price=2000.0, sl_price=1990.0,
            tp_price=2030.0, lot=0.01, current_price=2030.0,
        )
        assert result.gross_R > 0
        assert result.net_R > 0
        assert result.net_R < result.gross_R  # Net is less due to costs

    def test_09_gross_RR_and_net_RR_computed(self):
        engine = TransactionCostEngine("zero_spread_demo")
        result = engine.calculate(
            direction="BUY", entry_price=2000.0, sl_price=1990.0,
            tp_price=2030.0, lot=0.01, current_price=2030.0,
        )
        # gross_RR = (2030 - 2000) / (2000 - 1990) = 30/10 = 3.0
        assert result.gross_RR == pytest.approx(3.0, abs=0.01)
        assert result.net_RR < result.gross_RR  # Net RR less due to costs

    def test_10_break_even_price_after_cost(self):
        engine = TransactionCostEngine("zero_spread_demo")
        result = engine.calculate(
            direction="BUY", entry_price=2000.0, sl_price=1990.0,
            tp_price=2030.0, lot=0.01, current_price=2030.0,
        )
        # Break-even > entry for BUY (need to cover costs)
        assert result.break_even_price_after_cost > 2000.0

    def test_11_cost_adjusted_TP_and_SL(self):
        engine = TransactionCostEngine("zero_spread_demo")
        result = engine.calculate(
            direction="BUY", entry_price=2000.0, sl_price=1990.0,
            tp_price=2030.0, lot=0.01, current_price=2030.0,
        )
        # Cost-adjusted TP < original TP (costs eat into TP)
        assert result.cost_adjusted_TP < 2030.0
        # Cost-adjusted SL > original SL (costs make SL worse)
        assert result.cost_adjusted_SL > 1990.0

    def test_12_sell_direction(self):
        engine = TransactionCostEngine("zero_spread_demo")
        result = engine.calculate(
            direction="SELL", entry_price=2000.0, sl_price=2010.0,
            tp_price=1970.0, lot=0.01, current_price=1970.0,
        )
        # gross_profit = (2000 - 1970) * 0.01 * 100 = 30.0
        assert result.gross_profit == pytest.approx(30.0, abs=0.01)
        assert result.net_profit < result.gross_profit

    def test_13_no_order_send(self):
        import re
        src = (REPO_ROOT / "titan" / "production" / "transaction_cost_engine.py").read_text()
        code = re.sub(r'"""[\s\S]*?"""', '""', src)
        code = re.sub(r'"(?:[^"\\]|\\.)*"', '""', code)
        assert not re.search(r"\bmt5\.order_send\s*\(", code)

    def test_14_no_martingale(self):
        import re
        src = (REPO_ROOT / "titan" / "production" / "transaction_cost_engine.py").read_text()
        code = re.sub(r'"""[\s\S]*?"""', '""', src).lower()
        for term in ["martingale", "grid_trade", "averaging_down", "loss_based_lot"]:
            assert term not in code

    def test_15_result_has_all_fields(self):
        engine = TransactionCostEngine("zero_spread_demo")
        result = engine.calculate(
            direction="BUY", entry_price=2000.0, sl_price=1990.0,
            tp_price=2030.0, lot=0.01, current_price=2030.0,
        )
        required = [
            "gross_profit", "spread_cost", "commission_cost", "slippage_cost",
            "swap_cost", "total_transaction_cost", "net_profit",
            "gross_R", "net_R", "gross_RR", "net_RR",
            "break_even_price_after_cost", "minimum_price_move_to_profit",
            "cost_adjusted_TP", "cost_adjusted_SL", "cost_adjusted_expectancy",
        ]
        for f in required:
            assert hasattr(result, f), f"Missing field: {f}"
