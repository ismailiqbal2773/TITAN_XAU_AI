"""TITAN XAU AI - Sprint 9.9.3.45.8.3 Trade Reconciliation Tests"""
from __future__ import annotations
import sys
from pathlib import Path
import pytest
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from titan.production.demo_micro_trade_reconciliation import (
    reconcile_trade, TradeReconciliation,
    STATUS_OPEN, STATUS_CLOSED_TP, STATUS_CLOSED_SL,
    STATUS_CLOSED_MANUAL, STATUS_CLOSED_UNKNOWN,
    STATUS_PENDING_HISTORY, STATUS_UNKNOWN,
)


class TestTradeReconciliation:
    def test_01_reconciliation_imports(self):
        assert reconcile_trade is not None
        assert TradeReconciliation is not None

    def test_02_canonical_statuses(self):
        assert STATUS_OPEN == "OPEN"
        assert STATUS_CLOSED_TP == "CLOSED_TP"
        assert STATUS_CLOSED_SL == "CLOSED_SL"
        assert STATUS_CLOSED_MANUAL == "CLOSED_MANUAL"
        assert STATUS_CLOSED_UNKNOWN == "CLOSED_UNKNOWN"
        assert STATUS_PENDING_HISTORY == "PENDING_HISTORY"
        assert STATUS_UNKNOWN == "UNKNOWN"

    def test_03_open_position_detected(self):
        """Position in open_positions should return OPEN."""
        class FakePosition:
            ticket = 12345
            price_open = 2000.0
            price_current = 2005.0
        result = reconcile_trade(
            position_ticket=12345,
            open_positions=[FakePosition()],
            entry_price=2000.0,
        )
        assert result.status == STATUS_OPEN
        assert result.has_closing_deal is False

    def test_04_closed_tp_detected(self):
        """Close deal at TP price should return CLOSED_TP."""
        class FakeCloseDeal:
            ticket = 50001
            position_id = 12345
            entry = 1  # DEAL_ENTRY_OUT
            price = 2030.0
            time = 1700000000
            comment = ""
            profit = 30.0
        result = reconcile_trade(
            position_ticket=12345,
            open_positions=[],
            history_deals=[FakeCloseDeal()],
            entry_price=2000.0,
            initial_sl=1990.0,
            initial_tp=2030.0,
        )
        assert result.status == STATUS_CLOSED_TP
        assert result.has_closing_deal is True

    def test_05_closed_sl_detected(self):
        """Close deal at SL price should return CLOSED_SL."""
        class FakeCloseDeal:
            ticket = 50002
            position_id = 12345
            entry = 1
            price = 1990.0
            time = 1700000000
            comment = "[sl 1990.0]"
            profit = -10.0
        result = reconcile_trade(
            position_ticket=12345,
            open_positions=[],
            history_deals=[FakeCloseDeal()],
            entry_price=2000.0,
            initial_sl=1990.0,
            initial_tp=2030.0,
        )
        assert result.status == STATUS_CLOSED_SL

    def test_06_pending_history_when_no_deals(self):
        """No open position and no history deals should return PENDING_HISTORY."""
        result = reconcile_trade(
            position_ticket=12345,
            open_positions=[],
            history_deals=[],
        )
        assert result.status == STATUS_PENDING_HISTORY

    def test_07_closed_requires_closing_deal(self):
        """Closed status must require has_closing_deal=True."""
        class FakeCloseDeal:
            ticket = 50001
            position_id = 12345
            entry = 1
            price = 2030.0
            time = 1700000000
            comment = ""
            profit = 30.0
        result = reconcile_trade(
            position_ticket=12345,
            open_positions=[],
            history_deals=[FakeCloseDeal()],
            entry_price=2000.0,
            initial_tp=2030.0,
        )
        if result.status.startswith("CLOSED"):
            assert result.has_closing_deal is True

    def test_08_net_profit_computed(self):
        """Net profit must be computed for closed trades."""
        class FakeCloseDeal:
            ticket = 50001
            position_id = 12345
            entry = 1
            price = 2030.0
            time = 1700000000
            comment = ""
            profit = 30.0
        result = reconcile_trade(
            position_ticket=12345,
            open_positions=[],
            history_deals=[FakeCloseDeal()],
            entry_price=2000.0,
            initial_sl=1990.0,
            initial_tp=2030.0,
            lot=0.01,
            contract_size=100.0,
            spread=0.35,
            commission_per_lot=7.0,
            slippage=0.02,
        )
        assert result.net_profit < result.gross_profit  # Net less than gross

    def test_09_gross_RR_and_net_RR_computed(self):
        """Gross RR and net RR must be computed for closed trades."""
        class FakeCloseDeal:
            ticket = 50001
            position_id = 12345
            entry = 1
            price = 2030.0
            time = 1700000000
            comment = ""
            profit = 30.0
        result = reconcile_trade(
            position_ticket=12345,
            open_positions=[],
            history_deals=[FakeCloseDeal()],
            entry_price=2000.0,
            initial_sl=1990.0,
            initial_tp=2030.0,
            lot=0.01,
            contract_size=100.0,
        )
        assert result.gross_RR > 0
        assert result.net_RR > 0

    def test_10_no_order_send(self):
        import re
        src = (REPO_ROOT / "titan" / "production" / "demo_micro_trade_reconciliation.py").read_text()
        code = re.sub(r'"""[\s\S]*?"""', '""', src)
        code = re.sub(r'"(?:[^"\\]|\\.)*"', '""', code)
        assert not re.search(r"\bmt5\.order_send\s*\(", code)

    def test_11_no_martingale(self):
        import re
        src = (REPO_ROOT / "titan" / "production" / "demo_micro_trade_reconciliation.py").read_text()
        code = re.sub(r'"""[\s\S]*?"""', '""', src).lower()
        for term in ["martingale", "grid_trade", "averaging_down", "loss_based_lot"]:
            assert term not in code

    def test_12_result_has_all_fields(self):
        result = reconcile_trade(
            position_ticket=12345,
            open_positions=[],
            history_deals=[],
        )
        required = [
            "status", "entry_deal_ticket", "close_deal_ticket", "position_id",
            "entry_price", "close_price", "gross_profit", "net_profit",
            "gross_R", "net_R", "gross_RR", "net_RR",
            "sl_modify_events", "tp_modify_events",
            "has_closing_deal", "has_entry_deal",
        ]
        for f in required:
            assert hasattr(result, f), f"Missing field: {f}"
