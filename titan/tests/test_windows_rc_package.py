"""TITAN XAU AI - Sprint 9.9.3.40 Windows RC Package Builder Tests"""
from __future__ import annotations
import inspect, json, re, sys
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


class TestPackageBuilder:
    def test_01_package_builder_creates_dist(self, tmp_path, monkeypatch):
        import scripts.release.build_windows_rc_package as builder
        # Patch OUTPUT_DIR to tmp_path
        old_output = builder.OUTPUT_DIR
        builder.OUTPUT_DIR = tmp_path / "TITAN_XAU_AI_RC"
        try:
            result = builder.build_package()
            assert (tmp_path / "TITAN_XAU_AI_RC").exists()
            assert (tmp_path / "TITAN_XAU_AI_RC" / "RELEASE_MANIFEST.json").exists()
            assert (tmp_path / "TITAN_XAU_AI_RC" / "README_FIRST_RUN.md").exists()
            assert (tmp_path / "TITAN_XAU_AI_RC" / "SAFETY_NOTICE.md").exists()
        finally:
            builder.OUTPUT_DIR = old_output

    def test_02_release_manifest_writes(self, tmp_path, monkeypatch):
        import scripts.release.build_windows_rc_package as builder
        old_output = builder.OUTPUT_DIR
        builder.OUTPUT_DIR = tmp_path / "TITAN_XAU_AI_RC"
        try:
            result = builder.build_package()
            manifest_path = tmp_path / "TITAN_XAU_AI_RC" / "RELEASE_MANIFEST.json"
            with open(manifest_path) as f:
                manifest = json.load(f)
            assert "built_utc" in manifest
            assert "package_name" in manifest
            assert "included_files" in manifest
            assert "excluded_patterns" in manifest
            assert "safety" in manifest
            assert manifest["safety"]["live_trading_enabled"] is False
            assert manifest["safety"]["market_execution_available"] is False
            assert manifest["safety"]["demo_micro_execute_exposed"] is False
            assert manifest["safety"]["raw_mt5_probe_exposed"] is False
            assert manifest["safety"]["metatrader5_imported"] is False
            assert manifest["safety"]["raw_evidence_included"] is False
            assert manifest["safety"]["credentials_included"] is False
            assert manifest["safety"]["env_file_included"] is False
        finally:
            builder.OUTPUT_DIR = old_output

    def test_03_first_run_readme_writes(self, tmp_path, monkeypatch):
        import scripts.release.build_windows_rc_package as builder
        old_output = builder.OUTPUT_DIR
        builder.OUTPUT_DIR = tmp_path / "TITAN_XAU_AI_RC"
        try:
            result = builder.build_package()
            readme = (tmp_path / "TITAN_XAU_AI_RC" / "README_FIRST_RUN.md").read_text(encoding="utf-8")
            assert "First-Run Instructions" in readme
            assert "run_titan_first_run.bat" in readme
            assert "run_titan_operator.bat" in readme
            assert "BLOCKED" in readme or "BLOCKED".lower() in readme.lower()
        finally:
            builder.OUTPUT_DIR = old_output

    def test_04_safety_notice_writes(self, tmp_path, monkeypatch):
        import scripts.release.build_windows_rc_package as builder
        old_output = builder.OUTPUT_DIR
        builder.OUTPUT_DIR = tmp_path / "TITAN_XAU_AI_RC"
        try:
            result = builder.build_package()
            notice = (tmp_path / "TITAN_XAU_AI_RC" / "SAFETY_NOTICE.md").read_text(encoding="utf-8")
            assert "Safety Notice" in notice
            assert "BLOCKED" in notice
            assert "DEMO_MICRO_EXECUTE" in notice
            assert "MetaTrader5" in notice
            assert "credentials" in notice.lower()
        finally:
            builder.OUTPUT_DIR = old_output


class TestExclusions:
    def test_05_raw_evidence_not_copied(self, tmp_path, monkeypatch):
        """Raw evidence files must NOT be in the package."""
        import scripts.release.build_windows_rc_package as builder
        old_output = builder.OUTPUT_DIR
        builder.OUTPUT_DIR = tmp_path / "TITAN_XAU_AI_RC"
        try:
            result = builder.build_package()
            # Walk the package and check no raw evidence files
            for path in (tmp_path / "TITAN_XAU_AI_RC").rglob("*"):
                if path.is_file():
                    rel = str(path.relative_to(tmp_path / "TITAN_XAU_AI_RC")).replace("\\", "/")
                    assert "demo_micro_journal.jsonl" not in rel, f"Raw journal in package: {rel}"
                    assert "demo_micro_repeatability_journal.jsonl" not in rel, f"Raw journal in package: {rel}"
                    assert "raw_mt5_working_profile.json" not in rel, f"Raw profile in package: {rel}"
                    assert "broker_execution_profile.json" not in rel, f"Raw profile in package: {rel}"
                    assert "pass_evidence" not in rel, f"Pass evidence in package: {rel}"
        finally:
            builder.OUTPUT_DIR = old_output

    def test_06_env_file_not_copied(self, tmp_path, monkeypatch):
        """.env files must NOT be in the package."""
        import scripts.release.build_windows_rc_package as builder
        old_output = builder.OUTPUT_DIR
        builder.OUTPUT_DIR = tmp_path / "TITAN_XAU_AI_RC"
        try:
            result = builder.build_package()
            for path in (tmp_path / "TITAN_XAU_AI_RC").rglob("*"):
                if path.is_file():
                    rel = str(path.relative_to(tmp_path / "TITAN_XAU_AI_RC"))
                    assert not rel.endswith(".env"), f".env file in package: {rel}"
                    assert not rel.endswith(".env.local"), f".env.local file in package: {rel}"
                    assert "mt5_credentials" not in rel, f"Credentials file in package: {rel}"
        finally:
            builder.OUTPUT_DIR = old_output

    def test_07_api_keys_not_copied(self, tmp_path, monkeypatch):
        """No API key files in the package."""
        import scripts.release.build_windows_rc_package as builder
        old_output = builder.OUTPUT_DIR
        builder.OUTPUT_DIR = tmp_path / "TITAN_XAU_AI_RC"
        try:
            result = builder.build_package()
            for path in (tmp_path / "TITAN_XAU_AI_RC").rglob("*"):
                if path.is_file():
                    rel = str(path.relative_to(tmp_path / "TITAN_XAU_AI_RC")).lower()
                    assert "api_key" not in rel, f"API key file in package: {rel}"
                    assert "credentials" not in rel or "credentials" in rel and "registry" in rel, \
                        f"Credentials file in package: {rel}"
        finally:
            builder.OUTPUT_DIR = old_output


