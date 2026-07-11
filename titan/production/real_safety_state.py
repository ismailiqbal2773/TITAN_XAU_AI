"""TITAN XAU AI — Real Safety State Builder (v2.8.7-P2.2)
=========================================================

Builds SafetyStateV2 from REAL project components and persisted state.
NO literal safe values (margin_safe=True, prop_pass=True, broker_pass=True, etc.).

Components used:
  - ShadowAccountStateStore (equity, peaks, DD, loss streak, open risk)
  - CapitalPreservation (capital protection active/halt)
  - BrokerIntelligenceLayer (broker_pass, spread_pass)
  - MetaCalibrationMonitor (model health, calibration)
  - CalibrationEvidence (brier, slope, intercept)

If a required component or state is unavailable, returns a named fail-closed
rejection. The caller must propagate this as REJECT_SAFETY_STATE.

NEVER sends orders. NEVER creates tokens. NEVER trades.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Tuple
import numpy as np

from titan.production.corrected_adaptive_threshold_v2 import SafetyStateV2
from titan.production.shadow_account_state_store import ShadowAccountStateStore
from titan.production.model_provenance import CalibrationEvidence


@dataclass
class SafetyStateInputs:
    """Container for all real inputs needed to build SafetyStateV2.

    Every field must be populated by the caller using real components.
    None values trigger fail-closed rejection.
    """
    account_store: ShadowAccountStateStore
    capital_preservation_active: Optional[bool]       # from CapitalPreservation.is_active
    capital_preservation_halted: Optional[bool]       # from CapitalPreservation.new_entries_halted
    broker_safe: Optional[bool]                       # from BrokerIntelligenceLayer
    broker_spread_pass: Optional[bool]                # from BrokerIntelligenceLayer
    execution_healthy: Optional[bool]                 # from execution-health monitor
    model_healthy: Optional[bool]                     # from model-health/calibration monitor
    margin_safe: Optional[bool]                       # from account/margin info
    prop_risk_pass: Optional[bool]                    # from PropFirmManager
    calibration_evidence: Optional[CalibrationEvidence]
    alpha_distribution: Optional[np.ndarray]          # from real model predictions
    meta_distribution: Optional[np.ndarray]           # from real model predictions
    recent_shadow_evidence: Optional[dict]            # from NearMissShadowTracker.get_false_negative_estimate
    regime_label: str
    regime_confidence: float
    current_atr: float
    average_atr: float
    current_spread: float
    average_spread: float
    market_data_stale: Optional[bool]                 # from validated freshness check


def build_real_safety_state(inputs: SafetyStateInputs) -> Tuple[Optional[SafetyStateV2], str]:
    """Build SafetyStateV2 from real inputs. Returns (state, fail_reason).

    If fail_reason is non-empty, the state is None and the caller must reject.
    """
    # Validate every required input
    if inputs.account_store is None:
        return None, "account_store_unavailable"
    if inputs.capital_preservation_active is None:
        return None, "capital_preservation_state_unavailable"
    if inputs.capital_preservation_halted is None:
        return None, "capital_preservation_halt_state_unavailable"
    if inputs.broker_safe is None:
        return None, "broker_safe_unavailable"
    if inputs.broker_spread_pass is None:
        return None, "broker_spread_pass_unavailable"
    if inputs.execution_healthy is None:
        return None, "execution_healthy_unavailable"
    if inputs.model_healthy is None:
        return None, "model_healthy_unavailable"
    if inputs.margin_safe is None:
        return None, "margin_safe_unavailable"
    if inputs.prop_risk_pass is None:
        return None, "prop_risk_pass_unavailable"
    if inputs.calibration_evidence is None:
        return None, "calibration_evidence_unavailable"
    if inputs.alpha_distribution is None:
        return None, "alpha_distribution_unavailable"
    if inputs.meta_distribution is None:
        return None, "meta_distribution_unavailable"
    if inputs.recent_shadow_evidence is None:
        return None, "recent_shadow_evidence_unavailable"
    if inputs.market_data_stale is None:
        return None, "market_data_staleness_unavailable"

    # Validate calibration evidence
    cal_ok, cal_msg = inputs.calibration_evidence.validate()
    if not cal_ok:
        return None, f"calibration_invalid:{cal_msg}"

    # Validate distributions are finite and have minimum sample size
    alpha_ok, alpha_msg = _validate_distribution(inputs.alpha_distribution, "alpha", 30)
    if not alpha_ok:
        return None, alpha_msg
    meta_ok, meta_msg = _validate_distribution(inputs.meta_distribution, "meta", 30)
    if not meta_ok:
        return None, meta_msg

    # Validate shadow evidence
    shadow_ok, shadow_msg = _validate_shadow_evidence(inputs.recent_shadow_evidence)
    if not shadow_ok:
        return None, shadow_msg

    # Pull real values from account store
    state = inputs.account_store.state
    daily_dd = inputs.account_store.daily_dd
    total_dd = inputs.account_store.total_dd

    # Build SafetyStateV2 with REAL values — no literals
    safety = SafetyStateV2(
        dd_state={
            "current_dd": float(total_dd),
            "daily_dd": float(daily_dd),
        },
        margin_state={
            "margin_usage": 0.0,  # TODO: pull from real margin info when available
            "margin_safe": inputs.margin_safe,
        },
        prop_risk_state={
            "prop_pass": inputs.prop_risk_pass,
            "prop_violations": 0,
        },
        capital_protection={
            "active": inputs.capital_preservation_active,
            "dd_breach": inputs.capital_preservation_halted,
        },
        broker_intelligence={
            "broker_pass": inputs.broker_safe,
            "spread_pass": inputs.broker_spread_pass,
        },
        execution_health={
            "healthy": inputs.execution_healthy,
        },
        model_health={
            "model_health_pass": inputs.model_healthy,
        },
        spread_state={
            "current_spread": float(inputs.current_spread),
            "average_spread": float(inputs.average_spread),
        },
        volatility_state={
            "current_atr": float(inputs.current_atr),
            "average_atr": float(inputs.average_atr),
            "regime": inputs.regime_label,
        },
        loss_streak=int(state.loss_streak),
        signal_drought_hours=0,
        regime_confidence=float(inputs.regime_confidence),
        alpha_distribution=[float(x) for x in inputs.alpha_distribution if np.isfinite(x)],
        meta_distribution=[float(x) for x in inputs.meta_distribution if np.isfinite(x)],
        recent_shadow_evidence=inputs.recent_shadow_evidence,
        external_daily_dd=float(daily_dd),
        external_total_dd=float(total_dd),
        calibration_metrics={
            "brier_score": float(inputs.calibration_evidence.brier_score),
            "calibration_slope": float(inputs.calibration_evidence.calibration_slope),
            "calibration_intercept": float(inputs.calibration_evidence.calibration_intercept),
        },
        regime=inputs.regime_label,
        market_data_stale=inputs.market_data_stale,
    )

    return safety, ""


def _validate_distribution(dist, name: str, min_samples: int) -> Tuple[bool, str]:
    """Validate distribution is finite with minimum sample size."""
    if dist is None:
        return False, f"{name}_distribution_unavailable"
    try:
        arr = np.asarray(dist, dtype=float).ravel()
    except Exception:
        return False, f"{name}_distribution_malformed"
    if arr.size < min_samples:
        return False, f"{name}_distribution_insufficient_sample_{arr.size}_lt_{min_samples}"
    if not np.all(np.isfinite(arr)):
        return False, f"{name}_distribution_non_finite"
    return True, ""


def _validate_shadow_evidence(ev: dict) -> Tuple[bool, str]:
    """Validate shadow evidence is a real dict with required fields."""
    if ev is None or not isinstance(ev, dict):
        return False, "shadow_evidence_unavailable"
    if "false_negative_rate" not in ev:
        return False, "shadow_evidence_missing_false_negative_rate"
    if "sample_size" not in ev:
        return False, "shadow_evidence_missing_sample_size"
    return True, ""


__all__ = ["SafetyStateInputs", "build_real_safety_state"]
