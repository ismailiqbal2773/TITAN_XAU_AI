"""
TITAN XAU AI — Forward Observation Engine (Sprint 9.9.3.32)
============================================================

Collects and summarizes dry-run/demo-safe forward evidence over time.
Observes signals, execution intents, regimes, broker health, runtime
health, exit intents, safety blocks, and journal completeness.

Never imports MetaTrader5. Never sends orders. Only observes + reports.
"""
from __future__ import annotations
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional


class ForwardObservationEventType(str, Enum):
    SIGNAL_OBSERVED = "SIGNAL_OBSERVED"
    EXECUTION_INTENT_OBSERVED = "EXECUTION_INTENT_OBSERVED"
    REGIME_OBSERVED = "REGIME_OBSERVED"
    BROKER_HEALTH_OBSERVED = "BROKER_HEALTH_OBSERVED"
    RUNTIME_HEALTH_OBSERVED = "RUNTIME_HEALTH_OBSERVED"
    EXIT_INTENT_OBSERVED = "EXIT_INTENT_OBSERVED"
    SAFETY_BLOCK_OBSERVED = "SAFETY_BLOCK_OBSERVED"
    HEARTBEAT_OBSERVED = "HEARTBEAT_OBSERVED"
    OBSERVATION_GAP = "OBSERVATION_GAP"
    UNKNOWN = "UNKNOWN"


@dataclass
class ForwardObservationEvent:
    event_type: ForwardObservationEventType = ForwardObservationEventType.UNKNOWN
    timestamp_utc: str = ""
    symbol: str = "XAUUSD"
    timeframe: str = "H1"
    source: str = ""
    payload: dict = field(default_factory=dict)
    severity: str = "INFO"       # INFO / WARNING / CRITICAL
    safe: bool = True
    reason: str = ""


@dataclass
class ForwardObservationSummary:
    start_utc: str = ""
    end_utc: str = ""
    total_events: int = 0
    signal_count: int = 0
    execution_intent_count: int = 0
    exit_intent_count: int = 0
    regime_count: int = 0
    safety_block_count: int = 0
    heartbeat_count: int = 0
    observation_gap_count: int = 0
    broker_health_count: int = 0
    runtime_health_count: int = 0
    unknown_count: int = 0
    safe_to_continue_observation: bool = True
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# Mapping from raw journal event strings to observation types
_EVENT_TYPE_MAP = {
    "SIGNAL_CREATED": ForwardObservationEventType.SIGNAL_OBSERVED,
    "ADAPTER_PRE_SEND_DIAGNOSTICS": ForwardObservationEventType.EXECUTION_INTENT_OBSERVED,
    "DEMO_MICRO_ORDER_REQUESTED": ForwardObservationEventType.EXECUTION_INTENT_OBSERVED,
    "ADAPTER_BROKER_STATE_SNAPSHOT": ForwardObservationEventType.BROKER_HEALTH_OBSERVED,
    "ADAPTER_ORDER_CHECK_ATTEMPTED": ForwardObservationEventType.EXECUTION_INTENT_OBSERVED,
    "ADAPTER_ORDER_SEND_RESULT": ForwardObservationEventType.EXECUTION_INTENT_OBSERVED,
    "DEMO_MICRO_ORDER_FAILED": ForwardObservationEventType.SAFETY_BLOCK_OBSERVED,
    "DEMO_MICRO_MANUAL_REVIEW_REQUIRED": ForwardObservationEventType.SAFETY_BLOCK_OBSERVED,
    "DEMO_MICRO_EMERGENCY_CLOSE_TRIGGERED": ForwardObservationEventType.SAFETY_BLOCK_OBSERVED,
    "DEMO_MICRO_PROFILE_MISMATCH_BLOCKED": ForwardObservationEventType.SAFETY_BLOCK_OBSERVED,
    "DEMO_MICRO_ORDER_SEND_NONE": ForwardObservationEventType.SAFETY_BLOCK_OBSERVED,
    "DEMO_MICRO_FULL_CYCLE_PASS": ForwardObservationEventType.HEARTBEAT_OBSERVED,
    "DEMO_MICRO_EXECUTE_BLOCKED": ForwardObservationEventType.SAFETY_BLOCK_OBSERVED,
    "MARKET_CLOSED": ForwardObservationEventType.SAFETY_BLOCK_OBSERVED,
    "REPEATABILITY_CYCLE_PASS": ForwardObservationEventType.HEARTBEAT_OBSERVED,
    "REPEATABILITY_CYCLE_FAIL": ForwardObservationEventType.SAFETY_BLOCK_OBSERVED,
    "REPEATABILITY_CYCLE_START": ForwardObservationEventType.EXECUTION_INTENT_OBSERVED,
    "REPEATABILITY_CYCLE_HOLDING": ForwardObservationEventType.HEARTBEAT_OBSERVED,
    "ADAPTER_RAW_PROFILE_LOADED": ForwardObservationEventType.EXECUTION_INTENT_OBSERVED,
    "ADAPTER_RAW_NAKED_ORDER_ATTEMPTED": ForwardObservationEventType.EXECUTION_INTENT_OBSERVED,
    "ADAPTER_SLTP_MODIFY_ATTEMPTED": ForwardObservationEventType.EXIT_INTENT_OBSERVED,
    "ADAPTER_SLTP_MODIFY_RESULT": ForwardObservationEventType.EXIT_INTENT_OBSERVED,
    "ADAPTER_SLTP_MODIFY_SUCCESS": ForwardObservationEventType.EXIT_INTENT_OBSERVED,
    "ADAPTER_EMERGENCY_CLOSE_IF_SLTP_FAILED": ForwardObservationEventType.SAFETY_BLOCK_OBSERVED,
    "ADAPTER_EMERGENCY_CLOSE_REQUIRED": ForwardObservationEventType.SAFETY_BLOCK_OBSERVED,
    "ADAPTER_POSITION_CHECK_AFTER_FAILURE": ForwardObservationEventType.SAFETY_BLOCK_OBSERVED,
}


