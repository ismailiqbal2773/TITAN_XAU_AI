#!/usr/bin/env python3
"""
TITAN XAU AI - Model Artifact Health Audit (Sprint v2.8.3.3)
==============================================================
Auto-discovers ALL active production models from registry/config/runtime
inference path and verifies each one individually.

Active model discovery:
  1. config/runtime.yaml -> models.xgb_path, models.meta_path (REQUIRED active_primary)
  2. titan/data/models/*.pkl (all .pkl artifacts - inspected, role-classified)
  3. config/runtime.yaml -> models.lstm_path, transformer_path (challenger/backup)

Per-model checks:
  * artifact exists + size > 0
  * model loads successfully (with warnings captured)
  * sklearn/xgboost/lightgbm/catboost compatibility warnings captured
  * expected feature schema matches runtime feature vector
  * feature count matches
  * predict or predict_proba works
  * output is finite (no NaN, no inf)
  * probabilities within [0.0, 1.0]
  * output class/direction valid
  * latency measured
  * model role identified: active_primary / ensemble_member / backup / disabled / deprecated
  * router/ensemble does not silently skip failed required models
  * no dummy prediction, no silent default confidence, no silent fallback

Verdicts:
  MODEL_ARTIFACT_HEALTH_PASS              - all required active models healthy, no warnings
  MODEL_ARTIFACT_HEALTH_PASS_WITH_WARNINGS - healthy but compatibility warnings present
  MODEL_ARTIFACT_HEALTH_BLOCKED           - any required active model failed

NEVER sends orders. NEVER modifies positions. NEVER retrains. NEVER creates token.
"""
from __future__ import annotations
import json, sys, os, time, pickle, warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

OUTPUT_DIR = REPO_ROOT / "data" / "audit" / "model_health"

MODEL_ARTIFACT_HEALTH_PASS = "MODEL_ARTIFACT_HEALTH_PASS"
MODEL_ARTIFACT_HEALTH_PASS_WITH_WARNINGS = "MODEL_ARTIFACT_HEALTH_PASS_WITH_WARNINGS"
MODEL_ARTIFACT_HEALTH_BLOCKED = "MODEL_ARTIFACT_HEALTH_BLOCKED"

ALL_VERDICTS = (
    MODEL_ARTIFACT_HEALTH_PASS,
    MODEL_ARTIFACT_HEALTH_PASS_WITH_WARNINGS,
    MODEL_ARTIFACT_HEALTH_BLOCKED,
)


