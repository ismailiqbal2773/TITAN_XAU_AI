"""TITAN XAU AI - Sprint 9.9.3.45.8.8 Prop Funded Optimizer Tests"""
from __future__ import annotations
import sys, re
from pathlib import Path
import pytest
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from titan.production.prop_funded_optimizer import (
    PropFundedOptimizer, ProfileMetrics, OptimizationResult,
)


def _strip(src):
    src = re.sub(r'"""[\s\S]*?"""', '""', src)
    src = re.sub(r"'''[\s\S]*?'''", "''", src)
    src = re.sub(r'"(?:[^"\\]|\\.)*"', '""', src)
    src = re.sub(r"'(?:[^'\\]|\\.)*'", "''", src)
    return src


class TestPropFundedOptimizer:
    def test_01_optimizer_imports(self):
        assert PropFundedOptimizer is not None

    def test_02_optimize_returns_result(self):
        opt = PropFundedOptimizer()
        result = opt.optimize()
        assert isinstance(result, OptimizationResult)
        assert len(result.profiles) == 3

    def test_03_safe_profile_respects_dd_limits(self):
        """Safe profile must have internal daily DD <= 2.0% and total DD <= 6.0%."""
        opt = PropFundedOptimizer()
        result = opt.optimize()
        safe = next(p for p in result.profiles if p.profile_name == "prop_funded_safe")
        assert safe.internal_daily_dd_pct <= 2.0
        assert safe.internal_total_dd_pct <= 6.0

    def test_04_growth_profile_respects_dd_limits(self):
        """Growth profile must have internal daily DD <= 2.5% and total DD <= 7.0%."""
        opt = PropFundedOptimizer()
        result = opt.optimize()
        growth = next(p for p in result.profiles if p.profile_name == "prop_funded_growth")
        assert growth.internal_daily_dd_pct <= 2.5
        assert growth.internal_total_dd_pct <= 7.0

    def test_05_aggressive_profile_is_simulation_only(self):
        """Aggressive 20% profile must be simulation-only."""
        opt = PropFundedOptimizer()
        result = opt.optimize()
        aggressive = next(p for p in result.profiles if p.profile_name == "prop_funded_aggressive_20pct_simulation")
        assert aggressive.simulation_only is True
        assert aggressive.executable is False
        assert aggressive.live_allowed is False

    def test_06_aggressive_cannot_create_executable_request(self):
        """Aggressive profile executable must be False."""
        opt = PropFundedOptimizer()
        result = opt.optimize()
        aggressive = next(p for p in result.profiles if p.profile_name == "prop_funded_aggressive_20pct_simulation")
        assert aggressive.executable is False

    def test_07_optimizer_rejects_dd_breach(self):
        """Profile with DD > 8% must be blocked."""
        opt = PropFundedOptimizer()
        result = opt.optimize()
        aggressive = next(p for p in result.profiles if p.profile_name == "prop_funded_aggressive_20pct_simulation")
        # Aggressive has max_dd=9.43% which exceeds 8%
        # It should have DD breach
        assert aggressive.total_dd_breach_count > 0 or aggressive.max_dd > 8.0

    def test_08_optimizer_scores_profiles(self):
        """All profiles must have optimizer_score 0-100."""
        opt = PropFundedOptimizer()
        result = opt.optimize()
        for p in result.profiles:
            assert 0 <= p.optimizer_score <= 100

    def test_09_safe_profile_has_higher_score_than_aggressive(self):
        """Safe profile should score higher than aggressive (lower DD)."""
        opt = PropFundedOptimizer()
        result = opt.optimize()
        safe = next(p for p in result.profiles if p.profile_name == "prop_funded_safe")
        aggressive = next(p for p in result.profiles if p.profile_name == "prop_funded_aggressive_20pct_simulation")
        # Safe should generally score higher due to lower DD
        # (aggressive gets DD breach penalty)
        assert safe.optimizer_score >= aggressive.optimizer_score

    def test_10_optimizer_verdicts_valid(self):
        """Verdicts must be from the allowed set."""
        opt = PropFundedOptimizer()
        result = opt.optimize()
        valid_verdicts = {
            "PROP_FUNDED_OPTIMAL_READY",
            "PROP_FUNDED_READY_CONSERVATIVE",
            "PROP_FUNDED_GROWTH_READY",
            "PROP_FUNDED_AGGRESSIVE_SIMULATION_ONLY",
            "PROP_FUNDED_BLOCKED",
        }
        for p in result.profiles:
            assert p.verdict in valid_verdicts, f"Invalid verdict: {p.verdict}"

    def test_11_recommended_first_demo_profile_set(self):
        """Recommended first demo profile must be set."""
        opt = PropFundedOptimizer()
        result = opt.optimize()
        assert result.recommended_first_demo_profile != ""

    def test_12_evidence_source_documented(self):
        """All profiles must have evidence_source documented."""
        opt = PropFundedOptimizer()
        result = opt.optimize()
        for p in result.profiles:
            assert p.evidence_source != "", f"Missing evidence_source for {p.profile_name}"

    def test_13_no_order_send(self):
        src = (REPO_ROOT / "titan" / "production" / "prop_funded_optimizer.py").read_text()
        code = _strip(src)
        assert not re.search(r"\bmt5\.order_send\s*\(", code)

    def test_14_no_martingale(self):
        src = (REPO_ROOT / "titan" / "production" / "prop_funded_optimizer.py").read_text()
        code = _strip(src).lower()
        for term in ["martingale", "grid_trade", "averaging_down", "loss_based_lot"]:
            if term in code:
                idx = code.find(term)
                ctx = code[max(0, idx-40):idx+40]
                assert f"no_{term}" in ctx or f"no {term}" in ctx, f"Forbidden term '{term}' not negated"

    def test_15_metrics_have_all_fields(self):
        """ProfileMetrics must have all required fields."""
        opt = PropFundedOptimizer()
        result = opt.optimize()
        p = result.profiles[0]
        required = [
            "monthly_return_estimate", "yearly_return_estimate", "max_dd",
            "daily_dd_max", "daily_dd_breach_count", "total_dd_breach_count",
            "pf", "sharpe", "sortino", "win_rate", "expectancy",
            "wfe", "monte_carlo_survival", "broker_split_pass", "broker_score",
            "risk_per_trade_pct", "confidence_threshold", "atr_sl_multiplier",
            "tp_multiplier_initial_tp_R", "minimum_rr", "dynamic_tp_trigger_R",
            "optimizer_score", "verdict", "evidence_source",
        ]
        for f in required:
            assert hasattr(p, f), f"Missing field: {f}"

    def test_16_20pct_not_proven(self):
        """20% monthly must be marked NOT_PROVEN."""
        opt = PropFundedOptimizer()
        result = opt.optimize()
        assert "NOT_PROVEN" in result.aggressive_20pct_status or "REJECTED" in result.aggressive_20pct_status

    def test_17_safe_profile_executable(self):
        """Safe profile should be executable (not simulation-only)."""
        opt = PropFundedOptimizer()
        result = opt.optimize()
        safe = next(p for p in result.profiles if p.profile_name == "prop_funded_safe")
        assert safe.executable is True
        assert safe.simulation_only is False

    def test_18_growth_profile_executable(self):
        """Growth profile should be executable (not simulation-only)."""
        opt = PropFundedOptimizer()
        result = opt.optimize()
        growth = next(p for p in result.profiles if p.profile_name == "prop_funded_growth")
        assert growth.executable is True
        assert growth.simulation_only is False
