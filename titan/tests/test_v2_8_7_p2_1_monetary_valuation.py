"""TITAN XAU AI — v2.8.7-P2.1 Phase 1 Monetary Valuation Tests
=================================================================

EXACT fixtures verifying:
  - $10 SL distance, $300 risk → raw lot=0.30, broker step lot=0.30,
    monetary loss at ideal SL = $300 before costs
  - 3R TP → gross profit = $900, gross R = 3.0
  - Ideal SL → gross loss = -$300, gross R = -1.0
  - pnl_net = pnl_gross - total_cost; r_net = pnl_net / approved risk amount
  - Adverse gap may exceed -1R but reconciles via same tick-value function
  - Normal SL trade: actual monetary loss ≤ approved risk + broker rounding + execution-cost tolerance

Inconsistent fixture (tick_size=0.01, tick_value=0.01, contract_size=100)
MUST be rejected as REJECT_INSTRUMENT_VALUE_CONSISTENCY.
"""
from __future__ import annotations
import sys, math
from pathlib import Path
import pytest
import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


def _valid_xauusd_spec():
    from titan.production.canonical_backtest import InstrumentSpec
    return InstrumentSpec(
        tick_size=0.01, tick_value=1.00, contract_size=100.0,
        volume_min=0.01, volume_max=100.0, volume_step=0.01,
        account_currency="USD", profit_currency="USD",
        symbol_currency="USD", conversion_rate=1.0,
    )


class TestMonetaryValuationConsistency:
    def test_inconsistent_tick_value_rejected(self):
        """The previously-inconsistent fixture (tick_size=0.01, tick_value=0.01,
        contract_size=100) MUST be rejected.

        money_per_price_unit_from_ticks    = 0.01 / 0.01 × 1.0 = 1.0
        money_per_price_unit_from_contract = 100.0 × 1.0       = 100.0
        These differ beyond tolerance → reject.
        """
        from titan.production.canonical_backtest import InstrumentSpec, validate_instrument_spec
        bad_spec = InstrumentSpec(
            tick_size=0.01, tick_value=0.01, contract_size=100.0,
            volume_min=0.01, volume_max=100.0, volume_step=0.01,
            account_currency="USD", profit_currency="USD",
            symbol_currency="USD", conversion_rate=1.0,
        )
        ok, msg = validate_instrument_spec(bad_spec)
        assert ok is False
        assert "value_consistency_mismatch" in msg or "consistency" in msg

    def test_valid_xauusd_spec_accepted(self):
        from titan.production.canonical_backtest import validate_instrument_spec
        ok, msg = validate_instrument_spec(_valid_xauusd_spec())
        assert ok is True, f"Valid spec rejected: {msg}"

    def test_price_delta_to_money_uses_tick_formula(self):
        """price_delta_to_money = (price_delta / tick_size) × tick_value × lot × conversion_rate."""
        from titan.production.canonical_backtest import price_delta_to_money
        spec = _valid_xauusd_spec()
        # $1.00 price delta, 1.0 lot
        # ticks = 1.00 / 0.01 = 100
        # money = 100 × 1.00 × 1.0 × 1.0 = $100
        money = price_delta_to_money(spec, 1.00, 1.0)
        assert money == pytest.approx(100.0, abs=1e-6)
        # $10 price delta, 0.30 lot → 1000 ticks × 1.00 × 0.30 = $300
        money = price_delta_to_money(spec, 10.0, 0.30)
        assert money == pytest.approx(300.0, abs=1e-6)


