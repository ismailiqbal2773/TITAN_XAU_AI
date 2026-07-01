"""
TITAN XAU AI - Alpha Factory test suite
=======================================

Covers:
    1. Candidate generation
    2. Evaluation statuses (all 6)
    3. Leakage guard
    4. Walk-forward requirement
    5. Broker-split requirement
    6. Cost-adjusted validation
    7. No auto-live
    8. Registry persistence
    9. No martingale / grid / averaging
   10. No order_send

NEVER calls mt5.order_send. NEVER imports MetaTrader5.
"""
from __future__ import annotations

import inspect
import json
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from titan.research.alpha_factory.alpha_candidate_generator import (
    AlphaCandidate,
    AlphaCandidateGenerator,
    SAFETY_CONTRACT as CAND_SAFETY,
)
from titan.research.alpha_factory.alpha_evaluator import (
    ALL_STATUSES,
    AlphaEvaluation,
    AlphaEvaluator,
    AlphaStatus,
    EvaluatorThresholds,
    SAFETY_CONTRACT as EV_SAFETY,
)
from titan.research.alpha_factory.alpha_registry import AlphaRegistry


# ──────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────
@pytest.fixture
def fresh_registry(tmp_path: Path) -> AlphaRegistry:
    return AlphaRegistry(path=tmp_path / "alpha_registry.json")


def _make_candidate(name: str = "alpha_test") -> AlphaCandidate:
    return AlphaCandidate(
        name=name,
        description="test alpha",
        formula_type="MOMENTUM",
        parameters={"lookback": 14, "threshold": 0.001},
    )


# ──────────────────────────────────────────────────────────────────────────
# 1. Candidate generation
# ──────────────────────────────────────────────────────────────────────────
class TestCandidateGeneration:
    def test_01_generator_produces_candidates(self):
        gen = AlphaCandidateGenerator()
        cands = gen.generate_candidates()
        assert isinstance(cands, list)
        assert len(cands) >= 1
        for c in cands:
            assert isinstance(c, AlphaCandidate)
            assert c.status == "CANDIDATE"
            assert c.name
            assert c.formula_type
            assert isinstance(c.parameters, dict)

    def test_02_candidate_safety_contract_includes_required_flags(self):
        c = _make_candidate()
        assert c.safety["no_martingale"] is True
        assert c.safety["no_grid"] is True
        assert c.safety["no_averaging"] is True
        assert c.safety.get("no_loss_based_lot_multiplier") is True
        assert c.safety.get("no_auto_live") is True
        assert c.safety.get("no_order_send") is True

    def test_03_candidate_rejects_live_status_at_construction(self):
        with pytest.raises(ValueError):
            AlphaCandidate(
                name="bad",
                description="should fail",
                formula_type="MOMENTUM",
                parameters={},
                status="APPROVED_FOR_LIVE",
            )

    def test_04_register_candidate_only_accepts_candidate_status(self, fresh_registry):
        gen = AlphaCandidateGenerator()
        cands = gen.generate_candidates()
        gen.register_candidate(cands[0], fresh_registry)
        # Manually promote one — should fail registration
        c2 = AlphaCandidate(
            name="promoted_alpha",
            description="x",
            formula_type="MEAN_REVERSION",
            parameters={},
            status="VALIDATED_SHADOW_ONLY",
        )
        with pytest.raises(ValueError):
            fresh_registry.register(c2)


# ──────────────────────────────────────────────────────────────────────────
# 2. Evaluation statuses (all 6)
# ──────────────────────────────────────────────────────────────────────────
class TestEvaluationStatuses:
    def test_05_all_six_statuses_present(self):
        expected = {
            "CANDIDATE",
            "REJECTED_OVERFIT",
            "REJECTED_COST_ADJUSTED",
            "VALIDATED_SHADOW_ONLY",
            "APPROVED_FOR_DEMO",
            "APPROVED_FOR_LIVE_PENDING_HUMAN",
        }
        assert set(ALL_STATUSES) == expected

    def test_06_evaluator_default_status_is_candidate(self):
        ev = AlphaEvaluation(alpha_name="x")
        assert ev.status == AlphaStatus.CANDIDATE

    def test_07_full_promotion_ladder(self):
        """CANDIDATE -> VALIDATED_SHADOW_ONLY -> APPROVED_FOR_DEMO
        -> APPROVED_FOR_LIVE_PENDING_HUMAN (only with explicit call)."""
        ev = AlphaEvaluator()
        cand = _make_candidate("ladder_alpha")

        # Pass all four gates
        evaluation = ev.evaluate(
            cand,
            metrics={
                "walk_forward_score": 0.70,
                "broker_split_score": 0.65,
                "cost_adjusted_score": 0.55,
                "overfit_score": 0.30,
            },
        )
        assert evaluation.status == AlphaStatus.VALIDATED_SHADOW_ONLY

        # Promote to demo
        ev.promote_to_demo(evaluation)
        assert evaluation.status == AlphaStatus.APPROVED_FOR_DEMO

        # Request human approval for live
        ev.request_human_approval_for_live(evaluation)
        assert evaluation.status == AlphaStatus.APPROVED_FOR_LIVE_PENDING_HUMAN


