#!/usr/bin/env python3
"""TITAN XAU AI - Feature v2 Build Script (Sprint v2.8.7-E)
=============================================================
Builds v2 feature datasets, scaler, and drift comparison.

Tasks:
  Task 1: Feature schema v2 audit (classify all 55 v1 features)
  Task 2: Build v2 feature datasets for canonical H1 (2020-2026)
  Task 3: Feature drift recheck (v1 vs v2 IS vs OOS)

Outputs (all under data/reports/feature_v2/):
  - feature_schema_v2_audit.md
  - feature_schema_v2_audit.csv
  - feature_v2_build_report.md
  - feature_drift_v1_vs_v2.md
  - feature_drift_v1_vs_v2.csv

Datasets (under titan/data/features_v2/):
  - XAUUSD_H1_features_v2.parquet
  - XAUUSD_H1_labels_v2.parquet
  - XAUUSD_H1_X_train_v2.parquet (train 2020-2024)
  - XAUUSD_H1_X_val_v2.parquet   (val 2025)
  - XAUUSD_H1_X_test_v2.parquet  (OOS 2026)
  - XAUUSD_H1_y_train_v2.parquet
  - XAUUSD_H1_y_val_v2.parquet
  - XAUUSD_H1_y_test_v2.parquet
  - scaler_stats_v2.json
  - feature_schema_v2.json

NEVER sends orders. NEVER creates tokens. NEVER trades.
"""
from __future__ import annotations
import sys, json, csv, os
from pathlib import Path
from datetime import datetime, timezone
import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

OUTPUT_DIR = REPO_ROOT / "data" / "reports" / "feature_v2"
FEATURES_DIR = REPO_ROOT / "titan" / "data" / "features_v2"

from titan.production.feature_stream import H1FeatureStream, FEATURE_NAMES
from titan.training.feature_engine_v2 import compute_v2_features, compute_scaler_stats_v2
from titan.training.feature_schema_v2 import (
    FEATURE_NAMES_V1, FEATURE_NAMES_V2, ABSOLUTE_TO_RELATIVE,
    ABSOLUTE_FEATURES_V1, STATIONARY_FEATURES, BROKER_SENSITIVE,
    classify_feature, META_FEATURE_NAMES_V1, META_FEATURE_NAMES_V2,
)
from titan.production.spread_normalization import normalize_xauusd_spread_to_usd


def task1_schema_audit():
    """Task 1: Build feature schema v2 audit."""
    print("  [Task 1] Building feature schema v2 audit...")
    rows = []
    for old_name in FEATURE_NAMES_V1:
        classification = classify_feature(old_name)
        if old_name in ABSOLUTE_TO_RELATIVE:
            new_name = ABSOLUTE_TO_RELATIVE[old_name]
            reason = "Absolute price/value feature → replaced by relative/stationary"
            status = "REPLACED"
            expected_drift_after = 0.5  # expected to drop from ~10+ to <0.5
        elif old_name in BROKER_SENSITIVE:
            new_name = old_name
            reason = "Broker-sensitive but already normalized by v2.8.7-C spread normalization"
            status = "SAFE"
            expected_drift_after = 0.3
        else:
            new_name = old_name
            reason = "Already stationary (return/ratio/z-score/cyclical)"
            status = "SAFE"
            expected_drift_after = 0.5
        rows.append({
            "old_feature": old_name,
            "new_feature": new_name,
            "reason": reason,
            "classification": classification,
            "drift_score_before": "",  # filled by Task 3
            "expected_drift_after": expected_drift_after,
            "status": status,
        })

    # Write audit CSV
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_DIR / "feature_schema_v2_audit.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for row in rows:
            w.writerow(row)

    # Write audit MD
    with open(OUTPUT_DIR / "feature_schema_v2_audit.md", "w") as f:
        f.write("# Feature Schema v2 Audit (Sprint v2.8.7-E)\n\n")
        f.write(f"**Timestamp:** {datetime.now(timezone.utc).isoformat()}\n\n")
        f.write(f"**v1 feature count:** {len(FEATURE_NAMES_V1)}\n")
        f.write(f"**v2 feature count:** {len(FEATURE_NAMES_V2)}\n")
        f.write(f"**Replaced features:** {len(ABSOLUTE_FEATURES_V1)}\n\n")
        f.write("## Replacements (absolute → relative/stationary)\n\n")
        f.write("| Old Feature | New Feature | Reason |\n")
        f.write("|---|---|---|\n")
        for old in ABSOLUTE_FEATURES_V1:
            new = ABSOLUTE_TO_RELATIVE[old]
            f.write(f"| {old} | {new} | Absolute price/value drift fixed |\n")
        f.write("\n## Full Feature Classification\n\n")
        f.write("| Old Feature | New Feature | Classification | Status |\n")
        f.write("|---|---|---|---|\n")
        for row in rows:
            f.write(f"| {row['old_feature']} | {row['new_feature']} | "
                    f"{row['classification']} | {row['status']} |\n")
        f.write("\n## Meta-Feature Mapping\n\n")
        f.write("| v1 Meta Feature | v2 Meta Feature |\n|---|---|\n")
        for v1, v2 in zip(META_FEATURE_NAMES_V1, META_FEATURE_NAMES_V2):
            f.write(f"| {v1} | {v2} |\n")

    # Write feature_schema_v2.json (for runtime loading)
    FEATURES_DIR.mkdir(parents=True, exist_ok=True)
    schema_json = {
        "schema_version": "v2",
        "n_features": len(FEATURE_NAMES_V2),
        "feature_names_v2": FEATURE_NAMES_V2,
        "feature_names_v1": FEATURE_NAMES_V1,
        "absolute_to_relative": ABSOLUTE_TO_RELATIVE,
        "meta_feature_names_v2": META_FEATURE_NAMES_V2,
        "absolute_features_v1": ABSOLUTE_FEATURES_V1,
    }
    with open(FEATURES_DIR / "feature_schema_v2.json", "w") as f:
        json.dump(schema_json, f, indent=2)

    print(f"    Audit: {len(rows)} features classified, {len(ABSOLUTE_FEATURES_V1)} replaced")
    return rows


