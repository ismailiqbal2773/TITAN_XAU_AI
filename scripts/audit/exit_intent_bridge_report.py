#!/usr/bin/env python3
"""
TITAN XAU AI — Sprint 9.9.3.31 Exit Intent Bridge Report Writer
"""
from __future__ import annotations
import json, sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
OUTPUT_DIR = REPO_ROOT / "data" / "audit" / "exit_intent"
JSON_PATH = OUTPUT_DIR / "exit_intent_bridge_report.json"
MD_PATH = OUTPUT_DIR / "exit_intent_bridge_report.md"

from titan.production.position_lifecycle import PositionState, PositionSnapshot, PositionLifecycleEngine
from titan.production.exit_intent_bridge import ExitIntentBridge, ExitIntentAction


def write_report() -> dict:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).isoformat()
    bridge = ExitIntentBridge()

    # Sample snapshots
    hold_snap = PositionSnapshot(symbol="XAUUSD", side="BUY", entry_price=2000,
                                  current_price=2001, current_sl=1995, current_tp=2010,
                                  atr=5.0, regime="TREND_UP", ticket=1001, pnl_r=0.2)
    hold_intent = bridge.build_exit_intent(hold_snap)

    modify_sl_snap = PositionSnapshot(symbol="XAUUSD", side="BUY", entry_price=2000,
                                       current_price=2005, current_sl=1995, current_tp=2010,
                                       atr=5.0, regime="TREND_UP", ticket=1002, pnl_r=1.0)
    modify_sl_intent = bridge.build_exit_intent(modify_sl_snap)

    partial_snap = PositionSnapshot(symbol="XAUUSD", side="BUY", entry_price=2000,
                                     current_price=2010, current_sl=2000, current_tp=2020,
                                     atr=5.0, regime="SESSION_LONDON", ticket=1003, pnl_r=2.0)
    partial_intent = bridge.build_exit_intent(partial_snap)

    emergency_snap = PositionSnapshot(symbol="XAUUSD", side="BUY", entry_price=2000,
                                       current_price=2010, current_sl=1995, current_tp=2020,
                                       atr=5.0, regime="NEWS_SHOCK", ticket=1004, pnl_r=2.0)
    emergency_intent = bridge.build_exit_intent(emergency_snap)

    report = {
        "timestamp_utc": ts,
        "lifecycle_states": [s.value for s in PositionState],
        "exit_intent_actions": [a.value for a in ExitIntentAction],
        "safety_rules": [
            "dry_run=True by default",
            "demo_only=True by default",
            "should_send_order=False ALWAYS in this sprint",
            "Never imports MetaTrader5",
            "Never calls mt5.order_send",
            "Never calls MT5ExecutionAdapter",
            "Exception → MANUAL_REVIEW or NO_ACTION",
            "Stuck position → MANUAL_REVIEW",
            "Emergency exit → CLOSE_FULL (dry-run, should_send_order=False)",
            "Partial close never exceeds 50%",
            "SL modification never removes SL protection",
            "No lot increase",
        ],
        "pipeline": [
            "1. PositionLifecycleEngine.evaluate(snapshot) → lifecycle status",
            "2. If stuck → MANUAL_REVIEW",
            "3. SLDefenseEngine.evaluate(...) → SL decision",
            "4. ProfitCaptureEngine.evaluate(...) → profit decision",
            "5. ExitDecisionCoordinator.coordinate(sl, profit) → final decision",
            "6. Convert final decision → ExitIntent",
        ],
        "samples": {
            "hold_intent": _intent_to_dict(hold_intent),
            "modify_sl_intent": _intent_to_dict(modify_sl_intent),
            "partial_close_intent": _intent_to_dict(partial_intent),
            "emergency_close_intent": _intent_to_dict(emergency_intent),
        },
        "warnings": [
            "No MT5 execution occurs in this sprint — bridge only produces ExitIntent.",
            "should_send_order is always False — no orders are sent.",
            "Production trading behavior is NOT changed.",
        ],
    }

    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str, ensure_ascii=False)

    with open(MD_PATH, "w", encoding="utf-8") as f:
        f.write("# TITAN XAU AI — Exit Intent Bridge Report\n\n")
        f.write(f"**Generated:** {ts}\n\n")
        f.write("## Lifecycle States\n\n")
        for s in report["lifecycle_states"]:
            f.write(f"- `{s}`\n")
        f.write("\n## Exit Intent Actions\n\n")
        for a in report["exit_intent_actions"]:
            f.write(f"- `{a}`\n")
        f.write("\n## Pipeline\n\n")
        for p in report["pipeline"]:
            f.write(f"{p}\n")
        f.write("\n## Safety Rules\n\n")
        for r in report["safety_rules"]:
            f.write(f"- {r}\n")
        f.write("\n## Sample Intents\n\n")
        for name, intent in report["samples"].items():
            f.write(f"### {name}\n\n")
            f.write("| Field | Value |\n|---|---|\n")
            for k, v in intent.items():
                f.write(f"| {k} | {v} |\n")
            f.write("\n")
        f.write("## ⚠ Warnings\n\n")
        for w in report["warnings"]:
            f.write(f"- **{w}**\n")

    return {"json_path": str(JSON_PATH), "md_path": str(MD_PATH)}


def _intent_to_dict(intent) -> dict:
    return {
        "allowed": intent.allowed,
        "action": intent.action.value,
        "symbol": intent.symbol,
        "ticket": intent.ticket,
        "side": intent.side,
        "partial_close_pct": intent.partial_close_pct,
        "new_sl": intent.new_sl,
        "new_tp": intent.new_tp,
        "reason": intent.reason,
        "source_decision": intent.source_decision,
        "dry_run": intent.dry_run,
        "demo_only": intent.demo_only,
        "should_send_order": intent.should_send_order,
    }


def main():
    print("=" * 70)
    print("  TITAN XAU AI — Exit Intent Bridge Report (Sprint 9.9.3.31)")
    print("=" * 70)
    result = write_report()
    print(f"\n  JSON: {result['json_path']}")
    print(f"  MD:   {result['md_path']}")
    print(f"\n  should_send_order=False ALWAYS")
    print("\n" + "=" * 70)
    return 0

if __name__ == "__main__":
    sys.exit(main())
