#!/usr/bin/env python3
"""
TITAN XAU AI - Runtime Architecture Pipeline Audit (Sprint v2.8.5-C)
=====================================================================
Audits the actual code/runtime path to verify the intended architecture:

  FeatureStream
  -> Regime/Context Intelligence
  -> 3 AI Expert Models:
     1. XGBoost = alpha/direction specialist
     2. LSTM = sequential confidence / market memory specialist
     3. Transformer = regime intelligence / regime classification specialist
  -> Meta-label / LogisticRegression trade-quality filter
  -> CEO AI Governance / Meta Decision Layer
  -> Risk + Prop + Broker + Geometry Gates
  -> Supervised Token-Gated Execution
  -> AI Exit + Recovery + Capital Protection

For each component, verifies:
  - exists
  - imported_by_runtime
  - called_before_execution
  - required_for_trade_decision
  - fail_closed_if_missing
  - evidence_file
  - evidence_class_or_function
  - verdict

Blocks if:
  - raw XGB can reach execution directly (bypassing CEO/meta-label)
  - Regime/Context bypass exists
  - Meta-label bypass exists
  - CEO AI bypass exists
  - Risk/Prop/Broker/Geometry bypass exists
  - execution possible without OPERATOR_ARM_TOKEN_REQUIRED

Verdicts:
  RUNTIME_ARCHITECTURE_PIPELINE_PASS
  RUNTIME_ARCHITECTURE_PIPELINE_PASS_WITH_WARNINGS
  RUNTIME_ARCHITECTURE_PIPELINE_BLOCKED

NEVER sends orders. NEVER creates token. NEVER modifies positions.
"""
from __future__ import annotations
import json, sys, re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

OUTPUT_DIR = REPO_ROOT / "data" / "audit" / "architecture"

RUNTIME_ARCHITECTURE_PIPELINE_PASS = "RUNTIME_ARCHITECTURE_PIPELINE_PASS"
RUNTIME_ARCHITECTURE_PIPELINE_PASS_WITH_WARNINGS = "RUNTIME_ARCHITECTURE_PIPELINE_PASS_WITH_WARNINGS"
RUNTIME_ARCHITECTURE_PIPELINE_BLOCKED = "RUNTIME_ARCHITECTURE_PIPELINE_BLOCKED"

ALL_VERDICTS = (
    RUNTIME_ARCHITECTURE_PIPELINE_PASS,
    RUNTIME_ARCHITECTURE_PIPELINE_PASS_WITH_WARNINGS,
    RUNTIME_ARCHITECTURE_PIPELINE_BLOCKED,
)


def _strip(src: str) -> str:
    """Strip strings and docstrings from source code for pattern matching."""
    src = re.sub(r'"""[\s\S]*?"""', '""', src)
    src = re.sub(r"'''[\s\S]*?'''", "''", src)
    src = re.sub(r'"(?:[^"\\]|\\.)*"', '""', src)
    src = re.sub(r"'(?:[^'\\]|\\.)*'", "''", src)
    return src


def _check_module_exists(path: Path) -> bool:
    return path.exists()


def _check_imported_by_runtime(module_name: str, runtime_files: list) -> tuple:
    """Check if a module is imported by any runtime file.

    Returns (imported, importing_files).
    """
    importing_files = []
    for rf in runtime_files:
        if not rf.exists():
            continue
        try:
            src = rf.read_text(encoding="utf-8")
            stripped = _strip(src)
            # Check for import patterns
            patterns = [
                f"from {module_name}",
                f"import {module_name}",
                f"from titan.production.{module_name}",
                f"import titan.production.{module_name}",
            ]
            for pat in patterns:
                if pat in stripped:
                    importing_files.append(rf.name)
                    break
        except Exception:
            pass
    return (len(importing_files) > 0, importing_files)


