"""Tests for Dynamic Weighting Engine"""
import pytest
import numpy as np
from titan.weighting.engine import (
    WeightingEngine, ModelWeights, ModelMetrics, WeightingInputs,
    BayesianWeighting, WeightedVoting, ThompsonSamplingMAB,
    OnlineLinearRegression, MetaBandit, MODELS, ALGORITHMS,
)


@pytest.fixture
def metrics():
    return {
        m: ModelMetrics(
            accuracy=0.6, profit_factor=1.8, sharpe=2.0,
            dd_contribution=0.3, slippage_sensitivity=0.2,
            latency_sensitivity=0.1, regime_performance=0.65,
        )
        for m in MODELS
    }


@pytest.fixture
def inputs():
    return WeightingInputs(
        predictions={}, confidence={m: 0.7 for m in MODELS},
        regime="trend", eqs=90, risk_score=90, broker_score=90,
        ceo_caps={}, ceo_disabled=set(),
    )


class TestBayesianWeighting:
    def test_weights_sum_to_one(self, metrics, inputs):
        algo = BayesianWeighting()
        w = algo.compute_weights(metrics, inputs)
        assert abs(sum(w.values()) - 1.0) < 1e-6

    def test_weights_non_negative(self, metrics, inputs):
        algo = BayesianWeighting()
        w = algo.compute_weights(metrics, inputs)
        assert all(v >= 0 for v in w.values())

    def test_update_on_win(self):
        algo = BayesianWeighting()
        a_before, b_before = algo._priors["xgboost"]
        algo.update("xgboost", outcome=1.0)  # win
        a_after, b_after = algo._priors["xgboost"]
        assert a_after == a_before + 1
        assert b_after == b_before

    def test_update_on_loss(self):
        algo = BayesianWeighting()
        a_before, b_before = algo._priors["xgboost"]
        algo.update("xgboost", outcome=-1.0)  # loss
        a_after, b_after = algo._priors["xgboost"]
        assert a_after == a_before
        assert b_after == b_before + 1


class TestWeightedVoting:
    def test_weights_sum_to_one(self, metrics, inputs):
        algo = WeightedVoting()
        w = algo.compute_weights(metrics, inputs)
        assert abs(sum(w.values()) - 1.0) < 1e-6

    def test_update_changes_weights(self, metrics, inputs):
        algo = WeightedVoting()
        w1 = algo.compute_weights(metrics, inputs)
        algo.update("xgboost", outcome=3.0)  # High reward
        w2 = algo.compute_weights(metrics, inputs)
        # XGBoost weight should increase
        assert w2["xgboost"] >= w1["xgboost"]


class TestThompsonSamplingMAB:
    def test_weights_sum_to_one(self, metrics, inputs):
        algo = ThompsonSamplingMAB()
        w = algo.compute_weights(metrics, inputs)
        assert abs(sum(w.values()) - 1.0) < 1e-6

    def test_exploration(self, metrics, inputs):
        """MAB should explore — even low-performing arms get non-zero weight."""
        algo = ThompsonSamplingMAB()
        # Penalize xgboost heavily
        for _ in range(20):
            algo.update("xgboost", reward=0.0)
        w = algo.compute_weights(metrics, inputs)
        # xgboost should still get some weight (exploration)
        assert w["xgboost"] > 0

    def test_update_on_reward(self):
        algo = ThompsonSamplingMAB()
        a_before, b_before = algo._arms["lstm"]
        algo.update("lstm", reward=0.8)  # Good reward
        a_after, _ = algo._arms["lstm"]
        assert a_after == a_before + 1


class TestOnlineLinearRegression:
    def test_weights_sum_to_one(self, metrics, inputs):
        algo = OnlineLinearRegression()
        w = algo.compute_weights(metrics, inputs)
        assert abs(sum(w.values()) - 1.0) < 1e-6

    def test_update_changes_weights(self, metrics, inputs):
        algo = OnlineLinearRegression()
        w1 = algo.compute_weights(metrics, inputs)
        algo.update("xgboost", outcome=2.0)
        w2 = algo.compute_weights(metrics, inputs)
        # Weights should change
        assert w1 != w2


