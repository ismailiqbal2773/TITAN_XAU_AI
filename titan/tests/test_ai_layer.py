"""Tests for AI Layer — Base Model, Ensemble Voter, Model Registry"""
import pytest
import numpy as np
import os
import tempfile
from titan.ai.base_model import IModel, ModelType, ModelStatus, Prediction, ModelMetadata
from titan.ai.ensemble_voter import EnsembleVoter, EnsembleResult
from titan.ai.model_registry import ModelRegistry, ModelLoader, ModelRole, RegistryEntry


# ─── Mock Models for Testing ───

class MockModel(IModel):
    """Mock model for testing ensemble and registry."""
    def __init__(self, model_id, model_type=ModelType.XGBOOST, direction=1, confidence=0.8):
        super().__init__(model_id, model_type)
        self._mock_direction = direction
        self._mock_confidence = confidence
        self._status = ModelStatus.READY

    def predict(self, features):
        import time
        start = time.perf_counter()
        pred = Prediction(
            model_id=self._model_id,
            model_type=self._model_type,
            direction=self._mock_direction,
            confidence=self._mock_confidence,
            raw_output=np.array([0.1, 0.1, 0.8]),
            inference_time_ms=1.0,
        )
        self._record_inference(1.0)
        return pred

    def load(self, path):
        self._status = ModelStatus.READY
        return True

    def save(self, path):
        with open(path, "w") as f:
            f.write("mock")
        return True

    def export_onnx(self, path):
        with open(path, "w") as f:
            f.write("mock_onnx")
        return True


@pytest.fixture
def config():
    return {"min_confidence": 0.65, "quorum": 3}


@pytest.fixture
def mock_models():
    return {
        "xgb": MockModel("xgb", ModelType.XGBOOST, direction=1, confidence=0.85),
        "lstm": MockModel("lstm", ModelType.LSTM, direction=1, confidence=0.75),
        "transformer": MockModel("transformer", ModelType.TRANSFORMER, direction=1, confidence=0.80),
        "rl": MockModel("rl", ModelType.RL, direction=-1, confidence=0.60),
    }


# ─── Base Model Tests ───

class TestPrediction:
    def test_valid_prediction(self):
        p = Prediction(model_id="x", model_type=ModelType.XGBOOST, direction=1, confidence=0.8)
        assert p.is_valid is True

    def test_invalid_direction(self):
        p = Prediction(model_id="x", model_type=ModelType.XGBOOST, direction=5, confidence=0.8)
        assert p.is_valid is False

    def test_invalid_confidence(self):
        p = Prediction(model_id="x", model_type=ModelType.XGBOOST, direction=1, confidence=1.5)
        assert p.is_valid is False

    def test_default_timestamp(self):
        p = Prediction(model_id="x", model_type=ModelType.XGBOOST, direction=0, confidence=0.5)
        assert p.timestamp > 0


class TestMockModel:
    def test_predict_returns_prediction(self):
        m = MockModel("test", ModelType.XGBOOST, direction=1, confidence=0.8)
        pred = m.predict(np.array([1.0]))
        assert pred.direction == 1
        assert pred.confidence == 0.8
        assert pred.is_valid

    def test_inference_tracking(self):
        m = MockModel("test", ModelType.XGBOOST)
        m.predict(np.array([1.0]))
        m.predict(np.array([1.0]))
        assert m._inference_count == 2
        assert m.avg_inference_ms > 0


# ─── Ensemble Voter Tests ───

class TestEnsembleVoter:
    def test_register_model(self, config, mock_models):
        voter = EnsembleVoter(config)
        voter.register_model(mock_models["xgb"])
        assert "xgb" in voter.registered_models
        assert voter.active_models == 1

    def test_register_multiple_models(self, config, mock_models):
        voter = EnsembleVoter(config)
        for m in mock_models.values():
            voter.register_model(m)
        assert len(voter.registered_models) == 4

    def test_vote_all_agree(self, config):
        voter = EnsembleVoter(config)
        voter.register_model(MockModel("a", direction=1, confidence=0.9))
        voter.register_model(MockModel("b", direction=1, confidence=0.85))
        voter.register_model(MockModel("c", direction=1, confidence=0.80))
        result = voter.vote()
        assert result.direction == 1
        assert result.agreeing_models == 3
        assert result.quorum_met is True

    def test_vote_disagreement(self, config):
        voter = EnsembleVoter({"min_confidence": 0.40, "quorum": 2})
        voter.register_model(MockModel("a", direction=1, confidence=0.9))
        voter.register_model(MockModel("b", direction=-1, confidence=0.8))
        voter.register_model(MockModel("c", direction=1, confidence=0.7))
        result = voter.vote()
        assert result.direction == 1  # 2 out of 3 agree on long
        assert result.agreeing_models == 2

    def test_disable_model(self, config, mock_models):
        voter = EnsembleVoter(config)
        for m in mock_models.values():
            voter.register_model(m)
        voter.disable_model("rl")
        assert voter.active_models == 3
        assert voter.current_weights["rl"] == 0.0

    def test_enable_model(self, config, mock_models):
        voter = EnsembleVoter(config)
        voter.register_model(mock_models["xgb"])
        voter.disable_model("xgb")
        voter.enable_model("xgb", weight=0.30)
        assert voter.active_models == 1
        assert voter.current_weights["xgb"] > 0

    def test_set_dynamic_weights(self, config, mock_models):
        voter = EnsembleVoter(config)
        for m in mock_models.values():
            voter.register_model(m)
        voter.set_weights({"xgb": 0.50, "lstm": 0.30, "transformer": 0.15, "rl": 0.05})
        weights = voter.current_weights
        assert abs(sum(weights.values()) - 1.0) < 0.01  # Normalized

    def test_low_confidence_returns_flat(self, config):
        voter = EnsembleVoter({"min_confidence": 0.90, "quorum": 3})
        voter.register_model(MockModel("a", direction=1, confidence=0.50))
        voter.register_model(MockModel("b", direction=1, confidence=0.50))
        voter.register_model(MockModel("c", direction=1, confidence=0.50))
        result = voter.vote()
        assert result.direction == 0  # Below threshold → flat

    def test_no_active_models(self, config):
        voter = EnsembleVoter(config)
        result = voter.vote()
        assert result.direction == 0
        assert result.total_models == 0
        assert result.quorum_met is False

    def test_stats_tracking(self, config, mock_models):
        voter = EnsembleVoter(config)
        for m in mock_models.values():
            voter.register_model(m)
        voter.vote()
        voter.vote()
        assert voter.stats["total_votes"] == 2


