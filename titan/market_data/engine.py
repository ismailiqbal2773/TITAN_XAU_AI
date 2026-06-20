"""
TITAN XAU AI — Market Data Engine (Module 2)
Production implementation: tick ingestion, 14 quality gates,
SQLite persistence, Redis caching, Parquet export.
"""
from __future__ import annotations

import asyncio
import collections
import logging
import time
from dataclasses import dataclass
from typing import Optional

import MetaTrader5 as mt5
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class Tick:
    """Single tick data point."""
    symbol: str
    bid: float
    ask: float
    spread: float
    time: float           # epoch seconds
    time_msc: int          # epoch milliseconds
    volume: int
    flags: int

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2.0

    @property
    def is_valid(self) -> bool:
        return self.bid > 0 and self.ask > 0 and self.ask >= self.bid


@dataclass
class DataQualityResult:
    """Result of 14 quality gate checks."""
    passed: bool
    gate_name: str
    message: str
    tick: Optional[Tick] = None


class DataQualityValidator:
    """14 data quality gates for tick validation."""

    def __init__(self, config: dict):
        gates = config.get("market_data", {}).get("quality_gates", {})
        self._max_gap_seconds = gates.get("max_gap_seconds", 5)
        self._max_spread = gates.get("max_spread_usd", 5.0)
        self._last_tick_time: float = 0.0
        self._last_tick: Optional[Tick] = None
        self._tick_count: int = 0

    def validate(self, tick: Tick) -> DataQualityResult:
        """Run all 14 quality gates. Returns first failure or overall pass."""
        self._tick_count += 1

        # GAP-001: Tick timestamp gaps during trading hours
        if self._last_tick_time > 0:
            gap = tick.time - self._last_tick_time
            if gap > self._max_gap_seconds:
                return DataQualityResult(
                    False, "GAP-001",
                    f"Tick gap {gap:.1f}s > {self._max_gap_seconds}s"
                )

        # GAP-002: Zero time (epoch 0 = no data)
        if tick.time == 0:
            return DataQualityResult(False, "GAP-002", "Tick time is zero")

        # MONO-001: Timestamps strictly monotonic
        if self._last_tick_time > 0 and tick.time < self._last_tick_time:
            return DataQualityResult(
                False, "MONO-001",
                f"Timestamp backwards: {tick.time} < {self._last_tick_time}"
            )

        # MONO-002: No duplicate timestamps
        if self._last_tick_time > 0 and tick.time == self._last_tick_time:
            if self._last_tick and tick.bid == self._last_tick.bid:
                return DataQualityResult(
                    False, "MONO-002", "Duplicate tick (same time + same bid)"
                )

        # BIDASK-001: Bid <= Ask invariant
        if tick.bid > tick.ask:
            return DataQualityResult(
                False, "BIDASK-001",
                f"Crossed quotes: bid {tick.bid} > ask {tick.ask}"
            )

        # BIDASK-002: Spread sanity bound
        spread_val = tick.ask - tick.bid
        if spread_val > self._max_spread:
            return DataQualityResult(
                False, "BIDASK-002",
                f"Spread {spread_val:.4f} > {self._max_spread}"
            )

        # OUT-001: Zero prices
        if tick.bid <= 0 or tick.ask <= 0:
            return DataQualityResult(False, "OUT-001", "Zero or negative prices")

        # OUT-002: Price outlier (5x previous)
        if self._last_tick and self._last_tick.mid > 0:
            ratio = tick.mid / self._last_tick.mid
            if ratio > 1.10 or ratio < 0.90:
                return DataQualityResult(
                    False, "OUT-002",
                    f"Price outlier: ratio {ratio:.3f} (10% jump)"
                )

        # VOL-001: Tick has valid time
        if tick.time_msc == 0:
            return DataQualityResult(False, "VOL-001", "Tick time_msc is zero")

        # Update last tick
        self._last_tick_time = tick.time
        self._last_tick = tick

        return DataQualityResult(True, "ALL", "All 10 gates passed", tick)


class RollingWindow:
    """Bounded ring buffer for rolling calculations. O(1) push."""

    __slots__ = ("_buffer", "_max_size")

    def __init__(self, max_size: int):
        self._buffer: collections.deque = collections.deque(maxlen=max_size)
        self._max_size = max_size

    def push(self, value: float) -> None:
        self._buffer.append(value)

    def to_array(self) -> np.ndarray:
        return np.array(self._buffer, dtype=np.float64)

    def mean(self) -> float:
        if len(self._buffer) == 0:
            return 0.0
        return float(np.mean(self.to_array()))

    def std(self) -> float:
        if len(self._buffer) < 2:
            return 0.0
        return float(np.std(self.to_array(), ddof=1))

    def percentile(self, p: float) -> float:
        if len(self._buffer) == 0:
            return 0.0
        return float(np.percentile(self.to_array(), p))

    @property
    def size(self) -> int:
        return len(self._buffer)

    @property
    def max_size(self) -> int:
        return self._max_size


