"""
TITAN XAU AI - Auto Calibration Governance (Sprint 9.9.3.36)
=============================================================

Governance layer for automatic calibration recommendations.

NEVER imports MetaTrader5.
NEVER sends orders.
NEVER retrains models.
NEVER auto-applies calibration.

This module produces recommendations only. The operator must review and
explicitly apply any calibration change. Auto-apply is hardcoded to False.
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class CalibrationAction(str, Enum):
    KEEP_CURRENT = "KEEP_CURRENT"
    RECOMMEND_THRESHOLD_ADJUSTMENT = "RECOMMEND_THRESHOLD_ADJUSTMENT"
    RECOMMEND_PROBABILITY_RECALIBRATION = "RECOMMEND_PROBABILITY_RECALIBRATION"
    BLOCK_CALIBRATION = "BLOCK_CALIBRATION"
    NEEDS_REVIEW = "NEEDS_REVIEW"


# Conservative thresholds
MIN_CALIBRATION_SAMPLES = 500
BRIER_BLOCK_THRESHOLD = 0.35
BRIER_WARN_THRESHOLD = 0.25
ECE_BLOCK_THRESHOLD = 0.20
ECE_WARN_THRESHOLD = 0.10
THRESHOLD_ADJUSTMENT_DELTA = 0.05  # never recommend more than 5% adjustment


@dataclass
class CalibrationGovernanceResult:
    action: CalibrationAction
    current_threshold: Optional[float]
    recommended_threshold: Optional[float]
    calibration_score: Optional[float]
    brier_score: Optional[float]
    expected_calibration_error: Optional[float]
    sample_count: int
    reasons: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    apply_automatically: bool = False
    timestamp_utc: str = ""

    def __post_init__(self):
        if not self.timestamp_utc:
            self.timestamp_utc = datetime.now(timezone.utc).isoformat()
        # Auto-apply is FORBIDDEN. Always force False regardless of input.
        self.apply_automatically = False

    def to_dict(self) -> dict:
        d = asdict(self)
        d["action"] = self.action.value
        return d


class AutoCalibrationGovernance:
    """Governance layer for calibration recommendations.

    Never auto-applies. Never imports MT5. Never sends orders.
    """

    def __init__(self, live_mode: bool = False):
        # live_mode=True blocks ALL calibration recommendations.
        self.live_mode = live_mode
        self._last_result: Optional[CalibrationGovernanceResult] = None

    # ──────────────────────────────────────────────────────────────────────
    # Top-level evaluation
    # ──────────────────────────────────────────────────────────────────────

    def evaluate_calibration(self, metrics: dict) -> CalibrationGovernanceResult:
        """Evaluate calibration metrics and produce a governance result.

        Never auto-applies. Returns a recommendation only.
        """
        reasons: list[str] = []
        blockers: list[str] = []
        warnings: list[str] = []

        sample_count = int(metrics.get("sample_count", 0))
        brier = metrics.get("brier_score")
        ece = metrics.get("expected_calibration_error")
        current_threshold = metrics.get("current_threshold")
        calibration_score = metrics.get("calibration_score")

        # 1) Live mode blocks ALL calibration
        if self.live_mode or metrics.get("live_mode", False):
            blockers.append("Calibration application blocked: live mode active")
            result = CalibrationGovernanceResult(
                action=CalibrationAction.BLOCK_CALIBRATION,
                current_threshold=current_threshold,
                recommended_threshold=None,
                calibration_score=calibration_score,
                brier_score=brier,
                expected_calibration_error=ece,
                sample_count=sample_count,
                reasons=["Live mode active - calibration cannot be applied"],
                blockers=blockers,
                warnings=warnings,
                apply_automatically=False,
            )
            self._last_result = result
            return result

        # 2) Insufficient samples blocks recommendation
        ok_samples, sample_blockers = self.block_if_insufficient_samples(sample_count)
        if not ok_samples:
            blockers.extend(sample_blockers)

        # 3) Brier / ECE checks
        if brier is not None:
            if brier > BRIER_BLOCK_THRESHOLD:
                blockers.append(f"Brier score {brier:.3f} exceeds block threshold {BRIER_BLOCK_THRESHOLD}")
            elif brier > BRIER_WARN_THRESHOLD:
                warnings.append(f"Brier score elevated: {brier:.3f}")
        else:
            blockers.append("Missing brier_score")

        if ece is not None:
            if ece > ECE_BLOCK_THRESHOLD:
                blockers.append(f"ECE {ece:.3f} exceeds block threshold {ECE_BLOCK_THRESHOLD}")
            elif ece > ECE_WARN_THRESHOLD:
                warnings.append(f"ECE elevated: {ece:.3f}")
        else:
            blockers.append("Missing expected_calibration_error")

        # 4) Determine action
        if blockers:
            action = CalibrationAction.BLOCK_CALIBRATION
            reasons.append("Calibration blocked by governance gates")
        elif warnings:
            action = CalibrationAction.NEEDS_REVIEW
            reasons.append("Calibration has warnings - operator review required")
        elif brier is not None and ece is not None and brier < BRIER_WARN_THRESHOLD and ece < ECE_WARN_THRESHOLD:
            action = CalibrationAction.KEEP_CURRENT
            reasons.append("Calibration within acceptable range - keep current")
        else:
            action = CalibrationAction.NEEDS_REVIEW
            reasons.append("Calibration state unclear - operator review required")

        # 5) Optional threshold recommendation (non-binding)
        recommended_threshold = None
        if action not in (CalibrationAction.BLOCK_CALIBRATION,) and current_threshold is not None:
            recommended_threshold = self.recommend_threshold(metrics)
            if recommended_threshold is not None and current_threshold is not None:
                delta = abs(recommended_threshold - current_threshold)
                if delta > THRESHOLD_ADJUSTMENT_DELTA:
                    warnings.append(
                        f"Recommended threshold delta {delta:.3f} exceeds safe bound {THRESHOLD_ADJUSTMENT_DELTA} - clamped"
                    )
                    # Clamp the recommendation to the safe delta
                    if recommended_threshold > current_threshold:
                        recommended_threshold = current_threshold + THRESHOLD_ADJUSTMENT_DELTA
                    else:
                        recommended_threshold = current_threshold - THRESHOLD_ADJUSTMENT_DELTA

        result = CalibrationGovernanceResult(
            action=action,
            current_threshold=current_threshold,
            recommended_threshold=recommended_threshold,
            calibration_score=calibration_score,
            brier_score=brier,
            expected_calibration_error=ece,
            sample_count=sample_count,
            reasons=reasons,
            blockers=blockers,
            warnings=warnings,
            apply_automatically=False,
        )
        self._last_result = result
        return result

    # ──────────────────────────────────────────────────────────────────────
    # Individual validators
    # ──────────────────────────────────────────────────────────────────────

    def recommend_threshold(self, metrics: dict) -> Optional[float]:
        """Recommend a threshold based on calibration metrics.

        Returns a recommended threshold value, or None if no recommendation.
        Recommendation is non-binding - operator must explicitly apply.
        """
        current = metrics.get("current_threshold")
        brier = metrics.get("brier_score")
        ece = metrics.get("expected_calibration_error")
        if current is None:
            return None
        # Conservative rule: if model is over-confident (low brier but high ECE),
        # nudge threshold up slightly. If under-confident, nudge down.
        if brier is None or ece is None:
            return None
        if ece > ECE_WARN_THRESHOLD and brier < BRIER_WARN_THRESHOLD:
            # Over-confident - raise threshold
            return float(current) + 0.02
        if ece < ECE_WARN_THRESHOLD and brier > BRIER_WARN_THRESHOLD:
            # Under-confident - lower threshold
            return float(current) - 0.02
        return float(current)

    def block_if_insufficient_samples(self, sample_count: int) -> tuple[bool, list[str]]:
        """Block calibration if sample count is too low."""
        blockers: list[str] = []
        if sample_count < MIN_CALIBRATION_SAMPLES:
            blockers.append(
                f"Insufficient calibration samples: {sample_count} < {MIN_CALIBRATION_SAMPLES}"
            )
            return False, blockers
        return True, blockers

    def block_if_live_mode(self) -> tuple[bool, list[str]]:
        """Block calibration if live mode is active."""
        if self.live_mode:
            return False, ["Calibration blocked: live mode active"]
        return True, []

    # ──────────────────────────────────────────────────────────────────────
    # Safety helpers
    # ──────────────────────────────────────────────────────────────────────

    def enforce_no_auto_apply(self) -> bool:
        """Always returns False. Auto-apply is forbidden."""
        return False

    def summary(self) -> dict:
        """Return a summary of the last result."""
        if self._last_result is None:
            return {"verdict": "NO_RESULT", "message": "No evaluation has been run yet"}
        r = self._last_result
        return {
            "action": r.action.value,
            "apply_automatically": r.apply_automatically,  # always False
            "blocker_count": len(r.blockers),
            "warning_count": len(r.warnings),
            "sample_count": r.sample_count,
            "live_mode": self.live_mode,
        }
