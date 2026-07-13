"""TITAN XAU AI — v2.8.7-P2.4 Provenance & Leakage Tests
=========================================================

Tests for:
  - Correct leakage detection (training 2020-2024, OOS 2026 → LEAKAGE_FREE)
  - Training provenance manifest with actual date boundaries
  - Feature warm-up calculation (239 bars from feature definitions)
  - Feature integrity (no nan_to_num, no NaN/inf after warm-up)
"""
from __future__ import annotations
import sys
from pathlib import Path
import pytest
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


class TestProvenanceLeakage:
    """Phase 1: Correct leakage detection using actual date ranges."""

    def test_existing_v2_model_is_leakage_free_for_2026(self):
        """The existing v2 model was trained on 2020-2024, OOS is 2026 → LEAKAGE_FREE."""
        from titan.production.leakage_detection import assess_existing_v2_model_for_2026_holdout
        result = assess_existing_v2_model_for_2026_holdout()
        assert result.classification == "LEAKAGE_FREE"
        assert result.leakage_detected is False
        assert result.overlap_detected is False

    def test_training_ends_before_2026(self):
        """Training must end before 2026-01-01."""
        from titan.production.leakage_detection import load_existing_v2_provenance
        prov = load_existing_v2_provenance()
        import pandas as pd
        train_end = pd.Timestamp(prov.training_end)
        holdout_start = pd.Timestamp(prov.test_oos_start)
        assert train_end < holdout_start, \
            f"Training end {train_end} must be before OOS start {holdout_start}"

    def test_provenance_has_all_required_fields(self):
        """Training provenance manifest must contain all required fields."""
        from titan.production.leakage_detection import load_existing_v2_provenance
        prov = load_existing_v2_provenance()
        required = [
            "model_sha256", "meta_model_sha256", "scaler_sha256", "schema_sha256",
            "source_dataset_sha256", "training_start", "training_end",
            "inner_validation_start", "inner_validation_end",
            "calibration_start", "calibration_end",
            "test_oos_start", "test_oos_end",
            "label_horizon_bars", "purge_bars", "embargo_bars",
            "feature_names", "training_script_sha256",
            "hyperparameters", "random_seed", "software_versions",
            "generation_timestamp",
        ]
        d = prov.to_dict()
        for field in required:
            assert field in d, f"Missing provenance field: {field}"
            assert d[field] is not None, f"Empty provenance field: {field}"

    def test_no_mtime_only_leakage(self):
        """Leakage detection must NOT use file mtime as the sole criterion."""
        from titan.production.leakage_detection import assess_oos_leakage, load_existing_v2_provenance
        prov = load_existing_v2_provenance()
        # Even though model mtime is 2026-07-11 (after OOS start), the actual
        # training data ended 2024-12-31 (before OOS start) → LEAKAGE_FREE
        result = assess_oos_leakage(prov, prov.test_oos_start, prov.test_oos_end)
        assert result.classification == "LEAKAGE_FREE"

    def test_overlap_detected_when_training_overlaps_oos(self):
        """When training end >= OOS start, leakage is detected."""
        from titan.production.leakage_detection import assess_oos_leakage, load_existing_v2_provenance
        prov = load_existing_v2_provenance()
        # Simulate overlap: set training_end to after OOS start
        from titan.production.leakage_detection import TrainingProvenance
        bad_prov = TrainingProvenance(
            **{**prov.to_dict(),
               "training_end": "2026-03-01 00:00:00+00:00"}  # After OOS start
        )
        result = assess_oos_leakage(bad_prov, prov.test_oos_start, prov.test_oos_end)
        assert result.classification == "OOS_LEAKAGE_DETECTED"
        assert result.leakage_detected is True


class TestFeatureWarmup:
    """Phase 2: Feature warm-up calculation."""

    def test_required_warmup_is_239(self):
        """Required warm-up must be 239 bars (from vol_of_vol_120 compound lookback)."""
        from titan.production.feature_warmup import REQUIRED_WARMUP
        assert REQUIRED_WARMUP == 239

    def test_warmup_derived_from_code_not_hardcoded(self):
        """Warm-up must be derived from feature definitions, not arbitrary."""
        from titan.production.feature_warmup import (
            REQUIRED_WARMUP, SMA_200_LOOKBACK, VOL_OF_VOL_120_LOOKBACK,
            VOL_OF_VOL_60_LOOKBACK, REALIZED_VOL_120_LOOKBACK,
            RETURN_LAG_60, OBV_ROLLING_120, OBV_SLOPE_20_PLUS_ROLLING_120,
        )
        expected = max(
            SMA_200_LOOKBACK, VOL_OF_VOL_120_LOOKBACK, VOL_OF_VOL_60_LOOKBACK,
            REALIZED_VOL_120_LOOKBACK, RETURN_LAG_60,
            OBV_ROLLING_120, OBV_SLOPE_20_PLUS_ROLLING_120,
        )
        assert REQUIRED_WARMUP == expected
        # vol_of_vol_120 = 120 + 120 - 1 = 239 is the maximum
        assert REQUIRED_WARMUP == VOL_OF_VOL_120_LOOKBACK
        assert VOL_OF_VOL_120_LOOKBACK == 239

    def test_warmup_includes_purge_and_embargo(self):
        """Warm-up with purge and embargo must include label horizon bars."""
        from titan.production.feature_warmup import WARMUP_WITH_PURGE, REQUIRED_WARMUP, PURGE_BARS, EMBARGO_BARS
        assert WARMUP_WITH_PURGE == REQUIRED_WARMUP + PURGE_BARS + EMBARGO_BARS
        assert WARMUP_WITH_PURGE == 239 + 5 + 5  # 249


class TestFeatureIntegrity:
    """Phase 2: No nan_to_num, features must be finite after warm-up."""

    def test_nan_to_num_not_in_evaluation(self):
        """Evaluation script must not call nan_to_num."""
        import re
        for script in ["run_v2_4_evaluation.py"]:
            path = REPO_ROOT / "scripts" / script
            if path.exists():
                src = path.read_text()
                stripped = re.sub(r'"""[\s\S]*?"""', '""', src)
                assert "np.nan_to_num" not in stripped
                assert "nan_to_num(" not in stripped

    def test_feature_engine_no_nan_to_num_in_standardize(self):
        """standardize_v2 must not CALL nan_to_num (docstring mention is OK)."""
        from titan.training.feature_engine_v2 import standardize_v2
        import inspect, re
        src = inspect.getsource(standardize_v2)
        # Strip docstring
        stripped = re.sub(r'"""[\s\S]*?"""', '""', src)
        assert "np.nan_to_num" not in stripped
        assert "nan_to_num(" not in stripped