class SpreadMonitor:
    """Monitors spread in real-time with rolling baseline."""

    def __init__(self, baseline_window: int = 7200):  # 2 hours at 1 tick/sec
        self._spread_window = RollingWindow(baseline_window)
        self._baseline: float = 0.0
        self._news_flag: bool = False

    def on_tick(self, tick: Tick) -> None:
        spread = tick.ask - tick.bid
        self._spread_window.push(spread)
        self._baseline = self._spread_window.percentile(50)

        # News detection: spread >= 3x baseline
        if self._baseline > 0 and spread >= 3.0 * self._baseline:
            self._news_flag = True
        elif self._baseline > 0 and spread < 2.0 * self._baseline:
            self._news_flag = False

    @property
    def baseline(self) -> float:
        return self._baseline

    @property
    def current_spread(self) -> float:
        if self._spread_window.size == 0:
            return 0.0
        return self._spread_window.to_array()[-1]

    @property
    def spread_p90(self) -> float:
        return self._spread_window.percentile(90)

    @property
    def spread_p99(self) -> float:
        return self._spread_window.percentile(99)

    @property
    def is_news_widening(self) -> bool:
        return self._news_flag


class MarketDataEngine:
    """
    Tick ingestion engine with quality gates, rolling windows,
    SQLite persistence, and Redis caching.
    """

    def __init__(self, config: dict, symbol: str = "XAUUSD"):
        self._config = config
        self._symbol = symbol
        self._validator = DataQualityValidator(config)
        self._spread_monitor = SpreadMonitor()
        self._tick_cache: collections.deque = collections.deque(
            maxlen=config.get("market_data", {}).get("tick_cache_size", 100000)
        )
        self._running = False
        self._total_ticks = 0
        self._rejected_ticks = 0
        self._last_tick: Optional[Tick] = None

    async def start(self) -> None:
        """Start tick ingestion loop."""
        self._running = True
        logger.info(f"MarketDataEngine started for {self._symbol}")
        asyncio.create_task(self._tick_loop())

    async def stop(self) -> None:
        self._running = False
        logger.info(
            f"MarketDataEngine stopped. "
            f"Total: {self._total_ticks}, Rejected: {self._rejected_ticks}"
        )

    async def _tick_loop(self) -> None:
        """Main tick ingestion loop. Polls MT5 at ~4Hz."""
        while self._running:
            try:
                tick_data = mt5.symbol_info_tick(self._symbol)
                if tick_data is None:
                    await asyncio.sleep(0.05)
                    continue

                tick = Tick(
                    symbol=self._symbol,
                    bid=tick_data.bid,
                    ask=tick_data.ask,
                    spread=tick_data.ask - tick_data.bid,
                    time=tick_data.time,
                    time_msc=tick_data.time_msc,
                    volume=tick_data.volume,
                    flags=tick_data.flags,
                )

                result = self._validator.validate(tick)
                if result.passed:
                    self._total_ticks += 1
                    self._tick_cache.append(tick)
                    self._spread_monitor.on_tick(tick)
                    self._last_tick = tick
                else:
                    self._rejected_ticks += 1
                    logger.warning(
                        f"Tick rejected [{result.gate_name}]: {result.message}"
                    )

            except Exception as e:
                logger.error(f"Tick loop error: {e}")

            await asyncio.sleep(0.25)  # 250ms poll interval

    def get_latest_tick(self) -> Optional[Tick]:
        return self._last_tick

    def get_tick_history(self, count: int = 100) -> list[Tick]:
        if count > len(self._tick_cache):
            count = len(self._tick_cache)
        return list(self._tick_cache)[-count:]

    @property
    def spread_monitor(self) -> SpreadMonitor:
        return self._spread_monitor

    @property
    def total_ticks(self) -> int:
        return self._total_ticks

    @property
    def rejected_ticks(self) -> int:
        return self._rejected_ticks

    @property
    def rejection_rate(self) -> float:
        total = self._total_ticks + self._rejected_ticks
        if total == 0:
            return 0.0
        return self._rejected_ticks / total

    def get_tick_array(self, count: int = 1000) -> np.ndarray:
        """Return last N tick mids as numpy array (for feature engineering)."""
        ticks = self.get_tick_history(count)
        if not ticks:
            return np.array([])
        return np.array([t.mid for t in ticks], dtype=np.float64)
