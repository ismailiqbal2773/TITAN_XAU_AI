"""
TITAN XAU AI — Feature Schema v2 (Sprint v2.8.7-E)
====================================================
Defines the v2 feature schema that replaces 5 absolute-price features
with stationary/relative equivalents. This eliminates the OOS feature
drift identified in Sprint v2.8.7-D.

v2 Replacements (drop absolute, add relative):
  macd_signal       → macd_signal_relative      (macd_signal / close)
  macd_hist         → macd_hist_relative        (macd_hist / close)
  bb_upper          → bb_distance_upper         ((bb_upper - close) / close)
  obv               → obv_zscore_120            (rolling z-score of OBV)
  obv_slope_20      → obv_slope_20_zscore       (rolling z-score of slope)

All other 50 features remain unchanged from v1 (they are already
stationary: returns, ratios, z-scores, cyclical time, etc.).

This module is the single source of truth for the v2 schema.
feature_engine_v2.py and feature_stream_v2.py both import FEATURE_NAMES_V2
and ABSOLUTE_TO_RELATIVE mapping from here.

NEVER sends orders. NEVER creates tokens. NEVER trades.
"""
from __future__ import annotations

from typing import Dict, List, Tuple

# v1 feature names (55 features, in fixed order — must match
# titan.production.feature_stream.FEATURE_NAMES)
FEATURE_NAMES_V1: List[str] = [
    "n_brokers", "ret_1", "ret_5", "ret_15", "price_zscore_60", "hl_range",
    "close_pos_in_range", "rsi", "macd_signal", "macd_hist", "bb_upper",
    "bb_width", "bb_pct_b", "atr", "adx", "plus_di", "minus_di", "obv",
    "obv_slope_20", "sma_20_ratio", "sma_200_ratio", "realized_vol_10",
    "vol_of_vol_10", "realized_vol_20", "vol_of_vol_20", "realized_vol_60",
    "vol_of_vol_60", "realized_vol_120", "vol_of_vol_120", "vol_ratio_10_60",
    "atr_ratio_5_20", "spread_pct", "spread_zscore_60", "volume_zscore_60",
    "volume_ratio_5_20", "body_ratio", "upper_wick_ratio", "lower_wick_ratio",
    "body_dir", "hour_sin", "hour_cos", "dow_sin", "dow_cos", "asia_session",
    "eu_session", "us_session", "month_sin", "month_cos", "ret_lag_1",
    "ret_lag_2", "ret_lag_3", "ret_lag_5", "ret_lag_10", "ret_lag_20",
    "ret_lag_60",
]

# Absolute-price features that drift in OOS (root cause of v2.8.7-D collapse)
# These will be REMOVED in v2 and replaced by their relative equivalents.
ABSOLUTE_FEATURES_V1: List[str] = [
    "macd_signal",
    "macd_hist",
    "bb_upper",
    "obv",
    "obv_slope_20",
]

# Mapping: old absolute feature → new relative/stationary feature
ABSOLUTE_TO_RELATIVE: Dict[str, str] = {
    "macd_signal":  "macd_signal_relative",
    "macd_hist":    "macd_hist_relative",
    "bb_upper":     "bb_distance_upper",
    "obv":          "obv_zscore_120",
    "obv_slope_20": "obv_slope_20_zscore",
}

# v2 feature names = v1 with absolute features replaced by relative versions.
# Order: replace each absolute feature in-place so positional index is
# preserved where possible (this keeps META_FEATURE_NAMES valid after rename).
FEATURE_NAMES_V2: List[str] = []
for name in FEATURE_NAMES_V1:
    if name in ABSOLUTE_TO_RELATIVE:
        FEATURE_NAMES_V2.append(ABSOLUTE_TO_RELATIVE[name])
    else:
        FEATURE_NAMES_V2.append(name)

N_FEATURES_V2: int = len(FEATURE_NAMES_V2)  # = 55

