#!/usr/bin/env python3
"""
TITAN XAU AI - 7-Day Observation Finalizer (Sprint 9.9.3.42)
=============================================================

Reads 7 daily scorecards, aggregates results, and produces a final
7-day observation report.

Usage:
    python scripts/operator/finalize_7_day_demo_observation.py

NEVER imports MetaTrader5.
NEVER sends orders.
NEVER runs DEMO_MICRO_EXECUTE.
"""
from __future__ import annotations
import argparse, json, re, sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
OUTPUT_DIR = REPO_ROOT / "data" / "audit" / "observation_7day"

APPROVED_WARNINGS = {
    "REGIME_GATE_WIRED_BUT_PLACEHOLDER_CONTEXT",
}


def _load_day_scorecards() -> list[dict]:
    """Load all available day scorecards."""
    scorecards = []
    for day in range(1, 8):
        path = OUTPUT_DIR / f"day_{day}_scorecard.json"
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    scorecards.append(json.load(f))
            except Exception:
                pass
    return scorecards


def _load_all_journal_events() -> list[dict]:
    """Load all journal events from runtime + demo micro journals."""
    journal_paths = [
        REPO_ROOT / "data" / "runtime" / "titan_journal.jsonl",
        REPO_ROOT / "data" / "audit" / "demo_micro" / "demo_micro_journal.jsonl",
        REPO_ROOT / "data" / "audit" / "demo_micro" / "demo_micro_repeatability_journal.jsonl",
    ]
    events = []
    for path in journal_paths:
        if not path.exists():
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        events.append(json.loads(line))
                    except Exception:
                        continue
        except Exception:
            continue
    return events


def _check_forbidden_evidence(events: list[dict]) -> list[str]:
    """Check for forbidden execution evidence across all events."""
    violations = []
    for event in events:
        event_str = json.dumps(event, default=str)
        lower = event_str.lower()
        # order_send in execution context
        if re.search(r"\border_send\b", event_str, re.IGNORECASE):
            if "blocked" not in lower and "absent" not in lower and "not_called" not in lower:
                if "result" in lower or "sent" in lower or "executed" in lower:
                    violations.append("order_send execution evidence found")
        # live_trading=true
        if "live_trading" in lower and "true" in lower and "blocked" not in lower:
            violations.append("live_trading=true evidence found")
        # DEMO_MICRO_EXECUTE in execution context
        if "DEMO_MICRO_EXECUTE" in event_str:
            if "blocked" not in lower and "absent" not in lower and "not_exposed" not in lower:
                violations.append("DEMO_MICRO_EXECUTE execution evidence found")
        # raw_mt5_probe in execution context
        if "raw_mt5_probe" in event_str:
            if "blocked" not in lower and "absent" not in lower and "not_exposed" not in lower:
                violations.append("raw_mt5_probe execution evidence found")
    return violations


def _count_events(events: list[dict]) -> dict:
    """Count events by type."""
    counts = {
        "signals": 0,
        "signal_rejections": 0,
        "execution_intents": 0,
        "approved_intents": 0,
        "blocked_intents": 0,
        "trade_loop_called": 0,
        "trade_loop_skipped": 0,
        "dry_run_orders": 0,
        "exit_intents": 0,
        "kill_switch_events": 0,
        "broker_gate_events": 0,
        "drift_alerts": 0,
        "calibration_alerts": 0,
        "observation_gaps": 0,
    }
    for e in events:
        et = e.get("event_type", "")
        if et == "SIGNAL_CREATED":
            counts["signals"] += 1
        elif et == "SIGNAL_REJECTED":
            counts["signal_rejections"] += 1
        elif et == "EXECUTION_INTENT_CREATED":
            counts["execution_intents"] += 1
        elif et == "EXECUTION_INTENT_APPROVED":
            counts["approved_intents"] += 1
        elif et == "EXECUTION_INTENT_BLOCKED":
            counts["blocked_intents"] += 1
        elif et == "TRADE_LOOP_CALLED_AFTER_INTENT":
            counts["trade_loop_called"] += 1
        elif et == "TRADE_LOOP_SKIPPED_BY_INTENT":
            counts["trade_loop_skipped"] += 1
        elif et == "ORDER_CREATED":
            if e.get("dry_run", True):
                counts["dry_run_orders"] += 1
        elif et == "EXIT_INTENT_CREATED":
            counts["exit_intents"] += 1
        elif et.startswith("KILL_SWITCH"):
            counts["kill_switch_events"] += 1
        elif et == "BROKER_GATE_EVALUATED":
            counts["broker_gate_events"] += 1
        elif et in ("DRIFT_ALERT", "DRIFT_EMERGENCY"):
            counts["drift_alerts"] += 1
        elif et in ("META_CALIBRATION_WATCH", "META_RECALIBRATE_REQUIRED", "META_CALIBRATION_KILL"):
            counts["calibration_alerts"] += 1
        elif et == "OBSERVATION_GAP":
            counts["observation_gaps"] += 1
    return counts


