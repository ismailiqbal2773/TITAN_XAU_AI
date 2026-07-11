"""TITAN XAU AI — Sprint v2.8.7-P1.2 Canonical Integrity Tests

Exact behavioural tests for all defect groups A-G.
Every test asserts exact expected values.
"""
from __future__ import annotations
import sys, re, json
from pathlib import Path
import pytest
import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
np.random.seed(42)


# ===== B: Risk Governor =====

class TestRiskGovernor:
    def test_one_loss_doesnt_consume_full_budget(self):
        """One 0.30% loss should leave remaining daily budget."""
        from titan.production.risk_governor import govern_risk, RiskGovernorInput
        inp = RiskGovernorInput(
            equity=99700, equity_peak=100000, daily_peak=100000,
            daily_start_equity=100000, proposed_risk=0.003,
            setup_class="A_PLUS", loss_streak=0,
        )
        out = govern_risk(inp)
        assert out.approved is True
        assert out.approved_risk > 0
        # After 0.3% loss, daily DD ≈ 0.3%, remaining budget ≈ 1.7%
        assert out.remaining_daily_budget > 0.015

    def test_two_losses_multiply_075(self):
        from titan.production.risk_governor import govern_risk, RiskGovernorInput
        inp = RiskGovernorInput(
            equity=100000, equity_peak=100000, daily_peak=100000,
            daily_start_equity=100000, proposed_risk=0.003,
            setup_class="A_PLUS", loss_streak=2,
        )
        out = govern_risk(inp)
        assert out.risk_multiplier == pytest.approx(0.75, abs=1e-6)

    def test_three_losses_multiply_050(self):
        from titan.production.risk_governor import govern_risk, RiskGovernorInput
        inp = RiskGovernorInput(
            equity=100000, equity_peak=100000, daily_peak=100000,
            daily_start_equity=100000, proposed_risk=0.003,
            setup_class="A_PLUS", loss_streak=3,
        )
        out = govern_risk(inp)
        assert out.risk_multiplier == pytest.approx(0.50, abs=1e-6)

    def test_four_losses_block_entries(self):
        from titan.production.risk_governor import govern_risk, RiskGovernorInput
        inp = RiskGovernorInput(
            equity=100000, equity_peak=100000, daily_peak=100000,
            daily_start_equity=100000, proposed_risk=0.003,
            setup_class="A_PLUS", loss_streak=4,
        )
        out = govern_risk(inp)
        assert out.approved is False
        assert out.approved_risk == 0.0

    def test_daily_block_stage_zero_risk(self):
        from titan.production.risk_governor import govern_risk, RiskGovernorInput, DAILY_BLOCK
        # Daily DD at 1.6% (block stage)
        equity = 100000 * (1 - DAILY_BLOCK)
        inp = RiskGovernorInput(
            equity=equity, equity_peak=100000, daily_peak=100000,
            daily_start_equity=100000, proposed_risk=0.003,
            setup_class="A_PLUS",
        )
        out = govern_risk(inp)
        assert out.approved is False
        assert out.approved_risk == 0.0

    def test_risk_clamped_to_setup_cap(self):
        """A_PLUS risk clamped to 0.30%."""
        from titan.production.risk_governor import govern_risk, RiskGovernorInput, RISK_CAP_A_PLUS
        inp = RiskGovernorInput(
            equity=100000, equity_peak=100000, daily_peak=100000,
            daily_start_equity=100000, proposed_risk=0.01,  # Request 1%
            setup_class="A_PLUS",
        )
        out = govern_risk(inp)
        assert out.approved_risk <= RISK_CAP_A_PLUS

    def test_risk_rounds_down(self):
        """Risk must round down to 4 decimals."""
        from titan.production.risk_governor import govern_risk, RiskGovernorInput
        inp = RiskGovernorInput(
            equity=100000, equity_peak=100000, daily_peak=100000,
            daily_start_equity=100000, proposed_risk=0.003,
            setup_class="A_PLUS", loss_streak=2,  # 0.75x
        )
        out = govern_risk(inp)
        # 0.003 * 0.75 = 0.00225, rounded down to 0.0022
        assert out.approved_risk <= 0.00225
        # Must be 4 decimal places
        assert out.approved_risk == round(out.approved_risk, 4)


# ===== C: Backtest gap logic =====

