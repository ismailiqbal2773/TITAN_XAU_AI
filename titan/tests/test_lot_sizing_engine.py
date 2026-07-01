"""
TITAN XAU AI — LotSizingEngine unit tests (Sprint 9.9.3.45.8.5)
"""
from __future__ import annotations

import pytest

from titan.production.lot_sizing_engine import (
    LotSizingEngine,
    LotSizingInputs,
    LotSizingResult,
    LotSizingMode,
    LossBasedLotMultiplierForbidden,
    LotSizingError,
    SAFETY_FLAGS,
    lot_sizing_mode_for_adaptation_mode,
    inputs_from_adaptation_result,
)
from titan.production.account_adaptation_engine import (
    AccountAdaptationEngine,
    AccountFacts,
    AdaptationMode,
    AdaptationResult,
    AccountCurrency,
)


# ─── Fixtures ───────────────────────────────────────────────────────────────
@pytest.fixture
def fixed_engine() -> LotSizingEngine:
    return LotSizingEngine(mode=LotSizingMode.FIXED, fixed_lot_for_proof=0.01)


@pytest.fixture
def risk_engine() -> LotSizingEngine:
    return LotSizingEngine(mode=LotSizingMode.RISK_PERCENTAGE, fixed_lot_for_proof=0.01)


@pytest.fixture
def vol_engine() -> LotSizingEngine:
    return LotSizingEngine(mode=LotSizingMode.VOLATILITY_SCALED, fixed_lot_for_proof=0.01)


def _base_inputs(**overrides) -> LotSizingInputs:
    defaults = dict(
        dollar_equity=10000.0,
        risk_per_trade_pct=0.01,
        max_lot_account=0.10,
        min_lot_account=0.01,
        broker_min_lot=0.01,
        broker_max_lot=100.0,
        broker_lot_step=0.01,
        contract_size=100.0,
        tick_value=1.0,
        tick_size=0.01,
        sl_distance_price=2.0,
        price=2000.0,
        volatility_scalar=1.0,
        fixed_lot_for_proof=0.01,
    )
    defaults.update(overrides)
    return LotSizingInputs(**defaults)


# ─── Tests ──────────────────────────────────────────────────────────────────
class TestConstruction:
    def test_default_construction_uses_fixed_mode(self):
        eng = LotSizingEngine()
        assert eng.mode == LotSizingMode.FIXED
        assert eng.no_martingale is True
        assert eng.no_grid is True
        assert eng.no_averaging is True
        assert eng.no_loss_based_lot_multiplier is True

    def test_invalid_fixed_lot_raises(self):
        with pytest.raises(ValueError):
            LotSizingEngine(fixed_lot_for_proof=0.0)

    def test_invalid_default_lot_step_raises(self):
        with pytest.raises(ValueError):
            LotSizingEngine(default_lot_step=0.0)

    def test_safety_flags_property_returns_all_true(self, fixed_engine):
        flags = fixed_engine.safety_flags
        assert flags == SAFETY_FLAGS
        for k, v in flags.items():
            assert v is True


class TestFixedMode:
    def test_fixed_mode_returns_fixed_lot(self, fixed_engine):
        inputs = _base_inputs()
        result = fixed_engine.calculate_lot(inputs)
        assert isinstance(result, LotSizingResult)
        assert result.mode == LotSizingMode.FIXED
        assert result.lot == 0.01
        assert result.lot >= result.min_lot
        assert result.lot <= result.max_lot

    def test_fixed_mode_ignores_balance(self, fixed_engine):
        inputs = _base_inputs(dollar_equity=1_000_000.0)
        result = fixed_engine.calculate_lot(inputs)
        assert result.lot == 0.01

    def test_fixed_mode_clamps_to_broker_min_lot(self, fixed_engine):
        # If the fixed lot is below broker min, the result should clamp up.
        inputs = _base_inputs(fixed_lot_for_proof=0.005, broker_min_lot=0.01)
        result = fixed_engine.calculate_lot(inputs)
        assert result.lot == 0.01
        assert result.clamped_to_min is True


