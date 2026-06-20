"""Tests for Licensing Module — hardware fingerprint, JWT, activation, expiry, anti-tamper"""
import json
import time
import pytest

from titan.licensing.fingerprint import (
    HardwareFingerprint, FingerprintComponent, ComponentReading, SALT,
)
from titan.licensing.jwt_license import (
    JWTLicenseEngine, LicenseToken, LicenseClaims, LicenseType, LicenseTier,
    LicenseStatus, TIER_DURATION_SECONDS,
)
from titan.licensing.store import LicenseStore, StoredLicense
from titan.licensing.activation import (
    ActivationServer, ActivationClient, ActivationRequest, ActivationResponse,
    ActivationMode, OfflineActivationCode, ACTIVATION_TTL_SECONDS,
)
from titan.licensing.guard import (
    LicenseGuard, GuardAction, GuardViolation, GuardViolationError,
)


SECRET = "titan-test-secret-1234567890"


# ─── Hardware Fingerprint ─────────────────────────────────────────────────

class TestHardwareFingerprint:
    def test_collect_returns_6_components(self):
        fp = HardwareFingerprint.collect()
        assert fp.component_count() == 6

    def test_composite_digest_deterministic(self):
        fp1 = HardwareFingerprint.collect()
        fp2 = HardwareFingerprint.collect()
        # On same machine, both should produce identical composite
        assert fp1.composite_digest() == fp2.composite_digest()

    def test_short_id_is_16_hex_uppercase(self):
        fp = HardwareFingerprint.collect()
        sid = fp.short_id()
        assert len(sid) == 16
        assert sid == sid.upper()
        # All hex
        int(sid, 16)

    def test_machine_id_is_64_hex(self):
        fp = HardwareFingerprint.collect()
        mid = fp.machine_id()
        assert len(mid) == 64
        int(mid, 16)  # valid hex

    def test_match_exact(self):
        fp1 = HardwareFingerprint.collect()
        fp2 = HardwareFingerprint.collect()
        matched, ratio = fp1.match(fp2)
        assert matched
        assert ratio == 1.0

    def test_match_with_one_component_drift_5_of_6(self):
        """5/6 components match → still valid (tolerance for HW replacement).

        MIN_MATCH_RATIO = 5/6, so 5/6 components matching is exactly at
        the threshold and should pass.
        """
        fp1 = HardwareFingerprint.collect()
        readings = dict(fp1._readings)
        # Mutate one component
        comp = list(readings.keys())[0]
        readings[comp] = ComponentReading(
            name=comp, raw="mutated",
            digest="0" * 64,
        )
        fp2 = HardwareFingerprint(readings)
        matched, ratio = fp1.match(fp2)
        assert ratio == 5 / 6
        assert matched  # at threshold (5/6 >= 5/6)

    def test_to_dict_redacts_raw(self):
        fp = HardwareFingerprint.collect()
        d = fp.to_dict()
        assert "components" in d
        for name, digest in d["components"].items():
            assert "raw" not in digest  # only digest exposed
            assert len(digest) == 64

    def test_injected_readings_used(self):
        """Verify fingerprint can be constructed from injected readings (testing)."""
        readings = {
            comp: ComponentReading(
                name=comp, raw=f"test-{comp.value}",
                digest="a" * 64,
            )
            for comp in FingerprintComponent
        }
        fp = HardwareFingerprint(readings)
        assert fp.component_count() == 6
        assert fp.composite_digest()  # not raising


# ─── JWT License Engine ────────────────────────────────────────────────────

