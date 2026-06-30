"""TITAN XAU AI - Sprint 9.9.3.36 Model Registry Tests"""
from __future__ import annotations
import inspect, json, sys
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from titan.production.model_registry import (
    ModelRegistry, RegisteredModel,
)
from titan.production.model_lifecycle_governance import (
    ModelLifecycleStage, ModelApprovalStatus,
)


class TestRegistration:
    def test_01_new_registration_defaults_to_candidate(self):
        reg = ModelRegistry()
        m = reg.register_model(
            model_id="m1",
            version="0.1.0",
            artifact_path="/data/models/m1_v0.1.0.pkl",
            metrics={"oos_sharpe": 1.5},
        )
        assert m.stage == ModelLifecycleStage.CANDIDATE
        assert m.approval_status == ModelApprovalStatus.PENDING

    def test_02_duplicate_registration_raises(self):
        reg = ModelRegistry()
        reg.register_model("m1", "0.1.0", "/data/m1.pkl")
        with pytest.raises(ValueError):
            reg.register_model("m1", "0.2.0", "/data/m1_v2.pkl")


class TestChampionInvariant:
    def test_03_registry_allows_exactly_one_champion(self):
        reg = ModelRegistry()
        reg.register_model("m1", "0.1.0", "/data/m1.pkl")
        reg.register_model("m2", "0.1.0", "/data/m2.pkl")
        # Promote m1 to champion
        reg.promote_to_challenger("m1", approved_by="operator_a")
        reg.require_manual_champion_promotion(
            "m1", approved_by="operator_a", manual_approval_flag=True
        )
        assert reg.has_exactly_one_champion() is True
        # Now promote m2 to champion - m1 should be retired
        reg.promote_to_challenger("m2", approved_by="operator_a")
        reg.require_manual_champion_promotion(
            "m2", approved_by="operator_a", manual_approval_flag=True
        )
        assert reg.has_exactly_one_champion() is True
        # m1 should be retired
        m1 = reg.get_model("m1")
        assert m1.stage == ModelLifecycleStage.RETIRED
        # m2 should be champion
        m2 = reg.get_model("m2")
        assert m2.stage == ModelLifecycleStage.CHAMPION

    def test_04_no_champion_initially(self):
        reg = ModelRegistry()
        assert reg.has_no_champion() is True
        assert reg.has_exactly_one_champion() is False


class TestChampionPromotionSafety:
    def test_05_champion_promotion_requires_manual_flag(self):
        reg = ModelRegistry()
        reg.register_model("m1", "0.1.0", "/data/m1.pkl")
        reg.promote_to_challenger("m1", approved_by="operator_a")
        with pytest.raises(PermissionError):
            reg.require_manual_champion_promotion(
                "m1", approved_by="operator_a", manual_approval_flag=False
            )

    def test_06_champion_promotion_requires_operator_name(self):
        reg = ModelRegistry()
        reg.register_model("m1", "0.1.0", "/data/m1.pkl")
        reg.promote_to_challenger("m1", approved_by="operator_a")
        with pytest.raises(PermissionError):
            reg.require_manual_champion_promotion(
                "m1", approved_by="", manual_approval_flag=True
            )

    def test_07_cannot_promote_quarantined_to_champion(self):
        reg = ModelRegistry()
        reg.register_model("m1", "0.1.0", "/data/m1.pkl")
        reg.quarantine_model("m1", reason="leakage")
        with pytest.raises(ValueError):
            reg.require_manual_champion_promotion(
                "m1", approved_by="operator_a", manual_approval_flag=True
            )

    def test_08_cannot_promote_rejected_to_champion(self):
        reg = ModelRegistry()
        reg.register_model("m1", "0.1.0", "/data/m1.pkl")
        reg.reject_model("m1", reason="poor performance")
        with pytest.raises(ValueError):
            reg.require_manual_champion_promotion(
                "m1", approved_by="operator_a", manual_approval_flag=True
            )


class TestStateTransitions:
    def test_09_reject_model(self):
        reg = ModelRegistry()
        reg.register_model("m1", "0.1.0", "/data/m1.pkl")
        m = reg.reject_model("m1", reason="poor metrics")
        assert m.stage == ModelLifecycleStage.REJECTED
        assert m.approval_status == ModelApprovalStatus.REJECTED

    def test_10_quarantine_model(self):
        reg = ModelRegistry()
        reg.register_model("m1", "0.1.0", "/data/m1.pkl")
        m = reg.quarantine_model("m1", reason="leakage suspicion")
        assert m.stage == ModelLifecycleStage.QUARANTINED
        assert m.approval_status == ModelApprovalStatus.BLOCKED

    def test_11_retire_model(self):
        reg = ModelRegistry()
        reg.register_model("m1", "0.1.0", "/data/m1.pkl")
        m = reg.retire_model("m1", reason="end of life")
        assert m.stage == ModelLifecycleStage.RETIRED

    def test_12_promote_to_challenger(self):
        reg = ModelRegistry()
        reg.register_model("m1", "0.1.0", "/data/m1.pkl")
        m = reg.promote_to_challenger("m1", approved_by="operator_a")
        assert m.stage == ModelLifecycleStage.CHALLENGER
        assert m.approved_by == "operator_a"


