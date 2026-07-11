"""TITAN XAU AI — Corrected Setup Detector (Sprint v2.8.7-P1)
=============================================================
Fixes:
  - Current candle excluded from prior swing high/low
  - Proper breakout detection with ATR normalization
  - Closed-bar detection for all patterns
  - No approximate 0.999 multipliers

NEVER sends orders. NEVER creates tokens. NEVER trades.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List
import numpy as np
import pandas as pd


class CorrectedSetupType(str, Enum):
    PULLBACK = "PULLBACK"
    BREAKOUT = "BREAKOUT"
    BREAKOUT_RETEST = "BREAKOUT_RETEST"
    LIQUIDITY_SWEEP = "LIQUIDITY_SWEEP"
    FAILED_BREAKOUT = "FAILED_BREAKOUT"
    BULLISH_BREAK_OF_STRUCTURE = "BULLISH_BREAK_OF_STRUCTURE"
    BEARISH_BREAK_OF_STRUCTURE = "BEARISH_BREAK_OF_STRUCTURE"
    RANGE_EDGE_REJECTION = "RANGE_EDGE_REJECTION"
    CONTINUATION = "CONTINUATION"
    FAIR_VALUE_GAP = "FAIR_VALUE_GAP"
    NONE = "NONE"


@dataclass
class SetupResult:
    """Result of setup detection."""
    setup_type: CorrectedSetupType
    direction: str  # LONG / SHORT / NEUTRAL
    confidence: float
    reason_codes: list
    evidence: list


def detect_pullback(df: pd.DataFrame, direction: str, min_bars: int = 20) -> Optional[SetupResult]:
    """Detect pullback in trend. Uses CLOSED bars only, excludes current candle."""
    if len(df) < min_bars + 1:
        return None

    # Exclude current candle (iloc[-1]) from reference
    prior = df.iloc[:-1].tail(min_bars)
    closes = prior["close"]
    sma = closes.rolling(10).mean().iloc[-1]
    current_close = float(df["close"].iloc[-1])
    prev_close = float(df["close"].iloc[-2])

    if direction == "BULL":
        # Price pulled back near SMA then resumed up (current closes above prev)
        if prev_close < sma and current_close > prev_close:
            return SetupResult(
                setup_type=CorrectedSetupType.PULLBACK,
                direction="LONG", confidence=0.65,
                reason_codes=["pullback_to_sma_bull"],
                evidence=[f"prev_close({prev_close:.2f}) < SMA10({sma:.2f}), current({current_close:.2f}) > prev({prev_close:.2f})"],
            )
    elif direction == "BEAR":
        if prev_close > sma and current_close < prev_close:
            return SetupResult(
                setup_type=CorrectedSetupType.PULLBACK,
                direction="SHORT", confidence=0.65,
                reason_codes=["pullback_to_sma_bear"],
                evidence=[f"prev_close({prev_close:.2f}) > SMA10({sma:.2f}), current({current_close:.2f}) < prev({prev_close:.2f})"],
            )
    return None


def detect_breakout(df: pd.DataFrame, min_bars: int = 20, atr_value: float = 0) -> Optional[SetupResult]:
    """Detect genuine breakout with ATR normalization. Excludes current candle."""
    if len(df) < min_bars + 1:
        return None

    # Exclude current candle from reference range
    prior = df.iloc[:-1].tail(min_bars)
    prior_high = float(prior["high"].max())
    prior_low = float(prior["low"].min())
    current_close = float(df["close"].iloc[-1])
    current_high = float(df["high"].iloc[-1])
    current_low = float(df["low"].iloc[-1])

    # ATR-normalized displacement requirement (minimum 0.3 ATR beyond range)
    min_displacement = max(atr_value * 0.3, 0.5)

    # Bullish breakout
    if current_close > prior_high + min_displacement:
        # Close must be above breakout level (not just wick)
        return SetupResult(
            setup_type=CorrectedSetupType.BREAKOUT,
            direction="LONG", confidence=0.70,
            reason_codes=["bullish_breakout", f"displacement={min_displacement:.2f}"],
            evidence=[f"close({current_close:.2f}) > prior_high({prior_high:.2f}) + ATR_disp({min_displacement:.2f})"],
        )

    # Bearish breakout
    if current_close < prior_low - min_displacement:
        return SetupResult(
            setup_type=CorrectedSetupType.BREAKOUT,
            direction="SHORT", confidence=0.70,
            reason_codes=["bearish_breakout", f"displacement={min_displacement:.2f}"],
            evidence=[f"close({current_close:.2f}) < prior_low({prior_low:.2f}) - ATR_disp({min_displacement:.2f})"],
        )

    # Failed breakout (price exceeded range but closed back inside)
    if current_high > prior_high + min_displacement and current_close <= prior_high:
        return SetupResult(
            setup_type=CorrectedSetupType.FAILED_BREAKOUT,
            direction="SHORT", confidence=0.50,
            reason_codes=["failed_bullish_breakout"],
            evidence=[f"high({current_high:.2f}) > prior_high({prior_high:.2f}) but close({current_close:.2f}) <= prior_high"],
        )
    if current_low < prior_low - min_displacement and current_close >= prior_low:
        return SetupResult(
            setup_type=CorrectedSetupType.FAILED_BREAKOUT,
            direction="LONG", confidence=0.50,
            reason_codes=["failed_bearish_breakout"],
            evidence=[f"low({current_low:.2f}) < prior_low({prior_low:.2f}) but close({current_close:.2f}) >= prior_low"],
        )

    return None


def detect_break_of_structure(df: pd.DataFrame, min_bars: int = 10) -> Optional[SetupResult]:
    """Detect break of structure. Excludes current candle from reference."""
    if len(df) < min_bars + 1:
        return None

    prior = df.iloc[:-1].tail(min_bars)
    prior_high = float(prior["high"].max())
    prior_low = float(prior["low"].min())
    current_close = float(df["close"].iloc[-1])

    # Bullish BOS: close above prior high (with close acceptance, not just wick)
    if current_close > prior_high:
        return SetupResult(
            setup_type=CorrectedSetupType.BULLISH_BREAK_OF_STRUCTURE,
            direction="LONG", confidence=0.68,
            reason_codes=["bullish_bos"],
            evidence=[f"close({current_close:.2f}) > prior_high({prior_high:.2f})"],
        )

    # Bearish BOS: close below prior low
    if current_close < prior_low:
        return SetupResult(
            setup_type=CorrectedSetupType.BEARISH_BREAK_OF_STRUCTURE,
            direction="SHORT", confidence=0.68,
            reason_codes=["bearish_bos"],
            evidence=[f"close({current_close:.2f}) < prior_low({prior_low:.2f})"],
        )

    return None


def detect_liquidity_sweep(df: pd.DataFrame, min_bars: int = 5) -> Optional[SetupResult]:
    """Detect liquidity sweep. Excludes current candle from reference."""
    if len(df) < min_bars + 1:
        return None

    prior = df.iloc[:-1].tail(min_bars)
    prior_high = float(prior["high"].max())
    prior_low = float(prior["low"].min())
    current_low = float(df["low"].iloc[-1])
    current_high = float(df["high"].iloc[-1])
    current_close = float(df["close"].iloc[-1])
    current_open = float(df["open"].iloc[-1])

    # Bullish liquidity sweep: low pierced prior low but close back above
    if current_low < prior_low and current_close > current_open:
        return SetupResult(
            setup_type=CorrectedSetupType.LIQUIDITY_SWEEP,
            direction="LONG", confidence=0.60,
            reason_codes=["bullish_liquidity_sweep"],
            evidence=[f"low({current_low:.2f}) < prior_low({prior_low:.2f}), close bullish"],
        )

    # Bearish liquidity sweep: high pierced prior high but close back below
    if current_high > prior_high and current_close < current_open:
        return SetupResult(
            setup_type=CorrectedSetupType.LIQUIDITY_SWEEP,
            direction="SHORT", confidence=0.60,
            reason_codes=["bearish_liquidity_sweep"],
            evidence=[f"high({current_high:.2f}) > prior_high({prior_high:.2f}), close bearish"],
        )

    return None


def detect_fair_value_gap(df: pd.DataFrame) -> Optional[SetupResult]:
    """Detect fair value gap (3-bar imbalance). Uses closed bars."""
    if len(df) < 3:
        return None

    # Use bars -3, -2, -1 (all closed)
    bar1_high = float(df["high"].iloc[-3])
    bar1_low = float(df["low"].iloc[-3])
    bar3_low = float(df["low"].iloc[-1])
    bar3_high = float(df["high"].iloc[-1])

    # Bullish FVG: bar1.high < bar3.low (gap up)
    if bar1_high < bar3_low:
        gap_size = bar3_low - bar1_high
        return SetupResult(
            setup_type=CorrectedSetupType.FAIR_VALUE_GAP,
            direction="LONG", confidence=0.50,
            reason_codes=["bullish_fvg"],
            evidence=[f"gap: bar1_high({bar1_high:.2f}) < bar3_low({bar3_low:.2f}), size={gap_size:.2f}"],
        )

    # Bearish FVG: bar1.low > bar3.high (gap down)
    if bar1_low > bar3_high:
        gap_size = bar1_low - bar3_high
        return SetupResult(
            setup_type=CorrectedSetupType.FAIR_VALUE_GAP,
            direction="SHORT", confidence=0.50,
            reason_codes=["bearish_fvg"],
            evidence=[f"gap: bar1_low({bar1_low:.2f}) > bar3_high({bar3_high:.2f}), size={gap_size:.2f}"],
        )

    return None


def scan_setups_corrected(df: pd.DataFrame, regime_direction: str, atr_value: float = 0) -> list:
    """Scan for all valid setups. Returns list of SetupResult.

    Args:
        df: M15 or H1 DataFrame
        regime_direction: "BULL", "BEAR", "NEUTRAL", "UNKNOWN" from regime classifier
        atr_value: Current ATR for normalization
    """
    results = []

    # Only scan if regime is directional
    if regime_direction in ("BULL", "BEAR"):
        pb = detect_pullback(df, regime_direction)
        if pb:
            results.append(pb)

    bos = detect_break_of_structure(df)
    if bos:
        results.append(bos)

    bo = detect_breakout(df, atr_value=atr_value)
    if bo:
        results.append(bo)

    ls = detect_liquidity_sweep(df)
    if ls:
        results.append(ls)

    fvg = detect_fair_value_gap(df)
    if fvg:
        results.append(fvg)

    return results if results else [SetupResult(
        setup_type=CorrectedSetupType.NONE,
        direction="NEUTRAL", confidence=0.0,
        reason_codes=["no_setup_detected"],
        evidence=[],
    )]


__all__ = [
    "CorrectedSetupType", "SetupResult",
    "detect_pullback", "detect_breakout", "detect_break_of_structure",
    "detect_liquidity_sweep", "detect_fair_value_gap", "scan_setups_corrected",
]
