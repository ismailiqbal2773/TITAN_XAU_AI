"""TITAN XAU AI - Sprint 9.9.3.39 Master Integration Audit After Wiring Tests"""
from __future__ import annotations
import inspect, json, re, sys
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


class TestWiringMatrixAfterIntegration:
    def test_01_signal_execution_bridge_wired_in_autonomous_runtime(self, tmp_path):
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
            assert matrix["SignalExecutionBridge"]["classification"] == "WIRED_IN_AUTONOMOUS_RUNTIME", \
                f"SignalExecutionBridge: {matrix['SignalExecutionBridge']['classification']}"
        finally:
            audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH = old_dir, old_json, old_md

    def test_02_regime_detection_wired_in_autonomous_runtime(self, tmp_path):
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
            assert matrix["RegimeDetection"]["classification"] == "WIRED_IN_AUTONOMOUS_RUNTIME", \
                f"RegimeDetection: {matrix['RegimeDetection']['classification']}"
        finally:
            audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH = old_dir, old_json, old_md

    def test_03_broker_compatibility_matrix_wired(self, tmp_path):
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
            assert matrix["BrokerCompatibilityMatrix"]["classification"] == "WIRED_IN_AUTONOMOUS_RUNTIME", \
                f"BrokerCompatibilityMatrix: {matrix['BrokerCompatibilityMatrix']['classification']}"
        finally:
            audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH = old_dir, old_json, old_md

    def test_04_runtime_health_monitor_wired(self, tmp_path):
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
            assert matrix["RuntimeHealthMonitor"]["classification"] == "WIRED_IN_AUTONOMOUS_RUNTIME", \
                f"RuntimeHealthMonitor: {matrix['RuntimeHealthMonitor']['classification']}"
        finally:
            audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH = old_dir, old_json, old_md

    def test_05_security_gate_wired(self, tmp_path):
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
            assert matrix["SecurityGate"]["classification"] == "WIRED_IN_AUTONOMOUS_RUNTIME", \
                f"SecurityGate: {matrix['SecurityGate']['classification']}"
        finally:
            audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH = old_dir, old_json, old_md

    def test_06_position_lifecycle_engine_wired(self, tmp_path):
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
            assert matrix["PositionLifecycleEngine"]["classification"] == "WIRED_IN_AUTONOMOUS_RUNTIME", \
                f"PositionLifecycleEngine: {matrix['PositionLifecycleEngine']['classification']}"
        finally:
            audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH = old_dir, old_json, old_md

    def test_07_exit_intent_bridge_wired(self, tmp_path):
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
            assert matrix["ExitIntentBridge"]["classification"] == "WIRED_IN_AUTONOMOUS_RUNTIME", \
                f"ExitIntentBridge: {matrix['ExitIntentBridge']['classification']}"
        finally:
            audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH = old_dir, old_json, old_md

    def test_08_forward_observation_engine_wired(self, tmp_path):
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
            assert matrix["ForwardObservationEngine"]["classification"] == "WIRED_IN_AUTONOMOUS_RUNTIME", \
                f"ForwardObservationEngine: {matrix['ForwardObservationEngine']['classification']}"
        finally:
            audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH = old_dir, old_json, old_md

    def test_09_observation_scorecard_engine_wired(self, tmp_path):
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
            assert matrix["ObservationScorecardEngine"]["classification"] == "WIRED_IN_AUTONOMOUS_RUNTIME", \
                f"ObservationScorecardEngine: {matrix['ObservationScorecardEngine']['classification']}"
        finally:
            audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH = old_dir, old_json, old_md


