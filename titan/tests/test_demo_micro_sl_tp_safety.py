"""TITAN XAU AI - Sprint 9.9.3.44.3 Demo Micro SL/TP Safety Tests"""
from __future__ import annotations
import inspect, json, re, sys
from pathlib import Path
import pytest
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
from titan.production.demo_micro_sl_tp_safety import DemoMicroSLTPSafety, SLTPVerdict

class TestProvidedSLTP:
    def test_01_buy_valid_sl_tp(self):
        s = DemoMicroSLTPSafety()
        r = s.validate_or_compute(direction="BUY", entry_price=2000.0, sl=1990.0, tp=2010.0)
        assert r.verdict == SLTPVerdict.SLTP_VALID
        assert r.sl < 2000.0 and r.tp > 2000.0

    def test_02_sell_valid_sl_tp(self):
        s = DemoMicroSLTPSafety()
        r = s.validate_or_compute(direction="SELL", entry_price=2000.0, sl=2010.0, tp=1990.0)
        assert r.verdict == SLTPVerdict.SLTP_VALID
        assert r.sl > 2000.0 and r.tp < 2000.0

    def test_03_buy_sl_above_entry_blocks(self):
        s = DemoMicroSLTPSafety()
        r = s.validate_or_compute(direction="BUY", entry_price=2000.0, sl=2010.0, tp=1990.0)
        assert r.verdict == SLTPVerdict.SLTP_BLOCKED

    def test_04_sell_sl_below_entry_blocks(self):
        s = DemoMicroSLTPSafety()
        r = s.validate_or_compute(direction="SELL", entry_price=2000.0, sl=1990.0, tp=2010.0)
        assert r.verdict == SLTPVerdict.SLTP_BLOCKED

class TestATRFallback:
    def test_05_atr_creates_valid_buy_sl_tp(self):
        s = DemoMicroSLTPSafety()
        r = s.validate_or_compute(direction="BUY", entry_price=2000.0, sl=0.0, tp=0.0, atr=5.0)
        assert r.verdict == SLTPVerdict.SLTP_ATR_FALLBACK_USED
        assert r.has_sl and r.has_tp
        assert r.sl < 2000.0 and r.tp > 2000.0

    def test_06_atr_creates_valid_sell_sl_tp(self):
        s = DemoMicroSLTPSafety()
        r = s.validate_or_compute(direction="SELL", entry_price=2000.0, sl=0.0, tp=0.0, atr=5.0)
        assert r.verdict == SLTPVerdict.SLTP_ATR_FALLBACK_USED
        assert r.has_sl and r.has_tp
        assert r.sl > 2000.0 and r.tp < 2000.0

class TestReferencePriceMissing:
    def test_07_entry_price_zero_blocks(self):
        s = DemoMicroSLTPSafety()
        r = s.validate_or_compute(direction="BUY", entry_price=0.0, sl=0.0, tp=0.0, atr=5.0)
        assert r.verdict == SLTPVerdict.SLTP_BLOCKED
        assert any("REFERENCE_PRICE_MISSING" in b for b in r.blockers)

class TestMT5TickFallback:
    def test_08_atr_unavailable_no_mt5_blocks(self):
        """Without MT5 installed, ATR unavailable should block.
        With MT5 mock (conftest), the tick fallback may succeed.
        Test verifies the function does not crash and returns a valid verdict."""
        s = DemoMicroSLTPSafety()
        r = s.validate_or_compute(direction="BUY", entry_price=2000.0, sl=0.0, tp=0.0, atr=0.0)
        # With MT5 mock, tick fallback may succeed -> MT5_TICK_FALLBACK_USED
        # Without MT5, blocks
        assert r.verdict in (SLTPVerdict.SLTP_BLOCKED, SLTPVerdict.SLTP_MT5_TICK_FALLBACK_USED)

    def test_09_mt5_tick_fallback_verdict_exists(self):
        """SLTP_MT5_TICK_FALLBACK_USED verdict must exist in enum."""
        assert hasattr(SLTPVerdict, "SLTP_MT5_TICK_FALLBACK_USED")

class TestNoUnsafeOps:
    def test_10_no_order_send_in_safety_module(self):
        src = inspect.getsource(DemoMicroSLTPSafety)
        code = re.sub(r'"""[\s\S]*?"""','""',src)
        code = re.sub(r'"(?:[^"\\]|\\.)*"','""',code)
        code = re.sub(r"'(?:[^'\\]|\\.)*'","''",code)
        assert not re.search(r"\bmt5\.order_send\s*\(", code)

    def test_11_no_demo_micro_execute(self):
        src = inspect.getsource(DemoMicroSLTPSafety)
        code = re.sub(r'"""[\s\S]*?"""','""',src)
        code = re.sub(r'"(?:[^"\\]|\\.)*"','""',code)
        code = re.sub(r"'(?:[^'\\]|\\.)*'","''",code)
        assert not re.search(r"(?<!['\"])\b(DEMO_MICRO_EXECUTE|run_demo_micro)\s*\(", code)

    def test_12_no_raw_mt5_probe(self):
        src = inspect.getsource(DemoMicroSLTPSafety)
        code = re.sub(r'"""[\s\S]*?"""','""',src)
        code = re.sub(r'"(?:[^"\\]|\\.)*"','""',code)
        code = re.sub(r"'(?:[^'\\]|\\.)*'","''",code)
        assert not re.search(r"(?<!['\"])\b(run_raw_probe|raw_mt5_probe)\s*\(", code)

    def test_13_no_mojibake(self):
        src = inspect.getsource(DemoMicroSLTPSafety)
        assert "\u2014" not in src
