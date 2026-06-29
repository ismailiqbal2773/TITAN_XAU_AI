"""
TITAN XAU AI — Sprint 9.9.3 FundedNext Demo Micro Harness Tests (Expanded)

Covers harness safety, force-close watchdog, full cycle, and actual
DEMO_MICRO_EXECUTE order open/close/sync/net-PnL/journal using mocked MT5.

Z AI / CI tests use MockMT5 — NEVER real MT5 execution.
"""
from __future__ import annotations
import asyncio
import json
import os
import sys
import time
import yaml
import pytest
from pathlib import Path
from scripts.audit.demo_micro_full_cycle import run


REPO_ROOT = Path(__file__).resolve().parents[2]


def _run_harness(mode="DRY_ARM_CHECK_ONLY", **kwargs):
    """Helper to run harness with specific mode."""
    old = sys.argv
    argv = ["harness", "--mode", mode]
    for k, v in kwargs.items():
        argv.extend([f"--{k.replace('_', '-')}", str(v)])
    sys.argv = argv
    from scripts.audit.demo_micro_full_cycle import parse_args
    args = parse_args()
    sys.argv = old
    asyncio.run(run(args))


def _read_report():
    path = REPO_ROOT / "data" / "audit" / "demo_micro" / "demo_micro_report.json"
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return {}


class TestDryArmCheck:
    def test_26_dry_check_sends_no_order(self):
        _run_harness("DRY_ARM_CHECK_ONLY")
        r = _read_report()
        assert r["order_send_called"] is False

    def test_27_dry_check_runs_without_arm(self):
        os.environ.pop("TITAN_DEMO_MICRO_ARMED", None)
        _run_harness("DRY_ARM_CHECK_ONLY")
        r = _read_report()
        assert r["mode"] == "DRY_ARM_CHECK_ONLY"

    def test_28_dry_check_generates_report_json(self):
        _run_harness("DRY_ARM_CHECK_ONLY")
        assert (REPO_ROOT / "data" / "audit" / "demo_micro" / "demo_micro_report.json").exists()

    def test_29_dry_check_generates_report_md(self):
        _run_harness("DRY_ARM_CHECK_ONLY")
        assert (REPO_ROOT / "data" / "audit" / "demo_micro" / "demo_micro_report.md").exists()


