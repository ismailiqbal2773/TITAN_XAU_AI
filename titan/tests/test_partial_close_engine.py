"""
TITAN XAU AI — PartialCloseEngine unit tests (Sprint 9.9.3.45.8.6)
"""
from __future__ import annotations

import pytest

from titan.production.partial_close_engine import (
    PartialCloseEngine,
    PositionFacts,
    BrokerPartialCloseSupport,
    PartialClosePlan,
    PartialClosePolicy,
    PartialCloseVerdict,
    RemainingLotValidation,
    PartialCloseDisabled,
    DustPositionForbidden,
    SAFETY_FLAGS,
)


# ─── Fixtures ───────────────────────────────────────────────────────────────
@pytest.fixture
def enabled_fraction_engine() -> PartialCloseEngine:
    return PartialCloseEngine(
        enabled=True,
        policy=PartialClosePolicy.FIXED_FRACTION,
        fixed_fraction=0.5,
        preserve_sl_tp_on_partial=True,
    )


@pytest.fixture
def disabled_engine() -> PartialCloseEngine:
    """Disabled engine (default state)."""
    return PartialCloseEngine()


@pytest.fixture
def r_threshold_engine() -> PartialCloseEngine:
    return PartialCloseEngine(
        enabled=True,
        policy=PartialClosePolicy.R_THRESHOLD,
        fixed_fraction=0.5,
        r_threshold=1.0,
    )


@pytest.fixture
def fixed_lot_engine() -> PartialCloseEngine:
    return PartialCloseEngine(
        enabled=True,
        policy=PartialClosePolicy.FIXED_LOT,
        fixed_lot=0.02,
    )


def _profitable_buy_position() -> PositionFacts:
    return PositionFacts(
        ticket=12345,
        symbol="XAUUSD",
        side="BUY",
        open_lot=0.10,
        open_price=2000.0,
        current_price=2010.0,  # +$10 → profitable
        sl=1990.0,
        tp=2030.0,
        sl_distance_price=10.0,
    )


def _standard_broker() -> BrokerPartialCloseSupport:
    return BrokerPartialCloseSupport(
        supports_partial_close=True,
        min_lot=0.01,
        lot_step=0.01,
        contract_size=100.0,
        tick_value=1.0,
        tick_size=0.01,
    )


# ─── Tests ──────────────────────────────────────────────────────────────────
class TestConstruction:
    def test_default_engine_is_disabled(self):
        eng = PartialCloseEngine()
        assert eng.enabled is False
        assert eng.policy == PartialClosePolicy.DISABLED
        assert eng.is_enabled is False

    def test_safety_flags_all_true(self, disabled_engine):
        flags = disabled_engine.safety_flags
        assert flags == SAFETY_FLAGS
        for k, v in flags.items():
            assert v is True

    def test_invalid_fixed_fraction_raises(self):
        with pytest.raises(ValueError):
            PartialCloseEngine(
                enabled=True,
                policy=PartialClosePolicy.FIXED_FRACTION,
                fixed_fraction=0.0,
            )

    def test_invalid_fixed_fraction_above_max_raises(self):
        with pytest.raises(ValueError):
            PartialCloseEngine(
                enabled=True,
                policy=PartialClosePolicy.FIXED_FRACTION,
                fixed_fraction=1.5,
            )

    def test_invalid_fixed_lot_raises(self):
        with pytest.raises(ValueError):
            PartialCloseEngine(
                enabled=True,
                policy=PartialClosePolicy.FIXED_LOT,
                fixed_lot=0.0,
            )

    def test_invalid_r_threshold_raises(self):
        with pytest.raises(ValueError):
            PartialCloseEngine(
                enabled=True,
                policy=PartialClosePolicy.R_THRESHOLD,
                r_threshold=0.0,
            )


class TestCanPartialClose:
    def test_disabled_engine_blocks_all(self, disabled_engine):
        verdict = disabled_engine.can_partial_close(
            _profitable_buy_position(), _standard_broker()
        )
        assert verdict == PartialCloseVerdict.BLOCKED_DISABLED

    def test_broker_not_supporting_partial_close_blocks(
        self, enabled_fraction_engine
    ):
        broker = _standard_broker()
        broker.supports_partial_close = False
        verdict = enabled_fraction_engine.can_partial_close(
            _profitable_buy_position(), broker
        )
        assert verdict == PartialCloseVerdict.BLOCKED_BROKER

    def test_position_lot_below_broker_min_blocks(
        self, enabled_fraction_engine
    ):
        broker = _standard_broker()
        broker.min_lot = 0.10
        pos = _profitable_buy_position()
        pos.open_lot = 0.05
        verdict = enabled_fraction_engine.can_partial_close(pos, broker)
        assert verdict == PartialCloseVerdict.BLOCKED_LOT

    def test_invalid_side_blocks(self, enabled_fraction_engine):
        pos = _profitable_buy_position()
        pos.side = "INVALID"
        verdict = enabled_fraction_engine.can_partial_close(
            pos, _standard_broker()
        )
        assert verdict == PartialCloseVerdict.BLOCKED_INVALID_INPUT

    def test_zero_open_price_blocks(self, enabled_fraction_engine):
        pos = _profitable_buy_position()
        pos.open_price = 0.0
        verdict = enabled_fraction_engine.can_partial_close(
            pos, _standard_broker()
        )
        assert verdict == PartialCloseVerdict.BLOCKED_INVALID_INPUT

    def test_profitable_position_allowed(self, enabled_fraction_engine):
        verdict = enabled_fraction_engine.can_partial_close(
            _profitable_buy_position(), _standard_broker()
        )
        assert verdict == PartialCloseVerdict.ALLOWED


