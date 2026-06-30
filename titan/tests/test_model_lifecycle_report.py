"""TITAN XAU AI - Sprint 9.9.3.36 Model Lifecycle Report Tests"""
from __future__ import annotations
import inspect, json, sys
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


class TestReportWriter:
    def test_01_json_report_writes(self, tmp_path):
        import scripts.audit.model_lifecycle_report as rep
        old_dir, old_json, old_md = rep.OUTPUT_DIR, rep.JSON_PATH, rep.MD_PATH
        rep.OUTPUT_DIR = tmp_path
        rep.JSON_PATH = tmp_path / "report.json"
        rep.MD_PATH = tmp_path / "report.md"
        try:
            result = rep.write_report()
            assert Path(result["json_path"]).exists()
            with open(result["json_path"]) as f:
                data = json.load(f)
            assert "verdict" in data
            assert "champion" in data
            assert "candidates" in data
            assert "challengers" in data
            assert "calibration_governance" in data
            assert "alpha_factory_governance" in data
            assert "lifecycle_governance" in data
            assert "blocked_promotions" in data
            assert "manual_approval_required" in data
            assert "safety" in data
            assert "general_warnings" in data
        finally:
            rep.OUTPUT_DIR, rep.JSON_PATH, rep.MD_PATH = old_dir, old_json, old_md

    def test_02_md_report_writes(self, tmp_path):
        import scripts.audit.model_lifecycle_report as rep
        old_dir, old_json, old_md = rep.OUTPUT_DIR, rep.JSON_PATH, rep.MD_PATH
        rep.OUTPUT_DIR = tmp_path
        rep.JSON_PATH = tmp_path / "report.json"
        rep.MD_PATH = tmp_path / "report.md"
        try:
            result = rep.write_report()
            md = Path(result["md_path"]).read_text(encoding="utf-8")
            assert "Model Lifecycle Report" in md
            assert "Champion" in md
            assert "Candidates" in md
            assert "Calibration Governance" in md
            assert "Alpha Factory Governance" in md
            assert "Lifecycle Governance" in md
            assert "Safety" in md
        finally:
            rep.OUTPUT_DIR, rep.JSON_PATH, rep.MD_PATH = old_dir, old_json, old_md

    def test_03_verdict_in_valid_set(self, tmp_path):
        import scripts.audit.model_lifecycle_report as rep
        old_dir, old_json, old_md = rep.OUTPUT_DIR, rep.JSON_PATH, rep.MD_PATH
        rep.OUTPUT_DIR = tmp_path
        rep.JSON_PATH = tmp_path / "report.json"
        rep.MD_PATH = tmp_path / "report.md"
        try:
            result = rep.write_report()
            assert result["verdict"] in (
                "MODEL_LIFECYCLE_READY",
                "MODEL_LIFECYCLE_WARNINGS",
                "MODEL_LIFECYCLE_BLOCKED",
            )
        finally:
            rep.OUTPUT_DIR, rep.JSON_PATH, rep.MD_PATH = old_dir, old_json, old_md

    def test_04_report_with_champion(self, tmp_path):
        """Report should include champion metadata when a champion is registered."""
        from titan.production.model_registry import ModelRegistry
        import scripts.audit.model_lifecycle_report as rep
        reg = ModelRegistry()
        reg.register_model("m1", "0.1.0", "/data/m1.pkl", metrics={"oos_sharpe": 1.5})
        reg.promote_to_challenger("m1", approved_by="op")
        reg.require_manual_champion_promotion(
            "m1", approved_by="op", manual_approval_flag=True
        )
        old_dir, old_json, old_md = rep.OUTPUT_DIR, rep.JSON_PATH, rep.MD_PATH
        rep.OUTPUT_DIR = tmp_path
        rep.JSON_PATH = tmp_path / "report.json"
        rep.MD_PATH = tmp_path / "report.md"
        try:
            result = rep.write_report(registry=reg)
            with open(result["json_path"]) as f:
                data = json.load(f)
            assert data["champion"] is not None
            assert data["champion"]["model_id"] == "m1"
        finally:
            rep.OUTPUT_DIR, rep.JSON_PATH, rep.MD_PATH = old_dir, old_json, old_md

    def test_05_report_with_sample_calibration(self, tmp_path):
        """Report should reflect calibration governance evaluation."""
        import scripts.audit.model_lifecycle_report as rep
        old_dir, old_json, old_md = rep.OUTPUT_DIR, rep.JSON_PATH, rep.MD_PATH
        rep.OUTPUT_DIR = tmp_path
        rep.JSON_PATH = tmp_path / "report.json"
        rep.MD_PATH = tmp_path / "report.md"
        try:
            result = rep.write_report(sample_calibration_metrics={
                "sample_count": 1000,
                "brier_score": 0.15,
                "expected_calibration_error": 0.05,
                "current_threshold": 0.5,
            })
            with open(result["json_path"]) as f:
                data = json.load(f)
            cal = data["calibration_governance"]
            assert cal["apply_automatically"] is False
            assert cal["action"] in (
                "KEEP_CURRENT", "NEEDS_REVIEW", "BLOCK_CALIBRATION",
                "RECOMMEND_THRESHOLD_ADJUSTMENT", "RECOMMEND_PROBABILITY_RECALIBRATION",
            )
        finally:
            rep.OUTPUT_DIR, rep.JSON_PATH, rep.MD_PATH = old_dir, old_json, old_md

    def test_06_report_blocked_when_insufficient_samples(self, tmp_path):
        """Report should be BLOCKED when calibration samples are insufficient."""
        import scripts.audit.model_lifecycle_report as rep
        old_dir, old_json, old_md = rep.OUTPUT_DIR, rep.JSON_PATH, rep.MD_PATH
        rep.OUTPUT_DIR = tmp_path
        rep.JSON_PATH = tmp_path / "report.json"
        rep.MD_PATH = tmp_path / "report.md"
        try:
            result = rep.write_report(sample_calibration_metrics={
                "sample_count": 10,  # way below minimum
                "brier_score": 0.15,
                "expected_calibration_error": 0.05,
                "current_threshold": 0.5,
            })
            with open(result["json_path"]) as f:
                data = json.load(f)
            assert data["verdict"] == "MODEL_LIFECYCLE_BLOCKED"
        finally:
            rep.OUTPUT_DIR, rep.JSON_PATH, rep.MD_PATH = old_dir, old_json, old_md

    def test_07_safety_invariants_in_report(self, tmp_path):
        import scripts.audit.model_lifecycle_report as rep
        old_dir, old_json, old_md = rep.OUTPUT_DIR, rep.JSON_PATH, rep.MD_PATH
        rep.OUTPUT_DIR = tmp_path
        rep.JSON_PATH = tmp_path / "report.json"
        rep.MD_PATH = tmp_path / "report.md"
        try:
            result = rep.write_report()
            with open(result["json_path"]) as f:
                data = json.load(f)
            safety = data["safety"]
            assert safety["auto_promotion_allowed"] is False
            assert safety["calibration_auto_apply"] is False
            assert safety["metatrader5_imported"] is False
            assert safety["orders_sent"] == 0
            assert safety["models_retrained"] == 0
            assert safety["champion_replaced"] is False
            assert safety["live_trading_enabled"] is False
        finally:
            rep.OUTPUT_DIR, rep.JSON_PATH, rep.MD_PATH = old_dir, old_json, old_md