class TestVerdictAfterWiring:
    def test_10_final_verdict_is_ready_or_warnings(self, tmp_path):
        """After wiring, verdict should be INTEGRATION_READY or INTEGRATION_READY_WITH_WARNINGS."""
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
            ), f"Expected READY or READY_WITH_WARNINGS, got {result['verdict']}"
        finally:
            audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH = old_dir, old_json, old_md

    def test_11_no_blockers_after_wiring(self, tmp_path):
        """After wiring, there should be no integration blockers."""
        import scripts.audit.master_integration_audit as audit
        old_dir, old_json, old_md = audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH
        audit.OUTPUT_DIR = tmp_path
        audit.JSON_PATH = tmp_path / "audit.json"
        audit.MD_PATH = tmp_path / "audit.md"
        try:
            result = audit.write_report()
            with open(result["json_path"]) as f:
                data = json.load(f)
            # Filter out the LIVE_TRADING_READY blocker (which is a safety check, not a wiring issue)
            integration_blockers = [
                b for b in data["blockers"]
                if "LIVE_TRADING_READY" not in b
            ]
            assert len(integration_blockers) == 0, f"Integration blockers: {integration_blockers}"
        finally:
            audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH = old_dir, old_json, old_md

    def test_12_autonomous_runtime_wiring_complete_yes(self, tmp_path):
        """AUTONOMOUS_RUNTIME_WIRING_COMPLETE should be YES after wiring."""
        import scripts.audit.master_integration_audit as audit
        old_dir, old_json, old_md = audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH
        audit.OUTPUT_DIR = tmp_path
        audit.JSON_PATH = tmp_path / "audit.json"
        audit.MD_PATH = tmp_path / "audit.md"
        try:
            result = audit.write_report()
            with open(result["json_path"]) as f:
                data = json.load(f)
            assert data["product_readiness"]["AUTONOMOUS_RUNTIME_WIRING_COMPLETE"] == "YES"
        finally:
            audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH = old_dir, old_json, old_md

    def test_13_rc_assembly_truthful_yes(self, tmp_path):
        """RC_ASSEMBLY_TRUTHFUL should be YES after Sprint 9.9.3.39."""
        import scripts.audit.master_integration_audit as audit
        old_dir, old_json, old_md = audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH
        audit.OUTPUT_DIR = tmp_path
        audit.JSON_PATH = tmp_path / "audit.json"
        audit.MD_PATH = tmp_path / "audit.md"
        try:
            result = audit.write_report()
            with open(result["json_path"]) as f:
                data = json.load(f)
            assert data["product_readiness"]["RC_ASSEMBLY_TRUTHFUL"] == "YES"
        finally:
            audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH = old_dir, old_json, old_md

    def test_14_live_trading_ready_remains_no(self, tmp_path):
        """LIVE_TRADING_READY must remain NO even after wiring."""
        import scripts.audit.master_integration_audit as audit
        old_dir, old_json, old_md = audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH
        audit.OUTPUT_DIR = tmp_path
        audit.JSON_PATH = tmp_path / "audit.json"
        audit.MD_PATH = tmp_path / "audit.md"
        try:
            result = audit.write_report()
            with open(result["json_path"]) as f:
                data = json.load(f)
            assert data["product_readiness"]["LIVE_TRADING_READY"] == "NO"
        finally:
            audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH = old_dir, old_json, old_md

    def test_15_recommended_next_sprint_exists(self, tmp_path):
        """Recommended next sprint should still exist after wiring."""
        import scripts.audit.master_integration_audit as audit
        old_dir, old_json, old_md = audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH
        audit.OUTPUT_DIR = tmp_path
        audit.JSON_PATH = tmp_path / "audit.json"
        audit.MD_PATH = tmp_path / "audit.md"
        try:
            result = audit.write_report()
            with open(result["json_path"]) as f:
                data = json.load(f)
            assert data["recommended_next_sprint"]
            assert len(data["recommended_next_sprint"]) > 30
        finally:
            audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH = old_dir, old_json, old_md


class TestNoFalseWiring:
    def test_16_no_critical_module_falsely_marked_wired(self, tmp_path):
        """Verify that modules are not falsely marked as wired."""
        # The audit reads source files at rest and checks actual imports.
        # We verify the autonomous_loops.py actually contains the imports.
        autonomous_src = (REPO_ROOT / "titan" / "runtime" / "autonomous_loops.py").read_text(encoding="utf-8")
        # Strip strings/comments
        src = re.sub(r'"""[\s\S]*?"""', '""', autonomous_src)
        src = re.sub(r"'''[\s\S]*?'''", "''", src)
        src = re.sub(r'"(?:[^"\\]|\\.)*"', '""', src)
        src = re.sub(r"'(?:[^'\\]|\\.)*'", "''", src)
        # Verify actual imports exist
        assert "titan.production.signal_execution_bridge" in src
        assert "titan.production.regime_detection" in src
        assert "titan.production.broker_compatibility_matrix" in src
        assert "titan.production.runtime_health" in src
        assert "titan.security.security_gate" in src
        assert "titan.production.position_lifecycle" in src
        assert "titan.production.exit_intent_bridge" in src
        assert "titan.production.forward_observation" in src
        assert "titan.production.observation_scorecard" in src

    def test_17_executable_chain_matrix_improves(self, tmp_path):
        """The executable chain matrix should show improvement after wiring."""
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
            # At least some links should be PRESENT after wiring
            present_count = sum(1 for v in chain.values() if v == "PRESENT")
            assert present_count > 0, "No PRESENT links in chain matrix"
        finally:
            audit.OUTPUT_DIR, audit.JSON_PATH, audit.MD_PATH = old_dir, old_json, old_md
