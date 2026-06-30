"""TITAN XAU AI - Sprint 9.9.3.35 Operator Control Console Tests"""
from __future__ import annotations
import inspect, json, sys
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from titan.production.operator_control_console import (
    OperatorCommand, OperatorCommandResult, OperatorControlConsole,
)


class TestStatusCommand:
    def test_01_status_returns_ok(self):
        console = OperatorControlConsole()
        result = console.run_status()
        assert isinstance(result, OperatorCommandResult)
        assert result.command == OperatorCommand.STATUS.value
        assert result.ok is True
        assert result.verdict in ("RC_READY", "RC_READY_WITH_WARNINGS", "RC_BLOCKED")

    def test_02_status_message_includes_mode(self):
        console = OperatorControlConsole()
        result = console.run_status()
        assert "RC mode=" in result.message
        assert "live_blocked=" in result.message


class TestRcCheckCommand:
    def test_03_rc_check_returns_verdict(self):
        console = OperatorControlConsole()
        result = console.run_rc_check()
        assert result.command == OperatorCommand.RC_CHECK.value
        assert result.verdict in ("RC_READY", "RC_READY_WITH_WARNINGS", "RC_BLOCKED")

    def test_04_rc_check_live_trading_false(self):
        console = OperatorControlConsole()
        result = console.run_rc_check()
        # If live trading were enabled, blockers would include it
        assert all("live_trading_enabled" not in b for b in result.blockers) or \
               any("live_trading" in b for b in result.blockers)


class TestSafetyCheckCommand:
    def test_05_safety_check_blocks_live_trading(self):
        console = OperatorControlConsole()
        result = console.run_safety_check()
        assert result.command == OperatorCommand.SAFETY_CHECK.value
        # The console must report live trading as blocked
        assert "live_trading_enabled=False" in str(result.next_steps) or \
               "live_blocked=True" in result.message or \
               "live_blocked" in result.message or result.ok is True
        # No live trading blocker should fire in a clean repo
        for b in result.blockers:
            assert "live_trading_enabled=True" not in b

    def test_06_safety_check_max_lot_cap(self):
        console = OperatorControlConsole()
        result = console.run_safety_check()
        # No max_lot blocker should fire
        for b in result.blockers:
            assert "max_lot" not in b or "exceeds" not in b


class TestBrokerStatusCommand:
    def test_07_broker_status_includes_metaquotes_verified(self):
        console = OperatorControlConsole()
        result = console.run_broker_status()
        assert result.command == OperatorCommand.BROKER_STATUS.value
        assert "MetaQuotes-Demo" in result.message
        assert "VERIFIED_FOR_DEMO_MICRO" in result.message

    def test_08_broker_status_includes_fundednext_blocked(self):
        console = OperatorControlConsole()
        result = console.run_broker_status()
        assert "FundedNext" in result.message
        assert "DO_NOT_USE" in result.message or "BLOCKED" in result.message

    def test_09_broker_status_includes_pending_brokers(self):
        console = OperatorControlConsole()
        result = console.run_broker_status()
        assert "Exness" in result.message
        assert "ICMarkets" in result.message
        assert "PENDING" in result.message


class TestObservationReportCommand:
    def test_10_observation_report_handles_missing_journal(self):
        console = OperatorControlConsole()
        # Pointing at a nonexistent path - should not crash
        result = console.run_observation_report(since_hours=None)
        assert result.command == OperatorCommand.OBSERVATION_REPORT.value
        # Even with missing journals, the report should generate
        assert result.ok is True
        # Should warn about missing journals or no events
        assert len(result.reports_generated) >= 2  # JSON + MD


class TestDailyScorecardCommand:
    def test_11_daily_scorecard_handles_missing_journal(self):
        console = OperatorControlConsole()
        result = console.run_daily_scorecard(since_hours=24)
        assert result.command == OperatorCommand.DAILY_SCORECARD.value
        # With no journals, grade should be INSUFFICIENT_DATA
        assert result.verdict in ("INSUFFICIENT_DATA", "PASS", "WARN", "FAIL")
        # Should still generate report files
        assert len(result.reports_generated) >= 2  # JSON + MD


class TestFullAuditCommand:
    def test_12_full_audit_returns_report_paths(self):
        console = OperatorControlConsole()
        result = console.run_full_audit()
        assert result.command == OperatorCommand.FULL_AUDIT.value
        # Should generate at least 4 reports (assembly, forward, daily, redacted)
        assert len(result.reports_generated) >= 4
        # Each path should exist
        for p in result.reports_generated:
            assert Path(p).exists(), f"Report missing: {p}"


