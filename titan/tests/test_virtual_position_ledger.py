"""
TITAN XAU AI — Sprint 9.8 Virtual Position Ledger Tests
"""
from __future__ import annotations
import pytest
from titan.production.virtual_position_ledger import (
    VirtualPositionLedger, VirtualPosition, VirtualPositionStatus,
    VirtualCloseReason,
)
from titan.production.trade_journal import TradeJournal


@pytest.fixture
def journal(tmp_path):
    return TradeJournal(path=str(tmp_path / "vpl.jsonl"), session_id="vpl_test")


@pytest.fixture
def ledger(journal):
    return VirtualPositionLedger(journal=journal)


class TestVirtualPositionOpen:
    def test_open_buy_position(self, ledger):
        pos = ledger.open_position(
            symbol="XAUUSD", direction="BUY", entry_price=2000.0,
            lot=0.01, sl=1990.0, tp=2020.0,
            signal_id="sig-1", decision_id="dec-1",
        )
        assert pos.direction == "BUY"
        assert pos.entry_price == 2000.0
        assert pos.status == VirtualPositionStatus.OPEN
        assert pos.initial_sl == 1990.0
        assert pos.initial_tp == 2020.0
        assert pos.lot == 0.01

    def test_open_sell_position(self, ledger):
        pos = ledger.open_position(
            symbol="XAUUSD", direction="SELL", entry_price=2000.0,
            lot=0.01, sl=2010.0, tp=1980.0,
        )
        assert pos.direction == "SELL"
        assert pos.status == VirtualPositionStatus.OPEN

    def test_duplicate_position_blocked(self, ledger):
        ledger.open_position(
            symbol="XAUUSD", direction="BUY", entry_price=2000.0,
            lot=0.01, sl=1990.0, tp=2020.0,
            idempotency_key="key-1",
        )
        with pytest.raises(ValueError, match="Duplicate"):
            ledger.open_position(
                symbol="XAUUSD", direction="BUY", entry_price=2000.0,
                lot=0.01, sl=1990.0, tp=2020.0,
                idempotency_key="key-1",
            )

    def test_open_count(self, ledger):
        assert ledger.open_count == 0
        ledger.open_position("XAUUSD", "BUY", 2000, 0.01, 1990, 2020)
        assert ledger.open_count == 1


class TestSLTPDetection:
    def test_buy_sl_hit(self, ledger):
        pos = ledger.open_position("XAUUSD", "BUY", 2000, 0.01, 1990, 2020)
        closed = ledger.update_positions(current_price=1989, high=1995, low=1988)
        assert pos.position_id in closed
        assert pos.status == VirtualPositionStatus.CLOSED
        assert pos.close_reason == "SL_HIT"
        assert pos.close_price == 1990.0

    def test_buy_tp_hit(self, ledger):
        pos = ledger.open_position("XAUUSD", "BUY", 2000, 0.01, 1990, 2020)
        closed = ledger.update_positions(current_price=2021, high=2021, low=2019)
        assert pos.position_id in closed
        assert pos.close_reason == "TP_HIT"
        assert pos.close_price == 2020.0

    def test_sell_sl_hit(self, ledger):
        pos = ledger.open_position("XAUUSD", "SELL", 2000, 0.01, 2010, 1980)
        closed = ledger.update_positions(current_price=2011, high=2012, low=2008)
        assert pos.position_id in closed
        assert pos.close_reason == "SL_HIT"

    def test_sell_tp_hit(self, ledger):
        pos = ledger.open_position("XAUUSD", "SELL", 2000, 0.01, 2010, 1980)
        closed = ledger.update_positions(current_price=1979, high=2001, low=1979)
        assert pos.position_id in closed
        assert pos.close_reason == "TP_HIT"

    def test_ambiguous_candle_conservative_sl(self, ledger):
        """Both SL and TP hit in same candle → conservative SL-first."""
        pos = ledger.open_position("XAUUSD", "BUY", 2000, 0.01, 1990, 2020)
        # Low touches SL, High touches TP
        closed = ledger.update_positions(current_price=2005, high=2021, low=1989)
        assert pos.position_id in closed
        assert pos.close_reason == "SL_HIT"  # conservative

    def test_no_hit_stays_open(self, ledger):
        pos = ledger.open_position("XAUUSD", "BUY", 2000, 0.01, 1990, 2020)
        closed = ledger.update_positions(current_price=2005, high=2008, low=2002)
        assert len(closed) == 0
        assert pos.status == VirtualPositionStatus.OPEN


