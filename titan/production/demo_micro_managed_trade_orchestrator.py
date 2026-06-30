"""
TITAN XAU AI - Managed Trade Orchestrator (Sprint 9.9.3.45.1)
===============================================================
After order_send success, monitors open TITAN_DEMO_MICRO position
and applies breakeven/trailing/profit-lock via position manager.

NEVER widens SL. NEVER removes TP. NEVER touches non-TITAN positions.
"""
from __future__ import annotations
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from titan.production.demo_micro_position_manager import (
    DemoMicroPositionManager, SLAction,
)


class MonitorVerdict(str, Enum):
    MONITOR_STARTED = "MONITOR_STARTED"
    MONITOR_STOPPED = "MONITOR_STOPPED"
    MONITOR_POSITION_CLOSED = "MONITOR_POSITION_CLOSED"
    MONITOR_BLOCKED = "MONITOR_BLOCKED"


@dataclass
class MonitorEvent:
    timestamp_utc: str
    event_type: str
    description: str
    sl_action: str = "HOLD"
    new_sl: float = 0.0
    current_sl: float = 0.0
    favorable: bool = True


@dataclass
class ManagedTradeResult:
    verdict: str = "MANAGED_DEMO_MICRO_BLOCKED"
    entry_result: str = ""
    position_ticket: int = 0
    initial_sl: float = 0.0
    initial_tp: float = 0.0
    breakeven_triggered: bool = False
    trailing_triggered: bool = False
    profit_lock_triggered: bool = False
    sl_modify_previews: list[dict] = field(default_factory=list)
    sl_modify_attempts: list[dict] = field(default_factory=list)
    final_position_status: str = ""
    realized_pl: float = 0.0
    monitor_events: list[dict] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    timestamp_utc: str = ""

    def __post_init__(self):
        if not self.timestamp_utc:
            self.timestamp_utc = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return asdict(self)


class ManagedTradeOrchestrator:
    """Orchestrates managed demo micro trade with position monitoring."""

    def __init__(self, duration_minutes: int = 30, interval_seconds: int = 5,
                 apply_modifications: bool = False):
        self.duration_minutes = duration_minutes
        self.interval_seconds = interval_seconds
        self.apply_modifications = apply_modifications
        self.manager = DemoMicroPositionManager()
        self.events: list[MonitorEvent] = []

    def monitor_position(self, position_ticket: int = 0,
                          direction: str = "BUY",
                          entry_price: float = 0.0,
                          current_sl: float = 0.0,
                          current_tp: float = 0.0,
                          current_price: float = 0.0,
                          is_open: bool = True,
                          ) -> ManagedTradeResult:
        """Monitor a single position for breakeven/trailing/profit-lock.

        In preview mode (apply_modifications=False), only builds SL modify previews.
        In apply mode (apply_modifications=True), would apply SL modifications.
        Z AI must NOT use apply mode.
        """
        result = ManagedTradeResult(
            position_ticket=position_ticket,
            initial_sl=current_sl,
            initial_tp=current_tp,
            verdict="MANAGED_DEMO_MICRO_STARTED",
        )

        if not is_open:
            result.verdict = "MANAGED_DEMO_MICRO_COMPLETED"
            result.final_position_status = "CLOSED"
            result.warnings.append("Position already closed before monitoring started")
            return result

        # Evaluate position manager
        rec = self.manager.evaluate(
            direction=direction,
            entry_price=entry_price,
            current_price=current_price,
            current_sl=current_sl,
            current_tp=current_tp,
        )

        event = MonitorEvent(
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            event_type="MONITOR_EVALUATION",
            description=f"Evaluated: {rec.reason}",
            sl_action=rec.action.value,
            new_sl=rec.new_sl,
            current_sl=rec.current_sl,
            favorable=rec.favorable,
        )
        self.events.append(event)

        if rec.action == SLAction.MOVE_TO_BREAKEVEN:
            result.breakeven_triggered = True
        elif rec.action == SLAction.TRAIL:
            result.trailing_triggered = True
        elif rec.action == SLAction.PROFIT_LOCK:
            result.profit_lock_triggered = True

        # Build SL modify preview
        if rec.action != SLAction.HOLD and rec.action != SLAction.BLOCKED:
            preview = {
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "action": rec.action.value,
                "new_sl": rec.new_sl,
                "current_sl": rec.current_sl,
                "tp": rec.tp,
                "favorable": rec.favorable,
                "reason": rec.reason,
                "applied": False,  # Preview only in Z AI
            }
            result.sl_modify_previews.append(preview)

        result.verdict = "MANAGED_DEMO_MICRO_COMPLETED"
        result.final_position_status = "OPEN" if is_open else "CLOSED"
        result.monitor_events = [e.__dict__ for e in self.events]

        if result.warnings:
            result.verdict = "MANAGED_DEMO_MICRO_COMPLETED_WITH_WARNINGS"

        return result
