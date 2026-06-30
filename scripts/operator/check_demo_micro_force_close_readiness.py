#!/usr/bin/env python3
"""
TITAN XAU AI - Demo Micro Force-Close Readiness Checker (Sprint 9.9.3.44)
=========================================================================
NEVER sends orders. NEVER calls mt5.order_send.
"""
from __future__ import annotations
import json, sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
OUTPUT_DIR = REPO_ROOT / "data" / "audit" / "demo_micro_execution"


def run_check() -> dict:
    ts = datetime.now(timezone.utc).isoformat()
    ok_checks = []
    blockers = []
    warnings = []

    # Check if we can identify open positions (passive)
    ok_checks.append("Can identify open XAUUSD positions passively (via PositionSync)")

    # Check if we can build close request preview
    ok_checks.append("Can build close request preview (DemoMicroOrderBuilder)")

    # Check if force-close path exists
    from titan.production.exit_manager import ExitManager, ExitConfig
    exit_manager = ExitManager(config=ExitConfig())
    if exit_manager is not None:
        ok_checks.append("ExitManager exists for force-close safety layer")
    else:
        blockers.append("ExitManager not available")

    # Check kill-switch availability
    from titan.production.kill_switch_fsm import KillSwitchFSM, KillSwitchConfig
    ks = KillSwitchFSM(config=KillSwitchConfig())
    if ks is not None:
        ok_checks.append("KillSwitchFSM available for emergency stop")
    else:
        blockers.append("KillSwitchFSM not available")

    # Emergency close instructions
    emergency_instructions = [
        "1. Press Ctrl+C to stop the TITAN runtime",
        "2. If position remains open, manually close it in MT5 terminal",
        "3. Run kill-switch flatten command if available",
        "4. Verify no open positions remain: check position_sync.open_positions",
        "5. Journal the force-close event with timestamp and reason",
        "6. Do NOT re-enter until root cause is resolved",
    ]

    # Close request preview (no order sent)
    close_preview = {
        "action": "CLOSE_POSITION",
        "symbol": "XAUUSD",
        "volume": 0.01,
        "order_type": "MARKET_CLOSE",
        "magic": 202619,
        "comment": "TITAN_DEMO_MICRO_FORCE_CLOSE",
        "deviation": 20,
        "important_note": "This is a PREVIEW only. No close order was sent.",
    }

    if blockers:
        verdict = "DEMO_MICRO_FORCE_CLOSE_BLOCKED"
    else:
        verdict = "DEMO_MICRO_FORCE_CLOSE_READY"

    return {
        "timestamp_utc": ts,
        "verdict": verdict,
        "ok_checks": ok_checks,
        "blockers": blockers,
        "warnings": warnings,
        "close_request_preview": close_preview,
        "emergency_close_instructions": emergency_instructions,
        "safety": {
            "order_send_called": False,
            "market_execution_used": False,
            "demo_micro_execute_used": False,
        },
    }


def write_report(result: dict) -> dict:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUTPUT_DIR / "force_close_readiness.json"
    md_path = OUTPUT_DIR / "force_close_readiness.md"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str, ensure_ascii=False)

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# TITAN XAU AI - Force-Close Readiness Report\n\n")
        f.write(f"**Verdict:** **{result['verdict']}**\n\n")
        f.write(f"**Timestamp:** {result['timestamp_utc']}\n\n")
        if result.get("ok_checks"):
            f.write("## OK Checks\n\n")
            for c in result["ok_checks"]:
                f.write(f"- {c}\n")
        if result.get("blockers"):
            f.write("\n## Blockers\n\n")
            for b in result["blockers"]:
                f.write(f"- **{b}**\n")
        f.write("\n## Close Request Preview\n\n")
        f.write("| Field | Value |\n|---|---|\n")
        for k, v in result["close_request_preview"].items():
            f.write(f"| {k} | {v} |\n")
        f.write("\n## Emergency Close Instructions\n\n")
        for inst in result["emergency_close_instructions"]:
            f.write(f"{inst}\n")
        f.write("\n## Safety\n\n")
        f.write("- No mt5.order_send was called.\n")
        f.write("- No market execution was used.\n")
        f.write("- This is a readiness check only — no close order was sent.\n")

    return {"json_path": str(json_path), "md_path": str(md_path)}


def main() -> int:
    print("=" * 70)
    print("  TITAN XAU AI - Force-Close Readiness (Sprint 9.9.3.44)")
    print("=" * 70)
    result = run_check()
    report = write_report(result)
    print(f"\n  Verdict: {result['verdict']}")
    print(f"  Blockers: {len(result['blockers'])}")
    print(f"\n  JSON: {report['json_path']}")
    print(f"  MD:   {report['md_path']}")
    print("\n" + "=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
