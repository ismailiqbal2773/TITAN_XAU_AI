"""
TITAN XAU AI — Transformer Model (Module 9d)
Multi-head attention for long-range context.
PyTorch implementation. CPU-optimized. ONNX export.
"""
from __future__ import annotations

import logging
import os
import time
import math
from typing import Optional

import numpy as np

from .base_model import IModel, ModelType, ModelStatus, Prediction, ModelMetadata

logger = logging.getLogger(__name__)

_TORCH = None

def _get_torch():
    global _TORCH
    if _TORCH is None:
        import torch
        import torch.nn as nn
        _TORCH = (torch, nn)
    return _TORCH


class _TransformerNet:
    """PyTorch Transformer network (lazy import)."""

    @staticmethod
    def create(
        input_size: int = 87,
        d_model: int = 128,
        nhead: int = 8,
        num_layers: int = 6,
        num_classes: int = 3,
        seq_len: int = 60,
    ):
        torch, nn = _get_torch()

        class PositionalEncoding(nn.Module):
            def __init__(self, d_model, max_len=500):
                super().__init__()
                pe = torch.zeros(max_len, d_model)
                position = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)
                div_term = torch.exp(torch.arange(0, d_model, 2).float() * (-math.log(10000.0) / d_model))
                pe[:, 0::2] = torch.sin(position * div_term)
                pe[:, 1::2] = torch.cos(position * div_term)
                self.register_buffer('pe', pe.unsqueeze(0))

            def forward(self, x):
                return x + self.pe[:, :x.size(1)]

        class Net(nn.Module):
            def __init__(self):
                super().__init__()
                self.input_proj = nn.Linear(input_size, d_model)
                self.pos_enc = PositionalEncoding(d_model)
                encoder_layer = nn.TransformerEncoderLayer(
                    d_model=d_model, nhead=nhead, dim_feedforward=d_model * 4,
                    dropout=0.1, batch_first=True,
                )
                self.transformer = nn.TransformerEncoder(encoder_layer, num_layers)
                self.fc = nn.Linear(d_model, num_classes)
                self.softmax = nn.Softmax(dim=1)

            def forward(self, x):
                x = self.input_proj(x)
                x = self.pos_enc(x)
                x = self.transformer(x)
                x = x[:, -1, :]  # Last timestep
                x = self.fc(x)
                return self.softmax(x)

        return Net()


class TransformerModel(IModel):
    """
    Transformer model for long-range price context.
    Input: (batch, 60, 87) — 60-bar lookback, 87 features.
    Output: 3-class softmax (long / flat / short).
    """

    def __init__(self, model_id: str = "transformer_v1"):
        super().__init__(model_id, ModelType.TRANSFORMER)
        self._net = None
        self._input_size = 87
        self._d_model = 128
        self._nhead = 8
        self._num_layers = 6
        self._seq_len = 60
        self._onnx_session = None

    def train(
        self,
        X: np.ndarray,
        y: np.ndarray,
        epochs: int = 30,
        batch_size: int = 16,
        learning_rate: float = 0.0001,
    ) -> dict:
        """Train Transformer. X: (samples, seq_len, features). y: class labels."""
        torch, nn = _get_torch()

        self._net = _TransformerNet.create(
            input_size=X.shape[2],
            d_model=self._d_model,
            nhead=self._nhead,
            num_layers=self._num_layers,
            seq_len=X.shape[1],
        )
        self._input_size = X.shape[2]
        self._seq_len = X.shape[1]

        X_tensor = torch.FloatTensor(X)
        y_tensor = torch.LongTensor(y)
        dataset = torch.utils.data.TensorDataset(X_tensor, y_tensor)
        loader = torch.utils.data.DataLoader(dataset, batch_size=batch_size, shuffle=True)

        criterion = nn.CrossEntropyLoss()
        optimizer = torch.optim.AdamW(self._net.parameters(), lr=learning_rate, weight_decay=0.01)

        self._net.train()
        for epoch in range(epochs):
            total_loss = 0
            for batch_X, batch_y in loader:
                optimizer.zero_grad()
                outputs = self._net(batch_X)
                loss = criterion(outputs, batch_y)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(self._net.parameters(), 1.0)
                optimizer.step()
                total_loss += loss.item()

            if (epoch + 1) % 5 == 0:
                logger.info(f"Transformer epoch {epoch+1}/{epochs}, loss: {total_loss/len(loader):.4f}")

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
            if features.ndim == 2:
                features = features[np.newaxis, ...]
            input_data = features.astype(np.float32)
            outputs = self._onnx_session.run(None, {"input": input_data})
            probs = outputs[0][0]
        else:
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
        try:
            if path.endswith(".onnx"):
                return self._load_onnx(path)

            torch, _ = _get_torch()
            self._net = _TransformerNet.create(
                input_size=self._input_size,
                d_model=self._d_model,
                nhead=self._nhead,
                num_layers=self._num_layers,
                seq_len=self._seq_len,
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
            logger.info(f"Transformer model loaded: {path}")
            return True
        except Exception as e:
            logger.error(f"Transformer load failed: {e}")
            self._status = ModelStatus.ERROR
            return False

    def _load_onnx(self, path: str) -> bool:
        try:
            import onnxruntime as ort
            self._onnx_session = ort.InferenceSession(
                path, providers=["CPUExecutionProvider"]
            )
            self._status = ModelStatus.READY
            logger.info(f"Transformer ONNX loaded: {path}")
            return True
        except Exception as e:
            logger.error(f"Transformer ONNX load failed: {e}")
            return False

    def save(self, path: str) -> bool:
        try:
            torch, _ = _get_torch()
            torch.save(self._net.state_dict(), path)
            logger.info(f"Transformer model saved: {path}")
            return True
        except Exception as e:
            logger.error(f"Transformer save failed: {e}")
            return False

    def export_onnx(self, path: str) -> bool:
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
            logger.info(f"Transformer exported to ONNX: {path}")
            return True
        except Exception as e:
            logger.error(f"Transformer ONNX export failed: {e}")
            return False
