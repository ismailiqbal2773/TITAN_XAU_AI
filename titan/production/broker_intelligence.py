"""
TITAN XAU AI — Broker Intelligence Layer (Sprint 9.5)
======================================================

Auto-detects 20+ broker properties from MT5 terminal:
  - Broker name, server, account type (demo/live)
  - Prop/retail, cent/standard, ECN/RAW/standard
  - Symbol naming, digits, point value, tick size/value
  - Contract size, min/max lot, lot step
  - Freeze level, stop level
  - Margin mode, hedging/netting
  - Execution mode, filling mode, trading hours

All detection is FAIL-CLOSED: if MT5 unavailable or detection fails,
returns None and TITAN continues with default behavior.

Usage:
    layer = BrokerIntelligenceLayer(journal=journal)
    info = layer.detect()  # returns BrokerInfo or None
    if info:
        print(info.broker_name, info.account_type, info.spread_points)
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field, asdict
from typing import Optional

from titan.production.trade_journal import TradeJournal, EventType

logger = logging.getLogger(__name__)


# ─── Symbol naming patterns for common brokers ───────────────────────────────
SYMBOL_PATTERNS = {
    "exness": ["XAUUSD", "XAUUSDm", "XAUUSD.r", "XAUUSD.s"],
    "icmarkets": ["XAUUSD", "XAUUSD.r", "XAUUSD.raw"],
    "fbs": ["XAUUSD", "XAUUSD.m"],
    "fundednext": ["XAUUSD", "XAUUSD.c"],
    "ftmo": ["XAUUSD", "XAUUSD.r"],
    "the5ers": ["XAUUSD", "XAUUSD.r"],
    "myfundedfx": ["XAUUSD"],
}


# ─── BrokerInfo dataclass ────────────────────────────────────────────────────
@dataclass
class BrokerInfo:
    """Snapshot of broker properties detected from MT5."""
    # Identification
    broker_name: str = ""
    server: str = ""
    company: str = ""
    login: int = 0
    # Account type
    account_type: str = ""           # "demo" | "live"
    account_category: str = ""       # "prop" | "retail"
    account_size: str = ""           # "cent" | "standard"
    account_spread_type: str = ""    # "ecn" | "raw" | "standard"
    # Symbol properties
    symbol_name: str = "XAUUSD"
    symbol_detected: str = ""        # actual symbol found in Market Watch
    digits: int = 2
    point: float = 0.01
    tick_size: float = 0.01
    tick_value: float = 1.0
    contract_size: float = 100.0
    min_lot: float = 0.01
    max_lot: float = 100.0
    lot_step: float = 0.01
    freeze_level: int = 0
    stop_level: int = 0
    # Margin / execution
    margin_mode: str = ""            # "RETAIL_NETTING" | "RETAIL_HEDGING" | etc.
    hedging: bool = False
    execution_mode: str = ""         # "EXCHANGE" | "INSTANT" | "REQUEST" | "MARKET"
    filling_mode: str = ""           # "IOC" | "FOK" | "RETURN"
    # Trading hours (simplified — XAUUSD is near-24h)
    trading_hours: str = "near-24h"
    # Detection metadata
    detected_at: float = field(default_factory=time.time)
    detection_method: str = ""       # "mt5" | "stub" | "manual"

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def is_demo(self) -> bool:
        return self.account_type.lower() == "demo"

    @property
    def is_live(self) -> bool:
        return self.account_type.lower() == "live"

    @property
    def is_prop(self) -> bool:
        return self.account_category.lower() == "prop"

    @property
    def is_retail(self) -> bool:
        return self.account_category.lower() == "retail"

    @property
    def is_ecn(self) -> bool:
        return self.account_spread_type.lower() in ("ecn", "raw")


# ─── BrokerIntelligenceLayer ─────────────────────────────────────────────────
class BrokerIntelligenceLayer:
    """
    Auto-detects broker properties from MT5 terminal.

    Fail-closed: if MT5 unavailable, returns None and journals nothing.
    All detections are journaled as EventType.BROKER_DETECTED.
    """

    def __init__(self, journal: Optional[TradeJournal] = None):
        self.journal = journal
        self._last_info: Optional[BrokerInfo] = None
        self._detection_count: int = 0

    # ─── Public API ───────────────────────────────────────────────────────

    def detect(self, symbol: str = "XAUUSD") -> Optional[BrokerInfo]:
        """
        Detect broker properties from MT5.

        Returns BrokerInfo on success, None on failure (MT5 unavailable).
        Journals BROKER_DETECTED event on success.
        """
        try:
            import MetaTrader5 as mt5
        except ImportError:
            logger.debug("MetaTrader5 not available — broker detection skipped")
            return None

        if not mt5.initialize():
            logger.warning(f"mt5.initialize() failed: {mt5.last_error()}")
            return None

        try:
            info = self._detect_from_mt5(mt5, symbol)
            if info is not None:
                self._last_info = info
                self._detection_count += 1
                self._journal_event(EventType.BROKER_DETECTED, info.to_dict())
                logger.info(
                    f"Broker detected: {info.broker_name} "
                    f"({info.account_type}, {info.account_category}, "
                    f"{info.account_spread_type})"
                )
            return info
        except Exception as e:
            logger.error(f"Broker detection failed: {e}")
            return None
        finally:
            mt5.shutdown()

    def detect_from_account_info(self, account_info, symbol_info=None) -> Optional[BrokerInfo]:
        """
        Detect broker from pre-fetched MT5 account_info + symbol_info objects.
        Useful for testing + when MT5 connection is already established.
        """
        if account_info is None:
            return None
        try:
            info = self._build_info(account_info, symbol_info)
            self._last_info = info
            self._detection_count += 1
            self._journal_event(EventType.BROKER_DETECTED, info.to_dict())
            return info
        except Exception as e:
            logger.error(f"Broker detection from account_info failed: {e}")
            return None

    @property
    def last_info(self) -> Optional[BrokerInfo]:
        return self._last_info

    @property
    def detection_count(self) -> int:
        return self._detection_count

    # ─── Internal: MT5 detection ──────────────────────────────────────────

    def _detect_from_mt5(self, mt5, symbol: str) -> Optional[BrokerInfo]:
        """Detect broker properties from live MT5 connection."""
        acc = mt5.account_info()
        if acc is None:
            logger.warning("mt5.account_info() returned None")
            return None

        # Find symbol (try variations)
        symbol_info = None
        symbol_detected = symbol
        for candidate in self._symbol_candidates(symbol, acc):
            if mt5.symbol_select(candidate, True):
                symbol_info = mt5.symbol_info(candidate)
                if symbol_info is not None:
                    symbol_detected = candidate
                    break

        return self._build_info(acc, symbol_info, symbol_detected)

    def _symbol_candidates(self, requested: str, account_info) -> list[str]:
        """Generate symbol name candidates based on broker."""
        candidates = [requested]
        # Add common suffixes
        for suffix in ["", ".m", ".r", ".s", ".c", ".raw", ".ecn", ".pro"]:
            if suffix:
                candidates.append(f"{requested}{suffix}")
        # Try broker-specific patterns
        company = str(getattr(account_info, "company", "") or "").lower()
        for broker_key, symbols in SYMBOL_PATTERNS.items():
            if broker_key in company:
                candidates.extend(symbols)
                break
        # Deduplicate while preserving order
        seen = set()
        unique = []
        for c in candidates:
            if c not in seen:
                seen.add(c)
                unique.append(c)
        return unique

    def _build_info(self, acc, symbol_info=None, symbol_detected: str = "XAUUSD") -> BrokerInfo:
        """Build BrokerInfo from MT5 account_info + symbol_info."""
        info = BrokerInfo()
        # Account identification
        info.broker_name = str(getattr(acc, "company", "") or "")
        info.server = str(getattr(acc, "server", "") or "")
        info.company = info.broker_name
        info.login = int(getattr(acc, "login", 0) or 0)

        # Account type detection
        trade_mode = getattr(acc, "trade_mode", 0)
        # MT5 trade_mode: 0=DEMO, 1=CONTEST, 2=REAL
        if trade_mode == 0:
            info.account_type = "demo"
        elif trade_mode == 2:
            info.account_type = "live"
        elif trade_mode == 1:
            info.account_type = "contest"
        else:
            info.account_type = "unknown"

        # Account category: prop vs retail
        company_lower = info.broker_name.lower()
        prop_keywords = ["ftmo", "fundednext", "5ers", "myfundedfx", "funding", "prop"]
        info.account_category = (
            "prop" if any(k in company_lower for k in prop_keywords) else "retail"
        )

        # Account size: cent vs standard
        # Heuristic: cent accounts typically have balance > 1M or leverage > 1000
        leverage = getattr(acc, "leverage", 100) or 100
        balance = getattr(acc, "balance", 0) or 0
        if leverage >= 1000 or balance >= 1_000_000:
            info.account_size = "cent"
        else:
            info.account_size = "standard"

        # Spread type: ECN/RAW/standard
        server_lower = info.server.lower()
        if "raw" in server_lower or "ecn" in server_lower:
            info.account_spread_type = "ecn" if "ecn" in server_lower else "raw"
        elif "pro" in server_lower or "zero" in server_lower:
            info.account_spread_type = "raw"
        else:
            info.account_spread_type = "standard"

        # Symbol properties
        info.symbol_name = "XAUUSD"
        info.symbol_detected = symbol_detected
        if symbol_info is not None:
            info.digits = int(getattr(symbol_info, "digits", 2) or 2)
            info.point = float(getattr(symbol_info, "point", 0.01) or 0.01)
            info.spread = int(getattr(symbol_info, "spread", 0) or 0)
            info.trade_contract_size = float(
                getattr(symbol_info, "trade_contract_size", 100.0) or 100.0
            )
            info.volume_min = float(getattr(symbol_info, "volume_min", 0.01) or 0.01)
            info.volume_max = float(getattr(symbol_info, "volume_max", 100.0) or 100.0)
            info.volume_step = float(getattr(symbol_info, "volume_step", 0.01) or 0.01)
            info.trade_freeze_level = int(getattr(symbol_info, "trade_freeze_level", 0) or 0)
            info.trade_stops_level = int(getattr(symbol_info, "trade_stops_level", 0) or 0)
            # Tick value + size
            info.tick_value = float(getattr(symbol_info, "trade_tick_value", 1.0) or 1.0)
            info.tick_size = float(getattr(symbol_info, "trade_tick_size", info.point) or info.point)
            # Execution mode
            trade_exe = getattr(symbol_info, "trade_mode", 0)
            info.trade_execution = {
                0: "EXCHANGE",
                1: "INSTANT",
                2: "REQUEST",
                3: "MARKET",
            }.get(trade_exe, "UNKNOWN")
            # Filling mode (bitmask)
            filling = getattr(symbol_info, "filling_mode", 0) or 0
            filling_modes = []
            if filling & 1:
                filling_modes.append("FOK")
            if filling & 2:
                filling_modes.append("IOC")
            if filling & 4:
                filling_modes.append("RETURN")
            info.trade_filling = "|".join(filling_modes) if filling_modes else "UNKNOWN"

        # Margin mode from account
        margin_mode = getattr(acc, "margin_mode", 0)
        info.margin_mode = {
            0: "RETAIL_NETTING",
            1: "RETAIL_HEDGING",
            2: "EXCHANGE",
        }.get(margin_mode, "UNKNOWN")
        info.hedging = info.margin_mode == "RETAIL_HEDGING"

        info.detection_method = "mt5"
        return info

    def _journal_event(self, event_type: EventType, data: dict) -> None:
        if self.journal is None:
            return
        try:
            self.journal.log_event(event_type, data)
        except Exception as e:
            logger.error(f"Journal event {event_type.value} failed: {e}")
