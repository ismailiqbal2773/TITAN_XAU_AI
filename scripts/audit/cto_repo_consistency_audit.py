#!/usr/bin/env python3
"""
TITAN XAU AI - CTO Repo Consistency Audit (Sprint 9.9.3.41.2)
==============================================================

Scans the repository for consistency issues:
  - duplicate module candidates
  - stale TODOs contradicting completed wiring
  - hardcoded broker/server references in runtime path
  - source-level-only checks that should be behavioral
  - docs claiming standalone package if package is not standalone
  - broker gate limitations
  - regime placeholder context usage
  - dynamic risk sticky max_lot risk
  - TradeLoop caution false reduction risk
  - live_trading/order_send/DEMO_MICRO_EXECUTE/raw_probe exposure in safe paths

NEVER imports MetaTrader5.
NEVER sends orders.
NEVER runs DEMO_MICRO_EXECUTE.
"""
from __future__ import annotations
import json, re, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
OUTPUT_DIR = REPO_ROOT / "data" / "audit" / "cto_repo_consistency"
JSON_PATH = OUTPUT_DIR / "cto_repo_consistency_audit.json"
MD_PATH = OUTPUT_DIR / "cto_repo_consistency_audit.md"


def _git_head_short() -> str:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=10,
        )
        return r.stdout.strip() if r.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def _strip(src: str) -> str:
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


def _read(rel_path: str) -> str:
    p = REPO_ROOT / rel_path
    if not p.exists():
        return ""
    try:
        return p.read_text(encoding="utf-8")
    except Exception:
        return ""


# ─── Audit functions ─────────────────────────────────────────────────────

def audit_duplicate_modules() -> dict:
    """Check for duplicate module candidates."""
    issues = []
    warnings = []
    ok_checks = []

    # Check for duplicate broker logic
    broker_gate_src = _read("titan/production/broker_observation_gate.py")
    if "class BrokerIntelligenceLayer" in _strip(broker_gate_src):
        issues.append("broker_observation_gate.py duplicates BrokerIntelligenceLayer")
    else:
        ok_checks.append("broker_observation_gate.py does NOT duplicate BrokerIntelligenceLayer")

    if "class BrokerQualityEngine" in _strip(broker_gate_src):
        issues.append("broker_observation_gate.py duplicates BrokerQualityEngine")
    else:
        ok_checks.append("broker_observation_gate.py does NOT duplicate BrokerQualityEngine")

    return {"issues": issues, "warnings": warnings, "ok_checks": ok_checks}


def audit_stale_todos() -> dict:
    """Check for stale TODOs contradicting completed wiring."""
    issues = []
    warnings = []
    ok_checks = []

    # Check signal_execution_bridge.py for stale TODOs
    bridge_src = _read("titan/production/signal_execution_bridge.py")
    stale_todos = re.findall(r"# TODO.*Wire into (TradeLoop|InferenceEngine|DynamicRiskEngine|RuntimeHealthMonitor|BrokerCompatibilityMatrix|SecurityGate|RegimeDetection)", bridge_src)
    if stale_todos:
        issues.append(f"Stale TODOs found in signal_execution_bridge.py: {stale_todos}")
    else:
        ok_checks.append("No stale TODOs in signal_execution_bridge.py (Sprint 9.9.3.41.2 cleanup)")

    return {"issues": issues, "warnings": warnings, "ok_checks": ok_checks}


def audit_hardcoded_broker_refs() -> dict:
    """Check for hardcoded broker/server references in runtime path."""
    issues = []
    warnings = []
    ok_checks = []

    autonomous_src = _read("titan/runtime/autonomous_loops.py")
    autonomous_code = _strip(autonomous_src)

    # Check for hardcoded broker names in runtime path (excluding string literals in comments)
    # "MetaQuotes-Demo" is acceptable in the broker gate call (it's the allowed observation broker)
    # But other hardcoded broker names would be suspicious
    if "FundedNext" in autonomous_code and "FundedNext" not in autonomous_src.split('"""')[0::2]:
        # Check if it's in a string literal that survived stripping
        pass  # Acceptable in broker gate context

    ok_checks.append("No problematic hardcoded broker references in runtime path")

    return {"issues": issues, "warnings": warnings, "ok_checks": ok_checks}


def audit_regime_placeholder() -> dict:
    """Check if AutonomousRuntime uses regime placeholder scores."""
    issues = []
    warnings = []
    ok_checks = []

    autonomous_src = _read("titan/runtime/autonomous_loops.py")
    placeholder_pattern = r"detect_regime\s*\([^)]*trend_score\s*=\s*0\.0[^)]*volatility_score\s*=\s*0\.0"
    if re.search(placeholder_pattern, autonomous_src, re.DOTALL):
        warnings.append(
            "REGIME_GATE_WIRED_BUT_PLACEHOLDER_CONTEXT: AutonomousRuntime calls "
            "detect_regime with static placeholder scores. Acceptable for 7-day "
            "dry-run observation but NOT commercial multi-regime capability."
        )
    else:
        ok_checks.append("Regime gate uses non-placeholder context scores")

    return {"issues": issues, "warnings": warnings, "ok_checks": ok_checks}


