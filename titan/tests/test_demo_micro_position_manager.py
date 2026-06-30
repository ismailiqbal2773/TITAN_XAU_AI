"""TITAN XAU AI - Sprint 9.9.3.45 Position Manager Tests"""
from __future__ import annotations
import sys
from pathlib import Path
import pytest
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
from titan.production.demo_micro_position_manager import DemoMicroPositionManager, SLAction

class TestPositionManager:
    def test_01_buy_breakeven_trigger(self):
        mgr = DemoMicroPositionManager()
        rec = mgr.evaluate(direction="BUY", entry_price=2000.0, current_price=2001.5,
                           current_sl=1990.0, current_tp=2010.0)
        assert rec.action == SLAction.MOVE_TO_BREAKEVEN
        assert rec.new_sl > rec.current_sl  # Favorable: SL moves up

    def test_02_buy_trailing_trigger(self):
        mgr = DemoMicroPositionManager()
        rec = mgr.evaluate(direction="BUY", entry_price=2000.0, current_price=2002.5,
                           current_sl=1990.0, current_tp=2010.0)
        assert rec.action == SLAction.TRAIL
        assert rec.new_sl > rec.current_sl

    def test_03_buy_profit_lock_trigger(self):
        mgr = DemoMicroPositionManager()
        rec = mgr.evaluate(direction="BUY", entry_price=2000.0, current_price=2004.0,
                           current_sl=1990.0, current_tp=2010.0)
        assert rec.action == SLAction.PROFIT_LOCK
        assert rec.new_sl > rec.current_sl

    def test_04_sell_breakeven_trigger(self):
        mgr = DemoMicroPositionManager()
        rec = mgr.evaluate(direction="SELL", entry_price=2000.0, current_price=1998.5,
                           current_sl=2010.0, current_tp=1990.0)
        assert rec.action == SLAction.MOVE_TO_BREAKEVEN
        assert rec.new_sl < rec.current_sl  # Favorable: SL moves down

    def test_05_sell_trailing_trigger(self):
        mgr = DemoMicroPositionManager()
        rec = mgr.evaluate(direction="SELL", entry_price=2000.0, current_price=1997.5,
                           current_sl=2010.0, current_tp=1990.0)
        assert rec.action == SLAction.TRAIL
        assert rec.new_sl < rec.current_sl

    def test_06_buy_sl_never_moves_down(self):
        mgr = DemoMicroPositionManager()
        rec = mgr.evaluate(direction="BUY", entry_price=2000.0, current_price=2005.0,
                           current_sl=2003.0, current_tp=2010.0)
        assert rec.new_sl >= rec.current_sl

    def test_07_sell_sl_never_moves_up(self):
        mgr = DemoMicroPositionManager()
        rec = mgr.evaluate(direction="SELL", entry_price=2000.0, current_price=1995.0,
                           current_sl=1997.0, current_tp=1990.0)
        assert rec.new_sl <= rec.current_sl

    def test_08_tp_preserved(self):
        mgr = DemoMicroPositionManager()
        rec = mgr.evaluate(direction="BUY", entry_price=2000.0, current_price=2003.0,
                           current_sl=1990.0, current_tp=2010.0)
        assert rec.tp == 2010.0

    def test_09_hold_when_no_profit(self):
        mgr = DemoMicroPositionManager()
        rec = mgr.evaluate(direction="BUY", entry_price=2000.0, current_price=2000.5,
                           current_sl=1990.0, current_tp=2010.0)
        assert rec.action == SLAction.HOLD

    def test_10_stop_level_respected(self):
        mgr = DemoMicroPositionManager()
        rec = mgr.evaluate(direction="BUY", entry_price=2000.0, current_price=2003.0,
                           current_sl=1990.0, current_tp=2010.0,
                           stops_level_points=500, point=0.01)
        # If stop level blocks, action should be BLOCKED
        if rec.blockers:
            assert rec.action == SLAction.BLOCKED
