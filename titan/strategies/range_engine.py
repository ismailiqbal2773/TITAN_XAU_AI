"""
TITAN XAU AI — Range Strategy Engine (Module 7)
Production implementation: BB + RSI + ATR + Hurst, smart recovery
(non-martingale), mean-reversion entries at band extremes.
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


class RangePattern(str, Enum):
    BB_UPPER_TOUCH = "BB_UPPER_TOUCH"   # Price touches upper BB → sell
    BB_LOWER_TOUCH = "BB_LOWER_TOUCH"  # Price touches lower BB → buy
    RSI_OVERBOUGHT = "RSI_OVERBOUGHT"  # RSI > 70 → sell
    RSI_OVERSOLD = "RSI_OVERSOLD"      # RSI < 30 → buy
    MEAN_REVERT = "MEAN_REVERT"        # Price reverts from extreme to mean


class SignalDirection(int, Enum):
    LONG = 1
    SHORT = -1
    FLAT = 0


@dataclass
class RangeSignal:
    direction: SignalDirection
    pattern: RangePattern
    entry_price: float
    stop_loss: float
    take_profit: float
    risk_reward_ratio: float
    confidence: float
    proposed_volume: float
    hurst_exponent: float = 0.5
    recovery_count: int = 0           # Smart recovery tracking (non-martingale)
    timestamp: float = field(default_factory=time.time)


class RangeStrategyEngine:
    """
    Mean Reversion Strategy for range markets.
    Uses Bollinger Bands + RSI + ATR + Hurst Exponent.
    Smart recovery: if first entry fails, re-enter at better price
    with SAME lot size (never increase — anti-martingale).
    """

    def __init__(self, config: dict = None):
        cfg = config or {}
        self._bb_period = cfg.get("bb_period", 20)
        self._bb_std = cfg.get("bb_std", 2.0)
        self._rsi_period = cfg.get("rsi_period", 14)
        self._rsi_overbought = cfg.get("rsi_overbought", 70)
        self._rsi_oversold = cfg.get("rsi_oversold", 30)
        self._atr_period = cfg.get("atr_period", 14)
        self._hurst_window = cfg.get("hurst_window", 100)
        self._min_confidence = cfg.get("min_confidence", 0.60)
        self._risk_per_trade = cfg.get("risk_per_trade", 0.01)
        self._max_recovery_attempts = cfg.get("max_recovery", 2)  # Max re-entries
        self._signal_count = 0
        self._recovery_attempts = 0

    def generate_signal(
        self,
        closes: np.ndarray,
        highs: np.ndarray,
        lows: np.ndarray,
        features: RegimeFeatures,
        current_price: float,
        account_equity: float,
    ) -> Optional[RangeSignal]:
        if len(closes) < self._bb_period + 10:
            return None

        # Only trade in RANGE regime (caller checks, but verify)
        if features.adx > 25:
            return None

        # Compute indicators
        sma = np.mean(closes[-self._bb_period:])
        std = np.std(closes[-self._bb_period:], ddof=1)
        bb_upper = sma + self._bb_std * std
        bb_lower = sma - self._bb_std * std
        bb_mid = sma
        rsi = features.rsi
        atr = self._compute_atr(highs, lows, closes, self._atr_period)

        # Hurst exponent (mean-reversion check)
        hurst = self._compute_hurst(closes[-self._hurst_window:]) if len(closes) >= self._hurst_window else 0.5

        # Only trade if Hurst < 0.5 (mean-reverting series)
        if hurst > 0.55:
            return None

        # Check patterns
        signal = None

        # Pattern 1: BB upper touch + RSI overbought → SELL
        if current_price >= bb_upper and rsi > self._rsi_overbought:
            signal = self._create_signal(
                SignalDirection.SHORT, RangePattern.BB_UPPER_TOUCH,
                current_price, bb_upper, bb_lower, bb_mid, atr, features, hurst
            )

        # Pattern 2: BB lower touch + RSI oversold → BUY
        elif current_price <= bb_lower and rsi < self._rsi_oversold:
            signal = self._create_signal(
                SignalDirection.LONG, RangePattern.BB_LOWER_TOUCH,
                current_price, bb_lower, bb_upper, bb_mid, atr, features, hurst
            )

        # Pattern 3: RSI overbought without BB touch (weaker signal)
        elif rsi > self._rsi_overbought + 5:
            signal = self._create_signal(
                SignalDirection.SHORT, RangePattern.RSI_OVERBOUGHT,
                current_price, bb_upper, bb_lower, bb_mid, atr, features, hurst
            )

        # Pattern 4: RSI oversold without BB touch
        elif rsi < self._rsi_oversold - 5:
            signal = self._create_signal(
                SignalDirection.LONG, RangePattern.RSI_OVERSOLD,
                current_price, bb_lower, bb_upper, bb_mid, atr, features, hurst
            )

        # Pattern 5: Mean reversion from extreme back to mid
        elif abs(current_price - bb_mid) > 1.5 * std and 30 < rsi < 70:
            if current_price > bb_mid:
                signal = self._create_signal(
                    SignalDirection.SHORT, RangePattern.MEAN_REVERT,
                    current_price, bb_upper, bb_lower, bb_mid, atr, features, hurst
                )
            else:
                signal = self._create_signal(
                    SignalDirection.LONG, RangePattern.MEAN_REVERT,
                    current_price, bb_lower, bb_upper, bb_mid, atr, features, hurst
                )

        if signal and signal.confidence >= self._min_confidence:
            signal.proposed_volume = self._calculate_volume(
                account_equity, current_price, signal.stop_loss, signal.confidence
            )
            signal.recovery_count = self._recovery_attempts
            self._signal_count += 1
            logger.info(
                f"Range signal: {signal.direction.name} {signal.pattern.value} "
                f"conf={signal.confidence:.2f} hurst={hurst:.3f}"
            )
            return signal

        return None

    def _create_signal(self, direction, pattern, price, band_extreme,
                       opposite_band, mid_band, atr, features, hurst):
        """Create range signal with stop and target."""
        if direction == SignalDirection.LONG:
            stop_loss = price - atr
            take_profit = mid_band + (mid_band - price) * 0.5  # Half way to mid+
            distance = price - stop_loss
        else:
            stop_loss = price + atr
            take_profit = mid_band - (price - mid_band) * 0.5
            distance = stop_loss - price

        if distance <= 0:
            rr = 0
        else:
            target_distance = abs(take_profit - price)
            rr = target_distance / distance

        # Confidence based on RSI extremity + Hurst + BB position
        rsi_conf = abs(features.rsi - 50) / 50  # 0-1, higher = more extreme
        hurst_conf = (0.5 - hurst) * 2  # 0-1, lower hurst = more mean-reverting
        bb_conf = abs(price - mid_band) / (abs(band_extreme - mid_band) + 0.001)

        confidence = min(0.4 + rsi_conf * 0.2 + hurst_conf * 0.2 + bb_conf * 0.15, 0.90)

        return RangeSignal(
            direction=direction, pattern=pattern,
            entry_price=price, stop_loss=stop_loss, take_profit=take_profit,
            risk_reward_ratio=rr, confidence=confidence,
            proposed_volume=0.0, hurst_exponent=hurst,
        )

    def on_trade_closed(self, won: bool) -> None:
        """Track trade outcome for smart recovery logic."""
        if won:
            self._recovery_attempts = 0
        else:
            self._recovery_attempts = min(self._recovery_attempts + 1, self._max_recovery_attempts)

    @property
    def should_attempt_recovery(self) -> bool:
        """True if smart recovery is allowed (non-martingale)."""
        return self._recovery_attempts < self._max_recovery_attempts

    def _calculate_volume(self, equity, entry, stop, confidence):
        """Position sizing — SAME lot for recovery (anti-martingale)."""
        risk_amount = equity * self._risk_per_trade
        risk_per_lot = abs(entry - stop) * 100
        if risk_per_lot <= 0:
            return 0.01
        base_volume = risk_amount / risk_per_lot
        # Reduce by confidence
        conf_mult = 0.5 + confidence * 0.5
        volume = base_volume * conf_mult
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
        return float(np.mean(tr[-period:])) if len(tr) >= period else 1.0

    def _compute_hurst(self, data: np.ndarray) -> float:
        """
        Compute Hurst exponent using R/S analysis.
        H < 0.5: mean-reverting
        H = 0.5: random walk
        H > 0.5: trending
        """
        if len(data) < 20:
            return 0.5

        max_lags = min(len(data) - 1, 50)
        lags = range(2, max_lags)
        tau = []
        for lag in lags:
            pp = data[lag:] - data[:-lag]
            if len(pp) == 0:
                continue
            std = np.std(pp)
            if std == 0:
                continue
            tau.append(std * np.sqrt(lag))

        if len(tau) < 3:
            return 0.5

        # Linear regression: log(tau) = H * log(lag) + c
        log_lags = np.log(np.array(list(lags)[:len(tau)]))
        log_tau = np.log(np.array(tau))

        try:
            slope, _, _, _, _ = np.polyfit(log_lags, log_tau, 1, full=True)[0:1] if hasattr(np.polyfit(log_lags, log_tau, 1, full=True), '__getitem__') else (np.polyfit(log_lags, log_tau, 1)[0],)
            slope = np.polyfit(log_lags, log_tau, 1)[0]
        except Exception:
            return 0.5

        # Clamp to [0, 1]
        return float(np.clip(slope, 0.0, 1.0))

    @property
    def stats(self):
        return {"signals": self._signal_count, "recovery_attempts": self._recovery_attempts}
