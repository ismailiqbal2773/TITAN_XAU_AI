"""TITAN XAU AI - Sprint 9.9.3.44.4 Post-Trade Verification Tests"""
from __future__ import annotations
import json, re, sys
from pathlib import Path
import pytest
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

class TestPostTradeVerification:
    def test_01_returns_result(self):
        import scripts.operator.verify_demo_micro_position as vt
        result = vt.run_verification()
        assert "verdict" in result and "ok_checks" in result

    def test_02_writes_json(self, tmp_path):
        import scripts.operator.verify_demo_micro_position as vt
        old = vt.OUTPUT_DIR; vt.OUTPUT_DIR = tmp_path
        try:
            result = vt.run_verification(); report = vt.write_report(result)
            assert Path(report["json_path"]).exists()
        finally: vt.OUTPUT_DIR = old

    def test_03_writes_md(self, tmp_path):
        import scripts.operator.verify_demo_micro_position as vt
        old = vt.OUTPUT_DIR; vt.OUTPUT_DIR = tmp_path
        try:
            result = vt.run_verification(); report = vt.write_report(result)
            assert "Post-Trade Verification" in Path(report["md_path"]).read_text()
        finally: vt.OUTPUT_DIR = old

    def test_04_no_mojibake(self, tmp_path):
        import scripts.operator.verify_demo_micro_position as vt
        old = vt.OUTPUT_DIR; vt.OUTPUT_DIR = tmp_path
        try:
            result = vt.run_verification(); report = vt.write_report(result)
            md = Path(report["md_path"]).read_text(encoding="utf-8")
            assert "\u2014" not in md
        finally: vt.OUTPUT_DIR = old

    def test_05_no_order_send(self):
        src = (REPO_ROOT / "scripts" / "operator" / "verify_demo_micro_position.py").read_text()
        code = re.sub(r'"""[\s\S]*?"""','""',src)
        code = re.sub(r'"(?:[^"\\]|\\.)*"','""',code)
        code = re.sub(r"'(?:[^'\\]|\\.)*'","''",code)
        assert not re.search(r"\bmt5\.order_send\s*\(", code)

    def test_06_no_demo_micro_execute(self):
        src = (REPO_ROOT / "scripts" / "operator" / "verify_demo_micro_position.py").read_text()
        code = re.sub(r'"""[\s\S]*?"""','""',src)
        code = re.sub(r'"(?:[^"\\]|\\.)*"','""',code)
        code = re.sub(r"'(?:[^'\\]|\\.)*'","''",code)
        assert not re.search(r"(?<!['\"])\b(DEMO_MICRO_EXECUTE|run_demo_micro)\s*\(", code)
