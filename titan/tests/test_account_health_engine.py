"""
TITAN XAU AI — Sprint 9.2 AccountHealthEngine Unit Tests
"""
from __future__ import annotations
import pytest

from titan.production.account_health_engine import (
    AccountHealthEngine, AccountHealthInput, HealthWeights,
    score_to_band,
    HEALTH_BAND_NORMAL, HEALTH_BAND_SLIGHT_REDUCTION,
    HEALTH_BAND_DEFENSIVE, HEALTH_BAND_RECOVERY,
    HEALTH_BAND_CAPITAL_PRESERVATION,
)
from titan.production.trade_journal import TradeJournal, EventType


@pytest.fixture
def journal(tmp_path):
    return TradeJournal(path=str(tmp_path / "health.jsonl"), session_id="health_test")


@pytest.fixture
def engine(journal):
    return AccountHealthEngine(journal=journal)


class TestScoreToBand:
    def test_90_to_100_is_normal(self):
        assert score_to_band(90) == HEALTH_BAND_NORMAL
        assert score_to_band(95) == HEALTH_BAND_NORMAL
        assert score_to_band(100) == HEALTH_BAND_NORMAL

    def test_75_to_89_is_slight_reduction(self):
        assert score_to_band(75) == HEALTH_BAND_SLIGHT_REDUCTION
        assert score_to_band(85) == HEALTH_BAND_SLIGHT_REDUCTION
        assert score_to_band(89) == HEALTH_BAND_SLIGHT_REDUCTION

    def test_50_to_74_is_defensive(self):
        assert score_to_band(50) == HEALTH_BAND_DEFENSIVE
        assert score_to_band(60) == HEALTH_BAND_DEFENSIVE
        assert score_to_band(74) == HEALTH_BAND_DEFENSIVE

    def test_25_to_49_is_recovery(self):
        assert score_to_band(25) == HEALTH_BAND_RECOVERY
        assert score_to_band(35) == HEALTH_BAND_RECOVERY
        assert score_to_band(49) == HEALTH_BAND_RECOVERY

    def test_0_to_24_is_capital_preservation(self):
        assert score_to_band(0) == HEALTH_BAND_CAPITAL_PRESERVATION
        assert score_to_band(10) == HEALTH_BAND_CAPITAL_PRESERVATION
        assert score_to_band(24) == HEALTH_BAND_CAPITAL_PRESERVATION