class ForwardObservationEngine:
    """Observes and summarizes forward evidence. No MT5, no orders."""

    def load_events_from_jsonl(self, paths: list[str]) -> list[ForwardObservationEvent]:
        """Load events from JSONL journal files.

        Returns list of normalized ForwardObservationEvent.
        Never raises — skips malformed lines/files.
        """
        events = []
        for path_str in paths:
            path = Path(path_str)
            if not path.exists():
                continue
            try:
                with open(path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            raw = json.loads(line)
                        except Exception:
                            continue
                        event = self.normalize_event(raw)
                        events.append(event)
            except Exception:
                continue
        return events

    def normalize_event(self, raw: dict) -> ForwardObservationEvent:
        """Normalize a raw journal event into ForwardObservationEvent.

        Never raises — returns UNKNOWN on malformed input.
        """
        try:
            raw_event = raw.get("event", raw.get("event_type", ""))
            obs_type = _EVENT_TYPE_MAP.get(raw_event, ForwardObservationEventType.UNKNOWN)

            # If not in map, try to infer from event string
            if obs_type == ForwardObservationEventType.UNKNOWN and raw_event:
                upper = raw_event.upper()
                if "SIGNAL" in upper:
                    obs_type = ForwardObservationEventType.SIGNAL_OBSERVED
                elif "BLOCK" in upper or "FAIL" in upper or "EMERGENCY" in upper:
                    obs_type = ForwardObservationEventType.SAFETY_BLOCK_OBSERVED
                elif "HEARTBEAT" in upper or "PASS" in upper or "CYCLE_PASS" in upper:
                    obs_type = ForwardObservationEventType.HEARTBEAT_OBSERVED
                elif "REGIME" in upper:
                    obs_type = ForwardObservationEventType.REGIME_OBSERVED
                elif "EXIT" in upper or "SLTP" in upper or "CLOSE" in upper:
                    obs_type = ForwardObservationEventType.EXIT_INTENT_OBSERVED
                elif "BROKER" in upper or "ADAPTER_BROKER" in upper:
                    obs_type = ForwardObservationEventType.BROKER_HEALTH_OBSERVED
                elif "HEALTH" in upper or "RUNTIME" in upper:
                    obs_type = ForwardObservationEventType.RUNTIME_HEALTH_OBSERVED
                elif "ORDER" in upper or "INTENT" in upper or "SEND" in upper:
                    obs_type = ForwardObservationEventType.EXECUTION_INTENT_OBSERVED

            ts = raw.get("timestamp_utc", raw.get("timestamp", ""))
            symbol = raw.get("symbol", "XAUUSD")
            timeframe = raw.get("timeframe", "H1")
            source = raw_event or "unknown"
            payload = {k: v for k, v in raw.items()
                        if k not in ("event", "event_type", "timestamp_utc", "timestamp")}
            severity = "INFO"
            safe = True
            reason = ""

            if obs_type == ForwardObservationEventType.SAFETY_BLOCK_OBSERVED:
                severity = "CRITICAL"
                safe = False
                reason = raw.get("reason", raw.get("error", "Safety block observed"))
            elif obs_type == ForwardObservationEventType.OBSERVATION_GAP:
                severity = "WARNING"
                reason = "Observation gap detected"

            return ForwardObservationEvent(
                event_type=obs_type,
                timestamp_utc=ts,
                symbol=symbol,
                timeframe=timeframe,
                source=source,
                payload=payload,
                severity=severity,
                safe=safe,
                reason=reason,
            )
        except Exception:
            return ForwardObservationEvent(
                event_type=ForwardObservationEventType.UNKNOWN,
                source="normalize_error",
                safe=False,
                reason="Malformed event",
            )

    def detect_observation_gaps(self, events: list[ForwardObservationEvent],
                                 max_gap_seconds: int = 3600) -> list[ForwardObservationEvent]:
        """Detect observation gaps between consecutive events.

        Returns list of OBSERVATION_GAP events inserted at gap points.
        """
        gaps = []
        if len(events) < 2:
            return gaps

        # Sort by timestamp
        sorted_events = sorted(events, key=lambda e: e.timestamp_utc)

        for i in range(1, len(sorted_events)):
            prev_ts = self._parse_ts(sorted_events[i - 1].timestamp_utc)
            curr_ts = self._parse_ts(sorted_events[i].timestamp_utc)
            if prev_ts is None or curr_ts is None:
                continue
            delta = (curr_ts - prev_ts).total_seconds()
            if delta > max_gap_seconds:
                gaps.append(ForwardObservationEvent(
                    event_type=ForwardObservationEventType.OBSERVATION_GAP,
                    timestamp_utc=sorted_events[i].timestamp_utc,
                    symbol=sorted_events[i].symbol,
                    source="gap_detector",
                    payload={"gap_seconds": delta, "prev_ts": sorted_events[i-1].timestamp_utc,
                              "curr_ts": sorted_events[i].timestamp_utc},
                    severity="WARNING",
                    safe=True,
                    reason=f"Observation gap: {delta:.0f}s > {max_gap_seconds}s",
                ))
        return gaps

    def summarize(self, events: list[ForwardObservationEvent]) -> ForwardObservationSummary:
        """Summarize a list of events into a ForwardObservationSummary."""
        summary = ForwardObservationSummary(
            total_events=len(events),
        )

        if not events:
            summary.safe_to_continue_observation = True
            summary.warnings.append("No events to summarize")
            return summary

        # Time range
        timestamps = [e.timestamp_utc for e in events if e.timestamp_utc]
        if timestamps:
            summary.start_utc = min(timestamps)
            summary.end_utc = max(timestamps)

        # Count by type
        for e in events:
            if e.event_type == ForwardObservationEventType.SIGNAL_OBSERVED:
                summary.signal_count += 1
            elif e.event_type == ForwardObservationEventType.EXECUTION_INTENT_OBSERVED:
                summary.execution_intent_count += 1
            elif e.event_type == ForwardObservationEventType.EXIT_INTENT_OBSERVED:
                summary.exit_intent_count += 1
            elif e.event_type == ForwardObservationEventType.REGIME_OBSERVED:
                summary.regime_count += 1
            elif e.event_type == ForwardObservationEventType.SAFETY_BLOCK_OBSERVED:
                summary.safety_block_count += 1
            elif e.event_type == ForwardObservationEventType.HEARTBEAT_OBSERVED:
                summary.heartbeat_count += 1
            elif e.event_type == ForwardObservationEventType.OBSERVATION_GAP:
                summary.observation_gap_count += 1
            elif e.event_type == ForwardObservationEventType.BROKER_HEALTH_OBSERVED:
                summary.broker_health_count += 1
            elif e.event_type == ForwardObservationEventType.RUNTIME_HEALTH_OBSERVED:
                summary.runtime_health_count += 1
            elif e.event_type == ForwardObservationEventType.UNKNOWN:
                summary.unknown_count += 1

            # Check safety
            if not e.safe:
                if e.severity == "CRITICAL":
                    summary.blockers.append(f"{e.source}: {e.reason}")
                    summary.safe_to_continue_observation = False
                elif e.severity == "WARNING":
                    summary.warnings.append(f"{e.source}: {e.reason}")

        # Gap warnings
        if summary.observation_gap_count > 0:
            summary.warnings.append(
                f"{summary.observation_gap_count} observation gap(s) detected"
            )

        # Unknown event warnings
        if summary.unknown_count > 0:
            ratio = summary.unknown_count / summary.total_events
            if ratio > 0.3:
                summary.warnings.append(
                    f"High unknown event ratio: {summary.unknown_count}/{summary.total_events} "
                    f"({ratio:.0%})"
                )

        return summary

    def _parse_ts(self, ts_str: str) -> Optional[datetime]:
        """Parse an ISO timestamp string. Returns None on failure."""
        if not ts_str:
            return None
        try:
            return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        except Exception:
            return None
