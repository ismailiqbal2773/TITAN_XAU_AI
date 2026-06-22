"""
TITAN XAU AI — Production Inference Loop (Sprint 1)

Chains: H1FeatureStream → xgboost_v1 → meta_label_v2_context → Signal

Produces a Signal dataclass with direction (LONG/FLAT/SHORT),
confidence, meta-confidence, and the raw probabilities. Designed to
be called from a higher-level trade_loop once per new H1 bar close.

Usage:
    from titan.production.inference import InferenceEngine, Signal
    engine = InferenceEngine()           # auto-loads models
    signal = engine.generate(source="canonical")
    if signal.is_tradeable:
        # hand off to risk.evaluate + execution.place_order
        ...
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import numpy as np

from .feature_stream import H1FeatureStream, FeatureVector, N_FEATURES, FEATURE_NAMES
from .model_loader import (
    ModelBundle, load_production_models, extract_meta_features,
)

logger = logging.getLogger(__name__)

# ─── Decision thresholds (mirror Phase F-Prime spec) ─────────────────────────
XGB_PROB_THRESHOLD = 0.55      # L1: P ≥ 0.55 → directional signal
META_PROB_THRESHOLD = 0.65     # L2: P(win) ≥ 0.65 → trade approved


class Direction(int, Enum):
    SHORT = -1
    FLAT = 0
    LONG = 1


@dataclass
class Signal:
    """Output of the inference chain."""
    timestamp: object                  # pd.Timestamp of the latest bar
    direction: Direction
    confidence: float                  # XGB probability of predicted class
    meta_confidence: float             # Meta-label P(win)
    xgb_proba: list[float]             # [P(class_0), P(class_1)]
    meta_proba: list[float]            # [P(lose), P(win)]
    is_tradeable: bool                 # True iff direction != FLAT AND meta >= threshold
    reject_reason: Optional[str] = None
    feature_vector: Optional[np.ndarray] = None
    inference_ms: float = 0.0
    source: str = ""

    def __repr__(self) -> str:
        return (
            f"Signal(ts={self.timestamp}, dir={self.direction.name}, "
            f"conf={self.confidence:.3f}, meta={self.meta_confidence:.3f}, "
            f"tradeable={self.is_tradeable}, reason={self.reject_reason})"
        )


class InferenceEngine:
    """
    Wires feature_stream + model_loader into a single .generate() call.

    Lifecycle:
        engine = InferenceEngine()                # loads models once
        engine.warmup(source="canonical")        # prime feature buffer
        signal = engine.generate(source="canonical")
        signal = engine.generate(source="mt5", symbol="XAUUSD")
    """

    def __init__(
        self,
        xgb_threshold: float = XGB_PROB_THRESHOLD,
        meta_threshold: float = META_PROB_THRESHOLD,
        feature_window: int = 300,
        bundle: Optional[ModelBundle] = None,
    ):
        self.xgb_threshold = xgb_threshold
        self.meta_threshold = meta_threshold
        self.feature_stream = H1FeatureStream(window=feature_window)
        self.bundle = bundle or load_production_models()
        if not self.bundle.ok:
            raise RuntimeError(
                f"Cannot start InferenceEngine — models not loaded: {self.bundle.errors}"
            )
        logger.info(
            f"InferenceEngine ready (xgb_thresh={xgb_threshold}, "
            f"meta_thresh={meta_threshold})"
        )

    # ─── Public API ─────────────────────────────────────────────────────

    def warmup(self, source: str = "canonical", symbol: str = "XAUUSD") -> int:
        """Pre-load the feature buffer. Returns bar count loaded."""
        if source == "canonical":
            return self.feature_stream.load_canonical()
        elif source == "mt5":
            return self.feature_stream.load_from_mt5(symbol=symbol,
                                                     n_bars=self.feature_stream.window)
        else:
            raise ValueError(f"Unknown source: {source}")

    def generate(self, source: str = "canonical",
                 symbol: str = "XAUUSD") -> Signal:
        """
        Run the full inference chain:
            bars → 55 features → XGB.predict_proba → 22 meta features
                → meta.predict_proba → Signal

        Args:
            source: "canonical" (offline) or "mt5" (live)
            symbol: MT5 symbol (only for source="mt5")
        """
        t0 = time.perf_counter()

        # ── Step 1: Compute feature vector ──
        fv: FeatureVector = self.feature_stream.latest_vector(source=source,
                                                               symbol=symbol)
        if not fv.is_valid:
            return Signal(
                timestamp=fv.timestamp,
                direction=Direction.FLAT,
                confidence=0.0,
                meta_confidence=0.0,
                xgb_proba=[0.0, 0.0],
                meta_proba=[0.0, 0.0],
                is_tradeable=False,
                reject_reason=f"feature_error: {fv.error}",
                source=source,
            )

        # ── Step 2: XGB prediction ──
        xgb_input = fv.features.reshape(1, -1)
        try:
            xgb_proba = self.bundle.xgb.predict_proba(xgb_input)[0]
        except Exception as e:
            return Signal(
                timestamp=fv.timestamp,
                direction=Direction.FLAT,
                confidence=0.0,
                meta_confidence=0.0,
                xgb_proba=[0.0, 0.0],
                meta_proba=[0.0, 0.0],
                is_tradeable=False,
                reject_reason=f"xgb_error: {e}",
                source=source,
            )

        # Class 0 = down/short, Class 1 = up/long (binary model)
        p_down, p_up = float(xgb_proba[0]), float(xgb_proba[1])
        if p_up >= self.xgb_threshold:
            direction = Direction.LONG
            confidence = p_up
        elif p_down >= self.xgb_threshold:
            direction = Direction.SHORT
            confidence = p_down
        else:
            direction = Direction.FLAT
            confidence = max(p_up, p_down)

        # ── Step 3: Meta-label prediction ──
        try:
            meta_vec = extract_meta_features(fv.features, fv.feature_names)
            meta_proba = self.bundle.meta.predict_proba(meta_vec.reshape(1, -1))[0]
            meta_conf = float(meta_proba[1])  # P(win)
        except Exception as e:
            return Signal(
                timestamp=fv.timestamp,
                direction=direction,
                confidence=confidence,
                meta_confidence=0.0,
                xgb_proba=[p_down, p_up],
                meta_proba=[0.0, 0.0],
                is_tradeable=False,
                reject_reason=f"meta_error: {e}",
                feature_vector=fv.features,
                source=source,
            )

        # ── Step 4: Tradeable decision ──
        is_tradeable = False
        reject_reason = None
        if direction == Direction.FLAT:
            reject_reason = f"xgb_below_threshold ({max(p_up, p_down):.3f} < {self.xgb_threshold})"
        elif meta_conf < self.meta_threshold:
            reject_reason = f"meta_below_threshold ({meta_conf:.3f} < {self.meta_threshold})"
        else:
            is_tradeable = True

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return Signal(
            timestamp=fv.timestamp,
            direction=direction,
            confidence=confidence,
            meta_confidence=meta_conf,
            xgb_proba=[p_down, p_up],
            meta_proba=[float(meta_proba[0]), float(meta_proba[1])],
            is_tradeable=is_tradeable,
            reject_reason=reject_reason,
            feature_vector=fv.features,
            inference_ms=elapsed_ms,
            source=source,
        )

    # ─── Diagnostics ────────────────────────────────────────────────────

    def status(self) -> dict:
        """Return a status dict for monitoring."""
        return {
            "models_ok": self.bundle.ok,
            "xgb_n_features": self.bundle.xgb_n_features,
            "meta_n_features": self.bundle.meta_n_features,
            "xgb_classes": self.bundle.xgb_classes,
            "meta_classes": self.bundle.meta_classes,
            "xgb_threshold": self.xgb_threshold,
            "meta_threshold": self.meta_threshold,
            "bars_buffered": len(self.feature_stream._bars),
            "min_bars_required": self.feature_stream.window,
        }


if __name__ == "__main__":
    # Smoke test
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    print("=" * 70)
    print("TITAN InferenceEngine — Smoke Test")
    print("=" * 70)
    engine = InferenceEngine()
    print(f"\nStatus: {engine.status()}")
    print(f"\nRunning inference on canonical H1 data...")
    signal = engine.generate(source="canonical")
    print(f"\n{signal}")
    print(f"\n  xgb_proba: {signal.xgb_proba}")
    print(f"  meta_proba: {signal.meta_proba}")
    print(f"  feature_vector shape: {signal.feature_vector.shape if signal.feature_vector is not None else None}")
    print(f"  inference_ms: {signal.inference_ms:.2f}")
    if signal.is_tradeable:
        print(f"\n  ✓ TRADEABLE SIGNAL GENERATED")
    else:
        print(f"\n  ⚠ Signal rejected: {signal.reject_reason}")
    print("\n✓ InferenceEngine smoke test complete")
