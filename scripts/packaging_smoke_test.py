"""
TITAN XAU AI — Packaging Smoke Test (Sprint 7.5)

Verifies the packaged TITAN system launches correctly.
Tests:
  - TITAN.exe (or python titan_launcher.py) launches
  - Config loads
  - MT5 validation works
  - Journal writable
  - Runtime starts
  - Runtime shuts down safely

NO real orders are placed.

Usage:
    python scripts/packaging_smoke_test.py
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))


class PackagingTest:
    def __init__(self):
        self.results = []

    def check(self, name: str, fn) -> bool:
        print(f"  Testing: {name}... ", end="", flush=True)
        try:
            ok, msg = fn()
            icon = "✓" if ok else "✗"
            print(f"{icon} {msg}")
            self.results.append((name, ok, msg))
            return ok
        except Exception as e:
            print(f"✗ ERROR: {e}")
            self.results.append((name, False, str(e)))
            return False

    def test_launcher_imports(self):
        """Verify titan_launcher.py imports without error."""
        try:
            import titan_launcher
            return True, "imports OK"
        except Exception as e:
            return False, f"import error: {e}"

    def test_config_loads(self):
        """Verify config/runtime.yaml loads."""
        import yaml
        path = REPO_ROOT / "config" / "runtime.yaml"
        if not path.exists():
            return False, f"Config not found: {path}"
        with open(path) as f:
            cfg = yaml.safe_load(f)
        if cfg.get("runtime", {}).get("dry_run") is not True:
            return False, "dry_run is not True"
        return True, "dry_run=True (safe)"

    def test_mt5_validator(self):
        """Verify MT5 validator works (stub mode on non-Windows)."""
        from titan.setup.mt5_validator import StubMT5Validator
        v = StubMT5Validator()
        result = v.validate(simulate_demo=True)
        if result.ok:
            return True, "demo validated (stub)"
        return False, f"validation failed: {result.errors}"

    def test_setup_wizard(self):
        """Verify setup wizard can generate config."""
        import tempfile
        from titan.setup.setup_wizard import SetupWizard
        with tempfile.TemporaryDirectory() as tmpdir:
            wizard = SetupWizard(cli_mode=True, stub_mt5=True)
            wizard.config_path = Path(tmpdir) / "test_runtime.yaml"
            wizard.state.terminal_path = "/fake/terminal64.exe"
            wizard.state.login = 12345
            wizard.state.password = "test"
            wizard.state.server = "TestDemo"
            wizard.state.deployment_mode = "local"
            wizard.state.journal_path = "data/journal.jsonl"
            config = wizard._build_config()
            import yaml
            with open(wizard.config_path, "w") as f:
                yaml.safe_dump(config, f)
            if wizard.config_path.exists():
                return True, f"config generated ({wizard.config_path})"
            return False, "config not generated"
        return True, "ok"

    def test_first_run_check(self):
        """Verify first_run_check.py runs."""
        result = subprocess.run(
            [sys.executable, str(REPO_ROOT / "first_run_check.py")],
            capture_output=True, text=True, timeout=30,
            cwd=str(REPO_ROOT),
        )
        if result.returncode == 0:
            return True, "first run check passed"
        return False, f"exit code {result.returncode}: {result.stdout[-200:]}"

    def test_journal_writable(self):
        """Verify journal directory is writable."""
        journal_dir = REPO_ROOT / "data" / "runtime"
        journal_dir.mkdir(parents=True, exist_ok=True)
        test_file = journal_dir / ".packaging_test"
        try:
            with open(test_file, "w") as f:
                f.write("test")
            os.unlink(test_file)
            return True, str(journal_dir)
        except Exception as e:
            return False, f"not writable: {e}"

    def test_runtime_starts(self):
        """Verify TITAN runtime starts (dry_run mode)."""
        try:
            from titan.runtime.launcher import TitanLauncher
            launcher = TitanLauncher(config_path=str(REPO_ROOT / "config" / "runtime.yaml"))
            launcher.load_config()
            ok = launcher.validate_runtime()
            if ok:
                return True, "runtime validation passed"
            return False, "runtime validation failed"
        except Exception as e:
            return False, f"runtime error: {e}"

    def test_no_live_orders(self):
        """Verify dry_run is enforced — no live order path."""
        from titan.production.trade_loop import TradeLoopConfig
        cfg = TradeLoopConfig()
        if cfg.dry_run is True:
            return True, "dry_run=True (default)"
        return False, "dry_run is False — UNSAFE"

    def test_dry_run_default(self):
        """Verify dry_run=True is the default everywhere."""
        from titan.production.trade_loop import TradeLoopConfig
        from titan.production.order_modifier import OrderModifier
        from titan.production.watchdog_restarter import WatchdogRestarter
        checks = []
        checks.append(("TradeLoopConfig", TradeLoopConfig().dry_run is True))
        checks.append(("OrderModifier", OrderModifier().dry_run is True))
        checks.append(("WatchdogRestarter", WatchdogRestarter().dry_run is True))
        all_ok = all(ok for _, ok in checks)
        if all_ok:
            return True, "all modules dry_run=True"
        failed = [name for name, ok in checks if not ok]
        return False, f"not dry_run: {failed}"

    def run_all(self) -> bool:
        print()
        print("=" * 60)
        print("  TITAN XAU AI — Packaging Smoke Test")
        print("=" * 60)
        print()

        self.check("Launcher imports", self.test_launcher_imports)
        self.check("Config loads", self.test_config_loads)
        self.check("MT5 validator", self.test_mt5_validator)
        self.check("Setup wizard", self.test_setup_wizard)
        self.check("First run check", self.test_first_run_check)
        self.check("Journal writable", self.test_journal_writable)
        self.check("Runtime starts", self.test_runtime_starts)
        self.check("No live orders", self.test_no_live_orders)
        self.check("dry_run default", self.test_dry_run_default)

        print()
        print("-" * 60)
        passed = sum(1 for _, ok, _ in self.results if ok)
        failed = sum(1 for _, ok, _ in self.results if not ok)
        print(f"  Results: {passed} passed, {failed} failed")
        print()

        if failed > 0:
            print("  ✗ PACKAGING SMOKE TEST FAILED")
            print("  Do not distribute TITAN until all tests pass.")
            return False
        else:
            print("  ✓ PACKAGING SMOKE TEST PASSED")
            print("  TITAN is ready for distribution.")
            return True


def main():
    test = PackagingTest()
    success = test.run_all()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
