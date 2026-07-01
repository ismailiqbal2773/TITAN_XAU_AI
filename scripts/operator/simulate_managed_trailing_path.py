#!/usr/bin/env python3
"""
TITAN XAU AI - Simulate Managed Trailing Path (Sprint 9.9.3.45.6)
==================================================================
Test decision logic without real MT5 order or modification.

Modes:
  --scenario loss        -> HOLD (price moved against position)
  --scenario breakeven   -> MODIFY to breakeven/offset
  --scenario trailing    -> MODIFY favorable SL
  --scenario profit-lock -> MODIFY locked profit SL

Output:
  data/audit/demo_micro_execution/simulated_trailing_path.json
  data/audit/demo_micro_execution/simulated_trailing_path.md

NO order_send. NO modification. Pure decision simulation.
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
TITAN_SYMBOL = "XAUUSD"


# Scenario definitions: each scenario is a synthetic position state.
# BUY position: entry 2000.0, SL 1990.0, TP 2010.0
# Scenarios adjust current_price to drive specific actions.
SCENARIOS = {
    "loss": {
        "description": "Price moved against position (below entry). HOLD expected.",
        "direction": "BUY",
        "entry_price": 2000.0,
        "current_price": 1995.0,  # -5.0 profit_distance, below breakeven trigger
        "current_sl": 1990.0,
        "current_tp": 2010.0,
        "expected_action": "HOLD",
    },
    "breakeven": {
        "description": "Price moved +1.5 above entry (past breakeven_trigger=1.0).",
        "direction": "BUY",
        "entry_price": 2000.0,
        "current_price": 2001.5,  # +1.5 profit_distance, breakeven
        "current_sl": 1990.0,
        "current_tp": 2010.0,
        "expected_action": "MOVE_TO_BREAKEVEN",
    },
    "trailing": {
        "description": "Price moved +2.5 above entry (past trailing_trigger=2.0).",
        "direction": "BUY",
        "entry_price": 2000.0,
        "current_price": 2002.5,  # +2.5 profit_distance, trailing
        "current_sl": 1990.0,
        "current_tp": 2010.0,
        "expected_action": "TRAIL",
    },
    "profit-lock": {
        "description": "Price moved +3.5 above entry (past profit_lock_trigger=3.0).",
        "direction": "BUY",
        "entry_price": 2000.0,
        "current_price": 2003.5,  # +3.5 profit_distance, profit-lock
        "current_sl": 1990.0,
        "current_tp": 2010.0,
        "expected_action": "PROFIT_LOCK",
    },
}


def simulate_scenario(scenario: str) -> dict:
    """Run a synthetic decision simulation. No MT5, no order_send."""
    ts = datetime.now(timezone.utc).isoformat()
    if scenario not in SCENARIOS:
        return {
            "timestamp_utc": ts,
            "scenario": scenario,
            "verdict": "SIMULATION_BLOCKED",
            "blockers": [f"Unknown scenario: {scenario}"],
            "available_scenarios": list(SCENARIOS.keys()),
        }

    cfg = SCENARIOS[scenario]
    from titan.production.demo_micro_position_manager import (
        DemoMicroPositionManager, SLAction,
    )
    from titan.production.demo_micro_sl_modify_builder import DemoMicroSLModifyBuilder

    mgr = DemoMicroPositionManager()
    builder = DemoMicroSLModifyBuilder()

    rec = mgr.evaluate(
        direction=cfg["direction"],
        entry_price=cfg["entry_price"],
        current_price=cfg["current_price"],
        current_sl=cfg["current_sl"],
        current_tp=cfg["current_tp"],
    )

    preview = builder.build_preview(
        ticket=999999,  # Synthetic ticket
        new_sl=rec.new_sl,
        tp=cfg["current_tp"],
        favorable=rec.favorable,
        reason=rec.reason,
        blockers=rec.blockers,
    )

    # Compute TP preserve check
    tp_preserved = rec.tp == cfg["current_tp"]
    # Favorable-only check
    favorable = rec.favorable
    # No widening check
    if cfg["direction"] == "BUY":
        no_widening = rec.new_sl >= cfg["current_sl"]
    else:
        no_widening = rec.new_sl <= cfg["current_sl"] or cfg["current_sl"] == 0

    # Determine verdict
    if rec.action == SLAction.HOLD:
        verdict = "SIMULATION_HOLD"
        action_label = "HOLD"
    elif rec.action == SLAction.BLOCKED:
        verdict = "SIMULATION_BLOCKED"
        action_label = "MODIFY_BLOCKED"
    else:
        # MODIFY action
        if not tp_preserved:
            verdict = "SIMULATION_BLOCKED"
            action_label = "MODIFY_BLOCKED_TP_NOT_PRESERVED"
        elif not favorable:
            verdict = "SIMULATION_BLOCKED"
            action_label = "MODIFY_BLOCKED_UNFAVORABLE"
        elif not no_widening:
            verdict = "SIMULATION_BLOCKED"
            action_label = "MODIFY_BLOCKED_WIDENING"
        else:
            verdict = "SIMULATION_MODIFY"
            action_label = rec.action.value

    expected = cfg["expected_action"]
    matches_expected = rec.action.value == expected

    return {
        "timestamp_utc": ts,
        "scenario": scenario,
        "scenario_description": cfg["description"],
        "verdict": verdict,
        "action": action_label,
        "expected_action": expected,
        "matches_expected": matches_expected,
        "direction": cfg["direction"],
        "entry_price": cfg["entry_price"],
        "current_price": cfg["current_price"],
        "current_sl": cfg["current_sl"],
        "current_tp": cfg["current_tp"],
        "new_sl": rec.new_sl,
        "favorable": favorable,
        "tp_preserved": tp_preserved,
        "no_widening": no_widening,
        "modify_reason": rec.reason,
        "preview": preview,
        "blockers": rec.blockers,
        "safety": {
            "order_send_called": False,
            "position_modified": False,
            "no_martingale": True,
            "no_grid": True,
            "no_averaging": True,
        },
        "important_note": "This is a SIMULATION only. No mt5.order_send was called. No position was modified.",
    }


def write_report(result: dict) -> dict:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUTPUT_DIR / "simulated_trailing_path.json"
    md_path = OUTPUT_DIR / "simulated_trailing_path.md"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str, ensure_ascii=False)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# TITAN XAU AI - Simulated Managed Trailing Path\n\n")
        f.write(f"**Scenario:** {result.get('scenario', 'unknown')}\n\n")
        f.write(f"**Verdict:** **{result.get('verdict', 'UNKNOWN')}**\n\n")
        f.write(f"**Action:** {result.get('action', 'N/A')}\n\n")
        f.write(f"**Expected:** {result.get('expected_action', 'N/A')}\n\n")
        f.write(f"**Matches Expected:** {result.get('matches_expected', False)}\n\n")
        f.write(f"**Timestamp:** {result.get('timestamp_utc', '')}\n\n")
        f.write(f"**Description:** {result.get('scenario_description', '')}\n\n")
        f.write("## Synthetic Position\n\n")
        f.write("| Field | Value |\n|---|---|\n")
        f.write(f"| direction | {result.get('direction', 'N/A')} |\n")
        f.write(f"| entry_price | {result.get('entry_price', 'N/A')} |\n")
        f.write(f"| current_price | {result.get('current_price', 'N/A')} |\n")
        f.write(f"| current_sl | {result.get('current_sl', 'N/A')} |\n")
        f.write(f"| current_tp | {result.get('current_tp', 'N/A')} |\n")
        f.write("\n## Decision\n\n")
        f.write("| Field | Value |\n|---|---|\n")
        f.write(f"| new_sl | {result.get('new_sl', 'N/A')} |\n")
        f.write(f"| favorable | {result.get('favorable', 'N/A')} |\n")
        f.write(f"| tp_preserved | {result.get('tp_preserved', 'N/A')} |\n")
        f.write(f"| no_widening | {result.get('no_widening', 'N/A')} |\n")
        f.write(f"| modify_reason | {result.get('modify_reason', 'N/A')} |\n")
        if result.get("blockers"):
            f.write("\n## Blockers\n\n")
            for b in result["blockers"]:
                f.write(f"- {b}\n")
        f.write("\n## Safety\n\n")
        f.write("- order_send_called: False\n")
        f.write("- position_modified: False\n")
        f.write("- no_martingale: True\n")
        f.write("- no_grid: True\n")
        f.write("- no_averaging: True\n")
    return {"json_path": str(json_path), "md_path": str(md_path)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Simulate managed trailing path (no MT5, no order_send)")
    parser.add_argument("--scenario", required=True,
                        choices=["loss", "breakeven", "trailing", "profit-lock"],
                        help="Scenario to simulate")
    args = parser.parse_args()
    print("=" * 70)
    print("  TITAN XAU AI - Simulate Managed Trailing Path (Sprint 9.9.3.45.6)")
    print("=" * 70)
    result = simulate_scenario(args.scenario)
    report = write_report(result)
    print(f"\n  Scenario: {result.get('scenario', 'unknown')}")
    print(f"  Verdict: {result.get('verdict', 'UNKNOWN')}")
    print(f"  Action: {result.get('action', 'N/A')}")
    print(f"  Expected: {result.get('expected_action', 'N/A')}")
    print(f"  Matches expected: {result.get('matches_expected', False)}")
    print(f"  New SL: {result.get('new_sl', 'N/A')}")
    print(f"  TP preserved: {result.get('tp_preserved', 'N/A')}")
    print(f"  Favorable: {result.get('favorable', 'N/A')}")
    print(f"\n  JSON: {report['json_path']}")
    print(f"  MD:   {report['md_path']}")
    print("\n" + "=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
