"""TITAN XAU AI — Monetary Conversion (FINAL v2.8.7-P2.1)
=========================================================

One canonical monetary conversion used everywhere:

  ticks   = price_delta / tick_size
  money   = ticks × tick_value × lot_size × conversion_rate

This same function is used for:
  - monetary SL loss
  - gross trade PnL
  - adverse gap PnL
  - spread cost
  - slippage cost
  - MFE/MAE monetary conversion
  - risk reconciliation

Metadata consistency validation:

  money_per_price_unit_from_ticks    = tick_value / tick_size × conversion_rate
  money_per_price_unit_from_contract = contract_size × quote/account conversion

For directly-quoted USD instruments (account_currency == profit_currency
== symbol_currency == "USD"), these two values must be equal within a
small configured tolerance.

The previously-inconsistent fixture:

    tick_size=0.01
    tick_value=0.01
    contract_size=100

is REJECTED because:
  money_per_price_unit_from_ticks    = 0.01 / 0.01 × 1.0 = 1.0
  money_per_price_unit_from_contract = 100.0 × 1.0      = 100.0

A valid XAUUSD fixture is:

    tick_size=0.01
    tick_value=1.00
    contract_size=100

which yields 100.0 from both methods.

NEVER sends orders. NEVER creates tokens. NEVER trades.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Tuple
import math


# Default tolerance for cross-method consistency check (1% of contract-based value)
DEFAULT_CONSISTENCY_TOLERANCE = 0.01


@dataclass
class InstrumentSpec:
    """Validated instrument specification.

    For XAUUSD on a standard broker:
        tick_size       = 0.01   (USD per tick)
        tick_value      = 1.00   (USD per tick per lot)
        contract_size   = 100    (oz per lot)
        volume_min      = 0.01
        volume_max      = 100.0
        volume_step     = 0.01
        account_currency = "USD"
        profit_currency  = "USD"
        symbol_currency  = "USD"
        conversion_rate  = 1.0
    """
    tick_size: float = 0.01
    tick_value: float = 1.0
    contract_size: float = 100.0
    volume_min: float = 0.01
    volume_max: float = 100.0
    volume_step: float = 0.01
    account_currency: str = "USD"
    profit_currency: str = "USD"
    symbol_currency: str = "USD"
    conversion_rate: float = 1.0


def validate_instrument_spec(spec: Optional[InstrumentSpec]) -> Tuple[bool, str]:
    """Validate every InstrumentSpec field AND cross-method consistency.

    Returns (ok, reason). On failure, reason identifies the failing check.
    """
    if spec is None:
        return False, "instrument_spec_missing"
    if spec.tick_size <= 0:
        return False, "tick_size_invalid"
    if spec.tick_value <= 0:
        return False, "tick_value_invalid"
    if spec.contract_size <= 0:
        return False, "contract_size_invalid"
    if spec.volume_min <= 0:
        return False, "volume_min_invalid"
    if spec.volume_max <= 0:
        return False, "volume_max_invalid"
    if spec.volume_step <= 0:
        return False, "volume_step_invalid"
    if spec.volume_min > spec.volume_max:
        return False, "volume_min_exceeds_max"
    if not spec.account_currency:
        return False, "account_currency_empty"
    if not spec.profit_currency:
        return False, "profit_currency_empty"
    if not spec.symbol_currency:
        return False, "symbol_currency_empty"
    if spec.conversion_rate <= 0:
        return False, "conversion_rate_invalid"

    # Cross-method consistency
    ok, reason = _check_value_consistency(spec, DEFAULT_CONSISTENCY_TOLERANCE)
    if not ok:
        return False, reason
    return True, ""


def _check_value_consistency(spec: InstrumentSpec, tolerance: float) -> Tuple[bool, str]:
    """Verify tick-based and contract-based money-per-price-unit match.

    For directly-quoted instruments where account == profit == symbol == USD,
    the two methods must reconcile within tolerance.

    money_per_price_unit_from_ticks    = tick_value / tick_size × conversion_rate
    money_per_price_unit_from_contract = contract_size × quote/account conversion
    """
    if spec.tick_size <= 0:
        return False, "tick_size_invalid_for_consistency"
    from_ticks = (spec.tick_value / spec.tick_size) * spec.conversion_rate
    from_contract = spec.contract_size * spec.conversion_rate
    if from_ticks <= 0 or from_contract <= 0:
        return False, "money_per_price_unit_nonpositive"
    # For USD-direct instruments, require tight consistency
    is_usd_direct = (spec.account_currency == "USD"
                     and spec.profit_currency == "USD"
                     and spec.symbol_currency == "USD")
    if is_usd_direct:
        rel_diff = abs(from_ticks - from_contract) / max(from_contract, 1e-9)
        if rel_diff > tolerance:
            return False, (
                f"value_consistency_mismatch:"
                f"tick_based={from_ticks:.6f} "
                f"contract_based={from_contract:.6f} "
                f"rel_diff={rel_diff:.6f} > tolerance={tolerance:.6f}"
            )
    return True, ""


def price_delta_to_money(spec: InstrumentSpec, price_delta: float, lot_size: float) -> float:
    """Convert a price delta to monetary PnL using tick metadata.

        ticks = price_delta / tick_size
        money = ticks × tick_value × lot_size × conversion_rate

    Returns negative for adverse price movement when called with the
    directional price delta (already signed).
    """
    if spec.tick_size <= 0:
        return 0.0
    ticks = price_delta / spec.tick_size
    return ticks * spec.tick_value * lot_size * spec.conversion_rate


def compute_monetary_loss_per_lot(spec: InstrumentSpec, sl_distance_price: float) -> float:
    """Compute monetary loss per 1.0 lot at SL distance using tick metadata."""
    return price_delta_to_money(spec, abs(sl_distance_price), 1.0)


def compute_lot_size(
    spec: InstrumentSpec,
    risk_amount: float,
    sl_distance_price: float,
) -> Tuple[float, float, str]:
    """Compute broker-step-compliant lot size.

    Returns (lot, monetary_loss_at_sl, reject_reason).
    lot=0 and non-empty reject_reason means the trade must be rejected.
    """
    if risk_amount <= 0 or sl_distance_price <= 0:
        return 0.0, 0.0, "non_positive_risk_or_sl"
    loss_per_lot = compute_monetary_loss_per_lot(spec, sl_distance_price)
    if not math.isfinite(loss_per_lot) or loss_per_lot <= 0:
        return 0.0, 0.0, "invalid_tick_metadata"
    raw_lot = risk_amount / loss_per_lot
    if spec.volume_step > 0:
        stepped_lot = math.floor(raw_lot / spec.volume_step) * spec.volume_step
    else:
        stepped_lot = raw_lot
    stepped_lot = min(stepped_lot, spec.volume_max)
    if stepped_lot < spec.volume_min:
        return 0.0, 0.0, (
            f"volume_min_{spec.volume_min}_exceeds_approved_risk_lot_{stepped_lot:.6f}"
        )
    precision = max(0, int(round(-math.log10(spec.volume_step)))) if spec.volume_step < 1 else 0
    stepped_lot = round(stepped_lot, precision)
    monetary_loss = stepped_lot * loss_per_lot
    return stepped_lot, monetary_loss, ""


def valid_xauusd_instrument_spec() -> InstrumentSpec:
    """Return a valid XAUUSD InstrumentSpec fixture.

    tick_size=0.01, tick_value=1.00, contract_size=100 — passes consistency.
    """
    return InstrumentSpec(
        tick_size=0.01, tick_value=1.00, contract_size=100.0,
        volume_min=0.01, volume_max=100.0, volume_step=0.01,
        account_currency="USD", profit_currency="USD",
        symbol_currency="USD", conversion_rate=1.0,
    )


__all__ = [
    "InstrumentSpec", "validate_instrument_spec",
    "price_delta_to_money",
    "compute_monetary_loss_per_lot", "compute_lot_size",
    "valid_xauusd_instrument_spec",
    "DEFAULT_CONSISTENCY_TOLERANCE",
]
