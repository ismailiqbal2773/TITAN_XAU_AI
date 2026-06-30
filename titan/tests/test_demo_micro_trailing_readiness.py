"""TITAN XAU AI - Sprint 9.9.3.45 Trailing Readiness Tests"""
from __future__ import annotations
import json, sys
from pathlib import Path
import pytest
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

class TestTrailingReadiness:
    def test_01_returns_result(self):
        import scripts.audit.demo_micro_trailing_readiness_audit as ta
        result = ta.run_audit()
        assert "verdict" in result and "ok_checks" in result

    def test_02_verdict_in_valid_set(self):
        import scripts.audit.demo_micro_trailing_readiness_audit as ta
        result = ta.run_audit()
        assert result["verdict"] in ("TRAILING_READY","TRAILING_READY_WITH_WARNINGS","TRAILING_BLOCKED")

    def test_03_writes_json(self, tmp_path):
        import scripts.audit.demo_micro_trailing_readiness_audit as ta
        old = ta.OUTPUT_DIR; ta.OUTPUT_DIR = tmp_path
        try:
            result = ta.run_audit(); report = ta.write_report(result)
            assert Path(report["json_path"]).exists()
        finally: ta.OUTPUT_DIR = old

    def test_04_breakeven_logic_verified(self):
        import scripts.audit.demo_micro_trailing_readiness_audit as ta
        result = ta.run_audit()
        assert any("breakeven" in c.lower() for c in result["ok_checks"])

    def test_05_trailing_logic_verified(self):
        import scripts.audit.demo_micro_trailing_readiness_audit as ta
        result = ta.run_audit()
        assert any("trailing" in c.lower() for c in result["ok_checks"])

    def test_06_favorable_direction_verified(self):
        import scripts.audit.demo_micro_trailing_readiness_audit as ta
        result = ta.run_audit()
        assert any("favorable" in c.lower() for c in result["ok_checks"])
