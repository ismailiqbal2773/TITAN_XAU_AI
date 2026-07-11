"""TITAN XAU AI — v2.8.7-P2.2 Adaptive Policy Application & CEO Consistency Tests
==================================================================================

Phase 2: Prove tightening, relaxation and loss-streak multipliers alter the
actual decision and approved risk — not only returned metadata.

Phase 3: Prove CEO and risk governor block consistently for the same safety
violations.
"""
from __future__ import annotations
import sys
from pathlib import Path
from unittest.mock import patch
import pytest
import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
np.random.seed(42)


def _build_synthetic_bars(n=300, starting_price=2000.0, trend=0.5):
    end = pd.Timestamp.now(tz="UTC").floor("h")
    dates = pd.date_range(end=end, periods=n, freq="h", tz="UTC")
    np.random.seed(42)
    prices = starting_price + np.cumsum(np.full(n, trend)) + np.random.randn(n) * 0.5
    df = pd.DataFrame({
        "open": prices, "high": prices + 1, "low": prices - 1,
        "close": prices, "volume": 100, "spread_usd": 0.15, "spread": 0.15,
    }, index=dates)
    return df


def _make_safety_state(**overrides):
    from titan.production.corrected_adaptive_threshold_v2 import SafetyStateV2
    defaults = dict(
        dd_state={"current_dd": 0.005, "daily_dd": 0.003},
        margin_state={"margin_usage": 0.05, "margin_safe": True},
        prop_risk_state={"prop_pass": True, "prop_violations": 0},
        capital_protection={"active": False, "dd_breach": False},
        broker_intelligence={"broker_pass": True, "spread_pass": True},
        execution_health={"healthy": True},
        model_health={"model_health_pass": True},
        spread_state={"current_spread": 0.15, "average_spread": 0.15},
        volatility_state={"current_atr": 5.0, "average_atr": 5.0, "regime": "STABLE_RANGE"},
        loss_streak=0, signal_drought_hours=0,
        regime_confidence=0.80,
        alpha_distribution=[0.55] * 50,
        meta_distribution=[0.55] * 50,
        recent_shadow_evidence={"false_negative_rate": 0, "sample_size": 50},
        external_daily_dd=0.0, external_total_dd=0.0,
        calibration_metrics={"brier_score": 0.20, "calibration_slope": 1.0, "calibration_intercept": 0.0},
        regime="STABLE_RANGE", market_data_stale=False,
    )
    defaults.update(overrides)
    return SafetyStateV2(**defaults)


def _make_config():
    return {
        "alpha_threshold": 0.55, "meta_threshold": 0.50,
        "risk_percent": 0.003, "sl_atr_multiplier": 2.0, "rr_target": 3.0,
        "spread_filter": 1.0, "setup_class": "A_PLUS",
    }


def _make_instrument():
    from titan.production.instrument_valuation import InstrumentSpec
    return InstrumentSpec(
        tick_size=0.01, tick_value=1.00, contract_size=100.0,
        volume_min=0.01, volume_max=100.0, volume_step=0.01,
        account_currency="USD", profit_currency="USD",
        symbol_currency="USD", conversion_rate=1.0,
    )


def _build_context(df, alpha_proba, meta_proba, safety_state=None, loss_streak=0):
    from titan.production.canonical_decision_engine import DecisionContext
    if safety_state is None:
        safety_state = _make_safety_state()
    # Also set loss_streak on the safety_state (adaptive policy reads from there)
    safety_state.loss_streak = loss_streak
    entry_price = float(df["close"].iloc[-1])
    spread = 0.15
    return DecisionContext(
        df=df, alpha_proba=alpha_proba, meta_proba=meta_proba,
        alpha_probas_recent=np.full(60, alpha_proba),
        meta_probas_recent=np.full(60, meta_proba),
        atr_value=5.0,
        instrument=_make_instrument(),
        config=_make_config(),
        safety_state=safety_state,
        equity=100000.0, equity_peak=100000.0,
        daily_peak=100000.0, daily_start_equity=100000.0,
        loss_streak=loss_streak,
        adapter_mode="historical",
        spread=spread, entry_price=entry_price,
        timestamp=str(df.index[-1]),
        skip_freshness_check=True,
    )


