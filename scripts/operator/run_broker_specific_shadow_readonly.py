#!/usr/bin/env python3
"""TITAN XAU AI - Broker-Specific Read-Only Shadow Runner (Sprint v2.8.7-K)
=============================================================================
Read-only shadow runner for broker-specific prop profiles.

Rules:
  - read-only only
  - no order_send
  - no token creation
  - no live/funded
  - production_ready false
  - journal every decision
  - log broker-specific calibration

NEVER sends orders. NEVER creates tokens. NEVER trades.
"""
from __future__ import annotations
import sys, json, csv, os, argparse
from pathlib import Path
from datetime import datetime, timezone
import numpy as np
import pandas as pd
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

OUTPUT_DIR = REPO_ROOT / "data" / "reports" / "broker_specific_shadow"

from titan.production.spread_normalization import normalize_xauusd_spread_to_usd
from titan.production.feature_stream_v2 import H1FeatureStreamV2, FEATURE_NAMES_V2
from titan.training.feature_schema_v2 import META_FEATURE_NAMES_V2
from titan.production.model_loader import load_models_by_profile
from titan.production.ceo_ai_governance import evaluate_ceo_decision
from titan.production.mtf_confirmation import evaluate_mtf, load_m15_bars, load_m5_bars, reset_mtf_caches


BROKER_PATHS = {
    "canonical": REPO_ROOT / "titan" / "data" / "canonical" / "XAUUSD_H1_canonical.parquet",
    "exness": REPO_ROOT / "titan" / "data" / "sources" / "mt5_brokers" / "exness" / "XAUUSD_H1.parquet",
    "fbs": REPO_ROOT / "titan" / "data" / "sources" / "mt5_brokers" / "fbs" / "XAUUSD_H1.parquet",
    "fundednext": REPO_ROOT / "titan" / "data" / "sources" / "mt5_brokers" / "fundednext" / "XAUUSD_H1.parquet",
    "icmarkets": REPO_ROOT / "titan" / "data" / "sources" / "mt5_brokers" / "icmarkets" / "XAUUSD_H1.parquet",
}


def load_broker_profile(broker):
    """Load broker-specific calibrated profile."""
    profile_path = REPO_ROOT / "config" / "broker_profiles" / f"{broker}_prop_profile.yaml"
    if not profile_path.exists():
        return None
    with open(profile_path) as f:
        return yaml.safe_load(f)


def load_broker_data(broker):
    path = BROKER_PATHS.get(broker)
    if path is None or not path.exists():
        return None
    df = pd.read_parquet(path)
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)
    df = normalize_xauusd_spread_to_usd(df, symbol="XAUUSD", source=broker)
    return df


def compute_predictions(df, bundle):
    df_use = df[["open", "high", "low", "close"]].copy()
    if "tick_volume" in df.columns:
        df_use["volume"] = df["tick_volume"]
    else:
        df_use["volume"] = 0.0
    df_use["spread"] = df["spread_usd"]
    stream = H1FeatureStreamV2()
    stream._bars = df_use
    feats_df = stream._compute_features()
    features_matrix = np.nan_to_num(feats_df.values.astype(np.float64), nan=0.0, posinf=0.0, neginf=0.0)
    features_matrix = stream._standardize(features_matrix)
    alpha_proba = bundle.xgb.predict_proba(features_matrix)[:, 1]
    name_to_idx = {n: i for i, n in enumerate(FEATURE_NAMES_V2)}
    meta_indices = [name_to_idx[n] for n in META_FEATURE_NAMES_V2]
    meta_vecs = features_matrix[:, meta_indices]
    meta_proba = bundle.meta.predict_proba(meta_vecs)[:, 1]
    highs, lows, closes = df["high"].values, df["low"].values, df["close"].values
    atr_values = np.zeros(len(df))
    for i in range(14, len(df)):
        atr_values[i] = max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1]))
    for i in range(28, len(df)):
        atr_values[i] = np.mean(atr_values[i-14:i])
    return alpha_proba, meta_proba, atr_values


