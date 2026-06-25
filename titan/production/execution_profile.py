"""
TITAN XAU AI — Execution Profile Selector (Sprint 9.5)
=========================================================

Auto-selects execution profile based on broker quality score + broker info.

8 profiles:
  - ultra_low_spread  (institutional, ECN/RAW, score ≥95)
  - ecn               (excellent, ECN, score 85-94)
  - raw               (excellent, RAW, score 85-94)
  - prop_challenge    (prop firm, score 75+)
  - retail            (retail standard, score 75+)
  - cent              (cent account, score 60+)
  - aggressive        (high score, large account)
  - conservative      (low score or unknown)

Each profile defines:
  - risk_multiplier       (0.0-1.0, can only DECREASE)
  - max_lot_multiplier    (0.0-1.0)
  - max_open_positions    (1, hard cap)
  - atr_profile           (challenge | balanced | production_aggressive)
  - news_blackout_minutes (int)
  - spread_guard_usd      (max allowed spread)
  - allow_new_entries     (bool)

Journals EventType.BROKER_PROFILE_SELECTED + EXECUTION_PROFILE_CHANGED.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field, asdict
from typing import Optional

from titan.production.trade_journal import TradeJournal, EventType
from titan.production.broker_quality_engine import (
    BrokerQualityScore, score_to_band,
    BAND_INSTITUTIONAL, BAND_EXCELLENT, BAND_GOOD, BAND_AVERAGE, BAND_UNSAFE,
)

logger = logging.getLogger(__name__)


@dataclass
class ExecutionProfile:
    """Single execution profile."""
    name: str
    risk_multiplier: float              # 0.0-1.0
    max_lot_multiplier: float           # 0.0-1.0
    max_open_positions: int             # hard cap = 1
    atr_profile: str                    # challenge | balanced | production_aggressive
    news_blackout_minutes: int
    spread_guard_usd: float
    allow_new_entries: bool
    description: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# ─── 8 execution profiles ────────────────────────────────────────────────────
PROFILES: dict[str, ExecutionProfile] = {
    "ultra_low_spread": ExecutionProfile(
        name="ultra_low_spread",
        risk_multiplier=1.0,
        max_lot_multiplier=1.0,
        max_open_positions=1,
        atr_profile="production_aggressive",
        news_blackout_minutes=15,
        spread_guard_usd=0.50,
        allow_new_entries=True,
        description="Institutional ECN with ultra-low spread. Full risk, aggressive ATR.",
    ),
    "ecn": ExecutionProfile(
        name="ecn",
        risk_multiplier=1.0,
        max_lot_multiplier=1.0,
        max_open_positions=1,
        atr_profile="balanced",
        news_blackout_minutes=20,
        spread_guard_usd=0.80,
        allow_new_entries=True,
        description="ECN broker, excellent quality. Full risk, balanced ATR.",
    ),
    "raw": ExecutionProfile(
        name="raw",
        risk_multiplier=1.0,
        max_lot_multiplier=1.0,
        max_open_positions=1,
        atr_profile="balanced",
        news_blackout_minutes=20,
        spread_guard_usd=0.80,
        allow_new_entries=True,
        description="RAW spread broker, excellent quality. Full risk, balanced ATR.",
    ),
    "prop_challenge": ExecutionProfile(
        name="prop_challenge",
        risk_multiplier=1.0,
        max_lot_multiplier=1.0,
        max_open_positions=1,
        atr_profile="challenge",           # 1.5/3.0 — safest
        news_blackout_minutes=30,
        spread_guard_usd=1.00,
        allow_new_entries=True,
        description="Prop firm challenge. Conservative ATR, full risk within prop limits.",
    ),
    "retail": ExecutionProfile(
        name="retail",
        risk_multiplier=0.8,
        max_lot_multiplier=1.0,
        max_open_positions=1,
        atr_profile="balanced",
        news_blackout_minutes=30,
        spread_guard_usd=1.00,
        allow_new_entries=True,
        description="Retail standard account. 80% risk, balanced ATR.",
    ),
    "cent": ExecutionProfile(
        name="cent",
        risk_multiplier=0.5,
        max_lot_multiplier=1.0,
        max_open_positions=1,
        atr_profile="balanced",
        news_blackout_minutes=30,
        spread_guard_usd=1.50,
        allow_new_entries=True,
        description="Cent account. 50% risk (high leverage caution), balanced ATR.",
    ),
    "aggressive": ExecutionProfile(
        name="aggressive",
        risk_multiplier=1.0,
        max_lot_multiplier=1.0,
        max_open_positions=1,
        atr_profile="production_aggressive",
        news_blackout_minutes=15,
        spread_guard_usd=0.50,
        allow_new_entries=True,
        description="Aggressive — high score + large account. Full risk, aggressive ATR.",
    ),
    "conservative": ExecutionProfile(
        name="conservative",
        risk_multiplier=0.5,
        max_lot_multiplier=0.5,
        max_open_positions=1,
        atr_profile="challenge",
        news_blackout_minutes=45,
        spread_guard_usd=2.00,
        allow_new_entries=True,
        description="Conservative — low/unknown broker quality. 50% risk, challenge ATR.",
    ),
    "unsafe": ExecutionProfile(
        name="unsafe",
        risk_multiplier=0.0,
        max_lot_multiplier=0.0,
        max_open_positions=0,
        atr_profile="challenge",
        news_blackout_minutes=60,
        spread_guard_usd=0.50,
        allow_new_entries=False,
        description="Unsafe — broker quality below 60. NO new entries, flatten only.",
    ),
}


# ─── Selector ────────────────────────────────────────────────────────────────
class ExecutionProfileSelector:
    """
    Auto-selects execution profile from broker quality + broker info.

    Selection logic:
      1. If score band = unsafe → "unsafe" (no entries)
      2. If broker is prop firm → "prop_challenge"
      3. If broker is cent → "cent"
      4. If score band = institutional + ECN/RAW → "ultra_low_spread"
      5. If score band = excellent + ECN → "ecn"
      6. If score band = excellent + RAW → "raw"
      7. If score band = good + retail → "retail"
      8. If score band = good + large account → "aggressive"
      9. Fallback → "conservative"

    Journals BROKER_PROFILE_SELECTED on selection + EXECUTION_PROFILE_CHANGED
    on transition.
    """

    def __init__(
        self,
        journal: Optional[TradeJournal] = None,
        thresholds: Optional[dict] = None,
    ):
        self.journal = journal
        self.thresholds = thresholds or {
            "institutional_min": 95,
            "excellent_min": 85,
            "good_min": 75,
            "average_min": 60,
        }
        self._last_profile_name: Optional[str] = None
        self._evaluation_count: int = 0

    def select(
        self,
        quality_score: BrokerQualityScore,
        broker_info=None,
    ) -> ExecutionProfile:
        """Select execution profile. Journals selection + transition."""
        profile_name = self._select_name(quality_score, broker_info)
        profile = PROFILES.get(profile_name, PROFILES["conservative"])

        self._evaluation_count += 1

        # Journal selection
        self._journal_event(EventType.BROKER_PROFILE_SELECTED, {
            "profile_name": profile_name,
            "quality_score": quality_score.score,
            "quality_band": quality_score.band,
            "broker_name": broker_info.broker_name if broker_info else "unknown",
            "account_category": broker_info.account_category if broker_info else "unknown",
            "account_spread_type": broker_info.account_spread_type if broker_info else "unknown",
            "profile": profile.to_dict(),
        })

        # Journal transition if changed
        if (self._last_profile_name is not None
                and profile_name != self._last_profile_name):
            self._journal_event(EventType.EXECUTION_PROFILE_CHANGED, {
                "from_profile": self._last_profile_name,
                "to_profile": profile_name,
                "quality_score": quality_score.score,
                "quality_band": quality_score.band,
            })
            logger.info(
                f"Execution profile changed: {self._last_profile_name} → "
                f"{profile_name} (quality={quality_score.score:.1f})"
            )

        self._last_profile_name = profile_name
        return profile

    @property
    def last_profile_name(self) -> Optional[str]:
        return self._last_profile_name

    @property
    def evaluation_count(self) -> int:
        return self._evaluation_count

    # ─── Internal ─────────────────────────────────────────────────────────

    def _select_name(self, quality_score: BrokerQualityScore, broker_info) -> str:
        """Determine profile name from quality + broker info."""
        score = quality_score.score
        band = quality_score.band

        # Step 1: unsafe → halt
        if band == BAND_UNSAFE or score < self.thresholds["average_min"]:
            return "unsafe"

        # Step 2: prop firm → prop_challenge (regardless of score, as long as ≥ average)
        if broker_info is not None and broker_info.is_prop:
            return "prop_challenge"

        # Step 3: cent account
        if broker_info is not None and broker_info.account_size == "cent":
            return "cent"

        # Step 4-6: institutional / excellent
        if score >= self.thresholds["institutional_min"]:
            if broker_info is not None and broker_info.is_ecn:
                return "ultra_low_spread"
            return "aggressive"

        if score >= self.thresholds["excellent_min"]:
            if broker_info is not None:
                if broker_info.account_spread_type == "ecn":
                    return "ecn"
                if broker_info.account_spread_type == "raw":
                    return "raw"
            return "ecn"  # default for excellent

        # Step 7-8: good
        if score >= self.thresholds["good_min"]:
            if broker_info is not None and broker_info.is_retail:
                return "retail"
            return "aggressive"

        # Step 9: average → conservative
        return "conservative"

    def _journal_event(self, event_type: EventType, data: dict) -> None:
        if self.journal is None:
            return
        try:
            self.journal.log_event(event_type, data)
        except Exception as e:
            logger.error(f"Journal event {event_type.value} failed: {e}")
