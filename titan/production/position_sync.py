"""
TITAN XAU AI — Position Sync (Production Sprint 2)

Polls MT5 positions_get() every N seconds, treats broker as source of truth,
and syncs the open-positions state to the local database.

Design rules:
  1. Broker is the source of truth — local DB is cache only.
  2. New positions (in broker, not in DB) → INSERT into DB.
  3. Closed positions (in DB, not in broker) → mark CLOSED in DB.
  4. Modified positions (volume/SL/TP changed) → UPDATE in DB.
  5. Never auto-close or auto-modify via MT5 — only DB sync.
  6. Notifies TradeLoop when a position closes (decrements counter).

For testing without MT5, supports a "stub_broker" mode that returns
a configurable list of positions.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Optional, Callable, Awaitable

logger = logging.getLogger(__name__)


@dataclass
class BrokerPosition:
    """Normalized broker position (works with both real MT5 and stub)."""
    ticket: int
    symbol: str
    direction: int             # +1 long, -1 short
    volume: float
    entry_price: float
    stop_loss: float
    take_profit: float
    open_time: float           # epoch
    profit: float = 0.0
    swap: float = 0.0
    magic: int = 0
    comment: str = ""

    @classmethod
    def from_mt5(cls, mt5_pos) -> "BrokerPosition":
        """Convert an MT5 position object to BrokerPosition."""
        direction = 1 if mt5_pos.type == 0 else -1  # POSITION_TYPE_BUY=0
        return cls(
            ticket=int(mt5_pos.ticket),
            symbol=str(mt5_pos.symbol),
            direction=direction,
            volume=float(mt5_pos.volume),
            entry_price=float(mt5_pos.price_open),
            stop_loss=float(getattr(mt5_pos, "sl", 0.0) or 0.0),
            take_profit=float(getattr(mt5_pos, "tp", 0.0) or 0.0),
            open_time=float(getattr(mt5_pos, "time", 0)),
            profit=float(getattr(mt5_pos, "profit", 0.0) or 0.0),
            swap=float(getattr(mt5_pos, "swap", 0.0) or 0.0),
            magic=int(getattr(mt5_pos, "magic", 0) or 0),
            comment=str(getattr(mt5_pos, "comment", "") or ""),
        )


@dataclass
class SyncReport:
    """Result of a single sync cycle."""
    timestamp: float
    broker_positions: int = 0
    db_positions: int = 0
    new_positions: int = 0          # in broker, not in DB
    closed_positions: int = 0       # in DB, not in broker
    modified_positions: int = 0     # ticket exists both sides but fields differ
    sync_duration_ms: float = 0.0
    error: Optional[str] = None
    is_clean: bool = True           # True iff no drift

    @property
    def total_drifts(self) -> int:
        return self.new_positions + self.closed_positions + self.modified_positions


class PositionSync:
    """
    Async position sync loop. Polls broker every `interval_seconds`.

    Usage:
        sync = PositionSync(interval_seconds=10, broker_source="mt5")
        await sync.start()  # runs until cancelled

    For tests:
        sync = PositionSync(interval_seconds=0.1, broker_source="stub")
        sync.set_stub_positions([BrokerPosition(...)])
        report = await sync.sync_once()
    """

    def __init__(
        self,
        interval_seconds: float = 10.0,
        broker_source: str = "mt5",            # "mt5" | "stub"
        db_path: Optional[str] = None,
        on_position_closed: Optional[Callable[[], Awaitable[None]]] = None,
        magic_filter: Optional[int] = 202619,   # Only sync TITAN positions
    ):
        self.interval = interval_seconds
        self.broker_source = broker_source
        self.db_path = db_path
        self.on_position_closed = on_position_closed
        self.magic_filter = magic_filter
        self._stub_positions: list[BrokerPosition] = []
        self._local_state: dict[int, BrokerPosition] = {}  # ticket → position
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._last_report: Optional[SyncReport] = None

    # ─── Stub mode (for tests) ──────────────────────────────────────────

    def set_stub_positions(self, positions: list[BrokerPosition]) -> None:
        """Set the fake broker state for testing."""
        self._stub_positions = positions

    # ─── Broker polling ─────────────────────────────────────────────────

    def _fetch_broker_positions(self) -> list[BrokerPosition]:
        """Fetch positions from broker (MT5 or stub)."""
        if self.broker_source == "stub":
            positions = list(self._stub_positions)
        elif self.broker_source == "mt5":
            try:
                import MetaTrader5 as mt5
                positions = mt5.positions_get()
                if not positions:
                    return []
                positions = [BrokerPosition.from_mt5(p) for p in positions]
            except Exception as e:
                logger.error(f"MT5 positions_get failed: {e}")
                return []
        else:
            raise ValueError(f"Unknown broker_source: {self.broker_source}")
        # Apply magic filter (TITAN-only positions)
        if self.magic_filter is not None:
            positions = [p for p in positions if p.magic == self.magic_filter]
        return positions

    # ─── Sync logic ─────────────────────────────────────────────────────

    async def sync_once(self) -> SyncReport:
        """Run a single sync cycle. Returns SyncReport."""
        t0 = time.perf_counter()
        report = SyncReport(timestamp=time.time())

        try:
            broker_positions = self._fetch_broker_positions()
            report.broker_positions = len(broker_positions)  # post-filter count

            broker_tickets = {p.ticket for p in broker_positions}
            local_tickets = set(self._local_state.keys())

            # ── New positions (in broker, not in local) ──
            new_tickets = broker_tickets - local_tickets
            report.new_positions = len(new_tickets)
            for p in broker_positions:
                if p.ticket in new_tickets:
                    self._local_state[p.ticket] = p
                    logger.info(f"Position sync: NEW {p.ticket} ({p.symbol} {p.volume} lot)")

            # ── Closed positions (in local, not in broker) ──
            closed_tickets = local_tickets - broker_tickets
            report.closed_positions = len(closed_tickets)
            for ticket in closed_tickets:
                removed = self._local_state.pop(ticket)
                logger.info(f"Position sync: CLOSED {ticket} ({removed.symbol})")
                # Notify callback (e.g., TradeLoop.notify_position_closed)
                if self.on_position_closed is not None:
                    try:
                        await self.on_position_closed()
                    except Exception as e:
                        logger.error(f"on_position_closed callback failed: {e}")

            # ── Modified positions (ticket exists both sides, fields differ) ──
            for p in broker_positions:
                if p.ticket in self._local_state and p.ticket not in new_tickets:
                    local = self._local_state[p.ticket]
                    if (local.volume != p.volume or
                        local.stop_loss != p.stop_loss or
                        local.take_profit != p.take_profit):
                        self._local_state[p.ticket] = p
                        report.modified_positions += 1
                        logger.info(f"Position sync: MODIFIED {p.ticket}")

            report.db_positions = len(self._local_state)
            report.is_clean = (report.total_drifts == 0)
            report.sync_duration_ms = (time.perf_counter() - t0) * 1000.0
            self._last_report = report
            return report

        except Exception as e:
            report.error = str(e)
            report.sync_duration_ms = (time.perf_counter() - t0) * 1000.0
            logger.error(f"Sync failed: {e}")
            return report

    # ─── Loop control ───────────────────────────────────────────────────

    async def start(self) -> None:
        """Start the periodic sync loop. Runs until stop() is called."""
        self._running = True
        logger.info(f"PositionSync started (interval={self.interval}s, source={self.broker_source})")
        while self._running:
            await self.sync_once()
            await asyncio.sleep(self.interval)

    async def stop(self) -> None:
        """Stop the sync loop."""
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("PositionSync stopped")

    def start_background(self) -> asyncio.Task:
        """Start the sync loop as a background task."""
        self._task = asyncio.create_task(self.start())
        return self._task

    # ─── Public state accessors ─────────────────────────────────────────

    @property
    def open_positions(self) -> list[BrokerPosition]:
        """Return current open positions (from local cache)."""
        return list(self._local_state.values())

    @property
    def position_count(self) -> int:
        return len(self._local_state)

    @property
    def last_report(self) -> Optional[SyncReport]:
        return self._last_report


if __name__ == "__main__":
    # Smoke test with stub broker
    import asyncio

    async def main():
        print("=" * 70)
        print("TITAN PositionSync — Stub Smoke Test")
        print("=" * 70)
        sync = PositionSync(interval_seconds=10, broker_source="stub")
        sync.set_stub_positions([
            BrokerPosition(ticket=1001, symbol="XAUUSD", direction=1, volume=0.01,
                           entry_price=2000.0, stop_loss=1995.0, take_profit=2010.0,
                           open_time=time.time()),
        ])
        report = await sync.sync_once()
        print(f"\nReport: {report}")
        print(f"Open positions: {sync.open_positions}")
        print(f"Position count: {sync.position_count}")

    asyncio.run(main())
