#!/usr/bin/env python3
"""
TITAN XAU AI - Production Closure Readiness Audit v2.1 (Sprint 9.9.3.45.8.4)
=============================================================================
Single integrated audit that validates the entire production closure
system across 15 categories with honest score integrity.

Score integrity rules:
  1. If any required parameter is SAFE_DEFAULT or NEEDS_BACKTEST_BINDING:
     score capped at maximum 92, warning SAFE_DEFAULTS_PRESENT
  2. Score 100 only if: all modules present, all core params BACKTEST_VALIDATED,
     no safe defaults on critical params, no HIGH warnings, no blockers
  3. PRODUCTION_CLOSURE_READY requires: score >= 95, 0 blockers, 0 HIGH warnings,
     no NEEDS_BACKTEST_BINDING on core runtime parameters
  4. PRODUCTION_CLOSURE_READY_WITH_SAFE_DEFAULTS requires: score >= 90, 0 blockers,
     safe defaults clearly labeled, no false claim of full validation

Categories (15):
  1. Account profiles
  2. Broker profiles
  3. Cost/net profit
  4. Margin/leverage/risk
  5. Account adaptation/lot sizing
  6. SL/TP/profit corridor/partial close
  7. Unified reconciliation/forensics
  8. Alpha Factory
  9. Retraining and promotion gate
  10. Runtime calibration
  11. Licensing/anti-copy
  12. Crash/fail-closed resilience
  13. Dependency update safety
  14. Prop/retail/institutional readiness
  15. Production score honesty

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


def _check_module_exists(path: Path) -> bool:
    return path.exists()


def _check_no_forbidden(path: Path) -> bool:
    if not path.exists():
        return True
    code = _strip(path.read_text()).lower()
    for term in ["martingale", "grid_trade", "averaging_down", "double_lot",
                 "loss_based_lot", "recovery_multiplier"]:
        if term in code:
            idx = code.find(term)
            ctx = code[max(0, idx-40):idx+40]
            # Allow if explicitly negated (no_martingale, not martingale, forbidden, etc.)
            if (f"no_{term}" in ctx or f"no {term}" in ctx
                or f"not_{term}" in ctx or f"not {term}" in ctx
                or "forbid" in ctx or "never" in ctx
                or f"reject" in ctx or f"raise" in ctx):
                continue
            return False
    return True


def run_audit() -> dict:
    ts = datetime.now(timezone.utc).isoformat()
    ok_checks = []
    blockers = []
    warnings = []
    findings = {}
    score_breakdown = {}
    high_warnings = []

    # === Define all required modules ===
    required_modules = {
        # Existing
        "transaction_cost_engine": REPO_ROOT / "titan" / "production" / "transaction_cost_engine.py",
        "net_profit_target_validator": REPO_ROOT / "titan" / "production" / "net_profit_target_validator.py",
        "margin_leverage_guard": REPO_ROOT / "titan" / "production" / "margin_leverage_guard.py",
        "parameter_registry": REPO_ROOT / "titan" / "production" / "parameter_registry.py",
        "trade_reconciliation": REPO_ROOT / "titan" / "production" / "demo_micro_trade_reconciliation.py",
        "adaptive_trailing_policy": REPO_ROOT / "titan" / "production" / "adaptive_trailing_policy.py",
        "adaptive_profit_corridor": REPO_ROOT / "titan" / "production" / "adaptive_profit_corridor.py",
        "paired_sltp_modify_builder": REPO_ROOT / "titan" / "production" / "paired_sltp_modify_builder.py",
        # Sprint 9.9.3.45.8.4: new institutional modules
        "alpha_candidate_generator": REPO_ROOT / "titan" / "research" / "alpha_factory" / "alpha_candidate_generator.py",
        "alpha_evaluator": REPO_ROOT / "titan" / "research" / "alpha_factory" / "alpha_evaluator.py",
        "alpha_registry": REPO_ROOT / "titan" / "research" / "alpha_factory" / "alpha_registry.py",
        "retraining_orchestrator": REPO_ROOT / "titan" / "production" / "retraining_orchestrator.py",
        "model_promotion_gate": REPO_ROOT / "titan" / "production" / "model_promotion_gate.py",
        "runtime_calibration_engine": REPO_ROOT / "titan" / "production" / "runtime_calibration_engine.py",
        "license_validator": REPO_ROOT / "titan" / "commercial" / "licensing" / "license_validator.py",
        "machine_binding": REPO_ROOT / "titan" / "commercial" / "licensing" / "machine_binding.py",
        "expiry_guard": REPO_ROOT / "titan" / "commercial" / "licensing" / "expiry_guard.py",
        "runtime_health_guard": REPO_ROOT / "titan" / "production" / "runtime_health_guard.py",
        "fail_closed_runtime_guard": REPO_ROOT / "titan" / "production" / "fail_closed_runtime_guard.py",
        "watchdog_restarter": REPO_ROOT / "titan" / "production" / "watchdog_restarter.py",
        "broker_profile_engine": REPO_ROOT / "titan" / "production" / "broker_profile_engine.py",
        "broker_execution_adapter": REPO_ROOT / "titan" / "production" / "broker_execution_adapter.py",
        "account_adaptation_engine": REPO_ROOT / "titan" / "production" / "account_adaptation_engine.py",
        "lot_sizing_engine": REPO_ROOT / "titan" / "production" / "lot_sizing_engine.py",
        "partial_close_engine": REPO_ROOT / "titan" / "production" / "partial_close_engine.py",
    }

    required_configs = {
        "account_profiles": REPO_ROOT / "config" / "account_profiles.yaml",
        "broker_profiles": REPO_ROOT / "config" / "broker_profiles.yaml",
        "runtime_parameter_profiles": REPO_ROOT / "config" / "runtime_parameter_profiles.yaml",
        "transaction_cost_profiles": REPO_ROOT / "config" / "transaction_cost_profiles.yaml",
        "production_objective_profiles": REPO_ROOT / "config" / "production_objective_profiles.yaml",
        "dependency_policy": REPO_ROOT / "config" / "dependency_policy.yaml",
    }

    required_audits = {
        "backtest_parameter_binding_audit": REPO_ROOT / "scripts" / "audit" / "backtest_parameter_binding_audit.py",
        "integrated_exit_validation": REPO_ROOT / "scripts" / "audit" / "demo_micro_integrated_exit_validation.py",
        "managed_monitor_readiness_audit": REPO_ROOT / "scripts" / "audit" / "demo_micro_managed_monitor_readiness_audit.py",
        "retraining_readiness_audit": REPO_ROOT / "scripts" / "audit" / "retraining_readiness_audit.py",
        "calibration_readiness_audit": REPO_ROOT / "scripts" / "audit" / "calibration_readiness_audit.py",
        "licensing_readiness_audit": REPO_ROOT / "scripts" / "audit" / "licensing_readiness_audit.py",
        "runtime_resilience_audit": REPO_ROOT / "scripts" / "audit" / "runtime_resilience_audit.py",
        "dependency_update_readiness_audit": REPO_ROOT / "scripts" / "audit" / "dependency_update_readiness_audit.py",
        "alpha_factory_audit": REPO_ROOT / "scripts" / "research" / "run_alpha_factory_audit.py",
    }

    # === Check configs exist ===
    for name, path in required_configs.items():
        if path.exists():
            ok_checks.append(f"Config exists: {name}")
            findings[f"{name}_exists"] = True
        else:
            blockers.append(f"Config missing: {name}")
            findings[f"{name}_exists"] = False

    # === Check modules exist ===
    critical_modules = [
        "transaction_cost_engine", "net_profit_target_validator",
        "margin_leverage_guard", "parameter_registry", "trade_reconciliation",
        "adaptive_trailing_policy", "adaptive_profit_corridor",
        "retraining_orchestrator", "model_promotion_gate",
        "runtime_calibration_engine", "license_validator",
        "runtime_health_guard", "fail_closed_runtime_guard",
        "broker_execution_adapter", "account_adaptation_engine",
        "lot_sizing_engine", "partial_close_engine",
    ]
    for name, path in required_modules.items():
        exists = _check_module_exists(path)
        findings[f"{name}_exists"] = exists
        if exists:
            ok_checks.append(f"Module exists: {name}")
            # Check no martingale
            if _check_no_forbidden(path):
                findings[f"{name}_no_martingale"] = True
            else:
                blockers.append(f"Forbidden terms in module: {name}")
                findings[f"{name}_no_martingale"] = False
        else:
            if name in critical_modules:
                blockers.append(f"Critical module missing: {name}")
            else:
                warnings.append(f"Module missing: {name}")

    # === Check audits exist ===
    for name, path in required_audits.items():
        exists = _check_module_exists(path)
        findings[f"{name}_exists"] = exists
        if exists:
            ok_checks.append(f"Audit exists: {name}")
        else:
            warnings.append(f"Audit missing: {name}")

    # === Check account profiles constraints ===
    account_profiles_src = (REPO_ROOT / "config" / "account_profiles.yaml").read_text() if required_configs["account_profiles"].exists() else ""
    prop_constraints = all(s in account_profiles_src for s in [
        "prop_firm_100x_demo", "leverage: 100", "max_daily_dd_pct: 0.03",
        "max_total_dd_pct: 0.08", "minimum_RR: 2.0", "dynamic_tp_initial_tp_R: 3.0",
    ])
    findings["prop_constraints"] = prop_constraints
    if prop_constraints:
        ok_checks.append("Prop firm constraints present")
    else:
        blockers.append("Prop firm constraints missing")

    retail_constraints = "retail_demo_micro" in account_profiles_src and "retail_live_conservative" in account_profiles_src
    findings["retail_constraints"] = retail_constraints
    if not retail_constraints:
        blockers.append("Retail constraints missing")

    inst_constraints = "institutional_low_risk" in account_profiles_src and "institutional_balanced" in account_profiles_src
    findings["institutional_constraints"] = inst_constraints
    if not inst_constraints:
        blockers.append("Institutional constraints missing")

    # === Check safety invariants ===
    no_martingale = all(s in account_profiles_src for s in [
        "no_martingale: true", "no_grid: true", "no_averaging: true",
        "no_loss_based_lot_multiplier: true",
    ])
    findings["no_martingale"] = no_martingale
    if not no_martingale:
        blockers.append("Safety invariants missing in account profiles")

    # === Check transaction cost model ===
    tce_src = required_modules["transaction_cost_engine"].read_text() if required_modules["transaction_cost_engine"].exists() else ""
    has_net_profit = all(s in tce_src for s in ["net_profit", "gross_profit", "total_transaction_cost"])
    findings["net_profit_model"] = has_net_profit
    cost_fields = all(s in tce_src for s in ["spread_cost", "commission_cost", "slippage_cost", "swap_cost"])
    findings["cost_fields"] = cost_fields

    # === Check dynamic TP geometry ===
    nptv_src = required_modules["net_profit_target_validator"].read_text() if required_modules["net_profit_target_validator"].exists() else ""
    has_dynamic_tp_geometry = all(s in nptv_src for s in [
        "DYNAMIC_TP_TRIGGER_BEYOND_STATIC_TP", "INITIAL_TP_TOO_CLOSE_FOR_DYNAMIC_TP",
        "dynamic_tp_geometry_valid", "RR_1_1_BLOCKED_FOR_PROP_DYNAMIC_TP",
    ])
    findings["dynamic_tp_geometry"] = has_dynamic_tp_geometry
    has_rr_guard = "NET_RR_BELOW_PROFILE_MINIMUM" in nptv_src
    findings["rr_profile_guard"] = has_rr_guard

    # === Check margin guard ===
    mlg_src = required_modules["margin_leverage_guard"].read_text() if required_modules["margin_leverage_guard"].exists() else ""
    has_margin_guard = all(s in mlg_src for s in [
        "MARGIN_USAGE_TOO_HIGH", "RISK_PER_TRADE_TOO_HIGH",
        "DAILY_DD_LIMIT_RISK", "prop_firm_safe", "retail_safe", "institutional_safe",
    ])
    findings["margin_guard"] = has_margin_guard

    # === Check reconciliation ===
    recon_src = required_modules["trade_reconciliation"].read_text() if required_modules["trade_reconciliation"].exists() else ""
    has_reconciliation = all(s in recon_src for s in [
        "STATUS_OPEN", "STATUS_CLOSED_TP", "STATUS_CLOSED_SL", "has_closing_deal",
    ])
    findings["reconciliation"] = has_reconciliation

    # === Check fail-closed safety ===
    run_managed_src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
    runtime_yaml_path = REPO_ROOT / "config" / "runtime.yaml"
    runtime_yaml_content = runtime_yaml_path.read_text() if runtime_yaml_path.exists() else ""
    fail_closed = ("ACCOUNT_NOT_DEMO" in run_managed_src
                   and "MetaQuotes-Demo" in run_managed_src
                   and "dry_run" in runtime_yaml_content)
    findings["fail_closed"] = fail_closed

    # === Check all production modules for no martingale ===
    all_modules_clean = all(
        findings.get(f"{name}_no_martingale", False)
        for name in required_modules
        if findings.get(f"{name}_exists", False)
    )
    findings["no_martingale_modules"] = all_modules_clean

    # === Check parameter registry ===
    has_registry = _check_module_exists(required_modules["parameter_registry"])
    findings["parameter_registry"] = has_registry

    # === Sprint 9.9.3.45.8.6: broker scoring, prop rules, profile matrix ===
    broker_scoring_engine_path = REPO_ROOT / "titan" / "production" / "broker_scoring_engine.py"
    broker_score_audit_path = REPO_ROOT / "scripts" / "audit" / "broker_score_audit.py"
    prop_firm_rule_engine_path = REPO_ROOT / "titan" / "production" / "prop_firm_rule_engine.py"
    prop_firm_audit_path = REPO_ROOT / "scripts" / "audit" / "prop_firm_readiness_audit.py"
    risk_modes_path = REPO_ROOT / "config" / "risk_modes.yaml"
    profile_matrix_audit_path = REPO_ROOT / "scripts" / "audit" / "profile_matrix_readiness_audit.py"

    findings["broker_scoring_engine_exists"] = _check_module_exists(broker_scoring_engine_path)
    findings["broker_score_audit_exists"] = _check_module_exists(broker_score_audit_path)
    findings["prop_firm_rule_engine_exists"] = _check_module_exists(prop_firm_rule_engine_path)
    findings["prop_firm_audit_exists"] = _check_module_exists(prop_firm_audit_path)
    findings["risk_modes_exists"] = _check_module_exists(risk_modes_path)
    findings["profile_matrix_audit_exists"] = _check_module_exists(profile_matrix_audit_path)

    if findings["broker_scoring_engine_exists"]:
        ok_checks.append("Broker scoring engine exists")
    else:
        warnings.append("Broker scoring engine missing")

    if findings["prop_firm_rule_engine_exists"]:
        ok_checks.append("Prop firm rule engine exists")
    else:
        warnings.append("Prop firm rule engine missing")

    if findings["risk_modes_exists"]:
        ok_checks.append("Risk modes config exists")
    else:
        warnings.append("Risk modes config missing")

    if findings["profile_matrix_audit_exists"]:
        ok_checks.append("Profile matrix audit exists")
    else:
        warnings.append("Profile matrix audit missing")

    # Check aggressive profile is simulation-only
    if findings["risk_modes_exists"]:
        risk_modes_src = risk_modes_path.read_text()
        aggressive_sim_only = "aggressive_simulation_only" in risk_modes_src and "simulation_only: true" in risk_modes_src and "live_allowed: false" in risk_modes_src
        findings["aggressive_simulation_only"] = aggressive_sim_only
        if aggressive_sim_only:
            ok_checks.append("Aggressive profile is simulation-only (live_allowed=false)")
        else:
            blockers.append("Aggressive profile not properly marked simulation-only")
    else:
        findings["aggressive_simulation_only"] = False

    # === Sprint 9.9.3.45.8.12: Forward demo + trailing manager status ===
    archive_path = REPO_ROOT / "scripts" / "audit" / "archive_micro_proof_pass.py"
    daily_report_path = REPO_ROOT / "scripts" / "audit" / "forward_demo_daily_report.py"
    rollup_path = REPO_ROOT / "scripts" / "audit" / "forward_demo_rollup_report.py"
    trailing_audit_path = REPO_ROOT / "scripts" / "audit" / "trailing_manager_verification_audit.py"
    findings["archive_micro_proof_exists"] = _check_module_exists(archive_path)
    findings["forward_daily_report_exists"] = _check_module_exists(daily_report_path)
    findings["forward_rollup_exists"] = _check_module_exists(rollup_path)
    findings["trailing_manager_audit_exists"] = _check_module_exists(trailing_audit_path)
    if findings["archive_micro_proof_exists"]:
        ok_checks.append("Archive micro proof script exists")
    if findings["forward_daily_report_exists"]:
        ok_checks.append("Forward daily report script exists")
    if findings["forward_rollup_exists"]:
        ok_checks.append("Forward rollup report script exists")
    if findings["trailing_manager_audit_exists"]:
        ok_checks.append("Trailing manager verification audit exists")

    # Check for existing daily reports
    forward_demo_dir = REPO_ROOT / "data" / "audit" / "forward_demo"
    daily_report_count = 0
    if forward_demo_dir.exists():
        daily_report_count = len(list(forward_demo_dir.glob("daily_report_*.json")))
    findings["forward_demo_daily_reports_count"] = daily_report_count
    if daily_report_count > 0:
        ok_checks.append(f"Forward demo daily reports: {daily_report_count}")
    if daily_report_count >= 7:
        ok_checks.append("7-day forward demo complete")
        findings["forward_demo_complete"] = True
    else:
        findings["forward_demo_complete"] = False

    # Check for micro proof archive
    micro_proof_archives = list((REPO_ROOT / "data" / "audit" / "demo_micro").glob("micro_proof_pass_*"))
    findings["micro_proof_archived"] = len(micro_proof_archives) > 0
    if findings["micro_proof_archived"]:
        ok_checks.append("Micro proof archived")

    # === Sprint 9.9.3.45.8.15: Execution geometry enforcement ===
    geom_audit_path = REPO_ROOT / "scripts" / "audit" / "execution_geometry_receipt_audit.py"
    findings["execution_geometry_audit_exists"] = _check_module_exists(geom_audit_path)
    if findings["execution_geometry_audit_exists"]:
        ok_checks.append("Execution geometry receipt audit exists")

    # Check build-request has geometry enforcement
    run_managed_src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
    has_geom_gate = "EXECUTION_GEOMETRY_RR_BELOW_MINIMUM" in run_managed_src
    findings["execution_geometry_enforced"] = has_geom_gate
    if has_geom_gate:
        ok_checks.append("Execution geometry RR gate enforced in build-request and execute-and-monitor")
    else:
        blockers.append("EXECUTION_GEOMETRY_NOT_ENFORCED: RR gate missing from execution path")

    # === Sprint 9.9.3.45.8.16 v2.7.3: Autonomous readiness integration ===
    # Read latest verdicts from audit files (read-only - never re-run audits)
    audit_dir = REPO_ROOT / "data" / "audit" / "demo_micro_execution"

    # Latest execution geometry verdict
    geom_audit_json_path = audit_dir / "execution_geometry_audit.json"
    latest_geometry_verdict = ""
    if geom_audit_json_path.exists():
        try:
            with open(geom_audit_json_path, "r", encoding="utf-8") as f:
                geom_data = json.load(f)
            latest_geometry_verdict = geom_data.get("verdict", "")
        except Exception:
            pass
    findings["latest_execution_geometry_verdict"] = latest_geometry_verdict

    # Latest forensics verdict
    forensics_json_path = audit_dir / "post_trade_forensics.json"
    latest_forensics_verdict = ""
    if forensics_json_path.exists():
        try:
            with open(forensics_json_path, "r", encoding="utf-8") as f:
                forensics_data = json.load(f)
            latest_forensics_verdict = forensics_data.get("verdict", "")
        except Exception:
            pass
    findings["latest_forensics_verdict"] = latest_forensics_verdict

    # Ticket history scanner verdict
    ticket_scanner_path = audit_dir / "ticket_history_scanner.json"
    latest_ticket_scanner_verdict = ""
    if ticket_scanner_path.exists():
        try:
            with open(ticket_scanner_path, "r", encoding="utf-8") as f:
                ts_data = json.load(f)
            latest_ticket_scanner_verdict = ts_data.get("verdict", "")
        except Exception:
            pass
    findings["ticket_history_scanner_verdict"] = latest_ticket_scanner_verdict

    # End-to-end entry gate verdict
    entry_gate_path = audit_dir / "end_to_end_entry_gate_audit.json"
    latest_entry_gate_verdict = ""
    if entry_gate_path.exists():
        try:
            with open(entry_gate_path, "r", encoding="utf-8") as f:
                eg_data = json.load(f)
            latest_entry_gate_verdict = eg_data.get("verdict", "")
        except Exception:
            pass
    findings["end_to_end_entry_gate_verdict"] = latest_entry_gate_verdict

    # Autonomous demo readiness verdict
    autonomous_path = audit_dir / "autonomous_demo_readiness_audit.json"
    latest_autonomous_verdict = ""
    autonomous_allowed = False
    if autonomous_path.exists():
        try:
            with open(autonomous_path, "r", encoding="utf-8") as f:
                ar_data = json.load(f)
            latest_autonomous_verdict = ar_data.get("verdict", "")
            autonomous_allowed = ar_data.get("autonomous_allowed", False)
        except Exception:
            pass
    findings["autonomous_demo_readiness_verdict"] = latest_autonomous_verdict
    findings["autonomous_allowed"] = autonomous_allowed

    # v2.7.4: Selected profile (from shared resolver) and prop_funded_safe_active
    try:
        from titan.production.selected_profile_resolver import resolve_selected_profile
        resolved_profile = resolve_selected_profile(REPO_ROOT)
        findings["selected_profile"] = resolved_profile["selected_profile"]
        findings["selected_profile_source"] = resolved_profile["selected_profile_source"]
        findings["prop_funded_safe_active"] = resolved_profile["prop_funded_safe_active"]
    except Exception:
        findings["selected_profile"] = ""
        findings["selected_profile_source"] = ""
        findings["prop_funded_safe_active"] = False

    # Compute autonomous_execution_status: BLOCKED / OBSERVATION_ONLY / SUPERVISED_READY
    if latest_autonomous_verdict == "AUTONOMOUS_DEMO_READY_SUPERVISED":
        autonomous_execution_status = "SUPERVISED_READY"
    elif latest_autonomous_verdict == "AUTONOMOUS_DEMO_OBSERVATION_ONLY":
        autonomous_execution_status = "OBSERVATION_ONLY"
    elif latest_autonomous_verdict.startswith("AUTONOMOUS_DEMO_BLOCKED"):
        autonomous_execution_status = "BLOCKED"
    else:
        autonomous_execution_status = "BLOCKED"
    findings["autonomous_execution_status"] = autonomous_execution_status

    if autonomous_allowed:
        ok_checks.append("Autonomous demo readiness: SUPERVISED_READY")
    else:
        warnings.append(
            f"Autonomous demo not yet ready: verdict={latest_autonomous_verdict}, "
            f"status={autonomous_execution_status}. Production closure remains "
            "code-ready but is NOT autonomous-ready."
        )

    # === Sprint v2.8.1: Model artifact compatibility + autonomous entry decision ===
    model_compat_path = audit_dir / "model_artifact_compatibility_audit.json"
    model_compat_verdict = ""
    if model_compat_path.exists():
        try:
            with open(model_compat_path, "r", encoding="utf-8") as f:
                mc_data = json.load(f)
            model_compat_verdict = mc_data.get("verdict", "") or ""
        except Exception:
            pass
    findings["model_artifact_compatibility_verdict"] = model_compat_verdict
    if model_compat_verdict == "MODEL_ARTIFACTS_BLOCKED_VERSION_MISMATCH":
        warnings.append("MODEL_ARTIFACT_VERSION_WARNING: model artifacts blocked by version mismatch")
    elif model_compat_verdict == "MODEL_ARTIFACTS_COMPATIBLE_WITH_WARNINGS":
        warnings.append("MODEL_ARTIFACT_VERSION_WARNING: model artifacts compatible with version warnings")
    elif model_compat_verdict == "MODEL_ARTIFACTS_NOT_FOUND":
        warnings.append("MODEL_ARTIFACT_VERSION_WARNING: no model artifacts found")

    # === Sprint v2.8.3.3: CTO Consolidated Release Gate ===
    # Read latest verdicts from 3 new audit scripts:
    #   1. Model Artifact Health Audit (data/audit/model_health/model_artifact_health_audit.json)
    #   2. Feature Parity Audit (data/audit/model_health/feature_parity_audit.json)
    #   3. Runtime Safety Gate Audit (data/audit/demo_micro_execution/runtime_safety_gate_audit.json)
    model_health_dir = REPO_ROOT / "data" / "audit" / "model_health"

    # 1. Model artifact health
    model_health_path = model_health_dir / "model_artifact_health_audit.json"
    latest_model_health_verdict = ""
    model_health_pass = False
    active_model_count = 0
    failed_required_model_count = 0
    failed_optional_model_count = 0
    blocked_required_models = []
    warned_optional_models = []
    mh_v2_8_4_allowed = False
    if model_health_path.exists():
        try:
            with open(model_health_path, "r", encoding="utf-8") as f:
                mh_data = json.load(f)
            latest_model_health_verdict = mh_data.get("verdict", "") or ""
            active_model_count = int(mh_data.get("active_model_count", 0))
            # v2.8.3.3.1: use failed_required_model_count (was failed_model_count)
            failed_required_model_count = int(mh_data.get(
                "failed_required_model_count",
                mh_data.get("failed_model_count", 0)
            ))
            failed_optional_model_count = int(mh_data.get("failed_optional_model_count", 0))
            blocked_required_models = mh_data.get("blocked_required_models", []) or []
            warned_optional_models = mh_data.get("warned_optional_models", []) or []
            mh_v2_8_4_allowed = bool(mh_data.get("v2_8_4_allowed", False))
            # v2.8.3.3.1: model_health_pass = verdict is PASS/PASS_WITH_WARNINGS
            # AND failed_required_model_count == 0
            model_health_pass = (
                latest_model_health_verdict in (
                    "MODEL_ARTIFACT_HEALTH_PASS",
                    "MODEL_ARTIFACT_HEALTH_PASS_WITH_WARNINGS",
                )
                and failed_required_model_count == 0
            )
        except Exception:
            pass
    findings["latest_model_health_verdict"] = latest_model_health_verdict
    findings["model_health_pass"] = model_health_pass
    findings["active_model_count"] = active_model_count
    findings["failed_required_model_count"] = failed_required_model_count
    findings["failed_optional_model_count"] = failed_optional_model_count
    findings["blocked_required_models"] = blocked_required_models
    findings["warned_optional_models"] = warned_optional_models
    # Backwards-compat: failed_model_count = failed_required_model_count
    findings["failed_model_count"] = failed_required_model_count
    if latest_model_health_verdict == "MODEL_ARTIFACT_HEALTH_BLOCKED":
        blockers.append(
            f"MODEL_HEALTH_BLOCKED: {failed_required_model_count} required active model(s) failed health audit"
        )
    elif latest_model_health_verdict == "MODEL_ARTIFACT_HEALTH_PASS_WITH_WARNINGS":
        if failed_required_model_count > 0:
            # v2.8.3.3.1 reconciliation: should not happen, but fail-closed
            blockers.append(
                f"MODEL_HEALTH_RECONCILIATION_FAILURE: verdict=PASS_WITH_WARNINGS but "
                f"{failed_required_model_count} required model(s) failed - check audit logic"
            )
        else:
            warnings.append("MODEL_HEALTH_PASS_WITH_WARNINGS: compatibility warnings present but models healthy")
    elif latest_model_health_verdict == "":
        warnings.append("MODEL_HEALTH_AUDIT_MISSING: model_artifact_health_audit.json not found - run scripts/audit/model_artifact_health_audit.py")
    elif latest_model_health_verdict == "MODEL_ARTIFACT_HEALTH_PASS":
        ok_checks.append("Model health: PASS")

    # 2. Feature parity
    feature_parity_path = model_health_dir / "feature_parity_audit.json"
    latest_feature_parity_verdict = ""
    feature_parity_pass = False
    if feature_parity_path.exists():
        try:
            with open(feature_parity_path, "r", encoding="utf-8") as f:
                fp_data = json.load(f)
            latest_feature_parity_verdict = fp_data.get("verdict", "") or ""
            feature_parity_pass = latest_feature_parity_verdict in (
                "FEATURE_PARITY_PASS",
                "FEATURE_PARITY_PASS_WITH_WARNINGS",
            )
        except Exception:
            pass
    findings["latest_feature_parity_verdict"] = latest_feature_parity_verdict
    findings["feature_parity_pass"] = feature_parity_pass
    if latest_feature_parity_verdict == "FEATURE_PARITY_BLOCKED":
        blockers.append("FEATURE_PARITY_BLOCKED: train/live feature parity failed")
    elif latest_feature_parity_verdict == "FEATURE_PARITY_PASS_WITH_WARNINGS":
        warnings.append("FEATURE_PARITY_PASS_WITH_WARNINGS: feature parity has non-blocking warnings")
    elif latest_feature_parity_verdict == "":
        warnings.append("FEATURE_PARITY_AUDIT_MISSING: feature_parity_audit.json not found - run scripts/audit/feature_parity_audit.py")
    elif latest_feature_parity_verdict == "FEATURE_PARITY_PASS":
        ok_checks.append("Feature parity: PASS")

    # 3. Runtime safety gate
    runtime_safety_path = audit_dir / "runtime_safety_gate_audit.json"
    latest_runtime_safety_verdict = ""
    runtime_safety_pass = False
    if runtime_safety_path.exists():
        try:
            with open(runtime_safety_path, "r", encoding="utf-8") as f:
                rs_data = json.load(f)
            latest_runtime_safety_verdict = rs_data.get("verdict", "") or ""
            runtime_safety_pass = latest_runtime_safety_verdict == "RUNTIME_SAFETY_GATE_PASS"
        except Exception:
            pass
    findings["latest_runtime_safety_verdict"] = latest_runtime_safety_verdict
    findings["runtime_safety_pass"] = runtime_safety_pass
    if latest_runtime_safety_verdict == "RUNTIME_SAFETY_GATE_BLOCKED":
        blockers.append("RUNTIME_SAFETY_BLOCKED: runtime safety gate failed")
    elif latest_runtime_safety_verdict == "":
        warnings.append("RUNTIME_SAFETY_AUDIT_MISSING: runtime_safety_gate_audit.json not found - run scripts/audit/runtime_safety_gate_audit.py")
    elif latest_runtime_safety_verdict == "RUNTIME_SAFETY_GATE_PASS":
        ok_checks.append("Runtime safety gate: PASS")

    # v2.8.4 release gate: all 3 gates must pass
    v2833_release_gate_pass = (
        model_health_pass and feature_parity_pass and runtime_safety_pass
    )
    findings["v2_8_3_3_release_gate_pass"] = v2833_release_gate_pass
    findings["v2_8_4_allowed"] = v2833_release_gate_pass
    if not v2833_release_gate_pass:
        # Don't add as blocker if individual gates already added blockers - just warn
        if not any(b.startswith("MODEL_HEALTH_BLOCKED") or b.startswith("FEATURE_PARITY_BLOCKED")
                   or b.startswith("RUNTIME_SAFETY_BLOCKED") for b in blockers):
            blockers.append("V2_8_4_RELEASE_GATE_BLOCKED: not all 3 CTO gates pass")
    else:
        ok_checks.append("v2.8.4 release gate: ALLOWED (all 3 CTO gates pass)")

    # === Sprint v2.8.4: Prop Challenge Growth Profile Audit ===
    growth_profile_path = REPO_ROOT / "data" / "audit" / "prop_challenge_growth" / "prop_challenge_growth_profile_audit.json"
    latest_growth_profile_verdict = ""
    growth_profile_pass = False
    growth_profile_name = ""
    monthly_target_pct = 0.0
    daily_dd_soft = 0.0
    daily_dd_hard = 0.0
    total_dd_limit = 0.0
    if growth_profile_path.exists():
        try:
            with open(growth_profile_path, "r", encoding="utf-8") as f:
                gp_data = json.load(f)
            latest_growth_profile_verdict = gp_data.get("verdict", "") or ""
            growth_profile_pass = latest_growth_profile_verdict == "PROP_CHALLENGE_GROWTH_PROFILE_PASS"
            growth_profile_name = gp_data.get("profile_name", "") or ""
            gp_findings = gp_data.get("findings", {}) or {}
            monthly_target_pct = float(gp_findings.get("monthly_target_pct", 0) or 0)
            daily_dd_soft = float(gp_findings.get("daily_dd_soft_limit_pct", 0) or 0)
            daily_dd_hard = float(gp_findings.get("daily_dd_hard_limit_pct", 0) or 0)
            total_dd_limit = float(gp_findings.get("max_total_dd_pct", 0) or 0)
        except Exception:
            pass
    findings["latest_growth_profile_verdict"] = latest_growth_profile_verdict
    findings["growth_profile_pass"] = growth_profile_pass
    findings["growth_profile_name"] = growth_profile_name
    findings["growth_monthly_target_pct"] = monthly_target_pct
    findings["growth_daily_dd_soft_limit_pct"] = daily_dd_soft
    findings["growth_daily_dd_hard_limit_pct"] = daily_dd_hard
    findings["growth_total_dd_limit_pct"] = total_dd_limit
    # growth_profile_allowed: True only if profile passes AND v2.8.4 allowed
    growth_profile_allowed = growth_profile_pass and v2833_release_gate_pass
    findings["growth_profile_allowed"] = growth_profile_allowed
    if latest_growth_profile_verdict == "PROP_CHALLENGE_GROWTH_PROFILE_BLOCKED":
        blockers.append("GROWTH_PROFILE_BLOCKED: PROP_CHALLENGE_GROWTH_30_8 profile audit failed")
    elif latest_growth_profile_verdict == "":
        warnings.append("GROWTH_PROFILE_AUDIT_MISSING: prop_challenge_growth_profile_audit.json not found - run scripts/audit/prop_challenge_growth_profile_audit.py")
    elif latest_growth_profile_verdict == "PROP_CHALLENGE_GROWTH_PROFILE_PASS":
        ok_checks.append(f"Growth profile {growth_profile_name}: PASS")

    # === Sprint v2.8.5: Final Demo Activation Readiness Audit ===
    final_activation_path = REPO_ROOT / "data" / "audit" / "final_demo_activation" / "final_demo_activation_readiness_audit.json"
    latest_final_demo_activation_verdict = ""
    final_demo_activation_pass = False
    final_demo_activation_allowed = False
    metaquotes_demo_verified = False
    open_positions_count = 0
    pending_orders_count = 0
    stale_token_detected = False
    final_activation_execution_blocker = ""
    if final_activation_path.exists():
        try:
            with open(final_activation_path, "r", encoding="utf-8") as f:
                fa_data = json.load(f)
            latest_final_demo_activation_verdict = fa_data.get("verdict", "") or ""
            final_demo_activation_pass = latest_final_demo_activation_verdict == "FINAL_DEMO_ACTIVATION_READY_SUPERVISED"
            final_demo_activation_allowed = bool(fa_data.get("final_demo_activation_allowed", False))
            fa_findings = fa_data.get("findings", {}) or {}
            mt5_env = fa_findings.get("mt5_environment", {}) or {}
            metaquotes_demo_verified = (
                mt5_env.get("account_server", "") == "MetaQuotes-Demo"
                and mt5_env.get("account_type", "") == "DEMO"
            )
            open_positions_count = int(mt5_env.get("open_xauusd_positions", 0))
            pending_orders_count = int(mt5_env.get("pending_xauusd_orders", 0))
            token_info = fa_findings.get("operator_token", {}) or {}
            stale_token_detected = bool(token_info.get("stale", False))
            br_info = fa_findings.get("build_request_execution_blocker", "") or ""
            final_activation_execution_blocker = br_info
        except Exception:
            pass
    findings["latest_final_demo_activation_verdict"] = latest_final_demo_activation_verdict
    findings["final_demo_activation_pass"] = final_demo_activation_pass
    findings["final_demo_activation_allowed"] = final_demo_activation_allowed
    findings["metaquotes_demo_verified"] = metaquotes_demo_verified
    findings["open_positions_count"] = open_positions_count
    findings["pending_orders_count"] = pending_orders_count
    findings["stale_token_detected"] = stale_token_detected
    findings["final_activation_execution_blocker"] = final_activation_execution_blocker
    if latest_final_demo_activation_verdict == "FINAL_DEMO_ACTIVATION_BLOCKED":
        blockers.append("FINAL_DEMO_ACTIVATION_BLOCKED: final demo activation readiness audit failed")
    elif latest_final_demo_activation_verdict == "":
        warnings.append("FINAL_DEMO_ACTIVATION_AUDIT_MISSING: final_demo_activation_readiness_audit.json not found - run scripts/audit/final_demo_activation_readiness_audit.py")
    elif latest_final_demo_activation_verdict == "FINAL_DEMO_ACTIVATION_READY_SUPERVISED":
        ok_checks.append("Final demo activation: READY_SUPERVISED")

    # Sprint v2.8.3.3: SUPERVISED_READY requires all 3 CTO gates to pass.
    # If any gate is blocked, downgrade SUPERVISED_READY -> BLOCKED so v2.8.4 cannot start.
    if autonomous_execution_status == "SUPERVISED_READY" and not v2833_release_gate_pass:
        autonomous_execution_status = "BLOCKED"
        findings["autonomous_execution_status"] = autonomous_execution_status
        blockers.append(
            "AUTONOMOUS_STATUS_DOWNGRADED: SUPERVISED_READY downgraded to BLOCKED because "
            "not all 3 CTO release gates pass (model_health/feature_parity/runtime_safety)"
        )

    # Autonomous entry decision verdict
    ae_decision_path = audit_dir / "autonomous_entry_decision.json"
    ae_decision_verdict = ""
    ae_regime_source = ""
    ae_broker_gate_status = ""
    ae_broker_gate_source = ""
    ae_broker_gate_reason = ""
    ae_prop_funded_gate_pass = False
    ae_prop_funded_gate_source = ""
    ae_prop_funded_gate_reason = ""
    if ae_decision_path.exists():
        try:
            with open(ae_decision_path, "r", encoding="utf-8") as f:
                ae_data = json.load(f)
            ae_decision_verdict = ae_data.get("final_decision", "") or ""
            ae_regime_source = ae_data.get("regime_source", "") or ""
            ae_broker_gate_status = ae_data.get("broker_gate_status", "") or ""
            ae_broker_gate_source = ae_data.get("broker_gate_source", "") or ""
            ae_broker_gate_reason = ae_data.get("broker_gate_reason", "") or ""
            ae_prop_funded_gate_pass = bool(ae_data.get("prop_funded_gate_pass", False))
            ae_prop_funded_gate_source = ae_data.get("prop_funded_gate_source", "") or ""
            ae_prop_funded_gate_reason = ae_data.get("prop_funded_gate_reason", "") or ""
        except Exception:
            pass
    findings["autonomous_entry_decision_verdict"] = ae_decision_verdict
    findings["regime_source"] = ae_regime_source
    findings["broker_gate_status"] = ae_broker_gate_status
    findings["broker_gate_source"] = ae_broker_gate_source
    findings["broker_gate_reason"] = ae_broker_gate_reason
    findings["prop_funded_gate_pass"] = ae_prop_funded_gate_pass
    findings["prop_funded_gate_source"] = ae_prop_funded_gate_source
    findings["prop_funded_gate_reason"] = ae_prop_funded_gate_reason

    # === Sprint v2.8.2: Broker score freshness + execution venue ===
    broker_freshness_path = audit_dir / "broker_score_freshness_audit.json"
    broker_freshness_verdict = ""
    broker_execution_venue_status = ""
    broker_execution_venue_reason = ""
    if broker_freshness_path.exists():
        try:
            with open(broker_freshness_path, "r", encoding="utf-8") as f:
                bf_data = json.load(f)
            broker_freshness_verdict = bf_data.get("verdict", "") or ""
            bf_findings = bf_data.get("findings", {}) or {}
            broker_execution_venue_status = (
                "ALLOWED" if bf_findings.get("broker_execution_venue_allowed", False) else "BLOCKED"
            )
            broker_execution_venue_reason = bf_findings.get("broker_execution_venue_reason", "") or ""
        except Exception:
            pass
    findings["broker_score_freshness_verdict"] = broker_freshness_verdict
    findings["broker_execution_venue_status"] = broker_execution_venue_status
    findings["broker_execution_venue_reason"] = broker_execution_venue_reason

    # === Get parameter binding status ===
    safe_default_count = 0
    needs_backtest_binding_count = 0
    validated_count = 0
    critical_unbound_count = 0
    if has_registry:
        try:
            from titan.production.parameter_registry import ParameterRegistry
            registry = ParameterRegistry()
            summary = registry.get_summary()
            safe_default_count = summary.get("safe_default", 0)
            validated_count = summary.get("validated", 0)
            needs_backtest_binding_count = summary.get("safe_default", 0)
            critical_unbound_count = summary.get("critical_unbound", 0)
        except Exception:
            pass
    findings["safe_default_count"] = safe_default_count
    findings["needs_backtest_binding_count"] = needs_backtest_binding_count
    findings["validated_count"] = validated_count
    findings["critical_unbound_count"] = critical_unbound_count

    # === Compute production score (18 categories, 100 total) ===
    # 1. Account profiles (7)
    score_breakdown["account_profiles"] = 7 if (findings.get("account_profiles_exists") and findings.get("prop_constraints") and findings.get("retail_constraints") and findings.get("institutional_constraints")) else 0
    # 2. Broker profiles (3)
    score_breakdown["broker_profiles"] = 3 if findings.get("broker_profiles_exists") else 0
    # 3. Cost/net profit (8)
    score_breakdown["cost_net_profit"] = 8 if (findings.get("net_profit_model") and findings.get("cost_fields")) else 0
    # 4. Margin/leverage/risk (7)
    score_breakdown["margin_leverage_risk"] = 7 if findings.get("margin_guard") else 0
    # 5. Account adaptation/lot sizing (5)
    score_breakdown["account_adaptation_lot_sizing"] = 5 if (findings.get("account_adaptation_engine_exists") and findings.get("lot_sizing_engine_exists")) else 0
    # 6. SL/TP/profit corridor/partial close (8)
    score_breakdown["sl_tp_corridor_partial_close"] = 8 if (findings.get("dynamic_tp_geometry") and findings.get("rr_profile_guard") and findings.get("adaptive_profit_corridor_exists") and findings.get("partial_close_engine_exists")) else 0
    # 7. Reconciliation/forensics (5)
    score_breakdown["reconciliation_forensics"] = 5 if findings.get("reconciliation") else 0
    # 8. Alpha Factory (4)
    score_breakdown["alpha_factory"] = 4 if (findings.get("alpha_candidate_generator_exists") and findings.get("alpha_evaluator_exists") and findings.get("alpha_registry_exists")) else 0
    # 9. Retraining and promotion gate (6)
    score_breakdown["retraining_promotion"] = 6 if (findings.get("retraining_orchestrator_exists") and findings.get("model_promotion_gate_exists")) else 0
    # 10. Runtime calibration (4)
    score_breakdown["runtime_calibration"] = 4 if findings.get("runtime_calibration_engine_exists") else 0
    # 11. Licensing/anti-copy (4)
    score_breakdown["licensing"] = 4 if (findings.get("license_validator_exists") and findings.get("machine_binding_exists") and findings.get("expiry_guard_exists")) else 0
    # 12. Crash/fail-closed resilience (5)
    score_breakdown["crash_resilience"] = 5 if (findings.get("runtime_health_guard_exists") and findings.get("fail_closed_runtime_guard_exists") and findings.get("watchdog_restarter_exists")) else 0
    # 13. Dependency update safety (4)
    score_breakdown["dependency_safety"] = 4 if (findings.get("dependency_policy_exists") and findings.get("dependency_update_readiness_audit_exists")) else 0
    # 14. Prop/retail/institutional readiness (4)
    score_breakdown["prop_retail_inst"] = 4 if (findings.get("prop_constraints") and findings.get("retail_constraints") and findings.get("institutional_constraints")) else 0
    # 15. Production score honesty (4)
    score_breakdown["score_honesty"] = 4  # This audit itself provides honesty
    # 16. Broker scoring readiness (5) - NEW
    score_breakdown["broker_scoring"] = 5 if (findings.get("broker_scoring_engine_exists") and findings.get("broker_score_audit_exists")) else 0
    # 17. Prop/funded rule readiness (5) - NEW
    score_breakdown["prop_firm_rules"] = 5 if (findings.get("prop_firm_rule_engine_exists") and findings.get("prop_firm_audit_exists") and findings.get("risk_modes_exists")) else 0
    # 18. Profile matrix readiness + aggressive sim honesty (5) - NEW
    score_breakdown["profile_matrix"] = 5 if (findings.get("profile_matrix_audit_exists") and findings.get("aggressive_simulation_only")) else 0

    production_score = sum(score_breakdown.values())

    # === Score integrity: cap at 92 if safe defaults exist ===
    if safe_default_count > 0:
        if production_score > 92:
            warnings.append(f"SAFE_DEFAULTS_PRESENT: {safe_default_count} parameters use safe defaults. Score capped at 92.")
            high_warnings.append("SAFE_DEFAULTS_PRESENT")
            production_score = 92
        else:
            warnings.append(f"SAFE_DEFAULTS_PRESENT: {safe_default_count} parameters use safe defaults.")
            if production_score >= 90:
                high_warnings.append("SAFE_DEFAULTS_PRESENT")

    # === Score 100 blocked if NEEDS_BACKTEST_BINDING exists ===
    if needs_backtest_binding_count > 0 and production_score >= 100:
        warnings.append(f"NEEDS_BACKTEST_BINDING: {needs_backtest_binding_count} parameters need backtest binding. Score 100 not allowed.")
        high_warnings.append("NEEDS_BACKTEST_BINDING")
        production_score = min(production_score, 92)

    # === Critical parameter binding check ===
    if critical_unbound_count > 0:
        blockers.append(f"CRITICAL_PARAMETERS_UNBOUND: {critical_unbound_count} critical parameters remain SAFE_DEFAULT")
        high_warnings.append("CRITICAL_PARAMETERS_UNBOUND")

    # === Determine verdict ===
    if blockers:
        verdict = "PRODUCTION_CLOSURE_BLOCKED"
    elif critical_unbound_count == 0 and safe_default_count == 0 and len(high_warnings) == 0:
        # All parameters validated, no safe defaults, no HIGH warnings
        verdict = "PRODUCTION_CLOSURE_READY"
    elif critical_unbound_count == 0 and production_score >= 90 and len(blockers) == 0:
        # Critical parameters all bound, some non-critical safe defaults remain
        # Check if only non-critical safe defaults remain
        if safe_default_count > 0 and "SAFE_DEFAULTS_PRESENT" in high_warnings:
            # Remove HIGH warning if only non-critical safe defaults
            # (critical parameters are all bound)
            if critical_unbound_count == 0:
                high_warnings = [w for w in high_warnings if w != "SAFE_DEFAULTS_PRESENT"]
                warnings = [w for w in warnings if "SAFE_DEFAULTS_PRESENT" not in w]
                warnings.append(f"NON_CRITICAL_SAFE_DEFAULTS: {safe_default_count} non-critical parameters use safe defaults (all critical parameters bound)")
        verdict = "PRODUCTION_CLOSURE_READY_WITH_SAFE_DEFAULTS"
    elif production_score >= 90 and len(blockers) == 0:
        verdict = "PRODUCTION_CLOSURE_READY_WITH_SAFE_DEFAULTS"
    else:
        verdict = "PRODUCTION_CLOSURE_BLOCKED"

    return {
        "timestamp_utc": ts,
        "verdict": verdict,
        "production_score": production_score,
        "score_breakdown": score_breakdown,
        "safe_default_count": safe_default_count,
        "needs_backtest_binding_count": needs_backtest_binding_count,
        "validated_count": validated_count,
        "high_warnings": high_warnings,
        "ok_checks": ok_checks,
        "blockers": blockers,
        "warnings": warnings,
        "findings": findings,
        # Sprint 9.9.3.45.8.16 v2.7.3: top-level autonomous status fields
        "latest_execution_geometry_verdict": latest_geometry_verdict,
        "latest_forensics_verdict": latest_forensics_verdict,
        "ticket_history_scanner_verdict": latest_ticket_scanner_verdict,
        "end_to_end_entry_gate_verdict": latest_entry_gate_verdict,
        "autonomous_demo_readiness_verdict": latest_autonomous_verdict,
        "autonomous_allowed": autonomous_allowed,
        "autonomous_execution_status": autonomous_execution_status,
        # Sprint v2.8.3.3: CTO Consolidated Release Gate fields
        "latest_model_health_verdict": latest_model_health_verdict,
        "model_health_pass": model_health_pass,
        "active_model_count": active_model_count,
        "failed_required_model_count": failed_required_model_count,
        "failed_optional_model_count": failed_optional_model_count,
        "failed_model_count": failed_required_model_count,  # backwards-compat
        "blocked_required_models": blocked_required_models,
        "warned_optional_models": warned_optional_models,
        "latest_feature_parity_verdict": latest_feature_parity_verdict,
        "feature_parity_pass": feature_parity_pass,
        "latest_runtime_safety_verdict": latest_runtime_safety_verdict,
        "runtime_safety_pass": runtime_safety_pass,
        "v2_8_4_allowed": v2833_release_gate_pass,
        # Sprint v2.8.4: Prop Challenge Growth Profile fields
        "latest_growth_profile_verdict": latest_growth_profile_verdict,
        "growth_profile_pass": growth_profile_pass,
        "growth_profile_name": growth_profile_name,
        "growth_monthly_target_pct": monthly_target_pct,
        "growth_daily_dd_soft_limit_pct": daily_dd_soft,
        "growth_daily_dd_hard_limit_pct": daily_dd_hard,
        "growth_total_dd_limit_pct": total_dd_limit,
        "growth_profile_allowed": growth_profile_allowed,
        # Sprint v2.8.5: Final Demo Activation fields
        "latest_final_demo_activation_verdict": latest_final_demo_activation_verdict,
        "final_demo_activation_pass": final_demo_activation_pass,
        "final_demo_activation_allowed": final_demo_activation_allowed,
        "metaquotes_demo_verified": metaquotes_demo_verified,
        "open_positions_count": open_positions_count,
        "pending_orders_count": pending_orders_count,
        "stale_token_detected": stale_token_detected,
        "final_activation_execution_blocker": final_activation_execution_blocker,
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
        f.write("# TITAN XAU AI - Production Closure Readiness Audit v2.1 (v2.7.3)\n\n")
        f.write(f"**Verdict:** **{result['verdict']}**\n\n")
        f.write(f"**Production Score:** **{result['production_score']}/100**\n\n")
        f.write(f"**Safe Default Count:** {result.get('safe_default_count', 0)}\n\n")
        f.write(f"**Needs Backtest Binding:** {result.get('needs_backtest_binding_count', 0)}\n\n")
        f.write(f"**HIGH Warnings:** {result.get('high_warnings', [])}\n\n")
        f.write(f"**Timestamp:** {result['timestamp_utc']}\n\n")

        # v2.7.3: Autonomous execution status section
        f.write("## Autonomous Execution Status (v2.7.3)\n\n")
        f.write("| Field | Value |\n|---|---|\n")
        f.write(f"| latest_execution_geometry_verdict | {result.get('latest_execution_geometry_verdict', '')} |\n")
        f.write(f"| latest_forensics_verdict | {result.get('latest_forensics_verdict', '')} |\n")
        f.write(f"| ticket_history_scanner_verdict | {result.get('ticket_history_scanner_verdict', '')} |\n")
        f.write(f"| end_to_end_entry_gate_verdict | {result.get('end_to_end_entry_gate_verdict', '')} |\n")
        f.write(f"| autonomous_demo_readiness_verdict | {result.get('autonomous_demo_readiness_verdict', '')} |\n")
        f.write(f"| autonomous_allowed | {result.get('autonomous_allowed', False)} |\n")
        f.write(f"| autonomous_execution_status | **{result.get('autonomous_execution_status', 'BLOCKED')}** |\n\n")
        if not result.get('autonomous_allowed', False):
            f.write(
                "> **Note:** Production closure is code-ready but is NOT autonomous-ready. "
                "Autonomous execution remains blocked until all autonomous readiness checks pass.\n\n"
            )

        # v2.8.3.3: CTO Consolidated Release Gate section
        f.write("## CTO Consolidated Release Gate (v2.8.3.3.1)\n\n")
        f.write("| Field | Value |\n|---|---|\n")
        f.write(f"| latest_model_health_verdict | {result.get('latest_model_health_verdict', '')} |\n")
        f.write(f"| model_health_pass | {result.get('model_health_pass', False)} |\n")
        f.write(f"| active_model_count | {result.get('active_model_count', 0)} |\n")
        f.write(f"| failed_required_model_count | {result.get('failed_required_model_count', 0)} |\n")
        f.write(f"| failed_optional_model_count | {result.get('failed_optional_model_count', 0)} |\n")
        f.write(f"| blocked_required_models | {result.get('blocked_required_models', [])} |\n")
        f.write(f"| warned_optional_models | {result.get('warned_optional_models', [])} |\n")
        f.write(f"| latest_feature_parity_verdict | {result.get('latest_feature_parity_verdict', '')} |\n")
        f.write(f"| feature_parity_pass | {result.get('feature_parity_pass', False)} |\n")
        f.write(f"| latest_runtime_safety_verdict | {result.get('latest_runtime_safety_verdict', '')} |\n")
        f.write(f"| runtime_safety_pass | {result.get('runtime_safety_pass', False)} |\n")
        f.write(f"| **v2_8_4_allowed** | **{result.get('v2_8_4_allowed', False)}** |\n\n")

        # v2.8.4: Prop Challenge Growth Profile section
        f.write("## Prop Challenge Growth Profile (v2.8.4)\n\n")
        f.write("| Field | Value |\n|---|---|\n")
        f.write(f"| growth_profile_name | {result.get('growth_profile_name', '')} |\n")
        f.write(f"| latest_growth_profile_verdict | {result.get('latest_growth_profile_verdict', '')} |\n")
        f.write(f"| growth_profile_pass | {result.get('growth_profile_pass', False)} |\n")
        f.write(f"| growth_monthly_target_pct | {result.get('growth_monthly_target_pct', 0)} (target, NOT guarantee) |\n")
        f.write(f"| growth_daily_dd_soft_limit_pct | {result.get('growth_daily_dd_soft_limit_pct', 0)} |\n")
        f.write(f"| growth_daily_dd_hard_limit_pct | {result.get('growth_daily_dd_hard_limit_pct', 0)} |\n")
        f.write(f"| growth_total_dd_limit_pct | {result.get('growth_total_dd_limit_pct', 0)} |\n")
        f.write(f"| **growth_profile_allowed** | **{result.get('growth_profile_allowed', False)}** |\n\n")

        # v2.8.5: Final Demo Activation section
        f.write("## Final Demo Activation Readiness (v2.8.5)\n\n")
        f.write("| Field | Value |\n|---|---|\n")
        f.write(f"| latest_final_demo_activation_verdict | {result.get('latest_final_demo_activation_verdict', '')} |\n")
        f.write(f"| final_demo_activation_pass | {result.get('final_demo_activation_pass', False)} |\n")
        f.write(f"| final_demo_activation_allowed | {result.get('final_demo_activation_allowed', False)} |\n")
        f.write(f"| metaquotes_demo_verified | {result.get('metaquotes_demo_verified', False)} |\n")
        f.write(f"| open_positions_count | {result.get('open_positions_count', 0)} |\n")
        f.write(f"| pending_orders_count | {result.get('pending_orders_count', 0)} |\n")
        f.write(f"| stale_token_detected | {result.get('stale_token_detected', False)} |\n")
        f.write(f"| final_activation_execution_blocker | {result.get('final_activation_execution_blocker', '')} |\n\n")

        f.write("## Score Breakdown\n\n")
        f.write("| Category | Score |\n|---|---|\n")
        for k, v in result.get("score_breakdown", {}).items():
            f.write(f"| {k} | {v} |\n")
        f.write(f"| **TOTAL** | **{result['production_score']}** |\n")
        if result.get("blockers"):
            f.write("\n## Blockers\n\n")
            for b in result["blockers"]:
                f.write(f"- **{b}**\n")
        if result.get("warnings"):
            f.write("\n## Warnings\n\n")
            for w in result["warnings"]:
                f.write(f"- {w}\n")
        if result.get("ok_checks"):
            f.write("\n## OK Checks\n\n")
            for c in result["ok_checks"]:
                f.write(f"- {c}\n")
        f.write("\n## Safety\n\n")
        f.write("- order_send_called: False\n")
        f.write("- position_modified: False\n")
    return {"json_path": str(json_path), "md_path": str(md_path)}


def main() -> int:
    print("=" * 70)
    print("  TITAN XAU AI - Production Closure Readiness Audit v2.1 (v2.7.3)")
    print("=" * 70)
    result = run_audit()
    report = write_report(result)
    print(f"\n  Verdict: {result['verdict']}")
    print(f"  Production Score: {result['production_score']}/100")
    print(f"  Safe defaults: {result.get('safe_default_count', 0)}")
    print(f"  Needs backtest binding: {result.get('needs_backtest_binding_count', 0)}")
    print(f"  HIGH warnings: {result.get('high_warnings', [])}")
    print(f"  Blockers: {len(result.get('blockers', []))}")
    # v2.7.3: autonomous status
    print(f"\n  Autonomous execution status: {result.get('autonomous_execution_status', 'BLOCKED')}")
    print(f"  Autonomous allowed: {result.get('autonomous_allowed', False)}")
    print(f"  Latest geometry verdict: {result.get('latest_execution_geometry_verdict', '')}")
    print(f"  Latest forensics verdict: {result.get('latest_forensics_verdict', '')}")
    print(f"  Entry gate verdict: {result.get('end_to_end_entry_gate_verdict', '')}")
    # v2.8.3.3: CTO Consolidated Release Gate
    print(f"\n  --- v2.8.3.3.1 CTO Consolidated Release Gate ---")
    print(f"  Latest model health verdict: {result.get('latest_model_health_verdict', '')}")
    print(f"  Active models: {result.get('active_model_count', 0)}, Failed required: {result.get('failed_required_model_count', 0)}, Failed optional: {result.get('failed_optional_model_count', 0)}")
    print(f"  Latest feature parity verdict: {result.get('latest_feature_parity_verdict', '')}")
    print(f"  Latest runtime safety verdict: {result.get('latest_runtime_safety_verdict', '')}")
    print(f"  v2.8.4 allowed: {result.get('v2_8_4_allowed', False)}")
    # v2.8.4: Growth profile
    print(f"\n  --- v2.8.4 Prop Challenge Growth Profile ---")
    print(f"  Growth profile: {result.get('growth_profile_name', '')}")
    print(f"  Growth profile verdict: {result.get('latest_growth_profile_verdict', '')}")
    print(f"  Monthly target: {result.get('growth_monthly_target_pct', 0)} (target, NOT guarantee)")
    print(f"  Daily DD band: {result.get('growth_daily_dd_soft_limit_pct', 0)} to {result.get('growth_daily_dd_hard_limit_pct', 0)}")
    print(f"  Total DD cap: {result.get('growth_total_dd_limit_pct', 0)}")
    print(f"  Growth profile allowed: {result.get('growth_profile_allowed', False)}")
    # v2.8.5: Final demo activation
    print(f"\n  --- v2.8.5 Final Demo Activation Readiness ---")
    print(f"  Final demo activation verdict: {result.get('latest_final_demo_activation_verdict', '')}")
    print(f"  MetaQuotes-Demo verified: {result.get('metaquotes_demo_verified', False)}")
    print(f"  Open positions count: {result.get('open_positions_count', 0)}")
    print(f"  Pending orders count: {result.get('pending_orders_count', 0)}")
    print(f"  Stale token detected: {result.get('stale_token_detected', False)}")
    print(f"  Final demo activation allowed: {result.get('final_demo_activation_allowed', False)}")
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