class TestRiskPercentageMode:
    def test_risk_percentage_returns_positive_lot(self, risk_engine):
        inputs = _base_inputs(
            dollar_equity=10000.0,
            risk_per_trade_pct=0.01,
            sl_distance_price=2.0,
            contract_size=100.0,
            tick_size=0.01,
            tick_value=1.0,
        )
        result = risk_engine.calculate_lot(inputs)
        assert result.mode == LotSizingMode.RISK_PERCENTAGE
        assert result.lot > 0.0
        assert result.risk_amount == pytest.approx(100.0)  # 1% of $10k
        assert result.lot <= result.max_lot

    def test_risk_percentage_clamps_to_max_lot(self, risk_engine):
        """Large equity + large risk_pct → lot clamped to max_lot."""
        inputs = _base_inputs(
            dollar_equity=10_000_000.0,
            risk_per_trade_pct=0.05,
            max_lot_account=0.10,
            sl_distance_price=0.5,
        )
        result = risk_engine.calculate_lot(inputs)
        assert result.lot == result.max_lot
        assert result.clamped_to_max is True

    def test_risk_percentage_zero_equity_returns_min_lot(self, risk_engine):
        inputs = _base_inputs(dollar_equity=0.0)
        result = risk_engine.calculate_lot(inputs)
        assert result.lot == result.min_lot
        assert result.clamped_to_min is True

    def test_risk_percentage_zero_sl_uses_proxy(self, risk_engine):
        """When SL distance is 0, engine falls back to a price-based proxy."""
        inputs = _base_inputs(sl_distance_price=0.0, price=2000.0)
        result = risk_engine.calculate_lot(inputs)
        assert result.lot > 0.0
        assert result.lot <= result.max_lot

    def test_risk_percentage_rounds_to_lot_step(self, risk_engine):
        """Lot must be rounded DOWN to broker_lot_step (no dust)."""
        inputs = _base_inputs(
            dollar_equity=12345.67,
            risk_per_trade_pct=0.0137,
            sl_distance_price=1.857,
            broker_lot_step=0.01,
        )
        result = risk_engine.calculate_lot(inputs)
        # Lot must be an exact multiple of lot_step.
        remainder = (result.lot * 100) % (result.lot_step * 100)
        assert remainder < 1e-9 or abs(remainder - (result.lot_step * 100)) < 1e-9


class TestVolatilityScaledMode:
    def test_volatility_scaled_returns_positive_lot(self, vol_engine):
        inputs = _base_inputs(
            dollar_equity=50000.0,
            price=2000.0,
            volatility_scalar=0.5,
        )
        result = vol_engine.calculate_lot(inputs)
        assert result.mode == LotSizingMode.VOLATILITY_SCALED
        assert result.lot > 0.0
        assert result.volatility_scalar == 0.5
        assert result.lot <= result.max_lot

    def test_volatility_scaled_zero_scalar_clamps_to_min(self, vol_engine):
        inputs = _base_inputs(volatility_scalar=0.0)
        result = vol_engine.calculate_lot(inputs)
        assert result.lot == result.min_lot

    def test_volatility_scaled_clamps_scalar_to_range(self, vol_engine):
        inputs = _base_inputs(volatility_scalar=2.0)
        result = vol_engine.calculate_lot(inputs)
        # Internal scalar should be clamped to 1.0
        assert result.volatility_scalar == 1.0


class TestForbiddenLossBasedInputs:
    """Loss-based lot multipliers are EXPLICITLY FORBIDDEN."""

    def test_loss_based_true_raises(self, risk_engine):
        with pytest.raises(LossBasedLotMultiplierForbidden):
            risk_engine.calculate_lot(_base_inputs(), loss_based=True)

    def test_consecutive_losses_raises(self, risk_engine):
        with pytest.raises(LossBasedLotMultiplierForbidden):
            risk_engine.calculate_lot(_base_inputs(), consecutive_losses=3)

    def test_consecutive_wins_raises(self, risk_engine):
        with pytest.raises(LossBasedLotMultiplierForbidden):
            risk_engine.calculate_lot(_base_inputs(), consecutive_wins=3)

    def test_last_trade_result_raises(self, risk_engine):
        with pytest.raises(LossBasedLotMultiplierForbidden):
            risk_engine.calculate_lot(_base_inputs(), last_trade_result="loss")


