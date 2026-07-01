#!/usr/bin/env python3
"""
TITAN XAU AI - Retraining Readiness Audit (Sprint 9.9.3.46)
============================================================

Static readiness audit for the retraining orchestrator and model
promotion gate. Verifies that both modules exist and have the correct
safety invariants.

NEVER imports MetaTrader5. NEVER sends orders. Pure static / source
audit.

Verdicts:
    - RETRAINING_READY       : all checks pass
    - RETRAINING_NEEDS_WORK  : warnings only
    - RETRAINING_BLOCKED     : one or more blockers

Writes report to:
    data/audit/demo_micro_execution/retraining_readiness_audit.json
"""
from __future__ import annotations

import argparse
import inspect
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
OUTPUT_DIR = REPO_ROOT / "data" / "audit" / "demo_micro_execution"


def _strip(src: str) -> str:
    src = re.sub(r'"""[\s\S]*?"""', '""', src)
    src = re.sub(r"'''[\s\S]*?'''", "''", src)
    src = re.sub(r'"(?:[^"\\]|\\.)*"', '""', src)
    src = re.sub(r"'(?:[^'\\]|\\.)*'", "''", src)
    return src


def run_audit() -> dict:
    ts = datetime.now(timezone.utc).isoformat()
    ok_checks: list[str] = []
    blockers: list[str] = []
    warnings: list[str] = []
    findings: dict = {}

    # ──────────────────────────────────────────────────────────────────
    # 1. Modules exist
    # ──────────────────────────────────────────────────────────────────
    try:
        from titan.production.retraining_orchestrator import (
            RetrainingOrchestrator,
            RetrainingOrchestratorStatus,
            RetrainingOrchestratorResult,
            DriftDetectionInput,
            CandidateTrainingPlaceholder,
        )
        ok_checks.append("RetrainingOrchestrator module imports cleanly")
        findings["orchestrator_imports"] = True
    except Exception as e:  # pragma: no cover - audit-time only
        blockers.append(f"RetrainingOrchestrator import failed: {e}")
        findings["orchestrator_imports"] = False

    try:
        from titan.production.model_promotion_gate import (
            ModelPromotionGate,
            PromotionResult,
        )
        ok_checks.append("ModelPromotionGate module imports cleanly")
        findings["promotion_gate_imports"] = True
    except Exception as e:  # pragma: no cover - audit-time only
        blockers.append(f"ModelPromotionGate import failed: {e}")
        findings["promotion_gate_imports"] = False

    # ──────────────────────────────────────────────────────────────────
    # 2. Statuses present
    # ──────────────────────────────────────────────────────────────────
    required_statuses = [
        "DRIFT_DETECTED",
        "TRAINING_STARTED",
        "VALIDATION_PENDING",
        "SHADOW_MODE",
        "APPROVED_FOR_DEMO",
        "PROMOTION_PENDING_HUMAN",
        "REJECTED",
    ]
    try:
        statuses = [s.value for s in RetrainingOrchestratorStatus]
        missing = [s for s in required_statuses if s not in statuses]
        if not missing:
            ok_checks.append("All required orchestrator statuses present")
            findings["statuses_present"] = True
        else:
            blockers.append(f"Missing orchestrator statuses: {missing}")
            findings["statuses_present"] = False
    except Exception as e:
        blockers.append(f"Could not enumerate statuses: {e}")
        findings["statuses_present"] = False

    # ──────────────────────────────────────────────────────────────────
    # 3. Safety invariants in source
    # ──────────────────────────────────────────────────────────────────
    orchestrator_path = REPO_ROOT / "titan" / "production" / "retraining_orchestrator.py"
    promotion_path = REPO_ROOT / "titan" / "production" / "model_promotion_gate.py"

    if orchestrator_path.exists():
        orch_src = orchestrator_path.read_text(encoding="utf-8")
        # No MetaTrader5 import (check raw source)
        if "import MetaTrader5" not in orch_src and "from MetaTrader5" not in orch_src:
            ok_checks.append("RetrainingOrchestrator: no MetaTrader5 import")
            findings["orchestrator_no_mt5"] = True
        else:
            blockers.append("RetrainingOrchestrator: MetaTrader5 import found")
            findings["orchestrator_no_mt5"] = False
        # No order_send - check stripped code (ignore docstring/string mentions)
        orch_code_stripped = _strip(orch_src)
        # Use regex to find actual call sites of mt5.order_send( or adapter.send_*_order(
        order_send_pattern = r"(?<!['\"#])\b(mt5\.order_send|adapter\.send_open_order|adapter\.send_order|send_close_order)\s*\("
        order_send_matches = re.findall(order_send_pattern, orch_code_stripped)
        if not order_send_matches:
            ok_checks.append("RetrainingOrchestrator: no order_send calls")
            findings["orchestrator_no_order_send"] = True
        else:
            blockers.append(
                f"RetrainingOrchestrator: order_send call found: {order_send_matches}"
            )
            findings["orchestrator_no_order_send"] = False
        # Safety invariant fields present
        safety_required = [
            "no_martingale",
            "no_grid",
            "no_averaging",
            "auto_promote_to_live",
        ]
        missing_safety = [s for s in safety_required if s not in orch_src]
        if not missing_safety:
            ok_checks.append("RetrainingOrchestrator: safety invariant fields present")
            findings["orchestrator_safety_fields"] = True
        else:
            blockers.append(
                f"RetrainingOrchestrator: missing safety fields: {missing_safety}"
            )
            findings["orchestrator_safety_fields"] = False
        # No martingale/grid/averaging/loss_based_lot_multiplier in stripped code
        orch_code = _strip(orch_src).lower()
        forbidden = [
            "martingale",
            "grid_trade",
            "averaging_down",
            "double_lot",
            "add_position",
            "loss_based_lot_multiplier",
            "recovery_multiplier",
        ]
        # Allow the literal safety flag names (no_martingale etc.)
        # by removing them from the check text
        check_text = orch_code.replace("no_martingale", "").replace("no_grid", "")
        check_text = check_text.replace("no_averaging", "").replace(
            "no_loss_based_lot_multiplier", ""
        )
        found_forbidden = [t for t in forbidden if t in check_text]
        if not found_forbidden:
            ok_checks.append(
                "RetrainingOrchestrator: no martingale/grid/averaging/loss_based_lot"
            )
            findings["orchestrator_no_forbidden_patterns"] = True
        else:
            blockers.append(
                f"RetrainingOrchestrator: forbidden patterns: {found_forbidden}"
            )
            findings["orchestrator_no_forbidden_patterns"] = False
        # No training execution
        training_calls = re.findall(
            r"\b(\w+\.fit|train_model|retrain|run_hpo)\s*\(", orch_src
        )
        if not training_calls:
            ok_checks.append("RetrainingOrchestrator: no model training calls")
            findings["orchestrator_no_training"] = True
        else:
            blockers.append(
                f"RetrainingOrchestrator: training calls found: {training_calls}"
            )
            findings["orchestrator_no_training"] = False
        # enforce_no_auto_promotion_to_live returns False
        if "enforce_no_auto_promotion_to_live" in orch_src and "return False" in orch_src:
            ok_checks.append(
                "RetrainingOrchestrator: enforce_no_auto_promotion_to_live present"
            )
            findings["orchestrator_no_auto_promotion_helper"] = True
        else:
            blockers.append(
                "RetrainingOrchestrator: enforce_no_auto_promotion_to_live missing"
            )
            findings["orchestrator_no_auto_promotion_helper"] = False
    else:
        blockers.append(f"RetrainingOrchestrator source not found: {orchestrator_path}")

    # ──────────────────────────────────────────────────────────────────
    # 4. Promotion gate invariants
    # ──────────────────────────────────────────────────────────────────
    if promotion_path.exists():
        gate_src = promotion_path.read_text(encoding="utf-8")
        if "import MetaTrader5" not in gate_src and "from MetaTrader5" not in gate_src:
            ok_checks.append("ModelPromotionGate: no MetaTrader5 import")
            findings["gate_no_mt5"] = True
        else:
            blockers.append("ModelPromotionGate: MetaTrader5 import found")
            findings["gate_no_mt5"] = False
        # No order_send - check stripped code
        gate_code_stripped = _strip(gate_src)
        gate_order_send_matches = re.findall(order_send_pattern, gate_code_stripped)
        if not gate_order_send_matches:
            ok_checks.append("ModelPromotionGate: no order_send calls")
            findings["gate_no_order_send"] = True
        else:
            blockers.append(
                f"ModelPromotionGate: order_send call found: {gate_order_send_matches}"
            )
            findings["gate_no_order_send"] = False
        # validate_promotion signature requires human_approval
        if "human_approval: bool = False" in gate_src or "human_approval=False" in gate_src:
            ok_checks.append("ModelPromotionGate: human_approval parameter defaults False")
            findings["gate_human_approval_default"] = True
        else:
            blockers.append(
                "ModelPromotionGate: human_approval default-False missing"
            )
            findings["gate_human_approval_default"] = False
        # Hard post_init block on approved without human_approval
        if (
            "if self.approved and not self.human_approval" in gate_src
            and "self.approved = False" in gate_src
        ):
            ok_checks.append(
                "ModelPromotionGate: hard-block approved without human_approval"
            )
            findings["gate_hard_block_auto_approval"] = True
        else:
            blockers.append(
                "ModelPromotionGate: missing hard-block on auto-approval"
            )
            findings["gate_hard_block_auto_approval"] = False
        # Safety invariants
        gate_safety = ["no_martingale", "no_grid", "no_averaging", "auto_promote_to_live"]
        missing_gate_safety = [s for s in gate_safety if s not in gate_src]
        if not missing_gate_safety:
            ok_checks.append("ModelPromotionGate: safety invariant fields present")
            findings["gate_safety_fields"] = True
        else:
            blockers.append(
                f"ModelPromotionGate: missing safety fields: {missing_gate_safety}"
            )
            findings["gate_safety_fields"] = False
        # No martingale/grid/averaging/loss_based_lot
        gate_code = _strip(gate_src).lower()
        gate_check = gate_code.replace("no_martingale", "").replace("no_grid", "")
        gate_check = gate_check.replace("no_averaging", "").replace(
            "no_loss_based_lot_multiplier", ""
        )
        gate_forbidden = [
            "martingale",
            "grid_trade",
            "averaging_down",
            "double_lot",
            "add_position",
            "loss_based_lot_multiplier",
            "recovery_multiplier",
        ]
        gate_found = [t for t in gate_forbidden if t in gate_check]
        if not gate_found:
            ok_checks.append("ModelPromotionGate: no forbidden patterns")
            findings["gate_no_forbidden_patterns"] = True
        else:
            blockers.append(
                f"ModelPromotionGate: forbidden patterns: {gate_found}"
            )
            findings["gate_no_forbidden_patterns"] = False
    else:
        blockers.append(f"ModelPromotionGate source not found: {promotion_path}")

    # ──────────────────────────────────────────────────────────────────
    # 5. Functional smoke: orchestrator never auto-promotes
    # ──────────────────────────────────────────────────────────────────
    try:
        orch = RetrainingOrchestrator()
        if orch.enforce_no_auto_promotion_to_live() is False:
            ok_checks.append("RetrainingOrchestrator.enforce_no_auto_promotion_to_live == False")
            findings["orchestrator_enforce_returns_false"] = True
        else:
            blockers.append("RetrainingOrchestrator.enforce_no_auto_promotion_to_live != False")
            findings["orchestrator_enforce_returns_false"] = False

        # summary auto_promote_to_live False
        s = orch.summary()
        if s.get("auto_promote_to_live") is False:
            ok_checks.append("RetrainingOrchestrator.summary auto_promote_to_live == False")
            findings["orchestrator_summary_no_auto"] = True
        else:
            blockers.append("RetrainingOrchestrator.summary auto_promote_to_live != False")
            findings["orchestrator_summary_no_auto"] = False
    except Exception as e:
        blockers.append(f"RetrainingOrchestrator functional check failed: {e}")
        findings["orchestrator_functional"] = False

    try:
        gate = ModelPromotionGate()
        # Without human_approval, must not approve even if all checks pass
        result = gate.validate_promotion(
            candidate_model_id="cand-1",
            champion_model_id="champ-1",
            walk_forward_passed=True,
            broker_split_passed=True,
            cost_adjusted_passed=True,
            shadow_mode_completed=True,
            human_approval=False,
        )
        if result.approved is False:
            ok_checks.append(
                "ModelPromotionGate: blocks approval when human_approval=False"
            )
            findings["gate_blocks_without_human_approval"] = True
        else:
            blockers.append(
                "ModelPromotionGate: approved without human_approval - CRITICAL"
            )
            findings["gate_blocks_without_human_approval"] = False
        # With human_approval=True and approver, must approve
        result_ok = gate.validate_promotion(
            candidate_model_id="cand-2",
            champion_model_id="champ-2",
            walk_forward_passed=True,
            broker_split_passed=True,
            cost_adjusted_passed=True,
            shadow_mode_completed=True,
            human_approval=True,
            approver="ceo@example.com",
        )
        if result_ok.approved is True:
            ok_checks.append(
                "ModelPromotionGate: approves when human_approval=True and approver set"
            )
            findings["gate_approves_with_human_approval"] = True
        else:
            blockers.append(
                f"ModelPromotionGate: failed to approve with human_approval=True: {result_ok.blockers}"
            )
            findings["gate_approves_with_human_approval"] = False
        # Even approved result has auto_promote_to_live=False
        if result_ok.auto_promote_to_live is False:
            ok_checks.append(
                "ModelPromotionGate: approved result still has auto_promote_to_live=False"
            )
            findings["gate_approved_result_no_auto"] = True
        else:
            blockers.append(
                "ModelPromotionGate: approved result has auto_promote_to_live=True - CRITICAL"
            )
            findings["gate_approved_result_no_auto"] = False
    except Exception as e:
        blockers.append(f"ModelPromotionGate functional check failed: {e}")
        findings["gate_functional"] = False

    # ──────────────────────────────────────────────────────────────────
    # Verdict
    # ──────────────────────────────────────────────────────────────────
    if blockers:
        verdict = "RETRAINING_BLOCKED"
    elif warnings:
        verdict = "RETRAINING_NEEDS_WORK"
    else:
        verdict = "RETRAINING_READY"

    return {
        "timestamp_utc": ts,
        "verdict": verdict,
        "ok_checks": ok_checks,
        "blockers": blockers,
        "warnings": warnings,
        "findings": findings,
        "safety": {
            "order_send_called": False,
            "position_modified": False,
            "auto_promote_to_live": False,
            "no_martingale": True,
            "no_grid": True,
            "no_averaging": True,
        },
    }


