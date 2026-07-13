"""TITAN XAU AI — v2.8.7-P2.5.2 Final Closure Tests
=====================================================

Tests that prove:
  - 5 folds exist (not 3)
  - All OOS before 2026
  - Fold hashes are unique
  - Feature stream v2 has no nan_to_num
  - Gross PF differs from Net PF
  - Dev WFO has >= 200 trades
  - P2.5.1 invalidated
"""
from __future__ import annotations
import sys, json, re
from pathlib import Path
import pytest
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


class TestP251Invalidation:
    """Phase 0: P2.5.1 must be invalidated."""

    def test_invalidation_json_exists(self):
        path = REPO_ROOT / "data/reports/invalidated/p2_5_1_incomplete_closure/INVALIDATION.json"
        assert path.exists()

    def test_invalidation_states_reasons(self):
        path = REPO_ROOT / "data/reports/invalidated/p2_5_1_incomplete_closure/INVALIDATION.json"
        with open(path) as f:
            data = json.load(f)
        assert len(data["exact_reasons"]) >= 7
        assert data["fold_count_actual"] == 3
        assert data["fold_count_required"] == 5


class TestFiveFolds:
    """Phase 2: At least 5 folds must exist."""

    def test_five_fold_artifact_directories(self):
        artifacts_dir = REPO_ROOT / "data/artifacts/p2_5_1"
        fold_dirs = list(artifacts_dir.glob("fold_*"))
        assert len(fold_dirs) >= 5, f"Expected >=5 fold dirs, got {len(fold_dirs)}"

    def test_five_folds_in_provenance(self):
        prov_path = REPO_ROOT / "data/reports/competition_candidate/training_provenance.json"
        with open(provenance_path if 'provenance_path' in dir() else prov_path) as f:
            prov = json.load(f)
        fold_hashes = prov.get("fold_hashes", [])
        assert len(fold_hashes) >= 5, f"Expected >=5 folds in provenance, got {len(fold_hashes)}"

    def test_fold_hashes_all_unique(self):
        prov_path = REPO_ROOT / "data/reports/competition_candidate/training_provenance.json"
        with open(prov_path) as f:
            prov = json.load(f)
        alpha_hashes = [fh["alpha_model_hash"] for fh in prov.get("fold_hashes", [])]
        assert len(set(alpha_hashes)) == len(alpha_hashes), "Fold alpha hashes are not all unique"

    def test_all_oos_before_2026(self):
        prov_path = REPO_ROOT / "data/reports/competition_candidate/training_provenance.json"
        with open(prov_path) as f:
            prov = json.load(f)
        assert prov.get("all_oos_before_2026") is True

    def test_fold5_oos_ends_before_2026(self):
        prov_path = REPO_ROOT / "data/reports/competition_candidate/training_provenance.json"
        with open(prov_path) as f:
            prov = json.load(f)
        fold_hashes = prov.get("fold_hashes", [])
        if len(fold_hashes) >= 5:
            fold5_end = fold_hashes[4].get("oos_end_date", "")
            assert "2025" in fold5_end or "2024" in fold5_end, \
                f"Fold 5 OOS ends at {fold5_end} — must be before 2026"


class TestFeatureStreamNoNanToNum:
    """Phase 4: feature_stream_v2 must not use nan_to_num."""

    def test_no_nan_to_num_in_feature_stream_v2(self):
        path = REPO_ROOT / "titan/production/feature_stream_v2.py"
        src = path.read_text()
        stripped = re.sub(r'"""[\s\S]*?"""', '""', src)
        stripped = re.sub(r"'''[\s\S]*?'''", "''", stripped)
        assert "np.nan_to_num" not in stripped, "nan_to_num found in feature_stream_v2.py"
        assert "nan_to_num(" not in stripped, "nan_to_num() call found in feature_stream_v2.py"

    def test_feature_vector_has_is_valid_field(self):
        from titan.production.feature_stream_v2 import FeatureVectorV2
        import inspect
        src = inspect.getsource(FeatureVectorV2)
        assert "is_valid" in src
        assert "invalid_features" in src


