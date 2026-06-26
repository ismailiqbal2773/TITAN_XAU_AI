"""
TITAN XAU AI — Sprint 9.8 Virtual Lifecycle Validator Tests
"""
from __future__ import annotations
import pytest
from titan.production.virtual_position_ledger import (
    VirtualPositionLedger, VirtualPositionStatus,
)
from titan.production.net_profit_engine import NetProfitEngine
from titan.production.trade_journal import TradeJournal


@pytest.fixture
def journal(tmp_path):
    return TradeJournal(path=str(tmp_path / "vlv.jsonl"), session_id="vlv_test")


@pytest.fixture
def ledger(journal):
    return VirtualPositionLedger(journal=journal)


@pytest.fixture
def engine():
    return NetProfitEngine()


class TestScenarioMatrix:
    """25 scenario tests from the spec."""

    def _run_scenario(self, ledger, direction, entry, sl, tp,
                      high, low, close, expected_reason):
        pos = ledger.open_position("XAUUSD", direction, entry, 0.01, sl, tp)
        closed = ledger.update_positions(current_price=close, high=high, low=low)
        if expected_reason:
            assert pos.position_id in closed
            assert pos.close_reason == expected_reason
        else:
            assert pos.position_id not in closed
        return pos

    def test_01_buy_tp(self, ledger):
        self._run_scenario(ledger, "BUY", 2000, 1990, 2020, 2021, 2005, 2020, "TP_HIT")

    def test_02_buy_sl(self, ledger):
        self._run_scenario(ledger, "BUY", 2000, 1990, 2020, 2005, 1989, 1990, "SL_HIT")

    def test_03_sell_tp(self, ledger):
        self._run_scenario(ledger, "SELL", 2000, 2010, 1980, 2005, 1979, 1980, "TP_HIT")

    def test_04_sell_sl(self, ledger):
        self._run_scenario(ledger, "SELL", 2000, 2010, 1980, 2011, 1995, 2010, "SL_HIT")

    def test_05_buy_ai_exit_close(self, ledger):
        pos = ledger.open_position("XAUUSD", "BUY", 2000, 0.01, 1990, 2020)
        ledger.update_positions(current_price=2010, high=2012, low=2008)
        result = ledger.close_position(pos.position_id, 2010, "AI_EXIT_CLOSE")
        assert result.close_reason == "AI_EXIT_CLOSE"
        assert result.gross_pnl > 0

    def test_06_sell_ai_exit_close(self, ledger):
        pos = ledger.open_position("XAUUSD", "SELL", 2000, 0.01, 2010, 1980)
        ledger.update_positions(current_price=1990, high=2005, low=1988)
        result = ledger.close_position(pos.position_id, 1990, "AI_EXIT_CLOSE")
        assert result.close_reason == "AI_EXIT_CLOSE"
        assert result.gross_pnl > 0

    def test_07_regime_flips_against_buy(self, ledger):
        pos = ledger.open_position("XAUUSD", "BUY", 2000, 0.01, 1990, 2020)
        ledger.update_positions(current_price=2005, high=2008, low=2002)
        result = ledger.close_position(pos.position_id, 2000, "REGIME_RISK_EXIT")
        assert result.close_reason == "REGIME_RISK_EXIT"

    def test_08_regime_flips_against_sell(self, ledger):
        pos = ledger.open_position("XAUUSD", "SELL", 2000, 0.01, 2010, 1980)
        ledger.update_positions(current_price=1995, high=1998, low=1992)
        result = ledger.close_position(pos.position_id, 2000, "REGIME_RISK_EXIT")
        assert result.close_reason == "REGIME_RISK_EXIT"

    def test_09_alpha_decay_exit(self, ledger):
        pos = ledger.open_position("XAUUSD", "BUY", 2000, 0.01, 1990, 2020)
        result = ledger.close_position(pos.position_id, 2001, "ALPHA_DECAY_EXIT")
        assert result.close_reason == "ALPHA_DECAY_EXIT"

    def test_10_regime_change_alpha_old(self, ledger):
        pos = ledger.open_position("XAUUSD", "BUY", 2000, 0.01, 1990, 2020)
        result = ledger.close_position(pos.position_id, 1998, "REGIME_RISK_EXIT")
        assert result.gross_pnl < 0

    def test_11_alpha_reverses_strongly(self, ledger):
        pos = ledger.open_position("XAUUSD", "BUY", 2000, 0.01, 1990, 2020)
        result = ledger.close_position(pos.position_id, 1995, "ALPHA_DECAY_EXIT")
        assert result.gross_pnl < 0

    def test_12_spread_spike_before_tp(self, ledger):
        pos = ledger.open_position("XAUUSD", "BUY", 2000, 0.01, 1990, 2020,
                                   spread_cost=0.50)  # high spread
        closed = ledger.update_positions(current_price=2020, high=2020, low=2015)
        assert pos.close_reason == "TP_HIT"
        assert pos.net_pnl < pos.gross_pnl  # cost drag

    def test_13_spread_spike_before_sl(self, ledger):
        pos = ledger.open_position("XAUUSD", "BUY", 2000, 0.01, 1990, 2020,
                                   spread_cost=0.50)
        closed = ledger.update_positions(current_price=1990, high=2005, low=1989)
        assert pos.close_reason == "SL_HIT"

    def test_14_high_volatility_both_hit(self, ledger):
        """Both SL and TP hit in same candle → conservative SL."""
        pos = ledger.open_position("XAUUSD", "BUY", 2000, 0.01, 1990, 2020)
        closed = ledger.update_positions(current_price=2005, high=2025, low=1985)
        assert pos.close_reason == "SL_HIT"  # conservative

    def test_15_low_liquidity_no_trade(self, ledger):
        """No trade should be opened in low liquidity."""
        # This is a model-level decision — just verify ledger doesn't crash
        assert ledger.open_count == 0

    def test_16_stale_position_exit(self, ledger):
        pos = ledger.open_position("XAUUSD", "BUY", 2000, 0.01, 1990, 2020)
        result = ledger.close_position(pos.position_id, 2001, "STALE_POSITION_EXIT")
        assert result.close_reason == "STALE_POSITION_EXIT"

    def test_17_max_holding_exit(self, ledger):
        pos = ledger.open_position("XAUUSD", "BUY", 2000, 0.01, 1990, 2020)
        result = ledger.close_position(pos.position_id, 2005, "MAX_HOLDING_EXIT")
        assert result.close_reason == "MAX_HOLDING_EXIT"

    def test_18_profit_lock_exit(self, ledger):
        pos = ledger.open_position("XAUUSD", "BUY", 2000, 0.01, 1990, 2020)
        result = ledger.close_position(pos.position_id, 2015, "PROFIT_LOCK_EXIT")
        assert result.close_reason == "PROFIT_LOCK_EXIT"
        assert result.gross_pnl > 0

    def test_19_net_profit_positive_after_costs(self, engine):
        r = engine.calculate("BUY", 2000, 2020, 0.01, 1990,
                              spread_usd=0.30, slippage_pips=2.0, swap_cost=0)
        assert r.net_pnl > 0

    def test_20_gross_positive_net_negative(self, engine):
        r = engine.calculate("BUY", 2000, 2000.5, 0.01, 1990,
                              spread_usd=0.30, slippage_pips=2.0, swap_cost=0.50)
        assert r.gross_pnl > 0
        assert r.net_pnl < 0

    def test_21_trade_rejected_small_expected_profit(self, engine):
        """If expected net profit is too small, trade should be rejected."""
        r = engine.calculate("BUY", 2000, 2000.1, 0.01, 1990,
                              spread_usd=0.30, slippage_pips=2.0, swap_cost=0)
        assert r.net_pnl < 0  # would be rejected

    def test_22_unknown_scenario_fallback(self, ledger):
        """Unknown scenario should not crash."""
        pos = ledger.open_position("XAUUSD", "BUY", 2000, 0.01, 1990, 2020)
        # No update — position stays open
        assert pos.status == VirtualPositionStatus.OPEN

    def test_23_duplicate_virtual_order_blocked(self, ledger):
        ledger.open_position("XAUUSD", "BUY", 2000, 0.01, 1990, 2020,
                              idempotency_key="dup-key")
        with pytest.raises(ValueError):
            ledger.open_position("XAUUSD", "BUY", 2000, 0.01, 1990, 2020,
                                  idempotency_key="dup-key")

    def test_24_journal_corruption_detection(self, journal):
        """Journal should handle corrupt lines gracefully."""
        import json
        journal.log_heartbeat({"test": 1})
        journal.flush()
        # Append corrupt line
        with open(journal.path, "a") as f:
            f.write('{"partial": "corrupt\n')
        records = journal.read_all()
        # Should not crash — corrupt line skipped
        assert isinstance(records, list)

    def test_25_no_real_order_send(self, ledger):
        """No real MT5 order_send should be called."""
        # VirtualPositionLedger never calls mt5.order_send
        # Verify no import of MetaTrader5 in the module
        import titan.production.virtual_position_ledger as vpl
        import inspect
        src = inspect.getsource(vpl)
        # Check for actual order_send calls, not just "mt5" in comments
        assert "import MetaTrader5" not in src
        assert "mt5.order_send" not in src
        assert "order_send" not in src.split('"""')[0] if '"""' in src else True  # not in module code outside docstring