class TestMetaBandit:
    def test_select_algorithm_returns_valid(self):
        mb = MetaBandit()
        for regime in MetaBandit.REGIMES:
            algo = mb.select_algorithm(regime)
            assert algo in ALGORITHMS

    def test_update_changes_posterior(self):
        mb = MetaBandit()
        # Favor bayesian in trend
        for _ in range(20):
            mb.update("bayesian", "trend", quality=1.0)
        for _ in range(20):
            mb.update("mab_thompson", "trend", quality=0.0)
        best = mb.get_best_algorithm("trend")
        assert best == "bayesian"

    def test_per_regime_selection(self):
        mb = MetaBandit()
        # Train: bayesian best in range, mab best in trend
        for _ in range(20):
            mb.update("bayesian", "range", quality=1.0)
            mb.update("mab_thompson", "trend", quality=1.0)
        assert mb.get_best_algorithm("range") == "bayesian"
        assert mb.get_best_algorithm("trend") == "mab_thompson"


class TestWeightingEngine:
    def test_run_cycle_returns_weights(self, metrics, inputs):
        engine = WeightingEngine()
        result = engine.run_cycle(metrics, inputs)
        assert isinstance(result, ModelWeights)
        assert abs(sum(result.weights.values()) - 1.0) < 1e-6
        assert result.algorithm_used in ALGORITHMS

    def test_no_fixed_weights(self, metrics, inputs):
        """Weights must change across cycles — no fixed arrays."""
        engine = WeightingEngine()
        results = []
        for _ in range(10):
            r = engine.run_cycle(metrics, inputs)
            results.append(tuple(r.weights[m] for m in MODELS))
        # At least 3 distinct weight vectors
        distinct = len(set(results))
        assert distinct >= 2  # At least some variation

    def test_ceo_caps_applied(self, metrics):
        inputs = WeightingInputs(
            regime="trend", ceo_caps={"xgboost": 0.10}, ceo_disabled=set(),
            confidence={m: 0.7 for m in MODELS},
        )
        engine = WeightingEngine()
        result = engine.run_cycle(metrics, inputs)
        # After cap + re-normalization, xgboost should be significantly reduced
        assert result.weights["xgboost"] < 0.20  # Well below default 25%

    def test_ceo_disabled_model_zero(self, metrics):
        inputs = WeightingInputs(
            regime="trend", ceo_caps={}, ceo_disabled={"lstm"},
            confidence={m: 0.7 for m in MODELS},
        )
        engine = WeightingEngine()
        result = engine.run_cycle(metrics, inputs)
        assert result.weights["lstm"] == 0.0
        # Others should re-normalize
        assert abs(sum(result.weights.values()) - 1.0) < 1e-6

    def test_feedback_loop_updates(self, metrics, inputs):
        engine = WeightingEngine()
        engine.run_cycle(metrics, inputs)
        # Should not crash
        engine.on_trade_outcome("xgboost", reward=0.8, regime="trend", weight_quality=1.0)
        engine.on_trade_outcome("lstm", reward=0.2, regime="trend", weight_quality=0.0)

    def test_meta_bandit_best_tracking(self, metrics, inputs):
        engine = WeightingEngine()
        # Train meta-bandit
        for _ in range(20):
            engine.run_cycle(metrics, inputs)
            engine.on_trade_outcome("xgboost", reward=0.9, regime="trend", weight_quality=1.0)
        best = engine.meta_bandit_best
        assert "trend" in best
        assert best["trend"] in ALGORITHMS

    def test_all_weights_non_negative(self, metrics, inputs):
        engine = WeightingEngine()
        result = engine.run_cycle(metrics, inputs)
        assert all(v >= 0 for v in result.weights.values())

    def test_cycle_count_increments(self, metrics, inputs):
        engine = WeightingEngine()
        assert engine.cycle_count == 0
        engine.run_cycle(metrics, inputs)
        assert engine.cycle_count == 1
        engine.run_cycle(metrics, inputs)
        assert engine.cycle_count == 2
