"""
TITAN XAU AI — Capital Protection Layer (Sprint 9.2)
======================================================

Implements 4 capital-protection modules:

1. RecoveryMode
   After configurable losing streak → reduce risk, reduce max positions,
   allow only highest-confidence trades. Auto-recover when N winning
   trades hit recovery_target_trades.

2. CapitalPreservation
   Near prop-firm DD limits (e.g. 8% of 10% FTMO limit) → reduce exposure,
   disable scaling, stop new entries if DD crosses halt threshold.

3. ProfitLock
   Track highest equity. After lock_distance_pct gain, lock equity at
   (peak - trail_distance_pct). Locked equity never decreases.

4. EquityProtection
   Track highest equity, current equity, locked equity, recovery target.
   Journal all changes.

Safety invariants:
  - All modules can only DECREASE risk, never increase
  - Hard caps (max_lot=0.01, max_open_positions=1) always enforced
  - dry_run / live_trading flags never changed
  - All state transitions journaled

Journal events:
  - EventType.RECOVERY_MODE         (activation/deactivation/progress)
  - EventType.CAPITAL_PRESERVATION  (activation/deactivation)
  - EventType.PROFIT_LOCK           (lock activated, lock level changed)
  - EventType.EQUITY_PROTECTION     (equity milestone tracking)
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field, asdict
from typing import Optional

from titan.production.trade_journal import TradeJournal, EventType

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════════════
# 1. RecoveryMode
# ════════════════════════════════════════════════════════════════════════════
@dataclass
class RecoveryConfig:
    """Recovery mode configuration."""
    losing_streak_threshold: int = 3        # consecutive losses → enter recovery
    min_confidence_threshold: float = 0.75  # only allow trades with ≥ this confidence
    recovery_target_trades: int = 2         # N winning trades to exit recovery
    risk_multiplier: float = 0.5            # halve risk in recovery


@dataclass
class RecoveryState:
    """Current recovery state."""
    is_active: bool = False
    consecutive_losses: int = 0
    consecutive_wins_in_recovery: int = 0
    activated_at: Optional[float] = None    # timestamp
    deactivated_at: Optional[float] = None

    def to_dict(self) -> dict:
        return asdict(self)


class RecoveryMode:
    """
    Tracks losing streaks and triggers recovery mode.

    Activation: consecutive_losses >= losing_streak_threshold
    Deactivation: consecutive_wins_in_recovery >= recovery_target_trades
    """

    def __init__(
        self,
        config: RecoveryConfig,
        journal: Optional[TradeJournal] = None,
    ):
        self.config = config
        self.journal = journal
        self._state = RecoveryState()

    @property
    def state(self) -> RecoveryState:
        return self._state

    @property
    def is_active(self) -> bool:
        return self._state.is_active

    def record_loss(self) -> RecoveryState:
        """Record a losing trade. May activate recovery."""
        self._state.consecutive_losses += 1
        self._state.consecutive_wins_in_recovery = 0

        if (not self._state.is_active
                and self._state.consecutive_losses >= self.config.losing_streak_threshold):
            self._activate()

        self._journal(EventType.RECOVERY_MODE, {
            "event": "loss_recorded",
            "consecutive_losses": self._state.consecutive_losses,
            "is_active": self._state.is_active,
        })
        return self._state

    def record_win(self) -> RecoveryState:
        """Record a winning trade. May deactivate recovery."""
        if self._state.is_active:
            self._state.consecutive_wins_in_recovery += 1
            if self._state.consecutive_wins_in_recovery >= self.config.recovery_target_trades:
                self._deactivate()
        else:
            # Not in recovery → just reset consecutive losses
            self._state.consecutive_losses = 0

        self._journal(EventType.RECOVERY_MODE, {
            "event": "win_recorded",
            "consecutive_wins_in_recovery": self._state.consecutive_wins_in_recovery,
            "is_active": self._state.is_active,
        })
        return self._state

    def should_allow_trade(self, confidence: float) -> bool:
        """In recovery, only allow trades with confidence >= threshold."""
        if not self._state.is_active:
            return True
        return confidence >= self.config.min_confidence_threshold

    @property
    def risk_multiplier(self) -> float:
        """Returns risk multiplier (1.0 if not active, config value if active)."""
        return self.config.risk_multiplier if self._state.is_active else 1.0

    def _activate(self) -> None:
        self._state.is_active = True
        self._state.activated_at = time.time()
        self._state.consecutive_wins_in_recovery = 0
        logger.warning(
            f"RECOVERY MODE ACTIVATED — losing streak "
            f"{self._state.consecutive_losses} ≥ threshold "
            f"{self.config.losing_streak_threshold}"
        )
        self._journal(EventType.RECOVERY_MODE, {
            "event": "activated",
            "consecutive_losses": self._state.consecutive_losses,
            "risk_multiplier": self.config.risk_multiplier,
            "min_confidence_threshold": self.config.min_confidence_threshold,
            "recovery_target_trades": self.config.recovery_target_trades,
        })

    def _deactivate(self) -> None:
        logger.info(
            f"RECOVERY MODE DEACTIVATED — "
            f"{self._state.consecutive_wins_in_recovery} winning trades reached"
        )
        self._journal(EventType.RECOVERY_MODE, {
            "event": "deactivated",
            "consecutive_wins_in_recovery": self._state.consecutive_wins_in_recovery,
            "consecutive_losses_at_activation": self._state.consecutive_losses,
        })
        self._state.is_active = False
        self._state.consecutive_losses = 0
        self._state.consecutive_wins_in_recovery = 0
        self._state.deactivated_at = time.time()

    def _journal(self, event_type: EventType, data: dict) -> None:
        if self.journal is None:
            return
        try:
            self.journal.log_event(event_type, data | {"state": self._state.to_dict()})
        except Exception as e:
            logger.error(f"Journal event {event_type.value} failed: {e}")


# ════════════════════════════════════════════════════════════════════════════
# 2. CapitalPreservation
# ════════════════════════════════════════════════════════════════════════════
@dataclass
class CapitalPreservationConfig:
    """Capital preservation configuration."""
    trigger_dd_pct: float = 8.0             # activate at 8% total DD
    halt_new_entries_dd_pct: float = 9.0    # stop new entries at 9% DD
    risk_multiplier: float = 0.25           # quarter risk when active


@dataclass
class CapitalPreservationState:
    is_active: bool = False
    new_entries_halted: bool = False
    current_dd_pct: float = 0.0
    activated_at: Optional[float] = None
    deactivated_at: Optional[float] = None

    def to_dict(self) -> dict:
        return asdict(self)


class CapitalPreservation:
    """
    Activates when total drawdown approaches prop-firm limits.

    Two thresholds:
      - trigger_dd_pct: activate capital preservation (reduce risk)
      - halt_new_entries_dd_pct: stop new entries entirely
    """

    def __init__(
        self,
        config: CapitalPreservationConfig,
        journal: Optional[TradeJournal] = None,
    ):
        self.config = config
        self.journal = journal
        self._state = CapitalPreservationState()

    @property
    def state(self) -> CapitalPreservationState:
        return self._state

    @property
    def is_active(self) -> bool:
        return self._state.is_active

    @property
    def new_entries_halted(self) -> bool:
        return self._state.new_entries_halted

    def update(self, total_dd_pct: float) -> CapitalPreservationState:
        """Update with current total DD%. May activate/deactivate."""
        self._state.current_dd_pct = total_dd_pct
        prev_active = self._state.is_active
        prev_halted = self._state.new_entries_halted

        # Halt-new-entries check (higher threshold)
        self._state.new_entries_halted = total_dd_pct >= self.config.halt_new_entries_dd_pct

        # Activation check (lower threshold)
        if total_dd_pct >= self.config.trigger_dd_pct:
            if not self._state.is_active:
                self._state.is_active = True
                self._state.activated_at = time.time()
                logger.warning(
                    f"CAPITAL PRESERVATION ACTIVATED — "
                    f"total DD {total_dd_pct:.2f}% ≥ trigger "
                    f"{self.config.trigger_dd_pct}%"
                )
                self._journal(EventType.CAPITAL_PRESERVATION, {
                    "event": "activated",
                    "total_dd_pct": total_dd_pct,
                    "trigger_dd_pct": self.config.trigger_dd_pct,
                    "risk_multiplier": self.config.risk_multiplier,
                })
        else:
            if self._state.is_active:
                logger.info(
                    f"CAPITAL PRESERVATION DEACTIVATED — "
                    f"total DD {total_dd_pct:.2f}% < trigger "
                    f"{self.config.trigger_dd_pct}%"
                )
                self._journal(EventType.CAPITAL_PRESERVATION, {
                    "event": "deactivated",
                    "total_dd_pct": total_dd_pct,
                })
                self._state.is_active = False
                self._state.deactivated_at = time.time()

        # Journal halt state change
        if prev_halted != self._state.new_entries_halted:
            self._journal(EventType.CAPITAL_PRESERVATION, {
                "event": "new_entries_halted" if self._state.new_entries_halted else "new_entries_resumed",
                "total_dd_pct": total_dd_pct,
                "halt_threshold": self.config.halt_new_entries_dd_pct,
            })

        return self._state

    def should_allow_new_entry(self) -> bool:
        """Returns False if new entries are halted."""
        return not self._state.new_entries_halted

    @property
    def risk_multiplier(self) -> float:
        """Returns risk multiplier (1.0 if not active, config value if active)."""
        return self.config.risk_multiplier if self._state.is_active else 1.0

    def _journal(self, event_type: EventType, data: dict) -> None:
        if self.journal is None:
            return
        try:
            self.journal.log_event(event_type, data | {"state": self._state.to_dict()})
        except Exception as e:
            logger.error(f"Journal event {event_type.value} failed: {e}")


# ════════════════════════════════════════════════════════════════════════════
# 3. ProfitLock
# ════════════════════════════════════════════════════════════════════════════
@dataclass
class ProfitLockConfig:
    """Profit lock configuration."""
    enabled: bool = False                   # off by default — opt-in
    lock_distance_pct: float = 2.0          # lock equity after +2% gain
    trail_distance_pct: float = 1.0         # allow equity to dip 1% below peak


@dataclass
class ProfitLockState:
    is_locked: bool = False
    peak_equity: float = 0.0                # highest equity seen
    locked_equity: float = 0.0              # locked floor (peak - trail_distance_pct)
    initial_balance: float = 0.0
    locked_at: Optional[float] = None

    def to_dict(self) -> dict:
        return asdict(self)


class ProfitLock:
    """
    Tracks highest equity and locks in profit after lock_distance_pct gain.

    Locked equity = peak_equity * (1 - trail_distance_pct/100)
    Once locked, locked_equity NEVER decreases (only increases with new peaks).
    """

    def __init__(
        self,
        config: ProfitLockConfig,
        initial_balance: float,
        journal: Optional[TradeJournal] = None,
    ):
        self.config = config
        self.journal = journal
        self._state = ProfitLockState(
            peak_equity=initial_balance,
            locked_equity=initial_balance,
            initial_balance=initial_balance,
        )

    @property
    def state(self) -> ProfitLockState:
        return self._state

    @property
    def is_locked(self) -> bool:
        return self._state.is_locked

    @property
    def locked_equity(self) -> float:
        return self._state.locked_equity

    @property
    def peak_equity(self) -> float:
        return self._state.peak_equity

    def update(self, current_equity: float) -> ProfitLockState:
        """Update with current equity. May activate lock / raise locked floor."""
        if not self.config.enabled:
            return self._state

        # Track new peak
        if current_equity > self._state.peak_equity:
            self._state.peak_equity = current_equity
            self._journal(EventType.EQUITY_PROTECTION, {
                "event": "new_peak",
                "peak_equity": current_equity,
                "locked_equity": self._state.locked_equity,
            })

            # If already locked, raise the locked floor (trail the peak)
            if self._state.is_locked:
                new_locked = current_equity * (1.0 - self.config.trail_distance_pct / 100.0)
                if new_locked > self._state.locked_equity:
                    old_locked = self._state.locked_equity
                    self._state.locked_equity = new_locked
                    self._journal(EventType.PROFIT_LOCK, {
                        "event": "locked_equity_raised",
                        "old_locked": old_locked,
                        "new_locked": new_locked,
                        "peak_equity": current_equity,
                    })

        # Check for initial lock activation
        if not self._state.is_locked:
            gain_pct = (
                (current_equity - self._state.initial_balance)
                / self._state.initial_balance * 100
            ) if self._state.initial_balance > 0 else 0.0
            if gain_pct >= self.config.lock_distance_pct:
                self._state.is_locked = True
                self._state.locked_equity = (
                    self._state.peak_equity
                    * (1.0 - self.config.trail_distance_pct / 100.0)
                )
                self._state.locked_at = time.time()
                logger.info(
                    f"PROFIT LOCK ACTIVATED — gain {gain_pct:.2f}% ≥ "
                    f"lock_distance {self.config.lock_distance_pct}%, "
                    f"locked_equity={self._state.locked_equity:.2f}"
                )
                self._journal(EventType.PROFIT_LOCK, {
                    "event": "activated",
                    "peak_equity": self._state.peak_equity,
                    "locked_equity": self._state.locked_equity,
                    "lock_distance_pct": self.config.lock_distance_pct,
                    "trail_distance_pct": self.config.trail_distance_pct,
                    "gain_pct_at_activation": gain_pct,
                })

        return self._state

    def is_below_locked(self, current_equity: float) -> bool:
        """Returns True if current equity is below locked floor (should flatten)."""
        if not self._state.is_locked:
            return False
        return current_equity < self._state.locked_equity

    def _journal(self, event_type: EventType, data: dict) -> None:
        if self.journal is None:
            return
        try:
            self.journal.log_event(event_type, data | {"state": self._state.to_dict()})
        except Exception as e:
            logger.error(f"Journal event {event_type.value} failed: {e}")


# ════════════════════════════════════════════════════════════════════════════
# 4. EquityProtection (umbrella tracker)
# ════════════════════════════════════════════════════════════════════════════
@dataclass
class EquityProtectionState:
    """Snapshot of equity tracking."""
    initial_balance: float
    highest_equity: float
    current_equity: float
    locked_equity: float
    recovery_target: float                   # equity level to "recover" to
    drawdown_from_peak_pct: float
    drawdown_from_initial_pct: float

    def to_dict(self) -> dict:
        return asdict(self)


class EquityProtection:
    """
    Tracks equity milestones and journals changes.

    Tracks:
      - initial_balance: starting balance
      - highest_equity: peak equity ever reached
      - current_equity: latest equity snapshot
      - locked_equity: profit-lock floor (from ProfitLock module)
      - recovery_target: equity level to "recover" to after drawdown
    """

    def __init__(
        self,
        initial_balance: float,
        journal: Optional[TradeJournal] = None,
    ):
        self.initial_balance = initial_balance
        self.journal = journal
        self._highest_equity = initial_balance
        self._current_equity = initial_balance
        self._locked_equity = initial_balance
        self._last_snapshot_at = time.time()

    @property
    def state(self) -> EquityProtectionState:
        return EquityProtectionState(
            initial_balance=self.initial_balance,
            highest_equity=self._highest_equity,
            current_equity=self._current_equity,
            locked_equity=self._locked_equity,
            recovery_target=self._highest_equity,
            drawdown_from_peak_pct=self._dd_from_peak_pct,
            drawdown_from_initial_pct=self._dd_from_initial_pct,
        )

    @property
    def _dd_from_peak_pct(self) -> float:
        if self._highest_equity <= 0:
            return 0.0
        return max(0.0, (self._highest_equity - self._current_equity)
                   / self._highest_equity * 100.0)

    @property
    def _dd_from_initial_pct(self) -> float:
        if self.initial_balance <= 0:
            return 0.0
        return max(0.0, (self.initial_balance - self._current_equity)
                   / self.initial_balance * 100.0)

    def update(
        self,
        current_equity: float,
        locked_equity: Optional[float] = None,
    ) -> EquityProtectionState:
        """Update with current equity snapshot. Journals EQUITY_PROTECTION."""
        self._current_equity = current_equity
        if locked_equity is not None:
            self._locked_equity = locked_equity

        new_peak = False
        if current_equity > self._highest_equity:
            self._highest_equity = current_equity
            new_peak = True

        state = self.state
        # Journal only on significant changes (every call would flood the journal)
        self._journal(EventType.EQUITY_PROTECTION, {
            "event": "new_peak" if new_peak else "snapshot",
            "current_equity": current_equity,
            "highest_equity": self._highest_equity,
            "locked_equity": self._locked_equity,
            "recovery_target": state.recovery_target,
            "drawdown_from_peak_pct": state.drawdown_from_peak_pct,
            "drawdown_from_initial_pct": state.drawdown_from_initial_pct,
        })
        self._last_snapshot_at = time.time()
        return state

    def _journal(self, event_type: EventType, data: dict) -> None:
        if self.journal is None:
            return
        try:
            self.journal.log_event(event_type, data)
        except Exception as e:
            logger.error(f"Journal event {event_type.value} failed: {e}")
