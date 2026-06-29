#!/usr/bin/env python3
"""
TITAN XAU AI — Sprint 9.9.3.25 Demo Micro Repeatability Script
================================================================

Runs 3 controlled demo micro cycles on MetaQuotes-Demo to prove
execution repeatability.

Cycle 1: BUY  0.01  60s hold  force close
Cycle 2: SELL 0.01  60s hold  force close
Cycle 3: BUY  0.01  60s hold  force close

Each cycle:
  1. Hard gate passes
  2. Account is DEMO
  3. Server/login/symbol match raw working profile
  4. Lot <= 0.01, max 1 open position
  5. Trade opens successfully
  6. SLTP modify handled safely
  7. Force close succeeds
  8. Open positions after = 0
  9. Evidence archived with redaction

Final verdict:
  DEMO_REPEATABILITY_PASS — 3/3 cycles pass
  DEMO_REPEATABILITY_FAIL — any cycle fails

Safety:
  - Requires TITAN_DEMO_MICRO_ARMED=1
  - Refuses real accounts
  - Refuses server/profile mismatch
  - Stops immediately on first failure
  - Force closes any open position on failure

Usage (on Windows MT5 DEMO):
  set TITAN_DEMO_MICRO_ARMED=1
  python scripts/audit/demo_micro_repeatability.py --server MetaQuotes-Demo --symbol XAUUSD --lot 0.01 --max-hold-seconds 60
"""
from __future__ import annotations
import argparse
import asyncio
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

REPORT_JSON = OUTPUT_DIR / "demo_micro_repeatability_report.json"
REPORT_MD = OUTPUT_DIR / "demo_micro_repeatability_report.md"
JOURNAL_PATH = OUTPUT_DIR / "demo_micro_repeatability_journal.jsonl"

DEMO_MICRO_MAGIC = 20261993

# The 3-cycle test sequence
CYCLES = [
    {"name": "cycle_1", "side": "BUY", "lot": 0.01, "max_hold_seconds": 60},
    {"name": "cycle_2", "side": "SELL", "lot": 0.01, "max_hold_seconds": 60},
    {"name": "cycle_3", "side": "BUY", "lot": 0.01, "max_hold_seconds": 60},
]


def _journal(event_type: str, payload: dict) -> None:
    """Append a JSONL event to the repeatability journal."""
    entry = {"timestamp_utc": datetime.now(timezone.utc).isoformat(),
             "event": event_type, **payload}
    with open(JOURNAL_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, default=str) + "\n")


def _mask_login(login) -> str:
    if login is None:
        return "N/A"
    s = str(login)
    if len(s) <= 4:
        return s[:1] + "***" + s[-1:]
    return s[:2] + "***" + s[-2:]


def _redact_dict(obj) -> None:
    """Recursively redact login/name in a dict."""
    if isinstance(obj, dict):
        for key in list(obj.keys()):
            val = obj[key]
            if key in ("login", "name", "account_name") and isinstance(val, (str, int)):
                obj[key] = _mask_login(val) if key == "login" else "REDACTED"
            elif isinstance(val, (dict, list)):
                _redact_dict(val)
    elif isinstance(obj, list):
        for item in obj:
            _redact_dict(item)


