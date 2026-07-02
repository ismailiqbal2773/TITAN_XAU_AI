"""TITAN XAU AI - Live Feature Context Adapter (Sprint v2.8.2)
================================================================
Shared adapter that tries multiple methods to get the latest feature
vector from H1FeatureStream, with fallbacks to cached artifacts.

NEVER calls mt5.order_send. NEVER modifies positions.

Adapter tries in order:
  1. H1FeatureStream.latest_vector(source="canonical")
  2. H1FeatureStream.latest_vector(source="mt5", symbol=...)
  3. H1FeatureStream.latest_features()
  4. H1FeatureStream.get_latest() if exists
  5. H1FeatureStream.snapshot() if exists
  6. H1FeatureStream.read_latest() if exists
  7. Latest canonical feature artifact
  8. Latest runtime/context artifact
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass
class FeatureContext:
    """Result of the live feature context adapter."""
    features_available: bool = False
    feature_source: str = ""
    feature_timestamp: str = ""
    feature_count: int = 0
    feature_keys_sample: list = field(default_factory=list)
    adapter_method_used: str = ""
    adapter_error: str = ""
    feature_vector: Any = None  # FeatureVector or dict or None
    trend_score: float = 0.0
    volatility_score: float = 0.0
    range_score: float = 0.0
    spread_score: float = 0.0
    liquidity_score: float = 1.0

    def to_dict(self) -> dict:
        return {
            "features_available": self.features_available,
            "feature_source": self.feature_source,
            "feature_timestamp": self.feature_timestamp,
            "feature_count": self.feature_count,
            "feature_keys_sample": list(self.feature_keys_sample)[:10],
            "adapter_method_used": self.adapter_method_used,
            "adapter_error": self.adapter_error,
            "trend_score": self.trend_score,
            "volatility_score": self.volatility_score,
            "range_score": self.range_score,
            "spread_score": self.spread_score,
            "liquidity_score": self.liquidity_score,
        }


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        if v is None:
            return default
        f = float(v)
        return f if f == f else default
    except (TypeError, ValueError):
        return default


def _extract_scores(fv: Any) -> dict:
    """Extract regime-relevant scores from a feature vector or DataFrame row."""
    scores = {
        "trend_score": 0.0,
        "volatility_score": 0.0,
        "range_score": 0.0,
        "spread_score": 0.0,
        "liquidity_score": 1.0,
    }
    try:
        # Try FeatureVector dataclass
        if hasattr(fv, "features") and hasattr(fv, "feature_names"):
            feats = fv.features
            names = fv.feature_names
            if hasattr(feats, "__len__") and len(feats) == len(names):
                feat_dict = dict(zip(names, feats))
            else:
                feat_dict = {}
        elif hasattr(fv, "to_dict"):
            feat_dict = fv.to_dict()
        elif isinstance(fv, dict):
            feat_dict = fv
        elif hasattr(fv, "iloc"):
            # DataFrame row
            feat_dict = fv.to_dict()
        else:
            feat_dict = {}

        # Map feature names to regime scores
        # trend_score: use adx or sma_20_ratio as proxy
        scores["trend_score"] = _safe_float(
            feat_dict.get("adx", 0) or feat_dict.get("sma_20_ratio", 0)
        )
        # Normalize adx to 0-1 range (adx typically 0-100)
        if scores["trend_score"] > 1.0:
            scores["trend_score"] = min(scores["trend_score"] / 100.0, 1.0)
        # Sign from sma_20_ratio
        sma_ratio = _safe_float(feat_dict.get("sma_200_ratio", 0) or feat_dict.get("sma_20_ratio", 0))
        if sma_ratio < 1.0:
            scores["trend_score"] = -scores["trend_score"]

        # volatility_score: use realized_vol_20 or atr
        vol = _safe_float(feat_dict.get("realized_vol_20", 0) or feat_dict.get("atr", 0))
        scores["volatility_score"] = min(vol / 0.02, 1.0) if vol > 0 else 0.0

        # range_score: use bb_width or close_pos_in_range
        scores["range_score"] = _safe_float(feat_dict.get("bb_width", 0) or feat_dict.get("close_pos_in_range", 0.5))

        # spread_score: use spread_pct
        scores["spread_score"] = _safe_float(feat_dict.get("spread_pct", 0))
        if scores["spread_score"] > 1.0:
            scores["spread_score"] = min(scores["spread_score"] / 100.0, 1.0)

        # liquidity_score: use volume_zscore_60
        vol_z = _safe_float(feat_dict.get("volume_zscore_60", 0))
        scores["liquidity_score"] = max(0.0, min(1.0, 0.5 + vol_z * 0.1))

    except Exception:
        pass
    return scores


def get_live_feature_context(
    symbol: str = "XAUUSD",
    repo_root: Optional[Path] = None,
) -> FeatureContext:
    """Get the latest feature context using multiple fallback methods.

    NEVER calls mt5.order_send. NEVER modifies positions.
    """
    rr = repo_root or REPO_ROOT
    ctx = FeatureContext()

    try:
        from titan.production.feature_stream import H1FeatureStream
        stream = H1FeatureStream()

        # Method 1: latest_vector(source="canonical")
        try:
            fv = stream.latest_vector(source="canonical")
            if fv is not None and getattr(fv, "is_valid", True):
                ctx.features_available = True
                ctx.feature_source = "H1FeatureStream.latest_vector(canonical)"
                ctx.adapter_method_used = "latest_vector_canonical"
                ctx.feature_vector = fv
                ctx.feature_count = getattr(fv, "n_bars_used", 0)
                ctx.feature_timestamp = str(getattr(fv, "timestamp", ""))
                if hasattr(fv, "feature_names"):
                    ctx.feature_keys_sample = list(fv.feature_names[:10])
                scores = _extract_scores(fv)
                ctx.trend_score = scores["trend_score"]
                ctx.volatility_score = scores["volatility_score"]
                ctx.range_score = scores["range_score"]
                ctx.spread_score = scores["spread_score"]
                ctx.liquidity_score = scores["liquidity_score"]
                return ctx
        except Exception as e:
            ctx.adapter_error = f"latest_vector(canonical) failed: {e}"

        # Method 2: latest_vector(source="mt5")
        try:
            fv = stream.latest_vector(source="mt5", symbol=symbol)
            if fv is not None and getattr(fv, "is_valid", True):
                ctx.features_available = True
                ctx.feature_source = f"H1FeatureStream.latest_vector(mt5, {symbol})"
                ctx.adapter_method_used = "latest_vector_mt5"
                ctx.feature_vector = fv
                ctx.feature_count = getattr(fv, "n_bars_used", 0)
                ctx.feature_timestamp = str(getattr(fv, "timestamp", ""))
                if hasattr(fv, "feature_names"):
                    ctx.feature_keys_sample = list(fv.feature_names[:10])
                scores = _extract_scores(fv)
                ctx.trend_score = scores["trend_score"]
                ctx.volatility_score = scores["volatility_score"]
                ctx.range_score = scores["range_score"]
                ctx.spread_score = scores["spread_score"]
                ctx.liquidity_score = scores["liquidity_score"]
                return ctx
        except Exception as e:
            ctx.adapter_error = f"latest_vector(mt5) failed: {e}"

        # Method 3: latest_features()
        try:
            df = stream.latest_features()
            if df is not None and hasattr(df, "iloc") and len(df) > 0:
                ctx.features_available = True
                ctx.feature_source = "H1FeatureStream.latest_features()"
                ctx.adapter_method_used = "latest_features"
                ctx.feature_vector = df
                ctx.feature_count = len(df.columns)
                ctx.feature_keys_sample = list(df.columns[:10])
                scores = _extract_scores(df.iloc[-1])
                ctx.trend_score = scores["trend_score"]
                ctx.volatility_score = scores["volatility_score"]
                ctx.range_score = scores["range_score"]
                ctx.spread_score = scores["spread_score"]
                ctx.liquidity_score = scores["liquidity_score"]
                return ctx
        except Exception as e:
            ctx.adapter_error = f"latest_features() failed: {e}"

        # Method 4: get_latest() if exists
        if hasattr(stream, "get_latest"):
            try:
                fv = stream.get_latest()
                if fv is not None:
                    ctx.features_available = True
                    ctx.feature_source = "H1FeatureStream.get_latest()"
                    ctx.adapter_method_used = "get_latest"
                    ctx.feature_vector = fv
                    scores = _extract_scores(fv)
                    ctx.trend_score = scores["trend_score"]
                    ctx.volatility_score = scores["volatility_score"]
                    ctx.range_score = scores["range_score"]
                    ctx.spread_score = scores["spread_score"]
                    ctx.liquidity_score = scores["liquidity_score"]
                    return ctx
            except Exception as e:
                ctx.adapter_error = f"get_latest() failed: {e}"

        # Method 5: snapshot() if exists
        if hasattr(stream, "snapshot"):
            try:
                fv = stream.snapshot()
                if fv is not None:
                    ctx.features_available = True
                    ctx.feature_source = "H1FeatureStream.snapshot()"
                    ctx.adapter_method_used = "snapshot"
                    ctx.feature_vector = fv
                    scores = _extract_scores(fv)
                    ctx.trend_score = scores["trend_score"]
                    ctx.volatility_score = scores["volatility_score"]
                    ctx.range_score = scores["range_score"]
                    ctx.spread_score = scores["spread_score"]
                    ctx.liquidity_score = scores["liquidity_score"]
                    return ctx
            except Exception as e:
                ctx.adapter_error = f"snapshot() failed: {e}"

        # Method 6: read_latest() if exists
        if hasattr(stream, "read_latest"):
            try:
                fv = stream.read_latest()
                if fv is not None:
                    ctx.features_available = True
                    ctx.feature_source = "H1FeatureStream.read_latest()"
                    ctx.adapter_method_used = "read_latest"
                    ctx.feature_vector = fv
                    scores = _extract_scores(fv)
                    ctx.trend_score = scores["trend_score"]
                    ctx.volatility_score = scores["volatility_score"]
                    ctx.range_score = scores["range_score"]
                    ctx.spread_score = scores["spread_score"]
                    ctx.liquidity_score = scores["liquidity_score"]
                    return ctx
            except Exception as e:
                ctx.adapter_error = f"read_latest() failed: {e}"

    except ImportError:
        ctx.adapter_error = "H1FeatureStream import failed"
    except Exception as e:
        ctx.adapter_error = f"H1FeatureStream init failed: {e}"

    # Method 7: Latest canonical feature artifact
    canonical_artifact = rr / "data" / "runtime" / "latest_features.json"
    if canonical_artifact.exists():
        try:
            with open(canonical_artifact, "r") as f:
                data = json.load(f)
            if data:
                ctx.features_available = True
                ctx.feature_source = "cached_canonical_feature_artifact"
                ctx.adapter_method_used = "artifact_fallback"
                ctx.feature_vector = data
                ctx.feature_count = len(data)
                ctx.feature_keys_sample = list(data.keys())[:10]
                scores = _extract_scores(data)
                ctx.trend_score = scores["trend_score"]
                ctx.volatility_score = scores["volatility_score"]
                ctx.range_score = scores["range_score"]
                ctx.spread_score = scores["spread_score"]
                ctx.liquidity_score = scores["liquidity_score"]
                return ctx
        except Exception as e:
            ctx.adapter_error = f"canonical artifact read failed: {e}"

    # Method 8: Latest runtime/context artifact
    context_artifact = rr / "data" / "runtime" / "latest_context.json"
    if context_artifact.exists():
        try:
            with open(context_artifact, "r") as f:
                data = json.load(f)
            if data:
                ctx.features_available = True
                ctx.feature_source = "cached_runtime_context_artifact"
                ctx.adapter_method_used = "context_artifact_fallback"
                ctx.feature_vector = data
                ctx.feature_count = len(data)
                ctx.feature_keys_sample = list(data.keys())[:10]
                scores = _extract_scores(data)
                ctx.trend_score = scores["trend_score"]
                ctx.volatility_score = scores["volatility_score"]
                ctx.range_score = scores["range_score"]
                ctx.spread_score = scores["spread_score"]
                ctx.liquidity_score = scores["liquidity_score"]
                return ctx
        except Exception as e:
            ctx.adapter_error = f"context artifact read failed: {e}"

    # No features found
    if not ctx.adapter_error:
        ctx.adapter_error = "REGIME_FEATURES_MISSING: no feature source available"
    else:
        ctx.adapter_error = f"REGIME_FEATURES_MISSING: {ctx.adapter_error}"

    return ctx
