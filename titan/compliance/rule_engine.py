"""
TITAN XAU AI — Compliance Rule Engine (M22.2)

Rule-based engine that evaluates firm profile constraints against current
trading state. Produces actionable RuleResult objects that the Risk Engine
and CEO Supervisor can act on.

Rules implemented:
1.  DailyLossRule      — checks current day's realized + unrealized loss vs limit
2.  SoftDailyLossRule  — warning zone (disable new entries)
3.  OverallDrawdownRule — max drawdown from initial / peak
4.  TrailingDrawdownRule — peak-equity-based drawdown
5.  ProfitTargetRule   — has profit target been met (informational)
6.  ConsistencyRule    — single-day profit share ≤ consistency_pct
7.  NewsBlackoutRule   — no new entries in news window
8.  WeekendRule        — flat by Friday close / no weekend holding
9.  MaxLotRule         — single-trade lot size limit
10. MaxPositionsRule   — concurrent open positions limit
11. LeverageRule       — overall account leverage cap
12. HedgingRule        — disallow hedging if not allowed
13. MinTradingDaysRule — must trade minimum days to pass
14. MaxTradingDaysRule — hard ceiling on trading duration
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Optional

from titan.compliance.profiles import (
    FirmProfile, DailyLossMode, DrawdownMode, NewsMode, WeekendMode,
)

logger = logging.getLogger(__name__)


class RuleAction(str, Enum):
    ALLOW = "allow"               # rule passes, no action
    WARN = "warn"                 # warning, but allow
    DISABLE_NEW = "disable_new"   # disable new entries, manage existing
    REDUCE_POSITION = "reduce"    # reduce existing position
    CLOSE_ALL = "close_all"       # liquidate all positions immediately
    HALT = "halt"                 # halt system entirely (rule breach)


@dataclass
class RuleResult:
    rule_id: str
    action: RuleAction
    message: str
    severity: int = 0          # 0-100 (0 = no concern, 100 = critical)
    details: dict = field(default_factory=dict)


@dataclass
class RuleContext:
    """Snapshot of trading state at evaluation time."""
    # Account
    initial_balance: float
    current_balance: float
    current_equity: float
    peak_equity: float
    start_of_day_balance: float
    start_of_day_equity: float

    # Time
    now: datetime
    trading_days_elapsed: int
    is_weekend: bool
    is_high_impact_news: bool
    minutes_since_news: int = 0

    # Positions
    open_positions: int = 0
    net_exposure: float = 0.0          # in lots (signed)
    gross_exposure: float = 0.0         # in lots (unsigned)
    pending_lot_size: float = 0.0       # lot size of pending new trade
    has_hedged_positions: bool = False

    # Profit tracking
    today_realized_pnl: float = 0.0
    today_unrealized_pnl: float = 0.0
    largest_single_day_profit: float = 0.0
    total_realized_pnl: float = 0.0


class ComplianceRule:
    """Base class for compliance rules."""

    rule_id: str = "base"

    def evaluate(self, ctx: RuleContext, profile: FirmProfile) -> RuleResult:
        raise NotImplementedError


# ─── Concrete rules ────────────────────────────────────────────────────────

class DailyLossRule(ComplianceRule):
    rule_id = "daily_loss"

    def evaluate(self, ctx: RuleContext, profile: FirmProfile) -> RuleResult:
        if profile.daily_loss_mode == DailyLossMode.PEAK_EQUITY_BASED:
            base = max(ctx.start_of_day_equity, ctx.peak_equity)
        else:
            base = ctx.start_of_day_balance
        loss = base - (ctx.current_equity + 0)  # equity already includes u/p
        loss_pct = loss / profile.initial_balance if profile.initial_balance > 0 else 0.0

        # Hard limit
        if loss_pct >= profile.max_daily_loss_pct:
            return RuleResult(
                rule_id=self.rule_id, action=RuleAction.CLOSE_ALL,
                message=f"Daily loss {loss_pct:.2%} ≥ hard limit {profile.max_daily_loss_pct:.2%}",
                severity=100,
                details={"loss_pct": loss_pct, "limit_pct": profile.max_daily_loss_pct,
                         "loss_amount": loss},
            )
        return RuleResult(
            rule_id=self.rule_id, action=RuleAction.ALLOW,
            message=f"Daily loss {loss_pct:.2%} within {profile.max_daily_loss_pct:.2%}",
            severity=int(100 * loss_pct / profile.max_daily_loss_pct),
            details={"loss_pct": loss_pct},
        )


class SoftDailyLossRule(ComplianceRule):
    rule_id = "daily_loss_soft"

    def evaluate(self, ctx: RuleContext, profile: FirmProfile) -> RuleResult:
        if profile.soft_daily_loss_pct <= 0:
            return RuleResult(
                rule_id=self.rule_id, action=RuleAction.ALLOW,
                message="No soft limit configured", severity=0,
            )
        loss = ctx.start_of_day_balance - ctx.current_equity
        loss_pct = loss / profile.initial_balance if profile.initial_balance > 0 else 0.0
        if loss_pct >= profile.soft_daily_loss_pct:
            return RuleResult(
                rule_id=self.rule_id, action=RuleAction.DISABLE_NEW,
                message=f"Daily loss {loss_pct:.2%} ≥ soft limit {profile.soft_daily_loss_pct:.2%}",
                severity=70,
                details={"loss_pct": loss_pct, "soft_pct": profile.soft_daily_loss_pct},
            )
        return RuleResult(
            rule_id=self.rule_id, action=RuleAction.ALLOW,
            message=f"Daily loss {loss_pct:.2%} within soft limit",
            severity=int(70 * loss_pct / profile.soft_daily_loss_pct),
        )


class OverallDrawdownRule(ComplianceRule):
    rule_id = "overall_drawdown"

    def evaluate(self, ctx: RuleContext, profile: FirmProfile) -> RuleResult:
        if profile.drawdown_mode == DrawdownMode.TRAILING:
            base = ctx.peak_equity
        else:  # STATIC or HYBRID (use static here)
            base = ctx.initial_balance
        dd = (base - ctx.current_equity) / profile.initial_balance \
            if profile.initial_balance > 0 else 0.0
        if dd >= profile.max_overall_drawdown_pct:
            return RuleResult(
                rule_id=self.rule_id, action=RuleAction.HALT,
                message=f"Overall DD {dd:.2%} ≥ max {profile.max_overall_drawdown_pct:.2%}",
                severity=100,
                details={"dd_pct": dd, "base": base},
            )
        return RuleResult(
            rule_id=self.rule_id, action=RuleAction.ALLOW,
            message=f"Overall DD {dd:.2%} within {profile.max_overall_drawdown_pct:.2%}",
            severity=int(100 * dd / profile.max_overall_drawdown_pct),
            details={"dd_pct": dd, "mode": profile.drawdown_mode.value},
        )


class TrailingDrawdownRule(ComplianceRule):
    rule_id = "trailing_drawdown"
    """
    For trailing mode: drawdown is measured from peak equity.
    Threshold: peak_equity - max_overall_drawdown_pct * initial_balance.
    If equity drops below threshold → HALT.
    """
    def evaluate(self, ctx: RuleContext, profile: FirmProfile) -> RuleResult:
        if profile.drawdown_mode != DrawdownMode.TRAILING:
            return RuleResult(
                rule_id=self.rule_id, action=RuleAction.ALLOW,
                message="Not trailing mode", severity=0,
            )
        threshold = ctx.peak_equity - profile.max_overall_drawdown_pct * profile.initial_balance
        if ctx.current_equity <= threshold:
            dd = (ctx.peak_equity - ctx.current_equity) / profile.initial_balance
            return RuleResult(
                rule_id=self.rule_id, action=RuleAction.HALT,
                message=f"Trailing DD breach: equity {ctx.current_equity:.0f} ≤ threshold {threshold:.0f}",
                severity=100,
                details={"threshold": threshold, "dd_pct": dd,
                         "peak": ctx.peak_equity},
            )
        return RuleResult(
            rule_id=self.rule_id, action=RuleAction.ALLOW,
            message=f"Trailing DD OK (threshold={threshold:.0f})",
            severity=int(100 * (1 - (ctx.current_equity - threshold) /
                                max(1, profile.max_overall_drawdown_pct * profile.initial_balance))),
        )


class ProfitTargetRule(ComplianceRule):
    rule_id = "profit_target"

    def __init__(self, phase: str = "phase1"):
        self.phase = phase
        self.rule_id = f"profit_target_{phase}"

    def evaluate(self, ctx: RuleContext, profile: FirmProfile) -> RuleResult:
        target_pct = (profile.profit_target_pct_phase1 if self.phase == "phase1"
                      else profile.profit_target_pct_phase2)
        target = profile.initial_balance * target_pct
        profit = ctx.current_equity - profile.initial_balance
        if profit >= target:
            return RuleResult(
                rule_id=self.rule_id, action=RuleAction.ALLOW,
                message=f"Profit target {target_pct:.2%} REACHED (profit={profit:.0f})",
                severity=0,
                details={"profit": profit, "target": target, "reached": True},
            )
        return RuleResult(
            rule_id=self.rule_id, action=RuleAction.ALLOW,
            message=f"Profit {profit:.0f} of target {target:.0f} ({profit/target:.0%})",
            severity=0,
            details={"profit": profit, "target": target, "reached": False},
        )


class ConsistencyRule(ComplianceRule):
    rule_id = "consistency"

    def evaluate(self, ctx: RuleContext, profile: FirmProfile) -> RuleResult:
        if profile.consistency_pct <= 0:
            return RuleResult(
                rule_id=self.rule_id, action=RuleAction.ALLOW,
                message="No consistency rule", severity=0,
            )
        if ctx.total_realized_pnl <= 0:
            return RuleResult(
                rule_id=self.rule_id, action=RuleAction.ALLOW,
                message="No profit yet — consistency N/A", severity=0,
            )
        share = ctx.largest_single_day_profit / ctx.total_realized_pnl \
            if ctx.total_realized_pnl > 0 else 0
        if share > profile.consistency_pct:
            return RuleResult(
                rule_id=self.rule_id, action=RuleAction.DISABLE_NEW,
                message=f"Consistency breach: largest day {share:.0%} > limit {profile.consistency_pct:.0%}",
                severity=80,
                details={"share": share, "limit": profile.consistency_pct,
                         "largest_day": ctx.largest_single_day_profit,
                         "total": ctx.total_realized_pnl},
            )
        return RuleResult(
            rule_id=self.rule_id, action=RuleAction.ALLOW,
            message=f"Consistency OK ({share:.0%} of {profile.consistency_pct:.0%})",
            severity=int(80 * share / profile.consistency_pct),
        )


class NewsBlackoutRule(ComplianceRule):
    rule_id = "news_blackout"

    def evaluate(self, ctx: RuleContext, profile: FirmProfile) -> RuleResult:
        if profile.news_mode == NewsMode.ALLOW:
            return RuleResult(
                rule_id=self.rule_id, action=RuleAction.ALLOW,
                message="News trading allowed", severity=0,
            )
        if profile.news_mode == NewsMode.NO_NEWS_TRADING and ctx.is_high_impact_news:
            return RuleResult(
                rule_id=self.rule_id, action=RuleAction.DISABLE_NEW,
                message="High-impact news in progress — new entries disabled",
                severity=70,
            )
        if profile.news_mode == NewsMode.BLACKOUT_WINDOW:
            if ctx.is_high_impact_news or ctx.minutes_since_news < profile.news_blackout_minutes:
                return RuleResult(
                    rule_id=self.rule_id, action=RuleAction.DISABLE_NEW,
                    message=f"News blackout active ({ctx.minutes_since_news}min since)",
                    severity=70,
                    details={"minutes_since": ctx.minutes_since_news,
                             "blackout_min": profile.news_blackout_minutes},
                )
        return RuleResult(
            rule_id=self.rule_id, action=RuleAction.ALLOW,
            message="No news blackout", severity=0,
        )


class WeekendRule(ComplianceRule):
    rule_id = "weekend"

    def evaluate(self, ctx: RuleContext, profile: FirmProfile) -> RuleResult:
        if profile.weekend_mode == WeekendMode.ALLOW:
            return RuleResult(
                rule_id=self.rule_id, action=RuleAction.ALLOW,
                message="Weekend holding allowed", severity=0,
            )
        if profile.weekend_mode == WeekendMode.NO_WEEKEND_HOLDING and ctx.is_weekend:
            if ctx.open_positions > 0:
                return RuleResult(
                    rule_id=self.rule_id, action=RuleAction.CLOSE_ALL,
                    message="Weekend holding not allowed — close all positions",
                    severity=90,
                )
            return RuleResult(
                rule_id=self.rule_id, action=RuleAction.DISABLE_NEW,
                message="Weekend — new entries disabled",
                severity=50,
            )
        if profile.weekend_mode == WeekendMode.FLAT_BY_FRIDAY_CLOSE:
            # Friday 22:00 UTC heuristic for "Friday close"
            is_friday_late = (ctx.now.weekday() == 4 and ctx.now.hour >= 22)
            if (is_friday_late or ctx.is_weekend) and ctx.open_positions > 0:
                return RuleResult(
                    rule_id=self.rule_id, action=RuleAction.CLOSE_ALL,
                    message="Flat by Friday close — close all positions",
                    severity=90,
                )
            if is_friday_late or ctx.is_weekend:
                return RuleResult(
                    rule_id=self.rule_id, action=RuleAction.DISABLE_NEW,
                    message="Past Friday close — new entries disabled",
                    severity=50,
                )
        return RuleResult(
            rule_id=self.rule_id, action=RuleAction.ALLOW,
            message="Weekend rule OK", severity=0,
        )


class MaxLotRule(ComplianceRule):
    rule_id = "max_lot"

    def evaluate(self, ctx: RuleContext, profile: FirmProfile) -> RuleResult:
        if profile.max_lot_per_trade <= 0:
            return RuleResult(
                rule_id=self.rule_id, action=RuleAction.ALLOW,
                message="No lot cap", severity=0,
            )
        if ctx.pending_lot_size > profile.max_lot_per_trade:
            return RuleResult(
                rule_id=self.rule_id, action=RuleAction.DISABLE_NEW,
                message=f"Pending lot {ctx.pending_lot_size} > max {profile.max_lot_per_trade}",
                severity=60,
            )
        return RuleResult(
            rule_id=self.rule_id, action=RuleAction.ALLOW,
            message=f"Lot {ctx.pending_lot_size} ≤ max {profile.max_lot_per_trade}",
            severity=0,
        )


class MaxPositionsRule(ComplianceRule):
    rule_id = "max_positions"

    def evaluate(self, ctx: RuleContext, profile: FirmProfile) -> RuleResult:
        if profile.max_open_positions <= 0:
            return RuleResult(
                rule_id=self.rule_id, action=RuleAction.ALLOW,
                message="No position cap", severity=0,
            )
        if ctx.open_positions >= profile.max_open_positions:
            return RuleResult(
                rule_id=self.rule_id, action=RuleAction.DISABLE_NEW,
                message=f"Open positions {ctx.open_positions} ≥ max {profile.max_open_positions}",
                severity=60,
            )
        return RuleResult(
            rule_id=self.rule_id, action=RuleAction.ALLOW,
            message=f"Positions {ctx.open_positions} < max {profile.max_open_positions}",
            severity=0,
        )


class LeverageRule(ComplianceRule):
    rule_id = "leverage"

    def evaluate(self, ctx: RuleContext, profile: FirmProfile) -> RuleResult:
        if profile.max_overall_leverage <= 0:
            return RuleResult(
                rule_id=self.rule_id, action=RuleAction.ALLOW,
                message="No leverage cap", severity=0,
            )
        notional = ctx.gross_exposure * 100_000  # approx $100k per lot for XAUUSD
        lev = notional / max(1, ctx.current_equity)
        if lev > profile.max_overall_leverage:
            return RuleResult(
                rule_id=self.rule_id, action=RuleAction.REDUCE_POSITION,
                message=f"Leverage {lev:.1f}x > max {profile.max_overall_leverage:.1f}x",
                severity=70,
            )
        return RuleResult(
            rule_id=self.rule_id, action=RuleAction.ALLOW,
            message=f"Leverage {lev:.1f}x ≤ max {profile.max_overall_leverage:.1f}x",
            severity=0,
        )


class HedgingRule(ComplianceRule):
    rule_id = "hedging"

    def evaluate(self, ctx: RuleContext, profile: FirmProfile) -> RuleResult:
        if not profile.hedging_allowed and ctx.has_hedged_positions:
            return RuleResult(
                rule_id=self.rule_id, action=RuleAction.CLOSE_ALL,
                message="Hedging not allowed — close all positions",
                severity=85,
            )
        return RuleResult(
            rule_id=self.rule_id, action=RuleAction.ALLOW,
            message="Hedging OK", severity=0,
        )


class MinTradingDaysRule(ComplianceRule):
    rule_id = "min_trading_days"

    def evaluate(self, ctx: RuleContext, profile: FirmProfile) -> RuleResult:
        if profile.min_trading_days <= 0:
            return RuleResult(
                rule_id=self.rule_id, action=RuleAction.ALLOW,
                message="No minimum days", severity=0,
            )
        if ctx.trading_days_elapsed < profile.min_trading_days:
            return RuleResult(
                rule_id=self.rule_id, action=RuleAction.ALLOW,
                message=f"Days {ctx.trading_days_elapsed} < min {profile.min_trading_days} (cannot pass yet)",
                severity=20,
            )
        return RuleResult(
            rule_id=self.rule_id, action=RuleAction.ALLOW,
            message=f"Min trading days met ({ctx.trading_days_elapsed})",
            severity=0,
        )


class MaxTradingDaysRule(ComplianceRule):
    rule_id = "max_trading_days"

    def evaluate(self, ctx: RuleContext, profile: FirmProfile) -> RuleResult:
        if profile.max_trading_days <= 0:
            return RuleResult(
                rule_id=self.rule_id, action=RuleAction.ALLOW,
                message="No max days", severity=0,
            )
        if ctx.trading_days_elapsed >= profile.max_trading_days:
            return RuleResult(
                rule_id=self.rule_id, action=RuleAction.HALT,
                message=f"Max trading days {profile.max_trading_days} reached",
                severity=100,
            )
        return RuleResult(
            rule_id=self.rule_id, action=RuleAction.ALLOW,
            message=f"Days {ctx.trading_days_elapsed} < max {profile.max_trading_days}",
            severity=int(100 * ctx.trading_days_elapsed / profile.max_trading_days),
        )


# ─── Engine ────────────────────────────────────────────────────────────────

@dataclass
class ConsistencyResult:
    largest_day_share: float
    largest_day_profit: float
    total_profit: float
    within_limit: bool


class ComplianceRuleEngine:
    """
    Holds the rule set and applies all rules against a context.
    Returns the most severe aggregated action.
    """

    def __init__(self, phase: str = "phase1"):
        self.phase = phase
        self.rules: list[ComplianceRule] = [
            DailyLossRule(),
            SoftDailyLossRule(),
            OverallDrawdownRule(),
            TrailingDrawdownRule(),
            ProfitTargetRule(phase=phase),
            ConsistencyRule(),
            NewsBlackoutRule(),
            WeekendRule(),
            MaxLotRule(),
            MaxPositionsRule(),
            LeverageRule(),
            HedgingRule(),
            MinTradingDaysRule(),
            MaxTradingDaysRule(),
        ]

    def evaluate_all(self, ctx: RuleContext, profile: FirmProfile) -> list[RuleResult]:
        return [r.evaluate(ctx, profile) for r in self.rules]

    @staticmethod
    def aggregate_action(results: list[RuleResult]) -> RuleAction:
        """Pick the most severe action across all results."""
        # Order from least to most severe
        severity_order = [
            RuleAction.ALLOW, RuleAction.WARN, RuleAction.DISABLE_NEW,
            RuleAction.REDUCE_POSITION, RuleAction.CLOSE_ALL, RuleAction.HALT,
        ]
        worst = RuleAction.ALLOW
        for r in results:
            if severity_order.index(r.action) > severity_order.index(worst):
                worst = r.action
        return worst


__all__ = [
    "ComplianceRule", "RuleResult", "RuleAction", "RuleContext",
    "ConsistencyResult", "ComplianceRuleEngine",
    "DailyLossRule", "SoftDailyLossRule", "OverallDrawdownRule",
    "TrailingDrawdownRule", "ProfitTargetRule", "ConsistencyRule",
    "NewsBlackoutRule", "WeekendRule", "MaxLotRule", "MaxPositionsRule",
    "LeverageRule", "HedgingRule", "MinTradingDaysRule", "MaxTradingDaysRule",
]
