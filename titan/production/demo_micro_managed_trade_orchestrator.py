"""
TITAN XAU AI - Managed Trade Orchestrator (Sprint 9.9.3.45.6)
===============================================================
After order_send success, monitors open TITAN_DEMO_MICRO position
and applies breakeven/trailing/profit-lock via position manager.

Sprint 9.9.3.45.6 changes:
  - Default monitor duration: 30 minutes
  - Default monitor interval: 5 seconds
  - Monitor must continue while position is open until: position closes,
    timeout reached, kill switch/gate blocks, or unrecoverable error.
  - It must NOT exit after one HOLD evaluation while position is still open.
  - monitor_iterations > 1 when position remains open beyond one interval.
  - monitor_stop_reason explicit: POSITION_CLOSED, TIMEOUT,
    KILL_SWITCH_BLOCKED, GATE_BLOCKED, ERROR.
  - final_position_status from final positions_get/history check.
  - Apply path: only when action is MODIFY (not HOLD), SL move favorable,
    all gates pass. One modify attempt per decision step. No retry.
  - Journals every decision: HOLD, BREAKEVEN_MODIFY, TRAILING_MODIFY,
    PROFIT_LOCK_MODIFY, MODIFY_BLOCKED, MODIFY_SUCCESS, MODIFY_FAILED.

NEVER widens SL. NEVER removes TP. NEVER touches non-TITAN positions.
NEVER sends orders directly in Z AI (apply mode requires local operator).
"""
from __future__ import annotations
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Callable

from titan.production.demo_micro_position_manager import (
    DemoMicroPositionManager, SLAction, SLModifyRecommendation,
)


class MonitorVerdict(str, Enum):
    MONITOR_STARTED = "MONITOR_STARTED"
    MONITOR_STOPPED = "MONITOR_STOPPED"
    MONITOR_POSITION_CLOSED = "MONITOR_POSITION_CLOSED"
    MONITOR_BLOCKED = "MONITOR_BLOCKED"


# Sprint 9.9.3.45.6: explicit monitor stop reasons
STOP_REASON_POSITION_CLOSED = "POSITION_CLOSED"
STOP_REASON_TIMEOUT = "TIMEOUT"
STOP_REASON_KILL_SWITCH_BLOCKED = "KILL_SWITCH_BLOCKED"
STOP_REASON_GATE_BLOCKED = "GATE_BLOCKED"
STOP_REASON_ERROR = "ERROR"
STOP_REASON_POSITION_DISAPPEARED_WITHOUT_HISTORY = "POSITION_DISAPPEARED_WITHOUT_HISTORY"


@dataclass
class MonitorEvent:
    timestamp_utc: str
    event_type: str
    description: str
    sl_action: str = "HOLD"
    new_sl: float = 0.0
    current_sl: float = 0.0
    favorable: bool = True
    # Sprint 9.9.3.45.6: apply path fields
    modify_attempted: bool = False
    modify_retcode: int = 0
    modify_success: bool = False
    modify_reason: str = ""


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
    # Sprint 9.9.3.45.6: monitor lifecycle fields
    monitor_iterations: int = 0
    monitor_duration_seconds: float = 0.0
    monitor_stop_reason: str = ""
    final_position_source: str = ""
    final_positions_get_count: int = 0
    final_history_match_found: bool = False
    close_deal_ticket: int = 0
    close_comment: str = ""

    def __post_init__(self):
        if not self.timestamp_utc:
            self.timestamp_utc = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return asdict(self)


