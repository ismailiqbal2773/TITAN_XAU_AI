"""
TITAN XAU AI - Broker Observation Gate (Sprint 9.9.3.41.1)
============================================================

Thin adapter that reuses the EXISTING broker intelligence /
broker compatibility matrix / broker quality engine to enforce the
broker gate for controlled 7-day demo observation.

This module does NOT duplicate broker detection, scoring, or
compatibility logic. It calls the existing APIs:
  - titan.production.broker_compatibility_matrix.get_broker_info()
  - titan.production.broker_compatibility_matrix.get_all_brokers()
  - titan.production.broker_intelligence.BrokerIntelligenceLayer (optional)
  - titan.production.broker_quality_engine.BrokerQualityEngine (optional)

NEVER imports MetaTrader5.
NEVER sends orders.
NEVER calls order_send.
NEVER runs DEMO_MICRO_EXECUTE.
NEVER runs raw_mt5_probe.

For the current controlled 7-day observation, the ONLY allowed broker is
MetaQuotes-Demo because it has verified demo micro PASS evidence.

Future brokers require:
  - broker compatibility PASS
  - broker score PASS (if available)
  - explicit operator approval
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


# The only broker allowed for the current controlled 7-day observation.
# This is NOT a permanent restriction — future commercial users may use
# other brokers once they pass compatibility + score + operator approval.
ALLOWED_OBSERVATION_BROKER = "MetaQuotes-Demo"

# Brokers that are explicitly blocked for any observation.
BLOCKED_BROKERS = {
    "FundedNext Free Trial": "DO_NOT_USE - EA/Python automation not allowed",
    "FBS-Demo": "REJECTED (retcode 10006) - low priority, compatibility retest required",
}

# Brokers that are pending verification.
PENDING_BROKERS = {
    "Exness Demo": "PENDING - not yet tested",
    "ICMarkets Demo": "PENDING - not yet tested",
}


class ObservationBrokerVerdict(str, Enum):
    ALLOWED = "ALLOWED"
    BLOCKED = "BLOCKED"
    PENDING = "PENDING"
    UNKNOWN = "UNKNOWN"


@dataclass
class BrokerObservationGateResult:
    """Result of the broker observation gate check."""
    verdict: ObservationBrokerVerdict
    broker_name: str = ""
    registry_status: str = ""
    registry_priority: str = ""
    broker_score: Optional[float] = None
    broker_band: str = ""
    capability_score: Optional[float] = None
    observation_eligible: bool = False
    reason: str = ""
    next_action: str = ""
    timestamp_utc: str = ""

    def __post_init__(self):
        if not self.timestamp_utc:
            self.timestamp_utc = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        d = asdict(self)
        d["verdict"] = self.verdict.value
        return d


class BrokerObservationGate:
    """Thin adapter that reuses existing broker intelligence modules.

    Never duplicates broker detection, scoring, or compatibility logic.
    Calls existing APIs:
      - broker_compatibility_matrix.get_broker_info()
      - broker_compatibility_matrix.get_all_brokers()
      - BrokerIntelligenceLayer (optional, if MT5 available)
      - BrokerQualityEngine (optional, if score input available)
    """

    def __init__(self, broker_intelligence=None, broker_quality_engine=None):
        """Initialize with optional existing broker intelligence engines.

        Args:
            broker_intelligence: Existing BrokerIntelligenceLayer instance (optional).
            broker_quality_engine: Existing BrokerQualityEngine instance (optional).
        """
        self.broker_intelligence = broker_intelligence
        self.broker_quality_engine = broker_quality_engine

    # ──────────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────────

    def evaluate(self, broker_name: str = "") -> BrokerObservationGateResult:
        """Evaluate broker eligibility for 7-day observation.

        Args:
            broker_name: Broker server name. If empty, attempts to detect
                         via BrokerIntelligenceLayer (if available).

        Returns:
            BrokerObservationGateResult with verdict + reason + next_action.
        """
        # If no broker name provided, try to detect via existing intelligence
        if not broker_name and self.broker_intelligence is not None:
            try:
                info = self.broker_intelligence.detect()
                if info is not None:
                    broker_name = info.server or info.broker_name or ""
            except Exception:
                pass

        # If still no broker name, return UNKNOWN
        if not broker_name:
            return BrokerObservationGateResult(
                verdict=ObservationBrokerVerdict.UNKNOWN,
                reason="No broker detected and no broker name provided",
                next_action="Connect MetaQuotes-Demo for 7-day observation",
            )

        # Use existing broker_compatibility_matrix to get registry status
        try:
            from titan.production.broker_compatibility_matrix import get_broker_info
            registry_info = get_broker_info(broker_name)
        except Exception as e:
            return BrokerObservationGateResult(
                verdict=ObservationBrokerVerdict.UNKNOWN,
                broker_name=broker_name,
                reason=f"BrokerCompatibilityMatrix lookup failed: {e}",
                next_action="Verify broker_compatibility_matrix.py is importable",
            )

        registry_status = registry_info.get("status", "UNKNOWN")
        registry_priority = registry_info.get("priority", "MEDIUM")

        # Get broker score if quality engine is available
        broker_score = None
        broker_band = ""
        if self.broker_quality_engine is not None:
            try:
                last_score = self.broker_quality_engine.last_score()
                if last_score is not None:
                    broker_score = float(last_score.score)
                    broker_band = self.broker_quality_engine.last_band() or ""
            except Exception:
                pass

        # Determine verdict based on registry status
        # For controlled 7-day observation, ONLY MetaQuotes-Demo is allowed
        if broker_name == ALLOWED_OBSERVATION_BROKER:
            if registry_status == "PASS":
                return BrokerObservationGateResult(
                    verdict=ObservationBrokerVerdict.ALLOWED,
                    broker_name=broker_name,
                    registry_status=registry_status,
                    registry_priority=registry_priority,
                    broker_score=broker_score,
                    broker_band=broker_band,
                    observation_eligible=True,
                    reason=f"{broker_name} is verified for demo micro (PASS) - allowed for 7-day observation",
                    next_action="Proceed with 7-day observation in dry_run mode",
                )
            else:
                return BrokerObservationGateResult(
                    verdict=ObservationBrokerVerdict.BLOCKED,
                    broker_name=broker_name,
                    registry_status=registry_status,
                    registry_priority=registry_priority,
                    reason=f"{broker_name} registry status is {registry_status}, expected PASS",
                    next_action="Re-verify MetaQuotes-Demo compatibility before observation",
                )

        # Check blocked brokers
        if broker_name in BLOCKED_BROKERS:
            return BrokerObservationGateResult(
                verdict=ObservationBrokerVerdict.BLOCKED,
                broker_name=broker_name,
                registry_status=registry_status,
                registry_priority=registry_priority,
                reason=f"{broker_name} is BLOCKED: {BLOCKED_BROKERS[broker_name]}",
                next_action="Use MetaQuotes-Demo for 7-day observation",
            )

        # Check pending brokers
        if broker_name in PENDING_BROKERS:
            return BrokerObservationGateResult(
                verdict=ObservationBrokerVerdict.PENDING,
                broker_name=broker_name,
                registry_status=registry_status,
                registry_priority=registry_priority,
                reason=f"{broker_name} is PENDING: {PENDING_BROKERS[broker_name]}",
                next_action="Run raw_mt5_probe + demo_micro_repeatability to verify, then re-evaluate",
            )

        # Check registry status for other brokers
        if registry_status == "BLOCKED":
            return BrokerObservationGateResult(
                verdict=ObservationBrokerVerdict.BLOCKED,
                broker_name=broker_name,
                registry_status=registry_status,
                registry_priority=registry_priority,
                reason=f"{broker_name} registry status=BLOCKED",
                next_action="Use MetaQuotes-Demo for 7-day observation",
            )
        if registry_status == "REJECT":
            return BrokerObservationGateResult(
                verdict=ObservationBrokerVerdict.BLOCKED,
                broker_name=broker_name,
                registry_status=registry_status,
                registry_priority=registry_priority,
                reason=f"{broker_name} registry status=REJECT",
                next_action="Use MetaQuotes-Demo for 7-day observation",
            )
        if registry_status == "PENDING":
            return BrokerObservationGateResult(
                verdict=ObservationBrokerVerdict.PENDING,
                broker_name=broker_name,
                registry_status=registry_status,
                registry_priority=registry_priority,
                reason=f"{broker_name} registry status=PENDING - not yet verified",
                next_action="Verify compatibility before observation",
            )
        if registry_status == "UNKNOWN":
            return BrokerObservationGateResult(
                verdict=ObservationBrokerVerdict.UNKNOWN,
                broker_name=broker_name,
                registry_status=registry_status,
                registry_priority=registry_priority,
                reason=f"{broker_name} is unknown - not in registry",
                next_action="Add broker to registry and verify before observation",
            )

        # Default: blocked (only MetaQuotes-Demo is allowed for this controlled observation)
        return BrokerObservationGateResult(
            verdict=ObservationBrokerVerdict.BLOCKED,
            broker_name=broker_name,
            registry_status=registry_status,
            registry_priority=registry_priority,
            broker_score=broker_score,
            broker_band=broker_band,
            reason=f"{broker_name} is not the allowed observation broker ({ALLOWED_OBSERVATION_BROKER})",
            next_action=f"Use {ALLOWED_OBSERVATION_BROKER} for current 7-day observation",
        )

    def list_allowed_brokers(self) -> list[str]:
        """List brokers allowed for current 7-day observation."""
        return [ALLOWED_OBSERVATION_BROKER]

    def list_blocked_brokers(self) -> dict[str, str]:
        """List brokers blocked for current 7-day observation."""
        return dict(BLOCKED_BROKERS)

    def list_pending_brokers(self) -> dict[str, str]:
        """List brokers pending verification."""
        return dict(PENDING_BROKERS)

    def summary(self) -> dict:
        """Return a summary of the broker observation gate."""
        return {
            "allowed_observation_broker": ALLOWED_OBSERVATION_BROKER,
            "blocked_brokers": dict(BLOCKED_BROKERS),
            "pending_brokers": dict(PENDING_BROKERS),
            "broker_intelligence_wired": self.broker_intelligence is not None,
            "broker_quality_engine_wired": self.broker_quality_engine is not None,
            "auto_switch_allowed": False,  # always False - operator approval required
        }
