#!/usr/bin/env python3
"""
TITAN XAU AI — Sprint 9.9.3.21 Raw MT5 Probe Script
====================================================

Sends a 0.01-lot naked (sl=0, tp=0) XAUUSD market order on a DEMO account
using IOC filling, then immediately closes it. If successful, saves the
working request profile to:
    data/audit/demo_micro/raw_mt5_working_profile.json

The saved profile can be loaded by MT5ExecutionAdapter via the
use_raw_working_profile kwarg, so the adapter mirrors the exact request
shape that succeeded on this broker.

Safety:
  - DEMO account only (hard block on REAL/CONTEST)
  - max lot 0.01 (hard-coded)
  - magic isolated (DEMO_MICRO_MAGIC = 20261993)
  - force close immediately after open
  - fail closed if account is not demo

Usage (on Windows MT5 DEMO):
    python scripts/audit/raw_mt5_probe.py
    python scripts/audit/raw_mt5_probe.py --symbol XAUUSD --side BUY
    python scripts/audit/raw_mt5_probe.py --dry-run   # check only, no order

NEVER run this on a LIVE account.
"""
from __future__ import annotations
import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

OUTPUT_DIR = REPO_ROOT / "data" / "audit" / "demo_micro"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
PROFILE_PATH = OUTPUT_DIR / "raw_mt5_working_profile.json"

DEMO_MICRO_MAGIC = 20261993

# MT5 constants
_TRADE_ACTION_DEAL = 1
_TRADE_ACTION_SLTP = 2
_ORDER_TYPE_BUY = 0
_ORDER_TYPE_SELL = 1
_TRADE_RETCODE_DONE = 10009


def _get_mt5():
    try:
        import MetaTrader5 as mt5
        return mt5
    except ImportError:
        return None


def _is_demo_account(account_info) -> bool:
    if account_info is None:
        return False
    return getattr(account_info, "trade_mode", 2) == 0


def _safe(obj, attr, default=None):
    try:
        return getattr(obj, attr, default)
    except Exception:
        return default


