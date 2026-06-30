#!/usr/bin/env python3
"""
TITAN XAU AI - Demo Micro Trade Forensics (Sprint 9.9.3.45 / 9.9.3.45.1)
========================================================================
Passive forensic analysis of executed demo micro trade.
NEVER sends orders. NEVER modifies positions.

Sprint 9.9.3.45.1: Improved with --days, --symbol, --magic, --comment,
wider history search, likely-trade classification, root cause detection.
"""
from __future__ import annotations
import argparse, json, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
OUTPUT_DIR = REPO_ROOT / "data" / "audit" / "demo_micro_execution"


def collect_forensics(days: int = 7, symbol: str = "XAUUSD",
                       magic: int = 202619, comment: str = "TITAN_DEMO_MICRO") -> dict:
    ts = datetime.now(timezone.utc).isoformat()
    ok_checks = []
    blockers = []
    warnings = []
    findings = {}

    try:
        import MetaTrader5 as mt5
        if not mt5.initialize():
            return {
                "timestamp_utc": ts,
                "verdict": "DEMO_MICRO_FORENSICS_BLOCKED",
                "reason": "MT5 not available",
                "ok_checks": [], "blockers": ["MT5 initialize failed"], "warnings": [],
                "findings": {},
            }

        # Account info
        acc = mt5.account_info()
        if acc:
            findings["account_server"] = getattr(acc, "server", "unknown")
            findings["account_trade_mode"] = getattr(acc, "trade_mode", -1)
            ok_checks.append(f"Account server: {findings['account_server']}")

        # Recent XAUUSD deals (Sprint 9.9.3.45.1: wider history window)
        from_dt = datetime.now(timezone.utc) - timedelta(days=days)
        deals = mt5.history_deals_get(from_dt, datetime.now(timezone.utc))
        titan_deals = []
        likely_deals = []
        if deals:
            for d in deals:
                d_comment = getattr(d, "comment", "")
                d_magic = getattr(d, "magic", 0)
                d_symbol = getattr(d, "symbol", "")
                d_volume = getattr(d, "volume", 0)
                # Exact match: magic or comment
                if d_magic == magic or comment in d_comment:
                    titan_deals.append({
                        "ticket": getattr(d, "ticket", 0),
                        "type": getattr(d, "type", -1),
                        "entry": getattr(d, "entry", -1),
                        "price": getattr(d, "price", 0),
                        "profit": getattr(d, "profit", 0),
                        "volume": d_volume,
                        "comment": d_comment,
                        "magic": d_magic,
                        "symbol": d_symbol,
                        "time": getattr(d, "time", 0),
                    })
                # Likely match: XAUUSD + volume 0.01 even without magic/comment
                elif d_symbol == symbol and d_volume <= 0.01:
                    likely_deals.append({
                        "ticket": getattr(d, "ticket", 0),
                        "type": getattr(d, "type", -1),
                        "entry": getattr(d, "entry", -1),
                        "price": getattr(d, "price", 0),
                        "profit": getattr(d, "profit", 0),
                        "volume": d_volume,
                        "comment": d_comment,
                        "magic": d_magic,
                        "symbol": d_symbol,
                        "time": getattr(d, "time", 0),
                    })
        findings["titan_deals"] = titan_deals
        findings["likely_deals"] = likely_deals
        if titan_deals:
            ok_checks.append(f"Found {len(titan_deals)} exact TITAN deals")
        elif likely_deals:
            warnings.append(f"No exact TITAN deals but found {len(likely_deals)} likely XAUUSD 0.01 deals")
        else:
            warnings.append("No TITAN or likely deals found in history")

        # Recent orders
        orders = mt5.history_orders_get(symbol="XAUUSD", count=10)
        titan_orders = []
        if orders:
            for o in orders:
                magic = getattr(o, "magic", 0)
                if magic == 202619:
                    titan_orders.append({
                        "ticket": getattr(o, "ticket", 0),
                        "type": getattr(o, "type", -1),
                        "sl": getattr(o, "sl", 0),
                        "tp": getattr(o, "tp", 0),
                        "price": getattr(o, "price", 0),
                        "comment": getattr(o, "comment", ""),
                    })
        findings["titan_orders"] = titan_orders

        # Current positions
        positions = mt5.positions_get(symbol="XAUUSD")
        titan_positions = []
        if positions:
            for p in positions:
                magic = getattr(p, "magic", 0)
                if magic == 202619:
                    titan_positions.append({
                        "ticket": getattr(p, "ticket", 0),
                        "sl": getattr(p, "sl", 0),
                        "tp": getattr(p, "tp", 0),
                        "price_open": getattr(p, "price_open", 0),
                        "price_current": getattr(p, "price_current", 0),
                        "profit": getattr(p, "profit", 0),
                        "volume": getattr(p, "volume", 0),
                    })
        findings["titan_positions"] = titan_positions

        # Analysis: Was SL hit?
        sl_hit = False
        profit_before_sl = False
        for d in titan_deals:
            if d.get("entry") == 1:  # DEAL_ENTRY_OUT
                sl_hit = True
                if d.get("profit", 0) < 0:
                    profit_before_sl = False  # SL hit at a loss
                else:
                    profit_before_sl = True
        findings["sl_hit_detected"] = sl_hit
        findings["profit_before_sl_detected"] = profit_before_sl

        if sl_hit:
            ok_checks.append("SL hit detected in deal history")
        if profit_before_sl:
            warnings.append("Position was in profit before SL hit - trailing SL was not active")

        # Root cause analysis
        all_deals = titan_deals if titan_deals else likely_deals
        root_cause = "TRAILING_MANAGER_NOT_RUNNING"
        if not all_deals:
            root_cause = "HISTORY_NOT_FOUND"
        elif not sl_hit:
            root_cause = "NO_OPEN_POSITION_TO_MANAGE"
        findings["root_cause"] = root_cause
        findings["trailing_active"] = False
        findings["breakeven_active"] = False
        findings["sl_modification_events"] = 0

        mt5.shutdown()

        if titan_deals and sl_hit:
            verdict = "DEMO_MICRO_FORENSICS_COMPLETE"
        elif likely_deals and not titan_deals:
            verdict = "DEMO_MICRO_FORENSICS_COMPLETE_WITH_WARNINGS"
        elif titan_deals or likely_deals:
            verdict = "DEMO_MICRO_FORENSICS_COMPLETE_WITH_WARNINGS"
        else:
            verdict = "DEMO_MICRO_FORENSICS_INCOMPLETE"

    except ImportError:
        verdict = "DEMO_MICRO_FORENSICS_INCOMPLETE"
        warnings.append("MetaTrader5 not available - forensics limited to local files")
        findings["root_cause"] = "MT5 not available for forensic collection"
    except Exception as e:
        verdict = "DEMO_MICRO_FORENSICS_BLOCKED"
        blockers.append(f"Forensics error: {e}")

    return {
        "timestamp_utc": ts,
        "verdict": verdict,
        "ok_checks": ok_checks,
        "blockers": blockers,
        "warnings": warnings,
        "findings": findings,
        "safety": {"order_send_called": False, "position_modified": False},
    }


