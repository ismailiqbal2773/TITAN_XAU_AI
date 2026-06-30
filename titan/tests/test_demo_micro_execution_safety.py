"""TITAN XAU AI - Sprint 9.9.3.44 Demo Micro Execution Safety Tests"""
from __future__ import annotations
import re, sys
from pathlib import Path
import pytest
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

class TestSafety:
    def _strip(self, src):
        src = re.sub(r'"""[\s\S]*?"""','""',src); src = re.sub(r"'''[\s\S]*?'''","''",src)
        src = re.sub(r'r"[^"]*"','""',src); src = re.sub(r"r'[^']*'","''",src)
        src = re.sub(r'"(?:[^"\\]|\\.)*"','""',src); src = re.sub(r"'(?:[^'\\]|\\.)*'","''",src)
        lines = [line.split("#")[0] if "#" in line else line for line in src.splitlines()]
        return "\n".join(lines)

    def test_01_no_order_send_in_gate(self):
        src = (REPO_ROOT / "titan" / "production" / "demo_micro_execution_gate.py").read_text()
        code = self._strip(src)
        assert not re.search(r"\bmt5\.order_send\s*\(", code)

    def test_02_no_order_send_in_order_builder(self):
        src = (REPO_ROOT / "titan" / "production" / "demo_micro_order_builder.py").read_text()
        code = self._strip(src)
        assert not re.search(r"\bmt5\.order_send\s*\(", code)

    def test_03_no_order_send_in_operator_script(self):
        src = (REPO_ROOT / "scripts" / "operator" / "run_controlled_demo_micro_execution.py").read_text()
        code = self._strip(src)
        assert not re.search(r"\bmt5\.order_send\s*\(", code)

    def test_04_no_order_send_in_force_close(self):
        src = (REPO_ROOT / "scripts" / "operator" / "check_demo_micro_force_close_readiness.py").read_text()
        code = self._strip(src)
        assert not re.search(r"\bmt5\.order_send\s*\(", code)

    def test_05_no_demo_micro_execute_in_any_new_file(self):
        files = [
            "titan/production/demo_micro_execution_gate.py",
            "titan/production/demo_micro_order_builder.py",
            "scripts/operator/run_controlled_demo_micro_execution.py",
            "scripts/operator/check_demo_micro_force_close_readiness.py",
        ]
        for rel in files:
            src = (REPO_ROOT / rel).read_text()
            code = self._strip(src)
            assert not re.search(r"(?<!['\"])\b(DEMO_MICRO_EXECUTE|run_demo_micro)\s*\(", code), f"{rel}"

    def test_06_no_raw_mt5_probe_in_any_new_file(self):
        files = [
            "titan/production/demo_micro_execution_gate.py",
            "titan/production/demo_micro_order_builder.py",
            "scripts/operator/run_controlled_demo_micro_execution.py",
            "scripts/operator/check_demo_micro_force_close_readiness.py",
        ]
        for rel in files:
            src = (REPO_ROOT / rel).read_text()
            code = self._strip(src)
            assert not re.search(r"(?<!['\"])\b(run_raw_probe|raw_mt5_probe)\s*\(", code), f"{rel}"

    def test_07_no_market_execution_adapter_in_any_new_file(self):
        files = [
            "titan/production/demo_micro_execution_gate.py",
            "titan/production/demo_micro_order_builder.py",
        ]
        for rel in files:
            src = (REPO_ROOT / rel).read_text()
            code = self._strip(src)
            assert "MT5ExecutionAdapter()" not in code, f"{rel}"

    def test_08_no_metatrader5_import_in_any_new_file(self):
        files = [
            "titan/production/demo_micro_execution_gate.py",
            "titan/production/demo_micro_order_builder.py",
            "scripts/operator/run_controlled_demo_micro_execution.py",
            "scripts/operator/check_demo_micro_force_close_readiness.py",
        ]
        for rel in files:
            src = (REPO_ROOT / rel).read_text()
            assert "import MetaTrader5" not in src and "from MetaTrader5" not in src, f"{rel}"

    def test_09_no_martingale_grid_averaging(self):
        files = [
            "titan/production/demo_micro_execution_gate.py",
            "titan/production/demo_micro_order_builder.py",
        ]
        for rel in files:
            src = (REPO_ROOT / rel).read_text()
            code = self._strip(src).lower()
            assert "martingale" not in code or "no martingale" in code
            assert "grid_trading" not in code
            assert "averaging_down" not in code

    def test_10_runbook_exists(self):
        assert (REPO_ROOT / "docs" / "operator" / "controlled_demo_micro_execution_runbook.md").exists()

    def test_11_runbook_has_safety_rules(self):
        src = (REPO_ROOT / "docs" / "operator" / "controlled_demo_micro_execution_runbook.md").read_text()
        assert "MetaQuotes-Demo only" in src
        assert "max lot 0.01" in src.lower() or "0.01" in src
        assert "no martingale" in src.lower()
        assert "Z AI must NOT execute" in src or "Z AI must not execute" in src
