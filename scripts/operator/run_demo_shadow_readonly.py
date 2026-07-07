#!/usr/bin/env python3
"""TITAN XAU AI - Read-Only Demo Shadow Runner (Sprint v2.8.7-H)
================================================================
Runs the locked candidate in READ-ONLY shadow mode.

This script:
  - Reads MT5/canonical data only
  - Generates signals using locked candidate parameters
  - Journals decisions only
  - Does NOT send orders
  - Does NOT create tokens
  - Does NOT touch live/funded accounts
  - MetaQuotes-Demo only (configurable)
  - dry_run = true (always)
  - production_ready = false (always)

Each signal is logged with:
  timestamp, symbol, model_profile, alpha, meta, direction,
  CEO decision, risk decision, broker decision, MTF decision,
  final decision, reason if rejected,
  hypothetical SL, hypothetical TP, hypothetical lot,
  NO_ORDER_SENT = True

NEVER sends orders. NEVER creates tokens. NEVER trades.
"""
from __future__ import annotations
import sys, json, csv, os, argparse
from pathlib import Path
from datetime import datetime, timezone
import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

OUTPUT_DIR = REPO_ROOT / "data" / "reports" / "demo_shadow_readonly"

from titan.production.spread_normalization import normalize_xauusd_spread_to_usd
from titan.production.feature_stream_v2 import H1FeatureStreamV2, FEATURE_NAMES_V2
from titan.training.feature_schema_v2 import META_FEATURE_NAMES_V2
from titan.production.model_loader import load_models_by_profile
from titan.production.ceo_ai_governance import evaluate_ceo_decision
from titan.production.mtf_confirmation import evaluate_mtf, load_m15_bars, load_m5_bars, reset_mtf_caches


def load_locked_candidate():
    """Load locked candidate parameters from YAML config."""
    import yaml
    config_path = REPO_ROOT / "config" / "demo_shadow_candidate.yaml"
    with open(config_path) as f:
        config = yaml.safe_load(f)
    return config["candidate_lock"]


def load_shadow_data(broker="canonical"):
    """Load H1 data for shadow mode (default: canonical for offline shadow)."""
    if broker == "canonical":
        path = REPO_ROOT / "titan" / "data" / "canonical" / "XAUUSD_H1_canonical.parquet"
    else:
        path = REPO_ROOT / "titan" / "data" / "sources" / "mt5_brokers" / broker / "XAUUSD_H1.parquet"
    if not path.exists():
        return None
    df = pd.read_parquet(path)
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)
    df = normalize_xauusd_spread_to_usd(df, symbol="XAUUSD", source=broker)
    return df


def compute_predictions(df, bundle):
    """Compute v2 alpha + meta predictions."""
    df_use = df[["open", "high", "low", "close"]].copy()
    if "tick_volume" in df.columns:
        df_use["volume"] = df["tick_volume"]
    else:
        df_use["volume"] = 0.0
    df_use["spread"] = df["spread_usd"]

    stream = H1FeatureStreamV2()
    stream._bars = df_use
    feats_df = stream._compute_features()
    features_matrix = np.nan_to_num(
        feats_df.values.astype(np.float64), nan=0.0, posinf=0.0, neginf=0.0
    )
    features_matrix = stream._standardize(features_matrix)
    alpha_proba = bundle.xgb.predict_proba(features_matrix)[:, 1]
    name_to_idx = {n: i for i, n in enumerate(FEATURE_NAMES_V2)}
    meta_indices = [name_to_idx[n] for n in META_FEATURE_NAMES_V2]
    meta_vecs = features_matrix[:, meta_indices]
    meta_proba = bundle.meta.predict_proba(meta_vecs)[:, 1]

    # ATR
    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values
    atr_values = np.zeros(len(df))
    for i in range(14, len(df)):
        atr_values[i] = max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1]))
    for i in range(28, len(df)):
        atr_values[i] = np.mean(atr_values[i-14:i])
    return alpha_proba, meta_proba, atr_values


