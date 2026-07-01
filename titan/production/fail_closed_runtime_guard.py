"""
TITAN XAU AI — Fail-Closed Runtime Guard (Production Resilience)
=================================================================

Companion to RuntimeHealthGuard. Hard-blocks any new trade whenever:
  - the runtime is in recovery mode, OR
  - an emergency stop has been triggered, OR
  - an explicit "block new trades" gate has been set.

Design:
  - Pure-Python, no MetaTrader5 import, no order_send.
  - ALWAYS fails closed. allow_new_trades() can only flip the gate
    OFF after explicit recovery — never automatically.
  - Auditable: every state change is journaled with a reason and timestamp.

NEVER imports MetaTrader5. NEVER calls mt5.order_send.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional, Callable


@dataclass
class BlockState:
    """Snapshot of the fail-closed gate state."""
    blocked: bool
    reason: str
    emergency_stop: bool
    recovery_mode: bool
    manual_block: bool
    last_change_at: float
    history: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "blocked": self.blocked,
            "reason": self.reason,
            "emergency_stop": self.emergency_stop,
            "recovery_mode": self.recovery_mode,
            "manual_block": self.manual_block,
            "last_change_at": self.last_change_at,
            "history": list(self.history),
        }


class FailClosedRuntimeGuard:
    """
    Hard-blocks new trades whenever the runtime is in recovery, an
    emergency stop has been triggered, or the manual block is set.

    The block is sticky: once an emergency_stop is triggered, it can
    only be cleared by an explicit, audited call to `reset_emergency_stop()`
    which requires both:
      1. recovery_mode == False (caller must clear recovery first)
      2. manual_block == False (caller must clear manual block first)

    Args:
        clock: injectable clock for tests.
        on_block_changed: optional callback when the block state changes.
    """

    def __init__(
        self,
        clock: Optional[Callable[[], float]] = None,
        on_block_changed: Optional[Callable[[BlockState], None]] = None,
    ) -> None:
        self._clock = clock or time.time
        self._on_block_changed = on_block_changed

        self._emergency_stop: bool = False
        self._recovery_mode: bool = False
        self._manual_block: bool = False
        self._reason: str = ""
        self._last_change_at: float = self._clock()
        self._history: list[dict] = []

    # ─── State mutators ────────────────────────────────────────────────

    def emergency_stop(self, reason: str = "operator triggered") -> None:
        """Trigger an emergency stop. Sticky until explicit reset."""
        prev = self.is_blocked()
        self._emergency_stop = True
        self._reason = f"EMERGENCY_STOP: {reason}"
        self._record_change("emergency_stop", reason)
        if prev != self.is_blocked() and self._on_block_changed:
            try:
                self._on_block_changed(self.state())
            except Exception:
                pass

    def block_new_trades(self, reason: str = "manual block") -> None:
        """Set a manual block on new trades."""
        prev = self.is_blocked()
        self._manual_block = True
        if not self._reason or "EMERGENCY" not in self._reason:
            self._reason = f"MANUAL_BLOCK: {reason}"
        self._record_change("manual_block", reason)
        if prev != self.is_blocked() and self._on_block_changed:
            try:
                self._on_block_changed(self.state())
            except Exception:
                pass

    def allow_new_trades(self, reason: str = "manual clear") -> bool:
        """
        Clear the manual block. Returns True if the gate is now open.
        Will NOT clear an emergency stop or recovery mode — those require
        their own explicit reset / health recovery.
        """
        if self._emergency_stop:
            self._record_change(
                "allow_blocked_by_emergency_stop",
                "cannot allow new trades while emergency stop is active",
            )
            return False
        if self._recovery_mode:
            self._record_change(
                "allow_blocked_by_recovery",
                "cannot allow new trades while runtime is in recovery mode",
            )
            return False
        prev = self.is_blocked()
        self._manual_block = False
        self._reason = ""
        self._record_change("manual_allow", reason)
        if prev != self.is_blocked() and self._on_block_changed:
            try:
                self._on_block_changed(self.state())
            except Exception:
                pass
        return not self.is_blocked()

    def set_recovery_mode(self, in_recovery: bool, reason: str = "") -> None:
        """Mirror the recovery state from RuntimeHealthGuard."""
        prev_blocked = self.is_blocked()
        self._recovery_mode = bool(in_recovery)
        if in_recovery:
            if not self._reason or "EMERGENCY" not in self._reason:
                self._reason = f"RECOVERY_MODE: {reason}"
        else:
            # Recovery cleared — but only clear reason if it was a recovery reason.
            if self._reason.startswith("RECOVERY_MODE"):
                self._reason = ""
        self._record_change(
            "recovery_mode_set",
            f"in_recovery={in_recovery}; reason={reason}",
        )
        if prev_blocked != self.is_blocked() and self._on_block_changed:
            try:
                self._on_block_changed(self.state())
            except Exception:
                pass

    def reset_emergency_stop(self, reason: str = "operator reset") -> bool:
        """
        Reset the emergency stop. Requires recovery_mode == False and
        manual_block == False. Returns True on success.
        """
        if self._recovery_mode:
            self._record_change(
                "emergency_reset_blocked_by_recovery",
                "cannot reset emergency stop while in recovery mode",
            )
            return False
        if self._manual_block:
            self._record_change(
                "emergency_reset_blocked_by_manual",
                "cannot reset emergency stop while manual block is active",
            )
            return False
        prev = self.is_blocked()
        self._emergency_stop = False
        self._reason = ""
        self._record_change("emergency_stop_reset", reason)
        if prev != self.is_blocked() and self._on_block_changed:
            try:
                self._on_block_changed(self.state())
            except Exception:
                pass
        return True

    # ─── Public accessors ──────────────────────────────────────────────

    def is_blocked(self) -> bool:
        """True if new trades are blocked for ANY reason."""
        return self._emergency_stop or self._recovery_mode or self._manual_block

    @property
    def emergency_stop_active(self) -> bool:
        return self._emergency_stop

    @property
    def recovery_mode_active(self) -> bool:
        return self._recovery_mode

    @property
    def manual_block_active(self) -> bool:
        return self._manual_block

    @property
    def reason(self) -> str:
        return self._reason

    @property
    def last_change_at(self) -> float:
        return self._last_change_at

    @property
    def history(self) -> list[dict]:
        return list(self._history)

    def state(self) -> BlockState:
        return BlockState(
            blocked=self.is_blocked(),
            reason=self._reason,
            emergency_stop=self._emergency_stop,
            recovery_mode=self._recovery_mode,
            manual_block=self._manual_block,
            last_change_at=self._last_change_at,
            history=list(self._history),
        )

    # ─── Internal ──────────────────────────────────────────────────────

    def _record_change(self, event: str, detail: str) -> None:
        now = self._clock()
        self._last_change_at = now
        self._history.append({
            "ts": now,
            "event": event,
            "detail": detail,
            "blocked_after": self.is_blocked(),
            "emergency_stop_after": self._emergency_stop,
            "recovery_mode_after": self._recovery_mode,
            "manual_block_after": self._manual_block,
        })


__all__ = ["FailClosedRuntimeGuard", "BlockState"]
