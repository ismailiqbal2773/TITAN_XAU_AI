"""TITAN XAU AI - Sprint 9.9.3.37 Offline Retraining Report Tests"""
from __future__ import annotations
import inspect, json, sys
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


class TestReportWriter:
    def test_01_json_report_writes(self, tmp_path):
        import scripts.audit.offline_retraining_report as rep
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
            assert "trigger_monitor" in data
            assert "pipeline" in data
            assert "retraining_job_readiness" in data
            assert "candidate_registration_status" in data
            assert "champion_replacement_status" in data
            assert "training_execution_status" in data
            assert "blockers" in data
            assert "warnings" in data
            assert "safety" in data
            assert "general_warnings" in data
        finally:
            rep.OUTPUT_DIR, rep.JSON_PATH, rep.MD_PATH = old_dir, old_json, old_md

    def test_02_md_report_writes(self, tmp_path):
        import scripts.audit.offline_retraining_report as rep
        old_dir, old_json, old_md = rep.OUTPUT_DIR, rep.JSON_PATH, rep.MD_PATH
        rep.OUTPUT_DIR = tmp_path
        rep.JSON_PATH = tmp_path / "report.json"
        rep.MD_PATH = tmp_path / "report.md"
        try:
            result = rep.write_report()
            md = Path(result["md_path"]).read_text(encoding="utf-8")
            assert "Offline Retraining Report" in md
            assert "Trigger Monitor" in md
            assert "Pipeline" in md
            assert "Retraining Job Readiness" in md
            assert "Candidate Registration Status" in md
            assert "Champion Replacement Status" in md
            assert "Training Execution Status" in md
            assert "Safety" in md
        finally:
            rep.OUTPUT_DIR, rep.JSON_PATH, rep.MD_PATH = old_dir, old_json, old_md

    def test_03_verdict_in_valid_set(self, tmp_path):
        import scripts.audit.offline_retraining_report as rep
        old_dir, old_json, old_md = rep.OUTPUT_DIR, rep.JSON_PATH, rep.MD_PATH
        rep.OUTPUT_DIR = tmp_path
        rep.JSON_PATH = tmp_path / "report.json"
        rep.MD_PATH = tmp_path / "report.md"
        try:
            result = rep.write_report()
            assert result["verdict"] in (
                "RETRAINING_PIPELINE_READY",
                "RETRAINING_PIPELINE_WARNINGS",
                "RETRAINING_PIPELINE_BLOCKED",
            )
        finally:
            rep.OUTPUT_DIR, rep.JSON_PATH, rep.MD_PATH = old_dir, old_json, old_md

    def test_04_report_with_empty_metrics(self, tmp_path):
        """Report with empty metrics should produce INSUFFICIENT_DATA warnings."""
        import scripts.audit.offline_retraining_report as rep
        old_dir, old_json, old_md = rep.OUTPUT_DIR, rep.JSON_PATH, rep.MD_PATH
        rep.OUTPUT_DIR = tmp_path
        rep.JSON_PATH = tmp_path / "report.json"
        rep.MD_PATH = tmp_path / "report.md"
        try:
            result = rep.write_report(sample_runtime_metrics={})
            with open(result["json_path"]) as f:
                data = json.load(f)
            # With empty metrics, all signals should be INSUFFICIENT_DATA
            tm = data["trigger_monitor"]
            assert tm["performance_decay"]["recommended"] == "INSUFFICIENT_DATA"
            assert tm["calibration_drift"]["recommended"] == "INSUFFICIENT_DATA"
            assert tm["regime_shift"]["recommended"] == "INSUFFICIENT_DATA"
            assert tm["broker_degradation"]["recommended"] == "INSUFFICIENT_DATA"
            assert tm["aggregate_recommendation"]["recommended"] == "INSUFFICIENT_DATA"
        finally:
            rep.OUTPUT_DIR, rep.JSON_PATH, rep.MD_PATH = old_dir, old_json, old_md

    def test_05_report_with_full_metrics(self, tmp_path):
        """Report with full metrics should produce NEEDS_REVIEW at most."""
        import scripts.audit.offline_retraining_report as rep
        old_dir, old_json, old_md = rep.OUTPUT_DIR, rep.JSON_PATH, rep.MD_PATH
        rep.OUTPUT_DIR = tmp_path
        rep.JSON_PATH = tmp_path / "report.json"
        rep.MD_PATH = tmp_path / "report.md"
        try:
            result = rep.write_report(sample_runtime_metrics={
                "current_sharpe": 1.0,
                "baseline_sharpe": 2.0,
                "current_brier": 0.30,
                "baseline_brier": 0.15,
                "regime_shift_confidence": 0.85,
                "current_winrate": 0.50,
                "baseline_winrate": 0.65,
                "days_since_last_retraining": 100,
                "schedule_interval_days": 90,
                "sample_count": 200,
            })
            with open(result["json_path"]) as f:
                data = json.load(f)
            # With critical signals, aggregate should be NEEDS_REVIEW (capped)
            tm = data["trigger_monitor"]
            assert tm["aggregate_recommendation"]["recommended"] == "NEEDS_REVIEW"
        finally:
            rep.OUTPUT_DIR, rep.JSON_PATH, rep.MD_PATH = old_dir, old_json, old_md

    def test_06_safety_invariants_in_report(self, tmp_path):
        import scripts.audit.offline_retraining_report as rep
        old_dir, old_json, old_md = rep.OUTPUT_DIR, rep.JSON_PATH, rep.MD_PATH
        rep.OUTPUT_DIR = tmp_path
        rep.JSON_PATH = tmp_path / "report.json"
        rep.MD_PATH = tmp_path / "report.md"
        try:
            result = rep.write_report()
            with open(result["json_path"]) as f:
                data = json.load(f)
            safety = data["safety"]
            assert safety["metatrader5_imported"] is False
            assert safety["orders_sent"] == 0
            assert safety["live_runtime_config_changed"] is False
            assert safety["live_trading_enabled"] is False
            assert safety["champion_replaced"] is False
            assert safety["training_executed"] is False
            assert safety["model_artifacts_created"] == 0
        finally:
            rep.OUTPUT_DIR, rep.JSON_PATH, rep.MD_PATH = old_dir, old_json, old_md

    def test_07_champion_replacement_status_always_false(self, tmp_path):
        import scripts.audit.offline_retraining_report as rep
        old_dir, old_json, old_md = rep.OUTPUT_DIR, rep.JSON_PATH, rep.MD_PATH
        rep.OUTPUT_DIR = tmp_path
        rep.JSON_PATH = tmp_path / "report.json"
        rep.MD_PATH = tmp_path / "report.md"
        try:
            result = rep.write_report()
            with open(result["json_path"]) as f:
                data = json.load(f)
            assert data["champion_replacement_status"]["champion_replaced"] is False
            assert data["champion_replacement_status"]["auto_promotion_allowed"] is False
            assert data["champion_replacement_status"]["manual_approval_required"] is True
        finally:
            rep.OUTPUT_DIR, rep.JSON_PATH, rep.MD_PATH = old_dir, old_json, old_md

    def test_08_training_execution_status_always_false(self, tmp_path):
        import scripts.audit.offline_retraining_report as rep
        old_dir, old_json, old_md = rep.OUTPUT_DIR, rep.JSON_PATH, rep.MD_PATH
        rep.OUTPUT_DIR = tmp_path
        rep.JSON_PATH = tmp_path / "report.json"
        rep.MD_PATH = tmp_path / "report.md"
        try:
            result = rep.write_report()
            with open(result["json_path"]) as f:
                data = json.load(f)
            tes = data["training_execution_status"]
            assert tes["training_executed"] is False
            assert tes["hpo_executed"] is False
            assert tes["backtest_optimization_executed"] is False
            assert tes["model_artifacts_created"] == 0
        finally:
            rep.OUTPUT_DIR, rep.JSON_PATH, rep.MD_PATH = old_dir, old_json, old_md