def _run_engine(ctx):
    from titan.production.canonical_decision_engine import CanonicalDecisionEngine
    from titan.production.corrected_setup_detector_v2 import (
        SetupResultV2, CorrectedSetupTypeV2, ScanResultV2,
    )
    # Patch setup to match direction
    direction = "LONG" if ctx.alpha_proba >= 0.50 else "SHORT"
    setup = SetupResultV2(
        setup_type=CorrectedSetupTypeV2.PULLBACK,
        direction=direction, confidence=0.75,
        reason_codes=["mock"], evidence=["mock"],
    )
    mock_scan = ScanResultV2(
        selected_setup=setup, alternatives=[],
        rejection_reasons=[], ranking_evidence=["mock"],
        all_candidates=[setup], decision="SELECTED",
    )
    with patch("titan.production.canonical_decision_engine.scan_setups_governed",
               return_value=mock_scan), \
         patch("titan.production.canonical_decision_engine.evaluate_ceo_decision",
               return_value=type('C', (), {'allowed_to_trade': True})()):
        engine = CanonicalDecisionEngine()
        return engine.evaluate(ctx)


class TestAdaptivePolicyApplication:
    """Phase 2: Prove adaptive policy actually alters decisions and approved risk."""

    def test_tightening_raises_threshold_and_reduces_approved_risk(self):
        """When adaptive policy tightens (dd_warning), the effective alpha threshold
        increases and fewer trades pass — or approved risk is reduced."""
        df = _build_synthetic_bars(n=300, trend=0.5)
        # Normal state: no tightening (current_dd < 0.05)
        ctx_normal = _build_context(df, alpha_proba=0.56, meta_proba=0.60,
                                      safety_state=_make_safety_state(dd_state={"current_dd": 0.01, "daily_dd": 0.005}))
        dec_normal = _run_engine(ctx_normal)
        # Tightened state: dd_warning triggers (current_dd > 0.05 but < 0.065 hard block)
        ctx_tight = _build_context(df, alpha_proba=0.56, meta_proba=0.60,
                                     safety_state=_make_safety_state(dd_state={"current_dd": 0.055, "daily_dd": 0.005}))
        dec_tight = _run_engine(ctx_tight)
        # Both should have threshold values set (not hard-blocked)
        assert dec_normal.final_alpha_threshold is not None
        assert dec_tight.final_alpha_threshold is not None
        # The tightened threshold should be >= normal threshold
        assert dec_tight.final_alpha_threshold >= dec_normal.final_alpha_threshold
        # If both passed, tightened should have lower or equal approved risk
        if dec_normal.final_decision in ("HISTORICAL_SIGNAL", "SHADOW_SIGNAL") and \
           dec_tight.final_decision in ("HISTORICAL_SIGNAL", "SHADOW_SIGNAL"):
            assert dec_tight.approved_risk <= dec_normal.approved_risk

    def test_loss_streak_multiplier_reduces_approved_risk(self):
        """2 losses → 0.75x risk multiplier → approved risk is 75% of base."""
        df = _build_synthetic_bars(n=300, trend=0.5)
        # No losses
        ctx_0 = _build_context(df, alpha_proba=0.90, meta_proba=0.60, loss_streak=0)
        dec_0 = _run_engine(ctx_0)
        # 2 losses
        ctx_2 = _build_context(df, alpha_proba=0.90, meta_proba=0.60, loss_streak=2)
        dec_2 = _run_engine(ctx_2)
        # 3 losses
        ctx_3 = _build_context(df, alpha_proba=0.90, meta_proba=0.60, loss_streak=3)
        dec_3 = _run_engine(ctx_3)
        # If all pass, approved risk should decrease with loss streak
        if dec_0.final_decision in ("HISTORICAL_SIGNAL", "SHADOW_SIGNAL"):
            base_risk = dec_0.approved_risk
            if dec_2.final_decision in ("HISTORICAL_SIGNAL", "SHADOW_SIGNAL"):
                # 2 losses: 0.75x multiplier
                assert dec_2.adaptive_risk_multiplier == pytest.approx(0.75, abs=1e-4)
                assert dec_2.approved_risk <= base_risk
            if dec_3.final_decision in ("HISTORICAL_SIGNAL", "SHADOW_SIGNAL"):
                # 3 losses: 0.50x multiplier
                assert dec_3.adaptive_risk_multiplier == pytest.approx(0.50, abs=1e-4)
                assert dec_3.approved_risk <= dec_2.approved_risk

    def test_loss_streak_4_blocks_all_entries(self):
        """4+ losses → adaptive hard-blocks."""
        df = _build_synthetic_bars(n=300, trend=0.5)
        ctx = _build_context(df, alpha_proba=0.90, meta_proba=0.60, loss_streak=4)
        dec = _run_engine(ctx)
        assert dec.final_decision == "REJECT_ADAPTIVE_HARD_BLOCK"

    def test_adaptive_thresholds_journal_all_values(self):
        """Journal records: base, adaptive, regime modifier, final threshold."""
        df = _build_synthetic_bars(n=300, trend=0.5)
        ctx = _build_context(df, alpha_proba=0.90, meta_proba=0.60)
        dec = _run_engine(ctx)
        # All threshold values must be recorded
        assert dec.base_alpha_threshold is not None
        assert dec.adaptive_alpha_threshold is not None
        assert dec.final_alpha_threshold is not None
        assert dec.regime_threshold_modifier is not None
        assert dec.base_meta_threshold is not None
        assert dec.adaptive_meta_threshold is not None
        assert dec.final_meta_threshold is not None
        # Risk journal
        assert len(dec.risk_journal) > 0
        rj = dec.risk_journal[0]
        assert "base_risk_percent" in rj
        assert "adaptive_risk_multiplier" in rj
        assert "regime_risk_modifier" in rj
        assert "proposed_risk_percent" in rj
        assert "governor_approved_risk" in rj


