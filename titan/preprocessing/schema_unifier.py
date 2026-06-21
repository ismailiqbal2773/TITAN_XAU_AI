"""
Schema Unifier
===============
Converts each broker's raw parquet (MT5 schema) to a canonical schema
ready for cross-broker merging.

Canonical Schema:
    timestamp (datetime64[ns, UTC]) — index
    open, high, low, close (float64, USD)
    tick_volume (int64)
    spread_points (int64)   — kept raw for normalization later
    real_volume (int64)
    broker (str)            — source broker name (for traceability)

Input Schema (MT5 raw):
    timestamp (datetime64[ns, UTC])
    open, high, low, close (float64)
    tick_volume (int64)
    spread (int64)          — in broker's point units
    real_volume (int64)
"""
from __future__ import annotations
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class CanonicalSchema:
    """Canonical column definitions for unified data."""
    INDEX = "timestamp"
    OPEN = "open"
    HIGH = "high"
    LOW = "low"
    CLOSE = "close"
    TICK_VOLUME = "tick_volume"
    SPREAD_POINTS = "spread_points"
    REAL_VOLUME = "real_volume"
    BROKER = "broker"

    COLUMNS = [OPEN, HIGH, LOW, CLOSE, TICK_VOLUME,
               SPREAD_POINTS, REAL_VOLUME, BROKER]


class SchemaUnifier:
    """Converts raw broker parquet files to canonical schema."""

    def __init__(self):
        pass

    def unify(self, df: pd.DataFrame, broker_name: str) -> pd.DataFrame:
        """Convert a raw broker DataFrame to canonical schema.

        Args:
            df: Raw MT5 DataFrame with columns:
                [open, high, low, close, tick_volume, spread, real_volume]
            broker_name: Source broker name (exness/fundednext/fbs/icmarkets)

        Returns:
            Canonical-schema DataFrame with broker column added.
        """
        if df.empty:
            return pd.DataFrame(columns=CanonicalSchema.COLUMNS)

        # Ensure index is UTC datetime
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC")
        elif str(df.index.tz) != "UTC":
            df.index = df.index.tz_convert("UTC")
        df.index.name = CanonicalSchema.INDEX

        # Build canonical DataFrame
        out = pd.DataFrame(index=df.index)
        out[CanonicalSchema.OPEN] = df["open"].astype("float64")
        out[CanonicalSchema.HIGH] = df["high"].astype("float64")
        out[CanonicalSchema.LOW] = df["low"].astype("float64")
        out[CanonicalSchema.CLOSE] = df["close"].astype("float64")
        out[CanonicalSchema.TICK_VOLUME] = df["tick_volume"].astype("int64")
        # Rename 'spread' → 'spread_points' (raw, before normalization)
        out[CanonicalSchema.SPREAD_POINTS] = df["spread"].astype("int64")
        out[CanonicalSchema.REAL_VOLUME] = df["real_volume"].astype("int64")
        out[CanonicalSchema.BROKER] = broker_name

        return out[CanonicalSchema.COLUMNS]

    def load_broker_file(self, path: Path, broker_name: str,
                          timeframe: str = "H1") -> pd.DataFrame:
        """Load and unify a single broker parquet file."""
        df = pd.read_parquet(path)
        unified = self.unify(df, broker_name)
        logger.info(f"  {broker_name} {timeframe}: {len(unified):,} bars unified")
        return unified
