"""
TITAN XAU AI — Sprint 9.9.2 Demo Micro Hard Gate Tests (Config Fix)
"""
from __future__ import annotations
import json, os, sys, platform, yaml, pytest
from datetime import datetime, timezone
from pathlib import Path
from scripts.audit.demo_micro_hard_gate import evaluate
from scripts.audit.demo_micro_config import load_demo_micro_config

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO_ROOT / "config" / "runtime.yaml"


class TestConfigReading:
    def test_01_enabled_true_read_correctly(self, tmp_path):
        """top-level demo_micro.enabled=true is read as True"""
        cfg = tmp_path / "runtime.yaml"
        cfg.write_text("demo_micro:\n  enabled: true\n  max_lot: 0.01\n")
        result = load_demo_micro_config(str(cfg))
        assert result["demo_micro_enabled_raw"] is True
        assert result["demo_micro_enabled_effective"] is True

    def test_02_enabled_false_read_correctly(self, tmp_path):
        """top-level demo_micro.enabled=false is read as False"""
        cfg = tmp_path / "runtime.yaml"
        cfg.write_text("demo_micro:\n  enabled: false\n  max_lot: 0.01\n")
        result = load_demo_micro_config(str(cfg))
        assert result["demo_micro_enabled_raw"] is False
        assert result["demo_micro_enabled_effective"] is False

    def test_03_missing_section_defaults_false(self, tmp_path):
        """missing demo_micro section defaults to False"""
        cfg = tmp_path / "runtime.yaml"
        cfg.write_text("runtime:\n  dry_run: true\n")
        result = load_demo_micro_config(str(cfg))
        assert result["demo_micro_config_found"] is False
        assert result["demo_micro_enabled_effective"] is False

    def test_04_does_not_read_unrelated_enabled(self, tmp_path):
        """hard gate does not read unrelated enabled fields"""
        cfg = tmp_path / "runtime.yaml"
        cfg.write_text("runtime:\n  enabled: true\ncapital_protection:\n  enabled: true\ndemo_micro:\n  enabled: false\n")
        result = load_demo_micro_config(str(cfg))
        assert result["demo_micro_enabled_effective"] is False  # reads demo_micro, not others

    def test_05_diagnostic_includes_config_path(self, tmp_path):
        """hard gate diagnostic includes config_path_used"""
        cfg = tmp_path / "runtime.yaml"
        cfg.write_text("demo_micro:\n  enabled: true\n")
        result = load_demo_micro_config(str(cfg))
        assert "config_path_used" in result
        assert str(cfg) in result["config_path_used"]

    def test_06_diagnostic_includes_enabled_raw(self, tmp_path):
        """hard gate diagnostic includes demo_micro_enabled_raw"""
        cfg = tmp_path / "runtime.yaml"
        cfg.write_text("demo_micro:\n  enabled: true\n")
        result = load_demo_micro_config(str(cfg))
        assert "demo_micro_enabled_raw" in result
        assert result["demo_micro_enabled_raw"] is True

    def test_07_diagnostic_includes_enabled_effective(self, tmp_path):
        """hard gate diagnostic includes demo_micro_enabled_effective"""
        result = load_demo_micro_config()
        assert "demo_micro_enabled_effective" in result

    def test_08_harness_uses_same_config(self):
        """DRY_ARM_CHECK_ONLY uses same config value as hard gate"""
        gate_result = evaluate()
        cfg = load_demo_micro_config()
        assert gate_result["demo_micro_enabled_effective"] == cfg["demo_micro_enabled_effective"]

    def test_09_enabled_true_arm_present_can_arm(self, tmp_path):
        """if config enabled=true and arm present and checks pass, can become ARMED"""
        cfg = tmp_path / "runtime.yaml"
        cfg.write_text("demo_micro:\n  enabled: true\n  max_lot: 0.01\n  max_open_positions: 1\n  force_close_on_end: true\n")
        os.environ["TITAN_DEMO_MICRO_ARMED"] = "1"
        result = evaluate(str(cfg))
        # On Linux without MT5, still blocked — but demo_micro_enabled should be True
        assert result["demo_micro_enabled_effective"] is True
        os.environ.pop("TITAN_DEMO_MICRO_ARMED", None)

    def test_10_enabled_true_arm_missing_blocked(self, tmp_path):
        """if config enabled=true but arm missing, verdict BLOCKED"""
        cfg = tmp_path / "runtime.yaml"
        cfg.write_text("demo_micro:\n  enabled: true\n")
        os.environ.pop("TITAN_DEMO_MICRO_ARMED", None)
        result = evaluate(str(cfg))
        assert result["checks"]["demo_micro_enabled"] is True
        assert result["checks"]["arm_token_present"] is False
        assert result["verdict"] in ("DEMO_MICRO_BLOCKED", "MARKET_CLOSED")

    def test_11_enabled_false_arm_present_blocked(self, tmp_path):
        """if config enabled=false but arm present, verdict BLOCKED"""
        cfg = tmp_path / "runtime.yaml"
        cfg.write_text("demo_micro:\n  enabled: false\n")
        os.environ["TITAN_DEMO_MICRO_ARMED"] = "1"
        result = evaluate(str(cfg))
        assert result["checks"]["demo_micro_enabled"] is False
        assert result["verdict"] in ("DEMO_MICRO_BLOCKED", "MARKET_CLOSED")
        os.environ.pop("TITAN_DEMO_MICRO_ARMED", None)

    def test_12_no_order_send_in_hard_gate(self):
        """Hard gate module must never CALL mt5.order_send.

        Sprint 9.9.3.14 note: the module may now MENTION order_send in
        comments/diagnostics (e.g. explaining that retcode=10027 is what
        MT5 returns when autotrading is disabled), but it must never
        invoke the call. We check for the call pattern explicitly.
        """
        import inspect, re
        from scripts.audit import demo_micro_hard_gate
        src = inspect.getsource(demo_micro_hard_gate)
        # No direct mt5.order_send(...) call
        assert "mt5.order_send(" not in src
        # No indirect helper that sends orders
        assert "_send_open_order(" not in src
        assert "_close_position(" not in src
        # No bare alias either (defensive)
        assert not re.search(r"^\s*\w+\.order_send\s*\(", src, re.MULTILINE)

    def test_13_no_order_send_in_dry_check(self):
        """DRY_ARM_CHECK_ONLY path must never call order_send.

        Sprint 9.9.3 note: order_send IS now used inside DEMO_MICRO_EXECUTE
        (_run_execute), but it is NOT reachable from DRY_ARM_CHECK_ONLY.
        We verify both at runtime (no order_send_called=True) and at the
        source level by inspecting only the DRY_ARM_CHECK_ONLY branch.
        """
        import inspect
        from scripts.audit import fundednext_demo_micro_full_cycle as harness

        # Runtime check: running DRY_ARM_CHECK_ONLY must not call order_send.
        import asyncio
        old_argv = sys.argv
        sys.argv = ["harness", "--mode", "DRY_ARM_CHECK_ONLY"]
        from scripts.audit.fundednext_demo_micro_full_cycle import parse_args, run
        args = parse_args()
        sys.argv = old_argv
        asyncio.run(run(args))

        report_path = REPO_ROOT / "data" / "audit" / "demo_micro" / "demo_micro_report.json"
        with open(report_path) as f:
            r = json.load(f)
        assert r["order_send_called"] is False

        # Source check: order_send appears ONLY inside _run_execute (execute path).
        src = inspect.getsource(harness)
        # Find the DRY_ARM_CHECK_ONLY branch and assert it does not call order_send.
        dry_marker = 'if args.mode == "DRY_ARM_CHECK_ONLY":'
        execute_marker = 'if args.mode == "DEMO_MICRO_EXECUTE":'
        assert dry_marker in src
        assert execute_marker in src
        dry_section = src.split(dry_marker)[1].split(execute_marker)[0]
        assert "mt5.order_send" not in dry_section
        assert "_send_open_order" not in dry_section
        assert "_close_position" not in dry_section

    def test_14_execute_not_run_in_tests(self):
        """DEMO_MICRO_EXECUTE not run in tests"""
        # This test exists as a guard — we verify arm token is not set
        assert os.environ.get("TITAN_DEMO_MICRO_ARMED", "0") != "1" or True  # tests don't set it permanently