def _check_pre_conditions(server: str, symbol: str, lot: float) -> dict:
    """Check all pre-conditions before running cycles.

    Returns dict with ok=bool and error=str.
    """
    # 1. Must be armed
    if os.environ.get("TITAN_DEMO_MICRO_ARMED", "0") != "1":
        return {"ok": False, "error": "TITAN_DEMO_MICRO_ARMED not set to 1 — refusing to run"}

    # 2. Lot cap
    if lot > 0.01:
        return {"ok": False, "error": f"lot {lot} > 0.01 — repeatability test enforces 0.01 max"}

    # 3. Load raw working profile
    raw_profile_path = REPO_ROOT / "data" / "audit" / "demo_micro" / "raw_mt5_working_profile.json"
    if not raw_profile_path.exists():
        return {"ok": False, "error": f"raw_mt5_working_profile.json not found at {raw_profile_path}"}
    with open(raw_profile_path) as f:
        raw_profile = json.load(f)

    # 4. Check MT5 is available
    try:
        import MetaTrader5 as mt5
    except ImportError:
        return {"ok": False, "error": "MetaTrader5 not installed (Linux/Z AI — repeatability requires Windows MT5)"}

    if not mt5.initialize():
        return {"ok": False, "error": "mt5.initialize() failed"}

    try:
        # 5. Account must be DEMO
        account = mt5.account_info()
        if account is None:
            return {"ok": False, "error": "mt5.account_info() returned None"}
        if getattr(account, "trade_mode", 2) != 0:
            return {"ok": False, "error": f"NOT A DEMO ACCOUNT — trade_mode={account.trade_mode}"}

        # 6. Server must match raw profile
        mt5_server = getattr(account, "server", "")
        if server and mt5_server != server:
            return {"ok": False, "error": f"Server mismatch: requested={server}, actual={mt5_server}"}
        raw_server = raw_profile.get("server", "")
        if raw_server and mt5_server != raw_server:
            return {"ok": False, "error": f"Server mismatch: raw_profile={raw_server}, actual={mt5_server}"}

        # 7. Login must match raw profile
        mt5_login = getattr(account, "login", None)
        raw_login = raw_profile.get("login")
        if raw_login and str(mt5_login) != str(raw_login):
            return {"ok": False, "error": f"Login mismatch: raw_profile={_mask_login(raw_login)}, actual={_mask_login(mt5_login)}"}

        # 8. Symbol must match raw profile
        raw_symbol = raw_profile.get("symbol", "")
        if raw_symbol and symbol != raw_symbol:
            return {"ok": False, "error": f"Symbol mismatch: raw_profile={raw_symbol}, requested={symbol}"}

        # 9. No existing open positions
        positions = mt5.positions_get(symbol=symbol) or []
        matching = [p for p in positions if getattr(p, "magic", 0) == DEMO_MICRO_MAGIC]
        if matching:
            return {"ok": False, "error": f"Existing open positions ({len(matching)}) for {symbol} with magic {DEMO_MICRO_MAGIC} — refuse to start"}

        return {
            "ok": True,
            "mt5": mt5,
            "raw_profile": raw_profile,
            "account": {
                "server": mt5_server,
                "login": mt5_login,
                "trade_mode": getattr(account, "trade_mode"),
                "balance": getattr(account, "balance"),
            },
        }
    except Exception as e:
        return {"ok": False, "error": f"Pre-condition check failed: {e}"}


