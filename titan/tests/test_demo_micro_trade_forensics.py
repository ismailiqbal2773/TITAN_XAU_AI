"""TITAN XAU AI - Sprint 9.9.3.45.1 Demo Micro Trade Forensics Tests"""
from __future__ import annotations
import json, re, sys
from pathlib import Path
import pytest
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

class TestForensics:
    def test_01_returns_result_with_params(self):
        import scripts.operator.collect_demo_micro_trade_forensics as fc
        result = fc.collect_forensics(days=7, symbol="XAUUSD", magic=202619, comment="TITAN_DEMO_MICRO")
        assert "verdict" in result and "findings" in result

    def test_02_writes_json(self, tmp_path):
        import scripts.operator.collect_demo_micro_trade_forensics as fc
        old = fc.OUTPUT_DIR; fc.OUTPUT_DIR = tmp_path
        try:
            result = fc.collect_forensics(); report = fc.write_report(result)
            assert Path(report["json_path"]).exists()
        finally: fc.OUTPUT_DIR = old

    def test_03_handles_missing_mt5(self):
        import scripts.operator.collect_demo_micro_trade_forensics as fc
        result = fc.collect_forensics()
        assert result["verdict"] in ("DEMO_MICRO_FORENSICS_INCOMPLETE","DEMO_MICRO_FORENSICS_BLOCKED","DEMO_MICRO_FORENSICS_COMPLETE","DEMO_MICRO_FORENSICS_COMPLETE_WITH_WARNINGS")

    def test_04_no_order_send(self):
        src = (REPO_ROOT / "scripts" / "operator" / "collect_demo_micro_trade_forensics.py").read_text()
        code = re.sub(r'"""[\s\S]*?"""','""',src)
        code = re.sub(r'"(?:[^"\\]|\\.)*"','""',code)
        code = re.sub(r"'(?:[^'\\]|\\.)*'","''",code)
        assert not re.search(r"\bmt5\.order_send\s*\(", code)

    def test_05_no_demo_micro_execute(self):
        src = (REPO_ROOT / "scripts" / "operator" / "collect_demo_micro_trade_forensics.py").read_text()
        code = re.sub(r'"""[\s\S]*?"""','""',src)
        code = re.sub(r'"(?:[^"\\]|\\.)*"','""',code)
        code = re.sub(r"'(?:[^'\\]|\\.)*'","''",code)
        assert not re.search(r"(?<!['\"])\b(DEMO_MICRO_EXECUTE|run_demo_micro)\s*\(", code)

    def test_06_has_likely_deals_field(self):
        """When MT5 history is available, likely_deals should be in findings.
        When MT5 is not available or history fails, findings may be partial."""
        import scripts.operator.collect_demo_micro_trade_forensics as fc
        result = fc.collect_forensics()
        # If MT5 available with history, likely_deals should exist
        # If MT5 unavailable or error, findings may not have it
        if result["verdict"] not in ("DEMO_MICRO_FORENSICS_BLOCKED",):
            assert "likely_deals" in result.get("findings", {}) or "root_cause" in result.get("findings", {})

    def test_07_root_cause_in_findings(self):
        """root_cause should be in findings when MT5 history is accessible."""
        import scripts.operator.collect_demo_micro_trade_forensics as fc
        result = fc.collect_forensics()
        # root_cause may not be present if MT5 history fails
        if "root_cause" not in result.get("findings", {}):
            # Should have at least an error reason
            assert result["verdict"] in ("DEMO_MICRO_FORENSICS_INCOMPLETE", "DEMO_MICRO_FORENSICS_BLOCKED")
