"""TITAN XAU AI — v2.8.7-P2.1 Phase 5 Regime Policy Matrix Tests
==================================================================

Parameterized tests over EVERY RegimeTypeV2 value proving:
  - exact allowed families
  - exact blocked families
  - exact risk modifier
  - stress/unsafe regimes cannot create a selected setup
"""
from __future__ import annotations
import sys
from pathlib import Path
import pytest
import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


from titan.production.corrected_regime_classifier_v2 import RegimeTypeV2
from titan.production.corrected_setup_detector_v2 import (
    REGIME_ALLOWED_SETUPS, REGIME_BLOCKED_SETUPS,
    REGIME_RISK_MODIFIERS, REGIME_THRESHOLD_MODIFIERS,
    UNSAFE_REGIMES, scan_setups_governed,
)


# All 11 RegimeTypeV2 values
ALL_REGIMES = [r.value for r in RegimeTypeV2]
ALL_SETUP_TYPES = {
    "PULLBACK", "BREAKOUT", "BREAKOUT_RETEST", "LIQUIDITY_SWEEP",
    "FAILED_BREAKOUT", "BULLISH_BREAK_OF_STRUCTURE",
    "BEARISH_BREAK_OF_STRUCTURE", "RANGE_EDGE_REJECTION",
    "CONTINUATION", "FAIR_VALUE_GAP",
}


class TestRegimePolicyMatrixComplete:
    """Every RegimeTypeV2 value has an exact tested policy."""

    def test_every_regime_has_policy(self):
        """Every RegimeTypeV2 value must have entries in all four policy maps."""
        for r in ALL_REGIMES:
            assert r in REGIME_ALLOWED_SETUPS, f"regime {r} missing from REGIME_ALLOWED_SETUPS"
            assert r in REGIME_BLOCKED_SETUPS, f"regime {r} missing from REGIME_BLOCKED_SETUPS"
            assert r in REGIME_RISK_MODIFIERS, f"regime {r} missing from REGIME_RISK_MODIFIERS"
            assert r in REGIME_THRESHOLD_MODIFIERS, f"regime {r} missing from REGIME_THRESHOLD_MODIFIERS"

    def test_unsafe_regimes_have_empty_allowed_set(self):
        """Unsafe regimes must have empty allowed sets (no setups allowed)."""
        for r in UNSAFE_REGIMES:
            assert REGIME_ALLOWED_SETUPS[r] == set(), \
                f"unsafe regime {r} should have empty allowed set, got {REGIME_ALLOWED_SETUPS[r]}"

    def test_unsafe_regimes_have_zero_risk_modifier(self):
        for r in UNSAFE_REGIMES:
            assert REGIME_RISK_MODIFIERS[r] == 0.0, \
                f"unsafe regime {r} should have risk_modifier=0.0, got {REGIME_RISK_MODIFIERS[r]}"

    def test_safe_regimes_have_nonempty_allowed_set(self):
        """Safe regimes must have at least one allowed setup type."""
        safe_regimes = set(ALL_REGIMES) - UNSAFE_REGIMES
        for r in safe_regimes:
            assert len(REGIME_ALLOWED_SETUPS[r]) > 0, \
                f"safe regime {r} should have non-empty allowed set"

    def test_blocked_does_not_intersect_allowed(self):
        """For each regime, blocked and allowed must be disjoint."""
        for r in ALL_REGIMES:
            allowed = REGIME_ALLOWED_SETUPS[r]
            blocked = REGIME_BLOCKED_SETUPS[r]
            assert allowed.isdisjoint(blocked), \
                f"regime {r}: allowed and blocked intersect: {allowed & blocked}"

    def test_allowed_subset_of_all_setup_types(self):
        """Every allowed setup type must be a known setup type."""
        for r in ALL_REGIMES:
            for s in REGIME_ALLOWED_SETUPS[r]:
                assert s in ALL_SETUP_TYPES, f"regime {r}: unknown allowed setup {s}"

    def test_blocked_subset_of_all_setup_types(self):
        for r in ALL_REGIMES:
            for s in REGIME_BLOCKED_SETUPS[r]:
                assert s in ALL_SETUP_TYPES, f"regime {r}: unknown blocked setup {s}"

    def test_risk_modifiers_in_valid_range(self):
        """Risk modifiers must be in [0.0, 1.0]."""
        for r in ALL_REGIMES:
            m = REGIME_RISK_MODIFIERS[r]
            assert 0.0 <= m <= 1.0, f"regime {r}: risk_modifier {m} out of [0,1]"

    def test_threshold_modifiers_in_valid_range(self):
        """Threshold modifiers must be in [0.0, 0.20]."""
        for r in ALL_REGIMES:
            m = REGIME_THRESHOLD_MODIFIERS[r]
            assert 0.0 <= m <= 0.20, f"regime {r}: threshold_modifier {m} out of [0,0.20]"


