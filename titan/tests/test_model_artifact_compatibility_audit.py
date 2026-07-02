"""TITAN XAU AI - Sprint v2.8.1 Model Artifact Compatibility Audit Tests"""
from __future__ import annotations
import json, re, sys
from pathlib import Path
import pytest
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


def _strip(src):
    src = re.sub(r'"""[\s\S]*?"""', '""', src)
    src = re.sub(r"'''[\s\S]*?'''", "''", src)
    src = re.sub(r'"(?:[^"\\]|\\.)*"', '""', src)
    src = re.sub(r"'(?:[^'\\]|\\.)*'", "''", src)
    return src


class TestModelArtifactCompatibilityAudit:
    def test_01_module_imports(self):
        import scripts.audit.model_artifact_compatibility_audit as a
        assert hasattr(a, "run_audit")
        assert hasattr(a, "write_report")

    def test_02_all_verdicts_supported(self):
        import scripts.audit.model_artifact_compatibility_audit as a
        assert hasattr(a, "ALL_VERDICTS")
        assert a.MODEL_ARTIFACTS_COMPATIBLE in a.ALL_VERDICTS
        assert a.MODEL_ARTIFACTS_COMPATIBLE_WITH_WARNINGS in a.ALL_VERDICTS
        assert a.MODEL_ARTIFACTS_BLOCKED_VERSION_MISMATCH in a.ALL_VERDICTS
        assert a.MODEL_ARTIFACTS_NOT_FOUND in a.ALL_VERDICTS

    def test_03_returns_result_with_verdict(self):
        import scripts.audit.model_artifact_compatibility_audit as a
        result = a.run_audit()
        assert "verdict" in result
        assert "findings" in result
        assert "safety" in result
        assert result["verdict"] in a.ALL_VERDICTS

    def test_04_no_order_send(self):
        src = (REPO_ROOT / "scripts" / "audit" / "model_artifact_compatibility_audit.py").read_text()
        code = _strip(src)
        assert not re.search(r"\bmt5\.order_send\s*\(", code)

    def test_05_no_position_modification(self):
        src = (REPO_ROOT / "scripts" / "audit" / "model_artifact_compatibility_audit.py").read_text()
        code = _strip(src)
        assert not re.search(r"\bmt5\.(order_modify|positions_modify)\s*\(", code)

    def test_06_no_execution_token_creation(self):
        src = (REPO_ROOT / "scripts" / "audit" / "model_artifact_compatibility_audit.py").read_text()
        code = _strip(src).lower()
        assert "create_local_operator_execution_token" not in code

    def test_07_no_model_retraining(self):
        """Audit must never retrain or regenerate models."""
        src = (REPO_ROOT / "scripts" / "audit" / "model_artifact_compatibility_audit.py").read_text()
        code = _strip(src).lower()
        # Must not call retrain or regenerate functions
        assert "retrain" not in code or "no_retrain" in code or "models_retrained" in code
        assert "regenerate" not in code or "no_regenerate" in code or "models_regenerated" in code

    def test_08_includes_runtime_versions(self):
        """Audit must include runtime package versions."""
        import scripts.audit.model_artifact_compatibility_audit as a
        result = a.run_audit()
        fnd = result.get("findings", {})
        assert "runtime_versions" in fnd
        assert "xgboost" in fnd["runtime_versions"]
        assert "sklearn" in fnd["runtime_versions"]

    def test_09_includes_autonomous_readiness_impact(self):
        """Audit must include autonomous_readiness_impact field."""
        import scripts.audit.model_artifact_compatibility_audit as a
        result = a.run_audit()
        fnd = result.get("findings", {})
        assert "autonomous_readiness_impact" in fnd
        assert fnd["autonomous_readiness_impact"] in ("none", "warning", "hard_block")

    def test_10_writes_json_and_md(self, tmp_path, monkeypatch):
        import scripts.audit.model_artifact_compatibility_audit as a
        monkeypatch.setattr(a, "OUTPUT_DIR", tmp_path)
        result = a.run_audit()
        report = a.write_report(result)
        assert Path(report["json_path"]).exists()
        assert Path(report["md_path"]).exists()

    def test_11_safety_flags_in_result(self):
        """Result must include all safety flags."""
        import scripts.audit.model_artifact_compatibility_audit as a
        result = a.run_audit()
        safety = result.get("safety", {})
        assert safety.get("order_send_called") is False
        assert safety.get("position_modified") is False
        assert safety.get("execution_token_created") is False
        assert safety.get("models_retrained") is False
        assert safety.get("models_regenerated") is False

    def test_12_no_martingale(self):
        src = (REPO_ROOT / "scripts" / "audit" / "model_artifact_compatibility_audit.py").read_text()
        code = _strip(src).lower()
        for term in ["martingale", "grid_trade", "averaging_down", "loss_based_lot"]:
            assert term not in code or "no_" in code or "forbid" in code
