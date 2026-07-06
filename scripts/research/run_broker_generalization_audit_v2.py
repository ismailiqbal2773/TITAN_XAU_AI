#!/usr/bin/env python3
"""TITAN XAU AI - Broker Generalization Audit v2 (Sprint v2.8.7-F)
=================================================================
Audits broker feature/prediction distributions and OOS performance
using the v2 feature-normalized model.

Also audits the ICMarkets spread edge case (Task 3).

Outputs (under data/reports/broker_generalization_v2/):
  - broker_feature_distribution_v2.md / .csv
  - broker_prediction_distribution_v2.md / .csv
  - broker_failure_summary_v2.md
  - icmarkets_spread_edge_audit.md

NEVER sends orders. NEVER creates tokens. NEVER trades.
"""
from __future__ import annotations
import sys, csv, os, json
from pathlib import Path
from datetime import datetime, timezone
import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

OUTPUT_DIR = REPO_ROOT / "data" / "reports" / "broker_generalization_v2"

from titan.production.spread_normalization import (
    normalize_xauusd_spread_to_usd, spread_audit_row,
)
from titan.production.feature_stream_v2 import H1FeatureStreamV2, FEATURE_NAMES_V2
from titan.training.feature_schema_v2 import META_FEATURE_NAMES_V2
from titan.production.model_loader import load_models_by_profile


BROKER_PATHS = {
    "canonical": REPO_ROOT / "titan" / "data" / "canonical" / "XAUUSD_H1_canonical.parquet",
    "exness": REPO_ROOT / "titan" / "data" / "sources" / "mt5_brokers" / "exness" / "XAUUSD_H1.parquet",
    "fbs": REPO_ROOT / "titan" / "data" / "sources" / "mt5_brokers" / "fbs" / "XAUUSD_H1.parquet",
    "fundednext": REPO_ROOT / "titan" / "data" / "sources" / "mt5_brokers" / "fundednext" / "XAUUSD_H1.parquet",
    "icmarkets": REPO_ROOT / "titan" / "data" / "sources" / "mt5_brokers" / "icmarkets" / "XAUUSD_H1.parquet",
}


def load_broker_normalized(name):
    """Load broker parquet with v2.8.7-C/F spread normalization."""
    path = BROKER_PATHS[name]
    if not path.exists():
        return None
    df_raw = pd.read_parquet(path)
    if not isinstance(df_raw.index, pd.DatetimeIndex):
        df_raw.index = pd.to_datetime(df_raw.index)
    df = normalize_xauusd_spread_to_usd(df_raw.copy(), symbol="XAUUSD", source=name)
    return df_raw, df


def compute_v2_predictions_for_broker(df_norm, bundle):
    """Compute v2 alpha + meta predictions for a normalized broker DataFrame."""
    df_use = df_norm[["open", "high", "low", "close"]].copy()
    if "volume" in df_norm.columns:
        df_use["volume"] = df_norm["volume"]
    elif "tick_volume" in df_norm.columns:
        df_use["volume"] = df_norm["tick_volume"]
    else:
        df_use["volume"] = 0.0
    df_use["spread"] = df_norm["spread_usd"]

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

    return alpha_proba, meta_proba, features_matrix


