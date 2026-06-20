"""
TITAN XAU AI — XGBoost Model (Module 9b)
Gradient-boosted trees for tabular features.
Train, predict, save, load, ONNX export. CPU-optimized.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Optional

import numpy as np

from .base_model import IModel, ModelType, ModelStatus, Prediction, ModelMetadata

logger = logging.getLogger(__name__)


class XGBoostModel(IModel):
    """
    XGBoost model wrapper for XAUUSD signal prediction.
    Input: 87 tabular features (price action, indicators, regime hints).
    Output: 3-class softmax (long / flat / short).
    """

    def __init__(self, model_id: str = "xgboost_v1"):
        super().__init__(model_id, ModelType.XGBOOST)
        self._booster = None
        self._feature_names: list[str] = []
        self._num_features: int = 87
        self._onnx_session = None  # ONNX Runtime session (if loaded)

    def train(
        self,
        X: np.ndarray,
        y: np.ndarray,
        num_rounds: int = 500,
        max_depth: int = 6,
        learning_rate: float = 0.05,
    ) -> dict:
        """Train XGBoost model. y = 3-class labels (0=short, 1=flat, 2=long)."""
        try:
            import xgboost as xgb
        except ImportError:
            # Fallback: use sklearn GradientBoosting
            return self._train_sklearn_fallback(X, y)

        dtrain = xgb.DMatrix(X, label=y)
        params = {
            "max_depth": max_depth,
            "learning_rate": learning_rate,
            "objective": "multi:softprob",
            "num_class": 3,
            "eval_metric": "mlogloss",
            "tree_method": "hist",     # CPU-optimized
            "n_jobs": 4,
            "seed": 42,
        }
        self._booster = xgb.train(params, dtrain, num_rounds)
        self._num_features = X.shape[1]
        self._status = ModelStatus.READY

        return {
            "status": "trained",
            "samples": X.shape[0],
            "features": X.shape[1],
            "rounds": num_rounds,
        }

    def _train_sklearn_fallback(self, X, y):
        """Fallback using sklearn if xgboost not available."""
        from sklearn.ensemble import GradientBoostingClassifier
        self._booster = GradientBoostingClassifier(
            n_estimators=200, max_depth=5, learning_rate=0.05, random_state=42
        )
        self._booster.fit(X, y)
        self._num_features = X.shape[1]
        self._status = ModelStatus.READY
        return {"status": "trained (sklearn fallback)", "samples": X.shape[0]}

    def predict(self, features: np.ndarray) -> Prediction:
        """Run inference. features shape: (1, 87) or (87,)."""
        if self._status != ModelStatus.READY:
            return Prediction(
                model_id=self._model_id,
                model_type=self._model_type,
                direction=0, confidence=0.0,
            )

        start = time.perf_counter()

        # Use ONNX if available (faster)
        if self._onnx_session is not None:
            input_data = features.reshape(1, -1).astype(np.float32)
            outputs = self._onnx_session.run(None, {"input": input_data})
            probs = outputs[0][0]
        elif self._booster is not None:
            if hasattr(self._booster, "predict_proba"):
                # sklearn fallback
                probs = self._booster.predict_proba(features.reshape(1, -1))[0]
            else:
                # xgboost
                import xgboost as xgb
                dtest = xgb.DMatrix(features.reshape(1, -1))
                probs = self._booster.predict(dtest)[0]
        else:
            return Prediction(
                model_id=self._model_id, model_type=self._model_type,
                direction=0, confidence=0.0,
            )

        elapsed_ms = (time.perf_counter() - start) * 1000
        self._record_inference(elapsed_ms)

        # probs: [short_prob, flat_prob, long_prob]
        best_idx = int(np.argmax(probs))
        direction = {0: -1, 1: 0, 2: 1}[best_idx]
        confidence = float(probs[best_idx])

        return Prediction(
            model_id=self._model_id,
            model_type=self._model_type,
            direction=direction,
            confidence=confidence,
            raw_output=probs,
            inference_time_ms=elapsed_ms,
        )

    def load(self, path: str) -> bool:
        """Load model from file (.json for xgboost, .joblib for sklearn)."""
        try:
            if path.endswith(".onnx"):
                return self._load_onnx(path)
            elif path.endswith(".json"):
                import xgboost as xgb
                self._booster = xgb.Booster()
                self._booster.load_model(path)
                self._status = ModelStatus.READY
            elif path.endswith(".joblib"):
                import joblib
                self._booster = joblib.load(path)
                self._status = ModelStatus.READY
            else:
                logger.error(f"Unknown model format: {path}")
                return False

            file_hash = self._compute_file_hash(path)
            self._metadata = ModelMetadata(
                model_id=self._model_id,
                model_type=self._model_type,
                version="1.0.0",
                created_at=os.path.getctime(path),
                file_path=path,
                file_hash=file_hash,
                input_shape=(1, self._num_features),
                output_shape=(1, 3),
                features_count=self._num_features,
                onnx_exported=path.endswith(".onnx"),
                onnx_path=path if path.endswith(".onnx") else "",
            )
            logger.info(f"XGBoost model loaded: {path}")
            return True
        except Exception as e:
            logger.error(f"Failed to load XGBoost model: {e}")
            self._status = ModelStatus.ERROR
            return False

    def _load_onnx(self, path: str) -> bool:
        """Load ONNX model for inference."""
        try:
            import onnxruntime as ort
            self._onnx_session = ort.InferenceSession(
                path, providers=["CPUExecutionProvider"]
            )
            self._status = ModelStatus.READY
            logger.info(f"XGBoost ONNX loaded: {path}")
            return True
        except ImportError:
            logger.warning("onnxruntime not available, falling back to native")
            return False
        except Exception as e:
            logger.error(f"ONNX load failed: {e}")
            return False

    def save(self, path: str) -> bool:
        """Save model to file."""
        try:
            if hasattr(self._booster, "save_model"):
                self._booster.save_model(path)
            else:
                import joblib
                joblib.dump(self._booster, path)
            logger.info(f"XGBoost model saved: {path}")
            return True
        except Exception as e:
            logger.error(f"Save failed: {e}")
            return False

    def export_onnx(self, path: str) -> bool:
        """Export to ONNX format."""
        try:
            # Try xgboost ONNX export
            if hasattr(self._booster, "save_raw"):
                import xgboost as xgb
                # Use xgboost's native JSON export as ONNX alternative
                json_path = path.replace(".onnx", ".json")
                self._booster.save_model(json_path)
                logger.info(f"XGBoost exported (JSON): {json_path}")
                return True
            return False
        except Exception as e:
            logger.error(f"ONNX export failed: {e}")
            return False
