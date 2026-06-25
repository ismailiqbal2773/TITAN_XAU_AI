"""
TITAN XAU AI — Sprint 9.5 Broker Intelligence + Quality Engine Tests
"""
from __future__ import annotations
import pytest
from dataclasses import dataclass

from titan.production.broker_intelligence import (
    BrokerIntelligenceLayer, BrokerInfo, SYMBOL_PATTERNS,
)
from titan.production.broker_quality_engine import (
    BrokerQualityEngine, BrokerQualityInput, BrokerQualityScore,
    score_to_band,
    BAND_INSTITUTIONAL, BAND_EXCELLENT, BAND_GOOD, BAND_AVERAGE, BAND_UNSAFE,
)
from titan.production.trade_journal import TradeJournal, EventType


@pytest.fixture
def journal(tmp_path):
    return TradeJournal(path=str(tmp_path / "bi.jsonl"), session_id="bi_test")


# ════════════════════════════════════════════════════════════════════════════
# BrokerIntelligenceLayer
# ════════════════════════════════════════════════════════════════════════════
class TestBrokerIntelligenceLayer:
    @dataclass
    class FakeAcc:
        company: str = "Exness Technologies Ltd"
        server: str = "Exness-MT5Real3"
        login: int = 44974666
        trade_mode: int = 2  # REAL
        leverage: int = 500
        balance: float = 10000.0
        margin_mode: int = 1  # RETAIL_HEDGING

    @dataclass
    class FakeSymbol:
        digits: int = 2
        point: float = 0.01
        spread: int = 35
        trade_contract_size: float = 100.0
        volume_min: float = 0.01
        volume_max: float = 100.0
        volume_step: float = 0.01
        trade_freeze_level: int = 0
        trade_stops_level: int = 0
        trade_tick_value: float = 1.0
        trade_tick_size: float = 0.01
        trade_mode: int = 1  # INSTANT
        filling_mode: int = 6  # IOC | RETURN

    def test_detect_from_account_info_exness(self, journal):
        layer = BrokerIntelligenceLayer(journal=journal)
        info = layer.detect_from_account_info(
            self.FakeAcc(), self.FakeSymbol()
        )
        assert info is not None
        assert info.broker_name == "Exness Technologies Ltd"
        assert info.server == "Exness-MT5Real3"
        assert info.account_type == "live"
        assert info.account_category == "retail"
        assert info.account_size == "standard"
        assert info.digits == 2
        assert info.point == 0.01
        assert info.hedging is True  # margin_mode=1 = RETAIL_HEDGING

    def test_detect_demo_account(self, journal):
        layer = BrokerIntelligenceLayer(journal=journal)
        acc = self.FakeAcc(trade_mode=0)  # DEMO
        info = layer.detect_from_account_info(acc, self.FakeSymbol())
        assert info.account_type == "demo"
        assert info.is_demo is True

    def test_detect_ftmo_prop(self, journal):
        layer = BrokerIntelligenceLayer(journal=journal)
        acc = self.FakeAcc(company="FTMO Broker", server="FTMO-Server")
        info = layer.detect_from_account_info(acc, self.FakeSymbol())
        assert info.account_category == "prop"
        assert info.is_prop is True

    def test_detect_fundednext_prop(self, journal):
        layer = BrokerIntelligenceLayer(journal=journal)
        acc = self.FakeAcc(company="FundedNext Technologies", server="FundedNext-Server")
        info = layer.detect_from_account_info(acc, self.FakeSymbol())
        assert info.is_prop is True

    def test_detect_cent_account(self, journal):
        layer = BrokerIntelligenceLayer(journal=journal)
        acc = self.FakeAcc(leverage=1000, balance=2_000_000)
        info = layer.detect_from_account_info(acc, self.FakeSymbol())
        assert info.account_size == "cent"

    def test_detect_ecn_broker(self, journal):
        layer = BrokerIntelligenceLayer(journal=journal)
        acc = self.FakeAcc(server="ICMarkets-ECN")
        info = layer.detect_from_account_info(acc, self.FakeSymbol())
        assert info.account_spread_type == "ecn"
        assert info.is_ecn is True

    def test_detect_raw_broker(self, journal):
        layer = BrokerIntelligenceLayer(journal=journal)
        acc = self.FakeAcc(server="ICMarkets-Raw")
        info = layer.detect_from_account_info(acc, self.FakeSymbol())
        assert info.account_spread_type == "raw"

    def test_detect_none_returns_none(self, journal):
        layer = BrokerIntelligenceLayer(journal=journal)
        info = layer.detect_from_account_info(None, None)
        assert info is None

    def test_detect_journals_broker_detected(self, journal):
        layer = BrokerIntelligenceLayer(journal=journal)
        layer.detect_from_account_info(self.FakeAcc(), self.FakeSymbol())
        records = journal.read_all()
        detected = [r for r in records if r.get("event_type") == EventType.BROKER_DETECTED.value]
        assert len(detected) == 1
        assert "broker_name" in detected[0]["data"]

    def test_symbol_candidates_exness(self, journal):
        layer = BrokerIntelligenceLayer(journal=journal)
        candidates = layer._symbol_candidates("XAUUSD", self.FakeAcc())
        # Should include XAUUSD + common suffixes + Exness-specific
        assert "XAUUSD" in candidates
        assert "XAUUSD.m" in candidates
        assert "XAUUSD.r" in candidates

    def test_detection_count(self, journal):
        layer = BrokerIntelligenceLayer(journal=journal)
        for _ in range(3):
            layer.detect_from_account_info(self.FakeAcc(), self.FakeSymbol())
        assert layer.detection_count == 3