class TestPnLCalculation:
    def test_buy_profit_pnl(self, ledger):
        pos = ledger.open_position("XAUUSD", "BUY", 2000, 0.01, 1990, 2020,
                                   spread_cost=0.30, commission_cost=0.30)
        ledger.update_positions(current_price=2020, high=2020, low=2005)
        # gross = (2020-2000) * 100 * 0.01 = 20.0
        assert pos.gross_pnl == pytest.approx(20.0, abs=0.01)
        # net = 20.0 - 0.30 - 0.30 = 19.40
        assert pos.net_pnl == pytest.approx(19.40, abs=0.01)

    def test_sell_profit_pnl(self, ledger):
        pos = ledger.open_position("XAUUSD", "SELL", 2000, 0.01, 2010, 1980,
                                   spread_cost=0.30, commission_cost=0.30)
        ledger.update_positions(current_price=1980, high=2005, low=1980)
        # gross = (2000-1980) * 100 * 0.01 = 20.0
        assert pos.gross_pnl == pytest.approx(20.0, abs=0.01)
        assert pos.net_pnl == pytest.approx(19.40, abs=0.01)

    def test_buy_loss_pnl(self, ledger):
        pos = ledger.open_position("XAUUSD", "BUY", 2000, 0.01, 1990, 2020,
                                   spread_cost=0.30, commission_cost=0.30)
        ledger.update_positions(current_price=1990, high=2005, low=1989)
        # gross = (1990-2000) * 100 * 0.01 = -10.0
        assert pos.gross_pnl == pytest.approx(-10.0, abs=0.01)
        # net = -10.0 - 0.30 - 0.30 = -10.60
        assert pos.net_pnl == pytest.approx(-10.60, abs=0.01)

    def test_r_multiple(self, ledger):
        pos = ledger.open_position("XAUUSD", "BUY", 2000, 0.01, 1990, 2020)
        ledger.update_positions(current_price=2020, high=2020, low=2005)
        # initial_risk = |2000-1990| * 100 * 0.01 = 10.0
        # gross = 20.0, R = 20.0/10.0 = 2.0
        assert pos.r_multiple == pytest.approx(2.0, abs=0.01)


class TestMFE_MAE:
    def test_mfe_updated_for_buy(self, ledger):
        pos = ledger.open_position("XAUUSD", "BUY", 2000, 0.01, 1990, 2020)
        ledger.update_positions(current_price=2005, high=2008, low=2002)
        assert pos.mfe > 0  # 2008-2000=8
        # low=2002 > entry=2000, so no adverse excursion for BUY
        assert pos.mae == 0  # no adverse excursion

    def test_mae_updated_for_buy(self, ledger):
        pos = ledger.open_position("XAUUSD", "BUY", 2000, 0.01, 1990, 2020)
        ledger.update_positions(current_price=1995, high=2002, low=1992)
        assert pos.mae > 0  # 2000-1992=8


class TestManualClose:
    def test_close_position(self, ledger):
        pos = ledger.open_position("XAUUSD", "BUY", 2000, 0.01, 1990, 2020)
        result = ledger.close_position(pos.position_id, 2010, "AI_EXIT_CLOSE")
        assert result is not None
        assert result.status == VirtualPositionStatus.CLOSED
        assert result.close_reason == "AI_EXIT_CLOSE"
        assert result.gross_pnl == pytest.approx(10.0, abs=0.01)

    def test_close_nonexistent(self, ledger):
        result = ledger.close_position("nonexistent", 2010, "AI_EXIT_CLOSE")
        assert result is None

    def test_close_already_closed(self, ledger):
        pos = ledger.open_position("XAUUSD", "BUY", 2000, 0.01, 1990, 2020)
        ledger.close_position(pos.position_id, 2010, "AI_EXIT_CLOSE")
        result = ledger.close_position(pos.position_id, 2015, "AI_EXIT_CLOSE")
        assert result is None


class TestJournalEvents:
    def test_open_event_journaled(self, ledger, journal):
        ledger.open_position("XAUUSD", "BUY", 2000, 0.01, 1990, 2020)
        records = journal.read_all()
        opened = [r for r in records if "VIRTUAL_POSITION_OPENED" in str(r.get("data", {}))]
        assert len(opened) >= 1

    def test_close_event_journaled(self, ledger, journal):
        pos = ledger.open_position("XAUUSD", "BUY", 2000, 0.01, 1990, 2020)
        ledger.close_position(pos.position_id, 2010, "AI_EXIT_CLOSE")
        records = journal.read_all()
        closed = [r for r in records if "VIRTUAL_POSITION_CLOSED" in str(r.get("data", {}))]
        assert len(closed) >= 1
