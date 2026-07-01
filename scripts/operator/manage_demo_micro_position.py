#!/usr/bin/env python3
"""
TITAN XAU AI - Manage Demo Micro Position (Sprint 9.9.3.45.5)
=============================================================
NEVER sends orders in check-only or preview mode.
--apply-once is gated for local operator only. Z AI must NOT run it.

Sprint 9.9.3.45.5: Stale preview fix.
  - Before writing PREVIEW_GENERATED: re-read current positions_get,
    verify ticket still exists. If position not present: verdict
    NO_POSITION_FOUND or POSITION_CLOSED_BEFORE_PREVIEW. Do not write
    stale recommendation.
  - If position found and then disappears: include warning
    POSITION_DISAPPEARED_DURING_PREVIEW. Do not report actionable
    SLTP preview.
"""
from __future__ import annotations
import argparse, json, sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
OUTPUT_DIR = REPO_ROOT / "data" / "audit" / "demo_micro_execution"

TITAN_MAGIC = 202619
TITAN_COMMENT = "TITAN_DEMO_MICRO"


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
    """Sprint 9.9.3.45.5: Stale-preview-safe trailing preview.

    Re-reads positions_get TWICE if necessary:
      1. Initial scan finds candidate TITAN positions.
      2. For each candidate, immediately re-reads positions_get to
         verify the ticket still exists. If the position has
         disappeared between scans, returns POSITION_DISAPPEARED_DURING_PREVIEW
         and does NOT emit an actionable SLTP preview.
    """
    ts = datetime.now(timezone.utc).isoformat()
    from titan.production.demo_micro_position_manager import DemoMicroPositionManager
    from titan.production.demo_micro_sl_modify_builder import DemoMicroSLModifyBuilder

    mgr = DemoMicroPositionManager()
    builder = DemoMicroSLModifyBuilder()

    recommendations = []
    warnings = []
    disappeared_tickets = []
    found_count = 0
    verified_count = 0

    try:
        import MetaTrader5 as mt5
        if mt5.initialize():
            # === First scan: find candidate TITAN positions ===
            positions = mt5.positions_get(symbol="XAUUSD")
            candidates = []
            if positions:
                for p in positions:
                    magic = getattr(p, "magic", 0)
                    if magic != TITAN_MAGIC:
                        continue  # Ignore non-TITAN positions
                    candidates.append(p)
            found_count = len(candidates)

            if found_count == 0:
                mt5.shutdown()
                return {
                    "timestamp_utc": ts,
                    "mode": "preview_trailing",
                    "verdict": "NO_POSITION_FOUND",
                    "recommendations": [],
                    "count": 0,
                    "found_count": 0,
                    "verified_count": 0,
                    "disappeared_tickets": [],
                    "warnings": warnings,
                    "important_note": "No open TITAN_DEMO_MICRO position found. No preview generated.",
                }

            # === Second scan: verify each candidate still exists ===
            # Re-read positions_get to ensure ticket is still open
            verify_positions = mt5.positions_get(symbol="XAUUSD")
            verify_tickets = set()
            if verify_positions:
                for vp in verify_positions:
                    if getattr(vp, "magic", 0) == TITAN_MAGIC:
                        verify_tickets.add(getattr(vp, "ticket", 0))

            for p in candidates:
                ticket = getattr(p, "ticket", 0)
                if ticket not in verify_tickets:
                    # Position disappeared between first and second scan
                    disappeared_tickets.append(ticket)
                    warnings.append(
                        f"POSITION_DISAPPEARED_DURING_PREVIEW: ticket {ticket} was found in "
                        "initial scan but not in verification scan. No actionable SLTP preview emitted."
                    )
                    continue
                verified_count += 1
                direction = "BUY" if getattr(p, "type", 1) == 0 else "SELL"
                entry = getattr(p, "price_open", 0)
                current = getattr(p, "price_current", 0)
                sl = getattr(p, "sl", 0)
                tp = getattr(p, "tp", 0)

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
                    "verified_alive": True,
                    "verification_method": "positions_get_double_scan",
                })
            mt5.shutdown()
    except ImportError:
        warnings.append("MetaTrader5 not available - preview limited")
    except Exception as e:
        warnings.append(f"Preview error: {e}")

    # Determine verdict
    if disappeared_tickets and not recommendations:
        # All candidates disappeared
        verdict = "POSITION_CLOSED_BEFORE_PREVIEW"
    elif disappeared_tickets and recommendations:
        # Some disappeared, some verified
        verdict = "PREVIEW_GENERATED_WITH_WARNINGS"
    elif recommendations:
        verdict = "PREVIEW_GENERATED"
    else:
        verdict = "NO_POSITION_FOUND"

    return {
        "timestamp_utc": ts,
        "mode": "preview_trailing",
        "verdict": verdict,
        "recommendations": recommendations,
        "count": len(recommendations),
        "found_count": found_count,
        "verified_count": verified_count,
        "disappeared_tickets": disappeared_tickets,
        "warnings": warnings,
        "important_note": "This is a PREVIEW only. No mt5.order_send was called. No position was modified. "
                          "Recommendations are only emitted for positions verified alive via double-scan.",
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
        # Sprint 9.9.3.45.5: Stale-preview fields
        f.write("## Verification Summary\n\n")
        f.write("| Field | Value |\n|---|---|\n")
        f.write(f"| found_count | {result.get('found_count', 'N/A')} |\n")
        f.write(f"| verified_count | {result.get('verified_count', 'N/A')} |\n")
        f.write(f"| disappeared_tickets | {result.get('disappeared_tickets', [])} |\n")
        if result.get("recommendations"):
            f.write("\n## Recommendations (Verified Alive)\n\n")
            for r in result["recommendations"]:
                f.write(f"- Ticket: {r['ticket']}, Action: {r['action']}, "
                        f"Current SL: {r['current_sl']}, Recommended SL: {r['recommended_sl']}, "
                        f"Verified: {r.get('verified_alive', False)}\n")
        if result.get("warnings"):
            f.write("\n## Warnings\n\n")
            for w in result["warnings"]:
                f.write(f"- {w}\n")
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
    print("  TITAN XAU AI - Manage Demo Micro Position (Sprint 9.9.3.45.5)")
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
    print(f"  Found: {result.get('found_count', 'N/A')}  Verified: {result.get('verified_count', 'N/A')}")
    print(f"\n  JSON: {report['json_path']}")
    print(f"  MD:   {report['md_path']}")
    print("\n" + "=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
