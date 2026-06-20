"""
TITAN XAU AI — Walk-Forward Framework (Module 17)
Anchored/rolling WFA, WFE calculation, 3-band verdict.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import numpy as np

from titan.backtest.engine import TickReplayExecutor, TickData, Verdict

logger = logging.getLogger(__name__)


@dataclass
class FoldResult:
    fold_num: int
    train_start: int
    train_end: int
    test_start: int
    test_end: int
    is_sharpe: float = 0.0
    oos_sharpe: float = 0.0
    oos_mdd: float = 0.0
    oos_return: float = 0.0
    wfe: float = 0.0


@dataclass
class WFAResult:
    folds: list[FoldResult] = field(default_factory=list)
    wfe_median: float = 0.0
    wfe_min: float = 0.0
    wfe_max: float = 0.0
    oos_sharpe_median: float = 0.0
    oos_mdd_max: float = 0.0
    fold_consistency: float = 0.0  # Fraction of profitable folds
    verdict: Verdict = Verdict.REJECTED
    method: str = "anchored"
    duration_seconds: float = 0.0


class WalkForwardEngine:
    """
    Walk-Forward Analysis engine.
    Supports anchored (train grows) and rolling (train slides) windows.
    """

    def __init__(self, train_size: int = 500, test_size: int = 100, step: int = 100,
                 purge: int = 0, embargo: int = 0):
        """
        Walk-Forward Analysis engine.

        Parameters
        ----------
        train_size : int
            Number of bars in each training window.
        test_size : int
            Number of bars in each test window.
        step : int
            Number of bars to advance the window between folds.
        purge : int
            Purge gap (bars) between train_end and test_start. Set to
            max(target_horizons) to prevent label leakage from forward-
            shifted targets. (B4 remediation)
        embargo : int
            Embargo window (bars) AFTER each test_end, excluded from the
            next fold's training data. Prevents serial-correlation leakage.
            (B4 remediation)
        """
        self._train_size = train_size
        self._test_size = test_size
        self._step = step
        self._purge = max(0, purge)
        self._embargo = max(0, embargo)
        self._executor = TickReplayExecutor()

    def _run_fold(self, fold_num: int, ticks: list, signals: list,
                  train_start: int, train_end: int,
                  test_start: int, test_end: int) -> FoldResult:
        """Run a single WFA fold. Shared between anchored and rolling modes."""
        train_ticks = ticks[train_start:train_end]
        test_ticks = ticks[test_start:test_end]
        # Train: run backtest on train window (IS)
        train_signals = [s for s in signals
                         if train_ticks[0].time <= s["time"] <= train_ticks[-1].time]
        is_result = self._executor.run(train_ticks, train_signals)
        is_sharpe = is_result.sharpe if is_result.sharpe > 0 else 0.5
        # Test: run backtest on test window (OOS)
        test_signals = [s for s in signals
                        if test_ticks[0].time <= s["time"] <= test_ticks[-1].time]
        oos_result = self._executor.run(test_ticks, test_signals)
        # WFE for this fold
        wfe = oos_result.sharpe / is_sharpe if is_sharpe > 0 else 0.0
        return FoldResult(
            fold_num=fold_num,
            train_start=train_start, train_end=train_end,
            test_start=test_start, test_end=test_end,
            is_sharpe=is_sharpe,
            oos_sharpe=oos_result.sharpe,
            oos_mdd=oos_result.max_drawdown,
            oos_return=oos_result.total_return,
            wfe=wfe,
        )

    def run(self, ticks: list[TickData], signals: list[dict],
            method: str = "anchored") -> WFAResult:
        """Run walk-forward analysis on tick data.

        method='anchored': training window grows from index 0; only the
        test window slides forward. The first bar of every training
        window stays at index 0. (B1 remediation: previously the
        anchored branch was identical to rolling, producing a sliding
        window instead of a growing one.)

        method='rolling': both training and test windows slide forward
        by `step` bars per fold.

        Both modes apply the purge gap (between train_end and test_start)
        and embargo window (after test_end, before the next fold's
        train_start) when configured. (B4 remediation)
        """
        start = time.perf_counter()
        folds = []
        n = len(ticks)
        fold_num = 0

        if method == "anchored":
            # B1 FIX: True anchored expansion. train_start stays at 0;
            # train_end grows by `step` per fold. Only the test window
            # slides forward.
            train_end = self._train_size
            while train_end + self._purge + self._test_size <= n:
                fold_num += 1
                train_start = 0
                test_start = train_end + self._purge
                test_end = test_start + self._test_size
                fold = self._run_fold(
                    fold_num, ticks, signals,
                    train_start, train_end, test_start, test_end,
                )
                folds.append(fold)
                # Grow the training window by step; embargo prevents the
                # next fold's training data from including bars whose
                # targets overlap with the just-tested window.
                train_end += self._step + self._embargo
        elif method == "rolling":
            # Rolling: both windows slide forward by step.
            train_start = 0
            while train_start + self._train_size + self._purge + self._test_size <= n:
                fold_num += 1
                train_end = train_start + self._train_size
                test_start = train_end + self._purge
                test_end = test_start + self._test_size
                fold = self._run_fold(
                    fold_num, ticks, signals,
                    train_start, train_end, test_start, test_end,
                )
                folds.append(fold)
                train_start += self._step + self._embargo
        else:
            raise ValueError(
                f"Unknown method: {method!r} (use 'anchored' or 'rolling')"
            )

        if not folds:
            return WFAResult(verdict=Verdict.REJECTED, method=method,
                             duration_seconds=time.perf_counter() - start)

        # Aggregate
        wfes = [f.wfe for f in folds]
        oos_sharpes = [f.oos_sharpe for f in folds]
        oos_mdds = [f.oos_mdd for f in folds]
        profitable = sum(1 for f in folds if f.oos_return > 0)

        wfe_median = float(np.median(wfes))
        wfe_min = float(np.min(wfes))
        wfe_max = float(np.max(wfes))
        oos_sharpe_median = float(np.median(oos_sharpes))
        oos_mdd_max = float(np.max(oos_mdds))
        fold_consistency = profitable / len(folds) if folds else 0.0

        # Verdict
        if wfe_median >= 0.85 and oos_sharpe_median >= 1.5 and fold_consistency >= 0.8:
            verdict = Verdict.CERTIFIED
        elif wfe_median >= 0.50 and oos_sharpe_median >= 1.0:
            verdict = Verdict.CONDITIONAL
        else:
            verdict = Verdict.REJECTED

        elapsed = time.perf_counter() - start
        return WFAResult(
            folds=folds, wfe_median=wfe_median, wfe_min=wfe_min, wfe_max=wfe_max,
            oos_sharpe_median=oos_sharpe_median, oos_mdd_max=oos_mdd_max,
            fold_consistency=fold_consistency, verdict=verdict,
            method=method, duration_seconds=elapsed,
        )
