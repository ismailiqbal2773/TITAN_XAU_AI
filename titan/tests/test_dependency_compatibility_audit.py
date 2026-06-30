"""TITAN XAU AI - Sprint 9.9.3.43 Dependency Compatibility Audit Tests"""
from __future__ import annotations
import inspect, json, re, sys
from pathlib import Path
import pytest
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

class TestDependencyAudit:
    def test_01_json_writes(self, tmp_path):
        import scripts.audit.dependency_compatibility_audit as dep
        old_dir, old_json, old_md = dep.OUTPUT_DIR, dep.JSON_PATH, dep.MD_PATH
        dep.OUTPUT_DIR = tmp_path; dep.JSON_PATH = tmp_path / "dep.json"; dep.MD_PATH = tmp_path / "dep.md"
        try:
            result = dep.run_audit()
            report = dep.write_report(result)
            assert Path(report["json_path"]).exists()
            with open(report["json_path"]) as f: data = json.load(f)
            assert "verdict" in data and "installed_packages" in data
        finally:
            dep.OUTPUT_DIR, dep.JSON_PATH, dep.MD_PATH = old_dir, old_json, old_md

    def test_02_md_writes(self, tmp_path):
        import scripts.audit.dependency_compatibility_audit as dep
        old_dir, old_json, old_md = dep.OUTPUT_DIR, dep.JSON_PATH, dep.MD_PATH
        dep.OUTPUT_DIR = tmp_path; dep.JSON_PATH = tmp_path / "dep.json"; dep.MD_PATH = tmp_path / "dep.md"
        try:
            result = dep.run_audit(); report = dep.write_report(result)
            assert "Dependency Compatibility Audit" in Path(report["md_path"]).read_text()
        finally:
            dep.OUTPUT_DIR, dep.JSON_PATH, dep.MD_PATH = old_dir, old_json, old_md

    def test_03_verdict_in_valid_set(self):
        import scripts.audit.dependency_compatibility_audit as dep
        result = dep.run_audit()
        assert result["verdict"] in ("DEPENDENCY_READY","DEPENDENCY_READY_WITH_WARNINGS","DEPENDENCY_BLOCKED")

    def test_04_no_metatrader5_import(self):
        src = inspect.getsource(__import__("scripts.audit.dependency_compatibility_audit", fromlist=["x"]))
        assert "import MetaTrader5" not in src and "from MetaTrader5" not in src

    def test_05_no_order_send(self):
        import re; src = inspect.getsource(__import__("scripts.audit.dependency_compatibility_audit", fromlist=["x"]))
        code = re.sub(r'"""[\s\S]*?"""','""',src); code = re.sub(r'"(?:[^"\\]|\\.)*"','""',code); code = re.sub(r"'(?:[^'\\]|\\.)*'","''",code)
        assert not re.search(r"\bmt5\.order_send\s*\(", code)

    def test_06_no_auto_pip_install(self):
        src = inspect.getsource(__import__("scripts.audit.dependency_compatibility_audit", fromlist=["x"]))
        assert "pip install" not in src.lower()
