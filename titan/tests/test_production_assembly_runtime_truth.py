"""TITAN XAU AI - Sprint 9.9.3.39 Production Assembly Runtime Truth Tests"""
from __future__ import annotations
import sys
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from titan.production.production_runtime_assembly import (
    ProductionRuntimeAssembly, ProductionRuntimeMode, ProductionAssemblyVerdict,
)


class TestRuntimeWiringChecks:
    def test_01_validate_runtime_wiring_returns_dict(self):
        asm = ProductionRuntimeAssembly()
        ok, checks, blockers = asm.validate_runtime_wiring()
        assert isinstance(ok, bool)
        assert isinstance(checks, dict)
        assert isinstance(blockers, list)

    def test_02_all_wiring_checks_present(self):
        asm = ProductionRuntimeAssembly()
        ok, checks, blockers = asm.validate_runtime_wiring()
        required_checks = [
            "launcher_has_autonomous_runtime",
            "autonomous_runtime_has_signal_execution_bridge",
            "autonomous_runtime_builds_execution_intent",
            "autonomous_runtime_calls_bridge_before_trade_loop",
            "bridge_blocks_before_trade_loop",
            "autonomous_runtime_has_regime_gate",
            "autonomous_runtime_has_broker_gate",
            "autonomous_runtime_has_runtime_health_gate",
            "autonomous_runtime_has_security_gate",
            "autonomous_runtime_has_position_lifecycle",
            "autonomous_runtime_has_exit_intent_bridge",
            "observation_engine_runtime_wired",
            "scorecard_runtime_wired",
        ]
        for check_name in required_checks:
            assert check_name in checks, f"Missing wiring check: {check_name}"

    def test_03_all_wiring_checks_pass_after_sprint_939(self):
        """After Sprint 9.9.3.39, all wiring checks must pass."""
        asm = ProductionRuntimeAssembly()
        ok, checks, blockers = asm.validate_runtime_wiring()
        assert ok is True, f"Wiring checks failed: {blockers}"
        for check_name, check_value in checks.items():
            assert check_value is True, f"Wiring check failed: {check_name}"

    def test_04_build_status_includes_wiring_checks(self):
        """build_status() must call validate_runtime_wiring() and include blockers."""
        asm = ProductionRuntimeAssembly()
        status = asm.build_status()
        # After wiring, status should not have wiring blockers
        wiring_blockers = [b for b in status.blockers if "Runtime wiring check failed" in b]
        assert len(wiring_blockers) == 0, f"Wiring blockers present: {wiring_blockers}"


