"""
TITAN XAU AI — Drift Monitor (Production Sprint 4)

Monitors model drift WITHOUT retraining. Tracks:
  - PSI (Population Stability Index) — feature distribution drift
  - ECE (Expected Calibration Error) — confidence reliability
  - Brier score — prediction accuracy
  - Win-rate drift — actual vs expected trade outcomes
  - Confidence drift — average confidence over time

Monitoring only. No retraining. Outputs alerts when thresholds breach.

Usage:
    mon = DriftMonitor()
    mon.record_prediction(prob_up=0.75, actual_outcome=1, features=np.array(...))
    report = mon.get_report()
    if report.drift_breach:
        # notify operator / trigger caution
        ...
"""
from __future__ import annotations

import collections
import logging
import math
import time
from dataclasses import dataclass, field
from typing import Optional, Deque

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class DriftConfig:
    """Drift thresholds."""
    window_size: int = 200                  # rolling window for predictions
    psi_caution: float = 0.10               # PSI > 0.10 → caution
    psi_emergency: float = 0.25             # PSI > 0.25 → emergency
    ece_caution: float = 0.08               # ECE > 0.08 → caution
    ece_emergency: float = 0.12             # ECE > 0.12 → emergency
    brier_caution: float = 0.22             # Brier > 0.22 → caution
    brier_emergency: float = 0.28           # Brier > 0.28 → emergency
    winrate_drift_caution: float = 0.10     # |actual - expected| > 10% → caution
    winrate_drift_emergency: float = 0.20   # > 20% → emergency
    confidence_drift_caution: float = 0.10  # |current - baseline| > 0.10 → caution
    n_bins: int = 10                        # bins for PSI + ECE computation


@dataclass
class PredictionRecord:
    """Single prediction record."""
    timestamp: float
    prob_up: float                  # predicted probability of UP
    actual_outcome: int             # 1 = UP, 0 = DOWN
    confidence: float               # max(prob_up, 1-prob_up)
    feature_hash: Optional[str] = None  # for PSI


@dataclass
class DriftReport:
    """Drift monitoring report."""
    timestamp: float
    n_predictions: int = 0
    psi: float = 0.0
    ece: float = 0.0
    brier: float = 0.0
    win_rate_actual: float = 0.0
    win_rate_expected: float = 0.0
    win_rate_drift: float = 0.0
    mean_confidence: float = 0.0
    confidence_drift: float = 0.0
    drift_breach: bool = False       # caution-level breach
    drift_emergency: bool = False    # emergency-level breach
    reasons: list[str] = field(default_factory=list)

    def __repr__(self) -> str:
        return (
            f"DriftReport(n={self.n_predictions}, psi={self.psi:.4f}, "
            f"ece={self.ece:.4f}, brier={self.brier:.4f}, "
            f"wr_drift={self.win_rate_drift:.4f}, "
            f"breach={self.drift_breach}, emergency={self.drift_emergency})"
        )


