"""
Tests for titan/production/ Sprint 1 modules:
  - feature_stream.H1FeatureStream
  - model_loader.load_production_models
  - inference.InferenceEngine
"""
from __future__ import annotations

import os
import numpy as np
import pandas as pd
import pytest

from titan.production.feature_stream import (
    H1FeatureStream, FeatureVector, N_FEATURES, FEATURE_NAMES,
    MIN_BARS_FOR_FULL_FEATURES,
)
from titan.production.model_loader import (
    load_production_models, extract_meta_features, META_FEATURE_NAMES,
    ModelBundle, XGB_N_FEATURES, META_N_FEATURES,
)
from titan.production.inference import (
    InferenceEngine, Signal, Direction, XGB_PROB_THRESHOLD, META_PROB_THRESHOLD,
)

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


# ─── feature_stream.py ───────────────────────────────────────────────────────

class TestFeatureStream:
    def test_feature_count_matches_xgb(self):
        assert N_FEATURES == 55
        assert len(FEATURE_NAMES) == 55

    def test_window_too_small_raises(self):
        with pytest.raises(ValueError, match="window must be"):
            H1FeatureStream(window=100)

    def test_load_canonical(self):
        fs = H1FeatureStream(window=300)
        n = fs.load_canonical()
        assert n == 300, f"expected 300 bars, got {n}"

    def test_latest_vector_shape(self):
        fs = H1FeatureStream(window=300)
        vec = fs.latest_vector(source="canonical")
        assert vec.is_valid, f"vector invalid: {vec.error}"
        assert vec.features.shape == (55,), f"shape={vec.features.shape}"
        assert vec.feature_names == FEATURE_NAMES
        assert vec.source == "canonical"
        assert vec.n_bars_used == 300

    def test_no_nan_no_inf(self):
        fs = H1FeatureStream(window=300)
        vec = fs.latest_vector(source="canonical")
        assert not np.isnan(vec.features).any(), "NaN in features"
        assert not np.isinf(vec.features).any(), "Inf in features"

    def test_push_single_bar(self):
        fs = H1FeatureStream(window=300)
        fs.load_canonical()
        # Push a synthetic new bar
        last_ts = fs._bars.index[-1]
        new_ts = last_ts + pd.Timedelta(hours=1)
        fs.push_bar({
            "timestamp": new_ts,
            "open": 2000.0, "high": 2001.0, "low": 1999.0,
            "close": 2000.5, "volume": 1000, "spread": 0.2,
        })
        assert fs._bars.index[-1] == new_ts
        assert len(fs._bars) == 300  # window trimmed

    def test_invalid_source_raises(self):
        fs = H1FeatureStream(window=300)
        vec = fs.latest_vector(source="invalid_source")
        assert not vec.is_valid
        assert "Unknown source" in vec.error

    def test_window_constant(self):
        fs = H1FeatureStream(window=300)
        fs.load_canonical()
        # Push 50 more bars; window should stay at 300
        for i in range(50):
            fs.push_bar({
                "timestamp": pd.Timestamp.utcnow() + pd.Timedelta(hours=i),
                "open": 2000, "high": 2001, "low": 1999,
                "close": 2000, "volume": 1000, "spread": 0.2,
            })
        assert len(fs._bars) == 300


# ─── model_loader.py ─────────────────────────────────────────────────────────

class TestModelLoader:
    def test_bundle_loads_both_models(self):
        bundle = load_production_models()
        assert bundle.xgb is not None, "xgb model not loaded"
        assert bundle.meta is not None, "meta model not loaded"

    def test_xgb_feature_count(self):
        bundle = load_production_models()
        assert bundle.xgb_n_features == XGB_N_FEATURES == 55

    def test_meta_feature_count(self):
        bundle = load_production_models()
        assert bundle.meta_n_features == META_N_FEATURES == 22

    def test_xgb_verified(self):
        bundle = load_production_models()
        assert bundle.xgb_verified, "xgb verification failed"

    def test_meta_verified(self):
        bundle = load_production_models()
        assert bundle.meta_verified, "meta verification failed"

    def test_bundle_ok(self):
        bundle = load_production_models()
        assert bundle.ok, f"bundle not ok: {bundle.errors}"

    def test_predict_proba_works(self):
        bundle = load_production_models()
        x = np.random.randn(1, 55)
        proba = bundle.xgb.predict_proba(x)[0]
        assert proba.shape == (2,)
        assert abs(proba.sum() - 1.0) < 1e-6, "proba don't sum to 1"

    def test_meta_predict_proba_works(self):
        bundle = load_production_models()
        x = np.random.randn(1, 22)
        proba = bundle.meta.predict_proba(x)[0]
        assert proba.shape == (2,)
        assert abs(proba.sum() - 1.0) < 1e-6

    def test_extract_meta_features_shape(self):
        full_vec = np.random.randn(55)
        meta_vec = extract_meta_features(full_vec, FEATURE_NAMES)
        assert meta_vec.shape == (22,)

    def test_extract_meta_features_missing_raises(self):
        full_vec = np.random.randn(55)
        bad_names = FEATURE_NAMES[:-1] + ["nonexistent_feature"]
        with pytest.raises(ValueError, match="Missing features"):
            extract_meta_features(full_vec, bad_names)

    def test_meta_feature_names_count(self):
        assert len(META_FEATURE_NAMES) == 22
        # All must be in FEATURE_NAMES
        for n in META_FEATURE_NAMES:
            assert n in FEATURE_NAMES, f"meta feature '{n}' not in XGB features"

    def test_missing_xgb_path(self):
        bundle = load_production_models(xgb_path="/nonexistent/xgb.pkl")
        assert not bundle.xgb_verified
        assert any("xgboost_v1 load error" in e for e in bundle.errors)

    def test_missing_meta_path(self):
        bundle = load_production_models(meta_path="/nonexistent/meta.pkl")
        assert not bundle.meta_verified
        assert any("meta_label_v2_context load error" in e for e in bundle.errors)