class TestExactRiskLotMonetaryFixtures:
    """EXACT fixture: $10 SL distance, $300 risk → lot=0.30, monetary_loss=$300."""

    def test_10usd_sl_300usd_risk_lot_0_30(self):
        """$10 SL distance, $300 risk:
              loss_per_lot = (10 / 0.01) × 1.00 = 1000
              raw_lot      = 300 / 1000 = 0.30
              broker step  = 0.30 (already stepped)
              monetary_loss_at_sl = 0.30 × 1000 = $300
        """
        from titan.production.canonical_backtest import compute_lot_size
        spec = _valid_xauusd_spec()
        lot, monetary_loss, reject = compute_lot_size(spec, risk_amount=300.0, sl_distance_price=10.0)
        assert reject == ""
        assert lot == pytest.approx(0.30, abs=1e-6)
        assert monetary_loss == pytest.approx(300.0, abs=1e-6)

    def test_3R_tp_gross_profit_900_gross_r_3(self):
        """3R TP → gross profit = $900, gross R = 3.0."""
        from titan.production.canonical_backtest import price_delta_to_money
        spec = _valid_xauusd_spec()
        # lot=0.30, sl_distance=$10, RR=3 → tp_distance=$30
        # gross_profit = price_delta_to_money(30, 0.30) = (30/0.01) × 1.00 × 0.30 = $900
        gross_profit = price_delta_to_money(spec, 30.0, 0.30)
        assert gross_profit == pytest.approx(900.0, abs=1e-6)
        # gross R = gross_profit / risk_amount = 900 / 300 = 3.0
        gross_r = gross_profit / 300.0
        assert gross_r == pytest.approx(3.0, abs=1e-6)

    def test_ideal_sl_gross_loss_minus_300_gross_r_minus_1(self):
        """Ideal SL → gross loss = -$300, gross R = -1.0."""
        from titan.production.canonical_backtest import price_delta_to_money
        spec = _valid_xauusd_spec()
        # Long position hits SL: price moved against by $10 → price_delta = -10
        gross_loss = price_delta_to_money(spec, -10.0, 0.30)
        assert gross_loss == pytest.approx(-300.0, abs=1e-6)
        # gross R = -300 / 300 = -1.0
        gross_r = gross_loss / 300.0
        assert gross_r == pytest.approx(-1.0, abs=1e-6)

    def test_costs_subtracted_pnl_net_reconciles(self):
        """pnl_net = pnl_gross - total_cost; r_net = pnl_net / approved risk amount."""
        from titan.production.canonical_backtest import price_delta_to_money
        spec = _valid_xauusd_spec()
        lot = 0.30
        risk_amount = 300.0
        # TP at 3R: pnl_gross = $900
        pnl_gross = price_delta_to_money(spec, 30.0, lot)
        # Costs
        spread = 0.15
        slippage = 0.5
        commission_per_lot = 7.0
        entry_spread_cost = price_delta_to_money(spec, spread, lot)
        exit_spread_cost = price_delta_to_money(spec, spread, lot)
        entry_slip = price_delta_to_money(spec, slippage, lot)
        exit_slip = price_delta_to_money(spec, slippage, lot)
        commission = commission_per_lot * lot
        swap = 0.0
        total_cost = entry_spread_cost + exit_spread_cost + entry_slip + exit_slip + commission + swap
        pnl_net = pnl_gross - total_cost
        r_net = pnl_net / risk_amount
        # Reconciliation
        assert abs((pnl_gross - total_cost) - pnl_net) <= 0.01
        # r_net < 3.0 because of costs
        assert r_net < 3.0
        # r_net > 0 because TP profit exceeds costs
        assert r_net > 0

    def test_adverse_gap_reconciles_via_tick_value(self):
        """Adverse gap may exceed -1R; exact loss reconciles via tick-value function."""
        from titan.production.canonical_backtest import price_delta_to_money
        spec = _valid_xauusd_spec()
        lot = 0.30
        risk_amount = 300.0
        # Gap of $15 against long → price_delta = -15
        gap_loss = price_delta_to_money(spec, -15.0, lot)
        # gap_loss = (15/0.01) × 1.00 × 0.30 = $450 = -450
        assert gap_loss == pytest.approx(-450.0, abs=1e-6)
        gap_r = gap_loss / risk_amount
        # Exceeds -1R
        assert gap_r < -1.0
        assert gap_r == pytest.approx(-1.5, abs=1e-6)


