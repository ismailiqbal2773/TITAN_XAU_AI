#!/usr/bin/env python3
"""
TITAN XAU AI — Sprint 9.9.3.30 Exit Engine Architecture Report Writer
=======================================================================
"""
from __future__ import annotations
import json, sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
OUTPUT_DIR = REPO_ROOT / "data" / "audit" / "exit_engine"
JSON_PATH = OUTPUT_DIR / "exit_engine_architecture_report.json"
MD_PATH = OUTPUT_DIR / "exit_engine_architecture_report.md"

from titan.production.exit_defense_engine import SLAction, SLDefenseEngine
from titan.production.profit_capture_engine import ProfitAction, ProfitCaptureEngine
from titan.production.exit_decision_coordinator import FinalAction, ExitDecisionCoordinator, _PRIORITY


def write_report() -> dict:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).isoformat()
    report = {
        "timestamp_utc": ts,
        "sl_defense_rules": {
            "actions": [a.value for a in SLAction],
            "rules": [
                "SL engine can ONLY reduce risk (never widen beyond ATR/regime limit)",
                "NEWS_SHOCK → EMERGENCY_EXIT",
                "LIQUIDITY_VACUUM → EMERGENCY_EXIT",
                "Severe spread (>0.85) → EMERGENCY_EXIT",
                "Stale trade → EMERGENCY_EXIT",
                "MAE > 2R → EMERGENCY_EXIT",
                "High volatility → TIGHTEN_SL to 0.5 ATR",
                "Profit >= 1R → MOVE_TO_BREAKEVEN",
                "Profit >= 1.5R → TRAIL_SL at 1 ATR",
                "UNKNOWN regime → TIGHTEN_SL (fail-safe)",
            ],
        },
        "profit_capture_rules": {
            "actions": [a.value for a in ProfitAction],
            "rules": [
                "Can extend TP only when safe_to_hold=True",
                "Range regime → faster profit taking (TP at 1R, partial at 0.5R)",
                "Weak momentum → book 25% at 0.8R",
                "Partial close 25% at +2R and +3R",
                "Lock profit at +1R",
                "Strong trend aligned → EXTEND_TP x1.5",
                "Gold impulse + high confidence → EXTEND_TP x1.3",
                "Time decay > 1h + small profit → TAKE_PROFIT",
                "Never increases lot size",
                "Never disables SL protection",
            ],
        },
        "coordinator_priority": {
            "ladder": [
                {"priority": 1, "action": "EMERGENCY_EXIT"},
                {"priority": 3, "action": "MOVE_TO_BREAKEVEN"},
                {"priority": 4, "action": "TIGHTEN_SL / TRAIL_SL"},
                {"priority": 5, "action": "PARTIAL_CLOSE"},
                {"priority": 6, "action": "LOCK_PROFIT"},
                {"priority": 7, "action": "EXTEND_TP / TRAIL_TP"},
                {"priority": 8, "action": "HOLD"},
            ],
            "conflict_rules": [
                "SL Defense overrides Profit Capture when risk is critical",
                "Profit Capture operates only when safe_to_hold=True",
                "If engines disagree and severity unclear → fail safe toward protection",
                "Never removes SL",
                "Never increases risk above configured limits",
                "Never places orders — only produces decisions",
            ],
        },
        "regime_wise_exit_behavior": {
            "TREND_UP": "Allow winners to run, extend TP when aligned",
            "TREND_DOWN": "Allow winners to run, extend TP when aligned",
            "RANGE": "Faster profit taking, TP at 1R",
            "HIGH_VOLATILITY": "Tighten SL to 0.5 ATR, reduce risk",
            "LOW_VOLATILITY": "Book profit on weak momentum",
            "NEWS_SHOCK": "EMERGENCY_EXIT",
            "SPREAD_EXPANSION": "Tighten or emergency exit",
            "LIQUIDITY_VACUUM": "EMERGENCY_EXIT",
            "GOLD_IMPULSE": "Extend TP only with high confidence (>0.7)",
            "UNKNOWN": "Fail-safe tighten SL, reduce risk",
        },
        "fail_closed_rules": [
            "SL defense exception → fail-safe tighten",
            "Profit capture exception → fail-safe no action",
            "Coordinator exception → fail-safe hold with 0.5 risk reduction",
            "No MT5 orders sent in this sprint",
        ],
        "warnings": [
            "No MT5 execution occurs in this sprint — engines only produce decisions.",
            "Production trading behavior is NOT changed — exit engines are non-blocking foundation.",
        ],
    }
    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str, ensure_ascii=False)
    with open(MD_PATH, "w", encoding="utf-8") as f:
        f.write("# TITAN XAU AI — Exit Engine Architecture Report\n\n")
        f.write(f"**Generated:** {ts}\n\n")
        f.write("## SL Defense Rules\n\n")
        for r in report["sl_defense_rules"]["rules"]:
            f.write(f"- {r}\n")
        f.write("\n## Profit Capture Rules\n\n")
        for r in report["profit_capture_rules"]["rules"]:
            f.write(f"- {r}\n")
        f.write("\n## Coordinator Priority Ladder\n\n")
        f.write("| Priority | Action |\n|---|---|\n")
        for item in report["coordinator_priority"]["ladder"]:
            f.write(f"| {item['priority']} | {item['action']} |\n")
        f.write("\n## Conflict Rules\n\n")
        for r in report["coordinator_priority"]["conflict_rules"]:
            f.write(f"- {r}\n")
        f.write("\n## Regime-Wise Exit Behavior\n\n")
        f.write("| Regime | Behavior |\n|---|---|\n")
        for k, v in report["regime_wise_exit_behavior"].items():
            f.write(f"| {k} | {v} |\n")
        f.write("\n## Fail-Closed Rules\n\n")
        for r in report["fail_closed_rules"]:
            f.write(f"- {r}\n")
        f.write("\n## ⚠ Warnings\n\n")
        for w in report["warnings"]:
            f.write(f"- **{w}**\n")
    return {"json_path": str(JSON_PATH), "md_path": str(MD_PATH)}


def main():
    print("=" * 70)
    print("  TITAN XAU AI — Exit Engine Architecture Report (Sprint 9.9.3.30)")
    print("=" * 70)
    result = write_report()
    print(f"\n  JSON: {result['json_path']}")
    print(f"  MD:   {result['md_path']}")
    print("\n" + "=" * 70)
    return 0

if __name__ == "__main__":
    sys.exit(main())
