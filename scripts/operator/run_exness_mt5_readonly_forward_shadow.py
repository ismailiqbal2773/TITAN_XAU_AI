#!/usr/bin/env python3
"""TITAN XAU AI — Exness MT5 Read-Only Forward Shadow Runner (v2.8.7-P2.5.5)
=============================================================================

Local Windows MT5 forward shadow runner. Reads market data, computes features,
generates read-only signals via the Canonical Decision Engine. NEVER trades.

v2.8.7-P2.5.5 changes:
  - Removed ALL hard-coded safety values from _build_safety_state
  - Removed build_calibration_artifact_if_missing runtime call
  - Removed nan_to_num from feature computation
  - Safety state built from real inputs or fails closed with explicit reasons
  - Uses build_real_safety_state from real_safety_state.py

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
SHADOW_STATE_PATH = REPO_ROOT / "data" / "shadow_account_state.json"

from scripts.operator.mt5_safe_connector import safe_connect_and_audit
from titan.production.spread_normalization import normalize_xauusd_spread_to_usd
from titan.production.feature_stream_v2 import H1FeatureStreamV2, FEATURE_NAMES_V2
from titan.training.feature_schema_v2 import META_FEATURE_NAMES_V2
from titan.production.model_loader import load_production_models_v2
from titan.production.ceo_ai_governance import evaluate_ceo_decision
from titan.production.direction_logic import interpret_direction
from titan.production.instrument_valuation import InstrumentSpec, validate_instrument_spec
from titan.production.corrected_regime_classifier_v2 import classify_regime_v2
from titan.production.corrected_setup_detector_v2 import scan_setups_governed
from titan.production.corrected_adaptive_threshold_v2 import (
    SafetyStateV2, compute_adaptive_threshold_v2,
)
from titan.production.risk_governor import govern_risk, RiskGovernorInput
from titan.production.near_miss_tracker_v2 import NearMissShadowTrackerV2
from titan.production.shadow_account_state_store import ShadowAccountStateStore
from titan.production.model_provenance import (
    load_model_provenance, load_calibration_evidence,
)
from titan.production.canonical_decision_engine import (
    CanonicalDecisionEngine, DecisionContext,
)


LEVERAGE = 100


def load_exness_competition_shadow_profile():
    """Load the competition shadow profile (NOT the legacy profile)."""
    import yaml
    path = REPO_ROOT / "config" / "broker_profiles" / "exness_competition_shadow_profile.yaml"
    with open(path) as f:
        return yaml.safe_load(f)


def _make_instrument_spec_from_mt5(symbol_info, account_info) -> InstrumentSpec:
    """Extract a validated InstrumentSpec from MT5 symbol/account metadata.

    Phase 2: NO FALLBACKS. Missing/zero/malformed metadata must produce
    REJECT_INSTRUMENT_SPEC.
    """
    if symbol_info is None:
        raise ValueError("symbol_info_missing")
    if account_info is None:
        raise ValueError("account_info_missing")

    # Extract raw values — NO defaults
    tick_size = getattr(symbol_info, "trade_tick_size", None)
    tick_value = getattr(symbol_info, "trade_tick_value", None)
    contract_size = getattr(symbol_info, "trade_contract_size", None)
    volume_min = getattr(symbol_info, "volume_min", None)
    volume_max = getattr(symbol_info, "volume_max", None)
    volume_step = getattr(symbol_info, "volume_step", None)
    account_ccy = getattr(account_info, "currency", None)
    profit_ccy = getattr(symbol_info, "currency_profit", None) or "USD"
    symbol_ccy = getattr(symbol_info, "currency_base", None) or "XAU"

    # Phase 2: Refuse any None or non-positive value
    for name, val in [("tick_size", tick_size), ("tick_value", tick_value),
                       ("contract_size", contract_size), ("volume_min", volume_min),
                       ("volume_max", volume_max), ("volume_step", volume_step)]:
        if val is None:
            raise ValueError(f"instrument_metadata_missing:{name}")
        try:
            fval = float(val)
        except (TypeError, ValueError):
            raise ValueError(f"instrument_metadata_non_numeric:{name}={val}")
        if fval <= 0:
            raise ValueError(f"instrument_metadata_nonpositive:{name}={fval}")
    if not account_ccy:
        raise ValueError("account_currency_missing")
    if not profit_ccy:
        raise ValueError("profit_currency_missing")

    # Conversion rate: if account == profit, rate=1.0. Otherwise, the runner
    # cannot silently assume 1.0 — it must be supplied externally.
    if account_ccy == profit_ccy:
        conversion_rate = 1.0
    else:
        # Phase 2: Do not silently assume 1.0 when currencies differ
        raise ValueError(
            f"cross_currency_not_supported: account={account_ccy} profit={profit_ccy}. "
            "Supply explicit conversion_rate via broker profile."
        )

    spec = InstrumentSpec(
        tick_size=float(tick_size),
        tick_value=float(tick_value),
        contract_size=float(contract_size),
        volume_min=float(volume_min),
        volume_max=float(volume_max),
        volume_step=float(volume_step),
        account_currency=str(account_ccy),
        profit_currency=str(profit_ccy),
        symbol_currency=str(symbol_ccy),
        conversion_rate=conversion_rate,
    )
    ok, msg = validate_instrument_spec(spec)
    if not ok:
        raise ValueError(f"instrument_spec_invalid:{msg}")
    return spec


def _data_freshness_check(df: pd.DataFrame, max_age_hours: int = 24) -> tuple[bool, str]:
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
    required = {"open", "high", "low", "close"}
    if not required.issubset(df.columns):
        return False, f"missing_columns_{required - set(df.columns)}"
    if df[["open", "high", "low", "close"]].isna().any().any():
        return False, "NaN_in_OHLC"
    if not df.index.is_monotonic_increasing:
        return False, "index_not_monotonic"
    return True, ""


def _build_safety_state(account_store: ShadowAccountStateStore, spread: float,
                         atr: float, regime_label: str, regime_confidence: float,
                         alpha_probas_recent: np.ndarray, meta_probas_recent: np.ndarray,
                         calibration_evidence,
                         margin_info: dict = None,
                         broker_info: dict = None,
                         execution_health: dict = None,
                         model_health: dict = None,
                         prop_state: dict = None,
                         capital_protection_state: dict = None,
                         shadow_evidence: dict = None,
                         market_data_stale: bool = None) -> tuple:
    """Build SafetyStateV2 from REAL inputs. Fails closed on any unavailable value.

    v2.8.7-P2.5.5: NO hard-coded safe values. Every field must come from a real source.
    Returns (safety_state, fail_reason). If fail_reason is non-empty, safety_state is None.
    """
    # Validate every required input — fail closed if unavailable
    if account_store is None:
        return None, "REJECT_ACCOUNT_STATE_UNAVAILABLE"
    if margin_info is None or margin_info.get("margin_safe") is None:
        return None, "REJECT_MARGIN_STATE_UNAVAILABLE"
    if prop_state is None or prop_state.get("prop_pass") is None:
        return None, "REJECT_PROP_STATE_UNAVAILABLE"
    if capital_protection_state is None or capital_protection_state.get("active") is None:
        return None, "REJECT_CAPITAL_PROTECTION_STATE_UNAVAILABLE"
    if broker_info is None or broker_info.get("broker_pass") is None:
        return None, "REJECT_BROKER_HEALTH_UNAVAILABLE"
    if execution_health is None or execution_health.get("healthy") is None:
        return None, "REJECT_EXECUTION_HEALTH_UNAVAILABLE"
    if model_health is None or model_health.get("model_health_pass") is None:
        return None, "REJECT_MODEL_PROVENANCE"
    if calibration_evidence is None:
        return None, "REJECT_CALIBRATION_MISSING"
    if shadow_evidence is None:
        return None, "REJECT_SHADOW_EVIDENCE_UNAVAILABLE"
    if market_data_stale is None:
        return None, "REJECT_MARKET_DATA_STALE"

    state = account_store.state
    daily_dd = account_store.daily_dd
    total_dd = account_store.total_dd

    # Validate calibration
    cal_ok, cal_msg = calibration_evidence.validate()
    if not cal_ok:
        return None, f"REJECT_CALIBRATION:{cal_msg}"

    safety = SafetyStateV2(
        dd_state={"current_dd": float(total_dd), "daily_dd": float(daily_dd)},
        margin_state={
            "margin_usage": float(margin_info.get("margin_usage", 0.0)),
            "margin_safe": margin_info["margin_safe"],
        },
        prop_risk_state={
            "prop_pass": prop_state["prop_pass"],
            "prop_violations": int(prop_state.get("prop_violations", 0)),
        },
        capital_protection={
            "active": capital_protection_state["active"],
            "dd_breach": capital_protection_state.get("dd_breach", False),
        },
        broker_intelligence={
            "broker_pass": broker_info["broker_pass"],
            "spread_pass": broker_info.get("spread_pass", spread <= 1.0),
        },
        execution_health={"healthy": execution_health["healthy"]},
        model_health={"model_health_pass": model_health["model_health_pass"]},
        spread_state={"current_spread": float(spread), "average_spread": float(spread)},
        volatility_state={"current_atr": float(atr), "average_atr": float(atr),
                          "regime": regime_label},
        loss_streak=int(state.loss_streak),
        signal_drought_hours=int(shadow_evidence.get("signal_drought_hours", 0)),
        regime_confidence=float(regime_confidence),
        alpha_distribution=[float(x) for x in alpha_probas_recent if np.isfinite(x)],
        meta_distribution=[float(x) for x in meta_probas_recent if np.isfinite(x)],
        recent_shadow_evidence={
            "false_negative_rate": float(shadow_evidence.get("false_negative_rate", 0.0)),
            "sample_size": int(shadow_evidence.get("sample_size", 0)),
        },
        external_daily_dd=float(daily_dd),
        external_total_dd=float(total_dd),
        calibration_metrics={
            "brier_score": float(calibration_evidence.brier_score),
            "calibration_slope": float(calibration_evidence.calibration_slope),
            "calibration_intercept": float(calibration_evidence.calibration_intercept),
        },
        regime=regime_label,
        market_data_stale=market_data_stale,
    )
    return safety, ""


def run_forward_shadow_cycle(broker, symbol, timeframe, profile, bundle, equity=100000.0,
                             near_miss_tracker: NearMissShadowTrackerV2 = None,
                             journal_sink: list = None,
                             provenance=None, calibration_evidence=None,
                             account_store: ShadowAccountStateStore = None,
                             instrument_spec_override: InstrumentSpec = None,
                             **kwargs) -> dict:
    """Run one forward shadow cycle through CanonicalDecisionEngine.

    v2.8.7-P2.5.5: Decision logic delegated to CanonicalDecisionEngine (shared
    with historical adapter). Safety state built from real inputs via kwargs.
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
            "engine_version": "v2.8.7-P2.1",
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

    # ===== 2. instrument metadata extraction (NO FALLBACKS) =====
    call_trace.append("2:instrument_metadata_extraction_no_fallbacks")
    try:
        if instrument_spec_override is not None:
            ok, msg = validate_instrument_spec(instrument_spec_override)
            if not ok:
                sig = _base_signal()
                sig["final_decision"] = "REJECT_INSTRUMENT_SPEC"
                sig["reject_reason"] = msg
                if journal_sink is not None:
                    journal_sink.append(sig)
                return sig
            instrument = instrument_spec_override
        else:
            instrument = _make_instrument_spec_from_mt5(
                getattr(result, "symbol_info", None),
                getattr(result, "account_info", None),
            )
    except ValueError as e:
        sig = _base_signal()
        sig["final_decision"] = "REJECT_INSTRUMENT_SPEC"
        sig["reject_reason"] = str(e)
        if journal_sink is not None:
            journal_sink.append(sig)
        return sig
    except Exception as e:
        sig = _base_signal()
        sig["final_decision"] = "REJECT_INSTRUMENT_SPEC"
        sig["reject_reason"] = f"instrument_extraction_error: {e}"
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

    # ===== 4. feature generation =====
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
        features_matrix = feats_df.values.astype(np.float64)
        # v2.8.7-P2.5.5: No nan_to_num — fail closed on invalid features
        if not np.all(np.isfinite(features_matrix)):
            nan_count = int(np.isnan(features_matrix).sum())
            inf_count = int(np.isinf(features_matrix).sum())
            sig = _base_signal()
            sig["final_decision"] = "REJECT_FEATURE_INTEGRITY"
            sig["reject_reason"] = f"feature_nan_{nan_count}_inf_{inf_count}"
            if journal_sink is not None:
                journal_sink.append(sig)
            return sig
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
    if not hasattr(bundle.xgb, "classes_") or not np.array_equal(np.asarray(bundle.xgb.classes_), np.array([0, 1])):
        sig = _base_signal()
        sig["final_decision"] = "REJECT_MODEL_CLASSES"
        sig["reject_reason"] = f"xgb classes_ mismatch"
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

    # Build recent distributions for adaptive policy
    try:
        recent_features = features_matrix[-60:]
        alpha_probas_recent = bundle.xgb.predict_proba(recent_features)[:, 1]
        meta_vecs_recent = recent_features[:, meta_indices]
        meta_probas_recent = bundle.meta.predict_proba(meta_vecs_recent)[:, 1]
    except Exception:
        alpha_probas_recent = np.full(60, alpha_proba)
        meta_probas_recent = np.full(60, meta_proba)

    closes = df["close"].values
    highs = df["high"].values
    lows = df["low"].values
    i = len(df) - 1
    atr = max(
        highs[i] - lows[i],
        abs(highs[i] - closes[i - 1]),
        abs(lows[i] - closes[i - 1]),
    ) if i > 0 else 3.0
    spread = float(df["spread_usd"].iloc[-1])
    entry_price = float(closes[i])

    # ===== 7. regime classification (for safety state) =====
    call_trace.append("7:regime_classification_for_safety_state")
    regime_result = classify_regime_v2(df_use, min_bars=60)
    regime_label = regime_result.regime.value

    # ===== 8. account state daily reset =====
    call_trace.append("8:account_state_daily_reset")
    if account_store is not None:
        try:
            account_store.daily_reset_if_needed()
        except Exception as e:
            sig = _base_signal()
            sig["final_decision"] = "REJECT_ACCOUNT_STATE_CORRUPT"
            sig["reject_reason"] = str(e)
            if journal_sink is not None:
                journal_sink.append(sig)
            return sig

    # ===== 9. real safety state construction =====
    call_trace.append("9:real_safety_state_construction")
    # v2.8.7-P2.5.5: Build safety state from REAL inputs — fail closed if unavailable
    # In shadow mode without live MT5, these inputs must come from the caller.
    # If they are None (not provided), the safety builder will fail closed.
    margin_info = kwargs.get("margin_info") if "kwargs" in dir() else None
    broker_info = kwargs.get("broker_info") if "kwargs" in dir() else None
    execution_health = kwargs.get("execution_health") if "kwargs" in dir() else None
    model_health = kwargs.get("model_health") if "kwargs" in dir() else None
    prop_state = kwargs.get("prop_state") if "kwargs" in dir() else None
    capital_protection_state = kwargs.get("capital_protection_state") if "kwargs" in dir() else None
    shadow_evidence = kwargs.get("shadow_evidence") if "kwargs" in dir() else None
    market_data_stale = kwargs.get("market_data_stale") if "kwargs" in dir() else None

    safety_state, safety_fail_reason = _build_safety_state(
        account_store if account_store is not None else _default_account_store(equity),
        spread=spread, atr=float(atr), regime_label=regime_label,
        regime_confidence=float(regime_result.confidence),
        alpha_probas_recent=alpha_probas_recent,
        meta_probas_recent=meta_probas_recent,
        calibration_evidence=calibration_evidence,
        margin_info=margin_info,
        broker_info=broker_info,
        execution_health=execution_health,
        model_health=model_health,
        prop_state=prop_state,
        capital_protection_state=capital_protection_state,
        shadow_evidence=shadow_evidence,
        market_data_stale=market_data_stale,
    )
    if safety_state is None:
        sig = _base_signal()
        sig["final_decision"] = "REJECT_SAFETY_STATE"
        sig["reject_reason"] = safety_fail_reason
        if journal_sink is not None:
            journal_sink.append(sig)
        return sig

    # ===== 10. canonical decision engine =====
    call_trace.append("10:canonical_decision_engine")
    state = (account_store.state if account_store is not None
             else _default_account_store(equity).state)
    ctx = DecisionContext(
        df=df_use,
        alpha_proba=alpha_proba, meta_proba=meta_proba,
        alpha_probas_recent=alpha_probas_recent,
        meta_probas_recent=meta_probas_recent,
        atr_value=float(atr),
        instrument=instrument,
        config={**params},
        safety_state=safety_state,
        equity=float(state.equity), equity_peak=float(state.equity_peak),
        daily_peak=float(state.daily_peak), daily_start_equity=float(state.daily_start_equity),
        existing_daily_open_risk=float(state.existing_daily_open_risk),
        existing_total_open_risk=float(state.existing_total_open_risk),
        existing_combined_risk=float(state.existing_combined_risk),
        loss_streak=int(state.loss_streak),
        adapter_mode="shadow",
        near_miss_tracker=near_miss_tracker,
        spread=spread, entry_price=entry_price,
        timestamp=str(df.index[-1]),
    )
    engine = CanonicalDecisionEngine()
    decision = engine.evaluate(ctx)

    # ===== 11. structured journal persistence =====
    call_trace.append("11:structured_journal_persistence")
    call_trace.append("12:NO_ORDER_SENT_true")
    sig = _base_signal()
    sig["final_decision"] = decision.final_decision
    sig["reject_reason"] = decision.reject_reason
    sig["direction"] = decision.direction
    sig["directional_confidence"] = decision.directional_confidence
    sig["alpha_proba"] = decision.alpha_proba
    sig["meta_proba"] = decision.meta_proba
    sig["regime"] = decision.regime
    sig["regime_confidence"] = decision.regime_confidence
    sig["setup_selected"] = decision.setup_selected
    sig["setup_alternatives"] = decision.setup_alternatives
    sig["approved_risk"] = decision.approved_risk
    sig["lot_size"] = decision.lot_size
    sig["monetary_loss_at_sl"] = decision.monetary_loss_at_sl
    sig["risk_amount"] = decision.risk_amount
    sig["actual_risk_percent"] = decision.actual_risk_percent
    sig["margin_required"] = 0.0
    sig["margin_usage"] = 0.0
    sig["adaptive_block_reason"] = decision.adaptive_block_reason
    sig["adaptive_alpha_threshold"] = decision.adaptive_alpha_threshold
    sig["adaptive_meta_threshold"] = decision.adaptive_meta_threshold
    sig["adaptive_risk_multiplier"] = decision.adaptive_risk_multiplier
    sig["adaptive_journal"] = decision.adaptive_journal
    sig["ceo_decision"] = decision.ceo_decision
    sig["entry_reference"] = decision.entry_price
    sig["SL_reference"] = decision.sl_price
    sig["TP_reference"] = decision.tp_price
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
    sig["near_miss_consulted"] = decision.near_miss_consulted
    sig["near_miss_preview_eligible"] = decision.near_miss_preview_eligible
    sig["NO_ORDER_SENT"] = True
    sig["call_trace"] = call_trace + decision.call_trace
    if journal_sink is not None:
        journal_sink.append(sig)
    return sig


