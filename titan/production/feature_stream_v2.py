"""
TITAN XAU AI — Feature Stream v2 (Sprint v2.8.7-E)
====================================================
Live/inference v2 feature stream — same math as feature_engine_v2.py
but supports rolling window operation and loading from canonical/MT5.

Replaces 5 absolute-price features with relative equivalents to fix
the OOS feature drift identified in Sprint v2.8.7-D.

This module NEVER sends orders. NEVER creates tokens. NEVER trades.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

from titan.production.spread_normalization import normalize_xauusd_spread_to_usd
from titan.training.feature_engine_v2 import (
    compute_v2_features,
    standardize_v2,
    compute_scaler_stats_v2,
    MIN_BARS_FOR_FULL_FEATURES_V2,
)
from titan.training.feature_schema_v2 import (
    FEATURE_NAMES_V2,
    N_FEATURES_V2,
    META_FEATURE_NAMES_V2,
)

logger = logging.getLogger(__name__)


@dataclass
class FeatureVectorV2:
    """Latest computed v2 feature vector."""
    timestamp: pd.Timestamp
    features: np.ndarray           # shape (55,)
    feature_names: list[str]
    n_bars_used: int
    source: str
    schema_version: str = "v2"
    is_valid: bool = True
    error: Optional[str] = None
    invalid_features: Optional[list] = None  # v2.8.7-P2.5.2: feature names with NaN/inf


class H1FeatureStreamV2:
    """
    Rolling H1 feature stream v2.

    Maintains an in-memory buffer of recent H1 OHLCV bars and emits the
    55-feature v2 vector (with relative replacements for the 5 absolute
    features). Loads scaler_stats_v2.json for standardization.
    """

    def __init__(self, window: int = 300, canonical_path: Optional[str] = None):
        if window < MIN_BARS_FOR_FULL_FEATURES_V2:
            raise ValueError(
                f"window must be >= {MIN_BARS_FOR_FULL_FEATURES_V2} bars"
            )
        self.window = window
        self._bars: pd.DataFrame = pd.DataFrame(
            columns=["open", "high", "low", "close", "volume", "spread"]
        )
        self._canonical_path = canonical_path or self._default_canonical_path()
        self._canonical_loaded = False
        # v2 scaler stats
        self._train_mean: Optional[np.ndarray] = None
        self._train_std: Optional[np.ndarray] = None
        self._scaler_loaded = False
        self._load_training_scaler_v2()

    @staticmethod
    def _default_canonical_path() -> str:
        repo_root = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..")
        )
        return os.path.join(repo_root, "titan", "data", "canonical",
                            "XAUUSD_H1_canonical.parquet")

    @staticmethod
    def _default_scaler_path() -> str:
        repo_root = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..")
        )
        return os.path.join(repo_root, "titan", "data", "features_v2",
                            "scaler_stats_v2.json")

    def _load_training_scaler_v2(self) -> None:
        """Load v2 scaler stats for standardization."""
        scaler_path = self._default_scaler_path()
        if not os.path.exists(scaler_path):
            logger.warning(
                f"v2 scaler_stats_v2.json not found at {scaler_path} — "
                f"features will NOT be standardized. Run training first."
            )
            return
        try:
            with open(scaler_path, "r", encoding="utf-8") as f:
                scaler = json.load(f)
            self._train_mean = np.array(
                [scaler["mean"][f] for f in FEATURE_NAMES_V2], dtype=np.float64
            )
            self._train_std = np.array(
                [scaler["std"][f] for f in FEATURE_NAMES_V2], dtype=np.float64
            )
            self._scaler_loaded = True
            logger.info(
                f"v2 scaler loaded: {len(self._train_mean)} features"
            )
        except Exception as e:
            logger.error(f"Failed to load v2 scaler: {e}")

    def _standardize(self, vec: np.ndarray) -> np.ndarray:
        if not self._scaler_loaded or self._train_mean is None:
            return vec
        return standardize_v2(vec, self._train_mean, self._train_std)

    # ─── Bar ingestion ──────────────────────────────────────────────────

    def push_bars(self, bars: pd.DataFrame) -> None:
        """Push a DataFrame of bars (with either spread_usd or spread column).

        Spread is normalized to USD via normalize_xauusd_spread_to_usd.
        """
        if bars.empty:
            return
        df = bars.copy()
        if not isinstance(df.index, pd.DatetimeIndex):
            if "timestamp" in df.columns or "time" in df.columns:
                df = df.set_index("timestamp" if "timestamp" in df.columns else "time")
            else:
                df.index = pd.to_datetime(df.index)
        if "volume" not in df.columns and "tick_volume" in df.columns:
            df = df.rename(columns={"tick_volume": "volume"})
        if "volume" not in df.columns:
            df["volume"] = 0.0
        df = normalize_xauusd_spread_to_usd(df, symbol="XAUUSD", source="push_bars_v2")
        df = df[["open", "high", "low", "close", "volume", "spread"]]
        self._bars = pd.concat([self._bars, df]).sort_index()
        self._bars = self._bars[~self._bars.index.duplicated(keep="last")]
        if len(self._bars) > self.window:
            self._bars = self._bars.iloc[-self.window:]

    def load_canonical(self, path: Optional[str] = None) -> int:
        """Load canonical H1 parquet (spread_usd is preserved as USD)."""
        path = path or self._canonical_path
        if not os.path.exists(path):
            raise FileNotFoundError(f"Canonical H1 parquet not found: {path}")
        df = pd.read_parquet(path)
        if "tick_volume" in df.columns:
            df = df.rename(columns={"tick_volume": "volume"})
        if "volume" not in df.columns:
            df["volume"] = 0
        if not isinstance(df.index, pd.DatetimeIndex):
            ts_col = "timestamp" if "timestamp" in df.columns else "time"
            if ts_col in df.columns:
                df = df.set_index(ts_col)
        df = normalize_xauusd_spread_to_usd(df, symbol="XAUUSD", source="canonical_v2")
        self._bars = df[["open", "high", "low", "close", "volume", "spread"]].tail(self.window)
        self._canonical_loaded = True
        return len(self._bars)

    # ─── Feature computation ────────────────────────────────────────────

    def _compute_features(self) -> pd.DataFrame:
        """Compute all 55 v2 features on the current bar buffer."""
        return compute_v2_features(self._bars)

    def latest_features(self) -> pd.DataFrame:
        return self._compute_features()

    def latest_vector(self, source: str = "canonical",
                      symbol: str = "XAUUSD") -> FeatureVectorV2:
        try:
            if source == "canonical" and not self._canonical_loaded:
                self.load_canonical()
            feats = self._compute_features()
            last_row = feats.iloc[-1]
            vec = last_row.values.astype(np.float64)
            # v2.8.7-P2.5.2: No nan_to_num — fail closed on invalid features
            if not np.all(np.isfinite(vec)):
                # Find which features are invalid
                invalid_names = [FEATURE_NAMES_V2[i] for i in range(len(vec))
                                  if not np.isfinite(vec[i])]
                return FeatureVectorV2(
                    timestamp=feats.index[-1],
                    features=vec,
                    feature_names=FEATURE_NAMES_V2.copy(),
                    n_bars_used=len(self._bars),
                    source=source,
                    is_valid=False,
                    invalid_features=invalid_names,
                )
            vec = self._standardize(vec)
            return FeatureVectorV2(
                timestamp=feats.index[-1],
                features=vec,
                feature_names=FEATURE_NAMES_V2.copy(),
                n_bars_used=len(self._bars),
                source=source,
                is_valid=True,
            )
        except Exception as e:
            logger.error(f"v2 feature computation failed: {e}")
            return FeatureVectorV2(
                timestamp=pd.Timestamp.utcnow(),
                features=np.zeros(N_FEATURES_V2, dtype=np.float64),
                feature_names=FEATURE_NAMES_V2.copy(),
                n_bars_used=len(self._bars),
                source=source,
                is_valid=False,
                error=str(e),
            )


__all__ = [
    "H1FeatureStreamV2",
    "FeatureVectorV2",
    "FEATURE_NAMES_V2",
    "META_FEATURE_NAMES_V2",
    "N_FEATURES_V2",
]
