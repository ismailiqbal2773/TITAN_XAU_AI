"""
TITAN XAU AI — Sprint 9.9.3.24 Commercial Protection Tests
============================================================

Tests for LicenseGuard, AntiTamperGuard, and SecurityGate.

Covers:
  - LicenseGuard dev_mode allows
  - demo_internal_mode allows with warning
  - release_mode blocks missing license
  - release_mode blocks expired license
  - release_mode blocks account mismatch
  - release_mode blocks broker mismatch
  - AntiTamperGuard dev_mode allows
  - AntiTamperGuard release_mode blocks tamper
  - SecurityGate allows dev_mode
  - SecurityGate blocks release invalid license
  - no secret/license key hard-coded in repo
"""
from __future__ import annotations
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from titan.security.license_guard import (
    LicenseGuard, DEV_MODE, DEMO_INTERNAL_MODE, RELEASE_MODE,
    TIER_TRIAL, TIER_PAID_STANDARD, TIER_PAID_PRO, TIER_INTERNAL,
    OFFLINE_GRACE_HOURS, LICENSE_KEY_PATH,
)
from titan.security.anti_tamper_guard import (
    AntiTamperGuard, TamperEvent,
)
from titan.security.security_gate import (
    SecurityGate, SecurityGateError,
)


class TestLicenseGuard:
    """LicenseGuard mode-based behavior tests."""

    def test_01_dev_mode_allows(self):
        """Dev mode allows everything — no license required."""
        guard = LicenseGuard(mode=DEV_MODE)
        status = guard.check()
        assert status["allowed"] is True
        assert status["mode"] == DEV_MODE
        assert status["release_mode"] is False

    def test_02_demo_internal_mode_allows_with_warning(self, tmp_path):
        """Demo internal mode allows but warns when no license present."""
        guard = LicenseGuard(
            mode=DEMO_INTERNAL_MODE,
            license_key_path=str(tmp_path / "nonexistent.key"),
        )
        status = guard.check()
        assert status["allowed"] is True
        assert len(status["warnings"]) >= 1
        assert "demo_internal_mode" in status["warnings"][0]

    def test_03_release_mode_blocks_missing_license(self, tmp_path):
        """Release mode blocks when no license key is present."""
        guard = LicenseGuard(
            mode=RELEASE_MODE,
            license_key_path=str(tmp_path / "nonexistent.key"),
        )
        status = guard.check()
        assert status["allowed"] is False
        assert status["license_key_present"] is False
        assert "No license key found" in status["reason"]

    def test_04_release_mode_blocks_expired_license(self, tmp_path):
        """Release mode blocks when license is expired past grace period."""
        expiry = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        license_data = {
            "tier": TIER_PAID_STANDARD,
            "expiry_date": expiry,
            "device_fingerprint": None,  # skip device check
        }
        guard = LicenseGuard(
            mode=RELEASE_MODE,
            license_key_path=str(tmp_path / "license.key"),
            license_data=license_data,
        )
        status = guard.check()
        assert status["allowed"] is False
        assert status["expired"] is True
        assert status["offline_grace_valid"] is False
        assert "expired" in status["reason"].lower()

    def test_05_release_mode_expired_within_grace_allows(self, tmp_path):
        """Release mode allows expired license within offline grace period."""
        expiry = (datetime.now(timezone.utc) - timedelta(hours=12)).isoformat()
        license_data = {
            "tier": TIER_PAID_STANDARD,
            "expiry_date": expiry,
            "device_fingerprint": None,
        }
        guard = LicenseGuard(
            mode=RELEASE_MODE,
            license_key_path=str(tmp_path / "license.key"),
            license_data=license_data,
        )
        status = guard.check()
        assert status["allowed"] is True
        assert status["expired"] is True
        assert status["offline_grace_valid"] is True
        assert len(status["warnings"]) >= 1

    def test_06_release_mode_blocks_account_mismatch(self, tmp_path):
        """Release mode blocks when MT5 login doesn't match license."""
        expiry = (datetime.now(timezone.utc) + timedelta(days=90)).isoformat()
        license_data = {
            "tier": TIER_PAID_STANDARD,
            "expiry_date": expiry,
            "mt5_login": 12345678,
            "device_fingerprint": None,
        }
        guard = LicenseGuard(
            mode=RELEASE_MODE,
            license_key_path=str(tmp_path / "license.key"),
            license_data=license_data,
            mt5_login=87654321,  # different login
        )
        status = guard.check()
        assert status["allowed"] is False
        assert "login mismatch" in status["reason"].lower()

    def test_07_release_mode_blocks_broker_mismatch(self, tmp_path):
        """Release mode blocks when MT5 server doesn't match license."""
        expiry = (datetime.now(timezone.utc) + timedelta(days=90)).isoformat()
        license_data = {
            "tier": TIER_PAID_STANDARD,
            "expiry_date": expiry,
            "mt5_server": "MetaQuotes-Demo",
            "device_fingerprint": None,
        }
        guard = LicenseGuard(
            mode=RELEASE_MODE,
            license_key_path=str(tmp_path / "license.key"),
            license_data=license_data,
            mt5_server="FBS-Demo",  # different server
        )
        status = guard.check()
        assert status["allowed"] is False
        assert "server mismatch" in status["reason"].lower()

    def test_08_release_mode_valid_license_allows(self, tmp_path):
        """Release mode allows with a valid, non-expired license."""
        expiry = (datetime.now(timezone.utc) + timedelta(days=90)).isoformat()
        license_data = {
            "tier": TIER_PAID_STANDARD,
            "expiry_date": expiry,
            "device_fingerprint": None,  # skip device check
        }
        guard = LicenseGuard(
            mode=RELEASE_MODE,
            license_key_path=str(tmp_path / "license.key"),
            license_data=license_data,
        )
        status = guard.check()
        assert status["allowed"] is True
        assert status["license_valid"] is True
        assert status["days_remaining"] > 0

    def test_09_license_status_fields_present(self, tmp_path):
        """All required license status fields are present in the result."""
        guard = LicenseGuard(mode=DEV_MODE)
        status = guard.check()
        required_fields = [
            "allowed", "mode", "license_key_present", "license_valid",
            "expired", "device_bound", "account_bound", "broker_bound",
            "offline_grace_valid", "release_mode", "tier", "expiry_date",
            "days_remaining", "warnings", "errors", "reason",
        ]
        for field in required_fields:
            assert field in status, f"Missing status field: {field}"


