"""
TITAN XAU AI — Expiry Guard (Commercial Licensing Subsystem)
==============================================================

Checks license expiry with an offline grace period (default 72 hours).

Design:
  - Pure-Python, no MetaTrader5, no order_send.
  - Supports both wall-clock expiry and offline grace.
  - Offline grace is bounded: a license cannot be in grace forever.
    The "last known good" timestamp must be persisted by the caller; this
    guard accepts it as input so it remains pure / stateless.
  - Fail-closed: if no last-known-good timestamp is provided AND the system
    is offline, expiry is treated as hard-expired (no grace).

NEVER imports MetaTrader5. NEVER calls mt5.order_send.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

DEFAULT_OFFLINE_GRACE_HOURS: float = 72.0


@dataclass
class ExpiryResult:
    """Outcome of an expiry check."""
    expired: bool
    grace_period_remaining_hours: float
    reason: str
    in_grace: bool = False
    checked_at: float = field(default_factory=time.time)
    expiry_date: Optional[str] = None  # ISO-8601 UTC

    def to_dict(self) -> dict:
        return {
            "expired": self.expired,
            "in_grace": self.in_grace,
            "grace_period_remaining_hours": round(self.grace_period_remaining_hours, 4),
            "reason": self.reason,
            "checked_at": self.checked_at,
            "expiry_date": self.expiry_date,
        }


class ExpiryGuard:
    """
    Verifies license expiry with offline grace support.

    Args:
        offline_grace_hours: maximum grace period when offline (default 72h).
        clock: injectable clock for tests (defaults to time.time).
    """

    def __init__(
        self,
        offline_grace_hours: float = DEFAULT_OFFLINE_GRACE_HOURS,
        clock: Optional[callable] = None,  # type: ignore[assignment]
    ) -> None:
        if offline_grace_hours < 0:
            raise ValueError("offline_grace_hours must be >= 0")
        self.offline_grace_hours = offline_grace_hours
        self._clock = clock or time.time

    def check_expiry(
        self,
        expiry_epoch: float,
        last_known_good_epoch: Optional[float] = None,
        online: bool = True,
        now: Optional[float] = None,
    ) -> ExpiryResult:
        """
        Check whether a license has expired.

        Args:
            expiry_epoch: license expiry as unix seconds.
            last_known_good_epoch: last successful online validation (unix seconds).
                Required to claim offline grace when offline.
            online: whether the system can reach the licensing server right now.
            now: override "now" for tests.

        Rules:
          - If online and now > expiry: HARD expired (no grace).
          - If online and now <= expiry: not expired.
          - If offline and now > expiry:
              * If we have a last_known_good, allow grace until
                last_known_good + offline_grace_hours.
              * If no last_known_good: HARD expired (fail-closed).
          - If offline and now <= expiry: not expired (license itself still valid).
        """
        now = now if now is not None else self._clock()
        if expiry_epoch <= 0:
            return ExpiryResult(
                expired=True,
                grace_period_remaining_hours=0.0,
                reason="expiry_epoch not set — fail-closed",
                in_grace=False,
                checked_at=now,
                expiry_date=None,
            )

        expiry_iso = datetime.fromtimestamp(expiry_epoch, tz=timezone.utc).isoformat()

        # ── Online path ─────────────────────────────────────────────
        if online:
            if now > expiry_epoch:
                return ExpiryResult(
                    expired=True,
                    grace_period_remaining_hours=0.0,
                    reason="license expired (online check)",
                    in_grace=False,
                    checked_at=now,
                    expiry_date=expiry_iso,
                )
            return ExpiryResult(
                expired=False,
                grace_period_remaining_hours=0.0,
                reason="license valid (online check)",
                in_grace=False,
                checked_at=now,
                expiry_date=expiry_iso,
            )

        # ── Offline path ────────────────────────────────────────────
        # License itself not yet expired: still valid offline.
        if now <= expiry_epoch:
            return ExpiryResult(
                expired=False,
                grace_period_remaining_hours=0.0,
                reason="license valid (offline, within expiry)",
                in_grace=False,
                checked_at=now,
                expiry_date=expiry_iso,
            )

        # License expired AND offline — apply grace.
        if last_known_good_epoch is None or last_known_good_epoch <= 0:
            return ExpiryResult(
                expired=True,
                grace_period_remaining_hours=0.0,
                reason="offline + expired + no last_known_good — fail-closed",
                in_grace=False,
                checked_at=now,
                expiry_date=expiry_iso,
            )

        grace_deadline = last_known_good_epoch + self.offline_grace_hours * 3600.0
        if now <= grace_deadline:
            remaining_h = (grace_deadline - now) / 3600.0
            return ExpiryResult(
                expired=False,
                grace_period_remaining_hours=max(0.0, remaining_h),
                reason="offline grace period active",
                in_grace=True,
                checked_at=now,
                expiry_date=expiry_iso,
            )

        # Grace exhausted
        return ExpiryResult(
            expired=True,
            grace_period_remaining_hours=0.0,
            reason="offline grace period exhausted",
            in_grace=False,
            checked_at=now,
            expiry_date=expiry_iso,
        )


__all__ = ["ExpiryGuard", "ExpiryResult", "DEFAULT_OFFLINE_GRACE_HOURS"]
