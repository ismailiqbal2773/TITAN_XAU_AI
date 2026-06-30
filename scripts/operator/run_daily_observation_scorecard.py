#!/usr/bin/env python3
"""
TITAN XAU AI - Daily Observation Scorecard Runner (Sprint 9.9.3.42)
====================================================================

Runs a daily scorecard for the 7-day observation period.

Usage:
    python scripts/operator/run_daily_observation_scorecard.py --day 1 --since-hours 24
    python scripts/operator/run_daily_observation_scorecard.py --day 2 --since-hours 24 --check-only

NEVER imports MetaTrader5.
NEVER sends orders.
NEVER runs DEMO_MICRO_EXECUTE.
NEVER runs raw_mt5_probe.
"""
from __future__ import annotations
import argparse, json, re, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
OUTPUT_DIR = REPO_ROOT / "data" / "audit" / "observation_7day"

DEFAULT_JOURNALS = [
    str(REPO_ROOT / "data" / "runtime" / "titan_journal.jsonl"),
    str(REPO_ROOT / "data" / "audit" / "demo_micro" / "demo_micro_journal.jsonl"),
    str(REPO_ROOT / "data" / "audit" / "demo_micro" / "demo_micro_repeatability_journal.jsonl"),
]

# Forbidden evidence patterns that indicate unsafe execution
FORBIDDEN_PATTERNS = [
    ("order_send", r"order_send"),
    ("live_trading_enabled", r"live_trading.*true"),
    ("DEMO_MICRO_EXECUTE", r"DEMO_MICRO_EXECUTE"),
    ("raw_mt5_probe", r"raw_mt5_probe"),
]


def _load_journal_events(journal_paths: list[str], since_hours: int) -> list[dict]:
    """Load events from journal JSONL files."""
    events = []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=since_hours)
    for path_str in journal_paths:
        path = Path(path_str)
        if not path.exists():
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except Exception:
                        continue
                    # Filter by timestamp if possible
                    ts = record.get("timestamp_utc") or record.get("timestamp") or ""
                    if ts and since_hours > 0:
                        try:
                            parsed = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                            if parsed < cutoff:
                                continue
                        except Exception:
                            pass
                    events.append(record)
        except Exception:
            continue
    return events


def _check_forbidden_evidence(events: list[dict]) -> list[str]:
    """Check for forbidden execution evidence in journal events."""
    violations = []
    for event in events:
        event_str = json.dumps(event, default=str)
        for name, pattern in FORBIDDEN_PATTERNS:
            if re.search(pattern, event_str, re.IGNORECASE):
                # Check if it's in a "blocked" or "rejected" context (which is OK)
                # vs an actual execution context (which is NOT OK)
                lower_str = event_str.lower()
                if name == "order_send":
                    # order_send in a "blocked" or "absent" context is OK
                    if "blocked" in lower_str or "absent" in lower_str or "not_called" in lower_str:
                        continue
                    # order_send in a "result" or "sent" context is NOT OK
                    if "result" in lower_str or "sent" in lower_str or "executed" in lower_str:
                        violations.append(f"Forbidden order_send evidence: {event.get('event_type', 'unknown')}")
                elif name == "live_trading_enabled":
                    if "true" in lower_str and "blocked" not in lower_str:
                        violations.append(f"Forbidden live_trading=true evidence: {event.get('event_type', 'unknown')}")
                elif name == "DEMO_MICRO_EXECUTE":
                    if "blocked" in lower_str or "absent" in lower_str or "not_exposed" in lower_str:
                        continue
                    violations.append(f"Forbidden DEMO_MICRO_EXECUTE evidence: {event.get('event_type', 'unknown')}")
                elif name == "raw_mt5_probe":
                    if "blocked" in lower_str or "absent" in lower_str or "not_exposed" in lower_str:
                        continue
                    violations.append(f"Forbidden raw_mt5_probe evidence: {event.get('event_type', 'unknown')}")
    return violations


