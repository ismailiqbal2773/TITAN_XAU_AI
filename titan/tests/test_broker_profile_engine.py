"""
TITAN XAU AI — BrokerProfileEngine unit tests (Sprint 9.9.3.45.8.4)
"""
from __future__ import annotations
from pathlib import Path

import pytest
import yaml

from titan.production.broker_profile_engine import (
    BrokerProfileEngine,
    BrokerProfile,
    SymbolSpec,
    ValidationResult,
    SAFETY_FLAGS,
)


# ─── Test fixtures ─────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parents[2]
BROKER_PROFILES_YAML = REPO_ROOT / "config" / "broker_profiles.yaml"


@pytest.fixture
def engine() -> BrokerProfileEngine:
    return BrokerProfileEngine(BROKER_PROFILES_YAML)


@pytest.fixture
def tmp_engine(tmp_path: Path) -> BrokerProfileEngine:
    """Engine backed by a small in-process YAML for deterministic tests."""
    yaml_doc = {
        "brokers": {
            "test_broker": {
                "broker_id": "test_broker",
                "name": "Test Broker",
                "server": "Test-Server",
                "account_type": "demo",
                "typical_spread_xauusd": 0.30,
                "max_spread_xauusd": 0.45,
                "commission_per_lot_round_turn": 5.0,
                "typical_slippage_xauusd": 0.02,
                "max_slippage_xauusd": 0.08,
                "swap_long_xauusd_per_lot_per_night": -3.0,
                "swap_short_xauusd_per_lot_per_night": -1.0,
                "contract_size_xauusd": 100,
                "stops_level_points_xauusd": 30,
                "freeze_level_points_xauusd": 0,
                "filling_mode": "ORDER_FILLING_IOC",
                "margin_currency": "USD",
                "min_lot": 0.01,
                "max_lot": 50.0,
                "lot_step": 0.01,
                "leverage_options": [50, 100],
                "symbol_suffixes": {"XAUUSD": ".c"},
            },
            "cent_broker": {
                "broker_id": "cent_broker",
                "name": "Cent Broker",
                "server": "Cent-Server",
                "account_type": "demo",
                "typical_spread_xauusd": 0.25,
                "max_spread_xauusd": 0.40,
                "commission_per_lot_round_turn": 0.0,
                "typical_slippage_xauusd": 0.01,
                "max_slippage_xauusd": 0.06,
                "contract_size_xauusd": 100,
                "stops_level_points_xauusd": 20,
                "freeze_level_points_xauusd": 0,
                "filling_mode": "ORDER_FILLING_FOK",
                "margin_currency": "USD",
                "min_lot": 0.01,
                "max_lot": 100.0,
                "lot_step": 0.01,
                "leverage_options": [100, 200],
            },
        }
    }
    yaml_path = tmp_path / "broker_profiles.yaml"
    yaml_path.write_text(yaml.safe_dump(yaml_doc), encoding="utf-8")
    return BrokerProfileEngine(yaml_path)


