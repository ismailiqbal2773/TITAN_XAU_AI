"""TITAN XAU AI - Sprint 9.9.3.46 Model Promotion Gate Tests"""
from __future__ import annotations

import inspect
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from titan.production.model_promotion_gate import (
    ModelPromotionGate,
    PromotionResult,
    SAFETY_INVARIANTS,
)


class TestPromotionResultDataclass:
    def test_01_result_has_required_fields(self):
        r = PromotionResult(approved=False, reason="test")
        for f in [
            "approved",
            "reason",
            "blockers",
            "warnings",
            "candidate_model_id",
            "champion_model_id",
            "checks",
            "human_approval",
            "auto_promote_to_live",
            "no_martingale",
            "no_grid",
            "no_averaging",
            "no_loss_based_lot_multiplier",
            "timestamp_utc",
        ]:
            assert hasattr(r, f), f"Missing field: {f}"

    def test_02_safety_fields_forced_true(self):
        """Safety fields must always be True regardless of input."""
        # Try to construct with auto_promote_to_live=True
        r = PromotionResult(
            approved=False,
            reason="test",
            auto_promote_to_live=True,
            no_martingale=False,
            no_grid=False,
            no_averaging=False,
        )
        # __post_init__ forces them back
        assert r.auto_promote_to_live is False
        assert r.no_martingale is True
        assert r.no_grid is True
        assert r.no_averaging is True


class TestNoAutoApproval:
    def test_03_enforce_no_auto_promotion_returns_false(self):
        gate = ModelPromotionGate()
        assert gate.enforce_no_auto_promotion_to_live() is False

    def test_04_post_init_blocks_approved_without_human_approval(self):
        """Even if a caller tries approved=True with human_approval=False,
        __post_init__ must flip approved back to False."""
        r = PromotionResult(
            approved=True,
            reason="attempted bypass",
            human_approval=False,
        )
        assert r.approved is False
        assert any("human_approval" in b for b in r.blockers)


class TestValidatePromotionBlocked:
    def test_05_blocks_without_human_approval(self):
        """Even with all checks passing, no human_approval -> blocked."""
        gate = ModelPromotionGate()
        r = gate.validate_promotion(
            candidate_model_id="cand-1",
            champion_model_id="champ-1",
            walk_forward_passed=True,
            broker_split_passed=True,
            cost_adjusted_passed=True,
            shadow_mode_completed=True,
            human_approval=False,
        )
        assert r.approved is False
        assert any("human_approval=False" in b for b in r.blockers)

    def test_06_blocks_when_walk_forward_failed(self):
        gate = ModelPromotionGate()
        r = gate.validate_promotion(
            candidate_model_id="cand-1",
            champion_model_id="champ-1",
            walk_forward_passed=False,
            broker_split_passed=True,
            cost_adjusted_passed=True,
            shadow_mode_completed=True,
            human_approval=True,
            approver="ceo@example.com",
        )
        assert r.approved is False
        assert any("walk_forward" in b.lower() for b in r.blockers)

    def test_07_blocks_when_broker_split_failed(self):
        gate = ModelPromotionGate()
        r = gate.validate_promotion(
            candidate_model_id="cand-1",
            champion_model_id="champ-1",
            walk_forward_passed=True,
            broker_split_passed=False,
            cost_adjusted_passed=True,
            shadow_mode_completed=True,
            human_approval=True,
            approver="ceo@example.com",
        )
        assert r.approved is False
        assert any("broker_split" in b.lower() for b in r.blockers)

    def test_08_blocks_when_cost_adjusted_failed(self):
        gate = ModelPromotionGate()
        r = gate.validate_promotion(
            candidate_model_id="cand-1",
            champion_model_id="champ-1",
            walk_forward_passed=True,
            broker_split_passed=True,
            cost_adjusted_passed=False,
            shadow_mode_completed=True,
            human_approval=True,
            approver="ceo@example.com",
        )
        assert r.approved is False
        assert any("cost_adjusted" in b.lower() for b in r.blockers)

    def test_09_blocks_when_shadow_mode_incomplete(self):
        gate = ModelPromotionGate()
        r = gate.validate_promotion(
            candidate_model_id="cand-1",
            champion_model_id="champ-1",
            walk_forward_passed=True,
            broker_split_passed=True,
            cost_adjusted_passed=True,
            shadow_mode_completed=False,
            human_approval=True,
            approver="ceo@example.com",
        )
        assert r.approved is False
        assert any("shadow_mode" in b.lower() for b in r.blockers)

    def test_10_blocks_when_human_approval_without_approver(self):
        gate = ModelPromotionGate()
        r = gate.validate_promotion(
            candidate_model_id="cand-1",
            champion_model_id="champ-1",
            walk_forward_passed=True,
            broker_split_passed=True,
            cost_adjusted_passed=True,
            shadow_mode_completed=True,
            human_approval=True,
            approver="",  # empty
        )
        assert r.approved is False
        assert any("approver name is empty" in b for b in r.blockers)


