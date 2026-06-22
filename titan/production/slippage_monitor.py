"""
TITAN XAU AI — Slippage Monitor (Production Sprint 4)

Tracks requested vs filled price for every order, computes rolling
slippage statistics, and triggers caution/halt when slippage exceeds
thresholds.

Usage:
    mon = SlippageMonitor()
    mon.record_fill(requested_price=2000.00, filled_price=2000.05, ticket=50001)
    stats = mon.get_stats()
    if stats.caution:
        # reduce size or halt
        ...
"""
from __future__ import annotations

import collections
import logging
import time
from dataclasses import dataclass, field
from typing import Optional, Deque

logger = logging.getLogger(__name__)


@dataclass
class FillRecord:
    """Single fill record."""
    timestamp: float
    ticket: int
    requested_price: float
    filled_price: float
    direction: int = 1            # +1 long, -1 short
    slippage_pips: float = 0.0    # signed: + = unfavorable, - = favorable
    slippage_usd: float = 0.0


@dataclass
class SlippageStats:
    """Rolling slippage statistics."""
    n_fills: int = 0
    mean_slippage_pips: float = 0.0
    median_slippage_pips: float = 0.0
    p95_slippage_pips: float = 0.0
    max_slippage_pips: float = 0.0
    mean_slippage_usd: float = 0.0
    caution: bool = False
    halt: bool = False
    reason: str = ""

    def __repr__(self) -> str:
        return (
            f"SlippageStats(n={self.n_fills}, mean={self.mean_slippage_pips:.2f}pips, "
            f"p95={self.p95_slippage_pips:.2f}pips, max={self.max_slippage_pips:.2f}pips, "
            f"caution={self.caution}, halt={self.halt})"
        )


@dataclass
class SlippageConfig:
    """Slippage thresholds."""
    window_size: int = 100                    # rolling window
    caution_mean_pips: float = 2.0            # mean > 2 pips → CAUTION
    caution_p95_pips: float = 5.0             # p95 > 5 pips → CAUTION
    halt_mean_pips: float = 5.0               # mean > 5 pips → HALT
    halt_p95_pips: float = 10.0               # p95 > 10 pips → HALT
    halt_max_pips: float = 20.0               # any single fill > 20 pips → HALT
    pip_value_usd: float = 0.01               # XAUUSD 2-digit: 1 pip = $0.01
    contract_size: float = 100.0              # XAUUSD: 100 oz/lot


