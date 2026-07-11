"""TITAN XAU AI — v2.8.7-P2.1 Phase 7 Historical/Shadow Parity Test
=====================================================================

Parity test: Given identical bars, probabilities, InstrumentSpec, account
state and configuration, the historical adapter decision MUST equal the
shadow adapter decision.

Asserts equality for:
  - direction
  - confidence
  - regime
  - setup
  - threshold
  - approved risk
  - lot
  - SL/TP
  - rejection reason

Both adapters construct a DecisionContext and call
CanonicalDecisionEngine.evaluate(). The kernel is pure; the only
difference between adapters is adapter_mode ("shadow" vs "historical")
and the near_miss_tracker (shadow has one, historical doesn't).
"""
from __future__ import annotations
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


def _build_synthetic_bars(n=300, starting_price=2000.0, trend=0.5):
    end = pd.Timestamp.now(tz="UTC").floor("h")
    dates = pd.date_range(end=end, periods=n, freq="h", tz="UTC")
    np.random.seed(42)
    prices = starting_price + np.cumsum(np.full(n, trend)) + np.random.randn(n) * 0.5
    df = pd.DataFrame({
        "open": prices, "high": prices + 1, "low": prices - 1,
        "close": prices, "volume": 100, "spread_usd": 0.15,
        "spread": 0.15,
    }, index=dates)
    return df


