"""
TITAN XAU AI — Model Registry + Loader + Versioning (Module 9f)
SHA-256 content-addressed model storage. Version tracking.
Champion/Challenger support. ONNX preference for inference.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional

import numpy as np

from .base_model import IModel, ModelType, ModelMetadata

logger = logging.getLogger(__name__)


class ModelRole(str, Enum):
    CHAMPION = "CHAMPION"     # Current production model
    CHALLENGER = "CHALLENGER" # Candidate model (shadow testing)
    ARCHIVED = "ARCHIVED"     # Previous champion, archived


@dataclass
class RegistryEntry:
    """Model registry entry."""
    model_id: str
    model_type: ModelType
    version: str               # semantic version "1.0.0"
    role: ModelRole
    file_path: str
    onnx_path: str
    file_hash: str             # SHA-256 of model file
    onnx_hash: str             # SHA-256 of ONNX file
    created_at: float
    metrics: dict = field(default_factory=dict)  # sharpe, mdd, etc.
    is_active: bool = True


class ModelRegistry:
    """
    Model registry with versioning and champion/challenger support.
    Stores models in /models/{model_type}/{version}/ structure.
    Maintains registry.json manifest with all entries.
    """

    def __init__(self, registry_path: str = "data/models"):
        self._registry_path = registry_path
        self._manifest_path = os.path.join(registry_path, "registry.json")
        self._entries: dict[str, RegistryEntry] = {}  # model_id → entry
        self._load_manifest()

    def _load_manifest(self) -> None:
        """Load registry manifest from disk."""
        if os.path.exists(self._manifest_path):
            with open(self._manifest_path, "r") as f:
                data = json.load(f)
            for model_id, entry_data in data.items():
                entry_data["model_type"] = ModelType(entry_data["model_type"])
                entry_data["role"] = ModelRole(entry_data["role"])
                self._entries[model_id] = RegistryEntry(**entry_data)
            logger.info(f"Loaded {len(self._entries)} model entries from registry")

    def _save_manifest(self) -> None:
        """Save registry manifest to disk."""
        os.makedirs(self._registry_path, exist_ok=True)
        data = {}
        for model_id, entry in self._entries.items():
            d = asdict(entry)
            d["model_type"] = entry.model_type.value
            d["role"] = entry.role.value
            data[model_id] = d
        with open(self._manifest_path, "w") as f:
            json.dump(data, f, indent=2)

    def register(
        self,
        model: IModel,
        file_path: str,
        onnx_path: str = "",
        metrics: dict = None,
        role: ModelRole = ModelRole.CHALLENGER,
    ) -> RegistryEntry:
        """Register a model in the registry."""
        file_hash = model._compute_file_hash(file_path) if os.path.exists(file_path) else ""
        onnx_hash = model._compute_file_hash(onnx_path) if onnx_path and os.path.exists(onnx_path) else ""

        version = f"{int(time.time())}.0.0"  # Timestamp-based versioning

        entry = RegistryEntry(
            model_id=model.model_id,
            model_type=model.model_type,
            version=version,
            role=role,
            file_path=file_path,
            onnx_path=onnx_path,
            file_hash=file_hash,
            onnx_hash=onnx_hash,
            created_at=time.time(),
            metrics=metrics or {},
        )

        self._entries[model.model_id] = entry
        self._save_manifest()
        logger.info(f"Model registered: {model.model_id} v{version} ({role.value})")
        return entry

    def get_entry(self, model_id: str) -> Optional[RegistryEntry]:
        return self._entries.get(model_id)

    def list_models(self, model_type: ModelType = None) -> list[RegistryEntry]:
        if model_type:
            return [e for e in self._entries.values() if e.model_type == model_type]
        return list(self._entries.values())

    def get_champion(self, model_type: ModelType) -> Optional[RegistryEntry]:
        """Get current champion model for a type."""
        for entry in self._entries.values():
            if entry.model_type == model_type and entry.role == ModelRole.CHAMPION:
                return entry
        return None

    def promote_challenger(self, model_id: str) -> bool:
        """Promote challenger to champion (archive old champion)."""
        if model_id not in self._entries:
            return False

        entry = self._entries[model_id]
        if entry.role != ModelRole.CHALLENGER:
            return False

        # Archive current champion of same type
        for other_id, other in self._entries.items():
            if other.model_type == entry.model_type and other.role == ModelRole.CHAMPION:
                other.role = ModelRole.ARCHIVED
                logger.info(f"Previous champion archived: {other_id}")

        entry.role = ModelRole.CHAMPION
        self._save_manifest()
        logger.info(f"Model promoted to champion: {model_id}")
        return True

    def verify_integrity(self, model_id: str) -> bool:
        """Verify model file hasn't been tampered with."""
        entry = self._entries.get(model_id)
        if not entry:
            return False

        if not os.path.exists(entry.file_path):
            return False

        current_hash = self._compute_hash(entry.file_path)
        if current_hash != entry.file_hash:
            logger.error(f"Model integrity check FAILED: {model_id}")
            return False
        return True

    @staticmethod
    def _compute_hash(path: str) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            while True:
                chunk = f.read(8192)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()


class ModelLoader:
    """
    Loads models from registry. Prefers ONNX for CPU inference.
    Verifies integrity before loading.
    """

    def __init__(self, registry: ModelRegistry):
        self._registry = registry

    def load_model(self, model: IModel, prefer_onnx: bool = True) -> bool:
        """Load model from registry. Prefers ONNX if available."""
        entry = self._registry.get_entry(model.model_id)
        if not entry:
            logger.error(f"Model not in registry: {model.model_id}")
            return False

        # Verify integrity
        if not self._registry.verify_integrity(model.model_id):
            logger.error(f"Integrity check failed: {model.model_id}")
            return False

        # Prefer ONNX if available and requested
        if prefer_onnx and entry.onnx_path and os.path.exists(entry.onnx_path):
            if model.load(entry.onnx_path):
                logger.info(f"Loaded ONNX model: {model.model_id}")
                return True
            logger.warning(f"ONNX load failed, falling back to native: {model.model_id}")

        # Fall back to native format
        return model.load(entry.file_path)

    def load_champion(self, model: IModel) -> bool:
        """Load the current champion model for this model type."""
        entry = self._registry.get_champion(model.model_type)
        if not entry:
            logger.error(f"No champion for type: {model.model_type.value}")
            return False

        # Temporarily set model_id to champion's ID
        original_id = model._model_id
        model._model_id = entry.model_id
        success = self.load_model(model)
        if not success:
            model._model_id = original_id
        return success
