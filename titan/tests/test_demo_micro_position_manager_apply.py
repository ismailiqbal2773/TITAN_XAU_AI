"""TITAN XAU AI - Sprint 9.9.3.45.6 Demo Micro Position Manager Apply Tests

Tests for scripts/operator/manage_demo_micro_position.py apply-once path:
  - HOLD does not call mt5.order_send
  - breakeven trigger builds favorable SL modify
  - trailing trigger builds favorable SL modify
  - profit-lock trigger builds favorable SL modify
  - TP preserved on all modify requests
  - unfavorable SL modify blocked
  - apply-once requires local token
  - apply-once requires confirm-managed-trailing
  - apply-once blocks real account
  - apply-once blocks non-MetaQuotes-Demo
  - no real order_send in tests (mocked)
  - no martingale/grid/averaging
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


class TestPositionManagerApply:
    def test_01_apply_once_function_exists(self):
        """run_apply_once function must exist."""
        src = (REPO_ROOT / "scripts" / "operator" / "manage_demo_micro_position.py").read_text()
        assert "def run_apply_once" in src

    def test_02_apply_once_requires_confirm_local_operator(self):
        """apply-once must require --confirm-local-operator."""
        import scripts.operator.manage_demo_micro_position as mp

        class FakeArgs:
            confirm_local_operator = False
            confirm_managed_trailing = True
        result = mp.run_apply_once(FakeArgs())
        assert result["verdict"] == "MANAGE_REFUSED"
        assert any("confirm-local-operator" in b.lower() for b in result["blockers"])

    def test_03_apply_once_requires_confirm_managed_trailing(self):
        """apply-once must require --confirm-managed-trailing."""
        import scripts.operator.manage_demo_micro_position as mp

        class FakeArgs:
            confirm_local_operator = True
            confirm_managed_trailing = False
        result = mp.run_apply_once(FakeArgs())
        assert result["verdict"] == "MANAGE_REFUSED"
        assert any("confirm-managed-trailing" in b.lower() for b in result["blockers"])

    def test_04_apply_once_requires_valid_token(self, monkeypatch):
        """apply-once must require valid local operator token."""
        import scripts.operator.manage_demo_micro_position as mp
        from scripts.operator import create_local_operator_execution_token as tok_mod

        # Patch token to be invalid
        monkeypatch.setattr(tok_mod, "load_and_validate_token",
                            lambda: {"valid": False, "reason": "Token file not found", "token": None})

        class FakeArgs:
            confirm_local_operator = True
            confirm_managed_trailing = True
        result = mp.run_apply_once(FakeArgs())
        assert result["verdict"] == "MANAGE_REFUSED"
        assert any("LOCAL_TOKEN_INVALID" in b for b in result["blockers"])

    def test_05_apply_once_blocks_real_account(self, monkeypatch):
        """apply-once must block real (non-DEMO) account."""
        import scripts.operator.manage_demo_micro_position as mp
        import titan.mt5_stub as stub
        from scripts.operator import create_local_operator_execution_token as tok_mod

        # Valid token
        monkeypatch.setattr(tok_mod, "load_and_validate_token",
                            lambda: {"valid": True, "reason": "ok",
                                     "token": {"git_commit": "abc", "expires_utc": "2099-01-01T00:00:00+00:00"}})

        # Reset stub and patch account_info to return real account
        stub._reset_state()
        orig_account_info = stub.account_info

        class FakeAccount:
            server = "MetaQuotes-Demo"
            trade_mode = 1  # REAL account
            login = 12345

        def fake_account_info():
            return FakeAccount()

        monkeypatch.setattr(stub, "account_info", fake_account_info)
        # Also patch in sys.modules
        import sys as _sys
        monkeypatch.setattr(_sys.modules["MetaTrader5"], "account_info", fake_account_info)

        class FakeArgs:
            confirm_local_operator = True
            confirm_managed_trailing = True

        try:
            result = mp.run_apply_once(FakeArgs())
        finally:
            stub._reset_state()

        assert result["verdict"] == "MANAGE_REFUSED"
        assert any("ACCOUNT_NOT_DEMO" in b for b in result["blockers"])

    def test_06_apply_once_blocks_non_metaquotes_demo(self, monkeypatch):
        """apply-once must block non-MetaQuotes-Demo broker."""
        import scripts.operator.manage_demo_micro_position as mp
        import titan.mt5_stub as stub
        from scripts.operator import create_local_operator_execution_token as tok_mod

        monkeypatch.setattr(tok_mod, "load_and_validate_token",
                            lambda: {"valid": True, "reason": "ok",
                                     "token": {"git_commit": "abc", "expires_utc": "2099-01-01T00:00:00+00:00"}})

        stub._reset_state()

        class FakeAccount:
            server = "FundedNext-Real"  # Wrong broker
            trade_mode = 0  # DEMO
            login = 12345

        def fake_account_info():
            return FakeAccount()

        monkeypatch.setattr(stub, "account_info", fake_account_info)
        import sys as _sys
        monkeypatch.setattr(_sys.modules["MetaTrader5"], "account_info", fake_account_info)

        class FakeArgs:
            confirm_local_operator = True
            confirm_managed_trailing = True

        try:
            result = mp.run_apply_once(FakeArgs())
        finally:
            stub._reset_state()

        assert result["verdict"] == "MANAGE_REFUSED"
        assert any("BROKER_NOT_METAQUOTES_DEMO" in b for b in result["blockers"])

    def test_07_apply_once_blocks_no_open_position(self, monkeypatch):
        """apply-once must block when no open TITAN position."""
        import scripts.operator.manage_demo_micro_position as mp
        import titan.mt5_stub as stub
        from scripts.operator import create_local_operator_execution_token as tok_mod

        monkeypatch.setattr(tok_mod, "load_and_validate_token",
                            lambda: {"valid": True, "reason": "ok",
                                     "token": {"git_commit": "abc", "expires_utc": "2099-01-01T00:00:00+00:00"}})

        stub._reset_state()
        stub.initialize()
        # No positions in stub

        class FakeArgs:
            confirm_local_operator = True
            confirm_managed_trailing = True

        try:
            result = mp.run_apply_once(FakeArgs())
        finally:
            stub._reset_state()

        assert result["verdict"] == "MANAGE_REFUSED"
        assert any("NO_OPEN_TITAN_POSITION" in b for b in result["blockers"])

    def test_08_apply_once_blocks_multiple_positions(self, monkeypatch):
        """apply-once must block when multiple TITAN positions open."""
        import scripts.operator.manage_demo_micro_position as mp
        import titan.mt5_stub as stub
        from scripts.operator import create_local_operator_execution_token as tok_mod

        monkeypatch.setattr(tok_mod, "load_and_validate_token",
                            lambda: {"valid": True, "reason": "ok",
                                     "token": {"git_commit": "abc", "expires_utc": "2099-01-01T00:00:00+00:00"}})

        stub._reset_state()
        stub.initialize()
        # Add two TITAN positions
        stub._POSITIONS.append(stub._Position(ticket=1, magic=202619, comment="TITAN_DEMO_MICRO"))
        stub._POSITIONS.append(stub._Position(ticket=2, magic=202619, comment="TITAN_DEMO_MICRO"))

        class FakeArgs:
            confirm_local_operator = True
            confirm_managed_trailing = True

        try:
            result = mp.run_apply_once(FakeArgs())
        finally:
            stub._reset_state()

        assert result["verdict"] == "MANAGE_REFUSED"
        assert any("MULTIPLE_TITAN_POSITIONS" in b for b in result["blockers"])

    def test_09_apply_once_hold_does_not_send_order(self, monkeypatch):
        """If action is HOLD, mt5.order_send must NOT be called."""
        import scripts.operator.manage_demo_micro_position as mp
        import titan.mt5_stub as stub
        from scripts.operator import create_local_operator_execution_token as tok_mod

        monkeypatch.setattr(tok_mod, "load_and_validate_token",
                            lambda: {"valid": True, "reason": "ok",
                                     "token": {"git_commit": "abc", "expires_utc": "2099-01-01T00:00:00+00:00"}})

        stub._reset_state()
        stub.initialize()
        # Position in loss territory => HOLD
        stub._POSITIONS.append(stub._Position(
            ticket=99999, magic=202619, comment="TITAN_DEMO_MICRO",
            price_open=2000.0, price_current=1995.0,  # Loss
            sl=1990.0, tp=2010.0,
        ))

        class FakeArgs:
            confirm_local_operator = True
            confirm_managed_trailing = True

        try:
            result = mp.run_apply_once(FakeArgs())
            # Check no order_send was called
            assert len(stub._ORDER_SEND_CALLS) == 0, \
                f"order_send was called {len(stub._ORDER_SEND_CALLS)} times for HOLD"
        finally:
            stub._reset_state()

        assert result["verdict"] == "MANAGE_HOLD_NO_MODIFY"
        assert result["sl_modify_attempted"] is False

    def test_10_apply_once_breakeven_modify_success(self, monkeypatch):
        """If action is BREAKEVEN, mt5.order_send called once, success."""
        import scripts.operator.manage_demo_micro_position as mp
        import titan.mt5_stub as stub
        from scripts.operator import create_local_operator_execution_token as tok_mod

        monkeypatch.setattr(tok_mod, "load_and_validate_token",
                            lambda: {"valid": True, "reason": "ok",
                                     "token": {"git_commit": "abc", "expires_utc": "2099-01-01T00:00:00+00:00"}})

        stub._reset_state()
        stub.initialize()
        # Position in breakeven territory: profit_distance=+1.5
        stub._POSITIONS.append(stub._Position(
            ticket=88888, magic=202619, comment="TITAN_DEMO_MICRO",
            price_open=2000.0, price_current=2001.5,  # +1.5 profit
            sl=1990.0, tp=2010.0,
        ))

        class FakeArgs:
            confirm_local_operator = True
            confirm_managed_trailing = True

        try:
            result = mp.run_apply_once(FakeArgs())
            assert len(stub._ORDER_SEND_CALLS) == 1, \
                f"Expected 1 order_send call for breakeven modify, got {len(stub._ORDER_SEND_CALLS)}"
        finally:
            stub._reset_state()

        assert result["verdict"] == "MANAGE_MODIFY_SUCCESS"
        assert result["sl_modify_attempted"] is True
        assert result["sl_modify_retcode"] == 10009
        assert result["modify_success"] is True
        assert result["tp_preserved"] is True
        # SL moved up (BUY)
        assert result["new_sl"] > result["old_sl"]

    def test_11_apply_once_trailing_modify_success(self, monkeypatch):
        """If action is TRAIL, mt5.order_send called once, success."""
        import scripts.operator.manage_demo_micro_position as mp
        import titan.mt5_stub as stub
        from scripts.operator import create_local_operator_execution_token as tok_mod

        monkeypatch.setattr(tok_mod, "load_and_validate_token",
                            lambda: {"valid": True, "reason": "ok",
                                     "token": {"git_commit": "abc", "expires_utc": "2099-01-01T00:00:00+00:00"}})

        stub._reset_state()
        stub.initialize()
        # Position in trailing territory: profit_distance=+2.5
        stub._POSITIONS.append(stub._Position(
            ticket=77777, magic=202619, comment="TITAN_DEMO_MICRO",
            price_open=2000.0, price_current=2002.5,  # +2.5 profit
            sl=1990.0, tp=2010.0,
        ))

        class FakeArgs:
            confirm_local_operator = True
            confirm_managed_trailing = True

        try:
            result = mp.run_apply_once(FakeArgs())
            assert len(stub._ORDER_SEND_CALLS) == 1, \
                f"Expected 1 order_send call for trailing modify, got {len(stub._ORDER_SEND_CALLS)}"
        finally:
            stub._reset_state()

        assert result["verdict"] == "MANAGE_MODIFY_SUCCESS"
        assert result["sl_modify_attempted"] is True
        assert result["modify_success"] is True
        assert result["tp_preserved"] is True

    def test_12_apply_once_profit_lock_modify_success(self, monkeypatch):
        """If action is PROFIT_LOCK, mt5.order_send called once, success."""
        import scripts.operator.manage_demo_micro_position as mp
        import titan.mt5_stub as stub
        from scripts.operator import create_local_operator_execution_token as tok_mod

        monkeypatch.setattr(tok_mod, "load_and_validate_token",
                            lambda: {"valid": True, "reason": "ok",
                                     "token": {"git_commit": "abc", "expires_utc": "2099-01-01T00:00:00+00:00"}})

        stub._reset_state()
        stub.initialize()
        # Position in profit-lock territory: profit_distance=+3.5
        stub._POSITIONS.append(stub._Position(
            ticket=66666, magic=202619, comment="TITAN_DEMO_MICRO",
            price_open=2000.0, price_current=2003.5,  # +3.5 profit
            sl=1990.0, tp=2010.0,
        ))

        class FakeArgs:
            confirm_local_operator = True
            confirm_managed_trailing = True

        try:
            result = mp.run_apply_once(FakeArgs())
            assert len(stub._ORDER_SEND_CALLS) == 1, \
                f"Expected 1 order_send call for profit-lock modify, got {len(stub._ORDER_SEND_CALLS)}"
        finally:
            stub._reset_state()

        assert result["verdict"] == "MANAGE_MODIFY_SUCCESS"
        assert result["sl_modify_attempted"] is True
        assert result["modify_success"] is True
        assert result["tp_preserved"] is True

    def test_13_apply_once_modify_failed_retcode(self, monkeypatch):
        """If mt5.order_send returns failure retcode, modify_failed."""
        import scripts.operator.manage_demo_micro_position as mp
        import titan.mt5_stub as stub
        from scripts.operator import create_local_operator_execution_token as tok_mod

        monkeypatch.setattr(tok_mod, "load_and_validate_token",
                            lambda: {"valid": True, "reason": "ok",
                                     "token": {"git_commit": "abc", "expires_utc": "2099-01-01T00:00:00+00:00"}})

        stub._reset_state()
        stub.initialize()
        # Set order result to failure
        stub._ORDER_RESULT = {
            "retcode": 10006,  # REJECT
            "comment": "TRADE_RETCODE_REJECT",
            "order": 0, "deal": 0, "position_id": 0,
            "volume": 0.01, "price": 2000.0, "bid": 2000.0, "ask": 2000.0,
            "request_id": 0, "retcode_external": 0,
        }
        stub._ORDER_MODIFY_RESULT = {
            "retcode": 10006,
            "comment": "TRADE_RETCODE_REJECT",
        }
        # Position in breakeven territory
        stub._POSITIONS.append(stub._Position(
            ticket=55555, magic=202619, comment="TITAN_DEMO_MICRO",
            price_open=2000.0, price_current=2001.5,
            sl=1990.0, tp=2010.0,
        ))

        class FakeArgs:
            confirm_local_operator = True
            confirm_managed_trailing = True

        try:
            result = mp.run_apply_once(FakeArgs())
        finally:
            stub._reset_state()

        assert result["verdict"] == "MANAGE_MODIFY_FAILED"
        assert result["sl_modify_attempted"] is True
        assert result["modify_success"] is False
        assert result["sl_modify_retcode"] == 10006

    def test_14_apply_once_tp_preserved(self, monkeypatch):
        """TP must be preserved in modify request."""
        import scripts.operator.manage_demo_micro_position as mp
        import titan.mt5_stub as stub
        from scripts.operator import create_local_operator_execution_token as tok_mod

        monkeypatch.setattr(tok_mod, "load_and_validate_token",
                            lambda: {"valid": True, "reason": "ok",
                                     "token": {"git_commit": "abc", "expires_utc": "2099-01-01T00:00:00+00:00"}})

        stub._reset_state()
        stub.initialize()
        stub._POSITIONS.append(stub._Position(
            ticket=44444, magic=202619, comment="TITAN_DEMO_MICRO",
            price_open=2000.0, price_current=2001.5,
            sl=1990.0, tp=2010.0,  # TP
        ))

        class FakeArgs:
            confirm_local_operator = True
            confirm_managed_trailing = True

        try:
            result = mp.run_apply_once(FakeArgs())
            # Inspect the modify request
            assert len(stub._ORDER_SEND_CALLS) == 1
            modify_request = stub._ORDER_SEND_CALLS[0]
            assert modify_request["tp"] == 2010.0  # TP preserved
            assert modify_request["action"] == stub.TRADE_ACTION_SLTP
            assert modify_request["symbol"] == "XAUUSD"
            assert modify_request["position"] == 44444
        finally:
            stub._reset_state()

        assert result["tp_preserved"] is True

    def test_15_apply_once_favorable_only(self):
        """Source must enforce favorable-only SL."""
        src = (REPO_ROOT / "scripts" / "operator" / "manage_demo_micro_position.py").read_text()
        assert "UNFAVORABLE_SL_BLOCKED" in src

    def test_16_apply_once_no_widening(self):
        """Source must block SL widening."""
        src = (REPO_ROOT / "scripts" / "operator" / "manage_demo_micro_position.py").read_text()
        assert "SL_WIDENING_BLOCKED" in src

    def test_17_apply_once_records_modify_fields(self):
        """Source must record modify fields."""
        src = (REPO_ROOT / "scripts" / "operator" / "manage_demo_micro_position.py").read_text()
        for field in [
            "sl_modify_attempted", "sl_modify_retcode", "old_sl", "new_sl",
            "tp_preserved", "modify_reason", "modify_success",
        ]:
            assert field in src, f"Missing modify field: {field}"

    def test_18_apply_once_uses_trade_action_sltp(self):
        """Apply must use TRADE_ACTION_SLTP."""
        src = (REPO_ROOT / "scripts" / "operator" / "manage_demo_micro_position.py").read_text()
        assert "TRADE_ACTION_SLTP" in src

    def test_19_no_martingale_in_apply(self):
        """No martingale/grid/averaging in apply-once."""
        src = (REPO_ROOT / "scripts" / "operator" / "manage_demo_micro_position.py").read_text()
        code = _strip(src).lower()
        for term in ["martingale", "grid_trade", "averaging_down", "double_lot", "add_position"]:
            assert term not in code, f"Forbidden term '{term}' in code"

    def test_20_no_mojibake(self):
        src = (REPO_ROOT / "scripts" / "operator" / "manage_demo_micro_position.py").read_text()
        assert "\u2014" not in src
        assert "\u2013" not in src

    def test_21_apply_once_blocks_magic_mismatch(self, monkeypatch):
        """apply-once must block when position magic != 202619."""
        import scripts.operator.manage_demo_micro_position as mp
        import titan.mt5_stub as stub
        from scripts.operator import create_local_operator_execution_token as tok_mod

        monkeypatch.setattr(tok_mod, "load_and_validate_token",
                            lambda: {"valid": True, "reason": "ok",
                                     "token": {"git_commit": "abc", "expires_utc": "2099-01-01T00:00:00+00:00"}})

        stub._reset_state()
        stub.initialize()
        # Wrong magic
        stub._POSITIONS.append(stub._Position(
            ticket=33333, magic=999999, comment="OTHER_STRATEGY",
            price_open=2000.0, price_current=2001.5,
            sl=1990.0, tp=2010.0,
        ))

        class FakeArgs:
            confirm_local_operator = True
            confirm_managed_trailing = True

        try:
            result = mp.run_apply_once(FakeArgs())
        finally:
            stub._reset_state()

        # No TITAN position found (magic mismatch filters it out)
        assert result["verdict"] == "MANAGE_REFUSED"
        assert any("NO_OPEN_TITAN_POSITION" in b for b in result["blockers"])

    def test_22_apply_once_modify_request_has_correct_fields(self, monkeypatch):
        """Modify request must have action, symbol, position, sl, tp fields."""
        import scripts.operator.manage_demo_micro_position as mp
        import titan.mt5_stub as stub
        from scripts.operator import create_local_operator_execution_token as tok_mod

        monkeypatch.setattr(tok_mod, "load_and_validate_token",
                            lambda: {"valid": True, "reason": "ok",
                                     "token": {"git_commit": "abc", "expires_utc": "2099-01-01T00:00:00+00:00"}})

        stub._reset_state()
        stub.initialize()
        stub._POSITIONS.append(stub._Position(
            ticket=22222, magic=202619, comment="TITAN_DEMO_MICRO",
            price_open=2000.0, price_current=2002.5,  # Trailing
            sl=1990.0, tp=2010.0,
        ))

        class FakeArgs:
            confirm_local_operator = True
            confirm_managed_trailing = True

        try:
            result = mp.run_apply_once(FakeArgs())
            assert len(stub._ORDER_SEND_CALLS) == 1
            req = stub._ORDER_SEND_CALLS[0]
            assert "action" in req
            assert "symbol" in req
            assert "position" in req
            assert "sl" in req
            assert "tp" in req
        finally:
            stub._reset_state()

        assert result["modify_success"] is True

    # === Sprint 9.9.3.45.8 adaptive integration ===

    def test_23_position_manager_supports_adaptive_mode(self):
        """DemoMicroPositionManager must support legacy_mode=False."""
        from titan.production.demo_micro_position_manager import DemoMicroPositionManager
        from titan.production.adaptive_trailing_policy import AdaptiveTrailingPolicy
        mgr = DemoMicroPositionManager(legacy_mode=False)
        assert mgr.legacy_mode is False
        assert isinstance(mgr.adaptive_policy, AdaptiveTrailingPolicy)

    def test_24_adaptive_mode_returns_phase_field(self):
        """Adaptive mode evaluation must populate phase field."""
        from titan.production.demo_micro_position_manager import (
            DemoMicroPositionManager, SLAction,
        )
        from titan.production.adaptive_trailing_policy import Regime
        mgr = DemoMicroPositionManager(legacy_mode=False)
        rec = mgr.evaluate(
            direction="BUY", entry_price=2000.0, current_price=2010.0,
            current_sl=1990.0, current_tp=2020.0,
            initial_sl=1990.0, atr=1.0, spread=0.05,
            stops_level_points=0, point=0.01,
            regime=Regime.TREND, structure_buffer=0.0,
            hold_seconds=120, monitor_iterations=5,
            seconds_since_last_modify=999,
            spread_spike_flag=False, news_flag=False,
        )
        assert rec.phase != ""
        assert rec.phase.startswith("PHASE_")
        assert rec.profit_R > 0

    def test_25_adaptive_mode_no_sl_move_before_min_hold(self):
        """Adaptive mode must NOT move SL before min hold time."""
        from titan.production.demo_micro_position_manager import (
            DemoMicroPositionManager, SLAction,
        )
        from titan.production.adaptive_trailing_policy import Regime
        mgr = DemoMicroPositionManager(legacy_mode=False)
        rec = mgr.evaluate(
            direction="BUY", entry_price=2000.0, current_price=2015.0,
            current_sl=1990.0, current_tp=2030.0,
            initial_sl=1990.0, atr=1.0, spread=0.05,
            stops_level_points=0, point=0.01,
            regime=Regime.TREND, structure_buffer=0.0,
            hold_seconds=30,  # Below min_hold_seconds=60
            monitor_iterations=5,
            seconds_since_last_modify=999,
            spread_spike_flag=False, news_flag=False,
        )
        assert rec.action == SLAction.HOLD
        assert rec.phase == "PHASE_0_INITIAL_PROTECTION"

    def test_26_adaptive_mode_no_sl_move_below_1R(self):
        """Adaptive mode must NOT move SL when profit_R < 1.0."""
        from titan.production.demo_micro_position_manager import (
            DemoMicroPositionManager, SLAction,
        )
        from titan.production.adaptive_trailing_policy import Regime
        mgr = DemoMicroPositionManager(legacy_mode=False)
        rec = mgr.evaluate(
            direction="BUY", entry_price=2000.0, current_price=2005.0,
            current_sl=1990.0, current_tp=2020.0,
            initial_sl=1990.0, atr=1.0, spread=0.05,
            stops_level_points=0, point=0.01,
            regime=Regime.TREND, structure_buffer=0.0,
            hold_seconds=120, monitor_iterations=5,
            seconds_since_last_modify=999,
            spread_spike_flag=False, news_flag=False,
        )
        assert rec.action == SLAction.HOLD
        assert rec.phase == "PHASE_1_NOISE_FILTER"

    def test_27_adaptive_mode_spread_spike_blocks_modify(self):
        """Adaptive mode must block modify when spread spike flag is set."""
        from titan.production.demo_micro_position_manager import (
            DemoMicroPositionManager, SLAction,
        )
        from titan.production.adaptive_trailing_policy import Regime
        mgr = DemoMicroPositionManager(legacy_mode=False)
        rec = mgr.evaluate(
            direction="BUY", entry_price=2000.0, current_price=2010.0,
            current_sl=1990.0, current_tp=2020.0,
            initial_sl=1990.0, atr=1.0, spread=0.05,
            stops_level_points=0, point=0.01,
            regime=Regime.TREND, structure_buffer=0.0,
            hold_seconds=120, monitor_iterations=5,
            seconds_since_last_modify=999,
            spread_spike_flag=True,  # Spread spike
            news_flag=False,
        )
        assert rec.action == SLAction.HOLD
        assert any("SPREAD_SPIKE_FLAG_ACTIVE" in b for b in rec.anti_whipsaw_blocks)

    def test_28_adaptive_mode_breakeven_after_1R(self):
        """Adaptive mode must MOVE_TO_BREAKEVEN after 1R + noise clear."""
        from titan.production.demo_micro_position_manager import (
            DemoMicroPositionManager, SLAction,
        )
        from titan.production.adaptive_trailing_policy import Regime
        mgr = DemoMicroPositionManager(legacy_mode=False)
        rec = mgr.evaluate(
            direction="BUY", entry_price=2000.0, current_price=2010.0,
            current_sl=1990.0, current_tp=2020.0,
            initial_sl=1990.0, atr=1.0, spread=0.05,
            stops_level_points=0, point=0.01,
            regime=Regime.TREND, structure_buffer=0.0,
            hold_seconds=120, monitor_iterations=5,
            seconds_since_last_modify=999,
            spread_spike_flag=False, news_flag=False,
        )
        assert rec.action == SLAction.MOVE_TO_BREAKEVEN
        assert rec.phase == "PHASE_2_SOFT_BREAKEVEN"
        assert rec.favorable is True

    def test_29_adaptive_mode_trend_trail_wider_than_range(self):
        """Adaptive mode trend trailing distance > range trailing distance."""
        from titan.production.demo_micro_position_manager import (
            DemoMicroPositionManager,
        )
        from titan.production.adaptive_trailing_policy import Regime
        mgr = DemoMicroPositionManager(legacy_mode=False)
        # Trend
        rec_trend = mgr.evaluate(
            direction="BUY", entry_price=2000.0, current_price=2020.0,
            current_sl=1990.0, current_tp=2040.0,
            initial_sl=1990.0, atr=1.0, spread=0.05,
            stops_level_points=0, point=0.01,
            regime=Regime.TREND, structure_buffer=0.0,
            hold_seconds=120, monitor_iterations=5,
            seconds_since_last_modify=999,
            spread_spike_flag=False, news_flag=False,
        )
        # Range
        rec_range = mgr.evaluate(
            direction="BUY", entry_price=2000.0, current_price=2020.0,
            current_sl=1990.0, current_tp=2040.0,
            initial_sl=1990.0, atr=1.0, spread=0.05,
            stops_level_points=0, point=0.01,
            regime=Regime.RANGE, structure_buffer=0.0,
            hold_seconds=120, monitor_iterations=5,
            seconds_since_last_modify=999,
            spread_spike_flag=False, news_flag=False,
        )
        # Trend multiplier (2.0) > Range multiplier (1.0)
        assert rec_trend.trailing_distance > rec_range.trailing_distance

    def test_30_adaptive_mode_no_widening(self):
        """Adaptive mode must NOT widen SL on pullback."""
        from titan.production.demo_micro_position_manager import (
            DemoMicroPositionManager, SLAction,
        )
        from titan.production.adaptive_trailing_policy import Regime
        mgr = DemoMicroPositionManager(legacy_mode=False)
        # current_sl=2018 (trailed), price pulled back to 2015
        rec = mgr.evaluate(
            direction="BUY", entry_price=2000.0, current_price=2015.0,
            current_sl=2018.0, current_tp=2040.0,
            initial_sl=1990.0, atr=1.0, spread=0.05,
            stops_level_points=0, point=0.01,
            regime=Regime.TREND, structure_buffer=0.0,
            hold_seconds=120, monitor_iterations=5,
            seconds_since_last_modify=999,
            spread_spike_flag=False, news_flag=False,
        )
        # No widening: final_sl must be >= current_sl (2018) for BUY
        assert rec.final_sl >= 2018.0
        assert rec.action in (SLAction.HOLD, SLAction.BLOCKED)

    def test_31_adaptive_mode_tp_preserved(self):
        """Adaptive mode must preserve TP."""
        from titan.production.demo_micro_position_manager import (
            DemoMicroPositionManager,
        )
        from titan.production.adaptive_trailing_policy import Regime
        mgr = DemoMicroPositionManager(legacy_mode=False)
        rec = mgr.evaluate(
            direction="BUY", entry_price=2000.0, current_price=2020.0,
            current_sl=1990.0, current_tp=2040.0,
            initial_sl=1990.0, atr=1.0, spread=0.05,
            stops_level_points=0, point=0.01,
            regime=Regime.TREND, structure_buffer=0.0,
            hold_seconds=120, monitor_iterations=5,
            seconds_since_last_modify=999,
            spread_spike_flag=False, news_flag=False,
        )
        assert rec.tp_preserved is True

    def test_32_adaptive_mode_cooldown_blocks_repeated_modify(self):
        """Adaptive mode must block modify when cooldown active."""
        from titan.production.demo_micro_position_manager import (
            DemoMicroPositionManager, SLAction,
        )
        from titan.production.adaptive_trailing_policy import Regime
        mgr = DemoMicroPositionManager(legacy_mode=False)
        rec = mgr.evaluate(
            direction="BUY", entry_price=2000.0, current_price=2018.0,
            current_sl=1990.0, current_tp=2030.0,
            initial_sl=1990.0, atr=1.0, spread=0.05,
            stops_level_points=0, point=0.01,
            regime=Regime.TREND, structure_buffer=0.0,
            hold_seconds=120, monitor_iterations=5,
            seconds_since_last_modify=10,  # Within cooldown
            spread_spike_flag=False, news_flag=False,
        )
        assert rec.action == SLAction.HOLD
        assert any("COOLDOWN_ACTIVE" in b for b in rec.anti_whipsaw_blocks)
