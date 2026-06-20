"""
TITAN XAU AI — Regime Detection Engine (Module 5)
Production implementation: 4-regime classifier, 3-model vote
(HMM + Logit + Heuristic), transition confidence, regime stability.
CPU-only, NumPy/SciPy, no GPU required.
"""
from __future__ import annotations

import collections
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import numpy as np
from scipy import stats

logger = logging.getLogger(__name__)


class Regime(str, Enum):
    TREND = "TREND"
    RANGE = "RANGE"
    VOLATILE = "VOLATILE"
    NEWS = "NEWS"
    UNKNOWN = "UNKNOWN"


@dataclass
class RegimeFeatures:
    """Features extracted from price data for regime classification."""
    adx: float = 0.0              # ADX indicator (trend strength)
    atr_pct: float = 0.0          # ATR as % of price
    bb_width: float = 0.0         # Bollinger Band width (ATR ratio)
    bb_width_ratio: float = 0.0   # BB width / 30-day avg BB width
    ema_slope: float = 0.0        # EMA50 slope (directional bias)
    price_above_ema: bool = False # Price above EMA50
    hh_hl_pattern: bool = False   # Higher highs / higher lows
    lh_ll_pattern: bool = False   # Lower highs / lower lows
    rsi: float = 50.0             # RSI(14)
    volume_ratio: float = 1.0     # Current volume / avg volume
    spread_ratio: float = 1.0     # Current spread / baseline spread
    candle_range_ratio: float = 1.0  # Current candle range / avg range
    timestamp: float = 0.0


@dataclass
class RegimeVote:
    """Single model's regime vote."""
    model_name: str
    regime: Regime
    confidence: float              # 0.0 - 1.0


@dataclass
class RegimeResult:
    """Final regime detection result after 3-model vote."""
    regime: Regime
    confidence: float              # 0.0 - 1.0
    votes: list[RegimeVote] = field(default_factory=list)
    transition_confidence: float = 0.0  # confidence in regime change
    stable: bool = True            # regime stable for >= 5 minutes
    duration_seconds: float = 0.0  # how long in current regime
    evaluation_time_ms: float = 0.0
    features: Optional[RegimeFeatures] = None


