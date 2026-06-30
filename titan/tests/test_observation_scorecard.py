"""TITAN XAU AI — Sprint 9.9.3.33 Observation Scorecard Tests"""
from __future__ import annotations
import sys
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from titan.production.observation_scorecard import (
    ObservationScorecardEngine, ObservationScorecard, ObservationScoreGrade,
)
from titan.production.forward_observation import (
    ForwardObservationSummary, ForwardObservationEventType,
)


class TestScorecardGrades:
    def _summary(self, **kw):
        defaults = dict(total_events=10, signal_count=3, execution_intent_count=2,
                         exit_intent_count=1, regime_count=1, runtime_health_count=1,
                         broker_health_count=1, safety_block_count=0,
                         observation_gap_count=0, unknown_count=0,
                         start_utc="2026-06-29T08:00:00Z", end_utc="2026-06-29T20:00:00Z",
                         safe_to_continue_observation=True, blockers=[], warnings=[])
        defaults.update(kw)
        return ForwardObservationSummary(**defaults)

    def test_01_pass_with_healthy_summary(self):
        eng = ObservationScorecardEngine()
        card = eng.score(self._summary(), final_open_positions=0)
        assert card.grade == ObservationScoreGrade.PASS
        assert card.safety_score == 100.0

    def test_02_warn_with_observation_gaps(self):
        eng = ObservationScorecardEngine()
        card = eng.score(self._summary(observation_gap_count=2), final_open_positions=0)
        assert card.grade == ObservationScoreGrade.WARN
        assert len(card.warnings) >= 1

    def test_03_fail_with_open_positions(self):
        eng = ObservationScorecardEngine()
        card = eng.score(self._summary(), final_open_positions=1)
        assert card.grade == ObservationScoreGrade.FAIL
        assert any("open positions" in b.lower() for b in card.blockers)

    def test_04_fail_with_safety_blocks(self):
        eng = ObservationScorecardEngine()
        card = eng.score(self._summary(safety_block_count=1), final_open_positions=0)
        assert card.grade == ObservationScoreGrade.FAIL
        assert any("safety block" in b.lower() for b in card.blockers)

    def test_05_insufficient_data_when_no_events(self):
        eng = ObservationScorecardEngine()
        card = eng.score(self._summary(total_events=0, signal_count=0,
                                         execution_intent_count=0, exit_intent_count=0,
                                         regime_count=0, runtime_health_count=0,
                                         broker_health_count=0), final_open_positions=0)
        assert card.grade == ObservationScoreGrade.INSUFFICIENT_DATA

    def test_06_fail_with_excessive_gaps(self):
        eng = ObservationScorecardEngine()
        card = eng.score(self._summary(observation_gap_count=6), final_open_positions=0)
        assert card.grade == ObservationScoreGrade.FAIL


class TestScoreCalculations:
    def _summary(self, **kw):
        defaults = dict(total_events=10, signal_count=3, execution_intent_count=2,
                         exit_intent_count=1, regime_count=1, runtime_health_count=1,
                         broker_health_count=1, safety_block_count=0,
                         observation_gap_count=0, unknown_count=0,
                         start_utc="2026-06-29T08:00:00Z", end_utc="2026-06-29T20:00:00Z",
                         safe_to_continue_observation=True, blockers=[], warnings=[])
        defaults.update(kw)
        return ForwardObservationSummary(**defaults)

    def test_07_safety_score_100_when_clean(self):
        eng = ObservationScorecardEngine()
        card = eng.score(self._summary(), final_open_positions=0)
        assert card.safety_score == 100.0

    def test_08_safety_score_reduced_by_open_positions(self):
        eng = ObservationScorecardEngine()
        card = eng.score(self._summary(), final_open_positions=1)
        assert card.safety_score < 100.0

    def test_09_safety_score_reduced_by_safety_blocks(self):
        eng = ObservationScorecardEngine()
        card = eng.score(self._summary(safety_block_count=2), final_open_positions=0)
        assert card.safety_score < 100.0

    def test_10_completeness_score_nonzero_with_events(self):
        eng = ObservationScorecardEngine()
        card = eng.score(self._summary(), final_open_positions=0)
        assert card.completeness_score > 0

    def test_11_completeness_score_zero_with_no_events(self):
        eng = ObservationScorecardEngine()
        card = eng.score(self._summary(total_events=0, signal_count=0,
                                         execution_intent_count=0, exit_intent_count=0,
                                         regime_count=0, runtime_health_count=0,
                                         broker_health_count=0), final_open_positions=0)
        assert card.completeness_score == 0.0

    def test_12_execution_readiness_score_calculated(self):
        eng = ObservationScorecardEngine()
        card = eng.score(self._summary(), final_open_positions=0)
        assert 0 < card.execution_readiness_score <= 100

    def test_13_observation_quality_score_calculated(self):
        eng = ObservationScorecardEngine()
        card = eng.score(self._summary(), final_open_positions=0)
        assert 0 < card.observation_quality_score <= 100

    def test_14_unknown_ratio_reduces_completeness(self):
        eng = ObservationScorecardEngine()
        card_high_unknown = eng.score(self._summary(unknown_count=8), final_open_positions=0)
        card_low_unknown = eng.score(self._summary(unknown_count=0), final_open_positions=0)
        assert card_high_unknown.completeness_score < card_low_unknown.completeness_score


class TestFailSafe:
    def test_15_exception_returns_insufficient_data(self):
        eng = ObservationScorecardEngine()
        card = eng.score(None)  # type: ignore
        assert card.grade == ObservationScoreGrade.INSUFFICIENT_DATA

    def test_16_all_fields_present(self):
        card = ObservationScorecard()
        required = ["date_utc", "observation_window_hours", "total_events",
                     "signal_count", "execution_intent_count", "exit_intent_count",
                     "regime_count", "runtime_health_count", "broker_health_count",
                     "safety_block_count", "observation_gap_count", "unknown_count",
                     "final_open_positions", "safety_score", "completeness_score",
                     "execution_readiness_score", "observation_quality_score",
                     "grade", "blockers", "warnings", "timestamp_utc"]
        for f in required:
            assert hasattr(card, f), f"Missing field: {f}"