def task2_build_datasets():
    """Task 2: Build v2 feature datasets for canonical H1."""
    print("  [Task 2] Building v2 feature datasets...")

    # Load canonical H1 with spread normalization
    canon_path = REPO_ROOT / "titan" / "data" / "canonical" / "XAUUSD_H1_canonical.parquet"
    df_raw = pd.read_parquet(canon_path)
    if not isinstance(df_raw.index, pd.DatetimeIndex):
        df_raw.index = pd.to_datetime(df_raw.index)
    df = normalize_xauusd_spread_to_usd(df_raw.copy(), symbol="XAUUSD", source="canonical")

    # Prepare for v2 feature computation
    df_use = df[["open", "high", "low", "close"]].copy()
    if "volume" in df.columns:
        df_use["volume"] = df["volume"]
    elif "tick_volume" in df.columns:
        df_use["volume"] = df["tick_volume"]
    else:
        df_use["volume"] = 0.0
    df_use["spread"] = df["spread_usd"]

    # Compute v2 features
    print(f"    Computing v2 features on {len(df_use)} bars...")
    feats_df = compute_v2_features(df_use)
    print(f"    Features computed: {feats_df.shape}")

    # Generate labels (binary: next-bar return > 0 → 1)
    # Same label definition as v1: forward 5-bar return > 0
    horizon = 5
    fwd_ret = df_use["close"].shift(-horizon) / df_use["close"] - 1
    # Binary label: 1 if positive forward return exceeds spread+slippage cost
    # Use threshold of 0.0005 (5 bps) as cost proxy
    threshold = 0.0005
    labels = (fwd_ret > threshold).astype(int)
    labels.name = "label_long"

    # Drop NaN rows (warmup + last horizon bars)
    valid_mask = feats_df.notna().all(axis=1) & labels.notna()
    feats_df = feats_df[valid_mask]
    labels = labels[valid_mask]

    print(f"    Valid bars after NaN drop: {len(feats_df)}")
    print(f"    Label balance: {labels.value_counts().to_dict()}")

    # Save full features + labels
    FEATURES_DIR.mkdir(parents=True, exist_ok=True)
    feats_df.to_parquet(FEATURES_DIR / "XAUUSD_H1_features_v2.parquet")
    labels.to_frame().to_parquet(FEATURES_DIR / "XAUUSD_H1_labels_v2.parquet")

    # Time-based split (no leakage):
    # Primary split: train 2020-2024, val 2025, test 2026
    train_mask = feats_df.index.year <= 2024
    val_mask = feats_df.index.year == 2025
    test_mask = feats_df.index.year >= 2026

    X_train = feats_df[train_mask]
    X_val = feats_df[val_mask]
    X_test = feats_df[test_mask]
    y_train = labels[train_mask]
    y_val = labels[val_mask]
    y_test = labels[test_mask]

    X_train.to_parquet(FEATURES_DIR / "XAUUSD_H1_X_train_v2.parquet")
    X_val.to_parquet(FEATURES_DIR / "XAUUSD_H1_X_val_v2.parquet")
    X_test.to_parquet(FEATURES_DIR / "XAUUSD_H1_X_test_v2.parquet")
    y_train.to_frame().to_parquet(FEATURES_DIR / "XAUUSD_H1_y_train_v2.parquet")
    y_val.to_frame().to_parquet(FEATURES_DIR / "XAUUSD_H1_y_val_v2.parquet")
    y_test.to_frame().to_parquet(FEATURES_DIR / "XAUUSD_H1_y_test_v2.parquet")

    print(f"    Train: {len(X_train)} (2020-2024), positive rate: {y_train.mean():.3f}")
    print(f"    Val:   {len(X_val)} (2025), positive rate: {y_val.mean():.3f}")
    print(f"    Test:  {len(X_test)} (2026), positive rate: {y_test.mean():.3f}")

    # Compute scaler stats from TRAIN ONLY (no leakage)
    scaler = compute_scaler_stats_v2(X_train)
    with open(FEATURES_DIR / "scaler_stats_v2.json", "w") as f:
        json.dump(scaler, f, indent=2)

    # Build report
    with open(OUTPUT_DIR / "feature_v2_build_report.md", "w") as f:
        f.write("# Feature v2 Build Report (Sprint v2.8.7-E)\n\n")
        f.write(f"**Timestamp:** {datetime.now(timezone.utc).isoformat()}\n\n")
        f.write("## Source Data\n\n")
        f.write(f"- File: `titan/data/canonical/XAUUSD_H1_canonical.parquet`\n")
        f.write(f"- Total bars: {len(df_raw)}\n")
        f.write(f"- Date range: {df_raw.index.min()} → {df_raw.index.max()}\n")
        f.write(f"- Spread normalization: applied (v2.8.7-C)\n\n")
        f.write("## Feature Schema\n\n")
        f.write(f"- v1 features: {len(FEATURE_NAMES_V1)}\n")
        f.write(f"- v2 features: {len(FEATURE_NAMES_V2)}\n")
        f.write(f"- Replaced (absolute → relative): {len(ABSOLUTE_FEATURES_V1)}\n")
        f.write(f"- Replacements:\n")
        for old, new in ABSOLUTE_TO_RELATIVE.items():
            f.write(f"  - `{old}` → `{new}`\n")
        f.write("\n## Datasets Built\n\n")
        f.write(f"- Features: `titan/data/features_v2/XAUUSD_H1_features_v2.parquet` ({len(feats_df)} rows)\n")
        f.write(f"- Labels:   `titan/data/features_v2/XAUUSD_H1_labels_v2.parquet` ({len(labels)} rows)\n\n")
        f.write("## Time Splits (no leakage)\n\n")
        f.write(f"- Train (2020-2024): {len(X_train)} rows, positive rate {y_train.mean():.3f}\n")
        f.write(f"- Validation (2025): {len(X_val)} rows, positive rate {y_val.mean():.3f}\n")
        f.write(f"- Test/OOS (2026):    {len(X_test)} rows, positive rate {y_test.mean():.3f}\n\n")
        f.write("## Scaler Stats\n\n")
        f.write(f"- File: `titan/data/features_v2/scaler_stats_v2.json`\n")
        f.write(f"- Computed on TRAIN ONLY (2020-2024) — no leakage\n")
        f.write(f"- {len(scaler['mean'])} features\n\n")
        f.write("## Label Definition\n\n")
        f.write(f"- Horizon: {horizon} bars forward\n")
        f.write(f"- Threshold: {threshold} (5 bps cost proxy)\n")
        f.write(f"- Label 1 = forward return > threshold (long-profitable)\n")
        f.write(f"- Label 0 = forward return <= threshold\n")

    return {
        "n_train": len(X_train),
        "n_val": len(X_val),
        "n_test": len(X_test),
        "train_positive_rate": float(y_train.mean()),
        "val_positive_rate": float(y_val.mean()),
        "test_positive_rate": float(y_test.mean()),
    }


