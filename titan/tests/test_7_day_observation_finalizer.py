"""TITAN XAU AI - Sprint 9.9.3.42 7-Day Observation Finalizer Tests"""
from __future__ import annotations
import inspect, json, re, sys
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


class TestFinalizer:
    def test_01_finalizer_returns_result(self):
        import scripts.operator.finalize_7_day_demo_observation as fin
        result = fin.finalize()
        assert "verdict" in result
        assert "days_observed" in result
        assert "event_counts" in result
        assert "forbidden_evidence" in result
        assert "final_open_positions" in result

    def test_02_insufficient_data_when_no_scorecards(self, tmp_path):
        import scripts.operator.finalize_7_day_demo_observation as fin
        old_dir = fin.OUTPUT_DIR
        fin.OUTPUT_DIR = tmp_path
        try:
            result = fin.finalize()
            assert result["verdict"] == "SEVEN_DAY_OBSERVATION_INSUFFICIENT_DATA"
            assert result["days_observed"] == 0
        finally:
            fin.OUTPUT_DIR = old_dir

    def test_03_writes_json_report(self, tmp_path):
        import scripts.operator.finalize_7_day_demo_observation as fin
        old_dir = fin.OUTPUT_DIR
        fin.OUTPUT_DIR = tmp_path
        try:
            result = fin.finalize()
            report = fin.write_report(result)
            assert Path(report["json_path"]).exists()
            with open(report["json_path"]) as f:
                data = json.load(f)
            assert "verdict" in data
            assert "days_observed" in data
        finally:
            fin.OUTPUT_DIR = old_dir

    def test_04_writes_md_report(self, tmp_path):
        import scripts.operator.finalize_7_day_demo_observation as fin
        old_dir = fin.OUTPUT_DIR
        fin.OUTPUT_DIR = tmp_path
        try:
            result = fin.finalize()
            report = fin.write_report(result)
            md = Path(report["md_path"]).read_text(encoding="utf-8")
            assert "Final 7-Day Observation Report" in md
            assert "Verdict" in md
        finally:
            fin.OUTPUT_DIR = old_dir

    def test_05_handles_missing_days(self, tmp_path):
        """Finalizer should handle missing days gracefully."""
        import scripts.operator.finalize_7_day_demo_observation as fin
        old_dir = fin.OUTPUT_DIR
        fin.OUTPUT_DIR = tmp_path
        try:
            # Write only 3 day scorecards
            for day in range(1, 4):
                sc = {"day": day, "verdict": "PASS", "scorecard": {"warnings": []}}
                with open(tmp_path / f"day_{day}_scorecard.json", "w") as f:
                    json.dump(sc, f)
            result = fin.finalize()
            assert result["days_observed"] == 3
            assert result["missing_days"] == 4
            assert result["verdict"] == "SEVEN_DAY_OBSERVATION_INSUFFICIENT_DATA"
        finally:
            fin.OUTPUT_DIR = old_dir

    def test_06_pass_with_warnings_for_approved_regime_placeholder(self, tmp_path):
        """PASS_WITH_WARNINGS should be returned when only approved warnings exist."""
        import scripts.operator.finalize_7_day_demo_observation as fin
        old_dir = fin.OUTPUT_DIR
        fin.OUTPUT_DIR = tmp_path
        try:
            for day in range(1, 8):
                sc = {
                    "day": day,
                    "verdict": "WARN",
                    "scorecard": {"warnings": ["REGIME_GATE_WIRED_BUT_PLACEHOLDER_CONTEXT"]},
                    "regime_placeholder_persists": True,
                }
                with open(tmp_path / f"day_{day}_scorecard.json", "w") as f:
                    json.dump(sc, f)
            result = fin.finalize()
            assert result["verdict"] == "SEVEN_DAY_OBSERVATION_PASS_WITH_WARNINGS"
        finally:
            fin.OUTPUT_DIR = old_dir

    def test_07_fail_if_daily_fail(self, tmp_path):
        """FAIL should be returned if any daily scorecard is FAIL."""
        import scripts.operator.finalize_7_day_demo_observation as fin
        old_dir = fin.OUTPUT_DIR
        fin.OUTPUT_DIR = tmp_path
        try:
            for day in range(1, 8):
                verdict = "FAIL" if day == 3 else "PASS"
                sc = {"day": day, "verdict": verdict, "scorecard": {"warnings": []}}
                with open(tmp_path / f"day_{day}_scorecard.json", "w") as f:
                    json.dump(sc, f)
            result = fin.finalize()
            assert result["verdict"] == "SEVEN_DAY_OBSERVATION_FAIL"
        finally:
            fin.OUTPUT_DIR = old_dir


class TestSafetyInvariants:
    def test_08_no_metatrader5_import(self):
        import scripts.operator.finalize_7_day_demo_observation as fin
        src = inspect.getsource(fin)
        assert "import MetaTrader5" not in src
        assert "from MetaTrader5" not in src

    def test_09_no_order_send(self):
        import re
        import scripts.operator.finalize_7_day_demo_observation as fin
        src = inspect.getsource(fin)
        src = re.sub(r'"""[\s\S]*?"""', '""', src)
        src = re.sub(r"'''[\s\S]*?'''", "''", src)
        src = re.sub(r'r"[^"]*"', '""', src)
        src = re.sub(r"r'[^']*'", "''", src)
        src = re.sub(r'"(?:[^"\\]|\\.)*"', '""', src)
        src = re.sub(r"'(?:[^'\\]|\\.)*'", "''", src)
        assert not re.search(r"\bmt5\.order_send\s*\(", src)

    def test_10_no_demo_micro_execute(self):
        import re
        import scripts.operator.finalize_7_day_demo_observation as fin
        src = inspect.getsource(fin)
        src = re.sub(r'"""[\s\S]*?"""', '""', src)
        src = re.sub(r"'''[\s\S]*?'''", "''", src)
        src = re.sub(r'r"[^"]*"', '""', src)
        src = re.sub(r"r'[^']*'", "''", src)
        src = re.sub(r'"(?:[^"\\]|\\.)*"', '""', src)
        src = re.sub(r"'(?:[^'\\]|\\.)*'", "''", src)
        assert not re.search(r"(?<!['\"])\b(DEMO_MICRO_EXECUTE|run_demo_micro)\s*\(", src)
