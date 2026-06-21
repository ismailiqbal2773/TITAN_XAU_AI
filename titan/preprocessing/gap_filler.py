"""
Gap Filler
============
Fills missing bars in time series by reindexing to a canonical time grid
and interpolating values.

Strategy:
  - Reindex to expected frequency (1min for M1, 5min for M5, etc.)
  - Linear interpolation for OHLC prices (realistic for short gaps)
  - Forward-fill for spread (typically constant within session)
  - Zero-fill for volume (no trading = no volume)
  - Mark filled bars with 'is_filled' flag for transparency

Weekend/Holiday Handling:
  - XAUUSD trades Sun 23:00 UTC → Fri 22:00 UTC
  - We DO NOT fill weekend gaps (would create fake data)
  - Only fill intra-session gaps (e.g., 5-min missing bar)
"""
from __future__ import annotations
import logging
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# Trading hours: Sun 23:00 UTC → Fri 22:00 UTC
# Source: Dukascopy/IC Markets standard XAUUSD session
TRADING_HOURS = {
    "start_day": 6,   # Sunday=6
    "start_hour": 23,
    "end_day": 4,     # Friday=4
    "end_hour": 22,
}


class GapFiller:
    """Fills missing bars in intra-session time series."""

    def __init__(self, timeframe: str = "H1"):
        """
        Args:
            timeframe: M1, M5, M15, M30, H1, H4, D1
        """
        self.timeframe = timeframe
        self.freq_map = {
            "M1": "1min", "M5": "5min", "M15": "15min",
            "M30": "30min", "H1": "1h", "H4": "4h", "D1": "1D",
        }
        if timeframe not in self.freq_map:
            raise ValueError(f"Unsupported timeframe: {timeframe}")

    def _is_trading_time(self, ts: pd.Timestamp) -> bool:
        """Check if timestamp is within XAUUSD trading hours."""
        if ts.weekday() == 5:  # Saturday — closed
            return False
        if ts.weekday() == 6:  # Sunday — open from 23:00
            return ts.hour >= 23
        if ts.weekday() == 4:  # Friday — closed after 22:00
            return ts.hour < 22
        return True  # Mon-Thu — full 24h

    def fill_gaps(self, df: pd.DataFrame) -> pd.DataFrame:
        """Fill intra-session gaps with interpolation.

        Args:
            df: Canonical DataFrame with datetime UTC index

        Returns:
            DataFrame with gaps filled + 'is_filled' column
        """
        if df.empty:
            return df

        # Sort by timestamp
        df = df.sort_index()

        # Build full trading-hours time grid
        start = df.index.min()
        end = df.index.max()
        full_grid = pd.date_range(start=start, end=end,
                                   freq=self.freq_map[self.timeframe],
                                   tz="UTC")
        # Filter to trading hours only
        trading_mask = pd.Series(full_grid).apply(self._is_trading_time).values
        trading_grid = full_grid[trading_mask]

        # Reindex to full trading grid
        original_len = len(df)
        df_filled = df.reindex(trading_grid)
        n_filled = df_filled["close"].isna().sum()

        if n_filled > 0:
            # Linear interpolation for OHLC
            for col in ["open", "high", "low", "close"]:
                df_filled[col] = df_filled[col].interpolate(
                    method="time", limit_direction="both"
                )
            # Forward-fill for spread
            for col in ["spread_points", "spread_usd"]:
                if col in df_filled.columns:
                    df_filled[col] = df_filled[col].ffill().bfill()
            # Zero-fill for volume
            for col in ["tick_volume", "real_volume"]:
                df_filled[col] = df_filled[col].fillna(0).astype("int64")
            # Keep broker name
            if "broker" in df_filled.columns:
                df_filled["broker"] = df_filled["broker"].ffill().bfill()

            # Mark filled bars
            df_filled["is_filled"] = df_filled["close"].isna().astype(int) | (
                ~df_filled.index.isin(df.index)
            ).astype(int)
        else:
            df_filled["is_filled"] = 0

        # Replace any remaining NaN (edge cases) with 0
        df_filled = df_filled.fillna(0)

        new_len = len(df_filled)
        logger.info(f"  Gap fill: {original_len:,} → {new_len:,} bars "
                    f"({new_len - original_len:,} filled, "
                    f"{n_filled:,} NaN values interpolated)")

        return df_filled
