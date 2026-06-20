"""Tests for Validation Framework — Backtest, WFA, MC, Stress, Validator"""
import pytest
import numpy as np
from titan.backtest.engine import (
    TickReplayExecutor, CostEngine, TickData, Verdict,
    generate_synthetic_ticks, generate_synthetic_signals,
)
from titan.walk_forward.engine import WalkForwardEngine
from titan.monte_carlo.engine import MonteCarloEngine
from titan.stress_test.engine import StressTestEngine
from titan.validator.engine import ValidatorFramework
from titan.backtest.engine import BacktestTrade


@pytest.fixture
def ticks():
    return generate_synthetic_ticks(n_ticks=2000)


@pytest.fixture
def signals(ticks):
    return generate_synthetic_signals(ticks, frequency=100)


# ─── Backtest Tests ───

class TestCostEngine:
    def test_compute_costs(self):
        ce = CostEngine()
        costs = ce.compute_costs(
            entry_price=2000, exit_price=2010, direction=1, volume=0.5,
            spread_entry=0.18, spread_exit=0.18, hold_days=1.0,
            slippage_entry=0.04, slippage_exit=0.04,
        )
        assert costs["spread"] > 0
        assert costs["commission"] > 0
        assert costs["slippage"] > 0
        # Swap can be negative (credit) or positive (cost) depending on direction
        # Total should include all components
        assert "total" in costs


class TestTickReplayExecutor:
    def test_run_returns_result(self, ticks, signals):
        executor = TickReplayExecutor()
        result = executor.run(ticks, signals)
        assert result.total_trades > 0
        assert result.initial_equity == 10000.0
        assert result.duration_seconds > 0

    def test_result_has_metrics(self, ticks, signals):
        executor = TickReplayExecutor()
        result = executor.run(ticks, signals)
        assert result.sharpe is not None
        assert result.max_drawdown is not None
        assert result.win_rate is not None
        assert result.profit_factor is not None
        assert result.cost_drag is not None

    def test_verdict_in_valid_range(self, ticks, signals):
        executor = TickReplayExecutor()
        result = executor.run(ticks, signals)
        assert result.verdict in [Verdict.CERTIFIED, Verdict.CONDITIONAL, Verdict.REJECTED]

    def test_empty_signals(self, ticks):
        executor = TickReplayExecutor()
        result = executor.run(ticks, [])
        assert result.total_trades == 0
        assert result.verdict == Verdict.REJECTED


class TestSyntheticData:
    def test_generate_ticks(self):
        ticks = generate_synthetic_ticks(n_ticks=100)
        assert len(ticks) == 100
        assert all(t.bid > 0 and t.ask > 0 for t in ticks)
        assert all(t.ask >= t.bid for t in ticks)

    def test_generate_signals(self, ticks):
        signals = generate_synthetic_signals(ticks, frequency=50)
        assert len(signals) > 0
        assert all(s["direction"] in [-1, 1] for s in signals)


# ─── Walk-Forward Tests ───

class TestWalkForward:
    def test_run_returns_result(self, ticks, signals):
        wfa = WalkForwardEngine(train_size=500, test_size=100, step=200)
        result = wfa.run(ticks, signals, method="anchored")
        assert len(result.folds) > 0
        assert result.wfe_median >= 0
        assert result.verdict in [Verdict.CERTIFIED, Verdict.CONDITIONAL, Verdict.REJECTED]

    def test_fold_results_have_wfe(self, ticks, signals):
        wfa = WalkForwardEngine(train_size=500, test_size=100, step=300)
        result = wfa.run(ticks, signals)
        for fold in result.folds:
            assert fold.wfe >= 0
            assert fold.is_sharpe >= 0
            assert fold.oos_sharpe is not None

    def test_insufficient_data(self):
        ticks = generate_synthetic_ticks(n_ticks=100)
        signals = generate_synthetic_signals(ticks)
        wfa = WalkForwardEngine(train_size=500, test_size=100, step=100)
        result = wfa.run(ticks, signals)
        assert result.verdict == Verdict.REJECTED
        assert len(result.folds) == 0


# ─── Monte Carlo Tests ───

