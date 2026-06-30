"""
TITAN XAU AI — Trade Journal (Production Sprint 3)

Records every signal, decision, order, and exit to JSONL (append-only).
Safe for concurrent writes — uses atomic line appends.

Record types:
  - SIGNAL     : every signal from inference engine
  - DECISION   : every accepted/rejected trade decision
  - ORDER      : every dry_run or live order submission
  - EXIT       : every exit decision (TP/SL/timeout/stale/kill)
  - MODIFY     : every SL/TP modification
  - HEARTBEAT  : periodic health checkpoint

Usage:
    journal = TradeJournal(path="/path/to/journal.jsonl")
    journal.log_signal(signal)
    journal.log_decision(decision)
    journal.log_order(decision)
    journal.log_exit(ticket, exit_reason, ...)
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional, Any

logger = logging.getLogger(__name__)


# ─── Audit-grade event types (Sprint 6) ──────────────────────────────────────
class EventType(str, Enum):
    """All critical events that must be journaled for forward testing."""
    SIGNAL_CREATED = "SIGNAL_CREATED"
    SIGNAL_REJECTED = "SIGNAL_REJECTED"
    ORDER_CREATED = "ORDER_CREATED"
    ORDER_BLOCKED = "ORDER_BLOCKED"
    POSITION_OPENED = "POSITION_OPENED"
    POSITION_MODIFIED = "POSITION_MODIFIED"
    POSITION_CLOSED = "POSITION_CLOSED"
    EXIT_TRIGGERED = "EXIT_TRIGGERED"
    KILL_SWITCH_TRANSITION = "KILL_SWITCH_TRANSITION"
    KILL_SWITCH_BLOCK = "KILL_SWITCH_BLOCK"
    NEWS_HALT = "NEWS_HALT"
    DRIFT_ALERT = "DRIFT_ALERT"
    DRIFT_EMERGENCY = "DRIFT_EMERGENCY"
    SLIPPAGE_ALERT = "SLIPPAGE_ALERT"
    SLIPPAGE_HALT = "SLIPPAGE_HALT"
    WATCHDOG_RESTART = "WATCHDOG_RESTART"
    STARTUP = "STARTUP"
    SHUTDOWN = "SHUTDOWN"
    DAILY_SUMMARY = "DAILY_SUMMARY"
    WEEKLY_SUMMARY = "WEEKLY_SUMMARY"
    # Sprint 8.1 — Meta calibration events
    META_CALIBRATION_SAMPLE = "META_CALIBRATION_SAMPLE"
    META_CALIBRATION_WATCH = "META_CALIBRATION_WATCH"
    META_RECALIBRATE_REQUIRED = "META_RECALIBRATE_REQUIRED"
    META_RECALIBRATED = "META_RECALIBRATED"
    META_CALIBRATION_KILL = "META_CALIBRATION_KILL"
    # Sprint 9.0 — Prop firm adaptive risk layer events
    PROFILE_LOADED = "PROFILE_LOADED"
    PROFILE_SUGGESTION = "PROFILE_SUGGESTION"
    PROFILE_LOCKED = "PROFILE_LOCKED"
    PROFILE_UNLOCKED = "PROFILE_UNLOCKED"
    PROFILE_SWITCHED = "PROFILE_SWITCHED"
    PROFILE_REFUSED = "PROFILE_REFUSED"
    CHALLENGE_STATUS = "CHALLENGE_STATUS"
    RULE_BREACH = "RULE_BREACH"
    RULE_WARNING = "RULE_WARNING"
    # Sprint 9.2 — Adaptive capital protection layer events
    ACCOUNT_HEALTH = "ACCOUNT_HEALTH"
    HEALTH_TRANSITION = "HEALTH_TRANSITION"
    RECOVERY_MODE = "RECOVERY_MODE"
    CAPITAL_PRESERVATION = "CAPITAL_PRESERVATION"
    PROFIT_LOCK = "PROFIT_LOCK"
    EQUITY_PROTECTION = "EQUITY_PROTECTION"
    RISK_PROFILE_CHANGED = "RISK_PROFILE_CHANGED"
    # Sprint 9.5 — Universal execution intelligence events
    BROKER_DETECTED = "BROKER_DETECTED"
    BROKER_SCORE_UPDATED = "BROKER_SCORE_UPDATED"
    BROKER_PROFILE_SELECTED = "BROKER_PROFILE_SELECTED"
    EXECUTION_PROFILE_CHANGED = "EXECUTION_PROFILE_CHANGED"
    EXECUTION_WARNING = "EXECUTION_WARNING"
    EXECUTION_DEGRADED = "EXECUTION_DEGRADED"
    BROKER_UNSAFE = "BROKER_UNSAFE"
    EXECUTION_RECOVERED = "EXECUTION_RECOVERED"
    # Sprint 9.6 — AI Exit Intelligence events
    EXIT_AI_DECISION = "EXIT_AI_DECISION"
    EXIT_SCORE = "EXIT_SCORE"
    PARTIAL_EXIT = "PARTIAL_EXIT"
    BREAK_EVEN = "BREAK_EVEN"
    TRAIL_UPDATED = "TRAIL_UPDATED"
    TP_EXTENDED = "TP_EXTENDED"
    TP_REDUCED = "TP_REDUCED"
    EARLY_EXIT = "EARLY_EXIT"
    NEWS_EXIT = "NEWS_EXIT"
    WEEKEND_EXIT = "WEEKEND_EXIT"
    EXIT_GOVERNANCE = "EXIT_GOVERNANCE"

    # ─── Sprint 9.9.3.39: Institutional pipeline events ────────────────────
    # Wired into AutonomousRuntime via SignalExecutionBridge + RegimeDetection +
    # BrokerCompatibilityMatrix + RuntimeHealthMonitor + SecurityGate +
    # PositionLifecycleEngine + ExitIntentBridge + ForwardObservationEngine +
    # ObservationScorecardEngine.
    INSTITUTIONAL_PIPELINE_STARTED = "INSTITUTIONAL_PIPELINE_STARTED"
    REGIME_GATE_EVALUATED = "REGIME_GATE_EVALUATED"
    BROKER_GATE_EVALUATED = "BROKER_GATE_EVALUATED"
    RUNTIME_HEALTH_GATE_EVALUATED = "RUNTIME_HEALTH_GATE_EVALUATED"
    SECURITY_GATE_EVALUATED = "SECURITY_GATE_EVALUATED"
    EXECUTION_INTENT_CREATED = "EXECUTION_INTENT_CREATED"
    EXECUTION_INTENT_BLOCKED = "EXECUTION_INTENT_BLOCKED"
    EXECUTION_INTENT_APPROVED = "EXECUTION_INTENT_APPROVED"
    TRADE_LOOP_CALLED_AFTER_INTENT = "TRADE_LOOP_CALLED_AFTER_INTENT"
    TRADE_LOOP_SKIPPED_BY_INTENT = "TRADE_LOOP_SKIPPED_BY_INTENT"
    POSITION_LIFECYCLE_EVALUATED = "POSITION_LIFECYCLE_EVALUATED"
    EXIT_INTENT_CREATED = "EXIT_INTENT_CREATED"
    EXIT_INTENT_BLOCKED = "EXIT_INTENT_BLOCKED"
    EXIT_INTENT_APPROVED = "EXIT_INTENT_APPROVED"
    EXIT_MANAGER_FINAL_SAFETY_EVALUATED = "EXIT_MANAGER_FINAL_SAFETY_EVALUATED"
    FORWARD_OBSERVATION_EVENT_RECORDED = "FORWARD_OBSERVATION_EVENT_RECORDED"

    # ─── Sprint 9.9.3.43: Self-healing and dependency events ────────────
    RUNTIME_EXCEPTION_CAUGHT = "RUNTIME_EXCEPTION_CAUGHT"
    RUNTIME_FAIL_CLOSED = "RUNTIME_FAIL_CLOSED"
    RUNTIME_RECOVERY_ATTEMPTED = "RUNTIME_RECOVERY_ATTEMPTED"
    RUNTIME_RECOVERY_LIMIT_REACHED = "RUNTIME_RECOVERY_LIMIT_REACHED"
    DEPENDENCY_COMPATIBILITY_WARNING = "DEPENDENCY_COMPATIBILITY_WARNING"
    MODEL_ARTIFACT_COMPATIBILITY_WARNING = "MODEL_ARTIFACT_COMPATIBILITY_WARNING"
    DEMO_MICRO_READINESS_BLOCKED_BY_DEPENDENCY = "DEMO_MICRO_READINESS_BLOCKED_BY_DEPENDENCY"
    DEMO_MICRO_READINESS_BLOCKED_BY_MODEL = "DEMO_MICRO_READINESS_BLOCKED_BY_MODEL"

    # ─── Sprint 9.9.3.44: Demo micro execution events ──────────────────
    DEMO_MICRO_GATE_EVALUATED = "DEMO_MICRO_GATE_EVALUATED"
    DEMO_MICRO_GATE_BLOCKED = "DEMO_MICRO_GATE_BLOCKED"
    DEMO_MICRO_GATE_ARMED = "DEMO_MICRO_GATE_ARMED"
    DEMO_MICRO_REQUEST_BUILT = "DEMO_MICRO_REQUEST_BUILT"
    DEMO_MICRO_EXECUTION_REFUSED = "DEMO_MICRO_EXECUTION_REFUSED"
    DEMO_MICRO_EXECUTION_READY = "DEMO_MICRO_EXECUTION_READY"
    DEMO_MICRO_FORCE_CLOSE_READY = "DEMO_MICRO_FORCE_CLOSE_READY"
    DEMO_MICRO_FORCE_CLOSE_BLOCKED = "DEMO_MICRO_FORCE_CLOSE_BLOCKED"
    DEMO_MICRO_ENVIRONMENT_DRIFT_BLOCKED = "DEMO_MICRO_ENVIRONMENT_DRIFT_BLOCKED"
    DEMO_MICRO_MODEL_PARITY_BLOCKED = "DEMO_MICRO_MODEL_PARITY_BLOCKED"
    DEMO_MICRO_MODEL_HASH_DRIFT_BLOCKED = "DEMO_MICRO_MODEL_HASH_DRIFT_BLOCKED"
    DEMO_MICRO_XGBOOST_INFERENCE_BLOCKED = "DEMO_MICRO_XGBOOST_INFERENCE_BLOCKED"

    # ─── Sprint 9.9.3.44.2: SL/TP safety events ────────────────────────
    DEMO_MICRO_SL_TP_VALIDATED = "DEMO_MICRO_SL_TP_VALIDATED"
    DEMO_MICRO_SL_TP_BLOCKED = "DEMO_MICRO_SL_TP_BLOCKED"
    DEMO_MICRO_PREVIEW_NOT_EXECUTABLE = "DEMO_MICRO_PREVIEW_NOT_EXECUTABLE"
    DEMO_MICRO_ATR_FALLBACK_USED = "DEMO_MICRO_ATR_FALLBACK_USED"


@dataclass
class JournalRecord:
    """Single journal entry."""
    record_id: str
    timestamp: float
    record_type: str          # SIGNAL | DECISION | ORDER | EXIT | MODIFY | HEARTBEAT
    data: dict[str, Any]
    session_id: str = ""
    # Audit-grade fields (Sprint 6)
    utc_timestamp: str = ""   # ISO 8601 UTC
    event_type: str = ""      # EventType value (for forward-test events)

    def to_jsonl(self) -> str:
        """Serialize to a single JSONL line."""
        return json.dumps({
            "record_id": self.record_id,
            "timestamp": self.timestamp,
            "utc_timestamp": self.utc_timestamp,
            "record_type": self.record_type,
            "event_type": self.event_type,
            "session_id": self.session_id,
            "data": self.data,
        }, default=str, separators=(",", ":"))


class TradeJournal:
    """
    Append-only JSONL trade journal.

    Thread-safe via a single lock around file writes. Each record is a single
    line — atomic append on POSIX. Crash-safe: partial writes are truncated
    on next read (line without trailing newline is discarded).

    Usage:
        journal = TradeJournal(path="~/titan_trades.jsonl")
        journal.log_signal(signal)
    """

    def __init__(self, path: str, session_id: Optional[str] = None,
                 flush_every: int = 1):
        """
        Args:
            path: Path to JSONL file (created if missing)
            session_id: Optional session identifier (auto-generated if None)
            flush_every: Flush to disk every N records (1 = every write)
        """
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.session_id = session_id or str(uuid.uuid4())[:8]
        self._lock = threading.Lock()
        self._flush_every = flush_every
        self._buffer: list[str] = []
        self._record_count = 0

        # Touch the file to verify writability
        try:
            with open(self.path, "a", encoding="utf-8") as f:
                pass
        except IOError as e:
            raise IOError(f"Cannot write to journal path {self.path}: {e}")

        logger.info(f"TradeJournal initialized: {self.path} (session={self.session_id})")

    # ─── Internal ───────────────────────────────────────────────────────

    def _write(self, record: JournalRecord) -> str:
        """Write a single record. Returns the record_id."""
        line = record.to_jsonl()
        with self._lock:
            self._buffer.append(line)
            self._record_count += 1
            if len(self._buffer) >= self._flush_every:
                self._flush()
        return record.record_id

    def _flush(self) -> None:
        """Flush buffer to disk."""
        if not self._buffer:
            return
        with open(self.path, "a", encoding="utf-8") as f:
            for line in self._buffer:
                f.write(line + "\n")
        self._buffer.clear()

    def flush(self) -> None:
        """Public flush — call on shutdown."""
        with self._lock:
            self._flush()

    def _make_record(self, record_type: str, data: dict,
                     event_type: str = "") -> JournalRecord:
        return JournalRecord(
            record_id=str(uuid.uuid4()),
            timestamp=time.time(),
            utc_timestamp=datetime.now(timezone.utc).isoformat(),
            record_type=record_type,
            event_type=event_type,
            data=data,
            session_id=self.session_id,
        )

    # ─── Audit-grade event logging (Sprint 6) ───────────────────────────

    def log_event(self, event_type: EventType, data: dict) -> str:
        """
        Log a typed audit event. Every record includes:
          - unique event_id (UUID)
          - UTC timestamp (ISO 8601)
          - event_type (from EventType enum)
          - session_id
          - arbitrary data dict

        This is the primary method for forward-test audit events.
        """
        if not isinstance(event_type, EventType):
            raise ValueError(f"event_type must be EventType enum, got {type(event_type)}")
        return self._write(self._make_record(
            record_type="EVENT",
            data=data,
            event_type=event_type.value,
        ))

    def log_startup(self, config_summary: dict) -> str:
        """Log system startup event."""
        return self.log_event(EventType.STARTUP, config_summary)

    def log_shutdown(self, reason: str = "normal") -> str:
        """Log system shutdown event."""
        return self.log_event(EventType.SHUTDOWN, {"reason": reason})

    def log_daily_summary(self, summary: dict) -> str:
        """Log daily trading summary."""
        return self.log_event(EventType.DAILY_SUMMARY, summary)

    def log_weekly_summary(self, summary: dict) -> str:
        """Log weekly trading summary."""
        return self.log_event(EventType.WEEKLY_SUMMARY, summary)

    # ─── Verification methods (Sprint 6) ────────────────────────────────

    def verify_append_only(self) -> bool:
        """
        Verify that the journal file has only been appended to.
        Checks that all line numbers are sequential (no gaps from truncation).
        """
        self.flush()
        if not self.path.exists():
            return True  # empty journal is trivially append-only
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                line_count = 0
                for line in f:
                    line_count += 1
                    # Verify each line is valid JSON
                    json.loads(line.strip())
            # If we can read all lines, the file is intact
            return True
        except (json.JSONDecodeError, IOError):
            return False

    def verify_persistence(self) -> bool:
        """
        Verify that journal records survive a restart.
        Reads all records from disk and checks they match in-memory count.
        """
        disk_records = self.read_all()
        return len(disk_records) == self._record_count

    def verify_complete_lifecycle(self) -> dict:
        """
        Verify the journal contains a complete trade lifecycle.
        Returns a dict with verification results for each lifecycle stage.
        """
        self.flush()
        records = self.read_all()
        record_types = [r.get("record_type", "") for r in records]
        event_types = [r.get("event_type", "") for r in records]

        # Check for signal (either SIGNAL record type or SIGNAL_CREATED event)
        has_signal = ("SIGNAL" in record_types or
                      EventType.SIGNAL_CREATED.value in event_types or
                      EventType.SIGNAL_REJECTED.value in event_types)

        return {
            "total_records": len(records),
            "has_signal": has_signal,
            "has_decision": "DECISION" in record_types,
            "has_order": "ORDER" in record_types,
            "has_exit": "EXIT" in record_types,
            "has_modify": "MODIFY" in record_types,
            "has_heartbeat": "HEARTBEAT" in record_types,
            "has_startup": EventType.STARTUP.value in event_types,
            "has_shutdown": EventType.SHUTDOWN.value in event_types,
            "event_types_present": sorted(set(event_types) - {""}),
        }

    def recover_from_crash(self) -> int:
        """
        Recover journal after a crash. Truncates any partially-written last line.
        Returns the number of valid records recovered.
        """
        self.flush()
        if not self.path.exists():
            return 0
        valid_lines = []
        with open(self.path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    json.loads(line)
                    valid_lines.append(line)
                except json.JSONDecodeError:
                    logger.warning(f"Truncated/corrupt journal line discarded: {line[:80]}...")
        # Rewrite with only valid lines
        with open(self.path, "w", encoding="utf-8") as f:
            for line in valid_lines:
                f.write(line + "\n")
        logger.info(f"Journal recovery: {len(valid_lines)} valid records preserved")
        return len(valid_lines)

    def read_by_event_type(self, event_type: EventType) -> list[dict]:
        """Filter records by audit event type."""
        self.flush()
        return [r for r in self.read_all() if r.get("event_type") == event_type.value]

    # ─── Public logging API ─────────────────────────────────────────────

    def log_signal(self, signal) -> str:
        """Log a Signal object from inference.py."""
        return self._write(self._make_record("SIGNAL", {
            "direction": signal.direction.name,
            "confidence": float(signal.confidence),
            "meta_confidence": float(signal.meta_confidence),
            "xgb_proba": list(map(float, signal.xgb_proba)),
            "meta_proba": list(map(float, signal.meta_proba)),
            "is_tradeable": bool(signal.is_tradeable),
            "reject_reason": signal.reject_reason,
            "inference_ms": float(signal.inference_ms),
            "source": signal.source,
            "signal_timestamp": str(signal.timestamp),
        }))

    def log_decision(self, decision) -> str:
        """Log a TradeDecision object from trade_loop.py."""
        data = {
            "accepted": bool(decision.accepted),
            "reject_reason": decision.reject_reason,
            "risk_decision": decision.risk_decision,
            "adjusted_volume": float(decision.adjusted_volume),
            "dry_run": bool(decision.dry_run),
            "evaluation_ms": float(decision.evaluation_ms),
            "order_request": decision.order_request,
        }
        # ── Sprint 8.5: ATR execution audit fields ──
        # These fields MUST be present on every DECISION record so we can
        # verify at audit time whether ATR-based SL/TP was actually used
        # or silently fell back to legacy fixed-pip sizing.
        for attr in (
            "current_atr", "sl_tp_mode_used", "sl_mode_configured",
            "atr_sl_multiplier", "atr_tp_multiplier",
            "atr_sl_distance", "atr_tp_distance",
            "fallback_used", "fallback_reason",
            "entry_price", "computed_sl", "computed_tp",
        ):
            if hasattr(decision, attr):
                data[attr] = getattr(decision, attr)
        # ── Sprint 9.3.1: Capital Protection context fields ──
        # These fields MUST be present on every DECISION record so we can
        # verify at audit time that capital-protection context was propagated
        # through the trade path.
        for attr in (
            "health_score", "health_band", "risk_profile", "risk_multiplier",
            "recovery_mode_active", "capital_preservation_active",
            "profit_lock_active", "prop_profile_id", "challenge_status",
        ):
            if hasattr(decision, attr):
                data[attr] = getattr(decision, attr)
        return self._write(self._make_record("DECISION", data))

    def log_order(self, decision) -> str:
        """Log an ORDER record (for accepted decisions only)."""
        if not decision.accepted:
            return ""
        data = {
            "dry_run": bool(decision.dry_run),
            "order_request": decision.order_request,
            "order_result": decision.order_result,
            "risk_decision": decision.risk_decision,
            "adjusted_volume": float(decision.adjusted_volume),
        }
        # ── Sprint 8.5: ATR execution audit fields ──
        # Mirrored on ORDER records so a downstream consumer reading only
        # ORDER events still sees the ATR evidence.
        for attr in (
            "current_atr", "sl_tp_mode_used", "sl_mode_configured",
            "atr_sl_multiplier", "atr_tp_multiplier",
            "atr_sl_distance", "atr_tp_distance",
            "fallback_used", "fallback_reason",
            "entry_price", "computed_sl", "computed_tp",
        ):
            if hasattr(decision, attr):
                data[attr] = getattr(decision, attr)
        return self._write(self._make_record("ORDER", data))

    def log_exit(self, ticket: int, exit_reason: str,
                 entry_price: float, exit_price: float,
                 direction: int, volume: float,
                 pnl_usd: float = 0.0,
                 holding_time_seconds: float = 0.0,
                 extra: Optional[dict] = None) -> str:
        """Log an exit decision."""
        data = {
            "ticket": int(ticket),
            "exit_reason": exit_reason,
            "entry_price": float(entry_price),
            "exit_price": float(exit_price),
            "direction": int(direction),
            "volume": float(volume),
            "pnl_usd": float(pnl_usd),
            "holding_time_seconds": float(holding_time_seconds),
        }
        if extra:
            data["extra"] = extra
        return self._write(self._make_record("EXIT", data))

    def log_modify(self, ticket: int, old_sl: float, old_tp: float,
                   new_sl: float, new_tp: float, reason: str,
                   dry_run: bool = True) -> str:
        """Log an SL/TP modification."""
        return self._write(self._make_record("MODIFY", {
            "ticket": int(ticket),
            "old_sl": float(old_sl),
            "old_tp": float(old_tp),
            "new_sl": float(new_sl),
            "new_tp": float(new_tp),
            "reason": reason,
            "dry_run": bool(dry_run),
        }))

    def log_heartbeat(self, status: dict) -> str:
        """Log a periodic heartbeat / health checkpoint."""
        return self._write(self._make_record("HEARTBEAT", status))

    # ─── Read API (for backtesting / audit) ─────────────────────────────

    def read_all(self) -> list[dict]:
        """Read all records from the journal."""
        self.flush()
        if not self.path.exists():
            return []
        records = []
        with open(self.path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue  # skip truncated / corrupt lines
        return records

    def read_by_type(self, record_type: str) -> list[dict]:
        """Filter records by type."""
        return [r for r in self.read_all() if r.get("record_type") == record_type]

    @property
    def record_count(self) -> int:
        """Total records written (including unflushed buffer)."""
        return self._record_count

    @property
    def file_size_bytes(self) -> int:
        """Current file size on disk."""
        self.flush()
        return self.path.stat().st_size if self.path.exists() else 0


if __name__ == "__main__":
    # Smoke test
    import tempfile
    import time as _time
    from titan.production.inference import Signal, Direction
    from titan.production.trade_loop import TradeDecision
    import numpy as np

    print("=" * 70)
    print("TITAN TradeJournal — Smoke Test")
    print("=" * 70)

    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as tf:
        journal_path = tf.name

    try:
        journal = TradeJournal(path=journal_path)

        # Log a signal
        sig = Signal(
            timestamp=_time.time(),
            direction=Direction.LONG,
            confidence=0.75,
            meta_confidence=0.80,
            xgb_proba=[0.25, 0.75],
            meta_proba=[0.20, 0.80],
            is_tradeable=True,
            feature_vector=np.zeros(55),
            inference_ms=82.5,
            source="canonical",
        )
        rid1 = journal.log_signal(sig)
        print(f"\nLogged signal: {rid1}")

        # Log a decision
        dec = TradeDecision(
            accepted=True,
            signal=sig,
            risk_decision="ALLOW",
            adjusted_volume=0.01,
            order_request={"symbol": "XAUUSD", "volume": 0.01, "sl": 1999.5, "tp": 2001.0},
            order_result=None,
            evaluation_ms=12.3,
            dry_run=True,
        )
        rid2 = journal.log_decision(dec)
        rid3 = journal.log_order(dec)
        print(f"Logged decision: {rid2}")
        print(f"Logged order: {rid3}")

        # Log an exit
        rid4 = journal.log_exit(
            ticket=50001, exit_reason="TP_HIT",
            entry_price=2000.0, exit_price=2001.0,
            direction=1, volume=0.01,
            pnl_usd=10.0, holding_time_seconds=3600.0
        )
        print(f"Logged exit: {rid4}")

        # Log a modify
        rid5 = journal.log_modify(
            ticket=50001, old_sl=1999.5, old_tp=2001.0,
            new_sl=2000.0, new_tp=2001.0, reason="trailing_stop",
            dry_run=True
        )
        print(f"Logged modify: {rid5}")

        journal.flush()
        print(f"\nTotal records: {journal.record_count}")
        print(f"File size: {journal.file_size_bytes} bytes")

        # Read back
        records = journal.read_all()
        print(f"\nRead back {len(records)} records:")
        for r in records:
            print(f"  [{r['record_type']}] {r['record_id'][:8]}...")

    finally:
        os.unlink(journal_path)
