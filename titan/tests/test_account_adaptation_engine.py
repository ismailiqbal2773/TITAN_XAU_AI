"""
TITAN XAU AI — AccountAdaptationEngine unit tests (Sprint 9.9.3.45.8.5)
"""
from __future__ import annotations

import pytest

from titan.production.account_adaptation_engine import (
    AccountAdaptationEngine,
    AccountFacts,
    AdaptationMode,
    AdaptationResult,
    AccountCurrency,
    LossBasedLotMultiplierForbidden,
    AccountAdaptationError,
    SAFETY_FLAGS,
)


# ─── Fixtures ───────────────────────────────────────────────────────────────
@pytest.fixture
def proof_engine() -> AccountAdaptationEngine:
    return AccountAdaptationEngine(
        mode=AdaptationMode.PROOF_FIXED_LOT,
        max_lot=0.01,
        min_lot=0.01,
        fixed_lot_for_proof=0.01,
    )


@pytest.fixture
def conservative_engine() -> AccountAdaptationEngine:
    return AccountAdaptationEngine(
        mode=AdaptationMode.CONSERVATIVE_DYNAMIC,
        max_lot=0.10,
        min_lot=0.01,
        risk_per_trade_pct=0.01,
        max_risk_per_trade_pct=0.02,
        max_margin_usage_pct=0.20,
        leverage_cap=100,
    )


@pytest.fixture
def prop_engine() -> AccountAdaptationEngine:
    return AccountAdaptationEngine(
        mode=AdaptationMode.PROP_FIRM_CONSERVATIVE,
        max_lot=0.05,
        min_lot=0.01,
        risk_per_trade_pct=0.005,
        max_risk_per_trade_pct=0.005,
    )


@pytest.fixture
def institutional_engine() -> AccountAdaptationEngine:
    return AccountAdaptationEngine(
        mode=AdaptationMode.INSTITUTIONAL_VOLATILITY_SCALED,
        max_lot=0.50,
        min_lot=0.01,
        risk_per_trade_pct=0.005,
        max_risk_per_trade_pct=0.005,
        volatility_scalar=0.80,
    )


# ─── Tests ──────────────────────────────────────────────────────────────────
class TestConstruction:
    def test_default_construction_uses_proof_mode(self):
        eng = AccountAdaptationEngine()
        assert eng.mode == AdaptationMode.PROOF_FIXED_LOT
        assert eng.no_martingale is True
        assert eng.no_grid is True
        assert eng.no_averaging is True
        assert eng.no_loss_based_lot_multiplier is True

    def test_invalid_max_lot_raises(self):
        with pytest.raises(ValueError):
            AccountAdaptationEngine(max_lot=0.0)

    def test_invalid_min_lot_raises(self):
        with pytest.raises(ValueError):
            AccountAdaptationEngine(min_lot=0.0)

    def test_min_lot_exceeds_max_lot_raises(self):
        with pytest.raises(ValueError):
            AccountAdaptationEngine(min_lot=0.10, max_lot=0.01)

    def test_invalid_risk_pct_raises(self):
        with pytest.raises(ValueError):
            AccountAdaptationEngine(risk_per_trade_pct=1.5)

    def test_max_risk_pct_below_risk_pct_raises(self):
        with pytest.raises(ValueError):
            AccountAdaptationEngine(
                risk_per_trade_pct=0.02, max_risk_per_trade_pct=0.01
            )

    def test_invalid_volatility_scalar_raises(self):
        with pytest.raises(ValueError):
            AccountAdaptationEngine(
                mode=AdaptationMode.INSTITUTIONAL_VOLATILITY_SCALED,
                volatility_scalar=1.5,
            )


class TestSafetyFlags:
    def test_safety_flags_property_returns_all_true(self, proof_engine):
        flags = proof_engine.safety_flags
        assert flags == SAFETY_FLAGS
        for k, v in flags.items():
            assert v is True, f"{k} should be True"

    def test_set_loss_based_lot_multiplier_raises(self, proof_engine):
        with pytest.raises(LossBasedLotMultiplierForbidden):
            proof_engine.set_loss_based_lot_multiplier(multiplier=2.0)

    def test_adjust_lot_after_loss_raises(self, proof_engine):
        with pytest.raises(LossBasedLotMultiplierForbidden):
            proof_engine.adjust_lot_after_loss(loss_count=3)

    def test_adjust_lot_after_win_raises(self, conservative_engine):
        """Win-based sizing is also forbidden (martingale/anti-martingale are equivalent)."""
        with pytest.raises(LossBasedLotMultiplierForbidden):
            conservative_engine.adjust_lot_after_win(win_count=3)


class TestProofMode:
    def test_proof_mode_uses_fixed_lot(self, proof_engine):
        facts = AccountFacts(balance=10000.0, equity=10000.0, currency="USD", leverage=100)
        result = proof_engine.adapt(facts)
        assert isinstance(result, AdaptationResult)
        assert result.mode == AdaptationMode.PROOF_FIXED_LOT
        assert result.max_lot == 0.01
        assert result.risk_per_trade_pct == 0.0
        assert result.allow_new_entries is True
        assert result.is_cent_account is False

    def test_proof_mode_ignores_balance_for_lot(self, proof_engine):
        """Even huge balance → still 0.01 in proof mode."""
        facts = AccountFacts(balance=1_000_000.0, equity=1_000_000.0, currency="USD")
        result = proof_engine.adapt(facts)
        assert result.max_lot == 0.01