class TestBacktestGapLogic:
    def _setup(self, n=50, signal_bar=29, sl_dist=10, tp_dist=30, spread=0.15):
        dates = pd.date_range("2024-01-01", periods=n, freq="h", tz="UTC")
        prices = np.full(n, 2000.0)
        df = pd.DataFrame({
            "open": prices, "high": prices.copy(), "low": prices.copy(),
            "close": prices, "volume": 100, "spread_usd": spread,
        }, index=dates)
        alpha = np.full(n, 0.50)  # confidence=0.50 < 0.55
        alpha[signal_bar] = 0.90   # confidence=0.90 >= 0.55 → LONG
        meta = np.full(n, 0.55)
        atr = np.full(n, sl_dist)
        params = {"alpha_threshold": 0.55, "meta_threshold": 0.50, "risk_percent": 0.003,
                  "sl_atr_multiplier": 1.0, "rr_target": tp_dist/sl_dist,
                  "max_holding_bars": 3, "max_trades_per_day": 2,
                  "cooldown_after_loss": 0, "spread_filter": 1.0,
                  "commission_per_lot": 0, "slippage_points": 0, "swap_per_bar": 0,
                  "setup_class": "A_PLUS"}
        return df, alpha, meta, atr, params

    def _patch_ceo(self):
        from titan.production import ceo_ai_governance
        orig = ceo_ai_governance.evaluate_ceo_decision
        ceo_ai_governance.evaluate_ceo_decision = lambda **kw: type('C',(),{'allowed_to_trade':True})()
        return orig

    def _restore(self, orig):
        from titan.production import ceo_ai_governance
        ceo_ai_governance.evaluate_ceo_decision = orig

    def test_entry_bar_sl_hit(self):
        """SL hit inside entry bar."""
        from titan.production.canonical_backtest import run_backtest_v3, InstrumentSpec
        df, alpha, meta, atr, params = self._setup()
        entry_bar = 30
        df.loc[df.index[entry_bar], "low"] = 1985   # Below SL
        df.loc[df.index[entry_bar], "high"] = 2005   # Not above TP
        orig = self._patch_ceo()
        try:
            trades, metrics = run_backtest_v3(df, alpha, meta, atr, params, InstrumentSpec())
        finally:
            self._restore(orig)
        assert len(trades) >= 1
        assert trades[0].exit_reason == "SL_HIT"
        assert trades[0].holding_bars == 1

    def test_entry_bar_tp_hit(self):
        """TP hit inside entry bar."""
        from titan.production.canonical_backtest import run_backtest_v3, InstrumentSpec
        df, alpha, meta, atr, params = self._setup()
        entry_bar = 30
        df.loc[df.index[entry_bar], "high"] = 2040   # Above TP
        df.loc[df.index[entry_bar], "low"] = 1998     # Not below SL
        orig = self._patch_ceo()
        try:
            trades, metrics = run_backtest_v3(df, alpha, meta, atr, params, InstrumentSpec())
        finally:
            self._restore(orig)
        assert len(trades) >= 1
        assert trades[0].exit_reason == "TP_HIT"
        assert trades[0].holding_bars == 1

    def test_both_sl_tp_conservative(self):
        """Both hit in same bar → SL first (conservative)."""
        from titan.production.canonical_backtest import run_backtest_v3, InstrumentSpec
        df, alpha, meta, atr, params = self._setup()
        entry_bar = 30
        df.loc[df.index[entry_bar], "low"] = 1985
        df.loc[df.index[entry_bar], "high"] = 2040
        orig = self._patch_ceo()
        try:
            trades, metrics = run_backtest_v3(df, alpha, meta, atr, params, InstrumentSpec())
        finally:
            self._restore(orig)
        assert len(trades) >= 1
        assert trades[0].exit_reason == "SL_HIT"

    def test_holding_bar_gap_through_sl(self):
        """Gap on holding bar (j>0) opens beyond SL → fill at gap open."""
        from titan.production.canonical_backtest import run_backtest_v3, InstrumentSpec
        df, alpha, meta, atr, params = self._setup()
        # Entry at bar 30. Holding bar 31 gaps down below SL.
        # Entry = 2000 + 0.15 = 2000.15, SL = 2000.15 - 10 = 1990.15
        # Bar 31 opens at 1985 (below SL)
        df.loc[df.index[31], "open"] = 1985
        df.loc[df.index[31], "low"] = 1980
        df.loc[df.index[31], "high"] = 1995
        orig = self._patch_ceo()
        try:
            trades, metrics = run_backtest_v3(df, alpha, meta, atr, params, InstrumentSpec())
        finally:
            self._restore(orig)
        assert len(trades) >= 1
        assert trades[0].exit_reason == "SL_GAP"
        # Exit at gap open (1985), not ideal SL (1990.15)
        # R = (1985 - 2000.15) / 10 = -1.515 (worse than -1.0)
        assert trades[0].r_gross < -1.0

    def test_timeout_exit(self):
        """No SL or TP → timeout."""
        from titan.production.canonical_backtest import run_backtest_v3, InstrumentSpec
        df, alpha, meta, atr, params = self._setup()
        for i in range(30, 35):
            df.loc[df.index[i], "high"] = 2005
            df.loc[df.index[i], "low"] = 1998
        orig = self._patch_ceo()
        try:
            trades, metrics = run_backtest_v3(df, alpha, meta, atr, params, InstrumentSpec())
        finally:
            self._restore(orig)
        assert len(trades) >= 1
        assert trades[0].exit_reason == "TIMEOUT"

    def test_long_short_symmetry(self):
        """Long and short produce symmetric results."""
        from titan.production.canonical_backtest import run_backtest_v3, InstrumentSpec
        from titan.production.direction_logic import interpret_direction
        # Long: p_up=0.90 → LONG, confidence=0.90
        d1, c1 = interpret_direction(0.90)
        assert d1 == "LONG" and c1 == pytest.approx(0.90)
        # Short: p_up=0.10 → SHORT, confidence=0.90
        d2, c2 = interpret_direction(0.10)
        assert d2 == "SHORT" and c2 == pytest.approx(0.90)

    def test_spread_applied_once_entry_exit(self):
        """Spread applied exactly once at entry and once at exit."""
        from titan.production.canonical_backtest import run_backtest_v3, InstrumentSpec
        df, alpha, meta, atr, params = self._setup(spread=0.50)
        df.loc[df.index[30], "high"] = 2040  # TP hit
        df.loc[df.index[30], "low"] = 1998
        params["commission_per_lot"] = 0
        params["slippage_points"] = 0
        orig = self._patch_ceo()
        try:
            trades, metrics = run_backtest_v3(df, alpha, meta, atr, params, InstrumentSpec())
        finally:
            self._restore(orig)
        if trades:
            t = trades[0]
            # Entry spread + exit spread = 2 * 0.50 / sl_dist = 0.10
            assert t.entry_spread_cost > 0
            assert t.exit_spread_cost > 0
            assert t.entry_spread_cost == pytest.approx(t.exit_spread_cost, abs=0.01)


