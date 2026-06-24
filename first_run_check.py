"""
TITAN XAU AI — First Run Check (Sprint 7.5)

Verifies TITAN is ready for first run.
Shows clear PASS/WARN/FAIL messages.

Usage:
    python first_run_check.py
    python first_run_check.py --cli  # console output only
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))


class CheckResult:
    def __init__(self, name: str, status: str, message: str = ""):
        self.name = name
        self.status = status  # PASS | WARN | FAIL
        self.message = message

    def __repr__(self) -> str:
        icon = {"PASS": "✓", "WARN": "⚠", "FAIL": "✗"}.get(self.status, "?")
        return f"  {icon} [{self.status}] {self.name}: {self.message}"


def run_checks(cli_mode: bool = True) -> list[CheckResult]:
    """Run all first-run checks. Returns list of results."""
    results = []

    # ─── Check 1: Config exists ──
    config_path = REPO_ROOT / "config" / "runtime.yaml"
    if config_path.exists():
        results.append(CheckResult("Config file", "PASS", str(config_path)))
        # Verify dry_run=True
        try:
            import yaml
            # Sprint 9.0.1: explicit UTF-8 for Windows cp1252 compatibility.
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f)
            rt = cfg.get("runtime", {})
            if rt.get("dry_run", True):
                results.append(CheckResult("dry_run mode", "PASS", "True (safe)"))
            else:
                results.append(CheckResult("dry_run mode", "FAIL", "False — UNSAFE for first run"))
            if not rt.get("live_trading", False):
                results.append(CheckResult("live_trading flag", "PASS", "False (safe)"))
            else:
                results.append(CheckResult("live_trading flag", "FAIL", "True — UNSAFE for first run"))
        except Exception as e:
            results.append(CheckResult("Config valid", "FAIL", f"Parse error: {e}"))
    else:
        results.append(CheckResult("Config file", "FAIL", f"Not found: {config_path}"))
        results.append(CheckResult("dry_run mode", "WARN", "Cannot check — no config"))
        results.append(CheckResult("live_trading flag", "WARN", "Cannot check — no config"))

    # ─── Check 2: Models exist ──
    models_dir = REPO_ROOT / "titan" / "data" / "models"
    required_models = ["xgboost_v1.pkl", "meta_label_v2_context.pkl"]
    for model in required_models:
        path = models_dir / model
        if path.exists():
            results.append(CheckResult(f"Model: {model}", "PASS",
                                        f"{path.stat().st_size / 1024:.0f} KB"))
        else:
            results.append(CheckResult(f"Model: {model}", "FAIL", "Not found"))

    # ─── Check 3: Canonical data exists ──
    canonical_path = REPO_ROOT / "titan" / "data" / "canonical" / "XAUUSD_H1_canonical.parquet"
    if canonical_path.exists():
        results.append(CheckResult("Canonical H1 data", "PASS",
                                    f"{canonical_path.stat().st_size / 1024 / 1024:.1f} MB"))
    else:
        results.append(CheckResult("Canonical H1 data", "FAIL", "Not found"))

    # ─── Check 4: Journal writable ──
    journal_path = REPO_ROOT / "data" / "runtime" / "titan_journal.jsonl"
    try:
        journal_path.parent.mkdir(parents=True, exist_ok=True)
        test_file = journal_path.parent / ".write_test"
        # Sprint 9.0.1: explicit UTF-8 (defensive — content is ASCII).
        with open(test_file, "w", encoding="utf-8") as f:
            f.write("test")
        os.unlink(test_file)
        results.append(CheckResult("Journal directory", "PASS", str(journal_path.parent)))
    except Exception as e:
        results.append(CheckResult("Journal directory", "FAIL", f"Not writable: {e}"))

    # ─── Check 5: Python packages ──
    required_pkgs = ["yaml", "pandas", "numpy", "xgboost"]
    for pkg in required_pkgs:
        try:
            __import__(pkg)
            results.append(CheckResult(f"Package: {pkg}", "PASS", "installed"))
        except ImportError:
            results.append(CheckResult(f"Package: {pkg}", "FAIL", "not installed"))

    # ─── Check 6: MT5 reachable ──
    try:
        import MetaTrader5 as mt5
        if mt5.initialize(timeout=5000):
            mt5.shutdown()
            results.append(CheckResult("MT5 connection", "PASS", "reachable"))
        else:
            results.append(CheckResult("MT5 connection", "WARN", "initialize failed — stub mode"))
    except ImportError:
        results.append(CheckResult("MT5 connection", "WARN", "MetaTrader5 not installed — stub mode"))

    # ─── Check 7: No live trading env var ──
    live_flag = os.environ.get("TITAN_LIVE_TRADING", "0")
    if live_flag == "1":
        results.append(CheckResult("TITAN_LIVE_TRADING env", "WARN",
                                    "Set to 1 — live mode may be enabled"))
    else:
        results.append(CheckResult("TITAN_LIVE_TRADING env", "PASS",
                                    "Not set (dry_run only)"))

    return results


def main() -> int:
    print()
    print("=" * 60)
    print("  TITAN XAU AI — First Run Check")
    print("=" * 60)
    print()

    results = run_checks()

    pass_count = sum(1 for r in results if r.status == "PASS")
    warn_count = sum(1 for r in results if r.status == "WARN")
    fail_count = sum(1 for r in results if r.status == "FAIL")

    for r in results:
        print(r)

    print()
    print("-" * 60)
    print(f"  Results: {pass_count} PASS, {warn_count} WARN, {fail_count} FAIL")
    print()

    if fail_count > 0:
        print("  ✗ FIRST RUN CHECK FAILED")
        print("  Fix FAIL items above before starting TITAN.")
        return 1
    elif warn_count > 0:
        print("  ⚠ FIRST RUN CHECK PASSED WITH WARNINGS")
        print("  TITAN can start, but some features may be limited.")
        return 0
    else:
        print("  ✓ FIRST RUN CHECK PASSED")
        print("  TITAN is ready to start.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
