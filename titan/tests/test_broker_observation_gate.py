"""TITAN XAU AI - Sprint 9.9.3.41.1 Broker Observation Gate Tests"""
from __future__ import annotations
import inspect, json, re, sys
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from titan.production.broker_observation_gate import (
    BrokerObservationGate, BrokerObservationGateResult,
    ObservationBrokerVerdict,
)


class TestExistingModulesDiscovered:
    def test_01_broker_intelligence_exists(self):
        """Existing BrokerIntelligenceLayer must be discovered, not duplicated."""
        path = REPO_ROOT / "titan" / "production" / "broker_intelligence.py"
        assert path.exists(), "broker_intelligence.py must exist"
        src = path.read_text(encoding="utf-8")
        assert "class BrokerIntelligenceLayer" in src

    def test_02_broker_compatibility_matrix_exists(self):
        """Existing BrokerCompatibilityMatrix must be discovered."""
        path = REPO_ROOT / "titan" / "production" / "broker_compatibility_matrix.py"
        assert path.exists()
        src = path.read_text(encoding="utf-8")
        assert "def get_broker_info" in src
        assert "def get_all_brokers" in src

    def test_03_broker_scoring_exists(self):
        """Existing BrokerQualityEngine (broker scoring) must be discovered."""
        path = REPO_ROOT / "titan" / "production" / "broker_quality_engine.py"
        assert path.exists()
        src = path.read_text(encoding="utf-8")
        assert "class BrokerQualityEngine" in src

    def test_04_no_duplicate_broker_engine_created(self):
        """BrokerObservationGate must NOT duplicate BrokerIntelligenceLayer."""
        gate_path = REPO_ROOT / "titan" / "production" / "broker_observation_gate.py"
        assert gate_path.exists()
        src = gate_path.read_text(encoding="utf-8")
        # Strip strings/comments
        code = re.sub(r'"""[\s\S]*?"""', '""', src)
        code = re.sub(r"'''[\s\S]*?'''", "''", code)
        code = re.sub(r'r"[^"]*"', '""', code)
        code = re.sub(r"r'[^']*'", "''", code)
        code = re.sub(r'"(?:[^"\\]|\\.)*"', '""', code)
        code = re.sub(r"'(?:[^'\\]|\\.)*'", "''", code)
        # Must NOT define BrokerIntelligenceLayer (no duplication)
        assert "class BrokerIntelligenceLayer" not in code, \
            "BrokerObservationGate duplicates BrokerIntelligenceLayer"
        # Must NOT define BrokerQualityEngine (no duplication)
        assert "class BrokerQualityEngine" not in code, \
            "BrokerObservationGate duplicates BrokerQualityEngine"
        # Must import from existing broker_compatibility_matrix
        assert "from titan.production.broker_compatibility_matrix" in code or \
               "import titan.production.broker_compatibility_matrix" in code, \
            "BrokerObservationGate must reuse BrokerCompatibilityMatrix"


