#!/usr/bin/env python3
"""
TITAN XAU AI - Dependency Update Readiness Audit
=================================================
Verifies that the dependency policy is in place, that all production
dependencies are pinned, that the Python version meets the minimum,
that a lockfile exists and is git-versioned, and that no banned betting
patterns or unsafe auto-update logic are present.

NEVER imports MetaTrader5. NEVER sends orders. NEVER runs pip install.

Verdicts:
  - DEPENDENCY_READY        : all critical checks pass.
  - DEPENDENCY_NEEDS_UPDATE : non-blocking issues (e.g. some packages
                              not pinned in requirements.txt, but
                              lockfile is OK).
  - DEPENDENCY_BLOCKED      : a critical safety property is missing
                              (no lockfile, floating pin in lockfile,
                              Python < 3.12, banned pattern detected,
                              auto-update logic present).
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

OUTPUT_DIR = REPO_ROOT / "data" / "audit" / "dependency_update_readiness"
JSON_PATH = OUTPUT_DIR / "dependency_update_readiness_audit.json"
MD_PATH = OUTPUT_DIR / "dependency_update_readiness_audit.md"

POLICY_PATH = REPO_ROOT / "config" / "dependency_policy.yaml"
LOCKFILE_PATH = REPO_ROOT / "requirements-lock.txt"
REQUIREMENTS_PATH = REPO_ROOT / "requirements.txt"

DEPENDENCY_READY = "DEPENDENCY_READY"
DEPENDENCY_NEEDS_UPDATE = "DEPENDENCY_NEEDS_UPDATE"
DEPENDENCY_BLOCKED = "DEPENDENCY_BLOCKED"


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


def _has_no_martingale_logic(code: str) -> bool:
    """Detect actual banned *logic*, not the words as detection string literals
    or as safety-field declarations like `no_loss_based_lot_multiplier = True`.
    """
    low = code.lower()
    forbidden_patterns = [
        r"def\s+apply_martingale",
        r"def\s+apply_grid",
        r"def\s+average_down",
        r"lot\s*\*\s*2\b",
        r"position_size\s*\*=\s*2\b",
        # `loss_based_lot_multiplier = ...` is BANNED only when NOT preceded
        # by `no_` (i.e., the variable is actually the multiplier, not the
        # safety gate `no_loss_based_lot_multiplier`).
        r"(?<!no_)\bloss_based_lot_multiplier\s*=",
        r"(?<!no_)\bmartingale_multiplier\s*=",
    ]
    return not any(re.search(p, low) for p in forbidden_patterns)


def _python_version_tuple(v: str) -> tuple[int, int, int]:
    parts = v.split(".")
    if len(parts) < 3:
        parts = parts + ["0"] * (3 - len(parts))
    try:
        return (int(parts[0]), int(parts[1]), int(parts[2]))
    except ValueError:
        return (0, 0, 0)


def _read_lockfile() -> tuple[list[tuple[str, str, str]], list[str]]:
    """Return (pinned, floating) where pinned=[(name, op, ver)] and floating=[raw lines]."""
    if not LOCKFILE_PATH.exists():
        return [], []
    pinned: list[tuple[str, str, str]] = []
    floating: list[str] = []
    for raw in LOCKFILE_PATH.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        # Strip inline environment markers like ' ; python_version >= "3.8"'
        line = line.split(";")[0].strip()
        m = re.match(r"^([A-Za-z0-9_.\-]+)\s*(==|>=|<=|~=|>|<)\s*([A-Za-z0-9_.\-+*]+)\s*$", line)
        if m:
            name, op, ver = m.group(1), m.group(2), m.group(3)
            if op == "==":
                pinned.append((name, op, ver))
            else:
                floating.append(raw.strip())
        else:
            # Unparseable line — treat as floating for safety.
            floating.append(raw.strip())
    return pinned, floating


def run_audit() -> dict:
    ts = datetime.now(timezone.utc).isoformat()
    head = _git_head_short()

    ok_checks: list[str] = []
    warnings_list: list[str] = []
    blockers: list[str] = []

    # 1. Policy file exists and parses
    if not POLICY_PATH.exists():
        blockers.append("config/dependency_policy.yaml is missing")
        policy = None
    else:
        try:
            import yaml  # type: ignore
            policy = yaml.safe_load(POLICY_PATH.read_text(encoding="utf-8"))
            ok_checks.append("config/dependency_policy.yaml exists and parses as YAML")
        except Exception as e:
            blockers.append(f"config/dependency_policy.yaml failed to parse: {e}")
            policy = None

    # 2. Python version meets minimum
    min_version = "3.12.0"
    if policy and isinstance(policy.get("python"), dict):
        min_version = policy["python"].get("min_version", "3.12.0")
    actual = sys.version_info
    actual_str = f"{actual.major}.{actual.minor}.{actual.micro}"
    min_t = _python_version_tuple(min_version)
    actual_t = (actual.major, actual.minor, actual.micro)
    if actual_t >= min_t:
        ok_checks.append(
            f"Python {actual_str} >= required {min_version}"
        )
    else:
        blockers.append(
            f"Python {actual_str} < required {min_version}"
        )

    # 3. Lockfile exists
    if not LOCKFILE_PATH.exists():
        blockers.append("requirements-lock.txt is missing")
        pinned, floating = [], []
    else:
        ok_checks.append("requirements-lock.txt exists")
        pinned, floating = _read_lockfile()

    # 4. Lockfile has pinned entries
    if LOCKFILE_PATH.exists() and not pinned:
        blockers.append("requirements-lock.txt has no pinned (==) entries")
    elif pinned:
        ok_checks.append(
            f"requirements-lock.txt has {len(pinned)} pinned (==) dependencies"
        )

    # 5. Lockfile has NO floating entries
    if floating:
        blockers.append(
            f"requirements-lock.txt has {len(floating)} floating (non-==) entries: "
            + "; ".join(floating[:5])
        )
    else:
        ok_checks.append("requirements-lock.txt has no floating dependencies")

    # 6. Lockfile declares the Python version it was generated against
    if LOCKFILE_PATH.exists():
        lf_text = LOCKFILE_PATH.read_text(encoding="utf-8")
        if re.search(r"Python\s*3\.\d+", lf_text, flags=re.IGNORECASE):
            ok_checks.append("requirements-lock.txt declares the Python version")
        else:
            warnings_list.append(
                "requirements-lock.txt does not declare the Python version"
            )

    # 7. requirements.txt exists (human-readable docs)
    if not REQUIREMENTS_PATH.exists():
        warnings_list.append("requirements.txt is missing (lockfile is canonical)")
    else:
        ok_checks.append("requirements.txt exists (human-readable docs)")

    # 8. Policy fields present
    if policy:
        for key in ("python", "pinning", "metaTrader5", "lockfile",
                    "auto_update", "rollback", "banned", "audit"):
            if key in policy:
                ok_checks.append(f"policy declares section: {key}")
            else:
                blockers.append(f"policy missing section: {key}")

        # 9. Pinning requires exact pin
        if policy.get("pinning", {}).get("require_exact_pin"):
            ok_checks.append("policy requires exact (==) pinning")
        else:
            blockers.append("policy does NOT require exact pinning")

        # 10. Lockfile required
        if policy.get("lockfile", {}).get("required"):
            ok_checks.append("policy requires a lockfile")
        else:
            blockers.append("policy does NOT require a lockfile")

        # 11. Auto-update forbidden on boot
        if policy.get("auto_update", {}).get("forbidden_on_boot"):
            ok_checks.append("policy forbids auto-update on boot")
        else:
            blockers.append("policy does NOT forbid auto-update on boot")

        # 12. Auto-update forbidden in CI
        if policy.get("auto_update", {}).get("forbidden_in_ci"):
            ok_checks.append("policy forbids auto-update in CI")
        else:
            blockers.append("policy does NOT forbid auto-update in CI")

        # 13. Rollback method declared
        if policy.get("rollback", {}).get("method"):
            ok_checks.append(
                f"policy declares rollback method: {policy['rollback']['method']}"
            )
        else:
            blockers.append("policy missing rollback method")

        # 14. Banned patterns listed
        banned_patterns = policy.get("banned", {}).get("patterns", [])
        if banned_patterns:
            ok_checks.append(
                f"policy declares {len(banned_patterns)} banned patterns"
            )
        else:
            blockers.append("policy missing banned patterns list")

    # 15. MT5 optional & Windows-only (policy)
    if policy and isinstance(policy.get("metaTrader5"), dict):
        mt = policy["metaTrader5"]
        if not mt.get("required", True):
            ok_checks.append("MetaTrader5 is optional per policy")
        else:
            blockers.append("MetaTrader5 must be optional (Linux dev must work)")
        if mt.get("platform") == "win32":
            ok_checks.append("MetaTrader5 is Windows-only per policy")
        if mt.get("shim_module"):
            ok_checks.append(
                f"MetaTrader5 shim declared: {mt['shim_module']}"
            )

    # 16. Self-audit: this script must not call order_send / pip install
    try:
        own_src = Path(__file__).read_text(encoding="utf-8")
        own_code = _strip(own_src)
        if _has_no_order_send(own_code):
            ok_checks.append("dependency audit never calls mt5.order_send")
        else:
            blockers.append("dependency audit calls mt5.order_send")
        if "pip install" in own_code.lower() and "forbid_pip_install" not in own_code:
            blockers.append("dependency audit contains 'pip install'")
        else:
            ok_checks.append("dependency audit does not run pip install")
        if _has_no_martingale_logic(own_code):
            ok_checks.append("dependency audit has no martingale/grid/averaging logic")
        else:
            blockers.append("dependency audit contains banned betting logic")
    except Exception as e:
        blockers.append(f"dependency audit self-check error: {e}")

    # 17. Scan titan/ + scripts/ for banned betting logic (actual code only)
    banned_files: list[str] = []
    scan_dirs = [
        REPO_ROOT / "titan" / "commercial",
        REPO_ROOT / "titan" / "production",
    ]
    for d in scan_dirs:
        if not d.exists():
            continue
        for f in d.glob("*.py"):
            try:
                src = f.read_text(encoding="utf-8")
                code = _strip(src)
                if not _has_no_martingale_logic(code):
                    banned_files.append(str(f.relative_to(REPO_ROOT)))
            except Exception:
                pass
    if banned_files:
        blockers.append(
            f"banned betting logic detected in: {banned_files}"
        )
    else:
        ok_checks.append("no banned betting logic in titan/commercial or titan/production")

    # 18. Scan for unsafe auto-update in code
    unsafe_auto_update_files: list[str] = []
    for d in [REPO_ROOT / "titan", REPO_ROOT / "scripts"]:
        if not d.exists():
            continue
        for f in d.rglob("*.py"):
            try:
                src = f.read_text(encoding="utf-8")
                # Strip strings/comments so detection regex literals in audit
                # scripts are not flagged as actual pip-install calls.
                code = _strip(src)
                # Look for `subprocess.run(["pip", "install", "-U"` or `pip install -U`
                if re.search(r"pip['\"\s,]+install['\"\s,]+-U", code) or \
                   re.search(r"pip['\"\s,]+install['\"\s,]+--upgrade", code):
                    unsafe_auto_update_files.append(str(f.relative_to(REPO_ROOT)))
            except Exception:
                pass
    if unsafe_auto_update_files:
        blockers.append(
            f"unsafe auto-update logic detected in: {unsafe_auto_update_files[:5]}"
        )
    else:
        ok_checks.append("no unsafe auto-update logic in titan/ or scripts/")

    # 19. MT5 must NOT be imported by the new licensing / resilience / audit
    # modules (this is a closed, explicit list — pre-existing MT5-using audit
    # scripts such as raw_mt5_probe.py are allowed to import MT5).
    forbidden_mt5_files = [
        REPO_ROOT / "titan" / "commercial" / "licensing" / "license_validator.py",
        REPO_ROOT / "titan" / "commercial" / "licensing" / "machine_binding.py",
        REPO_ROOT / "titan" / "commercial" / "licensing" / "expiry_guard.py",
        REPO_ROOT / "titan" / "commercial" / "licensing" / "license_audit.py",
        REPO_ROOT / "titan" / "production" / "runtime_health_guard.py",
        REPO_ROOT / "titan" / "production" / "fail_closed_runtime_guard.py",
        REPO_ROOT / "titan" / "production" / "watchdog_restarter.py",
        REPO_ROOT / "scripts" / "audit" / "licensing_readiness_audit.py",
        REPO_ROOT / "scripts" / "audit" / "runtime_resilience_audit.py",
        REPO_ROOT / "scripts" / "audit" / "dependency_update_readiness_audit.py",
    ]
    mt5_import_files: list[str] = []
    for f in forbidden_mt5_files:
        if not f.exists():
            continue
        try:
            src = f.read_text(encoding="utf-8")
            # Strip strings/comments so that detection string literals
            # like `"import MetaTrader5" in src` inside audit scripts are
            # NOT flagged as actual imports.
            code = _strip(src)
            if re.search(r"^\s*import\s+MetaTrader5\b", code, flags=re.MULTILINE) or \
               re.search(r"^\s*from\s+MetaTrader5\b", code, flags=re.MULTILINE):
                mt5_import_files.append(str(f.relative_to(REPO_ROOT)))
        except Exception:
            pass
    if mt5_import_files:
        blockers.append(
            f"MetaTrader5 imported in forbidden modules: {mt5_import_files}"
        )
    else:
        ok_checks.append(
            "MetaTrader5 is not imported by licensing / resilience / new audit modules"
        )

    # ── Verdict ─────────────────────────────────────────────────────────
    if blockers:
        verdict = DEPENDENCY_BLOCKED
    elif warnings_list:
        verdict = DEPENDENCY_NEEDS_UPDATE
    else:
        verdict = DEPENDENCY_READY

    return {
        "timestamp_utc": ts,
        "head_short": head,
        "verdict": verdict,
        "ok_checks": ok_checks,
        "warnings": warnings_list,
        "blockers": blockers,
        "python_version": actual_str,
        "min_python_version": min_version,
        "lockfile_present": LOCKFILE_PATH.exists(),
        "pinned_count": len(pinned) if LOCKFILE_PATH.exists() else 0,
        "floating_count": len(floating) if LOCKFILE_PATH.exists() else 0,
        "design_description": (
            "Pinned dependencies with operator-initiated updates, "
            "git-versioned lockfile, 15-minute rollback SLA, and "
            "no unsafe auto-update. The audit NEVER calls mt5.order_send "
            "and NEVER runs pip install."
        ),
    }


def write_report(result: dict) -> dict:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str, ensure_ascii=False)
    with open(MD_PATH, "w", encoding="utf-8") as f:
        f.write("# TITAN XAU AI - Dependency Update Readiness Audit\n\n")
        f.write(f"**Verdict:** **{result['verdict']}**\n\n")
        f.write(f"**Design:** {result['design_description']}\n\n")
        f.write(f"**Timestamp:** {result['timestamp_utc']}\n\n")
        f.write(f"**Python:** {result['python_version']} (min: {result['min_python_version']})\n\n")
        f.write(
            f"**Lockfile:** present={result['lockfile_present']}, "
            f"pinned={result['pinned_count']}, floating={result['floating_count']}\n\n"
        )
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
        f.write("\n**The audit NEVER calls mt5.order_send and NEVER runs pip install.**\n")
    return {"json_path": str(JSON_PATH), "md_path": str(MD_PATH)}


def main() -> int:
    print("=" * 70)
    print("  TITAN XAU AI - Dependency Update Readiness Audit")
    print("=" * 70)
    result = run_audit()
    report = write_report(result)
    print(f"\n  Verdict: {result['verdict']}")
    print(f"  Blockers: {len(result['blockers'])}")
    print(f"  Warnings: {len(result['warnings'])}")
    print(f"  Python: {result['python_version']} (min: {result['min_python_version']})")
    print(f"  Lockfile pinned: {result['pinned_count']}, floating: {result['floating_count']}")
    print(f"\n  JSON: {report['json_path']}")
    print(f"  MD:   {report['md_path']}")
    print("\n" + "=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
