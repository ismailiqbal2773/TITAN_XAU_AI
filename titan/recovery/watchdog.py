"""
TITAN Heartbeat Watchdog
==========================
Detects hung components by tracking heartbeat timestamps.

Each component pings the watchdog periodically. If a component
misses N consecutive heartbeats, watchdog fires alert + can
trigger restart.

Components tracked:
  - market_data
  - ceo
  - weighting
  - risk
  - execution
  - broker
  - api
  - license_guard
  - compliance

Watchdog also tracks:
  - DB connection alive
  - Redis connection alive
  - MT5 connection alive
"""
from __future__ import annotations
import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Callable, Awaitable
from collections import defaultdict

logger = logging.getLogger(__name__)


@dataclass
class HeartbeatState:
    component: str
    last_beat: float = 0.0
    expected_interval_s: float = 30.0
    missed_count: int = 0
    threshold_misses: int = 3
    alert_fired: bool = False


class HeartbeatWatchdog:
    """Monitors heartbeats from all components."""

    def __init__(self, journal=None, alert_manager=None,
                 check_interval_s: float = 10.0):
        self._journal = journal
        self._alerts = alert_manager
        self._check_interval_s = check_interval_s
        self._states: dict[str, HeartbeatState] = {}
        self._running = False
        self._task: asyncio.Task | None = None
        self._on_hung: Callable[[str], Awaitable[None]] | None = None

    def register(self, component: str, expected_interval_s: float = 30.0,
                 threshold_misses: int = 3) -> None:
        """Register a component for heartbeat monitoring."""
        self._states[component] = HeartbeatState(
            component=component,
            expected_interval_s=expected_interval_s,
            threshold_misses=threshold_misses,
        )

    def beat(self, component: str) -> None:
        """Record a heartbeat from a component."""
        if component not in self._states:
            self.register(component)
        state = self._states[component]
        state.last_beat = time.time()
        state.missed_count = 0
        if state.alert_fired:
            state.alert_fired = False
            logger.info(f"Watchdog: {component} recovered")
            if self._journal:
                asyncio.create_task(self._journal.log(
                    "watchdog", component, "recovered",
                    {"last_beat": state.last_beat},
                ))

    async def _check_loop(self) -> None:
        """Periodic check loop."""
        while self._running:
            now = time.time()
            for component, state in self._states.items():
                if state.last_beat == 0:
                    continue  # not started yet
                elapsed = now - state.last_beat
                if elapsed > state.expected_interval_s:
                    state.missed_count = int(elapsed / state.expected_interval_s)
                    if state.missed_count >= state.threshold_misses and not state.alert_fired:
                        state.alert_fired = True
                        logger.error(
                            f"Watchdog: {component} HUNG "
                            f"(missed {state.missed_count} beats, "
                            f"{elapsed:.0f}s since last)"
                        )
                        if self._journal:
                            await self._journal.log(
                                "watchdog", component, "hung_detected",
                                {"missed_count": state.missed_count,
                                 "elapsed_s": elapsed,
                                 "threshold": state.threshold_misses},
                                severity="CRITICAL",
                            )
                        if self._alerts:
                            try:
                                await self._alerts.send_alert(
                                    "P1", f"Component hung: {component}",
                                    f"Missed {state.missed_count} heartbeats",
                                )
                            except Exception:
                                pass
                        if self._on_hung:
                            try:
                                await self._on_hung(component)
                            except Exception as e:
                                logger.error(f"on_hung callback failed: {e}")
            await asyncio.sleep(self._check_interval_s)

    async def start(self) -> None:
        """Start watchdog loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._check_loop())
        logger.info(f"Heartbeat watchdog started "
                    f"(check every {self._check_interval_s}s, "
                    f"monitoring {len(self._states)} components)")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    def status(self) -> dict:
        now = time.time()
        return {
            comp: {
                "last_beat_ago_s": now - s.last_beat if s.last_beat else None,
                "missed_count": s.missed_count,
                "alert_fired": s.alert_fired,
                "expected_interval_s": s.expected_interval_s,
            }
            for comp, s in self._states.items()
        }

    def set_on_hung(self, callback: Callable[[str], Awaitable[None]]) -> None:
        self._on_hung = callback
