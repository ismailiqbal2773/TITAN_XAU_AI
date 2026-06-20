"""TITAN XAU AI — Regime Detection Package"""
from .engine import (
    RegimeDetector,
    Regime,
    RegimeResult,
    RegimeVote,
    RegimeFeatures,
    FeatureExtractor,
    HMMRegimeModel,
    LogitRegimeModel,
    HeuristicRegimeModel,
)

__all__ = [
    "RegimeDetector",
    "Regime",
    "RegimeResult",
    "RegimeVote",
    "RegimeFeatures",
    "FeatureExtractor",
    "HMMRegimeModel",
    "LogitRegimeModel",
    "HeuristicRegimeModel",
]