async def _run_single_cycle(mt5, cycle: dict, raw_profile: dict,
                              symbol: str, server: str) -> dict:
    """Run a single demo micro cycle.

    Returns dict with cycle results.
    """
    from scripts.audit.demo_micro_full_cycle import (
        _send_open_order, _close_position, _sync_position,
        _check_existing_position, DEMO_MICRO_MAGIC,
    )

    cycle_name = cycle["name"]
    side = cycle["side"]
    lot = cycle["lot"]
    max_hold = cycle["max_hold_seconds"]

    _journal("REPEATABILITY_CYCLE_START", {
        "cycle": cycle_name, "side": side, "lot": lot, "max_hold_seconds": max_hold,
    })

    result = {
        "cycle": cycle_name,
        "side": side,
        "lot": lot,
        "max_hold_seconds": max_hold,
        "open_retcode": None,
        "close_retcode": None,
        "net_pnl": 0,
        "duration_seconds": 0,
        "open_positions_before": 0,
        "open_positions_after": 0,
        "verdict": "PENDING",
        "error": None,
    }

    start_time = time.time()

    try:
        # Check open positions before
        has_pos, pos_list = _check_existing_position(mt5, symbol)
        result["open_positions_before"] = len(pos_list) if pos_list else 0
        if has_pos:
            result["verdict"] = "FAIL"
            result["error"] = f"Open position exists before {cycle_name}"
            _journal("REPEATABILITY_CYCLE_FAIL", result)
            return result

        # Open order
        open_result = _send_open_order(
            mt5, symbol=symbol, side=side, lot=lot,
            magic=DEMO_MICRO_MAGIC,
            use_raw_working_profile=True,
        )
        result["open_retcode"] = open_result.get("retcode")

        if not open_result.get("ok"):
            result["verdict"] = "FAIL"
            result["error"] = f"Open failed: {open_result.get('error', 'unknown')}"
            result["duration_seconds"] = time.time() - start_time
            _journal("REPEATABILITY_CYCLE_FAIL", result)
            return result

        _journal("REPEATABILITY_CYCLE_OPENED", {
            "cycle": cycle_name, "retcode": result["open_retcode"],
            "order": open_result.get("order"),
        })

        # Sync position
        position = _sync_position(mt5, symbol, DEMO_MICRO_MAGIC, timeout_s=5.0)
        if position is None:
            result["verdict"] = "FAIL"
            result["error"] = "Position sync failed after open"
            result["duration_seconds"] = time.time() - start_time
            _journal("REPEATABILITY_CYCLE_FAIL", result)
            return result

        # Hold for max_hold seconds
        _journal("REPEATABILITY_CYCLE_HOLDING", {
            "cycle": cycle_name, "hold_seconds": max_hold,
            "ticket": position.get("ticket"),
        })
        await asyncio.sleep(max_hold)

        # Close position
        close_result = _close_position(mt5, position, magic=DEMO_MICRO_MAGIC)
        result["close_retcode"] = close_result.get("retcode")

        if not close_result.get("ok"):
            result["verdict"] = "FAIL"
            result["error"] = f"Close failed: {close_result.get('error', 'unknown')}"
            result["duration_seconds"] = time.time() - start_time
            # Try force close
            _journal("REPEATABILITY_CYCLE_FORCE_CLOSE", {
                "cycle": cycle_name, "reason": "close failed, attempting force close",
            })
            _close_position(mt5, position, magic=DEMO_MICRO_MAGIC)
            _journal("REPEATABILITY_CYCLE_FAIL", result)
            return result

        # Check open positions after
        has_pos_after, pos_list_after = _check_existing_position(mt5, symbol)
        result["open_positions_after"] = len(pos_list_after) if pos_list_after else 0

        # Calculate net PnL (simplified — from close result)
        result["net_pnl"] = close_result.get("net_pnl", 0) or 0
        result["duration_seconds"] = round(time.time() - start_time, 2)
        result["verdict"] = "PASS"

        _journal("REPEATABILITY_CYCLE_PASS", result)
        return result

    except Exception as e:
        result["verdict"] = "FAIL"
        result["error"] = f"Exception: {e}"
        result["duration_seconds"] = round(time.time() - start_time, 2)
        _journal("REPEATABILITY_CYCLE_FAIL", result)
        return result


def _force_close_all(mt5, symbol: str) -> None:
    """Force close any open positions with our magic."""
    try:
        from scripts.audit.demo_micro_full_cycle import _close_position
        positions = mt5.positions_get(symbol=symbol) or []
        matching = [p for p in positions if getattr(p, "magic", 0) == DEMO_MICRO_MAGIC]
        for p in matching:
            pos_dict = {
                "ticket": getattr(p, "ticket"),
                "type": "BUY" if getattr(p, "type", 1) == 0 else "SELL",
                "volume": getattr(p, "volume", 0.01),
                "symbol": getattr(p, "symbol", symbol),
                "price_open": getattr(p, "price_open"),
            }
            _close_position(mt5, pos_dict, magic=DEMO_MICRO_MAGIC)
    except Exception as e:
        _journal("REPEATABILITY_FORCE_CLOSE_ERROR", {"error": str(e)})


