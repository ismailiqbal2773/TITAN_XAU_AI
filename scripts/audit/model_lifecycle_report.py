#!/usr/bin/env python3
"""
TITAN XAU AI - Sprint 9.9.3.36 Model Lifecycle Report Writer
"""
from __future__ import annotations
import json, sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
OUTPUT_DIR = REPO_ROOT / "data" / "audit" / "model_lifecycle"
JSON_PATH = OUTPUT_DIR / "model_lifecycle_report.json"
MD_PATH = OUTPUT_DIR / "model_lifecycle_report.md"

from titan.production.model_lifecycle_governance import (
    ModelLifecycleGovernance, ModelLifecycleStage, ModelApprovalStatus,
)
from titan.production.auto_calibration_governance import (
    AutoCalibrationGovernance,
)
from titan.production.alpha_factory_governance import (
    AlphaFactoryGovernance, AlphaCandidateType,
)
from titan.production.model_registry import ModelRegistry


def write_report(
    registry: ModelRegistry = None,
    alpha_factory: AlphaFactoryGovernance = None,
    calibration_governance: AutoCalibrationGovernance = None,
    lifecycle_governance: ModelLifecycleGovernance = None,
    sample_calibration_metrics: dict = None,
    sample_candidate_metrics: dict = None,
) -> dict:
    """Write the model lifecycle report.

    All inputs are optional. If not provided, fresh empty instances are used.
    Never imports MetaTrader5. Never sends orders. Never retrains models.
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).isoformat()

    registry = registry or ModelRegistry()
    alpha_factory = alpha_factory or AlphaFactoryGovernance()
    calibration_governance = calibration_governance or AutoCalibrationGovernance()
    lifecycle_governance = lifecycle_governance or ModelLifecycleGovernance()

    # Run a calibration evaluation on provided metrics (or empty)
    cal_metrics = sample_calibration_metrics or {
        "sample_count": 0,
        "brier_score": None,
        "expected_calibration_error": None,
        "current_threshold": 0.5,
    }
    cal_result = calibration_governance.evaluate_calibration(cal_metrics)

    # Run a candidate evaluation on provided metrics (or empty)
    cand_metrics = sample_candidate_metrics or {}
    champion_metrics = None
    champion = registry.get_champion()
    if champion is not None:
        champion_metrics = champion.metrics
    lifecycle_decision = lifecycle_governance.evaluate_candidate(
        cand_metrics, champion_metrics, model_id="report_candidate"
    )

    # Aggregate blockers / manual approvals
    blocked_promotions: list[dict] = []
    manual_approval_required: list[dict] = []

    if lifecycle_decision.approval_status == ModelApprovalStatus.BLOCKED:
        blocked_promotions.append({
            "model_id": lifecycle_decision.model_id,
            "blockers": lifecycle_decision.blockers,
        })
    if lifecycle_decision.operator_approval_required:
        manual_approval_required.append({
            "model_id": lifecycle_decision.model_id,
            "proposed_stage": lifecycle_decision.proposed_stage.value,
            "reason": "Champion promotion requires operator approval",
        })

    if cal_result.action.value == "BLOCK_CALIBRATION":
        blocked_promotions.append({
            "model_id": "calibration",
            "blockers": cal_result.blockers,
        })

    # Determine final verdict
    has_blockers = len(blocked_promotions) > 0 or lifecycle_decision.approval_status == ModelApprovalStatus.BLOCKED
    has_warnings = (
        len(lifecycle_decision.warnings) > 0
        or len(cal_result.warnings) > 0
        or cal_result.action.value == "NEEDS_REVIEW"
    )
    if has_blockers:
        verdict = "MODEL_LIFECYCLE_BLOCKED"
    elif has_warnings:
        verdict = "MODEL_LIFECYCLE_WARNINGS"
    else:
        verdict = "MODEL_LIFECYCLE_READY"

    report = {
        "timestamp_utc": ts,
        "verdict": verdict,
        "champion": champion.to_dict() if champion else None,
        "candidates": [m.to_dict() for m in registry.list_candidates()],
        "challengers": [m.to_dict() for m in registry.list_challengers()],
        "calibration_governance": cal_result.to_dict(),
        "alpha_factory_governance": alpha_factory.summary(),
        "lifecycle_governance": lifecycle_governance.decision_summary(),
        "blocked_promotions": blocked_promotions,
        "manual_approval_required": manual_approval_required,
        "safety": {
            "auto_promotion_allowed": False,
            "calibration_auto_apply": False,
            "metatrader5_imported": False,
            "orders_sent": 0,
            "models_retrained": 0,
            "champion_replaced": False,
            "live_trading_enabled": False,
        },
        "general_warnings": [
            "Model lifecycle governance never auto-promotes a candidate to champion.",
            "Calibration recommendations are non-binding - operator must explicitly apply.",
            "Alpha factory may register candidates only - it cannot deploy, replace champion, or trade.",
            "Registry stores metadata only - it never loads pickle or model binaries.",
            "No retraining, no HPO, no backtest optimization occurs in this report.",
        ],
    }

    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str, ensure_ascii=False)

    with open(MD_PATH, "w", encoding="utf-8") as f:
        f.write("# TITAN XAU AI - Model Lifecycle Report\n\n")
        f.write(f"**Generated:** {ts}\n\n")
        f.write(f"**Verdict:** {verdict}\n\n")
        f.write("## Champion\n\n")
        if champion:
            f.write(f"- **Model ID:** {champion.model_id}\n")
            f.write(f"- **Version:** {champion.version}\n")
            f.write(f"- **Approved By:** {champion.approved_by or '(unapproved)'}\n")
            f.write(f"- **Approval Status:** {champion.approval_status.value}\n")
        else:
            f.write("- (no champion registered)\n")
        f.write("\n## Candidates\n\n")
        if report["candidates"]:
            f.write("| Model ID | Version | Approval Status |\n|---|---|---|\n")
            for c in report["candidates"]:
                f.write(f"| {c['model_id']} | {c['version']} | {c['approval_status']} |\n")
        else:
            f.write("- (no candidates registered)\n")
        f.write("\n## Challengers\n\n")
        if report["challengers"]:
            f.write("| Model ID | Version | Approved By |\n|---|---|---|\n")
            for c in report["challengers"]:
                f.write(f"| {c['model_id']} | {c['version']} | {c['approved_by']} |\n")
        else:
            f.write("- (no challengers registered)\n")
        f.write("\n## Calibration Governance\n\n")
        f.write(f"- **Action:** {cal_result.action.value}\n")
        f.write(f"- **Apply Automatically:** {cal_result.apply_automatically}\n")
        f.write(f"- **Sample Count:** {cal_result.sample_count}\n")
        f.write(f"- **Brier Score:** {cal_result.brier_score}\n")
        f.write(f"- **ECE:** {cal_result.expected_calibration_error}\n")
        if cal_result.blockers:
            f.write("\n### Calibration Blockers\n\n")
            for b in cal_result.blockers:
                f.write(f"- **{b}**\n")
        if cal_result.warnings:
            f.write("\n### Calibration Warnings\n\n")
            for w in cal_result.warnings:
                f.write(f"- {w}\n")
        f.write("\n## Alpha Factory Governance\n\n")
        af = report["alpha_factory_governance"]
        f.write(f"- **Total Candidates:** {af['total_candidates']}\n")
        f.write(f"- **Ready For Shadow:** {af['ready_for_shadow']}\n")
        f.write(f"- **Quarantined:** {af['quarantined']}\n")
        f.write(f"- **Can Promote To Champion:** {af['can_promote_to_champion']}\n")
        f.write("\n## Lifecycle Governance\n\n")
        lg = report["lifecycle_governance"]
        f.write(f"- **Verdict:** {lg.get('verdict', 'N/A')}\n")
        f.write(f"- **Operator Approval Required:** {lg.get('operator_approval_required', True)}\n")
        f.write(f"- **Blocker Count:** {lg.get('blocker_count', 0)}\n")
        f.write(f"- **Warning Count:** {lg.get('warning_count', 0)}\n")
        f.write(f"- **Auto Promotion:** {lg.get('auto_promotion', False)}\n")
        if report["blocked_promotions"]:
            f.write("\n## Blocked Promotions\n\n")
            for bp in report["blocked_promotions"]:
                f.write(f"- **{bp['model_id']}**\n")
                for b in bp["blockers"]:
                    f.write(f"  - {b}\n")
        if report["manual_approval_required"]:
            f.write("\n## Manual Approval Required\n\n")
            for ma in report["manual_approval_required"]:
                f.write(f"- **{ma['model_id']}** -> {ma['proposed_stage']}: {ma['reason']}\n")
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
    print("  TITAN XAU AI - Model Lifecycle Report (Sprint 9.9.3.36)")
    print("=" * 70)
    result = write_report()
    print(f"\n  Verdict: {result['verdict']}")
    print(f"\n  JSON: {result['json_path']}")
    print(f"  MD:   {result['md_path']}")
    print("\n" + "=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
