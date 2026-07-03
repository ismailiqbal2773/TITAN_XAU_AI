"""TITAN XAU AI - Auto Lot Sizing Engine (Sprint v2.8.5-D.1/E)
=================================================================

Real balance/equity-based Auto Lot Sizing Engine.

Calculates safe lot size from:
  - account_balance / account_equity
  - risk_percent (constant, never changes)
  - stop_loss_points
  - symbol_tick_value / tick_size / contract_size
  - broker constraints (min_lot, max_lot, lot_step)
  - profile caps (min_lot, max_lot)
  - account_mode (DEMO_SAFE, RETAIL_CENT_SAFE, etc.)
  - risk_tier (TIER_0, TIER_1, TIER_2)
  - ceo_risk_multiplier (from CEO AI Governance, never > 1.0)
  - drawdown_state / daily_drawdown_percent / total_drawdown_percent
  - capital_preservation_active
  - loss_streak
  - open_positions_count

Core formula:
  risk_amount = account_equity * risk_percent * ceo_risk_multiplier
  sl_money_per_1_lot = stop_loss_points * tick_value_per_point_for_1_lot
  raw_lot = risk_amount / sl_money_per_1_lot

Hard rules:
  1. Risk percent constant (never changes)
  2. RR geometry unchanged
  3. Lot may increase only because equity grows + profile cap allows
  4. Lot must decrease during drawdown/loss_streak/capital_preservation/weak CEO
  5. No martingale / grid / averaging / loss multiplier
  6. No forced recovery
  7. No lot increase after loss
  8. No lot increase to chase 30% monthly target
  9. If calculated lot > cap, use capped lot
  10. If capped lot violates risk, block
  11. If broker min lot violates risk, block (not force unsafe lot)

NEVER calls mt5.order_send. NEVER creates token. NEVER modifies positions.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
import math


@dataclass
class AutoLotResult:
    """Result of Auto Lot Sizing calculation."""
    auto_lot_enabled: bool = True
    account_equity_used: float = 0.0
    risk_percent: float = 0.0
    effective_risk_percent: float = 0.0
    risk_amount: float = 0.0
    stop_loss_points: float = 0.0
    sl_money_per_lot: float = 0.0
    raw_lot: float = 0.0
    rounded_lot: float = 0.0
    capped_lot: float = 0.0
    final_lot: float = 0.0
    profile_max_lot: float = 0.0
    cap_reasons: list = field(default_factory=list)
    blocked: bool = False
    blockers: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    reasoning_codes: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "auto_lot_enabled": self.auto_lot_enabled,
            "account_equity_used": self.account_equity_used,
            "risk_percent": self.risk_percent,
            "effective_risk_percent": self.effective_risk_percent,
            "risk_amount": self.risk_amount,
            "stop_loss_points": self.stop_loss_points,
            "sl_money_per_lot": self.sl_money_per_lot,
            "raw_lot": self.raw_lot,
            "rounded_lot": self.rounded_lot,
            "capped_lot": self.capped_lot,
            "final_lot": self.final_lot,
            "profile_max_lot": self.profile_max_lot,
            "cap_reasons": self.cap_reasons,
            "blocked": self.blocked,
            "blockers": self.blockers,
            "warnings": self.warnings,
            "reasoning_codes": self.reasoning_codes,
        }


# Profile defaults
PROFILE_DEFAULTS = {
    "DEMO_SAFE": {
        "auto_lot_enabled": True,
        "profile_min_lot": 0.01,
        "profile_max_lot": 0.01,
        "risk_percent": 0.005,
    },
    "RETAIL_CENT_SAFE": {
        "auto_lot_enabled": True,
        "profile_min_lot": 0.01,
        "profile_max_lot": 0.10,
        "risk_percent": 0.005,
    },
    "RETAIL_STANDARD_SAFE": {
        "auto_lot_enabled": True,
        "profile_min_lot": 0.01,
        "profile_max_lot": 0.50,
        "risk_percent": 0.005,
    },
    "PROP_CHALLENGE_SAFE": {
        "auto_lot_enabled": True,
        "profile_min_lot": 0.01,
        "profile_max_lot": 0.05,
        "risk_percent": 0.005,
    },
    "INSTITUTIONAL_CONSERVATIVE": {
        "auto_lot_enabled": True,
        "profile_min_lot": 0.01,
        "profile_max_lot": 1.00,
        "risk_percent": 0.0025,
    },
}

# XAUUSD typical values (operator can override)
XAUUSD_TICK_VALUE_PER_POINT_1LOT = 1.0  # $1 per point per 1 lot
XAUUSD_TICK_SIZE = 0.01
XAUUSD_CONTRACT_SIZE = 100.0


def calculate_auto_lot(
    *,
    account_balance: float = 10000.0,
    account_equity: float = 10000.0,
    risk_percent: float = 0.005,
    stop_loss_points: float = 50.0,
    symbol_tick_value: float = XAUUSD_TICK_VALUE_PER_POINT_1LOT,
    symbol_tick_size: float = XAUUSD_TICK_SIZE,
    symbol_contract_size: float = XAUUSD_CONTRACT_SIZE,
    broker_min_lot: float = 0.01,
    broker_max_lot: float = 0.01,
    broker_lot_step: float = 0.01,
    profile_min_lot: float = 0.01,
    profile_max_lot: float = 0.01,
    account_mode: str = "DEMO_SAFE",
    risk_tier: str = "TIER_1_STANDARD",
    ceo_risk_multiplier: float = 1.0,
    drawdown_state: str = "normal",
    daily_drawdown_percent: float = 0.0,
    total_drawdown_percent: float = 0.0,
    capital_preservation_active: bool = False,
    loss_streak: int = 0,
    open_positions_count: int = 0,
    max_open_positions: int = 1,
) -> AutoLotResult:
    """Calculate safe lot size using balance/equity-based risk management.

    NEVER calls mt5.order_send. NEVER creates token. NEVER modifies positions.

    Hard rules enforced:
      - risk_percent is constant (never changes)
      - ceo_risk_multiplier never exceeds 1.0
      - No martingale/grid/averaging/loss multiplier
      - Lot decreases during drawdown/loss_streak/capital_preservation
      - Lot never increases after loss
      - Final lot never exceeds profile_max_lot
      - If broker min lot violates risk cap, BLOCK (not force unsafe lot)
    """
    result = AutoLotResult()
    result.account_equity_used = account_equity
    result.risk_percent = risk_percent
    result.stop_loss_points = stop_loss_points
    result.profile_max_lot = profile_max_lot

    # Apply profile defaults if not overridden
    prof = PROFILE_DEFAULTS.get(account_mode, {})
    if prof:
        if profile_max_lot > prof.get("profile_max_lot", 0.01):
            profile_max_lot = prof["profile_max_lot"]
            result.profile_max_lot = profile_max_lot
            result.cap_reasons.append(f"profile_max_lot_capped_to_{profile_max_lot}")
        if risk_percent > prof.get("risk_percent", 0.005):
            risk_percent = prof["risk_percent"]
            result.risk_percent = risk_percent
            result.cap_reasons.append(f"risk_percent_capped_to_{risk_percent}")

    # Enforce CEO risk_multiplier cap (never > 1.0)
    if ceo_risk_multiplier > 1.0:
        ceo_risk_multiplier = 1.0
        result.warnings.append("CEO_RISK_MULTIPLIER_CAPPED_TO_1.0")
        result.reasoning_codes.append("CEO_RISK_MULTIPLIER_CAPPED")

    # Calculate effective risk percent
    result.effective_risk_percent = risk_percent * ceo_risk_multiplier

    # === Hard blocks ===

    # Block if stop_loss_points <= 0
    if stop_loss_points <= 0:
        result.blocked = True
        result.blockers.append("INVALID_STOP_LOSS: stop_loss_points <= 0")
        result.reasoning_codes.append("INVALID_SL")
        result.final_lot = 0.0
        return result

    # Block if account equity <= 0
    if account_equity <= 0:
        result.blocked = True
        result.blockers.append("INVALID_EQUITY: account_equity <= 0")
        result.reasoning_codes.append("INVALID_EQUITY")
        result.final_lot = 0.0
        return result

    # Block if tick value invalid
    if symbol_tick_value <= 0:
        result.blocked = True
        result.blockers.append("INVALID_TICK_VALUE: symbol_tick_value <= 0")
        result.reasoning_codes.append("INVALID_TICK_VALUE")
        result.final_lot = 0.0
        return result

    # Block if max open positions exceeded
    if open_positions_count >= max_open_positions:
        result.blocked = True
        result.blockers.append(
            f"MAX_OPEN_POSITIONS_EXCEEDED: {open_positions_count} >= {max_open_positions}"
        )
        result.reasoning_codes.append("MAX_POSITIONS")
        result.final_lot = 0.0
        return result

    # === Drawdown adjustments (reduce lot, never increase) ===
    drawdown_multiplier = 1.0

    # Capital preservation mode: reduce to 50%
    if capital_preservation_active:
        drawdown_multiplier = 0.5
        result.warnings.append("CAPITAL_PRESERVATION_ACTIVE: lot reduced to 50%")
        result.reasoning_codes.append("CAPITAL_PRESERVATION")
        result.cap_reasons.append("capital_preservation_50pct")

    # Daily DD soft limit: reduce to 50%
    if daily_drawdown_percent >= 0.01:  # 1% soft limit
        drawdown_multiplier = min(drawdown_multiplier, 0.5)
        result.warnings.append(
            f"DAILY_DD_SOFT_LIMIT: {daily_drawdown_percent:.4f} >= 0.01, lot reduced to 50%"
        )
        result.reasoning_codes.append("DAILY_DD_SOFT")
        result.cap_reasons.append("daily_dd_soft_50pct")

    # Daily DD hard limit: block
    if daily_drawdown_percent >= 0.02:  # 2% hard limit
        result.blocked = True
        result.blockers.append(
            f"DAILY_DD_HARD_LIMIT: {daily_drawdown_percent:.4f} >= 0.02"
        )
        result.reasoning_codes.append("DAILY_DD_HARD")
        result.final_lot = 0.0
        return result

    # Total DD cap: block
    if total_drawdown_percent >= 0.08:  # 8% total DD cap
        result.blocked = True
        result.blockers.append(
            f"TOTAL_DD_CAP_EXCEEDED: {total_drawdown_percent:.4f} >= 0.08"
        )
        result.reasoning_codes.append("TOTAL_DD_CAP")
        result.final_lot = 0.0
        return result

    # Loss streak: reduce lot (never increase)
    if loss_streak >= 3:
        streak_reduction = max(0.25, 1.0 - (loss_streak - 2) * 0.25)
        drawdown_multiplier = min(drawdown_multiplier, streak_reduction)
        result.warnings.append(
            f"LOSS_STREAK_REDUCTION: {loss_streak} losses, lot reduced to {streak_reduction*100:.0f}%"
        )
        result.reasoning_codes.append("LOSS_STREAK_REDUCTION")
        result.cap_reasons.append(f"loss_streak_{loss_streak}_reduction")

    # TIER_0_CAPITAL_PRESERVATION: reduce risk
    if risk_tier == "TIER_0_CAPITAL_PRESERVATION":
        drawdown_multiplier = min(drawdown_multiplier, 0.5)
        result.warnings.append("TIER_0_CAPITAL_PRESERVATION: lot reduced to 50%")
        result.reasoning_codes.append("TIER_0_REDUCTION")
        result.cap_reasons.append("tier_0_50pct")

    # === Core calculation ===
    # risk_amount = equity * risk_percent * ceo_risk_multiplier * drawdown_multiplier
    result.risk_amount = account_equity * result.effective_risk_percent * drawdown_multiplier

    # sl_money_per_1_lot = stop_loss_points * tick_value_per_point_for_1_lot
    result.sl_money_per_lot = stop_loss_points * symbol_tick_value

    # raw_lot = risk_amount / sl_money_per_1_lot
    if result.sl_money_per_lot > 0:
        result.raw_lot = result.risk_amount / result.sl_money_per_lot
    else:
        result.blocked = True
        result.blockers.append("SL_MONEY_PER_LOT_ZERO: cannot calculate lot")
        result.final_lot = 0.0
        return result

    # === Rounding ===
    # Round down to broker_lot_step
    if broker_lot_step > 0:
        result.rounded_lot = math.floor(result.raw_lot / broker_lot_step) * broker_lot_step
    else:
        result.rounded_lot = result.raw_lot
    result.rounded_lot = round(result.rounded_lot, 4)

    # === Capping ===
    capped = result.rounded_lot

    # Enforce broker_max_lot
    if capped > broker_max_lot:
        capped = broker_max_lot
        result.cap_reasons.append(f"broker_max_lot_{broker_max_lot}")

    # Enforce profile_max_lot
    if capped > profile_max_lot:
        capped = profile_max_lot
        result.cap_reasons.append(f"profile_max_lot_{profile_max_lot}")

    # Enforce broker_min_lot (floor)
    if capped < broker_min_lot:
        # Check if broker_min_lot violates risk cap
        min_lot_risk = broker_min_lot * result.sl_money_per_lot
        if min_lot_risk > result.risk_amount:
            result.blocked = True
            result.blockers.append(
                f"BROKER_MIN_LOT_VIOLATES_RISK: min_lot={broker_min_lot} "
                f"risk={min_lot_risk:.2f} > risk_amount={result.risk_amount:.2f}"
            )
            result.reasoning_codes.append("BROKER_MIN_LOT_RISK_VIOLATION")
            result.final_lot = 0.0
            return result
        capped = broker_min_lot
        result.cap_reasons.append(f"broker_min_lot_floor_{broker_min_lot}")

    # Enforce profile_min_lot
    if capped < profile_min_lot:
        min_lot_risk = profile_min_lot * result.sl_money_per_lot
        if min_lot_risk > result.risk_amount:
            result.blocked = True
            result.blockers.append(
                f"PROFILE_MIN_LOT_VIOLATES_RISK: min_lot={profile_min_lot} "
                f"risk={min_lot_risk:.2f} > risk_amount={result.risk_amount:.2f}"
            )
            result.reasoning_codes.append("PROFILE_MIN_LOT_RISK_VIOLATION")
            result.final_lot = 0.0
            return result
        capped = profile_min_lot
        result.cap_reasons.append(f"profile_min_lot_floor_{profile_min_lot}")

    result.capped_lot = round(capped, 4)
    result.final_lot = result.capped_lot

    # === No martingale / no loss-based multiplier check ===
    # (ensured by design: lot is calculated from equity, not from previous lot)
    result.reasoning_codes.append("NO_MARTINGALE")
    result.reasoning_codes.append("NO_LOSS_MULTIPLIER")
    result.reasoning_codes.append("RISK_PERCENT_CONSTANT")

    # === Final safety: DEMO_SAFE must never exceed 0.01 ===
    if account_mode == "DEMO_SAFE" and result.final_lot > 0.01:
        result.final_lot = 0.01
        result.cap_reasons.append("DEMO_SAFE_hard_cap_0.01")

    result.reasoning_codes.append(f"final_lot_{result.final_lot}")

    return result