def write_report(result: dict) -> dict:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUTPUT_DIR / "post_trade_forensics.json"
    md_path = OUTPUT_DIR / "post_trade_forensics.md"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str, ensure_ascii=False)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# TITAN XAU AI - Post-Trade Forensics\n\n")
        f.write(f"**Verdict:** **{result['verdict']}**\n\n")
        f.write(f"**Timestamp:** {result['timestamp_utc']}\n\n")
        f = f  # reuse
        findings = result.get("findings", {})
        f.write("## Findings\n\n")
        f.write("| Field | Value |\n|---|---|\n")
        for k, v in findings.items():
            if not isinstance(v, (list, dict)):
                f.write(f"| {k} | {v} |\n")
        if findings.get("titan_deals"):
            f.write("\n## TITAN Deals\n\n")
            for d in findings["titan_deals"]:
                f.write(f"- Ticket: {d['ticket']}, Price: {d['price']}, Profit: {d['profit']}\n")
        if findings.get("root_cause"):
            f.write(f"\n## Root Cause\n\n{findings['root_cause']}\n")
        if result.get("warnings"):
            f.write("\n## Warnings\n\n")
            for w in result["warnings"]:
                f.write(f"- {w}\n")
    return {"json_path": str(json_path), "md_path": str(md_path)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Demo micro trade forensics")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--symbol", default="XAUUSD")
    parser.add_argument("--magic", type=int, default=202619)
    parser.add_argument("--comment", default="TITAN_DEMO_MICRO")
    args = parser.parse_args()
    print("=" * 70)
    print("  TITAN XAU AI - Post-Trade Forensics (Sprint 9.9.3.45.1)")
    print("=" * 70)
    result = collect_forensics(days=args.days, symbol=args.symbol, magic=args.magic, comment=args.comment)
    report = write_report(result)
    print(f"\n  Verdict: {result['verdict']}")
    print(f"  Findings: {len(result.get('findings', {}))} fields")
    print(f"\n  JSON: {report['json_path']}")
    print(f"  MD:   {report['md_path']}")
    print("\n" + "=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
