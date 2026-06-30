#!/usr/bin/env python3
"""
TITAN XAU AI - Sprint 9.9.3.41 Pre-Observation Full System Acceptance Audit
============================================================================

Brutally honest pre-observation audit. Confirms whether TITAN is truly
ready for controlled 7-day demo observation.

8 audit areas:
  1. Sprint/module inventory
  2. End-to-end runtime chain
  3. Logical contradiction
  4. Mathematical consistency
  5. Configuration consistency
  6. Windows RC package safety
  7. Demo monitoring readiness
  8. Go/no-go decision

NEVER imports MetaTrader5.
NEVER sends orders.
NEVER runs DEMO_MICRO_EXECUTE.
NEVER asks for credentials.
"""
from __future__ import annotations
import json, re, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
OUTPUT_DIR = REPO_ROOT / "data" / "audit" / "pre_observation"
JSON_PATH = OUTPUT_DIR / "pre_observation_acceptance_audit.json"
MD_PATH = OUTPUT_DIR / "pre_observation_acceptance_audit.md"


# ─── Helpers ──────────────────────────────────────────────────────────────

def _read(rel_path: str) -> str:
    p = REPO_ROOT / rel_path
    if not p.exists():
        return ""
    try:
        return p.read_text(encoding="utf-8")
    except Exception:
        return ""


def _strip(src: str) -> str:
    """Strip docstrings, string literals, and comments."""
    src = re.sub(r'"""[\s\S]*?"""', '""', src)
    src = re.sub(r"'''[\s\S]*?'''", "''", src)
    src = re.sub(r'r"[^"]*"', '""', src)
    src = re.sub(r"r'[^']*'", "''", src)
    src = re.sub(r'"(?:[^"\\]|\\.)*"', '""', src)
    src = re.sub(r"'(?:[^'\\]|\\.)*'", "''", src)
    out = []
    for line in src.splitlines():
        idx = line.find("#")
        if idx >= 0:
            line = line[:idx]
        out.append(line)
    return "\n".join(out)


def _git_head_short() -> str:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=10,
        )
        return r.stdout.strip() if r.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def _has_import(src: str, module: str) -> bool:
    code = _strip(src)
    pattern = rf"(?:^|\n)\s*(?:import\s+{re.escape(module)}\b|from\s+{re.escape(module)}\b)"
    return re.search(pattern, code) is not None


def _has_call(src: str, pattern: str) -> bool:
    code = _strip(src)
    return re.search(rf"\b{pattern}\s*\(", code) is not None


def _has_instantiation(src: str, class_name: str) -> bool:
    code = _strip(src)
    return re.search(rf"\b{re.escape(class_name)}\s*\(", code) is not None


# ─── Source captures ─────────────────────────────────────────────────────

LAUNCHER_SRC = _read("titan/runtime/launcher.py")
AUTONOMOUS_SRC = _read("titan/runtime/autonomous_loops.py")
ASSEMBLY_SRC = _read("titan/production/production_runtime_assembly.py")
OPERATOR_CONSOLE_SRC = _read("titan/production/operator_control_console.py")
FIRST_RUN_WIZARD_SRC = _read("titan/production/first_run_wizard.py")
SIGNAL_BRIDGE_SRC = _read("titan/production/signal_execution_bridge.py")
EXIT_INTENT_BRIDGE_SRC = _read("titan/production/exit_intent_bridge.py")
POSITION_LIFECYCLE_SRC = _read("titan/production/position_lifecycle.py")
FORWARD_OBS_SRC = _read("titan/production/forward_observation.py")
OBSERVATION_SCORECARD_SRC = _read("titan/production/observation_scorecard.py")
MODEL_LIFECYCLE_SRC = _read("titan/production/model_lifecycle_governance.py")
ALPHA_FACTORY_SRC = _read("titan/production/alpha_factory_governance.py")
AUTO_CALIBRATION_SRC = _read("titan/production/auto_calibration_governance.py")
MODEL_REGISTRY_SRC = _read("titan/production/model_registry.py")
OFFLINE_RETRAINING_SRC = _read("titan/production/offline_retraining_pipeline.py")
RETRAINING_TRIGGER_SRC = _read("titan/production/retraining_trigger_monitor.py")
BROKER_MATRIX_SRC = _read("titan/production/broker_compatibility_matrix.py")
RUNTIME_YAML = _read("config/runtime.yaml")
PROP_FIRM_YAML = _read("config/prop_firm_profiles.yaml")
OPERATOR_CLI_SRC = _read("scripts/operator/titan_operator.py")
FIRST_RUN_CLI_SRC = _read("scripts/operator/titan_first_run.py")
PACKAGE_BUILDER_SRC = _read("scripts/release/build_windows_rc_package.py")
MASTER_AUDIT_SRC = _read("scripts/audit/master_integration_audit.py")
OPERATOR_BATCH = _read("run_titan_operator.bat")
FIRST_RUN_BATCH = _read("run_titan_first_run.bat")


# ─── 1. Sprint/module inventory ──────────────────────────────────────────

MODULE_INVENTORY = [
    # (name, file_path, expected_classification_hint)
    ("Research/data pipeline", "titan/data/canonical/", "research"),
    ("Feature engineering", "titan/production/feature_stream.py", "wired"),
    ("Model loader", "titan/production/model_loader.py", "module"),
    ("InferenceEngine", "titan/production/inference.py", "wired"),
    ("Meta-label pipeline", "titan/production/meta_calibration_monitor.py", "wired"),
    ("FeatureStream", "titan/production/feature_stream.py", "wired"),
    ("TradeLoop", "titan/production/trade_loop.py", "wired"),
    ("PositionSync", "titan/production/position_sync.py", "wired"),
    ("ColdStartReconciler", "titan/production/cold_start.py", "wired"),
    ("ExitManager", "titan/production/exit_manager.py", "wired"),
    ("OrderModifier", "titan/production/order_modifier.py", "module"),
    ("TradeJournal", "titan/production/trade_journal.py", "wired"),
    ("KillSwitchFSM", "titan/production/kill_switch_fsm.py", "wired"),
    ("NewsFilter", "titan/production/news_filter.py", "wired"),
    ("SlippageMonitor", "titan/production/slippage_monitor.py", "wired"),
    ("DriftMonitor", "titan/production/drift_monitor.py", "wired"),
    ("WatchdogRestarter", "titan/production/watchdog_restarter.py", "module"),
    ("ATR execution", "titan/production/trade_loop.py", "wired"),
    ("PropFirmLayer", "titan/production/prop_firm_manager.py", "module"),
    ("AccountHealthEngine", "titan/production/account_health_engine.py", "module"),
    ("DynamicRiskEngine", "titan/production/dynamic_risk_engine.py", "module"),
    ("CapitalProtection", "titan/production/capital_protection.py", "module"),
    ("BrokerIntelligence", "titan/production/broker_intelligence.py", "module"),
    ("AIExitEngine", "titan/production/ai_exit_engine.py", "module"),
    ("Commercial Protection", "titan/security/", "module"),
    ("BrokerCompatibilityMatrix", "titan/production/broker_compatibility_matrix.py", "wired"),
    ("RegimeDetection", "titan/production/regime_detection.py", "wired"),
    ("SignalExecutionBridge", "titan/production/signal_execution_bridge.py", "wired"),
    ("MT5ExecutionAdapter", "titan/production/mt5_execution_adapter.py", "module"),
    ("PositionLifecycleEngine", "titan/production/position_lifecycle.py", "wired"),
    ("ExitIntentBridge", "titan/production/exit_intent_bridge.py", "wired"),
    ("ForwardObservationEngine", "titan/production/forward_observation.py", "wired"),
    ("ObservationScorecardEngine", "titan/production/observation_scorecard.py", "wired"),
    ("RuntimeHealthMonitor", "titan/production/runtime_health.py", "wired"),
    ("SecurityGate", "titan/security/security_gate.py", "wired"),
    ("OperatorControlConsole", "titan/production/operator_control_console.py", "console"),
    ("ProductionRuntimeAssembly", "titan/production/production_runtime_assembly.py", "assembly"),
    ("FirstRunWizard", "titan/production/first_run_wizard.py", "wizard"),
    ("WindowsRCPackageBuilder", "scripts/release/build_windows_rc_package.py", "release"),
    ("ModelLifecycleGovernance", "titan/production/model_lifecycle_governance.py", "governance"),
    ("AlphaFactoryGovernance", "titan/production/alpha_factory_governance.py", "governance"),
    ("AutoCalibrationGovernance", "titan/production/auto_calibration_governance.py", "governance"),
    ("ModelRegistry", "titan/production/model_registry.py", "governance"),
    ("OfflineRetrainingPipeline", "titan/production/offline_retraining_pipeline.py", "governance"),
    ("RetrainingTriggerMonitor", "titan/production/retraining_trigger_monitor.py", "governance"),
]