# ─── Model Registry Tests ───

class TestModelRegistry:
    def test_register_and_retrieve(self, tmp_path):
        registry = ModelRegistry(str(tmp_path))
        model = MockModel("test_xgb", ModelType.XGBOOST)
        # Create dummy model file
        model_file = tmp_path / "model.json"
        model_file.write_text("dummy_model_data")
        entry = registry.register(model, str(model_file))
        assert entry.model_id == "test_xgb"
        assert entry.role == ModelRole.CHALLENGER
        assert entry.file_hash != ""

    def test_get_entry(self, tmp_path):
        registry = ModelRegistry(str(tmp_path))
        model = MockModel("test_xgb", ModelType.XGBOOST)
        model_file = tmp_path / "model.json"
        model_file.write_text("dummy")
        registry.register(model, str(model_file))
        entry = registry.get_entry("test_xgb")
        assert entry is not None
        assert entry.model_id == "test_xgb"

    def test_list_models(self, tmp_path):
        registry = ModelRegistry(str(tmp_path))
        m1 = MockModel("m1", ModelType.XGBOOST)
        m2 = MockModel("m2", ModelType.LSTM)
        f1 = tmp_path / "m1.json"; f1.write_text("d1")
        f2 = tmp_path / "m2.pt"; f2.write_text("d2")
        registry.register(m1, str(f1))
        registry.register(m2, str(f2))
        all_models = registry.list_models()
        assert len(all_models) == 2
        xgb_only = registry.list_models(ModelType.XGBOOST)
        assert len(xgb_only) == 1

    def test_promote_challenger(self, tmp_path):
        registry = ModelRegistry(str(tmp_path))
        champion = MockModel("champ", ModelType.XGBOOST)
        challenger = MockModel("chall", ModelType.XGBOOST)
        f1 = tmp_path / "champ.json"; f1.write_text("c1")
        f2 = tmp_path / "chall.json"; f2.write_text("c2")
        registry.register(champion, str(f1), role=ModelRole.CHAMPION)
        registry.register(challenger, str(f2), role=ModelRole.CHALLENGER)

        success = registry.promote_challenger("chall")
        assert success is True
        assert registry.get_entry("chall").role == ModelRole.CHAMPION
        assert registry.get_entry("champ").role == ModelRole.ARCHIVED

    def test_get_champion(self, tmp_path):
        registry = ModelRegistry(str(tmp_path))
        model = MockModel("champ", ModelType.XGBOOST)
        f = tmp_path / "champ.json"; f.write_text("c")
        registry.register(model, str(f), role=ModelRole.CHAMPION)
        champ = registry.get_champion(ModelType.XGBOOST)
        assert champ is not None
        assert champ.model_id == "champ"

    def test_verify_integrity(self, tmp_path):
        registry = ModelRegistry(str(tmp_path))
        model = MockModel("test", ModelType.XGBOOST)
        f = tmp_path / "model.json"; f.write_text("model_data")
        registry.register(model, str(f))
        assert registry.verify_integrity("test") is True

        # Tamper with file
        f.write_text("tampered")
        assert registry.verify_integrity("test") is False

    def test_manifest_persistence(self, tmp_path):
        registry1 = ModelRegistry(str(tmp_path))
        model = MockModel("persist_test", ModelType.XGBOOST)
        f = tmp_path / "model.json"; f.write_text("data")
        registry1.register(model, str(f))

        # Create new registry instance — should load from manifest
        registry2 = ModelRegistry(str(tmp_path))
        entry = registry2.get_entry("persist_test")
        assert entry is not None
        assert entry.model_id == "persist_test"


class TestModelLoader:
    def test_load_model(self, tmp_path):
        registry = ModelRegistry(str(tmp_path))
        model = MockModel("load_test", ModelType.XGBOOST)
        f = tmp_path / "model.json"; f.write_text("model_data")
        registry.register(model, str(f))

        loader = ModelLoader(registry)
        success = loader.load_model(model)
        assert success is True
        assert model.status == ModelStatus.READY
