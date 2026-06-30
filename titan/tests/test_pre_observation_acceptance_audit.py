"""TITAN XAU AI - Sprint 9.9.3.41 Pre-Observation Acceptance Audit Tests"""
from __future__ import annotations
import inspect, json, re, sys
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


class TestReportWriter:
    def test_01_json_writes(self, tmp_path):
        import scripts.audit.pre_observation_acceptance_audit as audit
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
            assert "sprint_module_inventory" in data
            assert "runtime_chain_audit" in data
            assert "logical_contradiction_audit" in data
            assert "mathematical_consistency_audit" in data
            assert "configuration_consistency_audit" in data
            assert "windows_rc_package_safety_audit" in data
            assert "demo_monitoring_readiness_audit" in data
            assert "blockers" in data
            assert "warnings" in data
            assert "recommended_next_sprint" in data
            assert "safety" in data
        finally:
            audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH = old_dir, old_json, old_md

    def test_02_md_writes(self, tmp_path):
        import scripts.audit.pre_observation_acceptance_audit as audit
        old_dir, old_json, old_md = audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH
        audit.OUTPUT_DIR = tmp_path
        audit.JSON_PATH = tmp_path / "audit.json"
        audit.MD_PATH = tmp_path / "audit.md"
        try:
            result = audit.write_report()
            md = Path(result["md_path"]).read_text(encoding="utf-8")
            assert "Pre-Observation Acceptance Audit" in md
            assert "Sprint/Module Inventory" in md
            assert "Runtime Chain Audit" in md
            assert "Logical Contradiction Audit" in md
            assert "Mathematical Consistency Audit" in md
            assert "Configuration Consistency Audit" in md
            assert "Windows RC Package Safety Audit" in md
            assert "Demo Monitoring Readiness Audit" in md
            assert "Recommended Next Sprint" in md
        finally:
            audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH = old_dir, old_json, old_md

    def test_03_current_head_commit_included(self, tmp_path):
        import scripts.audit.pre_observation_acceptance_audit as audit
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

    def test_04_all_major_modules_appear(self, tmp_path):
        import scripts.audit.pre_observation_acceptance_audit as audit
        old_dir, old_json, old_md = audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH
        audit.OUTPUT_DIR = tmp_path
        audit.JSON_PATH = tmp_path / "audit.json"
        audit.MD_PATH = tmp_path / "audit.md"
        try:
            result = audit.write_report()
            with open(result["json_path"]) as f:
                data = json.load(f)
            inventory = data["sprint_module_inventory"]["inventory"]
            inventory_names = {i["name"] for i in inventory}
            required = [
                "SignalExecutionBridge",
                "RegimeDetection",
                "BrokerCompatibilityMatrix",
                "RuntimeHealthMonitor",
                "SecurityGate",
                "PositionLifecycleEngine",
                "ExitIntentBridge",
                "ForwardObservationEngine",
                "ObservationScorecardEngine",
                "OperatorControlConsole",
                "ProductionRuntimeAssembly",
                "FirstRunWizard",
            ]
            for name in required:
                assert name in inventory_names, f"Missing module in inventory: {name}"
        finally:
            audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH = old_dir, old_json, old_md

    def test_05_runtime_chain_matrix_exists(self, tmp_path):
        import scripts.audit.pre_observation_acceptance_audit as audit
        old_dir, old_json, old_md = audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH
        audit.OUTPUT_DIR = tmp_path
        audit.JSON_PATH = tmp_path / "audit.json"
        audit.MD_PATH = tmp_path / "audit.md"
        try:
            result = audit.write_report()
            with open(result["json_path"]) as f:
                data = json.load(f)
            chain = data["runtime_chain_audit"]
            assert len(chain) > 0
            for link, status in chain.items():
                assert status in ("PRESENT", "PARTIAL", "ABSENT", "CONTRADICTORY"), \
                    f"Invalid chain status {status} for link {link}"
        finally:
            audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH = old_dir, old_json, old_md

    def test_06_contradiction_audit_exists(self, tmp_path):
        import scripts.audit.pre_observation_acceptance_audit as audit
        old_dir, old_json, old_md = audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH
        audit.OUTPUT_DIR = tmp_path
        audit.JSON_PATH = tmp_path / "audit.json"
        audit.MD_PATH = tmp_path / "audit.md"
        try:
            result = audit.write_report()
            with open(result["json_path"]) as f:
                data = json.load(f)
            c = data["logical_contradiction_audit"]
            assert "contradictions" in c
            assert "contradiction_count" in c
        finally:
            audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH = old_dir, old_json, old_md

    def test_07_math_audit_exists(self, tmp_path):
        import scripts.audit.pre_observation_acceptance_audit as audit
        old_dir, old_json, old_md = audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH
        audit.OUTPUT_DIR = tmp_path
        audit.JSON_PATH = tmp_path / "audit.json"
        audit.MD_PATH = tmp_path / "audit.md"
        try:
            result = audit.write_report()
            with open(result["json_path"]) as f:
                data = json.load(f)
            m = data["mathematical_consistency_audit"]
            assert "ok_checks" in m
            assert "issues" in m
        finally:
            audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH = old_dir, old_json, old_md

    def test_08_config_audit_exists(self, tmp_path):
        import scripts.audit.pre_observation_acceptance_audit as audit
        old_dir, old_json, old_md = audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH
        audit.OUTPUT_DIR = tmp_path
        audit.JSON_PATH = tmp_path / "audit.json"
        audit.MD_PATH = tmp_path / "audit.md"
        try:
            result = audit.write_report()
            with open(result["json_path"]) as f:
                data = json.load(f)
            c = data["configuration_consistency_audit"]
            assert "ok_checks" in c
            assert "issues" in c
        finally:
            audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH = old_dir, old_json, old_md

    def test_09_windows_rc_package_safety_audit_exists(self, tmp_path):
        import scripts.audit.pre_observation_acceptance_audit as audit
        old_dir, old_json, old_md = audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH
        audit.OUTPUT_DIR = tmp_path
        audit.JSON_PATH = tmp_path / "audit.json"
        audit.MD_PATH = tmp_path / "audit.md"
        try:
            result = audit.write_report()
            with open(result["json_path"]) as f:
                data = json.load(f)
            p = data["windows_rc_package_safety_audit"]
            assert "ok_checks" in p
            assert "issues" in p
        finally:
            audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH = old_dir, old_json, old_md

    def test_10_monitoring_readiness_audit_exists(self, tmp_path):
        import scripts.audit.pre_observation_acceptance_audit as audit
        old_dir, old_json, old_md = audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH
        audit.OUTPUT_DIR = tmp_path
        audit.JSON_PATH = tmp_path / "audit.json"
        audit.MD_PATH = tmp_path / "audit.md"
        try:
            result = audit.write_report()
            with open(result["json_path"]) as f:
                data = json.load(f)
            m = data["demo_monitoring_readiness_audit"]
            assert "ok_checks" in m
            assert "issues" in m
        finally:
            audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH = old_dir, old_json, old_md

    def test_11_go_no_go_verdict_exists(self, tmp_path):
        import scripts.audit.pre_observation_acceptance_audit as audit
        old_dir, old_json, old_md = audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH
        audit.OUTPUT_DIR = tmp_path
        audit.JSON_PATH = tmp_path / "audit.json"
        audit.MD_PATH = tmp_path / "audit.md"
        try:
            result = audit.write_report()
            assert result["verdict"] in (
                "DEMO_OBSERVATION_READY",
                "DEMO_OBSERVATION_READY_WITH_WARNINGS",
                "DEMO_OBSERVATION_BLOCKED",
            )
        finally:
            audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH = old_dir, old_json, old_md

    def test_12_recommended_next_sprint_exists(self, tmp_path):
        import scripts.audit.pre_observation_acceptance_audit as audit
        old_dir, old_json, old_md = audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH
        audit.OUTPUT_DIR = tmp_path
        audit.JSON_PATH = tmp_path / "audit.json"
        audit.MD_PATH = tmp_path / "audit.md"
        try:
            result = audit.write_report()
            with open(result["json_path"]) as f:
                data = json.load(f)
            assert data["recommended_next_sprint"]
            assert "Sprint" in data["recommended_next_sprint"]
        finally:
            audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH = old_dir, old_json, old_md