# v2 meta-feature names (subset used by meta-label model).
# Map each v1 meta name to its v2 equivalent.
META_FEATURE_NAMES_V1: List[str] = [
    "n_brokers", "spread_pct", "spread_zscore_60", "volume_zscore_60",
    "volume_ratio_5_20", "body_ratio", "upper_wick_ratio", "lower_wick_ratio",
    "body_dir", "ret_1", "ret_5", "ret_15", "price_zscore_60", "hl_range",
    "close_pos_in_range", "ret_lag_1", "ret_lag_2", "ret_lag_3", "ret_lag_5",
    "ret_lag_10", "ret_lag_20", "ret_lag_60",
]
META_FEATURE_NAMES_V2: List[str] = [
    ABSOLUTE_TO_RELATIVE.get(n, n) for n in META_FEATURE_NAMES_V1
]


# ─── Classification of all 55 v1 features ─────────────────────────────

# Features that are already stationary (no price-level dependence).
STATIONARY_FEATURES: List[str] = [
    "n_brokers", "ret_1", "ret_5", "ret_15", "price_zscore_60", "hl_range",
    "close_pos_in_range", "rsi", "bb_width", "bb_pct_b", "atr", "adx",
    "plus_di", "minus_di", "sma_20_ratio", "sma_200_ratio",
    "realized_vol_10", "vol_of_vol_10", "realized_vol_20", "vol_of_vol_20",
    "realized_vol_60", "vol_of_vol_60", "realized_vol_120",
    "vol_of_vol_120", "vol_ratio_10_60", "atr_ratio_5_20",
    "spread_pct", "spread_zscore_60", "volume_zscore_60",
    "volume_ratio_5_20", "body_ratio", "upper_wick_ratio",
    "lower_wick_ratio", "body_dir", "hour_sin", "hour_cos", "dow_sin",
    "dow_cos", "asia_session", "eu_session", "us_session", "month_sin",
    "month_cos", "ret_lag_1", "ret_lag_2", "ret_lag_3", "ret_lag_5",
    "ret_lag_10", "ret_lag_20", "ret_lag_60",
]

# Absolute price-level features (drift in OOS)
PRICE_LEVEL_ABSOLUTE: List[str] = ABSOLUTE_FEATURES_V1  # 5 features

# Broker-sensitive features (already handled by spread normalization v2.8.7-C)
BROKER_SENSITIVE: List[str] = [
    "spread_pct", "spread_zscore_60",
]


def classify_feature(name: str) -> str:
    """Classify a v1 feature by its drift risk."""
    if name in PRICE_LEVEL_ABSOLUTE:
        return "price_level_absolute"
    if name in BROKER_SENSITIVE:
        return "broker_sensitive"
    if name in STATIONARY_FEATURES:
        return "stationary"
    return "unknown"


def get_v2_feature_index(v1_name: str) -> int:
    """Get the positional index of a v1 feature's v2 replacement."""
    v2_name = ABSOLUTE_TO_RELATIVE.get(v1_name, v1_name)
    return FEATURE_NAMES_V2.index(v2_name)


def get_v1_to_v2_name_map() -> Dict[str, str]:
    """Return mapping from v1 feature names to v2 feature names."""
    out = {}
    for v1_name in FEATURE_NAMES_V1:
        out[v1_name] = ABSOLUTE_TO_RELATIVE.get(v1_name, v1_name)
    return out


__all__ = [
    "FEATURE_NAMES_V1",
    "FEATURE_NAMES_V2",
    "N_FEATURES_V2",
    "ABSOLUTE_FEATURES_V1",
    "ABSOLUTE_TO_RELATIVE",
    "META_FEATURE_NAMES_V1",
    "META_FEATURE_NAMES_V2",
    "STATIONARY_FEATURES",
    "PRICE_LEVEL_ABSOLUTE",
    "BROKER_SENSITIVE",
    "classify_feature",
    "get_v2_feature_index",
    "get_v1_to_v2_name_map",
]
