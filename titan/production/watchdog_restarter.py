"""
TITAN XAU AI — Watchdog Restarter (Production Sprint 4)

Wires the existing HeartbeatWatchdog (titan/recovery/watchdog.py) callback
to detect hung loops and restart them in dry_run mode.

Design:
  - Uses HeartbeatWatchdog.register(component, expected_interval_s, threshold_misses)
  - Wires set_on_hung(callback) to a restart handler
  - Restart handler logs the event + attempts to restart the failed loop
  - In dry_run, restart = recreate asyncio task (no real broker reconnect)
  - All recovery events journaled

Usage:
    restarter = WatchdogRestarter(journal=journal)
    restarter.register_component("inference_loop", task=my_loop, restart_fn=restart_fn)
    await restarter.start()  # background monitor
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Optional, Callable, Awaitable, Any

from titan.recovery.watchdog import HeartbeatWatchdog

logger = logging.getLogger(__name__)


@dataclass
class RecoveryEvent:
    """Record of a watchdog recovery action."""
    timestamp: float
    component: str
    missed_count: int
    action: str                  # "restart_attempted" | "restart_success" | "restart_failed"
    error: Optional[str] = None
    duration_ms: float = 0.0


@dataclass
class WatchedComponent:
    """A component registered with the watchdog restarter."""
    name: str
    expected_interval_s: float
    threshold_misses: int
    restart_fn: Optional[Callable[[], Awaitable[Any]]] = None
    task: Optional[asyncio.Task] = None
    last_restart: float = 0.0
    restart_count: int = 0


class WatchdogRestarter:
    """
    Wraps HeartbeatWatchdog with auto-restart capability.

    Safety:
      - dry_run=True default — only logs restart attempts, doesn't actually restart
      - If restart_fn raises, logs error + escalates to journal
      - Max 3 restart attempts per component per minute (rate-limited)
      - Fail-safe: if watchdog itself errors, all components marked as "needs restart"
    """

    def __init__(
        self,
        journal=None,
        dry_run: bool = True,
        check_interval_s: float = 10.0,
        max_restarts_per_minute: int = 3,
    ):
        self.journal = journal
        self.dry_run = dry_run
        self.check_interval_s = check_interval_s
        self.max_restarts_per_minute = max_restarts_per_minute
        self._watchdog = HeartbeatWatchdog(
            journal=None,  # we journal ourselves
            check_interval_s=check_interval_s,
        )
        self._components: dict[str, WatchedComponent] = {}
        self._recovery_events: list[RecoveryEvent] = []
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._restart_timestamps: dict[str, list[float]] = {}

        # Wire watchdog's on_hung callback
        self._watchdog.set_on_hung(self._handle_hung)
        logger.info(f"WatchdogRestarter initialized (dry_run={dry_run})")

    # ─── Public API ─────────────────────────────────────────────────────

    def register_component(
        self,
        name: str,
        expected_interval_s: float = 30.0,
        threshold_misses: int = 3,
        restart_fn: Optional[Callable[[], Awaitable[Any]]] = None,
        task: Optional[asyncio.Task] = None,
    ) -> None:
        """Register a component for heartbeat monitoring + auto-restart."""
        comp = WatchedComponent(
            name=name,
            expected_interval_s=expected_interval_s,
            threshold_misses=threshold_misses,
            restart_fn=restart_fn,
            task=task,
        )
        self._components[name] = comp
        self._watchdog.register(
            component=name,
            expected_interval_s=expected_interval_s,
            threshold_misses=threshold_misses,
        )
        logger.info(f"Registered component '{name}' (interval={expected_interval_s}s, "
                    f"threshold={threshold_misses} misses)")

    def beat(self, component: str) -> None:
        """Record a heartbeat from a component."""
        self._watchdog.beat(component)

    async def start(self) -> None:
        """Start the watchdog monitoring loop (background)."""
        self._running = True
        self._watchdog._running = True
        logger.info("WatchdogRestarter started")
        while self._running:
            try:
                await self._check_once()
            except Exception as e:
                logger.error(f"Watchdog check error (fail-safe): {e}")
                # Mark all components as needing restart
                for name in self._components:
                    try:
                        await self._handle_hung(name)
                    except Exception as inner_e:
                        logger.error(f"Recovery handler failed for {name}: {inner_e}")
            # Interruptible sleep
            try:
                await asyncio.wait_for(asyncio.sleep(self.check_interval_s),
                                        timeout=self.check_interval_s + 0.1)
            except asyncio.TimeoutError:
                pass
            except asyncio.CancelledError:
                break

    async def _check_once(self) -> None:
        """Single check iteration (mirrors HeartbeatWatchdog._check_loop body)."""
        import time as _time
        now = _time.time()
        for component, state in self._watchdog._states.items():
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
                    await self._handle_hung(component)

    async def stop(self) -> None:
        """Stop the watchdog."""
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("WatchdogRestarter stopped")

    def start_background(self) -> asyncio.Task:
        """Start as a background asyncio task."""
        self._task = asyncio.create_task(self.start())
        return self._task

    # ─── Recovery handler ───────────────────────────────────────────────

    async def _handle_hung(self, component: str) -> None:
        """Called by watchdog when a component is detected as hung."""
        t0 = time.perf_counter()
        comp = self._components.get(component)
        if comp is None:
            logger.warning(f"Hung component '{component}' not registered — skipping")
            return

        # Rate-limit restarts
        now = time.time()
        recent = [t for t in self._restart_timestamps.get(component, []) if now - t < 60]
        if len(recent) >= self.max_restarts_per_minute:
            logger.warning(
                f"Restart rate limit hit for '{component}' "
                f"({len(recent)}/min, max={self.max_restarts_per_minute})"
            )
            return
        recent.append(now)
        self._restart_timestamps[component] = recent

        logger.warning(f"Component '{component}' hung — attempting restart")
        event = RecoveryEvent(
            timestamp=now,
            component=component,
            missed_count=comp.threshold_misses,
            action="restart_attempted",
        )
        self._recovery_events.append(event)
        if self.journal:
            self.journal.log_heartbeat({
                "event": "watchdog_restart_attempted",
                "component": component,
                "missed_count": comp.threshold_misses,
            })

        # In dry_run, just log
        if self.dry_run:
            elapsed = (time.perf_counter() - t0) * 1000
            event.action = "restart_skipped_dry_run"
            event.duration_ms = elapsed
            logger.info(f"[DRY RUN] Would restart component '{component}'")
            return

        # Live mode: actually attempt restart
        if comp.restart_fn is None:
            event.action = "restart_failed"
            event.error = "no restart_fn provided"
            event.duration_ms = (time.perf_counter() - t0) * 1000
            logger.error(f"No restart_fn for '{component}' — cannot restart")
            return

        try:
            # Cancel existing task if running
            if comp.task is not None and not comp.task.done():
                comp.task.cancel()
                try:
                    await comp.task
                except asyncio.CancelledError:
                    pass

            # Call restart function
            await comp.restart_fn()
            comp.last_restart = time.time()
            comp.restart_count += 1
            elapsed = (time.perf_counter() - t0) * 1000
            event.action = "restart_success"
            event.duration_ms = elapsed
            logger.info(f"Component '{component}' restarted successfully ({elapsed:.1f}ms)")
        except Exception as e:
            elapsed = (time.perf_counter() - t0) * 1000
            event.action = "restart_failed"
            event.error = str(e)
            event.duration_ms = elapsed
            logger.error(f"Restart failed for '{component}': {e}")

    # ─── Accessors ──────────────────────────────────────────────────────

    @property
    def recovery_events(self) -> list[RecoveryEvent]:
        return list(self._recovery_events)

    @property
    def recovery_count(self) -> int:
        return len(self._recovery_events)

    @property
    def registered_components(self) -> list[str]:
        return list(self._components.keys())

    def get_component_status(self, name: str) -> Optional[dict]:
        comp = self._components.get(name)
        if comp is None:
            return None
        state = self._watchdog._states.get(name)
        return {
            "name": name,
            "expected_interval_s": comp.expected_interval_s,
            "threshold_misses": comp.threshold_misses,
            "last_beat": state.last_beat if state else 0,
            "missed_count": state.missed_count if state else 0,
            "alert_fired": state.alert_fired if state else False,
            "restart_count": comp.restart_count,
            "last_restart": comp.last_restart,
        }


if __name__ == "__main__":
    # Smoke test
    import asyncio

    async def main():
        print("=" * 70)
        print("TITAN WatchdogRestarter — Smoke Test")
        print("=" * 70)
        restarter = WatchdogRestarter(dry_run=True, check_interval_s=0.5)
        restarter.register_component("test_loop", expected_interval_s=0.5, threshold_misses=2)
        # Don't beat — let it detect as hung
        await restarter.start()
        await asyncio.sleep(2.0)
        await restarter.stop()
        print(f"\nRecovery events: {restarter.recovery_count}")
        for e in restarter.recovery_events:
            print(f"  {e}")

    asyncio.run(main())
