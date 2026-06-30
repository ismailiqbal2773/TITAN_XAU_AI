#!/usr/bin/env python3
"""
TITAN XAU AI - MT5 History Diagnostic (Sprint 9.9.3.45.1)
==========================================================
Passive MT5 history access diagnostic. NEVER sends orders.
"""
from __future__ import annotations
import argparse, json, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
OUTPUT_DIR = REPO_ROOT / "data" / "audit" / "demo_micro_execution"


def run_diagnostic(days: int = 7, symbol: str = "XAUUSD") -> dict:
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
                "verdict": "DIAGNOSTIC_BLOCKED",
                "reason": "MT5 initialize failed",
                "ok_checks": [], "blockers": ["MT5 initialize failed"], "warnings": [],
                "findings": {},
            }
        ok_checks.append("MT5 initialize succeeded")

        acc = mt5.account_info()
        if acc:
            findings["server"] = getattr(acc, "server", "unknown")
            findings["trade_mode"] = getattr(acc, "trade_mode", -1)
            ok_checks.append(f"Account server: {findings['server']}")

        # History orders
        from_dt = datetime.now(timezone.utc) - timedelta(days=days)
        orders = mt5.history_orders_get(from_dt, datetime.now(timezone.utc))
        if orders is None:
            warnings.append("history_orders_get returned None")
            findings["total_orders"] = 0
        else:
            findings["total_orders"] = len(orders)
            xauusd_orders = [o for o in orders if getattr(o, "symbol", "") == symbol]
            findings[f"{symbol}_orders"] = len(xauusd_orders)
            ok_checks.append(f"Total orders: {len(orders)}, {symbol}: {len(xauusd_orders)}")

        # History deals
        deals = mt5.history_deals_get(from_dt, datetime.now(timezone.utc))
        if deals is None:
            warnings.append("history_deals_get returned None")
            findings["total_deals"] = 0
        else:
            findings["total_deals"] = len(deals)
            xauusd_deals = [d for d in deals if getattr(d, "symbol", "") == symbol]
            findings[f"{symbol}_deals"] = len(xauusd_deals)
            ok_checks.append(f"Total deals: {len(deals)}, {symbol}: {len(xauusd_deals)}")
            # Check magic/comment presence
            magic_count = sum(1 for d in xauusd_deals if getattr(d, "magic", 0) == 202619)
            comment_count = sum(1 for d in xauusd_deals if "TITAN" in getattr(d, "comment", ""))
            findings["magic_202619_deals"] = magic_count
            findings["titan_comment_deals"] = comment_count

        mt5.shutdown()
        verdict = "DIAGNOSTIC_COMPLETE"
    except ImportError:
        verdict = "DIAGNOSTIC_BLOCKED"
        blockers.append("MetaTrader5 not available")
        warnings.append("Run on Windows with MT5 installed")
    except Exception as e:
        verdict = "DIAGNOSTIC_BLOCKED"
        blockers.append(f"Error: {e}")

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
    json_path = OUTPUT_DIR / "mt5_history_diagnostic.json"
    md_path = OUTPUT_DIR / "mt5_history_diagnostic.md"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str, ensure_ascii=False)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# TITAN XAU AI - MT5 History Diagnostic\n\n")
        f.write(f"**Verdict:** **{result['verdict']}**\n\n")
        f.write(f"**Timestamp:** {result['timestamp_utc']}\n\n")
        f.write("## Findings\n\n")
        f.write("| Field | Value |\n|---|---|\n")
        for k, v in result.get("findings", {}).items():
            f.write(f"| {k} | {v} |\n")
        if result.get("ok_checks"):
            f.write("\n## OK Checks\n\n")
            for c in result["ok_checks"]:
                f.write(f"- {c}\n")
        if result.get("warnings"):
            f.write("\n## Warnings\n\n")
            for w in result["warnings"]:
                f.write(f"- {w}\n")
    return {"json_path": str(json_path), "md_path": str(md_path)}


def main() -> int:
    parser = argparse.ArgumentParser(description="MT5 history diagnostic")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--symbol", default="XAUUSD")
    args = parser.parse_args()
    print("=" * 70)
    print("  TITAN XAU AI - MT5 History Diagnostic (Sprint 9.9.3.45.1)")
    print("=" * 70)
    result = run_diagnostic(args.days, args.symbol)
    report = write_report(result)
    print(f"\n  Verdict: {result['verdict']}")
    print(f"\n  JSON: {report['json_path']}")
    print(f"  MD:   {report['md_path']}")
    print("\n" + "=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
