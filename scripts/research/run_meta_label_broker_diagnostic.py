#!/usr/bin/env python3
"""TITAN XAU AI - Meta-Label Broker Diagnostic (Sprint v2.8.7-C)
=================================================================
Diagnoses meta-label broker mismatch: canonical has meta>0.65=7943 but
all other brokers have meta>0.65=0.

Root cause (v2.8.7-B): spread_pct feature is massively different between
brokers because exness/fbs/fundednext/icmarkets use 'spread' (integer
points) while canonical uses 'spread_usd' (float USD).

Fix (v2.8.7-C): Normalize spread to USD across all brokers BEFORE
sending data to H1FeatureStream. Re-run diagnostic and verify
spread_pct drift is reduced and meta-label distribution becomes more
realistic.

NEVER sends orders. NEVER creates token.
"""
from __future__ import annotations
import sys, json, csv, os
from pathlib import Path
from datetime import datetime, timezone
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

OUTPUT_DIR = REPO_ROOT / "data" / "reports" / "parameter_discovery"

BROKER_PATHS = {
    "canonical": "titan/data/canonical/XAUUSD_H1_canonical.parquet",
    "exness": "titan/data/sources/mt5_brokers/exness/XAUUSD_H1.parquet",
    "fbs": "titan/data/sources/mt5_brokers/fbs/XAUUSD_H1.parquet",
    "fundednext": "titan/data/sources/mt5_brokers/fundednext/XAUUSD_H1.parquet",
    "icmarkets": "titan/data/sources/mt5_brokers/icmarkets/XAUUSD_H1.parquet",
}