class TestAntiTamperGuard:
    """AntiTamperGuard mode-based behavior tests."""

    def test_10_dev_mode_allows(self):
        """Dev mode allows everything — no integrity checks."""
        guard = AntiTamperGuard(mode=DEV_MODE)
        status = guard.check()
        assert status["allowed"] is True
        assert status["tamper_detected"] is False

    def test_11_demo_internal_mode_warns_no_manifest(self):
        """Demo internal mode warns when no integrity manifest found."""
        guard = AntiTamperGuard(
            mode=DEMO_INTERNAL_MODE,
            integrity_manifest_path="/nonexistent/titan.integrity",
        )
        status = guard.check()
        assert status["allowed"] is True
        assert len(status["warnings"]) >= 1
        assert "manifest" in status["warnings"][0].lower()

    def test_12_release_mode_blocks_tamper(self):
        """Release mode blocks when tamper is detected."""
        guard = AntiTamperGuard(
            mode=RELEASE_MODE,
            integrity_manifest_path="/nonexistent/titan.integrity",
        )
        # Manually report a tamper event
        guard.report_tamper(
            file_path="titan/production/trade_loop.py",
            expected_hash="abc123",
            actual_hash="def456",
            check_type="source",
        )
        status = guard.check()
        assert status["allowed"] is False
        assert status["tamper_detected"] is True
        assert len(status["tamper_events"]) >= 1
        assert "Tamper detected" in status["reason"]

    def test_13_tamper_event_fields(self):
        """TamperEvent has all required fields."""
        event = TamperEvent(
            file_path="config/runtime.yaml",
            expected_hash="abc",
            actual_hash="def",
            check_type="config",
        )
        d = event.to_dict()
        assert d["file_path"] == "config/runtime.yaml"
        assert d["expected_hash"] == "abc"
        assert d["actual_hash"] == "def"
        assert d["check_type"] == "config"
        assert d["severity"] == "CRITICAL"
        assert "timestamp_utc" in d


