"""
Spread Normalizer
==================
Converts broker-specific spread (in points) to universal USD value.

Each broker has different point value:
    Exness:      digits=3, point=0.001  → 1 spread point = $0.001
    FundedNext:  digits=2, point=0.01   → 1 spread point = $0.01
    FBS:         digits=2, point=0.01   → 1 spread point = $0.01
    IC Markets:  digits=2, point=0.01   → 1 spread point = $0.01

After normalization, all spreads are in USD — directly comparable.
"""
from __future__ import annotations
import logging
from typing import Dict

import pandas as pd

logger = logging.getLogger(__name__)


# Broker point values (from MT5 verification JSONs)
BROKER_POINT_VALUES: Dict[str, float] = {
    "exness":      0.001,   # digits=3
    "fundednext":  0.01,    # digits=2
    "fbs":         0.01,    # digits=2
    "icmarkets":   0.01,    # digits=2
    # Default for unknown brokers (assume 2 digits = $0.01/point)
    "default":     0.01,
}


class SpreadNormalizer:
    """Normalizes broker spread (points → USD)."""

    def __init__(self, broker_point_values: Dict[str, float] = None):
        self.point_values = broker_point_values or BROKER_POINT_VALUES

    def normalize(self, df: pd.DataFrame, broker_name: str) -> pd.DataFrame:
        """Add 'spread_usd' column to canonical DataFrame.

        Args:
            df: Canonical DataFrame with 'spread_points' column
            broker_name: Broker name to look up point value

        Returns:
            DataFrame with new 'spread_usd' column added.
        """
        if "spread_points" not in df.columns:
            raise ValueError("DataFrame missing 'spread_points' column")

        point_value = self.point_values.get(
            broker_name, self.point_values["default"]
        )
        df = df.copy()
        df["spread_usd"] = df["spread_points"] * point_value

        # Stats
        mean_pts = df["spread_points"].mean()
        mean_usd = df["spread_usd"].mean()
        logger.info(f"  {broker_name}: spread normalized "
                    f"(mean {mean_pts:.2f} pts → ${mean_usd:.4f})")
        return df

    def normalize_all(self, broker_data: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]:
        """Normalize spread for all brokers in dict."""
        return {
            broker: self.normalize(df, broker)
            for broker, df in broker_data.items()
        }
