"""TITAN XAU AI - Sprint 9.9.3.45.2 Managed Demo Micro Trade Operator Tests"""
from __future__ import annotations
import re, sys
from pathlib import Path
import pytest
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

class TestManagedOperator:
    def test_01_check_only_returns_result(self):
        import scripts.operator.run_managed_demo_micro_trade as mt
        result = mt.run_check_only()
        assert "verdict" in result and result["mode"] == "check_only"

    def test_02_dry_arm_returns_result(self):
        import scripts.operator.run_managed_demo_micro_trade as mt
        result = mt.run_dry_arm()
        assert "verdict" in result and result["mode"] == "dry_arm"

    def test_03_build_request_returns_result(self):
        import scripts.operator.run_managed_demo_micro_trade as mt
        result = mt.run_build_request(direction="BUY", entry_price=2000.0, sl=1990.0, tp=2010.0)
        assert "verdict" in result and result["mode"] == "build_request"

    def test_04_execute_blocks_without_confirm_managed_trailing(self):
        import scripts.operator.run_managed_demo_micro_trade as mt
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
            confirm_managed_trailing = False
        result = mt.run_execute_and_monitor(FakeArgs())
        assert result["verdict"] == "MANAGED_DEMO_MICRO_BLOCKED"
        assert any("confirmation" in b.lower() for b in result["blockers"])

    def test_05_execute_blocks_without_token(self):
        import scripts.operator.run_managed_demo_micro_trade as mt
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
            confirm_managed_trailing = True
        result = mt.run_execute_and_monitor(FakeArgs())
        assert result["verdict"] == "MANAGED_DEMO_MICRO_BLOCKED"

    def test_06_order_send_only_in_execute_path(self):
        """order_send may only appear inside run_execute_and_monitor."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        code = re.sub(r'"""[\s\S]*?"""','""',src)
        code = re.sub(r'"(?:[^"\\]|\\.)*"','""',code)
        code = re.sub(r"'(?:[^'\\]|\\.)*'","''",code)
        lines = code.splitlines()
        in_execute = False
        for line in lines:
            if "def run_execute_and_monitor" in line:
                in_execute = True
            elif line and not line[0].isspace() and "def " in line:
                in_execute = False
            if "mt5.order_send" in line and not in_execute:
                pytest.fail(f"order_send found outside run_execute_and_monitor: {line.strip()}")

    def test_07_no_demo_micro_execute(self):
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        code = re.sub(r'"""[\s\S]*?"""','""',src)
        code = re.sub(r'"(?:[^"\\]|\\.)*"','""',code)
        code = re.sub(r"'(?:[^'\\]|\\.)*'","''",code)
        assert not re.search(r"(?<!['\"])\b(DEMO_MICRO_EXECUTE|run_demo_micro)\s*\(", code)

    def test_08_no_raw_mt5_probe(self):
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        code = re.sub(r'"""[\s\S]*?"""','""',src)
        code = re.sub(r'"(?:[^"\\]|\\.)*"','""',code)
        code = re.sub(r"'(?:[^'\\]|\\.)*'","''",code)
        assert not re.search(r"(?<!['\"])\b(run_raw_probe|raw_mt5_probe)\s*\(", code)