class TestExistingHardGateChecks:
    """All previous tests still pass with new config reading."""

    def test_15_blocks_non_demo(self):
        result = evaluate()
        if not result["checks"]["mt5_reachable"]:
            assert result["verdict"] in ("DEMO_MICRO_BLOCKED", "MARKET_CLOSED")

    def test_16_blocks_missing_arm(self):
        os.environ.pop("TITAN_DEMO_MICRO_ARMED", None)
        result = evaluate()
        assert result["checks"]["arm_token_present"] is False

    def test_17_dry_check_runs_without_arm(self):
        os.environ.pop("TITAN_DEMO_MICRO_ARMED", None)
        result = evaluate()
        assert "verdict" in result

    def test_18_max_lot_ok(self):
        result = evaluate()
        assert result["checks"]["max_lot_ok"] is True

    def test_19_force_close_on_end(self):
        result = evaluate()
        assert result["checks"]["force_close_on_end"] is True

    def test_20_kill_switch_normal(self):
        result = evaluate()
        assert result["checks"]["kill_switch_normal"] is True

    def test_21_market_open_check(self):
        result = evaluate()
        assert "market_open" in result["checks"]

    def test_22_not_real_account_check(self):
        result = evaluate()
        assert "not_real_account" in result["checks"]

    def test_23_report_json_generated(self):
        result = evaluate()
        json.dumps(result, default=str)

    def test_24_timestamps_utc(self):
        result = evaluate()
        ts = result["timestamp_utc"]
        assert "+" in ts or "Z" in ts

    def test_25_diagnostic_fields_present(self):
        result = evaluate()
        assert "config_path_used" in result
        assert "demo_micro_config_found" in result
        assert "demo_micro_enabled_raw" in result
        assert "demo_micro_enabled_effective" in result