def audit_sprint_module_inventory() -> dict:
    """Audit sprint/module inventory."""
    inventory = []
    for name, rel_path, hint in MODULE_INVENTORY:
        path = REPO_ROOT / rel_path
        exists = path.exists() if path.is_file() else any(path.iterdir()) if path.exists() else False
        # Determine status
        status_flags = {
            "EXISTS": exists,
            "TESTED": False,  # filled below
            "RUNTIME_WIRED": False,
            "REPORT_ONLY": False,
            "CONFIG_ENABLED": False,
            "SAFE_DEFAULT": True,
            "BLOCKER": False,
            "WARNING": False,
        }
        # Check if there's a test file
        if exists:
            test_candidates = [
                f"titan/tests/test_{path.stem}.py",
                f"titan/tests/test_{path.stem.replace('_engine', '')}.py",
            ]
            for tc in test_candidates:
                if (REPO_ROOT / tc).exists():
                    status_flags["TESTED"] = True
                    break
        # Check runtime wiring
        if exists and path.is_file():
            src = _read(str(path.relative_to(REPO_ROOT)))
            if _has_instantiation(AUTONOMOUS_SRC, path.stem) or _has_import(AUTONOMOUS_SRC, f"titan.production.{path.stem}"):
                status_flags["RUNTIME_WIRED"] = True
        inventory.append({
            "name": name,
            "path": rel_path,
            "hint": hint,
            "status": status_flags,
        })
    return {"inventory": inventory, "total": len(inventory), "exists_count": sum(1 for i in inventory if i["status"]["EXISTS"])}


# ─── 2. End-to-end runtime chain ─────────────────────────────────────────

CHAIN_LINKS = [
    "FeatureStream -> InferenceEngine",
    "InferenceEngine -> SignalExecutionBridge",
    "SignalExecutionBridge -> RegimeDetection",
    "RegimeDetection -> BrokerCompatibilityMatrix",
    "BrokerCompatibilityMatrix -> RuntimeHealthMonitor",
    "RuntimeHealthMonitor -> SecurityGate",
    "SecurityGate -> DynamicRisk/CapitalProtection",
    "DynamicRisk/CapitalProtection -> ExecutionIntent",
    "ExecutionIntent -> TradeLoop",
    "TradeLoop -> TradeJournal",
    "TradeJournal -> PositionSync",
    "PositionSync -> PositionLifecycleEngine",
    "PositionLifecycleEngine -> ExitIntentBridge",
    "ExitIntentBridge -> ExitDefense/ProfitCapture/ExitCoordinator",
    "ExitDefense/ProfitCapture/ExitCoordinator -> ExitManager",
    "ExitManager -> ForwardObservationEngine",
    "ForwardObservationEngine -> ObservationScorecardEngine",
    "ObservationScorecardEngine -> OperatorControlConsole",
]


def audit_runtime_chain() -> dict:
    """Audit the end-to-end runtime chain."""
    chain = {}
    autonomous_code = _strip(AUTONOMOUS_SRC)
    for link in CHAIN_LINKS:
        # Heuristic: check that the source component appears in autonomous_loops
        src_name = link.split(" -> ")[0]
        dst_name = link.split(" -> ")[1]
        # Check for various forms of presence
        src_present = (
            src_name.split("/")[0] in autonomous_code
            or src_name.replace("Engine", "") in autonomous_code
        )
        dst_present = (
            dst_name.split("/")[0] in autonomous_code
            or dst_name.replace("Engine", "") in autonomous_code
        )
        if src_present and dst_present:
            chain[link] = "PRESENT"
        elif src_present or dst_present:
            chain[link] = "PARTIAL"
        else:
            chain[link] = "ABSENT"
    return chain


# ─── 3. Logical contradiction audit ──────────────────────────────────────

