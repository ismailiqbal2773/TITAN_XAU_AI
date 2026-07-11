"""TITAN XAU AI — Corrected Adaptive Threshold V2 (Sprint v2.8.7-P1.1)
======================================================================
DG9: Hardened with loss-streak risk reduction, structured validation,
real journal interface, no raw spread>0.5 logic.
NEVER sends orders. NEVER creates tokens. NEVER trades.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, List, Callable
from datetime import datetime, timezone
import numpy as np


ALPHA_MIN = 0.48; ALPHA_MAX = 0.60; META_MIN = 0.48; META_MAX = 0.60
ALPHA_DEFAULT = 0.50; META_DEFAULT = 0.50


def compute_loss_streak_risk(loss_streak: int) -> float:
    """Compute risk multiplier based on consecutive losses.
    2 losses: 0.75, 3: 0.50, 4+: 0.0 (no new entries).
    """
    if loss_streak >= 4:
        return 0.0
    elif loss_streak == 3:
        return 0.50
    elif loss_streak == 2:
        return 0.75
    return 1.0


@dataclass
class SafetyStateV2:
    dd_state: dict
    margin_state: dict
    prop_risk_state: dict
    capital_protection: dict
    broker_intelligence: dict
    execution_health: dict
    model_health: dict
    spread_state: dict
    volatility_state: dict
    loss_streak: int
    signal_drought_hours: int
    regime_confidence: float
    alpha_distribution: list
    meta_distribution: list
    recent_shadow_evidence: dict


@dataclass
class CorrectedThresholdStateV2:
    alpha_threshold_effective: float
    meta_threshold_effective: float
    risk_multiplier: float
    allow_B_class_shadow: bool
    allow_A_class_shadow: bool
    block_reason: str
    policy_mode: str
    journal_entries: list


def compute_adaptive_threshold_v2(safety: SafetyStateV2, journal_callback=None) -> CorrectedThresholdStateV2:
    """Compute adaptive thresholds with all DG9 hardening.
    
    Args:
        safety: SafetyStateV2 with all required safety states.
        journal_callback: Optional callable that receives each journal entry.
    """
    journal = []
    def _emit(entry):
        journal.append(entry)
        if journal_callback:
            journal_callback(entry)

    # DG9: Validate all SafetyState members
    required = {
        "dd_state": safety.dd_state, "margin_state": safety.margin_state,
        "prop_risk_state": safety.prop_risk_state, "capital_protection": safety.capital_protection,
        "broker_intelligence": safety.broker_intelligence, "execution_health": safety.execution_health,
        "model_health": safety.model_health, "spread_state": safety.spread_state,
        "volatility_state": safety.volatility_state,
    }
    for name, state in required.items():
        if state is None or (isinstance(state, dict) and len(state) == 0):
            _emit({"change": "HARD_BLOCK", "reason": f"{name} unavailable or malformed"})
            return CorrectedThresholdStateV2(
                alpha_threshold_effective=ALPHA_MAX, meta_threshold_effective=META_MAX,
                risk_multiplier=0.0, allow_B_class_shadow=False, allow_A_class_shadow=False,
                block_reason=f"safety_state_unavailable:{name}", policy_mode="hard_block",
                journal_entries=journal,
            )

    alpha_eff = ALPHA_DEFAULT; meta_eff = META_DEFAULT
    risk_mult = 1.0; allow_B = True; allow_A = True
    block_reason = ""; mode = "default"

    # Extract safety — fail closed on None values
    broker_pass_val = safety.broker_intelligence.get("broker_pass")
    exec_healthy_val = safety.execution_health.get("healthy")
    model_healthy_val = safety.model_health.get("model_health_pass")
    margin_safe_val = safety.margin_state.get("margin_safe")
    prop_pass_val = safety.prop_risk_state.get("prop_pass")

    # None = unavailable → hard block
    if broker_pass_val is None or exec_healthy_val is None or model_healthy_val is None \
       or margin_safe_val is None or prop_pass_val is None:
        _emit({"change": "HARD_BLOCK", "reason": "safety_state_value_None"})
        return CorrectedThresholdStateV2(
            alpha_threshold_effective=ALPHA_MAX, meta_threshold_effective=META_MAX,
            risk_multiplier=0.0, allow_B_class_shadow=False, allow_A_class_shadow=False,
            block_reason="safety_value_none", policy_mode="hard_block",
            journal_entries=journal,
        )

    dd_safe = safety.dd_state.get("current_dd", 1.0) < 0.04
    daily_safe = safety.dd_state.get("daily_dd", 1.0) < 0.015
    margin_safe = margin_safe_val
    prop_pass = prop_pass_val
    cap_active = safety.capital_protection.get("active", True)
    cap_breach = safety.capital_protection.get("dd_breach", True)
    broker_pass = broker_pass_val
    exec_healthy = exec_healthy_val
    model_healthy = model_healthy_val

    # DG9: Loss-streak risk reduction
    loss_streak_mult = compute_loss_streak_risk(safety.loss_streak)
    risk_mult = min(risk_mult, loss_streak_mult)
    if safety.loss_streak >= 4:
        _emit({"change": "HARD_BLOCK", "reason": "loss_streak_4_plus"})
        return CorrectedThresholdStateV2(
            alpha_threshold_effective=ALPHA_MAX, meta_threshold_effective=META_MAX,
            risk_multiplier=0.0, allow_B_class_shadow=False, allow_A_class_shadow=False,
            block_reason="loss_streak_4_plus", policy_mode="hard_block",
            journal_entries=journal,
        )

    # Hard block
    if not (margin_safe and prop_pass and broker_pass and exec_healthy and model_healthy
            and not cap_active and not cap_breach):
        reasons = []
        if not margin_safe: reasons.append("margin_unsafe")
        if not prop_pass: reasons.append("prop_fail")
        if not broker_pass: reasons.append("broker_fail")
        if not exec_healthy: reasons.append("exec_unhealthy")
        if not model_healthy: reasons.append("model_unhealthy")
        if cap_active: reasons.append("cap_protection_active")
        if cap_breach: reasons.append("dd_breach")
        _emit({"change": "HARD_BLOCK", "reason": "; ".join(reasons)})
        return CorrectedThresholdStateV2(
            alpha_threshold_effective=ALPHA_MAX, meta_threshold_effective=META_MAX,
            risk_multiplier=0.0, allow_B_class_shadow=False, allow_A_class_shadow=False,
            block_reason="; ".join(reasons), policy_mode="hard_block",
            journal_entries=journal,
        )

    # Tightening
    vol_abnormal = safety.volatility_state.get("regime", "UNKNOWN") in (
        "VOLATILITY_COMPRESSION", "BREAKOUT_EXPANSION", "SPREAD_STRESS", "UNKNOWN_UNSAFE")
    dd_warning = safety.dd_state.get("current_dd", 0) > 0.05
    market_choppy = safety.regime_confidence < 0.3
    # DG9: No raw spread>0.5 — use normalized broker state
    spread_state_pass = safety.broker_intelligence.get("spread_pass", False)
    if not spread_state_pass or vol_abnormal or dd_warning or market_choppy:
        alpha_eff = min(ALPHA_MAX, alpha_eff + 0.05)
        meta_eff = min(META_MAX, meta_eff + 0.05)
        mode = "tightened"
        if dd_warning: block_reason = "dd_warning"
        elif vol_abnormal: block_reason = "vol_abnormal"
        elif not spread_state_pass: block_reason = "spread_state_fail"
        else: block_reason = "market_choppy"

    # Relaxation (not drought alone)
    drought = safety.signal_drought_hours >= 12
    false_neg = safety.recent_shadow_evidence.get("false_negative_rate", 0)
    shadow_sample = safety.recent_shadow_evidence.get("sample_size", 0)
    has_evidence = false_neg > 0.15 and shadow_sample >= 10
    if (dd_safe and daily_safe and margin_safe and prop_pass and
        spread_state_pass and not vol_abnormal and not dd_warning and
        not market_choppy and has_evidence and drought and safety.loss_streak < 2):
        alpha_eff = max(ALPHA_MIN, alpha_eff - 0.02)
        meta_eff = max(META_MIN, meta_eff - 0.02)
        mode = "relaxed"
        _emit({"change": "RELAX", "reason": "drought+evidence+all_safe"})

    alpha_eff = max(ALPHA_MIN, min(ALPHA_MAX, alpha_eff))
    meta_eff = max(META_MIN, min(META_MAX, meta_eff))

    # Always journal the final decision
    _emit({"change": "DECISION", "mode": mode, "alpha": alpha_eff, "meta": meta_eff,
           "risk_mult": risk_mult, "block_reason": block_reason})

    return CorrectedThresholdStateV2(
        alpha_threshold_effective=round(alpha_eff, 4),
        meta_threshold_effective=round(meta_eff, 4),
        risk_multiplier=round(risk_mult, 4),
        allow_B_class_shadow=allow_B, allow_A_class_shadow=allow_A,
        block_reason=block_reason, policy_mode=mode,
        journal_entries=journal,
    )


__all__ = [
    "SafetyStateV2", "CorrectedThresholdStateV2", "compute_adaptive_threshold_v2",
    "compute_loss_streak_risk",
    "ALPHA_MIN", "ALPHA_MAX", "META_MIN", "META_MAX",
]