class TestValidatePromotionApproved:
    def test_11_approves_with_all_checks_and_human_approval(self):
        gate = ModelPromotionGate()
        r = gate.validate_promotion(
            candidate_model_id="cand-1",
            champion_model_id="champ-1",
            walk_forward_passed=True,
            broker_split_passed=True,
            cost_adjusted_passed=True,
            shadow_mode_completed=True,
            human_approval=True,
            approver="ceo@example.com",
        )
        assert r.approved is True
        assert r.human_approval is True
        # Even approved, auto_promote_to_live remains False
        assert r.auto_promote_to_live is False
        assert r.no_martingale is True
        assert r.no_grid is True
        assert r.no_averaging is True


class TestDistinctIds:
    def test_12_blocks_when_candidate_equals_champion(self):
        gate = ModelPromotionGate()
        r = gate.validate_promotion(
            candidate_model_id="same-id",
            champion_model_id="same-id",
            walk_forward_passed=True,
            broker_split_passed=True,
            cost_adjusted_passed=True,
            shadow_mode_completed=True,
            human_approval=True,
            approver="ceo@example.com",
        )
        assert r.approved is False
        assert any("must differ" in b for b in r.blockers)


class TestSummary:
    def test_13_summary_returns_dict(self):
        gate = ModelPromotionGate()
        gate.validate_promotion(
            candidate_model_id="cand-1",
            champion_model_id="champ-1",
            walk_forward_passed=True,
            broker_split_passed=True,
            cost_adjusted_passed=True,
            shadow_mode_completed=True,
            human_approval=True,
            approver="ceo@example.com",
        )
        s = gate.summary()
        assert s["verdict"] == "APPROVED"
        assert s["approved"] is True
        assert s["auto_promote_to_live"] is False


class TestSafetyInvariants:
    def test_14_no_metatrader5_import(self):
        from titan.production import model_promotion_gate
        src = inspect.getsource(model_promotion_gate)
        assert "import MetaTrader5" not in src
        assert "from MetaTrader5" not in src

    def test_15_no_order_send_calls(self):
        from titan.production import model_promotion_gate
        src = inspect.getsource(model_promotion_gate)
        call_pattern = r"(?<!['\"#])\b(mt5\.order_send|adapter\.send_open_order|adapter\.send_order|send_close_order)\s*\("
        matches = re.findall(call_pattern, src)
        assert len(matches) == 0, f"Found execution calls: {matches}"

    def test_16_no_training_execution(self):
        from titan.production import model_promotion_gate
        src = inspect.getsource(model_promotion_gate)
        assert ".fit(" not in src
        assert "train_model(" not in src
        assert "retrain(" not in src
        assert "run_hpo(" not in src

    def test_17_no_forbidden_patterns(self):
        from titan.production import model_promotion_gate
        src_raw = inspect.getsource(model_promotion_gate)
        src = re.sub(r'"""[\s\S]*?"""', '""', src_raw)
        src = re.sub(r"'''[\s\S]*?'''", "''", src)
        src = re.sub(r'"(?:[^"\\]|\\.)*"', '""', src)
        src = re.sub(r"'(?:[^'\\]|\\.)*'", "''", src)
        low = src.lower()
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

    def test_18_safety_invariants_constant(self):
        assert SAFETY_INVARIANTS["no_martingale"] is True
        assert SAFETY_INVARIANTS["no_grid"] is True
        assert SAFETY_INVARIANTS["no_averaging"] is True
        assert SAFETY_INVARIANTS["auto_promote_to_live"] is False
