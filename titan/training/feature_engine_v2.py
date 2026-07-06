"""
TITAN XAU AI — Feature Engine v2 (Sprint v2.8.7-E)
====================================================
Generates v2 features that replace absolute-price features with
stationary/relative equivalents. The other 50 v1 features are unchanged.

v2 Replacements:
  macd_signal  → macd_signal_relative  = macd_signal / close
  macd_hist    → macd_hist_relative    = macd_hist / close
  bb_upper     → bb_distance_upper     = (bb_upper - close) / close
  obv          → obv_zscore_120        = (obv - obv.rolling(120).mean())
                                          / obv.rolling(120).std()
  obv_slope_20 → obv_slope_20_zscore   = (obv_slope_20
                                          - obv_slope_20.rolling(120).mean())
                                          / obv_slope_20.rolling(120).std()

This module NEVER sends orders. NEVER creates tokens. NEVER trades.
"""
from __future__ import annotations

import logging
import numpy as np
import pandas as pd

from titan.training.feature_schema_v2 import (
    FEATURE_NAMES_V2,
    ABSOLUTE_TO_RELATIVE,
    N_FEATURES_V2,
)

logger = logging.getLogger(__name__)


# Reuse indicator periods from v1 feature_stream (must match exactly)
RSI_PERIOD = 14
MACD_FAST, MACD_SLOW, MACD_SIGNAL = 12, 26, 9
BB_PERIOD, BB_STD = 20, 2.0
ATR_PERIOD, ADX_PERIOD = 14, 14
LAG_HORIZONS = [1, 2, 3, 5, 10, 20, 60]
VOL_WINDOWS = [10, 20, 60, 120]

MIN_BARS_FOR_FULL_FEATURES_V2 = 220  # sma_200_ratio + buffer (same as v1)


