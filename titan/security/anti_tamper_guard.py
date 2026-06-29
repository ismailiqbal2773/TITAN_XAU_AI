"""
TITAN XAU AI — AntiTamperGuard (Sprint 9.9.3.24)
=================================================

Stub/foundation for anti-tamper integrity checking.

Modes:
  dev_mode          — allow everything (no integrity checks)
  demo_internal_mode — warn only (log but don't block)
  release_mode      — fail closed on any tamper detected

Checks (placeholder — real hash computation is future work):
  - Integrity manifest (SHA-256 of all source files)
  - Config file hash
  - Model artifact hash
  - Executable signature

This is a STUB — no real hashes are computed yet. The structure is in
place for future implementation.
"""
from __future__ import annotations
import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from titan.security.license_guard import (
    DEV_MODE, DEMO_INTERNAL_MODE, RELEASE_MODE, _get_security_mode,
)


class TamperEvent:
    """Represents a single tamper detection event."""

    def __init__(self, file_path: str, expected_hash: str,
                 actual_hash: str, check_type: str = "source"):
        self.file_path = file_path
        self.expected_hash = expected_hash
        self.actual_hash = actual_hash
        self.check_type = check_type  # source / config / model / executable
        self.timestamp_utc = datetime.now(timezone.utc).isoformat()
        self.severity = "CRITICAL"

    def to_dict(self) -> dict:
        return {
            "file_path": self.file_path,
            "expected_hash": self.expected_hash,
            "actual_hash": self.actual_hash,
            "check_type": self.check_type,
            "timestamp_utc": self.timestamp_utc,
            "severity": self.severity,
        }

    def __repr__(self):
        return (f"TamperEvent(file={self.file_path}, "
                f"check={self.check_type}, severity={self.severity})")


class AntiTamperGuard:
    """Anti-tamper integrity checking guard.

    In dev mode: non-blocking (no checks).
    In demo mode: warn only (log tamper but don't block).
    In release mode: fail-closed on any tamper detected.
    """

    def __init__(self, mode: str = None,
                 integrity_manifest_path: Optional[str] = None,
                 config_path: Optional[str] = None,
                 model_dir: Optional[str] = None):
        """Initialize AntiTamperGuard.

        Args:
            mode: Security mode. If None, reads from TITAN_SECURITY_MODE env.
            integrity_manifest_path: Path to integrity manifest JSON.
            config_path: Path to config file to check.
            model_dir: Directory containing model artifacts to check.
        """
        self.mode = mode or _get_security_mode()
        self.integrity_manifest_path = (
            Path(integrity_manifest_path) if integrity_manifest_path
            else Path("titan.integrity")
        )
        self.config_path = (
            Path(config_path) if config_path
            else Path("config/runtime.yaml")
        )
        self.model_dir = (
            Path(model_dir) if model_dir
            else Path("titan/data/models")
        )
        self._tamper_events: list[TamperEvent] = []
        self._warnings = []

    def _load_integrity_manifest(self) -> Optional[dict]:
        """Load the integrity manifest (placeholder — returns None)."""
        if not self.integrity_manifest_path.exists():
            return None
        import json
        try:
            with open(self.integrity_manifest_path, "r") as f:
                return json.load(f)
        except Exception:
            return None

    def _compute_file_hash(self, path: Path) -> Optional[str]:
        """Compute SHA-256 hash of a file."""
        if not path.exists():
            return None
        try:
            h = hashlib.sha256()
            with open(path, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    h.update(chunk)
            return h.hexdigest()
        except Exception:
            return None

    def check(self) -> dict:
        """Run all tamper checks and return a status dict.

        Returns:
            dict with keys:
                - allowed (bool): True if execution is allowed
                - mode (str): current security mode
                - tamper_detected (bool): True if any tamper was found
                - tamper_events (list[dict]): list of tamper events
                - integrity_manifest_present (bool)
                - config_hash_valid (bool|None): placeholder
                - model_hash_valid (bool|None): placeholder
                - executable_signature_valid (bool|None): placeholder
                - warnings (list[str]): non-blocking warnings
                - errors (list[str]): blocking errors (release mode)
                - reason (str|None): fail reason if not allowed
        """
        manifest = self._load_integrity_manifest()
        manifest_present = manifest is not None

        # Placeholder checks — in future, these will compute and compare hashes
        config_hash_valid = None  # placeholder
        model_hash_valid = None   # placeholder
        executable_signature_valid = None  # placeholder

        # For now, tamper is detected if any tamper events have been reported
        # via report_tamper() or if the manifest says a file should have
        # hash X but the actual hash differs.
        tamper_detected = len(self._tamper_events) > 0

        status = {
            "allowed": True,
            "mode": self.mode,
            "tamper_detected": tamper_detected,
            "tamper_events": [e.to_dict() for e in self._tamper_events],
            "integrity_manifest_present": manifest_present,
            "config_hash_valid": config_hash_valid,
            "model_hash_valid": model_hash_valid,
            "executable_signature_valid": executable_signature_valid,
            "warnings": [],
            "errors": [],
            "reason": None,
        }

        # ── Dev mode: allow everything ──
        if self.mode == DEV_MODE:
            return status

        # ── Demo internal mode: warn only ──
        if self.mode == DEMO_INTERNAL_MODE:
            if not manifest_present:
                status["warnings"].append(
                    "No integrity manifest found — tamper detection disabled "
                    "(demo_internal_mode, non-blocking)"
                )
            if tamper_detected:
                status["warnings"].append(
                    f"Tamper detected in {len(self._tamper_events)} file(s) — "
                    f"non-blocking in demo_internal_mode"
                )
            return status

        # ── Release mode: fail closed on tamper ──
        errors = []

        if not manifest_present:
            errors.append(
                "No integrity manifest found — required in release mode"
            )

        if tamper_detected:
            for event in self._tamper_events:
                errors.append(
                    f"Tamper detected: {event.file_path} "
                    f"(expected {event.expected_hash[:16]}..., "
                    f"got {event.actual_hash[:16]}...)"
                )

        if errors:
            status["allowed"] = False
            status["errors"] = errors
            status["reason"] = "; ".join(errors)

        return status

    def allow(self) -> bool:
        """Convenience: return True if execution is allowed."""
        return self.check()["allowed"]

    def report_tamper(self, file_path: str, expected_hash: str,
                      actual_hash: str, check_type: str = "source") -> None:
        """Manually report a tamper event (for testing or future checks)."""
        event = TamperEvent(file_path, expected_hash, actual_hash, check_type)
        self._tamper_events.append(event)
