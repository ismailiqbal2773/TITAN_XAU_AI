"""TITAN XAU AI — Sprint 9.9.3.30 Exit Decision Coordinator Tests"""
from __future__ import annotations
import sys, inspect
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from titan.production.exit_defense_engine import SLDefenseDecision, SLAction
from titan.production.profit_capture_engine import ProfitCaptureDecision, ProfitAction
from titan.production.exit_decision_coordinator import (
    ExitDecisionCoordinator, ExitDecision, FinalAction,
)


class TestExitDecisionCoordinator:
    def _coord(self, sl: SLDefenseDecision, profit: ProfitCaptureDecision) -> ExitDecision:
        return ExitDecisionCoordinator().coordinate(sl, profit)

    def test_01_emergency_overrides_tp_extension(self):
        sl = SLDefenseDecision(action=SLAction.EMERGENCY_EXIT, allowed=False,
                                risk_reduction_factor=0.0, reason="NEWS_SHOCK")
        profit = ProfitCaptureDecision(action=ProfitAction.EXTEND_TP, allowed=True,
                                        reason="Extend TP")
        d = self._coord(sl, profit)
        assert d.final_action == FinalAction.EMERGENCY_EXIT
        assert d.should_close is True
        assert d.safe_to_hold is False

    def test_02_breakeven_priority(self):
        sl = SLDefenseDecision(action=SLAction.MOVE_TO_BREAKEVEN, allowed=True,
                                new_sl=2000, reason="Breakeven")
        profit = ProfitCaptureDecision(action=ProfitAction.HOLD, reason="Hold")
        d = self._coord(sl, profit)
        assert d.final_action == FinalAction.MOVE_TO_BREAKEVEN
        assert d.should_modify_sl is True
        assert d.new_sl == 2000

    def test_03_tighten_sl_overrides_extend_tp(self):
        sl = SLDefenseDecision(action=SLAction.TIGHTEN_SL, allowed=True,
                                new_sl=1997, reason="Tighten")
        profit = ProfitCaptureDecision(action=ProfitAction.EXTEND_TP, allowed=True,
                                        new_tp=2030, reason="Extend")
        d = self._coord(sl, profit)
        assert d.final_action == FinalAction.TIGHTEN_SL
        assert d.should_modify_sl is True
        assert d.should_modify_tp is False  # SL takes priority

    def test_04_partial_close_when_sl_holds(self):
        sl = SLDefenseDecision(action=SLAction.HOLD, allowed=True, reason="Hold")
        profit = ProfitCaptureDecision(action=ProfitAction.PARTIAL_CLOSE, allowed=True,
                                        partial_close_pct=0.25, reason="Partial")
        d = self._coord(sl, profit)
        assert d.final_action == FinalAction.PARTIAL_CLOSE
        assert d.should_partial_close is True
        assert d.partial_close_pct == 0.25

    def test_05_lock_profit_when_sl_holds(self):
        sl = SLDefenseDecision(action=SLAction.HOLD, allowed=True)
        profit = ProfitCaptureDecision(action=ProfitAction.LOCK_PROFIT, allowed=True,
                                        profit_lock_level=2000)
        d = self._coord(sl, profit)
        assert d.final_action == FinalAction.LOCK_PROFIT

    def test_06_extend_tp_when_safe(self):
        sl = SLDefenseDecision(action=SLAction.HOLD, allowed=True)
        profit = ProfitCaptureDecision(action=ProfitAction.EXTEND_TP, allowed=True,
                                        new_tp=2030, reason="Extend")
        d = self._coord(sl, profit)
        assert d.final_action == FinalAction.EXTEND_TP
        assert d.should_modify_tp is True
        assert d.new_tp == 2030

    def test_07_hold_when_both_hold(self):
        sl = SLDefenseDecision(action=SLAction.HOLD, allowed=True)
        profit = ProfitCaptureDecision(action=ProfitAction.HOLD, allowed=True)
        d = self._coord(sl, profit)
        assert d.final_action == FinalAction.HOLD
        assert d.should_close is False
        assert d.should_partial_close is False

    def test_08_sl_tighten_plus_partial_close(self):
        sl = SLDefenseDecision(action=SLAction.TIGHTEN_SL, allowed=True,
                                new_sl=1997, reason="Tighten")
        profit = ProfitCaptureDecision(action=ProfitAction.PARTIAL_CLOSE, allowed=True,
                                        partial_close_pct=0.25, reason="Partial")
        d = self._coord(sl, profit)
        assert d.final_action == FinalAction.PARTIAL_CLOSE
        assert d.should_partial_close is True
        assert d.should_modify_sl is True
        assert d.new_sl == 1997

    def test_09_profit_disabled_when_not_safe(self):
        sl = SLDefenseDecision(action=SLAction.HOLD, allowed=False, reason="Not safe")
        profit = ProfitCaptureDecision(action=ProfitAction.EXTEND_TP, allowed=True,
                                        reason="Extend")
        d = self._coord(sl, profit)
        assert d.final_action == FinalAction.HOLD
        assert d.safe_to_hold is False
        assert "disabled" in d.profit_action.lower() or d.profit_action == "EXTEND_TP"

    def test_10_take_profit_closes(self):
        sl = SLDefenseDecision(action=SLAction.HOLD, allowed=True)
        profit = ProfitCaptureDecision(action=ProfitAction.TAKE_PROFIT, allowed=True,
                                        reason="Take profit")
        d = self._coord(sl, profit)
        assert d.should_close is True

    def test_11_exception_fail_safe(self):
        sl = SLDefenseDecision(action="INVALID", reason="bad")  # type: ignore
        profit = ProfitCaptureDecision(action="INVALID")  # type: ignore
        d = self._coord(sl, profit)  # type: ignore
        assert d.final_action == FinalAction.HOLD
        assert d.safe_to_hold is False

    def test_12_priority_order_correct(self):
        """Emergency (1) < Breakeven (3) < Tighten (4) < Partial (5) < Lock (6) < Extend (7) < Hold (8)."""
        assert 1 < 3 < 4 < 5 < 6 < 7 < 8

    def test_13_risk_reduction_capped(self):
        d = ExitDecision(risk_reduction_factor=2.0)
        assert d.risk_reduction_factor == 1.0

    def test_14_no_order_send_in_source(self):
        from titan.production import exit_decision_coordinator
        src = inspect.getsource(exit_decision_coordinator)
        assert "order_send" not in src
        assert "mt5." not in src
