"""TITAN XAU AI — v2.8.7-P2.2 True Adapter Parity Test
========================================================

Phase 4: True integration test that invokes BOTH:
  1. actual shadow adapter (ShadowAdapter)
  2. actual historical adapter (HistoricalAdapter)

with identical bars, probabilities, InstrumentSpec, configuration and
account state. Asserts exact equality for all decision fields.

This is NOT a synthetic direct call to the same engine — it invokes the
actual adapter classes which construct the context independently.
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


class TestTrueAdapterParity:
    """True integration test: HistoricalAdapter vs ShadowAdapter with identical inputs."""

    def test_strong_long_parity(self):
        """Both adapters produce identical decisions for identical LONG context."""
        from titan.production.decision_adapters import HistoricalAdapter, ShadowAdapter
        from titan.production.corrected_setup_detector_v2 import (
            SetupResultV2, CorrectedSetupTypeV2, ScanResultV2,
        )

        df = _build_synthetic_bars(n=300, trend=0.5)
        alpha_proba = 0.90
        meta_proba = 0.60
        atr_value = 5.0
        entry_price = float(df["close"].iloc[-1])
        spread = 0.15
        timestamp = str(df.index[-1])
        alpha_dist = np.full(60, alpha_proba)
        meta_dist = np.full(60, meta_proba)
        safety = _make_safety_state()
        config = _make_config()
        instrument = _make_instrument()

        # Mock setup to return LONG (matching alpha=0.90 → LONG)
        setup = SetupResultV2(
            setup_type=CorrectedSetupTypeV2.PULLBACK,
            direction="LONG", confidence=0.75,
            reason_codes=["mock"], evidence=["mock"],
        )
        mock_scan = ScanResultV2(
            selected_setup=setup, alternatives=[],
            rejection_reasons=[], ranking_evidence=["mock"],
            all_candidates=[setup], decision="SELECTED",
        )

        # Historical adapter
        hist_adapter = HistoricalAdapter(
            instrument=instrument, config=config, safety_state=safety,
            equity=100000.0, equity_peak=100000.0,
            daily_peak=100000.0, daily_start_equity=100000.0,
        )
        # Shadow adapter
        shadow_adapter = ShadowAdapter(
            instrument=instrument, config=config, safety_state=safety,
            equity=100000.0, equity_peak=100000.0,
            daily_peak=100000.0, daily_start_equity=100000.0,
        )

        with patch("titan.production.canonical_decision_engine.scan_setups_governed",
                   return_value=mock_scan), \
             patch("titan.production.canonical_decision_engine.evaluate_ceo_decision",
                   return_value=type('C', (), {'allowed_to_trade': True})()):
            # Historical adapter uses bar index and windowed df
            i = len(df) - 1
            dec_hist = hist_adapter.evaluate_bar(
                df=df, i=i,
                alpha_proba=alpha_proba, meta_proba=meta_proba,
                atr_value=atr_value, entry_price=entry_price,
                spread=spread, timestamp=timestamp,
                alpha_dist=alpha_dist, meta_dist=meta_dist,
            )
            # Shadow adapter uses full df
            dec_shadow = shadow_adapter.evaluate_bar(
                df=df,
                alpha_proba=alpha_proba, meta_proba=meta_proba,
                atr_value=atr_value, entry_price=entry_price,
                spread=spread, timestamp=timestamp,
                alpha_probas_recent=alpha_dist,
                meta_probas_recent=meta_dist,
            )

        # Assert exact equality for all decision fields (except adapter_mode)
        assert dec_hist.direction == dec_shadow.direction
        assert dec_hist.directional_confidence == dec_shadow.directional_confidence
        assert dec_hist.alpha_proba == dec_shadow.alpha_proba
        assert dec_hist.meta_proba == dec_shadow.meta_proba
        assert dec_hist.regime == dec_shadow.regime
        assert dec_hist.regime_confidence == dec_shadow.regime_confidence
        assert dec_hist.setup_selected == dec_shadow.setup_selected
        assert dec_hist.base_alpha_threshold == dec_shadow.base_alpha_threshold
        assert dec_hist.adaptive_alpha_threshold == dec_shadow.adaptive_alpha_threshold
        assert dec_hist.final_alpha_threshold == dec_shadow.final_alpha_threshold
        assert dec_hist.base_meta_threshold == dec_shadow.base_meta_threshold
        assert dec_hist.adaptive_meta_threshold == dec_shadow.adaptive_meta_threshold
        assert dec_hist.final_meta_threshold == dec_shadow.final_meta_threshold
        assert dec_hist.adaptive_risk_multiplier == dec_shadow.adaptive_risk_multiplier
        assert dec_hist.approved_risk == dec_shadow.approved_risk
        assert dec_hist.lot_size == dec_shadow.lot_size
        assert dec_hist.sl_price == dec_shadow.sl_price
        assert dec_hist.tp_price == dec_shadow.tp_price
        assert dec_hist.entry_price == dec_shadow.entry_price
        assert dec_hist.ceo_decision == dec_shadow.ceo_decision
        assert dec_hist.reject_reason == dec_shadow.reject_reason
        # final_decision differs only by adapter prefix
        assert dec_hist.final_decision.replace("HISTORICAL", "SHADOW") == dec_shadow.final_decision or \
               dec_hist.final_decision == dec_shadow.final_decision

    def test_strong_short_parity(self):
        """Both adapters produce identical decisions for identical SHORT context."""
        from titan.production.decision_adapters import HistoricalAdapter, ShadowAdapter
        from titan.production.corrected_setup_detector_v2 import (
            SetupResultV2, CorrectedSetupTypeV2, ScanResultV2,
        )

        df = _build_synthetic_bars(n=300, trend=-0.5)
        alpha_proba = 0.10  # SHORT
        meta_proba = 0.60
        atr_value = 5.0
        entry_price = float(df["close"].iloc[-1])
        spread = 0.15
        timestamp = str(df.index[-1])
        alpha_dist = np.full(60, alpha_proba)
        meta_dist = np.full(60, meta_proba)
        safety = _make_safety_state()
        config = _make_config()
        instrument = _make_instrument()

        setup = SetupResultV2(
            setup_type=CorrectedSetupTypeV2.PULLBACK,
            direction="SHORT", confidence=0.75,
            reason_codes=["mock"], evidence=["mock"],
        )
        mock_scan = ScanResultV2(
            selected_setup=setup, alternatives=[],
            rejection_reasons=[], ranking_evidence=["mock"],
            all_candidates=[setup], decision="SELECTED",
        )

        hist_adapter = HistoricalAdapter(
            instrument=instrument, config=config, safety_state=safety,
            equity=100000.0, equity_peak=100000.0,
            daily_peak=100000.0, daily_start_equity=100000.0,
        )
        shadow_adapter = ShadowAdapter(
            instrument=instrument, config=config, safety_state=safety,
            equity=100000.0, equity_peak=100000.0,
            daily_peak=100000.0, daily_start_equity=100000.0,
        )

        with patch("titan.production.canonical_decision_engine.scan_setups_governed",
                   return_value=mock_scan), \
             patch("titan.production.canonical_decision_engine.evaluate_ceo_decision",
                   return_value=type('C', (), {'allowed_to_trade': True})()):
            i = len(df) - 1
            dec_hist = hist_adapter.evaluate_bar(
                df=df, i=i,
                alpha_proba=alpha_proba, meta_proba=meta_proba,
                atr_value=atr_value, entry_price=entry_price,
                spread=spread, timestamp=timestamp,
                alpha_dist=alpha_dist, meta_dist=meta_dist,
            )
            dec_shadow = shadow_adapter.evaluate_bar(
                df=df,
                alpha_proba=alpha_proba, meta_proba=meta_proba,
                atr_value=atr_value, entry_price=entry_price,
                spread=spread, timestamp=timestamp,
                alpha_probas_recent=alpha_dist,
                meta_probas_recent=meta_dist,
            )

        # Parity assertions
        assert dec_hist.direction == "SHORT"
        assert dec_hist.direction == dec_shadow.direction
        assert dec_hist.directional_confidence == dec_shadow.directional_confidence
        assert dec_hist.regime == dec_shadow.regime
        assert dec_hist.setup_selected == dec_shadow.setup_selected
        assert dec_hist.approved_risk == dec_shadow.approved_risk
        assert dec_hist.lot_size == dec_shadow.lot_size
        assert dec_hist.sl_price == dec_shadow.sl_price
        assert dec_hist.tp_price == dec_shadow.tp_price

    def test_rejection_parity(self):
        """Both adapters reject identically when alpha is below threshold."""
        from titan.production.decision_adapters import HistoricalAdapter, ShadowAdapter
        from titan.production.corrected_setup_detector_v2 import (
            SetupResultV2, CorrectedSetupTypeV2, ScanResultV2,
        )

        df = _build_synthetic_bars(n=300, trend=0.5)
        alpha_proba = 0.52  # Below threshold 0.55
        meta_proba = 0.60
        safety = _make_safety_state()
        config = _make_config()
        instrument = _make_instrument()
        alpha_dist = np.full(60, alpha_proba)
        meta_dist = np.full(60, meta_proba)

        setup = SetupResultV2(
            setup_type=CorrectedSetupTypeV2.PULLBACK,
            direction="LONG", confidence=0.75,
            reason_codes=["mock"], evidence=["mock"],
        )
        mock_scan = ScanResultV2(
            selected_setup=setup, alternatives=[],
            rejection_reasons=[], ranking_evidence=["mock"],
            all_candidates=[setup], decision="SELECTED",
        )

        hist_adapter = HistoricalAdapter(
            instrument=instrument, config=config, safety_state=safety,
            equity=100000.0, equity_peak=100000.0,
            daily_peak=100000.0, daily_start_equity=100000.0,
        )
        shadow_adapter = ShadowAdapter(
            instrument=instrument, config=config, safety_state=safety,
            equity=100000.0, equity_peak=100000.0,
            daily_peak=100000.0, daily_start_equity=100000.0,
        )

        with patch("titan.production.canonical_decision_engine.scan_setups_governed",
                   return_value=mock_scan), \
             patch("titan.production.canonical_decision_engine.evaluate_ceo_decision",
                   return_value=type('C', (), {'allowed_to_trade': True})()):
            i = len(df) - 1
            dec_hist = hist_adapter.evaluate_bar(
                df=df, i=i, alpha_proba=alpha_proba, meta_proba=meta_proba,
                atr_value=5.0, entry_price=float(df["close"].iloc[-1]),
                spread=0.15, timestamp=str(df.index[-1]),
                alpha_dist=alpha_dist, meta_dist=meta_dist,
            )
            dec_shadow = shadow_adapter.evaluate_bar(
                df=df, alpha_proba=alpha_proba, meta_proba=meta_proba,
                atr_value=5.0, entry_price=float(df["close"].iloc[-1]),
                spread=0.15, timestamp=str(df.index[-1]),
                alpha_probas_recent=alpha_dist, meta_probas_recent=meta_dist,
            )

        assert dec_hist.final_decision == "REJECT_ALPHA"
        assert dec_hist.final_decision == dec_shadow.final_decision
        assert dec_hist.reject_reason == dec_shadow.reject_reason
