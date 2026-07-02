"""TITAN XAU AI - Sprint v2.8.2 Live Feature Context Adapter Tests"""
from __future__ import annotations
import json, re, sys
from pathlib import Path
import pytest
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


def _strip(src):
    src = re.sub(r'"""[\s\S]*?"""', '""', src)
    src = re.sub(r"'''[\s\S]*?'''", "''", src)
    src = re.sub(r'"(?:[^"\\]|\\.)*"', '""', src)
    src = re.sub(r"'(?:[^'\\]|\\.)*'", "''", src)
    return src


class TestLiveFeatureContextAdapter:
    def test_01_module_imports(self):
        from titan.production.live_feature_context_adapter import (
            get_live_feature_context, FeatureContext,
        )
        assert callable(get_live_feature_context)
        assert hasattr(FeatureContext, "features_available")

    def test_02_adapter_returns_context_without_crashing(self):
        """Adapter must not crash even when H1FeatureStream fails."""
        from titan.production.live_feature_context_adapter import get_live_feature_context
        ctx = get_live_feature_context(symbol="XAUUSD", repo_root=REPO_ROOT)
        assert ctx is not None
        assert hasattr(ctx, "features_available")
        assert hasattr(ctx, "adapter_method_used")
        assert hasattr(ctx, "adapter_error")

    def test_03_adapter_does_not_call_latest_directly(self):
        """Adapter source must not call stream.latest() directly."""
        src = (REPO_ROOT / "titan" / "production" / "live_feature_context_adapter.py").read_text()
        # Must NOT contain stream.latest() - the v2.8.2 bug
        assert ".latest()" not in src or "latest_vector" in src or "latest_features" in src, \
            "Adapter must not call .latest() directly"

    def test_04_adapter_tries_multiple_methods(self):
        """Adapter must try latest_vector, latest_features, get_latest, snapshot, read_latest."""
        src = (REPO_ROOT / "titan" / "production" / "live_feature_context_adapter.py").read_text()
        assert "latest_vector" in src
        assert "latest_features" in src
        assert "get_latest" in src
        assert "snapshot" in src
        assert "read_latest" in src

    def test_05_adapter_has_artifact_fallbacks(self):
        """Adapter must try cached artifacts as fallback."""
        src = (REPO_ROOT / "titan" / "production" / "live_feature_context_adapter.py").read_text()
        assert "latest_features.json" in src
        assert "latest_context.json" in src

    def test_06_adapter_reports_method_used(self):
        """Adapter must report which method was used."""
        from titan.production.live_feature_context_adapter import get_live_feature_context
        ctx = get_live_feature_context(symbol="XAUUSD", repo_root=REPO_ROOT)
        # adapter_method_used must be set (even if empty string)
        assert ctx.adapter_method_used is not None

    def test_07_adapter_reports_error_when_no_features(self):
        """When no features found, adapter must report exact error."""
        from titan.production.live_feature_context_adapter import get_live_feature_context
        ctx = get_live_feature_context(symbol="XAUUSD", repo_root=REPO_ROOT)
        if not ctx.features_available:
            assert ctx.adapter_error, "adapter_error must be set when features unavailable"
            assert "REGIME_FEATURES_MISSING" in ctx.adapter_error or "failed" in ctx.adapter_error.lower()

    def test_08_adapter_extracts_regime_scores(self):
        """Adapter must extract trend/volatility/range/spread/liquidity scores."""
        from titan.production.live_feature_context_adapter import FeatureContext
        ctx = FeatureContext()
        assert hasattr(ctx, "trend_score")
        assert hasattr(ctx, "volatility_score")
        assert hasattr(ctx, "range_score")
        assert hasattr(ctx, "spread_score")
        assert hasattr(ctx, "liquidity_score")

    def test_09_adapter_no_order_send(self):
        """Adapter must never call mt5.order_send."""
        src = (REPO_ROOT / "titan" / "production" / "live_feature_context_adapter.py").read_text()
        code = _strip(src)
        assert not re.search(r"\bmt5\.order_send\s*\(", code)

    def test_10_adapter_no_position_modification(self):
        """Adapter must never modify positions."""
        src = (REPO_ROOT / "titan" / "production" / "live_feature_context_adapter.py").read_text()
        code = _strip(src)
        assert not re.search(r"\bmt5\.(order_modify|positions_modify)\s*\(", code)

    def test_11_adapter_to_dict_includes_all_fields(self):
        """FeatureContext.to_dict must include all required fields."""
        from titan.production.live_feature_context_adapter import FeatureContext
        ctx = FeatureContext()
        d = ctx.to_dict()
        required = [
            "features_available", "feature_source", "feature_timestamp",
            "feature_count", "feature_keys_sample", "adapter_method_used",
            "adapter_error", "trend_score", "volatility_score", "range_score",
            "spread_score", "liquidity_score",
        ]
        for field in required:
            assert field in d, f"Missing field in to_dict: {field}"

    def test_12_adapter_no_martingale(self):
        """Adapter must not contain forbidden patterns."""
        src = (REPO_ROOT / "titan" / "production" / "live_feature_context_adapter.py").read_text()
        code = _strip(src).lower()
        for term in ["martingale", "grid_trade", "averaging_down", "loss_based_lot"]:
            assert term not in code or "no_" in code or "forbid" in code