class TestJWTLicenseEngine:
    def test_issue_returns_valid_token(self):
        eng = JWTLicenseEngine(SECRET)
        token = eng.issue(
            machine_id="abc123", account_id="12345",
            tier=LicenseTier.YEARLY,
        )
        assert token.signature_valid
        assert token.claims.sub == "abc123"
        assert token.claims.account_id == "12345"
        assert token.claims.tier == LicenseTier.YEARLY.value
        assert token.claims.status == LicenseStatus.ACTIVE.value

    def test_verify_roundtrip(self):
        eng = JWTLicenseEngine(SECRET)
        token = eng.issue(
            machine_id="abc123", account_id="12345",
            tier=LicenseTier.MONTHLY,
        )
        verified = eng.verify(token.token)
        assert verified.signature_valid
        assert verified.claims.sub == "abc123"
        assert verified.claims.account_id == "12345"

    def test_verify_rejects_wrong_secret(self):
        eng1 = JWTLicenseEngine(SECRET)
        eng2 = JWTLicenseEngine("different-secret-1234567")
        token = eng1.issue(
            machine_id="abc123", account_id="12345",
            tier=LicenseTier.YEARLY,
        )
        verified = eng2.verify(token.token)
        assert not verified.signature_valid

    def test_verify_rejects_tampered_payload(self):
        eng = JWTLicenseEngine(SECRET)
        # Issue MONTHLY, then tamper to upgrade to YEARLY
        token = eng.issue(
            machine_id="abc123", account_id="12345",
            tier=LicenseTier.MONTHLY,
        )
        parts = token.token.split(".")
        import base64, json
        payload = json.loads(base64.urlsafe_b64decode(parts[1] + "=="))
        payload["tier"] = LicenseTier.YEARLY.value  # try to upgrade
        new_payload = base64.urlsafe_b64encode(
            json.dumps(payload, separators=(",", ":")).encode()
        ).rstrip(b"=").decode()
        tampered_token = f"{parts[0]}.{new_payload}.{parts[2]}"
        verified = eng.verify(tampered_token)
        assert not verified.signature_valid

    def test_tier_durations(self):
        assert TIER_DURATION_SECONDS[LicenseTier.MONTHLY] == 30 * 86400
        assert TIER_DURATION_SECONDS[LicenseTier.QUARTERLY] == 90 * 86400
        assert TIER_DURATION_SECONDS[LicenseTier.YEARLY] == 365 * 86400

    def test_monthly_expiry_30_days(self):
        eng = JWTLicenseEngine(SECRET)
        now = int(time.time())
        token = eng.issue(
            machine_id="abc", account_id="1",
            tier=LicenseTier.MONTHLY, issued_at=now,
        )
        assert token.claims.exp - token.claims.iat == 30 * 86400

    def test_quarterly_expiry_90_days(self):
        eng = JWTLicenseEngine(SECRET)
        now = int(time.time())
        token = eng.issue(
            machine_id="abc", account_id="1",
            tier=LicenseTier.QUARTERLY, issued_at=now,
        )
        assert token.claims.exp - token.claims.iat == 90 * 86400

    def test_yearly_expiry_365_days(self):
        eng = JWTLicenseEngine(SECRET)
        now = int(time.time())
        token = eng.issue(
            machine_id="abc", account_id="1",
            tier=LicenseTier.YEARLY, issued_at=now,
        )
        assert token.claims.exp - token.claims.iat == 365 * 86400

    def test_check_status_active(self):
        eng = JWTLicenseEngine(SECRET)
        token = eng.issue(
            machine_id="abc", account_id="1",
            tier=LicenseTier.YEARLY,
        )
        assert eng.check_status(token) == LicenseStatus.ACTIVE

    def test_check_status_expired_past_grace(self):
        eng = JWTLicenseEngine(SECRET)
        # Issue token far in the past
        past = int(time.time()) - 400 * 86400  # 400 days ago
        token = eng.issue(
            machine_id="abc", account_id="1",
            tier=LicenseTier.YEARLY, issued_at=past,
        )
        assert eng.check_status(token) == LicenseStatus.EXPIRED

    def test_check_status_in_grace_period(self):
        eng = JWTLicenseEngine(SECRET)
        # Issue 30 days ago, grace = 7 days → in grace
        past = int(time.time()) - 32 * 86400
        token = eng.issue(
            machine_id="abc", account_id="1",
            tier=LicenseTier.MONTHLY, issued_at=past,
            grace_seconds=7 * 86400,
        )
        assert token.is_expired
        assert token.in_grace_period
        assert eng.check_status(token) == LicenseStatus.ACTIVE

    def test_check_status_revoked(self):
        eng = JWTLicenseEngine(SECRET)
        token = eng.issue(
            machine_id="abc", account_id="1",
            tier=LicenseTier.YEARLY,
        )
        token.claims.status = LicenseStatus.REVOKED.value
        assert eng.check_status(token) == LicenseStatus.REVOKED

    def test_short_secret_rejected(self):
        with pytest.raises(ValueError):
            JWTLicenseEngine("short")

    def test_features_per_license_type(self):
        eng = JWTLicenseEngine(SECRET)
        trial = eng.issue("m", "a", LicenseTier.MONTHLY,
                          license_type=LicenseType.TRIAL)
        full = eng.issue("m", "a", LicenseTier.MONTHLY,
                         license_type=LicenseType.FULL)
        pro = eng.issue("m", "a", LicenseTier.MONTHLY,
                        license_type=LicenseType.PRO)
        ent = eng.issue("m", "a", LicenseTier.MONTHLY,
                        license_type=LicenseType.ENTERPRISE)
        assert "ai:lstm" not in trial.claims.features
        assert "ai:lstm" in full.claims.features
        assert "ai:transformer" in pro.claims.features
        assert "*" in ent.claims.features


