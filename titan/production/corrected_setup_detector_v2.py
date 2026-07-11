"""TITAN XAU AI — Corrected Setup Detector V2 (Sprint v2.8.7-P1.1)
==================================================================
DG8: Complete setup implementation + strengthened detectors.
NEVER sends orders. NEVER creates tokens. NEVER trades.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List
import numpy as np
import pandas as pd


class CorrectedSetupTypeV2(str, Enum):
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
class SetupResultV2:
    setup_type: CorrectedSetupTypeV2
    direction: str
    confidence: float
    reason_codes: List[str]
    evidence: List[str]


def detect_breakout_retest(df: pd.DataFrame, prior_high: float, min_bars: int = 20) -> Optional[SetupResultV2]:
    """Detect breakout retest: price broke above, pulled back to test, then resumed."""
    if len(df) < min_bars + 5:
        return None
    prior = df.iloc[:-1].tail(min_bars)
    # Look for a breakout in the last 5 bars, followed by retest
    for k in range(2, min(6, len(df) - 1)):
        bar = df.iloc[-k]
        if bar["close"] > prior_high:
            # Check if current bar retested near prior_high
            current = df.iloc[-1]
            if abs(current["low"] - prior_high) < current["close"] * 0.002 and current["close"] > prior_high:
                return SetupResultV2(
                    setup_type=CorrectedSetupTypeV2.BREAKOUT_RETEST,
                    direction="LONG", confidence=0.65,
                    reason_codes=["breakout_retest_long"],
                    evidence=[f"broke {prior_high:.2f}, retested, close={current['close']:.2f}"],
                )
    return None


def detect_range_edge_rejection(df: pd.DataFrame, range_high: float, range_low: float) -> Optional[SetupResultV2]:
    """Detect range edge rejection: price touched range edge and rejected."""
    if len(df) < 3:
        return None
    current = df.iloc[-1]
    current_open = float(current["open"])
    current_close = float(current["close"])

    # Rejection at range high (bearish)
    if float(current["high"]) >= range_high * 0.999 and current_close < current_open:
        return SetupResultV2(
            setup_type=CorrectedSetupTypeV2.RANGE_EDGE_REJECTION,
            direction="SHORT", confidence=0.55,
            reason_codes=["range_high_rejection"],
            evidence=[f"high={float(current['high']):.2f} >= range_high={range_high:.2f}, bearish close"],
        )
    # Rejection at range low (bullish)
    if float(current["low"]) <= range_low * 1.001 and current_close > current_open:
        return SetupResultV2(
            setup_type=CorrectedSetupTypeV2.RANGE_EDGE_REJECTION,
            direction="LONG", confidence=0.55,
            reason_codes=["range_low_rejection"],
            evidence=[f"low={float(current['low']):.2f} <= range_low={range_low:.2f}, bullish close"],
        )
    return None


def detect_continuation(df: pd.DataFrame, direction: str, min_bars: int = 10) -> Optional[SetupResultV2]:
    """Detect continuation: trend continues with momentum."""
    if len(df) < min_bars:
        return None
    closes = df["close"].tail(min_bars)
    sma = closes.rolling(5).mean().iloc[-1]
    current = float(closes.iloc[-1])
    prev = float(closes.iloc[-2])

    if direction == "BULL":
        if current > sma and current > prev:
            return SetupResultV2(
                setup_type=CorrectedSetupTypeV2.CONTINUATION,
                direction="LONG", confidence=0.60,
                reason_codes=["bullish_continuation"],
                evidence=[f"close={current:.2f} > SMA5={sma:.2f} > prev={prev:.2f}"],
            )
    elif direction == "BEAR":
        if current < sma and current < prev:
            return SetupResultV2(
                setup_type=CorrectedSetupTypeV2.CONTINUATION,
                direction="SHORT", confidence=0.60,
                reason_codes=["bearish_continuation"],
                evidence=[f"close={current:.2f} < SMA5={sma:.2f} < prev={prev:.2f}"],
            )
    return None


def scan_setups_v2(df: pd.DataFrame, regime_direction: str, atr_value: float = 0) -> List[SetupResultV2]:
    """Scan for all valid setups. Returns list, prevents conflicting directions."""
    from titan.production.corrected_setup_detector import (
        detect_pullback, detect_breakout, detect_break_of_structure,
        detect_liquidity_sweep, detect_fair_value_gap,
    )
    results = []

    if regime_direction in ("BULL", "BEAR"):
        pb = detect_pullback(df, regime_direction)
        if pb:
            results.append(SetupResultV2(
                setup_type=CorrectedSetupTypeV2.PULLBACK,
                direction=pb.direction, confidence=pb.confidence,
                reason_codes=pb.reason_codes, evidence=pb.evidence,
            ))

    bos = detect_break_of_structure(df)
    if bos:
        results.append(SetupResultV2(
            setup_type=CorrectedSetupTypeV2.BULLISH_BREAK_OF_STRUCTURE if bos.direction == "LONG"
                       else CorrectedSetupTypeV2.BEARISH_BREAK_OF_STRUCTURE,
            direction=bos.direction, confidence=bos.confidence,
            reason_codes=bos.reason_codes, evidence=bos.evidence,
        ))

    bo = detect_breakout(df, atr_value=atr_value)
    if bo:
        results.append(SetupResultV2(
            setup_type=CorrectedSetupTypeV2.BREAKOUT if "breakout" in bo.reason_codes[0]
                       else CorrectedSetupTypeV2.FAILED_BREAKOUT,
            direction=bo.direction, confidence=bo.confidence,
            reason_codes=bo.reason_codes, evidence=bo.evidence,
        ))

    ls = detect_liquidity_sweep(df)
    if ls:
        results.append(SetupResultV2(
            setup_type=CorrectedSetupTypeV2.LIQUIDITY_SWEEP,
            direction=ls.direction, confidence=ls.confidence,
            reason_codes=ls.reason_codes, evidence=ls.evidence,
        ))

    fvg = detect_fair_value_gap(df)
    if fvg:
        results.append(SetupResultV2(
            setup_type=CorrectedSetupTypeV2.FAIR_VALUE_GAP,
            direction=fvg.direction, confidence=fvg.confidence,
            reason_codes=fvg.reason_codes, evidence=fvg.evidence,
        ))

    # DG8: Prevent conflicting simultaneous LONG and SHORT
    long_results = [r for r in results if r.direction == "LONG"]
    short_results = [r for r in results if r.direction == "SHORT"]
    if long_results and short_results:
        # Keep only the highest-confidence direction
        max_long = max(long_results, key=lambda r: r.confidence)
        max_short = max(short_results, key=lambda r: r.confidence)
        if max_long.confidence >= max_short.confidence:
            results = [r for r in results if r.direction != "SHORT"]
        else:
            results = [r for r in results if r.direction != "LONG"]

    # Add new setups
    cont = detect_continuation(df, regime_direction)
    if cont:
        results.append(cont)

    # Detect breakout retest (must be called explicitly)
    prior_high = float(df.iloc[:-1].tail(20)["high"].max()) if len(df) > 20 else float(df["high"].max())
    br = detect_breakout_retest(df, prior_high=prior_high)
    if br:
        results.append(br)

    # Detect range edge rejection (must be called explicitly)
    range_high = float(df.iloc[:-1].tail(20)["high"].max()) if len(df) > 20 else float(df["high"].max())
    range_low = float(df.iloc[:-1].tail(20)["low"].min()) if len(df) > 20 else float(df["low"].min())
    rer = detect_range_edge_rejection(df, range_high=range_high, range_low=range_low)
    if rer:
        results.append(rer)

    return results if results else [SetupResultV2(
        setup_type=CorrectedSetupTypeV2.NONE, direction="NEUTRAL",
        confidence=0.0, reason_codes=["no_setup_detected"], evidence=[],
    )]


__all__ = [
    "CorrectedSetupTypeV2", "SetupResultV2",
    "detect_breakout_retest", "detect_range_edge_rejection",
    "detect_continuation", "scan_setups_v2",
]
