"""TITAN XAU AI - Sprint 9.9.3.44 Demo Micro Execution Gate Tests"""
from __future__ import annotations
import inspect, json, re, sys
from pathlib import Path
import pytest
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
from titan.production.demo_micro_execution_gate import DemoMicroExecutionGate, DemoMicroGateVerdict

class TestGate:
    def test_01_blocks_live_trading_true(self):
        gate = DemoMicroExecutionGate()
        result = gate.evaluate(live_trading=True)
        assert result.verdict == DemoMicroGateVerdict.DEMO_MICRO_GATE_BLOCKED
        assert any("live_trading" in b for b in result.blockers)

    def test_02_blocks_real_account(self):
        gate = DemoMicroExecutionGate()
        result = gate.evaluate(account_type="REAL")
        assert result.verdict == DemoMicroGateVerdict.DEMO_MICRO_GATE_BLOCKED
        assert any("REAL" in b for b in result.blockers)

    def test_03_blocks_fundednext(self):
        gate = DemoMicroExecutionGate()
        result = gate.evaluate(broker_name="FundedNext Free Trial")
        assert result.verdict == DemoMicroGateVerdict.DEMO_MICRO_GATE_BLOCKED

    def test_04_blocks_fbs(self):
        gate = DemoMicroExecutionGate()
        result = gate.evaluate(broker_name="FBS-Demo")
        assert result.verdict == DemoMicroGateVerdict.DEMO_MICRO_GATE_BLOCKED

    def test_05_blocks_unknown_broker(self):
        gate = DemoMicroExecutionGate()
        result = gate.evaluate(broker_name="UnknownBroker")
        assert result.verdict == DemoMicroGateVerdict.DEMO_MICRO_GATE_BLOCKED

    def test_06_allows_metaquotes(self):
        gate = DemoMicroExecutionGate()
        result = gate.evaluate(broker_name="MetaQuotes-Demo")
        # May have warnings but should not be blocked for broker reason
        assert all("FundedNext" not in b and "FBS" not in b for b in result.blockers)

    def test_07_blocks_lot_above_001(self):
        gate = DemoMicroExecutionGate()
        result = gate.evaluate(requested_lot=0.10)
        assert result.verdict == DemoMicroGateVerdict.DEMO_MICRO_GATE_BLOCKED
        assert any("lot" in b.lower() for b in result.blockers)

    def test_08_blocks_open_positions_above_0(self):
        gate = DemoMicroExecutionGate()
        result = gate.evaluate(current_open_positions=1)
        assert result.verdict == DemoMicroGateVerdict.DEMO_MICRO_GATE_BLOCKED
        assert any("open_positions" in b.lower() or "positions" in b.lower() for b in result.blockers)

    def test_09_blocks_max_positions_above_1(self):
        gate = DemoMicroExecutionGate()
        result = gate.evaluate(max_open_positions=5)
        assert result.verdict == DemoMicroGateVerdict.DEMO_MICRO_GATE_BLOCKED

    def test_10_no_metatrader5_import(self):
        from titan.production import demo_micro_execution_gate
        src = inspect.getsource(demo_micro_execution_gate)
        assert "import MetaTrader5" not in src and "from MetaTrader5" not in src

    def test_11_no_order_send(self):
        import re
        from titan.production import demo_micro_execution_gate
        src = inspect.getsource(demo_micro_execution_gate)
        code = re.sub(r'"""[\s\S]*?"""','""',src)
        code = re.sub(r'"(?:[^"\\]|\\.)*"','""',code)
        code = re.sub(r"'(?:[^'\\]|\\.)*'","''",code)
        assert not re.search(r"\bmt5\.order_send\s*\(", code)
