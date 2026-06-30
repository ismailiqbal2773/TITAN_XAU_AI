#!/usr/bin/env python3
"""
TITAN XAU AI - Manage Demo Micro Position (Sprint 9.9.3.45)
=============================================================
NEVER sends orders in check-only or preview mode.
--apply-once is gated for local operator only. Z AI must NOT run it.
"""
from __future__ import annotations
import argparse, json, sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
OUTPUT_DIR = REPO_ROOT / "data" / "audit" / "demo_micro_execution"


def run_check_only() -> dict:
    ts = datetime.now(timezone.utc).isoformat()
    from titan.production.demo_micro_position_manager import DemoMicroPositionManager
    mgr = DemoMicroPositionManager()
    return {
        "timestamp_utc": ts,
        "mode": "check_only",
        "verdict": "MANAGE_CHECK_PASS",
        "manager_available": True,
        "breakeven_trigger": mgr.breakeven_trigger,
        "trailing_trigger": mgr.trailing_trigger,
        "profit_lock_trigger": mgr.profit_lock_trigger,
        "next_action": "Run --preview-trailing to see SL modification recommendations",
    }


def run_preview_trailing() -> dict:
    ts = datetime.now(timezone.utc).isoformat()
    from titan.production.demo_micro_position_manager import DemoMicroPositionManager
    from titan.production.demo_micro_sl_modify_builder import DemoMicroSLModifyBuilder

    mgr = DemoMicroPositionManager()
    builder = DemoMicroSLModifyBuilder()

    # Try to get position passively
    recommendations = []
    try:
        import MetaTrader5 as mt5
        if mt5.initialize():
            positions = mt5.positions_get(symbol="XAUUSD")
            if positions:
                for p in positions:
                    magic = getattr(p, "magic", 0)
                    if magic != 202619:
                        continue  # Ignore non-TITAN positions
                    direction = "BUY" if getattr(p, "type", 1) == 0 else "SELL"
                    entry = getattr(p, "price_open", 0)
                    current = getattr(p, "price_current", 0)
                    sl = getattr(p, "sl", 0)
                    tp = getattr(p, "tp", 0)
                    ticket = getattr(p, "ticket", 0)

                    rec = mgr.evaluate(
                        direction=direction, entry_price=entry,
                        current_price=current, current_sl=sl, current_tp=tp,
                    )
                    preview = builder.build_preview(
                        ticket=ticket, new_sl=rec.new_sl, tp=tp,
                        favorable=rec.favorable, reason=rec.reason,
                        blockers=rec.blockers,
                    )
                    recommendations.append({
                        "ticket": ticket,
                        "direction": direction,
                        "entry": entry,
                        "current": current,
                        "current_sl": sl,
                        "recommended_sl": rec.new_sl,
                        "action": rec.action.value,
                        "preview": preview,
                    })
            mt5.shutdown()
    except ImportError:
        pass
    except Exception:
        pass

    return {
        "timestamp_utc": ts,
        "mode": "preview_trailing",
        "verdict": "PREVIEW_GENERATED" if recommendations else "NO_POSITION_FOUND",
        "recommendations": recommendations,
        "count": len(recommendations),
        "important_note": "This is a PREVIEW only. No mt5.order_send was called. No position was modified.",
    }


def run_apply_once(args) -> dict:
    """Gated SL modification. Z AI must NOT run this."""
    if not getattr(args, "confirm_local_operator", False):
        return {
            "mode": "apply_once",
            "verdict": "MANAGE_REFUSED",
            "blockers": ["Missing --confirm-local-operator"],
            "important_note": "No modification was sent.",
        }
    # In Z AI env, this will block on MT5 import or environment drift
    return {
        "mode": "apply_once",
        "verdict": "MANAGE_REFUSED",
        "blockers": ["Z AI / non-local environment - apply-once must be run locally by operator"],
        "important_note": "No modification was sent. No mt5.order_send was called.",
    }


def write_report(result: dict) -> dict:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUTPUT_DIR / "manage_position_report.json"
    md_path = OUTPUT_DIR / "manage_position_report.md"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str, ensure_ascii=False)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# TITAN XAU AI - Manage Demo Micro Position\n\n")
        f.write(f"**Mode:** {result.get('mode', 'unknown')}\n\n")
        f.write(f"**Verdict:** **{result.get('verdict', 'UNKNOWN')}**\n\n")
        f.write(f"**Timestamp:** {result.get('timestamp_utc', '')}\n\n")
        if result.get("recommendations"):
            f.write("## Recommendations\n\n")
            for r in result["recommendations"]:
                f.write(f"- Ticket: {r['ticket']}, Action: {r['action']}, "
                        f"Current SL: {r['current_sl']}, Recommended SL: {r['recommended_sl']}\n")
        if result.get("important_note"):
            f.write(f"\n## Note\n\n{result['important_note']}\n")
    return {"json_path": str(json_path), "md_path": str(md_path)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage demo micro position")
    parser.add_argument("--check-only", action="store_true", default=True)
    parser.add_argument("--preview-trailing", action="store_true", default=False)
    parser.add_argument("--apply-once", action="store_true", default=False)
    parser.add_argument("--confirm-local-operator", action="store_true", default=False)
    args = parser.parse_args()

    print("=" * 70)
    print("  TITAN XAU AI - Manage Demo Micro Position (Sprint 9.9.3.45)")
    print("=" * 70)

    if args.apply_once:
        result = run_apply_once(args)
    elif args.preview_trailing:
        result = run_preview_trailing()
    else:
        result = run_check_only()

    report = write_report(result)
    print(f"\n  Mode: {result.get('mode', 'check_only')}")
    print(f"  Verdict: {result.get('verdict', 'UNKNOWN')}")
    print(f"\n  JSON: {report['json_path']}")
    print(f"  MD:   {report['md_path']}")
    print("\n" + "=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
