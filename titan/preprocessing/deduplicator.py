"""
Deduplicator
=============
Removes exact timestamp duplicates within a single broker's data.
MT5 typically doesn't produce duplicates, but defensive check anyway.

Strategy:
  - Group by index (timestamp)
  - For duplicates, keep LAST (most recent write wins)
  - Log how many were removed
"""
from __future__ import annotations
import logging

import pandas as pd

logger = logging.getLogger(__name__)


class Deduplicator:
    """Removes duplicate timestamps from a DataFrame."""

    def __init__(self, keep: str = "last"):
        """
        Args:
            keep: 'first', 'last', or False (drop all dups)
        """
        self.keep = keep

    def deduplicate(self, df: pd.DataFrame) -> pd.DataFrame:
        """Remove duplicate timestamps.

        Args:
            df: Canonical DataFrame with timestamp index

        Returns:
            DataFrame with duplicates removed.
        """
        before = len(df)
        df = df[~df.index.duplicated(keep=self.keep)]
        after = len(df)
        removed = before - after

        if removed > 0:
            logger.info(f"  Dedup: {before:,} → {after:,} bars "
                        f"({removed:,} duplicates removed)")
        return df
