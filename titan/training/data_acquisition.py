"""
TITAN XAU AI — Data Acquisition Pipeline (M28.1)

Multi-source OHLC bar ingestion with:
- MT5 live source (Windows production)
- CSV source (offline / backtest data dumps)
- Parquet source (cached historical)
- Synthetic source (CI / dev environment)

Capabilities:
- Timeframe normalization (M1/M5/M15/M30/H1/H4/D1)
- Gap detection and reporting
- Incremental ingestion (skip already-fetched ranges)
- Parquet persistence partitioned by year-month
- Schema-validated BarData dataclass
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from enum import Enum
from pathlib import Path
from typing import Optional, Iterator

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


class DataSource(str, Enum):
    MT5 = "mt5"
    CSV = "csv"
    PARQUET = "parquet"
    SYNTHETIC = "synthetic"


class Timeframe(str, Enum):
    M1 = "M1"      # 1 minute
    M5 = "M5"
    M15 = "M15"
    M30 = "M30"
    H1 = "H1"
    H4 = "H4"
    D1 = "D1"

    @property
    def minutes(self) -> int:
        return {
            "M1": 1, "M5": 5, "M15": 15, "M30": 30,
            "H1": 60, "H4": 240, "D1": 1440,
        }[self.value]


@dataclass
class BarData:
    """OHLCV bar with strict schema."""
    timestamp: pd.Timestamp
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    spread: float = 0.0   # in price units (e.g., 0.18 USD for XAUUSD)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["timestamp"] = self.timestamp.isoformat()
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "BarData":
        d = dict(d)
        d["timestamp"] = pd.Timestamp(d["timestamp"])
        return cls(**d)


@dataclass
class AcquisitionResult:
    source: DataSource
    symbol: str
    timeframe: Timeframe
    bars_fetched: int
    bars_skipped: int = 0          # already in storage
    gaps_detected: int = 0
    first_timestamp: Optional[pd.Timestamp] = None
    last_timestamp: Optional[pd.Timestamp] = None
    duration_seconds: float = 0.0
    output_path: Optional[str] = None
    errors: list[str] = field(default_factory=list)


class DataAcquisitionPipeline:
    """
    Acquires OHLC bars from one of four sources, validates them, and
    persists to parquet partitioned by year-month.

    Usage:
        pipe = DataAcquisitionPipeline(storage_dir="data/xauusd")
        result = pipe.acquire(
            source=DataSource.SYNTHETIC,
            symbol="XAUUSD",
            timeframe=Timeframe.M1,
            start="2024-01-01", end="2024-06-01",
        )
    """

    def __init__(self, storage_dir: str = "data/xauusd"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def acquire(
        self,
        source: DataSource,
        symbol: str,
        timeframe: Timeframe,
        start: str | datetime,
        end: str | datetime,
        csv_path: Optional[str] = None,
    ) -> AcquisitionResult:
        """Acquire bars from the given source."""
        start_ts = pd.Timestamp(start)
        end_ts = pd.Timestamp(end)
        # Coerce to UTC-aware for consistent comparison with tz-aware DataFrames
        if start_ts.tz is None:
            start_ts = start_ts.tz_localize("UTC")
        if end_ts.tz is None:
            end_ts = end_ts.tz_localize("UTC")
        if end_ts <= start_ts:
            raise ValueError(f"end ({end_ts}) must be after start ({start_ts})")

        from time import perf_counter
        t0 = perf_counter()

        # Fetch bars from the requested source
        if source == DataSource.MT5:
            df = self._fetch_mt5(symbol, timeframe, start_ts, end_ts)
        elif source == DataSource.CSV:
            df = self._fetch_csv(csv_path, symbol, timeframe, start_ts, end_ts)
        elif source == DataSource.PARQUET:
            df = self._fetch_parquet(symbol, timeframe, start_ts, end_ts)
        elif source == DataSource.SYNTHETIC:
            df = self._fetch_synthetic(symbol, timeframe, start_ts, end_ts)
        else:
            raise ValueError(f"Unknown source: {source}")

        # Validate
        df = self._validate_schema(df)
        gaps = self._count_gaps(df, timeframe)

        # Skip already-stored bars (incremental ingestion)
        existing = self._load_existing(symbol, timeframe, start_ts, end_ts)
        if not existing.empty:
            df = df[~df.index.isin(existing.index)]

        # Persist
        out_path = self._persist(df, symbol, timeframe)
        elapsed = perf_counter() - t0

        return AcquisitionResult(
            source=source, symbol=symbol, timeframe=timeframe,
            bars_fetched=len(df),
            bars_skipped=len(existing),
            gaps_detected=gaps,
            first_timestamp=df.index.min() if not df.empty else None,
            last_timestamp=df.index.max() if not df.empty else None,
            duration_seconds=elapsed,
            output_path=str(out_path) if out_path else None,
        )

    # ─── Sources ──────────────────────────────────────────────────────

    def _fetch_mt5(self, symbol: str, tf: Timeframe,
                   start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
        """Fetch from MetaTrader5 (Windows production only)."""
        try:
            import MetaTrader5 as mt5
        except ImportError:
            from titan.mt5_stub import copy_rates_range as _copy, TIMEFRAME_M1
            # Stubbed — generate synthetic in lieu of MT5
            logger.warning("MT5 not available — using synthetic data fallback")
            return self._fetch_synthetic(symbol, tf, start, end)

        # Map our Timeframe to MT5 constants
        tf_map = {
            Timeframe.M1: mt5.TIMEFRAME_M1, Timeframe.M5: mt5.TIMEFRAME_M5,
            Timeframe.M15: mt5.TIMEFRAME_M15, Timeframe.M30: mt5.TIMEFRAME_M30,
            Timeframe.H1: mt5.TIMEFRAME_H1, Timeframe.H4: mt5.TIMEFRAME_H4,
            Timeframe.D1: mt5.TIMEFRAME_D1,
        }
        rates = mt5.copy_rates_range(symbol, tf_map[tf], start.to_pydatetime(),
                                      end.to_pydatetime())
        if rates is None or len(rates) == 0:
            return pd.DataFrame(columns=["open", "high", "low", "close",
                                          "volume", "spread"])
        df = pd.DataFrame(rates)
        df["timestamp"] = pd.to_datetime(df["time"], unit="s", utc=True)
        df = df.set_index("timestamp")[["open", "high", "low", "close",
                                         "tick_volume", "spread"]]
        df = df.rename(columns={"tick_volume": "volume"})
        return df

    def _fetch_csv(self, csv_path: Optional[str], symbol: str,
                   tf: Timeframe, start: pd.Timestamp,
                   end: pd.Timestamp) -> pd.DataFrame:
        """Load bars from CSV file (offline / backtest dumps)."""
        if csv_path is None or not os.path.exists(csv_path):
            raise FileNotFoundError(f"CSV path not provided or does not exist: {csv_path}")
        # Try common formats
        df = pd.read_csv(csv_path)
        # Find timestamp column (case-insensitive)
        ts_col = next((c for c in df.columns
                       if c.lower() in ("timestamp", "time", "date", "datetime")),
                      None)
        if ts_col is None:
            raise ValueError(f"CSV must have a timestamp/time/date column; found: {df.columns.tolist()}")
        df["timestamp"] = pd.to_datetime(df[ts_col], utc=True, errors="coerce")
        df = df.set_index("timestamp").sort_index()
        # Rename columns to canonical names
        rename = {}
        for c in df.columns:
            cl = c.lower()
            if cl in ("o", "open"): rename[c] = "open"
            elif cl in ("h", "high"): rename[c] = "high"
            elif cl in ("l", "low"): rename[c] = "low"
            elif cl in ("c", "close"): rename[c] = "close"
            elif cl in ("v", "vol", "volume", "tick_volume"): rename[c] = "volume"
            elif cl in ("s", "spread"): rename[c] = "spread"
        df = df.rename(columns=rename)
        # Filter to requested range
        df = df.loc[(df.index >= start) & (df.index < end)]
        for col in ("open", "high", "low", "close", "volume", "spread"):
            if col not in df.columns:
                df[col] = 0.0
        return df[["open", "high", "low", "close", "volume", "spread"]]

    def _fetch_parquet(self, symbol: str, tf: Timeframe,
                       start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
        """Load bars from existing parquet store."""
        return self._load_existing(symbol, tf, start, end)

    def _fetch_synthetic(self, symbol: str, tf: Timeframe,
                         start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
        """Generate synthetic OHLC for dev/CI/testing."""
        # XAUUSD realistic baseline
        base_price = 2000.0
        annual_vol = 0.15
        bars_per_year = 365 * 24 * 60 / tf.minutes
        step_vol = annual_vol / np.sqrt(bars_per_year)
        drift = 0.0001  # slight upward drift
        n_bars = int((end - start).total_seconds() / 60 / tf.minutes)
        if n_bars <= 0:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume", "spread"])
        rng = np.random.default_rng(seed=42)
        returns = rng.normal(drift, step_vol, n_bars)
        closes = base_price * np.exp(np.cumsum(returns))
        # Intraday OHLC from close: small perturbations
        opens = closes * (1 + rng.normal(0, step_vol * 0.3, n_bars))
        highs = np.maximum(opens, closes) * (1 + np.abs(rng.normal(0, step_vol * 0.4, n_bars)))
        lows = np.minimum(opens, closes) * (1 - np.abs(rng.normal(0, step_vol * 0.4, n_bars)))
        # Realistic spread: 0.10–0.40 USD
        spreads = rng.uniform(0.10, 0.40, n_bars)
        # Volume: random around a base
        volumes = rng.poisson(1000, n_bars).astype(float)
        timestamps = pd.date_range(start, periods=n_bars, freq=f"{tf.minutes}min", tz="UTC")
        df = pd.DataFrame({
            "open": opens, "high": highs, "low": lows, "close": closes,
            "volume": volumes, "spread": spreads,
        }, index=timestamps)
        df.index.name = "timestamp"
        return df

    # ─── Validation ───────────────────────────────────────────────────

    def _validate_schema(self, df: pd.DataFrame) -> pd.DataFrame:
        """Enforce canonical OHLCV+spread schema."""
        required = ["open", "high", "low", "close"]
        for col in required:
            if col not in df.columns:
                raise ValueError(f"Missing required column: {col}")
        # Optional columns
        for col in ("volume", "spread"):
            if col not in df.columns:
                df[col] = 0.0
        # Type coercion
        for col in ("open", "high", "low", "close", "volume", "spread"):
            df[col] = pd.to_numeric(df[col], errors="coerce")
        # Sanity checks: high >= max(open, close, low); low <= min(open, close, high)
        bad_highs = df["high"] < df[["open", "close", "low"]].max(axis=1)
        if bad_highs.any():
            logger.warning(f"Fixing {bad_highs.sum()} bars where high < max(o,c,l)")
            df.loc[bad_highs, "high"] = df.loc[bad_highs, ["open", "close", "low"]].max(axis=1)
        bad_lows = df["low"] > df[["open", "close", "high"]].min(axis=1)
        if bad_lows.any():
            logger.warning(f"Fixing {bad_lows.sum()} bars where low > min(o,c,h)")
            df.loc[bad_lows, "low"] = df.loc[bad_lows, ["open", "close", "high"]].min(axis=1)
        # Drop NaN
        df = df.dropna(subset=required)
        return df[["open", "high", "low", "close", "volume", "spread"]]

    def _count_gaps(self, df: pd.DataFrame, tf: Timeframe) -> int:
        """Count missing bars (gaps) in the time series."""
        if len(df) < 2:
            return 0
        expected_delta = pd.Timedelta(minutes=tf.minutes)
        deltas = df.index.to_series().diff().dropna()
        gaps = (deltas > expected_delta * 1.5).sum()
        return int(gaps)

    # ─── Persistence ──────────────────────────────────────────────────

    def _load_existing(self, symbol: str, tf: Timeframe,
                       start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
        """Load any already-stored bars in the requested range."""
        sym_dir = self.storage_dir / symbol / tf.value
        if not sym_dir.exists():
            return pd.DataFrame()
        parts = []
        for pq in sorted(sym_dir.glob("*.parquet")):
            try:
                df = pd.read_parquet(pq)
                parts.append(df)
            except Exception:
                continue
        if not parts:
            return pd.DataFrame()
        full = pd.concat(parts).sort_index()
        full = full.loc[(full.index >= start) & (full.index < end)]
        return full

    def _persist(self, df: pd.DataFrame, symbol: str,
                 tf: Timeframe) -> Optional[Path]:
        """Persist bars to parquet partitioned by year-month."""
        if df.empty:
            return None
        sym_dir = self.storage_dir / symbol / tf.value
        sym_dir.mkdir(parents=True, exist_ok=True)
        # Partition by year-month
        df = df.copy()
        df["year_month"] = df.index.strftime("%Y-%m")
        out_paths = []
        for ym, group in df.groupby("year_month"):
            group = group.drop(columns=["year_month"])
            out_path = sym_dir / f"{ym}.parquet"
            # Merge with existing if present
            if out_path.exists():
                existing = pd.read_parquet(out_path)
                combined = pd.concat([existing, group]).reset_index()
                combined = combined.drop_duplicates(subset=["timestamp"], keep="last")
                combined = combined.set_index("timestamp").sort_index()
                combined.to_parquet(out_path)
            else:
                group.to_parquet(out_path)
            out_paths.append(out_path)
        return out_paths[0] if out_paths else None


__all__ = [
    "DataAcquisitionPipeline", "DataSource", "Timeframe", "BarData",
    "AcquisitionResult",
]
