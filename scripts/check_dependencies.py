"""
TITAN XAU AI — Startup Dependency Checker

Verifies all required packages are installed + compatible.
Detects: missing packages, unsupported versions, incompatible Python.

Usage:
    python scripts/check_dependencies.py
    python scripts/check_dependencies.py --strict  (exit 1 on any warning)
"""
from __future__ import annotations

import sys
import importlib
import importlib.metadata
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# ─── Required packages (must be installed) ────────────────────────────────────
REQUIRED = {
    "numpy":        {"min": "1.26", "max": "3.0", "import": "numpy"},
    "scipy":        {"min": "1.12", "max": "2.0", "import": "scipy"},
    "pandas":       {"min": "2.2",  "max": "3.0", "import": "pandas"},
    "pyyaml":       {"min": "6.0",  "max": "7.0", "import": "yaml"},
    "sqlalchemy":   {"min": "2.0",  "max": "3.0", "import": "sqlalchemy"},
    "aiosqlite":    {"min": "0.20", "max": "1.0", "import": "aiosqlite"},
    "redis":        {"min": "5.0",  "max": "9.0", "import": "redis"},
    "fastapi":      {"min": "0.110","max": "1.0", "import": "fastapi"},
    "uvicorn":      {"min": "0.29", "max": "1.0", "import": "uvicorn"},
    "pydantic":     {"min": "2.6",  "max": "3.0", "import": "pydantic"},
    "xgboost":      {"min": "2.0",  "max": "3.0", "import": "xgboost"},
    "scikit-learn": {"min": "1.4",  "max": "2.0", "import": "sklearn"},
    "pyarrow":      {"min": "15.0", "max": "25.0","import": "pyarrow"},
    "structlog":    {"min": "24.0", "max": "27.0","import": "structlog"},
    "prometheus-client": {"min": "0.20", "max": "1.0", "import": "prometheus_client"},
    "reportlab":    {"min": "4.0",  "max": "5.0", "import": "reportlab"},
    "python-docx":  {"min": "1.0",  "max": "2.0", "import": "docx"},
    "requests":     {"min": "2.32", "max": "3.0", "import": "requests"},
    "pytest":       {"min": "8.0",  "max": "10.0","import": "pytest"},
    "pytest-asyncio": {"min": "0.23", "max": "2.0", "import": "pytest_asyncio"},
}

# ─── Optional packages (warn if missing, don't fail) ──────────────────────────
OPTIONAL = {
    "MetaTrader5":  {"min": "5.0",  "max": "6.0", "import": "MetaTrader5",
                     "note": "Windows only — stub mode used on Linux/Mac"},
    "torch":        {"min": "2.0",  "max": "3.0", "import": "torch",
                     "note": "Only needed for LSTM/Transformer inference"},
    "onnxruntime":  {"min": "1.17", "max": "2.0", "import": "onnxruntime",
                     "note": "Only needed for ONNX model inference"},
    "lightgbm":     {"min": "4.0",  "max": "5.0", "import": "lightgbm",
                     "note": "Only needed if using LightGBM model"},
    "optuna":       {"min": "4.0",  "max": "5.0", "import": "optuna",
                     "note": "Only needed for HPO (not runtime)"},
    "psutil":       {"min": "5.0",  "max": "8.0", "import": "psutil",
                     "note": "Optional — for runtime health monitoring"},
}

SUPPORTED_PYTHON = [(3, 11), (3, 12), (3, 13)]


def parse_version(ver_str: str) -> tuple:
    """Parse version string to tuple of ints."""
    parts = ver_str.split(".")
    return tuple(int(p) for p in parts if p.isdigit())


def version_in_range(ver: str, min_ver: str, max_ver: str) -> bool:
    """Check if version is in [min, max) range."""
    v = parse_version(ver)
    lo = parse_version(min_ver)
    hi = parse_version(max_ver)
    return lo <= v < hi


