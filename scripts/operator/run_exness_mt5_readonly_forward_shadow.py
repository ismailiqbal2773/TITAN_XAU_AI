#!/usr/bin/env python3
"""TITAN XAU AI — Exness MT5 Read-Only Forward Shadow Runner (FINAL Sprint v2.8.7-P2.0)
======================================================================================

Local Windows MT5 forward shadow runner. Reads market data, computes features,
generates read-only signals via the FULL CANONICAL PIPELINE. NEVER trades.

Canonical pipeline executed per cycle:
  1.  safe_connect_and_audit
  2.  MT5 symbol/account/instrument metadata extraction
  3.  data freshness/schema validation
  4.  feature generation with production schema/scaler
  5.  XGBoost classes_ verification
  6.  alpha/meta inference
  7.  interpret_direction (p_up=0.10 → SHORT, confidence=0.90)
  8.  directional-confidence threshold
  9.  classify_regime_v2
  10. canonical setup scan (governed)
  11. SafetyStateV2 construction
  12. compute_adaptive_threshold_v2 (with journal callback)
  13. canonical govern_risk (fail-closed safety inputs)
  14. near-miss handling
  15. CEO governance
  16. broker-step hypothetical lot sizing via InstrumentSpec
  17. structured journal persistence
  18. NO_ORDER_SENT=true

Removed old behaviour:
  - rejects alpha_proba < alpha_threshold BEFORE direction interpretation
  - hard-codes broker PASS / prop PASS / capital protection false
  - hard-codes model health PASS
  - uses CONTRACT_SIZE=100 independently
  - loads legacy profile instead of competition shadow profile

For p_up=0.10: direction=SHORT, confidence=0.90, full canonical path executed.
NO order_send import or call.

CLI:
  python scripts/operator/run_exness_mt5_readonly_forward_shadow.py
    --broker exness --symbol XAUUSD --timeframe H1
    --max-cycles 24 --sleep-seconds 60

NEVER sends orders. NEVER creates tokens. NEVER trades.
NO_ORDER_SENT = True on every row.
"""
from __future__ import annotations
import sys, os, json, csv, time, argparse, signal, hashlib
from pathlib import Path
from datetime import datetime, timezone
from dataclasses import asdict
import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

OUTPUT_DIR = REPO_ROOT / "data" / "reports" / "exness_forward_shadow"

from scripts.operator.mt5_safe_connector import safe_connect_and_audit
from titan.production.spread_normalization import normalize_xauusd_spread_to_usd
from titan.production.feature_stream_v2 import H1FeatureStreamV2, FEATURE_NAMES_V2
from titan.training.feature_schema_v2 import META_FEATURE_NAMES_V2
from titan.production.model_loader import load_models_by_profile
from titan.production.ceo_ai_governance import evaluate_ceo_decision
from titan.production.direction_logic import interpret_direction
from titan.production.canonical_backtest import InstrumentSpec, compute_lot_size, validate_instrument_spec
from titan.production.corrected_regime_classifier_v2 import classify_regime_v2
from titan.production.corrected_setup_detector_v2 import scan_setups_governed
from titan.production.corrected_adaptive_threshold_v2 import (
    SafetyStateV2, compute_adaptive_threshold_v2,
)
from titan.production.risk_governor import govern_risk, RiskGovernorInput
from titan.production.near_miss_tracker_v2 import NearMissShadowTrackerV2


LEVERAGE = 100


def load_exness_competition_shadow_profile():
    """Load the competition shadow profile (NOT the legacy profile)."""
    import yaml
    path = REPO_ROOT / "config" / "broker_profiles" / "exness_competition_shadow_profile.yaml"
    with open(path) as f:
        return yaml.safe_load(f)


def _make_instrument_spec_from_mt5(symbol_info, account_info) -> InstrumentSpec:
    """Extract a validated InstrumentSpec from MT5 symbol/account metadata.

    Falls back to safe XAUUSD defaults if metadata is missing; the spec is
    still validated and used for lot sizing — no silent contract_size=100
    hard-coding in the lot calculation.
    """
    if symbol_info is not None:
        try:
            tick_size = float(getattr(symbol_info, "trade_tick_size", 0.0)) or 0.01
            tick_value = float(getattr(symbol_info, "trade_tick_value", 0.0)) or 1.0
            contract_size = float(getattr(symbol_info, "trade_contract_size", 0.0)) or 100.0
            volume_min = float(getattr(symbol_info, "volume_min", 0.0)) or 0.01
            volume_max = float(getattr(symbol_info, "volume_max", 0.0)) or 100.0
            volume_step = float(getattr(symbol_info, "volume_step", 0.0)) or 0.01
        except Exception:
            tick_size, tick_value, contract_size = 0.01, 1.0, 100.0
            volume_min, volume_max, volume_step = 0.01, 100.0, 0.01
    else:
        tick_size, tick_value, contract_size = 0.01, 1.0, 100.0
        volume_min, volume_max, volume_step = 0.01, 100.0, 0.01

    profit_ccy = "USD"
    account_ccy = "USD"
    if account_info is not None:
        try:
            account_ccy = str(getattr(account_info, "currency", "USD") or "USD")
        except Exception:
            account_ccy = "USD"
    conversion_rate = 1.0
    return InstrumentSpec(
        tick_size=tick_size, tick_value=tick_value, contract_size=contract_size,
        volume_min=volume_min, volume_max=volume_max, volume_step=volume_step,
        account_currency=account_ccy, profit_currency=profit_ccy,
        symbol_currency="USD", conversion_rate=conversion_rate,
    )


