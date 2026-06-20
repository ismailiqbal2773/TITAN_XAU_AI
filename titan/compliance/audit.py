"""
TITAN XAU AI — Compliance Audit Log (M22.4)

Append-only audit trail for all compliance-relevant events:
- Daily resets
- Rule evaluations
- Soft/hard breaches
- Position close events
- License feature-gating events

SQLite-backed, schema-compatible with main titan.db.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Optional


SCHEMA = """
CREATE TABLE IF NOT EXISTS compliance_audit (
    event_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp    REAL NOT NULL,
    event_type   TEXT NOT NULL,
    firm_id      TEXT NOT NULL,
    rule_id      TEXT,
    severity     INTEGER,
    action       TEXT,
    message      TEXT,
    details_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_audit_firm    ON compliance_audit(firm_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_type    ON compliance_audit(event_type, timestamp);
CREATE INDEX IF NOT EXISTS idx_audit_severity ON compliance_audit(severity);
"""


@dataclass
class AuditEvent:
    timestamp: float
    event_type: str        # 'evaluation' | 'reset' | 'breach' | 'close_all' | 'halt' | 'license'
    firm_id: str
    rule_id: str = ""
    severity: int = 0
    action: str = ""
    message: str = ""
    details: dict = None

    def __post_init__(self):
        if self.details is None:
            self.details = {}

    def to_dict(self) -> dict:
        return asdict(self)


class ComplianceAuditLog:
    """Append-only audit log for compliance events."""

    def __init__(self, db_path: str = ":memory:"):
        self._db_path = db_path
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def log(self, event: AuditEvent) -> int:
        with self._lock:
            cur = self._conn.execute(
                """INSERT INTO compliance_audit
                   (timestamp, event_type, firm_id, rule_id, severity,
                    action, message, details_json)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (
                    event.timestamp, event.event_type, event.firm_id,
                    event.rule_id, event.severity, event.action,
                    event.message, json.dumps(event.details),
                ),
            )
            self._conn.commit()
            return cur.lastrowid

    def log_evaluation(self, firm_id: str, report_dict: dict) -> None:
        """Convenience: log each rule result from a ComplianceReport.to_dict()."""
        ts = time.time()
        for r in report_dict.get("rule_results", []):
            self.log(AuditEvent(
                timestamp=ts,
                event_type="evaluation",
                firm_id=firm_id,
                rule_id=r["rule_id"],
                severity=r["severity"],
                action=r["action"],
                message=r["message"],
                details={"overall_action": report_dict["overall_action"]},
            ))
        if report_dict.get("breaches"):
            self.log(AuditEvent(
                timestamp=ts,
                event_type="breach",
                firm_id=firm_id,
                severity=80,
                action=report_dict["overall_action"],
                message=" | ".join(report_dict["breaches"]),
                details={"breach_count": len(report_dict["breaches"])},
            ))

    def query(
        self, firm_id: Optional[str] = None,
        event_type: Optional[str] = None,
        min_severity: int = 0,
        since: Optional[float] = None,
        limit: int = 100,
    ) -> list[dict]:
        sql = "SELECT * FROM compliance_audit WHERE 1=1"
        args: list = []
        if firm_id:
            sql += " AND firm_id=?"
            args.append(firm_id)
        if event_type:
            sql += " AND event_type=?"
            args.append(event_type)
        if min_severity > 0:
            sql += " AND severity >= ?"
            args.append(min_severity)
        if since is not None:
            sql += " AND timestamp >= ?"
            args.append(since)
        sql += " ORDER BY timestamp DESC LIMIT ?"
        args.append(limit)
        with self._lock:
            rows = self._conn.execute(sql, args).fetchall()
            return [dict(r) for r in rows]

    def count(self) -> int:
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) AS n FROM compliance_audit"
            ).fetchone()
            return row["n"]


__all__ = ["ComplianceAuditLog", "AuditEvent", "SCHEMA"]
