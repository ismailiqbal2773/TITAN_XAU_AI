"""TITAN XAU AI - Sprint v2.8.7-O Model Registry Compat Tests"""
from __future__ import annotations
import sys, inspect
from pathlib import Path
import pytest
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


class TestModelRegistryCompat:
    def test_model_registry_importable(self):
        from titan.production.model_registry import ModelRegistry, RegisteredModel
        assert ModelRegistry is not None
        assert RegisteredModel is not None

    def test_register_model(self):
        from titan.production.model_registry import ModelRegistry, ModelLifecycleStage
        reg = ModelRegistry()
        m = reg.register_model("m1", "0.1.0", "/data/m1.pkl")
        assert m.stage == ModelLifecycleStage.CANDIDATE

    def test_no_metatrader5_import(self):
        from titan.production import model_registry
        src = inspect.getsource(model_registry)
        assert "import MetaTrader5" not in src
        assert "from MetaTrader5" not in src

    def test_no_order_send(self):
        import re
        from titan.production import model_registry
        src = inspect.getsource(model_registry)
        stripped = re.sub(r'"""[\s\S]*?"""', '""', src)
        assert "order_send(" not in stripped

    def test_no_pickle_load(self):
        from titan.production import model_registry
        src = inspect.getsource(model_registry)
        assert "pickle.load" not in src

    def test_profile_functions_still_work(self):
        from titan.production.model_registry import get_profile, list_profiles, get_default_profile_name
        assert "v1_legacy" in list_profiles()
        assert get_default_profile_name() == "v1_legacy"