def _check_open_positions(events: list[dict]) -> int:
    """Check for open positions at end of day."""
    # Look for the last POSITION_CLOSED or POSITION_OPENED event
    # If last position event is OPENED and no subsequent CLOSED, positions remain
    open_count = 0
    for event in reversed(events):
        event_type = event.get("event_type", "")
        if event_type == "POSITION_CLOSED":
            return 0  # Last position event is closed
        if event_type == "POSITION_OPENED":
            open_count += 1
            if open_count > 0:
                return open_count
    # Also check for explicit final_open_positions field
    for event in reversed(events):
        if "final_open_positions" in event:
            return int(event.get("final_open_positions", 0))
    return 0


def run_daily_scorecard(day: int, since_hours: int, journal_paths: list[str] = None,
                          check_only: bool = False) -> dict:
    """Run daily scorecard."""
    from titan.production.forward_observation import ForwardObservationEngine
    from titan.production.observation_scorecard import (
        ObservationScorecardEngine, ObservationScoreGrade,
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).isoformat()

    paths = journal_paths or DEFAULT_JOURNALS
    events = _load_journal_events(paths, since_hours)
    missing_journals = [p for p in paths if not Path(p).exists()]

    # Initialize engines
    obs_engine = ForwardObservationEngine()
    score_engine = ObservationScorecardEngine()

    # Normalize events through forward observation engine
    normalized = [obs_engine.normalize_event(e) for e in events]
    # Detect gaps
    gaps = obs_engine.detect_observation_gaps(normalized)
    all_events = normalized + gaps
    summary = obs_engine.summarize(all_events)

    # Check final open positions
    final_open_positions = _check_open_positions(events)

    # Score
    card = score_engine.score(summary, final_open_positions=final_open_positions)

    # Check for forbidden evidence
    forbidden_violations = _check_forbidden_evidence(events)

    # Determine verdict
    if forbidden_violations:
        verdict = "FAIL"
        reason = f"Forbidden execution evidence: {'; '.join(forbidden_violations)}"
    elif card.grade == ObservationScoreGrade.FAIL:
        verdict = "FAIL"
        reason = f"Scorecard FAIL: {card.blockers}"
    elif final_open_positions > 0:
        verdict = "FAIL"
        reason = f"Open positions at day end: {final_open_positions}"
    elif not events:
        verdict = "INSUFFICIENT_DATA"
        reason = "No journal events found"
    elif card.grade == ObservationScoreGrade.INSUFFICIENT_DATA:
        verdict = "INSUFFICIENT_DATA"
        reason = "Insufficient observation data"
    elif card.grade == ObservationScoreGrade.WARN or missing_journals:
        verdict = "WARN"
        reason = f"Warnings: {card.warnings}"
        if missing_journals:
            reason += f"; Missing journals: {[Path(p).name for p in missing_journals]}"
    else:
        verdict = "PASS"
        reason = "All checks pass"

    # Check for regime placeholder warning persistence
    regime_placeholder = any(
        "REGIME_GATE_WIRED_BUT_PLACEHOLDER_CONTEXT" in str(e)
        for e in events
    )
    if regime_placeholder and verdict == "PASS":
        verdict = "WARN"
        reason += "; REGIME_GATE_WIRED_BUT_PLACEHOLDER_CONTEXT persists"

    result = {
        "timestamp_utc": ts,
        "day": day,
        "since_hours": since_hours,
        "journal_paths": [Path(p).name for p in paths],
        "missing_journals": [Path(p).name for p in missing_journals],
        "total_events": len(events),
        "scorecard": {
            "grade": card.grade.value,
            "safety_score": round(card.safety_score, 1),
            "completeness_score": round(card.completeness_score, 1),
            "execution_readiness_score": round(card.execution_readiness_score, 1),
            "observation_quality_score": round(card.observation_quality_score, 1),
            "final_open_positions": final_open_positions,
            "blockers": card.blockers,
            "warnings": card.warnings,
        },
        "forbidden_evidence": forbidden_violations,
        "regime_placeholder_persists": regime_placeholder,
        "verdict": verdict,
        "reason": reason,
        "safety": {
            "live_trading_evidence": any("live_trading" in str(e).lower() and "true" in str(e).lower() for e in events),
            "order_send_evidence": bool(forbidden_violations),
            "demo_micro_execute_evidence": any("DEMO_MICRO_EXECUTE" in str(e) for e in events if "blocked" not in str(e).lower()),
            "raw_mt5_probe_evidence": any("raw_mt5_probe" in str(e) for e in events if "blocked" not in str(e).lower()),
        },
    }

    return result


