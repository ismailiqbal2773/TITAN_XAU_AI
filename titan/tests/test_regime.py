"""Tests for Regime Detection Engine"""
import pytest
import numpy as np
from titan.regime.engine import (
    RegimeDetector, Regime, RegimeFeatures, RegimeResult,
    FeatureExtractor, HMMRegimeModel, LogitRegimeModel, HeuristicRegimeModel,
)


@pytest.fixture
def trending_data():
    np.random.seed(42)
    base = 2000
    trend = np.linspace(0, 50, 100)
    noise = np.random.randn(100) * 2
    closes = base + trend + noise
    highs = closes + np.abs(np.random.randn(100)) * 1
    lows = closes - np.abs(np.random.randn(100)) * 1
    volumes = np.random.randint(50, 200, 100).astype(float)
    return closes, highs, lows, volumes


@pytest.fixture
def ranging_data():
    np.random.seed(42)
    base = 2000
    noise = np.random.randn(100) * 3
    closes = base + noise
    highs = closes + 1
    lows = closes - 1
    volumes = np.random.randint(50, 200, 100).astype(float)
    return closes, highs, lows, volumes


@pytest.fixture
def trend_features():
    return RegimeFeatures(
        adx=35, atr_pct=0.4, bb_width=30, bb_width_ratio=1.0,
        ema_slope=0.15, price_above_ema=True, hh_hl_pattern=True,
        lh_ll_pattern=False, rsi=65, volume_ratio=1.2,
        spread_ratio=1.0, candle_range_ratio=1.0,
    )


@pytest.fixture
def range_features():
    return RegimeFeatures(
        adx=15, atr_pct=0.2, bb_width=15, bb_width_ratio=0.6,
        ema_slope=0.01, price_above_ema=True, hh_hl_pattern=False,
        lh_ll_pattern=False, rsi=50, volume_ratio=0.8,
        spread_ratio=1.0, candle_range_ratio=0.8,
    )


@pytest.fixture
def volatile_features():
    return RegimeFeatures(
        adx=22, atr_pct=0.8, bb_width=50, bb_width_ratio=1.8,
        ema_slope=0.05, price_above_ema=True, hh_hl_pattern=False,
        lh_ll_pattern=False, rsi=55, volume_ratio=2.0,
        spread_ratio=1.5, candle_range_ratio=1.8,
    )


@pytest.fixture
def news_features():
    return RegimeFeatures(
        adx=20, atr_pct=0.6, bb_width=40, bb_width_ratio=1.4,
        ema_slope=0.02, price_above_ema=True, hh_hl_pattern=False,
        lh_ll_pattern=False, rsi=58, volume_ratio=3.0,
        spread_ratio=4.0, candle_range_ratio=2.5,
    )


class TestRegimeEnum:
    def test_regime_values(self):
        assert Regime.TREND == "TREND"
        assert Regime.RANGE == "RANGE"
        assert Regime.VOLATILE == "VOLATILE"
        assert Regime.NEWS == "NEWS"


class TestFeatureExtractor:
    def test_extract_from_trending_data(self, trending_data):
        closes, highs, lows, volumes = trending_data
        features = FeatureExtractor.extract(closes, highs, lows, volumes)
        assert features.adx > 0
        assert features.atr_pct > 0
        assert features.rsi > 0

    def test_extract_short_data_returns_defaults(self):
        closes = np.array([2000, 2001, 2002])
        features = FeatureExtractor.extract(closes, closes + 1, closes - 1, np.array([100, 100, 100]))
        assert features.adx == 0.0  # Default for insufficient data


class TestHMMModel:
    def test_trend_prediction(self, trend_features):
        model = HMMRegimeModel()
        vote = model.predict(trend_features)
        assert vote.model_name == "HMM"
        assert vote.regime in [Regime.TREND, Regime.RANGE, Regime.VOLATILE, Regime.NEWS]
        assert 0 <= vote.confidence <= 1.0

    def test_range_prediction(self, range_features):
        model = HMMRegimeModel()
        vote = model.predict(range_features)
        assert vote.model_name == "HMM"
        assert vote.confidence > 0


class TestLogitModel:
    def test_prediction(self, trend_features):
        model = LogitRegimeModel()
        vote = model.predict(trend_features)
        assert vote.model_name == "Logit"
        assert 0 <= vote.confidence <= 1.0

    def test_range_prediction(self, range_features):
        model = LogitRegimeModel()
        vote = model.predict(range_features)
        assert vote.model_name == "Logit"
        assert vote.regime in list(Regime)


class TestHeuristicModel:
    def test_trend_detected(self, trend_features):
        model = HeuristicRegimeModel()
        vote = model.predict(trend_features)
        assert vote.model_name == "Heuristic"
        assert vote.regime == Regime.TREND

    def test_range_detected(self, range_features):
        model = HeuristicRegimeModel()
        vote = model.predict(range_features)
        assert vote.model_name == "Heuristic"
        assert vote.regime == Regime.RANGE

    def test_volatile_detected(self, volatile_features):
        model = HeuristicRegimeModel()
        vote = model.predict(volatile_features)
        assert vote.regime == Regime.VOLATILE

    def test_news_detected(self, news_features):
        model = HeuristicRegimeModel()
        vote = model.predict(news_features)
        assert vote.regime == Regime.NEWS


class TestRegimeDetector:
    def test_trend_detection_consensus(self, trend_features):
        detector = RegimeDetector()
        result = detector.detect(trend_features)
        assert result.regime in [Regime.TREND, Regime.RANGE]
        assert len(result.votes) == 3
        assert 0 <= result.confidence <= 1.0
        assert result.evaluation_time_ms > 0

    def test_range_detection(self, range_features):
        detector = RegimeDetector()
        result = detector.detect(range_features)
        assert result.regime in [Regime.RANGE, Regime.TREND]
        assert len(result.votes) == 3

    def test_news_detection(self, news_features):
        detector = RegimeDetector()
        result = detector.detect(news_features)
        assert len(result.votes) == 3
        assert result.evaluation_time_ms < 100  # Fast evaluation

    def test_regime_persistence(self, trend_features):
        """Regime should not flip on every call — needs 2/3 + confidence."""
        detector = RegimeDetector()
        r1 = detector.detect(trend_features)
        r2 = detector.detect(trend_features)
        # Should be stable or same regime
        assert r2.regime == r1.regime or r2.transition_confidence < 1.0

    def test_current_regime_property(self, trend_features):
        detector = RegimeDetector()
        detector.detect(trend_features)
        assert detector.current_regime in list(Regime)
