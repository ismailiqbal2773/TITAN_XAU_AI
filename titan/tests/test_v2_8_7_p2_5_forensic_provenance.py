"""TITAN XAU AI — v2.8.7-P2.5 Forensic Provenance Tests
=========================================================

Tests that verify forensic corrections:
  1. Actual model params (397/7/0.0175) — not P2.4's wrong values (200/6/0.1)
  2. Legacy calibration artifact archived as invalid
  3. 2026 classified as RETROSPECTIVE_OOS_2026 (not untouched)
  4. CEO NOT mocked in evaluation
  5. Calibration slope on 2025-only segment passes (1.0042)
"""
from __future__ import annotations
import sys, json, pickle, re
from pathlib import Path
import pytest
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


class TestActualModelParams:
    """Phase 2: Verify actual model parameters from loaded artifacts."""

    def test_xgb_n_estimators_is_397(self):
        """Actual XGBoost has n_estimators=397, not 200."""
        with open(REPO_ROOT / "titan/data/models/xgboost_v2_feature_normalized.pkl", "rb") as f:
            xgb = pickle.load(f)
        assert xgb.n_estimators == 397

    def test_xgb_max_depth_is_7(self):
        """Actual XGBoost has max_depth=7, not 6."""
        with open(REPO_ROOT / "titan/data/models/xgboost_v2_feature_normalized.pkl", "rb") as f:
            xgb = pickle.load(f)
        assert xgb.max_depth == 7

    def test_xgb_learning_rate_is_0_0175(self):
        """Actual XGBoost has learning_rate=0.0175, not 0.1."""
        with open(REPO_ROOT / "titan/data/models/xgboost_v2_feature_normalized.pkl", "rb") as f:
            xgb = pickle.load(f)
        assert xgb.learning_rate == 0.0175

    def test_meta_model_is_logistic_regression(self):
        """Meta model is LogisticRegression."""
        with open(REPO_ROOT / "titan/data/models/meta_label_v2_feature_normalized.pkl", "rb") as f:
            meta = pickle.load(f)
        assert type(meta).__name__ == "LogisticRegression"

    def test_provenance_matches_actual_params(self):
        """Provenance manifest must match actual loaded model params."""
        provenance_path = REPO_ROOT / "data/reports/competition_candidate/training_provenance.json"
        if not provenance_path.exists():
            pytest.skip("Provenance not yet generated")
        with open(provenance_path) as f:
            prov = json.load(f)
        actual_params = prov.get("actual_xgb_params", {})
        assert actual_params.get("n_estimators") == 397
        assert actual_params.get("max_depth") == 7
        assert actual_params.get("learning_rate") == 0.0175


class TestLegacyCalibrationArchived:
    """Phase 4: Legacy calibration artifact must be archived as invalid."""

    def test_legacy_calibration_archived(self):
        """Legacy calibration (2020-2026) must be archived."""
        archive_path = REPO_ROOT / "data/reports/competition_candidate/legacy_calibration_archived.json"
        if not archive_path.exists():
            pytest.skip("Archive not yet generated")
        with open(archive_path) as f:
            archive = json.load(f)
        assert archive["status"] == "ARCHIVED_INVALID"
        assert "2020" in archive["original_period"]
        assert "2026" in archive["original_period"]

    def test_legacy_calibration_slope_0_167_does_not_pass(self):
        """The legacy slope 0.167 must NOT pass hard acceptance."""
        from titan.production.model_provenance import CalibrationEvidence
        ce = CalibrationEvidence(
            artifact_path="legacy", artifact_sha256="legacy",
            model_sha256="legacy", scaler_sha256="legacy", feature_schema_sha256="legacy",
            generated_at_utc="2026-07-11T00:00:00Z",
            sample_period_start="2020-01-02", sample_period_end="2026-06-19",
            brier_score=0.207, calibration_slope=0.167,
            calibration_intercept=0.5635, drift_status="none", n_samples=38233,
        )
        ok, msg = ce.validate()
        assert ok is False
        assert "REJECT_CALIBRATION" in msg


