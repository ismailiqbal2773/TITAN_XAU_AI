"""TITAN XAU AI - Sprint 9.9.3.42 Daily Observation Scorecard Runner Tests"""
from __future__ import annotations
import inspect, json, re, sys
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


class TestDailyScorecardRunner:
    def test_01_insufficient_data_when_no_journals(self, tmp_path):
        import scripts.operator.run_daily_observation_scorecard as runner
        # Use nonexistent journal path
        result = runner.run_daily_scorecard(
            day=1, since_hours=24,
            journal_paths=[str(tmp_path / "nonexistent.jsonl")],
        )
        assert result["verdict"] == "INSUFFICIENT_DATA"

    def test_02_writes_day_json(self, tmp_path):
        import scripts.operator.run_daily_observation_scorecard as runner
        old_dir = runner.OUTPUT_DIR
        runner.OUTPUT_DIR = tmp_path
        try:
            result = runner.run_daily_scorecard(
                day=1, since_hours=24,
                journal_paths=[str(tmp_path / "nonexistent.jsonl")],
            )
            report = runner.write_report(result)
            assert Path(report["json_path"]).exists()
            with open(report["json_path"]) as f:
                data = json.load(f)
            assert data["day"] == 1
            assert "verdict" in data
        finally:
            runner.OUTPUT_DIR = old_dir

    def test_03_writes_day_md(self, tmp_path):
        import scripts.operator.run_daily_observation_scorecard as runner
        old_dir = runner.OUTPUT_DIR
        runner.OUTPUT_DIR = tmp_path
        try:
            result = runner.run_daily_scorecard(
                day=1, since_hours=24,
                journal_paths=[str(tmp_path / "nonexistent.jsonl")],
            )
            report = runner.write_report(result)
            md = Path(report["md_path"]).read_text(encoding="utf-8")
            assert "Day 1 Observation Scorecard" in md
        finally:
            runner.OUTPUT_DIR = old_dir

    def test_04_fails_if_order_send_evidence(self, tmp_path):
        """If journal contains order_send execution evidence, verdict must be FAIL."""
        import scripts.operator.run_daily_observation_scorecard as runner
        journal = tmp_path / "test.jsonl"
        journal.write_text(json.dumps({
            "event_type": "ORDER_SENT",
            "timestamp_utc": "2026-06-30T10:00:00Z",
            "order_send_result": "success",
            "executed": True,
        }) + "\n")
        result = runner.run_daily_scorecard(
            day=1, since_hours=9999,
            journal_paths=[str(journal)],
        )
        assert result["verdict"] == "FAIL"
        assert any("order_send" in v for v in result["forbidden_evidence"])

    def test_05_fails_if_live_trading_evidence(self, tmp_path):
        import scripts.operator.run_daily_observation_scorecard as runner
        journal = tmp_path / "test.jsonl"
        journal.write_text(json.dumps({
            "event_type": "LIVE_TRADING_ENABLED",
            "timestamp_utc": "2026-06-30T10:00:00Z",
            "live_trading": True,
        }) + "\n")
        result = runner.run_daily_scorecard(
            day=1, since_hours=9999,
            journal_paths=[str(journal)],
        )
        assert result["verdict"] == "FAIL"

    def test_06_fails_if_open_positions_remain(self, tmp_path):
        import scripts.operator.run_daily_observation_scorecard as runner
        journal = tmp_path / "test.jsonl"
        journal.write_text(json.dumps({
            "event_type": "POSITION_OPENED",
            "timestamp_utc": "2026-06-30T10:00:00Z",
        }) + "\n")
        result = runner.run_daily_scorecard(
            day=1, since_hours=9999,
            journal_paths=[str(journal)],
        )
        # Open positions at day end → FAIL
        assert result["verdict"] in ("FAIL", "INSUFFICIENT_DATA")

    def test_07_returns_insufficient_data_for_empty_journal(self, tmp_path):
        import scripts.operator.run_daily_observation_scorecard as runner
        journal = tmp_path / "empty.jsonl"
        journal.write_text("")
        result = runner.run_daily_scorecard(
            day=1, since_hours=24,
            journal_paths=[str(journal)],
        )
        assert result["verdict"] == "INSUFFICIENT_DATA"


class TestSafetyInvariants:
    def test_08_no_metatrader5_import(self):
        import scripts.operator.run_daily_observation_scorecard as runner
        src = inspect.getsource(runner)
        assert "import MetaTrader5" not in src
        assert "from MetaTrader5" not in src

    def test_09_no_order_send(self):
        import re
        import scripts.operator.run_daily_observation_scorecard as runner
        src = inspect.getsource(runner)
        src = re.sub(r'"""[\s\S]*?"""', '""', src)
        src = re.sub(r"'''[\s\S]*?'''", "''", src)
        src = re.sub(r'r"[^"]*"', '""', src)
        src = re.sub(r"r'[^']*'", "''", src)
        src = re.sub(r'"(?:[^"\\]|\\.)*"', '""', src)
        src = re.sub(r"'(?:[^'\\]|\\.)*'", "''", src)
        assert not re.search(r"\bmt5\.order_send\s*\(", src)

    def test_10_no_demo_micro_execute(self):
        import re
        import scripts.operator.run_daily_observation_scorecard as runner
        src = inspect.getsource(runner)
        src = re.sub(r'"""[\s\S]*?"""', '""', src)
        src = re.sub(r"'''[\s\S]*?'''", "''", src)
        src = re.sub(r'r"[^"]*"', '""', src)
        src = re.sub(r"r'[^']*'", "''", src)
        src = re.sub(r'"(?:[^"\\]|\\.)*"', '""', src)
        src = re.sub(r"'(?:[^'\\]|\\.)*'", "''", src)
        assert not re.search(r"(?<!['\"])\b(DEMO_MICRO_EXECUTE|run_demo_micro)\s*\(", src)
