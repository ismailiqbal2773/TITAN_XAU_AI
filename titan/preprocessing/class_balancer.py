"""
Class Balancer
================
Handles class imbalance for direction prediction labels.

For XAUUSD direction prediction (3 classes):
  - UP:    next bar close > current close
  - DOWN:  next bar close < current close
  - FLAT:  |change| < threshold (0.01% default)

Markets typically have ~33% each class, but during strong trends
one class can dominate (e.g., 60% UP in bull market). This causes
the model to be biased toward majority class.

Strategy:
  - Stratified undersampling (keep all minority, downsample majority)
  - For H1 data, ~50K bars is plenty — undersampling is fine
  - For M1 data (1.7M bars), use regime-stratified sampling instead

This module is OPTIONAL — only used when training direction classifier.
For regression models (next bar return), class balancing doesn't apply.
"""
from __future__ import annotations
import logging
from typing import Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class ClassBalancer:
    """Balances direction classes via stratified undersampling."""

    def __init__(self, flat_threshold_pct: float = 0.01):
        """
        Args:
            flat_threshold_pct: Bars with |return| below this % → FLAT
        """
        self.flat_threshold = flat_threshold_pct / 100.0

    def label_direction(self, df: pd.DataFrame,
                         horizon: int = 1) -> pd.Series:
        """Create direction labels (UP/DOWN/FLAT) for next-N-bar return.

        Args:
            df: DataFrame with 'close' column
            horizon: Number of bars ahead to predict (default=1)

        Returns:
            Series of labels (UP/DOWN/FLAT)
        """
        future_return = df["close"].shift(-horizon) / df["close"] - 1
        labels = pd.Series("FLAT", index=df.index)
        labels[future_return > self.flat_threshold] = "UP"
        labels[future_return < -self.flat_threshold] = "DOWN"
        # Last `horizon` bars have no future → drop
        labels.iloc[-horizon:] = None
        return labels

    def balance(self, df: pd.DataFrame, labels: pd.Series
                ) -> Tuple[pd.DataFrame, pd.Series]:
        """Undersample majority classes to match minority count.

        Args:
            df: Feature DataFrame
            labels: Direction labels (UP/DOWN/FLAT)

        Returns:
            Tuple of (balanced_df, balanced_labels)
        """
        # Drop NaN labels
        valid = labels.notna()
        df = df[valid].copy()
        labels = labels[valid].copy()

        # Count per class
        counts = labels.value_counts()
        minority_count = counts.min()
        logger.info(f"  Class distribution before balancing:")
        for cls, cnt in counts.items():
            logger.info(f"    {cls:<6}: {cnt:>6,} ({cnt/len(labels)*100:.2f}%)")
        logger.info(f"  Target per class: {minority_count:,} (undersample majority)")

        # Stratified undersample
        indices = []
        for cls in counts.index:
            cls_indices = labels[labels == cls].index
            if len(cls_indices) > minority_count:
                sampled = cls_indices.to_series().sample(
                    minority_count, random_state=42
                ).index
            else:
                sampled = cls_indices
            indices.extend(sampled)

        # Shuffle to mix classes
        np.random.seed(42)
        np.random.shuffle(indices)

        balanced_df = df.loc[indices].sort_index()
        balanced_labels = labels.loc[indices].sort_index()

        # Stats after balancing
        counts_after = balanced_labels.value_counts()
        logger.info(f"  Class distribution after balancing:")
        for cls, cnt in counts_after.items():
            logger.info(f"    {cls:<6}: {cnt:>6,} ({cnt/len(balanced_labels)*100:.2f}%)")

        return balanced_df, balanced_labels
