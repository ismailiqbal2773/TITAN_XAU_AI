"""
TITAN XAU AI — Kill-Switch FSM (Production Sprint 4)

5-state finite state machine governing trade safety:

  NORMAL → CAUTION → HALT_NEW_TRADES → FLATTEN_ONLY → EMERGENCY_STOP

State semantics:
  NORMAL              : full trading allowed
  CAUTION             : trading allowed but reduced size (signal to operator)
  HALT_NEW_TRADES     : no new entries; existing positions managed normally
  FLATTEN_ONLY        : no new entries; exit manager requests flatten
  EMERGENCY_STOP      : kill-switch armed; flatten ALL positions immediately

Transitions are one-way DOWN (escalation) until manual reset.
Reset returns to NORMAL (operator action required).

Fail-safe: if the FSM itself errors, it transitions to EMERGENCY_STOP.

Usage:
    fsm = KillSwitchFSM()
    fsm.update(KillSwitchInput(daily_loss_pct=2.5, max_dd_pct=4.0, ...))
    state = fsm.state
    if state in (KillState.HALT_NEW_TRADES, KillState.FLATTEN_ONLY, KillState.EMERGENCY_STOP):
        # block new trades
        ...
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Callable

logger = logging.getLogger(__name__)


class KillState(str, Enum):
    NORMAL = "NORMAL"
    CAUTION = "CAUTION"
    HALT_NEW_TRADES = "HALT_NEW_TRADES"
    FLATTEN_ONLY = "FLATTEN_ONLY"
    EMERGENCY_STOP = "EMERGENCY_STOP"


# Ordered by severity (index = severity level)
_STATE_ORDER = [
    KillState.NORMAL,
    KillState.CAUTION,
    KillState.HALT_NEW_TRADES,
    KillState.FLATTEN_ONLY,
    KillState.EMERGENCY_STOP,
]


@dataclass
class KillSwitchConfig:
    """Kill-switch trigger thresholds."""
    # Loss-based triggers
    max_daily_loss_pct: float = 3.0           # daily loss % → HALT_NEW_TRADES
    max_drawdown_pct: float = 5.0             # overall DD % → FLATTEN_ONLY
    max_consecutive_losses: int = 5           # → HALT_NEW_TRADES
    emergency_daily_loss_pct: float = 5.0     # → EMERGENCY_STOP
    emergency_drawdown_pct: float = 8.0       # → EMERGENCY_STOP

    # Execution-based triggers
    max_latency_ms: float = 500.0             # p99 latency → CAUTION
    emergency_latency_ms: float = 1000.0      # → EMERGENCY_STOP
    max_spread_usd: float = 1.0               # → CAUTION
    emergency_spread_usd: float = 2.0         # → HALT_NEW_TRADES

    # News / drift triggers
    news_halt_active: bool = False            # external flag → HALT_NEW_TRADES
    drift_breach: bool = False                # external flag → CAUTION
    drift_emergency: bool = False             # external flag → EMERGENCY_STOP

    # Calibration triggers
    max_brier: float = 0.25                   # → CAUTION
    emergency_brier: float = 0.30             # → HALT_NEW_TRADES
    max_ece: float = 0.10                     # → CAUTION
    emergency_ece: float = 0.15               # → HALT_NEW_TRADES


@dataclass
class KillSwitchInput:
    """Inputs to the FSM update cycle."""
    daily_loss_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    consecutive_losses: int = 0
    latency_p99_ms: float = 0.0
    spread_usd: float = 0.0
    news_halt_active: bool = False
    drift_breach: bool = False
    drift_emergency: bool = False
    brier_score: float = 0.0
    ece: float = 0.0


@dataclass
class KillSwitchTransition:
    """Record of a state transition."""
    timestamp: float
    from_state: KillState
    to_state: KillState
    trigger: str
    input_snapshot: dict


class KillSwitchFSM:
    """
    5-state kill-switch finite state machine.

    Safety properties:
      1. Transitions only escalate (NORMAL → CAUTION → ... → EMERGENCY_STOP)
      2. De-escalation requires explicit reset() (manual operator action)
      3. If update() raises an exception, FSM goes to EMERGENCY_STOP (fail-safe)
      4. Every transition is journaled via optional callback
    """

    def __init__(
        self,
        config: Optional[KillSwitchConfig] = None,
        journal_callback: Optional[Callable[[KillSwitchTransition], None]] = None,
    ):
        self.config = config or KillSwitchConfig()
        self._state = KillState.NORMAL
        self._last_input: Optional[KillSwitchInput] = None
        self._last_transition: Optional[KillSwitchTransition] = None
        self._transition_history: list[KillSwitchTransition] = []
        self._journal_callback = journal_callback
        self._armed_time: Optional[float] = None  # when EMERGENCY_STOP was set
        logger.info(f"KillSwitchFSM initialized at {self._state.value}")

    # ─── Public API ─────────────────────────────────────────────────────

    def update(self, inp: KillSwitchInput) -> KillState:
        """
        Evaluate inputs and transition state if needed.
        Returns the new (or unchanged) state.
        """
        try:
            self._last_input = inp
            new_state = self._evaluate(inp)
            if new_state != self._state:
                self._transition(new_state, trigger=self._last_trigger, inp=inp)
            return self._state
        except Exception as e:
            # Fail-safe: any error → EMERGENCY_STOP
            logger.error(f"KillSwitchFSM error (fail-safe triggered): {e}")
            if self._state != KillState.EMERGENCY_STOP:
                self._transition(KillState.EMERGENCY_STOP,
                                 trigger=f"fsm_error: {e}", inp=inp)
            return self._state

    def reset(self) -> None:
        """Manual reset to NORMAL. Operator action required."""
        old = self._state
        self._state = KillState.NORMAL
        self._armed_time = None
        self._last_transition = KillSwitchTransition(
            timestamp=time.time(),
            from_state=old,
            to_state=KillState.NORMAL,
            trigger="manual_reset",
            input_snapshot={},
        )
        self._transition_history.append(self._last_transition)
        logger.warning(f"KillSwitchFSM RESET to NORMAL (was {old.value})")
        if self._journal_callback:
            self._journal_callback(self._last_transition)

    @property
    def state(self) -> KillState:
        return self._state

    @property
    def is_normal(self) -> bool:
        return self._state == KillState.NORMAL

    @property
    def allows_new_trades(self) -> bool:
        """True iff new entries are permitted."""
        return self._state in (KillState.NORMAL, KillState.CAUTION)

    @property
    def requires_flatten(self) -> bool:
        """True iff existing positions should be flattened."""
        return self._state in (KillState.FLATTEN_ONLY, KillState.EMERGENCY_STOP)

    @property
    def is_emergency(self) -> bool:
        return self._state == KillState.EMERGENCY_STOP

    @property
    def armed_time(self) -> Optional[float]:
        return self._armed_time

    @property
    def last_transition(self) -> Optional[KillSwitchTransition]:
        return self._last_transition

    @property
    def transition_count(self) -> int:
        return len(self._transition_history)

    # ─── Internal ───────────────────────────────────────────────────────

    _last_trigger: str = ""

    def _evaluate(self, inp: KillSwitchInput) -> KillState:
        """Determine target state from inputs. Returns highest-priority state."""
        cfg = self.config
        triggers = []

        # ── EMERGENCY_STOP triggers (highest priority) ──
        if inp.daily_loss_pct >= cfg.emergency_daily_loss_pct:
            triggers.append((KillState.EMERGENCY_STOP,
                             f"emergency_daily_loss ({inp.daily_loss_pct:.2f}%)"))
        if inp.max_drawdown_pct >= cfg.emergency_drawdown_pct:
            triggers.append((KillState.EMERGENCY_STOP,
                             f"emergency_drawdown ({inp.max_drawdown_pct:.2f}%)"))
        if inp.latency_p99_ms >= cfg.emergency_latency_ms:
            triggers.append((KillState.EMERGENCY_STOP,
                             f"emergency_latency ({inp.latency_p99_ms:.0f}ms)"))
        if inp.drift_emergency:
            triggers.append((KillState.EMERGENCY_STOP, "drift_emergency"))

        # ── FLATTEN_ONLY triggers ──
        if inp.max_drawdown_pct >= cfg.max_drawdown_pct:
            triggers.append((KillState.FLATTEN_ONLY,
                             f"max_drawdown ({inp.max_drawdown_pct:.2f}%)"))

        # ── HALT_NEW_TRADES triggers ──
        if inp.daily_loss_pct >= cfg.max_daily_loss_pct:
            triggers.append((KillState.HALT_NEW_TRADES,
                             f"max_daily_loss ({inp.daily_loss_pct:.2f}%)"))
        if inp.consecutive_losses >= cfg.max_consecutive_losses:
            triggers.append((KillState.HALT_NEW_TRADES,
                             f"consecutive_losses ({inp.consecutive_losses})"))
        if inp.spread_usd >= cfg.emergency_spread_usd:
            triggers.append((KillState.HALT_NEW_TRADES,
                             f"emergency_spread ({inp.spread_usd:.2f})"))
        if inp.news_halt_active:
            triggers.append((KillState.HALT_NEW_TRADES, "news_halt_active"))
        if inp.brier_score >= cfg.emergency_brier:
            triggers.append((KillState.HALT_NEW_TRADES,
                             f"emergency_brier ({inp.brier_score:.3f})"))
        if inp.ece >= cfg.emergency_ece:
            triggers.append((KillState.HALT_NEW_TRADES,
                             f"emergency_ece ({inp.ece:.3f})"))

        # ── CAUTION triggers ──
        if inp.latency_p99_ms >= cfg.max_latency_ms:
            triggers.append((KillState.CAUTION,
                             f"max_latency ({inp.latency_p99_ms:.0f}ms)"))
        if inp.spread_usd >= cfg.max_spread_usd:
            triggers.append((KillState.CAUTION,
                             f"max_spread ({inp.spread_usd:.2f})"))
        if inp.drift_breach:
            triggers.append((KillState.CAUTION, "drift_breach"))
        if inp.brier_score >= cfg.max_brier:
            triggers.append((KillState.CAUTION,
                             f"max_brier ({inp.brier_score:.3f})"))
        if inp.ece >= cfg.max_ece:
            triggers.append((KillState.CAUTION,
                             f"max_ece ({inp.ece:.3f})"))

        if not triggers:
            return self._state  # no escalation

        # Pick the highest-severity trigger
        triggers.sort(key=lambda t: _STATE_ORDER.index(t[0]), reverse=True)
        target_state, trigger_reason = triggers[0]
        self._last_trigger = trigger_reason
        return target_state

    def _transition(self, new_state: KillState, trigger: str, inp: KillSwitchInput) -> None:
        """Execute state transition (one-way escalation only)."""
        old_idx = _STATE_ORDER.index(self._state)
        new_idx = _STATE_ORDER.index(new_state)
        if new_idx <= old_idx:
            # Cannot de-escalate without reset()
            return
        old_state = self._state
        self._state = new_state
        if new_state == KillState.EMERGENCY_STOP:
            self._armed_time = time.time()

        transition = KillSwitchTransition(
            timestamp=time.time(),
            from_state=old_state,
            to_state=new_state,
            trigger=trigger,
            input_snapshot={
                "daily_loss_pct": inp.daily_loss_pct,
                "max_drawdown_pct": inp.max_drawdown_pct,
                "consecutive_losses": inp.consecutive_losses,
                "latency_p99_ms": inp.latency_p99_ms,
                "spread_usd": inp.spread_usd,
                "news_halt_active": inp.news_halt_active,
                "drift_breach": inp.drift_breach,
                "drift_emergency": inp.drift_emergency,
                "brier_score": inp.brier_score,
                "ece": inp.ece,
            },
        )
        self._last_transition = transition
        self._transition_history.append(transition)
        logger.warning(
            f"KILL-SWITCH: {old_state.value} → {new_state.value} "
            f"(trigger: {trigger})"
        )
        if self._journal_callback:
            try:
                self._journal_callback(transition)
            except Exception as e:
                logger.error(f"Journal callback failed: {e}")


if __name__ == "__main__":
    # Smoke test
    fsm = KillSwitchFSM()
    print(f"Initial state: {fsm.state.value}")

    # Trigger CAUTION via latency
    fsm.update(KillSwitchInput(latency_p99_ms=550))
    print(f"After latency 550ms: {fsm.state.value}")

    # Trigger HALT_NEW_TRADES via daily loss
    fsm.update(KillSwitchInput(daily_loss_pct=3.5))
    print(f"After daily loss 3.5%: {fsm.state.value}")

    # Trigger EMERGENCY_STOP via drawdown
    fsm.update(KillSwitchInput(max_drawdown_pct=8.5))
    print(f"After DD 8.5%: {fsm.state.value}")
    print(f"requires_flatten: {fsm.requires_flatten}")
    print(f"is_emergency: {fsm.is_emergency}")

    # Reset
    fsm.reset()
    print(f"After reset: {fsm.state.value}")
    print(f"\nTransitions: {fsm.transition_count}")
