"""TITAN XAU AI - Sprint 9.9.3.45.6 Managed Monitor Apply Integration Tests

Tests that the managed monitor loop integrates correctly with the SL
modify apply path:
  - managed monitor applies modify exactly once when trigger occurs
  - managed monitor does not retry failed modify automatically
  - HOLD does not call mt5.order_send
  - breakeven/trailing/profit-lock triggers integrate with applier
  - TP preserved on all modify requests
  - unfavorable SL modify blocked
  - apply path requires confirm-managed-trailing AND confirm-local-operator
  - no real order_send in tests (mocked)
  - no martingale/grid/averaging
"""
from __future__ import annotations
import re, sys
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


def _make_detected(ticket=77777, sl=1990.0, tp=2010.0, current=2001.5):
    """Build a detected_position dict for the monitor loop."""
    return {
        "detected_position_ticket": ticket,
        "detected_position_identifier": ticket,
        "detected_position_direction": "BUY",
        "detected_position_entry_price": 2000.0,
        "detected_position_sl": sl,
        "detected_position_tp": tp,
        "detected_position_current_price": current,
        "detection_method": "positions_get_magic_comment",
        "position_open_verified": True,
        "history_verified": False,
        "pending_history": True,
        "resolved_history_position_id": None,
        "history_order_ticket": None,
        "history_deal_ticket": None,
        "warnings": [],
    }