# ════════════════════════════════════════════════════════════════════════════
# BrokerQualityEngine
# ════════════════════════════════════════════════════════════════════════════
class TestBrokerQualityEngine:
    @pytest.fixture
    def engine(self, journal):
        return BrokerQualityEngine(journal=journal)

    def test_perfect_inputs_yield_high_score(self, engine):
        inp = BrokerQualityInput(
            spread_usd=0.10, spread_mean_usd=0.10, spread_std_usd=0.01,
            slippage_mean_pips=0, latency_mean_ms=20,
            connection_uptime_pct=100, symbol_health=100,
        )
        result = engine.evaluate(inp)
        assert result.score >= 95
        assert result.band == BAND_INSTITUTIONAL

    def test_terrible_inputs_yield_low_score(self, engine):
        inp = BrokerQualityInput(
            spread_usd=5.0, spread_mean_usd=5.0, spread_std_usd=2.0,
            spread_spike_count=15, slippage_mean_pips=25,
            requote_rate=0.25, rejection_rate=0.25,
            latency_mean_ms=1500, gap_count=8,
            connection_uptime_pct=70, symbol_health=40,
        )
        result = engine.evaluate(inp)
        assert result.score < 60
        assert result.band == BAND_UNSAFE

    def test_score_bands(self):
        assert score_to_band(95) == BAND_INSTITUTIONAL
        assert score_to_band(85) == BAND_EXCELLENT
        assert score_to_band(75) == BAND_GOOD
        assert score_to_band(60) == BAND_AVERAGE
        assert score_to_band(50) == BAND_UNSAFE

    def test_score_journaled(self, engine, journal):
        engine.evaluate(BrokerQualityInput())
        records = journal.read_all()
        scored = [r for r in records if r.get("event_type") == EventType.BROKER_SCORE_UPDATED.value]
        assert len(scored) == 1

    def test_score_always_in_0_100(self, engine):
        # Extreme inputs
        for _ in range(10):
            inp = BrokerQualityInput(
                spread_mean_usd=-1, slippage_mean_pips=-5,
                latency_mean_ms=-100, connection_uptime_pct=200,
            )
            result = engine.evaluate(inp)
            assert 0.0 <= result.score <= 100.0

    def test_history_tracked(self, engine):
        for i in range(5):
            engine.evaluate(BrokerQualityInput(spread_mean_usd=float(i)))
        assert len(engine.score_history) == 5

    def test_12_components_computed(self, engine):
        result = engine.evaluate(BrokerQualityInput())
        assert len(result.components) == 12
        # All components in 0-100
        for v in result.components.values():
            assert 0.0 <= v <= 100.0

    def test_spread_affects_score(self, engine):
        good = engine.evaluate(BrokerQualityInput(spread_mean_usd=0.10))
        engine._history.clear()  # reset
        bad = engine.evaluate(BrokerQualityInput(spread_mean_usd=3.0))
        assert good.score > bad.score

    def test_latency_affects_score(self, engine):
        fast = engine.evaluate(BrokerQualityInput(latency_mean_ms=20))
        engine._history.clear()
        slow = engine.evaluate(BrokerQualityInput(latency_mean_ms=800))
        assert fast.score > slow.score

    def test_rejection_rate_affects_score(self, engine):
        clean = engine.evaluate(BrokerQualityInput(rejection_rate=0.0))
        engine._history.clear()
        rejected = engine.evaluate(BrokerQualityInput(rejection_rate=0.15))
        assert clean.score > rejected.score