class TestAccountHealthEngine:
    def test_perfect_inputs_yield_high_score(self, engine):
        inp = AccountHealthInput(
            daily_dd_pct=0.0, total_dd_pct=0.0,
            max_daily_dd_limit_pct=5.0, max_total_dd_limit_pct=10.0,
            consecutive_losses=0, winning_streak=5,
            equity_slope=0.5, volatility_regime="normal",
            kill_switch_state="NORMAL", in_recovery_mode=False,
        )
        result = engine.evaluate(inp)
        assert result.score >= 90
        assert result.band == HEALTH_BAND_NORMAL

    def test_catastrophic_inputs_yield_low_score(self, engine):
        inp = AccountHealthInput(
            daily_dd_pct=4.9, total_dd_pct=9.9,
            max_daily_dd_limit_pct=5.0, max_total_dd_limit_pct=10.0,
            consecutive_losses=5, winning_streak=0,
            equity_slope=-0.5, volatility_regime="extreme",
            kill_switch_state="EMERGENCY_STOP", in_recovery_mode=True,
            recovery_progress=0.0,
        )
        result = engine.evaluate(inp)
        assert result.score < 25
        assert result.band == HEALTH_BAND_CAPITAL_PRESERVATION

    def test_zero_dd_normal_ks_yields_normal_band(self, engine):
        inp = AccountHealthInput(
            daily_dd_pct=0.0, total_dd_pct=0.0,
            consecutive_losses=0, winning_streak=0,
            equity_slope=0.0, volatility_regime="normal",
            kill_switch_state="NORMAL",
        )
        result = engine.evaluate(inp)
        # Should be high but not perfect (winning_streak=0 → 50, slope=0 → 50)
        assert 75 <= result.score <= 95
        assert result.band in (HEALTH_BAND_NORMAL, HEALTH_BAND_SLIGHT_REDUCTION)

    def test_kill_switch_caution_reduces_score(self, engine):
        good_inp = AccountHealthInput(
            daily_dd_pct=0.0, total_dd_pct=0.0,
            consecutive_losses=0, winning_streak=3,
            equity_slope=0.5, volatility_regime="normal",
            kill_switch_state="NORMAL",
        )
        caution_inp = AccountHealthInput(
            daily_dd_pct=0.0, total_dd_pct=0.0,
            consecutive_losses=0, winning_streak=3,
            equity_slope=0.5, volatility_regime="normal",
            kill_switch_state="CAUTION",
        )
        good = engine.evaluate(good_inp)
        # Reset engine state for second eval (avoid transition journaling confusion)
        engine._last_band = None
        engine._last_score = None
        caution = engine.evaluate(caution_inp)
        assert caution.score < good.score

    def test_consecutive_losses_lower_score(self, engine):
        engine.evaluate(AccountHealthInput(consecutive_losses=0))
        engine._last_band = None; engine._last_score = None
        s0 = engine.evaluate(AccountHealthInput(consecutive_losses=0)).score
        engine._last_band = None; engine._last_score = None
        s3 = engine.evaluate(AccountHealthInput(consecutive_losses=3)).score
        engine._last_band = None; engine._last_score = None
        s5 = engine.evaluate(AccountHealthInput(consecutive_losses=5)).score
        assert s0 > s3 > s5

    def test_health_event_journaled(self, engine, journal):
        engine.evaluate(AccountHealthInput())
        records = journal.read_all()
        health_events = [r for r in records if r.get("event_type") == EventType.ACCOUNT_HEALTH.value]
        assert len(health_events) == 1

    def test_transition_event_journaled_on_band_change(self, engine, journal):
        # First eval: perfect → NORMAL
        engine.evaluate(AccountHealthInput(
            daily_dd_pct=0.0, total_dd_pct=0.0,
            consecutive_losses=0, winning_streak=5,
            equity_slope=0.5, kill_switch_state="NORMAL",
        ))
        # Second eval: catastrophic → CAPITAL_PRESERVATION
        engine.evaluate(AccountHealthInput(
            daily_dd_pct=4.9, total_dd_pct=9.9,
            max_daily_dd_limit_pct=5.0, max_total_dd_limit_pct=10.0,
            consecutive_losses=5, winning_streak=0,
            equity_slope=-0.5, volatility_regime="extreme",
            kill_switch_state="EMERGENCY_STOP",
            in_recovery_mode=True, recovery_progress=0.0,
        ))
        records = journal.read_all()
        transitions = [r for r in records if r.get("event_type") == EventType.HEALTH_TRANSITION.value]
        assert len(transitions) == 1
        assert transitions[0]["data"]["from_band"] == HEALTH_BAND_NORMAL
        assert transitions[0]["data"]["to_band"] == HEALTH_BAND_CAPITAL_PRESERVATION

    def test_no_transition_event_on_same_band(self, engine, journal):
        # Two evals in same band → no transition
        engine.evaluate(AccountHealthInput(kill_switch_state="NORMAL"))
        engine.evaluate(AccountHealthInput(kill_switch_state="NORMAL"))
        records = journal.read_all()
        transitions = [r for r in records if r.get("event_type") == EventType.HEALTH_TRANSITION.value]
        assert len(transitions) == 0

    def test_score_always_in_0_100(self, engine):
        # Extreme inputs both directions
        for _ in range(10):
            inp = AccountHealthInput(
                daily_dd_pct=-5.0, total_dd_pct=-5.0,
                consecutive_losses=-3, winning_streak=10,
                equity_slope=2.0,
            )
            result = engine.evaluate(inp)
            assert 0.0 <= result.score <= 100.0

    def test_weights_normalized(self):
        w = HealthWeights(daily_dd=2.0, total_dd=2.0, consecutive_losses=1.0,
                          winning_streak=1.0, equity_slope=1.0,
                          volatility_regime=0.5, kill_switch_state=1.5,
                          recovery_status=0.5)
        nw = w.normalized()
        total = (nw.daily_dd + nw.total_dd + nw.consecutive_losses
                 + nw.winning_streak + nw.equity_slope
                 + nw.volatility_regime + nw.kill_switch_state
                 + nw.recovery_status)
        assert abs(total - 1.0) < 0.001

    def test_evaluation_count(self, engine):
        for _ in range(5):
            engine.evaluate(AccountHealthInput())
        assert engine.evaluation_count == 5
