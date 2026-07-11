"""TITAN XAU AI — Canonical Risk Governor (Sprint v2.8.7-P1.2)
==============================================================
One authoritative risk-stage governor used by:
  - corrected backtest
  - forward-shadow runtime
  - opportunity scorer
  - future execution path

Daily stages: caution 1.00%, recovery 1.30%, block 1.60%, emergency 1.80%, limit 2.00%
Total stages: recovery 4.00%, capital_preservation 5.50%, block 6.50%, emergency 7.20%, limit 8.00%

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
    """All inputs required for risk governance."""
    equity: float
    equity_peak: float           # Total HWM
    daily_peak: float            # Daily HWM
    daily_start_equity: float
    proposed_risk: float         # Risk % requested for this trade
    setup_class: str             # "A_PLUS", "A", "B", "C"
    existing_risk: float = 0.0   # Currently open risk
    loss_streak: int = 0
    regime_risk_modifier: float = 1.0
    broker_risk_modifier: float = 1.0
    prop_risk_pass: bool = True
    capital_protection_active: bool = False


@dataclass
class RiskGovernorOutput:
    """Result of risk governance."""
    approved_risk: float          # Final approved risk % (0 = blocked)
    approved: bool                # Whether trade is allowed
    block_reason: str             # "" if approved, reason if blocked
    daily_dd: float               # Current daily DD
    total_dd: float               # Current total DD
    daily_stage: str              # "normal", "caution", "recovery", "block", "emergency", "limit"
    total_stage: str              # Same stages
    risk_multiplier: float        # Applied multiplier
    remaining_daily_budget: float # Remaining daily risk budget
    remaining_total_budget: float # Remaining total risk budget


def govern_risk(inp: RiskGovernorInput) -> RiskGovernorOutput:
    """Canonical risk governor. Returns approved risk after all stage checks.

    Rules:
      - Risk reduction at caution (0.75x)
      - Stronger reduction at recovery (0.50x)
      - Zero risk at block stage
      - Zero risk during emergency/external breach
      - Approved risk clamped to remaining daily budget
      - Approved risk clamped to remaining total budget
      - Approved risk clamped to max combined 0.60%
      - 2 losses: 0.75x, 3 losses: 0.50x, 4+: blocked
      - Risk always rounds down
    """
    # Calculate DD
    total_dd = (inp.equity_peak - inp.equity) / inp.equity_peak if inp.equity_peak > 0 else 0
    daily_dd = (inp.daily_peak - inp.equity) / inp.daily_peak if inp.daily_peak > 0 else 0

    # Determine stages
    if daily_dd >= DAILY_LIMIT:
        daily_stage = "limit"
    elif daily_dd >= DAILY_EMERGENCY:
        daily_stage = "emergency"
    elif daily_dd >= DAILY_BLOCK:
        daily_stage = "block"
    elif daily_dd >= DAILY_RECOVERY:
        daily_stage = "recovery"
    elif daily_dd >= DAILY_CAUTION:
        daily_stage = "caution"
    else:
        daily_stage = "normal"

    if total_dd >= TOTAL_LIMIT:
        total_stage = "limit"
    elif total_dd >= TOTAL_EMERGENCY:
        total_stage = "emergency"
    elif total_dd >= TOTAL_BLOCK:
        total_stage = "block"
    elif total_dd >= TOTAL_CAPITAL_PRESERVATION:
        total_stage = "capital_preservation"
    elif total_dd >= TOTAL_RECOVERY:
        total_stage = "recovery"
    else:
        total_stage = "normal"

    # Hard blocks
    block_reasons = []

    if daily_stage in ("block", "emergency", "limit"):
        block_reasons.append(f"daily_{daily_stage}")
    if total_stage in ("block", "emergency", "limit"):
        block_reasons.append(f"total_{total_stage}")
    if inp.capital_protection_active:
        block_reasons.append("capital_protection_active")
    if not inp.prop_risk_pass:
        block_reasons.append("prop_risk_fail")
    if inp.loss_streak >= 4:
        block_reasons.append("loss_streak_4_plus")

    if block_reasons:
        return RiskGovernorOutput(
            approved_risk=0.0, approved=False,
            block_reason="; ".join(block_reasons),
            daily_dd=daily_dd, total_dd=total_dd,
            daily_stage=daily_stage, total_stage=total_stage,
            risk_multiplier=0.0,
            remaining_daily_budget=0.0, remaining_total_budget=0.0,
        )

    # Loss streak multiplier
    if inp.loss_streak >= 3:
        loss_mult = 0.50
    elif inp.loss_streak >= 2:
        loss_mult = 0.75
    else:
        loss_mult = 1.0

    # Stage-based multiplier
    if daily_stage == "caution":
        stage_mult = 0.75
    elif daily_stage == "recovery":
        stage_mult = 0.50
    else:
        stage_mult = 1.0

    if total_stage == "recovery":
        stage_mult = min(stage_mult, 0.50)
    elif total_stage == "capital_preservation":
        stage_mult = min(stage_mult, 0.25)

    # Setup class cap
    setup_caps = {"A_PLUS": RISK_CAP_A_PLUS, "A": RISK_CAP_A, "B": RISK_CAP_B, "C": RISK_CAP_C}
    cap = setup_caps.get(inp.setup_class, 0.0)

    # Apply modifiers
    risk_mult = loss_mult * stage_mult * inp.regime_risk_modifier * inp.broker_risk_modifier
    proposed = min(inp.proposed_risk, cap) * risk_mult

    # Clamp to remaining budgets
    remaining_daily = max(0, DAILY_LIMIT - daily_dd)
    remaining_total = max(0, TOTAL_LIMIT - total_dd)
    proposed = min(proposed, remaining_daily, remaining_total)

    # Clamp to max combined
    proposed = min(proposed, MAX_COMBINED_RISK - inp.existing_risk)

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
        )

    return RiskGovernorOutput(
        approved_risk=proposed, approved=True,
        block_reason="",
        daily_dd=daily_dd, total_dd=total_dd,
        daily_stage=daily_stage, total_stage=total_stage,
        risk_multiplier=risk_mult,
        remaining_daily_budget=remaining_daily,
        remaining_total_budget=remaining_total,
    )


__all__ = [
    "RiskGovernorInput", "RiskGovernorOutput", "govern_risk",
    "DAILY_CAUTION", "DAILY_RECOVERY", "DAILY_BLOCK", "DAILY_EMERGENCY", "DAILY_LIMIT",
    "TOTAL_RECOVERY", "TOTAL_CAPITAL_PRESERVATION", "TOTAL_BLOCK", "TOTAL_EMERGENCY", "TOTAL_LIMIT",
    "RISK_CAP_A_PLUS", "RISK_CAP_A", "RISK_CAP_B", "RISK_CAP_C", "MAX_COMBINED_RISK",
]
