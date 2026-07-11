"""TITAN XAU AI - Sprint v2.8.7-P Adaptive Threshold Policy Tests"""
from __future__ import annotations
import sys, re
from pathlib import Path
import pytest
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

class TestAdaptiveThresholdPolicy:
    def test_policy_exists(self):
        assert (REPO_ROOT / "titan" / "production" / "adaptive_threshold_policy.py").exists()
    def test_threshold_min_048(self):
        from titan.production.adaptive_threshold_policy import ALPHA_MIN, META_MIN
        assert ALPHA_MIN == 0.48
        assert META_MIN == 0.48
    def test_threshold_max_060(self):
        from titan.production.adaptive_threshold_policy import ALPHA_MAX, META_MAX
        assert ALPHA_MAX == 0.60
        assert META_MAX == 0.60
    def test_default_050(self):
        from titan.production.adaptive_threshold_policy import ALPHA_DEFAULT, META_DEFAULT
        assert ALPHA_DEFAULT == 0.50
        assert META_DEFAULT == 0.50
    def test_relax_only_on_drought(self):
        from titan.production.adaptive_threshold_policy import compute_adaptive_threshold
        # With drought and all safe
        state = compute_adaptive_threshold(
            dd_state={"current_dd":0.01,"daily_dd":0.01},
            spread_state={"current_spread":0.2,"average_spread":0.2},
            volatility_state={"current_atr":5,"average_atr":5,"regime":"NORMAL"},
            regime_confidence=0.7, recent_signal_count=0, recent_reject_reasons=[],
            alpha_distribution=[0.55], meta_distribution=[0.55],
            signal_drought_hours=15, loss_streak=0)
        assert state.alpha_threshold_effective <= 0.50
        assert state.policy_mode == "relaxed"
    def test_tighten_on_risk(self):
        from titan.production.adaptive_threshold_policy import compute_adaptive_threshold
        state = compute_adaptive_threshold(
            dd_state={"current_dd":0.06,"daily_dd":0.025},
            spread_state={"current_spread":0.2,"average_spread":0.2},
            volatility_state={"current_atr":10,"average_atr":5,"regime":"VOLATILITY_EXPANSION"},
            regime_confidence=0.2, recent_signal_count=5, recent_reject_reasons=[],
            alpha_distribution=[0.55], meta_distribution=[0.55],
            signal_drought_hours=0, loss_streak=0)
        assert state.alpha_threshold_effective > 0.50
        assert state.policy_mode == "tightened"
    def test_never_below_048(self):
        from titan.production.adaptive_threshold_policy import compute_adaptive_threshold, ALPHA_MIN
        state = compute_adaptive_threshold(
            dd_state={"current_dd":0,"daily_dd":0},
            spread_state={"current_spread":0,"average_spread":0},
            volatility_state={"current_atr":0,"average_atr":0,"regime":"NORMAL"},
            regime_confidence=1.0, recent_signal_count=0, recent_reject_reasons=[],
            alpha_distribution=[0.6], meta_distribution=[0.6],
            signal_drought_hours=100, loss_streak=0)
        assert state.alpha_threshold_effective >= ALPHA_MIN
    def test_no_order_send(self):
        src = (REPO_ROOT / "titan" / "production" / "adaptive_threshold_policy.py").read_text()
        assert "order_send" not in src
