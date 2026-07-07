"""
TITAN XAU AI — Model Registry (Sprint v2.8.7-E)
=================================================
Central registry of all model profiles available to production and research.

Profiles:
  - v1_legacy:               original v1 models (xgboost_v1.pkl + meta_label_v2_context.pkl)
                             + v1 55-feature schema (with absolute-price features)
  - v2_feature_normalized:   v2 models (xgboost_v2_feature_normalized.pkl +
                             meta_label_v2_feature_normalized.pkl) + v2 55-feature
                             schema (with relative/stationary features)

Default for production runtime: v1_legacy (until v2 is fully validated).
Research scripts can select: --model-profile v2_feature_normalized

This module NEVER sends orders. NEVER creates tokens. NEVER trades.
"""
from __future__ import annotations

import os
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


@dataclass
class ModelProfile:
    """A model profile entry in the registry."""
    name: str
    description: str
    xgb_path: str
    meta_path: str
    scaler_path: Optional[str]
    schema_path: Optional[str]
    feature_schema_version: str  # "v1" or "v2"
    production_default: bool
    research_allowed: bool


# ─── Registry ───────────────────────────────────────────────────────────────

_PROFILES: dict[str, ModelProfile] = {
    "v1_legacy": ModelProfile(
        name="v1_legacy",
        description="Original v1 models with absolute-price features (drift-prone in OOS)",
        xgb_path=os.path.join(REPO_ROOT, "titan", "data", "models", "xgboost_v1.pkl"),
        meta_path=os.path.join(REPO_ROOT, "titan", "data", "models",
                                "meta_label_v2_context.pkl"),
        scaler_path=os.path.join(REPO_ROOT, "titan", "data", "features",
                                  "scaler_stats.json"),
        schema_path=None,
        feature_schema_version="v1",
        production_default=True,
        research_allowed=True,
    ),
    "v2_feature_normalized": ModelProfile(
        name="v2_feature_normalized",
        description="v2 models with relative/stationary features (drift-resistant)",
        xgb_path=os.path.join(REPO_ROOT, "titan", "data", "models",
                               "xgboost_v2_feature_normalized.pkl"),
        meta_path=os.path.join(REPO_ROOT, "titan", "data", "models",
                                "meta_label_v2_feature_normalized.pkl"),
        scaler_path=os.path.join(REPO_ROOT, "titan", "data", "features_v2",
                                  "scaler_stats_v2.json"),
        schema_path=os.path.join(REPO_ROOT, "titan", "data", "features_v2",
                                  "feature_schema_v2.json"),
        feature_schema_version="v2",
        production_default=False,  # NOT default until fully validated
        research_allowed=True,
    ),
    "v2_multibroker": ModelProfile(
        name="v2_multibroker",
        description="v2 models trained on 5 brokers (canonical+exness+fbs+fundednext+icmarkets) for broker generalization",
        xgb_path=os.path.join(REPO_ROOT, "titan", "data", "models",
                               "xgboost_v2_multibroker.pkl"),
        meta_path=os.path.join(REPO_ROOT, "titan", "data", "models",
                                "meta_label_v2_multibroker.pkl"),
        scaler_path=os.path.join(REPO_ROOT, "titan", "data", "features_v2_multibroker",
                                  "scaler_stats_v2_multibroker.json"),
        schema_path=os.path.join(REPO_ROOT, "titan", "data", "features_v2_multibroker",
                                  "feature_schema_v2_multibroker.json"),
        feature_schema_version="v2",
        production_default=False,  # NOT default until fully validated
        research_allowed=True,
    ),
}


def get_profile(name: str = "v1_legacy") -> ModelProfile:
    """Get a model profile by name. Defaults to v1_legacy (production default)."""
    if name not in _PROFILES:
        raise ValueError(
            f"Unknown model profile: {name!r}. "
            f"Available: {list(_PROFILES.keys())}"
        )
    return _PROFILES[name]


def list_profiles() -> list[str]:
    """List all available model profile names."""
    return list(_PROFILES.keys())


def get_default_profile_name() -> str:
    """Return the production-default profile name."""
    for name, profile in _PROFILES.items():
        if profile.production_default:
            return name
    return "v1_legacy"


def is_research_allowed(name: str) -> bool:
    """Check if a profile is allowed for research use."""
    return get_profile(name).research_allowed


# ─── Backward-compatible ModelRegistry (Sprint v2.8.7-O) ───────────────
# The original model_registry.py had a ModelRegistry class with champion/
# challenger/candidate lifecycle management. The v2.8.7-E rewrite replaced
# it with ModelProfile (for model profile selection). This backward-compatible
# layer restores ModelRegistry + RegisteredModel so test_model_registry.py
# passes without breaking the new profile-based logic.
#
# We import the lifecycle enums from model_lifecycle_governance so that
# the test assertions (which use ModelLifecycleStage from that module) match.

from titan.production.model_lifecycle_governance import (
    ModelLifecycleStage, ModelApprovalStatus,
)


@dataclass
class RegisteredModel:
    """A model entry in the ModelRegistry."""
    model_id: str
    version: str
    artifact_path: str
    stage: ModelLifecycleStage = ModelLifecycleStage.CANDIDATE
    approval_status: ModelApprovalStatus = ModelApprovalStatus.PENDING
    approved_by: str = ""
    metrics: dict = field(default_factory=dict)
    registered_at: str = ""
    reason: str = ""

    def __post_init__(self):
        if not self.registered_at:
            self.registered_at = datetime.now(timezone.utc).isoformat()


