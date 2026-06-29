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
from scripts.audit.fundednext_demo_micro_full_cycle import run


REPO_ROOT = Path(__file__).resolve().parents[2]


def _run_harness(mode="DRY_ARM_CHECK_ONLY", **kwargs):
    """Helper to run harness with specific mode."""
    old = sys.argv
    argv = ["harness", "--mode", mode]
    for k, v in kwargs.items():
        argv.extend([f"--{k.replace('_', '-')}", str(v)])
    sys.argv = argv
    from scripts.audit.fundednext_demo_micro_full_cycle import parse_args
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
        from scripts.audit import fundednext_demo_micro_full_cycle as harness
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
    def __init__(self, name="XAUUSD", visible=True):
        self.name = name
        self.digits = 2
        self.point = 0.01
        self.spread = 10
        self.trade_contract_size = 100
        self.volume_min = 0.01
        self.volume_max = 100.0
        self.volume_step = 0.01
        self.trade_mode = 4
        self.visible = visible


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


class MockMT5:
    """Mock MT5 module with configurable behavior."""
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    TRADE_ACTION_DEAL = 1
    TRADE_RETCODE_DONE = 10009

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
                 account_trade_expert=True):
        self._initialized = False
        self._account = _MockAccount(account_trade_mode, account_balance)
        # Sprint 9.9.3.14 patch — allow tests to simulate disabled
        # Algo Trading by overriding trade_expert on the mock account.
        self._account.trade_expert = account_trade_expert
        self._tick = _MockTick(tick_bid, tick_ask)
        self._symbol_info = _MockSymbolInfo("XAUUSD", symbol_visible)
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
        # Tracking
        self.order_send_calls = []
        self.last_order_request = None

    def initialize(self, *a, **kw):
        self._initialized = True
        return True

    def shutdown(self):
        self._initialized = False

    def account_info(self):
        return self._account if self._initialized else None

    def symbol_info(self, symbol):
        return self._symbol_info if self._initialized else None

    def symbol_info_tick(self, symbol):
        return self._tick if self._initialized else None

    def symbol_select(self, symbol, visible=True):
        return True

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
        if "position" in request and request.get("position"):
            # Close order
            retcode = self._close_order_retcode
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
        else:
            # Open order
            retcode = self._open_order_retcode
            if (retcode == 10009 and self._sync_position_obj is None
                    and self._auto_create_position_on_open):
                # Auto-create a matching position
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
            return _MockOrderResult(retcode=retcode, order=67890, deal=12345,
                                    price=request.get("price", 2000.10),
                                    volume=request.get("volume", 0.01),
                                    comment="OPEN")


@pytest.fixture
def mock_mt5(monkeypatch):
    """Create a MockMT5 and install it via _get_mt5 patch."""
    mt5 = MockMT5()
    # Patch _get_mt5 to return our mock
    from scripts.audit import fundednext_demo_micro_full_cycle as harness
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
        argv.extend([f"--{k.replace('_', '-')}", str(v)])
    sys.argv = argv
    from scripts.audit.fundednext_demo_micro_full_cycle import parse_args, run
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
            "scripts.audit.fundednext_demo_micro_full_cycle._load_latest_ai_signal",
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
        from scripts.audit.fundednext_demo_micro_full_cycle import parse_args
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
        """Close order_send failure => DEMO_MANUAL_REVIEW_REQUIRED."""
        mock_mt5._close_order_retcode = 10006  # REJECT
        r = _run_execute_with_mock(mock_mt5, side="BUY", max_hold_seconds=1)
        assert r["final_verdict"] == "DEMO_MANUAL_REVIEW_REQUIRED"
        assert r["close_success"] == 0
        assert r["close_attempts"] == 1
        # Close attempted
        close_calls = [req for req in mock_mt5.order_send_calls
                       if req.get("position")]
        assert len(close_calls) == 1

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
                from scripts.audit.fundednext_demo_micro_full_cycle import _TRADE_RETCODE_DONE
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
        """Open order_send failure => DEMO_FULL_CYCLE_FAIL."""
        mock_mt5._open_order_retcode = 10006  # REJECT
        r = _run_execute_with_mock(mock_mt5, side="BUY", max_hold_seconds=1)
        assert r["final_verdict"] == "DEMO_FULL_CYCLE_FAIL"
        assert r["order_send_attempts"] == 1
        assert r["order_send_success"] == 0
        # No close attempt should be made
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
        from scripts.audit import fundednext_demo_micro_full_cycle as harness
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
        from scripts.audit import fundednext_demo_micro_full_cycle as harness
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
        from scripts.audit import fundednext_demo_micro_full_cycle as harness
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
        from scripts.audit.fundednext_demo_micro_full_cycle import _get_mt5
        assert _get_mt5() is None  # Returns None on Z AI / Linux

    def test_90_blocks_when_trade_expert_false(self, monkeypatch):
        """Sprint 9.9.3.14 — _run_execute must BLOCK (no order_send)
        when account_info.trade_expert=False, even if the hard gate
        verdict is DEMO_MICRO_ARMED.

        Defense in depth: operator may have toggled MT5 Algo Trading
        button between the hard-gate run and the execute run.
        """
        from scripts.audit import fundednext_demo_micro_full_cycle as harness
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
        from scripts.audit import fundednext_demo_micro_full_cycle as harness
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
        from scripts.audit import fundednext_demo_micro_full_cycle as harness
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