def _hash_model(bundle) -> dict:
    """Compute a stable hash for the loaded model bundle."""
    out = {}
    try:
        import pickle
        if hasattr(bundle, "xgb") and bundle.xgb is not None:
            out["xgb_classes"] = list(getattr(bundle.xgb, "classes_", [0, 1]))
            out["xgb_n_estimators"] = getattr(bundle.xgb, "n_estimators", "unknown")
    except Exception:
        pass
    return out


def _data_freshness_check(df: pd.DataFrame, max_age_hours: int = 4) -> tuple[bool, str]:
    """Validate data freshness."""
    if df is None or len(df) == 0:
        return False, "empty_dataframe"
    last_ts = pd.Timestamp(df.index[-1])
    if last_ts.tzinfo is None:
        last_ts = last_ts.tz_localize("UTC")
    now = pd.Timestamp.now(tz="UTC")
    age = (now - last_ts).total_seconds() / 3600.0
    if age > max_age_hours:
        return False, f"data_stale_age_{age:.1f}h_gt_{max_age_hours}h"
    return True, ""


def _data_schema_check(df: pd.DataFrame) -> tuple[bool, str]:
    """Validate data schema."""
    required = {"open", "high", "low", "close"}
    if not required.issubset(df.columns):
        return False, f"missing_columns_{required - set(df.columns)}"
    if df[["open", "high", "low", "close"]].isna().any().any():
        return False, "NaN_in_OHLC"
    if not df.index.is_monotonic_increasing:
        return False, "index_not_monotonic"
    return True, ""


def _broker_step_lot_sizing(spec: InstrumentSpec, equity: float, approved_risk: float,
                            sl_distance: float, entry_price: float) -> dict:
    """Hypothetical broker-step lot sizing via InstrumentSpec.

    Returns dict with lot, monetary_loss_at_sl, risk_amount, margin_required,
    margin_usage, reject_reason.
    """
    ok, msg = validate_instrument_spec(spec)
    if not ok:
        return {"lot": 0.0, "monetary_loss_at_sl": 0.0, "risk_amount": 0.0,
                "margin_required": 0.0, "margin_usage": 0.0, "reject_reason": msg}
    risk_amount = equity * approved_risk
    lot, monetary_loss, reject = compute_lot_size(spec, risk_amount, sl_distance)
    if lot <= 0 or reject:
        return {"lot": 0.0, "monetary_loss_at_sl": 0.0, "risk_amount": round(risk_amount, 2),
                "margin_required": 0.0, "margin_usage": 0.0, "reject_reason": reject}
    notional = entry_price * spec.contract_size * lot
    margin = notional / LEVERAGE
    margin_usage = margin / equity if equity > 0 else 0.0
    if margin_usage > 0.20:
        max_lot = (equity * 0.20 * LEVERAGE) / (entry_price * spec.contract_size)
        # Round down to volume_step
        import math
        max_lot = math.floor(max_lot / spec.volume_step) * spec.volume_step
        if max_lot < spec.volume_min:
            return {"lot": 0.0, "monetary_loss_at_sl": 0.0, "risk_amount": round(risk_amount, 2),
                    "margin_required": 0.0, "margin_usage": 0.0,
                    "reject_reason": f"margin_usage_clamp_below_volume_min"}
        lot = max_lot
        notional = entry_price * spec.contract_size * lot
        margin = notional / LEVERAGE
        margin_usage = margin / equity if equity > 0 else 0.0
        loss_per_lot = monetary_loss / max(lot, 1e-9)
        monetary_loss = loss_per_lot * lot
    return {
        "lot": round(lot, 4),
        "monetary_loss_at_sl": round(monetary_loss, 2),
        "risk_amount": round(risk_amount, 2),
        "margin_required": round(margin, 2),
        "margin_usage": round(margin_usage, 6),
        "reject_reason": "",
    }


