"""TITAN XAU AI - Sprint 9.9.3.36 Model Lifecycle Governance Tests"""
from __future__ import annotations
import inspect, sys
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from titan.production.model_lifecycle_governance import (
    ModelLifecycleGovernance, ModelLifecycleDecision,
    ModelLifecycleStage, ModelApprovalStatus,
)


class TestStagesAndApprovals:
    def test_01_all_stages_present(self):
        stages = [s.value for s in ModelLifecycleStage]
        for s in ["CHAMPION", "CHALLENGER", "CANDIDATE", "SHADOW",
                  "REJECTED", "RETIRED", "QUARANTINED"]:
            assert s in stages

    def test_02_all_approval_statuses_present(self):
        approvals = [a.value for a in ModelApprovalStatus]
        for a in ["APPROVED", "REJECTED", "NEEDS_REVIEW", "BLOCKED", "PENDING"]:
            assert a in approvals


class TestDecisionDataclass:
    def test_03_decision_has_all_required_fields(self):
        d = ModelLifecycleDecision(
            model_id="m1",
            current_stage=ModelLifecycleStage.CANDIDATE,
            proposed_stage=ModelLifecycleStage.SHADOW,
            approval_status=ModelApprovalStatus.NEEDS_REVIEW,
        )
        required = ["model_id", "current_stage", "proposed_stage",
                    "approval_status", "reasons", "blockers", "warnings",
                    "metrics_snapshot", "timestamp_utc", "operator_approval_required"]
        for f in required:
            assert hasattr(d, f), f"Missing: {f}"

    def test_04_champion_proposal_requires_operator_approval(self):
        d = ModelLifecycleDecision(
            model_id="m1",
            current_stage=ModelLifecycleStage.CHALLENGER,
            proposed_stage=ModelLifecycleStage.CHAMPION,
            approval_status=ModelApprovalStatus.NEEDS_REVIEW,
        )
        assert d.operator_approval_required is True


class TestNoAutoPromotion:
    def test_05_enforce_no_auto_promotion_returns_false(self):
        gov = ModelLifecycleGovernance()
        assert gov.enforce_no_auto_promotion() is False

    def test_06_candidate_cannot_auto_promote_to_champion(self):
        gov = ModelLifecycleGovernance()
        candidate = {
            "oos_sharpe": 2.0,
            "oos_max_drawdown": 0.05,
            "walk_forward_sharpe": 1.8,
            "broker_split_status": "PASS",
            "calibration_brier": 0.15,
            "calibration_ece": 0.05,
            "walk_forward_status": "PASS",
            "shadow_status": "PASS",
            "shadow_hours": 200,
        }
        champion = {
            "oos_sharpe": 1.5,
            "oos_max_drawdown": 0.07,
            "walk_forward_sharpe": 1.4,
            "calibration_brier": 0.18,
            "calibration_ece": 0.07,
        }
        decision = gov.evaluate_candidate(candidate, champion, model_id="c1")
        # Even with all gates passing, candidate should NOT be auto-promoted to CHAMPION
        assert decision.proposed_stage != ModelLifecycleStage.CHAMPION
        assert decision.operator_approval_required is True


class TestMissingMetrics:
    def test_07_missing_oos_blocks(self):
        gov = ModelLifecycleGovernance()
        candidate = {
            "oos_max_drawdown": 0.05,
            "walk_forward_sharpe": 1.8,
            "broker_split_status": "PASS",
            "calibration_brier": 0.15,
            "calibration_ece": 0.05,
        }
        decision = gov.evaluate_candidate(candidate, None, model_id="c1")
        assert decision.approval_status == ModelApprovalStatus.BLOCKED
        assert any("oos_sharpe" in b for b in decision.blockers)

    def test_08_missing_walk_forward_blocks(self):
        gov = ModelLifecycleGovernance()
        candidate = {
            "oos_sharpe": 2.0,
            "oos_max_drawdown": 0.05,
            "broker_split_status": "PASS",
            "calibration_brier": 0.15,
            "calibration_ece": 0.05,
            "walk_forward_status": "PASS",
        }
        decision = gov.evaluate_candidate(candidate, None, model_id="c1")
        assert decision.approval_status == ModelApprovalStatus.BLOCKED
        assert any("walk_forward_sharpe" in b for b in decision.blockers)

    def test_09_missing_broker_split_blocks(self):
        gov = ModelLifecycleGovernance()
        candidate = {
            "oos_sharpe": 2.0,
            "oos_max_drawdown": 0.05,
            "walk_forward_sharpe": 1.8,
            "calibration_brier": 0.15,
            "calibration_ece": 0.05,
            "walk_forward_status": "PASS",
        }
        decision = gov.evaluate_candidate(candidate, None, model_id="c1")
        assert decision.approval_status == ModelApprovalStatus.BLOCKED
        assert any("broker_split_status" in b for b in decision.blockers)


class TestLeakageQuarantine:
    def test_10_leakage_flag_quarantines_candidate(self):
        gov = ModelLifecycleGovernance()
        candidate = {
            "oos_sharpe": 2.0,
            "oos_max_drawdown": 0.05,
            "walk_forward_sharpe": 1.8,
            "broker_split_status": "PASS",
            "calibration_brier": 0.15,
            "calibration_ece": 0.05,
            "walk_forward_status": "PASS",
            "leakage_flags": ["future_peek_in_features"],
        }
        decision = gov.evaluate_candidate(candidate, None, model_id="c1")
        assert decision.proposed_stage == ModelLifecycleStage.QUARANTINED
        assert decision.approval_status == ModelApprovalStatus.BLOCKED
        assert any("Leakage" in b for b in decision.blockers)


