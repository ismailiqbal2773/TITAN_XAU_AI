"""TITAN XAU AI — Sprint 9.9.3.25.1 Demo Micro Full Cycle Adapter Diagnostics Tests"""
from __future__ import annotations
import sys
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


class TestSendOpenOrderDiagnostics:
    """Verify _send_open_order propagates adapter diagnostics."""

    def test_01_propagates_error_field(self, monkeypatch):
        """_send_open_order propagates error from adapter."""
        from scripts.audit import demo_micro_full_cycle as harness
        # Mock the adapter class at the module level
        class MockAdapter:
            def __init__(self, *a, **kw): pass
            def send_open_order(self, **kw):
                return {
                    "ok": False, "retcode": 10013,
                    "error": "OPEN_SUCCEEDED_SLTP_MODIFY_FAILED_EMERGENCY_CLOSED",
                    "reason": "SLTP modify failed retcode=10013",
                    "open_retcode": 10009,
                    "sltp_modify_retcode": 10013,
                    "sltp_modify_comment": "Invalid request",
                    "sltp_modify_retcode_meaning": "invalid request",
                    "emergency_close_required": True,
                    "emergency_close_result": {"ok": True, "retcode": 10009},
                    "mt5_last_error_code": None,
                    "mt5_last_error_message": "",
                    "raw_working_profile_used": True,
                    "broker_snapshot": {},
                    "send_attempts": [{"send_retcode": 10009, "send_ok": True}],
                    "check_attempts": [],
                    "filling_mode_selected": "IOC",
                    "filling_type_used": 2,
                    "filling_source": "raw_working_profile",
                    "filling_mask": 3,
                    "position_detected_after_failure": {"appeared": False, "tickets": [], "count": 0},
                    "emergency_close_tickets": [],
                }
        # Patch the import inside _send_open_order
        import titan.production.mt5_execution_adapter as adapter_mod
        monkeypatch.setattr(adapter_mod, "MT5ExecutionAdapter", MockAdapter)
        result = harness._send_open_order(
            mt5=None, symbol="XAUUSD", side="BUY", lot=0.01, magic=20261993,
        )
        assert result["error"] == "OPEN_SUCCEEDED_SLTP_MODIFY_FAILED_EMERGENCY_CLOSED"
        assert result["reason"] == "SLTP modify failed retcode=10013"
        assert result["open_retcode"] == 10009
        assert result["sltp_modify_retcode"] == 10013
        assert result["sltp_modify_comment"] == "Invalid request"
        assert result["sltp_modify_retcode_meaning"] == "invalid request"
        assert result["emergency_close_required"] is True
        assert result["emergency_close_result"]["ok"] is True

    def test_02_propagates_mt5_last_error(self, monkeypatch):
        """_send_open_order propagates mt5_last_error fields."""
        from scripts.audit import demo_micro_full_cycle as harness
        class MockAdapter:
            def __init__(self, *a, **kw): pass
            def send_open_order(self, **kw):
                return {
                    "ok": False, "retcode": None,
                    "error": "order_send returned None",
                    "mt5_last_error_code": -1,
                    "mt5_last_error_message": "MT5 internal error",
                    "send_attempts": [{"order_send_returned_none": True}],
                    "check_attempts": [],
                    "filling_mode_selected": None,
                    "filling_type_used": None,
                    "filling_source": None,
                    "filling_mask": None,
                    "position_detected_after_failure": {},
                    "emergency_close_required": False,
                    "emergency_close_tickets": [],
                    "broker_snapshot": {},
                }
        import titan.production.mt5_execution_adapter as adapter_mod
        monkeypatch.setattr(adapter_mod, "MT5ExecutionAdapter", MockAdapter)
        result = harness._send_open_order(
            mt5=None, symbol="XAUUSD", side="BUY", lot=0.01, magic=20261993,
        )
        assert result["mt5_last_error_code"] == -1
        assert result["mt5_last_error_message"] == "MT5 internal error"

    def test_03_propagates_raw_profile_used(self, monkeypatch):
        """_send_open_order propagates raw_profile_used field."""
        from scripts.audit import demo_micro_full_cycle as harness
        class MockAdapter:
            def __init__(self, *a, **kw): pass
            def send_open_order(self, **kw):
                return {
                    "ok": True, "retcode": 10009,
                    "raw_working_profile_used": True,
                    "send_attempts": [{"send_retcode": 10009, "send_ok": True}],
                    "check_attempts": [],
                    "filling_mode_selected": "IOC",
                    "filling_type_used": 2,
                    "filling_source": "raw_working_profile",
                    "filling_mask": 3,
                    "position_detected_after_failure": {},
                    "emergency_close_required": False,
                    "emergency_close_tickets": [],
                    "broker_snapshot": {},
                }
        import titan.production.mt5_execution_adapter as adapter_mod
        monkeypatch.setattr(adapter_mod, "MT5ExecutionAdapter", MockAdapter)
        result = harness._send_open_order(
            mt5=None, symbol="XAUUSD", side="BUY", lot=0.01, magic=20261993,
        )
        assert result["raw_profile_used"] is True

    def test_04_propagates_broker_snapshot(self, monkeypatch):
        """_send_open_order propagates broker_snapshot field."""
        from scripts.audit import demo_micro_full_cycle as harness
        class MockAdapter:
            def __init__(self, *a, **kw): pass
            def send_open_order(self, **kw):
                return {
                    "ok": True, "retcode": 10009,
                    "broker_snapshot": {"symbol": "XAUUSD", "account": {"server": "test"}},
                    "send_attempts": [{"send_retcode": 10009}],
                    "check_attempts": [],
                    "filling_mode_selected": "IOC",
                    "filling_type_used": 2,
                    "filling_source": "default",
                    "filling_mask": 3,
                    "position_detected_after_failure": {},
                    "emergency_close_required": False,
                    "emergency_close_tickets": [],
                }
        import titan.production.mt5_execution_adapter as adapter_mod
        monkeypatch.setattr(adapter_mod, "MT5ExecutionAdapter", MockAdapter)
        result = harness._send_open_order(
            mt5=None, symbol="XAUUSD", side="BUY", lot=0.01, magic=20261993,
        )
        assert result["broker_snapshot"]["symbol"] == "XAUUSD"
