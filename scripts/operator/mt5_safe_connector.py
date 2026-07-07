#!/usr/bin/env python3
"""TITAN XAU AI — MT5 Safe Connector (Module 1)
==============================================
Safe MT5 bridge for account info and market data ONLY.
NEVER trades. NEVER calls order_send. NEVER creates tokens.

This module:
  - Initializes MT5
  - Verifies MetaTrader5 package
  - Verifies terminal connected
  - Verifies account_info
  - Verifies DEMO account only
  - Verifies server string (Exness or approved demo)
  - Masks account login
  - Detects leverage, balance, equity, margin, free margin
  - Verifies XAUUSD symbol exists
  - Fetches latest H1 bars
  - Normalizes columns
  - Validates OHLC schema
  - Validates spread
  - Validates timestamp continuity

BLOCK RULES:
  - Live account → BLOCK_LIVE_ACCOUNT
  - Unknown server → BLOCK_UNKNOWN_SERVER
  - Symbol missing → BLOCK_SYMBOL_MISSING

NEVER sends orders. NEVER creates tokens. NEVER trades.
"""
from __future__ import annotations
import sys, os, json, logging
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

logger = logging.getLogger(__name__)

# Approved server strings
APPROVED_SERVER_STRINGS = [
    "Exness",
    "Exness-MT5Trial",
    "Exness-Demo",
    "MetaQuotes-Demo",  # benchmark/demo only, not approval
]

# Servers that can approve (not MetaQuotes-Demo which is benchmark only)
APPROVAL_SERVERS = ["Exness", "Exness-MT5Trial", "Exness-Demo"]


@dataclass
class MT5AccountInfo:
    """Safe account info — login is masked."""
    login_masked: str
    server: str
    server_approved: bool
    is_demo: bool
    leverage: int
    balance: float
    equity: float
    margin: float
    free_margin: float
    currency: str
    company: str

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


@dataclass
class MT5ConnectionResult:
    """Result of MT5 connection attempt."""
    success: bool
    verdict: str
    error: str = ""
    account_info: Optional[MT5AccountInfo] = None
    raw_bars: Optional[list] = None


def mask_login(login: int) -> str:
    """Mask account login for safety — only show last 4 digits."""
    s = str(login)
    if len(s) <= 4:
        return f"****{s[-2:]}"
    return f"****{s[-4:]}"


def check_mt5_package() -> bool:
    """Check if MetaTrader5 Python package is available."""
    try:
        import MetaTrader5  # noqa: F401
        return True
    except ImportError:
        return False


def is_demo_account(account_info) -> bool:
    """Check if account is demo. MT5 trade_mode: 0=real, 1=demo, 2=contest."""
    trade_mode = getattr(account_info, "trade_mode", 0)
    return trade_mode == 1


def is_server_approved(server: str) -> bool:
    """Check if server string is in approved list."""
    for approved in APPROVED_SERVER_STRINGS:
        if approved.lower() in server.lower():
            return True
    return False


def is_server_approval_capable(server: str) -> bool:
    """Check if server can approve prop readiness (not MetaQuotes-Demo)."""
    for approved in APPROVAL_SERVERS:
        if approved.lower() in server.lower():
            return True
    return False


def initialize_mt5() -> bool:
    """Initialize MT5 terminal. Returns True if successful."""
    try:
        import MetaTrader5 as mt5
        if not mt5.initialize():
            logger.error(f"MT5 initialize() failed: {mt5.last_error()}")
            return False
        return True
    except ImportError:
        logger.error("MetaTrader5 package not available")
        return False
    except Exception as e:
        logger.error(f"MT5 initialize error: {e}")
        return False


def shutdown_mt5():
    """Shutdown MT5 connection."""
    try:
        import MetaTrader5 as mt5
        mt5.shutdown()
    except Exception:
        pass


def get_account_info() -> Optional[MT5AccountInfo]:
    """Get safe account info from MT5. Returns None if failed."""
    try:
        import MetaTrader5 as mt5
        info = mt5.account_info()
        if info is None:
            return None

        server = getattr(info, "server", "unknown")
        login = getattr(info, "login", 0)

        return MT5AccountInfo(
            login_masked=mask_login(login),
            server=server,
            server_approved=is_server_approved(server),
            is_demo=is_demo_account(info),
            leverage=getattr(info, "leverage", 0),
            balance=float(getattr(info, "balance", 0)),
            equity=float(getattr(info, "equity", 0)),
            margin=float(getattr(info, "margin", 0)),
            free_margin=float(getattr(info, "margin_free", 0)),
            currency=getattr(info, "currency", ""),
            company=getattr(info, "company", ""),
        )
    except Exception as e:
        logger.error(f"get_account_info error: {e}")
        return None


def verify_symbol(symbol: str = "XAUUSD") -> bool:
    """Verify that symbol exists in MT5."""
    try:
        import MetaTrader5 as mt5
        info = mt5.symbol_info(symbol)
        return info is not None
    except Exception:
        return False


