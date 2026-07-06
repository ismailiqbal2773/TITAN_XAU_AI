"""
TITAN XAU AI — MTF Confirmation Helper (Sprint v2.8.7-E)
==========================================================
Real multi-timeframe confirmation for backtest and parameter discovery.

Implements actual M15 confirmation and M5 entry trigger checks using
lower-timeframe bar data. This fixes the v2.8.7-D finding that
h1_only/h1_m15/h1_m15_m5 produced identical results.

Rules (per Sprint v2.8.7-E spec):
  - h1_only:    H1 alpha/meta only. No M15/M5 check.
  - h1_m15:     H1 alpha/meta must pass AND M15 confirmation must pass.
                M15 confirmation = direction alignment (M15 close vs M15 SMA)
                AND volatility not abnormal (M15 ATR within sane band).
  - h1_m15_m5:  Above + M5 entry trigger must pass.
                M5 trigger = M5 momentum confirms direction (last bar close
                vs prior bar close) AND spread acceptable.

No future leakage: at H1 bar timestamp T, we look only at M15/M5 bars
with timestamp <= T (already-closed lower-timeframe bars).

NEVER sends orders. NEVER creates tokens. NEVER trades.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional, Literal

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

MTFMode = Literal["h1_only", "h1_m15", "h1_m15_m5"]


@dataclass
class MTFConfirmationResult:
    """Result of MTF confirmation check for a single H1 bar."""
    mtf_mode: str
    m15_used: bool
    m15_confirmation_pass: bool
    m5_used: bool
    m5_entry_trigger_pass: bool
    mtf_reject_reason: str
    m15_direction: str   # "LONG" / "SHORT" / "NEUTRAL" / "N/A"
    m5_direction: str    # "LONG" / "SHORT" / "NEUTRAL" / "N/A"


def load_m15_bars(canonical_path: Optional[str] = None) -> pd.DataFrame:
    """Load M15 canonical bars."""
    import os
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    path = canonical_path or os.path.join(repo_root, "titan", "data", "canonical",
                                           "XAUUSD_M15_canonical.parquet")
    if not os.path.exists(path):
        return pd.DataFrame()
    df = pd.read_parquet(path)
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)
    return df


def load_m5_bars(canonical_path: Optional[str] = None) -> pd.DataFrame:
    """Load M5 canonical bars."""
    import os
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    path = canonical_path or os.path.join(repo_root, "titan", "data", "canonical",
                                           "XAUUSD_M5_canonical.parquet")
    if not os.path.exists(path):
        return pd.DataFrame()
    df = pd.read_parquet(path)
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)
    return df


def check_m15_confirmation(
    m15_bars: pd.DataFrame,
    h1_timestamp: pd.Timestamp,
    h1_direction: str,
    sma_period: int = 20,
    _cache: dict = None,
) -> tuple[bool, str, str]:
    """Check M15 confirmation for an H1 bar.

    Args:
        m15_bars: M15 OHLCV DataFrame (DatetimeIndex).
        h1_timestamp: Timestamp of the H1 bar (we look at M15 bars <= this).
        h1_direction: "LONG" or "SHORT" — the H1 alpha direction.
        sma_period: M15 SMA period for trend confirmation.
        _cache: Optional dict for caching precomputed M15 features.

    Returns:
        (pass: bool, reject_reason: str, m15_direction: str)
    """
    if m15_bars.empty:
        return False, "M15_DATA_MISSING", "N/A"

    # === Performance optimization: precompute M15 features once ===
    if _cache is not None and "m15_close_sma" not in _cache:
        _cache["m15_close_sma"] = m15_bars["close"].rolling(sma_period).mean()
        _cache["m15_atr_14"] = m15_bars["high"].rolling(14).max() - m15_bars["low"].rolling(14).min()
        # Approximate long-term ATR using rolling mean of recent bar ranges
        bar_ranges = m15_bars["high"] - m15_bars["low"]
        _cache["m15_atr_60"] = bar_ranges.rolling(60).mean()
        _cache["m15_index"] = m15_bars.index

    if _cache is not None and "m15_close_sma" in _cache:
        # Use cache + searchsorted for O(log n) lookup
        idx_arr = _cache["m15_index"]
        sma_arr = _cache["m15_close_sma"]
        atr14_arr = _cache["m15_atr_14"]
        atr60_arr = _cache["m15_atr_60"]
        close_arr = m15_bars["close"].values

        # Find position where h1_timestamp would be inserted (rightmost <=)
        pos = idx_arr.searchsorted(h1_timestamp, side="right") - 1
        if pos < sma_period:
            return False, "M15_INSUFFICIENT_HISTORY", "N/A"

        last_close = float(close_arr[pos])
        sma = float(sma_arr.iloc[pos])
        recent_atr = float(atr14_arr.iloc[pos]) if not np.isnan(atr14_arr.iloc[pos]) else 0
        long_term_atr = float(atr60_arr.iloc[pos]) if not np.isnan(atr60_arr.iloc[pos]) else recent_atr
    else:
        # Fallback: original slow path
        eligible = m15_bars.loc[:h1_timestamp]
        if len(eligible) < sma_period + 1:
            return False, "M15_INSUFFICIENT_HISTORY", "N/A"
        last_close = float(eligible["close"].iloc[-1])
        sma = float(eligible["close"].iloc[-sma_period:].mean())
        recent_atr = float(
            (eligible["high"].iloc[-14:] - eligible["low"].iloc[-14:]).mean()
        )
        long_term_atr = float(
            (eligible["high"].iloc[-60:] - eligible["low"].iloc[-60:]).mean()
        ) if len(eligible) >= 60 else recent_atr

    if long_term_atr > 0 and (recent_atr > 3 * long_term_atr or recent_atr < long_term_atr / 3):
        return False, "M15_VOLATILITY_ABNORMAL", "N/A"

    if last_close > sma:
        m15_direction = "LONG"
    elif last_close < sma:
        m15_direction = "SHORT"
    else:
        m15_direction = "NEUTRAL"

    if m15_direction == h1_direction:
        return True, "", m15_direction
    elif m15_direction == "NEUTRAL":
        return False, "M15_NEUTRAL", m15_direction
    else:
        return False, "M15_DIRECTION_MISMATCH", m15_direction


def check_m5_trigger(
    m5_bars: pd.DataFrame,
    h1_timestamp: pd.Timestamp,
    h1_direction: str,
    _cache: dict = None,
) -> tuple[bool, str, str]:
    """Check M5 entry trigger for an H1 bar.

    Args:
        m5_bars: M5 OHLCV DataFrame (DatetimeIndex).
        h1_timestamp: Timestamp of the H1 bar.
        h1_direction: "LONG" or "SHORT".
        _cache: Optional dict for caching precomputed M5 index.

    Returns:
        (pass: bool, reject_reason: str, m5_direction: str)
    """
    if m5_bars.empty:
        return False, "M5_DATA_MISSING", "N/A"

    if _cache is not None and "m5_index" not in _cache:
        _cache["m5_index"] = m5_bars.index
        _cache["m5_close"] = m5_bars["close"].values
        if "spread_usd" in m5_bars.columns:
            _cache["m5_spread"] = m5_bars["spread_usd"].values
        else:
            _cache["m5_spread"] = None

    if _cache is not None and "m5_index" in _cache:
        idx_arr = _cache["m5_index"]
        close_arr = _cache["m5_close"]
        spread_arr = _cache["m5_spread"]
        pos = idx_arr.searchsorted(h1_timestamp, side="right") - 1
        if pos < 2:
            return False, "M5_INSUFFICIENT_HISTORY", "N/A"
        last_close = float(close_arr[pos])
        prior_close = float(close_arr[pos - 1])
        if spread_arr is not None and not np.isnan(spread_arr[pos]):
            last_spread = float(spread_arr[pos])
            if last_spread > 1.0:
                # We need m5_direction still
                if last_close > prior_close:
                    m5_direction = "LONG"
                elif last_close < prior_close:
                    m5_direction = "SHORT"
                else:
                    m5_direction = "NEUTRAL"
                return False, "M5_SPREAD_TOO_WIDE", m5_direction
    else:
        eligible = m5_bars.loc[:h1_timestamp]
        if len(eligible) < 3:
            return False, "M5_INSUFFICIENT_HISTORY", "N/A"
        last_close = float(eligible["close"].iloc[-1])
        prior_close = float(eligible["close"].iloc[-2])
        if "spread_usd" in eligible.columns:
            last_spread = float(eligible["spread_usd"].iloc[-1])
            if last_spread > 1.0:
                if last_close > prior_close:
                    m5_direction = "LONG"
                elif last_close < prior_close:
                    m5_direction = "SHORT"
                else:
                    m5_direction = "NEUTRAL"
                return False, "M5_SPREAD_TOO_WIDE", m5_direction

    if last_close > prior_close:
        m5_direction = "LONG"
    elif last_close < prior_close:
        m5_direction = "SHORT"
    else:
        m5_direction = "NEUTRAL"

    if m5_direction == h1_direction:
        return True, "", m5_direction
    elif m5_direction == "NEUTRAL":
        return False, "M5_NEUTRAL", m5_direction
    else:
        return False, "M5_DIRECTION_MISMATCH", m5_direction


# Module-level caches (populated on first call, reused across all trades)
_M15_CACHE: dict = {}
_M5_CACHE: dict = {}


def evaluate_mtf(
    mtf_mode: str,
    h1_timestamp: pd.Timestamp,
    h1_direction: str,
    m15_bars: Optional[pd.DataFrame] = None,
    m5_bars: Optional[pd.DataFrame] = None,
) -> MTFConfirmationResult:
    """Evaluate MTF confirmation for a single H1 bar.

    Uses module-level caches for M15/M5 precomputed features to achieve
    O(log n) per-trade lookup instead of O(n).

    Args:
        mtf_mode: "h1_only", "h1_m15", or "h1_m15_m5".
        h1_timestamp: Timestamp of the H1 bar.
        h1_direction: "LONG" or "SHORT".
        m15_bars: M15 OHLCV DataFrame (required for h1_m15+ modes).
        m5_bars: M5 OHLCV DataFrame (required for h1_m15_m5 mode).

    Returns:
        MTFConfirmationResult with all flags set.
    """
    global _M15_CACHE, _M5_CACHE

    if mtf_mode == "h1_only":
        return MTFConfirmationResult(
            mtf_mode=mtf_mode,
            m15_used=False,
            m15_confirmation_pass=True,
            m5_used=False,
            m5_entry_trigger_pass=True,
            mtf_reject_reason="",
            m15_direction="N/A",
            m5_direction="N/A",
        )

    if mtf_mode == "h1_m15":
        if m15_bars is None or m15_bars.empty:
            return MTFConfirmationResult(
                mtf_mode=mtf_mode, m15_used=True, m15_confirmation_pass=False,
                m5_used=False, m5_entry_trigger_pass=True,
                mtf_reject_reason="M15_DATA_MISSING",
                m15_direction="N/A", m5_direction="N/A",
            )
        m15_pass, m15_reason, m15_dir = check_m15_confirmation(
            m15_bars, h1_timestamp, h1_direction, _cache=_M15_CACHE,
        )
        return MTFConfirmationResult(
            mtf_mode=mtf_mode,
            m15_used=True,
            m15_confirmation_pass=m15_pass,
            m5_used=False,
            m5_entry_trigger_pass=True,
            mtf_reject_reason=m15_reason,
            m15_direction=m15_dir,
            m5_direction="N/A",
        )

    if mtf_mode == "h1_m15_m5":
        if m15_bars is None or m15_bars.empty:
            return MTFConfirmationResult(
                mtf_mode=mtf_mode, m15_used=True, m15_confirmation_pass=False,
                m5_used=True, m5_entry_trigger_pass=False,
                mtf_reject_reason="M15_DATA_MISSING",
                m15_direction="N/A", m5_direction="N/A",
            )
        m15_pass, m15_reason, m15_dir = check_m15_confirmation(
            m15_bars, h1_timestamp, h1_direction, _cache=_M15_CACHE,
        )
        if not m15_pass:
            return MTFConfirmationResult(
                mtf_mode=mtf_mode, m15_used=True, m15_confirmation_pass=False,
                m5_used=True, m5_entry_trigger_pass=False,
                mtf_reject_reason=m15_reason,
                m15_direction=m15_dir, m5_direction="N/A",
            )
        if m5_bars is None or m5_bars.empty:
            return MTFConfirmationResult(
                mtf_mode=mtf_mode, m15_used=True, m15_confirmation_pass=True,
                m5_used=True, m5_entry_trigger_pass=False,
                mtf_reject_reason="M5_DATA_MISSING",
                m15_direction=m15_dir, m5_direction="N/A",
            )
        m5_pass, m5_reason, m5_dir = check_m5_trigger(
            m5_bars, h1_timestamp, h1_direction, _cache=_M5_CACHE,
        )
        return MTFConfirmationResult(
            mtf_mode=mtf_mode,
            m15_used=True,
            m15_confirmation_pass=True,
            m5_used=True,
            m5_entry_trigger_pass=m5_pass,
            mtf_reject_reason=m5_reason,
            m15_direction=m15_dir,
            m5_direction=m5_dir,
        )

    return MTFConfirmationResult(
        mtf_mode=mtf_mode, m15_used=False, m15_confirmation_pass=False,
        m5_used=False, m5_entry_trigger_pass=False,
        mtf_reject_reason=f"UNKNOWN_MTF_MODE:{mtf_mode}",
        m15_direction="N/A", m5_direction="N/A",
    )


def reset_mtf_caches():
    """Clear M15/M5 caches (call when bar data changes)."""
    global _M15_CACHE, _M5_CACHE
    _M15_CACHE.clear()
    _M5_CACHE.clear()


__all__ = [
    "MTFMode",
    "MTFConfirmationResult",
    "load_m15_bars",
    "load_m5_bars",
    "check_m15_confirmation",
    "check_m5_trigger",
    "evaluate_mtf",
]