# ──────────────────────────────────────────────────────────────────────────
# 3. Leakage guard
# ──────────────────────────────────────────────────────────────────────────
class TestLeakageGuard:
    def test_08_leakage_flags_rejected_as_overfit(self):
        ev = AlphaEvaluator()
        cand = _make_candidate("leaky")
        evaluation = ev.evaluate(
            cand,
            metrics={
                "walk_forward_score": 0.95,
                "broker_split_score": 0.95,
                "cost_adjusted_score": 0.95,
                "overfit_score": 0.05,
            },
            leakage_flags=["future_peek_in_features"],
        )
        assert evaluation.status == AlphaStatus.REJECTED_OVERFIT
        assert any("leakage" in r.lower() for r in evaluation.rejection_reasons)

    def test_09_no_leakage_passes_leakage_gate(self):
        ev = AlphaEvaluator()
        assert ev.check_leakage_guard([]) is True
        assert ev.check_leakage_guard(["x"]) is False


# ──────────────────────────────────────────────────────────────────────────
# 4. Walk-forward requirement
# ──────────────────────────────────────────────────────────────────────────
class TestWalkForward:
    def test_10_walk_forward_below_threshold_rejected(self):
        ev = AlphaEvaluator()
        cand = _make_candidate("low_wf")
        evaluation = ev.evaluate(
            cand,
            metrics={
                "walk_forward_score": 0.20,  # below default 0.55
                "broker_split_score": 0.90,
                "cost_adjusted_score": 0.90,
                "overfit_score": 0.10,
            },
        )
        assert evaluation.status == AlphaStatus.REJECTED_OVERFIT
        assert any("walk-forward" in r.lower() for r in evaluation.rejection_reasons)

    def test_11_walk_forward_at_threshold_passes_that_gate(self):
        ev = AlphaEvaluator()
        assert ev.check_walk_forward(0.55) is True
        assert ev.check_walk_forward(0.54) is False


# ──────────────────────────────────────────────────────────────────────────
# 5. Broker-split requirement
# ──────────────────────────────────────────────────────────────────────────
class TestBrokerSplit:
    def test_12_broker_split_below_threshold_rejected(self):
        ev = AlphaEvaluator()
        cand = _make_candidate("low_bs")
        evaluation = ev.evaluate(
            cand,
            metrics={
                "walk_forward_score": 0.90,
                "broker_split_score": 0.30,  # below 0.55
                "cost_adjusted_score": 0.90,
                "overfit_score": 0.10,
            },
        )
        assert evaluation.status == AlphaStatus.REJECTED_OVERFIT
        assert any("broker-split" in r.lower() for r in evaluation.rejection_reasons)

    def test_13_broker_split_at_threshold_passes(self):
        ev = AlphaEvaluator()
        assert ev.check_broker_split(0.55) is True
        assert ev.check_broker_split(0.54) is False


# ──────────────────────────────────────────────────────────────────────────
# 6. Cost-adjusted validation
# ──────────────────────────────────────────────────────────────────────────
class TestCostAdjusted:
    def test_14_cost_adjusted_below_threshold_rejected(self):
        ev = AlphaEvaluator()
        cand = _make_candidate("low_ca")
        evaluation = ev.evaluate(
            cand,
            metrics={
                "walk_forward_score": 0.90,
                "broker_split_score": 0.90,
                "cost_adjusted_score": 0.10,  # below 0.40
                "overfit_score": 0.10,
            },
        )
        # Should NOT be REJECTED_OVERFIT — it's a separate rejection path
        assert evaluation.status == AlphaStatus.REJECTED_COST_ADJUSTED
        assert any("cost-adjusted" in r.lower() for r in evaluation.rejection_reasons)

    def test_15_cost_adjusted_at_threshold_passes(self):
        ev = AlphaEvaluator()
        assert ev.check_cost_adjusted(0.40) is True
        assert ev.check_cost_adjusted(0.39) is False