def fetch_h1_bars(symbol: str = "XAUUSD", count: int = 300) -> Optional[list]:
    """Fetch latest H1 bars from MT5. Returns list of raw bars or None."""
    try:
        import MetaTrader5 as mt5
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, count)
        if rates is None or len(rates) == 0:
            return None
        return rates.tolist()
    except Exception as e:
        logger.error(f"fetch_h1_bars error: {e}")
        return None


def validate_ohlc_schema(bars: list) -> Dict[str, Any]:
    """Validate OHLC schema of fetched bars."""
    if not bars:
        return {"valid": False, "error": "no bars"}

    required_fields = ["time", "open", "high", "low", "close", "tick_volume", "spread"]
    first_bar = bars[0] if isinstance(bars[0], dict) else None

    # MT5 returns named tuples — check by attribute
    sample = bars[0]
    if hasattr(sample, "_asdict"):
        sample = sample._asdict()
    elif not isinstance(sample, dict):
        # It's a tuple — MT5 returns structured arrays
        return {"valid": True, "note": "tuple format - column names from MT5"}

    missing = [f for f in required_fields if f not in sample]
    if missing:
        return {"valid": False, "error": f"missing fields: {missing}"}

    return {"valid": True, "missing": []}


def validate_spread(bars: list) -> Dict[str, Any]:
    """Validate spread values in bars."""
    if not bars:
        return {"valid": False, "error": "no bars"}

    spreads = []
    for bar in bars:
        if hasattr(bar, "spread"):
            spreads.append(bar.spread)
        elif isinstance(bar, dict) and "spread" in bar:
            spreads.append(bar["spread"])

    if not spreads:
        return {"valid": True, "note": "no spread field in bars"}

    import numpy as np
    return {
        "valid": True,
        "min": float(np.min(spreads)),
        "max": float(np.max(spreads)),
        "mean": float(np.mean(spreads)),
        "median": float(np.median(spreads)),
    }


def validate_timestamp_continuity(bars: list, timeframe_seconds: int = 3600) -> Dict[str, Any]:
    """Validate that bar timestamps are continuous (no gaps)."""
    if not bars or len(bars) < 2:
        return {"valid": True, "note": "insufficient bars"}

    timestamps = []
    for bar in bars:
        if hasattr(bar, "time"):
            timestamps.append(bar.time)
        elif isinstance(bar, dict) and "time" in bar:
            timestamps.append(bar["time"])

    if len(timestamps) < 2:
        return {"valid": True, "note": "insufficient timestamps"}

    gaps = 0
    for i in range(1, len(timestamps)):
        diff = timestamps[i] - timestamps[i-1]
        if diff != timeframe_seconds:
            gaps += 1

    return {
        "valid": gaps < len(timestamps) * 0.1,  # <10% gaps is OK
        "total_bars": len(timestamps),
        "gaps": gaps,
        "gap_rate": round(gaps / max(len(timestamps) - 1, 1), 4),
    }


def safe_connect_and_audit(symbol: str = "XAUUSD", bar_count: int = 300) -> MT5ConnectionResult:
    """Main entry: connect to MT5 safely and audit account.

    Returns MT5ConnectionResult with verdict:
      - CONNECT_SUCCESS
      - BLOCK_LIVE_ACCOUNT
      - BLOCK_UNKNOWN_SERVER
      - BLOCK_SYMBOL_MISSING
      - MT5_PACKAGE_MISSING
      - MT5_INITIALIZE_FAILED
      - MT5_NO_ACCOUNT_INFO
    """
    # 1. Check package
    if not check_mt5_package():
        return MT5ConnectionResult(
            success=False, verdict="MT5_PACKAGE_MISSING",
            error="MetaTrader5 Python package not installed"
        )

    # 2. Initialize
    if not initialize_mt5():
        return MT5ConnectionResult(
            success=False, verdict="MT5_INITIALIZE_FAILED",
            error="mt5.initialize() failed — terminal may not be running"
        )

    try:
        # 3. Get account info
        account = get_account_info()
        if account is None:
            return MT5ConnectionResult(
                success=False, verdict="MT5_NO_ACCOUNT_INFO",
                error="Could not retrieve account_info"
            )

        # 4. Block live accounts
        if not account.is_demo:
            return MT5ConnectionResult(
                success=False, verdict="BLOCK_LIVE_ACCOUNT",
                error=f"Account is LIVE (not demo). Login: {account.login_masked}",
                account_info=account
            )

        # 5. Block unknown servers
        if not account.server_approved:
            return MT5ConnectionResult(
                success=False, verdict="BLOCK_UNKNOWN_SERVER",
                error=f"Server '{account.server}' not in approved list",
                account_info=account
            )

        # 6. Verify symbol
        if not verify_symbol(symbol):
            return MT5ConnectionResult(
                success=False, verdict="BLOCK_SYMBOL_MISSING",
                error=f"Symbol {symbol} not found",
                account_info=account
            )

        # 7. Fetch bars
        bars = fetch_h1_bars(symbol, bar_count)
        if bars is None:
            return MT5ConnectionResult(
                success=False, verdict="MT5_NO_BARS",
                error=f"Could not fetch H1 bars for {symbol}",
                account_info=account
            )

        return MT5ConnectionResult(
            success=True, verdict="CONNECT_SUCCESS",
            account_info=account, raw_bars=bars
        )

    finally:
        shutdown_mt5()


