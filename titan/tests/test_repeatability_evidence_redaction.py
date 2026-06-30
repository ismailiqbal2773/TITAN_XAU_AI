"""TITAN XAU AI — Sprint 9.9.3.25.2 Repeatability Evidence Redaction Tests"""
from __future__ import annotations
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from scripts.audit.redact_repeatability_evidence import (
    generate_from_operator_summary, generate_from_evidence_dir,
    write_report, _mask_login, _redact_dict, _redact_string,
    OPERATOR_SUMMARY,
)


class TestOperatorSummary:
    """Operator summary mode tests."""

    def test_01_operator_summary_has_required_fields(self):
        s = generate_from_operator_summary()
        assert s["broker_server"] == "MetaQuotes-Demo"
        assert s["account_type"] == "DEMO"
        assert s["symbol"] == "XAUUSD"
        assert s["lot"] == 0.01
        assert s["raw_probe_status"] == "PASS"
        assert s["repeatability_verdict"] == "DEMO_REPEATABILITY_PASS"
        assert s["cycles_passed"] == 3
        assert s["cycles_failed"] == 0
        assert s["final_open_positions"] == 0
        assert s["z_ai_executed"] is False

    def test_02_operator_summary_has_safety_note(self):
        s = generate_from_operator_summary()
        assert "safety_note" in s
        assert "redacted" in s["safety_note"].lower()

    def test_03_operator_summary_no_login(self):
        s = generate_from_operator_summary()
        assert "login" not in s
        assert "account_login" not in s

    def test_04_operator_summary_no_balance(self):
        s = generate_from_operator_summary()
        assert "balance" not in s
        assert "equity" not in s


class TestRedaction:
    """Redaction function tests."""

    def test_05_mask_login(self):
        assert "12345678" not in _mask_login(12345678)
        assert "***" in _mask_login(12345678)
        assert _mask_login(None) == "REDACTED"

    def test_06_redact_dict_masks_login(self):
        d = {"account": {"login": 12345678, "name": "John Doe", "balance": 10000.0}}
        _redact_dict(d)
        assert d["account"]["login"] != 12345678
        assert "***" in str(d["account"]["login"])
        assert d["account"]["name"] == "REDACTED"
        assert d["account"]["balance"] == "REDACTED"

    def test_07_redact_dict_removes_paths(self):
        d = {"path": "C:\\Users\\operator\\evidence"}
        _redact_dict(d)
        assert d["path"] == "REDACTED"

    def test_08_redact_string_removes_windows_paths(self):
        text = "Evidence at C:\\Users\\operator\\data\\report.json"
        redacted = _redact_string(text)
        assert "C:\\Users" not in redacted
        assert "REDACTED_PATH" in redacted

    def test_09_redact_string_masks_logins(self):
        text = 'login: 12345678'
        redacted = _redact_string(text)
        assert "12345678" not in redacted
        assert "***" in redacted

    def test_10_redact_retains_verdict(self):
        d = {"verdict": "DEMO_REPEATABILITY_PASS", "cycles_passed": 3}
        _redact_dict(d)
        assert d["verdict"] == "DEMO_REPEATABILITY_PASS"
        assert d["cycles_passed"] == 3


class TestEvidenceDirMode:
    """Evidence directory mode tests."""

    def test_11_evidence_dir_fallback_when_not_found(self):
        s = generate_from_evidence_dir("/nonexistent/path")
        # Falls back to operator summary (source may be 'operator_summary' or 'operator_summary_fallback')
        assert "operator_summary" in s["source"]
        assert s["repeatability_verdict"] == "DEMO_REPEATABILITY_PASS"

    def test_12_evidence_dir_redacts_report(self, tmp_path):
        """Evidence dir mode redacts raw report data."""
        raw_report = {
            "final_verdict": "DEMO_REPEATABILITY_PASS",
            "cycles_passed": 3,
            "cycles_failed": 0,
            "final_open_positions": 0,
            "broker_server": "MetaQuotes-Demo",
            "cycles": [
                {"open_retcode": 10009, "close_retcode": 10009},
                {"open_retcode": 10009, "close_retcode": 10009},
                {"open_retcode": 10009, "close_retcode": 10009},
            ],
            "account": {"login": 12345678, "name": "John Doe", "balance": 10000.0},
        }
        report_path = tmp_path / "demo_micro_repeatability_report.json"
        report_path.write_text(json.dumps(raw_report))

        s = generate_from_evidence_dir(str(tmp_path))
        assert s["repeatability_verdict"] == "DEMO_REPEATABILITY_PASS"
        assert s["cycles_passed"] == 3
        assert s["final_open_positions"] == 0
        # Login must not appear in summary
        assert "12345678" not in json.dumps(s)


