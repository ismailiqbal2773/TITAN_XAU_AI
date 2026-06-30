"""TITAN XAU AI - Sprint 9.9.3.44 Controlled Demo Micro Execution Operator Tests"""
from __future__ import annotations
import inspect, json, re, sys
from pathlib import Path
import pytest
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

class TestOperator:
    def test_01_check_only_returns_result(self):
        import scripts.operator.run_controlled_demo_micro_execution as op
        result = op.run_check_only()
        assert "verdict" in result

    def test_02_dry_arm_does_not_send_order(self):
        import scripts.operator.run_controlled_demo_micro_execution as op
        result = op.run_dry_arm()
        assert result["mode"] == "dry_arm"
        assert "armed" in result
        # No order_send evidence
        assert "order_send" not in str(result).lower() or "blocked" in str(result).lower()

    def test_03_build_request_does_not_send_order(self):
        import scripts.operator.run_controlled_demo_micro_execution as op
        result = op.run_build_request(direction="BUY", entry_price=2000.0, sl=1990.0, tp=2010.0)
        assert result["mode"] == "build_request"
        assert "preview" in result

    def test_04_execute_once_refuses_without_confirmations(self):
        import scripts.operator.run_controlled_demo_micro_execution as op
        class FakeArgs:
            i_understand_demo_risk = False
            confirm_symbol = ""
            confirm_lot = 0.0
            confirm_broker = ""
            confirm_one_order_only = False
            confirm_not_live = False
            confirm_environment_locked = False
            confirm_model_parity_pass = False
        result = op.run_execute_once(FakeArgs())
        assert result["verdict"] == "DEMO_MICRO_EXECUTION_REFUSED"
        assert any("confirmation" in b.lower() for b in result["blockers"])

    def test_05_execute_once_refused_even_with_confirmations(self):
        """Z AI must NOT execute even with all confirmations."""
        import scripts.operator.run_controlled_demo_micro_execution as op
        class FakeArgs:
            i_understand_demo_risk = True
            confirm_symbol = "XAUUSD"
            confirm_lot = 0.01
            confirm_broker = "MetaQuotes-Demo"
            confirm_one_order_only = True
            confirm_not_live = True
            confirm_environment_locked = True
            confirm_model_parity_pass = True
        result = op.run_execute_once(FakeArgs())
        assert result["verdict"] == "DEMO_MICRO_EXECUTION_REFUSED"
        assert any("Z AI" in b or "prohibition" in b.lower() for b in result["blockers"])

    def test_06_no_order_send_in_operator_script(self):
        src = (REPO_ROOT / "scripts" / "operator" / "run_controlled_demo_micro_execution.py").read_text()
        code = re.sub(r'"""[\s\S]*?"""','""',src)
        code = re.sub(r'"(?:[^"\\]|\\.)*"','""',code)
        code = re.sub(r"'(?:[^'\\]|\\.)*'","''",code)
        assert not re.search(r"\bmt5\.order_send\s*\(", code)

    def test_07_no_metatrader5_import(self):
        src = (REPO_ROOT / "scripts" / "operator" / "run_controlled_demo_micro_execution.py").read_text()
        assert "import MetaTrader5" not in src and "from MetaTrader5" not in src

    def test_08_no_demo_micro_execute(self):
        src = (REPO_ROOT / "scripts" / "operator" / "run_controlled_demo_micro_execution.py").read_text()
        code = re.sub(r'"""[\s\S]*?"""','""',src)
        code = re.sub(r'"(?:[^"\\]|\\.)*"','""',code)
        code = re.sub(r"'(?:[^'\\]|\\.)*'","''",code)
        assert not re.search(r"(?<!['\"])\b(DEMO_MICRO_EXECUTE|run_demo_micro)\s*\(", code)
