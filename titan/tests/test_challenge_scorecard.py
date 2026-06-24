"""
TITAN XAU AI — Sprint 9.0 Challenge Scorecard Unit Tests
"""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

from titan.production.challenge_scorecard import (
    ChallengeScorecard, ChallengeState, ChallengeStatus,
)
from titan.production.prop_firm_manager import PropFirmProfileManager
from titan.production.trade_journal import TradeJournal, EventType


REPO_ROOT = Path(__file__).resolve().parents[2]
PROFILES_YAML = REPO_ROOT / "config" / "prop_firm_profiles.yaml"


@pytest.fixture
def journal(tmp_path):
    return TradeJournal(path=str(tmp_path / "scorecard_journal.jsonl"), session_id="sc_test")


@pytest.fixture
def mgr(journal):
    return PropFirmProfileManager(
        profiles_path=str(PROFILES_YAML),
        journal=journal,
    )


@pytest.fixture
def scorecard(journal):
    return ChallengeScorecard(journal=journal)


class TestChallengeScorecard:
    def test_status_emitted_on_evaluate(self, scorecard, mgr, journal):
        profile = mgr.load_profile("ftmo_challenge")
        now = datetime.now(timezone.utc)
        state = ChallengeState(
            initial_balance=100000.0,
            current_balance=100000.0,
            current_equity=100000.0,
            peak_equity=100000.0,
            start_of_day_balance=100000.0,
            today_realized_pnl=0.0,
            today_unrealized_pnl=0.0,
            largest_single_day_profit=0.0,
            total_realized_pnl=0.0,
            challenge_start_date=now - timedelta(days=2),
            now=now,
        )
        status = scorecard.evaluate(profile, state)
        assert isinstance(status, ChallengeStatus)
        assert status.profile_id == "ftmo_challenge"
        assert status.phase == "challenge"
        # Journal event emitted
        records = journal.read_all()
        status_events = [r for r in records if r.get("event_type") == EventType.CHALLENGE_STATUS.value]
        assert len(status_events) == 1

    def test_progress_pct_zero_at_start(self, scorecard, mgr):
        profile = mgr.load_profile("ftmo_challenge")
        now = datetime.now(timezone.utc)
        state = ChallengeState(
            initial_balance=100000.0,
            current_balance=100000.0,
            current_equity=100000.0,
            peak_equity=100000.0,
            start_of_day_balance=100000.0,
            today_realized_pnl=0.0,
            today_unrealized_pnl=0.0,
            largest_single_day_profit=0.0,
            total_realized_pnl=0.0,
            challenge_start_date=now,
            now=now,
        )
        status = scorecard.evaluate(profile, state)
        assert status.progress_pct == 0.0

    def test_progress_pct_50_at_halfway(self, scorecard, mgr):
        profile = mgr.load_profile("ftmo_challenge")  # 10% target
        now = datetime.now(timezone.utc)
        state = ChallengeState(
            initial_balance=100000.0,
            current_balance=105000.0,
            current_equity=105000.0,  # +5% = 50% of 10% target
            peak_equity=105000.0,
            start_of_day_balance=100000.0,
            today_realized_pnl=5000.0,
            today_unrealized_pnl=0.0,
            largest_single_day_profit=5000.0,
            total_realized_pnl=5000.0,
            challenge_start_date=now - timedelta(days=2),
            now=now,
        )
        status = scorecard.evaluate(profile, state)
        assert status.progress_pct == 50.0

    def test_min_days_met(self, scorecard, mgr):
        profile = mgr.load_profile("ftmo_challenge")  # 4 min days
        now = datetime.now(timezone.utc)
        state = ChallengeState(
            initial_balance=100000.0,
            current_balance=100000.0,
            current_equity=100000.0,
            peak_equity=100000.0,
            start_of_day_balance=100000.0,
            today_realized_pnl=0.0,
            today_unrealized_pnl=0.0,
            largest_single_day_profit=0.0,
            total_realized_pnl=0.0,
            challenge_start_date=now - timedelta(days=5),  # 5 > 4
            now=now,
        )
        status = scorecard.evaluate(profile, state)
        assert status.min_days_met is True

    def test_min_days_not_met(self, scorecard, mgr):
        profile = mgr.load_profile("ftmo_challenge")  # 4 min days
        now = datetime.now(timezone.utc)
        state = ChallengeState(
            initial_balance=100000.0,
            current_balance=110000.0,
            current_equity=110000.0,  # hit target
            peak_equity=110000.0,
            start_of_day_balance=100000.0,
            today_realized_pnl=10000.0,
            today_unrealized_pnl=0.0,
            largest_single_day_profit=10000.0,
            total_realized_pnl=10000.0,
            challenge_start_date=now - timedelta(days=2),  # only 2 days
            now=now,
        )
        status = scorecard.evaluate(profile, state)
        assert status.min_days_met is False
        assert "days_elapsed" in status.to_dict()

    def test_daily_loss_breach_detected(self, scorecard, mgr):
        profile = mgr.load_profile("ftmo_challenge")  # 5% daily loss
        now = datetime.now(timezone.utc)
        state = ChallengeState(
            initial_balance=100000.0,
            current_balance=100000.0,
            current_equity=94000.0,  # -6% from start-of-day (breach 5%)
            peak_equity=100000.0,
            start_of_day_balance=100000.0,
            today_realized_pnl=-6000.0,
            today_unrealized_pnl=0.0,
            largest_single_day_profit=0.0,
            total_realized_pnl=-6000.0,
            challenge_start_date=now,
            now=now,
        )
        status = scorecard.evaluate(profile, state)
        assert "DAILY_LOSS_BREACH" in status.rule_breaches

    def test_consistency_breach_detected(self, scorecard, mgr):
        profile = mgr.load_profile("ftmo_challenge")  # 40% consistency
        now = datetime.now(timezone.utc)
        state = ChallengeState(
            initial_balance=100000.0,
            current_balance=105000.0,
            current_equity=105000.0,
            peak_equity=105000.0,
            start_of_day_balance=100000.0,
            today_realized_pnl=4500.0,
            today_unrealized_pnl=0.0,
            largest_single_day_profit=4500.0,  # 90% of 5000 total
            total_realized_pnl=5000.0,
            challenge_start_date=now - timedelta(days=5),
            now=now,
        )
        status = scorecard.evaluate(profile, state)
        assert status.consistency_status == "breached"
        assert "CONSISTENCY_BREACH" in status.rule_breaches

    def test_readiness_score_decreases_with_loss(self, scorecard, mgr):
        profile = mgr.load_profile("ftmo_challenge")
        now = datetime.now(timezone.utc)

        # Healthy state
        healthy_state = ChallengeState(
            initial_balance=100000.0,
            current_balance=100000.0,
            current_equity=100000.0,
            peak_equity=100000.0,
            start_of_day_balance=100000.0,
            today_realized_pnl=0.0,
            today_unrealized_pnl=0.0,
            largest_single_day_profit=0.0,
            total_realized_pnl=0.0,
            challenge_start_date=now - timedelta(days=5),
            now=now,
        )
        healthy = scorecard.evaluate(profile, healthy_state)

        # Loss state
        loss_state = ChallengeState(
            initial_balance=100000.0,
            current_balance=95000.0,
            current_equity=95000.0,  # -5% from start of day
            peak_equity=100000.0,
            start_of_day_balance=100000.0,
            today_realized_pnl=-5000.0,
            today_unrealized_pnl=0.0,
            largest_single_day_profit=0.0,
            total_realized_pnl=-5000.0,
            challenge_start_date=now - timedelta(days=5),
            now=now,
        )
        loss = scorecard.evaluate(profile, loss_state)

        assert loss.readiness_score < healthy.readiness_score

    def test_funded_phase_no_target_progress(self, scorecard, mgr):
        profile = mgr.load_profile("ftmo_funded")  # profit_target=0
        now = datetime.now(timezone.utc)
        state = ChallengeState(
            initial_balance=100000.0,
            current_balance=100000.0,
            current_equity=100000.0,
            peak_equity=100000.0,
            start_of_day_balance=100000.0,
            today_realized_pnl=0.0,
            today_unrealized_pnl=0.0,
            largest_single_day_profit=0.0,
            total_realized_pnl=0.0,
            challenge_start_date=now - timedelta(days=10),
            now=now,
        )
        status = scorecard.evaluate(profile, state)
        # Funded phase: progress is "still alive" = 100% if equity >= initial
        assert status.progress_pct == 100.0
        assert status.target_pct == 0.0
