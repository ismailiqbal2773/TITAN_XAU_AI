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
from dataclasses import dataclass, field
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


__all__ = [
    "ModelProfile",
    "get_profile",
    "list_profiles",
    "get_default_profile_name",
    "is_research_allowed",
]