# ─── inference.py ────────────────────────────────────────────────────────────

class TestInferenceEngine:
    def test_engine_initializes(self):
        engine = InferenceEngine()
        assert engine.bundle.ok

    def test_status_dict(self):
        engine = InferenceEngine()
        s = engine.status()
        assert s["models_ok"] is True
        assert s["xgb_n_features"] == 55
        assert s["meta_n_features"] == 22
        assert s["xgb_threshold"] == XGB_PROB_THRESHOLD
        assert s["meta_threshold"] == META_PROB_THRESHOLD

    def test_generate_returns_signal(self):
        engine = InferenceEngine()
        sig = engine.generate(source="canonical")
        assert isinstance(sig, Signal)
        assert isinstance(sig.direction, Direction)
        assert 0.0 <= sig.confidence <= 1.0
        assert 0.0 <= sig.meta_confidence <= 1.0
        assert len(sig.xgb_proba) == 2
        assert len(sig.meta_proba) == 2
        assert sig.feature_vector is not None
        assert sig.feature_vector.shape == (55,)
        assert sig.inference_ms > 0
        assert sig.source == "canonical"

    def test_generate_stable_across_iterations(self):
        """Same input should produce same output (deterministic)."""
        engine = InferenceEngine()
        s1 = engine.generate(source="canonical")
        s2 = engine.generate(source="canonical")
        assert s1.direction == s2.direction
        assert abs(s1.confidence - s2.confidence) < 1e-9
        assert abs(s1.meta_confidence - s2.meta_confidence) < 1e-9

    def test_proba_sums_to_one(self):
        engine = InferenceEngine()
        sig = engine.generate(source="canonical")
        assert abs(sum(sig.xgb_proba) - 1.0) < 1e-6
        assert abs(sum(sig.meta_proba) - 1.0) < 1e-6

    def test_reject_reason_when_flat(self):
        engine = InferenceEngine()
        sig = engine.generate(source="canonical")
        if sig.direction == Direction.FLAT:
            assert sig.reject_reason is not None
            assert "threshold" in sig.reject_reason
            assert not sig.is_tradeable

    def test_tradeable_signal_passes_both_thresholds(self):
        """If signal is tradeable, both XGB and meta thresholds were passed."""
        engine = InferenceEngine()
        sig = engine.generate(source="canonical")
        if sig.is_tradeable:
            assert sig.confidence >= engine.xgb_threshold
            assert sig.meta_confidence >= engine.meta_threshold
            assert sig.direction in (Direction.LONG, Direction.SHORT)
            assert sig.reject_reason is None

    def test_warmup_canonical(self):
        engine = InferenceEngine()
        n = engine.warmup(source="canonical")
        assert n == 300

    def test_invalid_source_returns_invalid_signal(self):
        engine = InferenceEngine()
        sig = engine.generate(source="invalid")
        assert sig.direction == Direction.FLAT
        assert not sig.is_tradeable
        assert sig.reject_reason is not None
        assert "feature_error" in sig.reject_reason

    def test_inference_latency_under_500ms(self):
        """Inference should complete in < 500ms (Phase F-Prime signal_to_broker_budget)."""
        engine = InferenceEngine()
        # Warm up
        engine.generate(source="canonical")
        # Measure
        sig = engine.generate(source="canonical")
        assert sig.inference_ms < 500, f"latency {sig.inference_ms:.1f}ms exceeds 500ms"

    def test_custom_thresholds(self):
        engine = InferenceEngine(xgb_threshold=0.30, meta_threshold=0.30)
        assert engine.xgb_threshold == 0.30
        assert engine.meta_threshold == 0.30


# ─── Integration: feature_stream → model_loader → inference ──────────────────

class TestIntegration:
    def test_end_to_end_chain(self):
        """Full pipeline: canonical bars → features → XGB → meta → Signal."""
        engine = InferenceEngine()
        sig = engine.generate(source="canonical")
        # Verify the chain produced a valid Signal object
        assert sig.timestamp is not None
        assert sig.direction in (Direction.LONG, Direction.SHORT, Direction.FLAT)
        assert sig.feature_vector is not None
        assert sig.feature_vector.shape == (55,)

    def test_feature_extraction_matches_meta_input(self):
        """The 22 features extracted from the 55-vector must match META_FEATURE_NAMES."""
        engine = InferenceEngine()
        sig = engine.generate(source="canonical")
        meta_vec = extract_meta_features(sig.feature_vector, FEATURE_NAMES)
        assert meta_vec.shape == (22,)
        # Verify by re-predicting
        meta_proba = engine.bundle.meta.predict_proba(meta_vec.reshape(1, -1))[0]
        assert abs(meta_proba[1] - sig.meta_confidence) < 1e-9
