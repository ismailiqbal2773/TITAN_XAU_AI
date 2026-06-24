"""
TITAN XAU AI — Desktop Launcher (Sprint 7.5)

One-click startup for non-technical users.
- No terminal knowledge required
- GUI dialog boxes for errors (tkinter fallback)
- Environment validation
- Config validation
- MT5 validation
- Launch runtime
- User-friendly messages

Usage:
    python titan_launcher.py            # GUI mode (default)
    python titan_launcher.py --cli      # CLI mode (for debugging)
    python titan_launcher.py --validate # Validate only, don't start

When built with PyInstaller, this becomes TITAN.exe — double-click to run.
"""
from __future__ import annotations

import argparse
import logging
import os
import platform
import sys
import time
from pathlib import Path

# Add repo root to path (works for both script and PyInstaller exe)
if getattr(sys, "frozen", False):
    # PyInstaller exe — repo root is the exe's directory
    REPO_ROOT = Path(sys.executable).resolve().parent
else:
    # Script — repo root is parent of this file
    REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))

logger = logging.getLogger(__name__)


def show_message(title: str, message: str, mode: str = "info") -> None:
    """Show message via GUI (tkinter) or console."""
    if mode == "cli":
        prefix = {"info": "[INFO]", "warn": "[WARN]", "error": "[ERROR]"}.get(mode, "[INFO]")
        print(f"{prefix} {title}: {message}")
        return
    # Try GUI
    try:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        if mode == "error":
            messagebox.showerror(title, message)
        elif mode == "warn":
            messagebox.showwarning(title, message)
        else:
            messagebox.showinfo(title, message)
        root.destroy()
    except ImportError:
        # No tkinter — fall back to console
        print(f"[{mode.upper()}] {title}: {message}")


def validate_environment() -> tuple[bool, list[str]]:
    """Validate environment. Returns (success, messages)."""
    messages = []
    success = True

    # Python version
    py_ver = sys.version_info
    if py_ver.major >= 3 and py_ver.minor >= 12:
        messages.append(f"✓ Python {py_ver.major}.{py_ver.minor}.{py_ver.micro}")
    else:
        messages.append(f"✗ Python {py_ver.major}.{py_ver.minor} — need 3.12+")
        success = False

    # Operating system
    os_name = platform.system()
    messages.append(f"✓ OS: {os_name} {platform.release()}")

    # Required packages
    required = ["yaml", "pandas", "numpy", "xgboost"]
    for pkg in required:
        try:
            __import__(pkg)
            messages.append(f"✓ Package: {pkg}")
        except ImportError:
            messages.append(f"✗ Missing package: {pkg}")
            success = False

    return success, messages


def validate_config() -> tuple[bool, str]:
    """Validate runtime config exists and is safe."""
    config_path = REPO_ROOT / "config" / "runtime.yaml"
    if not config_path.exists():
        return False, f"Config file not found: {config_path}"

    try:
        import yaml
        # Sprint 9.0.1: explicit UTF-8 for Windows cp1252 compatibility.
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        rt = cfg.get("runtime", {})
        if rt.get("dry_run", True) is not True:
            return False, "Config has dry_run=false — refusing to start (safety)"
        if rt.get("live_trading", False) is True:
            return False, "Config has live_trading=true — refusing to start (safety)"
        return True, f"Config OK: {config_path}"
    except Exception as e:
        return False, f"Config validation error: {e}"


def validate_models() -> tuple[bool, list[str]]:
    """Validate model files exist."""
    messages = []
    success = True
    models_dir = REPO_ROOT / "titan" / "data" / "models"
    required = ["xgboost_v1.pkl", "meta_label_v2_context.pkl"]
    for model in required:
        path = models_dir / model
        if path.exists():
            messages.append(f"✓ Model: {model} ({path.stat().st_size / 1024:.0f} KB)")
        else:
            messages.append(f"✗ Missing model: {model}")
            success = False
    return success, messages


