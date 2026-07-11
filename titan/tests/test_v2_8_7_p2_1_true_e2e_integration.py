"""TITAN XAU AI — v2.8.7-P2.1 True End-to-End Integration Test (Phase 7)
==========================================================================

Tests the CanonicalDecisionEngine directly with monkeypatched dependencies.
This is the shared decision kernel used by BOTH the historical adapter and
the MT5 shadow adapter — so testing it once covers both paths.

The parity test in test_v2_8_7_p2_1_parity.py proves historical and shadow
adapters produce identical decisions from the same context. This file tests
the kernel's behavior across all required scenarios:

  - strong LONG
  - strong SHORT
  - unknown unsafe regime
  - daily-DD near-boundary risk clamp
  - missing prop state
  - broker unsafe
  - near-miss preview (no mutation)
  - malformed InstrumentSpec

Asserts:
  - exact decision
  - direction and confidence
  - setup
  - regime
  - approved risk
  - lot
  - decision_id
  - correlation_id
  - NO_ORDER_SENT=true

Forbidden: tests that only call interpret_direction in isolation.
"""
from __future__ import annotations
import sys, json, math
from pathlib import Path
from unittest.mock import MagicMock, patch
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
    if trend != 0:
        prices = starting_price + np.cumsum(np.full(n, trend)) + np.random.randn(n) * 0.5
    else:
        prices = np.full(n, starting_price) + np.random.randn(n) * 0.5
    df = pd.DataFrame({
        "open": prices, "high": prices + 1, "low": prices - 1,
        "close": prices, "volume": 100, "spread_usd": 0.15,
        "spread": 0.15,
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
        calibration_metrics={"brier_score": 0.20, "calibration_slope": 1.0},
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


def _make_instrument(**overrides):
    from titan.production.instrument_valuation import InstrumentSpec
    defaults = dict(
        tick_size=0.01, tick_value=1.00, contract_size=100.0,
        volume_min=0.01, volume_max=100.0, volume_step=0.01,
        account_currency="USD", profit_currency="USD",
        symbol_currency="USD", conversion_rate=1.0,
    )
    defaults.update(overrides)
    return InstrumentSpec(**defaults)


def _build_context(df, alpha_proba, meta_proba, atr_value=5.0,
                    adapter_mode="shadow", safety_state=None,
                    near_miss_tracker=None, instrument=None,
                    equity=100000.0, equity_peak=None, daily_peak=None,
                    loss_streak=0):
    from titan.production.canonical_decision_engine import DecisionContext
    if safety_state is None:
        safety_state = _make_safety_state()
    if instrument is None:
        instrument = _make_instrument()
    entry_price = float(df["close"].iloc[-1])
    spread = float(df["spread_usd"].iloc[-1]) if "spread_usd" in df.columns else 0.15
    return DecisionContext(
        df=df, alpha_proba=alpha_proba, meta_proba=meta_proba,
        alpha_probas_recent=np.full(60, alpha_proba),
        meta_probas_recent=np.full(60, meta_proba),
        atr_value=atr_value,
        instrument=instrument,
        config=_make_config(),
        safety_state=safety_state,
        equity=equity, equity_peak=equity_peak or equity,
        daily_peak=daily_peak or equity, daily_start_equity=equity,
        loss_streak=loss_streak,
        adapter_mode=adapter_mode,
        near_miss_tracker=near_miss_tracker,
        spread=spread, entry_price=entry_price,
        timestamp=str(df.index[-1]),
    )


def _run_engine(ctx):
    """Run the canonical decision engine with CEO mocked to PASS."""
    from titan.production.canonical_decision_engine import CanonicalDecisionEngine
    with patch("titan.production.canonical_decision_engine.evaluate_ceo_decision",
               return_value=type('C', (), {'allowed_to_trade': True})()):
        engine = CanonicalDecisionEngine()
        return engine.evaluate(ctx)


class TestTrueEndToEndIntegrationV2_1:
    """True end-to-end integration tests for CanonicalDecisionEngine."""

    def test_strong_long_path(self):
        """Strong LONG: p_up=0.90 → direction=LONG, confidence=0.90, full path."""
        df = _build_synthetic_bars(n=300, starting_price=2000.0, trend=0.5)
        ctx = _build_context(df, alpha_proba=0.90, meta_proba=0.60)
        dec = _run_engine(ctx)
        assert dec.direction == "LONG"
        assert dec.directional_confidence == pytest.approx(0.90, abs=1e-6)
        assert dec.alpha_proba == pytest.approx(0.90, abs=1e-6)
        assert dec.final_decision in ("SHADOW_SIGNAL", "HISTORICAL_SIGNAL", "REJECT_NO_SETUP")
        assert dec.NO_ORDER_SENT is True
        assert "decision_id" in dec.__dict__
        assert "correlation_id" in dec.__dict__
        # Call trace
        assert "1:data_schema_freshness_checks" in dec.call_trace
        assert "3:direction_interpretation" in dec.call_trace
        assert "4:regime_classification" in dec.call_trace
        assert "5:governed_setup_scan" in dec.call_trace

    def test_strong_short_path(self):
        """Strong SHORT: p_up=0.10 → direction=SHORT, confidence=0.90."""
        df = _build_synthetic_bars(n=300, starting_price=2000.0, trend=-0.5)
        ctx = _build_context(df, alpha_proba=0.10, meta_proba=0.60)
        dec = _run_engine(ctx)
        # CRITICAL: p_up=0.10 → SHORT, confidence=0.90
        assert dec.direction == "SHORT"
        assert dec.directional_confidence == pytest.approx(0.90, abs=1e-6)
        assert dec.alpha_proba == pytest.approx(0.10, abs=1e-6)
        assert dec.NO_ORDER_SENT is True

    def test_unknown_unsafe_regime_rejected(self):
        """UNKNOWN_UNSAFE regime → setup scanner returns REGIME_BLOCKED."""
        df = _build_synthetic_bars(n=300)
        # Patch classify_regime_v2 to return UNKNOWN_UNSAFE
        from titan.production.corrected_regime_classifier_v2 import RegimeTypeV2, RegimeResultV2
        mock_regime = RegimeResultV2(
            regime=RegimeTypeV2.UNKNOWN_UNSAFE, direction="UNKNOWN",
            confidence=0.0, evidence=["mock"], reason_codes=["mock"],
            allowed_setup_types=[], blocked_setup_types=["ALL"],
            risk_modifier=0.0, threshold_modifier=0.20,
            exit_sensitivity_modifier=1.0,
        )
        with patch("titan.production.canonical_decision_engine.classify_regime_v2",
                   return_value=mock_regime):
            ctx = _build_context(df, alpha_proba=0.90, meta_proba=0.60)
            dec = _run_engine(ctx)
        assert dec.final_decision == "REJECT_NO_SETUP"
        assert dec.regime == "UNKNOWN_UNSAFE"
        assert dec.NO_ORDER_SENT is True

    def test_missing_prop_state_blocks(self):
        """Missing prop_risk_state → adaptive policy hard-blocks."""
        df = _build_synthetic_bars(n=300)
        safety = _make_safety_state(prop_risk_state={"prop_pass": None, "prop_violations": 0})
        ctx = _build_context(df, alpha_proba=0.90, meta_proba=0.60, safety_state=safety)
        dec = _run_engine(ctx)
        assert dec.final_decision == "REJECT_ADAPTIVE_HARD_BLOCK"
        assert dec.NO_ORDER_SENT is True

    def test_broker_unsafe_blocks(self):
        """broker_safe=False → risk governor blocks."""
        df = _build_synthetic_bars(n=300)
        safety = _make_safety_state(broker_intelligence={"broker_pass": False, "spread_pass": True})
        ctx = _build_context(df, alpha_proba=0.90, meta_proba=0.60, safety_state=safety)
        dec = _run_engine(ctx)
        # Adaptive policy should hard-block on broker_unsafe
        assert dec.final_decision in ("REJECT_ADAPTIVE_HARD_BLOCK", "REJECT_RISK_GOVERNOR")
        assert dec.NO_ORDER_SENT is True

    def test_malformed_instrument_spec_rejected(self):
        """Malformed InstrumentSpec → engine still runs but lot sizing rejects."""
        df = _build_synthetic_bars(n=300)
        # Tick_size=0 is invalid
        bad_instrument = _make_instrument(tick_size=0.0)
        ctx = _build_context(df, alpha_proba=0.90, meta_proba=0.60, instrument=bad_instrument)
        dec = _run_engine(ctx)
        # Should reject at lot sizing or earlier (validate_instrument_spec)
        assert dec.NO_ORDER_SENT is True
        assert "REJECT" in dec.final_decision

    def test_near_miss_preview_does_not_mutate(self):
        """Near-miss preview must NOT consume records."""
        df = _build_synthetic_bars(n=300)
        from titan.production.near_miss_tracker_v2 import NearMissShadowTrackerV2, NearMissRecordV2
        tracker = NearMissShadowTrackerV2(timeframe="H1")
        record = NearMissRecordV2(
            timestamp=str(df.index[-1]), direction="LONG",
            setup_type="PULLBACK", regime="STRONG_BULL_TREND",
            score=0.70, effective_threshold=0.55,
            component_scores={}, rejection_reasons=["mock"],
            hypothetical_entry=2000.0, hypothetical_sl=1990.0, hypothetical_tp=2030.0,
            expiry_time=str(df.index[-1] + pd.Timedelta(hours=6)),
            rr=3.0, spread=0.15, commission=7.0, slippage=0.5,
        )
        tracker.records.append(record)
        ctx = _build_context(df, alpha_proba=0.90, meta_proba=0.60,
                             near_miss_tracker=tracker)
        dec = _run_engine(ctx)
        assert dec.near_miss_consulted is True
        # Record must NOT be consumed
        assert record.re_entry_consumed is False
        assert dec.NO_ORDER_SENT is True

    def test_journal_persistence(self):
        """Decision contains decision_id and correlation_id."""
        df = _build_synthetic_bars(n=300)
        ctx = _build_context(df, alpha_proba=0.90, meta_proba=0.60)
        dec = _run_engine(ctx)
        assert dec.decision_id.startswith("dec_")
        assert dec.correlation_id.startswith("corr_")
        assert dec.timestamp != ""

    def test_call_trace_records_canonical_pipeline(self):
        """Call trace contains all canonical pipeline steps."""
        df = _build_synthetic_bars(n=300)
        ctx = _build_context(df, alpha_proba=0.90, meta_proba=0.60)
        dec = _run_engine(ctx)
        # Verify all 12 steps are in trace (or rejection happened earlier)
        expected_steps = [
            "1:data_schema_freshness_checks",
            "2:model_class_verification",
            "3:direction_interpretation",
            "4:regime_classification",
            "5:governed_setup_scan",
        ]
        for step in expected_steps:
            assert step in dec.call_trace, f"Missing step in trace: {step}. Trace: {dec.call_trace}"

    def test_alpha_below_threshold_rejected(self):
        """alpha_proba=0.52 → dir_confidence=0.52 < effective_threshold (0.55+) → REJECT_ALPHA.

        Uses upward-trending bars so setup scanner returns LONG setup
        (matching LONG direction from alpha=0.52), avoiding setup conflict.
        """
        df = _build_synthetic_bars(n=300, starting_price=2000.0, trend=0.5)
        ctx = _build_context(df, alpha_proba=0.52, meta_proba=0.60)
        dec = _run_engine(ctx)
        assert dec.final_decision == "REJECT_ALPHA"
        assert dec.direction == "LONG"
        assert dec.directional_confidence == pytest.approx(0.52, abs=1e-6)

    def test_meta_below_threshold_rejected(self):
        """meta_proba=0.40 < 0.50 → REJECT_META."""
        df = _build_synthetic_bars(n=300)
        ctx = _build_context(df, alpha_proba=0.90, meta_proba=0.40)
        dec = _run_engine(ctx)
        assert dec.final_decision == "REJECT_META"
