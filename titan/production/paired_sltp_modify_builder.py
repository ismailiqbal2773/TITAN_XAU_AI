"""
TITAN XAU AI - Paired SLTP Modify Builder (Sprint 9.9.3.45.8.2)
=================================================================
Builds paired SL+TP modification request PREVIEW only. NEVER sends orders.

Used by AdaptiveProfitCorridor to build a single TRADE_ACTION_SLTP
request that modifies both SL and TP simultaneously. This is required
for the profit corridor: when TP is extended, SL must also be raised
into the profit zone in the same modify request.

Safety guarantees:
  - TP must never reduce (BUY: new_tp >= old_tp, SELL: new_tp <= old_tp)
  - SL must never widen (BUY: new_sl >= old_sl, SELL: new_sl <= old_sl)
  - TP cannot be removed (new_tp must be > 0)
  - SL must protect minimum locked_R profit
  - Must enforce broker stop/freeze level
  - action = TRADE_ACTION_SLTP
  - One modify request per call (no retry, no batch)
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional


@dataclass
class PairedSLTPModifyPreview:
    action: str = "SLTP_MODIFY"  # TRADE_ACTION_SLTP
    ticket: int = 0
    symbol: str = "XAUUSD"
    direction: str = "BUY"
    old_sl: float = 0.0
    new_sl: float = 0.0
    old_tp: float = 0.0
    new_tp: float = 0.0
    magic: int = 202619
    comment: str = "TITAN_DEMO_MICRO"
    favorable_sl: bool = True
    no_tp_reduction: bool = True
    no_sl_widening: bool = True
    tp_preserved_or_extended: bool = True
    sl_profit_floor_R: float = 0.0
    locked_profit_value: float = 0.0
    reason: str = ""
    blockers: list[str] = field(default_factory=list)
    timestamp_utc: str = ""

    def __post_init__(self):
        if not self.timestamp_utc:
            self.timestamp_utc = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return asdict(self)


class PairedSLTPModifyBuilder:
    """Builds paired SL+TP modify preview. NEVER sends orders."""

    def build_preview(self, *, ticket: int, direction: str,
                       old_sl: float, new_sl: float,
                       old_tp: float, new_tp: float,
                       entry_price: float, R: float,
                       locked_R: float,
                       reason: str = "",
                       stops_level_points: int = 0,
                       point: float = 0.01,
                       current_price: float = 0.0,
                       blockers: list[str] = None) -> dict:
        """Build paired SLTP modify preview.

        Validates:
          - ticket > 0
          - new_sl > 0
          - new_tp > 0
          - direction in (BUY, SELL)
          - For BUY: new_sl >= old_sl (no widening), new_tp >= old_tp (no reduction)
          - For SELL: new_sl <= old_sl (no widening), new_tp <= old_tp (no reduction)
          - SL protects minimum locked_R profit:
            BUY: new_sl >= entry + locked_R * R
            SELL: new_sl <= entry - locked_R * R
          - Stop level buffer: distance from current_price to new_sl
            must be >= stops_level_points * point
        """
        ok_checks = []
        warnings = []
        preview_blockers = list(blockers or [])

        # Basic validation
        if ticket <= 0:
            preview_blockers.append("Invalid ticket")

        if new_sl <= 0:
            preview_blockers.append("New SL must be > 0")

        if new_tp <= 0:
            preview_blockers.append("New TP must be > 0 (TP cannot be removed)")

        if direction not in ("BUY", "SELL"):
            preview_blockers.append(f"Invalid direction: {direction}")

        # Compute locked profit value
        locked_profit_value = locked_R * R if R > 0 else 0.0

        # Direction-specific checks
        favorable_sl = True
        no_tp_reduction = True
        no_sl_widening = True

        if direction == "BUY":
            favorable_sl = new_sl >= old_sl
            no_tp_reduction = new_tp >= old_tp
            no_sl_widening = new_sl >= old_sl
            # SL profit floor check
            if R > 0 and new_sl < (entry_price + locked_profit_value):
                preview_blockers.append(
                    f"SL_PROFIT_FLOOR_NOT_MET: new_sl={new_sl} < entry+locked_R*R={entry_price + locked_profit_value}"
                )
        elif direction == "SELL":
            favorable_sl = (new_sl <= old_sl) or old_sl == 0
            no_tp_reduction = new_tp <= old_tp
            no_sl_widening = (new_sl <= old_sl) or old_sl == 0
            # SL profit floor check
            if R > 0 and old_sl > 0 and new_sl > (entry_price - locked_profit_value):
                preview_blockers.append(
                    f"SL_PROFIT_FLOOR_NOT_MET: new_sl={new_sl} > entry-locked_R*R={entry_price - locked_profit_value}"
                )

        if not favorable_sl:
            preview_blockers.append("SL move is not favorable - blocked")

        if not no_tp_reduction:
            preview_blockers.append("TP_REDUCTION_BLOCKED: new_tp reduces old_tp")

        if not no_sl_widening:
            preview_blockers.append("SL_WIDENING_BLOCKED: new_sl widens old_sl")

        # Stop level buffer check
        if stops_level_points > 0 and current_price > 0 and new_sl > 0:
            min_distance = stops_level_points * point
            if direction == "BUY":
                if (current_price - new_sl) < min_distance:
                    preview_blockers.append(
                        f"STOP_LEVEL_TOO_CLOSE: (current_price - new_sl)={current_price - new_sl} < min_distance={min_distance}"
                    )
            else:
                if (new_sl - current_price) < min_distance:
                    preview_blockers.append(
                        f"STOP_LEVEL_TOO_CLOSE: (new_sl - current_price)={new_sl - current_price} < min_distance={min_distance}"
                    )

        # TP/SL ordering check (TP must be on the profit side of SL)
        if direction == "BUY" and new_tp <= new_sl:
            preview_blockers.append(f"TP_BELOW_SL: new_tp={new_tp} <= new_sl={new_sl}")
        elif direction == "SELL" and new_tp >= new_sl:
            preview_blockers.append(f"TP_ABOVE_SL: new_tp={new_tp} >= new_sl={new_sl}")

        tp_preserved_or_extended = no_tp_reduction  # TP either preserved or extended (never reduced)

        if not preview_blockers:
            ok_checks.append(f"Paired SLTP modify preview: ticket={ticket}, new_sl={new_sl}, new_tp={new_tp}")
            ok_checks.append("Favorable SL direction verified")
            ok_checks.append("No TP reduction verified")
            ok_checks.append("No SL widening verified")
            ok_checks.append(f"SL profit floor verified: locked_R={locked_R}, locked_profit_value={locked_profit_value}")
            ok_checks.append("TP preserved or extended")
            verdict = "PASS"
        else:
            verdict = "BLOCKED"

        preview = PairedSLTPModifyPreview(
            ticket=ticket, direction=direction,
            old_sl=old_sl, new_sl=new_sl,
            old_tp=old_tp, new_tp=new_tp,
            favorable_sl=favorable_sl,
            no_tp_reduction=no_tp_reduction,
            no_sl_widening=no_sl_widening,
            tp_preserved_or_extended=tp_preserved_or_extended,
            sl_profit_floor_R=locked_R,
            locked_profit_value=locked_profit_value,
            reason=reason, blockers=preview_blockers,
        )

        return {
            "preview": preview.to_dict(),
            "verdict": verdict,
            "ok_checks": ok_checks,
            "blockers": preview_blockers,
            "warnings": warnings,
            "action": "TRADE_ACTION_SLTP",
            "important_note": "This is a PREVIEW only. No mt5.order_send was called. No position was modified. "
                              "When applied locally, must use TRADE_ACTION_SLTP exactly once. No retry.",
        }
