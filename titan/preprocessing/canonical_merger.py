"""
Canonical Merger
=================
Merges 4 broker datasets into 1 unified canonical dataset.

Strategy (robust to broker outliers):
  For each timestamp:
    - open    = median(broker opens)     [robust to single-broker glitches]
    - high    = max(broker highs)        [true market high]
    - low     = min(broker lows)         [true market low]
    - close   = median(broker closes)    [robust central tendency]
    - volume  = sum(broker volumes)      [aggregated liquidity]
    - spread  = mean(broker spreads_usd) [average market spread]
    - n_brokers = count of brokers with data at this timestamp

Only timestamps present in AT LEAST 2 brokers are kept (single-broker
timestamps are suspicious — could be a glitch).

Output:
    timestamp (UTC) — index
    open, high, low, close (float64, USD)
    tick_volume (int64)
    spread_usd (float64)
    n_brokers (int)
"""
from __future__ import annotations
import logging
from typing import Dict

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class CanonicalMerger:
    """Merges multiple broker datasets into 1 canonical dataset."""

    def __init__(self, min_brokers: int = 2):
        """
        Args:
            min_brokers: Minimum brokers required at a timestamp to keep it.
        """
        self.min_brokers = min_brokers

    def merge(self, broker_data: Dict[str, pd.DataFrame]) -> pd.DataFrame:
        """Merge broker DataFrames into 1 canonical DataFrame.

        Args:
            broker_data: Dict of {broker_name: canonical DataFrame}
                         Each must have: open, high, low, close,
                                         tick_volume, spread_usd, broker

        Returns:
            Merged canonical DataFrame
        """
        if not broker_data:
            raise ValueError("No broker data provided")

        brokers = list(broker_data.keys())
        n_brokers_input = len(brokers)

        # Concatenate all brokers, keeping index (timestamp)
        all_data = pd.concat(
            [df.assign(broker=broker) for broker, df in broker_data.items()],
            ignore_index=False,
        )

        # Reset index to make timestamp a column for groupby
        all_data = all_data.reset_index()
        # The index name is 'timestamp' — make sure column exists
        if all_data.index.name != "timestamp" and "timestamp" not in all_data.columns:
            # If reset_index made a 'level_0' or 'index' column, rename it
            if "level_0" in all_data.columns:
                all_data = all_data.rename(columns={"level_0": "timestamp"})
            elif "index" in all_data.columns:
                all_data = all_data.rename(columns={"index": "timestamp"})

        logger.info(f"  Merging {n_brokers_input} brokers...")
        logger.info(f"  Total rows before merge: {len(all_data):,}")

        # Group by timestamp and aggregate
        grouped = all_data.groupby(all_data.columns[0])  # First column is timestamp
        merged = grouped.agg({
            "open": "median",
            "high": "max",
            "low": "min",
            "close": "median",
            "tick_volume": "sum",
            "spread_usd": "mean",
            "broker": "count",
        }).rename(columns={"broker": "n_brokers"})

        # Filter: keep only timestamps with >= min_brokers
        before_filter = len(merged)
        merged = merged[merged["n_brokers"] >= self.min_brokers]
        after_filter = len(merged)

        # Sort index and set as datetime UTC
        merged = merged.sort_index()
        merged.index = pd.to_datetime(merged.index, utc=True)
        merged.index.name = "timestamp"

        # Cast types
        merged["tick_volume"] = merged["tick_volume"].astype("int64")
        merged["n_brokers"] = merged["n_brokers"].astype("int64")

        logger.info(f"  Filtered (≥{self.min_brokers} brokers): "
                    f"{before_filter:,} → {after_filter:,} bars")
        logger.info(f"  Date range: {merged.index[0]} → {merged.index[-1]}")
        logger.info(f"  Avg brokers per bar: {merged['n_brokers'].mean():.2f}")

        return merged
