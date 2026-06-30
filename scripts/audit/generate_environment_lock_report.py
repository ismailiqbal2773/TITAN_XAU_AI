#!/usr/bin/env python3
"""
TITAN XAU AI - Environment Lock Report (Sprint 9.9.3.43)
=========================================================
NEVER imports MetaTrader5. NEVER sends orders. NEVER pip installs.
"""
from __future__ import annotations
import json, os, platform, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
OUTPUT_DIR = REPO_ROOT / "data" / "audit" / "dependency_compatibility"


def _git_head_short() -> str:
    try:
        r = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                           cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=10)
        return r.stdout.strip() if r.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def generate() -> dict:
    ts = datetime.now(timezone.utc).isoformat()
    head = _git_head_short()
    py_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"

    # Get installed packages
    packages = {}
    for imp in ["xgboost", "sklearn", "pandas", "numpy", "yaml", "MetaTrader5"]:
        try:
            mod = __import__(imp)
            packages[imp] = getattr(mod, "__version__", "unknown")
        except ImportError:
            packages[imp] = None
        except Exception:
            packages[imp] = None

    # Check model files
    model_files = {}
    models_dir = REPO_ROOT / "titan" / "data" / "models"
    if models_dir.exists():
        for f in models_dir.iterdir():
            if f.is_file():
                model_files[f.name] = f.stat().st_size

    return {
        "timestamp_utc": ts,
        "git_commit": head,
        "python_version": py_version,
        "platform": platform.platform(),
        "packages": packages,
        "model_files": model_files,
        "reproducibility_notes": [
            "This report captures the current environment state.",
            "Do NOT auto-install or upgrade packages based on this report.",
            "To reproduce: install the same package versions on the same Python version.",
            "Model files must be present at titan/data/models/.",
        ],
    }


def write_report(result: dict) -> dict:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUTPUT_DIR / "environment_lock_report.json"
    md_path = OUTPUT_DIR / "environment_lock_report.md"
    freeze_path = OUTPUT_DIR / "requirements_observed_freeze.txt"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str, ensure_ascii=False)

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# TITAN XAU AI - Environment Lock Report\n\n")
        f.write(f"**Generated:** {result['timestamp_utc']}\n\n")
        f.write(f"**Git Commit:** `{result['git_commit']}`\n\n")
        f.write(f"**Python:** {result['python_version']}\n\n")
        f.write(f"**Platform:** {result['platform']}\n\n")
        f.write("## Installed Packages\n\n")
        f.write("| Package | Version |\n|---|---|\n")
        for k, v in result["packages"].items():
            f.write(f"| {k} | {v or 'NOT INSTALLED'} |\n")
        f.write("\n## Model Files\n\n")
        f.write("| File | Size (bytes) |\n|---|---|\n")
        for k, v in result["model_files"].items():
            f.write(f"| {k} | {v} |\n")
        f.write("\n## Reproducibility Notes\n\n")
        for n in result["reproducibility_notes"]:
            f.write(f"- {n}\n")

    # Write observed freeze file
    with open(freeze_path, "w", encoding="utf-8") as f:
        f.write(f"# TITAN XAU AI - Observed Environment Freeze\n")
        f.write(f"# Generated: {result['timestamp_utc']}\n")
        f.write(f"# Git Commit: {result['git_commit']}\n")
        f.write(f"# Python: {result['python_version']}\n")
        f.write(f"# Platform: {result['platform']}\n\n")
        for k, v in sorted(result["packages"].items()):
            if v:
                f.write(f"{k}=={v}\n")

    return {"json_path": str(json_path), "md_path": str(md_path), "freeze_path": str(freeze_path)}


def main() -> int:
    print("=" * 70)
    print("  TITAN XAU AI - Environment Lock Report (Sprint 9.9.3.43)")
    print("=" * 70)
    result = generate()
    report = write_report(result)
    print(f"\n  Git: {result['git_commit']}")
    print(f"  Python: {result['python_version']}")
    print(f"  Packages: {len(result['packages'])}")
    print(f"  Model files: {len(result['model_files'])}")
    print(f"\n  JSON: {report['json_path']}")
    print(f"  MD:   {report['md_path']}")
    print(f"  Freeze: {report['freeze_path']}")
    print("\n" + "=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