class SlippageMonitor:
    """
    Rolling slippage monitor.

    Records each fill, computes stats over the last N fills, and flags
    caution/halt when thresholds are breached.

    Safety: if record_fill() raises, the monitor enters "halt" state
    (fail-safe).
    """

    def __init__(self, config: Optional[SlippageConfig] = None):
        self.config = config or SlippageConfig()
        self._fills: Deque[FillRecord] = collections.deque(maxlen=self.config.window_size)
        self._halt_override = False
        self._halt_reason = ""
        logger.info(f"SlippageMonitor initialized: window={self.config.window_size}")

    # ─── Public API ─────────────────────────────────────────────────────

    def record_fill(
        self,
        requested_price: float,
        filled_price: float,
        ticket: int = 0,
        direction: int = 1,
        volume: float = 0.01,
        timestamp: Optional[float] = None,
    ) -> FillRecord:
        """
        Record a single fill.

        Slippage is signed:
          + = unfavorable (paid more than requested for LONG, received less for SHORT)
          - = favorable (price improvement)
        """
        try:
            ts = timestamp or time.time()
            # Compute signed slippage in price units
            price_diff = filled_price - requested_price
            # For LONG: positive diff = unfavorable (paid more)
            # For SHORT: negative diff = unfavorable (received less)
            signed_diff = price_diff * direction
            slippage_pips = signed_diff / self.config.pip_value_usd
            slippage_usd = signed_diff * self.config.contract_size * volume

            record = FillRecord(
                timestamp=ts,
                ticket=ticket,
                requested_price=requested_price,
                filled_price=filled_price,
                direction=direction,
                slippage_pips=slippage_pips,
                slippage_usd=slippage_usd,
            )
            self._fills.append(record)

            # Check for immediate halt on single fill
            if abs(slippage_pips) >= self.config.halt_max_pips:
                self._halt_override = True
                self._halt_reason = f"single_fill_max ({slippage_pips:.2f}pips)"
                logger.warning(
                    f"SLIPPAGE HALT: single fill {slippage_pips:.2f} pips "
                    f"(ticket={ticket})"
                )

            return record
        except Exception as e:
            logger.error(f"SlippageMonitor error (fail-safe): {e}")
            self._halt_override = True
            self._halt_reason = f"monitor_error: {e}"
            return FillRecord(
                timestamp=timestamp or time.time(),
                ticket=ticket,
                requested_price=requested_price,
                filled_price=filled_price,
                direction=direction,
            )

    def get_stats(self) -> SlippageStats:
        """Compute current rolling statistics."""
        if not self._fills:
            return SlippageStats()

        slippages = [f.slippage_pips for f in self._fills]
        slippages_usd = [f.slippage_usd for f in self._fills]
        n = len(slippages)

        # Compute stats
        sorted_slip = sorted(slippages)
        mean_slip = sum(slippages) / n
        median_slip = sorted_slip[n // 2] if n % 2 == 1 else (sorted_slip[n//2 - 1] + sorted_slip[n//2]) / 2
        p95_idx = int(n * 0.95)
        p95_slip = sorted_slip[min(p95_idx, n - 1)]
        max_slip = max(slippages, key=abs)
        mean_usd = sum(slippages_usd) / n

        # Determine caution / halt
        caution = False
        halt = self._halt_override
        reason = self._halt_reason

        if not halt:
            if abs(mean_slip) >= self.config.halt_mean_pips:
                halt = True
                reason = f"halt_mean ({mean_slip:.2f}pips)"
            elif abs(p95_slip) >= self.config.halt_p95_pips:
                halt = True
                reason = f"halt_p95 ({p95_slip:.2f}pips)"

        if not halt:
            if abs(mean_slip) >= self.config.caution_mean_pips:
                caution = True
                reason = f"caution_mean ({mean_slip:.2f}pips)"
            elif abs(p95_slip) >= self.config.caution_p95_pips:
                caution = True
                reason = f"caution_p95 ({p95_slip:.2f}pips)"

        return SlippageStats(
            n_fills=n,
            mean_slippage_pips=mean_slip,
            median_slippage_pips=median_slip,
            p95_slippage_pips=p95_slip,
            max_slippage_pips=max_slip,
            mean_slippage_usd=mean_usd,
            caution=caution,
            halt=halt,
            reason=reason,
        )

    def reset(self) -> None:
        """Clear all fills and halt override."""
        self._fills.clear()
        self._halt_override = False
        self._halt_reason = ""
        logger.info("SlippageMonitor reset")

    @property
    def fill_count(self) -> int:
        return len(self._fills)

    @property
    def is_halted(self) -> bool:
        return self._halt_override or self.get_stats().halt


if __name__ == "__main__":
    # Smoke test
    print("=" * 70)
    print("TITAN SlippageMonitor — Smoke Test")
    print("=" * 70)
    mon = SlippageMonitor()

    # Record normal fills
    for i in range(10):
        mon.record_fill(requested_price=2000.0, filled_price=2000.02,
                       ticket=50000+i, direction=1, volume=0.01)
    print(f"\nAfter 10 normal fills (0.02 slippage):")
    print(f"  {mon.get_stats()}")

    # Record a bad fill
    mon.record_fill(requested_price=2000.0, filled_price=2000.30,
                   ticket=59999, direction=1, volume=0.01)
    print(f"\nAfter 1 bad fill (0.30 slippage = 30 pips):")
    print(f"  {mon.get_stats()}")
    print(f"  is_halted: {mon.is_halted}")
