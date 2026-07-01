"""TITAN XAU AI - Sprint 9.9.3.46 Retraining Orchestrator Tests"""
from __future__ import annotations

import inspect
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from titan.production.retraining_orchestrator import (
    CandidateTrainingPlaceholder,
    ChampionCandidateComparison,
    DriftDetectionInput,
    RetrainingOrchestrator,
    RetrainingOrchestratorResult,
    RetrainingOrchestratorStatus,
    SAFETY_INVARIANTS,
)


class TestStatuses:
    def test_01_all_required_statuses_present(self):
        statuses = [s.value for s in RetrainingOrchestratorStatus]
        for s in [
            "DRIFT_DETECTED",
            "TRAINING_STARTED",
            "VALIDATION_PENDING",
            "SHADOW_MODE",
            "APPROVED_FOR_DEMO",
            "PROMOTION_PENDING_HUMAN",
            "REJECTED",
        ]:
            assert s in statuses, f"Missing status: {s}"


class TestDriftDetectionInput:
    def test_02_drift_detected_creates_run(self):
        orch = RetrainingOrchestrator()
        drift = DriftDetectionInput(
            drift_detected=True,
            drift_severity="CRITICAL",
            drift_reason="sharpe drop 30%",
            champion_model_id="champ-1",
        )
        result = orch.ingest_drift("run-1", drift)
        assert result.status == RetrainingOrchestratorStatus.DRIFT_DETECTED
        assert result.champion_model_id == "champ-1"
        assert result.run_id == "run-1"

    def test_03_no_drift_rejects_run(self):
        orch = RetrainingOrchestrator()
        drift = DriftDetectionInput(
            drift_detected=False,
            champion_model_id="champ-1",
        )
        result = orch.ingest_drift("run-2", drift)
        assert result.status == RetrainingOrchestratorStatus.REJECTED
        assert any("drift_detected is False" in b for b in result.blockers)


class TestTrainingPlaceholder:
    def test_04_training_placeholder_advances_to_training_started(self):
        orch = RetrainingOrchestrator()
        orch.ingest_drift(
            "run-3",
            DriftDetectionInput(
                drift_detected=True,
                champion_model_id="champ-1",
            ),
        )
        placeholder = CandidateTrainingPlaceholder(
            candidate_model_id="cand-1",
            champion_model_id="champ-1",
            training_job_id="job-1",
        )
        result = orch.start_training_placeholder("run-3", placeholder)
        assert result.status == RetrainingOrchestratorStatus.TRAINING_STARTED
        assert result.candidate_model_id == "cand-1"

    def test_05_training_executed_true_blocks_placeholder(self):
        """The orchestrator must reject placeholders that claim training ran."""
        orch = RetrainingOrchestrator()
        orch.ingest_drift(
            "run-4",
            DriftDetectionInput(drift_detected=True, champion_model_id="champ-1"),
        )
        placeholder = CandidateTrainingPlaceholder(
            candidate_model_id="cand-1",
            champion_model_id="champ-1",
        )
        # Bypass __post_init__ to force training_executed=True
        object.__setattr__(placeholder, "training_executed", True)
        result = orch.start_training_placeholder("run-4", placeholder)
        assert result.status == RetrainingOrchestratorStatus.REJECTED
        assert any("training_executed=True is forbidden" in b for b in result.blockers)


