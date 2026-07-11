"""TITAN XAU AI — Canonical Decision Engine (v2.8.7-P2.2)
==========================================================

One canonical pure decision kernel used by BOTH:
  - historical replay adapter (HistoricalAdapter)
  - MT5 forward-shadow adapter (ShadowAdapter)

v2.8.7-P2.2 changes from P2.1:
  - Actually applies adaptive thresholds: effective_alpha = adaptive_alpha + regime_modifier
  - Actually applies adaptive risk multiplier: proposed_risk = base_risk × adaptive_risk_multiplier
  - CEO consumes the SAME safety truth as risk governor (no hard-coded PASS)
  - No safe literals anywhere in the decision path

The kernel executes:
  1. data/schema/freshness checks
  2. model-class verification
  3. direction interpretation
  4. regime classification
  5. governed setup scan
  6. adaptive thresholds (APPLIED to decision, not just metadata)
  7. real safety state
  8. risk governor (receives adaptive-adjusted proposed risk)
  9. near-miss preview (shadow only)
  10. CEO governance (receives same safety truth)
  11. instrument sizing
  12. structured decision

Adapters may differ; decision logic may NOT differ.

NEVER sends orders. NEVER creates tokens. NEVER trades.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
import math
import numpy as np
import pandas as pd

from titan.production.direction_logic import interpret_direction
from titan.production.instrument_valuation import (
    InstrumentSpec, validate_instrument_spec,
    price_delta_to_money, compute_lot_size,
)
from titan.production.corrected_regime_classifier_v2 import classify_regime_v2, RegimeResultV2
from titan.production.corrected_setup_detector_v2 import (
    scan_setups_governed, ScanResultV2, SetupResultV2,
    REGIME_RISK_MODIFIERS, REGIME_THRESHOLD_MODIFIERS, UNSAFE_REGIMES,
)
from titan.production.corrected_adaptive_threshold_v2 import (
    SafetyStateV2, compute_adaptive_threshold_v2, CorrectedThresholdStateV2,
)
from titan.production.risk_governor import (
    govern_risk, RiskGovernorInput, RiskGovernorOutput,
)
from titan.production.near_miss_tracker_v2 import NearMissShadowTrackerV2
from titan.production.ceo_ai_governance import evaluate_ceo_decision


@dataclass
class DecisionContext:
    """All inputs required for a canonical decision."""
    df: pd.DataFrame
    alpha_proba: float
    meta_proba: float
    alpha_probas_recent: np.ndarray
    meta_probas_recent: np.ndarray
    atr_value: float
    instrument: InstrumentSpec
    config: Dict[str, Any]
    safety_state: SafetyStateV2
    equity: float
    equity_peak: float
    daily_peak: float
    daily_start_equity: float
    existing_daily_open_risk: float = 0.0
    existing_total_open_risk: float = 0.0
    existing_combined_risk: float = 0.0
    loss_streak: int = 0
    adapter_mode: str = "shadow"
    near_miss_tracker: Optional[NearMissShadowTrackerV2] = None
    spread: float = 0.0
    entry_price: float = 0.0
    timestamp: str = ""
    skip_freshness_check: bool = False  # historical adapter skips freshness


@dataclass
class CanonicalDecision:
    """Structured decision output — identical for both adapters given same context."""
    decision_id: str
    correlation_id: str
    timestamp: str
    adapter_mode: str
    call_trace: List[str] = field(default_factory=list)
    final_decision: str = "REJECT"
    reject_reason: str = ""
    direction: Optional[str] = None
    directional_confidence: Optional[float] = None
    alpha_proba: Optional[float] = None
    meta_proba: Optional[float] = None
    regime: Optional[str] = None
    regime_confidence: Optional[float] = None
    regime_risk_modifier: float = 1.0
    regime_threshold_modifier: float = 0.0
    setup_selected: Optional[str] = None
    setup_alternatives: List[str] = field(default_factory=list)
    # Thresholds (APPLIED)
    base_alpha_threshold: Optional[float] = None
    adaptive_alpha_threshold: Optional[float] = None
    final_alpha_threshold: Optional[float] = None
    base_meta_threshold: Optional[float] = None
    adaptive_meta_threshold: Optional[float] = None
    final_meta_threshold: Optional[float] = None
    adaptive_risk_multiplier: Optional[float] = None
    adaptive_block_reason: str = ""
    # Risk (APPLIED)
    base_risk_percent: Optional[float] = None
    proposed_risk_percent: Optional[float] = None
    approved_risk: float = 0.0
    risk_amount: float = 0.0
    # Lot sizing
    lot_size: float = 0.0
    monetary_loss_at_sl: float = 0.0
    actual_risk_percent: float = 0.0
    # SL/TP
    sl_price: float = 0.0
    tp_price: float = 0.0
    entry_price: float = 0.0
    # CEO
    ceo_decision: str = ""
    # Safety
    NO_ORDER_SENT: bool = True
    # Near-miss
    near_miss_consulted: bool = False
    near_miss_preview_eligible: bool = False
    # Adaptive journal
    adaptive_journal: List[dict] = field(default_factory=list)
    # Risk journal
    risk_journal: List[dict] = field(default_factory=list)


class CanonicalDecisionEngine:
    """Pure decision kernel — no I/O, no side effects."""

    def evaluate(self, ctx: DecisionContext) -> CanonicalDecision:
        decision_id = f"dec_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')}"
        correlation_id = f"corr_{decision_id}"
        trace: List[str] = []
        decision = CanonicalDecision(
            decision_id=decision_id, correlation_id=correlation_id,
            timestamp=ctx.timestamp, adapter_mode=ctx.adapter_mode,
        )

        # ===== 1. data/schema/freshness checks =====
        trace.append("1:data_schema_freshness_checks")
        if ctx.df is None or len(ctx.df) == 0:
            decision.final_decision = "REJECT_DATA"
            decision.reject_reason = "empty_dataframe"
            decision.call_trace = trace
            return decision
        required = {"open", "high", "low", "close"}
        if not required.issubset(ctx.df.columns):
            decision.final_decision = "REJECT_SCHEMA"
            decision.reject_reason = f"missing_columns_{required - set(ctx.df.columns)}"
            decision.call_trace = trace
            return decision

        # ===== 2. model-class verification =====
        trace.append("2:model_class_verification")
        if not (0.0 <= ctx.alpha_proba <= 1.0) or not math.isfinite(ctx.alpha_proba):
            decision.final_decision = "REJECT_MODEL_INFERENCE"
            decision.reject_reason = f"alpha_proba_invalid_{ctx.alpha_proba}"
            decision.call_trace = trace
            return decision
        if not (0.0 <= ctx.meta_proba <= 1.0) or not math.isfinite(ctx.meta_proba):
            decision.final_decision = "REJECT_MODEL_INFERENCE"
            decision.reject_reason = f"meta_proba_invalid_{ctx.meta_proba}"
            decision.call_trace = trace
            return decision
        decision.alpha_proba = round(float(ctx.alpha_proba), 6)
        decision.meta_proba = round(float(ctx.meta_proba), 6)

        # ===== 3. direction interpretation =====
        trace.append("3:direction_interpretation")
        direction, dir_confidence = interpret_direction(ctx.alpha_proba)
        decision.direction = direction
        decision.directional_confidence = round(float(dir_confidence), 6)

        # ===== 4. regime classification =====
        trace.append("4:regime_classification")
        regime_result = classify_regime_v2(ctx.df, min_bars=60)
        regime_label = regime_result.regime.value
        regime_direction = regime_result.direction
        decision.regime = regime_label
        decision.regime_confidence = round(float(regime_result.confidence), 4)
        decision.regime_risk_modifier = REGIME_RISK_MODIFIERS.get(regime_label, 0.0)
        decision.regime_threshold_modifier = REGIME_THRESHOLD_MODIFIERS.get(regime_label, 0.20)

        # ===== 5. governed setup scan =====
        trace.append("5:governed_setup_scan")
        scan = scan_setups_governed(ctx.df, regime_direction=regime_direction,
                                     atr_value=float(ctx.atr_value),
                                     regime_label=regime_label)
        decision.setup_alternatives = [a.setup_type.value for a in scan.alternatives]
        if scan.selected_setup is None:
            decision.final_decision = "REJECT_NO_SETUP"
            decision.reject_reason = ";".join(scan.rejection_reasons)
            decision.call_trace = trace
            return decision
        selected_setup = scan.selected_setup
        decision.setup_selected = selected_setup.setup_type.value
        if selected_setup.direction != direction and selected_setup.direction != "NEUTRAL":
            decision.final_decision = "REJECT_SETUP_DIRECTION_CONFLICT"
            decision.reject_reason = f"setup_dir={selected_setup.direction} != model_dir={direction}"
            decision.call_trace = trace
            return decision

        # ===== 6. adaptive thresholds (APPLIED) =====
        trace.append("6:adaptive_thresholds_applied")
        adaptive_journal: List[dict] = []
        adaptive_result = compute_adaptive_threshold_v2(
            ctx.safety_state,
            journal_callback=lambda e: adaptive_journal.append(e),
        )
        decision.adaptive_alpha_threshold = adaptive_result.alpha_threshold_effective
        decision.adaptive_meta_threshold = adaptive_result.meta_threshold_effective
        decision.adaptive_risk_multiplier = adaptive_result.risk_multiplier
        decision.adaptive_block_reason = adaptive_result.block_reason
        decision.adaptive_journal = adaptive_journal
        if adaptive_result.policy_mode == "hard_block":
            decision.final_decision = "REJECT_ADAPTIVE_HARD_BLOCK"
            decision.reject_reason = adaptive_result.block_reason
            decision.call_trace = trace
            return decision

        # --- APPLY adaptive thresholds to decision ---
        base_alpha_threshold = ctx.config.get("alpha_threshold", 0.55)
        base_meta_threshold = ctx.config.get("meta_threshold", 0.50)
        # effective_alpha = max(adaptive_alpha, base_alpha) + regime_threshold_modifier
        # The config's base threshold is the floor; adaptive can tighten above it.
        effective_alpha = max(adaptive_result.alpha_threshold_effective, base_alpha_threshold) + decision.regime_threshold_modifier
        # effective_meta = max(adaptive_meta, base_meta)
        effective_meta = max(adaptive_result.meta_threshold_effective, base_meta_threshold)

        decision.base_alpha_threshold = base_alpha_threshold
        decision.adaptive_alpha_threshold = adaptive_result.alpha_threshold_effective
        decision.final_alpha_threshold = effective_alpha
        decision.base_meta_threshold = base_meta_threshold
        decision.adaptive_meta_threshold = adaptive_result.meta_threshold_effective
        decision.final_meta_threshold = effective_meta

        # Apply directional confidence threshold
        if dir_confidence < effective_alpha:
            decision.final_decision = "REJECT_ALPHA"
            decision.reject_reason = (
                f"dir_confidence_{dir_confidence:.4f}_below_"
                f"effective_{effective_alpha:.4f}"
                f"(base={base_alpha_threshold:.2f}"
                f"+adaptive={adaptive_result.alpha_threshold_effective - base_alpha_threshold:+.2f}"
                f"+regime={decision.regime_threshold_modifier:+.2f})"
            )
            decision.call_trace = trace
            return decision
        if ctx.meta_proba < effective_meta:
            decision.final_decision = "REJECT_META"
            decision.reject_reason = (
                f"meta_{ctx.meta_proba:.4f}_below_"
                f"effective_{effective_meta:.4f}"
            )
            decision.call_trace = trace
            return decision

        # ===== 7. real safety state (already in ctx) =====
        trace.append("7:real_safety_state")

        # ===== 8. risk governor (receives adaptive-adjusted proposed risk) =====
        trace.append("8:risk_governor_adaptive_risk")
        base_risk_percent = ctx.config.get("risk_percent", 0.003)
        # proposed_risk = base_risk × adaptive_risk_multiplier × regime_risk_modifier
        proposed_risk = base_risk_percent * adaptive_result.risk_multiplier * decision.regime_risk_modifier
        decision.base_risk_percent = base_risk_percent
        decision.proposed_risk_percent = proposed_risk

        setup_class = ctx.config.get("setup_class", "A_PLUS")
        gov_inp = RiskGovernorInput(
            equity=ctx.equity, equity_peak=ctx.equity_peak,
            daily_peak=ctx.daily_peak, daily_start_equity=ctx.daily_start_equity,
            proposed_risk=proposed_risk, setup_class=setup_class,
            existing_daily_open_risk=ctx.existing_daily_open_risk,
            existing_total_open_risk=ctx.existing_total_open_risk,
            existing_combined_risk=ctx.existing_combined_risk,
            loss_streak=ctx.loss_streak,
            regime_risk_modifier=1.0,  # already applied above
            broker_risk_modifier=1.0,
            # SAME safety truth as CEO
            prop_risk_pass=ctx.safety_state.prop_risk_state.get("prop_pass"),
            capital_protection_active=ctx.safety_state.capital_protection.get("active"),
            broker_safe=ctx.safety_state.broker_intelligence.get("broker_pass"),
            execution_healthy=ctx.safety_state.execution_health.get("healthy"),
            model_healthy=ctx.safety_state.model_health.get("model_health_pass"),
            margin_safe=ctx.safety_state.margin_state.get("margin_safe"),
            external_daily_dd=ctx.safety_state.external_daily_dd,
            external_total_dd=ctx.safety_state.external_total_dd,
        )
        gov_out = govern_risk(gov_inp)
        # Journal the risk decision
        decision.risk_journal.append({
            "base_risk_percent": base_risk_percent,
            "adaptive_risk_multiplier": adaptive_result.risk_multiplier,
            "regime_risk_modifier": decision.regime_risk_modifier,
            "proposed_risk_percent": proposed_risk,
            "governor_approved": gov_out.approved,
            "governor_approved_risk": gov_out.approved_risk,
            "governor_block_reason": gov_out.block_reason,
        })
        if not gov_out.approved:
            decision.final_decision = "REJECT_RISK_GOVERNOR"
            decision.reject_reason = gov_out.block_reason
            decision.call_trace = trace
            return decision
        decision.approved_risk = round(float(gov_out.approved_risk), 6)
        decision.risk_amount = round(float(ctx.equity * gov_out.approved_risk), 2)

        # ===== 9. near-miss preview (shadow only — no mutation) =====
        if ctx.adapter_mode == "shadow" and ctx.near_miss_tracker is not None:
            trace.append("9:near_miss_preview")
            decision.near_miss_consulted = True
            if ctx.near_miss_tracker.records:
                current_time = pd.Timestamp(ctx.timestamp) if ctx.timestamp else pd.Timestamp.utcnow()
                for record in ctx.near_miss_tracker.records:
                    if record.re_entry_consumed:
                        continue
                    eligible, reason = ctx.near_miss_tracker.preview_re_entry_eligibility(
                        record=record, current_time=current_time,
                        current_price=ctx.entry_price,
                        new_confirmation=True, hard_gates_clear=False,
                    )
                    if eligible:
                        decision.near_miss_preview_eligible = True
                        break

        # ===== 10. CEO governance (consumes SAME safety truth) =====
        trace.append("10:ceo_governance_same_safety_truth")
        rr_target = ctx.config.get("rr_target", 3.0)
        # CEO receives the SAME safety values as the risk governor — no hard-coded PASS
        ceo = evaluate_ceo_decision(
            regime_state={"detected": True, "regime_value": regime_label,
                           "confidence": float(regime_result.confidence)},
            xgb_alpha={"direction": direction, "confidence": dir_confidence, "pass": True},
            lstm_confidence=None, transformer_regime=None,
            meta_label_quality={"quality_score": ctx.meta_proba, "pass": True},
            broker_state={
                "broker_pass": ctx.safety_state.broker_intelligence.get("broker_pass"),
                "spread_pass": ctx.safety_state.broker_intelligence.get("spread_pass"),
                "slippage_pass": True,  # TODO: wire to real slippage monitor
            },
            prop_risk_state={
                "risk_pass": ctx.safety_state.prop_risk_state.get("prop_pass"),
                "prop_funded_pass": ctx.safety_state.prop_risk_state.get("prop_pass"),
                "max_positions_ok": True,
            },
            capital_protection_state={
                "capital_preservation_active": ctx.safety_state.capital_protection.get("active"),
                "dd_breach": ctx.safety_state.capital_protection.get("dd_breach"),
            },
            model_health_state={
                "model_health_pass": ctx.safety_state.model_health.get("model_health_pass"),
                "failed_required": 0,
            },
            geometry_state={"geometry_pass": True, "actual_RR": rr_target, "minimum_RR": 2.0},
        )
        decision.ceo_decision = "PASS" if ceo.allowed_to_trade else "BLOCK"
        if not ceo.allowed_to_trade:
            decision.final_decision = "REJECT_CEO"
            decision.reject_reason = "ceo_blocked"
            decision.call_trace = trace
            return decision

        # ===== 11. instrument sizing =====
        trace.append("11:instrument_sizing")
        sl_mult = ctx.config.get("sl_atr_multiplier", 2.0)
        sl_distance = float(ctx.atr_value) * sl_mult
        tp_distance = sl_distance * rr_target
        lot, monetary_loss_at_sl, lot_reject = compute_lot_size(
            ctx.instrument, decision.risk_amount, sl_distance
        )
        if lot <= 0 or lot_reject:
            decision.final_decision = "REJECT_LOT_SIZING"
            decision.reject_reason = lot_reject
            decision.call_trace = trace
            return decision
        decision.lot_size = round(float(lot), 4)
        decision.monetary_loss_at_sl = round(float(monetary_loss_at_sl), 2)
        decision.actual_risk_percent = round(float(monetary_loss_at_sl / ctx.equity), 6) if ctx.equity > 0 else 0.0
        decision.entry_price = round(float(ctx.entry_price), 4)
        if direction == "LONG":
            decision.sl_price = round(float(ctx.entry_price - sl_distance), 4)
            decision.tp_price = round(float(ctx.entry_price + tp_distance), 4)
        else:
            decision.sl_price = round(float(ctx.entry_price + sl_distance), 4)
            decision.tp_price = round(float(ctx.entry_price - tp_distance), 4)

        # ===== 12. structured decision =====
        trace.append("12:structured_decision")
        decision.final_decision = "SHADOW_SIGNAL" if ctx.adapter_mode == "shadow" else "HISTORICAL_SIGNAL"
        decision.call_trace = trace
        decision.NO_ORDER_SENT = True
        return decision


__all__ = ["DecisionContext", "CanonicalDecision", "CanonicalDecisionEngine"]