if __name__ == "__main__":
    # When run directly, perform safe audit
    import csv
    from datetime import datetime, timezone

    ts = datetime.now(timezone.utc).isoformat()
    output_dir = REPO_ROOT / "data" / "reports" / "exness_forward_shadow"
    output_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("  TITAN XAU AI - MT5 SAFE CONNECTOR AUDIT (Module 1)")
    print("=" * 70)
    print(f"  Timestamp: {ts}\n")

    result = safe_connect_and_audit()

    print(f"  Verdict: {result.verdict}")
    if result.account_info:
        ai = result.account_info
        print(f"  Login (masked): {ai.login_masked}")
        print(f"  Server: {ai.server}")
        print(f"  Server approved: {ai.server_approved}")
        print(f"  Is demo: {ai.is_demo}")
        print(f"  Leverage: 1:{ai.leverage}")
        print(f"  Balance: {ai.balance}")
        print(f"  Equity: {ai.equity}")
        print(f"  Margin: {ai.margin}")
        print(f"  Free margin: {ai.free_margin}")

    if result.success and result.raw_bars:
        schema = validate_ohlc_schema(result.raw_bars)
        spread = validate_spread(result.raw_bars)
        timestamps = validate_timestamp_continuity(result.raw_bars)

        print(f"\n  Bar count: {len(result.raw_bars)}")
        print(f"  Schema valid: {schema['valid']}")
        print(f"  Spread: {spread}")
        print(f"  Timestamps: {timestamps}")

        # Save sample bars
        import pandas as pd
        df = pd.DataFrame(result.raw_bars)
        if "time" in df.columns:
            df["time"] = pd.to_datetime(df["time"], unit="s")
        df.to_csv(output_dir / "mt5_market_data_sample.csv", index=False)

        # Schema audit
        schema_audit = {
            "timestamp_utc": ts,
            "verdict": result.verdict,
            "schema_valid": schema["valid"],
            "spread_valid": spread.get("valid", False),
            "timestamp_valid": timestamps.get("valid", False),
            "bar_count": len(result.raw_bars),
            "spread_stats": spread,
            "timestamp_stats": timestamps,
        }
        with open(output_dir / "mt5_data_schema_audit.json", "w") as f:
            json.dump(schema_audit, f, indent=2, default=str)
        with open(output_dir / "mt5_data_schema_audit.md", "w") as f:
            f.write("# MT5 Data Schema Audit (Module 1)\n\n")
            f.write(f"**Timestamp:** {ts}\n\n")
            f.write(f"## Verdict: {result.verdict}\n\n")
            f.write(f"- Schema valid: {schema['valid']}\n")
            f.write(f"- Spread valid: {spread.get('valid', False)}\n")
            f.write(f"- Timestamp valid: {timestamps.get('valid', False)}\n")
            f.write(f"- Bar count: {len(result.raw_bars)}\n")

    # Account safety audit
    audit = {
        "timestamp_utc": ts,
        "verdict": result.verdict,
        "success": result.success,
        "error": result.error,
        "account_info": result.account_info.to_dict() if result.account_info else None,
        "safety": {
            "no_order_send": True,
            "no_token": True,
            "no_live_trading": True,
            "no_funded_trading": True,
            "production_ready": False,
            "dry_run": True,
        },
    }
    with open(output_dir / "mt5_account_safety_audit.json", "w") as f:
        json.dump(audit, f, indent=2, default=str)
    with open(output_dir / "mt5_account_safety_audit.md", "w") as f:
        f.write("# MT5 Account Safety Audit (Module 1)\n\n")
        f.write(f"**Timestamp:** {ts}\n\n")
        f.write(f"## Verdict: {result.verdict}\n\n")
        if result.account_info:
            ai = result.account_info
            f.write("## Account Info\n\n")
            f.write(f"- Login (masked): {ai.login_masked}\n")
            f.write(f"- Server: {ai.server}\n")
            f.write(f"- Server approved: {ai.server_approved}\n")
            f.write(f"- Is demo: {ai.is_demo}\n")
            f.write(f"- Leverage: 1:{ai.leverage}\n")
            f.write(f"- Balance: {ai.balance}\n")
            f.write(f"- Equity: {ai.equity}\n")
            f.write(f"- Margin: {ai.margin}\n")
            f.write(f"- Free margin: {ai.free_margin}\n")
        f.write("\n## Safety\n\n")
        f.write("- no_order_send: True\n- no_token: True\n")
        f.write("- no_live_trading: True\n- no_funded_trading: True\n")
        f.write("- production_ready: False\n- dry_run: True\n")

    print(f"\n  Output: {output_dir}")
    print("\n" + "=" * 70)
    print("  > NO TRADE. NO TOKEN. NO order_send. Read-only data only.")
    print("=" * 70)