def write_report(result: dict) -> dict:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUTPUT_DIR / "retraining_readiness_audit.json"
    md_path = OUTPUT_DIR / "retraining_readiness_audit.md"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str, ensure_ascii=False)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# TITAN XAU AI - Retraining Readiness Audit\n\n")
        f.write(f"**Verdict:** **{result['verdict']}**\n\n")
        f.write(f"**Timestamp:** {result['timestamp_utc']}\n\n")
        f.write("## Findings\n\n")
        f.write("| Check | Status |\n|---|---|\n")
        for k, v in result.get("findings", {}).items():
            if isinstance(v, bool):
                status = "PASS" if v else "FAIL"
                f.write(f"| {k} | {status} |\n")
        if result.get("ok_checks"):
            f.write("\n## OK Checks\n\n")
            for c in result["ok_checks"]:
                f.write(f"- {c}\n")
        if result.get("blockers"):
            f.write("\n## Blockers\n\n")
            for b in result["blockers"]:
                f.write(f"- **{b}**\n")
        f.write("\n## Safety\n\n")
        f.write("- order_send_called: False\n")
        f.write("- position_modified: False\n")
        f.write("- auto_promote_to_live: False\n")
        f.write("- no_martingale: True\n")
        f.write("- no_grid: True\n")
        f.write("- no_averaging: True\n")
    return {"json_path": str(json_path), "md_path": str(md_path)}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Retraining readiness audit (no MT5, no order_send)"
    )
    parser.parse_args()
    print("=" * 70)
    print("  TITAN XAU AI - Retraining Readiness Audit (Sprint 9.9.3.46)")
    print("=" * 70)
    result = run_audit()
    report = write_report(result)
    print(f"\n  Verdict: {result['verdict']}")
    print(f"  OK checks: {len(result.get('ok_checks', []))}")
    print(f"  Blockers: {len(result.get('blockers', []))}")
    if result.get("blockers"):
        print("\n  Blockers:")
        for b in result["blockers"]:
            print(f"    - {b}")
    print(f"\n  JSON: {report['json_path']}")
    print(f"  MD:   {report['md_path']}")
    print("\n" + "=" * 70)
    return 0 if result["verdict"] == "RETRAINING_READY" else 1


if __name__ == "__main__":
    sys.exit(main())