def task3_drift_recheck(build_info):
    """Task 3: Compare v1 vs v2 feature drift (IS vs OOS)."""
    print("  [Task 3] Feature drift recheck (v1 vs v2)...")

    # Load v2 features (just built)
    feats_v2 = pd.read_parquet(FEATURES_DIR / "XAUUSD_H1_features_v2.parquet")

    # Load v1 features via H1FeatureStream on canonical
    canon_path = REPO_ROOT / "titan" / "data" / "canonical" / "XAUUSD_H1_canonical.parquet"
    df_raw = pd.read_parquet(canon_path)
    if not isinstance(df_raw.index, pd.DatetimeIndex):
        df_raw.index = pd.to_datetime(df_raw.index)
    df_raw = normalize_xauusd_spread_to_usd(df_raw.copy(), symbol="XAUUSD", source="canonical")

    df_use = df_raw[["open", "high", "low", "close"]].copy()
    if "tick_volume" in df_raw.columns:
        df_use["volume"] = df_raw["tick_volume"]
    else:
        df_use["volume"] = 0.0
    df_use["spread"] = df_raw["spread_usd"]

    stream_v1 = H1FeatureStream()
    stream_v1._bars = df_use
    feats_v1 = stream_v1._compute_features()

    # Align indices
    common_idx = feats_v1.index.intersection(feats_v2.index)
    feats_v1 = feats_v1.loc[common_idx]
    feats_v2 = feats_v2.loc[common_idx]

    # IS = 2020-2023, OOS = 2025-2026 (same as v2.8.7-D)
    is_mask = (common_idx.year >= 2020) & (common_idx.year <= 2023)
    oos_mask = (common_idx.year >= 2025) & (common_idx.year <= 2026)

    is_v1 = feats_v1[is_mask]
    oos_v1 = feats_v1[oos_mask]
    is_v2 = feats_v2[is_mask]
    oos_v2 = feats_v2[oos_mask]

    print(f"    IS bars: {len(is_v1)}, OOS bars: {len(oos_v1)}")

    # Compute drift for each v1 feature
    drift_rows = []
    for v1_name in FEATURE_NAMES_V1:
        v2_name = ABSOLUTE_TO_RELATIVE.get(v1_name, v1_name)

        is_col_v1 = is_v1[v1_name].replace([np.inf, -np.inf], np.nan).dropna()
        oos_col_v1 = oos_v1[v1_name].replace([np.inf, -np.inf], np.nan).dropna()
        is_col_v2 = is_v2[v2_name].replace([np.inf, -np.inf], np.nan).dropna()
        oos_col_v2 = oos_v2[v2_name].replace([np.inf, -np.inf], np.nan).dropna()

        is_mean_v1 = float(is_col_v1.mean()) if len(is_col_v1) else 0
        oos_mean_v1 = float(oos_col_v1.mean()) if len(oos_col_v1) else 0
        is_std_v1 = float(is_col_v1.std()) if len(is_col_v1) else 0
        drift_v1 = abs(is_mean_v1 - oos_mean_v1) / max(abs(is_std_v1), 0.001)

        is_mean_v2 = float(is_col_v2.mean()) if len(is_col_v2) else 0
        oos_mean_v2 = float(oos_col_v2.mean()) if len(oos_col_v2) else 0
        is_std_v2 = float(is_col_v2.std()) if len(is_col_v2) else 0
        drift_v2 = abs(is_mean_v2 - oos_mean_v2) / max(abs(is_std_v2), 0.001)

        improvement = drift_v1 - drift_v2
        improvement_pct = (improvement / drift_v1 * 100) if drift_v1 > 0 else 0

        drift_rows.append({
            "v1_feature": v1_name,
            "v2_feature": v2_name,
            "v1_drift_score": round(drift_v1, 4),
            "v2_drift_score": round(drift_v2, 4),
            "drift_improvement": round(improvement, 4),
            "drift_improvement_pct": round(improvement_pct, 2),
            "v1_is_mean": round(is_mean_v1, 6),
            "v1_oos_mean": round(oos_mean_v1, 6),
            "v2_is_mean": round(is_mean_v2, 6),
            "v2_oos_mean": round(oos_mean_v2, 6),
            "classification": classify_feature(v1_name),
        })

    # Sort by v1 drift descending (show worst v1 features first)
    drift_rows.sort(key=lambda x: x["v1_drift_score"], reverse=True)

    # Write CSV
    with open(OUTPUT_DIR / "feature_drift_v1_vs_v2.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(drift_rows[0].keys()))
        w.writeheader()
        for row in drift_rows:
            w.writerow(row)

    # Write MD
    with open(OUTPUT_DIR / "feature_drift_v1_vs_v2.md", "w") as f:
        f.write("# Feature Drift v1 vs v2 (Sprint v2.8.7-E)\n\n")
        f.write(f"**Timestamp:** {datetime.now(timezone.utc).isoformat()}\n\n")
        f.write(f"**IS period:** 2020-2023 ({len(is_v1)} bars)\n")
        f.write(f"**OOS period:** 2025-2026 ({len(oos_v1)} bars)\n\n")
        f.write("## Top 15 v1 Drifted Features (with v2 Comparison)\n\n")
        f.write("| v1 Feature | v2 Feature | v1 Drift | v2 Drift | Improvement % | Classification |\n")
        f.write("|---|---|---|---|---|---|\n")
        for row in drift_rows[:15]:
            f.write(f"| {row['v1_feature']} | {row['v2_feature']} | "
                    f"{row['v1_drift_score']} | {row['v2_drift_score']} | "
                    f"{row['drift_improvement_pct']}% | {row['classification']} |\n")
        f.write("\n## Acceptance Check\n\n")
        # Check: top 5 v1 drifted features must have v2 drift < 1.0
        top5_v1 = drift_rows[:5]
        v2_passing = sum(1 for r in top5_v1 if r["v2_drift_score"] < 1.0)
        f.write(f"- Top 5 v1 drifted features: {[r['v1_feature'] for r in top5_v1]}\n")
        f.write(f"- Top 5 v2 drift scores: {[r['v2_drift_score'] for r in top5_v1]}\n")
        f.write(f"- Features with v2 drift < 1.0: {v2_passing}/5\n")
        if v2_passing >= 4:
            f.write(f"- **ACCEPTANCE: PASS** — v2 normalization materially reduced drift\n")
            acceptance = "PASS"
        elif v2_passing >= 3:
            f.write(f"- **ACCEPTANCE: MARGINAL** — v2 reduced most drift but some remain\n")
            acceptance = "MARGINAL"
        else:
            f.write(f"- **ACCEPTANCE: FAIL** — v2 drift still severe\n")
            acceptance = "FAIL"

    # Print summary
    print(f"\n    Top 5 v1 drifted features:")
    for r in drift_rows[:5]:
        print(f"      {r['v1_feature']:25s} v1_drift={r['v1_drift_score']:8.2f}  "
              f"v2_drift={r['v2_drift_score']:8.2f}  improvement={r['drift_improvement_pct']:6.1f}%")
    print(f"\n    Acceptance: {acceptance}")

    return drift_rows, acceptance


def main():
    ts = datetime.now(timezone.utc).isoformat()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    FEATURES_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("  TITAN XAU AI - FEATURE v2 BUILD (Sprint v2.8.7-E)")
    print("=" * 70)
    print(f"  Timestamp: {ts}\n")

    task1_schema_audit()
    build_info = task2_build_datasets()
    drift_rows, acceptance = task3_drift_recheck(build_info)

    print("\n" + "=" * 70)
    print("  FEATURE v2 BUILD SUMMARY")
    print("=" * 70)
    print(f"\n  Acceptance: {acceptance}")
    print(f"  Train: {build_info['n_train']} bars, pos rate {build_info['train_positive_rate']:.3f}")
    print(f"  Val:   {build_info['n_val']} bars, pos rate {build_info['val_positive_rate']:.3f}")
    print(f"  Test:  {build_info['n_test']} bars, pos rate {build_info['test_positive_rate']:.3f}")
    print(f"\n  Output: {OUTPUT_DIR}")
    print(f"  Datasets: {FEATURES_DIR}")
    print("\n" + "=" * 70)
    print("\n  > Research only. NOT production. NO trade allowed.")
    print("=" * 70)

    return {
        "timestamp_utc": ts,
        "acceptance": acceptance,
        "build_info": build_info,
        "top_drifted": [
            {"feature": r["v1_feature"], "v1_drift": r["v1_drift_score"],
             "v2_drift": r["v2_drift_score"]}
            for r in drift_rows[:5]
        ],
    }


if __name__ == "__main__":
    main()
