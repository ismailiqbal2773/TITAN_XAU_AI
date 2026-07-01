"""TITAN XAU AI - Sprint 9.9.3.45.8.2 Adaptive Profit Corridor Policy Tests

Tests for titan/production/adaptive_profit_corridor.py:
  - dynamic TP disabled by default
  - TP preserved by default
  - dynamic TP requires explicit flag
  - TP extension requires trend regime
  - TP extension blocked in range unless explicit override
  - TP extension blocked by spread spike
  - TP extension blocked if SL cannot protect minimum profit
  - TP extension paired with SL raise
  - TP never reduced
  - SL never widened
  - paired SLTP modify preserves action safety
  - no tick chasing due cooldown
  - HOLD does not modify
  - MODIFY uses existing gated apply path
  - no martingale/grid/averaging
  - no loss-based lot multiplier
  - no real order_send in tests
"""
from __future__ import annotations
import re, sys
from pathlib import Path
import pytest
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from titan.production.adaptive_profit_corridor import (
    AdaptiveProfitCorridor, CorridorAction, CorridorDecision,
)
from titan.production.adaptive_trailing_policy import Regime


def _strip(src):
    src = re.sub(r'"""[\s\S]*?"""', '""', src)
    src = re.sub(r"'''[\s\S]*?'''", "''", src)
    src = re.sub(r'"(?:[^"\\]|\\.)*"', '""', src)
    src = re.sub(r"'(?:[^'\\]|\\.)*'", "''", src)
    return src


