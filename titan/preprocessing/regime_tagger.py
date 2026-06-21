"""
Regime Tagger
==============
Tags each bar with market regime classification. Critical for:
  - Preventing regime overfitting (model trains on balanced regimes)
  - Enabling regime-aware feature engineering
  - Allowing regime-stratified sampling

Regime Classification (4 classes):
  TREND_UP:    Strong upward trend (MA fast > MA slow, low volatility)
  TREND_DOWN:  Strong downward trend (MA fast < MA slow, low volatility)
  RANGE:       Sideways market (MAs close, low volatility)
  VOLATILE:    High volatility regardless of direction

Indicators:
  - MA fast (20 bars)
  - MA slow (200 bars)
  - Trend strength = (MA_fast - MA_slow) / MA_slow
  - Volatility = rolling std of returns (60 bars)

Thresholds (tuned for XAUUSD):
  - VOLATILE if vol_60m > 0.0030 (0.3% per bar)
  - TREND_UP if trend_strength > +0.001 AND not volatile
  - TREND_DOWN if trend_strength < -0.001 AND not volatile
  - RANGE otherwise
"""
from __future__ import annotations
import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class RegimeTagger:
    """Tags bars with market regime classification."""

    def __init__(self,
                 ma_fast: int = 20,
                 ma_slow: int = 200,
                 vol_window: int = 60,
                 trend_threshold: float = 0.001,
                 vol_threshold: float = 0.0030):
        self.ma_fast = ma_fast
        self.ma_slow = ma_slow
        self.vol_window = vol_window
        self.trend_threshold = trend_threshold
        self.vol_threshold = vol_threshold

    def tag(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add 'regime' column to DataFrame.

        Args:
            df: Canonical DataFrame with 'close' column

        Returns:
            DataFrame with 'regime' column added.
        """
        df = df.copy()

        # Calculate indicators
        df["ret_1m"] = df["close"].pct_change()
        df["vol_60m"] = df["ret_1m"].rolling(self.vol_window).std()
        df["ma_fast"] = df["close"].rolling(self.ma_fast).mean()
        df["ma_slow"] = df["close"].rolling(self.ma_slow).mean()
        df["trend_strength"] = (
            (df["ma_fast"] - df["ma_slow"]) / df["ma_slow"]
        )

        # Classify
        conditions = [
            df["vol_60m"] > self.vol_threshold,
            df["trend_strength"] > self.trend_threshold,
            df["trend_strength"] < -self.trend_threshold,
        ]
        choices = ["VOLATILE", "TREND_UP", "TREND_DOWN"]
        df["regime"] = np.select(conditions, choices, default="RANGE")

        # Replace NaN regimes (start of series) with UNKNOWN
        df["regime"] = df["regime"].fillna("UNKNOWN")

        # Drop intermediate columns (keep only 'regime')
        df = df.drop(columns=["ret_1m", "vol_60m", "ma_fast", "ma_slow",
                              "trend_strength"])

        # Stats
        regime_counts = df["regime"].value_counts()
        total = len(df)
        logger.info(f"  Regime distribution:")
        for regime, count in regime_counts.items():
            pct = count / total * 100
            logger.info(f"    {regime:<12}: {count:>6,} ({pct:>5.2f}%)")

        return df
