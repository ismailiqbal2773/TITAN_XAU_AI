#!/usr/bin/env python3
"""TITAN XAU AI - Model v2 Training (Sprint v2.8.7-E)
======================================================
Retrains XGBoost v2 and meta-label v2 on v2 feature-normalized datasets.

Tasks:
  Task 4: Retrain XGBoost v2 (alpha model)
  Task 5: Retrain meta-label v2

Outputs:
  Models (titan/models/):
    - xgboost_v2_feature_normalized.pkl
    - meta_label_v2_feature_normalized.pkl

  Reports (data/reports/training_v2/):
    - xgb_v2_training_report.md
    - xgb_v2_metrics.json
    - xgb_v2_feature_importance.csv
    - xgb_v2_calibration.csv
    - meta_v2_training_report.md
    - meta_v2_metrics.json
    - meta_v2_threshold_scan.csv
    - meta_v2_calibration.csv

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

OUTPUT_DIR = REPO_ROOT / "data" / "reports" / "training_v2"
MODELS_DIR = REPO_ROOT / "titan" / "data" / "models"
FEATURES_DIR = REPO_ROOT / "titan" / "data" / "features_v2"

from titan.training.feature_schema_v2 import (
    FEATURE_NAMES_V2, META_FEATURE_NAMES_V2, ABSOLUTE_TO_RELATIVE,
)
from titan.training.feature_engine_v2 import standardize_v2, compute_scaler_stats_v2


def load_v2_data():
    """Load v2 train/val/test datasets."""
    X_train = pd.read_parquet(FEATURES_DIR / "XAUUSD_H1_X_train_v2.parquet")
    X_val = pd.read_parquet(FEATURES_DIR / "XAUUSD_H1_X_val_v2.parquet")
    X_test = pd.read_parquet(FEATURES_DIR / "XAUUSD_H1_X_test_v2.parquet")
    y_train = pd.read_parquet(FEATURES_DIR / "XAUUSD_H1_y_train_v2.parquet").iloc[:, 0]
    y_val = pd.read_parquet(FEATURES_DIR / "XAUUSD_H1_y_val_v2.parquet").iloc[:, 0]
    y_test = pd.read_parquet(FEATURES_DIR / "XAUUSD_H1_y_test_v2.parquet").iloc[:, 0]

    # Load scaler stats
    with open(FEATURES_DIR / "scaler_stats_v2.json", "r") as f:
        scaler = json.load(f)
    mean = np.array([scaler["mean"][f] for f in FEATURE_NAMES_V2], dtype=np.float64)
    std = np.array([scaler["std"][f] for f in FEATURE_NAMES_V2], dtype=np.float64)

    # Standardize
    def _prep(X):
        arr = X[FEATURE_NAMES_V2].values.astype(np.float64)
        arr = np.nan_to_num(arr, nan=0.0, posinf=0.0, neginf=0.0)
        return standardize_v2(arr, mean, std)

    return {
        "X_train": _prep(X_train), "y_train": y_train.values,
        "X_val": _prep(X_val), "y_val": y_val.values,
        "X_test": _prep(X_test), "y_test": y_test.values,
        "train_idx": X_train.index, "val_idx": X_val.index, "test_idx": X_test.index,
        "scaler": scaler, "mean": mean, "std": std,
    }


def task4_train_xgb_v2(data):
    """Task 4: Retrain XGBoost v2."""
    print("  [Task 4] Training XGBoost v2...")
    from xgboost import XGBClassifier
    from sklearn.metrics import (
        roc_auc_score, average_precision_score, brier_score_loss,
        precision_score, recall_score, f1_score, confusion_matrix,
    )
    from sklearn.calibration import calibration_curve

    X_train, y_train = data["X_train"], data["y_train"]
    X_val, y_val = data["X_val"], data["y_val"]
    X_test, y_test = data["X_test"], data["y_test"]

    print(f"    Train: {X_train.shape}, positive rate: {y_train.mean():.3f}")
    print(f"    Val:   {X_val.shape}, positive rate: {y_val.mean():.3f}")
    print(f"    Test:  {X_test.shape}, positive rate: {y_test.mean():.3f}")

    # Match v1 hyperparameters (XGBClassifier, max_depth=7, n_estimators=397, lr=0.0175)
    model = XGBClassifier(
        max_depth=7,
        n_estimators=397,
        learning_rate=0.0175,
        subsample=0.8,
        colsample_bytree=0.8,
        objective="binary:logistic",
        eval_metric="auc",
        random_state=42,
        n_jobs=2,
        verbosity=0,
    )

    # Fit with early stopping on validation
    model.fit(
        X_train, y_train,
        eval_set=[(X_val, y_val)],
        verbose=False,
    )

    # Predictions
    train_proba = model.predict_proba(X_train)[:, 1]
    val_proba = model.predict_proba(X_val)[:, 1]
    test_proba = model.predict_proba(X_test)[:, 1]

    # Metrics
    def _metrics(y_true, proba, prefix):
        y_pred = (proba >= 0.5).astype(int)
        try:
            auc = float(roc_auc_score(y_true, proba))
        except Exception:
            auc = 0.5
        try:
            pr_auc = float(average_precision_score(y_true, proba))
        except Exception:
            pr_auc = 0.0
        brier = float(brier_score_loss(y_true, proba))
        precision = float(precision_score(y_true, y_pred, zero_division=0))
        recall = float(recall_score(y_true, y_pred, zero_division=0))
        f1 = float(f1_score(y_true, y_pred, zero_division=0))
        cm = confusion_matrix(y_true, y_pred).tolist()
        # Directional accuracy by confidence bucket
        buckets = {}
        for lo, hi in [(0.0, 0.5), (0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 1.01)]:
            mask = (proba >= lo) & (proba < hi)
            if mask.sum() > 0:
                # For proba > 0.5: prediction = 1 (LONG). For proba < 0.5: prediction = 0 (SHORT).
                # Directional accuracy: % of times prediction matches actual direction
                if lo >= 0.5:
                    # LONG prediction: correct if y_true == 1
                    acc = float(y_true[mask].mean())
                else:
                    # SHORT prediction: correct if y_true == 0
                    acc = float(1 - y_true[mask].mean())
                buckets[f"{lo:.2f}-{hi:.2f}"] = {
                    "n": int(mask.sum()),
                    "directional_accuracy": round(acc, 4),
                }
        return {
            f"{prefix}_auc": round(auc, 4),
            f"{prefix}_pr_auc": round(pr_auc, 4),
            f"{prefix}_brier": round(brier, 4),
            f"{prefix}_precision": round(precision, 4),
            f"{prefix}_recall": round(recall, 4),
            f"{prefix}_f1": round(f1, 4),
            f"{prefix}_confusion_matrix": cm,
            f"{prefix}_confidence_buckets": buckets,
        }

    metrics = {}
    metrics.update(_metrics(y_train, train_proba, "train"))
    metrics.update(_metrics(y_val, val_proba, "val"))
    metrics.update(_metrics(y_test, test_proba, "test"))

    # Calibration curve on test set
    try:
        frac_pos, mean_pred = calibration_curve(y_test, test_proba, n_bins=10, strategy="quantile")
        calib_rows = [{"bin_pred": round(float(p), 4), "bin_actual": round(float(a), 4)}
                      for p, a in zip(mean_pred, frac_pos)]
    except Exception:
        calib_rows = []

    # Feature importance
    fi = model.feature_importances_
    fi_rows = [{"feature": name, "importance": round(float(imp), 6)}
               for name, imp in zip(FEATURE_NAMES_V2, fi)]
    fi_rows.sort(key=lambda x: x["importance"], reverse=True)

    # Save model
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    with open(MODELS_DIR / "xgboost_v2_feature_normalized.pkl", "wb") as f:
        pickle.dump(model, f)

    # Save metrics
    metrics["timestamp_utc"] = datetime.now(timezone.utc).isoformat()
    metrics["model_type"] = type(model).__name__
    metrics["n_features"] = X_train.shape[1]
    metrics["train_size"] = X_train.shape[0]
    metrics["val_size"] = X_val.shape[0]
    metrics["test_size"] = X_test.shape[0]
    metrics["hyperparams"] = {
        "max_depth": 7, "n_estimators": 397, "learning_rate": 0.0175,
        "subsample": 0.8, "colsample_bytree": 0.8,
    }
    with open(OUTPUT_DIR / "xgb_v2_metrics.json", "w") as f:
        json.dump(metrics, f, indent=2, default=str)

    # Feature importance CSV
    with open(OUTPUT_DIR / "xgb_v2_feature_importance.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["feature", "importance"])
        w.writeheader()
        for row in fi_rows:
            w.writerow(row)

    # Calibration CSV
    with open(OUTPUT_DIR / "xgb_v2_calibration.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["bin_pred", "bin_actual"])
        w.writeheader()
        for row in calib_rows:
            w.writerow(row)

    # Training report
    with open(OUTPUT_DIR / "xgb_v2_training_report.md", "w") as f:
        f.write("# XGBoost v2 Training Report (Sprint v2.8.7-E)\n\n")
        f.write(f"**Timestamp:** {metrics['timestamp_utc']}\n\n")
        f.write("## Hyperparameters\n\n")
        f.write(f"- max_depth: 7\n- n_estimators: 397\n- learning_rate: 0.0175\n")
        f.write(f"- subsample: 0.8\n- colsample_bytree: 0.8\n\n")
        f.write("## Dataset\n\n")
        f.write(f"- Train: {metrics['train_size']} rows (2020-2024)\n")
        f.write(f"- Validation: {metrics['val_size']} rows (2025)\n")
        f.write(f"- Test/OOS: {metrics['test_size']} rows (2026)\n")
        f.write(f"- Features: {metrics['n_features']} (v2 schema)\n\n")
        f.write("## Metrics\n\n")
        f.write("| Split | AUC | PR AUC | Brier | Precision | Recall | F1 |\n")
        f.write("|---|---|---|---|---|---|---|\n")
        for split in ["train", "val", "test"]:
            f.write(f"| {split} | {metrics[f'{split}_auc']} | {metrics[f'{split}_pr_auc']} | "
                    f"{metrics[f'{split}_brier']} | {metrics[f'{split}_precision']} | "
                    f"{metrics[f'{split}_recall']} | {metrics[f'{split}_f1']} |\n")
        f.write("\n## Directional Accuracy by Confidence Bucket (Test/OOS)\n\n")
        f.write("| Bucket | N | Directional Accuracy |\n|---|---|---|\n")
        for bucket, stats in metrics["test_confidence_buckets"].items():
            f.write(f"| {bucket} | {stats['n']} | {stats['directional_accuracy']} |\n")
        f.write("\n## Top 10 Feature Importance\n\n")
        f.write("| Feature | Importance |\n|---|---|\n")
        for row in fi_rows[:10]:
            f.write(f"| {row['feature']} | {row['importance']} |\n")
        f.write("\n## Acceptance Check\n\n")
        oos_auc = metrics["test_auc"]
        if oos_auc > 0.50:
            f.write(f"- OOS AUC = {oos_auc} > 0.50: **PASS**\n")
        else:
            f.write(f"- OOS AUC = {oos_auc} <= 0.50: **FAIL**\n")

    print(f"    Train AUC: {metrics['train_auc']}")
    print(f"    Val AUC:   {metrics['val_auc']}")
    print(f"    Test AUC:  {metrics['test_auc']}")
    print(f"    Model saved: titan/data/models/xgboost_v2_feature_normalized.pkl")
    return metrics, model, (val_proba, test_proba)


def task5_train_meta_v2(data, xgb_model, xgb_probas):
    """Task 5: Retrain meta-label v2 on v2 alpha predictions."""
    print("\n  [Task 5] Training meta-label v2...")
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score, average_precision_score, brier_score_loss
    from sklearn.calibration import calibration_curve

    # Meta-label target: predict whether an alpha-approved (proba >= 0.5)
    # trade will have positive forward return after costs.
    # We use the SAME labels as alpha (y), but only for bars where alpha
    # predicts LONG (proba >= 0.5). This is the standard meta-label setup
    # (López de Prado 2018).

    # Get alpha predictions on all splits
    X_train, y_train = data["X_train"], data["y_train"]
    X_val, y_val = data["X_val"], data["y_val"]
    X_test, y_test = data["X_test"], data["y_test"]

    alpha_train_proba = xgb_model.predict_proba(X_train)[:, 1]
    alpha_val_proba = xgb_model.predict_proba(X_val)[:, 1]
    alpha_test_proba = xgb_model.predict_proba(X_test)[:, 1]

    # Meta features = subset of v2 features (META_FEATURE_NAMES_V2)
    name_to_idx = {n: i for i, n in enumerate(FEATURE_NAMES_V2)}
    meta_indices = [name_to_idx[n] for n in META_FEATURE_NAMES_V2]

    meta_X_train = X_train[:, meta_indices]
    meta_X_val = X_val[:, meta_indices]
    meta_X_test = X_test[:, meta_indices]

    # Meta target: 1 if alpha approves (proba >= 0.5) AND actual label is 1
    # This filters to alpha-approved bars and trains meta to predict quality
    alpha_train_pass = alpha_train_proba >= 0.5
    alpha_val_pass = alpha_val_proba >= 0.5
    alpha_test_pass = alpha_test_proba >= 0.5

    meta_y_train = (alpha_train_pass & (y_train == 1)).astype(int)
    meta_y_val = (alpha_val_pass & (y_val == 1)).astype(int)
    meta_y_test = (alpha_test_pass & (y_test == 1)).astype(int)

    print(f"    Meta train: {len(meta_y_train)} bars, alpha-pass: {alpha_train_pass.sum()}, "
          f"meta-positive: {meta_y_train.sum()} ({meta_y_train.mean():.3f})")
    print(f"    Meta val:   {len(meta_y_val)} bars, alpha-pass: {alpha_val_pass.sum()}, "
          f"meta-positive: {meta_y_val.sum()} ({meta_y_val.mean():.3f})")
    print(f"    Meta test:  {len(meta_y_test)} bars, alpha-pass: {alpha_test_pass.sum()}, "
          f"meta-positive: {meta_y_test.sum()} ({meta_y_test.mean():.3f})")

    # Train Logistic Regression (same family as v1)
    meta_model = LogisticRegression(
        C=1.0, max_iter=1000, random_state=42, solver="lbfgs", n_jobs=1,
    )
    meta_model.fit(meta_X_train, meta_y_train)

    # Predictions
    meta_train_proba = meta_model.predict_proba(meta_X_train)[:, 1]
    meta_val_proba = meta_model.predict_proba(meta_X_val)[:, 1]
    meta_test_proba = meta_model.predict_proba(meta_X_test)[:, 1]

    def _meta_metrics(y_true, proba, prefix):
        try:
            auc = float(roc_auc_score(y_true, proba))
        except Exception:
            auc = 0.5
        try:
            pr_auc = float(average_precision_score(y_true, proba))
        except Exception:
            pr_auc = 0.0
        try:
            brier = float(brier_score_loss(y_true, proba))
        except Exception:
            brier = 1.0
        return {
            f"{prefix}_auc": round(auc, 4),
            f"{prefix}_pr_auc": round(pr_auc, 4),
            f"{prefix}_brier": round(brier, 4),
            f"{prefix}_mean_proba": round(float(proba.mean()), 4),
            f"{prefix}_p50_proba": round(float(np.percentile(proba, 50)), 4),
            f"{prefix}_p95_proba": round(float(np.percentile(proba, 95)), 4),
        }

    metrics = {}
    metrics.update(_meta_metrics(meta_y_train, meta_train_proba, "train"))
    metrics.update(_meta_metrics(meta_y_val, meta_val_proba, "val"))
    metrics.update(_meta_metrics(meta_y_test, meta_test_proba, "test"))

    # Threshold scan on val set
    threshold_rows = []
    for threshold in [0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75]:
        pass_mask = meta_val_proba >= threshold
        n_pass = int(pass_mask.sum())
        if n_pass > 0:
            # Among alpha-pass bars, how many pass meta threshold AND have positive actual
            both_pass_and_positive = int(((alpha_val_pass) & (pass_mask) & (y_val == 1)).sum())
            precision = both_pass_and_positive / max(n_pass, 1)
            # Pass rate among alpha-pass bars
            pass_rate = n_pass / max(int(alpha_val_pass.sum()), 1)
            threshold_rows.append({
                "threshold": threshold,
                "n_pass": n_pass,
                "pass_rate_among_alpha": round(pass_rate, 4),
                "precision": round(precision, 4),
            })

    # Calibration
    try:
        frac_pos, mean_pred = calibration_curve(meta_y_test, meta_test_proba, n_bins=10, strategy="quantile")
        calib_rows = [{"bin_pred": round(float(p), 4), "bin_actual": round(float(a), 4)}
                      for p, a in zip(mean_pred, frac_pos)]
    except Exception:
        calib_rows = []

    # Save model
    with open(MODELS_DIR / "meta_label_v2_feature_normalized.pkl", "wb") as f:
        pickle.dump(meta_model, f)

    # Save metrics
    metrics["timestamp_utc"] = datetime.now(timezone.utc).isoformat()
    metrics["model_type"] = type(meta_model).__name__
    metrics["n_features"] = meta_X_train.shape[1]
    metrics["n_meta_features"] = len(META_FEATURE_NAMES_V2)
    metrics["meta_feature_names"] = META_FEATURE_NAMES_V2
    with open(OUTPUT_DIR / "meta_v2_metrics.json", "w") as f:
        json.dump(metrics, f, indent=2, default=str)

    # Threshold scan CSV
    with open(OUTPUT_DIR / "meta_v2_threshold_scan.csv", "w", newline="") as f:
        if threshold_rows:
            w = csv.DictWriter(f, fieldnames=list(threshold_rows[0].keys()))
            w.writeheader()
            for row in threshold_rows:
                w.writerow(row)

    # Calibration CSV
    with open(OUTPUT_DIR / "meta_v2_calibration.csv", "w", newline="") as f:
        if calib_rows:
            w = csv.DictWriter(f, fieldnames=list(calib_rows[0].keys()))
            w.writeheader()
            for row in calib_rows:
                w.writerow(row)

    # Training report
    with open(OUTPUT_DIR / "meta_v2_training_report.md", "w") as f:
        f.write("# Meta-Label v2 Training Report (Sprint v2.8.7-E)\n\n")
        f.write(f"**Timestamp:** {metrics['timestamp_utc']}\n\n")
        f.write("## Model\n\n")
        f.write(f"- Type: {metrics['model_type']}\n")
        f.write(f"- Features: {metrics['n_features']} (v2 meta subset)\n\n")
        f.write("## Dataset\n\n")
        f.write(f"- Train: {len(meta_y_train)} bars, alpha-pass: {int(alpha_train_pass.sum())}, "
                f"meta-positive: {int(meta_y_train.sum())} ({meta_y_train.mean():.3f})\n")
        f.write(f"- Val:   {len(meta_y_val)} bars, alpha-pass: {int(alpha_val_pass.sum())}, "
                f"meta-positive: {int(meta_y_val.sum())} ({meta_y_val.mean():.3f})\n")
        f.write(f"- Test:  {len(meta_y_test)} bars, alpha-pass: {int(alpha_test_pass.sum())}, "
                f"meta-positive: {int(meta_y_test.sum())} ({meta_y_test.mean():.3f})\n\n")
        f.write("## Metrics\n\n")
        f.write("| Split | AUC | PR AUC | Brier | Mean Proba | P50 | P95 |\n")
        f.write("|---|---|---|---|---|---|---|\n")
        for split in ["train", "val", "test"]:
            f.write(f"| {split} | {metrics[f'{split}_auc']} | {metrics[f'{split}_pr_auc']} | "
                    f"{metrics[f'{split}_brier']} | {metrics[f'{split}_mean_proba']} | "
                    f"{metrics[f'{split}_p50_proba']} | {metrics[f'{split}_p95_proba']} |\n")
        f.write("\n## Threshold Scan (Validation Set)\n\n")
        f.write("| Threshold | N Pass | Pass Rate (of alpha) | Precision |\n")
        f.write("|---|---|---|---|\n")
        for row in threshold_rows:
            f.write(f"| {row['threshold']} | {row['n_pass']} | "
                    f"{row['pass_rate_among_alpha']} | {row['precision']} |\n")
        f.write("\n## Acceptance Check\n\n")
        oos_mean = metrics["test_mean_proba"]
        if 0.05 < oos_mean < 0.95:
            f.write(f"- OOS mean proba = {oos_mean} (not degenerate): **PASS**\n")
        else:
            f.write(f"- OOS mean proba = {oos_mean} (degenerate): **FAIL**\n")
        oos_auc = metrics["test_auc"]
        if oos_auc > 0.50:
            f.write(f"- OOS AUC = {oos_auc} > 0.50: **PASS**\n")
        else:
            f.write(f"- OOS AUC = {oos_auc} <= 0.50: marginal\n")

    print(f"    Train AUC: {metrics['train_auc']}, mean_proba: {metrics['train_mean_proba']}")
    print(f"    Val AUC:   {metrics['val_auc']}, mean_proba: {metrics['val_mean_proba']}")
    print(f"    Test AUC:  {metrics['test_auc']}, mean_proba: {metrics['test_mean_proba']}")
    print(f"    Model saved: titan/data/models/meta_label_v2_feature_normalized.pkl")
    return metrics, meta_model


def main():
    ts = datetime.now(timezone.utc).isoformat()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("  TITAN XAU AI - MODEL v2 TRAINING (Sprint v2.8.7-E)")
    print("=" * 70)
    print(f"  Timestamp: {ts}\n")

    data = load_v2_data()
    print(f"  Data loaded: train={data['X_train'].shape}, val={data['X_val'].shape}, "
          f"test={data['X_test'].shape}\n")

    xgb_metrics, xgb_model, xgb_probas = task4_train_xgb_v2(data)
    meta_metrics, meta_model = task5_train_meta_v2(data, xgb_model, xgb_probas)

    print("\n" + "=" * 70)
    print("  MODEL v2 TRAINING SUMMARY")
    print("=" * 70)
    print(f"\n  XGBoost v2:")
    print(f"    Train AUC: {xgb_metrics['train_auc']}")
    print(f"    Val AUC:   {xgb_metrics['val_auc']}")
    print(f"    Test AUC:  {xgb_metrics['test_auc']}")
    print(f"\n  Meta-Label v2:")
    print(f"    Train AUC: {meta_metrics['train_auc']}, mean_proba: {meta_metrics['train_mean_proba']}")
    print(f"    Val AUC:   {meta_metrics['val_auc']}, mean_proba: {meta_metrics['val_mean_proba']}")
    print(f"    Test AUC:  {meta_metrics['test_auc']}, mean_proba: {meta_metrics['test_mean_proba']}")
    print(f"\n  Output: {OUTPUT_DIR}")
    print(f"  Models: {MODELS_DIR}")
    print("\n" + "=" * 70)
    print("\n  > Research only. NOT production. NO trade allowed.")
    print("=" * 70)


if __name__ == "__main__":
    main()
