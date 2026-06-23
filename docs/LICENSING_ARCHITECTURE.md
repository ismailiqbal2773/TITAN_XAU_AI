# TITAN XAU AI — Licensing Architecture (Future Design)

> **Status:** DOCUMENTATION ONLY — No licensing implemented.
> **Sprint:** 7.5
> **Date:** 2026-06-23

This document describes the **future** licensing architecture for TITAN XAU AI.
**No licensing is currently implemented.** No enforcement, no restrictions, no activation checks exist in the codebase.

---

## 1. Design Goals

| Goal | Description |
|------|-------------|
| Machine binding | License tied to specific hardware fingerprint |
| Online activation | License activated via online API |
| Offline activation | License activated via offline code exchange |
| Subscription model | Monthly / Quarterly / Yearly tiers |
| Institute license | Multi-seat license for institutions |
| Grace period | 7-day grace after expiry |
| Anti-tamper | License store encrypted + integrity-checked |

---

## 2. License Tiers

| Tier | Duration | Max Accounts | Price (Future) | Target User |
|------|----------|--------------|----------------|-------------|
| TRIAL | 7 days | 1 demo | Free | New users testing |
| MONTHLY | 30 days | 1 demo + 1 live | $49/mo | Individual traders |
| QUARTERLY | 90 days | 1 demo + 1 live | $129/qtr | Active traders |
| YEARLY | 365 days | 1 demo + 1 live | $399/yr | Committed traders |
| INSTITUTE | 365 days | 10 accounts | $2,999/yr | Prop firms, funds |

---

## 3. Machine Binding

### Hardware Fingerprint

License is bound to a 6-component hardware fingerprint:

```python
fingerprint = {
    "cpu_id": get_cpu_id(),           # CPU serial number
    "motherboard": get_mb_serial(),   # Motherboard serial
    "disk_id": get_disk_serial(),     # Primary disk serial
    "mac_address": get_mac(),         # Network adapter MAC
    "hostname": socket.gethostname(), # Computer name
    "os_uuid": get_os_uuid(),         # OS installation UUID
}
```

### Fingerprint Hash

```
machine_id = SHA256(cpu_id + motherboard + disk_id + mac + hostname + os_uuid)
```

License is valid only if `machine_id` matches the one stored in the license file.

### Hardware Change Tolerance

- Allow 1 component to change (e.g., MAC address change after network adapter swap)
- If 2+ components change → license invalidated → re-activation required

---

## 4. Online Activation Flow

```
User enters license key
        ↓
TITAN sends to activation server:
  - license_key
  - machine_id (SHA256)
  - timestamp
        ↓
Server validates:
  - Key exists in database?
  - Key not expired?
  - Key not already activated on different machine?
  - Key not blocked?
        ↓
Server returns:
  - JWT license token (signed)
  - Expiry date
  - Tier
  - Max accounts
        ↓
TITAN stores JWT in encrypted local store
        ↓
TITAN starts (license valid)
```

### JWT Token Structure

```json
{
  "license_key": "TITAN-XXXX-XXXX-XXXX",
  "machine_id": "abc123...",
  "tier": "MONTHLY",
  "issued_at": "2026-06-23T00:00:00Z",
  "expires_at": "2026-07-23T00:00:00Z",
  "max_accounts": 1,
  "features": ["dry_run", "live_trading", "dashboard"]
}
```

### JWT Signing

- Algorithm: HS256
- Secret: Server-side secret (rotated quarterly)
- Token valid for 7 days, refreshed via heartbeat

---

## 5. Offline Activation Flow

For users without internet access:

```
User enters license key
        ↓
TITAN displays:
  - license_key
  - machine_id (SHA256)
  - "Call/WhatsApp support with these values"
        ↓
Support generates offline activation code:
  - Code = Base32(Sign(license_key + machine_id + expiry))
        ↓
User enters offline code in TITAN
        ↓
TITAN verifies code signature
        ↓
TITAN stores license locally (valid until expiry)
```

### Offline Code Format

```
TITAN-OFFLINE-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX
```

- 32 characters Base32 encoded
- Contains: license_key hash + machine_id hash + expiry + signature
- Valid for the duration specified at generation time

---

## 6. Subscription Model

### Billing Cycle

| Tier | Billing | Auto-Renewal | Grace Period |
|------|---------|--------------|--------------|
| TRIAL | One-time | No | 0 days |
| MONTHLY | Monthly | Yes (cancel anytime) | 7 days |
| QUARTERLY | Quarterly | Yes (cancel anytime) | 7 days |
| YEARLY | Yearly | Yes (cancel anytime) | 14 days |
| INSTITUTE | Yearly | Yes | 30 days |

### Expiry Handling

