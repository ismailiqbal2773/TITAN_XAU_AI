"""
TITAN XAU AI - Unified Trade Reconciliation (Sprint 9.9.3.45.8.3)
==================================================================
Single helper used by run_managed_demo_micro_trade.py,
diagnose_latest_execution_receipt.py, and
collect_demo_micro_trade_forensics.py to avoid contradiction.

Canonical statuses:
  - OPEN
  - CLOSED_TP
  - CLOSED_SL
  - CLOSED_MANUAL
  - CLOSED_UNKNOWN
  - PENDING_HISTORY
  - UNKNOWN

Closed must require an actual closing deal/order, not only entry deal.

NEVER sends orders. NEVER modifies positions.
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional


# Canonical status constants
STATUS_OPEN = "OPEN"
STATUS_CLOSED_TP = "CLOSED_TP"
STATUS_CLOSED_SL = "CLOSED_SL"
STATUS_CLOSED_MANUAL = "CLOSED_MANUAL"
STATUS_CLOSED_UNKNOWN = "CLOSED_UNKNOWN"
STATUS_PENDING_HISTORY = "PENDING_HISTORY"
STATUS_UNKNOWN = "UNKNOWN"

ALL_STATUSES = [
    STATUS_OPEN, STATUS_CLOSED_TP, STATUS_CLOSED_SL,
    STATUS_CLOSED_MANUAL, STATUS_CLOSED_UNKNOWN,
    STATUS_PENDING_HISTORY, STATUS_UNKNOWN,
]


@dataclass
class TradeReconciliation:
    """Unified trade reconciliation result.

    Used by managed report, receipt diagnostic, and forensics to
    ensure consistent status determination.
    """
    status: str = STATUS_UNKNOWN
    entry_deal_ticket: int = 0
    close_deal_ticket: int = 0
    position_id: int = 0
    entry_price: float = 0.0
    close_price: float = 0.0
    entry_time: str = ""
    close_time: str = ""
    close_reason: str = ""
    gross_profit: float = 0.0
    spread_cost: float = 0.0
    commission_cost: float = 0.0
    slippage_cost: float = 0.0
    swap_cost: float = 0.0
    net_profit: float = 0.0
    gross_R: float = 0.0
    net_R: float = 0.0
    gross_RR: float = 0.0
    net_RR: float = 0.0
    sl_modify_events: int = 0
    tp_modify_events: int = 0
    # Source of reconciliation
    source: str = ""  # "positions_get", "history_deals_get", "receipt", "none"
    has_closing_deal: bool = False
    has_entry_deal: bool = False
    blockers: list[str] = field(default_factory=list)
    timestamp_utc: str = ""

    def __post_init__(self):
        if not self.timestamp_utc:
            self.timestamp_utc = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return asdict(self)


def reconcile_trade(*, position_ticket: int = 0,
                    open_positions: list = None,
                    history_deals: list = None,
                    entry_price: float = 0.0,
                    initial_sl: float = 0.0,
                    initial_tp: float = 0.0,
                    lot: float = 0.01,
                    contract_size: float = 100.0,
                    spread: float = 0.0,
                    commission_per_lot: float = 0.0,
                    slippage: float = 0.0,
                    swap_per_lot_per_night: float = 0.0,
                    nights_held: int = 0,
                    sl_modify_events: int = 0,
                    tp_modify_events: int = 0) -> TradeReconciliation:
    """Reconcile a single trade using unified logic.

    NEVER sends orders. Returns TradeReconciliation only.

    Logic:
      1. If position is in open_positions -> status = OPEN
      2. If position is NOT in open_positions:
         a. Search history_deals for closing deal (entry=OUT)
         b. If found: determine close_reason (TP/SL/manual) from close_price
         c. If not found: status = PENDING_HISTORY or UNKNOWN
      3. Closed status requires an actual closing deal (has_closing_deal=True)
    """
    result = TradeReconciliation(
        position_id=position_ticket,
        entry_price=entry_price,
        sl_modify_events=sl_modify_events,
        tp_modify_events=tp_modify_events,
    )

    open_positions = open_positions or []
    history_deals = history_deals or []

    # Step 1: Check if position is still open
    is_open = False
    for p in open_positions:
        if getattr(p, "ticket", 0) == position_ticket:
            is_open = True
            result.entry_price = float(getattr(p, "price_open", entry_price) or entry_price)
            result.close_price = float(getattr(p, "price_current", 0) or 0)
            break

    if is_open:
        result.status = STATUS_OPEN
        result.source = "positions_get"
        result.has_entry_deal = True
        result.has_closing_deal = False
        result.close_reason = "still_open"
        return result

    # Step 2: Position not open - search history for closing deal
    matching_deals = []
    for d in history_deals:
        d_pos_id = getattr(d, "position_id", 0)
        d_ticket = getattr(d, "ticket", 0)
        if d_pos_id == position_ticket or d_ticket == position_ticket:
            matching_deals.append(d)

    if not matching_deals:
        # No history found
        result.status = STATUS_PENDING_HISTORY
        result.source = "history_deals_get_empty"
        result.has_entry_deal = False
        result.has_closing_deal = False
        result.blockers.append("NO_HISTORY_DEALS_FOUND")
        return result

    # Find entry deal (entry=0, DEAL_ENTRY_IN) and close deal (entry=1, DEAL_ENTRY_OUT)
    entry_deal = None
    close_deal = None
    for d in matching_deals:
        entry_type = getattr(d, "entry", -1)
        if entry_type == 0:  # DEAL_ENTRY_IN
            entry_deal = d
        elif entry_type == 1:  # DEAL_ENTRY_OUT
            close_deal = d

    if entry_deal:
        result.entry_deal_ticket = getattr(entry_deal, "ticket", 0)
        result.entry_price = float(getattr(entry_deal, "price", entry_price) or entry_price)
        result.entry_time = str(getattr(entry_deal, "time", ""))
        result.has_entry_deal = True
    else:
        result.has_entry_deal = False

    if close_deal:
        result.close_deal_ticket = getattr(close_deal, "ticket", 0)
        result.close_price = float(getattr(close_deal, "price", 0) or 0)
        result.close_time = str(getattr(close_deal, "time", ""))
        result.has_closing_deal = True
        result.source = "history_deals_get"

        # Determine close reason
        close_comment = str(getattr(close_deal, "comment", "") or "").lower()
        profit = float(getattr(close_deal, "profit", 0) or 0)

        # Check if closed by TP
        if initial_tp > 0 and abs(result.close_price - initial_tp) < 0.01:
            result.status = STATUS_CLOSED_TP
            result.close_reason = "tp_hit"
        elif initial_sl > 0 and abs(result.close_price - initial_sl) < 0.01:
            result.status = STATUS_CLOSED_SL
            result.close_reason = "sl_hit"
        elif "[sl" in close_comment or "sl " in close_comment:
            result.status = STATUS_CLOSED_SL
            result.close_reason = f"sl_hit_comment: {close_comment}"
        elif "[tp" in close_comment or "tp " in close_comment:
            result.status = STATUS_CLOSED_TP
            result.close_reason = f"tp_hit_comment: {close_comment}"
        elif profit != 0:
            result.status = STATUS_CLOSED_MANUAL
            result.close_reason = "manual_close"
        else:
            result.status = STATUS_CLOSED_UNKNOWN
            result.close_reason = "unknown_close"

        # Calculate gross profit
        if result.entry_price > 0 and result.close_price > 0:
            # Assume BUY direction for profit calc (caller can override)
            gross_profit = (result.close_price - result.entry_price) * lot * contract_size
            result.gross_profit = round(gross_profit, 4)

        # Calculate costs
        result.spread_cost = round(spread * lot * contract_size, 4)
        result.commission_cost = round(commission_per_lot * lot, 4)
        result.slippage_cost = round(slippage * 2 * lot * contract_size, 4)
        result.swap_cost = round(swap_per_lot_per_night * lot * nights_held, 4)

        total_cost = result.spread_cost + result.commission_cost + result.slippage_cost + result.swap_cost
        result.net_profit = round(result.gross_profit - total_cost, 4)

        # Calculate R and RR
        R = abs(entry_price - initial_sl) * lot * contract_size if initial_sl > 0 else 0.0
        result.gross_R = round(result.gross_profit / R, 4) if R > 0 else 0.0
        result.net_R = round(result.net_profit / R, 4) if R > 0 else 0.0
        if initial_sl != entry_price and initial_sl > 0:
            result.gross_RR = round(abs(initial_tp - entry_price) / abs(entry_price - initial_sl), 4)
            cost_per_unit = total_cost / (lot * contract_size) if lot > 0 else 0.0
            net_tp_distance = abs(initial_tp - entry_price) - cost_per_unit
            result.net_RR = round(net_tp_distance / abs(entry_price - initial_sl), 4)
    else:
        # Entry deal found but no close deal
        result.status = STATUS_PENDING_HISTORY
        result.source = "history_deals_get_no_close"
        result.has_closing_deal = False
        result.blockers.append("ENTRY_DEAL_FOUND_BUT_NO_CLOSE_DEAL")

    return result