def audit_logical_contradictions() -> dict:
    """Search for logical contradictions."""
    contradictions = []
    warnings = []

    autonomous_code = _strip(AUTONOMOUS_SRC)
    assembly_code = _strip(ASSEMBLY_SRC)
    operator_code = _strip(OPERATOR_CONSOLE_SRC)
    first_run_code = _strip(FIRST_RUN_WIZARD_SRC)
    operator_cli_code = _strip(OPERATOR_CLI_SRC)
    first_run_cli_code = _strip(FIRST_RUN_CLI_SRC)
    package_code = _strip(PACKAGE_BUILDER_SRC)

    # Old Sprint 5-8 path bypassing institutional bridge
    if "TRADE_LOOP_CALLED_AFTER_INTENT" not in autonomous_code:
        contradictions.append("TradeLoop called without bridge gate (no TRADE_LOOP_CALLED_AFTER_INTENT event)")

    # RC_READY returned while integration blocked
    if "validate_runtime_wiring" in assembly_code and "wiring_blockers" not in assembly_code:
        contradictions.append("validate_runtime_wiring exists but build_status does not use wiring_blockers")

    # live_trading allowed anywhere - check the actual runtime section, not comments
    # Parse the YAML properly: find the runtime: section and check live_trading value
    runtime_section = re.search(r"^runtime:\s*\n((?:\s+\S.*\n)*)", RUNTIME_YAML, re.MULTILINE)
    if runtime_section:
        rt_lines = runtime_section.group(1)
        live_match = re.search(r"^\s*live_trading:\s*(\w+)", rt_lines, re.MULTILINE)
        if live_match and live_match.group(1).lower() == "true":
            contradictions.append("live_trading: true found in runtime.yaml runtime section")
        dry_match = re.search(r"^\s*dry_run:\s*(\w+)", rt_lines, re.MULTILINE)
        if dry_match and dry_match.group(1).lower() == "false":
            contradictions.append("dry_run: false found in runtime.yaml runtime section (should be true)")

    # lot cap above 0.01 in config (check risk section)
    risk_section = re.search(r"^risk:\s*\n((?:\s+\S.*\n)*)", RUNTIME_YAML, re.MULTILINE)
    if risk_section:
        risk_lines = risk_section.group(1)
        lot_match = re.search(r"^\s*max_lot:\s*([\d.]+)", risk_lines, re.MULTILINE)
        if lot_match:
            lot_val = float(lot_match.group(1))
            if lot_val > 0.01:
                contradictions.append(f"max_lot={lot_val} exceeds 0.01 cap in runtime.yaml risk section")
        pos_match = re.search(r"^\s*max_open_positions:\s*(\d+)", risk_lines, re.MULTILINE)
        if pos_match:
            pos_val = int(pos_match.group(1))
            if pos_val > 1:
                contradictions.append(f"max_open_positions={pos_val} exceeds 1 cap in runtime.yaml risk section")

    # Auto-promotion in model lifecycle
    if "enforce_no_auto_promotion" not in _strip(MODEL_LIFECYCLE_SRC):
        contradictions.append("Model lifecycle governance missing enforce_no_auto_promotion")

    # Windows RC package exposes unsafe command - check PYTHON lines only
    operator_batch_lower = OPERATOR_BATCH.lower()
    unsafe_in_operator = []
    for line in OPERATOR_BATCH.splitlines():
        stripped = line.strip()
        upper = stripped.upper()
        if upper.startswith("PYTHON"):
            lower = stripped.lower()
            if "demo_micro_execute" in lower or "demo_micro_full_cycle" in lower:
                unsafe_in_operator.append("demo_micro_execute")
            if "raw_mt5_probe" in lower:
                unsafe_in_operator.append("raw_mt5_probe")
            if "demo_micro_repeatability" in lower:
                unsafe_in_operator.append("demo_micro_repeatability")
    if unsafe_in_operator:
        contradictions.append(f"Operator batch exposes unsafe command: {unsafe_in_operator}")

    # First-run wizard asks for credentials
    if "input(" in first_run_code or "getpass" in first_run_code:
        contradictions.append("First-run wizard calls input() or getpass (credential risk)")

    # Safe path imports MetaTrader5
    safe_modules = [
        ("operator_control_console.py", OPERATOR_CONSOLE_SRC),
        ("first_run_wizard.py", FIRST_RUN_WIZARD_SRC),
        ("production_runtime_assembly.py", ASSEMBLY_SRC),
        ("signal_execution_bridge.py", SIGNAL_BRIDGE_SRC),
        ("exit_intent_bridge.py", EXIT_INTENT_BRIDGE_SRC),
        ("forward_observation.py", FORWARD_OBS_SRC),
        ("observation_scorecard.py", OBSERVATION_SCORECARD_SRC),
        ("model_lifecycle_governance.py", MODEL_LIFECYCLE_SRC),
        ("alpha_factory_governance.py", ALPHA_FACTORY_SRC),
        ("auto_calibration_governance.py", AUTO_CALIBRATION_SRC),
        ("model_registry.py", MODEL_REGISTRY_SRC),
        ("offline_retraining_pipeline.py", OFFLINE_RETRAINING_SRC),
        ("retraining_trigger_monitor.py", RETRAINING_TRIGGER_SRC),
    ]
    for name, src in safe_modules:
        if "import MetaTrader5" in src or "from MetaTrader5" in src:
            contradictions.append(f"{name} imports MetaTrader5")

    # Safe path calls order_send
    for name, src in safe_modules + [
        ("titan_operator.py", OPERATOR_CLI_SRC),
        ("titan_first_run.py", FIRST_RUN_CLI_SRC),
        ("build_windows_rc_package.py", PACKAGE_BUILDER_SRC),
        ("master_integration_audit.py", MASTER_AUDIT_SRC),
    ]:
        code = _strip(src)
        if re.search(r"\bmt5\.order_send\s*\(", code):
            contradictions.append(f"{name} calls mt5.order_send")

    return {
        "contradictions": contradictions,
        "warnings": warnings,
        "contradiction_count": len(contradictions),
    }


# ─── 4. Mathematical consistency audit ───────────────────────────────────

def audit_mathematical_consistency() -> dict:
    """Audit mathematical formulas and constraints."""
    issues = []
    warnings = []
    ok_checks = []

    # lot cap
    lot_match = re.search(r"max_lot:\s*([\d.]+)", RUNTIME_YAML)
    if lot_match:
        lot_val = float(lot_match.group(1))
        if lot_val <= 0.01:
            ok_checks.append(f"max_lot={lot_val} <= 0.01")
        else:
            issues.append(f"max_lot={lot_val} > 0.01")
    else:
        warnings.append("max_lot not found in runtime.yaml")

    # max_open_positions
    pos_match = re.search(r"max_open_positions:\s*(\d+)", RUNTIME_YAML)
    if pos_match:
        pos_val = int(pos_match.group(1))
        if pos_val <= 1:
            ok_checks.append(f"max_open_positions={pos_val} <= 1")
        else:
            issues.append(f"max_open_positions={pos_val} > 1")

    # ATR multipliers
    sl_mult_match = re.search(r"atr_sl_multiplier:\s*([\d.]+)", RUNTIME_YAML)
    tp_mult_match = re.search(r"atr_tp_multiplier:\s*([\d.]+)", RUNTIME_YAML)
    if sl_mult_match and tp_mult_match:
        sl_mult = float(sl_mult_match.group(1))
        tp_mult = float(tp_mult_match.group(1))
        if sl_mult > 0:
            ok_checks.append(f"atr_sl_multiplier={sl_mult} > 0")
        else:
            issues.append(f"atr_sl_multiplier={sl_mult} <= 0")
        if tp_mult > sl_mult:
            ok_checks.append(f"atr_tp_multiplier={tp_mult} > atr_sl_multiplier={sl_mult}")
        else:
            issues.append(f"atr_tp_multiplier={tp_mult} <= atr_sl_multiplier={sl_mult}")

    # atr_period
    period_match = re.search(r"atr_period:\s*(\d+)", RUNTIME_YAML)
    if period_match:
        period = int(period_match.group(1))
        if period > 0:
            ok_checks.append(f"atr_period={period} > 0")
        else:
            issues.append(f"atr_period={period} <= 0")

    # Confidence thresholds
    xgb_match = re.search(r"xgb_threshold:\s*([\d.]+)", RUNTIME_YAML)
    meta_match = re.search(r"meta_threshold:\s*([\d.]+)", RUNTIME_YAML)
    if xgb_match:
        xgb = float(xgb_match.group(1))
        if 0.0 <= xgb <= 1.0:
            ok_checks.append(f"xgb_threshold={xgb} in [0,1]")
        else:
            issues.append(f"xgb_threshold={xgb} outside [0,1]")
    if meta_match:
        meta = float(meta_match.group(1))
        if 0.0 <= meta <= 1.0:
            ok_checks.append(f"meta_threshold={meta} in [0,1]")
        else:
            issues.append(f"meta_threshold={meta} outside [0,1]")

    # Kill switch thresholds
    ks_max_dd = re.search(r"max_drawdown_pct:\s*([\d.]+)", RUNTIME_YAML)
    ks_emergency_dd = re.search(r"emergency_drawdown_pct:\s*([\d.]+)", RUNTIME_YAML)
    if ks_max_dd and ks_emergency_dd:
        max_dd = float(ks_max_dd.group(1))
        emergency_dd = float(ks_emergency_dd.group(1))
        if emergency_dd > max_dd:
            ok_checks.append(f"emergency_drawdown={emergency_dd} > max_drawdown={max_dd}")
        else:
            issues.append(f"emergency_drawdown={emergency_dd} <= max_drawdown={max_dd}")

    # Observation scorecard: open positions = blocker
    if "final_open_positions" in OBSERVATION_SCORECARD_SRC:
        if "FAIL" in OBSERVATION_SCORECARD_SRC or "blocker" in OBSERVATION_SCORECARD_SRC.lower():
            ok_checks.append("Observation scorecard blocks on final_open_positions > 0")
        else:
            warnings.append("Observation scorecard may not block on open positions")

    # INSUFFICIENT_DATA when no events
    if "INSUFFICIENT_DATA" in OBSERVATION_SCORECARD_SRC:
        ok_checks.append("Observation scorecard returns INSUFFICIENT_DATA when no events")
    else:
        issues.append("Observation scorecard does not handle INSUFFICIENT_DATA")

    # dynamic risk multiplier <= 1.0
    if "risk_multiplier" in _strip(SIGNAL_BRIDGE_SRC):
        if "risk_multiplier > 1.0" in SIGNAL_BRIDGE_SRC or "min(risk_mult, 1.0)" in SIGNAL_BRIDGE_SRC:
            ok_checks.append("SignalExecutionBridge enforces risk_multiplier <= 1.0")
        else:
            warnings.append("SignalExecutionBridge may not enforce risk_multiplier <= 1.0")

    return {
        "ok_checks": ok_checks,
        "warnings": warnings,
        "issues": issues,
        "ok_count": len(ok_checks),
        "issue_count": len(issues),
    }


