"""TITAN XAU AI — Sprint 9.9.3.30 SL Defense Engine Tests"""
from __future__ import annotations
import sys, inspect
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from titan.production.exit_defense_engine import (
    SLDefenseEngine, SLDefenseDecision, SLAction,
)


class TestSLDefenseEngine:
    def test_01_high_volatility_tightens_sl(self):
        eng = SLDefenseEngine()
        d = eng.evaluate(entry_price=2000, current_price=2010, current_sl=1995,
                         side="BUY", atr=5.0, regime="HIGH_VOLATILITY",
                         volatility_score=0.75)
        assert d.action == SLAction.TIGHTEN_SL
        assert d.risk_reduction_factor <= 0.5
        assert d.new_sl is not None

    def test_02_news_shock_emergency_exit(self):
        eng = SLDefenseEngine()
        d = eng.evaluate(entry_price=2000, current_price=2010, current_sl=1995,
                         side="BUY", atr=5.0, regime="NEWS_SHOCK")
        assert d.action == SLAction.EMERGENCY_EXIT
        assert d.allowed is False

    def test_03_liquidity_vacuum_emergency_exit(self):
        eng = SLDefenseEngine()
        d = eng.evaluate(entry_price=2000, current_price=2010, current_sl=1995,
                         side="BUY", atr=5.0, regime="LIQUIDITY_VACUUM")
        assert d.action == SLAction.EMERGENCY_EXIT

    def test_04_spread_expansion_emergency_exit(self):
        eng = SLDefenseEngine()
        d = eng.evaluate(entry_price=2000, current_price=2010, current_sl=1995,
                         side="BUY", atr=5.0, spread_score=0.9)
        assert d.action == SLAction.EMERGENCY_EXIT

    def test_05_spread_expansion_moderate_tightens(self):
        eng = SLDefenseEngine()
        d = eng.evaluate(entry_price=2000, current_price=2001, current_sl=1995,
                         side="BUY", atr=5.0, regime="TREND_UP", spread_score=0.65)
        assert d.action == SLAction.TIGHTEN_SL

    def test_06_breakeven_trigger(self):
        eng = SLDefenseEngine()
        d = eng.evaluate(entry_price=2000, current_price=2005, current_sl=1995,
                         side="BUY", atr=5.0, regime="TREND_UP")
        # r_multiple = (2005-2000)/5 = 1.0 → breakeven
        assert d.action == SLAction.MOVE_TO_BREAKEVEN
        assert d.new_sl == 2000

    def test_07_trailing_sl_never_widens(self):
        eng = SLDefenseEngine()
        # r=2 → trail at 1 ATR. For BUY, trail = 2010 - 5 = 2005 > current_sl 1995
        d = eng.evaluate(entry_price=2000, current_price=2010, current_sl=1995,
                         side="BUY", atr=5.0, regime="TREND_UP")
        assert d.action == SLAction.TRAIL_SL
        assert d.new_sl == 2005  # 2010 - 5
        assert d.new_sl > 1995  # tightened, not widened

    def test_08_unknown_regime_reduces_risk(self):
        eng = SLDefenseEngine()
        d = eng.evaluate(entry_price=2000, current_price=2003, current_sl=1995,
                         side="BUY", atr=5.0, regime="UNKNOWN")
        assert d.action == SLAction.TIGHTEN_SL
        assert d.risk_reduction_factor <= 0.5

    def test_09_stale_trade_emergency_exit(self):
        eng = SLDefenseEngine()
        d = eng.evaluate(entry_price=2000, current_price=2003, current_sl=1995,
                         side="BUY", atr=5.0, trade_age_seconds=7200,
                         max_trade_age_seconds=3600)
        assert d.action == SLAction.EMERGENCY_EXIT

    def test_10_mae_emergency_exit(self):
        eng = SLDefenseEngine()
        d = eng.evaluate(entry_price=2000, current_price=2003, current_sl=1995,
                         side="BUY", atr=5.0, max_adverse_excursion=12.0)
        # MAE 12/5 = 2.4R > 2R
        assert d.action == SLAction.EMERGENCY_EXIT

    def test_11_normal_hold(self):
        eng = SLDefenseEngine()
        d = eng.evaluate(entry_price=2000, current_price=2001, current_sl=1995,
                         side="BUY", atr=5.0, regime="TREND_UP")
        assert d.action == SLAction.HOLD

    def test_12_exception_fail_safe(self):
        eng = SLDefenseEngine()
        d = eng.evaluate(entry_price="invalid", current_price=2010,  # type: ignore
                         current_sl=1995, side="BUY", atr=5.0)
        assert d.action == SLAction.TIGHTEN_SL
        assert d.risk_reduction_factor <= 0.5

    def test_13_risk_reduction_never_above_1(self):
        d = SLDefenseDecision(risk_reduction_factor=2.0)
        assert d.risk_reduction_factor == 1.0

    def test_14_no_order_send_in_source(self):
        src = inspect.getsource(SLDefenseEngine)
        assert "order_send" not in src
        assert "mt5." not in src