def check_python() -> tuple[bool, str]:
    """Check Python version is supported."""
    major, minor = sys.version_info[:2]
    py_ver = f"{major}.{minor}"
    for supp_major, supp_minor in SUPPORTED_PYTHON:
        if major == supp_major and minor == supp_minor:
            return True, f"Python {py_ver} (supported)"
    return False, f"Python {py_ver} — UNSUPPORTED. Use one of: {', '.join(f'{m}.{n}' for m,n in SUPPORTED_PYTHON)}"


def check_package(name: str, info: dict, required: bool = True) -> tuple[bool, str, str]:
    """
    Check a single package.
    Returns (ok, status, message).
    """
    import_name = info["import"]
    try:
        mod = importlib.import_module(import_name)
        ver = getattr(mod, "__version__", None)
        if ver is None:
            # Try importlib.metadata
            try:
                ver = importlib.metadata.version(name)
            except Exception:
                ver = "unknown"

        if ver == "unknown":
            if required:
                return False, "FAIL", f"{name}: installed but version unknown (expected {info['min']}-{info['max']})"
            return True, "WARN", f"{name}: installed (version unknown)"

        if version_in_range(ver, info["min"], info["max"]):
            return True, "PASS", f"{name}=={ver} (in range {info['min']}-{info['max']})"
        else:
            if required:
                return False, "FAIL", f"{name}=={ver} OUTSIDE range {info['min']}-{info['max']}"
            return True, "WARN", f"{name}=={ver} (outside range {info['min']}-{info['max']})"

    except ImportError:
        if required:
            return False, "FAIL", f"{name}: NOT INSTALLED (required, range {info['min']}-{info['max']})"
        return True, "WARN", f"{name}: not installed — {info.get('note', 'optional')}"


def run_check(strict: bool = False) -> int:
    """Run all dependency checks. Returns exit code (0=pass, 1=fail)."""
    print()
    print("=" * 70)
    print("  TITAN XAU AI — Dependency Check")
    print("=" * 70)
    print()

    # Python version
    py_ok, py_msg = check_python()
    icon = "✓" if py_ok else "✗"
    print(f"  {icon} {py_msg}")
    if not py_ok:
        print("\n  ❌ Python version check FAILED")
        return 1

    print()

    # Required packages
    print("  REQUIRED PACKAGES:")
    required_fails = 0
    for name, info in sorted(REQUIRED.items()):
        ok, status, msg = check_package(name, info, required=True)
        icon = "✓" if ok else "✗"
        print(f"    {icon} [{status}] {msg}")
        if not ok:
            required_fails += 1
    print()

    # Optional packages
    print("  OPTIONAL PACKAGES:")
    optional_warns = 0
    for name, info in sorted(OPTIONAL.items()):
        ok, status, msg = check_package(name, info, required=False)
        icon = "✓" if status == "PASS" else "⚠"
        print(f"    {icon} [{status}] {msg}")
        if status == "WARN":
            optional_warns += 1
    print()

    # Summary
    total = len(REQUIRED) + len(OPTIONAL)
    passed = total - required_fails - optional_warns
    print(f"  Summary: {passed} passed, {required_fails} failed, {optional_warns} warnings")
    print()

    if required_fails > 0:
        print("  ❌ DEPENDENCY CHECK FAILED — install missing packages:")
        print(f"     pip install -r requirements.txt")
        return 1
    elif optional_warns > 0 and strict:
        print("  ⚠ DEPENDENCY CHECK PASSED WITH WARNINGS (strict mode)")
        return 1
    else:
        print("  ✅ DEPENDENCY CHECK PASSED")
        return 0


def main():
    import argparse
    parser = argparse.ArgumentParser(description="TITAN Dependency Checker")
    parser.add_argument("--strict", action="store_true",
                        help="Exit 1 on any warning (not just failures)")
    args = parser.parse_args()
    sys.exit(run_check(strict=args.strict))


if __name__ == "__main__":
    main()
