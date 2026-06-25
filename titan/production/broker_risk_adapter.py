"""
TITAN XAU AI — Broker Risk Adapter (Sprint 9.5)
=================================================

Adapts risk parameters based on broker quality score.

Mapping (broker quality → risk multiplier):
  Institutional (95-100) → 1.0  (full risk, hard cap)
  Excellent    (85-94)  → 1.0
  Good         (75-84)  → 0.8
  Average      (60-74)  → 0.6
  Unsafe       (<60)    → 0.0  (halt)

Safety: risk_multiplier is ALWAYS in [0.0, 1.0]. Broker quality can only
DECREASE risk, never increase. Hard cap MAX_LOT_CAP=0.01 always enforced
downstream by TradeLoop.

Applies to:
  - risk_multiplier       (affects trade_loop.config.max_lot)
  - max_open_positions    (capped at 1)
  - news_blackout_minutes (may increase for poor quality)
  - spread_guard_usd      (may tighten for poor quality)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, asdict
from typing import Optional

from titan.production.trade_journal import TradeJournal, EventType
from titan.production.broker_quality_engine import (
    BrokerQualityScore, score_to_band,
    BAND_INSTITUTIONAL, BAND_EXCELLENT, BAND_GOOD, BAND_AVERAGE, BAND_UNSAFE,
)
from titan.production.execution_profile import ExecutionProfile

logger = logging.getLogger(__name__)


@dataclass
class RiskAdaptation:
    """Result of broker-quality-driven risk adaptation."""
    risk_multiplier: float              # 0.0-1.0
    max_lot_multiplier: float           # 0.0-1.0
    max_open_positions: int             # capped at 1
    news_blackout_minutes: int
    spread_guard_usd: float
    allow_new_entries: bool
    quality_score: float
    quality_band: str
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


# ─── Adapter ─────────────────────────────────────────────────────────────────
class BrokerRiskAdapter:
    """
    Adapts risk based on broker quality.

    Usage:
        adapter = BrokerRiskAdapter(journal=journal, multipliers={...})
        adaptation = adapter.adapt(quality_score, execution_profile)
        # Apply adaptation.risk_multiplier to trade_loop.config.max_lot
    """

    def __init__(
        self,
        journal: Optional[TradeJournal] = None,
        multipliers: Optional[dict] = None,
    ):
        self.journal = journal
        # Default multipliers — can only DECREASE risk (≤1.0)
        self.multipliers = multipliers or {
            BAND_INSTITUTIONAL: 1.0,
            BAND_EXCELLENT: 1.0,
            BAND_GOOD: 0.8,
            BAND_AVERAGE: 0.6,
            BAND_UNSAFE: 0.0,
        }
        self._last_adaptation: Optional[RiskAdaptation] = None

    def adapt(
        self,
        quality_score: BrokerQualityScore,
        profile: ExecutionProfile,
    ) -> RiskAdaptation:
        """
        Compute risk adaptation from quality score + execution profile.

        The final risk_multiplier = min(profile.risk_multiplier, band_multiplier).
        This ensures broker quality can only DECREASE risk below what the
        execution profile allows, never increase it.
        """
        band = quality_score.band
        band_mult = self.multipliers.get(band, 0.5)

        # Final multiplier = min(profile, band) — most conservative wins
        final_risk_mult = min(profile.risk_multiplier, band_mult)
        final_max_lot_mult = min(profile.max_lot_multiplier, band_mult)

        # Allow new entries only if both profile AND band allow
        allow_entries = profile.allow_new_entries and band_mult > 0.0

        # Tighten spread guard for poor quality
        if band == BAND_UNSAFE:
            spread_guard = 0.50  # very tight — almost nothing will pass
            news_blackout = 60
        elif band == BAND_AVERAGE:
            spread_guard = min(profile.spread_guard_usd, 1.50)
            news_blackout = max(profile.news_blackout_minutes, 45)
        else:
            spread_guard = profile.spread_guard_usd
            news_blackout = profile.news_blackout_minutes

        adaptation = RiskAdaptation(
            risk_multiplier=final_risk_mult,
            max_lot_multiplier=final_max_lot_mult,
            max_open_positions=min(profile.max_open_positions, 1),
            news_blackout_minutes=news_blackout,
            spread_guard_usd=spread_guard,
            allow_new_entries=allow_entries,
            quality_score=quality_score.score,
            quality_band=band,
            reason=f"band={band}, band_mult={band_mult}, profile={profile.name}",
        )

        self._last_adaptation = adaptation
        return adaptation

    @property
    def last_adaptation(self) -> Optional[RiskAdaptation]:
        return self._last_adaptation

    def apply_to_trade_loop(self, adaptation: RiskAdaptation, loop_config) -> None:
        """
        Apply adaptation to a TradeLoopConfig (in-place).

        Safety: max_lot can only DECREASE. Hard cap MAX_LOT_CAP=0.01
        is enforced inside TradeLoop.__init__.
        """
        from titan.production.trade_loop import MAX_LOT_CAP

        # Compute effective max_lot = base_max_lot × max_lot_multiplier
        # but never exceed MAX_LOT_CAP
        effective_max_lot = min(
            MAX_LOT_CAP * adaptation.max_lot_multiplier,
            MAX_LOT_CAP,
        )
        # Floor at 0.001 so we don't completely zero out (unless unsafe)
        if adaptation.risk_multiplier > 0:
            effective_max_lot = max(0.001, effective_max_lot)
        else:
            effective_max_lot = 0.0

        loop_config.max_lot = effective_max_lot
        loop_config.max_open_positions = min(adaptation.max_open_positions, 1)
        loop_config.max_spread_usd = adaptation.spread_guard_usd
