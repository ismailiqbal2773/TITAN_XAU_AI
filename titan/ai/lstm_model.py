"""
TITAN XAU AI — LSTM Model (Module 9c)
Long Short-Term Memory for sequential pattern recognition.
PyTorch implementation. CPU-optimized. ONNX export.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Optional

import numpy as np

from .base_model import IModel, ModelType, ModelStatus, Prediction, ModelMetadata

logger = logging.getLogger(__name__)

# Lazy import PyTorch (heavy dependency)
_TORCH = None

def _get_torch():
    global _TORCH
    if _TORCH is None:
        import torch
        import torch.nn as nn
        _TORCH = (torch, nn)
    return _TORCH


class _LSTMNet:
    """PyTorch LSTM network definition (lazy import)."""

    @staticmethod
    def create(input_size: int = 87, hidden_size: int = 128, num_layers: int = 2, num_classes: int = 3):
        torch, nn = _get_torch()

        class Net(nn.Module):
            def __init__(self):
                super().__init__()
                self.lstm = nn.LSTM(
                    input_size, hidden_size, num_layers,
                    batch_first=True, dropout=0.1 if num_layers > 1 else 0,
                )
                self.fc = nn.Linear(hidden_size, num_classes)
                self.softmax = nn.Softmax(dim=1)

            def forward(self, x):
                # x shape: (batch, seq_len, input_size)
                out, _ = self.lstm(x)
                out = out[:, -1, :]  # Take last timestep
                out = self.fc(out)
                return self.softmax(out)

        return Net()


class LSTMModel(IModel):
    """
    LSTM model for sequential price pattern recognition.
    Input: (batch, 60, 87) — 60-bar lookback, 87 features.
    Output: 3-class softmax (long / flat / short).
    """

    def __init__(self, model_id: str = "lstm_v1"):
        super().__init__(model_id, ModelType.LSTM)
        self._net = None
        self._input_size = 87
        self._hidden_size = 128
        self._num_layers = 2
        self._seq_len = 60
        self._onnx_session = None

    def train(
        self,
        X: np.ndarray,
        y: np.ndarray,
        epochs: int = 50,
        batch_size: int = 32,
        learning_rate: float = 0.001,
    ) -> dict:
        """Train LSTM. X shape: (samples, seq_len, features). y: class labels."""
        torch, nn = _get_torch()

        self._net = _LSTMNet.create(
            input_size=X.shape[2],
            hidden_size=self._hidden_size,
            num_layers=self._num_layers,
        )
        self._input_size = X.shape[2]
        self._seq_len = X.shape[1]

        # Convert to tensors
        X_tensor = torch.FloatTensor(X)
        y_tensor = torch.LongTensor(y)

        dataset = torch.utils.data.TensorDataset(X_tensor, y_tensor)
        loader = torch.utils.data.DataLoader(dataset, batch_size=batch_size, shuffle=True)

        criterion = nn.CrossEntropyLoss()
        optimizer = torch.optim.Adam(self._net.parameters(), lr=learning_rate)

        self._net.train()
        for epoch in range(epochs):
            total_loss = 0
            for batch_X, batch_y in loader:
                optimizer.zero_grad()
                outputs = self._net(batch_X)
                loss = criterion(outputs, batch_y)
                loss.backward()
                optimizer.step()
                total_loss += loss.item()

            if (epoch + 1) % 10 == 0:
                logger.info(f"LSTM epoch {epoch+1}/{epochs}, loss: {total_loss/len(loader):.4f}")

        self._status = ModelStatus.READY
        return {"status": "trained", "epochs": epochs, "final_loss": total_loss / len(loader)}

    def predict(self, features: np.ndarray) -> Prediction:
        """Run inference. features: (seq_len, input_size) or (1, seq_len, input_size)."""
        if self._status != ModelStatus.READY:
            return Prediction(
                model_id=self._model_id, model_type=self._model_type,
                direction=0, confidence=0.0,
            )

        start = time.perf_counter()

        if self._onnx_session is not None:
            # ONNX inference
            if features.ndim == 2:
                features = features[np.newaxis, ...]
            input_data = features.astype(np.float32)
            outputs = self._onnx_session.run(None, {"input": input_data})
            probs = outputs[0][0]
        else:
            # PyTorch inference
            torch, _ = _get_torch()
            if features.ndim == 2:
                features = features[np.newaxis, ...]
            self._net.eval()
            with torch.no_grad():
                x = torch.FloatTensor(features)
                probs = self._net(x).numpy()[0]

        elapsed_ms = (time.perf_counter() - start) * 1000
        self._record_inference(elapsed_ms)

        best_idx = int(np.argmax(probs))
        direction = {0: -1, 1: 0, 2: 1}[best_idx]
        confidence = float(probs[best_idx])

        return Prediction(
            model_id=self._model_id, model_type=self._model_type,
            direction=direction, confidence=confidence,
            raw_output=probs, inference_time_ms=elapsed_ms,
        )

    def load(self, path: str) -> bool:
        """Load model from file."""
        try:
            if path.endswith(".onnx"):
                return self._load_onnx(path)

            torch, _ = _get_torch()
            self._net = _LSTMNet.create(
                input_size=self._input_size,
                hidden_size=self._hidden_size,
                num_layers=self._num_layers,
            )
            self._net.load_state_dict(torch.load(path, map_location="cpu"))
            self._net.eval()
            self._status = ModelStatus.READY

            file_hash = self._compute_file_hash(path)
            self._metadata = ModelMetadata(
                model_id=self._model_id, model_type=self._model_type,
                version="1.0.0", created_at=os.path.getctime(path),
                file_path=path, file_hash=file_hash,
                input_shape=(1, self._seq_len, self._input_size),
                output_shape=(1, 3), features_count=self._input_size,
            )
            logger.info(f"LSTM model loaded: {path}")
            return True
        except Exception as e:
            logger.error(f"LSTM load failed: {e}")
            self._status = ModelStatus.ERROR
            return False

    def _load_onnx(self, path: str) -> bool:
        try:
            import onnxruntime as ort
            self._onnx_session = ort.InferenceSession(
                path, providers=["CPUExecutionProvider"]
            )
            self._status = ModelStatus.READY
            logger.info(f"LSTM ONNX loaded: {path}")
            return True
        except Exception as e:
            logger.error(f"LSTM ONNX load failed: {e}")
            return False

    def save(self, path: str) -> bool:
        try:
            torch, _ = _get_torch()
            torch.save(self._net.state_dict(), path)
            logger.info(f"LSTM model saved: {path}")
            return True
        except Exception as e:
            logger.error(f"LSTM save failed: {e}")
            return False

    def export_onnx(self, path: str) -> bool:
        """Export to ONNX format."""
        try:
            torch, _ = _get_torch()
            dummy = torch.randn(1, self._seq_len, self._input_size)
            self._net.eval()
            torch.onnx.export(
                self._net, dummy, path,
                input_names=["input"], output_names=["output"],
                dynamic_axes={"input": {0: "batch"}, "output": {0: "batch"}},
                opset_version=14,
            )
            logger.info(f"LSTM exported to ONNX: {path}")
            return True
        except Exception as e:
            logger.error(f"LSTM ONNX export failed: {e}")
            return False
