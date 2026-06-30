#!/usr/bin/env python3
"""
TITAN XAU AI - Trailing Readiness Audit (Sprint 9.9.3.45)
==========================================================
NEVER sends orders. NEVER imports MetaTrader5.
"""
from __future__ import annotations
import json, sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
OUTPUT_DIR = REPO_ROOT / "data" / "audit" / "demo_micro_execution"


def run_audit() -> dict:
    ts = datetime.now(timezone.utc).isoformat()
    ok_checks = []
    blockers = []
    warnings = []

    # Check position manager exists
    try:
        from titan.production.demo_micro_position_manager import DemoMicroPositionManager
        ok_checks.append("DemoMicroPositionManager exists")
    except ImportError:
        blockers.append("DemoMicroPositionManager missing")

    # Check SL modify builder exists
    try:
        from titan.production.demo_micro_sl_modify_builder import DemoMicroSLModifyBuilder
        ok_checks.append("DemoMicroSLModifyBuilder exists")
    except ImportError:
        blockers.append("DemoMicroSLModifyBuilder missing")

    # Check breakeven logic
    mgr = DemoMicroPositionManager()
    if hasattr(mgr, "breakeven_trigger"):
        ok_checks.append(f"Breakeven logic exists (trigger={mgr.breakeven_trigger})")
    else:
        blockers.append("Breakeven logic missing")

    # Check trailing logic
    if hasattr(mgr, "trailing_trigger"):
        ok_checks.append(f"Trailing logic exists (trigger={mgr.trailing_trigger})")
    else:
        blockers.append("Trailing logic missing")

    # Check profit lock logic
    if hasattr(mgr, "profit_lock_trigger"):
        ok_checks.append(f"Profit lock logic exists (trigger={mgr.profit_lock_trigger})")
    else:
        blockers.append("Profit lock logic missing")

    # Verify manager only moves SL favorably
    rec = mgr.evaluate(direction="BUY", entry_price=2000.0, current_price=2003.0,
                       current_sl=1990.0, current_tp=2010.0)
    if rec.new_sl >= rec.current_sl:
        ok_checks.append("BUY SL only moves up (favorable)")
    else:
        blockers.append("BUY SL moved down (unfavorable)")

    rec_sell = mgr.evaluate(direction="SELL", entry_price=2000.0, current_price=1997.0,
                            current_sl=2010.0, current_tp=1990.0)
    if rec_sell.new_sl <= rec_sell.current_sl:
        ok_checks.append("SELL SL only moves down (favorable)")
    else:
        blockers.append("SELL SL moved up (unfavorable)")

    # Verify TP preserved
    if rec.tp == 2010.0 and rec_sell.tp == 1990.0:
        ok_checks.append("TP preserved in recommendations")
    else:
        blockers.append("TP not preserved")

    # Check manage script exists
    manage_path = REPO_ROOT / "scripts" / "operator" / "manage_demo_micro_position.py"
    if manage_path.exists():
        ok_checks.append("Manage demo micro position script exists")
    else:
        warnings.append("Manage script not found")

    if blockers:
        verdict = "TRAILING_BLOCKED"
    elif warnings:
        verdict = "TRAILING_READY_WITH_WARNINGS"
    else:
        verdict = "TRAILING_READY"

    return {
        "timestamp_utc": ts,
        "verdict": verdict,
        "ok_checks": ok_checks,
        "blockers": blockers,
        "warnings": warnings,
    }


def write_report(result: dict) -> dict:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUTPUT_DIR / "trailing_readiness_audit.json"
    md_path = OUTPUT_DIR / "trailing_readiness_audit.md"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str, ensure_ascii=False)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# TITAN XAU AI - Trailing Readiness Audit\n\n")
        f.write(f"**Verdict:** **{result['verdict']}**\n\n")
        if result.get("ok_checks"):
            f.write("## OK Checks\n\n")
            for c in result["ok_checks"]:
                f.write(f"- {c}\n")
        if result.get("warnings"):
            f.write("\n## Warnings\n\n")
            for w in result["warnings"]:
                f.write(f"- {w}\n")
        if result.get("blockers"):
            f.write("\n## Blockers\n\n")
            for b in result["blockers"]:
                f.write(f"- **{b}**\n")
    return {"json_path": str(json_path), "md_path": str(md_path)}


def main() -> int:
    print("=" * 70)
    print("  TITAN XAU AI - Trailing Readiness Audit (Sprint 9.9.3.45)")
    print("=" * 70)
    result = run_audit()
    report = write_report(result)
    print(f"\n  Verdict: {result['verdict']}")
    print(f"  Blockers: {len(result['blockers'])}")
    print(f"\n  JSON: {report['json_path']}")
    print(f"  MD:   {report['md_path']}")
    print("\n" + "=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
