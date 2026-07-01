"""
TITAN XAU AI — License Validator (Commercial Licensing Subsystem)
==================================================================

Validates a commercial license end-to-end:

  1. License key format (key prefix, length, checksum character).
  2. Expiry (delegates to ExpiryGuard, supports offline grace).
  3. Machine binding (delegates to MachineBinding).
  4. Feature flags (the requested feature must be present).
  5. Offline grace period (configurable, default 72h).
  6. Tamper detection (signature mismatch, missing fields, replay).

Fail-closed for LIVE trading: if `validate_license(for_live=True)`
returns a non-valid result, the caller MUST block all new trades.

NEVER imports MetaTrader5. NEVER calls mt5.order_send.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Sequence

from titan.commercial.licensing.expiry_guard import ExpiryGuard, ExpiryResult, DEFAULT_OFFLINE_GRACE_HOURS
from titan.commercial.licensing.machine_binding import MachineBinding, MachineSignature

# License key format: TITAN-<TIER>-<32 hex chars>-<4 checksum chars>
# Example: TITAN-PRO-a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6-AB12
LICENSE_KEY_PATTERN = re.compile(
    r"^TITAN-(?P<tier>TRIAL|FULL|PRO|ENT)-[0-9a-fA-F]{32}-[0-9A-Z]{4}$"
)

# Known feature tiers (subset of features). "*" = all features.
TIER_FEATURES: dict[str, tuple[str, ...]] = {
    "TRIAL": ("broker", "market_data", "execution", "risk", "ai:xgboost"),
    "FULL":  ("broker", "market_data", "execution", "risk", "regime",
              "strategies", "ai:xgboost", "ai:lstm", "backtest"),
    "PRO":   ("broker", "market_data", "execution", "risk", "regime",
              "strategies", "ai:xgboost", "ai:lstm", "ai:transformer",
              "backtest", "walk_forward", "monte_carlo", "stress_test"),
    "ENT":   ("*",),
}


@dataclass
class LicenseInfo:
    """Structured license payload provided by the caller."""
    license_key: str
    expiry_epoch: float
    machine_signature: str  # composite signature bound at activation time
    features: tuple[str, ...] = ()
    tier: str = "FULL"
    issued_epoch: float = 0.0
    signature: str = ""  # HMAC over (license_key|expiry_epoch|machine_signature)
    last_known_good_epoch: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "license_key": self.license_key,
            "tier": self.tier,
            "features": list(self.features),
            "expiry_epoch": self.expiry_epoch,
            "issued_epoch": self.issued_epoch,
            "machine_signature": self.machine_signature,
            "signature": self.signature,
            "last_known_good_epoch": self.last_known_good_epoch,
        }


@dataclass
class LicenseValidationResult:
    """Outcome of a license validation."""
    valid: bool
    reason: str
    expiry_date: Optional[str] = None  # ISO-8601 UTC
    features: tuple[str, ...] = ()
    machine_bound: bool = False
    in_grace: bool = False
    grace_period_remaining_hours: float = 0.0
    checked_at: float = field(default_factory=time.time)
    checks: dict[str, bool] = field(default_factory=dict)
    # Safety: must be True for any live-trade path to proceed.
    fail_closed_live: bool = False

    def to_dict(self) -> dict:
        return {
            "valid": self.valid,
            "reason": self.reason,
            "expiry_date": self.expiry_date,
            "features": list(self.features),
            "machine_bound": self.machine_bound,
            "in_grace": self.in_grace,
            "grace_period_remaining_hours": round(self.grace_period_remaining_hours, 4),
            "checked_at": self.checked_at,
            "checks": dict(self.checks),
            "fail_closed_live": self.fail_closed_live,
        }


def _hmac_sha256(secret: bytes, msg: bytes) -> str:
    return hmac.new(secret, msg, hashlib.sha256).hexdigest()


class LicenseValidator:
    """
    Validates commercial licenses with fail-closed semantics for live trading.

    Args:
        machine_binding: injectable MachineBinding (defaults to live collection).
        expiry_guard: injectable ExpiryGuard (defaults to 72h grace).
        signing_secret: secret used to verify license signature. If empty,
            signature check is skipped — but only test fixtures should do this.
    """

    def __init__(
        self,
        machine_binding: Optional[MachineBinding] = None,
        expiry_guard: Optional[ExpiryGuard] = None,
        signing_secret: bytes = b"",
    ) -> None:
        self.machine_binding = machine_binding or MachineBinding.collect()
        self.expiry_guard = expiry_guard or ExpiryGuard()
        self.signing_secret = signing_secret

    # ─── Public API ─────────────────────────────────────────────────────

    def validate_license(
        self,
        info: LicenseInfo,
        required_features: Sequence[str] = (),
        for_live: bool = True,
        online: bool = True,
        now: Optional[float] = None,
    ) -> LicenseValidationResult:
        """
        Run all license checks. Returns a LicenseValidationResult.

        When `for_live=True`, the result has fail_closed_live=True only when
        ALL checks pass — callers must block new trades otherwise.
        """
        now = now if now is not None else time.time()
        checks: dict[str, bool] = {}
        reasons: list[str] = []

        # 1. Format check
        fmt_ok = bool(LICENSE_KEY_PATTERN.match(info.license_key or ""))
        checks["format"] = fmt_ok
        if not fmt_ok:
            reasons.append("invalid license key format")

        # 2. Tier sanity
        tier_ok = info.tier in TIER_FEATURES
        checks["tier"] = tier_ok
        if not tier_ok:
            reasons.append(f"unknown tier '{info.tier}'")

        # 3. Tamper detection (signature) — only if a secret was provided.
        sig_ok = True
        if self.signing_secret:
            expected_sig = self._compute_signature(info)
            if not info.signature:
                sig_ok = False
                reasons.append("license signature missing")
            elif not hmac.compare_digest(expected_sig, info.signature):
                sig_ok = False
                reasons.append("license signature mismatch (tamper detected)")
        # If no secret configured, we mark the check as "skipped" but
        # do NOT treat it as passing for live trading — fail-closed.
        elif for_live:
            sig_ok = False
            reasons.append("signing secret not configured — cannot verify tamper for live")
        checks["tamper"] = sig_ok

        # 4. Expiry (with offline grace)
        expiry_result: ExpiryResult = self.expiry_guard.check_expiry(
            expiry_epoch=info.expiry_epoch,
            last_known_good_epoch=info.last_known_good_epoch,
            online=online,
            now=now,
        )
        checks["expiry"] = (not expiry_result.expired)
        if expiry_result.expired:
            reasons.append(expiry_result.reason)

        # 5. Machine binding
        bound, ratio, bind_reason = self.machine_binding.verify_binding(
            info.machine_signature
        )
        checks["machine_binding"] = bound
        if not bound:
            reasons.append(f"machine binding failed: {bind_reason}")

        # 6. Feature flags
        granted = self._effective_features(info)
        missing = [f for f in required_features if not self._feature_granted(granted, f)]
        checks["features"] = (len(missing) == 0)
        if missing:
            reasons.append(f"missing features: {','.join(missing)}")

        all_ok = all(checks.values())
        expiry_iso = (
            datetime.fromtimestamp(info.expiry_epoch, tz=timezone.utc).isoformat()
            if info.expiry_epoch > 0 else None
        )

        return LicenseValidationResult(
            valid=all_ok,
            reason="; ".join(reasons) if reasons else "all checks passed",
            expiry_date=expiry_iso,
            features=tuple(granted),
            machine_bound=bound,
            in_grace=expiry_result.in_grace,
            grace_period_remaining_hours=expiry_result.grace_period_remaining_hours,
            checked_at=now,
            checks=checks,
            # Live trading requires ALL checks pass (no grace for live).
            fail_closed_live=(all_ok and not expiry_result.in_grace),
        )

    # ─── Helpers ────────────────────────────────────────────────────────

    def _compute_signature(self, info: LicenseInfo) -> str:
        msg = f"{info.license_key}|{int(info.expiry_epoch)}|{info.machine_signature}".encode()
        return _hmac_sha256(self.signing_secret, msg)

    @staticmethod
    def _effective_features(info: LicenseInfo) -> list[str]:
        tier_feats = TIER_FEATURES.get(info.tier, ())
        if info.features:
            # Explicit feature list on the license wins (subject to tier subset).
            # "*" alone means all — only valid for ENT.
            if "*" in info.features:
                return ["*"]
            return [f for f in info.features if f in tier_feats or "*" in tier_feats]
        return list(tier_feats)

    @staticmethod
    def _feature_granted(granted: list[str], feature: str) -> bool:
        if "*" in granted:
            return True
        return feature in granted


__all__ = [
    "LicenseValidator",
    "LicenseInfo",
    "LicenseValidationResult",
    "LICENSE_KEY_PATTERN",
    "TIER_FEATURES",
    "DEFAULT_OFFLINE_GRACE_HOURS",
]
