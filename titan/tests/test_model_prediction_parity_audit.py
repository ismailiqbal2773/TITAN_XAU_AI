"""TITAN XAU AI - Sprint 9.9.3.43.1 Model Prediction Parity Audit Tests"""
from __future__ import annotations
import json, re, sys
from pathlib import Path
import pytest
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

class TestParityAudit:
    def test_01_writes_json(self, tmp_path):
        import scripts.audit.model_prediction_parity_audit as pa
        old = pa.OUTPUT_DIR; pa.OUTPUT_DIR = tmp_path
        try:
            result = pa.run_parity_audit(); report = pa.write_report(result)
            assert Path(report["json_path"]).exists()
            with open(report["json_path"]) as f: data = json.load(f)
            assert "verdict" in data and "xgboost_parity" in data
        finally: pa.OUTPUT_DIR = old

    def test_02_writes_md(self, tmp_path):
        import scripts.audit.model_prediction_parity_audit as pa
        old = pa.OUTPUT_DIR; pa.OUTPUT_DIR = tmp_path
        try:
            result = pa.run_parity_audit(); report = pa.write_report(result)
            assert "Prediction Parity Audit" in Path(report["md_path"]).read_text()
        finally: pa.OUTPUT_DIR = old

    def test_03_verdict_in_valid_set(self):
        import scripts.audit.model_prediction_parity_audit as pa
        result = pa.run_parity_audit()
        assert result["verdict"] in ("MODEL_PARITY_PASS","MODEL_PARITY_PASS_WITH_WARNINGS","MODEL_PARITY_FAIL","MODEL_PARITY_NOT_AVAILABLE")

    def test_04_not_available_when_no_candidates(self):
        """If no candidates exist, verdict should be NOT_AVAILABLE (not FAIL)."""
        import scripts.audit.model_prediction_parity_audit as pa
        result = pa.run_parity_audit()
        # If candidates don't exist, parity should be NOT_AVAILABLE
        if not (REPO_ROOT / "data" / "model_candidates" / "normalized_artifacts").exists():
            assert result["verdict"] == "MODEL_PARITY_NOT_AVAILABLE"

    def test_05_no_metatrader5_import(self):
        import inspect
        src = inspect.getsource(__import__("scripts.audit.model_prediction_parity_audit", fromlist=["x"]))
        assert "import MetaTrader5" not in src and "from MetaTrader5" not in src

    def test_06_no_order_send(self):
        import inspect, re
        src = inspect.getsource(__import__("scripts.audit.model_prediction_parity_audit", fromlist=["x"]))
        code = re.sub(r'"""[\s\S]*?"""','""',src)
        code = re.sub(r'"(?:[^"\\]|\\.)*"','""',code)
        code = re.sub(r"'(?:[^'\\]|\\.)*'","''",code)
        assert not re.search(r"\bmt5\.order_send\s*\(", code)

    def test_07_no_retraining(self):
        import inspect
        src = inspect.getsource(__import__("scripts.audit.model_prediction_parity_audit", fromlist=["x"]))
        code = re.sub(r'"""[\s\S]*?"""','""',src)
        assert ".fit(" not in code and "retrain" not in code