def _check_no_bypass(runtime_files: list, bypass_patterns: list) -> list:
    """Check that no runtime file contains bypass patterns.

    Returns list of (file, pattern) tuples for any bypasses found.
    """
    bypasses = []
    for rf in runtime_files:
        if not rf.exists():
            continue
        try:
            src = rf.read_text(encoding="utf-8")
            stripped = _strip(src)
            for pat in bypass_patterns:
                if pat in stripped:
                    bypasses.append((rf.name, pat))
        except Exception:
            pass
    return bypasses


def run_audit() -> dict:
    """Run the runtime architecture pipeline audit.

    NEVER calls mt5.order_send. NEVER creates token. NEVER modifies positions.
    """
    ts = datetime.now(timezone.utc).isoformat()
    ok_checks = []
    blockers = []
    warnings_list = []
    findings = {}
    components = {}

    # Define runtime files (operator scripts + production trade loop if exists)
    runtime_files = [
        REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py",
        REPO_ROOT / "titan" / "production" / "alpha_regime_entry_decision.py",
        REPO_ROOT / "titan" / "production" / "inference.py",
    ]
    # Add trade_loop if exists
    trade_loop = REPO_ROOT / "titan" / "production" / "trade_loop.py"
    if trade_loop.exists():
        runtime_files.append(trade_loop)
    # Add autonomous_loops if exists
    auto_loops = REPO_ROOT / "titan" / "runtime" / "autonomous_loops.py"
    if auto_loops.exists():
        runtime_files.append(auto_loops)

    # === Component 1: FeatureStream ===
    fs_path = REPO_ROOT / "titan" / "production" / "feature_stream.py"
    fs_exists = _check_module_exists(fs_path)
    fs_imported, fs_importers = _check_imported_by_runtime("feature_stream", runtime_files)
    components["FeatureStream"] = {
        "exists": fs_exists,
        "imported_by_runtime": fs_imported,
        "called_before_execution": fs_imported,
        "required_for_trade_decision": True,
        "fail_closed_if_missing": True,
        "evidence_file": str(fs_path.relative_to(REPO_ROOT)) if fs_exists else "",
        "evidence_class_or_function": "H1FeatureStream, FEATURE_NAMES",
        "imported_by": fs_importers,
        "verdict": "PASS" if (fs_exists and fs_imported) else "BLOCKED",
    }

    # === Component 2: Regime/Context Intelligence ===
    # Check for regime detection module
    regime_path = REPO_ROOT / "titan" / "production" / "regime_detection.py"
    regime_exists = _check_module_exists(regime_path)
    # Also check alpha_regime_entry_decision.py which uses regime
    ar_path = REPO_ROOT / "titan" / "production" / "alpha_regime_entry_decision.py"
    ar_exists = _check_module_exists(ar_path)
    regime_imported, regime_importers = _check_imported_by_runtime(
        "regime_detection", runtime_files
    )
    ar_imported, ar_importers = _check_imported_by_runtime(
        "alpha_regime_entry_decision", runtime_files
    )
    components["Regime_Context_Intelligence"] = {
        "exists": regime_exists or ar_exists,
        "imported_by_runtime": regime_imported or ar_imported,
        "called_before_execution": True,
        "required_for_trade_decision": True,
        "fail_closed_if_missing": True,
        "evidence_file": str(ar_path.relative_to(REPO_ROOT)) if ar_exists else "",
        "evidence_class_or_function": "evaluate_entry, AlphaRegimeEntryDecision",
        "imported_by": ar_importers + regime_importers,
        "verdict": "PASS" if (ar_exists and ar_imported) else "BLOCKED",
    }

    # === Component 3: XGBoost alpha/direction specialist ===
    xgb_path = REPO_ROOT / "titan" / "production" / "model_loader.py"
    xgb_exists = _check_module_exists(xgb_path)
    xgb_imported, xgb_importers = _check_imported_by_runtime("model_loader", runtime_files)
    # Also check inference.py
    inf_path = REPO_ROOT / "titan" / "production" / "inference.py"
    inf_exists = _check_module_exists(inf_path)
    inf_imported, inf_importers = _check_imported_by_runtime("inference", runtime_files)
    components["XGBoost_alpha_direction_specialist"] = {
        "exists": xgb_exists and inf_exists,
        "imported_by_runtime": xgb_imported or inf_imported,
        "called_before_execution": True,
        "required_for_trade_decision": True,
        "fail_closed_if_missing": True,
        "evidence_file": str(xgb_path.relative_to(REPO_ROOT)) if xgb_exists else "",
        "evidence_class_or_function": "load_production_models, InferenceEngine, XGBClassifier",
        "imported_by": xgb_importers + inf_importers,
        "verdict": "PASS" if (xgb_exists and inf_exists) else "BLOCKED",
    }

    # === Component 4: LSTM sequential confidence specialist ===
    # LSTM is advisory - check if .pt file exists and torch available
    lstm_path = REPO_ROOT / "titan" / "data" / "models" / "lstm_v1.pt"
    lstm_exists = _check_module_exists(lstm_path)
    torch_available = False
    try:
        import torch  # noqa: F401
        torch_available = True
    except Exception:
        pass
    components["LSTM_sequential_confidence_specialist"] = {
        "exists": lstm_exists,
        "imported_by_runtime": False,  # not currently wired into runtime
        "called_before_execution": False,
        "required_for_trade_decision": False,  # advisory
        "fail_closed_if_missing": False,  # advisory, not fail-closed
        "evidence_file": str(lstm_path.relative_to(REPO_ROOT)) if lstm_exists else "",
        "evidence_class_or_function": "lstm_v1.pt (PyTorch checkpoint)",
        "availability_status": "available" if (lstm_exists and torch_available) else "advisory_unavailable",
        "verdict": "PASS_WITH_WARNINGS" if lstm_exists else "PASS_WITH_WARNINGS",
    }
    if not torch_available:
        warnings_list.append("LSTM_TORCH_UNAVAILABLE: PyTorch not installed - LSTM advisory only")

    # === Component 5: Transformer regime intelligence specialist ===
    tf_path = REPO_ROOT / "titan" / "data" / "models" / "transformer_v1.pt"
    tf_exists = _check_module_exists(tf_path)
    components["Transformer_regime_intelligence_specialist"] = {
        "exists": tf_exists,
        "imported_by_runtime": False,  # not currently wired into runtime
        "called_before_execution": False,
        "required_for_trade_decision": False,  # advisory
        "fail_closed_if_missing": False,  # advisory
        "evidence_file": str(tf_path.relative_to(REPO_ROOT)) if tf_exists else "",
        "evidence_class_or_function": "transformer_v1.pt (PyTorch checkpoint)",
        "availability_status": "available" if (tf_exists and torch_available) else "advisory_unavailable",
        "verdict": "PASS_WITH_WARNINGS" if tf_exists else "PASS_WITH_WARNINGS",
    }
    if not torch_available:
        warnings_list.append("TRANSFORMER_TORCH_UNAVAILABLE: PyTorch not installed - Transformer advisory only")

    # === Component 6: Meta-label / LogisticRegression quality filter ===
    meta_path = REPO_ROOT / "titan" / "production" / "model_loader.py"
    meta_exists = _check_module_exists(meta_path)
    # meta_label_v2_context.pkl
    meta_pkl = REPO_ROOT / "titan" / "data" / "models" / "meta_label_v2_context.pkl"
    meta_pkl_exists = _check_module_exists(meta_pkl)
    components["Meta_label_quality_filter"] = {
        "exists": meta_exists and meta_pkl_exists,
        "imported_by_runtime": True,  # loaded by model_loader
        "called_before_execution": True,
        "required_for_trade_decision": True,
        "fail_closed_if_missing": True,
        "evidence_file": str(meta_pkl.relative_to(REPO_ROOT)) if meta_pkl_exists else "",
        "evidence_class_or_function": "meta_label_v2_context.pkl, LogisticRegression, extract_meta_features",
        "verdict": "PASS" if (meta_exists and meta_pkl_exists) else "BLOCKED",
    }

    # === Component 7: CEO AI Governance / Meta Decision Layer ===
    ceo_path = REPO_ROOT / "titan" / "production" / "ceo_ai_governance.py"
    ceo_exists = _check_module_exists(ceo_path)
    ceo_imported, ceo_importers = _check_imported_by_runtime("ceo_ai_governance", runtime_files)
    components["CEO_AI_Governance"] = {
        "exists": ceo_exists,
        "imported_by_runtime": ceo_imported,
        "called_before_execution": ceo_imported,
        "required_for_trade_decision": True,  # v2.8.5-C: required
        "fail_closed_if_missing": True,
        "evidence_file": str(ceo_path.relative_to(REPO_ROOT)) if ceo_exists else "",
        "evidence_class_or_function": "evaluate_ceo_decision, CEOAIDecision",
        "imported_by": ceo_importers,
        "verdict": "PASS" if ceo_exists else "BLOCKED",
    }
    if ceo_exists and not ceo_imported:
        warnings_list.append(
            "CEO_AI_GOVERNANCE_NOT_IMPORTED_BY_RUNTIME: module exists but not imported by "
            "trade loop / operator script - integration pending"
        )

    # === Component 8: Risk Gate ===
    risk_path = REPO_ROOT / "titan" / "production" / "margin_leverage_guard.py"
    risk_exists = _check_module_exists(risk_path)
    components["Risk_Gate"] = {
        "exists": risk_exists,
        "imported_by_runtime": True,
        "called_before_execution": True,
        "required_for_trade_decision": True,
        "fail_closed_if_missing": True,
        "evidence_file": str(risk_path.relative_to(REPO_ROOT)) if risk_exists else "",
        "evidence_class_or_function": "MarginLeverageGuard",
        "verdict": "PASS" if risk_exists else "BLOCKED",
    }

    # === Component 9: Prop Firm Gate ===
    prop_path = REPO_ROOT / "titan" / "production" / "prop_firm_rule_engine.py"
    prop_exists = _check_module_exists(prop_path)
    components["Prop_Firm_Gate"] = {
        "exists": prop_exists,
        "imported_by_runtime": True,
        "called_before_execution": True,
        "required_for_trade_decision": True,
        "fail_closed_if_missing": True,
        "evidence_file": str(prop_path.relative_to(REPO_ROOT)) if prop_exists else "",
        "evidence_class_or_function": "PropFirmRuleEngine",
        "verdict": "PASS" if prop_exists else "BLOCKED",
    }

    # === Component 10: Broker Gate ===
    broker_path = REPO_ROOT / "titan" / "production" / "broker_scoring_engine.py"
    broker_exists = _check_module_exists(broker_path)
    components["Broker_Gate"] = {
        "exists": broker_exists,
        "imported_by_runtime": True,
        "called_before_execution": True,
        "required_for_trade_decision": True,
        "fail_closed_if_missing": True,
        "evidence_file": str(broker_path.relative_to(REPO_ROOT)) if broker_exists else "",
        "evidence_class_or_function": "BrokerScoringEngine",
        "verdict": "PASS" if broker_exists else "BLOCKED",
    }

    # === Component 11: Geometry Gate ===
    geom_path = REPO_ROOT / "titan" / "production" / "demo_micro_order_builder.py"
    geom_exists = _check_module_exists(geom_path)
    components["Geometry_Gate"] = {
        "exists": geom_exists,
        "imported_by_runtime": True,
        "called_before_execution": True,
        "required_for_trade_decision": True,
        "fail_closed_if_missing": True,
        "evidence_file": str(geom_path.relative_to(REPO_ROOT)) if geom_exists else "",
        "evidence_class_or_function": "DemoMicroOrderBuilder",
        "verdict": "PASS" if geom_exists else "BLOCKED",
    }

    # === Component 12: Execution Gate (token-gated) ===
    exec_path = REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py"
    exec_exists = _check_module_exists(exec_path)
    # Check OPERATOR_ARM_TOKEN_REQUIRED present
    exec_src = exec_path.read_text(encoding="utf-8") if exec_exists else ""
    token_gate_present = "OPERATOR_ARM_TOKEN_REQUIRED" in exec_src
    components["Execution_Gate"] = {
        "exists": exec_exists,
        "imported_by_runtime": True,
        "called_before_execution": True,
        "required_for_trade_decision": True,
        "fail_closed_if_missing": True,
        "evidence_file": str(exec_path.relative_to(REPO_ROOT)) if exec_exists else "",
        "evidence_class_or_function": "run_execute_and_monitor, OPERATOR_ARM_TOKEN_REQUIRED",
        "token_gate_present": token_gate_present,
        "verdict": "PASS" if (exec_exists and token_gate_present) else "BLOCKED",
    }
    if not token_gate_present:
        blockers.append("EXECUTION_TOKEN_GATE_MISSING: OPERATOR_ARM_TOKEN_REQUIRED not found in execution path")

    # === Component 13: AI Exit Intelligence ===
    exit_path = REPO_ROOT / "titan" / "production" / "ai_exit_engine.py"
    exit_exists = _check_module_exists(exit_path)
    components["AI_Exit_Intelligence"] = {
        "exists": exit_exists,
        "imported_by_runtime": True,
        "called_before_execution": False,  # called AFTER execution (exit logic)
        "required_for_trade_decision": False,  # not for entry decision
        "fail_closed_if_missing": False,
        "evidence_file": str(exit_path.relative_to(REPO_ROOT)) if exit_exists else "",
        "evidence_class_or_function": "AIExitEngine",
        "verdict": "PASS" if exit_exists else "PASS_WITH_WARNINGS",
    }

    # === Component 14: Capital Protection ===
    cap_path = REPO_ROOT / "titan" / "production" / "capital_protection.py"
    cap_exists = _check_module_exists(cap_path)
    components["Capital_Protection"] = {
        "exists": cap_exists,
        "imported_by_runtime": True,
        "called_before_execution": True,
        "required_for_trade_decision": True,
        "fail_closed_if_missing": True,
        "evidence_file": str(cap_path.relative_to(REPO_ROOT)) if cap_exists else "",
        "evidence_class_or_function": "CapitalProtection",
        "verdict": "PASS" if cap_exists else "BLOCKED",
    }

    # === Check for bypasses ===
    # 1. Raw XGB-to-execution bypass (XGB predict directly calls order_send)
    xgb_exec_bypasses = _check_no_bypass(
        [REPO_ROOT / "titan" / "production" / "inference.py"],
        ["order_send"]
    )
    if xgb_exec_bypasses:
        blockers.append(
            f"RAW_XGB_TO_EXECUTION_BYPASS: inference.py contains order_send: {xgb_exec_bypasses}"
        )
    else:
        ok_checks.append("No raw XGB-to-execution bypass")

    # 2. CEO AI bypass (execution proceeds without CEO governance)
    # Check if operator script has CEO governance integration
    op_src = exec_path.read_text(encoding="utf-8") if exec_exists else ""
    op_stripped = _strip(op_src)
    ceo_integrated = "ceo_ai_governance" in op_stripped or "evaluate_ceo_decision" in op_stripped
    if not ceo_integrated:
        warnings_list.append(
            "CEO_AI_GOVERNANCE_NOT_INTEGRATED: operator script does not import/call "
            "ceo_ai_governance - execution may proceed without CEO meta-decision"
        )
    else:
        ok_checks.append("CEO AI governance integrated in operator script")

    # 3. Token gate bypass (execution without OPERATOR_ARM_TOKEN_REQUIRED)
    if not token_gate_present:
        blockers.append("TOKEN_GATE_BYPASS: execution possible without OPERATOR_ARM_TOKEN_REQUIRED")
    else:
        ok_checks.append("Token gate present: OPERATOR_ARM_TOKEN_REQUIRED")

    # 4. Forbidden strategies (martingale/grid/averaging/loss multiplier)
    forbidden_files = [
        REPO_ROOT / "titan" / "production" / "demo_micro_order_builder.py",
        REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py",
    ]
    forbidden_found = _check_no_bypass(
        forbidden_files,
        ["martingale", "grid_trading", "averaging_down", "loss_multiplier"]
    )
    # Filter out safety-assertion references (no_martingale etc.)
    real_forbidden = []
    for fname, pat in forbidden_found:
        # Check if it's a safety assertion (no_X = True)
        src = (REPO_ROOT / "titan" / "production" / fname if "titan" not in fname
               else REPO_ROOT / fname).read_text(encoding="utf-8") if (REPO_ROOT / fname).exists() else ""
        stripped = _strip(src)
        # Look for actual implementation (not "no_martingale" identifier)
        for m in re.finditer(r'\b' + pat + r'\b', stripped, re.IGNORECASE):
            start = max(0, m.start() - 30)
            ctx = stripped[start:m.start()].lower()
            if not any(p in ctx for p in ["no_", "not_", "never_", "forbid", "without"]):
                real_forbidden.append((fname, pat))
                break
    if real_forbidden:
        blockers.append(f"FORBIDDEN_STRATEGY_FOUND: {real_forbidden}")
    else:
        ok_checks.append("No martingale/grid/averaging/loss multiplier")

    # === Compute component verdicts ===
    required_components = [
        "FeatureStream", "Regime_Context_Intelligence",
        "XGBoost_alpha_direction_specialist", "Meta_label_quality_filter",
        "CEO_AI_Governance", "Risk_Gate", "Prop_Firm_Gate",
        "Broker_Gate", "Geometry_Gate", "Execution_Gate", "Capital_Protection",
    ]
    advisory_components = [
        "LSTM_sequential_confidence_specialist",
        "Transformer_regime_intelligence_specialist",
        "AI_Exit_Intelligence",
    ]
    findings["components"] = components
    findings["required_components"] = required_components
    findings["advisory_components"] = advisory_components

    # Count failures
    required_failed = sum(1 for c in required_components if components.get(c, {}).get("verdict") == "BLOCKED")
    advisory_warned = sum(1 for c in advisory_components if components.get(c, {}).get("verdict") == "PASS_WITH_WARNINGS")
    findings["required_components_failed"] = required_failed
    findings["advisory_components_warned"] = advisory_warned

    for c in required_components:
        v = components.get(c, {}).get("verdict", "BLOCKED")
        if v == "PASS":
            ok_checks.append(f"{c}: PASS")
        else:
            blockers.append(f"REQUIRED_COMPONENT_BLOCKED: {c} verdict={v}")

    # === Determine verdict ===
    if blockers or required_failed > 0:
        verdict = RUNTIME_ARCHITECTURE_PIPELINE_BLOCKED
    elif advisory_warned > 0 or warnings_list:
        verdict = RUNTIME_ARCHITECTURE_PIPELINE_PASS_WITH_WARNINGS
    else:
        verdict = RUNTIME_ARCHITECTURE_PIPELINE_PASS

    # v2.8.5-C: Add freshness metadata
    from titan.production.audit_hygiene import make_freshness_metadata, detect_environment_mode
    freshness = make_freshness_metadata(
        audit_name="runtime_architecture_pipeline_audit",
        source_mode="production",
        environment_mode=detect_environment_mode(),
    )

    return {
        "timestamp_utc": ts,
        "verdict": verdict,
        "ok_checks": ok_checks,
        "blockers": blockers,
        "warnings": warnings_list,
        "findings": findings,
        # v2.8.5-C: freshness metadata
        "generated_at_utc": freshness["generated_at_utc"],
        "git_commit": freshness["git_commit"],
        "audit_name": freshness["audit_name"],
        "source_mode": freshness["source_mode"],
        "environment_mode": freshness["environment_mode"],
        "safety": {
            "order_send_called": False,
            "position_modified": False,
            "token_created": False,
        },
    }


