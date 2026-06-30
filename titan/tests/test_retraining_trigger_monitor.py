"""TITAN XAU AI - Sprint 9.9.3.37 Retraining Trigger Monitor Tests"""
from __future__ import annotations
import inspect, sys
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from titan.production.retraining_trigger_monitor import (
    RetrainingTriggerMonitor, RetrainingTriggerSignal,
    TriggerSeverity, TriggerRecommendation,
)
from titan.production.offline_retraining_pipeline import RetrainingTrigger


class TestPerformanceDecay:
    def test_01_performance_decay_triggers_review(self):
        mon = RetrainingTriggerMonitor()
        signal = mon.evaluate_performance_decay({
            "current_sharpe": 1.0,
            "baseline_sharpe": 2.0,  # 50% drop
            "sample_count": 200,
        })
        assert signal.severity == TriggerSeverity.CRITICAL
        assert signal.recommended == TriggerRecommendation.NEEDS_REVIEW
        assert "decay" in signal.reason.lower()

    def test_02_minor_decay_triggers_review(self):
        mon = RetrainingTriggerMonitor()
        signal = mon.evaluate_performance_decay({
            "current_sharpe": 1.8,
            "baseline_sharpe": 2.0,  # 10% drop
            "sample_count": 200,
        })
        assert signal.severity == TriggerSeverity.WARNING
        assert signal.recommended == TriggerRecommendation.NEEDS_REVIEW

    def test_03_no_decay_no_action(self):
        mon = RetrainingTriggerMonitor()
        signal = mon.evaluate_performance_decay({
            "current_sharpe": 2.1,
            "baseline_sharpe": 2.0,
            "sample_count": 200,
        })
        assert signal.recommended == TriggerRecommendation.NO_ACTION

    def test_04_insufficient_data_no_trigger(self):
        mon = RetrainingTriggerMonitor()
        signal = mon.evaluate_performance_decay({
            "current_sharpe": 1.0,
            "baseline_sharpe": 2.0,
            "sample_count": 50,  # below MIN_SAMPLE_COUNT_FOR_TRIGGER
        })
        assert signal.recommended == TriggerRecommendation.INSUFFICIENT_DATA


class TestCalibrationDrift:
    def test_05_calibration_drift_triggers_review(self):
        mon = RetrainingTriggerMonitor()
        signal = mon.evaluate_calibration_drift({
            "current_brier": 0.30,
            "baseline_brier": 0.15,  # 0.15 delta > 0.05 threshold
            "sample_count": 200,
        })
        assert signal.severity == TriggerSeverity.CRITICAL
        assert signal.recommended == TriggerRecommendation.NEEDS_REVIEW

    def test_06_minor_drift_triggers_review(self):
        mon = RetrainingTriggerMonitor()
        signal = mon.evaluate_calibration_drift({
            "current_brier": 0.18,
            "baseline_brier": 0.15,  # 0.03 delta
            "sample_count": 200,
        })
        assert signal.severity == TriggerSeverity.WARNING
        assert signal.recommended == TriggerRecommendation.NEEDS_REVIEW

    def test_07_insufficient_data_no_trigger(self):
        mon = RetrainingTriggerMonitor()
        signal = mon.evaluate_calibration_drift({
            "current_brier": 0.30,
            "baseline_brier": 0.15,
            "sample_count": 50,
        })
        assert signal.recommended == TriggerRecommendation.INSUFFICIENT_DATA


class TestRegimeShift:
    def test_08_regime_shift_triggers_review(self):
        mon = RetrainingTriggerMonitor()
        signal = mon.evaluate_regime_shift({
            "regime_shift_confidence": 0.85,  # > 0.70 threshold
            "sample_count": 200,
        })
        assert signal.severity == TriggerSeverity.CRITICAL
        assert signal.recommended == TriggerRecommendation.NEEDS_REVIEW

    def test_09_minor_shift_triggers_review(self):
        mon = RetrainingTriggerMonitor()
        signal = mon.evaluate_regime_shift({
            "regime_shift_confidence": 0.60,  # between 0.5 and 0.7
            "sample_count": 200,
        })
        assert signal.severity == TriggerSeverity.WARNING
        assert signal.recommended == TriggerRecommendation.NEEDS_REVIEW

    def test_10_insufficient_data_no_trigger(self):
        mon = RetrainingTriggerMonitor()
        signal = mon.evaluate_regime_shift({
            "regime_shift_confidence": 0.85,
            "sample_count": 50,
        })
        assert signal.recommended == TriggerRecommendation.INSUFFICIENT_DATA


class TestBrokerDegradation:
    def test_11_broker_degradation_triggers_review(self):
        mon = RetrainingTriggerMonitor()
        signal = mon.evaluate_broker_degradation({
            "current_winrate": 0.50,
            "baseline_winrate": 0.65,  # 15% drop > 10% threshold
            "sample_count": 200,
        })
        assert signal.severity == TriggerSeverity.CRITICAL
        assert signal.recommended == TriggerRecommendation.NEEDS_REVIEW

    def test_12_minor_degradation_triggers_review(self):
        mon = RetrainingTriggerMonitor()
        signal = mon.evaluate_broker_degradation({
            "current_winrate": 0.62,
            "baseline_winrate": 0.65,  # 3% drop
            "sample_count": 200,
        })
        assert signal.severity == TriggerSeverity.WARNING
        assert signal.recommended == TriggerRecommendation.NEEDS_REVIEW

    def test_13_insufficient_data_no_trigger(self):
        mon = RetrainingTriggerMonitor()
        signal = mon.evaluate_broker_degradation({
            "current_winrate": 0.50,
            "baseline_winrate": 0.65,
            "sample_count": 50,
        })
        assert signal.recommended == TriggerRecommendation.INSUFFICIENT_DATA


