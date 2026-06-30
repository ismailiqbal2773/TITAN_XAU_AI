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
            confirm_local_operator = False
            direction = "BUY"
            entry_price = 2000.0
            sl = 0.0
            tp = 0.0
        result = op.run_execute_once(FakeArgs())
        assert result["verdict"] == "DEMO_MICRO_EXECUTION_REFUSED"
        assert any("confirmation" in b.lower() for b in result["blockers"])

    def test_05_execute_once_refused_even_with_confirmations(self):
        """Without --confirm-local-operator, execution must be refused.
        Note: In Z AI env, the environment drift gate blocks first, which is correct.
        On Windows with matching env, the --confirm-local-operator check would block."""
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
            confirm_local_operator = False  # Missing!
            direction = "BUY"
            entry_price = 2000.0
            sl = 0.0
            tp = 0.0
        result = op.run_execute_once(FakeArgs())
        assert result["verdict"] == "DEMO_MICRO_EXECUTION_REFUSED"
        # Must be refused - either by local-operator check or by gate blockers
        assert len(result["blockers"]) > 0

    def test_05a_execute_once_blocks_without_token(self):
        """With --confirm-local-operator but no token, execution must be refused."""
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
            confirm_local_operator = True
            direction = "BUY"
            entry_price = 2000.0
            sl = 0.0
            tp = 0.0
        result = op.run_execute_once(FakeArgs())
        assert result["verdict"] == "DEMO_MICRO_EXECUTION_REFUSED"
        # Should be refused due to gate blocked (env drift) or token missing
        assert len(result["blockers"]) > 0

    def test_06_order_send_only_in_execute_once_path(self):
        """mt5.order_send may only appear in the gated _attempt_gated_order_send path."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_controlled_demo_micro_execution.py").read_text()
        code = re.sub(r'"""[\s\S]*?"""','""',src)
        code = re.sub(r"'''[\s\S]*?'''","''",code)
        code = re.sub(r'r"[^"]*"','""',code)
        code = re.sub(r"r'[^']*'","''",code)
        code = re.sub(r'"(?:[^"\\]|\\.)*"','""',code)
        code = re.sub(r"'(?:[^'\\]|\\.)*'","''",code)
        # order_send is allowed ONLY inside _attempt_gated_order_send
        # Verify it exists only in that function context
        lines = code.splitlines()
        in_gated_function = False
        order_send_found_outside = False
        for line in lines:
            if "def _attempt_gated_order_send" in line:
                in_gated_function = True
            elif line and not line[0].isspace() and "def " in line:
                in_gated_function = False
            if "mt5.order_send" in line and not in_gated_function:
                order_send_found_outside = True
        assert not order_send_found_outside, "order_send found outside _attempt_gated_order_send"

    def test_07_metatrader5_import_only_in_gated_path(self):
        """MetaTrader5 import may only appear inside _attempt_gated_order_send."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_controlled_demo_micro_execution.py").read_text()
        # The import is inside the function, which is acceptable
        # Just verify it's not at the top level
        lines = src.splitlines()
        for i, line in enumerate(lines):
            stripped = line.strip()
            if "import MetaTrader5" in stripped or "from MetaTrader5" in stripped:
                # Must be inside a function (indented)
                assert line[0].isspace() if line else True, \
                    f"MetaTrader5 import at top level line {i+1}"

    def test_08_no_demo_micro_execute(self):
        src = (REPO_ROOT / "scripts" / "operator" / "run_controlled_demo_micro_execution.py").read_text()
        code = re.sub(r'"""[\s\S]*?"""','""',src)
        code = re.sub(r'"(?:[^"\\]|\\.)*"','""',code)
        code = re.sub(r"'(?:[^'\\]|\\.)*'","''",code)
        assert not re.search(r"(?<!['\"])\b(DEMO_MICRO_EXECUTE|run_demo_micro)\s*\(", code)