class TestConservativeDynamic:
    def test_conservative_uses_balance_based_cap(self, conservative_engine):
        facts = AccountFacts(balance=10000.0, equity=10000.0, currency="USD", leverage=100)
        result = conservative_engine.adapt(facts)
        assert result.mode == AdaptationMode.CONSERVATIVE_DYNAMIC
        assert result.risk_per_trade_pct == 0.01
        assert result.max_lot >= result.min_lot
        assert result.max_lot <= conservative_engine.max_lot
        assert result.dollar_balance == 10000.0
        assert result.dollar_equity == 10000.0

    def test_conservative_zero_equity_blocks_entries(self, conservative_engine):
        facts = AccountFacts(balance=0.0, equity=0.0, currency="USD", leverage=100)
        result = conservative_engine.adapt(facts)
        assert result.allow_new_entries is False


class TestPropFirmConservative:
    def test_prop_firm_caps_risk_at_max(self, prop_engine):
        facts = AccountFacts(balance=10000.0, equity=10000.0, currency="USD", leverage=100)
        result = prop_engine.adapt(facts)
        assert result.mode == AdaptationMode.PROP_FIRM_CONSERVATIVE
        # risk_per_trade_pct should be min(0.005, 0.005) = 0.005
        assert result.risk_per_trade_pct == 0.005
        assert result.max_lot <= prop_engine.max_lot


class TestInstitutionalVolatilityScaled:
    def test_institutional_uses_volatility_scalar(self, institutional_engine):
        facts = AccountFacts(balance=50000.0, equity=50000.0, currency="USD", leverage=100)
        result = institutional_engine.adapt(facts, volatility_scalar=0.5)
        assert result.mode == AdaptationMode.INSTITUTIONAL_VOLATILITY_SCALED
        assert result.volatility_scalar == 0.5
        assert result.max_lot <= institutional_engine.max_lot

    def test_institutional_zero_scalar_blocks_entries(self, institutional_engine):
        facts = AccountFacts(balance=50000.0, equity=50000.0, currency="USD", leverage=100)
        result = institutional_engine.adapt(facts, volatility_scalar=0.0)
        # max_lot will be 0 after scaling → clamped to min_lot
        assert result.max_lot == institutional_engine.min_lot

    def test_institutional_clamps_scalar_to_range(self, institutional_engine):
        facts = AccountFacts(balance=50000.0, equity=50000.0, currency="USD", leverage=100)
        result = institutional_engine.adapt(facts, volatility_scalar=2.0)
        assert result.volatility_scalar == 1.0


class TestCentAccountDetection:
    def test_detect_cent_by_currency_token(self, conservative_engine):
        facts = AccountFacts(
            balance=1_000_000.0,  # 1M cents = $10,000
            equity=1_000_000.0,
            currency="USDc",
            server="AnyBroker",
        )
        result = conservative_engine.adapt(facts)
        assert result.is_cent_account is True
        assert result.account_currency == AccountCurrency.CENT
        assert result.dollar_balance == 10000.0
        assert result.dollar_equity == 10000.0

    def test_detect_cent_by_server_name(self, conservative_engine):
        facts = AccountFacts(
            balance=500_000.0,  # 500k cents = $5,000
            equity=500_000.0,
            currency="USD",
            server="ICMarkets-Cent",
        )
        result = conservative_engine.adapt(facts)
        assert result.is_cent_account is True
        assert result.dollar_balance == 5000.0

    def test_dollar_account_passes_through(self, conservative_engine):
        facts = AccountFacts(balance=10000.0, equity=10000.0, currency="USD")
        result = conservative_engine.adapt(facts)
        assert result.is_cent_account is False
        assert result.account_currency == AccountCurrency.USD
        assert result.dollar_balance == 10000.0

    def test_cents_to_dollars_conversion(self):
        assert AccountAdaptationEngine.cents_to_dollars(1000.0) == 10.0
        assert AccountAdaptationEngine.cents_to_dollars(1_000_000.0) == 10000.0

    def test_dollars_to_cents_conversion(self):
        assert AccountAdaptationEngine.dollars_to_cents(10.0) == 1000.0
        assert AccountAdaptationEngine.dollars_to_cents(10000.0) == 1_000_000.0


class TestLeverageCap:
    def test_leverage_capped_at_engine_cap(self, conservative_engine):
        facts = AccountFacts(balance=10000.0, equity=10000.0, currency="USD", leverage=500)
        result = conservative_engine.adapt(facts)
        assert result.leverage == conservative_engine.leverage_cap

    def test_leverage_passed_through_when_below_cap(self, conservative_engine):
        facts = AccountFacts(balance=10000.0, equity=10000.0, currency="USD", leverage=50)
        result = conservative_engine.adapt(facts)
        assert result.leverage == 50


class TestAdaptationResultIntrospection:
    def test_to_dict_contains_all_fields(self, conservative_engine):
        facts = AccountFacts(balance=10000.0, equity=10000.0, currency="USD", leverage=100)
        result = conservative_engine.adapt(facts)
        d = result.to_dict()
        assert "mode" in d
        assert "dollar_balance" in d
        assert "dollar_equity" in d
        assert "max_lot" in d
        assert "min_lot" in d
        assert "safety_flags" in d
        assert d["safety_flags"]["no_martingale"] is True
        assert d["safety_flags"]["no_loss_based_lot_multiplier"] is True

    def test_engine_to_dict_round_trip(self, conservative_engine):
        d = conservative_engine.to_dict()
        assert d["mode"] == "CONSERVATIVE_DYNAMIC"
        assert d["max_lot"] == 0.10
        assert d["safety_flags"]["no_martingale"] is True
