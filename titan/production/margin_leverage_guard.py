"""
TITAN XAU AI - Margin, Leverage, and Risk Guard (Sprint 9.9.3.45.8.3)
=====================================================================
Calculates required margin, margin usage, risk per trade, drawdown
remaining, and validates against account profile constraints.

Blockers:
  - MARGIN_USAGE_TOO_HIGH
  - RISK_PER_TRADE_TOO_HIGH
  - DAILY_DD_LIMIT_RISK
  - TOTAL_DD_LIMIT_RISK
  - LEVERAGE_PROFILE_MISSING
  - ACCOUNT_PROFILE_MISSING
  - SYMBOL_CONTRACT_SIZE_MISSING

NEVER sends orders. NEVER modifies positions.
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional
import yaml
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ACCOUNT_PROFILES_PATH = REPO_ROOT / "config" / "account_profiles.yaml"
BROKER_PROFILES_PATH = REPO_ROOT / "config" / "broker_profiles.yaml"


@dataclass
class MarginRiskResult:
    """Output of margin/leverage/risk calculation."""
    symbol: str = "XAUUSD"
    price: float = 0.0
    contract_size: float = 100.0
    lot: float = 0.01
    notional: float = 0.0
    leverage: int = 100
    required_margin: float = 0.0
    balance: float = 0.0
    equity: float = 0.0
    free_margin_after_trade: float = 0.0
    margin_usage_pct: float = 0.0
    max_loss_if_SL: float = 0.0
    risk_pct: float = 0.0
    risk_amount: float = 0.0
    daily_dd_remaining: float = 0.0
    total_dd_remaining: float = 0.0
    prop_firm_safe: bool = False
    retail_safe: bool = False
    institutional_safe: bool = False
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    account_profile: str = ""
    broker_profile: str = ""
    timestamp_utc: str = ""

    def __post_init__(self):
        if not self.timestamp_utc:
            self.timestamp_utc = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return asdict(self)


class MarginLeverageGuard:
    """Calculates margin, leverage, risk, and validates against account
    profile constraints.

    NEVER sends orders. NEVER modifies positions.
    """

    def __init__(self, account_profile_name: str = "retail_demo_micro",
                 broker_profile_name: str = "metaquotes_demo"):
        self.account_profile_name = account_profile_name
        self.broker_profile_name = broker_profile_name
        self.account_profile = self._load_account_profile(account_profile_name)
        self.broker_profile = self._load_broker_profile(broker_profile_name)

    def _load_account_profile(self, name: str) -> dict:
        if not ACCOUNT_PROFILES_PATH.exists():
            return {}
        try:
            with open(ACCOUNT_PROFILES_PATH, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            return data.get("profiles", {}).get(name, {})
        except Exception:
            return {}

    def _load_broker_profile(self, name: str) -> dict:
        if not BROKER_PROFILES_PATH.exists():
            return {}
        try:
            with open(BROKER_PROFILES_PATH, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            return data.get("brokers", {}).get(name, {})
        except Exception:
            return {}

    def calculate(self, *, symbol: str = "XAUUSD", price: float,
                  sl_price: float, lot: float = 0.01,
                  balance: float = 10000.0, equity: float = 10000.0,
                  daily_dd_used: float = 0.0,
                  total_dd_used: float = 0.0) -> MarginRiskResult:
        """Calculate margin, leverage, risk, and validate.

        NEVER sends orders. Returns MarginRiskResult only.
        """
        result = MarginRiskResult(
            symbol=symbol, price=price, lot=lot,
            balance=balance, equity=equity,
            account_profile=self.account_profile_name,
            broker_profile=self.broker_profile_name,
        )

        # Check account profile exists
        if not self.account_profile:
            result.blockers.append("ACCOUNT_PROFILE_MISSING")
            return result

        # Check leverage
        leverage = self.account_profile.get("leverage", 100)
        result.leverage = leverage

        # Get contract size from broker profile
        contract_size_key = f"contract_size_{symbol.lower()}"
        contract_size = self.broker_profile.get(contract_size_key, 100.0)
        if contract_size <= 0:
            result.blockers.append("SYMBOL_CONTRACT_SIZE_MISSING")
            return result
        result.contract_size = contract_size

        # Calculate notional
        notional = price * lot * contract_size
        result.notional = round(notional, 4)

        # Calculate required margin
        required_margin = notional / leverage
        result.required_margin = round(required_margin, 4)

        # Calculate margin usage
        if equity > 0:
            margin_usage_pct = required_margin / equity
        else:
            margin_usage_pct = 0.0
        result.margin_usage_pct = round(margin_usage_pct, 4)

        # Free margin after trade
        free_margin_after_trade = equity - required_margin
        result.free_margin_after_trade = round(free_margin_after_trade, 4)

        # Max loss if SL hit
        max_loss_if_SL = abs(price - sl_price) * lot * contract_size
        result.max_loss_if_SL = round(max_loss_if_SL, 4)

        # Risk percentage
        if balance > 0:
            risk_pct = max_loss_if_SL / balance
        else:
            risk_pct = 0.0
        result.risk_pct = round(risk_pct, 4)
        result.risk_amount = round(max_loss_if_SL, 4)

        # Drawdown remaining
        max_daily_dd = self.account_profile.get("max_daily_dd_pct", 0.05)
        max_total_dd = self.account_profile.get("max_total_dd_pct", 0.10)
        daily_dd_remaining = (max_daily_dd * balance) - daily_dd_used
        total_dd_remaining = (max_total_dd * balance) - total_dd_used
        result.daily_dd_remaining = round(daily_dd_remaining, 4)
        result.total_dd_remaining = round(total_dd_remaining, 4)

        # Validate: MARGIN_USAGE_TOO_HIGH
        max_margin_usage = self.account_profile.get("max_margin_usage_pct", 0.20)
        if margin_usage_pct > max_margin_usage:
            result.blockers.append(
                f"MARGIN_USAGE_TOO_HIGH: margin_usage_pct={margin_usage_pct:.4f} > max={max_margin_usage}"
            )

        # Validate: RISK_PER_TRADE_TOO_HIGH
        max_risk = self.account_profile.get("max_risk_per_trade_pct", 0.01)
        if risk_pct > max_risk:
            result.blockers.append(
                f"RISK_PER_TRADE_TOO_HIGH: risk_pct={risk_pct:.4f} > max={max_risk}"
            )

        # Validate: DAILY_DD_LIMIT_RISK
        if max_loss_if_SL > daily_dd_remaining:
            result.blockers.append(
                f"DAILY_DD_LIMIT_RISK: max_loss={max_loss_if_SL} > daily_dd_remaining={daily_dd_remaining}"
            )

        # Validate: TOTAL_DD_LIMIT_RISK
        if max_loss_if_SL > total_dd_remaining:
            result.blockers.append(
                f"TOTAL_DD_LIMIT_RISK: max_loss={max_loss_if_SL} > total_dd_remaining={total_dd_remaining}"
            )

        # Determine safety flags
        is_prop = "prop_firm" in self.account_profile_name or "funded" in self.account_profile_name
        is_institutional = "institutional" in self.account_profile_name
        is_retail = "retail" in self.account_profile_name

        result.prop_firm_safe = is_prop and len(result.blockers) == 0
        result.retail_safe = is_retail and len(result.blockers) == 0
        result.institutional_safe = is_institutional and len(result.blockers) == 0

        return result
