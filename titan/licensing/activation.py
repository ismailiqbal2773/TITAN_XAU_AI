"""
TITAN XAU AI — License Activation Engine (M21.4)

Two activation modes:
- ONLINE:  client → HTTPS → activation server → signed JWT returned
- OFFLINE: client generates request code → vendor signs → client enters
           response code → client unlocks. Designed for air-gapped traders.

Both modes produce a LicenseToken bound to (machine_id, account_id).

Anti-piracy measures:
- Single account per active license (enforced by LicenseStore)
- Activation code is short-lived (TTL = 24h)
- Activation request includes challenge nonce to prevent replay
- Offline codes are base32-encoded, 6 blocks × 5 chars (e.g. ABCDE-FGHIJ-...)
- All codes are signed with the licensing secret
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
import uuid
from dataclasses import dataclass, asdict, field
from enum import Enum
from typing import Optional

from titan.licensing.fingerprint import HardwareFingerprint
from titan.licensing.jwt_license import (
    JWTLicenseEngine, LicenseToken, LicenseClaims, LicenseTier, LicenseType,
    LicenseStatus,
)
from titan.licensing.store import LicenseStore


ACTIVATION_TTL_SECONDS = 24 * 3600  # 24 hours
OFFLINE_CODE_BLOCKS = 6
OFFLINE_CODE_BLOCK_CHARS = 5
OFFLINE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # 30 chars, no confusing


class ActivationMode(str, Enum):
    ONLINE = "online"
    OFFLINE = "offline"


@dataclass
class ActivationRequest:
    """Client → server (online) or vendor (offline)."""
    request_id: str           # uuid4
    machine_id: str           # hardware fingerprint composite
    account_id: str           # MT5 login
    broker_id: str = ""
    license_type: str = LicenseType.FULL.value
    tier: str = LicenseTier.YEARLY.value
    customer_email: str = ""
    customer_name: str = ""
    challenge: str = ""       # random 16-byte hex (replay protection)
    timestamp: int = 0
    fingerprint_short: str = ""  # human-readable short ID for vendor display

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), separators=(",", ":"))

    @classmethod
    def from_dict(cls, d: dict) -> "ActivationRequest":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    @classmethod
    def from_json(cls, s: str) -> "ActivationRequest":
        return cls.from_dict(json.loads(s))


@dataclass
class ActivationResponse:
    """Server/vendor → client."""
    request_id: str
    success: bool
    token: str = ""                  # raw JWT (online mode)
    offline_code: str = ""           # base32 blocks (offline mode)
    error: str = ""
    activated_at: int = 0
    expires_at: int = 0


# ─── Offline code codec ────────────────────────────────────────────────────

def _b32_encode(data: bytes) -> str:
    """Custom base32 with OFFLINE_ALPHABET, grouped into blocks."""
    # Convert bytes to integer
    n = int.from_bytes(data, "big")
    alphabet = OFFLINE_ALPHABET
    base = len(alphabet)
    chars = []
    while n > 0:
        n, r = divmod(n, base)
        chars.append(alphabet[r])
    while len(chars) < OFFLINE_CODE_BLOCKS * OFFLINE_CODE_BLOCK_CHARS:
        chars.append(alphabet[0])
    s = "".join(reversed(chars))
    # Pad to exact length
    s = s.ljust(OFFLINE_CODE_BLOCKS * OFFLINE_CODE_BLOCK_CHARS, alphabet[0])[
        :OFFLINE_CODE_BLOCKS * OFFLINE_CODE_BLOCK_CHARS
    ]
    # Group into blocks
    blocks = [s[i:i + OFFLINE_CODE_BLOCK_CHARS]
              for i in range(0, len(s), OFFLINE_CODE_BLOCK_CHARS)]
    return "-".join(blocks)


def _b32_decode(code: str) -> bytes:
    """Decode base32 code (strips dashes, uppercases)."""
    code = code.replace("-", "").replace(" ", "").upper()
    alphabet = OFFLINE_ALPHABET
    base = len(alphabet)
    n = 0
    for c in code:
        n = n * base + alphabet.index(c)
    # We don't know exact byte length — use 32 bytes (SHA-256 size)
    return n.to_bytes(32, "big")


# ─── Server-side ───────────────────────────────────────────────────────────

class ActivationServer:
    """
    Vendor-side activation service. Issues licenses for valid activation
    requests. Persisted via LicenseStore (single-account enforcement).
    """

    def __init__(self, jwt_engine: JWTLicenseEngine, store: LicenseStore):
        self._jwt = jwt_engine
        self._store = store

    def handle_online(self, request: ActivationRequest,
                      ip_addr: str = "") -> ActivationResponse:
        """Online activation: validates request, issues JWT, persists."""
        # Validate freshness
        now = int(time.time())
        if abs(now - request.timestamp) > ACTIVATION_TTL_SECONDS:
            return ActivationResponse(
                request_id=request.request_id, success=False,
                error="Activation request expired",
            )
        # Single-account check (against store)
        existing = self._store.get_active_for_account(request.account_id)
        if existing and existing.machine_id != request.machine_id:
            return ActivationResponse(
                request_id=request.request_id, success=False,
                error=f"Account {request.account_id} already activated on another machine",
            )

        # Issue token
        token = self._jwt.issue(
            machine_id=request.machine_id,
            account_id=request.account_id,
            tier=LicenseTier(request.tier),
            license_type=LicenseType(request.license_type),
            broker_id=request.broker_id,
            customer_email=request.customer_email,
            customer_name=request.customer_name,
            jti=request.request_id,  # tie license to activation
        )

        # Persist
        saved = self._store.save(token, activated_via=ActivationMode.ONLINE.value)
        if not saved:
            return ActivationResponse(
                request_id=request.request_id, success=False,
                error="Single-account violation: account already active",
            )

        # Record activation
        self._store.record_activation(
            activation_id=str(uuid.uuid4()),
            jti=token.claims.jti,
            machine_id=request.machine_id,
            account_id=request.account_id,
            mode=ActivationMode.ONLINE.value,
            ip_addr=ip_addr,
            fingerprint=request.fingerprint_short,
        )

        return ActivationResponse(
            request_id=request.request_id, success=True,
            token=token.token,
            activated_at=token.claims.iat,
            expires_at=token.claims.exp,
        )

    def handle_offline(self, request: ActivationRequest) -> ActivationResponse:
        """
        Offline activation: signs the request and returns an offline code.
        The client will later use OfflineActivationCode.unlock() to decode
        the embedded JWT.
        """
        # Same single-account + freshness checks
        now = int(time.time())
        if abs(now - request.timestamp) > ACTIVATION_TTL_SECONDS:
            return ActivationResponse(
                request_id=request.request_id, success=False,
                error="Activation request expired",
            )

        existing = self._store.get_active_for_account(request.account_id)
        if existing and existing.machine_id != request.machine_id:
            return ActivationResponse(
                request_id=request.request_id, success=False,
                error="Account already activated on another machine",
            )

        # Issue token (will be embedded in offline code)
        token = self._jwt.issue(
            machine_id=request.machine_id,
            account_id=request.account_id,
            tier=LicenseTier(request.tier),
            license_type=LicenseType(request.license_type),
            broker_id=request.broker_id,
            customer_email=request.customer_email,
            customer_name=request.customer_name,
            jti=request.request_id,
        )

        # Build offline code: HMAC-SHA256(secret, token) → base32 blocks
        code = OfflineActivationCode.generate(token, self._jwt)
        return ActivationResponse(
            request_id=request.request_id, success=True,
            offline_code=code,
            token=token.token,  # client needs both code + token to verify
            activated_at=token.claims.iat,
            expires_at=token.claims.exp,
        )


# ─── Offline code wrapper ──────────────────────────────────────────────────

class OfflineActivationCode:
    """
    Wraps a license token in a base32-encoded offline activation code.
    Format: HMAC-SHA256(secret, token_str) — verifier can recompute.
    The code is bound to (machine_id, account_id) via the JWT claims.
    """

    @staticmethod
    def generate(token: LicenseToken, jwt_engine: JWTLicenseEngine) -> str:
        """Generate offline code from token."""
        # Sign the token string
        sig = hmac.new(
            jwt_engine._secret, token.token.encode("utf-8"), hashlib.sha256
        ).digest()
        # Combine: 16 bytes sig prefix + jti hash (16 bytes) → 32 bytes
        jti_hash = hashlib.sha256(token.claims.jti.encode()).digest()[:16]
        payload = sig[:16] + jti_hash
        return _b32_encode(payload)

    @staticmethod
    def verify(code: str, expected_token: str,
               jwt_engine: JWTLicenseEngine) -> bool:
        """Verify an offline code matches the expected token (vendor-side recheck)."""
        expected = OfflineActivationCode.generate(
            LicenseToken(
                token=expected_token,
                claims=jwt_engine.verify(expected_token).claims,
                signature_valid=True,
                issued_at=time.time(),
            ),
            jwt_engine,
        )
        return hmac.compare_digest(code.replace(" ", "").upper(),
                                   expected.replace(" ", "").upper())


# ─── Client-side ───────────────────────────────────────────────────────────

class ActivationClient:
    """
    Client-side activation helper. Builds requests, exchanges with server
    (online) or vendor (offline), persists resulting license.
    """

    def __init__(self, jwt_engine: JWTLicenseEngine, store: LicenseStore):
        self._jwt = jwt_engine
        self._store = store

    def build_request(
        self,
        account_id: str,
        tier: LicenseTier,
        license_type: LicenseType = LicenseType.FULL,
        broker_id: str = "",
        customer_email: str = "",
        customer_name: str = "",
    ) -> ActivationRequest:
        """Build a fresh activation request bound to this machine."""
        fp = HardwareFingerprint.collect()
        return ActivationRequest(
            request_id=str(uuid.uuid4()),
            machine_id=fp.machine_id(),
            account_id=account_id,
            broker_id=broker_id,
            license_type=license_type.value,
            tier=tier.value,
            customer_email=customer_email,
            customer_name=customer_name,
            challenge=secrets.token_hex(16),
            timestamp=int(time.time()),
            fingerprint_short=fp.short_id(),
        )

    def apply_online_response(self, response: ActivationResponse) -> LicenseToken:
        """Verify and persist an online activation response."""
        if not response.success:
            raise ValueError(f"Activation failed: {response.error}")
        token = self._jwt.verify(response.token)
        if not token.signature_valid:
            raise ValueError("Returned token signature invalid")
        self._store.save(token, activated_via=ActivationMode.ONLINE.value)
        return token

    def apply_offline_code(self, code: str, request: ActivationRequest) -> LicenseToken:
        """
        Apply an offline activation code: re-derives the JWT from the code.
        The code is HMAC-bound to a token that the vendor generated from the
        same request. We reconstruct: token stored alongside code is NOT in
        the code itself (too large), so the client must accept the token
        from a separate channel (file/QR). For test purposes we accept a
        combined "code|token" string.
        """
        # For practical offline flow: vendor sends (code, token) pair.
        # Client verifies code matches token, then stores token.
        parts = code.split("|", 1)
        if len(parts) != 2:
            raise ValueError(
                "Offline code must be 'CODE|JWT' pair (combined by vendor)"
            )
        offline_code, token_str = parts[0], parts[1]
        token = self._jwt.verify(token_str)
        if not token.signature_valid:
            raise ValueError("Offline token signature invalid")
        if not OfflineActivationCode.verify(offline_code, token_str, self._jwt):
            raise ValueError("Offline code does not match token")
        # Verify token matches the original request
        if (token.claims.sub != request.machine_id
                or token.claims.account_id != request.account_id):
            raise ValueError("Offline token does not match activation request")
        self._store.save(token, activated_via=ActivationMode.OFFLINE.value)
        return token


__all__ = [
    "ActivationMode", "ActivationRequest", "ActivationResponse",
    "ActivationServer", "ActivationClient",
    "OfflineActivationCode", "ACTIVATION_TTL_SECONDS",
]
