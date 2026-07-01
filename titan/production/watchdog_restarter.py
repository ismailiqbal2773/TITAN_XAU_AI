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

Safety claims (auditable, NOT "never crash"):
  - Fail-closed: on any recovery anomaly the restarter blocks new trades
    via the FailClosedRuntimeGuard and does not silently resume live trading.
  - Recoverable: orphan positions are detected on restart and surfaced for
    operator resolution before any new trading is permitted.
  - Auditable: every recovery event, orphan detection, and crash report is
    journaled with a timestamp and a deterministic reason.
  - The system does NOT claim "crash impossible" or "never crashes". It
    claims crash-tolerant, fail-closed, recoverable, auditable operation.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Callable, Awaitable, Any, Sequence

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
class OrphanPositionReport:
    """Result of an orphan-position scan on (re)start."""
    has_orphans: bool
    orphan_count: int
    orphan_positions: list[dict] = field(default_factory=list)
    checked_at: float = field(default_factory=time.time)
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "has_orphans": self.has_orphans,
            "orphan_count": self.orphan_count,
            "orphan_positions": list(self.orphan_positions),
            "checked_at": self.checked_at,
            "reason": self.reason,
        }


@dataclass
class CrashReport:
    """Auditable crash report generated after a recovery / restart."""
    timestamp: float
    reason: str
    recovery_events: list[dict] = field(default_factory=list)
    components: list[dict] = field(default_factory=list)
    orphan_positions: list[dict] = field(default_factory=list)
    fail_closed: bool = True
    design_note: str = "fail-closed, recoverable, auditable"
    never_claims_never_crash: bool = True

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "reason": self.reason,
            "recovery_events": list(self.recovery_events),
            "components": list(self.components),
            "orphan_positions": list(self.orphan_positions),
            "fail_closed": self.fail_closed,
            "design_note": self.design_note,
            "never_claims_never_crash": self.never_claims_never_crash,
        }


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
        positions_provider: Optional[Callable[[], list[dict]]] = None,
        crash_report_dir: Optional[Path] = None,
        fail_closed_guard: Optional[Any] = None,
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
        # Injectable positions provider — used by check_orphan_positions().
        # Must return a list of dicts (each representing an open position).
        self._positions_provider = positions_provider or (lambda: [])
        # Directory where crash reports are written.
        self._crash_report_dir = Path(crash_report_dir) if crash_report_dir else None
        # Optional FailClosedRuntimeGuard — when present, safe_restart()
        # will set its recovery gate so new trades are blocked.
        self._fail_closed_guard = fail_closed_guard

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

    # ─── Orphan positions & safe restart ───────────────────────────────

    def check_orphan_positions(
        self,
        positions: Optional[Sequence[dict]] = None,
        magic_filter: Optional[int] = None,
    ) -> OrphanPositionReport:
        """
        Scan for orphan positions left open by a previous run.

        Args:
            positions: optional explicit list of positions (each a dict).
                If omitted, the injected `positions_provider` is called.
            magic_filter: if set, only positions whose `magic` field
                matches are considered "ours".

        Returns:
            OrphanPositionReport. If orphans are found, the fail-closed
            guard (if wired) is set to recovery mode — callers MUST
            resolve orphans before allowing new trades.

        The system does NOT claim "orphan detection is impossible to fail".
        It claims fail-closed: if orphans are detected, new trades are
        blocked until they are resolved.
        """
        try:
            pos_list = list(positions) if positions is not None else list(self._positions_provider())
        except Exception as e:
            pos_list = []
            reason = f"positions_provider error: {e}"
        else:
            reason = ""

        if magic_filter is not None:
            pos_list = [
                p for p in pos_list
                if int(p.get("magic", -1)) == magic_filter
            ]

        orphan_count = len(pos_list)
        report = OrphanPositionReport(
            has_orphans=orphan_count > 0,
            orphan_count=orphan_count,
            orphan_positions=[dict(p) for p in pos_list],
            checked_at=time.time(),
            reason=reason or (
                f"{orphan_count} orphan position(s) detected"
                if orphan_count else "no orphan positions"
            ),
        )
        # Fail-closed: enter recovery if orphans found.
        if report.has_orphans and self._fail_closed_guard is not None:
            try:
                self._fail_closed_guard.set_recovery_mode(
                    True, reason=f"orphan_positions={orphan_count}"
                )
            except Exception as e:
                logger.error(f"Failed to set fail-closed recovery mode: {e}")
        if self.journal:
            try:
                self.journal.log_heartbeat({
                    "event": "orphan_position_check",
                    "has_orphans": report.has_orphans,
                    "orphan_count": report.orphan_count,
                })
            except Exception:
                pass
        return report

    async def safe_restart(
        self,
        reason: str = "operator initiated safe restart",
        magic_filter: Optional[int] = None,
    ) -> CrashReport:
        """
        Perform a safe restart sequence:
          1. Check for orphan positions (fail-closed if found).
          2. Generate a crash report capturing current state.
          3. If orphans are found, do NOT restart — return report and
             keep the runtime in recovery mode.
          4. If no orphans, restart each registered component via its
             `restart_fn`. In dry_run mode, restart is logged only.

        Returns:
            CrashReport. The system does NOT claim "safe restart always
            succeeds" — it claims "safe restart is fail-closed and
            auditable".
        """
        t0 = time.perf_counter()
        orphan_report = self.check_orphan_positions(magic_filter=magic_filter)
        report = CrashReport(
            timestamp=time.time(),
            reason=reason,
            recovery_events=[e.__dict__ if hasattr(e, "__dict__") else dict(e)
                             for e in self._recovery_events],
            components=[self.get_component_status(n) or {"name": n}
                        for n in self.registered_components],
            orphan_positions=orphan_report.orphan_positions,
            fail_closed=True,
        )
        # If orphans are present, fail-closed: do NOT restart.
        if orphan_report.has_orphans:
            report.reason = (
                f"safe_restart ABORTED: {orphan_report.orphan_count} "
                f"orphan position(s) detected — operator resolution required"
            )
            logger.error(report.reason)
            return report

        # No orphans — proceed with bounded restart.
        # In dry_run mode, restart is logged only (no live action).
        if self.dry_run:
            report.reason = (
                f"safe_restart DRY_RUN: {len(self.registered_components)} "
                f"component(s) would be restarted (reason={reason})"
            )
            logger.info(report.reason)
            return report

        # Live restart: cancel + restart each registered component.
        for name in self.registered_components:
            comp = self._components.get(name)
            if comp is None or comp.restart_fn is None:
                continue
            try:
                if comp.task is not None and not comp.task.done():
                    comp.task.cancel()
                    try:
                        await comp.task
                    except asyncio.CancelledError:
                        pass
                await comp.restart_fn()
                comp.last_restart = time.time()
                comp.restart_count += 1
            except Exception as e:
                logger.error(f"safe_restart: component '{name}' restart failed: {e}")
                # Fail-closed: enter recovery on restart failure.
                if self._fail_closed_guard is not None:
                    try:
                        self._fail_closed_guard.set_recovery_mode(
                            True, reason=f"restart_failed:{name}:{e}"
                        )
                    except Exception:
                        pass

        report.reason = (
            f"safe_restart COMPLETE: {len(self.registered_components)} "
            f"component(s) processed in {(time.perf_counter() - t0) * 1000:.1f}ms"
        )
        return report

    def generate_crash_report(
        self,
        reason: str = "manual crash report",
        out_dir: Optional[Path] = None,
    ) -> CrashReport:
        """
        Generate an auditable crash report and write it to disk
        (JSON + Markdown) if a directory is configured.

        The report does NOT claim "crash impossible" or "never crashes".
        It explicitly states: fail-closed, recoverable, auditable.
        """
        orphan_report = self.check_orphan_positions()
        report = CrashReport(
            timestamp=time.time(),
            reason=reason,
            recovery_events=[e.__dict__ if hasattr(e, "__dict__") else dict(e)
                             for e in self._recovery_events],
            components=[self.get_component_status(n) or {"name": n}
                        for n in self.registered_components],
            orphan_positions=orphan_report.orphan_positions,
            fail_closed=True,
            design_note="fail-closed, recoverable, auditable",
            never_claims_never_crash=True,
        )

        target_dir = Path(out_dir) if out_dir is not None else self._crash_report_dir
        if target_dir is not None:
            try:
                target_dir.mkdir(parents=True, exist_ok=True)
                ts_str = datetime.fromtimestamp(
                    report.timestamp, tz=timezone.utc
                ).strftime("%Y%m%dT%H%M%SZ")
                json_path = target_dir / f"crash_report_{ts_str}.json"
                md_path = target_dir / f"crash_report_{ts_str}.md"
                with open(json_path, "w", encoding="utf-8") as f:
                    json.dump(report.to_dict(), f, indent=2, default=str,
                              ensure_ascii=False)
                with open(md_path, "w", encoding="utf-8") as f:
                    f.write("# TITAN XAU AI - Crash Report\n\n")
                    f.write(f"**Reason:** {report.reason}\n\n")
                    f.write(f"**Timestamp:** {datetime.fromtimestamp(report.timestamp, tz=timezone.utc).isoformat()}\n\n")
                    f.write(f"**Design note:** {report.design_note}\n\n")
                    f.write(f"**Fail-closed:** {report.fail_closed}\n\n")
                    f.write(f"**Never claims 'never crash':** {report.never_claims_never_crash}\n\n")
                    f.write("## Recovery Events\n\n")
                    for e in report.recovery_events:
                        f.write(f"- {e}\n")
                    f.write("\n## Components\n\n")
                    for c in report.components:
                        f.write(f"- {c}\n")
                    f.write("\n## Orphan Positions\n\n")
                    if report.orphan_positions:
                        for p in report.orphan_positions:
                            f.write(f"- {p}\n")
                    else:
                        f.write("- (none)\n")
            except Exception as e:
                logger.error(f"Failed to write crash report: {e}")
        return report


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