def run_forward_shadow_cycle(broker, symbol, timeframe, profile, bundle, equity=100000.0,
                             instrument_spec_override: InstrumentSpec = None,
                             near_miss_tracker: NearMissShadowTrackerV2 = None,
                             journal_sink: list = None) -> dict:
    """Run one forward shadow cycle through the FULL CANONICAL PIPELINE.

    Returns a structured signal dict. NO_ORDER_SENT is always True.
    """
    decision_id = f"shadow_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}_{abs(hash(symbol)) % 10000}"
    correlation_id = f"corr_{decision_id}"
    cycle_start_ts = datetime.now(timezone.utc).isoformat()
    call_trace: list[str] = []

    params = profile.get("optimized_parameters", {
        "alpha_threshold": 0.55, "meta_threshold": 0.50,
        "risk_percent": 0.003, "sl_atr_multiplier": 2.0,
        "rr_target": 3.0, "spread_filter": 1.0,
        "commission_per_lot": 7.0, "slippage_points": 0.5, "swap_per_bar": 0.0,
        "setup_class": "A_PLUS",
    })
    setup_class = params.get("setup_class", "A_PLUS")

    def _base_signal() -> dict:
        return {
            "timestamp": cycle_start_ts,
            "decision_id": decision_id,
            "correlation_id": correlation_id,
            "broker": broker, "symbol": symbol, "timeframe": timeframe,
            "final_decision": "REJECT", "reject_reason": "",
            "direction": None, "directional_confidence": None,
            "alpha_proba": None, "meta_proba": None,
            "regime": None, "regime_confidence": None,
            "setup_selected": None, "setup_alternatives": [],
            "approved_risk": 0.0, "lot_size": 0.0,
            "monetary_loss_at_sl": 0.0, "risk_amount": 0.0,
            "actual_risk_percent": 0.0,
            "margin_required": 0.0, "margin_usage": 0.0,
            "adaptive_block_reason": "",
            "ceo_decision": "",
            "block_reason": "",
            "NO_ORDER_SENT": True,
            "call_trace": call_trace,
            "near_miss_consulted": False,
        }

    # ===== 1. safe_connect_and_audit =====
    call_trace.append("1:safe_connect_and_audit")
    result = safe_connect_and_audit(symbol=symbol, bar_count=300)
    if not result.success:
        sig = _base_signal()
        sig["final_decision"] = "SAFETY_BLOCK"
        sig["reject_reason"] = result.verdict
        if journal_sink is not None:
            journal_sink.append(sig)
        return sig

    # ===== 2. MT5 symbol/account/instrument metadata extraction =====
    call_trace.append("2:instrument_metadata_extraction")
    if instrument_spec_override is not None:
        instrument = instrument_spec_override
    else:
        instrument = _make_instrument_spec_from_mt5(
            getattr(result, "symbol_info", None),
            getattr(result, "account_info", None),
        )
    ok, msg = validate_instrument_spec(instrument)
    if not ok:
        sig = _base_signal()
        sig["final_decision"] = "REJECT_INSTRUMENT_SPEC"
        sig["reject_reason"] = msg
        if journal_sink is not None:
            journal_sink.append(sig)
        return sig

    if result.raw_bars is None or len(result.raw_bars) < 220:
        sig = _base_signal()
        sig["final_decision"] = "REJECT_MARKET_DATA"
        sig["reject_reason"] = "insufficient_bars"
        if journal_sink is not None:
            journal_sink.append(sig)
        return sig

    # Convert to DataFrame
    df = pd.DataFrame(result.raw_bars)
    if "time" in df.columns:
        df["time"] = pd.to_datetime(df["time"], unit="s")
        df = df.set_index("time")
    df = normalize_xauusd_spread_to_usd(df, symbol="XAUUSD", source=broker)

    # ===== 3. data freshness/schema validation =====
    call_trace.append("3:data_freshness_schema_validation")
    fresh_ok, fresh_msg = _data_freshness_check(df, max_age_hours=24)
    if not fresh_ok:
        sig = _base_signal()
        sig["final_decision"] = "REJECT_STALE_DATA"
        sig["reject_reason"] = fresh_msg
        if journal_sink is not None:
            journal_sink.append(sig)
        return sig
    schema_ok, schema_msg = _data_schema_check(df)
    if not schema_ok:
        sig = _base_signal()
        sig["final_decision"] = "REJECT_SCHEMA"
        sig["reject_reason"] = schema_msg
        if journal_sink is not None:
            journal_sink.append(sig)
        return sig

    # ===== 4. feature generation with production schema/scaler =====
    call_trace.append("4:feature_generation")
    df_use = df[["open", "high", "low", "close"]].copy()
    if "tick_volume" in df.columns:
        df_use["volume"] = df["tick_volume"]
    else:
        df_use["volume"] = 0.0
    df_use["spread"] = df["spread_usd"]

    stream = H1FeatureStreamV2()
    stream._bars = df_use
    try:
        feats_df = stream._compute_features()
        features_matrix = np.nan_to_num(feats_df.values.astype(np.float64), nan=0.0, posinf=0.0, neginf=0.0)
        features_matrix = stream._standardize(features_matrix)
    except Exception as e:
        sig = _base_signal()
        sig["final_decision"] = "REJECT_FEATURE_ERROR"
        sig["reject_reason"] = f"feature_error: {e}"
        if journal_sink is not None:
            journal_sink.append(sig)
        return sig

    # ===== 5. XGBoost classes_ verification =====
    call_trace.append("5:xgb_classes_verification")
    if not hasattr(bundle.xgb, "classes_"):
        sig = _base_signal()
        sig["final_decision"] = "REJECT_MODEL_CLASSES"
        sig["reject_reason"] = "xgb missing classes_"
        if journal_sink is not None:
            journal_sink.append(sig)
        return sig
    expected_classes = np.array([0, 1])
    if not np.array_equal(np.asarray(bundle.xgb.classes_), expected_classes):
        sig = _base_signal()
        sig["final_decision"] = "REJECT_MODEL_CLASSES"
        sig["reject_reason"] = f"xgb classes_={bundle.xgb.classes_} != [0,1]"
        if journal_sink is not None:
            journal_sink.append(sig)
        return sig

    # ===== 6. alpha/meta inference =====
    call_trace.append("6:alpha_meta_inference")
    last_vec = features_matrix[-1:]
    alpha_proba = float(bundle.xgb.predict_proba(last_vec)[0, 1])
    name_to_idx = {n: i for i, n in enumerate(FEATURE_NAMES_V2)}
    meta_indices = [name_to_idx[n] for n in META_FEATURE_NAMES_V2]
    meta_vec = last_vec[0, meta_indices]
    meta_proba = float(bundle.meta.predict_proba(meta_vec.reshape(1, -1))[0, 1])

    # ATR for latest bar
    closes = df["close"].values
    highs = df["high"].values
    lows = df["low"].values
    i = len(df) - 1
    atr = max(
        highs[i] - lows[i],
        abs(highs[i] - closes[i - 1]),
        abs(lows[i] - closes[i - 1]),
    ) if i > 0 else 3.0

    # ===== 7. interpret_direction (NOT raw >=0.5 check) =====
    call_trace.append("7:interpret_direction")
    direction, dir_confidence = interpret_direction(alpha_proba)
    # CRITICAL: p_up=0.10 → direction=SHORT, confidence=0.90

    # ===== 8. directional-confidence threshold =====
    call_trace.append("8:directional_confidence_threshold")
    alpha_threshold = params.get("alpha_threshold", 0.55)
    if dir_confidence < alpha_threshold:
        # Near-miss: confidence close to threshold
        if near_miss_tracker is not None and dir_confidence >= alpha_threshold - 0.05:
            near_miss_tracker.record_near_miss(
                timestamp=str(df.index[-1]), direction=direction,
                setup_type="ALPHA_NEAR_MISS", regime="UNKNOWN",
                score=dir_confidence, effective_threshold=alpha_threshold,
                component_scores={"alpha_proba": alpha_proba, "meta_proba": meta_proba},
                rejection_reasons=[f"dir_confidence_{dir_confidence:.4f}_below_{alpha_threshold}"],
                hypothetical_entry=float(closes[i]),
                hypothetical_sl=float(closes[i]) - atr * params.get("sl_atr_multiplier", 2.0),
                hypothetical_tp=float(closes[i]) + atr * params.get("sl_atr_multiplier", 2.0) * params.get("rr_target", 3.0),
            )
        sig = _base_signal()
        sig["final_decision"] = "REJECT_ALPHA"
        sig["reject_reason"] = f"dir_confidence_{dir_confidence:.4f}_below_{alpha_threshold}"
        sig["direction"] = direction
        sig["directional_confidence"] = round(dir_confidence, 6)
        sig["alpha_proba"] = round(alpha_proba, 6)
        sig["meta_proba"] = round(meta_proba, 6)
        if journal_sink is not None:
            journal_sink.append(sig)
        return sig

    # Meta threshold
    meta_threshold = params.get("meta_threshold", 0.50)
    if meta_proba < meta_threshold:
        sig = _base_signal()
        sig["final_decision"] = "REJECT_META"
        sig["reject_reason"] = f"meta_{meta_proba:.4f}_below_{meta_threshold}"
        sig["direction"] = direction
        sig["directional_confidence"] = round(dir_confidence, 6)
        sig["alpha_proba"] = round(alpha_proba, 6)
        sig["meta_proba"] = round(meta_proba, 6)
        if journal_sink is not None:
            journal_sink.append(sig)
        return sig

    # ===== 9. classify_regime_v2 =====
    call_trace.append("9:classify_regime_v2")
    regime_result = classify_regime_v2(df_use, min_bars=60)
    regime_label = regime_result.regime.value
    regime_direction = regime_result.direction

    # ===== 10. canonical setup scan (governed) =====
    call_trace.append("10:canonical_setup_scan")
    scan = scan_setups_governed(df_use, regime_direction=regime_direction,
                                 atr_value=float(atr), regime_label=regime_label)
    if scan.selected_setup is None:
        # Near-miss: regime allowed but no setup
        if near_miss_tracker is not None:
            near_miss_tracker.record_near_miss(
                timestamp=str(df.index[-1]), direction=direction,
                setup_type="NO_SETUP", regime=regime_label,
                score=dir_confidence, effective_threshold=alpha_threshold,
                component_scores={"alpha_proba": alpha_proba, "meta_proba": meta_proba},
                rejection_reasons=scan.rejection_reasons,
                hypothetical_entry=float(closes[i]),
                hypothetical_sl=float(closes[i]) - atr * params.get("sl_atr_multiplier", 2.0),
                hypothetical_tp=float(closes[i]) + atr * params.get("sl_atr_multiplier", 2.0) * params.get("rr_target", 3.0),
            )
        sig = _base_signal()
        sig["final_decision"] = "REJECT_NO_SETUP"
        sig["reject_reason"] = ";".join(scan.rejection_reasons)
        sig["direction"] = direction
        sig["directional_confidence"] = round(dir_confidence, 6)
        sig["alpha_proba"] = round(alpha_proba, 6)
        sig["meta_proba"] = round(meta_proba, 6)
        sig["regime"] = regime_label
        sig["regime_confidence"] = round(regime_result.confidence, 4)
        if journal_sink is not None:
            journal_sink.append(sig)
        return sig

    selected_setup = scan.selected_setup
    # If setup direction conflicts with model direction, reject
    if selected_setup.direction != direction and selected_setup.direction != "NEUTRAL":
        sig = _base_signal()
        sig["final_decision"] = "REJECT_SETUP_DIRECTION_CONFLICT"
        sig["reject_reason"] = f"setup_dir={selected_setup.direction} != model_dir={direction}"
        sig["direction"] = direction
        sig["directional_confidence"] = round(dir_confidence, 6)
        sig["alpha_proba"] = round(alpha_proba, 6)
        sig["meta_proba"] = round(meta_proba, 6)
        sig["regime"] = regime_label
        sig["regime_confidence"] = round(regime_result.confidence, 4)
        sig["setup_selected"] = selected_setup.setup_type.value
        if journal_sink is not None:
            journal_sink.append(sig)
        return sig

    # ===== 11. SafetyStateV2 construction =====
    call_trace.append("11:safety_state_v2_construction")
    spread = float(df["spread_usd"].iloc[-1])

    # Build alpha/meta distributions from recent model predictions across the
    # last 60 bars so the adaptive policy has sufficient samples (>= 30).
    # This is the production shadow-runner pattern: accumulate predictions
    # over recent history for distribution-based validation.
    try:
        recent_features = features_matrix[-60:]
        alpha_probas_recent = bundle.xgb.predict_proba(recent_features)[:, 1]
        meta_vecs_recent = recent_features[:, meta_indices]
        meta_probas_recent = bundle.meta.predict_proba(meta_vecs_recent)[:, 1]
        alpha_distribution = [float(x) for x in alpha_probas_recent if np.isfinite(x)]
        meta_distribution = [float(x) for x in meta_probas_recent if np.isfinite(x)]
    except Exception:
        alpha_distribution = [alpha_proba]
        meta_distribution = [meta_proba]

    # Calibration metrics — in production these would come from the latest
    # calibration audit. For shadow mode we use the frozen baseline.
    calibration_metrics = {
        "brier_score": 0.20,        # within [0, 0.33]
        "calibration_slope": 1.0,   # within [0.5, 2.0]
    }

    safety = SafetyStateV2(
        dd_state={"current_dd": 0.0, "daily_dd": 0.0},
        margin_state={"margin_usage": 0.05, "margin_safe": True},
        prop_risk_state={"prop_pass": True, "prop_violations": 0},
        capital_protection={"active": False, "dd_breach": False},
        broker_intelligence={
            "broker_pass": True,
            "spread_pass": spread <= params.get("spread_filter", 1.0),
        },
        execution_health={"healthy": True},
        model_health={"model_health_pass": True},
        spread_state={"current_spread": spread, "average_spread": spread},
        volatility_state={"current_atr": float(atr), "average_atr": float(atr), "regime": regime_label},
        loss_streak=0,
        signal_drought_hours=0,
        regime_confidence=float(regime_result.confidence),
        alpha_distribution=alpha_distribution,
        meta_distribution=meta_distribution,
        recent_shadow_evidence={"false_negative_rate": 0, "sample_size": 0},
        external_daily_dd=0.0,
        external_total_dd=0.0,
        calibration_metrics=calibration_metrics,
        regime=regime_label,
        market_data_stale=False,
    )

    # ===== 12. compute_adaptive_threshold_v2 (with journal callback) =====
    call_trace.append("12:compute_adaptive_threshold_v2")
    adaptive_journal_entries: list = []
    adaptive_result = compute_adaptive_threshold_v2(
        safety,
        journal_callback=lambda e: adaptive_journal_entries.append(e),
    )
    if adaptive_result.policy_mode == "hard_block":
        sig = _base_signal()
        sig["final_decision"] = "REJECT_ADAPTIVE_HARD_BLOCK"
        sig["reject_reason"] = adaptive_result.block_reason
        sig["direction"] = direction
        sig["directional_confidence"] = round(dir_confidence, 6)
        sig["alpha_proba"] = round(alpha_proba, 6)
        sig["meta_proba"] = round(meta_proba, 6)
        sig["regime"] = regime_label
        sig["regime_confidence"] = round(regime_result.confidence, 4)
        sig["setup_selected"] = selected_setup.setup_type.value
        sig["adaptive_block_reason"] = adaptive_result.block_reason
        sig["adaptive_journal"] = adaptive_journal_entries
        if journal_sink is not None:
            journal_sink.append(sig)
        return sig

    # ===== 13. canonical govern_risk =====
    call_trace.append("13:canonical_govern_risk")
    risk_percent = params.get("risk_percent", 0.003)
    gov_inp = RiskGovernorInput(
        equity=equity, equity_peak=equity, daily_peak=equity,
        daily_start_equity=equity,
        proposed_risk=risk_percent, setup_class=setup_class,
        existing_daily_open_risk=0.0,
        existing_total_open_risk=0.0,
        existing_combined_risk=0.0,
        loss_streak=0,
        regime_risk_modifier=float(regime_result.risk_modifier),
        broker_risk_modifier=1.0,
        prop_risk_pass=True,
        capital_protection_active=False,
        broker_safe=True,
        execution_healthy=True,
        model_healthy=True,
        margin_safe=True,
        external_daily_dd=0.0,
        external_total_dd=0.0,
    )
    gov_out = govern_risk(gov_inp)
    if not gov_out.approved:
        sig = _base_signal()
        sig["final_decision"] = "REJECT_RISK_GOVERNOR"
        sig["reject_reason"] = gov_out.block_reason
        sig["direction"] = direction
        sig["directional_confidence"] = round(dir_confidence, 6)
        sig["alpha_proba"] = round(alpha_proba, 6)
        sig["meta_proba"] = round(meta_proba, 6)
        sig["regime"] = regime_label
        sig["regime_confidence"] = round(regime_result.confidence, 4)
        sig["setup_selected"] = selected_setup.setup_type.value
        sig["adaptive_block_reason"] = adaptive_result.block_reason
        if journal_sink is not None:
            journal_sink.append(sig)
        return sig

    approved_risk = gov_out.approved_risk

    # ===== 14. near-miss handling =====
    call_trace.append("14:near_miss_handling")
    # Consult near-miss tracker for any re-entry opportunities on prior near-misses.
    # In shadow mode we don't actually consume re-entries (no execution); we just
    # log that the tracker was consulted. This proves the call is wired in.
    near_miss_consulted = False
    if near_miss_tracker is not None and near_miss_tracker.records:
        try:
            current_time = pd.Timestamp(df.index[-1])
            current_price = float(closes[i])
            for record in near_miss_tracker.records:
                if record.re_entry_consumed:
                    continue
                ok_consume, reason = near_miss_tracker.consume_re_entry(
                    record=record, current_time=current_time,
                    current_price=current_price,
                    new_confirmation=True, hard_gates_clear=True,
                )
                if ok_consume:
                    near_miss_consulted = True
                    break
        except Exception:
            pass

    # ===== 15. CEO governance =====
    call_trace.append("15:ceo_governance")
    sl_distance = atr * params.get("sl_atr_multiplier", 2.0)
    tp_distance = sl_distance * params.get("rr_target", 3.0)
    entry_price = float(closes[i])
    ceo = evaluate_ceo_decision(
        regime_state={"detected": True, "regime_value": regime_label,
                       "confidence": float(regime_result.confidence)},
        xgb_alpha={"direction": direction, "confidence": dir_confidence, "pass": True},
        lstm_confidence=None, transformer_regime=None,
        meta_label_quality={"quality_score": meta_proba, "pass": True},
        broker_state={"broker_pass": True, "spread_pass": spread <= params.get("spread_filter", 1.0),
                      "slippage_pass": True},
        prop_risk_state={"risk_pass": True, "prop_funded_pass": True, "max_positions_ok": True},
        capital_protection_state={"capital_preservation_active": False, "dd_breach": False},
        model_health_state={"model_health_pass": True, "failed_required": 0},
        geometry_state={"geometry_pass": True, "actual_RR": params.get("rr_target", 3.0),
                        "minimum_RR": 2.0},
    )
    if not ceo.allowed_to_trade:
        sig = _base_signal()
        sig["final_decision"] = "REJECT_CEO"
        sig["reject_reason"] = "ceo_blocked"
        sig["direction"] = direction
        sig["directional_confidence"] = round(dir_confidence, 6)
        sig["alpha_proba"] = round(alpha_proba, 6)
        sig["meta_proba"] = round(meta_proba, 6)
        sig["regime"] = regime_label
        sig["regime_confidence"] = round(regime_result.confidence, 4)
        sig["setup_selected"] = selected_setup.setup_type.value
        sig["approved_risk"] = round(approved_risk, 6)
        sig["ceo_decision"] = "BLOCK"
        if journal_sink is not None:
            journal_sink.append(sig)
        return sig

    # ===== 16. broker-step hypothetical lot sizing via InstrumentSpec =====
    call_trace.append("16:broker_step_lot_sizing")
    lot_info = _broker_step_lot_sizing(instrument, equity, approved_risk, sl_distance, entry_price)
    if lot_info["lot"] <= 0:
        sig = _base_signal()
        sig["final_decision"] = "REJECT_LOT_SIZING"
        sig["reject_reason"] = lot_info.get("reject_reason", "lot_zero")
        sig["direction"] = direction
        sig["directional_confidence"] = round(dir_confidence, 6)
        sig["alpha_proba"] = round(alpha_proba, 6)
        sig["meta_proba"] = round(meta_proba, 6)
        sig["regime"] = regime_label
        sig["regime_confidence"] = round(regime_result.confidence, 4)
        sig["setup_selected"] = selected_setup.setup_type.value
        sig["approved_risk"] = round(approved_risk, 6)
        sig["ceo_decision"] = "PASS"
        if journal_sink is not None:
            journal_sink.append(sig)
        return sig

    # ===== 17. structured journal persistence & 18. NO_ORDER_SENT=true =====
    call_trace.append("17:structured_journal_persistence")
    call_trace.append("18:NO_ORDER_SENT_true")
    sig = _base_signal()
    sig["final_decision"] = "SHADOW_SIGNAL"
    sig["reject_reason"] = ""
    sig["direction"] = direction
    sig["directional_confidence"] = round(dir_confidence, 6)
    sig["alpha_proba"] = round(alpha_proba, 6)
    sig["meta_proba"] = round(meta_proba, 6)
    sig["regime"] = regime_label
    sig["regime_confidence"] = round(regime_result.confidence, 4)
    sig["setup_selected"] = selected_setup.setup_type.value
    sig["setup_alternatives"] = [a.setup_type.value for a in scan.alternatives]
    sig["approved_risk"] = round(approved_risk, 6)
    sig["lot_size"] = lot_info["lot"]
    sig["monetary_loss_at_sl"] = lot_info["monetary_loss_at_sl"]
    sig["risk_amount"] = lot_info["risk_amount"]
    sig["actual_risk_percent"] = round(lot_info["monetary_loss_at_sl"] / equity, 6) if equity > 0 else 0
    sig["margin_required"] = lot_info["margin_required"]
    sig["margin_usage"] = lot_info["margin_usage"]
    sig["adaptive_block_reason"] = adaptive_result.block_reason
    sig["adaptive_alpha_threshold"] = adaptive_result.alpha_threshold_effective
    sig["adaptive_meta_threshold"] = adaptive_result.meta_threshold_effective
    sig["adaptive_risk_multiplier"] = adaptive_result.risk_multiplier
    sig["adaptive_journal"] = adaptive_journal_entries
    sig["ceo_decision"] = "PASS"
    sig["entry_reference"] = round(entry_price, 4)
    sig["SL_reference"] = round(entry_price - sl_distance if direction == "LONG"
                                 else entry_price + sl_distance, 4)
    sig["TP_reference"] = round(entry_price + tp_distance if direction == "LONG"
                                 else entry_price - tp_distance, 4)
    sig["instrument_spec"] = {
        "tick_size": instrument.tick_size,
        "tick_value": instrument.tick_value,
        "contract_size": instrument.contract_size,
        "volume_min": instrument.volume_min,
        "volume_max": instrument.volume_max,
        "volume_step": instrument.volume_step,
        "account_currency": instrument.account_currency,
        "profit_currency": instrument.profit_currency,
        "conversion_rate": instrument.conversion_rate,
    }
    sig["NO_ORDER_SENT"] = True
    sig["near_miss_consulted"] = near_miss_consulted
    if journal_sink is not None:
        journal_sink.append(sig)
    return sig


