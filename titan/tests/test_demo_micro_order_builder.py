"""TITAN XAU AI - Sprint 9.9.3.44 Demo Micro Order Builder Tests"""
from __future__ import annotations
import inspect, json, re, sys
from pathlib import Path
import pytest
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
from titan.production.demo_micro_order_builder import DemoMicroOrderBuilder

class TestOrderBuilder:
    def test_01_creates_preview(self):
        builder = DemoMicroOrderBuilder()
        result = builder.build_preview(direction="BUY", sl=1990.0, tp=2010.0)
        assert "preview" in result
        assert result["preview"]["symbol"] == "XAUUSD"
        assert result["preview"]["volume"] <= 0.01

    def test_02_blocks_missing_sl_tp_without_fallback(self):
        builder = DemoMicroOrderBuilder()
        result = builder.build_preview(direction="BUY", sl=0.0, tp=0.0, safe_fallback=False)
        assert result["verdict"] == "BLOCKED"
        assert any("SL/TP" in b for b in result["blockers"])

    def test_03_allows_missing_sl_tp_with_fallback(self):
        builder = DemoMicroOrderBuilder()
        result = builder.build_preview(direction="BUY", sl=0.0, tp=0.0, safe_fallback=True, fallback_reason="test")
        assert result["verdict"] == "PASS"
        assert result["preview"]["safe_fallback_used"] is True

    def test_04_lot_capped_at_001(self):
        builder = DemoMicroOrderBuilder()
        result = builder.build_preview(direction="BUY", sl=1990.0, tp=2010.0)
        assert result["preview"]["volume"] <= 0.01

    def test_05_no_order_send_in_builder(self):
        src = inspect.getsource(DemoMicroOrderBuilder)
        code = re.sub(r'"""[\s\S]*?"""','""',src)
        code = re.sub(r'"(?:[^"\\]|\\.)*"','""',code)
        code = re.sub(r"'(?:[^'\\]|\\.)*'","''",code)
        assert not re.search(r"\bmt5\.order_send\s*\(", code)

    def test_06_no_market_execution_adapter(self):
        src = inspect.getsource(DemoMicroOrderBuilder)
        code = re.sub(r'"""[\s\S]*?"""','""',src)
        code = re.sub(r'"(?:[^"\\]|\\.)*"','""',code)
        code = re.sub(r"'(?:[^'\\]|\\.)*'","''",code)
        assert "MT5ExecutionAdapter()" not in code

    def test_07_writes_preview(self, tmp_path):
        builder = DemoMicroOrderBuilder()
        old = builder.OUTPUT_DIR if hasattr(builder, 'OUTPUT_DIR') else None
        import titan.production.demo_micro_order_builder as mod
        old_dir = mod.OUTPUT_DIR; mod.OUTPUT_DIR = tmp_path
        try:
            result = builder.build_preview(direction="BUY", sl=1990.0, tp=2010.0)
            report = builder.write_preview(result)
            assert Path(report["json_path"]).exists()
            assert Path(report["md_path"]).exists()
        finally:
            mod.OUTPUT_DIR = old_dir
