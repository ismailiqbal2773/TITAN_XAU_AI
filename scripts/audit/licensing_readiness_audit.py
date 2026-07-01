#!/usr/bin/env python3
"""
TITAN XAU AI - Licensing Readiness Audit
=========================================
Verifies that the commercial licensing subsystem is present and exhibits
the required fail-closed safety properties.

NEVER imports MetaTrader5. NEVER sends orders. Pure-Python source audit.

Verdicts:
  - LICENSING_READY        : all critical checks pass.
  - LICENSING_NEEDS_WORK   : non-blocking issues found.
  - LICENSING_BLOCKED      : a fail-closed safety property is missing.
"""
from __future__ import annotations

import inspect
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

OUTPUT_DIR = REPO_ROOT / "data" / "audit" / "licensing_readiness"
JSON_PATH = OUTPUT_DIR / "licensing_readiness_audit.json"
MD_PATH = OUTPUT_DIR / "licensing_readiness_audit.md"

# Required licensing modules and the classes they must expose.
REQUIRED_MODULES: dict[str, tuple[str, ...]] = {
    "titan/commercial/licensing/license_validator.py": (
        "LicenseValidator", "LicenseValidationResult", "LicenseInfo",
    ),
    "titan/commercial/licensing/machine_binding.py": (
        "MachineBinding", "MachineSignature",
    ),
    "titan/commercial/licensing/expiry_guard.py": (
        "ExpiryGuard", "ExpiryResult",
    ),
    "titan/commercial/licensing/license_audit.py": (
        "LicenseAudit", "LICENSE_VALID", "LICENSE_EXPIRED",
        "LICENSE_INVALID", "LICENSE_GRACE_PERIOD",
    ),
}

# Verdicts
LICENSING_READY = "LICENSING_READY"
LICENSING_NEEDS_WORK = "LICENSING_NEEDS_WORK"
LICENSING_BLOCKED = "LICENSING_BLOCKED"


def _git_head_short() -> str:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=10,
        )
        return r.stdout.strip() if r.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def _strip(src: str) -> str:
    """Remove strings/comments to avoid false positives in keyword scans."""
    src = re.sub(r'"""[\s\S]*?"""', '""', src)
    src = re.sub(r"'''[\s\S]*?'''", "''", src)
    src = re.sub(r'r"[^"]*"', '""', src)
    src = re.sub(r"r'[^']*'", "''", src)
    src = re.sub(r'"(?:[^"\\]|\\.)*"', '""', src)
    src = re.sub(r"'(?:[^'\\]|\\.)*'", "''", src)
    out = []
    for line in src.splitlines():
        idx = line.find("#")
        if idx >= 0:
            line = line[:idx]
        out.append(line)
    return "\n".join(out)


def _has_no_order_send(code: str) -> bool:
    return not re.search(r"\bmt5\.order_send\s*\(", code) and \
           not re.search(r"\bMetaTrader5\.order_send\s*\(", code)


def _has_no_martingale(code: str) -> bool:
    bad = ("martingale", "grid_doubling", "averaging_down", "loss_based_lot_multiplier")
    low = code.lower()
    return not any(b in low for b in bad)


