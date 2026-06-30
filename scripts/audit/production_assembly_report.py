#!/usr/bin/env python3
"""
TITAN XAU AI — Sprint 9.9.3.34 Production Assembly Report Writer
"""
from __future__ import annotations
import json, sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
OUTPUT_DIR = REPO_ROOT / "data" / "audit" / "production_assembly"
JSON_PATH = OUTPUT_DIR / "production_assembly_report.json"
MD_PATH = OUTPUT_DIR / "production_assembly_report.md"

from titan.production.production_runtime_assembly import (
    ProductionRuntimeAssembly, ProductionRuntimeMode,
)


def write_report() -> dict:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).isoformat()
    assembly = ProductionRuntimeAssembly(mode=ProductionRuntimeMode.DRY_RUN)
    status = assembly.build_status()

    report = {
        "timestamp_utc": ts,
        "mode": status.mode.value,
        "verdict": status.verdict.value,
        "components": {
            "loaded": status.components_loaded,
            "missing": status.components_missing,
            "total_required": len(status.components_loaded) + len(status.components_missing),
            "total_loaded": len(status.components_loaded),
        },
        "safety_gates": status.safety_gates_enabled,
        "execution_permissions": {
            "live_trading_enabled": status.live_trading_enabled,
            "demo_only": status.demo_only,
            "dry_run": status.dry_run,
            "execution_allowed": status.execution_allowed,
            "mt5_order_send_allowed": status.mt5_order_send_allowed,
            "max_lot": status.max_lot,
            "max_open_positions": status.max_open_positions,
        },
        "broker_registry": status.broker_status,
        "observation_status": status.observation_status,
        "runtime_health_status": status.runtime_health_status,
        "security_status": status.security_status,
        "blockers": status.blockers,
        "warnings": status.warnings,
        "warnings_general": [
            "No market execution occurs in this sprint.",
            "Production assembly is a release candidate foundation — not a live trading system.",
            "All execution must be operator-run on local Windows MT5 DEMO only.",
        ],
    }

    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str, ensure_ascii=False)

    with open(MD_PATH, "w", encoding="utf-8") as f:
        f.write("# TITAN XAU AI — Production Assembly Report\n\n")
        f.write(f"**Generated:** {ts}\n\n")
        f.write(f"**Mode:** {status.mode.value}\n\n")
        f.write(f"**Verdict:** {status.verdict.value}\n\n")
        f.write("## Component Inventory\n\n")
        f.write(f"- **Loaded:** {len(status.components_loaded)}/{report['components']['total_required']}\n")
        f.write(f"- **Missing:** {len(status.components_missing)}\n")
        if status.components_missing:
            f.write(f"- **Missing List:** {', '.join(status.components_missing)}\n")
        f.write("\n### Loaded Components\n\n")
        for c in status.components_loaded:
            f.write(f"- {c}\n")
        f.write("\n## Safety Gates\n\n")
        for g in status.safety_gates_enabled:
            f.write(f"- {g}\n")
        f.write("\n## Execution Permissions\n\n")
        f.write("| Permission | Value |\n|---|---|\n")
        for k, v in report["execution_permissions"].items():
            f.write(f"| {k} | {v} |\n")
        f.write("\n## Broker Registry\n\n")
        f.write("| Broker | Status | Priority |\n|---|---|---|\n")
        for name, info in status.broker_status.items():
            f.write(f"| {name} | {info['status']} | {info['priority']} |\n")
        f.write(f"\n## Observation Status: {status.observation_status}\n\n")
        f.write(f"## Runtime Health: {status.runtime_health_status}\n\n")
        f.write(f"## Security: {status.security_status}\n\n")
        if status.blockers:
            f.write("## Blockers\n\n")
            for b in status.blockers:
                f.write(f"- **{b}**\n")
        if status.warnings:
            f.write("\n## Warnings\n\n")
            for w in status.warnings:
                f.write(f"- {w}\n")
        f.write("\n## General Warnings\n\n")
        for w in report["warnings_general"]:
            f.write(f"- **{w}**\n")

    return {"json_path": str(JSON_PATH), "md_path": str(MD_PATH)}


def main():
    print("=" * 70)
    print("  TITAN XAU AI — Production Assembly Report (Sprint 9.9.3.34)")
    print("=" * 70)
    result = write_report()
    print(f"\n  JSON: {result['json_path']}")
    print(f"  MD:   {result['md_path']}")
    print("\n" + "=" * 70)
    return 0

if __name__ == "__main__":
    sys.exit(main())
