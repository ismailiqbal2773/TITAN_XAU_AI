#!/usr/bin/env python3
"""TITAN XAU AI — MT5 Exness Account Safety Audit (Module 1)
=============================================================
Standalone audit script that uses mt5_safe_connector to verify
MT5 account safety. Can run on Windows with MT5 installed.

NEVER sends orders. NEVER creates tokens. NEVER trades.
"""
from __future__ import annotations
import sys, os, json
from pathlib import Path
from datetime import datetime, timezone

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

OUTPUT_DIR = REPO_ROOT / "data" / "reports" / "exness_forward_shadow"


def main():
    from scripts.operator.mt5_safe_connector import safe_connect_and_audit

    ts = datetime.now(timezone.utc).isoformat()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("  MT5 EXNESS ACCOUNT SAFETY AUDIT (Module 1)")
    print("=" * 70)
    print(f"  Timestamp: {ts}\n")

    result = safe_connect_and_audit()

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

    with open(OUTPUT_DIR / "mt5_account_safety_audit.json", "w") as f:
        json.dump(audit, f, indent=2, default=str)

    with open(OUTPUT_DIR / "mt5_account_safety_audit.md", "w") as f:
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
        if result.error:
            f.write(f"\n## Error: {result.error}\n")
        f.write("\n## Safety\n\n- no_order_send: True\n- no_token: True\n")
        f.write("- no_live_trading: True\n- no_funded_trading: True\n")
        f.write("- production_ready: False\n- dry_run: True\n")

    print(f"  Verdict: {result.verdict}")
    print(f"  Output: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
