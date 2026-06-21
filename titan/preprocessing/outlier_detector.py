"""
Cross-Broker Outlier Detector
===============================
Detects and filters bars where one broker's price deviates significantly
from the median of all brokers. This catches:
  - Tick errors (fat-finger prints)
  - Broker feed glitches
  - Stale quotes during low-liquidity periods

Strategy:
  For each timestamp, compute median close across all brokers.
  Flag any broker whose |close - median| / median > threshold (default 0.5%).

Flagged bars are NOT deleted — they're replaced with the median value
(robust imputation) and a flag column is set for traceability.
"""
from __future__ import annotations
import logging
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class CrossBrokerOutlierDetector:
    """Detects and imputes cross-broker price outliers."""

    def __init__(self, threshold_pct: float = 0.5):
        """
        Args:
            threshold_pct: Max allowed deviation from median (in %).
                          Default 0.5% (e.g., gold $2000, max diff $10).
        """
        self.threshold_pct = threshold_pct / 100.0

    def detect(self, broker_data: Dict[str, pd.DataFrame],
                column: str = "close") -> Tuple[Dict[str, pd.DataFrame], List[dict]]:
        """Detect outliers and impute with median.

        Args:
            broker_data: Dict of {broker_name: canonical DataFrame}
            column: Price column to check (close/open/high/low)

        Returns:
            Tuple of (cleaned_broker_data, list_of_outlier_reports)
        """
        # Pivot: timestamp → broker close
        # Concatenate all brokers' close column
        all_closes = pd.DataFrame({
            broker: df[column] for broker, df in broker_data.items()
        })

        # Compute median across brokers (skip NaN)
        median_close = all_closes.median(axis=1, skipna=True)
        rel_diff = (all_closes.sub(median_close, axis=0)).div(median_close, axis=0).abs()

        outlier_reports = []
        cleaned = {}
        for broker in broker_data:
            df = broker_data[broker].copy()
            broker_outliers = rel_diff[broker] > self.threshold_pct
            n_outliers = int(broker_outliers.sum())

            if n_outliers > 0:
                # Impute with median for outlier rows
                df.loc[broker_outliers, column] = median_close[broker_outliers]
                df["outlier_imputed"] = broker_outliers.astype(int)
                outlier_reports.append({
                    "broker": broker,
                    "column": column,
                    "outliers_detected": n_outliers,
                    "outliers_pct": round(n_outliers / len(df) * 100, 4),
                    "threshold_pct": self.threshold_pct * 100,
                    "imputation": "median",
                })
                logger.info(f"  {broker} {column}: {n_outliers} outliers "
                            f"({n_outliers/len(df)*100:.4f}%) imputed with median")
            else:
                df["outlier_imputed"] = 0

            cleaned[broker] = df

        return cleaned, outlier_reports