class TestBlockingConditions:
    """Test that the audit correctly blocks on critical conditions."""

    def test_13_live_trading_exposed_causes_blocked(self, tmp_path, monkeypatch):
        """If live_trading: true appears in runtime section, verdict must be BLOCKED."""
        import scripts.audit.pre_observation_acceptance_audit as audit
        # Patch the RUNTIME_YAML to have live_trading: true in the runtime section
        original_yaml = audit.RUNTIME_YAML
        patched_yaml = original_yaml.replace(
            "live_trading: false",
            "live_trading: true",
        )
        monkeypatch.setattr(audit, "RUNTIME_YAML", patched_yaml)
        old_dir, old_json, old_md = audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH
        audit.OUTPUT_DIR = tmp_path
        audit.JSON_PATH = tmp_path / "audit.json"
        audit.MD_PATH = tmp_path / "audit.md"
        try:
            result = audit.write_report()
            assert result["verdict"] == "DEMO_OBSERVATION_BLOCKED"
            assert any("live_trading" in b for b in json.load(open(result["json_path"]))["blockers"])
        finally:
            audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH = old_dir, old_json, old_md

    def test_14_lot_cap_above_001_causes_blocked(self, tmp_path, monkeypatch):
        """If max_lot > 0.01 in risk section, verdict must be BLOCKED."""
        import scripts.audit.pre_observation_acceptance_audit as audit
        original_yaml = audit.RUNTIME_YAML
        patched_yaml = original_yaml.replace(
            "max_lot: 0.01",
            "max_lot: 0.10",
        )
        monkeypatch.setattr(audit, "RUNTIME_YAML", patched_yaml)
        old_dir, old_json, old_md = audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH
        audit.OUTPUT_DIR = tmp_path
        audit.JSON_PATH = tmp_path / "audit.json"
        audit.MD_PATH = tmp_path / "audit.md"
        try:
            result = audit.write_report()
            assert result["verdict"] == "DEMO_OBSERVATION_BLOCKED"
        finally:
            audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH = old_dir, old_json, old_md

    def test_15_max_positions_above_1_causes_blocked(self, tmp_path, monkeypatch):
        """If max_open_positions > 1 in risk section, verdict must be BLOCKED."""
        import scripts.audit.pre_observation_acceptance_audit as audit
        original_yaml = audit.RUNTIME_YAML
        patched_yaml = original_yaml.replace(
            "max_open_positions: 1",
            "max_open_positions: 5",
        )
        monkeypatch.setattr(audit, "RUNTIME_YAML", patched_yaml)
        old_dir, old_json, old_md = audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH
        audit.OUTPUT_DIR = tmp_path
        audit.JSON_PATH = tmp_path / "audit.json"
        audit.MD_PATH = tmp_path / "audit.md"
        try:
            result = audit.write_report()
            assert result["verdict"] == "DEMO_OBSERVATION_BLOCKED"
        finally:
            audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH = old_dir, old_json, old_md

    def test_16_unsafe_windows_package_command_causes_blocked(self, tmp_path, monkeypatch):
        """If operator batch exposes unsafe command, verdict must be BLOCKED."""
        import scripts.audit.pre_observation_acceptance_audit as audit
        # Patch OPERATOR_BATCH to include an unsafe PYTHON line
        unsafe_batch = audit.OPERATOR_BATCH + '\npython "%TITAN_HOME%scripts\\audit\\demo_micro_full_cycle.py"\n'
        monkeypatch.setattr(audit, "OPERATOR_BATCH", unsafe_batch)
        old_dir, old_json, old_md = audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH
        audit.OUTPUT_DIR = tmp_path
        audit.JSON_PATH = tmp_path / "audit.json"
        audit.MD_PATH = tmp_path / "audit.md"
        try:
            result = audit.write_report()
            assert result["verdict"] == "DEMO_OBSERVATION_BLOCKED"
            assert any("unsafe" in b.lower() or "demo_micro" in b.lower() for b in json.load(open(result["json_path"]))["blockers"])
        finally:
            audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH = old_dir, old_json, old_md

    def test_17_missing_journal_results_in_warning_not_pass(self, tmp_path):
        """Verify the audit recognizes INSUFFICIENT_DATA handling in scorecard."""
        import scripts.audit.pre_observation_acceptance_audit as audit
        # The observation_scorecard.py must contain INSUFFICIENT_DATA
        scorecard_src = (REPO_ROOT / "titan" / "production" / "observation_scorecard.py").read_text()
        assert "INSUFFICIENT_DATA" in scorecard_src, \
            "Observation scorecard must handle INSUFFICIENT_DATA when no journal events"


