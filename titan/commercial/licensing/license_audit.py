"""
TITAN XAU AI — License Audit (Commercial Licensing Subsystem)
==============================================================

Runs a full license audit combining format / expiry / machine binding /
feature / tamper checks and returns a high-level verdict:

  - LICENSE_VALID        : all checks passed, license is fully usable.
  - LICENSE_GRACE_PERIOD : license expired but offline grace is still active.
                           Live trading is BLOCKED; read-only operations OK.
  - LICENSE_EXPIRED      : license has expired (and grace, if any, is exhausted).
  - LICENSE_INVALID      : structural failure (bad format, tamper, machine
                           mismatch, missing features, missing signing secret
                           for live trading).

NEVER imports MetaTrader5. NEVER calls mt5.order_send.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional, Sequence

from titan.commercial.licensing.expiry_guard import ExpiryGuard, DEFAULT_OFFLINE_GRACE_HOURS
from titan.commercial.licensing.license_validator import (
    LicenseInfo,
    LicenseValidationResult,
    LicenseValidator,
)
from titan.commercial.licensing.machine_binding import MachineBinding

# Audit verdicts
LICENSE_VALID = "LICENSE_VALID"
LICENSE_EXPIRED = "LICENSE_EXPIRED"
LICENSE_INVALID = "LICENSE_INVALID"
LICENSE_GRACE_PERIOD = "LICENSE_GRACE_PERIOD"

_ALL_VERDICTS = (
    LICENSE_VALID,
    LICENSE_EXPIRED,
    LICENSE_INVALID,
    LICENSE_GRACE_PERIOD,
)


@dataclass
class LicenseAuditResult:
    """Outcome of a full license audit."""
    verdict: str
    valid: bool
    reason: str
    expiry_date: Optional[str] = None
    features: tuple[str, ...] = ()
    machine_bound: bool = False
    in_grace: bool = False
    grace_period_remaining_hours: float = 0.0
    checked_at: float = field(default_factory=time.time)
    checks: dict[str, bool] = field(default_factory=dict)
    fail_closed_live: bool = False
    live_trading_permitted: bool = False

    def to_dict(self) -> dict:
        return {
            "verdict": self.verdict,
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
            "live_trading_permitted": self.live_trading_permitted,
        }


class LicenseAudit:
    """
    Runs a complete license audit and returns a high-level verdict.

    Args:
        machine_binding: injectable (defaults to live collection).
        expiry_guard: injectable (defaults to 72h grace).
        signing_secret: HMAC secret for tamper verification.
    """

    def __init__(
        self,
        machine_binding: Optional[MachineBinding] = None,
        expiry_guard: Optional[ExpiryGuard] = None,
        signing_secret: bytes = b"",
    ) -> None:
        self.validator = LicenseValidator(
            machine_binding=machine_binding,
            expiry_guard=expiry_guard,
            signing_secret=signing_secret,
        )

    def audit(
        self,
        info: LicenseInfo,
        required_features: Sequence[str] = (),
        for_live: bool = True,
        online: bool = True,
        now: Optional[float] = None,
    ) -> LicenseAuditResult:
        """Run a full audit and return a high-level verdict."""
        result: LicenseValidationResult = self.validator.validate_license(
            info=info,
            required_features=required_features,
            for_live=for_live,
            online=online,
            now=now,
        )

        verdict = self._derive_verdict(result)
        return LicenseAuditResult(
            verdict=verdict,
            valid=result.valid,
            reason=result.reason,
            expiry_date=result.expiry_date,
            features=result.features,
            machine_bound=result.machine_bound,
            in_grace=result.in_grace,
            grace_period_remaining_hours=result.grace_period_remaining_hours,
            checked_at=result.checked_at,
            checks=result.checks,
            fail_closed_live=result.fail_closed_live,
            # Live trading requires (valid AND not in grace AND all structural checks pass).
            live_trading_permitted=(
                verdict == LICENSE_VALID
                and not result.in_grace
                and result.fail_closed_live
            ),
        )

    # ─── Verdict logic ─────────────────────────────────────────────────

    @staticmethod
    def _derive_verdict(result: LicenseValidationResult) -> str:
        # If the structural checks pass but the license is in grace period,
        # we report GRACE_PERIOD (live trading blocked, read-only OK).
        if result.valid and result.in_grace:
            return LICENSE_GRACE_PERIOD

        # Fully valid
        if result.valid:
            return LICENSE_VALID

        # Invalid → distinguish "expired" vs "structurally invalid".
        checks = result.checks
        expiry_failed = checks.get("expiry", True) is False
        other_failed = any(
            not v for k, v in checks.items() if k != "expiry"
        )

        # If only expiry failed (everything else OK) → EXPIRED.
        if expiry_failed and not other_failed:
            return LICENSE_EXPIRED

        # Otherwise → INVALID (tamper, format, binding, features).
        return LICENSE_INVALID


__all__ = [
    "LicenseAudit",
    "LicenseAuditResult",
    "LICENSE_VALID",
    "LICENSE_EXPIRED",
    "LICENSE_INVALID",
    "LICENSE_GRACE_PERIOD",
]