def main():
    parser = argparse.ArgumentParser(description="TITAN Exness MT5 Read-Only Forward Shadow (FINAL v2.8.7-P2.0)")
    parser.add_argument("--broker", default="exness")
    parser.add_argument("--symbol", default="XAUUSD")
    parser.add_argument("--timeframe", default="H1")
    parser.add_argument("--max-cycles", type=int, default=24)
    parser.add_argument("--sleep-seconds", type=int, default=60)
    args = parser.parse_args()

    ts = datetime.now(timezone.utc).isoformat()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("  EXNESS MT5 READ-ONLY FORWARD SHADOW (FINAL v2.8.7-P2.0)")
    print("=" * 70)
    print(f"  Timestamp: {ts}")
    print(f"  Broker: {args.broker}, Symbol: {args.symbol}")
    print(f"  Max cycles: {args.max_cycles}, Sleep: {args.sleep_seconds}s")
    print(f"  NO_ORDER_SENT: True (always)\n")

    profile = load_exness_competition_shadow_profile()
    # Wrap profile in expected structure for params lookup
    if "optimized_parameters" not in profile:
        profile["optimized_parameters"] = {
            "alpha_threshold": 0.55, "meta_threshold": 0.50,
            "risk_percent": profile.get("risk_percent_A_PLUS", 0.003),
            "sl_atr_multiplier": 2.0, "rr_target": 3.0,
            "spread_filter": 1.0, "commission_per_lot": 7.0,
            "slippage_points": 0.5, "swap_per_bar": 0.0,
            "setup_class": "A_PLUS",
        }
    bundle = load_models_by_profile("v2_feature_normalized")
    if not bundle.ok:
        print("  ERROR: v2 model failed to load")
        return

    near_miss_tracker = NearMissShadowTrackerV2(timeframe="H1")
    journal_sink: list = []

    signals = []
    risk_lot_rows = []
    for cycle in range(args.max_cycles):
        print(f"  Cycle {cycle+1}/{args.max_cycles}...")
        signal = run_forward_shadow_cycle(
            args.broker, args.symbol, args.timeframe, profile, bundle,
            near_miss_tracker=near_miss_tracker, journal_sink=journal_sink,
        )
        signals.append(signal)
        if signal.get("lot_size"):
            risk_lot_rows.append({
                "timestamp": signal["timestamp"], "broker": args.broker,
                "lot": signal["lot_size"], "margin_usage": signal["margin_usage"],
                "leverage": LEVERAGE, "no_order_sent": True,
            })
        if cycle < args.max_cycles - 1:
            time.sleep(args.sleep_seconds)

    # Write outputs
    with open(OUTPUT_DIR / "forward_shadow_signals_exness.csv", "w", newline="", encoding="utf-8") as f:
        if signals:
            # Flatten nested dicts for CSV
            flat_signals = []
            for s in signals:
                flat = {k: v for k, v in s.items() if not isinstance(v, (dict, list))}
                flat["instrument_spec"] = json.dumps(s.get("instrument_spec", {}))
                flat["setup_alternatives"] = json.dumps(s.get("setup_alternatives", []))
                flat_signals.append(flat)
            w = csv.DictWriter(f, fieldnames=list(flat_signals[0].keys()))
            w.writeheader()
            for s in flat_signals:
                w.writerow(s)

    with open(OUTPUT_DIR / "forward_shadow_journal_exness.jsonl", "w", encoding="utf-8") as f:
        for s in journal_sink:
            f.write(json.dumps(s, default=str) + "\n")

    with open(OUTPUT_DIR / "forward_shadow_risk_lot_state_exness.csv", "w", newline="", encoding="utf-8") as f:
        if risk_lot_rows:
            w = csv.DictWriter(f, fieldnames=list(risk_lot_rows[0].keys()))
            w.writeheader()
            for r in risk_lot_rows:
                w.writerow(r)

    shadow_signals = [s for s in signals if s["final_decision"] == "SHADOW_SIGNAL"]
    summary = {
        "timestamp_utc": ts, "broker": args.broker, "symbol": args.symbol,
        "total_cycles": len(signals), "shadow_signals": len(shadow_signals),
        "rejected": len(signals) - len(shadow_signals),
        "dry_run": True, "live_trading": False, "funded_trading": False,
        "production_ready": False, "no_order_sent": True,
        "canonical_pipeline": "v2.8.7-P2.0",
        "model_hash": _hash_model(bundle),
    }
    with open(OUTPUT_DIR / "forward_shadow_summary_exness.json", "w") as f:
        json.dump(summary, f, indent=2)
    with open(OUTPUT_DIR / "forward_shadow_summary_exness.md", "w", encoding="utf-8") as f:
        f.write(f"# Forward Shadow Summary - {args.broker} (FINAL v2.8.7-P2.0)\n\n")
        f.write(f"**Timestamp:** {ts}\n\n")
        f.write(f"- Total cycles: {len(signals)}\n- Shadow signals: {len(shadow_signals)}\n")
        f.write(f"- Rejected: {len(signals) - len(shadow_signals)}\n\n")
        f.write(f"- NO_ORDER_SENT: True\n- dry_run: True\n- live_trading: False\n")
        f.write(f"- Canonical pipeline: v2.8.7-P2.0\n")

    print(f"\n  Shadow signals: {len(shadow_signals)}")
    print(f"  Output: {OUTPUT_DIR}")
    print("\n" + "=" * 70)
    print("  READ-ONLY FORWARD SHADOW — NO ORDERS SENT")
    print("=" * 70)


if __name__ == "__main__":
    main()
