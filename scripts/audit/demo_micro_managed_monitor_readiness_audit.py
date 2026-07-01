#!/usr/bin/env python3
"""
TITAN XAU AI - Demo Micro Managed Monitor Readiness Audit (Sprint 9.9.3.45.6)
=============================================================================
Pre-execution readiness audit for managed monitor and SL modify apply path.

Verifies:
  - monitor duration > interval
  - monitor loop cannot complete after one HOLD if position open
  - apply path exists
  - apply path is gated
  - HOLD does not modify
  - MODIFY preserves TP
  - MODIFY favorable-only
  - MetaQuotes-Demo only
  - DEMO only
  - no martingale/grid/averaging

Verdicts:
  - MANAGED_MONITOR_READY
  - MANAGED_MONITOR_BLOCKED

NO order_send. NO modification. Pure static / source-code audit.
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


def run_audit() -> dict:
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
    manage_position_src = (REPO_ROOT / "scripts" / "operator" /
                            "manage_demo_micro_position.py").read_text()
    position_mgr_src = (REPO_ROOT / "titan" / "production" /
                        "demo_micro_position_manager.py").read_text()
    sl_modify_builder_src = (REPO_ROOT / "titan" / "production" /
                              "demo_micro_sl_modify_builder.py").read_text()

    # 1. monitor duration > interval (default values)
    # Default monitor_duration_minutes=30, monitor_interval_seconds=5
    # 30 minutes = 1800 seconds > 5 seconds
    if "monitor_duration_minutes" in run_managed_src and "monitor_interval_seconds" in run_managed_src:
        ok_checks.append("CLI overrides --monitor-duration-minutes and --monitor-interval-seconds present")
        findings["cli_overrides_present"] = True
    else:
        blockers.append("CLI overrides --monitor-duration-minutes or --monitor-interval-seconds missing")
        findings["cli_overrides_present"] = False

    # Check default values: 30 minutes duration, 5 seconds interval
    has_default_30 = "default=30" in run_managed_src
    has_default_5 = "default=5" in run_managed_src
    if has_default_30 and has_default_5:
        ok_checks.append("Default monitor duration=30min, interval=5s (duration > interval)")
        findings["default_duration_greater_than_interval"] = True
    else:
        blockers.append("Default monitor duration/interval missing or invalid")
        findings["default_duration_greater_than_interval"] = False

    # 2. monitor loop cannot complete after one HOLD if position open
    # Check that _run_monitor_loop uses a for-loop with max_iterations
    loop_idx = run_managed_src.find("def _run_monitor_loop")
    if loop_idx > 0:
        loop_end = run_managed_src.find("\ndef ", loop_idx + 1)
        loop_body = run_managed_src[loop_idx:loop_end if loop_end > 0 else len(run_managed_src)]
        # Must have for-loop with max_iterations
        if "for iteration in range(1, max_iterations + 1)" in loop_body:
            ok_checks.append("Monitor loop iterates up to max_iterations (does not exit after one HOLD)")
            findings["loop_iterates_max_iterations"] = True
        else:
            blockers.append("Monitor loop does not iterate to max_iterations")
            findings["loop_iterates_max_iterations"] = False
        # Must sleep between iterations
        if "_time.sleep" in loop_body:
            ok_checks.append("Monitor loop sleeps between iterations")
            findings["loop_sleeps_between_iterations"] = True
        else:
            blockers.append("Monitor loop does not sleep between iterations")
            findings["loop_sleeps_between_iterations"] = False
    else:
        blockers.append("_run_monitor_loop function not found")
        findings["loop_function_present"] = False

    # 3. apply path exists
    apply_path_exists = (
        "def run_apply_once" in manage_position_src
        and "TRADE_ACTION_SLTP" in manage_position_src
        and "mt5.order_send" in manage_position_src
    )
    if apply_path_exists:
        ok_checks.append("Apply path exists (run_apply_once + TRADE_ACTION_SLTP + mt5.order_send)")
        findings["apply_path_exists"] = True
    else:
        blockers.append("Apply path missing or incomplete")
        findings["apply_path_exists"] = False

    # 4. apply path is gated (must require confirm-local-operator,
    #    confirm-managed-trailing, valid token, DEMO account,
    #    MetaQuotes-Demo, one TITAN position)
    required_gates = [
        "confirm-local-operator",
        "confirm-managed-trailing",
        "LOCAL_TOKEN_INVALID",
        "ACCOUNT_NOT_DEMO",
        "BROKER_NOT_METAQUOTES_DEMO",
        "NO_OPEN_TITAN_POSITION",
        "MULTIPLE_TITAN_POSITIONS",
        "MAGIC_MISMATCH",
        "COMMENT_MISMATCH",
        "SYMBOL_MISMATCH",
    ]
    missing_gates = [g for g in required_gates if g not in manage_position_src]
    if not missing_gates:
        ok_checks.append("Apply path gated with all required checks")
        findings["apply_path_gated"] = True
        findings["required_gates_present"] = required_gates
    else:
        blockers.append(f"Apply path missing gates: {missing_gates}")
        findings["apply_path_gated"] = False
        findings["missing_gates"] = missing_gates

    # 5. HOLD does not modify
    hold_no_modify = (
        'rec.action == SLAction.HOLD' in manage_position_src
        and 'MANAGE_HOLD_NO_MODIFY' in manage_position_src
        and '"sl_modify_attempted": False' in manage_position_src
    )
    if hold_no_modify:
        ok_checks.append("HOLD action does not send modification")
        findings["hold_no_modify"] = True
    else:
        blockers.append("HOLD action may send modification")
        findings["hold_no_modify"] = False

    # 6. MODIFY preserves TP
    tp_preserve = (
        "TP_NOT_PRESERVED" in manage_position_src
        and "tp_preserved" in manage_position_src
    )
    if tp_preserve:
        ok_checks.append("MODIFY preserves TP (TP_NOT_PRESERVED blocker present)")
        findings["modify_preserves_tp"] = True
    else:
        blockers.append("MODIFY TP preservation check missing")
        findings["modify_preserves_tp"] = False

    # 7. MODIFY favorable-only
    favorable_only = (
        "UNFAVORABLE_SL_BLOCKED" in manage_position_src
        and "favorable" in manage_position_src
    )
    if favorable_only:
        ok_checks.append("MODIFY favorable-only (UNFAVORABLE_SL_BLOCKED blocker present)")
        findings["modify_favorable_only"] = True
    else:
        blockers.append("MODIFY favorable-only check missing")
        findings["modify_favorable_only"] = False

    # 8. No widening SL
    no_widening = "SL_WIDENING_BLOCKED" in manage_position_src
    if no_widening:
        ok_checks.append("SL widening blocked")
        findings["no_widening"] = True
    else:
        blockers.append("SL widening check missing")
        findings["no_widening"] = False

    # 9. MetaQuotes-Demo only
    mq_demo = "MetaQuotes-Demo" in manage_position_src
    if mq_demo:
        ok_checks.append("MetaQuotes-Demo broker required")
        findings["metaquotes_demo_only"] = True
    else:
        blockers.append("MetaQuotes-Demo broker check missing")
        findings["metaquotes_demo_only"] = False

    # 10. DEMO only
    demo_only = "ACCOUNT_NOT_DEMO" in manage_position_src and "trade_mode" in manage_position_src
    if demo_only:
        ok_checks.append("DEMO account required (trade_mode == 0)")
        findings["demo_only"] = True
    else:
        blockers.append("DEMO account check missing")
        findings["demo_only"] = False

    # 11. No martingale/grid/averaging in any source
    forbidden_terms = ["martingale", "grid_trade", "averaging_down", "double_lot", "add_position"]
    found_forbidden = []
    for fname, src in [
        ("orchestrator", orchestrator_src),
        ("run_managed", run_managed_src),
        ("manage_position", manage_position_src),
        ("position_manager", position_mgr_src),
        ("sl_modify_builder", sl_modify_builder_src),
    ]:
        code = _strip(src).lower()
        for term in forbidden_terms:
            if term in code:
                # Allow if explicitly negated (e.g., "no martingale")
                idx = code.find(term)
                ctx = code[max(0, idx-30):idx+30]
                if f"no {term}" not in ctx and f"not {term}" not in ctx and "forbid" not in ctx:
                    found_forbidden.append(f"{fname}:{term}")
    if not found_forbidden:
        ok_checks.append("No martingale/grid/averaging in source")
        findings["no_martingale_grid_averaging"] = True
    else:
        blockers.append(f"Forbidden terms found: {found_forbidden}")
        findings["no_martingale_grid_averaging"] = False

    # 12. position manager is favorable-only
    pm_favorable = "favorable" in position_mgr_src and "best_sl >= current_sl" in position_mgr_src
    if pm_favorable:
        ok_checks.append("Position manager favorable-only (best_sl >= current_sl for BUY)")
        findings["position_manager_favorable_only"] = True
    else:
        blockers.append("Position manager favorable-only check missing")
        findings["position_manager_favorable_only"] = False

    # 13. SL modify builder preserves TP
    slmb_tp = "TP must be > 0 (preserved)" in sl_modify_builder_src or "TP preserved" in sl_modify_builder_src
    if slmb_tp:
        ok_checks.append("SL modify builder preserves TP")
        findings["sl_modify_builder_preserves_tp"] = True
    else:
        blockers.append("SL modify builder TP preservation missing")
        findings["sl_modify_builder_preserves_tp"] = False

    # 14. Monitor loop supports apply path integration
    apply_integration = (
        "modify_applier" in run_managed_src
        and "_build_modify_applier" in run_managed_src
        and "apply_allowed" in run_managed_src
    )
    if apply_integration:
        ok_checks.append("Monitor loop supports SL modify apply integration")
        findings["apply_integration"] = True
    else:
        blockers.append("Monitor loop apply integration missing")
        findings["apply_integration"] = False

    # 15. Explicit stop reasons present
    required_stop_reasons = [
        "POSITION_CLOSED",
        "TIMEOUT",
        "KILL_SWITCH_BLOCKED",
        "GATE_BLOCKED",
        "ERROR",
    ]
    missing_reasons = [r for r in required_stop_reasons if r not in run_managed_src]
    if not missing_reasons:
        ok_checks.append("All explicit stop reasons present")
        findings["stop_reasons_present"] = required_stop_reasons
    else:
        blockers.append(f"Stop reasons missing: {missing_reasons}")
        findings["stop_reasons_missing"] = missing_reasons

    # === Sprint 9.9.3.45.8.1: adaptive trailing opt-in wiring checks ===

    # 16. Adaptive policy module exists
    adaptive_policy_path = REPO_ROOT / "titan" / "production" / "adaptive_trailing_policy.py"
    adaptive_module_exists = adaptive_policy_path.exists()
    if adaptive_module_exists:
        ok_checks.append("Adaptive trailing policy module exists")
        findings["adaptive_policy_module_exists"] = True
    else:
        blockers.append("Adaptive trailing policy module missing")
        findings["adaptive_policy_module_exists"] = False

    # 17. Adaptive runtime flag exists (--use-adaptive-trailing)
    adaptive_cli_flag = "--use-adaptive-trailing" in run_managed_src
    if adaptive_cli_flag:
        ok_checks.append("Adaptive runtime CLI flag (--use-adaptive-trailing) exists")
        findings["adaptive_cli_flag_exists"] = True
    else:
        blockers.append("Adaptive runtime CLI flag missing")
        findings["adaptive_cli_flag_exists"] = False

    # 18. Adaptive runtime wiring exists (use_adaptive_policy passed to orchestrator)
    adaptive_wiring = (
        "use_adaptive_policy" in run_managed_src
        and "adaptive_policy_kwargs" in run_managed_src
        and "_build_adaptive_policy_kwargs" in run_managed_src
    )
    if adaptive_wiring:
        ok_checks.append("Adaptive runtime wiring (use_adaptive_policy + kwargs) present")
        findings["adaptive_runtime_wiring"] = True
    else:
        blockers.append("Adaptive runtime wiring missing")
        findings["adaptive_runtime_wiring"] = False

    # 19. Legacy default preserved (use_adaptive_trailing defaults to False)
    legacy_default_preserved = (
        'use-adaptive-trailing", action="store_true", default=False' in run_managed_src
        or "use_adaptive_trailing\", action=\"store_true\", default=False" in run_managed_src
    )
    if legacy_default_preserved:
        ok_checks.append("Legacy default preserved (use_adaptive_trailing defaults to False)")
        findings["legacy_default_preserved"] = True
    else:
        blockers.append("Legacy default not preserved (use_adaptive_trailing should default to False)")
        findings["legacy_default_preserved"] = False

    # 20. Adaptive opt-in available (report shows adaptive_trailing_enabled field)
    adaptive_opt_in_available = "adaptive_trailing_config" in run_managed_src
    if adaptive_opt_in_available:
        ok_checks.append("Adaptive opt-in available (adaptive_trailing_config in report)")
        findings["adaptive_opt_in_available"] = True
    else:
        blockers.append("Adaptive opt-in not available (adaptive_trailing_config missing from report)")
        findings["adaptive_opt_in_available"] = False

    # 21. Adaptive policy mode CLI flag
    adaptive_mode_flag = "--adaptive-policy-mode" in run_managed_src
    if adaptive_mode_flag:
        ok_checks.append("Adaptive policy mode CLI flag (--adaptive-policy-mode) exists")
        findings["adaptive_mode_cli_flag"] = True
    else:
        blockers.append("Adaptive policy mode CLI flag missing")
        findings["adaptive_mode_cli_flag"] = False

    # 22. No martingale/grid/averaging in adaptive policy module
    if adaptive_module_exists:
        adaptive_src = adaptive_policy_path.read_text()
        adaptive_code = _strip(adaptive_src).lower()
        forbidden_adaptive = ["martingale", "grid_trade", "averaging_down",
                              "double_lot", "add_position", "loss_based_lot",
                              "recovery_multiplier"]
        found_forbidden_adaptive = []
        for term in forbidden_adaptive:
            if term in adaptive_code:
                found_forbidden_adaptive.append(term)
        if not found_forbidden_adaptive:
            ok_checks.append("No martingale/grid/averaging in adaptive policy module")
            findings["adaptive_no_martingale"] = True
        else:
            blockers.append(f"Forbidden terms in adaptive policy module: {found_forbidden_adaptive}")
            findings["adaptive_no_martingale"] = False

    # Determine verdict
    # Sprint 9.9.3.45.8.1: if all base checks pass AND adaptive opt-in
    # wiring is present, return MANAGED_MONITOR_READY_ADAPTIVE_OPT_IN.
    # If base checks pass but adaptive wiring missing, return
    # MANAGED_MONITOR_READY. If any blockers, return MANAGED_MONITOR_BLOCKED.
    if not blockers:
        adaptive_wiring_complete = (
            findings.get("adaptive_policy_module_exists")
            and findings.get("adaptive_cli_flag_exists")
            and findings.get("adaptive_runtime_wiring")
            and findings.get("legacy_default_preserved")
            and findings.get("adaptive_opt_in_available")
            and findings.get("adaptive_mode_cli_flag")
            and findings.get("adaptive_no_martingale", True)
        )
        if adaptive_wiring_complete:
            verdict = "MANAGED_MONITOR_READY_ADAPTIVE_OPT_IN"
        else:
            verdict = "MANAGED_MONITOR_READY"
    else:
        verdict = "MANAGED_MONITOR_BLOCKED"

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
    json_path = OUTPUT_DIR / "managed_monitor_readiness_audit.json"
    md_path = OUTPUT_DIR / "managed_monitor_readiness_audit.md"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str, ensure_ascii=False)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# TITAN XAU AI - Managed Monitor Readiness Audit\n\n")
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
    parser = argparse.ArgumentParser(description="Managed monitor readiness audit (no MT5, no order_send)")
    args = parser.parse_args()
    print("=" * 70)
    print("  TITAN XAU AI - Managed Monitor Readiness Audit (Sprint 9.9.3.45.6)")
    print("=" * 70)
    result = run_audit()
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
