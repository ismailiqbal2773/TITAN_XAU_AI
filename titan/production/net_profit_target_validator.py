"""
TITAN XAU AI - Net Profit Target Validator (Sprint 9.9.3.45.8.3)
=================================================================
Validates that target gross profit, transaction costs, and net profit
satisfy the account profile constraints.

Blockers:
  - NET_PROFIT_TARGET_NOT_REACHED
  - COSTS_TOO_HIGH_FOR_TP_DISTANCE
  - NET_RR_BELOW_PROFILE_MINIMUM
  - TP_TOO_CLOSE_AFTER_SPREAD_COMMISSION
  - DYNAMIC_TP_TRIGGER_BEYOND_STATIC_TP
  - INITIAL_TP_TOO_CLOSE_FOR_DYNAMIC_TP

NEVER sends orders. NEVER modifies positions.
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional
import yaml
from pathlib import Path

from titan.production.transaction_cost_engine import (
    TransactionCostEngine, TransactionCostResult,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
ACCOUNT_PROFILES_PATH = REPO_ROOT / "config" / "account_profiles.yaml"


@dataclass
class NetProfitValidationResult:
    """Output of net profit target validation."""
    target_gross_profit: float = 0.0
    expected_total_transaction_cost: float = 0.0
    expected_net_profit: float = 0.0
    target_net_R: float = 0.0
    target_net_RR: float = 0.0
    profile_minimum_RR: float = 0.0
    tp_distance_after_costs: float = 0.0
    dynamic_tp_trigger_R: float = 0.0
    initial_tp_R: float = 0.0
    dynamic_tp_geometry_valid: bool = False
    cost_adjusted_geometry_valid: bool = False
    net_profit_target_reached: bool = False
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    cost_result: Optional[dict] = None
    account_profile: str = ""
    timestamp_utc: str = ""

    def __post_init__(self):
        if not self.timestamp_utc:
            self.timestamp_utc = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return asdict(self)


class NetProfitTargetValidator:
    """Validates net profit target against account profile constraints.

    NEVER sends orders. NEVER modifies positions.
    """

    def __init__(self, account_profile_name: str = "retail_demo_micro",
                 cost_profile_name: str = "zero_spread_demo"):
        self.account_profile_name = account_profile_name
        self.cost_profile_name = cost_profile_name
        self.account_profile = self._load_account_profile(account_profile_name)
        self.cost_engine = TransactionCostEngine(cost_profile_name)

    def _load_account_profile(self, name: str) -> dict:
        """Load account profile from YAML."""
        if not ACCOUNT_PROFILES_PATH.exists():
            return {}
        try:
            with open(ACCOUNT_PROFILES_PATH, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            profiles = data.get("profiles", {})
            return profiles.get(name, {})
        except Exception:
            return {}

    def validate(self, *, direction: str, entry_price: float,
                 sl_price: float, tp_price: float, lot: float = 0.01,
                 initial_tp_R: float = 3.0,
                 dynamic_tp_trigger_R: float = 2.0,
                 dynamic_tp_enabled: bool = False,
                 nights_held: int = 0) -> NetProfitValidationResult:
        """Validate net profit target against account profile.

        NEVER sends orders. Returns NetProfitValidationResult only.
        """
        result = NetProfitValidationResult(
            account_profile=self.account_profile_name,
            initial_tp_R=initial_tp_R,
            dynamic_tp_trigger_R=dynamic_tp_trigger_R,
            profile_minimum_RR=self.account_profile.get("minimum_RR", 1.5),
        )

        # Calculate transaction costs
        cost_result = self.cost_engine.calculate(
            direction=direction,
            entry_price=entry_price,
            sl_price=sl_price,
            tp_price=tp_price,
            lot=lot,
            current_price=tp_price,  # Use TP as projection for target
            nights_held=nights_held,
        )
        result.cost_result = cost_result.to_dict()
        result.target_gross_profit = cost_result.gross_profit
        result.expected_total_transaction_cost = cost_result.total_transaction_cost
        result.expected_net_profit = cost_result.net_profit
        result.target_net_R = cost_result.net_R
        result.target_net_RR = cost_result.net_RR

        # TP distance after costs
        R = abs(entry_price - sl_price)
        tp_distance = abs(tp_price - entry_price)
        cost_per_unit = cost_result.total_transaction_cost / (lot * cost_result.contract_size) if lot > 0 else 0.0
        result.tp_distance_after_costs = tp_distance - cost_per_unit

        # Check: NET_PROFIT_TARGET_NOT_REACHED
        # Net profit must be positive
        if cost_result.net_profit <= 0:
            result.blockers.append(
                f"NET_PROFIT_TARGET_NOT_REACHED: net_profit={cost_result.net_profit} <= 0"
            )

        # Check: COSTS_TOO_HIGH_FOR_TP_DISTANCE
        # If costs eat more than 50% of TP distance, block
        if tp_distance > 0 and cost_per_unit > 0:
            cost_ratio = cost_per_unit / tp_distance
            if cost_ratio > 0.5:
                result.blockers.append(
                    f"COSTS_TOO_HIGH_FOR_TP_DISTANCE: cost_ratio={cost_ratio:.2f} > 0.50"
                )

        # Check: NET_RR_BELOW_PROFILE_MINIMUM
        if cost_result.net_RR < self.account_profile.get("minimum_RR", 1.5):
            result.blockers.append(
                f"NET_RR_BELOW_PROFILE_MINIMUM: net_RR={cost_result.net_RR} < minimum_RR={self.account_profile.get('minimum_RR', 1.5)}"
            )

        # Check: TP_TOO_CLOSE_AFTER_SPREAD_COMMISSION
        # If TP distance after costs is less than 0.5 * R, too close
        if R > 0 and result.tp_distance_after_costs < 0.5 * R:
            result.blockers.append(
                f"TP_TOO_CLOSE_AFTER_SPREAD_COMMISSION: tp_distance_after_costs={result.tp_distance_after_costs} < 0.5*R={0.5 * R}"
            )

        # Dynamic TP geometry checks
        if dynamic_tp_enabled:
            # Check: DYNAMIC_TP_TRIGGER_BEYOND_STATIC_TP
            # initial_tp_R must be > dynamic_tp_trigger_R
            if initial_tp_R <= dynamic_tp_trigger_R:
                result.blockers.append(
                    f"DYNAMIC_TP_TRIGGER_BEYOND_STATIC_TP: initial_tp_R={initial_tp_R} <= dynamic_tp_trigger_R={dynamic_tp_trigger_R}"
                )
                result.dynamic_tp_geometry_valid = False
            else:
                result.dynamic_tp_geometry_valid = True

            # Check: INITIAL_TP_TOO_CLOSE_FOR_DYNAMIC_TP
            # initial_tp_R must be >= 3.0 for dynamic TP proof
            if initial_tp_R < 3.0:
                result.blockers.append(
                    f"INITIAL_TP_TOO_CLOSE_FOR_DYNAMIC_TP: initial_tp_R={initial_tp_R} < 3.0"
                )
                result.dynamic_tp_geometry_valid = False

            # RR 1:1 blocked for prop/funded/institutional dynamic TP
            account_type = self.account_profile.get("account_type", "")
            is_prop_or_funded = (
                "prop_firm" in self.account_profile_name
                or "funded" in self.account_profile_name
                or "institutional" in self.account_profile_name
            )
            if is_prop_or_funded and initial_tp_R < 2.0:
                result.blockers.append(
                    f"RR_1_1_BLOCKED_FOR_PROP_DYNAMIC_TP: initial_tp_R={initial_tp_R} < 2.0 for {self.account_profile_name}"
                )
                result.dynamic_tp_geometry_valid = False
        else:
            result.dynamic_tp_geometry_valid = True  # No dynamic TP, geometry OK

        # Cost-adjusted geometry valid if net_RR > 0 and net_profit > 0
        result.cost_adjusted_geometry_valid = (
            cost_result.net_RR > 0 and cost_result.net_profit > 0
        )

        # Net profit target reached if no blockers
        result.net_profit_target_reached = len(result.blockers) == 0

        return result