class TestSecurityGate:
    """SecurityGate coordinator tests."""

    def test_14_security_gate_dev_mode_allows(self):
        """SecurityGate allows in dev mode."""
        gate = SecurityGate(mode=DEV_MODE)
        assert gate.allow() is True

    def test_15_security_gate_blocks_release_invalid_license(self, tmp_path):
        """SecurityGate blocks in release mode with invalid license."""
        gate = SecurityGate(
            mode=RELEASE_MODE,
            license_key_path=str(tmp_path / "nonexistent.key"),
            integrity_manifest_path="/nonexistent/titan.integrity",
        )
        assert gate.allow() is False
        status = gate.check()
        assert "License" in status["reason"]
        assert "Tamper" in status["reason"]  # also no manifest

    def test_16_security_gate_enforce_raises(self, tmp_path):
        """SecurityGate.enforce() raises SecurityGateError when blocked."""
        gate = SecurityGate(
            mode=RELEASE_MODE,
            license_key_path=str(tmp_path / "nonexistent.key"),
            integrity_manifest_path="/nonexistent/titan.integrity",
        )
        with pytest.raises(SecurityGateError) as exc_info:
            gate.enforce()
        assert "License" in str(exc_info.value) or "Tamper" in str(exc_info.value)

    def test_17_security_gate_enforce_passes_dev(self):
        """SecurityGate.enforce() does not raise in dev mode."""
        gate = SecurityGate(mode=DEV_MODE)
        gate.enforce()  # should not raise

    def test_18_security_gate_combines_warnings(self, tmp_path):
        """SecurityGate combines warnings from both guards."""
        gate = SecurityGate(
            mode=DEMO_INTERNAL_MODE,
            license_key_path=str(tmp_path / "nonexistent.key"),
            integrity_manifest_path="/nonexistent/titan.integrity",
        )
        status = gate.check()
        assert status["allowed"] is True
        # Should have warnings from both license and tamper guards
        assert len(status["warnings"]) >= 2


class TestNoSecretsInRepo:
    """Verify no secrets, keys, or license data are committed."""

    def test_19_no_hardcoded_license_keys(self):
        """No hard-coded license keys in the security module."""
        import inspect
        from titan.security import license_guard
        src = inspect.getsource(license_guard)
        # Check for common patterns of hard-coded keys
        assert "ghp_" not in src, "GitHub PAT found in license_guard source"
        assert "sk-" not in src, "API key pattern found in license_guard source"
        # The file should mention "license.key" as a PATH, not contain actual key data
        assert "LICENSE_KEY_PATH" in src

    def test_20_no_real_license_key_file_committed(self):
        """No real license key file is committed to the repo."""
        # The default license path is ~/.titan/license.key (outside the repo)
        assert str(LICENSE_KEY_PATH).startswith(str(Path.home()))
        # Check that no .key files are tracked in titan/security/
        import subprocess
        result = subprocess.run(
            ["git", "ls-files", "titan/security/"],
            capture_output=True, text=True, cwd=str(REPO_ROOT),
        )
        tracked_files = result.stdout.strip().split("\n")
        for f in tracked_files:
            assert not f.endswith(".key"), f"License key file tracked: {f}"

    def test_21_no_secrets_in_security_modules(self):
        """No secrets in any security module source."""
        import inspect
        from titan.security import license_guard, anti_tamper_guard, security_gate
        for module in [license_guard, anti_tamper_guard, security_gate]:
            src = inspect.getsource(module)
            # Check for common secret patterns
            assert "-----BEGIN" not in src, f"Private key in {module.__name__}"
            assert "password" not in src.lower() or "password" in src.lower().split("#")[0].split('"')[0]
            # The word "secret" is fine in comments/descriptions but not as a value
            # This is a soft check — we're looking for actual secret VALUES

    def test_22_gitignore_covers_key_files(self):
        """Gitignore covers .key and .secret files."""
        gitignore = (REPO_ROOT / ".gitignore").read_text()
        assert "*.key" in gitignore
        assert "*.secret" in gitignore
