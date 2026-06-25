"""
TITAN XAU AI — Exit Strategy Engine (Sprint 9.6)
==================================================

Combines 8 sub-engines into one cohesive exit strategy layer:
  Part 2 — Dynamic Take Profit (extend/reduce TP based on trend/momentum)
  Part 3 — AI Break Even (statistically justified BE move)
  Part 4 — Adaptive Trailing (ATR + trend + volatility aware)
  Part 5 — Partial Profit Engine (configurable R-multiple levels)
  Part 6 — Early Exit Engine (meta collapse + trend reversal + news)
  Part 7 — Time Exit (regime-aware max holding duration)
  Part 8 — News Exit (hold/partial/close/trail based on news proximity)
  Part 9 — Weekend Engine (gap risk evaluation)

All strategies are OPTIONAL. When disabled, existing ExitManager is unchanged.

Journals: TP_EXTENDED, TP_REDUCED, BREAK_EVEN, TRAIL_UPDATED, PARTIAL_EXIT,
          EARLY_EXIT, NEWS_EXIT, WEEKEND_EXIT.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field, asdict
from typing import Optional

from titan.production.trade_journal import TradeJournal, EventType
from titan.production.ai_exit_engine import ExitInput, ExitAction

logger = logging.getLogger(__name__)


# ─── Strategy outputs ───────────────────────────────────────────────────────
@dataclass
class DynamicTPDecision:
    """Result of dynamic TP evaluation."""
    new_tp: float
    action: str                          # "extend" | "reduce" | "early_exit" | "keep"
    reason: str
    extension_pct: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class BreakEvenDecision:
    """Result of AI break-even evaluation."""
    should_move: bool
    new_sl: float
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class TrailingDecision:
    """Result of adaptive trailing evaluation."""
    should_update: bool
    new_sl: float
    trail_distance: float
    trail_mult: float
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PartialExitDecision:
    """Result of partial profit evaluation."""
    should_close: bool
    close_pct: float
    r_threshold: float
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class EarlyExitDecision:
    """Result of early exit evaluation."""
    should_exit: bool
    reason: str
    triggers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class TimeExitDecision:
    """Result of time exit evaluation."""
    should_exit: bool
    reason: str
    max_hours: float
    hours_elapsed: float

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class NewsExitDecision:
    """Result of news exit evaluation."""
    action: str                          # "hold" | "partial" | "close" | "trail"
    reason: str
    close_pct: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class WeekendExitDecision:
    """Result of weekend exit evaluation."""
    action: str                          # "hold" | "partial" | "close"
    reason: str
    close_pct: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


# ─── Engine ──────────────────────────────────────────────────────────────────
class ExitStrategyEngine:
    """
    Combines all 8 exit sub-strategies into one evaluation.

    Each sub-strategy is independent and journaled separately.
    The AIExitEngine combines their outputs into a final ExitDecision.
    """

    def __init__(
        self,
        journal: Optional[TradeJournal] = None,
        config: Optional[dict] = None,
    ):
        self.journal = journal
        self.config = config or {}
        self._partial_levels_triggered: dict[str, set] = {}  # ticket → triggered levels

    # ─── Part 2: Dynamic TP ──────────────────────────────────────────────

    def evaluate_dynamic_tp(self, inp: ExitInput) -> DynamicTPDecision:
        """Adjust TP based on trend/momentum/regime."""
        cfg = self.config.get("dynamic_tp", {})
        strong_ext = cfg.get("strong_trend_extension_pct", 50) / 100
        weak_red = cfg.get("weak_momentum_reduction_pct", 25) / 100
        sideways_early = cfg.get("sideways_early_exit_pct", 75) / 100

        original_tp_distance = abs(inp.take_profit - inp.entry_price)
        new_tp = inp.take_profit
        action = "keep"
        reason = "no change"
        ext_pct = 0.0

        if inp.regime == "trend" and inp.trend_strength * inp.direction > 0.5:
            # Strong trend → extend TP
            ext = original_tp_distance * strong_ext
            if inp.direction == 1:
                new_tp = inp.take_profit + ext
            else:
                new_tp = inp.take_profit - ext
            action = "extend"
            reason = f"strong trend (strength={inp.trend_strength:.2f})"
            ext_pct = strong_ext
            self._journal_event(EventType.TP_EXTENDED, {
                "original_tp": inp.take_profit, "new_tp": new_tp,
                "extension_pct": strong_ext * 100, "reason": reason,
            })
        elif inp.momentum < 0.3:
            # Weak momentum → reduce TP
            red = original_tp_distance * weak_red
            if inp.direction == 1:
                new_tp = inp.take_profit - red
            else:
                new_tp = inp.take_profit + red
            action = "reduce"
            reason = f"weak momentum (mom={inp.momentum:.2f})"
            ext_pct = -weak_red
            self._journal_event(EventType.TP_REDUCED, {
                "original_tp": inp.take_profit, "new_tp": new_tp,
                "reduction_pct": weak_red * 100, "reason": reason,
            })
        elif inp.regime == "range":
            # Sideways → early exit at % of TP
            early_target = inp.entry_price + (inp.take_profit - inp.entry_price) * sideways_early * inp.direction
            new_tp = early_target
            action = "early_exit"
            reason = f"sideways regime → exit at {sideways_early*100:.0f}% of TP"
            self._journal_event(EventType.TP_REDUCED, {
                "original_tp": inp.take_profit, "new_tp": new_tp,
                "reduction_pct": (1 - sideways_early) * 100, "reason": reason,
            })

        return DynamicTPDecision(
            new_tp=new_tp, action=action, reason=reason,
            extension_pct=ext_pct * 100,
        )

    # ─── Part 3: AI Break Even ───────────────────────────────────────────

    def evaluate_break_even(self, inp: ExitInput) -> BreakEvenDecision:
        """Move SL to BE only when statistically justified."""
        # Criteria: +1R + trend weakening + normal volatility
        if inp.r_multiple < 1.0:
            return BreakEvenDecision(False, inp.stop_loss, "r < 1.0R — not justified")
        if inp.trend_strength * inp.direction > 0.3:
            return BreakEvenDecision(False, inp.stop_loss, "trend still strong — hold SL")
        if inp.volatility_regime == "extreme":
            return BreakEvenDecision(False, inp.stop_loss, "extreme vol — keep SL for protection")

        # Move to BE
        self._journal_event(EventType.BREAK_EVEN, {
            "old_sl": inp.stop_loss, "new_sl": inp.entry_price,
            "r_multiple": inp.r_multiple, "reason": "statistically justified BE",
        })
        return BreakEvenDecision(True, inp.entry_price, "r≥1R + trend weakening + normal vol")

    # ─── Part 4: Adaptive Trailing ───────────────────────────────────────

    def evaluate_trailing(self, inp: ExitInput) -> TrailingDecision:
        """Adaptive trail based on ATR + trend + volatility."""
        if inp.r_multiple < 0.5:
            return TrailingDecision(False, inp.stop_loss, 0, 1.0, "r < 0.5R — no trail")

        cfg = self.config.get("trailing", {})
        base_mult = cfg.get("base_atr_multiplier", 1.0)
        strong_loosen = cfg.get("strong_trend_loosen", 2.0)
        weak_tighten = cfg.get("weak_market_tighten", 0.5)
        min_dist_mult = cfg.get("min_trail_distance_atr", 0.3)

        # Determine multiplier
        trend_aligned = inp.trend_strength * inp.direction
        if trend_aligned > 0.5:
            trail_mult = strong_loosen
            reason = f"strong trend → loosen to {trail_mult}×ATR"
        elif trend_aligned < 0.1:
            trail_mult = weak_tighten
            reason = f"weak market → tighten to {trail_mult}×ATR"
        else:
            trail_mult = base_mult
            reason = f"normal → {trail_mult}×ATR"

        trail_mult = max(min_dist_mult, trail_mult)
        trail_distance = trail_mult * inp.atr if inp.atr > 0 else 0

        if inp.direction == 1:
            new_sl = inp.current_price - trail_distance
            should = new_sl > inp.stop_loss
        else:
            new_sl = inp.current_price + trail_distance
            should = new_sl < inp.stop_loss

        if should:
            self._journal_event(EventType.TRAIL_UPDATED, {
                "old_sl": inp.stop_loss, "new_sl": new_sl,
                "trail_mult": trail_mult, "trail_distance": trail_distance,
                "reason": reason,
            })

        return TrailingDecision(should, new_sl, trail_distance, trail_mult, reason)

    # ─── Part 5: Partial Profit ──────────────────────────────────────────

    def evaluate_partial_exit(self, inp: ExitInput, ticket: str = "default") -> PartialExitDecision:
        """Partial close at configured R-multiple levels."""
        partial_cfg = self.config.get("partial_exits", {})
        if not partial_cfg.get("enabled", True):
            return PartialExitDecision(False, 0, 0, "disabled")

        levels = partial_cfg.get("levels", [
            {"r_multiple": 1.0, "close_pct": 25},
            {"r_multiple": 2.0, "close_pct": 25},
            {"r_multiple": 3.0, "close_pct": 25},
        ])
        min_remaining = partial_cfg.get("min_remaining_pct", 25) / 100

        triggered = self._partial_levels_triggered.setdefault(ticket, set())

        for i, level in enumerate(levels):
            r_threshold = level.get("r_multiple", 1.0)
            close_pct = level.get("close_pct", 25)
            if i in triggered:
                continue
            if inp.r_multiple >= r_threshold:
                triggered.add(i)
                self._journal_event(EventType.PARTIAL_EXIT, {
                    "ticket": ticket, "r_multiple": inp.r_multiple,
                    "r_threshold": r_threshold, "close_pct": close_pct,
                    "reason": f"partial at {r_threshold}R",
                })
                return PartialExitDecision(
                    True, close_pct, r_threshold,
                    f"r={inp.r_multiple:.1f}R ≥ {r_threshold}R",
                )
        return PartialExitDecision(False, 0, 0, "no level triggered")

    # ─── Part 6: Early Exit ──────────────────────────────────────────────

    def evaluate_early_exit(self, inp: ExitInput) -> EarlyExitDecision:
        """Exit before TP if edge disappears."""
        cfg = self.config.get("early_exit", {})
        meta_collapse = cfg.get("meta_confidence_collapse", 0.40)
        trend_reversal = cfg.get("trend_reversal_threshold", -0.3)
        momentum_collapse = cfg.get("momentum_collapse", 0.20)

        triggers = []
        if inp.meta_confidence < meta_collapse:
            triggers.append(f"meta_collapse ({inp.meta_confidence:.2f})")
        if inp.trend_strength * inp.direction < trend_reversal:
            triggers.append(f"trend_reversal ({inp.trend_strength:.2f})")
        if inp.momentum < momentum_collapse:
            triggers.append(f"momentum_collapse ({inp.momentum:.2f})")
        if inp.broker_quality_score < 60 and inp.r_multiple > 0:
            triggers.append(f"broker_degraded ({inp.broker_quality_score:.0f})")
        if inp.capital_preservation_active and inp.r_multiple > 0:
            triggers.append("capital_preservation + profit")

        if triggers:
            reason = f"early exit: {'; '.join(triggers)}"
            self._journal_event(EventType.EARLY_EXIT, {
                "triggers": triggers, "reason": reason,
                "r_multiple": inp.r_multiple, "meta_confidence": inp.meta_confidence,
            })
            return EarlyExitDecision(True, reason, triggers)
        return EarlyExitDecision(False, "edge intact", [])

    # ─── Part 7: Time Exit ───────────────────────────────────────────────

    def evaluate_time_exit(self, inp: ExitInput) -> TimeExitDecision:
        """AI decides max holding duration based on regime."""
        cfg = self.config.get("time_exit", {})
        if inp.regime == "trend" and inp.trend_strength * inp.direction > 0.5:
            max_hours = cfg.get("max_holding_hours_strong_trend", 48)
        elif inp.regime == "range":
            max_hours = cfg.get("max_holding_hours_sideways", 8)
        else:
            max_hours = cfg.get("max_holding_hours_normal", 24)

        if inp.time_in_trade_hours >= max_hours:
            reason = f"time exit: {inp.time_in_trade_hours:.1f}h ≥ {max_hours}h (regime={inp.regime})"
            return TimeExitDecision(True, reason, max_hours, inp.time_in_trade_hours)
        return TimeExitDecision(False, f"{inp.time_in_trade_hours:.1f}h < {max_hours}h",
                                max_hours, inp.time_in_trade_hours)

    # ─── Part 8: News Exit ───────────────────────────────────────────────

    def evaluate_news_exit(self, inp: ExitInput) -> NewsExitDecision:
        """AI decides hold/partial/close/trail when news approaches."""
        if not inp.news_imminent:
            return NewsExitDecision("hold", "no imminent news")

        # News imminent + in profit → partial close to lock profit
        if inp.r_multiple > 1.0:
            self._journal_event(EventType.NEWS_EXIT, {
                "action": "partial", "close_pct": 50,
                "r_multiple": inp.r_multiple, "reason": "news + profit → partial",
            })
            return NewsExitDecision("partial", "news + profit → lock 50%", 50)

        # News imminent + in loss → close to avoid gap risk
        if inp.r_multiple < 0:
            self._journal_event(EventType.NEWS_EXIT, {
                "action": "close", "close_pct": 100,
                "r_multiple": inp.r_multiple, "reason": "news + loss → close",
            })
            return NewsExitDecision("close", "news + loss → close to avoid gap", 100)

        # News imminent + near breakeven → trail tightly
        return NewsExitDecision("trail", "news + breakeven → trail tight")

    # ─── Part 9: Weekend Exit ────────────────────────────────────────────

    def evaluate_weekend_exit(self, inp: ExitInput, is_friday_late: bool = False) -> WeekendExitDecision:
        """Evaluate gap risk before weekend."""
        if not is_friday_late:
            return WeekendExitDecision("hold", "not friday late")

        # Friday late + in profit → partial close to reduce gap risk
        if inp.r_multiple > 0.5:
            self._journal_event(EventType.WEEKEND_EXIT, {
                "action": "partial", "close_pct": 50,
                "r_multiple": inp.r_multiple, "reason": "weekend + profit → partial",
            })
            return WeekendExitDecision("partial", "weekend + profit → partial 50%", 50)

        # Friday late + in loss → close to avoid gap
        if inp.r_multiple < 0:
            self._journal_event(EventType.WEEKEND_EXIT, {
                "action": "close", "close_pct": 100,
                "r_multiple": inp.r_multiple, "reason": "weekend + loss → close",
            })
            return WeekendExitDecision("close", "weekend + loss → close", 100)

        # Friday late + high volatility → close
        if inp.volatility_regime in ("high", "extreme"):
            self._journal_event(EventType.WEEKEND_EXIT, {
                "action": "close", "close_pct": 100,
                "volatility": inp.volatility_regime, "reason": "weekend + high vol → close",
            })
            return WeekendExitDecision("close", "weekend + high vol → close", 100)

        return WeekendExitDecision("hold", "weekend conditions acceptable")

    # ─── Internal ────────────────────────────────────────────────────────

    def _journal_event(self, event_type: EventType, data: dict) -> None:
        if self.journal is None:
            return
        try:
            self.journal.log_event(event_type, data)
        except Exception as e:
            logger.error(f"Journal event {event_type.value} failed: {e}")

    def reset_partial_levels(self, ticket: str = "default") -> None:
        """Reset partial exit tracking for a ticket (call when position closes)."""
        self._partial_levels_triggered.pop(ticket, None)
