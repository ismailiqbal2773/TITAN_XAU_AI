"""TITAN XAU AI - Sprint 9.9.3.44 Demo Micro Force-Close Readiness Tests"""
from __future__ import annotations
import json, re, sys
from pathlib import Path
import pytest
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

class TestForceCloseReadiness:
    def test_01_returns_result(self):
        import scripts.operator.check_demo_micro_force_close_readiness as fc
        result = fc.run_check()
        assert "verdict" in result and "ok_checks" in result

    def test_02_writes_json(self, tmp_path):
        import scripts.operator.check_demo_micro_force_close_readiness as fc
        old = fc.OUTPUT_DIR; fc.OUTPUT_DIR = tmp_path
        try:
            result = fc.run_check(); report = fc.write_report(result)
            assert Path(report["json_path"]).exists()
        finally: fc.OUTPUT_DIR = old

    def test_03_writes_md(self, tmp_path):
        import scripts.operator.check_demo_micro_force_close_readiness as fc
        old = fc.OUTPUT_DIR; fc.OUTPUT_DIR = tmp_path
        try:
            result = fc.run_check(); report = fc.write_report(result)
            assert "Force-Close Readiness" in Path(report["md_path"]).read_text()
        finally: fc.OUTPUT_DIR = old

    def test_04_close_preview_present(self):
        import scripts.operator.check_demo_micro_force_close_readiness as fc
        result = fc.run_check()
        assert "close_request_preview" in result
        assert result["close_request_preview"]["action"] == "CLOSE_POSITION"

    def test_05_emergency_instructions_present(self):
        import scripts.operator.check_demo_micro_force_close_readiness as fc
        result = fc.run_check()
        assert "emergency_close_instructions" in result
        assert len(result["emergency_close_instructions"]) >= 5

    def test_06_no_order_send(self):
        src = (REPO_ROOT / "scripts" / "operator" / "check_demo_micro_force_close_readiness.py").read_text()
        code = re.sub(r'"""[\s\S]*?"""','""',src)
        code = re.sub(r'"(?:[^"\\]|\\.)*"','""',code)
        code = re.sub(r"'(?:[^'\\]|\\.)*'","''",code)
        assert not re.search(r"\bmt5\.order_send\s*\(", code)

    def test_07_no_metatrader5_import(self):
        src = (REPO_ROOT / "scripts" / "operator" / "check_demo_micro_force_close_readiness.py").read_text()
        assert "import MetaTrader5" not in src and "from MetaTrader5" not in src
