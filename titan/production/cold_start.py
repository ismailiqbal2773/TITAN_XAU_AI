"""
TITAN XAU AI — Cold Start Reconciliation (Production Sprint 2)

On startup, fetches broker positions and rebuilds local state from broker truth.
Prevents:
  - Duplicate trades (TradeLoop thinks no position exists, opens another)
  - Orphan positions (local DB has stale position that broker already closed)
  - State drift (local DB volume/SL/TP differs from broker)

Run this BEFORE starting the TradeLoop or PositionSync periodic loop.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from titan.production.position_sync import BrokerPosition, PositionSync

logger = logging.getLogger(__name__)


@dataclass
class ColdStartReport:
    """Result of cold-start reconciliation."""
    timestamp: float
    broker_positions: int = 0
    local_state_built: int = 0
    orphan_positions_cleared: int = 0      # local DB had positions broker doesn't
    state_drifts_corrected: int = 0        # local DB had wrong volume/SL/TP
    duration_ms: float = 0.0
    error: Optional[str] = None
    is_clean: bool = True                  # True iff no orphans + no drifts
    positions: list[dict] = field(default_factory=list)

    def __repr__(self) -> str:
        return (
            f"ColdStartReport(broker={self.broker_positions}, "
            f"local_built={self.local_state_built}, "
            f"orphans_cleared={self.orphan_positions_cleared}, "
            f"drifts_corrected={self.state_drifts_corrected}, "
            f"clean={self.is_clean}, {self.duration_ms:.1f}ms)"
        )


class ColdStartReconciler:
    """
    Reconcile broker state → local state on startup.

    Usage:
        reconciler = ColdStartReconciler(position_sync=sync)
        report = await reconciler.reconcile()
        if report.is_clean:
            # safe to start TradeLoop
            ...
        else:
            logger.warning(f"State drift detected: {report}")
    """

    def __init__(self, position_sync: PositionSync):
        self.position_sync = position_sync

    async def reconcile(self) -> ColdStartReport:
        """
        Fetch broker positions and rebuild local state.
        Returns a ColdStartReport.
        """
        t0 = time.perf_counter()
        report = ColdStartReport(timestamp=time.time())

        try:
            # ── Step 1: Fetch broker truth ──
            broker_positions = self.position_sync._fetch_broker_positions()
            report.broker_positions = len(broker_positions)

            # ── Step 2: Detect orphan positions in local state ──
            # (positions in local DB that broker doesn't have)
            broker_tickets = {p.ticket for p in broker_positions}
            local_tickets = set(self.position_sync._local_state.keys())
            orphan_tickets = local_tickets - broker_tickets
            report.orphan_positions_cleared = len(orphan_tickets)

            for ticket in orphan_tickets:
                removed = self.position_sync._local_state.pop(ticket)
                logger.warning(
                    f"COLD START: orphan position {ticket} ({removed.symbol}) "
                    f"cleared from local state — broker has no record"
                )

            # ── Step 3: Detect state drifts (ticket exists both sides but fields differ) ──
            for p in broker_positions:
                if p.ticket in self.position_sync._local_state:
                    local = self.position_sync._local_state[p.ticket]
                    if (local.volume != p.volume or
                        local.stop_loss != p.stop_loss or
                        local.take_profit != p.take_profit or
                        local.direction != p.direction):
                        report.state_drifts_corrected += 1
                        logger.warning(
                            f"COLD START: state drift on ticket {p.ticket} — "
                            f"local(vol={local.volume}, sl={local.stop_loss}, tp={local.take_profit}) "
                            f"!= broker(vol={p.volume}, sl={p.stop_loss}, tp={p.take_profit})"
                        )

            # ── Step 4: Rebuild local state from broker truth ──
            # Clear and rebuild (broker is source of truth)
            self.position_sync._local_state.clear()
            for p in broker_positions:
                self.position_sync._local_state[p.ticket] = p

            report.local_state_built = len(self.position_sync._local_state)
            report.positions = [
                {
                    "ticket": p.ticket,
                    "symbol": p.symbol,
                    "direction": p.direction,
                    "volume": p.volume,
                    "entry_price": p.entry_price,
                    "stop_loss": p.stop_loss,
                    "take_profit": p.take_profit,
                }
                for p in broker_positions
            ]
            report.is_clean = (report.orphan_positions_cleared == 0 and
                               report.state_drifts_corrected == 0)
            report.duration_ms = (time.perf_counter() - t0) * 1000.0

            logger.info(
                f"Cold start complete: {report.broker_positions} broker positions, "
                f"{report.orphan_positions_cleared} orphans cleared, "
                f"{report.state_drifts_corrected} drifts corrected, "
                f"clean={report.is_clean}"
            )
            return report

        except Exception as e:
            report.error = str(e)
            report.duration_ms = (time.perf_counter() - t0) * 1000.0
            logger.error(f"Cold start reconciliation failed: {e}")
            return report


if __name__ == "__main__":
    # Smoke test
    import asyncio
    from titan.production.position_sync import PositionSync

    async def main():
        print("=" * 70)
        print("TITAN ColdStartReconciler — Smoke Test")
        print("=" * 70)

        # Stub broker with 1 position
        sync = PositionSync(interval_seconds=10, broker_source="stub")
        sync.set_stub_positions([
            BrokerPosition(ticket=50001, symbol="XAUUSD", direction=1, volume=0.01,
                           entry_price=2000.0, stop_loss=1995.0, take_profit=2010.0,
                           open_time=time.time()),
        ])
        # Simulate stale local state
        sync._local_state[99999] = BrokerPosition(
            ticket=99999, symbol="XAUUSD", direction=-1, volume=0.02,
            entry_price=1990.0, stop_loss=0, take_profit=0, open_time=0
        )

        reconciler = ColdStartReconciler(position_sync=sync)
        report = await reconciler.reconcile()
        print(f"\n{report}")
        print(f"\nLocal state after reconciliation: {len(sync.open_positions)} positions")
        for p in sync.open_positions:
            print(f"  ticket={p.ticket} dir={p.direction} vol={p.volume}")

    asyncio.run(main())
