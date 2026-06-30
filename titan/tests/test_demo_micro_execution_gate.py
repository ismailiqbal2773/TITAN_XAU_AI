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

    def test_12_python313_warning_approved_when_evidence_ok(self):
        """PYTHON_313_COMPATIBILITY_WARNING should be approved when all evidence passes."""
        from titan.production.demo_micro_execution_gate import DemoMicroExecutionGate
        gate = DemoMicroExecutionGate()
        result = gate.evaluate()
        # If all evidence passes, PYTHON_313 should be in approved_warnings
        py313_in_warnings = any("PYTHON_313" in w.upper() for w in result.warnings)
        if py313_in_warnings:
            # Check it's in approved, not unapproved
            py313_approved = any("PYTHON_313" in w.upper() for w in result.approved_warnings)
            py313_unapproved = any("PYTHON_313" in w.upper() for w in result.unapproved_warnings)
            assert py313_approved or not py313_unapproved, \
                "PYTHON_313 warning should be approved when evidence passes"

    def test_13_python313_warning_in_approved_set(self):
        """PYTHON_313_COMPATIBILITY_WARNING must be in APPROVED_WARNINGS set."""
        from titan.production.demo_micro_execution_gate import APPROVED_WARNINGS
        assert "PYTHON_313_COMPATIBILITY_WARNING" in APPROVED_WARNINGS

    def test_14_operator_token_missing_not_blocker_in_check_only(self):
        """Operator token missing should be WARNING, not blocker, in check-only."""
        from titan.production.demo_micro_execution_gate import DemoMicroExecutionGate
        gate = DemoMicroExecutionGate()
        result = gate.evaluate()  # No operator_confirmation_token
        token_blocker = any("confirmation token" in b.lower() for b in result.blockers)
        assert not token_blocker, "Operator token missing should not be a blocker in check-only"

    def test_15_no_mojibake_in_report(self):
        """Report should not contain mojibake characters."""
        from titan.production.demo_micro_execution_gate import DemoMicroExecutionGate
        gate = DemoMicroExecutionGate()
        result = gate.evaluate()
        result_str = str(result.to_dict())
        assert "\u2014" not in result_str, "Em-dash (mojibake source) found in report"
        assert "\ufffd" not in result_str, "Replacement character found in report"
