"""
TITAN XAU AI — Lot Sizing Engine (Sprint 9.9.3.45.8.5)
========================================================

Computes the order lot size for a single trade based on the active
account adaptation mode and broker symbol spec. The engine is the
ONLY place in the production stack where the final ``lot`` value is
determined.

Modes:
  FIXED                — proof/demo mode: lot = fixed_lot_for_proof.
                         No balance input, no risk input, no volatility input.
  RISK_PERCENTAGE      — conservative: lot derived from risk-per-trade
                         percentage of dollar equity, divided by SL distance
                         (in price) and contract size. Tightly capped.
  VOLATILITY_SCALED    — institutional: lot derived from a volatility
                         regime scalar (0.0–1.0) applied to the
                         equity-based max_lot. No loss-based input.

Validations enforced on every ``calculate_lot()`` call:
  - Resulting lot >= broker.min_lot (else min_lot used, warning logged).
  - Resulting lot <= account_profile.max_lot (hard cap, never exceeded).
  - Resulting lot <= broker.max_lot (broker cap).
  - Resulting lot is rounded DOWN to broker.lot_step (no dust).
  - If ``loss_based`` flag is passed to ``calculate_lot()``, the engine
    raises ``LossBasedLotMultiplierForbidden`` immediately.

Safety invariants (HARD):
  - no_martingale=True
  - no_grid=True
  - no_averaging=True
  - no_loss_based_lot_multiplier=True

This module is pure Python. It NEVER imports MetaTrader5 and NEVER
calls ``mt5.order_send``.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, Any

from titan.production.account_adaptation_engine import (
    AdaptationResult,
    AdaptationMode,
    LossBasedLotMultiplierForbidden,
    SAFETY_FLAGS as ACCOUNT_SAFETY_FLAGS,
)

logger = logging.getLogger(__name__)


# ─── Safety flags mirrored across the production stack ──────────────────────
SAFETY_FLAGS: dict[str, bool] = {
    "no_martingale": True,
    "no_grid": True,
    "no_averaging": True,
    "no_loss_based_lot_multiplier": True,
}


# ─── Exceptions ──────────────────────────────────────────────────────────────
class LotSizingError(Exception):
    """Raised for general lot-sizing failures (invalid inputs, etc.)."""


class LossBasedLotMultiplierForbidden(Exception):
    """
    Raised when ANY caller attempts to pass a loss-based input to the
    lot sizing engine. Loss-based sizing is forbidden by project
    doctrine and is non-recoverable.
    """


# ─── Enums ───────────────────────────────────────────────────────────────────
class LotSizingMode(str, Enum):
    """
    Lot sizing mode.

    FIXED                — proof/demo: fixed micro lot, no dynamic input.
    RISK_PERCENTAGE      — conservative: risk-percentage of equity.
    VOLATILITY_SCALED    — institutional: equity cap scaled by volatility.
    """
    FIXED = "FIXED"
    RISK_PERCENTAGE = "RISK_PERCENTAGE"
    VOLATILITY_SCALED = "VOLATILITY_SCALED"


# ─── Dataclasses ─────────────────────────────────────────────────────────────
@dataclass
class LotSizingInputs:
    """
    Inputs to ``LotSizingEngine.calculate_lot()``.

    Required fields vary by mode:
      FIXED              — fixed_lot_for_proof (set on engine init).
      RISK_PERCENTAGE    — dollar_equity, risk_per_trade_pct, sl_distance_price,
                           contract_size, tick_value.
      VOLATILITY_SCALED  — dollar_equity, max_lot (account profile),
                           volatility_scalar (0.0–1.0), contract_size, price.
    """
    # Account-level inputs (from AdaptationResult).
    dollar_equity: float = 0.0
    risk_per_trade_pct: float = 0.0
    max_lot_account: float = 0.01        # hard cap from account profile
    min_lot_account: float = 0.01
    # Broker-level inputs (from SymbolSpec).
    broker_min_lot: float = 0.01
    broker_max_lot: float = 100.0
    broker_lot_step: float = 0.01
    contract_size: float = 100.0
    tick_value: float = 1.0
    tick_size: float = 0.01
    # Trade-specific inputs.
    sl_distance_price: float = 0.0       # |entry - SL| in price units
    price: float = 0.0                   # current price (for notional calc)
    volatility_scalar: float = 1.0       # 0.0–1.0, institutional mode only
    fixed_lot_for_proof: float = 0.01    # FIXED mode only

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class LotSizingResult:
    """
    Output of ``calculate_lot()``.

    Contains the final ``lot`` value plus all the intermediate values
    used in the computation for audit/journal purposes.
    """
    mode: LotSizingMode
    lot: float
    requested_lot: float                 # pre-clamp value
    min_lot: float
    max_lot: float
    lot_step: float
    risk_amount: float = 0.0
    sl_distance_price: float = 0.0
    volatility_scalar: float = 1.0
    clamped_to_min: bool = False
    clamped_to_max: bool = False
    rounded_to_step: bool = False
    reason: str = ""
    safety_flags: dict[str, bool] = field(default_factory=lambda: dict(SAFETY_FLAGS))

    def to_dict(self) -> dict:
        return asdict(self)


# ─── Engine ─────────────────────────────────────────────────────────────────
class LotSizingEngine:
    """
    Lot sizing engine.

    Construction:
        engine = LotSizingEngine(
            mode=LotSizingMode.FIXED,
            fixed_lot_for_proof=0.01,
        )

    Usage:
        inputs = LotSizingInputs(
            dollar_equity=10000.0,
            risk_per_trade_pct=0.01,
            sl_distance_price=2.0,
            contract_size=100.0,
            tick_value=1.0,
            broker_min_lot=0.01,
            broker_max_lot=100.0,
            broker_lot_step=0.01,
            max_lot_account=0.05,
            min_lot_account=0.01,
        )
        result = engine.calculate_lot(inputs)

    The engine is stateless across calls — it never accumulates loss
    counts, win counts, or any other historical state. This is a
    deliberate safety design.
    """

    # Absolute hard ceiling regardless of inputs. Even if an account
    # profile allows more, the engine will never produce a lot above
    # this value. Mirrors titan/production/prop_firm_manager.HARD_MAX_LOT_CAP
    # but kept here as a local defensive constant.
    ABSOLUTE_HARD_MAX_LOT: float = 50.0

    def __init__(
        self,
        mode: LotSizingMode = LotSizingMode.FIXED,
        fixed_lot_for_proof: float = 0.01,
        default_lot_step: float = 0.01,
    ):
        if fixed_lot_for_proof <= 0.0:
            raise ValueError("fixed_lot_for_proof must be > 0")
        if default_lot_step <= 0.0:
            raise ValueError("default_lot_step must be > 0")
        self.mode = LotSizingMode(mode)
        self.fixed_lot_for_proof = float(fixed_lot_for_proof)
        self.default_lot_step = float(default_lot_step)

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

    # ─── Entry point ─────────────────────────────────────────────────────

    def calculate_lot(
        self,
        inputs: LotSizingInputs,
        loss_based: bool = False,
        consecutive_losses: Optional[int] = None,
        consecutive_wins: Optional[int] = None,
        last_trade_result: Optional[str] = None,
    ) -> LotSizingResult:
        """
        Compute the final lot for a single trade.

        Args:
            inputs: validated LotSizingInputs (caller is expected to fill
                in all fields relevant to the active mode).
            loss_based: if True, raises LossBasedLotMultiplierForbidden
                immediately. This is a tripwire — no caller should ever
                pass True; the parameter exists to make the doctrine
                explicit and to detect upstream misuse.
            consecutive_losses: if provided (not None), raises
                LossBasedLotMultiplierForbidden. Lot sizing must never
                consider loss counts.
            consecutive_wins: if provided (not None), raises
                LossBasedLotMultiplierForbidden. Lot sizing must never
                consider win counts.
            last_trade_result: if provided (not None), raises
                LossBasedLotMultiplierForbidden. Lot sizing must never
                consider the outcome of the previous trade.

        Returns:
            LotSizingResult with the final ``lot`` and audit metadata.
        """
        # ─── Forbidden inputs tripwires ────────────────────────────────
        if loss_based:
            raise LossBasedLotMultiplierForbidden(
                "calculate_lot(loss_based=True) is FORBIDDEN. Loss-based "
                "lot multipliers are not implemented and never will be."
            )
        if consecutive_losses is not None:
            raise LossBasedLotMultiplierForbidden(
                "calculate_lot(consecutive_losses=...) is FORBIDDEN. Lot "
                "sizing must never consider loss counts."
            )
        if consecutive_wins is not None:
            raise LossBasedLotMultiplierForbidden(
                "calculate_lot(consecutive_wins=...) is FORBIDDEN. Lot "
                "sizing must never consider win counts."
            )
        if last_trade_result is not None:
            raise LossBasedLotMultiplierForbidden(
                "calculate_lot(last_trade_result=...) is FORBIDDEN. Lot "
                "sizing must never consider the previous trade outcome."
            )

        # ─── Resolve mode → raw lot ─────────────────────────────────────
        # Clamp volatility_scalar into [0.0, 1.0] up-front so both the
        # mode implementation and the result see the same value.
        effective_v_scalar = max(0.0, min(1.0, float(inputs.volatility_scalar)))
        # Re-bind a clamped copy of inputs for the mode implementation.
        clamped_inputs = LotSizingInputs(**{**inputs.to_dict(),
                                            "volatility_scalar": effective_v_scalar})
        if self.mode == LotSizingMode.FIXED:
            raw_lot, risk_amount, reason = self._fixed_lot(clamped_inputs)
        elif self.mode == LotSizingMode.RISK_PERCENTAGE:
            raw_lot, risk_amount, reason = self._risk_percentage_lot(clamped_inputs)
        elif self.mode == LotSizingMode.VOLATILITY_SCALED:
            raw_lot, risk_amount, reason = self._volatility_scaled_lot(clamped_inputs)
        else:  # pragma: no cover — defensive
            raise LotSizingError(f"Unknown lot sizing mode: {self.mode}")

        # ─── Validate against broker and account caps ──────────────────
        min_lot = max(
            inputs.broker_min_lot,
            inputs.min_lot_account,
        )
        max_lot = min(
            inputs.broker_max_lot,
            inputs.max_lot_account,
            self.ABSOLUTE_HARD_MAX_LOT,
        )
        if max_lot < min_lot:
            raise LotSizingError(
                f"Invalid lot bounds: max_lot ({max_lot}) < min_lot ({min_lot}). "
                "Broker/account profile misconfiguration."
            )

        requested_lot = float(raw_lot)
        clamped_to_min = False
        clamped_to_max = False
        rounded_to_step = False

        lot = requested_lot
        # Round DOWN to lot_step first to avoid dust.
        lot_step = inputs.broker_lot_step if inputs.broker_lot_step > 0 else self.default_lot_step
        if lot_step > 0 and lot > 0:
            rounded = (lot // lot_step) * lot_step
            if abs(rounded - lot) > 1e-12:
                rounded_to_step = True
            lot = rounded

        # Clamp to min/max.
        if lot < min_lot:
            lot = min_lot
            clamped_to_min = True
        if lot > max_lot:
            lot = max_lot
            clamped_to_max = True

        # Final safety: never produce a zero or negative lot.
        if lot <= 0.0:
            lot = min_lot
            clamped_to_min = True

        return LotSizingResult(
            mode=self.mode,
            lot=lot,
            requested_lot=requested_lot,
            min_lot=min_lot,
            max_lot=max_lot,
            lot_step=lot_step,
            risk_amount=risk_amount,
            sl_distance_price=inputs.sl_distance_price,
            volatility_scalar=effective_v_scalar,
            clamped_to_min=clamped_to_min,
            clamped_to_max=clamped_to_max,
            rounded_to_step=rounded_to_step,
            reason=reason,
            safety_flags=self.safety_flags,
        )

    # ─── Mode implementations ───────────────────────────────────────────

    def _fixed_lot(
        self, inputs: LotSizingInputs
    ) -> tuple[float, float, str]:
        """FIXED mode: lot = fixed_lot_for_proof, no dynamic input."""
        lot = inputs.fixed_lot_for_proof or self.fixed_lot_for_proof
        return float(lot), 0.0, "FIXED: lot=fixed_lot_for_proof (proof/demo)"

    def _risk_percentage_lot(
        self, inputs: LotSizingInputs
    ) -> tuple[float, float, str]:
        """
        RISK_PERCENTAGE mode.

        Formula:
            risk_amount = dollar_equity * risk_per_trade_pct
            risk_per_lot_at_sl = |sl_distance_price| * (contract_size / tick_size) * tick_value
            raw_lot = risk_amount / risk_per_lot_at_sl

        If sl_distance_price is zero (no SL set), the engine falls back
        to a conservative equity-based max_lot proxy. The downstream
        clamp ensures the result is within broker/account bounds.
        """
        if inputs.dollar_equity <= 0.0:
            return 0.0, 0.0, "RISK_PERCENTAGE: dollar_equity <= 0 → lot=0 (will clamp to min)"
        if inputs.risk_per_trade_pct <= 0.0:
            return 0.0, 0.0, "RISK_PERCENTAGE: risk_per_trade_pct <= 0 → lot=0"
        risk_amount = inputs.dollar_equity * inputs.risk_per_trade_pct

        if inputs.sl_distance_price <= 0.0:
            # No SL set — fall back to equity-based proxy.
            # Use a conservative 1% notional risk proxy: assume SL is
            # 1% of price. This still produces a bounded lot.
            if inputs.price <= 0.0:
                return 0.0, risk_amount, "RISK_PERCENTAGE: no SL and no price → lot=0"
            proxy_sl = inputs.price * 0.01
            risk_per_lot = proxy_sl * (inputs.contract_size / max(inputs.tick_size, 1e-9)) * inputs.tick_value
        else:
            risk_per_lot = (
                inputs.sl_distance_price
                * (inputs.contract_size / max(inputs.tick_size, 1e-9))
                * inputs.tick_value
            )

        if risk_per_lot <= 0.0:
            return 0.0, risk_amount, "RISK_PERCENTAGE: risk_per_lot <= 0 → lot=0"

        raw_lot = risk_amount / risk_per_lot
        return float(raw_lot), float(risk_amount), (
            f"RISK_PERCENTAGE: risk_amount={risk_amount:.4f}, "
            f"risk_per_lot={risk_per_lot:.4f}, raw_lot={raw_lot:.4f}"
        )

    def _volatility_scaled_lot(
        self, inputs: LotSizingInputs
    ) -> tuple[float, float, str]:
        """
        VOLATILITY_SCALED mode (institutional).

        Formula:
            equity_max_lot = (dollar_equity * MAX_MARGIN_USAGE_PCT)
                             / (contract_size * price / leverage)
            raw_lot = equity_max_lot * volatility_scalar

        The volatility_scalar (0.0–1.0) is provided externally by the
        volatility regime detector. Lower scalar → smaller lot.
        """
        v_scalar = max(0.0, min(1.0, float(inputs.volatility_scalar)))
        if inputs.dollar_equity <= 0.0:
            return 0.0, 0.0, "VOLATILITY_SCALED: dollar_equity <= 0 → lot=0"
        if inputs.price <= 0.0:
            return 0.0, 0.0, "VOLATILITY_SCALED: price <= 0 → lot=0"

        # Conservative default: 10% margin usage at 100x leverage.
        margin_usage_pct = 0.10
        leverage = 100.0
        notional_per_lot = inputs.contract_size * inputs.price
        margin_per_lot = notional_per_lot / leverage
        if margin_per_lot <= 0.0:
            return 0.0, 0.0, "VOLATILITY_SCALED: margin_per_lot <= 0 → lot=0"
        equity_for_margin = inputs.dollar_equity * margin_usage_pct
        equity_max_lot = equity_for_margin / margin_per_lot
        raw_lot = equity_max_lot * v_scalar
        risk_amount = inputs.dollar_equity * 0.005  # institutional ~0.5% reference
        return float(raw_lot), float(risk_amount), (
            f"VOLATILITY_SCALED: equity_max_lot={equity_max_lot:.4f}, "
            f"volatility_scalar={v_scalar:.2f}, raw_lot={raw_lot:.4f}"
        )

    # ─── Introspection ───────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "mode": self.mode.value,
            "fixed_lot_for_proof": self.fixed_lot_for_proof,
            "default_lot_step": self.default_lot_step,
            "absolute_hard_max_lot": self.ABSOLUTE_HARD_MAX_LOT,
            "safety_flags": self.safety_flags,
        }


# ─── Convenience adapter ────────────────────────────────────────────────────
def lot_sizing_mode_for_adaptation_mode(
    adaptation_mode: AdaptationMode,
) -> LotSizingMode:
    """
    Map an AccountAdaptationEngine mode to the corresponding
    LotSizingEngine mode.

    PROOF_FIXED_LOT                  → FIXED
    CONSERVATIVE_DYNAMIC             → RISK_PERCENTAGE
    PROP_FIRM_CONSERVATIVE           → RISK_PERCENTAGE
    INSTITUTIONAL_VOLATILITY_SCALED  → VOLATILITY_SCALED
    """
    if adaptation_mode == AdaptationMode.PROOF_FIXED_LOT:
        return LotSizingMode.FIXED
    if adaptation_mode in (
        AdaptationMode.CONSERVATIVE_DYNAMIC,
        AdaptationMode.PROP_FIRM_CONSERVATIVE,
    ):
        return LotSizingMode.RISK_PERCENTAGE
    if adaptation_mode == AdaptationMode.INSTITUTIONAL_VOLATILITY_SCALED:
        return LotSizingMode.VOLATILITY_SCALED
    raise LotSizingError(
        f"Unsupported adaptation mode for lot sizing: {adaptation_mode}"
    )


def inputs_from_adaptation_result(
    result: AdaptationResult,
    sl_distance_price: float = 0.0,
    price: float = 2000.0,
    broker_min_lot: float = 0.01,
    broker_max_lot: float = 100.0,
    broker_lot_step: float = 0.01,
    contract_size: float = 100.0,
    tick_value: float = 1.0,
    tick_size: float = 0.01,
) -> LotSizingInputs:
    """
    Build LotSizingInputs from an AdaptationResult + broker spec.

    This is the canonical way to wire the two engines together.
    """
    return LotSizingInputs(
        dollar_equity=result.dollar_equity,
        risk_per_trade_pct=result.risk_per_trade_pct,
        max_lot_account=result.max_lot,
        min_lot_account=result.min_lot,
        broker_min_lot=broker_min_lot,
        broker_max_lot=broker_max_lot,
        broker_lot_step=broker_lot_step,
        contract_size=contract_size,
        tick_value=tick_value,
        tick_size=tick_size,
        sl_distance_price=sl_distance_price,
        price=price,
        volatility_scalar=result.volatility_scalar,
        fixed_lot_for_proof=result.max_lot,  # proof mode lot = result.max_lot
    )
