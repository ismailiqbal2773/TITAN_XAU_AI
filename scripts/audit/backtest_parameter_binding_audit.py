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
    validation_rate = summary["validation_rate"]

    ok_checks.append(f"Parameter registry loaded: {total} parameters")
    ok_checks.append(f"Validated (BACKTEST_VALIDATED): {validated}")
    ok_checks.append(f"Safe defaults (NEEDS_BACKTEST_BINDING): {safe_default}")
    ok_checks.append(f"Validation rate: {validation_rate:.1%}")

    if validation_rate == 1.0:
        verdict = "BACKTEST_BINDING_COMPLETE"
    elif validation_rate > 0:
        verdict = "BACKTEST_BINDING_PARTIAL"
        warnings.append(
            f"Only {validated}/{total} parameters are backtest-validated. "
            f"{safe_default} parameters use safe defaults."
        )
    else:
        verdict = "BACKTEST_BINDING_MISSING"
        warnings.append(
            "No backtest artifacts found. All parameters use safe defaults. "
            "Do not claim backtest-validated until artifacts are bound."
        )

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
