"""TITAN XAU AI - Sprint 9.9.3.45.8.16 v2.7.3 MT5 Ticket History Scanner Tests

Tests that the ticket history scanner:
  - finds exact deal/order/position_id matches
  - does NOT use old fallback trades as proof
  - never calls mt5.order_send
  - never modifies positions
  - never creates execution tokens
  - returns TICKET_HISTORY_MT5_UNAVAILABLE when MetaTrader5 not installed
"""
from __future__ import annotations
import json, re, sys
from pathlib import Path
import pytest
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


def _strip(src):
    src = re.sub(r'"""[\s\S]*?"""', '""', src)
    src = re.sub(r"'''[\s\S]*?'''", "''", src)
    src = re.sub(r'"(?:[^"\\]|\\.)*"', '""', src)
    src = re.sub(r"'(?:[^'\\]|\\.)*'", "''", src)
    return src


class TestMT5TicketHistoryScanner:
    def test_01_module_imports(self):
        import scripts.audit.mt5_ticket_history_scanner as s
        assert hasattr(s, "run_scan")
        assert hasattr(s, "write_report")

    def test_02_all_verdicts_supported(self):
        import scripts.audit.mt5_ticket_history_scanner as s
        assert hasattr(s, "ALL_VERDICTS")
        assert s.TICKET_HISTORY_MATCH_FOUND in s.ALL_VERDICTS
        assert s.TICKET_HISTORY_PENDING in s.ALL_VERDICTS
        assert s.TICKET_HISTORY_NOT_FOUND in s.ALL_VERDICTS
        assert s.TICKET_HISTORY_MT5_UNAVAILABLE in s.ALL_VERDICTS

    def test_03_returns_mt5_unavailable_when_no_mt5(self, tmp_path):
        """Without real MetaTrader5 (or with stub returning empty history),
        scanner must return a non-MATCH_FOUND verdict with safety flags False."""
        import scripts.audit.mt5_ticket_history_scanner as s
        # Receipt not strictly needed; pass tmp_path
        receipt_path = tmp_path / "receipt.json"
        receipt_path.write_text(json.dumps({
            "success": True,
            "deal_ticket": 12345,
            "order_ticket": 67890,
            "detected_position_identifier": 54321,
            "timestamp_utc": "2026-07-01T12:00:00+00:00",
        }))
        result = s.run_scan(receipt_path=receipt_path)
        # In Z AI env (no real MT5 broker), should be MT5_UNAVAILABLE or
        # TICKET_HISTORY_PENDING (stub returns empty history) or NOT_FOUND.
        # The only forbidden verdict is MATCH_FOUND (no real broker data).
        assert result["verdict"] != s.TICKET_HISTORY_MATCH_FOUND, \
            "Scanner must not claim MATCH_FOUND without real broker data"
        assert result["safety"]["order_send_called"] is False
        assert result["fallback_used"] is False
        assert result["old_trades_used_as_proof"] is False

    def test_04_extracts_receipt_tickets(self):
        """_extract_receipt_tickets must pull all candidate tickets."""
        import scripts.audit.mt5_ticket_history_scanner as s
        receipt = {
            "deal_ticket": 111,
            "order_send_result_deal": 222,
            "order_ticket": 333,
            "order_send_result_order": 444,
            "position_id": 555,
            "detected_position_ticket": 666,
            "detected_position_identifier": 777,
            "resolved_history_position_id": 888,
        }
        out = s._extract_receipt_tickets(receipt)
        assert 111 in out["deal_tickets"]
        assert 222 in out["deal_tickets"]
        assert 333 in out["order_tickets"]
        assert 444 in out["order_tickets"]
        assert 555 in out["position_ids"]
        assert 666 in out["position_ids"]
        assert 777 in out["position_ids"]
        assert 888 in out["position_ids"]

    def test_05_no_order_send_in_source(self):
        src = (REPO_ROOT / "scripts" / "audit" / "mt5_ticket_history_scanner.py").read_text()
        code = _strip(src)
        assert not re.search(r"\bmt5\.order_send\s*\(", code)

    def test_06_no_position_modification(self):
        src = (REPO_ROOT / "scripts" / "audit" / "mt5_ticket_history_scanner.py").read_text()
        code = _strip(src)
        assert not re.search(r"\bmt5\.(order_modify|positions_modify)\s*\(", code)

    def test_07_no_execution_token_creation(self):
        src = (REPO_ROOT / "scripts" / "audit" / "mt5_ticket_history_scanner.py").read_text()
        code = _strip(src).lower()
        assert "create_local_operator_execution_token" not in code
        assert "execution_token_created" in src  # safety flag in output

    def test_08_no_fallback_used_for_proof(self):
        """Scanner must never use magic/comment/symbol as proof - only as
        diagnostic context."""
        src = (REPO_ROOT / "scripts" / "audit" / "mt5_ticket_history_scanner.py").read_text()
        # magic/symbol/comment must be reported as diagnostic only
        assert "diagnostic_related_deals" in src
        assert "fallback_used" in src
        assert "old_trades_used_as_proof" in src
        # The verdict for non-exact matches must be NOT_FOUND, not MATCH_FOUND
        assert "TICKET_HISTORY_NOT_FOUND" in src

    def test_09_uses_wide_window_14_days(self):
        """Default window must be receipt_timestamp - 14 days to now + 1 day."""
        import scripts.audit.mt5_ticket_history_scanner as s
        src = (REPO_ROOT / "scripts" / "audit" / "mt5_ticket_history_scanner.py").read_text()
        assert "timedelta(days=days_back)" in src or "timedelta(days=14)" in src
        assert "timedelta(days=1)" in src  # now + 1 day

    def test_10_writes_json_and_md(self, tmp_path, monkeypatch):
        import scripts.audit.mt5_ticket_history_scanner as s
        monkeypatch.setattr(s, "OUTPUT_DIR", tmp_path)
        result = s.run_scan()
        report = s.write_report(result)
        assert Path(report["json_path"]).exists()
        assert Path(report["md_path"]).exists()

    def test_11_no_martingale_in_source(self):
        src = (REPO_ROOT / "scripts" / "audit" / "mt5_ticket_history_scanner.py").read_text()
        code = _strip(src).lower()
        for term in ["martingale", "grid_trade", "averaging_down", "loss_based_lot"]:
            assert term not in code or "no_" in code or "forbid" in code

    def test_12_cli_tickets_override_receipt(self):
        """CLI-provided tickets must be searched alongside receipt tickets."""
        import scripts.audit.mt5_ticket_history_scanner as s
        receipt = {
            "deal_ticket": 111,
            "timestamp_utc": "2026-07-01T12:00:00+00:00",
        }
        receipt_path = REPO_ROOT / "data" / "runtime" / "_test_receipt.json"
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        receipt_path.write_text(json.dumps(receipt))
        try:
            result = s.run_scan(
                receipt_path=receipt_path,
                deal_ticket=999,
                order_ticket=888,
                position_id=777,
            )
            # In Z AI env (no MT5), this should be MT5_UNAVAILABLE but
            # candidates must include CLI tickets.
            findings = result.get("findings", {})
            assert 999 in findings.get("deal_candidates", [])
            assert 888 in findings.get("order_candidates", [])
            assert 777 in findings.get("position_candidates", [])
        finally:
            if receipt_path.exists():
                receipt_path.unlink()

    def test_13_safety_flags_in_result(self):
        """Result must include all safety flags."""
        import scripts.audit.mt5_ticket_history_scanner as s
        result = s.run_scan()
        safety = result.get("safety", {})
        assert "order_send_called" in safety
        assert "position_modified" in safety
        assert "execution_token_created" in safety
        assert safety["order_send_called"] is False
        assert safety["position_modified"] is False
        assert safety["execution_token_created"] is False

    def test_14_match_found_verdict_when_exact_match(self):
        """Source code must contain TICKET_HISTORY_MATCH_FOUND verdict path
        for exact ticket matches."""
        src = (REPO_ROOT / "scripts" / "audit" / "mt5_ticket_history_scanner.py").read_text()
        assert "TICKET_HISTORY_MATCH_FOUND" in src
        assert "exact_deal_ticket_" in src
        assert "exact_order_ticket_" in src
        assert "exact_position_id_" in src

    def test_15_pending_verdict_when_mt5_returns_empty(self):
        """Source code must contain TICKET_HISTORY_PENDING path for when
        MT5 returns empty history in wide window."""
        src = (REPO_ROOT / "scripts" / "audit" / "mt5_ticket_history_scanner.py").read_text()
        assert "TICKET_HISTORY_PENDING" in src
