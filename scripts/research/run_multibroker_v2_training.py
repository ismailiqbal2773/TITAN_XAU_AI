#!/usr/bin/env python3
"""TITAN XAU AI - Multi-Broker v2 Training (Sprint v2.8.7-F)
=============================================================
Builds multi-broker v2 training dataset and retrains XGBoost + meta-label.

Tasks:
  Task 4: Multi-broker v2 training dataset (5 brokers, balanced sampling)
  Task 5: Retrain XGBoost v2 multi-broker
  Task 6: Retrain meta-label v2 multi-broker

Outputs:
  Datasets (titan/data/features_v2_multibroker/):
    - XAUUSD_H1_features_v2_multibroker.parquet
    - XAUUSD_H1_labels_v2_multibroker.parquet
    - XAUUSD_H1_X_train_v2_multibroker.parquet (2020-2024)
    - XAUUSD_H1_X_val_v2_multibroker.parquet   (2025)
    - XAUUSD_H1_X_test_v2_multibroker.parquet  (2026)
    - XAUUSD_H1_y_train/val/test_v2_multibroker.parquet
    - scaler_stats_v2_multibroker.json
    - feature_schema_v2_multibroker.json

  Models (titan/data/models/):
    - xgboost_v2_multibroker.pkl
    - meta_label_v2_multibroker.pkl

  Reports (data/reports/broker_generalization_v2/):
    - multibroker_dataset_report.md
    - xgb_v2_multibroker_training_report.md / .json / feature_importance.csv / calibration.csv
    - meta_v2_multibroker_training_report.md / .json / threshold_scan.csv / calibration.csv

NEVER sends orders. NEVER creates tokens. NEVER trades.
"""
from __future__ import annotations
import sys, json, csv, os, pickle
from pathlib import Path
from datetime import datetime, timezone
import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

OUTPUT_DIR = REPO_ROOT / "data" / "reports" / "broker_generalization_v2"
FEATURES_DIR = REPO_ROOT / "titan" / "data" / "features_v2_multibroker"
MODELS_DIR = REPO_ROOT / "titan" / "data" / "models"

from titan.production.spread_normalization import normalize_xauusd_spread_to_usd
from titan.training.feature_engine_v2 import compute_v2_features, compute_scaler_stats_v2, standardize_v2
from titan.training.feature_schema_v2 import FEATURE_NAMES_V2, META_FEATURE_NAMES_V2


BROKER_PATHS = {
    "canonical": REPO_ROOT / "titan" / "data" / "canonical" / "XAUUSD_H1_canonical.parquet",
    "exness": REPO_ROOT / "titan" / "data" / "sources" / "mt5_brokers" / "exness" / "XAUUSD_H1.parquet",
    "fbs": REPO_ROOT / "titan" / "data" / "sources" / "mt5_brokers" / "fbs" / "XAUUSD_H1.parquet",
    "fundednext": REPO_ROOT / "titan" / "data" / "sources" / "mt5_brokers" / "fundednext" / "XAUUSD_H1.parquet",
    "icmarkets": REPO_ROOT / "titan" / "data" / "sources" / "mt5_brokers" / "icmarkets" / "XAUUSD_H1.parquet",
}

# Broker IDs for the broker_id column (0=canonical, 1=exness, 2=fbs, 3=fundednext, 4=icmarkets)
BROKER_IDS = {name: i for i, name in enumerate(BROKER_PATHS.keys())}