def validate_mt5() -> tuple[bool, str]:
    """Validate MT5 connection (Windows only)."""
    if platform.system() != "Windows":
        return True, "Non-Windows — MT5 validation skipped (stub mode)"
    try:
        import MetaTrader5 as mt5
        if mt5.initialize():
            info = mt5.account_info()
            mt5.shutdown()
            if info:
                return True, f"MT5 connected: login={info.login}, server={info.server}"
            return False, "MT5 initialized but no account info"
        return False, "MT5 initialize failed"
    except ImportError:
        return False, "MetaTrader5 package not installed"


def run_smoke_test() -> tuple[bool, str]:
    """Run the demo smoke test."""
    try:
        import asyncio
        from scripts.demo_smoke_test import run_smoke_test as _run
        success = asyncio.run(_run(verbose=False))
        return success, "Smoke test " + ("PASSED" if success else "FAILED")
    except Exception as e:
        return False, f"Smoke test error: {e}"


def launch_runtime() -> int:
    """Launch the TITAN runtime. Returns exit code."""
    try:
        from titan.runtime.launcher import TitanLauncher
        launcher = TitanLauncher(config_path=str(REPO_ROOT / "config" / "runtime.yaml"))
        launcher.start()
        return 0
    except Exception as e:
        logger.error(f"Runtime launch failed: {e}", exc_info=True)
        show_message("TITAN Startup Failed",
                     f"Runtime error: {e}\n\nCheck the log file for details.",
                     mode="error")
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="TITAN XAU AI — Desktop Launcher")
    parser.add_argument("--cli", action="store_true", help="CLI mode (no GUI dialogs)")
    parser.add_argument("--validate", action="store_true", help="Validate only, don't start")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    mode = "cli" if args.cli else "gui"
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=log_level,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    print("=" * 60)
    print("  TITAN XAU AI — Desktop Launcher")
    print("=" * 60)
    print()

    # ─── Step 1: Environment validation ──
    print("[1/5] Validating environment...")
    env_ok, env_msgs = validate_environment()
    for msg in env_msgs:
        print(f"  {msg}")
    if not env_ok:
        show_message("TITAN — Environment Error",
                     "Environment validation failed.\n\n" + "\n".join(env_msgs),
                     mode=mode if mode == "cli" else "error")
        return 1
    print()

    # ─── Step 2: Config validation ──
    print("[2/5] Validating config...")
    cfg_ok, cfg_msg = validate_config()
    print(f"  {cfg_msg}")
    if not cfg_ok:
        show_message("TITAN — Config Error", cfg_msg, mode=mode if mode == "cli" else "error")
        return 1
    print()

    # ─── Step 3: Model validation ──
    print("[3/5] Validating models...")
    model_ok, model_msgs = validate_models()
    for msg in model_msgs:
        print(f"  {msg}")
    if not model_ok:
        show_message("TITAN — Models Error",
                     "Model files missing.\n\n" + "\n".join(model_msgs),
                     mode=mode if mode == "cli" else "error")
        return 1
    print()

    # ─── Step 4: MT5 validation ──
    print("[4/5] Validating MT5 connection...")
    mt5_ok, mt5_msg = validate_mt5()
    print(f"  {mt5_msg}")
    if not mt5_ok:
        show_message("TITAN — MT5 Warning",
                     f"MT5 validation failed: {mt5_msg}\n\n"
                     "TITAN will run in stub mode (no live data).",
                     mode=mode if mode == "cli" else "warn")
    print()

    if args.validate:
        print("[5/5] Validation only — skipping runtime launch")
        show_message("TITAN — Validation Complete",
                     "All validations passed. TITAN is ready to start.",
                     mode=mode if mode == "cli" else "info")
        return 0

    # ─── Step 5: Launch runtime ──
    print("[5/5] Launching TITAN runtime...")
    print()
    print("  Mode: dry_run (NO real orders)")
    print("  Press Ctrl+C to stop")
    print()
    return launch_runtime()


if __name__ == "__main__":
    sys.exit(main())
