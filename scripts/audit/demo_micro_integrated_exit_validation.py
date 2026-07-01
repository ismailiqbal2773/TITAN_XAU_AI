#!/usr/bin/env python3
"""
TITAN XAU AI - Integrated Exit Validation (Sprint 9.9.3.45.8.2)
================================================================
Integrated validation of adaptive trailing + profit corridor exit system.

Validates:
  - adaptive iteration propagation correct
  - min iteration/hold clears
  - TP preserve default
  - dynamic TP opt-in exists
  - TP extension paired with SL improvement
  - SL profit floor enforced
  - no TP reduction
  - no SL widening
  - no tick chasing
  - cooldown/hysteresis
  - spread/news freeze blocks
  - monitor lifecycle
  - receipt/forensics strict matching
  - no martingale/grid/averaging
  - no loss-based lot multiplier

Verdicts:
  - INTEGRATED_EXIT_VALIDATION_READY
  - INTEGRATED_EXIT_VALIDATION_READY_DYNAMIC_TP_OPT_IN
  - INTEGRATED_EXIT_VALIDATION_BLOCKED

NO order_send. NO modification. Pure source-code audit.
"""
from __future__ import annotations
import argparse, json, re, sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
OUTPUT_DIR = REPO_ROOT / "data" / "audit" / "demo_micro_execution"


def _strip(src: str) -> str:
    src = re.sub(r'"""[\s\S]*?"""', '""', src)
    src = re.sub(r"'''[\s\S]*?'''", "''", src)
    src = re.sub(r'"(?:[^"\\]|\\.)*"', '""', src)
    src = re.sub(r"'(?:[^'\\]|\\.)*'", "''", src)
    return src


