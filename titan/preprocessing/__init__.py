"""
TITAN XAU AI — Data Preprocessing Subpackage
=============================================
World-class data preprocessing pipeline for 4-broker XAUUSD data.

Handles:
  - Schema unification (4 brokers → 1 canonical schema)
  - Spread normalization (points → USD using broker's point value)
  - Cross-broker outlier detection (deviation from median)
  - Gap filling (interpolation for missing bars)
  - Deduplication (by timestamp)
  - Regime tagging (TREND_UP/DOWN/RANGE/VOLATILE)
  - Class balancing (SMOTE for direction labels)
  - Canonical merge (combine 4 brokers → 1 unified dataset)

Anti-Overfit/Underfit Strategy:
  - Median-based merge (robust to broker outliers)
  - PurgedKFold cross-validation (purge=60 bars, embargo=10)
  - Train-only scaler fit (no leakage)
  - Regime-balanced sampling (prevents regime overfitting)
  - SMOTE for direction class imbalance
  - Feature selection (drop |r|>0.95 + zero-variance)

Usage:
    from titan.preprocessing import PreprocessingPipeline
    pipeline = PreprocessingPipeline()
    canonical = pipeline.run()  # processes all 4 brokers → 1 unified dataset
"""
from .schema_unifier import SchemaUnifier, CanonicalSchema
from .spread_normalizer import SpreadNormalizer
from .outlier_detector import CrossBrokerOutlierDetector
from .gap_filler import GapFiller
from .deduplicator import Deduplicator
from .regime_tagger import RegimeTagger
from .class_balancer import ClassBalancer
from .canonical_merger import CanonicalMerger
from .pipeline import PreprocessingPipeline

__all__ = [
    "SchemaUnifier", "CanonicalSchema",
    "SpreadNormalizer",
    "CrossBrokerOutlierDetector",
    "GapFiller",
    "Deduplicator",
    "RegimeTagger",
    "ClassBalancer",
    "CanonicalMerger",
    "PreprocessingPipeline",
]
