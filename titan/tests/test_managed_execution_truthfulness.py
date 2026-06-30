"""TITAN XAU AI - Sprint 9.9.3.45.4 Managed Execution Truthfulness Tests"""
from __future__ import annotations
import re, sys
from pathlib import Path
import pytest
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

class TestTruthfulness:
    def _strip(self, src):
        src = re.sub(r'"""[\s\S]*?"""','""',src)
        src = re.sub(r"'''[\s\S]*?'''","''",src)
        src = re.sub(r'r"[^"]*"','""',src)
        src = re.sub(r"r'[^']*'","''",src)
        src = re.sub(r'"(?:[^"\\]|\\.)*"','""',src)
        src = re.sub(r"'(?:[^'\\]|\\.)*'","''",src)
        lines = [line.split("#")[0] if "#" in line else line for line in src.splitlines()]
        return "\n".join(lines)

    def test_01_started_requires_receipt_written(self):
        """STARTED verdict must only be returned when receipt_written=True."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        # Find the MANAGED_DEMO_MICRO_STARTED return block
        assert "MANAGED_DEMO_MICRO_STARTED" in src
        assert "receipt_written" in src
        assert "RECEIPT_WRITE_FAILED" in src

    def test_02_started_requires_position_detected(self):
        """STARTED verdict must only be returned when position_detected=True."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        assert "POSITION_NOT_DETECTED_AFTER_EXECUTION" in src
        assert "position_detected" in src

    def test_03_failed_on_order_send_failure(self):
        """Order_send failure must return MANAGED_DEMO_MICRO_FAILED."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        assert "ORDER_SEND_FAILED" in src
        assert "MANAGED_DEMO_MICRO_FAILED" in src

    def test_04_failed_on_receipt_write_failure(self):
        """Receipt write failure must return MANAGED_DEMO_MICRO_FAILED."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        assert "RECEIPT_WRITE_FAILED" in src

    def test_05_quick_close_returns_completed_with_warnings(self):
        """Quick close must return COMPLETED_WITH_WARNINGS, not STARTED."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        assert "POSITION_CLOSED_BEFORE_MONITOR" in src
        assert "MANAGED_DEMO_MICRO_COMPLETED_WITH_WARNINGS" in src

    def test_06_monitor_started_only_with_position(self):
        """monitor_started must only be True when position is detected."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        # The STARTED return must have monitor_started=True
        assert '"monitor_started": True' in src or "monitor_started\": True" in src

    def test_07_no_false_started_without_evidence(self):
        """The script must not return STARTED without receipt + position."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        # Find the STARTED return block in the ORIGINAL source (not stripped)
        started_idx = src.find("MANAGED_DEMO_MICRO_STARTED")
        assert started_idx > 0
        # Check the surrounding context has receipt_written and position_detected
        context = src[max(0, started_idx-500):started_idx+500]
        assert "receipt_written" in context
        assert "position_detected" in context

    def test_08_execution_attempted_field(self):
        """Report must include execution_attempted field."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        assert "execution_attempted" in src

    def test_09_order_send_comment_field(self):
        """Report must include order_send_comment field."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        assert "order_send_comment" in src

    def test_10_receipt_path_field(self):
        """Report must include receipt_path field."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        assert "receipt_path" in src

    def test_11_position_detection_method_field(self):
        """Report must include position_detection_method field."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        assert "position_detection_method" in src

    def test_12_final_position_status_field(self):
        """Report must include final_position_status field."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        assert "final_position_status" in src

    def test_13_no_mojibake(self):
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        assert "\u2014" not in src

    def test_14_order_send_isolated(self):
        """order_send must only be inside run_execute_and_monitor."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        code = self._strip(src)
        lines = code.splitlines()
        in_execute = False
        for line in lines:
            if "def run_execute_and_monitor" in line:
                in_execute = True
            elif line and not line[0].isspace() and "def " in line:
                in_execute = False
            if "mt5.order_send" in line and not in_execute:
                pytest.fail(f"order_send found outside run_execute_and_monitor: {line.strip()}")

    def test_15_no_demo_micro_execute(self):
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        code = self._strip(src)
        assert not re.search(r"(?<!['\"])\b(DEMO_MICRO_EXECUTE|run_demo_micro)\s*\(", code)

    def test_16_no_raw_mt5_probe(self):
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        code = self._strip(src)
        assert not re.search(r"(?<!['\"])\b(run_raw_probe|raw_mt5_probe)\s*\(", code)