class TestReportWriter:
    """Report writer tests."""

    def test_13_json_report_writes(self, tmp_path):
        import scripts.audit.redact_repeatability_evidence as rep
        old_json = rep.JSON_PATH
        old_md = rep.MD_PATH
        old_dir = rep.OUTPUT_DIR
        rep.OUTPUT_DIR = tmp_path
        rep.JSON_PATH = tmp_path / "report.json"
        rep.MD_PATH = tmp_path / "report.md"
        try:
            summary = generate_from_operator_summary()
            result = write_report(summary)
            assert Path(result["json_path"]).exists()
            with open(result["json_path"]) as f:
                data = json.load(f)
            assert data["repeatability_verdict"] == "DEMO_REPEATABILITY_PASS"
            assert data["cycles_passed"] == 3
            assert "login" not in json.dumps(data)
            assert "balance" not in json.dumps(data)
        finally:
            rep.OUTPUT_DIR = old_dir
            rep.JSON_PATH = old_json
            rep.MD_PATH = old_md

    def test_14_md_report_writes(self, tmp_path):
        import scripts.audit.redact_repeatability_evidence as rep
        old_json = rep.JSON_PATH
        old_md = rep.MD_PATH
        old_dir = rep.OUTPUT_DIR
        rep.OUTPUT_DIR = tmp_path
        rep.JSON_PATH = tmp_path / "report.json"
        rep.MD_PATH = tmp_path / "report.md"
        try:
            summary = generate_from_operator_summary()
            result = write_report(summary)
            md = Path(result["md_path"]).read_text()
            assert "DEMO_REPEATABILITY_PASS" in md
            assert "MetaQuotes-Demo" in md
            assert "10009" in md
            assert "REDACTED" in md
        finally:
            rep.OUTPUT_DIR = old_dir
            rep.JSON_PATH = old_json
            rep.MD_PATH = old_md


class TestGitignore:
    """Verify raw evidence is ignored by git."""

    def test_15_raw_evidence_ignored(self):
        gitignore = (REPO_ROOT / ".gitignore").read_text()
        assert "raw_mt5_working_profile.json" in gitignore
        assert "demo_micro_repeatability_report.json" in gitignore
        assert "demo_micro_repeatability_journal.jsonl" in gitignore
        assert "broker_execution_profile.json" in gitignore
        assert "demo_micro_journal.jsonl" in gitignore

    def test_16_registry_not_ignored(self):
        """The docs/audit/ registry IS committed (not ignored)."""
        gitignore = (REPO_ROOT / ".gitignore").read_text()
        assert "docs/audit/" not in gitignore


class TestExecutionRegistry:
    """Verify the execution registry file exists and has correct content."""

    def test_17_registry_exists(self):
        registry = REPO_ROOT / "docs" / "audit" / "demo_micro_execution_registry.md"
        assert registry.exists()

    def test_18_registry_has_metaquotes_pass(self):
        registry = (REPO_ROOT / "docs" / "audit" / "demo_micro_execution_registry.md").read_text()
        assert "MetaQuotes-Demo" in registry
        assert "VERIFIED_FOR_DEMO_MICRO" in registry
        assert "PASS" in registry
        assert "3/3" in registry

    def test_19_registry_has_fbs_rejected(self):
        registry = (REPO_ROOT / "docs" / "audit" / "demo_micro_execution_registry.md").read_text()
        assert "FBS-Demo" in registry
        assert "REJECTED" in registry
        assert "10006" in registry

    def test_20_registry_has_fundednext_blocked(self):
        registry = (REPO_ROOT / "docs" / "audit" / "demo_micro_execution_registry.md").read_text()
        assert "FundedNext Free Trial" in registry
        assert "DO_NOT_USE" in registry
        assert "BLOCKED" in registry

    def test_21_registry_has_safety_notes(self):
        registry = (REPO_ROOT / "docs" / "audit" / "demo_micro_execution_registry.md").read_text()
        assert "No raw" in registry or "redacted" in registry.lower()
        assert "live trading" in registry.lower() or "dry_run" in registry.lower()
