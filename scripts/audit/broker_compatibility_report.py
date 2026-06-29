#!/usr/bin/env python3
"""
TITAN XAU AI — Sprint 9.9.3.27 Broker Compatibility Report Writer
==================================================================

Writes broker compatibility matrix to JSON + MD files.

Output:
  data/audit/broker_compatibility/broker_compatibility_matrix.json
  data/audit/broker_compatibility/broker_compatibility_matrix.md
"""
from __future__ import annotations
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

OUTPUT_DIR = REPO_ROOT / "data" / "audit" / "broker_compatibility"
JSON_PATH = OUTPUT_DIR / "broker_compatibility_matrix.json"
MD_PATH = OUTPUT_DIR / "broker_compatibility_matrix.md"

from titan.production.broker_compatibility_matrix import (
    get_all_brokers, get_broker_summary, get_priority_ranking,
)


def write_report() -> dict:
    """Write broker compatibility matrix JSON + MD.

    Returns dict with json_path, md_path.
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    brokers = get_all_brokers()
    summary = get_broker_summary()
    ranking = get_priority_ranking()
    timestamp = datetime.now(timezone.utc).isoformat()

    # JSON
    report = {
        "timestamp_utc": timestamp,
        "summary": summary,
        "priority_ranking": ranking,
        "brokers": brokers,
        "warnings": [
            "FundedNext Free Trial must NOT be used — EA/Python automation blocked by broker.",
            "Repeatability 3-cycle execution PENDING until market opens (MetaQuotes-Demo).",
        ],
    }
    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)

    # MD
    with open(MD_PATH, "w", encoding="utf-8") as f:
        f.write("# TITAN XAU AI — Broker Compatibility Matrix\n\n")
        f.write(f"**Generated:** {timestamp}\n\n")

        # Summary
        f.write("## Summary\n\n")
        f.write(f"| Metric | Value |\n|---|---|\n")
        f.write(f"| Total Brokers | {summary['total_brokers']} |\n")
        for status, count in summary["counts"].items():
            f.write(f"| {status} | {count} |\n")
        f.write(f"\n**Next broker to test:** {summary['next_broker_to_test']}\n\n")

        # Warnings
        f.write("## ⚠ Warnings\n\n")
        for w in report["warnings"]:
            f.write(f"- **{w}**\n")
        f.write("\n")

        # Priority ranking
        f.write("## Priority Ranking\n\n")
        f.write("| # | Server | Priority | Status | Risk Level |\n")
        f.write("|---|---|---|---|---|\n")
        for i, b in enumerate(ranking, 1):
            f.write(f"| {i} | {b['server_name']} | {b['priority']} | "
                    f"{b['status']} | {b['risk_level']} |\n")
        f.write("\n")

        # Detailed table
        f.write("## Detailed Compatibility Matrix\n\n")
        f.write("| Server | Status | Account | Auto | EA | Raw Probe | "
                "TITAN Micro | Repeatability | Filling | Behavior | "
                "Risk | Priority | Notes |\n")
        f.write("|---|---|---|---|---|---|---|---|---|---|---|---|---|\n")
        for b in brokers.values():
            notes_short = (b.get("notes") or "")[:60].replace("|", "/")
            f.write(
                f"| {b['server_name']} | {b['status']} | {b['account_type']} | "
                f"{'✓' if b['automation_allowed'] else '✗' if b['automation_allowed'] is False else '?'} | "
                f"{'✓' if b['ea_allowed'] else '✗' if b['ea_allowed'] is False else '?'} | "
                f"{b['raw_probe_status']} | {b['titan_micro_status']} | "
                f"{b['repeatability_status']} | {b['preferred_filling_mode'] or 'N/A'} | "
                f"{b['order_send_behavior'][:30]} | {b['risk_level']} | "
                f"{b['priority']} | {notes_short} |\n"
            )

        # Known reject reasons
        f.write("\n## Known Reject Reasons\n\n")
        for b in brokers.values():
            if b.get("known_reject_reason"):
                f.write(f"### {b['server_name']}\n\n")
                f.write(f"{b['known_reject_reason']}\n\n")

    return {"json_path": str(JSON_PATH), "md_path": str(MD_PATH)}


def main():
    print("=" * 70)
    print("  TITAN XAU AI — Broker Compatibility Report (Sprint 9.9.3.27)")
    print("=" * 70)
    result = write_report()
    print(f"\n  JSON: {result['json_path']}")
    print(f"  MD:   {result['md_path']}")

    summary = get_broker_summary()
    print(f"\n  Total brokers: {summary['total_brokers']}")
    for status, count in summary["counts"].items():
        print(f"    {status}: {count}")
    print(f"\n  Next to test: {summary['next_broker_to_test']}")
    print(f"  DO NOT USE: {', '.join(summary['do_not_use'])}")
    print("\n" + "=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
