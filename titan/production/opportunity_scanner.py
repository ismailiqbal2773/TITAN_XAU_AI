"""TITAN XAU AI — Opportunity Scanner (Sprint v2.8.7-P)
=========================================================
Multi-timeframe opportunity scanner.

H1 = regime filter (trend/range/volatility)
M15 = setup scanner (pullback/breakout/liquidity sweep/FVG/BOS/order block)
M5 = entry timing (micro pullback/candle confirmation/liquidity grab/spread/volatility)

Signal classes:
  A_PLUS — highest quality, full risk
  A      — high quality, full risk
  B      — moderate quality, reduced risk
  C_SHADOW_ONLY — observation only, never trades

NEVER sends orders. NEVER creates tokens. NEVER trades.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


class SignalClass(str, Enum):
    A_PLUS = "A_PLUS"
    A = "A"
    B = "B"
    C_SHADOW_ONLY = "C_SHADOW_ONLY"


class RegimeType(str, Enum):
    TREND = "TREND"
    RANGE = "RANGE"
    VOLATILITY_EXPANSION = "VOLATILITY_EXPANSION"
    SPREAD_EXPANSION = "SPREAD_EXPANSION"
    NORMAL = "NORMAL"


class SetupType(str, Enum):
    PULLBACK = "PULLBACK"
    BREAKOUT = "BREAKOUT"
    LIQUIDITY_SWEEP = "LIQUIDITY_SWEEP"
    FAIR_VALUE_GAP = "FAIR_VALUE_GAP"
    BREAK_OF_STRUCTURE = "BREAK_OF_STRUCTURE"
    ORDER_BLOCK_PROXIMITY = "ORDER_BLOCK_PROXIMITY"
    NONE = "NONE"


@dataclass
class SignalCandidate:
    """A signal candidate from the opportunity scanner."""
    timestamp: str
    direction: str  # LONG / SHORT
    setup_type: str
    regime: str
    confidence: float
    setup_score: float
    alpha_score: float
    meta_score: float
    entry_reference: float
    sl_reference: float
    tp_reference: float
    rr: float
    expected_frequency_class: str  # A_PLUS / A / B / C_SHADOW_ONLY
    reason_codes: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


def classify_regime(h1_df: pd.DataFrame) -> RegimeType:
    """Classify H1 regime from recent bars."""
    if len(h1_df) < 20:
        return RegimeType.NORMAL

    closes = h1_df["close"].tail(20)
    sma = closes.rolling(10).mean().iloc[-1]
    current = closes.iloc[-1]
    atr = (h1_df["high"] - h1_df["low"]).tail(14).mean()

    # Volatility expansion
    if len(h1_df) >= 60:
        long_atr = (h1_df["high"] - h1_df["low"]).tail(60).mean()
        if atr > long_atr * 1.8:
            return RegimeType.VOLATILITY_EXPANSION

    # Spread expansion
    if "spread" in h1_df.columns:
        recent_spread = h1_df["spread"].tail(10).mean()
        long_spread = h1_df["spread"].tail(60).mean() if len(h1_df) >= 60 else recent_spread
        if recent_spread > long_spread * 2:
            return RegimeType.SPREAD_EXPANSION

    # Trend vs range
    if current > sma * 1.002:
        return RegimeType.TREND
    elif current < sma * 0.998:
        return RegimeType.TREND
    else:
        return RegimeType.RANGE


def scan_m15_setup(m15_df: pd.DataFrame, regime: RegimeType) -> tuple[SetupType, float, str]:
    """Scan M15 for setup patterns. Returns (setup_type, setup_score, direction)."""
    if len(m15_df) < 20:
        return SetupType.NONE, 0.0, "NEUTRAL"

    closes = m15_df["close"]
    highs = m15_df["high"]
    lows = m15_df["low"]
    sma = closes.rolling(10).mean().iloc[-1]
    current = closes.iloc[-1]

    # Break of structure
    if len(closes) >= 10:
        recent_high = highs.tail(10).max()
        recent_low = lows.tail(10).min()
        if current > recent_high * 0.999:
            return SetupType.BREAK_OF_STRUCTURE, 0.7, "LONG"
        if current < recent_low * 1.001:
            return SetupType.BREAK_OF_STRUCTURE, 0.7, "SHORT"

    # Pullback in trend
    if regime == RegimeType.TREND:
        if current > sma and closes.iloc[-2] < sma:
            return SetupType.PULLBACK, 0.6, "LONG"
        if current < sma and closes.iloc[-2] > sma:
            return SetupType.PULLBACK, 0.6, "SHORT"

    # Breakout
    if len(closes) >= 20:
        range_high = highs.tail(20).max()
        range_low = lows.tail(20).min()
        if current > range_high * 0.999:
            return SetupType.BREAKOUT, 0.65, "LONG"
        if current < range_low * 1.001:
            return SetupType.BREAKOUT, 0.65, "SHORT"

    # Fair value gap
    if len(closes) >= 3:
        gap = highs.iloc[-1] - lows.iloc[-3]
        body = abs(closes.iloc[-1] - m15_df["open"].iloc[-1])
        if gap > body * 2 and gap > 0:
            return SetupType.FAIR_VALUE_GAP, 0.5, "LONG" if closes.iloc[-1] > closes.iloc[-3] else "SHORT"

    # Liquidity sweep
    if len(closes) >= 5:
        if lows.iloc[-1] < lows.iloc[-5:-1].min() and closes.iloc[-1] > m15_df["open"].iloc[-1]:
            return SetupType.LIQUIDITY_SWEEP, 0.55, "LONG"
        if highs.iloc[-1] > highs.iloc[-5:-1].max() and closes.iloc[-1] < m15_df["open"].iloc[-1]:
            return SetupType.LIQUIDITY_SWEEP, 0.55, "SHORT"

    return SetupType.NONE, 0.0, "NEUTRAL"


def check_m5_entry_timing(m5_df: pd.DataFrame, direction: str, spread: float) -> tuple[bool, float, list]:
    """Check M5 for entry timing confirmation. Returns (pass, timing_score, reason_codes)."""
    if len(m5_df) < 5:
        return False, 0.0, ["insufficient_m5_data"]

    reasons = []
    closes = m5_df["close"]
    opens = m5_df["open"]
    current_close = closes.iloc[-1]
    prev_close = closes.iloc[-2]

    # Spread acceptable
    if spread > 0.5:
        reasons.append("spread_too_wide")
        return False, 0.0, reasons

    # Candle confirmation
    if direction == "LONG":
        if current_close > prev_close:
            reasons.append("candle_confirmation_long")
            timing_score = 0.7
        else:
            return False, 0.0, ["no_candle_confirmation"]
    elif direction == "SHORT":
        if current_close < prev_close:
            reasons.append("candle_confirmation_short")
            timing_score = 0.7
        else:
            return False, 0.0, ["no_candle_confirmation"]
    else:
        return False, 0.0, ["neutral_direction"]

    # Micro pullback check
    if len(closes) >= 3:
        if direction == "LONG" and closes.iloc[-3] > closes.iloc[-2]:
            reasons.append("micro_pullback_long")
            timing_score += 0.15
        if direction == "SHORT" and closes.iloc[-3] < closes.iloc[-2]:
            reasons.append("micro_pullback_short")
            timing_score += 0.15

    # Volatility acceptable
    recent_range = (m5_df["high"].tail(5) - m5_df["low"].tail(5)).mean()
    if recent_range > 0:
        reasons.append("volatility_acceptable")
        timing_score += 0.1

    return True, min(timing_score, 1.0), reasons


def classify_signal(setup_type: SetupType, setup_score: float,
                    alpha_score: float, meta_score: float,
                    timing_score: float, regime: RegimeType) -> SignalClass:
    """Classify signal into A_PLUS / A / B / C_SHADOW_ONLY."""
    combined = (setup_score * 0.3 + alpha_score * 0.3 + meta_score * 0.2 + timing_score * 0.2)

    if setup_type == SetupType.NONE:
        return SignalClass.C_SHADOW_ONLY

    if combined >= 0.75 and regime == RegimeType.TREND:
        return SignalClass.A_PLUS
    elif combined >= 0.65:
        return SignalClass.A
    elif combined >= 0.50:
        return SignalClass.B
    else:
        return SignalClass.C_SHADOW_ONLY


def scan_opportunities(h1_df: pd.DataFrame, m15_df: pd.DataFrame, m5_df: pd.DataFrame,
                        alpha_proba: float, meta_proba: float,
                        atr_value: float, spread: float,
                        sl_atr_multiplier: float = 2.0, rr_target: float = 3.0) -> list:
    """Scan for trading opportunities across H1/M15/M5.

    Returns list of SignalCandidate objects.
    """
    candidates = []

    # H1 regime
    regime = classify_regime(h1_df)

    # Skip if volatility or spread expansion
    if regime in (RegimeType.VOLATILITY_EXPANSION, RegimeType.SPREAD_EXPANSION):
        return candidates

    # M15 setup
    setup_type, setup_score, direction = scan_m15_setup(m15_df, regime)
    if setup_type == SetupType.NONE:
        return candidates

    # M5 entry timing
    timing_pass, timing_score, timing_reasons = check_m5_entry_timing(m5_df, direction, spread)
    if not timing_pass:
        return candidates

    # Classify signal
    signal_class = classify_signal(setup_type, setup_score, alpha_proba, meta_proba,
                                     timing_score, regime)

    # Skip C_SHADOW_ONLY for actual signals (still logged but not traded)
    if signal_class == SignalClass.C_SHADOW_ONLY:
        candidates.append(SignalCandidate(
            timestamp=str(h1_df.index[-1]),
            direction=direction, setup_type=setup_type.value,
            regime=regime.value, confidence=round(setup_score * alpha_proba, 4),
            setup_score=round(setup_score, 4), alpha_score=round(alpha_proba, 4),
            meta_score=round(meta_proba, 4),
            entry_reference=round(float(h1_df["close"].iloc[-1]), 4),
            sl_reference=0, tp_reference=0, rr=0,
            expected_frequency_class=signal_class.value,
            reason_codes=timing_reasons + ["c_shadow_only_observation"],
        ))
        return candidates

    # Calculate SL/TP
    entry_price = float(h1_df["close"].iloc[-1])
    sl_distance = atr_value * sl_atr_multiplier
    tp_distance = sl_distance * rr_target

    if direction == "LONG":
        sl_price = entry_price - sl_distance
        tp_price = entry_price + tp_distance
    else:
        sl_price = entry_price + sl_distance
        tp_price = entry_price - tp_distance

    candidates.append(SignalCandidate(
        timestamp=str(h1_df.index[-1]),
        direction=direction, setup_type=setup_type.value,
        regime=regime.value, confidence=round(setup_score * alpha_proba, 4),
        setup_score=round(setup_score, 4), alpha_score=round(alpha_proba, 4),
        meta_score=round(meta_proba, 4),
        entry_reference=round(entry_price, 4),
        sl_reference=round(sl_price, 4), tp_reference=round(tp_price, 4),
        rr=rr_target, expected_frequency_class=signal_class.value,
        reason_codes=timing_reasons,
    ))

    return candidates


__all__ = [
    "SignalClass", "RegimeType", "SetupType", "SignalCandidate",
    "classify_regime", "scan_m15_setup", "check_m5_entry_timing",
    "classify_signal", "scan_opportunities",
]