# ──────────────────────────────────────────────────────────────────────────
# 7. No auto-live
# ──────────────────────────────────────────────────────────────────────────
class TestNoAutoLive:
    def test_16_never_auto_approve_live_returns_false(self):
        ev = AlphaEvaluator()
        assert ev.never_auto_approve_live() is False

    def test_17_evaluate_never_returns_live_pending_status(self):
        ev = AlphaEvaluator()
        cand = _make_candidate("no_auto_live")
        # Even with perfect scores, evaluate() must NOT return
        # APPROVED_FOR_LIVE_PENDING_HUMAN directly.
        evaluation = ev.evaluate(
            cand,
            metrics={
                "walk_forward_score": 1.0,
                "broker_split_score": 1.0,
                "cost_adjusted_score": 1.0,
                "overfit_score": 0.0,
            },
        )
        assert evaluation.status != AlphaStatus.APPROVED_FOR_LIVE_PENDING_HUMAN
        assert evaluation.status == AlphaStatus.VALIDATED_SHADOW_ONLY

    def test_18_request_human_approval_requires_demo_status_first(self):
        ev = AlphaEvaluator()
        cand = _make_candidate("skip_ladder")
        # Start with VALIDATED_SHADOW_ONLY
        evaluation = ev.evaluate(
            cand,
            metrics={
                "walk_forward_score": 0.80,
                "broker_split_score": 0.80,
                "cost_adjusted_score": 0.60,
                "overfit_score": 0.20,
            },
        )
        assert evaluation.status == AlphaStatus.VALIDATED_SHADOW_ONLY
        # Try to skip the demo gate — should be rejected
        ev.request_human_approval_for_live(evaluation)
        assert evaluation.status == AlphaStatus.VALIDATED_SHADOW_ONLY
        assert any("APPROVED_FOR_DEMO" in r for r in evaluation.rejection_reasons)


# ──────────────────────────────────────────────────────────────────────────
# 8. Registry persistence
# ──────────────────────────────────────────────────────────────────────────
class TestRegistryPersistence:
    def test_19_registry_persists_and_reloads(self, tmp_path: Path):
        path = tmp_path / "registry.json"
        reg = AlphaRegistry(path=path)
        c = _make_candidate("persist_alpha")
        reg.register(c)
        assert path.exists()

        # New instance loads from disk
        reg2 = AlphaRegistry(path=path)
        loaded = reg2.get_candidate("persist_alpha")
        assert loaded is not None
        assert loaded.name == "persist_alpha"
        assert loaded.status == "CANDIDATE"

    def test_20_registry_stores_and_reloads_evaluation(self, tmp_path: Path):
        path = tmp_path / "registry.json"
        reg = AlphaRegistry(path=path)
        reg.register(_make_candidate("eval_alpha"))

        ev = AlphaEvaluator()
        evaluation = ev.evaluate(
            reg.get_candidate("eval_alpha"),
            metrics={
                "walk_forward_score": 0.80,
                "broker_split_score": 0.80,
                "cost_adjusted_score": 0.60,
                "overfit_score": 0.20,
            },
        )
        reg.store_evaluation(evaluation)

        reg2 = AlphaRegistry(path=path)
        ev_loaded = reg2.get_evaluation("eval_alpha")
        assert ev_loaded is not None
        assert ev_loaded.status == AlphaStatus.VALIDATED_SHADOW_ONLY
        assert reg2.get_status("eval_alpha") == AlphaStatus.VALIDATED_SHADOW_ONLY

    def test_21_get_approved_for_demo_returns_only_demo_alphas(self, tmp_path: Path):
        path = tmp_path / "registry.json"
        reg = AlphaRegistry(path=path)
        reg.register(_make_candidate("demo_a"))
        reg.register(_make_candidate("demo_b"))
        reg.register(_make_candidate("shadow_only"))

        ev = AlphaEvaluator()
        for name in ("demo_a", "demo_b", "shadow_only"):
            evaluation = ev.evaluate(
                reg.get_candidate(name),
                metrics={
                    "walk_forward_score": 0.80,
                    "broker_split_score": 0.80,
                    "cost_adjusted_score": 0.60,
                    "overfit_score": 0.20,
                },
            )
            reg.store_evaluation(evaluation)

        # Promote only demo_a and demo_b
        for name in ("demo_a", "demo_b"):
            e = reg.get_evaluation(name)
            ev.promote_to_demo(e)
            reg.store_evaluation(e)

        approved = reg.get_approved_for_demo()
        assert set(approved) == {"demo_a", "demo_b"}
        assert "shadow_only" not in approved