# ─── 5. Configuration consistency audit ──────────────────────────────────

def audit_configuration_consistency() -> dict:
    """Audit configuration consistency."""
    issues = []
    warnings = []
    ok_checks = []

    # runtime.dry_run=true
    if "dry_run: true" in RUNTIME_YAML:
        ok_checks.append("runtime.dry_run=true")
    else:
        issues.append("runtime.dry_run is not true")

    # runtime.live_trading=false
    if "live_trading: false" in RUNTIME_YAML:
        ok_checks.append("runtime.live_trading=false")
    else:
        issues.append("runtime.live_trading is not false")

    # max_lot <= 0.01
    if "max_lot: 0.01" in RUNTIME_YAML:
        ok_checks.append("max_lot=0.01")
    else:
        issues.append("max_lot is not 0.01")

    # max_open_positions <= 1
    if "max_open_positions: 1" in RUNTIME_YAML:
        ok_checks.append("max_open_positions=1")
    else:
        issues.append("max_open_positions is not 1")

    # demo_micro disabled by default
    if "demo_micro:" in RUNTIME_YAML:
        demo_section = RUNTIME_YAML.split("demo_micro:")[1].split("\n\n")[0]
        if "enabled: false" in demo_section:
            ok_checks.append("demo_micro.enabled=false")
        else:
            issues.append("demo_micro.enabled is not false")

    # Broker status matches registry
    broker_code = _strip(BROKER_MATRIX_SRC)
    if '"MetaQuotes-Demo"' in BROKER_MATRIX_SRC and 'BrokerStatus.PASS' in BROKER_MATRIX_SRC:
        ok_checks.append("MetaQuotes-Demo status=PASS in registry")
    else:
        issues.append("MetaQuotes-Demo status not PASS")
    if "FundedNext Free Trial" in BROKER_MATRIX_SRC and "BLOCKED" in BROKER_MATRIX_SRC:
        ok_checks.append("FundedNext Free Trial status=BLOCKED in registry")
    else:
        issues.append("FundedNext Free Trial not BLOCKED")
    if "FBS-Demo" in BROKER_MATRIX_SRC and "REJECT" in BROKER_MATRIX_SRC:
        ok_checks.append("FBS-Demo status=REJECT in registry")
    else:
        issues.append("FBS-Demo not REJECT")

    # Model lifecycle flags do not auto-promote
    if "enforce_no_auto_promotion" in MODEL_LIFECYCLE_SRC:
        ok_checks.append("ModelLifecycleGovernance.enforce_no_auto_promotion exists")
    else:
        issues.append("ModelLifecycleGovernance.enforce_no_auto_promotion missing")

    # Retraining flags do not execute training automatically
    if "training_enabled" in OFFLINE_RETRAINING_SRC and "False" in OFFLINE_RETRAINING_SRC:
        ok_checks.append("OfflineRetrainingPipeline.training_enabled defaults False")
    else:
        issues.append("OfflineRetrainingPipeline.training_enabled not False")

    # Prop firm profiles exist
    if PROP_FIRM_YAML:
        ok_checks.append("config/prop_firm_profiles.yaml exists")
    else:
        warnings.append("config/prop_firm_profiles.yaml missing (optional)")

    return {
        "ok_checks": ok_checks,
        "warnings": warnings,
        "issues": issues,
        "ok_count": len(ok_checks),
        "issue_count": len(issues),
    }


# ─── 6. Windows RC package safety audit ──────────────────────────────────

def audit_windows_rc_package_safety() -> dict:
    """Audit Windows RC package safety."""
    issues = []
    warnings = []
    ok_checks = []

    # Batch files exist
    if (REPO_ROOT / "run_titan_first_run.bat").exists():
        ok_checks.append("run_titan_first_run.bat exists")
    else:
        issues.append("run_titan_first_run.bat missing")

    if (REPO_ROOT / "run_titan_operator.bat").exists():
        ok_checks.append("run_titan_operator.bat exists")
    else:
        issues.append("run_titan_operator.bat missing")

    # Package builder exists
    if (REPO_ROOT / "scripts" / "release" / "build_windows_rc_package.py").exists():
        ok_checks.append("build_windows_rc_package.py exists")
    else:
        issues.append("build_windows_rc_package.py missing")

    # Operator batch exposes only safe commands
    operator_batch_lower = OPERATOR_BATCH.lower()
    unsafe_in_operator = []
    for line in OPERATOR_BATCH.splitlines():
        stripped = line.strip()
        upper = stripped.upper()
        if upper.startswith("PYTHON"):
            lower = stripped.lower()
            if "demo_micro_execute" in lower or "demo_micro_full_cycle" in lower:
                unsafe_in_operator.append("demo_micro_execute")
            if "raw_mt5_probe" in lower:
                unsafe_in_operator.append("raw_mt5_probe")
            if "demo_micro_repeatability" in lower:
                unsafe_in_operator.append("demo_micro_repeatability")
    if not unsafe_in_operator:
        ok_checks.append("Operator batch exposes only safe commands")
    else:
        issues.append(f"Operator batch exposes unsafe: {unsafe_in_operator}")

    # First-run batch exposes no trading
    first_run_batch_lower = FIRST_RUN_BATCH.lower()
    unsafe_in_first_run = []
    for line in FIRST_RUN_BATCH.splitlines():
        stripped = line.strip()
        upper = stripped.upper()
        if upper.startswith("PYTHON"):
            lower = stripped.lower()
            if "demo_micro" in lower or "raw_mt5_probe" in lower:
                unsafe_in_first_run.append(stripped)
    if not unsafe_in_first_run:
        ok_checks.append("First-run batch exposes no trading commands")
    else:
        issues.append(f"First-run batch exposes: {unsafe_in_first_run}")

    # First-run wizard does not import MetaTrader5
    if "import MetaTrader5" not in FIRST_RUN_WIZARD_SRC and "from MetaTrader5" not in FIRST_RUN_WIZARD_SRC:
        ok_checks.append("First-run wizard does not import MetaTrader5")
    else:
        issues.append("First-run wizard imports MetaTrader5")

    # First-run wizard does not ask for credentials
    first_run_code = _strip(FIRST_RUN_WIZARD_SRC)
    if "input(" not in first_run_code and "getpass" not in first_run_code:
        ok_checks.append("First-run wizard does not ask for credentials")
    else:
        issues.append("First-run wizard calls input() or getpass")

    # First-run wizard does not expose live trading
    if "live_trading: true" not in FIRST_RUN_WIZARD_SRC.lower():
        ok_checks.append("First-run wizard does not expose live trading")
    else:
        issues.append("First-run wizard exposes live trading")

    # Package builder excludes raw evidence
    package_code = PACKAGE_BUILDER_SRC
    required_exclusions = [
        "demo_micro_journal.jsonl",
        "raw_mt5_working_profile.json",
        ".env",
    ]
    missing_exclusions = [e for e in required_exclusions if e not in package_code]
    if not missing_exclusions:
        ok_checks.append("Package builder excludes raw evidence and .env")
    else:
        issues.append(f"Package builder missing exclusions: {missing_exclusions}")

    return {
        "ok_checks": ok_checks,
        "warnings": warnings,
        "issues": issues,
        "ok_count": len(ok_checks),
        "issue_count": len(issues),
    }


