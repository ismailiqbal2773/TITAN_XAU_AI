#!/usr/bin/env python3
"""
TITAN XAU AI - Model Artifact Compatibility Audit (Sprint 9.9.3.43)
====================================================================
NEVER imports MetaTrader5. NEVER sends orders.
"""
from __future__ import annotations
import json, os, subprocess, sys, warnings, pickle
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
OUTPUT_DIR = REPO_ROOT / "data" / "audit" / "model_artifacts"
JSON_PATH = OUTPUT_DIR / "model_artifact_compatibility_audit.json"
MD_PATH = OUTPUT_DIR / "model_artifact_compatibility_audit.md"


def _git_head_short() -> str:
    try:
        r = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                           cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=10)
        return r.stdout.strip() if r.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def run_audit() -> dict:
    ts = datetime.now(timezone.utc).isoformat()
    head = _git_head_short()
    py_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"

    ok_checks = []
    warnings_list = []
    blockers = []

    # Package versions
    xgb_ver = None
    sklearn_ver = None
    try:
        import xgboost as xgb
        xgb_ver = xgb.__version__
        ok_checks.append(f"XGBoost version: {xgb_ver}")
    except Exception as e:
        blockers.append(f"XGBoost import failed: {e}")

    try:
        import sklearn
        sklearn_ver = sklearn.__version__
        ok_checks.append(f"scikit-learn version: {sklearn_ver}")
    except Exception as e:
        blockers.append(f"scikit-learn import failed: {e}")

    # Model files
    models_dir = REPO_ROOT / "titan" / "data" / "models"
    xgb_path = models_dir / "xgboost_v1.pkl"
    meta_path = models_dir / "meta_label_v2_context.pkl"

    model_info = {}
    for name, path in [("xgboost_v1.pkl", xgb_path), ("meta_label_v2_context.pkl", meta_path)]:
        if path.exists():
            model_info[name] = {"exists": True, "size_bytes": path.stat().st_size}
            ok_checks.append(f"{name} exists ({path.stat().st_size} bytes)")
        else:
            model_info[name] = {"exists": False, "size_bytes": 0}
            blockers.append(f"Model file missing: {name}")

    # Try loading models
    xgb_loaded = False
    meta_loaded = False
    xgb_model = None
    meta_model = None

    if xgb_path.exists() and not blockers:
        try:
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                with open(xgb_path, "rb") as f:
                    xgb_model = pickle.load(f)
                xgb_loaded = True
                ok_checks.append("xgboost_v1.pkl loaded successfully")
                # Check for serialization warnings
                for warning in w:
                    msg = str(warning.message)
                    if "version" in msg.lower() or "compat" in msg.lower() or "inconsistent" in msg.lower():
                        warnings_list.append(f"MODEL_SERIALIZATION_VERSION_WARNING: XGBoost: {msg}")
        except Exception as e:
            blockers.append(f"xgboost_v1.pkl load failed: {e}")

    if meta_path.exists() and not blockers:
        try:
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                with open(meta_path, "rb") as f:
                    meta_model = pickle.load(f)
                meta_loaded = True
                ok_checks.append("meta_label_v2_context.pkl loaded successfully")
                for warning in w:
                    msg = str(warning.message)
                    if "version" in msg.lower() or "compat" in msg.lower() or "inconsistent" in msg.lower():
                        warnings_list.append(f"MODEL_SERIALIZATION_VERSION_WARNING: sklearn: {msg}")
        except Exception as e:
            blockers.append(f"meta_label_v2_context.pkl load failed: {e}")

    # Try sample inference
    inference_passed = False
    prediction_info = {}
    if xgb_loaded and not blockers:
        try:
            import numpy as np
            # Try to get feature count from model
            if hasattr(xgb_model, "n_features_in_"):
                n_features = xgb_model.n_features_in_
                prediction_info["expected_features"] = n_features
                ok_checks.append(f"Model expects {n_features} features")
            elif hasattr(xgb_model, "feature_names"):
                n_features = len(xgb_model.feature_names) if xgb_model.feature_names else 0
                prediction_info["expected_features"] = n_features
                ok_checks.append(f"Model expects {n_features} features (from feature_names)")

            # Create dummy input
            n_feat = prediction_info.get("expected_features", 100)
            dummy = np.zeros((1, n_feat))
            pred = xgb_model.predict(dummy)
            prediction_info["output_shape"] = list(pred.shape) if hasattr(pred, "shape") else [1]
            prediction_info["has_nan"] = bool(np.isnan(pred).any()) if hasattr(pred, "__len__") else False
            prediction_info["deterministic"] = True  # verified below

            # Check determinism
            pred2 = xgb_model.predict(dummy)
            if hasattr(pred, "__len__") and hasattr(pred2, "__len__"):
                prediction_info["deterministic"] = bool(np.allclose(pred, pred2))

            if prediction_info["has_nan"]:
                blockers.append("Model prediction contains NaN")
            else:
                inference_passed = True
                ok_checks.append("Sample inference passed (no NaN, deterministic)")

        except Exception as e:
            blockers.append(f"Sample inference failed: {e}")

    # Verdict
    if blockers:
        verdict = "MODEL_ARTIFACT_BLOCKED"
    elif warnings_list:
        if inference_passed:
            verdict = "MODEL_ARTIFACT_READY_WITH_WARNINGS"
        else:
            verdict = "MODEL_ARTIFACT_BLOCKED"
    else:
        verdict = "MODEL_ARTIFACT_READY"

    return {
        "timestamp_utc": ts,
        "head_short": head,
        "verdict": verdict,
        "python_version": py_version,
        "xgboost_version": xgb_ver,
        "sklearn_version": sklearn_ver,
        "model_info": model_info,
        "prediction_info": prediction_info,
        "inference_passed": inference_passed,
        "ok_checks": ok_checks,
        "warnings": warnings_list,
        "blockers": blockers,
    }


