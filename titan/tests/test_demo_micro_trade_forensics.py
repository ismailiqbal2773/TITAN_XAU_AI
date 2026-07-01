"""TITAN XAU AI - Sprint 9.9.3.45.5 Demo Micro Trade Forensics Tests

Sprint 9.9.3.45.5 adds:
  - Explicit --position-id not found does NOT fallback to old trade
  - Receipt_success=True but receipt not found does NOT fallback
  - Fallback candidates are diagnostic only when fallback blocked
  - New fields: explicit_position_id_supplied, explicit_position_id_found,
    receipt_match_required, receipt_match_found, fallback_candidates_count,
    fallback_used, fallback_allowed, fallback_blocked_reason
  - Tests mock MT5 (no order_send, no modification)
"""
from __future__ import annotations
import json, re, sys
from pathlib import Path
from datetime import datetime, timezone
import pytest
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


def _strip(src):
    src = re.sub(r'"""[\s\S]*?"""', '""', src)
    src = re.sub(r"'''[\s\S]*?'''", "''", src)
    src = re.sub(r'"(?:[^"\\]|\\.)*"', '""', src)
    src = re.sub(r"'(?:[^'\\]|\\.)*'", "''", src)
    return src


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
        code = _strip(src)
        assert not re.search(r"\bmt5\.order_send\s*\(", code)

    def test_09_no_demo_micro_execute(self):
        src = (REPO_ROOT / "scripts" / "operator" / "collect_demo_micro_trade_forensics.py").read_text()
        code = _strip(src)
        assert not re.search(r"(?<!['\"])\b(DEMO_MICRO_EXECUTE|run_demo_micro)\s*\(", code)

    def test_10_default_days_is_30(self):
        """Default days should be 30, not 7."""
        src = (REPO_ROOT / "scripts" / "operator" / "collect_demo_micro_trade_forensics.py").read_text()
        assert "default=30" in src

    # === Sprint 9.9.3.45.5 new tests ===

    def test_11_has_strict_no_fallback_fields(self):
        """Forensics must include strict no-fallback fields."""
        import scripts.operator.collect_demo_micro_trade_forensics as fc
        result = fc.collect_forensics()
        findings = result.get("findings", {})
        required = [
            "explicit_position_id_supplied", "explicit_position_id_found",
            "receipt_match_required", "receipt_match_found",
            "fallback_candidates_count", "fallback_used",
            "fallback_allowed", "fallback_blocked_reason",
        ]
        for field in required:
            assert field in findings, f"Missing field: {field}"

    def test_12_explicit_position_id_not_found_does_not_fallback(self):
        """If explicit --position-id is supplied and not found, must NOT
        fallback to old trades."""
        import scripts.operator.collect_demo_micro_trade_forensics as fc
        # position_id 57344905358 doesn't exist in MT5 stub history
        result = fc.collect_forensics(position_id=57344905358)
        assert result["verdict"] == "DEMO_MICRO_FORENSICS_INCOMPLETE"
        findings = result.get("findings", {})
        assert findings.get("explicit_position_id_supplied") is True
        assert findings.get("explicit_position_id_found") is False
        assert findings.get("fallback_used") is False
        assert findings.get("root_cause") == "EXPLICIT_POSITION_ID_NOT_FOUND"

    def test_13_explicit_order_ticket_not_found_does_not_fallback(self):
        """If explicit --order-ticket is supplied and not found, must NOT
        fallback to old trades."""
        import scripts.operator.collect_demo_micro_trade_forensics as fc
        result = fc.collect_forensics(order_ticket=99999999)
        assert result["verdict"] == "DEMO_MICRO_FORENSICS_INCOMPLETE"
        findings = result.get("findings", {})
        assert findings.get("fallback_used") is False
        assert "EXPLICIT_ORDER_TICKET_NOT_FOUND" in findings.get("root_cause", "")

    def test_14_receipt_success_true_but_not_found_does_not_fallback(self, tmp_path, monkeypatch):
        """If receipt exists with success=True but trade not found in
        history or open positions, must NOT fallback to old trades."""
        import scripts.operator.collect_demo_micro_trade_forensics as fc

        # Create a fake receipt with success=True
        receipt_path = tmp_path / "demo_micro_execution_receipt.json"
        receipt_data = {
            "success": True,
            "execution_mode": "execute_and_monitor",
            "detected_position_ticket": 57344905358,
            "detected_position_identifier": 57344905358,
            "order_ticket": 57344905358,
            "deal_ticket": 57001412567,
            "position_id": None,
            "timestamp_utc": "2025-01-01T00:00:00Z",
        }
        receipt_path.write_text(json.dumps(receipt_data))

        # Patch RECEIPT_PATH
        monkeypatch.setattr(fc, "RECEIPT_PATH", receipt_path)

        result = fc.collect_forensics()
        assert result["verdict"] == "DEMO_MICRO_FORENSICS_INCOMPLETE"
        findings = result.get("findings", {})
        assert findings.get("receipt_match_required") is True
        assert findings.get("receipt_match_found") is False
        assert findings.get("fallback_used") is False
        assert findings.get("root_cause") == "RECEIPT_TRADE_NOT_FOUND_IN_HISTORY_OR_OPEN_POSITIONS"
        # Fallback candidates should be diagnostic only
        assert "fallback_candidates" in findings
        assert findings.get("fallback_candidates_count", 0) == 0  # MT5 stub has no history

    def test_15_fallback_allowed_when_no_receipt_no_explicit(self, monkeypatch, tmp_path):
        """Fallback is allowed when no receipt and no explicit id."""
        import scripts.operator.collect_demo_micro_trade_forensics as fc

        # No receipt
        receipt_path = tmp_path / "nonexistent.json"
        monkeypatch.setattr(fc, "RECEIPT_PATH", receipt_path)

        result = fc.collect_forensics()
        findings = result.get("findings", {})
        assert findings.get("fallback_allowed") is True
        assert findings.get("receipt_match_required") is False

    def test_16_fallback_blocked_when_explicit_id_supplied(self, monkeypatch, tmp_path):
        """Fallback must be blocked when explicit position_id is supplied."""
        import scripts.operator.collect_demo_micro_trade_forensics as fc

        # Even with a successful receipt, explicit id takes precedence
        receipt_path = tmp_path / "demo_micro_execution_receipt.json"
        receipt_path.write_text(json.dumps({"success": True, "detected_position_ticket": 12345}))
        monkeypatch.setattr(fc, "RECEIPT_PATH", receipt_path)

        result = fc.collect_forensics(position_id=57344905358)
        findings = result.get("findings", {})
        assert "EXPLICIT_ID_SUPPLIED_FORBIDS_FALLBACK" in findings.get("fallback_blocked_reason", "") \
            or "EXPLICIT_POSITION_ID_NOT_FOUND" in findings.get("fallback_blocked_reason", "")
        assert findings.get("fallback_used") is False

    def test_17_fallback_candidates_diagnostic_only_when_blocked(self, monkeypatch, tmp_path):
        """When fallback is blocked, candidates are included as diagnostics
        only - verdict must not be COMPLETE based on them."""
        import scripts.operator.collect_demo_micro_trade_forensics as fc

        # Successful receipt but trade not found
        receipt_path = tmp_path / "demo_micro_execution_receipt.json"
        receipt_path.write_text(json.dumps({
            "success": True,
            "detected_position_ticket": 57344905358,
        }))
        monkeypatch.setattr(fc, "RECEIPT_PATH", receipt_path)

        result = fc.collect_forensics()
        # Verdict must NOT be COMPLETE or COMPLETE_WITH_WARNINGS — only INCOMPLETE allowed
        assert result["verdict"] == "DEMO_MICRO_FORENSICS_INCOMPLETE", \
            f"Expected INCOMPLETE, got {result['verdict']}"
        findings = result.get("findings", {})
        # If fallback_candidates exists, fallback_used must be False
        if "fallback_candidates" in findings:
            assert findings.get("fallback_used") is False

    def test_18_no_mojibake(self):
        src = (REPO_ROOT / "scripts" / "operator" / "collect_demo_micro_trade_forensics.py").read_text()
        assert "\u2014" not in src
        assert "\u2013" not in src

    def test_19_no_martingale(self):
        src = (REPO_ROOT / "scripts" / "operator" / "collect_demo_micro_trade_forensics.py").read_text()
        code = _strip(src).lower()
        for term in ["martingale", "grid_trade", "averaging_down", "double_lot"]:
            assert term not in code, f"Forbidden term '{term}' in code"

    def test_20_no_position_modification(self):
        """Forensics must NEVER call order_send or modify positions."""
        src = (REPO_ROOT / "scripts" / "operator" / "collect_demo_micro_trade_forensics.py").read_text()
        code = _strip(src)
        # No order_send, no order_modify
        assert not re.search(r"\bmt5\.order_send\s*\(", code)
        # No SL/TP modification functions
        assert not re.search(r"\bmt5\.(order_modify|positions_modify|order_calc_margin)\s*\(", code)

    def test_21_writes_strict_no_fallback_summary_in_md(self, tmp_path):
        """MD report must include Strict No-Fallback Summary section."""
        import scripts.operator.collect_demo_micro_trade_forensics as fc
        old = fc.OUTPUT_DIR; fc.OUTPUT_DIR = tmp_path
        try:
            result = fc.collect_forensics(position_id=57344905358)
            report = fc.write_report(result)
            md = Path(report["md_path"]).read_text()
            assert "Strict No-Fallback Summary" in md
            assert "fallback_used" in md
            assert "fallback_blocked_reason" in md
        finally: fc.OUTPUT_DIR = old
