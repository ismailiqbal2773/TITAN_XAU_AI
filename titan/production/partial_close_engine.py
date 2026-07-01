"""
TITAN XAU AI — Partial Close Engine (Sprint 9.9.3.45.8.6)
============================================================

Disabled-by-default partial close engine that, when explicitly opted-in,
computes a safe partial-close plan for an open position.

Responsibilities:
  1. ``can_partial_close()`` — verify broker + position + lot preconditions.
  2. ``calculate_partial_close()`` — compute the partial close lot,
     realized profit, and remaining position state.
  3. ``validate_remaining_lot()`` — verify the remaining lot after a
     partial close is non-dust and >= broker min_lot.
  4. Preserve / update SL/TP safely: the engine returns the new SL/TP
     the caller should set on the remaining position (or None if the
     existing SL/TP should be left untouched).

Safety invariants (HARD):
  - Disabled by default. Caller must pass ``enabled=True`` to opt in.
  - Never produces a dust position (remaining lot always >= broker min_lot).
  - Never closes more than the open volume.
  - Never auto-retries a failed partial close.
  - Never increases risk after a partial close (no martingale, no grid,
    no averaging, no loss-based multiplier).
  - Never calls ``mt5.order_send``. The caller is responsible for the
    actual close.

Hard flags:
    no_martingale=True
    no_grid=True
    no_averaging=True
    no_loss_based_lot_multiplier=True
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, Any

logger = logging.getLogger(__name__)


# ─── Safety flags mirrored across the production stack ──────────────────────
SAFETY_FLAGS: dict[str, bool] = {
    "no_martingale": True,
    "no_grid": True,
    "no_averaging": True,
    "no_loss_based_lot_multiplier": True,
}


# ─── Exceptions ──────────────────────────────────────────────────────────────
class PartialCloseError(Exception):
    """Raised for general partial-close failures."""


class PartialCloseDisabled(Exception):
    """Raised when partial close is attempted while the engine is disabled."""


class DustPositionForbidden(Exception):
    """
    Raised when a partial close would leave a dust position (remaining
    lot below broker min_lot or below the configured dust threshold).
    """


# ─── Enums ───────────────────────────────────────────────────────────────────
class PartialClosePolicy(str, Enum):
    """
    Partial close policy.

    DISABLED                — engine refuses all partial close requests.
    FIXED_FRACTION          — close a fixed fraction (e.g. 50%) of the lot.
    FIXED_LOT               — close a fixed lot amount.
    R_THRESHOLD             — close at +R threshold (e.g. close 50% at +1R).
    """
    DISABLED = "DISABLED"
    FIXED_FRACTION = "FIXED_FRACTION"
    FIXED_LOT = "FIXED_LOT"
    R_THRESHOLD = "R_THRESHOLD"


class PartialCloseVerdict(str, Enum):
    """High-level verdict returned by the engine."""
    ALLOWED = "ALLOWED"
    BLOCKED_DISABLED = "BLOCKED_DISABLED"
    BLOCKED_BROKER = "BLOCKED_BROKER"
    BLOCKED_LOT = "BLOCKED_LOT"
    BLOCKED_DUST = "BLOCKED_DUST"
    BLOCKED_NO_PROFIT = "BLOCKED_NO_PROFIT"
    BLOCKED_INVALID_INPUT = "BLOCKED_INVALID_INPUT"


# ─── Dataclasses ─────────────────────────────────────────────────────────────
@dataclass
class PositionFacts:
    """
    Raw facts about an open position (provided by the caller; not queried).

    The engine NEVER queries MT5 directly. The caller is responsible for
    obtaining ``open_lot``, ``open_price``, ``current_price``, ``sl``,
    ``tp``, etc. from ``mt5.positions_get()`` and passing them in.
    """
    ticket: int = 0
    symbol: str = ""
    side: str = "BUY"                   # BUY | SELL
    open_lot: float = 0.0
    open_price: float = 0.0
    current_price: float = 0.0
    sl: float = 0.0
    tp: float = 0.0
    # Optional R-multiple context (entry-to-SL distance in price).
    sl_distance_price: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class BrokerPartialCloseSupport:
    """
    Broker/position facts that affect partial close eligibility.

    The caller populates this from the broker profile + MT5 symbol spec.
    """
    supports_partial_close: bool = True
    min_lot: float = 0.01
    lot_step: float = 0.01
    contract_size: float = 100.0
    tick_value: float = 1.0
    tick_size: float = 0.01
    # Dust threshold — the engine refuses any partial close that would
    # leave a remaining lot below this value (defaults to broker min_lot).
    dust_threshold: Optional[float] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PartialClosePlan:
    """
    Result of ``calculate_partial_close()``.

    Contains the partial close lot, realized profit estimate, remaining
    position state, and the SL/TP to apply to the remaining position
    (``new_sl`` / ``new_tp`` = None means "leave unchanged").
    """
    verdict: PartialCloseVerdict
    policy: PartialClosePolicy
    close_lot: float                     # lot to close (0.0 if blocked)
    remaining_lot: float                 # lot remaining after close
    realized_profit: float               # estimated realized profit (account ccy)
    open_price: float
    close_price: float
    side: str
    new_sl: Optional[float] = None       # SL to apply to remaining position
    new_tp: Optional[float] = None       # TP to apply to remaining position
    reason: str = ""
    safety_flags: dict[str, bool] = field(default_factory=lambda: dict(SAFETY_FLAGS))

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RemainingLotValidation:
    """Result of ``validate_remaining_lot()``."""
    ok: bool
    remaining_lot: float
    min_lot: float
    lot_step: float
    dust_threshold: float
    is_dust: bool = False
    rounded_to_step: bool = False
    reason: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# ─── Engine ─────────────────────────────────────────────────────────────────
class PartialCloseEngine:
    """
    Partial close engine.

    Construction:
        engine = PartialCloseEngine(
            enabled=True,                                # opt-in
            policy=PartialClosePolicy.FIXED_FRACTION,
            fixed_fraction=0.5,
            fixed_lot=0.01,
            r_threshold=1.0,
            preserve_sl_tp_on_partial=True,
            dust_threshold=None,                         # defaults to broker min
        )

    Usage:
        plan = engine.calculate_partial_close(
            position=position_facts,
            broker=broker_support,
        )
        if plan.verdict == PartialCloseVerdict.ALLOWED:
            # Caller invokes mt5.order_send with plan.close_lot
            # Then applies plan.new_sl / plan.new_tp if not None.
            ...

    The engine NEVER calls ``mt5.order_send``. It only computes the
        safe plan and hands it back to the caller.
    """

    # Maximum fraction of the position that can be closed in a single
    # partial close. 1.0 = full close (use close_position instead).
    MAX_FRACTION: float = 0.95

    def __init__(
        self,
        enabled: bool = False,
        policy: PartialClosePolicy = PartialClosePolicy.DISABLED,
        fixed_fraction: float = 0.5,
        fixed_lot: float = 0.01,
        r_threshold: float = 1.0,
        preserve_sl_tp_on_partial: bool = True,
        dust_threshold: Optional[float] = None,
        require_profit: bool = True,
    ):
        if not 0.0 < fixed_fraction <= self.MAX_FRACTION:
            raise ValueError(
                f"fixed_fraction must be in (0.0, {self.MAX_FRACTION}] "
                f"(got {fixed_fraction})"
            )
        if fixed_lot <= 0.0:
            raise ValueError("fixed_lot must be > 0")
        if r_threshold <= 0.0:
            raise ValueError("r_threshold must be > 0")

        self.enabled = bool(enabled)
        # If the engine is disabled, force the policy to DISABLED for
        # safety. Even if the caller passes policy=FIXED_FRACTION with
        # enabled=False, the engine will refuse all requests.
        self.policy = PartialClosePolicy(policy) if self.enabled else PartialClosePolicy.DISABLED
        self.fixed_fraction = float(fixed_fraction)
        self.fixed_lot = float(fixed_lot)
        self.r_threshold = float(r_threshold)
        self.preserve_sl_tp_on_partial = bool(preserve_sl_tp_on_partial)
        self.dust_threshold = dust_threshold  # resolved per-call from broker
        self.require_profit = bool(require_profit)

        # Hard safety invariants — exposed for downstream audit.
        self.no_martingale = True
        self.no_grid = True
        self.no_averaging = True
        self.no_loss_based_lot_multiplier = True

    # ─── Public properties ───────────────────────────────────────────────

    @property
    def safety_flags(self) -> dict[str, bool]:
        return {
            "no_martingale": self.no_martingale,
            "no_grid": self.no_grid,
            "no_averaging": self.no_averaging,
            "no_loss_based_lot_multiplier": self.no_loss_based_lot_multiplier,
        }

    @property
    def is_enabled(self) -> bool:
        return self.enabled and self.policy != PartialClosePolicy.DISABLED

    # ─── can_partial_close ───────────────────────────────────────────────

    def can_partial_close(
        self,
        position: PositionFacts,
        broker: BrokerPartialCloseSupport,
    ) -> PartialCloseVerdict:
        """
        Check whether partial close is permitted for this position+broker.

        Returns a verdict:
          ALLOWED              — partial close may proceed.
          BLOCKED_DISABLED     — engine is disabled.
          BLOCKED_BROKER       — broker does not support partial close.
          BLOCKED_LOT          — position lot is below broker min_lot.
          BLOCKED_INVALID_INPUT — position facts are invalid.
        """
        if not self.is_enabled:
            return PartialCloseVerdict.BLOCKED_DISABLED

        if not broker.supports_partial_close:
            return PartialCloseVerdict.BLOCKED_BROKER

        if position.open_lot <= 0.0:
            return PartialCloseVerdict.BLOCKED_INVALID_INPUT
        if position.open_lot < broker.min_lot:
            return PartialCloseVerdict.BLOCKED_LOT
        if position.side.upper() not in ("BUY", "SELL"):
            return PartialCloseVerdict.BLOCKED_INVALID_INPUT
        if position.open_price <= 0.0 or position.current_price <= 0.0:
            return PartialCloseVerdict.BLOCKED_INVALID_INPUT

        return PartialCloseVerdict.ALLOWED

    # ─── calculate_partial_close ─────────────────────────────────────────

    def calculate_partial_close(
        self,
        position: PositionFacts,
        broker: BrokerPartialCloseSupport,
        r_multiple: Optional[float] = None,
    ) -> PartialClosePlan:
        """
        Compute a partial-close plan.

        Args:
            position: open position facts.
            broker: broker partial-close support facts.
            r_multiple: current position R-multiple (profit / initial risk).
                Required for R_THRESHOLD policy; ignored by other policies.

        Returns:
            PartialClosePlan with the close lot, realized profit, and
            new SL/TP to apply to the remaining position.
        """
        verdict = self.can_partial_close(position, broker)
        if verdict != PartialCloseVerdict.ALLOWED:
            return PartialClosePlan(
                verdict=verdict,
                policy=self.policy,
                close_lot=0.0,
                remaining_lot=position.open_lot,
                realized_profit=0.0,
                open_price=position.open_price,
                close_price=position.current_price,
                side=position.side,
                reason=f"Partial close blocked: {verdict.value}",
                safety_flags=self.safety_flags,
            )

        # ─── Determine the close lot by policy ──────────────────────────
        if self.policy == PartialClosePolicy.FIXED_FRACTION:
            raw_close_lot = position.open_lot * self.fixed_fraction
            policy_reason = f"FIXED_FRACTION ({self.fixed_fraction:.2f})"
        elif self.policy == PartialClosePolicy.FIXED_LOT:
            raw_close_lot = self.fixed_lot
            policy_reason = f"FIXED_LOT ({self.fixed_lot:.2f})"
        elif self.policy == PartialClosePolicy.R_THRESHOLD:
            if r_multiple is None or r_multiple < self.r_threshold:
                return PartialClosePlan(
                    verdict=PartialCloseVerdict.BLOCKED_NO_PROFIT,
                    policy=self.policy,
                    close_lot=0.0,
                    remaining_lot=position.open_lot,
                    realized_profit=0.0,
                    open_price=position.open_price,
                    close_price=position.current_price,
                    side=position.side,
                    reason=(
                        f"R_THRESHOLD not reached: r_multiple={r_multiple} "
                        f"< threshold={self.r_threshold}"
                    ),
                    safety_flags=self.safety_flags,
                )
            raw_close_lot = position.open_lot * self.fixed_fraction
            policy_reason = (
                f"R_THRESHOLD ({self.r_threshold:.2f} reached at "
                f"{r_multiple:.2f}, fraction={self.fixed_fraction:.2f})"
            )
        else:  # pragma: no cover — defensive
            return PartialClosePlan(
                verdict=PartialCloseVerdict.BLOCKED_DISABLED,
                policy=self.policy,
                close_lot=0.0,
                remaining_lot=position.open_lot,
                realized_profit=0.0,
                open_price=position.open_price,
                close_price=position.current_price,
                side=position.side,
                reason=f"Unknown policy: {self.policy}",
                safety_flags=self.safety_flags,
            )

        # ─── Validate profit requirement (if enabled) ──────────────────
        profit = self._compute_realized_profit(
            position, raw_close_lot, broker
        )
        if self.require_profit and profit <= 0.0:
            return PartialClosePlan(
                verdict=PartialCloseVerdict.BLOCKED_NO_PROFIT,
                policy=self.policy,
                close_lot=0.0,
                remaining_lot=position.open_lot,
                realized_profit=profit,
                open_price=position.open_price,
                close_price=position.current_price,
                side=position.side,
                reason=(
                    f"require_profit=True but realized profit <= 0 "
                    f"(profit={profit:.4f})"
                ),
                safety_flags=self.safety_flags,
            )

        # ─── Round close lot DOWN to lot_step ───────────────────────────
        lot_step = broker.lot_step if broker.lot_step > 0 else 0.01
        close_lot = (raw_close_lot // lot_step) * lot_step

        # ─── Clamp close_lot into [0, open_lot - dust_threshold] ────────
        dust_threshold = (
            self.dust_threshold
            if self.dust_threshold is not None
            else broker.min_lot
        )
        max_closeable = max(0.0, position.open_lot - dust_threshold)
        if close_lot > max_closeable:
            close_lot = (max_closeable // lot_step) * lot_step
        if close_lot < broker.min_lot:
            return PartialClosePlan(
                verdict=PartialCloseVerdict.BLOCKED_LOT,
                policy=self.policy,
                close_lot=0.0,
                remaining_lot=position.open_lot,
                realized_profit=0.0,
                open_price=position.open_price,
                close_price=position.current_price,
                side=position.side,
                reason=(
                    f"Close lot {close_lot:.4f} below broker min_lot "
                    f"{broker.min_lot:.4f}"
                ),
                safety_flags=self.safety_flags,
            )

        remaining_lot = position.open_lot - close_lot
        # Re-validate remaining lot (no dust).
        validation = self.validate_remaining_lot(remaining_lot, broker)
        if not validation.ok:
            return PartialClosePlan(
                verdict=PartialCloseVerdict.BLOCKED_DUST,
                policy=self.policy,
                close_lot=0.0,
                remaining_lot=position.open_lot,
                realized_profit=0.0,
                open_price=position.open_price,
                close_price=position.current_price,
                side=position.side,
                reason=f"Remaining lot validation failed: {validation.reason}",
                safety_flags=self.safety_flags,
            )

        # ─── Realized profit on the closed portion ─────────────────────
        realized_profit = self._compute_realized_profit(
            position, close_lot, broker
        )

        # ─── SL/TP preservation ────────────────────────────────────────
        if self.preserve_sl_tp_on_partial:
            new_sl = position.sl  # leave unchanged (caller may still apply)
            new_tp = position.tp
        else:
            # Move SL to breakeven (open_price) after partial close.
            new_sl = position.open_price
            new_tp = position.tp

        return PartialClosePlan(
            verdict=PartialCloseVerdict.ALLOWED,
            policy=self.policy,
            close_lot=close_lot,
            remaining_lot=remaining_lot,
            realized_profit=realized_profit,
            open_price=position.open_price,
            close_price=position.current_price,
            side=position.side,
            new_sl=new_sl,
            new_tp=new_tp,
            reason=(
                f"{policy_reason}: close {close_lot:.4f} of "
                f"{position.open_lot:.4f}, remaining {remaining_lot:.4f}, "
                f"realized profit {realized_profit:.4f}"
            ),
            safety_flags=self.safety_flags,
        )

    # ─── validate_remaining_lot ──────────────────────────────────────────

    def validate_remaining_lot(
        self,
        remaining_lot: float,
        broker: BrokerPartialCloseSupport,
    ) -> RemainingLotValidation:
        """
        Validate that a remaining lot is non-dust and >= broker min_lot.

        The lot is also checked for being an exact multiple of lot_step.
        """
        lot_step = broker.lot_step if broker.lot_step > 0 else 0.01
        dust_threshold = (
            self.dust_threshold
            if self.dust_threshold is not None
            else broker.min_lot
        )
        lot = float(remaining_lot)
        is_dust = lot < dust_threshold
        below_min = lot < broker.min_lot
        # Check lot-step alignment (within float tolerance).
        if lot_step > 0 and lot > 0:
            ratio = lot / lot_step
            rounded = abs(ratio - round(ratio)) < 1e-6
        else:
            rounded = True

        if is_dust or below_min:
            return RemainingLotValidation(
                ok=False,
                remaining_lot=lot,
                min_lot=broker.min_lot,
                lot_step=lot_step,
                dust_threshold=dust_threshold,
                is_dust=is_dust,
                rounded_to_step=rounded,
                reason=(
                    f"Remaining lot {lot:.4f} below "
                    f"{'dust_threshold' if is_dust else 'broker min_lot'} "
                    f"({dust_threshold:.4f})"
                ),
            )
        if not rounded:
            return RemainingLotValidation(
                ok=False,
                remaining_lot=lot,
                min_lot=broker.min_lot,
                lot_step=lot_step,
                dust_threshold=dust_threshold,
                is_dust=False,
                rounded_to_step=False,
                reason=(
                    f"Remaining lot {lot:.4f} not a multiple of lot_step "
                    f"{lot_step:.4f}"
                ),
            )
        return RemainingLotValidation(
            ok=True,
            remaining_lot=lot,
            min_lot=broker.min_lot,
            lot_step=lot_step,
            dust_threshold=dust_threshold,
            is_dust=False,
            rounded_to_step=True,
            reason=(
                f"Remaining lot {lot:.4f} valid "
                f"(>= {broker.min_lot:.4f}, >= dust {dust_threshold:.4f}, "
                f"step {lot_step:.4f})"
            ),
        )

    # ─── Recompute remaining risk ────────────────────────────────────────

    def recompute_remaining_risk(
        self,
        position: PositionFacts,
        remaining_lot: float,
        broker: BrokerPartialCloseSupport,
    ) -> dict[str, float]:
        """
        Recompute the remaining dollar-risk on the open position after a
        partial close.

        Risk = |current_price - sl| * (remaining_lot * contract_size / tick_size) * tick_value

        Returns a dict with ``remaining_risk``, ``original_risk``,
        ``risk_reduction``, and ``risk_reduction_pct``.
        """
        if position.sl <= 0.0:
            return {
                "remaining_risk": 0.0,
                "original_risk": 0.0,
                "risk_reduction": 0.0,
                "risk_reduction_pct": 0.0,
                "reason": "No SL set — risk undefined",
            }
        sl_distance = abs(position.current_price - position.sl)
        ticks = sl_distance / max(broker.tick_size, 1e-9)
        original_risk = (
            ticks * broker.tick_value * position.open_lot
        )
        remaining_risk = (
            ticks * broker.tick_value * remaining_lot
        )
        if original_risk > 0.0:
            reduction_pct = 1.0 - (remaining_risk / original_risk)
        else:
            reduction_pct = 0.0
        return {
            "remaining_risk": remaining_risk,
            "original_risk": original_risk,
            "risk_reduction": original_risk - remaining_risk,
            "risk_reduction_pct": reduction_pct,
            "reason": "Risk recomputed from current_price to SL",
        }

    # ─── Helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _compute_realized_profit(
        position: PositionFacts,
        close_lot: float,
        broker: BrokerPartialCloseSupport,
    ) -> float:
        """
        Compute the realized profit on the closed portion.

        For BUY: profit = (close_price - open_price) * close_lot * contract_size
        For SELL: profit = (open_price - close_price) * close_lot * contract_size
        """
        if close_lot <= 0.0:
            return 0.0
        side = position.side.upper()
        if side == "BUY":
            price_diff = position.current_price - position.open_price
        else:  # SELL
            price_diff = position.open_price - position.current_price
        return float(price_diff * close_lot * broker.contract_size)

    # ─── Introspection ───────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "policy": self.policy.value,
            "fixed_fraction": self.fixed_fraction,
            "fixed_lot": self.fixed_lot,
            "r_threshold": self.r_threshold,
            "preserve_sl_tp_on_partial": self.preserve_sl_tp_on_partial,
            "dust_threshold": self.dust_threshold,
            "require_profit": self.require_profit,
            "safety_flags": self.safety_flags,
        }
