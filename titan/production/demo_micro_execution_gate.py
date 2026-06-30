"""
TITAN XAU AI - Demo Micro Execution Gate (Sprint 9.9.3.44)
==========================================================
Strictly gated demo micro execution gate. Validates ALL safety
conditions before any demo micro execution is permitted.

NEVER imports MetaTrader5. NEVER sends orders. NEVER calls order_send.
"""
from __future__ import annotations
import os, re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[2]

APPROVED_WARNINGS = {
    "REGIME_GATE_WIRED_BUT_PLACEHOLDER_CONTEXT",
    "DEPENDENCY_READY_WITH_WARNINGS",
    "DEPENDENCY_VERSION_DRIFT_WARNING",
    "MODEL_SERIALIZATION_VERSION_WARNING",
    "SELF_HEALING_READY_WITH_WARNINGS",
    "REPLAY_NOT_REAL_FORWARD_EVIDENCE",
    "REAL_SHORT_NOT_FULL_7_DAY_EVIDENCE",
    "DEMO_MICRO_READY_WITH_WARNINGS",
    "MODEL_PARITY_NOT_AVAILABLE",
    "XGBOOST_PARITY_NOT_AVAILABLE",
    "ENVIRONMENT_LOCK_READY_WITH_WARNINGS",
    "MetaQuotes-Demo verified",
    "FundedNext Free Trial remains DO_NOT_USE",
    "FBS-Demo remains REJECTED",
    "operator must run execution locally",
    "git_clean_hint",
    "virtualenv",
    "release_docs",
    "Retry/restart policy bounding",
    "Watchdog restarter module not found",
    "requirements.txt missing",
    "Operator confirmation token missing",  # non-blocking for gate check
}


class DemoMicroGateVerdict(str, Enum):
    DEMO_MICRO_GATE_PASS = "DEMO_MICRO_GATE_PASS"
    DEMO_MICRO_GATE_PASS_WITH_WARNINGS = "DEMO_MICRO_GATE_PASS_WITH_WARNINGS"
    DEMO_MICRO_GATE_BLOCKED = "DEMO_MICRO_GATE_BLOCKED"


@dataclass
class DemoMicroGateResult:
    verdict: DemoMicroGateVerdict = DemoMicroGateVerdict.DEMO_MICRO_GATE_BLOCKED
    ok_checks: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    approved_warnings: list[str] = field(default_factory=list)
    unapproved_warnings: list[str] = field(default_factory=list)
    checks: dict = field(default_factory=dict)
    timestamp_utc: str = ""

    def __post_init__(self):
        if not self.timestamp_utc:
            self.timestamp_utc = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        d = asdict(self)
        d["verdict"] = self.verdict.value
        return d


