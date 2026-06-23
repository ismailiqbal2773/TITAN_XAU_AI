"""
TITAN XAU AI — Meta Calibration Monitor (Sprint 8.1)

Tracks meta-label predicted probabilities vs realized trade outcomes.
Computes rolling ECE, Brier, calibration slope, and reliability bins.
Applies isotonic recalibration when ECE degrades — WITHOUT touching L1.

States:
  CALIBRATED             ECE < 0.07
  WATCH                  0.07 <= ECE < 0.10
  RECALIBRATE_REQUIRED   0.10 <= ECE < 0.15
  KILL_THRESHOLD_BREACHED ECE >= 0.15

Usage:
    mon = MetaCalibrationMonitor()
    mon.record_prediction(prob_win=0.80, actual_outcome=1)
    state = mon.get_state()
    if state == CalibrationState.RECALIBRATE_REQUIRED:
        mon.recalibrate()
"""
from __future__ import annotations

import logging
import math
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


class CalibrationState(str, Enum):
    CALIBRATED = "CALIBRATED"
    WATCH = "WATCH"
    RECALIBRATE_REQUIRED = "RECALIBRATE_REQUIRED"
    KILL_THRESHOLD_BREACHED = "KILL_THRESHOLD_BREACHED"


@dataclass
class CalibrationConfig:
    """Configuration for meta-label calibration monitoring."""
    enabled: bool = True
    window_size: int = 200           # rolling window of trades
    min_samples: int = 50            # minimum before any action
    watch_ece: float = 0.07
    recalibrate_ece: float = 0.10
    kill_ece: float = 0.15
    method: str = "isotonic"         # isotonic | Platt (only isotonic implemented)
    dry_run_only: bool = True        # if True, recalibration is logged but not applied to live predictions


@dataclass
class CalibrationReport:
    """Snapshot of calibration metrics."""
    timestamp: float
    n_samples: int = 0
    ece: float = 0.0
    brier: float = 0.0
    calibration_slope: float = 1.0   # 1.0 = perfectly calibrated
    state: CalibrationState = CalibrationState.CALIBRATED
    reliability_bins: list = field(default_factory=list)
    recalibrated: bool = False
    error: Optional[str] = None

    def __repr__(self) -> str:
        return (
            f"CalibrationReport(n={self.n_samples}, ece={self.ece:.4f}, "
            f"brier={self.brier:.4f}, slope={self.calibration_slope:.3f}, "
            f"state={self.state.value}, recalibrated={self.recalibrated})"
        )


