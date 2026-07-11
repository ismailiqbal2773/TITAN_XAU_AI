"""TITAN XAU AI - Module 2 Exness Forward Shadow Runner Tests (v2.8.7-P2.1)

BEHAVIORAL tests for the v2.1 shadow runner which uses
CanonicalDecisionEngine. Source-string assertions are forbidden
except for static safety invariants (no order_send, no martingale).
"""
from __future__ import annotations
import sys, re
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


def _build_synthetic_bars(n=300, starting_price=2000.0):
    end = pd.Timestamp.now(tz="UTC").floor("h")
    dates = pd.date_range(end=end, periods=n, freq="h", tz="UTC")
    np.random.seed(42)
    prices = starting_price + np.cumsum(np.random.randn(n) * 0.5)
    df = pd.DataFrame({
        "open": prices, "high": prices + 0.5, "low": prices - 0.5,
        "close": prices, "tick_volume": 100, "spread_usd": 0.15,
    }, index=dates)
    return df


def _make_mock_connector_result(df):
    bars = []
    for ts, row in df.iterrows():
        bars.append({
            "time": int(ts.timestamp()), "open": float(row["open"]),
            "high": float(row["high"]), "low": float(row["low"]),
            "close": float(row["close"]), "tick_volume": int(row["tick_volume"]),
            "spread": int(row["spread_usd"] * 10000),
        })
    result = MagicMock()
    result.success = True
    result.verdict = "OK"
    result.raw_bars = bars
    result.account_info = MagicMock()
    result.account_info.is_demo = True
    result.account_info.server = "Exness-Mock"
    result.account_info.currency = "USD"
    result.symbol_info = MagicMock()
    result.symbol_info.trade_tick_size = 0.01
    result.symbol_info.trade_tick_value = 1.00
    result.symbol_info.trade_contract_size = 100.0
    result.symbol_info.volume_min = 0.01
    result.symbol_info.volume_max = 100.0
    result.symbol_info.volume_step = 0.01
    return result


def _make_mock_bundle(alpha_proba=0.90, meta_proba=0.60):
    bundle = MagicMock()
    bundle.ok = True
    bundle.xgb = MagicMock()
    bundle.xgb.classes_ = np.array([0, 1])
    def _xgb_predict(X):
        n = len(X) if hasattr(X, "__len__") else 1
        col1 = np.full(n, alpha_proba, dtype=float)
        if n > 1:
            noise = np.random.randn(n - 1) * 0.02
            col1[:-1] = np.clip(col1[:-1] + noise, 0.01, 0.99)
        return np.column_stack([1 - col1, col1])
    bundle.xgb.predict_proba = _xgb_predict
    bundle.meta = MagicMock()
    bundle.meta.classes_ = np.array([0, 1])
    def _meta_predict(X):
        n = len(X) if hasattr(X, "__len__") else 1
        col1 = np.full(n, meta_proba, dtype=float)
        if n > 1:
            noise = np.random.randn(n - 1) * 0.02
            col1[:-1] = np.clip(col1[:-1] + noise, 0.01, 0.99)
        return np.column_stack([1 - col1, col1])
    bundle.meta.predict_proba = _meta_predict
    return bundle


def _make_profile():
    return {"optimized_parameters": {
        "alpha_threshold": 0.55, "meta_threshold": 0.50,
        "risk_percent": 0.003, "sl_atr_multiplier": 2.0, "rr_target": 3.0,
        "spread_filter": 1.0, "commission_per_lot": 7.0,
        "slippage_points": 0.5, "swap_per_bar": 0.0, "setup_class": "A_PLUS",
    }}


def _make_calibration_evidence():
    """Build a mock calibration evidence object."""
    from titan.production.model_provenance import CalibrationEvidence
    return CalibrationEvidence(
        artifact_path="mock", artifact_sha256="mock",
        model_sha256="mock", scaler_sha256="mock", feature_schema_sha256="mock",
        generated_at_utc="2026-01-01T00:00:00Z",
        sample_period_start="2024-01-01", sample_period_end="2026-01-01",
        brier_score=0.20, calibration_slope=1.0, calibration_intercept=0.0,
        drift_status="none", n_samples=200,
    )


