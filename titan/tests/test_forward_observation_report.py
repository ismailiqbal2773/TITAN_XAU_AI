"""TITAN XAU AI — Sprint 9.9.3.32 Forward Observation Report Tests"""
from __future__ import annotations
import inspect, json, sys
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


class TestReportWriter:
    def test_01_json_report_writes(self, tmp_path):
        import scripts.audit.forward_observation_report as rep
        old_dir, old_json, old_md = rep.OUTPUT_DIR, rep.JSON_PATH, rep.MD_PATH
        rep.OUTPUT_DIR = tmp_path
        rep.JSON_PATH = tmp_path / "report.json"
        rep.MD_PATH = tmp_path / "report.md"
        try:
            result = rep.write_report(journal_paths=["/nonexistent/path.jsonl"])
            assert Path(result["json_path"]).exists()
            with open(result["json_path"]) as f:
                data = json.load(f)
            assert "counts" in data
            assert "verdict" in data
            assert "warnings_general" in data
            assert data["counts"]["total_events"] == 0
        finally:
            rep.OUTPUT_DIR, rep.JSON_PATH, rep.MD_PATH = old_dir, old_json, old_md

    def test_02_md_report_writes(self, tmp_path):
        import scripts.audit.forward_observation_report as rep
        old_dir, old_json, old_md = rep.OUTPUT_DIR, rep.JSON_PATH, rep.MD_PATH
        rep.OUTPUT_DIR = tmp_path
        rep.JSON_PATH = tmp_path / "report.json"
        rep.MD_PATH = tmp_path / "report.md"
        try:
            result = rep.write_report(journal_paths=["/nonexistent/path.jsonl"])
            md = Path(result["md_path"]).read_text()
            assert "Forward Observation Report" in md
            assert "Event Counts" in md
            assert "Journals" in md
            assert "no market execution" in md.lower()
        finally:
            rep.OUTPUT_DIR, rep.JSON_PATH, rep.MD_PATH = old_dir, old_json, old_md

    def test_03_missing_journal_does_not_crash(self):
        import scripts.audit.forward_observation_report as rep
        result = rep.write_report(journal_paths=["/nonexistent/path.jsonl"])
        assert result is not None

    def test_04_report_with_actual_journal(self, tmp_path):
        import scripts.audit.forward_observation_report as rep
        jpath = tmp_path / "test.jsonl"
        jpath.write_text(json.dumps({"event": "SIGNAL_CREATED", "symbol": "XAUUSD"}) + "\n"
                          + json.dumps({"event": "DEMO_MICRO_FULL_CYCLE_PASS"}) + "\n")
        old_dir, old_json, old_md = rep.OUTPUT_DIR, rep.JSON_PATH, rep.MD_PATH
        rep.OUTPUT_DIR = tmp_path
        rep.JSON_PATH = tmp_path / "report.json"
        rep.MD_PATH = tmp_path / "report.md"
        try:
            result = rep.write_report(journal_paths=[str(jpath)])
            with open(result["json_path"]) as f:
                data = json.load(f)
            assert data["counts"]["signal_count"] >= 1
            assert data["counts"]["heartbeat_count"] >= 1
        finally:
            rep.OUTPUT_DIR, rep.JSON_PATH, rep.MD_PATH = old_dir, old_json, old_md

    def test_05_no_mt5_in_report_writer(self):
        import scripts.audit.forward_observation_report as rep
        src = inspect.getsource(rep)
        assert "import MetaTrader5" not in src
        assert "order_send" not in src

    def test_06_verdict_ready_when_no_events(self, tmp_path):
        import scripts.audit.forward_observation_report as rep
        old_dir, old_json, old_md = rep.OUTPUT_DIR, rep.JSON_PATH, rep.MD_PATH
        rep.OUTPUT_DIR = tmp_path
        rep.JSON_PATH = tmp_path / "report.json"
        rep.MD_PATH = tmp_path / "report.md"
        try:
            result = rep.write_report(journal_paths=["/nonexistent/path.jsonl"])
            with open(result["json_path"]) as f:
                data = json.load(f)
            # With 0 events and no blockers, should be READY or WARNINGS
            assert data["verdict"] in ("OBSERVATION_READY", "OBSERVATION_WARNINGS")
        finally:
            rep.OUTPUT_DIR, rep.JSON_PATH, rep.MD_PATH = old_dir, old_json, old_md
