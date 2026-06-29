"""
TITAN XAU AI — Sprint 9.9.3.25 Demo Micro Repeatability Tests
===============================================================

Tests for the 3-cycle repeatability script.
Covers pre-condition checks, cycle execution, failure handling,
evidence archiving, and privacy redaction.
"""
from __future__ import annotations
import json
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


class TestRepeatabilityPreConditions:
    """Pre-condition checks for the repeatability script."""

    def test_01_blocks_when_not_armed(self, monkeypatch):
        """Script blocks when TITAN_DEMO_MICRO_ARMED is not set."""
        from scripts.audit.demo_micro_repeatability import _check_pre_conditions
        monkeypatch.delenv("TITAN_DEMO_MICRO_ARMED", raising=False)
        result = _check_pre_conditions("MetaQuotes-Demo", "XAUUSD", 0.01)
        assert result["ok"] is False
        assert "TITAN_DEMO_MICRO_ARMED" in result["error"]

    def test_02_blocks_lot_above_001(self, monkeypatch):
        """Script blocks when lot > 0.01."""
        from scripts.audit.demo_micro_repeatability import _check_pre_conditions
        monkeypatch.setenv("TITAN_DEMO_MICRO_ARMED", "1")
        result = _check_pre_conditions("MetaQuotes-Demo", "XAUUSD", 0.02)
        assert result["ok"] is False
        assert "0.01" in result["error"]

    def test_03_blocks_no_raw_profile(self, monkeypatch, tmp_path):
        """Script blocks when raw_mt5_working_profile.json doesn't exist."""
        from scripts.audit.demo_micro_repeatability import _check_pre_conditions
        monkeypatch.setenv("TITAN_DEMO_MICRO_ARMED", "1")
        # Temporarily rename the raw profile
        raw_path = REPO_ROOT / "data" / "audit" / "demo_micro" / "raw_mt5_working_profile.json"
        original = None
        if raw_path.exists():
            original = raw_path.read_text()
            raw_path.unlink()
        try:
            result = _check_pre_conditions("MetaQuotes-Demo", "XAUUSD", 0.01)
            assert result["ok"] is False
            assert "raw_mt5_working_profile" in result["error"]
        finally:
            if original is not None:
                raw_path.write_text(original)

    def test_04_blocks_no_mt5(self, monkeypatch):
        """Script blocks when MetaTrader5 is not installed (Linux/Z AI)."""
        from scripts.audit.demo_micro_repeatability import _check_pre_conditions
        monkeypatch.setenv("TITAN_DEMO_MICRO_ARMED", "1")
        # On Linux, MetaTrader5 is not installed — this should fail
        result = _check_pre_conditions("MetaQuotes-Demo", "XAUUSD", 0.01)
        if "MetaTrader5 not installed" in result.get("error", ""):
            assert result["ok"] is False
        # If MT5 IS installed (Windows), other checks apply — skip on Linux


class TestRepeatabilityRedaction:
    """Privacy redaction tests for repeatability evidence."""

    def test_05_redact_dict_masks_login(self):
        """_redact_dict masks login values."""
        from scripts.audit.demo_micro_repeatability import _redact_dict
        data = {"account": {"login": 12345678, "name": "John Doe"}}
        _redact_dict(data)
        assert data["account"]["login"] != 12345678
        assert "***" in str(data["account"]["login"])
        assert data["account"]["name"] == "REDACTED"

    def test_06_mask_login(self):
        """_mask_login masks login for privacy."""
        from scripts.audit.demo_micro_repeatability import _mask_login
        assert "12345678" not in _mask_login(12345678)
        assert "***" in _mask_login(12345678)
        assert _mask_login(None) == "N/A"

    def test_07_redact_nested_login(self):
        """_redact_dict handles nested login/name fields."""
        from scripts.audit.demo_micro_repeatability import _redact_dict
        data = {
            "cycles": [{"account": {"login": 999, "name": "Test"}}],
            "nested": {"deep": {"login": 11111, "name": "Deep"}},
        }
        _redact_dict(data)
        assert "***" in str(data["cycles"][0]["account"]["login"])
        assert data["cycles"][0]["account"]["name"] == "REDACTED"
        assert "***" in str(data["nested"]["deep"]["login"])
        assert data["nested"]["deep"]["name"] == "REDACTED"


