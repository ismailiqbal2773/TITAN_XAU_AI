#!/usr/bin/env python3
"""
TITAN XAU AI — Sprint 9.9.3.32 Forward Observation Report Writer
"""
from __future__ import annotations
import json, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
OUTPUT_DIR = REPO_ROOT / "data" / "audit" / "forward_observation"
JSON_PATH = OUTPUT_DIR / "forward_observation_report.json"
MD_PATH = OUTPUT_DIR / "forward_observation_report.md"

from titan.production.forward_observation import (
    ForwardObservationEngine, ForwardObservationEventType,
)

DEFAULT_JOURNALS = [
    str(REPO_ROOT / "data" / "audit" / "demo_micro" / "demo_micro_journal.jsonl"),
    str(REPO_ROOT / "data" / "audit" / "demo_micro" / "demo_micro_repeatability_journal.jsonl"),
]


def write_report(journal_paths: list[str] = None,
                  since_hours: int = None,
                  max_gap_seconds: int = 3600) -> dict:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).isoformat()
    engine = ForwardObservationEngine()
    paths = journal_paths or DEFAULT_JOURNALS
    events = engine.load_events_from_jsonl(paths)
    missing_journals = [p for p in paths if not Path(p).exists()]

    # Filter by since_hours if specified
    if since_hours and events:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=since_hours)
        filtered = []
        for e in events:
            parsed = engine._parse_ts(e.timestamp_utc)
            if parsed and parsed >= cutoff:
                filtered.append(e)
        events = filtered

    # Detect gaps
    gaps = engine.detect_observation_gaps(events, max_gap_seconds)
    all_events = events + gaps

    # Summarize
    summary = engine.summarize(all_events)

    # Determine verdict
    if not summary.safe_to_continue_observation:
        verdict = "OBSERVATION_BLOCKED"
    elif summary.warnings:
        verdict = "OBSERVATION_WARNINGS"
    else:
        verdict = "OBSERVATION_READY"

    report = {
        "timestamp_utc": ts,
        "observation_window": {
            "start_utc": summary.start_utc,
            "end_utc": summary.end_utc,
            "since_hours": since_hours,
        },
        "journal_paths": [str(Path(p).name) for p in paths],
        "missing_journals": missing_journals,
        "counts": {
            "total_events": summary.total_events,
            "signal_count": summary.signal_count,
            "execution_intent_count": summary.execution_intent_count,
            "exit_intent_count": summary.exit_intent_count,
            "regime_count": summary.regime_count,
            "safety_block_count": summary.safety_block_count,
            "heartbeat_count": summary.heartbeat_count,
            "observation_gap_count": summary.observation_gap_count,
            "broker_health_count": summary.broker_health_count,
            "runtime_health_count": summary.runtime_health_count,
            "unknown_count": summary.unknown_count,
        },
        "safety_blocks": summary.blockers,
        "warnings": summary.warnings,
        "verdict": verdict,
        "safe_to_continue": summary.safe_to_continue_observation,
        "event_types": [e.value for e in ForwardObservationEventType],
        "warnings_general": [
            "No market execution occurs in this sprint — observation only.",
            "Forward observation is non-blocking and does not place trades.",
        ],
    }

    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str, ensure_ascii=False)

    with open(MD_PATH, "w", encoding="utf-8") as f:
        f.write("# TITAN XAU AI — Forward Observation Report\n\n")
        f.write(f"**Generated:** {ts}\n\n")
        f.write(f"**Verdict:** {verdict}\n\n")
        f.write(f"**Safe to Continue:** {summary.safe_to_continue_observation}\n\n")
        f.write("## Observation Window\n\n")
        f.write(f"| Field | Value |\n|---|---|\n")
        f.write(f"| Start | {summary.start_utc or 'N/A'} |\n")
        f.write(f"| End | {summary.end_utc or 'N/A'} |\n")
        f.write(f"| Since Hours | {since_hours or 'all'} |\n\n")
        f.write("## Event Counts\n\n")
        f.write("| Type | Count |\n|---|---|\n")
        for k, v in report["counts"].items():
            f.write(f"| {k} | {v} |\n")
        f.write("\n## Journals\n\n")
        for p in report["journal_paths"]:
            status = "MISSING" if any(p in m for m in missing_journals) else "OK"
            f.write(f"- `{p}`: {status}\n")
        if summary.blockers:
            f.write("\n## Safety Blocks\n\n")
            for b in summary.blockers:
                f.write(f"- **{b}**\n")
        if summary.warnings:
            f.write("\n## Warnings\n\n")
            for w in summary.warnings:
                f.write(f"- {w}\n")
        f.write("\n## General Warnings\n\n")
        for w in report["warnings_general"]:
            f.write(f"- **{w}**\n")

    return {"json_path": str(JSON_PATH), "md_path": str(MD_PATH)}


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Forward Observation Report")
    parser.add_argument("--journal", action="append", default=None)
    parser.add_argument("--since-hours", type=int, default=None)
    parser.add_argument("--max-gap-seconds", type=int, default=3600)
    args = parser.parse_args()

    print("=" * 70)
    print("  TITAN XAU AI — Forward Observation Report (Sprint 9.9.3.32)")
    print("=" * 70)
    result = write_report(
        journal_paths=args.journal,
        since_hours=args.since_hours,
        max_gap_seconds=args.max_gap_seconds,
    )
    print(f"\n  JSON: {result['json_path']}")
    print(f"  MD:   {result['md_path']}")
    print("\n" + "=" * 70)
    return 0

if __name__ == "__main__":
    sys.exit(main())
