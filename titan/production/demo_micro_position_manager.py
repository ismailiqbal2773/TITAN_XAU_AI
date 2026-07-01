"""
TITAN XAU AI - Demo Micro Position Manager (Sprint 9.9.3.45.8)
=============================================================
Monitors one open XAUUSD TITAN_DEMO_MICRO position and computes
breakeven/trailing/profit-lock SL modifications.

Sprint 9.9.3.45.8: AdaptiveTrailingPolicy integration. The manager
can be configured to use either the legacy fixed-threshold logic
(legacy_mode=True, default for backwards compat with 45.6 tests) or
the new AdaptiveTrailingPolicy (legacy_mode=False) which uses
R-multiple, ATR/noise buffer, regime, spread/stop-level buffers, and
hysteresis/cooldown.

NEVER widens SL. NEVER moves SL backward. NEVER removes TP.
NEVER modifies non-TITAN positions. NEVER sends orders directly.
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from titan.production.adaptive_trailing_policy import (
    AdaptiveTrailingPolicy, PolicyMode, PolicyAction, Regime,
    PHASE_0_INITIAL_PROTECTION, PHASE_1_NOISE_FILTER,
    PHASE_2_SOFT_BREAKEVEN, PHASE_3_ADAPTIVE_TRAIL, PHASE_4_PROFIT_LOCK,
)


# Default conservative thresholds (in XAUUSD price units) - legacy
BREAKEVEN_TRIGGER = 1.0
BREAKEVEN_OFFSET = 0.1
TRAILING_TRIGGER = 2.0
TRAILING_DISTANCE = 1.0
PROFIT_LOCK_TRIGGER = 3.0
TITAN_MAGIC = 202619


class SLAction(str, Enum):
    HOLD = "HOLD"
    MOVE_TO_BREAKEVEN = "MOVE_TO_BREAKEVEN"
    TRAIL = "TRAIL"
    PROFIT_LOCK = "PROFIT_LOCK"
    BLOCKED = "BLOCKED"


# Mapping from PolicyAction to SLAction (for adaptive mode)
_POLICY_TO_SL_ACTION = {
    PolicyAction.HOLD: SLAction.HOLD,
    PolicyAction.MOVE_TO_BREAKEVEN: SLAction.MOVE_TO_BREAKEVEN,
    PolicyAction.TRAIL: SLAction.TRAIL,
    PolicyAction.PROFIT_LOCK: SLAction.PROFIT_LOCK,
    PolicyAction.BLOCKED: SLAction.BLOCKED,
}


@dataclass
class SLModifyRecommendation:
    action: SLAction = SLAction.HOLD
    new_sl: float = 0.0
    current_sl: float = 0.0
    entry_price: float = 0.0
    current_price: float = 0.0
    tp: float = 0.0
    favorable: bool = True
    reason: str = ""
    blockers: list[str] = field(default_factory=list)
    timestamp_utc: str = ""
    # Sprint 9.9.3.45.8: adaptive policy fields
    phase: str = ""
    profit_R: float = 0.0
    R: float = 0.0
    ATR_noise: float = 0.0
    regime: str = ""
    spread_buffer: float = 0.0
    stop_level_buffer: float = 0.0
    structure_buffer: float = 0.0
    trailing_distance: float = 0.0
    proposed_sl: float = 0.0
    final_sl: float = 0.0
    tp_preserved: bool = True
    no_widening: bool = True
    anti_whipsaw_blocks: list[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.timestamp_utc:
            self.timestamp_utc = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        d = asdict(self)
        d["action"] = self.action.value
        return d


class DemoMicroPositionManager:
    """Position manager for demo micro. Favorable-only SL movement.

    Sprint 9.9.3.45.8: supports both legacy fixed-threshold mode and
    new adaptive trailing policy mode.

    Set legacy_mode=False to use AdaptiveTrailingPolicy.
    """

    def __init__(self, breakeven_trigger: float = BREAKEVEN_TRIGGER,
                 breakeven_offset: float = BREAKEVEN_OFFSET,
                 trailing_trigger: float = TRAILING_TRIGGER,
                 trailing_distance: float = TRAILING_DISTANCE,
                 profit_lock_trigger: float = PROFIT_LOCK_TRIGGER,
                 legacy_mode: bool = True,
                 adaptive_policy: Optional[AdaptiveTrailingPolicy] = None):
        self.breakeven_trigger = breakeven_trigger
        self.breakeven_offset = breakeven_offset
        self.trailing_trigger = trailing_trigger
        self.trailing_distance = trailing_distance
        self.profit_lock_trigger = profit_lock_trigger
        self.legacy_mode = legacy_mode
        # Adaptive policy: inject or create default balanced_conservative
        self.adaptive_policy = adaptive_policy if adaptive_policy is not None else (
            AdaptiveTrailingPolicy(mode=PolicyMode.BALANCED_CONSERVATIVE)
            if not legacy_mode else None
        )

    def evaluate(self, direction: str, entry_price: float, current_price: float,
                 current_sl: float, current_tp: float,
                 stops_level_points: int = 0, point: float = 0.01,
                 **adaptive_kwargs) -> SLModifyRecommendation:
        """Evaluate position and recommend SL modification.

        NEVER sends orders. Returns recommendation only.
        Favorable-only: BUY SL only moves up, SELL SL only moves down.

        Sprint 9.9.3.45.8: When legacy_mode=False, delegates to
        AdaptiveTrailingPolicy. Adaptive kwargs (atr, spread, regime,
        hold_seconds, monitor_iterations, seconds_since_last_modify,
        spread_spike_flag, news_flag, structure_buffer) are passed
        through to the policy.
        """
        if not self.legacy_mode and self.adaptive_policy is not None:
            return self._evaluate_adaptive(
                direction=direction, entry_price=entry_price,
                current_price=current_price, current_sl=current_sl,
                current_tp=current_tp, stops_level_points=stops_level_points,
                point=point, **adaptive_kwargs,
            )
        return self._evaluate_legacy(
            direction=direction, entry_price=entry_price,
            current_price=current_price, current_sl=current_sl,
            current_tp=current_tp, stops_level_points=stops_level_points,
            point=point,
        )

    def _evaluate_legacy(self, direction: str, entry_price: float,
                          current_price: float, current_sl: float,
                          current_tp: float, stops_level_points: int = 0,
                          point: float = 0.01) -> SLModifyRecommendation:
        """Legacy fixed-threshold evaluation (Sprint 9.9.3.45.6 behavior)."""
        rec = SLModifyRecommendation(
            current_sl=current_sl,
            entry_price=entry_price,
            current_price=current_price,
            tp=current_tp,
            phase="LEGACY",
        )

        if direction not in ("BUY", "SELL"):
            rec.action = SLAction.BLOCKED
            rec.blockers.append(f"Invalid direction: {direction}")
            return rec

        # Compute profit distance
        if direction == "BUY":
            profit_distance = current_price - entry_price
        else:
            profit_distance = entry_price - current_price

        # Compute new SL candidates
        if direction == "BUY":
            breakeven_sl = entry_price + self.breakeven_offset
            trailing_sl = current_price - self.trailing_distance
            profit_lock_sl = entry_price + self.profit_lock_trigger
            best_sl = current_sl
            best_action = SLAction.HOLD
            if profit_distance >= self.profit_lock_trigger:
                candidate = max(profit_lock_sl, trailing_sl, breakeven_sl)
                if candidate > best_sl:
                    best_sl = candidate
                    best_action = SLAction.PROFIT_LOCK
            elif profit_distance >= self.trailing_trigger:
                candidate = max(trailing_sl, breakeven_sl)
                if candidate > best_sl:
                    best_sl = candidate
                    best_action = SLAction.TRAIL
            elif profit_distance >= self.breakeven_trigger:
                candidate = breakeven_sl
                if candidate > best_sl:
                    best_sl = candidate
                    best_action = SLAction.MOVE_TO_BREAKEVEN
        else:  # SELL
            breakeven_sl = entry_price - self.breakeven_offset
            trailing_sl = current_price + self.trailing_distance
            profit_lock_sl = entry_price - self.profit_lock_trigger
            best_sl = current_sl
            best_action = SLAction.HOLD
            if current_sl == 0:
                best_sl = 999999.0
            if profit_distance >= self.profit_lock_trigger:
                candidate = min(profit_lock_sl, trailing_sl, breakeven_sl)
                if candidate < best_sl:
                    best_sl = candidate
                    best_action = SLAction.PROFIT_LOCK
            elif profit_distance >= self.trailing_trigger:
                candidate = min(trailing_sl, breakeven_sl)
                if candidate < best_sl:
                    best_sl = candidate
                    best_action = SLAction.TRAIL
            elif profit_distance >= self.breakeven_trigger:
                candidate = breakeven_sl
                if candidate < best_sl:
                    best_sl = candidate
                    best_action = SLAction.MOVE_TO_BREAKEVEN
            if best_sl == 999999.0:
                best_sl = current_sl

        if direction == "BUY":
            favorable = best_sl >= current_sl
        else:
            favorable = best_sl <= current_sl or current_sl == 0

        min_stop_distance = stops_level_points * point if stops_level_points > 0 else 0
        if direction == "BUY":
            if best_sl > 0 and (current_price - best_sl) < min_stop_distance:
                rec.blockers.append(f"SL too close to current price (stop level)")
                best_action = SLAction.BLOCKED
        else:
            if best_sl > 0 and (best_sl - current_price) < min_stop_distance:
                rec.blockers.append(f"SL too close to current price (stop level)")
                best_action = SLAction.BLOCKED

        rec.action = best_action
        rec.new_sl = best_sl if best_action != SLAction.HOLD else current_sl
        rec.favorable = favorable
        rec.reason = f"profit_distance={profit_distance:.4f}, action={best_action.value}"
        return rec

    def _evaluate_adaptive(self, direction: str, entry_price: float,
                            current_price: float, current_sl: float,
                            current_tp: float, stops_level_points: int = 0,
                            point: float = 0.01, **adaptive_kwargs) -> SLModifyRecommendation:
        """Adaptive trailing policy evaluation (Sprint 9.9.3.45.8)."""
        # initial_sl: the policy needs the ORIGINAL SL to compute R.
        # If the caller passes 'initial_sl' in adaptive_kwargs, use it.
        # Otherwise, fall back to current_sl (which is the SL at the time
        # of evaluation; on the first iteration this equals initial_sl).
        initial_sl = adaptive_kwargs.pop("initial_sl", current_sl)

        decision = self.adaptive_policy.evaluate(
            direction=direction,
            entry_price=entry_price,
            initial_sl=initial_sl,
            current_price=current_price,
            current_sl=current_sl,
            current_tp=current_tp,
            stops_level_points=stops_level_points,
            point=point,
            **adaptive_kwargs,
        )

        # Map PolicyAction -> SLAction
        sl_action = _POLICY_TO_SL_ACTION.get(decision.action, SLAction.HOLD)

        rec = SLModifyRecommendation(
            action=sl_action,
            new_sl=decision.final_sl if sl_action not in (SLAction.HOLD, SLAction.BLOCKED) else current_sl,
            current_sl=current_sl,
            entry_price=entry_price,
            current_price=current_price,
            tp=current_tp,
            favorable=decision.favorable,
            reason=decision.reason,
            blockers=list(decision.anti_whipsaw_blocks),
            phase=decision.phase,
            profit_R=decision.profit_R,
            R=decision.R,
            ATR_noise=decision.ATR_noise,
            regime=decision.regime.value,
            spread_buffer=decision.spread_buffer,
            stop_level_buffer=decision.stop_level_buffer,
            structure_buffer=decision.structure_buffer,
            trailing_distance=decision.trailing_distance,
            proposed_sl=decision.proposed_sl,
            final_sl=decision.final_sl,
            tp_preserved=decision.tp_preserved,
            no_widening=decision.no_widening,
            anti_whipsaw_blocks=list(decision.anti_whipsaw_blocks),
        )
        return rec