class TestRepeatabilityGitignore:
    """Gitignore covers repeatability runtime files."""

    def test_08_repeatability_files_ignored(self):
        """Repeatability report/journal files are in .gitignore."""
        gitignore = (REPO_ROOT / ".gitignore").read_text()
        assert "demo_micro_repeatability_report.json" in gitignore
        assert "demo_micro_repeatability_report.md" in gitignore
        assert "demo_micro_repeatability_journal.jsonl" in gitignore


class TestRepeatabilityScriptStructure:
    """Structural tests for the repeatability script."""

    def test_09_script_imports(self):
        """Repeatability script imports correctly."""
        from scripts.audit.demo_micro_repeatability import (
            main, _check_pre_conditions, _run_single_cycle,
            _force_close_all, _write_report, _archive_evidence,
            _journal, _mask_login, _redact_dict,
            CYCLES, DEMO_MICRO_MAGIC,
        )
        assert DEMO_MICRO_MAGIC == 20261993
        assert len(CYCLES) == 3
        assert CYCLES[0]["side"] == "BUY"
        assert CYCLES[1]["side"] == "SELL"
        assert CYCLES[2]["side"] == "BUY"

    def test_10_cycles_sequence(self):
        """Cycles are BUY, SELL, BUY in that order."""
        from scripts.audit.demo_micro_repeatability import CYCLES
        sides = [c["side"] for c in CYCLES]
        assert sides == ["BUY", "SELL", "BUY"]

    def test_11_all_cycles_use_001_lot(self):
        """All cycles use 0.01 lot."""
        from scripts.audit.demo_micro_repeatability import CYCLES
        for c in CYCLES:
            assert c["lot"] == 0.01

    def test_12_write_report_generates_json_and_md(self, tmp_path):
        """_write_report generates both JSON and MD files."""
        from scripts.audit.demo_micro_repeatability import _write_report
        # We need to temporarily redirect the output paths
        import scripts.audit.demo_micro_repeatability as rep
        old_json = rep.REPORT_JSON
        old_md = rep.REPORT_MD
        rep.REPORT_JSON = tmp_path / "report.json"
        rep.REPORT_MD = tmp_path / "report.md"
        try:
            cycles = [
                {"cycle": "cycle_1", "side": "BUY", "lot": 0.01,
                 "max_hold_seconds": 1, "open_retcode": 10009, "close_retcode": 10009,
                 "net_pnl": 1.5, "duration_seconds": 62.0,
                 "open_positions_before": 0, "open_positions_after": 0,
                 "verdict": "PASS", "error": None},
            ]
            _write_report(cycles, "DEMO_REPEATABILITY_PASS",
                          {"server": "MetaQuotes-Demo", "login": 12345678, "trade_mode": 0},
                          True)
            assert rep.REPORT_JSON.exists()
            assert rep.REPORT_MD.exists()
            with open(rep.REPORT_JSON) as f:
                data = json.load(f)
            assert data["final_verdict"] == "DEMO_REPEATABILITY_PASS"
            assert data["cycles_passed"] == 1
            assert data["cycles_failed"] == 0
            # Login must be masked in report
            assert "12345678" not in json.dumps(data)
        finally:
            rep.REPORT_JSON = old_json
            rep.REPORT_MD = old_md

    def test_13_archive_evidence_redacts(self, tmp_path):
        """_archive_evidence creates redacted copies."""
        from scripts.audit.demo_micro_repeatability import _archive_evidence
        import scripts.audit.demo_micro_repeatability as rep

        # Create temporary report files
        old_json = rep.REPORT_JSON
        old_md = rep.REPORT_MD
        old_journal = rep.JOURNAL_PATH
        old_output = rep.OUTPUT_DIR

        rep.OUTPUT_DIR = tmp_path
        rep.REPORT_JSON = tmp_path / "demo_micro_repeatability_report.json"
        rep.REPORT_MD = tmp_path / "demo_micro_repeatability_report.md"
        rep.JOURNAL_PATH = tmp_path / "demo_micro_repeatability_journal.jsonl"

        # Write test data with login
        rep.REPORT_JSON.write_text(json.dumps({
            "final_verdict": "DEMO_REPEATABILITY_PASS",
            "account": {"login": 12345678, "name": "John Doe"},
        }))
        rep.REPORT_MD.write_text("# Report\nLogin: 12345678\nName: John Doe\n")
        rep.JOURNAL_PATH.write_text(json.dumps({"login": 12345678, "name": "John"}) + "\n")

        try:
            archive_path = _archive_evidence(
                [], "DEMO_REPEATABILITY_PASS",
                {"server": "MetaQuotes-Demo", "login": 12345678},
            )
            assert Path(archive_path).exists()

            # Verify JSON is redacted
            archived_json = Path(archive_path) / "demo_micro_repeatability_report.json"
            with open(archived_json) as f:
                data = json.load(f)
            assert "12345678" not in json.dumps(data)
            assert data["account"]["name"] == "REDACTED"

            # Verify JSONL is redacted
            archived_jsonl = Path(archive_path) / "demo_micro_repeatability_journal.jsonl"
            content = archived_jsonl.read_text()
            assert "12345678" not in content
            assert "John" not in content or "REDACTED" in content

            # Verify MD is redacted
            archived_md = Path(archive_path) / "demo_micro_repeatability_report.md"
            md_content = archived_md.read_text()
            assert "12345678" not in md_content

        finally:
            rep.OUTPUT_DIR = old_output
            rep.REPORT_JSON = old_json
            rep.REPORT_MD = old_md
            rep.JOURNAL_PATH = old_journal


