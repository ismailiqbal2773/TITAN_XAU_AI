"""
TITAN Feature Pipeline Adapter
================================
Connects canonical preprocessed data → architect's FeatureEngine.

Architect (M28.3) provides:
  - FeatureEngine with 6 feature groups: price, technical, volatility,
    microstructure, time, lag
  - StandardScaler (with ±5σ clip) — train-only fit
  - RobustScaler (with ±5σ clip) — train-only fit
  - FeatureSelector (drops |r|>0.95 + zero-variance)

This adapter:
  - Maps canonical schema (tick_volume → volume) for architect's engine
  - Calls architect's FeatureEngine.generate()
  - Applies scalers (TRAIN-ONLY fit to prevent leakage)
  - Applies FeatureSelector (TRAIN-ONLY fit)
  - Splits into train/val/test with purge=60 + embargo=10
  - Returns ready-to-train (X, y) matrices

Anti-leakage measures:
  - Scaler fit on TRAIN ONLY (no val/test data leaks into scaler)
  - FeatureSelector fit on TRAIN ONLY
  - Purge gap of 60 bars between train and val (prevents label leakage)
  - Embargo of 10 bars after train (extra safety margin)

Usage:
    from titan.preprocessing.feature_pipeline import FeaturePipeline
    fp = FeaturePipeline(timeframe="H1")
    result = fp.run()
    # result.train.X, result.train.y, result.val.X, result.val.y, ...
"""
from __future__ import annotations
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from titan.training.feature_engine import (
    FeatureEngine, FeatureConfig, StandardScaler, RobustScaler, FeatureSelector,
)

logger = logging.getLogger(__name__)


PROJECT_ROOT = Path("/tmp/titan_audit")
DEFAULT_CANONICAL_DIR = PROJECT_ROOT / "titan" / "data" / "canonical"
DEFAULT_FEATURES_DIR = PROJECT_ROOT / "titan" / "data" / "features"


@dataclass
class SplitResult:
    """One split (train/val/test)."""
    X: pd.DataFrame
    y: pd.Series
    indices: pd.DatetimeIndex


@dataclass
class FeaturePipelineResult:
    """Output of feature pipeline run."""
    train: SplitResult
    val: SplitResult
    test: SplitResult
    feature_names: list[str]
    feature_groups: dict[str, list[str]]
    scaler_stats: dict
    selector_stats: dict
    n_features_before_selection: int
    n_features_after_selection: int
    purge_bars: int
    embargo_bars: int