class TestQueries:
    def test_13_get_champion(self):
        reg = ModelRegistry()
        reg.register_model("m1", "0.1.0", "/data/m1.pkl")
        assert reg.get_champion() is None
        reg.promote_to_challenger("m1", approved_by="op")
        reg.require_manual_champion_promotion(
            "m1", approved_by="op", manual_approval_flag=True
        )
        champ = reg.get_champion()
        assert champ is not None
        assert champ.model_id == "m1"

    def test_14_list_challengers(self):
        reg = ModelRegistry()
        reg.register_model("m1", "0.1.0", "/data/m1.pkl")
        reg.register_model("m2", "0.1.0", "/data/m2.pkl")
        reg.promote_to_challenger("m1", approved_by="op")
        challengers = reg.list_challengers()
        assert len(challengers) == 1
        assert challengers[0].model_id == "m1"

    def test_15_list_candidates(self):
        reg = ModelRegistry()
        reg.register_model("m1", "0.1.0", "/data/m1.pkl")
        reg.register_model("m2", "0.1.0", "/data/m2.pkl")
        candidates = reg.list_candidates()
        assert len(candidates) == 2


class TestPersistence:
    def test_16_save_registry_json(self, tmp_path):
        reg = ModelRegistry()
        reg.register_model("m1", "0.1.0", "/data/m1.pkl", metrics={"oos_sharpe": 1.5})
        reg.register_model("m2", "0.1.0", "/data/m2.pkl")
        reg.promote_to_challenger("m2", approved_by="op")
        out = reg.save_registry_json(tmp_path / "registry.json")
        assert Path(out["path"]).exists()
        with open(out["path"]) as f:
            data = json.load(f)
        assert data["model_count"] == 2
        assert data["safety"]["loads_pickle"] is False
        assert data["safety"]["loads_model_binaries"] is False
        assert data["safety"]["auto_promotes_champion"] is False
        assert data["safety"]["imports_metatrader5"] is False

    def test_17_load_registry_json(self, tmp_path):
        reg = ModelRegistry()
        reg.register_model("m1", "0.1.0", "/data/m1.pkl", metrics={"oos_sharpe": 1.5})
        reg.register_model("m2", "0.1.0", "/data/m2.pkl")
        reg.promote_to_challenger("m2", approved_by="op")
        path = tmp_path / "registry.json"
        reg.save_registry_json(path)
        # Load into a fresh registry
        reg2 = ModelRegistry()
        result = reg2.load_registry_json(path)
        assert result["model_count"] == 2
        assert reg2.get_model("m1") is not None
        assert reg2.get_model("m2") is not None
        assert reg2.get_model("m2").stage == ModelLifecycleStage.CHALLENGER
        assert reg2.get_model("m2").approved_by == "op"

    def test_18_load_nonexistent_raises(self, tmp_path):
        reg = ModelRegistry()
        with pytest.raises(FileNotFoundError):
            reg.load_registry_json(tmp_path / "nonexistent.json")


class TestSummary:
    def test_19_summary_returns_dict(self):
        reg = ModelRegistry()
        reg.register_model("m1", "0.1.0", "/data/m1.pkl")
        reg.register_model("m2", "0.1.0", "/data/m2.pkl")
        s = reg.summary()
        assert s["total_models"] == 2
        assert s["champion"] is None
        assert s["candidate_count"] == 2
        assert s["challenger_count"] == 0
        assert s["exactly_one_champion"] is False
        assert s["auto_promotion_allowed"] is False


class TestSafetyInvariants:
    def test_20_no_metatrader5_import(self):
        from titan.production import model_registry
        src = inspect.getsource(model_registry)
        assert "import MetaTrader5" not in src
        assert "from MetaTrader5" not in src

    def test_21_no_order_send_calls(self):
        import re
        from titan.production import model_registry
        src = inspect.getsource(model_registry)
        call_pattern = r"(?<!['\"#])\b(mt5\.order_send|adapter\.send_open_order|adapter\.send_order|send_close_order)\s*\("
        matches = re.findall(call_pattern, src)
        assert len(matches) == 0, f"Found execution calls: {matches}"

    def test_22_no_pickle_load(self):
        """Registry must never load pickle or model binaries."""
        from titan.production import model_registry
        src = inspect.getsource(model_registry)
        assert "pickle.load" not in src
        assert "joblib.load" not in src
        assert "torch.load" not in src
        # pickle.dump also forbidden - registry never writes binaries
        assert "pickle.dump" not in src

    def test_23_no_model_training_execution(self):
        from titan.production import model_registry
        src = inspect.getsource(model_registry)
        assert ".fit(" not in src
        assert "train_model(" not in src
        assert "retrain(" not in src

    def test_24_no_champion_replacement_artifact(self):
        """Registry must never copy/move/replace model artifacts on disk."""
        from titan.production import model_registry
        src = inspect.getsource(model_registry)
        assert "shutil.copy" not in src
        assert "shutil.move" not in src
        assert "os.replace" not in src
        assert "os.remove" not in src
