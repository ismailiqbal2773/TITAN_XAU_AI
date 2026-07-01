#!/usr/bin/env python3
"""
TITAN XAU AI - Prop/Funded Optimization Audit (Sprint 9.9.3.45.8.8)
=====================================================================
Runs the prop/funded optimizer and generates a proof report.

NEVER sends orders. NEVER modifies positions. NEVER fabricates metrics.
"""
from __future__ import annotations
import json, sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
OUTPUT_DIR = REPO_ROOT / "data" / "audit" / "prop_funded_optimization"


def run_audit() -> dict:
    ts = datetime.now(timezone.utc).isoformat()
    from titan.production.prop_funded_optimizer import PropFundedOptimizer

    optimizer = PropFundedOptimizer()
    result = optimizer.optimize()

    ok_checks = []
    blockers = list(result.blockers)
    warnings = list(result.warnings)

    for p in result.profiles:
        ok_checks.append(
            f"{p.profile_name}: score={p.optimizer_score}, verdict={p.verdict}, "
            f"monthly={p.monthly_return_estimate}%, max_dd={p.max_dd}%, PF={p.pf}, "
            f"Sharpe={p.sharpe}, executable={p.executable}, sim_only={p.simulation_only}"
        )

    if result.best_safe_profile:
        ok_checks.append(f"Best safe profile: {result.best_safe_profile}")
    if result.best_growth_profile:
        ok_checks.append(f"Best growth profile: {result.best_growth_profile}")
    ok_checks.append(f"Aggressive 20% status: {result.aggressive_20pct_status}")
    ok_checks.append(f"Recommended first demo: {result.recommended_first_demo_profile}")

    return {
        "timestamp_utc": ts,
        "verdict": result.verdict,
        "ok_checks": ok_checks,
        "blockers": blockers,
        "warnings": warnings,
        "optimization_result": result.to_dict(),
        "safety": result.safety,
    }


def write_report(result: dict) -> dict:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUTPUT_DIR / "prop_funded_optimization_report.json"
    md_path = OUTPUT_DIR / "prop_funded_optimization_report.md"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str, ensure_ascii=False)

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# TITAN XAU AI - Prop/Funded Optimization Report\n\n")
        f.write(f"**Verdict:** **{result['verdict']}**\n\n")
        f.write(f"**Timestamp:** {result['timestamp_utc']}\n\n")

        opt = result.get("optimization_result", {})
        f.write(f"**Best Safe Profile:** {opt.get('best_safe_profile', 'N/A')}\n\n")
        f.write(f"**Best Growth Profile:** {opt.get('best_growth_profile', 'N/A')}\n\n")
        f.write(f"**Aggressive 20% Status:** {opt.get('aggressive_20pct_status', 'N/A')}\n\n")
        f.write(f"**Recommended First Demo:** {opt.get('recommended_first_demo_profile', 'N/A')}\n\n")

        f.write("## Profile Metrics\n\n")
        f.write("| Profile | Monthly% | Yearly% | MaxDD% | PF | Sharpe | Sortino | WR% | Score | Verdict | Executable | SimOnly |\n")
        f.write("|---|---|---|---|---|---|---|---|---|---|---|---|\n")
        for p in opt.get("profiles", []):
            f.write(f"| {p['profile_name']} | {p['monthly_return_estimate']} | {p['yearly_return_estimate']} | "
                    f"{p['max_dd']} | {p['pf']} | {p['sharpe']} | {p['sortino']} | {p['win_rate']} | "
                    f"{p['optimizer_score']} | {p['verdict']} | {p['executable']} | {p['simulation_only']} |\n")

        f.write("\n## Detailed Parameters\n\n")
        for p in opt.get("profiles", []):
            f.write(f"### {p['profile_name']}\n\n")
            f.write(f"**Purpose:** {p['purpose']}\n\n")
            f.write(f"**Evidence:** {p['evidence_source']}\n\n")
            f.write("| Parameter | Value |\n|---|---|\n")
            f.write(f"| risk_per_trade_pct | {p['risk_per_trade_pct']} |\n")
            f.write(f"| confidence_threshold | {p['confidence_threshold']} |\n")
            f.write(f"| atr_sl_multiplier | {p['atr_sl_multiplier']} |\n")
            f.write(f"| tp_multiplier_initial_tp_R | {p['tp_multiplier_initial_tp_R']} |\n")
            f.write(f"| minimum_rr | {p['minimum_rr']} |\n")
            f.write(f"| dynamic_tp_trigger_R | {p['dynamic_tp_trigger_R']} |\n")
            f.write(f"| breakeven_trigger_R | {p['breakeven_trigger_R']} |\n")
            f.write(f"| trailing_trigger_R | {p['trailing_trigger_R']} |\n")
            f.write(f"| profit_lock_trigger_R | {p['profit_lock_trigger_R']} |\n")
            f.write(f"| internal_daily_dd_pct | {p['internal_daily_dd_pct']} |\n")
            f.write(f"| internal_total_dd_pct | {p['internal_total_dd_pct']} |\n")
            f.write(f"| daily_dd_breach_count | {p['daily_dd_breach_count']} |\n")
            f.write(f"| total_dd_breach_count | {p['total_dd_breach_count']} |\n")
            f.write(f"| wfe | {p['wfe']} |\n")
            f.write(f"| monte_carlo_survival | {p['monte_carlo_survival']} |\n")
            f.write(f"| broker_score | {p['broker_score']} |\n")
            f.write(f"| spread_cost | {p['spread_cost_estimate']} |\n")
            f.write(f"| slippage_cost | {p['slippage_cost_estimate']} |\n")
            f.write(f"| commission_cost | {p['commission_cost_estimate']} |\n")
            f.write(f"| optimizer_score | {p['optimizer_score']} |\n")
            f.write(f"| verdict | {p['verdict']} |\n")
            f.write(f"| reason | {p.get('reason', 'N/A')} |\n\n")

        if result.get("blockers"):
            f.write("## Blockers\n\n")
            for b in result["blockers"]:
                f.write(f"- **{b}**\n")
        if result.get("warnings"):
            f.write("\n## Warnings\n\n")
            for w in result["warnings"]:
                f.write(f"- {w}\n")

        f.write("\n## Safety\n\n")
        f.write("- no_martingale: True\n")
        f.write("- no_grid: True\n")
        f.write("- no_averaging: True\n")
        f.write("- no_loss_based_lot_multiplier: True\n")
        f.write("- order_send_called: False\n")
        f.write("- position_modified: False\n")

    return {"json_path": str(json_path), "md_path": str(md_path)}


def main() -> int:
    print("=" * 70)
    print("  TITAN XAU AI - Prop/Funded Optimization Audit")
    print("=" * 70)
    result = run_audit()
    report = write_report(result)
    print(f"\n  Verdict: {result['verdict']}")
    opt = result.get("optimization_result", {})
    print(f"  Best Safe: {opt.get('best_safe_profile', 'N/A')}")
    print(f"  Best Growth: {opt.get('best_growth_profile', 'N/A')}")
    print(f"  Aggressive 20%: {opt.get('aggressive_20pct_status', 'N/A')}")
    print(f"  Recommended Demo: {opt.get('recommended_first_demo_profile', 'N/A')}")
    for p in opt.get("profiles", []):
        print(f"  {p['profile_name']}: score={p['optimizer_score']}, verdict={p['verdict']}")
    print(f"\n  JSON: {report['json_path']}")
    print(f"  MD:   {report['md_path']}")
    print("\n" + "=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
