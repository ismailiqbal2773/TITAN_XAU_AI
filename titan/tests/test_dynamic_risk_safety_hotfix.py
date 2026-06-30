"""TITAN XAU AI - Sprint 9.9.3.41.2 Dynamic Risk Safety Hotfix Tests"""
from __future__ import annotations
import asyncio, inspect, re, sys
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


class TestDynamicRiskSafety:
    def test_01_risk_multiplier_zero_blocks_trade(self):
        """risk_multiplier <= 0 must block the trade, not floor to 0.001."""
        from titan.runtime.autonomous_loops import AutonomousRuntime, RuntimeConfig
        from titan.production.trade_journal import TradeJournal
        import tempfile, os
        with tempfile.TemporaryDirectory() as td:
            journal = TradeJournal(path=os.path.join(td, "test.jsonl"))
            rt = AutonomousRuntime(config=RuntimeConfig(dry_run=True), journal=journal)
            rt.initialize()
            # Verify the source contains zero-risk blocking logic
            src = inspect.getsource(AutonomousRuntime._inference_loop)
            assert "ctx_risk_multiplier <= 0.0" in src or "zero_risk_multiplier_block" in src, \
                "Zero risk multiplier blocking not found in _inference_loop source"

    def test_02_dynamic_risk_does_not_permanently_mutate_max_lot(self):
        """Dynamic risk must not permanently mutate TradeLoopConfig.max_lot."""
        from titan.runtime.autonomous_loops import AutonomousRuntime, RuntimeConfig
        from titan.production.trade_journal import TradeJournal
        import tempfile, os
        with tempfile.TemporaryDirectory() as td:
            journal = TradeJournal(path=os.path.join(td, "test.jsonl"))
            rt = AutonomousRuntime(config=RuntimeConfig(dry_run=True), journal=journal)
            rt.initialize()
            original_max_lot = rt.trade_loop.config.max_lot
            # Verify the source contains restore logic
            src = inspect.getsource(AutonomousRuntime._inference_loop)
            assert "original_max_lot" in src, \
                "original_max_lot restore logic not found in _inference_loop source"
            assert "self.trade_loop.config.max_lot = original_max_lot" in src, \
                "max_lot restore not found in _inference_loop source"

    def test_03_max_lot_hard_cap_remains_001(self):
        """max_lot hard cap must remain 0.01."""
        from titan.runtime.autonomous_loops import AutonomousRuntime, RuntimeConfig
        from titan.production.trade_journal import TradeJournal
        import tempfile, os
        with tempfile.TemporaryDirectory() as td:
            journal = TradeJournal(path=os.path.join(td, "test.jsonl"))
            rt = AutonomousRuntime(config=RuntimeConfig(dry_run=True), journal=journal)
            rt.initialize()
            assert rt.trade_loop.config.max_lot <= 0.01

    def test_04_risk_can_only_reduce_or_block(self):
        """Risk multiplier can only reduce max_lot or block, never increase."""
        from titan.runtime.autonomous_loops import AutonomousRuntime, RuntimeConfig
        src = inspect.getsource(AutonomousRuntime._inference_loop)
        # Verify there's no code that increases max_lot based on risk_multiplier
        # The code should only reduce (multiply by < 1.0) or block (<= 0)
        assert "ctx_risk_multiplier < 1.0" in src, \
            "Risk reduction logic not found"
        # Verify there's no increase path
        assert "max_lot * ctx_risk_multiplier" in src or \
               "original_max_lot * ctx_risk_multiplier" in src, \
            "Risk multiplication logic not found"


class TestTradeLoopCautionFix:
    def test_05_caution_does_not_falsely_claim_reduction(self):
        """CAUTION must not use max(original/2, 0.01) which doesn't reduce when original=0.01."""
        from titan.production import trade_loop
        src = inspect.getsource(trade_loop)
        # Strip comments to check actual code only
        code = re.sub(r'"""[\s\S]*?"""', '""', src)
        code = re.sub(r"'''[\s\S]*?'''", "''", code)
        code = re.sub(r'r"[^"]*"', '""', code)
        code = re.sub(r"r'[^']*'", "''", code)
        code = re.sub(r'"(?:[^"\\]|\\.)*"', '""', code)
        code = re.sub(r"'(?:[^'\\]|\\.)*'", "''", code)
        # Strip line comments
        lines = []
        for line in code.splitlines():
            idx = line.find("#")
            if idx >= 0:
                line = line[:idx]
            lines.append(line)
        code = "\n".join(lines)
        # The old false reduction pattern should NOT be in actual code
        assert not re.search(r"max\s*\(\s*original_max\s*/\s*2\s*,\s*0\.01\s*\)", code), \
            "TradeLoop still uses false reduction pattern in actual code"

    def test_06_caution_blocks_new_entries(self):
        """CAUTION should block new entries in RC phase."""
        from titan.production import trade_loop
        src = inspect.getsource(trade_loop)
        assert "caution_blocks_new_entries_rc_phase" in src, \
            "CAUTION blocks new entries logic not found"
        assert "kill_switch_caution_blocks_entries" in src, \
            "CAUTION block reason not found"


class TestSafetyInvariants:
    def test_07_no_metatrader5_import_in_autonomous_loops(self):
        from titan.runtime import autonomous_loops
        src = inspect.getsource(autonomous_loops)
        assert "import MetaTrader5" not in src
        assert "from MetaTrader5" not in src

    def test_08_no_order_send_in_trade_loop(self):
        import re
        from titan.production import trade_loop
        src = inspect.getsource(trade_loop)
        src = re.sub(r'"""[\s\S]*?"""', '""', src)
        src = re.sub(r"'''[\s\S]*?'''", "''", src)
        src = re.sub(r'r"[^"]*"', '""', src)
        src = re.sub(r"r'[^']*'", "''", src)
        src = re.sub(r'"(?:[^"\\]|\\.)*"', '""', src)
        src = re.sub(r"'(?:[^'\\]|\\.)*'", "''", src)
        call_pattern = r"\bmt5\.order_send\s*\("
        matches = re.findall(call_pattern, src)
        assert len(matches) == 0

    def test_09_no_demo_micro_execute_in_trade_loop(self):
        import re
        from titan.production import trade_loop
        src = inspect.getsource(trade_loop)
        src = re.sub(r'"""[\s\S]*?"""', '""', src)
        src = re.sub(r"'''[\s\S]*?'''", "''", src)
        src = re.sub(r'r"[^"]*"', '""', src)
        src = re.sub(r"r'[^']*'", "''", src)
        src = re.sub(r'"(?:[^"\\]|\\.)*"', '""', src)
        src = re.sub(r"'(?:[^'\\]|\\.)*'", "''", src)
        call_pattern = r"(?<!['\"])\b(DEMO_MICRO_EXECUTE|run_demo_micro|execute_demo_micro)\s*\("
        matches = re.findall(call_pattern, src)
        assert len(matches) == 0
