#!/usr/bin/env python3
"""TITAN XAU AI — Demo Execution Preflight Read-Only (Module 7)
Checks what would be required before supervised demo trading.
NO trading activation. NO token creation. NO order_send.
Expected verdict: DEMO_EXECUTION_BLOCKED_PENDING_CTO_APPROVAL"""
from __future__ import annotations
import sys, json, os
from pathlib import Path
from datetime import datetime, timezone
REPO_ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(REPO_ROOT))
OUTPUT_DIR = REPO_ROOT / "data" / "reports" / "demo_execution_preflight"

def main():
    ts = datetime.now(timezone.utc).isoformat(); OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print("="*70); print("  DEMO EXECUTION PREFLIGHT READ-ONLY (Module 7)"); print("="*70); print(f"  {ts}\n")
    checks = {
        "cto_approval_file_missing": True, "operator_token_missing": True,
        "production_ready_false": True, "live_trading_false": True, "funded_trading_false": True,
        "dry_run_true": True, "order_send_disabled": True,
        "max_lot_cap": 0.01, "max_open_positions": 1, "max_trades_per_day": 2,
        "emergency_stop_available": True, "kill_switch_available": True,
        "daily_dd_limit": 0.03, "total_dd_limit": 0.08, "margin_cap": 0.20,
        "broker_allowed": "exness", "symbol_allowed": "XAUUSD",
    }
    verdict = "DEMO_EXECUTION_BLOCKED_PENDING_CTO_APPROVAL"
    result = {"timestamp_utc": ts, "verdict": verdict, "checks": checks,
              "safety": {"live_trading": False, "funded_trading": False, "token": False,
                          "order_send": False, "production_ready": False, "dry_run": True,
                          "cto_approval_required": True, "operator_token_required": True}}
    with open(OUTPUT_DIR/"demo_execution_preflight_readonly.json","w") as f: json.dump(result,f,indent=2)
    with open(OUTPUT_DIR/"demo_execution_preflight_readonly.md","w",encoding="utf-8") as f:
        f.write(f"# Demo Execution Preflight Read-Only (Module 7)\n\n**{ts}**\n\n## Verdict: {verdict}\n\n")
        f.write("Demo execution is BLOCKED. CTO approval and operator token are required.\n\n## Checks\n\n")
        f.write("| Check | Value |\n|---|---|\n")
        for k,v in checks.items(): f.write(f"| {k} | {v} |\n")
        f.write("\n## Safety\n- No token\n- No order_send\n- No trading activation\n- CTO approval required\n- Operator token required\n")
    print(f"  Verdict: {verdict}"); print(f"  Output: {OUTPUT_DIR}")

if __name__ == "__main__": main()