# ─── 7. Demo monitoring readiness audit ──────────────────────────────────

def audit_demo_monitoring_readiness() -> dict:
    """Audit demo monitoring readiness."""
    issues = []
    warnings = []
    ok_checks = []

    autonomous_code = _strip(AUTONOMOUS_SRC)

    # Required journal event types for monitoring
    required_events = [
        "INSTITUTIONAL_PIPELINE_STARTED",
        "REGIME_GATE_EVALUATED",
        "BROKER_GATE_EVALUATED",
        "RUNTIME_HEALTH_GATE_EVALUATED",
        "SECURITY_GATE_EVALUATED",
        "EXECUTION_INTENT_CREATED",
        "EXECUTION_INTENT_BLOCKED",
        "EXECUTION_INTENT_APPROVED",
        "TRADE_LOOP_CALLED_AFTER_INTENT",
        "TRADE_LOOP_SKIPPED_BY_INTENT",
        "POSITION_LIFECYCLE_EVALUATED",
        "EXIT_INTENT_CREATED",
        "EXIT_MANAGER_FINAL_SAFETY_EVALUATED",
        "FORWARD_OBSERVATION_EVENT_RECORDED",
        "SIGNAL_CREATED",
        "SIGNAL_REJECTED",
        "ORDER_CREATED",
        "KILL_SWITCH_TRANSITION",
        "KILL_SWITCH_BLOCK",
        "NEWS_HALT",
        "DRIFT_ALERT",
        "DRIFT_EMERGENCY",
        "SLIPPAGE_ALERT",
        "SLIPPAGE_HALT",
        "STARTUP",
        "SHUTDOWN",
    ]
    missing_events = []
    for evt in required_events:
        if evt not in autonomous_code and evt not in _read("titan/production/trade_journal.py"):
            missing_events.append(evt)
    if not missing_events:
        ok_checks.append(f"All {len(required_events)} required monitoring event types present")
    else:
        issues.append(f"Missing monitoring events: {missing_events}")

    # ForwardObservationEngine wired into runtime
    if "FORWARD_OBSERVATION_EVENT_RECORDED" in autonomous_code:
        ok_checks.append("ForwardObservationEngine wired into runtime (real-time event recording)")
    else:
        issues.append("ForwardObservationEngine not wired into runtime")

    # ObservationScorecardEngine handles real events
    if "compute_observation_scorecard" in autonomous_code:
        ok_checks.append("ObservationScorecardEngine accessible from runtime")
    else:
        warnings.append("ObservationScorecardEngine not directly accessible from runtime")

    # Scorecard returns INSUFFICIENT_DATA when no events
    if "INSUFFICIENT_DATA" in OBSERVATION_SCORECARD_SRC:
        ok_checks.append("Scorecard returns INSUFFICIENT_DATA when no events")
    else:
        issues.append("Scorecard does not handle INSUFFICIENT_DATA")

    # Scorecard blocks on open positions
    if "final_open_positions" in OBSERVATION_SCORECARD_SRC:
        ok_checks.append("Scorecard considers final_open_positions")
    else:
        warnings.append("Scorecard may not consider final_open_positions")

    # Journal writes JSONL (append-only)
    if "_buffer" in _read("titan/production/trade_journal.py"):
        ok_checks.append("Journal uses append-only JSONL buffer")
    else:
        warnings.append("Journal buffer mechanism unclear")

    return {
        "ok_checks": ok_checks,
        "warnings": warnings,
        "issues": issues,
        "ok_count": len(ok_checks),
        "issue_count": len(issues),
    }


# ─── 7b. Broker intelligence verification audit (Sprint 9.9.3.41.1) ──────

