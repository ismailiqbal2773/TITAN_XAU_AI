"""
TITAN XAU AI — Sprint 9.8.1 Virtual Lifecycle Validator Tests (Fixed DD)
"""
from __future__ import annotations
import pytest
from titan.production.virtual_position_ledger import VirtualPositionLedger, VirtualPositionStatus
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


# ── DD normalization tests ──────────────────────────────────────────────────
class TestDDNormalization:
    def test_dd_uses_starting_equity_not_zero(self):
        """DD must be calculated from 6000 equity, not 0."""
        from scripts.audit.virtual_lifecycle_validator import compute_metrics, DEFAULT_START_EQUITY

        class FakePos:
            def __init__(self, net_pnl, gross_pnl=0, r_multiple=0, holding_seconds=0,
                         mfe=0, mae=0, spread_cost=0, commission_cost=0, slippage_cost=0, swap_cost=0):
                self.net_pnl = net_pnl
                self.gross_pnl = gross_pnl
                self.r_multiple = r_multiple
                self.holding_seconds = holding_seconds
                self.mfe = mfe
                self.mae = mae
                self.spread_cost = spread_cost
                self.commission_cost = commission_cost
                self.slippage_cost = slippage_cost
                self.swap_cost = swap_cost

        # Win 10, then lose 5 → DD should be tiny relative to 6000
        positions = [FakePos(net_pnl=10), FakePos(net_pnl=-5)]
        m = compute_metrics(positions, DEFAULT_START_EQUITY)
        # equity goes 6000→6010→6005, peak=6010, dd=(6010-6005)/6010=0.083%
        assert m["max_drawdown_pct_of_start_equity"] < 1.0  # not 50%+
        assert m["max_drawdown_pct_of_peak_equity"] < 1.0

    def test_dd_realistic_with_6000_equity(self):
        from scripts.audit.virtual_lifecycle_validator import compute_metrics
        class P:
            net_pnl = -20; gross_pnl = -20; r_multiple = -1; holding_seconds = 3600
            mfe = 0; mae = 20; spread_cost = 0.3; commission_cost = 0.3; slippage_cost = 2.0; swap_cost = 0
        m = compute_metrics([P()], 6000)
        # equity = 6000 - 20 = 5980, dd = 20/6000 = 0.33%
        assert m["max_drawdown_pct_of_start_equity"] < 1.0


# ── Normal vs stress separation ─────────────────────────────────────────────
class TestScenarioSeparation:
    def test_normal_scenarios_classified(self):
        from scripts.audit.virtual_lifecycle_validator import NORMAL_SCENARIOS
        assert "BUY_TP" in NORMAL_SCENARIOS
        assert "BUY_SL" in NORMAL_SCENARIOS
        assert "AMBIGUOUS_CANDLE" not in NORMAL_SCENARIOS

    def test_stress_scenarios_classified(self):
        from scripts.audit.virtual_lifecycle_validator import STRESS_SCENARIOS
        assert "AMBIGUOUS_CANDLE" in STRESS_SCENARIOS
        assert "HIGH_VOLATILITY" in STRESS_SCENARIOS
        assert "BUY_TP" not in STRESS_SCENARIOS

    def test_stress_dd_does_not_hide_risk(self):
        from scripts.audit.virtual_lifecycle_validator import compute_metrics
        class P:
            net_pnl = -50; gross_pnl = -50; r_multiple = -2; holding_seconds = 3600
            mfe = 0; mae = 50; spread_cost = 0.5; commission_cost = 0.3; slippage_cost = 5.0; swap_cost = 0
        m = compute_metrics([P()], 6000)
        assert m["max_drawdown_usd"] > 0
        assert m["max_drawdown_pct_of_start_equity"] > 0


# ── Scenario matrix (from Sprint 9.8) ───────────────────────────────────────
class TestScenarioMatrix:
    def _run(self, ledger, direction, entry, sl, tp, high, low, close, expected):
        pos = ledger.open_position("XAUUSD", direction, entry, 0.01, sl, tp)
        closed = ledger.update_positions(current_price=close, high=high, low=low)
        if expected:
            assert pos.close_reason == expected
        return pos

    def test_01_buy_tp(self, ledger): self._run(ledger, "BUY", 2000, 1990, 2020, 2021, 2005, 2020, "TP_HIT")
    def test_02_buy_sl(self, ledger): self._run(ledger, "BUY", 2000, 1990, 2020, 2005, 1989, 1990, "SL_HIT")
    def test_03_sell_tp(self, ledger): self._run(ledger, "SELL", 2000, 2010, 1980, 2005, 1979, 1980, "TP_HIT")
    def test_04_sell_sl(self, ledger): self._run(ledger, "SELL", 2000, 2010, 1980, 2011, 1995, 2010, "SL_HIT")

    def test_05_buy_ai_exit(self, ledger):
        pos = ledger.open_position("XAUUSD", "BUY", 2000, 0.01, 1990, 2020)
        ledger.close_position(pos.position_id, 2010, "AI_EXIT_CLOSE")
        assert pos.close_reason == "AI_EXIT_CLOSE"

    def test_14_high_vol_both_hit(self, ledger):
        pos = ledger.open_position("XAUUSD", "BUY", 2000, 0.01, 1990, 2020)
        closed = ledger.update_positions(current_price=2005, high=2025, low=1985)
        assert pos.close_reason == "SL_HIT"

    def test_23_duplicate_blocked(self, ledger):
        ledger.open_position("XAUUSD", "BUY", 2000, 0.01, 1990, 2020, idempotency_key="k1")
        with pytest.raises(ValueError):
            ledger.open_position("XAUUSD", "BUY", 2000, 0.01, 1990, 2020, idempotency_key="k1")

    def test_25_no_order_send(self, ledger):
        import titan.production.virtual_position_ledger as vpl
        import inspect
        src = inspect.getsource(vpl)
        assert "import MetaTrader5" not in src
        assert "mt5.order_send" not in src


# ── Metrics tests ───────────────────────────────────────────────────────────
class TestMetrics:
    def test_multiple_positions(self, ledger):
        for _ in range(5):
            ledger.open_position("XAUUSD", "BUY", 2000, 0.01, 1990, 2020)
            ledger.update_positions(current_price=2020, high=2020, low=2005)
        assert len(ledger.get_closed_positions()) == 5

    def test_mixed_win_loss(self, ledger):
        ledger.open_position("XAUUSD", "BUY", 2000, 0.01, 1990, 2020)
        ledger.update_positions(current_price=2020, high=2020, low=2005)
        ledger.open_position("XAUUSD", "BUY", 2000, 0.01, 1990, 2020)
        ledger.update_positions(current_price=1990, high=2005, low=1989)
        closed = ledger.get_closed_positions()
        wins = [p for p in closed if p.gross_pnl > 0]
        assert len(wins) == 1