def run_validation() -> dict:
    ts = datetime.now(timezone.utc).isoformat()
    ok_checks = []
    blockers = []
    warnings = []
    findings = {}

    # Files to audit
    orchestrator_src = (REPO_ROOT / "titan" / "production" /
                        "demo_micro_managed_trade_orchestrator.py").read_text()
    run_managed_src = (REPO_ROOT / "scripts" / "operator" /
                       "run_managed_demo_micro_trade.py").read_text()
    adaptive_policy_src = (REPO_ROOT / "titan" / "production" /
                           "adaptive_trailing_policy.py").read_text()
    profit_corridor_src = (REPO_ROOT / "titan" / "production" /
                           "adaptive_profit_corridor.py").read_text()
    paired_builder_src = (REPO_ROOT / "titan" / "production" /
                          "paired_sltp_modify_builder.py").read_text()
    simulate_src = (REPO_ROOT / "scripts" / "operator" /
                    "simulate_managed_trailing_path.py").read_text()
    diagnose_src = (REPO_ROOT / "scripts" / "operator" /
                    "diagnose_latest_execution_receipt.py").read_text()
    forensics_src = (REPO_ROOT / "scripts" / "operator" /
                     "collect_demo_micro_trade_forensics.py").read_text()

    # 1. Adaptive iteration propagation correct
    # Sprint 9.9.3.45.8.2: orchestrator must accept explicit monitor_iterations param
    iteration_propagation = (
        "monitor_iterations: Optional[int] = None" in orchestrator_src
        and "hold_seconds: Optional[int] = None" in orchestrator_src
        and "actual_monitor_iterations" in orchestrator_src
    )
    if iteration_propagation:
        ok_checks.append("Adaptive iteration propagation correct (explicit monitor_iterations param)")
        findings["iteration_propagation"] = True
    else:
        blockers.append("Adaptive iteration propagation missing or incorrect")
        findings["iteration_propagation"] = False

    # 2. Min iteration/hold clears
    min_clears = (
        "MIN_MONITOR_ITERATIONS_NOT_REACHED" in adaptive_policy_src
        and "MIN_HOLD_TIME_NOT_REACHED" in adaptive_policy_src
        and "PHASE_0_INITIAL_PROTECTION" in adaptive_policy_src
    )
    if min_clears:
        ok_checks.append("Min iteration/hold Phase 0 blocks present and clearable")
        findings["min_iteration_hold_clears"] = True
    else:
        blockers.append("Min iteration/hold logic missing")
        findings["min_iteration_hold_clears"] = False

    # 3. TP preserve default
    tp_preserve_default = (
        'use-dynamic-tp-extension", action="store_true", default=False' in run_managed_src
    )
    if tp_preserve_default:
        ok_checks.append("TP preserve default (dynamic TP defaults to False)")
        findings["tp_preserve_default"] = True
    else:
        blockers.append("TP preserve default not enforced")
        findings["tp_preserve_default"] = False

    # 4. Dynamic TP opt-in exists
    dynamic_tp_opt_in = "--use-dynamic-tp-extension" in run_managed_src
    if dynamic_tp_opt_in:
        ok_checks.append("Dynamic TP opt-in CLI flag exists")
        findings["dynamic_tp_opt_in"] = True
    else:
        blockers.append("Dynamic TP opt-in missing")
        findings["dynamic_tp_opt_in"] = False

    # 5. TP extension paired with SL improvement
    tp_sl_paired = (
        "EXTEND_TP_AND_RAISE_SL" in profit_corridor_src
        and "RAISE_SL_ONLY" in profit_corridor_src
        and "tp_sl_pair_valid" in profit_corridor_src
    )
    if tp_sl_paired:
        ok_checks.append("TP extension paired with SL improvement")
        findings["tp_sl_paired"] = True
    else:
        blockers.append("TP/SL pairing missing")
        findings["tp_sl_paired"] = False

    # 6. SL profit floor enforced
    sl_profit_floor = (
        "sl_profit_floor_R" in profit_corridor_src
        and "locked_R" in profit_corridor_src
        and "SL_PROFIT_FLOOR_NOT_MET" in paired_builder_src
    )
    if sl_profit_floor:
        ok_checks.append("SL profit floor enforced (locked_R)")
        findings["sl_profit_floor"] = True
    else:
        blockers.append("SL profit floor missing")
        findings["sl_profit_floor"] = False

    # 7. No TP reduction
    no_tp_reduction = (
        "no_tp_reduction" in profit_corridor_src
        and "TP_REDUCTION_BLOCKED" in profit_corridor_src
        and "no_tp_reduction" in paired_builder_src
    )
    if no_tp_reduction:
        ok_checks.append("No TP reduction enforced")
        findings["no_tp_reduction"] = True
    else:
        blockers.append("No TP reduction check missing")
        findings["no_tp_reduction"] = False

    # 8. No SL widening
    no_sl_widening = (
        "no_sl_widening" in profit_corridor_src
        and "SL_WIDENING_BLOCKED" in profit_corridor_src
        and "no_sl_widening" in paired_builder_src
    )
    if no_sl_widening:
        ok_checks.append("No SL widening enforced")
        findings["no_sl_widening"] = True
    else:
        blockers.append("No SL widening check missing")
        findings["no_sl_widening"] = False

    # 9. No tick chasing
    no_tick_chasing = (
        "MFE_NOT_IMPROVING" in profit_corridor_src
        and "no tick chasing" in profit_corridor_src.lower()
    )
    if no_tick_chasing:
        ok_checks.append("No tick chasing (MFE improving check)")
        findings["no_tick_chasing"] = True
    else:
        blockers.append("No tick chasing check missing")
        findings["no_tick_chasing"] = False

    # 10. Cooldown/hysteresis
    cooldown_hysteresis = (
        "tp_extension_cooldown_seconds" in profit_corridor_src
        and "COOLDOWN_ACTIVE" in profit_corridor_src
    )
    if cooldown_hysteresis:
        ok_checks.append("Cooldown/hysteresis for TP extension")
        findings["cooldown_hysteresis"] = True
    else:
        blockers.append("Cooldown/hysteresis missing")
        findings["cooldown_hysteresis"] = False

    # 11. Spread/news freeze blocks
    spread_news_blocks = (
        "SPREAD_SPIKE_FLAG_ACTIVE" in profit_corridor_src
        and "NEWS_FLAG_ACTIVE" in profit_corridor_src
    )
    if spread_news_blocks:
        ok_checks.append("Spread/news freeze blocks for TP extension")
        findings["spread_news_blocks"] = True
    else:
        blockers.append("Spread/news freeze blocks missing")
        findings["spread_news_blocks"] = False

    # 12. Monitor lifecycle
    monitor_lifecycle = (
        "monitor_iterations" in run_managed_src
        and "monitor_stop_reason" in run_managed_src
        and "TIMEOUT" in run_managed_src
    )
    if monitor_lifecycle:
        ok_checks.append("Monitor lifecycle fields present")
        findings["monitor_lifecycle"] = True
    else:
        blockers.append("Monitor lifecycle missing")
        findings["monitor_lifecycle"] = False

    # 13. Receipt/forensics strict matching
    receipt_forensics_strict = (
        "EXPLICIT_POSITION_ID_NOT_FOUND" in forensics_src
        and "RECEIPT_TRADE_NOT_FOUND_IN_HISTORY_OR_OPEN_POSITIONS" in forensics_src
        and "fallback_used" in forensics_src
    )
    if receipt_forensics_strict:
        ok_checks.append("Receipt/forensics strict matching (no fallback)")
        findings["receipt_forensics_strict"] = True
    else:
        blockers.append("Receipt/forensics strict matching missing")
        findings["receipt_forensics_strict"] = False

    # 14. No martingale/grid/averaging
    forbidden_terms = ["martingale", "grid_trade", "averaging_down", "double_lot",
                       "add_position", "loss_based_lot", "recovery_multiplier"]
    found_forbidden = []
    for fname, src in [
        ("orchestrator", orchestrator_src),
        ("run_managed", run_managed_src),
        ("adaptive_policy", adaptive_policy_src),
        ("profit_corridor", profit_corridor_src),
        ("paired_builder", paired_builder_src),
        ("simulate", simulate_src),
    ]:
        code = _strip(src).lower()
        for term in forbidden_terms:
            if term in code:
                # Allow if explicitly negated
                idx = code.find(term)
                ctx = code[max(0, idx-30):idx+30]
                if f"no {term}" not in ctx and f"not {term}" not in ctx and "forbid" not in ctx:
                    found_forbidden.append(f"{fname}:{term}")
    if not found_forbidden:
        ok_checks.append("No martingale/grid/averaging in any exit module")
        findings["no_martingale_grid_averaging"] = True
    else:
        blockers.append(f"Forbidden terms found: {found_forbidden}")
        findings["no_martingale_grid_averaging"] = False

    # 15. No loss-based lot multiplier
    no_loss_lot = (
        "loss_based_lot" not in _strip(profit_corridor_src).lower()
        and "double_after_loss" not in _strip(profit_corridor_src).lower()
        and "loss_multiplier" not in _strip(profit_corridor_src).lower()
    )
    if no_loss_lot:
        ok_checks.append("No loss-based lot multiplier")
        findings["no_loss_based_lot_multiplier"] = True
    else:
        blockers.append("Loss-based lot multiplier detected")
        findings["no_loss_based_lot_multiplier"] = False

    # 16. Adaptive profit corridor module exists
    corridor_exists = (REPO_ROOT / "titan" / "production" / "adaptive_profit_corridor.py").exists()
    if corridor_exists:
        ok_checks.append("Adaptive profit corridor module exists")
        findings["corridor_module_exists"] = True
    else:
        blockers.append("Adaptive profit corridor module missing")
        findings["corridor_module_exists"] = False

    # 17. Paired SLTP modify builder exists
    paired_exists = (REPO_ROOT / "titan" / "production" / "paired_sltp_modify_builder.py").exists()
    if paired_exists:
        ok_checks.append("Paired SLTP modify builder module exists")
        findings["paired_builder_exists"] = True
    else:
        blockers.append("Paired SLTP modify builder module missing")
        findings["paired_builder_exists"] = False

    # 18. Adaptive scenarios include profit corridor scenarios
    corridor_scenarios = (
        "tp_extension_disabled_preserve" in simulate_src
        and "profit_2R_trend_extend_tp_and_raise_sl" in simulate_src
        and "tp_extension_blocked_by_spread" in simulate_src
        and "no_tick_chasing" in simulate_src
    )
    if corridor_scenarios:
        ok_checks.append("Adaptive scenarios include profit corridor scenarios")
        findings["corridor_scenarios"] = True
    else:
        blockers.append("Profit corridor scenarios missing")
        findings["corridor_scenarios"] = False

    # Determine verdict
    if not blockers:
        dynamic_tp_complete = (
            findings.get("dynamic_tp_opt_in")
            and findings.get("tp_sl_paired")
            and findings.get("sl_profit_floor")
            and findings.get("no_tp_reduction")
            and findings.get("no_sl_widening")
            and findings.get("no_tick_chasing")
            and findings.get("cooldown_hysteresis")
            and findings.get("spread_news_blocks")
            and findings.get("corridor_module_exists")
            and findings.get("paired_builder_exists")
            and findings.get("corridor_scenarios")
        )
        if dynamic_tp_complete:
            verdict = "INTEGRATED_EXIT_VALIDATION_READY_DYNAMIC_TP_OPT_IN"
        else:
            verdict = "INTEGRATED_EXIT_VALIDATION_READY"
    else:
        verdict = "INTEGRATED_EXIT_VALIDATION_BLOCKED"

    return {
        "timestamp_utc": ts,
        "verdict": verdict,
        "ok_checks": ok_checks,
        "blockers": blockers,
        "warnings": warnings,
        "findings": findings,
        "safety": {
            "order_send_called": False,
            "position_modified": False,
        },
    }