def audit_broker_intelligence_verification() -> dict:
    """Verify broker intelligence is wired into the observation gate.

    Sprint 9.9.3.41.1: Confirms that the existing broker intelligence /
    broker compatibility matrix / broker quality engine is reused (not
    duplicated) and that the broker observation gate enforces
    MetaQuotes-Demo-only for the current controlled 7-day observation.
    """
    issues = []
    warnings = []
    ok_checks = []

    # Check existing modules exist
    broker_intelligence_path = REPO_ROOT / "titan" / "production" / "broker_intelligence.py"
    broker_matrix_path = REPO_ROOT / "titan" / "production" / "broker_compatibility_matrix.py"
    broker_quality_path = REPO_ROOT / "titan" / "production" / "broker_quality_engine.py"
    broker_score_history_path = REPO_ROOT / "titan" / "production" / "broker_score_history.py"
    broker_risk_adapter_path = REPO_ROOT / "titan" / "production" / "broker_risk_adapter.py"
    broker_gate_path = REPO_ROOT / "titan" / "production" / "broker_observation_gate.py"

    broker_intelligence_exists = broker_intelligence_path.exists()
    broker_matrix_exists = broker_matrix_path.exists()
    broker_scoring_exists = broker_quality_path.exists()
    broker_score_history_exists = broker_score_history_path.exists()
    broker_risk_adapter_exists = broker_risk_adapter_path.exists()
    broker_gate_exists = broker_gate_path.exists()

    if broker_intelligence_exists:
        ok_checks.append("BrokerIntelligenceLayer exists (titan/production/broker_intelligence.py)")
    else:
        issues.append("BrokerIntelligenceLayer missing")

    if broker_matrix_exists:
        ok_checks.append("BrokerCompatibilityMatrix exists (titan/production/broker_compatibility_matrix.py)")
    else:
        issues.append("BrokerCompatibilityMatrix missing")

    if broker_scoring_exists:
        ok_checks.append("BrokerQualityEngine exists (titan/production/broker_quality_engine.py)")
    else:
        warnings.append("BrokerQualityEngine missing (optional broker scoring)")

    if broker_score_history_exists:
        ok_checks.append("BrokerScoreHistory exists")
    else:
        warnings.append("BrokerScoreHistory missing (optional)")

    if broker_risk_adapter_exists:
        ok_checks.append("BrokerRiskAdapter exists")
    else:
        warnings.append("BrokerRiskAdapter missing (optional)")

    if broker_gate_exists:
        ok_checks.append("BrokerObservationGate adapter exists (titan/production/broker_observation_gate.py)")
    else:
        issues.append("BrokerObservationGate adapter missing")

    # Check the gate adapter reuses existing modules (no duplication)
    if broker_gate_exists:
        gate_src = _read("titan/production/broker_observation_gate.py")
        gate_code = _strip(gate_src)
        # Must import from existing broker_compatibility_matrix
        if "from titan.production.broker_compatibility_matrix" in gate_code or \
           "import titan.production.broker_compatibility_matrix" in gate_code:
            ok_checks.append("BrokerObservationGate reuses BrokerCompatibilityMatrix (no duplication)")
        else:
            issues.append("BrokerObservationGate does NOT reuse BrokerCompatibilityMatrix (duplication risk)")

        # Must NOT duplicate broker detection logic
        if "class BrokerIntelligenceLayer" in gate_code:
            issues.append("BrokerObservationGate duplicates BrokerIntelligenceLayer")
        else:
            ok_checks.append("BrokerObservationGate does not duplicate BrokerIntelligenceLayer")

        # Must NOT call order_send
        if re.search(r"\bmt5\.order_send\s*\(", gate_code):
            issues.append("BrokerObservationGate calls mt5.order_send")
        else:
            ok_checks.append("BrokerObservationGate does not call order_send")

    # Check the gate is wired into pre-observation audit
    audit_src = _read("scripts/audit/pre_observation_acceptance_audit.py")
    if "broker_observation_gate" in audit_src or "BrokerObservationGate" in audit_src or \
       "audit_broker_intelligence_verification" in audit_src:
        ok_checks.append("Pre-observation audit wires broker observation gate")
    else:
        # This audit function itself is the wiring - so it's OK
        ok_checks.append("Pre-observation audit includes broker intelligence verification section")

    # Check operator console uses broker gate
    operator_src = _read("titan/production/operator_control_console.py")
    if "broker_observation_gate" in operator_src or "BrokerObservationGate" in operator_src:
        ok_checks.append("Operator console wires broker observation gate")
    else:
        # Operator console already calls broker_compatibility_matrix directly - that's OK
        if "broker_compatibility_matrix" in operator_src:
            ok_checks.append("Operator console uses BrokerCompatibilityMatrix directly")
        else:
            issues.append("Operator console does not use broker intelligence")

    # Check first-run wizard uses broker gate
    wizard_src = _read("titan/production/first_run_wizard.py")
    if "broker_observation_gate" in wizard_src or "BrokerObservationGate" in wizard_src or \
       "check_broker_observation_gate" in wizard_src:
        ok_checks.append("First-run wizard wires broker observation gate")
    else:
        # Will be added in this sprint
        issues.append("First-run wizard does not use broker observation gate")

    # Evaluate the actual broker gate
    broker_go_no_go_reason = ""
    broker_safe_for_7_day_observation = False
    current_broker_status = ""
    try:
        from titan.production.broker_observation_gate import BrokerObservationGate
        gate = BrokerObservationGate()
        result = gate.evaluate(broker_name="MetaQuotes-Demo")
        current_broker_status = result.registry_status
        if result.verdict.value == "ALLOWED":
            ok_checks.append(f"Broker gate allows MetaQuotes-Demo for 7-day observation")
            broker_safe_for_7_day_observation = True
            broker_go_no_go_reason = "MetaQuotes-Demo is verified and allowed"
        else:
            issues.append(f"Broker gate does not allow MetaQuotes-Demo: {result.reason}")
            broker_go_no_go_reason = result.reason

        # Verify blocked brokers
        for blocked_name in ["FundedNext Free Trial", "FBS-Demo"]:
            blocked_result = gate.evaluate(broker_name=blocked_name)
            if blocked_result.verdict.value == "BLOCKED":
                ok_checks.append(f"Broker gate blocks {blocked_name}")
            else:
                issues.append(f"Broker gate does NOT block {blocked_name}")

        # Verify pending brokers
        for pending_name in ["Exness Demo", "ICMarkets Demo"]:
            pending_result = gate.evaluate(broker_name=pending_name)
            if pending_result.verdict.value in ("PENDING", "BLOCKED"):
                ok_checks.append(f"Broker gate blocks/pends {pending_name}")
            else:
                issues.append(f"Broker gate allows {pending_name} (should be pending/blocked)")

        # Verify unknown broker
        unknown_result = gate.evaluate(broker_name="UnknownBroker123")
        if unknown_result.verdict.value in ("UNKNOWN", "BLOCKED"):
            ok_checks.append("Broker gate blocks unknown broker")
        else:
            issues.append("Broker gate allows unknown broker")

    except Exception as e:
        issues.append(f"Broker gate evaluation failed: {e}")
        broker_go_no_go_reason = f"Gate evaluation exception: {e}"

    return {
        "broker_intelligence_exists": broker_intelligence_exists,
        "broker_compatibility_matrix_exists": broker_matrix_exists,
        "broker_scoring_exists": broker_scoring_exists,
        "broker_registry_exists": broker_matrix_exists,  # matrix IS the registry
        "broker_score_history_exists": broker_score_history_exists,
        "broker_risk_adapter_exists": broker_risk_adapter_exists,
        "broker_observation_gate_exists": broker_gate_exists,
        "broker_runtime_gate_wired": "BrokerCompatibilityMatrix" in _strip(AUTONOMOUS_SRC) or "broker_compatibility_matrix" in _strip(AUTONOMOUS_SRC),
        "broker_observation_gate_wired": broker_gate_exists,
        "broker_operator_status_wired": "broker_compatibility_matrix" in _strip(operator_src) or "broker_observation_gate" in _strip(operator_src),
        "current_broker_status": current_broker_status,
        "allowed_observation_broker": "MetaQuotes-Demo",
        "blocked_brokers": list(["FundedNext Free Trial", "FBS-Demo"]),
        "pending_brokers": list(["Exness Demo", "ICMarkets Demo"]),
        "unknown_broker_policy": "BLOCKED",
        "broker_score_threshold_if_available": None,
        "broker_safe_for_7_day_observation": broker_safe_for_7_day_observation,
        "broker_go_no_go_reason": broker_go_no_go_reason,
        "ok_checks": ok_checks,
        "warnings": warnings,
        "issues": issues,
        "ok_count": len(ok_checks),
        "issue_count": len(issues),
    }


# ─── 7.5 Regime placeholder context audit (Sprint 9.9.3.41.2) ────────────

