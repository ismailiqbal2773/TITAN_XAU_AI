"""
TITAN XAU AI — License Guard (M21.5)

Runtime enforcement layer. Sits at the system entrypoint and:
- Verifies license signature on startup
- Verifies hardware fingerprint matches license.sub
- Verifies MT5 account_id matches license.account_id (single-account lock)
- Verifies license is not expired / revoked
- Periodically re-verifies (heartbeat every 60s) to detect tampering
- Triggers GuardAction on violation: WARN / DEGRADE / HALT
- Records all violations for audit

Usage:
    guard = LicenseGuard(jwt_engine, store, fingerprint=HardwareFingerprint.collect())
    guard.startup_check(account_id="12345678")  # raises on violation
    guard.start_heartbeat()  # async background task
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Callable

from titan.licensing.fingerprint import HardwareFingerprint
from titan.licensing.jwt_license import (
    JWTLicenseEngine, LicenseToken, LicenseStatus,
)
from titan.licensing.store import LicenseStore

logger = logging.getLogger(__name__)


class GuardAction(str, Enum):
    WARN = "warn"           # log + metric, continue operating
    DEGRADE = "degrade"     # disable AI features, continue trading
    HALT = "halt"           # full shutdown, close all positions


@dataclass
class GuardViolation:
    timestamp: float
    code: str           # machine-readable violation code
    message: str
    action: GuardAction
    jti: str = ""

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "code": self.code,
            "message": self.message,
            "action": self.action.value,
            "jti": self.jti,
        }


class LicenseGuard:
    """
    Boot-time + runtime license enforcement.
    """

    HEARTBEAT_INTERVAL_SECONDS = 60
    GRACE_PERIOD_BEHAVIOR = GuardAction.DEGRADE  # if in grace, degrade (no AI)

    def __init__(
        self,
        jwt_engine: JWTLicenseEngine,
        store: LicenseStore,
        fingerprint: Optional[HardwareFingerprint] = None,
        on_violation: Optional[Callable[[GuardViolation], None]] = None,
    ):
        self._jwt = jwt_engine
        self._store = store
        self._fp = fingerprint or HardwareFingerprint.collect()
        self._on_violation = on_violation
        self._active_token: Optional[LicenseToken] = None
        self._violations: list[GuardViolation] = []
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._running = False

    # ─── Boot-time ─────────────────────────────────────────────────────

    def startup_check(
        self,
        account_id: str,
        token_str: Optional[str] = None,
    ) -> LicenseToken:
        """
        Run all boot-time license checks. Raises GuardViolation on halt-level
        violations. Returns the active license token.
        """
        # 1. Locate active license — prefer machine lookup (hardware always known)
        if token_str:
            token = self._jwt.verify(token_str)
            if not token.signature_valid:
                self._raise(GuardAction.HALT, "LIC_SIG_INVALID",
                            "License signature verification failed")
        else:
            # Try machine_id first (the hardware fingerprint always identifies us)
            stored = self._store.get_active_for_machine(self._fp.machine_id())
            if not stored:
                # Look for any-status license (may be revoked/expired — we'll catch below)
                stored = self._store.get_for_machine_any_status(self._fp.machine_id())
            if not stored:
                # Fall back to account lookup
                stored = self._store.get_active_for_account(account_id)
            if not stored:
                self._raise(GuardAction.HALT, "LIC_NOT_FOUND",
                            f"No active license for machine {self._fp.short_id()} "
                            f"or account {account_id}")
            token = self._jwt.verify(stored.token_blob)
            if not token.signature_valid:
                self._raise(GuardAction.HALT, "LIC_TAMPERED",
                            "Stored license token has been tampered with")

        # 2. Check revocation
        if self._store.is_revoked(token.claims.jti):
            self._raise(GuardAction.HALT, "LIC_REVOKED",
                        f"License {token.claims.jti} has been revoked")

        # 3. Hardware fingerprint match
        matched, ratio = self._fp.match(
            HardwareFingerprint({})  # build from claims
        )
        # We can't rebuild the original fingerprint from the JWT (only the
        # composite digest is in sub). Compare composite digests instead.
        if token.claims.sub != self._fp.machine_id():
            # Single-component drift tolerance: 5/6 match acceptable.
            # For composite digest, exact match required (the composite is
            # derived from all 6 components). For tolerance, vendor would
            # re-issue with new fingerprint after HW change.
            self._raise(GuardAction.HALT, "LIC_HW_MISMATCH",
                        f"Hardware fingerprint does not match license "
                        f"(expected {token.claims.sub[:16]}, got {self._fp.short_id()})")

        # 4. Single-account lock
        if token.claims.account_id != account_id:
            self._raise(GuardAction.HALT, "LIC_ACCT_MISMATCH",
                        f"License is for account {token.claims.account_id}, "
                        f"not {account_id}")

        # 5. Status / expiry
        status = self._jwt.check_status(token)
        if status == LicenseStatus.REVOKED:
            self._raise(GuardAction.HALT, "LIC_STATUS_REVOKED",
                        "License status is REVOKED")
        if status == LicenseStatus.EXPIRED:
            self._raise(GuardAction.HALT, "LIC_EXPIRED",
                        f"License expired and grace period ended")
        if status == LicenseStatus.SUSPENDED:
            self._raise(GuardAction.DEGRADE, "LIC_SUSPENDED",
                        "License is SUSPENDED — running in degraded mode")
        # ACTIVE or in-grace: continue
        if token.is_expired and not token.in_grace_period:
            self._raise(GuardAction.HALT, "LIC_EXPIRED_HARD",
                        "License has hard-expired")

        # 6. Anti-tamper: recompute store digest
        if not self._store.verify_token(token.token):
            self._raise(GuardAction.HALT, "LIC_DB_TAMPERED",
                        "Token in store does not match computed digest")

        self._active_token = token
        logger.info(
            f"✓ License validated: {token.claims.jti[:8]} "
            f"tier={token.claims.tier} days_left={token.days_to_expiry:.1f}"
        )
        return token

    # ─── Runtime heartbeat ────────────────────────────────────────────

    async def start_heartbeat(self) -> None:
        """Start background heartbeat task. Re-checks license every 60s."""
        if self._heartbeat_task and not self._heartbeat_task.done():
            return
        self._running = True
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def stop_heartbeat(self) -> None:
        self._running = False
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass

    async def _heartbeat_loop(self) -> None:
        while self._running:
            try:
                self._heartbeat_once()
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")
            await asyncio.sleep(self.HEARTBEAT_INTERVAL_SECONDS)

    def _heartbeat_once(self) -> None:
        if not self._active_token:
            return
        # Re-verify signature
        token = self._jwt.verify(self._active_token.token)
        if not token.signature_valid:
            self._raise(GuardAction.HALT, "LIC_HB_SIG",
                        "Heartbeat: signature invalid (possible tampering)")
        # Check revocation
        if self._store.is_revoked(token.claims.jti):
            self._raise(GuardAction.HALT, "LIC_HB_REVOKED",
                        "Heartbeat: license revoked since startup")
        # Check expiry
        status = self._jwt.check_status(token)
        if status == LicenseStatus.EXPIRED:
            self._raise(GuardAction.HALT, "LIC_HB_EXPIRED",
                        "Heartbeat: license hard-expired")
        if status == LicenseStatus.SUSPENDED:
            self._record(GuardAction.DEGRADE, "LIC_HB_SUSPENDED",
                         "Heartbeat: license suspended")

    # ─── Feature gating ───────────────────────────────────────────────

    def has_feature(self, feature: str) -> bool:
        """Check if the active license grants a feature."""
        if not self._active_token:
            return False
        feats = self._active_token.claims.features
        if "*" in feats:
            return True
        return feature in feats

    def require_feature(self, feature: str) -> None:
        """Raise if feature not granted."""
        if not self.has_feature(feature):
            self._raise(GuardAction.DEGRADE, "LIC_FEATURE_DENIED",
                        f"Feature '{feature}' not licensed")

    @property
    def active_token(self) -> Optional[LicenseToken]:
        return self._active_token

    @property
    def violations(self) -> list[GuardViolation]:
        return list(self._violations)

    # ─── Internal ──────────────────────────────────────────────────────

    def _raise(self, action: GuardAction, code: str, msg: str) -> None:
        v = GuardViolation(
            timestamp=time.time(),
            code=code, message=msg, action=action,
            jti=self._active_token.claims.jti if self._active_token else "",
        )
        self._violations.append(v)
        if self._on_violation:
            try:
                self._on_violation(v)
            except Exception:
                pass
        logger.error(f"[LICENSE GUARD] {action.value}: {code} — {msg}")
        raise GuardViolationError(v)

    def _record(self, action: GuardAction, code: str, msg: str) -> None:
        v = GuardViolation(
            timestamp=time.time(),
            code=code, message=msg, action=action,
            jti=self._active_token.claims.jti if self._active_token else "",
        )
        self._violations.append(v)
        if self._on_violation:
            try:
                self._on_violation(v)
            except Exception:
                pass
        logger.warning(f"[LICENSE GUARD] {action.value}: {code} — {msg}")


class GuardViolationError(Exception):
    """Raised when a halt-level license violation occurs."""

    def __init__(self, violation: GuardViolation):
        self.violation = violation
        super().__init__(f"{violation.code}: {violation.message}")


__all__ = [
    "LicenseGuard", "GuardAction", "GuardViolation", "GuardViolationError",
]
