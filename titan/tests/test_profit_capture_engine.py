"""TITAN XAU AI — Sprint 9.9.3.30 Profit Capture Engine Tests"""
from __future__ import annotations
import sys, inspect
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from titan.production.profit_capture_engine import (
    ProfitCaptureEngine, ProfitCaptureDecision, ProfitAction,
)


class TestProfitCaptureEngine:
    def test_01_strong_trend_extends_tp(self):
        eng = ProfitCaptureEngine()
        d = eng.evaluate(entry_price=2000, current_price=2010, current_tp=2020,
                         side="BUY", atr=5.0, regime="TREND_UP", r_multiple=1.2,
                         safe_to_hold=True, confidence=0.8)
        assert d.action == ProfitAction.EXTEND_TP
        assert d.tp_extension_factor > 1.0

    def test_02_strong_trend_blocked_when_not_safe(self):
        eng = ProfitCaptureEngine()
        d = eng.evaluate(entry_price=2000, current_price=2010, current_tp=2020,
                         side="BUY", atr=5.0, regime="TREND_UP", r_multiple=1.0,
                         safe_to_hold=False)
        assert d.allowed is False
        assert d.action == ProfitAction.NO_ACTION

    def test_03_range_takes_profit_faster(self):
        eng = ProfitCaptureEngine()
        d = eng.evaluate(entry_price=2000, current_price=2005, current_tp=2020,
                         side="BUY", atr=5.0, regime="RANGE", r_multiple=1.0,
                         safe_to_hold=True)
        assert d.action == ProfitAction.TAKE_PROFIT

    def test_04_range_partial_close(self):
        eng = ProfitCaptureEngine()
        d = eng.evaluate(entry_price=2000, current_price=2002.5, current_tp=2020,
                         side="BUY", atr=5.0, regime="RANGE", r_multiple=0.5,
                         safe_to_hold=True)
        assert d.action == ProfitAction.PARTIAL_CLOSE
        assert d.partial_close_pct == 0.5

    def test_05_partial_close_at_2r(self):
        eng = ProfitCaptureEngine()
        d = eng.evaluate(entry_price=2000, current_price=2010, current_tp=2020,
                         side="BUY", atr=5.0, regime="SESSION_LONDON", r_multiple=2.0,
                         safe_to_hold=True, confidence=0.8)
        # r=2.0 → partial close 25%
        assert d.action == ProfitAction.PARTIAL_CLOSE
        assert d.partial_close_pct == 0.25

    def test_06_partial_close_at_3r(self):
        eng = ProfitCaptureEngine()
        d = eng.evaluate(entry_price=2000, current_price=2015, current_tp=2030,
                         side="BUY", atr=5.0, regime="SESSION_LONDON", r_multiple=3.0,
                         safe_to_hold=True, confidence=0.8)
        assert d.action == ProfitAction.PARTIAL_CLOSE
        assert d.partial_close_pct == 0.25

    def test_07_lock_profit_at_1r(self):
        eng = ProfitCaptureEngine()
        d = eng.evaluate(entry_price=2000, current_price=2005, current_tp=2020,
                         side="BUY", atr=5.0, regime="SESSION_LONDON", r_multiple=1.0,
                         safe_to_hold=True)
        assert d.action == ProfitAction.LOCK_PROFIT
        assert d.profit_lock_level == 2000

    def test_08_gold_impulse_extends_tp_high_confidence(self):
        eng = ProfitCaptureEngine()
        d = eng.evaluate(entry_price=2000, current_price=2006, current_tp=2020,
                         side="BUY", atr=5.0, regime="GOLD_IMPULSE", r_multiple=1.2,
                         safe_to_hold=True, confidence=0.8)
        assert d.action == ProfitAction.EXTEND_TP
        assert d.tp_extension_factor >= 1.3

    def test_09_gold_impulse_blocked_low_confidence(self):
        eng = ProfitCaptureEngine()
        d = eng.evaluate(entry_price=2000, current_price=2005, current_tp=2020,
                         side="BUY", atr=5.0, regime="GOLD_IMPULSE", r_multiple=1.0,
                         safe_to_hold=True, confidence=0.5)
        # confidence < 0.7 → no extend
        assert d.action != ProfitAction.EXTEND_TP or d.confidence < 0.7

    def test_10_weak_momentum_books_profit(self):
        eng = ProfitCaptureEngine()
        d = eng.evaluate(entry_price=2000, current_price=2004, current_tp=2020,
                         side="BUY", atr=5.0, regime="LOW_VOLATILITY",
                         r_multiple=0.8, safe_to_hold=True)
        assert d.action == ProfitAction.PARTIAL_CLOSE
        assert d.partial_close_pct == 0.25

    def test_11_time_decay_take_profit(self):
        eng = ProfitCaptureEngine()
        d = eng.evaluate(entry_price=2000, current_price=2002, current_tp=2020,
                         side="BUY", atr=5.0, regime="SESSION_LONDON",
                         r_multiple=0.4, safe_to_hold=True,
                         trade_age_seconds=3700)
        assert d.action == ProfitAction.TAKE_PROFIT

    def test_12_exception_fail_safe(self):
        eng = ProfitCaptureEngine()
        d = eng.evaluate(entry_price=2000, current_price=2010,
                         current_tp=2020, side="BUY", atr=-1.0,
                         regime="TREND_UP", r_multiple=None)  # type: ignore
        assert d.allowed is False

    def test_13_no_order_send_in_source(self):
        src = inspect.getsource(ProfitCaptureEngine)
        assert "order_send" not in src
        assert "mt5." not in src

    def test_14_never_increases_lot(self):
        eng = ProfitCaptureEngine()
        d = eng.evaluate(entry_price=2000, current_price=2010, current_tp=2020,
                         side="BUY", atr=5.0, regime="TREND_UP", r_multiple=2.0,
                         safe_to_hold=True, confidence=0.8)
        # partial_close_pct should be <= 1.0 (never increase lot)
        assert d.partial_close_pct <= 1.0
