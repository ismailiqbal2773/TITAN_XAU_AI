"""
TITAN XAU AI - Demo Micro Position Manager (Sprint 9.9.3.45)
=============================================================
Monitors one open XAUUSD TITAN_DEMO_MICRO position and computes
breakeven/trailing/profit-lock SL modifications.

NEVER widens SL. NEVER moves SL backward. NEVER removes TP.
NEVER modifies non-TITAN positions. NEVER sends orders directly.
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


# Default conservative thresholds (in XAUUSD price units)
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

    def __post_init__(self):
        if not self.timestamp_utc:
            self.timestamp_utc = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        d = asdict(self)
        d["action"] = self.action.value
        return d


class DemoMicroPositionManager:
    """Position manager for demo micro. Favorable-only SL movement."""

    def __init__(self, breakeven_trigger: float = BREAKEVEN_TRIGGER,
                 breakeven_offset: float = BREAKEVEN_OFFSET,
                 trailing_trigger: float = TRAILING_TRIGGER,
                 trailing_distance: float = TRAILING_DISTANCE,
                 profit_lock_trigger: float = PROFIT_LOCK_TRIGGER):
        self.breakeven_trigger = breakeven_trigger
        self.breakeven_offset = breakeven_offset
        self.trailing_trigger = trailing_trigger
        self.trailing_distance = trailing_distance
        self.profit_lock_trigger = profit_lock_trigger

    def evaluate(self, direction: str, entry_price: float, current_price: float,
                 current_sl: float, current_tp: float,
                 stops_level_points: int = 0, point: float = 0.01) -> SLModifyRecommendation:
        """Evaluate position and recommend SL modification.

        NEVER sends orders. Returns recommendation only.
        Favorable-only: BUY SL only moves up, SELL SL only moves down.
        """
        rec = SLModifyRecommendation(
            current_sl=current_sl,
            entry_price=entry_price,
            current_price=current_price,
            tp=current_tp,
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
            # Favorable = new_sl > current_sl (SL moves up for BUY)
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
            # Favorable = new_sl < current_sl (SL moves down for SELL)
            best_sl = current_sl
            best_action = SLAction.HOLD
            if current_sl == 0:
                best_sl = 999999.0  # Sentinel for SELL when SL=0
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
                best_sl = current_sl  # No improvement

        # Validate favorable direction
        if direction == "BUY":
            favorable = best_sl >= current_sl
        else:
            favorable = best_sl <= current_sl or current_sl == 0

        # Validate stop level
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
