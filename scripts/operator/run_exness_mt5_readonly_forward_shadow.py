#!/usr/bin/env python3
"""TITAN XAU AI — Exness MT5 Read-Only Forward Shadow Runner (Module 2)
=======================================================================
Local Windows MT5 forward shadow runner. Reads market data, computes
features, generates read-only signals. NEVER trades.

CLI:
  python scripts/operator/run_exness_mt5_readonly_forward_shadow.py
    --broker exness --symbol XAUUSD --timeframe H1
    --max-cycles 24 --sleep-seconds 60

NEVER sends orders. NEVER creates tokens. NEVER trades.
NO_ORDER_SENT = True on every row.
"""
from __future__ import annotations
import sys, os, json, csv, time, argparse, signal
from pathlib import Path
from datetime import datetime, timezone
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

CONTRACT_SIZE = 100
LEVERAGE = 100


def load_exness_profile():
    import yaml
    path = REPO_ROOT / "config" / "broker_profiles" / "exness_legacy_optimized_prop_profile.yaml"
    with open(path) as f:
        return yaml.safe_load(f)


def calculate_risk_based_lot(equity, risk_percent, sl_distance, entry_price):
    if sl_distance <= 0 or entry_price <= 0:
        return 0.01, 0.0, 0.0
    risk_amount = equity * risk_percent
    estimated_loss_per_lot = sl_distance * CONTRACT_SIZE
    lot_size = risk_amount / estimated_loss_per_lot
    notional = entry_price * CONTRACT_SIZE * lot_size
    margin = notional / LEVERAGE
    margin_usage = margin / equity if equity > 0 else 0
    if margin_usage > 0.20:
        max_lot = (equity * 0.20 * LEVERAGE) / (entry_price * CONTRACT_SIZE)
        lot_size = min(lot_size, max_lot)
        notional = entry_price * CONTRACT_SIZE * lot_size
        margin = notional / LEVERAGE
        margin_usage = margin / equity if equity > 0 else 0
    return round(lot_size, 4), round(margin, 2), round(margin_usage, 6)


