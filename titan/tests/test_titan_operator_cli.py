"""TITAN XAU AI - Sprint 9.9.3.35 Operator CLI Tests"""
from __future__ import annotations
import inspect, json, subprocess, sys
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

CLI_PATH = REPO_ROOT / "scripts" / "operator" / "titan_operator.py"


class TestCliCommands:
    def _run_cli(self, args: list[str]) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(CLI_PATH)] + args,
            capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=120,
        )

    def test_01_status_command(self):
        result = self._run_cli(["status"])
        assert result.returncode in (0, 1)
        assert "OK" in result.stdout
        assert "Verdict" in result.stdout

    def test_02_rc_check_command(self):
        result = self._run_cli(["rc-check"])
        assert result.returncode in (0, 1)
        assert "Verdict" in result.stdout
        assert "RC_" in result.stdout

    def test_03_safety_check_command(self):
        result = self._run_cli(["safety-check"])
        assert result.returncode in (0, 1)
        assert "Verdict" in result.stdout

    def test_04_broker_status_command(self):
        result = self._run_cli(["broker-status"])
        assert result.returncode in (0, 1)
        assert "MetaQuotes-Demo" in result.stdout

    def test_05_observation_report_command(self):
        result = self._run_cli(["observation-report"])
        assert result.returncode in (0, 1)
        assert "Verdict" in result.stdout

    def test_06_daily_scorecard_command(self):
        result = self._run_cli(["daily-scorecard", "--since-hours", "24"])
        assert result.returncode in (0, 1)
        assert "Verdict" in result.stdout

    def test_07_full_audit_command(self):
        result = self._run_cli(["full-audit"])
        assert result.returncode in (0, 1)
        assert "Reports Generated" in result.stdout or "Reports" in result.stdout

    def test_08_help_command(self):
        result = self._run_cli(["help"])
        assert result.returncode == 0
        assert "Available commands" in result.stdout or "Available" in result.stdout

    def test_09_unknown_command_returns_error(self):
        result = self._run_cli(["nonexistent-command"])
        assert result.returncode == 2
        assert "unknown command" in result.stderr.lower() or "ERROR" in result.stderr


class TestJsonOutput:
    def _run_cli(self, args: list[str]) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(CLI_PATH)] + args,
            capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=120,
        )

    def test_10_status_json_output(self):
        result = self._run_cli(["status", "--json"])
        assert result.returncode in (0, 1)
        data = json.loads(result.stdout)
        assert "command" in data
        assert "ok" in data
        assert "verdict" in data
        assert "message" in data
        assert "reports_generated" in data
        assert "blockers" in data
        assert "warnings" in data
        assert "next_steps" in data
        assert "timestamp_utc" in data

    def test_11_rc_check_json_output(self):
        result = self._run_cli(["rc-check", "--json"])
        assert result.returncode in (0, 1)
        data = json.loads(result.stdout)
        assert data["command"] == "rc-check"

    def test_12_safety_check_json_output(self):
        result = self._run_cli(["safety-check", "--json"])
        assert result.returncode in (0, 1)
        data = json.loads(result.stdout)
        assert data["command"] == "safety-check"

    def test_13_broker_status_json_output(self):
        result = self._run_cli(["broker-status", "--json"])
        assert result.returncode in (0, 1)
        data = json.loads(result.stdout)
        assert data["command"] == "broker-status"
        assert "MetaQuotes-Demo" in data["message"]

    def test_14_help_json_output(self):
        result = self._run_cli(["help", "--json"])
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["command"] == "help"
        assert data["ok"] is True


class TestCommandReportArtifacts:
    def test_15_command_report_json_writes(self, tmp_path, monkeypatch):
        # Patch the OUTPUT_DIR / paths inside the console module
        import titan.production.operator_control_console as occ
        monkeypatch.setattr(occ, "OUTPUT_DIR", tmp_path)
        monkeypatch.setattr(occ, "JSON_PATH", tmp_path / "operator_command_report.json")
        monkeypatch.setattr(occ, "MD_PATH", tmp_path / "operator_command_report.md")
        console = occ.OperatorControlConsole()
        # Use execute() to trigger command report writing
        console.execute(occ.OperatorCommand.STATUS)
        json_path = tmp_path / "operator_command_report.json"
        assert json_path.exists()
        with open(json_path) as f:
            data = json.load(f)
        assert "last_command" in data
        assert "result" in data
        assert "safety" in data

    def test_16_command_report_md_writes(self, tmp_path, monkeypatch):
        import titan.production.operator_control_console as occ
        monkeypatch.setattr(occ, "OUTPUT_DIR", tmp_path)
        monkeypatch.setattr(occ, "JSON_PATH", tmp_path / "operator_command_report.json")
        monkeypatch.setattr(occ, "MD_PATH", tmp_path / "operator_command_report.md")
        console = occ.OperatorControlConsole()
        # Use execute() to trigger command report writing
        console.execute(occ.OperatorCommand.RC_CHECK)
        md_path = tmp_path / "operator_command_report.md"
        assert md_path.exists()
        md = md_path.read_text(encoding="utf-8")
        assert "Operator Command Report" in md


