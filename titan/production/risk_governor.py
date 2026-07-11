"""TITAN XAU AI — Canonical Risk Governor (FINAL Sprint v2.8.7-P2.0)
=====================================================================

One authoritative risk-stage governor used by:
  - corrected backtest
  - forward-shadow runtime
  - opportunity scorer
  - future execution path

Daily stages: caution 1.00%, recovery 1.30%, block 1.60%, emergency 1.80%, limit 2.00%
Total stages: recovery 4.00%, capital_preservation 5.50%, block 6.50%, emergency 7.20%, limit 8.00%

Safety inputs are EXPLICIT and fail-closed:
  - prop_risk_pass: Optional[bool]            default None  -> block on None or False
  - capital_protection_active: Optional[bool] default None  -> block on None or True
  - broker_safe: Optional[bool]               default None  -> block on None or False
  - execution_healthy: Optional[bool]         default None  -> block on None or False
  - model_healthy: Optional[bool]             default None  -> block on None or False
  - margin_safe: Optional[bool]               default None  -> block on None or False

Risk budgets are SEPARATED:
  - existing_daily_open_risk   (currently open risk attributable to daily budget)
  - existing_total_open_risk   (currently open risk attributable to total budget)
  - existing_combined_risk     (currently open risk attributable to combined cap)

Entry budgets:
  remaining_daily_entry_budget   = DAILY_BLOCK - daily_dd - existing_daily_open_risk
  remaining_total_entry_budget   = TOTAL_BLOCK - total_dd - existing_total_open_risk
  remaining_combined_budget      = MAX_COMBINED_RISK   - existing_combined_risk

Approved risk = min(
    proposed_risk_after_caps_and_modifiers,
    remaining_daily_entry_budget,
    remaining_total_entry_budget,
    remaining_combined_budget,
)

NEVER sends orders. NEVER creates tokens. NEVER trades.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
import math

# Daily DD stages
DAILY_CAUTION = 0.010
DAILY_RECOVERY = 0.013
DAILY_BLOCK = 0.016
DAILY_EMERGENCY = 0.018
DAILY_LIMIT = 0.020

# Total DD stages
TOTAL_RECOVERY = 0.040
TOTAL_CAPITAL_PRESERVATION = 0.055
TOTAL_BLOCK = 0.065
TOTAL_EMERGENCY = 0.072
TOTAL_LIMIT = 0.080

# Safe setup caps
RISK_CAP_A_PLUS = 0.003   # 0.30%
RISK_CAP_A = 0.0025       # 0.25%
RISK_CAP_B = 0.001        # 0.10%
RISK_CAP_C = 0.0           # 0%
MAX_COMBINED_RISK = 0.006  # 0.60%


@dataclass
class RiskGovernorInput:
    """All inputs required for risk governance.

    All safety flags default to None (unavailable) which forces fail-closed
    blocking. Callers MUST explicitly supply every safety state.
    """
    equity: float
    equity_peak: float
    daily_peak: float
    daily_start_equity: float
    proposed_risk: float
    setup_class: str
    # SEPARATED existing-open-risk fields — callers must populate all three
    existing_daily_open_risk: float = 0.0
    existing_total_open_risk: float = 0.0
    existing_combined_risk: float = 0.0
    # Legacy compat alias (existing_risk) — if set, treated as combined only
    existing_risk: float = 0.0
    loss_streak: int = 0
    regime_risk_modifier: float = 1.0
    broker_risk_modifier: float = 1.0
    # Safety states — None default = unavailable = block
    prop_risk_pass: Optional[bool] = None
    capital_protection_active: Optional[bool] = None
    broker_safe: Optional[bool] = None
    execution_healthy: Optional[bool] = None
    model_healthy: Optional[bool] = None
    margin_safe: Optional[bool] = None
    # External DD (prop firm daily/total) — None = unavailable = block
    external_daily_dd: Optional[float] = None
    external_total_dd: Optional[float] = None


@dataclass
class RiskGovernorOutput:
    approved_risk: float
    approved: bool
    block_reason: str
    daily_dd: float
    total_dd: float
    daily_stage: str
    total_stage: str
    risk_multiplier: float
    remaining_daily_budget: float
    remaining_total_budget: float
    remaining_combined_budget: float


def _classify_daily_stage(daily_dd: float) -> str:
    if daily_dd >= DAILY_LIMIT:
        return "limit"
    if daily_dd >= DAILY_EMERGENCY:
        return "emergency"
    if daily_dd >= DAILY_BLOCK:
        return "block"
    if daily_dd >= DAILY_RECOVERY:
        return "recovery"
    if daily_dd >= DAILY_CAUTION:
        return "caution"
    return "normal"


def _classify_total_stage(total_dd: float) -> str:
    if total_dd >= TOTAL_LIMIT:
        return "limit"
    if total_dd >= TOTAL_EMERGENCY:
        return "emergency"
    if total_dd >= TOTAL_BLOCK:
        return "block"
    if total_dd >= TOTAL_CAPITAL_PRESERVATION:
        return "capital_preservation"
    if total_dd >= TOTAL_RECOVERY:
        return "recovery"
    return "normal"


def govern_risk(inp: RiskGovernorInput) -> RiskGovernorOutput:
    """Canonical risk governor. Fail-closed on every missing/unsafe safety input."""
    # DD
    total_dd = (inp.equity_peak - inp.equity) / inp.equity_peak if inp.equity_peak > 0 else 0.0
    daily_dd = (inp.daily_peak - inp.equity) / inp.daily_peak if inp.daily_peak > 0 else 0.0
    daily_stage = _classify_daily_stage(daily_dd)
    total_stage = _classify_total_stage(total_dd)

    block_reasons: list[str] = []

    # Stage hard blocks
    if daily_stage in ("block", "emergency", "limit"):
        block_reasons.append(f"daily_{daily_stage}")
    if total_stage in ("block", "emergency", "limit"):
        block_reasons.append(f"total_{total_stage}")

    # External DD hard blocks (prop firm)
    if inp.external_daily_dd is None:
        block_reasons.append("external_daily_dd_unavailable")
    elif inp.external_daily_dd >= 0.020:
        block_reasons.append("external_daily_dd_breach")
    if inp.external_total_dd is None:
        block_reasons.append("external_total_dd_unavailable")
    elif inp.external_total_dd >= 0.080:
        block_reasons.append("external_total_dd_breach")

    # Loss streak
    if inp.loss_streak >= 4:
        block_reasons.append("loss_streak_4_plus")

    # Fail-closed safety inputs
    if inp.prop_risk_pass is None:
        block_reasons.append("prop_risk_unavailable")
    elif not inp.prop_risk_pass:
        block_reasons.append("prop_risk_fail")

    if inp.capital_protection_active is None:
        block_reasons.append("capital_protection_unavailable")
    elif inp.capital_protection_active:
        block_reasons.append("capital_protection_active")

    if inp.broker_safe is None:
        block_reasons.append("broker_safe_unavailable")
    elif not inp.broker_safe:
        block_reasons.append("broker_unsafe")

    if inp.execution_healthy is None:
        block_reasons.append("execution_health_unavailable")
    elif not inp.execution_healthy:
        block_reasons.append("execution_unhealthy")

    if inp.model_healthy is None:
        block_reasons.append("model_health_unavailable")
    elif not inp.model_healthy:
        block_reasons.append("model_unhealthy")

    if inp.margin_safe is None:
        block_reasons.append("margin_safe_unavailable")
    elif not inp.margin_safe:
        block_reasons.append("margin_unsafe")

    if block_reasons:
        return RiskGovernorOutput(
            approved_risk=0.0, approved=False,
            block_reason="; ".join(block_reasons),
            daily_dd=daily_dd, total_dd=total_dd,
            daily_stage=daily_stage, total_stage=total_stage,
            risk_multiplier=0.0,
            remaining_daily_budget=0.0,
            remaining_total_budget=0.0,
            remaining_combined_budget=0.0,
        )

    # Loss streak multiplier
    if inp.loss_streak >= 3:
        loss_mult = 0.50
    elif inp.loss_streak >= 2:
        loss_mult = 0.75
    else:
        loss_mult = 1.0

    # Stage-based multiplier
    stage_mult = 1.0
    if daily_stage == "caution":
        stage_mult = min(stage_mult, 0.75)
    elif daily_stage == "recovery":
        stage_mult = min(stage_mult, 0.50)
    if total_stage == "recovery":
        stage_mult = min(stage_mult, 0.50)
    elif total_stage == "capital_preservation":
        stage_mult = min(stage_mult, 0.25)

    # Setup class cap
    setup_caps = {"A_PLUS": RISK_CAP_A_PLUS, "A": RISK_CAP_A, "B": RISK_CAP_B, "C": RISK_CAP_C}
    cap = setup_caps.get(inp.setup_class, 0.0)

    risk_mult = loss_mult * stage_mult * inp.regime_risk_modifier * inp.broker_risk_modifier
    proposed = min(inp.proposed_risk, cap) * risk_mult

    # Backfill existing_combined_risk from legacy alias when caller didn't separate
    existing_daily = inp.existing_daily_open_risk
    existing_total = inp.existing_total_open_risk
    existing_combined = inp.existing_combined_risk if inp.existing_combined_risk > 0 else inp.existing_risk

    remaining_daily = max(0.0, DAILY_BLOCK - daily_dd - existing_daily)
    remaining_total = max(0.0, TOTAL_BLOCK - total_dd - existing_total)
    remaining_combined = max(0.0, MAX_COMBINED_RISK - existing_combined)

    proposed = min(proposed, remaining_daily, remaining_total, remaining_combined)

    # Round down to 4 decimal places
    proposed = math.floor(proposed * 10000) / 10000

    if proposed <= 0:
        return RiskGovernorOutput(
            approved_risk=0.0, approved=False,
            block_reason="risk_below_zero_after_clamp",
            daily_dd=daily_dd, total_dd=total_dd,
            daily_stage=daily_stage, total_stage=total_stage,
            risk_multiplier=risk_mult,
            remaining_daily_budget=remaining_daily,
            remaining_total_budget=remaining_total,
            remaining_combined_budget=remaining_combined,
        )

    return RiskGovernorOutput(
        approved_risk=proposed, approved=True,
        block_reason="",
        daily_dd=daily_dd, total_dd=total_dd,
        daily_stage=daily_stage, total_stage=total_stage,
        risk_multiplier=risk_mult,
        remaining_daily_budget=remaining_daily,
        remaining_total_budget=remaining_total,
        remaining_combined_budget=remaining_combined,
    )


__all__ = [
    "RiskGovernorInput", "RiskGovernorOutput", "govern_risk",
    "DAILY_CAUTION", "DAILY_RECOVERY", "DAILY_BLOCK", "DAILY_EMERGENCY", "DAILY_LIMIT",
    "TOTAL_RECOVERY", "TOTAL_CAPITAL_PRESERVATION", "TOTAL_BLOCK", "TOTAL_EMERGENCY", "TOTAL_LIMIT",
    "RISK_CAP_A_PLUS", "RISK_CAP_A", "RISK_CAP_B", "RISK_CAP_C", "MAX_COMBINED_RISK",
]