def compute_v2_features(df: pd.DataFrame) -> pd.DataFrame:
    """Compute all 55 v2 features on a DataFrame of OHLCV bars.

    Args:
        df: DataFrame with columns open/high/low/close/volume/spread.
            Spread MUST be in USD (use spread_normalization first).
            Index must be DatetimeIndex.

    Returns:
        DataFrame with FEATURE_NAMES_V2 columns in fixed order.
    """
    if len(df) < MIN_BARS_FOR_FULL_FEATURES_V2:
        raise ValueError(
            f"Need >= {MIN_BARS_FOR_FULL_FEATURES_V2} bars, have {len(df)}"
        )

    c, h, l, o, v = df["close"], df["high"], df["low"], df["open"], df["volume"]
    spread = df["spread"]
    feats = pd.DataFrame(index=df.index)

    # ── Price (7) ──
    feats["n_brokers"] = 1  # default for single-broker feed
    feats["ret_1"] = c.pct_change(1)
    feats["ret_5"] = c.pct_change(5)
    feats["ret_15"] = c.pct_change(15)
    feats["price_zscore_60"] = (c - c.rolling(60).mean()) / c.rolling(60).std().replace(0, np.nan)
    feats["hl_range"] = (h - l) / c
    rng = (h - l).replace(0, np.nan)
    feats["close_pos_in_range"] = (c - l) / rng

    # ── Technical (14) — with v2 replacements ──
    delta = c.diff()
    gain = delta.where(delta > 0, 0).rolling(RSI_PERIOD).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(RSI_PERIOD).mean()
    rs = gain / loss.replace(0, np.nan)
    feats["rsi"] = 100 - (100 / (1 + rs))

    ema_fast = c.ewm(span=MACD_FAST, adjust=False).mean()
    ema_slow = c.ewm(span=MACD_SLOW, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=MACD_SIGNAL, adjust=False).mean()
    # === v2 FIX 1: macd_signal_relative ===
    feats["macd_signal_relative"] = signal_line / c.replace(0, np.nan)
    # === v2 FIX 2: macd_hist_relative ===
    feats["macd_hist_relative"] = (macd_line - signal_line) / c.replace(0, np.nan)

    sma = c.rolling(BB_PERIOD).mean()
    std = c.rolling(BB_PERIOD).std()
    bb_upper = sma + BB_STD * std
    bb_lower = sma - BB_STD * std
    feats["bb_width"] = (bb_upper - bb_lower) / sma.replace(0, np.nan)
    feats["bb_pct_b"] = (c - bb_lower) / (bb_upper - bb_lower).replace(0, np.nan)
    # === v2 FIX 3: bb_distance_upper (replaces bb_upper) ===
    feats["bb_distance_upper"] = (bb_upper - c) / c.replace(0, np.nan)

    tr = pd.concat([
        (h - l),
        (h - c.shift(1)).abs(),
        (l - c.shift(1)).abs(),
    ], axis=1).max(axis=1)
    feats["atr"] = tr.rolling(ATR_PERIOD).mean() / c

    plus_dm = (h - h.shift(1)).where((h - h.shift(1)) > (l.shift(1) - l), 0)
    minus_dm = (l.shift(1) - l).where((l.shift(1) - l) > (h - h.shift(1)), 0)
    atr_adx = tr.ewm(span=ADX_PERIOD, adjust=False).mean()
    plus_di = 100 * plus_dm.ewm(span=ADX_PERIOD, adjust=False).mean() / atr_adx.replace(0, np.nan)
    minus_di = 100 * minus_dm.ewm(span=ADX_PERIOD, adjust=False).mean() / atr_adx.replace(0, np.nan)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    feats["adx"] = dx.ewm(span=ADX_PERIOD, adjust=False).mean()
    feats["plus_di"] = plus_di
    feats["minus_di"] = minus_di

    obv = (np.sign(c.diff()) * v).fillna(0).cumsum()
    obv_slope_20 = obv.diff(20)
    # === v2 FIX 4: obv_zscore_120 (replaces obv) ===
    obv_mean_120 = obv.rolling(120).mean()
    obv_std_120 = obv.rolling(120).std().replace(0, np.nan)
    feats["obv_zscore_120"] = (obv - obv_mean_120) / obv_std_120
    # === v2 FIX 5: obv_slope_20_zscore (replaces obv_slope_20) ===
    obv_slope_mean = obv_slope_20.rolling(120).mean()
    obv_slope_std = obv_slope_20.rolling(120).std().replace(0, np.nan)
    feats["obv_slope_20_zscore"] = (obv_slope_20 - obv_slope_mean) / obv_slope_std

    feats["sma_20_ratio"] = c / c.rolling(20).mean()
    feats["sma_200_ratio"] = c / c.rolling(200).mean()

    # ── Volatility (10) ──
    log_ret = np.log(c / c.shift(1))
    for w in VOL_WINDOWS:
        feats[f"realized_vol_{w}"] = log_ret.rolling(w).std()
        feats[f"vol_of_vol_{w}"] = log_ret.rolling(w).std().rolling(w).std()
    feats["vol_ratio_10_60"] = log_ret.rolling(10).std() / log_ret.rolling(60).std().replace(0, np.nan)
    feats["atr_ratio_5_20"] = tr.rolling(5).mean() / tr.rolling(20).mean().replace(0, np.nan)

    # ── Microstructure (8) ──
    feats["spread_pct"] = spread / c
    feats["spread_zscore_60"] = (spread - spread.rolling(60).mean()) / spread.rolling(60).std().replace(0, np.nan)
    feats["volume_zscore_60"] = (v - v.rolling(60).mean()) / v.rolling(60).std().replace(0, np.nan)
    feats["volume_ratio_5_20"] = v.rolling(5).mean() / v.rolling(20).mean().replace(0, np.nan)
    body = (c - o).abs()
    full_range = (h - l).replace(0, np.nan)
    feats["body_ratio"] = body / full_range
    feats["upper_wick_ratio"] = (h - np.maximum(o, c)) / full_range
    feats["lower_wick_ratio"] = (np.minimum(o, c) - l) / full_range
    feats["body_dir"] = (c - o) / full_range

    # ── Time (9) ──
    ts = df.index
    hour = ts.hour + ts.minute / 60.0
    feats["hour_sin"] = np.sin(2 * np.pi * hour / 24)
    feats["hour_cos"] = np.cos(2 * np.pi * hour / 24)
    dow = ts.dayofweek
    feats["dow_sin"] = np.sin(2 * np.pi * dow / 7)
    feats["dow_cos"] = np.cos(2 * np.pi * dow / 7)
    feats["asia_session"] = ((hour >= 0) & (hour < 8)).astype(int)
    feats["eu_session"] = ((hour >= 7) & (hour < 16)).astype(int)
    feats["us_session"] = ((hour >= 13) & (hour < 22)).astype(int)
    month = ts.month
    feats["month_sin"] = np.sin(2 * np.pi * month / 12)
    feats["month_cos"] = np.cos(2 * np.pi * month / 12)

    # ── Lag (7) ──
    for hz in LAG_HORIZONS:
        feats[f"ret_lag_{hz}"] = c.pct_change(hz).shift(1)

    # Reorder to match FEATURE_NAMES_V2 exactly
    feats = feats[FEATURE_NAMES_V2]
    return feats


def standardize_v2(features_matrix: np.ndarray, mean: np.ndarray, std: np.ndarray) -> np.ndarray:
    """Standardize v2 features using v2 training mean/std."""
    std_safe = np.where(std == 0, 1.0, std)
    out = (features_matrix - mean) / std_safe
    return np.nan_to_num(out, nan=0.0, posinf=0.0, neginf=0.0)


def compute_scaler_stats_v2(features_df: pd.DataFrame) -> dict:
    """Compute v2 scaler stats (mean/std per feature) for standardization."""
    means = {name: float(features_df[name].mean()) for name in FEATURE_NAMES_V2}
    stds = {name: float(features_df[name].std()) for name in FEATURE_NAMES_V2}
    return {"mean": means, "std": stds, "n_features": N_FEATURES_V2}


__all__ = [
    "compute_v2_features",
    "standardize_v2",
    "compute_scaler_stats_v2",
    "MIN_BARS_FOR_FULL_FEATURES_V2",
]