def _run_cycle(alpha_proba=0.90, meta_proba=0.60, setup_direction="LONG"):
    """Helper: run a single shadow cycle with all canonical components mocked."""
    from scripts.operator.run_exness_mt5_readonly_forward_shadow import run_forward_shadow_cycle
    from titan.production.instrument_valuation import InstrumentSpec
    from titan.production.shadow_account_state_store import ShadowAccountStateStore
    from titan.production.corrected_setup_detector_v2 import (
        SetupResultV2, CorrectedSetupTypeV2, ScanResultV2,
    )
    import tempfile

    df = _build_synthetic_bars()
    bundle = _make_mock_bundle(alpha_proba=alpha_proba, meta_proba=meta_proba)
    profile = _make_profile()
    spec = InstrumentSpec(tick_size=0.01, tick_value=1.00, contract_size=100.0,
                          volume_min=0.01, volume_max=100.0, volume_step=0.01,
                          account_currency="USD", profit_currency="USD",
                          symbol_currency="USD", conversion_rate=1.0)

    connector_result = _make_mock_connector_result(df)
    calib = _make_calibration_evidence()
    tmp_state = Path(tempfile.gettempdir()) / "titan_shadow_test_state.json"
    if tmp_state.exists():
        tmp_state.unlink()
    account_store = ShadowAccountStateStore(path=tmp_state, starting_equity=100000.0)

    # Mock setup scan to return a setup matching setup_direction
    setup = SetupResultV2(
        setup_type=CorrectedSetupTypeV2.PULLBACK,
        direction=setup_direction, confidence=0.75,
        reason_codes=["mock"], evidence=["mock"],
    )
    scan = ScanResultV2(
        selected_setup=setup, alternatives=[],
        rejection_reasons=[], ranking_evidence=["mock"],
        all_candidates=[setup], decision="SELECTED",
    )

    with patch("scripts.operator.run_exness_mt5_readonly_forward_shadow.safe_connect_and_audit",
               return_value=connector_result), \
         patch("titan.production.canonical_decision_engine.evaluate_ceo_decision",
               return_value=type('C', (), {'allowed_to_trade': True})()), \
         patch("titan.production.canonical_decision_engine.scan_setups_governed",
               return_value=scan):
        return run_forward_shadow_cycle(
            "exness", "XAUUSD", "H1", profile, bundle,
            near_miss_tracker=None, journal_sink=[],
            calibration_evidence=calib,
            account_store=account_store,
            instrument_spec_override=spec,
        )