# ─── Tests ──────────────────────────────────────────────────────────────────
class TestBrokerProfileEngineLoading:
    def test_loads_real_broker_profiles_yaml(self, engine: BrokerProfileEngine):
        """The shipped config/broker_profiles.yaml must load."""
        assert engine.has_broker("metaquotes_demo")
        assert engine.has_broker("ic_markets_standard")
        assert engine.has_broker("ftmo_prop")
        assert engine.has_broker("institutional_ecn")

    def test_list_brokers_returns_sorted_ids(self, engine: BrokerProfileEngine):
        ids = engine.list_brokers()
        assert ids == sorted(ids)
        assert len(ids) >= 4

    def test_missing_yaml_raises_filenotfound(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            BrokerProfileEngine(tmp_path / "nonexistent.yaml")

    def test_unknown_broker_raises_keyerror(self, engine: BrokerProfileEngine):
        with pytest.raises(KeyError):
            engine.get_broker_profile("does_not_exist")


class TestBrokerProfileFields:
    def test_get_broker_profile_returns_typed_dataclass(self, engine: BrokerProfileEngine):
        profile = engine.get_broker_profile("metaquotes_demo")
        assert isinstance(profile, BrokerProfile)
        assert profile.broker_id == "metaquotes_demo"
        assert profile.server == "MetaQuotes-Demo"
        assert profile.account_type == "demo"
        assert profile.contract_size_xauusd == 100
        assert profile.min_lot == 0.01
        assert profile.max_lot == 100.0
        assert profile.lot_step == 0.01
        assert profile.filling_mode == "ORDER_FILLING_IOC"

    def test_profile_safety_flags_all_true(self, engine: BrokerProfileEngine):
        """Every shipped profile must enforce all four safety flags."""
        for broker_id in engine.list_brokers():
            profile = engine.get_broker_profile(broker_id)
            assert profile.no_martingale is True, f"{broker_id} no_martingale=False"
            assert profile.no_grid is True, f"{broker_id} no_grid=False"
            assert profile.no_averaging is True, f"{broker_id} no_averaging=False"
            assert profile.no_loss_based_lot_multiplier is True, (
                f"{broker_id} no_loss_based_lot_multiplier=False"
            )

    def test_safety_audit_returns_all_brokers(self, engine: BrokerProfileEngine):
        audit = engine.safety_audit()
        assert set(audit.keys()) == set(engine.list_brokers())
        for broker_id, flags in audit.items():
            assert flags["no_martingale"] is True
            assert flags["no_grid"] is True
            assert flags["no_averaging"] is True
            assert flags["no_loss_based_lot_multiplier"] is True

    def test_yaml_overriding_safety_flag_is_force_corrected(
        self, tmp_path: Path
    ):
        """If YAML maliciously sets no_martingale=False, engine must override."""
        yaml_doc = {
            "brokers": {
                "bad_broker": {
                    "broker_id": "bad_broker",
                    "name": "Bad Broker",
                    "server": "Bad-Server",
                    "no_martingale": False,           # should be corrected to True
                    "no_grid": False,                 # should be corrected to True
                    "no_averaging": False,            # should be corrected to True
                    "no_loss_based_lot_multiplier": False,  # corrected to True
                }
            }
        }
        yaml_path = tmp_path / "bad_brokers.yaml"
        yaml_path.write_text(yaml.safe_dump(yaml_doc), encoding="utf-8")
        eng = BrokerProfileEngine(yaml_path)
        profile = eng.get_broker_profile("bad_broker")
        assert profile.no_martingale is True
        assert profile.no_grid is True
        assert profile.no_averaging is True
        assert profile.no_loss_based_lot_multiplier is True


class TestSymbolSpec:
    def test_get_symbol_spec_returns_xauusd_defaults(self, engine: BrokerProfileEngine):
        spec = engine.get_symbol_spec("XAUUSD", "metaquotes_demo")
        assert isinstance(spec, SymbolSpec)
        assert spec.symbol == "XAUUSD"
        assert spec.broker_symbol == "XAUUSD"
        assert spec.contract_size == 100
        assert spec.min_lot == 0.01
        assert spec.max_lot == 100.0
        assert spec.lot_step == 0.01
        assert spec.filling_mode == "ORDER_FILLING_IOC"
        assert spec.stop_level_points == 50

    def test_get_symbol_spec_applies_suffix(self, tmp_engine: BrokerProfileEngine):
        """The test_broker profile declares a '.c' suffix for XAUUSD."""
        spec = tmp_engine.get_symbol_spec("XAUUSD", "test_broker")
        assert spec.symbol == "XAUUSD"
        assert spec.broker_symbol == "XAUUSD.c"

    def test_get_symbol_spec_strips_incoming_suffix(self, tmp_engine: BrokerProfileEngine):
        """Caller can pass an already-suffixed symbol — engine canonicalizes first."""
        spec = tmp_engine.get_symbol_spec("XAUUSD.r", "test_broker")
        assert spec.symbol == "XAUUSD"
        # broker_symbol should still be the test_broker's declared suffix.
        assert spec.broker_symbol == "XAUUSD.c"

    def test_canonicalize_symbol_handles_common_variants(self, engine: BrokerProfileEngine):
        assert engine.canonicalize_symbol("XAUUSD") == "XAUUSD"
        assert engine.canonicalize_symbol("XAUUSD.c") == "XAUUSD"
        assert engine.canonicalize_symbol("XAUUSD.m") == "XAUUSD"
        assert engine.canonicalize_symbol("XAUUSD.r") == "XAUUSD"
        assert engine.canonicalize_symbol("XAUUSD.raw") == "XAUUSD"
        assert engine.canonicalize_symbol("m.XAUUSD") == "XAUUSD"
        assert engine.canonicalize_symbol("xauusd.ecn") == "XAUUSD"

    def test_canonicalize_symbol_rejects_empty(self, engine: BrokerProfileEngine):
        with pytest.raises(ValueError):
            engine.canonicalize_symbol("")

    def test_resolve_broker_symbol_returns_canonical_when_no_suffix(
        self, engine: BrokerProfileEngine
    ):
        assert engine.resolve_broker_symbol("XAUUSD", "metaquotes_demo") == "XAUUSD"

    def test_resolve_broker_symbol_applies_declared_suffix(
        self, tmp_engine: BrokerProfileEngine
    ):
        assert tmp_engine.resolve_broker_symbol("XAUUSD", "test_broker") == "XAUUSD.c"


class TestSpreadValidation:
    def test_validate_spread_pass_when_within_limit(self, engine: BrokerProfileEngine):
        result = engine.validate_spread("metaquotes_demo", spread=0.32)
        assert isinstance(result, ValidationResult)
        assert result.ok is True
        assert result.verdict == "PASS"
        assert result.limit == 0.50

    def test_validate_spread_block_when_exceeds_limit(self, engine: BrokerProfileEngine):
        result = engine.validate_spread("metaquotes_demo", spread=0.75)
        assert result.ok is False
        assert result.verdict == "BLOCK"
        assert "exceeds max_spread" in result.reason

    def test_validate_spread_block_when_negative(self, engine: BrokerProfileEngine):
        result = engine.validate_spread("metaquotes_demo", spread=-0.10)
        assert result.ok is False
        assert result.verdict == "BLOCK"
        assert "Negative spread" in result.reason

    def test_validate_spread_pass_at_exact_limit(self, engine: BrokerProfileEngine):
        result = engine.validate_spread("metaquotes_demo", spread=0.50)
        assert result.ok is True
        assert result.verdict == "PASS"


class TestSlippageValidation:
    def test_validate_slippage_pass_when_within_limit(self, engine: BrokerProfileEngine):
        result = engine.validate_slippage("metaquotes_demo", slippage=0.05)
        assert result.ok is True
        assert result.verdict == "PASS"
        assert result.limit == 0.10

    def test_validate_slippage_reject_when_exceeds_limit(self, engine: BrokerProfileEngine):
        result = engine.validate_slippage("metaquotes_demo", slippage=0.20)
        assert result.ok is False
        assert result.verdict == "REJECT"

    def test_validate_slippage_normalizes_negative_to_absolute(
        self, engine: BrokerProfileEngine
    ):
        """Slippage sign is normalized by the engine — abs value used."""
        result = engine.validate_slippage("metaquotes_demo", slippage=-0.05)
        assert result.ok is True
        assert result.actual == 0.05
        assert result.verdict == "PASS"

    def test_validate_slippage_pass_at_exact_limit(self, engine: BrokerProfileEngine):
        result = engine.validate_slippage("metaquotes_demo", slippage=0.10)
        assert result.ok is True
        assert result.verdict == "PASS"


class TestSafetyFlagsConstant:
    def test_safety_flags_constant_matches_expected(self):
        assert SAFETY_FLAGS == {
            "no_martingale": True,
            "no_grid": True,
            "no_averaging": True,
            "no_loss_based_lot_multiplier": True,
        }


class TestProfileIntrospection:
    def test_all_profiles_returns_dict_copy(self, engine: BrokerProfileEngine):
        all_profs = engine.all_profiles()
        assert isinstance(all_profs, dict)
        assert len(all_profs) == len(engine.list_brokers())
        # Mutating the returned dict must not affect the engine's state.
        all_profs.clear()
        assert len(engine.all_profiles()) > 0

    def test_profile_to_dict_round_trip(self, engine: BrokerProfileEngine):
        profile = engine.get_broker_profile("ftmo_prop")
        d = profile.to_dict()
        assert d["broker_id"] == "ftmo_prop"
        assert d["name"] == "FTMO"
        assert d["no_martingale"] is True
