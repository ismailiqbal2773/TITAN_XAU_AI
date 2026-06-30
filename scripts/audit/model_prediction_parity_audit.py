#!/usr/bin/env python3
"""
TITAN XAU AI - Model Prediction Parity Audit (Sprint 9.9.3.43.1)
=================================================================
Compares original active artifacts vs normalized candidates.
NEVER replaces active models. NEVER retrain.
"""
from __future__ import annotations
import json, pickle, sys, warnings
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
OUTPUT_DIR = REPO_ROOT / "data" / "audit" / "model_artifacts"

CANDIDATE_DIR = REPO_ROOT / "data" / "model_candidates" / "normalized_artifacts"


def run_parity_audit() -> dict:
    ts = datetime.now(timezone.utc).isoformat()
    ok_checks = []
    warnings_list = []
    blockers = []

    models_dir = REPO_ROOT / "titan" / "data" / "models"
    xgb_path = models_dir / "xgboost_v1.pkl"
    meta_path = models_dir / "meta_label_v2_context.pkl"

    # Load original XGBoost model
    xgb_original = None
    if xgb_path.exists():
        try:
            with warnings.catch_warnings(record=True):
                warnings.simplefilter("always")
                with open(xgb_path, "rb") as f:
                    xgb_original = pickle.load(f)
                ok_checks.append("Original XGBoost model loaded")
        except Exception as e:
            blockers.append(f"Original XGBoost load failed: {e}")

    # Load candidate XGBoost model if available
    xgb_candidate = None
    candidate_xgb_path = CANDIDATE_DIR / "xgboost_v1_normalized.json"
    if candidate_xgb_path.exists():
        try:
            import xgboost as xgb
            booster = xgb.Booster()
            booster.load_model(str(candidate_xgb_path))
            xgb_candidate = booster
            ok_checks.append("Candidate XGBoost model loaded")
        except Exception as e:
            warnings_list.append(f"Candidate XGBoost load failed: {e}")
    else:
        ok_checks.append("No XGBoost candidate available — PARITY_NOT_AVAILABLE for XGBoost")

    # Run parity test for XGBoost
    xgb_parity = "NOT_AVAILABLE"
    if xgb_original is not None and xgb_candidate is not None:
        try:
            import numpy as np
            n_features = getattr(xgb_original, "n_features_in_", 100)
            dummy = np.zeros((1, n_features))
            pred_orig = xgb_original.predict(dummy)
            pred_cand = xgb_candidate.predict(xgb.DMatrix(dummy))
            if hasattr(pred_orig, "__len__") and hasattr(pred_cand, "__len__"):
                diff = float(np.max(np.abs(pred_orig - pred_cand)))
            else:
                diff = abs(float(pred_orig) - float(pred_cand))
            tolerance = 1e-6
            if diff <= tolerance:
                xgb_parity = "PASS"
                ok_checks.append(f"XGBoost parity PASS (diff={diff:.2e} <= {tolerance})")
            else:
                xgb_parity = "FAIL"
                blockers.append(f"XGBoost parity FAIL (diff={diff:.2e} > {tolerance})")
        except Exception as e:
            xgb_parity = "FAIL"
            blockers.append(f"XGBoost parity test failed: {e}")

    # Load original meta model
    meta_original = None
    if meta_path.exists():
        try:
            with warnings.catch_warnings(record=True):
                warnings.simplefilter("always")
                with open(meta_path, "rb") as f:
                    meta_original = pickle.load(f)
                ok_checks.append("Original meta-label model loaded")
        except Exception as e:
            blockers.append(f"Original meta-label load failed: {e}")

    # Load candidate meta model if available
    meta_candidate = None
    candidate_meta_path = CANDIDATE_DIR / "meta_label_v2_context_normalized.joblib"
    if candidate_meta_path.exists():
        try:
            import joblib
            meta_candidate = joblib.load(str(candidate_meta_path))
            ok_checks.append("Candidate meta-label model loaded")
        except Exception as e:
            warnings_list.append(f"Candidate meta-label load failed: {e}")
    else:
        ok_checks.append("No meta-label candidate available — PARITY_NOT_AVAILABLE for meta")

    # Run parity test for meta
    meta_parity = "NOT_AVAILABLE"
    if meta_original is not None and meta_candidate is not None:
        try:
            import numpy as np
            n_features = getattr(meta_original, "n_features_in_", 10)
            dummy = np.zeros((1, n_features))
            pred_orig = meta_original.predict(dummy)
            pred_cand = meta_candidate.predict(dummy)
            if hasattr(pred_orig, "__len__") and hasattr(pred_cand, "__len__"):
                diff = float(np.max(np.abs(pred_orig - pred_cand)))
            else:
                diff = abs(float(pred_orig) - float(pred_cand))
            tolerance = 1e-6
            if diff <= tolerance:
                meta_parity = "PASS"
                ok_checks.append(f"Meta-label parity PASS (diff={diff:.2e})")
            else:
                meta_parity = "FAIL"
                blockers.append(f"Meta-label parity FAIL (diff={diff:.2e})")
        except Exception as e:
            meta_parity = "FAIL"
            blockers.append(f"Meta-label parity test failed: {e}")

    # Verdict
    if blockers:
        verdict = "MODEL_PARITY_FAIL"
    elif xgb_parity == "NOT_AVAILABLE" and meta_parity == "NOT_AVAILABLE":
        verdict = "MODEL_PARITY_NOT_AVAILABLE"
    elif warnings_list:
        verdict = "MODEL_PARITY_PASS_WITH_WARNINGS"
    else:
        verdict = "MODEL_PARITY_PASS"

    return {
        "timestamp_utc": ts,
        "verdict": verdict,
        "xgboost_parity": xgb_parity,
        "meta_parity": meta_parity,
        "ok_checks": ok_checks,
        "warnings": warnings_list,
        "blockers": blockers,
        "important_note": (
            "Parity audit does NOT replace active models. "
            "If parity FAIL, future model replacement is BLOCKED. "
            "No champion replacement in this sprint."
        ),
    }


def write_report(result: dict) -> dict:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUTPUT_DIR / "model_prediction_parity_audit.json"
    md_path = OUTPUT_DIR / "model_prediction_parity_audit.md"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str, ensure_ascii=False)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# TITAN XAU AI - Model Prediction Parity Audit\n\n")
        f.write(f"**Verdict:** **{result['verdict']}**\n\n")
        f.write(f"**XGBoost Parity:** {result['xgboost_parity']}\n\n")
        f.write(f"**Meta-label Parity:** {result['meta_parity']}\n\n")
        if result.get("ok_checks"):
            f.write("## OK Checks\n\n")
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
        f.write(f"\n## Important Note\n\n{result['important_note']}\n")
    return {"json_path": str(json_path), "md_path": str(md_path)}


def main() -> int:
    print("=" * 70)
    print("  TITAN XAU AI - Model Prediction Parity Audit (Sprint 9.9.3.43.1)")
    print("=" * 70)
    result = run_parity_audit()
    report = write_report(result)
    print(f"\n  Verdict: {result['verdict']}")
    print(f"  XGBoost Parity: {result['xgboost_parity']}")
    print(f"  Meta Parity: {result['meta_parity']}")
    print(f"\n  JSON: {report['json_path']}")
    print(f"  MD:   {report['md_path']}")
    print("\n" + "=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
