"""TITAN XAU AI - Sprint 9.9.3.45 SL Modify Builder Tests"""
from __future__ import annotations
import inspect, re, sys
from pathlib import Path
import pytest
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
from titan.production.demo_micro_sl_modify_builder import DemoMicroSLModifyBuilder

class TestSLModifyBuilder:
    def test_01_builds_preview(self):
        b = DemoMicroSLModifyBuilder()
        result = b.build_preview(ticket=12345, new_sl=2001.0, tp=2010.0, favorable=True)
        assert result["verdict"] == "PASS"
        assert result["preview"]["new_sl"] == 2001.0
        assert result["preview"]["tp"] == 2010.0

    def test_02_blocks_unfavorable(self):
        b = DemoMicroSLModifyBuilder()
        result = b.build_preview(ticket=12345, new_sl=2001.0, tp=2010.0, favorable=False)
        assert result["verdict"] == "BLOCKED"
        assert any("favorable" in bl.lower() for bl in result["blockers"])

    def test_03_blocks_invalid_ticket(self):
        b = DemoMicroSLModifyBuilder()
        result = b.build_preview(ticket=0, new_sl=2001.0, tp=2010.0, favorable=True)
        assert result["verdict"] == "BLOCKED"

    def test_04_blocks_sl_zero(self):
        b = DemoMicroSLModifyBuilder()
        result = b.build_preview(ticket=12345, new_sl=0.0, tp=2010.0, favorable=True)
        assert result["verdict"] == "BLOCKED"

    def test_05_blocks_tp_zero(self):
        b = DemoMicroSLModifyBuilder()
        result = b.build_preview(ticket=12345, new_sl=2001.0, tp=0.0, favorable=True)
        assert result["verdict"] == "BLOCKED"

    def test_06_tp_preserved(self):
        b = DemoMicroSLModifyBuilder()
        result = b.build_preview(ticket=12345, new_sl=2001.0, tp=2010.0, favorable=True)
        assert result["preview"]["tp"] == 2010.0

    def test_07_no_order_send(self):
        src = inspect.getsource(DemoMicroSLModifyBuilder)
        code = re.sub(r'"""[\s\S]*?"""','""',src)
        code = re.sub(r'"(?:[^"\\]|\\.)*"','""',code)
        code = re.sub(r"'(?:[^'\\]|\\.)*'","''",code)
        assert not re.search(r"\bmt5\.order_send\s*\(", code)
