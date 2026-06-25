"""
TITAN XAU AI — Execution Self-Protection (Sprint 9.5)
=======================================================

Detects execution anomalies and takes automatic protective action:
  - Abnormal spread
  - Broker manipulation (sudden rule changes)
  - Execution degradation
  - Latency spikes
  - Connection instability
  - Repeated requotes
  - Repeated rejected orders

Actions (escalating):
  1. EXECUTION_WARNING         (journal only)
  2. EXECUTION_DEGRADED        (reduce risk multiplier)
  3. BROKER_UNSAFE             (halt new entries)
  4. Trigger Kill Switch       (flatten all, halt system)

Journals every action. Never increases risk.
"""
from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field, asdict
from typing import Optional

from titan.production.trade_journal import TradeJournal, EventType

logger = logging.getLogger(__name__)


@dataclass
class SelfProtectionConfig:
    """Self-protection thresholds."""
    max_spread_spike_usd: float = 3.0       # spread > $3 → EXECUTION_WARNING
    max_latency_ms: float = 1000.0          # latency > 1000ms → EXECUTION_DEGRADED
    max_requote_rate: float = 0.10          # >10% requotes → EXECUTION_DEGRADED
    max_rejection_rate: float = 0.10        # >10% rejections → BROKER_UNSAFE
    pause_entries_on_unsafe: bool = True
    consecutive_anomaly_threshold: int = 3  # N consecutive anomalies → escalate


@dataclass
class ProtectionState:
    """Current self-protection state."""
    warning_active: bool = False
    degraded_active: bool = False
    unsafe_active: bool = False
    entries_paused: bool = False
    consecutive_anomalies: int = 0
    last_warning_at: Optional[float] = None
    last_degraded_at: Optional[float] = None
    last_unsafe_at: Optional[float] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ProtectionAction:
    """Result of a protection evaluation."""
    action: str                          # "none" | "warning" | "degraded" | "unsafe" | "kill_switch"
    reason: str
    risk_multiplier: float               # 1.0 | 0.5 | 0.25 | 0.0
    pause_entries: bool
    trigger_kill_switch: bool
    state: ProtectionState

    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "reason": self.reason,
            "risk_multiplier": self.risk_multiplier,
            "pause_entries": self.pause_entries,
            "trigger_kill_switch": self.trigger_kill_switch,
            "state": self.state.to_dict(),
        }


