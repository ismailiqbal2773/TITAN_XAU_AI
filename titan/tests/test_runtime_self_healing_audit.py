"""TITAN XAU AI - Sprint 9.9.3.43 Runtime Self-Healing Audit Tests"""
from __future__ import annotations
import inspect, json, re, sys
from pathlib import Path
import pytest
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

class TestSelfHealingAudit:
    def test_01_json_writes(self, tmp_path):
        import scripts.audit.runtime_self_healing_audit as sh
        old_d, old_j, old_m = sh.OUTPUT_DIR, sh.JSON_PATH, sh.MD_PATH
        sh.OUTPUT_DIR = tmp_path; sh.JSON_PATH = tmp_path / "sh.json"; sh.MD_PATH = tmp_path / "sh.md"
        try:
            result = sh.run_audit(); report = sh.write_report(result)
            assert Path(report["json_path"]).exists()
            with open(report["json_path"]) as f: data = json.load(f)
            assert "verdict" in data and "ok_checks" in data
        finally: sh.OUTPUT_DIR, sh.JSON_PATH, sh.MD_PATH = old_d, old_j, old_m

    def test_02_md_writes(self, tmp_path):
        import scripts.audit.runtime_self_healing_audit as sh
        old_d, old_j, old_m = sh.OUTPUT_DIR, sh.JSON_PATH, sh.MD_PATH
        sh.OUTPUT_DIR = tmp_path; sh.JSON_PATH = tmp_path / "sh.json"; sh.MD_PATH = tmp_path / "sh.md"
        try:
            result = sh.run_audit(); report = sh.write_report(result)
            md = Path(report["md_path"]).read_text()
            assert "Self-Healing Audit" in md
            # The MD should NOT contain false claims (but may contain "does NOT claim")
            # Check the actual assertion text doesn't falsely claim
            lines = md.splitlines()
            for line in lines:
                stripped = line.strip()
                if "crash impossible" in stripped.lower() and "not" not in stripped.lower() and "does not" not in stripped.lower():
                    pytest.fail(f"MD falsely claims crash impossible: {stripped}")
        finally: sh.OUTPUT_DIR, sh.JSON_PATH, sh.MD_PATH = old_d, old_j, old_m

    def test_03_verdict_in_valid_set(self):
        import scripts.audit.runtime_self_healing_audit as sh
        result = sh.run_audit()
        assert result["verdict"] in ("SELF_HEALING_READY","SELF_HEALING_READY_WITH_WARNINGS","SELF_HEALING_BLOCKED")

    def test_04_does_not_claim_crash_impossible(self):
        import scripts.audit.runtime_self_healing_audit as sh
        result = sh.run_audit()
        # The result should not contain "crash impossible" as a positive claim
        # It may contain it in a negation context ("does NOT claim crash impossible")
        result_str = str(result).lower()
        # Check that "crash impossible" only appears in negation context
        if "crash impossible" in result_str:
            # Must be preceded by "not" or "does not"
            idx = result_str.find("crash impossible")
            context = result_str[max(0, idx-30):idx]
            assert "not" in context, "Result claims crash impossible without negation"
        assert "Crash-tolerant fail-closed" in result["design_description"]

    def test_05_no_metatrader5_import(self):
        src = inspect.getsource(__import__("scripts.audit.runtime_self_healing_audit", fromlist=["x"]))
        assert "import MetaTrader5" not in src and "from MetaTrader5" not in src
