"""
TITAN XAU AI - Retraining Trigger Monitor (Sprint 9.9.3.37)
============================================================

Monitors runtime metrics and recommends retraining triggers.

NEVER imports MetaTrader5.
NEVER sends orders.
NEVER launches training automatically.
NEVER modifies runtime config.

The monitor only RECOMMENDS. Actual retraining requires explicit operator
approval and submission through OfflineRetrainingPipeline + ModelRegistry.
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from titan.production.offline_retraining_pipeline import RetrainingTrigger


class TriggerSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class TriggerRecommendation(str, Enum):
    NO_ACTION = "NO_ACTION"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    RECOMMEND_RETRAINING = "RECOMMEND_RETRAINING"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


@dataclass
class RetrainingTriggerSignal:
    trigger: RetrainingTrigger
    severity: TriggerSeverity
    reason: str
    metrics: dict = field(default_factory=dict)
    recommended: TriggerRecommendation = TriggerRecommendation.NEEDS_REVIEW
    timestamp_utc: str = ""

    def __post_init__(self):
        if not self.timestamp_utc:
            self.timestamp_utc = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        d = asdict(self)
        d["trigger"] = self.trigger.value
        d["severity"] = self.severity.value
        d["recommended"] = self.recommended.value
        return d


# Conservative thresholds
PERFORMANCE_DECAY_SHARPE_DROP = 0.30   # 30% drop from baseline
CALIBRATION_DRIFT_BRIER_DELTA = 0.05   # brier increased by 0.05
REGIME_SHIFT_CONFIDENCE = 0.70          # 70% confidence regime changed
BROKER_DEGRADATION_WINRATE_DROP = 0.10  # 10% winrate drop
MIN_SAMPLE_COUNT_FOR_TRIGGER = 100      # below this, INSUFFICIENT_DATA


class RetrainingTriggerMonitor:
    """Monitors metrics and recommends retraining triggers.

    Never launches training. Never modifies runtime config. Never imports MT5.
    """

    def __init__(self):
        self._last_signals: list[RetrainingTriggerSignal] = []

    # ──────────────────────────────────────────────────────────────────────
    # Individual evaluators
    # ──────────────────────────────────────────────────────────────────────

    def evaluate_performance_decay(self, metrics: dict) -> RetrainingTriggerSignal:
        """Evaluate performance decay. Recommends NEEDS_REVIEW at most.

        Performance decay = current sharpe significantly below baseline.
        """
        current_sharpe = metrics.get("current_sharpe")
        baseline_sharpe = metrics.get("baseline_sharpe")
        sample_count = metrics.get("sample_count", 0)

        if current_sharpe is None or baseline_sharpe is None:
            return self._insufficient_data_signal(
                RetrainingTrigger.PERFORMANCE_DECAY,
                "Missing current_sharpe or baseline_sharpe",
                metrics,
            )
        if sample_count < MIN_SAMPLE_COUNT_FOR_TRIGGER:
            return self._insufficient_data_signal(
                RetrainingTrigger.PERFORMANCE_DECAY,
                f"Insufficient samples: {sample_count} < {MIN_SAMPLE_COUNT_FOR_TRIGGER}",
                metrics,
            )
        if baseline_sharpe <= 0:
            return self._insufficient_data_signal(
                RetrainingTrigger.PERFORMANCE_DECAY,
                f"Invalid baseline_sharpe: {baseline_sharpe}",
                metrics,
            )

        drop_ratio = (baseline_sharpe - current_sharpe) / baseline_sharpe
        if drop_ratio >= PERFORMANCE_DECAY_SHARPE_DROP:
            severity = TriggerSeverity.CRITICAL
            recommended = TriggerRecommendation.NEEDS_REVIEW
            reason = (
                f"Performance decay detected: current_sharpe={current_sharpe:.3f} "
                f"baseline_sharpe={baseline_sharpe:.3f} drop={drop_ratio:.1%}"
            )
        elif drop_ratio > 0:
            severity = TriggerSeverity.WARNING
            recommended = TriggerRecommendation.NEEDS_REVIEW
            reason = (
                f"Minor performance decay: current_sharpe={current_sharpe:.3f} "
                f"baseline_sharpe={baseline_sharpe:.3f} drop={drop_ratio:.1%}"
            )
        else:
            severity = TriggerSeverity.INFO
            recommended = TriggerRecommendation.NO_ACTION
            reason = (
                f"No performance decay: current_sharpe={current_sharpe:.3f} "
                f"baseline_sharpe={baseline_sharpe:.3f}"
            )

        signal = RetrainingTriggerSignal(
            trigger=RetrainingTrigger.PERFORMANCE_DECAY,
            severity=severity,
            reason=reason,
            metrics=metrics,
            recommended=recommended,
        )
        self._last_signals.append(signal)
        return signal

    def evaluate_calibration_drift(self, metrics: dict) -> RetrainingTriggerSignal:
        """Evaluate calibration drift. Recommends NEEDS_REVIEW at most."""
        current_brier = metrics.get("current_brier")
        baseline_brier = metrics.get("baseline_brier")
        sample_count = metrics.get("sample_count", 0)

        if current_brier is None or baseline_brier is None:
            return self._insufficient_data_signal(
                RetrainingTrigger.CALIBRATION_DRIFT,
                "Missing current_brier or baseline_brier",
                metrics,
            )
        if sample_count < MIN_SAMPLE_COUNT_FOR_TRIGGER:
            return self._insufficient_data_signal(
                RetrainingTrigger.CALIBRATION_DRIFT,
                f"Insufficient samples: {sample_count} < {MIN_SAMPLE_COUNT_FOR_TRIGGER}",
                metrics,
            )

        delta = current_brier - baseline_brier
        if delta >= CALIBRATION_DRIFT_BRIER_DELTA:
            severity = TriggerSeverity.CRITICAL
            recommended = TriggerRecommendation.NEEDS_REVIEW
            reason = (
                f"Calibration drift detected: current_brier={current_brier:.3f} "
                f"baseline_brier={baseline_brier:.3f} delta=+{delta:.3f}"
            )
        elif delta > 0:
            severity = TriggerSeverity.WARNING
            recommended = TriggerRecommendation.NEEDS_REVIEW
            reason = (
                f"Minor calibration drift: current_brier={current_brier:.3f} "
                f"baseline_brier={baseline_brier:.3f} delta=+{delta:.3f}"
            )
        else:
            severity = TriggerSeverity.INFO
            recommended = TriggerRecommendation.NO_ACTION
            reason = (
                f"No calibration drift: current_brier={current_brier:.3f} "
                f"baseline_brier={baseline_brier:.3f}"
            )

        signal = RetrainingTriggerSignal(
            trigger=RetrainingTrigger.CALIBRATION_DRIFT,
            severity=severity,
            reason=reason,
            metrics=metrics,
            recommended=recommended,
        )
        self._last_signals.append(signal)
        return signal

    def evaluate_regime_shift(self, metrics: dict) -> RetrainingTriggerSignal:
        """Evaluate regime shift. Recommends NEEDS_REVIEW at most."""
        regime_confidence = metrics.get("regime_shift_confidence")
        sample_count = metrics.get("sample_count", 0)

        if regime_confidence is None:
            return self._insufficient_data_signal(
                RetrainingTrigger.REGIME_SHIFT,
                "Missing regime_shift_confidence",
                metrics,
            )
        if sample_count < MIN_SAMPLE_COUNT_FOR_TRIGGER:
            return self._insufficient_data_signal(
                RetrainingTrigger.REGIME_SHIFT,
                f"Insufficient samples: {sample_count} < {MIN_SAMPLE_COUNT_FOR_TRIGGER}",
                metrics,
            )

        if regime_confidence >= REGIME_SHIFT_CONFIDENCE:
            severity = TriggerSeverity.CRITICAL
            recommended = TriggerRecommendation.NEEDS_REVIEW
            reason = (
                f"Regime shift detected: confidence={regime_confidence:.1%} "
                f"(threshold {REGIME_SHIFT_CONFIDENCE:.0%})"
            )
        elif regime_confidence > 0.5:
            severity = TriggerSeverity.WARNING
            recommended = TriggerRecommendation.NEEDS_REVIEW
            reason = f"Possible regime shift: confidence={regime_confidence:.1%}"
        else:
            severity = TriggerSeverity.INFO
            recommended = TriggerRecommendation.NO_ACTION
            reason = f"No regime shift: confidence={regime_confidence:.1%}"

        signal = RetrainingTriggerSignal(
            trigger=RetrainingTrigger.REGIME_SHIFT,
            severity=severity,
            reason=reason,
            metrics=metrics,
            recommended=recommended,
        )
        self._last_signals.append(signal)
        return signal

    def evaluate_broker_degradation(self, metrics: dict) -> RetrainingTriggerSignal:
        """Evaluate broker degradation. Recommends NEEDS_REVIEW at most."""
        current_winrate = metrics.get("current_winrate")
        baseline_winrate = metrics.get("baseline_winrate")
        sample_count = metrics.get("sample_count", 0)

        if current_winrate is None or baseline_winrate is None:
            return self._insufficient_data_signal(
                RetrainingTrigger.BROKER_DEGRADATION,
                "Missing current_winrate or baseline_winrate",
                metrics,
            )
        if sample_count < MIN_SAMPLE_COUNT_FOR_TRIGGER:
            return self._insufficient_data_signal(
                RetrainingTrigger.BROKER_DEGRADATION,
                f"Insufficient samples: {sample_count} < {MIN_SAMPLE_COUNT_FOR_TRIGGER}",
                metrics,
            )

        drop = baseline_winrate - current_winrate
        if drop >= BROKER_DEGRADATION_WINRATE_DROP:
            severity = TriggerSeverity.CRITICAL
            recommended = TriggerRecommendation.NEEDS_REVIEW
            reason = (
                f"Broker degradation detected: current_winrate={current_winrate:.1%} "
                f"baseline_winrate={baseline_winrate:.1%} drop={drop:.1%}"
            )
        elif drop > 0:
            severity = TriggerSeverity.WARNING
            recommended = TriggerRecommendation.NEEDS_REVIEW
            reason = (
                f"Minor broker degradation: current_winrate={current_winrate:.1%} "
                f"baseline_winrate={baseline_winrate:.1%} drop={drop:.1%}"
            )
        else:
            severity = TriggerSeverity.INFO
            recommended = TriggerRecommendation.NO_ACTION
            reason = (
                f"No broker degradation: current_winrate={current_winrate:.1%} "
                f"baseline_winrate={baseline_winrate:.1%}"
            )

        signal = RetrainingTriggerSignal(
            trigger=RetrainingTrigger.BROKER_DEGRADATION,
            severity=severity,
            reason=reason,
            metrics=metrics,
            recommended=recommended,
        )
        self._last_signals.append(signal)
        return signal

    def evaluate_schedule_due(self, metrics: dict) -> RetrainingTriggerSignal:
        """Evaluate scheduled retraining. Recommends NEEDS_REVIEW at most."""
        days_since_last = metrics.get("days_since_last_retraining")
        schedule_interval_days = metrics.get("schedule_interval_days", 90)

        if days_since_last is None:
            return self._insufficient_data_signal(
                RetrainingTrigger.SCHEDULED,
                "Missing days_since_last_retraining",
                metrics,
            )

        if days_since_last >= schedule_interval_days:
            severity = TriggerSeverity.INFO
            recommended = TriggerRecommendation.NEEDS_REVIEW
            reason = (
                f"Scheduled retraining due: {days_since_last} days since last "
                f"(interval={schedule_interval_days})"
            )
        else:
            severity = TriggerSeverity.INFO
            recommended = TriggerRecommendation.NO_ACTION
            reason = (
                f"Scheduled retraining not due: {days_since_last} days since last "
                f"(interval={schedule_interval_days})"
            )

        signal = RetrainingTriggerSignal(
            trigger=RetrainingTrigger.SCHEDULED,
            severity=severity,
            reason=reason,
            metrics=metrics,
            recommended=recommended,
        )
        self._last_signals.append(signal)
        return signal

    # ──────────────────────────────────────────────────────────────────────
    # Aggregated recommendation
    # ──────────────────────────────────────────────────────────────────────

    def recommend_trigger(self, metrics: dict) -> RetrainingTriggerSignal:
        """Aggregate all evaluations and produce a single recommendation.

        Returns the most severe signal. Default is NEEDS_REVIEW when any
        signal is non-INFO; otherwise NO_ACTION.
        """
        signals = [
            self.evaluate_performance_decay(metrics),
            self.evaluate_calibration_drift(metrics),
            self.evaluate_regime_shift(metrics),
            self.evaluate_broker_degradation(metrics),
            self.evaluate_schedule_due(metrics),
        ]
        # Pick the most severe
        severity_order = {
            TriggerSeverity.INFO: 0,
            TriggerSeverity.WARNING: 1,
            TriggerSeverity.CRITICAL: 2,
        }
        # Filter out INSUFFICIENT_DATA signals - they should not trigger retraining
        valid_signals = [s for s in signals if s.recommended != TriggerRecommendation.INSUFFICIENT_DATA]
        if not valid_signals:
            signal = RetrainingTriggerSignal(
                trigger=RetrainingTrigger.MANUAL_OPERATOR_REQUEST,
                severity=TriggerSeverity.INFO,
                reason="All evaluators returned INSUFFICIENT_DATA - no trigger",
                metrics=metrics,
                recommended=TriggerRecommendation.INSUFFICIENT_DATA,
            )
            self._last_signals.append(signal)
            return signal

        most_severe = max(valid_signals, key=lambda s: severity_order.get(s.severity, 0))
        # Cap recommendation at NEEDS_REVIEW - never auto-recommend retraining
        if most_severe.recommended == TriggerRecommendation.RECOMMEND_RETRAINING:
            most_severe.recommended = TriggerRecommendation.NEEDS_REVIEW
        self._last_signals.append(most_severe)
        return most_severe

    # ──────────────────────────────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────────────────────────────

    def _insufficient_data_signal(
        self, trigger: RetrainingTrigger, reason: str, metrics: dict
    ) -> RetrainingTriggerSignal:
        signal = RetrainingTriggerSignal(
            trigger=trigger,
            severity=TriggerSeverity.INFO,
            reason=reason,
            metrics=metrics,
            recommended=TriggerRecommendation.INSUFFICIENT_DATA,
        )
        self._last_signals.append(signal)
        return signal

    def summary(self) -> dict:
        return {
            "total_signals": len(self._last_signals),
            "auto_launches_training": False,
            "default_recommendation": TriggerRecommendation.NEEDS_REVIEW.value,
            "insufficient_data_treatment": "no trigger / warning only",
        }
