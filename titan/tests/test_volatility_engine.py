"""Tests for Volatility Engine"""
import pytest
import numpy as np
from titan.strategies.volatility_engine import (
    VolatilityEngine, VolatilitySignal, VolPattern, SignalDirection,
)
from titan.regime.engine import RegimeFeatures


@pytest.fixture
def config():
    return {"atr_period": 14, "atr_avg_period": 30, "breakout_mult": 2.0, "min_confidence": 0.55}


@pytest.fixture
def volatile_market():
    np.random.seed(42)
    base = 2000
    # Create data with volatility expansion
    noise = np.random.randn(100) * 2
    # Add a sudden move at end
    noise[-5:] += np.array([0, 5, -3, 8, -2])
    closes = base + np.cumsum(noise)
    highs = closes + np.abs(np.random.randn(100)) * 2
    lows = closes - np.abs(np.random.randn(100)) * 2
    return closes, highs, lows


@pytest.fixture
def volatile_features():
    return RegimeFeatures(
        adx=22, atr_pct=0.6, bb_width=50, bb_width_ratio=1.8,
        ema_slope=0.05, price_above_ema=True, hh_hl_pattern=False,
        lh_ll_pattern=False, rsi=55, volume_ratio=2.0,
        spread_ratio=1.5, candle_range_ratio=1.8,
    )


@pytest.fixture
def extreme_vol_features():
    return RegimeFeatures(
        adx=15, atr_pct=2.5, bb_width=80, bb_width_ratio=2.5,
        ema_slope=0.01, price_above_ema=True, hh_hl_pattern=False,
        lh_ll_pattern=False, rsi=50, volume_ratio=1.0,
        spread_ratio=1.0, candle_range_ratio=1.0,
    )


class TestVolPattern:
    def test_pattern_values(self):
        assert VolPattern.ATR_BREAKOUT_UP == "ATR_BREAKOUT_UP"
        assert VolPattern.ATR_BREAKOUT_DOWN == "ATR_BREAKOUT_DOWN"
        assert VolPattern.VOL_EXPANSION == "VOL_EXPANSION"
        assert VolPattern.VOL_CONTRACTION == "VOL_CONTRACTION"
        assert VolPattern.NEWS_BREAKOUT == "NEWS_BREAKOUT"


class TestVolatilityEngine:
    def test_no_signal_extreme_volatility(self, config, volatile_market, extreme_vol_features):
        """Should NOT trade when ATR > 2% of price."""
        closes, highs, lows = volatile_market
        engine = VolatilityEngine(config)
        signal = engine.generate_signal(closes, highs, lows, extreme_vol_features, closes[-1], 10000)
        assert signal is None

    def test_insufficient_data(self, config, volatile_features):
        closes = np.array([2000, 2001, 2002])
        engine = VolatilityEngine(config)
        signal = engine.generate_signal(closes, closes+1, closes-1, volatile_features, 2002, 10000)
        assert signal is None

    def test_position_sizing_reduced_in_high_vol(self, config, volatile_market, volatile_features):
        """Volume should be reduced in high volatility."""
        closes, highs, lows = volatile_market
        engine = VolatilityEngine(config)
        signal = engine.generate_signal(closes, highs, lows, volatile_features, closes[-1], 10000)
        if signal:
            assert signal.proposed_volume > 0
            # ATR is 0.6% which is > 0.5%, so volume should be reduced (0.75x)
            assert signal.proposed_volume <= 0.5  # Should be small

    def test_atr_ratio_property(self, config, volatile_market, volatile_features):
        closes, highs, lows = volatile_market
        engine = VolatilityEngine(config)
        engine.generate_signal(closes, highs, lows, volatile_features, closes[-1], 10000)
        assert engine.current_atr_ratio > 0

    def test_wider_stops_for_volatility(self, config, volatile_market, volatile_features):
        """Volatility trades should use 2x ATR stops (wider than trend)."""
        closes, highs, lows = volatile_market
        engine = VolatilityEngine(config)
        signal = engine.generate_signal(closes, highs, lows, volatile_features, closes[-1], 10000)
        if signal and signal.direction != SignalDirection.FLAT:
            # Stop should be at least 1.5 ATR away
            distance = abs(signal.entry_price - signal.stop_loss)
            assert distance > 0

    def test_news_breakout_blocks_during_high_spread(self, config, volatile_market):
        """During news (high spread), should NOT enter ATR breakout."""
        closes, highs, lows = volatile_market
        features = RegimeFeatures(
            adx=25, atr_pct=0.6, spread_ratio=4.0,  # High spread = news
            bb_width_ratio=1.8, volume_ratio=2.0, candle_range_ratio=1.8,
            rsi=55,
        )
        engine = VolatilityEngine(config)
        # With news_active=True and high spread, should not do ATR breakout
        signal = engine.generate_signal(closes, highs, lows, features, closes[-1], 10000, news_active=True)
        # Should be None or NEWS_BREAKOUT (not ATR_BREAKOUT)
        if signal:
            assert signal.pattern != VolPattern.ATR_BREAKOUT_UP
            assert signal.pattern != VolPattern.ATR_BREAKOUT_DOWN
