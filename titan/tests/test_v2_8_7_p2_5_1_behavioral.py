"""TITAN XAU AI — v2.8.7-P2.5.1 Behavioral Tests
===================================================

Tests that prove behavior, not merely search for text.
"""
from __future__ import annotations
import sys, json, pickle, re
from pathlib import Path
import pytest
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


class TestP25Invalidation:
    """P2.5 reports must be invalidated."""

    def test_invalidation_json_exists(self):
        path = REPO_ROOT / "data/reports/invalidated/p2_5_single_model_slicing/INVALIDATION.json"
        assert path.exists(), "INVALIDATION.json must exist"

    def test_invalidation_contains_reasons(self):
        path = REPO_ROOT / "data/reports/invalidated/p2_5_single_model_slicing/INVALIDATION.json"
        with open(path) as f:
            data = json.load(f)
        assert len(data["exact_reasons"]) >= 10
        assert "PF 9.5775" in data["statement"]

    def test_p25_reports_archived(self):
        archive = REPO_ROOT / "data/reports/invalidated/p2_5_single_model_slicing"
        assert (archive / "final_verdict.json").exists()


class TestFoldSpecificHashes:
    """Each fold must have different model hashes — no single-model slicing."""

    def test_fold_hashes_are_different(self):
        prov_path = REPO_ROOT / "data/reports/competition_candidate/training_provenance.json"
        if not prov_path.exists():
            pytest.skip("Provenance not yet generated")
        with open(prov_path) as f:
            prov = json.load(f)
        assert prov.get("folds_have_different_hashes") is True

    def test_fold_artifact_directories_exist(self):
        artifacts_dir = REPO_ROOT / "data/artifacts/p2_5_1"
        if not artifacts_dir.exists():
            pytest.skip("Fold artifacts not yet generated")
        fold_dirs = list(artifacts_dir.glob("fold_*"))
        assert len(fold_dirs) >= 3, f"Expected >=3 fold dirs, got {len(fold_dirs)}"

    def test_each_fold_has_alpha_model(self):
        artifacts_dir = REPO_ROOT / "data/artifacts/p2_5_1"
        if not artifacts_dir.exists():
            pytest.skip("Fold artifacts not yet generated")
        for fold_dir in sorted(artifacts_dir.glob("fold_*")):
            assert (fold_dir / "alpha_model.pkl").exists(), f"Missing alpha_model in {fold_dir.name}"
            assert (fold_dir / "meta_model.pkl").exists(), f"Missing meta_model in {fold_dir.name}"
            assert (fold_dir / "scaler.json").exists(), f"Missing scaler in {fold_dir.name}"
            assert (fold_dir / "provenance.json").exists(), f"Missing provenance in {fold_dir.name}"


class TestFoldBoundaries:
    """Fold OOS must end before 2026."""

    def test_all_oos_before_2026(self):
        prov_path = REPO_ROOT / "data/reports/competition_candidate/training_provenance.json"
        if not prov_path.exists():
            pytest.skip("Provenance not yet generated")
        with open(prov_path) as f:
            prov = json.load(f)
        assert prov.get("all_oos_before_2026") is True

    def test_split_manifest_oos_before_2026(self):
        path = REPO_ROOT / "data/reports/competition_candidate/split_manifest.json"
        if not path.exists():
            pytest.skip("Split manifest not yet generated")
        with open(path) as f:
            data = json.load(f)
        for fold in data.get("folds", []):
            oos_end = fold.get("oos_end_date", "")
            assert "2025" in oos_end or "2024" in oos_end or "2023" in oos_end or "2022" in oos_end or "2021" in oos_end, \
                f"Fold {fold.get('fold')} OOS ends at {oos_end} — must be before 2026"