class ModelRegistry:
    """Backward-compatible model lifecycle registry.
    
    Manages champion/challenger/candidate model lifecycle with safety:
    - No auto-promotion (manual flag required)
    - No pickle/model binary loading
    - No MetaTrader5 import
    - No order_send
    """

    def __init__(self):
        self._models: dict[str, RegisteredModel] = {}

    def register_model(self, model_id: str, version: str,
                       artifact_path: str, metrics: dict = None) -> RegisteredModel:
        if model_id in self._models:
            raise ValueError(f"Model {model_id} already registered")
        m = RegisteredModel(
            model_id=model_id, version=version,
            artifact_path=artifact_path, metrics=metrics or {},
        )
        self._models[model_id] = m
        return m

    def get_model(self, model_id: str) -> Optional[RegisteredModel]:
        return self._models.get(model_id)

    def promote_to_challenger(self, model_id: str, approved_by: str) -> RegisteredModel:
        m = self._models[model_id]
        if m.stage in (ModelLifecycleStage.QUARANTINED, ModelLifecycleStage.REJECTED):
            raise ValueError(f"Cannot promote {model_id} from {m.stage}")
        m.stage = ModelLifecycleStage.CHALLENGER
        m.approved_by = approved_by
        m.approval_status = ModelApprovalStatus.NEEDS_REVIEW
        return m

    def require_manual_champion_promotion(self, model_id: str,
                                           approved_by: str,
                                           manual_approval_flag: bool) -> RegisteredModel:
        if not manual_approval_flag:
            raise PermissionError("Manual approval flag is required")
        if not approved_by:
            raise PermissionError("Operator name is required")
        m = self._models[model_id]
        if m.stage in (ModelLifecycleStage.QUARANTINED, ModelLifecycleStage.REJECTED):
            raise ValueError(f"Cannot promote {model_id} from {m.stage}")
        # Retire current champion if exists
        for other in self._models.values():
            if other.stage == ModelLifecycleStage.CHAMPION and other.model_id != model_id:
                other.stage = ModelLifecycleStage.RETIRED
        m.stage = ModelLifecycleStage.CHAMPION
        m.approval_status = ModelApprovalStatus.APPROVED
        m.approved_by = approved_by
        return m

    def reject_model(self, model_id: str, reason: str) -> RegisteredModel:
        m = self._models[model_id]
        m.stage = ModelLifecycleStage.REJECTED
        m.approval_status = ModelApprovalStatus.REJECTED
        m.reason = reason
        return m

    def quarantine_model(self, model_id: str, reason: str) -> RegisteredModel:
        m = self._models[model_id]
        m.stage = ModelLifecycleStage.QUARANTINED
        m.approval_status = ModelApprovalStatus.BLOCKED
        m.reason = reason
        return m

    def retire_model(self, model_id: str, reason: str) -> RegisteredModel:
        m = self._models[model_id]
        m.stage = ModelLifecycleStage.RETIRED
        m.reason = reason
        return m

    def get_champion(self) -> Optional[RegisteredModel]:
        for m in self._models.values():
            if m.stage == ModelLifecycleStage.CHAMPION:
                return m
        return None

    def has_exactly_one_champion(self) -> bool:
        return sum(1 for m in self._models.values()
                   if m.stage == ModelLifecycleStage.CHAMPION) == 1

    def has_no_champion(self) -> bool:
        return self.get_champion() is None

    def list_challengers(self) -> list:
        return [m for m in self._models.values()
                if m.stage == ModelLifecycleStage.CHALLENGER]

    def list_candidates(self) -> list:
        return [m for m in self._models.values()
                if m.stage == ModelLifecycleStage.CANDIDATE]

    def summary(self) -> dict:
        return {
            "total_models": len(self._models),
            "champion": self.get_champion().model_id if self.get_champion() else None,
            "candidate_count": len(self.list_candidates()),
            "challenger_count": len(self.list_challengers()),
            "exactly_one_champion": self.has_exactly_one_champion(),
            "auto_promotion_allowed": False,
        }

    def save_registry_json(self, path) -> dict:
        data = {
            "model_count": len(self._models),
            "models": {k: {"model_id": v.model_id, "version": v.version,
                           "stage": v.stage.value, "approved_by": v.approved_by,
                           "metrics": v.metrics}
                      for k, v in self._models.items()},
            "safety": {
                "loads_pickle": False,
                "loads_model_binaries": False,
                "auto_promotes_champion": False,
                "imports_metatrader5": False,
            },
        }
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        return {"path": str(path), "model_count": len(self._models)}

    def load_registry_json(self, path) -> dict:
        if not os.path.exists(path):
            raise FileNotFoundError(f"Registry file not found: {path}")
        with open(path) as f:
            data = json.load(f)
        self._models.clear()
        for k, v in data.get("models", {}).items():
            m = RegisteredModel(
                model_id=v["model_id"], version=v["version"],
                artifact_path="",  # not persisted for safety
            )
            m.stage = ModelLifecycleStage(v["stage"])
            m.approved_by = v.get("approved_by", "")
            m.metrics = v.get("metrics", {})
            self._models[k] = m
        return {"model_count": len(self._models)}


__all__ = [
    "ModelProfile",
    "get_profile",
    "list_profiles",
    "get_default_profile_name",
    "is_research_allowed",
    "ModelRegistry",
    "RegisteredModel",
]