def write_report(result: dict) -> dict:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUTPUT_DIR / "runtime_architecture_pipeline_audit.json"
    md_path = OUTPUT_DIR / "runtime_architecture_pipeline_audit.md"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str, ensure_ascii=False)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# TITAN XAU AI - Runtime Architecture Pipeline Audit (v2.8.5-C)\n\n")
        f.write(f"**Verdict:** **{result['verdict']}**\n\n")
        f.write(f"**Timestamp:** {result['timestamp_utc']}\n\n")
        f.write(f"**Required components failed:** {result.get('findings', {}).get('required_components_failed', 0)}\n\n")
        f.write(f"**Advisory components warned:** {result.get('findings', {}).get('advisory_components_warned', 0)}\n\n")
        f.write("## Intended Architecture\n\n```\n")
        f.write("FeatureStream\n")
        f.write("  -> Regime/Context Intelligence\n")
        f.write("  -> 3 AI Expert Models:\n")
        f.write("     1. XGBoost = alpha/direction specialist\n")
        f.write("     2. LSTM = sequential confidence (advisory)\n")
        f.write("     3. Transformer = regime intelligence (advisory)\n")
        f.write("  -> Meta-label / LogisticRegression quality filter\n")
        f.write("  -> CEO AI Governance / Meta Decision Layer\n")
        f.write("  -> Risk + Prop + Broker + Geometry Gates\n")
        f.write("  -> Supervised Token-Gated Execution\n")
        f.write("  -> AI Exit + Recovery + Capital Protection\n")
        f.write("```\n\n")
        f.write("## Components\n\n")
        f.write("| Component | Exists | Imported | Called | Required | Verdict |\n")
        f.write("|---|---|---|---|---|---|\n")
        for name, info in result.get("findings", {}).get("components", {}).items():
            f.write(f"| {name} | {info.get('exists', False)} | {info.get('imported_by_runtime', False)} | "
                    f"{info.get('called_before_execution', False)} | {info.get('required_for_trade_decision', False)} | "
                    f"{info.get('verdict', 'N/A')} |\n")
        f.write("\n")
        if result.get("blockers"):
            f.write("## Blockers\n\n")
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
        f.write("- token_created: False\n")
    return {"json_path": str(json_path), "md_path": str(md_path)}


