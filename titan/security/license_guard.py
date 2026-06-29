"""
TITAN XAU AI — LicenseGuard (Sprint 9.9.3.24)
==============================================

Stub/foundation for commercial license validation.

Modes:
  dev_mode          — allow everything (no license required)
  demo_internal_mode — allow with warning (no license required)
  release_mode      — fail closed if license invalid, expired,
                       device/account/broker mismatch, or offline grace exceeded

License keys are NEVER hard-coded in the repository. They are stored
locally in ~/.titan/license.key (not committed).

This is a STUB — no real license server, no real cryptographic validation,
no real device fingerprinting. The structure is in place for future
implementation.

Safety:
  - No secrets, keys, or tokens are committed
  - In dev/demo mode, LicenseGuard is non-blocking
  - In release mode, LicenseGuard returns fail-closed on ANY issue
"""
from __future__ import annotations
import os
import hashlib
import json
import platform
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional


# Operating modes
DEV_MODE = "dev_mode"
DEMO_INTERNAL_MODE = "demo_internal_mode"
RELEASE_MODE = "release_mode"

# License tiers
TIER_TRIAL = "trial"
TIER_PAID_STANDARD = "paid_standard"
TIER_PAID_PRO = "paid_pro"
TIER_INTERNAL = "internal"

# Offline grace period (hours)
OFFLINE_GRACE_HOURS = 72

# License key path (NEVER committed — in user's home dir)
LICENSE_KEY_PATH = Path.home() / ".titan" / "license.key"


def _get_security_mode() -> str:
    """Determine the current security mode from environment."""
    mode = os.environ.get("TITAN_SECURITY_MODE", DEV_MODE)
    if mode not in (DEV_MODE, DEMO_INTERNAL_MODE, RELEASE_MODE):
        return DEV_MODE  # fail safe to dev mode for unknown values
    return mode


def _compute_device_fingerprint() -> str:
    """Compute a device fingerprint hash (stub — basic info only)."""
    info = [
        platform.system(),
        platform.machine(),
        platform.node(),
        str(uuid.getnode()),   # MAC address as int
    ]
    raw = "|".join(info)
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


