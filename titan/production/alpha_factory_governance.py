"""
TITAN XAU AI - Alpha Factory Governance (Sprint 9.9.3.36)
==========================================================

Governance layer for the alpha factory. The alpha factory generates and
registers candidate variants (feature sets, label variants, model variants,
ensembles, threshold variants, regime specialists, exit policies).

NEVER imports MetaTrader5.
NEVER sends orders.
NEVER deploys a model.
NEVER replaces the champion.
NEVER modifies live runtime config.
NEVER bypasses ModelLifecycleGovernance.

The alpha factory may only REGISTER candidates. Promotion to shadow,
challenger, or champion must go through ModelLifecycleGovernance and
explicit operator approval.
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class AlphaCandidateType(str, Enum):
    FEATURE_SET = "FEATURE_SET"
    LABEL_VARIANT = "LABEL_VARIANT"
    MODEL_VARIANT = "MODEL_VARIANT"
    ENSEMBLE_VARIANT = "ENSEMBLE_VARIANT"
    THRESHOLD_VARIANT = "THRESHOLD_VARIANT"
    REGIME_SPECIALIST = "REGIME_SPECIALIST"
    EXIT_POLICY_VARIANT = "EXIT_POLICY_VARIANT"


class AlphaCandidateStatus(str, Enum):
    GENERATED = "GENERATED"
    VALIDATING = "VALIDATING"
    PASSED_INITIAL_FILTER = "PASSED_INITIAL_FILTER"
    REJECTED = "REJECTED"
    QUARANTINED = "QUARANTINED"
    READY_FOR_SHADOW = "READY_FOR_SHADOW"
    NEEDS_REVIEW = "NEEDS_REVIEW"


@dataclass
class AlphaCandidate:
    candidate_id: str
    candidate_type: AlphaCandidateType
    description: str
    source: str
    created_utc: str = ""
    metrics: dict = field(default_factory=dict)
    validation_status: AlphaCandidateStatus = AlphaCandidateStatus.GENERATED
    leakage_flags: list[str] = field(default_factory=list)
    broker_split_status: str = "PENDING"
    walk_forward_status: str = "PENDING"
    shadow_ready: bool = False
    notes: str = ""

    def __post_init__(self):
        if not self.created_utc:
            self.created_utc = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        d = asdict(self)
        d["candidate_type"] = self.candidate_type.value
        d["validation_status"] = self.validation_status.value
        return d


class AlphaFactoryGovernance:
    """Governance for alpha candidate registration and validation.

    May register candidates only. Cannot deploy, replace champion, trade,
    modify live runtime config, or bypass ModelLifecycleGovernance.
    """

    def __init__(self):
        self._candidates: dict[str, AlphaCandidate] = {}

    # ──────────────────────────────────────────────────────────────────────
    # Registration
    # ──────────────────────────────────────────────────────────────────────

    def register_candidate(
        self,
        candidate_id: str,
        candidate_type: AlphaCandidateType,
        description: str,
        source: str,
        metrics: Optional[dict] = None,
        notes: str = "",
    ) -> AlphaCandidate:
        """Register a new alpha candidate. Defaults to GENERATED status.

        Never deploys. Never promotes. Never modifies live config.
        """
        if candidate_id in self._candidates:
            raise ValueError(f"Candidate already registered: {candidate_id}")
        candidate = AlphaCandidate(
            candidate_id=candidate_id,
            candidate_type=candidate_type,
            description=description,
            source=source,
            metrics=dict(metrics or {}),
            notes=notes,
        )
        self._candidates[candidate_id] = candidate
        return candidate

    def get_candidate(self, candidate_id: str) -> Optional[AlphaCandidate]:
        return self._candidates.get(candidate_id)

    def list_candidates(self) -> list[AlphaCandidate]:
        return list(self._candidates.values())

    # ──────────────────────────────────────────────────────────────────────
    # Validators
    # ──────────────────────────────────────────────────────────────────────

    def validate_candidate_metadata(self, candidate: AlphaCandidate) -> tuple[bool, list[str]]:
        """Validate that a candidate has the minimum required metadata."""
        blockers: list[str] = []
        if not candidate.candidate_id:
            blockers.append("Missing candidate_id")
        if not candidate.candidate_type:
            blockers.append("Missing candidate_type")
        if not candidate.description:
            blockers.append("Missing description")
        if not candidate.source:
            blockers.append("Missing source")
        return len(blockers) == 0, blockers

    def reject_if_leakage_flags(self, candidate: AlphaCandidate) -> tuple[bool, list[str]]:
        """If leakage flags are present, reject and quarantine the candidate.

        Returns (rejected, reasons).
        """
        if candidate.leakage_flags:
            candidate.validation_status = AlphaCandidateStatus.QUARANTINED
            candidate.shadow_ready = False
            reasons = [f"Leakage flags present: {candidate.leakage_flags}"]
            return True, reasons
        return False, []

    def require_walk_forward(self, candidate: AlphaCandidate) -> tuple[bool, list[str]]:
        """Require walk-forward validation status = PASS."""
        blockers: list[str] = []
        if candidate.walk_forward_status == "PENDING":
            blockers.append("Walk-forward validation not yet run")
        elif candidate.walk_forward_status == "FAIL":
            blockers.append("Walk-forward validation failed")
        elif candidate.walk_forward_status != "PASS":
            blockers.append(f"Walk-forward status unknown: {candidate.walk_forward_status}")
        return len(blockers) == 0, blockers

    def require_broker_split(self, candidate: AlphaCandidate) -> tuple[bool, list[str]]:
        """Require broker-split validation status = PASS."""
        blockers: list[str] = []
        if candidate.broker_split_status == "PENDING":
            blockers.append("Broker-split validation not yet run")
        elif candidate.broker_split_status == "FAIL":
            blockers.append("Broker-split validation failed")
        elif candidate.broker_split_status != "PASS":
            blockers.append(f"Broker-split status unknown: {candidate.broker_split_status}")
        return len(blockers) == 0, blockers

    def require_reality_gap_metrics(self, candidate: AlphaCandidate) -> tuple[bool, list[str]]:
        """Require reality-gap metrics to be present in the metrics dict.

        Reality-gap metrics compare backtest vs live/shadow performance.
        """
        blockers: list[str] = []
        m = candidate.metrics
        if "reality_gap_sharpe" not in m:
            blockers.append("Missing reality_gap_sharpe metric")
        if "reality_gap_drawdown" not in m:
            blockers.append("Missing reality_gap_drawdown metric")
        return len(blockers) == 0, blockers

    def mark_ready_for_shadow(self, candidate: AlphaCandidate) -> tuple[bool, list[str]]:
        """Mark a candidate as ready for shadow validation.

        Only after passing all required validations.
        Returns (ok, blockers).
        """
        blockers: list[str] = []

        # Must NOT be quarantined or rejected
        if candidate.validation_status in (AlphaCandidateStatus.QUARANTINED, AlphaCandidateStatus.REJECTED):
            blockers.append(f"Candidate is {candidate.validation_status.value} - cannot mark ready for shadow")
            return False, blockers

        # Run all validators
        _, meta_blockers = self.validate_candidate_metadata(candidate)
        blockers.extend(meta_blockers)

        rejected, _ = self.reject_if_leakage_flags(candidate)
        if rejected:
            blockers.append("Candidate has leakage flags - quarantined")

        ok_wf, wf_blockers = self.require_walk_forward(candidate)
        blockers.extend(wf_blockers)

        ok_bs, bs_blockers = self.require_broker_split(candidate)
        blockers.extend(bs_blockers)

        ok_rg, rg_blockers = self.require_reality_gap_metrics(candidate)
        blockers.extend(rg_blockers)

        if blockers:
            candidate.validation_status = AlphaCandidateStatus.NEEDS_REVIEW
            candidate.shadow_ready = False
            return False, blockers

        candidate.validation_status = AlphaCandidateStatus.READY_FOR_SHADOW
        candidate.shadow_ready = True
        return True, []

    def never_promote_to_champion(self) -> bool:
        """Always returns False. Alpha factory never promotes to champion.

        Promotion to champion must go through ModelLifecycleGovernance with
        explicit operator approval.
        """
        return False

    # ──────────────────────────────────────────────────────────────────────
    # Summary
    # ──────────────────────────────────────────────────────────────────────

    def summary(self) -> dict:
        """Return a summary of registered candidates."""
        candidates = list(self._candidates.values())
        return {
            "total_candidates": len(candidates),
            "by_status": self._count_by_status(candidates),
            "by_type": self._count_by_type(candidates),
            "ready_for_shadow": sum(1 for c in candidates if c.shadow_ready),
            "quarantined": sum(1 for c in candidates if c.validation_status == AlphaCandidateStatus.QUARANTINED),
            "can_promote_to_champion": False,  # always False
        }

    def _count_by_status(self, candidates: list[AlphaCandidate]) -> dict:
        counts: dict[str, int] = {}
        for c in candidates:
            k = c.validation_status.value
            counts[k] = counts.get(k, 0) + 1
        return counts

    def _count_by_type(self, candidates: list[AlphaCandidate]) -> dict:
        counts: dict[str, int] = {}
        for c in candidates:
            k = c.candidate_type.value
            counts[k] = counts.get(k, 0) + 1
        return counts