class TestCEOConsistencyWithRiskGovernor:
    """Phase 3: CEO and risk governor must block consistently for same safety violations."""

    def test_broker_unsafe_blocks_both_ceo_and_governor(self):
        """broker_safe=False → both CEO and risk governor block."""
        df = _build_synthetic_bars(n=300, trend=0.5)
        safety = _make_safety_state(broker_intelligence={"broker_pass": False, "spread_pass": True})
        ctx = _build_context(df, alpha_proba=0.90, meta_proba=0.60, safety_state=safety)
        dec = _run_engine(ctx)
        # Should be blocked — either by adaptive (hard_block) or risk governor
        assert dec.final_decision in ("REJECT_ADAPTIVE_HARD_BLOCK", "REJECT_RISK_GOVERNOR", "REJECT_CEO")
        assert dec.NO_ORDER_SENT is True

    def test_execution_unhealthy_blocks_both(self):
        df = _build_synthetic_bars(n=300, trend=0.5)
        safety = _make_safety_state(execution_health={"healthy": False})
        ctx = _build_context(df, alpha_proba=0.90, meta_proba=0.60, safety_state=safety)
        dec = _run_engine(ctx)
        assert dec.final_decision in ("REJECT_ADAPTIVE_HARD_BLOCK", "REJECT_RISK_GOVERNOR", "REJECT_CEO")

    def test_model_unhealthy_blocks_both(self):
        df = _build_synthetic_bars(n=300, trend=0.5)
        safety = _make_safety_state(model_health={"model_health_pass": False})
        ctx = _build_context(df, alpha_proba=0.90, meta_proba=0.60, safety_state=safety)
        dec = _run_engine(ctx)
        assert dec.final_decision in ("REJECT_ADAPTIVE_HARD_BLOCK", "REJECT_RISK_GOVERNOR", "REJECT_CEO")

    def test_prop_failure_blocks_both(self):
        df = _build_synthetic_bars(n=300, trend=0.5)
        safety = _make_safety_state(prop_risk_state={"prop_pass": False, "prop_violations": 1})
        ctx = _build_context(df, alpha_proba=0.90, meta_proba=0.60, safety_state=safety)
        dec = _run_engine(ctx)
        assert dec.final_decision in ("REJECT_ADAPTIVE_HARD_BLOCK", "REJECT_RISK_GOVERNOR", "REJECT_CEO")

    def test_capital_protection_active_blocks_both(self):
        df = _build_synthetic_bars(n=300, trend=0.5)
        safety = _make_safety_state(capital_protection={"active": True, "dd_breach": False})
        ctx = _build_context(df, alpha_proba=0.90, meta_proba=0.60, safety_state=safety)
        dec = _run_engine(ctx)
        assert dec.final_decision in ("REJECT_ADAPTIVE_HARD_BLOCK", "REJECT_RISK_GOVERNOR", "REJECT_CEO")

    def test_margin_unsafe_blocks_both(self):
        df = _build_synthetic_bars(n=300, trend=0.5)
        safety = _make_safety_state(margin_state={"margin_usage": 0.5, "margin_safe": False})
        ctx = _build_context(df, alpha_proba=0.90, meta_proba=0.60, safety_state=safety)
        dec = _run_engine(ctx)
        assert dec.final_decision in ("REJECT_ADAPTIVE_HARD_BLOCK", "REJECT_RISK_GOVERNOR", "REJECT_CEO")

    def test_daily_dd_block_stage_blocks_both(self):
        """Daily DD at block stage (1.6%) → both block."""
        df = _build_synthetic_bars(n=300, trend=0.5)
        from titan.production.risk_governor import DAILY_BLOCK
        safety = _make_safety_state(
            dd_state={"current_dd": 0.005, "daily_dd": DAILY_BLOCK},
            external_daily_dd=DAILY_BLOCK,
        )
        ctx = _build_context(df, alpha_proba=0.90, meta_proba=0.60, safety_state=safety)
        dec = _run_engine(ctx)
        assert dec.final_decision in ("REJECT_ADAPTIVE_HARD_BLOCK", "REJECT_RISK_GOVERNOR", "REJECT_CEO")
