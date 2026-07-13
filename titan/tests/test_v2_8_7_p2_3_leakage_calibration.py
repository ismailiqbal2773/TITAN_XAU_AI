"""TITAN XAU AI — v2.8.7-P2.3 Leakage & Calibration Tests
==========================================================

Tests for:
  - OOS leakage detection (model trained on full dataset → leakage)
  - Calibration hard acceptance (slope 0.167 must fail)
  - Feature integrity (no nan_to_num, NaN/inf after warm-up must fail)
  - Historical safety provider (no fake PASS flags)
"""
from __future__ import annotations
import sys
from pathlib import Path
import pytest
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


class TestLeakageDetection:
    """Phase 3: OOS leakage detection (v2.8.7-P2.4: uses actual date ranges, not mtime)."""

    def test_existing_model_is_leakage_free_for_2026(self):
        """The existing v2 model trained on 2020-2024 is LEAKAGE_FREE for 2026 OOS."""
        from titan.production.leakage_detection import assess_existing_v2_model_for_2026_holdout
        result = assess_existing_v2_model_for_2026_holdout()
        assert result.classification == "LEAKAGE_FREE"
        assert result.leakage_detected is False

    def test_no_leakage_when_training_ends_before_oos(self):
        """If training ends before OOS starts, no leakage."""
        from titan.production.leakage_detection import assess_oos_leakage, load_existing_v2_provenance
        prov = load_existing_v2_provenance()
        result = assess_oos_leakage(prov, prov.test_oos_start, prov.test_oos_end)
        assert result.classification == "LEAKAGE_FREE"

    def test_leakage_detected_when_training_overlaps_oos(self):
        """If training ends after OOS starts, leakage is detected."""
        from titan.production.leakage_detection import assess_oos_leakage, load_existing_v2_provenance, TrainingProvenance
        prov = load_existing_v2_provenance()
        bad_prov = TrainingProvenance(**{**prov.to_dict(), "training_end": "2026-03-01 00:00:00+00:00"})
        result = assess_oos_leakage(bad_prov, prov.test_oos_start, prov.test_oos_end)
        assert result.classification == "OOS_LEAKAGE_DETECTED"
        assert result.leakage_detected is True


class TestCalibrationHardAcceptance:
    """Phase 4: Calibration hard acceptance — slope 0.167 must fail."""

    def test_slope_0_167_fails(self):
        """Slope 0.167 is outside [0.50, 2.00] → REJECT_CALIBRATION."""
        from titan.production.model_provenance import CalibrationEvidence
        ce = CalibrationEvidence(
            artifact_path="test", artifact_sha256="test",
            model_sha256="test", scaler_sha256="test", feature_schema_sha256="test",
            generated_at_utc="2026-01-01T00:00:00Z",
            sample_period_start="2024-01-01", sample_period_end="2026-01-01",
            brier_score=0.207, calibration_slope=0.167,
            calibration_intercept=0.0, drift_status="none", n_samples=38233,
        )
        ok, msg = ce.validate()
        assert ok is False
        assert "REJECT_CALIBRATION" in msg
        assert "0.167" in msg

    def test_slope_1_0_passes(self):
        """Slope 1.0 is within [0.50, 2.00] → PASS."""
        from titan.production.model_provenance import CalibrationEvidence
        ce = CalibrationEvidence(
            artifact_path="test", artifact_sha256="test",
            model_sha256="test", scaler_sha256="test", feature_schema_sha256="test",
            generated_at_utc="2026-01-01T00:00:00Z",
            sample_period_start="2024-01-01", sample_period_end="2026-01-01",
            brier_score=0.20, calibration_slope=1.0,
            calibration_intercept=0.0, drift_status="none", n_samples=200,
        )
        ok, msg = ce.validate()
        assert ok is True

    def test_slope_0_49_fails(self):
        """Slope 0.49 is below 0.50 → REJECT_CALIBRATION."""
        from titan.production.model_provenance import CalibrationEvidence
        ce = CalibrationEvidence(
            artifact_path="test", artifact_sha256="test",
            model_sha256="test", scaler_sha256="test", feature_schema_sha256="test",
            generated_at_utc="2026-01-01T00:00:00Z",
            sample_period_start="2024-01-01", sample_period_end="2026-01-01",
            brier_score=0.20, calibration_slope=0.49,
            calibration_intercept=0.0, drift_status="none", n_samples=200,
        )
        ok, msg = ce.validate()
        assert ok is False
        assert "REJECT_CALIBRATION" in msg

    def test_slope_2_01_fails(self):
        """Slope 2.01 is above 2.00 → REJECT_CALIBRATION."""
        from titan.production.model_provenance import CalibrationEvidence
        ce = CalibrationEvidence(
            artifact_path="test", artifact_sha256="test",
            model_sha256="test", scaler_sha256="test", feature_schema_sha256="test",
            generated_at_utc="2026-01-01T00:00:00Z",
            sample_period_start="2024-01-01", sample_period_end="2026-01-01",
            brier_score=0.20, calibration_slope=2.01,
            calibration_intercept=0.0, drift_status="none", n_samples=200,
        )
        ok, msg = ce.validate()
        assert ok is False
        assert "REJECT_CALIBRATION" in msg

    def test_brier_above_0_33_fails(self):
        """Brier > 0.33 (worse than random) → REJECT_CALIBRATION."""
        from titan.production.model_provenance import CalibrationEvidence
        ce = CalibrationEvidence(
            artifact_path="test", artifact_sha256="test",
            model_sha256="test", scaler_sha256="test", feature_schema_sha256="test",
            generated_at_utc="2026-01-01T00:00:00Z",
            sample_period_start="2024-01-01", sample_period_end="2026-01-01",
            brier_score=0.40, calibration_slope=1.0,
            calibration_intercept=0.0, drift_status="none", n_samples=200,
        )
        ok, msg = ce.validate()
        assert ok is False
        assert "REJECT_CALIBRATION" in msg


