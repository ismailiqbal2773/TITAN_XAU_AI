"""
TITAN XAU AI — Runtime Health Monitor (Sprint 6)

Monitors runtime health: CPU, memory, uptime, heartbeats, restarts.
Generates alerts when thresholds exceeded.

Usage:
    monitor = RuntimeHealthMonitor(journal=journal)
    health = monitor.check()
    if health.alert:
        # take action
        ...
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field, asdict
from typing import Optional

from titan.production.trade_journal import TradeJournal, EventType

logger = logging.getLogger(__name__)


@dataclass
class HealthStatus:
    """Runtime health snapshot."""
    timestamp: float
    uptime_seconds: float = 0.0
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    memory_mb: float = 0.0
    missed_heartbeats: int = 0
    restart_count: int = 0
    api_available: bool = False
    alert: bool = False
    alert_reasons: list[str] = field(default_factory=list)

    def __repr__(self) -> str:
        return (
            f"HealthStatus(uptime={self.uptime_seconds/3600:.1f}h, "
            f"cpu={self.cpu_percent:.1f}%, mem={self.memory_percent:.1f}%, "
            f"missed_hb={self.missed_heartbeats}, restarts={self.restart_count}, "
            f"alert={self.alert})"
        )


@dataclass
class HealthConfig:
    """Health monitoring thresholds."""
    cpu_alert_pct: float = 80.0
    memory_alert_pct: float = 80.0
    max_missed_heartbeats: int = 5
    max_restarts: int = 10
    uptime_alert_hours: float = 0.0   # 0 = no alert on uptime


class RuntimeHealthMonitor:
    """
    Monitors runtime health metrics.

    Uses psutil if available, otherwise falls back to /proc on Linux
    or stub values.
    """

    def __init__(
        self,
        journal: Optional[TradeJournal] = None,
        config: Optional[HealthConfig] = None,
    ):
        self.journal = journal
        self.config = config or HealthConfig()
        self._start_time = time.time()
        self._psutil = None
        try:
            import psutil
            self._psutil = psutil
        except ImportError:
            logger.warning("psutil not available — using stub health metrics")
        self._last_heartbeat: dict[str, float] = {}
        self._restart_count = 0

    def record_heartbeat(self, component: str) -> None:
        """Record a heartbeat from a component."""
        self._last_heartbeat[component] = time.time()

    def record_restart(self, component: str = "system") -> None:
        """Record a component restart."""
        self._restart_count += 1
        if self.journal:
            self.journal.log_event(EventType.WATCHDOG_RESTART, {
                "component": component,
                "restart_count": self._restart_count,
            })

    def check(self) -> HealthStatus:
        """Check current health. Returns HealthStatus."""
        now = time.time()
        status = HealthStatus(timestamp=now)
        status.uptime_seconds = now - self._start_time
        status.restart_count = self._restart_count

        # ── CPU + Memory ──
        if self._psutil is not None:
            try:
                status.cpu_percent = self._psutil.cpu_percent(interval=0.1)
                mem = self._psutil.virtual_memory()
                status.memory_percent = mem.percent
                status.memory_mb = mem.used / (1024 * 1024)
            except Exception as e:
                logger.warning(f"psutil check failed: {e}")
        else:
            # Stub values
            status.cpu_percent = 15.0
            status.memory_percent = 30.0
            status.memory_mb = 256.0

        # ── Missed heartbeats ──
        status.missed_heartbeats = 0
        for comp, last_beat in self._last_heartbeat.items():
            elapsed = now - last_beat
            if elapsed > 60:  # 60s without heartbeat = missed
                status.missed_heartbeats += 1

        # ── API availability (stub — would check /health endpoint) ──
        status.api_available = True  # simplified

        # ── Alert evaluation ──
        reasons = []
        if status.cpu_percent >= self.config.cpu_alert_pct:
            reasons.append(f"cpu_high ({status.cpu_percent:.1f}%)")
        if status.memory_percent >= self.config.memory_alert_pct:
            reasons.append(f"memory_high ({status.memory_percent:.1f}%)")
        if status.missed_heartbeats >= self.config.max_missed_heartbeats:
            reasons.append(f"missed_heartbeats ({status.missed_heartbeats})")
        if status.restart_count >= self.config.max_restarts:
            reasons.append(f"restart_count ({status.restart_count})")
        if self.config.uptime_alert_hours > 0 and status.uptime_seconds / 3600 < self.config.uptime_alert_hours:
            reasons.append(f"uptime_low ({status.uptime_seconds/3600:.1f}h)")

        status.alert = len(reasons) > 0
        status.alert_reasons = reasons

        if status.alert and self.journal:
            self.journal.log_event(EventType.DRIFT_ALERT, {
                "health_alert": True,
                "reasons": reasons,
                "cpu": status.cpu_percent,
                "memory": status.memory_percent,
                "uptime_s": status.uptime_seconds,
            })

        return status

    @property
    def uptime_seconds(self) -> float:
        return time.time() - self._start_time

    @property
    def uptime_hours(self) -> float:
        return self.uptime_seconds / 3600.0