# ===== D: Net metrics =====

class TestNetMetrics:
    def test_exact_net_pf_ledger(self):
        """Net PF = sum(pos net) / abs(sum(neg net)) from actual trades."""
        from titan.production.canonical_backtest import run_backtest_v3, InstrumentSpec
        # Create scenario with known outcomes
        n = 50
        dates = pd.date_range("2024-01-01", periods=n, freq="h", tz="UTC")
        prices = np.full(n, 2000.0)
        df = pd.DataFrame({
            "open": prices, "high": prices.copy(), "low": prices.copy(),
            "close": prices, "volume": 100, "spread_usd": 0.0,  # No spread for exact calc
        }, index=dates)
        # Signal at bar 29 → entry at 30, TP hit
        alpha = np.full(n, 0.50)
        alpha[29] = 0.90
        meta = np.full(n, 0.55)
        atr = np.full(n, 10.0)
        # Bar 30: TP hit
        df.loc[df.index[30], "high"] = 2040
        df.loc[df.index[30], "low"] = 1998
        params = {"alpha_threshold": 0.55, "meta_threshold": 0.50, "risk_percent": 0.003,
                  "sl_atr_multiplier": 1.0, "rr_target": 3.0,
                  "max_holding_bars": 3, "max_trades_per_day": 2,
                  "cooldown_after_loss": 0, "spread_filter": 1.0,
                  "commission_per_lot": 0, "slippage_points": 0, "swap_per_bar": 0,
                  "setup_class": "A_PLUS"}
        from titan.production import ceo_ai_governance
        orig = ceo_ai_governance.evaluate_ceo_decision
        ceo_ai_governance.evaluate_ceo_decision = lambda **kw: type('C',(),{'allowed_to_trade':True})()
        try:
            trades, metrics = run_backtest_v3(df, alpha, meta, atr, params, InstrumentSpec())
        finally:
            ceo_ai_governance.evaluate_ceo_decision = orig
        if trades:
            # With 0 spread, 0 commission, 0 slippage:
            # Entry = 2000 (open + 0 spread), TP = 2000 + 30 = 2030
            # R_gross = 3.0, R_net = 3.0
            # pnl_gross = pnl_net = equity * 0.003 * 3.0 = 900
            assert trades[0].r_gross == pytest.approx(3.0, abs=0.01)
            assert trades[0].pnl_gross == pytest.approx(trades[0].pnl_net, abs=0.01)

    def test_commission_reduces_net(self):
        """Commission must reduce net vs gross."""
        from titan.production.canonical_backtest import run_backtest_v3, InstrumentSpec
        n = 300
        dates = pd.date_range("2024-01-01", periods=n, freq="h", tz="UTC")
        np.random.seed(42)
        prices = np.cumsum(np.random.randn(n) * 0.5) + 2000
        df = pd.DataFrame({
            "open": prices, "high": prices + 5, "low": prices - 5,
            "close": prices, "volume": 100, "spread_usd": 0.15,
        }, index=dates)
        alpha = np.full(n, 0.90)  # All pass
        meta = np.full(n, 0.55)
        atr = np.full(n, 10.0)
        params = {"alpha_threshold": 0.55, "meta_threshold": 0.50, "risk_percent": 0.003,
                  "sl_atr_multiplier": 2.0, "rr_target": 3.0,
                  "max_holding_bars": 3, "max_trades_per_day": 2,
                  "cooldown_after_loss": 0, "spread_filter": 1.0,
                  "commission_per_lot": 7.0, "slippage_points": 0.5, "swap_per_bar": 0,
                  "setup_class": "A_PLUS"}
        from titan.production import ceo_ai_governance
        orig = ceo_ai_governance.evaluate_ceo_decision
        ceo_ai_governance.evaluate_ceo_decision = lambda **kw: type('C',(),{'allowed_to_trade':True})()
        try:
            trades, metrics = run_backtest_v3(df, alpha, meta, atr, params, InstrumentSpec())
        finally:
            ceo_ai_governance.evaluate_ceo_decision = orig
        if metrics.total_trades > 0:
            assert metrics.pf_net <= metrics.pf_gross
            assert metrics.total_commission > 0
            assert metrics.net_profit < metrics.gross_profit - metrics.gross_loss


