"""
TITAN XAU AI - Model Registry (Sprint 9.9.3.36)
================================================

Metadata-only registry for registered models. Tracks champion, challengers,
and candidates. NEVER loads pickle or model binaries. NEVER imports MT5.

Rules:
  - Exactly one champion allowed at any time.
  - New registrations default to CANDIDATE.
  - Champion replacement requires an explicit manual approval flag.
  - Registry stores metadata only (no model artifacts).
"""
from __future__ import annotations
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

from titan.production.model_lifecycle_governance import (
    ModelLifecycleStage, ModelApprovalStatus,
)


@dataclass
class RegisteredModel:
    model_id: str
    version: str
    stage: ModelLifecycleStage
    artifact_path: str  # metadata-only reference; never loaded by registry
    metrics: dict = field(default_factory=dict)
    created_utc: str = ""
    approved_by: str = ""  # operator name; empty until manually approved
    approval_status: ModelApprovalStatus = ModelApprovalStatus.PENDING
    notes: str = ""

    def __post_init__(self):
        if not self.created_utc:
            self.created_utc = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        d = asdict(self)
        d["stage"] = self.stage.value
        d["approval_status"] = self.approval_status.value
        return d


class ModelRegistry:
    """Metadata-only model registry.

    Never loads pickle or model binaries. Never imports MT5.
    """

    def __init__(self):
        self._models: dict[str, RegisteredModel] = {}

    # ──────────────────────────────────────────────────────────────────────
    # Registration
    # ──────────────────────────────────────────────────────────────────────

    def register_model(
        self,
        model_id: str,
        version: str,
        artifact_path: str,
        metrics: Optional[dict] = None,
        notes: str = "",
    ) -> RegisteredModel:
        """Register a new model. Defaults to CANDIDATE stage and PENDING approval."""
        if model_id in self._models:
            raise ValueError(f"Model already registered: {model_id}")
        model = RegisteredModel(
            model_id=model_id,
            version=version,
            stage=ModelLifecycleStage.CANDIDATE,
            artifact_path=artifact_path,
            metrics=dict(metrics or {}),
            notes=notes,
        )
        self._models[model_id] = model
        return model

    # ──────────────────────────────────────────────────────────────────────
    # Queries
    # ──────────────────────────────────────────────────────────────────────

    def get_model(self, model_id: str) -> Optional[RegisteredModel]:
        return self._models.get(model_id)

    def get_champion(self) -> Optional[RegisteredModel]:
        """Return the current champion, or None if no champion registered."""
        for m in self._models.values():
            if m.stage == ModelLifecycleStage.CHAMPION:
                return m
        return None

    def list_challengers(self) -> list[RegisteredModel]:
        return [m for m in self._models.values() if m.stage == ModelLifecycleStage.CHALLENGER]

    def list_candidates(self) -> list[RegisteredModel]:
        return [m for m in self._models.values() if m.stage == ModelLifecycleStage.CANDIDATE]

    def list_all(self) -> list[RegisteredModel]:
        return list(self._models.values())

    # ──────────────────────────────────────────────────────────────────────
    # State transitions
    # ──────────────────────────────────────────────────────────────────────

    def reject_model(self, model_id: str, reason: str = "") -> RegisteredModel:
        """Mark a model as REJECTED."""
        m = self._require(model_id)
        m.stage = ModelLifecycleStage.REJECTED
        m.approval_status = ModelApprovalStatus.REJECTED
        if reason:
            m.notes = (m.notes + " | " if m.notes else "") + f"REJECTED: {reason}"
        return m

    def quarantine_model(self, model_id: str, reason: str = "") -> RegisteredModel:
        """Mark a model as QUARANTINED."""
        m = self._require(model_id)
        m.stage = ModelLifecycleStage.QUARANTINED
        m.approval_status = ModelApprovalStatus.BLOCKED
        if reason:
            m.notes = (m.notes + " | " if m.notes else "") + f"QUARANTINED: {reason}"
        return m

    def retire_model(self, model_id: str, reason: str = "") -> RegisteredModel:
        """Mark a model as RETIRED."""
        m = self._require(model_id)
        m.stage = ModelLifecycleStage.RETIRED
        m.approval_status = ModelApprovalStatus.APPROVED  # retirement is approved by operator
        if reason:
            m.notes = (m.notes + " | " if m.notes else "") + f"RETIRED: {reason}"
        return m

    def promote_to_challenger(
        self, model_id: str, approved_by: str
    ) -> RegisteredModel:
        """Promote a candidate to challenger. Requires operator name."""
        m = self._require(model_id)
        if m.stage not in (ModelLifecycleStage.CANDIDATE, ModelLifecycleStage.SHADOW):
            raise ValueError(
                f"Cannot promote {model_id} from {m.stage.value} to CHALLENGER"
            )
        m.stage = ModelLifecycleStage.CHALLENGER
        m.approval_status = ModelApprovalStatus.APPROVED
        m.approved_by = approved_by
        return m

    def require_manual_champion_promotion(
        self,
        model_id: str,
        approved_by: str,
        manual_approval_flag: bool = False,
    ) -> RegisteredModel:
        """Promote a model to champion.

        Requires explicit manual_approval_flag=True and an operator name.
        If a champion already exists, the existing champion is retired first.
        """
        if not manual_approval_flag:
            raise PermissionError(
                "Champion promotion requires manual_approval_flag=True - auto-promotion is forbidden"
            )
        if not approved_by:
            raise PermissionError(
                "Champion promotion requires approved_by operator name"
            )
        m = self._require(model_id)
        if m.stage in (ModelLifecycleStage.REJECTED, ModelLifecycleStage.QUARANTINED):
            raise ValueError(
                f"Cannot promote {model_id} from {m.stage.value} to CHAMPION"
            )
        # Retire any existing champion first (exactly-one-champion invariant)
        existing = self.get_champion()
        if existing is not None and existing.model_id != model_id:
            existing.stage = ModelLifecycleStage.RETIRED
            existing.notes = (existing.notes + " | " if existing.notes else "") + \
                f"RETIRED: replaced by {model_id}"
        m.stage = ModelLifecycleStage.CHAMPION
        m.approval_status = ModelApprovalStatus.APPROVED
        m.approved_by = approved_by
        return m

    # ──────────────────────────────────────────────────────────────────────
    # Persistence (metadata only)
    # ──────────────────────────────────────────────────────────────────────

    def save_registry_json(self, path) -> dict:
        """Save the registry as JSON. Metadata only - no model binaries."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "saved_utc": datetime.now(timezone.utc).isoformat(),
            "model_count": len(self._models),
            "champion_model_id": self.get_champion().model_id if self.get_champion() else None,
            "models": [m.to_dict() for m in self._models.values()],
            "safety": {
                "loads_pickle": False,
                "loads_model_binaries": False,
                "auto_promotes_champion": False,
                "imports_metatrader5": False,
            },
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, default=str, ensure_ascii=False)
        return {"path": str(path), "model_count": len(self._models)}

    def load_registry_json(self, path) -> dict:
        """Load registry from JSON. Metadata only - never loads model binaries."""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Registry file not found: {path}")
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        # Reset and reload
        self._models = {}
        for m_dict in payload.get("models", []):
            stage = ModelLifecycleStage(m_dict.get("stage", ModelLifecycleStage.CANDIDATE.value))
            approval = ModelApprovalStatus(m_dict.get("approval_status", ModelApprovalStatus.PENDING.value))
            m = RegisteredModel(
                model_id=m_dict["model_id"],
                version=m_dict.get("version", ""),
                stage=stage,
                artifact_path=m_dict.get("artifact_path", ""),
                metrics=m_dict.get("metrics", {}),
                created_utc=m_dict.get("created_utc", ""),
                approved_by=m_dict.get("approved_by", ""),
                approval_status=approval,
                notes=m_dict.get("notes", ""),
            )
            self._models[m.model_id] = m
        return {"path": str(path), "model_count": len(self._models)}

    # ──────────────────────────────────────────────────────────────────────
    # Invariant checks
    # ──────────────────────────────────────────────────────────────────────

    def has_exactly_one_champion(self) -> bool:
        """True if exactly one champion is registered."""
        count = sum(1 for m in self._models.values() if m.stage == ModelLifecycleStage.CHAMPION)
        return count == 1

    def has_no_champion(self) -> bool:
        """True if no champion is registered (initial state)."""
        count = sum(1 for m in self._models.values() if m.stage == ModelLifecycleStage.CHAMPION)
        return count == 0

    def summary(self) -> dict:
        return {
            "total_models": len(self._models),
            "champion": self.get_champion().model_id if self.get_champion() else None,
            "challenger_count": len(self.list_challengers()),
            "candidate_count": len(self.list_candidates()),
            "exactly_one_champion": self.has_exactly_one_champion(),
            "auto_promotion_allowed": False,
        }

    # ──────────────────────────────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────────────────────────────

    def _require(self, model_id: str) -> RegisteredModel:
        m = self._models.get(model_id)
        if m is None:
            raise KeyError(f"Model not registered: {model_id}")
        return m
