"""
TITAN XAU AI — Sprint 9.9.3 Additional Task: Stress PnL Loss Root Cause Audit
==============================================================================

This script reads the latest virtual_lifecycle_report.json, identifies all
losing scenarios (across NORMAL + STRESS categories), and produces a root-cause
analysis + mitigation backlog.

This is READ-ONLY — does NOT modify any trading strategy, live/demo execution,
or model code. It only writes reports under data/audit/stress_loss/.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_REPORT = REPO_ROOT / "data" / "audit" / "virtual_lifecycle" / "virtual_lifecycle_report.json"
SOURCE_JOURNAL = REPO_ROOT / "data" / "audit" / "virtual_lifecycle" / "virtual_lifecycle_journal.jsonl"
OUTPUT_DIR = REPO_ROOT / "data" / "audit" / "stress_loss"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
JSON_OUT = OUTPUT_DIR / "stress_loss_root_cause_report.json"
MD_OUT = OUTPUT_DIR / "stress_loss_root_cause_report.md"


# ─── Root cause classification rules ─────────────────────────────────────────
# Map each scenario's loss signature to root cause(s) and mitigation(s).
# Driven by signal from the report: close_reason + MFE + MAE + R + costs.

def classify_scenario(scenario: dict) -> dict:
    """Classify a losing scenario's root cause and recommend mitigations."""
    name = scenario["scenario"]
    direction = scenario["direction"]
    entry = scenario["entry"]
    close = scenario["close"]
    reason = scenario["reason"]
    gross = scenario["gross_pnl"]
    net = scenario["net_pnl"]
    r = scenario["r_multiple"]
    mfe = scenario.get("mfe", 0.0)
    mae = scenario.get("mae", 0.0)
    costs = scenario["costs"]
    spread_cost = costs["spread_cost"]
    comm_cost = costs["commission_cost"]
    slip_cost = costs["slippage_cost"]
    swap_cost = costs["swap_cost"]
    total_cost = costs["total_cost"]

    root_causes = []
    mitigations = []
    severity = "LOW"
    notes = []

    # REGIME_FLIP scenarios — flat price move, only cost hit
    if reason == "REGIME_RISK_EXIT" and gross == 0.0 and mfe == 0 and mae == 0:
        root_causes.append("regime_misclassification")
        root_causes.append("tighter_regime_flip_exit")
        mitigations.append("no-trade filter: block entries within N bars of regime-flip signal")
        mitigations.append("stricter alpha threshold per regime: require meta_conf >= 0.70 in transitional regime")
        mitigations.append("reduce risk multiplier to 0.5 in transitional regime")
        mitigations.append("faster regime-flip exit: trigger close on first regime probability > 0.6 (vs current > 0.7)")
        severity = "LOW"
        notes.append("Loss is small (only cost). But signal was wrong-direction or noise — entry filter should reject.")

    # HIGH_VOLATILITY — massive MFE giveback
    elif name == "HIGH_VOLATILITY" and reason == "SL_HIT" and mfe >= 25 and mae >= 15:
        root_causes.append("volatility_shock")
        root_causes.append("exit_delay_profit_giveback")
        root_causes.append("weak_alpha_accepted")
        mitigations.append("volatility shock filter: block entries when ATR percentile > 90 (current regime has 30-point swing)")
        mitigations.append("earlier break-even: move SL to BE when MFE >= 1.0R (currently +30 unrealized then SL hit = -1.0R giveback)")
        mitigations.append("faster partial close: take 50% at +1R, lock 25% more at +2R (current partial plan not aggressive enough in high-vol)")
        mitigations.append("trailing stop: tighten trail to 0.5R in high-vol regime (vs current 1.0R)")
        mitigations.append("spread/slippage block: max_spread_usd < 0.40 in high-vol (was 0.50)")
        severity = "CRITICAL"
        notes.append(f"Position was +${mfe} profit but ended at SL = -1.0R. Worst giveback in test set.")

    # AMBIGUOUS_CANDLE — strong MFE then SL hit
    elif name == "AMBIGUOUS_CANDLE" and reason == "SL_HIT" and mfe >= 20:
        root_causes.append("weak_alpha_accepted")
        root_causes.append("exit_delay_profit_giveback")
        root_causes.append("bad_session_liquidity")
        mitigations.append("stricter alpha threshold: require meta_conf >= 0.70 on ambiguous candle patterns")
        mitigations.append("earlier break-even: move SL to BE at +1.0R (was +25 unrealized then -10 at SL)")
        mitigations.append("no-trade filter: skip entry if candle range > 2.0 * ATR AND direction ambiguous (close near middle)")
        mitigations.append("faster partial close: lock 50% at +1R for ambiguous-candle entries")
        mitigations.append("tighter regime-flip exit: any opposite-direction 1-bar momentum > 1.5 ATR → close immediately")
        severity = "HIGH"
        notes.append("Strong directional bias but gave back 100%+ of MFE. Exit policy too loose.")

    # EQUITY_PROTECTION — designed exit, smaller loss than SL would be
    elif reason == "EQUITY_PROTECTION_EXIT":
        root_causes.append("broker_execution_condition")
        root_causes.append("weak_alpha_accepted")
        mitigations.append("disable strategy in that regime when equity protection is engaged (capital_preservation state)")
        mitigations.append("reduce risk multiplier to 0.25 when equity-protection threshold is within 2% of trigger")
        mitigations.append("no-trade filter: block new entries when daily DD > 50% of equity-protection threshold")
        mitigations.append("earlier break-even: when in equity-protection zone, force BE at +0.3R instead of +1.0R")
        severity = "MEDIUM"
        notes.append("This is CORRECT BEHAVIOR — equity protection triggered before SL. Smaller loss (-5) than SL (-10).")

    # CAPITAL_PRESERVATION — designed exit, smallest loss
    elif reason == "CAPITAL_PRESERVATION_EXIT":
        root_causes.append("broker_execution_condition")
        root_causes.append("weak_alpha_accepted")
        mitigations.append("disable strategy in that regime when capital_preservation state active (allow_new_entries=false)")
        mitigations.append("reduce risk multiplier to 0.0 when capital_preservation active (config already does this)")
        mitigations.append("no-trade filter: block ALL new entries when account health < 25 (capital_preservation profile)")
        mitigations.append("faster exit on capital_preservation: trigger exit at -0.3R (not -0.5R) in capital_preservation mode")
        severity = "LOW"
        notes.append("CORRECT BEHAVIOR — capital preservation correctly minimized loss (-2 vs SL -10).")

    # BUY_SL / SELL_SL — baseline stop-loss tests
    elif reason == "SL_HIT" and "SL" in name:
        root_causes.append("weak_alpha_accepted")
        root_causes.append("spread_slippage_cost")
        mitigations.append("stricter alpha threshold: meta_conf >= 0.70 for entries (currently 0.65)")
        mitigations.append("spread/slippage block: skip if spread > 0.30 USD (currently allows up to 1.00)")
        mitigations.append("earlier break-even: move SL to BE at +0.5R (currently +1.0R) to reduce stop-out cost")
        mitigations.append("faster partial close: take 25% at +0.5R to recoup spread/commission")
        mitigations.append("disable strategy in that regime if win_rate < 35% over rolling 50 trades")
        severity = "MEDIUM"
        notes.append("Baseline SL test — expected loss (-10 gross + 0.6 cost). Loss is within R-model, but cost drag compounds in stress.")

    # Fallback classification
    else:
        root_causes.append("unknown")
        mitigations.append("investigate scenario with dev team")
        severity = "UNKNOWN"

    # Cost analysis
    cost_drag_pct = (total_cost / abs(gross) * 100) if gross != 0 else 100.0
    is_cost_dominant = gross == 0.0 and net < 0  # pure cost loss (no move)

    return {
        "scenario": name,
        "category": scenario["category"],
        "direction": direction,
        "entry_price": entry,
        "close_price": close,
        "close_reason": reason,
        "gross_pnl": gross,
        "net_pnl": net,
        "r_multiple": r,
        "mfe": mfe,
        "mae": mae,
        "costs": {
            "spread_cost": spread_cost,
            "commission_cost": comm_cost,
            "slippage_cost": slip_cost,
            "swap_cost": swap_cost,
            "total_cost": total_cost,
            "cost_drag_pct": round(cost_drag_pct, 2),
        },
        "is_cost_dominant_loss": is_cost_dominant,
        "root_causes": root_causes,
        "mitigations": mitigations,
        "severity": severity,
        "notes": notes,
    }