def probe_raw_mt5(symbol: str = "XAUUSD", side: str = "BUY",
                   lot: float = 0.01, deviation: int = 50,
                   dry_run: bool = False) -> dict:
    """Send a naked IOC demo order, close it, save working profile.

    Returns a result dict with:
      - ok (bool): True if the full open→close cycle succeeded
      - profile_path (str): path to saved profile (if ok)
      - error (str): error message (if not ok)
      - open_result, close_result: raw MT5 result dicts
    """
    mt5 = _get_mt5()
    if mt5 is None:
        return {"ok": False, "error": "MetaTrader5 not installed (Linux/Z AI)"}

    if not mt5.initialize():
        return {"ok": False, "error": "mt5.initialize() failed"}

    try:
        # ── Safety: DEMO account only ──
        account_info = mt5.account_info()
        if not _is_demo_account(account_info):
            return {"ok": False,
                    "error": "NOT A DEMO ACCOUNT — raw probe aborted for safety"}
        server = _safe(account_info, "server", "unknown")
        login = _safe(account_info, "login", "unknown")
        print(f"  Account: login={login} server={server} (DEMO ✓)")

        # ── Safety: lot cap ──
        if lot > 0.01:
            return {"ok": False,
                    "error": f"lot {lot} > 0.01 — raw probe enforces 0.01 max"}

        # ── Symbol info ──
        info = mt5.symbol_info(symbol)
        if info is None:
            return {"ok": False, "error": f"symbol_info({symbol}) returned None"}
        if not getattr(info, "visible", True):
            if not mt5.symbol_select(symbol, True):
                return {"ok": False,
                        "error": f"symbol_select({symbol}) failed"}

        # ── Get ORDER_FILLING_IOC from the mt5 module ──
        order_filling_ioc = getattr(mt5, "ORDER_FILLING_IOC", 2)
        print(f"  mt5.ORDER_FILLING_IOC = {order_filling_ioc}")

        # ── Fresh tick ──
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return {"ok": False, "error": "symbol_info_tick returned None"}

        if side == "BUY":
            price = float(getattr(tick, "ask", 0))
            order_type = _ORDER_TYPE_BUY
        else:
            price = float(getattr(tick, "bid", 0))
            order_type = _ORDER_TYPE_SELL

        # ── Build naked request (sl=0, tp=0) ──
        request = {
            "action": _TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": float(lot),
            "type": order_type,
            "price": price,
            "sl": 0.0,        # naked — no SL
            "tp": 0.0,        # naked — no TP
            "deviation": deviation,
            "magic": DEMO_MICRO_MAGIC,
            "comment": "TITAN_RAW_PROBE",
            "type_time": 0,   # ORDER_TIME_GTC
            "type_filling": order_filling_ioc,
        }

        print(f"\n  Raw probe request:")
        for k, v in request.items():
            print(f"    {k}: {v}")

        if dry_run:
            print("\n  [DRY RUN] Skipping order_send")
            return {"ok": True, "dry_run": True, "request": request,
                    "account": {"server": server, "login": login}}

        # ── order_check ──
        check_result = mt5.order_check(request)
        check_retcode = _safe(check_result, "retcode", None) if check_result else None
        check_comment = _safe(check_result, "comment", "") if check_result else ""
        print(f"\n  order_check: retcode={check_retcode} comment={check_comment}")
        if check_retcode != 0:
            return {"ok": False,
                    "error": f"order_check failed: retcode={check_retcode} ({check_comment})",
                    "request": request}

        # ── order_send ──
        send_result = mt5.order_send(request)
        if send_result is None:
            last_err = mt5.last_error() if hasattr(mt5, "last_error") else None
            return {"ok": False,
                    "error": f"order_send returned None — last_error={last_err}",
                    "request": request}

        send_retcode = _safe(send_result, "retcode", None)
        print(f"\n  order_send: retcode={send_retcode}")
        if send_retcode != _TRADE_RETCODE_DONE:
            return {"ok": False,
                    "error": f"order_send failed: retcode={send_retcode}",
                    "request": request, "send_result": str(send_result)}

        order_ticket = _safe(send_result, "order")
        deal_ticket = _safe(send_result, "deal")
        print(f"  Order opened: order={order_ticket} deal={deal_ticket}")

        # ── Wait for position to appear ──
        position_ticket = None
        for _ in range(10):
            positions = mt5.positions_get(symbol=symbol) or []
            matching = [p for p in positions
                        if _safe(p, "magic") == DEMO_MICRO_MAGIC]
            if matching:
                pos = matching[0]
                position_ticket = _safe(pos, "ticket")
                break
            time.sleep(0.5)

        if position_ticket is None:
            print("  WARNING: position not found after order_send — may have closed")
        else:
            print(f"  Position found: ticket={position_ticket}")

        # ── Close position immediately ──
        close_tick = mt5.symbol_info_tick(symbol)
        if close_tick and position_ticket:
            if side == "BUY":
                close_price = float(getattr(close_tick, "bid", 0))
                close_type = _ORDER_TYPE_SELL
            else:
                close_price = float(getattr(close_tick, "ask", 0))
                close_type = _ORDER_TYPE_BUY

            close_request = {
                "action": _TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": float(lot),
                "type": close_type,
                "position": int(position_ticket),
                "price": close_price,
                "deviation": deviation,
                "magic": DEMO_MICRO_MAGIC,
                "comment": "TITAN_RAW_PROBE_CLOSE",
                "type_time": 0,
                "type_filling": order_filling_ioc,
            }
            close_result = mt5.order_send(close_request)
            close_retcode = _safe(close_result, "retcode", None) if close_result else None
            print(f"  Close order: retcode={close_retcode}")
            if close_retcode != _TRADE_RETCODE_DONE:
                print(f"  WARNING: close failed — position may still be open!")
        else:
            close_result = None
            close_retcode = None

        # ── Save working profile ──
        profile = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "server": server,
            "login": login,
            "symbol": symbol,
            "side": side,
            "lot": lot,
            "deviation": deviation,
            "type_filling": order_filling_ioc,
            "type_filling_name": "IOC",
            "sl": 0.0,
            "tp": 0.0,
            "sl_tp_mode": "naked_then_sltp_modify",
            "type_time": 0,
            "type_time_name": "ORDER_TIME_GTC",
            "magic": DEMO_MICRO_MAGIC,
            "open_retcode": send_retcode,
            "open_order_ticket": order_ticket,
            "open_deal_ticket": deal_ticket,
            "position_ticket": position_ticket,
            "close_retcode": close_retcode,
            "working_request": request,
            "close_request": close_request if position_ticket else None,
        }
        with open(PROFILE_PATH, "w", encoding="utf-8") as f:
            json.dump(profile, f, indent=2, default=str)
        print(f"\n  ✓ Working profile saved: {PROFILE_PATH}")

        return {
            "ok": True,
            "profile_path": str(PROFILE_PATH),
            "profile": profile,
            "open_retcode": send_retcode,
            "close_retcode": close_retcode,
        }

    finally:
        try:
            mt5.shutdown()
        except Exception:
            pass


def main():
    parser = argparse.ArgumentParser(
        description="TITAN Raw MT5 Probe — send naked IOC demo order, close, save profile")
    parser.add_argument("--symbol", default="XAUUSD")
    parser.add_argument("--side", choices=["BUY", "SELL"], default="BUY")
    parser.add_argument("--lot", type=float, default=0.01)
    parser.add_argument("--deviation", type=int, default=50)
    parser.add_argument("--dry-run", action="store_true",
                        help="Check account/symbol only, don't send order")
    args = parser.parse_args()

    print("=" * 70)
    print("  TITAN XAU AI — Raw MT5 Probe (Sprint 9.9.3.21)")
    print("=" * 70)
    print(f"  Symbol: {args.symbol}")
    print(f"  Side: {args.side}")
    print(f"  Lot: {args.lot}")
    print(f"  Deviation: {args.deviation}")
    print(f"  Dry run: {args.dry_run}")
    print()

    result = probe_raw_mt5(
        symbol=args.symbol, side=args.side,
        lot=args.lot, deviation=args.deviation,
        dry_run=args.dry_run,
    )

    print("\n" + "=" * 70)
    if result["ok"]:
        print("  ✓ RAW PROBE SUCCEEDED")
        if result.get("profile_path"):
            print(f"  Profile: {result['profile_path']}")
    else:
        print(f"  ✗ RAW PROBE FAILED: {result.get('error', 'unknown')}")
    print("=" * 70)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
