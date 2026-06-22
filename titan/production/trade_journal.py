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
from pathlib import Path
from typing import Optional, Any

logger = logging.getLogger(__name__)


@dataclass
class JournalRecord:
    """Single journal entry."""
    record_id: str
    timestamp: float
    record_type: str          # SIGNAL | DECISION | ORDER | EXIT | MODIFY | HEARTBEAT
    data: dict[str, Any]
    session_id: str = ""

    def to_jsonl(self) -> str:
        """Serialize to a single JSONL line."""
        return json.dumps({
            "record_id": self.record_id,
            "timestamp": self.timestamp,
            "record_type": self.record_type,
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

    def _make_record(self, record_type: str, data: dict) -> JournalRecord:
        return JournalRecord(
            record_id=str(uuid.uuid4()),
            timestamp=time.time(),
            record_type=record_type,
            data=data,
            session_id=self.session_id,
        )

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
        return self._write(self._make_record("DECISION", {
            "accepted": bool(decision.accepted),
            "reject_reason": decision.reject_reason,
            "risk_decision": decision.risk_decision,
            "adjusted_volume": float(decision.adjusted_volume),
            "dry_run": bool(decision.dry_run),
            "evaluation_ms": float(decision.evaluation_ms),
            "order_request": decision.order_request,
        }))

    def log_order(self, decision) -> str:
        """Log an ORDER record (for accepted decisions only)."""
        if not decision.accepted:
            return ""
        return self._write(self._make_record("ORDER", {
            "dry_run": bool(decision.dry_run),
            "order_request": decision.order_request,
            "order_result": decision.order_result,
            "risk_decision": decision.risk_decision,
            "adjusted_volume": float(decision.adjusted_volume),
        }))

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
