#!/usr/bin/env python3
"""TITAN XAU AI — v2.8.7-P2.5.3 Baseline Registry Builder
==========================================================

Loads every fold artifact, recomputes hashes, and creates an immutable
baseline registry. All values come from committed artifacts — nothing
is manually typed.

NEVER sends orders. NEVER creates tokens. NEVER trades.
"""
from __future__ import annotations
import sys, json, hashlib, pickle
from pathlib import Path
from datetime import datetime, timezone

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

ARTIFACTS_DIR = REPO_ROOT / "data/artifacts/p2_5_1"
REGISTRY_PATH = REPO_ROOT / "data/artifacts/p2_5_3/baseline_registry.json"


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def main():
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)

    registry = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "artifact_base": "data/artifacts/p2_5_1",
        "folds": [],
    }

    for fold_dir in sorted(ARTIFACTS_DIR.glob("fold_*")):
        fold_num = int(fold_dir.name.split("_")[1])
        prov_path = fold_dir / "provenance.json"
        if not prov_path.exists():
            continue

        with open(prov_path) as f:
            prov = json.load(f)

        # Recompute actual hashes from files
        alpha_path = fold_dir / "alpha_model.pkl"
        meta_path = fold_dir / "meta_model.pkl"
        scaler_path = fold_dir / "scaler.json"

        actual_alpha_hash = sha256_file(alpha_path) if alpha_path.exists() else ""
        actual_meta_hash = sha256_file(meta_path) if meta_path.exists() else ""
        actual_scaler_hash = sha256_file(scaler_path) if scaler_path.exists() else ""
        prov_hash = sha256_file(prov_path)

        # Verify hashes match provenance
        alpha_match = actual_alpha_hash == prov.get("alpha_model_hash", "")
        meta_match = actual_meta_hash == prov.get("meta_model_hash", "")
        scaler_match = actual_scaler_hash == prov.get("scaler_hash", "")

        # Load models to verify class and params
        alpha_class = ""
        alpha_params = {}
        meta_class = ""
        meta_params = {}
        if alpha_path.exists():
            with open(alpha_path, "rb") as f:
                alpha_model = pickle.load(f)
            alpha_class = type(alpha_model).__name__
            alpha_params = {k: v for k, v in alpha_model.get_params().items()
                            if v is None or isinstance(v, (int, float, str, bool))}
        if meta_path.exists():
            with open(meta_path, "rb") as f:
                meta_model = pickle.load(f)
            meta_class = type(meta_model).__name__
            meta_params = {k: v for k, v in meta_model.get_params().items()
                           if v is None or isinstance(v, (int, float, str, bool))}

        fold_entry = {
            "fold": fold_num,
            "artifact_directory": str(fold_dir.relative_to(REPO_ROOT)),
            "scaler_hash": actual_scaler_hash,
            "alpha_model_hash": actual_alpha_hash,
            "meta_model_hash": actual_meta_hash,
            "alpha_calibrator_hash": prov.get("alpha_calibrator_hash", ""),
            "meta_calibrator_hash": prov.get("meta_calibrator_hash", ""),
            "provenance_hash": prov_hash,
            "training_start": prov.get("training_start", ""),
            "training_end": prov.get("training_end", ""),
            "validation_start": prov.get("val_start", ""),
            "validation_end": prov.get("val_end", ""),
            "calibration_start": prov.get("calibration_start", ""),
            "calibration_end": prov.get("calibration_end", ""),
            "oos_start": prov.get("oos_start", ""),
            "oos_end": prov.get("oos_end", ""),
            "alpha_model_class": alpha_class,
            "alpha_model_params": alpha_params,
            "meta_model_class": meta_class,
            "meta_model_params": meta_params,
            "hash_verification": {
                "alpha_match": alpha_match,
                "meta_match": meta_match,
                "scaler_match": scaler_match,
            },
            "source_commit": prov.get("git_commit", ""),
        }
        registry["folds"].append(fold_entry)

    # Verify all alpha hashes are unique
    alpha_hashes = [f["alpha_model_hash"] for f in registry["folds"]]
    meta_hashes = [f["meta_model_hash"] for f in registry["folds"]]
    registry["all_alpha_hashes_unique"] = len(set(alpha_hashes)) == len(alpha_hashes)
    registry["all_meta_hashes_unique"] = len(set(meta_hashes)) == len(meta_hashes)

    # Verify all OOS before 2026
    registry["all_oos_before_2026"] = all(
        f["oos_end"] < "2026-01-01" for f in registry["folds"]
    )

    # Verify all hashes match
    registry["all_hashes_match"] = all(
        f["hash_verification"]["alpha_match"] and
        f["hash_verification"]["meta_match"] and
        f["hash_verification"]["scaler_match"]
        for f in registry["folds"]
    )

    with open(REGISTRY_PATH, "w") as f:
        json.dump(registry, f, indent=2, default=str)

    print(f"Baseline registry written to {REGISTRY_PATH}")
    print(f"Folds: {len(registry['folds'])}")
    print(f"All alpha hashes unique: {registry['all_alpha_hashes_unique']}")
    print(f"All meta hashes unique: {registry['all_meta_hashes_unique']}")
    print(f"All OOS before 2026: {registry['all_oos_before_2026']}")
    print(f"All hashes match: {registry['all_hashes_match']}")

    if not registry["all_hashes_match"]:
        print("WARNING: Hash mismatch detected!")
        for f in registry["folds"]:
            if not f["hash_verification"]["alpha_match"]:
                print(f"  Fold {f['fold']}: alpha hash mismatch")
            if not f["hash_verification"]["meta_match"]:
                print(f"  Fold {f['fold']}: meta hash mismatch")


if __name__ == "__main__":
    main()