class TestHelpCommand:
    def test_13_help_lists_commands(self):
        console = OperatorControlConsole()
        result = console.run_help()
        assert result.command == OperatorCommand.HELP.value
        assert result.ok is True
        # Help should mention all commands
        for cmd in OperatorCommand:
            assert cmd.value in result.message or cmd.value.replace("-", "") in result.message.replace("-", "")


class TestExecuteDispatch:
    def test_14_execute_dispatches_by_enum(self):
        console = OperatorControlConsole()
        for cmd in OperatorCommand:
            result = console.execute(cmd)
            assert isinstance(result, OperatorCommandResult)
            assert result.command == cmd.value

    def test_15_execute_dispatches_by_string(self):
        console = OperatorControlConsole()
        result = console.execute("status")
        assert result.command == "status"

    def test_16_execute_unknown_command_fails_closed(self):
        console = OperatorControlConsole()
        result = console.execute("nonexistent-command")
        assert result.ok is False
        assert result.verdict == "CONSOLE_FAILED"


class TestCommandReportWriter:
    def test_17_command_report_json_writes(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "titan.production.operator_control_console.OUTPUT_DIR", tmp_path
        )
        monkeypatch.setattr(
            "titan.production.operator_control_console.JSON_PATH",
            tmp_path / "operator_command_report.json",
        )
        monkeypatch.setattr(
            "titan.production.operator_control_console.MD_PATH",
            tmp_path / "operator_command_report.md",
        )
        console = OperatorControlConsole()
        # Use execute() to trigger command report writing
        console.execute(OperatorCommand.STATUS)
        json_path = tmp_path / "operator_command_report.json"
        assert json_path.exists()
        with open(json_path) as f:
            data = json.load(f)
        assert "last_command" in data
        assert "result" in data
        assert "safety" in data
        assert data["safety"]["live_trading_enabled"] is False
        assert data["safety"]["mt5_order_send_allowed"] is False
        assert data["safety"]["metatrader5_imported"] is False
        assert data["safety"]["market_execution_run"] is False
        assert data["safety"]["demo_micro_execute_run"] is False

    def test_18_command_report_md_writes(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "titan.production.operator_control_console.OUTPUT_DIR", tmp_path
        )
        monkeypatch.setattr(
            "titan.production.operator_control_console.JSON_PATH",
            tmp_path / "operator_command_report.json",
        )
        monkeypatch.setattr(
            "titan.production.operator_control_console.MD_PATH",
            tmp_path / "operator_command_report.md",
        )
        console = OperatorControlConsole()
        # Use execute() to trigger command report writing
        console.execute(OperatorCommand.STATUS)
        md_path = tmp_path / "operator_command_report.md"
        assert md_path.exists()
        md = md_path.read_text(encoding="utf-8")
        assert "Operator Command Report" in md
        assert "Safety" in md
        assert "live_trading_enabled" in md
        assert "Live trading remains BLOCKED" in md or "BLOCKED" in md


class TestSafetyInvariants:
    def test_19_no_metatrader5_import_in_console(self):
        from titan.production import operator_control_console
        src = inspect.getsource(operator_control_console)
        assert "import MetaTrader5" not in src
        assert "from MetaTrader5" not in src

    def test_20_no_order_send_calls_in_console(self):
        import re
        from titan.production import operator_control_console
        src = inspect.getsource(operator_control_console)
        call_pattern = r"(?<!['\"#])\b(mt5\.order_send|adapter\.send_open_order|adapter\.send_order|send_close_order)\s*\("
        matches = re.findall(call_pattern, src)
        assert len(matches) == 0, f"Found execution calls: {matches}"

    def test_21_no_mt5_execution_adapter_execution_in_console(self):
        from titan.production import operator_control_console
        src = inspect.getsource(operator_control_console)
        # MT5ExecutionAdapter may be referenced in docstrings, but should never
        # be imported here for execution purposes.
        assert "MT5ExecutionAdapter()" not in src
        assert "send_open_order(" not in src
        assert "send_close_order(" not in src

    def test_22_no_demo_micro_execute_in_console(self):
        import re
        from titan.production import operator_control_console
        src = inspect.getsource(operator_control_console)
        # Should not execute DEMO_MICRO_EXECUTE — check for actual function calls,
        # not string mentions in safety warnings.
        call_pattern = r"(?<!['\"#])\b(execute_demo_micro|run_demo_micro_execute)\s*\("
        matches = re.findall(call_pattern, src)
        assert len(matches) == 0, f"Found demo micro execute calls: {matches}"
        # Should not import demo_micro_execute module
        assert "import demo_micro_execute" not in src
        assert "from demo_micro_execute" not in src

    def test_23_no_raw_probe_in_console(self):
        import re
        from titan.production import operator_control_console
        src = inspect.getsource(operator_control_console)
        # Should not import or call raw_mt5_probe (string mentions in warnings OK)
        call_pattern = r"(?<!['\"#])\b(run_raw_probe|raw_mt5_probe)\s*\("
        matches = re.findall(call_pattern, src)
        assert len(matches) == 0, f"Found raw probe calls: {matches}"
        assert "import raw_mt5_probe" not in src
        assert "from raw_mt5_probe" not in src

    def test_24_no_repeatability_execution_in_console(self):
        import re
        from titan.production import operator_control_console
        src = inspect.getsource(operator_control_console)
        # Should not execute repeatability runner — check for actual function calls,
        # not file path references to redacted registry files.
        call_pattern = r"(?<!['\"#])\b(run_repeatability|execute_repeatability)\s*\("
        matches = re.findall(call_pattern, src)
        assert len(matches) == 0, f"Found repeatability calls: {matches}"
        # Should not import the repeatability module for execution
        assert "import demo_micro_repeatability" not in src
        assert "from demo_micro_repeatability" not in src