def write_report(result: dict) -> dict:
    """Write day scorecard report."""
    day = result["day"]
    json_path = OUTPUT_DIR / f"day_{day}_scorecard.json"
    md_path = OUTPUT_DIR / f"day_{day}_scorecard.md"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str, ensure_ascii=False)

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# TITAN XAU AI - Day {day} Observation Scorecard\n\n")
        f.write(f"**Generated:** {result['timestamp_utc']}\n\n")
        f.write(f"**Day:** {result['day']}\n\n")
        f.write(f"**Since Hours:** {result['since_hours']}\n\n")
        f.write(f"**Verdict:** **{result['verdict']}**\n\n")
        f.write(f"**Reason:** {result['reason']}\n\n")
        f.write("## Scorecard\n\n")
        s = result["scorecard"]
        f.write("| Metric | Value |\n|---|---|\n")
        f.write(f"| Grade | {s['grade']} |\n")
        f.write(f"| Safety Score | {s['safety_score']} |\n")
        f.write(f"| Completeness Score | {s['completeness_score']} |\n")
        f.write(f"| Execution Readiness | {s['execution_readiness_score']} |\n")
        f.write(f"| Observation Quality | {s['observation_quality_score']} |\n")
        f.write(f"| Final Open Positions | {s['final_open_positions']} |\n")
        f.write(f"\n**Total Events:** {result['total_events']}\n\n")
        if result.get("missing_journals"):
            f.write("## Missing Journals\n\n")
            for m in result["missing_journals"]:
                f.write(f"- `{m}`\n")
            f.write("\n")
        if result.get("forbidden_evidence"):
            f.write("## Forbidden Evidence\n\n")
            for v in result["forbidden_evidence"]:
                f.write(f"- **{v}**\n")
            f.write("\n")
        if s.get("blockers"):
            f.write("## Blockers\n\n")
            for b in s["blockers"]:
                f.write(f"- **{b}**\n")
            f.write("\n")
        if s.get("warnings"):
            f.write("## Warnings\n\n")
            for w in s["warnings"]:
                f.write(f"- {w}\n")
            f.write("\n")
        f.write("## Safety\n\n")
        f.write("| Check | Value |\n|---|---|\n")
        for k, v in result["safety"].items():
            f.write(f"| {k} | {v} |\n")

    return {"json_path": str(json_path), "md_path": str(md_path)}


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="run_daily_observation_scorecard",
        description="Daily observation scorecard runner",
    )
    parser.add_argument("--day", type=int, required=True, help="Day number (1-7)")
    parser.add_argument("--since-hours", type=int, default=24)
    parser.add_argument("--journal-path", action="append", default=None)
    parser.add_argument("--check-only", action="store_true", default=False)
    args = parser.parse_args()

    print("=" * 70)
    print(f"  TITAN XAU AI - Day {args.day} Observation Scorecard (Sprint 9.9.3.42)")
    print("=" * 70)

    result = run_daily_scorecard(
        day=args.day,
        since_hours=args.since_hours,
        journal_paths=args.journal_path,
        check_only=args.check_only,
    )
    report = write_report(result)

    print(f"\n  Day: {result['day']}")
    print(f"  Verdict: {result['verdict']}")
    print(f"  Events: {result['total_events']}")
    print(f"  Open Positions: {result['scorecard']['final_open_positions']}")
    print(f"\n  JSON: {report['json_path']}")
    print(f"  MD:   {report['md_path']}")
    print("\n" + "=" * 70)

    return 0 if result["verdict"] in ("PASS", "WARN", "INSUFFICIENT_DATA") else 1


if __name__ == "__main__":
    sys.exit(main())
