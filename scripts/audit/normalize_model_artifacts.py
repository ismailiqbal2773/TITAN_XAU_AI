#!/usr/bin/env python3
"""
TITAN XAU AI - Normalize Model Artifacts (Sprint 9.9.3.43.1)
=============================================================
Creates normalized candidate artifacts WITHOUT retraining.
NEVER replaces active production models.
"""
from __future__ import annotations
import hashlib, json, pickle, sys, warnings
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
OUTPUT_DIR = REPO_ROOT / "data" / "audit" / "model_artifacts"
CANDIDATE_DIR = REPO_ROOT / "data" / "model_candidates" / "normalized_artifacts"


def run_normalization() -> dict:
    ts = datetime.now(timezone.utc).isoformat()
    ok_checks = []
    warnings_list = []
    blockers = []
    candidates = {}

    models_dir = REPO_ROOT / "titan" / "data" / "models"
    xgb_path = models_dir / "xgboost_v1.pkl"
    meta_path = models_dir / "meta_label_v2_context.pkl"

    # Load XGBoost model
    xgb_model = None
    xgb_ver = None
    if xgb_path.exists():
        try:
            import xgboost as xgb
            xgb_ver = xgb.__version__
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                with open(xgb_path, "rb") as f:
                    xgb_model = pickle.load(f)
                ok_checks.append("XGBoost model loaded for normalization")
                for warning in w:
                    msg = str(warning.message)
                    if "version" in msg.lower() or "compat" in msg.lower():
                        warnings_list.append(f"MODEL_SERIALIZATION_VERSION_WARNING: XGBoost: {msg}")
        except Exception as e:
            blockers.append(f"XGBoost model load failed: {e}")
    else:
        blockers.append("xgboost_v1.pkl not found")

    # Try to export XGBoost native format
    if xgb_model is not None:
        try:
            if hasattr(xgb_model, "save_raw"):
                raw = xgb_model.save_raw()
                CANDIDATE_DIR.mkdir(parents=True, exist_ok=True)
                candidate_path = CANDIDATE_DIR / "xgboost_v1_normalized.json"
                # Try JSON export via Booster if available
                if hasattr(xgb_model, "get_booster"):
                    booster = xgb_model.get_booster()
                    booster.save_model(str(candidate_path))
                    candidates["xgboost_v1_normalized.json"] = {
                        "path": str(candidate_path),
                        "size_bytes": candidate_path.stat().st_size,
                    }
                    ok_checks.append("XGBoost normalized candidate exported (native JSON)")
                else:
                    ok_checks.append("XGBoost model has no Booster access — skipping native export")
            else:
                ok_checks.append("XGBoost model has no save_raw — skipping native export")
        except Exception as e:
            warnings_list.append(f"XGBoost native export failed: {e}")

    # Load sklearn meta model
    meta_model = None
    sklearn_ver = None
    if meta_path.exists():
        try:
            import sklearn
            sklearn_ver = sklearn.__version__
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                with open(meta_path, "rb") as f:
                    meta_model = pickle.load(f)
                ok_checks.append("Meta-label model loaded for normalization")
                for warning in w:
                    msg = str(warning.message)
                    if "version" in msg.lower() or "compat" in msg.lower() or "inconsistent" in msg.lower():
                        warnings_list.append(f"MODEL_SERIALIZATION_VERSION_WARNING: sklearn: {msg}")
        except Exception as e:
            blockers.append(f"Meta-label model load failed: {e}")
    else:
        blockers.append("meta_label_v2_context.pkl not found")

    # Export sklearn model as joblib copy (current environment normalized)
    if meta_model is not None:
        try:
            import joblib
            CANDIDATE_DIR.mkdir(parents=True, exist_ok=True)
            candidate_path = CANDIDATE_DIR / "meta_label_v2_context_normalized.joblib"
            joblib.dump(meta_model, str(candidate_path))
            candidates["meta_label_v2_context_normalized.joblib"] = {
                "path": str(candidate_path),
                "size_bytes": candidate_path.stat().st_size,
            }
            ok_checks.append("Meta-label normalized candidate exported (joblib)")
        except Exception as e:
            warnings_list.append(f"Meta-label joblib export failed: {e}")

    # Verdict
    if blockers:
        verdict = "MODEL_NORMALIZATION_BLOCKED"
    elif warnings_list:
        verdict = "MODEL_NORMALIZATION_READY_WITH_WARNINGS"
    else:
        verdict = "MODEL_NORMALIZATION_READY"

    return {
        "timestamp_utc": ts,
        "verdict": verdict,
        "xgboost_version": xgb_ver,
        "sklearn_version": sklearn_ver,
        "candidates": candidates,
        "ok_checks": ok_checks,
        "warnings": warnings_list,
        "blockers": blockers,
        "important_note": (
            "Normalized candidates are NOT active production models. "
            "They must NOT replace active artifacts without parity proof and separate approval. "
            "No retraining occurred."
        ),
    }


def write_report(result: dict) -> dict:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUTPUT_DIR / "model_normalization_report.json"
    md_path = OUTPUT_DIR / "model_normalization_report.md"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str, ensure_ascii=False)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# TITAN XAU AI - Model Normalization Report\n\n")
        f.write(f"**Verdict:** **{result['verdict']}**\n\n")
        f.write(f"**XGBoost:** {result.get('xgboost_version', 'N/A')}\n\n")
        f.write(f"**scikit-learn:** {result.get('sklearn_version', 'N/A')}\n\n")
        if result.get("candidates"):
            f.write("## Candidate Artifacts\n\n")
            f.write("| File | Size |\n|---|---|\n")
            for name, info in result["candidates"].items():
                f.write(f"| {name} | {info['size_bytes']} |\n")
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
        f.write(f"\n## Important Note\n\n{result['important_note']}\n")
    return {"json_path": str(json_path), "md_path": str(md_path)}


def main() -> int:
    print("=" * 70)
    print("  TITAN XAU AI - Model Artifact Normalization (Sprint 9.9.3.43.1)")
    print("=" * 70)
    result = run_normalization()
    report = write_report(result)
    print(f"\n  Verdict: {result['verdict']}")
    print(f"  Candidates: {len(result['candidates'])}")
    print(f"  Blockers: {len(result['blockers'])}")
    print(f"\n  JSON: {report['json_path']}")
    print(f"  MD:   {report['md_path']}")
    print("\n" + "=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
