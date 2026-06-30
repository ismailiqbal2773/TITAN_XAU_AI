"""
TITAN XAU AI - Demo Micro SL/TP Safety (Sprint 9.9.3.44.3)
============================================================
Safe SL/TP fallback calculator for demo micro execution.

Sprint 9.9.3.44.3: Added real MT5 tick protective fallback.
When ATR is unavailable, uses passive mt5.symbol_info_tick to get
real demo tick price and computes protective SL/TP from that.

NEVER calls mt5.order_send. NEVER executes orders.
"""
from __future__ import annotations
import math
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


# Default safe fallback distances for XAUUSD demo micro (in price units)
DEFAULT_XAUUSD_SL_DISTANCE = 3.0
DEFAULT_XAUUSD_TP_DISTANCE = 3.0
SAFETY_MULTIPLIER = 2.0  # multiplier for broker stop level


class SLTPVerdict(str, Enum):
    SLTP_VALID = "SLTP_VALID"
    SLTP_ATR_FALLBACK_USED = "SLTP_ATR_FALLBACK_USED"
    SLTP_MT5_TICK_FALLBACK_USED = "SLTP_MT5_TICK_FALLBACK_USED"
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
    reference_price: float = 0.0
    sl_distance: float = 0.0
    tp_distance: float = 0.0
    stop_level_checked: bool = False
    stop_level_valid: bool = False
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
    """Safe SL/TP calculator. Never guesses. Never uses zero SL/TP.

    Fallback priority:
    1. Provided SL/TP if valid
    2. ATR-based fallback if ATR and entry_price available
    3. MT5 tick protective fallback if ATR unavailable (Sprint 9.9.3.44.3)
    4. Block if all fail
    """

    def validate_or_compute(self, direction: str, entry_price: float,
                              sl: float = 0.0, tp: float = 0.0,
                              atr: float = 0.0,
                              symbol: str = "XAUUSD",
                              ) -> SLTPResult:
        """Validate existing SL/TP or compute fallback.

        NEVER calls mt5.order_send.
        """
        result = SLTPResult()

        if direction not in ("BUY", "SELL"):
            result.blockers.append(f"Invalid direction: {direction}")
            result.verdict = SLTPVerdict.SLTP_BLOCKED
            return result

        if entry_price <= 0:
            result.blockers.append("DEMO_MICRO_REFERENCE_PRICE_MISSING: Entry/reference price unavailable - must be > 0")
            result.verdict = SLTPVerdict.SLTP_BLOCKED
            return result

        # 1. Try to use provided SL/TP first
        has_sl = sl > 0
        has_tp = tp > 0

        if has_sl and has_tp:
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
            result.reference_price = entry_price
            result.verdict = SLTPVerdict.SLTP_VALID
            result.fallback_reason = "Provided SL/TP validated"
            return result

        # 2. ATR-based fallback
        if atr > 0:
            sl_distance = 1.0 * atr
            tp_distance = 1.5 * atr

            if direction == "BUY":
                result.sl = entry_price - sl_distance
                result.tp = entry_price + tp_distance
            else:
                result.sl = entry_price + sl_distance
                result.tp = entry_price - tp_distance

            result.has_sl = True
            result.has_tp = True
            result.atr_used = atr
            result.reference_price = entry_price
            result.sl_distance = sl_distance
            result.tp_distance = tp_distance
            result.fallback_reason = f"ATR fallback: sl_dist={sl_distance:.4f}, tp_dist={tp_distance:.4f}"
            result.verdict = SLTPVerdict.SLTP_ATR_FALLBACK_USED
            return result

        # 3. Sprint 9.9.3.44.3: MT5 tick protective fallback
        # ATR unavailable - try real MT5 tick for reference price and stop level
        mt5_result = self._try_mt5_tick_fallback(direction, entry_price, symbol)
        if mt5_result is not None:
            return mt5_result

        # 4. All fallbacks failed - block
        result.blockers.append(
            "DEMO_MICRO_SL_TP_MISSING: SL/TP missing, ATR unavailable, and MT5 tick fallback failed"
        )
        result.verdict = SLTPVerdict.SLTP_BLOCKED
        return result

    def _try_mt5_tick_fallback(self, direction: str, entry_price: float,
                                 symbol: str) -> Optional[SLTPResult]:
        """Try to get real MT5 demo tick and compute protective SL/TP.

        Uses passive MT5 reads only:
        - mt5.initialize
        - mt5.symbol_info
        - mt5.symbol_info_tick
        - mt5.shutdown

        NEVER calls mt5.order_send.
        """
        try:
            import MetaTrader5 as mt5
        except ImportError:
            return None

        result = SLTPResult()

        try:
            if not mt5.initialize():
                return None

            # Get symbol info
            info = mt5.symbol_info(symbol)
            if info is None:
                mt5.shutdown()
                return None

            # Get tick
            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                mt5.shutdown()
                return None

            mt5.shutdown()

            # Use real tick price as reference
            if direction == "BUY":
                ref_price = tick.ask
            else:
                ref_price = tick.bid

            if ref_price <= 0:
                return None

            # Get point and digits
            point = info.point if info.point > 0 else 0.01
            digits = info.digits if info.digits > 0 else 2

            # Get broker stop level
            stops_level = getattr(info, "trade_stops_level", 0) or 0
            freeze_level = getattr(info, "trade_freeze_level", 0) or 0

            # Compute safe distance
            broker_min_distance = max(stops_level, freeze_level) * point
            safe_distance = max(
                DEFAULT_XAUUSD_SL_DISTANCE,
                broker_min_distance * SAFETY_MULTIPLIER,
            )

            sl_distance = safe_distance
            tp_distance = safe_distance

            # Compute SL/TP
            if direction == "BUY":
                sl = ref_price - sl_distance
                tp = ref_price + tp_distance
            else:
                sl = ref_price + sl_distance
                tp = ref_price - tp_distance

            # Round to symbol digits
            sl = round(sl, digits)
            tp = round(tp, digits)

            # Validate against stop level
            stop_level_valid = True
            if stops_level > 0:
                min_stop_price = stops_level * point
                if sl_distance < min_stop_price * SAFETY_MULTIPLIER:
                    # Widen distance
                    sl_distance = min_stop_price * SAFETY_MULTIPLIER
                    tp_distance = min_stop_price * SAFETY_MULTIPLIER
                    if direction == "BUY":
                        sl = round(ref_price - sl_distance, digits)
                        tp = round(ref_price + tp_distance, digits)
                    else:
                        sl = round(ref_price + sl_distance, digits)
                        tp = round(ref_price - tp_distance, digits)

            result.sl = sl
            result.tp = tp
            result.has_sl = True
            result.has_tp = True
            result.reference_price = ref_price
            result.sl_distance = sl_distance
            result.tp_distance = tp_distance
            result.stop_level_checked = True
            result.stop_level_valid = stop_level_valid
            result.fallback_reason = "mt5_tick_protective_fallback"
            result.verdict = SLTPVerdict.SLTP_MT5_TICK_FALLBACK_USED
            return result

        except Exception:
            try:
                mt5.shutdown()
            except Exception:
                pass
            return None
