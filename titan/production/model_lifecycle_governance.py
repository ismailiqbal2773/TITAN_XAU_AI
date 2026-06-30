"""
TITAN XAU AI - Model Lifecycle Governance (Sprint 9.9.3.36)
============================================================

Institutional governance for the champion/challenger/candidate model lifecycle.

NEVER imports MetaTrader5.
NEVER sends orders.
NEVER retrains models.
NEVER replaces the champion model automatically.
NEVER deploys a model.

This module is a governance foundation only. Every promotion must be explicit
and require operator approval. Auto-promotion is hardcoded to False.
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class ModelLifecycleStage(str, Enum):
    CHAMPION = "CHAMPION"
    CHALLENGER = "CHALLENGER"
    CANDIDATE = "CANDIDATE"
    SHADOW = "SHADOW"
    REJECTED = "REJECTED"
    RETIRED = "RETIRED"
    QUARANTINED = "QUARANTINED"


class ModelApprovalStatus(str, Enum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    BLOCKED = "BLOCKED"
    PENDING = "PENDING"


# Minimum required metric keys for any candidate evaluation.
REQUIRED_METRIC_KEYS = (
    "oos_sharpe",            # out-of-sample sharpe
    "oos_max_drawdown",      # out-of-sample max drawdown (positive number = loss)
    "walk_forward_sharpe",   # walk-forward aggregated sharpe
    "broker_split_status",   # "PASS" / "FAIL" / "PENDING"
    "calibration_brier",     # brier score
    "calibration_ece",       # expected calibration error
)

# Thresholds (conservative defaults).
MIN_SAMPLE_COUNT = 200
MAX_DRAWDOWN_TOLERANCE = 0.02   # candidate may have up to 2% worse drawdown before NEEDS_REVIEW
MAX_DRAWDOWN_BLOCK = 0.05       # >5% worse drawdown -> BLOCKED
LEAKAGE_QUARANTINE = True


@dataclass
class ModelLifecycleDecision:
    model_id: str
    current_stage: ModelLifecycleStage
    proposed_stage: ModelLifecycleStage
    approval_status: ModelApprovalStatus
    reasons: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metrics_snapshot: dict = field(default_factory=dict)
    timestamp_utc: str = ""
    operator_approval_required: bool = True

    def __post_init__(self):
        if not self.timestamp_utc:
            self.timestamp_utc = datetime.now(timezone.utc).isoformat()
        # Auto-promotion is FORBIDDEN. Champion promotion always requires operator approval.
        if self.proposed_stage == ModelLifecycleStage.CHAMPION:
            self.operator_approval_required = True

    def to_dict(self) -> dict:
        d = asdict(self)
        d["current_stage"] = self.current_stage.value
        d["proposed_stage"] = self.proposed_stage.value
        d["approval_status"] = self.approval_status.value
        return d


class ModelLifecycleGovernance:
    """Institutional governance for champion/challenger lifecycle.

    Never auto-promotes. Never replaces the champion without operator approval.
    Never imports MetaTrader5. Never sends orders. Never retrains models.
    """

    def __init__(self):
        self._last_decision: Optional[ModelLifecycleDecision] = None
        self._quarantine_reasons: dict[str, str] = {}

    # ──────────────────────────────────────────────────────────────────────
    # Top-level evaluation
    # ──────────────────────────────────────────────────────────────────────

    def evaluate_candidate(
        self,
        candidate_metrics: dict,
        champion_metrics: Optional[dict] = None,
        model_id: str = "candidate",
    ) -> ModelLifecycleDecision:
        """Evaluate a candidate against champion metrics.

        Returns a ModelLifecycleDecision. Never auto-promotes.
        """
        reasons: list[str] = []
        blockers: list[str] = []
        warnings: list[str] = []

        # 1) Validate minimum metrics
        ok_min, min_blockers = self.validate_minimum_metrics(candidate_metrics)
        if not ok_min:
            blockers.extend(min_blockers)

        # 2) Walk-forward validation
        ok_wf, wf_blockers = self.validate_walk_forward(candidate_metrics)
        if not ok_wf:
            blockers.extend(wf_blockers)

        # 3) Broker split validation
        ok_bs, bs_blockers = self.validate_broker_split(candidate_metrics)
        if not ok_bs:
            blockers.extend(bs_blockers)

        # 4) Calibration validation
        ok_cal, cal_warnings, cal_blockers = self.validate_calibration(candidate_metrics)
        if not ok_cal:
            blockers.extend(cal_blockers)
        warnings.extend(cal_warnings)

        # 5) Shadow results validation
        ok_shadow, shadow_warnings, shadow_blockers = self.validate_shadow_results(candidate_metrics)
        if not ok_shadow:
            blockers.extend(shadow_blockers)
        warnings.extend(shadow_warnings)

        # 6) Drawdown limits
        if champion_metrics:
            ok_dd, dd_warnings, dd_blockers = self.validate_drawdown_limits(
                candidate_metrics, champion_metrics
            )
            if not ok_dd:
                blockers.extend(dd_blockers)
            warnings.extend(dd_warnings)

            # 7) Better single metric alone must not approve
            # If candidate has better sharpe but worse drawdown, that's already caught above.
            # Here we ensure a single better metric does NOT override blockers.
            if self._has_only_single_metric_improvement(candidate_metrics, champion_metrics):
                warnings.append(
                    "Candidate improves on a single metric only - multi-metric improvement required"
                )
        else:
            warnings.append("No champion metrics supplied - candidate evaluated against minimum gates only")

        # 8) Leakage quarantine
        if candidate_metrics.get("leakage_flags"):
            blockers.append(f"Leakage flags present: {candidate_metrics['leakage_flags']}")
            decision = self.quarantine(
                reason=f"Leakage flags: {candidate_metrics['leakage_flags']}",
                model_id=model_id,
                metrics_snapshot=candidate_metrics,
            )
            self._last_decision = decision
            return decision

        # Determine approval status & proposed stage
        if blockers:
            approval_status = ModelApprovalStatus.BLOCKED
            proposed_stage = ModelLifecycleStage.CANDIDATE
            reasons.append("Candidate blocked by governance gates")
        elif warnings:
            approval_status = ModelApprovalStatus.NEEDS_REVIEW
            proposed_stage = ModelLifecycleStage.CANDIDATE
            reasons.append("Candidate has warnings - operator review required")
        else:
            approval_status = ModelApprovalStatus.NEEDS_REVIEW  # never auto-approve
            proposed_stage = ModelLifecycleStage.SHADOW
            reasons.append("Candidate passed all gates - shadow validation recommended")

        decision = ModelLifecycleDecision(
            model_id=model_id,
            current_stage=ModelLifecycleStage.CANDIDATE,
            proposed_stage=proposed_stage,
            approval_status=approval_status,
            reasons=reasons,
            blockers=blockers,
            warnings=warnings,
            metrics_snapshot=dict(candidate_metrics),
            operator_approval_required=True,
        )
        self._last_decision = decision
        return decision

    # ──────────────────────────────────────────────────────────────────────
    # Individual validators
    # ──────────────────────────────────────────────────────────────────────

    def validate_minimum_metrics(self, metrics: dict) -> tuple[bool, list[str]]:
        """Confirm all required metric keys are present and non-None."""
        blockers: list[str] = []
        for k in REQUIRED_METRIC_KEYS:
            v = metrics.get(k)
            if v is None:
                blockers.append(f"Missing required metric: {k}")
        return len(blockers) == 0, blockers

    def validate_walk_forward(self, metrics: dict) -> tuple[bool, list[str]]:
        """Confirm walk-forward metrics are present and pass minimum threshold."""
        blockers: list[str] = []
        wf_sharpe = metrics.get("walk_forward_sharpe")
        wf_status = metrics.get("walk_forward_status")
        if wf_sharpe is None:
            blockers.append("Missing walk_forward_sharpe metric")
        elif wf_sharpe < 0.0:
            blockers.append(f"Walk-forward sharpe negative: {wf_sharpe}")
        if wf_status is not None and wf_status == "FAIL":
            blockers.append("Walk-forward status = FAIL")
        return len(blockers) == 0, blockers

    def validate_broker_split(self, metrics: dict) -> tuple[bool, list[str]]:
        """Confirm broker-split validation is present and PASS."""
        blockers: list[str] = []
        status = metrics.get("broker_split_status")
        if status is None:
            blockers.append("Missing broker_split_status metric")
        elif status == "FAIL":
            blockers.append("Broker split validation = FAIL")
        elif status == "PENDING":
            blockers.append("Broker split validation = PENDING (not yet run)")
        elif status != "PASS":
            blockers.append(f"Broker split status unknown: {status}")
        return len(blockers) == 0, blockers

    def validate_calibration(self, metrics: dict) -> tuple[bool, list[str], list[str]]:
        """Confirm calibration metrics are acceptable.

        Returns (ok, warnings, blockers).
        """
        warnings: list[str] = []
        blockers: list[str] = []
        brier = metrics.get("calibration_brier")
        ece = metrics.get("calibration_ece")
        if brier is None:
            blockers.append("Missing calibration_brier metric")
        elif brier > 0.35:
            blockers.append(f"Brier score too high: {brier:.3f} (>0.35)")
        elif brier > 0.25:
            warnings.append(f"Brier score elevated: {brier:.3f}")
        if ece is None:
            blockers.append("Missing calibration_ece metric")
        elif ece > 0.20:
            blockers.append(f"ECE too high: {ece:.3f} (>0.20)")
        elif ece > 0.10:
            warnings.append(f"ECE elevated: {ece:.3f}")
        ok = len(blockers) == 0
        return ok, warnings, blockers

    def validate_shadow_results(self, metrics: dict) -> tuple[bool, list[str], list[str]]:
        """Confirm shadow validation results are acceptable.

        Returns (ok, warnings, blockers).
        """
        warnings: list[str] = []
        blockers: list[str] = []
        shadow_status = metrics.get("shadow_status")
        shadow_hours = metrics.get("shadow_hours", 0)
        if shadow_status is None:
            # Shadow not yet run - warning, not blocker (candidate can still be CANDIDATE)
            warnings.append("Shadow validation not yet run - candidate remains at CANDIDATE stage")
        elif shadow_status == "FAIL":
            blockers.append("Shadow validation status = FAIL")
        elif shadow_status == "PENDING":
            warnings.append("Shadow validation still in progress")
        if shadow_hours is not None and shadow_hours < 168:
            warnings.append(
                f"Shadow validation hours ({shadow_hours}) below 168h minimum"
            )
        ok = len(blockers) == 0
        return ok, warnings, blockers

    def validate_drawdown_limits(
        self, candidate_metrics: dict, champion_metrics: dict
    ) -> tuple[bool, list[str], list[str]]:
        """Confirm candidate drawdown is not worse than champion beyond tolerance.

        Returns (ok, warnings, blockers).
        """
        warnings: list[str] = []
        blockers: list[str] = []
        c_dd = candidate_metrics.get("oos_max_drawdown")
        ch_dd = champion_metrics.get("oos_max_drawdown")
        if c_dd is None or ch_dd is None:
            warnings.append("Cannot compare drawdown - missing values")
            return True, warnings, blockers
        delta = c_dd - ch_dd  # positive = candidate worse
        if delta > MAX_DRAWDOWN_BLOCK:
            blockers.append(
                f"Candidate drawdown {c_dd:.4f} > champion {ch_dd:.4f} by {delta:.4f} (block threshold {MAX_DRAWDOWN_BLOCK})"
            )
        elif delta > MAX_DRAWDOWN_TOLERANCE:
            warnings.append(
                f"Candidate drawdown {c_dd:.4f} worse than champion {ch_dd:.4f} by {delta:.4f}"
            )
        ok = len(blockers) == 0
        return ok, warnings, blockers

    def enforce_no_auto_promotion(self) -> bool:
        """Always returns False. Auto-promotion is forbidden."""
        return False

    def quarantine(
        self,
        reason: str,
        model_id: str = "candidate",
        metrics_snapshot: Optional[dict] = None,
    ) -> ModelLifecycleDecision:
        """Quarantine a model. Used for leakage suspicion or critical issues."""
        decision = ModelLifecycleDecision(
            model_id=model_id,
            current_stage=ModelLifecycleStage.CANDIDATE,
            proposed_stage=ModelLifecycleStage.QUARANTINED,
            approval_status=ModelApprovalStatus.BLOCKED,
            reasons=[f"Quarantined: {reason}"],
            blockers=[f"Quarantine reason: {reason}"],
            warnings=[],
            metrics_snapshot=dict(metrics_snapshot or {}),
            operator_approval_required=True,
        )
        self._quarantine_reasons[model_id] = reason
        self._last_decision = decision
        return decision

    def decision_summary(self) -> dict:
        """Return a summary of the last decision."""
        if self._last_decision is None:
            return {"verdict": "NO_DECISION", "message": "No evaluation has been run yet"}
        d = self._last_decision
        return {
            "verdict": d.approval_status.value,
            "model_id": d.model_id,
            "proposed_stage": d.proposed_stage.value,
            "operator_approval_required": d.operator_approval_required,
            "blocker_count": len(d.blockers),
            "warning_count": len(d.warnings),
            "auto_promotion": False,
            "quarantined_models": dict(self._quarantine_reasons),
        }

    # ──────────────────────────────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────────────────────────────

    def _has_only_single_metric_improvement(
        self, candidate_metrics: dict, champion_metrics: dict
    ) -> bool:
        """Detect if candidate improves on exactly one of the key metrics.

        Used to prevent single-metric-driven approval.
        """
        improvements = 0
        c_sharpe = candidate_metrics.get("oos_sharpe")
        ch_sharpe = champion_metrics.get("oos_sharpe")
        if c_sharpe is not None and ch_sharpe is not None and c_sharpe > ch_sharpe:
            improvements += 1
        c_dd = candidate_metrics.get("oos_max_drawdown")
        ch_dd = champion_metrics.get("oos_max_drawdown")
        if c_dd is not None and ch_dd is not None and c_dd < ch_dd:
            improvements += 1
        c_wf = candidate_metrics.get("walk_forward_sharpe")
        ch_wf = champion_metrics.get("walk_forward_sharpe")
        if c_wf is not None and ch_wf is not None and c_wf > ch_wf:
            improvements += 1
        c_brier = candidate_metrics.get("calibration_brier")
        ch_brier = champion_metrics.get("calibration_brier")
        if c_brier is not None and ch_brier is not None and c_brier < ch_brier:
            improvements += 1
        return improvements == 1