class LicenseGuard:
    """Commercial license validation guard.

    In dev/demo mode: non-blocking (allows everything).
    In release mode: fail-closed on any license issue.
    """

    def __init__(self, mode: str = None,
                 license_key_path: Optional[str] = None,
                 mt5_login: Optional[int] = None,
                 mt5_server: Optional[str] = None,
                 license_data: Optional[dict] = None):
        """Initialize LicenseGuard.

        Args:
            mode: Security mode (dev_mode/demo_internal_mode/release_mode).
                  If None, reads from TITAN_SECURITY_MODE env var.
            license_key_path: Path to license key file. If None, uses default.
            mt5_login: Current MT5 login for account binding check.
            mt5_server: Current MT5 server for broker binding check.
            license_data: Pre-loaded license data dict (for testing).
        """
        self.mode = mode or _get_security_mode()
        self.license_key_path = Path(license_key_path) if license_key_path else LICENSE_KEY_PATH
        self.mt5_login = mt5_login
        self.mt5_server = mt5_server
        self._license_data = license_data
        self._warnings = []

    def _load_license_data(self) -> Optional[dict]:
        """Load license data from key file or pre-loaded dict."""
        if self._license_data is not None:
            return self._license_data
        if not self.license_key_path.exists():
            return None
        try:
            with open(self.license_key_path, "r") as f:
                return json.load(f)
        except Exception:
            return None

    def check(self) -> dict:
        """Run all license checks and return a status dict.

        Returns:
            dict with keys:
                - allowed (bool): True if execution is allowed
                - mode (str): current security mode
                - license_key_present (bool)
                - license_valid (bool)
                - expired (bool)
                - device_bound (bool)
                - account_bound (bool)
                - broker_bound (bool)
                - offline_grace_valid (bool)
                - release_mode (bool)
                - tier (str|None)
                - expiry_date (str|None)
                - days_remaining (int|None)
                - warnings (list[str]): non-blocking warnings
                - errors (list[str]): blocking errors (release mode)
                - reason (str|None): fail reason if not allowed
        """
        license_data = self._load_license_data()
        license_present = license_data is not None

        # Default status
        status = {
            "allowed": True,
            "mode": self.mode,
            "license_key_present": license_present,
            "license_valid": False,
            "expired": False,
            "device_bound": False,
            "account_bound": False,
            "broker_bound": False,
            "offline_grace_valid": True,
            "release_mode": self.mode == RELEASE_MODE,
            "tier": None,
            "expiry_date": None,
            "days_remaining": None,
            "warnings": [],
            "errors": [],
            "reason": None,
        }

        # ── Dev mode: allow everything ──
        if self.mode == DEV_MODE:
            status["allowed"] = True
            return status

        # ── Demo internal mode: allow with warning ──
        if self.mode == DEMO_INTERNAL_MODE:
            status["allowed"] = True
            if not license_present:
                status["warnings"].append(
                    "Running in demo_internal_mode without a license key — "
                    "this is fine for internal testing but will not work "
                    "in release mode"
                )
            return status

        # ── Release mode: fail closed on any issue ──
        errors = []

        if not license_present:
            errors.append("No license key found — license required in release mode")
            status["license_valid"] = False
        else:
            # Validate license data
            status["license_valid"] = True  # stub — no crypto validation yet
            status["tier"] = license_data.get("tier", TIER_PAID_STANDARD)
            status["expiry_date"] = license_data.get("expiry_date")

            # Check expiry
            expiry_str = license_data.get("expiry_date")
            if expiry_str:
                try:
                    expiry = datetime.fromisoformat(expiry_str)
                    now = datetime.now(timezone.utc)
                    if expiry.tzinfo is None:
                        expiry = expiry.replace(tzinfo=timezone.utc)
                    status["days_remaining"] = (expiry - now).days
                    if now > expiry:
                        # License is expired — check offline grace
                        status["expired"] = True
                        grace_end = expiry + timedelta(hours=OFFLINE_GRACE_HOURS)
                        if now > grace_end:
                            status["offline_grace_valid"] = False
                            errors.append(
                                f"License expired on {expiry_str} and offline "
                                f"grace period ({OFFLINE_GRACE_HOURS}h) exceeded"
                            )
                        else:
                            status["warnings"].append(
                                f"License expired but within offline grace period "
                                f"({OFFLINE_GRACE_HOURS}h)"
                            )
                            status["offline_grace_valid"] = True
                except Exception:
                    errors.append(f"Invalid expiry_date format: {expiry_str}")

            # Check device binding
            licensed_device = license_data.get("device_fingerprint")
            if licensed_device:
                current_device = _compute_device_fingerprint()
                if licensed_device == current_device:
                    status["device_bound"] = True
                else:
                    errors.append("Device fingerprint mismatch — license bound to different device")

            # Check account binding
            licensed_login = license_data.get("mt5_login")
            if licensed_login and self.mt5_login:
                if str(licensed_login) == str(self.mt5_login):
                    status["account_bound"] = True
                else:
                    errors.append(
                        f"MT5 login mismatch — license bound to login {licensed_login} "
                        f"but current login is {self.mt5_login}"
                    )
            elif licensed_login and not self.mt5_login:
                errors.append("License requires MT5 login binding but no login provided")

            # Check broker binding
            licensed_server = license_data.get("mt5_server")
            if licensed_server and self.mt5_server:
                if licensed_server == self.mt5_server:
                    status["broker_bound"] = True
                else:
                    errors.append(
                        f"MT5 server mismatch — license bound to {licensed_server} "
                        f"but current server is {self.mt5_server}"
                    )

        if errors:
            status["allowed"] = False
            status["errors"] = errors
            status["reason"] = "; ".join(errors)
        return status

    def allow(self) -> bool:
        """Convenience: return True if execution is allowed."""
        return self.check()["allowed"]