class TestValidationGate:
    def test_06_validation_gate_passes_to_validation_pending(self):
        orch = RetrainingOrchestrator()
        orch.ingest_drift(
            "run-5",
            DriftDetectionInput(drift_detected=True, champion_model_id="champ-1"),
        )
        orch.start_training_placeholder(
            "run-5",
            CandidateTrainingPlaceholder(
                candidate_model_id="cand-1",
                champion_model_id="champ-1",
            ),
        )
        candidate_metrics = {
            "walk_forward_sharpe": 1.5,
            "walk_forward_status": "PASS",
            "broker_split_status": "PASS",
            "cost_adjusted_net_profit": 100.0,
            "shadow_status": "PASS",
            "shadow_hours": 200,
            "oos_sharpe": 2.0,
            "oos_max_drawdown": 0.05,
        }
        champion_metrics = {
            "oos_sharpe": 1.5,
            "oos_max_drawdown": 0.07,
            "cost_adjusted_net_profit": 50.0,
        }
        result = orch.run_validation_gate("run-5", candidate_metrics, champion_metrics)
        assert result.status == RetrainingOrchestratorStatus.VALIDATION_PENDING
        assert len(result.blockers) == 0

    def test_07_validation_gate_blocks_on_failed_walk_forward(self):
        orch = RetrainingOrchestrator()
        orch.ingest_drift(
            "run-6",
            DriftDetectionInput(drift_detected=True, champion_model_id="champ-1"),
        )
        orch.start_training_placeholder(
            "run-6",
            CandidateTrainingPlaceholder(
                candidate_model_id="cand-1",
                champion_model_id="champ-1",
            ),
        )
        candidate_metrics = {
            "walk_forward_sharpe": -0.2,  # negative
            "walk_forward_status": "FAIL",
            "broker_split_status": "PASS",
            "cost_adjusted_net_profit": 100.0,
            "shadow_status": "PASS",
            "shadow_hours": 200,
        }
        result = orch.run_validation_gate("run-6", candidate_metrics)
        assert result.status == RetrainingOrchestratorStatus.REJECTED
        assert any("walk_forward" in b.lower() for b in result.blockers)

    def test_08_validation_gate_blocks_on_failed_broker_split(self):
        orch = RetrainingOrchestrator()
        orch.ingest_drift(
            "run-7",
            DriftDetectionInput(drift_detected=True, champion_model_id="champ-1"),
        )
        orch.start_training_placeholder(
            "run-7",
            CandidateTrainingPlaceholder(
                candidate_model_id="cand-1",
                champion_model_id="champ-1",
            ),
        )
        candidate_metrics = {
            "walk_forward_sharpe": 1.5,
            "walk_forward_status": "PASS",
            "broker_split_status": "FAIL",
            "cost_adjusted_net_profit": 100.0,
            "shadow_status": "PASS",
            "shadow_hours": 200,
        }
        result = orch.run_validation_gate("run-7", candidate_metrics)
        assert result.status == RetrainingOrchestratorStatus.REJECTED
        assert any("broker_split" in b.lower() for b in result.blockers)

    def test_09_validation_gate_blocks_on_negative_cost_adjusted(self):
        orch = RetrainingOrchestrator()
        orch.ingest_drift(
            "run-8",
            DriftDetectionInput(drift_detected=True, champion_model_id="champ-1"),
        )
        orch.start_training_placeholder(
            "run-8",
            CandidateTrainingPlaceholder(
                candidate_model_id="cand-1",
                champion_model_id="champ-1",
            ),
        )
        candidate_metrics = {
            "walk_forward_sharpe": 1.5,
            "walk_forward_status": "PASS",
            "broker_split_status": "PASS",
            "cost_adjusted_net_profit": -50.0,  # negative
            "shadow_status": "PASS",
            "shadow_hours": 200,
        }
        result = orch.run_validation_gate("run-8", candidate_metrics)
        assert result.status == RetrainingOrchestratorStatus.REJECTED
        assert any("cost_adjusted" in b.lower() for b in result.blockers)


class TestShadowMode:
    def test_10_shadow_mode_requires_min_hours(self):
        orch = RetrainingOrchestrator()
        orch.ingest_drift(
            "run-9",
            DriftDetectionInput(drift_detected=True, champion_model_id="champ-1"),
        )
        orch.start_training_placeholder(
            "run-9",
            CandidateTrainingPlaceholder(
                candidate_model_id="cand-1",
                champion_model_id="champ-1",
            ),
        )
        orch.run_validation_gate(
            "run-9",
            {
                "walk_forward_sharpe": 1.5,
                "walk_forward_status": "PASS",
                "broker_split_status": "PASS",
                "cost_adjusted_net_profit": 100.0,
                "shadow_status": "PASS",
                "shadow_hours": 200,
                "oos_sharpe": 2.0,
                "oos_max_drawdown": 0.05,
            },
            {
                "oos_sharpe": 1.5,
                "oos_max_drawdown": 0.07,
                "cost_adjusted_net_profit": 50.0,
            },
        )
        # Insufficient hours
        result = orch.enter_shadow_mode(
            "run-9", {"shadow_status": "PASS", "shadow_hours": 100}
        )
        assert result.status == RetrainingOrchestratorStatus.REJECTED
        assert any("shadow_hours" in b for b in result.blockers)


