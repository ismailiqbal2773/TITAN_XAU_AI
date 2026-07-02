#!/usr/bin/env python3
"""
TITAN XAU AI - Model Artifact Compatibility Audit (Sprint v2.8.1)
==================================================================
Captures XGBoost/sklearn version mismatch warnings seen during
autonomous-entry-check and classifies their autonomous readiness impact.

NEVER sends orders. NEVER modifies positions. NEVER retrains models.
NEVER regenerates model artifacts.

Verdicts:
  MODEL_ARTIFACTS_COMPATIBLE              - no warnings, models load cleanly
  MODEL_ARTIFACTS_COMPATIBLE_WITH_WARNINGS - version warnings present but
                                              models still load and predict
  MODEL_ARTIFACTS_BLOCKED_VERSION_MISMATCH - model loading fails or prediction
                                              is invalid due to version mismatch
  MODEL_ARTIFACTS_NOT_FOUND                - no model artifacts found

Outputs:
  data/audit/demo_micro_execution/model_artifact_compatibility_audit.json
  data/audit/demo_micro_execution/model_artifact_compatibility_audit.md
"""
from __future__ import annotations
import argparse, json, sys, warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

OUTPUT_DIR = REPO_ROOT / "data" / "audit" / "demo_micro_execution"

MODEL_ARTIFACTS_COMPATIBLE = "MODEL_ARTIFACTS_COMPATIBLE"
MODEL_ARTIFACTS_COMPATIBLE_WITH_WARNINGS = "MODEL_ARTIFACTS_COMPATIBLE_WITH_WARNINGS"
MODEL_ARTIFACTS_BLOCKED_VERSION_MISMATCH = "MODEL_ARTIFACTS_BLOCKED_VERSION_MISMATCH"
MODEL_ARTIFACTS_NOT_FOUND = "MODEL_ARTIFACTS_NOT_FOUND"

ALL_VERDICTS = (
    MODEL_ARTIFACTS_COMPATIBLE,
    MODEL_ARTIFACTS_COMPATIBLE_WITH_WARNINGS,
    MODEL_ARTIFACTS_BLOCKED_VERSION_MISMATCH,
    MODEL_ARTIFACTS_NOT_FOUND,
)


def _get_runtime_versions() -> dict:
    """Get runtime package versions."""
    versions = {}
    try:
        import xgboost
        versions["xgboost"] = xgboost.__version__
    except Exception:
        versions["xgboost"] = "not_installed"
    try:
        import sklearn
        versions["sklearn"] = sklearn.__version__
    except Exception:
        versions["sklearn"] = "not_installed"
    try:
        import numpy
        versions["numpy"] = numpy.__version__
    except Exception:
        versions["numpy"] = "not_installed"
    try:
        import scipy
        versions["scipy"] = scipy.__version__
    except Exception:
        versions["scipy"] = "not_installed"
    return versions


def _find_model_artifacts() -> list:
    """Find model artifact files in the project."""
    model_paths = []
    search_dirs = [
        REPO_ROOT / "models",
        REPO_ROOT / "data" / "models",
        REPO_ROOT / "artifacts" / "models",
    ]
    for d in search_dirs:
        if d.exists():
            for ext in ("*.json", "*.pkl", "*.ubj", "*.model"):
                model_paths.extend(d.rglob(ext))
    return model_paths


def _try_load_models(captured_warnings: list) -> dict:
    """Try to load models and capture warnings.

    Returns dict with:
      - models_loadable: bool
      - prediction_valid: bool
      - model_files: list
      - load_errors: list
    """
    result = {
        "models_loadable": False,
        "prediction_valid": False,
        "model_files": [],
        "load_errors": [],
    }
    try:
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            from titan.production.model_loader import load_production_models
            bundle = load_production_models()
            result["models_loadable"] = bundle is not None
            if bundle:
                result["model_files"] = [
                    str(getattr(bundle, "xgb_path", "")),
                    str(getattr(bundle, "meta_path", "")),
                ]
            # Capture warnings
            for warning in w:
                captured_warnings.append({
                    "category": warning.category.__name__,
                    "message": str(warning.message),
                    "severity": "warning",
                })
    except Exception as e:
        result["load_errors"].append(str(e))

    # Try prediction
    if result["models_loadable"]:
        try:
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                from titan.production.inference import InferenceEngine
                engine = InferenceEngine()
                signal = engine.generate(source="canonical")
                result["prediction_valid"] = signal is not None
                for warning in w:
                    captured_warnings.append({
                        "category": warning.category.__name__,
                        "message": str(warning.message),
                        "severity": "warning",
                    })
        except Exception as e:
            result["load_errors"].append(f"prediction_error: {e}")

    return result