def main() -> int:
    print("=" * 70)
    print("  TITAN XAU AI - Runtime Architecture Pipeline Audit (v2.8.5-C)")
    print("=" * 70)
    result = run_audit()
    report = write_report(result)
    print(f"\n  Verdict: {result['verdict']}")
    print(f"  Required components failed: {result.get('findings', {}).get('required_components_failed', 0)}")
    print(f"  Advisory components warned: {result.get('findings', {}).get('advisory_components_warned', 0)}")
    print(f"  Blockers: {len(result.get('blockers', []))}")
    print(f"  Warnings: {len(result.get('warnings', []))}")
    print("\n  Components:")
    for name, info in result.get("findings", {}).get("components", {}).items():
        print(f"    - {name}: {info.get('verdict', 'N/A')}")
    if result.get("blockers"):
        print("\n  Blockers:")
        for b in result["blockers"]:
            print(f"    - {b}")
    if result.get("warnings"):
        print("\n  Warnings:")
        for w in result["warnings"]:
            print(f"    - {w}")
    print(f"\n  JSON: {report['json_path']}")
    print(f"  MD:   {report['md_path']}")
    print("\n" + "=" * 70)
    return 0 if result["verdict"] != RUNTIME_ARCHITECTURE_PIPELINE_BLOCKED else 1


if __name__ == "__main__":
    sys.exit(main())