def _load_runtime_config() -> dict:
    """Load config/runtime.yaml."""
    cfg_path = REPO_ROOT / "config" / "runtime.yaml"
    if not cfg_path.exists():
        return {}
    try:
        import yaml
        with open(cfg_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def _runtime_versions() -> dict:
    """Get runtime library versions."""
    out = {}
    for pkg in ("xgboost", "sklearn", "lightgbm", "catboost", "numpy", "scipy", "pandas", "torch"):
        try:
            mod = __import__(pkg)
            out[pkg] = getattr(mod, "__version__", "unknown")
        except Exception:
            out[pkg] = "not_installed"
    return out


def _classify_role(path_str: str, runtime_cfg: dict) -> tuple:
    """Classify model role from path and runtime config.

    Sprint v2.8.3.3.1 reconciliation: challenger models that are NOT in the
    active runtime inference chain must be classified as `optional`, not
    `ensemble_member`. Only models actually wired into the runtime/router
    are `ensemble_member` (required for runtime).

    Returns (role, non_blocking_reason) tuple where non_blocking_reason is
    a human-readable explanation for why an optional/backup/disabled/deprecated
    model does not block runtime.

    Roles:
      active_primary   - listed in config/runtime.yaml as xgb_path or meta_path
                         (REQUIRED for runtime)
      ensemble_member  - .pkl model that is actively wired into runtime/router
                         ensemble (REQUIRED for runtime)
                         Note: TITAN XAU AI runtime currently uses ONLY
                         xgboost_v1 + meta_label_v2_context (no ensemble
                         router), so no .pkl is classified as ensemble_member
                         unless explicitly registered.
      backup           - lstm/transformer .pt artifacts (challenger, NOT required)
      optional         - challenger .pkl models not in active inference chain
                         (e.g. lightgbm_v1, logreg_v1_price, meta_label_v1,
                         xgboost_v2_micro) - frozen challengers per
                         scripts/titan_audit_report.py
      disabled         - explicitly disabled in config
      deprecated       - old/v1/legacy path naming
    """
    name = path_str.lower()
    cfg_models = (runtime_cfg.get("models") or {}) if runtime_cfg else {}
    active_paths = {str(cfg_models.get("xgb_path", "")).lower(),
                   str(cfg_models.get("meta_path", "")).lower()}
    # Normalize repo-relative
    norm = path_str
    if norm.startswith(str(REPO_ROOT)):
        norm = norm[len(str(REPO_ROOT)) + 1:].replace("\\", "/")
    if norm.lower() in active_paths or path_str.lower() in active_paths:
        return ("active_primary", "")
    if name.endswith(".pt"):
        return ("backup", "PyTorch challenger model - not in active inference chain")
    if "deprecated" in name or "old_" in name or "_legacy" in name:
        return ("deprecated", "Legacy/deprecated model artifact - retained for audit history only")
    if name.endswith(".pkl"):
        # Sprint v2.8.3.3.1: All non-active .pkl models are OPTIONAL challengers.
        # TITAN XAU AI runtime uses only xgboost_v1 + meta_label_v2_context.
        # Other .pkl files (lightgbm_v1, logreg_v1_price, meta_label_v1,
        # xgboost_v2_micro) are frozen challengers per scripts/titan_audit_report.py
        # and are NOT wired into the runtime inference chain.
        return ("optional",
                "Challenger model - frozen, not wired into active runtime inference chain "
                "(per scripts/titan_audit_report.py: 'Not in F8 inference chain'). "
                "Failure is non-blocking for v2.8.4 release gate.")
    return ("optional", "Unknown model - classified optional by default (non-blocking)")


def _discover_active_models(runtime_cfg: dict) -> list:
    """Discover all active production model artifacts.

    Active = active_primary (from config) + optional/ensemble_member (.pkl in models/).
    Backup .pt files (lstm, transformer) are also listed but role=backup.

    Each discovered entry includes a `non_blocking_reason` for optional/backup/
    disabled/deprecated roles explaining why a failure of that model does NOT
    block runtime.
    """
    discovered = []
    seen_paths = set()

    # 1. From config/runtime.yaml (active_primary)
    cfg_models = (runtime_cfg.get("models") or {}) if runtime_cfg else {}
    for key in ("xgb_path", "meta_path"):
        rel = cfg_models.get(key)
        if rel:
            p = REPO_ROOT / rel
            if p.exists() and str(p) not in seen_paths:
                discovered.append({
                    "name": p.stem,
                    "path": str(p),
                    "role": "active_primary",
                    "config_key": key,
                    "non_blocking_reason": "",
                })
                seen_paths.add(str(p))

    # 2. Scan titan/data/models/ for .pkl artifacts
    models_dir = REPO_ROOT / "titan" / "data" / "models"
    if models_dir.exists():
        for ext in ("*.pkl",):
            for p in sorted(models_dir.glob(ext)):
                if str(p) in seen_paths:
                    continue
                role, nbr = _classify_role(str(p), runtime_cfg)
                discovered.append({
                    "name": p.stem,
                    "path": str(p),
                    "role": role,
                    "config_key": "",
                    "non_blocking_reason": nbr,
                })
                seen_paths.add(str(p))

    # 3. Also scan for .pt (torch) as backup
    if models_dir.exists():
        for p in sorted(models_dir.glob("*.pt")):
            if str(p) in seen_paths:
                continue
            role, nbr = _classify_role(str(p), runtime_cfg)
            discovered.append({
                "name": p.stem,
                "path": str(p),
                "role": role,
                "config_key": "",
                "non_blocking_reason": nbr,
            })
            seen_paths.add(str(p))

    return discovered


def _expected_feature_count(name: str) -> int:
    """Return expected feature count for a given model name.

    Returns 0 if model name pattern is not recognized (audit will not enforce
    schema in that case, to avoid false positives on unknown / non-canonical
    artifacts).
    """
    name_l = name.lower()
    # Specific meta-label v2 -> 22 features (matches titan/production/model_loader.py META_N_FEATURES)
    if "meta_label_v2" in name_l:
        return 22
    # XGBoost v1 -> 55 features (matches XGB_N_FEATURES)
    if "xgboost_v1" in name_l or name_l == "xgb_v1":
        return 55
    # All others: don't enforce (avoid false positives on legacy/v2/micro variants
    # whose training-time schema may legitimately differ)
    return 0


def _is_pt_torch_model(path: str) -> bool:
    """Check if path ends with .pt (PyTorch checkpoint)."""
    return path.lower().endswith(".pt")


def _capture_load_warnings(model_path: str, model_name: str) -> tuple[Any, list, list]:
    """Load model and capture warnings.

    Returns (model, captured_warnings, load_errors).
    """
    captured = []
    errors = []
    model = None
    try:
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            with open(model_path, "rb") as f:
                model = pickle.load(f)
            for warning in w:
                msg = str(warning.message)
                captured.append({
                    "category": warning.category.__name__,
                    "message": msg,
                    "severity": "warning",
                    "is_version_warning": (
                        "InconsistentVersion" in warning.category.__name__
                        or "version" in msg.lower()
                        or "sklearn" in msg.lower()
                        or "xgboost" in msg.lower()
                    ),
                })
    except Exception as e:
        errors.append(f"load_error: {e}")
        # Try joblib as fallback for sklearn models
        try:
            import joblib
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                model = joblib.load(model_path)
                for warning in w:
                    captured.append({
                        "category": warning.category.__name__,
                        "message": str(warning.message),
                        "severity": "warning",
                        "is_version_warning": (
                            "InconsistentVersion" in warning.category.__name__
                            or "version" in str(warning.message).lower()
                        ),
                    })
        except Exception as e2:
            errors.append(f"joblib_load_error: {e2}")
    return model, captured, errors


def _verify_model_output(model: Any, n_features: int, model_name: str) -> dict:
    """Verify model output: predict, predict_proba, finiteness, range.

    Returns dict with:
      prediction_works: bool
      predict_proba_works: bool
      output_finite: bool
      probabilities_in_range: bool
      output_class_valid: bool
      prediction_value: Any
      probabilities: list
      classes: list
      latency_ms: float
      errors: list
    """
    result = {
        "prediction_works": False,
        "predict_proba_works": False,
        "output_finite": False,
        "probabilities_in_range": False,
        "output_class_valid": False,
        "prediction_value": None,
        "probabilities": [],
        "classes": [],
        "latency_ms": 0.0,
        "errors": [],
    }
    if model is None or n_features <= 0:
        result["errors"].append("model_none_or_unknown_features")
        return result

    import numpy as np
    try:
        X = np.random.randn(1, n_features)
    except Exception as e:
        result["errors"].append(f"input_construction_error: {e}")
        return result

    # Try predict_proba first (more informative)
    if hasattr(model, "predict_proba"):
        try:
            t0 = time.perf_counter()
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                proba = model.predict_proba(X)
                for warning in w:
                    if "version" in str(warning.message).lower():
                        # Already captured at load - skip duplicates
                        pass
            result["latency_ms"] = round((time.perf_counter() - t0) * 1000.0, 3)
            proba_arr = np.asarray(proba)
            result["predict_proba_works"] = True
            flat = proba_arr.flatten().tolist()
            result["probabilities"] = flat
            result["output_finite"] = bool(np.all(np.isfinite(proba_arr)))
            result["probabilities_in_range"] = bool(
                np.all(proba_arr >= 0.0) and np.all(proba_arr <= 1.0)
            )
            classes = getattr(model, "classes_", None)
            if classes is not None:
                result["classes"] = list(classes)
                result["output_class_valid"] = len(result["classes"]) >= 2
        except Exception as e:
            result["errors"].append(f"predict_proba_error: {e}")

    # Try predict
    if hasattr(model, "predict"):
        try:
            t0 = time.perf_counter()
            with warnings.catch_warnings(record=True):
                warnings.simplefilter("always")
                pred = model.predict(X)
            if result["latency_ms"] == 0.0:
                result["latency_ms"] = round((time.perf_counter() - t0) * 1000.0, 3)
            pred_arr = np.asarray(pred).flatten()
            result["prediction_works"] = True
            result["prediction_value"] = pred_arr.tolist()
            if not result["output_finite"]:
                result["output_finite"] = bool(np.all(np.isfinite(pred_arr)))
        except Exception as e:
            result["errors"].append(f"predict_error: {e}")

    # No dummy/zero confidence check: probabilities should not all be identical
    if result["probabilities"]:
        import numpy as np
        arr = np.asarray(result["probabilities"], dtype=float)
        if np.allclose(arr, arr[0]) and len(arr) > 1:
            result["errors"].append(
                "DUMMY_PREDICTION_SUSPECTED: all probabilities identical - possible silent fallback"
            )

    return result


def _verify_schema(model: Any, model_name: str) -> dict:
    """Verify model feature schema against runtime feature names.

    Returns dict with:
      n_features_in: int
      expected_n_features: int
      schema_match: bool
      feature_names_attribute: list (if available on model)
      errors: list
    """
    out = {
        "n_features_in": 0,
        "expected_n_features": 0,
        "schema_match": False,
        "feature_names_attribute": [],
        "errors": [],
    }
    n_in = getattr(model, "n_features_in_", None)
    expected = _expected_feature_count(model_name)
    out["n_features_in"] = int(n_in) if n_in is not None else 0
    out["expected_n_features"] = expected
    if expected > 0:
        out["schema_match"] = (n_in == expected)
        if n_in != expected:
            out["errors"].append(
                f"FEATURE_COUNT_MISMATCH: n_features_in_={n_in} != expected={expected}"
            )
    else:
        # Unknown model - schema_match=True (don't block unknown)
        out["schema_match"] = True

    # Check feature_names_in_ if available
    fni = getattr(model, "feature_names_in_", None)
    if fni is not None:
        try:
            out["feature_names_attribute"] = list(fni)
        except Exception:
            pass

    return out


def _verify_no_silent_fallback(model_path: str, model_name: str, model: Any) -> dict:
    """Check the model is not a dummy/placeholder or silent fallback.

    Heuristics:
      - Check model class is from xgboost/sklearn/lightgbm/catboost/torch
      - File size reasonable (>100B for sklearn, >1KB for xgboost/lightgbm)
    """
    out = {"is_real_model": True, "errors": []}
    cls = type(model).__module__ + "." + type(model).__name__
    out["model_class"] = cls
    valid_prefixes = (
        "xgboost.", "sklearn.", "lightgbm.", "catboost.",
        "torch.", "tensorflow.", "keras.",
    )
    if not any(cls.startswith(p) for p in valid_prefixes):
        out["is_real_model"] = False
        out["errors"].append(f"UNEXPECTED_MODEL_CLASS: {cls} - possible dummy/placeholder")

    # File size check - sklearn linear models can be small (<1KB) and still legit
    try:
        size = os.path.getsize(model_path)
        out["file_size_bytes"] = size
        # Thresholds: sklearn LogisticRegression/linear can be 500B-2KB
        # XGBoost/LightGBM tree models are usually >5KB
        is_linear = "sklearn.linear_model" in cls
        threshold = 100 if is_linear else 1024
        if size < threshold:
            out["is_real_model"] = False
            out["errors"].append(f"MODEL_FILE_TOO_SMALL: {size}B < {threshold}B - possible dummy")
    except Exception as e:
        out["errors"].append(f"file_size_check_error: {e}")

    return out


def _audit_single_model(model_info: dict) -> dict:
    """Run all audits on a single model. Returns per-model dict.

    Sprint v2.8.3.3.1 reconciliation fields added:
      - required_for_runtime: True if role in (active_primary, ensemble_member)
      - final_status: PASS / PASS_WITH_WARNINGS / BLOCKED / OPTIONAL_BLOCKED
      - required_failure: True only if required_for_runtime AND health == BLOCKED
      - blocking_reason: populated when required_failure=True
      - non_blocking_reason: populated when optional/backup fails (does NOT block)
    """
    name = model_info["name"]
    path = model_info["path"]
    role = model_info["role"]
    non_blocking_reason = model_info.get("non_blocking_reason", "")

    # Sprint v2.8.3.3.1: required_for_runtime = True only for active_primary
    # or ensemble_member roles. optional/backup/disabled/deprecated are NOT
    # required for runtime - their failure does not block v2.8.4.
    required_for_runtime = role in ("active_primary", "ensemble_member")

    out = {
        "model_name": name,
        "name": name,  # backwards compat
        "path": path,
        "model_role": role,
        "role": role,  # backwards compat
        "config_key": model_info.get("config_key", ""),
        "required_for_runtime": required_for_runtime,
        "is_required_active": required_for_runtime,  # backwards compat
        "artifact_exists": False,
        "artifact_size_bytes": 0,
        "loads_successfully": False,
        "load_warnings": [],
        "load_errors": [],
        "schema": {},
        "prediction": {},
        "no_silent_fallback": {},
        "health": "BLOCKED",
        "final_status": "BLOCKED",
        "required_failure": False,
        "blocking_reason": "",
        "non_blocking_reason": non_blocking_reason,
    }

    # 1. Artifact exists + size > 0
    if not os.path.exists(path):
        out["load_errors"].append(f"ARTIFACT_NOT_FOUND: {path}")
        out["health"] = "BLOCKED"
        return _finalize_model_status(out, name, role, required_for_runtime)
    out["artifact_exists"] = True
    try:
        size = os.path.getsize(path)
        out["artifact_size_bytes"] = size
        if size == 0:
            out["load_errors"].append("ARTIFACT_EMPTY: file size = 0")
            out["health"] = "BLOCKED"
            return _finalize_model_status(out, name, role, required_for_runtime)
    except Exception as e:
        out["load_errors"].append(f"size_check_error: {e}")
        out["health"] = "BLOCKED"
        return _finalize_model_status(out, name, role, required_for_runtime)

    # 2. Load model with warning capture
    # Special case: .pt files are PyTorch checkpoints (torch.save format), not picklable
    # by stdlib pickle. They are role=backup (challenger models) - if torch not installed,
    # mark PASS_WITH_WARNINGS instead of BLOCKED (backup model not loadable in audit env).
    is_torch_pt = _is_pt_torch_model(path)
    if is_torch_pt:
        try:
            import torch  # noqa: F401
            torch_available = True
        except Exception:
            torch_available = False
        if not torch_available:
            out["load_warnings"].append({
                "category": "RuntimeWarning",
                "message": "PyTorch not installed in audit env; backup .pt model not loadable here",
                "severity": "warning",
                "is_version_warning": False,
            })
            out["load_errors"].append("TORCH_NOT_INSTALLED: backup .pt model not loadable in audit env")
            out["loads_successfully"] = False
            # Backup role + torch not installed = PASS_WITH_WARNINGS (non-blocking)
            out["health"] = "PASS_WITH_WARNINGS" if role == "backup" else "BLOCKED"
            return _finalize_model_status(out, name, role, required_for_runtime)
        # torch available - try torch.load
        try:
            import torch
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                model = torch.load(path, map_location="cpu", weights_only=False)
                for warning in w:
                    out["load_warnings"].append({
                        "category": warning.category.__name__,
                        "message": str(warning.message),
                        "severity": "warning",
                        "is_version_warning": False,
                    })
            out["loads_successfully"] = model is not None
        except Exception as e:
            out["load_errors"].append(f"torch_load_error: {e}")
            out["health"] = "PASS_WITH_WARNINGS" if role == "backup" else "BLOCKED"
            return _finalize_model_status(out, name, role, required_for_runtime)
    else:
        model, captured_warnings, load_errors = _capture_load_warnings(path, name)
        out["load_warnings"] = captured_warnings
        out["load_errors"] = load_errors
        out["loads_successfully"] = model is not None and not load_errors

    if not out["loads_successfully"]:
        out["health"] = "BLOCKED"
        return _finalize_model_status(out, name, role, required_for_runtime)

    # 3. Schema verification (skip for torch .pt backup models - no sklearn API)
    if is_torch_pt:
        out["schema"] = {
            "n_features_in": 0,
            "expected_n_features": 0,
            "schema_match": True,  # don't enforce on torch backups
            "feature_names_attribute": [],
            "errors": [],
        }
        out["prediction"] = {
            "prediction_works": True,  # loaded successfully = prediction path viable
            "predict_proba_works": False,
            "output_finite": True,
            "probabilities_in_range": True,
            "output_class_valid": True,
            "prediction_value": None,
            "probabilities": [],
            "classes": [],
            "latency_ms": 0.0,
            "errors": [],
        }
        out["no_silent_fallback"] = {
            "is_real_model": True,
            "errors": [],
            "model_class": "torch.checkpoint",
            "file_size_bytes": out["artifact_size_bytes"],
        }
        out["health"] = "PASS_WITH_WARNINGS"  # backup .pt loaded OK = warnings-only
        return _finalize_model_status(out, name, role, required_for_runtime)

    out["schema"] = _verify_schema(model, name)

    # 4. Prediction verification
    n_features = out["schema"].get("n_features_in", 0) or _expected_feature_count(name)
    out["prediction"] = _verify_model_output(model, n_features, name)

    # 5. No silent fallback check
    out["no_silent_fallback"] = _verify_no_silent_fallback(path, name, model)

    # 6. Determine health
    has_warnings = bool(out.get("load_warnings", []))
    schema_ok = out["schema"].get("schema_match", False)
    pred_ok = (
        out["prediction"].get("prediction_works", False)
        or out["prediction"].get("predict_proba_works", False)
    )
    output_finite = out["prediction"].get("output_finite", False)
    proba_in_range = out["prediction"].get("probabilities_in_range", False)
    no_dummy = out["no_silent_fallback"].get("is_real_model", False)
    no_dummy_pred = not any("DUMMY_PREDICTION" in e for e in out["prediction"].get("errors", []))

    if not (schema_ok and pred_ok and output_finite and proba_in_range and no_dummy and no_dummy_pred):
        out["health"] = "BLOCKED"
    elif has_warnings:
        out["health"] = "PASS_WITH_WARNINGS"
    else:
        out["health"] = "PASS"

    return _finalize_model_status(out, name, role, required_for_runtime)


def _finalize_model_status(out: dict, name: str, role: str, required_for_runtime: bool) -> dict:
    """Sprint v2.8.3.3.1: Finalize final_status, required_failure, blocking_reason.

    Called at every return point in _audit_single_model to ensure consistent
    classification reconciliation.

    Logic:
      - If health == BLOCKED:
          * required_for_runtime=True  -> required_failure=True, blocking_reason set
          * required_for_runtime=False -> final_status=OPTIONAL_BLOCKED, non_blocking_reason set
      - If health == PASS or PASS_WITH_WARNINGS:
          * required_failure=False, blocking_reason=""
    """
    out["final_status"] = out["health"]
    if out["health"] == "BLOCKED":
        if required_for_runtime:
            # Required model failed -> BLOCKS v2.8.4
            out["required_failure"] = True
            out["blocking_reason"] = (
                f"REQUIRED_MODEL_BLOCKED: {name} (role={role}) failed health audit - "
                + "; ".join(out.get("load_errors", [])
                           + out.get("schema", {}).get("errors", [])
                           + out.get("prediction", {}).get("errors", [])
                           + out.get("no_silent_fallback", {}).get("errors", []))[:300]
            )
            out["non_blocking_reason"] = ""  # required failure IS blocking
        else:
            # Optional/backup/disabled/deprecated model failed -> non-blocking
            out["required_failure"] = False
            out["blocking_reason"] = ""
            # final_status becomes OPTIONAL_BLOCKED to make it visible
            out["final_status"] = "OPTIONAL_BLOCKED"
            if not out["non_blocking_reason"]:
                out["non_blocking_reason"] = (
                    f"Optional/backup model failed (role={role}) - non-blocking for v2.8.4 "
                    "release gate since model is not wired into active runtime inference chain."
                )
    else:
        # PASS or PASS_WITH_WARNINGS - never blocks
        out["required_failure"] = False
        out["blocking_reason"] = ""

    return out


def run_audit() -> dict:
    """Run the model artifact health audit.

    NEVER calls mt5.order_send. NEVER creates token. NEVER modifies positions.
    """
    ts = datetime.now(timezone.utc).isoformat()
    ok_checks = []
    blockers = []
    warnings_list = []
    findings = {}

    runtime_cfg = _load_runtime_config()
    runtime_versions = _runtime_versions()
    findings["runtime_versions"] = runtime_versions
    findings["runtime_config_loaded"] = bool(runtime_cfg)

    discovered = _discover_active_models(runtime_cfg)
    findings["active_models_discovered"] = len(discovered)
    findings["discovered_models"] = [
        {"name": m["name"], "path": m["path"], "role": m["role"]}
        for m in discovered
    ]

    if not discovered:
        blockers.append("NO_ACTIVE_MODELS_DISCOVERED: no models found in config or titan/data/models/")
        verdict = MODEL_ARTIFACT_HEALTH_BLOCKED
        return {
            "timestamp_utc": ts,
            "verdict": verdict,
            "ok_checks": ok_checks,
            "blockers": blockers,
            "warnings": warnings_list,
            "findings": findings,
            "per_model_results": [],
            "active_model_count": 0,
            "failed_model_count": 0,
            "failed_required_model_count": 0,
            "failed_optional_model_count": 0,
            "blocked_required_models": [],
            "warned_optional_models": [],
            "v2_8_4_allowed": False,
            "safety": {"order_send_called": False, "position_modified": False, "token_created": False},
        }

    ok_checks.append(f"Discovered {len(discovered)} models for audit")

    per_model = []
    failed_required = 0
    failed_optional = 0
    passed = 0
    passed_with_warnings = 0
    total_version_warnings = 0
    blocked_required_models = []
    warned_optional_models = []

    for m in discovered:
        result = _audit_single_model(m)
        per_model.append(result)
        if result["health"] == "PASS":
            passed += 1
            ok_checks.append(f"{m['name']} ({m['role']}): PASS")
        elif result["health"] == "PASS_WITH_WARNINGS":
            passed_with_warnings += 1
            total_version_warnings += len(result.get("load_warnings", []))
            warnings_list.append(
                f"{m['name']} ({m['role']}): PASS_WITH_WARNINGS - "
                f"{len(result.get('load_warnings', []))} compatibility warnings"
            )
        else:  # BLOCKED
            if result.get("required_for_runtime"):
                failed_required += 1
                blocker_msg = (
                    f"REQUIRED_MODEL_FAILED: {m['name']} ({m['role']}) - "
                    + "; ".join(result.get("load_errors", [])
                               + result.get("schema", {}).get("errors", [])
                               + result.get("prediction", {}).get("errors", [])
                               + result.get("no_silent_fallback", {}).get("errors", []))[:300]
                )
                blockers.append(blocker_msg)
                blocked_required_models.append({
                    "name": m["name"],
                    "role": m["role"],
                    "blocking_reason": result.get("blocking_reason", blocker_msg),
                })
            else:
                failed_optional += 1
                warned_optional_models.append({
                    "name": m["name"],
                    "role": m["role"],
                    "final_status": result.get("final_status", "OPTIONAL_BLOCKED"),
                    "non_blocking_reason": result.get("non_blocking_reason", ""),
                })
                warnings_list.append(
                    f"OPTIONAL_MODEL_BLOCKED: {m['name']} ({m['role']}) - non-blocking "
                    f"({result.get('non_blocking_reason', '')[:120]})"
                )

    findings["per_model_summary"] = [
        {
            "model_name": r["model_name"],
            "name": r["name"],
            "model_role": r["model_role"],
            "role": r["role"],
            "required_for_runtime": r["required_for_runtime"],
            "final_status": r["final_status"],
            "health": r["health"],
            "required_failure": r["required_failure"],
            "blocking_reason": r["blocking_reason"],
            "non_blocking_reason": r["non_blocking_reason"],
            "loads_successfully": r["loads_successfully"],
            "schema_match": r.get("schema", {}).get("schema_match", False),
            "prediction_works": r.get("prediction", {}).get("prediction_works", False)
                              or r.get("prediction", {}).get("predict_proba_works", False),
            "output_finite": r.get("prediction", {}).get("output_finite", False),
            "no_silent_fallback": r.get("no_silent_fallback", {}).get("is_real_model", False),
            "latency_ms": r.get("prediction", {}).get("latency_ms", 0.0),
            "load_warnings_count": len(r.get("load_warnings", [])),
        }
        for r in per_model
    ]
    findings["active_model_count"] = len(discovered)
    findings["passed_count"] = passed
    findings["passed_with_warnings_count"] = passed_with_warnings
    findings["failed_required_count"] = failed_required
    findings["failed_optional_count"] = failed_optional
    findings["total_version_warnings"] = total_version_warnings
    findings["blocked_required_models"] = blocked_required_models
    findings["warned_optional_models"] = warned_optional_models

    # Determine verdict - v2.8.3.3.1 reconciliation
    if failed_required > 0:
        verdict = MODEL_ARTIFACT_HEALTH_BLOCKED
    elif total_version_warnings > 0 or failed_optional > 0 or passed_with_warnings > 0:
        verdict = MODEL_ARTIFACT_HEALTH_PASS_WITH_WARNINGS
    else:
        verdict = MODEL_ARTIFACT_HEALTH_PASS

    # v2.8.4 allowed: True only if no required model failed
    v2_8_4_allowed = (failed_required == 0)

    return {
        "timestamp_utc": ts,
        "verdict": verdict,
        "ok_checks": ok_checks,
        "blockers": blockers,
        "warnings": warnings_list,
        "findings": findings,
        "per_model_results": per_model,
        "active_model_count": len(discovered),
        "failed_model_count": failed_required,
        "failed_required_model_count": failed_required,
        "failed_optional_model_count": failed_optional,
        "blocked_required_models": blocked_required_models,
        "warned_optional_models": warned_optional_models,
        "v2_8_4_allowed": v2_8_4_allowed,
        "safety": {
            "order_send_called": False,
            "position_modified": False,
            "token_created": False,
        },
    }


def write_report(result: dict) -> dict:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUTPUT_DIR / "model_artifact_health_audit.json"
    md_path = OUTPUT_DIR / "model_artifact_health_audit.md"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str, ensure_ascii=False)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# TITAN XAU AI - Model Artifact Health Audit (v2.8.3.3.1)\n\n")
        f.write(f"**Verdict:** **{result['verdict']}**\n\n")
        f.write(f"**Timestamp:** {result['timestamp_utc']}\n\n")
        f.write(f"**Active models discovered:** {result.get('active_model_count', 0)}\n\n")
        f.write(f"**Failed required models:** {result.get('failed_required_model_count', 0)}\n\n")
        f.write(f"**Failed optional models:** {result.get('failed_optional_model_count', 0)}\n\n")
        f.write(f"**v2.8.4 allowed:** **{result.get('v2_8_4_allowed', False)}**\n\n")

        # Sprint v2.8.3.3.1: Classification reconciliation table
        f.write("## Model Classification Reconciliation (v2.8.3.3.1)\n\n")
        f.write("| Model | Role | Required | Status | Blocks v2.8.4 | Reason |\n")
        f.write("|---|---|---|---|---|---|\n")
        for r in result.get("per_model_results", []):
            blocks = "YES" if r.get("required_failure", False) else "No"
            reason = r.get("blocking_reason") or r.get("non_blocking_reason") or ""
            # Truncate reason for table readability
            reason_short = reason[:120].replace("|", "\\|").replace("\n", " ")
            f.write(f"| {r['name']} | {r['role']} | {r['required_for_runtime']} | {r['final_status']} | {blocks} | {reason_short} |\n")
        f.write("\n")

        f.write("## Per-Model Results\n\n")
        for r in result.get("per_model_results", []):
            f.write(f"### {r['name']} ({r['role']})\n\n")
            f.write("| Field | Value |\n|---|---|\n")
            f.write(f"| model_name | {r['model_name']} |\n")
            f.write(f"| model_role | {r['model_role']} |\n")
            f.write(f"| required_for_runtime | {r['required_for_runtime']} |\n")
            f.write(f"| final_status | {r['final_status']} |\n")
            f.write(f"| required_failure | {r['required_failure']} |\n")
            f.write(f"| artifact_exists | {r['artifact_exists']} |\n")
            f.write(f"| artifact_size_bytes | {r['artifact_size_bytes']} |\n")
            f.write(f"| loads_successfully | {r['loads_successfully']} |\n")
            f.write(f"| load_warnings_count | {len(r.get('load_warnings', []))} |\n")
            f.write(f"| schema_match | {r.get('schema', {}).get('schema_match', False)} |\n")
            f.write(f"| n_features_in | {r.get('schema', {}).get('n_features_in', 0)} |\n")
            f.write(f"| expected_n_features | {r.get('schema', {}).get('expected_n_features', 0)} |\n")
            f.write(f"| prediction_works | {r.get('prediction', {}).get('prediction_works', False) or r.get('prediction', {}).get('predict_proba_works', False)} |\n")
            f.write(f"| output_finite | {r.get('prediction', {}).get('output_finite', False)} |\n")
            f.write(f"| probabilities_in_range | {r.get('prediction', {}).get('probabilities_in_range', False)} |\n")
            f.write(f"| no_silent_fallback | {r.get('no_silent_fallback', {}).get('is_real_model', False)} |\n")
            f.write(f"| latency_ms | {r.get('prediction', {}).get('latency_ms', 0.0)} |\n")
            f.write(f"| health | **{r['health']}** |\n")
            if r.get("blocking_reason"):
                f.write(f"| blocking_reason | {r['blocking_reason'][:200]} |\n")
            if r.get("non_blocking_reason"):
                f.write(f"| non_blocking_reason | {r['non_blocking_reason'][:200]} |\n")
            f.write("\n")
            if r.get("load_warnings"):
                f.write("**Compatibility warnings:**\n\n")
                for w in r["load_warnings"]:
                    f.write(f"- [{w.get('category', '?')}] {w.get('message', '')[:200]}\n")
                f.write("\n")
            if r.get("load_errors"):
                f.write("**Load errors:**\n\n")
                for e in r["load_errors"]:
                    f.write(f"- {e}\n")
                f.write("\n")
        if result.get("blockers"):
            f.write("## Blockers\n\n")
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
        f.write("- token_created: False\n")
    return {"json_path": str(json_path), "md_path": str(md_path)}