def run_shadow_session(df, alpha_proba, meta_proba, atr_values, params,
                        m15_bars=None, m5_bars=None, symbol="XAUUSD",
                        max_signals=100):
    """Run a read-only shadow session. Returns list of signal journals."""
    signals = []
    closes = df["close"].values
    index = df.index

    # Use OOS period (2025-2026) or last N bars
    oos_mask = (df.index.year >= 2025) & (df.index.year <= 2026)
    oos_indices = np.where(np.asarray(oos_mask))[0]

    # Limit to max_signals for journal size
    if len(oos_indices) > max_signals:
        # Sample evenly across the OOS period
        step = len(oos_indices) // max_signals
        oos_indices = oos_indices[::step][:max_signals]

    print(f"  Shadow session: {len(oos_indices)} bars to evaluate")

    for idx in oos_indices:
        i = int(idx)
        if i < 28 or i >= len(df) - params["max_holding_bars"] - 1:
            continue

        timestamp = str(index[i])
        alpha_confidence = float(alpha_proba[i])
        meta_confidence = float(meta_proba[i])

        # Direction
        direction = "LONG" if alpha_confidence >= 0.5 else "SHORT"
        if alpha_confidence == 0.5:
            direction = "LONG" if closes[i] > closes[i-1] else "SHORT"

        signal = {
            "timestamp": timestamp,
            "symbol": symbol,
            "model_profile": "v2_feature_normalized",
            "alpha": round(alpha_confidence, 6),
            "meta": round(meta_confidence, 6),
            "direction": direction,
            "alpha_pass": alpha_confidence >= params["alpha_threshold"],
            "meta_pass": meta_confidence >= params["meta_threshold"],
            "ceo_decision": "",
            "risk_decision": "",
            "broker_decision": "",
            "mtf_decision": "",
            "final_decision": "REJECT",
            "reject_reason": "",
            "hypothetical_sl": None,
            "hypothetical_tp": None,
            "hypothetical_lot": params["max_lot"],
            "NO_ORDER_SENT": True,
        }

        # Check alpha threshold
        if not signal["alpha_pass"]:
            signal["reject_reason"] = f"alpha_{alpha_confidence:.3f}_below_{params['alpha_threshold']}"
            signals.append(signal)
            continue

        # Check meta threshold
        if not signal["meta_pass"]:
            signal["reject_reason"] = f"meta_{meta_confidence:.3f}_below_{params['meta_threshold']}"
            signals.append(signal)
            continue

        # CEO decision
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

        # Risk decision (check spread filter)
        spread = float(df["spread_usd"].iloc[i]) if "spread_usd" in df.columns else 0.3
        if spread > params["spread_filter"]:
            signal["risk_decision"] = "BLOCK"
            signal["reject_reason"] = f"spread_{spread:.3f}_above_{params['spread_filter']}"
            signals.append(signal)
            continue
        signal["risk_decision"] = "PASS"

        # Broker decision (always MetaQuotes-Demo in shadow mode)
        signal["broker_decision"] = "MetaQuotes-Demo (shadow)"

        # MTF decision
        mtf_mode = params["mtf_mode"]
        if mtf_mode != "h1_only":
            mtf_result = evaluate_mtf(mtf_mode, index[i], direction, m15_bars, m5_bars)
            signal["mtf_decision"] = "PASS" if mtf_result.m15_confirmation_pass else f"BLOCK:{mtf_result.mtf_reject_reason}"
            if not mtf_result.m15_confirmation_pass:
                signal["reject_reason"] = f"mtf_blocked:{mtf_result.mtf_reject_reason}"
                signals.append(signal)
                continue
        else:
            signal["mtf_decision"] = "N/A (h1_only)"

        # All gates passed — hypothetical signal
        atr = atr_values[i] if atr_values[i] > 0 else 3.0
        sl_distance = atr * params["sl_atr_multiplier"]
        tp_distance = sl_distance * params["rr_target"]
        entry_price = closes[i]
        if direction == "LONG":
            sl_price = entry_price - sl_distance
            tp_price = entry_price + tp_distance
        else:
            sl_price = entry_price + sl_distance
            tp_price = entry_price - tp_distance

        signal["final_decision"] = "SHADOW_SIGNAL"
        signal["reject_reason"] = ""
        signal["hypothetical_sl"] = round(float(sl_price), 4)
        signal["hypothetical_tp"] = round(float(tp_price), 4)
        signal["hypothetical_entry"] = round(float(entry_price), 4)
        signal["hypothetical_lot"] = params["max_lot"]
        signals.append(signal)

    return signals