class TestAdaptiveProfitCorridorPolicy:
    def test_01_module_imports(self):
        from titan.production import adaptive_profit_corridor
        assert hasattr(adaptive_profit_corridor, "AdaptiveProfitCorridor")
        assert hasattr(adaptive_profit_corridor, "CorridorAction")
        assert hasattr(adaptive_profit_corridor, "CorridorDecision")

    def test_02_corridor_actions_supported(self):
        assert CorridorAction.HOLD.value == "HOLD"
        assert CorridorAction.EXTEND_TP_AND_RAISE_SL.value == "EXTEND_TP_AND_RAISE_SL"
        assert CorridorAction.RAISE_SL_ONLY.value == "RAISE_SL_ONLY"
        assert CorridorAction.BLOCKED.value == "BLOCKED"

    def test_03_dynamic_tp_disabled_by_default(self):
        """Dynamic TP must be disabled by default."""
        corridor = AdaptiveProfitCorridor()  # Default
        assert corridor.dynamic_tp_enabled is False

    def test_04_tp_preserved_when_dynamic_tp_disabled(self):
        """When dynamic_tp_enabled=False, TP must be preserved (HOLD)."""
        corridor = AdaptiveProfitCorridor(dynamic_tp_enabled=False)
        decision = corridor.evaluate(
            direction="BUY", entry_price=2000.0, initial_sl=1990.0,
            current_sl=2012.0, current_tp=2025.0, current_price=2020.0,
            atr=1.0, spread=0.05, regime=Regime.TREND,
            monitor_iterations=5, hold_seconds=120,
            seconds_since_last_tp_extension=999,
            mfe=2020.0, adaptive_trailing_enabled=True,
        )
        assert decision.action == CorridorAction.HOLD
        assert decision.tp_extension_allowed is False
        assert decision.final_tp == 2025.0  # Preserved
        assert decision.no_tp_reduction is True

    def test_05_dynamic_tp_requires_explicit_flag(self):
        """Dynamic TP requires explicit dynamic_tp_enabled=True."""
        corridor = AdaptiveProfitCorridor(dynamic_tp_enabled=False)
        decision = corridor.evaluate(
            direction="BUY", entry_price=2000.0, initial_sl=1990.0,
            current_sl=2012.0, current_tp=2025.0, current_price=2020.0,
            atr=1.0, spread=0.05, regime=Regime.TREND,
            monitor_iterations=5, hold_seconds=120,
            seconds_since_last_tp_extension=999,
            mfe=2020.0, adaptive_trailing_enabled=True,
        )
        # Without explicit flag, TP extension not allowed
        assert decision.tp_extension_allowed is False

    def test_06_tp_extension_requires_adaptive_trailing(self):
        """TP extension requires adaptive_trailing_enabled=True."""
        corridor = AdaptiveProfitCorridor(dynamic_tp_enabled=True)
        decision = corridor.evaluate(
            direction="BUY", entry_price=2000.0, initial_sl=1990.0,
            current_sl=2012.0, current_tp=2025.0, current_price=2020.0,
            atr=1.0, spread=0.05, regime=Regime.TREND,
            monitor_iterations=5, hold_seconds=120,
            seconds_since_last_tp_extension=999,
            mfe=2020.0,
            adaptive_trailing_enabled=False,  # Not enabled
        )
        assert decision.action == CorridorAction.HOLD
        assert decision.tp_extension_allowed is False
        assert any("ADAPTIVE_TRAILING_REQUIRED" in b for b in decision.blocks)

    def test_07_tp_extension_requires_trend_regime(self):
        """TP extension requires trend regime."""
        corridor = AdaptiveProfitCorridor(dynamic_tp_enabled=True)
        decision = corridor.evaluate(
            direction="BUY", entry_price=2000.0, initial_sl=1990.0,
            current_sl=2012.0, current_tp=2025.0, current_price=2020.0,
            atr=1.0, spread=0.05, regime=Regime.TREND,
            monitor_iterations=5, hold_seconds=120,
            seconds_since_last_tp_extension=999,
            mfe=2020.0, adaptive_trailing_enabled=True,
        )
        # Trend regime: TP extension allowed (if other conditions met)
        # SL protects 1.2R profit (2012 >= 2000 + 1.2*10 = 2012), so OK
        assert decision.action == CorridorAction.EXTEND_TP_AND_RAISE_SL
        assert decision.tp_extension_allowed is True

    def test_08_tp_extension_blocked_in_range(self):
        """TP extension blocked in range regime."""
        corridor = AdaptiveProfitCorridor(dynamic_tp_enabled=True)
        decision = corridor.evaluate(
            direction="BUY", entry_price=2000.0, initial_sl=1990.0,
            current_sl=2012.0, current_tp=2025.0, current_price=2020.0,
            atr=1.0, spread=0.05, regime=Regime.RANGE,  # Range
            monitor_iterations=5, hold_seconds=120,
            seconds_since_last_tp_extension=999,
            mfe=2020.0, adaptive_trailing_enabled=True,
        )
        assert decision.action == CorridorAction.HOLD
        assert decision.tp_extension_allowed is False
        assert any("RANGE_REGIME" in b for b in decision.blocks)

    def test_09_tp_extension_blocked_by_spread_spike(self):
        """TP extension blocked by spread spike."""
        corridor = AdaptiveProfitCorridor(dynamic_tp_enabled=True)
        decision = corridor.evaluate(
            direction="BUY", entry_price=2000.0, initial_sl=1990.0,
            current_sl=2012.0, current_tp=2025.0, current_price=2020.0,
            atr=1.0, spread=0.05, regime=Regime.TREND,
            monitor_iterations=5, hold_seconds=120,
            seconds_since_last_tp_extension=999,
            spread_spike_flag=True,  # Spread spike
            mfe=2020.0, adaptive_trailing_enabled=True,
        )
        assert decision.action == CorridorAction.HOLD
        assert decision.tp_extension_allowed is False
        assert any("SPREAD_SPIKE_FLAG_ACTIVE" in b for b in decision.blocks)

    def test_10_tp_extension_blocked_by_news(self):
        """TP extension blocked by news flag."""
        corridor = AdaptiveProfitCorridor(dynamic_tp_enabled=True)
        decision = corridor.evaluate(
            direction="BUY", entry_price=2000.0, initial_sl=1990.0,
            current_sl=2012.0, current_tp=2025.0, current_price=2020.0,
            atr=1.0, spread=0.05, regime=Regime.TREND,
            monitor_iterations=5, hold_seconds=120,
            seconds_since_last_tp_extension=999,
            news_flag=True,  # News active
            mfe=2020.0, adaptive_trailing_enabled=True,
        )
        assert decision.action == CorridorAction.HOLD
        assert any("NEWS_FLAG_ACTIVE" in b for b in decision.blocks)

    def test_11_tp_extension_blocked_if_sl_cannot_protect_profit(self):
        """TP extension blocked if SL doesn't protect minimum locked_R profit.

        SL must be raised first (RAISE_SL_ONLY action).
        """
        corridor = AdaptiveProfitCorridor(dynamic_tp_enabled=True, locked_R=1.2)
        decision = corridor.evaluate(
            direction="BUY", entry_price=2000.0, initial_sl=1990.0,
            current_sl=2005.0,  # Only protects 0.5R < 1.2R locked_R
            current_tp=2025.0, current_price=2020.0,
            atr=1.0, spread=0.05, regime=Regime.TREND,
            monitor_iterations=5, hold_seconds=120,
            seconds_since_last_tp_extension=999,
            mfe=2020.0, adaptive_trailing_enabled=True,
        )
        # SL must be raised first, TP not extended yet
        assert decision.action == CorridorAction.RAISE_SL_ONLY
        assert decision.tp_extension_allowed is False
        # SL raised to protect locked_R profit
        # locked_profit_value = 1.2 * 10 = 12, so SL = 2000 + 12 = 2012
        assert decision.final_sl == pytest.approx(2012.0, abs=0.01)

    def test_12_tp_extension_paired_with_sl_raise(self):
        """TP extension must be paired with SL raise."""
        corridor = AdaptiveProfitCorridor(dynamic_tp_enabled=True, locked_R=1.2)
        decision = corridor.evaluate(
            direction="BUY", entry_price=2000.0, initial_sl=1990.0,
            current_sl=2012.0,  # Protects 1.2R profit
            current_tp=2025.0, current_price=2020.0,
            atr=1.0, spread=0.05, regime=Regime.TREND,
            monitor_iterations=5, hold_seconds=120,
            seconds_since_last_tp_extension=999,
            mfe=2020.0, adaptive_trailing_enabled=True,
        )
        assert decision.action == CorridorAction.EXTEND_TP_AND_RAISE_SL
        assert decision.tp_sl_pair_valid is True
        # TP must be extended (new_tp > old_tp for BUY)
        assert decision.final_tp > 2025.0
        # SL must be raised or maintained (new_sl >= old_sl for BUY)
        assert decision.final_sl >= 2012.0

    def test_13_tp_never_reduced(self):
        """TP must never be reduced."""
        corridor = AdaptiveProfitCorridor(dynamic_tp_enabled=True)
        decision = corridor.evaluate(
            direction="BUY", entry_price=2000.0, initial_sl=1990.0,
            current_sl=2012.0, current_tp=2025.0, current_price=2020.0,
            atr=1.0, spread=0.05, regime=Regime.TREND,
            monitor_iterations=5, hold_seconds=120,
            seconds_since_last_tp_extension=999,
            mfe=2020.0, adaptive_trailing_enabled=True,
        )
        assert decision.no_tp_reduction is True
        assert decision.final_tp >= 2025.0  # TP preserved or extended

    def test_14_sl_never_widened(self):
        """SL must never widen."""
        corridor = AdaptiveProfitCorridor(dynamic_tp_enabled=True)
        decision = corridor.evaluate(
            direction="BUY", entry_price=2000.0, initial_sl=1990.0,
            current_sl=2018.0,  # Already trailed up high
            current_tp=2030.0, current_price=2020.0,
            atr=1.0, spread=0.05, regime=Regime.TREND,
            monitor_iterations=5, hold_seconds=120,
            seconds_since_last_tp_extension=999,
            mfe=2020.0, adaptive_trailing_enabled=True,
        )
        # SL must not widen (final_sl >= current_sl for BUY)
        assert decision.final_sl >= 2018.0
        assert decision.no_sl_widening is True

    def test_15_no_tick_chasing_due_cooldown(self):
        """No tick chasing - cooldown blocks repeated TP extension."""
        corridor = AdaptiveProfitCorridor(
            dynamic_tp_enabled=True, tp_extension_cooldown_seconds=120,
        )
        decision = corridor.evaluate(
            direction="BUY", entry_price=2000.0, initial_sl=1990.0,
            current_sl=2012.0, current_tp=2025.0, current_price=2020.0,
            atr=1.0, spread=0.05, regime=Regime.TREND,
            monitor_iterations=5, hold_seconds=120,
            seconds_since_last_tp_extension=30,  # Within 120s cooldown
            mfe=2020.0, adaptive_trailing_enabled=True,
        )
        assert decision.action == CorridorAction.HOLD
        assert decision.tp_extension_allowed is False
        assert any("COOLDOWN_ACTIVE" in b for b in decision.blocks)

    def test_16_no_tick_chasing_mfe_not_improving(self):
        """No tick chasing - MFE not improving blocks TP extension."""
        corridor = AdaptiveProfitCorridor(dynamic_tp_enabled=True)
        decision = corridor.evaluate(
            direction="BUY", entry_price=2000.0, initial_sl=1990.0,
            current_sl=2012.0, current_tp=2025.0, current_price=2018.0,
            atr=1.0, spread=0.05, regime=Regime.TREND,
            monitor_iterations=5, hold_seconds=120,
            seconds_since_last_tp_extension=999,
            mfe=2025.0,  # MFE higher than current_price -> not improving
            adaptive_trailing_enabled=True,
        )
        # profit_R = 1.8 < tp_extension_trigger_R=2.0, so HOLD anyway
        # But also MFE not improving would block
        assert decision.action == CorridorAction.HOLD
        assert decision.tp_extension_allowed is False

    def test_17_hold_does_not_modify(self):
        """HOLD action must not modify SL or TP."""
        corridor = AdaptiveProfitCorridor(dynamic_tp_enabled=False)
        decision = corridor.evaluate(
            direction="BUY", entry_price=2000.0, initial_sl=1990.0,
            current_sl=2012.0, current_tp=2025.0, current_price=2020.0,
            atr=1.0, spread=0.05, regime=Regime.TREND,
            monitor_iterations=5, hold_seconds=120,
            seconds_since_last_tp_extension=999,
            mfe=2020.0, adaptive_trailing_enabled=True,
        )
        assert decision.action == CorridorAction.HOLD
        # final_sl and final_tp must equal current values (no modification)
        assert decision.final_sl == 2012.0
        assert decision.final_tp == 2025.0

    def test_18_sell_direction_tp_extension(self):
        """SELL direction TP extension must work correctly."""
        corridor = AdaptiveProfitCorridor(dynamic_tp_enabled=True, locked_R=1.2)
        decision = corridor.evaluate(
            direction="SELL", entry_price=2000.0, initial_sl=2010.0,
            current_sl=1988.0,  # Protects 1.2R profit (1988 <= 2000 - 12 = 1988)
            current_tp=1975.0, current_price=1980.0,
            atr=1.0, spread=0.05, regime=Regime.TREND,
            monitor_iterations=5, hold_seconds=120,
            seconds_since_last_tp_extension=999,
            mfe=1980.0, adaptive_trailing_enabled=True,
        )
        assert decision.action == CorridorAction.EXTEND_TP_AND_RAISE_SL
        # SELL: TP must be reduced (extended downward) or preserved
        assert decision.final_tp <= 1975.0
        # SELL: SL must be reduced or maintained (new_sl <= old_sl)
        assert decision.final_sl <= 1988.0
        assert decision.no_tp_reduction is True  # no_tp_reduction means TP not moved against
        assert decision.no_sl_widening is True

    def test_19_decision_has_all_required_fields(self):
        """CorridorDecision must populate all required fields."""
        corridor = AdaptiveProfitCorridor(dynamic_tp_enabled=True)
        decision = corridor.evaluate(
            direction="BUY", entry_price=2000.0, initial_sl=1990.0,
            current_sl=2012.0, current_tp=2025.0, current_price=2020.0,
            atr=1.0, spread=0.05, regime=Regime.TREND,
            monitor_iterations=5, hold_seconds=120,
            seconds_since_last_tp_extension=999,
            mfe=2020.0, adaptive_trailing_enabled=True,
        )
        required = [
            "dynamic_tp_enabled", "profit_corridor_enabled", "action",
            "actual_monitor_iteration", "policy_monitor_iteration",
            "hold_seconds", "profit_R", "R", "MFE",
            "old_sl", "proposed_sl", "final_sl",
            "old_tp", "proposed_tp", "final_tp",
            "tp_extension_allowed", "tp_extension_action", "tp_sl_pair_valid",
            "sl_profit_floor_R", "max_profit_giveback_R",
            "no_tp_reduction", "no_sl_widening", "reason", "blocks",
        ]
        for field in required:
            assert hasattr(decision, field), f"Missing field: {field}"

    def test_20_no_martingale_in_corridor(self):
        """Corridor must NOT contain martingale/grid/averaging."""
        src = (REPO_ROOT / "titan" / "production" / "adaptive_profit_corridor.py").read_text()
        code = _strip(src).lower()
        for term in ["martingale", "grid_trade", "averaging_down", "double_lot",
                     "add_position", "loss_based_lot", "recovery_multiplier"]:
            assert term not in code, f"Forbidden term '{term}' in corridor code"

    def test_21_no_order_send_in_corridor(self):
        """Corridor must NOT call mt5.order_send or mt5.order_modify."""
        src = (REPO_ROOT / "titan" / "production" / "adaptive_profit_corridor.py").read_text()
        code = _strip(src)
        assert not re.search(r"\bmt5\.order_send\s*\(", code)
        assert not re.search(r"\bmt5\.order_modify\s*\(", code)

    def test_22_no_loss_based_lot_multiplier(self):
        """Corridor must NOT implement loss-based lot multiplier."""
        src = (REPO_ROOT / "titan" / "production" / "adaptive_profit_corridor.py").read_text()
        code = _strip(src).lower()
        assert "loss_based_lot" not in code
        assert "double_after_loss" not in code
        assert "loss_multiplier" not in code

    def test_23_high_vol_regime_blocks_tp_extension(self):
        """High volatility regime must block TP extension."""
        corridor = AdaptiveProfitCorridor(dynamic_tp_enabled=True)
        decision = corridor.evaluate(
            direction="BUY", entry_price=2000.0, initial_sl=1990.0,
            current_sl=2012.0, current_tp=2025.0, current_price=2020.0,
            atr=1.0, spread=0.05, regime=Regime.HIGH_VOL,
            monitor_iterations=5, hold_seconds=120,
            seconds_since_last_tp_extension=999,
            mfe=2020.0, adaptive_trailing_enabled=True,
        )
        assert decision.action == CorridorAction.HOLD
        assert any("HIGH_VOL_REGIME" in b for b in decision.blocks)

    def test_24_profit_below_trigger_blocks_tp_extension(self):
        """profit_R below tp_extension_trigger_R must block TP extension."""
        corridor = AdaptiveProfitCorridor(
            dynamic_tp_enabled=True, tp_extension_trigger_R=2.0,
        )
        decision = corridor.evaluate(
            direction="BUY", entry_price=2000.0, initial_sl=1990.0,
            current_sl=2012.0, current_tp=2025.0, current_price=2015.0,  # profit_R=1.5
            atr=1.0, spread=0.05, regime=Regime.TREND,
            monitor_iterations=5, hold_seconds=120,
            seconds_since_last_tp_extension=999,
            mfe=2015.0, adaptive_trailing_enabled=True,
        )
        assert decision.action == CorridorAction.HOLD
        assert decision.tp_extension_allowed is False

    def test_25_no_mojibake(self):
        src = (REPO_ROOT / "titan" / "production" / "adaptive_profit_corridor.py").read_text()
        assert "\u2014" not in src
        assert "\u2013" not in src
        assert "\u2018" not in src
        assert "\u2019" not in src

    # === Sprint 9.9.3.45.8.2.1: hard invariant tests ===

    def test_26_modify_requires_favorable_true(self):
        """Any MODIFY action (EXTEND_TP_AND_RAISE_SL or RAISE_SL_ONLY)
        must have favorable=True."""
        corridor = AdaptiveProfitCorridor(dynamic_tp_enabled=True, locked_R=1.2)
        # Test EXTEND_TP_AND_RAISE_SL
        decision = corridor.evaluate(
            direction="BUY", entry_price=2000.0, initial_sl=1990.0,
            current_sl=2012.0, current_tp=2025.0, current_price=2020.0,
            atr=1.0, spread=0.05, regime=Regime.TREND,
            monitor_iterations=5, hold_seconds=120,
            seconds_since_last_tp_extension=999,
            mfe=2020.0, adaptive_trailing_enabled=True,
        )
        if decision.action in (CorridorAction.EXTEND_TP_AND_RAISE_SL, CorridorAction.RAISE_SL_ONLY):
            assert decision.favorable is True, \
                f"MODIFY action {decision.action} must have favorable=True, got False"

    def test_27_modify_requires_no_widening_true(self):
        """Any MODIFY action must have no_sl_widening=True."""
        corridor = AdaptiveProfitCorridor(dynamic_tp_enabled=True, locked_R=1.2)
        decision = corridor.evaluate(
            direction="BUY", entry_price=2000.0, initial_sl=1990.0,
            current_sl=2012.0, current_tp=2025.0, current_price=2020.0,
            atr=1.0, spread=0.05, regime=Regime.TREND,
            monitor_iterations=5, hold_seconds=120,
            seconds_since_last_tp_extension=999,
            mfe=2020.0, adaptive_trailing_enabled=True,
        )
        if decision.action in (CorridorAction.EXTEND_TP_AND_RAISE_SL, CorridorAction.RAISE_SL_ONLY):
            assert decision.no_sl_widening is True, \
                f"MODIFY action must have no_sl_widening=True"

    def test_28_tp_extension_requires_no_tp_reduction_true(self):
        """TP extension (EXTEND_TP_AND_RAISE_SL) must have
        no_tp_reduction=True."""
        corridor = AdaptiveProfitCorridor(dynamic_tp_enabled=True, locked_R=1.2)
        decision = corridor.evaluate(
            direction="BUY", entry_price=2000.0, initial_sl=1990.0,
            current_sl=2012.0, current_tp=2025.0, current_price=2020.0,
            atr=1.0, spread=0.05, regime=Regime.TREND,
            monitor_iterations=5, hold_seconds=120,
            seconds_since_last_tp_extension=999,
            mfe=2020.0, adaptive_trailing_enabled=True,
        )
        if decision.action == CorridorAction.EXTEND_TP_AND_RAISE_SL:
            assert decision.no_tp_reduction is True, \
                "TP extension must have no_tp_reduction=True"

    def test_29_tp_extension_requires_tp_sl_pair_valid_true(self):
        """TP extension (EXTEND_TP_AND_RAISE_SL) must have
        tp_sl_pair_valid=True."""
        corridor = AdaptiveProfitCorridor(dynamic_tp_enabled=True, locked_R=1.2)
        decision = corridor.evaluate(
            direction="BUY", entry_price=2000.0, initial_sl=1990.0,
            current_sl=2012.0, current_tp=2025.0, current_price=2020.0,
            atr=1.0, spread=0.05, regime=Regime.TREND,
            monitor_iterations=5, hold_seconds=120,
            seconds_since_last_tp_extension=999,
            mfe=2020.0, adaptive_trailing_enabled=True,
        )
        if decision.action == CorridorAction.EXTEND_TP_AND_RAISE_SL:
            assert decision.tp_sl_pair_valid is True, \
                "TP extension must have tp_sl_pair_valid=True"

    def test_30_modify_requires_zero_blocking_reasons(self):
        """Any MODIFY action must have blocking_reasons_count=0."""
        corridor = AdaptiveProfitCorridor(dynamic_tp_enabled=True, locked_R=1.2)
        decision = corridor.evaluate(
            direction="BUY", entry_price=2000.0, initial_sl=1990.0,
            current_sl=2012.0, current_tp=2025.0, current_price=2020.0,
            atr=1.0, spread=0.05, regime=Regime.TREND,
            monitor_iterations=5, hold_seconds=120,
            seconds_since_last_tp_extension=999,
            mfe=2020.0, adaptive_trailing_enabled=True,
        )
        if decision.action in (CorridorAction.EXTEND_TP_AND_RAISE_SL, CorridorAction.RAISE_SL_ONLY):
            assert decision.blocking_reasons_count == 0, \
                f"MODIFY action must have 0 blocking_reasons, got {decision.blocking_reasons_count}"

    def test_31_blocking_reason_forces_hold_or_blocked(self):
        """Any blocking reason must force action to HOLD or BLOCKED,
        not MODIFY."""
        corridor = AdaptiveProfitCorridor(dynamic_tp_enabled=True, locked_R=1.2)
        # Spread spike -> blocking reason -> HOLD
        decision = corridor.evaluate(
            direction="BUY", entry_price=2000.0, initial_sl=1990.0,
            current_sl=2012.0, current_tp=2025.0, current_price=2020.0,
            atr=1.0, spread=0.05, regime=Regime.TREND,
            monitor_iterations=5, hold_seconds=120,
            seconds_since_last_tp_extension=999,
            spread_spike_flag=True,  # Blocking
            mfe=2020.0, adaptive_trailing_enabled=True,
        )
        assert decision.blocking_reasons_count > 0
        assert decision.action in (CorridorAction.HOLD, CorridorAction.BLOCKED), \
            f"Blocking reason must force HOLD/BLOCKED, got {decision.action}"

    def test_32_decision_has_blocking_and_informational_fields(self):
        """CorridorDecision must have blocking_reasons and
        informational_notes fields."""
        import dataclasses
        fields = {f.name for f in dataclasses.fields(CorridorDecision)}
        assert "blocking_reasons" in fields
        assert "informational_notes" in fields
        assert "action_allowed" in fields

    def test_33_decision_has_count_properties(self):
        """CorridorDecision must have blocking_reasons_count and
        informational_notes_count properties."""
        corridor = AdaptiveProfitCorridor(dynamic_tp_enabled=True, locked_R=1.2)
        decision = corridor.evaluate(
            direction="BUY", entry_price=2000.0, initial_sl=1990.0,
            current_sl=2012.0, current_tp=2025.0, current_price=2020.0,
            atr=1.0, spread=0.05, regime=Regime.TREND,
            monitor_iterations=5, hold_seconds=120,
            seconds_since_last_tp_extension=999,
            mfe=2020.0, adaptive_trailing_enabled=True,
        )
        assert hasattr(decision, "blocking_reasons_count")
        assert hasattr(decision, "informational_notes_count")
        assert isinstance(decision.blocking_reasons_count, int)
        assert isinstance(decision.informational_notes_count, int)

    def test_34_to_dict_includes_counts(self):
        """to_dict must include blocking_reasons_count and
        informational_notes_count."""
        corridor = AdaptiveProfitCorridor(dynamic_tp_enabled=True, locked_R=1.2)
        decision = corridor.evaluate(
            direction="BUY", entry_price=2000.0, initial_sl=1990.0,
            current_sl=2012.0, current_tp=2025.0, current_price=2020.0,
            atr=1.0, spread=0.05, regime=Regime.TREND,
            monitor_iterations=5, hold_seconds=120,
            seconds_since_last_tp_extension=999,
            mfe=2020.0, adaptive_trailing_enabled=True,
        )
        d = decision.to_dict()
        assert "blocking_reasons_count" in d
        assert "informational_notes_count" in d
        assert "action_allowed" in d

    def test_35_action_allowed_true_for_modify_without_blocking(self):
        """action_allowed must be True for MODIFY without blocking reasons."""
        corridor = AdaptiveProfitCorridor(dynamic_tp_enabled=True, locked_R=1.2)
        decision = corridor.evaluate(
            direction="BUY", entry_price=2000.0, initial_sl=1990.0,
            current_sl=2012.0, current_tp=2025.0, current_price=2020.0,
            atr=1.0, spread=0.05, regime=Regime.TREND,
            monitor_iterations=5, hold_seconds=120,
            seconds_since_last_tp_extension=999,
            mfe=2020.0, adaptive_trailing_enabled=True,
        )
        if decision.action == CorridorAction.EXTEND_TP_AND_RAISE_SL:
            assert decision.action_allowed is True

    def test_36_unfavorable_modify_downgraded_to_hold(self):
        """If MODIFY would be unfavorable, action must be downgraded to HOLD."""
        corridor = AdaptiveProfitCorridor(dynamic_tp_enabled=True, locked_R=1.2)
        # current_sl already at max possible (no improvement possible)
        # current_sl=2028, proposed_sl would be max(2028, 2012, 2020-2.0=2018) = 2028
        # So proposed_sl == current_sl -> not favorable -> HOLD
        decision = corridor.evaluate(
            direction="BUY", entry_price=2000.0, initial_sl=1990.0,
            current_sl=2028.0,  # Already at the level corridor would propose
            current_tp=2040.0, current_price=2020.0,
            atr=1.0, spread=0.05, regime=Regime.TREND,
            monitor_iterations=5, hold_seconds=120,
            seconds_since_last_tp_extension=999,
            mfe=2020.0, adaptive_trailing_enabled=True,
        )
        # If proposed_sl == current_sl (no improvement), should be HOLD not MODIFY
        if not decision.favorable:
            assert decision.action in (CorridorAction.HOLD, CorridorAction.BLOCKED), \
                f"Unfavorable must be HOLD/BLOCKED, got {decision.action}"

    def test_37_no_contradiction_modify_with_favorable_false(self):
        """Hard invariant: no MODIFY action with favorable=False."""
        corridor = AdaptiveProfitCorridor(dynamic_tp_enabled=True, locked_R=1.2)
        # Test multiple scenarios
        test_cases = [
            # (current_sl, current_tp, current_price, spread_spike, news, regime)
            (2012.0, 2025.0, 2020.0, False, False, Regime.TREND),
            (2012.0, 2025.0, 2030.0, False, False, Regime.TREND),
            (2005.0, 2025.0, 2020.0, False, False, Regime.TREND),  # SL not protecting
            (2012.0, 2025.0, 2020.0, True, False, Regime.TREND),   # Spread spike
            (2012.0, 2025.0, 2020.0, False, True, Regime.TREND),    # News
            (2012.0, 2025.0, 2020.0, False, False, Regime.RANGE),   # Range
        ]
        for sl, tp, price, spike, news, regime in test_cases:
            decision = corridor.evaluate(
                direction="BUY", entry_price=2000.0, initial_sl=1990.0,
                current_sl=sl, current_tp=tp, current_price=price,
                atr=1.0, spread=0.05, regime=regime,
                monitor_iterations=5, hold_seconds=120,
                seconds_since_last_tp_extension=999,
                spread_spike_flag=spike, news_flag=news,
                mfe=price, adaptive_trailing_enabled=True,
            )
            if decision.action in (CorridorAction.EXTEND_TP_AND_RAISE_SL, CorridorAction.RAISE_SL_ONLY):
                assert decision.favorable is True, \
                    f"CONTRADICTION: action={decision.action} with favorable=False " \
                    f"(sl={sl}, tp={tp}, price={price}, spike={spike}, regime={regime})"
                assert decision.blocking_reasons_count == 0, \
                    f"CONTRADICTION: action={decision.action} with blocking_reasons_count>0"