class TestMonteCarlo:
    @pytest.fixture
    def trades(self):
        np.random.seed(42)
        return [
            BacktestTrade(
                symbol="XAUUSD", direction=1, volume=0.1,
                entry_price=2000, exit_price=2010,
                pnl=np.random.randn() * 50 + 10,
                pnl_ideal=np.random.randn() * 50 + 15,
                slippage=0.04, spread_cost=3.6,
            )
            for _ in range(50)
        ]

    def test_run_returns_result(self, trades):
        mc = MonteCarloEngine(n_simulations=100)
        result = mc.run(trades)
        assert result.total_sims == 100
        assert 0 <= result.survival_score <= 100
        assert 0 <= result.risk_of_ruin <= 1
        assert result.verdict in [Verdict.CERTIFIED, Verdict.CONDITIONAL, Verdict.REJECTED]

    def test_survival_score_calculated(self, trades):
        mc = MonteCarloEngine(n_simulations=100)
        result = mc.run(trades)
        assert result.survived >= 0
        assert result.survived <= 100

    def test_percentiles_populated(self, trades):
        mc = MonteCarloEngine(n_simulations=100)
        result = mc.run(trades)
        assert result.p5_sharpe is not None
        assert result.p50_sharpe is not None
        assert result.p95_sharpe is not None

    def test_empty_trades(self):
        mc = MonteCarloEngine(n_simulations=10)
        result = mc.run([])
        assert result.verdict == Verdict.REJECTED


# ─── Stress Test Tests ───

class TestStressTest:
    def test_run_all_returns_results(self, ticks, signals):
        engine = StressTestEngine()
        result = engine.run_all(ticks, signals)
        assert len(result.results) == 6  # 6 scenarios
        assert result.duration_seconds > 0

    def test_all_scenarios_present(self, ticks, signals):
        from titan.stress_test.engine import StressScenario
        engine = StressTestEngine()
        result = engine.run_all(ticks, signals)
        scenarios = {r.scenario for r in result.results}
        assert StressScenario.FLASH_CRASH in scenarios
        assert StressScenario.HIGH_SPREAD in scenarios
        assert StressScenario.SERVER_LAG in scenarios
        assert StressScenario.BROKER_DISCONNECT in scenarios
        assert StressScenario.EXTREME_VOLATILITY in scenarios
        assert StressScenario.GAP_OPEN in scenarios

    def test_each_result_has_pass_fail(self, ticks, signals):
        engine = StressTestEngine()
        result = engine.run_all(ticks, signals)
        for r in result.results:
            assert isinstance(r.passed, bool)
            assert r.metric_value is not None
            assert r.threshold is not None


# ─── Validator Tests ───

class TestValidator:
    def test_run_returns_certification(self, ticks, signals):
        validator = ValidatorFramework()
        result = validator.run(ticks, signals)
        assert len(result.suites) == 8
        assert 0 <= result.aggregate_score <= 100
        assert result.verdict in [Verdict.CERTIFIED, Verdict.CONDITIONAL, Verdict.REJECTED]
        assert result.duration_seconds > 0

    def test_all_suites_present(self, ticks, signals):
        validator = ValidatorFramework()
        result = validator.run(ticks, signals)
        suite_ids = {s.suite_id for s in result.suites}
        assert "S1_BROKER" in suite_ids
        assert "S2_RISK" in suite_ids
        assert "S8_BACKTEST" in suite_ids

    def test_suite_scores_in_range(self, ticks, signals):
        validator = ValidatorFramework()
        result = validator.run(ticks, signals)
        for s in result.suites:
            assert 0 <= s.score <= 100

    def test_aggregate_score_weighted(self, ticks, signals):
        validator = ValidatorFramework()
        result = validator.run(ticks, signals)
        # Aggregate should be close to weighted average
        weights = ValidatorFramework.SUITE_WEIGHTS
        expected = sum(s.score * weights.get(s.suite_id, 0) for s in result.suites) / sum(weights.values())
        assert abs(result.aggregate_score - expected) < 1.0

    def test_run_without_data_uses_synthetic(self):
        validator = ValidatorFramework()
        result = validator.run()
        assert len(result.suites) == 8
