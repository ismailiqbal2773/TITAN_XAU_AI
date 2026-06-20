"""
TITAN XAU AI — Broker Compatibility Engine (Module 1)
Production implementation: runtime broker detection, symbol resolution,
6-broker profile system, 9 properties per broker.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import MetaTrader5 as mt5
import yaml

logger = logging.getLogger(__name__)


class BrokerId(str, Enum):
    EXNESS = "exness"
    ICMARKETS = "icmarkets"
    PEPPERSTONE = "pepperstone"
    TICKMILL = "tickmill"
    FP_MARKETS = "fp_markets"
    FUSION_MARKETS = "fusion_markets"
    UNKNOWN = "unknown"


class MarginMode(str, Enum):
    RETAIL = "retail"
    EXCHANGE = "exchange"
    PORTFOLIO = "portfolio"


@dataclass(frozen=True)
class BrokerProfile:
    """9 broker properties — resolved at runtime."""
    broker_id: BrokerId
    broker_name: str
    server_name: str
    symbol_suffix: str
    contract_size: float       # oz for XAUUSD (100)
    min_lot: float
    lot_step: float
    leverage: int
    margin_mode: MarginMode
    timezone: str
    # Runtime-resolved
    account_balance: float = 0.0
    account_currency: str = "USD"
    account_leverage_actual: int = 0
    company_name: str = ""


@dataclass
class SymbolInfo:
    """Resolved symbol information from MT5."""
    name: str
    digits: int
    point: float
    spread: int
    contract_size: float
    min_volume: float
    max_volume: float
    volume_step: float
    trade_mode: int
    bid: float
    ask: float
    last_tick_time: float


class BrokerCompatibilityEngine:
    """
    Runtime broker detection engine.
    Connects to MT5, identifies broker, loads profile,
    resolves XAUUSD symbol with correct suffix.
    """

    # Predefined profiles loaded from config
    PROFILES: dict[str, dict] = {}

    def __init__(self, config_path: str = "config/titan.yaml"):
        self._config = self._load_config(config_path)
        self._profile: Optional[BrokerProfile] = None
        self._symbol_info: Optional[SymbolInfo] = None
        self._mt5_initialized = False
        self._detection_time_ms: float = 0.0

    def _load_config(self, path: str) -> dict:
        with open(path, "r") as f:
            return yaml.safe_load(f)

    def initialize(self) -> bool:
        """Initialize MT5 terminal connection."""
        mt5_cfg = self._config.get("mt5", {})

        terminal_path = mt5_cfg.get("terminal_path", "")
        login = mt5_cfg.get("login", 0)
        password = mt5_cfg.get("password", "")
        server = mt5_cfg.get("server", "")
        timeout = mt5_cfg.get("timeout", 60000)

        if terminal_path:
            if not mt5.initialize(
                path=terminal_path,
                login=login,
                password=password,
                server=server,
                timeout=timeout,
            ):
                logger.error(f"MT5 initialize failed: {mt5.last_error()}")
                return False
        else:
            if not mt5.initialize(timeout=timeout):
                logger.error(f"MT5 initialize failed: {mt5.last_error()}")
                return False

        self._mt5_initialized = True
        logger.info("MT5 terminal initialized successfully")
        return True

    def detect_broker(self) -> BrokerProfile:
        """
        Detect broker at runtime from MT5 terminal info.
        Must complete within 2 seconds (BRO-001 requirement).
        """
        if not self._mt5_initialized:
            raise RuntimeError("MT5 not initialized. Call initialize() first.")

        start = time.perf_counter()

        terminal_info = mt5.terminal_info()
        account_info = mt5.account_info()

        if terminal_info is None:
            raise RuntimeError(f"Failed to get terminal info: {mt5.last_error()}")

        company_name = terminal_info.company
        server_name = terminal_info.name if hasattr(terminal_info, "name") else ""

        broker_id = self._match_broker(company_name, server_name)

        # Load predefined profile
        broker_cfg = self._config.get("brokers", {})
        profile_data = broker_cfg.get(broker_id.value, broker_cfg.get("icmarkets", {}))

        elapsed_ms = (time.perf_counter() - start) * 1000
        self._detection_time_ms = elapsed_ms

        self._profile = BrokerProfile(
            broker_id=broker_id,
            broker_name=company_name,
            server_name=server_name,
            symbol_suffix=profile_data.get("symbol_suffix", ""),
            contract_size=profile_data.get("contract_size", 100),
            min_lot=profile_data.get("min_lot", 0.01),
            lot_step=profile_data.get("lot_step", 0.01),
            leverage=profile_data.get("leverage", 500),
            margin_mode=MarginMode(profile_data.get("margin_mode", "retail")),
            timezone=profile_data.get("timezone", "EET"),
            account_balance=account_info.balance if account_info else 0.0,
            account_currency=account_info.currency if account_info else "USD",
            account_leverage_actual=account_info.leverage if account_info else 0,
            company_name=company_name,
        )

        logger.info(
            f"Broker detected: {broker_id.value} ({company_name}) "
            f"in {elapsed_ms:.1f}ms"
        )
        return self._profile

    def _match_broker(self, company_name: str, server_name: str) -> BrokerId:
        """Match broker from company/server name."""
        combined = f"{company_name} {server_name}".lower()

        if "exness" in combined:
            return BrokerId.EXNESS
        elif "ic markets" in combined or "icmarkets" in combined:
            return BrokerId.ICMARKETS
        elif "pepperstone" in combined:
            return BrokerId.PEPPERSTONE
        elif "tickmill" in combined:
            return BrokerId.TICKMILL
        elif "fp markets" in combined or "fp_markets" in combined:
            return BrokerId.FP_MARKETS
        elif "fusion" in combined:
            return BrokerId.FUSION_MARKETS
        else:
            logger.warning(f"Unknown broker: {company_name} / {server_name}")
            return BrokerId.UNKNOWN

    def resolve_symbol(self, base_symbol: str = "XAUUSD") -> SymbolInfo:
        """
        Resolve the correct symbol name for this broker.
        Tries base_symbol + suffix variants.
        """
        if self._profile is None:
            raise RuntimeError("Broker not detected. Call detect_broker() first.")

        symbols_config = self._config.get("symbols", {})
        alternate_names = symbols_config.get("alternate_names", ["XAUUSD"])

        # Build candidate list: base + suffix, then alternates
        candidates = []
        suffix = self._profile.symbol_suffix
        if suffix:
            candidates.append(f"{base_symbol}{suffix}")
        candidates.append(base_symbol)
        candidates.extend(alternate_names)
        # Add suffix to alternates too
        if suffix:
            for alt in alternate_names:
                candidates.append(f"{alt}{suffix}")

        # Deduplicate while preserving order
        seen = set()
        unique_candidates = []
        for c in candidates:
            if c not in seen:
                seen.add(c)
                unique_candidates.append(c)

        for candidate in unique_candidates:
            info = mt5.symbol_info(candidate)
            if info is not None:
                # Ensure symbol is visible in Market Watch
                if not info.visible:
                    mt5.symbol_select(candidate, True)
                    info = mt5.symbol_info(candidate)

                tick = mt5.symbol_info_tick(candidate)

                self._symbol_info = SymbolInfo(
                    name=candidate,
                    digits=info.digits,
                    point=info.point,
                    spread=info.spread,
                    contract_size=info.trade_contract_size,
                    min_volume=info.volume_min,
                    max_volume=info.volume_max,
                    volume_step=info.volume_step,
                    trade_mode=info.trade_mode,
                    bid=tick.bid if tick else 0.0,
                    ask=tick.ask if tick else 0.0,
                    last_tick_time=tick.time if tick else 0.0,
                )
                logger.info(f"Symbol resolved: {candidate}")
                return self._symbol_info

        raise RuntimeError(
            f"Could not resolve symbol. Tried: {unique_candidates}"
        )

    @property
    def profile(self) -> Optional[BrokerProfile]:
        return self._profile

    @property
    def symbol_info(self) -> Optional[SymbolInfo]:
        return self._symbol_info

    @property
    def detection_time_ms(self) -> float:
        return self._detection_time_ms

    def shutdown(self) -> None:
        """Shutdown MT5 connection."""
        if self._mt5_initialized:
            mt5.shutdown()
            self._mt5_initialized = False
            logger.info("MT5 terminal shutdown")

    def get_all_symbols(self, pattern: str = "XAU") -> list[str]:
        """Get all symbols matching pattern (for multi-symbol support)."""
        if not self._mt5_initialized:
            raise RuntimeError("MT5 not initialized")
        all_symbols = mt5.symbols_get(pattern)
        if all_symbols is None:
            return []
        return [s.name for s in all_symbols]

    def validate_profile(self) -> list[str]:
        """
        Validate that all 9 broker properties are populated.
        Returns list of missing properties (empty = all present).
        """
        if self._profile is None:
            return ["profile not loaded"]

        missing = []
        checks = [
            ("broker_name", self._profile.broker_name),
            ("server_name", self._profile.server_name),
            ("symbol_suffix", self._profile.symbol_suffix if self._profile.symbol_suffix is not None else ""),
            ("contract_size", self._profile.contract_size if self._profile.contract_size > 0 else None),
            ("min_lot", self._profile.min_lot if self._profile.min_lot > 0 else None),
            ("lot_step", self._profile.lot_step if self._profile.lot_step > 0 else None),
            ("leverage", self._profile.leverage if self._profile.leverage > 0 else None),
            ("margin_mode", self._profile.margin_mode.value),
            ("timezone", self._profile.timezone),
        ]
        for name, value in checks:
            if value is None or value == "":
                missing.append(name)

        if self._symbol_info is None:
            missing.append("symbol_info not resolved")
        elif self._symbol_info.contract_size != self._profile.contract_size:
            logger.warning(
                f"Contract size mismatch: profile={self._profile.contract_size}, "
                f"symbol={self._symbol_info.contract_size}"
            )

        return missing