class FeatureExtractor:
    """Extracts regime features from price arrays."""

    @staticmethod
    def extract(
        closes: np.ndarray,
        highs: np.ndarray,
        lows: np.ndarray,
        volumes: np.ndarray,
        spread_ratio: float = 1.0,
    ) -> RegimeFeatures:
        if len(closes) < 30:
            return RegimeFeatures()

        # ADX approximation (simplified Welles Wilder)
        adx = FeatureExtractor._compute_adx(highs, lows, closes, period=14)

        # ATR as % of price
        atr = FeatureExtractor._compute_atr(highs, lows, closes, period=14)
        atr_pct = (atr / closes[-1]) * 100 if closes[-1] > 0 else 0.0

        # Bollinger Bands
        sma = np.mean(closes[-20:])
        std = np.std(closes[-20:], ddof=1)
        bb_upper = sma + 2 * std
        bb_lower = sma - 2 * std
        bb_width = bb_upper - bb_lower
        avg_bb_width = np.mean([
            np.std(closes[i-20:i], ddof=1) * 4
            for i in range(20, len(closes))
        ]) if len(closes) > 40 else bb_width
        bb_width_ratio = bb_width / avg_bb_width if avg_bb_width > 0 else 1.0

        # EMA50 slope
        ema50 = FeatureExtractor._compute_ema(closes, 50)
        ema_slope = (ema50[-1] - ema50[-5]) / ema50[-5] * 100 if len(ema50) >= 5 and ema50[-5] > 0 else 0.0
        price_above_ema = closes[-1] > ema50[-1]

        # HH/HL or LH/LL pattern
        hh_hl = FeatureExtractor._check_hh_hl(highs[-10:], lows[-10:])
        lh_ll = FeatureExtractor._check_lh_ll(highs[-10:], lows[-10:])

        # RSI
        rsi = FeatureExtractor._compute_rsi(closes, period=14)

        # Volume ratio
        avg_vol = np.mean(volumes[-20:]) if len(volumes) >= 20 else 1.0
        volume_ratio = volumes[-1] / avg_vol if avg_vol > 0 else 1.0

        # Candle range ratio
        candle_ranges = highs[-20:] - lows[-20:]
        avg_range = np.mean(candle_ranges)
        current_range = candle_ranges[-1]
        candle_range_ratio = current_range / avg_range if avg_range > 0 else 1.0

        return RegimeFeatures(
            adx=adx,
            atr_pct=atr_pct,
            bb_width=bb_width,
            bb_width_ratio=bb_width_ratio,
            ema_slope=ema_slope,
            price_above_ema=price_above_ema,
            hh_hl_pattern=hh_hl,
            lh_ll_pattern=lh_ll,
            rsi=rsi,
            volume_ratio=float(volume_ratio),
            spread_ratio=spread_ratio,
            candle_range_ratio=float(candle_range_ratio),
            timestamp=time.time(),
        )

    @staticmethod
    def _compute_atr(highs, lows, closes, period=14):
        tr = np.maximum(
            highs - lows,
            np.maximum(
                np.abs(highs - np.roll(closes, 1)),
                np.abs(lows - np.roll(closes, 1)),
            ),
        )
        tr[0] = highs[0] - lows[0]
        return np.mean(tr[-period:])

    @staticmethod
    def _compute_adx(highs, lows, closes, period=14):
        if len(closes) < period * 2:
            return 25.0

        plus_dm = np.zeros(len(closes))
        minus_dm = np.zeros(len(closes))
        tr = np.zeros(len(closes))

        for i in range(1, len(closes)):
            up_move = highs[i] - highs[i-1]
            down_move = lows[i-1] - lows[i]
            if up_move > down_move and up_move > 0:
                plus_dm[i] = up_move
            if down_move > up_move and down_move > 0:
                minus_dm[i] = down_move
            tr[i] = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i-1]),
                abs(lows[i] - closes[i-1]),
            )

        atr = np.mean(tr[-period:])
        if atr == 0:
            return 25.0

        plus_di = 100 * np.mean(plus_dm[-period:]) / atr
        minus_di = 100 * np.mean(minus_dm[-period:]) / atr

        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di) if (plus_di + minus_di) > 0 else 0
        return float(dx)

    @staticmethod
    def _compute_ema(data, period):
        alpha = 2.0 / (period + 1)
        ema = np.zeros(len(data))
        ema[0] = data[0]
        for i in range(1, len(data)):
            ema[i] = alpha * data[i] + (1 - alpha) * ema[i-1]
        return ema

    @staticmethod
    def _compute_rsi(closes, period=14):
        if len(closes) < period + 1:
            return 50.0
        deltas = np.diff(closes[-(period+1):])
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        avg_gain = np.mean(gains)
        avg_loss = np.mean(losses)
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return float(100.0 - (100.0 / (1.0 + rs)))

    @staticmethod
    def _check_hh_hl(highs, lows):
        if len(highs) < 4:
            return False
        hh = highs[-1] > highs[-3] and highs[-3] > highs[-5] if len(highs) >= 5 else False
        hl = lows[-1] > lows[-3] and lows[-3] > lows[-5] if len(lows) >= 5 else False
        return hh or hl

    @staticmethod
    def _check_lh_ll(highs, lows):
        if len(highs) < 4:
            return False
        lh = highs[-1] < highs[-3] and highs[-3] < highs[-5] if len(highs) >= 5 else False
        ll = lows[-1] < lows[-3] and lows[-3] < lows[-5] if len(lows) >= 5 else False
        return lh or ll


