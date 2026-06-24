"""
TITAN XAU AI — Dynamic Risk Engine (Sprint 9.2)
=================================================

Maps account health score to a risk profile and computes:
  - risk_multiplier       (0.0 to 1.0)
  - max_exposure_multiplier (0.0 to 1.0)
  - allow_new_entries     (bool)
  - profile_name          (normal | slight_reduction | defensive | recovery_mode | capital_preservation)

Health → Profile mapping:
  90-100 → normal                (1.0× risk, 1.0× exposure, entries allowed)
  75-89  → slight_reduction      (0.75× risk, 0.75× exposure, entries allowed)
  50-74  → defensive             (0.5× risk, 0.5× exposure, entries allowed)
  25-49  → recovery_mode         (0.25× risk, 0.25× exposure, entries allowed)
  0-24   → capital_preservation  (0.0× risk, 0.0× exposure, NO new entries)

Safety: risk can only DECREASE below baseline, never increase.
All transitions journaled via EventType.RISK_PROFILE_CHANGED.

Usage:
    engine = DynamicRiskEngine(journal=journal)
    profile = engine.evaluate(health_score=85.0)
    # profile.risk_multiplier=0.75, profile.name="slight_reduction"
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field, asdict
from typing import Optional

from titan.production.trade_journal import TradeJournal, EventType
from titan.production.account_health_engine import (
    score_to_band,
    HEALTH_BAND_NORMAL,
    HEALTH_BAND_SLIGHT_REDUCTION,
    HEALTH_BAND_DEFENSIVE,
    HEALTH_BAND_RECOVERY,
    HEALTH_BAND_CAPITAL_PRESERVATION,
)

logger = logging.getLogger(__name__)


# ─── Profile definitions ────────────────────────────────────────────────────
@dataclass
class RiskProfile:
    """Single risk profile corresponding to a health band."""
    name: str                          # band name
    min_health: int                    # minimum health score for this profile
    risk_multiplier: float             # 0.0 to 1.0
    max_exposure_multiplier: float     # 0.0 to 1.0
    allow_new_entries: bool
    description: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# Default profiles (can be overridden via config)
DEFAULT_PROFILES: list[RiskProfile] = [
    RiskProfile(
        name=HEALTH_BAND_NORMAL,
        min_health=90,
        risk_multiplier=1.0,
        max_exposure_multiplier=1.0,
        allow_new_entries=True,
        description="Normal trading — full risk and exposure",
    ),
    RiskProfile(
        name=HEALTH_BAND_SLIGHT_REDUCTION,
        min_health=75,
        risk_multiplier=0.75,
        max_exposure_multiplier=0.75,
        allow_new_entries=True,
        description="Slight reduction — 75% risk and exposure",
    ),
    RiskProfile(
        name=HEALTH_BAND_DEFENSIVE,
        min_health=50,
        risk_multiplier=0.5,
        max_exposure_multiplier=0.5,
        allow_new_entries=True,
        description="Defensive — 50% risk and exposure",
    ),
    RiskProfile(
        name=HEALTH_BAND_RECOVERY,
        min_health=25,
        risk_multiplier=0.25,
        max_exposure_multiplier=0.25,
        allow_new_entries=True,
        description="Recovery mode — 25% risk, high-confidence trades only",
    ),
    RiskProfile(
        name=HEALTH_BAND_CAPITAL_PRESERVATION,
        min_health=0,
        risk_multiplier=0.0,
        max_exposure_multiplier=0.0,
        allow_new_entries=False,
        description="Capital preservation — no new entries, flatten only",
    ),
]


@dataclass
class DynamicRiskEvaluation:
    """Result of a dynamic risk evaluation."""
    profile: RiskProfile
    health_score: float
    timestamp: float = field(default_factory=time.time)

    @property
    def risk_multiplier(self) -> float:
        return self.profile.risk_multiplier

    @property
    def max_exposure_multiplier(self) -> float:
        return self.profile.max_exposure_multiplier

    @property
    def allow_new_entries(self) -> bool:
        return self.profile.allow_new_entries

    @property
    def profile_name(self) -> str:
        return self.profile.name

    def to_dict(self) -> dict:
        return {
            "profile": self.profile.to_dict(),
            "health_score": self.health_score,
            "timestamp": self.timestamp,
        }


class DynamicRiskEngine:
    """
    Maps health score to risk profile. Journals all transitions.

    Safety: risk_multiplier and max_exposure_multiplier are always in [0.0, 1.0].
    The engine NEVER returns a profile with risk_multiplier > 1.0 — capital
    protection can only DECREASE risk, never increase.
    """

    def __init__(
        self,
        journal: Optional[TradeJournal] = None,
        profiles: Optional[list[RiskProfile]] = None,
    ):
        self.journal = journal
        # Sort profiles by min_health descending so we can pick the highest
        # band whose min_health <= score.
        self.profiles = sorted(
            profiles or DEFAULT_PROFILES,
            key=lambda p: p.min_health,
            reverse=True,
        )
        self._last_profile_name: Optional[str] = None
        self._evaluation_count: int = 0

    def evaluate(self, health_score: float) -> DynamicRiskEvaluation:
        """Map health score to risk profile. Journals RISK_PROFILE_CHANGED on transitions."""
        health_score = max(0.0, min(100.0, float(health_score)))
        profile = self._select_profile(health_score)
        result = DynamicRiskEvaluation(
            profile=profile,
            health_score=health_score,
        )
        self._evaluation_count += 1

        # Journal transition if profile changed
        if (self._last_profile_name is not None
                and profile.name != self._last_profile_name):
            self._journal_event(EventType.RISK_PROFILE_CHANGED, {
                "from_profile": self._last_profile_name,
                "to_profile": profile.name,
                "health_score": health_score,
                "new_risk_multiplier": profile.risk_multiplier,
                "new_max_exposure_multiplier": profile.max_exposure_multiplier,
                "new_allow_new_entries": profile.allow_new_entries,
            })
            logger.info(
                f"RISK PROFILE CHANGED: {self._last_profile_name} → "
                f"{profile.name} (health={health_score:.1f}, "
                f"risk_mult={profile.risk_multiplier})"
            )

        self._last_profile_name = profile.name
        return result

    @property
    def last_profile_name(self) -> Optional[str]:
        return self._last_profile_name

    @property
    def evaluation_count(self) -> int:
        return self._evaluation_count

    # ─── Internal ─────────────────────────────────────────────────────────

    def _select_profile(self, health_score: float) -> RiskProfile:
        """Pick the profile with the highest min_health <= health_score."""
        for profile in self.profiles:
            if health_score >= profile.min_health:
                return profile
        # Fallback: return the last (lowest) profile
        return self.profiles[-1]

    def _journal_event(self, event_type: EventType, data: dict) -> None:
        if self.journal is None:
            return
        try:
            self.journal.log_event(event_type, data)
        except Exception as e:
            logger.error(f"Journal event {event_type.value} failed: {e}")
