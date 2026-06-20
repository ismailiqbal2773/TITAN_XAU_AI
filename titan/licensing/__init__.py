"""
TITAN XAU AI — Licensing Module (Module 21)
Hardware-locked JWT licensing with online + offline activation.
"""
from titan.licensing.fingerprint import HardwareFingerprint, FingerprintComponent
from titan.licensing.jwt_license import (
    LicenseToken, LicenseClaims, JWTLicenseEngine,
    LicenseType, LicenseTier, LicenseStatus,
)
from titan.licensing.activation import (
    ActivationServer, ActivationClient, ActivationRequest, ActivationResponse,
    OfflineActivationCode, ActivationMode,
)
from titan.licensing.guard import LicenseGuard, GuardAction, GuardViolation
from titan.licensing.store import LicenseStore

__all__ = [
    "HardwareFingerprint", "FingerprintComponent",
    "LicenseToken", "LicenseClaims", "JWTLicenseEngine",
    "LicenseType", "LicenseTier", "LicenseStatus",
    "ActivationServer", "ActivationClient", "ActivationRequest", "ActivationResponse",
    "OfflineActivationCode", "ActivationMode",
    "LicenseGuard", "GuardAction", "GuardViolation",
    "LicenseStore",
]
