"""
TITAN XAU AI — Exit Governance (Sprint 9.6)
=============================================

CEO AI governance layer for exit decisions.

Receives recommendations from:
  - Exit AI
  - Risk Engine
  - Capital Protection
  - Broker Intelligence
  - Meta Model
  - Context Engine
  - Account Health

Makes the FINAL exit decision using weighted confidence (NOT majority voting).

Each advisor provides:
  - recommended_action: ExitAction
  - confidence: 0-1
  - weight: configurable per advisor

CEO computes weighted vote per action and picks the highest.
Journals EventType.EXIT_GOVERNANCE on every decision.
"""
from __future__ import annotations

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from typing import Optional

from titan.production.trade_journal import TradeJournal, EventType
from titan.production.ai_exit_engine import ExitAction, ExitDecision

logger = logging.getLogger(__name__)


@dataclass
class AdvisorRecommendation:
    """Single advisor's exit recommendation."""
    advisor_name: str                    # "exit_ai" | "risk_engine" | etc.
    recommended_action: ExitAction
    confidence: float                    # 0-1
    weight: float                        # 0-1 (configured)
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "advisor": self.advisor_name,
            "action": self.recommended_action.value,
            "confidence": self.confidence,
            "weight": self.weight,
            "reason": self.reason,
        }


@dataclass
class GovernanceDecision:
    """Final CEO governance decision."""
    final_action: ExitAction
    final_confidence: float              # 0-1
    weighted_votes: dict                 # action → total weighted vote
    advisors: list[AdvisorRecommendation]
    reason: str
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "final_action": self.final_action.value,
            "final_confidence": self.final_confidence,
            "weighted_votes": {k: round(v, 4) for k, v in self.weighted_votes.items()},
            "advisors": [a.to_dict() for a in self.advisors],
            "reason": self.reason,
            "timestamp": self.timestamp,
        }


class ExitGovernance:
    """
    CEO AI governance for exits.

    Weighted confidence voting — NOT majority voting.
    Each advisor's vote = confidence × weight.
    Final action = action with highest total weighted vote.
    """

    def __init__(
        self,
        journal: Optional[TradeJournal] = None,
        weights: Optional[dict] = None,
    ):
        self.journal = journal
        self.weights = weights or {
            "exit_ai": 0.40,
            "risk_engine": 0.20,
            "capital_protection": 0.15,
            "broker_intelligence": 0.10,
            "meta_model": 0.10,
            "context_engine": 0.05,
        }
        self._decision_count: int = 0

    def decide(
        self,
        exit_ai_decision: ExitDecision,
        advisors: Optional[list[AdvisorRecommendation]] = None,
    ) -> GovernanceDecision:
        """
        Make final exit decision.

        Args:
            exit_ai_decision: Primary recommendation from AIExitEngine
            advisors: Additional advisor recommendations (optional)

        Returns:
            GovernanceDecision with final action + full audit trail
        """
        # Build advisor list (always includes exit_ai)
        all_advisors = [AdvisorRecommendation(
            advisor_name="exit_ai",
            recommended_action=exit_ai_decision.action,
            confidence=exit_ai_decision.confidence,
            weight=self.weights.get("exit_ai", 0.40),
            reason=exit_ai_decision.reason,
        )]
        if advisors:
            for a in advisors:
                # Apply configured weight
                a.weight = self.weights.get(a.advisor_name, 0.05)
                all_advisors.append(a)

        # Weighted voting
        weighted_votes: dict[str, float] = defaultdict(float)
        for advisor in all_advisors:
            vote = advisor.confidence * advisor.weight
            weighted_votes[advisor.recommended_action.value] += vote

        # Pick winner
        if weighted_votes:
            winner_action_str = max(weighted_votes, key=weighted_votes.get)
            winner_action = ExitAction(winner_action_str)
            total_votes = sum(weighted_votes.values())
            final_confidence = (
                weighted_votes[winner_action_str] / total_votes
                if total_votes > 0 else 0.0
            )
        else:
            winner_action = exit_ai_decision.action
            final_confidence = exit_ai_decision.confidence

        decision = GovernanceDecision(
            final_action=winner_action,
            final_confidence=final_confidence,
            weighted_votes=dict(weighted_votes),
            advisors=all_advisors,
            reason=f"weighted vote → {winner_action.value} (conf={final_confidence:.2f})",
        )

        self._decision_count += 1

        # Journal
        if self.journal is not None:
            try:
                self.journal.log_event(EventType.EXIT_GOVERNANCE, decision.to_dict())
            except Exception as e:
                logger.error(f"Journal EXIT_GOVERNANCE failed: {e}")

        return decision

    @property
    def decision_count(self) -> int:
        return self._decision_count
