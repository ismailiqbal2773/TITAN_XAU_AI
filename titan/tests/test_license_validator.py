"""
TITAN XAU AI — Commercial License Validator Tests
==================================================

12+ tests covering:
  - Format check (valid / invalid keys)
  - Tier sanity
  - Expiry (online / offline / grace)
  - Machine binding (match / mismatch / tolerant match)
  - Feature flags (present / missing)
  - Tamper detection (missing / wrong signature)
  - Fail-closed for live trading
  - LicenseAudit verdict mapping

NEVER imports MetaTrader5. NEVER calls mt5.order_send.
"""
from __future__ import annotations

import hashlib
import hmac
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

from titan.commercial.licensing.expiry_guard import ExpiryGuard, ExpiryResult
from titan.commercial.licensing.machine_binding import (
    MachineBinding, MachineSignature,
)
from titan.commercial.licensing.license_validator import (
    LicenseInfo, LicenseValidationResult, LicenseValidator,
    LICENSE_KEY_PATTERN, TIER_FEATURES,
)
from titan.commercial.licensing.license_audit import (
    LicenseAudit, LicenseAuditResult,
    LICENSE_VALID, LICENSE_EXPIRED, LICENSE_INVALID, LICENSE_GRACE_PERIOD,
)


SECRET = b"test-licensing-secret-0123456789"


# ─── Fixtures ──────────────────────────────────────────────────────────

def _sig(info: LicenseInfo, secret: bytes = SECRET) -> str:
    msg = f"{info.license_key}|{int(info.expiry_epoch)}|{info.machine_signature}".encode()
    return hmac.new(secret, msg, hashlib.sha256).hexdigest()


@pytest.fixture
def machine_binding() -> MachineBinding:
    return MachineBinding.collect()


@pytest.fixture
def validator(machine_binding: MachineBinding) -> LicenseValidator:
    return LicenseValidator(
        machine_binding=machine_binding,
        expiry_guard=ExpiryGuard(offline_grace_hours=72.0),
        signing_secret=SECRET,
    )


def _valid_info(machine_signature: str, **overrides) -> LicenseInfo:
    base = LicenseInfo(
        license_key="TITAN-FULL-" + "a" * 32 + "-AB12",
        expiry_epoch=time.time() + 86400.0,
        machine_signature=machine_signature,
        features=("broker", "market_data", "execution", "risk"),
        tier="FULL",
        issued_epoch=time.time() - 86400.0,
        signature="",
    )
    base = LicenseInfo(**{**base.to_dict(), **overrides})  # type: ignore[arg-type]
    base = LicenseInfo(
        license_key=base.license_key,
        expiry_epoch=base.expiry_epoch,
        machine_signature=base.machine_signature,
        features=base.features,
        tier=base.tier,
        issued_epoch=base.issued_epoch,
        last_known_good_epoch=base.last_known_good_epoch,
        signature=_sig(base),
    )
    return base


# ─── 1. Format checks ─────────────────────────────────────────────────

class TestLicenseKeyFormat:
    def test_valid_key_pattern_matches(self):
        key = "TITAN-PRO-" + "0" * 32 + "-ZZ99"
        assert LICENSE_KEY_PATTERN.match(key) is not None

    def test_invalid_key_pattern_rejected(self):
        assert LICENSE_KEY_PATTERN.match("BADKEY-12345") is None
        assert LICENSE_KEY_PATTERN.match("TITAN-BOGUS-" + "0" * 32 + "-ZZ99") is None
        assert LICENSE_KEY_PATTERN.match("TITAN-FULL-short-AB12") is None


# ─── 2. Validator: valid license ──────────────────────────────────────

class TestValidatorHappyPath:
    def test_valid_license_passes_all_checks(self, validator, machine_binding):
        sig = machine_binding.get_machine_signature()
        info = _valid_info(sig.composite)
        result = validator.validate_license(
            info, required_features=("broker", "execution"), for_live=True,
        )
        assert result.valid, result.reason
        assert result.machine_bound is True
        assert result.fail_closed_live is True
        assert result.in_grace is False
        assert result.checks["format"] is True
        assert result.checks["tamper"] is True
        assert result.checks["expiry"] is True
        assert result.checks["features"] is True
        assert result.checks["machine_binding"] is True


# ─── 3. Validator: format failure ─────────────────────────────────────

class TestValidatorFormatFailure:
    def test_invalid_key_format_blocks(self, validator, machine_binding):
        sig = machine_binding.get_machine_signature()
        info = _valid_info(sig.composite)
        info = LicenseInfo(**{**info.to_dict(), "license_key": "BAD-KEY", "signature": ""})
        # Need to recompute signature with new key
        info = LicenseInfo(
            license_key="BAD-KEY",
            expiry_epoch=info.expiry_epoch,
            machine_signature=info.machine_signature,
            features=info.features,
            tier=info.tier,
            issued_epoch=info.issued_epoch,
            signature=_sig(info),
        )
        result = validator.validate_license(info, for_live=True)
        assert not result.valid
        assert result.checks["format"] is False
        assert result.fail_closed_live is False
        assert "invalid license key format" in result.reason