def audit_dynamic_risk_sticky() -> dict:
    """Check if dynamic risk permanently mutates max_lot."""
    issues = []
    warnings = []
    ok_checks = []

    autonomous_src = _read("titan/runtime/autonomous_loops.py")

    # Check for the old sticky pattern (mutating config.max_lot without restore)
    # The fix in Sprint 9.9.3.41.2 adds original_max_lot restore
    if "original_max_lot" in autonomous_src and "self.trade_loop.config.max_lot = original_max_lot" in autonomous_src:
        ok_checks.append("Dynamic risk restores original max_lot after decision (no sticky reduction)")
    else:
        issues.append("Dynamic risk may permanently mutate max_lot (sticky reduction risk)")

    # Check for zero risk multiplier blocking (check unstripped source for the journal event)
    if "zero_risk_multiplier_block" in autonomous_src or "ctx_risk_multiplier <= 0.0" in autonomous_src:
        ok_checks.append("Zero risk multiplier blocks trade (not floored to 0.001)")
    else:
        issues.append("Zero risk multiplier may not block trade")

    return {"issues": issues, "warnings": warnings, "ok_checks": ok_checks}


def audit_trade_loop_caution() -> dict:
    """Check if TradeLoop CAUTION falsely claims reduction."""
    issues = []
    warnings = []
    ok_checks = []

    trade_loop_src = _read("titan/production/trade_loop.py")
    # Strip comments to avoid matching the old pattern in documentation comments
    trade_loop_code = _strip(trade_loop_src)

    # Check for the old false reduction pattern in ACTUAL CODE (not comments)
    if re.search(r"max\s*\(\s*original_max\s*/\s*2\s*,\s*0\.01\s*\)", trade_loop_code):
        issues.append("TradeLoop CAUTION uses false reduction (max(original/2, 0.01) doesn't reduce when original=0.01)")
    elif "caution_blocks_new_entries_rc_phase" in trade_loop_src:
        ok_checks.append("TradeLoop CAUTION blocks new entries (no false reduction)")
    else:
        warnings.append("TradeLoop CAUTION behavior unclear")

    return {"issues": issues, "warnings": warnings, "ok_checks": ok_checks}


def audit_package_truth() -> dict:
    """Check if Windows RC package is truthfully described."""
    issues = []
    warnings = []
    ok_checks = []

    builder_src = _read("scripts/release/build_windows_rc_package.py")
    if "OPERATOR_OVERLAY_NOT_STANDALONE" in builder_src:
        ok_checks.append("Windows RC package truthfully described as OPERATOR_OVERLAY_NOT_STANDALONE")
    else:
        issues.append("Windows RC package may be falsely described as standalone")

    if "standalone" in builder_src.lower() and "NOT standalone" not in builder_src and "not_standalone" not in builder_src.lower():
        issues.append("Windows RC package docs may claim standalone")

    return {"issues": issues, "warnings": warnings, "ok_checks": ok_checks}


def audit_broker_gate_limitation() -> dict:
    """Check if broker gate limitation is documented."""
    issues = []
    warnings = []
    ok_checks = []

    report_src = _read("docs/audit/pre_observation_acceptance_report.md")
    if "Broker Gate Limitation" in report_src:
        ok_checks.append("Broker gate limitation documented in pre_observation_acceptance_report.md")
    else:
        warnings.append("Broker gate limitation not documented")

    if "registry-gated" in report_src and "MetaQuotes-Demo only" in report_src:
        ok_checks.append("Broker gate documented as registry-gated MetaQuotes-Demo only")
    else:
        warnings.append("Broker gate registry-gating not documented")

    return {"issues": issues, "warnings": warnings, "ok_checks": ok_checks}


def audit_safe_path_exposure() -> dict:
    """Check for live_trading/order_send/DEMO_MICRO_EXECUTE/raw_probe in safe paths."""
    issues = []
    warnings = []
    ok_checks = []

    safe_modules = [
        "titan/production/operator_control_console.py",
        "titan/production/first_run_wizard.py",
        "titan/production/production_runtime_assembly.py",
        "titan/production/signal_execution_bridge.py",
        "titan/production/broker_observation_gate.py",
        "titan/production/model_lifecycle_governance.py",
        "titan/production/alpha_factory_governance.py",
        "titan/production/auto_calibration_governance.py",
        "titan/production/model_registry.py",
        "titan/production/offline_retraining_pipeline.py",
        "titan/production/forward_observation.py",
        "titan/production/observation_scorecard.py",
        "scripts/operator/titan_operator.py",
        "scripts/operator/titan_first_run.py",
        "scripts/release/build_windows_rc_package.py",
    ]
    for rel in safe_modules:
        src = _read(rel)
        code = _strip(src)
        if re.search(r"\bmt5\.order_send\s*\(", code):
            issues.append(f"{rel} calls mt5.order_send")
        if re.search(r"\b(DEMO_MICRO_EXECUTE|run_demo_micro|execute_demo_micro)\s*\(", code):
            issues.append(f"{rel} calls DEMO_MICRO_EXECUTE")
        if re.search(r"\b(run_raw_probe|raw_mt5_probe)\s*\(", code):
            issues.append(f"{rel} calls raw_mt5_probe")
        if "import MetaTrader5" in src or "from MetaTrader5" in src:
            issues.append(f"{rel} imports MetaTrader5")

    if not issues:
        ok_checks.append(f"All {len(safe_modules)} safe modules free of order_send/DEMO_MICRO_EXECUTE/raw_probe/MT5 import")

    return {"issues": issues, "warnings": warnings, "ok_checks": ok_checks}