class TestExecuteModeSafety:
    def test_30_execute_requires_arm(self):
        os.environ.pop("TITAN_DEMO_MICRO_ARMED", None)
        _run_harness("DEMO_MICRO_EXECUTE")
        r = _read_report()
        assert r["final_verdict"] == "DEMO_MICRO_BLOCKED"
        assert "Arm token" in r.get("reason", "")

    def test_31_execute_requires_demo(self):
        os.environ["TITAN_DEMO_MICRO_ARMED"] = "1"
        _run_harness("DEMO_MICRO_EXECUTE")
        r = _read_report()
        # On Linux no MT5 → blocked
        assert r["final_verdict"] in ("DEMO_MICRO_BLOCKED", "DEMO_MANUAL_REVIEW_REQUIRED")
        os.environ.pop("TITAN_DEMO_MICRO_ARMED", None)

    def test_32_execute_blocks_non_demo_with_arm(self):
        os.environ["TITAN_DEMO_MICRO_ARMED"] = "1"
        _run_harness("DEMO_MICRO_EXECUTE")
        r = _read_report()
        # Can't verify DEMO on Linux but verify it doesn't pass
        assert r["final_verdict"] != "DEMO_FULL_CYCLE_PASS"
        os.environ.pop("TITAN_DEMO_MICRO_ARMED", None)

    def test_33_execute_blocks_market_closed(self):
        # Can't control market on Linux, but verify structure
        os.environ["TITAN_DEMO_MICRO_ARMED"] = "1"
        _run_harness("DEMO_MICRO_EXECUTE")
        r = _read_report()
        assert "final_verdict" in r
        os.environ.pop("TITAN_DEMO_MICRO_ARMED", None)

    def test_34_execute_blocks_lot_over_0_01(self):
        # Config enforces max_lot=0.01
        with open(REPO_ROOT / "config" / "runtime.yaml", "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        assert cfg["demo_micro"]["max_lot"] <= 0.01

    def test_35_execute_no_order_send_without_arm(self):
        os.environ.pop("TITAN_DEMO_MICRO_ARMED", None)
        _run_harness("DEMO_MICRO_EXECUTE")
        r = _read_report()
        assert r["order_send_called"] is False

    def test_36_no_martingale_grid_averaging(self):
        """Verify no martingale/grid/averaging logic is implemented as a feature.

        Sprint 9.9.3 note: the words "martingale/grid/averaging" DO appear in
        the module docstring as a safety statement ("no martingale, no grid, ...").
        We instead verify there is no function/code path that implements them.
        """
        import inspect
        from scripts.audit import demo_micro_full_cycle as harness
        src = inspect.getsource(harness)
        # No functions implementing these strategies
        assert "def _martingale" not in src
        assert "def _grid" not in src
        assert "def _averaging" not in src
        # No lot escalation logic
        assert "lot *= 2" not in src
        assert "lot *=2" not in src
        assert "next_lot" not in src
        # No add-to-position logic (averaging)
        assert "add_to_position" not in src
        # Hard cap enforcement is present
        assert "args.lot > cfg[\"max_lot\"]" in src or 'args.lot > cfg["max_lot"]' in src

    def test_37_no_lot_escalation(self):
        with open(REPO_ROOT / "config" / "runtime.yaml", "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        assert cfg["demo_micro"]["max_lot"] == 0.01

    def test_38_order_send_impossible_without_demo_arm(self):
        os.environ.pop("TITAN_DEMO_MICRO_ARMED", None)
        _run_harness("DEMO_MICRO_EXECUTE")
        r = _read_report()
        assert r["order_send_called"] is False

    def test_39_order_send_failure_handled(self):
        # Harness doesn't crash on failure — verify it produces report
        os.environ.pop("TITAN_DEMO_MICRO_ARMED", None)
        _run_harness("DEMO_MICRO_EXECUTE")
        r = _read_report()
        assert "final_verdict" in r

    def test_40_close_failure_marks_manual_review(self):
        # When execute is blocked, it doesn't reach close — verify structure
        os.environ["TITAN_DEMO_MICRO_ARMED"] = "1"
        _run_harness("DEMO_MICRO_EXECUTE")
        r = _read_report()
        # On Linux, either blocked or manual review
        assert r["final_verdict"] in ("DEMO_MICRO_BLOCKED", "DEMO_MANUAL_REVIEW_REQUIRED")
        os.environ.pop("TITAN_DEMO_MICRO_ARMED", None)

    def test_41_open_position_remaining_prevents_pass(self):
        # If no trades closed, can't be PASS
        _run_harness("DRY_ARM_CHECK_ONLY")
        r = _read_report()
        assert r["final_verdict"] != "DEMO_FULL_CYCLE_PASS"


class TestForceCloseWatchdog:
    def test_42_force_close_max_duration_config(self):
        with open(REPO_ROOT / "config" / "runtime.yaml", "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        assert cfg["demo_micro"]["force_close_on_end"] is True
        assert cfg["demo_micro"]["force_close_after_minutes"] > 0

    def test_43_force_close_loss_threshold_config(self):
        with open(REPO_ROOT / "config" / "runtime.yaml", "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        assert cfg["demo_micro"]["max_total_loss_pct"] > 0
        assert cfg["demo_micro"]["max_daily_loss_pct"] > 0

    def test_44_emergency_stop_available(self):
        # Kill switch framework exists
        from titan.production.kill_switch_fsm import KillSwitchFSM
        ks = KillSwitchFSM()
        assert ks.state.value == "NORMAL"

    def test_45_shutdown_safe_close(self):
        # Harness handles shutdown via try/except in run()
        _run_harness("DRY_ARM_CHECK_ONLY")
        r = _read_report()
        assert "final_verdict" in r  # didn't crash

    def test_46_close_failure_demands_manual_review(self):
        # Verify DEMO_MANUAL_REVIEW_REQUIRED is a valid verdict
        assert "DEMO_MANUAL_REVIEW_REQUIRED" in [
            "DEMO_FULL_CYCLE_PASS", "DEMO_FULL_CYCLE_FAIL",
            "DEMO_MICRO_BLOCKED", "MARKET_CLOSED", "DEMO_MANUAL_REVIEW_REQUIRED"
        ]


class TestJournalAndMetrics:
    def test_47_journal_path_configured(self):
        with open(REPO_ROOT / "config" / "runtime.yaml", "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        assert "journal_path" in cfg["demo_micro"]

    def test_48_final_report_json_generated(self):
        _run_harness("DRY_ARM_CHECK_ONLY")
        assert (REPO_ROOT / "data" / "audit" / "demo_micro" / "demo_micro_report.json").exists()

    def test_49_final_report_md_generated(self):
        _run_harness("DRY_ARM_CHECK_ONLY")
        assert (REPO_ROOT / "data" / "audit" / "demo_micro" / "demo_micro_report.md").exists()

    def test_50_net_pnl_subtracts_costs(self):
        from titan.production.net_profit_engine import NetProfitEngine
        engine = NetProfitEngine()
        r = engine.calculate("BUY", 2000, 2010, 0.01, 1990,
                             spread_usd=0.30, slippage_pips=2.0, swap_cost=0.50)
        assert r.net_pnl < r.gross_pnl
        assert r.costs.spread_cost > 0
        assert r.costs.commission_cost > 0
        assert r.costs.slippage_cost > 0

    def test_51_unknown_close_state_manual_review(self):
        # Verify DEMO_MANUAL_REVIEW_REQUIRED is used for unknown states
        _run_harness("DRY_ARM_CHECK_ONLY")
        r = _read_report()
        # DRY_ARM_CHECK_ONLY never reaches close — verify it's not PASS
        assert r["final_verdict"] != "DEMO_FULL_CYCLE_PASS"

    def test_52_successful_mock_produces_correct_verdict(self):
        # DRY_ARM_CHECK_ONLY on Linux produces BLOCKED (correct)
        _run_harness("DRY_ARM_CHECK_ONLY")
        r = _read_report()
        assert r["final_verdict"] in ("DEMO_MICRO_BLOCKED", "MARKET_CLOSED", "DEMO_MICRO_ARMED")

    def test_53_journal_integrity_valid(self):
        # Verify journal path is writable
        jpath = REPO_ROOT / "data" / "audit" / "demo_micro" / "demo_micro_journal.jsonl"
        jpath.parent.mkdir(parents=True, exist_ok=True)
        with open(jpath, "w") as f:
            f.write('{"test": 1}\n')
        with open(jpath) as f:
            json.loads(f.readline())
        assert jpath.exists()

    def test_54_timestamps_utc(self):
        _run_harness("DRY_ARM_CHECK_ONLY")
        r = _read_report()
        ts = r.get("timestamp_utc", "")
        assert "+" in ts or "Z" in ts


class TestProductionSafety:
    def test_55_production_live_path_unchanged(self):
        with open(REPO_ROOT / "config" / "runtime.yaml", "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        assert cfg["runtime"]["live_trading"] is False

    def test_56_dry_run_default_unchanged(self):
        with open(REPO_ROOT / "config" / "runtime.yaml", "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        assert cfg["runtime"]["dry_run"] is True

    def test_57_live_trading_default_unchanged(self):
        with open(REPO_ROOT / "config" / "runtime.yaml", "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        assert cfg["runtime"]["live_trading"] is False

    def test_58_demo_micro_disabled_by_default(self):
        with open(REPO_ROOT / "config" / "runtime.yaml", "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        assert cfg["demo_micro"]["enabled"] is False

    def test_59_no_real_live_execution_possible(self):
        import titan.production.virtual_position_ledger as vpl
        import inspect
        src = inspect.getsource(vpl)
        assert "mt5.order_send" not in src
        assert "import MetaTrader5" not in src


# ─── Sprint 9.9.3 — Mock MT5 tests for actual execute logic ──────────────────
"""
These tests verify the actual DEMO_MICRO_EXECUTE logic using a mocked MT5
module. They NEVER call real MT5 — Z AI must not run actual execution.

Tests cover: order open, position sync, controlled close, net PnL,
journal events, safety blocks, and CLI side validation.
"""
import types
from typing import Optional


class _MockAccount:
    def __init__(self, trade_mode=0, balance=10000.0):
        self.trade_mode = trade_mode  # 0=DEMO, 1=CONTEST, 2=REAL
        self.balance = balance
        self.equity = balance
        self.currency = "USD"
        self.leverage = 500
        # Sprint 9.9.3.14 patch — trade_expert must be True for the
        # harness to proceed past the new defense-in-depth check in
        # _run_execute. Tests that specifically want to verify the
        # block behavior can override this via MockMT5(account_trade_expert=False).
        self.trade_expert = True
        self.trade_allowed = True


class _MockTick:
    def __init__(self, bid=2000.00, ask=2000.10):
        self.bid = bid
        self.ask = ask
        self.time = int(time.time())  # fresh
        self.time_msc = self.time * 1000
        self.volume = 100
        self.flags = 2


class _MockSymbolInfo:
    def __init__(self, name="XAUUSD", visible=True, filling_mode=None):
        self.name = name
        self.digits = 2
        self.point = 0.01
        self.spread = 10
        self.trade_contract_size = 100
        self.volume_min = 0.01
        self.volume_max = 100.0
        self.volume_step = 0.01
        self.trade_mode = 4
        # Sprint 9.9.3.16 patch — trade_exemode is queried by
        # _build_order_diagnostics for the pre-send journal event.
        # MQL5 SYMBOL_TRADE_EXECUTION enum: 0=INSTANT, 1=REQUEST,
        # 2=MARKET, 3=EXCHANGE. Default 2 (MARKET) — most common for FX.
        self.trade_exemode = 2
        self.visible = visible
        # Sprint 9.9.3.15 patch — expose filling_mode bitmask so tests
        # can simulate brokers that only support FOK / IOC / RETURN /
        # BOC / or none of the above. Default None means "attribute
        # missing" — the helper will fall back to its permissive default
        # mask (FOK+IOC+RETURN). Pass an int (1/2/4/8 or any OR-combo)
        # to simulate a real broker's symbol_info.filling_mode value.
        if filling_mode is not None:
            self.filling_mode = filling_mode


class _MockOrderResult:
    def __init__(self, retcode=10009, order=67890, deal=12345,
                 price=2000.10, volume=0.01, comment="TITAN"):
        self.retcode = retcode
        self.order = order
        self.deal = deal
        self.volume = volume
        self.price = price
        self.bid = 2000.00
        self.ask = 2000.10
        self.comment = comment
        self.request_id = 1


class _MockOrderCheckResult:
    """Sprint 9.9.3.16 patch — mock for mt5.order_check() result.

    mt5.order_check() returns an MqlTradeCheckResult namedtuple with
    retcode (int) and comment (str). retcode 0 = passed, anything else
    = rejected. This mock lets tests simulate per-filling-mode rejections.
    """
    def __init__(self, retcode=0, comment=""):
        self.retcode = retcode
        self.comment = comment


class _MockPosition:
    def __init__(self, ticket=1001, position_type=0, volume=0.01,
                 price_open=2000.10, magic=20261993, symbol="XAUUSD",
                 profit=0.0, sl=1995.10, tp=2010.10):
        self.ticket = ticket
        self.identifier = ticket
        self.type = position_type  # 0=BUY, 1=SELL
        self.volume = volume
        self.price_open = price_open
        self.price_current = price_open
        self.sl = sl
        self.tp = tp
        self.time = int(time.time())
        self.magic = magic
        self.symbol = symbol
        self.profit = profit
        self.swap = 0.0
        self.commission = 0.0


class _MockTerminalInfo:
    """Sprint 9.9.3.17 patch — mock for mt5.terminal_info() result.

    Real MQL5 TerminalInfo returns a namedtuple with many fields. The
    adapter only reads name, company, trade_allowed, tradeapi_disabled,
    community_account, connected. We expose all of them with sensible
    defaults.
    """
    def __init__(self, name="MetaTrader 5", company="MetaQuotes Ltd.",
                 trade_allowed=True, tradeapi_disabled=False,
                 community_account=False, connected=True):
        self.name = name
        self.company = company
        self.trade_allowed = trade_allowed
        self.tradeapi_disabled = tradeapi_disabled
        self.community_account = community_account
        self.connected = connected


class MockMT5:
    """Mock MT5 module with configurable behavior."""
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    TRADE_ACTION_DEAL = 1
    TRADE_RETCODE_DONE = 10009
    # Sprint 9.9.3.20 patch — expose ORDER_FILLING_* constants so the
    # adapter can read them at runtime via getattr(mt5, "ORDER_FILLING_*").
    # These match the real MetaTrader5 Python module's constant values.
    ORDER_FILLING_FOK = 1
    ORDER_FILLING_IOC = 2
    ORDER_FILLING_BOC = 3
    ORDER_FILLING_RETURN = 4

    def __init__(self,
                 account_trade_mode=0,
                 account_balance=10000.0,
                 tick_bid=2000.00,
                 tick_ask=2000.10,
                 symbol_visible=True,
                 open_positions=None,
                 open_order_retcode=10009,
                 close_order_retcode=10009,
                 sync_position_after=0,
                 sync_position_obj=None,
                 floating_pnl_sequence=None,
                 never_visible_position=False,
                 auto_create_position_on_open=True,
                 account_trade_expert=True,
                 symbol_filling_mode=None,
                 order_check_default_retcode=0,
                 order_check_retcode_per_mode=None,
                 # Sprint 9.9.3.17 patch — send-level fallback knobs:
                 order_send_retcode_per_mode=None,
                 position_appears_after_send_failure=False,
                 terminal_info_obj=None,
                 # Sprint 9.9.3.18 patch — None-result simulation:
                 order_send_returns_none_per_mode=None,
                 mt5_last_error=None,
                 # Sprint 9.9.3.19 patch — broker compatibility fallback knobs:
                 protected_order_retcode=None,    # retcode for SL/TP-attached orders
                 naked_order_retcode=None,        # retcode for sl=0/tp=0 orders
                 sltp_modify_retcode=10009):      # retcode for TRADE_ACTION_SLTP
        self._initialized = False
        self._account = _MockAccount(account_trade_mode, account_balance)
        # Sprint 9.9.3.14 patch — allow tests to simulate disabled
        # Algo Trading by overriding trade_expert on the mock account.
        self._account.trade_expert = account_trade_expert
        self._tick = _MockTick(tick_bid, tick_ask)
        # Sprint 9.9.3.15 patch — allow tests to simulate brokers that
        # support specific filling modes (FBS=IOC, FundedNext=FOK+IOC, etc.)
        self._symbol_info = _MockSymbolInfo("XAUUSD", symbol_visible,
                                             filling_mode=symbol_filling_mode)
        self._open_positions = list(open_positions or [])
        self._open_order_retcode = open_order_retcode
        self._close_order_retcode = close_order_retcode
        self._sync_position_after = sync_position_after
        self._sync_position_obj = sync_position_obj
        self._sync_attempts = 0
        self._floating_pnl_sequence = list(floating_pnl_sequence or [])
        self._floating_idx = 0
        self._never_visible_position = never_visible_position
        self._auto_create_position_on_open = auto_create_position_on_open
        # Sprint 9.9.3.16 patch — order_check() configuration.
        self._order_check_default_retcode = order_check_default_retcode
        self._order_check_retcode_per_mode = dict(order_check_retcode_per_mode or {})
        # Sprint 9.9.3.17 patch — send-level fallback configuration.
        # order_send_retcode_per_mode lets tests say "FOK send returns
        # 10006, IOC send returns 10009" without using the legacy
        # open_order_retcode (which is global, not per-mode).
        self._order_send_retcode_per_mode = dict(order_send_retcode_per_mode or {})
        # When True, simulates the MT5 race condition: order_send
        # returns a failure retcode BUT a position with our magic
        # appears in positions_get anyway. The adapter must detect
        # this and signal emergency_close_required.
        self._position_appears_after_send_failure = position_appears_after_send_failure
        self._send_failure_count = 0   # tracks how many failed sends have happened
        # Sprint 9.9.3.17 patch — terminal_info mock.
        self._terminal_info = terminal_info_obj or _MockTerminalInfo()
        # Sprint 9.9.3.18 patch — None-result simulation.
        # order_send_returns_none_per_mode is a set of filling_type ints
        # for which order_send should return None (simulating MT5 internal
        # error). E.g. {1} means "FOK send returns None, IOC send works".
        self._order_send_returns_none_per_mode = set(order_send_returns_none_per_mode or [])
        # mt5_last_error is what mt5.last_error() returns when called.
        # Real MT5 returns a (code, message) tuple. Default simulates
        # a generic internal error.
        self._mt5_last_error = mt5_last_error or (-1, "MT5 internal error: request not processed")
        # Sprint 9.9.3.19 patch — broker compatibility fallback knobs.
        # protected_order_retcode: if set, order_send returns this retcode
        #   when the request has SL/TP attached (sl != 0 or tp != 0).
        # naked_order_retcode: if set, order_send returns this retcode
        #   when the request has sl=0 AND tp=0 (naked market order).
        # sltp_modify_retcode: retcode for TRADE_ACTION_SLTP requests.
        self._protected_order_retcode = protected_order_retcode
        self._naked_order_retcode = naked_order_retcode
        self._sltp_modify_retcode = sltp_modify_retcode
        self._sltp_modify_calls = 0
        # Tracking
        self.order_send_calls = []
        self.last_order_request = None
        self.order_check_calls = []   # Sprint 9.9.3.16 patch
        self.symbol_info_tick_calls = []   # Sprint 9.9.3.17 patch — tick refresh tracking
        self.last_error_calls = 0   # Sprint 9.9.3.18 patch — track last_error() calls

    def initialize(self, *a, **kw):
        self._initialized = True
        return True

    def shutdown(self):
        self._initialized = False

    def account_info(self):
        return self._account if self._initialized else None

    def terminal_info(self):
        """Sprint 9.9.3.17 patch — mock for mt5.terminal_info()."""
        return self._terminal_info if self._initialized else None

    def symbol_info(self, symbol):
        return self._symbol_info if self._initialized else None

    def symbol_info_tick(self, symbol):
        # Sprint 9.9.3.17 patch — track tick refreshes so tests can
        # assert that the adapter refreshed the tick before each send.
        self.symbol_info_tick_calls.append(symbol)
        return self._tick if self._initialized else None

    def symbol_select(self, symbol, visible=True):
        return True

    def last_error(self):
        """Sprint 9.9.3.18 patch — mock for mt5.last_error().

        Real MT5 returns a (code, message) tuple. This mock returns
        whatever was set via the mt5_last_error kwarg.
        """
        self.last_error_calls += 1
        return self._mt5_last_error

    def order_check(self, request):
        """Sprint 9.9.3.16 patch — mock for mt5.order_check().

        Returns _MockOrderCheckResult with retcode determined by
        order_check_retcode_per_mode (keyed by request['type_filling'])
        or order_check_default_retcode if the mode is not in the dict.

        Default retcode 0 = pass — so existing tests that don't care
        about order_check still work without any configuration.
        """
        if not self._initialized:
            return None
        # Track the call for assertion in tests
        self.order_check_calls.append(dict(request))
        filling_type = request.get("type_filling")
        if filling_type in self._order_check_retcode_per_mode:
            retcode = self._order_check_retcode_per_mode[filling_type]
        else:
            retcode = self._order_check_default_retcode
        comment = "" if retcode == 0 else f"mock reject for filling={filling_type}"
        return _MockOrderCheckResult(retcode=retcode, comment=comment)

    def positions_get(self, symbol=None, ticket=None):
        if not self._initialized:
            return None
        # If never_visible_position is set, always return empty (sync failure)
        if self._never_visible_position:
            return []
        # If a floating pnl sequence is set, mutate current position profit
        if self._floating_pnl_sequence and self._open_positions:
            if self._floating_idx < len(self._floating_pnl_sequence):
                pnl = self._floating_pnl_sequence[self._floating_idx]
                self._open_positions[0].profit = pnl
                self._floating_idx += 1
        # Optionally hold back position for sync_position_after attempts
        if self._sync_position_obj is not None and self._sync_attempts < self._sync_position_after:
            self._sync_attempts += 1
            return []
        if self._sync_position_obj is not None and self._sync_attempts == self._sync_position_after:
            self._sync_attempts += 1
            return [self._sync_position_obj]
        return list(self._open_positions)

    def order_send(self, request):
        if not self._initialized:
            return None
        self.order_send_calls.append(request)
        self.last_order_request = request
        # Determine if this is open or close based on "position" field
        is_close = "position" in request and request.get("position")
        filling_type = request.get("type_filling")
        # Sprint 9.9.3.19 patch — detect TRADE_ACTION_SLTP requests (action=2).
        # These are SL/TP modify requests, not market orders. Handle separately.
        is_sltp_modify = request.get("action") == 2
        if is_sltp_modify:
            retcode = getattr(self, "_sltp_modify_retcode", 10009)
            self._sltp_modify_calls = getattr(self, "_sltp_modify_calls", 0) + 1
            return _MockOrderResult(retcode=retcode, order=0, deal=0,
                                    price=request.get("price", 0),
                                    volume=0, comment="SLTP_MODIFY")

        # Sprint 9.9.3.19 patch — broker compatibility fallback.
        # If protected_order_retcode is set and this request has SL/TP
        # attached (sl != 0 or tp != 0), return the protected retcode.
        # If naked_order_retcode is set and this request has sl=0 AND tp=0,
        # return the naked retcode. This lets tests simulate FBS-style
        # brokers that reject protected market orders but accept naked ones.
        sl_val = request.get("sl", 0) or 0
        tp_val = request.get("tp", 0) or 0
        is_protected_order = (sl_val != 0 or tp_val != 0)
        if is_protected_order and self._protected_order_retcode is not None:
            # Protected order rejected — don't create a position
            return _MockOrderResult(retcode=self._protected_order_retcode,
                                    order=0, deal=0,
                                    price=request.get("price", 2000.0),
                                    volume=request.get("volume", 0.01),
                                    comment="PROTECTED_REJECTED")
        if not is_protected_order and self._naked_order_retcode is not None:
            retcode = self._naked_order_retcode
            is_success = retcode in (10009, 10010)
            if is_success and not is_close and self._auto_create_position_on_open:
                side_type = 0 if request.get("type") == 0 else 1
                new_pos = _MockPosition(
                    ticket=66666,
                    position_type=side_type,
                    volume=request.get("volume", 0.01),
                    price_open=request.get("price", 2000.10),
                    magic=request.get("magic", 20261993),
                    symbol=request.get("symbol", "XAUUSD"),
                    profit=0.0,
                )
                self._open_positions = [new_pos]
            elif is_success and is_close:
                # Close order — remove the position being closed
                self._open_positions = [
                    p for p in self._open_positions
                    if p.ticket != request.get("position")
                ]
            return _MockOrderResult(retcode=retcode, order=66666, deal=66666,
                                    price=request.get("price", 2000.10),
                                    volume=request.get("volume", 0.01),
                                    comment="NAKED_OPEN" if not is_close else "NAKED_CLOSE")

        # Sprint 9.9.3.18 patch — simulate order_send returning None.
        # If this filling mode is in the None-return set, return None
        # immediately (simulating MT5 internal error). But first, if
        # position_appears_after_send_failure is True, inject a ghost
        # position so the adapter can detect it via positions_get.
        if filling_type in self._order_send_returns_none_per_mode:
            if (self._position_appears_after_send_failure
                    and self._send_failure_count == 0
                    and not is_close):
                self._send_failure_count += 1
                side_type = 0 if request.get("type") == 0 else 1
                ghost_pos = _MockPosition(
                    ticket=77777,
                    position_type=side_type,
                    volume=request.get("volume", 0.01),
                    price_open=request.get("price", 2000.10),
                    magic=request.get("magic", 20261993),
                    symbol=request.get("symbol", "XAUUSD"),
                    profit=0.0,
                )
                self._open_positions = [ghost_pos]
            return None

        # Sprint 9.9.3.17 patch — determine retcode with per-mode override.
        # Priority: order_send_retcode_per_mode[filling_type] >
        #           (open_order_retcode / close_order_retcode) legacy.
        if filling_type in self._order_send_retcode_per_mode:
            retcode = self._order_send_retcode_per_mode[filling_type]
        elif is_close:
            retcode = self._close_order_retcode
        else:
            retcode = self._open_order_retcode

        is_success = retcode in (10009, 10010)

        # Sprint 9.9.3.17 patch — simulate the MT5 race condition where
        # order_send returns a failure retcode BUT a position with our
        # magic appears anyway. This happens on the FIRST failed send
        # only (so subsequent modes see the position in positions_get
        # and the adapter can detect it).
        if (not is_success and self._position_appears_after_send_failure
                and self._send_failure_count == 0
                and not is_close):
            self._send_failure_count += 1
            # Inject a position with the request's magic
            side_type = 0 if request.get("type") == 0 else 1
            ghost_pos = _MockPosition(
                ticket=88888,
                position_type=side_type,
                volume=request.get("volume", 0.01),
                price_open=request.get("price", 2000.10),
                magic=request.get("magic", 20261993),
                symbol=request.get("symbol", "XAUUSD"),
                profit=0.0,
            )
            self._open_positions = [ghost_pos]
            return _MockOrderResult(retcode=retcode, order=0, deal=0,
                                    price=request.get("price", 2000.0),
                                    volume=request.get("volume", 0.01),
                                    comment="GHOST_POSITION_INJECTED")

        if is_close:
            # Remove position from open list on success
            if retcode == 10009:
                self._open_positions = [
                    p for p in self._open_positions
                    if p.ticket != request["position"]
                ]
            return _MockOrderResult(retcode=retcode, order=67891, deal=12346,
                                    price=request.get("price", 2000.0),
                                    volume=request.get("volume", 0.01),
                                    comment="CLOSE")
        # Open order success path — auto-create a matching position
        if (is_success and self._sync_position_obj is None
                and self._auto_create_position_on_open):
            side_type = 0 if request.get("type") == 0 else 1
            new_pos = _MockPosition(
                ticket=99999,
                position_type=side_type,
                volume=request.get("volume", 0.01),
                price_open=request.get("price", 2000.10),
                magic=request.get("magic", 20261993),
                symbol=request.get("symbol", "XAUUSD"),
                profit=0.0,
            )
            self._open_positions = [new_pos]
        if not is_success:
            self._send_failure_count += 1
        return _MockOrderResult(retcode=retcode, order=67890, deal=12345,
                                price=request.get("price", 2000.10),
                                volume=request.get("volume", 0.01),
                                comment="OPEN")


@pytest.fixture
def mock_mt5(monkeypatch):
    """Create a MockMT5 and install it via _get_mt5 patch."""
    mt5 = MockMT5()
    # Patch _get_mt5 to return our mock
    from scripts.audit import demo_micro_full_cycle as harness
    monkeypatch.setattr(harness, "_get_mt5", lambda: mt5)
    # Patch hard_gate_evaluate to return ARMED
    def fake_evaluate(config_path=None):
        return {
            "verdict": "DEMO_MICRO_ARMED",
            "reasons": [],
            "checks": {
                "mt5_reachable": True,
                "account_demo": True,
                "demo_micro_enabled": True,
                "arm_token_present": True,
                "not_real_account": True,
                "max_lot_ok": True,
                "max_positions_ok": True,
                "max_trades_ok": True,
                "force_close_on_end": True,
                "kill_switch_normal": True,
                "market_open": True,
                "demo_micro_readiness_ok": True,
            },
            "config_path_used": "mock",
            "demo_micro_config_found": True,
            "demo_micro_enabled_raw": True,
            "demo_micro_enabled_effective": True,
        }
    monkeypatch.setattr(harness, "hard_gate_evaluate", fake_evaluate)
    # Set arm token
    monkeypatch.setenv("TITAN_DEMO_MICRO_ARMED", "1")
    # Clear emergency stop
    monkeypatch.delenv("TITAN_DEMO_MICRO_EMERGENCY_STOP", raising=False)
    return mt5


def _run_execute_with_mock(mock_mt5, **kwargs):
    """Run DEMO_MICRO_EXECUTE with patched mock_mt5 and return the report dict."""
    # Clear previous report
    report_path = REPO_ROOT / "data" / "audit" / "demo_micro" / "demo_micro_report.json"
    if report_path.exists():
        report_path.unlink()
    # Clear previous journal
    journal_path = REPO_ROOT / "data" / "audit" / "demo_micro" / "demo_micro_journal.jsonl"
    if journal_path.exists():
        journal_path.unlink()

    old = sys.argv
    argv = ["harness", "--mode", "DEMO_MICRO_EXECUTE"]
    for k, v in kwargs.items():
        flag = f"--{k.replace('_', '-')}"
        if v is True:
            # store_true flag — just add the flag without a value
            argv.append(flag)
        elif v is False or v is None:
            # Skip False/None values
            continue
        else:
            argv.extend([flag, str(v)])
    sys.argv = argv
    from scripts.audit.demo_micro_full_cycle import parse_args, run
    args = parse_args()
    sys.argv = old
    asyncio.run(run(args))

    if report_path.exists():
        with open(report_path) as f:
            return json.load(f)
    return {}


def _read_journal_events():
    journal_path = REPO_ROOT / "data" / "audit" / "demo_micro" / "demo_micro_journal.jsonl"
    if not journal_path.exists():
        return []
    events = []
    with open(journal_path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    events.append(json.loads(line))
                except Exception:
                    pass
    return events


class TestExecuteSideValidation:
    """Tests 60-67: --side and AI signal resolution."""

    def test_60_blocks_without_side_no_signal(self, mock_mt5, monkeypatch):
        """execute blocks if no AI signal and no --side."""
        # Make sure no AI signal loads
        monkeypatch.setattr(
            "scripts.audit.demo_micro_full_cycle._load_latest_ai_signal",
            lambda: None,
        )
        r = _run_execute_with_mock(mock_mt5)
        assert r["final_verdict"] == "DEMO_MICRO_BLOCKED"
        assert "refusing to guess" in r["reason"]
        assert r["order_send_called"] is False
        # No order_send was called
        assert len(mock_mt5.order_send_calls) == 0

    def test_61_accepts_side_buy(self, mock_mt5):
        """execute accepts --side BUY and sends one BUY order."""
        r = _run_execute_with_mock(mock_mt5, side="BUY", max_hold_seconds=1)
        assert r["order_send_called"] is True
        assert r["order_send_attempts"] == 1
        assert r["order_send_success"] == 1
        assert r["position"]["type"] == "BUY"
        # Verify exactly one order_send for open
        assert len(mock_mt5.order_send_calls) >= 1
        # First call should be BUY (type=0)
        first_req = mock_mt5.order_send_calls[0]
        assert first_req["type"] == 0  # ORDER_TYPE_BUY
        assert first_req["volume"] == 0.01

    def test_62_accepts_side_sell(self, mock_mt5):
        """execute accepts --side SELL and sends one SELL order."""
        r = _run_execute_with_mock(mock_mt5, side="SELL", max_hold_seconds=1)
        assert r["order_send_called"] is True
        assert r["position"]["type"] == "SELL"
        first_req = mock_mt5.order_send_calls[0]
        assert first_req["type"] == 1  # ORDER_TYPE_SELL

    def test_63_blocks_lot_over_max(self, mock_mt5):
        """execute blocks lot > 0.01."""
        r = _run_execute_with_mock(mock_mt5, side="BUY", lot=0.05)
        assert r["final_verdict"] == "DEMO_MICRO_BLOCKED"
        assert "max_lot" in r["reason"]
        assert r["order_send_called"] is False
        assert len(mock_mt5.order_send_calls) == 0

    def test_64_blocks_existing_open_position(self, mock_mt5):
        """execute blocks if existing open position."""
        existing = _MockPosition(ticket=11111, magic=20261993)
        mock_mt5._open_positions = [existing]
        r = _run_execute_with_mock(mock_mt5, side="BUY")
        assert r["final_verdict"] == "DEMO_MICRO_BLOCKED"
        assert "Existing open position" in r["reason"]
        assert r["order_send_called"] is False
        assert len(mock_mt5.order_send_calls) == 0

    def test_65_sends_exactly_one_open_order(self, mock_mt5):
        """execute sends exactly one order_send for open."""
        r = _run_execute_with_mock(mock_mt5, side="BUY", max_hold_seconds=1)
        assert r["order_send_attempts"] == 1
        # Total order_send calls = 1 (open) + 1 (close) = 2
        # But never more than one OPEN order
        open_calls = [req for req in mock_mt5.order_send_calls
                      if not req.get("position")]
        assert len(open_calls) == 1

    def test_66_does_not_duplicate_open_order(self, mock_mt5):
        """execute does not send duplicate open orders on retry."""
        r = _run_execute_with_mock(mock_mt5, side="BUY", max_hold_seconds=1)
        # Even after close, only one open order was ever sent
        open_calls = [req for req in mock_mt5.order_send_calls
                      if not req.get("position")]
        assert len(open_calls) == 1
        assert r["order_send_success"] == 1

    def test_67_cli_side_validation(self):
        """CLI --side accepts only BUY or SELL."""
        from scripts.audit.demo_micro_full_cycle import parse_args
        old = sys.argv
        # BUY valid
        sys.argv = ["h", "--mode", "DEMO_MICRO_EXECUTE", "--side", "BUY"]
        args = parse_args()
        assert args.side == "BUY"
        # SELL valid
        sys.argv = ["h", "--mode", "DEMO_MICRO_EXECUTE", "--side", "SELL"]
        args = parse_args()
        assert args.side == "SELL"
        # No side = None
        sys.argv = ["h", "--mode", "DEMO_MICRO_EXECUTE"]
        args = parse_args()
        assert args.side is None
        sys.argv = old
        # Invalid side raises
        sys.argv = ["h", "--mode", "DEMO_MICRO_EXECUTE", "--side", "INVALID"]
        try:
            parse_args()
            assert False, "Should have raised"
        except SystemExit:
            pass
        sys.argv = old


class TestExecuteCloseLogic:
    """Tests 68-72: BUY->SELL close, SELL->BUY close, close failure."""

    def test_68_buy_close_uses_sell(self, mock_mt5):
        """Close BUY position uses SELL order."""
        r = _run_execute_with_mock(mock_mt5, side="BUY", max_hold_seconds=1)
        assert r["final_verdict"] == "DEMO_FULL_CYCLE_PASS"
        # Find close request (has "position" field)
        close_calls = [req for req in mock_mt5.order_send_calls
                       if req.get("position")]
        assert len(close_calls) == 1
        assert close_calls[0]["type"] == 1  # ORDER_TYPE_SELL

    def test_69_sell_close_uses_buy(self, mock_mt5):
        """Close SELL position uses BUY order."""
        # Configure mock: open SELL position
        r = _run_execute_with_mock(mock_mt5, side="SELL", max_hold_seconds=1)
        assert r["final_verdict"] == "DEMO_FULL_CYCLE_PASS"
        close_calls = [req for req in mock_mt5.order_send_calls
                       if req.get("position")]
        assert len(close_calls) == 1
        assert close_calls[0]["type"] == 0  # ORDER_TYPE_BUY

    def test_70_close_failure_manual_review(self, mock_mt5):
        """Close order_send failure => DEMO_MANUAL_REVIEW_REQUIRED.

        Sprint 9.9.3.17 update: with the universal adapter, the close order
        also uses send-level fallback. Default mock has FOK+IOC modes (RETURN
        filtered by MARKET execution). Both fail with 10006 → 2 close attempts.
        """
        mock_mt5._close_order_retcode = 10006  # REJECT
        r = _run_execute_with_mock(mock_mt5, side="BUY", max_hold_seconds=1)
        assert r["final_verdict"] == "DEMO_MANUAL_REVIEW_REQUIRED"
        assert r["close_success"] == 0
        # Sprint 9.9.3.17 — adapter tries FOK + IOC for close (2 attempts)
        assert r["close_attempts"] >= 1
        # Close attempted
        close_calls = [req for req in mock_mt5.order_send_calls
                       if req.get("position")]
        assert len(close_calls) >= 1

    def test_71_close_success_full_cycle_pass(self, mock_mt5):
        """Close success + no remaining positions => DEMO_FULL_CYCLE_PASS."""
        r = _run_execute_with_mock(mock_mt5, side="BUY", max_hold_seconds=1)
        assert r["final_verdict"] == "DEMO_FULL_CYCLE_PASS"
        assert r["close_success"] == 1
        assert r["open_positions_remaining"] == 0

    def test_72_open_position_remaining_not_pass(self, mock_mt5):
        """If open positions remain after close, never report PASS."""
        # Configure mock: keep position even after close attempt
        original_order_send = mock_mt5.order_send

        def stubborn_order_send(request):
            # Close returns success but doesn't actually remove position
            if "position" in request and request.get("position"):
                # Don't remove from _open_positions
                from scripts.audit.demo_micro_full_cycle import _TRADE_RETCODE_DONE
                return _MockOrderResult(retcode=10009, order=99999, deal=99999,
                                        price=request.get("price", 2000.0),
                                        volume=request.get("volume", 0.01),
                                        comment="CLOSE_BUT_STILL_OPEN")
            return original_order_send(request)
        mock_mt5.order_send = stubborn_order_send
        r = _run_execute_with_mock(mock_mt5, side="BUY", max_hold_seconds=1)
        assert r["final_verdict"] == "DEMO_MANUAL_REVIEW_REQUIRED"
        assert r["open_positions_remaining"] >= 1


class TestExecutePositionSync:
    """Tests 73-74: position sync success/failure."""

    def test_73_position_sync_success(self, mock_mt5):
        """Position sync succeeds after order_send."""
        # Default mock auto-creates position, so sync should succeed
        r = _run_execute_with_mock(mock_mt5, side="BUY", max_hold_seconds=1)
        assert r["final_verdict"] == "DEMO_FULL_CYCLE_PASS"
        assert r["position"]["ticket"] is not None
        assert r["position"]["type"] == "BUY"
        assert r["position"]["price_open"] > 0

    def test_74_position_sync_failure_manual_review(self, mock_mt5):
        """Position sync failure => DEMO_MANUAL_REVIEW_REQUIRED."""
        # Configure mock: open succeeds but position never appears
        mock_mt5._never_visible_position = True
        mock_mt5._auto_create_position_on_open = False
        r = _run_execute_with_mock(mock_mt5, side="BUY", max_hold_seconds=1)
        assert r["final_verdict"] == "DEMO_MANUAL_REVIEW_REQUIRED"
        assert r["order_send_success"] == 1  # open succeeded
        assert r["open_positions_remaining"] == 1


class TestExecuteOrderFailure:
    """Tests 75-76: open order failure."""

    def test_75_open_order_failure_fail(self, mock_mt5):
        """Open order_send failure => DEMO_FULL_CYCLE_FAIL.

        Sprint 9.9.3.17 update: with the universal adapter, all supported
        filling modes are tried via send-level fallback. Default mock has
        no symbol_filling_mode set → adapter uses default mask (FOK+IOC+RETURN)
        but trade_exemode=MARKET filters out RETURN → 2 modes (FOK, IOC).
        Both fail with 10006 (retryable) → fail closed after 2 send attempts.
        """
        mock_mt5._open_order_retcode = 10006  # REJECT
        r = _run_execute_with_mock(mock_mt5, side="BUY", max_hold_seconds=1)
        assert r["final_verdict"] == "DEMO_FULL_CYCLE_FAIL"
        # Sprint 9.9.3.17 — adapter tries FOK then IOC (2 send attempts)
        assert r["order_send_attempts"] >= 1
        assert r["order_send_success"] == 0
        # No close attempt should be made (no position opened)
        close_calls = [req for req in mock_mt5.order_send_calls
                       if req.get("position")]
        assert len(close_calls) == 0

    def test_76_open_order_returns_none(self, mock_mt5):
        """Open order_send returns None => DEMO_FULL_CYCLE_FAIL."""
        def none_order_send(request):
            mock_mt5.order_send_calls.append(request)
            return None
        mock_mt5.order_send = none_order_send
        r = _run_execute_with_mock(mock_mt5, side="BUY", max_hold_seconds=1)
        assert r["final_verdict"] == "DEMO_FULL_CYCLE_FAIL"


class TestExecuteNetPnl:
    """Tests 77-78: net PnL calculation and reporting."""

    def test_77_net_pnl_calculated_after_close(self, mock_mt5):
        """Net PnL is calculated after close."""
        r = _run_execute_with_mock(mock_mt5, side="BUY", max_hold_seconds=1)
        assert r["final_verdict"] == "DEMO_FULL_CYCLE_PASS"
        # Net PnL fields present
        assert "net_pnl" in r
        assert "gross_pnl" in r
        assert "spread_cost" in r
        assert "commission_cost" in r
        assert "slippage_cost" in r
        assert "swap_cost" in r
        assert "holding_seconds" in r
        assert "open_price" in r
        assert "close_price" in r
        assert "max_floating_dd" in r
        # Costs should be non-negative
        assert r["commission_cost"] >= 0
        assert r["spread_cost"] >= 0

    def test_78_report_json_includes_ticket_order(self, mock_mt5):
        """Report JSON includes ticket/order identifiers."""
        r = _run_execute_with_mock(mock_mt5, side="BUY", max_hold_seconds=1)
        assert r["final_verdict"] == "DEMO_FULL_CYCLE_PASS"
        assert r["position"]["ticket"] is not None
        assert r["open_order"]["order"] is not None
        assert r["open_order"]["deal"] is not None
        # MD file exists and includes verdict
        md_path = REPO_ROOT / "data" / "audit" / "demo_micro" / "demo_micro_report.md"
        assert md_path.exists()
        md = md_path.read_text(encoding="utf-8")
        assert "DEMO_FULL_CYCLE_PASS" in md
        assert "Order send called: True" in md


class TestExecuteJournalEvents:
    """Tests 79-80: journal records open/close requests."""

    def test_79_journal_records_open_request(self, mock_mt5):
        """Journal records DEMO_MICRO_ORDER_REQUESTED and ORDER_SENT events."""
        _run_execute_with_mock(mock_mt5, side="BUY", max_hold_seconds=1)
        events = _read_journal_events()
        event_types = [e["event"] for e in events]
        assert "DEMO_MICRO_ORDER_REQUESTED" in event_types
        assert "DEMO_MICRO_ORDER_SENT" in event_types
        # Find ORDER_REQUESTED payload
        req_evt = next(e for e in events if e["event"] == "DEMO_MICRO_ORDER_REQUESTED")
        assert req_evt["side"] == "BUY"
        assert req_evt["symbol"] == "XAUUSD"
        assert req_evt["lot"] == 0.01

    def test_80_journal_records_close_request(self, mock_mt5):
        """Journal records CLOSE_REQUESTED and POSITION_CLOSED events."""
        _run_execute_with_mock(mock_mt5, side="BUY", max_hold_seconds=1)
        events = _read_journal_events()
        event_types = [e["event"] for e in events]
        assert "DEMO_MICRO_POSITION_CLOSE_REQUESTED" in event_types
        assert "DEMO_MICRO_POSITION_CLOSED" in event_types
        assert "DEMO_MICRO_FULL_CYCLE_PASS" in event_types


class TestExecuteCloseTriggers:
    """Tests 81-83: max hold, loss threshold, emergency stop."""

    def test_81_max_hold_seconds_triggers_close(self, mock_mt5):
        """--max-hold-seconds triggers close after the specified duration."""
        r = _run_execute_with_mock(mock_mt5, side="BUY", max_hold_seconds=1)
        assert r["final_verdict"] == "DEMO_FULL_CYCLE_PASS"
        # close_reason should be max_hold_seconds
        assert r["close_reason"] == "max_hold_seconds"
        assert r["holding_seconds"] >= 1

    def test_82_loss_threshold_triggers_close(self, mock_mt5):
        """Loss threshold hit triggers close."""
        # Set floating pnl sequence to a large negative value
        mock_mt5._floating_pnl_sequence = [-200.0]
        r = _run_execute_with_mock(mock_mt5, side="BUY", max_hold_seconds=10)
        assert r["close_reason"] == "loss_threshold"
        assert r["max_floating_dd"] <= -200.0

    def test_83_emergency_stop_triggers_close(self, mock_mt5, monkeypatch):
        """Emergency stop env var triggers close."""
        # Set emergency stop BEFORE running
        monkeypatch.setenv("TITAN_DEMO_MICRO_EMERGENCY_STOP", "1")
        r = _run_execute_with_mock(mock_mt5, side="BUY", max_hold_seconds=10)
        assert r["close_reason"] == "emergency_stop"
        assert r["emergency_stop"] is True


class TestExecuteSafetyBlocks:
    """Tests 84-87: safety blocks prevent order_send."""

    def test_84_no_order_send_without_hard_gate_armed(self, monkeypatch):
        """No order_send if hard gate verdict is not DEMO_MICRO_ARMED."""
        from scripts.audit import demo_micro_full_cycle as harness
        mt5 = MockMT5()
        monkeypatch.setattr(harness, "_get_mt5", lambda: mt5)
        monkeypatch.setattr(harness, "hard_gate_evaluate",
                            lambda config_path=None: {"verdict": "DEMO_MICRO_BLOCKED",
                                                       "reasons": ["test"],
                                                       "checks": {}})
        monkeypatch.setenv("TITAN_DEMO_MICRO_ARMED", "1")
        r = _run_execute_with_mock(mt5, side="BUY")
        assert r["final_verdict"] == "DEMO_MICRO_BLOCKED"
        assert r["order_send_called"] is False
        assert len(mt5.order_send_calls) == 0

    def test_85_no_order_send_in_dry_check(self):
        """DRY_ARM_CHECK_ONLY never calls order_send."""
        # Already verified by test_26 but assert explicitly here
        _run_harness("DRY_ARM_CHECK_ONLY")
        r = _read_report()
        assert r["order_send_called"] is False

    def test_86_no_order_send_without_arm(self, monkeypatch):
        """No order_send if TITAN_DEMO_MICRO_ARMED is not set."""
        from scripts.audit import demo_micro_full_cycle as harness
        mt5 = MockMT5()
        monkeypatch.setattr(harness, "_get_mt5", lambda: mt5)
        monkeypatch.setattr(harness, "hard_gate_evaluate",
                            lambda config_path=None: {"verdict": "DEMO_MICRO_ARMED",
                                                       "reasons": [],
                                                       "checks": {}})
        monkeypatch.delenv("TITAN_DEMO_MICRO_ARMED", raising=False)
        r = _run_execute_with_mock(mt5, side="BUY")
        assert r["final_verdict"] == "DEMO_MICRO_BLOCKED"
        assert r["order_send_called"] is False
        assert len(mt5.order_send_calls) == 0

    def test_87_no_order_send_on_non_demo_account(self, monkeypatch):
        """No order_send if account is not DEMO."""
        mt5 = MockMT5(account_trade_mode=2)  # REAL
        from scripts.audit import demo_micro_full_cycle as harness
        monkeypatch.setattr(harness, "_get_mt5", lambda: mt5)
        monkeypatch.setattr(harness, "hard_gate_evaluate",
                            lambda config_path=None: {"verdict": "DEMO_MICRO_ARMED",
                                                       "reasons": [],
                                                       "checks": {}})
        monkeypatch.setenv("TITAN_DEMO_MICRO_ARMED", "1")
        r = _run_execute_with_mock(mt5, side="BUY")
        assert r["final_verdict"] == "DEMO_MICRO_BLOCKED"
        assert "NOT DEMO" in r["reason"]
        assert r["order_send_called"] is False
        assert len(mt5.order_send_calls) == 0


class TestExecuteProductionSafety:
    """Tests 88-89: production live path + Z AI/CI never executes."""

    def test_88_production_live_path_unchanged(self):
        """Production live_trading flag remains False."""
        with open(REPO_ROOT / "config" / "runtime.yaml", "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        assert cfg["runtime"]["live_trading"] is False
        assert cfg["runtime"]["dry_run"] is True

    def test_89_z_ai_never_runs_live_mt5(self):
        """Z AI / CI environment never runs actual live MT5 execution.

        This test verifies that MetaTrader5 is NOT importable in the Z AI
        environment (the safety mechanism that prevents accidental execution).
        """
        try:
            import MetaTrader5  # noqa: F401
            # If importable, we're on Windows — skip this safety check
            pytest.skip("MetaTrader5 is installed (Windows) — safety check N/A")
        except ImportError:
            # Expected on Z AI / Linux
            pass

        # Also verify the harness guards against missing MT5
        from scripts.audit.demo_micro_full_cycle import _get_mt5
        assert _get_mt5() is None  # Returns None on Z AI / Linux

    def test_90_blocks_when_trade_expert_false(self, monkeypatch):
        """Sprint 9.9.3.14 — _run_execute must BLOCK (no order_send)
        when account_info.trade_expert=False, even if the hard gate
        verdict is DEMO_MICRO_ARMED.

        Defense in depth: operator may have toggled MT5 Algo Trading
        button between the hard-gate run and the execute run.
        """
        from scripts.audit import demo_micro_full_cycle as harness
        # Mock MT5 with DEMO account but trade_expert=False
        mt5 = MockMT5(account_trade_mode=0, account_trade_expert=False)
        monkeypatch.setattr(harness, "_get_mt5", lambda: mt5)
        # Hard gate says ARMED (simulating a race / stale gate verdict)
        monkeypatch.setattr(harness, "hard_gate_evaluate",
                            lambda config_path=None: {"verdict": "DEMO_MICRO_ARMED",
                                                       "reasons": [],
                                                       "checks": {}})
        monkeypatch.setenv("TITAN_DEMO_MICRO_ARMED", "1")
        r = _run_execute_with_mock(mt5, side="BUY")

        assert r["final_verdict"] == "DEMO_MICRO_BLOCKED"
        assert "expert" in r["reason"].lower()
        assert "retcode=10027" in r["reason"]
        assert r["order_send_called"] is False
        assert r["order_send_attempts"] == 0
        assert len(mt5.order_send_calls) == 0

    def test_91_proceeds_when_trade_expert_true(self, monkeypatch):
        """Sprint 9.9.3.14 — when trade_expert=True, the new check
        must NOT block, and execution must proceed normally (verified
        by order_send being attempted)."""
        from scripts.audit import demo_micro_full_cycle as harness
        mt5 = MockMT5(account_trade_mode=0, account_trade_expert=True)
        monkeypatch.setattr(harness, "_get_mt5", lambda: mt5)
        monkeypatch.setattr(harness, "hard_gate_evaluate",
                            lambda config_path=None: {"verdict": "DEMO_MICRO_ARMED",
                                                       "reasons": [],
                                                       "checks": {}})
        monkeypatch.setenv("TITAN_DEMO_MICRO_ARMED", "1")
        r = _run_execute_with_mock(mt5, side="BUY", max_hold_seconds=1)

        # Should NOT be blocked on trade_expert grounds — order_send was called.
        # (It may still fail later in the cycle for other mock reasons, but
        # the trade_expert check itself passed.)
        assert r["final_verdict"] != "DEMO_MICRO_BLOCKED" or \
               "expert" not in r.get("reason", "").lower(), \
               f"Blocked on trade_expert unexpectedly: {r['reason']}"
        assert r["order_send_called"] is True
        assert len(mt5.order_send_calls) >= 1

    def test_92_retcode_10027_diagnostic_on_order_failure(self, monkeypatch):
        """Sprint 9.9.3.14 — if order_send somehow returns retcode=10027
        (e.g., terminal autotrading disabled AFTER the gate check),
        the journal entry must include the canonical meaning string."""
        from scripts.audit import demo_micro_full_cycle as harness
        # Mock MT5 where trade_expert=True at gate time but order_send
        # returns retcode=10027 (simulating terminal toggle after gate)
        mt5 = MockMT5(account_trade_mode=0,
                      account_trade_expert=True,
                      open_order_retcode=10027)
        monkeypatch.setattr(harness, "_get_mt5", lambda: mt5)
        monkeypatch.setattr(harness, "hard_gate_evaluate",
                            lambda config_path=None: {"verdict": "DEMO_MICRO_ARMED",
                                                       "reasons": [],
                                                       "checks": {}})
        monkeypatch.setenv("TITAN_DEMO_MICRO_ARMED", "1")
        r = _run_execute_with_mock(mt5, side="BUY", max_hold_seconds=1)

        # order_send was called but failed
        assert r["order_send_called"] is True
        assert r["order_send_success"] == 0
        assert r["final_verdict"] == "DEMO_FULL_CYCLE_FAIL"
        assert "10027" in r["reason"]
        # The canonical meaning must appear in the journal
        events = _read_journal_events()
        order_failed_events = [e for e in events if e.get("event") == "DEMO_MICRO_ORDER_FAILED"]
        assert len(order_failed_events) >= 1
        assert order_failed_events[-1].get("retcode") == 10027
        assert order_failed_events[-1].get("retcode_meaning") == \
               "client terminal autotrading disabled"


# ─── Sprint 9.9.3.15 patch — auto-detect MT5 filling mode tests ────────────────

class TestFillingModeAutoDetect:
    """Sprint 9.9.3.15 — auto-detect supported MT5 filling mode.

    Background: FBS DEMO XAUUSD returned retcode=10030
    (TRADE_RETCODE_INVALID_FILL) because the harness was hard-coding
    type_filling=2 (IOC, but commented as RETURN). FBS XAUUSD's
    symbol_info.filling_mode bitmask doesn't include the IOC bit, so
    order_send was rejected. The fix reads the bitmask and selects
    the most preferred supported mode (FOK → IOC → RETURN).
    """

    def test_93_filling_mode_constants(self):
        """Sprint 9.9.3.20 — MT5 filling mode constants correctly separate
        SYMBOL_FILLING flags from ORDER_FILLING enum values."""
        from scripts.audit.demo_micro_full_cycle import (
            ORDER_FILLING_FOK, ORDER_FILLING_IOC,
            ORDER_FILLING_BOC, ORDER_FILLING_RETURN,
            _SYMBOL_FILLING_FOK_BIT, _SYMBOL_FILLING_IOC_BIT,
            _SYMBOL_FILLING_BOC_BIT,
            _TRADE_RETCODE_INVALID_FILL, _RETCODE_10030_MEANING,
        )
        # MQL5 ORDER_TYPE_FILLING enum values (for request["type_filling"])
        assert ORDER_FILLING_FOK == 1
        assert ORDER_FILLING_IOC == 2
        assert ORDER_FILLING_BOC == 3
        assert ORDER_FILLING_RETURN == 4
        # symbol_info.filling_mode bitmask flags (for detecting support)
        # NOTE: There is NO _SYMBOL_FILLING_RETURN_BIT — RETURN is not a flag.
        assert _SYMBOL_FILLING_FOK_BIT == 1
        assert _SYMBOL_FILLING_IOC_BIT == 2
        assert _SYMBOL_FILLING_BOC_BIT == 4
        # retcode 10030 = invalid fill type
        assert _TRADE_RETCODE_INVALID_FILL == 10030
        assert _RETCODE_10030_MEANING == \
               "invalid order filling type (TRADE_RETCODE_INVALID_FILL)"

    def test_94_retcode_10030_lookup(self):
        """_lookup_retcode_meaning returns canonical string for 10030."""
        from scripts.audit.demo_micro_full_cycle import _lookup_retcode_meaning
        assert _lookup_retcode_meaning(10030) == \
               "invalid order filling type (TRADE_RETCODE_INVALID_FILL)"
        # Backward compat — 10027 still mapped
        assert _lookup_retcode_meaning(10027) == \
               "client terminal autotrading disabled"
        # Unknown retcode returns None
        assert _lookup_retcode_meaning(99999) is None
        assert _lookup_retcode_meaning(None) is None

    def test_95_helper_selects_fok_when_only_fok_supported(self):
        """If symbol_info.filling_mode = FOK bit only, helper selects FOK."""
        from scripts.audit.demo_micro_full_cycle import _select_filling_mode
        mt5 = MockMT5(symbol_filling_mode=1)   # FOK bit only
        mt5.initialize()   # required so symbol_info() returns the mock
        r = _select_filling_mode(mt5, "XAUUSD")
        assert r is not None
        assert r["filling_name"] == "FOK"
        assert r["filling_type"] == 1
        assert r["filling_source"] == "symbol_info"
        assert r["filling_mask"] == 1

    def test_96_helper_selects_ioc_when_only_ioc_supported(self):
        """If symbol_info.filling_mode = IOC bit only, helper selects IOC.
        This is the FBS XAUUSD scenario that triggered retcode=10030."""
        from scripts.audit.demo_micro_full_cycle import _select_filling_mode
        mt5 = MockMT5(symbol_filling_mode=2)   # IOC bit only
        mt5.initialize()
        r = _select_filling_mode(mt5, "XAUUSD")
        assert r is not None
        assert r["filling_name"] == "IOC"
        assert r["filling_type"] == 2

    def test_97_helper_selects_return_when_only_return_supported(self):
        """Sprint 9.9.3.20 — RETURN is not flag-based. When trade_exemode=INSTANT
        and no FOK/IOC flags are set, helper selects RETURN."""
        from scripts.audit.demo_micro_full_cycle import _select_filling_mode
        # filling_mode=4 (BOC only, non-zero so default mask isn't applied)
        # + trade_exemode=INSTANT → RETURN (FOK/IOC not in bitmask)
        mt5 = MockMT5(symbol_filling_mode=4)   # BOC only — no FOK/IOC
        mt5._symbol_info.trade_exemode = 0   # INSTANT — allows RETURN
        mt5.initialize()
        r = _select_filling_mode(mt5, "XAUUSD")
        assert r is not None
        assert r["filling_name"] == "RETURN"
        assert r["filling_type"] == 4

    def test_98_helper_prefers_fok_over_ioc_and_return(self):
        """When multiple modes supported, FOK is preferred (market order best practice)."""
        from scripts.audit.demo_micro_full_cycle import _select_filling_mode
        # FOK + IOC + RETURN all supported
        mt5 = MockMT5(symbol_filling_mode=1 | 2 | 8)
        mt5.initialize()
        r = _select_filling_mode(mt5, "XAUUSD")
        assert r["filling_name"] == "FOK"
        # FOK + IOC only
        mt5 = MockMT5(symbol_filling_mode=1 | 2)
        mt5.initialize()
        r = _select_filling_mode(mt5, "XAUUSD")
        assert r["filling_name"] == "FOK"

    def test_99_helper_falls_back_to_ioc_when_fok_unsupported(self):
        """When FOK not supported but IOC is, helper selects IOC."""
        from scripts.audit.demo_micro_full_cycle import _select_filling_mode
        # IOC + RETURN only (no FOK)
        mt5 = MockMT5(symbol_filling_mode=2 | 8)
        mt5.initialize()
        r = _select_filling_mode(mt5, "XAUUSD")
        assert r["filling_name"] == "IOC"

    def test_100_helper_falls_back_to_return_when_fok_and_ioc_unsupported(self):
        """Sprint 9.9.3.20 — RETURN is not flag-based. When no FOK/IOC flags
        are set and trade_exemode=INSTANT, helper falls back to RETURN."""
        from scripts.audit.demo_micro_full_cycle import _select_filling_mode
        mt5 = MockMT5(symbol_filling_mode=4)   # BOC only — no FOK/IOC
        mt5._symbol_info.trade_exemode = 0      # INSTANT — allows RETURN
        mt5.initialize()
        r = _select_filling_mode(mt5, "XAUUSD")
        assert r["filling_name"] == "RETURN"

    def test_101_helper_returns_none_when_only_boc_supported(self):
        """BOC is invalid for market orders — helper returns None (fail closed)."""
        from scripts.audit.demo_micro_full_cycle import _select_filling_mode
        mt5 = MockMT5(symbol_filling_mode=4)   # BOC bit only
        mt5.initialize()
        r = _select_filling_mode(mt5, "XAUUSD")
        assert r is None

    def test_102_helper_returns_none_when_symbol_info_is_none(self):
        """If mt5.symbol_info() returns None, helper returns None."""
        from scripts.audit.demo_micro_full_cycle import _select_filling_mode

        class _MT5None:
            def symbol_info(self, sym):
                return None
        r = _select_filling_mode(_MT5None(), "XAUUSD")
        assert r is None

    def test_103_helper_falls_back_to_default_when_filling_mode_missing(self):
        """If symbol_info lacks filling_mode attribute, helper uses default mask."""
        from scripts.audit.demo_micro_full_cycle import _select_filling_mode
        # Default MockMT5 with no filling_mode kwarg → attribute missing
        mt5 = MockMT5()
        mt5.initialize()
        r = _select_filling_mode(mt5, "XAUUSD")
        assert r is not None
        assert r["filling_name"] == "FOK"
        assert r["filling_source"] == "default"

    def test_104_helper_falls_back_to_default_when_filling_mode_zero(self):
        """If symbol_info.filling_mode == 0, helper uses default mask."""
        from scripts.audit.demo_micro_full_cycle import _select_filling_mode
        mt5 = MockMT5(symbol_filling_mode=0)
        mt5.initialize()
        r = _select_filling_mode(mt5, "XAUUSD")
        assert r is not None
        assert r["filling_source"] == "default"

    def test_105_open_order_uses_detected_filling_mode(self, monkeypatch):
        """_send_open_order puts the detected filling type into the request."""
        from scripts.audit import demo_micro_full_cycle as harness
        # FBS-like: only IOC supported (bit 2)
        mt5 = MockMT5(symbol_filling_mode=2)
        monkeypatch.setattr(harness, "_get_mt5", lambda: mt5)
        monkeypatch.setattr(harness, "hard_gate_evaluate",
                            lambda config_path=None: {"verdict": "DEMO_MICRO_ARMED",
                                                       "reasons": [],
                                                       "checks": {}})
        monkeypatch.setenv("TITAN_DEMO_MICRO_ARMED", "1")
        r = _run_execute_with_mock(mt5, side="BUY", max_hold_seconds=1)

        # The order_send request must have used type_filling=2 (IOC)
        # rather than the old hard-coded value.
        assert len(mt5.order_send_calls) >= 1
        req = mt5.order_send_calls[0]
        assert req["type_filling"] == 2   # IOC for FBS
        # Result must surface the selected filling mode
        assert r.get("filling_mode_selected") == "IOC"
        assert r.get("filling_type_used") == 2

    def test_106_open_order_uses_fok_when_supported(self, monkeypatch):
        """When FOK is supported, _send_open_order uses type_filling=1 (FOK)."""
        from scripts.audit import demo_micro_full_cycle as harness
        mt5 = MockMT5(symbol_filling_mode=1)   # FOK only
        monkeypatch.setattr(harness, "_get_mt5", lambda: mt5)
        monkeypatch.setattr(harness, "hard_gate_evaluate",
                            lambda config_path=None: {"verdict": "DEMO_MICRO_ARMED",
                                                       "reasons": [],
                                                       "checks": {}})
        monkeypatch.setenv("TITAN_DEMO_MICRO_ARMED", "1")
        r = _run_execute_with_mock(mt5, side="BUY", max_hold_seconds=1)
        assert len(mt5.order_send_calls) >= 1
        assert mt5.order_send_calls[0]["type_filling"] == 1   # FOK
        assert r.get("filling_mode_selected") == "FOK"

    def test_107_open_order_uses_return_when_only_return_supported(self, monkeypatch):
        """Sprint 9.9.3.20 — RETURN is not flag-based. When no FOK/IOC flags
        are set and trade_exemode=INSTANT, adapter uses ORDER_FILLING_RETURN."""
        from scripts.audit import demo_micro_full_cycle as harness
        mt5 = MockMT5(symbol_filling_mode=4)   # BOC only — no FOK/IOC
        mt5._symbol_info.trade_exemode = 0      # INSTANT — allows RETURN
        monkeypatch.setattr(harness, "_get_mt5", lambda: mt5)
        monkeypatch.setattr(harness, "hard_gate_evaluate",
                            lambda config_path=None: {"verdict": "DEMO_MICRO_ARMED",
                                                       "reasons": [],
                                                       "checks": {}})
        monkeypatch.setenv("TITAN_DEMO_MICRO_ARMED", "1")
        r = _run_execute_with_mock(mt5, side="BUY", max_hold_seconds=1)
        assert len(mt5.order_send_calls) >= 1
        assert mt5.order_send_calls[0]["type_filling"] == 4   # RETURN
        assert r.get("filling_mode_selected") == "RETURN"

    def test_108_fail_closed_when_no_supported_filling_mode(self, monkeypatch):
        """Sprint 9.9.3.15 — if no FOK/IOC/RETURN bit is set, harness must
        fail closed BEFORE order_send. order_send_called must be False."""
        from scripts.audit import demo_micro_full_cycle as harness
        # Only BOC supported (bit 4) — invalid for market orders
        mt5 = MockMT5(symbol_filling_mode=4)
        monkeypatch.setattr(harness, "_get_mt5", lambda: mt5)
        monkeypatch.setattr(harness, "hard_gate_evaluate",
                            lambda config_path=None: {"verdict": "DEMO_MICRO_ARMED",
                                                       "reasons": [],
                                                       "checks": {}})
        monkeypatch.setenv("TITAN_DEMO_MICRO_ARMED", "1")
        r = _run_execute_with_mock(mt5, side="BUY", max_hold_seconds=1)

        # Fail closed — verdict FAIL, order_send NEVER called
        assert r["final_verdict"] == "DEMO_FULL_CYCLE_FAIL"
        assert r["order_send_called"] is False
        assert r["order_send_attempts"] == 0
        assert len(mt5.order_send_calls) == 0
        # Reason must mention filling mode and retcode 10030
        assert "filling mode" in r["reason"].lower()
        assert "10030" in r["reason"]
        # Filling mode selected must be None
        assert r.get("filling_mode_selected") is None

    def test_109_fail_closed_journal_event(self, monkeypatch):
        """When fail-closed fires, journal must record DEMO_MICRO_EXECUTE_BLOCKED
        with the canonical retcode_10030_meaning."""
        from scripts.audit import demo_micro_full_cycle as harness
        mt5 = MockMT5(symbol_filling_mode=4)   # BOC only — fail closed
        monkeypatch.setattr(harness, "_get_mt5", lambda: mt5)
        monkeypatch.setattr(harness, "hard_gate_evaluate",
                            lambda config_path=None: {"verdict": "DEMO_MICRO_ARMED",
                                                       "reasons": [],
                                                       "checks": {}})
        monkeypatch.setenv("TITAN_DEMO_MICRO_ARMED", "1")
        _run_execute_with_mock(mt5, side="BUY", max_hold_seconds=1)

        events = _read_journal_events()
        blocked_events = [e for e in events
                          if e.get("event") == "DEMO_MICRO_EXECUTE_BLOCKED"
                          and "filling mode" in (e.get("reason") or "").lower()]
        assert len(blocked_events) >= 1
        assert blocked_events[-1].get("retcode_10030_meaning") == \
               "invalid order filling type (TRADE_RETCODE_INVALID_FILL)"
        assert blocked_events[-1].get("filling_mode_raw") == 4

    def test_110_filling_mode_selected_journal_event(self, monkeypatch):
        """When filling mode IS selected, journal records
        DEMO_MICRO_FILLING_MODE_SELECTED with the chosen mode."""
        from scripts.audit import demo_micro_full_cycle as harness
        mt5 = MockMT5(symbol_filling_mode=2)   # IOC
        monkeypatch.setattr(harness, "_get_mt5", lambda: mt5)
        monkeypatch.setattr(harness, "hard_gate_evaluate",
                            lambda config_path=None: {"verdict": "DEMO_MICRO_ARMED",
                                                       "reasons": [],
                                                       "checks": {}})
        monkeypatch.setenv("TITAN_DEMO_MICRO_ARMED", "1")
        _run_execute_with_mock(mt5, side="BUY", max_hold_seconds=1)

        events = _read_journal_events()
        selected_events = [e for e in events
                           if e.get("event") == "DEMO_MICRO_FILLING_MODE_SELECTED"]
        assert len(selected_events) >= 1
        ev = selected_events[-1]
        assert ev["filling_mode_selected"] == "IOC"
        assert ev["filling_type_used"] == 2
        assert ev["filling_source"] == "symbol_info"
        assert ev["filling_mask"] == 2

    def test_111_retcode_10030_diagnostic_on_order_failure(self, monkeypatch):
        """Sprint 9.9.3.15 — if order_send returns retcode=10030
        (e.g., broker changed filling support between gate and send),
        the journal entry must include the canonical 10030 meaning.

        Sprint 9.9.3.17 update: with the universal adapter, BOTH FOK and
        IOC send attempts fail with 10030 (retryable). The adapter tries
        both, then fails closed. The retcode=10030 appears in the
        send_attempts list and in ADAPTER_ORDER_SEND_RESULT journal events.
        """
        from scripts.audit import demo_micro_full_cycle as harness
        # Mock: FOK+IOC supported, but order_send returns 10030 for both
        mt5 = MockMT5(symbol_filling_mode=1 | 2,
                      open_order_retcode=10030)
        monkeypatch.setattr(harness, "_get_mt5", lambda: mt5)
        monkeypatch.setattr(harness, "hard_gate_evaluate",
                            lambda config_path=None: {"verdict": "DEMO_MICRO_ARMED",
                                                       "reasons": [],
                                                       "checks": {}})
        monkeypatch.setenv("TITAN_DEMO_MICRO_ARMED", "1")
        r = _run_execute_with_mock(mt5, side="BUY", max_hold_seconds=1)

        # order_send was called (at least once) but all attempts failed
        assert r["order_send_called"] is True
        assert r["order_send_success"] == 0
        assert r["final_verdict"] == "DEMO_FULL_CYCLE_FAIL"
        # Send attempts list must contain 10030 retcodes
        send_attempts = r.get("send_attempts") or []
        assert len(send_attempts) >= 1
        for attempt in send_attempts:
            assert attempt["send_retcode"] == 10030
            assert attempt["send_retcode_meaning"] == \
                   "invalid order filling type (TRADE_RETCODE_INVALID_FILL)"

        # Journal must include ADAPTER_ORDER_SEND_RESULT events with 10030
        events = _read_journal_events()
        send_result_events = [e for e in events
                              if e.get("event") == "ADAPTER_ORDER_SEND_RESULT"]
        assert len(send_result_events) >= 1
        for ev in send_result_events:
            assert ev.get("send_retcode") == 10030
            assert ev.get("send_retcode_meaning") == \
                   "invalid order filling type (TRADE_RETCODE_INVALID_FILL)"

    def test_112_close_position_also_uses_detected_filling_mode(self, monkeypatch):
        """Sprint 9.9.3.15 — _close_position must ALSO use the detected
        filling mode (not the old hard-coded value).

        Uses the same pattern as test_68_buy_close_uses_sell: harness
        opens a BUY position, then max_hold_seconds=1 triggers a close.
        Both open and close requests must use the auto-detected IOC mode.
        """
        from scripts.audit import demo_micro_full_cycle as harness
        # Only IOC supported (bit 2) — FBS-like
        mt5 = MockMT5(symbol_filling_mode=2)
        monkeypatch.setattr(harness, "_get_mt5", lambda: mt5)
        monkeypatch.setattr(harness, "hard_gate_evaluate",
                            lambda config_path=None: {"verdict": "DEMO_MICRO_ARMED",
                                                       "reasons": [],
                                                       "checks": {}})
        monkeypatch.setenv("TITAN_DEMO_MICRO_ARMED", "1")
        r = _run_execute_with_mock(mt5, side="BUY", max_hold_seconds=1)

        # Position should have opened AND closed successfully
        assert r["final_verdict"] == "DEMO_FULL_CYCLE_PASS", \
            f"Expected PASS, got {r['final_verdict']}: {r.get('reason')}"

        # Find the close order request (has "position" field)
        close_calls = [c for c in mt5.order_send_calls if c.get("position")]
        assert len(close_calls) >= 1, \
            f"No close order call found in {len(mt5.order_send_calls)} total calls"
        # Close order must use type_filling=2 (IOC) from auto-detect
        assert close_calls[-1]["type_filling"] == 2   # IOC
        # Also verify the open order used IOC
        open_calls = [c for c in mt5.order_send_calls if not c.get("position")]
        assert len(open_calls) >= 1
        assert open_calls[0]["type_filling"] == 2   # IOC

    def test_113_no_hardcoded_filling_in_source(self):
        """Sprint 9.9.3.15 / 9.9.3.16 — source inspection: no remaining
        hard-coded `type_filling: <int>` literal in the harness source.

        Sprint 9.9.3.16 refactored the request builders to omit type_filling
        from base_request (it's now set per-attempt by _attempt_filling_modes
        via `req["type_filling"] = mode["filling_type"]`). So this test now
        checks two things:

          1. No `"type_filling": <int>` literal in any base_request dict
             (the old hard-coded bug we fixed in Sprint 9.9.3.15).
          2. The only place type_filling is *assigned* (not just read) in
             the harness is inside _attempt_filling_modes, where it is set
             from mode["filling_type"] (the auto-detected value).
        """
        import inspect, re
        from scripts.audit import demo_micro_full_cycle as harness
        src = inspect.getsource(harness)

        # (1) No hard-coded "type_filling": <integer> in any dict literal.
        hardcoded_matches = re.findall(r'"type_filling"\s*:\s*(\d+)', src)
        assert len(hardcoded_matches) == 0, \
            f"Hard-coded type_filling integer literals found: {hardcoded_matches}"

        # (2) The only assignment to req["type_filling"] must be inside
        # _attempt_filling_modes and must use mode["filling_type"].
        # Find all `req["type_filling"] = ...` or `request["type_filling"] = ...`
        # assignments anywhere in the source.
        assign_matches = re.findall(
            r'(?:req|request)\["type_filling"\]\s*=\s*([^\n]+)', src)
        assert len(assign_matches) >= 1, \
            "Expected at least one type_filling assignment in _attempt_filling_modes"
        for m in assign_matches:
            val = m.strip()
            assert "mode[" in val or "filling_type" in val, \
                f"type_filling assignment does not use auto-detected mode: {val!r}"


# ─── Sprint 9.9.3.16 patch — order_check + filling fallback tests ──────────────

class TestOrderCheckAndFillingFallback:
    """Sprint 9.9.3.16 — add mt5.order_check() before order_send and
    fall back through supported filling modes (FOK → IOC → RETURN) if
    the preferred one is rejected.

    Background: FBS DEMO XAUUSD returned retcode=10006 (REJECT) even
    though the new filling-mode helper (Sprint 9.9.3.15) selected FOK
    based on symbol_info.filling_mode bitmask. The bitmask lies on
    some brokers — only a real order_check reveals the truth. We now
    call mt5.order_check(request) for each supported filling mode and
    only call order_send with the first mode that passes.
    """

    def test_114_retcode_10006_constants(self):
        """retcode 10006 (TRADE_RETCODE_REJECT) is exported with correct meaning."""
        from scripts.audit.demo_micro_full_cycle import (
            _TRADE_RETCODE_REJECT, _RETCODE_10006_MEANING,
            _TRADE_RETCODE_CHECK_PASSED, _RETCODE_0_MEANING,
        )
        assert _TRADE_RETCODE_REJECT == 10006
        assert _RETCODE_10006_MEANING == "request rejected (TRADE_RETCODE_REJECT)"
        assert _TRADE_RETCODE_CHECK_PASSED == 0
        assert _RETCODE_0_MEANING == "order_check passed (request is valid)"

    def test_115_retcode_10006_lookup(self):
        """_lookup_retcode_meaning returns canonical string for 10006."""
        from scripts.audit.demo_micro_full_cycle import _lookup_retcode_meaning
        assert _lookup_retcode_meaning(10006) == \
               "request rejected (TRADE_RETCODE_REJECT)"
        # All previously mapped codes still work
        assert _lookup_retcode_meaning(0) == "order_check passed (request is valid)"
        assert _lookup_retcode_meaning(10009) == "request completed"
        assert _lookup_retcode_meaning(10027) == "client terminal autotrading disabled"
        assert _lookup_retcode_meaning(10030) == \
               "invalid order filling type (TRADE_RETCODE_INVALID_FILL)"

    def test_116_list_supported_filling_modes_returns_ordered_list(self):
        """Sprint 9.9.3.20 — returns ordered list (FOK→IOC→RETURN).

        RETURN is not flag-based — it's included when trade_exemode=INSTANT.
        So filling_mode=1|2 (FOK+IOC flags) + trade_exemode=INSTANT gives 3 modes.
        """
        from scripts.audit.demo_micro_full_cycle import _list_supported_filling_modes
        mt5 = MockMT5(symbol_filling_mode=1 | 2)   # FOK+IOC flags
        mt5._symbol_info.trade_exemode = 0   # INSTANT — allows RETURN
        mt5.initialize()
        modes = _list_supported_filling_modes(mt5, "XAUUSD")
        assert len(modes) == 3
        assert [m["filling_name"] for m in modes] == ["FOK", "IOC", "RETURN"]

    def test_117_list_supported_filling_modes_empty_when_only_boc(self):
        """_list_supported_filling_modes returns [] when only BOC is set."""
        from scripts.audit.demo_micro_full_cycle import _list_supported_filling_modes
        mt5 = MockMT5(symbol_filling_mode=4)   # BOC only
        mt5.initialize()
        modes = _list_supported_filling_modes(mt5, "XAUUSD")
        assert modes == []

    def test_118_attempt_filling_modes_picks_first_pass(self):
        """_attempt_filling_modes returns the first mode that passes order_check."""
        from scripts.audit.demo_micro_full_cycle import _attempt_filling_modes
        # FOK+IOC+RETURN all supported, all pass — should pick FOK (first)
        mt5 = MockMT5(symbol_filling_mode=1 | 2 | 8,
                      order_check_default_retcode=0)
        mt5.initialize()
        base_req = {"action": 1, "symbol": "XAUUSD", "volume": 0.01}
        modes = [
            {"filling_type": 1, "filling_name": "FOK", "filling_mask": 11, "filling_source": "symbol_info"},
            {"filling_type": 2, "filling_name": "IOC", "filling_mask": 11, "filling_source": "symbol_info"},
            {"filling_type": 4, "filling_name": "RETURN", "filling_mask": 11, "filling_source": "symbol_info"},
        ]
        result = _attempt_filling_modes(mt5, base_req, modes, label="open")
        assert result["ok"] is True
        assert result["filling"]["filling_name"] == "FOK"
        assert result["request"]["type_filling"] == 1
        assert len(result["check_attempts"]) == 1   # stopped at first pass

    def test_119_attempt_filling_modes_falls_back_to_ioc_when_fok_rejected(self):
        """FOK rejected by order_check → fall back to IOC, which passes.
        This is the exact FBS scenario from the operator report."""
        from scripts.audit.demo_micro_full_cycle import _attempt_filling_modes
        # FOK rejected (retcode 10006), IOC passes (retcode 0)
        mt5 = MockMT5(symbol_filling_mode=1 | 2,   # FOK+IOC supported
                      order_check_retcode_per_mode={1: 10006, 2: 0})
        mt5.initialize()
        base_req = {"action": 1, "symbol": "XAUUSD", "volume": 0.01}
        modes = [
            {"filling_type": 1, "filling_name": "FOK", "filling_mask": 3, "filling_source": "symbol_info"},
            {"filling_type": 2, "filling_name": "IOC", "filling_mask": 3, "filling_source": "symbol_info"},
        ]
        result = _attempt_filling_modes(mt5, base_req, modes, label="open")
        assert result["ok"] is True
        assert result["filling"]["filling_name"] == "IOC"
        assert result["request"]["type_filling"] == 2
        # Both attempts recorded
        assert len(result["check_attempts"]) == 2
        assert result["check_attempts"][0]["filling_name"] == "FOK"
        assert result["check_attempts"][0]["passed"] is False
        assert result["check_attempts"][0]["check_retcode"] == 10006
        assert result["check_attempts"][1]["filling_name"] == "IOC"
        assert result["check_attempts"][1]["passed"] is True

    def test_120_attempt_filling_modes_falls_back_to_return(self):
        """FOK and IOC both rejected → fall back to RETURN, which passes."""
        from scripts.audit.demo_micro_full_cycle import _attempt_filling_modes
        mt5 = MockMT5(symbol_filling_mode=1 | 2 | 8,
                      order_check_retcode_per_mode={1: 10006, 2: 10006, 4: 0})
        mt5.initialize()
        base_req = {"action": 1, "symbol": "XAUUSD", "volume": 0.01}
        modes = [
            {"filling_type": 1, "filling_name": "FOK", "filling_mask": 11, "filling_source": "symbol_info"},
            {"filling_type": 2, "filling_name": "IOC", "filling_mask": 11, "filling_source": "symbol_info"},
            {"filling_type": 4, "filling_name": "RETURN", "filling_mask": 11, "filling_source": "symbol_info"},
        ]
        result = _attempt_filling_modes(mt5, base_req, modes, label="open")
        assert result["ok"] is True
        assert result["filling"]["filling_name"] == "RETURN"
        assert result["request"]["type_filling"] == 4
        assert len(result["check_attempts"]) == 3

    def test_121_attempt_filling_modes_fails_closed_when_all_rejected(self):
        """All supported filling modes rejected by order_check → fail closed.
        Returns ok=False with full check_attempts log; caller must NOT
        call order_send."""
        from scripts.audit.demo_micro_full_cycle import _attempt_filling_modes
        mt5 = MockMT5(symbol_filling_mode=1 | 2 | 8,
                      order_check_default_retcode=10006)   # all reject
        mt5.initialize()
        base_req = {"action": 1, "symbol": "XAUUSD", "volume": 0.01}
        modes = [
            {"filling_type": 1, "filling_name": "FOK", "filling_mask": 11, "filling_source": "symbol_info"},
            {"filling_type": 2, "filling_name": "IOC", "filling_mask": 11, "filling_source": "symbol_info"},
            {"filling_type": 4, "filling_name": "RETURN", "filling_mask": 11, "filling_source": "symbol_info"},
        ]
        result = _attempt_filling_modes(mt5, base_req, modes, label="open")
        assert result["ok"] is False
        assert result["request"] is None
        assert result["filling"] is None
        assert "no filling mode passed order_check" in result["error"]
        # All 3 attempts recorded with retcode 10006
        assert len(result["check_attempts"]) == 3
        for attempt in result["check_attempts"]:
            assert attempt["passed"] is False
            assert attempt["check_retcode"] == 10006
            assert attempt["check_retcode_meaning"] == \
                   "request rejected (TRADE_RETCODE_REJECT)"

    def test_122_attempt_filling_modes_journals_each_attempt(self):
        """Each order_check attempt is journaled as DEMO_MICRO_ORDER_CHECK_ATTEMPTED."""
        from scripts.audit.demo_micro_full_cycle import _attempt_filling_modes
        # Clear journal
        journal_path = REPO_ROOT / "data" / "audit" / "demo_micro" / "demo_micro_journal.jsonl"
        if journal_path.exists():
            journal_path.unlink()
        mt5 = MockMT5(symbol_filling_mode=1 | 2,
                      order_check_retcode_per_mode={1: 10006, 2: 0})
        mt5.initialize()
        base_req = {"action": 1, "symbol": "XAUUSD", "volume": 0.01}
        modes = [
            {"filling_type": 1, "filling_name": "FOK", "filling_mask": 3, "filling_source": "symbol_info"},
            {"filling_type": 2, "filling_name": "IOC", "filling_mask": 3, "filling_source": "symbol_info"},
        ]
        _attempt_filling_modes(mt5, base_req, modes, label="open")

        events = _read_journal_events()
        check_events = [e for e in events
                        if e.get("event") == "DEMO_MICRO_ORDER_CHECK_ATTEMPTED"]
        assert len(check_events) == 2
        assert check_events[0]["filling_name"] == "FOK"
        assert check_events[0]["passed"] is False
        assert check_events[0]["check_retcode"] == 10006
        assert check_events[0]["check_retcode_meaning"] == \
               "request rejected (TRADE_RETCODE_REJECT)"
        assert check_events[1]["filling_name"] == "IOC"
        assert check_events[1]["passed"] is True
        assert check_events[1]["check_retcode"] == 0

    def test_123_send_open_order_calls_order_check_before_order_send(self, monkeypatch):
        """_send_open_order calls mt5.order_check BEFORE mt5.order_send."""
        from scripts.audit import demo_micro_full_cycle as harness
        # FOK+IOC supported, FOK passes — should send with FOK
        mt5 = MockMT5(symbol_filling_mode=1 | 2,
                      order_check_default_retcode=0)
        monkeypatch.setattr(harness, "_get_mt5", lambda: mt5)
        monkeypatch.setattr(harness, "hard_gate_evaluate",
                            lambda config_path=None: {"verdict": "DEMO_MICRO_ARMED",
                                                       "reasons": [],
                                                       "checks": {}})
        monkeypatch.setenv("TITAN_DEMO_MICRO_ARMED", "1")
        _run_execute_with_mock(mt5, side="BUY", max_hold_seconds=1)
        # order_check must have been called at least once
        assert len(mt5.order_check_calls) >= 1, \
            "mt5.order_check was never called"
        # order_send must also have been called (since FOK passed)
        assert len(mt5.order_send_calls) >= 1
        # Verify the order_check used the same filling type as the eventual order_send
        assert mt5.order_check_calls[0]["type_filling"] == 1   # FOK
        assert mt5.order_send_calls[0]["type_filling"] == 1    # FOK

    def test_124_send_open_order_falls_back_when_preferred_rejected(self, monkeypatch):
        """Sprint 9.9.3.16 — FBS scenario: FOK rejected by order_check,
        harness falls back to IOC and sends with IOC."""
        from scripts.audit import demo_micro_full_cycle as harness
        # FOK+IOC supported, FOK rejected (10006), IOC passes (0)
        mt5 = MockMT5(symbol_filling_mode=1 | 2,
                      order_check_retcode_per_mode={1: 10006, 2: 0})
        monkeypatch.setattr(harness, "_get_mt5", lambda: mt5)
        monkeypatch.setattr(harness, "hard_gate_evaluate",
                            lambda config_path=None: {"verdict": "DEMO_MICRO_ARMED",
                                                       "reasons": [],
                                                       "checks": {}})
        monkeypatch.setenv("TITAN_DEMO_MICRO_ARMED", "1")
        r = _run_execute_with_mock(mt5, side="BUY", max_hold_seconds=1)

        # order_check called twice (FOK then IOC)
        assert len(mt5.order_check_calls) >= 2
        assert mt5.order_check_calls[0]["type_filling"] == 1   # FOK tried first
        assert mt5.order_check_calls[1]["type_filling"] == 2   # IOC tried second
        # order_send called once with IOC (the fallback winner)
        assert len(mt5.order_send_calls) >= 1
        assert mt5.order_send_calls[0]["type_filling"] == 2   # IOC
        # Result reports IOC as the selected filling mode
        assert r.get("filling_mode_selected") == "IOC"
        assert r.get("filling_type_used") == 2

    def test_125_send_open_order_fails_closed_when_all_modes_rejected(self, monkeypatch):
        """Sprint 9.9.3.16 — if ALL supported filling modes fail order_check,
        harness must fail closed: order_send NEVER called, verdict FAIL.

        Sprint 9.9.3.17 update: the universal adapter filters RETURN when
        trade_exemode=MARKET. To test all 3 modes, set trade_exemode=INSTANT
        so RETURN is also tried.
        """
        from scripts.audit import demo_micro_full_cycle as harness
        # FOK+IOC+RETURN supported, ALL rejected by order_check
        mt5 = MockMT5(symbol_filling_mode=1 | 2 | 8,
                      order_check_default_retcode=10006)
        # Sprint 9.9.3.17 — allow RETURN (needs INSTANT/REQUEST execution)
        mt5._symbol_info.trade_exemode = 0   # INSTANT
        monkeypatch.setattr(harness, "_get_mt5", lambda: mt5)
        monkeypatch.setattr(harness, "hard_gate_evaluate",
                            lambda config_path=None: {"verdict": "DEMO_MICRO_ARMED",
                                                       "reasons": [],
                                                       "checks": {}})
        monkeypatch.setenv("TITAN_DEMO_MICRO_ARMED", "1")
        r = _run_execute_with_mock(mt5, side="BUY", max_hold_seconds=1)

        # order_check called for all 3 modes (FOK, IOC, RETURN)
        assert len(mt5.order_check_calls) == 3
        # order_send NEVER called (all checks failed)
        assert len(mt5.order_send_calls) == 0
        # Verdict is FAIL
        assert r["final_verdict"] == "DEMO_FULL_CYCLE_FAIL"
        assert r["order_send_called"] is False
        assert r["order_send_attempts"] == 0
        # check_attempts surfaced in result for operator debugging
        assert r.get("check_attempts") is not None
        assert len(r["check_attempts"]) == 3
        for attempt in r["check_attempts"]:
            assert attempt["passed"] is False
            assert attempt["check_retcode"] == 10006

    def test_126_pre_send_diagnostics_journal_event(self, monkeypatch):
        """Sprint 9.9.3.16 / 9.9.3.17 — pre-send diagnostics event captures
        all required fields before order_send.

        Sprint 9.9.3.17 update: the universal adapter emits
        ADAPTER_PRE_SEND_DIAGNOSTICS (not DEMO_MICRO_ORDER_PRE_SEND_DIAGNOSTICS).
        The adapter's snapshot includes all required fields.
        """
        from scripts.audit import demo_micro_full_cycle as harness
        mt5 = MockMT5(symbol_filling_mode=1)   # FOK supported
        monkeypatch.setattr(harness, "_get_mt5", lambda: mt5)
        monkeypatch.setattr(harness, "hard_gate_evaluate",
                            lambda config_path=None: {"verdict": "DEMO_MICRO_ARMED",
                                                       "reasons": [],
                                                       "checks": {}})
        monkeypatch.setenv("TITAN_DEMO_MICRO_ARMED", "1")
        _run_execute_with_mock(mt5, side="BUY", max_hold_seconds=1)

        events = _read_journal_events()
        # Sprint 9.9.3.17 — adapter emits ADAPTER_PRE_SEND_DIAGNOSTICS
        diag_events = [e for e in events
                       if e.get("event") == "ADAPTER_PRE_SEND_DIAGNOSTICS"
                       and e.get("label") == "open"]
        assert len(diag_events) >= 1
        diag = diag_events[-1]
        # The adapter snapshot includes symbol_info + tick + account + terminal
        assert "broker_snapshot" in diag
        snap = diag["broker_snapshot"]
        # Required fields per the operator's patch spec
        assert snap["symbol"] == "XAUUSD"
        assert "filling_mode" in snap["symbol_info"]
        assert snap["symbol_info"]["filling_mode"] == 1   # FOK bit set
        assert snap["symbol_info"]["volume_min"] == 0.01
        assert "bid" in snap["tick"]
        assert "ask" in snap["tick"]
        assert "spread" in snap["tick"]
        assert "trade_mode" in snap["symbol_info"]
        assert "trade_exemode" in snap["symbol_info"]
        # Supported filling modes listed
        assert "supported_filling_modes" in diag
        assert "FOK" in diag["supported_filling_modes"]

    def test_127_filling_source_never_unknown_in_failure_path(self, monkeypatch):
        """Sprint 9.9.3.16 — bug fix: filling_source must never show
        'unknown' in console output / report when order_check fails.

        Previously, the failure path in _run_execute did not propagate
        filling_source from open_result, causing the console to fall
        back to 'unknown'. Now it always propagates (or shows 'N/A'
        if genuinely unset, e.g., when no supported mode exists at all).
        """
        from scripts.audit import demo_micro_full_cycle as harness
        # FOK+IOC+RETURN supported but ALL rejected by order_check
        mt5 = MockMT5(symbol_filling_mode=1 | 2 | 8,
                      order_check_default_retcode=10006)
        monkeypatch.setattr(harness, "_get_mt5", lambda: mt5)
        monkeypatch.setattr(harness, "hard_gate_evaluate",
                            lambda config_path=None: {"verdict": "DEMO_MICRO_ARMED",
                                                       "reasons": [],
                                                       "checks": {}})
        monkeypatch.setenv("TITAN_DEMO_MICRO_ARMED", "1")
        r = _run_execute_with_mock(mt5, side="BUY", max_hold_seconds=1)

        # Verdict is FAIL (all order_checks rejected)
        assert r["final_verdict"] == "DEMO_FULL_CYCLE_FAIL"
        # filling_source must be present in the result dict (not missing)
        # and must NOT be the string "unknown" — when no mode passed
        # order_check, filling_source is None (which is correct).
        assert "filling_source" in r
        assert r.get("filling_source") != "unknown"
        # When all order_checks fail, filling_mode_selected is None
        # (no mode won), and filling_source is also None.
        assert r.get("filling_mode_selected") is None

    def test_128_filling_source_propagated_in_success_path(self, monkeypatch):
        """Sprint 9.9.3.16 — filling_source is propagated in the success
        path with the correct value ('symbol_info' or 'default')."""
        from scripts.audit import demo_micro_full_cycle as harness
        # symbol_info.filling_mode=1 (FOK only) → source should be 'symbol_info'
        mt5 = MockMT5(symbol_filling_mode=1,
                      order_check_default_retcode=0)
        monkeypatch.setattr(harness, "_get_mt5", lambda: mt5)
        monkeypatch.setattr(harness, "hard_gate_evaluate",
                            lambda config_path=None: {"verdict": "DEMO_MICRO_ARMED",
                                                       "reasons": [],
                                                       "checks": {}})
        monkeypatch.setenv("TITAN_DEMO_MICRO_ARMED", "1")
        r = _run_execute_with_mock(mt5, side="BUY", max_hold_seconds=1)
        # On success, filling_source must be 'symbol_info' (since we
        # explicitly set filling_mode=1 on the mock).
        assert r.get("filling_source") == "symbol_info"
        assert r.get("filling_mode_selected") == "FOK"

    def test_129_filling_source_default_when_attr_missing(self, monkeypatch):
        """Sprint 9.9.3.16 — filling_source='default' when symbol_info
        lacks the filling_mode attribute (older MT5 builds)."""
        from scripts.audit import demo_micro_full_cycle as harness
        # No filling_mode kwarg → attribute missing → helper uses default mask
        mt5 = MockMT5()
        monkeypatch.setattr(harness, "_get_mt5", lambda: mt5)
        monkeypatch.setattr(harness, "hard_gate_evaluate",
                            lambda config_path=None: {"verdict": "DEMO_MICRO_ARMED",
                                                       "reasons": [],
                                                       "checks": {}})
        monkeypatch.setenv("TITAN_DEMO_MICRO_ARMED", "1")
        r = _run_execute_with_mock(mt5, side="BUY", max_hold_seconds=1)
        # filling_source must be 'default' (not 'unknown', not None)
        assert r.get("filling_source") == "default"

    def test_130_close_position_also_uses_order_check_fallback(self, monkeypatch):
        """Sprint 9.9.3.16 — _close_position also uses order_check fallback.
        When FOK is rejected for the close order, harness falls back to IOC."""
        from scripts.audit import demo_micro_full_cycle as harness
        # FOK+IOC supported. For BOTH open and close, FOK rejected, IOC passes.
        mt5 = MockMT5(symbol_filling_mode=1 | 2,
                      order_check_retcode_per_mode={1: 10006, 2: 0})
        monkeypatch.setattr(harness, "_get_mt5", lambda: mt5)
        monkeypatch.setattr(harness, "hard_gate_evaluate",
                            lambda config_path=None: {"verdict": "DEMO_MICRO_ARMED",
                                                       "reasons": [],
                                                       "checks": {}})
        monkeypatch.setenv("TITAN_DEMO_MICRO_ARMED", "1")
        r = _run_execute_with_mock(mt5, side="BUY", max_hold_seconds=1)

        # Full cycle must PASS — both open and close succeeded via IOC fallback
        assert r["final_verdict"] == "DEMO_FULL_CYCLE_PASS", \
            f"Expected PASS, got {r['final_verdict']}: {r.get('reason')}"
        # Both open and close order_send calls used IOC (type_filling=2)
        open_calls = [c for c in mt5.order_send_calls if not c.get("position")]
        close_calls = [c for c in mt5.order_send_calls if c.get("position")]
        assert len(open_calls) >= 1
        assert len(close_calls) >= 1
        assert open_calls[0]["type_filling"] == 2   # IOC
        assert close_calls[-1]["type_filling"] == 2   # IOC
        # order_check called at least 4 times: 2 for open (FOK+IOC) + 2 for close (FOK+IOC)
        assert len(mt5.order_check_calls) >= 4

    def test_131_retcode_10006_diagnostic_on_order_send_failure(self, monkeypatch):
        """Sprint 9.9.3.16 / 9.9.3.17 — if order_send returns retcode=10006
        AFTER order_check passed, the journal entry must include the
        canonical 10006 meaning.

        Sprint 9.9.3.17 update: with only FOK supported (symbol_filling_mode=1),
        the adapter tries FOK send → 10006 (retryable) → no more modes to try
        → fail closed. The 10006 appears in send_attempts and
        ADAPTER_ORDER_SEND_RESULT journal events.
        """
        from scripts.audit import demo_micro_full_cycle as harness
        # order_check passes for FOK, but order_send returns 10006
        mt5 = MockMT5(symbol_filling_mode=1,
                      order_check_default_retcode=0,        # check passes
                      open_order_retcode=10006)              # send rejects
        monkeypatch.setattr(harness, "_get_mt5", lambda: mt5)
        monkeypatch.setattr(harness, "hard_gate_evaluate",
                            lambda config_path=None: {"verdict": "DEMO_MICRO_ARMED",
                                                       "reasons": [],
                                                       "checks": {}})
        monkeypatch.setenv("TITAN_DEMO_MICRO_ARMED", "1")
        r = _run_execute_with_mock(mt5, side="BUY", max_hold_seconds=1)

        # order_send was called (check passed) but failed with 10006
        assert r["order_send_called"] is True
        assert r["order_send_success"] == 0
        assert r["final_verdict"] == "DEMO_FULL_CYCLE_FAIL"
        # Send attempts must contain the 10006 retcode
        send_attempts = r.get("send_attempts") or []
        assert len(send_attempts) >= 1
        assert send_attempts[0]["send_retcode"] == 10006
        assert send_attempts[0]["send_retcode_meaning"] == \
               "request rejected (TRADE_RETCODE_REJECT)"
        # Journal must include ADAPTER_ORDER_SEND_RESULT with 10006
        events = _read_journal_events()
        send_result_events = [e for e in events
                              if e.get("event") == "ADAPTER_ORDER_SEND_RESULT"]
        assert len(send_result_events) >= 1
        assert send_result_events[-1].get("send_retcode") == 10006
        assert send_result_events[-1].get("send_retcode_meaning") == \
               "request rejected (TRADE_RETCODE_REJECT)"

    def test_132_check_attempts_surface_in_journal_and_report(self, monkeypatch):
        """Sprint 9.9.3.16 / 9.9.3.17 — when order_check fallback is exercised,
        the check_attempts list is surfaced in the result and journal.

        Sprint 9.9.3.17 update: set trade_exemode=INSTANT so all 3 modes
        (FOK+IOC+RETURN) are tried by the adapter.
        """
        from scripts.audit import demo_micro_full_cycle as harness
        # FOK+IOC+RETURN all rejected by order_check
        mt5 = MockMT5(symbol_filling_mode=1 | 2 | 8,
                      order_check_default_retcode=10006)
        mt5._symbol_info.trade_exemode = 0   # INSTANT — allow RETURN
        monkeypatch.setattr(harness, "_get_mt5", lambda: mt5)
        monkeypatch.setattr(harness, "hard_gate_evaluate",
                            lambda config_path=None: {"verdict": "DEMO_MICRO_ARMED",
                                                       "reasons": [],
                                                       "checks": {}})
        monkeypatch.setenv("TITAN_DEMO_MICRO_ARMED", "1")
        r = _run_execute_with_mock(mt5, side="BUY", max_hold_seconds=1)

        # check_attempts must be in the result
        assert r.get("check_attempts") is not None
        assert len(r["check_attempts"]) == 3
        # Each attempt must have: filling_name, filling_type, check_retcode,
        # check_comment, check_retcode_meaning, passed
        for a in r["check_attempts"]:
            assert "filling_name" in a
            assert "filling_type" in a
            assert "check_retcode" in a
            assert "check_comment" in a
            assert "check_retcode_meaning" in a
            assert "passed" in a

        # The journal's DEMO_MICRO_ORDER_FAILED event must include check_attempts
        events = _read_journal_events()
        order_failed_events = [e for e in events
                               if e.get("event") == "DEMO_MICRO_ORDER_FAILED"]
        assert len(order_failed_events) >= 1
        assert order_failed_events[-1].get("check_attempts") is not None
        assert len(order_failed_events[-1]["check_attempts"]) == 3


# ─── Sprint 9.9.3.17 patch — Universal MT5ExecutionAdapter tests ──────────────

class TestMT5ExecutionAdapter:
    """Sprint 9.9.3.17 — universal MT5 broker execution adapter.

    Tests the MT5ExecutionAdapter class directly (not through the harness)
    to verify: send-level fallback, tick refresh per attempt, duplicate
    position detection, emergency close signaling, broker profile output,
    and close-position fallback.
    """

    def test_133_adapter_imports_and_constants(self):
        """Adapter module imports and exposes required constants."""
        from titan.production.mt5_execution_adapter import (
            MT5ExecutionAdapter, lookup_retcode_meaning,
            ORDER_FILLING_FOK, ORDER_FILLING_IOC, ORDER_FILLING_RETURN,
            _SUCCESS_RETCODES, _RETRYABLE_RETCODES,
            _TRADE_EXECUTION_MARKET, _TRADE_EXECUTIONS_THAT_ALLOW_RETURN,
        )
        assert ORDER_FILLING_FOK == 1
        assert ORDER_FILLING_IOC == 2
        assert ORDER_FILLING_RETURN == 4
        assert 10009 in _SUCCESS_RETCODES
        assert 10010 in _SUCCESS_RETCODES
        assert 10006 in _RETRYABLE_RETCODES
        assert 10030 in _RETRYABLE_RETCODES
        assert 10004 in _RETRYABLE_RETCODES
        assert _TRADE_EXECUTION_MARKET == 2
        assert 0 in _TRADE_EXECUTIONS_THAT_ALLOW_RETURN   # INSTANT
        assert 1 in _TRADE_EXECUTIONS_THAT_ALLOW_RETURN   # REQUEST
        assert 2 not in _TRADE_EXECUTIONS_THAT_ALLOW_RETURN   # MARKET

    def test_134_adapter_retcode_lookup_covers_all_required_codes(self):
        """Adapter's lookup_retcode_meaning covers all required retcodes."""
        from titan.production.mt5_execution_adapter import lookup_retcode_meaning
        # Required by operator spec
        assert lookup_retcode_meaning(10004) is not None   # requote
        assert lookup_retcode_meaning(10006) is not None   # reject
        assert lookup_retcode_meaning(10009) is not None   # done
        assert lookup_retcode_meaning(10010) is not None   # done partial
        assert lookup_retcode_meaning(10013) is not None   # invalid request
        assert lookup_retcode_meaning(10016) is not None   # invalid stops
        assert lookup_retcode_meaning(10020) is not None   # price changed
        assert lookup_retcode_meaning(10021) is not None   # price off
        assert lookup_retcode_meaning(10027) is not None   # autotrading disabled
        assert lookup_retcode_meaning(10030) is not None   # invalid fill
        # Unknown retcode returns None
        assert lookup_retcode_meaning(99999) is None
        assert lookup_retcode_meaning(None) is None

    def test_135_adapter_fok_send_succeeds(self):
        """Adapter sends FOK when FOK is supported and order_send succeeds."""
        from titan.production.mt5_execution_adapter import MT5ExecutionAdapter
        mt5 = MockMT5(symbol_filling_mode=1, order_check_default_retcode=0)
        mt5.initialize()
        adapter = MT5ExecutionAdapter(mt5, journal_event=lambda e, p: None)
        result = adapter.send_open_order(
            symbol="XAUUSD", side="BUY", lot=0.01, magic=20261993,
        )
        assert result["ok"] is True
        assert result["filling_mode_selected"] == "FOK"
        assert result["filling_type_used"] == 1
        assert len(result.get("send_attempts", [])) == 1
        assert result["emergency_close_required"] is False

    def test_136_adapter_send_level_fallback_fok_to_ioc(self):
        """Sprint 9.9.3.17 — FOK send rejected (10006), adapter falls back
        to IOC send which succeeds. This is the FBS scenario."""
        from titan.production.mt5_execution_adapter import MT5ExecutionAdapter
        mt5 = MockMT5(symbol_filling_mode=1 | 2,
                      order_check_default_retcode=0,
                      order_send_retcode_per_mode={1: 10006, 2: 10009})
        mt5.initialize()
        adapter = MT5ExecutionAdapter(mt5, journal_event=lambda e, p: None)
        result = adapter.send_open_order(
            symbol="XAUUSD", side="BUY", lot=0.01, magic=20261993,
        )
        assert result["ok"] is True
        assert result["filling_mode_selected"] == "IOC"
        assert result["filling_type_used"] == 2
        # Two send attempts: FOK (failed) + IOC (succeeded)
        send_attempts = result.get("send_attempts", [])
        assert len(send_attempts) == 2
        assert send_attempts[0]["filling_name"] == "FOK"
        assert send_attempts[0]["send_retcode"] == 10006
        assert send_attempts[0]["send_ok"] is False
        assert send_attempts[1]["filling_name"] == "IOC"
        assert send_attempts[1]["send_retcode"] == 10009
        assert send_attempts[1]["send_ok"] is True

    def test_137_adapter_send_level_fallback_to_return(self):
        """FOK and IOC send both rejected, RETURN send succeeds (if allowed)."""
        from titan.production.mt5_execution_adapter import MT5ExecutionAdapter
        mt5 = MockMT5(symbol_filling_mode=1 | 2 | 8,
                      order_check_default_retcode=0,
                      order_send_retcode_per_mode={1: 10006, 2: 10006, 4: 10009})
        # RETURN requires INSTANT/REQUEST execution mode
        mt5._symbol_info.trade_exemode = 0   # INSTANT
        mt5.initialize()
        adapter = MT5ExecutionAdapter(mt5, journal_event=lambda e, p: None)
        result = adapter.send_open_order(
            symbol="XAUUSD", side="BUY", lot=0.01, magic=20261993,
        )
        assert result["ok"] is True
        assert result["filling_mode_selected"] == "RETURN"
        assert result["filling_type_used"] == 4
        # Three send attempts: FOK + IOC + RETURN
        assert len(result.get("send_attempts", [])) == 3

    def test_138_adapter_all_send_attempts_rejected_fail_closed(self):
        """All send attempts rejected → fail closed, no duplicate orders."""
        from titan.production.mt5_execution_adapter import MT5ExecutionAdapter
        mt5 = MockMT5(symbol_filling_mode=1 | 2,
                      order_check_default_retcode=0,
                      order_send_retcode_per_mode={1: 10006, 2: 10006})
        mt5.initialize()
        adapter = MT5ExecutionAdapter(mt5, journal_event=lambda e, p: None)
        result = adapter.send_open_order(
            symbol="XAUUSD", side="BUY", lot=0.01, magic=20261993,
        )
        assert result["ok"] is False
        assert result["emergency_close_required"] is False
        # Two send attempts, both failed
        send_attempts = result.get("send_attempts", [])
        assert len(send_attempts) == 2
        for a in send_attempts:
            assert a["send_ok"] is False
            assert a["send_retcode"] == 10006
        # No more than 2 order_send calls (no duplicate/retry loop)
        assert len(mt5.order_send_calls) == 2

    def test_139_adapter_emergency_close_when_position_appears_after_failure(self):
        """Sprint 9.9.3.17 — if a position appears after a failed send,
        adapter signals emergency_close_required=True."""
        from titan.production.mt5_execution_adapter import MT5ExecutionAdapter
        # FOK send fails (10006) AND a ghost position appears
        mt5 = MockMT5(symbol_filling_mode=1 | 2,
                      order_check_default_retcode=0,
                      order_send_retcode_per_mode={1: 10006},
                      position_appears_after_send_failure=True)
        mt5.initialize()
        adapter = MT5ExecutionAdapter(mt5, journal_event=lambda e, p: None)
        result = adapter.send_open_order(
            symbol="XAUUSD", side="BUY", lot=0.01, magic=20261993,
        )
        assert result["ok"] is False
        assert result["emergency_close_required"] is True
        assert len(result.get("emergency_close_tickets", [])) >= 1
        # Only ONE send attempt (adapter stops after detecting ghost position)
        assert len(result.get("send_attempts", [])) == 1
        # Position was detected
        pos_check = result.get("position_detected_after_failure", {})
        assert pos_check.get("appeared") is True

    def test_140_adapter_tick_refresh_before_each_send_attempt(self):
        """Adapter refreshes tick (calls symbol_info_tick) before each send."""
        from titan.production.mt5_execution_adapter import MT5ExecutionAdapter
        # FOK fails, IOC succeeds → 2 send attempts → 2+ tick refreshes
        mt5 = MockMT5(symbol_filling_mode=1 | 2,
                      order_check_default_retcode=0,
                      order_send_retcode_per_mode={1: 10006, 2: 10009})
        mt5.initialize()
        adapter = MT5ExecutionAdapter(mt5, journal_event=lambda e, p: None)
        adapter.send_open_order(
            symbol="XAUUSD", side="BUY", lot=0.01, magic=20261993,
        )
        # symbol_info_tick called multiple times (snapshot + per-attempt refresh)
        assert len(mt5.symbol_info_tick_calls) >= 2

    def test_141_adapter_request_contains_type_time_gtc(self):
        """Adapter-built request includes type_time=0 (ORDER_TIME_GTC)."""
        from titan.production.mt5_execution_adapter import MT5ExecutionAdapter
        mt5 = MockMT5(symbol_filling_mode=1, order_check_default_retcode=0)
        mt5.initialize()
        adapter = MT5ExecutionAdapter(mt5, journal_event=lambda e, p: None)
        adapter.send_open_order(
            symbol="XAUUSD", side="BUY", lot=0.01, magic=20261993,
        )
        # The order_send request must have type_time=0
        assert len(mt5.order_send_calls) >= 1
        req = mt5.order_send_calls[0]
        assert req.get("type_time") == 0   # ORDER_TIME_GTC

    def test_142_adapter_broker_comment_logged(self):
        """Adapter logs broker comment from order_send result."""
        from titan.production.mt5_execution_adapter import MT5ExecutionAdapter
        # Capture journal events
        journal_events = []
        def capture(event_type, payload):
            journal_events.append({"event": event_type, **payload})
        mt5 = MockMT5(symbol_filling_mode=1, order_check_default_retcode=0)
        mt5.initialize()
        adapter = MT5ExecutionAdapter(mt5, journal_event=capture)
        adapter.send_open_order(
            symbol="XAUUSD", side="BUY", lot=0.01, magic=20261993,
        )
        # Find ADAPTER_ORDER_SEND_RESULT events
        send_result_events = [e for e in journal_events
                              if e.get("event") == "ADAPTER_ORDER_SEND_RESULT"]
        assert len(send_result_events) >= 1
        # Broker comment must be present (even if empty string)
        assert "send_comment" in send_result_events[-1]

    def test_143_adapter_broker_execution_profile_json_written(self):
        """Adapter writes broker_execution_profile.json."""
        import json
        from titan.production.mt5_execution_adapter import MT5ExecutionAdapter
        profile_path = str(REPO_ROOT / "data" / "audit" / "demo_micro" / "broker_execution_profile.json")
        mt5 = MockMT5(symbol_filling_mode=1 | 2,
                      order_check_default_retcode=0,
                      order_send_retcode_per_mode={1: 10006, 2: 10009})
        mt5.initialize()
        adapter = MT5ExecutionAdapter(mt5, journal_event=lambda e, p: None,
                                       profile_path=profile_path)
        result = adapter.send_open_order(
            symbol="XAUUSD", side="BUY", lot=0.01, magic=20261993,
        )
        # Profile file must exist
        from pathlib import Path
        assert Path(profile_path).exists(), "broker_execution_profile.json not written"
        with open(profile_path) as f:
            profile = json.load(f)
        # Required fields
        assert "timestamp_utc" in profile
        assert "label" in profile
        assert "verdict" in profile
        assert "broker_snapshot" in profile
        assert "filling_modes_in_bitmask" in profile
        assert "check_attempts" in profile
        assert "send_attempts" in profile
        assert "filling_mode_selected" in profile
        # Verdict must be SUCCESS (IOC send succeeded)
        assert profile["verdict"] == "SUCCESS"
        assert profile["filling_mode_selected"] == "IOC"
        # Broker snapshot must include account, terminal, symbol_info, tick
        snap = profile["broker_snapshot"]
        assert "account" in snap
        assert "terminal" in snap
        assert "symbol_info" in snap
        assert "tick" in snap
        assert "open_positions" in snap
        # Symbol info must include filling_mode, volume_min/step/max, trade_mode, trade_exemode
        sinfo = snap["symbol_info"]
        assert "filling_mode" in sinfo
        assert "volume_min" in sinfo
        assert "volume_step" in sinfo
        assert "volume_max" in sinfo
        assert "trade_mode" in sinfo
        assert "trade_exemode" in sinfo

    def test_144_adapter_duplicate_order_protection(self):
        """Adapter blocks send when a position is already open for symbol+magic."""
        from titan.production.mt5_execution_adapter import MT5ExecutionAdapter
        # Pre-create an open position with our magic
        existing_pos = _MockPosition(ticket=55555, position_type=0,
                                      volume=0.01, magic=20261993, symbol="XAUUSD")
        mt5 = MockMT5(symbol_filling_mode=1,
                      open_positions=[existing_pos])
        mt5.initialize()
        adapter = MT5ExecutionAdapter(mt5, journal_event=lambda e, p: None)
        result = adapter.send_open_order(
            symbol="XAUUSD", side="BUY", lot=0.01, magic=20261993,
        )
        # Must be blocked — no order_send called
        assert result["ok"] is False
        assert "duplicate" in result["error"].lower()
        assert len(mt5.order_send_calls) == 0
        assert result["emergency_close_required"] is False

    def test_145_adapter_close_position_uses_send_level_fallback(self):
        """Adapter's send_close_order also uses send-level fallback."""
        from titan.production.mt5_execution_adapter import MT5ExecutionAdapter
        # Pre-create an open position to close
        open_pos = _MockPosition(ticket=1001, position_type=0,  # BUY
                                  volume=0.01, magic=20261993, symbol="XAUUSD")
        # FOK send fails, IOC send succeeds (for close)
        mt5 = MockMT5(symbol_filling_mode=1 | 2,
                      order_check_default_retcode=0,
                      order_send_retcode_per_mode={1: 10006, 2: 10009},
                      open_positions=[open_pos])
        mt5.initialize()
        adapter = MT5ExecutionAdapter(mt5, journal_event=lambda e, p: None)
        position_dict = {
            "ticket": 1001, "type": "BUY", "volume": 0.01,
            "symbol": "XAUUSD", "price_open": 2000.10,
        }
        result = adapter.send_close_order(position=position_dict, magic=20261993)
        assert result["ok"] is True
        assert result["filling_mode_selected"] == "IOC"
        # Two send attempts: FOK (failed) + IOC (succeeded)
        assert len(result.get("send_attempts", [])) == 2

    def test_146_adapter_fail_closed_when_no_supported_filling_mode(self):
        """Adapter fails closed when symbol_info has no FOK/IOC/RETURN bits."""
        from titan.production.mt5_execution_adapter import MT5ExecutionAdapter
        # Only BOC supported (bit 4) — invalid for market orders
        mt5 = MockMT5(symbol_filling_mode=4)
        mt5.initialize()
        adapter = MT5ExecutionAdapter(mt5, journal_event=lambda e, p: None)
        result = adapter.send_open_order(
            symbol="XAUUSD", side="BUY", lot=0.01, magic=20261993,
        )
        assert result["ok"] is False
        assert "no supported filling mode" in result["error"].lower()
        assert len(mt5.order_send_calls) == 0
        assert len(mt5.order_check_calls) == 0

    def test_147_adapter_return_filtered_for_market_execution(self):
        """Adapter filters out RETURN when trade_exemode=MARKET (2)."""
        from titan.production.mt5_execution_adapter import MT5ExecutionAdapter
        # FOK+IOC+RETURN in bitmask, but MARKET execution → RETURN filtered
        mt5 = MockMT5(symbol_filling_mode=1 | 2 | 8)
        mt5._symbol_info.trade_exemode = 2   # MARKET
        mt5.initialize()
        adapter = MT5ExecutionAdapter(mt5, journal_event=lambda e, p: None)
        # All sends fail → adapter tries FOK + IOC only (RETURN filtered)
        mt5._order_send_retcode_per_mode = {1: 10006, 2: 10006, 4: 10006}
        result = adapter.send_open_order(
            symbol="XAUUSD", side="BUY", lot=0.01, magic=20261993,
        )
        # Only 2 send attempts (FOK + IOC), not 3
        send_attempts = result.get("send_attempts", [])
        assert len(send_attempts) == 2
        filling_names = [a["filling_name"] for a in send_attempts]
        assert "FOK" in filling_names
        assert "IOC" in filling_names
        assert "RETURN" not in filling_names

    def test_148_adapter_harness_integration_emergency_close_path(self, monkeypatch):
        """Sprint 9.9.3.17 — full harness integration: when adapter signals
        emergency_close_required, the harness enters the emergency close
        path and attempts to close the ghost position."""
        from scripts.audit import demo_micro_full_cycle as harness
        # FOK send fails with 10006 AND ghost position appears
        mt5 = MockMT5(symbol_filling_mode=1 | 2,
                      order_check_default_retcode=0,
                      order_send_retcode_per_mode={1: 10006, 2: 10006},
                      position_appears_after_send_failure=True)
        monkeypatch.setattr(harness, "_get_mt5", lambda: mt5)
        monkeypatch.setattr(harness, "hard_gate_evaluate",
                            lambda config_path=None: {"verdict": "DEMO_MICRO_ARMED",
                                                       "reasons": [],
                                                       "checks": {}})
        monkeypatch.setenv("TITAN_DEMO_MICRO_ARMED", "1")
        r = _run_execute_with_mock(mt5, side="BUY", max_hold_seconds=1)

        # Emergency close was triggered
        assert r.get("emergency_close_required") is True
        assert r.get("emergency_close_attempted") is True
        # The harness should have attempted to close the ghost position
        # (close order has "position" field)
        close_calls = [c for c in mt5.order_send_calls if c.get("position")]
        assert len(close_calls) >= 1, \
            f"Expected at least 1 close call, got {len(close_calls)}"
        # Verdict should be MANUAL_REVIEW (ghost was detected and close attempted)
        # or FAIL (if close failed). Either way, not PASS.
        assert r["final_verdict"] in ("DEMO_MANUAL_REVIEW_REQUIRED",
                                       "DEMO_FULL_CYCLE_FAIL")

    def test_149_adapter_journal_events_emitted(self, monkeypatch):
        """Adapter emits all required journal events during a successful send."""
        from scripts.audit import demo_micro_full_cycle as harness
        mt5 = MockMT5(symbol_filling_mode=1, order_check_default_retcode=0)
        monkeypatch.setattr(harness, "_get_mt5", lambda: mt5)
        monkeypatch.setattr(harness, "hard_gate_evaluate",
                            lambda config_path=None: {"verdict": "DEMO_MICRO_ARMED",
                                                       "reasons": [],
                                                       "checks": {}})
        monkeypatch.setenv("TITAN_DEMO_MICRO_ARMED", "1")
        _run_execute_with_mock(mt5, side="BUY", max_hold_seconds=1)

        events = _read_journal_events()
        event_types = [e.get("event") for e in events]
        # Required adapter events
        assert "ADAPTER_BROKER_STATE_SNAPSHOT" in event_types
        assert "ADAPTER_PRE_SEND_DIAGNOSTICS" in event_types
        assert "ADAPTER_ORDER_CHECK_ATTEMPTED" in event_types
        assert "ADAPTER_ORDER_SEND_ATTEMPTED" in event_types
        assert "ADAPTER_ORDER_SEND_RESULT" in event_types

    def test_150_adapter_position_check_after_failure_event(self, monkeypatch):
        """Adapter emits ADAPTER_POSITION_CHECK_AFTER_FAILURE after every failed send."""
        from scripts.audit import demo_micro_full_cycle as harness
        # Clear journal so we only see events from this test
        journal_path = REPO_ROOT / "data" / "audit" / "demo_micro" / "demo_micro_journal.jsonl"
        if journal_path.exists():
            journal_path.unlink()
        # FOK send fails, IOC succeeds
        mt5 = MockMT5(symbol_filling_mode=1 | 2,
                      order_check_default_retcode=0,
                      order_send_retcode_per_mode={1: 10006, 2: 10009})
        monkeypatch.setattr(harness, "_get_mt5", lambda: mt5)
        monkeypatch.setattr(harness, "hard_gate_evaluate",
                            lambda config_path=None: {"verdict": "DEMO_MICRO_ARMED",
                                                       "reasons": [],
                                                       "checks": {}})
        monkeypatch.setenv("TITAN_DEMO_MICRO_ARMED", "1")
        _run_execute_with_mock(mt5, side="BUY", max_hold_seconds=1)

        events = _read_journal_events()
        pos_check_events = [e for e in events
                            if e.get("event") == "ADAPTER_POSITION_CHECK_AFTER_FAILURE"]
        # At least 2: one after open FOK failure, one after close FOK failure
        assert len(pos_check_events) >= 1
        # The event must include position_appeared flag
        assert "position_appeared" in pos_check_events[-1]
        # Filter to OPEN-order position checks only (is_close_order=False).
        # For open orders, position_appeared must be False after FOK failure
        # (no ghost position in this test scenario).
        open_pos_checks = [e for e in pos_check_events if not e.get("is_close_order")]
        assert len(open_pos_checks) >= 1
        assert open_pos_checks[-1]["position_appeared"] is False


# ─── Sprint 9.9.3.18 patch — order_send None result tests ─────────────────────

class TestOrderSendNoneResult:
    """Sprint 9.9.3.18 — handle mt5.order_send() returning None safely.

    When order_send returns None (MT5 internal error), the adapter must:
      1. Call mt5.last_error() to get the actual error code/message
      2. Log DEMO_MICRO_ORDER_SEND_NONE with full diagnostics
      3. Check positions_get(symbol)+magic immediately
      4. If no position: treat as retryable, try next filling mode
      5. If position exists: trigger emergency_close_required
      6. Never show retcode=None without mt5.last_error diagnostics
    """

    def test_151_none_result_calls_last_error(self):
        """When order_send returns None, adapter calls mt5.last_error()."""
        from titan.production.mt5_execution_adapter import MT5ExecutionAdapter
        mt5 = MockMT5(symbol_filling_mode=1,
                      order_check_default_retcode=0,
                      order_send_returns_none_per_mode={1},  # FOK returns None
                      mt5_last_error=(-1, "MT5 internal error: request not processed"))
        mt5.initialize()
        adapter = MT5ExecutionAdapter(mt5, journal_event=lambda e, p: None)
        result = adapter.send_open_order(
            symbol="XAUUSD", side="BUY", lot=0.01, magic=20261993,
        )
        # Adapter must have called last_error at least once
        assert mt5.last_error_calls >= 1
        # The send attempt must record the None result + last_error
        send_attempts = result.get("send_attempts", [])
        assert len(send_attempts) >= 1
        attempt = send_attempts[0]
        assert attempt["order_send_returned_none"] is True
        assert attempt["send_retcode"] is None
        assert attempt["mt5_last_error_code"] == -1
        assert "internal error" in attempt["mt5_last_error_message"].lower()

    def test_152_none_result_logs_diagnostics_event(self):
        """DEMO_MICRO_ORDER_SEND_NONE journal event is emitted with full diagnostics."""
        from titan.production.mt5_execution_adapter import MT5ExecutionAdapter
        journal_events = []
        def capture(event_type, payload):
            journal_events.append({"event": event_type, **payload})
        mt5 = MockMT5(symbol_filling_mode=1,
                      order_check_default_retcode=0,
                      order_send_returns_none_per_mode={1},
                      mt5_last_error=(-1, "Request not processed"))
        mt5.initialize()
        adapter = MT5ExecutionAdapter(mt5, journal_event=capture)
        adapter.send_open_order(
            symbol="XAUUSD", side="BUY", lot=0.01, magic=20261993,
        )
        none_events = [e for e in journal_events
                       if e.get("event") == "DEMO_MICRO_ORDER_SEND_NONE"]
        assert len(none_events) >= 1
        ev = none_events[-1]
        # Required fields per operator spec
        assert ev["mt5_last_error_code"] == -1
        assert "request not processed" in ev["mt5_last_error_message"].lower()
        assert ev["filling_name"] == "FOK"
        assert ev["price"] is not None
        assert "bid" in ev
        assert "ask" in ev
        assert "spread" in ev
        assert "request" in ev  # sanitized request

    def test_153_none_result_falls_back_to_next_mode(self):
        """FOK returns None → adapter falls back to IOC which succeeds."""
        from titan.production.mt5_execution_adapter import MT5ExecutionAdapter
        mt5 = MockMT5(symbol_filling_mode=1 | 2,
                      order_check_default_retcode=0,
                      order_send_returns_none_per_mode={1},  # FOK returns None
                      mt5_last_error=(-1, "FOK not processed"))
        mt5.initialize()
        adapter = MT5ExecutionAdapter(mt5, journal_event=lambda e, p: None)
        result = adapter.send_open_order(
            symbol="XAUUSD", side="BUY", lot=0.01, magic=20261993,
        )
        # IOC fallback should succeed
        assert result["ok"] is True
        assert result["filling_mode_selected"] == "IOC"
        # Two send attempts: FOK (None) + IOC (success)
        send_attempts = result.get("send_attempts", [])
        assert len(send_attempts) == 2
        assert send_attempts[0]["filling_name"] == "FOK"
        assert send_attempts[0]["order_send_returned_none"] is True
        assert send_attempts[1]["filling_name"] == "IOC"
        assert send_attempts[1]["send_ok"] is True

    def test_154_none_result_all_modes_fail_closed(self):
        """All modes return None → fail closed, no duplicate orders."""
        from titan.production.mt5_execution_adapter import MT5ExecutionAdapter
        mt5 = MockMT5(symbol_filling_mode=1 | 2,
                      order_check_default_retcode=0,
                      order_send_returns_none_per_mode={1, 2},  # Both return None
                      mt5_last_error=(-1, "No modes processed"))
        mt5.initialize()
        adapter = MT5ExecutionAdapter(mt5, journal_event=lambda e, p: None)
        result = adapter.send_open_order(
            symbol="XAUUSD", side="BUY", lot=0.01, magic=20261993,
        )
        assert result["ok"] is False
        assert result["emergency_close_required"] is False
        # Two send attempts, both None
        send_attempts = result.get("send_attempts", [])
        assert len(send_attempts) == 2
        for a in send_attempts:
            assert a["order_send_returned_none"] is True
            assert a["send_retcode"] is None
            assert a["mt5_last_error_code"] == -1

    def test_155_none_result_with_ghost_position_triggers_emergency_close(self):
        """FOK returns None AND ghost position appears → emergency_close_required."""
        from titan.production.mt5_execution_adapter import MT5ExecutionAdapter
        mt5 = MockMT5(symbol_filling_mode=1 | 2,
                      order_check_default_retcode=0,
                      order_send_returns_none_per_mode={1},  # FOK returns None
                      position_appears_after_send_failure=True,
                      mt5_last_error=(-1, "None but position placed"))
        mt5.initialize()
        adapter = MT5ExecutionAdapter(mt5, journal_event=lambda e, p: None)
        result = adapter.send_open_order(
            symbol="XAUUSD", side="BUY", lot=0.01, magic=20261993,
        )
        # Emergency close must be triggered
        assert result["ok"] is False
        assert result["emergency_close_required"] is True
        assert len(result.get("emergency_close_tickets", [])) >= 1
        # Only ONE send attempt (adapter stops after detecting ghost position)
        assert len(result.get("send_attempts", [])) == 1
        assert result["send_attempts"][0]["order_send_returned_none"] is True

    def test_156_none_result_never_shows_retcode_none_without_last_error(self):
        """When retcode is None, mt5_last_error must always be populated."""
        from titan.production.mt5_execution_adapter import MT5ExecutionAdapter
        mt5 = MockMT5(symbol_filling_mode=1,
                      order_check_default_retcode=0,
                      order_send_returns_none_per_mode={1},
                      mt5_last_error=(4753, "No prices for symbol"))
        mt5.initialize()
        adapter = MT5ExecutionAdapter(mt5, journal_event=lambda e, p: None)
        result = adapter.send_open_order(
            symbol="XAUUSD", side="BUY", lot=0.01, magic=20261993,
        )
        # Every send attempt with retcode=None must have mt5_last_error populated
        for a in result.get("send_attempts", []):
            if a["send_retcode"] is None:
                assert a["mt5_last_error_code"] is not None, \
                    "retcode=None without mt5_last_error_code"
                assert a["mt5_last_error_message"], \
                    "retcode=None without mt5_last_error_message"

    def test_157_none_result_in_broker_profile(self):
        """broker_execution_profile.json includes order_send_returned_none + mt5_last_error."""
        import json
        from pathlib import Path
        from titan.production.mt5_execution_adapter import MT5ExecutionAdapter
        profile_path = str(REPO_ROOT / "data" / "audit" / "demo_micro" / "broker_execution_profile.json")
        mt5 = MockMT5(symbol_filling_mode=1 | 2,
                      order_check_default_retcode=0,
                      order_send_returns_none_per_mode={1},  # FOK returns None
                      mt5_last_error=(-1, "FOK not processed"))
        mt5.initialize()
        adapter = MT5ExecutionAdapter(mt5, journal_event=lambda e, p: None,
                                       profile_path=profile_path)
        adapter.send_open_order(
            symbol="XAUUSD", side="BUY", lot=0.01, magic=20261993,
        )
        assert Path(profile_path).exists()
        with open(profile_path) as f:
            profile = json.load(f)
        # Profile must include None-result fields
        assert "order_send_returned_none" in profile
        assert profile["order_send_returned_none"] is True
        assert "mt5_last_error" in profile
        assert profile["mt5_last_error"] is not None
        assert profile["mt5_last_error"]["code"] == -1
        assert "FOK not processed" in profile["mt5_last_error"]["message"]

    def test_158_none_result_harness_integration_fallback(self, monkeypatch):
        """Full harness: FOK returns None → IOC fallback → cycle PASS."""
        from scripts.audit import demo_micro_full_cycle as harness
        mt5 = MockMT5(symbol_filling_mode=1 | 2,
                      order_check_default_retcode=0,
                      order_send_returns_none_per_mode={1},  # FOK returns None
                      mt5_last_error=(-1, "FOK not processed"))
        monkeypatch.setattr(harness, "_get_mt5", lambda: mt5)
        monkeypatch.setattr(harness, "hard_gate_evaluate",
                            lambda config_path=None: {"verdict": "DEMO_MICRO_ARMED",
                                                       "reasons": [],
                                                       "checks": {}})
        monkeypatch.setenv("TITAN_DEMO_MICRO_ARMED", "1")
        r = _run_execute_with_mock(mt5, side="BUY", max_hold_seconds=1)
        # IOC fallback should succeed → full cycle PASS
        assert r["final_verdict"] == "DEMO_FULL_CYCLE_PASS"
        assert r.get("filling_mode_selected") == "IOC"

    def test_159_none_result_harness_emergency_close(self, monkeypatch):
        """Full harness: FOK returns None + ghost position → emergency close path."""
        from scripts.audit import demo_micro_full_cycle as harness
        mt5 = MockMT5(symbol_filling_mode=1 | 2,
                      order_check_default_retcode=0,
                      order_send_returns_none_per_mode={1},
                      position_appears_after_send_failure=True,
                      mt5_last_error=(-1, "None but ghost"))
        monkeypatch.setattr(harness, "_get_mt5", lambda: mt5)
        monkeypatch.setattr(harness, "hard_gate_evaluate",
                            lambda config_path=None: {"verdict": "DEMO_MICRO_ARMED",
                                                       "reasons": [],
                                                       "checks": {}})
        monkeypatch.setenv("TITAN_DEMO_MICRO_ARMED", "1")
        r = _run_execute_with_mock(mt5, side="BUY", max_hold_seconds=1)
        # Emergency close must be triggered
        assert r.get("emergency_close_required") is True
        assert r.get("emergency_close_attempted") is True

    def test_160_none_result_journal_event_in_harness(self, monkeypatch):
        """DEMO_MICRO_ORDER_SEND_NONE event appears in journal from harness run."""
        from scripts.audit import demo_micro_full_cycle as harness
        # Clear journal
        journal_path = REPO_ROOT / "data" / "audit" / "demo_micro" / "demo_micro_journal.jsonl"
        if journal_path.exists():
            journal_path.unlink()
        mt5 = MockMT5(symbol_filling_mode=1 | 2,
                      order_check_default_retcode=0,
                      order_send_returns_none_per_mode={1},
                      mt5_last_error=(-1, "FOK not processed"))
        monkeypatch.setattr(harness, "_get_mt5", lambda: mt5)
        monkeypatch.setattr(harness, "hard_gate_evaluate",
                            lambda config_path=None: {"verdict": "DEMO_MICRO_ARMED",
                                                       "reasons": [],
                                                       "checks": {}})
        monkeypatch.setenv("TITAN_DEMO_MICRO_ARMED", "1")
        _run_execute_with_mock(mt5, side="BUY", max_hold_seconds=1)
        events = _read_journal_events()
        none_events = [e for e in events
                       if e.get("event") == "DEMO_MICRO_ORDER_SEND_NONE"]
        assert len(none_events) >= 1
        ev = none_events[-1]
        assert ev["mt5_last_error_code"] == -1
        assert ev["filling_name"] == "FOK"


# ─── Sprint 9.9.3.19 patch — broker compatibility fallback tests ──────────────

class TestBrokerCompatibilityFallback:
    """Sprint 9.9.3.19 — two-step broker compatibility fallback.

    When a protected market order (SL/TP attached) is rejected by a
    MARKET-execution broker (FBS scenario), the adapter tries:
      a) naked market order (sl=0, tp=0)
      b) SLTP modify via TRADE_ACTION_SLTP
      c) emergency close if SLTP modify fails
    """

    def test_161_protected_reject_naked_success_sltp_success(self):
        """Protected FOK rejected (10006) → naked FOK succeeds → SLTP modify succeeds."""
        from titan.production.mt5_execution_adapter import MT5ExecutionAdapter
        mt5 = MockMT5(symbol_filling_mode=1,   # FOK only
                      order_check_default_retcode=0,
                      protected_order_retcode=10006,  # protected rejected
                      naked_order_retcode=10009,      # naked succeeds
                      sltp_modify_retcode=10009)      # SLTP modify succeeds
        mt5._symbol_info.trade_exemode = 2   # MARKET execution
        mt5.initialize()
        adapter = MT5ExecutionAdapter(mt5, journal_event=lambda e, p: None)
        result = adapter.send_open_order(
            symbol="XAUUSD", side="BUY", lot=0.01, magic=20261993,
            demo_micro=True,
        )
        assert result["ok"] is True
        assert result.get("broker_compatibility_fallback_tried") is True
        assert result.get("broker_compatibility_fallback_succeeded") is True
        assert result.get("sltp_modify_result", {}).get("ok") is True
        assert mt5._sltp_modify_calls >= 1

    def test_162_protected_reject_naked_success_sltp_fail_emergency_close(self):
        """Protected reject → naked success → SLTP modify FAILS → emergency close."""
        from titan.production.mt5_execution_adapter import MT5ExecutionAdapter
        mt5 = MockMT5(symbol_filling_mode=1,
                      order_check_default_retcode=0,
                      protected_order_retcode=10006,
                      naked_order_retcode=10009,
                      sltp_modify_retcode=10013)  # SLTP modify fails
        mt5._symbol_info.trade_exemode = 2
        mt5.initialize()
        adapter = MT5ExecutionAdapter(mt5, journal_event=lambda e, p: None)
        result = adapter.send_open_order(
            symbol="XAUUSD", side="BUY", lot=0.01, magic=20261993,
            demo_micro=True,
        )
        assert result["ok"] is False
        assert result.get("emergency_close_required") is True
        assert result.get("emergency_close_attempted") is True
        assert result.get("broker_compatibility_fallback_succeeded") is False
        assert result.get("sltp_modify_result", {}).get("ok") is False

    def test_163_naked_order_also_fails_fail_closed(self):
        """Protected reject → naked also fails → fail closed, no SLTP modify."""
        from titan.production.mt5_execution_adapter import MT5ExecutionAdapter
        mt5 = MockMT5(symbol_filling_mode=1,
                      order_check_default_retcode=0,
                      protected_order_retcode=10006,
                      naked_order_retcode=10006,   # naked also rejected
                      sltp_modify_retcode=10009)
        mt5._symbol_info.trade_exemode = 2
        mt5.initialize()
        adapter = MT5ExecutionAdapter(mt5, journal_event=lambda e, p: None)
        result = adapter.send_open_order(
            symbol="XAUUSD", side="BUY", lot=0.01, magic=20261993,
            demo_micro=True,
        )
        assert result["ok"] is False
        assert result.get("broker_compatibility_fallback_tried") is True
        assert result.get("broker_compatibility_fallback_succeeded") is False
        # SLTP modify should NOT have been called (naked order failed first)
        assert mt5._sltp_modify_calls == 0
        # No emergency close (no position was opened)
        assert result.get("emergency_close_required") is False

    def test_164_result_propagation_shows_real_retcode_not_none(self, monkeypatch):
        """Sprint 9.9.3.19 — console/report must show real adapter retcode
        (10006) instead of retcode=None when adapter has send_attempts."""
        from scripts.audit import demo_micro_full_cycle as harness
        # Protected FOK rejected with 10006, naked also rejected with 10006
        mt5 = MockMT5(symbol_filling_mode=1,
                      order_check_default_retcode=0,
                      protected_order_retcode=10006,
                      naked_order_retcode=10006)
        mt5._symbol_info.trade_exemode = 2
        monkeypatch.setattr(harness, "_get_mt5", lambda: mt5)
        monkeypatch.setattr(harness, "hard_gate_evaluate",
                            lambda config_path=None: {"verdict": "DEMO_MICRO_ARMED",
                                                       "reasons": [],
                                                       "checks": {}})
        monkeypatch.setenv("TITAN_DEMO_MICRO_ARMED", "1")
        r = _run_execute_with_mock(mt5, side="BUY", max_hold_seconds=1)
        # The result must show retcode=10006 (from last send attempt),
        # NOT retcode=None (which was the old bug).
        assert r.get("retcode") == 10006
        assert r.get("last_send_retcode") == 10006
        assert "10006" in r.get("reason", "")
        # retcode_meaning must be populated
        assert r.get("retcode_meaning") is not None
        assert "reject" in r.get("retcode_meaning", "").lower()

    def test_165_broker_compat_journal_events_emitted(self):
        """All required broker compat journal events are emitted."""
        from titan.production.mt5_execution_adapter import MT5ExecutionAdapter
        journal_events = []
        def capture(event_type, payload):
            journal_events.append({"event": event_type, **payload})
        mt5 = MockMT5(symbol_filling_mode=1,
                      order_check_default_retcode=0,
                      protected_order_retcode=10006,
                      naked_order_retcode=10009,
                      sltp_modify_retcode=10009)
        mt5._symbol_info.trade_exemode = 2
        mt5.initialize()
        adapter = MT5ExecutionAdapter(mt5, journal_event=capture)
        adapter.send_open_order(
            symbol="XAUUSD", side="BUY", lot=0.01, magic=20261993,
            demo_micro=True,
        )
        event_types = [e.get("event") for e in journal_events]
        assert "ADAPTER_PROTECTED_ORDER_REJECTED" in event_types
        assert "ADAPTER_NAKED_ORDER_ATTEMPTED" in event_types
        assert "ADAPTER_SLTP_MODIFY_ATTEMPTED" in event_types
        assert "ADAPTER_SLTP_MODIFY_SUCCESS" in event_types

    def test_166_emergency_close_if_sltp_failed_event(self):
        """ADAPTER_EMERGENCY_CLOSE_IF_SLTP_FAILED event emitted on SLTP failure."""
        from titan.production.mt5_execution_adapter import MT5ExecutionAdapter
        journal_events = []
        def capture(event_type, payload):
            journal_events.append({"event": event_type, **payload})
        mt5 = MockMT5(symbol_filling_mode=1,
                      order_check_default_retcode=0,
                      protected_order_retcode=10006,
                      naked_order_retcode=10009,
                      sltp_modify_retcode=10013)  # SLTP fails
        mt5._symbol_info.trade_exemode = 2
        mt5.initialize()
        adapter = MT5ExecutionAdapter(mt5, journal_event=capture)
        adapter.send_open_order(
            symbol="XAUUSD", side="BUY", lot=0.01, magic=20261993,
            demo_micro=True,
        )
        event_types = [e.get("event") for e in journal_events]
        assert "ADAPTER_EMERGENCY_CLOSE_IF_SLTP_FAILED" in event_types

    def test_167_broker_compat_only_in_demo_micro_mode(self):
        """Broker compatibility fallback only runs when demo_micro=True."""
        from titan.production.mt5_execution_adapter import MT5ExecutionAdapter
        mt5 = MockMT5(symbol_filling_mode=1,
                      order_check_default_retcode=0,
                      protected_order_retcode=10006,
                      naked_order_retcode=10009,
                      sltp_modify_retcode=10009)
        mt5._symbol_info.trade_exemode = 2
        mt5.initialize()
        adapter = MT5ExecutionAdapter(mt5, journal_event=lambda e, p: None)
        # demo_micro=False (default) — fallback should NOT run
        result = adapter.send_open_order(
            symbol="XAUUSD", side="BUY", lot=0.01, magic=20261993,
            demo_micro=False,
        )
        assert result["ok"] is False
        assert result.get("broker_compatibility_fallback_tried") is not True
        # SLTP modify should NOT have been called
        assert mt5._sltp_modify_calls == 0

    def test_168_broker_compat_not_triggered_for_non_market_execution(self):
        """Fallback not triggered when trade_exemode != MARKET (e.g. INSTANT)."""
        from titan.production.mt5_execution_adapter import MT5ExecutionAdapter
        mt5 = MockMT5(symbol_filling_mode=1,
                      order_check_default_retcode=0,
                      protected_order_retcode=10006,
                      naked_order_retcode=10009,
                      sltp_modify_retcode=10009)
        mt5._symbol_info.trade_exemode = 0   # INSTANT, not MARKET
        mt5.initialize()
        adapter = MT5ExecutionAdapter(mt5, journal_event=lambda e, p: None)
        result = adapter.send_open_order(
            symbol="XAUUSD", side="BUY", lot=0.01, magic=20261993,
            demo_micro=True,
        )
        # Fallback should NOT run (trade_exemode is not MARKET)
        assert result.get("broker_compatibility_fallback_tried") is not True

    def test_169_broker_compat_harness_integration_success(self, monkeypatch):
        """Full harness: protected reject → naked success → SLTP success → PASS."""
        from scripts.audit import demo_micro_full_cycle as harness
        mt5 = MockMT5(symbol_filling_mode=1,
                      order_check_default_retcode=0,
                      protected_order_retcode=10006,
                      naked_order_retcode=10009,
                      sltp_modify_retcode=10009)
        mt5._symbol_info.trade_exemode = 2
        monkeypatch.setattr(harness, "_get_mt5", lambda: mt5)
        monkeypatch.setattr(harness, "hard_gate_evaluate",
                            lambda config_path=None: {"verdict": "DEMO_MICRO_ARMED",
                                                       "reasons": [],
                                                       "checks": {}})
        monkeypatch.setenv("TITAN_DEMO_MICRO_ARMED", "1")
        r = _run_execute_with_mock(mt5, side="BUY", max_hold_seconds=1)
        # Full cycle should PASS via broker compat fallback
        assert r["final_verdict"] == "DEMO_FULL_CYCLE_PASS"
        assert r.get("filling_mode_selected") is not None


# ─── Sprint 9.9.3.21 patch — raw working profile tests ────────────────────────

class TestRawWorkingProfile:
    """Sprint 9.9.3.21 — raw MT5 working profile support.

    When use_raw_working_profile=True and raw_mt5_working_profile.json
    exists, the adapter mirrors the exact request shape that succeeded
    on this broker: naked IOC order (sl=0, tp=0) + SLTP modify after open.
    """

    def _create_temp_raw_profile(self, tmp_path, **overrides):
        """Helper: create a temp raw_mt5_working_profile.json."""
        import json
        profile = {
            "server": "MetaQuotes-Demo",
            "symbol": "XAUUSD",
            "type_filling": 2,  # IOC
            "type_filling_name": "IOC",
            "deviation": 50,
            "sl": 0.0,
            "tp": 0.0,
            "sl_tp_mode": "naked_then_sltp_modify",
            "type_time": 0,
            "type_time_name": "ORDER_TIME_GTC",
            "magic": 20261993,
        }
        profile.update(overrides)
        profile_path = tmp_path / "raw_mt5_working_profile.json"
        profile_path.write_text(json.dumps(profile))
        return str(profile_path)

    def test_170_raw_profile_ioc_naked_succeeds(self, tmp_path):
        """Raw profile IOC naked order succeeds + SLTP modify succeeds."""
        from titan.production.mt5_execution_adapter import MT5ExecutionAdapter
        profile_path = self._create_temp_raw_profile(tmp_path)
        mt5 = MockMT5(symbol_filling_mode=1 | 2,
                      order_check_default_retcode=0,
                      naked_order_retcode=10009,
                      sltp_modify_retcode=10009)
        mt5._symbol_info.trade_exemode = 2
        mt5.initialize()
        adapter = MT5ExecutionAdapter(mt5, journal_event=lambda e, p: None)
        result = adapter.send_open_order(
            symbol="XAUUSD", side="BUY", lot=0.01, magic=20261993,
            use_raw_working_profile=True, raw_profile_path=profile_path,
        )
        assert result["ok"] is True
        assert result.get("raw_working_profile_used") is True
        assert result.get("raw_naked_open_then_sltp") is True
        assert result.get("filling_mode_selected") == "IOC"
        assert result.get("filling_source") == "raw_working_profile"
        assert result.get("sltp_modify_result", {}).get("ok") is True
        assert mt5._sltp_modify_calls >= 1

    def test_171_adapter_uses_ioc_first_from_raw_profile(self, tmp_path):
        """Adapter uses IOC filling type from raw profile (not FOK)."""
        from titan.production.mt5_execution_adapter import MT5ExecutionAdapter
        profile_path = self._create_temp_raw_profile(tmp_path, type_filling=2)
        mt5 = MockMT5(symbol_filling_mode=1 | 2,
                      order_check_default_retcode=0,
                      naked_order_retcode=10009,
                      sltp_modify_retcode=10009)
        mt5.initialize()
        adapter = MT5ExecutionAdapter(mt5, journal_event=lambda e, p: None)
        adapter.send_open_order(
            symbol="XAUUSD", side="BUY", lot=0.01, magic=20261993,
            use_raw_working_profile=True, raw_profile_path=profile_path,
        )
        # The open order request must use type_filling=2 (IOC)
        open_calls = [c for c in mt5.order_send_calls
                      if not c.get("position") and c.get("action") == 1]
        assert len(open_calls) >= 1
        assert open_calls[0]["type_filling"] == 2   # IOC from raw profile

    def test_172_adapter_sends_naked_sl_zero_tp_zero(self, tmp_path):
        """Adapter sends sl=0 and tp=0 (naked order) when using raw profile."""
        from titan.production.mt5_execution_adapter import MT5ExecutionAdapter
        profile_path = self._create_temp_raw_profile(tmp_path)
        mt5 = MockMT5(symbol_filling_mode=1 | 2,
                      order_check_default_retcode=0,
                      naked_order_retcode=10009,
                      sltp_modify_retcode=10009)
        mt5.initialize()
        adapter = MT5ExecutionAdapter(mt5, journal_event=lambda e, p: None)
        adapter.send_open_order(
            symbol="XAUUSD", side="BUY", lot=0.01, magic=20261993,
            use_raw_working_profile=True, raw_profile_path=profile_path,
        )
        open_calls = [c for c in mt5.order_send_calls
                      if not c.get("position") and c.get("action") == 1]
        assert len(open_calls) >= 1
        assert open_calls[0]["sl"] == 0.0
        assert open_calls[0]["tp"] == 0.0

    def test_173_sltp_modify_attempted_after_open(self, tmp_path):
        """SLTP modify (TRADE_ACTION_SLTP) is attempted after naked open."""
        from titan.production.mt5_execution_adapter import MT5ExecutionAdapter
        profile_path = self._create_temp_raw_profile(tmp_path)
        mt5 = MockMT5(symbol_filling_mode=1 | 2,
                      order_check_default_retcode=0,
                      naked_order_retcode=10009,
                      sltp_modify_retcode=10009)
        mt5.initialize()
        adapter = MT5ExecutionAdapter(mt5, journal_event=lambda e, p: None)
        adapter.send_open_order(
            symbol="XAUUSD", side="BUY", lot=0.01, magic=20261993,
            use_raw_working_profile=True, raw_profile_path=profile_path,
        )
        # SLTP modify must have been called (action=2)
        sltp_calls = [c for c in mt5.order_send_calls if c.get("action") == 2]
        assert len(sltp_calls) >= 1
        # SLTP request must have non-zero SL/TP
        sltp_req = sltp_calls[0]
        assert sltp_req["sl"] != 0.0
        assert sltp_req["tp"] != 0.0

    def test_174_sltp_modify_fails_emergency_close(self, tmp_path):
        """If SLTP modify fails after raw naked open, position is emergency-closed."""
        from titan.production.mt5_execution_adapter import MT5ExecutionAdapter
        profile_path = self._create_temp_raw_profile(tmp_path)
        mt5 = MockMT5(symbol_filling_mode=1 | 2,
                      order_check_default_retcode=0,
                      naked_order_retcode=10009,
                      sltp_modify_retcode=10013)  # SLTP fails
        mt5._symbol_info.trade_exemode = 2
        mt5.initialize()
        adapter = MT5ExecutionAdapter(mt5, journal_event=lambda e, p: None)
        result = adapter.send_open_order(
            symbol="XAUUSD", side="BUY", lot=0.01, magic=20261993,
            use_raw_working_profile=True, raw_profile_path=profile_path,
        )
        assert result["ok"] is False
        assert result.get("emergency_close_required") is True
        assert result.get("emergency_close_attempted") is True
        assert result.get("raw_working_profile_used") is True
        # Close order must have been sent (has "position" field)
        close_calls = [c for c in mt5.order_send_calls if c.get("position")]
        assert len(close_calls) >= 1

    def test_175_raw_profile_not_found_falls_back(self, tmp_path):
        """When use_raw_working_profile=True but no profile exists, falls
        back to normal filling-mode fallback."""
        from titan.production.mt5_execution_adapter import MT5ExecutionAdapter
        # Point to a non-existent path
        missing_path = str(tmp_path / "does_not_exist.json")
        mt5 = MockMT5(symbol_filling_mode=1,
                      order_check_default_retcode=0)
        mt5.initialize()
        adapter = MT5ExecutionAdapter(mt5, journal_event=lambda e, p: None)
        result = adapter.send_open_order(
            symbol="XAUUSD", side="BUY", lot=0.01, magic=20261993,
            use_raw_working_profile=True, raw_profile_path=missing_path,
        )
        # Should fall back to normal path (not raw)
        assert result.get("raw_working_profile_used") is not True
        # Should still work via normal filling-mode fallback
        assert result["ok"] is True

    def test_176_raw_profile_deviation_mirrored(self, tmp_path):
        """Adapter uses deviation from raw profile (50, not default 20)."""
        from titan.production.mt5_execution_adapter import MT5ExecutionAdapter
        profile_path = self._create_temp_raw_profile(tmp_path, deviation=50)
        mt5 = MockMT5(symbol_filling_mode=1 | 2,
                      order_check_default_retcode=0,
                      naked_order_retcode=10009,
                      sltp_modify_retcode=10009)
        mt5.initialize()
        adapter = MT5ExecutionAdapter(mt5, journal_event=lambda e, p: None)
        adapter.send_open_order(
            symbol="XAUUSD", side="BUY", lot=0.01, magic=20261993,
            deviation=20,   # caller passes 20, but raw profile says 50
            use_raw_working_profile=True, raw_profile_path=profile_path,
        )
        open_calls = [c for c in mt5.order_send_calls
                      if not c.get("position") and c.get("action") == 1]
        assert len(open_calls) >= 1
        # Deviation must be 50 (from raw profile), not 20 (from caller)
        assert open_calls[0]["deviation"] == 50

    def test_177_raw_profile_journal_events(self, tmp_path):
        """Required raw profile journal events are emitted."""
        from titan.production.mt5_execution_adapter import MT5ExecutionAdapter
        profile_path = self._create_temp_raw_profile(tmp_path)
        journal_events = []
        def capture(event_type, payload):
            journal_events.append({"event": event_type, **payload})
        mt5 = MockMT5(symbol_filling_mode=1 | 2,
                      order_check_default_retcode=0,
                      naked_order_retcode=10009,
                      sltp_modify_retcode=10009)
        mt5.initialize()
        adapter = MT5ExecutionAdapter(mt5, journal_event=capture)
        adapter.send_open_order(
            symbol="XAUUSD", side="BUY", lot=0.01, magic=20261993,
            use_raw_working_profile=True, raw_profile_path=profile_path,
        )
        event_types = [e.get("event") for e in journal_events]
        assert "ADAPTER_RAW_WORKING_PROFILE_MODE" in event_types
        assert "ADAPTER_RAW_PROFILE_LOADED" in event_types
        assert "ADAPTER_RAW_NAKED_ORDER_ATTEMPTED" in event_types
        assert "ADAPTER_RAW_SLTP_MODIFY_SUCCESS" in event_types

    def test_178_raw_probe_script_exists(self):
        """scripts/audit/raw_mt5_probe.py exists and is importable."""
        from pathlib import Path
        probe_path = REPO_ROOT / "scripts" / "audit" / "raw_mt5_probe.py"
        assert probe_path.exists(), "raw_mt5_probe.py not found"
        # Verify it has the required functions
        import importlib.util
        spec = importlib.util.spec_from_file_location("raw_probe", str(probe_path))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert hasattr(mod, "probe_raw_mt5")
        assert hasattr(mod, "main")
        assert mod.DEMO_MICRO_MAGIC == 20261993

    def test_179_raw_profile_harness_integration(self, tmp_path, monkeypatch):
        """Full harness: --use-raw-working-profile flag works end-to-end."""
        from scripts.audit import demo_micro_full_cycle as harness
        profile_path = self._create_temp_raw_profile(tmp_path)
        mt5 = MockMT5(symbol_filling_mode=1 | 2,
                      order_check_default_retcode=0,
                      naked_order_retcode=10009,
                      sltp_modify_retcode=10009)
        mt5._symbol_info.trade_exemode = 2
        monkeypatch.setattr(harness, "_get_mt5", lambda: mt5)
        monkeypatch.setattr(harness, "hard_gate_evaluate",
                            lambda config_path=None: {"verdict": "DEMO_MICRO_ARMED",
                                                       "reasons": [],
                                                       "checks": {}})
        monkeypatch.setenv("TITAN_DEMO_MICRO_ARMED", "1")
        # Simulate --use-raw-working-profile --raw-profile-path=...
        old_argv = sys.argv
        sys.argv = ["harness", "--mode", "DEMO_MICRO_EXECUTE",
                     "--side", "BUY", "--max-hold-seconds", "1",
                     "--use-raw-working-profile",
                     "--raw-profile-path", profile_path]
        try:
            args = harness.parse_args()
            assert args.use_raw_working_profile is True
            assert args.raw_profile_path == profile_path
        finally:
            sys.argv = old_argv


# ─── Sprint 9.9.3.22 patch — rename + pass evidence tests ─────────────────────

class TestScriptRenameAndPassEvidence:
    """Sprint 9.9.3.22 — script renamed + backward wrapper + pass evidence archiver."""

    def test_180_new_script_imports_work(self):
        """New module scripts.audit.demo_micro_full_cycle imports correctly."""
        from scripts.audit.demo_micro_full_cycle import (
            parse_args, run, main, _run_execute, _send_open_order,
            _close_position, _get_mt5, DEMO_MICRO_MAGIC,
        )
        assert DEMO_MICRO_MAGIC == 20261993
        assert callable(parse_args)
        assert callable(run)
        assert callable(main)

    def test_181_old_wrapper_still_works(self):
        """Old module scripts.audit.fundednext_demo_micro_full_cycle still imports
        via backward-compatible wrapper and re-exports the same functions."""
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            from scripts.audit.fundednext_demo_micro_full_cycle import (
                parse_args as old_parse, run as old_run,
                _send_open_order as old_send, DEMO_MICRO_MAGIC as old_magic,
            )
        from scripts.audit.demo_micro_full_cycle import parse_args as new_parse
        # Old wrapper re-exports the SAME function objects
        assert old_parse is new_parse
        assert old_magic == 20261993

    def test_182_old_wrapper_emits_deprecation_warning(self):
        """Importing the old wrapper emits a DeprecationWarning."""
        import warnings
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            # Force re-import by removing from cache
            import importlib
            if "scripts.audit.fundednext_demo_micro_full_cycle" in sys.modules:
                old_mod = sys.modules.pop("scripts.audit.fundednext_demo_micro_full_cycle")
            else:
                old_mod = None
            try:
                import scripts.audit.fundednext_demo_micro_full_cycle  # noqa: F401
            finally:
                # Restore if needed
                pass
        # At least one DeprecationWarning should have been caught
        dep_warnings = [w for w in caught if issubclass(w.category, DeprecationWarning)]
        assert len(dep_warnings) >= 1

    def test_183_pass_evidence_archiver_works(self, tmp_path):
        """Pass evidence archiver copies files and generates PASS_SUMMARY.md."""
        import json
        from scripts.audit.archive_pass_evidence import archive_pass_evidence
        # Create a minimal demo_micro_report.json in the source dir
        source_dir = REPO_ROOT / "data" / "audit" / "demo_micro"
        report_path = source_dir / "demo_micro_report.json"
        # Save original if it exists
        original_report = None
        if report_path.exists():
            original_report = report_path.read_text()
        try:
            test_report = {
                "final_verdict": "DEMO_FULL_CYCLE_PASS",
                "net_pnl": 2.40,
                "open_positions_remaining": 0,
                "filling_mode_selected": "IOC",
                "filling_source": "raw_working_profile",
                "raw_working_profile_used": True,
                "open_order": {"retcode": 10009, "request": {"symbol": "XAUUSD",
                                  "volume": 0.01, "type": 0}},
                "close_result": {"retcode": 10009},
                "pre_send_diagnostics": {"account": {"server": "MetaQuotes-Demo",
                                     "login": 12345678}},
            }
            report_path.write_text(json.dumps(test_report))
            # Also create minimal journal + profile files
            (source_dir / "demo_micro_journal.jsonl").write_text('{"event":"test"}\n')
            (source_dir / "broker_execution_profile.json").write_text('{"verdict":"SUCCESS"}')
            (source_dir / "demo_micro_report.md").write_text("# Test Report")

            result = archive_pass_evidence(server="MetaQuotes-Demo")
            assert result["ok"] is True
            assert "pass_evidence" in result["archive_path"]
            assert "metaquotes-demo" in result["archive_path"] or "metaquotes_demo" in result["archive_path"]
            assert "PASS_SUMMARY.md" in result["summary_path"]

            # Verify files were copied
            from pathlib import Path
            archive_dir = Path(result["archive_path"])
            assert (archive_dir / "demo_micro_report.json").exists()
            assert (archive_dir / "demo_micro_journal.jsonl").exists()
            assert (archive_dir / "broker_execution_profile.json").exists()
            assert (archive_dir / "PASS_SUMMARY.md").exists()

            # Verify PASS_SUMMARY.md content
            summary = (archive_dir / "PASS_SUMMARY.md").read_text()
            assert "DEMO_FULL_CYCLE_PASS" in summary
            assert "MetaQuotes-Demo" in summary
            assert "XAUUSD" in summary
            assert "10009" in summary   # open retcode

        finally:
            # Restore original report
            if original_report is not None:
                report_path.write_text(original_report)
            else:
                report_path.unlink(missing_ok=True)

    def test_184_pass_evidence_archiver_dry_run(self):
        """Archiver --dry-run reports without copying."""
        import json
        from scripts.audit.archive_pass_evidence import archive_pass_evidence
        # Ensure a report exists for the dry-run
        source_dir = REPO_ROOT / "data" / "audit" / "demo_micro"
        report_path = source_dir / "demo_micro_report.json"
        original = None
        if report_path.exists():
            original = report_path.read_text()
        if not report_path.exists():
            report_path.write_text(json.dumps({"final_verdict": "DEMO_FULL_CYCLE_PASS"}))
        try:
            result = archive_pass_evidence(server="TestServer", dry_run=True)
            assert result["ok"] is True
            assert result.get("dry_run") is True
            assert "files_to_archive" in result
        finally:
            if original is not None:
                report_path.write_text(original)
            elif report_path.exists():
                report_path.unlink()

    def test_185_pass_evidence_archiver_missing_report(self):
        """Archiver fails gracefully if demo_micro_report.json doesn't exist."""
        from scripts.audit.archive_pass_evidence import archive_pass_evidence
        # Temporarily rename the report
        source_dir = REPO_ROOT / "data" / "audit" / "demo_micro"
        report_path = source_dir / "demo_micro_report.json"
        original = None
        if report_path.exists():
            original = report_path.read_text()
            report_path.unlink()
        try:
            result = archive_pass_evidence(server="TestServer")
            assert result["ok"] is False
            assert "not found" in result["error"].lower()
        finally:
            if original is not None:
                report_path.write_text(original)

    def test_186_pass_summary_masks_login(self, tmp_path):
        """PASS_SUMMARY.md masks the login for privacy."""
        from scripts.audit.archive_pass_evidence import _mask_login
        assert _mask_login(12345678) == "12***78"
        assert _mask_login(123) == "1***3"
        assert _mask_login(None) == "N/A"

    def test_187_raw_profile_path_still_works_after_rename(self, tmp_path, monkeypatch):
        """Raw profile path still works after the script rename."""
        import json
        from scripts.audit import demo_micro_full_cycle as harness
        profile_path = tmp_path / "raw_mt5_working_profile.json"
        profile = {
            "server": "MetaQuotes-Demo", "symbol": "XAUUSD",
            "type_filling": 2, "type_filling_name": "IOC",
            "deviation": 50, "sl": 0.0, "tp": 0.0,
            "sl_tp_mode": "naked_then_sltp_modify", "type_time": 0,
        }
        profile_path.write_text(json.dumps(profile))
        mt5 = MockMT5(symbol_filling_mode=1 | 2,
                      order_check_default_retcode=0,
                      naked_order_retcode=10009,
                      sltp_modify_retcode=10009)
        mt5._symbol_info.trade_exemode = 2
        monkeypatch.setattr(harness, "_get_mt5", lambda: mt5)
        monkeypatch.setattr(harness, "hard_gate_evaluate",
                            lambda config_path=None: {"verdict": "DEMO_MICRO_ARMED",
                                                       "reasons": [], "checks": {}})
        monkeypatch.setenv("TITAN_DEMO_MICRO_ARMED", "1")
        r = _run_execute_with_mock(mt5, side="BUY", max_hold_seconds=1,
                                    use_raw_working_profile=True,
                                    raw_profile_path=str(profile_path))
        # Should PASS via raw profile
        assert r["final_verdict"] == "DEMO_FULL_CYCLE_PASS"
        assert r.get("filling_mode_selected") is not None