# ─── License Store ─────────────────────────────────────────────────────────

class TestLicenseStore:
    def test_save_and_get(self):
        eng = JWTLicenseEngine(SECRET)
        store = LicenseStore(":memory:")
        token = eng.issue("machine-1", "acct-1", LicenseTier.YEARLY)
        saved = store.save(token)
        assert saved
        retrieved = store.get_by_jti(token.claims.jti)
        assert retrieved is not None
        assert retrieved.account_id == "acct-1"

    def test_single_account_enforcement(self):
        """One ACTIVE license per account_id."""
        eng = JWTLicenseEngine(SECRET)
        store = LicenseStore(":memory:")
        t1 = eng.issue("machine-1", "acct-1", LicenseTier.YEARLY,
                       jti="jti-1")
        assert store.save(t1)
        # Different machine, same account → blocked
        t2 = eng.issue("machine-2", "acct-1", LicenseTier.YEARLY,
                       jti="jti-2")
        assert not store.save(t2)

    def test_revoke_license(self):
        eng = JWTLicenseEngine(SECRET)
        store = LicenseStore(":memory:")
        token = eng.issue("machine-1", "acct-1", LicenseTier.YEARLY)
        store.save(token)
        store.revoke(token.claims.jti, reason="Payment refunded")
        assert store.is_revoked(token.claims.jti)
        # Same account can now be re-activated
        t2 = eng.issue("machine-1", "acct-1", LicenseTier.YEARLY,
                       jti="jti-new")
        assert store.save(t2)

    def test_anti_tamper_digest(self):
        eng = JWTLicenseEngine(SECRET)
        store = LicenseStore(":memory:")
        token = eng.issue("machine-1", "acct-1", LicenseTier.YEARLY)
        store.save(token)
        # Token in store verifies
        assert store.verify_token(token.token)
        # Tampered token does not
        assert not store.verify_token(token.token + "x")

    def test_list_for_machine(self):
        eng = JWTLicenseEngine(SECRET)
        store = LicenseStore(":memory:")
        for i in range(3):
            t = eng.issue("machine-X", f"acct-{i}", LicenseTier.MONTHLY,
                          jti=f"jti-{i}")
            store.save(t)
        result = store.list_for_machine("machine-X")
        assert len(result) == 3

    def test_record_activation(self):
        eng = JWTLicenseEngine(SECRET)
        store = LicenseStore(":memory:")
        token = eng.issue("m", "a", LicenseTier.YEARLY, jti="jti-1")
        store.save(token)
        store.record_activation(
            "act-1", "jti-1", "m", "a", "online",
            ip_addr="1.2.3.4", fingerprint="ABCDEF",
        )
        # No direct query for activation, but no error means OK
        assert True