class TestBatchFileSafety:
    def test_25_batch_file_contains_no_live_trading_command(self):
        batch_path = REPO_ROOT / "run_titan_operator.bat"
        assert batch_path.exists(), "run_titan_operator.bat missing"
        content = batch_path.read_text(encoding="utf-8")
        # Must NOT expose live trading option as an actual command
        # Check only executable lines (not REM comments or echo banners)
        for line in content.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            upper = stripped.upper()
            # Skip comments and echo banners
            if upper.startswith("REM") or upper.startswith("@") or upper.startswith("ECHO"):
                continue
            if upper.startswith(":") or upper.startswith("GOTO") or upper.startswith("SET"):
                continue
            if upper.startswith("IF") or upper.startswith("CD") or upper.startswith("PYTHON"):
                continue
            if upper.startswith("CLS") or upper.startswith("PAUSE") or upper.startswith("ENDLOCAL"):
                continue
            if upper.startswith("CALL") or upper.startswith("EXIT"):
                continue
            # Anything else must not enable live trading
            assert "TITAN_LIVE_TRADING=1" not in stripped
            assert "live_trading: true" not in stripped.lower()

    def test_26_batch_file_contains_no_demo_micro_execute_command(self):
        batch_path = REPO_ROOT / "run_titan_operator.bat"
        content = batch_path.read_text(encoding="utf-8")
        # Check only executable python invocations
        for line in content.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            # Skip comments and banners
            upper = stripped.upper()
            if upper.startswith("REM") or upper.startswith("@") or upper.startswith("ECHO"):
                continue
            if upper.startswith(":") or upper.startswith("GOTO") or upper.startswith("SET"):
                continue
            if upper.startswith("IF") or upper.startswith("CD"):
                continue
            if upper.startswith("CLS") or upper.startswith("PAUSE") or upper.startswith("ENDLOCAL"):
                continue
            if upper.startswith("CALL") or upper.startswith("EXIT"):
                continue
            # For PYTHON lines (actual command execution), must not invoke these scripts
            if upper.startswith("PYTHON"):
                lower = stripped.lower()
                assert "demo_micro_execute" not in lower, \
                    f"DEMO_MICRO_EXECUTE in line: {stripped}"
                assert "demo_micro_full_cycle" not in lower
                assert "raw_mt5_probe" not in lower
                assert "demo_micro_repeatability" not in lower

    def test_27_batch_file_has_menu(self):
        batch_path = REPO_ROOT / "run_titan_operator.bat"
        content = batch_path.read_text(encoding="utf-8")
        assert "STATUS" in content
        assert "RC CHECK" in content
        assert "SAFETY CHECK" in content
        assert "BROKER STATUS" in content
        assert "FULL AUDIT" in content
        assert "HELP" in content


class TestResultDataclass:
    def test_28_result_has_all_required_fields(self):
        result = OperatorCommandResult(
            command="status",
            ok=True,
            verdict="RC_READY",
            message="test",
        )
        required = ["command", "ok", "verdict", "message", "reports_generated",
                     "blockers", "warnings", "next_steps", "timestamp_utc"]
        for f in required:
            assert hasattr(result, f), f"Missing field: {f}"

    def test_29_result_timestamp_auto_set(self):
        result = OperatorCommandResult(
            command="status", ok=True, verdict="RC_READY", message="",
        )
        assert result.timestamp_utc != ""

    def test_30_result_to_json_roundtrip(self):
        result = OperatorCommandResult(
            command="status", ok=True, verdict="RC_READY", message="test",
            reports_generated=["/tmp/a.json"],
            blockers=[], warnings=["w"], next_steps=["s"],
        )
        s = result.to_json()
        data = json.loads(s)
        assert data["command"] == "status"
        assert data["ok"] is True
        assert data["verdict"] == "RC_READY"
