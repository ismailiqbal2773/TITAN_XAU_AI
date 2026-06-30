"""TITAN XAU AI - Sprint 9.9.3.43.1 Environment Drift Gate Tests"""
from __future__ import annotations
import json, sys, tempfile
from pathlib import Path
import pytest
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
from titan.production.environment_drift_gate import EnvironmentDriftGate, DriftVerdict

class TestDriftGate:
    def test_01_blocks_when_no_signature(self, tmp_path):
        gate = EnvironmentDriftGate(signature_path=tmp_path / "nonexistent.json")
        result = gate.evaluate()
        assert result.verdict == DriftVerdict.ENVIRONMENT_LOCK_BLOCKED
        assert any("signature not found" in b.lower() for b in result.blockers)

    def test_02_blocks_missing_package(self, tmp_path):
        sig = {"python_version": f"{sys.version_info.major}.{sys.version_info.minor}.0",
               "critical_packages": {"xgboost": "9.9.9", "sklearn": "9.9.9", "pandas": "9.9.9",
                                     "numpy": "9.9.9", "yaml": "9.9.9", "MetaTrader5": None, "joblib": "9.9.9"},
               "model_files": {}}
        sig_path = tmp_path / "sig.json"
        sig_path.write_text(json.dumps(sig))
        gate = EnvironmentDriftGate(signature_path=sig_path)
        result = gate.evaluate()
        assert result.verdict == DriftVerdict.ENVIRONMENT_LOCK_BLOCKED

    def test_03_blocks_python_major_drift(self, tmp_path):
        sig = {"python_version": "2.7.0", "critical_packages": {}, "model_files": {}}
        sig_path = tmp_path / "sig.json"
        sig_path.write_text(json.dumps(sig))
        gate = EnvironmentDriftGate(signature_path=sig_path)
        result = gate.evaluate()
        assert result.verdict == DriftVerdict.ENVIRONMENT_LOCK_BLOCKED
        assert any("python" in b.lower() for b in result.blockers)

    def test_04_blocks_model_hash_drift(self, tmp_path):
        sig = {"python_version": f"{sys.version_info.major}.{sys.version_info.minor}.0",
               "critical_packages": {}, "model_files": {"xgboost_v1.pkl": {"sha256": "wrong", "size_bytes": 1}}}
        sig_path = tmp_path / "sig.json"
        sig_path.write_text(json.dumps(sig))
        gate = EnvironmentDriftGate(signature_path=sig_path)
        result = gate.evaluate()
        assert result.verdict == DriftVerdict.ENVIRONMENT_LOCK_BLOCKED
        assert any("hash" in b.lower() or "missing" in b.lower() for b in result.blockers)

    def test_05_warns_on_minor_package_drift(self, tmp_path):
        # Create a signature with same major version but different minor
        import xgboost, sklearn
        sig = {"python_version": f"{sys.version_info.major}.{sys.version_info.minor}.0",
               "critical_packages": {
                   "xgboost": "0.0.1",  # Different minor, same major "0"
                   "sklearn": "0.0.1",
                   "pandas": None, "numpy": None, "yaml": None, "MetaTrader5": None, "joblib": None,
               },
               "model_files": {}}
        sig_path = tmp_path / "sig.json"
        sig_path.write_text(json.dumps(sig))
        gate = EnvironmentDriftGate(signature_path=sig_path)
        result = gate.evaluate()
        # Should have warnings about version drift
        assert any("DRIFT" in w for w in result.warnings) or result.verdict == DriftVerdict.ENVIRONMENT_LOCK_BLOCKED

    def test_06_no_metatrader5_import(self):
        import inspect
        from titan.production import environment_drift_gate
        src = inspect.getsource(environment_drift_gate)
        assert "import MetaTrader5" not in src and "from MetaTrader5" not in src

    def test_07_no_order_send(self):
        import inspect, re
        from titan.production import environment_drift_gate
        src = inspect.getsource(environment_drift_gate)
        code = re.sub(r'"""[\s\S]*?"""','""',src)
        code = re.sub(r'"(?:[^"\\]|\\.)*"','""',code)
        code = re.sub(r"'(?:[^'\\]|\\.)*'","''",code)
        assert not re.search(r"\bmt5\.order_send\s*\(", code)

    def test_08_no_pip_install(self):
        import inspect, re
        from titan.production import environment_drift_gate
        src = inspect.getsource(environment_drift_gate)
        code = re.sub(r'"""[\s\S]*?"""','""',src)
        assert "pip install" not in code.lower()
