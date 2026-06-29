"""
TITAN XAU AI — Runtime Health & Recovery Foundation (Sprint 9.9.3.26)
=====================================================================

Detects runtime anomalies during demo micro execution and makes
fail-closed recovery decisions. Writes incident reports for audit.

Health checks (all non-blocking in dev/demo, fail-closed in release):
  1. MT5 disconnect              — mt5.initialize() fails or terminal_info disconnected
  2. Terminal closed             — terminal_info.connected == False
  3. Account switch              — login/server changed mid-cycle
  4. Symbol unavailable          — symbol_info returns None
  5. Stale tick / market closed  — tick time > 60s old, or trade_mode != market
  6. Existing TITAN position     — positions_get finds magic-matched position on startup
  7. order_send reject           — retcode 10006 / 10013 / 10018 / 10030
  8. Close reject                — close order_send retcode not in success set
  9. Stuck position              — position remains open after close attempt + timeout
  10. Journal write failure      — journal path not writable
  11. Loop crash                 — unhandled exception in execution loop

Recovery decisions:
  - MT5_DISCONNECTED        → stop, shutdown, require operator restart
  - TERMINAL_CLOSED         → stop, require operator restart
  - ACCOUNT_SWITCHED        → stop, force close all TITAN positions, block
  - SYMBOL_UNAVAILABLE      → stop, skip cycle
  - STALE_TICK              → wait + retry (3 attempts), then stop
  - MARKET_CLOSED           → stop, log, wait for market open
  - EXISTING_POSITION       → block start, require manual resolution
  - ORDER_SEND_REJECT       → log, try fallback (adapter handles), then fail cycle
  - CLOSE_REJECT            → retry close (3 attempts), then mark stuck
  - STUCK_POSITION          → force close, emergency close, manual review
  - JOURNAL_WRITE_FAILURE   → continue in-memory, log to stderr, flag for review
  - LOOP_CRASH              → force close all, write incident report, stop

Incident report:
  data/audit/demo_micro/incident_report_<timestamp>.json
  data/audit/demo_micro/incident_report_<timestamp>.md
"""
from __future__ import annotations
import json
import os
import sys
import time
import traceback
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

INCIDENT_DIR = REPO_ROOT / "data" / "audit" / "demo_micro"

# Success retcodes for order_send
_SUCCESS_RETCODES = frozenset({10009, 10010})

# Retryable retcodes
_RETRYABLE_RETCODES = frozenset({10004, 10006, 10020, 10021, 10030})

# Non-retryable (fail immediately)
_NON_RETRYABLE_RETCODES = frozenset({10013, 10014, 10015, 10016, 10018, 10019, 10027})

# Max close retry attempts
MAX_CLOSE_RETRIES = 3

# Max stale tick retry attempts
MAX_STALE_TICK_RETRIES = 3

# Stale tick threshold (seconds)
STALE_TICK_THRESHOLD = 60


class HealthStatus(Enum):
    """Runtime health status."""
    HEALTHY = "HEALTHY"
    WARNING = "WARNING"
    DEGRADED = "DEGRADED"
    CRITICAL = "CRITICAL"


class RecoveryAction(Enum):
    """Recovery decision for a detected anomaly."""
    CONTINUE = "CONTINUE"                     # no action needed
    RETRY = "RETRY"                           # retry the operation
    STOP_CYCLE = "STOP_CYCLE"                 # stop current cycle, continue to next
    STOP_ALL = "STOP_ALL"                     # stop all cycles immediately
    FORCE_CLOSE_ALL = "FORCE_CLOSE_ALL"       # force close all TITAN positions, then stop
    BLOCK_START = "BLOCK_START"               # block execution start
    WAIT_RETRY = "WAIT_RETRY"                 # wait and retry
    MANUAL_REVIEW = "MANUAL_REVIEW"           # require operator intervention


class HealthEvent:
    """A single runtime health event."""

    def __init__(self, event_type: str, severity: HealthStatus,
                 action: RecoveryAction, message: str,
                 details: dict = None):
        self.event_type = event_type
        self.severity = severity
        self.action = action
        self.message = message
        self.details = details or {}
        self.timestamp_utc = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return {
            "event_type": self.event_type,
            "severity": self.severity.value,
            "action": self.action.value,
            "message": self.message,
            "details": self.details,
            "timestamp_utc": self.timestamp_utc,
        }

    def __repr__(self):
        return (f"HealthEvent(type={self.event_type}, severity={self.severity.value}, "
                f"action={self.action.value})")


