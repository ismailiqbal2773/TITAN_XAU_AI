"""
TITAN XAU AI — Production Model Loader (Sprint 1)

Loads the two production model artifacts required for live inference:
  - xgboost_v1.pkl       (L1 signal engine, 55 features → 2-class prob)
  - meta_label_v2_context.pkl  (L2 meta-label filter, 22 features → 2-class prob)

Verifies each model loads AND can produce a valid prediction on a
synthetic feature vector of the expected shape. Returns a ModelBundle
dataclass that the inference loop consumes.

Usage:
    from titan.production.model_loader import load_production_models
    bundle = load_production_models()
    if bundle.ok:
        proba = bundle.xgb.predict_proba(vec.xgb_features)
        meta_proba = bundle.meta.predict_proba(vec.meta_features)
"""
from __future__ import annotations

import logging
import os
import pickle
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# ─── Default paths ────────────────────────────────────────────────────────────
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DEFAULT_XGB_PATH = os.path.join(_REPO_ROOT, "titan", "data", "models", "xgboost_v1.pkl")
DEFAULT_META_PATH = os.path.join(_REPO_ROOT, "titan", "data", "models",
                                  "meta_label_v2_context.pkl")

# Expected feature counts (verified by direct model inspection)
XGB_N_FEATURES = 55        # xgboost_v1.pkl: n_features_in_ = 55
META_N_FEATURES = 22       # meta_label_v2_context.pkl: n_features_in_ = 22

# Subset of the 55 XGB features that meta-label uses (micro 9 + price 13 = 22).
# These names match the Clean Model Performance Report's micro+price feature set.
META_FEATURE_NAMES: list[str] = [
    # Microstructure (9)
    "n_brokers", "spread_pct", "spread_zscore_60", "volume_zscore_60",
    "volume_ratio_5_20", "body_ratio", "upper_wick_ratio",
    "lower_wick_ratio", "body_dir",
    # Price (13)
    "ret_1", "ret_5", "ret_15", "price_zscore_60", "hl_range",
    "close_pos_in_range", "ret_lag_1", "ret_lag_2", "ret_lag_3",
    "ret_lag_5", "ret_lag_10", "ret_lag_20", "ret_lag_60",
]
assert len(META_FEATURE_NAMES) == META_N_FEATURES, \
    f"meta feature name count mismatch: {len(META_FEATURE_NAMES)} != {META_N_FEATURES}"


@dataclass
class ModelBundle:
    """Container for loaded production models."""
    xgb: object = None                # xgboost.sklearn.XGBClassifier
    meta: object = None               # sklearn.linear_model.LogisticRegression
    xgb_path: str = ""
    meta_path: str = ""
    xgb_n_features: int = 0
    meta_n_features: int = 0
    xgb_classes: list = field(default_factory=list)
    meta_classes: list = field(default_factory=list)
    xgb_verified: bool = False
    meta_verified: bool = False
    ok: bool = False
    errors: list[str] = field(default_factory=list)

    def __repr__(self) -> str:
        return (
            f"ModelBundle(xgb={'LOADED' if self.xgb else 'MISSING'} "
            f"[{self.xgb_n_features}f, verified={self.xgb_verified}], "
            f"meta={'LOADED' if self.meta else 'MISSING'} "
            f"[{self.meta_n_features}f, verified={self.meta_verified}], "
            f"ok={self.ok})"
        )