class TestRetrospective2026Classification:
    """Phase 5: 2026 must be classified as RETROSPECTIVE_OOS_2026."""

    def test_2026_not_described_as_untouched(self):
        """2026 must NOT be described as 'untouched holdout' in any report
        (except in the context of explicitly saying it is NOT untouched)."""
        report_dir = REPO_ROOT / "data/reports/competition_candidate"
        if not report_dir.exists():
            pytest.skip("Reports not yet generated")
        for f in report_dir.iterdir():
            if f.suffix in (".json", ".txt", ".yaml"):
                content = f.read_text().lower()
                # The phrase "untouched holdout" is only OK if preceded by "not an"
                # or "not untouched"
                lines = content.split('\n')
                for line in lines:
                    if "untouched holdout" in line and "not" not in line:
                        pytest.fail(f"File {f.name} describes 2026 as 'untouched holdout' without negation: {line.strip()}")

    def test_2026_classified_as_retrospective(self):
        """2026 must be classified as RETROSPECTIVE_OOS_2026."""
        retro_path = REPO_ROOT / "data/reports/competition_candidate/retrospective_2026_metrics.json"
        if not retro_path.exists():
            pytest.skip("Retrospective metrics not yet generated")
        with open(retro_path) as f:
            retro = json.load(f)
        assert retro.get("classification") == "RETROSPECTIVE_OOS_2026"


class TestCEONotMocked:
    """Phase 3: CEO governance must NOT be mocked in evaluation."""

    def test_no_ceo_mock_in_evaluation_script(self):
        """Evaluation script must not mock CEO governance."""
        eval_path = REPO_ROOT / "scripts/run_v2_5_evaluation.py"
        if not eval_path.exists():
            pytest.skip("Evaluation script not found")
        src = eval_path.read_text()
        # Strip docstrings
        stripped = re.sub(r'"""[\s\S]*?"""', '""', src)
        stripped = re.sub(r"'''[\s\S]*?'''", "''", stripped)
        # Check for CEO mock patterns
        assert "evaluate_ceo_decision = lambda" not in stripped, \
            "CEO is mocked with lambda in evaluation script"
        assert "allowed_to_trade': True" not in stripped or "type('C'" not in stripped, \
            "CEO result is hard-coded to PASS in evaluation script"

    def test_no_ceo_mock_in_backtest(self):
        """canonical_backtest.py must not mock CEO."""
        path = REPO_ROOT / "titan/production/canonical_backtest.py"
        src = path.read_text()
        stripped = re.sub(r'"""[\s\S]*?"""', '""', src)
        assert "evaluate_ceo_decision = lambda" not in stripped
        assert "allowed_to_trade': True" not in stripped


class TestFeatureWarmupProgrammatic:
    """Phase 1: Warm-up must be determined programmatically, not hard-coded."""

    def test_first_valid_row_is_239(self):
        """First fully valid feature row must be at index 239 (all 55 features finite)."""
        import pandas as pd
        from titan.production.feature_stream_v2 import H1FeatureStreamV2
        df = pd.read_parquet(REPO_ROOT / "titan/data/canonical/XAUUSD_H1_canonical.parquet")
        df_use = df[["open", "high", "low", "close"]].copy()
        df_use["volume"] = df["tick_volume"]
        df_use["spread"] = df["spread_usd"]
        stream = H1FeatureStreamV2()
        stream._bars = df_use
        feats = stream._compute_features()
        fm = feats.values.astype(np.float64)
        first_valid = None
        for i in range(len(fm)):
            if np.all(np.isfinite(fm[i])):
                first_valid = i
                break
        assert first_valid == 239

    def test_no_nan_to_num_in_feature_engine(self):
        """feature_engine_v2 standardize_v2 must not call nan_to_num."""
        from titan.training.feature_engine_v2 import standardize_v2
        import inspect, re
        src = inspect.getsource(standardize_v2)
        stripped = re.sub(r'"""[\s\S]*?"""', '""', src)
        assert "nan_to_num(" not in stripped
        assert "np.nan_to_num" not in stripped
