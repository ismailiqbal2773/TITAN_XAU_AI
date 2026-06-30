"""TITAN XAU AI - Sprint 9.9.3.40 First-Run Wizard Tests"""
from __future__ import annotations
import inspect, json, re, sys
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from titan.production.first_run_wizard import (
    FirstRunWizard, FirstRunCheckStatus, FirstRunWizardResult, FirstRunWizardSummary,
)


class TestWizardBasics:
    def test_01_status_enum_values(self):
        assert FirstRunCheckStatus.PASS.value == "PASS"
        assert FirstRunCheckStatus.WARN.value == "WARN"
        assert FirstRunCheckStatus.FAIL.value == "FAIL"
        assert FirstRunCheckStatus.SKIP.value == "SKIP"

    def test_02_result_dataclass(self):
        r = FirstRunWizardResult(
            check_name="test",
            status=FirstRunCheckStatus.PASS,
            message="test message",
        )
        assert r.check_name == "test"
        assert r.status == FirstRunCheckStatus.PASS
        assert r.message == "test message"
        assert r.details == {}
        assert r.next_step == ""

    def test_03_summary_dataclass(self):
        s = FirstRunWizardSummary()
        assert s.overall_status == FirstRunCheckStatus.PASS
        assert s.passed == 0
        assert s.warnings == 0
        assert s.failed == 0
        assert s.skipped == 0
        assert s.timestamp_utc != ""


class TestRunAll:
    def test_04_run_all_returns_summary(self):
        wizard = FirstRunWizard()
        summary = wizard.run_all()
        assert isinstance(summary, FirstRunWizardSummary)
        assert len(summary.results) >= 11  # 11 checks minimum
        assert summary.passed + summary.warnings + summary.failed + summary.skipped == len(summary.results)

    def test_05_wizard_returns_pass_or_warn_when_safe(self):
        """When the RC environment is safe, overall status is PASS or WARN (not FAIL)."""
        wizard = FirstRunWizard()
        summary = wizard.run_all()
        # In a clean repo with all safety invariants, status should be PASS or WARN
        # (WARN may come from virtualenv not active or git dirty)
        assert summary.overall_status in (FirstRunCheckStatus.PASS, FirstRunCheckStatus.WARN), \
            f"Expected PASS or WARN, got {summary.overall_status}. Blockers: {summary.blockers}"

    def test_06_python_version_check_passes(self):
        wizard = FirstRunWizard()
        r = wizard.check_python_version()
        assert r.status in (FirstRunCheckStatus.PASS, FirstRunCheckStatus.FAIL)
        # In test env, Python should be 3.10+
        assert r.status == FirstRunCheckStatus.PASS

    def test_07_required_files_check_passes(self):
        wizard = FirstRunWizard()
        r = wizard.check_required_files()
        assert r.status in (FirstRunCheckStatus.PASS, FirstRunCheckStatus.FAIL)
        # All required files should exist in the repo
        assert r.status == FirstRunCheckStatus.PASS, f"Missing: {r.details.get('missing', [])}"

    def test_08_operator_console_check_passes(self):
        wizard = FirstRunWizard()
        r = wizard.check_operator_console()
        assert r.status == FirstRunCheckStatus.PASS, f"Operator console check: {r.message}"

    def test_09_production_runtime_assembly_check_passes(self):
        wizard = FirstRunWizard()
        r = wizard.check_production_runtime_assembly()
        assert r.status == FirstRunCheckStatus.PASS, f"Assembly check: {r.message}"

    def test_10_master_integration_audit_check_passes(self):
        wizard = FirstRunWizard()
        r = wizard.check_master_integration_audit()
        # Should be PASS (INTEGRATION_READY_WITH_WARNINGS) or WARN (audit exception)
        assert r.status in (FirstRunCheckStatus.PASS, FirstRunCheckStatus.WARN), \
            f"Audit check: {r.message}"

    def test_11_raw_evidence_ignored_check_passes(self):
        wizard = FirstRunWizard()
        r = wizard.check_raw_evidence_ignored()
        assert r.status == FirstRunCheckStatus.PASS, f"Raw evidence check: {r.message}"

    def test_12_live_trading_blocked_check_passes(self):
        wizard = FirstRunWizard()
        r = wizard.check_live_trading_blocked()
        assert r.status == FirstRunCheckStatus.PASS, f"Live trading check: {r.message}"

    def test_13_market_execution_absent_check_passes(self):
        wizard = FirstRunWizard()
        r = wizard.check_market_execution_absent()
        assert r.status == FirstRunCheckStatus.PASS, f"Market execution check: {r.message}"

    def test_14_no_order_send_exposed_check_passes(self):
        wizard = FirstRunWizard()
        r = wizard.check_no_order_send_exposed()
        assert r.status == FirstRunCheckStatus.PASS, f"order_send check: {r.message}"