# ──────────────────────────────────────────────────────────────────────────
# 9. No martingale / grid / averaging / loss_based_lot_multiplier
# ──────────────────────────────────────────────────────────────────────────
class TestNoMartingaleGridAveraging:
    @pytest.mark.parametrize(
        "module_path",
        [
            "titan.research.alpha_factory.alpha_candidate_generator",
            "titan.research.alpha_factory.alpha_evaluator",
            "titan.research.alpha_factory.alpha_registry",
        ],
    )
    def test_22_no_martingale_grid_averaging_in_source(self, module_path: str):
        module = sys.modules[module_path]
        src = inspect.getsource(module)
        # Strip docstrings (triple-quoted blocks) before scanning so that
        # documentation lines like "NEVER adds martingale, grid, averaging"
        # do not false-positive. We only forbid actual code usage.
        code_only = re.sub(
            r'"""[\s\S]*?"""', "", src
        )
        code_only = re.sub(
            r"'''[\s\S]*?'''", "", code_only
        )
        # Strip the rest of the comments
        lines = []
        for line in code_only.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            # drop inline comments
            if "#" in line:
                line = line.split("#", 1)[0]
            lines.append(line)
        code_text = "\n".join(lines)

        forbidden_patterns = [
            r"\bmartingale\b(?!\s*[:=]\s*False)",
            r"\bgrid_(?:step|level|order)\b",
            r"\baveraging_(?:down|up)\b",
            r"\bloss_based_lot_multiplier\b(?!\s*[:=]\s*True)",
            r"\bdef\s+martingale\b",
            r"\bdef\s+grid\b",
            r"\bdef\s+averaging\b",
        ]
        for pat in forbidden_patterns:
            matches = re.findall(pat, code_text, flags=re.IGNORECASE)
            assert len(matches) == 0, (
                f"Forbidden pattern {pat!r} found in {module_path}: {matches!r}"
            )

    def test_23_safety_contract_flags_are_true(self):
        for sc in (CAND_SAFETY, EV_SAFETY):
            assert sc["no_martingale"] is True
            assert sc["no_grid"] is True
            assert sc["no_averaging"] is True
            assert sc.get("no_loss_based_lot_multiplier") is True


# ──────────────────────────────────────────────────────────────────────────
# 10. No order_send / no MetaTrader5 import
# ──────────────────────────────────────────────────────────────────────────
class TestNoOrderSend:
    @pytest.mark.parametrize(
        "module_path",
        [
            "titan.research.alpha_factory.alpha_candidate_generator",
            "titan.research.alpha_factory.alpha_evaluator",
            "titan.research.alpha_factory.alpha_registry",
        ],
    )
    def test_24_no_metatrader5_import(self, module_path: str):
        module = sys.modules[module_path]
        src = inspect.getsource(module)
        assert "import MetaTrader5" not in src
        assert "from MetaTrader5" not in src

    @pytest.mark.parametrize(
        "module_path",
        [
            "titan.research.alpha_factory.alpha_candidate_generator",
            "titan.research.alpha_factory.alpha_evaluator",
            "titan.research.alpha_factory.alpha_registry",
        ],
    )
    def test_25_no_order_send_calls(self, module_path: str):
        module = sys.modules[module_path]
        src = inspect.getsource(module)
        # Allow "no_order_send" safety-flag references; forbid actual calls.
        call_pattern = r"(?<!['\"#])\b(mt5\.order_send|adapter\.send_open_order|adapter\.send_order|send_close_order)\s*\("
        for line in src.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if "no_order_send" in stripped:
                continue
            matches = re.findall(call_pattern, stripped)
            assert len(matches) == 0, (
                f"order_send call found in {module_path}: {stripped!r}"
            )

    def test_26_audit_script_has_no_order_send(self):
        path = REPO_ROOT / "scripts" / "research" / "run_alpha_factory_audit.py"
        src = path.read_text(encoding="utf-8")
        # The audit script references 'order_send' as a forbidden pattern
        # (for scanning other modules) — that's fine. But it must NOT
        # actually CALL mt5.order_send itself.
        for line in src.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            # Skip lines that are part of the forbidden-pattern regex
            if "r\"mt5" in stripped or "r'mt5" in stripped or "r\"\\bmt5" in stripped:
                continue
            if "no_order_send" in stripped:
                continue
            assert "mt5.order_send(" not in stripped, (
                f"audit script calls mt5.order_send: {stripped!r}"
            )
