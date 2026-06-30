"""TITAN XAU AI - Sprint 9.9.3.45 Demo Micro Trade Forensics Tests"""
from __future__ import annotations
import json, re, sys
from pathlib import Path
import pytest
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

class TestForensics:
    def test_01_returns_result(self):
        import scripts.operator.collect_demo_micro_trade_forensics as fc
        result = fc.collect_forensics()
        assert "verdict" in result and "findings" in result

    def test_02_writes_json(self, tmp_path):
        import scripts.operator.collect_demo_micro_trade_forensics as fc
        old = fc.OUTPUT_DIR; fc.OUTPUT_DIR = tmp_path
        try:
            result = fc.collect_forensics(); report = fc.write_report(result)
            assert Path(report["json_path"]).exists()
        finally: fc.OUTPUT_DIR = old

    def test_03_writes_md(self, tmp_path):
        import scripts.operator.collect_demo_micro_trade_forensics as fc
        old = fc.OUTPUT_DIR; fc.OUTPUT_DIR = tmp_path
        try:
            result = fc.collect_forensics(); report = fc.write_report(result)
            assert "Forensics" in Path(report["md_path"]).read_text()
        finally: fc.OUTPUT_DIR = old

    def test_04_no_order_send(self):
        src = (REPO_ROOT / "scripts" / "operator" / "collect_demo_micro_trade_forensics.py").read_text()
        code = re.sub(r'"""[\s\S]*?"""','""',src)
        code = re.sub(r'"(?:[^"\\]|\\.)*"','""',code)
        code = re.sub(r"'(?:[^'\\]|\\.)*'","''",code)
        assert not re.search(r"\bmt5\.order_send\s*\(", code)

    def test_05_no_demo_micro_execute(self):
        src = (REPO_ROOT / "scripts" / "operator" / "collect_demo_micro_trade_forensics.py").read_text()
        code = re.sub(r'"""[\s\S]*?"""','""',src)
        code = re.sub(r'"(?:[^"\\]|\\.)*"','""',code)
        code = re.sub(r"'(?:[^'\\]|\\.)*'","''",code)
        assert not re.search(r"(?<!['\"])\b(DEMO_MICRO_EXECUTE|run_demo_micro)\s*\(", code)
