"""TITAN XAU AI — Sprint 9.9.3.33 Daily Demo Observation Runner Tests"""
from __future__ import annotations
import inspect, json, sys
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


class TestDailyRunner:
    def test_01_json_writes(self, tmp_path):
        import scripts.audit.daily_demo_observation_runner as runner
        old_dir, old_json, old_md = runner.OUTPUT_DIR, runner.JSON_PATH, runner.MD_PATH
        runner.OUTPUT_DIR = tmp_path
        runner.JSON_PATH = tmp_path / "scorecard.json"
        runner.MD_PATH = tmp_path / "scorecard.md"
        try:
            report = runner.run_scorecard(
                journal_paths=["/nonexistent/path.jsonl"],
                since_hours=24, final_open_positions=0,
            )
            assert Path(runner.JSON_PATH).exists()
            with open(runner.JSON_PATH) as f:
                data = json.load(f)
            assert "scorecard" in data
            assert "grade" in data["scorecard"]
            assert "operator_next_steps" in data
        finally:
            runner.OUTPUT_DIR, runner.JSON_PATH, runner.MD_PATH = old_dir, old_json, old_md

    def test_02_md_writes(self, tmp_path):
        import scripts.audit.daily_demo_observation_runner as runner
        old_dir, old_json, old_md = runner.OUTPUT_DIR, runner.JSON_PATH, runner.MD_PATH
        runner.OUTPUT_DIR = tmp_path
        runner.JSON_PATH = tmp_path / "scorecard.json"
        runner.MD_PATH = tmp_path / "scorecard.md"
        try:
            runner.run_scorecard(journal_paths=["/nonexistent/path.jsonl"])
            md = Path(runner.MD_PATH).read_text()
            assert "Daily Demo Observation Scorecard" in md
            assert "Scores" in md
            assert "Operator Next Steps" in md
            assert "no market execution" in md.lower()
        finally:
            runner.OUTPUT_DIR, runner.JSON_PATH, runner.MD_PATH = old_dir, old_json, old_md

    def test_03_missing_journal_does_not_crash(self):
        import scripts.audit.daily_demo_observation_runner as runner
        report = runner.run_scorecard(journal_paths=["/nonexistent/path.jsonl"])
        assert report is not None
        assert report["scorecard"]["grade"] == "INSUFFICIENT_DATA"

    def test_04_with_actual_journal(self, tmp_path):
        import scripts.audit.daily_demo_observation_runner as runner
        jpath = tmp_path / "test.jsonl"
        jpath.write_text(json.dumps({"event": "SIGNAL_CREATED", "symbol": "XAUUSD",
                                       "timestamp_utc": "2026-06-29T10:00:00Z"}) + "\n"
                          + json.dumps({"event": "DEMO_MICRO_FULL_CYCLE_PASS",
                                          "timestamp_utc": "2026-06-29T11:00:00Z"}) + "\n")
        old_dir, old_json, old_md = runner.OUTPUT_DIR, runner.JSON_PATH, runner.MD_PATH
        runner.OUTPUT_DIR = tmp_path
        runner.JSON_PATH = tmp_path / "scorecard.json"
        runner.MD_PATH = tmp_path / "scorecard.md"
        try:
            report = runner.run_scorecard(journal_paths=[str(jpath)], since_hours=99999)
            assert report["scorecard"]["signal_count"] >= 1
            assert report["scorecard"]["total_events"] >= 2
        finally:
            runner.OUTPUT_DIR, runner.JSON_PATH, runner.MD_PATH = old_dir, old_json, old_md

    def test_05_no_mt5_import(self):
        from titan.production import observation_scorecard
        src = inspect.getsource(observation_scorecard)
        assert "import MetaTrader5" not in src
        assert "order_send" not in src
        assert "MT5ExecutionAdapter" not in src

    def test_06_no_mt5_in_runner(self):
        import scripts.audit.daily_demo_observation_runner as runner
        src = inspect.getsource(runner)
        assert "import MetaTrader5" not in src
        assert "order_send" not in src

    def test_07_operator_next_steps_included(self, tmp_path):
        import scripts.audit.daily_demo_observation_runner as runner
        old_dir, old_json, old_md = runner.OUTPUT_DIR, runner.JSON_PATH, runner.MD_PATH
        runner.OUTPUT_DIR = tmp_path
        runner.JSON_PATH = tmp_path / "scorecard.json"
        runner.MD_PATH = tmp_path / "scorecard.md"
        try:
            report = runner.run_scorecard(journal_paths=["/nonexistent/path.jsonl"])
            assert len(report["operator_next_steps"]) >= 1
        finally:
            runner.OUTPUT_DIR, runner.JSON_PATH, runner.MD_PATH = old_dir, old_json, old_md