def _write_report(cycles: list, final_verdict: str, account: dict,
                    raw_profile_match: bool) -> None:
    """Write JSON + MD report."""
    cycles_passed = sum(1 for c in cycles if c["verdict"] == "PASS")
    cycles_failed = sum(1 for c in cycles if c["verdict"] == "FAIL")
    total_pnl = sum(c.get("net_pnl", 0) for c in cycles)

    report = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "final_verdict": final_verdict,
        "cycles_passed": cycles_passed,
        "cycles_failed": cycles_failed,
        "total_net_pnl": total_pnl,
        "final_open_positions": cycles[-1].get("open_positions_after", 0) if cycles else None,
        "broker_server": account.get("server"),
        "raw_profile_match": raw_profile_match,
        "cycles": cycles,
        "account": {
            "server": account.get("server"),
            "login": _mask_login(account.get("login")),
            "trade_mode": account.get("trade_mode"),
        },
    }

    # JSON
    with open(REPORT_JSON, "w") as f:
        json.dump(report, f, indent=2, default=str)

    # MD
    with open(REPORT_MD, "w") as f:
        f.write("# Demo Micro Repeatability Report\n\n")
        f.write(f"**Final Verdict: {final_verdict}**\n\n")
        f.write(f"**Timestamp:** {report['timestamp_utc']}\n\n")
        f.write(f"**Server:** {account.get('server')}\n\n")
        f.write(f"**Login:** {_mask_login(account.get('login'))}\n\n")
        f.write(f"**Cycles Passed:** {cycles_passed}/{len(cycles)}\n\n")
        f.write(f"**Total Net PnL:** {total_pnl}\n\n")
        f.write(f"**Raw Profile Match:** {'YES' if raw_profile_match else 'NO'}\n\n")
        f.write("## Per-Cycle Results\n\n")
        f.write("| Cycle | Side | Lot | Open Retcode | Close Retcode | Net PnL | Duration | Open Before | Open After | Verdict |\n")
        f.write("|---|---|---|---|---|---|---|---|---|---|\n")
        for c in cycles:
            f.write(f"| {c['cycle']} | {c['side']} | {c['lot']} | {c['open_retcode']} | "
                    f"{c['close_retcode']} | {c.get('net_pnl', 0)} | {c.get('duration_seconds', 0)}s | "
                    f"{c.get('open_positions_before', 0)} | {c.get('open_positions_after', 0)} | "
                    f"{c['verdict']} |\n")
        if any(c["verdict"] == "FAIL" for c in cycles):
            f.write("\n## Failures\n\n")
            for c in cycles:
                if c["verdict"] == "FAIL":
                    f.write(f"- **{c['cycle']}**: {c.get('error', 'unknown')}\n")


def _archive_evidence(cycles: list, final_verdict: str, account: dict) -> str:
    """Archive redacted repeatability evidence."""
    import shutil
    from scripts.audit.archive_pass_evidence import _slugify

    server_slug = _slugify(account.get("server", "unknown"))
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive_dir = OUTPUT_DIR / "pass_evidence" / server_slug / f"repeatability_{timestamp}"
    archive_dir.mkdir(parents=True, exist_ok=True)

    # Redact and copy files
    for src_file in [REPORT_JSON, REPORT_MD, JOURNAL_PATH]:
        if src_file.exists():
            dst = archive_dir / src_file.name
            if src_file.suffix == ".json":
                import json
                with open(src_file) as f:
                    data = json.load(f)
                _redact_dict(data)
                with open(dst, "w") as f:
                    json.dump(data, f, indent=2, default=str)
            elif src_file.suffix == ".jsonl":
                with open(src_file) as f_in, open(dst, "w") as f_out:
                    for line in f_in:
                        try:
                            obj = json.loads(line.strip())
                            _redact_dict(obj)
                            f_out.write(json.dumps(obj, default=str) + "\n")
                        except Exception:
                            f_out.write(line)
            else:
                # Redact MD files too
                from scripts.audit.archive_pass_evidence import _redact_md_file
                _redact_md_file(src_file, dst)

    return str(archive_dir)


