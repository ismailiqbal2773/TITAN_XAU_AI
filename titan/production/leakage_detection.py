"""TITAN XAU AI — OOS Leakage Detection (v2.8.7-P2.3)
=====================================================

Detects whether the frozen model was trained on data that overlaps with
walk-forward OOS periods. If leakage is detected, the evaluation must
return OOS_LEAKAGE_DETECTED.

The model file `xgboost_v2_feature_normalized.pkl` has mtime 2026-07-11.
The canonical H1 dataset spans 2020-01-02 to 2026-06-19.
Fold 1 OOS starts at 2021-08-18.

Since the model was trained AFTER the full dataset was collected (including
all OOS periods), there IS leakage. This module detects and reports it.

NEVER sends orders. NEVER creates tokens. NEVER trades.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime, timezone
import json
import hashlib

REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass
class LeakageAssessment:
    """Result of OOS leakage assessment."""
    leakage_detected: bool
    reason: str
    model_mtime_utc: str
    dataset_end_date: str
    fold1_oos_start_date: str
    model_trained_before_fold1_oos: bool
    retraining_prohibited: bool
    immutable_manifest_path: str | None = None


def assess_oos_leakage(
    model_path: Path,
    dataset_end_date: str,
    fold1_oos_start_date: str,
) -> LeakageAssessment:
    """Assess whether the frozen model has OOS leakage.

    Leakage is detected if:
      1. The model's file mtime is AFTER fold1_oos_start_date, AND
      2. The dataset includes data from or after fold1_oos_start_date, AND
      3. No immutable manifest proves the model was trained before fold1_oos_start_date.

    For the current frozen model:
      - model mtime: 2026-07-11 (well after fold1 OOS start 2021-08-18)
      - dataset end: 2026-06-19 (includes all fold OOS periods)
      - No immutable training manifest exists
      → LEAKAGE DETECTED
    """
    model_mtime = datetime.fromtimestamp(model_path.stat().st_mtime, tz=timezone.utc)
    model_mtime_str = model_mtime.isoformat()

    # Parse dates for comparison
    fold1_oos_start = datetime.fromisoformat(fold1_oos_start_date.replace("Z", "+00:00"))
    if fold1_oos_start.tzinfo is None:
        fold1_oos_start = fold1_oos_start.replace(tzinfo=timezone.utc)

    model_trained_before_fold1_oos = model_mtime < fold1_oos_start

    # Check for immutable training manifest
    manifest_path = REPO_ROOT / "data" / "manifests" / "model_training_manifest.json"
    has_manifest = manifest_path.exists()

    # Leakage detection
    if model_trained_before_fold1_oos:
        leakage_detected = False
        reason = "Model mtime is before Fold 1 OOS start — no leakage"
    elif has_manifest:
        # Check manifest
        with open(manifest_path) as f:
            manifest = json.load(f)
        manifest_training_end = manifest.get("training_end_date", "")
        manifest_model_hash = manifest.get("model_sha256", "")
        actual_model_hash = _sha256_file(model_path)
        if manifest_model_hash == actual_model_hash:
            manifest_date = datetime.fromisoformat(manifest_training_end.replace("Z", "+00:00"))
            if manifest_date.tzinfo is None:
                manifest_date = manifest_date.replace(tzinfo=timezone.utc)
            if manifest_date < fold1_oos_start:
                leakage_detected = False
                reason = "Immutable training manifest proves model was trained before Fold 1 OOS"
            else:
                leakage_detected = True
                reason = "Manifest training end date is after Fold 1 OOS start — leakage"
        else:
            leakage_detected = True
            reason = "Manifest model hash does not match actual model hash — cannot prove no leakage"
    else:
        leakage_detected = True
        reason = (
            f"Model mtime ({model_mtime_str}) is after Fold 1 OOS start "
            f"({fold1_oos_start_date}) and no immutable training manifest exists. "
            f"The model was trained on the full dataset which includes OOS periods. "
            f"This is OOS leakage."
        )

    return LeakageAssessment(
        leakage_detected=leakage_detected,
        reason=reason,
        model_mtime_utc=model_mtime_str,
        dataset_end_date=dataset_end_date,
        fold1_oos_start_date=fold1_oos_start_date,
        model_trained_before_fold1_oos=model_trained_before_fold1_oos,
        retraining_prohibited=True,
        immutable_manifest_path=str(manifest_path) if has_manifest else None,
    )


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


__all__ = ["LeakageAssessment", "assess_oos_leakage"]