# ─── 4. Validator: expiry ─────────────────────────────────────────────

class TestValidatorExpiry:
    def test_expired_license_online_blocks(self, validator, machine_binding):
        sig = machine_binding.get_machine_signature()
        info = _valid_info(sig.composite, expiry_epoch=time.time() - 3600.0)
        result = validator.validate_license(info, for_live=True, online=True)
        assert not result.valid
        assert result.checks["expiry"] is False
        assert "expired" in result.reason.lower()

    def test_offline_grace_allows_read_only(self, machine_binding):
        """Offline + expired + within grace → valid but in_grace (live blocked)."""
        now = time.time()
        eg = ExpiryGuard(offline_grace_hours=72.0, clock=lambda: now)
        v = LicenseValidator(
            machine_binding=machine_binding, expiry_guard=eg, signing_secret=SECRET,
        )
        sig = machine_binding.get_machine_signature()
        info = _valid_info(
            sig.composite,
            expiry_epoch=now - 3600.0,  # expired 1h ago
            last_known_good_epoch=now - 1800.0,  # 30min ago, well within 72h grace
        )
        result = v.validate_license(info, for_live=True, online=False, now=now)
        assert result.valid is True
        assert result.in_grace is True
        assert result.grace_period_remaining_hours > 0.0
        # Live trading is blocked while in grace.
        assert result.fail_closed_live is False

    def test_offline_grace_exhausted_blocks(self, machine_binding):
        now = time.time()
        eg = ExpiryGuard(offline_grace_hours=1.0, clock=lambda: now)
        v = LicenseValidator(
            machine_binding=machine_binding, expiry_guard=eg, signing_secret=SECRET,
        )
        sig = machine_binding.get_machine_signature()
        info = _valid_info(
            sig.composite,
            expiry_epoch=now - 7200.0,  # expired 2h ago
            last_known_good_epoch=now - 7200.0,  # grace deadline = -1h ago → exhausted
        )
        result = v.validate_license(info, for_live=True, online=False, now=now)
        assert not result.valid
        assert "offline grace period exhausted" in result.reason

    def test_offline_no_last_known_good_fail_closed(self, machine_binding):
        now = time.time()
        eg = ExpiryGuard(offline_grace_hours=72.0, clock=lambda: now)
        v = LicenseValidator(
            machine_binding=machine_binding, expiry_guard=eg, signing_secret=SECRET,
        )
        sig = machine_binding.get_machine_signature()
        info = _valid_info(
            sig.composite,
            expiry_epoch=now - 3600.0,
            last_known_good_epoch=None,  # fail-closed
        )
        result = v.validate_license(info, for_live=True, online=False, now=now)
        assert not result.valid
        assert "fail-closed" in result.reason


# ─── 5. Validator: machine binding ────────────────────────────────────

class TestValidatorMachineBinding:
    def test_machine_mismatch_blocks(self, machine_binding):
        v = LicenseValidator(
            machine_binding=machine_binding,
            expiry_guard=ExpiryGuard(),
            signing_secret=SECRET,
        )
        # Wrong signature (a random 64-hex string)
        info = _valid_info("0" * 64)
        result = v.validate_license(info, for_live=True)
        assert not result.valid
        assert result.checks["machine_binding"] is False
        assert result.machine_bound is False
        assert "machine binding" in result.reason.lower()

    def test_tolerant_match_via_components(self, machine_binding):
        """5/6 component match should still bind."""
        sig = machine_binding.get_machine_signature()
        # Mutate one component to a wrong digest (still 5/6 match)
        comp = dict(sig.components)
        first_key = next(iter(comp))
        comp[first_key] = "0" * 64
        bad_sig = MachineSignature(
            composite="not-the-real-composite",
            components=comp,
            short_id="DEADBEEFDEADBEEF",
        )
        v = LicenseValidator(
            machine_binding=machine_binding,
            expiry_guard=ExpiryGuard(),
            signing_secret=SECRET,
        )
        info = _valid_info(bad_sig)  # type: ignore[arg-type]
        result = v.validate_license(info, for_live=True)
        assert result.checks["machine_binding"] is True
        assert result.machine_bound is True


# ─── 6. Validator: features ───────────────────────────────────────────

