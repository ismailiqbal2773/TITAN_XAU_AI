#!/usr/bin/env python3
"""
TITAN XAU AI - Accelerated Observation Scorecard (Sprint 9.9.3.42.1)
=====================================================================

Reads accelerated observation reports and produces a scorecard that
clearly separates real_short, replay, and true_forward metrics.

NEVER mixes replay and real forward evidence into one misleading number.

Usage:
    python scripts/operator/run_accelerated_observation_scorecard.py
"""
from __future__ import annotations
import json, sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
OUTPUT_DIR = REPO_ROOT / "data" / "audit" / "accelerated_observation"


def _load_report(name: str) -> dict:
    path = OUTPUT_DIR / f"{name}.json"
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def run_scorecard() -> dict:
    """Produce accelerated observation scorecard."""
    ts = datetime.now(timezone.utc).isoformat()

    real_short = _load_report("real_short_observation_report")
    replay = _load_report("replay_7day_validation")
    combined = _load_report("accelerated_observation_final_report")

    # Real short metrics (clearly separated)
    real_short_metrics = {
        "available": bool(real_short),
        "verdict": real_short.get("verdict", "NOT_RUN"),
        "signal_count": real_short.get("signal_count", 0),
        "execution_intent_count": real_short.get("execution_intent_count", 0),
        "dry_run_order_count": real_short.get("dry_run_order_count", 0),
        "order_send_count": real_short.get("order_send_count", 0),
        "live_trading_detected": real_short.get("live_trading_detected", False),
        "label": "REAL_SHORT_OBSERVATION (not full 7-day forward)",
    }

    # Replay metrics (clearly separated)
    replay_metrics = {
        "available": bool(replay),
        "verdict": replay.get("verdict", "NOT_RUN"),
        "signal_count": replay.get("signal_count", 0),
        "execution_intent_count": replay.get("execution_intent_count", 0),
        "approved_intent_count": replay.get("approved_intent_count", 0),
        "blocked_intent_count": replay.get("blocked_intent_count", 0),
        "dry_run_order_count": replay.get("dry_run_order_count", 0),
        "order_send_count": replay.get("order_send_count", 0),
        "live_trading_detected": replay.get("live_trading_detected", False),
        "label": "HISTORICAL_REPLAY_VALIDATION (not real forward)",
    }

    # True forward metrics (always NOT_RUN in accelerated mode)
    true_forward_metrics = {
        "available": False,
        "verdict": "NOT_RUN",
        "label": "TRUE_7_DAY_FORWARD (not run in accelerated mode — requires real 7-day observation)",
    }

    # Combined verdict
    combined_verdict = combined.get("verdict", "NOT_RUN")

    # Determine scorecard verdict
    if real_short.get("order_send_count", 0) > 0 or replay.get("order_send_count", 0) > 0:
        verdict = "ACCELERATED_SCORECARD_FAIL"
        reason = "order_send detected in accelerated evidence"
    elif real_short.get("live_trading_detected") or replay.get("live_trading_detected"):
        verdict = "ACCELERATED_SCORECARD_FAIL"
        reason = "live_trading detected"
    elif not real_short and not replay:
        verdict = "ACCELERATED_SCORECARD_INSUFFICIENT_DATA"
        reason = "No accelerated observation reports found"
    else:
        verdict = "ACCELERATED_SCORECARD_PASS_WITH_WARNINGS"
        reason = "Accelerated validation passed with approved warnings (replay/short, not real forward)"

    return {
        "timestamp_utc": ts,
        "verdict": verdict,
        "reason": reason,
        "real_short_metrics": real_short_metrics,
        "replay_metrics": replay_metrics,
        "true_forward_metrics": true_forward_metrics,
        "combined_verdict": combined_verdict,
        "safety": {
            "order_send_total": real_short.get("order_send_count", 0) + replay.get("order_send_count", 0),
            "live_trading_detected": real_short.get("live_trading_detected", False) or replay.get("live_trading_detected", False),
            "demo_micro_execute_used": False,
            "raw_mt5_probe_used": False,
        },
        "important_note": (
            "This scorecard separates REAL_SHORT, REPLAY, and TRUE_FORWARD metrics. "
            "Replay and short observations are NOT real 7-day forward evidence. "
            "Do NOT claim 7-day forward proof, live readiness, or commercial capability."
        ),
    }


def write_report(result: dict) -> dict:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUTPUT_DIR / "accelerated_scorecard.json"
    md_path = OUTPUT_DIR / "accelerated_scorecard.md"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str, ensure_ascii=False)

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# TITAN XAU AI - Accelerated Observation Scorecard\n\n")
        f.write(f"**Verdict:** **{result['verdict']}**\n\n")
        f.write(f"**Reason:** {result['reason']}\n\n")
        f.write(f"**Timestamp:** {result['timestamp_utc']}\n\n")
        f.write("## Real Short Metrics\n\n")
        rs = result["real_short_metrics"]
        f.write(f"**Label:** {rs['label']}\n\n")
        f.write("| Metric | Value |\n|---|---|\n")
        for k, v in rs.items():
            if k != "label":
                f.write(f"| {k} | {v} |\n")
        f.write("\n## Replay Metrics\n\n")
        rp = result["replay_metrics"]
        f.write(f"**Label:** {rp['label']}\n\n")
        f.write("| Metric | Value |\n|---|---|\n")
        for k, v in rp.items():
            if k != "label":
                f.write(f"| {k} | {v} |\n")
        f.write("\n## True Forward Metrics\n\n")
        tf = result["true_forward_metrics"]
        f.write(f"**Label:** {tf['label']}\n\n")
        f.write(f"- Available: {tf['available']}\n")
        f.write(f"- Verdict: {tf['verdict']}\n\n")
        f.write("## Important Note\n\n")
        f.write(f"{result['important_note']}\n\n")
        f.write("## Safety\n\n")
        f.write("| Check | Value |\n|---|---|\n")
        for k, v in result["safety"].items():
            f.write(f"| {k} | {v} |\n")

    return {"json_path": str(json_path), "md_path": str(md_path)}


def main() -> int:
    print("=" * 70)
    print("  TITAN XAU AI - Accelerated Observation Scorecard (Sprint 9.9.3.42.1)")
    print("=" * 70)

    result = run_scorecard()
    report = write_report(result)

    print(f"\n  Verdict: {result['verdict']}")
    print(f"  Real Short Available: {result['real_short_metrics']['available']}")
    print(f"  Replay Available: {result['replay_metrics']['available']}")
    print(f"  True Forward Available: {result['true_forward_metrics']['available']}")
    print(f"\n  JSON: {report['json_path']}")
    print(f"  MD:   {report['md_path']}")
    print("\n" + "=" * 70)

    return 0 if "PASS" in result["verdict"] else 1


if __name__ == "__main__":
    sys.exit(main())