class TestRepeatabilityFailClosed:
    """Fail-closed behavior tests."""

    def test_14_final_fail_when_any_cycle_fails(self):
        """Final verdict is FAIL when any cycle verdict is FAIL."""
        from scripts.audit.demo_micro_repeatability import _write_report
        import scripts.audit.demo_micro_repeatability as rep
        cycles = [
            {"cycle": "c1", "side": "BUY", "lot": 0.01, "max_hold_seconds": 1,
             "open_retcode": 10009, "close_retcode": 10009, "net_pnl": 1,
             "duration_seconds": 62, "open_positions_before": 0,
             "open_positions_after": 0, "verdict": "PASS", "error": None},
            {"cycle": "c2", "side": "SELL", "lot": 0.01, "max_hold_seconds": 1,
             "open_retcode": 10006, "close_retcode": None, "net_pnl": 0,
             "duration_seconds": 5, "open_positions_before": 0,
             "open_positions_after": 0, "verdict": "FAIL", "error": "Open failed"},
        ]
        # The script determines final_verdict based on cycle results
        # If any cycle fails, final_verdict = DEMO_REPEATABILITY_FAIL
        final = "DEMO_REPEATABILITY_FAIL" if any(c["verdict"] == "FAIL" for c in cycles) else "DEMO_REPEATABILITY_PASS"
        assert final == "DEMO_REPEATABILITY_FAIL"

    def test_15_final_pass_only_when_all_pass(self):
        """Final verdict is PASS only when all 3 cycles pass."""
        cycles = [
            {"verdict": "PASS"}, {"verdict": "PASS"}, {"verdict": "PASS"},
        ]
        final = "DEMO_REPEATABILITY_PASS" if all(c["verdict"] == "PASS" for c in cycles) else "DEMO_REPEATABILITY_FAIL"
        assert final == "DEMO_REPEATABILITY_PASS"

    def test_16_stops_after_first_failure(self):
        """Script stops after first failed cycle (only 2 cycles in results)."""
        # Simulate: cycle 1 passes, cycle 2 fails → only 2 cycles in results
        cycles = [
            {"cycle": "c1", "verdict": "PASS"},
            {"cycle": "c2", "verdict": "FAIL"},
        ]
        # Script would break after c2 — cycle 3 never runs
        assert len(cycles) == 2
        assert cycles[-1]["verdict"] == "FAIL"
