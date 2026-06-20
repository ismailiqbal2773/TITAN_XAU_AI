"""
TITAN XAU AI — Tests for Market Data Engine
Tests for Tick, RollingWindow, DataQualityValidator, SpreadMonitor.
"""
import pytest
import numpy as np
from titan.market_data.engine import (
    Tick,
    RollingWindow,
    DataQualityValidator,
    DataQualityResult,
    SpreadMonitor,
)


@pytest.fixture
def config():
    return {
        "market_data": {
            "tick_cache_size": 1000,
            "quality_gates": {
                "max_gap_seconds": 5,
                "max_spread_usd": 5.0,
            },
        },
    }


@pytest.fixture
def valid_tick():
    return Tick(
        symbol="XAUUSD", bid=2000.00, ask=2000.18,
        spread=0.18, time=1700000000, time_msc=1700000000000,
        volume=100, flags=2,
    )


class TestTick:
    def test_mid_price(self, valid_tick):
        assert valid_tick.mid == pytest.approx(2000.09, abs=0.001)

    def test_is_valid(self, valid_tick):
        assert valid_tick.is_valid is True

    def test_invalid_zero_bid(self):
        t = Tick("XAUUSD", 0, 2000, 2000, 1700000000, 1700000000000, 100, 2)
        assert t.is_valid is False

    def test_invalid_crossed_quotes(self):
        t = Tick("XAUUSD", 2001, 2000, -1, 1700000000, 1700000000000, 100, 2)
        assert t.is_valid is False


class TestRollingWindow:
    def test_push_and_size(self):
        w = RollingWindow(5)
        for i in range(3):
            w.push(float(i))
        assert w.size == 3

    def test_eviction(self):
        w = RollingWindow(5)
        for i in range(10):
            w.push(float(i))
        assert w.size == 5
        arr = w.to_array()
        assert arr[0] == 5.0  # oldest retained
        assert arr[-1] == 9.0  # newest

    def test_mean(self):
        w = RollingWindow(100)
        for i in range(10):
            w.push(float(i + 1))
        assert w.mean() == pytest.approx(5.5)

    def test_std(self):
        w = RollingWindow(100)
        for i in range(10):
            w.push(float(i + 1))
        assert w.std() > 0

    def test_percentile(self):
        w = RollingWindow(100)
        for i in range(100):
            w.push(float(i + 1))
        assert w.percentile(50) == pytest.approx(50.5, abs=1.0)
        assert w.percentile(90) > 80

    def test_empty_window(self):
        w = RollingWindow(10)
        assert w.mean() == 0.0
        assert w.std() == 0.0
        assert w.percentile(50) == 0.0


class TestDataQualityValidator:
    def test_valid_tick_passes(self, config, valid_tick):
        v = DataQualityValidator(config)
        result = v.validate(valid_tick)
        assert result.passed is True

    def test_zero_bid_rejected(self, config):
        v = DataQualityValidator(config)
        tick = Tick("XAU", 0, 2000, 2000, 1700000000, 1700000000000, 100, 2)
        result = v.validate(tick)
        assert result.passed is False
        assert result.gate_name in ("OUT-001", "BIDASK-002")  # Either gate fires

    def test_crossed_quotes_rejected(self, config):
        v = DataQualityValidator(config)
        tick = Tick("XAU", 2001, 2000, -1, 1700000000, 1700000000000, 100, 2)
        result = v.validate(tick)
        assert result.passed is False
        assert "BIDASK-001" in result.gate_name

    def test_excessive_spread_rejected(self, config):
        v = DataQualityValidator(config)
        tick = Tick("XAU", 2000, 2010, 10, 1700000000, 1700000000000, 100, 2)
        result = v.validate(tick)
        assert result.passed is False
        assert "BIDASK-002" in result.gate_name

    def test_timestamp_backwards_rejected(self, config, valid_tick):
        v = DataQualityValidator(config)
        v.validate(valid_tick)
        backwards = Tick("XAU", 2000, 2000.18, 0.18, 1699999999, 1699999999000, 100, 2)
        result = v.validate(backwards)
        assert result.passed is False
        assert "MONO-001" in result.gate_name

    def test_duplicate_tick_rejected(self, config, valid_tick):
        v = DataQualityValidator(config)
        v.validate(valid_tick)
        result = v.validate(valid_tick)  # Same tick again
        assert result.passed is False
        assert "MONO-002" in result.gate_name


class TestSpreadMonitor:
    def test_baseline_computation(self):
        m = SpreadMonitor(baseline_window=100)
        for i in range(50):
            tick = Tick("XAU", 2000, 2000.18, 0.18, 1700000000 + i, 1700000000000 + i*1000, 100, 2)
            m.on_tick(tick)
        assert m.baseline == pytest.approx(0.18, abs=0.01)

    def test_news_widening_detection(self):
        m = SpreadMonitor(baseline_window=100)
        # Normal spread ticks
        for i in range(50):
            tick = Tick("XAU", 2000, 2000.18, 0.18, 1700000000 + i, 1700000000000 + i*1000, 100, 2)
            m.on_tick(tick)
        assert m.is_news_widening is False

        # Widened spread (3x baseline = 0.54)
        wide_tick = Tick("XAU", 2000, 2000.60, 0.60, 1700000050, 1700000050000, 100, 2)
        m.on_tick(wide_tick)
        assert m.is_news_widening is True
