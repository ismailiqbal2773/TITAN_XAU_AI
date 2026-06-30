"""
TITAN XAU AI — Observation Scorecard Engine (Sprint 9.9.3.33)
==============================================================

Scores daily forward observation quality. Never imports MT5, never sends orders.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class ObservationScoreGrade(str, Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


@dataclass
class ObservationScorecard:
    date_utc: str = ""
    observation_window_hours: float = 0.0
    total_events: int = 0
    signal_count: int = 0
    execution_intent_count: int = 0
    exit_intent_count: int = 0
    regime_count: int = 0
    runtime_health_count: int = 0
    broker_health_count: int = 0
    safety_block_count: int = 0
    observation_gap_count: int = 0
    unknown_count: int = 0
    final_open_positions: int = 0
    safety_score: float = 0.0       # 0-100
    completeness_score: float = 0.0  # 0-100
    execution_readiness_score: float = 0.0  # 0-100
    observation_quality_score: float = 0.0   # 0-100
    grade: ObservationScoreGrade = ObservationScoreGrade.INSUFFICIENT_DATA
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    timestamp_utc: str = ""

    def __post_init__(self):
        if not self.timestamp_utc:
            self.timestamp_utc = datetime.now(timezone.utc).isoformat()


class ObservationScorecardEngine:
    """Scores forward observation summaries into a daily scorecard."""

    def score(self, summary, final_open_positions: int = 0) -> ObservationScorecard:
        """Score a ForwardObservationSummary into an ObservationScorecard.

        Never raises — returns INSUFFICIENT_DATA on error.
        """
        try:
            card = ObservationScorecard(
                total_events=summary.total_events,
                signal_count=summary.signal_count,
                execution_intent_count=summary.execution_intent_count,
                exit_intent_count=summary.exit_intent_count,
                regime_count=summary.regime_count,
                runtime_health_count=summary.runtime_health_count,
                broker_health_count=summary.broker_health_count,
                safety_block_count=summary.safety_block_count,
                observation_gap_count=summary.observation_gap_count,
                unknown_count=summary.unknown_count,
                final_open_positions=final_open_positions,
                date_utc=summary.start_utc or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            )

            # Compute window hours
            if summary.start_utc and summary.end_utc:
                try:
                    start = datetime.fromisoformat(summary.start_utc.replace("Z", "+00:00"))
                    end = datetime.fromisoformat(summary.end_utc.replace("Z", "+00:00"))
                    card.observation_window_hours = (end - start).total_seconds() / 3600.0
                except Exception:
                    pass

            card.safety_score = self._compute_safety_score(card)
            card.completeness_score = self._compute_completeness_score(card)
            card.execution_readiness_score = self._compute_execution_readiness_score(card)
            card.observation_quality_score = self._compute_observation_quality_score(card)

            # Determine grade
            card.grade = self._determine_grade(card, summary)
            return card

        except Exception:
            return ObservationScorecard(
                grade=ObservationScoreGrade.INSUFFICIENT_DATA,
                blockers=["Scorecard exception"],
            )

    def _compute_safety_score(self, card: ObservationScorecard) -> float:
        """Safety score: 100 = no issues, 0 = critical failures."""
        score = 100.0
        # Final open positions > 0 is critical
        if card.final_open_positions > 0:
            score -= 50.0
        # Each safety block reduces score
        score -= min(card.safety_block_count * 15.0, 50.0)
        # Observation gaps reduce slightly
        score -= min(card.observation_gap_count * 5.0, 20.0)
        return max(score, 0.0)

    def _compute_completeness_score(self, card: ObservationScorecard) -> float:
        """Completeness: how well the journal covers required event types."""
        if card.total_events == 0:
            return 0.0
        # Check for presence of required event categories
        categories_present = 0
        total_categories = 6  # signal, execution, exit, regime, health, heartbeat
        if card.signal_count > 0:
            categories_present += 1
        if card.execution_intent_count > 0:
            categories_present += 1
        if card.exit_intent_count > 0:
            categories_present += 1
        if card.regime_count > 0:
            categories_present += 1
        if card.runtime_health_count > 0 or card.broker_health_count > 0:
            categories_present += 1
        if card.total_events - card.unknown_count > 0:
            categories_present += 1  # at least some known events
        base = (categories_present / total_categories) * 80.0
        # Unknown ratio penalty
        if card.total_events > 0:
            unknown_ratio = card.unknown_count / card.total_events
            base *= (1.0 - unknown_ratio * 0.5)
        return min(base, 100.0)

    def _compute_execution_readiness_score(self, card: ObservationScorecard) -> float:
        """Execution readiness: combines safety + completeness + signal evidence."""
        safety = card.safety_score / 100.0
        completeness = card.completeness_score / 100.0
        signal_factor = min(card.signal_count / 5.0, 1.0)  # need >= 5 signals
        intent_factor = min(card.execution_intent_count / 3.0, 1.0)  # need >= 3 intents
        return (safety * 0.4 + completeness * 0.3 + signal_factor * 0.15 + intent_factor * 0.15) * 100.0

    def _compute_observation_quality_score(self, card: ObservationScorecard) -> float:
        """Overall observation quality: weighted combination."""
        return (card.safety_score * 0.4 +
                card.completeness_score * 0.3 +
                card.execution_readiness_score * 0.3)

    def _determine_grade(self, card: ObservationScorecard, summary) -> ObservationScoreGrade:
        """Determine final grade based on scores and rules."""
        blockers = []
        warnings = []

        # INSUFFICIENT_DATA: no events
        if card.total_events == 0:
            return ObservationScoreGrade.INSUFFICIENT_DATA

        # FAIL: final_open_positions > 0
        if card.final_open_positions > 0:
            blockers.append(f"Final open positions = {card.final_open_positions} (must be 0)")

        # FAIL: severe safety blocks
        if card.safety_block_count > 0:
            blockers.append(f"{card.safety_block_count} safety block(s) observed")

        # WARN: observation gaps
        if card.observation_gap_count > 0:
            if card.observation_gap_count >= 5:
                blockers.append(f"{card.observation_gap_count} observation gaps (>= 5 = FAIL)")
            else:
                warnings.append(f"{card.observation_gap_count} observation gap(s)")

        # WARN: low completeness
        if card.completeness_score < 50:
            warnings.append(f"Low completeness score: {card.completeness_score:.0f}")

        # WARN: high unknown ratio
        if card.total_events > 0:
            unknown_ratio = card.unknown_count / card.total_events
            if unknown_ratio > 0.3:
                warnings.append(f"High unknown event ratio: {unknown_ratio:.0%}")

        card.blockers = blockers
        card.warnings = warnings

        if blockers:
            return ObservationScoreGrade.FAIL
        if warnings:
            return ObservationScoreGrade.WARN
        return ObservationScoreGrade.PASS
