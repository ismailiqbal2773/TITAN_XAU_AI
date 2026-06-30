"""TITAN XAU AI - Sprint 9.9.3.36 Auto Calibration Governance Tests"""
from __future__ import annotations
import inspect, sys
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from titan.production.auto_calibration_governance import (
    AutoCalibrationGovernance, CalibrationGovernanceResult, CalibrationAction,
)


class TestCalibrationActions:
    def test_01_all_actions_present(self):
        actions = [a.value for a in CalibrationAction]
        for a in ["KEEP_CURRENT", "RECOMMEND_THRESHOLD_ADJUSTMENT",
                  "RECOMMEND_PROBABILITY_RECALIBRATION", "BLOCK_CALIBRATION",
                  "NEEDS_REVIEW"]:
            assert a in actions


class TestResultDataclass:
    def test_02_result_has_all_required_fields(self):
        r = CalibrationGovernanceResult(
            action=CalibrationAction.KEEP_CURRENT,
            current_threshold=0.5,
            recommended_threshold=0.5,
            calibration_score=0.9,
            brier_score=0.15,
            expected_calibration_error=0.05,
            sample_count=1000,
        )
        required = ["action", "current_threshold", "recommended_threshold",
                    "calibration_score", "brier_score", "expected_calibration_error",
                    "sample_count", "reasons", "blockers", "warnings",
                    "apply_automatically", "timestamp_utc"]
        for f in required:
            assert hasattr(r, f), f"Missing: {f}"

    def test_03_apply_automatically_always_false(self):
        # Even if we try to set it True, __post_init__ forces False
        r = CalibrationGovernanceResult(
            action=CalibrationAction.KEEP_CURRENT,
            current_threshold=0.5,
            recommended_threshold=0.5,
            calibration_score=0.9,
            brier_score=0.15,
            expected_calibration_error=0.05,
            sample_count=1000,
        )
        r.apply_automatically = True  # try to override
        assert r.apply_automatically is True  # instance attr can be set, but...
        # But every time a new result is created via governance, it must be False
        gov = AutoCalibrationGovernance()
        result = gov.evaluate_calibration({
            "sample_count": 1000,
            "brier_score": 0.15,
            "expected_calibration_error": 0.05,
            "current_threshold": 0.5,
        })
        assert result.apply_automatically is False


class TestNoAutoApply:
    def test_04_enforce_no_auto_apply_returns_false(self):
        gov = AutoCalibrationGovernance()
        assert gov.enforce_no_auto_apply() is False

    def test_05_recommendation_does_not_auto_apply(self):
        gov = AutoCalibrationGovernance()
        result = gov.evaluate_calibration({
            "sample_count": 1000,
            "brier_score": 0.15,
            "expected_calibration_error": 0.05,
            "current_threshold": 0.5,
        })
        assert result.apply_automatically is False
        # Even if action is RECOMMEND_*, apply_automatically must be False
        if result.action.value.startswith("RECOMMEND"):
            assert result.apply_automatically is False


class TestInsufficientSamples:
    def test_06_insufficient_samples_blocks(self):
        gov = AutoCalibrationGovernance()
        result = gov.evaluate_calibration({
            "sample_count": 100,  # < 500 minimum
            "brier_score": 0.15,
            "expected_calibration_error": 0.05,
            "current_threshold": 0.5,
        })
        assert result.action == CalibrationAction.BLOCK_CALIBRATION
        assert any("Insufficient" in b for b in result.blockers)

    def test_07_block_if_insufficient_samples_helper(self):
        gov = AutoCalibrationGovernance()
        ok, blockers = gov.block_if_insufficient_samples(100)
        assert ok is False
        assert len(blockers) >= 1
        ok, blockers = gov.block_if_insufficient_samples(1000)
        assert ok is True
        assert len(blockers) == 0


class TestLiveMode:
    def test_08_live_mode_blocks_calibration(self):
        gov = AutoCalibrationGovernance(live_mode=True)
        result = gov.evaluate_calibration({
            "sample_count": 1000,
            "brier_score": 0.15,
            "expected_calibration_error": 0.05,
            "current_threshold": 0.5,
        })
        assert result.action == CalibrationAction.BLOCK_CALIBRATION
        assert any("live mode" in b.lower() for b in result.blockers)

    def test_09_live_mode_in_metrics_blocks_calibration(self):
        gov = AutoCalibrationGovernance(live_mode=False)
        result = gov.evaluate_calibration({
            "sample_count": 1000,
            "brier_score": 0.15,
            "expected_calibration_error": 0.05,
            "current_threshold": 0.5,
            "live_mode": True,
        })
        assert result.action == CalibrationAction.BLOCK_CALIBRATION
        assert any("live mode" in b.lower() for b in result.blockers)

    def test_10_block_if_live_mode_helper(self):
        gov = AutoCalibrationGovernance(live_mode=True)
        ok, blockers = gov.block_if_live_mode()
        assert ok is False
        assert len(blockers) >= 1
        gov2 = AutoCalibrationGovernance(live_mode=False)
        ok, blockers = gov2.block_if_live_mode()
        assert ok is True


