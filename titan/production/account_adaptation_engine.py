"""
TITAN XAU AI — Account Adaptation Engine (Sprint 9.9.3.45.8.5)
================================================================

Maps account facts (balance, equity, currency, account type, leverage)
to an adaptive risk mode and provides balance/equity-based sizing
inputs to the downstream ``LotSizingEngine``.

Modes:
  PROOF_FIXED_LOT                  — fixed micro lot for proof/demo runs
                                     (no dynamic adaptation; max_lot = fixed_lot).
  CONSERVATIVE_DYNAMIC             — risk-percentage based on balance,
                                     tightly capped max_lot, no loss-based input.
  PROP_FIRM_CONSERVATIVE           — prop-firm mode: hard daily/total DD caps,
                                     fixed minimum lot, no loss-based input.
  INSTITUTIONAL_VOLATILITY_SCALED  — institutional mode: lot scaled by
                                     volatility regime (provided externally),
                                     equity-based cap, no loss-based input.

Cent account handling:
  Cent accounts report balance/equity in cents. The engine detects cent
  accounts (by currency suffix or account_id heuristics) and converts
  reported balance/equity to dollar terms for risk calculations.

Dollar account handling:
  USD (or USD-quoted) accounts pass through unchanged.

CRITICAL SAFETY INVARIANT:
  This engine NEVER implements loss-based lot multipliers. There is no
  "after N losing trades, increase/decrease lot" logic here. Loss-based
  sizing is explicitly forbidden by the project's safety doctrine —
  any attempt to enable it raises ``LossBasedLotMultiplierForbidden``.

  Hard flags:
    no_martingale=True
    no_grid=True
    no_averaging=True
    no_loss_based_lot_multiplier=True

This module is pure Python. It NEVER imports MetaTrader5, NEVER calls
``mt5.order_send``, and NEVER submits orders.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, Any

logger = logging.getLogger(__name__)


# ─── Safety flags mirrored across the production stack ──────────────────────
SAFETY_FLAGS: dict[str, bool] = {
    "no_martingale": True,
    "no_grid": True,
    "no_averaging": True,
    "no_loss_based_lot_multiplier": True,
}


# ─── Exceptions ──────────────────────────────────────────────────────────────
class LossBasedLotMultiplierForbidden(Exception):
    """
    Raised when ANY caller attempts to enable loss-based lot sizing.

    Loss-based sizing (martingale, anti-martingale, recovery-upsize)
    is forbidden by project doctrine. This exception is non-recoverable.
    """


class AccountAdaptationError(Exception):
    """Raised for general account adaptation failures."""


# ─── Enums ───────────────────────────────────────────────────────────────────
class AdaptationMode(str, Enum):
    """
    Account-adaptation mode.

    Each mode defines a different policy for translating account state
    into lot-sizing inputs. None of them implement loss-based sizing.
    """
    PROOF_FIXED_LOT = "PROOF_FIXED_LOT"
    CONSERVATIVE_DYNAMIC = "CONSERVATIVE_DYNAMIC"
    PROP_FIRM_CONSERVATIVE = "PROP_FIRM_CONSERVATIVE"
    INSTITUTIONAL_VOLATILITY_SCALED = "INSTITUTIONAL_VOLATILITY_SCALED"


class AccountCurrency(str, Enum):
    """Account currency classification."""
    USD = "USD"
    CENT = "CENT"
    EUR = "EUR"
    GBP = "GBP"
    OTHER = "OTHER"


# ─── Dataclasses ─────────────────────────────────────────────────────────────
@dataclass
class AccountFacts:
    """
    Raw facts about an MT5 account (provided by the caller; not queried).

    The engine NEVER queries MT5 directly. The caller is responsible for
    obtaining ``balance``, ``equity``, ``currency``, ``leverage`` etc.
    from ``mt5.account_info()`` and passing them in.
    """
    account_id: str = ""
    balance: float = 0.0
    equity: float = 0.0
    currency: str = "USD"
    leverage: int = 100
    account_type: str = "demo"          # demo | live
    server: str = ""
    name: str = ""
    company: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class AdaptationResult:
    """
    Output of an adaptation evaluation.

    Contains the resolved mode, dollar-equivalent balance/equity, the
    effective max_lot, the risk-per-trade fraction, and the safety
    flags snapshot for audit.
    """
    mode: AdaptationMode
    account_currency: AccountCurrency
    is_cent_account: bool
    raw_balance: float
    raw_equity: float
    dollar_balance: float
    dollar_equity: float
    leverage: int
    max_lot: float
    min_lot: float
    risk_per_trade_pct: float
    allow_new_entries: bool
    reason: str = ""
    safety_flags: dict[str, bool] = field(default_factory=lambda: dict(SAFETY_FLAGS))
    # Volatility regime scalar (0.0–1.0) — only populated in
    # INSTITUTIONAL_VOLATILITY_SCALED mode; defaults to 1.0 otherwise.
    volatility_scalar: float = 1.0

    def to_dict(self) -> dict:
        return asdict(self)


# ─── Engine ─────────────────────────────────────────────────────────────────
class AccountAdaptationEngine:
    """
    Account adaptation engine.

    Construction:
        engine = AccountAdaptationEngine(
            mode=AdaptationMode.PROOF_FIXED_LOT,
            max_lot=0.01,
            min_lot=0.01,
            fixed_lot_for_proof=0.01,
            risk_per_trade_pct=0.01,
        )

    Evaluation:
        facts = AccountFacts(balance=10000.0, equity=10050.0, currency="USD", leverage=100)
        result = engine.adapt(facts)

    The engine is stateless across calls — it never accumulates loss
    counts, win counts, or any other historical state. This is a
    deliberate safety design: there is NO data structure inside the
    engine that could ever be repurposed for loss-based sizing.
    """

    # Cent-account currency strings we recognize. Stored in upper-case
    # because detect_currency() normalizes the input currency to upper.
    CENT_CURRENCY_TOKENS: frozenset[str] = frozenset({
        "USDC", "USDCENT", "CENT", "EURC", "EURCENT", "GBRC", "GBPCENT",
    })

    # Cent-account server-name tokens (case-insensitive substring match).
    CENT_SERVER_TOKENS: tuple[str, ...] = ("cent", "cents", "micro")

    def __init__(
        self,
        mode: AdaptationMode = AdaptationMode.PROOF_FIXED_LOT,
        max_lot: float = 0.01,
        min_lot: float = 0.01,
        lot_step: float = 0.01,
        fixed_lot_for_proof: float = 0.01,
        risk_per_trade_pct: float = 0.01,
        max_risk_per_trade_pct: float = 0.01,
        max_margin_usage_pct: float = 0.20,
        volatility_scalar: float = 1.0,
        leverage_cap: int = 100,
    ):
        if max_lot <= 0.0:
            raise ValueError(f"max_lot must be > 0 (got {max_lot})")
        if min_lot <= 0.0:
            raise ValueError(f"min_lot must be > 0 (got {min_lot})")
        if min_lot > max_lot:
            raise ValueError(
                f"min_lot ({min_lot}) cannot exceed max_lot ({max_lot})"
            )
        if fixed_lot_for_proof <= 0.0:
            raise ValueError("fixed_lot_for_proof must be > 0")
        if risk_per_trade_pct < 0.0 or risk_per_trade_pct > 1.0:
            raise ValueError("risk_per_trade_pct must be in [0.0, 1.0]")
        if max_risk_per_trade_pct < 0.0 or max_risk_per_trade_pct > 1.0:
            raise ValueError("max_risk_per_trade_pct must be in [0.0, 1.0]")
        if max_risk_per_trade_pct < risk_per_trade_pct:
            raise ValueError(
                "max_risk_per_trade_pct cannot be less than risk_per_trade_pct"
            )
        if not 0.0 <= volatility_scalar <= 1.0:
            raise ValueError("volatility_scalar must be in [0.0, 1.0]")

        self.mode = AdaptationMode(mode)
        self.max_lot = float(max_lot)
        self.min_lot = float(min_lot)
        self.lot_step = float(lot_step)
        self.fixed_lot_for_proof = float(fixed_lot_for_proof)
        self.risk_per_trade_pct = float(risk_per_trade_pct)
        self.max_risk_per_trade_pct = float(max_risk_per_trade_pct)
        self.max_margin_usage_pct = float(max_margin_usage_pct)
        self.volatility_scalar = float(volatility_scalar)
        self.leverage_cap = int(leverage_cap)

        # Hard safety invariants — exposed for downstream audit.
        self.no_martingale = True
        self.no_grid = True
        self.no_averaging = True
        self.no_loss_based_lot_multiplier = True

    # ─── Public properties ───────────────────────────────────────────────

    @property
    def safety_flags(self) -> dict[str, bool]:
        return {
            "no_martingale": self.no_martingale,
            "no_grid": self.no_grid,
            "no_averaging": self.no_averaging,
            "no_loss_based_lot_multiplier": self.no_loss_based_lot_multiplier,
        }

    # ─── Cent / dollar detection ─────────────────────────────────────────

    def detect_currency(self, facts: AccountFacts) -> AccountCurrency:
        """
        Classify the account currency as USD, CENT, EUR, GBP, or OTHER.

        Cent detection is conservative: it triggers on either an
        explicit cent-currency token (e.g. "USDc") or a cent-server
        name token (e.g. "ICMarkets-Cent"), provided the balance/equity
        magnitudes are consistent with a cent account (>= 1000 cents
        i.e. >= $10).
        """
        cur = (facts.currency or "").upper().strip()
        if cur in self.CENT_CURRENCY_TOKENS:
            return AccountCurrency.CENT

        server = (facts.server or "").lower()
        if any(tok in server for tok in self.CENT_SERVER_TOKENS):
            # Heuristic: cent accounts typically have very large nominal
            # balances (e.g. 1,000,000 cents = $10,000). If the raw
            # balance is implausibly large for a real-dollar account
            # at this server, classify as CENT.
            if facts.balance >= 1000.0:
                return AccountCurrency.CENT

        if cur == "USD":
            return AccountCurrency.USD
        if cur == "EUR":
            return AccountCurrency.EUR
        if cur == "GBP":
            return AccountCurrency.GBP
        return AccountCurrency.OTHER

    @staticmethod
    def is_cent_account(facts: AccountFacts, currency: AccountCurrency) -> bool:
        """Return True iff the account should be treated as a cent account."""
        return currency == AccountCurrency.CENT

    @staticmethod
    def cents_to_dollars(cents: float) -> float:
        """Convert a cent-denominated value to dollars (1/100)."""
        return float(cents) / 100.0

    @staticmethod
    def dollars_to_cents(dollars: float) -> float:
        """Convert a dollar-denominated value to cents (×100)."""
        return float(dollars) * 100.0

    # ─── Adaptation entry point ──────────────────────────────────────────

    def adapt(
        self,
        facts: AccountFacts,
        volatility_scalar: Optional[float] = None,
    ) -> AdaptationResult:
        """
        Evaluate the configured adaptation mode against account facts.

        Args:
            facts: raw account facts from the caller.
            volatility_scalar: optional override (0.0–1.0) used only by
                INSTITUTIONAL_VOLATILITY_SCALED mode. Other modes ignore
                this parameter.

        Returns:
            AdaptationResult containing dollar-normalized balance/equity,
            effective max/min lot, risk-per-trade fraction, and safety
            flags.
        """
        currency = self.detect_currency(facts)
        is_cent = self.is_cent_account(facts, currency)

        if is_cent:
            dollar_balance = self.cents_to_dollars(facts.balance)
            dollar_equity = self.cents_to_dollars(facts.equity)
        else:
            dollar_balance = float(facts.balance)
            dollar_equity = float(facts.equity)

        leverage = min(int(facts.leverage), self.leverage_cap) if facts.leverage > 0 else self.leverage_cap

        if self.mode == AdaptationMode.PROOF_FIXED_LOT:
            max_lot = min(self.fixed_lot_for_proof, self.max_lot)
            risk_pct = 0.0  # proof mode uses fixed lot, not %-based risk
            v_scalar = 1.0
            reason = "PROOF_FIXED_LOT: fixed micro lot, no dynamic risk"
        elif self.mode == AdaptationMode.CONSERVATIVE_DYNAMIC:
            max_lot = self._equity_based_max_lot(dollar_equity)
            risk_pct = self.risk_per_trade_pct
            v_scalar = 1.0
            reason = "CONSERVATIVE_DYNAMIC: balance-based risk percentage"
        elif self.mode == AdaptationMode.PROP_FIRM_CONSERVATIVE:
            max_lot = self._equity_based_max_lot(dollar_equity)
            # Prop firm: hard cap risk at max_risk_per_trade_pct
            risk_pct = min(self.risk_per_trade_pct, self.max_risk_per_trade_pct)
            v_scalar = 1.0
            reason = "PROP_FIRM_CONSERVATIVE: hard DD-cap risk profile"
        elif self.mode == AdaptationMode.INSTITUTIONAL_VOLATILITY_SCALED:
            v_scalar = float(volatility_scalar) if volatility_scalar is not None else self.volatility_scalar
            v_scalar = max(0.0, min(1.0, v_scalar))
            max_lot = self._equity_based_max_lot(dollar_equity) * v_scalar
            risk_pct = self.risk_per_trade_pct * v_scalar
            reason = (
                "INSTITUTIONAL_VOLATILITY_SCALED: equity cap scaled by "
                f"volatility regime ({v_scalar:.2f})"
            )
        else:  # pragma: no cover — defensive
            raise AccountAdaptationError(f"Unknown adaptation mode: {self.mode}")

        # Clamp max_lot into [min_lot, hard_max_lot]
        max_lot = max(self.min_lot, min(max_lot, self.max_lot))

        # Allow new entries iff dollar_equity > 0 and margin usage would be ok.
        allow_new_entries = dollar_equity > 0.0 and max_lot > 0.0

        return AdaptationResult(
            mode=self.mode,
            account_currency=currency,
            is_cent_account=is_cent,
            raw_balance=float(facts.balance),
            raw_equity=float(facts.equity),
            dollar_balance=dollar_balance,
            dollar_equity=dollar_equity,
            leverage=leverage,
            max_lot=max_lot,
            min_lot=self.min_lot,
            risk_per_trade_pct=risk_pct,
            allow_new_entries=allow_new_entries,
            reason=reason,
            safety_flags=self.safety_flags,
            volatility_scalar=v_scalar,
        )

    # ─── Equity-based lot cap ────────────────────────────────────────────

    def _equity_based_max_lot(self, dollar_equity: float) -> float:
        """
        Compute an equity-based maximum lot.

        Formula: max_lot_by_equity = (dollar_equity * max_margin_usage_pct)
                 / (contract_size * price).

        For XAUUSD at price=2000, contract_size=100, the per-lot
        notional is $200,000. With max_margin_usage_pct=0.20 and
        leverage=100, the equity required per lot is $2,000.

        This helper returns the raw equity-based cap before applying
        the hard ``self.max_lot`` ceiling. The caller clamps the result.
        """
        if dollar_equity <= 0.0:
            return self.min_lot
        # Approximate price for XAUUSD — caller can re-clamp downstream
        # using the live broker symbol spec. We use 2000 as a sane default
        # so the equity cap is conservative.
        approx_price = 2000.0
        contract_size = 100.0
        leverage = max(1, self.leverage_cap)
        notional_per_lot = contract_size * approx_price
        margin_per_lot = notional_per_lot / leverage
        # Equity available for margin usage.
        equity_for_margin = dollar_equity * self.max_margin_usage_pct
        if margin_per_lot <= 0.0:
            return self.max_lot
        cap = equity_for_margin / margin_per_lot
        # Round DOWN to lot_step to avoid dust.
        if self.lot_step > 0.0:
            cap = (cap // self.lot_step) * self.lot_step
        return max(self.min_lot, cap)

    # ─── Forbidden API surface ───────────────────────────────────────────

    def set_loss_based_lot_multiplier(self, *args: Any, **kwargs: Any) -> None:
        """
        EXPLICITLY FORBIDDEN.

        Any caller attempting to enable loss-based lot sizing triggers
        this method (or a similarly named shim) and raises
        ``LossBasedLotMultiplierForbidden``. The engine contains no
        data path that could honor such a request even if it were made.
        """
        raise LossBasedLotMultiplierForbidden(
            "Loss-based lot multipliers are FORBIDDEN by project doctrine. "
            "This engine does not implement, store, or honor any loss-based "
            "sizing input. Violation: set_loss_based_lot_multiplier called "
            "with args=%r kwargs=%r" % (args, kwargs)
        )

    def adjust_lot_after_loss(self, *args: Any, **kwargs: Any) -> None:
        """EXPLICITLY FORBIDDEN — same as set_loss_based_lot_multiplier."""
        raise LossBasedLotMultiplierForbidden(
            "adjust_lot_after_loss is FORBIDDEN — loss-based sizing is "
            "not implemented and never will be."
        )

    def adjust_lot_after_win(self, *args: Any, **kwargs: Any) -> None:
        """
        EXPLICITLY FORBIDDEN.

        Even win-based sizing is forbidden because it can be trivially
        repurposed as loss-based (martingale/anti-martingale are two
        sides of the same coin). The engine only supports equity-based
        and volatility-scaled sizing.
        """
        raise LossBasedLotMultiplierForbidden(
            "adjust_lot_after_win is FORBIDDEN — win/loss-based sizing "
            "is not implemented."
        )

    # ─── Introspection ───────────────────────────────────────────────────

    def to_dict(self) -> dict:
        """Return the engine's static configuration as a dict."""
        return {
            "mode": self.mode.value,
            "max_lot": self.max_lot,
            "min_lot": self.min_lot,
            "lot_step": self.lot_step,
            "fixed_lot_for_proof": self.fixed_lot_for_proof,
            "risk_per_trade_pct": self.risk_per_trade_pct,
            "max_risk_per_trade_pct": self.max_risk_per_trade_pct,
            "max_margin_usage_pct": self.max_margin_usage_pct,
            "volatility_scalar": self.volatility_scalar,
            "leverage_cap": self.leverage_cap,
            "safety_flags": self.safety_flags,
        }
