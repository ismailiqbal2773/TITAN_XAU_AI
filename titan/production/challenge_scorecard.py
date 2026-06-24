"""
TITAN XAU AI — Challenge Scorecard (Sprint 9.0)
=================================================

Computes challenge progress from journal history + current equity state,
emits CHALLENGE_STATUS journal events every heartbeat.

Fields emitted:
  - profile_id
  - phase
  - target_pct
  - progress_pct       (current equity vs profit target)
  - daily_loss_pct
  - total_dd_pct
  - days_elapsed
  - min_days_met       (bool)
  - consistency_status (ok | breached | n/a)
  - weekend_status     (ok | flat_required | flat_failed)
  - rule_breaches      (list of breach IDs)
  - readiness_score    (0-100)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional

from titan.production.trade_journal import TradeJournal, EventType
from titan.production.prop_firm_manager import FirmProfile

logger = logging.getLogger(__name__)


@dataclass
class ChallengeState:
    """Snapshot of challenge state at evaluation time."""
    initial_balance: float
    current_balance: float
    current_equity: float
    peak_equity: float
    start_of_day_balance: float
    today_realized_pnl: float
    today_unrealized_pnl: float
    largest_single_day_profit: float
    total_realized_pnl: float
    challenge_start_date: datetime
    now: datetime
    open_positions: int = 0


@dataclass
class ChallengeStatus:
    """Computed challenge status — emitted as CHALLENGE_STATUS event."""
    profile_id: str
    phase: str
    target_pct: float
    progress_pct: float
    daily_loss_pct: float
    total_dd_pct: float
    days_elapsed: int
    min_days_met: bool
    consistency_status: str             # ok | breached | n/a
    weekend_status: str                 # ok | flat_required | flat_failed
    rule_breaches: list[str] = field(default_factory=list)
    readiness_score: float = 0.0

    def to_dict(self) -> dict:
        return {
            "profile_id": self.profile_id,
            "phase": self.phase,
            "target_pct": self.target_pct,
            "progress_pct": self.progress_pct,
            "daily_loss_pct": self.daily_loss_pct,
            "total_dd_pct": self.total_dd_pct,
            "days_elapsed": self.days_elapsed,
            "min_days_met": self.min_days_met,
            "consistency_status": self.consistency_status,
            "weekend_status": self.weekend_status,
            "rule_breaches": self.rule_breaches,
            "readiness_score": self.readiness_score,
        }


class ChallengeScorecard:
    """
    Computes ChallengeStatus from ChallengeState + FirmProfile.

    Usage:
        sc = ChallengeScorecard(journal=journal)
        status = sc.evaluate(profile=profile, state=state)
        # status is automatically journaled as CHALLENGE_STATUS event
    """

    def __init__(self, journal: Optional[TradeJournal] = None):
        self.journal = journal

    def evaluate(
        self,
        profile: FirmProfile,
        state: ChallengeState,
    ) -> ChallengeStatus:
        """Compute challenge status and emit CHALLENGE_STATUS journal event."""
        now = state.now

        # Days elapsed
        if state.challenge_start_date.tzinfo is None:
            start = state.challenge_start_date.replace(tzinfo=timezone.utc)
        else:
            start = state.challenge_start_date
        days_elapsed = max(0, (now - start).days)

        # Progress toward profit target
        if profile.profit_target_pct > 0 and profile.initial_balance > 0:
            profit_needed = profile.initial_balance * profile.profit_target_pct
            current_profit = state.current_equity - profile.initial_balance
            progress_pct = (current_profit / profit_needed) * 100 if profit_needed > 0 else 0.0
        else:
            # Funded phase: no target, progress is "still alive"
            progress_pct = 100.0 if state.current_equity >= profile.initial_balance else 0.0

        # Daily loss (relative to start of day balance)
        if state.start_of_day_balance > 0:
            daily_loss_pct = (
                (state.start_of_day_balance - state.current_equity)
                / state.start_of_day_balance
            ) * 100
        else:
            daily_loss_pct = 0.0

        # Total drawdown (peak equity based — works for both static and trailing)
        if state.peak_equity > 0:
            total_dd_pct = (
                (state.peak_equity - state.current_equity) / state.peak_equity
            ) * 100
        else:
            total_dd_pct = 0.0

        # Min trading days met?
        min_days_met = days_elapsed >= profile.min_trading_days

        # Consistency check (if enabled)
        if profile.consistency_rule_enabled and profile.consistency_pct > 0:
            if state.total_realized_pnl > 0:
                single_day_share = (
                    state.largest_single_day_profit / state.total_realized_pnl
                ) if state.total_realized_pnl > 0 else 0.0
                consistency_status = (
                    "ok" if single_day_share <= profile.consistency_pct else "breached"
                )
            else:
                consistency_status = "n/a"
        else:
            consistency_status = "n/a"

        # Weekend status
        is_weekend = now.weekday() >= 5  # Sat=5, Sun=6
        if profile.weekend_close_required:
            if is_weekend and state.open_positions > 0:
                weekend_status = "flat_failed"
            elif is_weekend:
                weekend_status = "ok"
            else:
                # Friday after 21:00 UTC = should be flat
                is_friday_late = (now.weekday() == 4 and now.hour >= 21)
                if is_friday_late and state.open_positions > 0:
                    weekend_status = "flat_required"
                else:
                    weekend_status = "ok"
        else:
            weekend_status = "ok"

        # Rule breaches
        rule_breaches: list[str] = []
        if daily_loss_pct > profile.max_daily_loss_pct * 100:
            rule_breaches.append("DAILY_LOSS_BREACH")
        if total_dd_pct > profile.max_total_loss_pct * 100:
            rule_breaches.append("OVERALL_DD_BREACH")
        if consistency_status == "breached":
            rule_breaches.append("CONSISTENCY_BREACH")
        if weekend_status == "flat_failed":
            rule_breaches.append("WEEKEND_HOLDING_BREACH")

        # Readiness score (0-100) — higher is better
        # Start at 100, subtract for each issue
        score = 100.0
        score -= min(50, max(0, daily_loss_pct / (profile.max_daily_loss_pct * 100) * 30))
        score -= min(40, max(0, total_dd_pct / (profile.max_total_loss_pct * 100) * 30))
        if not min_days_met:
            score -= 10
        if consistency_status == "breached":
            score -= 15
        if weekend_status == "flat_failed":
            score -= 20
        score = max(0.0, min(100.0, score))

        status = ChallengeStatus(
            profile_id=profile.profile_id,
            phase=profile.phase,
            target_pct=profile.profit_target_pct * 100,
            progress_pct=round(progress_pct, 2),
            daily_loss_pct=round(daily_loss_pct, 4),
            total_dd_pct=round(total_dd_pct, 4),
            days_elapsed=days_elapsed,
            min_days_met=min_days_met,
            consistency_status=consistency_status,
            weekend_status=weekend_status,
            rule_breaches=rule_breaches,
            readiness_score=round(score, 1),
        )

        # Journal the event
        if self.journal is not None:
            try:
                self.journal.log_event(EventType.CHALLENGE_STATUS, status.to_dict())
            except Exception as e:
                logger.error(f"Failed to journal CHALLENGE_STATUS: {e}")

        return status