class TestBrokerGateVerdicts:
    def test_05_metaquotes_allowed(self):
        """MetaQuotes-Demo must be ALLOWED for 7-day observation."""
        gate = BrokerObservationGate()
        result = gate.evaluate(broker_name="MetaQuotes-Demo")
        assert result.verdict == ObservationBrokerVerdict.ALLOWED
        assert result.observation_eligible is True

    def test_06_fundednext_blocked(self):
        """FundedNext Free Trial must be BLOCKED."""
        gate = BrokerObservationGate()
        result = gate.evaluate(broker_name="FundedNext Free Trial")
        assert result.verdict == ObservationBrokerVerdict.BLOCKED

    def test_07_fbs_blocked(self):
        """FBS-Demo must be BLOCKED (REJECTED)."""
        gate = BrokerObservationGate()
        result = gate.evaluate(broker_name="FBS-Demo")
        assert result.verdict == ObservationBrokerVerdict.BLOCKED

    def test_08_exness_pending(self):
        """Exness Demo must be PENDING (blocked for observation)."""
        gate = BrokerObservationGate()
        result = gate.evaluate(broker_name="Exness Demo")
        assert result.verdict in (ObservationBrokerVerdict.PENDING, ObservationBrokerVerdict.BLOCKED)

    def test_09_icmarkets_pending(self):
        """ICMarkets Demo must be PENDING (blocked for observation)."""
        gate = BrokerObservationGate()
        result = gate.evaluate(broker_name="ICMarkets Demo")
        assert result.verdict in (ObservationBrokerVerdict.PENDING, ObservationBrokerVerdict.BLOCKED)

    def test_10_unknown_broker_blocked(self):
        """Unknown broker must be BLOCKED for current 7-day observation."""
        gate = BrokerObservationGate()
        result = gate.evaluate(broker_name="UnknownBroker123")
        assert result.verdict in (ObservationBrokerVerdict.UNKNOWN, ObservationBrokerVerdict.BLOCKED)

    def test_11_no_broker_returns_unknown(self):
        """No broker name provided returns UNKNOWN."""
        gate = BrokerObservationGate()
        result = gate.evaluate(broker_name="")
        assert result.verdict == ObservationBrokerVerdict.UNKNOWN


class TestBrokerGateWiring:
    def test_12_operator_console_uses_broker_gate(self):
        """Operator console BROKER STATUS must use broker gate."""
        path = REPO_ROOT / "titan" / "production" / "operator_control_console.py"
        src = path.read_text(encoding="utf-8")
        assert "broker_observation_gate" in src or "BrokerObservationGate" in src, \
            "Operator console must use BrokerObservationGate"

    def test_13_first_run_wizard_uses_broker_gate(self):
        """First-run wizard must use broker gate."""
        path = REPO_ROOT / "titan" / "production" / "first_run_wizard.py"
        src = path.read_text(encoding="utf-8")
        assert "check_broker_observation_gate" in src, \
            "First-run wizard must have check_broker_observation_gate"
        assert "broker_observation_gate" in src or "BrokerObservationGate" in src, \
            "First-run wizard must use BrokerObservationGate"

    def test_14_pre_observation_audit_includes_broker_intelligence_section(self):
        """Pre-observation audit must include broker intelligence verification section."""
        path = REPO_ROOT / "scripts" / "audit" / "pre_observation_acceptance_audit.py"
        src = path.read_text(encoding="utf-8")
        assert "audit_broker_intelligence_verification" in src, \
            "Pre-observation audit must include broker intelligence verification"
        assert "broker_observation_gate" in src or "BrokerObservationGate" in src, \
            "Pre-observation audit must reference BrokerObservationGate"


class TestBrokerGateBehavior:
    def test_15_broker_registry_blocked_overrides_runtime_allow(self):
        """If registry says BLOCKED, gate must BLOCK even if broker name is allowed-like."""
        gate = BrokerObservationGate()
        # FundedNext Free Trial is in registry as BLOCKED
        result = gate.evaluate(broker_name="FundedNext Free Trial")
        assert result.verdict == ObservationBrokerVerdict.BLOCKED
        assert result.registry_status == "BLOCKED"

    def test_16_broker_auto_switch_blocked(self):
        """Broker auto-switch must NOT be allowed without operator approval."""
        gate = BrokerObservationGate()
        summary = gate.summary()
        assert summary["auto_switch_allowed"] is False, \
            "Broker auto-switch must always be False (operator approval required)"

    def test_17_list_allowed_brokers(self):
        """list_allowed_brokers returns only MetaQuotes-Demo."""
        gate = BrokerObservationGate()
        allowed = gate.list_allowed_brokers()
        assert allowed == ["MetaQuotes-Demo"]

    def test_18_list_blocked_brokers(self):
        """list_blocked_brokers includes FundedNext and FBS."""
        gate = BrokerObservationGate()
        blocked = gate.list_blocked_brokers()
        assert "FundedNext Free Trial" in blocked
        assert "FBS-Demo" in blocked

    def test_19_list_pending_brokers(self):
        """list_pending_brokers includes Exness and ICMarkets."""
        gate = BrokerObservationGate()
        pending = gate.list_pending_brokers()
        assert "Exness Demo" in pending
        assert "ICMarkets Demo" in pending


