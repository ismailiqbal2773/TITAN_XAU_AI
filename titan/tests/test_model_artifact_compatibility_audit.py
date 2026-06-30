"""TITAN XAU AI - Sprint 9.9.3.43 Model Artifact Compatibility Audit Tests"""
from __future__ import annotations
import inspect, json, re, sys
from pathlib import Path
import pytest
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

class TestModelArtifactAudit:
    def test_01_json_writes(self, tmp_path):
        import scripts.audit.model_artifact_compatibility_audit as ma
        old_d, old_j, old_m = ma.OUTPUT_DIR, ma.JSON_PATH, ma.MD_PATH
        ma.OUTPUT_DIR = tmp_path; ma.JSON_PATH = tmp_path / "ma.json"; ma.MD_PATH = tmp_path / "ma.md"
        try:
            result = ma.run_audit(); report = ma.write_report(result)
            assert Path(report["json_path"]).exists()
            with open(report["json_path"]) as f: data = json.load(f)
            assert "verdict" in data and "model_info" in data
        finally: ma.OUTPUT_DIR, ma.JSON_PATH, ma.MD_PATH = old_d, old_j, old_m

    def test_02_md_writes(self, tmp_path):
        import scripts.audit.model_artifact_compatibility_audit as ma
        old_d, old_j, old_m = ma.OUTPUT_DIR, ma.JSON_PATH, ma.MD_PATH
        ma.OUTPUT_DIR = tmp_path; ma.JSON_PATH = tmp_path / "ma.json"; ma.MD_PATH = tmp_path / "ma.md"
        try:
            result = ma.run_audit(); report = ma.write_report(result)
            assert "Model Artifact Compatibility Audit" in Path(report["md_path"]).read_text()
        finally: ma.OUTPUT_DIR, ma.JSON_PATH, ma.MD_PATH = old_d, old_j, old_m

    def test_03_verdict_in_valid_set(self):
        import scripts.audit.model_artifact_compatibility_audit as ma
        result = ma.run_audit()
        assert result["verdict"] in ("MODEL_ARTIFACT_READY","MODEL_ARTIFACT_READY_WITH_WARNINGS","MODEL_ARTIFACT_BLOCKED")

    def test_04_no_metatrader5_import(self):
        src = inspect.getsource(__import__("scripts.audit.model_artifact_compatibility_audit", fromlist=["x"]))
        assert "import MetaTrader5" not in src and "from MetaTrader5" not in src

    def test_05_no_order_send(self):
        import re; src = inspect.getsource(__import__("scripts.audit.model_artifact_compatibility_audit", fromlist=["x"]))
        code = re.sub(r'"""[\s\S]*?"""','""',src); code = re.sub(r'"(?:[^"\\]|\\.)*"','""',code); code = re.sub(r"'(?:[^'\\]|\\.)*'","''",code)
        assert not re.search(r"\bmt5\.order_send\s*\(", code)

    def test_06_inference_passed(self):
        import scripts.audit.model_artifact_compatibility_audit as ma
        result = ma.run_audit()
        # Inference should pass if models are loadable
        if not result["blockers"]:
            assert result["inference_passed"] is True
