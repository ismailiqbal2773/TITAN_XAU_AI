"""TITAN XAU AI — Sprint 9.9.3.34 Production Runtime Assembly Tests"""
from __future__ import annotations
import inspect, sys
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from titan.production.production_runtime_assembly import (
    ProductionRuntimeAssembly, ProductionAssemblyStatus,
    ProductionRuntimeMode, ProductionAssemblyVerdict,
    REQUIRED_COMPONENTS,
)


class TestComponentInventory:
    def test_01_all_required_components_listed(self):
        assert len(REQUIRED_COMPONENTS) >= 16

    def test_02_components_load(self):
        asm = ProductionRuntimeAssembly()
        loaded, missing = asm.load_components()
        assert len(missing) == 0, f"Missing components: {missing}"

    def test_03_validate_component_presence(self):
        asm = ProductionRuntimeAssembly()
        ok, missing = asm.validate_component_presence()
        assert ok is True
        assert len(missing) == 0


class TestSafetyGates:
    def test_04_safety_gates_validated(self):
        asm = ProductionRuntimeAssembly()
        ok, enabled, blockers = asm.validate_safety_gates()
        assert ok is True
        assert len(enabled) >= 10
        assert len(blockers) == 0

    def test_05_execution_permissions(self):
        asm = ProductionRuntimeAssembly()
        ok, blockers = asm.validate_execution_permissions()
        assert ok is True
        assert len(blockers) == 0


class TestBrokerRegistry:
    def test_06_broker_registry_has_metaquotes(self):
        asm = ProductionRuntimeAssembly()
        registry = asm.validate_broker_registry()
        assert "MetaQuotes-Demo" in registry
        assert registry["MetaQuotes-Demo"]["status"] == "PASS"

    def test_07_fundednext_blocked(self):
        asm = ProductionRuntimeAssembly()
        registry = asm.validate_broker_registry()
        assert registry["FundedNext Free Trial"]["status"] == "BLOCKED"

    def test_08_fbs_rejected(self):
        asm = ProductionRuntimeAssembly()
        registry = asm.validate_broker_registry()
        assert registry["FBS-Demo"]["status"] == "REJECT"


class TestBuildStatus:
    def test_09_status_has_all_fields(self):
        asm = ProductionRuntimeAssembly()
        status = asm.build_status()
        required = ["mode", "verdict", "components_loaded", "components_missing",
                     "safety_gates_enabled", "live_trading_enabled", "demo_only",
                     "dry_run", "execution_allowed", "mt5_order_send_allowed",
                     "max_lot", "max_open_positions", "broker_status",
                     "runtime_health_status", "security_status",
                     "observation_status", "blockers", "warnings", "timestamp_utc"]
        for f in required:
            assert hasattr(status, f), f"Missing field: {f}"

    def test_10_dry_run_true(self):
        asm = ProductionRuntimeAssembly()
        status = asm.build_status()
        assert status.dry_run is True

    def test_11_demo_only_true(self):
        asm = ProductionRuntimeAssembly()
        status = asm.build_status()
        assert status.demo_only is True

    def test_12_live_trading_false(self):
        asm = ProductionRuntimeAssembly()
        status = asm.build_status()
        assert status.live_trading_enabled is False

    def test_13_mt5_order_send_false(self):
        asm = ProductionRuntimeAssembly()
        status = asm.build_status()
        assert status.mt5_order_send_allowed is False

    def test_14_max_lot_001(self):
        asm = ProductionRuntimeAssembly()
        status = asm.build_status()
        assert status.max_lot <= 0.01

    def test_15_max_open_positions_1(self):
        asm = ProductionRuntimeAssembly()
        status = asm.build_status()
        assert status.max_open_positions <= 1

    def test_16_verdict_ready_or_warnings(self):
        asm = ProductionRuntimeAssembly()
        status = asm.build_status()
        assert status.verdict in (ProductionAssemblyVerdict.RC_READY,
                                   ProductionAssemblyVerdict.RC_READY_WITH_WARNINGS)

    def test_17_observation_scorecard_in_loaded(self):
        asm = ProductionRuntimeAssembly()
        status = asm.build_status()
        assert "ObservationScorecardEngine" in status.components_loaded

    def test_18_fail_closed_on_exception(self):
        asm = ProductionRuntimeAssembly()
        status = asm.fail_closed_status("test reason")
        assert status.verdict == ProductionAssemblyVerdict.RC_BLOCKED
        assert "test reason" in status.blockers[0]


class TestNoMT5:
    def test_19_no_metatrader5_import(self):
        from titan.production import production_runtime_assembly
        src = inspect.getsource(production_runtime_assembly)
        assert "import MetaTrader5" not in src
        assert "from MetaTrader5" not in src

    def test_20_no_order_send_calls(self):
        """No actual order_send CALLS (mentions in docstrings ok)."""
        import re
        from titan.production import production_runtime_assembly
        src = inspect.getsource(production_runtime_assembly)
        call_pattern = r"(?<!['\"#])\b(mt5\.order_send|adapter\.send_open_order|adapter\.send_order|send_close_order)\s*\("
        matches = re.findall(call_pattern, src)
        assert len(matches) == 0, f"Found execution calls: {matches}"
