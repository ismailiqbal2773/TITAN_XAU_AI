#!/usr/bin/env python3
"""
TITAN XAU AI - First-Run Wizard CLI (Sprint 9.9.3.40)
======================================================

Non-technical operator first-run wizard CLI.

Usage:
    python scripts/operator/titan_first_run.py
    python scripts/operator/titan_first_run.py --json

NEVER imports MetaTrader5.
NEVER sends orders.
NEVER asks for credentials.
"""
from __future__ import annotations
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from titan.production.first_run_wizard import (
    FirstRunWizard, FirstRunCheckStatus,
)

OUTPUT_DIR = REPO_ROOT / "data" / "audit" / "operator"
JSON_PATH = OUTPUT_DIR / "first_run_wizard_report.json"
MD_PATH = OUTPUT_DIR / "first_run_wizard_report.md"


def _print_human(summary) -> None:
    print("=" * 72)
    print("  TITAN XAU AI - First-Run Wizard")
    print("=" * 72)
    print(f"  Overall: {summary.overall_status.value}")
    print(f"  Passed: {summary.passed}  Warnings: {summary.warnings}  "
          f"Failed: {summary.failed}  Skipped: {summary.skipped}")
    print(f"  Timestamp: {summary.timestamp_utc}")
    print()
    for r in summary.results:
        icon = {"PASS": "[OK]", "WARN": "[!!]", "FAIL": "[XX]", "SKIP": "[--]"}[r.status.value]
        print(f"  {icon} {r.check_name}: {r.message}")
        if r.next_step:
            print(f"       next: {r.next_step}")
    print()
    if summary.blockers:
        print("  BLOCKERS:")
        for b in summary.blockers:
            print(f"    - {b}")
        print()
    if summary.next_steps:
        print("  NEXT STEPS:")
        for s in summary.next_steps:
            print(f"    -> {s}")
    print()
    print("=" * 72)


def write_report(summary) -> dict:
    """Write first-run wizard report (JSON + MD)."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "timestamp_utc": summary.timestamp_utc,
        "overall_status": summary.overall_status.value,
        "counts": {
            "passed": summary.passed,
            "warnings": summary.warnings,
            "failed": summary.failed,
            "skipped": summary.skipped,
        },
        "results": [r.to_dict() for r in summary.results],
        "blockers": summary.blockers,
        "next_steps": summary.next_steps,
        "safety": {
            "metatrader5_imported": False,
            "orders_sent": 0,
            "demo_micro_execute_run": False,
            "live_trading_enabled": False,
            "credentials_requested": False,
        },
        "general_warnings": [
            "First-run wizard never imports MetaTrader5.",
            "First-run wizard never sends orders.",
            "First-run wizard never asks for account password or API key.",
            "Live trading remains BLOCKED.",
            "Market execution is NOT available from this wizard.",
        ],
    }
    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str, ensure_ascii=False)

    with open(MD_PATH, "w", encoding="utf-8") as f:
        f.write("# TITAN XAU AI - First-Run Wizard Report\n\n")
        f.write(f"**Generated:** {summary.timestamp_utc}\n\n")
        f.write(f"**Overall Status:** **{summary.overall_status.value}**\n\n")
        f.write("## Counts\n\n")
        f.write("| Status | Count |\n|---|---|\n")
        f.write(f"| PASS | {summary.passed} |\n")
        f.write(f"| WARN | {summary.warnings} |\n")
        f.write(f"| FAIL | {summary.failed} |\n")
        f.write(f"| SKIP | {summary.skipped} |\n\n")
        f.write("## Check Results\n\n")
        f.write("| Check | Status | Message |\n|---|---|---|\n")
        for r in summary.results:
            f.write(f"| {r.check_name} | {r.status.value} | {r.message} |\n")
        f.write("\n## Per-Check Details\n\n")
        for r in summary.results:
            f.write(f"### {r.check_name} ({r.status.value})\n\n")
            f.write(f"**Message:** {r.message}\n\n")
            if r.details:
                f.write("**Details:**\n\n```\n")
                f.write(json.dumps(r.details, indent=2, default=str))
                f.write("\n```\n\n")
            if r.next_step:
                f.write(f"**Next Step:** {r.next_step}\n\n")
        if summary.blockers:
            f.write("## Blockers\n\n")
            for b in summary.blockers:
                f.write(f"- **{b}**\n")
            f.write("\n")
        if summary.next_steps:
            f.write("## Next Steps\n\n")
            for s in summary.next_steps:
                f.write(f"- {s}\n")
            f.write("\n")
        f.write("## Safety\n\n")
        f.write("| Field | Value |\n|---|---|\n")
        for k, v in payload["safety"].items():
            f.write(f"| {k} | {v} |\n")
        f.write("\n## General Warnings\n\n")
        for w in payload["general_warnings"]:
            f.write(f"- **{w}**\n")

    return {"json_path": str(JSON_PATH), "md_path": str(MD_PATH)}


def main(argv: list[str] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="titan_first_run",
        description="TITAN XAU AI first-run wizard (safe, no live trading)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON output instead of human-readable text.",
    )
    args = parser.parse_args(argv)

    wizard = FirstRunWizard()
    summary = wizard.run_all()

    try:
        report_paths = write_report(summary)
    except Exception as e:
        print(f"WARNING: failed to write report: {e}", file=sys.stderr)

    if args.json:
        print(json.dumps(summary.to_dict(), indent=2, default=str, ensure_ascii=False))
    else:
        _print_human(summary)
        print(f"  JSON: {JSON_PATH}")
        print(f"  MD:   {MD_PATH}")
        print("=" * 72)

    return 0 if summary.overall_status != FirstRunCheckStatus.FAIL else 1


if __name__ == "__main__":
    sys.exit(main())
