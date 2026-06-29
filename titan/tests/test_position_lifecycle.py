"""TITAN XAU AI — Sprint 9.9.3.31 Position Lifecycle Tests"""
from __future__ import annotations
import sys
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from titan.production.position_lifecycle import (
    PositionState, PositionSnapshot, PositionLifecycleStatus,
    PositionLifecycleEngine, STALE_POSITION_THRESHOLD,
)


class TestPositionLifecycle:
    def test_01_new_position(self):
        eng = PositionLifecycleEngine()
        snap = PositionSnapshot(entry_price=2000, current_price=2000.5,
                                 current_sl=1995, initial_sl=1995, ticket=1001, age_seconds=10)
        status = eng.evaluate(snap)
        assert status.state == PositionState.NEW

    def test_02_open_position(self):
        eng = PositionLifecycleEngine()
        snap = PositionSnapshot(entry_price=2000, current_price=1999,
                                 current_sl=1995, initial_sl=1995, ticket=1001, age_seconds=120,
                                 pnl_r=-0.2)
        status = eng.evaluate(snap)
        assert status.state == PositionState.OPEN

    def test_03_in_profit(self):
        eng = PositionLifecycleEngine()
        snap = PositionSnapshot(entry_price=2000, current_price=2005,
                                 current_sl=1995, ticket=1001, age_seconds=300,
                                 pnl_r=1.0)
        status = eng.evaluate(snap)
        assert status.state == PositionState.IN_PROFIT

    def test_04_at_breakeven(self):
        eng = PositionLifecycleEngine()
        snap = PositionSnapshot(entry_price=2000, current_price=2005,
                                 current_sl=2000, initial_sl=1995,
                                 ticket=1001, age_seconds=300, atr=5.0,
                                 pnl_r=1.0)
        status = eng.evaluate(snap)
        assert status.state == PositionState.AT_BREAKEVEN
        assert status.protection_level == "BREAKEVEN"

    def test_05_trailing(self):
        eng = PositionLifecycleEngine()
        snap = PositionSnapshot(entry_price=2000, current_price=2010,
                                 current_sl=2005, initial_sl=1995,
                                 side="BUY", ticket=1001, age_seconds=600,
                                 atr=5.0, pnl_r=2.0)
        status = eng.evaluate(snap)
        assert status.state == PositionState.TRAILING
        assert status.protection_level == "TRAILING"

    def test_06_stuck_position(self):
        eng = PositionLifecycleEngine()
        snap = PositionSnapshot(entry_price=2000, current_price=2005,
                                 current_sl=1995, ticket=1001,
                                 age_seconds=STALE_POSITION_THRESHOLD + 100)
        status = eng.evaluate(snap)
        assert status.state == PositionState.STUCK
        assert status.safe_to_hold is False
        assert status.risk_level == "CRITICAL"

    def test_07_protected_state(self):
        eng = PositionLifecycleEngine()
        snap = PositionSnapshot(entry_price=2000, current_price=1998,
                                 current_sl=1997, initial_sl=1995,
                                 ticket=1001, age_seconds=300, pnl_r=-0.4)
        status = eng.evaluate(snap)
        assert status.state == PositionState.PROTECTED

    def test_08_missing_price_fails_safe(self):
        eng = PositionLifecycleEngine()
        snap = PositionSnapshot(entry_price=0, current_price=2000, ticket=1001)
        status = eng.evaluate(snap)
        assert status.state == PositionState.UNKNOWN
        assert status.safe_to_hold is False

    def test_09_missing_ticket_fails_safe(self):
        eng = PositionLifecycleEngine()
        snap = PositionSnapshot(entry_price=2000, current_price=2000, ticket=0)
        status = eng.evaluate(snap)
        assert status.state == PositionState.UNKNOWN

    def test_10_exception_fails_safe(self):
        eng = PositionLifecycleEngine()
        snap = PositionSnapshot(entry_price="invalid", current_price=2000, ticket=1001)  # type: ignore
        status = eng.evaluate(snap)
        assert status.state == PositionState.UNKNOWN
        assert status.safe_to_hold is False

    def test_11_all_states_present(self):
        states = [s.value for s in PositionState]
        expected = ["NEW", "OPEN", "IN_PROFIT", "AT_BREAKEVEN",
                     "PARTIALLY_CLOSED", "TRAILING", "PROTECTED",
                     "EXIT_PENDING", "CLOSED", "STUCK", "UNKNOWN"]
        for s in expected:
            assert s in states