# ─── Activation ────────────────────────────────────────────────────────────

class TestOnlineActivation:
    def test_full_flow(self):
        eng = JWTLicenseEngine(SECRET)
        client_store = LicenseStore(":memory:")
        server_store = LicenseStore(":memory:")
        client = ActivationClient(eng, client_store)
        server = ActivationServer(eng, server_store)

        req = client.build_request(
            account_id="12345", tier=LicenseTier.YEARLY,
            customer_email="trader@example.com",
        )
        resp = server.handle_online(req)
        assert resp.success
        assert resp.token

        token = client.apply_online_response(resp)
        assert token.claims.account_id == "12345"
        assert token.signature_valid

    def test_expired_request_rejected(self):
        eng = JWTLicenseEngine(SECRET)
        client = ActivationClient(eng, LicenseStore(":memory:"))
        server = ActivationServer(eng, LicenseStore(":memory:"))
        req = client.build_request("12345", LicenseTier.YEARLY)
        # Backdate
        req.timestamp = int(time.time()) - 2 * ACTIVATION_TTL_SECONDS
        resp = server.handle_online(req)
        assert not resp.success
        assert "expired" in resp.error.lower()

    def test_account_already_activated_elsewhere(self):
        eng = JWTLicenseEngine(SECRET)
        client = ActivationClient(eng, LicenseStore(":memory:"))
        server_store = LicenseStore(":memory:")
        server = ActivationServer(eng, server_store)

        # First activation on machine-1
        req1 = client.build_request("12345", LicenseTier.YEARLY)
        resp1 = server.handle_online(req1)
        assert resp1.success

        # Second activation for SAME account, DIFFERENT machine
        req2 = client.build_request("12345", LicenseTier.YEARLY)
        req2.machine_id = "different-machine"
        resp2 = server.handle_online(req2)
        assert not resp2.success
        assert "another machine" in resp2.error.lower()


class TestOfflineActivation:
    def test_offline_code_format(self):
        eng = JWTLicenseEngine(SECRET)
        client = ActivationClient(eng, LicenseStore(":memory:"))
        server = ActivationServer(eng, LicenseStore(":memory:"))
        req = client.build_request("12345", LicenseTier.QUARTERLY)
        resp = server.handle_offline(req)
        assert resp.success
        code = resp.offline_code
        # Format: 6 blocks of 5 chars, separated by -
        blocks = code.split("-")
        assert len(blocks) == 6
        for b in blocks:
            assert len(b) == 5

    def test_offline_apply(self):
        eng = JWTLicenseEngine(SECRET)
        client = ActivationClient(eng, LicenseStore(":memory:"))
        server = ActivationServer(eng, LicenseStore(":memory:"))
        req = client.build_request("99999", LicenseTier.MONTHLY)
        resp = server.handle_offline(req)
        assert resp.success
        # Client receives offline code + JWT
        combined = resp.offline_code + "|" + resp.token
        token = client.apply_offline_code(combined, req)
        assert token.claims.account_id == "99999"
        assert token.claims.tier == LicenseTier.MONTHLY.value

    def test_offline_code_wrong_token_rejected(self):
        eng = JWTLicenseEngine(SECRET)
        client = ActivationClient(eng, LicenseStore(":memory:"))
        server = ActivationServer(eng, LicenseStore(":memory:"))
        req = client.build_request("99999", LicenseTier.MONTHLY)
        resp = server.handle_offline(req)
        # Generate a DIFFERENT token, try to apply with original code
        other_token = eng.issue("m", "99999", LicenseTier.MONTHLY)
        combined = resp.offline_code + "|" + other_token.token
        with pytest.raises(ValueError, match="does not match"):
            client.apply_offline_code(combined, req)

    def test_offline_mismatched_request_rejected(self):
        """Offline code bound to machine-A cannot be applied on machine-B.

        We inject different fingerprints to simulate two different machines.
        """
        eng = JWTLicenseEngine(SECRET)
        client_store_a = LicenseStore(":memory:")
        client_store_b = LicenseStore(":memory:")
        client_a = ActivationClient(eng, client_store_a)
        client_b = ActivationClient(eng, client_store_b)
        server = ActivationServer(eng, LicenseStore(":memory:"))
        req_a = client_a.build_request("99999", LicenseTier.MONTHLY)
        resp = server.handle_offline(req_a)
        # Build req_b but with DIFFERENT machine_id (simulate machine B)
        req_b = client_b.build_request("99999", LicenseTier.MONTHLY)
        req_b.machine_id = "different-machine-id-xyz"
        combined = resp.offline_code + "|" + resp.token
        with pytest.raises(ValueError, match="does not match"):
            client_b.apply_offline_code(combined, req_b)


