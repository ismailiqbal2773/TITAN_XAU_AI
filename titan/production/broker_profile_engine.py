"""
TITAN XAU AI — Broker Profile Engine (Sprint 9.9.3.45.8.4)
============================================================

Loads broker profiles from ``config/broker_profiles.yaml`` and exposes a
deterministic, broker-agnostic API for symbol spec detection, spread
validation, and slippage validation.

Responsibilities:
  1. Parse ``config/broker_profiles.yaml`` into typed ``BrokerProfile`` and
     ``SymbolSpec`` dataclasses.
  2. Resolve broker-specific symbol naming (prefix/suffix support, e.g.
     ``XAUUSD``, ``XAUUSD.c``, ``XAUUSD.m``, ``XAUUSD.r``).
  3. Provide ``validate_spread()`` and ``validate_slippage()`` gate methods
     used by the broker execution adapter before any order is sent.
  4. Surface contract_size, tick_size, tick_value, min_lot, max_lot,
     lot_step, stop_level, freeze_level, filling_mode for downstream
     lot-sizing and execution modules.

Safety invariants (HARD — enforced for every profile):
  - no_martingale: true
  - no_grid: true
  - no_averaging: true
  - no_loss_based_lot_multiplier: true

This module is pure Python. It NEVER imports MetaTrader5, NEVER calls
``mt5.order_send``, and NEVER submits orders. It only reads configuration
and provides validated broker/symbol facts to the rest of the stack.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional, Any

import yaml

logger = logging.getLogger(__name__)


# ─── Safety flags mirrored across the production stack ──────────────────────
SAFETY_FLAGS: dict[str, bool] = {
    "no_martingale": True,
    "no_grid": True,
    "no_averaging": True,
    "no_loss_based_lot_multiplier": True,
}


# ─── Canonical symbol base names ────────────────────────────────────────────
# Brokers attach arbitrary prefixes (e.g. "m.", "EUR-") and suffixes
# (e.g. ".c", ".m", ".r", "#") to canonical symbols. The engine strips
# these so the rest of the stack works with a single canonical base.
CANONICAL_SYMBOLS: tuple[str, ...] = (
    "XAUUSD",
    "XAGUSD",
    "EURUSD",
    "GBPUSD",
    "USDJPY",
    "USDCHF",
    "AUDUSD",
    "USDCAD",
    "NZDUSD",
)

# Common broker suffixes/prefixes observed in production.
# Order matters: longer suffixes first so we don't strip a leading "."
# from ".c" before matching ".raw".
_SYMBOL_SUFFIX_PATTERN = re.compile(
    r"(?i)\.(?:raw|ecn|r|m|c|s|pro|standard|std|#)$"
)
_SYMBOL_PREFIX_PATTERN = re.compile(
    r"(?i)^(?:m\.|r\.|c\.|s\.|raw\.|ecn\.|pro\.|std\.)"
)


# ─── Dataclasses ─────────────────────────────────────────────────────────────
@dataclass
class SymbolSpec:
    """
    Fully resolved symbol specification for a single broker.

    All fields are in account/quote currency as appropriate.
    ``filling_mode`` is the broker's preferred MT5 filling mode constant
    name (e.g. ``ORDER_FILLING_IOC``).
    """
    symbol: str                       # canonical base symbol, e.g. "XAUUSD"
    broker_symbol: str                # actual broker symbol w/ suffix, e.g. "XAUUSD.c"
    broker_id: str                    # parent broker profile id
    contract_size: float = 100.0
    tick_size: float = 0.01
    tick_value: float = 1.0
    min_lot: float = 0.01
    max_lot: float = 100.0
    lot_step: float = 0.01
    stop_level_points: int = 0
    freeze_level_points: int = 0
    filling_mode: str = "ORDER_FILLING_IOC"
    digits: int = 2
    point: float = 0.01

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class BrokerProfile:
    """
    Single broker profile loaded from YAML.

    Stores both broker-level fields and per-symbol overrides for XAUUSD
    (the primary TITAN symbol). Per-symbol overrides are merged into the
    SymbolSpec by ``get_symbol_spec()``.
    """
    broker_id: str
    name: str
    server: str
    account_type: str = "demo"
    typical_spread_xauusd: float = 0.35
    max_spread_xauusd: float = 0.50
    commission_per_lot_round_turn: float = 0.0
    typical_slippage_xauusd: float = 0.02
    max_slippage_xauusd: float = 0.10
    swap_long_xauusd_per_lot_per_night: float = -3.50
    swap_short_xauusd_per_lot_per_night: float = -1.20
    contract_size_xauusd: float = 100.0
    stops_level_points_xauusd: int = 50
    freeze_level_points_xauusd: int = 0
    filling_mode: str = "ORDER_FILLING_IOC"
    margin_currency: str = "USD"
    min_lot: float = 0.01
    max_lot: float = 100.0
    lot_step: float = 0.01
    leverage_options: list[int] = field(default_factory=list)
    # Symbol suffix map: canonical → broker-specific suffix (".c", ".m", ...)
    symbol_suffixes: dict[str, str] = field(default_factory=dict)
    # Hard safety caps — must always be present.
    no_martingale: bool = True
    no_grid: bool = True
    no_averaging: bool = True
    no_loss_based_lot_multiplier: bool = True

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def safety_flags(self) -> dict[str, bool]:
        return {
            "no_martingale": self.no_martingale,
            "no_grid": self.no_grid,
            "no_averaging": self.no_averaging,
            "no_loss_based_lot_multiplier": self.no_loss_based_lot_multiplier,
        }


# ─── Validation result ──────────────────────────────────────────────────────
@dataclass
class ValidationResult:
    """Result of a spread or slippage validation gate."""
    ok: bool
    actual: float
    limit: float
    reason: str = ""
    verdict: str = ""                  # PASS | REJECT | BLOCK
    timestamp_utc: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp_utc:
            from datetime import datetime, timezone
            self.timestamp_utc = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return asdict(self)


# ─── Engine ─────────────────────────────────────────────────────────────────
class BrokerProfileEngine:
    """
    Loads broker profiles from YAML and resolves symbol specs.

    The engine is broker-agnostic — it does not query MT5 directly. It
    trusts the YAML configuration file as the single source of truth for
    broker execution facts. Live MT5 detection is the responsibility of
    ``BrokerIntelligenceLayer`` and ``MT5ExecutionAdapter``.

    Usage:
        engine = BrokerProfileEngine("config/broker_profiles.yaml")
        profile = engine.get_broker_profile("metaquotes_demo")
        spec = engine.get_symbol_spec("XAUUSD", "metaquotes_demo")
        spread_ok = engine.validate_spread("metaquotes_demo", spread=0.32)
        slip_ok = engine.validate_slippage("metaquotes_demo", slippage=0.05)
    """

    # ─── Construction ─────────────────────────────────────────────────────
    def __init__(
        self,
        profiles_path: str | Path,
        journal: Optional[Any] = None,
    ):
        self.profiles_path = Path(profiles_path)
        self.journal = journal
        self._raw: dict[str, dict] = {}
        self._profiles: dict[str, BrokerProfile] = {}
        self._load_yaml()

    # ─── YAML loading ────────────────────────────────────────────────────
    def _load_yaml(self) -> None:
        if not self.profiles_path.exists():
            raise FileNotFoundError(
                f"Broker profiles YAML not found: {self.profiles_path}"
            )
        # Sprint 9.0.1: explicit UTF-8 — Windows defaults to cp1252 which
        # raises UnicodeDecodeError on non-ASCII chars in profile notes.
        with open(self.profiles_path, "r", encoding="utf-8") as f:
            doc = yaml.safe_load(f) or {}
        raw_brokers = doc.get("brokers", {}) or {}
        for broker_id, raw in raw_brokers.items():
            if not isinstance(raw, dict):
                logger.warning(
                    "Skipping broker entry '%s': not a mapping", broker_id
                )
                continue
            self._raw[broker_id] = raw
            self._profiles[broker_id] = self._build_profile(broker_id, raw)
        logger.info(
            "BrokerProfileEngine loaded %d broker profiles from %s",
            len(self._profiles),
            self.profiles_path,
        )

    def _build_profile(
        self,
        broker_id: str,
        raw: dict,
    ) -> BrokerProfile:
        """Construct a BrokerProfile from raw YAML dict."""
        # Defensive: enforce safety flags even if YAML omits them.
        profile = BrokerProfile(
            broker_id=broker_id,
            name=raw.get("name", broker_id),
            server=raw.get("server", broker_id),
            account_type=str(raw.get("account_type", "demo")).lower(),
            typical_spread_xauusd=float(raw.get("typical_spread_xauusd", 0.35)),
            max_spread_xauusd=float(raw.get("max_spread_xauusd", 0.50)),
            commission_per_lot_round_turn=float(
                raw.get("commission_per_lot_round_turn", 0.0)
            ),
            typical_slippage_xauusd=float(raw.get("typical_slippage_xauusd", 0.02)),
            max_slippage_xauusd=float(raw.get("max_slippage_xauusd", 0.10)),
            swap_long_xauusd_per_lot_per_night=float(
                raw.get("swap_long_xauusd_per_lot_per_night", -3.50)
            ),
            swap_short_xauusd_per_lot_per_night=float(
                raw.get("swap_short_xauusd_per_lot_per_night", -1.20)
            ),
            contract_size_xauusd=float(raw.get("contract_size_xauusd", 100.0)),
            stops_level_points_xauusd=int(raw.get("stops_level_points_xauusd", 50)),
            freeze_level_points_xauusd=int(raw.get("freeze_level_points_xauusd", 0)),
            filling_mode=str(raw.get("filling_mode", "ORDER_FILLING_IOC")),
            margin_currency=str(raw.get("margin_currency", "USD")),
            min_lot=float(raw.get("min_lot", 0.01)),
            max_lot=float(raw.get("max_lot", 100.0)),
            lot_step=float(raw.get("lot_step", 0.01)),
            leverage_options=list(raw.get("leverage_options", []) or []),
            symbol_suffixes=dict(raw.get("symbol_suffixes", {}) or {}),
            no_martingale=bool(raw.get("no_martingale", True)),
            no_grid=bool(raw.get("no_grid", True)),
            no_averaging=bool(raw.get("no_averaging", True)),
            no_loss_based_lot_multiplier=bool(
                raw.get("no_loss_based_lot_multiplier", True)
            ),
        )
        # Enforce hard safety invariants regardless of YAML content.
        # If YAML ever disables one of these, we override back to True
        # and log a warning so the operator sees it.
        for flag in SAFETY_FLAGS:
            if not getattr(profile, flag):
                logger.warning(
                    "Broker '%s' YAML set %s=False — overriding to True "
                    "(safety invariant)", broker_id, flag
                )
                setattr(profile, flag, True)
        return profile

    # ─── Public API ──────────────────────────────────────────────────────

    def list_brokers(self) -> list[str]:
        """Return all available broker profile ids."""
        return sorted(self._profiles.keys())

    def has_broker(self, broker_id: str) -> bool:
        return broker_id in self._profiles

    def get_broker_profile(self, broker_id: str) -> BrokerProfile:
        """
        Return the BrokerProfile for ``broker_id``.

        Raises:
            KeyError: if the broker is not registered in the YAML.
        """
        if broker_id not in self._profiles:
            raise KeyError(
                f"Broker profile '{broker_id}' not found in "
                f"{self.profiles_path}. Available: {self.list_brokers()}"
            )
        return self._profiles[broker_id]

    def get_symbol_spec(
        self,
        symbol: str,
        broker: str,
    ) -> SymbolSpec:
        """
        Resolve a SymbolSpec for the given canonical symbol and broker.

        The returned spec contains both the canonical symbol name and the
        broker-specific symbol (with prefix/suffix applied).

        Raises:
            KeyError: if broker is unknown.
            ValueError: if symbol cannot be canonicalized.
        """
        profile = self.get_broker_profile(broker)
        canonical = self.canonicalize_symbol(symbol)
        broker_symbol = self._resolve_broker_symbol(canonical, profile)

        # XAUUSD is the primary TITAN symbol — its spec is fully populated
        # in the YAML. For other symbols we fall back to broker defaults.
        if canonical.upper() == "XAUUSD":
            spec = SymbolSpec(
                symbol=canonical,
                broker_symbol=broker_symbol,
                broker_id=profile.broker_id,
                contract_size=profile.contract_size_xauusd,
                tick_size=0.01,
                tick_value=1.0,
                min_lot=profile.min_lot,
                max_lot=profile.max_lot,
                lot_step=profile.lot_step,
                stop_level_points=profile.stops_level_points_xauusd,
                freeze_level_points=profile.freeze_level_points_xauusd,
                filling_mode=profile.filling_mode,
                digits=2,
                point=0.01,
            )
        else:
            spec = SymbolSpec(
                symbol=canonical,
                broker_symbol=broker_symbol,
                broker_id=profile.broker_id,
                contract_size=profile.contract_size_xauusd,
                tick_size=0.01,
                tick_value=1.0,
                min_lot=profile.min_lot,
                max_lot=profile.max_lot,
                lot_step=profile.lot_step,
                stop_level_points=profile.stops_level_points_xauusd,
                freeze_level_points=profile.freeze_level_points_xauusd,
                filling_mode=profile.filling_mode,
                digits=2,
                point=0.01,
            )
        return spec

    def validate_spread(
        self,
        broker: str,
        spread: float,
        symbol: str = "XAUUSD",
    ) -> ValidationResult:
        """
        Validate that the observed spread is within broker limits.

        The limit is taken from the broker profile's ``max_spread_xauusd``
        for XAUUSD. Returns a ``ValidationResult`` with ``ok=True`` if
        the spread is within tolerance, otherwise ``ok=False`` with a
        BLOCK verdict.
        """
        profile = self.get_broker_profile(broker)
        canonical = self.canonicalize_symbol(symbol)
        if canonical.upper() == "XAUUSD":
            limit = profile.max_spread_xauusd
            typical = profile.typical_spread_xauusd
        else:
            # Fall back to XAUUSD limit for non-XAUUSD symbols.
            limit = profile.max_spread_xauusd
            typical = profile.typical_spread_xauusd

        actual = float(spread)
        if actual < 0.0:
            return ValidationResult(
                ok=False,
                actual=actual,
                limit=limit,
                reason=f"Negative spread reported ({actual})",
                verdict="BLOCK",
            )
        if actual > limit:
            return ValidationResult(
                ok=False,
                actual=actual,
                limit=limit,
                reason=(
                    f"Spread {actual} exceeds max_spread {limit} "
                    f"(typical={typical}) for broker '{broker}'"
                ),
                verdict="BLOCK",
            )
        return ValidationResult(
            ok=True,
            actual=actual,
            limit=limit,
            reason=(
                f"Spread {actual} within max_spread {limit} "
                f"(typical={typical}) for broker '{broker}'"
            ),
            verdict="PASS",
        )

    def validate_slippage(
        self,
        broker: str,
        slippage: float,
        symbol: str = "XAUUSD",
    ) -> ValidationResult:
        """
        Validate that the observed slippage is within broker limits.

        The limit is taken from the broker profile's ``max_slippage_xauusd``
        for XAUUSD. ``slippage`` must be a non-negative absolute value
        (sign of trade-side slippage is normalized by the caller).
        """
        profile = self.get_broker_profile(broker)
        canonical = self.canonicalize_symbol(symbol)
        if canonical.upper() == "XAUUSD":
            limit = profile.max_slippage_xauusd
            typical = profile.typical_slippage_xauusd
        else:
            limit = profile.max_slippage_xauusd
            typical = profile.typical_slippage_xauusd

        actual = abs(float(slippage))
        if actual > limit:
            return ValidationResult(
                ok=False,
                actual=actual,
                limit=limit,
                reason=(
                    f"Slippage {actual} exceeds max_slippage {limit} "
                    f"(typical={typical}) for broker '{broker}'"
                ),
                verdict="REJECT",
            )
        return ValidationResult(
            ok=True,
            actual=actual,
            limit=limit,
            reason=(
                f"Slippage {actual} within max_slippage {limit} "
                f"(typical={typical}) for broker '{broker}'"
            ),
            verdict="PASS",
        )

    # ─── Symbol naming helpers ───────────────────────────────────────────

    @staticmethod
    def canonicalize_symbol(symbol: str) -> str:
        """
        Strip broker prefix/suffix from a symbol name.

        Examples:
          "XAUUSD"      → "XAUUSD"
          "XAUUSD.c"    → "XAUUSD"
          "XAUUSD.m"    → "XAUUSD"
          "m.XAUUSD"    → "XAUUSD"
          "xauusd.r"    → "XAUUSD"
        """
        if not symbol:
            raise ValueError("symbol cannot be empty")
        s = symbol.strip()
        # Strip prefix first, then suffix.
        s = _SYMBOL_PREFIX_PATTERN.sub("", s)
        s = _SYMBOL_SUFFIX_PATTERN.sub("", s)
        return s.upper()

    def _resolve_broker_symbol(
        self,
        canonical: str,
        profile: BrokerProfile,
    ) -> str:
        """
        Apply broker-specific suffix/prefix to a canonical symbol.

        If the broker profile declares an explicit suffix for this symbol
        (e.g. ``XAUUSD: ".c"``), apply it. Otherwise return the canonical
        name unchanged.
        """
        suffix = profile.symbol_suffixes.get(canonical.upper(), "")
        return f"{canonical}{suffix}" if suffix else canonical

    def resolve_broker_symbol(
        self,
        symbol: str,
        broker: str,
    ) -> str:
        """
        Public helper: given any (possibly already-suffixed) symbol and
        a broker id, return the broker-specific symbol name.

        This canonicalizes first, then re-applies the broker suffix so
        callers can pass either form interchangeably.
        """
        profile = self.get_broker_profile(broker)
        canonical = self.canonicalize_symbol(symbol)
        return self._resolve_broker_symbol(canonical, profile)

    # ─── Introspection ───────────────────────────────────────────────────

    def all_profiles(self) -> dict[str, BrokerProfile]:
        """Return a shallow copy of all broker profiles."""
        return dict(self._profiles)

    def safety_audit(self) -> dict[str, dict[str, bool]]:
        """
        Return a per-broker safety flag audit.

        Every broker profile must have all four safety flags set to True.
        Any False indicates either a YAML error or an upstream override.
        """
        return {
            broker_id: profile.safety_flags
            for broker_id, profile in self._profiles.items()
        }
