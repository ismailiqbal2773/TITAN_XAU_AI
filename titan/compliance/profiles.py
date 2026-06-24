"""
TITAN XAU AI — Prop Firm Profiles (M22.1)

Per-firm rule profiles. Five core firms + custom slot.

Profile schema (each firm differs by these knobs):
- initial_balance         : starting capital
- max_daily_loss_pct      : % of initial balance lost in a single day (HARD limit)
- soft_daily_loss_pct     : % of initial balance → disable new entries (SOFT limit)
- max_overall_drawdown_pct: % of initial balance (or peak equity) — HARD limit
- drawdown_mode           : STATIC | TRAILING | HYBRID
- daily_loss_mode         : BALANCE_BASED | PEAK_EQUITY_BASED
- profit_target_pct       : % to pass challenge phase
- min_trading_days        : minimum days to be eligible to pass
- max_trading_days        : hard ceiling (after which auto-fail)
- consistency_pct         : max share of total profit from single day (e.g. 40% for FTMO)
- news_mode               : ALLOW | BLACKOUT_WINDOW | NO_NEWS_TRADING
- news_blackout_minutes   : minutes around high-impact news to avoid new entries
- weekend_mode            : ALLOW | FLAT_BY_FRIDAY_CLOSE | NO_WEEKEND_HOLDING
- max_lot_per_trade       : 0 = unlimited
- max_open_positions      : 0 = unlimited
- max_overall_leverage    : 0 = unlimited
- hedging_allowed         : bool
- eas_allowed             : bool (some firms ban EAs in evaluation)
- timezone                : firm's daily reset timezone (UTC offsets)

All percentages are stored as decimal fractions (0.05 = 5%).
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional


class FirmId(str, Enum):
    FTMO = "ftmo"
    FUNDEDNEXT = "fundednext"
    E8 = "e8"
    THE5ERS = "the5ers"
    FUNDING_PIPS = "funding_pips"
    MYFUNDEDFX = "myfundedfx"      # Sprint 9.0
    CUSTOM = "custom"


class DailyLossMode(str, Enum):
    BALANCE_BASED = "balance_based"            # loss relative to start-of-day balance
    PEAK_EQUITY_BASED = "peak_equity_based"    # loss relative to today's peak equity


class DrawdownMode(str, Enum):
    STATIC = "static"        # relative to initial balance (FTMO challenge)
    TRAILING = "trailing"    # relative to peak equity (FTMO funded, FundedNext)
    HYBRID = "hybrid"        # static for phase 1, trailing for phase 2


class NewsMode(str, Enum):
    ALLOW = "allow"
    BLACKOUT_WINDOW = "blackout_window"
    NO_NEWS_TRADING = "no_news_trading"


class WeekendMode(str, Enum):
    ALLOW = "allow"
    FLAT_BY_FRIDAY_CLOSE = "flat_by_friday_close"
    NO_WEEKEND_HOLDING = "no_weekend_holding"


# Default profit targets per phase (as fraction)
PROFIT_TARGET_PCT = {
    "phase1": 0.10,    # 10% to pass Phase 1
    "phase2": 0.05,    # 5% to pass Phase 2
    "funded": 0.0,     # funded: no target, just don't breach
}


@dataclass
class FirmProfile:
    firm_id: FirmId
    name: str
    initial_balance: float
    max_daily_loss_pct: float          # e.g. 0.05 = 5%
    soft_daily_loss_pct: float         # e.g. 0.04 — soft warning
    max_overall_drawdown_pct: float    # e.g. 0.10 = 10%
    drawdown_mode: DrawdownMode
    daily_loss_mode: DailyLossMode
    profit_target_pct_phase1: float
    profit_target_pct_phase2: float
    min_trading_days: int
    max_trading_days: int
    consistency_pct: float             # e.g. 0.40 = max 40% of profit in 1 day
    news_mode: NewsMode
    news_blackout_minutes: int
    weekend_mode: WeekendMode
    max_lot_per_trade: float
    max_open_positions: int
    max_overall_leverage: float
    hedging_allowed: bool
    eas_allowed: bool
    timezone_offset_hours: int         # UTC offset for daily reset
    notes: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["firm_id"] = self.firm_id.value
        d["drawdown_mode"] = self.drawdown_mode.value
        d["daily_loss_mode"] = self.daily_loss_mode.value
        d["news_mode"] = self.news_mode.value
        d["weekend_mode"] = self.weekend_mode.value
        return d


# ─── Built-in firm profiles ────────────────────────────────────────────────

def _ftmo_profile(balance: float = 100_000.0) -> FirmProfile:
    return FirmProfile(
        firm_id=FirmId.FTMO,
        name="FTMO",
        initial_balance=balance,
        max_daily_loss_pct=0.05,
        soft_daily_loss_pct=0.045,
        max_overall_drawdown_pct=0.10,
        drawdown_mode=DrawdownMode.STATIC,
        daily_loss_mode=DailyLossMode.BALANCE_BASED,
        profit_target_pct_phase1=0.10,
        profit_target_pct_phase2=0.05,
        min_trading_days=4,
        max_trading_days=0,                # no hard ceiling
        consistency_pct=0.40,
        news_mode=NewsMode.ALLOW,
        news_blackout_minutes=0,
        weekend_mode=WeekendMode.FLAT_BY_FRIDAY_CLOSE,
        max_lot_per_trade=0.0,
        max_open_positions=0,
        max_overall_leverage=0.0,
        hedging_allowed=True,
        eas_allowed=True,
        timezone_offset_hours=0,           # CET actually, but UTC for simplicity
        notes="FTMO Challenge: 5% daily loss, 10% max DD, 10% phase1 / 5% phase2 profit target, 4 min days",
    )


def _fundednext_profile(balance: float = 100_000.0) -> FirmProfile:
    return FirmProfile(
        firm_id=FirmId.FUNDEDNEXT,
        name="FundedNext",
        initial_balance=balance,
        max_daily_loss_pct=0.05,
        soft_daily_loss_pct=0.045,
        max_overall_drawdown_pct=0.10,
        drawdown_mode=DrawdownMode.TRAILING,  # FundedNext uses trailing on funded
        daily_loss_mode=DailyLossMode.BALANCE_BASED,
        profit_target_pct_phase1=0.10,
        profit_target_pct_phase2=0.05,
        min_trading_days=0,
        max_trading_days=0,
        consistency_pct=0.0,                # FundedNext: no strict consistency rule
        news_mode=NewsMode.ALLOW,
        news_blackout_minutes=0,
        weekend_mode=WeekendMode.FLAT_BY_FRIDAY_CLOSE,
        max_lot_per_trade=0.0,
        max_open_positions=0,
        max_overall_leverage=0.0,
        hedging_allowed=True,
        eas_allowed=True,
        timezone_offset_hours=0,
        notes="FundedNext: 5%/10% loss, trailing DD on funded, no consistency rule",
    )


def _e8_profile(balance: float = 100_000.0) -> FirmProfile:
    return FirmProfile(
        firm_id=FirmId.E8,
        name="E8 Funding",
        initial_balance=balance,
        max_daily_loss_pct=0.05,
        soft_daily_loss_pct=0.04,
        max_overall_drawdown_pct=0.08,      # E8 uses 8% overall DD
        drawdown_mode=DrawdownMode.STATIC,
        daily_loss_mode=DailyLossMode.BALANCE_BASED,
        profit_target_pct_phase1=0.08,
        profit_target_pct_phase2=0.05,
        min_trading_days=0,
        max_trading_days=0,
        consistency_pct=0.0,
        news_mode=NewsMode.ALLOW,
        news_blackout_minutes=0,
        weekend_mode=WeekendMode.ALLOW,     # E8 allows weekend holding
        max_lot_per_trade=0.0,
        max_open_positions=0,
        max_overall_leverage=0.0,
        hedging_allowed=True,
        eas_allowed=True,
        timezone_offset_hours=0,
        notes="E8: 5% daily, 8% max DD, 8%/5% targets, weekend holding OK",
    )


def _the5ers_profile(balance: float = 100_000.0) -> FirmProfile:
    return FirmProfile(
        firm_id=FirmId.THE5ERS,
        name="The 5ers",
        initial_balance=balance,
        max_daily_loss_pct=0.04,             # 5ers is 4% daily
        soft_daily_loss_pct=0.035,
        max_overall_drawdown_pct=0.06,       # 6% overall DD (lower risk firm)
        drawdown_mode=DrawdownMode.STATIC,
        daily_loss_mode=DailyLossMode.BALANCE_BASED,
        profit_target_pct_phase1=0.06,
        profit_target_pct_phase2=0.04,
        min_trading_days=0,
        max_trading_days=0,
        consistency_pct=0.0,
        news_mode=NewsMode.BLACKOUT_WINDOW,  # 5ers prefers no entries 2min around news
        news_blackout_minutes=2,             # 2-minute blackout window
        weekend_mode=WeekendMode.FLAT_BY_FRIDAY_CLOSE,
        max_lot_per_trade=0.0,
        max_open_positions=0,
        max_overall_leverage=0.0,
        hedging_allowed=False,
        eas_allowed=True,
        timezone_offset_hours=0,
        notes="The 5ers: 4% daily, 6% max DD (low-risk), no hedging, 2min news blackout",
    )


def _funding_pips_profile(balance: float = 100_000.0) -> FirmProfile:
    return FirmProfile(
        firm_id=FirmId.FUNDING_PIPS,
        name="Funding Pips",
        initial_balance=balance,
        max_daily_loss_pct=0.05,
        soft_daily_loss_pct=0.045,
        max_overall_drawdown_pct=0.10,
        drawdown_mode=DrawdownMode.STATIC,
        daily_loss_mode=DailyLossMode.BALANCE_BASED,
        profit_target_pct_phase1=0.08,
        profit_target_pct_phase2=0.05,
        min_trading_days=0,
        max_trading_days=0,
        consistency_pct=0.0,
        news_mode=NewsMode.ALLOW,
        news_blackout_minutes=0,
        weekend_mode=WeekendMode.FLAT_BY_FRIDAY_CLOSE,
        max_lot_per_trade=0.0,
        max_open_positions=0,
        max_overall_leverage=0.0,
        hedging_allowed=True,
        eas_allowed=True,
        timezone_offset_hours=0,
        notes="Funding Pips: 5% daily, 10% DD, 8%/5% targets, very similar to FTMO",
    )


def _custom_profile(balance: float = 100_000.0) -> FirmProfile:
    return FirmProfile(
        firm_id=FirmId.CUSTOM,
        name="Custom Firm",
        initial_balance=balance,
        max_daily_loss_pct=0.05,
        soft_daily_loss_pct=0.04,
        max_overall_drawdown_pct=0.10,
        drawdown_mode=DrawdownMode.HYBRID,
        daily_loss_mode=DailyLossMode.BALANCE_BASED,
        profit_target_pct_phase1=0.08,
        profit_target_pct_phase2=0.05,
        min_trading_days=3,
        max_trading_days=30,
        consistency_pct=0.40,
        news_mode=NewsMode.BLACKOUT_WINDOW,
        news_blackout_minutes=5,
        weekend_mode=WeekendMode.FLAT_BY_FRIDAY_CLOSE,
        max_lot_per_trade=10.0,
        max_open_positions=5,
        max_overall_leverage=30.0,
        hedging_allowed=True,
        eas_allowed=True,
        timezone_offset_hours=0,
        notes="Custom: configurable baseline — adjust per firm requirements",
    )


def _myfundedfx_profile(balance: float = 100_000.0) -> FirmProfile:
    """Sprint 9.0 — MyFundedFX challenge profile."""
    return FirmProfile(
        firm_id=FirmId.MYFUNDEDFX,
        name="MyFundedFX",
        initial_balance=balance,
        max_daily_loss_pct=0.05,
        soft_daily_loss_pct=0.04,
        max_overall_drawdown_pct=0.10,
        drawdown_mode=DrawdownMode.STATIC,
        daily_loss_mode=DailyLossMode.BALANCE_BASED,
        profit_target_pct_phase1=0.08,
        profit_target_pct_phase2=0.05,
        min_trading_days=3,
        max_trading_days=0,
        consistency_pct=0.0,
        news_mode=NewsMode.ALLOW,
        news_blackout_minutes=0,
        weekend_mode=WeekendMode.FLAT_BY_FRIDAY_CLOSE,
        max_lot_per_trade=0.0,
        max_open_positions=0,
        max_overall_leverage=0.0,
        hedging_allowed=True,
        eas_allowed=True,
        timezone_offset_hours=0,
        notes="MyFundedFX: 8% target, 5% daily, 10% DD, 3 min days, no consistency rule",
    )


class PropFirmProfiles:
    """Factory for built-in firm profiles."""

    _BUILDERS = {
        FirmId.FTMO: _ftmo_profile,
        FirmId.FUNDEDNEXT: _fundednext_profile,
        FirmId.E8: _e8_profile,
        FirmId.THE5ERS: _the5ers_profile,
        FirmId.FUNDING_PIPS: _funding_pips_profile,
        FirmId.MYFUNDEDFX: _myfundedfx_profile,
        FirmId.CUSTOM: _custom_profile,
    }

    @classmethod
    def get(cls, firm_id: FirmId, balance: float = 100_000.0) -> FirmProfile:
        builder = cls._BUILDERS[firm_id]
        return builder(balance)

    @classmethod
    def all_firms(cls, balance: float = 100_000.0) -> dict[FirmId, FirmProfile]:
        return {fid: cls.get(fid, balance) for fid in FirmId}

    @classmethod
    def supported_firms(cls) -> list[str]:
        return [f.value for f in FirmId]


__all__ = [
    "FirmProfile", "FirmId", "DailyLossMode", "DrawdownMode", "NewsMode", "WeekendMode",
    "PropFirmProfiles", "PROFIT_TARGET_PCT",
]
