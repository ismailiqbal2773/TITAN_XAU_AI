"""TITAN XAU AI — Corrected Setup Detector V2 (FINAL Sprint v2.8.7-P2.0)
=========================================================================

Finalized setup scanner with:
  1. Detection of EVERY candidate setup type
  2. Regime allowed/blocked setup type enforcement
  3. ATR/tick-normalized score normalization (no raw 0.999/1.001 multipliers)
  4. Conflict resolution AFTER all candidates collected
  5. Equal-quality opposite-direction → NO_TRADE_CONFLICT
  6. Returns: selected_setup, alternatives, rejection_reasons, ranking_evidence

Strengthened detectors:
  - pullback with structure + reclaim
  - sweep with penetration + reclaim
  - FVG with normalized minimum gap
  - retest with historical breakout + retest + resumption

NEVER sends orders. NEVER creates tokens. NEVER trades.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Dict
import math
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


@dataclass
class ScanResultV2:
    """Governed scan result with selected setup, alternatives, rejections, evidence."""
    selected_setup: Optional[SetupResultV2]
    alternatives: List[SetupResultV2]
    rejection_reasons: List[str]
    ranking_evidence: List[str]
    all_candidates: List[SetupResultV2]
    decision: str   # "SELECTED" | "NO_TRADE_CONFLICT" | "NO_CANDIDATES" | "REGIME_BLOCKED"


# Regime → allowed setup types mapping
# EVERY RegimeTypeV2 value has an EXACT policy (Phase 5).
# Empty allowed set means NO setups allowed (not all setups).
REGIME_ALLOWED_SETUPS: Dict[str, set] = {
    "STRONG_BULL_TREND": {"PULLBACK", "BREAKOUT", "BREAKOUT_RETEST", "BULLISH_BREAK_OF_STRUCTURE",
                          "LIQUIDITY_SWEEP", "CONTINUATION", "FAIR_VALUE_GAP"},
    "WEAK_BULL_TREND": {"PULLBACK", "BREAKOUT_RETEST", "BULLISH_BREAK_OF_STRUCTURE",
                         "CONTINUATION", "FAIR_VALUE_GAP"},
    "STRONG_BEAR_TREND": {"PULLBACK", "BREAKOUT", "BREAKOUT_RETEST", "BEARISH_BREAK_OF_STRUCTURE",
                          "LIQUIDITY_SWEEP", "CONTINUATION", "FAIR_VALUE_GAP"},
    "WEAK_BEAR_TREND": {"PULLBACK", "BREAKOUT_RETEST", "BEARISH_BREAK_OF_STRUCTURE",
                         "CONTINUATION", "FAIR_VALUE_GAP"},
    "STABLE_RANGE": {"RANGE_EDGE_REJECTION", "FAILED_BREAKOUT", "FAIR_VALUE_GAP"},
    "VOLATILITY_COMPRESSION": set(),  # unsafe — no setups
    "BREAKOUT_EXPANSION": {"BREAKOUT", "BREAKOUT_RETEST", "FAIR_VALUE_GAP"},
    "TRANSITION_CHOP": set(),  # unsafe — no setups
    "SPREAD_STRESS": set(),  # unsafe — no setups
    "LIQUIDITY_STRESS": set(),  # unsafe — no setups
    "UNKNOWN_UNSAFE": set(),  # unsafe — no setups
}

REGIME_BLOCKED_SETUPS: Dict[str, set] = {
    "STRONG_BULL_TREND": {"RANGE_EDGE_REJECTION", "BEARISH_BREAK_OF_STRUCTURE", "FAILED_BREAKOUT"},
    "WEAK_BULL_TREND": {"RANGE_EDGE_REJECTION", "BEARISH_BREAK_OF_STRUCTURE", "FAILED_BREAKOUT"},
    "STRONG_BEAR_TREND": {"RANGE_EDGE_REJECTION", "BULLISH_BREAK_OF_STRUCTURE", "FAILED_BREAKOUT"},
    "WEAK_BEAR_TREND": {"RANGE_EDGE_REJECTION", "BULLISH_BREAK_OF_STRUCTURE", "FAILED_BREAKOUT"},
    "STABLE_RANGE": {"BULLISH_BREAK_OF_STRUCTURE", "BEARISH_BREAK_OF_STRUCTURE", "CONTINUATION"},
    "VOLATILITY_COMPRESSION": {"PULLBACK", "BREAKOUT", "BREAKOUT_RETEST",
                                 "BULLISH_BREAK_OF_STRUCTURE", "BEARISH_BREAK_OF_STRUCTURE",
                                 "LIQUIDITY_SWEEP", "RANGE_EDGE_REJECTION", "CONTINUATION",
                                 "FAIR_VALUE_GAP", "FAILED_BREAKOUT"},
    "BREAKOUT_EXPANSION": {"RANGE_EDGE_REJECTION", "PULLBACK", "BULLISH_BREAK_OF_STRUCTURE",
                            "BEARISH_BREAK_OF_STRUCTURE", "CONTINUATION"},
    "TRANSITION_CHOP": {"PULLBACK", "BREAKOUT", "BREAKOUT_RETEST",
                          "BULLISH_BREAK_OF_STRUCTURE", "BEARISH_BREAK_OF_STRUCTURE",
                          "LIQUIDITY_SWEEP", "RANGE_EDGE_REJECTION", "CONTINUATION",
                          "FAIR_VALUE_GAP", "FAILED_BREAKOUT"},
    "SPREAD_STRESS": {"PULLBACK", "BREAKOUT", "BREAKOUT_RETEST",
                       "BULLISH_BREAK_OF_STRUCTURE", "BEARISH_BREAK_OF_STRUCTURE",
                       "LIQUIDITY_SWEEP", "RANGE_EDGE_REJECTION", "CONTINUATION",
                       "FAIR_VALUE_GAP", "FAILED_BREAKOUT"},
    "LIQUIDITY_STRESS": {"PULLBACK", "BREAKOUT", "BREAKOUT_RETEST",
                          "BULLISH_BREAK_OF_STRUCTURE", "BEARISH_BREAK_OF_STRUCTURE",
                          "LIQUIDITY_SWEEP", "RANGE_EDGE_REJECTION", "CONTINUATION",
                          "FAIR_VALUE_GAP", "FAILED_BREAKOUT"},
    "UNKNOWN_UNSAFE": {"PULLBACK", "BREAKOUT", "BREAKOUT_RETEST",
                        "BULLISH_BREAK_OF_STRUCTURE", "BEARISH_BREAK_OF_STRUCTURE",
                        "LIQUIDITY_SWEEP", "RANGE_EDGE_REJECTION", "CONTINUATION",
                        "FAIR_VALUE_GAP", "FAILED_BREAKOUT"},
}

# Risk modifier per regime (Phase 5 — every regime has an exact tested value)
REGIME_RISK_MODIFIERS: Dict[str, float] = {
    "STRONG_BULL_TREND": 1.0,
    "WEAK_BULL_TREND": 0.85,
    "STRONG_BEAR_TREND": 1.0,
    "WEAK_BEAR_TREND": 0.85,
    "STABLE_RANGE": 0.70,
    "VOLATILITY_COMPRESSION": 0.0,   # blocked
    "BREAKOUT_EXPANSION": 0.90,
    "TRANSITION_CHOP": 0.0,           # blocked
    "SPREAD_STRESS": 0.0,             # blocked
    "LIQUIDITY_STRESS": 0.0,          # blocked
    "UNKNOWN_UNSAFE": 0.0,            # blocked
}

# Threshold modifier per regime (added to alpha_threshold)
REGIME_THRESHOLD_MODIFIERS: Dict[str, float] = {
    "STRONG_BULL_TREND": 0.0,
    "WEAK_BULL_TREND": 0.02,
    "STRONG_BEAR_TREND": 0.0,
    "WEAK_BEAR_TREND": 0.02,
    "STABLE_RANGE": 0.05,
    "VOLATILITY_COMPRESSION": 0.10,
    "BREAKOUT_EXPANSION": 0.0,
    "TRANSITION_CHOP": 0.10,
    "SPREAD_STRESS": 0.10,
    "LIQUIDITY_STRESS": 0.10,
    "UNKNOWN_UNSAFE": 0.20,
}

# Regimes that are unsafe — selected_setup must be None
UNSAFE_REGIMES: set = {
    "VOLATILITY_COMPRESSION", "TRANSITION_CHOP", "SPREAD_STRESS",
    "LIQUIDITY_STRESS", "UNKNOWN_UNSAFE",
}


def _atr_tolerance(atr_value: float, fraction: float = 0.10) -> float:
    """ATR-normalized tolerance — replaces raw 0.999/1.001 multipliers."""
    return max(atr_value * fraction, 0.01)


def detect_pullback_strengthened(df: pd.DataFrame, regime_direction: str, atr_value: float = 0.0) -> Optional[SetupResultV2]:
    """Pullback with structure + reclaim. Requires:
       - trend direction established
       - pullback to recent structure (SMA or swing)
       - reclaim in current bar (close > pullback level for LONG)
    """
    if len(df) < 25 or atr_value <= 0:
        return None
    closes = df["close"].values
    highs = df["high"].values
    lows = df["low"].values
    sma20 = pd.Series(closes).rolling(20).mean().iloc[-1]
    if not np.isfinite(sma20):
        return None
    tol = _atr_tolerance(atr_value, 0.10)
    current_close = float(closes[-1])
    prev_close = float(closes[-2])

    if regime_direction == "BULL":
        # Stronger trend: closes mostly above sma20
        recent_above = np.sum(closes[-20:] > sma20)
        if recent_above < 12:
            return None
        # Pullback: prev_close was within tolerance of sma20
        if abs(prev_close - sma20) > tol * 2:
            return None
        # Reclaim: current_close > sma20 + tol/2
        if current_close <= sma20 + tol * 0.5:
            return None
        return SetupResultV2(
            setup_type=CorrectedSetupTypeV2.PULLBACK,
            direction="LONG", confidence=0.70,
            reason_codes=["pullback_structure_reclaim_long"],
            evidence=[f"close={current_close:.2f} > sma20={sma20:.2f}+tol, above_count={recent_above}/20"],
        )
    if regime_direction == "BEAR":
        recent_below = np.sum(closes[-20:] < sma20)
        if recent_below < 12:
            return None
        if abs(prev_close - sma20) > tol * 2:
            return None
        if current_close >= sma20 - tol * 0.5:
            return None
        return SetupResultV2(
            setup_type=CorrectedSetupTypeV2.PULLBACK,
            direction="SHORT", confidence=0.70,
            reason_codes=["pullback_structure_reclaim_short"],
            evidence=[f"close={current_close:.2f} < sma20={sma20:.2f}-tol, below_count={recent_below}/20"],
        )
    return None


def detect_breakout_strengthened(df: pd.DataFrame, atr_value: float = 0.0) -> Optional[SetupResultV2]:
    """Breakout: close exceeds prior 20-bar high/low by ATR-normalized tolerance."""
    if len(df) < 25 or atr_value <= 0:
        return None
    closes = df["close"].values
    highs = df["high"].values
    lows = df["low"].values
    prior_high = float(np.max(highs[-21:-1]))
    prior_low = float(np.min(lows[-21:-1]))
    current_close = float(closes[-1])
    tol = _atr_tolerance(atr_value, 0.10)
    if current_close > prior_high + tol:
        return SetupResultV2(
            setup_type=CorrectedSetupTypeV2.BREAKOUT,
            direction="LONG", confidence=0.70,
            reason_codes=["breakout_long"],
            evidence=[f"close={current_close:.2f} > prior_high={prior_high:.2f}+tol={tol:.4f}"],
        )
    if current_close < prior_low - tol:
        return SetupResultV2(
            setup_type=CorrectedSetupV2.BREAKOUT if False else CorrectedSetupTypeV2.BREAKOUT,
            direction="SHORT", confidence=0.70,
            reason_codes=["breakout_short"],
            evidence=[f"close={current_close:.2f} < prior_low={prior_low:.2f}-tol={tol:.4f}"],
        )
    return None


def detect_breakout_retest(df: pd.DataFrame, prior_high: float = None, min_bars: int = 20, atr_value: float = 0.0) -> Optional[SetupResultV2]:
    """Breakout retest: prior breakout → pullback to breakout level → resumption."""
    if len(df) < min_bars + 5:
        return None
    closes = df["close"].values
    highs = df["high"].values
    lows = df["low"].values
    if prior_high is None:
        prior_high = float(np.max(highs[-(min_bars+5):-5]))
    tol = _atr_tolerance(atr_value, 0.10) if atr_value > 0 else 0.10

    # Look for breakout in last 5 bars
    breakout_idx = -1
    for k in range(2, min(6, len(df) - 1)):
        if closes[-k] > prior_high + tol:
            breakout_idx = -k
            break
    if breakout_idx == -1:
        return None

    # Verify retest: subsequent low came back near prior_high (within tol)
    retest_lows = lows[breakout_idx + 1:-1]
    if len(retest_lows) == 0:
        return None
    retest_low = float(np.min(retest_lows))
    if abs(retest_low - prior_high) > tol * 3:
        return None

    # Verify resumption: current close above prior_high
    current_close = float(closes[-1])
    if current_close <= prior_high + tol * 0.5:
        return None

    return SetupResultV2(
        setup_type=CorrectedSetupTypeV2.BREAKOUT_RETEST,
        direction="LONG", confidence=0.72,
        reason_codes=["breakout_retest_long"],
        evidence=[f"broke {prior_high:.2f}, retested low={retest_low:.2f}, resumed close={current_close:.2f}"],
    )


def detect_range_edge_rejection(df: pd.DataFrame, range_high: float = None, range_low: float = None, atr_value: float = 0.0) -> Optional[SetupResultV2]:
    """Range edge rejection with ATR tolerance."""
    if len(df) < 3:
        return None
    highs = df["high"].values
    lows = df["low"].values
    opens = df["open"].values
    closes = df["close"].values
    if range_high is None:
        range_high = float(np.max(highs[-21:-1]))
    if range_low is None:
        range_low = float(np.min(lows[-21:-1]))
    tol = _atr_tolerance(atr_value, 0.10) if atr_value > 0 else 0.10
    current_high = float(highs[-1])
    current_low = float(lows[-1])
    current_open = float(opens[-1])
    current_close = float(closes[-1])

    if current_high >= range_high - tol and current_close < current_open:
        return SetupResultV2(
            setup_type=CorrectedSetupTypeV2.RANGE_EDGE_REJECTION,
            direction="SHORT", confidence=0.60,
            reason_codes=["range_high_rejection"],
            evidence=[f"high={current_high:.2f} near range_high={range_high:.2f}, bearish close"],
        )
    if current_low <= range_low + tol and current_close > current_open:
        return SetupResultV2(
            setup_type=CorrectedSetupTypeV2.RANGE_EDGE_REJECTION,
            direction="LONG", confidence=0.60,
            reason_codes=["range_low_rejection"],
            evidence=[f"low={current_low:.2f} near range_low={range_low:.2f}, bullish close"],
        )
    return None


def detect_liquidity_sweep_strengthened(df: pd.DataFrame, atr_value: float = 0.0) -> Optional[SetupResultV2]:
    """Liquidity sweep with penetration + reclaim."""
    if len(df) < 25 or atr_value <= 0:
        return None
    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values
    prior_high = float(np.max(highs[-21:-1]))
    prior_low = float(np.min(lows[-21:-1]))
    tol = _atr_tolerance(atr_value, 0.10)
    current_high = float(highs[-1])
    current_low = float(lows[-1])
    current_close = float(closes[-1])

    # Bullish sweep: low penetrated below prior_low, close reclaims above
    if current_low < prior_low - tol and current_close > prior_low + tol * 0.5:
        return SetupResultV2(
            setup_type=CorrectedSetupTypeV2.LIQUIDITY_SWEEP,
            direction="LONG", confidence=0.68,
            reason_codes=["liquidity_sweep_low_reclaim"],
            evidence=[f"low={current_low:.2f} < prior_low={prior_low:.2f}, close reclaimed={current_close:.2f}"],
        )
    # Bearish sweep: high penetrated above prior_high, close reclaims below
    if current_high > prior_high + tol and current_close < prior_high - tol * 0.5:
        return SetupResultV2(
            setup_type=CorrectedSetupTypeV2.LIQUIDITY_SWEEP,
            direction="SHORT", confidence=0.68,
            reason_codes=["liquidity_sweep_high_reclaim"],
            evidence=[f"high={current_high:.2f} > prior_high={prior_high:.2f}, close reclaimed={current_close:.2f}"],
        )
    return None


def detect_failed_breakout(df: pd.DataFrame, atr_value: float = 0.0) -> Optional[SetupResultV2]:
    """Failed breakout: previous bar broke above prior_high but current close fell back below."""
    if len(df) < 25 or atr_value <= 0:
        return None
    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values
    prior_high = float(np.max(highs[-22:-2]))
    prior_low = float(np.min(lows[-22:-2]))
    tol = _atr_tolerance(atr_value, 0.10)
    prev_high = float(highs[-2])
    prev_low = float(lows[-2])
    current_close = float(closes[-1])

    if prev_high > prior_high + tol and current_close < prior_high:
        return SetupResultV2(
            setup_type=CorrectedSetupTypeV2.FAILED_BREAKOUT,
            direction="SHORT", confidence=0.62,
            reason_codes=["failed_breakout_long_reverse"],
            evidence=[f"prev_high={prev_high:.2f} broke {prior_high:.2f}, close fell back={current_close:.2f}"],
        )
    if prev_low < prior_low - tol and current_close > prior_low:
        return SetupResultV2(
            setup_type=CorrectedSetupTypeV2.FAILED_BREAKOUT,
            direction="LONG", confidence=0.62,
            reason_codes=["failed_breakout_short_reverse"],
            evidence=[f"prev_low={prev_low:.2f} broke {prior_low:.2f}, close reclaimed={current_close:.2f}"],
        )
    return None


def detect_continuation(df: pd.DataFrame, direction: str, min_bars: int = 10, atr_value: float = 0.0) -> Optional[SetupResultV2]:
    """Continuation: trend continues with momentum above/below SMA."""
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
                direction="LONG", confidence=0.62,
                reason_codes=["bullish_continuation"],
                evidence=[f"close={current:.2f} > SMA5={sma:.2f} > prev={prev:.2f}"],
            )
    elif direction == "BEAR":
        if current < sma and current < prev:
            return SetupResultV2(
                setup_type=CorrectedSetupTypeV2.CONTINUATION,
                direction="SHORT", confidence=0.62,
                reason_codes=["bearish_continuation"],
                evidence=[f"close={current:.2f} < SMA5={sma:.2f} < prev={prev:.2f}"],
            )
    return None


def detect_fair_value_gap_strengthened(df: pd.DataFrame, atr_value: float = 0.0) -> Optional[SetupResultV2]:
    """FVG with ATR-normalized minimum gap."""
    if len(df) < 3 or atr_value <= 0:
        return None
    highs = df["high"].values
    lows = df["low"].values
    min_gap = _atr_tolerance(atr_value, 0.05)
    # Bullish FVG: low[-1] > high[-3]
    if float(lows[-1]) > float(highs[-3]) + min_gap:
        gap_size = float(lows[-1]) - float(highs[-3])
        return SetupResultV2(
            setup_type=CorrectedSetupTypeV2.FAIR_VALUE_GAP,
            direction="LONG", confidence=0.60,
            reason_codes=["bullish_fvg"],
            evidence=[f"low[-1]={float(lows[-1]):.2f} > high[-3]={float(highs[-3]):.2f}, gap={gap_size:.2f}"],
        )
    # Bearish FVG: high[-1] < low[-3]
    if float(highs[-1]) < float(lows[-3]) - min_gap:
        gap_size = float(lows[-3]) - float(highs[-1])
        return SetupResultV2(
            setup_type=CorrectedSetupTypeV2.FAIR_VALUE_GAP,
            direction="SHORT", confidence=0.60,
            reason_codes=["bearish_fvg"],
            evidence=[f"high[-1]={float(highs[-1]):.2f} < low[-3]={float(lows[-3]):.2f}, gap={gap_size:.2f}"],
        )
    return None


def detect_break_of_structure(df: pd.DataFrame, atr_value: float = 0.0) -> Optional[SetupResultV2]:
    """BOS: close breaks prior 20-bar high (bullish) or low (bearish) by ATR tolerance."""
    if len(df) < 25 or atr_value <= 0:
        return None
    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values
    prior_high = float(np.max(highs[-21:-1]))
    prior_low = float(np.min(lows[-21:-1]))
    current_close = float(closes[-1])
    tol = _atr_tolerance(atr_value, 0.10)
    if current_close > prior_high + tol:
        return SetupResultV2(
            setup_type=CorrectedSetupTypeV2.BULLISH_BREAK_OF_STRUCTURE,
            direction="LONG", confidence=0.68,
            reason_codes=["bos_bull"],
            evidence=[f"close={current_close:.2f} > prior_high={prior_high:.2f}+tol"],
        )
    if current_close < prior_low - tol:
        return SetupResultV2(
            setup_type=CorrectedSetupTypeV2.BEARISH_BREAK_OF_STRUCTURE,
            direction="SHORT", confidence=0.68,
            reason_codes=["bos_bear"],
            evidence=[f"close={current_close:.2f} < prior_low={prior_low:.2f}-tol"],
        )
    return None


def _normalize_score(conf: float) -> float:
    """Normalize score to [0, 1]."""
    return max(0.0, min(1.0, float(conf)))


def scan_setups_v2(df: pd.DataFrame, regime_direction: str, atr_value: float = 0) -> List[SetupResultV2]:
    """Backward-compatible list-returning scan (used by old tests)."""
    result = scan_setups_governed(df, regime_direction, atr_value)
    if result.selected_setup is not None:
        out = [result.selected_setup] + result.alternatives
    else:
        out = result.alternatives if result.alternatives else [SetupResultV2(
            setup_type=CorrectedSetupTypeV2.NONE, direction="NEUTRAL",
            confidence=0.0, reason_codes=["no_setup_detected"], evidence=[],
        )]
    return out


def scan_setups_governed(df: pd.DataFrame, regime_direction: str, atr_value: float = 0,
                         regime_label: str = None) -> ScanResultV2:
    """Canonical governed scan.

    Order:
      1. Detect every candidate
      2. Enforce regime allowed/blocked
      3. Normalize scores
      4. Resolve conflicts AFTER collection
      5. Equal-quality opposite directions → NO_TRADE_CONFLICT
      6. Return selected_setup, alternatives, rejection_reasons, ranking_evidence
    """
    candidates: List[SetupResultV2] = []
    rejection_reasons: List[str] = []
    ranking_evidence: List[str] = []

    # 1. Detect every candidate
    pb = detect_pullback_strengthened(df, regime_direction, atr_value)
    if pb: candidates.append(pb)

    bo = detect_breakout_strengthened(df, atr_value)
    if bo: candidates.append(bo)

    br = detect_breakout_retest(df, atr_value=atr_value)
    if br: candidates.append(br)

    bos = detect_break_of_structure(df, atr_value)
    if bos: candidates.append(bos)

    rer = detect_range_edge_rejection(df, atr_value=atr_value)
    if rer: candidates.append(rer)

    ls = detect_liquidity_sweep_strengthened(df, atr_value)
    if ls: candidates.append(ls)

    fb = detect_failed_breakout(df, atr_value)
    if fb: candidates.append(fb)

    cont = detect_continuation(df, regime_direction, atr_value=atr_value)
    if cont: candidates.append(cont)

    fvg = detect_fair_value_gap_strengthened(df, atr_value)
    if fvg: candidates.append(fvg)

    # 2. Enforce regime allowed/blocked
    if regime_label is None:
        regime_label = _infer_regime_label(regime_direction)
    # Phase 5: Unmapped regime → fail closed
    if regime_label not in REGIME_ALLOWED_SETUPS:
        rejection_reasons.append(f"regime_unmapped:{regime_label}")
        return ScanResultV2(
            selected_setup=None, alternatives=[],
            rejection_reasons=rejection_reasons,
            ranking_evidence=[f"regime={regime_label} not in policy matrix → fail closed"],
            all_candidates=candidates,
            decision="REGIME_BLOCKED",
        )
    allowed = REGIME_ALLOWED_SETUPS[regime_label]
    blocked = REGIME_BLOCKED_SETUPS[regime_label]
    # Phase 5: Unsafe regime → no setups allowed
    if regime_label in UNSAFE_REGIMES:
        rejection_reasons.append(f"regime_unsafe:{regime_label}")
        return ScanResultV2(
            selected_setup=None, alternatives=[],
            rejection_reasons=rejection_reasons,
            ranking_evidence=[f"regime={regime_label} is unsafe → no candidates allowed"],
            all_candidates=candidates,
            decision="REGIME_BLOCKED",
        )
    # Phase 5: Empty allowed set means NO setups allowed (not all)
    if not allowed:
        rejection_reasons.append(f"regime_empty_allowed_set:{regime_label}")
        return ScanResultV2(
            selected_setup=None, alternatives=[],
            rejection_reasons=rejection_reasons,
            ranking_evidence=[f"regime={regime_label} has empty allowed set → no candidates"],
            all_candidates=candidates,
            decision="REGIME_BLOCKED",
        )

    filtered = []
    for c in candidates:
        setup_name = c.setup_type.value
        if blocked and setup_name in blocked:
            rejection_reasons.append(f"{setup_name} blocked by regime {regime_label}")
            continue
        if allowed and setup_name not in allowed:
            rejection_reasons.append(f"{setup_name} not in allowed set for regime {regime_label}")
            continue
        filtered.append(c)

    # 3. Normalize scores
    for c in filtered:
        c.confidence = _normalize_score(c.confidence)

    if not filtered:
        if candidates:
            rejection_reasons.append("all_candidates_filtered_by_regime")
        else:
            rejection_reasons.append("no_candidates_detected")
        return ScanResultV2(
            selected_setup=None, alternatives=[],
            rejection_reasons=rejection_reasons,
            ranking_evidence=ranking_evidence,
            all_candidates=candidates,
            decision="NO_CANDIDATES",
        )

    # 4. Resolve conflicts AFTER all candidates collected
    long_results = [c for c in filtered if c.direction == "LONG"]
    short_results = [c for c in filtered if c.direction == "SHORT"]

    if long_results and short_results:
        max_long = max(long_results, key=lambda r: r.confidence)
        max_short = max(short_results, key=lambda r: r.confidence)
        # 5. Equal-quality (within 0.02) opposite directions → NO_TRADE_CONFLICT
        if abs(max_long.confidence - max_short.confidence) <= 0.02:
            ranking_evidence.append(
                f"CONFLICT: best LONG {max_long.setup_type.value}@{max_long.confidence:.2f} "
                f"≈ best SHORT {max_short.setup_type.value}@{max_short.confidence:.2f}"
            )
            return ScanResultV2(
                selected_setup=None, alternatives=filtered,
                rejection_reasons=["equal_quality_opposite_directions"],
                ranking_evidence=ranking_evidence,
                all_candidates=candidates,
                decision="NO_TRADE_CONFLICT",
            )
        # Keep the higher-confidence direction
        if max_long.confidence > max_short.confidence:
            kept = [c for c in filtered if c.direction == "LONG"]
            dropped = [c for c in filtered if c.direction == "SHORT"]
            for c in dropped:
                rejection_reasons.append(f"dropped {c.setup_type.value} (lower-confidence direction)")
            filtered = kept
        else:
            kept = [c for c in filtered if c.direction == "SHORT"]
            dropped = [c for c in filtered if c.direction == "LONG"]
            for c in dropped:
                rejection_reasons.append(f"dropped {c.setup_type.value} (lower-confidence direction)")
            filtered = kept

    # Rank by confidence (deterministic tie-break by setup_type name)
    filtered.sort(key=lambda r: (-r.confidence, r.setup_type.value))
    selected = filtered[0]
    alternatives = filtered[1:]
    ranking_evidence.append(
        f"SELECTED {selected.setup_type.value} dir={selected.direction} conf={selected.confidence:.2f}; "
        f"alternatives={[f'{a.setup_type.value}@{a.confidence:.2f}' for a in alternatives]}"
    )

    return ScanResultV2(
        selected_setup=selected,
        alternatives=alternatives,
        rejection_reasons=rejection_reasons,
        ranking_evidence=ranking_evidence,
        all_candidates=candidates,
        decision="SELECTED",
    )


def _infer_regime_label(regime_direction: str) -> str:
    """Map simple regime_direction strings to regime labels for allowed/blocked enforcement.

    Phase 5: This is ONLY a fallback. Real callers should pass the actual
    RegimeTypeV2.value as regime_label. Unmapped → UNKNOWN_UNSAFE (fail closed).
    """
    if regime_direction == "BULL":
        return "WEAK_BULL_TREND"
    if regime_direction == "BEAR":
        return "WEAK_BEAR_TREND"
    if regime_direction in ("RANGE", "NEUTRAL"):
        return "STABLE_RANGE"
    return "UNKNOWN_UNSAFE"


__all__ = [
    "CorrectedSetupTypeV2", "SetupResultV2", "ScanResultV2",
    "detect_pullback_strengthened", "detect_breakout_strengthened",
    "detect_breakout_retest", "detect_range_edge_rejection",
    "detect_continuation", "detect_liquidity_sweep_strengthened",
    "detect_failed_breakout", "detect_fair_value_gap_strengthened",
    "detect_break_of_structure",
    "scan_setups_v2", "scan_setups_governed",
    "REGIME_ALLOWED_SETUPS", "REGIME_BLOCKED_SETUPS",
    "REGIME_RISK_MODIFIERS", "REGIME_THRESHOLD_MODIFIERS",
    "UNSAFE_REGIMES",
]