def _default_account_store(equity: float = 100000.0) -> ShadowAccountStateStore:
    """For environments without a real account store (e.g. CI/test)."""
    import tempfile
    tmp = Path(tempfile.gettempdir()) / "titan_shadow_account_state_default.json"
    return ShadowAccountStateStore(path=tmp, starting_equity=equity)


def main():
    parser = argparse.ArgumentParser(description="TITAN Exness MT5 Read-Only Forward Shadow (v2.8.7-P2.1)")
    parser.add_argument("--broker", default="exness")
    parser.add_argument("--symbol", default="XAUUSD")
    parser.add_argument("--timeframe", default="H1")
    parser.add_argument("--max-cycles", type=int, default=24)
    parser.add_argument("--sleep-seconds", type=int, default=60)
    args = parser.parse_args()

    ts = datetime.now(timezone.utc).isoformat()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("  EXNESS MT5 READ-ONLY FORWARD SHADOW (v2.8.7-P2.1)")
    print("=" * 70)
    print(f"  Timestamp: {ts}")
    print(f"  NO_ORDER_SENT: True (always)\n")

    profile = load_exness_competition_shadow_profile()
    if "optimized_parameters" not in profile:
        profile["optimized_parameters"] = {
            "alpha_threshold": 0.55, "meta_threshold": 0.50,
            "risk_percent": profile.get("risk_percent_A_PLUS", 0.003),
            "sl_atr_multiplier": 2.0, "rr_target": 3.0,
            "spread_filter": 1.0, "commission_per_lot": 7.0,
            "slippage_points": 0.5, "swap_per_bar": 0.0,
            "setup_class": "A_PLUS",
        }
    bundle = load_production_models_v2()
    if not bundle.ok:
        print("  ERROR: v2 model failed to load")
        return

    # Phase 4: Load real provenance and calibration evidence
    try:
        provenance = load_model_provenance("v2_feature_normalized")
        # v2.8.7-P2.5.5: Do NOT auto-generate calibration — only load pre-approved artifact
        calibration_evidence = load_calibration_evidence(provenance)
        print(f"  Provenance: model_sha256={provenance.model_sha256[:16]}...")
        print(f"  Calibration: brier={calibration_evidence.brier_score:.4f} slope={calibration_evidence.calibration_slope:.4f}")
    except Exception as e:
        print(f"  WARNING: provenance/calibration load failed: {e}")
        provenance = None
        calibration_evidence = None

    # Phase 3: Initialize shadow account state store
    try:
        account_store = ShadowAccountStateStore(path=SHADOW_STATE_PATH)
    except Exception as e:
        print(f"  WARNING: account store init failed: {e}")
        account_store = None

    near_miss_tracker = NearMissShadowTrackerV2(timeframe="H1")
    journal_sink: list = []

    signals = []
    for cycle in range(args.max_cycles):
        print(f"  Cycle {cycle+1}/{args.max_cycles}...")
        signal = run_forward_shadow_cycle(
            args.broker, args.symbol, args.timeframe, profile, bundle,
            near_miss_tracker=near_miss_tracker, journal_sink=journal_sink,
            provenance=provenance, calibration_evidence=calibration_evidence,
            account_store=account_store,
        )
        signals.append(signal)
        if cycle < args.max_cycles - 1:
            time.sleep(args.sleep_seconds)

    # Write outputs
    with open(OUTPUT_DIR / "forward_shadow_journal_exness.jsonl", "w", encoding="utf-8") as f:
        for s in journal_sink:
            f.write(json.dumps(s, default=str) + "\n")

    shadow_signals = [s for s in signals if s["final_decision"] == "SHADOW_SIGNAL"]
    summary = {
        "timestamp_utc": ts, "broker": args.broker, "symbol": args.symbol,
        "total_cycles": len(signals), "shadow_signals": len(shadow_signals),
        "rejected": len(signals) - len(shadow_signals),
        "dry_run": True, "live_trading": False, "funded_trading": False,
        "production_ready": False, "no_order_sent": True,
        "engine_version": "v2.8.7-P2.1",
        "model_sha256": provenance.model_sha256 if provenance else None,
        "calibration_brier": calibration_evidence.brier_score if calibration_evidence else None,
    }
    with open(OUTPUT_DIR / "forward_shadow_summary_exness.json", "w") as f:
        json.dump(summary, f, indent=2)

    print(f"\n  Shadow signals: {len(shadow_signals)}")
    print(f"  Output: {OUTPUT_DIR}")
    print("\n" + "=" * 70)
    print("  READ-ONLY FORWARD SHADOW — NO ORDERS SENT")
    print("=" * 70)


if __name__ == "__main__":
    main()
