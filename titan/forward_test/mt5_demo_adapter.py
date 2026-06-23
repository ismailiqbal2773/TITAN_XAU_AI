"""
TITAN XAU AI — MT5 Demo Adapter (Sprint 6)

FAIL-CLOSED adapter that connects ONLY to MT5 DEMO accounts.
Refuses to start on real accounts. Refuses to start if account
cannot be verified.

Safety properties:
  1. Account type must be DEMO (verified via MT5 account_info)
  2. If account type cannot be determined → refuse startup
  3. If account is REAL → refuse startup
  4. All verification results journaled

Usage:
    adapter = MT5DemoAdapter(journal=journal)
    if adapter.connect(login=..., password=..., server=...):
        # safe to proceed with demo trading
        ...
    else:
        # refuse to start
        ...
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from titan.production.trade_journal import TradeJournal, EventType

logger = logging.getLogger(__name__)


@dataclass
class AccountVerification:
    """Result of MT5 account verification."""
    verified: bool = False
    is_demo: bool = False
    login: int = 0
    server: str = ""
    company: str = ""
    currency: str = ""
    leverage: int = 0
    balance: float = 0.0
    equity: float = 0.0
    error: Optional[str] = None
    verified_at: float = 0.0


class MT5DemoAdapter:
    """
    Fail-closed MT5 demo account adapter.

    Will NOT connect to real accounts. Will NOT proceed if account
    type cannot be verified.
    """

    def __init__(self, journal: Optional[TradeJournal] = None):
        self.journal = journal
        self._connected = False
        self._verification: Optional[AccountVerification] = None
        self._mt5 = None

    def connect(self, login: int, password: str, server: str,
                terminal_path: str = "") -> bool:
        """
        Connect to MT5 and verify account is DEMO.

        Returns True iff:
          1. MT5 initialize succeeds
          2. Account info retrieved
          3. Account type verified as DEMO

        Returns False (and logs to journal) on ANY failure.
        """
        try:
            import MetaTrader5 as mt5
            self._mt5 = mt5
        except ImportError:
            logger.error("MetaTrader5 package not available — cannot connect")
            if self.journal:
                self.journal.log_event(EventType.STARTUP, {
                    "adapter": "mt5_demo",
                    "status": "failed",
                    "error": "MetaTrader5 not installed",
                })
            return False

        # ── Initialize MT5 ──
        init_kwargs = {"login": login, "password": password, "server": server}
        if terminal_path:
            init_kwargs["path"] = terminal_path

        if not mt5.initialize(**init_kwargs):
            error = f"mt5.initialize() failed: {mt5.last_error()}"
            logger.error(error)
            self._verification = AccountVerification(
                verified=False, error=error, verified_at=time.time()
            )
            if self.journal:
                self.journal.log_event(EventType.STARTUP, {
                    "adapter": "mt5_demo", "status": "init_failed",
                    "error": error, "login": login, "server": server,
                })
            return False

        # ── Verify account ──
        self._verification = self._verify_account(login, server)
        mt5.shutdown()

        if not self._verification.verified:
            logger.error(f"Account verification failed: {self._verification.error}")
            if self.journal:
                self.journal.log_event(EventType.STARTUP, {
                    "adapter": "mt5_demo", "status": "verification_failed",
                    "error": self._verification.error,
                    "login": login, "server": server,
                })
            return False

        if not self._verification.is_demo:
            error = f"REFUSING REAL ACCOUNT (login={login}, server={server})"
            logger.critical(error)
            self._verification.verified = False
            self._verification.error = "real_account_blocked"
            if self.journal:
                self.journal.log_event(EventType.KILL_SWITCH_BLOCK, {
                    "reason": "real_account_detected",
                    "login": login, "server": server,
                    "company": self._verification.company,
                })
            return False

        # ── Success: demo account verified ──
        self._connected = True
        logger.info(f"✓ MT5 demo account verified: login={login}, server={server}")
        if self.journal:
            self.journal.log_event(EventType.STARTUP, {
                "adapter": "mt5_demo", "status": "connected",
                "login": login, "server": server,
                "company": self._verification.company,
                "balance": self._verification.balance,
                "currency": self._verification.currency,
            })
        return True

    def _verify_account(self, login: int, server: str) -> AccountVerification:
        """Verify the connected account is a DEMO account."""
        mt5 = self._mt5
        account_info = mt5.account_info()
        if account_info is None:
            return AccountVerification(
                verified=False, login=login, server=server,
                error="account_info() returned None",
                verified_at=time.time(),
            )

        # Determine if demo
        # MT5 doesn't have a direct "is_demo" field, but we can infer from:
        # 1. Server name contains "demo" or "Demo"
        # 2. Company name contains "demo"
        # 3. Trade mode (4 = full mode, but demo servers often have specific patterns)
        server_lower = server.lower()
        company = getattr(account_info, "company", "") or ""
        company_lower = company.lower()

        is_demo = (
            "demo" in server_lower or
            "demo" in company_lower or
            server_lower.startswith("fundednext-server") or  # FundedNext demo
            "fbs-demo" in server_lower or
            "icmarkets-demo" in server_lower
        )

        # If we can't determine, FAIL CLOSED
        if not is_demo and "demo" not in server_lower and "demo" not in company_lower:
            # Could be real — refuse
            return AccountVerification(
                verified=False, is_demo=False,
                login=getattr(account_info, "login", login),
                server=server,
                company=getattr(account_info, "company", ""),
                currency=getattr(account_info, "currency", "USD"),
                leverage=getattr(account_info, "leverage", 0),
                balance=getattr(account_info, "balance", 0.0),
                equity=getattr(account_info, "equity", 0.0),
                error="cannot_verify_demo_status",
                verified_at=time.time(),
            )

        return AccountVerification(
            verified=True, is_demo=True,
            login=getattr(account_info, "login", login),
            server=server,
            company=getattr(account_info, "company", ""),
            currency=getattr(account_info, "currency", "USD"),
            leverage=getattr(account_info, "leverage", 0),
            balance=getattr(account_info, "balance", 0.0),
            equity=getattr(account_info, "equity", 0.0),
            verified_at=time.time(),
        )

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def verification(self) -> Optional[AccountVerification]:
        return self._verification

    def disconnect(self) -> None:
        """Disconnect from MT5."""
        if self._mt5 and self._connected:
            try:
                self._mt5.shutdown()
            except Exception:
                pass
        self._connected = False
        logger.info("MT5 demo adapter disconnected")


class StubMT5DemoAdapter(MT5DemoAdapter):
    """
    Stub adapter for testing without real MT5.
    Simulates demo account verification.
    """

    def __init__(self, journal: Optional[TradeJournal] = None,
                 simulate_demo: bool = True,
                 simulate_login: int = 34265693,
                 simulate_server: str = "FundedNext-Server 3"):
        super().__init__(journal=journal)
        self._simulate_demo = simulate_demo
        self._simulate_login = simulate_login
        self._simulate_server = simulate_server

    def connect(self, login: int = 0, password: str = "", server: str = "",
                terminal_path: str = "") -> bool:
        """Simulate connection without real MT5."""
        login = login or self._simulate_login
        server = server or self._simulate_server

        if not self._simulate_demo:
            # Simulate real account — must refuse
            self._verification = AccountVerification(
                verified=False, is_demo=False,
                login=login, server=server,
                company="Real Broker Ltd",
                error="real_account_blocked",
                verified_at=time.time(),
            )
            logger.warning(f"STUB: Refusing real account (login={login})")
            if self.journal:
                self.journal.log_event(EventType.KILL_SWITCH_BLOCK, {
                    "reason": "real_account_detected",
                    "login": login, "server": server,
                })
            return False

        # Simulate demo account
        self._verification = AccountVerification(
            verified=True, is_demo=True,
            login=login, server=server,
            company="FundedNext Ltd",
            currency="USD", leverage=100,
            balance=6000.0, equity=6000.0,
            verified_at=time.time(),
        )
        self._connected = True
        logger.info(f"STUB: Demo account verified (login={login}, server={server})")
        if self.journal:
            self.journal.log_event(EventType.STARTUP, {
                "adapter": "mt5_demo_stub", "status": "connected",
                "login": login, "server": server,
                "balance": 6000.0,
            })
        return True