class TestPackageContents:
    def test_08_operator_batch_included(self, tmp_path, monkeypatch):
        import scripts.release.build_windows_rc_package as builder
        old_output = builder.OUTPUT_DIR
        builder.OUTPUT_DIR = tmp_path / "TITAN_XAU_AI_RC"
        try:
            result = builder.build_package()
            assert (tmp_path / "TITAN_XAU_AI_RC" / "run_titan_operator.bat").exists()
        finally:
            builder.OUTPUT_DIR = old_output

    def test_09_first_run_batch_included(self, tmp_path, monkeypatch):
        import scripts.release.build_windows_rc_package as builder
        old_output = builder.OUTPUT_DIR
        builder.OUTPUT_DIR = tmp_path / "TITAN_XAU_AI_RC"
        try:
            result = builder.build_package()
            assert (tmp_path / "TITAN_XAU_AI_RC" / "run_titan_first_run.bat").exists()
        finally:
            builder.OUTPUT_DIR = old_output

    def test_10_operator_cli_included(self, tmp_path, monkeypatch):
        import scripts.release.build_windows_rc_package as builder
        old_output = builder.OUTPUT_DIR
        builder.OUTPUT_DIR = tmp_path / "TITAN_XAU_AI_RC"
        try:
            result = builder.build_package()
            assert (tmp_path / "TITAN_XAU_AI_RC" / "scripts" / "operator" / "titan_operator.py").exists()
            assert (tmp_path / "TITAN_XAU_AI_RC" / "scripts" / "operator" / "titan_first_run.py").exists()
        finally:
            builder.OUTPUT_DIR = old_output

    def test_11_docs_included(self, tmp_path, monkeypatch):
        import scripts.release.build_windows_rc_package as builder
        old_output = builder.OUTPUT_DIR
        builder.OUTPUT_DIR = tmp_path / "TITAN_XAU_AI_RC"
        try:
            result = builder.build_package()
            assert (tmp_path / "TITAN_XAU_AI_RC" / "docs" / "operator" / "operator_control_console.md").exists()
            assert (tmp_path / "TITAN_XAU_AI_RC" / "docs" / "release" / "windows_rc_package_guide.md").exists()
            assert (tmp_path / "TITAN_XAU_AI_RC" / "docs" / "audit" / "master_integration_gap_report.md").exists()
        finally:
            builder.OUTPUT_DIR = old_output


class TestSafetyInvariants:
    def test_12_no_metatrader5_import_in_builder(self):
        import scripts.release.build_windows_rc_package as builder
        src = inspect.getsource(builder)
        assert "import MetaTrader5" not in src
        assert "from MetaTrader5" not in src

    def test_13_no_order_send_in_builder(self):
        import re
        import scripts.release.build_windows_rc_package as builder
        src = inspect.getsource(builder)
        src = re.sub(r'"""[\s\S]*?"""', '""', src)
        src = re.sub(r"'''[\s\S]*?'''", "''", src)
        src = re.sub(r'"(?:[^"\\]|\\.)*"', '""', src)
        src = re.sub(r"'(?:[^'\\]|\\.)*'", "''", src)
        call_pattern = r"\bmt5\.order_send\s*\("
        matches = re.findall(call_pattern, src)
        assert len(matches) == 0, f"Found order_send calls: {matches}"

    def test_14_no_mt5_execution_adapter_in_builder(self):
        import re
        import scripts.release.build_windows_rc_package as builder
        src = inspect.getsource(builder)
        src = re.sub(r'"""[\s\S]*?"""', '""', src)
        src = re.sub(r"'''[\s\S]*?'''", "''", src)
        src = re.sub(r'"(?:[^"\\]|\\.)*"', '""', src)
        src = re.sub(r"'(?:[^'\\]|\\.)*'", "''", src)
        call_pattern = r"\b(MT5ExecutionAdapter|adapter\.send_open_order|adapter\.send_order)\s*\("
        matches = re.findall(call_pattern, src)
        assert len(matches) == 0, f"Found adapter calls: {matches}"

    def test_15_no_demo_micro_execute_in_builder(self):
        import re
        import scripts.release.build_windows_rc_package as builder
        src = inspect.getsource(builder)
        src = re.sub(r'"""[\s\S]*?"""', '""', src)
        src = re.sub(r"'''[\s\S]*?'''", "''", src)
        src = re.sub(r'"(?:[^"\\]|\\.)*"', '""', src)
        src = re.sub(r"'(?:[^'\\]|\\.)*'", "''", src)
        call_pattern = r"\b(DEMO_MICRO_EXECUTE|run_demo_micro|execute_demo_micro)\s*\("
        matches = re.findall(call_pattern, src)
        assert len(matches) == 0, f"Found demo micro execute calls: {matches}"