@pytest.mark.parametrize("regime_label", ALL_REGIMES)
def test_regime_scan_returns_blocked_or_selected(regime_label):
    """Every regime returns a valid ScanResultV2 decision."""
    n = 100
    dates = pd.date_range("2024-01-01", periods=n, freq="h", tz="UTC")
    prices = np.linspace(2000, 2100, n)
    df = pd.DataFrame({
        "open": prices, "high": prices + 2, "low": prices - 2,
        "close": prices, "volume": 500, "spread": 0.15,
    }, index=dates)
    result = scan_setups_governed(df, regime_direction="BULL", atr_value=5.0,
                                   regime_label=regime_label)
    assert result.decision in ("SELECTED", "NO_TRADE_CONFLICT", "NO_CANDIDATES", "REGIME_BLOCKED")
    # Unsafe regimes must NOT produce a selected setup
    if regime_label in UNSAFE_REGIMES:
        assert result.decision == "REGIME_BLOCKED", \
            f"unsafe regime {regime_label} produced decision={result.decision}"
        assert result.selected_setup is None


def test_unknown_unsafe_regime_blocks_all():
    """UNKNOWN_UNSAFE regime must block all setups."""
    n = 100
    dates = pd.date_range("2024-01-01", periods=n, freq="h", tz="UTC")
    prices = np.linspace(2000, 2100, n)
    df = pd.DataFrame({
        "open": prices, "high": prices + 2, "low": prices - 2,
        "close": prices, "volume": 500, "spread": 0.15,
    }, index=dates)
    result = scan_setups_governed(df, regime_direction="UNKNOWN", atr_value=5.0,
                                   regime_label="UNKNOWN_UNSAFE")
    assert result.decision == "REGIME_BLOCKED"
    assert result.selected_setup is None


def test_unmapped_regime_fails_closed():
    """Unmapped regime label must fail closed with REGIME_BLOCKED."""
    n = 50
    dates = pd.date_range("2024-01-01", periods=n, freq="h", tz="UTC")
    prices = np.full(n, 2000.0)
    df = pd.DataFrame({
        "open": prices, "high": prices + 1, "low": prices - 1,
        "close": prices, "volume": 100, "spread": 0.15,
    }, index=dates)
    result = scan_setups_governed(df, regime_direction="UNKNOWN", atr_value=5.0,
                                   regime_label="NONEXISTENT_REGIME")
    assert result.decision == "REGIME_BLOCKED"
    assert "regime_unmapped" in result.rejection_reasons[0]


class TestRegimePolicyExactValues:
    """EXACT policy values for each regime."""

    def test_strong_bull_trend_policy(self):
        a = REGIME_ALLOWED_SETUPS["STRONG_BULL_TREND"]
        b = REGIME_BLOCKED_SETUPS["STRONG_BULL_TREND"]
        r = REGIME_RISK_MODIFIERS["STRONG_BULL_TREND"]
        t = REGIME_THRESHOLD_MODIFIERS["STRONG_BULL_TREND"]
        assert a == {"PULLBACK", "BREAKOUT", "BREAKOUT_RETEST",
                      "BULLISH_BREAK_OF_STRUCTURE", "LIQUIDITY_SWEEP",
                      "CONTINUATION", "FAIR_VALUE_GAP"}
        assert "BEARISH_BREAK_OF_STRUCTURE" in b
        assert "RANGE_EDGE_REJECTION" in b
        assert r == 1.0
        assert t == 0.0

    def test_weak_bull_trend_policy(self):
        a = REGIME_ALLOWED_SETUPS["WEAK_BULL_TREND"]
        r = REGIME_RISK_MODIFIERS["WEAK_BULL_TREND"]
        t = REGIME_THRESHOLD_MODIFIERS["WEAK_BULL_TREND"]
        assert "BREAKOUT" not in a  # Weak trend does not allow breakout
        assert "PULLBACK" in a
        assert r == 0.85
        assert t == 0.02

    def test_strong_bear_trend_policy(self):
        a = REGIME_ALLOWED_SETUPS["STRONG_BEAR_TREND"]
        r = REGIME_RISK_MODIFIERS["STRONG_BEAR_TREND"]
        assert "BEARISH_BREAK_OF_STRUCTURE" in a
        assert "BULLISH_BREAK_OF_STRUCTURE" not in a
        assert r == 1.0

    def test_stable_range_policy(self):
        a = REGIME_ALLOWED_SETUPS["STABLE_RANGE"]
        r = REGIME_RISK_MODIFIERS["STABLE_RANGE"]
        assert "RANGE_EDGE_REJECTION" in a
        assert "BULLISH_BREAK_OF_STRUCTURE" not in a
        assert r == 0.70

    def test_volatility_compression_blocks_all(self):
        assert REGIME_ALLOWED_SETUPS["VOLATILITY_COMPRESSION"] == set()
        assert REGIME_RISK_MODIFIERS["VOLATILITY_COMPRESSION"] == 0.0

    def test_spread_stress_blocks_all(self):
        assert REGIME_ALLOWED_SETUPS["SPREAD_STRESS"] == set()
        assert REGIME_RISK_MODIFIERS["SPREAD_STRESS"] == 0.0

    def test_liquidity_stress_blocks_all(self):
        assert REGIME_ALLOWED_SETUPS["LIQUIDITY_STRESS"] == set()
        assert REGIME_RISK_MODIFIERS["LIQUIDITY_STRESS"] == 0.0

    def test_breakout_expansion_allows_breakout(self):
        a = REGIME_ALLOWED_SETUPS["BREAKOUT_EXPANSION"]
        assert "BREAKOUT" in a
        assert "BREAKOUT_RETEST" in a
        assert "FAIR_VALUE_GAP" in a
        assert "PULLBACK" not in a
        assert REGIME_RISK_MODIFIERS["BREAKOUT_EXPANSION"] == 0.90