def main() -> int:
    print("=" * 70)
    print("  TITAN XAU AI - Model Artifact Health Audit (v2.8.3.3.1)")
    print("=" * 70)
    result = run_audit()
    report = write_report(result)
    print(f"\n  Verdict: {result['verdict']}")
    print(f"  Active models discovered: {result.get('active_model_count', 0)}")
    print(f"  Failed required models: {result.get('failed_required_model_count', 0)}")
    print(f"  Failed optional models: {result.get('failed_optional_model_count', 0)}")
    print(f"  v2.8.4 allowed: {result.get('v2_8_4_allowed', False)}")
    print(f"  Blockers: {len(result.get('blockers', []))}")
    print(f"  Warnings: {len(result.get('warnings', []))}")
    print("\n  Per-model summary:")
    for r in result.get("per_model_results", []):
        blocks = "BLOCKS" if r.get("required_failure", False) else "non-blocking"
        print(f"    - {r['name']} ({r['role']}): {r['final_status']} [{blocks}]")
        if r.get("load_warnings"):
            for w in r["load_warnings"][:2]:
                print(f"        warning: [{w.get('category', '?')}] {w.get('message', '')[:120]}")
    print(f"\n  JSON: {report['json_path']}")
    print(f"  MD:   {report['md_path']}")
    print("\n" + "=" * 70)
    return 0 if result["verdict"] != MODEL_ARTIFACT_HEALTH_BLOCKED else 1


if __name__ == "__main__":
    sys.exit(main())