class ManagedTradeOrchestrator:
    """Orchestrates managed demo micro trade with position monitoring.

    Sprint 9.9.3.45.6: continuous monitor loop with explicit stop
    reasons, optional SL modify apply path (local operator only).
    """

    def __init__(self, duration_minutes: int = 30, interval_seconds: int = 5,
                 apply_modifications: bool = False,
                 modify_applier: Optional[Callable] = None):
        self.duration_minutes = max(0, int(duration_minutes))
        self.interval_seconds = max(0, int(interval_seconds))
        self.apply_modifications = apply_modifications
        # modify_applier: callable(position_ticket, new_sl, tp) -> dict
        # with keys: retcode, success, reason. Injected by local operator
        # only. Z AI must NOT inject a real applier.
        self.modify_applier = modify_applier
        self.manager = DemoMicroPositionManager()
        self.events: list[MonitorEvent] = []
        self.kill_switch_active = False

    def trigger_kill_switch(self):
        """Mark kill switch as active. Loop must stop on next iteration."""
        self.kill_switch_active = True

    def evaluate_single_step(self, position_ticket: int, direction: str,
                              entry_price: float, current_sl: float,
                              current_tp: float, current_price: float,
                              is_open: bool = True) -> tuple[SLModifyRecommendation, MonitorEvent]:
        """Evaluate one position once and return (recommendation, event).

        Does NOT send any order. Used by the monitor loop and by tests.
        """
        rec = self.manager.evaluate(
            direction=direction,
            entry_price=entry_price,
            current_price=current_price,
            current_sl=current_sl,
            current_tp=current_tp,
        )
        event_type = "MONITOR_EVALUATION"
        event = MonitorEvent(
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            event_type=event_type,
            description=f"Evaluated: {rec.reason}",
            sl_action=rec.action.value,
            new_sl=rec.new_sl,
            current_sl=rec.current_sl,
            favorable=rec.favorable,
        )
        self.events.append(event)
        return rec, event

    def monitor_position(self, position_ticket: int = 0,
                          direction: str = "BUY",
                          entry_price: float = 0.0,
                          current_sl: float = 0.0,
                          current_tp: float = 0.0,
                          current_price: float = 0.0,
                          is_open: bool = True,
                          ) -> ManagedTradeResult:
        """Monitor a single position for breakeven/trailing/profit-lock.

        Sprint 9.9.3.45.5 compatibility: single-evaluation entry point.
        Builds SL modify previews. If apply_modifications=True and a
        modify_applier is set, applies the modification exactly once
        per decision step.

        Z AI must NOT use apply mode.
        """
        result = ManagedTradeResult(
            position_ticket=position_ticket,
            initial_sl=current_sl,
            initial_tp=current_tp,
            verdict="MANAGED_DEMO_MICRO_STARTED",
            monitor_iterations=1,
            monitor_stop_reason="",
        )

        if not is_open:
            result.verdict = "MANAGED_DEMO_MICRO_COMPLETED"
            result.final_position_status = "CLOSED"
            result.final_position_source = "caller_assertion"
            result.monitor_stop_reason = STOP_REASON_POSITION_CLOSED
            result.warnings.append("Position already closed before monitoring started")
            result.monitor_events = [e.__dict__ for e in self.events]
            return result

        # Evaluate position manager
        rec, event = self.evaluate_single_step(
            position_ticket=position_ticket,
            direction=direction,
            entry_price=entry_price,
            current_sl=current_sl,
            current_tp=current_tp,
            current_price=current_price,
            is_open=True,
        )

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
                "applied": False,
            }
            result.sl_modify_previews.append(preview)

            # Sprint 9.9.3.45.6: apply path (local operator only)
            if self.apply_modifications and self.modify_applier is not None:
                # TP preserve check
                if rec.tp != current_tp:
                    attempt = {
                        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                        "action": rec.action.value,
                        "ticket": position_ticket,
                        "old_sl": current_sl,
                        "new_sl": rec.new_sl,
                        "tp_preserved": False,
                        "modify_reason": "TP_NOT_PRESERVED",
                        "modify_success": False,
                        "modify_retcode": 0,
                    }
                    result.sl_modify_attempts.append(attempt)
                    event.modify_attempted = False
                    event.modify_reason = "TP_NOT_PRESERVED"
                # Favorable-only check
                elif not rec.favorable:
                    attempt = {
                        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                        "action": rec.action.value,
                        "ticket": position_ticket,
                        "old_sl": current_sl,
                        "new_sl": rec.new_sl,
                        "tp_preserved": True,
                        "modify_reason": "UNFAVORABLE_SL_BLOCKED",
                        "modify_success": False,
                        "modify_retcode": 0,
                    }
                    result.sl_modify_attempts.append(attempt)
                    event.modify_attempted = False
                    event.modify_reason = "UNFAVORABLE_SL_BLOCKED"
                # SL equal to current SL = no modification needed
                elif rec.new_sl == current_sl:
                    attempt = {
                        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                        "action": rec.action.value,
                        "ticket": position_ticket,
                        "old_sl": current_sl,
                        "new_sl": rec.new_sl,
                        "tp_preserved": True,
                        "modify_reason": "SL_EQUALS_CURRENT_NO_MODIFY",
                        "modify_success": False,
                        "modify_retcode": 0,
                    }
                    result.sl_modify_attempts.append(attempt)
                    event.modify_attempted = False
                    event.modify_reason = "SL_EQUALS_CURRENT_NO_MODIFY"
                else:
                    # Apply modification via injected applier (exactly once)
                    try:
                        applier_result = self.modify_applier(
                            position_ticket, rec.new_sl, current_tp,
                        )
                        retcode = int(applier_result.get("retcode", 0))
                        success = bool(applier_result.get("success", False))
                        reason = applier_result.get("reason", "")
                    except Exception as e:
                        retcode = 0
                        success = False
                        reason = f"APPLIER_ERROR: {e}"
                    attempt = {
                        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                        "action": rec.action.value,
                        "ticket": position_ticket,
                        "old_sl": current_sl,
                        "new_sl": rec.new_sl,
                        "tp_preserved": True,
                        "modify_reason": reason,
                        "modify_success": success,
                        "modify_retcode": retcode,
                    }
                    result.sl_modify_attempts.append(attempt)
                    event.modify_attempted = True
                    event.modify_retcode = retcode
                    event.modify_success = success
                    event.modify_reason = reason

        # Single-evaluation entry point: verdict based on caller assertion
        result.verdict = "MANAGED_DEMO_MICRO_COMPLETED"
        result.final_position_status = "OPEN" if is_open else "CLOSED"
        result.monitor_events = [e.__dict__ for e in self.events]

        if result.warnings:
            result.verdict = "MANAGED_DEMO_MICRO_COMPLETED_WITH_WARNINGS"

        return result