1. **7 days before expiry:** TITAN shows warning in dashboard
2. **On expiry:** TITAN enters grace period
3. **During grace:** TITAN continues to function (with warning)
4. **After grace:** TITAN refuses to start (blocks all trading)

### Renewal

- Online: automatic via payment processor (Stripe/PayPal)
- Offline: user purchases renewal code, enters in TITAN

---

## 7. Institute License

### Multi-Seat Management

| Feature | Description |
|---------|-------------|
| Max accounts | 10 MT5 accounts per institute license |
| Central management | Web dashboard for license admin |
| Sub-licenses | Admin can issue sub-licenses to traders |
| Usage tracking | Per-account usage statistics |
| Concurrent limit | Up to 10 concurrent TITAN instances |

### Admin Dashboard (Future)

```
Institute Admin Dashboard
├── License overview (seats used / available)
├── Trader management (add / remove / block)
├── Usage statistics (per-trader PnL, signals)
├── Billing history
└── Support tickets
```

---

## 8. License Store (Local)

### Storage Location

```
Windows: C:\Users\<user>\AppData\Roaming\TITAN\license.store
Linux:   ~/.titan/license.store
```

### Store Format

Encrypted SQLite database with tables:

```sql
CREATE TABLE licenses (
    license_key TEXT PRIMARY KEY,
    jwt_token TEXT NOT NULL,
    machine_id TEXT NOT NULL,
    tier TEXT NOT NULL,
    issued_at TIMESTAMP NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    activated_at TIMESTAMP NOT NULL,
    last_heartbeat TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE
);

CREATE TABLE activation_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TIMESTAMP NOT NULL,
    event TEXT NOT NULL,  -- activated | renewed | expired | blocked
    license_key TEXT NOT NULL,
    details TEXT
);
```

### Encryption

- AES-256-GCM
- Key derived from machine_id + app_secret
- Integrity verified via HMAC-SHA256

---

## 9. Anti-Tamper Measures

| Measure | Description |
|---------|-------------|
| Encrypted store | License file encrypted, not plaintext |
| Integrity check | HMAC verified on every read |
| Heartbeat | License re-verified every 60 seconds |
| Clock skew detection | Reject if system clock changed >5 min since last heartbeat |
| Reverse engineering protection | PyInstaller exe + code obfuscation |
| Debug detection | Refuse to run if debugger detected |

---

## 10. Existing Code Foundation

TITAN already has licensing infrastructure in `titan/licensing/` (Sprint 1-4):

| File | Purpose | Status |
|------|---------|--------|
| `fingerprint.py` | 6-component hardware fingerprint | ✓ Implemented |
| `jwt_license.py` | HS256 JWT license engine | ✓ Implemented |
| `store.py` | SQLite license store (encrypted) | ✓ Implemented |
| `activation.py` | Online + offline activation | ✓ Implemented |
| `guard.py` | Runtime enforcement + heartbeat | ✓ Implemented |

**These modules exist but are NOT enforced.** They are tested (47 tests pass) but the launcher does not check licenses before starting.

### Future Enforcement (Not Implemented)

To enable enforcement, add to `titan/runtime/launcher.py`:

```python
# BEFORE starting runtime:
from titan.licensing.guard import LicenseGuard
guard = LicenseGuard(...)
if not guard.startup_check():
    raise LauncherError("License invalid or expired")
```

---

## 11. Implementation Roadmap (Future)

| Phase | Duration | Deliverable |
|-------|----------|-------------|
| Phase 1 | 2 weeks | Activation server (REST API) |
| Phase 2 | 1 week | License admin dashboard |
| Phase 3 | 1 week | Payment processor integration (Stripe) |
| Phase 4 | 1 week | Offline activation code generator |
| Phase 5 | 1 week | Institute multi-seat management |
| Phase 6 | 1 week | Anti-tamper hardening |
| **Total** | **7 weeks** | **Full licensing system** |

---

## 12. Current Status

| Component | Status |
|-----------|--------|
| Hardware fingerprint | ✓ Code exists, not enforced |
| JWT license engine | ✓ Code exists, not enforced |
| License store | ✓ Code exists, not enforced |
| Activation (online + offline) | ✓ Code exists, not enforced |
| License guard (heartbeat) | ✓ Code exists, not enforced |
| Activation server | ✗ Not built |
| Payment processor | ✗ Not built |
| Admin dashboard | ✗ Not built |
| Institute management | ✗ Not built |
| Enforcement in launcher | ✗ Not enabled |

**TITAN currently runs without any license check.** All features are available to all users. Licensing enforcement will be added in a future sprint after the activation server is built.

---

*This document is for architectural planning only. No licensing is enforced.*
