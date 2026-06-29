"""TITAN XAU AI — Sprint 9.9.3.25.1 SLTP Constants Tests"""
from __future__ import annotations
import sys, inspect
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from titan.production.mt5_execution_adapter import (
    MT5ExecutionAdapter, _TRADE_ACTION_SLTP_DEFAULT,
)


class TestTradeActionConstants:
    """Verify adapter reads TRADE_ACTION_SLTP at runtime, not hardcoded."""

    def test_01_adapter_reads_runtime_trade_action_sltp(self):
        """Adapter reads mt5.TRADE_ACTION_SLTP at runtime."""
        class MockMT5WithConstants:
            TRADE_ACTION_DEAL = 1
            TRADE_ACTION_SLTP = 2
            ORDER_FILLING_FOK = 1
            ORDER_FILLING_IOC = 2
            ORDER_FILLING_RETURN = 4
            def initialize(self): return True
            def shutdown(self): pass
            def account_info(self): return None
            def terminal_info(self): return None
            def symbol_info(self, s): return None
            def symbol_info_tick(self, s): return None
            def symbol_select(self, s, v=True): return True
            def positions_get(self, **kw): return []
            def order_check(self, r): return None
            def order_send(self, r): return None
            def last_error(self): return (0, "ok")

        mt5 = MockMT5WithConstants()
        adapter = MT5ExecutionAdapter(mt5, journal_event=lambda e, p: None)
        consts = adapter._get_trade_action_constants()
        assert consts["TRADE_ACTION_SLTP"] == 2
        assert consts["TRADE_ACTION_DEAL"] == 1

    def test_02_adapter_falls_back_when_constant_missing(self):
        """Adapter falls back to default when TRADE_ACTION_SLTP missing."""
        class MockMT5NoConstants:
            ORDER_FILLING_FOK = 1
            ORDER_FILLING_IOC = 2
            ORDER_FILLING_RETURN = 4
            def initialize(self): return True
            def shutdown(self): pass
            def account_info(self): return None
            def terminal_info(self): return None
            def symbol_info(self, s): return None
            def symbol_info_tick(self, s): return None
            def symbol_select(self, s, v=True): return True
            def positions_get(self, **kw): return []
            def order_check(self, r): return None
            def order_send(self, r): return None
            def last_error(self): return (0, "ok")

        mt5 = MockMT5NoConstants()
        adapter = MT5ExecutionAdapter(mt5, journal_event=lambda e, p: None)
        consts = adapter._get_trade_action_constants()
        assert consts["TRADE_ACTION_SLTP"] == _TRADE_ACTION_SLTP_DEFAULT
        assert consts["TRADE_ACTION_DEAL"] == 1  # default _TRADE_ACTION_DEAL

    def test_03_sltp_modify_uses_runtime_action(self):
        """SLTP modify request uses runtime TRADE_ACTION_SLTP, not hardcoded."""
        class MockMT5WithCustomSLTP:
            TRADE_ACTION_DEAL = 1
            TRADE_ACTION_SLTP = 99  # custom value to verify it's used
            ORDER_FILLING_FOK = 1
            ORDER_FILLING_IOC = 2
            ORDER_FILLING_RETURN = 4
            def initialize(self): return True
            def shutdown(self): pass
            def account_info(self): return None
            def terminal_info(self): return None
            def symbol_info(self, s):
                class Info:
                    digits = 5
                    point = 0.01
                    trade_stops_level = 0
                    trade_freeze_level = 0
                return Info()
            def symbol_info_tick(self, s):
                class Tick:
                    bid = 2000.0
                    ask = 2000.1
                    time = 9999999999
                return Tick()
            def symbol_select(self, s, v=True): return True
            def positions_get(self, **kw): return []
            def order_check(self, r): return None
            class _Result:
                retcode = 10009
                comment = "ok"
            def order_send(self, r):
                # Verify the action is 99 (runtime constant)
                assert r["action"] == 99, f"Expected action=99, got {r['action']}"
                return self._Result()
            def last_error(self): return (0, "ok")

        mt5 = MockMT5WithCustomSLTP()
        adapter = MT5ExecutionAdapter(mt5, journal_event=lambda e, p: None)
        result = adapter._modify_position_sltp(12345, "XAUUSD", 1995.0, 2010.0)
        assert result["ok"] is True

    def test_04_sltp_modify_request_includes_required_fields(self):
        """SLTP modify request includes position, symbol, sl, tp."""
        captured_request = {}
        class MockMT5Capture:
            TRADE_ACTION_DEAL = 1
            TRADE_ACTION_SLTP = 2
            ORDER_FILLING_FOK = 1
            ORDER_FILLING_IOC = 2
            ORDER_FILLING_RETURN = 4
            def initialize(self): return True
            def shutdown(self): pass
            def account_info(self): return None
            def terminal_info(self): return None
            def symbol_info(self, s):
                class Info:
                    digits = 5
                    point = 0.01
                    trade_stops_level = 0
                    trade_freeze_level = 0
                return Info()
            def symbol_info_tick(self, s):
                class Tick:
                    bid = 2000.0
                    ask = 2000.1
                    time = 9999999999
                return Tick()
            def symbol_select(self, s, v=True): return True
            def positions_get(self, **kw): return []
            def order_check(self, r): return None
            class _Result:
                retcode = 10009
                comment = "ok"
            def order_send(self, r):
                captured_request.update(r)
                return self._Result()
            def last_error(self): return (0, "ok")

        mt5 = MockMT5Capture()
        adapter = MT5ExecutionAdapter(mt5, journal_event=lambda e, p: None)
        adapter._modify_position_sltp(12345, "XAUUSD", 1995.0, 2010.0)
        assert captured_request["position"] == 12345
        assert captured_request["symbol"] == "XAUUSD"
        assert captured_request["sl"] == 1995.0
        assert captured_request["tp"] == 2010.0
        assert "action" in captured_request

    def test_05_sltp_modify_rounds_to_digits(self):
        """SLTP modify rounds SL/TP to symbol digits."""
        class MockMT5Rounding:
            TRADE_ACTION_DEAL = 1
            TRADE_ACTION_SLTP = 2
            ORDER_FILLING_FOK = 1
            ORDER_FILLING_IOC = 2
            ORDER_FILLING_RETURN = 4
            def initialize(self): return True
            def shutdown(self): pass
            def account_info(self): return None
            def terminal_info(self): return None
            def symbol_info(self, s):
                class Info:
                    digits = 2  # 2 decimal places
                    point = 0.01
                    trade_stops_level = 0
                    trade_freeze_level = 0
                return Info()
            def symbol_info_tick(self, s):
                class Tick:
                    bid = 2000.0
                    ask = 2000.1
                    time = 9999999999
                return Tick()
            def symbol_select(self, s, v=True): return True
            def positions_get(self, **kw): return []
            def order_check(self, r): return None
            class _Result:
                retcode = 10009
                comment = "ok"
            def order_send(self, r):
                # SL should be rounded to 2 digits
                assert r["sl"] == round(1995.123456, 2)
                assert r["tp"] == round(2010.987654, 2)
                return self._Result()
            def last_error(self): return (0, "ok")

        mt5 = MockMT5Rounding()
        adapter = MT5ExecutionAdapter(mt5, journal_event=lambda e, p: None)
        result = adapter._modify_position_sltp(12345, "XAUUSD", 1995.123456, 2010.987654)
        assert result["ok"] is True

    def test_06_sltp_modify_rejects_zero_sl_tp(self):
        """SLTP modify rejects zero SL or TP."""
        class MockMT5Basic:
            TRADE_ACTION_DEAL = 1
            TRADE_ACTION_SLTP = 2
            ORDER_FILLING_FOK = 1
            ORDER_FILLING_IOC = 2
            ORDER_FILLING_RETURN = 4
            def initialize(self): return True
            def shutdown(self): pass
            def account_info(self): return None
            def terminal_info(self): return None
            def symbol_info(self, s): return None
            def symbol_info_tick(self, s): return None
            def symbol_select(self, s, v=True): return True
            def positions_get(self, **kw): return []
            def order_check(self, r): return None
            def order_send(self, r): return None
            def last_error(self): return (0, "ok")

        mt5 = MockMT5Basic()
        adapter = MT5ExecutionAdapter(mt5, journal_event=lambda e, p: None)
        result = adapter._modify_position_sltp(12345, "XAUUSD", 0.0, 2010.0)
        assert result["ok"] is False
        assert "zero" in result.get("comment", "").lower()

    def test_07_sltp_modify_returns_retcode_meaning(self):
        """SLTP modify result includes retcode_meaning on failure."""
        class MockMT5FailSLTP:
            TRADE_ACTION_DEAL = 1
            TRADE_ACTION_SLTP = 2
            ORDER_FILLING_FOK = 1
            ORDER_FILLING_IOC = 2
            ORDER_FILLING_RETURN = 4
            def initialize(self): return True
            def shutdown(self): pass
            def account_info(self): return None
            def terminal_info(self): return None
            def symbol_info(self, s):
                class Info:
                    digits = 5
                    point = 0.01
                    trade_stops_level = 0
                    trade_freeze_level = 0
                return Info()
            def symbol_info_tick(self, s):
                class Tick:
                    bid = 2000.0
                    ask = 2000.1
                    time = 9999999999
                return Tick()
            def symbol_select(self, s, v=True): return True
            def positions_get(self, **kw): return []
            def order_check(self, r): return None
            class _Result:
                retcode = 10013  # INVALID_REQUEST
                comment = "Invalid request"
            def order_send(self, r): return self._Result()
            def last_error(self): return (0, "ok")

        mt5 = MockMT5FailSLTP()
        adapter = MT5ExecutionAdapter(mt5, journal_event=lambda e, p: None)
        result = adapter._modify_position_sltp(12345, "XAUUSD", 1995.0, 2010.0)
        assert result["ok"] is False
        assert result["retcode"] == 10013
        assert result.get("retcode_meaning") is not None
        assert "invalid request" in result["retcode_meaning"].lower()