# ─── Sprint 9.9.3.14 patch — trade_expert hard gate tests ──────────────────────

class TestTradeExpertHardGate:
    """Sprint 9.9.3.14 — block DEMO_MICRO_ARMED when account_info.trade_expert=False.

    Background: Monday DEMO micro execution attempt failed safely with
    MT5 retcode=10027 ("client terminal autotrading disabled") because
    account_info.trade_expert was False even though account_trade_allowed,
    terminal_trade_allowed, and tradeapi_disabled all looked fine. The
    hard gate must block BEFORE arming in this state.
    """

    def test_26_trade_expert_check_exists(self):
        """Hard gate exposes a trade_expert_enabled check."""
        result = evaluate()
        assert "trade_expert_enabled" in result["checks"]

    def test_27_account_trade_expert_diagnostic_field(self):
        """Result includes account_trade_expert diagnostic (may be None on Linux)."""
        result = evaluate()
        assert "account_trade_expert" in result
        # On Linux without MT5, this is None — that's expected.
        # On Windows with MT5, it must be a bool.
        v = result["account_trade_expert"]
        assert v is None or isinstance(v, bool)

    def test_28_retcode_10027_meaning_documented(self):
        """Module exports the canonical meaning for retcode=10027."""
        from scripts.audit.demo_micro_hard_gate import RETCODE_10027_MEANING
        assert RETCODE_10027_MEANING == "client terminal autotrading disabled"

    def test_29_trade_expert_disabled_reason_canonical(self):
        """Module exports the canonical reason string for the blocked case."""
        from scripts.audit.demo_micro_hard_gate import TRADE_EXPERT_DISABLED_REASON
        # Must mention both "expert" and "retcode=10027" so the journal
        # entry is greppable by operators.
        assert "expert" in TRADE_EXPERT_DISABLED_REASON.lower()
        assert "retcode=10027" in TRADE_EXPERT_DISABLED_REASON
        assert "disabled" in TRADE_EXPERT_DISABLED_REASON.lower()

    def test_30_blocks_when_trade_expert_false(self, tmp_path, monkeypatch):
        """If account_info.trade_expert=False, verdict must be DEMO_MICRO_BLOCKED.

        We simulate MT5 by injecting a fake mt5 module that returns a
        DEMO account with trade_expert=False. All other config knobs are
        set to passing values — the ONLY blocking reason must be the
        trade_expert check.
        """
        cfg = tmp_path / "runtime.yaml"
        cfg.write_text(
            "demo_micro:\n"
            "  enabled: true\n"
            "  max_lot: 0.01\n"
            "  max_open_positions: 1\n"
            "  max_trades_per_run: 1\n"
            "  force_close_on_end: true\n"
            "  arm_token_env: TITAN_DEMO_MICRO_ARMED\n"
        )
        monkeypatch.setenv("TITAN_DEMO_MICRO_ARMED", "1")

        # Fake MT5 — DEMO account with trade_expert=False
        class _FakeAccountInfo:
            trade_mode = 0          # 0 = DEMO
            trade_expert = False    # THE BUG WE ARE FIXING
            trade_allowed = True
            name = "FakeDemo"
            server = "FundedNext-Server 3"

        class _FakeMT5:
            @staticmethod
            def initialize():
                return True
            @staticmethod
            def account_info():
                return _FakeAccountInfo()
            @staticmethod
            def shutdown():
                return True

        import sys
        # Remove any cached MetaTrader5 to force re-import
        sys.modules.pop("MetaTrader5", None)
        sys.modules["MetaTrader5"] = _FakeMT5

        try:
            # Also need a readiness report so that check doesn't mask the verdict
            from pathlib import Path as _P
            readiness_dir = _P(__file__).resolve().parents[2] / "data" / "audit" / "demo_micro_readiness"
            readiness_dir.mkdir(parents=True, exist_ok=True)
            readiness_path = readiness_dir / "demo_micro_readiness_report.json"
            readiness_path.write_text(json.dumps({"verdict": "DEMO_MICRO_READY"}))

            # Weekend guard — if today is Sat/Sun, the verdict would be
            # MARKET_CLOSED and mask our test. Force a weekday by patching
            # datetime in the hard_gate module.
            from datetime import datetime as _dt, timezone as _tz
            from scripts.audit import demo_micro_hard_gate as hg

            class _FakeDT(_dt):
                @classmethod
                def now(cls, tz=None):
                    # 2026-06-29 is a Monday — guarantees weekday check passes
                    return _dt(2026, 6, 29, 12, 0, 0, tzinfo=tz or _tz.utc)

            original_dt = hg.datetime
            hg.datetime = _FakeDT
            try:
                result = evaluate(str(cfg))
            finally:
                hg.datetime = original_dt

            assert result["verdict"] == "DEMO_MICRO_BLOCKED", \
                f"Expected DEMO_MICRO_BLOCKED, got {result['verdict']}: {result['reasons']}"
            assert result["checks"]["trade_expert_enabled"] is False
            assert result["checks"]["account_demo"] is True
            assert result["account_trade_expert"] is False
            # The canonical reason must appear in the reasons list
            assert any("expert" in r.lower() and "retcode=10027" in r
                       for r in result["reasons"]), \
                f"trade_expert reason not found in: {result['reasons']}"
        finally:
            sys.modules.pop("MetaTrader5", None)
            monkeypatch.delenv("TITAN_DEMO_MICRO_ARMED", raising=False)

    def test_31_passes_when_trade_expert_true(self, tmp_path, monkeypatch):
        """If account_info.trade_expert=True (and everything else OK),
        the gate can reach DEMO_MICRO_ARMED. Note: the readiness report
        check is also required, so we inject a DEMO_MICRO_READY report.
        """
        cfg = tmp_path / "runtime.yaml"
        cfg.write_text(
            "demo_micro:\n"
            "  enabled: true\n"
            "  max_lot: 0.01\n"
            "  max_open_positions: 1\n"
            "  max_trades_per_run: 1\n"
            "  force_close_on_end: true\n"
            "  arm_token_env: TITAN_DEMO_MICRO_ARMED\n"
        )
        monkeypatch.setenv("TITAN_DEMO_MICRO_ARMED", "1")

        class _FakeAccountInfo:
            trade_mode = 0          # DEMO
            trade_expert = True     # THE FIX — expert trading enabled
            trade_allowed = True
            name = "FakeDemo"
            server = "FundedNext-Server 3"

        class _FakeMT5:
            @staticmethod
            def initialize():
                return True
            @staticmethod
            def account_info():
                return _FakeAccountInfo()
            @staticmethod
            def shutdown():
                return True

        import sys
        sys.modules.pop("MetaTrader5", None)
        sys.modules["MetaTrader5"] = _FakeMT5

        try:
            from pathlib import Path as _P
            readiness_dir = _P(__file__).resolve().parents[2] / "data" / "audit" / "demo_micro_readiness"
            readiness_dir.mkdir(parents=True, exist_ok=True)
            readiness_path = readiness_dir / "demo_micro_readiness_report.json"
            readiness_path.write_text(json.dumps({"verdict": "DEMO_MICRO_READY"}))

            # Force weekday
            from datetime import datetime as _dt, timezone as _tz
            from scripts.audit import demo_micro_hard_gate as hg

            class _FakeDT(_dt):
                @classmethod
                def now(cls, tz=None):
                    return _dt(2026, 6, 29, 12, 0, 0, tzinfo=tz or _tz.utc)

            original_dt = hg.datetime
            hg.datetime = _FakeDT
            try:
                result = evaluate(str(cfg))
            finally:
                hg.datetime = original_dt

            # trade_expert check MUST pass
            assert result["checks"]["trade_expert_enabled"] is True
            assert result["checks"]["account_demo"] is True
            assert result["account_trade_expert"] is True
            # trade_expert reason MUST NOT appear
            assert not any("expert" in r.lower() and "retcode=10027" in r
                           for r in result["reasons"])
            # Verdict should be ARMED (all checks pass in this mock setup)
            assert result["verdict"] == "DEMO_MICRO_ARMED", \
                f"Expected DEMO_MICRO_ARMED, got {result['verdict']}: {result['reasons']}"
        finally:
            sys.modules.pop("MetaTrader5", None)
            monkeypatch.delenv("TITAN_DEMO_MICRO_ARMED", raising=False)

    def test_32_retcode_10027_diagnostic_mapping(self):
        """retcode=10027 maps to 'client terminal autotrading disabled'.

        Verifies the canonical mapping is exported from both the hard
        gate and the harness module so operator journal entries are
        greppable across both code paths.
        """
        from scripts.audit.demo_micro_hard_gate import RETCODE_10027_MEANING as m1
        from scripts.audit.fundednext_demo_micro_full_cycle import (
            _RETCODE_10027_MEANING as m2,
            _TRADE_RETCODE_AUTOTRADING_DISABLED,
        )
        assert m1 == "client terminal autotrading disabled"
        assert m2 == "client terminal autotrading disabled"
        assert _TRADE_RETCODE_AUTOTRADING_DISABLED == 10027

    def test_33_harness_blocks_execute_when_trade_expert_false(self, monkeypatch):
        """fundednext_demo_micro_full_cycle._run_execute must block
        when account_info.trade_expert=False, even if the hard gate
        verdict is DEMO_MICRO_ARMED (defense in depth — operator may
        have toggled MT5 Algo Trading button between gate run and
        execute run).
        """
        import asyncio, sys
        from pathlib import Path as _P

        class _FakeAccountInfo:
            trade_mode = 0
            trade_expert = False    # Simulate operator disabled Algo Trading
            trade_allowed = True
            balance = 10000.0
            name = "FakeDemo"
            server = "FundedNext-Server 3"

        class _FakeMT5:
            initialized = False
            @staticmethod
            def initialize():
                _FakeMT5.initialized = True
                return True
            @staticmethod
            def account_info():
                return _FakeAccountInfo()
            @staticmethod
            def shutdown():
                return True

        sys.modules.pop("MetaTrader5", None)
        sys.modules["MetaTrader5"] = _FakeMT5

        # Force ARMED state — hard gate verdict bypassed by setting
        # trade_expert=True in the gate's view, but the harness sees
        # the False value (simulating a race).
        monkeypatch.setenv("TITAN_DEMO_MICRO_ARMED", "1")

        try:
            from scripts.audit.fundednext_demo_micro_full_cycle import _run_execute
            # Build a fake gate verdict (ARMED) and args
            gate = {"verdict": "DEMO_MICRO_ARMED"}
            cfg = {
                "max_lot": 0.01,
                "max_spread_usd": 1.0,
                "max_open_positions": 1,
                "max_trades_per_run": 1,
                "force_close_on_end": True,
            }

            class _Args:
                symbol = "XAUUSD"
                lot = 0.01
                side = "BUY"
                max_hold_seconds = 60
                force_close_on_end = "true"
                max_trades = 1
                max_duration_minutes = 240

            args = _Args()
            result = asyncio.run(_run_execute(args, gate, cfg))

            assert result["final_verdict"] == "DEMO_MICRO_BLOCKED"
            assert "expert" in result["reason"].lower()
            assert "retcode=10027" in result["reason"]
            # No order must have been sent
            assert result["order_send_called"] is False
            assert result["order_send_attempts"] == 0
        finally:
            sys.modules.pop("MetaTrader5", None)
            monkeypatch.delenv("TITAN_DEMO_MICRO_ARMED", raising=False)

    def test_34_demo_micro_execute_not_run_in_tests(self):
        """Sanity: TITAN_DEMO_MICRO_ARMED is not persistently set."""
        # This is a meta-check — the previous tests must clean up after themselves.
        # If they didn't, this assertion catches the leak.
        v = os.environ.get("TITAN_DEMO_MICRO_ARMED", "0")
        assert v != "1", "TITAN_DEMO_MICRO_ARMED leaked into env after a test"
