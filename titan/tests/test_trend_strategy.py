"""Tests for Trend Strategy Engine"""
import pytest
import numpy as np
from titan.strategies.trend_engine import (
    TrendStrategyEngine, TrendSignal, TrendPattern, SignalDirection,
)
from titan.regime.engine import RegimeFeatures


@pytest.fixture
def config():
    return {"ema_fast": 20, "ema_slow": 50, "adx_threshold": 25, "risk_reward": 2.0}


@pytest.fixture
def trending_market():
    np.random.seed(42)
    base = 2000
    trend = np.linspace(0, 50, 100)
    noise = np.random.randn(100) * 1
    closes = base + trend + noise
    highs = closes + np.abs(np.random.randn(100))
    lows = closes - np.abs(np.random.randn(100))
    return closes, highs, lows


@pytest.fixture
def trend_features():
    return RegimeFeatures(
        adx=35, atr_pct=0.4, bb_width=30, bb_width_ratio=1.0,
        ema_slope=0.15, price_above_ema=True, hh_hl_pattern=True,
        lh_ll_pattern=False, rsi=65, volume_ratio=1.2,
        spread_ratio=1.0, candle_range_ratio=1.0,
    )


@pytest.fixture
def downtrend_features():
    return RegimeFeatures(
        adx=35, atr_pct=0.4, bb_width=30, bb_width_ratio=1.0,
        ema_slope=-0.15, price_above_ema=False, hh_hl_pattern=False,
        lh_ll_pattern=True, rsi=35, volume_ratio=1.2,
        spread_ratio=1.0, candle_range_ratio=1.0,
    )


class TestTrendPattern:
    def test_pattern_values(self):
        assert TrendPattern.HH_HL == "HH_HL"
        assert TrendPattern.LH_LL == "LH_LL"
        assert TrendPattern.BREAKOUT == "BREAKOUT"
        assert TrendPattern.PULLBACK == "PULLBACK"
        assert TrendPattern.CONTINUATION == "CONTINUATION"


class TestTrendStrategyEngine:
    def test_signal_generation_uptrend(self, config, trending_market, trend_features):
        closes, highs, lows = trending_market
        engine = TrendStrategyEngine(config)
        signal = engine.generate_signal(closes, highs, lows, trend_features, closes[-1], 10000)
        assert signal is not None
        assert signal.direction == SignalDirection.LONG
        assert signal.stop_loss < signal.entry_price
        assert signal.take_profit > signal.entry_price
        assert signal.risk_reward_ratio > 0
        assert signal.proposed_volume > 0

    def test_no_signal_insufficient_data(self, config, trend_features):
        closes = np.array([2000, 2001, 2002])
        highs = closes + 1
        lows = closes - 1
        engine = TrendStrategyEngine(config)
        signal = engine.generate_signal(closes, highs, lows, trend_features, 2002, 10000)
        assert signal is None

    def test_confidence_in_range(self, config, trending_market, trend_features):
        closes, highs, lows = trending_market
        engine = TrendStrategyEngine(config)
        signal = engine.generate_signal(closes, highs, lows, trend_features, closes[-1], 10000)
        if signal:
            assert 0 <= signal.confidence <= 1.0

    def test_position_sizing(self, config, trending_market, trend_features):
        closes, highs, lows = trending_market
        engine = TrendStrategyEngine(config)
        signal = engine.generate_signal(closes, highs, lows, trend_features, closes[-1], 10000)
        if signal:
            assert signal.proposed_volume >= 0.01  # Minimum lot

    def test_downtrend_signal(self, config, trending_market, downtrend_features):
        closes, highs, lows = trending_market
        engine = TrendStrategyEngine(config)
        signal = engine.generate_signal(closes, highs, lows, downtrend_features, closes[-1], 10000)
        # May or may not generate, but if it does, should be SHORT
        if signal:
            assert signal.direction == SignalDirection.SHORT