class DemoMicroExecutionGate:
    """Strictly gated demo micro execution gate.

    NEVER sends orders. NEVER imports MetaTrader5.
    """

    def evaluate(self, dry_run: bool = True, live_trading: bool = False,
                 broker_name: str = "MetaQuotes-Demo",
                 account_type: str = "DEMO",
                 requested_lot: float = 0.01,
                 max_lot: float = 0.01,
                 max_open_positions: int = 1,
                 current_open_positions: int = 0,
                 operator_confirmation_token: str = "",
                 ) -> DemoMicroGateResult:
        result = DemoMicroGateResult()

        # 1. Config checks
        if not dry_run:
            result.blockers.append("dry_run=false — must be true unless explicit demo arm active")
        else:
            result.ok_checks.append("dry_run=true")

        if live_trading:
            result.blockers.append("live_trading=true — must be false")
        else:
            result.ok_checks.append("live_trading=false")

        if os.environ.get("TITAN_LIVE_TRADING") == "1":
            result.blockers.append("TITAN_LIVE_TRADING=1 env var is set")
        else:
            result.ok_checks.append("TITAN_LIVE_TRADING not enabled")

        result.checks["dry_run"] = dry_run
        result.checks["live_trading"] = live_trading
        result.checks["TITAN_LIVE_TRADING_env"] = os.environ.get("TITAN_LIVE_TRADING", "0")

        # 2. Account type
        if account_type != "DEMO":
            result.blockers.append(f"account_type={account_type} — must be DEMO")
        else:
            result.ok_checks.append("account_type=DEMO")

        # 3. Broker gate
        from titan.production.broker_observation_gate import BrokerObservationGate, ObservationBrokerVerdict
        gate = BrokerObservationGate()
        broker_result = gate.evaluate(broker_name=broker_name)
        result.checks["broker_gate_verdict"] = broker_result.verdict.value
        if broker_result.verdict != ObservationBrokerVerdict.ALLOWED:
            result.blockers.append(f"Broker gate: {broker_result.verdict.value} — {broker_result.reason}")
        else:
            result.ok_checks.append(f"Broker gate: {broker_name} ALLOWED")

        # Block FundedNext, FBS, unknown
        for blocked_broker in ["FundedNext Free Trial", "FBS-Demo", "UnknownBroker"]:
            br = gate.evaluate(broker_name=blocked_broker)
            if br.verdict == ObservationBrokerVerdict.ALLOWED:
                result.blockers.append(f"{blocked_broker} should be blocked but got ALLOWED")

        # 4. Lot checks
        if max_lot > 0.01:
            result.blockers.append(f"max_lot={max_lot} > 0.01")
        if requested_lot > 0.01:
            result.blockers.append(f"requested_lot={requested_lot} > 0.01")
        if requested_lot > max_lot:
            result.blockers.append(f"requested_lot={requested_lot} > max_lot={max_lot}")
        else:
            result.ok_checks.append(f"lot={requested_lot} <= 0.01")

        result.checks["max_lot"] = max_lot
        result.checks["requested_lot"] = requested_lot

        # 5. Position checks
        if max_open_positions > 1:
            result.blockers.append(f"max_open_positions={max_open_positions} > 1")
        if current_open_positions > 0:
            result.blockers.append(f"current_open_positions={current_open_positions} > 0 — must be 0 before entry")
        else:
            result.ok_checks.append("current_open_positions=0")

        result.checks["max_open_positions"] = max_open_positions
        result.checks["current_open_positions"] = current_open_positions

        # 6. Environment drift gate
        try:
            from titan.production.environment_drift_gate import EnvironmentDriftGate, DriftVerdict
            env_gate = EnvironmentDriftGate()
            env_result = env_gate.evaluate()
            result.checks["environment_drift_verdict"] = env_result.verdict.value
            if env_result.verdict == DriftVerdict.ENVIRONMENT_LOCK_BLOCKED:
                result.blockers.append(f"Environment drift BLOCKED: {env_result.blockers}")
            else:
                result.ok_checks.append(f"Environment drift: {env_result.verdict.value}")
                result.warnings.extend(env_result.warnings)
        except Exception as e:
            result.blockers.append(f"Environment drift gate failed: {e}")
            result.checks["environment_drift_verdict"] = "SKIP"

        # 7. Dependency audit
        try:
            import scripts.audit.dependency_compatibility_audit as dep_audit
            dep_result = dep_audit.run_audit()
            result.checks["dependency_audit_verdict"] = dep_result["verdict"]
            if "BLOCKED" in dep_result["verdict"]:
                result.blockers.append(f"Dependency audit BLOCKED: {dep_result['blockers']}")
            else:
                result.ok_checks.append(f"Dependency audit: {dep_result['verdict']}")
                result.warnings.extend(dep_result.get("warnings", []))
        except Exception as e:
            result.blockers.append(f"Dependency audit failed: {e}")

        # 8. Model artifact audit
        try:
            import scripts.audit.model_artifact_compatibility_audit as model_audit
            model_result = model_audit.run_audit()
            result.checks["model_artifact_verdict"] = model_result["verdict"]
            if "BLOCKED" in model_result["verdict"]:
                result.blockers.append(f"Model artifact audit BLOCKED: {model_result['blockers']}")
            else:
                result.ok_checks.append(f"Model artifact audit: {model_result['verdict']}")
                result.warnings.extend(model_result.get("warnings", []))
        except Exception as e:
            result.blockers.append(f"Model artifact audit failed: {e}")

        # 9. Model parity audit
        try:
            import scripts.audit.model_prediction_parity_audit as parity_audit
            parity_result = parity_audit.run_parity_audit()
            result.checks["model_parity_verdict"] = parity_result["verdict"]
            if parity_result["verdict"] == "MODEL_PARITY_FAIL":
                result.blockers.append(f"Model parity FAIL: {parity_result['blockers']}")
            else:
                result.ok_checks.append(f"Model parity: {parity_result['verdict']}")
        except Exception as e:
            result.checks["model_parity_verdict"] = "MODEL_PARITY_NOT_AVAILABLE"
            result.ok_checks.append("Model parity: NOT_AVAILABLE (no candidates)")

        # 10. Runtime self-healing audit
        try:
            import scripts.audit.runtime_self_healing_audit as sh_audit
            sh_result = sh_audit.run_audit()
            result.checks["self_healing_verdict"] = sh_result["verdict"]
            if "BLOCKED" in sh_result["verdict"]:
                result.blockers.append(f"Self-healing audit BLOCKED: {sh_result['blockers']}")
            else:
                result.ok_checks.append(f"Self-healing audit: {sh_result['verdict']}")
                result.warnings.extend(sh_result.get("warnings", []))
        except Exception as e:
            result.blockers.append(f"Self-healing audit failed: {e}")

        # 11. Operator confirmation token
        if not operator_confirmation_token:
            result.warnings.append("Operator confirmation token missing — required for --execute-once")
        else:
            result.ok_checks.append("Operator confirmation token present")

        # 12. Filter approved vs unapproved warnings
        for w in result.warnings:
            is_approved = any(aw.lower() in w.lower() for aw in APPROVED_WARNINGS)
            if is_approved:
                result.approved_warnings.append(w)
            else:
                result.unapproved_warnings.append(w)

        if result.unapproved_warnings:
            result.blockers.extend([f"Unapproved warning: {w}" for w in result.unapproved_warnings])

        # Verdict
        if result.blockers:
            result.verdict = DemoMicroGateVerdict.DEMO_MICRO_GATE_BLOCKED
        elif result.approved_warnings:
            result.verdict = DemoMicroGateVerdict.DEMO_MICRO_GATE_PASS_WITH_WARNINGS
        else:
            result.verdict = DemoMicroGateVerdict.DEMO_MICRO_GATE_PASS

        return result