def run_forward_shadow_cycle(broker, symbol, timeframe, profile, bundle, equity=100000):
    """Run one forward shadow cycle — fetch latest bars, compute signal."""
    params = profile["optimized_parameters"]

    # Try MT5 connection
    result = safe_connect_and_audit(symbol=symbol, bar_count=300)

    if not result.success:
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "broker": broker, "symbol": symbol, "timeframe": timeframe,
            "final_decision": "SAFETY_BLOCK",
            "reject_reason": result.verdict,
            "NO_ORDER_SENT": True,
        }

    if result.raw_bars is None or len(result.raw_bars) < 220:
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "broker": broker, "symbol": symbol, "timeframe": timeframe,
            "final_decision": "REJECT_MARKET_DATA",
            "reject_reason": "insufficient_bars",
            "NO_ORDER_SENT": True,
        }

    # Convert to DataFrame
    df = pd.DataFrame(result.raw_bars)
    if "time" in df.columns:
        df["time"] = pd.to_datetime(df["time"], unit="s")
        df = df.set_index("time")
    df = normalize_xauusd_spread_to_usd(df, symbol="XAUUSD", source=broker)

    # Compute features
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
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "broker": broker, "symbol": symbol, "timeframe": timeframe,
            "final_decision": "REJECT_MARKET_DATA",
            "reject_reason": f"feature_error: {e}",
            "NO_ORDER_SENT": True,
        }

    # Latest bar prediction
    last_vec = features_matrix[-1:]
    alpha_proba = bundle.xgb.predict_proba(last_vec)[0, 1]
    name_to_idx = {n: i for i, n in enumerate(FEATURE_NAMES_V2)}
    meta_indices = [name_to_idx[n] for n in META_FEATURE_NAMES_V2]
    meta_vec = last_vec[0, meta_indices]
    meta_proba = bundle.meta.predict_proba(meta_vec.reshape(1, -1))[0, 1]

    # ATR for latest bar
    closes = df["close"].values
    highs = df["high"].values
    lows = df["low"].values
    i = len(df) - 1
    atr = max(
        highs[i] - lows[i],
        abs(highs[i] - closes[i-1]),
        abs(lows[i] - closes[i-1]),
    ) if i > 0 else 3.0

    direction = "LONG" if alpha_proba >= 0.5 else "SHORT"
    timestamp = str(df.index[-1])

    signal = {
        "timestamp": timestamp,
        "broker": broker, "symbol": symbol, "timeframe": timeframe,
        "account_type": "demo" if result.account_info and result.account_info.is_demo else "unknown",
        "server_masked": result.account_info.server if result.account_info else "N/A",
        "alpha_confidence": round(float(alpha_proba), 6),
        "meta_confidence": round(float(meta_proba), 6),
        "CEO_decision": "", "broker_decision": "", "prop_risk_decision": "",
        "final_decision": "REJECT", "reject_reason": "",
        "entry_reference": round(float(closes[i]), 4),
        "SL_reference": None, "TP_reference": None,
        "risk_amount": round(equity * params["risk_percent"], 2),
        "calculated_lot": None, "margin_required": None, "margin_usage": None,
        "leverage": LEVERAGE,
        "NO_ORDER_SENT": True,
    }

    # Alpha check
    if alpha_proba < params["alpha_threshold"]:
        signal["final_decision"] = "REJECT_ALPHA"
        signal["reject_reason"] = f"alpha_{alpha_proba:.4f}_below_{params['alpha_threshold']}"
        return signal

    # Meta check
    if meta_proba < params["meta_threshold"]:
        signal["final_decision"] = "REJECT_META"
        signal["reject_reason"] = f"meta_{meta_proba:.4f}_below_{params['meta_threshold']}"
        return signal

    # CEO
    ceo = evaluate_ceo_decision(
        regime_state={"detected": True, "regime_value": "MARKET_OPEN", "confidence": alpha_proba},
        xgb_alpha={"direction": direction, "confidence": alpha_proba, "pass": True},
        lstm_confidence=None, transformer_regime=None,
        meta_label_quality={"quality_score": meta_proba, "pass": True},
        broker_state={"broker_pass": True, "spread_pass": True, "slippage_pass": True},
        prop_risk_state={"risk_pass": True, "prop_funded_pass": True, "max_positions_ok": True},
        capital_protection_state={"capital_preservation_active": False, "dd_breach": False},
        model_health_state={"model_health_pass": True, "failed_required": 0},
        geometry_state={"geometry_pass": True, "actual_RR": params["rr_target"], "minimum_RR": 2.0},
    )
    signal["CEO_decision"] = "PASS" if ceo.allowed_to_trade else "BLOCK"
    if not ceo.allowed_to_trade:
        signal["final_decision"] = "REJECT_CEO"
        signal["reject_reason"] = "ceo_blocked"
        return signal

    # Spread check
    spread = float(df["spread_usd"].iloc[-1])
    if spread > params["spread_filter"]:
        signal["final_decision"] = "REJECT_SPREAD"
        signal["reject_reason"] = f"spread_{spread:.4f}_above_{params['spread_filter']}"
        return signal

    # Lot sizing
    sl_distance = atr * params["sl_atr_multiplier"]
    tp_distance = sl_distance * params["rr_target"]
    entry_price = float(closes[i])
    lot, margin_req, margin_usage = calculate_risk_based_lot(equity, params["risk_percent"], sl_distance, entry_price)

    # Margin check
    if margin_usage > 0.20:
        signal["final_decision"] = "REJECT_MARGIN"
        signal["reject_reason"] = f"margin_usage_{margin_usage:.4f}_above_0.20"
        return signal

    # Prop risk check (simplified — no live equity tracking in shadow)
    signal["broker_decision"] = "PASS"
    signal["prop_risk_decision"] = "PASS"
    signal["final_decision"] = "SHADOW_SIGNAL"
    signal["SL_reference"] = round(entry_price - sl_distance if direction == "LONG" else entry_price + sl_distance, 4)
    signal["TP_reference"] = round(entry_price + tp_distance if direction == "LONG" else entry_price - tp_distance, 4)
    signal["calculated_lot"] = lot
    signal["margin_required"] = margin_req
    signal["margin_usage"] = margin_usage
    signal["direction"] = direction

    return signal


