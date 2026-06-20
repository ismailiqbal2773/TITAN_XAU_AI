"""
TITAN XAU AI — Feature Generation Pipeline (M28.3)

Generates features from OHLCV bars for model training:
- Price-derived features (returns, log returns, normalized)
- Technical indicators (RSI, MACD, BB, ATR, ADX, OBV, etc.)
- Volatility features (realized vol, vol-of-vol, ATR ratio)
- Microstructure features (spread, volume imbalance, body/wick ratios)
- Time features (hour, day-of-week, session)
- Lag features (returns at multiple horizons)
- Multi-horizon targets (next-bar return, multi-step ahead)

All features are vectorized pandas/numpy for speed. Designed for
~10M-bar training datasets on a single CPU core within 60 seconds.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class FeatureConfig:
    """Toggle which feature groups to generate."""
    price_features: bool = True
    technical_features: bool = True
    volatility_features: bool = True
    microstructure_features: bool = True
    time_features: bool = True
    lag_features: bool = True
    # RSI / MACD / BB periods
    rsi_period: int = 14
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    bb_period: int = 20
    bb_std: float = 2.0
    atr_period: int = 14
    adx_period: int = 14
    # Lag horizons (in bars)
    lag_horizons: list[int] = field(default_factory=lambda: [1, 2, 3, 5, 10, 20, 60])
    # Volatility windows
    vol_windows: list[int] = field(default_factory=lambda: [10, 20, 60, 120])


@dataclass
class TargetConfig:
    """Multi-horizon target configuration."""
    horizons: list[int] = field(default_factory=lambda: [1, 5, 15, 60])  # bars ahead
    target_type: str = "return"   # "return" or "log_return"
    threshold: float = 0.0        # for classification: > threshold → 1, < -threshold → -1


@dataclass
class FeatureSet:
    """Result of feature generation: a feature matrix X and targets y."""
    features: pd.DataFrame
    targets: pd.DataFrame
    feature_names: list[str]
    target_names: list[str]
    n_bars: int
    n_features: int
    n_targets: int
    feature_groups: dict[str, list[str]]   # group → feature names
    duration_seconds: float = 0.0

    def to_dict(self) -> dict:
        return {
            "n_bars": self.n_bars,
            "n_features": self.n_features,
            "n_targets": self.n_targets,
            "feature_names": self.feature_names,
            "target_names": self.target_names,
            "feature_groups": {k: v for k, v in self.feature_groups.items()},
            "duration_seconds": self.duration_seconds,
        }


class FeatureEngine:
    """
    Generate training features from OHLCV bars.
    """

    def __init__(self, config: Optional[FeatureConfig] = None,
                 target_config: Optional[TargetConfig] = None):
        self.config = config or FeatureConfig()
        self.target_config = target_config or TargetConfig()

    def generate(self, bars: pd.DataFrame) -> FeatureSet:
        """Generate all features + targets from OHLCV bars."""
        from time import perf_counter
        t0 = perf_counter()
        if bars.empty:
            return FeatureSet(
                features=pd.DataFrame(), targets=pd.DataFrame(),
                feature_names=[], target_names=[],
                n_bars=0, n_features=0, n_targets=0,
                feature_groups={},
            )
        df = bars.copy()
        groups: dict[str, list[str]] = {}

        if self.config.price_features:
            feats = self._price_features(df)
            groups["price"] = list(feats.columns)
            df = pd.concat([df, feats], axis=1)

        if self.config.technical_features:
            feats = self._technical_features(df)
            groups["technical"] = list(feats.columns)
            df = pd.concat([df, feats], axis=1)

        if self.config.volatility_features:
            feats = self._volatility_features(df)
            groups["volatility"] = list(feats.columns)
            df = pd.concat([df, feats], axis=1)

        if self.config.microstructure_features:
            feats = self._microstructure_features(df)
            groups["microstructure"] = list(feats.columns)
            df = pd.concat([df, feats], axis=1)

        if self.config.time_features:
            feats = self._time_features(df)
            groups["time"] = list(feats.columns)
            df = pd.concat([df, feats], axis=1)

        if self.config.lag_features:
            feats = self._lag_features(df)
            groups["lag"] = list(feats.columns)
            df = pd.concat([df, feats], axis=1)

        # Targets
        targets = self._generate_targets(bars)

        # Drop OHLCV from features (keep derived features)
        drop_cols = ["open", "high", "low", "close", "volume", "spread"]
        feature_df = df.drop(columns=[c for c in drop_cols if c in df.columns])

        # Align features and targets (drop last N bars where targets are NaN)
        max_horizon = max(self.target_config.horizons)
        feature_df = feature_df.iloc[:-max_horizon]
        targets = targets.iloc[:-max_horizon]

        # Drop any remaining NaN rows (warmup periods for indicators)
        valid_mask = feature_df.notna().all(axis=1) & targets.notna().all(axis=1)
        feature_df = feature_df[valid_mask]
        targets = targets[valid_mask]

        elapsed = perf_counter() - t0
        return FeatureSet(
            features=feature_df,
            targets=targets,
            feature_names=feature_df.columns.tolist(),
            target_names=targets.columns.tolist(),
            n_bars=len(feature_df),
            n_features=feature_df.shape[1],
            n_targets=targets.shape[1],
            feature_groups=groups,
            duration_seconds=elapsed,
        )

    # ─── Feature groups ───────────────────────────────────────────────

    def _price_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Price-derived features."""
        c = df["close"]
        out = pd.DataFrame(index=df.index)
        out["ret_1"] = c.pct_change(1)
        out["ret_5"] = c.pct_change(5)
        out["ret_15"] = c.pct_change(15)
        out["logret_1"] = np.log(c / c.shift(1))
        out["logret_5"] = np.log(c / c.shift(5))
        # Normalized price (z-score over 60 bars)
        out["price_zscore_60"] = (c - c.rolling(60).mean()) / c.rolling(60).std().replace(0, np.nan)
        # High-low range
        out["hl_range"] = (df["high"] - df["low"]) / c
        # Close position in bar range
        range_ = (df["high"] - df["low"]).replace(0, np.nan)
        out["close_pos_in_range"] = (df["close"] - df["low"]) / range_
        return out

    def _technical_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Technical indicators (RSI, MACD, BB, ATR, ADX, OBV)."""
        c = df["close"]
        h = df["high"]
        l = df["low"]
        v = df["volume"]
        out = pd.DataFrame(index=df.index)
        p = self.config

        # RSI
        delta = c.diff()
        gain = delta.where(delta > 0, 0).rolling(p.rsi_period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(p.rsi_period).mean()
        rs = gain / loss.replace(0, np.nan)
        out["rsi"] = 100 - (100 / (1 + rs))

        # MACD
        ema_fast = c.ewm(span=p.macd_fast, adjust=False).mean()
        ema_slow = c.ewm(span=p.macd_slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=p.macd_signal, adjust=False).mean()
        out["macd"] = macd_line
        out["macd_signal"] = signal_line
        out["macd_hist"] = macd_line - signal_line

        # Bollinger Bands
        sma = c.rolling(p.bb_period).mean()
        std = c.rolling(p.bb_period).std()
        out["bb_upper"] = sma + p.bb_std * std
        out["bb_lower"] = sma - p.bb_std * std
        out["bb_width"] = (out["bb_upper"] - out["bb_lower"]) / sma.replace(0, np.nan)
        out["bb_pct_b"] = (c - out["bb_lower"]) / (out["bb_upper"] - out["bb_lower"]).replace(0, np.nan)

        # ATR
        tr = pd.concat([
            (h - l),
            (h - c.shift(1)).abs(),
            (l - c.shift(1)).abs(),
        ], axis=1).max(axis=1)
        out["atr"] = tr.rolling(p.atr_period).mean() / c

        # ADX (simplified)
        plus_dm = (h - h.shift(1)).where((h - h.shift(1)) > (l.shift(1) - l), 0)
        minus_dm = (l.shift(1) - l).where((l.shift(1) - l) > (h - h.shift(1)), 0)
        atr_adx = tr.ewm(span=p.adx_period, adjust=False).mean()
        plus_di = 100 * plus_dm.ewm(span=p.adx_period, adjust=False).mean() / atr_adx.replace(0, np.nan)
        minus_di = 100 * minus_dm.ewm(span=p.adx_period, adjust=False).mean() / atr_adx.replace(0, np.nan)
        dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
        out["adx"] = dx.ewm(span=p.adx_period, adjust=False).mean()
        out["plus_di"] = plus_di
        out["minus_di"] = minus_di

        # OBV (On-Balance Volume)
        obv = (np.sign(c.diff()) * v).fillna(0).cumsum()
        out["obv"] = obv
        out["obv_slope_20"] = obv.diff(20)

        # SMA / EMA ratios
        out["sma_20_ratio"] = c / c.rolling(20).mean()
        out["sma_50_ratio"] = c / c.rolling(50).mean()
        out["sma_200_ratio"] = c / c.rolling(200).mean()
        out["ema_12_ratio"] = c / c.ewm(span=12, adjust=False).mean()

        return out

    def _volatility_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Volatility features at multiple windows."""
        c = df["close"]
        log_ret = np.log(c / c.shift(1))
        out = pd.DataFrame(index=df.index)
        for w in self.config.vol_windows:
            out[f"realized_vol_{w}"] = log_ret.rolling(w).std()
            out[f"vol_of_vol_{w}"] = log_ret.rolling(w).std().rolling(w).std()
        # Volatility ratio (short / long)
        out["vol_ratio_10_60"] = (
            log_ret.rolling(10).std() / log_ret.rolling(60).std().replace(0, np.nan)
        )
        # ATR ratio (short / long)
        tr = pd.concat([
            (df["high"] - df["low"]),
            (df["high"] - c.shift(1)).abs(),
            (df["low"] - c.shift(1)).abs(),
        ], axis=1).max(axis=1)
        out["atr_ratio_5_20"] = (
            tr.rolling(5).mean() / tr.rolling(20).mean().replace(0, np.nan)
        )
        return out

    def _microstructure_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Microstructure: spread, volume, candle shape."""
        c = df["close"]
        o = df["open"]
        h = df["high"]
        l = df["low"]
        v = df["volume"]
        out = pd.DataFrame(index=df.index)
        # Spread features (spread is in price units)
        out["spread_pct"] = df.get("spread", 0) / c
        out["spread_zscore_60"] = (
            (df.get("spread", 0) - df.get("spread", 0).rolling(60).mean())
            / df.get("spread", 0).rolling(60).std().replace(0, np.nan)
        )
        # Volume features
        out["volume_zscore_60"] = (v - v.rolling(60).mean()) / v.rolling(60).std().replace(0, np.nan)
        out["volume_ratio_5_20"] = v.rolling(5).mean() / v.rolling(20).mean().replace(0, np.nan)
        # Candle body / wick
        body = (c - o).abs()
        full_range = (h - l).replace(0, np.nan)
        out["body_ratio"] = body / full_range
        out["upper_wick_ratio"] = (h - np.maximum(o, c)) / full_range
        out["lower_wick_ratio"] = (np.minimum(o, c) - l) / full_range
        # Directional body
        out["body_dir"] = (c - o) / full_range
        return out

    def _time_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Time-of-day, day-of-week, session features."""
        out = pd.DataFrame(index=df.index)
        ts = df.index
        # Cyclical hour-of-day
        hour = ts.hour + ts.minute / 60.0
        out["hour_sin"] = np.sin(2 * np.pi * hour / 24)
        out["hour_cos"] = np.cos(2 * np.pi * hour / 24)
        # Day of week (0=Mon, 6=Sun)
        dow = ts.dayofweek
        out["dow_sin"] = np.sin(2 * np.pi * dow / 7)
        out["dow_cos"] = np.cos(2 * np.pi * dow / 7)
        # Trading session (Asia / EU / US) — based on UTC hour
        # Asia: 0-8 UTC, EU: 7-16 UTC, US: 13-22 UTC
        out["asia_session"] = ((hour >= 0) & (hour < 8)).astype(int)
        out["eu_session"] = ((hour >= 7) & (hour < 16)).astype(int)
        out["us_session"] = ((hour >= 13) & (hour < 22)).astype(int)
        # Weekend flag (Sat=5, Sun=6)
        out["is_weekend"] = (dow >= 5).astype(int)
        # Month (cyclical)
        month = ts.month
        out["month_sin"] = np.sin(2 * np.pi * month / 12)
        out["month_cos"] = np.cos(2 * np.pi * month / 12)
        return out

    def _lag_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Lagged returns at multiple horizons."""
        c = df["close"]
        out = pd.DataFrame(index=df.index)
        for h in self.config.lag_horizons:
            out[f"ret_lag_{h}"] = c.pct_change(h).shift(1)
        return out

    # ─── Targets ──────────────────────────────────────────────────────

    def _generate_targets(self, bars: pd.DataFrame) -> pd.DataFrame:
        """Generate multi-horizon forward returns."""
        c = bars["close"]
        out = pd.DataFrame(index=bars.index)
        for h in self.target_config.horizons:
            col = f"target_ret_{h}"
            if self.target_config.target_type == "log_return":
                out[col] = np.log(c.shift(-h) / c)
            else:
                out[col] = (c.shift(-h) - c) / c
        return out


# ─── B3: Feature Scalers (train-only fit, no leakage) ────────────────────


class StandardScaler:
    """Mean/std scaler fit ONLY on training data.

    Stores column means and stds; transform applies (x - mean) / std.
    Std is clipped to a small floor (1e-8) to avoid divide-by-zero on
    constant features. NaN-safe.
    """

    def __init__(self, clip: float = 5.0):
        self.clip = clip
        self.means_: pd.Series | None = None
        self.stds_: pd.Series | None = None
        self.columns_: list[str] = []
        self._fitted = False

    def fit(self, df: pd.DataFrame) -> "StandardScaler":
        self.means_ = df.mean(axis=0, skipna=True)
        self.stds_ = df.std(axis=0, skipna=True).replace(0, np.nan)
        self.stds_ = self.stds_.fillna(1.0).clip(lower=1e-8)
        self.columns_ = df.columns.tolist()
        self._fitted = True
        return self

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        if not self._fitted:
            raise RuntimeError("StandardScaler.transform called before fit()")
        out = (df - self.means_) / self.stds_
        if self.clip is not None and self.clip > 0:
            out = out.clip(-self.clip, self.clip)
        return out

    def fit_transform(self, df: pd.DataFrame) -> pd.DataFrame:
        return self.fit(df).transform(df)


class RobustScaler:
    """Median/IQR scaler fit ONLY on training data.

    More robust to outliers than StandardScaler. Stores column medians
    and IQRs (75th - 25th percentile); transform applies (x - median) / IQR.
    IQR is clipped to a small floor to avoid divide-by-zero.
    """

    def __init__(self, clip: float = 5.0):
        self.clip = clip
        self.medians_: pd.Series | None = None
        self.iqrs_: pd.Series | None = None
        self.columns_: list[str] = []
        self._fitted = False

    def fit(self, df: pd.DataFrame) -> "RobustScaler":
        self.medians_ = df.median(axis=0, skipna=True)
        q1 = df.quantile(0.25, axis=0)
        q3 = df.quantile(0.75, axis=0)
        self.iqrs_ = (q3 - q1).replace(0, np.nan).fillna(1.0).clip(lower=1e-8)
        self.columns_ = df.columns.tolist()
        self._fitted = True
        return self

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        if not self._fitted:
            raise RuntimeError("RobustScaler.transform called before fit()")
        out = (df - self.medians_) / self.iqrs_
        if self.clip is not None and self.clip > 0:
            out = out.clip(-self.clip, self.clip)
        return out

    def fit_transform(self, df: pd.DataFrame) -> pd.DataFrame:
        return self.fit(df).transform(df)


# ─── B5: Feature Selector (zero-variance + correlation pruning) ──────────


@dataclass
class FeatureSelectionReport:
    """Report from feature selection. Records what was dropped and why."""
    n_input: int = 0
    n_output: int = 0
    dropped_zero_variance: list[str] = field(default_factory=list)
    dropped_high_correlation: list[str] = field(default_factory=list)
    high_correlation_pairs: list[tuple[str, str, float]] = field(default_factory=list)
    kept_features: list[str] = field(default_factory=list)
    variance_threshold: float = 0.0
    correlation_threshold: float = 0.0

    def to_dict(self) -> dict:
        return {
            "n_input": self.n_input,
            "n_output": self.n_output,
            "n_dropped": self.n_input - self.n_output,
            "dropped_zero_variance": self.dropped_zero_variance,
            "dropped_high_correlation": self.dropped_high_correlation,
            "high_correlation_pairs": [
                {"a": a, "b": b, "corr": round(c, 4)}
                for a, b, c in self.high_correlation_pairs
            ],
            "kept_features": self.kept_features,
            "variance_threshold": self.variance_threshold,
            "correlation_threshold": self.correlation_threshold,
        }


class FeatureSelector:
    """Drop zero-variance and highly-correlated features.

    Two-pass selection:
      1. Drop features whose variance is below `variance_threshold`
         (default 1e-10 — catches truly constant features).
      2. Compute pairwise absolute correlation. For each pair with
         |r| > `correlation_threshold` (default 0.95), drop the feature
         with lower variance (the less informative one).

    The selector is fit ONLY on training data. The kept-feature list is
    applied to validation/test data via transform().
    """

    def __init__(self, variance_threshold: float = 1e-10,
                 correlation_threshold: float = 0.95):
        self.variance_threshold = variance_threshold
        self.correlation_threshold = correlation_threshold
        self.report_: FeatureSelectionReport | None = None
        self.kept_features_: list[str] = []
        self._fitted = False

    def fit(self, df: pd.DataFrame) -> "FeatureSelector":
        n_input = df.shape[1]
        report = FeatureSelectionReport(
            n_input=n_input,
            variance_threshold=self.variance_threshold,
            correlation_threshold=self.correlation_threshold,
        )
        # Pass 1: drop zero-variance
        variances = df.var(axis=0, skipna=True).fillna(0)
        zero_var = variances[variances <= self.variance_threshold].index.tolist()
        report.dropped_zero_variance = zero_var
        kept = [c for c in df.columns if c not in zero_var]
        df_pass1 = df[kept]
        # Pass 2: drop high-correlation (lower-variance partner of each pair)
        if len(df_pass1.columns) > 1:
            corr = df_pass1.corr().abs()
            np.fill_diagonal(corr.values, 0)
            to_drop: set[str] = set()
            high_pairs: list[tuple[str, str, float]] = []
            cols = df_pass1.columns.tolist()
            for i in range(len(cols)):
                for j in range(i + 1, len(cols)):
                    a, b = cols[i], cols[j]
                    c = float(corr.loc[a, b])
                    if c > self.correlation_threshold:
                        high_pairs.append((a, b, c))
                        # Drop whichever has lower variance
                        if variances[a] < variances[b]:
                            to_drop.add(a)
                        else:
                            to_drop.add(b)
            report.high_correlation_pairs = high_pairs
            report.dropped_high_correlation = sorted(to_drop)
            kept = [c for c in kept if c not in to_drop]
        report.kept_features = kept
        report.n_output = len(kept)
        self.kept_features_ = kept
        self.report_ = report
        self._fitted = True
        return self

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        if not self._fitted:
            raise RuntimeError("FeatureSelector.transform called before fit()")
        # Only keep columns that exist in df
        cols = [c for c in self.kept_features_ if c in df.columns]
        return df[cols]

    def fit_transform(self, df: pd.DataFrame) -> pd.DataFrame:
        return self.fit(df).transform(df)


__all__ = ["FeatureEngine", "FeatureSet", "FeatureConfig", "TargetConfig",
           "StandardScaler", "RobustScaler",
           "FeatureSelector", "FeatureSelectionReport"]
