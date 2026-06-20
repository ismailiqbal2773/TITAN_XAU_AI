"""
TITAN Reconciliation Engine
=============================
Reconciles local DB state against broker (MT5) truth.

Three reconciliation types:
  1. Position reconciliation: local positions table vs MT5 PositionsGet()
  2. Pending order reconciliation: local orders table vs MT5 OrdersGet()
  3. Trade history reconciliation: local trades table vs MT5 HistoryGet*()

For each, detect drift and produce a ReconciliationReport listing:
  - missing locally (in broker, not in DB)
  - missing in broker (in DB, not in broker)
  - mismatched (ticket exists both sides but fields differ)

Reconciliation NEVER auto-closes positions or cancels orders.
It only LOGS drift and updates DB to match broker truth.
Manual intervention required for risky actions.
"""
from __future__ import annotations
import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Optional
from collections import defaultdict

logger = logging.getLogger(__name__)


@dataclass
class DriftItem:
    ticket: int
    drift_type: str          # missing_locally | missing_in_broker | mismatched
    field: str | None = None
    local_value: object = None
    broker_value: object = None
    severity: str = "WARN"   # INFO | WARN | ERROR


@dataclass
class ReconciliationReport:
    timestamp: float
    position_drifts: list[DriftItem] = field(default_factory=list)
    order_drifts: list[DriftItem] = field(default_factory=list)
    trade_drifts: list[DriftItem] = field(default_factory=list)
    local_positions: int = 0
    broker_positions: int = 0
    local_orders: int = 0
    broker_orders: int = 0
    reconciled: bool = False
    error: str | None = None

    @property
    def total_drifts(self) -> int:
        return (len(self.position_drifts) + len(self.order_drifts)
                + len(self.trade_drifts))

    @property
    def is_clean(self) -> bool:
        return self.reconciled and self.total_drifts == 0

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "local_positions": self.local_positions,
            "broker_positions": self.broker_positions,
            "local_orders": self.local_orders,
            "broker_orders": self.broker_orders,
            "position_drifts": [d.__dict__ for d in self.position_drifts],
            "order_drifts": [d.__dict__ for d in self.order_drifts],
            "trade_drifts": [d.__dict__ for d in self.trade_drifts],
            "total_drifts": self.total_drifts,
            "is_clean": self.is_clean,
            "error": self.error,
        }


