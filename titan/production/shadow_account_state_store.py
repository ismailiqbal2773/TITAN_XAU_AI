"""TITAN XAU AI — Shadow Account State Store (v2.8.7-P2.1)
============================================================

Persistent shadow account-state store with:
  - UTC trading-day reset
  - Atomic updates
  - Restart recovery
  - Schema version
  - Corruption detection
  - Account login and broker-server binding

This store is the SINGLE SOURCE OF TRUTH for the shadow runner's safety
state. No literal safe values may be used in SafetyStateV2,
RiskGovernorInput, or CEO governance — all values must come from this
store (or its underlying component engines).

NEVER sends orders. NEVER creates tokens. NEVER trades.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict, field
from typing import Optional, Dict, Any
from datetime import datetime, timezone, timedelta
from pathlib import Path
import json
import hashlib
import os
import tempfile

SCHEMA_VERSION = "2.8.7-P2.1"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _utc_trading_day(ts: Optional[datetime] = None) -> str:
    """Return YYYY-MM-DD for the current UTC trading day."""
    if ts is None:
        ts = datetime.now(timezone.utc)
    return ts.strftime("%Y-%m-%d")


@dataclass
class ShadowAccountState:
    schema_version: str = SCHEMA_VERSION
    account_login: str = ""
    broker_server: str = ""
    account_currency: str = "USD"
    starting_equity: float = 100000.0
    equity: float = 100000.0
    equity_peak: float = 100000.0
    daily_start_equity: float = 100000.0
    daily_peak: float = 100000.0
    current_trading_day: str = ""
    last_update_utc: str = ""
    loss_streak: int = 0
    max_consecutive_losses: int = 0
    existing_daily_open_risk: float = 0.0
    existing_total_open_risk: float = 0.0
    existing_combined_risk: float = 0.0
    n_open_positions: int = 0
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    state_hash: str = ""

    def compute_hash(self) -> str:
        """SHA-256 hash of all fields except state_hash itself."""
        d = asdict(self)
        d.pop("state_hash", None)
        serialized = json.dumps(d, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode()).hexdigest()

    def to_dict(self) -> dict:
        d = asdict(self)
        d["state_hash"] = self.compute_hash()
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "ShadowAccountState":
        # Validate hash for corruption detection
        stored_hash = d.get("state_hash", "")
        state = cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})
        computed_hash = state.compute_hash()
        if stored_hash and stored_hash != computed_hash:
            raise ValueError(f"shadow_account_state_corruption: hash mismatch")
        return state


class ShadowAccountStateStore:
    """Persistent shadow account state store.

    Stores state as a single JSON file with atomic writes.
    """

    def __init__(self, path: Path, account_login: str = "", broker_server: str = "",
                 starting_equity: float = 100000.0, account_currency: str = "USD"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._state: Optional[ShadowAccountState] = None
        self._load_or_initialize(account_login, broker_server, starting_equity, account_currency)

    def _load_or_initialize(self, account_login: str, broker_server: str,
                              starting_equity: float, account_currency: str):
        if self.path.exists():
            try:
                with open(self.path) as f:
                    data = json.load(f)
                # Verify account/server binding
                if account_login and data.get("account_login") and \
                        data.get("account_login") != account_login:
                    raise ValueError(
                        f"account_login_mismatch: stored={data.get('account_login')} "
                        f"requested={account_login}"
                    )
                if broker_server and data.get("broker_server") and \
                        data.get("broker_server") != broker_server:
                    raise ValueError(
                        f"broker_server_mismatch: stored={data.get('broker_server')} "
                        f"requested={broker_server}"
                    )
                self._state = ShadowAccountState.from_dict(data)
            except Exception as e:
                # Corruption detection — refuse to silently overwrite
                raise RuntimeError(
                    f"shadow_account_state_corrupt_or_unreadable: {e}. "
                    f"Manual intervention required at {self.path}"
                ) from e
        else:
            today = _utc_trading_day()
            self._state = ShadowAccountState(
                account_login=account_login,
                broker_server=broker_server,
                account_currency=account_currency,
                starting_equity=starting_equity,
                equity=starting_equity,
                equity_peak=starting_equity,
                daily_start_equity=starting_equity,
                daily_peak=starting_equity,
                current_trading_day=today,
                last_update_utc=_utc_now_iso(),
            )
            self._save_atomic()

    def _save_atomic(self):
        """Atomic write via temp file + rename."""
        self._state.last_update_utc = _utc_now_iso()
        self._state.state_hash = self._state.compute_hash()
        tmp_path = self.path.with_suffix(".tmp")
        with open(tmp_path, "w") as f:
            json.dump(self._state.to_dict(), f, indent=2, default=str)
        os.replace(tmp_path, self.path)

    @property
    def state(self) -> ShadowAccountState:
        if self._state is None:
            raise RuntimeError("state_not_initialized")
        return self._state

    def daily_reset_if_needed(self):
        """Reset daily counters if UTC trading day has changed."""
        today = _utc_trading_day()
        if self._state.current_trading_day != today:
            self._state.current_trading_day = today
            self._state.daily_start_equity = self._state.equity
            self._state.daily_peak = self._state.equity
            self._save_atomic()

    def update_equity(self, new_equity: float):
        """Update equity and peaks. Atomic."""
        self._state.equity = new_equity
        if new_equity > self._state.equity_peak:
            self._state.equity_peak = new_equity
        if new_equity > self._state.daily_peak:
            self._state.daily_peak = new_equity
        self._save_atomic()

    def record_trade(self, pnl_net: float, won: bool):
        """Record a closed trade's PnL. Atomic."""
        self._state.equity += pnl_net
        if self._state.equity > self._state.equity_peak:
            self._state.equity_peak = self._state.equity
        if self._state.equity > self._state.daily_peak:
            self._state.daily_peak = self._state.equity
        self._state.total_trades += 1
        if won:
            self._state.wins += 1
            self._state.loss_streak = 0
        else:
            self._state.losses += 1
            self._state.loss_streak += 1
            if self._state.loss_streak > self._state.max_consecutive_losses:
                self._state.max_consecutive_losses = self._state.loss_streak
        self._save_atomic()

    def add_open_risk(self, daily_risk: float, total_risk: float, combined_risk: float):
        self._state.existing_daily_open_risk += daily_risk
        self._state.existing_total_open_risk += total_risk
        self._state.existing_combined_risk += combined_risk
        self._state.n_open_positions += 1
        self._save_atomic()

    def release_open_risk(self, daily_risk: float, total_risk: float, combined_risk: float):
        self._state.existing_daily_open_risk = max(0.0, self._state.existing_daily_open_risk - daily_risk)
        self._state.existing_total_open_risk = max(0.0, self._state.existing_total_open_risk - total_risk)
        self._state.existing_combined_risk = max(0.0, self._state.existing_combined_risk - combined_risk)
        self._state.n_open_positions = max(0, self._state.n_open_positions - 1)
        self._save_atomic()

    @property
    def daily_dd(self) -> float:
        if self._state.daily_peak <= 0:
            return 0.0
        return (self._state.daily_peak - self._state.equity) / self._state.daily_peak

    @property
    def total_dd(self) -> float:
        if self._state.equity_peak <= 0:
            return 0.0
        return (self._state.equity_peak - self._state.equity) / self._state.equity_peak


__all__ = ["ShadowAccountState", "ShadowAccountStateStore", "SCHEMA_VERSION"]