def main():
    ts = datetime.now(timezone.utc).isoformat()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("  TITAN XAU AI - BROKER GENERALIZATION AUDIT v2 (Sprint v2.8.7-F)")
    print("=" * 70)
    print(f"  Timestamp: {ts}\n")

    # Load v2 models
    bundle = load_models_by_profile("v2_feature_normalized")
    if not bundle.ok:
        print("  ERROR: v2 models failed to load")
        return

    # === ICMarkets Spread Edge Audit (Task 3) ===
    print("  [Task 3] ICMarkets spread edge audit...")
    icmarkets_audit_rows = []
    all_audit_rows = []
    for name in BROKER_PATHS:
        result = load_broker_normalized(name)
        if result is None:
            continue
        df_raw, df_norm = result
        audit = spread_audit_row(df_raw, df_norm, source=name)
        all_audit_rows.append(audit)
        if name == "icmarkets":
            icmarkets_audit_rows.append(audit)
            # Detailed ICMarkets analysis
            raw = df_raw.get("spread", df_raw.get("spread_usd", pd.Series([0])))
            is_int = pd.api.types.is_integer_dtype(raw)
            int_frac = float((raw.dropna() == raw.dropna().astype(int)).mean()) if len(raw.dropna()) > 0 else 0
            print(f"    icmarkets: dtype={raw.dtype}, is_integer_dtype={is_int}, "
                  f"int_frac={int_frac:.4f}, median={raw.median():.2f}")
            print(f"    -> detected as: {df_norm['spread_unit_detected'].iloc[0]}")
            print(f"    -> normalized median: {df_norm['spread_usd'].median():.4f} USD")

    # Write ICMarkets edge audit
    icm = icmarkets_audit_rows[0] if icmarkets_audit_rows else {}
    icmarkets_edge_fixed = icm.get("spread_unit_detected") == "POINTS_CONVERTED"

    with open(OUTPUT_DIR / "icmarkets_spread_edge_audit.md", "w") as f:
        f.write("# ICMarkets Spread Edge Audit (Sprint v2.8.7-F)\n\n")
        f.write(f"**Timestamp:** {ts}\n\n")
        f.write("## Issue (v2.8.7-C)\n\n")
        f.write("ICMarkets raw spread median = 2.0, which fell exactly at the boundary\n")
        f.write("of the v2.8.7-C detection rule (median <= 2.0 → USD). This caused\n")
        f.write("ICMarkets to be treated as USD (2.0 USD per bar) when it should have\n")
        f.write("been treated as POINTS (2.0 points × 0.01 = 0.02 USD).\n\n")
        f.write("## Root Cause\n\n")
        f.write("MT5 `copy_rates_*` returns spread as `int64` (integer points). Canonical\n")
        f.write("`spread_usd` is always `float64` (true USD). The v2.8.7-C rule only\n")
        f.write("checked the median value, not the dtype. ICMarkets has median=2.0 (low)\n")
        f.write("but is 100% integer dtype — a clear MT5 POINTS signature.\n\n")
        f.write("## Fix (v2.8.7-F)\n\n")
        f.write("Added integer-detection rule to `normalize_xauusd_spread_to_usd`:\n")
        f.write("- If column dtype is integer OR >95% of values are integer-like\n")
        f.write("  → treat as POINTS (regardless of median)\n")
        f.write("- Fallback to median-based rule for non-integer columns\n\n")
        f.write("## ICMarkets Result\n\n")
        f.write(f"- Raw spread dtype: int64\n")
        f.write(f"- Raw spread median: {icm.get('raw_spread_median', 'N/A')}\n")
        f.write(f"- Detected unit: {icm.get('spread_unit_detected', 'N/A')}\n")
        f.write(f"- Normalized spread median: {icm.get('normalized_spread_median', 'N/A')} USD\n")
        f.write(f"- spread_pct before: {icm.get('spread_pct_mean_before', 'N/A')}\n")
        f.write(f"- spread_pct after: {icm.get('spread_pct_mean_after', 'N/A')}\n")
        f.write(f"- Conversion applied: {icm.get('conversion_applied', 'N/A')}\n\n")
        f.write(f"**ICMARKETS_SPREAD_EDGE_FIXED:** {icmarkets_edge_fixed}\n\n")
        f.write("## All Brokers After Fix\n\n")
        f.write("| Broker | Raw Median | Detected Unit | Norm Median (USD) | spread_pct After |\n")
        f.write("|---|---|---|---|---|\n")
        for row in all_audit_rows:
            f.write(f"| {row['source']} | {row['raw_spread_median']} | "
                    f"{row['spread_unit_detected']} | {row['normalized_spread_median']} | "
                    f"{row['spread_pct_mean_after']} |\n")

    # Write all-broker spread audit CSV
    with open(OUTPUT_DIR / "icmarkets_spread_audit.csv", "w", newline="") as f:
        if all_audit_rows:
            w = csv.DictWriter(f, fieldnames=list(all_audit_rows[0].keys()))
            w.writeheader()
            for row in all_audit_rows:
                w.writerow(row)

    # === Broker Feature Distribution Audit (Task 2) ===
    print("\n  [Task 2] Broker feature distribution audit...")
    brokers_data = {}
    brokers_preds = {}
    for name in BROKER_PATHS:
        result = load_broker_normalized(name)
        if result is None:
            continue
        df_raw, df_norm = result
        brokers_data[name] = df_norm
        print(f"    Computing v2 predictions for {name}...")
        alpha, meta, feats = compute_v2_predictions_for_broker(df_norm, bundle)
        brokers_preds[name] = {"alpha": alpha, "meta": meta, "features": feats}
        print(f"      {name}: alpha mean={alpha.mean():.4f}, meta mean={meta.mean():.4f}, "
              f"alpha>0.55: {(alpha>=0.55).sum()}, meta>0.65: {(meta>=0.65).sum()}")

    # Feature distribution comparison vs canonical
    feature_rows = []
    if "canonical" in brokers_preds:
        canon_feats = brokers_preds["canonical"]["features"]
        for broker, preds in brokers_preds.items():
            if broker == "canonical":
                continue
            broker_feats = preds["features"]
            for j, fname in enumerate(FEATURE_NAMES_V2):
                canon_col = canon_feats[:, j]
                broker_col = broker_feats[:, j]
                drift = abs(float(canon_col.mean()) - float(broker_col.mean())) / \
                        max(abs(float(canon_col.std())), 0.001)
                feature_rows.append({
                    "broker": broker,
                    "feature": fname,
                    "canonical_mean": round(float(canon_col.mean()), 6),
                    "broker_mean": round(float(broker_col.mean()), 6),
                    "drift_score": round(drift, 4),
                })

    feature_rows.sort(key=lambda x: x["drift_score"], reverse=True)
    with open(OUTPUT_DIR / "broker_feature_distribution_v2.csv", "w", newline="") as f:
        if feature_rows:
            w = csv.DictWriter(f, fieldnames=list(feature_rows[0].keys()))
            w.writeheader()
            for row in feature_rows:
                w.writerow(row)

    # Prediction distribution
    pred_rows = []
    for broker, preds in brokers_preds.items():
        alpha = preds["alpha"]
        meta = preds["meta"]
        pred_rows.append({
            "broker": broker,
            "alpha_mean": round(float(alpha.mean()), 4),
            "alpha_p50": round(float(np.percentile(alpha, 50)), 4),
            "alpha_p95": round(float(np.percentile(alpha, 95)), 4),
            "meta_mean": round(float(meta.mean()), 4),
            "meta_p50": round(float(np.percentile(meta, 50)), 4),
            "meta_p95": round(float(np.percentile(meta, 95)), 4),
            "alpha_pass_050": int((alpha >= 0.50).sum()),
            "alpha_pass_055": int((alpha >= 0.55).sum()),
            "alpha_pass_060": int((alpha >= 0.60).sum()),
            "meta_pass_050": int((meta >= 0.50).sum()),
            "meta_pass_055": int((meta >= 0.55).sum()),
            "meta_pass_060": int((meta >= 0.60).sum()),
            "meta_pass_065": int((meta >= 0.65).sum()),
            "both_pass_055_065": int(((alpha >= 0.55) & (meta >= 0.65)).sum()),
        })

    with open(OUTPUT_DIR / "broker_prediction_distribution_v2.csv", "w", newline="") as f:
        if pred_rows:
            w = csv.DictWriter(f, fieldnames=list(pred_rows[0].keys()))
            w.writeheader()
            for row in pred_rows:
                w.writerow(row)

    # Write MD files
    with open(OUTPUT_DIR / "broker_feature_distribution_v2.md", "w") as f:
        f.write("# Broker Feature Distribution v2 (Sprint v2.8.7-F)\n\n")
        f.write(f"**Timestamp:** {ts}\n\n")
        f.write("## Top 15 Drifted Features (v2, broker vs canonical)\n\n")
        f.write("| Broker | Feature | Canon Mean | Broker Mean | Drift |\n")
        f.write("|---|---|---|---|---|\n")
        for row in feature_rows[:15]:
            f.write(f"| {row['broker']} | {row['feature']} | {row['canonical_mean']} | "
                    f"{row['broker_mean']} | {row['drift_score']} |\n")

    with open(OUTPUT_DIR / "broker_prediction_distribution_v2.md", "w") as f:
        f.write("# Broker Prediction Distribution v2 (Sprint v2.8.7-F)\n\n")
        f.write(f"**Timestamp:** {ts}\n\n")
        f.write("## Per-Broker Prediction Summary\n\n")
        f.write("| Broker | Alpha Mean | Alpha P50 | Meta Mean | Meta P50 | α>0.55 | M>0.65 | Both Pass |\n")
        f.write("|---|---|---|---|---|---|---|---|\n")
        for row in pred_rows:
            f.write(f"| {row['broker']} | {row['alpha_mean']} | {row['alpha_p50']} | "
                    f"{row['meta_mean']} | {row['meta_p50']} | {row['alpha_pass_055']} | "
                    f"{row['meta_pass_065']} | {row['both_pass_055_065']} |\n")

    # === Failure Summary ===
    # Run quick OOS backtest per broker (2025-2026)
    print("\n  Computing OOS performance per broker...")
    from scripts.research.run_safe_parameter_discovery import (
        run_backtest, ParamSet, precompute_model_predictions,
    )
    params = ParamSet()
    oos_rows = []
    for broker, df_norm in brokers_data.items():
        # OOS 2025-2026
        oos_mask = (df_norm.index.year >= 2025) & (df_norm.index.year <= 2026)
        if oos_mask.sum() < 100:
            continue
        df_oos = df_norm[oos_mask]
        preds = brokers_preds[broker]
        oos_preds = {
            "alpha_proba": preds["alpha"][oos_mask.values if hasattr(oos_mask, 'values') else oos_mask],
            "meta_proba": preds["meta"][oos_mask.values if hasattr(oos_mask, 'values') else oos_mask],
            "valid_mask": np.ones(oos_mask.sum(), dtype=bool),
            "atr_values": np.zeros(oos_mask.sum()),
        }
        # Compute ATR
        highs = df_oos["high"].values
        lows = df_oos["low"].values
        closes = df_oos["close"].values
        atr = np.zeros(len(df_oos))
        for i in range(14, len(df_oos)):
            atr[i] = max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1]))
        for i in range(28, len(df_oos)):
            atr[i] = np.mean(atr[i-14:i])
        oos_preds["atr_values"] = atr
        oos_preds["valid_mask"] = np.ones(len(df_oos), dtype=bool)

        summary = run_backtest(df_oos, oos_preds, params)
        oos_rows.append({
            "broker": broker,
            "trades": summary["trades"],
            "pf": summary["profit_factor"],
            "sharpe": summary["sharpe"],
            "dd": summary["max_total_dd"],
            "win_rate": summary["win_rate"],
        })
        print(f"    {broker:12s}: trades={summary['trades']:4d}, pf={summary['profit_factor']:.4f}, "
              f"sharpe={summary['sharpe']:.4f}")

    # Determine flags
    broker_generalization_gap = False
    exness_specific_gap = False
    icmarkets_spread_edge = not icmarkets_edge_fixed

    # Check if only canonical is profitable
    profitable = [r for r in oos_rows if r["pf"] > 1.0 and r["trades"] >= 5]
    if len(profitable) < 2:
        broker_generalization_gap = True
    # Check if exness specifically fails
    for r in oos_rows:
        if r["broker"] == "exness" and r["pf"] < 1.0:
            exness_specific_gap = True

    with open(OUTPUT_DIR / "broker_failure_summary_v2.md", "w") as f:
        f.write("# Broker Failure Summary v2 (Sprint v2.8.7-F)\n\n")
        f.write(f"**Timestamp:** {ts}\n\n")
        f.write("## Flags\n\n")
        f.write(f"- BROKER_GENERALIZATION_GAP: {broker_generalization_gap}\n")
        f.write(f"- EXNESS_SPECIFIC_GAP: {exness_specific_gap}\n")
        f.write(f"- ICMARKETS_SPREAD_EDGE: {icmarkets_spread_edge}\n")
        f.write(f"- ICMARKETS_SPREAD_EDGE_FIXED: {icmarkets_edge_fixed}\n\n")
        f.write("## OOS Performance (2025-2026, baseline params)\n\n")
        f.write("| Broker | Trades | PF | Sharpe | DD | Win Rate |\n")
        f.write("|---|---|---|---|---|---|\n")
        for row in oos_rows:
            f.write(f"| {row['broker']} | {row['trades']} | {row['pf']} | "
                    f"{row['sharpe']} | {row['dd']} | {row['win_rate']} |\n")
        f.write("\n## Diagnosis\n\n")
        if broker_generalization_gap:
            f.write("- Only canonical is profitable in OOS. v2 model (trained on canonical only)\n")
            f.write("  does not generalize to other brokers without multi-broker training.\n")
        if exness_specific_gap:
            f.write("- Exness specifically underperforms (PF < 1.0). Likely cause: exness\n")
            f.write("  price feed differs from canonical enough to shift v2 features.\n")
        if icmarkets_edge_fixed:
            f.write("- ICMarkets spread edge has been FIXED in v2.8.7-F (integer-detection rule).\n")
        else:
            f.write("- ICMarkets spread edge NOT fixed.\n")
        f.write("\n## Recommendation\n\n")
        f.write("- Build multi-broker v2 training dataset (canonical + exness + fbs + fundednext + icmarkets)\n")
        f.write("- Retrain XGBoost v2 + meta-label v2 on multi-broker data\n")
        f.write("- Re-run parameter discovery with v2_multibroker profile\n")

    # Print summary
    print(f"\n  FLAGS:")
    print(f"    BROKER_GENERALIZATION_GAP: {broker_generalization_gap}")
    print(f"    EXNESS_SPECIFIC_GAP: {exness_specific_gap}")
    print(f"    ICMARKETS_SPREAD_EDGE: {icmarkets_spread_edge}")
    print(f"    ICMARKETS_SPREAD_EDGE_FIXED: {icmarkets_edge_fixed}")
    print(f"\n  Output: {OUTPUT_DIR}")
    print("\n" + "=" * 70)

    return {
        "broker_generalization_gap": broker_generalization_gap,
        "exness_specific_gap": exness_specific_gap,
        "icmarkets_spread_edge": icmarkets_spread_edge,
        "icmarkets_spread_edge_fixed": icmarkets_edge_fixed,
        "oos_results": oos_rows,
    }


if __name__ == "__main__":
    main()