class TestSafetyInvariants:
    def test_20_no_metatrader5_import_in_gate(self):
        from titan.production import broker_observation_gate
        src = inspect.getsource(broker_observation_gate)
        assert "import MetaTrader5" not in src
        assert "from MetaTrader5" not in src

    def test_21_no_order_send_in_gate(self):
        import re
        from titan.production import broker_observation_gate
        src = inspect.getsource(broker_observation_gate)
        src = re.sub(r'"""[\s\S]*?"""', '""', src)
        src = re.sub(r"'''[\s\S]*?'''", "''", src)
        src = re.sub(r'r"[^"]*"', '""', src)
        src = re.sub(r"r'[^']*'", "''", src)
        src = re.sub(r'"(?:[^"\\]|\\.)*"', '""', src)
        src = re.sub(r"'(?:[^'\\]|\\.)*'", "''", src)
        call_pattern = r"\bmt5\.order_send\s*\("
        matches = re.findall(call_pattern, src)
        assert len(matches) == 0, f"Found order_send calls: {matches}"

    def test_22_no_demo_micro_execute_in_gate(self):
        import re
        from titan.production import broker_observation_gate
        src = inspect.getsource(broker_observation_gate)
        src = re.sub(r'"""[\s\S]*?"""', '""', src)
        src = re.sub(r"'''[\s\S]*?'''", "''", src)
        src = re.sub(r'r"[^"]*"', '""', src)
        src = re.sub(r"r'[^']*'", "''", src)
        src = re.sub(r'"(?:[^"\\]|\\.)*"', '""', src)
        src = re.sub(r"'(?:[^'\\]|\\.)*'", "''", src)
        call_pattern = r"(?<!['\"])\b(DEMO_MICRO_EXECUTE|run_demo_micro|execute_demo_micro)\s*\("
        matches = re.findall(call_pattern, src)
        assert len(matches) == 0, f"Found demo micro execute calls: {matches}"

    def test_23_no_raw_mt5_probe_in_gate(self):
        import re
        from titan.production import broker_observation_gate
        src = inspect.getsource(broker_observation_gate)
        src = re.sub(r'"""[\s\S]*?"""', '""', src)
        src = re.sub(r"'''[\s\S]*?'''", "''", src)
        src = re.sub(r'r"[^"]*"', '""', src)
        src = re.sub(r"r'[^']*'", "''", src)
        src = re.sub(r'"(?:[^"\\]|\\.)*"', '""', src)
        src = re.sub(r"'(?:[^'\\]|\\.)*'", "''", src)
        call_pattern = r"(?<!['\"])\b(run_raw_probe|raw_mt5_probe)\s*\("
        matches = re.findall(call_pattern, src)
        assert len(matches) == 0, f"Found raw probe calls: {matches}"

    def test_24_no_market_execution_in_gate(self):
        """Gate must not call any market execution function."""
        import re
        from titan.production import broker_observation_gate
        src = inspect.getsource(broker_observation_gate)
        src = re.sub(r'"""[\s\S]*?"""', '""', src)
        src = re.sub(r"'''[\s\S]*?'''", "''", src)
        src = re.sub(r'r"[^"]*"', '""', src)
        src = re.sub(r"r'[^']*'", "''", src)
        src = re.sub(r'"(?:[^"\\]|\\.)*"', '""', src)
        src = re.sub(r"'(?:[^'\\]|\\.)*'", "''", src)
        call_pattern = r"\b(adapter\.send_open_order|adapter\.send_order|send_close_order)\s*\("
        matches = re.findall(call_pattern, src)
        assert len(matches) == 0, f"Found market execution calls: {matches}"
