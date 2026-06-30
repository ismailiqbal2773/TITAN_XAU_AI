"""TITAN XAU AI - Sprint 9.9.3.42.1 Accelerated Observation Scorecard Tests"""
from __future__ import annotations
import json, sys
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


class TestScorecard:
    def test_01_scorecard_returns_result(self, tmp_path):
        import scripts.operator.run_accelerated_observation_scorecard as sc
        old_dir = sc.OUTPUT_DIR
        sc.OUTPUT_DIR = tmp_path
        try:
            result = sc.run_scorecard()
            assert "verdict" in result
            assert "real_short_metrics" in result
            assert "replay_metrics" in result
            assert "true_forward_metrics" in result
        finally:
            sc.OUTPUT_DIR = old_dir

    def test_02_scorecard_separates_real_short_and_replay(self, tmp_path):
        import scripts.operator.run_accelerated_observation_scorecard as sc
        old_dir = sc.OUTPUT_DIR
        sc.OUTPUT_DIR = tmp_path
        try:
            result = sc.run_scorecard()
            rs = result["real_short_metrics"]
            rp = result["replay_metrics"]
            # Metrics must be separate objects
            assert rs is not rp
            # Labels must be different
            assert "REAL_SHORT" in rs["label"]
            assert "REPLAY" in rp["label"]
        finally:
            sc.OUTPUT_DIR = old_dir

    def test_03_true_forward_not_run(self, tmp_path):
        import scripts.operator.run_accelerated_observation_scorecard as sc
        old_dir = sc.OUTPUT_DIR
        sc.OUTPUT_DIR = tmp_path
        try:
            result = sc.run_scorecard()
            tf = result["true_forward_metrics"]
            assert tf["available"] is False
            assert tf["verdict"] == "NOT_RUN"
        finally:
            sc.OUTPUT_DIR = old_dir

    def test_04_insufficient_data_when_no_reports(self, tmp_path):
        import scripts.operator.run_accelerated_observation_scorecard as sc
        old_dir = sc.OUTPUT_DIR
        sc.OUTPUT_DIR = tmp_path
        try:
            result = sc.run_scorecard()
            assert result["verdict"] == "ACCELERATED_SCORECARD_INSUFFICIENT_DATA"
        finally:
            sc.OUTPUT_DIR = old_dir

    def test_05_writes_json(self, tmp_path):
        import scripts.operator.run_accelerated_observation_scorecard as sc
        old_dir = sc.OUTPUT_DIR
        sc.OUTPUT_DIR = tmp_path
        try:
            result = sc.run_scorecard()
            report = sc.write_report(result)
            assert Path(report["json_path"]).exists()
            with open(report["json_path"]) as f:
                data = json.load(f)
            assert "verdict" in data
        finally:
            sc.OUTPUT_DIR = old_dir

    def test_06_writes_md(self, tmp_path):
        import scripts.operator.run_accelerated_observation_scorecard as sc
        old_dir = sc.OUTPUT_DIR
        sc.OUTPUT_DIR = tmp_path
        try:
            result = sc.run_scorecard()
            report = sc.write_report(result)
            md = Path(report["md_path"]).read_text(encoding="utf-8")
            assert "Accelerated Observation Scorecard" in md
            assert "Real Short Metrics" in md
            assert "Replay Metrics" in md
            assert "True Forward Metrics" in md
        finally:
            sc.OUTPUT_DIR = old_dir

    def test_07_no_metatrader5_import(self):
        import inspect
        import scripts.operator.run_accelerated_observation_scorecard as sc
        src = inspect.getsource(sc)
        assert "import MetaTrader5" not in src
        assert "from MetaTrader5" not in src

    def test_08_no_order_send(self):
        import re, inspect
        import scripts.operator.run_accelerated_observation_scorecard as sc
        src = inspect.getsource(sc)
        src = re.sub(r'"""[\s\S]*?"""', '""', src)
        src = re.sub(r"'''[\s\S]*?'''", "''", src)
        src = re.sub(r'r"[^"]*"', '""', src)
        src = re.sub(r"r'[^']*'", "''", src)
        src = re.sub(r'"(?:[^"\\]|\\.)*"', '""', src)
        src = re.sub(r"'(?:[^'\\]|\\.)*'", "''", src)
        assert not re.search(r"\bmt5\.order_send\s*\(", src)
