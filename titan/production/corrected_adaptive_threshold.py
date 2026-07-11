"""TITAN XAU AI — Corrected Adaptive Threshold Policy (Sprint v2.8.7-P1)
========================================================================
Fixes:
  - Removed hardcoded no_margin_risk=True, no_prop_risk=True placeholders
  - Accepts real structured safety inputs
  - Fails closed when safety state unavailable
  - Signal drought alone cannot relax thresholds
  - Journals every threshold change

NEVER sends orders. NEVER creates tokens. NEVER trades.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime, timezone
import numpy as np


# Hard limits
ALPHA_MIN = 0.48
ALPHA_MAX = 0.60
META_MIN = 0.48
META_MAX = 0.60
ALPHA_DEFAULT = 0.50
META_DEFAULT = 0.50

SIGNAL_DROUGHT_THRESHOLD_HOURS = 12


@dataclass
class SafetyState:
    """Real safety state from production systems. All must be provided."""
    dd_state: dict              # {"current_dd": float, "daily_dd": float}
    margin_state: dict          # {"margin_usage": float, "margin_safe": bool}
    prop_risk_state: dict       # {"prop_pass": bool, "prop_violations": int}
    capital_protection: dict    # {"active": bool, "dd_breach": bool}
    broker_intelligence: dict   # {"broker_pass": bool, "spread_pass": bool}
    execution_health: dict      # {"healthy": bool, "latency_ms": float}
    model_health: dict          # {"model_health_pass": bool}
    spread_state: dict          # {"current_spread": float, "average_spread": float}
    volatility_state: dict      # {"current_atr": float, "average_atr": float, "regime": str}
    loss_streak: int
    signal_drought_hours: int
    regime_confidence: float
    alpha_distribution: list
    meta_distribution: list
    recent_shadow_evidence: dict  # {"false_negative_rate": float, "sample_size": int}


@dataclass
class CorrectedThresholdState:
    """Corrected adaptive threshold state."""
    alpha_threshold_effective: float
    meta_threshold_effective: float
    risk_multiplier: float
    allow_B_class_shadow: bool
    allow_A_class_shadow: bool
    block_reason: str
    policy_mode: str  # "default", "relaxed", "tightened", "hard_block"
    journal_entries: list  # List of threshold change journals


def compute_corrected_adaptive_threshold(
    safety: SafetyState,
) -> CorrectedThresholdState:
    """Compute adaptive thresholds with real safety inputs.

    Rules:
      1. If any required safety state is unavailable → fail closed (hard_block)
      2. Signal drought alone CANNOT relax thresholds
      3. Relaxation requires: all safety pass + model calibration valid +
         shadow evidence of false negatives + spread/execution normal +
         DD safe + loss streak safe + regime stable
      4. Tightening on: spread high, vol abnormal, DD warning, market choppy
      5. All changes journaled with evidence
    """
    journal = []

    # === FAIL CLOSED: Check all required safety states ===
    required_states = {
        "dd_state": safety.dd_state,
        "margin_state": safety.margin_state,
        "prop_risk_state": safety.prop_risk_state,
        "capital_protection": safety.capital_protection,
        "broker_intelligence": safety.broker_intelligence,
        "execution_health": safety.execution_health,
        "model_health": safety.model_health,
    }

    for name, state in required_states.items():
        if state is None:
            journal.append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "change": "HARD_BLOCK",
                "reason": f"{name} unavailable — failing closed",
            })
            return CorrectedThresholdState(
                alpha_threshold_effective=ALPHA_MAX,
                meta_threshold_effective=META_MAX,
                risk_multiplier=0.0,
                allow_B_class_shadow=False,
                allow_A_class_shadow=False,
                block_reason=f"safety_state_unavailable:{name}",
                policy_mode="hard_block",
                journal_entries=journal,
            )

    # Default
    alpha_eff = ALPHA_DEFAULT
    meta_eff = META_DEFAULT
    risk_mult = 1.0
    allow_B = True
    allow_A = True
    block_reason = ""
    mode = "default"

    # === Extract safety values ===
    dd_safe = (safety.dd_state.get("current_dd", 1.0) < 0.04 and
               safety.dd_state.get("daily_dd", 1.0) < 0.015)
    margin_safe = safety.margin_state.get("margin_safe", False)
    prop_pass = safety.prop_risk_state.get("prop_pass", False)
    cap_prot_active = safety.capital_protection.get("active", True)
    cap_dd_breach = safety.capital_protection.get("dd_breach", True)
    broker_pass = safety.broker_intelligence.get("broker_pass", False)
    spread_pass = safety.broker_intelligence.get("spread_pass", False)
    exec_healthy = safety.execution_health.get("healthy", False)
    model_healthy = safety.model_health.get("model_health_pass", False)

    spread_high = safety.spread_state.get("current_spread", 1.0) > 0.5
    vol_abnormal = safety.volatility_state.get("regime", "UNKNOWN_UNSAFE") in (
        "VOLATILITY_COMPRESSION", "BREAKOUT_EXPANSION", "SPREAD_STRESS",
        "LIQUIDITY_STRESS", "UNKNOWN_UNSAFE"
    )
    dd_warning = safety.dd_state.get("current_dd", 0) > 0.05
    market_choppy = safety.regime_confidence < 0.3
    loss_streak_safe = safety.loss_streak < 3
    drought = safety.signal_drought_hours >= SIGNAL_DROUGHT_THRESHOLD_HOURS

    # Shadow evidence of false negatives
    false_neg_rate = safety.recent_shadow_evidence.get("false_negative_rate", 0)
    shadow_sample = safety.recent_shadow_evidence.get("sample_size", 0)
    has_false_neg_evidence = false_neg_rate > 0.15 and shadow_sample >= 10

    # === HARD BLOCK: Any safety failure ===
    if not (margin_safe and prop_pass and broker_pass and spread_pass and
            exec_healthy and model_healthy and not cap_prot_active and not cap_dd_breach):
        block_reasons = []
        if not margin_safe: block_reasons.append("margin_unsafe")
        if not prop_pass: block_reasons.append("prop_risk_fail")
        if not broker_pass: block_reasons.append("broker_fail")
        if not spread_pass: block_reasons.append("spread_fail")
        if not exec_healthy: block_reasons.append("exec_unhealthy")
        if not model_healthy: block_reasons.append("model_unhealthy")
        if cap_prot_active: block_reasons.append("capital_protection_active")
        if cap_dd_breach: block_reasons.append("dd_breach")

        journal.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "change": "HARD_BLOCK",
            "reason": "; ".join(block_reasons),
        })
        return CorrectedThresholdState(
            alpha_threshold_effective=ALPHA_MAX,
            meta_threshold_effective=META_MAX,
            risk_multiplier=0.0,
            allow_B_class_shadow=False,
            allow_A_class_shadow=False,
            block_reason="; ".join(block_reasons),
            policy_mode="hard_block",
            journal_entries=journal,
        )

    # === TIGHTENING (safety priority) ===
    if spread_high or vol_abnormal or dd_warning or market_choppy:
        alpha_eff = min(ALPHA_MAX, alpha_eff + 0.05)
        meta_eff = min(META_MAX, meta_eff + 0.05)
        mode = "tightened"
        if dd_warning:
            block_reason = "dd_warning"
        elif vol_abnormal:
            block_reason = "volatility_abnormal"
        elif spread_high:
            block_reason = "spread_high"
        else:
            block_reason = "market_choppy"
        journal.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "change": "TIGHTEN",
            "alpha": alpha_eff, "meta": meta_eff,
            "reason": block_reason,
        })

    # === RELAXATION (only if ALL conditions met, NOT drought alone) ===
    elif (dd_safe and margin_safe and prop_pass and loss_streak_safe and
          not spread_high and not vol_abnormal and not dd_warning and
          not market_choppy and has_false_neg_evidence and drought):

        alpha_eff = max(ALPHA_MIN, alpha_eff - 0.02)
        meta_eff = max(META_MIN, meta_eff - 0.02)
        mode = "relaxed"
        block_reason = ""
        journal.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "change": "RELAX",
            "alpha": alpha_eff, "meta": meta_eff,
            "reason": f"drought({safety.signal_drought_hours}h) + false_neg_rate({false_neg_rate:.2%}) + all_safety_pass",
        })

    # Hard clamp
    alpha_eff = max(ALPHA_MIN, min(ALPHA_MAX, alpha_eff))
    meta_eff = max(META_MIN, min(META_MAX, meta_eff))

    return CorrectedThresholdState(
        alpha_threshold_effective=round(alpha_eff, 4),
        meta_threshold_effective=round(meta_eff, 4),
        risk_multiplier=round(risk_mult, 4),
        allow_B_class_shadow=allow_B,
        allow_A_class_shadow=allow_A,
        block_reason=block_reason,
        policy_mode=mode,
        journal_entries=journal,
    )


__all__ = [
    "SafetyState", "CorrectedThresholdState", "compute_corrected_adaptive_threshold",
    "ALPHA_MIN", "ALPHA_MAX", "META_MIN", "META_MAX",
    "ALPHA_DEFAULT", "META_DEFAULT", "SIGNAL_DROUGHT_THRESHOLD_HOURS",
]
