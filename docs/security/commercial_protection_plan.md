# TITAN XAU AI — Commercial Protection Plan

**Sprint 9.9.3.24 — Foundation Document**
**Status:** Stub / Design — no real license server, keys, or secrets implemented yet.

---

## 1. Limitation Statement

No software is 100% crack-proof. The goal of this plan is **layered protection**
that raises the cost and effort of piracy, cracking, and tampering to a level
where it is economically unviable for most attackers, while keeping the
developer/demo workflow frictionless.

Layers are additive: defeating one layer does not bypass all layers.

---

## 2. Operating Modes

| Mode | LicenseGuard | AntiTamperGuard | SecurityGate | Use Case |
|---|---|---|---|---|
| `dev_mode` | Allow | Allow | Allow | Local development, unit tests, CI |
| `demo_internal_mode` | Allow + warning | Warn only | Allow + warning | Internal demo testing, operator training |
| `release_mode` | Fail closed if invalid | Fail closed on tamper | Fail closed | Production release, paid customers |

Mode is determined by:
- Environment variable `TITAN_SECURITY_MODE` (dev/demo_internal/release)
- Default: `dev_mode` when unset

**In dev/demo mode, no security checks block execution.**
**In release mode, ALL checks must pass or execution is blocked.**

---

## 3. Licensing Model

### 3.1 License Tiers

| Tier | Features | Duration |
|---|---|---|
| Trial | 0.01 lot, 1 trade/day, DEMO only | 14 days |
| Paid — Standard | Full strategy, DEMO + funded challenge | 90 days renewable |
| Paid — Pro | Standard + dynamic lot, multi-account | 90 days renewable |
| Internal | Unrestricted, dev/demo only | No expiry |

### 3.2 License Key Format

License keys are NOT hard-coded in the repository. They are:
- Issued by the license server (future implementation)
- Delivered to the customer via secure channel
- Stored locally in `~/.titan/license.key` (never in the repo)
- Validated at startup and periodically

### 3.3 License Status Fields

```python
{
    "license_key_present": bool,      # key file exists
    "license_valid": bool,            # signature + format valid
    "expired": bool,                  # expiry date passed
    "device_bound": bool,             # device fingerprint matches
    "account_bound": bool,            # MT5 login matches license
    "broker_bound": bool,             # MT5 server matches license
    "offline_grace_valid": bool,      # within offline grace period
    "release_mode": bool,             # running in release mode
    "tier": str,                      # trial/paid_standard/paid_pro/internal
    "expiry_date": str | None,        # ISO date
    "days_remaining": int | None,     # days until expiry
}
```

### 3.4 Device Fingerprinting

Device fingerprint is a hash of:
- OS platform + version
- CPU architecture
- Machine GUID (Windows) / /etc/machine-id (Linux)
- MAC address of primary network interface

Fingerprint is embedded in the license key at activation.
At runtime, the guard recomputes the fingerprint and compares.

### 3.5 Account Binding

License can be bound to specific MT5 login(s).
At runtime, the guard reads `mt5.account_info().login` and compares.
If the login doesn't match, execution is blocked in release mode.

### 3.6 Broker Binding

License can be bound to specific MT5 server(s).
At runtime, the guard reads `mt5.account_info().server` and compares.
If the server doesn't match, execution is blocked in release mode.

### 3.7 Expiry & Renewal

- License has an expiry date embedded in the key.
- 7 days before expiry, a renewal reminder is shown.
- After expiry, the license is invalid.
- Renewal is done via the license server (future).
- Offline grace period: 72 hours after expiry, the license still works
  to allow time for renewal. After 72 hours, execution is blocked.

### 3.8 Revocation / Ban

- The license server can revoke a license (e.g., chargeback, abuse).
- Revocation list is checked at activation and periodically.
- In offline mode, the revocation list is cached from the last successful
  server check. If the cache is older than 7 days, execution is blocked.

---

## 4. License Server Design (Future)

### 4.1 Architecture

```
Customer Client → HTTPS → License Server → Database
                   ↓
                 Issue / Validate / Revoke / Renew
```

### 4.2 Secure Activation Flow

1. Customer installs TITAN and runs `titan --activate`
2. Client sends device fingerprint + purchase code to license server
3. Server validates purchase code, issues signed license key
4. Client stores license key in `~/.titan/license.key`
5. Client validates key at every startup

### 4.3 Server Endpoints (Future)

- `POST /activate` — issue license from purchase code
- `POST /validate` — validate existing license
- `POST /renew` — renew expiring license
- `POST /revoke` — revoke license (admin only)
- `GET /revocation-list` — download cached revocation list

---

## 5. Anti-Tamper Protection

### 5.1 Integrity Manifest

A manifest file `titan.integrity` contains SHA-256 hashes of:
- All Python source files in `titan/`
- All config files in `config/`
- All model artifacts in `titan/data/models/`
- The executable (for PyInstaller builds)

At startup, AntiTamperGuard recomputes hashes and compares.
Any mismatch = tamper detected = fail closed in release mode.

### 5.2 Config Hash

`config/runtime.yaml` hash is checked at startup.
If the config has been modified outside the official update path,
execution is blocked in release mode.

### 5.3 Model Artifact Hash

Model files (`xgboost_v1.pkl`, `meta_label_v2_context.pkl`) are hashed.
If a model file has been replaced or modified, execution is blocked.

### 5.4 Executable Signature

