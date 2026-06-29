"""
TITAN XAU AI — Exit Decision Coordinator (Sprint 9.9.3.30)
============================================================

Resolves SLDefenseDecision + ProfitCaptureDecision into one final
ExitDecision using a strict priority ladder.

Priority (highest first):
  1. EMERGENCY_EXIT
  2. FORCE_CLOSE / MANUAL_REVIEW safety
  3. MOVE_TO_BREAKEVEN
  4. TIGHTEN_SL / TRAIL_SL
  5. PARTIAL_CLOSE
  6. LOCK_PROFIT
  7. EXTEND_TP / TRAIL_TP
  8. HOLD

Conflict rules:
  - SL Defense overrides Profit Capture when risk is critical
  - Profit Capture operates only when safe_to_hold=True
  - If engines disagree and severity unclear → fail safe toward protection
  - Never removes SL
  - Never increases risk above configured limits
  - Never places orders — only produces decisions
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from titan.production.exit_defense_engine import SLDefenseDecision, SLAction
from titan.production.profit_capture_engine import ProfitCaptureDecision, ProfitAction


class FinalAction(str, Enum):
    EMERGENCY_EXIT = "EMERGENCY_EXIT"
    MOVE_TO_BREAKEVEN = "MOVE_TO_BREAKEVEN"
    TIGHTEN_SL = "TIGHTEN_SL"
    TRAIL_SL = "TRAIL_SL"
    PARTIAL_CLOSE = "PARTIAL_CLOSE"
    LOCK_PROFIT = "LOCK_PROFIT"
    EXTEND_TP = "EXTEND_TP"
    TRAIL_TP = "TRAIL_TP"
    HOLD = "HOLD"


# Priority mapping (lower number = higher priority)
_PRIORITY = {
    FinalAction.EMERGENCY_EXIT: 1,
    FinalAction.MOVE_TO_BREAKEVEN: 3,
    FinalAction.TIGHTEN_SL: 4,
    FinalAction.TRAIL_SL: 4,
    FinalAction.PARTIAL_CLOSE: 5,
    FinalAction.LOCK_PROFIT: 6,
    FinalAction.EXTEND_TP: 7,
    FinalAction.TRAIL_TP: 7,
    FinalAction.HOLD: 8,
}


@dataclass
class ExitDecision:
    final_action: FinalAction = FinalAction.HOLD
    sl_action: str = "NO_ACTION"
    profit_action: str = "NO_ACTION"
    should_close: bool = False
    should_partial_close: bool = False
    partial_close_pct: float = 0.0
    should_modify_sl: bool = False
    new_sl: Optional[float] = None
    should_modify_tp: bool = False
    new_tp: Optional[float] = None
    risk_reduction_factor: float = 1.0
    reason: str = ""
    priority: int = 8
    safe_to_hold: bool = True
    timestamp_utc: str = ""

    def __post_init__(self):
        if self.risk_reduction_factor > 1.0:
            self.risk_reduction_factor = 1.0
        if not self.timestamp_utc:
            self.timestamp_utc = datetime.now(timezone.utc).isoformat()


class ExitDecisionCoordinator:
    """Resolves SL + Profit decisions into final ExitDecision."""

    def coordinate(self,
                   sl_decision: SLDefenseDecision,
                   profit_decision: ProfitCaptureDecision,
                   ) -> ExitDecision:
        """Resolve two engine decisions into one final ExitDecision.

        Never raises — returns fail-safe HOLD on error.
        """
        try:
            # Determine safe_to_hold from SL decision
            safe_to_hold = (
                sl_decision.allowed and
                sl_decision.action not in (SLAction.EMERGENCY_EXIT,)
            )

            # ── Priority 1: EMERGENCY_EXIT ──
            if sl_decision.action == SLAction.EMERGENCY_EXIT:
                return ExitDecision(
                    final_action=FinalAction.EMERGENCY_EXIT,
                    sl_action=sl_decision.action.value,
                    profit_action=profit_decision.action.value,
                    should_close=True,
                    risk_reduction_factor=sl_decision.risk_reduction_factor,
                    reason=f"SL emergency: {sl_decision.reason}",
                    priority=_PRIORITY[FinalAction.EMERGENCY_EXIT],
                    safe_to_hold=False,
                )

            # ── Priority 3: MOVE_TO_BREAKEVEN ──
            if sl_decision.action == SLAction.MOVE_TO_BREAKEVEN:
                return ExitDecision(
                    final_action=FinalAction.MOVE_TO_BREAKEVEN,
                    sl_action=sl_decision.action.value,
                    profit_action=profit_decision.action.value,
                    should_modify_sl=True,
                    new_sl=sl_decision.new_sl,
                    risk_reduction_factor=sl_decision.risk_reduction_factor,
                    reason=f"SL breakeven: {sl_decision.reason}",
                    priority=_PRIORITY[FinalAction.MOVE_TO_BREAKEVEN],
                    safe_to_hold=safe_to_hold,
                )

            # ── Priority 4: TIGHTEN_SL / TRAIL_SL ──
            if sl_decision.action in (SLAction.TIGHTEN_SL, SLAction.TRAIL_SL):
                # SL defense wants to tighten — check if profit wants to act too
                if profit_decision.action == ProfitAction.PARTIAL_CLOSE and safe_to_hold:
                    # Both want to act — partial close + tighten SL
                    return ExitDecision(
                        final_action=FinalAction.PARTIAL_CLOSE,
                        sl_action=sl_decision.action.value,
                        profit_action=profit_decision.action.value,
                        should_partial_close=True,
                        partial_close_pct=profit_decision.partial_close_pct,
                        should_modify_sl=True,
                        new_sl=sl_decision.new_sl,
                        risk_reduction_factor=sl_decision.risk_reduction_factor,
                        reason=f"SL tighten + partial close: {sl_decision.reason} | {profit_decision.reason}",
                        priority=_PRIORITY[FinalAction.PARTIAL_CLOSE],
                        safe_to_hold=safe_to_hold,
                    )
                # SL tighten takes priority over profit extend
                return ExitDecision(
                    final_action=FinalAction.TIGHTEN_SL if sl_decision.action == SLAction.TIGHTEN_SL else FinalAction.TRAIL_SL,
                    sl_action=sl_decision.action.value,
                    profit_action=profit_decision.action.value,
                    should_modify_sl=True,
                    new_sl=sl_decision.new_sl,
                    risk_reduction_factor=sl_decision.risk_reduction_factor,
                    reason=f"SL action: {sl_decision.reason}",
                    priority=_PRIORITY[FinalAction.TIGHTEN_SL],
                    safe_to_hold=safe_to_hold,
                )

            # ── SL says HOLD — check profit actions ──
            if not safe_to_hold:
                # SL not safe but not emergency — fail safe toward protection
                return ExitDecision(
                    final_action=FinalAction.HOLD,
                    sl_action=sl_decision.action.value,
                    profit_action="DISABLED",
                    risk_reduction_factor=min(sl_decision.risk_reduction_factor, 0.5),
                    reason="SL not safe — profit capture disabled, fail-safe hold",
                    priority=8,
                    safe_to_hold=False,
                )

            # ── Priority 5: PARTIAL_CLOSE ──
            if profit_decision.action == ProfitAction.PARTIAL_CLOSE:
                return ExitDecision(
                    final_action=FinalAction.PARTIAL_CLOSE,
                    sl_action=sl_decision.action.value,
                    profit_action=profit_decision.action.value,
                    should_partial_close=True,
                    partial_close_pct=profit_decision.partial_close_pct,
                    risk_reduction_factor=sl_decision.risk_reduction_factor,
                    reason=f"Profit partial close: {profit_decision.reason}",
                    priority=_PRIORITY[FinalAction.PARTIAL_CLOSE],
                    safe_to_hold=True,
                )

            # ── Priority 6: LOCK_PROFIT ──
            if profit_decision.action == ProfitAction.LOCK_PROFIT:
                return ExitDecision(
                    final_action=FinalAction.LOCK_PROFIT,
                    sl_action=sl_decision.action.value,
                    profit_action=profit_decision.action.value,
                    risk_reduction_factor=sl_decision.risk_reduction_factor,
                    reason=f"Profit lock: {profit_decision.reason}",
                    priority=_PRIORITY[FinalAction.LOCK_PROFIT],
                    safe_to_hold=True,
                )

            # ── Priority 7: EXTEND_TP / TRAIL_TP ──
            if profit_decision.action == ProfitAction.EXTEND_TP:
                return ExitDecision(
                    final_action=FinalAction.EXTEND_TP,
                    sl_action=sl_decision.action.value,
                    profit_action=profit_decision.action.value,
                    should_modify_tp=True,
                    new_tp=profit_decision.new_tp,
                    risk_reduction_factor=sl_decision.risk_reduction_factor,
                    reason=f"Profit extend TP: {profit_decision.reason}",
                    priority=_PRIORITY[FinalAction.EXTEND_TP],
                    safe_to_hold=True,
                )

            if profit_decision.action == ProfitAction.TAKE_PROFIT:
                return ExitDecision(
                    final_action=FinalAction.PARTIAL_CLOSE,
                    sl_action=sl_decision.action.value,
                    profit_action=profit_decision.action.value,
                    should_close=True,
                    risk_reduction_factor=sl_decision.risk_reduction_factor,
                    reason=f"Profit take profit: {profit_decision.reason}",
                    priority=_PRIORITY[FinalAction.PARTIAL_CLOSE],
                    safe_to_hold=True,
                )

            # ── Priority 8: HOLD ──
            return ExitDecision(
                final_action=FinalAction.HOLD,
                sl_action=sl_decision.action.value,
                profit_action=profit_decision.action.value,
                risk_reduction_factor=sl_decision.risk_reduction_factor,
                reason="Both engines hold",
                priority=_PRIORITY[FinalAction.HOLD],
                safe_to_hold=True,
            )
        except Exception:
            return ExitDecision(
                final_action=FinalAction.HOLD,
                reason="Coordinator exception — fail-safe hold",
                priority=8,
                safe_to_hold=False,
                risk_reduction_factor=0.5,
            )
