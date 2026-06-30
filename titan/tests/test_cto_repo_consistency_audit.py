"""TITAN XAU AI - Sprint 9.9.3.41.2 CTO Repo Consistency Audit Tests"""
from __future__ import annotations
import inspect, json, re, sys
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


class TestReportWriter:
    def test_01_json_writes(self, tmp_path):
        import scripts.audit.cto_repo_consistency_audit as audit
        old_dir, old_json, old_md = audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH
        audit.OUTPUT_DIR = tmp_path
        audit.JSON_PATH = tmp_path / "audit.json"
        audit.MD_PATH = tmp_path / "audit.md"
        try:
            result = audit.write_report()
            assert Path(result["json_path"]).exists()
            with open(result["json_path"]) as f:
                data = json.load(f)
            assert "verdict" in data
            assert "head_short" in data
            assert "audits" in data
            assert "blockers" in data
            assert "warnings" in data
        finally:
            audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH = old_dir, old_json, old_md

    def test_02_md_writes(self, tmp_path):
        import scripts.audit.cto_repo_consistency_audit as audit
        old_dir, old_json, old_md = audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH
        audit.OUTPUT_DIR = tmp_path
        audit.JSON_PATH = tmp_path / "audit.json"
        audit.MD_PATH = tmp_path / "audit.md"
        try:
            result = audit.write_report()
            md = Path(result["md_path"]).read_text(encoding="utf-8")
            assert "CTO Repo Consistency Audit" in md
            assert "Audit Results" in md
        finally:
            audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH = old_dir, old_json, old_md

    def test_03_head_commit_included(self, tmp_path):
        import scripts.audit.cto_repo_consistency_audit as audit
        old_dir, old_json, old_md = audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH
        audit.OUTPUT_DIR = tmp_path
        audit.JSON_PATH = tmp_path / "audit.json"
        audit.MD_PATH = tmp_path / "audit.md"
        try:
            result = audit.write_report()
            with open(result["json_path"]) as f:
                data = json.load(f)
            assert data["head_short"]
            assert len(data["head_short"]) >= 7
        finally:
            audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH = old_dir, old_json, old_md

    def test_04_all_audit_areas_present(self, tmp_path):
        import scripts.audit.cto_repo_consistency_audit as audit
        old_dir, old_json, old_md = audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH
        audit.OUTPUT_DIR = tmp_path
        audit.JSON_PATH = tmp_path / "audit.json"
        audit.MD_PATH = tmp_path / "audit.md"
        try:
            result = audit.write_report()
            with open(result["json_path"]) as f:
                data = json.load(f)
            required = [
                "duplicate_modules", "stale_todos", "hardcoded_broker_refs",
                "regime_placeholder", "dynamic_risk_sticky", "trade_loop_caution",
                "package_truth", "broker_gate_limitation", "safe_path_exposure",
                "rc_truth",
            ]
            for name in required:
                assert name in data["audits"], f"Missing audit area: {name}"
        finally:
            audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH = old_dir, old_json, old_md

    def test_05_verdict_in_valid_set(self, tmp_path):
        import scripts.audit.cto_repo_consistency_audit as audit
        old_dir, old_json, old_md = audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH
        audit.OUTPUT_DIR = tmp_path
        audit.JSON_PATH = tmp_path / "audit.json"
        audit.MD_PATH = tmp_path / "audit.md"
        try:
            result = audit.write_report()
            assert result["verdict"] in ("CTO_READY", "CTO_READY_WITH_WARNINGS", "CTO_BLOCKED")
        finally:
            audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH = old_dir, old_json, old_md


class TestStaleTodoDetection:
    def test_06_stale_todos_removed_from_bridge(self):
        """Sprint 9.9.3.41.2: stale TODOs removed from signal_execution_bridge.py."""
        bridge_src = (REPO_ROOT / "titan" / "production" / "signal_execution_bridge.py").read_text()
        stale = re.findall(r"# TODO.*Wire into (TradeLoop|InferenceEngine|DynamicRiskEngine|RuntimeHealthMonitor|BrokerCompatibilityMatrix|SecurityGate|RegimeDetection)", bridge_src)
        assert len(stale) == 0, f"Stale TODOs found: {stale}"

    def test_07_bridge_has_integration_status_comment(self):
        """Bridge should have 'Already wired into AutonomousRuntime' comment."""
        bridge_src = (REPO_ROOT / "titan" / "production" / "signal_execution_bridge.py").read_text()
        assert "Already wired into AutonomousRuntime" in bridge_src or \
               "already wired" in bridge_src.lower()


