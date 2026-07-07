#!/usr/bin/env python3
"""TITAN XAU AI - Legacy Optimized Broker Shadow Runner (Sprint v2.8.7-L)
=========================================================================
Read-only shadow runner for legacy optimized broker profiles.
Uses 1:100 leverage risk-based lot sizing.

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

OUTPUT_DIR = REPO_ROOT / "data" / "reports" / "legacy_optimized_shadow"

from titan.production.spread_normalization import normalize_xauusd_spread_to_usd
from titan.production.feature_stream_v2 import H1FeatureStreamV2, FEATURE_NAMES_V2
from titan.training.feature_schema_v2 import META_FEATURE_NAMES_V2
from titan.production.model_loader import load_models_by_profile
from titan.production.ceo_ai_governance import evaluate_ceo_decision

BROKER_PATHS = {
    "canonical": REPO_ROOT / "titan" / "data" / "canonical" / "XAUUSD_H1_canonical.parquet",
    "exness": REPO_ROOT / "titan" / "data" / "sources" / "mt5_brokers" / "exness" / "XAUUSD_H1.parquet",
    "fbs": REPO_ROOT / "titan" / "data" / "sources" / "mt5_brokers" / "fbs" / "XAUUSD_H1.parquet",
    "fundednext": REPO_ROOT / "titan" / "data" / "sources" / "mt5_brokers" / "fundednext" / "XAUUSD_H1.parquet",
    "icmarkets": REPO_ROOT / "titan" / "data" / "sources" / "mt5_brokers" / "icmarkets" / "XAUUSD_H1.parquet",
}

CONTRACT_SIZE = 100
LEVERAGE = 100


def load_broker_profile(broker):
    profile_path = REPO_ROOT / "config" / "broker_profiles" / f"{broker}_legacy_optimized_prop_profile.yaml"
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


def calculate_risk_based_lot(equity, risk_percent, sl_distance, entry_price):
    if sl_distance <= 0 or entry_price <= 0:
        return 0.01, 0.0, 0.0
    risk_amount = equity * risk_percent
    estimated_loss_per_lot = sl_distance * CONTRACT_SIZE
    lot_size = risk_amount / estimated_loss_per_lot
    notional_value = entry_price * CONTRACT_SIZE * lot_size
    margin_required = notional_value / LEVERAGE
    margin_usage = margin_required / equity if equity > 0 else 0
    if margin_usage > 0.20:
        max_lot = (equity * 0.20 * LEVERAGE) / (entry_price * CONTRACT_SIZE)
        lot_size = min(lot_size, max_lot)
        notional_value = entry_price * CONTRACT_SIZE * lot_size
        margin_required = notional_value / LEVERAGE
        margin_usage = margin_required / equity if equity > 0 else 0
    return round(lot_size, 4), round(margin_required, 2), round(margin_usage, 6)


def main():
    parser = argparse.ArgumentParser(description="TITAN Legacy Optimized Broker Shadow Runner")
    parser.add_argument("--broker", required=True,
                        choices=["exness", "fundednext", "fbs", "icmarkets"])
    parser.add_argument("--max-signals", type=int, default=100)
    args = parser.parse_args()

    ts = datetime.now(timezone.utc).isoformat()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("  TITAN XAU AI - LEGACY OPTIMIZED BROKER SHADOW (v2.8.7-L)")
    print("=" * 70)
    print(f"  Timestamp: {ts}")
    print(f"  Broker: {args.broker}")
    print(f"  NO_ORDER_SENT: True (always)\n")

    profile = load_broker_profile(args.broker)
    if profile is None:
        print(f"  ERROR: No legacy optimized profile for {args.broker}")
        return

    assert profile["safety"]["dry_run"] is True
    assert profile["safety"]["live_trading"] is False
    assert profile["safety"]["funded_trading"] is False
    assert profile["safety"]["production_ready"] is False

    bundle = load_models_by_profile("v2_feature_normalized")
    if not bundle.ok:
        print("  ERROR: v2 model failed to load")
        return

    df = load_broker_data(args.broker)
    if df is None:
        print(f"  ERROR: {args.broker} data not found")
        return

    alpha_proba, meta_proba, atr_values = compute_predictions(df, bundle)

    # Run shadow
    signals = []
    risk_state_rows = []
    closes = df["close"].values
    index = df.index
    oos_mask = (df.index.year >= 2025) & (df.index.year <= 2026)
    oos_indices = np.where(np.asarray(oos_mask))[0]
    if len(oos_indices) > args.max_signals:
        step = len(oos_indices) // args.max_signals
        oos_indices = oos_indices[::step][:args.max_signals]

    params = profile["optimized_parameters"]
    for idx in oos_indices:
        i = int(idx)
        if i < 28 or i >= len(df) - 3:
            continue

        alpha_conf = float(alpha_proba[i])
        meta_conf = float(meta_proba[i])
        direction = "LONG" if alpha_conf >= 0.5 else "SHORT"

        atr = atr_values[i] if atr_values[i] > 0 else 3.0
        sl_distance = atr * params["sl_atr_multiplier"]
        entry_price = closes[i]
        lot_size, margin_req, margin_usage = calculate_risk_based_lot(
            100000, params["risk_percent"], sl_distance, entry_price
        )

        signal = {
            "timestamp": str(index[i]), "broker": args.broker, "symbol": "XAUUSD",
            "model_profile": "v2_feature_normalized",
            "alpha": round(alpha_conf, 6), "meta": round(meta_conf, 6),
            "direction": direction,
            "alpha_pass": alpha_conf >= params["alpha_threshold"],
            "meta_pass": meta_conf >= params["meta_threshold"],
            "ceo_decision": "", "final_decision": "REJECT", "reject_reason": "",
            "hypothetical_entry": round(entry_price, 4),
            "hypothetical_sl": round(entry_price - sl_distance if direction == "LONG" else entry_price + sl_distance, 4),
            "hypothetical_tp": round(entry_price + sl_distance * params["rr_target"] if direction == "LONG" else entry_price - sl_distance * params["rr_target"], 4),
            "hypothetical_lot": lot_size,
            "margin_required": margin_req,
            "margin_usage": margin_usage,
            "leverage": LEVERAGE,
            "NO_ORDER_SENT": True,
        }

        risk_state_rows.append({
            "timestamp": str(index[i]), "broker": args.broker,
            "alpha": round(alpha_conf, 4), "meta": round(meta_conf, 4),
            "direction": direction, "lot": lot_size,
            "margin_usage": margin_usage, "leverage": LEVERAGE,
            "no_order_sent": True,
        })

        if not signal["alpha_pass"] or not signal["meta_pass"]:
            signal["reject_reason"] = "threshold_not_met"
            signals.append(signal)
            continue

        ceo = evaluate_ceo_decision(
            regime_state={"detected": True, "regime_value": "MARKET_OPEN", "confidence": alpha_conf},
            xgb_alpha={"direction": direction, "confidence": alpha_conf, "pass": True},
            lstm_confidence=None, transformer_regime=None,
            meta_label_quality={"quality_score": meta_conf, "pass": True},
            broker_state={"broker_pass": True, "spread_pass": True, "slippage_pass": True},
            prop_risk_state={"risk_pass": True, "prop_funded_pass": True, "max_positions_ok": True},
            capital_protection_state={"capital_preservation_active": False, "dd_breach": False},
            model_health_state={"model_health_pass": True, "failed_required": 0},
            geometry_state={"geometry_pass": True, "actual_RR": params["rr_target"], "minimum_RR": 2.0},
        )
        signal["ceo_decision"] = "PASS" if ceo.allowed_to_trade else "BLOCK"
        if not ceo.allowed_to_trade:
            signal["reject_reason"] = "ceo_blocked"
            signals.append(signal)
            continue

        signal["final_decision"] = "SHADOW_SIGNAL"
        signals.append(signal)

    shadow_signals = [s for s in signals if s["final_decision"] == "SHADOW_SIGNAL"]
    print(f"\n  Shadow signals: {len(shadow_signals)}")
    print(f"  Total evaluated: {len(signals)}")

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

    with open(OUTPUT_DIR / f"risk_lot_state_{args.broker}.csv", "w", newline="") as f:
        if risk_state_rows:
            w = csv.DictWriter(f, fieldnames=list(risk_state_rows[0].keys()))
            w.writeheader()
            for r in risk_state_rows:
                w.writerow(r)

    summary = {
        "timestamp_utc": ts, "broker": args.broker,
        "total_evaluated": len(signals), "shadow_signals": len(shadow_signals),
        "dry_run": True, "live_trading": False, "funded_trading": False,
        "production_ready": False, "no_order_sent": True,
        "leverage": LEVERAGE, "risk_based_lot_sizing": True,
    }
    with open(OUTPUT_DIR / f"shadow_summary_{args.broker}.json", "w") as f:
        json.dump(summary, f, indent=2)

    with open(OUTPUT_DIR / f"shadow_summary_{args.broker}.md", "w") as f:
        f.write(f"# Shadow Summary - {args.broker} (v2.8.7-L)\n\n")
        f.write(f"**Timestamp:** {ts}\n\n")
        f.write(f"## Results\n\n- Total: {len(signals)}\n- Shadow signals: {len(shadow_signals)}\n\n")
        f.write(f"## Safety\n\n- dry_run: True\n- live_trading: False\n- funded_trading: False\n")
        f.write(f"- production_ready: False\n- NO_ORDER_SENT: True\n- Leverage: 1:{LEVERAGE}\n")
        f.write(f"- Risk-based lot sizing: True\n")

    print(f"\n  Output: {OUTPUT_DIR}")
    print("\n" + "=" * 70)
    print("  READ-ONLY SHADOW COMPLETE — NO ORDERS SENT")
    print("=" * 70)


if __name__ == "__main__":
    main()