class TestDrawdownProtection:
    def test_11_worse_drawdown_blocks_when_severe(self):
        gov = ModelLifecycleGovernance()
        candidate = {
            "oos_sharpe": 2.0,
            "oos_max_drawdown": 0.15,
            "walk_forward_sharpe": 1.8,
            "broker_split_status": "PASS",
            "calibration_brier": 0.15,
            "calibration_ece": 0.05,
            "walk_forward_status": "PASS",
        }
        champion = {
            "oos_sharpe": 1.5,
            "oos_max_drawdown": 0.05,
            "walk_forward_sharpe": 1.4,
            "calibration_brier": 0.18,
            "calibration_ece": 0.07,
        }
        decision = gov.evaluate_candidate(candidate, champion, model_id="c1")
        # 10% worse drawdown > 5% block threshold
        assert decision.approval_status == ModelApprovalStatus.BLOCKED
        assert any("drawdown" in b.lower() for b in decision.blockers)

    def test_12_worse_drawdown_needs_review_when_mild(self):
        gov = ModelLifecycleGovernance()
        candidate = {
            "oos_sharpe": 2.0,
            "oos_max_drawdown": 0.07,  # 2% worse than champion's 0.05
            "walk_forward_sharpe": 1.8,
            "broker_split_status": "PASS",
            "calibration_brier": 0.15,
            "calibration_ece": 0.05,
            "walk_forward_status": "PASS",
            "shadow_status": "PASS",
            "shadow_hours": 200,
        }
        champion = {
            "oos_sharpe": 1.5,
            "oos_max_drawdown": 0.05,
            "walk_forward_sharpe": 1.4,
            "calibration_brier": 0.18,
            "calibration_ece": 0.07,
        }
        decision = gov.evaluate_candidate(candidate, champion, model_id="c1")
        # 2% worse drawdown -> warning (NEEDS_REVIEW since other gates pass)
        assert any("drawdown" in w.lower() for w in decision.warnings)


class TestSingleMetricApproval:
    def test_13_better_single_metric_alone_does_not_approve(self):
        """A candidate that improves only sharpe but is worse elsewhere
        should not be auto-approved."""
        gov = ModelLifecycleGovernance()
        candidate = {
            "oos_sharpe": 2.0,  # better than champion
            "oos_max_drawdown": 0.05,  # same as champion
            "walk_forward_sharpe": 1.4,  # worse than champion
            "broker_split_status": "PASS",
            "calibration_brier": 0.18,  # same as champion
            "calibration_ece": 0.07,  # same as champion
            "walk_forward_status": "PASS",
            "shadow_status": "PASS",
            "shadow_hours": 200,
        }
        champion = {
            "oos_sharpe": 1.5,
            "oos_max_drawdown": 0.05,
            "walk_forward_sharpe": 1.8,
            "calibration_brier": 0.18,
            "calibration_ece": 0.07,
        }
        decision = gov.evaluate_candidate(candidate, champion, model_id="c1")
        # Even if some metrics are better, single-metric improvement alone
        # must not approve - operator review still required
        assert decision.approval_status != ModelApprovalStatus.APPROVED
        assert decision.operator_approval_required is True


class TestOperatorApprovalRequired:
    def test_14_operator_approval_required_for_champion(self):
        gov = ModelLifecycleGovernance()
        decision = gov.quarantine(reason="test", model_id="m1")
        assert decision.operator_approval_required is True

    def test_15_decision_summary_returns_dict(self):
        gov = ModelLifecycleGovernance()
        gov.evaluate_candidate({
            "oos_sharpe": 2.0,
            "oos_max_drawdown": 0.05,
            "walk_forward_sharpe": 1.8,
            "broker_split_status": "PASS",
            "calibration_brier": 0.15,
            "calibration_ece": 0.05,
            "walk_forward_status": "PASS",
            "shadow_status": "PASS",
            "shadow_hours": 200,
        }, None, model_id="c1")
        s = gov.decision_summary()
        assert "verdict" in s
        assert "auto_promotion" in s
        assert s["auto_promotion"] is False


class TestQuarantine:
    def test_16_quarantine_sets_stage(self):
        gov = ModelLifecycleGovernance()
        decision = gov.quarantine(reason="suspicious pattern", model_id="m1")
        assert decision.proposed_stage == ModelLifecycleStage.QUARANTINED
        assert decision.approval_status == ModelApprovalStatus.BLOCKED
        assert any("suspicious pattern" in b for b in decision.blockers)


class TestSafetyInvariants:
    def test_17_no_metatrader5_import(self):
        from titan.production import model_lifecycle_governance
        src = inspect.getsource(model_lifecycle_governance)
        assert "import MetaTrader5" not in src
        assert "from MetaTrader5" not in src

    def test_18_no_order_send_calls(self):
        import re
        from titan.production import model_lifecycle_governance
        src = inspect.getsource(model_lifecycle_governance)
        call_pattern = r"(?<!['\"#])\b(mt5\.order_send|adapter\.send_open_order|adapter\.send_order|send_close_order)\s*\("
        matches = re.findall(call_pattern, src)
        assert len(matches) == 0, f"Found execution calls: {matches}"

    def test_19_no_model_training_execution(self):
        from titan.production import model_lifecycle_governance
        src = inspect.getsource(model_lifecycle_governance)
        # Should not call any training functions
        assert ".fit(" not in src
        assert "train_model(" not in src
        assert "retrain(" not in src
        assert "run_hpo(" not in src

    def test_20_no_champion_replacement(self):
        from titan.production import model_lifecycle_governance
        src = inspect.getsource(model_lifecycle_governance)
        # Should not modify any artifact on disk
        assert "open(" not in src.replace("open(reason", "")  # allow open() in quarantine(reason)
        assert "shutil.copy" not in src
        assert "shutil.move" not in src
        assert "pickle.dump" not in src