class TestCalculatePartialCloseFixedFraction:
    def test_fixed_fraction_closes_half(self, enabled_fraction_engine):
        plan = enabled_fraction_engine.calculate_partial_close(
            _profitable_buy_position(), _standard_broker()
        )
        assert plan.verdict == PartialCloseVerdict.ALLOWED
        assert plan.close_lot == pytest.approx(0.05, rel=1e-6)
        assert plan.remaining_lot == pytest.approx(0.05, rel=1e-6)

    def test_realized_profit_positive_for_profitable_buy(
        self, enabled_fraction_engine
    ):
        plan = enabled_fraction_engine.calculate_partial_close(
            _profitable_buy_position(), _standard_broker()
        )
        # BUY: (2010 - 2000) * 0.05 * 100 = 50.0
        assert plan.realized_profit == pytest.approx(50.0, rel=1e-6)

    def test_sl_tp_preserved_when_configured(self, enabled_fraction_engine):
        pos = _profitable_buy_position()
        plan = enabled_fraction_engine.calculate_partial_close(
            pos, _standard_broker()
        )
        assert plan.new_sl == pos.sl
        assert plan.new_tp == pos.tp

    def test_sl_tp_moved_to_breakeven_when_not_preserved(self):
        eng = PartialCloseEngine(
            enabled=True,
            policy=PartialClosePolicy.FIXED_FRACTION,
            fixed_fraction=0.5,
            preserve_sl_tp_on_partial=False,
        )
        pos = _profitable_buy_position()
        plan = eng.calculate_partial_close(pos, _standard_broker())
        assert plan.verdict == PartialCloseVerdict.ALLOWED
        assert plan.new_sl == pos.open_price  # breakeven
        assert plan.new_tp == pos.tp


class TestCalculatePartialCloseRThreshold:
    def test_r_threshold_blocks_when_not_reached(self, r_threshold_engine):
        plan = r_threshold_engine.calculate_partial_close(
            _profitable_buy_position(),
            _standard_broker(),
            r_multiple=0.5,  # below threshold of 1.0
        )
        assert plan.verdict == PartialCloseVerdict.BLOCKED_NO_PROFIT
        assert plan.close_lot == 0.0

    def test_r_threshold_allows_when_reached(self, r_threshold_engine):
        plan = r_threshold_engine.calculate_partial_close(
            _profitable_buy_position(),
            _standard_broker(),
            r_multiple=1.5,  # above threshold
        )
        assert plan.verdict == PartialCloseVerdict.ALLOWED
        assert plan.close_lot > 0.0


class TestCalculatePartialCloseFixedLot:
    def test_fixed_lot_closes_specified_amount(self, fixed_lot_engine):
        plan = fixed_lot_engine.calculate_partial_close(
            _profitable_buy_position(), _standard_broker()
        )
        assert plan.verdict == PartialCloseVerdict.ALLOWED
        assert plan.close_lot == pytest.approx(0.02, rel=1e-6)
        assert plan.remaining_lot == pytest.approx(0.08, rel=1e-6)


class TestDustPositionProtection:
    def test_partial_close_leaving_dust_is_blocked(self):
        """If the partial close would leave a dust position, the engine blocks."""
        eng = PartialCloseEngine(
            enabled=True,
            policy=PartialClosePolicy.FIXED_FRACTION,
            fixed_fraction=0.9,  # close 90% — would leave 0.01 (== dust threshold)
            dust_threshold=0.02,
        )
        pos = _profitable_buy_position()
        pos.open_lot = 0.10  # close 0.09, leave 0.01 < dust_threshold 0.02
        plan = eng.calculate_partial_close(pos, _standard_broker())
        # The engine should clamp close_lot down to leave at least dust_threshold.
        # close_lot = max(0, 0.10 - 0.02) = 0.08 → remaining 0.02
        if plan.verdict == PartialCloseVerdict.ALLOWED:
            assert plan.remaining_lot >= 0.02
        else:
            # Or the engine may refuse entirely if the clamped close_lot
            # is below broker min_lot.
            assert plan.verdict in (
                PartialCloseVerdict.BLOCKED_DUST,
                PartialCloseVerdict.BLOCKED_LOT,
            )

    def test_full_close_attempt_blocked(self, enabled_fraction_engine):
        """Closing more than the open lot is not allowed."""
        pos = _profitable_buy_position()
        pos.open_lot = 0.02
        broker = _standard_broker()
        broker.min_lot = 0.01
        # 50% of 0.02 = 0.01 (close) → 0.01 (remaining). Both are >= min_lot.
        plan = enabled_fraction_engine.calculate_partial_close(pos, broker)
        assert plan.verdict == PartialCloseVerdict.ALLOWED
        assert plan.close_lot <= pos.open_lot
        assert plan.remaining_lot > 0