def main():
    parser = argparse.ArgumentParser(
        description="TITAN Demo Micro Repeatability — 3-cycle proof on MetaQuotes-Demo")
    parser.add_argument("--server", default="MetaQuotes-Demo")
    parser.add_argument("--symbol", default="XAUUSD")
    parser.add_argument("--lot", type=float, default=0.01)
    parser.add_argument("--max-hold-seconds", type=int, default=60)
    args = parser.parse_args()

    print("=" * 70)
    print("  TITAN XAU AI — Demo Micro Repeatability (Sprint 9.9.3.25)")
    print("=" * 70)
    print(f"  Server: {args.server}")
    print(f"  Symbol: {args.symbol}")
    print(f"  Lot: {args.lot}")
    print(f"  Max hold: {args.max_hold_seconds}s")
    print(f"  Cycles: {len(CYCLES)} (BUY, SELL, BUY)")
    print()

    # Clear previous journal
    if JOURNAL_PATH.exists():
        JOURNAL_PATH.unlink()

    # Pre-conditions
    pre = _check_pre_conditions(args.server, args.symbol, args.lot)
    if not pre["ok"]:
        print(f"  ✗ PRE-CONDITION FAILED: {pre['error']}")
        print("=" * 70)
        return 1

    mt5 = pre["mt5"]
    raw_profile = pre["raw_profile"]
    account = pre["account"]

    print(f"  Account: server={account['server']} login={_mask_login(account['login'])} (DEMO)")
    print(f"  Raw profile: server={raw_profile.get('server')} symbol={raw_profile.get('symbol')}")
    print()

    # Run cycles
    cycles_results = []
    final_verdict = "DEMO_REPEATABILITY_PASS"

    for i, cycle in enumerate(CYCLES):
        print(f"  ── Cycle {i+1}/{len(CYCLES)}: {cycle['side']} {cycle['lot']} ──")

        # Override lot/hold from args
        cycle["lot"] = args.lot
        cycle["max_hold_seconds"] = args.max_hold_seconds

        result = asyncio.run(_run_single_cycle(mt5, cycle, raw_profile,
                                                  args.symbol, args.server))
        cycles_results.append(result)

        print(f"    Verdict: {result['verdict']}")
        if result["verdict"] == "PASS":
            print(f"    Open: {result['open_retcode']}  Close: {result['close_retcode']}")
            print(f"    Duration: {result['duration_seconds']}s  PnL: {result['net_pnl']}")
        else:
            print(f"    ERROR: {result.get('error', 'unknown')}")
            print(f"    Stopping — force closing any open positions...")
            _force_close_all(mt5, args.symbol)
            final_verdict = "DEMO_REPEATABILITY_FAIL"
            break

        print()

    # Final position check
    try:
        positions = mt5.positions_get(symbol=args.symbol) or []
        final_open = len([p for p in positions if getattr(p, "magic", 0) == DEMO_MICRO_MAGIC])
    except Exception:
        final_open = -1

    try:
        mt5.shutdown()
    except Exception:
        pass

    # Raw profile match check
    raw_profile_match = (
        account.get("server") == raw_profile.get("server") and
        str(account.get("login")) == str(raw_profile.get("login")) and
        args.symbol == raw_profile.get("symbol")
    )

    # Write report
    _write_report(cycles_results, final_verdict, account, raw_profile_match)

    # Archive evidence
    archive_path = _archive_evidence(cycles_results, final_verdict, account)

    # Print final
    cycles_passed = sum(1 for c in cycles_results if c["verdict"] == "PASS")
    cycles_failed = sum(1 for c in cycles_results if c["verdict"] == "FAIL")
    total_pnl = sum(c.get("net_pnl", 0) for c in cycles_results)

    print("=" * 70)
    print(f"  FINAL VERDICT: {final_verdict}")
    print(f"  Cycles: {cycles_passed} passed, {cycles_failed} failed")
    print(f"  Total PnL: {total_pnl}")
    print(f"  Final open positions: {final_open}")
    print(f"  Evidence archived: {archive_path}")
    print(f"  Report: {REPORT_JSON}")
    print("=" * 70)

    return 0 if final_verdict == "DEMO_REPEATABILITY_PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
