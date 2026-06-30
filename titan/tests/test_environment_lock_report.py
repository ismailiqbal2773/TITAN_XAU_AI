"""TITAN XAU AI - Sprint 9.9.3.43 Environment Lock Report Tests"""
from __future__ import annotations
import inspect, json, re, sys
from pathlib import Path
import pytest
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

class TestEnvLockReport:
    def test_01_json_writes(self, tmp_path):
        import scripts.audit.generate_environment_lock_report as env
        old = env.OUTPUT_DIR; env.OUTPUT_DIR = tmp_path
        try:
            result = env.generate(); report = env.write_report(result)
            assert Path(report["json_path"]).exists()
            with open(report["json_path"]) as f: data = json.load(f)
            assert "python_version" in data and "packages" in data
        finally: env.OUTPUT_DIR = old

    def test_02_md_writes(self, tmp_path):
        import scripts.audit.generate_environment_lock_report as env
        old = env.OUTPUT_DIR; env.OUTPUT_DIR = tmp_path
        try:
            result = env.generate(); report = env.write_report(result)
            assert "Environment Lock Report" in Path(report["md_path"]).read_text()
        finally: env.OUTPUT_DIR = old

    def test_03_freeze_file_writes(self, tmp_path):
        import scripts.audit.generate_environment_lock_report as env
        old = env.OUTPUT_DIR; env.OUTPUT_DIR = tmp_path
        try:
            result = env.generate(); report = env.write_report(result)
            assert Path(report["freeze_path"]).exists()
        finally: env.OUTPUT_DIR = old

    def test_04_no_auto_pip_install(self):
        import re
        src = inspect.getsource(__import__("scripts.audit.generate_environment_lock_report", fromlist=["x"]))
        # Strip docstrings
        src = re.sub(r'"""[\s\S]*?"""', '""', src)
        # Check actual code only
        assert "subprocess.run" not in src or "pip" not in src.lower()

    def test_05_no_metatrader5_import(self):
        src = inspect.getsource(__import__("scripts.audit.generate_environment_lock_report", fromlist=["x"]))
        assert "import MetaTrader5" not in src and "from MetaTrader5" not in src
