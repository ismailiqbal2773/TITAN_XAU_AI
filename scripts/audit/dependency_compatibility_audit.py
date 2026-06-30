#!/usr/bin/env python3
"""
TITAN XAU AI - Dependency Compatibility Audit (Sprint 9.9.3.43)
================================================================
NEVER imports MetaTrader5 in safe path. NEVER sends orders.
"""
from __future__ import annotations
import json, os, platform, subprocess, sys, warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
OUTPUT_DIR = REPO_ROOT / "data" / "audit" / "dependency_compatibility"
JSON_PATH = OUTPUT_DIR / "dependency_compatibility_audit.json"
MD_PATH = OUTPUT_DIR / "dependency_compatibility_audit.md"

CRITICAL_PACKAGES = {
    "xgboost": "xgboost",
    "scikit-learn": "sklearn",
    "pandas": "pandas",
    "numpy": "numpy",
    "pyyaml": "yaml",
}


def _git_head_short() -> str:
    try:
        r = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                           cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=10)
        return r.stdout.strip() if r.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def _get_pkg_version(import_name: str) -> Optional[str]:
    try:
        mod = __import__(import_name)
        return getattr(mod, "__version__", "unknown")
    except ImportError:
        return None
    except Exception:
        return None


def _read_requirements() -> dict:
    """Read requirements.txt and return {package_name: version_spec}."""
    req_path = REPO_ROOT / "requirements.txt"
    if not req_path.exists():
        return {}
    result = {}
    for line in req_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(">=") if ">=" in line else line.split("==") if "==" in line else [line, ""]
        pkg = parts[0].strip()
        ver = parts[1].strip() if len(parts) > 1 else ""
        result[pkg] = ver
    return result


def run_audit() -> dict:
    ts = datetime.now(timezone.utc).isoformat()
    head = _git_head_short()
    py_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    py_major_minor = f"{sys.version_info.major}.{sys.version_info.minor}"

    ok_checks = []
    warnings_list = []
    blockers = []

    # Check Python version
    if sys.version_info >= (3, 13):
        warnings_list.append("PYTHON_313_COMPATIBILITY_WARNING: Python 3.13+ may have compatibility issues with some packages")
    ok_checks.append(f"Python {py_version}")

    # Check critical packages
    installed = {}
    for display_name, import_name in CRITICAL_PACKAGES.items():
        ver = _get_pkg_version(import_name)
        installed[display_name] = ver
        if ver is None:
            blockers.append(f"Missing critical package: {display_name}")
        else:
            ok_checks.append(f"{display_name} {ver} installed")

    # Check MetaTrader5 (optional)
    mt5_ver = _get_pkg_version("MetaTrader5")
    installed["MetaTrader5"] = mt5_ver
    if mt5_ver:
        ok_checks.append(f"MetaTrader5 {mt5_ver} installed (optional)")
    else:
        ok_checks.append("MetaTrader5 not installed (optional, expected in dry-run)")

    # Check requirements.txt
    requirements = _read_requirements()
    if requirements:
        ok_checks.append(f"requirements.txt found with {len(requirements)} packages")
    else:
        warnings_list.append("requirements.txt missing or empty")

    # Detect version drift
    for pkg, req_ver in requirements.items():
        # Map requirements name to import name
        import_map = {"scikit-learn": "sklearn", "pyyaml": "yaml"}
        imp = import_map.get(pkg, pkg)
        actual_ver = installed.get(pkg) or _get_pkg_version(imp)
        if actual_ver and req_ver:
            if not actual_ver.startswith(req_ver.split(".")[0]):
                warnings_list.append(f"DEPENDENCY_VERSION_DRIFT_WARNING: {pkg} installed={actual_ver} vs required={req_ver}")

    # Check XGBoost serialization compatibility
    try:
        import xgboost as xgb
        ok_checks.append(f"XGBoost version: {xgb.__version__}")
    except Exception as e:
        blockers.append(f"XGBoost import failed: {e}")

    # Check sklearn compatibility
    try:
        import sklearn
        ok_checks.append(f"scikit-learn version: {sklearn.__version__}")
    except Exception as e:
        blockers.append(f"scikit-learn import failed: {e}")

    # Environment hash
    env_hash = f"{py_version}-{platform.platform()}-{hash(tuple(sorted(installed.items())))}"

    # Verdict
    if blockers:
        verdict = "DEPENDENCY_BLOCKED"
    elif warnings_list:
        verdict = "DEPENDENCY_READY_WITH_WARNINGS"
    else:
        verdict = "DEPENDENCY_READY"

    return {
        "timestamp_utc": ts,
        "head_short": head,
        "verdict": verdict,
        "python_version": py_version,
        "python_major_minor": py_major_minor,
        "platform": platform.platform(),
        "installed_packages": installed,
        "requirements_txt": requirements,
        "environment_hash": env_hash,
        "ok_checks": ok_checks,
        "warnings": warnings_list,
        "blockers": blockers,
        "reproducible": bool(requirements) and not blockers,
    }


def write_report(result: dict) -> dict:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str, ensure_ascii=False)
    with open(MD_PATH, "w", encoding="utf-8") as f:
        f.write("# TITAN XAU AI - Dependency Compatibility Audit\n\n")
        f.write(f"**Verdict:** **{result['verdict']}**\n\n")
        f.write(f"**Timestamp:** {result['timestamp_utc']}\n\n")
        f.write(f"**Python:** {result['python_version']}\n\n")
        f.write(f"**Platform:** {result['platform']}\n\n")
        f.write("## Installed Packages\n\n")
        f.write("| Package | Version |\n|---|---|\n")
        for k, v in result["installed_packages"].items():
            f.write(f"| {k} | {v or 'NOT INSTALLED'} |\n")
        f.write(f"\n## Environment Hash: `{result['environment_hash']}`\n\n")
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
        f.write(f"\n## Reproducible: {result['reproducible']}\n")
    return {"json_path": str(JSON_PATH), "md_path": str(MD_PATH)}


def main() -> int:
    print("=" * 70)
    print("  TITAN XAU AI - Dependency Compatibility Audit (Sprint 9.9.3.43)")
    print("=" * 70)
    result = run_audit()
    report = write_report(result)
    print(f"\n  Verdict: {result['verdict']}")
    print(f"  Python: {result['python_version']}")
    print(f"  Blockers: {len(result['blockers'])}")
    print(f"  Warnings: {len(result['warnings'])}")
    print(f"\n  JSON: {report['json_path']}")
    print(f"  MD:   {report['md_path']}")
    print("\n" + "=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
