"""TITAN XAU AI - Sprint 9.9.3.45.2 Demo Micro Trade Forensics Tests"""
from __future__ import annotations
import json, re, sys
from pathlib import Path
import pytest
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

class TestForensics:
    def test_01_returns_result_with_params(self):
        import scripts.operator.collect_demo_micro_trade_forensics as fc
        result = fc.collect_forensics(days=30, symbol="XAUUSD", magic=202619, comment="TITAN_DEMO_MICRO")
        assert "verdict" in result and "findings" in result

    def test_02_writes_json(self, tmp_path):
        import scripts.operator.collect_demo_micro_trade_forensics as fc
        old = fc.OUTPUT_DIR; fc.OUTPUT_DIR = tmp_path
        try:
            result = fc.collect_forensics(); report = fc.write_report(result)
            assert Path(report["json_path"]).exists()
        finally: fc.OUTPUT_DIR = old

    def test_03_supports_position_id(self):
        import scripts.operator.collect_demo_micro_trade_forensics as fc
        result = fc.collect_forensics(position_id=12345)
        assert "verdict" in result

    def test_04_supports_order_ticket(self):
        import scripts.operator.collect_demo_micro_trade_forensics as fc
        result = fc.collect_forensics(order_ticket=67890)
        assert "verdict" in result

    def test_05_supports_deal_ticket(self):
        import scripts.operator.collect_demo_micro_trade_forensics as fc
        result = fc.collect_forensics(deal_ticket=11111)
        assert "verdict" in result

    def test_06_has_match_method_field(self):
        import scripts.operator.collect_demo_micro_trade_forensics as fc
        result = fc.collect_forensics()
        assert "match_method" in result.get("findings", {}) or result["verdict"] in ("DEMO_MICRO_FORENSICS_INCOMPLETE", "DEMO_MICRO_FORENSICS_BLOCKED")

    def test_07_has_root_cause(self):
        import scripts.operator.collect_demo_micro_trade_forensics as fc
        result = fc.collect_forensics()
        assert "root_cause" in result.get("findings", {}) or result["verdict"] in ("DEMO_MICRO_FORENSICS_BLOCKED",)

    def test_08_no_order_send(self):
        src = (REPO_ROOT / "scripts" / "operator" / "collect_demo_micro_trade_forensics.py").read_text()
        code = re.sub(r'"""[\s\S]*?"""','""',src)
        code = re.sub(r'"(?:[^"\\]|\\.)*"','""',code)
        code = re.sub(r"'(?:[^'\\]|\\.)*'","''",code)
        assert not re.search(r"\bmt5\.order_send\s*\(", code)

    def test_09_no_demo_micro_execute(self):
        src = (REPO_ROOT / "scripts" / "operator" / "collect_demo_micro_trade_forensics.py").read_text()
        code = re.sub(r'"""[\s\S]*?"""','""',src)
        code = re.sub(r'"(?:[^"\\]|\\.)*"','""',code)
        code = re.sub(r"'(?:[^'\\]|\\.)*'","''",code)
        assert not re.search(r"(?<!['\"])\b(DEMO_MICRO_EXECUTE|run_demo_micro)\s*\(", code)

    def test_10_default_days_is_30(self):
        """Sprint 9.9.3.45.2: default days should be 30, not 7."""
        src = (REPO_ROOT / "scripts" / "operator" / "collect_demo_micro_trade_forensics.py").read_text()
        # Check argparse default
        assert "default=30" in src