# ─── License Guard ─────────────────────────────────────────────────────────

class TestLicenseGuard:
    def _make_guard(self, machine_id: str, account_id: str = "12345"):
        """Build a guard with an active license for the given machine."""
        eng = JWTLicenseEngine(SECRET)
        store = LicenseStore(":memory:")
        # Build fingerprint with controlled machine_id
        from titan.licensing.fingerprint import HardwareFingerprint, FingerprintComponent, ComponentReading
        readings = {
            comp: ComponentReading(
                name=comp, raw=f"test-{comp.value}-{machine_id}",
                digest=f"hash-{comp.value}-{machine_id}",
            )
            for comp in FingerprintComponent
        }
        fp = HardwareFingerprint(readings)
        # Issue a token bound to this machine
        token = eng.issue(
            machine_id=fp.machine_id(),
            account_id=account_id,
            tier=LicenseTier.YEARLY,
        )
        store.save(token)
        guard = LicenseGuard(eng, store, fingerprint=fp)
        return eng, store, guard, token

    def test_startup_check_passes(self):
        eng, store, guard, token = self._make_guard("machine-1")
        # Should pass
        result = guard.startup_check(account_id="12345")
        assert result.claims.account_id == "12345"
        assert guard.active_token is not None

    def test_startup_check_no_license(self):
        eng = JWTLicenseEngine(SECRET)
        store = LicenseStore(":memory:")
        from titan.licensing.fingerprint import HardwareFingerprint
        guard = LicenseGuard(eng, store, fingerprint=HardwareFingerprint.collect())
        with pytest.raises(GuardViolationError) as exc:
            guard.startup_check(account_id="missing")
        assert exc.value.violation.code == "LIC_NOT_FOUND"

    def test_startup_check_wrong_account(self):
        """License bound to account A cannot run on account B."""
        eng, store, guard, token = self._make_guard("machine-1", account_id="11111")
        with pytest.raises(GuardViolationError) as exc:
            guard.startup_check(account_id="22222")
        assert exc.value.violation.code == "LIC_ACCT_MISMATCH"

    def test_startup_check_revoked(self):
        eng, store, guard, token = self._make_guard("machine-1")
        store.revoke(token.claims.jti, reason="test")
        with pytest.raises(GuardViolationError) as exc:
            guard.startup_check(account_id="12345")
        assert exc.value.violation.code == "LIC_REVOKED"

    def test_startup_check_expired_hard(self):
        """Token past grace period → halt."""
        eng = JWTLicenseEngine(SECRET)
        store = LicenseStore(":memory:")
        from titan.licensing.fingerprint import HardwareFingerprint, FingerprintComponent, ComponentReading
        readings = {
            comp: ComponentReading(
                name=comp, raw="x",
                digest=f"d-{comp.value}",
            )
            for comp in FingerprintComponent
        }
        fp = HardwareFingerprint(readings)
        past = int(time.time()) - 400 * 86400  # 400 days ago
        token = eng.issue(
            machine_id=fp.machine_id(), account_id="12345",
            tier=LicenseTier.YEARLY, issued_at=past,
        )
        store.save(token)
        guard = LicenseGuard(eng, store, fingerprint=fp)
        with pytest.raises(GuardViolationError) as exc:
            guard.startup_check(account_id="12345")
        assert exc.value.violation.code in ("LIC_EXPIRED", "LIC_EXPIRED_HARD")

    def test_feature_gating(self):
        """FULL license has 'ai:lstm' but not 'ai:transformer' (Pro only)."""
        eng, store, guard, token = self._make_guard("machine-1")
        # Must call startup_check first to populate active_token
        guard.startup_check(account_id="12345")
        # FULL license has ai:lstm but NOT ai:transformer (Pro/Ent only)
        assert guard.has_feature("ai:lstm")
        assert not guard.has_feature("ai:transformer")
        # 'unknown' feature not in list
        assert not guard.has_feature("nonexistent-feature")

    def test_require_feature_raises(self):
        eng, store, guard, token = self._make_guard("machine-1")
        guard.startup_check(account_id="12345")
        with pytest.raises(GuardViolationError) as exc:
            guard.require_feature("nonexistent-feature")
        assert exc.value.violation.code == "LIC_FEATURE_DENIED"

    def test_violation_callback(self):
        callbacks = []
        eng = JWTLicenseEngine(SECRET)
        store = LicenseStore(":memory:")
        from titan.licensing.fingerprint import HardwareFingerprint
        guard = LicenseGuard(
            eng, store, fingerprint=HardwareFingerprint.collect(),
            on_violation=lambda v: callbacks.append(v),
        )
        with pytest.raises(GuardViolationError):
            guard.startup_check(account_id="missing")
        assert len(callbacks) == 1
        assert callbacks[0].code == "LIC_NOT_FOUND"
        assert callbacks[0].action == GuardAction.HALT

    def test_heartbeat_async(self):
        """Heartbeat re-verifies the token every cycle."""
        import asyncio
        eng, store, guard, token = self._make_guard("machine-1")
        guard.startup_check(account_id="12345")

        async def run_test():
            # Use a short heartbeat for testing
            guard.HEARTBEAT_INTERVAL_SECONDS = 0.05
            await guard.start_heartbeat()
            await asyncio.sleep(0.15)
            await guard.stop_heartbeat()

        asyncio.run(run_test())
        # No violation recorded (token still valid)
        assert not guard.violations

    def test_heartbeat_detects_revocation(self):
        """If license is revoked mid-run, heartbeat raises."""
        import asyncio
        eng, store, guard, token = self._make_guard("machine-1")
        guard.startup_check(account_id="12345")

        async def run_test():
            guard.HEARTBEAT_INTERVAL_SECONDS = 0.05
            await guard.start_heartbeat()
            await asyncio.sleep(0.06)
            # Revoke mid-run
            store.revoke(token.claims.jti, "mid-run test")
            await asyncio.sleep(0.1)
            await guard.stop_heartbeat()

        asyncio.run(run_test())
        # Should have recorded a halt-level violation
        halt_violations = [v for v in guard.violations
                           if v.action == GuardAction.HALT]
        assert halt_violations


# ─── Integration: full pipeline ────────────────────────────────────────────

class TestLicensingIntegration:
    def test_full_yearly_online_flow(self):
        """End-to-end: build request → activate online → guard startup → heartbeat."""
        eng = JWTLicenseEngine(SECRET)
        client_store = LicenseStore(":memory:")
        server_store = LicenseStore(":memory:")
        client = ActivationClient(eng, client_store)
        server = ActivationServer(eng, server_store)

        req = client.build_request(
            account_id="ACC-MAIN", tier=LicenseTier.YEARLY,
            customer_email="ceo@fund.com",
        )
        resp = server.handle_online(req)
        token = client.apply_online_response(resp)

        # Now build a guard on the client side
        from titan.licensing.fingerprint import HardwareFingerprint
        # Reconstruct same fingerprint (the client stored machine_id in req)
        guard = LicenseGuard(
            eng, client_store,
            fingerprint=HardwareFingerprint.collect(),
        )
        result = guard.startup_check(account_id="ACC-MAIN")
        assert result.claims.tier == LicenseTier.YEARLY.value
        assert guard.has_feature("ai:lstm")
