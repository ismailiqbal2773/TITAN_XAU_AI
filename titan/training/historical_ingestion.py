"""
TITAN XAU AI — Historical XAUUSD Ingestion (M28.2)

Bulk historical ingestion engine that:
- Downloads multi-year XAUUSD history from MT5 (or generates synthetic
  in CI/dev)
- Aggregates M1 ticks to higher timeframes (M5, M15, H1, H4, D1)
- Reports ingestion coverage and gap statistics
- Idempotent: re-running skips already-stored ranges

Used as a one-time bootstrap before model training. After bootstrap,
incremental acquisition (M28.1) keeps the dataset current.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import pandas as pd
import numpy as np

from titan.training.data_acquisition import (
    DataAcquisitionPipeline, DataSource, Timeframe,
)

logger = logging.getLogger(__name__)


@dataclass
class IngestionResult:
    """Result of a full historical ingestion run."""
    symbol: str
    timeframe: Timeframe
    start: pd.Timestamp
    end: pd.Timestamp
    bars_total: int = 0
    bars_new: int = 0
    bars_skipped: int = 0
    gaps: int = 0
    coverage_pct: float = 0.0
    duration_seconds: float = 0.0
    output_paths: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe.value,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "bars_total": self.bars_total,
            "bars_new": self.bars_new,
            "bars_skipped": self.bars_skipped,
            "gaps": self.gaps,
            "coverage_pct": round(self.coverage_pct, 2),
            "duration_seconds": round(self.duration_seconds, 3),
            "output_paths": self.output_paths,
            "errors": self.errors,
        }


class HistoricalIngestionEngine:
    """
    One-shot bulk ingestion for multi-year XAUUSD history.
    Iterates year-by-year to avoid memory blowups on long ranges.
    """

    DEFAULT_TIMEFRAMES = [Timeframe.M1, Timeframe.M5, Timeframe.M15,
                          Timeframe.H1, Timeframe.H4, Timeframe.D1]
    DEFAULT_SYMBOL = "XAUUSD"

    def __init__(self, storage_dir: str = "data/xauusd"):
        self.pipeline = DataAcquisitionPipeline(storage_dir=storage_dir)

    def ingest(
        self,
        symbol: str = "XAUUSD",
        start: str = "2020-01-01",
        end: Optional[str] = None,
        timeframes: Optional[list[Timeframe]] = None,
        source: DataSource = DataSource.SYNTHETIC,
        csv_paths: Optional[dict[Timeframe, str]] = None,
    ) -> dict[Timeframe, IngestionResult]:
        """Ingest multi-year history across multiple timeframes."""
        end_ts = pd.Timestamp(end) if end else pd.Timestamp.utcnow()
        start_ts = pd.Timestamp(start)
        tfs = timeframes or self.DEFAULT_TIMEFRAMES
        results: dict[Timeframe, IngestionResult] = {}

        for tf in tfs:
            logger.info(f"Ingesting {symbol} {tf.value} from {start_ts} to {end_ts}")
            try:
                # Iterate year-by-year to bound memory
                year_results = []
                cur = start_ts
                while cur < end_ts:
                    next_year = cur.replace(year=cur.year + 1, month=1, day=1)
                    chunk_end = min(next_year, end_ts)
                    csv_path = (csv_paths or {}).get(tf)
                    r = self.pipeline.acquire(
                        source=source, symbol=symbol, timeframe=tf,
                        start=cur, end=chunk_end, csv_path=csv_path,
                    )
                    year_results.append(r)
                    cur = next_year

                # Aggregate
                total_bars_new = sum(r.bars_fetched for r in year_results)
                total_bars_skip = sum(r.bars_skipped for r in year_results)
                total_gaps = sum(r.gaps_detected for r in year_results)
                first_ts = next((r.first_timestamp for r in year_results
                                 if r.first_timestamp is not None), None)
                last_ts = next((r.last_timestamp for r in reversed(year_results)
                                if r.last_timestamp is not None), None)
                duration = sum(r.duration_seconds for r in year_results)

                # Compute coverage
                coverage = self._compute_coverage(first_ts, last_ts, tf, total_gaps)

                results[tf] = IngestionResult(
                    symbol=symbol, timeframe=tf,
                    start=start_ts, end=end_ts,
                    bars_total=total_bars_new + total_bars_skip,
                    bars_new=total_bars_new,
                    bars_skipped=total_bars_skip,
                    gaps=total_gaps,
                    coverage_pct=coverage,
                    duration_seconds=duration,
                    output_paths=[r.output_path for r in year_results if r.output_path],
                    errors=[e for r in year_results for e in r.errors],
                )
                logger.info(
                    f"  {tf.value}: {total_bars_new} new bars, "
                    f"{total_bars_skip} skipped, {total_gaps} gaps, "
                    f"{coverage:.1f}% coverage"
                )
            except Exception as e:
                logger.error(f"  {tf.value}: FAILED — {e}")
                results[tf] = IngestionResult(
                    symbol=symbol, timeframe=tf,
                    start=start_ts, end=end_ts,
                    errors=[str(e)],
                )

        return results

    def aggregate_timeframe(
        self, symbol: str, source_tf: Timeframe, target_tf: Timeframe,
        start: str, end: str,
    ) -> IngestionResult:
        """Aggregate M1 bars to a higher timeframe (e.g. M5, H1)."""
        from time import perf_counter
        t0 = perf_counter()
        # Coerce tz to UTC for consistent comparison
        start_ts = pd.Timestamp(start)
        end_ts = pd.Timestamp(end)
        if start_ts.tz is None:
            start_ts = start_ts.tz_localize("UTC")
        if end_ts.tz is None:
            end_ts = end_ts.tz_localize("UTC")
        # Load source bars
        df = self.pipeline._load_existing(symbol, source_tf, start_ts, end_ts)
        if df.empty:
            return IngestionResult(
                symbol=symbol, timeframe=target_tf,
                start=pd.Timestamp(start), end=pd.Timestamp(end),
                errors=["No source bars found"],
            )
        # Resample
        rule = f"{target_tf.minutes}min"
        agg = df.resample(rule).agg({
            "open": "first", "high": "max", "low": "min",
            "close": "last", "volume": "sum", "spread": "mean",
        }).dropna(subset=["open", "close"])
        # Persist
        sym_dir = self.pipeline.storage_dir / symbol / target_tf.value
        sym_dir.mkdir(parents=True, exist_ok=True)
        df_to_persist = agg.copy()
        df_to_persist["year_month"] = df_to_persist.index.strftime("%Y-%m")
        out_paths = []
        for ym, group in df_to_persist.groupby("year_month"):
            group = group.drop(columns=["year_month"])
            out_path = sym_dir / f"{ym}.parquet"
            group.to_parquet(out_path)
            out_paths.append(str(out_path))
        elapsed = perf_counter() - t0
        gaps = self.pipeline._count_gaps(agg, target_tf)
        coverage = self._compute_coverage(agg.index.min(), agg.index.max(),
                                          target_tf, gaps)
        return IngestionResult(
            symbol=symbol, timeframe=target_tf,
            start=pd.Timestamp(start), end=pd.Timestamp(end),
            bars_total=len(agg), bars_new=len(agg),
            gaps=gaps, coverage_pct=coverage,
            duration_seconds=elapsed,
            output_paths=out_paths,
        )

    @staticmethod
    def _compute_coverage(first: Optional[pd.Timestamp],
                           last: Optional[pd.Timestamp],
                           tf: Timeframe, gaps: int) -> float:
        if first is None or last is None:
            return 0.0
        total_bars_expected = int((last - first).total_seconds() / 60 / tf.minutes)
        if total_bars_expected == 0:
            return 100.0
        actual_bars = total_bars_expected - gaps
        return max(0.0, min(100.0, 100.0 * actual_bars / total_bars_expected))


class SyntheticDataGenerator:
    """
    Standalone synthetic XAUUSD data generator for CI/testing.
    Produces realistic OHLC with intraday volatility patterns.
    """

    def __init__(self, seed: int = 42):
        self.rng = np.random.default_rng(seed=seed)

    def generate(
        self, start: str, end: str, timeframe: Timeframe = Timeframe.M1,
        base_price: float = 2000.0, annual_vol: float = 0.15,
    ) -> pd.DataFrame:
        """Generate a synthetic OHLCV DataFrame."""
        start_ts = pd.Timestamp(start, tz="UTC")
        end_ts = pd.Timestamp(end, tz="UTC")
        n_bars = int((end_ts - start_ts).total_seconds() / 60 / timeframe.minutes)
        if n_bars <= 0:
            return pd.DataFrame()
        bars_per_year = 365 * 24 * 60 / timeframe.minutes
        step_vol = annual_vol / np.sqrt(bars_per_year)
        # Slight upward drift + mean reversion
        returns = self.rng.normal(0.0001, step_vol, n_bars)
        closes = base_price * np.exp(np.cumsum(returns))
        opens = closes * (1 + self.rng.normal(0, step_vol * 0.3, n_bars))
        highs = np.maximum(opens, closes) * (1 + np.abs(self.rng.normal(0, step_vol * 0.4, n_bars)))
        lows = np.minimum(opens, closes) * (1 - np.abs(self.rng.normal(0, step_vol * 0.4, n_bars)))
        spreads = self.rng.uniform(0.10, 0.40, n_bars)
        volumes = self.rng.poisson(1000, n_bars).astype(float)
        timestamps = pd.date_range(start_ts, periods=n_bars,
                                    freq=f"{timeframe.minutes}min")
        df = pd.DataFrame({
            "open": opens, "high": highs, "low": lows, "close": closes,
            "volume": volumes, "spread": spreads,
        }, index=timestamps)
        df.index.name = "timestamp"
        return df

    def generate_with_regimes(
        self, start: str, end: str, timeframe: Timeframe = Timeframe.M1,
    ) -> pd.DataFrame:
        """Generate data with regime shifts (trend up / trend down / range)."""
        start_ts = pd.Timestamp(start, tz="UTC")
        end_ts = pd.Timestamp(end, tz="UTC")
        n_bars = int((end_ts - start_ts).total_seconds() / 60 / timeframe.minutes)
        if n_bars <= 0:
            return pd.DataFrame()
        # Regime: 0=trend up, 1=trend down, 2=range, 3=high vol
        regime_lengths = self.rng.integers(500, 2000, size=max(1, n_bars // 1000))
        regimes = []
        for rl in regime_lengths:
            r = self.rng.integers(0, 4)
            regimes.extend([r] * rl)
        regimes = regimes[:n_bars]
        while len(regimes) < n_bars:
            regimes.append(0)

        base_price = 2000.0
        bars_per_year = 365 * 24 * 60 / timeframe.minutes
        step_vol = 0.15 / np.sqrt(bars_per_year)

        returns = np.zeros(n_bars)
        for i, r in enumerate(regimes):
            if r == 0:    # trend up
                returns[i] = self.rng.normal(0.0005, step_vol)
            elif r == 1:  # trend down
                returns[i] = self.rng.normal(-0.0005, step_vol)
            elif r == 2:  # range
                returns[i] = self.rng.normal(0, step_vol * 0.5)
            else:         # high vol
                returns[i] = self.rng.normal(0, step_vol * 3.0)

        closes = base_price * np.exp(np.cumsum(returns))
        opens = closes * (1 + self.rng.normal(0, step_vol * 0.3, n_bars))
        highs = np.maximum(opens, closes) * (1 + np.abs(self.rng.normal(0, step_vol * 0.4, n_bars)))
        lows = np.minimum(opens, closes) * (1 - np.abs(self.rng.normal(0, step_vol * 0.4, n_bars)))
        spreads = self.rng.uniform(0.10, 0.40, n_bars)
        volumes = self.rng.poisson(1000, n_bars).astype(float)
        timestamps = pd.date_range(start_ts, periods=n_bars,
                                    freq=f"{timeframe.minutes}min")
        df = pd.DataFrame({
            "open": opens, "high": highs, "low": lows, "close": closes,
            "volume": volumes, "spread": spreads,
        }, index=timestamps)
        df.index.name = "timestamp"
        return df


__all__ = [
    "HistoricalIngestionEngine", "IngestionResult", "SyntheticDataGenerator",
]
