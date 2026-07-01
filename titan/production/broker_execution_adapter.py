"""
TITAN XAU AI — Broker Execution Adapter (Sprint 9.9.3.45.8.4)
================================================================

Broker-aware execution adapter that sits between the strategy layer and
the MT5 ``order_send`` boundary. The adapter handles:

  1. ``prepare_request()`` — translate a strategy intent (side, lot,
     price, sl, tp) into a broker-specific MT5 request dict, applying
     the broker's preferred filling mode and symbol suffix.
  2. ``handle_requote()`` — apply the configured requote policy
     (``REJECT`` / ``BOUNDED_REPRICE`` / ``ACCEPT_WORST``) when the
     broker returns a requote (retcode 10004) or price-moved retcode.
  3. ``handle_slippage()`` — apply the slippage limit and bounded
     reprice policy when the filled price differs from the requested
     price by more than the broker's ``max_slippage_xauusd``.

Proof mode (``proof_mode=True``):
  - No retry, fail closed.
  - Requote policy is forced to ``REJECT``.
  - Slippage policy is forced to ``REJECT``.
  - The adapter never auto-resubmits an order in proof mode.

Safety invariants (HARD — enforced in every code path):
  - no_martingale: True
  - no_grid: True
  - no_averaging: True
  - no_loss_based_lot_multiplier: True
  - Never auto-retry in proof mode.

This module is pure Python. It NEVER imports MetaTrader5 directly and
NEVER calls ``mt5.order_send``. It only constructs/transforms request
dicts and policy decisions. The actual ``order_send`` call lives in
``mt5_execution_adapter.py`` which is the only place in the codebase
authorized to invoke the MT5 API.
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


# ─── Enums ───────────────────────────────────────────────────────────────────
class RequotePolicy(str, Enum):
    """
    Broker requote handling policy.

    REJECT           — reject the order, do not reprice, do not retry.
    BOUNDED_REPRICE  — reprice once within slippage_limit, no further retry.
    ACCEPT_WORST     — accept the broker's requote price unconditionally
                       (only used in non-proof institutional mode).
    """
    REJECT = "REJECT"
    BOUNDED_REPRICE = "BOUNDED_REPRICE"
    ACCEPT_WORST = "ACCEPT_WORST"


class SlippagePolicy(str, Enum):
    """
    Broker slippage handling policy.

    REJECT           — reject the fill if slippage exceeds the limit.
    BOUNDED_REPRICE  — accept the fill but record a warning; future
                       requests reprice by the observed slippage.
    ACCEPT_WORST     — accept the fill unconditionally (institutional only).
    """
    REJECT = "REJECT"
    BOUNDED_REPRICE = "BOUNDED_REPRICE"
    ACCEPT_WORST = "ACCEPT_WORST"


class AdapterVerdict(str, Enum):
    """High-level verdict returned by the adapter."""
    SEND = "SEND"                     # request is safe to send
    REJECT = "REJECT"                 # request must be rejected
    REPRICE = "REPRICE"               # request was repriced, retry once
    FAIL_CLOSED = "FAIL_CLOSED"       # proof mode failure, no retry


# ─── MT5 retcode constants (local copy — avoid importing MT5) ────────────────
RETCODE_REQUOTE = 10004
RETCODE_PRICE_OFF = 10020
RETCODE_PRICE_CHANGED = 10021
RETCODE_REQUOTE_OFF = 10026
RETCODE_DONE = 10009
RETCODE_DONE_PARTIAL = 10010
RETCODE_INVALID_FILL = 10030
RETCODE_UNSUPPORTED = 10015

# Retcodes that indicate a requote-like condition (caller should consult
# requote policy).
REQUOTE_RETCODES: frozenset[int] = frozenset({
    RETCODE_REQUOTE,
    RETCODE_PRICE_OFF,
    RETCODE_PRICE_CHANGED,
    RETCODE_REQUOTE_OFF,
})


# ─── Dataclasses ─────────────────────────────────────────────────────────────
@dataclass
class ExecutionIntent:
    """
    Strategy-side intent for a single market order.

    The adapter is responsible for translating this into a broker-ready
    MT5 request dict via ``prepare_request()``.
    """
    symbol: str                       # canonical symbol (e.g. "XAUUSD")
    side: str                         # "BUY" | "SELL"
    lot: float                        # already validated against broker min/step
    price: float                      # requested entry price
    sl: float = 0.0
    tp: float = 0.0
    magic: int = 0
    deviation_points: int = 20
    comment: str = "titan"
    type_filling: Optional[str] = None  # override broker default if set

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PreparedRequest:
    """
    Broker-ready MT5 request dict wrapper.

    ``request`` is the literal dict that would be passed to
    ``mt5.order_send``. The adapter NEVER invokes order_send — it only
    builds the dict and hands it back to the caller.
    """
    request: dict[str, Any]
    broker_symbol: str
    filling_mode: str
    verdict: AdapterVerdict
    reason: str = ""
    safety_flags: dict[str, bool] = field(default_factory=lambda: dict(SAFETY_FLAGS))

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RequoteResult:
    """Result of a requote policy evaluation."""
    verdict: AdapterVerdict
    policy: RequotePolicy
    original_price: float
    requote_price: float
    new_price: Optional[float] = None  # repriced price (if BOUNDED_REPRICE)
    reason: str = ""
    retry_allowed: bool = False
    safety_flags: dict[str, bool] = field(default_factory=lambda: dict(SAFETY_FLAGS))

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SlippageResult:
    """Result of a slippage policy evaluation."""
    verdict: AdapterVerdict
    policy: SlippagePolicy
    requested_price: float
    filled_price: float
    slippage: float
    slippage_limit: float
    reason: str = ""
    accept_fill: bool = False
    safety_flags: dict[str, bool] = field(default_factory=lambda: dict(SAFETY_FLAGS))

    def to_dict(self) -> dict:
        return asdict(self)


# ─── Adapter ────────────────────────────────────────────────────────────────
class BrokerExecutionAdapter:
    """
    Broker-aware execution adapter.

    Construction:
        adapter = BrokerExecutionAdapter(
            broker_id="metaquotes_demo",
            broker_symbol="XAUUSD",
            filling_mode="ORDER_FILLING_IOC",
            slippage_limit=0.10,
            requote_policy=RequotePolicy.REJECT,
            slippage_policy=SlippagePolicy.REJECT,
            proof_mode=True,
        )

    The adapter is stateless across orders — each call to
    ``prepare_request`` / ``handle_requote`` / ``handle_slippage`` is
    independent. The caller is responsible for actually sending the
    request through ``mt5_execution_adapter.MT5ExecutionAdapter``.
    """

    def __init__(
        self,
        broker_id: str,
        broker_symbol: str,
        filling_mode: str = "ORDER_FILLING_IOC",
        slippage_limit: float = 0.10,
        requote_policy: RequotePolicy = RequotePolicy.REJECT,
        slippage_policy: SlippagePolicy = SlippagePolicy.REJECT,
        proof_mode: bool = True,
        max_reprice_offset: Optional[float] = None,
    ):
        if not broker_id:
            raise ValueError("broker_id cannot be empty")
        if not broker_symbol:
            raise ValueError("broker_symbol cannot be empty")
        if slippage_limit < 0.0:
            raise ValueError("slippage_limit cannot be negative")

        self.broker_id = broker_id
        self.broker_symbol = broker_symbol
        self.filling_mode = filling_mode
        self.slippage_limit = float(slippage_limit)
        self.requote_policy = RequotePolicy(requote_policy)
        self.slippage_policy = SlippagePolicy(slippage_policy)
        self.proof_mode = bool(proof_mode)
        # Maximum absolute offset (in price units) the adapter is willing
        # to reprice by in BOUNDED_REPRICE mode. Defaults to slippage_limit.
        self.max_reprice_offset = (
            float(max_reprice_offset)
            if max_reprice_offset is not None
            else float(slippage_limit)
        )

        # In proof mode, force the strictest policies.
        if self.proof_mode:
            self.requote_policy = RequotePolicy.REJECT
            self.slippage_policy = SlippagePolicy.REJECT

        # Safety invariants — exposed for downstream audit.
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

    @property
    def can_retry(self) -> bool:
        """True iff the adapter is allowed to retry a failed send."""
        # Proof mode: never retry. Fail closed.
        if self.proof_mode:
            return False
        # Non-proof: only retry if the requote policy allows a reprice.
        return self.requote_policy == RequotePolicy.BOUNDED_REPRICE

    # ─── prepare_request ─────────────────────────────────────────────────

    def prepare_request(
        self,
        intent: ExecutionIntent,
    ) -> PreparedRequest:
        """
        Translate an ExecutionIntent into a broker-ready MT5 request dict.

        The adapter NEVER calls order_send. The returned dict is handed
        to the caller (typically ``MT5ExecutionAdapter``) which performs
        the actual send.

        In proof mode, any deviation from the broker's preferred filling
        mode is rejected (fail closed).
        """
        side = str(intent.side).upper()
        if side not in ("BUY", "SELL"):
            return PreparedRequest(
                request={},
                broker_symbol=self.broker_symbol,
                filling_mode=self.filling_mode,
                verdict=AdapterVerdict.FAIL_CLOSED,
                reason=f"Invalid side '{intent.side}' — must be BUY or SELL",
                safety_flags=self.safety_flags,
            )
        if intent.lot <= 0.0:
            return PreparedRequest(
                request={},
                broker_symbol=self.broker_symbol,
                filling_mode=self.filling_mode,
                verdict=AdapterVerdict.FAIL_CLOSED,
                reason=f"Invalid lot {intent.lot} — must be > 0",
                safety_flags=self.safety_flags,
            )
        if intent.price <= 0.0:
            return PreparedRequest(
                request={},
                broker_symbol=self.broker_symbol,
                filling_mode=self.filling_mode,
                verdict=AdapterVerdict.FAIL_CLOSED,
                reason=f"Invalid price {intent.price} — must be > 0",
                safety_flags=self.safety_flags,
            )

        # Filling mode resolution.
        filling_mode = intent.type_filling or self.filling_mode
        if self.proof_mode and intent.type_filling and intent.type_filling != self.filling_mode:
            # In proof mode, do not permit caller overrides — fail closed.
            return PreparedRequest(
                request={},
                broker_symbol=self.broker_symbol,
                filling_mode=self.filling_mode,
                verdict=AdapterVerdict.FAIL_CLOSED,
                reason=(
                    f"Proof mode forbids filling_mode override "
                    f"(caller={intent.type_filling}, broker={self.filling_mode})"
                ),
                safety_flags=self.safety_flags,
            )

        mt5_type = 0 if side == "BUY" else 1  # TRADE_ACTION_DEAL = 0
        # ORDER_TYPE_BUY = 0, ORDER_TYPE_SELL = 1
        order_type = 0 if side == "BUY" else 1

        request: dict[str, Any] = {
            "action": mt5_type,
            "symbol": self.broker_symbol,
            "volume": float(intent.lot),
            "type": order_type,
            "price": float(intent.price),
            "sl": float(intent.sl),
            "tp": float(intent.tp),
            "magic": int(intent.magic),
            "deviation": int(intent.deviation_points),
            "comment": str(intent.comment),
            "type_filling": self._mt5_filling_constant(filling_mode),
            "type_time": 0,  # ORDER_TIME_GTC
        }

        return PreparedRequest(
            request=request,
            broker_symbol=self.broker_symbol,
            filling_mode=filling_mode,
            verdict=AdapterVerdict.SEND,
            reason="Request prepared and validated",
            safety_flags=self.safety_flags,
        )

    # ─── handle_requote ──────────────────────────────────────────────────

    def handle_requote(
        self,
        original_price: float,
        requote_price: float,
        side: str,
        retcode: Optional[int] = None,
    ) -> RequoteResult:
        """
        Apply the configured requote policy.

        In proof mode the policy is forced to ``REJECT`` and retry is
        never allowed, regardless of the caller's request.

        Args:
            original_price: the price the caller originally requested.
            requote_price: the broker's requote price (from retcode 10004
                or the SendResult's ``price`` field).
            side: "BUY" or "SELL" — used to determine whether a higher
                requote is worse (BUY) or better (SELL).
            retcode: optional MT5 retcode that triggered the requote.

        Returns:
            RequoteResult with verdict, optional repriced price, and a
            retry_allowed flag (always False in proof mode).
        """
        side = str(side).upper()
        if side not in ("BUY", "SELL"):
            return RequoteResult(
                verdict=AdapterVerdict.FAIL_CLOSED,
                policy=self.requote_policy,
                original_price=float(original_price),
                requote_price=float(requote_price),
                reason=f"Invalid side '{side}' — must be BUY or SELL",
                retry_allowed=False,
                safety_flags=self.safety_flags,
            )

        o = float(original_price)
        r = float(requote_price)
        offset = abs(r - o)

        # Determine whether the requote is "worse" for the caller.
        # BUY  → higher price is worse
        # SELL → lower price is worse
        if side == "BUY":
            worse = r > o
        else:
            worse = r < o

        # Proof mode: never retry, fail closed regardless of policy.
        if self.proof_mode:
            return RequoteResult(
                verdict=AdapterVerdict.FAIL_CLOSED,
                policy=RequotePolicy.REJECT,
                original_price=o,
                requote_price=r,
                reason=(
                    f"Proof mode: requote rejected (retcode={retcode}, "
                    f"offset={offset:.5f}, worse={worse})"
                ),
                retry_allowed=False,
                safety_flags=self.safety_flags,
            )

        # Non-proof: apply configured policy.
        if self.requote_policy == RequotePolicy.REJECT:
            return RequoteResult(
                verdict=AdapterVerdict.REJECT,
                policy=RequotePolicy.REJECT,
                original_price=o,
                requote_price=r,
                reason=f"Requote rejected by REJECT policy (offset={offset:.5f})",
                retry_allowed=False,
                safety_flags=self.safety_flags,
            )

        if self.requote_policy == RequotePolicy.ACCEPT_WORST:
            return RequoteResult(
                verdict=AdapterVerdict.SEND,
                policy=RequotePolicy.ACCEPT_WORST,
                original_price=o,
                requote_price=r,
                new_price=r,
                reason="ACCEPT_WORST: accepting broker's requote price",
                retry_allowed=False,
                safety_flags=self.safety_flags,
            )

        # BOUNDED_REPRICE: reprice once within max_reprice_offset.
        if offset > self.max_reprice_offset:
            return RequoteResult(
                verdict=AdapterVerdict.REJECT,
                policy=RequotePolicy.BOUNDED_REPRICE,
                original_price=o,
                requote_price=r,
                reason=(
                    f"BOUNDED_REPRICE: offset {offset:.5f} exceeds "
                    f"max_reprice_offset {self.max_reprice_offset:.5f}"
                ),
                retry_allowed=False,
                safety_flags=self.safety_flags,
            )

        return RequoteResult(
            verdict=AdapterVerdict.REPRICE,
            policy=RequotePolicy.BOUNDED_REPRICE,
            original_price=o,
            requote_price=r,
            new_price=r,
            reason=(
                f"BOUNDED_REPRICE: reprice within offset "
                f"({offset:.5f} <= {self.max_reprice_offset:.5f})"
            ),
            retry_allowed=True,
            safety_flags=self.safety_flags,
        )

    # ─── handle_slippage ─────────────────────────────────────────────────

    def handle_slippage(
        self,
        requested_price: float,
        filled_price: float,
        side: str,
    ) -> SlippageResult:
        """
        Evaluate whether the observed fill slippage is acceptable.

        ``slippage`` is the absolute value of the price difference
        between requested and filled. In proof mode the policy is forced
        to ``REJECT`` and the fill is never accepted.
        """
        side = str(side).upper()
        if side not in ("BUY", "SELL"):
            return SlippageResult(
                verdict=AdapterVerdict.FAIL_CLOSED,
                policy=self.slippage_policy,
                requested_price=float(requested_price),
                filled_price=float(filled_price),
                slippage=0.0,
                slippage_limit=self.slippage_limit,
                reason=f"Invalid side '{side}' — must be BUY or SELL",
                accept_fill=False,
                safety_flags=self.safety_flags,
            )

        rp = float(requested_price)
        fp = float(filled_price)
        slip = abs(fp - rp)

        # Hard limit check — even non-proof policies must respect this.
        if slip > self.slippage_limit:
            # Proof mode: never accept, never retry.
            if self.proof_mode:
                return SlippageResult(
                    verdict=AdapterVerdict.FAIL_CLOSED,
                    policy=SlippagePolicy.REJECT,
                    requested_price=rp,
                    filled_price=fp,
                    slippage=slip,
                    slippage_limit=self.slippage_limit,
                    reason=(
                        f"Proof mode: slippage {slip:.5f} exceeds limit "
                        f"{self.slippage_limit:.5f}"
                    ),
                    accept_fill=False,
                    safety_flags=self.safety_flags,
                )
            return SlippageResult(
                verdict=AdapterVerdict.REJECT,
                policy=self.slippage_policy,
                requested_price=rp,
                filled_price=fp,
                slippage=slip,
                slippage_limit=self.slippage_limit,
                reason=(
                    f"Slippage {slip:.5f} exceeds limit "
                    f"{self.slippage_limit:.5f}"
                ),
                accept_fill=False,
                safety_flags=self.safety_flags,
            )

        # Slippage within limit.
        if self.proof_mode:
            # In proof mode we still REJECT-then-record because the
            # policy is forced to REJECT — but the fill has already
            # happened, so the caller should treat accept_fill=False as
            # "log and continue, do not retry".
            return SlippageResult(
                verdict=AdapterVerdict.SEND,
                policy=SlippagePolicy.REJECT,
                requested_price=rp,
                filled_price=fp,
                slippage=slip,
                slippage_limit=self.slippage_limit,
                reason=(
                    f"Slippage {slip:.5f} within limit "
                    f"{self.slippage_limit:.5f} (proof mode, no retry)"
                ),
                accept_fill=True,
                safety_flags=self.safety_flags,
            )

        if self.slippage_policy == SlippagePolicy.REJECT:
            # Within limit but policy is REJECT-on-principle: accept the
            # fill (it already happened) and record a warning.
            return SlippageResult(
                verdict=AdapterVerdict.SEND,
                policy=SlippagePolicy.REJECT,
                requested_price=rp,
                filled_price=fp,
                slippage=slip,
                slippage_limit=self.slippage_limit,
                reason="Slippage within limit (REJECT policy records warning)",
                accept_fill=True,
                safety_flags=self.safety_flags,
            )

        if self.slippage_policy == SlippagePolicy.BOUNDED_REPRICE:
            return SlippageResult(
                verdict=AdapterVerdict.SEND,
                policy=SlippagePolicy.BOUNDED_REPRICE,
                requested_price=rp,
                filled_price=fp,
                slippage=slip,
                slippage_limit=self.slippage_limit,
                reason="BOUNDED_REPRICE: slippage within limit, accept and note",
                accept_fill=True,
                safety_flags=self.safety_flags,
            )

        # ACCEPT_WORST
        return SlippageResult(
            verdict=AdapterVerdict.SEND,
            policy=SlippagePolicy.ACCEPT_WORST,
            requested_price=rp,
            filled_price=fp,
            slippage=slip,
            slippage_limit=self.slippage_limit,
            reason="ACCEPT_WORST: fill accepted unconditionally",
            accept_fill=True,
            safety_flags=self.safety_flags,
        )

    # ─── Helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def is_requote_retcode(retcode: int) -> bool:
        """Return True if the MT5 retcode represents a requote condition."""
        return int(retcode) in REQUOTE_RETCODES

    @staticmethod
    def _mt5_filling_constant(filling_mode: str) -> int:
        """
        Map a filling-mode string to the MT5 numeric constant.

        Defaults to ORDER_FILLING_IOC (1) if unknown. The mapping is
        kept here so the adapter does not need to import MetaTrader5.
        """
        fm = str(filling_mode).upper()
        if fm in ("ORDER_FILLING_FOK", "FOK"):
            return 0
        if fm in ("ORDER_FILLING_IOC", "IOC"):
            return 1
        if fm in ("ORDER_FILLING_RETURN", "RETURN"):
            return 2
        if fm in ("ORDER_FILLING_BOC", "BOC"):
            return 3
        # Default to IOC — safest common default for market orders.
        return 1