class HMMRegimeModel:
    """Simplified Hidden Markov Model for regime detection."""

    def __init__(self):
        self._transition_matrix = np.array([
            [0.92, 0.05, 0.02, 0.01],  # TREND -> ?
            [0.05, 0.90, 0.03, 0.02],  # RANGE -> ?
            [0.10, 0.10, 0.70, 0.10],  # VOLATILE -> ?
            [0.05, 0.05, 0.10, 0.80],  # NEWS -> ?
        ])
        self._current_state = Regime.RANGE
        self._state_history: collections.deque = collections.deque(maxlen=100)

    def predict(self, features: RegimeFeatures) -> RegimeVote:
        state_idx = {
            Regime.TREND: 0, Regime.RANGE: 1,
            Regime.VOLATILE: 2, Regime.NEWS: 3,
        }[self._current_state]
        transitions = self._transition_matrix[state_idx]

        # Emission probabilities based on features
        emissions = np.array([
            self._trend_emission(features),
            self._range_emission(features),
            self._volatile_emission(features),
            self._news_emission(features),
        ])

        # Combined probability
        combined = transitions * emissions
        total = combined.sum()
        if total > 0:
            probs = combined / total
        else:
            probs = np.array([0.25, 0.25, 0.25, 0.25])

        regimes = [Regime.TREND, Regime.RANGE, Regime.VOLATILE, Regime.NEWS]
        best_idx = int(np.argmax(probs))
        new_regime = regimes[best_idx]
        confidence = float(probs[best_idx])

        self._current_state = new_regime
        self._state_history.append(new_regime)

        return RegimeVote(
            model_name="HMM",
            regime=new_regime,
            confidence=confidence,
        )

    def _trend_emission(self, f: RegimeFeatures) -> float:
        score = 0.0
        if f.adx > 25:
            score += 0.3
        if abs(f.ema_slope) > 0.05:
            score += 0.2
        if f.hh_hl_pattern or f.lh_ll_pattern:
            score += 0.3
        if f.bb_width_ratio < 1.2:
            score += 0.2
        return score

    def _range_emission(self, f: RegimeFeatures) -> float:
        score = 0.0
        if f.adx < 20:
            score += 0.4
        if f.bb_width_ratio < 0.8:
            score += 0.3
        if 40 < f.rsi < 60:
            score += 0.3
        return score

    def _volatile_emission(self, f: RegimeFeatures) -> float:
        score = 0.0
        if f.atr_pct > 0.5:
            score += 0.3
        if f.bb_width_ratio > 1.5:
            score += 0.3
        if f.candle_range_ratio > 1.5:
            score += 0.2
        if f.volume_ratio > 1.5:
            score += 0.2
        return score

    def _news_emission(self, f: RegimeFeatures) -> float:
        score = 0.0
        if f.spread_ratio > 3.0:
            score += 0.5
        if f.candle_range_ratio > 2.0:
            score += 0.3
        if f.volume_ratio > 2.0:
            score += 0.2
        return score


class LogitRegimeModel:
    """Logistic regression-based regime classifier (simplified)."""

    def __init__(self):
        self._weights = {
            Regime.TREND:    np.array([0.3, -0.1, -0.1, 0.2, 0.3, 0.0, 0.2, 0.0, 0.0, 0.0, -0.1, -0.1]),
            Regime.RANGE:    np.array([-0.3, 0.0, -0.2, -0.2, -0.1, 0.1, 0.0, 0.0, 0.2, 0.0, -0.1, -0.1]),
            Regime.VOLATILE: np.array([0.0, 0.3, 0.3, 0.2, 0.0, 0.0, 0.0, 0.0, 0.0, 0.2, 0.0, 0.3]),
            Regime.NEWS:     np.array([0.0, 0.1, 0.1, 0.1, 0.0, 0.0, 0.0, 0.0, 0.0, 0.3, 0.5, 0.2]),
        }
        self._biases = {Regime.TREND: -0.5, Regime.RANGE: 0.0, Regime.VOLATILE: -1.0, Regime.NEWS: -1.5}

    def predict(self, features: RegimeFeatures) -> RegimeVote:
        x = np.array([
            features.adx / 50.0, features.atr_pct, features.bb_width_ratio, features.candle_range_ratio,
            abs(features.ema_slope), float(features.price_above_ema), float(features.hh_hl_pattern),
            float(features.lh_ll_pattern), (features.rsi - 50) / 50, features.volume_ratio,
            features.spread_ratio, features.candle_range_ratio,
        ])

        scores = {}
        for regime, w in self._weights.items():
            z = np.dot(w, x) + self._biases[regime]
            scores[regime] = 1.0 / (1.0 + np.exp(-z))

        total = sum(scores.values())
        if total > 0:
            probs = {r: s / total for r, s in scores.items()}
        else:
            probs = {r: 0.25 for r in scores}

        best_regime = max(probs, key=probs.get)
        return RegimeVote(
            model_name="Logit",
            regime=best_regime,
            confidence=probs[best_regime],
        )