class ReconciliationEngine:
    """Reconcile DB state with broker state."""

    def __init__(self, db, broker=None, journal=None):
        self._db = db
        self._broker = broker
        self._journal = journal

    def _has_mt5(self) -> bool:
        """Check if broker is available (not in Linux stub mode)."""
        if not self._broker:
            return False
        try:
            return self._broker._mt5_initialized
        except Exception:
            return False

    async def reconcile_positions(self, auto_fix: bool = False) -> list[DriftItem]:
        """Reconcile positions table with MT5 PositionsGet."""
        drifts: list[DriftItem] = []
        from titan.database.layer import PositionRepository
        repo = PositionRepository(self._db)
        local = await repo.get_all_positions()
        local_by_ticket = {p["ticket"]: p for p in local}

        broker_positions = []
        if self._has_mt5():
            import MetaTrader5 as mt5
            broker_positions = list(mt5.positions_get() or [])
        broker_by_ticket = {p.ticket: p for p in broker_positions}

        # Missing locally (in broker, not in DB)
        for ticket, bpos in broker_by_ticket.items():
            if ticket not in local_by_ticket:
                drifts.append(DriftItem(
                    ticket=ticket, drift_type="missing_locally",
                    broker_value=str(bpos._asdict())[:200],
                    severity="ERROR",
                ))
                if auto_fix and self._journal:
                    await self._journal.log(
                        "reconcile", "positions", "drift_detected",
                        {"ticket": ticket, "type": "missing_locally"},
                        severity="ERROR",
                    )

        # Missing in broker (in DB, not in broker)
        for ticket, lpos in local_by_ticket.items():
            if ticket not in broker_by_ticket:
                drifts.append(DriftItem(
                    ticket=ticket, drift_type="missing_in_broker",
                    local_value=str(lpos)[:200],
                    severity="ERROR",
                ))
                if auto_fix:
                    # Position no longer in broker → close in DB
                    await repo.delete_position(ticket)
                    if self._journal:
                        await self._journal.log(
                            "reconcile", "positions", "drift_fixed",
                            {"ticket": ticket, "action": "deleted_local"},
                            severity="WARN",
                        )

        # Mismatched (ticket exists both sides, fields differ)
        for ticket, lpos in local_by_ticket.items():
            if ticket not in broker_by_ticket:
                continue
            bpos = broker_by_ticket[ticket]
            # Compare key fields
            for field_name, local_val, broker_val in [
                ("volume", lpos.get("volume"), getattr(bpos, "volume", None)),
                ("direction", lpos.get("direction"), int(getattr(bpos, "type", 0))),
                ("entry_price", lpos.get("entry_price"), getattr(bpos, "price_open", None)),
            ]:
                if local_val is not None and broker_val is not None:
                    if abs(float(local_val) - float(broker_val)) > 1e-6:
                        drifts.append(DriftItem(
                            ticket=ticket, drift_type="mismatched",
                            field=field_name,
                            local_value=local_val, broker_value=broker_val,
                            severity="WARN",
                        ))
                        if auto_fix and self._journal:
                            await self._journal.log(
                                "reconcile", "positions", "drift_detected",
                                {"ticket": ticket, "field": field_name,
                                 "local": local_val, "broker": broker_val},
                                severity="WARN",
                            )

        if self._journal:
            await self._journal.log(
                "reconcile", "positions", "completed",
                {"local": len(local), "broker": len(broker_positions),
                 "drifts": len(drifts)},
            )
        return drifts

    async def reconcile_orders(self, auto_fix: bool = False) -> list[DriftItem]:
        """Reconcile orders table with MT5 OrdersGet."""
        drifts: list[DriftItem] = []
        from titan.database.layer import OrderRepository
        repo = OrderRepository(self._db)
        # Get local OPEN orders (state != FILLED, REJECTED, CANCELLED)
        async with self._db._lock:
            cur = await self._db.conn.execute(
                "SELECT * FROM orders WHERE state NOT IN ('FILLED','REJECTED','CANCELLED')"
            )
            rows = await cur.fetchall()
        local = [dict(r) for r in rows]
        local_by_ticket = {o.get("order_ticket") or o.get("id"): o for o in local}

        broker_orders = []
        if self._has_mt5():
            import MetaTrader5 as mt5
            broker_orders = list(mt5.orders_get() or [])
        broker_by_ticket = {o.ticket: o for o in broker_orders}

        for ticket, bord in broker_by_ticket.items():
            if ticket not in local_by_ticket:
                drifts.append(DriftItem(
                    ticket=ticket, drift_type="missing_locally",
                    broker_value=str(bord._asdict())[:200],
                    severity="WARN",
                ))

        for ticket, lord in local_by_ticket.items():
            if ticket not in broker_by_ticket:
                drifts.append(DriftItem(
                    ticket=ticket, drift_type="missing_in_broker",
                    local_value=str(lord)[:200],
                    severity="WARN",
                ))
                if auto_fix:
                    # Mark as cancelled in DB
                    async with self._db._lock:
                        await self._db.conn.execute(
                            "UPDATE orders SET state = 'CANCELLED' "
                            "WHERE idempotency_key = ?",
                            (lord.get("idempotency_key"),),
                        )
                        await self._db.conn.commit()
                    if self._journal:
                        await self._journal.log(
                            "reconcile", "orders", "drift_fixed",
                            {"ticket": ticket, "action": "marked_cancelled"},
                            severity="WARN",
                        )

        if self._journal:
            await self._journal.log(
                "reconcile", "orders", "completed",
                {"local": len(local), "broker": len(broker_orders),
                 "drifts": len(drifts)},
            )
        return drifts

    async def reconcile_trades(self, since_ts: float = 0.0) -> list[DriftItem]:
        """Reconcile trades table with MT5 history."""
        drifts: list[DriftItem] = []
        if not self._has_mt5():
            return drifts
        import MetaTrader5 as mt5
        from datetime import datetime, timezone
        from_ts = int(since_ts) if since_ts else 0
        broker_deals = list(mt5.history_deals_get(from_ts, time.time()) or [])
        broker_tickets = {d.ticket for d in broker_deals}

        async with self._db._lock:
            cur = await self._db.conn.execute(
                "SELECT ticket, status FROM trades WHERE opened_at >= ?",
                (from_ts,),
            )
            rows = await cur.fetchall()
        local_tickets = {r["ticket"] for r in rows if r["ticket"]}

        # Trades in broker history, not in DB → potential missed trade
        for d in broker_deals:
            if d.ticket not in local_tickets:
                drifts.append(DriftItem(
                    ticket=d.ticket, drift_type="missing_locally",
                    broker_value=str(d._asdict())[:200],
                    severity="ERROR",
                ))

        # Trades in DB, not in broker → potential phantom trade
        for t in local_tickets:
            if t not in broker_tickets:
                drifts.append(DriftItem(
                    ticket=t, drift_type="missing_in_broker",
                    severity="ERROR",
                ))

        if self._journal:
            await self._journal.log(
                "reconcile", "trades", "completed",
                {"broker_deals": len(broker_deals),
                 "local_trades": len(local_tickets),
                 "drifts": len(drifts)},
            )
        return drifts

    async def full_reconciliation(self, auto_fix: bool = False) -> ReconciliationReport:
        """Run all reconciliations."""
        report = ReconciliationReport(timestamp=time.time())
        try:
            report.position_drifts = await self.reconcile_positions(auto_fix=auto_fix)
            report.order_drifts = await self.reconcile_orders(auto_fix=auto_fix)
            report.trade_drifts = await self.reconcile_trades()
            # Get counts
            from titan.database.layer import PositionRepository
            repo = PositionRepository(self._db)
            report.local_positions = await repo.get_position_count()
            if self._has_mt5():
                import MetaTrader5 as mt5
                report.broker_positions = len(mt5.positions_get() or [])
                report.broker_orders = len(mt5.orders_get() or [])
            report.local_orders = len(
                await self._db.query_all(
                    "SELECT * FROM orders WHERE state NOT IN ('FILLED','REJECTED','CANCELLED')"
                )
            )
            report.reconciled = True
        except Exception as e:
            report.error = str(e)
            logger.error(f"Reconciliation failed: {e}")
            if self._journal:
                await self._journal.log(
                    "reconcile", "system", "failed",
                    {"error": str(e)[:200]}, severity="ERROR",
                )
        return report