class TestRequireProfit:
    def test_losing_position_blocked_when_require_profit_true(
        self, enabled_fraction_engine
    ):
        pos = _profitable_buy_position()
        pos.current_price = 1990.0  # losing position
        plan = enabled_fraction_engine.calculate_partial_close(
            pos, _standard_broker()
        )
        assert plan.verdict == PartialCloseVerdict.BLOCKED_NO_PROFIT

    def test_losing_position_allowed_when_require_profit_false(self):
        eng = PartialCloseEngine(
            enabled=True,
            policy=PartialClosePolicy.FIXED_FRACTION,
            fixed_fraction=0.5,
            require_profit=False,
        )
        pos = _profitable_buy_position()
        pos.current_price = 1990.0  # losing position
        plan = eng.calculate_partial_close(pos, _standard_broker())
        assert plan.verdict == PartialCloseVerdict.ALLOWED


class TestValidateRemainingLot:
    def test_valid_remaining_lot_passes(self, enabled_fraction_engine):
        result = enabled_fraction_engine.validate_remaining_lot(
            0.05, _standard_broker()
        )
        assert isinstance(result, RemainingLotValidation)
        assert result.ok is True
        assert result.is_dust is False

    def test_dust_remaining_lot_fails(self, enabled_fraction_engine):
        result = enabled_fraction_engine.validate_remaining_lot(
            0.005, _standard_broker()
        )
        assert result.ok is False
        assert result.is_dust is True

    def test_remaining_lot_below_broker_min_fails(
        self, enabled_fraction_engine
    ):
        result = enabled_fraction_engine.validate_remaining_lot(
            0.005, _standard_broker()
        )
        assert result.ok is False

    def test_remaining_lot_not_step_aligned_fails(
        self, enabled_fraction_engine
    ):
        broker = _standard_broker()
        broker.lot_step = 0.05
        result = enabled_fraction_engine.validate_remaining_lot(
            0.07, broker  # not a multiple of 0.05
        )
        assert result.ok is False
        assert result.rounded_to_step is False

    def test_remaining_lot_step_aligned_passes(
        self, enabled_fraction_engine
    ):
        broker = _standard_broker()
        broker.lot_step = 0.05
        result = enabled_fraction_engine.validate_remaining_lot(
            0.10, broker  # exact multiple of 0.05
        )
        assert result.ok is True
        assert result.rounded_to_step is True


class TestRecomputeRemainingRisk:
    def test_recompute_remaining_risk_halves_when_lot_halves(
        self, enabled_fraction_engine
    ):
        pos = _profitable_buy_position()
        # SL=1990, current=2010 → distance = 20
        # tick_size=0.01 → ticks = 2000
        # tick_value=1.0 → per_lot_risk = 2000 * 1.0 = 2000 per lot
        # original_risk = 2000 * 0.10 = 200.0
        # remaining_risk = 2000 * 0.05 = 100.0
        risk = enabled_fraction_engine.recompute_remaining_risk(
            pos, remaining_lot=0.05, broker=_standard_broker()
        )
        assert risk["original_risk"] == pytest.approx(200.0, rel=1e-6)
        assert risk["remaining_risk"] == pytest.approx(100.0, rel=1e-6)
        assert risk["risk_reduction"] == pytest.approx(100.0, rel=1e-6)
        assert risk["risk_reduction_pct"] == pytest.approx(0.5, rel=1e-6)

    def test_recompute_remaining_risk_no_sl_returns_zero(
        self, enabled_fraction_engine
    ):
        pos = _profitable_buy_position()
        pos.sl = 0.0
        risk = enabled_fraction_engine.recompute_remaining_risk(
            pos, remaining_lot=0.05, broker=_standard_broker()
        )
        assert risk["remaining_risk"] == 0.0
        assert "No SL" in risk["reason"]


class TestPlanIntrospection:
    def test_plan_to_dict_contains_all_fields(self, enabled_fraction_engine):
        plan = enabled_fraction_engine.calculate_partial_close(
            _profitable_buy_position(), _standard_broker()
        )
        d = plan.to_dict()
        for key in ("verdict", "policy", "close_lot", "remaining_lot",
                    "realized_profit", "open_price", "close_price",
                    "side", "new_sl", "new_tp", "reason", "safety_flags"):
            assert key in d
        assert d["safety_flags"]["no_martingale"] is True
        assert d["safety_flags"]["no_loss_based_lot_multiplier"] is True

    def test_engine_to_dict_round_trip(self, enabled_fraction_engine):
        d = enabled_fraction_engine.to_dict()
        assert d["enabled"] is True
        assert d["policy"] == "FIXED_FRACTION"
        assert d["fixed_fraction"] == 0.5
        assert d["safety_flags"]["no_martingale"] is True
