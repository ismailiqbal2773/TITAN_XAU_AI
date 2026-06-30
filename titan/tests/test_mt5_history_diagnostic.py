"""TITAN XAU AI - Sprint 9.9.3.45.1 MT5 History Diagnostic Tests"""
from __future__ import annotations
import json, re, sys
from pathlib import Path
import pytest
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

class TestDiagnostic:
    def test_01_returns_result(self):
        import scripts.operator.diagnose_mt5_history_access as dg
        result = dg.run_diagnostic()
        assert "verdict" in result and "findings" in result

    def test_02_writes_json(self, tmp_path):
        import scripts.operator.diagnose_mt5_history_access as dg
        old = dg.OUTPUT_DIR; dg.OUTPUT_DIR = tmp_path
        try:
            result = dg.run_diagnostic(); report = dg.write_report(result)
            assert Path(report["json_path"]).exists()
        finally: dg.OUTPUT_DIR = old

    def test_03_writes_md(self, tmp_path):
        import scripts.operator.diagnose_mt5_history_access as dg
        old = dg.OUTPUT_DIR; dg.OUTPUT_DIR = tmp_path
        try:
            result = dg.run_diagnostic(); report = dg.write_report(result)
            assert "Diagnostic" in Path(report["md_path"]).read_text()
        finally: dg.OUTPUT_DIR = old

    def test_04_no_order_send(self):
        src = (REPO_ROOT / "scripts" / "operator" / "diagnose_mt5_history_access.py").read_text()
        code = re.sub(r'"""[\s\S]*?"""','""',src)
        code = re.sub(r'"(?:[^"\\]|\\.)*"','""',code)
        code = re.sub(r"'(?:[^'\\]|\\.)*'","''",code)
        assert not re.search(r"\bmt5\.order_send\s*\(", code)

    def test_05_no_demo_micro_execute(self):
        src = (REPO_ROOT / "scripts" / "operator" / "diagnose_mt5_history_access.py").read_text()
        code = re.sub(r'"""[\s\S]*?"""','""',src)
        code = re.sub(r'"(?:[^"\\]|\\.)*"','""',code)
        code = re.sub(r"'(?:[^'\\]|\\.)*'","''",code)
        assert not re.search(r"(?<!['\"])\b(DEMO_MICRO_EXECUTE|run_demo_micro)\s*\(", code)