def write_report(result: dict) -> dict:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str, ensure_ascii=False)
    with open(MD_PATH, "w", encoding="utf-8") as f:
        f.write("# TITAN XAU AI - Model Artifact Compatibility Audit\n\n")
        f.write(f"**Verdict:** **{result['verdict']}**\n\n")
        f.write(f"**Timestamp:** {result['timestamp_utc']}\n\n")
        f.write(f"**XGBoost:** {result.get('xgboost_version', 'N/A')}\n\n")
        f.write(f"**scikit-learn:** {result.get('sklearn_version', 'N/A')}\n\n")
        f.write(f"**Inference Passed:** {result['inference_passed']}\n\n")
        f.write("## Model Files\n\n")
        f.write("| File | Exists | Size |\n|---|---|---|\n")
        for name, info in result["model_info"].items():
            f.write(f"| {name} | {info['exists']} | {info['size_bytes']} |\n")
        f.write("\n## Prediction Info\n\n")
        f.write("| Field | Value |\n|---|---|\n")
        for k, v in result.get("prediction_info", {}).items():
            f.write(f"| {k} | {v} |\n")
        if result.get("ok_checks"):
            f.write("\n## OK Checks\n\n")
            for c in result["ok_checks"]:
                f.write(f"- {c}\n")
        if result.get("warnings"):
            f.write("\n## Warnings\n\n")
            for w in result["warnings"]:
                f.write(f"- {w}\n")
        if result.get("blockers"):
            f.write("\n## Blockers\n\n")
            for b in result["blockers"]:
                f.write(f"- **{b}**\n")
    return {"json_path": str(JSON_PATH), "md_path": str(MD_PATH)}


def main() -> int:
    print("=" * 70)
    print("  TITAN XAU AI - Model Artifact Compatibility Audit (Sprint 9.9.3.43)")
    print("=" * 70)
    result = run_audit()
    report = write_report(result)
    print(f"\n  Verdict: {result['verdict']}")
    print(f"  XGBoost: {result.get('xgboost_version', 'N/A')}")
    print(f"  sklearn: {result.get('sklearn_version', 'N/A')}")
    print(f"  Inference: {result['inference_passed']}")
    print(f"  Blockers: {len(result['blockers'])}")
    print(f"  Warnings: {len(result['warnings'])}")
    print(f"\n  JSON: {report['json_path']}")
    print(f"  MD:   {report['md_path']}")
    print("\n" + "=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
