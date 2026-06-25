"""
TITAN XAU AI — Exit Quality Scorer (Sprint 9.6)
==================================================

Scores every exit 0-100 based on 5 components:
  - Timing          (exited at optimal time?)
  - Profit efficiency (captured % of max favorable excursion)
  - Risk reduction   (did exit reduce risk?)
  - Trend capture    (held through trend, exited when trend weakened?)
  - Drawdown avoidance (exited before deep DD?)

Journals EventType.EXIT_SCORE on every exit.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field, asdict
from typing import Optional

from titan.production.trade_journal import TradeJournal, EventType

logger = logging.getLogger(__name__)


@dataclass
class ExitQualityInput:
    """Inputs for exit quality scoring."""
    # Position info
    entry_price: float = 0.0
    exit_price: float = 0.0
    direction: int = 1                  # +1 long, -1 short
    max_favorable_price: float = 0.0    # MFE — best price during trade
    max_adverse_price: float = 0.0      # MAE — worst price during trade
    # Timing
    entry_time: float = 0.0
    exit_time: float = 0.0
    optimal_exit_time: float = 0.0      # when MFE was reached
    # PnL
    realized_pnl_usd: float = 0.0
    max_floating_profit_usd: float = 0.0
    max_floating_loss_usd: float = 0.0
    # Market context at exit
    trend_strength_at_exit: float = 0.0
    # Risk metrics
    initial_risk_usd: float = 0.0       # |entry - SL| × contract × volume
    drawdown_avoided_pct: float = 0.0   # how much DD avoided by exiting


@dataclass
class ExitQualityScore:
    """Computed exit quality score."""
    score: float                         # 0-100
    components: dict                     # per-component 0-100
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "score": round(self.score, 2),
            "components": {k: round(v, 2) for k, v in self.components.items()},
            "timestamp": self.timestamp,
        }


class ExitQualityScorer:
    """Scores exit quality. Journals EXIT_SCORE."""

    def __init__(self, journal: Optional[TradeJournal] = None):
        self.journal = journal

    def score(self, inp: ExitQualityInput) -> ExitQualityScore:
        components = {
            "timing": self._score_timing(inp),
            "profit_efficiency": self._score_profit_efficiency(inp),
            "risk_reduction": self._score_risk_reduction(inp),
            "trend_capture": self._score_trend_capture(inp),
            "drawdown_avoidance": self._score_drawdown_avoidance(inp),
        }
        score = sum(components.values()) / len(components)
        score = max(0.0, min(100.0, score))

        result = ExitQualityScore(score=score, components=components)

        if self.journal is not None:
            try:
                self.journal.log_event(EventType.EXIT_SCORE, result.to_dict() | {
                    "realized_pnl_usd": inp.realized_pnl_usd,
                    "max_floating_profit": inp.max_floating_profit_usd,
                    "entry_price": inp.entry_price,
                    "exit_price": inp.exit_price,
                })
            except Exception as e:
                logger.error(f"Journal EXIT_SCORE failed: {e}")

        return result

    def _score_timing(self, inp: ExitQualityInput) -> float:
        """Did we exit near the optimal time (MFE)?"""
        if inp.optimal_exit_time <= 0 or inp.exit_time <= 0:
            return 50.0  # no data
        diff = abs(inp.exit_time - inp.optimal_exit_time)
        max_diff = max(1.0, inp.exit_time - inp.entry_time)
        ratio = diff / max_diff
        return max(0.0, 100.0 * (1.0 - ratio))

    def _score_profit_efficiency(self, inp: ExitQualityInput) -> float:
        """How much of MFE was captured?"""
        if inp.max_floating_profit_usd <= 0:
            return 50.0  # neutral — no profit to capture
        efficiency = inp.realized_pnl_usd / inp.max_floating_profit_usd
        return max(0.0, min(100.0, efficiency * 100))

    def _score_risk_reduction(self, inp: ExitQualityInput) -> float:
        """Did exit reduce risk? (positive PnL = good risk reduction)"""
        if inp.realized_pnl_usd > 0:
            return 100.0
        if inp.realized_pnl_usd == 0:
            return 50.0
        # Loss — did we limit it?
        if inp.initial_risk_usd > 0:
            loss_ratio = abs(inp.realized_pnl_usd) / inp.initial_risk_usd
            if loss_ratio < 1.0:
                return 75.0  # exited before full SL
            return 25.0  # hit full SL
        return 25.0

    def _score_trend_capture(self, inp: ExitQualityInput) -> float:
        """Held through trend, exited when trend weakened?"""
        if inp.trend_strength_at_exit * inp.direction > 0.3:
            return 40.0  # exited while trend still strong — suboptimal
        if inp.trend_strength_at_exit * inp.direction < 0:
            return 90.0  # exited after trend reversed — good
        return 70.0  # exited when trend neutral — acceptable

    def _score_drawdown_avoidance(self, inp: ExitQualityInput) -> float:
        """Did we avoid deeper drawdown?"""
        return max(0.0, min(100.0, inp.drawdown_avoided_pct))