class TestRegimePlaceholderWarning:
    def test_08_cto_audit_reports_regime_placeholder(self, tmp_path):
        """CTO audit must report regime placeholder warning."""
        import scripts.audit.cto_repo_consistency_audit as audit
        old_dir, old_json, old_md = audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH
        audit.OUTPUT_DIR = tmp_path
        audit.JSON_PATH = tmp_path / "audit.json"
        audit.MD_PATH = tmp_path / "audit.md"
        try:
            result = audit.write_report()
            with open(result["json_path"]) as f:
                data = json.load(f)
            regime_audit = data["audits"]["regime_placeholder"]
            # Should have a warning about placeholder context
            has_placeholder_warning = any("PLACEHOLDER_CONTEXT" in w for w in regime_audit.get("warnings", []))
            assert has_placeholder_warning, "Regime placeholder warning not found"
        finally:
            audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH = old_dir, old_json, old_md


class TestPackageTruth:
    def test_09_package_truth_overlay_not_standalone(self, tmp_path):
        """CTO audit must report package as overlay, not standalone."""
        import scripts.audit.cto_repo_consistency_audit as audit
        old_dir, old_json, old_md = audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH
        audit.OUTPUT_DIR = tmp_path
        audit.JSON_PATH = tmp_path / "audit.json"
        audit.MD_PATH = tmp_path / "audit.md"
        try:
            result = audit.write_report()
            with open(result["json_path"]) as f:
                data = json.load(f)
            package_audit = data["audits"]["package_truth"]
            # Should have OK check about overlay truth
            has_overlay_ok = any("OPERATOR_OVERLAY_NOT_STANDALONE" in c for c in package_audit.get("ok_checks", []))
            assert has_overlay_ok, "Package overlay truth not verified"
        finally:
            audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH = old_dir, old_json, old_md


class TestSafetyInvariants:
    def test_10_no_metatrader5_import_in_cto_audit(self):
        import re
        import scripts.audit.cto_repo_consistency_audit as audit
        src = inspect.getsource(audit)
        # Strip strings/comments to check actual code only
        src = re.sub(r'"""[\s\S]*?"""', '""', src)
        src = re.sub(r"'''[\s\S]*?'''", "''", src)
        src = re.sub(r'r"[^"]*"', '""', src)
        src = re.sub(r"r'[^']*'", "''", src)
        src = re.sub(r'"(?:[^"\\]|\\.)*"', '""', src)
        src = re.sub(r"'(?:[^'\\]|\\.)*'", "''", src)
        # Strip line comments
        lines = []
        for line in src.splitlines():
            idx = line.find("#")
            if idx >= 0:
                line = line[:idx]
            lines.append(line)
        src = "\n".join(lines)
        assert "import MetaTrader5" not in src
        assert "from MetaTrader5" not in src

    def test_11_no_order_send_in_cto_audit(self):
        import re
        import scripts.audit.cto_repo_consistency_audit as audit
        src = inspect.getsource(audit)
        src = re.sub(r'"""[\s\S]*?"""', '""', src)
        src = re.sub(r"'''[\s\S]*?'''", "''", src)
        src = re.sub(r'r"[^"]*"', '""', src)
        src = re.sub(r"r'[^']*'", "''", src)
        src = re.sub(r'"(?:[^"\\]|\\.)*"', '""', src)
        src = re.sub(r"'(?:[^'\\]|\\.)*'", "''", src)
        call_pattern = r"\bmt5\.order_send\s*\("
        matches = re.findall(call_pattern, src)
        assert len(matches) == 0

    def test_12_no_demo_micro_execute_in_cto_audit(self):
        import re
        import scripts.audit.cto_repo_consistency_audit as audit
        src = inspect.getsource(audit)
        src = re.sub(r'"""[\s\S]*?"""', '""', src)
        src = re.sub(r"'''[\s\S]*?'''", "''", src)
        src = re.sub(r'r"[^"]*"', '""', src)
        src = re.sub(r"r'[^']*'", "''", src)
        src = re.sub(r'"(?:[^"\\]|\\.)*"', '""', src)
        src = re.sub(r"'(?:[^'\\]|\\.)*'", "''", src)
        call_pattern = r"(?<!['\"])\b(DEMO_MICRO_EXECUTE|run_demo_micro|execute_demo_micro)\s*\("
        matches = re.findall(call_pattern, src)
        assert len(matches) == 0