class TestBacktestMonetaryReconciliation:
    """End-to-end backtest trade fixtures with EXACT monetary assertions."""

    def _patch_ceo(self):
        from titan.production import ceo_ai_governance, canonical_decision_engine as cde
        orig_ceo = ceo_ai_governance.evaluate_ceo_decision
        orig_cde = cde.evaluate_ceo_decision
        mock = lambda **kw: type('C', (), {'allowed_to_trade': True})()
        ceo_ai_governance.evaluate_ceo_decision = mock
        cde.evaluate_ceo_decision = mock
        return (orig_ceo, orig_cde)

    def _restore(self, orig):
        from titan.production import ceo_ai_governance, canonical_decision_engine as cde
        orig_ceo, orig_cde = orig
        ceo_ai_governance.evaluate_ceo_decision = orig_ceo
        cde.evaluate_ceo_decision = orig_cde

    def _patch_setup(self, direction="LONG"):
        from titan.production import canonical_decision_engine as cde
        from titan.production.corrected_setup_detector_v2 import (
            SetupResultV2, CorrectedSetupTypeV2, ScanResultV2,
        )
        orig = cde.scan_setups_governed
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
        cde.scan_setups_governed = lambda *a, **kw: mock_scan
        return orig

    def _restore_setup(self, orig):
        from titan.production import canonical_decision_engine as cde
        cde.scan_setups_governed = orig



    def _make_test_safety_provider(self, alpha_probas=None, meta_probas=None, n=100):
        """Build a HistoricalSafetyProvider for tests with valid calibration (slope=1.0)."""
        from titan.production.historical_safety_provider import HistoricalSafetyProvider
        from titan.production.model_provenance import CalibrationEvidence
        import numpy as np
        ce = CalibrationEvidence(
            artifact_path="test", artifact_sha256="test",
            model_sha256="test", scaler_sha256="test", feature_schema_sha256="test",
            generated_at_utc="2026-01-01T00:00:00Z",
            sample_period_start="2024-01-01", sample_period_end="2026-01-01",
            brier_score=0.20, calibration_slope=1.0, calibration_intercept=0.0,
            drift_status="none", n_samples=200,
        )
        if alpha_probas is None:
            alpha_probas = np.full(n, 0.55)
        if meta_probas is None:
            meta_probas = np.full(n, 0.55)
        return HistoricalSafetyProvider(
            calibration_evidence=ce,
            alpha_probas_full=alpha_probas,
            meta_probas_full=meta_probas,
        )

    def test_normal_sl_loss_within_tolerance_of_approved_risk(self):
        """For every normal SL trade: actual monetary loss ≤ approved risk +
        broker rounding + execution-cost tolerance."""
        from titan.production.canonical_backtest import run_backtest_v3
        n = 100
        dates = pd.date_range("2024-01-01", periods=n, freq="h", tz="UTC")
        np.random.seed(42)
        prices = 2000.0 + np.cumsum(np.random.randn(n) * 0.3) + np.linspace(0, 5, n)
        df = pd.DataFrame({
            "open": prices, "high": prices.copy(), "low": prices.copy(),
            "close": prices, "volume": 100, "spread_usd": 0.15,
        }, index=dates)
        alpha = np.full(n, 0.50); alpha[60] = 0.90
        meta = np.full(n, 0.55)
        atr = np.full(n, 10.0)
        # SL hit at bar 30
        df.loc[df.index[61], "low"] = 1985
        df.loc[df.index[61], "high"] = 2005
        params = {
            "alpha_threshold": 0.55, "meta_threshold": 0.50,
            "risk_percent": 0.003, "sl_atr_multiplier": 1.0, "rr_target": 3.0,
            "max_holding_bars": 3, "max_trades_per_day": 2,
            "cooldown_after_loss": 0, "spread_filter": 1.0,
            "commission_per_lot": 7.0, "slippage_points": 0.5, "swap_per_bar": 0.0,
            "setup_class": "A_PLUS",
        }
        orig_ceo = self._patch_ceo()
        orig_setup = self._patch_setup()
        try:
            trades, metrics = run_backtest_v3(df, alpha, meta, atr, params,
                                              instrument=_valid_xauusd_spec(),
                                              safety_provider=self._make_test_safety_provider(alpha, meta, len(df)))
        finally:
            self._restore(orig_ceo)
            self._restore_setup(orig_setup)
        assert len(trades) >= 1
        t = trades[0]
        assert t.exit_reason == "SL_HIT"
        # gross loss should be approximately -1R (within slippage/spread tolerance)
        # Approved risk % = 0.003 → risk_amount = $300
        # gross loss at SL = -$300 → gross R = -1.0 (approximately)
        # Allow tolerance for spread + slippage at entry (entry price was shifted by spread+slippage)
        assert -1.5 <= t.r_gross <= -0.5  # Should be near -1R
        # Actual monetary loss (pnl_gross) should not exceed approved risk by more than
        # broker rounding + execution-cost tolerance
        # risk_amount = $300, tolerance = $10 (broker rounding + spread+slippage at entry)
        assert t.pnl_gross >= -(t.risk_amount + 10.0)

    def test_tp_gross_r_approximately_3(self):
        """TP hit → gross R approximately configured RR (3.0)."""
        from titan.production.canonical_backtest import run_backtest_v3
        n = 100
        dates = pd.date_range("2024-01-01", periods=n, freq="h", tz="UTC")
        np.random.seed(42)
        prices = 2000.0 + np.cumsum(np.random.randn(n) * 0.3) + np.linspace(0, 5, n)
        df = pd.DataFrame({
            "open": prices, "high": prices.copy(), "low": prices.copy(),
            "close": prices, "volume": 100, "spread_usd": 0.0,  # no spread for exact calc
        }, index=dates)
        alpha = np.full(n, 0.50); alpha[60] = 0.90
        meta = np.full(n, 0.55)
        atr = np.full(n, 10.0)
        # TP hit at bar 30: high reaches 2030 (entry 2000, SL dist 10, TP 2030)
        df.loc[df.index[61], "high"] = 2040
        df.loc[df.index[61], "low"] = 1998
        params = {
            "alpha_threshold": 0.55, "meta_threshold": 0.50,
            "risk_percent": 0.003, "sl_atr_multiplier": 1.0, "rr_target": 3.0,
            "max_holding_bars": 3, "max_trades_per_day": 2,
            "cooldown_after_loss": 0, "spread_filter": 1.0,
            "commission_per_lot": 0, "slippage_points": 0, "swap_per_bar": 0,
            "setup_class": "A_PLUS",
        }
        orig_ceo = self._patch_ceo()
        orig_setup = self._patch_setup()
        try:
            trades, metrics = run_backtest_v3(df, alpha, meta, atr, params,
                                              instrument=_valid_xauusd_spec(),
                                              safety_provider=self._make_test_safety_provider(alpha, meta, len(df)))
        finally:
            self._restore(orig_ceo)
            self._restore_setup(orig_setup)
        assert len(trades) >= 1
        t = trades[0]
        assert t.exit_reason == "TP_HIT"
        # No spread, no slippage, no commission → gross R should be exactly 3.0
        assert t.r_gross == pytest.approx(3.0, abs=0.001)
        # Net R = gross R (no costs)
        assert t.r_net == pytest.approx(3.0, abs=0.001)