class FeaturePipeline:
    """Adapter: canonical data → architect's FeatureEngine → train/val/test."""

    def __init__(self,
                 timeframe: str = "H1",
                 canonical_dir: Path = None,
                 output_dir: Path = None,
                 purge_bars: int = 60,
                 embargo_bars: int = 10,
                 train_pct: float = 0.70,
                 val_pct: float = 0.15):
        """
        Args:
            timeframe: M5/M15/M30/H1
            canonical_dir: Path to canonical parquet files
            output_dir: Where to save feature parquet files
            purge_bars: Bars to skip between train/val (label leakage prevention)
            embargo_bars: Extra safety margin after train
            train_pct: % of data for training (default 70%)
            val_pct: % for validation (default 15%, remaining 15% for test)
        """
        self.timeframe = timeframe
        self.canonical_dir = canonical_dir or DEFAULT_CANONICAL_DIR
        self.output_dir = output_dir or DEFAULT_FEATURES_DIR
        self.purge_bars = purge_bars
        self.embargo_bars = embargo_bars
        self.train_pct = train_pct
        self.val_pct = val_pct
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Use architect's FeatureEngine
        self.engine = FeatureEngine(FeatureConfig())

    def _load_canonical(self) -> pd.DataFrame:
        """Load canonical parquet, adapt schema for architect's engine."""
        path = self.canonical_dir / f"XAUUSD_{self.timeframe}_canonical.parquet"
        if not path.exists():
            raise FileNotFoundError(f"Canonical data not found: {path}")
        df = pd.read_parquet(path)
        logger.info(f"  Loaded {len(df):,} bars from {path.name}")

        # Adapt schema for architect's FeatureEngine
        # Architect expects: open, high, low, close, volume, spread
        # Canonical has:    open, high, low, close, tick_volume, spread_usd
        df = df.rename(columns={
            "tick_volume": "volume",
            "spread_usd": "spread",
        })

        return df

    def _generate_features(self, df: pd.DataFrame) -> tuple:
        """Run architect's FeatureEngine to generate all features."""
        logger.info("  Running architect's FeatureEngine...")
        feature_set = self.engine.generate(df)
        X = feature_set.features
        y = feature_set.targets
        logger.info(f"  Generated {X.shape[1]} features × {X.shape[0]:,} bars")
        for group, cols in feature_set.feature_groups.items():
            logger.info(f"    {group}: {len(cols)} features")
        return X, y, feature_set.feature_groups

    def _split_with_purge(self, X: pd.DataFrame, y: pd.Series
                          ) -> tuple[SplitResult, SplitResult, SplitResult]:
        """Split into train/val/test with purge gap + embargo.

        Layout:
        [TRAIN...........................][PURGE=60][EMBARGO=10][VAL....][TEST....]

        Purge gap prevents label leakage (labels look forward `horizon` bars).
        Embargo provides extra safety margin.
        """
        n = len(X)
        train_end = int(n * self.train_pct)
        val_end = int(n * (self.train_pct + self.val_pct))

        # Train: 0 → train_end
        train_X = X.iloc[:train_end]
        train_y = y.iloc[:train_end]

        # Val: starts AFTER purge + embargo
        val_start = train_end + self.purge_bars + self.embargo_bars
        val_X = X.iloc[val_start:val_end]
        val_y = y.iloc[val_start:val_end]

        # Test: AFTER another purge between val and test
        test_start = val_end + self.purge_bars + self.embargo_bars
        test_X = X.iloc[test_start:]
        test_y = y.iloc[test_start:]

        logger.info(f"  Split (purge={self.purge_bars}, embargo={self.embargo_bars}):")
        logger.info(f"    Train: {len(train_X):,} bars "
                    f"({train_X.index[0]} → {train_X.index[-1]})")
        logger.info(f"    Val:   {len(val_X):,} bars "
                    f"({val_X.index[0] if len(val_X) else 'N/A'} → "
                    f"{val_X.index[-1] if len(val_X) else 'N/A'})")
        logger.info(f"    Test:  {len(test_X):,} bars "
                    f"({test_X.index[0] if len(test_X) else 'N/A'} → "
                    f"{test_X.index[-1] if len(test_X) else 'N/A'})")

        return (
            SplitResult(train_X, train_y, train_X.index),
            SplitResult(val_X, val_y, val_X.index),
            SplitResult(test_X, test_y, test_X.index),
        )

    def _fit_scalers_train_only(self, train_X: pd.DataFrame) -> tuple:
        """Fit StandardScaler + RobustScaler on TRAIN ONLY (no leakage)."""
        logger.info("  Fitting scalers on TRAIN ONLY (no leakage)...")
        std_scaler = StandardScaler(clip=5.0)
        std_scaler.fit(train_X)

        robust_scaler = RobustScaler(clip=5.0)
        robust_scaler.fit(train_X)

        return std_scaler, robust_scaler

    def _transform_with_scaler(self, X: pd.DataFrame,
                                std_scaler: StandardScaler,
                                robust_scaler: RobustScaler) -> pd.DataFrame:
        """Apply both scalers: standardized + robust-scaled columns."""
        std_X = std_scaler.transform(X)
        robust_X = robust_scaler.transform(X)
        # Combine: use standardized for normal features, robust for outliers
        # For simplicity, use standardized (architect's recommended default)
        return std_X

    def _fit_selector_train_only(self, train_X: pd.DataFrame) -> FeatureSelector:
        """Fit FeatureSelector on TRAIN ONLY."""
        logger.info("  Fitting FeatureSelector on TRAIN ONLY...")
        selector = FeatureSelector(
            variance_threshold=1e-10,
            correlation_threshold=0.95,
        )
        selector.fit(train_X)
        kept = sum(selector.kept_) if hasattr(selector, "kept_") else 0
        dropped = train_X.shape[1] - kept
        logger.info(f"    Kept: {kept} / {train_X.shape[1]} features "
                    f"(dropped {dropped} due to low variance or high correlation)")
        return selector

    def _save_features(self, result: FeaturePipelineResult) -> Path:
        """Save train/val/test features to parquet."""
        prefix = f"XAUUSD_{self.timeframe}"
        for split_name, split in [("train", result.train),
                                   ("val", result.val),
                                   ("test", result.test)]:
            if len(split.X) == 0:
                continue
            X_path = self.output_dir / f"{prefix}_X_{split_name}.parquet"
            y_path = self.output_dir / f"{prefix}_y_{split_name}.parquet"
            split.X.to_parquet(X_path, compression="snappy")
            split.y.to_frame().to_parquet(y_path, compression="snappy")
            logger.info(f"    Saved {split_name}: X={split.X.shape}, y={split.y.shape}")

        return self.output_dir

    def run(self) -> FeaturePipelineResult:
        """Execute full feature pipeline."""
        logger.info("=" * 70)
        logger.info(f"FEATURE PIPELINE — {self.timeframe}")
        logger.info("=" * 70)

        # Step 1: Load canonical
        logger.info("\nSTEP 1: Load canonical data")
        df = self._load_canonical()

        # Step 2: Generate features (architect's FeatureEngine)
        logger.info("\nSTEP 2: Generate features (architect's engine)")
        X, y, feature_groups = self._generate_features(df)

        # Drop rows with NaN (first 200 bars have NaN due to MA periods)
        # Drop rows with NaN (first 200 bars have NaN due to MA periods)
        # Use separate masks to avoid pandas alignment issues
        X_valid = X.notna().all(axis=1)
        y_series = y["target_ret_1"] if hasattr(y, "columns") else y
        y_valid = y_series.notna()
        valid_mask = X_valid valid_mask = X_valid & y_valid.values y_valid
        n_dropped = int(len(X) - valid_mask.sum())
        X = X[valid_mask].copy()
        y = y_series[valid_mask].copy()
        logger.info(f"\n  Dropped {n_dropped:,} rows with NaN (warmup period)")

        # Step 3: Split with purge + embargo
        logger.info("\nSTEP 3: Split train/val/test (purge + embargo)")
        train, val, test = self._split_with_purge(X, y)

        # Step 4: Fit scalers on TRAIN ONLY (anti-leakage)
        logger.info("\nSTEP 4: Fit scalers on TRAIN ONLY")
        std_scaler, robust_scaler = self._fit_scalers_train_only(train.X)

        # Step 5: Apply scaler to all splits
        logger.info("\nSTEP 5: Apply scaler (train-only fit) to all splits")
        train_X_scaled = self._transform_with_scaler(train.X, std_scaler, robust_scaler)
        val_X_scaled = self._transform_with_scaler(val.X, std_scaler, robust_scaler)
        test_X_scaled = self._transform_with_scaler(test.X, std_scaler, robust_scaler)

        # Step 6: Feature selection (fit on TRAIN ONLY)
        logger.info("\nSTEP 6: Feature selection (train-only fit)")
        selector = self._fit_selector_train_only(train_X_scaled)

        # Apply selector to all splits
        train_X_final = selector.transform(train_X_scaled)
        val_X_final = selector.transform(val_X_scaled)
        test_X_final = selector.transform(test_X_scaled)

        # Step 7: Save
        logger.info("\nSTEP 7: Save feature parquets")
        result = FeaturePipelineResult(
            train=SplitResult(train_X_final, train.y, train_X_final.index),
            val=SplitResult(val_X_final, val.y, val_X_final.index),
            test=SplitResult(test_X_final, test.y, test_X_final.index),
            feature_names=list(train_X_final.columns),
            feature_groups=feature_groups,
            scaler_stats={"method": "StandardScaler (clip=5σ), train-only fit"},
            selector_stats={"method": "Variance + Correlation (|r|>0.95 drop), train-only fit"},
            n_features_before_selection=train.X.shape[1],
            n_features_after_selection=train_X_final.shape[1],
            purge_bars=self.purge_bars,
            embargo_bars=self.embargo_bars,
        )
        self._save_features(result)

        logger.info("\n" + "=" * 70)
        logger.info("FEATURE PIPELINE COMPLETE")
        logger.info("=" * 70)
        logger.info(f"  Train: {result.train.X.shape}")
        logger.info(f"  Val:   {result.val.X.shape}")
        logger.info(f"  Test:  {result.test.X.shape}")
        logger.info(f"  Features: {result.n_features_before_selection} → "
                    f"{result.n_features_after_selection} (after selection)")
        logger.info(f"  Purge: {result.purge_bars} bars, Embargo: {result.embargo_bars} bars")

        return result


if __name__ == "__main__":
    import sys
    timeframe = sys.argv[1] if len(sys.argv) > 1 else "H1"
    fp = FeaturePipeline(timeframe=timeframe)
    result = fp.run()
    print(f"\nFinal shapes:")
    print(f"  Train: X={result.train.X.shape}, y={result.train.y.shape}")
    print(f"  Val:   X={result.val.X.shape}, y={result.val.y.shape}")
    print(f"  Test:  X={result.test.X.shape}, y={result.test.y.shape}")