class TestCeoApprovalGate:
    def test_11_approve_for_demo_requires_ceo_approval(self):
        orch = RetrainingOrchestrator()
        orch.ingest_drift(
            "run-10",
            DriftDetectionInput(drift_detected=True, champion_model_id="champ-1"),
        )
        orch.start_training_placeholder(
            "run-10",
            CandidateTrainingPlaceholder(
                candidate_model_id="cand-1",
                champion_model_id="champ-1",
            ),
        )
        orch.run_validation_gate(
            "run-10",
            {
                "walk_forward_sharpe": 1.5,
                "walk_forward_status": "PASS",
                "broker_split_status": "PASS",
                "cost_adjusted_net_profit": 100.0,
                "shadow_status": "PASS",
                "shadow_hours": 200,
                "oos_sharpe": 2.0,
                "oos_max_drawdown": 0.05,
            },
            {
                "oos_sharpe": 1.5,
                "oos_max_drawdown": 0.07,
                "cost_adjusted_net_profit": 50.0,
            },
        )
        orch.enter_shadow_mode(
            "run-10", {"shadow_status": "PASS", "shadow_hours": 200}
        )
        # Without CEO approval
        result = orch.approve_for_demo("run-10", ceo_approval=False, approver="")
        assert result.status == RetrainingOrchestratorStatus.REJECTED
        assert any("CEO approval required" in b for b in result.blockers)

    def test_12_approve_for_demo_with_ceo_approval(self):
        orch = RetrainingOrchestrator()
        orch.ingest_drift(
            "run-11",
            DriftDetectionInput(drift_detected=True, champion_model_id="champ-1"),
        )
        orch.start_training_placeholder(
            "run-11",
            CandidateTrainingPlaceholder(
                candidate_model_id="cand-1",
                champion_model_id="champ-1",
            ),
        )
        orch.run_validation_gate(
            "run-11",
            {
                "walk_forward_sharpe": 1.5,
                "walk_forward_status": "PASS",
                "broker_split_status": "PASS",
                "cost_adjusted_net_profit": 100.0,
                "shadow_status": "PASS",
                "shadow_hours": 200,
                "oos_sharpe": 2.0,
                "oos_max_drawdown": 0.05,
            },
            {
                "oos_sharpe": 1.5,
                "oos_max_drawdown": 0.07,
                "cost_adjusted_net_profit": 50.0,
            },
        )
        orch.enter_shadow_mode(
            "run-11", {"shadow_status": "PASS", "shadow_hours": 200}
        )
        result = orch.approve_for_demo(
            "run-11", ceo_approval=True, approver="ceo@example.com"
        )
        assert result.status == RetrainingOrchestratorStatus.APPROVED_FOR_DEMO


class TestHumanPromotionGate:
    def test_13_request_human_promotion_is_terminal(self):
        """The orchestrator must end at PROMOTION_PENDING_HUMAN, not promote."""
        orch = RetrainingOrchestrator()
        orch.ingest_drift(
            "run-12",
            DriftDetectionInput(drift_detected=True, champion_model_id="champ-1"),
        )
        orch.start_training_placeholder(
            "run-12",
            CandidateTrainingPlaceholder(
                candidate_model_id="cand-1",
                champion_model_id="champ-1",
            ),
        )
        orch.run_validation_gate(
            "run-12",
            {
                "walk_forward_sharpe": 1.5,
                "walk_forward_status": "PASS",
                "broker_split_status": "PASS",
                "cost_adjusted_net_profit": 100.0,
                "shadow_status": "PASS",
                "shadow_hours": 200,
                "oos_sharpe": 2.0,
                "oos_max_drawdown": 0.05,
            },
            {
                "oos_sharpe": 1.5,
                "oos_max_drawdown": 0.07,
                "cost_adjusted_net_profit": 50.0,
            },
        )
        orch.enter_shadow_mode(
            "run-12", {"shadow_status": "PASS", "shadow_hours": 200}
        )
        orch.approve_for_demo(
            "run-12", ceo_approval=True, approver="ceo@example.com"
        )
        result = orch.request_human_promotion("run-12")
        assert result.status == RetrainingOrchestratorStatus.PROMOTION_PENDING_HUMAN
        assert result.auto_promote_to_live is False
        assert result.human_approval_required is True