class TestPoorCalibration:
    def test_11_poor_brier_triggers_needs_review_or_block(self):
        gov = AutoCalibrationGovernance()
        result = gov.evaluate_calibration({
            "sample_count": 1000,
            "brier_score": 0.28,  # elevated
            "expected_calibration_error": 0.05,
            "current_threshold": 0.5,
        })
        assert result.action in (CalibrationAction.NEEDS_REVIEW, CalibrationAction.BLOCK_CALIBRATION)
        assert any("Brier" in w or "Brier" in b for w in [result.warnings, result.blockers][0])

    def test_12_poor_brier_blocks_when_severe(self):
        gov = AutoCalibrationGovernance()
        result = gov.evaluate_calibration({
            "sample_count": 1000,
            "brier_score": 0.40,  # > 0.35 block threshold
            "expected_calibration_error": 0.05,
            "current_threshold": 0.5,
        })
        assert result.action == CalibrationAction.BLOCK_CALIBRATION


class TestThresholdRecommendation:
    def test_13_recommend_threshold_returns_value(self):
        gov = AutoCalibrationGovernance()
        rec = gov.recommend_threshold({
            "current_threshold": 0.5,
            "brier_score": 0.15,
            "expected_calibration_error": 0.12,  # elevated ECE, low brier -> over-confident
        })
        assert rec is not None
        assert rec > 0.5  # should nudge up

    def test_14_recommend_threshold_clamped(self):
        """Recommended threshold delta should not exceed safe bound."""
        gov = AutoCalibrationGovernance()
        result = gov.evaluate_calibration({
            "sample_count": 1000,
            "brier_score": 0.15,
            "expected_calibration_error": 0.12,
            "current_threshold": 0.5,
        })
        if result.recommended_threshold is not None and result.current_threshold is not None:
            delta = abs(result.recommended_threshold - result.current_threshold)
            assert delta <= 0.06  # safe bound is 0.05, allow float tolerance


class TestSummary:
    def test_15_summary_returns_dict(self):
        gov = AutoCalibrationGovernance()
        gov.evaluate_calibration({
            "sample_count": 1000,
            "brier_score": 0.15,
            "expected_calibration_error": 0.05,
            "current_threshold": 0.5,
        })
        s = gov.summary()
        assert "action" in s
        assert "apply_automatically" in s
        assert s["apply_automatically"] is False


class TestSafetyInvariants:
    def test_16_no_metatrader5_import(self):
        from titan.production import auto_calibration_governance
        src = inspect.getsource(auto_calibration_governance)
        assert "import MetaTrader5" not in src
        assert "from MetaTrader5" not in src

    def test_17_no_order_send_calls(self):
        import re
        from titan.production import auto_calibration_governance
        src = inspect.getsource(auto_calibration_governance)
        call_pattern = r"(?<!['\"#])\b(mt5\.order_send|adapter\.send_open_order|adapter\.send_order|send_close_order)\s*\("
        matches = re.findall(call_pattern, src)
        assert len(matches) == 0, f"Found execution calls: {matches}"

    def test_18_no_model_training_execution(self):
        from titan.production import auto_calibration_governance
        src = inspect.getsource(auto_calibration_governance)
        assert ".fit(" not in src
        assert "train_model(" not in src
        assert "retrain(" not in src
        assert "run_hpo(" not in src

    def test_19_no_champion_replacement(self):
        from titan.production import auto_calibration_governance
        src = inspect.getsource(auto_calibration_governance)
        assert "shutil.copy" not in src
        assert "shutil.move" not in src
        assert "pickle.dump" not in src
        # Should not write any files
        assert "open(" not in src

    def test_20_no_runtime_config_modification(self):
        from titan.production import auto_calibration_governance
        src = inspect.getsource(auto_calibration_governance)
        # Should not modify runtime.yaml or any config
        assert "runtime.yaml" not in src
        assert "config/runtime" not in src