For PyInstaller builds, the executable is code-signed.
At startup, the signature is verified.
If the signature is invalid, execution is blocked.

### 5.5 Tamper Event

When tamper is detected:
```python
{
    "tamper_detected": True,
    "tampered_files": ["titan/production/trade_loop.py", "config/runtime.yaml"],
    "expected_hash": "abc123...",
    "actual_hash": "def456...",
    "timestamp_utc": "2026-06-29T...",
    "severity": "CRITICAL",
}
```

---

## 6. Code Signing Plan

### 6.1 Release Build

- PyInstaller builds the executable
- Executable is signed with code-signing certificate
- Signature is verified at startup by AntiTamperGuard
- Integrity manifest is generated post-build and signed

### 6.2 Certificate Management

- Code-signing certificate stored in HSM or secure CI/CD secret store
- NEVER committed to the repository
- Rotated annually

---

## 7. Encrypted Artifacts

### 7.1 Config Artifacts

- `config/runtime.yaml` can be encrypted at rest
- Decryption key derived from license key + device fingerprint
- In dev mode, config is plaintext

### 7.2 Model Artifacts

- Model `.pkl` files can be encrypted
- Decryption key derived from license key
- In dev mode, models are plaintext

---

## 8. Release Build Obfuscation

### 8.1 Python Obfuscation

- Use PyArmor or similar for Python source obfuscation
- Critical modules (license_guard, anti_tamper_guard, trade_loop) are obfuscated
- String literals containing security checks are encrypted

### 8.2 Binary Obfuscation

- PyInstaller with `--onefile` for single-binary distribution
- Binary is stripped of debug symbols
- UPX packing (optional, may trigger AV false positives)

---

## 9. Anti-Copy Strategy

### 9.1 Device Binding

- License is bound to a device fingerprint
- Copying TITAN to another machine invalidates the license
- Re-activation required on new hardware

### 9.2 Account Binding

- License is bound to MT5 login(s)
- Sharing the license with another MT5 account is blocked

### 9.3 Broker Binding

- License is bound to specific broker server(s)
- Using the license on an unauthorized broker is blocked

---

## 10. Anti-Cracking Layers

### Layer 1: License Validation
- License key is cryptographically signed (RSA-2048)
- Signature is verified at startup
- Key cannot be forged without the private key (held on license server)

### Layer 2: Device Fingerprint
- License is bound to hardware
- Cracker must re-engineer the fingerprint check

### Layer 3: Integrity Manifest
- All source files are hashed
- Modifying any file (including license_guard.py) triggers tamper detection

### Layer 4: Code Obfuscation
- Source code is obfuscated in release builds
- Reverse-engineering the security logic is time-consuming

### Layer 5: Periodic Server Check
- License is periodically validated against the server
- Cracked licenses that bypass local validation are caught by the server
- Offline grace period limits the window for cracked operation

### Layer 6: Encrypted Artifacts
- Config and model files are encrypted
- Without the license key, artifacts cannot be decrypted

### Layer 7: Code Signing
- Executable is signed
- Modified executables fail signature verification

---

## 11. Secrets Management

### 11.1 What Goes Where

| Secret | Storage | Committed to Repo? |
|---|---|---|
| License signing private key | License server HSM | NO |
| Code-signing certificate | CI/CD secret store | NO |
| License keys | `~/.titan/license.key` (customer) | NO |
| API keys / tokens | Environment variables | NO |
| MT5 credentials | MT5 terminal (not TITAN) | NO |

### 11.2 `.gitignore` Enforcement

The following patterns are in `.gitignore`:
- `*.key`, `*.secret`, `.env`, `.env.*`
- `data/audit/demo_micro/raw_mt5_working_profile.json` (contains account info)

---

## 12. Customer Mode vs Internal Developer Mode

| Aspect | Customer Mode (release) | Internal Mode (dev/demo) |
|---|---|---|
| Security gate | Enforced | Non-blocking |
| License required | Yes | No |
| Tamper check | Enforced | Warning only |
| Obfuscation | Applied | Not applied |
| Encrypted artifacts | Yes | No |
| Server check | Periodic | Skipped |

---

## 13. Secure Update Path

1. Update package is signed with code-signing certificate
2. Client downloads update + signature
3. Client verifies signature before applying
4. After update, integrity manifest is regenerated and verified
5. License is re-validated after update
6. If any step fails, update is rolled back

---

## 14. Implementation Status

| Component | Status | Sprint |
|---|---|---|
| Commercial protection plan | **This document** | 9.9.3.24 |
| LicenseGuard (stub) | **Implemented** | 9.9.3.24 |
| AntiTamperGuard (stub) | **Implemented** | 9.9.3.24 |
| SecurityGate (stub) | **Implemented** | 9.9.3.24 |
| License server | Future | — |
| Code signing | Future | — |
| Obfuscation | Future | — |
| Encrypted artifacts | Future | — |
| Integrity manifest | Placeholder | 9.9.3.24 |

---

## 15. Security Gate Hook (Non-Blocking Placeholder)

The security gate is currently wired as a **non-blocking placeholder** in the
demo micro execution path. A TODO comment marks where future release/live
mode will enforce it:

```python
# TODO Sprint 9.9.4+: Enforce SecurityGate in release/live mode
# security_gate = SecurityGate(mode="release")
# if not security_gate.allow():
#     raise SecurityGateError("Security gate check failed")
```

In dev/demo mode, the security gate is never called — existing tests and
demo workflows continue to pass without any security enforcement.