class ExecutionSelfProtection:
    """
    Monitors execution metrics and takes protective action.

    Escalation ladder:
      none → warning → degraded → unsafe → kill_switch

    Each escalation reduces risk_multiplier further.
    De-escalation requires N consecutive clean evaluations.
    """

    def __init__(
        self,
        config: SelfProtectionConfig,
        journal: Optional[TradeJournal] = None,
    ):
        self.config = config
        self.journal = journal
        self._state = ProtectionState()
        self._clean_streak: int = 0
        self._recent_actions: deque = deque(maxlen=100)

    @property
    def state(self) -> ProtectionState:
        return self._state

    @property
    def entries_paused(self) -> bool:
        return self._state.entries_paused

    @property
    def risk_multiplier(self) -> float:
        """Current risk multiplier based on protection level."""
        if self._state.unsafe_active:
            return 0.0
        if self._state.degraded_active:
            return 0.25
        if self._state.warning_active:
            return 0.5
        return 1.0

    def evaluate(
        self,
        spread_usd: float = 0.0,
        latency_ms: float = 0.0,
        requote_rate: float = 0.0,
        rejection_rate: float = 0.0,
        connection_lost: bool = False,
    ) -> ProtectionAction:
        """
        Evaluate current execution metrics and return protective action.

        Args:
            spread_usd: current spread in USD
            latency_ms: current execution latency in ms
            requote_rate: requote rate (0-1)
            rejection_rate: order rejection rate (0-1)
            connection_lost: True if broker connection lost
        """
        anomalies = []

        # Check each anomaly
        if connection_lost:
            anomalies.append("connection_lost")
        if spread_usd > self.config.max_spread_spike_usd:
            anomalies.append(f"spread_spike ({spread_usd:.2f} > {self.config.max_spread_spike_usd})")
        if latency_ms > self.config.max_latency_ms:
            anomalies.append(f"latency_spike ({latency_ms:.0f}ms > {self.config.max_latency_ms}ms)")
        if requote_rate > self.config.max_requote_rate:
            anomalies.append(f"high_requotes ({requote_rate:.2%} > {self.config.max_requote_rate:.2%})")
        if rejection_rate > self.config.max_rejection_rate:
            anomalies.append(f"high_rejections ({rejection_rate:.2%} > {self.config.max_rejection_rate:.2%})")

        if anomalies:
            self._state.consecutive_anomalies += 1
            self._clean_streak = 0
        else:
            self._state.consecutive_anomalies = 0
            self._clean_streak += 1

        # Determine action based on anomalies + escalation logic
        action = self._determine_action(anomalies)

        # Apply state changes
        self._apply_action(action, anomalies)

        # Build result
        result = ProtectionAction(
            action=action,
            reason="; ".join(anomalies) if anomalies else "clean",
            risk_multiplier=self.risk_multiplier,
            pause_entries=self._state.entries_paused,
            trigger_kill_switch=(action == "kill_switch"),
            state=self._state,
        )
        self._recent_actions.append(result)

        # Journal
        self._journal_action(action, result)

        return result

    # ─── Internal ─────────────────────────────────────────────────────────

    def _determine_action(self, anomalies: list[str]) -> str:
        """Determine action from anomalies + current state."""
        if not anomalies:
            # De-escalation: need 5 clean evaluations to drop one level
            if self._clean_streak >= 5:
                if self._state.unsafe_active:
                    return "degraded"  # unsafe → degraded
                if self._state.degraded_active:
                    return "warning"   # degraded → warning
                if self._state.warning_active:
                    return "none"      # warning → clear
            return "none" if not (self._state.warning_active or self._state.degraded_active or self._state.unsafe_active) else "maintain"

        # Anomalies detected — escalate
        # Connection loss or rejection rate > threshold → unsafe immediately
        if "connection_lost" in anomalies:
            return "kill_switch"

        rejection_anomalies = [a for a in anomalies if "high_rejections" in a]
        if rejection_anomalies:
            return "unsafe"

        # Latency spike or high requotes → degraded
        if any("latency_spike" in a for a in anomalies):
            return "degraded"
        if any("high_requotes" in a for a in anomalies):
            return "degraded"

        # Spread spike → warning (or escalate if already warning)
        if any("spread_spike" in a for a in anomalies):
            if self._state.consecutive_anomalies >= self.config.consecutive_anomaly_threshold:
                return "degraded"
            return "warning"

        return "warning"

    def _apply_action(self, action: str, anomalies: list[str]) -> None:
        """Apply action to state."""
        now = time.time()

        if action == "none":
            # Clear all
            self._state.warning_active = False
            self._state.degraded_active = False
            self._state.unsafe_active = False
            self._state.entries_paused = False

        elif action == "maintain":
            # Keep current state — no change
            pass

        elif action == "warning":
            self._state.warning_active = True
            self._state.last_warning_at = now
            self._state.entries_paused = False

        elif action == "degraded":
            self._state.warning_active = True
            self._state.degraded_active = True
            self._state.last_degraded_at = now
            self._state.entries_paused = False

        elif action == "unsafe":
            self._state.warning_active = True
            self._state.degraded_active = True
            self._state.unsafe_active = True
            self._state.last_unsafe_at = now
            self._state.entries_paused = self.config.pause_entries_on_unsafe

        elif action == "kill_switch":
            self._state.warning_active = True
            self._state.degraded_active = True
            self._state.unsafe_active = True
            self._state.entries_paused = True

    def _journal_action(self, action: str, result: ProtectionAction) -> None:
        if self.journal is None:
            return

        try:
            if action == "warning":
                self.journal.log_event(EventType.EXECUTION_WARNING, result.to_dict())
            elif action == "degraded":
                self.journal.log_event(EventType.EXECUTION_DEGRADED, result.to_dict())
            elif action == "unsafe":
                self.journal.log_event(EventType.BROKER_UNSAFE, result.to_dict())
            elif action == "kill_switch":
                self.journal.log_event(EventType.BROKER_UNSAFE, result.to_dict() | {
                    "kill_switch_triggered": True
                })
            elif action == "none" and self._clean_streak == 5:
                # Recovery event — we just cleared
                self.journal.log_event(EventType.EXECUTION_RECOVERED, {
                    "clean_streak": self._clean_streak,
                    "previous_state": "warning_or_degraded",
                })
        except Exception as e:
            logger.error(f"Journal action failed: {e}")

    @property
    def recent_actions(self) -> list[ProtectionAction]:
        return list(self._recent_actions)
