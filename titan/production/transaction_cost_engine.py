"""
TITAN XAU AI - Transaction Cost Engine (Sprint 9.9.3.45.8.3)
==============================================================
Computes gross vs net profit, spread cost, commission cost, slippage
cost, swap cost, and cost-adjusted TP/SL/RR.

Formula:
  net_profit = gross_profit - spread_cost - commission_cost - slippage_cost - swap_cost

NEVER evaluates profit target only on gross profit.
All readiness reports show both gross and net.

NEVER sends orders. NEVER modifies positions.
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional
import yaml
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
COST_PROFILES_PATH = REPO_ROOT / "config" / "transaction_cost_profiles.yaml"


@dataclass
class TransactionCostResult:
    """Output of a single transaction cost calculation."""
    gross_profit: float = 0.0
    spread_cost: float = 0.0
    commission_cost: float = 0.0
    slippage_cost: float = 0.0
    swap_cost: float = 0.0
    total_transaction_cost: float = 0.0
    net_profit: float = 0.0
    gross_R: float = 0.0
    net_R: float = 0.0
    gross_RR: float = 0.0
    net_RR: float = 0.0
    break_even_price_after_cost: float = 0.0
    minimum_price_move_to_profit: float = 0.0
    cost_adjusted_TP: float = 0.0
    cost_adjusted_SL: float = 0.0
    cost_adjusted_expectancy: float = 0.0
    direction: str = "BUY"
    entry_price: float = 0.0
    sl_price: float = 0.0
    tp_price: float = 0.0
    lot: float = 0.01
    contract_size: float = 100.0
    spread: float = 0.0
    commission_per_lot_round_turn: float = 0.0
    slippage: float = 0.0
    swap_long_per_lot_per_night: float = 0.0
    swap_short_per_lot_per_night: float = 0.0
    nights_held: int = 0
    cost_profile: str = ""
    timestamp_utc: str = ""

    def __post_init__(self):
        if not self.timestamp_utc:
            self.timestamp_utc = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return asdict(self)


class TransactionCostEngine:
    """Computes gross vs net profit, spread/commission/slippage/swap costs,
    and cost-adjusted TP/SL/RR.

    NEVER sends orders. NEVER modifies positions.
    """

    def __init__(self, cost_profile_name: str = "zero_spread_demo"):
        self.cost_profile_name = cost_profile_name
        self.profile = self._load_profile(cost_profile_name)

    def _load_profile(self, name: str) -> dict:
        """Load transaction cost profile from YAML."""
        if not COST_PROFILES_PATH.exists():
            return {}
        try:
            with open(COST_PROFILES_PATH, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            profiles = data.get("profiles", {})
            return profiles.get(name, {})
        except Exception:
            return {}

    def calculate(self, *, direction: str, entry_price: float,
                  sl_price: float, tp_price: float, lot: float = 0.01,
                  current_price: float = 0.0, nights_held: int = 0,
                  custom_spread: float = 0.0,
                  custom_commission: float = 0.0,
                  custom_slippage: float = 0.0) -> TransactionCostResult:
        """Calculate transaction costs and net profit.

        For a closed trade: current_price = close_price.
        For an open trade: current_price = current market price (unrealized).

        NEVER sends orders. Returns TransactionCostResult only.
        """
        contract_size = self.profile.get("contract_size_xauusd", 100.0)
        spread = custom_spread if custom_spread > 0 else self.profile.get("spread_xauusd", 0.0)
        commission_per_lot = (custom_commission if custom_commission > 0
                              else self.profile.get("commission_per_lot_round_turn", 0.0))
        slippage = custom_slippage if custom_slippage > 0 else self.profile.get("typical_slippage_xauusd", 0.0)
        swap_long = self.profile.get("swap_long_per_lot_per_night", 0.0)
        swap_short = self.profile.get("swap_short_per_lot_per_night", 0.0)

        # Compute gross profit
        if current_price == 0.0:
            current_price = tp_price  # If no close price, use TP for projection

        if direction == "BUY":
            gross_profit = (current_price - entry_price) * lot * contract_size
        else:
            gross_profit = (entry_price - current_price) * lot * contract_size

        # Spread cost (round turn: paid on entry and exit)
        spread_cost = spread * lot * contract_size

        # Commission cost (per lot round turn)
        commission_cost = commission_per_lot * lot

        # Slippage cost (assume slippage on both entry and exit)
        slippage_cost = slippage * 2 * lot * contract_size

        # Swap cost
        if direction == "BUY":
            swap_cost = swap_long * lot * nights_held
        else:
            swap_cost = swap_short * lot * nights_held

        total_transaction_cost = spread_cost + commission_cost + slippage_cost + swap_cost
        net_profit = gross_profit - total_transaction_cost

        # Compute R (risk = abs(entry - SL) * lot * contract_size)
        R = abs(entry_price - sl_price) * lot * contract_size
        gross_R = gross_profit / R if R > 0 else 0.0
        net_R = net_profit / R if R > 0 else 0.0

        # Compute RR (reward:risk ratio based on TP and SL)
        gross_RR = abs(tp_price - entry_price) / abs(entry_price - sl_price) if sl_price != entry_price else 0.0
        # Net RR = (TP distance - costs) / SL distance
        cost_per_unit = total_transaction_cost / (lot * contract_size) if lot > 0 else 0.0
        net_tp_distance = abs(tp_price - entry_price) - cost_per_unit
        net_RR = net_tp_distance / abs(entry_price - sl_price) if sl_price != entry_price else 0.0

        # Break-even price after cost
        cost_per_unit_for_be = total_transaction_cost / (lot * contract_size) if lot > 0 else 0.0
        if direction == "BUY":
            break_even_price_after_cost = entry_price + cost_per_unit_for_be
        else:
            break_even_price_after_cost = entry_price - cost_per_unit_for_be

        # Minimum price move to profit (after costs)
        minimum_price_move_to_profit = cost_per_unit_for_be

        # Cost-adjusted TP and SL
        if direction == "BUY":
            cost_adjusted_TP = tp_price - cost_per_unit_for_be
            cost_adjusted_SL = sl_price + cost_per_unit_for_be  # SL gets worse by cost
        else:
            cost_adjusted_TP = tp_price + cost_per_unit_for_be
            cost_adjusted_SL = sl_price - cost_per_unit_for_be

        # Cost-adjusted expectancy (assuming 50% win rate for simplicity;
        # caller can override with actual win rate)
        win_amount = net_profit if net_profit > 0 else 0.0
        loss_amount = -R - total_transaction_cost if net_profit <= 0 else -R - total_transaction_cost
        cost_adjusted_expectancy = (0.5 * win_amount) + (0.5 * loss_amount)

        return TransactionCostResult(
            gross_profit=round(gross_profit, 4),
            spread_cost=round(spread_cost, 4),
            commission_cost=round(commission_cost, 4),
            slippage_cost=round(slippage_cost, 4),
            swap_cost=round(swap_cost, 4),
            total_transaction_cost=round(total_transaction_cost, 4),
            net_profit=round(net_profit, 4),
            gross_R=round(gross_R, 4),
            net_R=round(net_R, 4),
            gross_RR=round(gross_RR, 4),
            net_RR=round(net_RR, 4),
            break_even_price_after_cost=round(break_even_price_after_cost, 4),
            minimum_price_move_to_profit=round(minimum_price_move_to_profit, 4),
            cost_adjusted_TP=round(cost_adjusted_TP, 4),
            cost_adjusted_SL=round(cost_adjusted_SL, 4),
            cost_adjusted_expectancy=round(cost_adjusted_expectancy, 4),
            direction=direction,
            entry_price=entry_price,
            sl_price=sl_price,
            tp_price=tp_price,
            lot=lot,
            contract_size=contract_size,
            spread=spread,
            commission_per_lot_round_turn=commission_per_lot,
            slippage=slippage,
            swap_long_per_lot_per_night=swap_long,
            swap_short_per_lot_per_night=swap_short,
            nights_held=nights_held,
            cost_profile=self.cost_profile_name,
        )