def _make_safety_state():
    from titan.production.corrected_adaptive_threshold_v2 import SafetyStateV2
    return SafetyStateV2(
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


def _build_context(df, alpha_proba, meta_proba, atr_value, adapter_mode,
                    near_miss_tracker=None):
    from titan.production.canonical_decision_engine import DecisionContext
    entry_price = float(df["close"].iloc[-1])
    spread = float(df["spread_usd"].iloc[-1])
    return DecisionContext(
        df=df, alpha_proba=alpha_proba, meta_proba=meta_proba,
        alpha_probas_recent=np.full(60, alpha_proba),
        meta_probas_recent=np.full(60, meta_proba),
        atr_value=atr_value,
        instrument=_make_instrument(),
        config=_make_config(),
        safety_state=_make_safety_state(),
        equity=100000.0, equity_peak=100000.0,
        daily_peak=100000.0, daily_start_equity=100000.0,
        existing_daily_open_risk=0.0,
        existing_total_open_risk=0.0,
        existing_combined_risk=0.0,
        loss_streak=0,
        adapter_mode=adapter_mode,
        near_miss_tracker=near_miss_tracker,
        spread=spread, entry_price=entry_price,
        timestamp=str(df.index[-1]),
    )


def _run_engine(ctx):
    """Run the canonical decision engine with CEO mocked to PASS."""
    from titan.production.canonical_decision_engine import CanonicalDecisionEngine
    with patch("titan.production.ceo_ai_governance.evaluate_ceo_decision",
               return_value=type('C', (), {'allowed_to_trade': True})()):
        engine = CanonicalDecisionEngine()
        return engine.evaluate(ctx)


class TestHistoricalShadowParity:
    """Parity: historical adapter decision == shadow adapter decision."""

    def test_strong_long_parity(self):
        """Identical context produces identical decisions for both adapters."""
        df = _build_synthetic_bars(n=300, starting_price=2000.0, trend=0.5)
        from titan.production.near_miss_tracker_v2 import NearMissShadowTrackerV2
        ctx_shadow = _build_context(df, alpha_proba=0.90, meta_proba=0.60,
                                     atr_value=5.0, adapter_mode="shadow",
                                     near_miss_tracker=NearMissShadowTrackerV2(timeframe="H1"))
        ctx_hist = _build_context(df, alpha_proba=0.90, meta_proba=0.60,
                                   atr_value=5.0, adapter_mode="historical",
                                   near_miss_tracker=None)
        dec_shadow = _run_engine(ctx_shadow)
        dec_hist = _run_engine(ctx_hist)
        # Parity assertions
        assert dec_shadow.direction == dec_hist.direction
        assert dec_shadow.directional_confidence == dec_hist.directional_confidence
        assert dec_shadow.alpha_proba == dec_hist.alpha_proba
        assert dec_shadow.meta_proba == dec_hist.meta_proba
        assert dec_shadow.regime == dec_hist.regime
        assert dec_shadow.regime_confidence == dec_hist.regime_confidence
        assert dec_shadow.setup_selected == dec_hist.setup_selected
        assert dec_shadow.adaptive_alpha_threshold == dec_hist.adaptive_alpha_threshold
        assert dec_shadow.adaptive_meta_threshold == dec_hist.adaptive_meta_threshold
        assert dec_shadow.adaptive_risk_multiplier == dec_hist.adaptive_risk_multiplier
        assert dec_shadow.approved_risk == dec_hist.approved_risk
        assert dec_shadow.lot_size == dec_hist.lot_size
        assert dec_shadow.sl_price == dec_hist.sl_price
        assert dec_shadow.tp_price == dec_hist.tp_price
        assert dec_shadow.entry_price == dec_hist.entry_price
        assert dec_shadow.final_decision == dec_hist.final_decision or (
            dec_shadow.final_decision == "SHADOW_SIGNAL" and dec_hist.final_decision == "HISTORICAL_SIGNAL"
        )
        assert dec_shadow.reject_reason == dec_hist.reject_reason

    def test_strong_short_parity(self):
        df = _build_synthetic_bars(n=300, starting_price=2000.0, trend=-0.5)
        ctx_shadow = _build_context(df, alpha_proba=0.10, meta_proba=0.60,
                                     atr_value=5.0, adapter_mode="shadow")
        ctx_hist = _build_context(df, alpha_proba=0.10, meta_proba=0.60,
                                   atr_value=5.0, adapter_mode="historical")
        dec_shadow = _run_engine(ctx_shadow)
        dec_hist = _run_engine(ctx_hist)
        assert dec_shadow.direction == "SHORT"
        assert dec_shadow.directional_confidence == pytest.approx(0.90, abs=1e-6)
        assert dec_shadow.direction == dec_hist.direction
        assert dec_shadow.directional_confidence == dec_hist.directional_confidence
        assert dec_shadow.regime == dec_hist.regime
        assert dec_shadow.setup_selected == dec_hist.setup_selected
        assert dec_shadow.approved_risk == dec_hist.approved_risk
        assert dec_shadow.lot_size == dec_hist.lot_size
        assert dec_shadow.sl_price == dec_hist.sl_price
        assert dec_shadow.tp_price == dec_hist.tp_price

    def test_alpha_below_threshold_parity(self):
        df = _build_synthetic_bars(n=300)
        ctx_shadow = _build_context(df, alpha_proba=0.50, meta_proba=0.60,
                                     atr_value=5.0, adapter_mode="shadow")
        ctx_hist = _build_context(df, alpha_proba=0.50, meta_proba=0.60,
                                   atr_value=5.0, adapter_mode="historical")
        dec_shadow = _run_engine(ctx_shadow)
        dec_hist = _run_engine(ctx_hist)
        # Both should reject for the same reason
        assert "REJECT" in dec_shadow.final_decision
        assert "REJECT" in dec_hist.final_decision
        assert dec_shadow.reject_reason == dec_hist.reject_reason
        assert dec_shadow.direction == dec_hist.direction

    def test_meta_below_threshold_parity(self):
        df = _build_synthetic_bars(n=300)
        ctx_shadow = _build_context(df, alpha_proba=0.90, meta_proba=0.40,
                                     atr_value=5.0, adapter_mode="shadow")
        ctx_hist = _build_context(df, alpha_proba=0.90, meta_proba=0.40,
                                   atr_value=5.0, adapter_mode="historical")
        dec_shadow = _run_engine(ctx_shadow)
        dec_hist = _run_engine(ctx_hist)
        assert dec_shadow.reject_reason == dec_hist.reject_reason
        assert dec_shadow.final_decision == dec_hist.final_decision or (
            dec_shadow.final_decision == "SHADOW_SIGNAL" and dec_hist.final_decision == "HISTORICAL_SIGNAL"
        )

    def test_call_trace_identical_except_near_miss(self):
        """Call traces should be identical except shadow has near-miss preview step."""
        df = _build_synthetic_bars(n=300, starting_price=2000.0, trend=0.5)
        ctx_shadow = _build_context(df, alpha_proba=0.90, meta_proba=0.60,
                                     atr_value=5.0, adapter_mode="shadow")
        ctx_hist = _build_context(df, alpha_proba=0.90, meta_proba=0.60,
                                   atr_value=5.0, adapter_mode="historical")
        dec_shadow = _run_engine(ctx_shadow)
        dec_hist = _run_engine(ctx_hist)
        # Shadow may have an extra "9:near_miss_preview" step
        # All other steps should match
        common = [s for s in dec_shadow.call_trace if s in dec_hist.call_trace]
        assert len(common) == len(dec_hist.call_trace)  # historical steps are subset

    def test_shadow_does_not_mutate_near_miss_records(self):
        """Shadow mode must NOT call consume_re_entry; only preview."""
        df = _build_synthetic_bars(n=300)
        from titan.production.near_miss_tracker_v2 import NearMissShadowTrackerV2, NearMissRecordV2
        tracker = NearMissShadowTrackerV2(timeframe="H1")
        # Manually add a record to test
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
                             atr_value=5.0, adapter_mode="shadow",
                             near_miss_tracker=tracker)
        _run_engine(ctx)
        # Record must NOT be consumed
        assert record.re_entry_consumed is False, \
            "Shadow mode mutated near-miss record — only preview is allowed"