class TestFeatureIntegrity:
    """Phase 5: No nan_to_num — NaN/inf after warm-up must fail."""

    def test_nan_to_num_not_used_in_evaluation(self):
        """Verify nan_to_num is not CALLED in the evaluation script (docstring mentions are OK)."""
        eval_path = REPO_ROOT / "scripts/run_v2_3_evaluation.py"
        if eval_path.exists():
            src = eval_path.read_text()
            # Strip docstrings
            import re
            stripped = re.sub(r'"""[\s\S]*?"""', '""', src)
            stripped = re.sub(r"'''[\s\S]*?'''", "''", stripped)
            # Check for actual function calls
            assert "np.nan_to_num" not in stripped, "np.nan_to_num called in evaluation script"
            assert "nan_to_num(" not in stripped, "nan_to_num() called in evaluation script"

    def test_backtest_requires_safety_provider(self):
        """run_backtest_v3 must require safety_provider — no default."""
        from titan.production.canonical_backtest import run_backtest_v3
        import inspect
        sig = inspect.signature(run_backtest_v3)
        assert "safety_provider" in sig.parameters
        # No default value (or default is None which fails closed)
        assert sig.parameters["safety_provider"].default is None

    def test_no_build_default_safety_state(self):
        """_build_default_safety_state must not exist in canonical_backtest."""
        from titan.production import canonical_backtest
        assert not hasattr(canonical_backtest, "_build_default_safety_state")


class TestHistoricalSafetyProvider:
    """Phase 2: Historical safety provider — no fake PASS flags."""

    def test_provider_reconstructs_real_state(self):
        """Provider builds SafetyStateV2 from real historical information."""
        from titan.production.historical_safety_provider import HistoricalSafetyProvider
        from titan.production.model_provenance import CalibrationEvidence
        ce = CalibrationEvidence(
            artifact_path="test", artifact_sha256="test",
            model_sha256="test", scaler_sha256="test", feature_schema_sha256="test",
            generated_at_utc="2026-01-01T00:00:00Z",
            sample_period_start="2024-01-01", sample_period_end="2026-01-01",
            brier_score=0.20, calibration_slope=1.0,
            calibration_intercept=0.0, drift_status="none", n_samples=200,
        )
        provider = HistoricalSafetyProvider(
            calibration_evidence=ce,
            alpha_probas_full=np.full(100, 0.55),
            meta_probas_full=np.full(100, 0.55),
        )
        state = provider.build_state_at_bar(
            bar_index=50, equity=100000, equity_peak=100000,
            daily_peak=100000, daily_start_equity=100000,
            loss_streak=0, total_dd=0.0, daily_dd=0.0,
            spread=0.15, atr=5.0, regime_label="STABLE_RANGE",
            regime_confidence=0.7,
        )
        # No fake PASS flags — values come from real inputs
        assert state.dd_state["current_dd"] == 0.0
        assert state.dd_state["daily_dd"] == 0.0
        assert state.loss_streak == 0
        assert state.calibration_metrics["calibration_slope"] == 1.0
        assert len(state.alpha_distribution) > 0
        assert len(state.meta_distribution) > 0

    def test_provider_capital_protection_activates_at_8pct_dd(self):
        """When total_dd >= 0.08, capital_protection.active = True."""
        from titan.production.historical_safety_provider import HistoricalSafetyProvider
        from titan.production.model_provenance import CalibrationEvidence
        ce = CalibrationEvidence(
            artifact_path="test", artifact_sha256="test",
            model_sha256="test", scaler_sha256="test", feature_schema_sha256="test",
            generated_at_utc="2026-01-01T00:00:00Z",
            sample_period_start="2024-01-01", sample_period_end="2026-01-01",
            brier_score=0.20, calibration_slope=1.0,
            calibration_intercept=0.0, drift_status="none", n_samples=200,
        )
        provider = HistoricalSafetyProvider(
            calibration_evidence=ce,
            alpha_probas_full=np.full(100, 0.55),
            meta_probas_full=np.full(100, 0.55),
        )
        state = provider.build_state_at_bar(
            bar_index=50, equity=92000, equity_peak=100000,
            daily_peak=92000, daily_start_equity=100000,
            loss_streak=0, total_dd=0.08, daily_dd=0.0,
            spread=0.15, atr=5.0, regime_label="STABLE_RANGE",
            regime_confidence=0.7,
        )
        assert state.capital_protection["active"] is True