def run_shadow(broker, df, alpha_proba, meta_proba, atr_values, profile, max_signals=100):
    """Run read-only shadow for a broker."""
    signals = []
    risk_state_rows = []
    closes = df["close"].values
    index = df.index

    cal = profile["calibrated_thresholds"]
    params = {
        "alpha_threshold": cal["alpha_threshold"],
        "meta_threshold": cal["meta_threshold"],
        "sl_atr_multiplier": 2.0, "rr_target": 3.0,
        "max_holding_bars": 3, "risk_percent": profile["risk_percent"],
        "max_trades_per_day": profile["max_trades_per_day"],
        "cooldown_after_loss": profile["cooldown_after_loss"],
        "session_filter": profile["session_filter"],
        "spread_filter": profile["spread_filter"],
        "mtf_mode": profile["mtf_mode"],
    }

    # Use OOS 2025-2026
    oos_mask = (df.index.year >= 2025) & (df.index.year <= 2026)
    oos_indices = np.where(np.asarray(oos_mask))[0]
    if len(oos_indices) > max_signals:
        step = len(oos_indices) // max_signals
        oos_indices = oos_indices[::step][:max_signals]

    daily_dd_limit = profile["dd_stops"]["external_daily_dd_limit"]
    total_dd_limit = profile["dd_stops"]["external_total_dd_limit"]

    for idx in oos_indices:
        i = int(idx)
        if i < 28 or i >= len(df) - params["max_holding_bars"] - 1:
            continue

        timestamp = str(index[i])
        alpha_confidence = float(alpha_proba[i])
        meta_confidence = float(meta_proba[i])
        direction = "LONG" if alpha_confidence >= 0.5 else "SHORT"
        if alpha_confidence == 0.5:
            direction = "LONG" if closes[i] > closes[i-1] else "SHORT"

        signal = {
            "timestamp": timestamp, "broker": broker, "symbol": "XAUUSD",
            "model_profile": "v2_feature_normalized",
            "alpha": round(alpha_confidence, 6), "meta": round(meta_confidence, 6),
            "direction": direction,
            "alpha_pass": alpha_confidence >= params["alpha_threshold"],
            "meta_pass": meta_confidence >= params["meta_threshold"],
            "ceo_decision": "", "risk_decision": "", "broker_decision": "",
            "mtf_decision": "", "final_decision": "REJECT", "reject_reason": "",
            "hypothetical_sl": None, "hypothetical_tp": None,
            "hypothetical_lot": profile["max_lot"],
            "NO_ORDER_SENT": True,
        }

        # Risk state tracking
        risk_state_rows.append({
            "timestamp": timestamp, "broker": broker,
            "alpha": round(alpha_confidence, 4), "meta": round(meta_confidence, 4),
            "direction": direction,
            "daily_dd_limit": daily_dd_limit, "total_dd_limit": total_dd_limit,
            "no_order_sent": True,
        })

        if not signal["alpha_pass"]:
            signal["reject_reason"] = f"alpha_below_{params['alpha_threshold']}"
            signals.append(signal)
            continue
        if not signal["meta_pass"]:
            signal["reject_reason"] = f"meta_below_{params['meta_threshold']}"
            signals.append(signal)
            continue

        ceo_decision = evaluate_ceo_decision(
            regime_state={"detected": True, "regime_value": "MARKET_OPEN", "confidence": alpha_confidence},
            xgb_alpha={"direction": direction, "confidence": alpha_confidence, "pass": True},
            lstm_confidence=None, transformer_regime=None,
            meta_label_quality={"quality_score": meta_confidence, "pass": True},
            broker_state={"broker_pass": True, "spread_pass": True, "slippage_pass": True},
            prop_risk_state={"risk_pass": True, "prop_funded_pass": True, "max_positions_ok": True},
            capital_protection_state={"capital_preservation_active": False, "dd_breach": False},
            model_health_state={"model_health_pass": True, "failed_required": 0},
            geometry_state={"geometry_pass": True, "actual_RR": params["rr_target"], "minimum_RR": 2.0},
        )
        signal["ceo_decision"] = "PASS" if ceo_decision.allowed_to_trade else "BLOCK"
        if not ceo_decision.allowed_to_trade:
            signal["reject_reason"] = "ceo_blocked"
            signals.append(signal)
            continue

        spread = float(df["spread_usd"].iloc[i]) if "spread_usd" in df.columns else 0.3
        if spread > params["spread_filter"]:
            signal["risk_decision"] = "BLOCK"
            signal["reject_reason"] = f"spread_{spread:.3f}"
            signals.append(signal)
            continue
        signal["risk_decision"] = "PASS"
        signal["broker_decision"] = f"{broker} (read-only shadow)"

        signal["mtf_decision"] = "N/A (h1_only)"
        atr = atr_values[i] if atr_values[i] > 0 else 3.0
        sl_distance = atr * params["sl_atr_multiplier"]
        tp_distance = sl_distance * params["rr_target"]
        entry_price = closes[i]
        if direction == "LONG":
            sl_price, tp_price = entry_price - sl_distance, entry_price + tp_distance
        else:
            sl_price, tp_price = entry_price + sl_distance, entry_price - tp_distance

        signal["final_decision"] = "SHADOW_SIGNAL"
        signal["hypothetical_sl"] = round(float(sl_price), 4)
        signal["hypothetical_tp"] = round(float(tp_price), 4)
        signal["hypothetical_entry"] = round(float(entry_price), 4)
        signals.append(signal)

    return signals, risk_state_rows


