"""
TITAN XAU AI — Volatility Engine (Module 8)
Production implementation: news-aware ATR breakout, volatility-of-volatility,
regime-conditional sizing, volatility expansion detection.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import numpy as np

from titan.regime.engine import RegimeFeatures

logger = logging.getLogger(__name__)


class VolPattern(str, Enum):
    ATR_BREAKOUT_UP = "ATR_BREAKOUT_UP"       # Volatility breakout long
    ATR_BREAKOUT_DOWN = "ATR_BREAKOUT_DOWN"   # Volatility breakout short
    VOL_EXPANSION = "VOL_EXPANSION"           # Volatility expanding (prepare)
    VOL_CONTRACTION = "VOL_CONTRACTION"       # Volatility contracting (wait)
    NEWS_BREAKOUT = "NEWS_BREAKOUT"           # Post-news direction


class SignalDirection(int, Enum):
    LONG = 1
    SHORT = -1
    FLAT = 0


@dataclass
class VolatilitySignal:
    direction: SignalDirection
    pattern: VolPattern
    entry_price: float
    stop_loss: float
    take_profit: float
    risk_reward_ratio: float
    confidence: float
    proposed_volume: float
    atr_current: float = 0.0
    atr_avg: float = 0.0
    vol_of_vol: float = 0.0          # Volatility of volatility
    news_active: bool = False
    timestamp: float = field(default_factory=time.time)


class VolatilityEngine:
    """
    Volatility-based strategy for high-volatility regimes.
    - ATR breakout: enters on volatility expansion
    - News-aware: blocks entries during news, enters post-news direction
    - Vol-of-vol: tracks volatility of ATR itself
    - Adaptive sizing: reduces size in extreme volatility
    """

    def __init__(self, config: dict = None):
        cfg = config or {}
        self._atr_period = cfg.get("atr_period", 14)
        self._atr_avg_period = cfg.get("atr_avg_period", 30)
        self._breakout_mult = cfg.get("breakout_mult", 2.0)  # 2x ATR for breakout
        self._vol_of_vol_period = cfg.get("vol_of_vol_period", 20)
        self._min_confidence = cfg.get("min_confidence", 0.60)
        self._risk_per_trade = cfg.get("risk_per_trade", 0.005)  # 0.5% (lower for vol)
        self._max_atr_pct = cfg.get("max_atr_pct", 2.0)  # Don't trade if ATR > 2% of price
        self._signal_count = 0
        self._atr_history: list[float] = []

    def generate_signal(
        self,
        closes: np.ndarray,
        highs: np.ndarray,
        lows: np.ndarray,
        features: RegimeFeatures,
        current_price: float,
        account_equity: float,
        news_active: bool = False,
    ) -> Optional[VolatilitySignal]:
        if len(closes) < self._atr_avg_period + self._atr_period:
            return None

        # Don't trade if ATR is too high (extreme volatility)
        if features.atr_pct > self._max_atr_pct:
            logger.debug(f"ATR too high: {features.atr_pct:.2f}% > {self._max_atr_pct}%")
            return None

        # Compute ATR and averages
        atr = self._compute_atr(highs, lows, closes, self._atr_period)
        atr_history = self._compute_atr_series(highs, lows, closes, self._atr_period)
        atr_avg = np.mean(atr_history[-self._atr_avg_period:]) if len(atr_history) >= self._atr_avg_period else atr

        # Volatility of volatility (std of ATR history)
        if len(atr_history) >= self._vol_of_vol_period:
            vol_of_vol = float(np.std(atr_history[-self._vol_of_vol_period:], ddof=1) / (atr_avg + 1e-10))
        else:
            vol_of_vol = 0.0

        # Track ATR history
        self._atr_history.append(atr)
        if len(self._atr_history) > 100:
            self._atr_history = self._atr_history[-100:]

        # Pattern detection
        signal = None

        # Pattern 1: ATR Breakout — current candle breaks 2x ATR from previous close
        if not news_active:
            prev_close = closes[-2]
            price_move = current_price - prev_close

            if abs(price_move) > self._breakout_mult * atr and features.adx > 20:
                if price_move > 0:
                    signal = self._create_breakout_signal(
                        SignalDirection.LONG, VolPattern.ATR_BREAKOUT_UP,
                        current_price, atr, atr_avg, vol_of_vol, features, news_active
                    )
                else:
                    signal = self._create_breakout_signal(
                        SignalDirection.SHORT, VolPattern.ATR_BREAKOUT_DOWN,
                        current_price, atr, atr_avg, vol_of_vol, features, news_active
                    )

        # Pattern 2: Volatility expansion — ATR > 1.5x average (prepare for breakout)
        elif atr > 1.5 * atr_avg and vol_of_vol > 0.3:
            # Don't enter yet — wait for direction
            signal = VolatilitySignal(
                direction=SignalDirection.FLAT,
                pattern=VolPattern.VOL_EXPANSION,
                entry_price=current_price,
                stop_loss=0, take_profit=0,
                risk_reward_ratio=0, confidence=0.5,
                proposed_volume=0.0,
                atr_current=atr, atr_avg=atr_avg,
                vol_of_vol=vol_of_vol, news_active=news_active,
            )

        # Pattern 3: Post-news breakout — enter in news direction after spread normalizes
        if news_active and features.spread_ratio < 2.0:
            # Spread normalizing after news — enter in breakout direction
            prev_close = closes[-2]
            price_move = current_price - prev_close

            if abs(price_move) > 1.5 * atr:
                if price_move > 0:
                    signal = self._create_breakout_signal(
                        SignalDirection.LONG, VolPattern.NEWS_BREAKOUT,
                        current_price, atr, atr_avg, vol_of_vol, features, news_active=True
                    )
                else:
                    signal = self._create_breakout_signal(
                        SignalDirection.SHORT, VolPattern.NEWS_BREAKOUT,
                        current_price, atr, atr_avg, vol_of_vol, features, news_active=True
                    )

        if signal and signal.confidence >= self._min_confidence and signal.direction != SignalDirection.FLAT:
            signal.proposed_volume = self._calculate_volume(
                account_equity, current_price, signal.stop_loss, signal.confidence, features.atr_pct
            )
            self._signal_count += 1
            logger.info(
                f"Volatility signal: {signal.direction.name} {signal.pattern.value} "
                f"conf={signal.confidence:.2f} ATR={atr:.2f} vol_of_vol={vol_of_vol:.3f}"
            )
            return signal

        return None

    def _create_breakout_signal(self, direction, pattern, price, atr, atr_avg,
                                 vol_of_vol, features, news_active):
        """Create volatility breakout signal."""
        # Wider stops for volatility trades (2x ATR)
        if direction == SignalDirection.LONG:
            stop_loss = price - 2.0 * atr
            take_profit = price + 3.0 * atr  # 1.5:1 RR
            distance = price - stop_loss
        else:
            stop_loss = price + 2.0 * atr
            take_profit = price - 3.0 * atr
            distance = stop_loss - price

        rr = 3.0 / 2.0  # Fixed 1.5:1 for vol trades

        # Confidence based on ATR ratio + ADX + volume
        atr_ratio = atr / atr_avg if atr_avg > 0 else 1.0
        atr_conf = min(atr_ratio / 3.0, 0.4)
        adx_conf = min(features.adx / 50, 0.3)
        vol_conf = min(vol_of_vol, 0.2)
        news_bonus = 0.1 if news_active else 0.0

        confidence = min(0.4 + atr_conf + adx_conf + vol_conf + news_bonus, 0.90)

        return VolatilitySignal(
            direction=direction, pattern=pattern,
            entry_price=price, stop_loss=stop_loss, take_profit=take_profit,
            risk_reward_ratio=rr, confidence=confidence,
            proposed_volume=0.0,
            atr_current=atr, atr_avg=atr_avg,
            vol_of_vol=vol_of_vol, news_active=news_active,
        )

    def _calculate_volume(self, equity, entry, stop, confidence, atr_pct):
        """Position sizing — reduced for high volatility."""
        risk_amount = equity * self._risk_per_trade
        risk_per_lot = abs(entry - stop) * 100
        if risk_per_lot <= 0:
            return 0.01

        base_volume = risk_amount / risk_per_lot

        # Reduce size in high volatility (ATR > 1% of price)
        vol_mult = 1.0
        if atr_pct > 1.0:
            vol_mult = 0.5
        elif atr_pct > 0.5:
            vol_mult = 0.75

        conf_mult = 0.5 + confidence * 0.5
        volume = base_volume * vol_mult * conf_mult
        return max(round(volume, 2), 0.01)

    def _compute_atr(self, highs, lows, closes, period=14):
        tr = np.maximum(
            highs - lows,
            np.maximum(
                np.abs(highs - np.roll(closes, 1)),
                np.abs(lows - np.roll(closes, 1)),
            ),
        )
        tr[0] = highs[0] - lows[0]
        return float(np.mean(tr[-period:]))

    def _compute_atr_series(self, highs, lows, closes, period=14):
        """Compute rolling ATR series."""
        tr = np.maximum(
            highs - lows,
            np.maximum(
                np.abs(highs - np.roll(closes, 1)),
                np.abs(lows - np.roll(closes, 1)),
            ),
        )
        tr[0] = highs[0] - lows[0]

        atr_series = []
        for i in range(period, len(tr) + 1):
            atr_series.append(np.mean(tr[i-period:i]))

        return np.array(atr_series) if atr_series else np.array([1.0])

    @property
    def stats(self):
        return {"signals": self._signal_count}

    @property
    def current_atr_ratio(self) -> float:
        """Current ATR / average ATR ratio."""
        if len(self._atr_history) < 2:
            return 1.0
        avg = np.mean(self._atr_history)
        if avg == 0:
            return 1.0
        return self._atr_history[-1] / avg
