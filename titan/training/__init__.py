"""
TITAN XAU AI — Model Training Preparation Module (M28)

Pipeline modules:
- data_acquisition: multi-source tick/bar ingestion
- historical_ingestion: bulk XAUUSD historical download
- feature_engine: feature generation + target construction
- dataset_validator: schema, integrity, leakage checks
- quality_scorer: 5-dimensional 0-100 quality scoring

This module is purely additive. It does not modify any existing
architecture, interface, or class. It writes to titan/data/ for
intermediate artifacts.
"""
from titan.training.data_acquisition import (
    DataAcquisitionPipeline, DataSource, Timeframe, BarData,
)
from titan.training.historical_ingestion import (
    HistoricalIngestionEngine, IngestionResult, SyntheticDataGenerator,
)
from titan.training.feature_engine import (
    FeatureEngine, FeatureSet, FeatureConfig, TargetConfig,
    StandardScaler, RobustScaler,
    FeatureSelector, FeatureSelectionReport,
)
from titan.training.dataset_validator import (
    DatasetValidator, ValidationReport, ValidationSeverity,
    time_series_train_val_test_split, SplitResult,
    PurgedKFold, PurgedFold, PurgedKFoldResult,
)
from titan.training.quality_scorer import (
    DataQualityScorer, QualityScore, QualityDimension,
)

__all__ = [
    "DataAcquisitionPipeline", "DataSource", "Timeframe", "BarData",
    "HistoricalIngestionEngine", "IngestionResult", "SyntheticDataGenerator",
    "FeatureEngine", "FeatureSet", "FeatureConfig", "TargetConfig",
    "StandardScaler", "RobustScaler",
    "FeatureSelector", "FeatureSelectionReport",
    "DatasetValidator", "ValidationReport", "ValidationSeverity",
    "time_series_train_val_test_split", "SplitResult",
    "PurgedKFold", "PurgedFold", "PurgedKFoldResult",
    "DataQualityScorer", "QualityScore", "QualityDimension",
]