def main():
    parser = argparse.ArgumentParser(description="TITAN Broker-Specific Read-Only Shadow Runner")
    parser.add_argument("--broker", required=True,
                        choices=["fundednext", "exness", "icmarkets", "fbs"],
                        help="Target broker for shadow")
    parser.add_argument("--profile", default="cautious", choices=["cautious", "base"],
                        help="Risk profile")
    parser.add_argument("--max-signals", type=int, default=100)
    args = parser.parse_args()

    ts = datetime.now(timezone.utc).isoformat()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("  TITAN XAU AI - BROKER-SPECIFIC READ-ONLY SHADOW (v2.8.7-K)")
    print("=" * 70)
    print(f"  Timestamp: {ts}")
    print(f"  Broker: {args.broker}")
    print(f"  Profile: {args.profile}")
    print(f"  NO_ORDER_SENT: True (always)\n")

    # Load broker profile
    profile = load_broker_profile(args.broker)
    if profile is None:
        print(f"  ERROR: No prop profile found for {args.broker}")
        print(f"  Broker may be rejected. Check config/broker_profiles/{args.broker}_REJECTED.note")
        return

    # Safety checks
    assert profile["safety"]["dry_run"] is True
    assert profile["safety"]["live_trading"] is False
    assert profile["safety"]["funded_trading"] is False
    assert profile["safety"]["production_ready"] is False

    # Load model
    bundle = load_models_by_profile("v2_feature_normalized")
    if not bundle.ok:
        print("  ERROR: v2 model failed to load")
        return

    # Load data
    df = load_broker_data(args.broker)
    if df is None:
        print(f"  ERROR: {args.broker} data not found")
        return
    print(f"  Loaded {len(df)} bars for {args.broker}")

    # Compute predictions
    alpha_proba, meta_proba, atr_values = compute_predictions(df, bundle)

    # Run shadow
    signals, risk_state_rows = run_shadow(args.broker, df, alpha_proba, meta_proba, atr_values,
                                            profile, args.max_signals)

    shadow_signals = [s for s in signals if s["final_decision"] == "SHADOW_SIGNAL"]
    rejected = [s for s in signals if s["final_decision"] == "REJECT"]
    print(f"\n  Shadow signals: {len(shadow_signals)}")
    print(f"  Rejected: {len(rejected)}")

    # Write outputs
    with open(OUTPUT_DIR / f"shadow_signals_{args.broker}.csv", "w", newline="") as f:
        if signals:
            w = csv.DictWriter(f, fieldnames=list(signals[0].keys()))
            w.writeheader()
            for s in signals:
                w.writerow(s)

    with open(OUTPUT_DIR / f"shadow_journal_{args.broker}.jsonl", "w") as f:
        for s in signals:
            f.write(json.dumps(s, default=str) + "\n")

    with open(OUTPUT_DIR / f"broker_prop_risk_state_{args.broker}.csv", "w", newline="") as f:
        if risk_state_rows:
            w = csv.DictWriter(f, fieldnames=list(risk_state_rows[0].keys()))
            w.writeheader()
            for r in risk_state_rows:
                w.writerow(r)

    summary = {
        "timestamp_utc": ts, "broker": args.broker, "profile": args.profile,
        "total_evaluated": len(signals), "shadow_signals": len(shadow_signals),
        "rejected": len(rejected), "dry_run": True, "live_trading": False,
        "funded_trading": False, "production_ready": False, "no_order_sent": True,
    }
    with open(OUTPUT_DIR / f"shadow_summary_{args.broker}.json", "w") as f:
        json.dump(summary, f, indent=2, default=str)

    with open(OUTPUT_DIR / f"shadow_summary_{args.broker}.md", "w") as f:
        f.write(f"# Shadow Summary - {args.broker} (Sprint v2.8.7-K)\n\n")
        f.write(f"**Timestamp:** {ts}\n\n")
        f.write(f"## Results\n\n")
        f.write(f"- Total evaluated: {len(signals)}\n")
        f.write(f"- Shadow signals: {len(shadow_signals)}\n")
        f.write(f"- Rejected: {len(rejected)}\n\n")
        f.write(f"## Safety\n\n")
        f.write(f"- dry_run: True\n- live_trading: False\n- funded_trading: False\n")
        f.write(f"- production_ready: False\n- NO_ORDER_SENT: True\n")
        f.write(f"- Broker: {args.broker} (read-only shadow)\n")

    print(f"\n  Output: {OUTPUT_DIR}")
    print("\n" + "=" * 70)
    print("  READ-ONLY SHADOW COMPLETE — NO ORDERS SENT")
    print("=" * 70)


if __name__ == "__main__":
    main()