class DriftMonitor:
    """
    Rolling drift monitor. Monitoring only — does NOT retrain.

    Safety: if record_prediction() or get_report() raises,
    drift_emergency is set to True (fail-safe).
    """

    def __init__(
        self,
        config: Optional[DriftConfig] = None,
        baseline_features: Optional[np.ndarray] = None,
    ):
        self.config = config or DriftConfig()
        self._predictions: Deque[PredictionRecord] = collections.deque(
            maxlen=self.config.window_size
        )
        self._baseline_features = baseline_features
        self._current_features: list[np.ndarray] = []
        self._baseline_confidence: Optional[float] = None
        self._error_state = False
        self._error_reason = ""
        logger.info(f"DriftMonitor initialized: window={self.config.window_size}")

    # ─── Public API ─────────────────────────────────────────────────────

    def set_baseline_features(self, features: np.ndarray) -> None:
        """Set baseline feature distribution (training-time reference)."""
        self._baseline_features = features.copy()
        logger.info(f"Baseline features set: shape={features.shape}")

    def set_baseline_confidence(self, confidence: float) -> None:
        """Set baseline average confidence (from training/backtest)."""
        self._baseline_confidence = confidence
        logger.info(f"Baseline confidence set: {confidence:.4f}")

    def record_prediction(
        self,
        prob_up: float,
        actual_outcome: int,
        confidence: Optional[float] = None,
        features: Optional[np.ndarray] = None,
        timestamp: Optional[float] = None,
    ) -> PredictionRecord:
        """Record a single prediction + outcome."""
        try:
            ts = timestamp or time.time()
            conf = confidence if confidence is not None else max(prob_up, 1 - prob_up)
            record = PredictionRecord(
                timestamp=ts,
                prob_up=float(prob_up),
                actual_outcome=int(actual_outcome),
                confidence=float(conf),
            )
            self._predictions.append(record)
            if features is not None:
                self._current_features.append(features.copy())
                # Keep only last window_size
                if len(self._current_features) > self.config.window_size:
                    self._current_features = self._current_features[-self.config.window_size:]
            return record
        except Exception as e:
            logger.error(f"DriftMonitor record error (fail-safe): {e}")
            self._error_state = True
            self._error_reason = f"record_error: {e}"
            return PredictionRecord(
                timestamp=timestamp or time.time(),
                prob_up=prob_up,
                actual_outcome=actual_outcome,
                confidence=confidence or 0.5,
            )

    def get_report(self) -> DriftReport:
        """Compute current drift report."""
        try:
            if not self._predictions:
                return DriftReport(timestamp=time.time())

            preds = list(self._predictions)
            n = len(preds)

            # ── Brier score: mean((prob - outcome)^2) ──
            brier = sum((p.prob_up - p.actual_outcome) ** 2 for p in preds) / n

            # ── ECE (Expected Calibration Error) ──
            ece = self._compute_ece(preds)

            # ── Win rate drift ──
            actual_wr = sum(p.actual_outcome for p in preds) / n
            expected_wr = sum(p.confidence for p in preds) / n
            wr_drift = abs(actual_wr - expected_wr)

            # ── Confidence drift ──
            mean_conf = sum(p.confidence for p in preds) / n
            conf_drift = 0.0
            if self._baseline_confidence is not None:
                conf_drift = abs(mean_conf - self._baseline_confidence)

            # ── PSI (if features available) ──
            psi = 0.0
            if self._baseline_features is not None and self._current_features:
                psi = self._compute_psi()

            # ── Determine breach level ──
            reasons = []
            breach = False
            emergency = self._error_state

            if self._error_state:
                reasons.append(self._error_reason)

            # PSI checks
            if psi >= self.config.psi_emergency:
                emergency = True
                reasons.append(f"psi_emergency ({psi:.4f})")
            elif psi >= self.config.psi_caution:
                breach = True
                reasons.append(f"psi_caution ({psi:.4f})")

            # ECE checks
            if ece >= self.config.ece_emergency:
                emergency = True
                reasons.append(f"ece_emergency ({ece:.4f})")
            elif ece >= self.config.ece_caution:
                breach = True
                reasons.append(f"ece_caution ({ece:.4f})")

            # Brier checks
            if brier >= self.config.brier_emergency:
                emergency = True
                reasons.append(f"brier_emergency ({brier:.4f})")
            elif brier >= self.config.brier_caution:
                breach = True
                reasons.append(f"brier_caution ({brier:.4f})")

            # Win rate drift checks
            if wr_drift >= self.config.winrate_drift_emergency:
                emergency = True
                reasons.append(f"wr_drift_emergency ({wr_drift:.4f})")
            elif wr_drift >= self.config.winrate_drift_caution:
                breach = True
                reasons.append(f"wr_drift_caution ({wr_drift:.4f})")

            # Confidence drift checks
            if conf_drift >= self.config.confidence_drift_caution:
                breach = True
                reasons.append(f"conf_drift_caution ({conf_drift:.4f})")

            return DriftReport(
                timestamp=time.time(),
                n_predictions=n,
                psi=psi,
                ece=ece,
                brier=brier,
                win_rate_actual=actual_wr,
                win_rate_expected=expected_wr,
                win_rate_drift=wr_drift,
                mean_confidence=mean_conf,
                confidence_drift=conf_drift,
                drift_breach=breach,
                drift_emergency=emergency,
                reasons=reasons,
            )
        except Exception as e:
            logger.error(f"DriftMonitor report error (fail-safe): {e}")
            return DriftReport(
                timestamp=time.time(),
                drift_breach=True,
                drift_emergency=True,
                reasons=[f"report_error: {e}"],
            )

    def reset(self) -> None:
        """Clear all records."""
        self._predictions.clear()
        self._current_features.clear()
        self._error_state = False
        self._error_reason = ""

    @property
    def prediction_count(self) -> int:
        return len(self._predictions)

    # ─── Internal ───────────────────────────────────────────────────────

    def _compute_ece(self, preds: list[PredictionRecord]) -> float:
        """Expected Calibration Error (binned)."""
        n_bins = self.config.n_bins
        bin_boundaries = np.linspace(0.5, 1.0, n_bins + 1)
        ece = 0.0
        n = len(preds)
        for i in range(n_bins):
            lo, hi = bin_boundaries[i], bin_boundaries[i + 1]
            # Predictions where confidence falls in this bin
            in_bin = [p for p in preds if lo <= p.confidence < hi or (i == n_bins - 1 and p.confidence == hi)]
            if not in_bin:
                continue
            bin_size = len(in_bin)
            avg_conf = sum(p.confidence for p in in_bin) / bin_size
            avg_acc = sum(p.actual_outcome for p in in_bin) / bin_size
            ece += (bin_size / n) * abs(avg_conf - avg_acc)
        return ece

    def _compute_psi(self) -> float:
        """
        Population Stability Index between baseline and current feature distributions.
        PSI = sum((p_i - q_i) * ln(p_i / q_i))
        Uses first feature column for simplicity (extendable to all features).
        """
        if self._baseline_features is None or not self._current_features:
            return 0.0
        try:
            # Use first column of features (or mean if multi-dim)
            baseline_vals = self._baseline_features.flatten() if hasattr(self._baseline_features, 'flatten') else np.array(self._baseline_features)
            current_vals = np.array([f.flatten() if hasattr(f, 'flatten') else np.array(f) for f in self._current_features])
            if current_vals.ndim > 1:
                current_vals = current_vals.mean(axis=1)  # collapse to 1D
            if baseline_vals.ndim > 1:
                baseline_vals = baseline_vals.mean(axis=1) if baseline_vals.size > 1 else baseline_vals.flatten()

            # Bin into 10 quantiles based on baseline
            n_bins = self.config.n_bins
            quantiles = np.linspace(0, 1, n_bins + 1)
            bin_edges = np.quantile(baseline_vals, quantiles)
            bin_edges[0] = -np.inf
            bin_edges[-1] = np.inf

            # Count baseline and current in each bin
            baseline_counts, _ = np.histogram(baseline_vals, bins=bin_edges)
            current_counts, _ = np.histogram(current_vals, bins=bin_edges)

            # Convert to proportions (with smoothing to avoid div-by-zero)
            baseline_pct = (baseline_counts + 1) / (len(baseline_vals) + n_bins)
            current_pct = (current_counts + 1) / (len(current_vals) + n_bins)

            # PSI = sum((p - q) * ln(p / q))
            psi = sum((c - b) * math.log(c / b) for b, c in zip(baseline_pct, current_pct))
            return float(psi)
        except Exception as e:
            logger.warning(f"PSI computation failed: {e}")
            return 0.0


if __name__ == "__main__":
    # Smoke test
    print("=" * 70)
    print("TITAN DriftMonitor — Smoke Test")
    print("=" * 70)
    mon = DriftMonitor()
    mon.set_baseline_confidence(0.75)

    # Record well-calibrated predictions
    import random
    random.seed(42)
    for _ in range(100):
        outcome = random.choice([0, 1])
        prob = 0.75 if outcome == 1 else 0.25
        mon.record_prediction(prob_up=prob, actual_outcome=outcome)
    print(f"\nAfter 100 calibrated predictions:")
    print(f"  {mon.get_report()}")

    # Record drifted predictions (overconfident)
    for _ in range(100):
        outcome = random.choice([0, 1])
        prob = 0.95  # overconfident
        mon.record_prediction(prob_up=prob, actual_outcome=outcome)
    print(f"\nAfter 100 overconfident predictions:")
    print(f"  {mon.get_report()}")
