"""
TITAN XAU AI — Tests for Broker Compatibility Engine
Tests that run without live MT5 connection (mock where needed).
"""
import pytest
from unittest.mock import Mock, MagicMock, patch
from titan.broker.engine import (
    BrokerCompatibilityEngine,
    BrokerId,
    MarginMode,
    BrokerProfile,
    SymbolInfo,
)


@pytest.fixture
def mock_config():
    return {
        "mt5": {"terminal_path": "", "login": 0, "password": "", "server": "", "timeout": 60000},
        "brokers": {
            "icmarkets": {
                "server_prefix": "ICMarkets", "symbol_suffix": ".c",
                "contract_size": 100, "min_lot": 0.01, "lot_step": 0.01,
                "leverage": 500, "margin_mode": "retail", "timezone": "EET",
            },
            "exness": {
                "server_prefix": "Exness", "symbol_suffix": "",
                "contract_size": 100, "min_lot": 0.01, "lot_step": 0.01,
                "leverage": 500, "margin_mode": "retail", "timezone": "EET",
            },
        },
        "symbols": {
            "primary": "XAUUSD",
            "alternate_names": ["XAUUSD", "XAUUSD.c", "GOLD"],
        },
    }


class TestBrokerId:
    def test_broker_id_values(self):
        assert BrokerId.EXNESS == "exness"
        assert BrokerId.ICMARKETS == "icmarkets"
        assert BrokerId.PEPPERSTONE == "pepperstone"
        assert BrokerId.TICKMILL == "tickmill"
        assert BrokerId.FP_MARKETS == "fp_markets"
        assert BrokerId.FUSION_MARKETS == "fusion_markets"
        assert BrokerId.UNKNOWN == "unknown"


class TestBrokerProfile:
    def test_profile_creation(self):
        p = BrokerProfile(
            broker_id=BrokerId.ICMARKETS,
            broker_name="IC Markets",
            server_name="ICMarketsSC-Live06",
            symbol_suffix=".c",
            contract_size=100,
            min_lot=0.01,
            lot_step=0.01,
            leverage=500,
            margin_mode=MarginMode.RETAIL,
            timezone="EET",
        )
        assert p.broker_id == BrokerId.ICMARKETS
        assert p.contract_size == 100
        assert p.symbol_suffix == ".c"

    def test_profile_defaults(self):
        p = BrokerProfile(
            broker_id=BrokerId.EXNESS,
            broker_name="Exness",
            server_name="Exness-Real",
            symbol_suffix="",
            contract_size=100,
            min_lot=0.01,
            lot_step=0.01,
            leverage=500,
            margin_mode=MarginMode.RETAIL,
            timezone="EET",
        )
        assert p.account_balance == 0.0
        assert p.account_currency == "USD"


class TestBrokerMatch:
    def test_match_exness(self, mock_config):
        engine = BrokerCompatibilityEngine.__new__(BrokerCompatibilityEngine)
        engine._config = mock_config
        result = engine._match_broker("Exness Technologies", "Exness-Real")
        assert result == BrokerId.EXNESS

    def test_match_icmarkets(self, mock_config):
        engine = BrokerCompatibilityEngine.__new__(BrokerCompatibilityEngine)
        engine._config = mock_config
        result = engine._match_broker("IC Markets", "ICMarketsSC-Live06")
        assert result == BrokerId.ICMARKETS

    def test_match_pepperstone(self, mock_config):
        engine = BrokerCompatibilityEngine.__new__(BrokerCompatibilityEngine)
        engine._config = mock_config
        result = engine._match_broker("Pepperstone", "Pepperstone-Live")
        assert result == BrokerId.PEPPERSTONE

    def test_match_tickmill(self, mock_config):
        engine = BrokerCompatibilityEngine.__new__(BrokerCompatibilityEngine)
        engine._config = mock_config
        result = engine._match_broker("Tickmill", "Tickmill-Live")
        assert result == BrokerId.TICKMILL

    def test_match_unknown(self, mock_config):
        engine = BrokerCompatibilityEngine.__new__(BrokerCompatibilityEngine)
        engine._config = mock_config
        result = engine._match_broker("Unknown Broker", "SomeServer")
        assert result == BrokerId.UNKNOWN
