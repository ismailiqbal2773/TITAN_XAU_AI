"""TITAN XAU AI — Corrected Regime Classifier V2 (Sprint v2.8.7-P1.1)
=====================================================================
DG7 fixes: missing spread → UNKNOWN_UNSAFE; flat string reason codes;
true range ATR; rolling MA for chop; no dead enum expressions.

NEVER sends orders. NEVER creates tokens. NEVER trades.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List
import numpy as np
import pandas as pd


class RegimeTypeV2(str, Enum):
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
class RegimeResultV2:
    regime: RegimeTypeV2
    direction: str
    confidence: float
    evidence: List[str]
    reason_codes: List[str]  # Always flat strings
    allowed_setup_types: List[str]
    blocked_setup_types: List[str]
    risk_modifier: float
    threshold_modifier: float
    exit_sensitivity_modifier: float


def classify_regime_v2(df: pd.DataFrame, min_bars: int = 60) -> RegimeResultV2:
    """Classify regime with all DG7 corrections."""
    if df is None or len(df) < min_bars:
        return RegimeResultV2(
            regime=RegimeTypeV2.UNKNOWN_UNSAFE, direction="UNKNOWN",
            confidence=0.0, evidence=["insufficient_data"],
            reason_codes=["INSUFFICIENT_BARS"],
            allowed_setup_types=[], blocked_setup_types=["ALL"],
            risk_modifier=0.0, threshold_modifier=0.10,
            exit_sensitivity_modifier=1.0,
        )

    # DG7: Missing spread → UNKNOWN_UNSAFE (not zero/safe)
    if "spread" not in df.columns and "spread_usd" not in df.columns:
        return RegimeResultV2(
            regime=RegimeTypeV2.UNKNOWN_UNSAFE, direction="UNKNOWN",
            confidence=0.0, evidence=["missing_spread_data"],
            reason_codes=["MISSING_SPREAD"],
            allowed_setup_types=[], blocked_setup_types=["ALL"],
            risk_modifier=0.0, threshold_modifier=0.10,
            exit_sensitivity_modifier=1.0,
        )

    spread_col = "spread" if "spread" in df.columns else "spread_usd"
    closes = df["close"]
    highs = df["high"]
    lows = df["low"]
    volumes = df.get("volume", None)
    spreads = df[spread_col]

    current = float(closes.iloc[-1])
    # DG7: Rolling moving averages
    sma_10 = float(closes.rolling(10).mean().iloc[-1])
    sma_20 = float(closes.rolling(20).mean().iloc[-1])
    sma_50 = float(closes.rolling(50).mean().iloc[-1]) if len(closes) >= 50 else sma_20

    # DG7: True range ATR (not just high-low)
    tr = pd.concat([
        highs - lows,
        (highs - closes.shift(1)).abs(),
        (lows - closes.shift(1)).abs(),
    ], axis=1).max(axis=1)
    current_atr = float(tr.tail(20).mean())
    long_atr = float(tr.tail(60).mean()) if len(df) >= 60 else current_atr
    vol_ratio = current_atr / max(long_atr, 0.001)

    # Spread analysis
    current_spread = float(spreads.iloc[-1])
    avg_spread = float(spreads.tail(60).mean()) if len(spreads) >= 60 else current_spread
    spread_ratio = current_spread / max(avg_spread, 0.001)

    # DG7: Volume — check if reliable
    has_volume = volumes is not None and volumes.iloc[-1] > 0
    current_vol = float(volumes.iloc[-1]) if has_volume else 0
    avg_vol = float(volumes.tail(20).mean()) if has_volume and len(volumes) >= 20 else 0
    vol_ratio_val = current_vol / max(avg_vol, 0.001) if avg_vol > 0 else 1.0

    # Direction
    strong_bull = current > sma_10 > sma_20 > sma_50
    strong_bear = current < sma_10 < sma_20 < sma_50
    bull_trend = current > sma_10 > sma_20
    bear_trend = current < sma_10 < sma_20

    # Range
    range_20 = float(highs.tail(20).max() - lows.tail(20).min())
    range_pct = range_20 / current if current > 0 else 0
    is_range = range_pct < 0.02 and not (strong_bull or strong_bear)
    is_tight_range = range_pct < 0.01

    # DG7: Rolling MA for chop-cross
    sma_fast = closes.rolling(10).mean()
    sma_slow = closes.rolling(20).mean()
    sma_cross_count = 0
    for k in range(1, min(10, len(closes) - 1)):
        if (sma_fast.iloc[-k] > sma_slow.iloc[-k] and sma_fast.iloc[-k-1] <= sma_slow.iloc[-k-1]) or \
           (sma_fast.iloc[-k] < sma_slow.iloc[-k] and sma_fast.iloc[-k-1] >= sma_slow.iloc[-k-1]):
            sma_cross_count += 1
    is_choppy = sma_cross_count >= 3

    evidence = []
    reason_codes = []  # DG7: Always flat strings

    # Spread stress
    if spread_ratio > 2.0:
        evidence.append(f"spread_expansion: {spread_ratio:.1f}x average")
        reason_codes.append("SPREAD_EXPANSION")
        return RegimeResultV2(
            regime=RegimeTypeV2.SPREAD_STRESS, direction="NEUTRAL",
            confidence=0.3, evidence=evidence, reason_codes=reason_codes,
            allowed_setup_types=[], blocked_setup_types=["ALL"],
            risk_modifier=0.0, threshold_modifier=0.10,
            exit_sensitivity_modifier=1.5,
        )

    # DG7: Liquidity — distinguish unknown vs genuinely low
    if not has_volume:
        evidence.append("volume_data_unavailable")
        reason_codes.append("VOLUME_UNKNOWN")
        return RegimeResultV2(
            regime=RegimeTypeV2.UNKNOWN_UNSAFE, direction="UNKNOWN",
            confidence=0.0, evidence=evidence, reason_codes=reason_codes,
            allowed_setup_types=[], blocked_setup_types=["ALL"],
            risk_modifier=0.0, threshold_modifier=0.10,
            exit_sensitivity_modifier=1.0,
        )
    if vol_ratio_val < 0.3:
        evidence.append(f"low_liquidity: volume {vol_ratio_val:.1%} of average")
        reason_codes.append("LOW_LIQUIDITY")
        return RegimeResultV2(
            regime=RegimeTypeV2.LIQUIDITY_STRESS, direction="NEUTRAL",
            confidence=0.3, evidence=evidence, reason_codes=reason_codes,
            allowed_setup_types=[], blocked_setup_types=["ALL"],
            risk_modifier=0.0, threshold_modifier=0.08,
            exit_sensitivity_modifier=1.3,
        )

    # Volatility compression
    if vol_ratio < 0.6:
        evidence.append(f"volatility_compression: ATR {vol_ratio:.1%} of long-term")
        reason_codes.append("VOL_COMPRESSION")
        return RegimeResultV2(
            regime=RegimeTypeV2.VOLATILITY_COMPRESSION, direction="NEUTRAL",
            confidence=0.4, evidence=evidence, reason_codes=reason_codes,
            allowed_setup_types=["FAIR_VALUE_GAP", "BREAKOUT"],
            blocked_setup_types=["PULLBACK", "LIQUIDITY_SWEEP"],
            risk_modifier=0.5, threshold_modifier=0.02,
            exit_sensitivity_modifier=0.8,
        )

    # Breakout expansion
    if vol_ratio > 1.8:
        if strong_bull:
            reason_codes.append("BREAKOUT_EXPANSION")
            reason_codes.append("STRONG_BULL")
            evidence.append(f"breakout_expansion_bull: ATR {vol_ratio:.1%}")
            return RegimeResultV2(
                regime=RegimeTypeV2.BREAKOUT_EXPANSION, direction="BULL",
                confidence=0.7, evidence=evidence, reason_codes=reason_codes,
                allowed_setup_types=["BREAKOUT", "BREAK_OF_STRUCTURE", "CONTINUATION"],
                blocked_setup_types=["PULLBACK"],
                risk_modifier=1.0, threshold_modifier=0.0,
                exit_sensitivity_modifier=1.2,
            )
        elif strong_bear:
            reason_codes.append("BREAKOUT_EXPANSION")
            reason_codes.append("STRONG_BEAR")
            evidence.append(f"breakout_expansion_bear: ATR {vol_ratio:.1%}")
            return RegimeResultV2(
                regime=RegimeTypeV2.BREAKOUT_EXPANSION, direction="BEAR",
                confidence=0.7, evidence=evidence, reason_codes=reason_codes,
                allowed_setup_types=["BREAKOUT", "BREAK_OF_STRUCTURE", "CONTINUATION"],
                blocked_setup_types=["PULLBACK"],
                risk_modifier=1.0, threshold_modifier=0.0,
                exit_sensitivity_modifier=1.2,
            )

    # Transition chop
    if is_choppy and not (strong_bull or strong_bear):
        reason_codes.append("CHOPPY_TRANSITION")
        evidence.append(f"transition_chop: {sma_cross_count} SMA crosses")
        return RegimeResultV2(
            regime=RegimeTypeV2.TRANSITION_CHOP, direction="NEUTRAL",
            confidence=0.2, evidence=evidence, reason_codes=reason_codes,
            allowed_setup_types=["LIQUIDITY_SWEEP"],
            blocked_setup_types=["PULLBACK", "BREAKOUT", "BREAK_OF_STRUCTURE"],
            risk_modifier=0.3, threshold_modifier=0.05,
            exit_sensitivity_modifier=1.4,
        )

    # Strong bull
    if strong_bull:
        reason_codes.append("STRONG_BULL_TREND")
        evidence.append("strong_bull: price > SMA10 > SMA20 > SMA50")
        return RegimeResultV2(
            regime=RegimeTypeV2.STRONG_BULL_TREND, direction="BULL",
            confidence=0.8, evidence=evidence, reason_codes=reason_codes,
            allowed_setup_types=["PULLBACK", "BREAK_OF_STRUCTURE", "CONTINUATION", "BREAKOUT"],
            blocked_setup_types=[],
            risk_modifier=1.0, threshold_modifier=0.0, exit_sensitivity_modifier=1.0,
        )

    # Strong bear
    if strong_bear:
        reason_codes.append("STRONG_BEAR_TREND")
        evidence.append("strong_bear: price < SMA10 < SMA20 < SMA50")
        return RegimeResultV2(
            regime=RegimeTypeV2.STRONG_BEAR_TREND, direction="BEAR",
            confidence=0.8, evidence=evidence, reason_codes=reason_codes,
            allowed_setup_types=["PULLBACK", "BREAK_OF_STRUCTURE", "CONTINUATION", "BREAKOUT"],
            blocked_setup_types=[],
            risk_modifier=1.0, threshold_modifier=0.0, exit_sensitivity_modifier=1.0,
        )

    # Weak bull (not tight range)
    if bull_trend and not is_tight_range:
        reason_codes.append("WEAK_BULL_TREND")
        evidence.append("weak_bull: price > SMA10 > SMA20")
        return RegimeResultV2(
            regime=RegimeTypeV2.WEAK_BULL_TREND, direction="BULL",
            confidence=0.5, evidence=evidence, reason_codes=reason_codes,
            allowed_setup_types=["PULLBACK", "CONTINUATION"],
            blocked_setup_types=["BREAKOUT"],
            risk_modifier=0.7, threshold_modifier=0.02, exit_sensitivity_modifier=1.1,
        )

    # Weak bear (not tight range)
    if bear_trend and not is_tight_range:
        reason_codes.append("WEAK_BEAR_TREND")
        evidence.append("weak_bear: price < SMA10 < SMA20")
        return RegimeResultV2(
            regime=RegimeTypeV2.WEAK_BEAR_TREND, direction="BEAR",
            confidence=0.5, evidence=evidence, reason_codes=reason_codes,
            allowed_setup_types=["PULLBACK", "CONTINUATION"],
            blocked_setup_types=["BREAKOUT"],
            risk_modifier=0.7, threshold_modifier=0.02, exit_sensitivity_modifier=1.1,
        )

    # Stable range
    if is_range or is_tight_range:
        reason_codes.append("STABLE_RANGE")
        evidence.append(f"stable_range: {range_pct:.2%}")
        return RegimeResultV2(
            regime=RegimeTypeV2.STABLE_RANGE, direction="NEUTRAL",
            confidence=0.4, evidence=evidence, reason_codes=reason_codes,
            allowed_setup_types=["LIQUIDITY_SWEEP", "FAIR_VALUE_GAP", "RANGE_EDGE_REJECTION"],
            blocked_setup_types=["PULLBACK", "BREAK_OF_STRUCTURE"],
            risk_modifier=0.5, threshold_modifier=0.03, exit_sensitivity_modifier=1.2,
        )

    # Fallback
    reason_codes.append("UNKNOWN_REGIME")
    evidence.append("no_clear_regime")
    return RegimeResultV2(
        regime=RegimeTypeV2.UNKNOWN_UNSAFE, direction="UNKNOWN",
        confidence=0.0, evidence=evidence, reason_codes=reason_codes,
        allowed_setup_types=[], blocked_setup_types=["ALL"],
        risk_modifier=0.0, threshold_modifier=0.10, exit_sensitivity_modifier=1.0,
    )


__all__ = ["RegimeTypeV2", "RegimeResultV2", "classify_regime_v2"]
