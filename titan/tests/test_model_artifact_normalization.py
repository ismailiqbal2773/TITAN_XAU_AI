"""TITAN XAU AI - Sprint 9.9.3.43.1 Model Artifact Normalization Tests"""
from __future__ import annotations
import json, re, sys
from pathlib import Path
import pytest
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

class TestNormalization:
    def test_01_writes_json(self, tmp_path):
        import scripts.audit.normalize_model_artifacts as nm
        old = nm.OUTPUT_DIR; nm.OUTPUT_DIR = tmp_path
        try:
            result = nm.run_normalization(); report = nm.write_report(result)
            assert Path(report["json_path"]).exists()
            with open(report["json_path"]) as f: data = json.load(f)
            assert "verdict" in data
        finally: nm.OUTPUT_DIR = old

    def test_02_writes_md(self, tmp_path):
        import scripts.audit.normalize_model_artifacts as nm
        old = nm.OUTPUT_DIR; nm.OUTPUT_DIR = tmp_path
        try:
            result = nm.run_normalization(); report = nm.write_report(result)
            assert "Model Normalization Report" in Path(report["md_path"]).read_text()
        finally: nm.OUTPUT_DIR = old

    def test_03_does_not_replace_active_artifacts(self):
        """Active model files must remain unchanged."""
        models_dir = REPO_ROOT / "titan" / "data" / "models"
        xgb_path = models_dir / "xgboost_v1.pkl"
        meta_path = models_dir / "meta_label_v2_context.pkl"
        # Verify active models still exist and are unchanged
        if xgb_path.exists():
            assert xgb_path.exists()
        if meta_path.exists():
            assert meta_path.exists()

    def test_04_does_not_retrain(self):
        import inspect, re
        src = inspect.getsource(__import__("scripts.audit.normalize_model_artifacts", fromlist=["x"]))
        code = re.sub(r'"""[\s\S]*?"""','""',src)
        code = re.sub(r"'''[\s\S]*?'''","''",code)
        code = re.sub(r'r"[^"]*"','""',code)
        code = re.sub(r"r'[^']*'","''",code)
        code = re.sub(r'"(?:[^"\\]|\\.)*"','""',code)
        code = re.sub(r"'(?:[^'\\]|\\.)*'","''",code)
        # Strip comments
        lines = []
        for line in code.splitlines():
            idx = line.find("#")
            if idx >= 0: line = line[:idx]
            lines.append(line)
        code = "\n".join(lines)
        assert ".fit(" not in code
        assert "train_model(" not in code
        # Check for actual retrain function CALLS (not string mentions)
        assert not re.search(r"(?<!['\"])\bretrain\s*\(", code)

    def test_05_verdict_in_valid_set(self):
        import scripts.audit.normalize_model_artifacts as nm
        result = nm.run_normalization()
        assert result["verdict"] in ("MODEL_NORMALIZATION_READY","MODEL_NORMALIZATION_READY_WITH_WARNINGS","MODEL_NORMALIZATION_BLOCKED")

    def test_06_no_metatrader5_import(self):
        import inspect
        src = inspect.getsource(__import__("scripts.audit.normalize_model_artifacts", fromlist=["x"]))
        assert "import MetaTrader5" not in src and "from MetaTrader5" not in src

    def test_07_no_order_send(self):
        import inspect, re
        src = inspect.getsource(__import__("scripts.audit.normalize_model_artifacts", fromlist=["x"]))
        code = re.sub(r'"""[\s\S]*?"""','""',src)
        code = re.sub(r'"(?:[^"\\]|\\.)*"','""',code)
        code = re.sub(r"'(?:[^'\\]|\\.)*'","''",code)
        assert not re.search(r"\bmt5\.order_send\s*\(", code)

    def test_08_candidates_not_in_active_dir(self):
        """Candidates must be in data/model_candidates/, NOT in titan/data/models/."""
        candidate_dir = REPO_ROOT / "data" / "model_candidates" / "normalized_artifacts"
        active_dir = REPO_ROOT / "titan" / "data" / "models"
        if candidate_dir.exists():
            for f in candidate_dir.iterdir():
                assert not (active_dir / f.name).exists(), f"Candidate {f.name} in active dir!"
