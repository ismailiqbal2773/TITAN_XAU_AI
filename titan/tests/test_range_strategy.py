"""Tests for Range Strategy Engine"""
import pytest
import numpy as np
from titan.strategies.range_engine import (
    RangeStrategyEngine, RangeSignal, RangePattern, SignalDirection,
)
from titan.regime.engine import RegimeFeatures


@pytest.fixture
def config():
    return {"bb_period": 20, "bb_std": 2.0, "rsi_period": 14, "min_confidence": 0.55}


@pytest.fixture
def ranging_market():
    np.random.seed(42)
    base = 2000
    noise = np.random.randn(100) * 3
    closes = base + noise
    highs = closes + 1
    lows = closes - 1
    return closes, highs, lows


@pytest.fixture
def range_features_oversold():
    return RegimeFeatures(
        adx=15, atr_pct=0.2, bb_width=15, bb_width_ratio=0.6,
        ema_slope=0.01, price_above_ema=True, hh_hl_pattern=False,
        lh_ll_pattern=False, rsi=25, volume_ratio=0.8,
        spread_ratio=1.0, candle_range_ratio=0.8,
    )


@pytest.fixture
def range_features_overbought():
    return RegimeFeatures(
        adx=15, atr_pct=0.2, bb_width=15, bb_width_ratio=0.6,
        ema_slope=0.01, price_above_ema=True, hh_hl_pattern=False,
        lh_ll_pattern=False, rsi=75, volume_ratio=0.8,
        spread_ratio=1.0, candle_range_ratio=0.8,
    )


class TestRangePattern:
    def test_pattern_values(self):
        assert RangePattern.BB_UPPER_TOUCH == "BB_UPPER_TOUCH"
        assert RangePattern.BB_LOWER_TOUCH == "BB_LOWER_TOUCH"
        assert RangePattern.RSI_OVERBOUGHT == "RSI_OVERBOUGHT"
        assert RangePattern.RSI_OVERSOLD == "RSI_OVERSOLD"
        assert RangePattern.MEAN_REVERT == "MEAN_REVERT"


class TestRangeStrategyEngine:
    def test_no_signal_in_strong_trend(self, config, ranging_market):
        closes, highs, lows = ranging_market
        features = RegimeFeatures(adx=35, rsi=50)  # Strong trend ADX
        engine = RangeStrategyEngine(config)
        signal = engine.generate_signal(closes, highs, lows, features, closes[-1], 10000)
        assert signal is None

    def test_insufficient_data(self, config, range_features_oversold):
        closes = np.array([2000, 2001, 2002])
        engine = RangeStrategyEngine(config)
        signal = engine.generate_signal(closes, closes+1, closes-1, range_features_oversold, 2002, 10000)
        assert signal is None

    def test_smart_recovery_reset_on_win(self, config):
        engine = RangeStrategyEngine(config)
        engine.on_trade_closed(won=False)
        assert engine.should_attempt_recovery is True
        engine.on_trade_closed(won=True)
        assert engine.should_attempt_recovery is True
        assert engine.stats["recovery_attempts"] == 0

    def test_smart_recovery_max_attempts(self, config):
        engine = RangeStrategyEngine(config)
        engine.on_trade_closed(won=False)
        engine.on_trade_closed(won=False)
        assert engine.should_attempt_recovery is False  # Max 2 attempts

    def test_anti_martingale_same_volume(self, config, ranging_market, range_features_oversold):
        """Recovery should NOT increase volume (anti-martingale)."""
        closes, highs, lows = ranging_market
        engine = RangeStrategyEngine(config)
        engine.on_trade_closed(won=False)  # First loss
        signal1 = engine.generate_signal(closes, highs, lows, range_features_oversold, closes[-1], 10000)

        engine.on_trade_closed(won=False)  # Second loss
        signal2 = engine.generate_signal(closes, highs, lows, range_features_oversold, closes[-1], 10000)

        # Recovery volume should NOT be larger than initial
        if signal1 and signal2:
            assert signal2.proposed_volume <= signal1.proposed_volume * 1.01  # Allow rounding