def _check_open_positions(events: list[dict]) -> int:
    """Check for open positions at final check."""
    for event in reversed(events):
        if "final_open_positions" in event:
            return int(event.get("final_open_positions", 0))
    # Check last position events
    for event in reversed(events):
        et = event.get("event_type", "")
        if et == "POSITION_CLOSED":
            return 0
        if et == "POSITION_OPENED":
            return 1
    return 0


def finalize() -> dict:
    """Run the final 7-day observation report."""
    ts = datetime.now(timezone.utc).isoformat()
    scorecards = _load_day_scorecards()
    events = _load_all_journal_events()
    event_counts = _count_events(events)
    forbidden = _check_forbidden_evidence(events)
    final_open_positions = _check_open_positions(events)

    # Collect all warnings from daily scorecards
    all_warnings = []
    for sc in scorecards:
        all_warnings.extend(sc.get("scorecard", {}).get("warnings", []))
        if sc.get("regime_placeholder_persists"):
            all_warnings.append("REGIME_GATE_WIRED_BUT_PLACEHOLDER_CONTEXT")

    # Filter approved vs unapproved
    approved_warnings = []
    unapproved_warnings = []
    for w in all_warnings:
        is_approved = any(aw.lower() in w.lower() for aw in APPROVED_WARNINGS)
        if is_approved:
            approved_warnings.append(w)
        else:
            unapproved_warnings.append(w)

    # Determine verdict
    days_observed = len(scorecards)
    missing_days = 7 - days_observed

    if forbidden:
        verdict = "SEVEN_DAY_OBSERVATION_FAIL"
        reason = f"Forbidden execution evidence: {'; '.join(forbidden)}"
    elif final_open_positions > 0:
        verdict = "SEVEN_DAY_OBSERVATION_FAIL"
        reason = f"Open positions at final check: {final_open_positions}"
    elif days_observed < 7:
        if days_observed == 0:
            verdict = "SEVEN_DAY_OBSERVATION_INSUFFICIENT_DATA"
            reason = f"No daily scorecards found (0/7 days)"
        else:
            verdict = "SEVEN_DAY_OBSERVATION_INSUFFICIENT_DATA"
            reason = f"Only {days_observed}/7 days observed (missing {missing_days} days)"
    elif any(sc.get("verdict") == "FAIL" for sc in scorecards):
        verdict = "SEVEN_DAY_OBSERVATION_FAIL"
        reason = "At least one daily scorecard returned FAIL"
    elif unapproved_warnings:
        verdict = "SEVEN_DAY_OBSERVATION_FAIL"
        reason = f"Unapproved warnings: {unapproved_warnings[:3]}"
    elif approved_warnings or any(sc.get("verdict") == "WARN" for sc in scorecards):
        verdict = "SEVEN_DAY_OBSERVATION_PASS_WITH_WARNINGS"
        reason = f"Passed with approved warnings: {set(approved_warnings)}"
    else:
        verdict = "SEVEN_DAY_OBSERVATION_PASS"
        reason = "All 7 days passed with no warnings"

    result = {
        "timestamp_utc": ts,
        "days_observed": days_observed,
        "missing_days": missing_days,
        "event_counts": event_counts,
        "forbidden_evidence": forbidden,
        "final_open_positions": final_open_positions,
        "approved_warnings": list(set(approved_warnings)),
        "unapproved_warnings": list(set(unapproved_warnings)),
        "daily_verdicts": [sc.get("verdict", "MISSING") for sc in scorecards],
        "verdict": verdict,
        "reason": reason,
        "safety": {
            "live_trading_evidence": bool(forbidden),
            "order_send_evidence": any("order_send" in v for v in forbidden),
            "demo_micro_execute_evidence": any("DEMO_MICRO_EXECUTE" in v for v in forbidden),
            "raw_mt5_probe_evidence": any("raw_mt5_probe" in v for v in forbidden),
            "open_positions_at_final": final_open_positions,
        },
    }

    return result


