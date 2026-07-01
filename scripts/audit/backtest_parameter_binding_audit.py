#!/usr/bin/env python3
"""
TITAN XAU AI - Backtest Parameter Binding Audit (Sprint 9.9.3.45.8.3)
=====================================================================
Audits the parameter registry for backtest binding status.

Reports:
  - Total parameters
  - Validated (BACKTEST_VALIDATED)
  - Safe defaults (SAFE_DEFAULT, NEEDS_BACKTEST_BINDING)
  - Per-parameter: name, value, source, artifact_path, status, reason

Verdicts:
  - BACKTEST_BINDING_COMPLETE (all parameters validated)
  - BACKTEST_BINDING_PARTIAL (some validated, some safe defaults)
  - BACKTEST_BINDING_MISSING (all safe defaults)

NEVER sends orders. NEVER modifies positions.
"""
from __future__ import annotations
import argparse, json, sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
OUTPUT_DIR = REPO_ROOT / "data" / "audit" / "demo_micro_execution"


def run_audit() -> dict:
    ts = datetime.now(timezone.utc).isoformat()
    from titan.production.parameter_registry import ParameterRegistry

    registry = ParameterRegistry()
    summary = registry.get_summary()

    ok_checks = []
    blockers = []
    warnings = []

    total = summary["total_parameters"]
    validated = summary["validated"]
    safe_default = summary["safe_default"]
    needs_review = summary.get("needs_review", 0)
    validation_rate = summary["validation_rate"]
    critical_total = summary.get("critical_total", 0)
    critical_bound = summary.get("critical_bound", 0)
    critical_unbound = summary.get("critical_unbound", 0)
    artifacts_scanned = summary.get("artifacts_scanned", 0)

    ok_checks.append(f"Parameter registry loaded: {total} parameters")
    ok_checks.append(f"Artifacts scanned: {artifacts_scanned}")
    ok_checks.append(f"Validated: {validated}")
    ok_checks.append(f"Safe defaults: {safe_default}")
    ok_checks.append(f"Needs review: {needs_review}")
    ok_checks.append(f"Validation rate: {validation_rate:.1%}")
    ok_checks.append(f"Critical parameters: {critical_total} total, {critical_bound} bound, {critical_unbound} unbound")

    if critical_unbound > 0:
        blockers.append(f"CRITICAL_PARAMETERS_UNBOUND: {critical_unbound} critical parameters remain SAFE_DEFAULT")
        verdict = "BACKTEST_BINDING_BLOCKED"
    elif validation_rate == 1.0:
        verdict = "BACKTEST_BINDING_READY"
    elif critical_unbound == 0 and validated > 0:
        verdict = "BACKTEST_BINDING_READY_WITH_GAPS"
        warnings.append(
            f"All {critical_total} critical parameters bound. "
            f"{safe_default} non-critical parameters use safe defaults."
        )
    elif validated > 0:
        verdict = "BACKTEST_BINDING_READY_WITH_GAPS"
        warnings.append(
            f"Only {validated}/{total} parameters are validated. "
            f"{safe_default} parameters use safe defaults."
        )
    else:
        verdict = "BACKTEST_BINDING_BLOCKED"
        warnings.append(
            "No backtest artifacts found. All parameters use safe defaults. "
            "Do not claim backtest-validated until artifacts are bound."
        )

    # Also write binding report to production_closure directory
    report_dir = REPO_ROOT / "data" / "audit" / "production_closure"
    report_dir.mkdir(parents=True, exist_ok=True)
    binding_report = {
        "timestamp_utc": ts,
        "total_parameters_checked": total,
        "parameters_bound": validated,
        "parameters_safe_default": safe_default,
        "parameters_needs_review": needs_review,
        "critical_parameters_unbound": critical_unbound,
        "artifact_paths_used": list(set(p.get("artifact_path", "") for p in summary.get("parameters", []) if p.get("artifact_path"))),
        "metric_summaries": {p["parameter_name"]: p.get("metric_summary", "") for p in summary.get("parameters", []) if p.get("metric_summary")},
        "score_impact": f"Score capped at 92 due to {safe_default} safe defaults" if safe_default > 0 else "No score cap",
        "final_verdict": verdict,
    }
    with open(report_dir / "backtest_parameter_binding_report.json", "w", encoding="utf-8") as f:
        json.dump(binding_report, f, indent=2, default=str, ensure_ascii=False)
    with open(report_dir / "backtest_parameter_binding_report.md", "w", encoding="utf-8") as f:
        f.write("# TITAN XAU AI - Backtest Parameter Binding Report\n\n")
        f.write(f"**Verdict:** **{verdict}**\n\n")
        f.write(f"**Timestamp:** {ts}\n\n")
        f.write("## Summary\n\n")
        f.write("| Metric | Value |\n|---|---|\n")
        f.write(f"| Total parameters checked | {total} |\n")
        f.write(f"| Parameters bound | {validated} |\n")
        f.write(f"| Parameters safe default | {safe_default} |\n")
        f.write(f"| Parameters needs review | {needs_review} |\n")
        f.write(f"| Critical parameters unbound | {critical_unbound} |\n")
        f.write(f"| Artifacts scanned | {artifacts_scanned} |\n")
        f.write(f"| Score impact | {binding_report['score_impact']} |\n")
        f.write("\n## Artifact Paths Used\n\n")
        for p in binding_report["artifact_paths_used"]:
            f.write(f"- `{p}`\n")
        f.write("\n## Parameter Details\n\n")
        f.write("| Parameter | Value | Source | Critical | Status | Metric |\n")
        f.write("|---|---|---|---|---|---|\n")
        for p in summary.get("parameters", []):
            f.write(f"| {p['parameter_name']} | {p['runtime_value']} | {p['source']} | "
                    f"{'YES' if p.get('is_critical') else 'no'} | {p['validation_status']} | "
                    f"{p.get('metric_summary', 'N/A')[:60]} |\n")

    return {
        "timestamp_utc": ts,
        "verdict": verdict,
        "ok_checks": ok_checks,
        "blockers": blockers,
        "warnings": warnings,
        "findings": summary,
        "safety": {
            "order_send_called": False,
            "position_modified": False,
        },
    }


