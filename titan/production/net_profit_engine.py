"""
TITAN XAU AI — Net Profit Engine (Sprint 9.8)
================================================

Calculates net PnL with full cost breakdown:
  net_pnl = gross_pnl - spread_cost - commission_cost - slippage_cost - swap_cost

Supports XAUUSD contract/tick value safely.
If precise broker contract value unavailable, uses conservative fallback.
"""
from __future__ import annotations
import logging
from dataclasses import dataclass, asdict
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class TradeCosts:
    """Cost breakdown for a single trade."""
    spread_cost: float = 0.0
    commission_cost: float = 0.0
    slippage_cost: float = 0.0
    swap_cost: float = 0.0
    total_cost: float = 0.0
    is_estimate: bool = False
    estimate_reason: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class NetPnLResult:
    """Result of net PnL calculation."""
    gross_pnl: float
    net_pnl: float
    costs: TradeCosts
    r_multiple: float = 0.0
    is_profitable_net: bool = False
    is_profitable_gross: bool = False
    cost_drag_pct: float = 0.0

    def to_dict(self) -> dict:
        return {
            "gross_pnl": self.gross_pnl,
            "net_pnl": self.net_pnl,
            "costs": self.costs.to_dict(),
            "r_multiple": self.r_multiple,
            "is_profitable_net": self.is_profitable_net,
            "is_profitable_gross": self.is_profitable_gross,
            "cost_drag_pct": self.cost_drag_pct,
        }


class NetProfitEngine:
    """
    Calculates net profit with cost awareness.

    Usage:
        engine = NetProfitEngine(contract_size=100.0, commission_per_lot=30.20)
        result = engine.calculate(
            direction="BUY", entry_price=2000.0, close_price=2010.0,
            lot=0.01, sl=1990.0,
            spread_usd=0.30, slippage_pips=2,
        )
    """

    def __init__(
        self,
        contract_size: float = 100.0,     # XAUUSD: 1 lot = 100 oz
        commission_per_lot: float = 30.20, # Exness standard
        tick_value: float = 1.0,           # $1 per 0.01 move per lot
        tick_size: float = 0.01,
        default_spread_usd: float = 0.30,
        default_slippage_pips: float = 2.0,
        default_swap_per_day: float = 0.0,
    ):
        self.contract_size = contract_size
        self.commission_per_lot = commission_per_lot
        self.tick_value = tick_value
        self.tick_size = tick_size
        self.default_spread_usd = default_spread_usd
        self.default_slippage_pips = default_slippage_pips
        self.default_swap_per_day = default_swap_per_day

    def calculate(
        self,
        direction: str,
        entry_price: float,
        close_price: float,
        lot: float,
        sl: float,
        spread_usd: Optional[float] = None,
        slippage_pips: Optional[float] = None,
        swap_cost: Optional[float] = None,
        holding_days: float = 0.0,
    ) -> NetPnLResult:
        """
        Calculate net PnL with full cost breakdown.

        Args:
            direction: "BUY" or "SELL"
            entry_price: entry price
            close_price: close price
            lot: lot size
            sl: stop loss (for R-multiple calculation)
            spread_usd: spread in USD (optional, uses default if None)
            slippage_pips: slippage in pips (optional, uses default if None)
            swap_cost: swap/financing cost (optional, calculated from holding_days if None)
            holding_days: holding time in days (for swap calculation)
        """
        is_estimate = False
        estimate_reason = ""

        # Gross PnL
        if direction.upper() == "BUY":
            gross_pnl = (close_price - entry_price) * self.contract_size * lot
        else:
            gross_pnl = (entry_price - close_price) * self.contract_size * lot

        # Spread cost
        if spread_usd is not None:
            spread_cost = spread_usd * lot
        else:
            spread_cost = self.default_spread_usd * lot
            is_estimate = True
            estimate_reason = "spread_estimated"

        # Commission cost
        commission_cost = self.commission_per_lot * lot

        # Slippage cost
        if slippage_pips is not None:
            slippage_cost = slippage_pips * self.tick_value * lot / self.tick_size
        else:
            slippage_cost = self.default_slippage_pips * self.tick_value * lot / self.tick_size
            is_estimate = True
            estimate_reason += "+slippage_estimated" if estimate_reason else "slippage_estimated"

        # Swap cost
        if swap_cost is not None:
            swap_cost_val = swap_cost
        else:
            swap_cost_val = self.default_swap_per_day * holding_days * lot
            if holding_days > 0:
                is_estimate = True
                estimate_reason += "+swap_estimated" if estimate_reason else "swap_estimated"

        # Total costs
        total_cost = spread_cost + commission_cost + slippage_cost + swap_cost_val

        # Net PnL
        net_pnl = gross_pnl - total_cost

        # R-multiple
        initial_risk = abs(entry_price - sl) * self.contract_size * lot
        r_multiple = gross_pnl / initial_risk if initial_risk > 0 else 0.0

        # Cost drag
        cost_drag_pct = (total_cost / abs(gross_pnl) * 100) if gross_pnl != 0 else 0.0

        costs = TradeCosts(
            spread_cost=spread_cost,
            commission_cost=commission_cost,
            slippage_cost=slippage_cost,
            swap_cost=swap_cost_val,
            total_cost=total_cost,
            is_estimate=is_estimate,
            estimate_reason=estimate_reason,
        )

        return NetPnLResult(
            gross_pnl=gross_pnl,
            net_pnl=net_pnl,
            costs=costs,
            r_multiple=r_multiple,
            is_profitable_net=net_pnl > 0,
            is_profitable_gross=gross_pnl > 0,
            cost_drag_pct=cost_drag_pct,
        )

    def estimate_costs(
        self,
        lot: float,
        spread_usd: Optional[float] = None,
        slippage_pips: Optional[float] = None,
        holding_days: float = 0.0,
    ) -> TradeCosts:
        """Estimate costs for a trade without calculating PnL."""
        return self.calculate(
            direction="BUY", entry_price=0, close_price=0,
            lot=lot, sl=0,
            spread_usd=spread_usd, slippage_pips=slippage_pips,
            holding_days=holding_days,
        ).costs
