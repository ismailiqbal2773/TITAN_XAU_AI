#!/usr/bin/env python3
"""
TITAN XAU AI - Sprint 9.9.3.37 Offline Retraining Report Writer
"""
from __future__ import annotations
import json, sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
OUTPUT_DIR = REPO_ROOT / "data" / "audit" / "model_lifecycle"
JSON_PATH = OUTPUT_DIR / "offline_retraining_report.json"
MD_PATH = OUTPUT_DIR / "offline_retraining_report.md"

from titan.production.offline_retraining_pipeline import (
    OfflineRetrainingPipeline, RetrainingTrigger, RetrainingJobStatus,
)
from titan.production.retraining_trigger_monitor import (
    RetrainingTriggerMonitor, TriggerRecommendation,
)


def write_report(
    pipeline: OfflineRetrainingPipeline = None,
    trigger_monitor: RetrainingTriggerMonitor = None,
    sample_runtime_metrics: dict = None,
) -> dict:
    """Write the offline retraining report.

    All inputs are optional. If not provided, fresh empty instances are used.
    Never imports MetaTrader5. Never sends orders. Never retrains models.
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).isoformat()

    pipeline = pipeline or OfflineRetrainingPipeline()
    trigger_monitor = trigger_monitor or RetrainingTriggerMonitor()

    # Evaluate trigger signals using sample (or empty) metrics
    runtime_metrics = sample_runtime_metrics or {}
    perf_signal = trigger_monitor.evaluate_performance_decay(runtime_metrics)
    cal_signal = trigger_monitor.evaluate_calibration_drift(runtime_metrics)
    regime_signal = trigger_monitor.evaluate_regime_shift(runtime_metrics)
    broker_signal = trigger_monitor.evaluate_broker_degradation(runtime_metrics)
    schedule_signal = trigger_monitor.evaluate_schedule_due(runtime_metrics)
    aggregate_signal = trigger_monitor.recommend_trigger(runtime_metrics)

    # Aggregate blockers / warnings
    blockers: list[str] = []
    warnings: list[str] = []

    # If any signal is INSUFFICIENT_DATA, warn
    for s in [perf_signal, cal_signal, regime_signal, broker_signal, schedule_signal]:
        if s.recommended == TriggerRecommendation.INSUFFICIENT_DATA:
            warnings.append(f"{s.trigger.value}: insufficient data - {s.reason}")

    # If any signal is NEEDS_REVIEW, warn
    for s in [perf_signal, cal_signal, regime_signal, broker_signal]:
        if s.recommended == TriggerRecommendation.NEEDS_REVIEW and s.severity.value == "CRITICAL":
            warnings.append(f"{s.trigger.value}: critical signal - {s.reason}")

    # Pipeline safety invariants
    pipeline_summary = pipeline.summary()
    if pipeline_summary["training_enabled_default"] is not False:
        blockers.append("Pipeline training_enabled_default must be False")
    if pipeline_summary["dry_run_default"] is not True:
        blockers.append("Pipeline dry_run_default must be True")
    if pipeline_summary["champion_replacement_allowed"] is not False:
        blockers.append("Pipeline champion_replacement_allowed must be False")

    # Determine final verdict
    if blockers:
        verdict = "RETRAINING_PIPELINE_BLOCKED"
    elif warnings:
        verdict = "RETRAINING_PIPELINE_WARNINGS"
    else:
        verdict = "RETRAINING_PIPELINE_READY"

    report = {
        "timestamp_utc": ts,
        "verdict": verdict,
        "trigger_monitor": {
            "performance_decay": perf_signal.to_dict(),
            "calibration_drift": cal_signal.to_dict(),
            "regime_shift": regime_signal.to_dict(),
            "broker_degradation": broker_signal.to_dict(),
            "schedule_due": schedule_signal.to_dict(),
            "aggregate_recommendation": aggregate_signal.to_dict(),
            "summary": trigger_monitor.summary(),
        },
        "pipeline": pipeline_summary,
        "retraining_job_readiness": {
            "training_enabled_default": False,
            "dry_run_default": True,
            "training_executed": False,
            "candidate_registered": False,
            "champion_replaced": False,
        },
        "candidate_registration_status": {
            "registered_stage": "CANDIDATE",
            "registry_updated": False,
            "champion_replacement_required": False,
            "manual_approval_required": True,
        },
        "champion_replacement_status": {
            "champion_replaced": False,
            "auto_promotion_allowed": False,
            "manual_approval_required": True,
        },
        "training_execution_status": {
            "training_executed": False,
            "hpo_executed": False,
            "backtest_optimization_executed": False,
            "model_artifacts_created": 0,
        },
        "blockers": blockers,
        "warnings": warnings,
        "safety": {
            "metatrader5_imported": False,
            "orders_sent": 0,
            "live_runtime_config_changed": False,
            "live_trading_enabled": False,
            "champion_replaced": False,
            "training_executed": False,
            "model_artifacts_created": 0,
        },
        "general_warnings": [
            "The retraining pipeline produces job specs and candidate metadata only.",
            "Training execution is disabled - no .fit() / train_model() / retrain() / run_hpo().",
            "Champion replacement is forbidden - manual operator approval required.",
            "Trigger monitor recommends only - it cannot launch training automatically.",
            "Insufficient data produces no trigger (INSUFFICIENT_DATA recommendation).",
            "No MetaTrader5 import. No orders sent. No live runtime config changes.",
        ],
    }

    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str, ensure_ascii=False)

    with open(MD_PATH, "w", encoding="utf-8") as f:
        f.write("# TITAN XAU AI - Offline Retraining Report\n\n")
        f.write(f"**Generated:** {ts}\n\n")
        f.write(f"**Verdict:** {verdict}\n\n")
        f.write("## Trigger Monitor\n\n")
        f.write("### Performance Decay\n\n")
        s = perf_signal
        f.write(f"- **Severity:** {s.severity.value}\n")
        f.write(f"- **Recommended:** {s.recommended.value}\n")
        f.write(f"- **Reason:** {s.reason}\n\n")
        f.write("### Calibration Drift\n\n")
        s = cal_signal
        f.write(f"- **Severity:** {s.severity.value}\n")
        f.write(f"- **Recommended:** {s.recommended.value}\n")
        f.write(f"- **Reason:** {s.reason}\n\n")
        f.write("### Regime Shift\n\n")
        s = regime_signal
        f.write(f"- **Severity:** {s.severity.value}\n")
        f.write(f"- **Recommended:** {s.recommended.value}\n")
        f.write(f"- **Reason:** {s.reason}\n\n")
        f.write("### Broker Degradation\n\n")
        s = broker_signal
        f.write(f"- **Severity:** {s.severity.value}\n")
        f.write(f"- **Recommended:** {s.recommended.value}\n")
        f.write(f"- **Reason:** {s.reason}\n\n")
        f.write("### Schedule Due\n\n")
        s = schedule_signal
        f.write(f"- **Severity:** {s.severity.value}\n")
        f.write(f"- **Recommended:** {s.recommended.value}\n")
        f.write(f"- **Reason:** {s.reason}\n\n")
        f.write("### Aggregate Recommendation\n\n")
        s = aggregate_signal
        f.write(f"- **Trigger:** {s.trigger.value}\n")
        f.write(f"- **Severity:** {s.severity.value}\n")
        f.write(f"- **Recommended:** {s.recommended.value}\n")
        f.write(f"- **Reason:** {s.reason}\n\n")
        f.write("## Pipeline\n\n")
        f.write("| Field | Value |\n|---|---|\n")
        for k, v in report["pipeline"].items():
            f.write(f"| {k} | {v} |\n")
        f.write("\n## Retraining Job Readiness\n\n")
        f.write("| Field | Value |\n|---|---|\n")
        for k, v in report["retraining_job_readiness"].items():
            f.write(f"| {k} | {v} |\n")
        f.write("\n## Candidate Registration Status\n\n")
        f.write("| Field | Value |\n|---|---|\n")
        for k, v in report["candidate_registration_status"].items():
            f.write(f"| {k} | {v} |\n")
        f.write("\n## Champion Replacement Status\n\n")
        f.write("| Field | Value |\n|---|---|\n")
        for k, v in report["champion_replacement_status"].items():
            f.write(f"| {k} | {v} |\n")
        f.write("\n## Training Execution Status\n\n")
        f.write("| Field | Value |\n|---|---|\n")
        for k, v in report["training_execution_status"].items():
            f.write(f"| {k} | {v} |\n")
        if blockers:
            f.write("\n## Blockers\n\n")
            for b in blockers:
                f.write(f"- **{b}**\n")
        if warnings:
            f.write("\n## Warnings\n\n")
            for w in warnings:
                f.write(f"- {w}\n")
        f.write("\n## Safety\n\n")
        f.write("| Field | Value |\n|---|---|\n")
        for k, v in report["safety"].items():
            f.write(f"| {k} | {v} |\n")
        f.write("\n## General Warnings\n\n")
        for w in report["general_warnings"]:
            f.write(f"- **{w}**\n")

    return {"json_path": str(JSON_PATH), "md_path": str(MD_PATH), "verdict": verdict}


def main():
    print("=" * 70)
    print("  TITAN XAU AI - Offline Retraining Report (Sprint 9.9.3.37)")
    print("=" * 70)
    result = write_report()
    print(f"\n  Verdict: {result['verdict']}")
    print(f"\n  JSON: {result['json_path']}")
    print(f"  MD:   {result['md_path']}")
    print("\n" + "=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
