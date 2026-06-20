"""
TITAN Checkpoint Manager
=========================
Periodically saves full system state to SQLite. On restart, can load
last good checkpoint and resume from there.

Checkpoint contents:
  - CEO status + scores + cycle_count
  - Weighting algorithm + weights + cycle_count
  - Risk mode + equity + drawdowns + utilization
  - Open positions snapshot
  - Open orders snapshot
  - Active idempotency keys (to prevent post-crash duplicates)
  - Model states (XGBoost/LSTM/Transformer weights hash + path)
  - Kill-switch armed flag
  - Active regime

Each checkpoint is one row in `recovery_checkpoints` table with JSON payload.
"""
from __future__ import annotations
import asyncio
import json
import time
import logging
from dataclasses import dataclass, asdict
from typing import Any, Optional
import aiosqlite

logger = logging.getLogger(__name__)

CHECKPOINT_SCHEMA = """
CREATE TABLE IF NOT EXISTS recovery_checkpoints (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL NOT NULL,
    checkpoint_type TEXT NOT NULL,       -- periodic | shutdown | manual
    payload_json TEXT NOT NULL,          -- full state JSON
    checksum TEXT,                       -- SHA-256 of payload
    is_valid INTEGER DEFAULT 1           -- 1 = good, 0 = corrupt
);
CREATE INDEX IF NOT EXISTS idx_cp_ts ON recovery_checkpoints(timestamp);
CREATE INDEX IF NOT EXISTS idx_cp_valid ON recovery_checkpoints(is_valid);
"""


@dataclass
class CheckpointPayload:
    timestamp: float
    ceo: dict | None = None
    weighting: dict | None = None
    risk: dict | None = None
    positions: list[dict] | None = None
    open_orders: list[dict] | None = None
    idempotency_keys: list[str] | None = None
    model_hashes: dict | None = None
    kill_switch_armed: bool = False
    active_regime: str | None = None
    cycle_counts: dict | None = None


class CheckpointManager:
    """Manages periodic system-wide state checkpoints."""

    def __init__(self, db, journal=None):
        self._db = db
        self._journal = journal
        self._initialized = False
        self._lock = asyncio.Lock()
        self._last_checkpoint_id: int | None = None
        self._last_checkpoint_ts: float = 0.0

    async def initialize(self) -> None:
        if self._initialized:
            return
        async with self._lock:
            await self._db.conn.executescript(CHECKPOINT_SCHEMA)
            await self._db.conn.commit()
            self._initialized = True

    async def save_checkpoint(self, payload: CheckpointPayload,
                               checkpoint_type: str = "periodic") -> int:
        """Save a checkpoint. Returns row id."""
        if not self._initialized:
            await self.initialize()
        ts = time.time()
        payload.timestamp = ts
        payload_json = json.dumps(asdict(payload), default=str)
        # Compute checksum
        import hashlib
        checksum = hashlib.sha256(payload_json.encode()).hexdigest()
        async with self._lock:
            cur = await self._db.conn.execute(
                "INSERT INTO recovery_checkpoints "
                "(timestamp, checkpoint_type, payload_json, checksum, is_valid) "
                "VALUES (?, ?, ?, ?, 1)",
                (ts, checkpoint_type, payload_json, checksum),
            )
            await self._db.conn.commit()
            self._last_checkpoint_id = cur.lastrowid
            self._last_checkpoint_ts = ts
        if self._journal:
            await self._journal.log(
                "checkpoint", "system", "save",
                {"checkpoint_id": self._last_checkpoint_id,
                 "type": checkpoint_type,
                 "size_bytes": len(payload_json),
                 "positions_count": len(payload.positions or []),
                 "orders_count": len(payload.open_orders or [])},
            )
        logger.debug(f"Checkpoint saved: id={self._last_checkpoint_id} "
                     f"type={checkpoint_type}")
        return self._last_checkpoint_id

    async def load_latest_checkpoint(self) -> CheckpointPayload | None:
        """Load most recent valid checkpoint."""
        if not self._initialized:
            await self.initialize()
        async with self._lock:
            cur = await self._db.conn.execute(
                "SELECT id, timestamp, payload_json, checksum "
                "FROM recovery_checkpoints WHERE is_valid = 1 "
                "ORDER BY timestamp DESC LIMIT 1"
            )
            row = await cur.fetchone()
        if not row:
            return None
        # Verify checksum
        import hashlib
        computed = hashlib.sha256(row["payload_json"].encode()).hexdigest()
        if computed != row["checksum"]:
            logger.error(f"Checkpoint {row['id']} checksum mismatch — marking invalid")
            async with self._lock:
                await self._db.conn.execute(
                    "UPDATE recovery_checkpoints SET is_valid = 0 WHERE id = ?",
                    (row["id"],),
                )
                await self._db.conn.commit()
            return await self.load_latest_checkpoint()  # try previous

        payload_dict = json.loads(row["payload_json"])
        if self._journal:
            await self._journal.log(
                "checkpoint", "system", "load",
                {"checkpoint_id": row["id"], "age_seconds": time.time() - row["timestamp"]},
            )
        return CheckpointPayload(**payload_dict)

    async def list_checkpoints(self, limit: int = 10) -> list[dict]:
        if not self._initialized:
            await self.initialize()
        async with self._lock:
            cur = await self._db.conn.execute(
                "SELECT id, timestamp, checkpoint_type, is_valid, "
                "length(payload_json) as size_bytes "
                "FROM recovery_checkpoints ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            )
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def cleanup_old(self, keep_count: int = 100) -> int:
        """Keep only the most recent N valid checkpoints."""
        if not self._initialized:
            await self.initialize()
        async with self._lock:
            cur = await self._db.conn.execute(
                "DELETE FROM recovery_checkpoints WHERE id NOT IN ("
                "  SELECT id FROM recovery_checkpoints WHERE is_valid = 1 "
                "  ORDER BY timestamp DESC LIMIT ?"
                ")",
                (keep_count,),
            )
            await self._db.conn.commit()
            return cur.rowcount

    @property
    def last_checkpoint_id(self) -> int | None:
        return self._last_checkpoint_id

    @property
    def last_checkpoint_ts(self) -> float:
        return self._last_checkpoint_ts