class HeuristicRegimeModel:
    """Rule-based heuristic regime classifier."""

    def predict(self, features: RegimeFeatures) -> RegimeVote:
        scores = {r: 0.0 for r in Regime if r != Regime.UNKNOWN}

        # Trend signals
        if features.adx > 25:
            scores[Regime.TREND] += 2.0
        if features.adx > 35:
            scores[Regime.TREND] += 1.0
        if features.hh_hl_pattern or features.lh_ll_pattern:
            scores[Regime.TREND] += 1.5
        if abs(features.ema_slope) > 0.1:
            scores[Regime.TREND] += 1.0

        # Range signals
        if features.adx < 20:
            scores[Regime.RANGE] += 2.0
        if features.bb_width_ratio < 0.7:
            scores[Regime.RANGE] += 1.5
        if 40 < features.rsi < 60:
            scores[Regime.RANGE] += 1.0

        # Volatile signals
        if features.atr_pct > 0.5:
            scores[Regime.VOLATILE] += 2.0
        if features.bb_width_ratio > 1.5:
            scores[Regime.VOLATILE] += 1.5
        if features.candle_range_ratio > 1.5:
            scores[Regime.VOLATILE] += 1.0
        if features.volume_ratio > 1.5:
            scores[Regime.VOLATILE] += 0.5

        # News signals
        if features.spread_ratio > 3.0:
            scores[Regime.NEWS] += 3.0
        if features.spread_ratio > 5.0:
            scores[Regime.NEWS] += 2.0
        if features.candle_range_ratio > 2.0 and features.spread_ratio > 2.0:
            scores[Regime.NEWS] += 1.5

        total = sum(scores.values())
        if total > 0:
            probs = {r: s / total for r, s in scores.items()}
        else:
            probs = {r: 0.25 for r in scores}

        best_regime = max(probs, key=probs.get)
        return RegimeVote(
            model_name="Heuristic",
            regime=best_regime,
            confidence=probs[best_regime],
        )


class RegimeDetector:
    """
    Main regime detection engine.
    3-model vote (HMM + Logit + Heuristic).
    2/3 consensus required. Transition confidence >= 0.65.
    """

    def __init__(self):
        self._hmm = HMMRegimeModel()
        self._logit = LogitRegimeModel()
        self._heuristic = HeuristicRegimeModel()
        self._current_regime: Regime = Regime.UNKNOWN
        self._regime_start_time: float = time.time()
        self._regime_history: collections.deque = collections.deque(maxlen=1000)
        self._min_confidence = 0.65
        self._min_stability_seconds = 300  # 5 minutes

    def detect(self, features: RegimeFeatures) -> RegimeResult:
        """Run 3-model vote and return regime result."""
        start = time.perf_counter()

        votes = [
            self._hmm.predict(features),
            self._logit.predict(features),
            self._heuristic.predict(features),
        ]

        # 2/3 consensus vote
        regime_counts: dict[Regime, float] = {}
        for v in votes:
            if v.regime not in regime_counts:
                regime_counts[v.regime] = 0.0
            regime_counts[v.regime] += v.confidence

        # Sort by weighted vote
        sorted_regimes = sorted(regime_counts.items(), key=lambda x: x[1], reverse=True)
        best_regime = sorted_regimes[0][0]
        best_score = sorted_regimes[0][1]

        # Check if 2+ models agree
        agreeing_models = sum(1 for v in votes if v.regime == best_regime)
        consensus = agreeing_models >= 2

        # Confidence = average confidence of agreeing models
        agreeing_confs = [v.confidence for v in votes if v.regime == best_regime]
        confidence = float(np.mean(agreeing_confs)) if agreeing_confs else 0.0

        # Transition confidence
        transition_conf = confidence if best_regime != self._current_regime else 1.0

        # Regime change handling
        if best_regime != self._current_regime:
            if consensus and confidence >= self._min_confidence:
                # Regime change confirmed
                old_regime = self._current_regime
                self._current_regime = best_regime
                self._regime_start_time = time.time()
                logger.info(
                    f"Regime change: {old_regime.value} → {best_regime.value} "
                    f"(confidence: {confidence:.2f}, votes: {agreeing_models}/3)"
                )
            else:
                # Not enough confidence — keep current regime
                best_regime = self._current_regime
                confidence = 0.5
        else:
            transition_conf = 1.0

        duration = time.time() - self._regime_start_time
        stable = duration >= self._min_stability_seconds

        elapsed_ms = (time.perf_counter() - start) * 1000

        result = RegimeResult(
            regime=best_regime,
            confidence=confidence,
            votes=votes,
            transition_confidence=transition_conf,
            stable=stable,
            duration_seconds=duration,
            evaluation_time_ms=elapsed_ms,
            features=features,
        )

        self._regime_history.append(result)
        return result

    @property
    def current_regime(self) -> Regime:
        return self._current_regime

    @property
    def regime_duration(self) -> float:
        return time.time() - self._regime_start_time

    def get_history(self, count: int = 100) -> list[RegimeResult]:
        if count > len(self._regime_history):
            count = len(self._regime_history)
        return list(self._regime_history)[-count:]