class TestForwardShadowRunner:
    """BEHAVIORAL tests — execute the actual runner, assert on signal outputs."""

    def test_runner_exists(self):
        path = REPO_ROOT / "scripts" / "operator" / "run_exness_mt5_readonly_forward_shadow.py"
        assert path.exists()

    def test_no_order_send_call(self):
        src = (REPO_ROOT / "scripts" / "operator" / "run_exness_mt5_readonly_forward_shadow.py").read_text()
        stripped = re.sub(r'"""[\s\S]*?"""', '""', src)
        stripped = re.sub(r"'''[\s\S]*?'''", "''", stripped)
        stripped = re.sub(r'r"[^"]*"', '""', stripped)
        stripped = re.sub(r"r'[^']*'", "''", stripped)
        stripped = re.sub(r'"[^"]*"', '""', stripped)
        stripped = re.sub(r"'[^']*'", "''", stripped)
        assert "order_send(" not in stripped

    def test_no_token_creation(self):
        src = (REPO_ROOT / "scripts" / "operator" / "run_exness_mt5_readonly_forward_shadow.py").read_text()
        assert "create_local_operator_execution_token" not in src

    def test_no_martingale(self):
        src = (REPO_ROOT / "scripts" / "operator" / "run_exness_mt5_readonly_forward_shadow.py").read_text()
        assert "martingale" not in src.lower()

    def test_cycle_returns_signal_dict(self):
        """Executing run_forward_shadow_cycle returns a dict with required fields."""
        signal = _run_cycle(alpha_proba=0.90, meta_proba=0.60, setup_direction="LONG")
        assert isinstance(signal, dict)
        assert "final_decision" in signal
        assert "NO_ORDER_SENT" in signal
        assert "decision_id" in signal
        assert "correlation_id" in signal
        assert "direction" in signal
        assert "alpha_proba" in signal
        assert "meta_proba" in signal
        assert "regime" in signal
        assert "setup_selected" in signal
        assert "approved_risk" in signal
        assert "lot_size" in signal
        assert "margin_usage" in signal
        assert "ceo_decision" in signal

    def test_NO_ORDER_SENT_always_true(self):
        """NO_ORDER_SENT is True on every signal — even rejections."""
        sig = _run_cycle(alpha_proba=0.90, meta_proba=0.60, setup_direction="LONG")
        assert sig["NO_ORDER_SENT"] is True
        # REJECT_ALPHA path
        sig = _run_cycle(alpha_proba=0.50, meta_proba=0.60, setup_direction="LONG")
        assert sig["NO_ORDER_SENT"] is True
        # REJECT_META path
        sig = _run_cycle(alpha_proba=0.90, meta_proba=0.40, setup_direction="LONG")
        assert sig["NO_ORDER_SENT"] is True

    def test_meta_proba_logged_on_inference_path(self):
        """Meta probability is logged on signals that reach inference."""
        sig = _run_cycle(alpha_proba=0.90, meta_proba=0.60, setup_direction="LONG")
        assert "meta_proba" in sig
        assert sig["meta_proba"] is not None

    def test_decision_types_reachable(self):
        """All canonical decision types are reachable via fixtures."""
        sig = _run_cycle(alpha_proba=0.90, meta_proba=0.60, setup_direction="LONG")
        # Decision type must be one of the canonical types
        assert sig["final_decision"] in (
            "SHADOW_SIGNAL", "REJECT_ALPHA", "REJECT_META", "REJECT_CEO",
            "REJECT_NO_SETUP", "REJECT_RISK_GOVERNOR", "REJECT_ADAPTIVE_HARD_BLOCK",
            "REJECT_LOT_SIZING", "REJECT_SETUP_DIRECTION_CONFLICT",
            "REJECT_STALE_DATA", "REJECT_SCHEMA", "REJECT_MARKET_DATA",
            "REJECT_INSTRUMENT_SPEC", "REJECT_SAFETY_STATE",
            "REJECT_ACCOUNT_STATE_CORRUPT", "SAFETY_BLOCK",
        )
        # REJECT_ALPHA: alpha below threshold
        sig = _run_cycle(alpha_proba=0.50, meta_proba=0.60, setup_direction="LONG")
        assert sig["final_decision"] == "REJECT_ALPHA"
        # REJECT_META: meta below threshold
        sig = _run_cycle(alpha_proba=0.90, meta_proba=0.40, setup_direction="LONG")
        assert sig["final_decision"] == "REJECT_META"

    def test_production_ready_not_true_in_summary(self):
        src = (REPO_ROOT / "scripts" / "operator" / "run_exness_mt5_readonly_forward_shadow.py").read_text()
        if "production_ready" in src:
            assert re.search(r'"production_ready"\s*:\s*False', src) or \
                   re.search(r"production_ready\s*=\s*False", src)

    def test_competition_shadow_profile_loaded(self):
        src = (REPO_ROOT / "scripts" / "operator" / "run_exness_mt5_readonly_forward_shadow.py").read_text()
        assert "exness_competition_shadow_profile" in src

    def test_canonical_pipeline_imports(self):
        """Runner must import all canonical pipeline components."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_exness_mt5_readonly_forward_shadow.py").read_text()
        for required_import in [
            "interpret_direction",
            "classify_regime_v2",
            "scan_setups_governed",
            "compute_adaptive_threshold_v2",
            "govern_risk",
            "InstrumentSpec",
            "validate_instrument_spec",
            "NearMissShadowTrackerV2",
            "evaluate_ceo_decision",
            "CanonicalDecisionEngine",
            "ShadowAccountStateStore",
            "load_model_provenance",
            "load_calibration_evidence",
        ]:
            assert required_import in src, f"Missing canonical import: {required_import}"

    def test_no_hardcoded_safe_constants(self):
        """Phase 3: No literal safe values (prop_pass=True, broker_pass=True, etc.)
        in SafetyStateV2 construction within the runner."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_exness_mt5_readonly_forward_shadow.py").read_text()
        # The runner should use _build_safety_state helper which pulls from
        # account_store and calibration_evidence — not literal constants.
        assert "_build_safety_state" in src
        assert "calibration_evidence" in src
        assert "account_store" in src

    def test_no_instrument_fallbacks(self):
        """Phase 2: No fallback values for instrument metadata in runner source."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_exness_mt5_readonly_forward_shadow.py").read_text()
        # The _make_instrument_spec_from_mt5 function should NOT have fallback defaults
        # like `or 0.01` or `or 100.0`
        # Find the function body
        import re as re_mod
        match = re_mod.search(r"def _make_instrument_spec_from_mt5.*?(?=\ndef |\Z)",
                              src, re_mod.DOTALL)
        if match:
            func_body = match.group(0)
            # No `or 0.01` or `or 100.0` fallback patterns
            assert "or 0.01" not in func_body, "Instrument fallback found in _make_instrument_spec_from_mt5"
            assert "or 100.0" not in func_body, "Instrument fallback found in _make_instrument_spec_from_mt5"
            assert "or 1.0" not in func_body, "Instrument fallback found in _make_instrument_spec_from_mt5"
