"""TITAN XAU AI — Feature Warm-up Calculator (v2.8.7-P2.4)
==========================================================

Calculates the exact maximum feature lookback from feature definitions.

Feature lookbacks:
  - SMA 200: rolling(200) → 200 bars
  - vol_of_vol_120: rolling(120).std().rolling(120).std() → 120 + 120 - 1 = 239 bars
  - vol_of_vol_60: rolling(60).std().rolling(60).std() → 60 + 60 - 1 = 119 bars
  - realized_vol_120: rolling(120).std() → 120 bars
  - return lag 60: shift(60) → 60 bars
  - price_zscore_60: rolling(60) → 60 bars

Maximum compound lookback = vol_of_vol_120 = 239 bars

required_warmup = 239 (derived from code, not hard-coded)

NEVER sends orders. NEVER creates tokens. NEVER trades.
"""
from __future__ import annotations

# Feature lookback constants derived from feature_stream.py definitions
SMA_200_LOOKBACK = 200
VOL_OF_VOL_120_LOOKBACK = 120 + 120 - 1  # rolling(120).std().rolling(120).std() = 239
VOL_OF_VOL_60_LOOKBACK = 60 + 60 - 1     # rolling(60).std().rolling(60).std() = 119
REALIZED_VOL_120_LOOKBACK = 120
RETURN_LAG_60 = 60
PRICE_ZSCORE_60 = 60
OBV_ROLLING_120 = 120
OBV_SLOPE_20_PLUS_ROLLING_120 = 20 + 120 - 1  # rolling(120).shift(20) = 139

# Exact maximum mathematical lookback from all features
# vol_of_vol_120 = 239 is the maximum
REQUIRED_WARMUP = max(
    SMA_200_LOOKBACK,           # 200
    VOL_OF_VOL_120_LOOKBACK,    # 239
    VOL_OF_VOL_60_LOOKBACK,     # 119
    REALIZED_VOL_120_LOOKBACK,  # 120
    RETURN_LAG_60,              # 60
    PRICE_ZSCORE_60,            # 60
    OBV_ROLLING_120,            # 120
    OBV_SLOPE_20_PLUS_ROLLING_120,  # 139
)

# Additional safety margin for label horizon + ATR
LABEL_HORIZON = 5  # 5-bar prediction horizon
PURGE_BARS = LABEL_HORIZON
EMBARGO_BARS = LABEL_HORIZON
WARMUP_WITH_PURGE = REQUIRED_WARMUP + PURGE_BARS + EMBARGO_BARS


def get_required_warmup() -> int:
    """Return the exact required warm-up bars derived from feature definitions."""
    return REQUIRED_WARMUP


def get_warmup_with_purge_embargo() -> int:
    """Return warm-up including purge and embargo bars."""
    return WARMUP_WITH_PURGE


__all__ = [
    "REQUIRED_WARMUP", "WARMUP_WITH_PURGE",
    "LABEL_HORIZON", "PURGE_BARS", "EMBARGO_BARS",
    "get_required_warmup", "get_warmup_with_purge_embargo",
]