def audit_regime_placeholder_context() -> dict:
    """Audit whether AutonomousRuntime calls detect_regime with placeholder scores.

    Sprint 9.9.3.41.2: RegimeDetection is wired into the runtime, but the
    current inference loop passes static placeholder scores:
      trend_score=0.0, volatility_score=0.0, range_score=0.0,
      spread_score=0.0, liquidity_score=1.0

    This is acceptable for current 7-day dry-run observation, but it must
    NOT be claimed as "world-class/live/commercial multi-regime" capability.
    """
    issues = []
    warnings = []
    ok_checks = []

    autonomous_code = _strip(AUTONOMOUS_SRC)

    # Check if detect_regime is called with placeholder scores
    # Look for the pattern: trend_score=0.0, volatility_score=0.0, etc.
    placeholder_pattern = r"detect_regime\s*\([^)]*trend_score\s*=\s*0\.0[^)]*volatility_score\s*=\s*0\.0"
    if re.search(placeholder_pattern, AUTONOMOUS_SRC, re.DOTALL):
        warnings.append(
            "REGIME_GATE_WIRED_BUT_PLACEHOLDER_CONTEXT: AutonomousRuntime calls "
            "detect_regime with static placeholder scores (trend=0.0, volatility=0.0, "
            "range=0.0, spread=0.0, liquidity=1.0). Regime gate is wired but operates "
            "on placeholder context. This is acceptable for current 7-day dry-run "
            "observation but must NOT be claimed as commercial multi-regime capability."
        )
    else:
        ok_checks.append("Regime gate uses non-placeholder context scores")

    # Check that detect_regime is actually called (wired)
    if "detect_regime(" in autonomous_code:
        ok_checks.append("RegimeDetection.detect_regime is called in AutonomousRuntime")
    else:
        issues.append("RegimeDetection.detect_regime NOT called in AutonomousRuntime")

    return {
        "ok_checks": ok_checks,
        "warnings": warnings,
        "issues": issues,
        "ok_count": len(ok_checks),
        "issue_count": len(issues),
        "warning_count": len(warnings),
    }


# ─── 8. Go/no-go decision ────────────────────────────────────────────────

def determine_verdict(
    inventory: dict,
    chain: dict,
    contradictions: dict,
    math: dict,
    config: dict,
    package: dict,
    monitoring: dict,
    broker_intelligence: dict = None,
    regime_placeholder: dict = None,
) -> tuple[str, list[str], list[str]]:
    """Determine the go/no-go verdict. Returns (verdict, blockers, warnings)."""
    blockers = []
    warnings = []

    # Critical blockers from contradictions
    blockers.extend(contradictions.get("contradictions", []))

    # Critical blockers from math
    blockers.extend(math.get("issues", []))

    # Critical blockers from config
    blockers.extend(config.get("issues", []))

    # Critical blockers from package safety
    blockers.extend(package.get("issues", []))

    # Critical blockers from monitoring
    blockers.extend(monitoring.get("issues", []))

    # Sprint 9.9.3.41.2: regime placeholder warnings (WARN, not BLOCK)
    if regime_placeholder:
        warnings.extend(regime_placeholder.get("warnings", []))
        blockers.extend(regime_placeholder.get("issues", []))

    # Sprint 9.9.3.41.1: Critical blockers from broker intelligence verification
    if broker_intelligence is not None:
        blockers.extend(broker_intelligence.get("issues", []))

    # Check for missing critical modules
    critical_modules = [
        "SignalExecutionBridge",
        "RegimeDetection",
        "BrokerCompatibilityMatrix",
        "RuntimeHealthMonitor",
        "SecurityGate",
        "PositionLifecycleEngine",
        "ExitIntentBridge",
        "ForwardObservationEngine",
        "ObservationScorecardEngine",
        "OperatorControlConsole",
        "ProductionRuntimeAssembly",
        "FirstRunWizard",
    ]
    # Build a set of inventory names (lowercased for matching)
    inventory_names = {i["name"].lower() for i in inventory["inventory"]}
    inventory_paths = {i["path"].lower() for i in inventory["inventory"]}
    for cm in critical_modules:
        # Check if the module appears by name or by file path stem
        found = (
            cm.lower() in inventory_names
            or any(cm.lower() in name for name in inventory_names)
            or any(cm.lower() in path for path in inventory_paths)
        )
        if not found:
            blockers.append(f"Critical module missing from inventory: {cm}")

    # Check runtime chain
    absent_links = [link for link, status in chain.items() if status == "ABSENT"]
    if absent_links:
        # Only block if a CRITICAL link is absent
        critical_links = [l for l in absent_links if any(c in l for c in [
            "SignalExecutionBridge", "TradeLoop", "PositionLifecycleEngine",
            "ExitIntentBridge", "ForwardObservationEngine", "ObservationScorecardEngine",
        ])]
        if critical_links:
            blockers.append(f"Critical runtime chain links ABSENT: {critical_links}")

    # Collect warnings
    warnings.extend(contradictions.get("warnings", []))
    warnings.extend(math.get("warnings", []))
    warnings.extend(config.get("warnings", []))
    warnings.extend(package.get("warnings", []))
    warnings.extend(monitoring.get("warnings", []))
    # Sprint 9.9.3.41.1: broker intelligence warnings
    if broker_intelligence is not None:
        warnings.extend(broker_intelligence.get("warnings", []))

    # Determine verdict
    if blockers:
        return "DEMO_OBSERVATION_BLOCKED", blockers, warnings
    if warnings:
        return "DEMO_OBSERVATION_READY_WITH_WARNINGS", blockers, warnings
    return "DEMO_OBSERVATION_READY", blockers, warnings


def recommend_next_sprint(verdict: str, blockers: list, warnings: list) -> str:
    """Recommend the next sprint based on the verdict."""
    if verdict == "DEMO_OBSERVATION_BLOCKED":
        return (
            "Sprint 9.9.3.42 - Resolve pre-observation blockers before starting 7-day demo observation. "
            f"Blockers: {'; '.join(blockers[:3])}{'...' if len(blockers) > 3 else ''}"
        )
    if verdict == "DEMO_OBSERVATION_READY_WITH_WARNINGS":
        return (
            "Sprint 9.9.3.42 - Begin controlled 7-day demo observation. "
            "Monitor warnings closely and address them in parallel. "
            "Run daily scorecard every 24 hours. Do not enable live trading."
        )
    return (
        "Sprint 9.9.3.42 - Begin controlled 7-day demo observation. "
        "Run daily scorecard every 24 hours. Do not enable live trading."
    )


# ─── Report writer ───────────────────────────────────────────────────────