def write_report(result: dict) -> dict:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUTPUT_DIR / "integrated_exit_validation.json"
    md_path = OUTPUT_DIR / "integrated_exit_validation.md"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str, ensure_ascii=False)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# TITAN XAU AI - Integrated Exit Validation\n\n")
        f.write(f"**Verdict:** **{result['verdict']}**\n\n")
        f.write(f"**Timestamp:** {result['timestamp_utc']}\n\n")
        f.write("## Findings\n\n")
        f.write("| Check | Status |\n|---|---|\n")
        for k, v in result.get("findings", {}).items():
            if isinstance(v, bool):
                status = "PASS" if v else "FAIL"
                f.write(f"| {k} | {status} |\n")
        if result.get("ok_checks"):
            f.write("\n## OK Checks\n\n")
            for c in result["ok_checks"]:
                f.write(f"- {c}\n")
        if result.get("blockers"):
            f.write("\n## Blockers\n\n")
            for b in result["blockers"]:
                f.write(f"- **{b}**\n")
        f.write("\n## Safety\n\n")
        f.write("- order_send_called: False\n")
        f.write("- position_modified: False\n")
    return {"json_path": str(json_path), "md_path": str(md_path)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Integrated exit validation (no MT5, no order_send)")
    args = parser.parse_args()
    print("=" * 70)
    print("  TITAN XAU AI - Integrated Exit Validation (Sprint 9.9.3.45.8.2)")
    print("=" * 70)
    result = run_validation()
    report = write_report(result)
    print(f"\n  Verdict: {result['verdict']}")
    print(f"  OK checks: {len(result.get('ok_checks', []))}")
    print(f"  Blockers: {len(result.get('blockers', []))}")
    if result.get("blockers"):
        print("\n  Blockers:")
        for b in result["blockers"]:
            print(f"    - {b}")
    print(f"\n  JSON: {report['json_path']}")
    print(f"  MD:   {report['md_path']}")
    print("\n" + "=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
