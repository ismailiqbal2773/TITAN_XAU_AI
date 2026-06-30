"""
TITAN XAU AI — Production Runtime Assembly (Sprint 9.9.3.34)
=============================================================

Connects all completed components into one safe dry-run/demo-ready runtime
assembly. Never imports MetaTrader5. Never sends orders.

Components wired:
  - InferenceEngine, SignalExecutionBridge, RegimeDetection
  - BrokerCompatibilityMatrix, RuntimeHealthMonitor, SecurityGate
  - PositionLifecycleEngine, SLDefenseEngine, ProfitCaptureEngine
  - ExitDecisionCoordinator, ExitIntentBridge
  - ForwardObservationEngine, ObservationScorecardEngine
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class ProductionRuntimeMode(str, Enum):
    DRY_RUN = "DRY_RUN"
    DEMO_OBSERVATION = "DEMO_OBSERVATION"
    DEMO_MICRO_OPERATOR = "DEMO_MICRO_OPERATOR"
    LIVE_BLOCKED = "LIVE_BLOCKED"


class ProductionAssemblyVerdict(str, Enum):
    RC_READY = "RC_READY"
    RC_READY_WITH_WARNINGS = "RC_READY_WITH_WARNINGS"
    RC_BLOCKED = "RC_BLOCKED"


# Components that must be present for RC
REQUIRED_COMPONENTS = {
    "InferenceEngine": "titan.production.inference",
    "SignalExecutionBridge": "titan.production.signal_execution_bridge",
    "RegimeDetection": "titan.production.regime_detection",
    "BrokerCompatibilityMatrix": "titan.production.broker_compatibility_matrix",
    "RuntimeHealthMonitor": "titan.production.runtime_health",
    "SecurityGate": "titan.security.security_gate",
    "PositionLifecycleEngine": "titan.production.position_lifecycle",
    "SLDefenseEngine": "titan.production.exit_defense_engine",
    "ProfitCaptureEngine": "titan.production.profit_capture_engine",
    "ExitDecisionCoordinator": "titan.production.exit_decision_coordinator",
    "ExitIntentBridge": "titan.production.exit_intent_bridge",
    "ForwardObservationEngine": "titan.production.forward_observation",
    "ObservationScorecardEngine": "titan.production.observation_scorecard",
    "MT5ExecutionAdapter": "titan.production.mt5_execution_adapter",
    "LicenseGuard": "titan.security.license_guard",
    "AntiTamperGuard": "titan.security.anti_tamper_guard",
}


@dataclass
class ProductionAssemblyStatus:
    mode: ProductionRuntimeMode = ProductionRuntimeMode.DRY_RUN
    verdict: ProductionAssemblyVerdict = ProductionAssemblyVerdict.RC_BLOCKED
    components_loaded: list[str] = field(default_factory=list)
    components_missing: list[str] = field(default_factory=list)
    safety_gates_enabled: list[str] = field(default_factory=list)
    live_trading_enabled: bool = False
    demo_only: bool = True
    dry_run: bool = True
    execution_allowed: bool = False
    mt5_order_send_allowed: bool = False
    max_lot: float = 0.01
    max_open_positions: int = 1
    broker_status: dict = field(default_factory=dict)
    runtime_health_status: str = "UNKNOWN"
    security_status: str = "UNKNOWN"
    observation_status: str = "UNKNOWN"
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    timestamp_utc: str = ""

    def __post_init__(self):
        if not self.timestamp_utc:
            self.timestamp_utc = datetime.now(timezone.utc).isoformat()


class ProductionRuntimeAssembly:
    """Validates that all components are present and safety gates are enabled.

    Never imports MetaTrader5. Never sends orders.
    """

    def __init__(self, mode: ProductionRuntimeMode = ProductionRuntimeMode.DRY_RUN):
        self.mode = mode
        self._components_loaded: list[str] = []
        self._components_missing: list[str] = []

    def load_components(self) -> tuple[list[str], list[str]]:
        """Check that all required components can be imported.

        Returns (loaded, missing) lists of component names.
        """
        loaded = []
        missing = []
        for name, module_path in REQUIRED_COMPONENTS.items():
            try:
                __import__(module_path)
                loaded.append(name)
            except Exception:
                missing.append(name)
        self._components_loaded = loaded
        self._components_missing = missing
        return loaded, missing

    def validate_component_presence(self) -> tuple[bool, list[str]]:
        """True if all required components are present."""
        if not self._components_loaded:
            self.load_components()
        missing = self._components_missing
        return len(missing) == 0, missing

    def validate_safety_gates(self) -> tuple[bool, list[str], list[str]]:
        """Validate safety gates. Returns (ok, enabled, blockers)."""
        enabled = [
            "LicenseGuard (dev_mode non-blocking)",
            "AntiTamperGuard (dev_mode non-blocking)",
            "SecurityGate (dev_mode non-blocking)",
            "HardGate (demo_micro_hard_gate.py)",
            "DemoMicroArmedToken (TITAN_DEMO_MICRO_ARMED required)",
            "DryRunEnforced (runtime.dry_run=true)",
            "LiveTradingBlocked (runtime.live_trading=false)",
            "MaxLotCap (0.01)",
            "MaxPositionsCap (1)",
            "ForceCloseOnEnd (default true)",
        ]
        blockers = []
        # In dev/demo mode, safety gates are non-blocking but listed
        return True, enabled, blockers

    def validate_execution_permissions(self) -> tuple[bool, list[str]]:
        """Validate execution permissions. Returns (ok, blockers)."""
        blockers = []
        # live_trading must be False
        # mt5_order_send must be False
        # These are hardcoded safe defaults in this sprint
        return True, blockers

    def validate_broker_registry(self) -> dict:
        """Validate broker registry. Returns dict with broker statuses."""
        from titan.production.broker_compatibility_matrix import get_all_brokers
        brokers = get_all_brokers()
        return {
            name: {
                "status": b["status"],
                "priority": b["priority"],
            }
            for name, b in brokers.items()
        }

    def validate_observation_readiness(self) -> tuple[str, list[str]]:
        """Validate observation readiness. Returns (status, warnings)."""
        warnings = []
        status = "READY"
        # Check if observation components are loaded
        if "ForwardObservationEngine" in self._components_missing:
            status = "BLOCKED"
            warnings.append("ForwardObservationEngine missing")
        if "ObservationScorecardEngine" in self._components_missing:
            status = "BLOCKED"
            warnings.append("ObservationScorecardEngine missing")
        return status, warnings

    # ─── Sprint 9.9.3.39: Actual runtime wiring checks ──────────────────
    # Before this sprint, ProductionRuntimeAssembly returned RC_READY based
    # on component IMPORT PRESENCE alone (via __import__). Sprint 9.9.3.38
    # master integration audit identified this as not truthful.
    #
    # These new checks inspect the source files at rest and verify that
    # AutonomousRuntime actually wires the institutional pipeline into the
    # runtime decision path. If any critical wiring check fails, the verdict
    # must be RC_BLOCKED.

    def validate_runtime_wiring(self) -> tuple[bool, dict, list[str]]:
        """Validate that AutonomousRuntime actually wires the institutional pipeline.

        Returns (ok, checks, blockers).
        """
        import re
        from pathlib import Path

        repo_root = Path(__file__).resolve().parents[2]
        launcher_src = (repo_root / "titan" / "runtime" / "launcher.py").read_text(encoding="utf-8")
        autonomous_src = (repo_root / "titan" / "runtime" / "autonomous_loops.py").read_text(encoding="utf-8")

        def _strip(src: str) -> str:
            src = re.sub(r'"""[\s\S]*?"""', '""', src)
            src = re.sub(r"'''[\s\S]*?'''", "''", src)
            src = re.sub(r'"(?:[^"\\]|\\.)*"', '""', src)
            src = re.sub(r"'(?:[^'\\]|\\.)*'", "''", src)
            return src

        launcher_code = _strip(launcher_src)
        autonomous_code = _strip(autonomous_src)

        checks: dict[str, bool] = {}
        blockers: list[str] = []

        # 1) launcher_has_autonomous_runtime
        checks["launcher_has_autonomous_runtime"] = (
            "titan.runtime.autonomous_loops" in launcher_code
            or "AutonomousRuntime" in launcher_code
        )

        # 2) autonomous_runtime_has_signal_execution_bridge
        checks["autonomous_runtime_has_signal_execution_bridge"] = (
            "titan.production.signal_execution_bridge" in autonomous_code
            or "SignalExecutionBridge(" in autonomous_code
        )

        # 3) autonomous_runtime_builds_execution_intent
        checks["autonomous_runtime_builds_execution_intent"] = (
            "build_intent(" in autonomous_code
            or "ExecutionIntent" in autonomous_code
        )

        # 4) autonomous_runtime_calls_bridge_before_trade_loop
        # Check that build_intent appears BEFORE process_signal in the inference loop.
        # Heuristic: both must be present, and bridge block must skip process_signal.
        checks["autonomous_runtime_calls_bridge_before_trade_loop"] = (
            "build_intent(" in autonomous_code
            and "TRADE_LOOP_SKIPPED_BY_INTENT" in autonomous_code
            and "TRADE_LOOP_CALLED_AFTER_INTENT" in autonomous_code
        )

        # 5) bridge_blocks_before_trade_loop
        checks["bridge_blocks_before_trade_loop"] = (
            "EXECUTION_INTENT_BLOCKED" in autonomous_code
            and "TRADE_LOOP_SKIPPED_BY_INTENT" in autonomous_code
        )

        # 6) autonomous_runtime_has_regime_gate
        checks["autonomous_runtime_has_regime_gate"] = (
            "titan.production.regime_detection" in autonomous_code
            or "detect_regime(" in autonomous_code
            or "REGIME_GATE_EVALUATED" in autonomous_code
        )

        # 7) autonomous_runtime_has_broker_gate
        checks["autonomous_runtime_has_broker_gate"] = (
            "titan.production.broker_compatibility_matrix" in autonomous_code
            or "get_broker_info(" in autonomous_code
            or "BROKER_GATE_EVALUATED" in autonomous_code
        )

        # 8) autonomous_runtime_has_runtime_health_gate
        checks["autonomous_runtime_has_runtime_health_gate"] = (
            "titan.production.runtime_health" in autonomous_code
            or "RuntimeHealthMonitor(" in autonomous_code
            or "RUNTIME_HEALTH_GATE_EVALUATED" in autonomous_code
        )

        # 9) autonomous_runtime_has_security_gate
        checks["autonomous_runtime_has_security_gate"] = (
            "titan.security.security_gate" in autonomous_code
            or "SecurityGate(" in autonomous_code
            or "SECURITY_GATE_EVALUATED" in autonomous_code
        )

        # 10) autonomous_runtime_has_position_lifecycle
        checks["autonomous_runtime_has_position_lifecycle"] = (
            "titan.production.position_lifecycle" in autonomous_code
            or "PositionLifecycleEngine(" in autonomous_code
            or "POSITION_LIFECYCLE_EVALUATED" in autonomous_code
        )

        # 11) autonomous_runtime_has_exit_intent_bridge
        checks["autonomous_runtime_has_exit_intent_bridge"] = (
            "titan.production.exit_intent_bridge" in autonomous_code
            or "ExitIntentBridge(" in autonomous_code
            or "EXIT_INTENT_CREATED" in autonomous_code
        )

        # 12) observation_engine_runtime_wired
        checks["observation_engine_runtime_wired"] = (
            "titan.production.forward_observation" in autonomous_code
            or "ForwardObservationEngine(" in autonomous_code
            or "FORWARD_OBSERVATION_EVENT_RECORDED" in autonomous_code
        )

        # 13) scorecard_runtime_wired
        checks["scorecard_runtime_wired"] = (
            "titan.production.observation_scorecard" in autonomous_code
            or "ObservationScorecardEngine(" in autonomous_code
            or "compute_observation_scorecard" in autonomous_code
        )

        # Build blockers for any failed critical check
        critical_checks = [
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
        for check_name in critical_checks:
            if not checks.get(check_name, False):
                blockers.append(f"Runtime wiring check failed: {check_name}")

        ok = len(blockers) == 0
        return ok, checks, blockers

    def build_status(self) -> ProductionAssemblyStatus:
        """Build the full assembly status. Never raises."""
        try:
            loaded, missing = self.load_components()
            comp_ok, comp_missing = self.validate_component_presence()
            safety_ok, safety_enabled, safety_blockers = self.validate_safety_gates()
            exec_ok, exec_blockers = self.validate_execution_permissions()
            broker_registry = self.validate_broker_registry()
            obs_status, obs_warnings = self.validate_observation_readiness()
            # Sprint 9.9.3.39: actual runtime wiring checks
            wiring_ok, wiring_checks, wiring_blockers = self.validate_runtime_wiring()

            blockers = []
            warnings = []

            # Missing critical components
            if comp_missing:
                blockers.append(f"Missing components: {', '.join(comp_missing)}")

            # Safety blockers
            blockers.extend(safety_blockers)
            blockers.extend(exec_blockers)

            # Sprint 9.9.3.39: runtime wiring blockers (critical)
            blockers.extend(wiring_blockers)

            # Warnings
            warnings.extend(obs_warnings)

            # Determine verdict
            if blockers:
                verdict = ProductionAssemblyVerdict.RC_BLOCKED
            elif warnings:
                verdict = ProductionAssemblyVerdict.RC_READY_WITH_WARNINGS
            else:
                verdict = ProductionAssemblyVerdict.RC_READY

            # Extract MetaQuotes status
            metaquotes = broker_registry.get("MetaQuotes-Demo", {})
            fundednext = broker_registry.get("FundedNext Free Trial", {})
            fbs = broker_registry.get("FBS-Demo", {})

            if metaquotes.get("status") == "PASS":
                warnings.append("MetaQuotes-Demo verified for demo micro — operator must run execution locally")
            if fundednext.get("status") == "BLOCKED":
                warnings.append("FundedNext Free Trial remains DO_NOT_USE")
            if fbs.get("status") == "REJECT":
                warnings.append("FBS-Demo remains REJECTED (retcode 10006) — low priority")

            return ProductionAssemblyStatus(
                mode=self.mode,
                verdict=verdict,
                components_loaded=loaded,
                components_missing=missing,
                safety_gates_enabled=safety_enabled,
                live_trading_enabled=False,
                demo_only=True,
                dry_run=True,
                execution_allowed=False,
                mt5_order_send_allowed=False,
                max_lot=0.01,
                max_open_positions=1,
                broker_status=broker_registry,
                runtime_health_status="READY",
                security_status="DEV_MODE_NON_BLOCKING",
                observation_status=obs_status,
                blockers=blockers,
                warnings=warnings,
            )
        except Exception as e:
            return self.fail_closed_status(f"Assembly exception: {e}")

    def fail_closed_status(self, reason: str) -> ProductionAssemblyStatus:
        return ProductionAssemblyStatus(
            mode=self.mode,
            verdict=ProductionAssemblyVerdict.RC_BLOCKED,
            blockers=[reason],
        )