def run_audit() -> dict:
    """Run the model artifact compatibility audit.

    NEVER calls mt5.order_send. NEVER retrains models.
    """
    ts = datetime.now(timezone.utc).isoformat()
    ok_checks = []
    blockers = []
    warnings_list = []
    findings = {}

    # Runtime versions
    runtime_versions = _get_runtime_versions()
    findings["runtime_versions"] = runtime_versions
    ok_checks.append(f"Runtime versions: {runtime_versions}")

    # Find model artifacts
    model_artifacts = _find_model_artifacts()
    findings["model_artifacts_found"] = len(model_artifacts)
    findings["model_artifact_paths"] = [str(p) for p in model_artifacts[:20]]

    if not model_artifacts:
        verdict = MODEL_ARTIFACTS_NOT_FOUND
        warnings_list.append("No model artifacts found in models/ or data/models/")
    else:
        ok_checks.append(f"Found {len(model_artifacts)} model artifacts")

        # Try to load models and capture warnings
        captured_warnings = []
        load_result = _try_load_models(captured_warnings)
        findings["models_loadable"] = load_result["models_loadable"]
        findings["prediction_valid"] = load_result["prediction_valid"]
        findings["model_files_loaded"] = load_result["model_files"]
        findings["load_errors"] = load_result["load_errors"]
        findings["captured_warnings"] = captured_warnings

        # Classify warnings
        version_mismatch_warnings = []
        for w in captured_warnings:
            msg = w.get("message", "").lower()
            if "version" in msg or "inconsistent" in msg or "xgboost" in msg or "sklearn" in msg:
                version_mismatch_warnings.append(w)

        findings["version_mismatch_warnings"] = version_mismatch_warnings
        findings["has_version_mismatch_warnings"] = len(version_mismatch_warnings) > 0

        # Determine verdict
        if not load_result["models_loadable"]:
            verdict = MODEL_ARTIFACTS_BLOCKED_VERSION_MISMATCH
            blockers.append("MODELS_NOT_LOADABLE: model loading failed")
        elif not load_result["prediction_valid"]:
            verdict = MODEL_ARTIFACTS_BLOCKED_VERSION_MISMATCH
            blockers.append("PREDICTION_INVALID: model loaded but prediction failed")
        elif version_mismatch_warnings:
            verdict = MODEL_ARTIFACTS_COMPATIBLE_WITH_WARNINGS
            for w in version_mismatch_warnings:
                warnings_list.append(
                    f"MODEL_ARTIFACT_VERSION_WARNING: {w.get('category', '')}: {w.get('message', '')}"
                )
            ok_checks.append("Models load and predict despite version warnings")
        else:
            verdict = MODEL_ARTIFACTS_COMPATIBLE
            ok_checks.append("Models load and predict with no version warnings")

    # Autonomous readiness impact
    autonomous_readiness_impact = "none"
    if verdict == MODEL_ARTIFACTS_BLOCKED_VERSION_MISMATCH:
        autonomous_readiness_impact = "hard_block"
    elif verdict == MODEL_ARTIFACTS_COMPATIBLE_WITH_WARNINGS:
        autonomous_readiness_impact = "warning"
    elif verdict == MODEL_ARTIFACTS_NOT_FOUND:
        autonomous_readiness_impact = "warning"
    findings["autonomous_readiness_impact"] = autonomous_readiness_impact

    return {
        "timestamp_utc": ts,
        "verdict": verdict,
        "ok_checks": ok_checks,
        "blockers": blockers,
        "warnings": warnings_list,
        "findings": findings,
        "safety": {
            "order_send_called": False,
            "position_modified": False,
            "execution_token_created": False,
            "models_retrained": False,
            "models_regenerated": False,
        },
    }