def write_report(result: dict) -> dict:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUTPUT_DIR / "backtest_parameter_binding_audit.json"
    md_path = OUTPUT_DIR / "backtest_parameter_binding_audit.md"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str, ensure_ascii=False)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# TITAN XAU AI - Backtest Parameter Binding Audit\n\n")
        f.write(f"**Verdict:** **{result['verdict']}**\n\n")
        f.write(f"**Timestamp:** {result['timestamp_utc']}\n\n")
        findings = result.get("findings", {})
        f.write("## Summary\n\n")
        f.write("| Field | Value |\n|---|---|\n")
        f.write(f"| total_parameters | {findings.get('total_parameters', 'N/A')} |\n")
        f.write(f"| validated | {findings.get('validated', 'N/A')} |\n")
        f.write(f"| safe_default | {findings.get('safe_default', 'N/A')} |\n")
        f.write(f"| validation_rate | {findings.get('validation_rate', 'N/A')} |\n")
        f.write("\n## Parameters\n\n")
        f.write("| Parameter | Value | Source | Status | Artifact | Reason |\n")
        f.write("|---|---|---|---|---|---|\n")
        for p in findings.get("parameters", []):
            f.write(f"| {p['parameter_name']} | {p['runtime_value']} | {p['source']} | "
                    f"{p['validation_status']} | {p.get('artifact_path', 'N/A')} | "
                    f"{p.get('reason', 'N/A')} |\n")
        if result.get("warnings"):
            f.write("\n## Warnings\n\n")
            for w in result["warnings"]:
                f.write(f"- {w}\n")
    return {"json_path": str(json_path), "md_path": str(md_path)}


def main() -> int:
    print("=" * 70)
    print("  TITAN XAU AI - Backtest Parameter Binding Audit")
    print("=" * 70)
    result = run_audit()
    report = write_report(result)
    print(f"\n  Verdict: {result['verdict']}")
    print(f"  Total: {result['findings']['total_parameters']}")
    print(f"  Validated: {result['findings']['validated']}")
    print(f"  Safe defaults: {result['findings']['safe_default']}")
    print(f"  Validation rate: {result['findings']['validation_rate']:.1%}")
    print(f"\n  JSON: {report['json_path']}")
    print(f"  MD:   {report['md_path']}")
    print("\n" + "=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
