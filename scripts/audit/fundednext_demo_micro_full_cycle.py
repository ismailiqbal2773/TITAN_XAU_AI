"""
TITAN XAU AI — Sprint 9.9 FundedNext Demo Micro Full-Cycle Harness
===================================================================

Two modes:
  DRY_ARM_CHECK_ONLY — checks gates, no order, safe to run anywhere
  DEMO_MICRO_EXECUTE — operator-only, requires arm token + DEMO account

Z AI must NEVER run DEMO_MICRO_EXECUTE.
"""
from __future__ import annotations
import argparse, asyncio, json, os, sys, time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from scripts.audit.demo_micro_hard_gate import evaluate as hard_gate_evaluate
from scripts.audit.demo_micro_config import load_demo_micro_config
from titan.production.trade_journal import TradeJournal

OUTPUT_DIR = REPO_ROOT / "data" / "audit" / "demo_micro"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def parse_args():
    p = argparse.ArgumentParser(description="FundedNext Demo Micro Full-Cycle")
    p.add_argument("--mode", choices=["DRY_ARM_CHECK_ONLY", "DEMO_MICRO_EXECUTE"],
                   default="DRY_ARM_CHECK_ONLY")
    p.add_argument("--max-trades", type=int, default=1)
    p.add_argument("--max-duration-minutes", type=int, default=240)
    p.add_argument("--symbol", type=str, default="XAUUSD")
    p.add_argument("--lot", type=float, default=0.01)
    return p.parse_args()


async def run(args):
    print("=" * 78)
    print("  TITAN XAU AI — Sprint 9.9 FundedNext Demo Micro Full-Cycle Harness")
    print("=" * 78)
    print(f"  Mode: {args.mode}")
    print(f"  Max trades: {args.max_trades}")
    print(f"  Max duration: {args.max_duration_minutes} min")
    print(f"  Symbol: {args.symbol}")
    print(f"  Lot: {args.lot}")

    # ── Hard gate ──
    print("\n── Running hard gate ──")
    gate = hard_gate_evaluate()
    for k, v in gate["checks"].items():
        print(f"  [{'✓' if v else '✗'}] {k}: {v}")
    print(f"\n  Gate verdict: {gate['verdict']}")

    # ── Mode: DRY_ARM_CHECK_ONLY ──
    if args.mode == "DRY_ARM_CHECK_ONLY":
        result = {
            "mode": "DRY_ARM_CHECK_ONLY",
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "hard_gate_verdict": gate["verdict"],
            "hard_gate_checks": gate["checks"],
            "hard_gate_reasons": gate["reasons"],
            "order_send_called": False,
            "order_send_success": 0,
            "trades_opened": 0,
            "trades_closed": 0,
            "net_pnl": 0,
            "final_verdict": gate["verdict"],
            "message": "DRY_ARM_CHECK_ONLY — no orders sent. "
                       "Execute would be " + ("ARMED" if gate["verdict"] == "DEMO_MICRO_ARMED"
                                              else "BLOCKED") + ".",
        }
        _save_report(result, "DRY_ARM_CHECK_ONLY")
        print(f"\n  >>> DRY_ARM_CHECK_ONLY result: {result['final_verdict']}")
        print(f"  >>> {result['message']}")
        return

    # ── Mode: DEMO_MICRO_EXECUTE ──
    if args.mode == "DEMO_MICRO_EXECUTE":
        # SAFETY: Z AI must never run this. Block unless explicitly armed.
        arm_env = os.environ.get("TITAN_DEMO_MICRO_ARMED", "0")
        if arm_env != "1":
            print("\n  ✗ TITAN_DEMO_MICRO_ARMED not set to 1 — BLOCKED")
            print("  This mode is operator-only. Z AI must not execute.")
            result = {
                "mode": "DEMO_MICRO_EXECUTE",
                "final_verdict": "DEMO_MICRO_BLOCKED",
                "reason": "Arm token not present",
                "order_send_called": False,
            }
            _save_report(result, "DEMO_MICRO_EXECUTE_BLOCKED")
            return

        if gate["verdict"] != "DEMO_MICRO_ARMED":
            print(f"\n  ✗ Hard gate verdict: {gate['verdict']} — BLOCKED")
            result = {
                "mode": "DEMO_MICRO_EXECUTE",
                "final_verdict": "DEMO_MICRO_BLOCKED",
                "reason": f"Hard gate: {gate['verdict']}",
                "order_send_called": False,
            }
            _save_report(result, "DEMO_MICRO_EXECUTE_BLOCKED")
            return

        # If we get here, operator is running on Windows with DEMO + arm token
        # Actual execution would happen here — but we don't implement the
        # actual MT5 order_send in this harness for safety.
        # Operator would implement/extend this section on their Windows machine.
        print("\n  ⚠ DEMO_MICRO_EXECUTE armed — but actual order execution")
        print("  must be performed by operator on Windows MT5 DEMO.")
        print("  This harness provides the safety framework + reporting.")
        result = {
            "mode": "DEMO_MICRO_EXECUTE",
            "final_verdict": "DEMO_MANUAL_REVIEW_REQUIRED",
            "reason": "Execute mode armed but order implementation requires "
                      "operator Windows MT5 environment",
            "order_send_called": False,
        }
        _save_report(result, "DEMO_MICRO_EXECUTE")


def _save_report(result, suffix):
    json_path = OUTPUT_DIR / "demo_micro_report.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str)
    md_path = OUTPUT_DIR / "demo_micro_report.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# Sprint 9.9 — Demo Micro Full-Cycle ({suffix})\n\n")
        f.write(f"**Verdict: {result.get('final_verdict', 'UNKNOWN')}**\n\n")
        f.write(f"**Mode: {result.get('mode', 'UNKNOWN')}**\n\n")
        f.write(f"**Order send called: {result.get('order_send_called', False)}**\n\n")
        if "message" in result:
            f.write(f"**Message: {result['message']}**\n")
        if "reason" in result:
            f.write(f"**Reason: {result['reason']}**\n")
    print(f"\n  JSON: {json_path}")
    print(f"  MD:   {md_path}")


def main():
    args = parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