class RuntimeHealthMonitor:
    """Monitors runtime health during demo micro execution.

    Usage:
        monitor = RuntimeHealthMonitor(mt5, magic=20261993, symbol="XAUUSD")
        events = monitor.check_startup()
        if monitor.should_block_start(events):
            print("Blocked — cannot start")
            return
        # ... run cycles ...
        events = monitor.check_tick_health()
        if monitor.should_stop(events):
            print("Stopping — health critical")
            return
    """

    def __init__(self, mt5=None, magic: int = 20261993,
                 symbol: str = "XAUUSD",
                 journal_path: Optional[str] = None):
        self.mt5 = mt5
        self.magic = magic
        self.symbol = symbol
        self.journal_path = Path(journal_path) if journal_path else None
        self._events: list[HealthEvent] = []
        self._initial_login: Optional[int] = None
        self._initial_server: Optional[str] = None

    def _safe(self, obj, attr, default=None):
        try:
            return getattr(obj, attr, default)
        except Exception:
            return default

    def _record(self, event: HealthEvent) -> None:
        self._events.append(event)

    def get_events(self) -> list[HealthEvent]:
        return list(self._events)

    def clear_events(self) -> None:
        self._events.clear()

    # ─── Startup checks ──────────────────────────────────────────────────────

    def check_startup(self) -> list[HealthEvent]:
        """Run all startup health checks. Returns list of events."""
        events = []

        # 1. MT5 reachable
        events.extend(self._check_mt5_connected())

        # 2. Terminal connected
        events.extend(self._check_terminal_connected())

        # 3. Account info + capture initial login/server
        events.extend(self._check_account())

        # 4. Symbol available
        events.extend(self._check_symbol_available())

        # 5. Tick freshness / market open
        events.extend(self._check_tick_freshness())

        # 6. Existing TITAN position on startup
        events.extend(self._check_existing_position())

        # 7. Journal writable
        events.extend(self._check_journal_writable())

        for e in events:
            self._record(e)
        return events

    def _check_mt5_connected(self) -> list[HealthEvent]:
        """Check if MT5 is reachable."""
        if self.mt5 is None:
            return [HealthEvent(
                "MT5_UNAVAILABLE", HealthStatus.CRITICAL,
                RecoveryAction.BLOCK_START,
                "MT5 module not available (Linux/Z AI)",
            )]
        try:
            if not self.mt5.initialize():
                return [HealthEvent(
                    "MT5_DISCONNECTED", HealthStatus.CRITICAL,
                    RecoveryAction.BLOCK_START,
                    "mt5.initialize() returned False",
                )]
        except Exception as e:
            return [HealthEvent(
                "MT5_DISCONNECTED", HealthStatus.CRITICAL,
                RecoveryAction.BLOCK_START,
                f"mt5.initialize() raised: {e}",
            )]
        return []

    def _check_terminal_connected(self) -> list[HealthEvent]:
        """Check if MT5 terminal is connected."""
        if self.mt5 is None:
            return []
        try:
            terminal = self.mt5.terminal_info()
            if terminal is None:
                return [HealthEvent(
                    "TERMINAL_CLOSED", HealthStatus.CRITICAL,
                    RecoveryAction.BLOCK_START,
                    "terminal_info() returned None — terminal may be closed",
                )]
            if not self._safe(terminal, "connected", False):
                return [HealthEvent(
                    "TERMINAL_CLOSED", HealthStatus.CRITICAL,
                    RecoveryAction.STOP_ALL,
                    "Terminal not connected",
                )]
        except Exception as e:
            return [HealthEvent(
                "TERMINAL_CLOSED", HealthStatus.WARNING,
                RecoveryAction.CONTINUE,
                f"terminal_info() raised: {e}",
            )]
        return []

    def _check_account(self) -> list[HealthEvent]:
        """Check account info and capture initial login/server."""
        if self.mt5 is None:
            return []
        try:
            account = self.mt5.account_info()
            if account is None:
                return [HealthEvent(
                    "ACCOUNT_UNAVAILABLE", HealthStatus.CRITICAL,
                    RecoveryAction.BLOCK_START,
                    "account_info() returned None",
                )]
            self._initial_login = self._safe(account, "login")
            self._initial_server = self._safe(account, "server")
            trade_mode = self._safe(account, "trade_mode", 2)
            if trade_mode != 0:
                return [HealthEvent(
                    "ACCOUNT_NOT_DEMO", HealthStatus.CRITICAL,
                    RecoveryAction.BLOCK_START,
                    f"Account trade_mode={trade_mode} — NOT DEMO",
                )]
        except Exception as e:
            return [HealthEvent(
                "ACCOUNT_UNAVAILABLE", HealthStatus.CRITICAL,
                RecoveryAction.BLOCK_START,
                f"account_info() raised: {e}",
            )]
        return []

    def _check_symbol_available(self) -> list[HealthEvent]:
        """Check if symbol is available."""
        if self.mt5 is None:
            return []
        try:
            info = self.mt5.symbol_info(self.symbol)
            if info is None:
                return [HealthEvent(
                    "SYMBOL_UNAVAILABLE", HealthStatus.CRITICAL,
                    RecoveryAction.STOP_CYCLE,
                    f"symbol_info({self.symbol}) returned None",
                )]
        except Exception as e:
            return [HealthEvent(
                "SYMBOL_UNAVAILABLE", HealthStatus.CRITICAL,
                RecoveryAction.STOP_CYCLE,
                f"symbol_info() raised: {e}",
            )]
        return []

    def _check_tick_freshness(self) -> list[HealthEvent]:
        """Check if tick is fresh and market is open."""
        if self.mt5 is None:
            return []
        try:
            tick = self.mt5.symbol_info_tick(self.symbol)
            if tick is None:
                return [HealthEvent(
                    "STALE_TICK", HealthStatus.WARNING,
                    RecoveryAction.WAIT_RETRY,
                    "symbol_info_tick returned None",
                )]
            tick_time = self._safe(tick, "time", 0)
            if tick_time == 0:
                return [HealthEvent(
                    "STALE_TICK", HealthStatus.WARNING,
                    RecoveryAction.WAIT_RETRY,
                    "Tick time is 0 — no tick data",
                )]
            age = time.time() - tick_time
            if age > STALE_TICK_THRESHOLD:
                return [HealthEvent(
                    "STALE_TICK", HealthStatus.WARNING,
                    RecoveryAction.WAIT_RETRY,
                    f"Tick is {age:.0f}s old (> {STALE_TICK_THRESHOLD}s threshold)",
                    {"tick_age_seconds": round(age, 1)},
                )]
        except Exception as e:
            return [HealthEvent(
                "STALE_TICK", HealthStatus.WARNING,
                RecoveryAction.WAIT_RETRY,
                f"symbol_info_tick() raised: {e}",
            )]
        return []

    def _check_existing_position(self) -> list[HealthEvent]:
        """Check for existing TITAN positions on startup."""
        if self.mt5 is None:
            return []
        try:
            positions = self.mt5.positions_get(symbol=self.symbol) or []
            matching = [p for p in positions if self._safe(p, "magic", 0) == self.magic]
            if matching:
                tickets = [self._safe(p, "ticket") for p in matching]
                return [HealthEvent(
                    "EXISTING_POSITION", HealthStatus.CRITICAL,
                    RecoveryAction.BLOCK_START,
                    f"Existing TITAN position(s) found on startup: {len(matching)}",
                    {"tickets": tickets, "count": len(matching)},
                )]
        except Exception as e:
            return [HealthEvent(
                "EXISTING_POSITION", HealthStatus.WARNING,
                RecoveryAction.CONTINUE,
                f"positions_get() raised: {e}",
            )]
        return []

    def _check_journal_writable(self) -> list[HealthEvent]:
        """Check if journal path is writable."""
        if self.journal_path is None:
            return []
        try:
            parent = self.journal_path.parent
            parent.mkdir(parents=True, exist_ok=True)
            test_path = parent / ".health_check_write_test"
            test_path.write_text("ok")
            test_path.unlink()
        except Exception as e:
            return [HealthEvent(
                "JOURNAL_WRITE_FAILURE", HealthStatus.WARNING,
                RecoveryAction.CONTINUE,
                f"Journal path not writable: {e}",
            )]
        return []

    # ─── Runtime checks (during cycles) ──────────────────────────────────────

    def check_tick_health(self) -> list[HealthEvent]:
        """Check tick freshness during execution."""
        return self._check_tick_freshness()

    def check_account_switch(self) -> list[HealthEvent]:
        """Check if account login/server changed mid-cycle."""
        if self.mt5 is None or self._initial_login is None:
            return []
        try:
            account = self.mt5.account_info()
            if account is None:
                return [HealthEvent(
                    "ACCOUNT_SWITCHED", HealthStatus.CRITICAL,
                    RecoveryAction.FORCE_CLOSE_ALL,
                    "account_info() returned None mid-cycle — account may have switched",
                )]
            current_login = self._safe(account, "login")
            current_server = self._safe(account, "server")
            if str(current_login) != str(self._initial_login):
                return [HealthEvent(
                    "ACCOUNT_SWITCHED", HealthStatus.CRITICAL,
                    RecoveryAction.FORCE_CLOSE_ALL,
                    f"Login changed: {self._initial_login} → {current_login}",
                )]
            if current_server != self._initial_server:
                return [HealthEvent(
                    "ACCOUNT_SWITCHED", HealthStatus.CRITICAL,
                    RecoveryAction.FORCE_CLOSE_ALL,
                    f"Server changed: {self._initial_server} → {current_server}",
                )]
        except Exception as e:
            return [HealthEvent(
                "ACCOUNT_SWITCHED", HealthStatus.WARNING,
                RecoveryAction.CONTINUE,
                f"account_info() raised during switch check: {e}",
            )]
        return []

    def check_order_send_result(self, retcode: Optional[int],
                                  operation: str = "open") -> list[HealthEvent]:
        """Check order_send result retcode."""
        if retcode is None:
            return [HealthEvent(
                "ORDER_SEND_NONE", HealthStatus.WARNING,
                RecoveryAction.RETRY,
                f"order_send ({operation}) returned None — MT5 internal error",
                {"operation": operation, "retcode": retcode},
            )]
        if retcode in _SUCCESS_RETCODES:
            return []
        if retcode == 10018:
            return [HealthEvent(
                "MARKET_CLOSED", HealthStatus.CRITICAL,
                RecoveryAction.STOP_ALL,
                f"order_send ({operation}) retcode=10018 — MARKET_CLOSED",
                {"operation": operation, "retcode": retcode},
            )]
        if retcode in _RETRYABLE_RETCODES:
            return [HealthEvent(
                "ORDER_SEND_REJECT", HealthStatus.WARNING,
                RecoveryAction.RETRY,
                f"order_send ({operation}) rejected: retcode={retcode}",
                {"operation": operation, "retcode": retcode},
            )]
        if retcode in _NON_RETRYABLE_RETCODES:
            return [HealthEvent(
                "ORDER_SEND_REJECT", HealthStatus.CRITICAL,
                RecoveryAction.STOP_CYCLE,
                f"order_send ({operation}) non-retryable reject: retcode={retcode}",
                {"operation": operation, "retcode": retcode},
            )]
        # Unknown retcode
        return [HealthEvent(
            "ORDER_SEND_REJECT", HealthStatus.WARNING,
            RecoveryAction.STOP_CYCLE,
            f"order_send ({operation}) unknown retcode={retcode}",
            {"operation": operation, "retcode": retcode},
        )]

    def check_close_result(self, retcode: Optional[int]) -> list[HealthEvent]:
        """Check close order_send result."""
        events = self.check_order_send_result(retcode, operation="close")
        # For close failures, escalate to force close
        for e in events:
            if e.severity == HealthStatus.CRITICAL and e.action == RecoveryAction.STOP_CYCLE:
                e.action = RecoveryAction.FORCE_CLOSE_ALL
                e.message += " — escalating to force close"
        return events

    def check_stuck_position(self, max_close_retries: int = MAX_CLOSE_RETRIES) -> list[HealthEvent]:
        """Check if position is stuck (still open after close attempts)."""
        if self.mt5 is None:
            return []
        try:
            positions = self.mt5.positions_get(symbol=self.symbol) or []
            matching = [p for p in positions if self._safe(p, "magic", 0) == self.magic]
            if matching:
                tickets = [self._safe(p, "ticket") for p in matching]
                return [HealthEvent(
                    "STUCK_POSITION", HealthStatus.CRITICAL,
                    RecoveryAction.FORCE_CLOSE_ALL,
                    f"Position still open after {max_close_retries} close attempts",
                    {"tickets": tickets, "close_attempts": max_close_retries},
                )]
        except Exception as e:
            return [HealthEvent(
                "STUCK_POSITION", HealthStatus.WARNING,
                RecoveryAction.CONTINUE,
                f"positions_get() raised during stuck check: {e}",
            )]
        return []

    def check_loop_crash(self, exc: Exception) -> list[HealthEvent]:
        """Record a loop crash (unhandled exception)."""
        tb = traceback.format_exc()
        return [HealthEvent(
            "LOOP_CRASH", HealthStatus.CRITICAL,
            RecoveryAction.FORCE_CLOSE_ALL,
            f"Unhandled exception in execution loop: {exc}",
            {
                "exception_type": type(exc).__name__,
                "exception_message": str(exc),
                "traceback": tb,
            },
        )]

    # ─── Recovery decision helpers ───────────────────────────────────────────

    def should_block_start(self, events: list[HealthEvent]) -> bool:
        """True if any event requires blocking execution start."""
        return any(e.action == RecoveryAction.BLOCK_START for e in events)

    def should_stop(self, events: list[HealthEvent]) -> bool:
        """True if any event requires stopping all execution."""
        return any(e.action in (RecoveryAction.STOP_ALL, RecoveryAction.FORCE_CLOSE_ALL)
                    for e in events)

    def should_stop_cycle(self, events: list[HealthEvent]) -> bool:
        """True if any event requires stopping the current cycle."""
        return any(e.action in (RecoveryAction.STOP_CYCLE, RecoveryAction.STOP_ALL,
                                 RecoveryAction.FORCE_CLOSE_ALL)
                    for e in events)

    def should_force_close(self, events: list[HealthEvent]) -> bool:
        """True if any event requires force closing all positions."""
        return any(e.action == RecoveryAction.FORCE_CLOSE_ALL for e in events)

    # ─── Health status summary ───────────────────────────────────────────────

    def get_health_status(self) -> dict:
        """Return current health status summary."""
        events = self.get_events()
        if not events:
            return {"status": HealthStatus.HEALTHY.value, "event_count": 0,
                    "actions": [], "events": []}
        max_sev_str = _max_severity(events)
        max_severity = HealthStatus(max_sev_str)
        return {
            "status": max_severity.value,
            "event_count": len(events),
            "actions": [e.action.value for e in events],
            "events": [e.to_dict() for e in events],
        }