class TestSafetyInvariants:
    def test_18_no_metatrader5_import_in_audit_module(self):
        import re
        import scripts.audit.pre_observation_acceptance_audit as audit
        src = inspect.getsource(audit)
        # Strip strings/comments to check actual code only
        src = re.sub(r'"""[\s\S]*?"""', '""', src)
        src = re.sub(r"'''[\s\S]*?'''", "''", src)
        src = re.sub(r'r"[^"]*"', '""', src)
        src = re.sub(r"r'[^']*'", "''", src)
        src = re.sub(r'"(?:[^"\\]|\\.)*"', '""', src)
        src = re.sub(r"'(?:[^'\\]|\\.)*'", "''", src)
        # Strip line comments
        out_lines = []
        for line in src.splitlines():
            idx = line.find("#")
            if idx >= 0:
                line = line[:idx]
            out_lines.append(line)
        src = "\n".join(out_lines)
        # No actual import statement (string literal mentions are OK)
        assert "import MetaTrader5" not in src
        assert "from MetaTrader5" not in src

    def test_19_no_order_send_in_audit_module(self):
        import re
        import scripts.audit.pre_observation_acceptance_audit as audit
        src = inspect.getsource(audit)
        src = re.sub(r'"""[\s\S]*?"""', '""', src)
        src = re.sub(r"'''[\s\S]*?'''", "''", src)
        src = re.sub(r'r"[^"]*"', '""', src)
        src = re.sub(r"r'[^']*'", "''", src)
        src = re.sub(r'"(?:[^"\\]|\\.)*"', '""', src)
        src = re.sub(r"'(?:[^'\\]|\\.)*'", "''", src)
        call_pattern = r"\bmt5\.order_send\s*\("
        matches = re.findall(call_pattern, src)
        assert len(matches) == 0, f"Found order_send calls: {matches}"

    def test_20_no_demo_micro_execute_in_audit_module(self):
        import re
        import scripts.audit.pre_observation_acceptance_audit as audit
        src = inspect.getsource(audit)
        src = re.sub(r'"""[\s\S]*?"""', '""', src)
        src = re.sub(r"'''[\s\S]*?'''", "''", src)
        src = re.sub(r'r"[^"]*"', '""', src)
        src = re.sub(r"r'[^']*'", "''", src)
        src = re.sub(r'"(?:[^"\\]|\\.)*"', '""', src)
        src = re.sub(r"'(?:[^'\\]|\\.)*'", "''", src)
        call_pattern = r"(?<!['\"])\b(DEMO_MICRO_EXECUTE|run_demo_micro|execute_demo_micro)\s*\("
        matches = re.findall(call_pattern, src)
        assert len(matches) == 0, f"Found demo micro execute calls: {matches}"

    def test_21_no_credentials_requested_in_audit_module(self):
        """Audit module must never call input() to ask for credentials."""
        import re
        import scripts.audit.pre_observation_acceptance_audit as audit
        src = inspect.getsource(audit)
        src = re.sub(r'"""[\s\S]*?"""', '""', src)
        src = re.sub(r"'''[\s\S]*?'''", "''", src)
        src = re.sub(r'r"[^"]*"', '""', src)
        src = re.sub(r"r'[^']*'", "''", src)
        src = re.sub(r'"(?:[^"\\]|\\.)*"', '""', src)
        src = re.sub(r"'(?:[^'\\]|\\.)*'", "''", src)
        assert "input(" not in src
        assert "getpass" not in src

    def test_22_audit_does_not_import_runtime_modules(self):
        """Audit should not import autonomous_loops or launcher (to avoid side effects)."""
        import scripts.audit.pre_observation_acceptance_audit as audit
        src = inspect.getsource(audit)
        assert "from titan.runtime" not in src
        assert "import titan.runtime" not in src