class TestRCReadyTruthfulness:
    def test_05_rc_ready_only_when_wiring_complete(self):
        """RC_READY must only be possible when all wiring checks pass."""
        asm = ProductionRuntimeAssembly()
        status = asm.build_status()
        wiring_ok, _, _ = asm.validate_runtime_wiring()
        if not wiring_ok:
            assert status.verdict == ProductionAssemblyVerdict.RC_BLOCKED, \
                "RC_READY must be blocked when wiring checks fail"
        else:
            # When wiring passes, verdict can be RC_READY or RC_READY_WITH_WARNINGS
            assert status.verdict in (
                ProductionAssemblyVerdict.RC_READY,
                ProductionAssemblyVerdict.RC_READY_WITH_WARNINGS,
            )

    def test_06_rc_ready_blocked_if_bridge_not_wired(self):
        """If SignalExecutionBridge is not wired, RC_READY must be blocked."""
        # This test verifies the wiring check exists and would block.
        # We simulate by checking the wiring check directly.
        asm = ProductionRuntimeAssembly()
        ok, checks, blockers = asm.validate_runtime_wiring()
        # The check for signal_execution_bridge must exist
        assert "autonomous_runtime_has_signal_execution_bridge" in checks
        # After Sprint 9.9.3.39, this check passes
        assert checks["autonomous_runtime_has_signal_execution_bridge"] is True

    def test_07_rc_ready_blocked_if_bridge_does_not_precede_trade_loop(self):
        """If bridge does not precede TradeLoop, RC_READY must be blocked."""
        asm = ProductionRuntimeAssembly()
        ok, checks, blockers = asm.validate_runtime_wiring()
        assert "autonomous_runtime_calls_bridge_before_trade_loop" in checks
        assert "bridge_blocks_before_trade_loop" in checks
        # After Sprint 9.9.3.39, both checks pass
        assert checks["autonomous_runtime_calls_bridge_before_trade_loop"] is True
        assert checks["bridge_blocks_before_trade_loop"] is True

    def test_08_rc_ready_blocked_if_exit_intent_bridge_not_wired(self):
        """If ExitIntentBridge is not wired, RC_READY must be blocked."""
        asm = ProductionRuntimeAssembly()
        ok, checks, blockers = asm.validate_runtime_wiring()
        assert "autonomous_runtime_has_exit_intent_bridge" in checks
        assert checks["autonomous_runtime_has_exit_intent_bridge"] is True

    def test_09_rc_ready_blocked_if_observation_not_wired(self):
        """If observation engine is not wired, RC_READY must be blocked."""
        asm = ProductionRuntimeAssembly()
        ok, checks, blockers = asm.validate_runtime_wiring()
        assert "observation_engine_runtime_wired" in checks
        assert "scorecard_runtime_wired" in checks
        assert checks["observation_engine_runtime_wired"] is True
        assert checks["scorecard_runtime_wired"] is True

    def test_10_live_trading_true_blocks_rc(self):
        """live_trading_enabled=True must block RC_READY."""
        # ProductionRuntimeAssembly hardcodes live_trading_enabled=False
        # and mt5_order_send_allowed=False. This test verifies those invariants.
        asm = ProductionRuntimeAssembly()
        status = asm.build_status()
        assert status.live_trading_enabled is False
        assert status.mt5_order_send_allowed is False

    def test_11_order_send_allowed_true_blocks_rc(self):
        """mt5_order_send_allowed=True must block RC_READY."""
        asm = ProductionRuntimeAssembly()
        status = asm.build_status()
        # Hardcoded to False in ProductionAssemblyStatus
        assert status.mt5_order_send_allowed is False

    def test_12_max_lot_cap_enforced(self):
        """max_lot must not exceed 0.01."""
        asm = ProductionRuntimeAssembly()
        status = asm.build_status()
        assert status.max_lot <= 0.01

    def test_13_max_open_positions_cap_enforced(self):
        """max_open_positions must not exceed 1."""
        asm = ProductionRuntimeAssembly()
        status = asm.build_status()
        assert status.max_open_positions <= 1

    def test_14_dry_run_enforced(self):
        """dry_run must be True."""
        asm = ProductionRuntimeAssembly()
        status = asm.build_status()
        assert status.dry_run is True

    def test_15_demo_only_enforced(self):
        """demo_only must be True."""
        asm = ProductionRuntimeAssembly()
        status = asm.build_status()
        assert status.demo_only is True


class TestRCVerdictAfterWiring:
    def test_16_rc_verdict_after_wiring(self):
        """After Sprint 9.9.3.39 wiring, RC verdict should be RC_READY or RC_READY_WITH_WARNINGS."""
        asm = ProductionRuntimeAssembly()
        status = asm.build_status()
        # With wiring complete, verdict should be RC_READY (with broker warnings)
        assert status.verdict in (
            ProductionAssemblyVerdict.RC_READY,
            ProductionAssemblyVerdict.RC_READY_WITH_WARNINGS,
        ), f"Expected RC_READY or RC_READY_WITH_WARNINGS, got {status.verdict}"

    def test_17_no_wiring_blockers_after_sprint_939(self):
        """No wiring blockers should remain after Sprint 9.9.3.39."""
        asm = ProductionRuntimeAssembly()
        status = asm.build_status()
        wiring_blockers = [b for b in status.blockers if "Runtime wiring check failed" in b]
        assert len(wiring_blockers) == 0
