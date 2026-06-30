"""
TITAN XAU AI - Demo Micro SL/TP Safety (Sprint 9.9.3.44.2)
============================================================
Safe SL/TP fallback calculator for demo micro execution.
NEVER imports MetaTrader5. NEVER sends orders.
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class SLTPVerdict(str, Enum):
    SLTP_VALID = "SLTP_VALID"
    SLTP_ATR_FALLBACK_USED = "SLTP_ATR_FALLBACK_USED"
    SLTP_BLOCKED = "SLTP_BLOCKED"


@dataclass
class SLTPResult:
    verdict: SLTPVerdict = SLTPVerdict.SLTP_BLOCKED
    sl: float = 0.0
    tp: float = 0.0
    has_sl: bool = False
    has_tp: bool = False
    fallback_reason: str = ""
    atr_used: float = 0.0
    blockers: list[str] = field(default_factory=list)
    timestamp_utc: str = ""

    def __post_init__(self):
        if not self.timestamp_utc:
            self.timestamp_utc = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        d = asdict(self)
        d["verdict"] = self.verdict.value
        return d


class DemoMicroSLTPSafety:
    """Safe SL/TP calculator. Never guesses. Never uses zero SL/TP."""

    def validate_or_compute(self, direction: str, entry_price: float,
                              sl: float = 0.0, tp: float = 0.0,
                              atr: float = 0.0,
                              ) -> SLTPResult:
        """Validate existing SL/TP or compute ATR-based fallback.

        Rules:
        - If SL/TP provided and valid, use them.
        - If SL/TP missing but ATR > 0 and entry_price > 0, compute fallback.
        - If ATR unavailable or entry_price unavailable, BLOCK.
        - Never use zero SL/TP.
        - Never use random SL/TP.
        """
        result = SLTPResult()

        if direction not in ("BUY", "SELL"):
            result.blockers.append(f"Invalid direction: {direction}")
            result.verdict = SLTPVerdict.SLTP_BLOCKED
            return result

        if entry_price <= 0:
            result.blockers.append("Entry/reference price unavailable - must be > 0")
            result.verdict = SLTPVerdict.SLTP_BLOCKED
            return result

        # Try to use provided SL/TP first
        has_sl = sl > 0
        has_tp = tp > 0

        if has_sl and has_tp:
            # Validate direction
            if direction == "BUY":
                if sl >= entry_price:
                    result.blockers.append(f"BUY SL={sl} must be below entry={entry_price}")
                    result.verdict = SLTPVerdict.SLTP_BLOCKED
                    return result
                if tp <= entry_price:
                    result.blockers.append(f"BUY TP={tp} must be above entry={entry_price}")
                    result.verdict = SLTPVerdict.SLTP_BLOCKED
                    return result
            elif direction == "SELL":
                if sl <= entry_price:
                    result.blockers.append(f"SELL SL={sl} must be above entry={entry_price}")
                    result.verdict = SLTPVerdict.SLTP_BLOCKED
                    return result
                if tp >= entry_price:
                    result.blockers.append(f"SELL TP={tp} must be below entry={entry_price}")
                    result.verdict = SLTPVerdict.SLTP_BLOCKED
                    return result

            result.sl = sl
            result.tp = tp
            result.has_sl = True
            result.has_tp = True
            result.verdict = SLTPVerdict.SLTP_VALID
            result.fallback_reason = "Provided SL/TP validated"
            return result

        # SL/TP missing - try ATR fallback
        if atr <= 0:
            result.blockers.append("SL/TP missing and ATR unavailable - cannot compute safe fallback")
            result.verdict = SLTPVerdict.SLTP_BLOCKED
            return result

        # ATR-based fallback
        sl_distance = 1.0 * atr  # conservative
        tp_distance = 1.5 * atr  # 1.5:1 reward-risk

        if direction == "BUY":
            result.sl = entry_price - sl_distance
            result.tp = entry_price + tp_distance
        else:  # SELL
            result.sl = entry_price + sl_distance
            result.tp = entry_price - tp_distance

        result.has_sl = True
        result.has_tp = True
        result.atr_used = atr
        result.fallback_reason = f"ATR fallback: sl_dist={sl_distance:.4f}, tp_dist={tp_distance:.4f}"
        result.verdict = SLTPVerdict.SLTP_ATR_FALLBACK_USED
        return result
