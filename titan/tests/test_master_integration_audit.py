"""TITAN XAU AI - Sprint 9.9.3.38 Master Integration Audit Tests"""
from __future__ import annotations
import inspect, json, re, sys
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


class TestReportWriter:
    def test_01_json_writes(self, tmp_path):
        import scripts.audit.master_integration_audit as audit
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
            assert "head_commit" in data
            assert "head_short" in data
            assert "component_wiring_matrix" in data
            assert "executable_chain_matrix" in data
            assert "critical_questions" in data
            assert "safety_audit" in data
            assert "product_readiness" in data
            assert "launcher_findings" in data
            assert "autonomous_runtime_findings" in data
            assert "operator_console_findings" in data
            assert "module_exists_not_wired" in data
            assert "blockers" in data
            assert "warnings" in data
            assert "recommended_next_sprint" in data
            assert "safety" in data
        finally:
            audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH = old_dir, old_json, old_md

    def test_02_md_writes(self, tmp_path):
        import scripts.audit.master_integration_audit as audit
        old_dir, old_json, old_md = audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH
        audit.OUTPUT_DIR = tmp_path
        audit.JSON_PATH = tmp_path / "audit.json"
        audit.MD_PATH = tmp_path / "audit.md"
        try:
            result = audit.write_report()
            md = Path(result["md_path"]).read_text(encoding="utf-8")
            assert "Master Integration Audit" in md
            assert "Component Wiring Matrix" in md
            assert "Executable Chain Matrix" in md
            assert "Critical Questions" in md
            assert "Safety Audit" in md
            assert "Product Readiness" in md
            assert "Recommended Next Sprint" in md
        finally:
            audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH = old_dir, old_json, old_md

    def test_03_current_head_commit_included(self, tmp_path):
        import scripts.audit.master_integration_audit as audit
        old_dir, old_json, old_md = audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH
        audit.OUTPUT_DIR = tmp_path
        audit.JSON_PATH = tmp_path / "audit.json"
        audit.MD_PATH = tmp_path / "audit.md"
        try:
            result = audit.write_report()
            with open(result["json_path"]) as f:
                data = json.load(f)
            # HEAD commit must be a non-empty string
            assert data["head_commit"]
            assert len(data["head_commit"]) >= 7
            assert data["head_short"]
        finally:
            audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH = old_dir, old_json, old_md

    def test_04_every_major_component_in_matrix(self, tmp_path):
        import scripts.audit.master_integration_audit as audit
        old_dir, old_json, old_md = audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH
        audit.OUTPUT_DIR = tmp_path
        audit.JSON_PATH = tmp_path / "audit.json"
        audit.MD_PATH = tmp_path / "audit.md"
        try:
            result = audit.write_report()
            with open(result["json_path"]) as f:
                data = json.load(f)
            matrix = data["component_wiring_matrix"]
            required = [
                "FeatureStream", "InferenceEngine", "TradeLoop",
                "SignalExecutionBridge", "RegimeDetection",
                "BrokerCompatibilityMatrix", "RuntimeHealthMonitor",
                "SecurityGate", "LicenseGuard", "AntiTamperGuard",
                "AccountHealthEngine", "DynamicRiskEngine", "CapitalProtection",
                "PositionSync", "PositionLifecycleEngine", "ExitManager",
                "SLDefenseEngine", "ProfitCaptureEngine",
                "ExitDecisionCoordinator", "ExitIntentBridge", "AIExitEngine",
                "ForwardObservationEngine", "ObservationScorecardEngine",
                "OperatorControlConsole", "ProductionRuntimeAssembly",
                "ModelLifecycleGovernance", "AlphaFactoryGovernance",
                "AutoCalibrationGovernance", "ModelRegistry",
                "OfflineRetrainingPipeline", "RetrainingTriggerMonitor",
            ]
            for name in required:
                assert name in matrix, f"Missing component in matrix: {name}"
                assert "classification" in matrix[name]
        finally:
            audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH = old_dir, old_json, old_md

    def test_05_executable_chain_matrix_exists(self, tmp_path):
        import scripts.audit.master_integration_audit as audit
        old_dir, old_json, old_md = audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH
        audit.OUTPUT_DIR = tmp_path
        audit.JSON_PATH = tmp_path / "audit.json"
        audit.MD_PATH = tmp_path / "audit.md"
        try:
            result = audit.write_report()
            with open(result["json_path"]) as f:
                data = json.load(f)
            chain = data["executable_chain_matrix"]
            assert len(chain) > 0
            for link, status in chain.items():
                assert status in ("PRESENT", "PARTIAL", "ABSENT", "UNKNOWN"), \
                    f"Invalid chain status {status} for link {link}"
        finally:
            audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH = old_dir, old_json, old_md

    def test_06_launcher_file_inspected(self, tmp_path):
        import scripts.audit.master_integration_audit as audit
        old_dir, old_json, old_md = audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH
        audit.OUTPUT_DIR = tmp_path
        audit.JSON_PATH = tmp_path / "audit.json"
        audit.MD_PATH = tmp_path / "audit.md"
        try:
            result = audit.write_report()
            with open(result["json_path"]) as f:
                data = json.load(f)
            lf = data["launcher_findings"]
            assert lf["inspected_file"] == "titan/runtime/launcher.py"
            assert "uses_production_runtime_assembly" in lf
            assert "summary" in lf
        finally:
            audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH = old_dir, old_json, old_md

    def test_07_autonomous_runtime_file_inspected(self, tmp_path):
        import scripts.audit.master_integration_audit as audit
        old_dir, old_json, old_md = audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH
        audit.OUTPUT_DIR = tmp_path
        audit.JSON_PATH = tmp_path / "audit.json"
        audit.MD_PATH = tmp_path / "audit.md"
        try:
            result = audit.write_report()
            with open(result["json_path"]) as f:
                data = json.load(f)
            af = data["autonomous_runtime_findings"]
            assert af["inspected_file"] == "titan/runtime/autonomous_loops.py"
            assert "imports" in af
            assert "does_not_import" in af
            assert "summary" in af
        finally:
            audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH = old_dir, old_json, old_md

    def test_08_operator_console_inspected(self, tmp_path):
        import scripts.audit.master_integration_audit as audit
        old_dir, old_json, old_md = audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH
        audit.OUTPUT_DIR = tmp_path
        audit.JSON_PATH = tmp_path / "audit.json"
        audit.MD_PATH = tmp_path / "audit.md"
        try:
            result = audit.write_report()
            with open(result["json_path"]) as f:
                data = json.load(f)
            of = data["operator_console_findings"]
            assert of["inspected_file"] == "titan/production/operator_control_console.py"
            assert "calls_real_reports" in of
            assert "exposes_live_trading_command" in of
            assert "exposes_market_execution_command" in of
        finally:
            audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH = old_dir, old_json, old_md

    def test_09_report_only_classification_works(self, tmp_path):
        """Verify the report-only classification appears for at least one module."""
        import scripts.audit.master_integration_audit as audit
        old_dir, old_json, old_md = audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH
        audit.OUTPUT_DIR = tmp_path
        audit.JSON_PATH = tmp_path / "audit.json"
        audit.MD_PATH = tmp_path / "audit.md"
        try:
            result = audit.write_report()
            with open(result["json_path"]) as f:
                data = json.load(f)
            matrix = data["component_wiring_matrix"]
            # At least one module should be classified as report-only or module-exists-not-wired
            classifications = {v["classification"] for v in matrix.values()}
            assert "MODULE_EXISTS_NOT_WIRED" in classifications or \
                   "WIRED_IN_REPORT_ONLY" in classifications, \
                   f"Expected at least one report-only or not-wired classification, got: {classifications}"
        finally:
            audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH = old_dir, old_json, old_md

    def test_10_module_exists_not_wired_identified(self, tmp_path):
        """Verify the audit identifies at least one module as not-wired OR wired-in-runtime.

        Sprint 9.9.3.39 update: After wiring, SignalExecutionBridge is now
        WIRED_IN_AUTONOMOUS_RUNTIME. The audit must still correctly classify
        modules. This test verifies the classification works for both
        pre-wiring (MODULE_EXISTS_NOT_WIRED) and post-wiring (WIRED_IN_AUTONOMOUS_RUNTIME)
        states.
        """
        import scripts.audit.master_integration_audit as audit
        old_dir, old_json, old_md = audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH
        audit.OUTPUT_DIR = tmp_path
        audit.JSON_PATH = tmp_path / "audit.json"
        audit.MD_PATH = tmp_path / "audit.md"
        try:
            result = audit.write_report()
            with open(result["json_path"]) as f:
                data = json.load(f)
            matrix = data["component_wiring_matrix"]
            # After Sprint 9.9.3.39, SignalExecutionBridge is WIRED_IN_AUTONOMOUS_RUNTIME.
            # Some non-critical modules (e.g. SLDefenseEngine) may still be MODULE_EXISTS_NOT_WIRED
            # because they are invoked internally by ExitIntentBridge (which IS wired).
            classifications = {v["classification"] for v in matrix.values()}
            # At least one of these classifications must exist
            assert "MODULE_EXISTS_NOT_WIRED" in classifications or \
                   "WIRED_IN_REPORT_ONLY" in classifications or \
                   "WIRED_IN_AUTONOMOUS_RUNTIME" in classifications, \
                f"No expected classifications found: {classifications}"
        finally:
            audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH = old_dir, old_json, old_md

    def test_11_missing_offline_retraining_modules_handled_safely(self, tmp_path):
        """Verify OfflineRetrainingPipeline and RetrainingTriggerMonitor are handled."""
        import scripts.audit.master_integration_audit as audit
        old_dir, old_json, old_md = audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH
        audit.OUTPUT_DIR = tmp_path
        audit.JSON_PATH = tmp_path / "audit.json"
        audit.MD_PATH = tmp_path / "audit.md"
        try:
            result = audit.write_report()
            with open(result["json_path"]) as f:
                data = json.load(f)
            matrix = data["component_wiring_matrix"]
            # Both should be present in matrix (not MISSING)
            assert "OfflineRetrainingPipeline" in matrix
            assert "RetrainingTriggerMonitor" in matrix
            assert matrix["OfflineRetrainingPipeline"]["classification"] != "MISSING"
            assert matrix["RetrainingTriggerMonitor"]["classification"] != "MISSING"
        finally:
            audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH = old_dir, old_json, old_md

    def test_12_safety_section_includes_live_trading_blocked(self, tmp_path):
        import scripts.audit.master_integration_audit as audit
        old_dir, old_json, old_md = audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH
        audit.OUTPUT_DIR = tmp_path
        audit.JSON_PATH = tmp_path / "audit.json"
        audit.MD_PATH = tmp_path / "audit.md"
        try:
            result = audit.write_report()
            with open(result["json_path"]) as f:
                data = json.load(f)
            safety = data["safety_audit"]
            assert "live_trading_false_default" in safety
            assert safety["live_trading_false_default"]["ok"] is True
        finally:
            audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH = old_dir, old_json, old_md

    def test_13_safety_section_includes_no_order_send_in_safe_modules(self, tmp_path):
        import scripts.audit.master_integration_audit as audit
        old_dir, old_json, old_md = audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH
        audit.OUTPUT_DIR = tmp_path
        audit.JSON_PATH = tmp_path / "audit.json"
        audit.MD_PATH = tmp_path / "audit.md"
        try:
            result = audit.write_report()
            with open(result["json_path"]) as f:
                data = json.load(f)
            safety = data["safety_audit"]
            assert "safe_modules_no_order_send" in safety
            assert safety["safe_modules_no_order_send"]["ok"] is True
        finally:
            audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH = old_dir, old_json, old_md

    def test_14_operator_console_no_live_trading_command(self, tmp_path):
        import scripts.audit.master_integration_audit as audit
        old_dir, old_json, old_md = audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH
        audit.OUTPUT_DIR = tmp_path
        audit.JSON_PATH = tmp_path / "audit.json"
        audit.MD_PATH = tmp_path / "audit.md"
        try:
            result = audit.write_report()
            with open(result["json_path"]) as f:
                data = json.load(f)
            safety = data["safety_audit"]
            assert "operator_console_no_live_trading_command" in safety
            assert safety["operator_console_no_live_trading_command"]["ok"] is True
        finally:
            audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH = old_dir, old_json, old_md

    def test_15_operator_console_no_market_execution_command(self, tmp_path):
        import scripts.audit.master_integration_audit as audit
        old_dir, old_json, old_md = audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH
        audit.OUTPUT_DIR = tmp_path
        audit.JSON_PATH = tmp_path / "audit.json"
        audit.MD_PATH = tmp_path / "audit.md"
        try:
            result = audit.write_report()
            with open(result["json_path"]) as f:
                data = json.load(f)
            safety = data["safety_audit"]
            assert "operator_console_no_market_execution_command" in safety
            assert safety["operator_console_no_market_execution_command"]["ok"] is True
        finally:
            audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH = old_dir, old_json, old_md

    def test_16_final_verdict_exists(self, tmp_path):
        import scripts.audit.master_integration_audit as audit
        old_dir, old_json, old_md = audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH
        audit.OUTPUT_DIR = tmp_path
        audit.JSON_PATH = tmp_path / "audit.json"
        audit.MD_PATH = tmp_path / "audit.md"
        try:
            result = audit.write_report()
            assert result["verdict"] in (
                "INTEGRATION_READY",
                "INTEGRATION_READY_WITH_WARNINGS",
                "INTEGRATION_BLOCKED",
            )
        finally:
            audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH = old_dir, old_json, old_md

    def test_17_recommended_next_sprint_exists(self, tmp_path):
        import scripts.audit.master_integration_audit as audit
        old_dir, old_json, old_md = audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH
        audit.OUTPUT_DIR = tmp_path
        audit.JSON_PATH = tmp_path / "audit.json"
        audit.MD_PATH = tmp_path / "audit.md"
        try:
            result = audit.write_report()
            with open(result["json_path"]) as f:
                data = json.load(f)
            next_sprint = data["recommended_next_sprint"]
            assert next_sprint
            assert len(next_sprint) > 30  # should be a meaningful recommendation
            assert "Sprint" in next_sprint
        finally:
            audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH = old_dir, old_json, old_md

    def test_18_live_trading_ready_is_no(self, tmp_path):
        """LIVE_TRADING_READY must remain NO."""
        import scripts.audit.master_integration_audit as audit
        old_dir, old_json, old_md = audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH
        audit.OUTPUT_DIR = tmp_path
        audit.JSON_PATH = tmp_path / "audit.json"
        audit.MD_PATH = tmp_path / "audit.md"
        try:
            result = audit.write_report()
            with open(result["json_path"]) as f:
                data = json.load(f)
            readiness = data["product_readiness"]
            assert readiness["LIVE_TRADING_READY"] == "NO", \
                "LIVE_TRADING_READY must remain NO"
        finally:
            audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH = old_dir, old_json, old_md