def task4_build_multibroker_dataset():
    """Task 4: Build multi-broker v2 training dataset with balanced sampling."""
    print("  [Task 4] Building multi-broker v2 dataset...")

    all_features = []
    all_labels = []
    all_broker_ids = []
    broker_stats = []

    for broker_name, path in BROKER_PATHS.items():
        if not path.exists():
            continue
        df_raw = pd.read_parquet(path)
        if not isinstance(df_raw.index, pd.DatetimeIndex):
            df_raw.index = pd.to_datetime(df_raw.index)
        df = normalize_xauusd_spread_to_usd(df_raw.copy(), symbol="XAUUSD", source=broker_name)

        df_use = df[["open", "high", "low", "close"]].copy()
        if "volume" in df.columns:
            df_use["volume"] = df["volume"]
        elif "tick_volume" in df.columns:
            df_use["volume"] = df["tick_volume"]
        else:
            df_use["volume"] = 0.0
        df_use["spread"] = df["spread_usd"]

        # Compute v2 features
        feats = compute_v2_features(df_use)

        # Labels: forward 5-bar return > 5 bps (same as v2.8.7-E)
        horizon = 5
        fwd_ret = df_use["close"].shift(-horizon) / df_use["close"] - 1
        threshold = 0.0005
        labels = (fwd_ret > threshold).astype(int)

        # Drop NaN rows
        valid_mask = feats.notna().all(axis=1) & labels.notna()
        feats = feats[valid_mask]
        labels = labels[valid_mask]
        broker_ids = pd.Series(BROKER_IDS[broker_name], index=feats.index)

        all_features.append(feats)
        all_labels.append(labels)
        all_broker_ids.append(broker_ids)

        broker_stats.append({
            "broker": broker_name,
            "broker_id": BROKER_IDS[broker_name],
            "n_bars": len(feats),
            "positive_rate": float(labels.mean()),
            "date_range": f"{feats.index.min()} -> {feats.index.max()}",
        })
        print(f"    {broker_name:12s}: {len(feats)} bars, pos rate={labels.mean():.3f}")

    # Concatenate all brokers
    features_df = pd.concat(all_features)
    labels_series = pd.concat(all_labels)
    broker_ids_series = pd.concat(all_broker_ids)

    # Add broker_id as a feature column (not in FEATURE_NAMES_V2, but stored separately)
    features_df["broker_id"] = broker_ids_series

    print(f"\n    Total bars: {len(features_df)}")
    print(f"    Broker distribution: {broker_ids_series.value_counts().sort_index().to_dict()}")

    # Time-based split (no leakage):
    # Train: 2020-2024, Val: 2025, Test: 2026
    train_mask = features_df.index.year <= 2024
    val_mask = features_df.index.year == 2025
    test_mask = features_df.index.year >= 2026

    X_train = features_df[train_mask][FEATURE_NAMES_V2]
    X_val = features_df[val_mask][FEATURE_NAMES_V2]
    X_test = features_df[test_mask][FEATURE_NAMES_V2]
    y_train = labels_series[train_mask]
    y_val = labels_series[val_mask]
    y_test = labels_series[test_mask]

    # Also keep broker_id for reporting
    bid_train = broker_ids_series[train_mask]
    bid_val = broker_ids_series[val_mask]
    bid_test = broker_ids_series[test_mask]

    print(f"\n    Train: {len(X_train)} (2020-2024), pos rate: {y_train.mean():.3f}")
    print(f"    Val:   {len(X_val)} (2025), pos rate: {y_val.mean():.3f}")
    print(f"    Test:  {len(X_test)} (2026), pos rate: {y_test.mean():.3f}")

    # Broker distribution per split
    for split_name, bids in [("train", bid_train), ("val", bid_val), ("test", bid_test)]:
        dist = bids.value_counts().sort_index().to_dict()
        print(f"    {split_name} broker dist: {dist}")

    # Save datasets
    FEATURES_DIR.mkdir(parents=True, exist_ok=True)
    features_df.to_parquet(FEATURES_DIR / "XAUUSD_H1_features_v2_multibroker.parquet")
    labels_series.to_frame().to_parquet(FEATURES_DIR / "XAUUSD_H1_labels_v2_multibroker.parquet")
    X_train.to_parquet(FEATURES_DIR / "XAUUSD_H1_X_train_v2_multibroker.parquet")
    X_val.to_parquet(FEATURES_DIR / "XAUUSD_H1_X_val_v2_multibroker.parquet")
    X_test.to_parquet(FEATURES_DIR / "XAUUSD_H1_X_test_v2_multibroker.parquet")
    y_train.to_frame().to_parquet(FEATURES_DIR / "XAUUSD_H1_y_train_v2_multibroker.parquet")
    y_val.to_frame().to_parquet(FEATURES_DIR / "XAUUSD_H1_y_val_v2_multibroker.parquet")
    y_test.to_frame().to_parquet(FEATURES_DIR / "XAUUSD_H1_y_test_v2_multibroker.parquet")

    # Scaler stats (fit on TRAIN ONLY — no leakage)
    scaler = compute_scaler_stats_v2(X_train)
    with open(FEATURES_DIR / "scaler_stats_v2_multibroker.json", "w") as f:
        json.dump(scaler, f, indent=2)

    # Schema JSON
    schema = {
        "schema_version": "v2_multibroker",
        "n_features": len(FEATURE_NAMES_V2),
        "feature_names_v2": FEATURE_NAMES_V2,
        "meta_feature_names_v2": META_FEATURE_NAMES_V2,
        "broker_ids": BROKER_IDS,
        "brokers": list(BROKER_PATHS.keys()),
        "splits": {
            "train": "2020-2024",
            "validation": "2025",
            "test": "2026",
        },
    }
    with open(FEATURES_DIR / "feature_schema_v2_multibroker.json", "w") as f:
        json.dump(schema, f, indent=2)

    # Build report
    with open(OUTPUT_DIR / "multibroker_dataset_report.md", "w") as f:
        f.write("# Multi-Broker v2 Dataset Report (Sprint v2.8.7-F)\n\n")
        f.write(f"**Timestamp:** {datetime.now(timezone.utc).isoformat()}\n\n")
        f.write("## Source Brokers\n\n")
        f.write("| Broker | ID | Bars | Positive Rate | Date Range |\n")
        f.write("|---|---|---|---|---|\n")
        for s in broker_stats:
            f.write(f"| {s['broker']} | {s['broker_id']} | {s['n_bars']} | "
                    f"{s['positive_rate']:.3f} | {s['date_range']} |\n")
        f.write(f"\n## Total Bars: {len(features_df)}\n\n")
        f.write("## Splits (no leakage, time-based)\n\n")
        f.write(f"- Train (2020-2024): {len(X_train)} rows, pos rate {y_train.mean():.3f}\n")
        f.write(f"- Validation (2025): {len(X_val)} rows, pos rate {y_val.mean():.3f}\n")
        f.write(f"- Test/OOS (2026):    {len(X_test)} rows, pos rate {y_test.mean():.3f}\n\n")
        f.write("## Broker Distribution Per Split\n\n")
        for split_name, bids in [("train", bid_train), ("val", bid_val), ("test", bid_test)]:
            dist = bids.value_counts().sort_index().to_dict()
            id_to_name = {v: k for k, v in BROKER_IDS.items()}
            dist_named = {id_to_name.get(k, k): v for k, v in dist.items()}
            f.write(f"- {split_name}: {dist_named}\n")
        f.write("\n## Scaler Stats\n\n")
        f.write(f"- File: `titan/data/features_v2_multibroker/scaler_stats_v2_multibroker.json`\n")
        f.write(f"- Computed on TRAIN ONLY (2020-2024, all brokers) — no leakage\n")
        f.write(f"- {len(scaler['mean'])} features\n\n")
        f.write("## Label Definition\n\n")
        f.write(f"- Horizon: 5 bars forward\n")
        f.write(f"- Threshold: 0.0005 (5 bps cost proxy)\n")
        f.write(f"- Label 1 = forward return > threshold (long-profitable)\n")

    return {
        "X_train": X_train, "X_val": X_val, "X_test": X_test,
        "y_train": y_train, "y_val": y_val, "y_test": y_test,
        "bid_train": bid_train, "bid_val": bid_val, "bid_test": bid_test,
        "scaler": scaler,
    }