class TestValidatorFeatures:
    def test_missing_feature_blocks(self, validator, machine_binding):
        sig = machine_binding.get_machine_signature()
        info = _valid_info(sig.composite)
        result = validator.validate_license(
            info, required_features=("broker", "ai:lstm", "ai:nonexistent"),
            for_live=True,
        )
        assert not result.valid
        assert result.checks["features"] is False
        assert "missing features" in result.reason.lower()

    def test_wildcard_feature_grants_all(self, machine_binding):
        sig = machine_binding.get_machine_signature()
        info = _valid_info(sig.composite, tier="ENT", features=("*",))
        # ENT tier supports "*"
        result = LicenseValidator(
            machine_binding=machine_binding,
            expiry_guard=ExpiryGuard(),
            signing_secret=SECRET,
        ).validate_license(
            info,
            required_features=("anything", "we", "want"),
            for_live=True,
        )
        assert result.checks["features"] is True


# ─── 7. Validator: tamper detection ───────────────────────────────────

class TestValidatorTamper:
    def test_missing_signature_blocks_live(self, machine_binding):
        v = LicenseValidator(
            machine_binding=machine_binding,
            expiry_guard=ExpiryGuard(),
            signing_secret=SECRET,
        )
        sig = machine_binding.get_machine_signature()
        info = _valid_info(sig.composite)
        info = LicenseInfo(**{**info.to_dict(), "signature": ""})
        result = v.validate_license(info, for_live=True)
        assert not result.valid
        assert result.checks["tamper"] is False
        assert "signature missing" in result.reason.lower()

    def test_wrong_signature_blocks(self, validator, machine_binding):
        sig = machine_binding.get_machine_signature()
        info = _valid_info(sig.composite)
        info = LicenseInfo(**{**info.to_dict(), "signature": "deadbeef" * 8})
        result = validator.validate_license(info, for_live=True)
        assert not result.valid
        assert result.checks["tamper"] is False
        assert "signature mismatch" in result.reason.lower() or "tamper" in result.reason.lower()

    def test_no_secret_blocks_live(self, machine_binding):
        v = LicenseValidator(
            machine_binding=machine_binding,
            expiry_guard=ExpiryGuard(),
            signing_secret=b"",  # no secret
        )
        sig = machine_binding.get_machine_signature()
        info = _valid_info(sig.composite)
        result = v.validate_license(info, for_live=True)
        # Live trading must be blocked without a secret.
        assert not result.valid
        assert "signing secret not configured" in result.reason.lower()


# ─── 8. Audit verdicts ────────────────────────────────────────────────

class TestLicenseAuditVerdicts:
    def _audit(self, machine_binding, info, online=True, now=None, for_live=True):
        audit = LicenseAudit(
            machine_binding=machine_binding,
            expiry_guard=ExpiryGuard(offline_grace_hours=72.0),
            signing_secret=SECRET,
        )
        return audit.audit(
            info, required_features=("broker",), for_live=for_live, online=online, now=now,
        )

    def test_audit_valid_verdict(self, machine_binding):
        sig = machine_binding.get_machine_signature()
        info = _valid_info(sig.composite)
        result = self._audit(machine_binding, info, online=True)
        assert result.verdict == LICENSE_VALID
        assert result.live_trading_permitted is True

    def test_audit_expired_verdict(self, machine_binding):
        sig = machine_binding.get_machine_signature()
        info = _valid_info(sig.composite, expiry_epoch=time.time() - 3600.0)
        result = self._audit(machine_binding, info, online=True)
        assert result.verdict == LICENSE_EXPIRED
        assert result.live_trading_permitted is False

    def test_audit_grace_period_verdict(self, machine_binding):
        now = time.time()
        sig = machine_binding.get_machine_signature()
        info = _valid_info(
            sig.composite,
            expiry_epoch=now - 3600.0,
            last_known_good_epoch=now - 1800.0,
        )
        result = self._audit(machine_binding, info, online=False, now=now)
        assert result.verdict == LICENSE_GRACE_PERIOD
        # Live trading blocked during grace.
        assert result.live_trading_permitted is False
        assert result.valid is True

    def test_audit_invalid_verdict_on_tamper(self, machine_binding):
        sig = machine_binding.get_machine_signature()
        info = _valid_info(sig.composite)
        info = LicenseInfo(**{**info.to_dict(), "signature": "deadbeef" * 8})
        result = self._audit(machine_binding, info, online=True)
        assert result.verdict == LICENSE_INVALID
        assert result.live_trading_permitted is False

    def test_audit_invalid_verdict_on_format(self, machine_binding):
        sig = machine_binding.get_machine_signature()
        info = _valid_info(sig.composite)
        info = LicenseInfo(
            license_key="BAD-KEY",
            expiry_epoch=info.expiry_epoch,
            machine_signature=info.machine_signature,
            features=info.features,
            tier=info.tier,
            issued_epoch=info.issued_epoch,
            signature=_sig(LicenseInfo(
                license_key="BAD-KEY",
                expiry_epoch=info.expiry_epoch,
                machine_signature=info.machine_signature,
            )),
        )
        result = self._audit(machine_binding, info, online=True)
        assert result.verdict == LICENSE_INVALID
