"""
TITAN XAU AI — JWT License Engine (M21.2)

Issues and verifies JWT-encoded licenses with:
- HMAC-SHA256 signing (HS256)
- Hardware binding (machine_id in sub claim)
- Single MT5 account binding (account_id claim)
- Three expiry tiers: MONTHLY (30d), QUARTERLY (90d), YEARLY (365d)
- Anti-rollback (issued_at + not_before + expiration)
- License type (TRIAL, FULL, PRO, ENTERPRISE)
- Status (ACTIVE, SUSPENDED, EXPIRED, REVOKED)

Pure-Python JWT (no PyJWT dependency — vendored minimal implementation).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional


class LicenseType(str, Enum):
    TRIAL = "trial"
    FULL = "full"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class LicenseTier(str, Enum):
    MONTHLY = "monthly"      # 30 days
    QUARTERLY = "quarterly"  # 90 days
    YEARLY = "yearly"        # 365 days


class LicenseStatus(str, Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    EXPIRED = "expired"
    REVOKED = "revoked"


TIER_DURATION_SECONDS = {
    LicenseTier.MONTHLY: 30 * 86400,
    LicenseTier.QUARTERLY: 90 * 86400,
    LicenseTier.YEARLY: 365 * 86400,
}


@dataclass
class LicenseClaims:
    """Claims embedded in the JWT payload."""
    iss: str = "titan-xau-ai/licensing"          # issuer
    sub: str = ""                                  # machine_id (hardware fingerprint)
    aud: str = "titan-xau-ai"                      # audience
    iat: int = 0                                   # issued at (unix)
    nbf: int = 0                                   # not before (unix)
    exp: int = 0                                   # expiration (unix)
    jti: str = ""                                  # unique license id (uuid)
    license_type: str = LicenseType.FULL.value
    tier: str = LicenseTier.YEARLY.value
    status: str = LicenseStatus.ACTIVE.value
    account_id: str = ""                           # MT5 login (single-account lock)
    broker_id: str = ""                            # optional: restrict to broker
    max_balance: float = 0.0                       # 0 = unlimited
    features: list[str] = field(default_factory=list)  # enabled modules
    customer_email: str = ""
    customer_name: str = ""
    grace_seconds: int = 7 * 86400                 # 7-day grace after expiry
    revocable: bool = True

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "LicenseClaims":
        # Tolerate missing fields (backward compat)
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in known})


# Need `fields` import
from dataclasses import fields


@dataclass
class LicenseToken:
    """A signed JWT license token."""
    token: str                  # raw JWT
    claims: LicenseClaims
    signature_valid: bool
    issued_at: float

    @property
    def is_expired(self) -> bool:
        return time.time() > self.claims.exp

    @property
    def in_grace_period(self) -> bool:
        now = time.time()
        return self.claims.exp < now <= self.claims.exp + self.claims.grace_seconds

    @property
    def days_to_expiry(self) -> float:
        return max(0.0, (self.claims.exp - time.time()) / 86400.0)


# ─── Minimal JWT (HS256) ───────────────────────────────────────────────────

def _b64url_encode(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def _b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def _hmac_sha256(secret: bytes, msg: bytes) -> bytes:
    return hmac.new(secret, msg, hashlib.sha256).digest()


class JWTLicenseEngine:
    """
    Issues and verifies JWT licenses signed with HS256.
    """

    HEADER = {"alg": "HS256", "typ": "JWT", "kid": "titan-v1"}

    def __init__(self, secret: str):
        if not secret or len(secret) < 16:
            raise ValueError("JWT secret must be ≥16 chars")
        self._secret = secret.encode("utf-8")

    # ─── Issuance ───────────────────────────────────────────────────────

    def issue(
        self,
        machine_id: str,
        account_id: str,
        tier: LicenseTier,
        license_type: LicenseType = LicenseType.FULL,
        jti: str = "",
        broker_id: str = "",
        max_balance: float = 0.0,
        features: Optional[list[str]] = None,
        customer_email: str = "",
        customer_name: str = "",
        grace_seconds: int = 7 * 86400,
        issued_at: Optional[int] = None,
        duration_override_seconds: Optional[int] = None,
    ) -> LicenseToken:
        """Issue a new license token bound to (machine_id, account_id)."""
        now = int(issued_at if issued_at is not None else time.time())
        duration = duration_override_seconds or TIER_DURATION_SECONDS[tier]
        claims = LicenseClaims(
            sub=machine_id,
            account_id=account_id,
            iat=now,
            nbf=now,
            exp=now + duration,
            jti=jti or _uuid4_str(),
            license_type=license_type.value,
            tier=tier.value,
            status=LicenseStatus.ACTIVE.value,
            broker_id=broker_id,
            max_balance=max_balance,
            features=features or _default_features(license_type),
            customer_email=customer_email,
            customer_name=customer_name,
            grace_seconds=grace_seconds,
        )
        token = self._encode(claims.to_dict())
        return LicenseToken(
            token=token,
            claims=claims,
            signature_valid=True,
            issued_at=float(now),
        )

    # ─── Verification ───────────────────────────────────────────────────

    def verify(self, token: str) -> LicenseToken:
        """Verify signature + parse claims. Does NOT check expiry (use check_status)."""
        try:
            header_b64, payload_b64, sig_b64 = token.split(".")
        except ValueError:
            return LicenseToken(
                token=token, claims=LicenseClaims(),
                signature_valid=False, issued_at=0.0,
            )
        # Verify signature
        signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
        expected_sig = _hmac_sha256(self._secret, signing_input)
        actual_sig = _b64url_decode(sig_b64)
        sig_valid = hmac.compare_digest(expected_sig, actual_sig)
        try:
            payload = json.loads(_b64url_decode(payload_b64))
            claims = LicenseClaims.from_dict(payload)
        except Exception:
            claims = LicenseClaims()
        return LicenseToken(
            token=token, claims=claims,
            signature_valid=sig_valid,
            issued_at=float(claims.iat),
        )

    # ─── Status checks ─────────────────────────────────────────────────

    @staticmethod
    def check_status(token: LicenseToken, now: Optional[float] = None) -> LicenseStatus:
        """Return effective license status (considers expiry + grace)."""
        if not token.signature_valid:
            return LicenseStatus.REVOKED
        now = now or time.time()
        if token.claims.status == LicenseStatus.REVOKED.value:
            return LicenseStatus.REVOKED
        if token.claims.status == LicenseStatus.SUSPENDED.value:
            return LicenseStatus.SUSPENDED
        if now < token.claims.nbf:
            return LicenseStatus.SUSPENDED  # not yet valid
        if now > token.claims.exp + token.claims.grace_seconds:
            return LicenseStatus.EXPIRED
        return LicenseStatus.ACTIVE

    # ─── Internal ──────────────────────────────────────────────────────

    def _encode(self, claims: dict) -> str:
        header_b64 = _b64url_encode(json.dumps(self.HEADER, separators=(",", ":")).encode())
        payload_b64 = _b64url_encode(json.dumps(claims, separators=(",", ":")).encode())
        signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
        sig = _hmac_sha256(self._secret, signing_input)
        sig_b64 = _b64url_encode(sig)
        return f"{header_b64}.{payload_b64}.{sig_b64}"


def _uuid4_str() -> str:
    import uuid
    return str(uuid.uuid4())


def _default_features(lt: LicenseType) -> list[str]:
    """Feature flags per license type."""
    base = ["broker", "market_data", "execution", "risk", "regime", "strategies"]
    if lt == LicenseType.TRIAL:
        return base + ["ai:xgboost"]
    if lt == LicenseType.FULL:
        return base + ["ai:xgboost", "ai:lstm", "backtest"]
    if lt == LicenseType.PRO:
        return base + ["ai:xgboost", "ai:lstm", "ai:transformer",
                       "backtest", "walk_forward", "monte_carlo", "stress_test"]
    # ENTERPRISE
    return ["*"]  # all features


__all__ = [
    "LicenseType", "LicenseTier", "LicenseStatus",
    "LicenseClaims", "LicenseToken",
    "JWTLicenseEngine", "TIER_DURATION_SECONDS",
]
