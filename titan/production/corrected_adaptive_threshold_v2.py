"""TITAN XAU AI — Corrected Adaptive Threshold V2 (FINAL Sprint v2.8.7-P2.0)
==============================================================================

Finalized adaptive policy with explicit hard-block conditions and structured
journal entries.

Hard-blocks (no relaxation permitted) when any of:
  - daily_dd >= 0.016
  - total_dd >= 0.065
  - daily external DD >= 0.020
  - total external DD >= 0.080
  - loss_streak >= 4
  - stale market data
  - broker unsafe
  - execution unhealthy
  - model unhealthy
  - calibration invalid
  - margin unsafe
  - prop risk fail
  - capital protection active

Validation:
  - alpha distribution is finite with minimum sample size
  - meta distribution is finite with minimum sample size
  - calibration metrics exist and within configured limits
  - recent shadow evidence has valid sample size

Journal callback entry contains:
  timestamp, decision_id, correlation_id,
  old/new alpha threshold, old/new meta threshold, old/new risk multiplier,
  evidence, block_reason, regime, loss_streak

NEVER sends orders. NEVER creates tokens. NEVER trades.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, List, Callable, Any
from datetime import datetime, timezone
import math
import uuid
import numpy as np


ALPHA_MIN = 0.48; ALPHA_MAX = 0.60
META_MIN = 0.48; META_MAX = 0.60
ALPHA_DEFAULT = 0.50; META_DEFAULT = 0.50

# Hard-block thresholds (FINAL)
DAILY_DD_HARD_BLOCK = 0.016
TOTAL_DD_HARD_BLOCK = 0.065
EXTERNAL_DAILY_DD_HARD_BLOCK = 0.020
EXTERNAL_TOTAL_DD_HARD_BLOCK = 0.080
LOSS_STREAK_HARD_BLOCK = 4

MIN_ALPHA_SAMPLE = 30
MIN_META_SAMPLE = 30
MIN_SHADOW_SAMPLE = 10


def compute_loss_streak_risk(loss_streak: int) -> float:
    """2 losses: 0.75, 3: 0.50, 4+: 0.0."""
    if loss_streak >= 4:
        return 0.0
    if loss_streak == 3:
        return 0.50
    if loss_streak == 2:
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
    # New explicit fields for hard-block validation
    external_daily_dd: Optional[float] = None
    external_total_dd: Optional[float] = None
    calibration_metrics: Optional[dict] = None
    regime: str = "UNKNOWN"
    market_data_stale: Optional[bool] = None


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


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _validate_distribution(dist: Any, name: str, min_samples: int) -> tuple[bool, str]:
    """Validate that distribution is finite and has minimum sample size."""
    if dist is None:
        return False, f"{name}_unavailable"
    try:
        arr = np.asarray(dist, dtype=float).ravel()
    except Exception:
        return False, f"{name}_malformed"
    if arr.size < min_samples:
        return False, f"{name}_insufficient_sample_{arr.size}_lt_{min_samples}"
    if not np.all(np.isfinite(arr)):
        return False, f"{name}_non_finite"
    return True, ""


def _validate_calibration(cal: Optional[dict]) -> tuple[bool, str]:
    """Validate calibration metrics exist and within configured limits."""
    if cal is None:
        return False, "calibration_unavailable"
    if not isinstance(cal, dict) or len(cal) == 0:
        return False, "calibration_empty"
    # Required fields (loosely defined; brokers can extend)
    required_fields = ["brier_score", "calibration_slope"]
    for f in required_fields:
        if f not in cal:
            return False, f"calibration_missing_{f}"
    brier = cal.get("brier_score")
    slope = cal.get("calibration_slope")
    if not isinstance(brier, (int, float)) or not isinstance(slope, (int, float)):
        return False, "calibration_non_numeric"
    if not math.isfinite(brier) or not math.isfinite(slope):
        return False, "calibration_non_finite"
    # v2.8.7-P2.3: Hard acceptance — slope must be in [0.50, 2.00]
    if brier > 0.33:
        return False, f"REJECT_CALIBRATION:brier_{brier:.3f}_exceeds_0.33"
    if slope < 0.50 or slope > 2.00:
        return False, f"REJECT_CALIBRATION:slope_{slope:.3f}_out_of_[0.50,2.00]"
    return True, ""


def _validate_shadow_evidence(ev: Optional[dict]) -> tuple[bool, str]:
    """Validate recent shadow evidence has valid sample size."""
    if ev is None or not isinstance(ev, dict):
        return False, "shadow_evidence_unavailable"
    sample_size = ev.get("sample_size", 0)
    if not isinstance(sample_size, (int, float)) or sample_size < 0:
        return False, "shadow_evidence_sample_invalid"
    # For relaxation we require MIN_SHADOW_SAMPLE; for non-relaxation 0 is acceptable.
    return True, ""


def compute_adaptive_threshold_v2(safety: SafetyStateV2, journal_callback: Optional[Callable] = None) -> CorrectedThresholdStateV2:
    """Finalized adaptive threshold policy with hard blocks and structured journaling."""
    journal: list = []
    decision_id = f"adap_{uuid.uuid4().hex[:12]}"
    correlation_id = f"corr_{uuid.uuid4().hex[:12]}"
    ts = _now_iso()

    def _emit(entry: dict):
        # Always include mandatory fields
        entry.setdefault("timestamp", ts)
        entry.setdefault("decision_id", decision_id)
        entry.setdefault("correlation_id", correlation_id)
        entry.setdefault("regime", safety.regime)
        entry.setdefault("loss_streak", safety.loss_streak)
        journal.append(entry)
        if journal_callback:
            try:
                journal_callback(entry)
            except Exception:
                pass

    def _hard_block(reason: str, evidence: List[str]) -> CorrectedThresholdStateV2:
        _emit({
            "change": "HARD_BLOCK",
            "reason": reason,
            "block_reason": reason,
            "evidence": evidence,
            "old_alpha_threshold": ALPHA_DEFAULT, "new_alpha_threshold": ALPHA_MAX,
            "old_meta_threshold": META_DEFAULT, "new_meta_threshold": META_MAX,
            "old_risk_multiplier": 1.0, "new_risk_multiplier": 0.0,
        })
        return CorrectedThresholdStateV2(
            alpha_threshold_effective=ALPHA_MAX, meta_threshold_effective=META_MAX,
            risk_multiplier=0.0, allow_B_class_shadow=False, allow_A_class_shadow=False,
            block_reason=reason, policy_mode="hard_block",
            journal_entries=journal,
        )

    # Validate all SafetyState members
    required = {
        "dd_state": safety.dd_state, "margin_state": safety.margin_state,
        "prop_risk_state": safety.prop_risk_state, "capital_protection": safety.capital_protection,
        "broker_intelligence": safety.broker_intelligence, "execution_health": safety.execution_health,
        "model_health": safety.model_health, "spread_state": safety.spread_state,
        "volatility_state": safety.volatility_state,
    }
    for name, state in required.items():
        if state is None or (isinstance(state, dict) and len(state) == 0):
            return _hard_block(f"safety_state_unavailable:{name}", [f"{name} was None or empty"])

    # Extract safety values — fail closed on None
    broker_pass_val = safety.broker_intelligence.get("broker_pass")
    exec_healthy_val = safety.execution_health.get("healthy")
    model_healthy_val = safety.model_health.get("model_health_pass")
    margin_safe_val = safety.margin_state.get("margin_safe")
    prop_pass_val = safety.prop_risk_state.get("prop_pass")
    cap_active_val = safety.capital_protection.get("active")
    cap_breach_val = safety.capital_protection.get("dd_breach")
    market_stale_val = safety.market_data_stale

    if (broker_pass_val is None or exec_healthy_val is None or model_healthy_val is None
            or margin_safe_val is None or prop_pass_val is None
            or cap_active_val is None or cap_breach_val is None):
        return _hard_block("safety_value_none", ["one or more safety values was None"])

    # Stale market data → hard block
    if market_stale_val is True:
        return _hard_block("market_data_stale", ["market_data_stale=True"])

    # Hard-block thresholds
    daily_dd = float(safety.dd_state.get("daily_dd", 1.0))
    current_dd = float(safety.dd_state.get("current_dd", 1.0))
    if daily_dd >= DAILY_DD_HARD_BLOCK:
        return _hard_block(f"daily_dd_{daily_dd:.4f}_>=_{DAILY_DD_HARD_BLOCK}",
                          [f"daily_dd={daily_dd:.4f}"])
    if current_dd >= TOTAL_DD_HARD_BLOCK:
        return _hard_block(f"total_dd_{current_dd:.4f}_>=_{TOTAL_DD_HARD_BLOCK}",
                          [f"total_dd={current_dd:.4f}"])

    # External DD hard-blocks
    if safety.external_daily_dd is not None and safety.external_daily_dd >= EXTERNAL_DAILY_DD_HARD_BLOCK:
        return _hard_block(f"external_daily_dd_{safety.external_daily_dd:.4f}_>=_{EXTERNAL_DAILY_DD_HARD_BLOCK}",
                          [f"external_daily_dd={safety.external_daily_dd:.4f}"])
    if safety.external_total_dd is not None and safety.external_total_dd >= EXTERNAL_TOTAL_DD_HARD_BLOCK:
        return _hard_block(f"external_total_dd_{safety.external_total_dd:.4f}_>=_{EXTERNAL_TOTAL_DD_HARD_BLOCK}",
                          [f"external_total_dd={safety.external_total_dd:.4f}"])

    # Loss streak hard-block
    if safety.loss_streak >= LOSS_STREAK_HARD_BLOCK:
        return _hard_block(f"loss_streak_{safety.loss_streak}_>=_{LOSS_STREAK_HARD_BLOCK}",
                          [f"loss_streak={safety.loss_streak}"])

    # Boolean hard-blocks
    if not broker_pass_val:
        return _hard_block("broker_unsafe", ["broker_pass=False"])
    if not exec_healthy_val:
        return _hard_block("execution_unhealthy", ["execution_health.healthy=False"])
    if not model_healthy_val:
        return _hard_block("model_unhealthy", ["model_health.model_health_pass=False"])
    if not margin_safe_val:
        return _hard_block("margin_unsafe", ["margin_state.margin_safe=False"])
    if not prop_pass_val:
        return _hard_block("prop_risk_fail", ["prop_risk_state.prop_pass=False"])
    if cap_active_val:
        return _hard_block("capital_protection_active", ["capital_protection.active=True"])
    if cap_breach_val:
        return _hard_block("dd_breach", ["capital_protection.dd_breach=True"])

    # Calibration validation
    cal_ok, cal_reason = _validate_calibration(safety.calibration_metrics)
    if not cal_ok:
        return _hard_block(cal_reason, [f"calibration_metrics={safety.calibration_metrics}"])

    # Distribution validation
    alpha_ok, alpha_reason = _validate_distribution(safety.alpha_distribution, "alpha_distribution", MIN_ALPHA_SAMPLE)
    if not alpha_ok:
        return _hard_block(alpha_reason, ["alpha_distribution insufficient or non-finite"])
    meta_ok, meta_reason = _validate_distribution(safety.meta_distribution, "meta_distribution", MIN_META_SAMPLE)
    if not meta_ok:
        return _hard_block(meta_reason, ["meta_distribution insufficient or non-finite"])

    # Shadow evidence validation
    shadow_ok, shadow_reason = _validate_shadow_evidence(safety.recent_shadow_evidence)
    if not shadow_ok:
        return _hard_block(shadow_reason, ["recent_shadow_evidence unavailable"])

    # All hard-blocks passed — proceed to tightening/relaxation
    alpha_eff = ALPHA_DEFAULT
    meta_eff = META_DEFAULT
    risk_mult = compute_loss_streak_risk(safety.loss_streak)
    block_reason = ""
    mode = "default"

    # Tightening
    vol_abnormal = safety.volatility_state.get("regime", "UNKNOWN") in (
        "VOLATILITY_COMPRESSION", "BREAKOUT_EXPANSION", "SPREAD_STRESS", "UNKNOWN_UNSAFE")
    dd_warning = current_dd > 0.05
    market_choppy = safety.regime_confidence < 0.3
    spread_state_pass = safety.broker_intelligence.get("spread_pass", False)
    if not spread_state_pass or vol_abnormal or dd_warning or market_choppy:
        old_alpha, old_meta = alpha_eff, meta_eff
        alpha_eff = min(ALPHA_MAX, alpha_eff + 0.05)
        meta_eff = min(META_MAX, meta_eff + 0.05)
        mode = "tightened"
        if dd_warning: block_reason = "dd_warning"
        elif vol_abnormal: block_reason = "vol_abnormal"
        elif not spread_state_pass: block_reason = "spread_state_fail"
        else: block_reason = "market_choppy"
        _emit({
            "change": "TIGHTEN",
            "old_alpha_threshold": old_alpha, "new_alpha_threshold": alpha_eff,
            "old_meta_threshold": old_meta, "new_meta_threshold": meta_eff,
            "old_risk_multiplier": risk_mult, "new_risk_multiplier": risk_mult,
            "block_reason": block_reason,
            "evidence": [f"reason={block_reason}"],
        })

    # Relaxation (not drought alone)
    drought = safety.signal_drought_hours >= 12
    false_neg = safety.recent_shadow_evidence.get("false_negative_rate", 0)
    shadow_sample = safety.recent_shadow_evidence.get("sample_size", 0)
    has_evidence = false_neg > 0.15 and shadow_sample >= MIN_SHADOW_SAMPLE
    dd_safe = current_dd < 0.04
    daily_safe = daily_dd < 0.015
    if (dd_safe and daily_safe and broker_pass_val and exec_healthy_val and model_healthy_val
            and margin_safe_val and prop_pass_val and not cap_active_val and not cap_breach_val
            and spread_state_pass and not vol_abnormal and not dd_warning
            and not market_choppy and has_evidence and drought and safety.loss_streak < 2):
        old_alpha, old_meta = alpha_eff, meta_eff
        alpha_eff = max(ALPHA_MIN, alpha_eff - 0.02)
        meta_eff = max(META_MIN, meta_eff - 0.02)
        mode = "relaxed"
        _emit({
            "change": "RELAX",
            "old_alpha_threshold": old_alpha, "new_alpha_threshold": alpha_eff,
            "old_meta_threshold": old_meta, "new_meta_threshold": meta_eff,
            "old_risk_multiplier": risk_mult, "new_risk_multiplier": risk_mult,
            "block_reason": "",
            "evidence": ["drought+evidence+all_safe"],
        })

    alpha_eff = max(ALPHA_MIN, min(ALPHA_MAX, alpha_eff))
    meta_eff = max(META_MIN, min(META_MAX, meta_eff))

    _emit({
        "change": "DECISION",
        "old_alpha_threshold": ALPHA_DEFAULT, "new_alpha_threshold": alpha_eff,
        "old_meta_threshold": META_DEFAULT, "new_meta_threshold": meta_eff,
        "old_risk_multiplier": 1.0, "new_risk_multiplier": risk_mult,
        "block_reason": block_reason,
        "evidence": [f"mode={mode}"],
    })

    return CorrectedThresholdStateV2(
        alpha_threshold_effective=round(alpha_eff, 4),
        meta_threshold_effective=round(meta_eff, 4),
        risk_multiplier=round(risk_mult, 4),
        allow_B_class_shadow=True, allow_A_class_shadow=True,
        block_reason=block_reason, policy_mode=mode,
        journal_entries=journal,
    )


__all__ = [
    "SafetyStateV2", "CorrectedThresholdStateV2", "compute_adaptive_threshold_v2",
    "compute_loss_streak_risk",
    "ALPHA_MIN", "ALPHA_MAX", "META_MIN", "META_MAX",
    "DAILY_DD_HARD_BLOCK", "TOTAL_DD_HARD_BLOCK",
    "EXTERNAL_DAILY_DD_HARD_BLOCK", "EXTERNAL_TOTAL_DD_HARD_BLOCK",
    "LOSS_STREAK_HARD_BLOCK",
]