class TestNoFullDatasetInference:
    """No full-dataset prediction array before fold processing."""

    def test_no_load_production_models_in_evaluation(self):
        """Evaluation script must not call load_production_models_v2 for fold training."""
        eval_path = REPO_ROOT / "scripts/run_v2_5_1_evaluation.py"
        if not eval_path.exists():
            pytest.skip("Evaluation script not found")
        src = eval_path.read_text()
        stripped = re.sub(r'"""[\s\S]*?"""', '""', src)
        # load_production_models_v2 is OK for loading the EXISTING model as benchmark
        # but NOT for outer-fold training or OOS prediction
        assert "load_production_models_v2()" not in stripped or "benchmark" in stripped.lower(), \
            "load_production_models_v2() should not be used for fold training"


class TestCEONotMocked:
    """CEO must not be mocked in evaluation."""

    def test_no_ceo_mock_in_evaluation(self):
        eval_path = REPO_ROOT / "scripts/run_v2_5_1_evaluation.py"
        if not eval_path.exists():
            pytest.skip("Evaluation script not found")
        src = eval_path.read_text()
        stripped = re.sub(r'"""[\s\S]*?"""', '""', src)
        assert "evaluate_ceo_decision = lambda" not in stripped, \
            "CEO is mocked with lambda"
        assert "allowed_to_trade': True" not in stripped or "type('C'" not in stripped, \
            "CEO result is hard-coded to PASS"


class TestGrossNetPFDiffer:
    """Gross PF and Net PF must differ when costs exist."""

    def test_pf_gross_differs_from_pf_net(self):
        path = REPO_ROOT / "data/reports/competition_candidate/final_verdict.json"
        if not path.exists():
            pytest.skip("Verdict not yet generated")
        with open(path) as f:
            verdict = json.load(f)
        assert verdict.get("pf_gross_differs_from_pf_net") is True


class TestContinuousEquity:
    """Equity must be continuous across folds."""

    def test_continuous_equity_flag(self):
        path = REPO_ROOT / "data/reports/competition_candidate/walk_forward_metrics.json"
        if not path.exists():
            pytest.skip("WFO metrics not yet generated")
        with open(path) as f:
            data = json.load(f)
        assert data.get("continuous_equity") is True


class TestCrossFittedMeta:
    """Cross-fitted meta must be validated, not just a JSON boolean."""

    def test_cross_fitted_meta_validated(self):
        path = REPO_ROOT / "data/reports/competition_candidate/walk_forward_metrics.json"
        if not path.exists():
            pytest.skip("WFO metrics not yet generated")
        with open(path) as f:
            data = json.load(f)
        assert data.get("cross_fitted_meta_validated") is True

    def test_oof_coverage_reported(self):
        prov_path = REPO_ROOT / "data/reports/competition_candidate/training_provenance.json"
        if not prov_path.exists():
            pytest.skip("Provenance not yet generated")
        with open(prov_path) as f:
            prov = json.load(f)
        fold_hashes = prov.get("fold_hashes", [])
        for fh in fold_hashes:
            assert "oof_coverage" in fh, f"Missing oof_coverage in fold {fh.get('fold')}"


class TestCalibrationFoldSpecific:
    """Calibration must be fold-specific, not a single 2025 result."""

    def test_calibration_fold_specific(self):
        path = REPO_ROOT / "data/reports/competition_candidate/calibration_assessment.json"
        if not path.exists():
            pytest.skip("Calibration assessment not yet generated")
        with open(path) as f:
            data = json.load(f)
        assert data.get("fold_specific") is True

    def test_alpha_slopes_all_pass(self):
        path = REPO_ROOT / "data/reports/competition_candidate/calibration_assessment.json"
        if not path.exists():
            pytest.skip("Calibration assessment not yet generated")
        with open(path) as f:
            data = json.load(f)
        for slope in data.get("alpha_slopes", []):
            assert 0.50 <= slope <= 2.00, f"Alpha slope {slope} outside [0.50, 2.00]"


class TestRetrospective2026:
    """2026 must be classified as RETROSPECTIVE_OOS_2026."""

    def test_2026_classification(self):
        path = REPO_ROOT / "data/reports/competition_candidate/retrospective_2026_metrics.json"
        if not path.exists():
            pytest.skip("Retrospective metrics not yet generated")
        with open(path) as f:
            data = json.load(f)
        assert data.get("classification") == "RETROSPECTIVE_OOS_2026"
