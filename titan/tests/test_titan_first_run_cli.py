"""TITAN XAU AI - Sprint 9.9.3.40 First-Run CLI Tests"""
from __future__ import annotations
import inspect, json, subprocess, sys
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

CLI_PATH = REPO_ROOT / "scripts" / "operator" / "titan_first_run.py"


class TestCliExecution:
    def _run_cli(self, args: list[str]) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(CLI_PATH)] + args,
            capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=60,
        )

    def test_01_first_run_cli_runs(self):
        result = self._run_cli([])
        assert result.returncode in (0, 1)
        assert "First-Run Wizard" in result.stdout
        assert "Overall:" in result.stdout

    def test_02_json_output_valid(self):
        result = self._run_cli(["--json"])
        assert result.returncode in (0, 1)
        data = json.loads(result.stdout)
        assert "overall_status" in data
        assert "passed" in data
        assert "warnings" in data
        assert "failed" in data
        assert "skipped" in data
        assert "results" in data
        assert "blockers" in data
        assert "next_steps" in data
        assert "timestamp_utc" in data

    def test_03_json_results_have_required_fields(self):
        result = self._run_cli(["--json"])
        data = json.loads(result.stdout)
        for r in data["results"]:
            assert "check_name" in r
            assert "status" in r
            assert "message" in r
            assert "details" in r
            assert "next_step" in r

    def test_04_overall_status_in_valid_set(self):
        result = self._run_cli(["--json"])
        data = json.loads(result.stdout)
        assert data["overall_status"] in ("PASS", "WARN", "FAIL", "SKIP")


class TestReportArtifacts:
    def test_05_json_report_writes(self, tmp_path, monkeypatch):
        import scripts.operator.titan_first_run as cli
        old_dir, old_json, old_md = cli.OUTPUT_DIR, cli.JSON_PATH, cli.MD_PATH
        cli.OUTPUT_DIR = tmp_path
        cli.JSON_PATH = tmp_path / "first_run.json"
        cli.MD_PATH = tmp_path / "first_run.md"
        try:
            from titan.production.first_run_wizard import FirstRunWizard
            summary = FirstRunWizard().run_all()
            result = cli.write_report(summary)
            assert Path(result["json_path"]).exists()
            with open(result["json_path"]) as f:
                data = json.load(f)
            assert "overall_status" in data
            assert "counts" in data
            assert "results" in data
            assert "safety" in data
            assert data["safety"]["metatrader5_imported"] is False
            assert data["safety"]["orders_sent"] == 0
            assert data["safety"]["demo_micro_execute_run"] is False
            assert data["safety"]["live_trading_enabled"] is False
            assert data["safety"]["credentials_requested"] is False
        finally:
            cli.OUTPUT_DIR, cli.JSON_PATH, cli.MD_PATH = old_dir, old_json, old_md

    def test_06_md_report_writes(self, tmp_path, monkeypatch):
        import scripts.operator.titan_first_run as cli
        old_dir, old_json, old_md = cli.OUTPUT_DIR, cli.JSON_PATH, cli.MD_PATH
        cli.OUTPUT_DIR = tmp_path
        cli.JSON_PATH = tmp_path / "first_run.json"
        cli.MD_PATH = tmp_path / "first_run.md"
        try:
            from titan.production.first_run_wizard import FirstRunWizard
            summary = FirstRunWizard().run_all()
            result = cli.write_report(summary)
            md = Path(result["md_path"]).read_text(encoding="utf-8")
            assert "First-Run Wizard Report" in md
            assert "Overall Status" in md
            assert "Check Results" in md
            assert "Safety" in md
        finally:
            cli.OUTPUT_DIR, cli.JSON_PATH, cli.MD_PATH = old_dir, old_json, old_md


class TestSafetyInvariants:
    def test_07_no_metatrader5_import_in_cli(self):
        src = CLI_PATH.read_text(encoding="utf-8")
        assert "import MetaTrader5" not in src
        assert "from MetaTrader5" not in src

    def test_08_no_order_send_in_cli(self):
        import re
        src = CLI_PATH.read_text(encoding="utf-8")
        src = re.sub(r'"""[\s\S]*?"""', '""', src)
        src = re.sub(r"'''[\s\S]*?'''", "''", src)
        src = re.sub(r'"(?:[^"\\]|\\.)*"', '""', src)
        src = re.sub(r"'(?:[^'\\]|\\.)*'", "''", src)
        call_pattern = r"\bmt5\.order_send\s*\("
        matches = re.findall(call_pattern, src)
        assert len(matches) == 0, f"Found order_send calls: {matches}"

    def test_09_no_demo_micro_execute_in_cli(self):
        import re
        src = CLI_PATH.read_text(encoding="utf-8")
        src = re.sub(r'"""[\s\S]*?"""', '""', src)
        src = re.sub(r"'''[\s\S]*?'''", "''", src)
        src = re.sub(r'"(?:[^"\\]|\\.)*"', '""', src)
        src = re.sub(r"'(?:[^'\\]|\\.)*'", "''", src)
        call_pattern = r"\b(DEMO_MICRO_EXECUTE|run_demo_micro|execute_demo_micro)\s*\("
        matches = re.findall(call_pattern, src)
        assert len(matches) == 0, f"Found demo micro execute calls: {matches}"

    def test_10_no_credentials_requested_in_cli(self):
        """CLI must never call input() to ask for credentials."""
        import re
        src = CLI_PATH.read_text(encoding="utf-8")
        src = re.sub(r'"""[\s\S]*?"""', '""', src)
        src = re.sub(r"'''[\s\S]*?'''", "''", src)
        src = re.sub(r'"(?:[^"\\]|\\.)*"', '""', src)
        src = re.sub(r"'(?:[^'\\]|\\.)*'", "''", src)
        assert "input(" not in src
        assert "getpass" not in src
