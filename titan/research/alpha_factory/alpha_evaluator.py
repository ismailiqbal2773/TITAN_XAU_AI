"""
TITAN XAU AI - Alpha Evaluator (research layer)
===============================================

Evaluates registered alpha candidates against four mandatory gates:

    1. Leakage guard
    2. Walk-forward validation
    3. Broker-split validation
    4. Cost-adjusted validation

Promotion ladder (each step must be explicit — never automatic):

    CANDIDATE
        └─> (passes leakage + walk-forward + broker-split + overfit)
            VALIDATED_SHADOW_ONLY
                └─> (passes cost-adjusted gate)
                    APPROVED_FOR_DEMO
                        └─> (EXPLICIT human request only)
                            APPROVED_FOR_LIVE_PENDING_HUMAN

Rejection outcomes:
    * REJECTED_OVERFIT       — leakage, walk-forward fail, broker-split fail,
                                or overfit_score above threshold.
    * REJECTED_COST_ADJUSTED — cost-adjusted score below threshold.

Hard invariants:
    * NEVER auto-approves for live.
    * NEVER imports MetaTrader5.
    * NEVER calls mt5.order_send.
    * NEVER adds martingale, grid, averaging, or loss_based_lot_multiplier.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Optional


# ──────────────────────────────────────────────────────────────────────────
# Status enum (string constants — no enum import required, easy to serialize)
# ──────────────────────────────────────────────────────────────────────────
class AlphaStatus:
    CANDIDATE = "CANDIDATE"
    REJECTED_OVERFIT = "REJECTED_OVERFIT"
    REJECTED_COST_ADJUSTED = "REJECTED_COST_ADJUSTED"
    VALIDATED_SHADOW_ONLY = "VALIDATED_SHADOW_ONLY"
    APPROVED_FOR_DEMO = "APPROVED_FOR_DEMO"
    APPROVED_FOR_LIVE_PENDING_HUMAN = "APPROVED_FOR_LIVE_PENDING_HUMAN"


ALL_STATUSES: tuple[str, ...] = (
    AlphaStatus.CANDIDATE,
    AlphaStatus.REJECTED_OVERFIT,
    AlphaStatus.REJECTED_COST_ADJUSTED,
    AlphaStatus.VALIDATED_SHADOW_ONLY,
    AlphaStatus.APPROVED_FOR_DEMO,
    AlphaStatus.APPROVED_FOR_LIVE_PENDING_HUMAN,
)


SAFETY_CONTRACT: dict[str, bool] = {
    "no_martingale": True,
    "no_grid": True,
    "no_averaging": True,
    "no_loss_based_lot_multiplier": True,
    "no_auto_live": True,
    "no_order_send": True,
}


# ──────────────────────────────────────────────────────────────────────────
# Evaluation record
# ──────────────────────────────────────────────────────────────────────────
@dataclass
class AlphaEvaluation:
    """Result of evaluating one alpha candidate.

    All score fields are floats in [0.0, 1.0] unless otherwise stated.
    A *higher* score is *better* for walk_forward / broker_split /
    cost_adjusted. A *lower* overfit_score is better.
    """

    alpha_name: str
    walk_forward_score: float = 0.0
    broker_split_score: float = 0.0
    cost_adjusted_score: float = 0.0
    overfit_score: float = 1.0
    status: str = AlphaStatus.CANDIDATE
    leakage_flags: list[str] = field(default_factory=list)
    rejection_reasons: list[str] = field(default_factory=list)
    safety: dict[str, bool] = field(default_factory=lambda: dict(SAFETY_CONTRACT))
    evaluated_utc: str = ""
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.evaluated_utc:
            self.evaluated_utc = datetime.now(timezone.utc).isoformat()
        self.safety = dict(SAFETY_CONTRACT) | {
            k: v for k, v in self.safety.items() if k not in SAFETY_CONTRACT
        }

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AlphaEvaluation":
        return cls(
            alpha_name=data["alpha_name"],
            walk_forward_score=float(data.get("walk_forward_score", 0.0)),
            broker_split_score=float(data.get("broker_split_score", 0.0)),
            cost_adjusted_score=float(data.get("cost_adjusted_score", 0.0)),
            overfit_score=float(data.get("overfit_score", 1.0)),
            status=data.get("status", AlphaStatus.CANDIDATE),
            leakage_flags=list(data.get("leakage_flags", []) or []),
            rejection_reasons=list(data.get("rejection_reasons", []) or []),
            safety=dict(data.get("safety", SAFETY_CONTRACT)),
            evaluated_utc=data.get("evaluated_utc", ""),
            notes=data.get("notes", ""),
        )


# ──────────────────────────────────────────────────────────────────────────
# Evaluator
# ──────────────────────────────────────────────────────────────────────────
@dataclass
class EvaluatorThresholds:
    """Configurable thresholds for the four gates.

    Defaults are conservative: candidates must demonstrate non-trivial
    out-of-sample robustness AND survive realistic transaction-cost
    adjustment before they can be promoted even to shadow-only status.
    """

    walk_forward_min: float = 0.55
    broker_split_min: float = 0.55
    cost_adjusted_min: float = 0.40
    overfit_max: float = 0.50


class AlphaEvaluator:
    """Evaluates AlphaCandidate objects through the four mandatory gates.

    The evaluator is *stateless* with respect to the registry — it accepts
    candidate metrics, returns an AlphaEvaluation, and lets the caller
    persist via AlphaRegistry. Promotion to live status is gated behind
    an explicit method `request_human_approval_for_live()` that always
    returns the PENDING_HUMAN status — never an actual live status.
    """

    def __init__(self, thresholds: Optional[EvaluatorThresholds] = None) -> None:
        self.thresholds = thresholds or EvaluatorThresholds()

    # ── public API ────────────────────────────────────────────────────
    def evaluate(
        self,
        candidate: Any,
        metrics: Optional[dict[str, Any]] = None,
        leakage_flags: Optional[list[str]] = None,
    ) -> AlphaEvaluation:
        """Evaluate a candidate and return an AlphaEvaluation record.

        Parameters
        ----------
        candidate : AlphaCandidate
            The candidate to evaluate. Only `candidate.name` and
            `candidate.safety` are read here.
        metrics : dict, optional
            Score dictionary with keys:
                walk_forward_score, broker_split_score,
                cost_adjusted_score, overfit_score
            Missing keys default to failing values.
        leakage_flags : list[str], optional
            Active leakage flags. Any non-empty list causes the
            candidate to be rejected for overfit.
        """
        metrics = dict(metrics or {})
        leakage_flags = list(leakage_flags or [])

        wf = float(metrics.get("walk_forward_score", 0.0))
        bs = float(metrics.get("broker_split_score", 0.0))
        ca = float(metrics.get("cost_adjusted_score", 0.0))
        of = float(metrics.get("overfit_score", 1.0))

        ev = AlphaEvaluation(
            alpha_name=getattr(candidate, "name", "unknown"),
            walk_forward_score=wf,
            broker_split_score=bs,
            cost_adjusted_score=ca,
            overfit_score=of,
            status=AlphaStatus.CANDIDATE,
            leakage_flags=leakage_flags,
        )

        # ── Gate 1: leakage guard ────────────────────────────────────
        if not self.check_leakage_guard(leakage_flags):
            ev.status = AlphaStatus.REJECTED_OVERFIT
            ev.rejection_reasons.append(
                f"Leakage guard failed: flags={leakage_flags}"
            )
            return ev

        # ── Gate 2: walk-forward validation ──────────────────────────
        if not self.check_walk_forward(wf):
            ev.status = AlphaStatus.REJECTED_OVERFIT
            ev.rejection_reasons.append(
                f"Walk-forward validation failed: "
                f"score={wf:.3f} < min={self.thresholds.walk_forward_min:.3f}"
            )
            return ev

        # ── Gate 3: broker-split validation ──────────────────────────
        if not self.check_broker_split(bs):
            ev.status = AlphaStatus.REJECTED_OVERFIT
            ev.rejection_reasons.append(
                f"Broker-split validation failed: "
                f"score={bs:.3f} < min={self.thresholds.broker_split_min:.3f}"
            )
            return ev

        # ── Gate 3b: overfit score ───────────────────────────────────
        if not self.check_overfit(of):
            ev.status = AlphaStatus.REJECTED_OVERFIT
            ev.rejection_reasons.append(
                f"Overfit score too high: "
                f"score={of:.3f} > max={self.thresholds.overfit_max:.3f}"
            )
            return ev

        # ── Gate 4: cost-adjusted validation ─────────────────────────
        if not self.check_cost_adjusted(ca):
            ev.status = AlphaStatus.REJECTED_COST_ADJUSTED
            ev.rejection_reasons.append(
                f"Cost-adjusted validation failed: "
                f"score={ca:.3f} < min={self.thresholds.cost_adjusted_min:.3f}"
            )
            return ev

        # ── All gates passed: validated for shadow only ──────────────
        ev.status = AlphaStatus.VALIDATED_SHADOW_ONLY
        return ev

    # ── individual gate checks ────────────────────────────────────────
    def check_leakage_guard(self, leakage_flags: list[str]) -> bool:
        """Return True iff there are no active leakage flags."""
        return len(leakage_flags) == 0

    def check_walk_forward(self, walk_forward_score: float) -> bool:
        return walk_forward_score >= self.thresholds.walk_forward_min

    def check_broker_split(self, broker_split_score: float) -> bool:
        return broker_split_score >= self.thresholds.broker_split_min

    def check_cost_adjusted(self, cost_adjusted_score: float) -> bool:
        return cost_adjusted_score >= self.thresholds.cost_adjusted_min

    def check_overfit(self, overfit_score: float) -> bool:
        return overfit_score <= self.thresholds.overfit_max

    # ── explicit promotion ladder ─────────────────────────────────────
    def promote_to_demo(self, evaluation: AlphaEvaluation) -> AlphaEvaluation:
        """Promote a VALIDATED_SHADOW_ONLY evaluation to APPROVED_FOR_DEMO.

        This represents the end of shadow observation. It is NOT a live
        promotion.
        """
        if evaluation.status != AlphaStatus.VALIDATED_SHADOW_ONLY:
            evaluation.rejection_reasons.append(
                f"Cannot promote to demo from status '{evaluation.status}'. "
                f"Must be VALIDATED_SHADOW_ONLY."
            )
            return evaluation
        evaluation.status = AlphaStatus.APPROVED_FOR_DEMO
        return evaluation

    def request_human_approval_for_live(
        self, evaluation: AlphaEvaluation
    ) -> AlphaEvaluation:
        """Mark an APPROVED_FOR_DEMO evaluation as pending human approval
        for live trading.

        This is the ONLY method that produces APPROVED_FOR_LIVE_PENDING_HUMAN.
        It never returns an actual live status — live deployment requires
        a separate, out-of-band human action that this module never
        performs.
        """
        if evaluation.status != AlphaStatus.APPROVED_FOR_DEMO:
            evaluation.rejection_reasons.append(
                f"Cannot request live approval from status "
                f"'{evaluation.status}'. Must be APPROVED_FOR_DEMO."
            )
            return evaluation
        evaluation.status = AlphaStatus.APPROVED_FOR_LIVE_PENDING_HUMAN
        return evaluation

    # ── safety surface ────────────────────────────────────────────────
    @staticmethod
    def safety_contract() -> dict[str, bool]:
        return dict(SAFETY_CONTRACT)

    @staticmethod
    def never_auto_approve_live() -> bool:
        """Always returns False — the evaluator never auto-approves live."""
        return False
