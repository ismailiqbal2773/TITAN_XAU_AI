"""TITAN XAU AI - CEO AI Governance / Meta Decision Layer (Sprint v2.8.5-C)
============================================================================

Minimal production-safe CEO AI Governance layer that sits ABOVE the
alpha/regime entry decision and BELOW the execution token gate.

Architecture position:
  FeatureStream
  -> Regime/Context Intelligence
  -> 3 AI Expert Models (XGBoost alpha, LSTM sequential, Transformer regime)
  -> Meta-label / LogisticRegression quality filter
  -> ** CEO AI Governance / Meta Decision Layer **  (THIS MODULE)
  -> Risk + Prop + Broker + Geometry Gates
  -> Supervised Token-Gated Execution
  -> AI Exit + Recovery + Capital Protection

The CEO AI Governance layer receives:
  - regime/context state
  - XGB alpha direction/confidence
  - LSTM sequential confidence (or unavailable status)
  - Transformer regime classification (or unavailable status)
  - Meta-label / LogisticRegression quality score
  - spread/slippage/broker state
  - prop profile/risk state
  - capital protection state
  - model health state
  - execution geometry state

It outputs a final decision object:
  - final_decision: PASS / BLOCKED
  - allowed_to_trade: bool
  - decision_confidence: float [0.0, 1.0]
  - risk_multiplier: float (1.0 default, never > 1.0)
  - blockers: list of str
  - warnings: list of str
  - reasoning_codes: list of str

Hard rules (NEVER violated):
  - No MT5 calls
  - No token creation
  - No position modification
  - No override of hard gates
  - No forced trade
  - No risk increase above current cap (risk_multiplier <= 1.0)
  - Execution must not proceed unless CEO governance allowed_to_trade=true
    AND all hard gates pass
  - No martingale / grid / averaging / loss multiplier

Journal event: CEO_AI_DECISION
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass
class CEOAIDecision:
    """CEO AI Governance decision object."""
    timestamp_utc: str = ""
    final_decision: str = "BLOCKED"  # PASS | BLOCKED
    allowed_to_trade: bool = False
    decision_confidence: float = 0.0
    risk_multiplier: float = 1.0  # never > 1.0
    blockers: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    reasoning_codes: list = field(default_factory=list)
    # Input states received
    regime_state: dict = field(default_factory=dict)
    xgb_alpha: dict = field(default_factory=dict)
    lstm_confidence: dict = field(default_factory=dict)  # or unavailable
    transformer_regime: dict = field(default_factory=dict)  # or unavailable
    meta_label_quality: dict = field(default_factory=dict)
    broker_state: dict = field(default_factory=dict)
    prop_risk_state: dict = field(default_factory=dict)
    capital_protection_state: dict = field(default_factory=dict)
    model_health_state: dict = field(default_factory=dict)
    geometry_state: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "timestamp_utc": self.timestamp_utc,
            "final_decision": self.final_decision,
            "allowed_to_trade": self.allowed_to_trade,
            "decision_confidence": self.decision_confidence,
            "risk_multiplier": self.risk_multiplier,
            "blockers": self.blockers,
            "warnings": self.warnings,
            "reasoning_codes": self.reasoning_codes,
            "regime_state": self.regime_state,
            "xgb_alpha": self.xgb_alpha,
            "lstm_confidence": self.lstm_confidence,
            "transformer_regime": self.transformer_regime,
            "meta_label_quality": self.meta_label_quality,
            "broker_state": self.broker_state,
            "prop_risk_state": self.prop_risk_state,
            "capital_protection_state": self.capital_protection_state,
            "model_health_state": self.model_health_state,
            "geometry_state": self.geometry_state,
        }


def evaluate_ceo_decision(
    *,
    regime_state: Optional[dict] = None,
    xgb_alpha: Optional[dict] = None,
    lstm_confidence: Optional[dict] = None,
    transformer_regime: Optional[dict] = None,
    meta_label_quality: Optional[dict] = None,
    broker_state: Optional[dict] = None,
    prop_risk_state: Optional[dict] = None,
    capital_protection_state: Optional[dict] = None,
    model_health_state: Optional[dict] = None,
    geometry_state: Optional[dict] = None,
    alpha_confidence_threshold: float = 0.55,
    meta_label_threshold: float = 0.65,
) -> CEOAIDecision:
    """Evaluate the CEO AI Governance meta decision.

    NEVER calls mt5.order_send. NEVER creates token. NEVER modifies positions.
    NEVER forces a trade. NEVER increases risk above cap (risk_multiplier <= 1.0).

    The CEO layer consolidates all expert model inputs, hard-gate states, and
    capital protection state into a single PASS/BLOCKED decision. It does NOT
    override hard gates - if any hard gate fails, the CEO layer blocks.

    Args:
        regime_state: dict with detected, regime_value, confidence
        xgb_alpha: dict with direction, confidence, pass
        lstm_confidence: dict with confidence, available (or None if unavailable)
        transformer_regime: dict with regime_class, confidence, available (or None)
        meta_label_quality: dict with quality_score, pass
        broker_state: dict with broker_pass, spread_pass, slippage_pass
        prop_risk_state: dict with risk_pass, prop_funded_pass, max_positions_ok
        capital_protection_state: dict with capital_preservation_active, dd_breach
        model_health_state: dict with model_health_pass, failed_required
        geometry_state: dict with geometry_pass, actual_RR, minimum_RR
        alpha_confidence_threshold: minimum XGB confidence for PASS (default 0.55)
        meta_label_threshold: minimum meta-label quality for PASS (default 0.65)

    Returns:
        CEOAIDecision with final_decision, allowed_to_trade, etc.
    """
    ts = datetime.now(timezone.utc).isoformat()
    decision = CEOAIDecision(timestamp_utc=ts)

    # Store input states
    decision.regime_state = regime_state or {}
    decision.xgb_alpha = xgb_alpha or {}
    decision.lstm_confidence = lstm_confidence or {}
    decision.transformer_regime = transformer_regime or {}
    decision.meta_label_quality = meta_label_quality or {}
    decision.broker_state = broker_state or {}
    decision.prop_risk_state = prop_risk_state or {}
    decision.capital_protection_state = capital_protection_state or {}
    decision.model_health_state = model_health_state or {}
    decision.geometry_state = geometry_state or {}

    # === Fail-closed: if required inputs missing, BLOCK ===
    # Regime is required
    if not regime_state:
        decision.blockers.append("CEO_REGIME_MISSING: regime_state not provided")
        decision.reasoning_codes.append("REGIME_MISSING")
    elif not regime_state.get("detected", False):
        decision.blockers.append("CEO_REGIME_NOT_DETECTED: regime detected=False")
        decision.reasoning_codes.append("REGIME_NOT_DETECTED")

    # XGB alpha is required
    if not xgb_alpha:
        decision.blockers.append("CEO_XGB_ALPHA_MISSING: xgb_alpha not provided")
        decision.reasoning_codes.append("XGB_ALPHA_MISSING")
    else:
        xgb_pass = bool(xgb_alpha.get("pass", False))
        xgb_conf = float(xgb_alpha.get("confidence", 0) or 0)
        if not xgb_pass:
            decision.blockers.append(f"CEO_XGB_ALPHA_NOT_PASS: xgb pass=False, confidence={xgb_conf}")
            decision.reasoning_codes.append("XGB_ALPHA_NOT_PASS")
        if xgb_conf < alpha_confidence_threshold:
            decision.blockers.append(
                f"CEO_XGB_CONFIDENCE_LOW: {xgb_conf} < threshold={alpha_confidence_threshold}"
            )
            decision.reasoning_codes.append("XGB_CONFIDENCE_LOW")

    # Meta-label quality is required
    if not meta_label_quality:
        decision.blockers.append("CEO_META_LABEL_MISSING: meta_label_quality not provided")
        decision.reasoning_codes.append("META_LABEL_MISSING")
    else:
        ml_pass = bool(meta_label_quality.get("pass", False))
        ml_score = float(meta_label_quality.get("quality_score", 0) or 0)
        if not ml_pass:
            decision.blockers.append(f"CEO_META_LABEL_NOT_PASS: pass=False, score={ml_score}")
            decision.reasoning_codes.append("META_LABEL_NOT_PASS")
        if ml_score < meta_label_threshold:
            decision.blockers.append(
                f"CEO_META_LABEL_QUALITY_LOW: {ml_score} < threshold={meta_label_threshold}"
            )
            decision.reasoning_codes.append("META_LABEL_QUALITY_LOW")

    # LSTM is advisory (not blocking if unavailable)
    if lstm_confidence is None:
        decision.warnings.append("CEO_LSTM_UNAVAILABLE: LSTM sequential confidence not provided (advisory)")
        decision.reasoning_codes.append("LSTM_UNAVAILABLE")
    elif not lstm_confidence.get("available", True):
        decision.warnings.append("CEO_LSTM_UNAVAILABLE: LSTM marked unavailable (advisory)")
        decision.reasoning_codes.append("LSTM_UNAVAILABLE")
    else:
        lstm_conf = float(lstm_confidence.get("confidence", 0) or 0)
        decision.reasoning_codes.append(f"LSTM_CONFIDENCE_{lstm_conf:.2f}")

    # Transformer is advisory (not blocking if unavailable)
    if transformer_regime is None:
        decision.warnings.append("CEO_TRANSFORMER_UNAVAILABLE: Transformer regime not provided (advisory)")
        decision.reasoning_codes.append("TRANSFORMER_UNAVAILABLE")
    elif not transformer_regime.get("available", True):
        decision.warnings.append("CEO_TRANSFORMER_UNAVAILABLE: Transformer marked unavailable (advisory)")
        decision.reasoning_codes.append("TRANSFORMER_UNAVAILABLE")
    else:
        t_regime = transformer_regime.get("regime_class", "unknown")
        decision.reasoning_codes.append(f"TRANSFORMER_REGIME_{t_regime}")

    # Broker state is required
    if not broker_state:
        decision.blockers.append("CEO_BROKER_STATE_MISSING: broker_state not provided")
        decision.reasoning_codes.append("BROKER_STATE_MISSING")
    else:
        if not broker_state.get("broker_pass", False):
            decision.blockers.append("CEO_BROKER_NOT_PASS: broker_pass=False")
            decision.reasoning_codes.append("BROKER_NOT_PASS")
        if not broker_state.get("spread_pass", True):
            decision.blockers.append("CEO_SPREAD_NOT_PASS: spread_pass=False")
            decision.reasoning_codes.append("SPREAD_NOT_PASS")
        if not broker_state.get("slippage_pass", True):
            decision.blockers.append("CEO_SLIPPAGE_NOT_PASS: slippage_pass=False")
            decision.reasoning_codes.append("SLIPPAGE_NOT_PASS")

    # Prop/risk state is required
    if not prop_risk_state:
        decision.blockers.append("CEO_PROP_RISK_STATE_MISSING: prop_risk_state not provided")
        decision.reasoning_codes.append("PROP_RISK_STATE_MISSING")
    else:
        if not prop_risk_state.get("risk_pass", False):
            decision.blockers.append("CEO_RISK_NOT_PASS: risk_pass=False")
            decision.reasoning_codes.append("RISK_NOT_PASS")
        if not prop_risk_state.get("prop_funded_pass", False):
            decision.blockers.append("CEO_PROP_FUNDED_NOT_PASS: prop_funded_pass=False")
            decision.reasoning_codes.append("PROP_FUNDED_NOT_PASS")
        if not prop_risk_state.get("max_positions_ok", True):
            decision.blockers.append("CEO_MAX_POSITIONS_EXCEEDED: max_positions_ok=False")
            decision.reasoning_codes.append("MAX_POSITIONS_EXCEEDED")

    # Capital protection state is required
    if not capital_protection_state:
        decision.blockers.append("CEO_CAPITAL_PROTECTION_MISSING: capital_protection_state not provided")
        decision.reasoning_codes.append("CAPITAL_PROTECTION_MISSING")
    else:
        if capital_protection_state.get("dd_breach", False):
            decision.blockers.append("CEO_DD_BREACH: drawdown breach detected")
            decision.reasoning_codes.append("DD_BREACH")
        # Capital preservation mode reduces risk_multiplier (never increases)
        if capital_protection_state.get("capital_preservation_active", False):
            decision.risk_multiplier = 0.5  # reduce to 50% in preservation mode
            decision.warnings.append("CEO_CAPITAL_PRESERVATION_ACTIVE: risk_multiplier reduced to 0.5")
            decision.reasoning_codes.append("CAPITAL_PRESERVATION_ACTIVE")

    # Model health state is required
    if not model_health_state:
        decision.blockers.append("CEO_MODEL_HEALTH_MISSING: model_health_state not provided")
        decision.reasoning_codes.append("MODEL_HEALTH_MISSING")
    else:
        if not model_health_state.get("model_health_pass", False):
            decision.blockers.append("CEO_MODEL_HEALTH_NOT_PASS: model_health_pass=False")
            decision.reasoning_codes.append("MODEL_HEALTH_NOT_PASS")
        failed_required = int(model_health_state.get("failed_required", 0) or 0)
        if failed_required > 0:
            decision.blockers.append(f"CEO_MODEL_HEALTH_FAILED_REQUIRED: {failed_required} required model(s) failed")
            decision.reasoning_codes.append("MODEL_HEALTH_FAILED_REQUIRED")

    # Geometry state is required
    if not geometry_state:
        decision.blockers.append("CEO_GEOMETRY_MISSING: geometry_state not provided")
        decision.reasoning_codes.append("GEOMETRY_MISSING")
    else:
        if not geometry_state.get("geometry_pass", False):
            decision.blockers.append("CEO_GEOMETRY_NOT_PASS: geometry_pass=False")
            decision.reasoning_codes.append("GEOMETRY_NOT_PASS")
        actual_rr = float(geometry_state.get("actual_RR", 0) or 0)
        min_rr = float(geometry_state.get("minimum_RR", 2.0) or 2.0)
        if actual_rr < min_rr:
            decision.blockers.append(
                f"CEO_RR_BELOW_MINIMUM: actual_RR={actual_rr} < minimum_RR={min_rr}"
            )
            decision.reasoning_codes.append("RR_BELOW_MINIMUM")

    # === Compute decision confidence ===
    # Confidence is the minimum of all available expert confidences
    confidences = []
    if xgb_alpha:
        confidences.append(float(xgb_alpha.get("confidence", 0) or 0))
    if lstm_confidence and lstm_confidence.get("available", True):
        confidences.append(float(lstm_confidence.get("confidence", 0) or 0))
    if transformer_regime and transformer_regime.get("available", True):
        confidences.append(float(transformer_regime.get("confidence", 0) or 0))
    if meta_label_quality:
        confidences.append(float(meta_label_quality.get("quality_score", 0) or 0))
    if regime_state:
        confidences.append(float(regime_state.get("confidence", 0) or 0))
    decision.decision_confidence = min(confidences) if confidences else 0.0

    # === Final decision ===
    # PASS only if no blockers
    if decision.blockers:
        decision.final_decision = "BLOCKED"
        decision.allowed_to_trade = False
    else:
        decision.final_decision = "PASS"
        decision.allowed_to_trade = True

    # Hard rule: risk_multiplier never exceeds 1.0
    if decision.risk_multiplier > 1.0:
        decision.risk_multiplier = 1.0
        decision.warnings.append("CEO_RISK_MULTIPLIER_CAPPED: reduced to 1.0 (never exceeds cap)")

    # === Log CEO_AI_DECISION event to journal ===
    _log_ceo_ai_decision(decision)

    return decision


def _log_ceo_ai_decision(decision: CEOAIDecision) -> None:
    """Log CEO_AI_DECISION event to trade journal.

    Best-effort logging - never blocks the decision.
    """
    try:
        journal_path = REPO_ROOT / "data" / "runtime" / "titan_journal.jsonl"
        journal_path.parent.mkdir(parents=True, exist_ok=True)
        event = {
            "timestamp_utc": decision.timestamp_utc,
            "event_type": "CEO_AI_DECISION",
            "final_decision": decision.final_decision,
            "allowed_to_trade": decision.allowed_to_trade,
            "decision_confidence": decision.decision_confidence,
            "risk_multiplier": decision.risk_multiplier,
            "blockers_count": len(decision.blockers),
            "warnings_count": len(decision.warnings),
            "reasoning_codes": decision.reasoning_codes,
        }
        with open(journal_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, default=str) + "\n")
    except Exception:
        pass  # never block decision on journal write failure


def is_ceo_governance_wired() -> bool:
    """Check if CEO AI Governance is importable (always True if this module exists)."""
    return True


def get_ceo_governance_info() -> dict:
    """Return info about CEO AI Governance module for audit purposes."""
    return {
        "module_exists": True,
        "module_path": str(Path(__file__).relative_to(REPO_ROOT)),
        "evaluates_decision": True,
        "logs_journal_event": "CEO_AI_DECISION",
        "hard_rules": [
            "no_mt5_calls",
            "no_token_creation",
            "no_position_modification",
            "no_hard_gate_override",
            "no_forced_trade",
            "no_risk_increase_above_cap",
            "no_martingale_grid_averaging_loss_multiplier",
        ],
        "required_inputs": [
            "regime_state", "xgb_alpha", "meta_label_quality",
            "broker_state", "prop_risk_state", "capital_protection_state",
            "model_health_state", "geometry_state",
        ],
        "advisory_inputs": [
            "lstm_confidence", "transformer_regime",
        ],
        "outputs": [
            "final_decision", "allowed_to_trade", "decision_confidence",
            "risk_multiplier", "blockers", "warnings", "reasoning_codes",
        ],
    }
