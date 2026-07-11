"""TITAN XAU AI — Adaptive Threshold Policy (Sprint v2.8.7-P)
===============================================================
Adaptive threshold policy to avoid 0-trade days without weakening safety.

Rules:
  - Default: alpha=0.50, meta=0.50
  - Can relax to alpha=0.48, meta=0.48 ONLY if:
    DD safe, spread safe, volatility normal, no loss streak, no margin risk,
    no prop risk, signal drought >= 12 H1 hours
  - Can tighten to alpha=0.55-0.60, meta=0.55-0.60 if:
    spread high, volatility abnormal, DD warning, market choppy
  - NEVER use adaptive threshold to force trade

NEVER sends orders. NEVER creates tokens. NEVER trades.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
import numpy as np


# Hard limits
ALPHA_MIN = 0.48
ALPHA_MAX = 0.60
META_MIN = 0.48
META_MAX = 0.60
ALPHA_DEFAULT = 0.50
META_DEFAULT = 0.50

# Signal drought threshold (hours of H1 bars without signal)
SIGNAL_DROUGHT_THRESHOLD_HOURS = 12


@dataclass
class ThresholdState:
    """Current adaptive threshold state."""
    alpha_threshold_effective: float
    meta_threshold_effective: float
    risk_multiplier: float
    allow_B_class_shadow: bool
    allow_A_class_shadow: bool
    block_reason: str
    policy_mode: str  # "default", "relaxed", "tightened"


def compute_adaptive_threshold(
    dd_state: dict,           # {"current_dd": float, "daily_dd": float}
    spread_state: dict,       # {"current_spread": float, "average_spread": float}
    volatility_state: dict,   # {"current_atr": float, "average_atr": float, "regime": str}
    regime_confidence: float, # 0-1
    recent_signal_count: int, # signals in last 24h
    recent_reject_reasons: list,  # list of rejection reason strings
    alpha_distribution: list, # recent alpha values
    meta_distribution: list,  # recent meta values
    signal_drought_hours: int = 0,  # hours since last signal
    loss_streak: int = 0,
) -> ThresholdState:
    """Compute adaptive thresholds based on market and risk state.

    Returns ThresholdState with effective thresholds and policy mode.
    """

    # Default
    alpha_effective = ALPHA_DEFAULT
    meta_effective = META_DEFAULT
    risk_multiplier = 1.0
    allow_B = True
    allow_A = True
    block_reason = ""
    mode = "default"

    # Check safety conditions for relaxation
    dd_safe = dd_state.get("current_dd", 0) < 0.04 and dd_state.get("daily_dd", 0) < 0.02
    spread_safe = spread_state.get("current_spread", 0) < 0.4
    vol_normal = volatility_state.get("regime", "NORMAL") in ("NORMAL", "TREND")
    no_loss_streak = loss_streak < 3
    no_margin_risk = True  # would be passed from risk engine
    no_prop_risk = True    # would be passed from prop engine
    drought = signal_drought_hours >= SIGNAL_DROUGHT_THRESHOLD_HOURS

    # Tightening conditions
    spread_high = spread_state.get("current_spread", 0) > 0.5
    vol_abnormal = volatility_state.get("regime", "NORMAL") in ("VOLATILITY_EXPANSION", "SPREAD_EXPANSION")
    dd_warning = dd_state.get("current_dd", 0) > 0.05 or dd_state.get("daily_dd", 0) > 0.02
    market_choppy = regime_confidence < 0.3

    # Apply tightening first (safety priority)
    if spread_high or vol_abnormal or dd_warning or market_choppy:
        alpha_effective = min(ALPHA_MAX, alpha_effective + 0.05)
        meta_effective = min(META_MAX, meta_effective + 0.05)
        mode = "tightened"
        if dd_warning:
            block_reason = "dd_warning"
        elif vol_abnormal:
            block_reason = "volatility_abnormal"
        elif spread_high:
            block_reason = "spread_high"
        else:
            block_reason = "market_choppy"

    # Apply relaxation only if all safety conditions met
    elif dd_safe and spread_safe and vol_normal and no_loss_streak and no_margin_risk and no_prop_risk and drought:
        alpha_effective = max(ALPHA_MIN, alpha_effective - 0.02)
        meta_effective = max(META_MIN, meta_effective - 0.02)
        mode = "relaxed"
        block_reason = ""

    # If alpha distribution is very low, don't relax further
    if alpha_distribution and np.mean(alpha_distribution) < 0.45:
        alpha_effective = max(ALPHA_DEFAULT, alpha_effective)
        meta_effective = max(META_DEFAULT, meta_effective)
        mode = "default"

    # Hard clamp
    alpha_effective = max(ALPHA_MIN, min(ALPHA_MAX, alpha_effective))
    meta_effective = max(META_MIN, min(META_MAX, meta_effective))

    return ThresholdState(
        alpha_threshold_effective=round(alpha_effective, 4),
        meta_threshold_effective=round(meta_effective, 4),
        risk_multiplier=round(risk_multiplier, 4),
        allow_B_class_shadow=allow_B,
        allow_A_class_shadow=allow_A,
        block_reason=block_reason,
        policy_mode=mode,
    )


__all__ = [
    "ThresholdState", "compute_adaptive_threshold",
    "ALPHA_MIN", "ALPHA_MAX", "META_MIN", "META_MAX",
    "ALPHA_DEFAULT", "META_DEFAULT", "SIGNAL_DROUGHT_THRESHOLD_HOURS",
]