class TestBrokerAndAccountValidation:
    def test_broker_min_lot_enforced(self, risk_engine):
        inputs = _base_inputs(
            dollar_equity=100.0,
            risk_per_trade_pct=0.001,
            sl_distance_price=20.0,
            broker_min_lot=0.05,
        )
        result = risk_engine.calculate_lot(inputs)
        assert result.lot >= 0.05
        assert result.min_lot == 0.05

    def test_account_max_lot_caps_result(self, risk_engine):
        inputs = _base_inputs(
            dollar_equity=10_000_000.0,
            risk_per_trade_pct=0.05,
            sl_distance_price=0.5,
            max_lot_account=0.02,
        )
        result = risk_engine.calculate_lot(inputs)
        assert result.lot <= 0.02
        assert result.clamped_to_max is True

    def test_broker_max_lot_caps_result(self, risk_engine):
        inputs = _base_inputs(
            dollar_equity=10_000_000.0,
            risk_per_trade_pct=0.05,
            sl_distance_price=0.5,
            broker_max_lot=0.03,
            max_lot_account=10.0,
        )
        result = risk_engine.calculate_lot(inputs)
        assert result.lot <= 0.03
        assert result.clamped_to_max is True

    def test_invalid_bounds_raises(self, risk_engine):
        """max_lot < min_lot must raise."""
        inputs = _base_inputs(
            broker_min_lot=0.10,
            broker_max_lot=0.05,
        )
        with pytest.raises(LotSizingError):
            risk_engine.calculate_lot(inputs)

    def test_lot_step_rounding_no_dust(self, risk_engine):
        inputs = _base_inputs(
            dollar_equity=9999.99,
            risk_per_trade_pct=0.0117,
            sl_distance_price=1.234,
            broker_lot_step=0.01,
        )
        result = risk_engine.calculate_lot(inputs)
        # lot must be an exact multiple of lot_step within float tolerance.
        ratio = result.lot / result.lot_step
        assert abs(ratio - round(ratio)) < 1e-6


class TestResultIntrospection:
    def test_to_dict_contains_all_fields(self, risk_engine):
        result = risk_engine.calculate_lot(_base_inputs())
        d = result.to_dict()
        for key in ("mode", "lot", "requested_lot", "min_lot", "max_lot",
                    "lot_step", "risk_amount", "safety_flags"):
            assert key in d
        assert d["safety_flags"]["no_martingale"] is True
        assert d["safety_flags"]["no_loss_based_lot_multiplier"] is True

    def test_engine_to_dict_round_trip(self, risk_engine):
        d = risk_engine.to_dict()
        assert d["mode"] == "RISK_PERCENTAGE"
        assert "absolute_hard_max_lot" in d
        assert d["safety_flags"]["no_martingale"] is True


class TestAdaptationBridge:
    def test_lot_sizing_mode_for_adaptation_mode_mapping(self):
        assert (
            lot_sizing_mode_for_adaptation_mode(AdaptationMode.PROOF_FIXED_LOT)
            == LotSizingMode.FIXED
        )
        assert (
            lot_sizing_mode_for_adaptation_mode(AdaptationMode.CONSERVATIVE_DYNAMIC)
            == LotSizingMode.RISK_PERCENTAGE
        )
        assert (
            lot_sizing_mode_for_adaptation_mode(AdaptationMode.PROP_FIRM_CONSERVATIVE)
            == LotSizingMode.RISK_PERCENTAGE
        )
        assert (
            lot_sizing_mode_for_adaptation_mode(
                AdaptationMode.INSTITUTIONAL_VOLATILITY_SCALED
            )
            == LotSizingMode.VOLATILITY_SCALED
        )

    def test_inputs_from_adaptation_result_bridge(self):
        # Build a real AdaptationResult via the account engine.
        acct = AccountAdaptationEngine(
            mode=AdaptationMode.CONSERVATIVE_DYNAMIC,
            max_lot=0.10,
            min_lot=0.01,
            risk_per_trade_pct=0.01,
        )
        facts = AccountFacts(balance=10000.0, equity=10000.0, currency="USD", leverage=100)
        adaptation = acct.adapt(facts)
        inputs = inputs_from_adaptation_result(
            adaptation,
            sl_distance_price=2.0,
            price=2000.0,
            broker_min_lot=0.01,
            broker_max_lot=100.0,
            broker_lot_step=0.01,
        )
        assert inputs.dollar_equity == 10000.0
        assert inputs.risk_per_trade_pct == 0.01
        assert inputs.max_lot_account == pytest.approx(adaptation.max_lot, rel=1e-6)

        # End-to-end: feed the inputs to the lot sizing engine.
        lot_engine = LotSizingEngine(
            mode=lot_sizing_mode_for_adaptation_mode(adaptation.mode),
            fixed_lot_for_proof=0.01,
        )
        result = lot_engine.calculate_lot(inputs)
        assert result.lot > 0.0
        assert result.lot <= inputs.max_lot_account