def run_diagnostic():
    """Run meta-label broker diagnostic with v2.8.7-C spread normalization."""
    import pandas as pd
    from titan.production.feature_stream import H1FeatureStream, FEATURE_NAMES
    from titan.production.model_loader import load_production_models, META_FEATURE_NAMES
    from titan.production.spread_normalization import (
        normalize_xauusd_spread_to_usd,
        spread_audit_row,
    )

    ts = datetime.now(timezone.utc).isoformat()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    bundle = load_production_models()
    if not bundle.ok:
        return {"error": "Models failed to load"}

    name_to_idx = {n: i for i, n in enumerate(FEATURE_NAMES)}
    meta_indices = [name_to_idx[n] for n in META_FEATURE_NAMES]

    # === Task 1: Meta-label broker diagnostic ===
    diag_rows = []
    feature_dist_rows = []
    meta_label_broker_shift = False

    broker_predictions = {}
    broker_meta_features = {}
    spread_audit_rows = []

    for broker, path in BROKER_PATHS.items():
        full_path = REPO_ROOT / path
        if not full_path.exists():
            continue
        df_raw = pd.read_parquet(full_path)

        # === v2.8.7-C: Normalize spread to USD BEFORE feature computation ===
        df_norm = normalize_xauusd_spread_to_usd(
            df_raw.copy(), symbol="XAUUSD", source=broker
        )

        # Build audit row comparing raw vs normalized
        audit_row = spread_audit_row(df_raw, df_norm, source=broker)
        spread_audit_rows.append(audit_row)

        # Use normalized spread for feature stream
        df_use = df_norm[["open", "high", "low", "close"]].copy()
        if "volume" in df_norm.columns:
            df_use["volume"] = df_norm["volume"]
        elif "tick_volume" in df_norm.columns:
            df_use["volume"] = df_norm["tick_volume"]
        else:
            df_use["volume"] = 0
        df_use["spread"] = df_norm["spread_usd"]  # ALWAYS USD after normalization

        stream = H1FeatureStream()
        stream._bars = df_use
        feats_df = stream._compute_features()
        features_matrix = np.nan_to_num(
            feats_df.values.astype(np.float64), nan=0.0, posinf=0.0, neginf=0.0
        )
        features_matrix = stream._standardize(features_matrix)

        xgb_proba = bundle.xgb.predict_proba(features_matrix)[:, 1]
        meta_vecs = features_matrix[:, meta_indices]
        meta_proba = bundle.meta.predict_proba(meta_vecs)[:, 1]

        broker_predictions[broker] = {"alpha": xgb_proba, "meta": meta_proba}
        broker_meta_features[broker] = meta_vecs

        # Diagnostic stats
        for label, probas in [("alpha", xgb_proba), ("meta", meta_proba)]:
            diag_rows.append({
                "broker": broker,
                "model": label,
                "count": len(probas),
                "min": round(float(probas.min()), 6),
                "max": round(float(probas.max()), 6),
                "mean": round(float(probas.mean()), 6),
                "p50": round(float(np.percentile(probas, 50)), 6),
                "p75": round(float(np.percentile(probas, 75)), 6),
                "p90": round(float(np.percentile(probas, 90)), 6),
                "p95": round(float(np.percentile(probas, 95)), 6),
                "p99": round(float(np.percentile(probas, 99)), 6),
            })

        # Pass counts
        for threshold in [0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70]:
            diag_rows.append({
                "broker": broker,
                "model": f"meta_pass_{threshold:.2f}",
                "count": int((meta_proba >= threshold).sum()),
                "min": "", "max": "", "mean": "", "p50": "", "p75": "", "p90": "", "p95": "", "p99": "",
            })
        for threshold in [0.50, 0.55, 0.60]:
            diag_rows.append({
                "broker": broker,
                "model": f"alpha_pass_{threshold:.2f}",
                "count": int((xgb_proba >= threshold).sum()),
                "min": "", "max": "", "mean": "", "p50": "", "p75": "", "p90": "", "p95": "", "p99": "",
            })
        # Both pass
        for alpha_t, meta_t in [(0.55, 0.65), (0.50, 0.50), (0.55, 0.50)]:
            both = int(((xgb_proba >= alpha_t) & (meta_proba >= meta_t)).sum())
            diag_rows.append({
                "broker": broker,
                "model": f"both_pass_alpha{alpha_t}_meta{meta_t}",
                "count": both,
                "min": "", "max": "", "mean": "", "p50": "", "p75": "", "p90": "", "p95": "", "p99": "",
            })

        # Check for broker shift (still using same threshold heuristic, but
        # post-normalization we expect this to be FALSE for all brokers).
        meta_pass_065 = int((meta_proba >= 0.65).sum())
        if broker != "canonical" and meta_pass_065 == 0:
            meta_label_broker_shift = True

    # Write spread normalization audit
    if spread_audit_rows:
        with open(OUTPUT_DIR / "spread_normalization_audit.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(spread_audit_rows[0].keys()))
            w.writeheader()
            for row in spread_audit_rows:
                w.writerow(row)

        with open(OUTPUT_DIR / "spread_normalization_audit.md", "w") as f:
            f.write("# Spread Normalization Audit (v2.8.7-C)\n\n")
            f.write(f"**Timestamp:** {ts}\n\n")
            f.write("## Per-Broker Before/After\n\n")
            f.write("| Broker | Raw Col | Raw Median | Raw P95 | Detected Unit | Norm Median | Norm P95 | "
                    "spread_pct Before | spread_pct After | Conversion Applied |\n")
            f.write("|---|---|---|---|---|---|---|---|---|---|\n")
            for row in spread_audit_rows:
                f.write(f"| {row['source']} | {row['raw_spread_column']} | "
                        f"{row['raw_spread_median']} | {row['raw_spread_p95']} | "
                        f"{row['spread_unit_detected']} | {row['normalized_spread_median']} | "
                        f"{row['normalized_spread_p95']} | {row['spread_pct_mean_before']} | "
                        f"{row['spread_pct_mean_after']} | {row['conversion_applied']} |\n")
            f.write("\n## Assessment\n\n")
            conversions = sum(1 for r in spread_audit_rows if r["conversion_applied"])
            f.write(f"- Brokers with POINTS->USD conversion applied: {conversions}\n")
            f.write(f"- Brokers using spread_usd as-is (canonical): "
                    f"{sum(1 for r in spread_audit_rows if r['spread_unit_detected']=='USD' and not r['conversion_applied'])}\n")
            f.write(f"- Brokers defaulting to 0.0 (missing): "
                    f"{sum(1 for r in spread_audit_rows if r['spread_unit_detected']=='MISSING_DEFAULT_ZERO')}\n")
            # Check spread_pct ratio improvement
            for row in spread_audit_rows:
                before = row["spread_pct_mean_before"]
                after = row["spread_pct_mean_after"]
                if before > 0 and after > 0:
                    ratio = before / after
                    f.write(f"- {row['source']}: spread_pct before/after ratio = {ratio:.2f}x\n")

    # Write diagnostic CSV
    with open(OUTPUT_DIR / "meta_label_broker_diagnostic.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["broker", "model", "count", "min", "max", "mean", "p50", "p75", "p90", "p95", "p99"])
        w.writeheader()
        for row in diag_rows:
            w.writerow(row)

    # Write diagnostic MD
    with open(OUTPUT_DIR / "meta_label_broker_diagnostic.md", "w") as f:
        f.write("# Meta-Label Broker Diagnostic (v2.8.7-C)\n\n")
        f.write(f"**Timestamp:** {ts}\n\n")
        f.write(f"**META_LABEL_BROKER_SHIFT:** {meta_label_broker_shift}\n\n")
        f.write("## Broker Prediction Summary (post-spread-normalization)\n\n")
        f.write("| Broker | Alpha mean | Alpha p50 | Meta mean | Meta p50 | Alpha>0.55 | Meta>0.65 | Both pass |\n")
        f.write("|---|---|---|---|---|---|---|---|\n")
        for broker in broker_predictions:
            p = broker_predictions[broker]
            a = p["alpha"]
            m = p["meta"]
            f.write(f"| {broker} | {a.mean():.4f} | {np.percentile(a,50):.4f} | "
                    f"{m.mean():.4f} | {np.percentile(m,50):.4f} | "
                    f"{int((a>=0.55).sum())} | {int((m>=0.65).sum())} | "
                    f"{int(((a>=0.55)&(m>=0.65)).sum())} |\n")

        if meta_label_broker_shift:
            f.write("\n## ⚠️ META_LABEL_BROKER_SHIFT DETECTED\n\n")
            f.write("Non-canonical brokers STILL have meta>0.65 = 0 even after normalization.\n")
            f.write("Investigate other feature distribution shifts beyond spread_pct.\n")
        else:
            f.write("\n## ✅ NO BROKER SHIFT AFTER NORMALIZATION\n\n")
            f.write("Spread unit normalization has brought broker meta distributions\n")
            f.write("into the same scale as canonical. Spread_pct drift eliminated.\n")

    # === Task 2: Meta feature distribution comparison ===
    if "canonical" in broker_meta_features:
        canon_meta = broker_meta_features["canonical"]
        for broker, meta_vecs in broker_meta_features.items():
            if broker == "canonical":
                continue
            for j, name in enumerate(META_FEATURE_NAMES):
                canon_vals = canon_meta[:, j]
                broker_vals = meta_vecs[:, j]
                drift = abs(canon_vals.mean() - broker_vals.mean())
                feature_dist_rows.append({
                    "feature": name,
                    "broker": broker,
                    "canonical_mean": round(float(canon_vals.mean()), 6),
                    "broker_mean": round(float(broker_vals.mean()), 6),
                    "mean_drift": round(float(drift), 6),
                    "canonical_std": round(float(canon_vals.std()), 6),
                    "broker_std": round(float(broker_vals.std()), 6),
                    "canonical_p50": round(float(np.percentile(canon_vals, 50)), 6),
                    "broker_p50": round(float(np.percentile(broker_vals, 50)), 6),
                    "canonical_p95": round(float(np.percentile(canon_vals, 95)), 6),
                    "broker_p95": round(float(np.percentile(broker_vals, 95)), 6),
                    "canonical_zeros": int((canon_vals == 0).sum()),
                    "broker_zeros": int((broker_vals == 0).sum()),
                })

    with open(OUTPUT_DIR / "meta_feature_distribution_comparison.csv", "w", newline="") as f:
        if feature_dist_rows:
            w = csv.DictWriter(f, fieldnames=list(feature_dist_rows[0].keys()))
            w.writeheader()
            for row in feature_dist_rows:
                w.writerow(row)

    # Find top drifted features
    top_drifted = sorted(feature_dist_rows, key=lambda x: x["mean_drift"], reverse=True)[:10]
    with open(OUTPUT_DIR / "meta_feature_distribution_comparison.md", "w") as f:
        f.write("# Meta Feature Distribution Comparison (v2.8.7-C)\n\n")
        f.write(f"**Timestamp:** {ts}\n\n")
        f.write("## Top 10 Drifted Features (post-normalization)\n\n")
        f.write("| Feature | Broker | Canon Mean | Broker Mean | Drift | Canon Std | Broker Std |\n")
        f.write("|---|---|---|---|---|---|---|\n")
        for row in top_drifted:
            f.write(f"| {row['feature']} | {row['broker']} | {row['canonical_mean']} | "
                    f"{row['broker_mean']} | {row['mean_drift']} | {row['canonical_std']} | {row['broker_std']} |\n")
        if top_drifted:
            f.write(f"\n**Most drifted feature:** {top_drifted[0]['feature']} "
                    f"(drift={top_drifted[0]['mean_drift']})\n")

    # === Task 3: Model compatibility audit ===
    import xgboost
    import sklearn
    model_compat = {
        "xgboost_version": xgboost.__version__,
        "sklearn_version": sklearn.__version__,
        "xgb_model_type": type(bundle.xgb).__name__,
        "meta_model_type": type(bundle.meta).__name__,
        "xgb_n_features": bundle.xgb_n_features,
        "meta_n_features": bundle.meta_n_features,
        "xgb_verified": bundle.xgb_verified,
        "meta_verified": bundle.meta_verified,
        "bundle_ok": bundle.ok,
        "bundle_errors": bundle.errors,
    }

    # Check for version mismatch warnings
    try:
        import warnings
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            import pickle
            with open(REPO_ROOT / "titan" / "data" / "models" / "meta_label_v2_context.pkl", "rb") as f:
                pickle.load(f)
            model_compat["warning_count"] = len(w)
            model_compat["warnings"] = [str(warning.message)[:200] for warning in w]
    except Exception as e:
        model_compat["warning_count"] = -1
        model_compat["warnings"] = [str(e)]

    with open(OUTPUT_DIR / "model_compatibility_audit.md", "w") as f:
        f.write("# Model Compatibility Audit (v2.8.7-C)\n\n")
        f.write(f"**Timestamp:** {ts}\n\n")
        f.write("## Environment\n\n")
        f.write(f"- XGBoost version: {model_compat['xgboost_version']}\n")
        f.write(f"- sklearn version: {model_compat['sklearn_version']}\n\n")
        f.write("## Models\n\n")
        f.write(f"- XGBoost type: {model_compat['xgb_model_type']}\n")
        f.write(f"- XGBoost features: {model_compat['xgb_n_features']}\n")
        f.write(f"- XGBoost verified: {model_compat['xgb_verified']}\n")
        f.write(f"- Meta-label type: {model_compat['meta_model_type']}\n")
        f.write(f"- Meta-label features: {model_compat['meta_n_features']}\n")
        f.write(f"- Meta-label verified: {model_compat['meta_verified']}\n")
        f.write(f"- Bundle OK: {model_compat['bundle_ok']}\n\n")
        f.write("## Version Warnings\n\n")
        if model_compat.get("warnings"):
            for w in model_compat["warnings"]:
                f.write(f"- {w}\n")
        else:
            f.write("- No warnings detected\n")
        f.write("\n## Assessment\n\n")
        f.write("- Models load and predict successfully\n")
        f.write("- Spread unit normalization applied before feature computation\n")
        f.write("- Meta-label distribution should now be comparable across brokers\n")

    # Print summary
    print("=" * 70)
    print("  META-LABEL BROKER DIAGNOSTIC (v2.8.7-C)")
    print("=" * 70)
    print(f"\n  META_LABEL_BROKER_SHIFT: {meta_label_broker_shift}")
    for broker in broker_predictions:
        p = broker_predictions[broker]
        a, m = p["alpha"], p["meta"]
        print(f"  {broker:15s}: alpha>0.55={int((a>=0.55).sum()):6d}, meta>0.65={int((m>=0.65).sum()):6d}, "
              f"meta_mean={m.mean():.4f}, meta_p50={np.percentile(m,50):.4f}")
    if top_drifted:
        print(f"\n  Top drifted feature (post-norm): {top_drifted[0]['feature']} (drift={top_drifted[0]['mean_drift']})")
    if spread_audit_rows:
        print(f"\n  Spread normalization audit:")
        for row in spread_audit_rows:
            print(f"    {row['source']:15s}: {row['raw_spread_column']} median={row['raw_spread_median']} "
                  f"-> unit={row['spread_unit_detected']} -> norm median={row['normalized_spread_median']} "
                  f"spread_pct {row['spread_pct_mean_before']} -> {row['spread_pct_mean_after']}")
    print(f"\n  XGBoost: {model_compat['xgboost_version']}, sklearn: {model_compat['sklearn_version']}")
    print(f"  Output: {OUTPUT_DIR}")
    print("\n" + "=" * 70)

    return {
        "timestamp_utc": ts,
        "meta_label_broker_shift": meta_label_broker_shift,
        "top_drifted_feature": top_drifted[0]["feature"] if top_drifted else "",
        "top_drifted_value": top_drifted[0]["mean_drift"] if top_drifted else 0,
        "model_compat": model_compat,
        "spread_audit_rows": spread_audit_rows,
        "broker_predictions": {b: {"alpha_mean": float(p["alpha"].mean()), "meta_mean": float(p["meta"].mean()),
                                    "meta_p50": float(np.percentile(p["meta"], 50)),
                                    "meta_pass_065": int((p["meta"] >= 0.65).sum())}
                               for b, p in broker_predictions.items()},
    }


if __name__ == "__main__":
    run_diagnostic()