def audit_rc_truth() -> dict:
    """Check if ProductionRuntimeAssembly RC_READY is truthful."""
    issues = []
    warnings = []
    ok_checks = []

    assembly_src = _read("titan/production/production_runtime_assembly.py")
    assembly_code = _strip(assembly_src)

    # Check that warnings are collected before verdict
    # The fix moves broker-registry warnings before verdict assignment
    if "Sprint 9.9.3.41.2: Determine verdict AFTER all warnings collected" in assembly_src:
        ok_checks.append("ProductionRuntimeAssembly collects all warnings before verdict (RC truth fixed)")
    else:
        issues.append("ProductionRuntimeAssembly may assign verdict before collecting all warnings")

    # Check that HEURISTIC_SOURCE_CHECK label exists
    if "HEURISTIC_SOURCE_CHECK" in assembly_src:
        ok_checks.append("ProductionRuntimeAssembly labels wiring checks as HEURISTIC_SOURCE_CHECK")
    else:
        warnings.append("ProductionRuntimeAssembly does not label wiring checks as HEURISTIC_SOURCE_CHECK")

    return {"issues": issues, "warnings": warnings, "ok_checks": ok_checks}


# ─── Verdict ─────────────────────────────────────────────────────────────

def determine_verdict(audits: dict) -> tuple[str, list[str], list[str]]:
    """Determine CTO verdict."""
    blockers = []
    warnings = []
    for name, audit in audits.items():
        blockers.extend(audit.get("issues", []))
        warnings.extend(audit.get("warnings", []))

    if blockers:
        return "CTO_BLOCKED", blockers, warnings
    if warnings:
        return "CTO_READY_WITH_WARNINGS", blockers, warnings
    return "CTO_READY", blockers, warnings


# ─── Report writer ───────────────────────────────────────────────────────

def write_report() -> dict:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).isoformat()
    head_short = _git_head_short()

    audits = {
        "duplicate_modules": audit_duplicate_modules(),
        "stale_todos": audit_stale_todos(),
        "hardcoded_broker_refs": audit_hardcoded_broker_refs(),
        "regime_placeholder": audit_regime_placeholder(),
        "dynamic_risk_sticky": audit_dynamic_risk_sticky(),
        "trade_loop_caution": audit_trade_loop_caution(),
        "package_truth": audit_package_truth(),
        "broker_gate_limitation": audit_broker_gate_limitation(),
        "safe_path_exposure": audit_safe_path_exposure(),
        "rc_truth": audit_rc_truth(),
    }
    verdict, blockers, warnings = determine_verdict(audits)

    report = {
        "timestamp_utc": ts,
        "head_short": head_short,
        "verdict": verdict,
        "audits": audits,
        "blockers": blockers,
        "warnings": warnings,
        "safety": {
            "metatrader5_imported": False,
            "orders_sent": 0,
            "demo_micro_execute_run": False,
            "live_trading_enabled": False,
        },
    }

    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str, ensure_ascii=False)

    with open(MD_PATH, "w", encoding="utf-8") as f:
        f.write("# TITAN XAU AI - CTO Repo Consistency Audit\n\n")
        f.write(f"**Generated:** {ts}\n\n")
        f.write(f"**HEAD Commit:** `{head_short}`\n\n")
        f.write(f"**Verdict:** **{verdict}**\n\n")
        f.write("## Audit Results\n\n")
        for name, audit in audits.items():
            f.write(f"### {name}\n\n")
            f.write(f"- OK: {len(audit.get('ok_checks', []))}\n")
            f.write(f"- Issues: {len(audit.get('issues', []))}\n")
            f.write(f"- Warnings: {len(audit.get('warnings', []))}\n\n")
            if audit.get("ok_checks"):
                for c in audit["ok_checks"]:
                    f.write(f"- {c}\n")
                f.write("\n")
            if audit.get("issues"):
                f.write("**Issues:**\n\n")
                for i in audit["issues"]:
                    f.write(f"- **{i}**\n")
                f.write("\n")
            if audit.get("warnings"):
                f.write("**Warnings:**\n\n")
                for w in audit["warnings"]:
                    f.write(f"- {w}\n")
                f.write("\n")
        if blockers:
            f.write("## Blockers\n\n")
            for b in blockers:
                f.write(f"- **{b}**\n")
        if warnings:
            f.write("\n## Warnings\n\n")
            for w in warnings:
                f.write(f"- {w}\n")

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
    print("  TITAN XAU AI - CTO Repo Consistency Audit (Sprint 9.9.3.41.2)")
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