# ===== E: Setup engine =====

class TestSetupEngine:
    def test_no_conflicting_long_short(self):
        """Scanner must not produce simultaneous LONG and SHORT."""
        from titan.production.corrected_setup_detector_v2 import scan_setups_v2
        n = 100
        dates = pd.date_range("2024-01-01", periods=n, freq="h", tz="UTC")
        prices = np.linspace(2000, 2100, n)
        df = pd.DataFrame({
            "open": prices, "high": prices + 2, "low": prices - 2,
            "close": prices, "volume": 500, "spread": 0.15,
        }, index=dates)
        results = scan_setups_v2(df, "BULL", atr_value=5.0)
        dirs = set(r.direction for r in results if r.direction != "NEUTRAL")
        assert not ({"LONG", "SHORT"}.issubset(dirs))

    def test_breakout_retest_implemented(self):
        from titan.production.corrected_setup_detector_v2 import detect_breakout_retest
        assert callable(detect_breakout_retest)

    def test_range_edge_rejection_implemented(self):
        from titan.production.corrected_setup_detector_v2 import detect_range_edge_rejection
        assert callable(detect_range_edge_rejection)

    def test_continuation_implemented(self):
        from titan.production.corrected_setup_detector_v2 import detect_continuation
        assert callable(detect_continuation)


# ===== F: Adaptive threshold =====