class TestSLTPFailureDiagnostics:
    """Verify SLTP failure returns OPEN_SUCCEEDED_SLTP_MODIFY_FAILED_EMERGENCY_CLOSED."""

    def test_08_naked_open_success_sltp_fail_returns_clear_error(self, tmp_path):
        """When naked open succeeds but SLTP fails, error is OPEN_SUCCEEDED_SLTP_MODIFY_FAILED_EMERGENCY_CLOSED."""
        # This test uses the existing MockMT5 from the harness test file
        sys.path.insert(0, str(REPO_ROOT / "titan" / "tests"))
        import importlib.util
        spec = importlib.util.spec_from_file_location("tm", str(REPO_ROOT / "titan" / "tests" / "test_fundednext_demo_micro_harness.py"))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        MockMT5 = m.MockMT5

        # Create a raw profile
        import json
        raw_profile = {
            "server": "MetaQuotes-Demo", "login": 12345678, "symbol": "XAUUSD",
            "type_filling": 2, "type_filling_name": "IOC",
            "deviation": 50, "sl": 0.0, "tp": 0.0,
            "sl_tp_mode": "naked_then_sltp_modify", "type_time": 0,
        }
        profile_path = tmp_path / "raw_profile.json"
        profile_path.write_text(json.dumps(raw_profile))

        # Naked open succeeds, SLTP modify fails (10013)
        mt5 = MockMT5(symbol_filling_mode=1 | 2,
                      order_check_default_retcode=0,
                      naked_order_retcode=10009,
                      sltp_modify_retcode=10013)  # SLTP fails
        mt5._account.server = "MetaQuotes-Demo"
        mt5._account.login = 12345678
        mt5._account.trade_mode = 0
        mt5._symbol_info.trade_exemode = 2
        mt5.initialize()

        from titan.production.mt5_execution_adapter import MT5ExecutionAdapter
        adapter = MT5ExecutionAdapter(mt5, journal_event=lambda e, p: None)
        result = adapter.send_open_order(
            symbol="XAUUSD", side="BUY", lot=0.01, magic=20261993,
            use_raw_working_profile=True, raw_profile_path=str(profile_path),
        )
        # Should fail with OPEN_SUCCEEDED_SLTP_MODIFY_FAILED_EMERGENCY_CLOSED
        assert result["ok"] is False
        assert result["error"] == "OPEN_SUCCEEDED_SLTP_MODIFY_FAILED_EMERGENCY_CLOSED"
        assert result.get("open_retcode") == 10009
        assert result.get("sltp_modify_retcode") == 10013
        assert result.get("sltp_modify_comment") is not None
        assert result.get("sltp_modify_retcode_meaning") is not None
        assert result.get("emergency_close_required") is True
        assert result.get("emergency_close_result") is not None

    def test_09_no_hardcoded_action_2_in_sltp_request(self):
        """Source inspection: no hardcoded action=2 in _modify_position_sltp."""
        from titan.production import mt5_execution_adapter
        src = inspect.getsource(mt5_execution_adapter)
        # The _modify_position_sltp method should use action_sltp (runtime)
        # not the literal _TRADE_ACTION_SLTP constant directly
        method_src = src.split("def _modify_position_sltp")[1].split("def _try_naked_order_fallback")[0]
        # Should use action_sltp variable, not _TRADE_ACTION_SLTP directly
        assert "action_sltp" in method_src
        # Should NOT have "action": _TRADE_ACTION_SLTP (hardcoded usage)
        assert '"action": _TRADE_ACTION_SLTP' not in method_src
        assert '"action": 2' not in method_src