def build_report():
    with open(SOURCE_REPORT, "r", encoding="utf-8") as f:
        source = json.load(f)

    all_scenarios = source["scenarios"]
    losing = [s for s in all_scenarios if s["net_pnl"] < 0]
    profitable = [s for s in all_scenarios if s["net_pnl"] >= 0]
    classified = [classify_scenario(s) for s in losing]

    # Sort losing scenarios by severity then by net_pnl (worst first)
    severity_rank = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "UNKNOWN": 4}
    classified.sort(key=lambda x: (severity_rank.get(x["severity"], 9), x["net_pnl"]))

    # Aggregate root cause counts
    root_cause_counts = {}
    mitigation_counts = {}
    for c in classified:
        for rc in c["root_causes"]:
            root_cause_counts[rc] = root_cause_counts.get(rc, 0) + 1
        for m in c["mitigations"]:
            mitigation_counts[m] = mitigation_counts.get(m, 0) + 1

    # Mitigation backlog (deduplicated, ranked by frequency)
    backlog = []
    seen_mitigations = set()
    for c in classified:
        for m in c["mitigations"]:
            if m not in seen_mitigations:
                seen_mitigations.add(m)
                backlog.append({
                    "mitigation": m,
                    "frequency": mitigation_counts[m],
                    "applies_to_scenarios": [
                        cc["scenario"] for cc in classified if m in cc["mitigations"]
                    ],
                })
    backlog.sort(key=lambda x: -x["frequency"])

    report = {
        "audit": "sprint_9_9_3_stress_loss_root_cause",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "source_report": str(SOURCE_REPORT.relative_to(REPO_ROOT)),
        "source_journal": str(SOURCE_JOURNAL.relative_to(REPO_ROOT)),
        "source_audit_id": source.get("audit", ""),
        "source_verdict": source.get("verdict", ""),
        "source_demo_gate": source.get("demo_gate", ""),
        "summary": {
            "total_scenarios": len(all_scenarios),
            "normal_scenarios": sum(1 for s in all_scenarios if s["category"] == "NORMAL"),
            "stress_scenarios": sum(1 for s in all_scenarios if s["category"] == "STRESS"),
            "profitable_scenarios": len(profitable),
            "losing_scenarios": len(losing),
            "loss_total_net_pnl": round(sum(s["net_pnl"] for s in losing), 2),
            "profit_total_net_pnl": round(sum(s["net_pnl"] for s in profitable), 2),
            "net_pnl_combined": source["combined_metrics"]["net_pnl_total"],
            "stress_net_pnl": source["stress_metrics"]["net_pnl_total"],
            "stress_win_rate": source["stress_metrics"]["win_rate_net"],
            "stress_profit_factor": source["stress_metrics"]["profit_factor_net"],
            "stress_max_drawdown_usd": source["stress_metrics"]["max_drawdown_usd"],
            "stress_cost_drag_pct": source["stress_metrics"]["cost_drag_pct"],
            "normal_cost_drag_pct": source["normal_metrics"]["cost_drag_pct"],
        },
        "losing_scenarios_classified": classified,
        "profitable_scenarios": [
            {
                "scenario": s["scenario"],
                "category": s["category"],
                "net_pnl": s["net_pnl"],
                "r_multiple": s["r_multiple"],
                "close_reason": s["reason"],
            } for s in profitable
        ],
        "root_cause_frequency": root_cause_counts,
        "mitigation_backlog": backlog,
        "code_changed": False,
        "strategy_changed": False,
        "demo_micro_execute_run": False,
        "notes": [
            "This audit is READ-ONLY — no code, strategy, or model changes were made.",
            "All mitigations are recommendations for future sprints, not implemented here.",
            "The 8 losing scenarios include 2 NORMAL (BUY_SL, SELL_SL) and 6 STRESS.",
            "Two STRESS losses (EQUITY_PROTECTION, CAPITAL_PRESERVATION) are CORRECT BEHAVIOR — ",
            "safety systems triggered before SL, minimizing loss.",
            "Two STRESS losses (HIGH_VOLATILITY, AMBIGUOUS_CANDLE) are CRITICAL — large MFE giveback.",
            "Two STRESS losses (REGIME_FLIP_BUY/SELL) are LOW — pure cost loss from wrong-direction entry.",
        ],
    }

    with open(JSON_OUT, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)

    # Build MD
    md_lines = []
    md_lines.append("# Sprint 9.9.3 — Stress PnL Loss Root Cause Audit\n")
    md_lines.append(f"**Timestamp UTC:** {report['timestamp_utc']}\n")
    md_lines.append(f"**Source report:** `{report['source_report']}`\n")
    md_lines.append(f"**Source journal:** `{report['source_journal']}`\n")
    md_lines.append(f"**Source audit ID:** `{report['source_audit_id']}`\n")
    md_lines.append(f"**Source verdict:** `{report['source_verdict']}`\n")
    md_lines.append(f"**Source demo gate:** `{report['source_demo_gate']}`\n")
    md_lines.append("\n## Important\n")
    md_lines.append("- This audit is **READ-ONLY** — no code, strategy, or model changes were made.\n")
    md_lines.append("- All mitigations listed below are **recommendations for future sprints**, not implementations.\n")
    md_lines.append("- **DEMO_MICRO_EXECUTE was NOT run.**\n")
    md_lines.append("- **Trading strategy was NOT changed.**\n")
    md_lines.append("\n## Summary\n")
    md_lines.append("| Metric | Value |\n|---|---|\n")
    s = report["summary"]
    md_lines.append(f"| Total scenarios | {s['total_scenarios']} |\n")
    md_lines.append(f"| NORMAL scenarios | {s['normal_scenarios']} |\n")
    md_lines.append(f"| STRESS scenarios | {s['stress_scenarios']} |\n")
    md_lines.append(f"| Profitable scenarios | {s['profitable_scenarios']} |\n")
    md_lines.append(f"| Losing scenarios | {s['losing_scenarios']} |\n")
    md_lines.append(f"| Total profit (net PnL) | {s['profit_total_net_pnl']} |\n")
    md_lines.append(f"| Total loss (net PnL) | {s['loss_total_net_pnl']} |\n")
    md_lines.append(f"| Combined net PnL | {s['net_pnl_combined']} |\n")
    md_lines.append(f"| STRESS net PnL | {s['stress_net_pnl']} |\n")
    md_lines.append(f"| STRESS win rate | {s['stress_win_rate']}% |\n")
    md_lines.append(f"| STRESS profit factor | {s['stress_profit_factor']} |\n")
    md_lines.append(f"| STRESS max DD (USD) | {s['stress_max_drawdown_usd']} |\n")
    md_lines.append(f"| STRESS cost drag % | {s['stress_cost_drag_pct']}% |\n")
    md_lines.append(f"| NORMAL cost drag % | {s['normal_cost_drag_pct']}% |\n")

    md_lines.append("\n## Why Losing Scenarios Reduced Quality Despite Good Overall Profit\n")
    md_lines.append(
        "Combined net PnL is **+$44.1** (positive headline), but STRESS net PnL is **-$11.5** "
        "with 25% win rate and 0.63 profit factor. Stress cost drag is **91.67%** (vs 8.85% in NORMAL), "
        "meaning almost all gross PnL is consumed by costs in stress conditions. "
        "Two CRITICAL scenarios (**HIGH_VOLATILITY** and **AMBIGUOUS_CANDLE**) lost **-$21.4 combined** "
        "despite reaching MFE of +$30 and +$25 respectively — extreme profit giveback. "
        "These losses are masked by the profitable NORMAL scenarios but represent a real risk if the "
        "strategy encounters sustained volatility shocks in production.\n"
    )

    md_lines.append("\n## The 8 Losing Scenarios (Root Cause Classification)\n")
    md_lines.append("| # | Scenario | Category | Direction | Close Reason | Gross PnL | Net PnL | R | MFE | MAE | Severity | Root Causes |\n")
    md_lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|\n")
    for i, c in enumerate(classified, 1):
        md_lines.append(
            f"| {i} | {c['scenario']} | {c['category']} | {c['direction']} | {c['close_reason']} | "
            f"{c['gross_pnl']} | {c['net_pnl']} | {c['r_multiple']} | {c['mfe']} | {c['mae']} | "
            f"{c['severity']} | {', '.join(c['root_causes'])} |\n"
        )

    md_lines.append("\n## Per-Scenario Root Cause + Mitigation Detail\n")
    for i, c in enumerate(classified, 1):
        md_lines.append(f"\n### {i}. {c['scenario']} ({c['category']})\n")
        md_lines.append(f"- **Direction:** {c['direction']}\n")
        md_lines.append(f"- **Entry / Close:** {c['entry_price']} → {c['close_price']} ({c['close_reason']})\n")
        md_lines.append(f"- **Gross / Net PnL:** {c['gross_pnl']} / {c['net_pnl']}\n")
        md_lines.append(f"- **R-multiple:** {c['r_multiple']}  |  **MFE:** {c['mfe']}  |  **MAE:** {c['mae']}\n")
        md_lines.append(f"- **Costs:** spread={c['costs']['spread_cost']}, commission={c['costs']['commission_cost']}, "
                        f"slippage={c['costs']['slippage_cost']}, swap={c['costs']['swap_cost']}, "
                        f"total={c['costs']['total_cost']} ({c['costs']['cost_drag_pct']}% drag)\n")
        md_lines.append(f"- **Severity:** {c['severity']}\n")
        md_lines.append(f"- **Root causes:**\n")
        for rc in c["root_causes"]:
            md_lines.append(f"  - {rc}\n")
        md_lines.append(f"- **Recommended mitigations:**\n")
        for m in c["mitigations"]:
            md_lines.append(f"  - {m}\n")
        if c["notes"]:
            md_lines.append(f"- **Notes:**\n")
            for n in c["notes"]:
                md_lines.append(f"  - {n}\n")

    md_lines.append("\n## Root Cause Frequency\n")
    md_lines.append("| Root Cause | Count |\n|---|---|\n")
    for rc, cnt in sorted(root_cause_counts.items(), key=lambda x: -x[1]):
        md_lines.append(f"| {rc} | {cnt} |\n")

    md_lines.append("\n## Mitigation Backlog (Ranked by Frequency)\n")
    md_lines.append("| # | Mitigation | Frequency | Applies to Scenarios |\n")
    md_lines.append("|---|---|---|---|\n")
    for i, b in enumerate(backlog, 1):
        md_lines.append(f"| {i} | {b['mitigation']} | {b['frequency']} | {', '.join(b['applies_to_scenarios'])} |\n")

    md_lines.append("\n## Profitable Scenarios (for Reference)\n")
    md_lines.append("| Scenario | Category | Net PnL | R | Close Reason |\n|---|---|---|---|---|\n")
    for p in report["profitable_scenarios"]:
        md_lines.append(f"| {p['scenario']} | {p['category']} | {p['net_pnl']} | {p['r_multiple']} | {p['close_reason']} |\n")

    md_lines.append("\n## Safety Confirmation\n")
    md_lines.append("| Item | Value |\n|---|---|\n")
    md_lines.append(f"| Code changed | {'YES' if report['code_changed'] else 'NO'} |\n")
    md_lines.append(f"| Strategy changed | {'YES' if report['strategy_changed'] else 'NO'} |\n")
    md_lines.append(f"| DEMO_MICRO_EXECUTE run | {'YES' if report['demo_micro_execute_run'] else 'NO'} |\n")

    md_lines.append("\n## Next Steps\n")
    md_lines.append("1. Review this report with the team.\n")
    md_lines.append("2. Prioritize CRITICAL mitigations first (HIGH_VOLATILITY, AMBIGUOUS_CANDLE).\n")
    md_lines.append("3. Implement mitigations in a future sprint (NOT this one).\n")
    md_lines.append("4. Re-run virtual_lifecycle_validator.py after each mitigation to verify improvement.\n")
    md_lines.append("5. Do NOT retrain models or change trading strategy without separate sprint approval.\n")

    with open(MD_OUT, "w", encoding="utf-8") as f:
        f.writelines(md_lines)

    print(f"JSON report: {JSON_OUT}")
    print(f"MD report:   {MD_OUT}")
    print(f"\nLosing scenarios identified: {len(classified)}")
    print(f"Profitable scenarios:        {len(profitable)}")
    print(f"Total scenarios:             {len(all_scenarios)}")
    return report


if __name__ == "__main__":
    build_report()
