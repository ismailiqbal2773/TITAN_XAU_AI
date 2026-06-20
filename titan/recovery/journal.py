"""
TITAN Recovery Journal + Audit Trail
=====================================
Append-only SQLite log of every recovery-related event.

Tables:
  - recovery_journal: every checkpoint, reconnect, reconcile action
  - recovery_audit:   every state change (status transitions, kill-switch,
                       manual overrides) with old+new values

This is SEPARATE from compliance audit (which logs prop firm rule
violations). Recovery audit logs system-state transitions.
"""
from __future__ import annotations
import asyncio
import json
import time
import logging
from dataclasses import dataclass, asdict
from typing import Optional, Any
import aiosqlite

logger = logging.getLogger(__name__)

JOURNAL_SCHEMA = """
CREATE TABLE IF NOT EXISTS recovery_journal (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL NOT NULL,
    event_type TEXT NOT NULL,         -- checkpoint | reconnect | reconcile | crash_recovery | watchdog
    component TEXT NOT NULL,          -- db | redis | mt5 | api | ceo | weighting | risk | execution
    action TEXT,                      -- save | load | reconnect_success | reconnect_failed | drift_detected | drift_fixed
    details_json TEXT,                -- JSON dict with arbitrary context
    severity TEXT DEFAULT 'INFO'      -- INFO | WARN | ERROR | CRITICAL
);
CREATE INDEX IF NOT EXISTS idx_rj_ts ON recovery_journal(timestamp);
CREATE INDEX IF NOT EXISTS idx_rj_type ON recovery_journal(event_type);
CREATE INDEX IF NOT EXISTS idx_rj_severity ON recovery_journal(severity);

CREATE TABLE IF NOT EXISTS recovery_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL NOT NULL,
    component TEXT NOT NULL,
    field TEXT NOT NULL,              -- what changed (e.g. 'system_status', 'kill_switch_armed')
    old_value TEXT,
    new_value TEXT,
    reason TEXT,
    initiated_by TEXT DEFAULT 'system'  -- system | user | watchdog
);
CREATE INDEX IF NOT EXISTS idx_ra_ts ON recovery_audit(timestamp);
CREATE INDEX IF NOT EXISTS idx_ra_component ON recovery_audit(component);
"""


class RecoveryJournal:
    """Append-only journal of recovery events."""

    def __init__(self, db):
        self._db = db
        self._initialized = False
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        """Create tables if not exist. Idempotent."""
        if self._initialized:
            return
        async with self._lock:
            await self._db.conn.executescript(JOURNAL_SCHEMA)
            await self._db.conn.commit()
            self._initialized = True
            logger.info("Recovery journal initialized")

    async def log(self, event_type: str, component: str, action: str,
                  details: dict | None = None, severity: str = "INFO") -> int:
        """Append a journal entry. Returns row id."""
        if not self._initialized:
            await self.initialize()
        ts = time.time()
        details_json = json.dumps(details or {}, default=str)
        async with self._lock:
            cur = await self._db.conn.execute(
                "INSERT INTO recovery_journal "
                "(timestamp, event_type, component, action, details_json, severity) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (ts, event_type, component, action, details_json, severity),
            )
            await self._db.conn.commit()
            return cur.lastrowid

    async def query(self, event_type: str | None = None,
                    component: str | None = None,
                    since_ts: float | None = None,
                    limit: int = 100) -> list[dict]:
        """Query journal entries."""
        sql = ("SELECT * FROM recovery_journal WHERE 1=1")
        params: list = []
        if event_type:
            sql += " AND event_type = ?"
            params.append(event_type)
        if component:
            sql += " AND component = ?"
            params.append(component)
        if since_ts:
            sql += " AND timestamp >= ?"
            params.append(since_ts)
        sql += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        async with self._lock:
            cur = await self._db.conn.execute(sql, tuple(params))
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def count(self) -> int:
        async with self._lock:
            cur = await self._db.conn.execute("SELECT COUNT(*) FROM recovery_journal")
            row = await cur.fetchone()
            return row[0] if row else 0


class AuditTrail:
    """Audit trail of every state transition (old → new)."""

    def __init__(self, db):
        self._db = db
        self._lock = asyncio.Lock()
        self._initialized = False

    async def initialize(self) -> None:
        """Ensure audit table exists."""
        if self._initialized:
            return
        async with self._lock:
            await self._db.conn.executescript(JOURNAL_SCHEMA)
            await self._db.conn.commit()
            self._initialized = True

    async def log_change(self, component: str, field: str,
                          old_value: Any, new_value: Any,
                          reason: str = "", initiated_by: str = "system") -> int:
        if not self._initialized:
            await self.initialize()
        ts = time.time()
        async with self._lock:
            cur = await self._db.conn.execute(
                "INSERT INTO recovery_audit "
                "(timestamp, component, field, old_value, new_value, reason, initiated_by) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (ts, component, field,
                 str(old_value) if old_value is not None else None,
                 str(new_value) if new_value is not None else None,
                 reason, initiated_by),
            )
            await self._db.conn.commit()
            return cur.lastrowid

    async def query(self, component: str | None = None,
                    field: str | None = None,
                    since_ts: float | None = None,
                    limit: int = 100) -> list[dict]:
        sql = "SELECT * FROM recovery_audit WHERE 1=1"
        params: list = []
        if component:
            sql += " AND component = ?"; params.append(component)
        if field:
            sql += " AND field = ?"; params.append(field)
        if since_ts:
            sql += " AND timestamp >= ?"; params.append(since_ts)
        sql += " ORDER BY timestamp DESC LIMIT ?"; params.append(limit)
        async with self._lock:
            cur = await self._db.conn.execute(sql, tuple(params))
            rows = await cur.fetchall()
        return [dict(r) for r in rows]