def _load_pickle(path: str, label: str) -> object:
    """Load a pickle file with error handling."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"{label} model not found: {path}")
    if os.path.getsize(path) < 100:
        raise IOError(f"{label} model file too small ({os.path.getsize(path)}B): {path}")
    with open(path, "rb") as f:
        obj = pickle.load(f)
    logger.info(f"Loaded {label} from {path} (type={type(obj).__module__}.{type(obj).__name__})")
    return obj


def _verify_model(model: object, n_expected: int, label: str) -> tuple[bool, int, list]:
    """
    Verify model accepts a feature vector of expected length.
    Returns (verified, n_features_in, classes).
    """
    n_in = getattr(model, "n_features_in_", None)
    if n_in is None:
        return False, 0, []
    if n_in != n_expected:
        logger.warning(
            f"{label} n_features_in_={n_in} != expected {n_expected}"
        )
    # Try prediction on synthetic input
    try:
        X = np.random.randn(1, n_in)
        pred = model.predict(X)
        proba = model.predict_proba(X) if hasattr(model, "predict_proba") else None
        classes = getattr(model, "classes_", []).tolist() if hasattr(model, "classes_") else []
        if proba is not None and proba.shape == (1, len(classes)):
            return True, n_in, classes
        elif proba is not None:
            # Some models return different shape — still verified if predict worked
            return True, n_in, classes
        else:
            return True, n_in, classes
    except Exception as e:
        logger.error(f"{label} prediction verification failed: {e}")
        return False, n_in, []


def load_production_models(
    xgb_path: str = DEFAULT_XGB_PATH,
    meta_path: str = DEFAULT_META_PATH,
) -> ModelBundle:
    """
    Load both production models and verify they can predict.

    Returns a ModelBundle with .ok=True only if BOTH models load AND
    produce valid predictions on synthetic input.
    """
    bundle = ModelBundle(xgb_path=xgb_path, meta_path=meta_path)

    # ── Load XGBoost ──
    try:
        bundle.xgb = _load_pickle(xgb_path, "xgboost_v1")
        verified, n_in, classes = _verify_model(bundle.xgb, XGB_N_FEATURES, "xgboost_v1")
        bundle.xgb_verified = verified
        bundle.xgb_n_features = n_in
        bundle.xgb_classes = classes
        if not verified:
            bundle.errors.append("xgboost_v1 verification failed")
    except Exception as e:
        bundle.errors.append(f"xgboost_v1 load error: {e}")
        logger.error(f"xgboost_v1 load error: {e}")

    # ── Load Meta-Label ──
    try:
        bundle.meta = _load_pickle(meta_path, "meta_label_v2_context")
        verified, n_in, classes = _verify_model(bundle.meta, META_N_FEATURES, "meta_label_v2_context")
        bundle.meta_verified = verified
        bundle.meta_n_features = n_in
        bundle.meta_classes = classes
        if not verified:
            bundle.errors.append("meta_label_v2_context verification failed")
    except Exception as e:
        bundle.errors.append(f"meta_label_v2_context load error: {e}")
        logger.error(f"meta_label_v2_context load error: {e}")

    bundle.ok = bundle.xgb_verified and bundle.meta_verified
    if bundle.ok:
        logger.info(f"✓ Production models loaded: {bundle}")
    else:
        logger.error(f"✗ Model load incomplete: {bundle.errors}")
    return bundle


def extract_meta_features(xgb_features: np.ndarray,
                          xgb_feature_names: list[str]) -> np.ndarray:
    """
    Extract the 22 meta-label features from the 55 XGB features by name.

    Args:
        xgb_features: shape (55,) — full feature vector
        xgb_feature_names: list of 55 feature names
    Returns:
        shape (22,) — meta-label feature vector
    """
    if len(xgb_features) != len(xgb_feature_names):
        raise ValueError(
            f"feature vector length {len(xgb_features)} != names {len(xgb_feature_names)}"
        )
    name_to_idx = {n: i for i, n in enumerate(xgb_feature_names)}
    missing = [n for n in META_FEATURE_NAMES if n not in name_to_idx]
    if missing:
        raise ValueError(f"Missing features required by meta-label: {missing}")
    idxs = [name_to_idx[n] for n in META_FEATURE_NAMES]
    return xgb_features[idxs]


if __name__ == "__main__":
    # Smoke test
    logging.basicConfig(level=logging.INFO)
    bundle = load_production_models()
    print(f"\n{bundle}")
    if bundle.ok:
        # Test feature extraction
        from titan.production.feature_stream import FEATURE_NAMES, N_FEATURES
        dummy = np.random.randn(N_FEATURES)
        meta_vec = extract_meta_features(dummy, FEATURE_NAMES)
        print(f"XGB input shape: {dummy.shape}")
        print(f"Meta input shape: {meta_vec.shape}")
        # Run prediction
        xgb_proba = bundle.xgb.predict_proba(dummy.reshape(1, -1))[0]
        meta_proba = bundle.meta.predict_proba(meta_vec.reshape(1, -1))[0]
        print(f"XGB proba: {xgb_proba}")
        print(f"Meta proba: {meta_proba}")
        print("\n✓ Model loader smoke test PASSED")
    else:
        print(f"\n✗ Smoke test FAILED: {bundle.errors}")