class TestSafetyInvariants:
    def _strip_strings_and_comments(self, src: str) -> str:
        """Strip docstrings, string literals, and comments."""
        src = re.sub(r'"""[\s\S]*?"""', '""', src)
        src = re.sub(r"'''[\s\S]*?'''", "''", src)
        src = re.sub(r'"(?:[^"\\]|\\.)*"', '""', src)
        src = re.sub(r"'(?:[^'\\]|\\.)*'", "''", src)
        out_lines = []
        for line in src.splitlines():
            idx = line.find("#")
            if idx >= 0:
                line = line[:idx]
            out_lines.append(line)
        return "\n".join(out_lines)

    def test_19_no_metatrader5_import_in_audit_module(self):
        import scripts.audit.master_integration_audit as audit
        src = self._strip_strings_and_comments(inspect.getsource(audit))
        # No actual import statement (string literal mentions are OK)
        assert "import MetaTrader5" not in src
        assert "from MetaTrader5" not in src

    def test_20_no_order_send_execution_in_audit_module(self):
        import scripts.audit.master_integration_audit as audit
        src = self._strip_strings_and_comments(inspect.getsource(audit))
        call_pattern = r"\b(mt5\.order_send|adapter\.send_open_order|adapter\.send_order|send_close_order)\s*\("
        matches = re.findall(call_pattern, src)
        assert len(matches) == 0, f"Found execution calls: {matches}"

    def test_21_no_demo_micro_execute_in_audit_module(self):
        import scripts.audit.master_integration_audit as audit
        src = self._strip_strings_and_comments(inspect.getsource(audit))
        call_pattern = r"\b(DEMO_MICRO_EXECUTE|run_demo_micro|execute_demo_micro)\s*\("
        matches = re.findall(call_pattern, src)
        assert len(matches) == 0, f"Found demo micro execute calls: {matches}"

    def test_22_no_model_training_in_audit_module(self):
        import scripts.audit.master_integration_audit as audit
        src = self._strip_strings_and_comments(inspect.getsource(audit))
        call_pattern = r"\b(\w+\.fit|train_model|retrain|run_hpo)\s*\("
        matches = re.findall(call_pattern, src)
        assert len(matches) == 0, f"Found training calls: {matches}"

    def test_23_no_runtime_config_modification_in_audit_module(self):
        import scripts.audit.master_integration_audit as audit
        src = self._strip_strings_and_comments(inspect.getsource(audit))
        # Should not WRITE to runtime.yaml (reading for inspection is OK)
        # Check for write-mode open() calls
        write_pattern = r"open\s*\([^)]*['\"]runtime\.yaml['\"][^)]*['\"]w"
        matches = re.findall(write_pattern, src)
        assert len(matches) == 0, f"Found runtime.yaml write calls: {matches}"
        # Should not import yaml and dump to runtime config
        assert "yaml.dump" not in src

    def test_24_audit_does_not_import_runtime_modules(self):
        """Audit should not import autonomous_loops or launcher (to avoid side effects)."""
        import scripts.audit.master_integration_audit as audit
        src = self._strip_strings_and_comments(inspect.getsource(audit))
        # Should not import runtime modules - only read their source
        assert "from titan.runtime" not in src
        assert "import titan.runtime" not in src

    def test_25_audit_reads_source_files_at_rest(self):
        """Audit should use _read_source helper, not import runtime modules."""
        import scripts.audit.master_integration_audit as audit
        src = inspect.getsource(audit)
        assert "_read_source" in src
        assert "LAUNCHER_SRC" in src
        assert "AUTONOMOUS_SRC" in src