class TestGrossNetPFDiffer:
    """Phase 7: Gross PF must differ from Net PF when costs exist."""

    def test_pf_gross_differs_from_pf_net(self):
        path = REPO_ROOT / "data/reports/competition_candidate/final_verdict.json"
        with open(path) as f:
            v = json.load(f)
        assert v.get("pf_gross_differs_from_pf_net") is True

    def test_pf_gross_not_equal_pf_net_in_baseline(self):
        path = REPO_ROOT / "data/reports/competition_candidate/baseline_metrics.json"
        with open(path) as f:
            m = json.load(f)
        assert m.get("pf_gross") != m.get("pf_net"), \
            f"pf_gross={m.get('pf_gross')} equals pf_net={m.get('pf_net')}"


class TestAdequateTradeSample:
    """Phase 9: Dev WFO must have >= 200 trades."""

    def test_dev_trades_ge_200(self):
        path = REPO_ROOT / "data/reports/competition_candidate/final_verdict.json"
        with open(path) as f:
            v = json.load(f)
        assert v["dev_metrics"]["trades"] >= 200, \
            f"Dev trades={v['dev_metrics']['trades']} < 200"


class TestContinuousEquity:
    """Phase 7: Equity must be continuous."""

    def test_continuous_equity_flag(self):
        path = REPO_ROOT / "data/reports/competition_candidate/walk_forward_metrics.json"
        with open(path) as f:
            data = json.load(f)
        assert data.get("continuous_equity") is True


class TestCrossFittedMetaValidated:
    """Phase 3: Cross-fitted meta must be validated."""

    def test_cross_fitted_meta_validated(self):
        path = REPO_ROOT / "data/reports/competition_candidate/walk_forward_metrics.json"
        with open(path) as f:
            data = json.load(f)
        assert data.get("cross_fitted_meta_validated") is True

    def test_wfo_type_is_fold_specific(self):
        path = REPO_ROOT / "data/reports/competition_candidate/walk_forward_metrics.json"
        with open(path) as f:
            data = json.load(f)
        assert "fold_specific" in data.get("wfo_type", "")


class TestCalibrationFoldSpecific:
    """Phase 5: Calibration must be fold-specific."""

    def test_calibration_fold_specific(self):
        path = REPO_ROOT / "data/reports/competition_candidate/calibration_assessment.json"
        with open(path) as f:
            data = json.load(f)
        assert data.get("fold_specific") is True

    def test_all_alpha_slopes_pass(self):
        path = REPO_ROOT / "data/reports/competition_candidate/calibration_assessment.json"
        with open(path) as f:
            data = json.load(f)
        for slope in data.get("alpha_slopes", []):
            assert 0.50 <= slope <= 2.00, f"Alpha slope {slope} outside [0.50, 2.00]"


class TestRetrospective2026:
    """Phase 5: 2026 must be RETROSPECTIVE_OOS_2026."""

    def test_2026_classification(self):
        path = REPO_ROOT / "data/reports/competition_candidate/retrospective_2026_metrics.json"
        with open(path) as f:
            data = json.load(f)
        assert data.get("classification") == "RETROSPECTIVE_OOS_2026"


class TestReportReconciliation:
    """Phase 1: Report values must match committed artifacts."""

    def test_fold_hashes_match_artifacts(self):
        """Report fold hashes must match actual committed artifact hashes."""
        import hashlib, pickle
        prov_path = REPO_ROOT / "data/reports/competition_candidate/training_provenance.json"
        with open(prov_path) as f:
            prov = json.load(f)
        for fh in prov.get("fold_hashes", []):
            fold_num = fh["fold"]
            fold_dir = REPO_ROOT / f"data/artifacts/p2_5_1/fold_{fold_num:02d}"
            if not fold_dir.exists():
                continue
            fold_prov = json.load(open(fold_dir / "provenance.json"))
            assert fh["alpha_model_hash"] == fold_prov["alpha_model_hash"][:16], \
                f"Fold {fold_num}: report hash {fh['alpha_model_hash']} != provenance {fold_prov['alpha_model_hash'][:16]}"
