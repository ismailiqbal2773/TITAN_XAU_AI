"""TITAN XAU AI - Sprint v2.8.6 Multi-Timeframe Signal Engine Tests"""
from __future__ import annotations
import sys
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


class TestRegimePolicy:
    def test_trend_strong_allowed(self):
        from titan.production.multi_timeframe_signal_engine import get_regime_policy
        p = get_regime_policy("TREND_STRONG")
        assert p.allowed is True
        assert "H1" in p.allowed_timeframes

    def test_holiday_blocked(self):
        from titan.production.multi_timeframe_signal_engine import get_regime_policy
        p = get_regime_policy("HOLIDAY")
        assert p.allowed is False
        assert p.block_reason != ""

    def test_spread_expansion_blocked(self):
        from titan.production.multi_timeframe_signal_engine import get_regime_policy
        p = get_regime_policy("SPREAD_EXPANSION")
        assert p.allowed is False

    def test_unknown_regime_blocked(self):
        from titan.production.multi_timeframe_signal_engine import get_regime_policy
        p = get_regime_policy("UNKNOWN")
        assert p.allowed is False


class TestMTFDecision:
    def test_all_pass_creates_allowed(self):
        from titan.production.multi_timeframe_signal_engine import evaluate_mtf_decision
        d = evaluate_mtf_decision(
            regime_value="TREND_NORMAL",
            alpha_confidence=0.7, alpha_pass=True,
            meta_label_confidence=0.8, meta_label_pass=True,
            alpha_direction="LONG",
            ceo_final_decision="PASS", ceo_allowed=True,
            h1_context_pass=True, m15_confirmation_pass=True, m5_entry_trigger_pass=True,
            h1_data_ok=True, m15_data_ok=True, m5_data_ok=True,
            h1_rates_received=300, m15_rates_received=500, m5_rates_received=800,
            h1_feature_build_ok=True, h1_feature_count=55,
            h1_model_load_ok=True, h1_inference_ok=True, h1_meta_label_ok=True,
        )
        assert d.ceo_allowed is True
        assert d.signal_source == "live_mt5_fresh"
        assert not d.blockers

    def test_regime_block_blocks(self):
        from titan.production.multi_timeframe_signal_engine import evaluate_mtf_decision
        d = evaluate_mtf_decision(
            regime_value="HOLIDAY",
            alpha_confidence=0.9, alpha_pass=True,
            meta_label_confidence=0.9, meta_label_pass=True,
            ceo_allowed=True, ceo_final_decision="PASS",
            h1_context_pass=True, m15_confirmation_pass=True, m5_entry_trigger_pass=True,
            h1_data_ok=True, m15_data_ok=True, m5_data_ok=True,
            h1_rates_received=300, m15_rates_received=500, m5_rates_received=800,
            h1_feature_build_ok=True, h1_feature_count=55,
            h1_model_load_ok=True, h1_inference_ok=True, h1_meta_label_ok=True,
        )
        assert d.ceo_allowed is False
        assert any("REGIME_BLOCKED" in b for b in d.blockers)

    def test_alpha_fail_blocks(self):
        from titan.production.multi_timeframe_signal_engine import evaluate_mtf_decision
        d = evaluate_mtf_decision(
            regime_value="TREND_NORMAL",
            alpha_confidence=0.3, alpha_pass=False,
            meta_label_confidence=0.9, meta_label_pass=True,
            ceo_allowed=True, ceo_final_decision="PASS",
            h1_context_pass=True, m15_confirmation_pass=True, m5_entry_trigger_pass=True,
            h1_data_ok=True, m15_data_ok=True, m5_data_ok=True,
            h1_rates_received=300, m15_rates_received=500, m5_rates_received=800,
            h1_feature_build_ok=True, h1_feature_count=55,
            h1_model_load_ok=True, h1_inference_ok=True, h1_meta_label_ok=True,
        )
        assert d.ceo_allowed is False
        assert any("ALPHA_FAIL" in b for b in d.blockers)

    def test_meta_label_fail_blocks(self):
        from titan.production.multi_timeframe_signal_engine import evaluate_mtf_decision
        d = evaluate_mtf_decision(
            regime_value="TREND_NORMAL",
            alpha_confidence=0.7, alpha_pass=True,
            meta_label_confidence=0.3, meta_label_pass=False,
            ceo_allowed=True, ceo_final_decision="PASS",
            h1_context_pass=True, m15_confirmation_pass=True, m5_entry_trigger_pass=True,
            h1_data_ok=True, m15_data_ok=True, m5_data_ok=True,
            h1_rates_received=300, m15_rates_received=500, m5_rates_received=800,
            h1_feature_build_ok=True, h1_feature_count=55,
            h1_model_load_ok=True, h1_inference_ok=True, h1_meta_label_ok=True,
        )
        assert d.ceo_allowed is False
        assert any("META_LABEL_FAIL" in b for b in d.blockers)

    def test_missing_timeframe_blocks(self):
        from titan.production.multi_timeframe_signal_engine import evaluate_mtf_decision
        d = evaluate_mtf_decision(
            regime_value="TREND_NORMAL",
            alpha_confidence=0.7, alpha_pass=True,
            meta_label_confidence=0.8, meta_label_pass=True,
            ceo_allowed=True, ceo_final_decision="PASS",
            h1_context_pass=True, m15_confirmation_pass=True, m5_entry_trigger_pass=True,
            h1_data_ok=True, m15_data_ok=False, m5_data_ok=True,
            h1_rates_received=300, m15_rates_received=0, m5_rates_received=800,
            h1_feature_build_ok=True, h1_feature_count=55,
            h1_model_load_ok=True, h1_inference_ok=True, h1_meta_label_ok=True,
        )
        assert d.ceo_allowed is False
        assert any("M15_DATA_UNAVAILABLE" in b for b in d.blockers)

    def test_m15_confirmation_fail_blocks(self):
        from titan.production.multi_timeframe_signal_engine import evaluate_mtf_decision
        d = evaluate_mtf_decision(
            regime_value="TREND_NORMAL",
            alpha_confidence=0.7, alpha_pass=True,
            meta_label_confidence=0.8, meta_label_pass=True,
            ceo_allowed=True, ceo_final_decision="PASS",
            h1_context_pass=True, m15_confirmation_pass=False, m5_entry_trigger_pass=True,
            h1_data_ok=True, m15_data_ok=True, m5_data_ok=True,
            h1_rates_received=300, m15_rates_received=500, m5_rates_received=800,
            h1_feature_build_ok=True, h1_feature_count=55,
            h1_model_load_ok=True, h1_inference_ok=True, h1_meta_label_ok=True,
        )
        assert d.ceo_allowed is False
        assert any("M15_CONFIRMATION_FAIL" in b for b in d.blockers)

    def test_m5_trigger_fail_blocks(self):
        from titan.production.multi_timeframe_signal_engine import evaluate_mtf_decision
        d = evaluate_mtf_decision(
            regime_value="TREND_NORMAL",
            alpha_confidence=0.7, alpha_pass=True,
            meta_label_confidence=0.8, meta_label_pass=True,
            ceo_allowed=True, ceo_final_decision="PASS",
            h1_context_pass=True, m15_confirmation_pass=True, m5_entry_trigger_pass=False,
            h1_data_ok=True, m15_data_ok=True, m5_data_ok=True,
            h1_rates_received=300, m15_rates_received=500, m5_rates_received=800,
            h1_feature_build_ok=True, h1_feature_count=55,
            h1_model_load_ok=True, h1_inference_ok=True, h1_meta_label_ok=True,
        )
        assert d.ceo_allowed is False
        assert any("M5_TRIGGER_FAIL" in b for b in d.blockers)

    def test_ceo_block_blocks(self):
        from titan.production.multi_timeframe_signal_engine import evaluate_mtf_decision
        d = evaluate_mtf_decision(
            regime_value="TREND_NORMAL",
            alpha_confidence=0.7, alpha_pass=True,
            meta_label_confidence=0.8, meta_label_pass=True,
            ceo_allowed=False, ceo_final_decision="BLOCKED",
            h1_context_pass=True, m15_confirmation_pass=True, m5_entry_trigger_pass=True,
            h1_data_ok=True, m15_data_ok=True, m5_data_ok=True,
            h1_rates_received=300, m15_rates_received=500, m5_rates_received=800,
            h1_feature_build_ok=True, h1_feature_count=55,
            h1_model_load_ok=True, h1_inference_ok=True, h1_meta_label_ok=True,
        )
        assert d.ceo_allowed is False
        assert any("CEO_BLOCKED" in b for b in d.blockers)

    def test_cached_cannot_pass(self):
        from titan.production.multi_timeframe_signal_engine import evaluate_mtf_decision
        d = evaluate_mtf_decision(
            regime_value="TREND_NORMAL",
            alpha_confidence=0.7, alpha_pass=True,
            meta_label_confidence=0.8, meta_label_pass=True,
            ceo_allowed=True, ceo_final_decision="PASS",
            h1_context_pass=True, m15_confirmation_pass=True, m5_entry_trigger_pass=True,
            h1_data_ok=True, m15_data_ok=True, m5_data_ok=True,
            h1_rates_received=300, m15_rates_received=500, m5_rates_received=800,
            h1_feature_build_ok=True, h1_feature_count=55,
            h1_model_load_ok=True, h1_inference_ok=False, h1_meta_label_ok=True,
        )
        assert d.signal_source == "cached_fallback"
        assert d.cache_used is True
        assert d.ceo_allowed is False