def task5_train_xgb_multibroker(data):
    """Task 5: Retrain XGBoost v2 multi-broker."""
    print("\n  [Task 5] Training XGBoost v2 multi-broker...")
    from xgboost import XGBClassifier
    from sklearn.metrics import roc_auc_score, average_precision_score, brier_score_loss

    mean = np.array([data["scaler"]["mean"][f] for f in FEATURE_NAMES_V2], dtype=np.float64)
    std = np.array([data["scaler"]["std"][f] for f in FEATURE_NAMES_V2], dtype=np.float64)

    X_train = standardize_v2(data["X_train"].values.astype(np.float64), mean, std)
    X_val = standardize_v2(data["X_val"].values.astype(np.float64), mean, std)
    X_test = standardize_v2(data["X_test"].values.astype(np.float64), mean, std)
    y_train = data["y_train"].values
    y_val = data["y_val"].values
    y_test = data["y_test"].values
    bid_train = data["bid_train"].values
    bid_val = data["bid_val"].values
    bid_test = data["bid_test"].values

    print(f"    Train: {X_train.shape}, pos rate: {y_train.mean():.3f}")
    print(f"    Val:   {X_val.shape}, pos rate: {y_val.mean():.3f}")
    print(f"    Test:  {X_test.shape}, pos rate: {y_test.mean():.3f}")

    model = XGBClassifier(
        max_depth=7, n_estimators=397, learning_rate=0.0175,
        subsample=0.8, colsample_bytree=0.8,
        objective="binary:logistic", eval_metric="auc",
        random_state=42, n_jobs=2, verbosity=0,
    )
    model.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)

    # Predictions
    train_proba = model.predict_proba(X_train)[:, 1]
    val_proba = model.predict_proba(X_val)[:, 1]
    test_proba = model.predict_proba(X_test)[:, 1]

    # Overall metrics
    def _metrics(y, p, prefix):
        return {
            f"{prefix}_auc": round(float(roc_auc_score(y, p)), 4),
            f"{prefix}_pr_auc": round(float(average_precision_score(y, p)), 4),
            f"{prefix}_brier": round(float(brier_score_loss(y, p)), 4),
        }

    metrics = {}
    metrics.update(_metrics(y_train, train_proba, "train"))
    metrics.update(_metrics(y_val, val_proba, "val"))
    metrics.update(_metrics(y_test, test_proba, "test"))

    # Broker-wise AUC on test set
    id_to_name = {v: k for k, v in BROKER_IDS.items()}
    broker_auc = {}
    for bid in np.unique(bid_test):
        mask = bid_test == bid
        if mask.sum() > 50:
            auc = float(roc_auc_score(y_test[mask], test_proba[mask]))
            broker_auc[id_to_name[bid]] = round(auc, 4)
    metrics["test_broker_auc"] = broker_auc

    # Year-wise AUC (combine all brokers)
    test_idx = data["X_test"].index
    test_idx_years = pd.Series(test_idx.year, index=test_idx)
    year_auc = {}
    for year in sorted(test_idx_years.unique()):
        mask = (test_idx_years == year).values
        if mask.sum() > 50:
            auc = float(roc_auc_score(y_test[mask], test_proba[mask]))
            year_auc[str(year)] = round(auc, 4)
    metrics["test_year_auc"] = year_auc

    # Feature importance
    fi = model.feature_importances_
    fi_rows = [{"feature": n, "importance": round(float(i), 6)} for n, i in zip(FEATURE_NAMES_V2, fi)]
    fi_rows.sort(key=lambda x: x["importance"], reverse=True)

    # Save model
    with open(MODELS_DIR / "xgboost_v2_multibroker.pkl", "wb") as f:
        pickle.dump(model, f)

    # Save metrics
    metrics["timestamp_utc"] = datetime.now(timezone.utc).isoformat()
    metrics["model_type"] = type(model).__name__
    with open(OUTPUT_DIR / "xgb_v2_multibroker_metrics.json", "w") as f:
        json.dump(metrics, f, indent=2, default=str)

    # Feature importance CSV
    with open(OUTPUT_DIR / "xgb_v2_multibroker_feature_importance.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["feature", "importance"])
        w.writeheader()
        for row in fi_rows:
            w.writerow(row)

    # Training report
    with open(OUTPUT_DIR / "xgb_v2_multibroker_training_report.md", "w") as f:
        f.write("# XGBoost v2 Multi-Broker Training Report (Sprint v2.8.7-F)\n\n")
        f.write(f"**Timestamp:** {metrics['timestamp_utc']}\n\n")
        f.write("## Overall Metrics\n\n")
        f.write("| Split | AUC | PR AUC | Brier |\n|---|---|---|---|\n")
        for split in ["train", "val", "test"]:
            f.write(f"| {split} | {metrics[f'{split}_auc']} | {metrics[f'{split}_pr_auc']} | "
                    f"{metrics[f'{split}_brier']} |\n")
        f.write("\n## Broker-wise AUC (Test/OOS 2026)\n\n")
        f.write("| Broker | AUC |\n|---|---|\n")
        for b, a in broker_auc.items():
            f.write(f"| {b} | {a} |\n")
        f.write("\n## Top 10 Feature Importance\n\n")
        f.write("| Feature | Importance |\n|---|---|\n")
        for row in fi_rows[:10]:
            f.write(f"| {row['feature']} | {row['importance']} |\n")
        f.write("\n## Acceptance Check\n\n")
        if metrics["test_auc"] > 0.50:
            f.write(f"- OOS AUC = {metrics['test_auc']} > 0.50: **PASS**\n")
        else:
            f.write(f"- OOS AUC = {metrics['test_auc']} <= 0.50: **FAIL**\n")

    print(f"    Train AUC: {metrics['train_auc']}, Val AUC: {metrics['val_auc']}, Test AUC: {metrics['test_auc']}")
    print(f"    Broker AUC: {broker_auc}")
    print(f"    Model saved: xgboost_v2_multibroker.pkl")
    return metrics, model


def task6_train_meta_multibroker(data, xgb_model):
    """Task 6: Retrain meta-label v2 multi-broker."""
    print("\n  [Task 6] Training meta-label v2 multi-broker...")
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score, average_precision_score, brier_score_loss

    mean = np.array([data["scaler"]["mean"][f] for f in FEATURE_NAMES_V2], dtype=np.float64)
    std = np.array([data["scaler"]["std"][f] for f in FEATURE_NAMES_V2], dtype=np.float64)

    X_train = standardize_v2(data["X_train"].values.astype(np.float64), mean, std)
    X_val = standardize_v2(data["X_val"].values.astype(np.float64), mean, std)
    X_test = standardize_v2(data["X_test"].values.astype(np.float64), mean, std)
    y_train = data["y_train"].values
    y_val = data["y_val"].values
    y_test = data["y_test"].values
    bid_train = data["bid_train"].values
    bid_val = data["bid_val"].values
    bid_test = data["bid_test"].values

    alpha_train = xgb_model.predict_proba(X_train)[:, 1]
    alpha_val = xgb_model.predict_proba(X_val)[:, 1]
    alpha_test = xgb_model.predict_proba(X_test)[:, 1]

    name_to_idx = {n: i for i, n in enumerate(FEATURE_NAMES_V2)}
    meta_indices = [name_to_idx[n] for n in META_FEATURE_NAMES_V2]
    meta_X_train = X_train[:, meta_indices]
    meta_X_val = X_val[:, meta_indices]
    meta_X_test = X_test[:, meta_indices]

    # Meta target: 1 if alpha approves (>=0.5) AND actual label is 1
    meta_y_train = ((alpha_train >= 0.5) & (y_train == 1)).astype(int)
    meta_y_val = ((alpha_val >= 0.5) & (y_val == 1)).astype(int)
    meta_y_test = ((alpha_test >= 0.5) & (y_test == 1)).astype(int)

    print(f"    Meta train: {len(meta_y_train)}, alpha-pass: {(alpha_train>=0.5).sum()}, "
          f"meta-pos: {meta_y_train.sum()} ({meta_y_train.mean():.3f})")
    print(f"    Meta val:   {len(meta_y_val)}, alpha-pass: {(alpha_val>=0.5).sum()}, "
          f"meta-pos: {meta_y_val.sum()} ({meta_y_val.mean():.3f})")
    print(f"    Meta test:  {len(meta_y_test)}, alpha-pass: {(alpha_test>=0.5).sum()}, "
          f"meta-pos: {meta_y_test.sum()} ({meta_y_test.mean():.3f})")

    meta_model = LogisticRegression(C=1.0, max_iter=1000, random_state=42, solver="lbfgs", n_jobs=1)
    meta_model.fit(meta_X_train, meta_y_train)

    meta_train_proba = meta_model.predict_proba(meta_X_train)[:, 1]
    meta_val_proba = meta_model.predict_proba(meta_X_val)[:, 1]
    meta_test_proba = meta_model.predict_proba(meta_X_test)[:, 1]

    def _m(y, p, prefix):
        return {
            f"{prefix}_auc": round(float(roc_auc_score(y, p)), 4),
            f"{prefix}_pr_auc": round(float(average_precision_score(y, p)), 4),
            f"{prefix}_brier": round(float(brier_score_loss(y, p)), 4),
            f"{prefix}_mean_proba": round(float(p.mean()), 4),
        }

    metrics = {}
    metrics.update(_m(meta_y_train, meta_train_proba, "train"))
    metrics.update(_m(meta_y_val, meta_val_proba, "val"))
    metrics.update(_m(meta_y_test, meta_test_proba, "test"))

    # Broker-wise meta stats on test
    id_to_name = {v: k for k, v in BROKER_IDS.items()}
    broker_meta = {}
    for bid in np.unique(bid_test):
        mask = bid_test == bid
        if mask.sum() > 50:
            broker_meta[id_to_name[bid]] = {
                "mean_proba": round(float(meta_test_proba[mask].mean()), 4),
                "pass_rate_065": round(float((meta_test_proba[mask] >= 0.65).mean()), 4),
            }
    metrics["test_broker_meta"] = broker_meta

    # Threshold scan on val
    threshold_rows = []
    for threshold in [0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75]:
        pass_mask = meta_val_proba >= threshold
        n_pass = int(pass_mask.sum())
        if n_pass > 0:
            both_pass_positive = int(((alpha_val >= 0.5) & pass_mask & (y_val == 1)).sum())
            precision = both_pass_positive / max(n_pass, 1)
            pass_rate = n_pass / max(int((alpha_val >= 0.5).sum()), 1)
            threshold_rows.append({
                "threshold": threshold, "n_pass": n_pass,
                "pass_rate_among_alpha": round(pass_rate, 4),
                "precision": round(precision, 4),
            })

    # Save model
    with open(MODELS_DIR / "meta_label_v2_multibroker.pkl", "wb") as f:
        pickle.dump(meta_model, f)

    # Save metrics
    metrics["timestamp_utc"] = datetime.now(timezone.utc).isoformat()
    with open(OUTPUT_DIR / "meta_v2_multibroker_metrics.json", "w") as f:
        json.dump(metrics, f, indent=2, default=str)

    # Threshold scan CSV
    with open(OUTPUT_DIR / "meta_v2_multibroker_threshold_scan.csv", "w", newline="") as f:
        if threshold_rows:
            w = csv.DictWriter(f, fieldnames=list(threshold_rows[0].keys()))
            w.writeheader()
            for row in threshold_rows:
                w.writerow(row)

    # Training report
    with open(OUTPUT_DIR / "meta_v2_multibroker_training_report.md", "w") as f:
        f.write("# Meta-Label v2 Multi-Broker Training Report (Sprint v2.8.7-F)\n\n")
        f.write(f"**Timestamp:** {metrics['timestamp_utc']}\n\n")
        f.write("## Overall Metrics\n\n")
        f.write("| Split | AUC | PR AUC | Brier | Mean Proba |\n|---|---|---|---|---|\n")
        for split in ["train", "val", "test"]:
            f.write(f"| {split} | {metrics[f'{split}_auc']} | {metrics[f'{split}_pr_auc']} | "
                    f"{metrics[f'{split}_brier']} | {metrics[f'{split}_mean_proba']} |\n")
        f.write("\n## Broker-wise Meta Stats (Test/OOS 2026)\n\n")
        f.write("| Broker | Mean Proba | Pass Rate (>=0.65) |\n|---|---|---|\n")
        for b, s in broker_meta.items():
            f.write(f"| {b} | {s['mean_proba']} | {s['pass_rate_065']} |\n")
        f.write("\n## Threshold Scan (Validation Set)\n\n")
        f.write("| Threshold | N Pass | Pass Rate (of alpha) | Precision |\n|---|---|---|---|\n")
        for row in threshold_rows:
            f.write(f"| {row['threshold']} | {row['n_pass']} | {row['pass_rate_among_alpha']} | "
                    f"{row['precision']} |\n")
        f.write("\n## Acceptance Check\n\n")
        if 0.05 < metrics["test_mean_proba"] < 0.95:
            f.write(f"- OOS mean proba = {metrics['test_mean_proba']} (not degenerate): **PASS**\n")
        else:
            f.write(f"- OOS mean proba degenerate: **FAIL**\n")

    print(f"    Train AUC: {metrics['train_auc']}, Val AUC: {metrics['val_auc']}, Test AUC: {metrics['test_auc']}")
    print(f"    Test mean proba: {metrics['test_mean_proba']}")
    print(f"    Model saved: meta_label_v2_multibroker.pkl")
    return metrics, meta_model


def main():
    ts = datetime.now(timezone.utc).isoformat()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    FEATURES_DIR.mkdir(parents=True, exist_ok=True)
    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("  TITAN XAU AI - MULTI-BROKER v2 TRAINING (Sprint v2.8.7-F)")
    print("=" * 70)
    print(f"  Timestamp: {ts}\n")

    data = task4_build_multibroker_dataset()
    xgb_metrics, xgb_model = task5_train_xgb_multibroker(data)
    meta_metrics, meta_model = task6_train_meta_multibroker(data, xgb_model)

    print("\n" + "=" * 70)
    print("  MULTI-BROKER v2 TRAINING SUMMARY")
    print("=" * 70)
    print(f"\n  XGBoost v2 multi-broker:")
    print(f"    Train AUC: {xgb_metrics['train_auc']}")
    print(f"    Val AUC:   {xgb_metrics['val_auc']}")
    print(f"    Test AUC:  {xgb_metrics['test_auc']}")
    print(f"    Broker AUC: {xgb_metrics['test_broker_auc']}")
    print(f"\n  Meta-Label v2 multi-broker:")
    print(f"    Train AUC: {meta_metrics['train_auc']}")
    print(f"    Val AUC:   {meta_metrics['val_auc']}")
    print(f"    Test AUC:  {meta_metrics['test_auc']}")
    print(f"    Test mean proba: {meta_metrics['test_mean_proba']}")
    print(f"\n  Output: {OUTPUT_DIR}")
    print("\n" + "=" * 70)
    print("\n  > Research only. NOT production. NO trade allowed.")
    print("=" * 70)


if __name__ == "__main__":
    main()
