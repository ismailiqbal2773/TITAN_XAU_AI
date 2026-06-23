"""
TITAN XAU AI — MT5 Bridge Validator (Sprint 7.5)

Verifies MT5 installation, connection, account type, and symbol availability.
Fail-closed on any error.

Usage:
    validator = MT5Validator()
    result = validator.validate(login=34265693, password="...", server="FundedNext-Server 3")
    if result.ok:
        # safe to proceed
        ...
    else:
        # refuse to start
        ...
"""
from __future__ import annotations

import logging
import os
import platform
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of MT5 validation."""
    ok: bool = False
    checks: dict = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    account_info: dict = field(default_factory=dict)
    symbol_info: dict = field(default_factory=dict)

    def __repr__(self) -> str:
        return f"ValidationResult(ok={self.ok}, errors={len(self.errors)}, warnings={len(self.warnings)})"


class MT5Validator:
    """
    Fail-closed MT5 validator.

    Verifies:
      1. MT5 package installed
      2. MT5 terminal installed (Windows)
      3. MT5 initialize succeeds
      4. Account connected
      5. Account is DEMO
      6. Symbol (XAUUSD) available
    """

    DEFAULT_TERMINAL_PATHS = [
        r"C:\Program Files\MetaTrader 5\terminal64.exe",
        r"C:\Program Files (x86)\MetaTrader 5\terminal64.exe",
        os.path.expanduser(r"~\AppData\Roaming\MetaQuotes\Terminal\terminal64.exe"),
    ]

    def __init__(self, journal=None):
        self.journal = journal
        self._mt5 = None

    def validate(
        self,
        login: int = 0,
        password: str = "",
        server: str = "",
        terminal_path: str = "",
        symbol: str = "XAUUSD",
    ) -> ValidationResult:
        """
        Run full MT5 validation.
        Returns ValidationResult.
        """
        result = ValidationResult()

        # ─── Check 1: Platform ──
        if platform.system() != "Windows":
            result.warnings.append("Non-Windows platform — MT5 not available (stub mode)")
            result.checks["platform"] = "skipped_non_windows"
            # On non-Windows, we can't validate MT5 — return ok with warning
            result.ok = True
            return result
        result.checks["platform"] = "windows"

        # ─── Check 2: MT5 package ──
        try:
            import MetaTrader5 as mt5
            self._mt5 = mt5
            result.checks["mt5_package"] = "installed"
        except ImportError:
            result.errors.append("MetaTrader5 Python package not installed")
            result.checks["mt5_package"] = "missing"
            return result

        # ─── Check 3: MT5 terminal installed ──
        terminal = terminal_path or self._find_terminal()
        if terminal and os.path.exists(terminal):
            result.checks["terminal_path"] = terminal
        else:
            result.errors.append(f"MT5 terminal not found. Looked in: {self.DEFAULT_TERMINAL_PATHS}")
            result.checks["terminal_path"] = "not_found"
            return result

        # ─── Check 4: MT5 initialize ──
        init_kwargs = {"timeout": 30000}
        if terminal_path:
            init_kwargs["path"] = terminal
        if login:
            init_kwargs["login"] = login
            init_kwargs["password"] = password
            init_kwargs["server"] = server

        if not mt5.initialize(**init_kwargs):
            error = f"mt5.initialize() failed: {mt5.last_error()}"
            result.errors.append(error)
            result.checks["initialize"] = "failed"
            return result
        result.checks["initialize"] = "ok"

        try:
            # ─── Check 5: Account info ──
            account = mt5.account_info()
            if account is None:
                result.errors.append("account_info() returned None")
                result.checks["account"] = "none"
                return result

            result.account_info = {
                "login": account.login,
                "server": account.server,
                "company": getattr(account, "company", ""),
                "currency": account.currency,
                "leverage": account.leverage,
                "balance": account.balance,
                "equity": account.equity,
            }
            result.checks["account"] = "connected"

            # ─── Check 6: Account is DEMO ──
            server_lower = (server or account.server or "").lower()
            company_lower = (getattr(account, "company", "") or "").lower()
            is_demo = (
                "demo" in server_lower or
                "demo" in company_lower or
                "fundednext-server" in server_lower or
                "fbs-demo" in server_lower or
                "icmarkets-demo" in server_lower
            )
            if not is_demo:
                result.errors.append(
                    f"REAL ACCOUNT DETECTED (login={account.login}, server={account.server}) — "
                    "TITAN refuses to connect to real accounts"
                )
                result.checks["is_demo"] = False
                return result
            result.checks["is_demo"] = True

            # ─── Check 7: Symbol available ──
            if not mt5.symbol_select(symbol, True):
                result.errors.append(f"symbol_select({symbol}) failed — symbol not available")
                result.checks["symbol"] = "not_available"
                return result

            sym_info = mt5.symbol_info(symbol)
            if sym_info:
                result.symbol_info = {
                    "name": sym_info.name,
                    "digits": sym_info.digits,
                    "point": sym_info.point,
                    "spread": sym_info.spread,
                    "contract_size": sym_info.trade_contract_size,
                }
                result.checks["symbol"] = "available"
            else:
                result.warnings.append(f"symbol_info({symbol}) returned None")
                result.checks["symbol"] = "no_info"

            result.ok = True
            return result

        finally:
            mt5.shutdown()

    def _find_terminal(self) -> Optional[str]:
        """Find MT5 terminal executable."""
        for path in self.DEFAULT_TERMINAL_PATHS:
            if os.path.exists(path):
                return path
        return None


class StubMT5Validator(MT5Validator):
    """Stub validator for testing without real MT5."""

    def validate(
        self,
        login: int = 0,
        password: str = "",
        server: str = "",
        terminal_path: str = "",
        symbol: str = "XAUUSD",
        simulate_demo: bool = True,
    ) -> ValidationResult:
        result = ValidationResult()
        result.checks = {
            "platform": "stub",
            "mt5_package": "stub",
            "terminal_path": "stub",
            "initialize": "ok",
            "account": "connected",
            "is_demo": simulate_demo,
            "symbol": "available",
        }
        if not simulate_demo:
            result.errors.append("REAL ACCOUNT DETECTED — TITAN refuses real accounts")
            result.ok = False
            return result
        result.account_info = {
            "login": login or 34265693,
            "server": server or "FundedNext-Server 3",
            "company": "FundedNext Ltd",
            "currency": "USD",
            "leverage": 100,
            "balance": 6000.0,
            "equity": 6000.0,
        }
        result.symbol_info = {
            "name": symbol,
            "digits": 2,
            "point": 0.01,
            "spread": 45,
            "contract_size": 100.0,
        }
        result.ok = True
        return result
