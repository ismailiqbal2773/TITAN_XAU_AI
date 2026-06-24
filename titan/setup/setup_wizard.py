"""
TITAN XAU AI — Setup Wizard (Sprint 7.5)

Interactive 6-step setup wizard for non-technical users.
Generates runtime.yaml config.

Wizard steps:
  Step 1: Locate MT5 terminal
  Step 2: Validate MT5 installation
  Step 3: Validate demo account
  Step 4: Select deployment mode (Local PC / VPS / Institute)
  Step 5: Configure journal location
  Step 6: Save configuration

Usage:
    wizard = SetupWizard()
    wizard.run()
    # Config saved to config/runtime.yaml
"""
from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

from titan.setup.mt5_validator import MT5Validator, StubMT5Validator

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = REPO_ROOT / "config" / "runtime.yaml"


@dataclass
class WizardState:
    """State of the setup wizard."""
    step: int = 1
    terminal_path: str = ""
    mt5_validated: bool = False
    login: int = 0
    password: str = ""
    server: str = ""
    demo_validated: bool = False
    deployment_mode: str = "local"   # local | vps | institute
    journal_path: str = "data/runtime/titan_journal.jsonl"
    config_saved: bool = False
    config_path: str = ""


class SetupWizard:
    """
    Interactive setup wizard.

    In CLI mode, uses input() prompts.
    In GUI mode (future), uses tkinter dialogs.
    """

    def __init__(self, cli_mode: bool = True, stub_mt5: bool = False):
        self.cli_mode = cli_mode
        self.stub_mt5 = stub_mt5
        self.state = WizardState()
        self.config_path = DEFAULT_CONFIG_PATH

    def run(self) -> bool:
        """Run the full wizard. Returns True iff config saved successfully."""
        print()
        print("=" * 60)
        print("  TITAN XAU AI — Setup Wizard")
        print("=" * 60)
        print("  This wizard will configure TITAN for your MT5 demo account.")
        print("  Press Ctrl+C at any time to cancel.")
        print()

        try:
            self._step1_locate_mt5()
            self._step2_validate_mt5()
            self._step3_validate_demo()
            self._step4_select_deployment()
            self._step5_configure_journal()
            self._step6_save_config()
            return True
        except KeyboardInterrupt:
            print("\n\nWizard cancelled by user.")
            return False
        except Exception as e:
            print(f"\n\nWizard failed: {e}")
            return False

    # ─── Steps ──────────────────────────────────────────────────────────

    def _step1_locate_mt5(self) -> None:
        """Step 1: Locate MT5 terminal."""
        self.state.step = 1
        print("[Step 1/6] Locate MT5 Terminal")
        print("-" * 40)

        # Try to auto-detect
        validator = MT5Validator()
        detected = validator._find_terminal()

        if detected:
            print(f"  ✓ MT5 terminal detected: {detected}")
            response = input(f"  Use this path? (Y/n): ").strip().lower()
            if response in ("", "y", "yes"):
                self.state.terminal_path = detected
                return

        # Manual input
        print("\n  Please enter the path to your MT5 terminal64.exe")
        print("  Default: C:\\Program Files\\MetaTrader 5\\terminal64.exe")
        path = input("  Path: ").strip()
        if not path:
            path = r"C:\Program Files\MetaTrader 5\terminal64.exe"
        self.state.terminal_path = path
        print(f"  ✓ Terminal path set: {path}")
        print()

    def _step2_validate_mt5(self) -> None:
        """Step 2: Validate MT5 installation."""
        self.state.step = 2
        print("[Step 2/6] Validate MT5 Installation")
        print("-" * 40)

        if self.stub_mt5:
            validator = StubMT5Validator()
            result = validator.validate(simulate_demo=True)
        else:
            validator = MT5Validator()
            result = validator.validate(terminal_path=self.state.terminal_path)

        if result.ok:
            print("  ✓ MT5 installation validated")
            self.state.mt5_validated = True
        else:
            print("  ✗ MT5 validation failed:")
            for err in result.errors:
                print(f"      {err}")
            if self.stub_mt5:
                print("  ⚠ Using stub mode — continuing anyway")
                self.state.mt5_validated = True
            else:
                response = input("  Continue anyway? (y/N): ").strip().lower()
                if response != "y":
                    sys.exit(1)
                self.state.mt5_validated = False
        print()

    def _step3_validate_demo(self) -> None:
        """Step 3: Validate demo account."""
        self.state.step = 3
        print("[Step 3/6] Validate Demo Account")
        print("-" * 40)

        print("  Enter your MT5 demo account credentials:")
        login_str = input("  Login (e.g., 34265693): ").strip()
        self.state.login = int(login_str) if login_str.isdigit() else 0
        self.state.password = input("  Password: ").strip()
        self.state.server = input("  Server (e.g., FundedNext-Server 3): ").strip()

        if self.stub_mt5:
            validator = StubMT5Validator()
            result = validator.validate(
                login=self.state.login,
                password=self.state.password,
                server=self.state.server,
                simulate_demo=True,
            )
        else:
            validator = MT5Validator()
            result = validator.validate(
                login=self.state.login,
                password=self.state.password,
                server=self.state.server,
                terminal_path=self.state.terminal_path,
            )

        if result.ok and result.checks.get("is_demo"):
            print(f"  ✓ Demo account validated: login={self.state.login}")
            self.state.demo_validated = True
        else:
            print("  ✗ Demo account validation failed:")
            for err in result.errors:
                print(f"      {err}")
            if self.stub_mt5:
                print("  ⚠ Stub mode — continuing")
                self.state.demo_validated = True
            else:
                response = input("  Continue anyway? (y/N): ").strip().lower()
                if response != "y":
                    sys.exit(1)
        print()

    def _step4_select_deployment(self) -> None:
        """Step 4: Select deployment mode."""
        self.state.step = 4
        print("[Step 4/6] Select Deployment Mode")
        print("-" * 40)
        print("  1. Local PC (recommended for demo)")
        print("  2. VPS (for 24/7 unattended operation)")
        print("  3. Institute (multi-account management)")
        choice = input("  Select (1/2/3) [default=1]: ").strip()
        modes = {"1": "local", "2": "vps", "3": "institute"}
        self.state.deployment_mode = modes.get(choice, "local")
        print(f"  ✓ Deployment mode: {self.state.deployment_mode}")
        print()

    def _step5_configure_journal(self) -> None:
        """Step 5: Configure journal location."""
        self.state.step = 5
        print("[Step 5/6] Configure Journal Location")
        print("-" * 40)
        print(f"  Default: {self.state.journal_path}")
        path = input("  Journal path (press Enter for default): ").strip()
        if path:
            self.state.journal_path = path
        print(f"  ✓ Journal path: {self.state.journal_path}")
        print()

    def _step6_save_config(self) -> None:
        """Step 6: Save configuration."""
        self.state.step = 6
        print("[Step 6/6] Save Configuration")
        print("-" * 40)

        config = self._build_config()
        config_dir = self.config_path.parent
        config_dir.mkdir(parents=True, exist_ok=True)

        # Sprint 9.0.1: explicit UTF-8 for Windows cp1252 compatibility.
        with open(self.config_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(config, f, default_flow_style=False, sort_keys=False,
                           allow_unicode=True)

        self.state.config_saved = True
        self.state.config_path = str(self.config_path)
        print(f"  ✓ Configuration saved: {self.config_path}")
        print()
        print("=" * 60)
        print("  Setup Complete!")
        print("=" * 60)
        print(f"  Config: {self.config_path}")
        print(f"  Mode:   dry_run (NO real orders)")
        print(f"  Next:   Run TITAN.bat or python titan_launcher.py")
        print()

    def _build_config(self) -> dict:
        """Build the runtime.yaml config dict."""
        return {
            "runtime": {
                "dry_run": True,
                "live_trading": False,
                "log_level": "INFO",
                "journal_path": self.state.journal_path,
                "session_id": "auto",
            },
            "symbol": {
                "name": "XAUUSD",
                "timeframe": "H1",
                "alternate_names": ["XAUUSD", "XAUUSD.c", "GOLD", "XAU/USD"],
            },
            "models": {
                "xgb_path": "titan/data/models/xgboost_v1.pkl",
                "meta_path": "titan/data/models/meta_label_v2_context.pkl",
                "lstm_path": "titan/data/models/lstm_v1.pt",
                "transformer_path": "titan/data/models/transformer_v1.pt",
                "hpo_params_dir": "titan/data/hpo",
            },
            "features": {
                "window": 300,
                "source": "canonical",
                "canonical_path": "titan/data/canonical/XAUUSD_H1_canonical.parquet",
            },
            "inference": {
                "xgb_threshold": 0.55,
                "meta_threshold": 0.65,
            },
            "risk": {
                "max_lot": 0.01,
                "max_open_positions": 1,
                "sl_pips": 50,
                "tp_pips": 100,
                "max_spread_usd": 1.0,
                "deviation_points": 20,
                "magic_number": 202619,
            },
            "kill_switch": {
                "max_daily_loss_pct": 3.0,
                "max_drawdown_pct": 5.0,
                "max_consecutive_losses": 5,
                "emergency_daily_loss_pct": 5.0,
                "emergency_drawdown_pct": 8.0,
                "max_latency_ms": 500.0,
                "emergency_latency_ms": 1000.0,
                "max_spread_usd": 1.0,
                "emergency_spread_usd": 2.0,
                "max_brier": 0.22,
                "emergency_brier": 0.28,
                "max_ece": 0.08,
                "emergency_ece": 0.12,
            },
            "news_filter": {
                "enabled": True,
                "csv_path": "data/economic_calendar.csv",
                "block_window_minutes": 30,
                "event_types": ["NFP", "CPI", "FOMC", "ECB", "BOE"],
            },
            "position_sync": {
                "interval_seconds": 10.0,
                "broker_source": "mt5" if not self.stub_mt5 else "stub",
                "magic_filter": 202619,
            },
            "watchdog": {
                "enabled": True,
                "dry_run": True,
                "check_interval_s": 10.0,
                "max_restarts_per_minute": 3,
            },
            "exit_manager": {
                "max_holding_hours": 24.0,
                "stale_threshold_seconds": 300.0,
                "trailing_activation_r_multiple": 1.0,
                "trailing_distance_r": 0.5,
                "enable_trailing": True,
                "enable_max_holding": True,
                "enable_stale": True,
            },
            "mt5": {
                "terminal_path": self.state.terminal_path,
                "login": self.state.login,
                "password": "***",  # placeholder — user sets via env var in production
                "server": self.state.server,
                "timeout": 60000,
            },
            "deployment": {
                "mode": self.state.deployment_mode,
            },
        }


def run_wizard_cli(stub_mt5: bool = False) -> bool:
    """Run the setup wizard in CLI mode."""
    wizard = SetupWizard(cli_mode=True, stub_mt5=stub_mt5)
    return wizard.run()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="TITAN Setup Wizard")
    parser.add_argument("--stub", action="store_true", help="Use stub MT5 (for testing)")
    args = parser.parse_args()
    success = run_wizard_cli(stub_mt5=args.stub)
    sys.exit(0 if success else 1)
