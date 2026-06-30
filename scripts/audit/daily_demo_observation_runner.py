#!/usr/bin/env python3
"""
TITAN XAU AI — Sprint 9.9.3.33 Daily Demo Observation Runner
"""
from __future__ import annotations
import json, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
OUTPUT_DIR = REPO_ROOT / "data" / "audit" / "forward_observation"
JSON_PATH = OUTPUT_DIR / "daily_demo_observation_scorecard.json"
MD_PATH = OUTPUT_DIR / "daily_demo_observation_scorecard.md"

from titan.production.forward_observation import ForwardObservationEngine
from titan.production.observation_scorecard import (
    ObservationScorecardEngine, ObservationScoreGrade,
)

DEFAULT_JOURNALS = [
    str(REPO_ROOT / "data" / "audit" / "demo_micro" / "demo_micro_journal.jsonl"),
    str(REPO_ROOT / "data" / "audit" / "demo_micro" / "demo_micro_repeatability_journal.jsonl"),
]


def run_scorecard(journal_paths: list[str] = None,
                   since_hours: int = 24,
                   max_gap_seconds: int = 3600,
                   final_open_positions: int = 0) -> dict:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).isoformat()

    obs_engine = ForwardObservationEngine()
    score_engine = ObservationScorecardEngine()
    paths = journal_paths or DEFAULT_JOURNALS
    events = obs_engine.load_events_from_jsonl(paths)
    missing_journals = [p for p in paths if not Path(p).exists()]

    if since_hours and events:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=since_hours)
        filtered = []
        for e in events:
            parsed = obs_engine._parse_ts(e.timestamp_utc)
            if parsed and parsed >= cutoff:
                filtered.append(e)
        events = filtered

    gaps = obs_engine.detect_observation_gaps(events, max_gap_seconds)
    all_events = events + gaps
    summary = obs_engine.summarize(all_events)
    card = score_engine.score(summary, final_open_positions=final_open_positions)

    report = {
        "timestamp_utc": ts,
        "scorecard": {
            "date_utc": card.date_utc,
            "observation_window_hours": card.observation_window_hours,
            "total_events": card.total_events,
            "signal_count": card.signal_count,
            "execution_intent_count": card.execution_intent_count,
            "exit_intent_count": card.exit_intent_count,
            "regime_count": card.regime_count,
            "runtime_health_count": card.runtime_health_count,
            "broker_health_count": card.broker_health_count,
            "safety_block_count": card.safety_block_count,
            "observation_gap_count": card.observation_gap_count,
            "unknown_count": card.unknown_count,
            "final_open_positions": card.final_open_positions,
            "safety_score": round(card.safety_score, 1),
            "completeness_score": round(card.completeness_score, 1),
            "execution_readiness_score": round(card.execution_readiness_score, 1),
            "observation_quality_score": round(card.observation_quality_score, 1),
            "grade": card.grade.value,
            "blockers": card.blockers,
            "warnings": card.warnings,
        },
        "missing_journals": missing_journals,
        "operator_next_steps": _next_steps(card),
        "safety_note": "No market execution occurs in this runner — observation only.",
    }

    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str, ensure_ascii=False)

    with open(MD_PATH, "w", encoding="utf-8") as f:
        s = report["scorecard"]
        f.write("# TITAN XAU AI — Daily Demo Observation Scorecard\n\n")
        f.write(f"**Generated:** {ts}\n\n")
        f.write(f"**Grade:** {s['grade']}\n\n")
        f.write(f"**Date:** {s['date_utc']}\n\n")
        f.write(f"**Window:** {s['observation_window_hours']:.1f} hours\n\n")
        f.write("## Scores\n\n")
        f.write("| Metric | Score |\n|---|---|\n")
        f.write(f"| Safety | {s['safety_score']} |\n")
        f.write(f"| Completeness | {s['completeness_score']} |\n")
        f.write(f"| Execution Readiness | {s['execution_readiness_score']} |\n")
        f.write(f"| Observation Quality | {s['observation_quality_score']} |\n")
        f.write("\n## Event Counts\n\n")
        f.write("| Type | Count |\n|---|---|\n")
        for k in ["total_events", "signal_count", "execution_intent_count",
                    "exit_intent_count", "regime_count", "runtime_health_count",
                    "broker_health_count", "safety_block_count",
                    "observation_gap_count", "unknown_count"]:
            f.write(f"| {k} | {s[k]} |\n")
        f.write(f"\n**Final Open Positions:** {s['final_open_positions']}\n\n")
        if s["blockers"]:
            f.write("## Blockers\n\n")
            for b in s["blockers"]:
                f.write(f"- **{b}**\n")
        if s["warnings"]:
            f.write("\n## Warnings\n\n")
            for w in s["warnings"]:
                f.write(f"- {w}\n")
        if report["missing_journals"]:
            f.write("\n## Missing Journals\n\n")
            for m in report["missing_journals"]:
                f.write(f"- `{Path(m).name}`\n")
        f.write("\n## Operator Next Steps\n\n")
        for step in report["operator_next_steps"]:
            f.write(f"- {step}\n")
        f.write(f"\n## Safety\n\n- {report['safety_note']}\n")

    return report


def _next_steps(card) -> list[str]:
    steps = []
    if card.grade == ObservationScoreGrade.INSUFFICIENT_DATA:
        steps.append("No observation data found — run demo micro DRY_ARM_CHECK_ONLY to generate journal events")
        steps.append("Ensure TITAN is running in dry_run mode to produce signal + heartbeat events")
    elif card.grade == ObservationScoreGrade.FAIL:
        steps.append("Address blockers before continuing observation")
        if card.final_open_positions > 0:
            steps.append(f"Close {card.final_open_positions} open position(s) — final_open_positions must be 0")
        if card.safety_block_count > 0:
            steps.append("Review safety block events in the journal for root cause")
    elif card.grade == ObservationScoreGrade.WARN:
        steps.append("Review warnings — observation can continue but issues should be monitored")
    else:
        steps.append("Observation quality is good — continue daily collection")
    steps.append("Do not enable live trading")
    steps.append("Do not commit raw journal files with private account data")
    return steps


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Daily Demo Observation Runner")
    parser.add_argument("--since-hours", type=int, default=24)
    parser.add_argument("--journal", action="append", default=None)
    parser.add_argument("--max-gap-seconds", type=int, default=3600)
    parser.add_argument("--final-open-positions", type=int, default=0)
    args = parser.parse_args()

    print("=" * 70)
    print("  TITAN XAU AI — Daily Demo Observation Runner (Sprint 9.9.3.33)")
    print("=" * 70)
    report = run_scorecard(
        journal_paths=args.journal,
        since_hours=args.since_hours,
        max_gap_seconds=args.max_gap_seconds,
        final_open_positions=args.final_open_positions,
    )
    s = report["scorecard"]
    print(f"\n  Grade: {s['grade']}")
    print(f"  Quality Score: {s['observation_quality_score']}")
    print(f"  Total Events: {s['total_events']}")
    print(f"  Safety Blocks: {s['safety_block_count']}")
    print(f"\n  JSON: {JSON_PATH}")
    print(f"  MD:   {MD_PATH}")
    print("\n" + "=" * 70)
    return 0

if __name__ == "__main__":
    sys.exit(main())
