"""
TITAN XAU AI — Sprint 9.2 DynamicRiskEngine Unit Tests
"""
from __future__ import annotations
import pytest

from titan.production.dynamic_risk_engine import (
    DynamicRiskEngine, DynamicRiskEvaluation, RiskProfile,
    DEFAULT_PROFILES,
)
from titan.production.account_health_engine import (
    HEALTH_BAND_NORMAL, HEALTH_BAND_SLIGHT_REDUCTION,
    HEALTH_BAND_DEFENSIVE, HEALTH_BAND_RECOVERY,
    HEALTH_BAND_CAPITAL_PRESERVATION,
)
from titan.production.trade_journal import TradeJournal, EventType


@pytest.fixture
def journal(tmp_path):
    return TradeJournal(path=str(tmp_path / "drisk.jsonl"), session_id="drisk_test")


@pytest.fixture
def engine(journal):
    return DynamicRiskEngine(journal=journal)


class TestDynamicRiskEngine:
    def test_score_95_returns_normal_profile(self, engine):
        result = engine.evaluate(95.0)
        assert result.profile.name == HEALTH_BAND_NORMAL
        assert result.risk_multiplier == 1.0
        assert result.allow_new_entries is True

    def test_score_85_returns_slight_reduction(self, engine):
        result = engine.evaluate(85.0)
        assert result.profile.name == HEALTH_BAND_SLIGHT_REDUCTION
        assert result.risk_multiplier == 0.75
        assert result.allow_new_entries is True

    def test_score_60_returns_defensive(self, engine):
        result = engine.evaluate(60.0)
        assert result.profile.name == HEALTH_BAND_DEFENSIVE
        assert result.risk_multiplier == 0.5
        assert result.allow_new_entries is True

    def test_score_35_returns_recovery_mode(self, engine):
        result = engine.evaluate(35.0)
        assert result.profile.name == HEALTH_BAND_RECOVERY
        assert result.risk_multiplier == 0.25
        assert result.allow_new_entries is True

    def test_score_10_returns_capital_preservation(self, engine):
        result = engine.evaluate(10.0)
        assert result.profile.name == HEALTH_BAND_CAPITAL_PRESERVATION
        assert result.risk_multiplier == 0.0
        assert result.allow_new_entries is False

    def test_score_clamped_to_0_100(self, engine):
        r1 = engine.evaluate(-10.0)
        assert r1.profile.name == HEALTH_BAND_CAPITAL_PRESERVATION
        engine._last_profile_name = None  # reset
        r2 = engine.evaluate(150.0)
        assert r2.profile.name == HEALTH_BAND_NORMAL

    def test_risk_multiplier_never_exceeds_1(self, engine):
        """Capital protection can only DECREASE risk, never increase."""
        for score in [0, 25, 50, 75, 90, 100]:
            engine._last_profile_name = None  # avoid transition spam
            result = engine.evaluate(float(score))
            assert result.risk_multiplier <= 1.0
            assert result.max_exposure_multiplier <= 1.0

    def test_transition_journaled_on_profile_change(self, engine, journal):
        engine.evaluate(95.0)  # normal
        engine.evaluate(35.0)  # recovery
        records = journal.read_all()
        transitions = [r for r in records if r.get("event_type") == EventType.RISK_PROFILE_CHANGED.value]
        assert len(transitions) == 1
        assert transitions[0]["data"]["from_profile"] == HEALTH_BAND_NORMAL
        assert transitions[0]["data"]["to_profile"] == HEALTH_BAND_RECOVERY

    def test_no_transition_on_same_profile(self, engine, journal):
        engine.evaluate(95.0)
        engine.evaluate(95.0)
        records = journal.read_all()
        transitions = [r for r in records if r.get("event_type") == EventType.RISK_PROFILE_CHANGED.value]
        assert len(transitions) == 0

    def test_default_profiles_count(self):
        assert len(DEFAULT_PROFILES) == 5

    def test_custom_profiles_can_be_passed(self, journal):
        custom = [
            RiskProfile(name="custom_high", min_health=80,
                        risk_multiplier=0.9, max_exposure_multiplier=0.9,
                        allow_new_entries=True),
            RiskProfile(name="custom_low", min_health=0,
                        risk_multiplier=0.1, max_exposure_multiplier=0.1,
                        allow_new_entries=True),
        ]
        eng = DynamicRiskEngine(journal=journal, profiles=custom)
        result = eng.evaluate(85.0)
        assert result.profile.name == "custom_high"
        eng._last_profile_name = None
        result = eng.evaluate(50.0)
        assert result.profile.name == "custom_low"

    def test_evaluation_count(self, engine):
        for s in [10, 30, 60, 85, 95]:
            engine._last_profile_name = None
            engine.evaluate(float(s))
        assert engine.evaluation_count == 5