class TestCliSafetyInvariants:
    def test_17_no_metatrader5_import_in_cli(self):
        src = CLI_PATH.read_text(encoding="utf-8")
        assert "import MetaTrader5" not in src
        assert "from MetaTrader5" not in src

    def test_18_no_order_send_in_cli(self):
        src = CLI_PATH.read_text(encoding="utf-8")
        assert "mt5.order_send(" not in src
        assert "send_open_order(" not in src
        assert "send_close_order(" not in src

    def test_19_no_demo_micro_execute_in_cli(self):
        src = CLI_PATH.read_text(encoding="utf-8")
        # Check for actual calls, not string mentions
        assert "execute_demo_micro(" not in src
        assert "import demo_micro_execute" not in src
        assert "from demo_micro_execute" not in src

    def test_20_no_mt5_execution_adapter_execution_in_cli(self):
        src = CLI_PATH.read_text(encoding="utf-8")
        assert "MT5ExecutionAdapter()" not in src

    def test_21_no_raw_probe_in_cli(self):
        src = CLI_PATH.read_text(encoding="utf-8")
        # Check for actual imports/calls
        assert "import raw_mt5_probe" not in src
        assert "from raw_mt5_probe" not in src
        assert "run_raw_probe(" not in src

    def test_22_no_repeatability_in_cli(self):
        src = CLI_PATH.read_text(encoding="utf-8")
        # Check for actual imports/calls
        assert "import demo_micro_repeatability" not in src
        assert "from demo_micro_repeatability" not in src
        assert "run_repeatability(" not in src


class TestBatchFileContents:
    def test_23_batch_file_contains_no_live_trading_command(self):
        batch_path = REPO_ROOT / "run_titan_operator.bat"
        content = batch_path.read_text(encoding="utf-8")
        # Check only executable lines (not REM comments or echo banners)
        for line in content.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            upper = stripped.upper()
            # Skip comments, banners, control flow
            if upper.startswith(("REM", "@", "ECHO", ":", "GOTO", "SET",
                                  "IF", "CD", "CLS", "PAUSE", "ENDLOCAL",
                                  "CALL", "EXIT")):
                continue
            if upper.startswith("PYTHON"):
                # PYTHON lines run titan_operator.py — must not enable live trading
                assert "TITAN_LIVE_TRADING=1" not in stripped
                assert "live_trading" not in stripped.lower() or \
                       "live_trading : blocked" in stripped.lower()

    def test_24_batch_file_contains_no_demo_micro_execute_command(self):
        batch_path = REPO_ROOT / "run_titan_operator.bat"
        content = batch_path.read_text(encoding="utf-8")
        # Check PYTHON lines (actual command execution)
        for line in content.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            upper = stripped.upper()
            if not upper.startswith("PYTHON"):
                continue
            lower = stripped.lower()
            assert "demo_micro_execute" not in lower, \
                f"DEMO_MICRO_EXECUTE in line: {stripped}"
            assert "demo_micro_full_cycle" not in lower
            assert "raw_mt5_probe" not in lower
            assert "demo_micro_repeatability" not in lower

    def test_25_batch_file_calls_titan_operator_py(self):
        batch_path = REPO_ROOT / "run_titan_operator.bat"
        content = batch_path.read_text(encoding="utf-8")
        assert "scripts\\operator\\titan_operator.py" in content or \
               "scripts/operator/titan_operator.py" in content

    def test_26_batch_file_activates_venv(self):
        batch_path = REPO_ROOT / "run_titan_operator.bat"
        content = batch_path.read_text(encoding="utf-8")
        # Should attempt to activate venv if available
        assert "activate.bat" in content
