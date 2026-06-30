#!/usr/bin/env python3
"""
TITAN XAU AI - Freeze Current Environment (Sprint 9.9.3.43.1)
==============================================================
Generates environment lock files. NEVER pip installs. NEVER upgrades.
"""
from __future__ import annotations
import hashlib, json, os, platform, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
OUTPUT_DIR = REPO_ROOT / "config" / "environment"

CRITICAL_IMPORTS = ["xgboost", "sklearn", "pandas", "numpy", "yaml", "MetaTrader5", "joblib"]


def _git_head_short() -> str:
    try:
        r = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                           cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=10)
        return r.stdout.strip() if r.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def _pkg_version(imp: str) -> str | None:
    try:
        mod = __import__(imp)
        return getattr(mod, "__version__", "unknown")
    except ImportError:
        return None
    except Exception:
        return None


def _file_hash(path: Path) -> str:
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return ""


def freeze() -> dict:
    ts = datetime.now(timezone.utc).isoformat()
    head = _git_head_short()
    py_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    py_major_minor = f"{sys.version_info.major}.{sys.version_info.minor}"

    packages = {}
    for imp in CRITICAL_IMPORTS:
        packages[imp] = _pkg_version(imp)

    # Model file hashes
    models_dir = REPO_ROOT / "titan" / "data" / "models"
    model_hashes = {}
    if models_dir.exists():
        for f in sorted(models_dir.iterdir()):
            if f.is_file():
                model_hashes[f.name] = {
                    "size_bytes": f.stat().st_size,
                    "sha256": _file_hash(f),
                }

    # pip freeze
    pip_freeze = []
    try:
        r = subprocess.run([sys.executable, "-m", "pip", "freeze"],
                           capture_output=True, text=True, timeout=30)
        if r.returncode == 0:
            pip_freeze = r.stdout.strip().splitlines()
    except Exception:
        pass

    signature = {
        "timestamp_utc": ts,
        "git_commit": head,
        "python_version": py_version,
        "python_major_minor": py_major_minor,
        "platform": platform.platform(),
        "architecture": platform.machine(),
        "critical_packages": packages,
        "model_files": model_hashes,
        "pip_freeze": pip_freeze,
        "warning": (
            "This is an OBSERVED lock, not auto-updated requirements. "
            "Do NOT auto-install or auto-upgrade based on this file. "
            "Do NOT overwrite requirements.txt automatically."
        ),
    }
    return signature


def write_report(sig: dict) -> dict:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    lock_path = OUTPUT_DIR / "requirements_observed_lock.txt"
    sig_json = OUTPUT_DIR / "environment_signature.json"
    sig_md = OUTPUT_DIR / "environment_signature.md"

    # Write lock file
    with open(lock_path, "w", encoding="utf-8") as f:
        f.write(f"# TITAN XAU AI - Observed Environment Lock\n")
        f.write(f"# Generated: {sig['timestamp_utc']}\n")
        f.write(f"# Git: {sig['git_commit']}\n")
        f.write(f"# Python: {sig['python_version']}\n")
        f.write(f"# Platform: {sig['platform']}\n\n")
        for k, v in sorted(sig["critical_packages"].items()):
            if v:
                f.write(f"{k}=={v}\n")
        f.write("\n# Full pip freeze:\n")
        for line in sig["pip_freeze"]:
            f.write(f"# {line}\n")

    # Write JSON signature
    with open(sig_json, "w", encoding="utf-8") as f:
        json.dump(sig, f, indent=2, default=str, ensure_ascii=False)

    # Write MD
    with open(sig_md, "w", encoding="utf-8") as f:
        f.write("# TITAN XAU AI - Environment Signature\n\n")
        f.write(f"**Generated:** {sig['timestamp_utc']}\n\n")
        f.write(f"**Git Commit:** `{sig['git_commit']}`\n\n")
        f.write(f"**Python:** {sig['python_version']}\n\n")
        f.write(f"**Platform:** {sig['platform']}\n\n")
        f.write(f"**Architecture:** {sig['architecture']}\n\n")
        f.write("## Critical Packages\n\n")
        f.write("| Package | Version |\n|---|---|\n")
        for k, v in sig["critical_packages"].items():
            f.write(f"| {k} | {v or 'NOT INSTALLED'} |\n")
        f.write("\n## Model Files\n\n")
        f.write("| File | Size | SHA256 |\n|---|---|---|\n")
        for name, info in sig["model_files"].items():
            f.write(f"| {name} | {info['size_bytes']} | `{info['sha256'][:16]}...` |\n")
        f.write(f"\n## Warning\n\n{sig['warning']}\n")

    return {"lock_path": str(lock_path), "json_path": str(sig_json), "md_path": str(sig_md)}


def main() -> int:
    print("=" * 70)
    print("  TITAN XAU AI - Freeze Current Environment (Sprint 9.9.3.43.1)")
    print("=" * 70)
    sig = freeze()
    report = write_report(sig)
    print(f"\n  Git: {sig['git_commit']}")
    print(f"  Python: {sig['python_version']}")
    print(f"  Packages: {len(sig['critical_packages'])}")
    print(f"  Model files: {len(sig['model_files'])}")
    print(f"\n  Lock: {report['lock_path']}")
    print(f"  JSON: {report['json_path']}")
    print(f"  MD:   {report['md_path']}")
    print("\n" + "=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
