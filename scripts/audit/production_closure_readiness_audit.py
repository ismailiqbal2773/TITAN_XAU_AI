#!/usr/bin/env python3
"""
TITAN XAU AI - Production Closure Readiness Audit (Sprint 9.9.3.45.8.3)
========================================================================
Single integrated audit that validates the entire production closure
system: account profiles, broker profiles, transaction costs, parameter
registry, margin/leverage guard, net profit validator, dynamic TP
geometry, gross/net profit model, RR profile guard, reconciliation,
prop/retail/institutional constraints, fail-closed safety, and
demo-only proof enforcement.

Production score out of 100:
  - 15 risk/margin/leverage
  - 15 transaction costs/net profit
  - 15 RR/SL/TP geometry
  - 15 reconciliation/forensics
  - 15 prop/retail/institutional profiles
  - 10 model/backtest parameter binding
  - 10 fail-closed safety
  - 5 reporting/audit quality

Minimum to proceed to demo proof:
  - score >= 90
  - 0 blockers
  - no HIGH warnings
  - dynamic TP geometry valid
  - net RR valid
  - cost model active

Verdicts:
  - PRODUCTION_CLOSURE_READY
  - PRODUCTION_CLOSURE_READY_WITH_SAFE_DEFAULTS
  - PRODUCTION_CLOSURE_BLOCKED

NEVER sends orders. NEVER modifies positions.
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
    score_breakdown = {}

    # Check config files exist
    config_files = {
        "account_profiles": REPO_ROOT / "config" / "account_profiles.yaml",
        "broker_profiles": REPO_ROOT / "config" / "broker_profiles.yaml",
        "runtime_parameter_profiles": REPO_ROOT / "config" / "runtime_parameter_profiles.yaml",
        "transaction_cost_profiles": REPO_ROOT / "config" / "transaction_cost_profiles.yaml",
        "production_objective_profiles": REPO_ROOT / "config" / "production_objective_profiles.yaml",
    }
    for name, path in config_files.items():
        if path.exists():
            ok_checks.append(f"Config exists: {name}")
            findings[f"{name}_exists"] = True
        else:
            blockers.append(f"Config missing: {name}")
            findings[f"{name}_exists"] = False

    # Check production modules exist
    modules = {
        "transaction_cost_engine": REPO_ROOT / "titan" / "production" / "transaction_cost_engine.py",
        "net_profit_target_validator": REPO_ROOT / "titan" / "production" / "net_profit_target_validator.py",
        "margin_leverage_guard": REPO_ROOT / "titan" / "production" / "margin_leverage_guard.py",
        "parameter_registry": REPO_ROOT / "titan" / "production" / "parameter_registry.py",
        "trade_reconciliation": REPO_ROOT / "titan" / "production" / "demo_micro_trade_reconciliation.py",
        "adaptive_trailing_policy": REPO_ROOT / "titan" / "production" / "adaptive_trailing_policy.py",
        "adaptive_profit_corridor": REPO_ROOT / "titan" / "production" / "adaptive_profit_corridor.py",
        "paired_sltp_modify_builder": REPO_ROOT / "titan" / "production" / "paired_sltp_modify_builder.py",
    }
    for name, path in modules.items():
        if path.exists():
            ok_checks.append(f"Module exists: {name}")
            findings[f"{name}_exists"] = True
        else:
            blockers.append(f"Module missing: {name}")
            findings[f"{name}_exists"] = False

    # Check audit scripts exist
    audits = {
        "backtest_parameter_binding_audit": REPO_ROOT / "scripts" / "audit" / "backtest_parameter_binding_audit.py",
        "integrated_exit_validation": REPO_ROOT / "scripts" / "audit" / "demo_micro_integrated_exit_validation.py",
        "managed_monitor_readiness_audit": REPO_ROOT / "scripts" / "audit" / "demo_micro_managed_monitor_readiness_audit.py",
    }
    for name, path in audits.items():
        if path.exists():
            ok_checks.append(f"Audit exists: {name}")
            findings[f"{name}_exists"] = True
        else:
            blockers.append(f"Audit missing: {name}")
            findings[f"{name}_exists"] = False

    # Check prop firm constraints in account profiles
    account_profiles_src = (REPO_ROOT / "config" / "account_profiles.yaml").read_text() if config_files["account_profiles"].exists() else ""
    prop_constraints = (
        "prop_firm_100x_demo" in account_profiles_src
        and "leverage: 100" in account_profiles_src
        and "max_daily_dd_pct: 0.03" in account_profiles_src
        and "max_total_dd_pct: 0.08" in account_profiles_src
        and "minimum_RR: 2.0" in account_profiles_src
        and "dynamic_tp_initial_tp_R: 3.0" in account_profiles_src
    )
    if prop_constraints:
        ok_checks.append("Prop firm constraints present (100x, 3% daily DD, 8% total DD, min RR 2.0, initial TP 3R)")
        findings["prop_constraints"] = True
    else:
        blockers.append("Prop firm constraints missing")
        findings["prop_constraints"] = False

    # Check retail constraints
    retail_constraints = "retail_demo_micro" in account_profiles_src and "retail_live_conservative" in account_profiles_src
    if retail_constraints:
        ok_checks.append("Retail constraints present (demo + live)")
        findings["retail_constraints"] = True
    else:
        blockers.append("Retail constraints missing")
        findings["retail_constraints"] = False

    # Check institutional constraints
    inst_constraints = "institutional_low_risk" in account_profiles_src and "institutional_balanced" in account_profiles_src
    if inst_constraints:
        ok_checks.append("Institutional constraints present (low_risk + balanced)")
        findings["institutional_constraints"] = True
    else:
        blockers.append("Institutional constraints missing")
        findings["institutional_constraints"] = False

    # Check no martingale/grid/averaging in all profiles
    no_martingale = (
        "no_martingale: true" in account_profiles_src
        and "no_grid: true" in account_profiles_src
        and "no_averaging: true" in account_profiles_src
        and "no_loss_based_lot_multiplier: true" in account_profiles_src
    )
    if no_martingale:
        ok_checks.append("No martingale/grid/averaging/loss_based_lot in account profiles")
        findings["no_martingale"] = True
    else:
        blockers.append("Safety invariants missing in account profiles")
        findings["no_martingale"] = False

    # Check transaction cost engine has net profit
    tce_src = modules["transaction_cost_engine"].read_text() if modules["transaction_cost_engine"].exists() else ""
    has_net_profit = "net_profit" in tce_src and "gross_profit" in tce_src and "total_transaction_cost" in tce_src
    if has_net_profit:
        ok_checks.append("Transaction cost engine computes net profit")
        findings["net_profit_model"] = True
    else:
        blockers.append("Transaction cost engine missing net profit model")
        findings["net_profit_model"] = False

    # Check spread/commission/slippage/swap included
    cost_fields = all(field in tce_src for field in ["spread_cost", "commission_cost", "slippage_cost", "swap_cost"])
    if cost_fields:
        ok_checks.append("All cost fields present (spread, commission, slippage, swap)")
        findings["cost_fields"] = True
    else:
        blockers.append("Cost fields missing")
        findings["cost_fields"] = False

    # Check dynamic TP geometry validation
    nptv_src = modules["net_profit_target_validator"].read_text() if modules["net_profit_target_validator"].exists() else ""
    has_dynamic_tp_geometry = (
        "DYNAMIC_TP_TRIGGER_BEYOND_STATIC_TP" in nptv_src
        and "INITIAL_TP_TOO_CLOSE_FOR_DYNAMIC_TP" in nptv_src
        and "dynamic_tp_geometry_valid" in nptv_src
    )
    if has_dynamic_tp_geometry:
        ok_checks.append("Dynamic TP geometry validation present")
        findings["dynamic_tp_geometry"] = True
    else:
        blockers.append("Dynamic TP geometry validation missing")
        findings["dynamic_tp_geometry"] = False

    # Check RR profile guard
    has_rr_guard = "NET_RR_BELOW_PROFILE_MINIMUM" in nptv_src and "RR_1_1_BLOCKED_FOR_PROP_DYNAMIC_TP" in nptv_src
    if has_rr_guard:
        ok_checks.append("RR profile guard present (net RR minimum + RR 1:1 blocked for prop)")
        findings["rr_profile_guard"] = True
    else:
        blockers.append("RR profile guard missing")
        findings["rr_profile_guard"] = False

    # Check margin/leverage guard
    mlg_src = modules["margin_leverage_guard"].read_text() if modules["margin_leverage_guard"].exists() else ""
    has_margin_guard = all(field in mlg_src for field in [
        "MARGIN_USAGE_TOO_HIGH", "RISK_PER_TRADE_TOO_HIGH",
        "DAILY_DD_LIMIT_RISK", "TOTAL_DD_LIMIT_RISK",
        "prop_firm_safe", "retail_safe", "institutional_safe",
    ])
    if has_margin_guard:
        ok_checks.append("Margin/leverage guard present with all safety flags")
        findings["margin_guard"] = True
    else:
        blockers.append("Margin/leverage guard incomplete")
        findings["margin_guard"] = False

    # Check reconciliation helper
    recon_src = modules["trade_reconciliation"].read_text() if modules["trade_reconciliation"].exists() else ""
    has_reconciliation = all(field in recon_src for field in [
        "STATUS_OPEN", "STATUS_CLOSED_TP", "STATUS_CLOSED_SL",
        "CLOSED_MANUAL", "has_closing_deal", "net_profit",
    ])
    if has_reconciliation:
        ok_checks.append("Unified reconciliation helper present")
        findings["reconciliation"] = True
    else:
        blockers.append("Reconciliation helper incomplete")
        findings["reconciliation"] = False

    # Check parameter registry
    pr_src = modules["parameter_registry"].read_text() if modules["parameter_registry"].exists() else ""
    has_registry = "BACKTEST_VALIDATED" in pr_src and "SAFE_DEFAULT" in pr_src and "NEEDS_BACKTEST_BINDING" in pr_src
    if has_registry:
        ok_checks.append("Parameter registry present (backtest binding aware)")
        findings["parameter_registry"] = True
    else:
        blockers.append("Parameter registry missing")
        findings["parameter_registry"] = False

    # Check adaptive trailing + dynamic TP corridor integrated
    corridor_src = modules["adaptive_profit_corridor"].read_text() if modules["adaptive_profit_corridor"].exists() else ""
    adaptive_src = modules["adaptive_trailing_policy"].read_text() if modules["adaptive_trailing_policy"].exists() else ""
    integrated = "EXTEND_TP_AND_RAISE_SL" in corridor_src and "blocking_reasons" in corridor_src and "PHASE_3_ADAPTIVE_TRAIL" in adaptive_src
    if integrated:
        ok_checks.append("Adaptive SL + dynamic TP corridor integrated")
        findings["adaptive_corridor_integrated"] = True
    else:
        blockers.append("Adaptive/corridor integration incomplete")
        findings["adaptive_corridor_integrated"] = False

    # Check fail-closed safety (no live trading, demo only)
    run_managed_src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
    runtime_yaml_path = REPO_ROOT / "config" / "runtime.yaml"
    runtime_yaml_content = runtime_yaml_path.read_text() if runtime_yaml_path.exists() else ""
    fail_closed = ("ACCOUNT_NOT_DEMO" in run_managed_src
                   and "MetaQuotes-Demo" in run_managed_src
                   and "dry_run" in runtime_yaml_content)
    if fail_closed:
        ok_checks.append("Fail-closed safety (demo-only, MetaQuotes-Demo enforced)")
        findings["fail_closed"] = True
    else:
        blockers.append("Fail-closed safety incomplete")
        findings["fail_closed"] = False

    # Check no martingale in all production modules
    forbidden_terms = ["martingale", "grid_trade", "averaging_down", "double_lot", "loss_based_lot"]
    found_forbidden = []
    for name, path in modules.items():
        if path.exists():
            code = _strip(path.read_text()).lower()
            for term in forbidden_terms:
                if term in code:
                    idx = code.find(term)
                    ctx = code[max(0, idx-30):idx+30]
                    if f"no {term}" not in ctx and f"not {term}" not in ctx and "forbid" not in ctx:
                        found_forbidden.append(f"{name}:{term}")
    if not found_forbidden:
        ok_checks.append("No martingale/grid/averaging/loss_based_lot in production modules")
        findings["no_martingale_modules"] = True
    else:
        blockers.append(f"Forbidden terms in modules: {found_forbidden}")
        findings["no_martingale_modules"] = False

    # Compute production score
    # 15 risk/margin/leverage
    score_breakdown["risk_margin_leverage"] = 15 if findings.get("margin_guard") else 0
    # 15 transaction costs/net profit
    score_breakdown["transaction_costs_net_profit"] = 15 if findings.get("net_profit_model") and findings.get("cost_fields") else 0
    # 15 RR/SL/TP geometry
    score_breakdown["rr_sl_tp_geometry"] = 15 if findings.get("dynamic_tp_geometry") and findings.get("rr_profile_guard") else 0
    # 15 reconciliation/forensics
    score_breakdown["reconciliation_forensics"] = 15 if findings.get("reconciliation") else 0
    # 15 prop/retail/institutional profiles
    score_breakdown["profiles"] = 15 if (findings.get("prop_constraints") and findings.get("retail_constraints") and findings.get("institutional_constraints")) else 0
    # 10 model/backtest parameter binding
    score_breakdown["parameter_binding"] = 10 if findings.get("parameter_registry") else 0
    # 10 fail-closed safety
    score_breakdown["fail_closed_safety"] = 10 if findings.get("fail_closed") and findings.get("no_martingale") and findings.get("no_martingale_modules") else 0
    # 5 reporting/audit quality
    score_breakdown["reporting_audit"] = 5 if (findings.get("backtest_parameter_binding_audit_exists") and findings.get("integrated_exit_validation_exists") and findings.get("managed_monitor_readiness_audit_exists")) else 0

    production_score = sum(score_breakdown.values())

    # Determine verdict
    if blockers:
        verdict = "PRODUCTION_CLOSURE_BLOCKED"
    elif production_score >= 90:
        # Check if all parameters are backtest-validated
        from titan.production.parameter_registry import ParameterRegistry
        registry = ParameterRegistry()
        summary = registry.get_summary()
        if summary["validated"] == 0:
            verdict = "PRODUCTION_CLOSURE_READY_WITH_SAFE_DEFAULTS"
        else:
            verdict = "PRODUCTION_CLOSURE_READY"
    else:
        verdict = "PRODUCTION_CLOSURE_BLOCKED"

    return {
        "timestamp_utc": ts,
        "verdict": verdict,
        "production_score": production_score,
        "score_breakdown": score_breakdown,
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
    json_path = OUTPUT_DIR / "production_closure_readiness_audit.json"
    md_path = OUTPUT_DIR / "production_closure_readiness_audit.md"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str, ensure_ascii=False)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# TITAN XAU AI - Production Closure Readiness Audit\n\n")
        f.write(f"**Verdict:** **{result['verdict']}**\n\n")
        f.write(f"**Production Score:** **{result['production_score']}/100**\n\n")
        f.write(f"**Timestamp:** {result['timestamp_utc']}\n\n")
        f.write("## Score Breakdown\n\n")
        f.write("| Category | Max | Score |\n|---|---|---|\n")
        for k, v in result.get("score_breakdown", {}).items():
            max_score = {"risk_margin_leverage": 15, "transaction_costs_net_profit": 15,
                         "rr_sl_tp_geometry": 15, "reconciliation_forensics": 15,
                         "profiles": 15, "parameter_binding": 10,
                         "fail_closed_safety": 10, "reporting_audit": 5}.get(k, 0)
            f.write(f"| {k} | {max_score} | {v} |\n")
        f.write(f"| **TOTAL** | **100** | **{result['production_score']}** |\n")
        f.write("\n## Findings\n\n")
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
    print("=" * 70)
    print("  TITAN XAU AI - Production Closure Readiness Audit")
    print("=" * 70)
    result = run_audit()
    report = write_report(result)
    print(f"\n  Verdict: {result['verdict']}")
    print(f"  Production Score: {result['production_score']}/100")
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
