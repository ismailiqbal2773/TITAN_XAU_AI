"""
TITAN XAU AI — Base Model Interface (Module 9a)
Common interface for all AI models (XGBoost, LSTM, Transformer, RL).
ONNX export/import. CPU-optimized inference.
"""
from __future__ import annotations

import hashlib
import logging
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


class ModelType(str, Enum):
    XGBOOST = "xgboost"
    LSTM = "lstm"
    TRANSFORMER = "transformer"
    RL = "rl"
    ENSEMBLE = "ensemble"


class ModelStatus(str, Enum):
    UNLOADED = "UNLOADED"
    LOADED = "LOADED"
    READY = "READY"
    ERROR = "ERROR"
    DISABLED = "DISABLED"


@dataclass
class Prediction:
    """Single model prediction output."""
    model_id: str
    model_type: ModelType
    direction: int          # +1 long, -1 short, 0 flat
    confidence: float        # 0.0 - 1.0
    raw_output: np.ndarray = field(default_factory=lambda: np.array([]))
    inference_time_ms: float = 0.0
    timestamp: float = field(default_factory=time.time)

    @property
    def is_valid(self) -> bool:
        return self.direction in (-1, 0, 1) and 0.0 <= self.confidence <= 1.0


@dataclass
class ModelMetadata:
    """Model version metadata."""
    model_id: str
    model_type: ModelType
    version: str             # semantic version "1.0.0"
    created_at: float
    file_path: str
    file_hash: str           # SHA-256 of model file
    input_shape: tuple
    output_shape: tuple
    features_count: int
    training_samples: int = 0
    training_sharpe: float = 0.0
    onnx_exported: bool = False
    onnx_path: str = ""


class IModel(ABC):
    """Abstract interface for all AI models."""

    def __init__(self, model_id: str, model_type: ModelType):
        self._model_id = model_id
        self._model_type = model_type
        self._status = ModelStatus.UNLOADED
        self._metadata: Optional[ModelMetadata] = None
        self._inference_count = 0
        self._total_inference_ms = 0.0

    @abstractmethod
    def predict(self, features: np.ndarray) -> Prediction:
        """Run inference on features. Returns Prediction."""
        pass

    @abstractmethod
    def load(self, path: str) -> bool:
        """Load model from file."""
        pass

    @abstractmethod
    def save(self, path: str) -> bool:
        """Save model to file."""
        pass

    @abstractmethod
    def export_onnx(self, path: str) -> bool:
        """Export model to ONNX format."""
        pass

    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def model_type(self) -> ModelType:
        return self._model_type

    @property
    def status(self) -> ModelStatus:
        return self._status

    @property
    def metadata(self) -> Optional[ModelMetadata]:
        return self._metadata

    @property
    def avg_inference_ms(self) -> float:
        if self._inference_count == 0:
            return 0.0
        return self._total_inference_ms / self._inference_count

    def _compute_file_hash(self, path: str) -> str:
        """Compute SHA-256 hash of file."""
        h = hashlib.sha256()
        with open(path, "rb") as f:
            while True:
                chunk = f.read(8192)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()

    def _record_inference(self, inference_ms: float) -> None:
        self._inference_count += 1
        self._total_inference_ms += inference_ms

    @staticmethod
    def _softmax(x: np.ndarray) -> np.ndarray:
        """Numerically stable softmax."""
        x = x - np.max(x)
        exp_x = np.exp(x)
        return exp_x / np.sum(exp_x)

    @staticmethod
    def _sigmoid(x: float) -> float:
        return 1.0 / (1.0 + np.exp(-np.clip(x, -500, 500)))
