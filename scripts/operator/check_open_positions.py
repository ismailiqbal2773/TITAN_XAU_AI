#!/usr/bin/env python3
"""
TITAN XAU AI - Open Position Safety Probe (Sprint 9.9.3.45.8.9)
=================================================================
Read-only MT5 connection to check for open positions.
NEVER sends orders. NEVER modifies positions.

Verdicts:
  - SAFE_NO_OPEN_POSITIONS
  - BLOCKED_OPEN_POSITION_EXISTS
  - MT5_NOT_CONNECTED
  - ACCOUNT_NOT_DEMO
"""
from __future__ import annotations
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

TITAN_MAGIC = 202619


def run_probe() -> dict:
    ts = datetime.now(timezone.utc).isoformat()
    findings = {
        "mt5_initialized": False,
        "account_login_masked": "",
        "server": "",
        "account_type": "",
        "symbol": "XAUUSD",
        "open_positions_count": 0,
        "titan_magic_positions_count": 0,
        "positions_detail": [],
    }

    try:
        import MetaTrader5 as mt5
    except ImportError:
        return {
            "timestamp_utc": ts,
            "verdict": "MT5_NOT_CONNECTED",
            "findings": findings,
            "safety": {"order_send_called": False, "position_modified": False},
        }

    try:
        if not mt5.initialize():
            return {
                "timestamp_utc": ts,
                "verdict": "MT5_NOT_CONNECTED",
                "findings": findings,
                "safety": {"order_send_called": False, "position_modified": False},
            }
        findings["mt5_initialized"] = True

        # Account info
        acc = mt5.account_info()
        if acc:
            login = getattr(acc, "login", 0)
            findings["account_login_masked"] = f"***{str(login)[-4:]}" if login else "unknown"
            findings["server"] = getattr(acc, "server", "unknown")
            trade_mode = getattr(acc, "trade_mode", -1)
            findings["account_type"] = "DEMO" if trade_mode == 0 else ("REAL" if trade_mode == 1 else "CONTEST" if trade_mode == 2 else "UNKNOWN")

            if trade_mode != 0:
                mt5.shutdown()
                return {
                    "timestamp_utc": ts,
                    "verdict": "ACCOUNT_NOT_DEMO",
                    "findings": findings,
                    "safety": {"order_send_called": False, "position_modified": False},
                }

        # Positions
        positions = mt5.positions_get(symbol="XAUUSD") or []
        findings["open_positions_count"] = len(positions)

        titan_positions = []
        for p in positions:
            pos_info = {
                "ticket": getattr(p, "ticket", 0),
                "magic": getattr(p, "magic", 0),
                "comment": getattr(p, "comment", ""),
                "profit": getattr(p, "profit", 0),
                "volume": getattr(p, "volume", 0),
                "type": "BUY" if getattr(p, "type", 1) == 0 else "SELL",
            }
            findings["positions_detail"].append(pos_info)
            if getattr(p, "magic", 0) == TITAN_MAGIC:
                titan_positions.append(pos_info)

        findings["titan_magic_positions_count"] = len(titan_positions)

        mt5.shutdown()

        if findings["open_positions_count"] == 0:
            verdict = "SAFE_NO_OPEN_POSITIONS"
        else:
            verdict = "BLOCKED_OPEN_POSITION_EXISTS"

    except Exception as e:
        try:
            mt5.shutdown()
        except Exception:
            pass
        return {
            "timestamp_utc": ts,
            "verdict": "MT5_NOT_CONNECTED",
            "findings": findings,
            "error": str(e),
            "safety": {"order_send_called": False, "position_modified": False},
        }

    return {
        "timestamp_utc": ts,
        "verdict": verdict,
        "findings": findings,
        "safety": {"order_send_called": False, "position_modified": False},
    }


def main() -> int:
    print("=" * 70)
    print("  TITAN XAU AI - Open Position Safety Probe (Read-Only)")
    print("=" * 70)
    result = run_probe()
    print(f"\n  Verdict: {result['verdict']}")
    f = result.get("findings", {})
    print(f"  MT5 initialized: {f.get('mt5_initialized', False)}")
    print(f"  Account: {f.get('account_login_masked', 'N/A')}")
    print(f"  Server: {f.get('server', 'N/A')}")
    print(f"  Account type: {f.get('account_type', 'N/A')}")
    print(f"  Open positions: {f.get('open_positions_count', 0)}")
    print(f"  TITAN magic positions: {f.get('titan_magic_positions_count', 0)}")
    if f.get("positions_detail"):
        print("\n  Open positions detail:")
        for p in f["positions_detail"]:
            print(f"    ticket={p['ticket']}, magic={p['magic']}, comment={p['comment']}, profit={p['profit']}")
    print(f"\n  Safety: order_send_called=False, position_modified=False")
    print("\n" + "=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