class TestSafetyInvariants:
    def test_15_no_metatrader5_import_in_wizard(self):
        from titan.production import first_run_wizard
        src = inspect.getsource(first_run_wizard)
        assert "import MetaTrader5" not in src
        assert "from MetaTrader5" not in src

    def test_16_no_order_send_in_wizard(self):
        from titan.production import first_run_wizard
        src = inspect.getsource(first_run_wizard)
        # Strip strings/comments
        src = re.sub(r'"""[\s\S]*?"""', '""', src)
        src = re.sub(r"'''[\s\S]*?'''", "''", src)
        src = re.sub(r'"(?:[^"\\]|\\.)*"', '""', src)
        src = re.sub(r"'(?:[^'\\]|\\.)*'", "''", src)
        call_pattern = r"\bmt5\.order_send\s*\("
        matches = re.findall(call_pattern, src)
        assert len(matches) == 0, f"Found order_send calls: {matches}"

    def test_17_no_demo_micro_execute_in_wizard(self):
        from titan.production import first_run_wizard
        src = inspect.getsource(first_run_wizard)
        # Strip triple-quoted docstrings first
        src = re.sub(r'"""[\s\S]*?"""', '""', src)
        src = re.sub(r"'''[\s\S]*?'''", "''", src)
        # Strip line comments
        lines = []
        for line in src.splitlines():
            # Remove # comments
            idx = line.find("#")
            if idx >= 0:
                line = line[:idx]
            lines.append(line)
        src = "\n".join(lines)
        # Strip remaining string literals (handle raw strings)
        src = re.sub(r'r"[^"]*"', '""', src)
        src = re.sub(r"r'[^']*'", "''", src)
        src = re.sub(r'"(?:[^"\\]|\\.)*"', '""', src)
        src = re.sub(r"'(?:[^'\\]|\\.)*'", "''", src)
        # Check for actual function CALLS (not string mentions)
        call_pattern = r"(?<!['\"])\b(DEMO_MICRO_EXECUTE|run_demo_micro|execute_demo_micro)\s*\("
        matches = re.findall(call_pattern, src)
        assert len(matches) == 0, f"Found demo micro execute calls: {matches}"

    def test_18_no_credentials_requested_in_wizard(self):
        """Wizard must never call input() to ask for credentials."""
        from titan.production import first_run_wizard
        src = inspect.getsource(first_run_wizard)
        # Strip strings/comments
        src = re.sub(r'"""[\s\S]*?"""', '""', src)
        src = re.sub(r"'''[\s\S]*?'''", "''", src)
        src = re.sub(r'"(?:[^"\\]|\\.)*"', '""', src)
        src = re.sub(r"'(?:[^'\\]|\\.)*'", "''", src)
        # No input() calls
        assert "input(" not in src
        # No getpass calls
        assert "getpass" not in src


class TestBatchFileSafety:
    def test_19_first_run_batch_no_live_trading(self):
        batch_path = REPO_ROOT / "run_titan_first_run.bat"
        content = batch_path.read_text(encoding="utf-8")
        # Check no TITAN_LIVE_TRADING=1
        assert "TITAN_LIVE_TRADING=1" not in content

    def test_20_first_run_batch_no_demo_micro_execute(self):
        batch_path = REPO_ROOT / "run_titan_first_run.bat"
        content = batch_path.read_text(encoding="utf-8")
        # Check PYTHON lines (actual command execution) for forbidden scripts
        for line in content.splitlines():
            stripped = line.strip()
            upper = stripped.upper()
            if upper.startswith("PYTHON"):
                lower = stripped.lower()
                assert "demo_micro_execute" not in lower
                assert "demo_micro_full_cycle" not in lower
                assert "raw_mt5_probe" not in lower
                assert "demo_micro_repeatability" not in lower

    def test_21_operator_batch_no_live_trading(self):
        batch_path = REPO_ROOT / "run_titan_operator.bat"
        content = batch_path.read_text(encoding="utf-8")
        assert "TITAN_LIVE_TRADING=1" not in content

    def test_22_operator_batch_no_demo_micro_execute(self):
        batch_path = REPO_ROOT / "run_titan_operator.bat"
        content = batch_path.read_text(encoding="utf-8")
        for line in content.splitlines():
            stripped = line.strip()
            upper = stripped.upper()
            if upper.startswith("PYTHON"):
                lower = stripped.lower()
                assert "demo_micro_execute" not in lower
                assert "demo_micro_full_cycle" not in lower
                assert "raw_mt5_probe" not in lower
                assert "demo_micro_repeatability" not in lower

    def test_23_operator_batch_has_all_9_safe_commands(self):
        """Operator batch must expose all 9 safe commands (STATUS, RC CHECK, SAFETY CHECK, BROKER STATUS, OBSERVATION REPORT, DAILY SCORECARD, FULL AUDIT, HELP, EXIT)."""
        batch_path = REPO_ROOT / "run_titan_operator.bat"
        content = batch_path.read_text(encoding="utf-8")
        assert "STATUS" in content
        assert "RC CHECK" in content
        assert "SAFETY CHECK" in content
        assert "BROKER STATUS" in content
        assert "OBSERVATION REPORT" in content
        assert "DAILY SCORECARD" in content
        assert "FULL AUDIT" in content
        assert "HELP" in content
        assert "EXIT" in content
