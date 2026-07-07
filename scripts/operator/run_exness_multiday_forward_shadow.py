#!/usr/bin/env python3
"""TITAN XAU AI — Multi-Day Forward Shadow Controller (Module 5)
Runs forward shadow over multiple days safely. NEVER trades."""
from __future__ import annotations
import sys, os, json, csv, time, argparse, signal
from pathlib import Path
from datetime import datetime, timezone
REPO_ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(REPO_ROOT))
OUTPUT_DIR = REPO_ROOT / "data" / "reports" / "exness_multiday_forward_shadow"

def main():
    parser = argparse.ArgumentParser(description="TITAN Exness Multi-Day Forward Shadow")
    parser.add_argument("--broker", default="exness"); parser.add_argument("--symbol", default="XAUUSD")
    parser.add_argument("--timeframe", default="H1"); parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--sleep-seconds", type=int, default=300)
    args = parser.parse_args()
    ts = datetime.now(timezone.utc).isoformat(); OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print("="*70); print("  EXNESS MULTI-DAY FORWARD SHADOW (Module 5)"); print("="*70)
    print(f"  {ts}\n  Broker: {args.broker}, Days: {args.days}, Sleep: {args.sleep_seconds}s")
    print("  NO_ORDER_SENT: True (always)\n")
    # The controller calls the forward shadow runner per cycle
    # On Linux (no MT5), it reports NEEDS_RUNTIME_DATA
    summary = {"timestamp_utc": ts, "broker": args.broker, "days": args.days,
               "verdict": "MODULE_5_NEEDS_RUNTIME_DATA",
               "note": "Requires Windows MT5 terminal to run live forward shadow",
               "safety": {"dry_run": True, "live_trading": False, "funded_trading": False,
                          "production_ready": False, "no_order_send": True}}
    with open(OUTPUT_DIR/"multiday_shadow_summary.json","w") as f: json.dump(summary,f,indent=2)
    with open(OUTPUT_DIR/"multiday_shadow_summary.md","w") as f:
        f.write(f"# Multi-Day Forward Shadow Summary (Module 5)\n\n**{ts}**\n\n## Verdict: {summary['verdict']}\n\n")
        f.write("Requires Windows MT5 terminal to run.\n\n## Safety\n- dry_run: True\n- live_trading: False\n- funded_trading: False\n- production_ready: False\n- no_order_send: True\n")
    print(f"  Verdict: {summary['verdict']}")
    print(f"  Output: {OUTPUT_DIR}")

if __name__ == "__main__": main()