def main():
    parser = argparse.ArgumentParser(description="TITAN Demo Shadow Read-Only Runner")
    parser.add_argument("--broker", default="canonical",
                        help="Broker data source for shadow (default: canonical)")
    parser.add_argument("--max-signals", type=int, default=100,
                        help="Maximum signals to journal (default: 100)")
    parser.add_argument("--symbol", default="XAUUSD")
    args = parser.parse_args()

    ts = datetime.now(timezone.utc).isoformat()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("  TITAN XAU AI - READ-ONLY DEMO SHADOW RUNNER (Sprint v2.8.7-H)")
    print("=" * 70)
    print(f"  Timestamp: {ts}")
    print(f"  Broker data: {args.broker}")
    print(f"  Max signals: {args.max_signals}")
    print(f"  NO_ORDER_SENT: True (always)")
    print(f"  dry_run: True (always)")
    print(f"  production_ready: False (always)\n")

    # Load locked candidate
    print("  Loading locked candidate...")
    candidate = load_locked_candidate()
    params = candidate["parameters"]
    print(f"  Candidate: {candidate['lock_id']}")
    print(f"  alpha_threshold: {params['alpha_threshold']}")
    print(f"  meta_threshold: {params['meta_threshold']}")

    # Safety checks
    assert candidate["safety"]["dry_run"] is True
    assert candidate["safety"]["live_trading"] is False
    assert candidate["safety"]["funded_trading"] is False
    assert candidate["safety"]["production_ready"] is False
    assert candidate["safety"]["no_order_send"] is True

    # Load model
    print("\n  Loading v2 model...")
    bundle = load_models_by_profile("v2_feature_normalized")
    if not bundle.ok:
        print("  ERROR: v2 model failed to load")
        return

    # Load data
    print(f"\n  Loading {args.broker} data...")
    df = load_shadow_data(args.broker)
    if df is None:
        print(f"  ERROR: {args.broker} data not found")
        return
    print(f"  Loaded {len(df)} bars")

    # Load M15/M5 if MTF mode
    m15_bars = None
    m5_bars = None
    if params["mtf_mode"] != "h1_only":
        m15_bars = load_m15_bars()
        m5_bars = load_m5_bars()
        reset_mtf_caches()

    # Compute predictions
    print("\n  Computing predictions...")
    alpha_proba, meta_proba, atr_values = compute_predictions(df, bundle)
    print(f"  Predictions: {len(alpha_proba)} bars")

    # Run shadow session
    print("\n  Running shadow session (READ-ONLY)...")
    signals = run_shadow_session(df, alpha_proba, meta_proba, atr_values, params,
                                  m15_bars, m5_bars, args.symbol, args.max_signals)

    # Stats
    shadow_signals = [s for s in signals if s["final_decision"] == "SHADOW_SIGNAL"]
    rejected = [s for s in signals if s["final_decision"] == "REJECT"]
    print(f"\n  Shadow signals: {len(shadow_signals)}")
    print(f"  Rejected: {len(rejected)}")
    print(f"  Total evaluated: {len(signals)}")

    # Rejection breakdown
    reject_reasons = {}
    for s in rejected:
        reason = s["reject_reason"].split(":")[0].split("_")[0]  # first word
        reject_reasons[reason] = reject_reasons.get(reason, 0) + 1
    print(f"  Rejection breakdown: {reject_reasons}")

    # Write outputs
    print("\n  Writing outputs...")

    # shadow_signals.csv
    with open(OUTPUT_DIR / "shadow_signals.csv", "w", newline="") as f:
        if signals:
            w = csv.DictWriter(f, fieldnames=list(signals[0].keys()))
            w.writeheader()
            for s in signals:
                w.writerow(s)

    # shadow_journal.jsonl
    with open(OUTPUT_DIR / "shadow_journal.jsonl", "w") as f:
        for s in signals:
            f.write(json.dumps(s, default=str) + "\n")

    # Session summary
    summary = {
        "timestamp_utc": ts,
        "broker": args.broker,
        "symbol": args.symbol,
        "candidate_id": candidate["lock_id"],
        "model_profile": "v2_feature_normalized",
        "total_evaluated": len(signals),
        "shadow_signals": len(shadow_signals),
        "rejected": len(rejected),
        "rejection_breakdown": reject_reasons,
        "dry_run": True,
        "live_trading": False,
        "funded_trading": False,
        "production_ready": False,
        "no_order_sent": True,
        "broker_target": "MetaQuotes-Demo",
        "cto_review_required": True,
    }
    with open(OUTPUT_DIR / "shadow_session_summary.json", "w") as f:
        json.dump(summary, f, indent=2, default=str)

    with open(OUTPUT_DIR / "shadow_session_summary.md", "w") as f:
        f.write("# Shadow Session Summary (Sprint v2.8.7-H)\n\n")
        f.write(f"**Timestamp:** {ts}\n\n")
        f.write("## Session Overview\n\n")
        f.write(f"- Broker data: {args.broker}\n")
        f.write(f"- Symbol: {args.symbol}\n")
        f.write(f"- Candidate: {candidate['lock_id']}\n")
        f.write(f"- Model profile: v2_feature_normalized\n\n")
        f.write("## Results\n\n")
        f.write(f"- Total bars evaluated: {len(signals)}\n")
        f.write(f"- Shadow signals generated: {len(shadow_signals)}\n")
        f.write(f"- Rejected: {len(rejected)}\n\n")
        f.write("## Rejection Breakdown\n\n")
        for reason, count in sorted(reject_reasons.items(), key=lambda x: -x[1]):
            f.write(f"- {reason}: {count}\n")
        f.write("\n## Safety\n\n")
        f.write(f"- dry_run: True\n")
        f.write(f"- live_trading: False\n")
        f.write(f"- funded_trading: False\n")
        f.write(f"- production_ready: False\n")
        f.write(f"- NO_ORDER_SENT: True\n")
        f.write(f"- Broker target: MetaQuotes-Demo\n")
        f.write(f"- CTO review required: True\n\n")
        f.write("## Shadow Signals (first 10)\n\n")
        f.write("| Timestamp | Direction | Alpha | Meta | Entry | SL | TP | Lot |\n")
        f.write("|---|---|---|---|---|---|---|---|\n")
        for s in shadow_signals[:10]:
            f.write(f"| {s['timestamp']} | {s['direction']} | {s['alpha']} | "
                    f"{s['meta']} | {s.get('hypothetical_entry', 'N/A')} | "
                    f"{s['hypothetical_sl']} | {s['hypothetical_tp']} | "
                    f"{s['hypothetical_lot']} |\n")

    print(f"\n  Output: {OUTPUT_DIR}")
    print("\n" + "=" * 70)
    print("  READ-ONLY SHADOW COMPLETE — NO ORDERS SENT")
    print("  CTO review required before any demo activity")
    print("=" * 70)


if __name__ == "__main__":
    main()