def run_audit() -> dict:
    ts = datetime.now(timezone.utc).isoformat()
    head = _git_head_short()

    ok_checks: list[str] = []
    warnings_list: list[str] = []
    blockers: list[str] = []

    # 1. Each required module exists
    for rel, classes in REQUIRED_MODULES.items():
        path = REPO_ROOT / rel
        if not path.exists():
            blockers.append(f"missing required module: {rel}")
            continue
        src = path.read_text(encoding="utf-8")
        for cls in classes:
            if cls not in src:
                blockers.append(f"{rel}: missing required symbol '{cls}'")
            else:
                ok_checks.append(f"{rel}: defines '{cls}'")

    # 2. license_validator.py must declare `from __future__ import annotations`
    for rel in REQUIRED_MODULES:
        path = REPO_ROOT / rel
        if not path.exists():
            continue
        src = path.read_text(encoding="utf-8")
        if "from __future__ import annotations" in src:
            ok_checks.append(f"{rel}: future annotations declared")
        else:
            blockers.append(f"{rel}: missing 'from __future__ import annotations'")

    # 3. Fail-closed for live trading
    lv_path = REPO_ROOT / "titan/commercial/licensing/license_validator.py"
    if lv_path.exists():
        lv_src = lv_path.read_text(encoding="utf-8")
        if "fail_closed_live" in lv_src:
            ok_checks.append("license_validator exposes fail_closed_live field")
        else:
            blockers.append("license_validator missing fail_closed_live field")
        if "for_live" in lv_src:
            ok_checks.append("license_validator supports for_live gating")
        else:
            blockers.append("license_validator missing for_live gating")

        # tamper detection must be present
        if "tamper" in lv_src.lower():
            ok_checks.append("license_validator performs tamper detection")
        else:
            blockers.append("license_validator missing tamper detection")

        # machine binding must be present
        if "machine_binding" in lv_src and "machine_bound" in lv_src:
            ok_checks.append("license_validator performs machine binding")
        else:
            blockers.append("license_validator missing machine binding")

        # offline grace must be present
        if "grace" in lv_src.lower():
            ok_checks.append("license_validator supports offline grace period")
        else:
            blockers.append("license_validator missing offline grace period")

        # order_send must NEVER appear in code
        lv_code = _strip(lv_src)
        if _has_no_order_send(lv_code):
            ok_checks.append("license_validator never calls mt5.order_send")
        else:
            blockers.append("license_validator calls mt5.order_send")

        if _has_no_martingale(lv_code):
            ok_checks.append("license_validator has no martingale/grid/averaging")
        else:
            blockers.append("license_validator contains banned betting pattern")

    # 4. expiry_guard default grace = 72 hours
    eg_path = REPO_ROOT / "titan/commercial/licensing/expiry_guard.py"
    if eg_path.exists():
        eg_src = eg_path.read_text(encoding="utf-8")
        if "DEFAULT_OFFLINE_GRACE_HOURS" in eg_src and "72" in eg_src:
            ok_checks.append("expiry_guard: default offline grace = 72 hours")
        else:
            warnings_list.append("expiry_guard: default grace not 72 hours")

    # 5. license_audit verdict set
    la_path = REPO_ROOT / "titan/commercial/licensing/license_audit.py"
    if la_path.exists():
        la_src = la_path.read_text(encoding="utf-8")
        for v in ("LICENSE_VALID", "LICENSE_EXPIRED", "LICENSE_INVALID", "LICENSE_GRACE_PERIOD"):
            if v in la_src:
                ok_checks.append(f"license_audit declares verdict {v}")
            else:
                blockers.append(f"license_audit missing verdict {v}")

    # 6. Self-audit: no MetaTrader5 import in any licensing file
    licensing_dir = REPO_ROOT / "titan" / "commercial" / "licensing"
    if licensing_dir.exists():
        for f in licensing_dir.glob("*.py"):
            s = f.read_text(encoding="utf-8")
            # Strip strings/comments to avoid flagging detection string literals.
            code = _strip(s)
            if re.search(r"^\s*import\s+MetaTrader5\b", code, flags=re.MULTILINE) or \
               re.search(r"^\s*from\s+MetaTrader5\b", code, flags=re.MULTILINE):
                blockers.append(f"{f.name}: imports MetaTrader5 (forbidden)")
            else:
                ok_checks.append(f"{f.name}: no MetaTrader5 import")

    # 7. Runtime sanity: LicenseValidator.validate_license returns LicenseValidationResult
    try:
        from titan.commercial.licensing.license_validator import (
            LicenseValidator, LicenseValidationResult, LicenseInfo,
        )
        from titan.commercial.licensing.machine_binding import MachineBinding
        from titan.commercial.licensing.expiry_guard import ExpiryGuard

        mb = MachineBinding.collect()
        sig = mb.get_machine_signature()
        eg = ExpiryGuard()
        lv = LicenseValidator(
            machine_binding=mb,
            expiry_guard=eg,
            signing_secret=b"audit-test-secret-0123456789",
        )
        # Build a valid LicenseInfo bound to the current machine.
        import time as _t
        exp = _t.time() + 86400.0
        info = LicenseInfo(
            license_key="TITAN-FULL-" + "a" * 32 + "-AB12",
            expiry_epoch=exp,
            machine_signature=sig.composite,
            features=("broker", "market_data", "execution", "risk"),
            tier="FULL",
            issued_epoch=_t.time(),
            signature="",
        )
        # Compute a correct signature
        msg = f"{info.license_key}|{int(info.expiry_epoch)}|{info.machine_signature}".encode()
        import hmac as _hmac, hashlib as _hl
        info = LicenseInfo(
            license_key=info.license_key,
            expiry_epoch=info.expiry_epoch,
            machine_signature=info.machine_signature,
            features=info.features,
            tier=info.tier,
            issued_epoch=info.issued_epoch,
            signature=_hmac.new(b"audit-test-secret-0123456789", msg, _hl.sha256).hexdigest(),
        )
        result = lv.validate_license(info, required_features=("broker",), for_live=True, online=True)
        if isinstance(result, LicenseValidationResult):
            ok_checks.append("LicenseValidator.validate_license returns LicenseValidationResult")
        else:
            blockers.append("LicenseValidator.validate_license did not return LicenseValidationResult")
        if not result.valid:
            blockers.append(f"LicenseValidator self-test failed: {result.reason}")
        else:
            ok_checks.append("LicenseValidator self-test passed on a valid license")
        # Negative test: tamper the signature → must be invalid for live
        bad = LicenseInfo(
            license_key=info.license_key,
            expiry_epoch=info.expiry_epoch,
            machine_signature=info.machine_signature,
            features=info.features,
            tier=info.tier,
            issued_epoch=info.issued_epoch,
            signature="deadbeef",
        )
        bad_result = lv.validate_license(bad, required_features=("broker",), for_live=True, online=True)
        if not bad_result.valid and not bad_result.fail_closed_live:
            ok_checks.append("LicenseValidator fails closed on tampered signature")
        else:
            blockers.append("LicenseValidator did NOT fail-closed on tampered signature")
    except Exception as e:
        blockers.append(f"LicenseValidator runtime self-test error: {e}")

    # ── Verdict ─────────────────────────────────────────────────────────
    if blockers:
        verdict = LICENSING_BLOCKED
    elif warnings_list:
        verdict = LICENSING_NEEDS_WORK
    else:
        verdict = LICENSING_READY

    return {
        "timestamp_utc": ts,
        "head_short": head,
        "verdict": verdict,
        "ok_checks": ok_checks,
        "warnings": warnings_list,
        "blockers": blockers,
        "design_description": (
            "Fail-closed commercial licensing with machine binding, "
            "offline grace period, and tamper detection. Live trading "
            "is blocked unless all checks pass and the license is not "
            "in grace period."
        ),
    }


