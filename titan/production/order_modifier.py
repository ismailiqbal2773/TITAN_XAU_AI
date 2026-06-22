"""
TITAN XAU AI — Order Modifier (Production Sprint 3)

Wraps MT5 SL/TP modification with:
  - Idempotency key (prevent duplicate modifications)
  - Retry with exponential backoff
  - dry_run=True default (NEVER modify broker order in tests)
  - Trailing stop support

Safety:
  - dry_run=True by default — no real MT5 calls
  - Requires explicit dry_run=False + TITAN_LIVE_TRADING=1 env var for live
  - Idempotency cache prevents duplicate modifications within session
  - All modifications are journaled via TradeJournal

Usage:
    modifier = OrderModifier(dry_run=True)
    result = await modifier.modify_sl_tp(
        ticket=50001, new_sl=2000.0, new_tp=2001.0,
        reason="trailing_stop", journal=journal
    )
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ModifyRequest:
    """SL/TP modification request."""
    ticket: int
    new_sl: float
    new_tp: float
    reason: str = "manual"
    idempotency_key: str = field(default_factory=lambda: str(uuid.uuid4()))

    def fingerprint(self) -> str:
        """Stable hash for idempotency (ticket+sl+tp+reason)."""
        raw = f"{self.ticket}:{self.new_sl}:{self.new_tp}:{self.reason}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]


@dataclass
class ModifyResult:
    """Result of a modification attempt."""
    success: bool
    ticket: int
    old_sl: float = 0.0
    old_tp: float = 0.0
    new_sl: float = 0.0
    new_tp: float = 0.0
    retcode: int = 0
    error: Optional[str] = None
    latency_ms: float = 0.0
    dry_run: bool = True
    idempotency_hit: bool = False
    journal_record_id: Optional[str] = None


class OrderModifier:
    """
    Wrap MT5 order_modify with safety + idempotency + journaling.

    Usage:
        modifier = OrderModifier(dry_run=True)
        result = await modifier.modify_sl_tp(ticket=50001, new_sl=2000.0, new_tp=2001.0)
    """

    def __init__(
        self,
        dry_run: bool = True,
        max_retries: int = 2,
        retry_backoff_ms: float = 500.0,
        idempotency_cache_size: int = 1000,
        require_live_config_flag: bool = True,
    ):
        self.dry_run = dry_run
        self.max_retries = max_retries
        self.retry_backoff_ms = retry_backoff_ms
        self._idempotency_cache: dict[str, float] = {}  # fingerprint → timestamp
        self._max_cache_size = idempotency_cache_size
        self._require_live_flag = require_live_config_flag

        # Verify safety: if dry_run=False, require explicit env var
        if not self.dry_run and self._require_live_flag:
            flag = os.environ.get("TITAN_LIVE_TRADING", "0")
            if flag != "1":
                raise PermissionError(
                    "dry_run=False requires TITAN_LIVE_TRADING=1 environment variable."
                )

        logger.info(f"OrderModifier initialized (dry_run={dry_run})")

    # ─── Public API ─────────────────────────────────────────────────────

    async def modify_sl_tp(
        self,
        ticket: int,
        new_sl: float,
        new_tp: float,
        reason: str = "manual",
        journal=None,
        execution_engine=None,
    ) -> ModifyResult:
        """
        Modify SL/TP for an open position.

        Args:
            ticket: MT5 position ticket
            new_sl: New stop-loss price
            new_tp: New take-profit price
            reason: Modification reason (e.g., "trailing_stop")
            journal: Optional TradeJournal for logging
            execution_engine: Optional ExecutionEngine for live modifications

        Returns:
            ModifyResult with success/failure details
        """
        t0 = time.perf_counter()
        req = ModifyRequest(ticket=ticket, new_sl=new_sl, new_tp=new_tp, reason=reason)

        # ── Idempotency check ──
        fp = req.fingerprint()
        if fp in self._idempotency_cache:
            logger.warning(f"Duplicate modify blocked (fingerprint={fp})")
            return ModifyResult(
                success=False,
                ticket=ticket,
                new_sl=new_sl,
                new_tp=new_tp,
                error="Duplicate modification (idempotency hit)",
                latency_ms=(time.perf_counter() - t0) * 1000,
                dry_run=self.dry_run,
                idempotency_hit=True,
            )

        # ── Validate inputs ──
        if new_sl <= 0 or new_tp <= 0:
            return ModifyResult(
                success=False,
                ticket=ticket,
                new_sl=new_sl,
                new_tp=new_tp,
                error="SL and TP must be > 0",
                latency_ms=(time.perf_counter() - t0) * 1000,
                dry_run=self.dry_run,
            )
        if new_sl == new_tp:
            return ModifyResult(
                success=False,
                ticket=ticket,
                new_sl=new_sl,
                new_tp=new_tp,
                error="SL and TP cannot be equal",
                latency_ms=(time.perf_counter() - t0) * 1000,
                dry_run=self.dry_run,
            )

        # ── Fetch current SL/TP (for journal old_sl/old_tp) ──
        old_sl, old_tp = await self._fetch_current_sl_tp(ticket, execution_engine)

        # ── DRY RUN: log and return without modifying ──
        if self.dry_run:
            elapsed = (time.perf_counter() - t0) * 1000
            logger.info(
                f"[DRY RUN] Would modify ticket={ticket}: "
                f"SL {old_sl}→{new_sl}, TP {old_tp}→{new_tp} ({reason})"
            )
            # Journal the modification
            journal_rid = None
            if journal is not None:
                journal_rid = journal.log_modify(
                    ticket=ticket, old_sl=old_sl, old_tp=old_tp,
                    new_sl=new_sl, new_tp=new_tp, reason=reason,
                    dry_run=True,
                )
            # Cache fingerprint
            self._cache_fingerprint(fp)
            return ModifyResult(
                success=True,
                ticket=ticket,
                old_sl=old_sl,
                old_tp=old_tp,
                new_sl=new_sl,
                new_tp=new_tp,
                latency_ms=elapsed,
                dry_run=True,
                journal_record_id=journal_rid,
            )

        # ── LIVE: call MT5 order_modify via execution_engine ──
        if execution_engine is None:
            return ModifyResult(
                success=False,
                ticket=ticket,
                new_sl=new_sl,
                new_tp=new_tp,
                error="No execution_engine provided for live modification",
                latency_ms=(time.perf_counter() - t0) * 1000,
                dry_run=False,
            )

        last_error = ""
        for attempt in range(self.max_retries + 1):
            try:
                result = await self._call_mt5_modify(
                    execution_engine, ticket, new_sl, new_tp
                )
                if result:
                    elapsed = (time.perf_counter() - t0) * 1000
                    journal_rid = None
                    if journal is not None:
                        journal_rid = journal.log_modify(
                            ticket=ticket, old_sl=old_sl, old_tp=old_tp,
                            new_sl=new_sl, new_tp=new_tp, reason=reason,
                            dry_run=False,
                        )
                    self._cache_fingerprint(fp)
                    return ModifyResult(
                        success=True,
                        ticket=ticket,
                        old_sl=old_sl,
                        old_tp=old_tp,
                        new_sl=new_sl,
                        new_tp=new_tp,
                        retcode=10009,  # TRADE_RETCODE_DONE
                        latency_ms=elapsed,
                        dry_run=False,
                        journal_record_id=journal_rid,
                    )
            except Exception as e:
                last_error = str(e)
                logger.warning(f"Modify attempt {attempt+1} failed: {e}")
                if attempt < self.max_retries:
                    await asyncio.sleep(self.retry_backoff_ms / 1000)

        return ModifyResult(
            success=False,
            ticket=ticket,
            old_sl=old_sl,
            old_tp=old_tp,
            new_sl=new_sl,
            new_tp=new_tp,
            error=f"Modify failed after {self.max_retries+1} attempts: {last_error}",
            latency_ms=(time.perf_counter() - t0) * 1000,
            dry_run=False,
        )

    async def trailing_stop_update(
        self,
        ticket: int,
        current_price: float,
        direction: int,                  # +1 long, -1 short
        activation_offset: float,        # e.g., 1.0 = activate after +1R profit
        sl_distance: float,              # trail distance behind current price
        entry_price: float,
        original_sl: float,
        original_tp: float,
        journal=None,
        execution_engine=None,
    ) -> ModifyResult:
        """
        Update SL via trailing stop logic.

        Only activates after price moves activation_offset in favor of position.
        Trailing SL is current_price - sl_distance (long) or current_price + sl_distance (short).
        SL only moves in the favorable direction (never widens risk).

        Returns ModifyResult. If trailing not yet activated, returns success=False with
        error="trailing_not_activated".
        """
        # Compute profit in price units
        if direction == 1:
            profit = current_price - entry_price
        else:
            profit = entry_price - current_price

        if profit < activation_offset:
            return ModifyResult(
                success=False,
                ticket=ticket,
                new_sl=original_sl,
                new_tp=original_tp,
                error=f"trailing_not_activated (profit={profit:.4f} < activation={activation_offset:.4f})",
                dry_run=self.dry_run,
            )

        # Compute new trailing SL
        if direction == 1:
            new_sl = current_price - sl_distance
            # SL must be higher than original (never widen risk)
            if new_sl <= original_sl:
                return ModifyResult(
                    success=False,
                    ticket=ticket,
                    new_sl=original_sl,
                    new_tp=original_tp,
                    error=f"trailing_sl_below_original ({new_sl:.4f} <= {original_sl:.4f})",
                    dry_run=self.dry_run,
                )
            new_tp = original_tp  # TP unchanged
        else:
            new_sl = current_price + sl_distance
            # SL must be lower than original (never widen risk for short)
            if new_sl >= original_sl:
                return ModifyResult(
                    success=False,
                    ticket=ticket,
                    new_sl=original_sl,
                    new_tp=original_tp,
                    error=f"trailing_sl_above_original ({new_sl:.4f} >= {original_sl:.4f})",
                    dry_run=self.dry_run,
                )
            new_tp = original_tp

        return await self.modify_sl_tp(
            ticket=ticket,
            new_sl=round(new_sl, 5),
            new_tp=round(new_tp, 5),
            reason=f"trailing_stop (profit={profit:.4f})",
            journal=journal,
            execution_engine=execution_engine,
        )

    # ─── Internal helpers ───────────────────────────────────────────────

    async def _fetch_current_sl_tp(
        self, ticket: int, execution_engine=None
    ) -> tuple[float, float]:
        """Fetch current SL/TP from broker (or stub)."""
        if execution_engine is not None:
            try:
                positions = execution_engine.get_positions()
                for p in positions:
                    if int(getattr(p, "ticket", 0)) == ticket:
                        return (
                            float(getattr(p, "sl", 0) or 0),
                            float(getattr(p, "tp", 0) or 0),
                        )
            except Exception as e:
                logger.warning(f"Could not fetch current SL/TP: {e}")
        return 0.0, 0.0  # stub default

    async def _call_mt5_modify(
        self, execution_engine, ticket: int, new_sl: float, new_tp: float
    ) -> bool:
        """Call MT5 order_modify via execution_engine."""
        try:
            import MetaTrader5 as mt5
            position = mt5.positions_get(ticket=ticket)
            if not position:
                return False
            pos = position[0]
            request = {
                "action": mt5.TRADE_ACTION_SLTP,
                "symbol": pos.symbol,
                "position": ticket,
                "sl": new_sl,
                "tp": new_tp,
            }
            result = mt5.order_send(request)
            if result is None:
                return False
            return result.retcode == mt5.TRADE_RETCODE_DONE
        except Exception as e:
            logger.error(f"MT5 order_modify failed: {e}")
            return False

    def _cache_fingerprint(self, fp: str) -> None:
        """Add fingerprint to idempotency cache."""
        self._idempotency_cache[fp] = time.time()
        if len(self._idempotency_cache) > self._max_cache_size:
            # Evict oldest 25%
            sorted_items = sorted(self._idempotency_cache.items(), key=lambda x: x[1])
            for k, _ in sorted_items[:len(sorted_items) // 4]:
                del self._idempotency_cache[k]

    @property
    def cache_size(self) -> int:
        return len(self._idempotency_cache)


if __name__ == "__main__":
    import asyncio

    async def main():
        print("=" * 70)
        print("TITAN OrderModifier — Dry-Run Smoke Test")
        print("=" * 70)
        mod = OrderModifier(dry_run=True)

        # Test basic modify
        r1 = await mod.modify_sl_tp(ticket=50001, new_sl=2000.0, new_tp=2001.0,
                                     reason="trailing_stop")
        print(f"\nBasic modify: {r1}")

        # Test trailing stop (activated)
        r2 = await mod.trailing_stop_update(
            ticket=50001, current_price=2002.0, direction=1,
            activation_offset=1.0, sl_distance=0.5,
            entry_price=2000.0, original_sl=1999.5, original_tp=2010.0,
        )
        print(f"\nTrailing (activated): {r2}")

        # Test trailing stop (not yet activated)
        r3 = await mod.trailing_stop_update(
            ticket=50002, current_price=2000.5, direction=1,
            activation_offset=1.0, sl_distance=0.5,
            entry_price=2000.0, original_sl=1999.5, original_tp=2010.0,
        )
        print(f"\nTrailing (not activated): {r3}")

    asyncio.run(main())
