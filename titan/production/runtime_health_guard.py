"""
TITAN XAU AI — Runtime Health Guard (Production Resilience)
=============================================================

Tracks component heartbeats, detects component failures, and places the
runtime into a safe recovery mode when failures accumulate.

Design:
  - Pure-Python, no MetaTrader5 import, no order_send.
  - Heartbeat per component with bounded staleness threshold.
  - Fail-closed: when ANY critical component fails, the guard enters
    recovery mode and is_healthy() returns False — callers MUST block
    new trades in that state.
  - Auditable: every state change is journaled.

NEVER imports MetaTrader5. NEVER calls mt5.order_send.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Callable


@dataclass
class ComponentHealth:
    """Last-known health of a single component."""
    name: str
    last_heartbeat: float
    expected_interval_s: float
    healthy: bool
    last_failure_reason: str = ""
    failure_count: int = 0
    last_status: str = "unknown"

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "last_heartbeat": self.last_heartbeat,
            "expected_interval_s": self.expected_interval_s,
            "healthy": self.healthy,
            "last_failure_reason": self.last_failure_reason,
            "failure_count": self.failure_count,
            "last_status": self.last_status,
        }


@dataclass
class HealthSnapshot:
    """Snapshot of overall runtime health."""
    healthy: bool
    in_recovery: bool
    recovery_reason: str
    components: dict[str, ComponentHealth] = field(default_factory=dict)
    checked_at: float = field(default_factory=time.time)
    consecutive_failures: int = 0

    def to_dict(self) -> dict:
        return {
            "healthy": self.healthy,
            "in_recovery": self.in_recovery,
            "recovery_reason": self.recovery_reason,
            "consecutive_failures": self.consecutive_failures,
            "checked_at": self.checked_at,
            "components": {k: v.to_dict() for k, v in self.components.items()},
        }


class RuntimeHealthGuard:
    """
    Tracks per-component heartbeat health, detects failures, and
    switches the runtime into a safe recovery mode.

    Args:
        clock: injectable clock for tests.
        recovery_threshold: number of consecutive unhealthy checks
            before entering recovery mode (default 2).
        on_recovery_entered: optional callback when recovery is entered.
        on_recovery_exited: optional callback when recovery is exited.
    """

    def __init__(
        self,
        clock: Optional[Callable[[], float]] = None,
        recovery_threshold: int = 2,
        on_recovery_entered: Optional[Callable[[str], None]] = None,
        on_recovery_exited: Optional[Callable[[], None]] = None,
    ) -> None:
        if recovery_threshold < 1:
            raise ValueError("recovery_threshold must be >= 1")
        self._clock = clock or time.time
        self.recovery_threshold = recovery_threshold
        self._on_recovery_entered = on_recovery_entered
        self._on_recovery_exited = on_recovery_exited

        self._components: dict[str, ComponentHealth] = {}
        self._in_recovery: bool = False
        self._recovery_reason: str = ""
        self._consecutive_failures: int = 0
        self._journal: list[dict] = []

    # ─── Component registration & heartbeat ────────────────────────────

    def register_component(
        self,
        name: str,
        expected_interval_s: float,
    ) -> None:
        """Register a component for health tracking."""
        if expected_interval_s <= 0:
            raise ValueError("expected_interval_s must be > 0")
        self._components[name] = ComponentHealth(
            name=name,
            last_heartbeat=0.0,
            expected_interval_s=expected_interval_s,
            healthy=False,
            last_status="registered",
        )
        self._journal.append({
            "ts": self._clock(),
            "event": "component_registered",
            "component": name,
            "expected_interval_s": expected_interval_s,
        })

    def heartbeat(self, component: str, status: str = "ok") -> None:
        """Record a heartbeat from a component."""
        if component not in self._components:
            raise KeyError(f"component '{component}' not registered")
        now = self._clock()
        c = self._components[component]
        c.last_heartbeat = now
        c.last_status = status
        c.healthy = True
        c.last_failure_reason = ""
        self._journal.append({
            "ts": now,
            "event": "heartbeat",
            "component": component,
            "status": status,
        })

    def check_component(self, component: str) -> bool:
        """
        Check whether a single component is healthy based on its last
        heartbeat. Updates internal state. Returns True if healthy.
        """
        if component not in self._components:
            raise KeyError(f"component '{component}' not registered")
        now = self._clock()
        c = self._components[component]
        if c.last_heartbeat == 0:
            c.healthy = False
            c.last_failure_reason = "no heartbeat ever received"
            c.failure_count += 1
        else:
            elapsed = now - c.last_heartbeat
            if elapsed > c.expected_interval_s:
                c.healthy = False
                c.last_failure_reason = (
                    f"heartbeat stale: {elapsed:.1f}s > {c.expected_interval_s:.1f}s"
                )
                c.failure_count += 1
            else:
                c.healthy = True
                c.last_failure_reason = ""
        self._journal.append({
            "ts": now,
            "event": "component_check",
            "component": component,
            "healthy": c.healthy,
            "reason": c.last_failure_reason,
        })
        # Re-evaluate overall health
        self._evaluate_recovery()
        return c.healthy

    # ─── Recovery mode ─────────────────────────────────────────────────

    def enter_recovery_mode(self, reason: str) -> None:
        """Force the runtime into recovery mode."""
        if not self._in_recovery:
            self._in_recovery = True
            self._journal.append({
                "ts": self._clock(),
                "event": "recovery_entered",
                "reason": reason,
            })
            if self._on_recovery_entered:
                try:
                    self._on_recovery_entered(reason)
                except Exception:
                    pass
        self._recovery_reason = reason

    def exit_recovery_mode(self) -> None:
        """Exit recovery mode (only valid if all components healthy)."""
        if not self._in_recovery:
            return
        # Only exit if every registered component is currently healthy.
        all_healthy = all(c.healthy for c in self._components.values()) and \
            len(self._components) > 0
        if all_healthy:
            self._in_recovery = False
            self._recovery_reason = ""
            self._consecutive_failures = 0
            self._journal.append({
                "ts": self._clock(),
                "event": "recovery_exited",
            })
            if self._on_recovery_exited:
                try:
                    self._on_recovery_exited()
                except Exception:
                    pass

    def _evaluate_recovery(self) -> None:
        """Auto-enter recovery if any component is unhealthy."""
        any_unhealthy = any(not c.healthy for c in self._components.values())
        if any_unhealthy:
            self._consecutive_failures += 1
            if self._consecutive_failures >= self.recovery_threshold and not self._in_recovery:
                bad = [c.name for c in self._components.values() if not c.healthy]
                self.enter_recovery_mode(
                    f"components unhealthy: {','.join(bad)}"
                )
        else:
            if self._in_recovery:
                self.exit_recovery_mode()

    # ─── Public accessors ──────────────────────────────────────────────

    def is_healthy(self) -> bool:
        """Return True only if NOT in recovery AND all components healthy."""
        if self._in_recovery:
            return False
        if not self._components:
            return False  # nothing registered → not healthy
        return all(c.healthy for c in self._components.values())

    @property
    def in_recovery(self) -> bool:
        return self._in_recovery

    @property
    def recovery_reason(self) -> str:
        return self._recovery_reason

    @property
    def consecutive_failures(self) -> int:
        return self._consecutive_failures

    def snapshot(self) -> HealthSnapshot:
        return HealthSnapshot(
            healthy=self.is_healthy(),
            in_recovery=self._in_recovery,
            recovery_reason=self._recovery_reason,
            components={k: v for k, v in self._components.items()},
            checked_at=self._clock(),
            consecutive_failures=self._consecutive_failures,
        )

    @property
    def journal(self) -> list[dict]:
        return list(self._journal)

    def registered_components(self) -> list[str]:
        return list(self._components.keys())

    def get_component(self, name: str) -> Optional[ComponentHealth]:
        return self._components.get(name)


__all__ = [
    "RuntimeHealthGuard",
    "ComponentHealth",
    "HealthSnapshot",
]
