"""TITAN XAU AI - Sprint 9.9.3.42 7-Day Observation Batch Safety Tests"""
from __future__ import annotations
import re, sys
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


class TestBatchFileSafety:
    def test_01_batch_file_exists(self):
        batch_path = REPO_ROOT / "run_titan_7_day_observation.bat"
        assert batch_path.exists()

    def test_02_batch_has_4_safe_options(self):
        batch_path = REPO_ROOT / "run_titan_7_day_observation.bat"
        content = batch_path.read_text(encoding="utf-8")
        assert "START 7-DAY OBSERVATION CHECK" in content
        assert "RUN DAILY SCORECARD" in content
        assert "FINALIZE 7-DAY REPORT" in content
        assert "OPEN OPERATOR CONSOLE" in content
        assert "EXIT" in content

    def test_03_batch_no_live_trading_command(self):
        batch_path = REPO_ROOT / "run_titan_7_day_observation.bat"
        content = batch_path.read_text(encoding="utf-8")
        for line in content.splitlines():
            stripped = line.strip()
            upper = stripped.upper()
            if upper.startswith("PYTHON"):
                lower = stripped.lower()
                assert "live_trading" not in lower or "blocked" in lower

    def test_04_batch_no_demo_micro_execute(self):
        batch_path = REPO_ROOT / "run_titan_7_day_observation.bat"
        content = batch_path.read_text(encoding="utf-8")
        for line in content.splitlines():
            stripped = line.strip()
            upper = stripped.upper()
            if upper.startswith("PYTHON"):
                lower = stripped.lower()
                assert "demo_micro_execute" not in lower
                assert "demo_micro_full_cycle" not in lower

    def test_05_batch_no_raw_mt5_probe(self):
        batch_path = REPO_ROOT / "run_titan_7_day_observation.bat"
        content = batch_path.read_text(encoding="utf-8")
        for line in content.splitlines():
            stripped = line.strip()
            upper = stripped.upper()
            if upper.startswith("PYTHON"):
                lower = stripped.lower()
                assert "raw_mt5_probe" not in lower

    def test_06_batch_no_repeatability(self):
        batch_path = REPO_ROOT / "run_titan_7_day_observation.bat"
        content = batch_path.read_text(encoding="utf-8")
        for line in content.splitlines():
            stripped = line.strip()
            upper = stripped.upper()
            if upper.startswith("PYTHON"):
                lower = stripped.lower()
                assert "demo_micro_repeatability" not in lower

    def test_07_batch_no_retraining(self):
        batch_path = REPO_ROOT / "run_titan_7_day_observation.bat"
        content = batch_path.read_text(encoding="utf-8")
        for line in content.splitlines():
            stripped = line.strip()
            upper = stripped.upper()
            if upper.startswith("PYTHON"):
                lower = stripped.lower()
                assert "retrain" not in lower
                assert "hpo" not in lower

    def test_08_batch_activates_venv(self):
        batch_path = REPO_ROOT / "run_titan_7_day_observation.bat"
        content = batch_path.read_text(encoding="utf-8")
        assert "activate.bat" in content

    def test_09_batch_calls_safe_scripts(self):
        batch_path = REPO_ROOT / "run_titan_7_day_observation.bat"
        content = batch_path.read_text(encoding="utf-8")
        assert "start_7_day_demo_observation.py" in content
        assert "run_daily_observation_scorecard.py" in content
        assert "finalize_7_day_demo_observation.py" in content
        assert "titan_operator.py" in content


class TestNoUnsafeExposure:
    def test_10_no_order_send_in_safe_scripts(self):
        """All operator scripts must not call order_send."""
        safe_scripts = [
            "scripts/operator/start_7_day_demo_observation.py",
            "scripts/operator/run_daily_observation_scorecard.py",
            "scripts/operator/finalize_7_day_demo_observation.py",
            "scripts/operator/titan_operator.py",
            "scripts/operator/titan_first_run.py",
        ]
        for rel in safe_scripts:
            path = REPO_ROOT / rel
            if not path.exists():
                continue
            src = path.read_text(encoding="utf-8")
            code = re.sub(r'"""[\s\S]*?"""', '""', src)
            code = re.sub(r"'''[\s\S]*?'''", "''", code)
            code = re.sub(r'r"[^"]*"', '""', code)
            code = re.sub(r"r'[^']*'", "''", code)
            code = re.sub(r'"(?:[^"\\]|\\.)*"', '""', code)
            code = re.sub(r"'(?:[^'\\]|\\.)*'", "''", code)
            assert not re.search(r"\bmt5\.order_send\s*\(", code), \
                f"{rel} calls mt5.order_send"

    def test_11_no_demo_micro_execute_in_safe_scripts(self):
        safe_scripts = [
            "scripts/operator/start_7_day_demo_observation.py",
            "scripts/operator/run_daily_observation_scorecard.py",
            "scripts/operator/finalize_7_day_demo_observation.py",
        ]
        for rel in safe_scripts:
            path = REPO_ROOT / rel
            if not path.exists():
                continue
            src = path.read_text(encoding="utf-8")
            code = re.sub(r'"""[\s\S]*?"""', '""', src)
            code = re.sub(r"'''[\s\S]*?'''", "''", code)
            code = re.sub(r'r"[^"]*"', '""', code)
            code = re.sub(r"r'[^']*'", "''", code)
            code = re.sub(r'"(?:[^"\\]|\\.)*"', '""', code)
            code = re.sub(r"'(?:[^'\\]|\\.)*'", "''", code)
            assert not re.search(r"(?<!['\"])\b(DEMO_MICRO_EXECUTE|run_demo_micro)\s*\(", code), \
                f"{rel} calls DEMO_MICRO_EXECUTE"

    def test_12_no_raw_mt5_probe_in_safe_scripts(self):
        safe_scripts = [
            "scripts/operator/start_7_day_demo_observation.py",
            "scripts/operator/run_daily_observation_scorecard.py",
            "scripts/operator/finalize_7_day_demo_observation.py",
        ]
        for rel in safe_scripts:
            path = REPO_ROOT / rel
            if not path.exists():
                continue
            src = path.read_text(encoding="utf-8")
            code = re.sub(r'"""[\s\S]*?"""', '""', src)
            code = re.sub(r"'''[\s\S]*?'''", "''", code)
            code = re.sub(r'r"[^"]*"', '""', code)
            code = re.sub(r"r'[^']*'", "''", code)
            code = re.sub(r'"(?:[^"\\]|\\.)*"', '""', code)
            code = re.sub(r"'(?:[^'\\]|\\.)*'", "''", code)
            assert not re.search(r"(?<!['\"])\b(run_raw_probe|raw_mt5_probe)\s*\(", code), \
                f"{rel} calls raw_mt5_probe"