class TestNoAutoPromotion:
    def test_14_enforce_no_auto_promotion_returns_false(self):
        orch = RetrainingOrchestrator()
        assert orch.enforce_no_auto_promotion_to_live() is False

    def test_15_summary_has_no_auto_promote(self):
        orch = RetrainingOrchestrator()
        s = orch.summary()
        assert s["auto_promote_to_live"] is False
        assert s["human_approval_required"] is True


class TestChampionCandidateComparison:
    def test_16_candidate_better_when_sharpe_up_and_drawdown_no_worse(self):
        orch = RetrainingOrchestrator()
        comparison = orch.compare_champion_vs_candidate(
            {
                "oos_sharpe": 2.0,
                "oos_max_drawdown": 0.05,  # same as champion
                "cost_adjusted_net_profit": 100.0,  # better than champion
            },
            {
                "oos_sharpe": 1.5,
                "oos_max_drawdown": 0.05,
                "cost_adjusted_net_profit": 50.0,
            },
        )
        assert comparison.candidate_better is True

    def test_17_candidate_not_better_when_drawdown_worse(self):
        orch = RetrainingOrchestrator()
        comparison = orch.compare_champion_vs_candidate(
            {
                "oos_sharpe": 2.5,  # much better
                "oos_max_drawdown": 0.15,  # much worse
                "cost_adjusted_net_profit": 100.0,
            },
            {
                "oos_sharpe": 1.5,
                "oos_max_drawdown": 0.05,
                "cost_adjusted_net_profit": 50.0,
            },
        )
        assert comparison.candidate_better is False


class TestSafetyInvariants:
    def test_18_no_metatrader5_import(self):
        from titan.production import retraining_orchestrator
        src = inspect.getsource(retraining_orchestrator)
        assert "import MetaTrader5" not in src
        assert "from MetaTrader5" not in src

    def test_19_no_order_send_calls(self):
        from titan.production import retraining_orchestrator
        src = inspect.getsource(retraining_orchestrator)
        call_pattern = r"(?<!['\"#])\b(mt5\.order_send|adapter\.send_open_order|adapter\.send_order|send_close_order)\s*\("
        matches = re.findall(call_pattern, src)
        assert len(matches) == 0, f"Found execution calls: {matches}"

    def test_20_no_training_execution(self):
        from titan.production import retraining_orchestrator
        src_raw = inspect.getsource(retraining_orchestrator)
        src = re.sub(r'"""[\s\S]*?"""', '""', src_raw)
        src = re.sub(r"'''[\s\S]*?'''", "''", src)
        call_pattern = r"\b(\w+\.fit|train_model|retrain|run_hpo)\s*\("
        matches = re.findall(call_pattern, src)
        assert len(matches) == 0, f"Found training calls: {matches}"

    def test_21_no_forbidden_patterns(self):
        from titan.production import retraining_orchestrator
        src_raw = inspect.getsource(retraining_orchestrator)
        src = re.sub(r'"""[\s\S]*?"""', '""', src_raw)
        src = re.sub(r"'''[\s\S]*?'''", "''", src)
        src = re.sub(r'"(?:[^"\\]|\\.)*"', '""', src)
        src = re.sub(r"'(?:[^'\\]|\\.)*'", "''", src)
        low = src.lower()
        # Allow the safety flag literal names by removing them
        low = low.replace("no_martingale", "").replace("no_grid", "")
        low = low.replace("no_averaging", "").replace("no_loss_based_lot_multiplier", "")
        forbidden = [
            "martingale",
            "grid_trade",
            "averaging_down",
            "double_lot",
            "add_position",
            "loss_based_lot_multiplier",
            "recovery_multiplier",
        ]
        found = [t for t in forbidden if t in low]
        assert found == [], f"Forbidden patterns found: {found}"

    def test_22_safety_invariants_constant(self):
        assert SAFETY_INVARIANTS["no_martingale"] is True
        assert SAFETY_INVARIANTS["no_grid"] is True
        assert SAFETY_INVARIANTS["no_averaging"] is True
        assert SAFETY_INVARIANTS["auto_promote_to_live"] is False

    def test_23_result_has_safety_fields(self):
        r = RetrainingOrchestratorResult(
            run_id="x",
            status=RetrainingOrchestratorStatus.DRIFT_DETECTED,
        )
        assert r.no_martingale is True
        assert r.no_grid is True
        assert r.no_averaging is True
        assert r.auto_promote_to_live is False
        assert r.human_approval_required is True
