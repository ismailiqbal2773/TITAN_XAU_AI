"""
TITAN XAU AI — Monte Carlo Framework (Module 18)
10,000 simulations, 3 randomization dimensions, Survival Score.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from titan.backtest.engine import BacktestTrade, Verdict

logger = logging.getLogger(__name__)


@dataclass
class MCResult:
    survival_score: float = 0.0       # 0-100
    risk_of_ruin: float = 0.0         # 0-1
    p5_sharpe: float = 0.0
    p50_sharpe: float = 0.0
    p95_sharpe: float = 0.0
    p5_mdd: float = 0.0
    p50_mdd: float = 0.0
    p95_mdd: float = 0.0
    p5_cagr: float = 0.0
    p5_equity: float = 1.0
    total_sims: int = 0
    survived: int = 0
    verdict: Verdict = Verdict.REJECTED
    duration_seconds: float = 0.0


class MonteCarloEngine:
    """
    Monte Carlo simulation engine.
    3 randomization dimensions: trade order, slippage, spread.
    Survival = profitable AND MDD ≤ 8% AND Sharpe ≥ 1.0.
    """

    def __init__(self, n_simulations: int = 10000, seed: int = 42):
        self._n_sims = n_simulations
        self._seed = seed

    def run(self, trades: list[BacktestTrade],
            initial_equity: float = 10000.0) -> MCResult:
        """Run Monte Carlo on trade ledger."""
        start = time.perf_counter()

        if not trades:
            return MCResult(verdict=Verdict.REJECTED,
                            duration_seconds=time.perf_counter() - start)

        np.random.seed(self._seed)
        n_trades = len(trades)
        pnls = np.array([t.pnl for t in trades])
        slippages = np.array([t.slippage for t in trades])
        spreads = np.array([t.spread_cost for t in trades])

        # Baseline values for randomization
        slip_p50 = np.median(slippages) if len(slippages) > 0 else 0.04
        slip_p99 = np.percentile(slippages, 99) if len(slippages) > 0 else 0.35
        spread_baseline = np.median(spreads) / 10.0 if len(spreads) > 0 else 0.18

        sharpes = np.zeros(self._n_sims)
        mdds = np.zeros(self._n_sims)
        cagrs = np.zeros(self._n_sims)
        final_equities = np.zeros(self._n_sims)
        survived_count = 0

        for i in range(self._n_sims):
            # Dimension 1: Shuffle trade order
            shuffled = np.random.permutation(pnls)

            # Dimension 2: Random slippage (LogNormal)
            slip_costs = np.random.lognormal(
                mean=np.log(max(slip_p50, 0.001)),
                sigma=0.3, size=n_trades
            )
            slip_costs = np.clip(slip_costs, 0, slip_p99 * 3)

            # Dimension 3: Random spread (Beta × max)
            spread_mult = np.random.beta(2, 5, size=n_trades) * 5.0
            spread_costs = spread_baseline * spread_mult * 10.0

            # Adjusted PnL
            adjusted_pnls = shuffled - slip_costs - spread_costs

            # Equity curve
            equity = np.cumsum(np.concatenate([[initial_equity], adjusted_pnls]))
            final_equity = equity[-1]
            final_equities[i] = final_equity

            # Max drawdown
            peak = np.maximum.accumulate(equity)
            dd = (peak - equity) / np.where(peak > 0, peak, 1)
            mdd = float(np.max(dd)) * 100 if len(dd) > 0 else 0.0
            mdds[i] = mdd

            # Sharpe
            if len(adjusted_pnls) > 1 and np.std(adjusted_pnls) > 0:
                sharpe = float(np.mean(adjusted_pnls) / np.std(adjusted_pnls) * np.sqrt(252))
            else:
                sharpe = 0.0
            sharpes[i] = sharpe

            # CAGR (simplified)
            cagr = (final_equity / initial_equity - 1) * 100
            cagrs[i] = cagr

            # Survival check
            if final_equity > initial_equity and mdd <= 8.0 and sharpe >= 1.0:
                survived_count += 1

        survival_score = (survived_count / self._n_sims) * 100
        risk_of_ruin = np.mean(final_equities < initial_equity * 0.5)

        # Verdict
        if survival_score >= 95.0 and np.percentile(sharpes, 5) >= 1.0:
            verdict = Verdict.CERTIFIED
        elif survival_score >= 85.0 and np.percentile(sharpes, 5) >= 0.8:
            verdict = Verdict.CONDITIONAL
        else:
            verdict = Verdict.REJECTED

        elapsed = time.perf_counter() - start
        return MCResult(
            survival_score=survival_score,
            risk_of_ruin=float(risk_of_ruin),
            p5_sharpe=float(np.percentile(sharpes, 5)),
            p50_sharpe=float(np.percentile(sharpes, 50)),
            p95_sharpe=float(np.percentile(sharpes, 95)),
            p5_mdd=float(np.percentile(mdds, 5)),
            p50_mdd=float(np.percentile(mdds, 50)),
            p95_mdd=float(np.percentile(mdds, 95)),
            p5_cagr=float(np.percentile(cagrs, 5)),
            p5_equity=float(np.percentile(final_equities, 5) / initial_equity),
            total_sims=self._n_sims,
            survived=survived_count,
            verdict=verdict,
            duration_seconds=elapsed,
        )
