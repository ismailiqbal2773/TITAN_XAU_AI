"""
TITAN XAU AI - Retraining Orchestrator (Sprint 9.9.3.46)
=========================================================

End-to-end retraining workflow orchestrator. Consumes drift-detection
input, drives candidate training placeholders, runs the validation gate,
performs champion vs candidate comparison, and routes a candidate through
the institutional promotion gates (walk-forward, broker-split,
cost-adjusted, shadow mode, human/CEO approval).

NEVER imports MetaTrader5.
NEVER sends orders (no mt5.order_send anywhere in this file).
NEVER trains a model (placeholder only; .fit / train_model / retrain /
    run_hpo are forbidden in this module).
NEVER adds martingale / grid / averaging / loss-based lot multipliers.
NEVER auto-promotes a candidate to live trading. Every promotion step
    requires explicit human approval via ModelPromotionGate.

The orchestrator is a state machine. Status flow:

    DRIFT_DETECTED
        -> TRAINING_STARTED
            -> VALIDATION_PENDING
                -> SHADOW_MODE
                    -> APPROVED_FOR_DEMO
                        -> PROMOTION_PENDING_HUMAN
                            -> (PROMOTED via external manual registry call)
                            -> REJECTED

The orchestrator NEVER transitions a candidate to a live champion itself.
The final PROMOTION_PENDING_HUMAN state requires explicit human/CEO approval
to leave the orchestrator; the actual promotion is performed out-of-band
through ModelRegistry.require_manual_champion_promotion() by an operator.

Safety fields exposed on every result:
    no_martingale=True
    no_grid=True
    no_averaging=True
    auto_promote_to_live=False
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


# ──────────────────────────────────────────────────────────────────────────
# Safety invariant flags (mirrored on every public result)
# ──────────────────────────────────────────────────────────────────────────
SAFETY_INVARIANTS: dict = {
    "no_martingale": True,
    "no_grid": True,
    "no_averaging": True,
    "no_loss_based_lot_multiplier": True,
    "auto_promote_to_live": False,
}


class RetrainingOrchestratorStatus(str, Enum):
    """Lifecycle statuses for a retraining workflow run."""

    DRIFT_DETECTED = "DRIFT_DETECTED"
    TRAINING_STARTED = "TRAINING_STARTED"
    VALIDATION_PENDING = "VALIDATION_PENDING"
    SHADOW_MODE = "SHADOW_MODE"
    APPROVED_FOR_DEMO = "APPROVED_FOR_DEMO"
    PROMOTION_PENDING_HUMAN = "PROMOTION_PENDING_HUMAN"
    REJECTED = "REJECTED"


# Legal forward transitions. Promotions may never skip the human gate.
LEGAL_TRANSITIONS: dict[RetrainingOrchestratorStatus, list[RetrainingOrchestratorStatus]] = {
    RetrainingOrchestratorStatus.DRIFT_DETECTED: [
        RetrainingOrchestratorStatus.TRAINING_STARTED,
        RetrainingOrchestratorStatus.REJECTED,
    ],
    RetrainingOrchestratorStatus.TRAINING_STARTED: [
        RetrainingOrchestratorStatus.VALIDATION_PENDING,
        RetrainingOrchestratorStatus.REJECTED,
    ],
    RetrainingOrchestratorStatus.VALIDATION_PENDING: [
        RetrainingOrchestratorStatus.SHADOW_MODE,
        RetrainingOrchestratorStatus.REJECTED,
    ],
    RetrainingOrchestratorStatus.SHADOW_MODE: [
        RetrainingOrchestratorStatus.APPROVED_FOR_DEMO,
        RetrainingOrchestratorStatus.REJECTED,
    ],
    RetrainingOrchestratorStatus.APPROVED_FOR_DEMO: [
        RetrainingOrchestratorStatus.PROMOTION_PENDING_HUMAN,
        RetrainingOrchestratorStatus.REJECTED,
    ],
    RetrainingOrchestratorStatus.PROMOTION_PENDING_HUMAN: [
        RetrainingOrchestratorStatus.REJECTED,
        # PROMOTION_PENDING_HUMAN -> APPROVED_FOR_DEMO (rollback) is allowed
        RetrainingOrchestratorStatus.APPROVED_FOR_DEMO,
    ],
    RetrainingOrchestratorStatus.REJECTED: [],
}


# Minimum requirements to advance through each gate.
MIN_WALK_FORWARD_SHARPE = 0.0          # walk-forward aggregated sharpe must be positive
MIN_SHADOW_HOURS = 168                  # 7 days of shadow validation
MIN_COST_ADJUSTED_NET_PROFIT_RATIO = 0.0  # cost-adjusted returns must be non-negative
REQUIRED_VALIDATION_KEYS = (
    "walk_forward_sharpe",
    "walk_forward_status",
    "broker_split_status",
    "cost_adjusted_net_profit",
    "shadow_status",
    "shadow_hours",
)


@dataclass
class DriftDetectionInput:
    """Input payload produced by the drift monitor / trigger monitor.

    The orchestrator does NOT validate the underlying metrics; it only
    checks that drift has been flagged.
    """

    drift_detected: bool
    drift_severity: str = "INFO"           # INFO / WARNING / CRITICAL
    drift_reason: str = ""
    champion_model_id: str = ""
    drift_metrics: dict = field(default_factory=dict)
    timestamp_utc: str = ""

    def __post_init__(self):
        if not self.timestamp_utc:
            self.timestamp_utc = datetime.now(timezone.utc).isoformat()


@dataclass
class CandidateTrainingPlaceholder:
    """Metadata-only placeholder for a candidate model produced by training.

    The orchestrator NEVER executes training. This dataclass only records
    what a hypothetical training job would have produced so the validation
    gate can evaluate the candidate against the champion.
    """

    candidate_model_id: str
    champion_model_id: str
    training_job_id: str = ""
    placeholder_metrics: dict = field(default_factory=dict)
    training_executed: bool = False        # ALWAYS False - placeholder only
    notes: str = ""

    def __post_init__(self):
        # Hard safety: training is never executed by the orchestrator.
        self.training_executed = False


@dataclass
class ChampionCandidateComparison:
    """Snapshot of the champion vs candidate comparison."""

    champion_metrics: dict = field(default_factory=dict)
    candidate_metrics: dict = field(default_factory=dict)
    sharpe_delta: Optional[float] = None
    drawdown_delta: Optional[float] = None
    cost_adjusted_delta: Optional[float] = None
    candidate_better: bool = False
    reasons: list[str] = field(default_factory=list)


@dataclass
class RetrainingOrchestratorResult:
    """Result emitted by every orchestrator state transition."""

    run_id: str
    status: RetrainingOrchestratorStatus
    previous_status: Optional[RetrainingOrchestratorStatus] = None
    candidate_model_id: str = ""
    champion_model_id: str = ""
    comparison: Optional[dict] = None
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    validation_summary: dict = field(default_factory=dict)
    auto_promote_to_live: bool = False
    no_martingale: bool = True
    no_grid: bool = True
    no_averaging: bool = True
    no_loss_based_lot_multiplier: bool = True
    human_approval_required: bool = True
    timestamp_utc: str = ""

    def __post_init__(self):
        if not self.timestamp_utc:
            self.timestamp_utc = datetime.now(timezone.utc).isoformat()
        # Hard safety invariants - always forced regardless of caller input.
        self.auto_promote_to_live = False
        self.no_martingale = True
        self.no_grid = True
        self.no_averaging = True
        self.no_loss_based_lot_multiplier = True
        self.human_approval_required = True

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        if self.previous_status is not None:
            d["previous_status"] = self.previous_status.value
        else:
            d["previous_status"] = None
        return d


class RetrainingOrchestrator:
    """Orchestrates the retraining workflow from drift detection to human gate.

    NEVER auto-promotes to live. The final state is PROMOTION_PENDING_HUMAN,
    which requires explicit external human/CEO approval to leave.
    """

    def __init__(self):
        self._runs: dict[str, RetrainingOrchestratorResult] = {}
        self._status: dict[str, RetrainingOrchestratorStatus] = {}

    # ──────────────────────────────────────────────────────────────────────
    # Status helpers
    # ──────────────────────────────────────────────────────────────────────

    def get_status(self, run_id: str) -> Optional[RetrainingOrchestratorStatus]:
        return self._status.get(run_id)

    def get_result(self, run_id: str) -> Optional[RetrainingOrchestratorResult]:
        return self._runs.get(run_id)

    def _legal_transition(
        self,
        current: RetrainingOrchestratorStatus,
        target: RetrainingOrchestratorStatus,
    ) -> bool:
        return target in LEGAL_TRANSITIONS.get(current, [])

    def _record(self, result: RetrainingOrchestratorResult) -> RetrainingOrchestratorResult:
        self._runs[result.run_id] = result
        self._status[result.run_id] = result.status
        return result

    # ──────────────────────────────────────────────────────────────────────
    # Phase 1: drift detection input
    # ──────────────────────────────────────────────────────────────────────

    def ingest_drift(
        self, run_id: str, drift: DriftDetectionInput
    ) -> RetrainingOrchestratorResult:
        """Ingest drift-detection input and create a new run in DRIFT_DETECTED.

        If drift is not actually detected, the run is rejected immediately.
        """
        blockers: list[str] = []
        reasons: list[str] = []
        if not drift.drift_detected:
            blockers.append("drift_detected is False - no retraining trigger")
            result = RetrainingOrchestratorResult(
                run_id=run_id,
                status=RetrainingOrchestratorStatus.REJECTED,
                champion_model_id=drift.champion_model_id,
                blockers=blockers,
                reasons=["Drift not detected - retraining not warranted"],
            )
            return self._record(result)
        if not drift.champion_model_id:
            blockers.append("Missing champion_model_id in drift input")
        reasons.append(
            f"Drift detected (severity={drift.drift_severity}): {drift.drift_reason}"
        )
        result = RetrainingOrchestratorResult(
            run_id=run_id,
            status=RetrainingOrchestratorStatus.DRIFT_DETECTED,
            champion_model_id=drift.champion_model_id,
            blockers=blockers,
            reasons=reasons,
            validation_summary={
                "drift_severity": drift.drift_severity,
                "drift_reason": drift.drift_reason,
            },
        )
        return self._record(result)

    # ──────────────────────────────────────────────────────────────────────
    # Phase 2: candidate training placeholder
    # ──────────────────────────────────────────────────────────────────────

    def start_training_placeholder(
        self, run_id: str, placeholder: CandidateTrainingPlaceholder
    ) -> RetrainingOrchestratorResult:
        """Record a candidate training placeholder and move to TRAINING_STARTED.

        This NEVER executes training. The placeholder is metadata-only.
        """
        current = self._status.get(run_id)
        if current is None:
            return self._record(RetrainingOrchestratorResult(
                run_id=run_id,
                status=RetrainingOrchestratorStatus.REJECTED,
                blockers=["Run does not exist - call ingest_drift first"],
            ))
        if not self._legal_transition(current, RetrainingOrchestratorStatus.TRAINING_STARTED):
            return self._record(RetrainingOrchestratorResult(
                run_id=run_id,
                status=current,
                previous_status=current,
                blockers=[f"Illegal transition from {current.value} to TRAINING_STARTED"],
            ))

        blockers: list[str] = []
        if not placeholder.candidate_model_id:
            blockers.append("Missing candidate_model_id")
        if not placeholder.champion_model_id:
            blockers.append("Missing champion_model_id on placeholder")
        if placeholder.training_executed:
            blockers.append(
                "training_executed=True is forbidden - orchestrator never executes training"
            )

        if blockers:
            result = RetrainingOrchestratorResult(
                run_id=run_id,
                status=RetrainingOrchestratorStatus.REJECTED,
                previous_status=current,
                candidate_model_id=placeholder.candidate_model_id,
                champion_model_id=placeholder.champion_model_id,
                blockers=blockers,
                reasons=["Training placeholder rejected"],
            )
            return self._record(result)

        result = RetrainingOrchestratorResult(
            run_id=run_id,
            status=RetrainingOrchestratorStatus.TRAINING_STARTED,
            previous_status=current,
            candidate_model_id=placeholder.candidate_model_id,
            champion_model_id=placeholder.champion_model_id,
            reasons=[
                "Candidate training placeholder recorded (training NOT executed)",
            ],
            validation_summary={
                "training_job_id": placeholder.training_job_id,
                "training_executed": False,
            },
        )
        return self._record(result)

    # ──────────────────────────────────────────────────────────────────────
    # Phase 3: validation gate
    # ──────────────────────────────────────────────────────────────────────

    def run_validation_gate(
        self,
        run_id: str,
        candidate_metrics: dict,
        champion_metrics: Optional[dict] = None,
    ) -> RetrainingOrchestratorResult:
        """Run the validation gate. Never auto-promotes.

        Checks:
            - all REQUIRED_VALIDATION_KEYS present
            - walk-forward passed (sharpe >= 0, status != FAIL)
            - broker-split passed (status == PASS)
            - cost-adjusted requirement met
        On success moves to VALIDATION_PENDING (shadow mode still required).
        On failure moves to REJECTED.
        """
        current = self._status.get(run_id)
        if current is None:
            return self._record(RetrainingOrchestratorResult(
                run_id=run_id,
                status=RetrainingOrchestratorStatus.REJECTED,
                blockers=["Run does not exist"],
            ))
        if not self._legal_transition(current, RetrainingOrchestratorStatus.VALIDATION_PENDING):
            return self._record(RetrainingOrchestratorResult(
                run_id=run_id,
                status=current,
                previous_status=current,
                blockers=[f"Illegal transition from {current.value} to VALIDATION_PENDING"],
            ))

        blockers: list[str] = []
        warnings: list[str] = []
        reasons: list[str] = []

        # Required keys
        for k in REQUIRED_VALIDATION_KEYS:
            if k not in candidate_metrics or candidate_metrics[k] is None:
                blockers.append(f"Missing required validation metric: {k}")

        # Walk-forward
        wf_sharpe = candidate_metrics.get("walk_forward_sharpe")
        wf_status = candidate_metrics.get("walk_forward_status")
        if wf_sharpe is not None and wf_sharpe < MIN_WALK_FORWARD_SHARPE:
            blockers.append(
                f"walk_forward_sharpe {wf_sharpe} below minimum {MIN_WALK_FORWARD_SHARPE}"
            )
        if wf_status is not None and wf_status != "PASS":
            blockers.append(f"walk_forward_status={wf_status} (expected PASS)")

        # Broker split
        bs_status = candidate_metrics.get("broker_split_status")
        if bs_status is not None and bs_status != "PASS":
            blockers.append(f"broker_split_status={bs_status} (expected PASS)")

        # Cost-adjusted
        cost_adj = candidate_metrics.get("cost_adjusted_net_profit")
        if cost_adj is not None and cost_adj < MIN_COST_ADJUSTED_NET_PROFIT_RATIO:
            blockers.append(
                f"cost_adjusted_net_profit {cost_adj} below minimum "
                f"{MIN_COST_ADJUSTED_NET_PROFIT_RATIO}"
            )

        # Champion vs candidate comparison
        comparison = self.compare_champion_vs_candidate(
            candidate_metrics, champion_metrics or {}
        )
        if champion_metrics:
            if not comparison.candidate_better:
                blockers.append(
                    "Candidate does not improve over champion on key metrics"
                )
            else:
                reasons.append("Candidate improves over champion on key metrics")

        if blockers:
            result = RetrainingOrchestratorResult(
                run_id=run_id,
                status=RetrainingOrchestratorStatus.REJECTED,
                previous_status=current,
                candidate_model_id=self._runs[run_id].candidate_model_id,
                champion_model_id=self._runs[run_id].champion_model_id,
                blockers=blockers,
                warnings=warnings,
                reasons=reasons + ["Validation gate failed"],
                comparison=comparison.__dict__,
                validation_summary={"ok": False, "blocker_count": len(blockers)},
            )
            return self._record(result)

        result = RetrainingOrchestratorResult(
            run_id=run_id,
            status=RetrainingOrchestratorStatus.VALIDATION_PENDING,
            previous_status=current,
            candidate_model_id=self._runs[run_id].candidate_model_id,
            champion_model_id=self._runs[run_id].champion_model_id,
            blockers=blockers,
            warnings=warnings,
            reasons=reasons + ["Validation gate passed - shadow mode required next"],
            comparison=comparison.__dict__,
            validation_summary={
                "ok": True,
                "walk_forward_passed": True,
                "broker_split_passed": True,
                "cost_adjusted_passed": True,
            },
        )
        return self._record(result)

    # ──────────────────────────────────────────────────────────────────────
    # Phase 4: shadow mode requirement
    # ──────────────────────────────────────────────────────────────────────

    def enter_shadow_mode(
        self, run_id: str, shadow_metrics: dict
    ) -> RetrainingOrchestratorResult:
        """Move candidate into shadow mode after validation gate passed.

        Requires shadow_status == PASS and shadow_hours >= MIN_SHADOW_HOURS.
        """
        current = self._status.get(run_id)
        if current is None:
            return self._record(RetrainingOrchestratorResult(
                run_id=run_id,
                status=RetrainingOrchestratorStatus.REJECTED,
                blockers=["Run does not exist"],
            ))
        if not self._legal_transition(current, RetrainingOrchestratorStatus.SHADOW_MODE):
            return self._record(RetrainingOrchestratorResult(
                run_id=run_id,
                status=current,
                previous_status=current,
                blockers=[f"Illegal transition from {current.value} to SHADOW_MODE"],
            ))

        blockers: list[str] = []
        shadow_status = shadow_metrics.get("shadow_status")
        shadow_hours = shadow_metrics.get("shadow_hours", 0)
        if shadow_status is None:
            blockers.append("Missing shadow_status")
        elif shadow_status != "PASS":
            blockers.append(f"shadow_status={shadow_status} (expected PASS)")
        if shadow_hours is None or shadow_hours < MIN_SHADOW_HOURS:
            blockers.append(
                f"shadow_hours={shadow_hours} below minimum {MIN_SHADOW_HOURS}"
            )

        if blockers:
            result = RetrainingOrchestratorResult(
                run_id=run_id,
                status=RetrainingOrchestratorStatus.REJECTED,
                previous_status=current,
                candidate_model_id=self._runs[run_id].candidate_model_id,
                champion_model_id=self._runs[run_id].champion_model_id,
                blockers=blockers,
                reasons=["Shadow mode requirements not met"],
                validation_summary={"ok": False, "blocker_count": len(blockers)},
            )
            return self._record(result)

        result = RetrainingOrchestratorResult(
            run_id=run_id,
            status=RetrainingOrchestratorStatus.SHADOW_MODE,
            previous_status=current,
            candidate_model_id=self._runs[run_id].candidate_model_id,
            champion_model_id=self._runs[run_id].champion_model_id,
            reasons=[
                f"Shadow mode passed ({shadow_hours}h >= {MIN_SHADOW_HOURS}h minimum)"
            ],
            validation_summary={
                "ok": True,
                "shadow_status": shadow_status,
                "shadow_hours": shadow_hours,
            },
        )
        return self._record(result)

    # ──────────────────────────────────────────────────────────────────────
    # Phase 5: approved for demo (CEO approval required to leave shadow)
    # ──────────────────────────────────────────────────────────────────────

    def approve_for_demo(
        self,
        run_id: str,
        ceo_approval: bool = False,
        approver: str = "",
    ) -> RetrainingOrchestratorResult:
        """Move candidate from SHADOW_MODE to APPROVED_FOR_DEMO.

        Requires explicit CEO approval. NEVER auto-approves.
        """
        current = self._status.get(run_id)
        if current is None:
            return self._record(RetrainingOrchestratorResult(
                run_id=run_id,
                status=RetrainingOrchestratorStatus.REJECTED,
                blockers=["Run does not exist"],
            ))
        if not self._legal_transition(current, RetrainingOrchestratorStatus.APPROVED_FOR_DEMO):
            return self._record(RetrainingOrchestratorResult(
                run_id=run_id,
                status=current,
                previous_status=current,
                blockers=[f"Illegal transition from {current.value} to APPROVED_FOR_DEMO"],
            ))

        blockers: list[str] = []
        if not ceo_approval:
            blockers.append("CEO approval required to leave shadow mode for demo")
        if not approver:
            blockers.append("approver name required")
        if not ceo_approval or not approver:
            result = RetrainingOrchestratorResult(
                run_id=run_id,
                status=RetrainingOrchestratorStatus.REJECTED,
                previous_status=current,
                candidate_model_id=self._runs[run_id].candidate_model_id,
                champion_model_id=self._runs[run_id].champion_model_id,
                blockers=blockers,
                reasons=["CEO approval not granted - cannot promote to demo"],
            )
            return self._record(result)

        result = RetrainingOrchestratorResult(
            run_id=run_id,
            status=RetrainingOrchestratorStatus.APPROVED_FOR_DEMO,
            previous_status=current,
            candidate_model_id=self._runs[run_id].candidate_model_id,
            champion_model_id=self._runs[run_id].champion_model_id,
            reasons=[
                f"Approved for demo by CEO={approver} - awaiting human promotion gate"
            ],
            validation_summary={
                "ok": True,
                "ceo_approval": True,
                "approver": approver,
            },
        )
        return self._record(result)

    # ──────────────────────────────────────────────────────────────────────
    # Phase 6: human promotion gate (terminal state for the orchestrator)
    # ──────────────────────────────────────────────────────────────────────

    def request_human_promotion(self, run_id: str) -> RetrainingOrchestratorResult:
        """Move from APPROVED_FOR_DEMO to PROMOTION_PENDING_HUMAN.

        This is the terminal state for the orchestrator. The orchestrator
        NEVER promotes to live. An external human/CEO must invoke
        ModelPromotionGate.validate_promotion(human_approval=True) and then
        ModelRegistry.require_manual_champion_promotion().
        """
        current = self._status.get(run_id)
        if current is None:
            return self._record(RetrainingOrchestratorResult(
                run_id=run_id,
                status=RetrainingOrchestratorStatus.REJECTED,
                blockers=["Run does not exist"],
            ))
        if not self._legal_transition(
            current, RetrainingOrchestratorStatus.PROMOTION_PENDING_HUMAN
        ):
            return self._record(RetrainingOrchestratorResult(
                run_id=run_id,
                status=current,
                previous_status=current,
                blockers=[
                    f"Illegal transition from {current.value} to PROMOTION_PENDING_HUMAN"
                ],
            ))

        result = RetrainingOrchestratorResult(
            run_id=run_id,
            status=RetrainingOrchestratorStatus.PROMOTION_PENDING_HUMAN,
            previous_status=current,
            candidate_model_id=self._runs[run_id].candidate_model_id,
            champion_model_id=self._runs[run_id].champion_model_id,
            reasons=[
                "Promotion pending human/CEO approval - orchestrator will NOT auto-promote"
            ],
            validation_summary={
                "ok": True,
                "auto_promote_to_live": False,
                "human_approval_required": True,
            },
        )
        return self._record(result)

    # ──────────────────────────────────────────────────────────────────────
    # Champion vs candidate comparison
    # ──────────────────────────────────────────────────────────────────────

    def compare_champion_vs_candidate(
        self,
        candidate_metrics: dict,
        champion_metrics: dict,
    ) -> ChampionCandidateComparison:
        """Compare candidate against champion on key metrics.

        Returns a ChampionCandidateComparison. candidate_better=True only
        when the candidate is no worse on drawdown AND better on at least
        one of (sharpe, walk_forward_sharpe, cost_adjusted_net_profit).
        """
        comparison = ChampionCandidateComparison(
            champion_metrics=dict(champion_metrics),
            candidate_metrics=dict(candidate_metrics),
        )
        reasons: list[str] = []

        c_sharpe = candidate_metrics.get("oos_sharpe")
        ch_sharpe = champion_metrics.get("oos_sharpe")
        if c_sharpe is not None and ch_sharpe is not None:
            comparison.sharpe_delta = c_sharpe - ch_sharpe
            if comparison.sharpe_delta > 0:
                reasons.append(
                    f"Candidate sharpe {c_sharpe} > champion {ch_sharpe}"
                )

        c_dd = candidate_metrics.get("oos_max_drawdown")
        ch_dd = champion_metrics.get("oos_max_drawdown")
        if c_dd is not None and ch_dd is not None:
            # positive delta = candidate has WORSE drawdown
            comparison.drawdown_delta = c_dd - ch_dd
            if comparison.drawdown_delta < 0:
                reasons.append(
                    f"Candidate drawdown {c_dd} < champion {ch_dd} (better)"
                )
            elif comparison.drawdown_delta > 0:
                reasons.append(
                    f"Candidate drawdown {c_dd} > champion {ch_dd} (worse)"
                )

        c_cost = candidate_metrics.get("cost_adjusted_net_profit")
        ch_cost = champion_metrics.get("cost_adjusted_net_profit")
        if c_cost is not None and ch_cost is not None:
            comparison.cost_adjusted_delta = c_cost - ch_cost
            if comparison.cost_adjusted_delta > 0:
                reasons.append(
                    f"Candidate cost-adjusted profit {c_cost} > champion {ch_cost}"
                )

        # Candidate is better only when:
        #   - drawdown not worse (delta <= 0), AND
        #   - at least one of sharpe / cost-adjusted is strictly better
        better_drawdown = (
            comparison.drawdown_delta is None or comparison.drawdown_delta <= 0
        )
        better_metric = (
            (comparison.sharpe_delta is not None and comparison.sharpe_delta > 0)
            or (
                comparison.cost_adjusted_delta is not None
                and comparison.cost_adjusted_delta > 0
            )
        )
        comparison.candidate_better = bool(better_drawdown and better_metric)
        comparison.reasons = reasons
        return comparison

    # ──────────────────────────────────────────────────────────────────────
    # Safety helpers
    # ──────────────────────────────────────────────────────────────────────

    def enforce_no_auto_promotion_to_live(self) -> bool:
        """Always returns False. Auto-promotion to live is forbidden."""
        return False

    def safety_invariants(self) -> dict:
        """Return the static safety invariant dictionary."""
        return dict(SAFETY_INVARIANTS)

    def summary(self) -> dict:
        return {
            "total_runs": len(self._runs),
            "auto_promote_to_live": False,
            "human_approval_required": True,
            "min_walk_forward_sharpe": MIN_WALK_FORWARD_SHARPE,
            "min_shadow_hours": MIN_SHADOW_HOURS,
            "min_cost_adjusted_net_profit_ratio": MIN_COST_ADJUSTED_NET_PROFIT_RATIO,
            "no_martingale": True,
            "no_grid": True,
            "no_averaging": True,
            "no_loss_based_lot_multiplier": True,
        }
