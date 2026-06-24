"""
TITAN XAU AI — Account Health Engine (Sprint 9.2)
====================================================

Computes an institutional account health score (0-100) from 8 inputs:
  - Daily drawdown
  - Total drawdown
  - Consecutive losses
  - Winning streak (positive contribution)
  - Equity slope (positive = healthy)
  - Volatility regime
  - Kill switch state
  - Recovery status

Score semantics:
  90-100 → Normal            (full trading)
  75-89  → Slight reduction  (75% risk)
  50-74  → Defensive         (50% risk)
  25-49  → Recovery Mode     (25% risk, high-confidence trades only)
  0-24   → Capital Preservation (no new entries, flatten-only)

Journal events:
  - EventType.ACCOUNT_HEALTH     (every heartbeat)
  - EventType.HEALTH_TRANSITION  (on score band change)

Usage:
    engine = AccountHealthEngine(journal=journal, config=cfg)
    score = engine.evaluate(AccountHealthInput(...))
    # score is 0-100, automatically journaled
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field, asdict
from typing import Optional

from titan.production.trade_journal import TradeJournal, EventType

logger = logging.getLogger(__name__)


# ─── Health bands ────────────────────────────────────────────────────────────
HEALTH_BAND_NORMAL = "normal"                       # 90-100
HEALTH_BAND_SLIGHT_REDUCTION = "slight_reduction"   # 75-89
HEALTH_BAND_DEFENSIVE = "defensive"                 # 50-74
HEALTH_BAND_RECOVERY = "recovery_mode"              # 25-49
HEALTH_BAND_CAPITAL_PRESERVATION = "capital_preservation"  # 0-24


def score_to_band(score: float) -> str:
    """Map health score (0-100) to band name."""
    if score >= 90:
        return HEALTH_BAND_NORMAL
    if score >= 75:
        return HEALTH_BAND_SLIGHT_REDUCTION
    if score >= 50:
        return HEALTH_BAND_DEFENSIVE
    if score >= 25:
        return HEALTH_BAND_RECOVERY
    return HEALTH_BAND_CAPITAL_PRESERVATION


# ─── Dataclasses ─────────────────────────────────────────────────────────────
@dataclass
class HealthWeights:
    """Weights for each health score component. Should sum to ~1.0."""
    daily_dd: float = 0.20
    total_dd: float = 0.20
    consecutive_losses: float = 0.15
    winning_streak: float = 0.10
    equity_slope: float = 0.10
    volatility_regime: float = 0.05
    kill_switch_state: float = 0.15
    recovery_status: float = 0.05

    def normalized(self) -> "HealthWeights":
        """Return a copy with weights normalized to sum to 1.0."""
        total = (self.daily_dd + self.total_dd + self.consecutive_losses
                 + self.winning_streak + self.equity_slope
                 + self.volatility_regime + self.kill_switch_state
                 + self.recovery_status)
        if total <= 0:
            return self
        return HealthWeights(
            daily_dd=self.daily_dd / total,
            total_dd=self.total_dd / total,
            consecutive_losses=self.consecutive_losses / total,
            winning_streak=self.winning_streak / total,
            equity_slope=self.equity_slope / total,
            volatility_regime=self.volatility_regime / total,
            kill_switch_state=self.kill_switch_state / total,
            recovery_status=self.recovery_status / total,
        )


@dataclass
class AccountHealthInput:
    """Inputs to the health score computation."""
    daily_dd_pct: float = 0.0                # current daily drawdown %
    total_dd_pct: float = 0.0                # current total drawdown %
    max_daily_dd_limit_pct: float = 5.0      # prop firm daily DD limit (e.g. FTMO 5%)
    max_total_dd_limit_pct: float = 10.0     # prop firm total DD limit (e.g. FTMO 10%)
    consecutive_losses: int = 0              # current consecutive losing trades
    winning_streak: int = 0                  # current consecutive winning trades
    equity_slope: float = 0.0                # recent equity slope (per-trade %; +ve = healthy)
    volatility_regime: str = "normal"        # "low" | "normal" | "high" | "extreme"
    kill_switch_state: str = "NORMAL"        # KillSwitchFSM state value
    in_recovery_mode: bool = False           # currently in recovery mode?
    recovery_progress: float = 0.0           # 0-1, fraction of recovery target met


@dataclass
class AccountHealthScore:
    """Computed health score + breakdown."""
    score: float                              # 0-100
    band: str                                 # band name
    components: dict                          # per-component contribution
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "score": round(self.score, 2),
            "band": self.band,
            "components": {k: round(v, 4) for k, v in self.components.items()},
            "timestamp": self.timestamp,
        }


# ─── Engine ──────────────────────────────────────────────────────────────────
class AccountHealthEngine:
    """
    Computes account health score and journals transitions.

    The score is a weighted sum of 8 components, each normalized to 0-100
    (100 = best, 0 = worst). Components:
      - daily_dd_pct:        100 at 0% DD, 0 at max_daily_dd_limit_pct
      - total_dd_pct:        100 at 0% DD, 0 at max_total_dd_limit_pct
      - consecutive_losses:  100 at 0 losses, 0 at 5+ losses
      - winning_streak:      100 at 3+ wins, 50 at 1 win, 0 at 0 wins (positive bias)
      - equity_slope:        100 at +0.5%/trade, 50 at 0%, 0 at -0.5%/trade
      - volatility_regime:   100 normal, 80 low, 50 high, 20 extreme
      - kill_switch_state:   100 NORMAL, 70 CAUTION, 30 HALT, 10 FLATTEN, 0 EMERGENCY
      - recovery_status:     100 not in recovery, 0-100 progress if in recovery
    """

    def __init__(
        self,
        journal: Optional[TradeJournal] = None,
        weights: Optional[HealthWeights] = None,
    ):
        self.journal = journal
        self.weights = (weights or HealthWeights()).normalized()
        self._last_band: Optional[str] = None
        self._last_score: Optional[float] = None
        self._evaluation_count: int = 0
        logger.info(
            f"AccountHealthEngine initialized "
            f"(weights sum={sum(asdict(self.weights).values()):.3f})"
        )

    # ─── Public API ───────────────────────────────────────────────────────

    def evaluate(self, inp: AccountHealthInput) -> AccountHealthScore:
        """Compute health score from inputs. Journals ACCOUNT_HEALTH + transitions."""
        components = self._compute_components(inp)
        weights = asdict(self.weights)
        score = sum(components[k] * weights[k] for k in components)
        score = max(0.0, min(100.0, score))
        band = score_to_band(score)

        result = AccountHealthScore(
            score=score,
            band=band,
            components=components,
        )
        self._evaluation_count += 1

        # Journal ACCOUNT_HEALTH on every evaluation
        self._journal_event(EventType.ACCOUNT_HEALTH, result.to_dict() | {
            "daily_dd_pct": inp.daily_dd_pct,
            "total_dd_pct": inp.total_dd_pct,
            "consecutive_losses": inp.consecutive_losses,
            "winning_streak": inp.winning_streak,
            "equity_slope": inp.equity_slope,
            "volatility_regime": inp.volatility_regime,
            "kill_switch_state": inp.kill_switch_state,
            "in_recovery_mode": inp.in_recovery_mode,
            "recovery_progress": inp.recovery_progress,
        })

        # Journal HEALTH_TRANSITION on band change
        if self._last_band is not None and band != self._last_band:
            self._journal_event(EventType.HEALTH_TRANSITION, {
                "from_band": self._last_band,
                "to_band": band,
                "from_score": self._last_score,
                "to_score": score,
            })
            logger.info(
                f"Health transition: {self._last_band} ({self._last_score:.1f}) "
                f"→ {band} ({score:.1f})"
            )

        self._last_band = band
        self._last_score = score
        return result

    @property
    def last_score(self) -> Optional[AccountHealthScore]:
        """Returns the last computed score (or None if never evaluated)."""
        if self._last_score is None:
            return None
        return AccountHealthScore(
            score=self._last_score,
            band=self._last_band or HEALTH_BAND_NORMAL,
            components={},
        )

    @property
    def evaluation_count(self) -> int:
        return self._evaluation_count

    # ─── Internal: component scoring ──────────────────────────────────────

    def _compute_components(self, inp: AccountHealthInput) -> dict[str, float]:
        """Compute each component score (0-100 each)."""
        return {
            "daily_dd": self._score_daily_dd(inp),
            "total_dd": self._score_total_dd(inp),
            "consecutive_losses": self._score_consecutive_losses(inp),
            "winning_streak": self._score_winning_streak(inp),
            "equity_slope": self._score_equity_slope(inp),
            "volatility_regime": self._score_volatility_regime(inp),
            "kill_switch_state": self._score_kill_switch(inp),
            "recovery_status": self._score_recovery(inp),
        }

    def _score_daily_dd(self, inp: AccountHealthInput) -> float:
        """100 at 0% DD, 0 at max_daily_dd_limit_pct, linear in between."""
        if inp.max_daily_dd_limit_pct <= 0:
            return 100.0
        score = 100.0 * (1.0 - inp.daily_dd_pct / inp.max_daily_dd_limit_pct)
        return max(0.0, min(100.0, score))

    def _score_total_dd(self, inp: AccountHealthInput) -> float:
        """100 at 0% DD, 0 at max_total_dd_limit_pct."""
        if inp.max_total_dd_limit_pct <= 0:
            return 100.0
        score = 100.0 * (1.0 - inp.total_dd_pct / inp.max_total_dd_limit_pct)
        return max(0.0, min(100.0, score))

    def _score_consecutive_losses(self, inp: AccountHealthInput) -> float:
        """100 at 0 losses, 0 at 5+ losses."""
        if inp.consecutive_losses <= 0:
            return 100.0
        if inp.consecutive_losses >= 5:
            return 0.0
        return 100.0 * (1.0 - inp.consecutive_losses / 5.0)

    def _score_winning_streak(self, inp: AccountHealthInput) -> float:
        """Positive bias: 100 at 3+ wins, 50 at 1 win, 0 at 0 wins."""
        if inp.winning_streak <= 0:
            return 50.0  # neutral, not penalized
        if inp.winning_streak >= 3:
            return 100.0
        return 50.0 + (50.0 * inp.winning_streak / 3.0)

    def _score_equity_slope(self, inp: AccountHealthInput) -> float:
        """100 at +0.5%/trade, 50 at 0%, 0 at -0.5%/trade."""
        slope = inp.equity_slope
        if slope >= 0.5:
            return 100.0
        if slope <= -0.5:
            return 0.0
        return 50.0 + (50.0 * slope / 0.5)

    def _score_volatility_regime(self, inp: AccountHealthInput) -> float:
        """100 normal, 80 low, 50 high, 20 extreme."""
        return {
            "low": 80.0,
            "normal": 100.0,
            "high": 50.0,
            "extreme": 20.0,
        }.get(inp.volatility_regime.lower(), 100.0)

    def _score_kill_switch(self, inp: AccountHealthInput) -> float:
        """100 NORMAL, 70 CAUTION, 30 HALT, 10 FLATTEN, 0 EMERGENCY."""
        return {
            "NORMAL": 100.0,
            "CAUTION": 70.0,
            "HALT_NEW_TRADES": 30.0,
            "FLATTEN_ONLY": 10.0,
            "EMERGENCY_STOP": 0.0,
        }.get(inp.kill_switch_state.upper(), 100.0)

    def _score_recovery(self, inp: AccountHealthInput) -> float:
        """100 if not in recovery; if in recovery, scaled by recovery_progress."""
        if not inp.in_recovery_mode:
            return 100.0
        progress = max(0.0, min(1.0, inp.recovery_progress))
        return 50.0 * progress  # max 50% while in recovery

    # ─── Internal: journal ────────────────────────────────────────────────

    def _journal_event(self, event_type: EventType, data: dict) -> None:
        if self.journal is None:
            return
        try:
            self.journal.log_event(event_type, data)
        except Exception as e:
            logger.error(f"Journal event {event_type.value} failed: {e}")
