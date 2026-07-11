"""TITAN XAU AI — Corrected Regime Classifier (Sprint v2.8.7-P1)
================================================================
Fixes bug: directionless TREND state. Now classifies directional regimes.

Required states:
  STRONG_BULL_TREND, WEAK_BULL_TREND, STRONG_BEAR_TREND, WEAK_BEAR_TREND,
  STABLE_RANGE, VOLATILITY_COMPRESSION, BREAKOUT_EXPANSION,
  TRANSITION_CHOP, SPREAD_STRESS, LIQUIDITY_STRESS, UNKNOWN_UNSAFE

Insufficient data returns UNKNOWN_UNSAFE (not NORMAL).

NEVER sends orders. NEVER creates tokens. NEVER trades.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import numpy as np
import pandas as pd


class RegimeType(str, Enum):
    STRONG_BULL_TREND = "STRONG_BULL_TREND"
    WEAK_BULL_TREND = "WEAK_BULL_TREND"
    STRONG_BEAR_TREND = "STRONG_BEAR_TREND"
    WEAK_BEAR_TREND = "WEAK_BEAR_TREND"
    STABLE_RANGE = "STABLE_RANGE"
    VOLATILITY_COMPRESSION = "VOLATILITY_COMPRESSION"
    BREAKOUT_EXPANSION = "BREAKOUT_EXPANSION"
    TRANSITION_CHOP = "TRANSITION_CHOP"
    SPREAD_STRESS = "SPREAD_STRESS"
    LIQUIDITY_STRESS = "LIQUIDITY_STRESS"
    UNKNOWN_UNSAFE = "UNKNOWN_UNSAFE"


@dataclass
class RegimeResult:
    """Full regime classification result."""
    regime: RegimeType
    direction: str          # "BULL", "BEAR", "NEUTRAL", "UNKNOWN"
    confidence: float       # 0-1
    evidence: list          # reason strings
    reason_codes: list
    allowed_setup_types: list
    blocked_setup_types: list
    risk_modifier: float    # multiplier for risk (e.g., 0.5 = half risk)
    threshold_modifier: float  # additive for thresholds (e.g., +0.05 = tighter)
    exit_sensitivity_modifier: float  # multiplier for exit sensitivity


def classify_regime_corrected(df: pd.DataFrame, min_bars: int = 60) -> RegimeResult:
    """Classify market regime with directional awareness.

    Args:
        df: OHLCV DataFrame with at least min_bars rows.
        min_bars: Minimum bars required for classification.

    Returns:
        RegimeResult with full regime information.
    """
    # Insufficient data → UNKNOWN_UNSAFE (never silently NORMAL)
    if df is None or len(df) < min_bars:
        return RegimeResult(
            regime=RegimeType.UNKNOWN_UNSAFE,
            direction="UNKNOWN", confidence=0.0,
            evidence=["insufficient_data"],
            reason_codes=["INSUFFICIENT_BARS"],
            allowed_setup_types=[], blocked_setup_types=["ALL"],
            risk_modifier=0.0, threshold_modifier=0.10,
            exit_sensitivity_modifier=1.0,
        )

    closes = df["close"]
    highs = df["high"]
    lows = df["low"]
    volumes = df.get("volume", pd.Series([0] * len(df)))
    spreads = df.get("spread", pd.Series([0] * len(df)))

    current = float(closes.iloc[-1])
    sma_10 = float(closes.tail(10).mean())
    sma_20 = float(closes.tail(20).mean())
    sma_50 = float(closes.tail(50).mean()) if len(closes) >= 50 else sma_20

    # ATR-based volatility
    ranges = (highs - lows).tail(20)
    current_atr = float(ranges.mean())
    long_atr = float((highs - lows).tail(60).mean()) if len(df) >= 60 else current_atr

    # Volatility ratio
    vol_ratio = current_atr / max(long_atr, 0.001)

    # Spread analysis
    current_spread = float(spreads.iloc[-1]) if len(spreads) > 0 else 0
    avg_spread = float(spreads.tail(60).mean()) if len(spreads) >= 60 else current_spread
    spread_ratio = current_spread / max(avg_spread, 0.001)

    # Volume analysis
    current_vol = float(volumes.iloc[-1]) if len(volumes) > 0 else 0
    avg_vol = float(volumes.tail(20).mean()) if len(volumes) >= 20 else current_vol
    vol_ratio_value = current_vol / max(avg_vol, 0.001)

    # Direction from moving averages
    bull_trend = current > sma_10 > sma_20
    bear_trend = current < sma_10 < sma_20
    strong_bull = current > sma_10 > sma_20 > sma_50
    strong_bear = current < sma_10 < sma_20 < sma_50

    # Range detection: check range first if no strong trend
    range_20 = float(highs.tail(20).max() - lows.tail(20).min())
    range_pct = range_20 / current if current > 0 else 0
    is_range = range_pct < 0.02 and not (strong_bull or strong_bear)
    # Also check weak trends — if range is very tight, classify as range even with weak trend
    is_tight_range = range_pct < 0.01

    # Choppy / transition
    sma_cross_count = 0
    for k in range(1, min(10, len(closes) - 1)):
        if (closes.iloc[-k] > sma_10 and closes.iloc[-k-1] < sma_10) or \
           (closes.iloc[-k] < sma_10 and closes.iloc[-k-1] > sma_10):
            sma_cross_count += 1
    is_choppy = sma_cross_count >= 3

    evidence = []
    reason_codes = []

    # Spread stress
    if spread_ratio > 2.0:
        evidence.append(f"spread_expansion: {spread_ratio:.1f}x average")
        reason_codes.append("SPREAD_EXPANSION")
        return RegimeResult(
            regime=RegimeType.SPREAD_STRESS,
            direction="NEUTRAL", confidence=0.3,
            evidence=evidence, reason_codes=reason_codes,
            allowed_setup_types=[], blocked_setup_types=["ALL"],
            risk_modifier=0.0, threshold_modifier=0.10,
            exit_sensitivity_modifier=1.5,
        )

    # Liquidity stress (very low volume)
    if vol_ratio_value < 0.3 and avg_vol > 0:
        evidence.append(f"low_liquidity: volume {vol_ratio_value:.1%} of average")
        reason_codes.append("LOW_LIQUIDITY")
        return RegimeResult(
            regime=RegimeType.LIQUIDITY_STRESS,
            direction="NEUTRAL", confidence=0.3,
            evidence=evidence, reason_codes=reason_codes,
            allowed_setup_types=[], blocked_setup_types=["ALL"],
            risk_modifier=0.0, threshold_modifier=0.08,
            exit_sensitivity_modifier=1.3,
        )

    # Volatility compression
    if vol_ratio < 0.6:
        evidence.append(f"volatility_compression: ATR {vol_ratio:.1%} of long-term")
        reason_codes.append("VOL_COMPRESSION")
        return RegimeResult(
            regime=RegimeType.VOLATILE_COMPRESSION if False else RegimeType.VOLATILITY_COMPRESSION,
            direction="NEUTRAL", confidence=0.4,
            evidence=evidence, reason_codes=reason_codes,
            allowed_setup_types=["FAIR_VALUE_GAP", "BREAKOUT"],
            blocked_setup_types=["PULLBACK", "LIQUIDITY_SWEEP"],
            risk_modifier=0.5, threshold_modifier=0.02,
            exit_sensitivity_modifier=0.8,
        )

    # Breakout expansion
    if vol_ratio > 1.8:
        if strong_bull:
            evidence.append(f"breakout_expansion_bull: ATR {vol_ratio:.1%} of long-term, strong bull alignment")
            reason_codes.append(["BREAKOUT_EXPANSION", "STRONG_BULL"])
            return RegimeResult(
                regime=RegimeType.BREAKOUT_EXPANSION,
                direction="BULL", confidence=0.7,
                evidence=evidence, reason_codes=reason_codes,
                allowed_setup_types=["BREAKOUT", "BREAK_OF_STRUCTURE", "CONTINUATION"],
                blocked_setup_types=["PULLBACK"],
                risk_modifier=1.0, threshold_modifier=0.0,
                exit_sensitivity_modifier=1.2,
            )
        elif strong_bear:
            evidence.append(f"breakout_expansion_bear: ATR {vol_ratio:.1%} of long-term, strong bear alignment")
            reason_codes.append(["BREAKOUT_EXPANSION", "STRONG_BEAR"])
            return RegimeResult(
                regime=RegimeType.BREAKOUT_EXPANSION,
                direction="BEAR", confidence=0.7,
                evidence=evidence, reason_codes=reason_codes,
                allowed_setup_types=["BREAKOUT", "BREAK_OF_STRUCTURE", "CONTINUATION"],
                blocked_setup_types=["PULLBACK"],
                risk_modifier=1.0, threshold_modifier=0.0,
                exit_sensitivity_modifier=1.2,
            )

    # Transition chop
    if is_choppy and not (strong_bull or strong_bear):
        evidence.append(f"transition_chop: {sma_cross_count} SMA crosses in last 10 bars")
        reason_codes.append("CHOPPY_TRANSITION")
        return RegimeResult(
            regime=RegimeType.TRANSITION_CHOP,
            direction="NEUTRAL", confidence=0.2,
            evidence=evidence, reason_codes=reason_codes,
            allowed_setup_types=["LIQUIDITY_SWEEP"],
            blocked_setup_types=["PULLBACK", "BREAKOUT", "BREAK_OF_STRUCTURE"],
            risk_modifier=0.3, threshold_modifier=0.05,
            exit_sensitivity_modifier=1.4,
        )

    # Strong bull trend
    if strong_bull:
        evidence.append("strong_bull_trend: price > SMA10 > SMA20 > SMA50")
        reason_codes.append("STRONG_BULL_TREND")
        return RegimeResult(
            regime=RegimeType.STRONG_BULL_TREND,
            direction="BULL", confidence=0.8,
            evidence=evidence, reason_codes=reason_codes,
            allowed_setup_types=["PULLBACK", "BREAK_OF_STRUCTURE", "CONTINUATION", "BREAKOUT"],
            blocked_setup_types=[],
            risk_modifier=1.0, threshold_modifier=0.0,
            exit_sensitivity_modifier=1.0,
        )

    # Strong bear trend
    if strong_bear:
        evidence.append("strong_bear_trend: price < SMA10 < SMA20 < SMA50")
        reason_codes.append("STRONG_BEAR_TREND")
        return RegimeResult(
            regime=RegimeType.STRONG_BEAR_TREND,
            direction="BEAR", confidence=0.8,
            evidence=evidence, reason_codes=reason_codes,
            allowed_setup_types=["PULLBACK", "BREAK_OF_STRUCTURE", "CONTINUATION", "BREAKOUT"],
            blocked_setup_types=[],
            risk_modifier=1.0, threshold_modifier=0.0,
            exit_sensitivity_modifier=1.0,
        )

    # Weak bull trend (only if not tight range)
    if bull_trend and not is_tight_range:
        evidence.append("weak_bull_trend: price > SMA10 > SMA20 (no SMA50 confirmation)")
        reason_codes.append("WEAK_BULL_TREND")
        return RegimeResult(
            regime=RegimeType.WEAK_BULL_TREND,
            direction="BULL", confidence=0.5,
            evidence=evidence, reason_codes=reason_codes,
            allowed_setup_types=["PULLBACK", "CONTINUATION"],
            blocked_setup_types=["BREAKOUT"],
            risk_modifier=0.7, threshold_modifier=0.02,
            exit_sensitivity_modifier=1.1,
        )

    # Weak bear trend (only if not tight range)
    if bear_trend and not is_tight_range:
        evidence.append("weak_bear_trend: price < SMA10 < SMA20 (no SMA50 confirmation)")
        reason_codes.append("WEAK_BEAR_TREND")
        return RegimeResult(
            regime=RegimeType.WEAK_BEAR_TREND,
            direction="BEAR", confidence=0.5,
            evidence=evidence, reason_codes=reason_codes,
            allowed_setup_types=["PULLBACK", "CONTINUATION"],
            blocked_setup_types=["BREAKOUT"],
            risk_modifier=0.7, threshold_modifier=0.02,
            exit_sensitivity_modifier=1.1,
        )

    # Stable range
    if is_range:
        evidence.append(f"stable_range: 20-bar range {range_pct:.2%} of price")
        reason_codes.append("STABLE_RANGE")
        return RegimeResult(
            regime=RegimeType.STABLE_RANGE,
            direction="NEUTRAL", confidence=0.4,
            evidence=evidence, reason_codes=reason_codes,
            allowed_setup_types=["LIQUIDITY_SWEEP", "FAIR_VALUE_GAP", "RANGE_EDGE_REJECTION"],
            blocked_setup_types=["PULLBACK", "BREAK_OF_STRUCTURE"],
            risk_modifier=0.5, threshold_modifier=0.03,
            exit_sensitivity_modifier=1.2,
        )

    # Fallback: unknown unsafe
    evidence.append("no_clear_regime: conditions mixed")
    reason_codes.append("UNKNOWN_REGIME")
    return RegimeResult(
        regime=RegimeType.UNKNOWN_UNSAFE,
        direction="UNKNOWN", confidence=0.0,
        evidence=evidence, reason_codes=reason_codes,
        allowed_setup_types=[], blocked_setup_types=["ALL"],
        risk_modifier=0.0, threshold_modifier=0.10,
        exit_sensitivity_modifier=1.0,
    )


__all__ = ["RegimeType", "RegimeResult", "classify_regime_corrected"]
