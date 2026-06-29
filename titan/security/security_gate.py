"""
TITAN XAU AI — SecurityGate Coordinator (Sprint 9.9.3.24)
==========================================================

Combines LicenseGuard and AntiTamperGuard into a single security gate.

Modes:
  dev_mode          — allow everything (non-blocking)
  demo_internal_mode — allow with warnings (non-blocking)
  release_mode      — fail closed if license invalid OR tamper detected

Behavior:
  - dev/test/demo internal mode does NOT block existing tests
  - release mode blocks on any license or tamper failure
  - future live trading MUST require a valid security gate

This is a STUB — wired as a non-blocking placeholder in the demo micro
execution path. A TODO marks where future release/live mode will enforce it.
"""
from __future__ import annotations
from typing import Optional

from titan.security.license_guard import (
    LicenseGuard, DEV_MODE, DEMO_INTERNAL_MODE, RELEASE_MODE,
    _get_security_mode,
)
from titan.security.anti_tamper_guard import AntiTamperGuard


class SecurityGateError(Exception):
    """Raised when the security gate blocks execution in release mode."""
    pass


class SecurityGate:
    """Coordinator combining LicenseGuard and AntiTamperGuard.

    Usage:
        gate = SecurityGate(mode="release", mt5_login=12345, mt5_server="...")
        if not gate.allow():
            raise SecurityGateError(gate.check()["reason"])
    """

    def __init__(self, mode: str = None,
                 mt5_login: Optional[int] = None,
                 mt5_server: Optional[str] = None,
                 license_key_path: Optional[str] = None,
                 license_data: Optional[dict] = None,
                 integrity_manifest_path: Optional[str] = None):
        """Initialize SecurityGate.

        Args:
            mode: Security mode. If None, reads from TITAN_SECURITY_MODE env.
            mt5_login: Current MT5 login for license account binding.
            mt5_server: Current MT5 server for license broker binding.
            license_key_path: Path to license key file.
            license_data: Pre-loaded license data (for testing).
            integrity_manifest_path: Path to integrity manifest.
        """
        self.mode = mode or _get_security_mode()
        self.license_guard = LicenseGuard(
            mode=self.mode,
            license_key_path=license_key_path,
            mt5_login=mt5_login,
            mt5_server=mt5_server,
            license_data=license_data,
        )
        self.anti_tamper_guard = AntiTamperGuard(
            mode=self.mode,
            integrity_manifest_path=integrity_manifest_path,
        )
        self._last_check: Optional[dict] = None

    def check(self) -> dict:
        """Run both guards and return a combined status dict.

        Returns:
            dict with keys:
                - allowed (bool): True if BOTH guards allow
                - mode (str): current security mode
                - release_mode (bool)
                - license_status (dict): from LicenseGuard
                - tamper_status (dict): from AntiTamperGuard
                - warnings (list[str]): combined non-blocking warnings
                - errors (list[str]): combined blocking errors
                - reason (str|None): fail reason if not allowed
        """
        license_status = self.license_guard.check()
        tamper_status = self.anti_tamper_guard.check()

        warnings = license_status.get("warnings", []) + tamper_status.get("warnings", [])
        errors = license_status.get("errors", []) + tamper_status.get("errors", [])

        allowed = license_status["allowed"] and tamper_status["allowed"]
        reason = None
        if not allowed:
            reasons = []
            if not license_status["allowed"]:
                reasons.append(f"License: {license_status.get('reason', 'blocked')}")
            if not tamper_status["allowed"]:
                reasons.append(f"Tamper: {tamper_status.get('reason', 'blocked')}")
            reason = "; ".join(reasons)

        result = {
            "allowed": allowed,
            "mode": self.mode,
            "release_mode": self.mode == RELEASE_MODE,
            "license_status": license_status,
            "tamper_status": tamper_status,
            "warnings": warnings,
            "errors": errors,
            "reason": reason,
        }
        self._last_check = result
        return result

    def allow(self) -> bool:
        """Convenience: return True if execution is allowed."""
        return self.check()["allowed"]

    def enforce(self) -> None:
        """Check and raise SecurityGateError if not allowed.

        This is the method future release/live mode will call:
            gate = SecurityGate(mode="release")
            gate.enforce()  # raises if invalid
        """
        status = self.check()
        if not status["allowed"]:
            raise SecurityGateError(status["reason"] or "Security gate blocked")