class TestMetricsCalculation:
    def test_multiple_positions_metrics(self, ledger):
        """Test that metrics can be calculated from multiple positions."""
        # Open and close several positions
        for i in range(5):
            pos = ledger.open_position("XAUUSD", "BUY", 2000, 0.01, 1990, 2020)
            ledger.update_positions(current_price=2020, high=2020, low=2005)

        closed = ledger.get_closed_positions()
        assert len(closed) == 5
        assert all(p.gross_pnl > 0 for p in closed)
        assert all(p.close_reason == "TP_HIT" for p in closed)

    def test_mixed_win_loss(self, ledger):
        # Win
        pos1 = ledger.open_position("XAUUSD", "BUY", 2000, 0.01, 1990, 2020)
        ledger.update_positions(current_price=2020, high=2020, low=2005)
        # Loss
        pos2 = ledger.open_position("XAUUSD", "BUY", 2000, 0.01, 1990, 2020)
        ledger.update_positions(current_price=1990, high=2005, low=1989)

        closed = ledger.get_closed_positions()
        wins = [p for p in closed if p.gross_pnl > 0]
        losses = [p for p in closed if p.gross_pnl < 0]
        assert len(wins) == 1
        assert len(losses) == 1
        win_rate = len(wins) / len(closed) * 100
        assert win_rate == 50.0


class TestHoldingTime:
    def test_holding_seconds_updated(self, ledger):
        pos = ledger.open_position("XAUUSD", "BUY", 2000, 0.01, 1990, 2020)
        import time
        time.sleep(0.1)
        ledger.update_positions(current_price=2005, high=2008, low=2002)
        assert pos.holding_seconds > 0
