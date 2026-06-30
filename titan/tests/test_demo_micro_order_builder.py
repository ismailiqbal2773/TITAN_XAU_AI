"""TITAN XAU AI - Sprint 9.9.3.44.2 Demo Micro Order Builder Tests"""
from __future__ import annotations
import inspect, json, re, sys
from pathlib import Path
import pytest
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
from titan.production.demo_micro_order_builder import DemoMicroOrderBuilder
from titan.production.demo_micro_sl_tp_safety import DemoMicroSLTPSafety, SLTPVerdict

class TestOrderBuilder:
    def test_01_creates_preview_with_valid_sl_tp(self):
        builder = DemoMicroOrderBuilder()
        result = builder.build_preview(direction="BUY", entry_price=2000.0, sl=1990.0, tp=2010.0)
        assert result["verdict"] == "PASS"
        assert result["executable_status"] == "EXECUTABLE_WITH_PROTECTIVE_SL_TP"
        assert result["preview"]["has_sl"] is True
        assert result["preview"]["has_tp"] is True

    def test_02_sl0_tp0_is_preview_only_not_executable(self):
        builder = DemoMicroOrderBuilder()
        result = builder.build_preview(direction="BUY", entry_price=2000.0, sl=0.0, tp=0.0, safe_fallback=True, fallback_reason="dry_run_preview_mode")
        assert result["executable_status"] == "PREVIEW_ONLY_NOT_EXECUTABLE"
        assert result["preview"]["has_sl"] is False
        assert result["preview"]["has_tp"] is False

    def test_03_blocks_missing_sl_tp_without_fallback(self):
        builder = DemoMicroOrderBuilder()
        result = builder.build_preview(direction="BUY", entry_price=2000.0, sl=0.0, tp=0.0, safe_fallback=False)
        assert result["verdict"] == "BLOCKED"

    def test_04_lot_capped_at_001(self):
        builder = DemoMicroOrderBuilder()
        result = builder.build_preview(direction="BUY", entry_price=2000.0, sl=1990.0, tp=2010.0)
        assert result["preview"]["volume"] <= 0.01

    def test_05_no_order_send(self):
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
        import titan.production.demo_micro_order_builder as mod
        old_dir = mod.OUTPUT_DIR; mod.OUTPUT_DIR = tmp_path
        try:
            result = builder.build_preview(direction="BUY", entry_price=2000.0, sl=1990.0, tp=2010.0)
            report = builder.write_preview(result)
            assert Path(report["json_path"]).exists()
            assert Path(report["md_path"]).exists()
        finally:
            mod.OUTPUT_DIR = old_dir

    def test_08_no_mojibake_in_md(self, tmp_path):
        builder = DemoMicroOrderBuilder()
        import titan.production.demo_micro_order_builder as mod
        old_dir = mod.OUTPUT_DIR; mod.OUTPUT_DIR = tmp_path
        try:
            result = builder.build_preview(direction="BUY", entry_price=2000.0, sl=1990.0, tp=2010.0)
            report = builder.write_preview(result)
            md = Path(report["md_path"]).read_text(encoding="utf-8")
            assert "\u2014" not in md
            assert "\ufffd" not in md
        finally:
            mod.OUTPUT_DIR = old_dir

class TestSLTPSafety:
    def test_09_buy_sl_below_entry_tp_above(self):
        safety = DemoMicroSLTPSafety()
        result = safety.validate_or_compute(direction="BUY", entry_price=2000.0, sl=1990.0, tp=2010.0)
        assert result.verdict == SLTPVerdict.SLTP_VALID
        assert result.sl < 2000.0
        assert result.tp > 2000.0

    def test_10_sell_sl_above_entry_tp_below(self):
        safety = DemoMicroSLTPSafety()
        result = safety.validate_or_compute(direction="SELL", entry_price=2000.0, sl=2010.0, tp=1990.0)
        assert result.verdict == SLTPVerdict.SLTP_VALID
        assert result.sl > 2000.0
        assert result.tp < 2000.0

    def test_11_buy_sl_above_entry_blocks(self):
        safety = DemoMicroSLTPSafety()
        result = safety.validate_or_compute(direction="BUY", entry_price=2000.0, sl=2010.0, tp=1990.0)
        assert result.verdict == SLTPVerdict.SLTP_BLOCKED

    def test_12_atr_fallback_creates_valid_sl_tp(self):
        safety = DemoMicroSLTPSafety()
        result = safety.validate_or_compute(direction="BUY", entry_price=2000.0, sl=0.0, tp=0.0, atr=5.0)
        assert result.verdict == SLTPVerdict.SLTP_ATR_FALLBACK_USED
        assert result.has_sl is True
        assert result.has_tp is True
        assert result.sl < 2000.0
        assert result.tp > 2000.0

    def test_13_atr_missing_blocks(self):
        safety = DemoMicroSLTPSafety()
        result = safety.validate_or_compute(direction="BUY", entry_price=2000.0, sl=0.0, tp=0.0, atr=0.0)
        assert result.verdict == SLTPVerdict.SLTP_BLOCKED

    def test_14_entry_price_missing_blocks(self):
        safety = DemoMicroSLTPSafety()
        result = safety.validate_or_compute(direction="BUY", entry_price=0.0, sl=0.0, tp=0.0, atr=5.0)
        assert result.verdict == SLTPVerdict.SLTP_BLOCKED