class TestSafetyInvariants:
    def _strip_docstrings(self, src: str) -> str:
        """Remove docstrings AND string literals to check actual code only."""
        import re
        # Remove triple-quoted strings (both """ and ''')
        src = re.sub(r'"""[\s\S]*?"""', '""', src)
        src = re.sub(r"'''[\s\S]*?'''", "''", src)
        # Remove single-line double-quoted strings (handles escaped quotes)
        src = re.sub(r'"(?:[^"\\]|\\.)*"', '""', src)
        # Remove single-line single-quoted strings
        src = re.sub(r"'(?:[^'\\]|\\.)*'", "''", src)
        # Remove single-line comments
        lines = []
        for line in src.splitlines():
            in_str = False
            quote_char = None
            result = []
            i = 0
            while i < len(line):
                c = line[i]
                if in_str:
                    if c == quote_char and (i == 0 or line[i-1] != '\\'):
                        in_str = False
                        quote_char = None
                    result.append(c)
                else:
                    if c in ('"', "'"):
                        in_str = True
                        quote_char = c
                        result.append(c)
                    elif c == '#':
                        break
                    else:
                        result.append(c)
                i += 1
            lines.append(''.join(result))
        return '\n'.join(lines)

    def test_09_no_metatrader5_import_in_report_writer(self):
        import scripts.audit.offline_retraining_report as rep
        src = inspect.getsource(rep)
        assert "import MetaTrader5" not in src
        assert "from MetaTrader5" not in src

    def test_10_no_order_send_in_report_writer(self):
        import re
        import scripts.audit.offline_retraining_report as rep
        src = self._strip_docstrings(inspect.getsource(rep))
        call_pattern = r"\b(mt5\.order_send|adapter\.send_open_order|adapter\.send_order|send_close_order)\s*\("
        matches = re.findall(call_pattern, src)
        assert len(matches) == 0, f"Found execution calls: {matches}"

    def test_11_no_model_training_in_report_writer(self):
        import re
        import scripts.audit.offline_retraining_report as rep
        src = self._strip_docstrings(inspect.getsource(rep))
        call_pattern = r"\b(\w+\.fit|train_model|retrain|run_hpo)\s*\("
        matches = re.findall(call_pattern, src)
        assert len(matches) == 0, f"Found training calls: {matches}"

    def test_12_no_champion_replacement_in_report_writer(self):
        import re
        import scripts.audit.offline_retraining_report as rep
        src = self._strip_docstrings(inspect.getsource(rep))
        call_pattern = r"\b(require_manual_champion_promotion|promote_to_challenger)\s*\("
        matches = re.findall(call_pattern, src)
        assert len(matches) == 0, f"Found champion promotion calls: {matches}"
        assert "shutil.copy" not in src
        assert "shutil.move" not in src

    def test_13_no_runtime_config_modification_in_report_writer(self):
        import scripts.audit.offline_retraining_report as rep
        src = inspect.getsource(rep)
        assert "runtime.yaml" not in src
        assert "config/runtime" not in src

    def test_14_no_pickle_operations(self):
        import re
        import scripts.audit.offline_retraining_report as rep
        src = self._strip_docstrings(inspect.getsource(rep))
        assert "import pickle" not in src
        assert "import joblib" not in src
        assert "import torch" not in src
        call_pattern = r"\b(pickle\.(load|dump)|joblib\.(load|dump)|torch\.(load|save))\s*\("
        matches = re.findall(call_pattern, src)
        assert len(matches) == 0, f"Found pickle/joblib/torch calls: {matches}"