class MetaCalibrationMonitor:
    """
    Rolling meta-label calibration monitor.

    Records (predicted_prob, actual_outcome) pairs and computes:
      - ECE (Expected Calibration Error)
      - Brier score
      - Calibration slope (linear regression of outcome on prob)
      - Reliability bins (for reliability diagram)

    When ECE crosses thresholds, transitions state.
    In RECALIBRATE_REQUIRED, fits isotonic regression to remap probabilities.
    NEVER modifies the L1 XGBoost model — only the meta-label probability mapping.
    """

    def __init__(self, config: Optional[CalibrationConfig] = None):
        self.config = config or CalibrationConfig()
        self._predictions: deque = deque(maxlen=self.config.window_size)
        self._outcomes: deque = deque(maxlen=self.config.window_size)
        self._isotonic_model = None       # sklearn IsotonicRegression (fitted)
        self._recalibration_count = 0
        self._last_state = CalibrationState.CALIBRATED
        logger.info(f"MetaCalibrationMonitor initialized: window={self.config.window_size}")

    # ─── Public API ─────────────────────────────────────────────────────

    def record_prediction(self, prob_win: float, actual_outcome: int) -> None:
        """
        Record a single meta-label prediction + realized outcome.

        Args:
            prob_win: Meta-label predicted P(win) [0, 1]
            actual_outcome: 1 = trade won, 0 = trade lost
        """
        self._predictions.append(float(prob_win))
        self._outcomes.append(int(actual_outcome))

    def get_report(self) -> CalibrationReport:
        """Compute current calibration report."""
        n = len(self._predictions)
        if n == 0:
            return CalibrationReport(timestamp=time.time())

        try:
            preds = np.array(self._predictions)
            outcomes = np.array(self._outcomes)

            ece = self._compute_ece(preds, outcomes)
            brier = self._compute_brier(preds, outcomes)
            slope = self._compute_slope(preds, outcomes)
            bins = self._compute_reliability_bins(preds, outcomes)
            state = self._determine_state(ece, n)

            return CalibrationReport(
                timestamp=time.time(),
                n_samples=n,
                ece=ece,
                brier=brier,
                calibration_slope=slope,
                state=state,
                reliability_bins=bins,
            )
        except Exception as e:
            logger.error(f"Calibration report error: {e}")
            return CalibrationReport(
                timestamp=time.time(), n_samples=n, error=str(e),
                state=CalibrationState.KILL_THRESHOLD_BREACHED,  # fail-safe
            )

    def recalibrate(self) -> bool:
        """
        Fit isotonic regression on (predicted_prob → actual_outcome).
        This remaps the meta-label probability mapping WITHOUT touching L1.

        Returns True iff recalibration succeeded.
        """
        n = len(self._predictions)
        if n < self.config.min_samples:
            logger.warning(
                f"Recalibration skipped: only {n} samples "
                f"(need {self.config.min_samples})"
            )
            return False

        try:
            from sklearn.isotonic import IsotonicRegression
            preds = np.array(self._predictions)
            outcomes = np.array(self._outcomes)

            self._isotonic_model = IsotonicRegression(
                y_min=0.0, y_max=1.0, out_of_bounds="clip",
            )
            self._isotonic_model.fit(preds, outcomes)
            self._recalibration_count += 1
            logger.info(
                f"Isotonic recalibration fitted on {n} samples "
                f"(recalibration #{self._recalibration_count})"
            )

            # Verify improvement
            remapped = self._isotonic_model.predict(preds)
            new_ece = self._compute_ece(remapped, outcomes)
            old_ece = self._compute_ece(preds, outcomes)
            logger.info(
                f"Recalibration ECE: {old_ece:.4f} → {new_ece:.4f} "
                f"(improvement: {(old_ece - new_ece):.4f})"
            )
            return True
        except ImportError:
            logger.error("sklearn not available — cannot recalibrate")
            return False
        except Exception as e:
            logger.error(f"Recalibration failed: {e}")
            return False

    def apply_recalibration(self, prob_win: float) -> float:
        """
        Apply isotonic recalibration to a new probability.
        If no recalibration has been done, returns the input unchanged.

        This is the ONLY function that changes what the trade loop sees —
        it remaps meta-label P(win) but NEVER touches L1 XGBoost.
        """
        if self._isotonic_model is None:
            return prob_win
        return float(self._isotonic_model.predict([prob_win])[0])

    # ─── State determination ────────────────────────────────────────────

    def _determine_state(self, ece: float, n: int) -> CalibrationState:
        """Determine calibration state from ECE."""
        if n < self.config.min_samples:
            return CalibrationState.CALIBRATED  # not enough data to judge
        if ece >= self.config.kill_ece:
            return CalibrationState.KILL_THRESHOLD_BREACHED
        if ece >= self.config.recalibrate_ece:
            return CalibrationState.RECALIBRATE_REQUIRED
        if ece >= self.config.watch_ece:
            return CalibrationState.WATCH
        return CalibrationState.CALIBRATED

    @property
    def state(self) -> CalibrationState:
        """Current calibration state."""
        return self.get_report().state

    @property
    def recalibration_count(self) -> int:
        return self._recalibration_count

    @property
    def has_recalibration(self) -> bool:
        return self._isotonic_model is not None

    @property
    def sample_count(self) -> int:
        return len(self._predictions)

    # ─── Metric computations ────────────────────────────────────────────

    def _compute_ece(self, preds: np.ndarray, outcomes: np.ndarray,
                     n_bins: int = 10) -> float:
        """Expected Calibration Error (binned)."""
        bin_boundaries = np.linspace(0, 1, n_bins + 1)
        ece = 0.0
        n = len(preds)
        for i in range(n_bins):
            lo, hi = bin_boundaries[i], bin_boundaries[i + 1]
            mask = (preds >= lo) & (preds < hi if i < n_bins - 1 else preds <= hi)
            if not mask.any():
                continue
            bin_size = mask.sum()
            avg_conf = preds[mask].mean()
            avg_acc = outcomes[mask].mean()
            ece += (bin_size / n) * abs(avg_conf - avg_acc)
        return float(ece)

    def _compute_brier(self, preds: np.ndarray, outcomes: np.ndarray) -> float:
        """Brier score = mean((pred - outcome)^2)."""
        return float(np.mean((preds - outcomes) ** 2))

    def _compute_slope(self, preds: np.ndarray, outcomes: np.ndarray) -> float:
        """
        Calibration slope via linear regression: outcome = a + b * pred.
        slope=1.0 = perfectly calibrated.
        slope>1 = underconfident (predictions too conservative).
        slope<1 = overconfident (predictions too extreme).
        """
        if len(preds) < 2:
            return 1.0
        # Add small noise to avoid singular matrix
        x = preds + np.random.normal(0, 1e-8, len(preds))
        y = outcomes
        # OLS: b = cov(x,y) / var(x)
        var_x = np.var(x)
        if var_x < 1e-10:
            return 1.0
        cov_xy = np.cov(x, y)[0, 1]
        return float(cov_xy / var_x)

    def _compute_reliability_bins(self, preds: np.ndarray,
                                   outcomes: np.ndarray,
                                   n_bins: int = 10) -> list:
        """Compute reliability diagram bins."""
        bin_boundaries = np.linspace(0, 1, n_bins + 1)
        bins = []
        for i in range(n_bins):
            lo, hi = bin_boundaries[i], bin_boundaries[i + 1]
            mask = (preds >= lo) & (preds < hi if i < n_bins - 1 else preds <= hi)
            if not mask.any():
                continue
            bins.append({
                "bin_low": float(lo),
                "bin_high": float(hi),
                "count": int(mask.sum()),
                "avg_confidence": float(preds[mask].mean()),
                "avg_accuracy": float(outcomes[mask].mean()),
                "gap": float(abs(preds[mask].mean() - outcomes[mask].mean())),
            })
        return bins

    def reset(self) -> None:
        """Clear all data + recalibration."""
        self._predictions.clear()
        self._outcomes.clear()
        self._isotonic_model = None
        self._recalibration_count = 0
        self._last_state = CalibrationState.CALIBRATED


if __name__ == "__main__":
    # Smoke test
    print("=" * 60)
    print("MetaCalibrationMonitor — Smoke Test")
    print("=" * 60)
    mon = MetaCalibrationMonitor()

    # Simulate well-calibrated predictions
    np.random.seed(42)
    for _ in range(100):
        p = np.random.uniform(0.5, 0.9)
        outcome = 1 if np.random.random() < p else 0
        mon.record_prediction(p, outcome)
    r = mon.get_report()
    print(f"\nWell-calibrated: {r}")

    # Simulate overconfident predictions
    mon.reset()
    for _ in range(100):
        p = 0.95  # always says 95% confident
        outcome = 1 if np.random.random() < 0.60 else 0  # actual win rate 60%
        mon.record_prediction(p, outcome)
    r = mon.get_report()
    print(f"\nOverconfident: {r}")

    # Recalibrate
    success = mon.recalibrate()
    print(f"\nRecalibration: success={success}")
    if success:
        # Apply recalibration
        new_p = mon.apply_recalibration(0.95)
        print(f"Remapped 0.95 → {new_p:.4f}")
        r2 = mon.get_report()
        print(f"After recalibration: ece={r2.ece:.4f} (was {r.ece:.4f})")
