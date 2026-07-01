"""
TITAN XAU AI - Model Promotion Gate (Sprint 9.9.3.46)
======================================================

Institutional promotion gate for candidate -> champion transitions.

NEVER imports MetaTrader5.
NEVER sends orders (no mt5.order_send anywhere in this file).
NEVER retrains models (no .fit / train_model / retrain / run_hpo).
NEVER adds martingale / grid / averaging / loss-based lot multipliers.
NEVER auto-promotes to live. validate_promotion() returns approved=True
    ONLY when ALL gates pass AND human_approval=True is explicitly passed.

A PromotionResult carries:
    - approved: bool
    - blockers: list[str]
    - reason: str
    - safety flags: no_martingale / no_grid / no_averaging /
      no_loss_based_lot_multiplier / auto_promote_to_live (always False)

Required checks (all must PASS):
    - walk_forward_passed
    - broker_split_passed
    - cost_adjusted_passed
    - shadow_mode_completed
    - human_approval_received (explicit human_approval=True parameter)

The gate is intentionally separable from the registry. Even when the
gate approves, the actual ModelRegistry.require_manual_champion_promotion()
must still be called out-of-band by an operator.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
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


@dataclass
class PromotionResult:
    """Outcome of a promotion gate evaluation."""

    approved: bool
    reason: str
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    candidate_model_id: str = ""
    champion_model_id: str = ""
    checks: dict = field(default_factory=dict)
    human_approval: bool = False
    auto_promote_to_live: bool = False
    no_martingale: bool = True
    no_grid: bool = True
    no_averaging: bool = True
    no_loss_based_lot_multiplier: bool = True
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
        # approved can never be True without human_approval
        if self.approved and not self.human_approval:
            self.approved = False
            self.blockers.append(
                "Promotion requires explicit human_approval=True - auto-approval blocked"
            )
            self.reason = "BLOCKED: human_approval missing"

    def to_dict(self) -> dict:
        return asdict(self)


class ModelPromotionGate:
    """Promotion gate. NEVER auto-promotes to live.

    validate_promotion() requires every check to PASS AND an explicit
    human_approval=True parameter to return approved=True.
    """

    def __init__(self):
        self._last_result: Optional[PromotionResult] = None

    # ──────────────────────────────────────────────────────────────────────
    # Top-level evaluation
    # ──────────────────────────────────────────────────────────────────────

    def validate_promotion(
        self,
        candidate_model_id: str,
        champion_model_id: str,
        *,
        walk_forward_passed: bool = False,
        broker_split_passed: bool = False,
        cost_adjusted_passed: bool = False,
        shadow_mode_completed: bool = False,
        human_approval: bool = False,
        approver: str = "",
        notes: str = "",
    ) -> PromotionResult:
        """Validate a candidate -> champion promotion request.

        Returns a PromotionResult. NEVER auto-promotes to live. The
        approved field is True only when every check passes AND
        human_approval=True is explicitly provided.
        """
        blockers: list[str] = []
        warnings: list[str] = []
        checks = {
            "walk_forward_passed": bool(walk_forward_passed),
            "broker_split_passed": bool(broker_split_passed),
            "cost_adjusted_passed": bool(cost_adjusted_passed),
            "shadow_mode_completed": bool(shadow_mode_completed),
            "human_approval_received": bool(human_approval),
        }

        # 1) Identifiers must be present and distinct
        if not candidate_model_id:
            blockers.append("Missing candidate_model_id")
        if not champion_model_id:
            blockers.append("Missing champion_model_id")
        if (
            candidate_model_id
            and champion_model_id
            and candidate_model_id == champion_model_id
        ):
            blockers.append(
                "candidate_model_id must differ from champion_model_id"
            )

        # 2) Walk-forward
        if not walk_forward_passed:
            blockers.append("walk_forward_passed=False - walk-forward validation required")

        # 3) Broker-split
        if not broker_split_passed:
            blockers.append(
                "broker_split_passed=False - broker-split validation required"
            )

        # 4) Cost-adjusted
        if not cost_adjusted_passed:
            blockers.append(
                "cost_adjusted_passed=False - cost-adjusted validation required"
            )

        # 5) Shadow mode completed
        if not shadow_mode_completed:
            blockers.append(
                "shadow_mode_completed=False - shadow mode validation required"
            )

        # 6) Human approval (explicit parameter)
        if not human_approval:
            blockers.append(
                "human_approval=False - explicit human/CEO approval required"
            )
        else:
            if not approver:
                blockers.append(
                    "human_approval=True but approver name is empty - approval not attributable"
                )

        # Determine approval
        approved = len(blockers) == 0
        if approved:
            reason = (
                f"Promotion APPROVED with explicit human approval by {approver} - "
                "auto_promote_to_live remains False (registry must promote manually)"
            )
        else:
            reason = f"Promotion BLOCKED: {len(blockers)} blocker(s)"

        result = PromotionResult(
            approved=approved,
            reason=reason,
            blockers=blockers,
            warnings=warnings,
            candidate_model_id=candidate_model_id,
            champion_model_id=champion_model_id,
            checks=checks,
            human_approval=bool(human_approval),
        )
        self._last_result = result
        return result

    # ──────────────────────────────────────────────────────────────────────
    # Convenience helpers
    # ──────────────────────────────────────────────────────────────────────

    def enforce_no_auto_promotion_to_live(self) -> bool:
        """Always returns False. Auto-promotion to live is forbidden."""
        return False

    def safety_invariants(self) -> dict:
        return dict(SAFETY_INVARIANTS)

    def summary(self) -> dict:
        if self._last_result is None:
            return {
                "verdict": "NO_RESULT",
                "auto_promote_to_live": False,
                "no_martingale": True,
                "no_grid": True,
                "no_averaging": True,
                "no_loss_based_lot_multiplier": True,
            }
        r = self._last_result
        return {
            "verdict": "APPROVED" if r.approved else "BLOCKED",
            "approved": r.approved,
            "blocker_count": len(r.blockers),
            "warning_count": len(r.warnings),
            "human_approval": r.human_approval,
            "auto_promote_to_live": False,
            "no_martingale": True,
            "no_grid": True,
            "no_averaging": True,
            "no_loss_based_lot_multiplier": True,
        }