class TestSafetyInvariants:
    def test_08_no_metatrader5_import_in_report_writer(self):
        import scripts.audit.model_lifecycle_report as rep
        src = inspect.getsource(rep)
        assert "import MetaTrader5" not in src
        assert "from MetaTrader5" not in src

    def test_09_no_order_send_in_report_writer(self):
        import re
        import scripts.audit.model_lifecycle_report as rep
        src = inspect.getsource(rep)
        call_pattern = r"(?<!['\"#])\b(mt5\.order_send|adapter\.send_open_order|adapter\.send_order|send_close_order)\s*\("
        matches = re.findall(call_pattern, src)
        assert len(matches) == 0, f"Found execution calls: {matches}"

    def test_10_no_model_training_in_report_writer(self):
        import scripts.audit.model_lifecycle_report as rep
        src = inspect.getsource(rep)
        assert ".fit(" not in src
        assert "train_model(" not in src
        assert "retrain(" not in src
        assert "run_hpo(" not in src

    def test_11_no_champion_replacement_in_report_writer(self):
        import scripts.audit.model_lifecycle_report as rep
        src = inspect.getsource(rep)
        assert "shutil.copy" not in src
        assert "shutil.move" not in src
        assert "os.replace" not in src
        # Should not call any model registry promotion method
        assert "require_manual_champion_promotion" not in src

    def test_12_no_pickle_operations(self):
        import scripts.audit.model_lifecycle_report as rep
        src = inspect.getsource(rep)
        assert "pickle.load" not in src
        assert "pickle.dump" not in src
        assert "joblib.load" not in src