def write_report(result: dict) -> dict:
    """Write final 7-day observation report."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUTPUT_DIR / "final_7_day_observation_report.json"
    md_path = OUTPUT_DIR / "final_7_day_observation_report.md"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str, ensure_ascii=False)

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# TITAN XAU AI - Final 7-Day Observation Report\n\n")
        f.write(f"**Generated:** {result['timestamp_utc']}\n\n")
        f.write(f"**Verdict:** **{result['verdict']}**\n\n")
        f.write(f"**Reason:** {result['reason']}\n\n")
        f.write(f"## Days Observed: {result['days_observed']}/7\n\n")
        if result["missing_days"] > 0:
            f.write(f"**Missing Days:** {result['missing_days']}\n\n")
        f.write("## Event Counts\n\n")
        f.write("| Event Type | Count |\n|---|---|\n")
        for k, v in result["event_counts"].items():
            f.write(f"| {k} | {v} |\n")
        f.write(f"\n## Final Open Positions: {result['final_open_positions']}\n\n")
        f.write("## Daily Verdicts\n\n")
        for i, v in enumerate(result["daily_verdicts"], 1):
            f.write(f"- Day {i}: {v}\n")
        f.write("\n")
        if result.get("forbidden_evidence"):
            f.write("## Forbidden Evidence\n\n")
            for v in result["forbidden_evidence"]:
                f.write(f"- **{v}**\n")
            f.write("\n")
        if result["approved_warnings"]:
            f.write("## Approved Warnings\n\n")
            for w in result["approved_warnings"]:
                f.write(f"- {w}\n")
            f.write("\n")
        if result["unapproved_warnings"]:
            f.write("## Unapproved Warnings\n\n")
            for w in result["unapproved_warnings"]:
                f.write(f"- **{w}**\n")
            f.write("\n")
        f.write("## Safety\n\n")
        f.write("| Check | Value |\n|---|---|\n")
        for k, v in result["safety"].items():
            f.write(f"| {k} | {v} |\n")
        f.write("\n## Note\n\n")
        f.write("This 7-day observation does NOT prove world no.1, live readiness, "
                "or commercial multi-broker capability. Live trading remains BLOCKED.\n")

    return {"json_path": str(json_path), "md_path": str(md_path)}


def main() -> int:
    print("=" * 70)
    print("  TITAN XAU AI - 7-Day Observation Finalizer (Sprint 9.9.3.42)")
    print("=" * 70)

    result = finalize()
    report = write_report(result)

    print(f"\n  Verdict: {result['verdict']}")
    print(f"  Days Observed: {result['days_observed']}/7")
    print(f"  Final Open Positions: {result['final_open_positions']}")
    print(f"  Forbidden Evidence: {len(result['forbidden_evidence'])}")
    print(f"\n  JSON: {report['json_path']}")
    print(f"  MD:   {report['md_path']}")
    print("\n" + "=" * 70)

    return 0 if "PASS" in result["verdict"] else 1


if __name__ == "__main__":
    sys.exit(main())