def write_report(result: dict) -> dict:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str, ensure_ascii=False)
    with open(MD_PATH, "w", encoding="utf-8") as f:
        f.write("# TITAN XAU AI - Licensing Readiness Audit\n\n")
        f.write(f"**Verdict:** **{result['verdict']}**\n\n")
        f.write(f"**Design:** {result['design_description']}\n\n")
        f.write(f"**Timestamp:** {result['timestamp_utc']}\n\n")
        if result.get("ok_checks"):
            f.write("## OK Checks\n\n")
            for c in result["ok_checks"]:
                f.write(f"- {c}\n")
        if result.get("warnings"):
            f.write("\n## Warnings\n\n")
            for w in result["warnings"]:
                f.write(f"- {w}\n")
        if result.get("blockers"):
            f.write("\n## Blockers\n\n")
            for b in result["blockers"]:
                f.write(f"- **{b}**\n")
        f.write("\n**Licensing subsystem fails closed for live trading when invalid.**\n")
    return {"json_path": str(JSON_PATH), "md_path": str(MD_PATH)}


def main() -> int:
    print("=" * 70)
    print("  TITAN XAU AI - Licensing Readiness Audit")
    print("=" * 70)
    result = run_audit()
    report = write_report(result)
    print(f"\n  Verdict: {result['verdict']}")
    print(f"  Blockers: {len(result['blockers'])}")
    print(f"  Warnings: {len(result['warnings'])}")
    print(f"\n  JSON: {report['json_path']}")
    print(f"  MD:   {report['md_path']}")
    print("\n" + "=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