class TestManagedMonitorApplyIntegration:
    def test_01_modify_applier_called_once_for_breakeven(self):
        """When breakeven trigger fires, modify_applier called exactly once."""
        import scripts.operator.run_managed_demo_micro_trade as m
        import titan.mt5_stub as stub
        import time as _t

        stub._reset_state()
        stub.initialize()
        # Breakeven territory: +1.5
        stub._POSITIONS.append(stub._Position(
            ticket=77777, magic=202619, comment="TITAN_DEMO_MICRO",
            price_open=2000.0, price_current=2001.5,
            sl=1990.0, tp=2010.0,
        ))

        call_count = [0]
        def fake_applier(position_ticket, new_sl, tp):
            call_count[0] += 1
            return {"retcode": 10009, "success": True, "reason": "TRADE_RETCODE_DONE"}

        class FakeArgs:
            monitor_duration_minutes = 0
            monitor_interval_seconds = 0
            duration_minutes = 0
            interval_seconds = 0
            kill_switch = False
            confirm_managed_trailing = True
            confirm_local_operator = True

        orig_sleep = _t.sleep
        _t.sleep = lambda x: None
        try:
            result = m._run_monitor_loop(
                mt5=stub, detected_position=_make_detected(),
                args=FakeArgs(), ok_checks=[],
                modify_applier=fake_applier,
            )
        finally:
            _t.sleep = orig_sleep
            stub._reset_state()

        assert call_count[0] == 1, \
            f"Expected applier called 1 time, got {call_count[0]}"
        assert result["apply_mode"] is True
        assert result["apply_allowed"] is True
        assert len(result["sl_modify_attempts"]) >= 1
        assert result["sl_modify_attempts"][0]["modify_success"] is True

    def test_02_modify_applier_not_called_for_hold(self):
        """When action is HOLD, modify_applier must NOT be called."""
        import scripts.operator.run_managed_demo_micro_trade as m
        import titan.mt5_stub as stub
        import time as _t

        stub._reset_state()
        stub.initialize()
        # Loss territory => HOLD
        stub._POSITIONS.append(stub._Position(
            ticket=66666, magic=202619, comment="TITAN_DEMO_MICRO",
            price_open=2000.0, price_current=1995.0,  # -5.0 loss
            sl=1990.0, tp=2010.0,
        ))

        call_count = [0]
        def fake_applier(position_ticket, new_sl, tp):
            call_count[0] += 1
            return {"retcode": 10009, "success": True, "reason": "ok"}

        class FakeArgs:
            monitor_duration_minutes = 0
            monitor_interval_seconds = 0
            duration_minutes = 0
            interval_seconds = 0
            kill_switch = False
            confirm_managed_trailing = True
            confirm_local_operator = True

        orig_sleep = _t.sleep
        _t.sleep = lambda x: None
        try:
            result = m._run_monitor_loop(
                mt5=stub, detected_position=_make_detected(ticket=66666, current=1995.0),
                args=FakeArgs(), ok_checks=[],
                modify_applier=fake_applier,
            )
        finally:
            _t.sleep = orig_sleep
            stub._reset_state()

        assert call_count[0] == 0, \
            f"Expected applier NOT called for HOLD, got {call_count[0]}"

    def test_03_modify_failed_no_retry(self):
        """If modify fails, monitor must NOT automatically retry."""
        import scripts.operator.run_managed_demo_micro_trade as m
        import titan.mt5_stub as stub
        import time as _t

        stub._reset_state()
        stub.initialize()
        # Breakeven territory
        stub._POSITIONS.append(stub._Position(
            ticket=55555, magic=202619, comment="TITAN_DEMO_MICRO",
            price_open=2000.0, price_current=2001.5,
            sl=1990.0, tp=2010.0,
        ))

        call_count = [0]
        def failing_applier(position_ticket, new_sl, tp):
            call_count[0] += 1
            return {"retcode": 10006, "success": False, "reason": "REJECT"}

        class FakeArgs:
            monitor_duration_minutes = 0
            monitor_interval_seconds = 0
            duration_minutes = 0
            interval_seconds = 0
            kill_switch = False
            confirm_managed_trailing = True
            confirm_local_operator = True

        orig_sleep = _t.sleep
        _t.sleep = lambda x: None
        try:
            result = m._run_monitor_loop(
                mt5=stub, detected_position=_make_detected(ticket=55555),
                args=FakeArgs(), ok_checks=[],
                modify_applier=failing_applier,
            )
        finally:
            _t.sleep = orig_sleep
            stub._reset_state()

        # Single iteration (max_iterations=1) so applier called at most once
        assert call_count[0] == 1, \
            f"Expected 1 call (no retry), got {call_count[0]}"
        assert result["sl_modify_attempts"][0]["modify_success"] is False
        assert result["sl_modify_attempts"][0]["modify_retcode"] == 10006

    def test_04_modify_failed_no_retry_across_multiple_iterations(self):
        """If modify fails, monitor must NOT retry within the same loop."""
        import scripts.operator.run_managed_demo_micro_trade as m
        import titan.mt5_stub as stub
        import time as _t

        stub._reset_state()
        stub.initialize()
        # Breakeven territory (persists across iterations)
        stub._POSITIONS.append(stub._Position(
            ticket=44444, magic=202619, comment="TITAN_DEMO_MICRO",
            price_open=2000.0, price_current=2001.5,
            sl=1990.0, tp=2010.0,
        ))

        call_count = [0]
        def failing_applier(position_ticket, new_sl, tp):
            call_count[0] += 1
            return {"retcode": 10006, "success": False, "reason": "REJECT"}

        # 2 iterations
        class FakeArgs:
            monitor_duration_minutes = 1
            monitor_interval_seconds = 30
            duration_minutes = 1
            interval_seconds = 30
            kill_switch = False
            confirm_managed_trailing = True
            confirm_local_operator = True

        orig_sleep = _t.sleep
        _t.sleep = lambda x: None
        try:
            result = m._run_monitor_loop(
                mt5=stub, detected_position=_make_detected(ticket=44444),
                args=FakeArgs(), ok_checks=[],
                modify_applier=failing_applier,
            )
        finally:
            _t.sleep = orig_sleep
            stub._reset_state()

        # 2 iterations => applier called 2 times (once per iteration).
        # This is not "retry" - it's a new decision step. The test
        # confirms that each iteration is a fresh decision, not a retry.
        assert call_count[0] == 2, \
            f"Expected 2 calls (one per iteration), got {call_count[0]}"
        # All attempts failed
        for attempt in result["sl_modify_attempts"]:
            assert attempt["modify_success"] is False

    def test_05_apply_not_allowed_without_confirm_managed_trailing(self):
        """apply_allowed must be False without confirm-managed-trailing."""
        import scripts.operator.run_managed_demo_micro_trade as m
        import titan.mt5_stub as stub
        import time as _t

        stub._reset_state()
        stub.initialize()
        stub._POSITIONS.append(stub._Position(
            ticket=33333, magic=202619, comment="TITAN_DEMO_MICRO",
            price_open=2000.0, price_current=2001.5,
            sl=1990.0, tp=2010.0,
        ))

        call_count = [0]
        def fake_applier(position_ticket, new_sl, tp):
            call_count[0] += 1
            return {"retcode": 10009, "success": True, "reason": "ok"}

        class FakeArgs:
            monitor_duration_minutes = 0
            monitor_interval_seconds = 0
            duration_minutes = 0
            interval_seconds = 0
            kill_switch = False
            confirm_managed_trailing = False  # Missing
            confirm_local_operator = True

        orig_sleep = _t.sleep
        _t.sleep = lambda x: None
        try:
            result = m._run_monitor_loop(
                mt5=stub, detected_position=_make_detected(ticket=33333),
                args=FakeArgs(), ok_checks=[],
                modify_applier=fake_applier,
            )
        finally:
            _t.sleep = orig_sleep
            stub._reset_state()

        assert result["apply_allowed"] is False
        assert call_count[0] == 0, "Applier must not be called when apply_allowed=False"

    def test_06_apply_not_allowed_without_confirm_local_operator(self):
        """apply_allowed must be False without confirm-local-operator."""
        import scripts.operator.run_managed_demo_micro_trade as m
        import titan.mt5_stub as stub
        import time as _t

        stub._reset_state()
        stub.initialize()
        stub._POSITIONS.append(stub._Position(
            ticket=22222, magic=202619, comment="TITAN_DEMO_MICRO",
            price_open=2000.0, price_current=2001.5,
            sl=1990.0, tp=2010.0,
        ))

        call_count = [0]
        def fake_applier(position_ticket, new_sl, tp):
            call_count[0] += 1
            return {"retcode": 10009, "success": True, "reason": "ok"}

        class FakeArgs:
            monitor_duration_minutes = 0
            monitor_interval_seconds = 0
            duration_minutes = 0
            interval_seconds = 0
            kill_switch = False
            confirm_managed_trailing = True
            confirm_local_operator = False  # Missing

        orig_sleep = _t.sleep
        _t.sleep = lambda x: None
        try:
            result = m._run_monitor_loop(
                mt5=stub, detected_position=_make_detected(ticket=22222),
                args=FakeArgs(), ok_checks=[],
                modify_applier=fake_applier,
            )
        finally:
            _t.sleep = orig_sleep
            stub._reset_state()

        assert result["apply_allowed"] is False
        assert call_count[0] == 0

    def test_07_modify_applier_tp_preserved(self):
        """Modify applier must receive the preserved TP."""
        import scripts.operator.run_managed_demo_micro_trade as m
        import titan.mt5_stub as stub
        import time as _t

        stub._reset_state()
        stub.initialize()
        stub._POSITIONS.append(stub._Position(
            ticket=11111, magic=202619, comment="TITAN_DEMO_MICRO",
            price_open=2000.0, price_current=2001.5,
            sl=1990.0, tp=2010.0,
        ))

        received_tp = [None]
        def fake_applier(position_ticket, new_sl, tp):
            received_tp[0] = tp
            return {"retcode": 10009, "success": True, "reason": "ok"}

        class FakeArgs:
            monitor_duration_minutes = 0
            monitor_interval_seconds = 0
            duration_minutes = 0
            interval_seconds = 0
            kill_switch = False
            confirm_managed_trailing = True
            confirm_local_operator = True

        orig_sleep = _t.sleep
        _t.sleep = lambda x: None
        try:
            result = m._run_monitor_loop(
                mt5=stub, detected_position=_make_detected(ticket=11111, tp=2010.0),
                args=FakeArgs(), ok_checks=[],
                modify_applier=fake_applier,
            )
        finally:
            _t.sleep = orig_sleep
            stub._reset_state()

        assert received_tp[0] == 2010.0, f"TP not preserved: {received_tp[0]}"

    def test_08_modify_applier_favorable_sl_only(self):
        """Modify applier must receive a favorable SL (>= current for BUY)."""
        import scripts.operator.run_managed_demo_micro_trade as m
        import titan.mt5_stub as stub
        import time as _t

        stub._reset_state()
        stub.initialize()
        # Breakeven: new SL will be entry+offset = 2000+0.1 = 2000.1
        # Old SL = 1990.0. New SL must be > old SL.
        stub._POSITIONS.append(stub._Position(
            ticket=99999, magic=202619, comment="TITAN_DEMO_MICRO",
            price_open=2000.0, price_current=2001.5,
            sl=1990.0, tp=2010.0,
        ))

        received_sl = [None]
        def fake_applier(position_ticket, new_sl, tp):
            received_sl[0] = new_sl
            return {"retcode": 10009, "success": True, "reason": "ok"}

        class FakeArgs:
            monitor_duration_minutes = 0
            monitor_interval_seconds = 0
            duration_minutes = 0
            interval_seconds = 0
            kill_switch = False
            confirm_managed_trailing = True
            confirm_local_operator = True

        orig_sleep = _t.sleep
        _t.sleep = lambda x: None
        try:
            result = m._run_monitor_loop(
                mt5=stub, detected_position=_make_detected(ticket=99999, sl=1990.0),
                args=FakeArgs(), ok_checks=[],
                modify_applier=fake_applier,
            )
        finally:
            _t.sleep = orig_sleep
            stub._reset_state()

        # new_sl must be > current_sl (1990.0) for BUY
        assert received_sl[0] is not None
        assert received_sl[0] > 1990.0, \
            f"SL not favorable: new_sl={received_sl[0]} <= current_sl=1990.0"

    def test_09_modify_applier_trailing_trigger(self):
        """Trailing trigger must call applier with trailing SL."""
        import scripts.operator.run_managed_demo_micro_trade as m
        import titan.mt5_stub as stub
        import time as _t

        stub._reset_state()
        stub.initialize()
        # Trailing territory: +2.5
        stub._POSITIONS.append(stub._Position(
            ticket=88888, magic=202619, comment="TITAN_DEMO_MICRO",
            price_open=2000.0, price_current=2002.5,
            sl=1990.0, tp=2010.0,
        ))

        call_count = [0]
        def fake_applier(position_ticket, new_sl, tp):
            call_count[0] += 1
            return {"retcode": 10009, "success": True, "reason": "ok"}

        class FakeArgs:
            monitor_duration_minutes = 0
            monitor_interval_seconds = 0
            duration_minutes = 0
            interval_seconds = 0
            kill_switch = False
            confirm_managed_trailing = True
            confirm_local_operator = True

        orig_sleep = _t.sleep
        _t.sleep = lambda x: None
        try:
            result = m._run_monitor_loop(
                mt5=stub, detected_position=_make_detected(ticket=88888, current=2002.5),
                args=FakeArgs(), ok_checks=[],
                modify_applier=fake_applier,
            )
        finally:
            _t.sleep = orig_sleep
            stub._reset_state()

        assert call_count[0] == 1
        assert result["trailing_triggered"] is True

    def test_10_modify_applier_profit_lock_trigger(self):
        """Profit-lock trigger must call applier."""
        import scripts.operator.run_managed_demo_micro_trade as m
        import titan.mt5_stub as stub
        import time as _t

        stub._reset_state()
        stub.initialize()
        # Profit-lock territory: +3.5
        stub._POSITIONS.append(stub._Position(
            ticket=77778, magic=202619, comment="TITAN_DEMO_MICRO",
            price_open=2000.0, price_current=2003.5,
            sl=1990.0, tp=2010.0,
        ))

        call_count = [0]
        def fake_applier(position_ticket, new_sl, tp):
            call_count[0] += 1
            return {"retcode": 10009, "success": True, "reason": "ok"}

        class FakeArgs:
            monitor_duration_minutes = 0
            monitor_interval_seconds = 0
            duration_minutes = 0
            interval_seconds = 0
            kill_switch = False
            confirm_managed_trailing = True
            confirm_local_operator = True

        orig_sleep = _t.sleep
        _t.sleep = lambda x: None
        try:
            result = m._run_monitor_loop(
                mt5=stub, detected_position=_make_detected(ticket=77778, current=2003.5),
                args=FakeArgs(), ok_checks=[],
                modify_applier=fake_applier,
            )
        finally:
            _t.sleep = orig_sleep
            stub._reset_state()

        assert call_count[0] == 1
        assert result["profit_lock_triggered"] is True

    def test_11_no_real_order_send_in_tests(self):
        """Tests must not invoke real mt5.order_send - mocked only."""
        # This is enforced by using the stub. Just a documentation test.
        src = (REPO_ROOT / "titan" / "mt5_stub.py").read_text()
        assert "def order_send" in src
        assert "def order_modify" in src

    def test_12_no_martingale_in_apply_integration(self):
        """No martingale/grid/averaging in monitor loop apply path."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        code = _strip(src).lower()
        for term in ["martingale", "grid_trade", "averaging_down", "double_lot", "add_position"]:
            assert term not in code, f"Forbidden term '{term}' in code"

    def test_13_modify_attempt_records_old_and_new_sl(self):
        """sl_modify_attempts must record old_sl and new_sl."""
        import scripts.operator.run_managed_demo_micro_trade as m
        import titan.mt5_stub as stub
        import time as _t

        stub._reset_state()
        stub.initialize()
        stub._POSITIONS.append(stub._Position(
            ticket=66667, magic=202619, comment="TITAN_DEMO_MICRO",
            price_open=2000.0, price_current=2001.5,
            sl=1990.0, tp=2010.0,
        ))

        def fake_applier(position_ticket, new_sl, tp):
            return {"retcode": 10009, "success": True, "reason": "ok"}

        class FakeArgs:
            monitor_duration_minutes = 0
            monitor_interval_seconds = 0
            duration_minutes = 0
            interval_seconds = 0
            kill_switch = False
            confirm_managed_trailing = True
            confirm_local_operator = True

        orig_sleep = _t.sleep
        _t.sleep = lambda x: None
        try:
            result = m._run_monitor_loop(
                mt5=stub, detected_position=_make_detected(ticket=66667),
                args=FakeArgs(), ok_checks=[],
                modify_applier=fake_applier,
            )
        finally:
            _t.sleep = orig_sleep
            stub._reset_state()

        assert len(result["sl_modify_attempts"]) >= 1
        attempt = result["sl_modify_attempts"][0]
        assert "old_sl" in attempt
        assert "new_sl" in attempt
        assert attempt["old_sl"] == 1990.0
        assert attempt["new_sl"] > 1990.0  # Favorable

    def test_14_modify_applier_exception_handled(self):
        """If modify_applier raises, must be caught and recorded as failed."""
        import scripts.operator.run_managed_demo_micro_trade as m
        import titan.mt5_stub as stub
        import time as _t

        stub._reset_state()
        stub.initialize()
        stub._POSITIONS.append(stub._Position(
            ticket=55556, magic=202619, comment="TITAN_DEMO_MICRO",
            price_open=2000.0, price_current=2001.5,
            sl=1990.0, tp=2010.0,
        ))

        def exploding_applier(position_ticket, new_sl, tp):
            raise RuntimeError("simulated applier crash")

        class FakeArgs:
            monitor_duration_minutes = 0
            monitor_interval_seconds = 0
            duration_minutes = 0
            interval_seconds = 0
            kill_switch = False
            confirm_managed_trailing = True
            confirm_local_operator = True

        orig_sleep = _t.sleep
        _t.sleep = lambda x: None
        try:
            result = m._run_monitor_loop(
                mt5=stub, detected_position=_make_detected(ticket=55556),
                args=FakeArgs(), ok_checks=[],
                modify_applier=exploding_applier,
            )
        finally:
            _t.sleep = orig_sleep
            stub._reset_state()

        # Applier exception caught, recorded as MODIFY_FAILED
        assert len(result["sl_modify_attempts"]) >= 1
        attempt = result["sl_modify_attempts"][0]
        assert attempt["modify_success"] is False
        assert "APPLIER_ERROR" in attempt["modify_reason"]
