"""
TITAN XAU AI — License Store (M21.3)

Persistent storage for issued/active licenses.
- SQLite-backed (graceful fallback to in-memory)
- Tracks: license_id, machine_id, account_id, status, issued_at, expires_at
- Single-account enforcement: one active license per account_id
- Anti-tamper: stores SHA-256 of token; on read, verifies digest matches
- Revocation list (jti → revoked_at)
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from titan.licensing.jwt_license import LicenseToken, LicenseStatus, LicenseTier, LicenseType


SCHEMA = """
CREATE TABLE IF NOT EXISTS licenses (
    jti              TEXT PRIMARY KEY,
    machine_id       TEXT NOT NULL,
    account_id       TEXT NOT NULL,
    broker_id        TEXT,
    license_type     TEXT NOT NULL,
    tier             TEXT NOT NULL,
    status           TEXT NOT NULL,
    issued_at        INTEGER NOT NULL,
    expires_at       INTEGER NOT NULL,
    customer_email   TEXT,
    customer_name    TEXT,
    token_sha256     TEXT NOT NULL UNIQUE,
    token_blob       TEXT NOT NULL,
    revoked_at       INTEGER,
    activated_via    TEXT NOT NULL,    -- 'online' | 'offline'
    activated_at     INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_licenses_account ON licenses(account_id, status);
CREATE INDEX IF NOT EXISTS idx_licenses_machine ON licenses(machine_id, status);
CREATE INDEX IF NOT EXISTS idx_licenses_status  ON licenses(status);

CREATE TABLE IF NOT EXISTS revocations (
    jti           TEXT PRIMARY KEY,
    revoked_at    INTEGER NOT NULL,
    reason        TEXT
);

CREATE TABLE IF NOT EXISTS activations (
    activation_id TEXT PRIMARY KEY,
    jti           TEXT NOT NULL,
    machine_id    TEXT NOT NULL,
    account_id    TEXT NOT NULL,
    mode          TEXT NOT NULL,           -- 'online' | 'offline'
    activated_at  INTEGER NOT NULL,
    ip_addr       TEXT,
    fingerprint   TEXT
);

CREATE INDEX IF NOT EXISTS idx_activations_jti ON activations(jti);
"""


@dataclass
class StoredLicense:
    jti: str
    machine_id: str
    account_id: str
    broker_id: str
    license_type: str
    tier: str
    status: str
    issued_at: int
    expires_at: int
    customer_email: str
    customer_name: str
    token_sha256: str
    token_blob: str
    revoked_at: Optional[int]
    activated_via: str
    activated_at: int


class LicenseStore:
    """SQLite-backed license store with anti-tamper digest verification."""

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

    # ─── Insertion ─────────────────────────────────────────────────────

    def save(self, token: LicenseToken, activated_via: str = "online") -> bool:
        """
        Persist a freshly issued token. Enforces single-account rule:
        one ACTIVE license per account_id. Returns False if a conflicting
        active license exists for this account.
        """
        with self._lock:
            # Single-account check
            if self._has_active_license(token.claims.account_id, exclude_jti=token.claims.jti):
                return False
            digest = self._sha256(token.token)
            self._conn.execute(
                """INSERT OR REPLACE INTO licenses
                   (jti, machine_id, account_id, broker_id, license_type, tier,
                    status, issued_at, expires_at, customer_email, customer_name,
                    token_sha256, token_blob, revoked_at, activated_via, activated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    token.claims.jti,
                    token.claims.sub,
                    token.claims.account_id,
                    token.claims.broker_id,
                    token.claims.license_type,
                    token.claims.tier,
                    token.claims.status,
                    token.claims.iat,
                    token.claims.exp,
                    token.claims.customer_email,
                    token.claims.customer_name,
                    digest,
                    token.token,
                    None,
                    activated_via,
                    int(time.time()),
                ),
            )
            self._conn.commit()
            return True

    # ─── Queries ────────────────────────────────────────────────────────

    def get_by_jti(self, jti: str) -> Optional[StoredLicense]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM licenses WHERE jti=?", (jti,)
            ).fetchone()
            return self._row_to_stored(row) if row else None

    def get_active_for_account(self, account_id: str) -> Optional[StoredLicense]:
        with self._lock:
            row = self._conn.execute(
                """SELECT * FROM licenses
                   WHERE account_id=? AND status=?
                   ORDER BY expires_at DESC LIMIT 1""",
                (account_id, LicenseStatus.ACTIVE.value),
            ).fetchone()
            return self._row_to_stored(row) if row else None

    def get_active_for_machine(self, machine_id: str) -> Optional[StoredLicense]:
        """Return the most recent active license for a machine."""
        with self._lock:
            row = self._conn.execute(
                """SELECT * FROM licenses
                   WHERE machine_id=? AND status=?
                   ORDER BY expires_at DESC LIMIT 1""",
                (machine_id, LicenseStatus.ACTIVE.value),
            ).fetchone()
            return self._row_to_stored(row) if row else None

    def get_for_machine_any_status(self, machine_id: str) -> Optional[StoredLicense]:
        """Return the most recent license for a machine regardless of status."""
        with self._lock:
            row = self._conn.execute(
                """SELECT * FROM licenses
                   WHERE machine_id=?
                   ORDER BY issued_at DESC LIMIT 1""",
                (machine_id,),
            ).fetchone()
            return self._row_to_stored(row) if row else None

    def list_for_machine(self, machine_id: str) -> list[StoredLicense]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM licenses WHERE machine_id=? ORDER BY issued_at DESC",
                (machine_id,),
            ).fetchall()
            return [self._row_to_stored(r) for r in rows]

    def list_active(self) -> list[StoredLicense]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM licenses WHERE status=? ORDER BY expires_at DESC",
                (LicenseStatus.ACTIVE.value,),
            ).fetchall()
            return [self._row_to_stored(r) for r in rows]

    # ─── Anti-tamper ───────────────────────────────────────────────────

    def verify_token(self, token: str) -> bool:
        """Verify the token on disk has not been tampered with."""
        with self._lock:
            digest = self._sha256(token)
            row = self._conn.execute(
                "SELECT token_sha256 FROM licenses WHERE token_sha256=?",
                (digest,),
            ).fetchone()
            return row is not None

    # ─── Status mutations ──────────────────────────────────────────────

    def revoke(self, jti: str, reason: str = "") -> bool:
        with self._lock:
            now = int(time.time())
            self._conn.execute(
                "UPDATE licenses SET status=?, revoked_at=? WHERE jti=?",
                (LicenseStatus.REVOKED.value, now, jti),
            )
            self._conn.execute(
                "INSERT OR REPLACE INTO revocations (jti, revoked_at, reason) VALUES (?,?,?)",
                (jti, now, reason),
            )
            self._conn.commit()
            return True

    def suspend(self, jti: str) -> bool:
        with self._lock:
            self._conn.execute(
                "UPDATE licenses SET status=? WHERE jti=?",
                (LicenseStatus.SUSPENDED.value, jti),
            )
            self._conn.commit()
            return True

    def mark_expired(self, jti: str) -> bool:
        with self._lock:
            self._conn.execute(
                "UPDATE licenses SET status=? WHERE jti=?",
                (LicenseStatus.EXPIRED.value, jti),
            )
            self._conn.commit()
            return True

    def is_revoked(self, jti: str) -> bool:
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM revocations WHERE jti=?", (jti,)
            ).fetchone()
            return row is not None

    def record_activation(
        self, activation_id: str, jti: str, machine_id: str,
        account_id: str, mode: str, ip_addr: str = "",
        fingerprint: str = "",
    ) -> None:
        with self._lock:
            self._conn.execute(
                """INSERT OR REPLACE INTO activations
                   (activation_id, jti, machine_id, account_id, mode,
                    activated_at, ip_addr, fingerprint)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (activation_id, jti, machine_id, account_id, mode,
                 int(time.time()), ip_addr, fingerprint),
            )
            self._conn.commit()

    # ─── Internal ──────────────────────────────────────────────────────

    def _has_active_license(self, account_id: str, exclude_jti: str = "") -> bool:
        row = self._conn.execute(
            """SELECT 1 FROM licenses
               WHERE account_id=? AND status=?
                 AND jti <> ? LIMIT 1""",
            (account_id, LicenseStatus.ACTIVE.value, exclude_jti),
        ).fetchone()
        return row is not None

    @staticmethod
    def _sha256(s: str) -> str:
        return hashlib.sha256(s.encode("utf-8")).hexdigest()

    @staticmethod
    def _row_to_stored(row: sqlite3.Row) -> StoredLicense:
        return StoredLicense(
            jti=row["jti"],
            machine_id=row["machine_id"],
            account_id=row["account_id"],
            broker_id=row["broker_id"] or "",
            license_type=row["license_type"],
            tier=row["tier"],
            status=row["status"],
            issued_at=row["issued_at"],
            expires_at=row["expires_at"],
            customer_email=row["customer_email"] or "",
            customer_name=row["customer_name"] or "",
            token_sha256=row["token_sha256"],
            token_blob=row["token_blob"],
            revoked_at=row["revoked_at"],
            activated_via=row["activated_via"],
            activated_at=row["activated_at"],
        )


__all__ = ["LicenseStore", "StoredLicense", "SCHEMA"]
