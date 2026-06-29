"""
TITAN XAU AI — Exit Intent Bridge (Sprint 9.9.3.31)
=====================================================

Connects PositionSnapshot → PositionLifecycle → SL Defense → Profit Capture
→ Exit Decision Coordinator → ExitIntent.

Never imports MetaTrader5. Never sends orders. should_send_order is always
False in this sprint.

Safety:
  - dry_run=True by default
  - demo_only=True by default
  - should_send_order=False always
  - Any exception → MANUAL_REVIEW or NO_ACTION
  - Stuck position → MANUAL_REVIEW
  - Emergency exit → CLOSE_FULL intent (dry-run, should_send_order=False)
  - Partial close never exceeds configured percentage
  - SL/TP modification never removes SL protection
  - No lot increase
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from titan.production.position_lifecycle import (
    PositionSnapshot, PositionLifecycleEngine, PositionLifecycleStatus,
    PositionState,
)
from titan.production.exit_defense_engine import (
    SLDefenseEngine, SLDefenseDecision, SLAction,
)
from titan.production.profit_capture_engine import (
    ProfitCaptureEngine, ProfitCaptureDecision, ProfitAction,
)
from titan.production.exit_decision_coordinator import (
    ExitDecisionCoordinator, ExitDecision, FinalAction,
)


class ExitIntentAction(str, Enum):
    HOLD = "HOLD"
    MODIFY_SL = "MODIFY_SL"
    MODIFY_TP = "MODIFY_TP"
    PARTIAL_CLOSE = "PARTIAL_CLOSE"
    CLOSE_FULL = "CLOSE_FULL"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    NO_ACTION = "NO_ACTION"


@dataclass
class ExitIntent:
    """Intent to act on a position. NOT an order — just a decision."""
    allowed: bool = False
    action: ExitIntentAction = ExitIntentAction.NO_ACTION
    symbol: str = "XAUUSD"
    ticket: int = 0
    side: str = "BUY"
    volume: float = 0.01
    partial_close_pct: float = 0.0
    new_sl: Optional[float] = None
    new_tp: Optional[float] = None
    reason: str = ""
    source_decision: str = ""
    dry_run: bool = True
    demo_only: bool = True
    should_send_order: bool = False   # ALWAYS False in this sprint
    timestamp_utc: str = ""

    def __post_init__(self):
        if not self.timestamp_utc:
            self.timestamp_utc = datetime.now(timezone.utc).isoformat()
        # Enforce: never send orders in this sprint
        self.should_send_order = False
        # Enforce: partial close never exceeds 100%
        if self.partial_close_pct > 1.0:
            self.partial_close_pct = 1.0


MAX_PARTIAL_CLOSE_PCT = 0.50  # Never close more than 50% in one partial


class ExitIntentBridge:
    """Builds ExitIntent from PositionSnapshot through the full pipeline.

    Pipeline:
      1. PositionLifecycleEngine.evaluate(snapshot) → lifecycle status
      2. If stuck → MANUAL_REVIEW
      3. SLDefenseEngine.evaluate(...) → SL decision
      4. ProfitCaptureEngine.evaluate(...) → profit decision
      5. ExitDecisionCoordinator.coordinate(sl, profit) → final decision
      6. Convert final decision → ExitIntent
    """

    def __init__(self, dry_run: bool = True, demo_only: bool = True,
                 max_partial_close_pct: float = MAX_PARTIAL_CLOSE_PCT):
        self.dry_run = dry_run
        self.demo_only = demo_only
        self.max_partial_close_pct = max_partial_close_pct
        self.lifecycle_engine = PositionLifecycleEngine()
        self.sl_engine = SLDefenseEngine()
        self.profit_engine = ProfitCaptureEngine()
        self.coordinator = ExitDecisionCoordinator()

    def build_exit_intent(self, snapshot: PositionSnapshot) -> ExitIntent:
        """Build an ExitIntent from a position snapshot.

        Never raises — returns fail-closed intent on any error.
        """
        try:
            # ── Step 1: Lifecycle evaluation ──
            lifecycle = self.lifecycle_engine.evaluate(snapshot)

            # ── Step 2: Stuck → MANUAL_REVIEW ──
            if lifecycle.state == PositionState.STUCK:
                return ExitIntent(
                    allowed=False,
                    action=ExitIntentAction.MANUAL_REVIEW,
                    symbol=snapshot.symbol,
                    ticket=snapshot.ticket,
                    side=snapshot.side,
                    volume=snapshot.volume,
                    reason=f"Stuck position: {lifecycle.reason}",
                    source_decision="LIFECYCLE_STUCK",
                    dry_run=self.dry_run,
                    demo_only=self.demo_only,
                )

            # ── Step 2b: Unknown lifecycle → MANUAL_REVIEW (fail-safe) ──
            if lifecycle.state == PositionState.UNKNOWN:
                return ExitIntent(
                    allowed=False,
                    action=ExitIntentAction.MANUAL_REVIEW,
                    symbol=snapshot.symbol,
                    ticket=snapshot.ticket,
                    side=snapshot.side,
                    volume=snapshot.volume,
                    reason=f"Unknown lifecycle: {lifecycle.reason}",
                    source_decision="LIFECYCLE_UNKNOWN",
                    dry_run=self.dry_run,
                    demo_only=self.demo_only,
                )

            # ── Step 3: SL Defense ──
            sl_decision = self.sl_engine.evaluate(
                entry_price=snapshot.entry_price,
                current_price=snapshot.current_price,
                current_sl=snapshot.current_sl,
                side=snapshot.side,
                atr=snapshot.atr,
                regime=snapshot.regime,
                volatility_score=0.0,  # could be enriched from snapshot
                spread_score=snapshot.spread_points / 100.0 if snapshot.spread_points > 0 else 0.0,
                liquidity_score=1.0,
                confidence=snapshot.model_confidence,
            )

            # ── Step 4: Profit Capture ──
            safe_to_hold = lifecycle.safe_to_hold and sl_decision.allowed
            profit_decision = self.profit_engine.evaluate(
                entry_price=snapshot.entry_price,
                current_price=snapshot.current_price,
                current_tp=snapshot.current_tp,
                side=snapshot.side,
                atr=snapshot.atr,
                regime=snapshot.regime,
                r_multiple=snapshot.pnl_r,
                confidence=snapshot.model_confidence,
                safe_to_hold=safe_to_hold,
                trade_age_seconds=snapshot.age_seconds,
            )

            # ── Step 5: Coordinator ──
            final = self.coordinator.coordinate(sl_decision, profit_decision)

            # ── Step 6: Convert to ExitIntent ──
            return self._convert_to_intent(snapshot, final, lifecycle)

        except Exception as e:
            return self._fail_closed(snapshot, f"Bridge exception: {e}")

    def _convert_to_intent(self, snapshot: PositionSnapshot,
                            final: ExitDecision,
                            lifecycle: PositionLifecycleStatus) -> ExitIntent:
        """Convert ExitDecision to ExitIntent."""
        action = ExitIntentAction.NO_ACTION
        partial_pct = 0.0
        new_sl = None
        new_tp = None
        allowed = False

        if final.final_action == FinalAction.EMERGENCY_EXIT:
            action = ExitIntentAction.CLOSE_FULL
            allowed = True
        elif final.final_action == FinalAction.MOVE_TO_BREAKEVEN:
            action = ExitIntentAction.MODIFY_SL
            new_sl = final.new_sl
            allowed = True
        elif final.final_action in (FinalAction.TIGHTEN_SL, FinalAction.TRAIL_SL):
            action = ExitIntentAction.MODIFY_SL
            new_sl = final.new_sl
            allowed = True
        elif final.final_action == FinalAction.PARTIAL_CLOSE:
            action = ExitIntentAction.PARTIAL_CLOSE
            partial_pct = min(final.partial_close_pct, self.max_partial_close_pct)
            if final.should_close and partial_pct == 0:
                # TAKE_PROFIT mapped as full close
                action = ExitIntentAction.CLOSE_FULL
            allowed = True
        elif final.final_action == FinalAction.LOCK_PROFIT:
            action = ExitIntentAction.HOLD  # Lock = hold with SL at BE
            allowed = True
        elif final.final_action == FinalAction.EXTEND_TP:
            action = ExitIntentAction.MODIFY_TP
            new_tp = final.new_tp
            allowed = True
        elif final.final_action == FinalAction.HOLD:
            action = ExitIntentAction.HOLD
            allowed = True

        # Safety: SL modification must never remove SL
        if action == ExitIntentAction.MODIFY_SL and new_sl is not None:
            if snapshot.side == "BUY" and new_sl < snapshot.entry_price * 0.5:
                new_sl = snapshot.entry_price * 0.5  # floor
            elif snapshot.side == "SELL" and new_sl > snapshot.entry_price * 1.5:
                new_sl = snapshot.entry_price * 1.5  # ceiling

        return ExitIntent(
            allowed=allowed,
            action=action,
            symbol=snapshot.symbol,
            ticket=snapshot.ticket,
            side=snapshot.side,
            volume=snapshot.volume,
            partial_close_pct=partial_pct,
            new_sl=new_sl,
            new_tp=new_tp,
            reason=final.reason,
            source_decision=final.final_action.value,
            dry_run=self.dry_run,
            demo_only=self.demo_only,
        )

    def _fail_closed(self, snapshot: PositionSnapshot,
                      reason: str) -> ExitIntent:
        return ExitIntent(
            allowed=False,
            action=ExitIntentAction.MANUAL_REVIEW,
            symbol=snapshot.symbol,
            ticket=snapshot.ticket,
            side=snapshot.side,
            volume=snapshot.volume,
            reason=reason,
            source_decision="FAIL_CLOSED",
            dry_run=self.dry_run,
            demo_only=self.demo_only,
        )