def main():
    parser = argparse.ArgumentParser(description="TITAN Exness MT5 Read-Only Forward Shadow")
    parser.add_argument("--broker", default="exness")
    parser.add_argument("--symbol", default="XAUUSD")
    parser.add_argument("--timeframe", default="H1")
    parser.add_argument("--max-cycles", type=int, default=24)
    parser.add_argument("--sleep-seconds", type=int, default=60)
    args = parser.parse_args()

    ts = datetime.now(timezone.utc).isoformat()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("  EXNESS MT5 READ-ONLY FORWARD SHADOW (Module 2)")
    print("=" * 70)
    print(f"  Timestamp: {ts}")
    print(f"  Broker: {args.broker}, Symbol: {args.symbol}")
    print(f"  Max cycles: {args.max_cycles}, Sleep: {args.sleep_seconds}s")
    print(f"  NO_ORDER_SENT: True (always)\n")

    profile = load_exness_profile()
    bundle = load_models_by_profile("v2_feature_normalized")
    if not bundle.ok:
        print("  ERROR: v2 model failed to load")
        return

    signals = []
    risk_lot_rows = []

    for cycle in range(args.max_cycles):
        print(f"  Cycle {cycle+1}/{args.max_cycles}...")
        signal = run_forward_shadow_cycle(args.broker, args.symbol, args.timeframe, profile, bundle)
        signals.append(signal)

        if signal.get("calculated_lot"):
            risk_lot_rows.append({
                "timestamp": signal["timestamp"], "broker": args.broker,
                "lot": signal["calculated_lot"], "margin_usage": signal["margin_usage"],
                "leverage": LEVERAGE, "no_order_sent": True,
            })

        if cycle < args.max_cycles - 1:
            time.sleep(args.sleep_seconds)

    # Write outputs
    with open(OUTPUT_DIR / "forward_shadow_signals_exness.csv", "w", newline="", encoding="utf-8") as f:
        if signals:
            w = csv.DictWriter(f, fieldnames=list(signals[0].keys()))
            w.writeheader()
            for s in signals:
                w.writerow(s)

    with open(OUTPUT_DIR / "forward_shadow_journal_exness.jsonl", "w", encoding="utf-8") as f:
        for s in signals:
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
    }
    with open(OUTPUT_DIR / "forward_shadow_summary_exness.json", "w") as f:
        json.dump(summary, f, indent=2)
    with open(OUTPUT_DIR / "forward_shadow_summary_exness.md", "w", encoding="utf-8") as f:
        f.write(f"# Forward Shadow Summary - {args.broker} (Module 2)\n\n")
        f.write(f"**Timestamp:** {ts}\n\n")
        f.write(f"- Total cycles: {len(signals)}\n- Shadow signals: {len(shadow_signals)}\n")
        f.write(f"- Rejected: {len(signals) - len(shadow_signals)}\n\n")
        f.write(f"- NO_ORDER_SENT: True\n- dry_run: True\n- live_trading: False\n")

    print(f"\n  Shadow signals: {len(shadow_signals)}")
    print(f"  Output: {OUTPUT_DIR}")
    print("\n" + "=" * 70)
    print("  READ-ONLY FORWARD SHADOW — NO ORDERS SENT")
    print("=" * 70)


if __name__ == "__main__":
    main()