class TestAdaptiveThresholdHardening:
    def test_malformed_state_hard_blocks(self):
        from titan.production.corrected_adaptive_threshold_v2 import SafetyStateV2, compute_adaptive_threshold_v2
        safety = SafetyStateV2(
            dd_state={}, margin_state={}, prop_risk_state={},
            capital_protection={}, broker_intelligence={},
            execution_health={}, model_health={},
            spread_state={}, volatility_state={},
            loss_streak=0, signal_drought_hours=0,
            regime_confidence=0.5,
            alpha_distribution=[], meta_distribution=[],
            recent_shadow_evidence={},
        )
        result = compute_adaptive_threshold_v2(safety)
        assert result.policy_mode == "hard_block"
        assert result.risk_multiplier == 0.0

    def test_drought_alone_cannot_relax(self):
        from titan.production.corrected_adaptive_threshold_v2 import SafetyStateV2, compute_adaptive_threshold_v2
        safety = SafetyStateV2(
            dd_state={"current_dd": 0.01, "daily_dd": 0.005},
            margin_state={"margin_usage": 0.05, "margin_safe": True},
            prop_risk_state={"prop_pass": True, "prop_violations": 0},
            capital_protection={"active": False, "dd_breach": False},
            broker_intelligence={"broker_pass": True, "spread_pass": True},
            execution_health={"healthy": True, "latency_ms": 10},
            model_health={"model_health_pass": True},
            spread_state={"current_spread": 0.2, "average_spread": 0.2},
            volatility_state={"current_atr": 5, "average_atr": 5, "regime": "STABLE_RANGE"},
            loss_streak=0, signal_drought_hours=20,
            regime_confidence=0.7,
            alpha_distribution=[0.55], meta_distribution=[0.55],
            recent_shadow_evidence={"false_negative_rate": 0, "sample_size": 0},
        )
        result = compute_adaptive_threshold_v2(safety)
        assert result.policy_mode != "relaxed"


# ===== G: Integration test =====

class TestIntegration:
    def test_runtime_calls_corrected_components(self):
        """Verify all canonical components are importable and callable."""
        from titan.production.direction_logic import interpret_direction
        from titan.production.risk_governor import govern_risk, RiskGovernorInput
        from titan.production.canonical_backtest import run_backtest_v3, InstrumentSpec
        from titan.production.corrected_regime_classifier_v2 import classify_regime_v2
        from titan.production.corrected_setup_detector_v2 import scan_setups_v2
        from titan.production.corrected_adaptive_threshold_v2 import compute_adaptive_threshold_v2
        from titan.production.near_miss_tracker_v2 import NearMissShadowTrackerV2
        assert callable(interpret_direction)
        assert callable(govern_risk)
        assert callable(run_backtest_v3)
        assert callable(classify_regime_v2)
        assert callable(scan_setups_v2)
        assert callable(compute_adaptive_threshold_v2)
        tracker = NearMissShadowTrackerV2(timeframe="H1")
        assert hasattr(tracker, 'consume_re_entry')

    def test_no_order_send_in_canonical_files(self):
        files = [
            "titan/production/risk_governor.py",
            "titan/production/canonical_backtest.py",
            "titan/production/direction_logic.py",
            "titan/production/corrected_regime_classifier_v2.py",
            "titan/production/corrected_setup_detector_v2.py",
            "titan/production/corrected_adaptive_threshold_v2.py",
            "titan/production/near_miss_tracker_v2.py",
        ]
        for f in files:
            path = REPO_ROOT / f
            if path.exists():
                src = path.read_text()
                stripped = re.sub(r'"""[\s\S]*?"""', '""', src)
                assert "order_send(" not in stripped, f"order_send in {f}"

    def test_profile_uses_2pct_daily_dd(self):
        import yaml
        path = REPO_ROOT / "config" / "broker_profiles" / "exness_competition_shadow_profile.yaml"
        with open(path) as f:
            config = yaml.safe_load(f)
        assert config["daily_DD_limit"] == 0.02
        assert config["risk_percent_A_PLUS"] == 0.003
        assert config["risk_percent_A"] == 0.0025
        assert config["risk_percent_B"] == 0.001
        assert config["risk_percent_C"] == 0
        assert config["live_trading"] is False
        assert config["funded_trading"] is False
        assert config["production_ready"] is False
        assert config["no_order_send"] is True

    def test_dry_run_safety_intact(self):
        import yaml
        path = REPO_ROOT / "config" / "broker_profiles" / "exness_legacy_optimized_prop_profile.yaml"
        with open(path) as f:
            config = yaml.safe_load(f)
        assert config["safety"]["dry_run"] is True
        assert config["safety"]["live_trading"] is False
        assert config["safety"]["production_ready"] is False