# ─── Incident report writer ───────────────────────────────────────────────────

# Severity ordering for comparison (higher = more severe)
_SEVERITY_ORDER = {
    HealthStatus.HEALTHY: 0,
    HealthStatus.WARNING: 1,
    HealthStatus.DEGRADED: 2,
    HealthStatus.CRITICAL: 3,
}


def _max_severity(events: list[HealthEvent]) -> str:
    """Return the highest severity among events as a string."""
    if not events:
        return HealthStatus.HEALTHY.value
    max_ev = max(events, key=lambda e: _SEVERITY_ORDER.get(e.severity, 0))
    return max_ev.severity.value


def write_incident_report(events: list[HealthEvent],
                           context: dict = None,
                           output_dir: Path = None) -> dict:
    """Write incident report JSON + MD.

    Args:
        events: List of HealthEvent objects.
        context: Additional context (cycle, operation, etc.).
        output_dir: Directory for report files. Default: data/audit/demo_micro/.

    Returns:
        dict with json_path, md_path.
    """
    if output_dir is None:
        output_dir = INCIDENT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    json_path = output_dir / f"incident_report_{timestamp}.json"
    md_path = output_dir / f"incident_report_{timestamp}.md"

    report = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "event_count": len(events),
        "events": [e.to_dict() for e in events],
        "context": context or {},
        "max_severity": _max_severity(events),
        "recovery_actions": [e.action.value for e in events],
    }

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# TITAN Runtime Incident Report\n\n")
        f.write(f"**Timestamp:** {report['timestamp_utc']}\n\n")
        f.write(f"**Max Severity:** {report['max_severity']}\n\n")
        f.write(f"**Event Count:** {report['event_count']}\n\n")
        if context:
            f.write("## Context\n\n")
            for k, v in context.items():
                f.write(f"- **{k}**: {v}\n")
            f.write("\n")
        f.write("## Events\n\n")
        f.write("| # | Type | Severity | Action | Message | Timestamp |\n")
        f.write("|---|---|---|---|---|---|\n")
        for i, e in enumerate(events, 1):
            f.write(f"| {i} | {e.event_type} | {e.severity.value} | "
                    f"{e.action.value} | {e.message[:80]} | {e.timestamp_utc} |\n")
        f.write("\n## Event Details\n\n")
        for i, e in enumerate(events, 1):
            f.write(f"### Event {i}: {e.event_type}\n\n")
            f.write(f"- **Severity:** {e.severity.value}\n")
            f.write(f"- **Action:** {e.action.value}\n")
            f.write(f"- **Message:** {e.message}\n")
            if e.details:
                f.write(f"- **Details:** `{json.dumps(e.details, default=str)}`\n")
            f.write(f"- **Timestamp:** {e.timestamp_utc}\n\n")

    return {"json_path": str(json_path), "md_path": str(md_path)}