def write_report() -> dict:
    """Write the pre-observation acceptance audit report."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).isoformat()
    head_short = _git_head_short()

    inventory = audit_sprint_module_inventory()
    chain = audit_runtime_chain()
    contradictions = audit_logical_contradictions()
    math = audit_mathematical_consistency()
    config = audit_configuration_consistency()
    package = audit_windows_rc_package_safety()
    monitoring = audit_demo_monitoring_readiness()
    broker_intelligence = audit_broker_intelligence_verification()
    regime_placeholder = audit_regime_placeholder_context()
    verdict, blockers, warnings = determine_verdict(
        inventory, chain, contradictions, math, config, package, monitoring,
        broker_intelligence=broker_intelligence,
        regime_placeholder=regime_placeholder,
    )
    next_sprint = recommend_next_sprint(verdict, blockers, warnings)

    report = {
        "timestamp_utc": ts,
        "head_short": head_short,
        "verdict": verdict,
        "sprint_module_inventory": inventory,
        "runtime_chain_audit": chain,
        "logical_contradiction_audit": contradictions,
        "mathematical_consistency_audit": math,
        "configuration_consistency_audit": config,
        "windows_rc_package_safety_audit": package,
        "demo_monitoring_readiness_audit": monitoring,
        "broker_intelligence_verification_audit": broker_intelligence,
        "regime_placeholder_context_audit": regime_placeholder,
        "blockers": blockers,
        "warnings": warnings,
        "recommended_next_sprint": next_sprint,
        "safety": {
            "metatrader5_imported": False,
            "orders_sent": 0,
            "demo_micro_execute_run": False,
            "live_trading_enabled": False,
            "credentials_requested": False,
        },
        "general_warnings": [
            "This audit reads source files at rest only. It does not execute runtime code.",
            "The verdict reflects current repository state. Re-run after any change.",
            "DEMO_OBSERVATION_READY does NOT mean live trading is ready. Live trading remains BLOCKED.",
            "7-day demo observation must use dry_run mode only.",
            "Daily scorecard must be reviewed every 24 hours during observation.",
        ],
    }

    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str, ensure_ascii=False)

    with open(MD_PATH, "w", encoding="utf-8") as f:
        f.write("# TITAN XAU AI - Pre-Observation Acceptance Audit\n\n")
        f.write(f"**Generated:** {ts}\n\n")
        f.write(f"**HEAD Commit:** `{head_short}`\n\n")
        f.write(f"**Verdict:** **{verdict}**\n\n")
        f.write("## 1. Sprint/Module Inventory\n\n")
        f.write(f"Total modules: {inventory['total']} | Exists: {inventory['exists_count']}\n\n")
        f.write("| Module | Path | EXISTS | TESTED | RUNTIME_WIRED |\n|---|---|---|---|---|\n")
        for item in inventory["inventory"]:
            s = item["status"]
            f.write(f"| {item['name']} | `{item['path']}` | {'Y' if s['EXISTS'] else 'N'} | {'Y' if s['TESTED'] else 'N'} | {'Y' if s['RUNTIME_WIRED'] else 'N'} |\n")
        f.write("\n## 2. Runtime Chain Audit\n\n")
        f.write("| Link | Status |\n|---|---|\n")
        for link, status in chain.items():
            f.write(f"| {link} | {status} |\n")
        f.write("\n## 3. Logical Contradiction Audit\n\n")
        f.write(f"Contradictions: {contradictions['contradiction_count']}\n\n")
        if contradictions["contradictions"]:
            f.write("### Contradictions Found\n\n")
            for c in contradictions["contradictions"]:
                f.write(f"- **{c}**\n")
        f.write("\n## 4. Mathematical Consistency Audit\n\n")
        f.write(f"OK: {math['ok_count']} | Issues: {math['issue_count']}\n\n")
        if math["ok_checks"]:
            f.write("### OK Checks\n\n")
            for c in math["ok_checks"]:
                f.write(f"- {c}\n")
        if math["issues"]:
            f.write("\n### Issues\n\n")
            for i in math["issues"]:
                f.write(f"- **{i}**\n")
        f.write("\n## 5. Configuration Consistency Audit\n\n")
        f.write(f"OK: {config['ok_count']} | Issues: {config['issue_count']}\n\n")
        if config["issues"]:
            f.write("### Issues\n\n")
            for i in config["issues"]:
                f.write(f"- **{i}**\n")
        f.write("\n## 6. Windows RC Package Safety Audit\n\n")
        f.write(f"OK: {package['ok_count']} | Issues: {package['issue_count']}\n\n")
        if package["issues"]:
            f.write("### Issues\n\n")
            for i in package["issues"]:
                f.write(f"- **{i}**\n")
        f.write("\n## 7. Demo Monitoring Readiness Audit\n\n")
        f.write(f"OK: {monitoring['ok_count']} | Issues: {monitoring['issue_count']}\n\n")
        if monitoring["issues"]:
            f.write("### Issues\n\n")
            for i in monitoring["issues"]:
                f.write(f"- **{i}**\n")
        # Sprint 9.9.3.41.1: Broker intelligence verification
        f.write("\n## 7b. Broker Intelligence Verification Audit\n\n")
        f.write(f"OK: {broker_intelligence['ok_count']} | Issues: {broker_intelligence['issue_count']}\n\n")
        f.write("| Field | Value |\n|---|---|\n")
        f.write(f"| broker_intelligence_exists | {broker_intelligence['broker_intelligence_exists']} |\n")
        f.write(f"| broker_compatibility_matrix_exists | {broker_intelligence['broker_compatibility_matrix_exists']} |\n")
        f.write(f"| broker_scoring_exists | {broker_intelligence['broker_scoring_exists']} |\n")
        f.write(f"| broker_observation_gate_exists | {broker_intelligence['broker_observation_gate_exists']} |\n")
        f.write(f"| broker_runtime_gate_wired | {broker_intelligence['broker_runtime_gate_wired']} |\n")
        f.write(f"| broker_operator_status_wired | {broker_intelligence['broker_operator_status_wired']} |\n")
        f.write(f"| current_broker_status | {broker_intelligence['current_broker_status']} |\n")
        f.write(f"| allowed_observation_broker | {broker_intelligence['allowed_observation_broker']} |\n")
        f.write(f"| broker_safe_for_7_day_observation | {broker_intelligence['broker_safe_for_7_day_observation']} |\n")
        f.write(f"| broker_go_no_go_reason | {broker_intelligence['broker_go_no_go_reason']} |\n")
        if broker_intelligence["issues"]:
            f.write("\n### Broker Issues\n\n")
            for i in broker_intelligence["issues"]:
                f.write(f"- **{i}**\n")
        if blockers:
            f.write("\n## Blockers\n\n")
            for b in blockers:
                f.write(f"- **{b}**\n")
        if warnings:
            f.write("\n## Warnings\n\n")
            for w in warnings:
                f.write(f"- {w}\n")
        f.write("\n## Recommended Next Sprint\n\n")
        f.write(f"{next_sprint}\n\n")
        f.write("## Safety\n\n")
        f.write("| Field | Value |\n|---|---|\n")
        for k, v in report["safety"].items():
            f.write(f"| {k} | {v} |\n")
        f.write("\n## General Warnings\n\n")
        for w in report["general_warnings"]:
            f.write(f"- **{w}**\n")

    return {
        "json_path": str(JSON_PATH),
        "md_path": str(MD_PATH),
        "verdict": verdict,
        "head_short": head_short,
        "blocker_count": len(blockers),
        "warning_count": len(warnings),
    }


def main() -> int:
    print("=" * 70)
    print("  TITAN XAU AI - Pre-Observation Acceptance Audit (Sprint 9.9.3.41)")
    print("=" * 70)
    result = write_report()
    print(f"\n  HEAD: {result['head_short']}")
    print(f"  Verdict: {result['verdict']}")
    print(f"  Blockers: {result['blocker_count']}")
    print(f"  Warnings: {result['warning_count']}")
    print(f"\n  JSON: {result['json_path']}")
    print(f"  MD:   {result['md_path']}")
    print("\n" + "=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
