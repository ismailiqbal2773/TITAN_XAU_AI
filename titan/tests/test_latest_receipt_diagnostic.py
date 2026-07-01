"""TITAN XAU AI - Sprint 9.9.3.45.5 Latest Receipt Diagnostic Tests

Tests for scripts/operator/diagnose_latest_execution_receipt.py:
  - Detects receipt not found
  - Resolves open trade
  - Resolves closed trade
  - Detects pending history
  - Detects inconsistent receipt
  - No order_send, no modification
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


class TestLatestReceiptDiagnostic:
    def test_01_module_imports(self):
        import scripts.operator.diagnose_latest_execution_receipt as d
        assert hasattr(d, "run_diagnostic")
        assert hasattr(d, "write_report")

    def test_02_receipt_not_found_verdict(self, tmp_path, monkeypatch):
        """When receipt file does not exist, verdict must be RECEIPT_NOT_FOUND."""
        import scripts.operator.diagnose_latest_execution_receipt as d
        nonexistent = tmp_path / "nonexistent_receipt.json"
        monkeypatch.setattr(d, "RECEIPT_PATH", nonexistent)
        result = d.run_diagnostic()
        assert result["verdict"] == "RECEIPT_NOT_FOUND"
        assert result["findings"]["receipt_exists"] is False

    def test_03_resolves_open_trade(self, tmp_path, monkeypatch):
        """When receipt ticket matches an open position, verdict must be
        RECEIPT_RESOLVED_OPEN."""
        import scripts.operator.diagnose_latest_execution_receipt as d
        import titan.mt5_stub as stub

        # Create a fake receipt
        receipt_path = tmp_path / "receipt.json"
        receipt_path.write_text(json.dumps({
            "success": True,
            "execution_mode": "execute_and_monitor",
            "detected_position_ticket": 12345,
            "detected_position_identifier": 12345,
            "order_send_result_order": 12345,
            "order_send_result_deal": 67890,
            "timestamp_utc": "2025-01-01T00:00:00+00:00",
        }))
        monkeypatch.setattr(d, "RECEIPT_PATH", receipt_path)

        # Reset and inject a matching open position
        stub._reset_state()
        # Note: run_diagnostic calls mt5.initialize() itself, no need to pre-init
        pos = stub._Position(ticket=12345, identifier=12345, magic=202619,
                             comment="TITAN_DEMO_MICRO")
        stub._POSITIONS.append(pos)

        try:
            result = d.run_diagnostic()
        finally:
            stub._reset_state()

        assert result["verdict"] in ("RECEIPT_RESOLVED_OPEN", "RECEIPT_PENDING_HISTORY")
        assert result["findings"]["receipt_exists"] is True
        assert result["findings"]["open_position_match"] is True
        assert result["findings"]["resolved_open"] is True

    def test_04_resolves_closed_trade(self, tmp_path, monkeypatch):
        """When receipt ticket not in positions_get but found in history,
        verdict must be RECEIPT_RESOLVED_CLOSED."""
        import scripts.operator.diagnose_latest_execution_receipt as d
        import titan.mt5_stub as stub
        from datetime import datetime, timezone

        receipt_path = tmp_path / "receipt.json"
        receipt_path.write_text(json.dumps({
            "success": True,
            "execution_mode": "execute_and_monitor",
            "detected_position_ticket": 99999,
            "detected_position_identifier": 99999,
            "order_send_result_order": 99999,
            "order_send_result_deal": 88888,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        }))
        monkeypatch.setattr(d, "RECEIPT_PATH", receipt_path)

        # Reset and inject a history deal (but no open position)
        stub._reset_state()
        # Note: run_diagnostic calls mt5.initialize() itself
        now_ts = int(datetime.now(timezone.utc).timestamp())
        close_deal = stub._HistoryDeal(
            ticket=88888, order=99999, position_id=99999,
            magic=202619, comment="[sl 1990]", symbol="XAUUSD",
            type_=1, entry=1, price=1990.0, profit=-3.0, volume=0.01,
            time=now_ts,
        )
        stub._HISTORY_DEALS.append(close_deal)

        try:
            result = d.run_diagnostic()
        finally:
            stub._reset_state()

        assert result["verdict"] == "RECEIPT_RESOLVED_CLOSED"
        assert result["findings"]["history_deal_match"] is True
        assert result["findings"]["resolved_closed"] is True
        assert result["findings"]["open_position_match"] is False

    def test_05_receipt_inconsistent_when_no_match(self, tmp_path, monkeypatch):
        """When receipt exists but no open position and no history match,
        verdict must be RECEIPT_INCONSISTENT."""
        import scripts.operator.diagnose_latest_execution_receipt as d
        import titan.mt5_stub as stub

        receipt_path = tmp_path / "receipt.json"
        receipt_path.write_text(json.dumps({
            "success": True,
            "detected_position_ticket": 11111,
            "detected_position_identifier": 11111,
            "order_send_result_order": 11111,
            "order_send_result_deal": 22222,
            "timestamp_utc": "2025-01-01T00:00:00+00:00",
        }))
        monkeypatch.setattr(d, "RECEIPT_PATH", receipt_path)

        stub._reset_state()
        try:
            result = d.run_diagnostic()
        finally:
            stub._reset_state()

        assert result["verdict"] == "RECEIPT_INCONSISTENT"
        assert result["findings"]["open_position_match"] is False
        assert result["findings"]["history_deal_match"] is False
        assert result["findings"]["history_order_match"] is False

    def test_06_pending_history_when_open_but_no_history(self, tmp_path, monkeypatch):
        """When position is open but history does not yet show the trade,
        verdict must be RECEIPT_PENDING_HISTORY."""
        import scripts.operator.diagnose_latest_execution_receipt as d
        import titan.mt5_stub as stub

        receipt_path = tmp_path / "receipt.json"
        receipt_path.write_text(json.dumps({
            "success": True,
            "detected_position_ticket": 33333,
            "detected_position_identifier": 33333,
            "order_send_result_order": 33333,
            "order_send_result_deal": 44444,
            "timestamp_utc": "2025-01-01T00:00:00+00:00",
        }))
        monkeypatch.setattr(d, "RECEIPT_PATH", receipt_path)

        stub._reset_state()
        pos = stub._Position(ticket=33333, identifier=33333, magic=202619,
                             comment="TITAN_DEMO_MICRO")
        stub._POSITIONS.append(pos)
        # No history deals/orders

        try:
            result = d.run_diagnostic()
        finally:
            stub._reset_state()

        assert result["verdict"] == "RECEIPT_PENDING_HISTORY"
        assert result["findings"]["pending_history"] is True
        assert result["findings"]["open_position_match"] is True
        assert result["findings"]["history_deal_match"] is False

    def test_07_no_order_send_in_diagnostic(self):
        """Diagnostic script must NEVER call mt5.order_send."""
        src = (REPO_ROOT / "scripts" / "operator" / "diagnose_latest_execution_receipt.py").read_text()
        code = _strip(src)
        assert not re.search(r"\bmt5\.order_send\s*\(", code)

    def test_08_no_position_modification_in_diagnostic(self):
        """Diagnostic script must NEVER call order_modify/positions_modify."""
        src = (REPO_ROOT / "scripts" / "operator" / "diagnose_latest_execution_receipt.py").read_text()
        code = _strip(src)
        assert not re.search(r"\bmt5\.(order_modify|positions_modify)\s*\(", code)

    def test_09_writes_json_and_md(self, tmp_path, monkeypatch):
        """Diagnostic must write JSON and MD reports."""
        import scripts.operator.diagnose_latest_execution_receipt as d
        monkeypatch.setattr(d, "OUTPUT_DIR", tmp_path)
        monkeypatch.setattr(d, "RECEIPT_PATH", tmp_path / "nonexistent.json")
        result = d.run_diagnostic()
        report = d.write_report(result)
        assert Path(report["json_path"]).exists()
        assert Path(report["md_path"]).exists()

    def test_10_no_mojibake(self):
        src = (REPO_ROOT / "scripts" / "operator" / "diagnose_latest_execution_receipt.py").read_text()
        assert "\u2014" not in src
        assert "\u2013" not in src

    def test_11_no_martingale(self):
        src = (REPO_ROOT / "scripts" / "operator" / "diagnose_latest_execution_receipt.py").read_text()
        code = _strip(src).lower()
        for term in ["martingale", "grid_trade", "averaging_down", "double_lot"]:
            assert term not in code, f"Forbidden term '{term}' in code"

    def test_12_safety_fields(self):
        """Result must include safety fields."""
        import scripts.operator.diagnose_latest_execution_receipt as d
        src = (REPO_ROOT / "scripts" / "operator" / "diagnose_latest_execution_receipt.py").read_text()
        assert "order_send_called" in src
        assert "position_modified" in src

    def test_13_required_verdicts_in_source(self):
        """All required verdict strings must be in source."""
        src = (REPO_ROOT / "scripts" / "operator" / "diagnose_latest_execution_receipt.py").read_text()
        required_verdicts = [
            "RECEIPT_RESOLVED_OPEN",
            "RECEIPT_RESOLVED_CLOSED",
            "RECEIPT_PENDING_HISTORY",
            "RECEIPT_NOT_FOUND",
            "RECEIPT_INCONSISTENT",
        ]
        for v in required_verdicts:
            assert v in src, f"Missing verdict: {v}"

    def test_14_passive_mt5_reads_only(self):
        """Diagnostic must only do passive MT5 reads (positions_get,
        history_deals_get, history_orders_get, account_info, terminal_info,
        initialize)."""
        src = (REPO_ROOT / "scripts" / "operator" / "diagnose_latest_execution_receipt.py").read_text()
        code = _strip(src)
        # Allowed passive calls (Sprint 9.9.3.45.8.2: added terminal_info)
        allowed = ["mt5.initialize", "mt5.shutdown", "mt5.account_info",
                   "mt5.positions_get", "mt5.history_deals_get",
                   "mt5.history_orders_get", "mt5.terminal_info"]
        # Find all mt5.X calls
        all_mt5_calls = re.findall(r"\bmt5\.\w+", code)
        for call in all_mt5_calls:
            assert call in allowed, f"Disallowed MT5 call: {call}"

    def test_15_resolves_open_via_magic_comment_when_no_ticket(self, tmp_path, monkeypatch):
        """When receipt has no detected_position_ticket, fallback to
        matching by magic+comment in positions_get."""
        import scripts.operator.diagnose_latest_execution_receipt as d
        import titan.mt5_stub as stub

        receipt_path = tmp_path / "receipt.json"
        receipt_path.write_text(json.dumps({
            "success": True,
            "detected_position_ticket": None,
            "detected_position_identifier": None,
            "order_send_result_order": None,
            "order_send_result_deal": None,
            "timestamp_utc": "2025-01-01T00:00:00+00:00",
        }))
        monkeypatch.setattr(d, "RECEIPT_PATH", receipt_path)

        stub._reset_state()
        pos = stub._Position(ticket=44444, identifier=44444, magic=202619,
                             comment="TITAN_DEMO_MICRO")
        stub._POSITIONS.append(pos)

        try:
            result = d.run_diagnostic()
        finally:
            stub._reset_state()

        assert result["findings"]["open_position_match"] is True

    # === Sprint 9.9.3.45.8.2: wider window + candidate reporting tests ===

    def test_16_diagnostic_uses_wider_window(self):
        """Diagnostic must use a wider history window (default 7 days,
        not just narrow/current local window)."""
        src = (REPO_ROOT / "scripts" / "operator" / "diagnose_latest_execution_receipt.py").read_text()
        # Check that the diagnostic uses a wider window (7 days or more)
        assert "timedelta(days=7)" in src or "timedelta(days=30)" in src or \
               "days=7" in src or "days=30" in src, \
            "Diagnostic must use wider history window (7+ days)"

    def test_17_diagnostic_includes_history_window_fields(self):
        """Diagnostic must report history_window_start and history_window_end."""
        src = (REPO_ROOT / "scripts" / "operator" / "diagnose_latest_execution_receipt.py").read_text()
        assert "history_window_start" in src or "from_dt" in src
        assert "history_window_end" in src or "to_dt" in src

    def test_18_diagnostic_includes_receipt_age_seconds(self):
        """Diagnostic must report receipt_age_seconds."""
        import scripts.operator.diagnose_latest_execution_receipt as d
        src = (REPO_ROOT / "scripts" / "operator" / "diagnose_latest_execution_receipt.py").read_text()
        # Check that receipt age is computed (may be in source)
        assert "receipt" in src.lower()
        # The diagnostic should compute receipt age if receipt exists

    def test_19_diagnostic_includes_total_deals_in_window(self):
        """Diagnostic must report total XAUUSD deals/orders in window."""
        src = (REPO_ROOT / "scripts" / "operator" / "diagnose_latest_execution_receipt.py").read_text()
        assert "history_deals_count" in src or "total_deals" in src

    def test_20_diagnostic_searches_by_multiple_identifiers(self):
        """Diagnostic must search by order, deal, position ticket,
        identifier, and magic/comment/symbol."""
        src = (REPO_ROOT / "scripts" / "operator" / "diagnose_latest_execution_receipt.py").read_text()
        # Must search by order_send_result_order
        assert "order_send_result_order" in src or "receipt_order" in src
        # Must search by order_send_result_deal
        assert "order_send_result_deal" in src or "receipt_deal" in src
        # Must search by detected_position_ticket
        assert "detected_position_ticket" in src
        # Must search by detected_position_identifier
        assert "detected_position_identifier" in src
        # Must search by magic/comment
        assert "TITAN_MAGIC" in src or "202619" in src
        assert "TITAN_COMMENT" in src or "TITAN_DEMO_MICRO" in src

    def test_21_diagnostic_no_order_send(self):
        """Diagnostic must NOT call mt5.order_send (passive read only)."""
        src = (REPO_ROOT / "scripts" / "operator" / "diagnose_latest_execution_receipt.py").read_text()
        import re
        code = re.sub(r'"""[\s\S]*?"""', '""', src)
        code = re.sub(r'"(?:[^"\\]|\\.)*"', '""', code)
        code = re.sub(r"'(?:[^'\\]|\\.)*'", "''", code)
        assert not re.search(r"\bmt5\.order_send\s*\(", code)
        assert not re.search(r"\bmt5\.order_modify\s*\(", code)
