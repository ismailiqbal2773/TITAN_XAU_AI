"""TITAN XAU AI - Sprint 9.9.3.43.1 Environment Freeze Lock Tests"""
from __future__ import annotations
import json, re, sys
from pathlib import Path
import pytest
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

class TestFreezeLock:
    def test_01_freeze_writes_lock_file(self, tmp_path):
        import scripts.audit.freeze_current_environment as fe
        old = fe.OUTPUT_DIR; fe.OUTPUT_DIR = tmp_path
        try:
            sig = fe.freeze(); report = fe.write_report(sig)
            assert Path(report["lock_path"]).exists()
        finally: fe.OUTPUT_DIR = old

    def test_02_freeze_writes_json(self, tmp_path):
        import scripts.audit.freeze_current_environment as fe
        old = fe.OUTPUT_DIR; fe.OUTPUT_DIR = tmp_path
        try:
            sig = fe.freeze(); report = fe.write_report(sig)
            assert Path(report["json_path"]).exists()
            with open(report["json_path"]) as f: data = json.load(f)
            assert "python_version" in data and "critical_packages" in data
        finally: fe.OUTPUT_DIR = old

    def test_03_freeze_writes_md(self, tmp_path):
        import scripts.audit.freeze_current_environment as fe
        old = fe.OUTPUT_DIR; fe.OUTPUT_DIR = tmp_path
        try:
            sig = fe.freeze(); report = fe.write_report(sig)
            assert "Environment Signature" in Path(report["md_path"]).read_text()
        finally: fe.OUTPUT_DIR = old

    def test_04_freeze_includes_model_hashes(self, tmp_path):
        import scripts.audit.freeze_current_environment as fe
        old = fe.OUTPUT_DIR; fe.OUTPUT_DIR = tmp_path
        try:
            sig = fe.freeze()
            assert "model_files" in sig
            if sig["model_files"]:
                for name, info in sig["model_files"].items():
                    assert "sha256" in info and "size_bytes" in info
        finally: fe.OUTPUT_DIR = old

    def test_05_no_auto_pip_install(self):
        import inspect
        src = inspect.getsource(__import__("scripts.audit.freeze_current_environment", fromlist=["x"]))
        # pip freeze is OK (read-only), but pip install is NOT
        code = re.sub(r'"""[\s\S]*?"""','""',src)
        assert "pip install" not in code.lower()

    def test_06_no_metatrader5_import(self):
        import inspect
        src = inspect.getsource(__import__("scripts.audit.freeze_current_environment", fromlist=["x"]))
        assert "import MetaTrader5" not in src and "from MetaTrader5" not in src

    def test_07_no_order_send(self):
        import inspect, re
        src = inspect.getsource(__import__("scripts.audit.freeze_current_environment", fromlist=["x"]))
        code = re.sub(r'"""[\s\S]*?"""','""',src)
        code = re.sub(r'"(?:[^"\\]|\\.)*"','""',code)
        code = re.sub(r"'(?:[^'\\]|\\.)*'","''",code)
        assert not re.search(r"\bmt5\.order_send\s*\(", code)