def write_report(result: dict) -> dict:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUTPUT_DIR / "model_artifact_compatibility_audit.json"
    md_path = OUTPUT_DIR / "model_artifact_compatibility_audit.md"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str, ensure_ascii=False)

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# TITAN XAU AI - Model Artifact Compatibility Audit (v2.8.1)\n\n")
        f.write("**Passive audit - no order_send, no retraining, no regeneration.**\n\n")
        f.write(f"**Verdict:** **{result['verdict']}**\n\n")
        f.write(f"**Timestamp:** {result['timestamp_utc']}\n\n")

        fnd = result.get("findings", {}) or {}
        f.write("## Runtime Versions\n\n")
        f.write("| Package | Version |\n|---|---|\n")
        for pkg, ver in fnd.get("runtime_versions", {}).items():
            f.write(f"| {pkg} | {ver} |\n")

        f.write(f"\n## Model Artifacts\n\n")
        f.write(f"- Artifacts found: {fnd.get('model_artifacts_found', 0)}\n")
        f.write(f"- Models loadable: {fnd.get('models_loadable', False)}\n")
        f.write(f"- Prediction valid: {fnd.get('prediction_valid', False)}\n")
        f.write(f"- Version mismatch warnings: {len(fnd.get('version_mismatch_warnings', []))}\n")
        f.write(f"- Autonomous readiness impact: {fnd.get('autonomous_readiness_impact', 'none')}\n")

        if fnd.get("captured_warnings"):
            f.write("\n## Captured Warnings\n\n")
            f.write("| Category | Message |\n|---|---|\n")
            for w in fnd["captured_warnings"]:
                f.write(f"| {w.get('category', '')} | {w.get('message', '')[:200]} |\n")

        if fnd.get("load_errors"):
            f.write("\n## Load Errors\n\n")
            for e in fnd["load_errors"]:
                f.write(f"- {e}\n")

        if result.get("blockers"):
            f.write("\n## Blockers\n\n")
            for b in result["blockers"]:
                f.write(f"- **{b}**\n")
        if result.get("warnings"):
            f.write("\n## Warnings\n\n")
            for w in result["warnings"]:
                f.write(f"- {w}\n")
        if result.get("ok_checks"):
            f.write("\n## OK Checks\n\n")
            for c in result["ok_checks"]:
                f.write(f"- {c}\n")

        f.write("\n## Safety\n\n")
        f.write("- order_send_called: False\n")
        f.write("- position_modified: False\n")
        f.write("- execution_token_created: False\n")
        f.write("- models_retrained: False\n")
        f.write("- models_regenerated: False\n")

    return {"json_path": str(json_path), "md_path": str(md_path)}


def main() -> int:
    print("=" * 70)
    print("  TITAN XAU AI - Model Artifact Compatibility Audit (v2.8.1)")
    print("=" * 70)
    result = run_audit()
    report = write_report(result)
    print(f"\n  Verdict: {result['verdict']}")
    fnd = result.get("findings", {})
    print(f"  Runtime versions: {fnd.get('runtime_versions', {})}")
    print(f"  Model artifacts found: {fnd.get('model_artifacts_found', 0)}")
    print(f"  Models loadable: {fnd.get('models_loadable', False)}")
    print(f"  Prediction valid: {fnd.get('prediction_valid', False)}")
    print(f"  Version mismatch warnings: {len(fnd.get('version_mismatch_warnings', []))}")
    print(f"  Autonomous readiness impact: {fnd.get('autonomous_readiness_impact', 'none')}")
    if result.get("blockers"):
        print(f"  Blockers: {len(result['blockers'])}")
        for b in result["blockers"]:
            print(f"    - {b}")
    if result.get("warnings"):
        print(f"  Warnings: {len(result['warnings'])}")
        for w in result["warnings"][:3]:
            print(f"    - {w}")
    print(f"\n  JSON: {report['json_path']}")
    print(f"  MD:   {report['md_path']}")
    print("\n" + "=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
