"""
TITAN XAU AI — Virtual Position Ledger (Sprint 9.8)
=====================================================

Tracks virtual positions for dry-run/shadow mode. No real MT5 orders.
Each dry-run accepted trade becomes a virtual OPEN position that is
updated on every heartbeat/bar until SL/TP/AI-exit closes it.

Safety:
  - NEVER sends real MT5 orders
  - All positions are virtual/shadow only
  - PnL calculated with costs (spread, commission, slippage, swap)
"""
from __future__ import annotations
import logging
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from titan.production.trade_journal import TradeJournal, EventType

logger = logging.getLogger(__name__)


class VirtualPositionStatus(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class VirtualCloseReason(str, Enum):
    SL_HIT = "SL_HIT"
    TP_HIT = "TP_HIT"
    AI_EXIT_CLOSE = "AI_EXIT_CLOSE"
    MAX_HOLDING_EXIT = "MAX_HOLDING_EXIT"
    STALE_POSITION_EXIT = "STALE_POSITION_EXIT"
    PROFIT_LOCK_EXIT = "PROFIT_LOCK_EXIT"
    EQUITY_PROTECTION_EXIT = "EQUITY_PROTECTION_EXIT"
    CAPITAL_PRESERVATION_EXIT = "CAPITAL_PRESERVATION_EXIT"
    REGIME_RISK_EXIT = "REGIME_RISK_EXIT"
    ALPHA_DECAY_EXIT = "ALPHA_DECAY_EXIT"
    MANUAL_GOVERNANCE_BLOCK = "MANUAL_GOVERNANCE_BLOCK"


# Sprint 9.8 virtual lifecycle events
class VirtualEventType(str, Enum):
    VIRTUAL_POSITION_OPENED = "VIRTUAL_POSITION_OPENED"
    VIRTUAL_POSITION_UPDATED = "VIRTUAL_POSITION_UPDATED"
    VIRTUAL_SL_HIT = "VIRTUAL_SL_HIT"
    VIRTUAL_TP_HIT = "VIRTUAL_TP_HIT"
    VIRTUAL_POSITION_CLOSED = "VIRTUAL_POSITION_CLOSED"
    NET_PNL_CALCULATED = "NET_PNL_CALCULATED"
    TRADE_COSTS_ESTIMATED = "TRADE_COSTS_ESTIMATED"
    TRADE_COSTS_APPLIED = "TRADE_COSTS_APPLIED"


# Register events in EventType if not present
for _vt in VirtualEventType:
    if not hasattr(EventType, _vt.name):
        # Can't add to Enum dynamically, but we can use string values directly
        pass


@dataclass
class VirtualPosition:
    """Single virtual position tracked in dry-run."""
    position_id: str
    symbol: str
    direction: str                    # "BUY" | "SELL"
    entry_price: float
    entry_time_utc: str
    lot: float
    initial_sl: float
    initial_tp: float
    current_sl: float
    current_tp: float
    status: VirtualPositionStatus = VirtualPositionStatus.OPEN
    close_price: float = 0.0
    close_time_utc: str = ""
    close_reason: str = ""
    gross_pnl: float = 0.0
    spread_cost: float = 0.0
    commission_cost: float = 0.0
    slippage_cost: float = 0.0
    swap_cost: float = 0.0
    net_pnl: float = 0.0
    mfe: float = 0.0                  # max favorable excursion
    mae: float = 0.0                  # max adverse excursion
    r_multiple: float = 0.0
    holding_seconds: float = 0.0
    source_signal_id: str = ""
    source_decision_id: str = ""
    # Tracking
    _entry_timestamp: float = field(default_factory=time.time, repr=False)
    _max_price: float = 0.0          # for MFE/MAE (BUY)
    _min_price: float = 0.0

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        # Remove private fields
        d.pop("_entry_timestamp", None)
        d.pop("_max_price", None)
        d.pop("_min_price", None)
        return d


class VirtualPositionLedger:
    """
    Manages virtual positions for dry-run mode.

    Usage:
        ledger = VirtualPositionLedger(journal=journal)
        pos = ledger.open_position(
            symbol="XAUUSD", direction="BUY", entry_price=2000.0,
            lot=0.01, sl=1990.0, tp=2020.0,
            signal_id="sig-001", decision_id="dec-001",
        )
        # Update with new bar
        ledger.update_positions(current_price=2010.0, high=2015.0, low=2005.0)
        # Close
        ledger.close_position(pos.position_id, close_price=2015.0, reason="AI_EXIT_CLOSE")
    """

    CONTRACT_SIZE = 100.0  # XAUUSD: 1 lot = 100 oz

    def __init__(self, journal: Optional[TradeJournal] = None):
        self.journal = journal
        self._positions: dict[str, VirtualPosition] = {}
        self._closed: list[VirtualPosition] = []
        self._position_idempotency: set[str] = set()

    # ─── Public API ───────────────────────────────────────────────────────

    def open_position(
        self,
        symbol: str,
        direction: str,
        entry_price: float,
        lot: float,
        sl: float,
        tp: float,
        signal_id: str = "",
        decision_id: str = "",
        spread_cost: float = 0.0,
        commission_cost: float = 0.0,
        idempotency_key: str = "",
    ) -> VirtualPosition:
        """Open a virtual position. Returns the position."""
        if idempotency_key and idempotency_key in self._position_idempotency:
            logger.warning(f"Duplicate virtual position blocked: {idempotency_key}")
            raise ValueError(f"Duplicate position: {idempotency_key}")

        if idempotency_key:
            self._position_idempotency.add(idempotency_key)

        pos = VirtualPosition(
            position_id=str(uuid.uuid4())[:8],
            symbol=symbol,
            direction=direction.upper(),
            entry_price=entry_price,
            entry_time_utc=datetime.now(timezone.utc).isoformat(),
            lot=lot,
            initial_sl=sl,
            initial_tp=tp,
            current_sl=sl,
            current_tp=tp,
            spread_cost=spread_cost,
            commission_cost=commission_cost,
            source_signal_id=signal_id,
            source_decision_id=decision_id,
        )
        pos._max_price = entry_price
        pos._min_price = entry_price

        self._positions[pos.position_id] = pos

        self._journal_event("VIRTUAL_POSITION_OPENED", pos.to_dict())
        logger.info(f"Virtual position opened: {pos.position_id} {direction} {lot} @ {entry_price}")
        return pos

    def update_positions(
        self,
        current_price: float,
        high: float = 0.0,
        low: float = 0.0,
        spread: float = 0.0,
    ) -> list[str]:
        """
        Update all open positions with latest price data.
        Checks SL/TP hits. Returns list of closed position IDs.
        """
        closed_ids = []
        for pos_id in list(self._positions.keys()):
            pos = self._positions[pos_id]
            if pos.status != VirtualPositionStatus.OPEN:
                continue

            # Update MFE/MAE
            h = high if high > 0 else current_price
            l = low if low > 0 else current_price
            if pos.direction == "BUY":
                pos.mfe = max(pos.mfe, h - pos.entry_price)
                pos.mae = max(pos.mae, pos.entry_price - l)
            else:
                pos.mfe = max(pos.mfe, pos.entry_price - l)
                pos.mae = max(pos.mae, h - pos.entry_price)

            # Update holding time
            pos.holding_seconds = time.time() - pos._entry_timestamp

            # Check SL/TP
            sl_hit = False
            tp_hit = False
            ambiguous = False

            if pos.direction == "BUY":
                if l <= pos.current_sl:
                    sl_hit = True
                if h >= pos.current_tp:
                    tp_hit = True
            else:  # SELL
                if h >= pos.current_sl:
                    sl_hit = True
                if l <= pos.current_tp:
                    tp_hit = True

            # Handle ambiguity (both SL and TP hit in same candle)
            if sl_hit and tp_hit:
                ambiguous = True
                # Conservative: assume SL hit first
                sl_hit = True
                tp_hit = False
                logger.warning(
                    f"Ambiguous candle for {pos.position_id}: both SL and TP hit — "
                    f"conservative SL-first assumption"
                )

            if sl_hit:
                close_price = pos.current_sl
                self._close_position_internal(
                    pos, close_price, "SL_HIT", current_price, ambiguous
                )
                closed_ids.append(pos_id)
                self._journal_event("VIRTUAL_SL_HIT", {
                    "position_id": pos_id, "close_price": close_price,
                    "ambiguous": ambiguous,
                })
            elif tp_hit:
                close_price = pos.current_tp
                self._close_position_internal(
                    pos, close_price, "TP_HIT", current_price, ambiguous
                )
                closed_ids.append(pos_id)
                self._journal_event("VIRTUAL_TP_HIT", {
                    "position_id": pos_id, "close_price": close_price,
                    "ambiguous": ambiguous,
                })
            else:
                # Just update
                self._journal_event("VIRTUAL_POSITION_UPDATED", {
                    "position_id": pos_id,
                    "current_price": current_price,
                    "mfe": pos.mfe,
                    "mae": pos.mae,
                    "holding_seconds": pos.holding_seconds,
                })

        return closed_ids

    def close_position(
        self,
        position_id: str,
        close_price: float,
        reason: str,
        current_price: float = 0.0,
    ) -> Optional[VirtualPosition]:
        """Manually close a virtual position (e.g., AI exit)."""
        if position_id not in self._positions:
            logger.warning(f"Position not found: {position_id}")
            return None
        pos = self._positions[position_id]
        if pos.status != VirtualPositionStatus.OPEN:
            return None
        self._close_position_internal(pos, close_price, reason, current_price or close_price)
        return pos

    def get_open_positions(self) -> list[VirtualPosition]:
        return [p for p in self._positions.values() if p.status == VirtualPositionStatus.OPEN]

    def get_closed_positions(self) -> list[VirtualPosition]:
        return list(self._closed)

    def get_position(self, position_id: str) -> Optional[VirtualPosition]:
        return self._positions.get(position_id)

    @property
    def open_count(self) -> int:
        return len(self.get_open_positions())

    @property
    def closed_count(self) -> int:
        return len(self._closed)

    @property
    def total_count(self) -> int:
        return len(self._positions)

    # ─── Internal ─────────────────────────────────────────────────────────

    def _close_position_internal(
        self,
        pos: VirtualPosition,
        close_price: float,
        reason: str,
        current_price: float,
        ambiguous: bool = False,
    ) -> None:
        """Close a position and calculate PnL."""
        pos.status = VirtualPositionStatus.CLOSED
        pos.close_price = close_price
        pos.close_time_utc = datetime.now(timezone.utc).isoformat()
        pos.close_reason = reason
        pos.holding_seconds = time.time() - pos._entry_timestamp

        # Calculate gross PnL
        if pos.direction == "BUY":
            pos.gross_pnl = (close_price - pos.entry_price) * self.CONTRACT_SIZE * pos.lot
        else:
            pos.gross_pnl = (pos.entry_price - close_price) * self.CONTRACT_SIZE * pos.lot

        # Calculate R-multiple
        initial_risk = abs(pos.entry_price - pos.initial_sl) * self.CONTRACT_SIZE * pos.lot
        pos.r_multiple = pos.gross_pnl / initial_risk if initial_risk > 0 else 0.0

        # Net PnL = gross - costs
        pos.net_pnl = (
            pos.gross_pnl
            - pos.spread_cost
            - pos.commission_cost
            - pos.slippage_cost
            - pos.swap_cost
        )

        # Move to closed list
        self._closed.append(pos)
        # Keep in _positions dict for lookup but mark closed

        self._journal_event("VIRTUAL_POSITION_CLOSED", pos.to_dict())
        self._journal_event("NET_PNL_CALCULATED", {
            "position_id": pos.position_id,
            "gross_pnl": pos.gross_pnl,
            "spread_cost": pos.spread_cost,
            "commission_cost": pos.commission_cost,
            "slippage_cost": pos.slippage_cost,
            "swap_cost": pos.swap_cost,
            "net_pnl": pos.net_pnl,
            "r_multiple": pos.r_multiple,
        })

        logger.info(
            f"Virtual position closed: {pos.position_id} reason={reason} "
            f"gross={pos.gross_pnl:.2f} net={pos.net_pnl:.2f} R={pos.r_multiple:.2f}"
        )

    def _journal_event(self, event_type: str, data: dict) -> None:
        if self.journal is None:
            return
        try:
            # Use log_event with string event type
            self.journal.log_event(EventType.STARTUP, {"virtual_event": event_type, **data})
        except Exception:
            # Fallback: use log_heartbeat
            try:
                self.journal.log_heartbeat({"virtual_event": event_type, **data})
            except Exception:
                pass