class TestScheduleDue:
    def test_14_schedule_due_triggers_review(self):
        mon = RetrainingTriggerMonitor()
        signal = mon.evaluate_schedule_due({
            "days_since_last_retraining": 100,
            "schedule_interval_days": 90,
        })
        assert signal.recommended == TriggerRecommendation.NEEDS_REVIEW

    def test_15_schedule_not_due_no_action(self):
        mon = RetrainingTriggerMonitor()
        signal = mon.evaluate_schedule_due({
            "days_since_last_retraining": 30,
            "schedule_interval_days": 90,
        })
        assert signal.recommended == TriggerRecommendation.NO_ACTION


class TestRecommendTrigger:
    def test_16_aggregate_picks_most_severe(self):
        mon = RetrainingTriggerMonitor()
        # All evaluators will be called with mixed signals
        signal = mon.recommend_trigger({
            "current_sharpe": 1.0,
            "baseline_sharpe": 2.0,
            "current_brier": 0.18,
            "baseline_brier": 0.15,
            "regime_shift_confidence": 0.60,
            "current_winrate": 0.62,
            "baseline_winrate": 0.65,
            "days_since_last_retraining": 30,
            "schedule_interval_days": 90,
            "sample_count": 200,
        })
        # Performance decay is CRITICAL, others are WARNING/INFO
        assert signal.severity == TriggerSeverity.CRITICAL
        # Cap at NEEDS_REVIEW
        assert signal.recommended == TriggerRecommendation.NEEDS_REVIEW

    def test_17_aggregate_insufficient_data_when_all_insufficient(self):
        mon = RetrainingTriggerMonitor()
        signal = mon.recommend_trigger({
            "sample_count": 10,  # below all minimums
        })
        assert signal.recommended == TriggerRecommendation.INSUFFICIENT_DATA

    def test_18_recommendation_capped_at_needs_review(self):
        """Monitor should never auto-recommend RECOMMEND_RETRAINING."""
        mon = RetrainingTriggerMonitor()
        signal = mon.recommend_trigger({
            "current_sharpe": 0.5,
            "baseline_sharpe": 2.0,
            "current_brier": 0.40,
            "baseline_brier": 0.15,
            "regime_shift_confidence": 0.90,
            "current_winrate": 0.40,
            "baseline_winrate": 0.65,
            "days_since_last_retraining": 200,
            "schedule_interval_days": 90,
            "sample_count": 500,
        })
        # Even with all critical signals, recommendation is capped
        assert signal.recommended != TriggerRecommendation.RECOMMEND_RETRAINING


class TestSignalDataclass:
    def test_19_signal_has_all_required_fields(self):
        s = RetrainingTriggerSignal(
            trigger=RetrainingTrigger.PERFORMANCE_DECAY,
            severity=TriggerSeverity.WARNING,
            reason="test",
        )
        required = ["trigger", "severity", "reason", "metrics",
                    "recommended", "timestamp_utc"]
        for f in required:
            assert hasattr(s, f), f"Missing: {f}"

    def test_20_signal_defaults_to_needs_review(self):
        s = RetrainingTriggerSignal(
            trigger=RetrainingTrigger.PERFORMANCE_DECAY,
            severity=TriggerSeverity.WARNING,
            reason="test",
        )
        assert s.recommended == TriggerRecommendation.NEEDS_REVIEW


class TestSafetyInvariants:
    def test_21_no_metatrader5_import(self):
        from titan.production import retraining_trigger_monitor
        src = inspect.getsource(retraining_trigger_monitor)
        assert "import MetaTrader5" not in src
        assert "from MetaTrader5" not in src

    def test_22_no_order_send_calls(self):
        import re
        from titan.production import retraining_trigger_monitor
        src = inspect.getsource(retraining_trigger_monitor)
        call_pattern = r"(?<!['\"#])\b(mt5\.order_send|adapter\.send_open_order|adapter\.send_order|send_close_order)\s*\("
        matches = re.findall(call_pattern, src)
        assert len(matches) == 0, f"Found execution calls: {matches}"

    def test_23_no_model_training_execution(self):
        import re
        from titan.production import retraining_trigger_monitor
        # Strip docstrings to check actual code only
        src_raw = inspect.getsource(retraining_trigger_monitor)
        src = re.sub(r'"""[\s\S]*?"""', '""', src_raw)
        src = re.sub(r"'''[\s\S]*?'''", "''", src)
        call_pattern = r"\b(\w+\.fit|train_model|retrain|run_hpo)\s*\("
        matches = re.findall(call_pattern, src)
        assert len(matches) == 0, f"Found training calls: {matches}"

    def test_24_no_runtime_config_modification(self):
        from titan.production import retraining_trigger_monitor
        src = inspect.getsource(retraining_trigger_monitor)
        assert "runtime.yaml" not in src
        assert "config/runtime" not in src
        # Should not write any files (no open() calls for writing)
        import re
        write_pattern = r"open\s*\([^)]*['\"][^'\"]*['\"],\s*['\"]w"
        matches = re.findall(write_pattern, src)
        assert len(matches) == 0, f"Found file write calls: {matches}"

    def test_25_summary_returns_dict(self):
        mon = RetrainingTriggerMonitor()
        s = mon.summary()
        assert "auto_launches_training" in s
        assert s["auto_launches_training"] is False
        assert s["default_recommendation"] == "NEEDS_REVIEW"
