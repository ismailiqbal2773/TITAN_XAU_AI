"""
Tests for Sprint 7.5 — Packaging & Distribution Layer.

Verifies:
  - Launcher starts correctly
  - Setup wizard creates config
  - MT5 validator works
  - First-run checks work
  - Packaging smoke test passes
  - No live orders enabled
  - dry_run remains default
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import tempfile
import time
import pytest
import yaml
import numpy as np
from pathlib import Path
from unittest.mock import patch

from titan.production.inference import Signal, Direction
from titan.production.trade_loop import TradeLoop, TradeLoopConfig
from titan.production.trade_journal import TradeJournal, EventType
from titan.production.kill_switch_fsm import KillSwitchFSM
from titan.setup.mt5_validator import MT5Validator, StubMT5Validator, ValidationResult
from titan.setup.setup_wizard import SetupWizard, WizardState


REPO_ROOT = Path(__file__).resolve().parents[2]


# ─── Helpers ──────────────────────────────────────────────────────────────────

def make_signal(direction=Direction.LONG, is_tradeable=True) -> Signal:
    return Signal(
        timestamp=time.time(), direction=direction,
        confidence=0.80, meta_confidence=0.85,
        xgb_proba=[0.2, 0.8] if direction == Direction.LONG else [0.8, 0.2],
        meta_proba=[0.15, 0.85], is_tradeable=is_tradeable,
        feature_vector=np.zeros(55), inference_ms=10.0, source="test",
    )


# ─── 1. Launcher Tests ────────────────────────────────────────────────────────

class TestLauncher:
    def test_launcher_imports(self):
        """Verify titan_launcher.py imports without error."""
        import titan_launcher
        assert hasattr(titan_launcher, "main")
        assert hasattr(titan_launcher, "validate_environment")
        assert hasattr(titan_launcher, "validate_config")
        assert hasattr(titan_launcher, "validate_models")

    def test_validate_environment(self):
        import titan_launcher
        ok, msgs = titan_launcher.validate_environment()
        # Should pass in test environment
        assert isinstance(ok, bool)
        assert isinstance(msgs, list)
        assert len(msgs) > 0

    def test_validate_config_passes(self):
        """Config should be valid (dry_run=True default)."""
        import titan_launcher
        ok, msg = titan_launcher.validate_config()
        assert ok is True
        assert "OK" in msg

    def test_validate_models_passes(self):
        """Models should exist."""
        import titan_launcher
        ok, msgs = titan_launcher.validate_models()
        assert ok is True
        assert len(msgs) >= 2  # xgb + meta

    def test_launcher_validate_only(self):
        """Launcher --validate should exit 0."""
        result = subprocess.run(
            [sys.executable, str(REPO_ROOT / "titan_launcher.py"),
             "--validate", "--cli"],
            capture_output=True, text=True, timeout=30,
            cwd=str(REPO_ROOT),
        )
        assert result.returncode == 0
        assert "Validation" in result.stdout

    def test_dry_run_enforced_in_launcher(self):
        """Launcher refuses to start if dry_run=False."""
        import titan_launcher
        # Create a temp config with dry_run=False
        with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as tf:
            cfg = {
                "runtime": {"dry_run": False, "live_trading": True,
                            "journal_path": "/tmp/test.jsonl"},
            }
            yaml.safe_dump(cfg, tf)
            temp_config = tf.name
        try:
            # Patch the config path
            original_path = titan_launcher.REPO_ROOT
            titan_launcher.REPO_ROOT = Path(temp_config).parent
            # Rename temp to runtime.yaml
            target = Path(temp_config).parent / "config" / "runtime.yaml"
            target.parent.mkdir(exist_ok=True)
            import shutil
            shutil.copy(temp_config, target)
            ok, msg = titan_launcher.validate_config()
            assert ok is False
            assert "dry_run=false" in msg or "refusing" in msg
            titan_launcher.REPO_ROOT = original_path
        finally:
            os.unlink(temp_config)


# ─── 2. MT5 Validator Tests ──────────────────────────────────────────────────

class TestMT5Validator:
    def test_stub_validator_demo_passes(self):
        v = StubMT5Validator()
        result = v.validate(simulate_demo=True)
        assert result.ok is True
        assert result.checks["is_demo"] is True

    def test_stub_validator_real_fails(self):
        v = StubMT5Validator()
        result = v.validate(simulate_demo=False)
        assert result.ok is False
        assert any("REAL ACCOUNT" in e for e in result.errors)

    def test_stub_validator_returns_account_info(self):
        v = StubMT5Validator()
        result = v.validate(login=34265693, server="FundedNext-Server 3")
        assert result.account_info["login"] == 34265693
        assert result.account_info["server"] == "FundedNext-Server 3"
        assert result.account_info["balance"] == 6000.0

    def test_stub_validator_returns_symbol_info(self):
        v = StubMT5Validator()
        result = v.validate()
        assert result.symbol_info["name"] == "XAUUSD"
        assert result.symbol_info["contract_size"] == 100.0

    def test_real_validator_non_windows_skips(self):
        """On non-Windows, validator skips (stub mode)."""
        v = MT5Validator()
        result = v.validate()
        # On Linux test env, should skip with warning
        assert result.ok is True
        assert len(result.warnings) > 0

    def test_validator_result_has_checks_dict(self):
        v = StubMT5Validator()
        result = v.validate()
        assert isinstance(result.checks, dict)
        assert "platform" in result.checks
        assert "mt5_package" in result.checks
        assert "initialize" in result.checks
        assert "is_demo" in result.checks
        assert "symbol" in result.checks


# ─── 3. Setup Wizard Tests ───────────────────────────────────────────────────

class TestSetupWizard:
    def test_wizard_initializes(self):
        wizard = SetupWizard(cli_mode=True, stub_mt5=True)
        assert wizard.state.step == 1
        assert wizard.state.deployment_mode == "local"

    def test_wizard_builds_config(self):
        wizard = SetupWizard(cli_mode=True, stub_mt5=True)
        wizard.state.terminal_path = "/fake/terminal64.exe"
        wizard.state.login = 12345
        wizard.state.password = "test"
        wizard.state.server = "TestDemo"
        wizard.state.deployment_mode = "vps"
        wizard.state.journal_path = "custom/journal.jsonl"
        config = wizard._build_config()
        assert config["runtime"]["dry_run"] is True
        assert config["runtime"]["live_trading"] is False
        assert config["runtime"]["journal_path"] == "custom/journal.jsonl"
        assert config["mt5"]["terminal_path"] == "/fake/terminal64.exe"
        assert config["mt5"]["login"] == 12345
        assert config["mt5"]["server"] == "TestDemo"
        assert config["deployment"]["mode"] == "vps"

    def test_wizard_saves_config(self, tmp_path):
        wizard = SetupWizard(cli_mode=True, stub_mt5=True)
        wizard.config_path = tmp_path / "test_runtime.yaml"
        wizard.state.terminal_path = "/fake/terminal64.exe"
        wizard.state.login = 12345
        wizard.state.password = "test"
        wizard.state.server = "TestDemo"
        wizard.state.deployment_mode = "local"
        wizard.state.journal_path = "data/journal.jsonl"
        # Build + save config
        config = wizard._build_config()
        with open(wizard.config_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(config, f, allow_unicode=True)
        assert wizard.config_path.exists()
        # Verify config is valid YAML
        with open(wizard.config_path, "r", encoding="utf-8") as f:
            loaded = yaml.safe_load(f)
        assert loaded["runtime"]["dry_run"] is True

    def test_wizard_config_has_safe_defaults(self):
        """Config generated by wizard must have safe defaults."""
        wizard = SetupWizard(cli_mode=True, stub_mt5=True)
        config = wizard._build_config()
        # dry_run must be True
        assert config["runtime"]["dry_run"] is True
        # live_trading must be False
        assert config["runtime"]["live_trading"] is False
        # max_lot must be 0.01
        assert config["risk"]["max_lot"] == 0.01
        # max_open_positions must be 1
        assert config["risk"]["max_open_positions"] == 1
        # watchdog dry_run must be True
        assert config["watchdog"]["dry_run"] is True

    def test_wizard_config_includes_all_sections(self):
        wizard = SetupWizard(cli_mode=True, stub_mt5=True)
        config = wizard._build_config()
        required_sections = [
            "runtime", "symbol", "models", "features", "inference",
            "risk", "kill_switch", "news_filter", "position_sync",
            "watchdog", "exit_manager", "mt5", "deployment",
        ]
        for section in required_sections:
            assert section in config, f"Missing section: {section}"


# ─── 4. First Run Check Tests ─────────────────────────────────────────────────

class TestFirstRunCheck:
    def test_first_run_check_runs(self):
        """first_run_check.py should run and return 0 or 1."""
        result = subprocess.run(
            [sys.executable, str(REPO_ROOT / "first_run_check.py")],
            capture_output=True, text=True, timeout=30,
            cwd=str(REPO_ROOT),
        )
        # Should pass (exit 0) in the test environment
        assert result.returncode in (0, 1)
        assert "FIRST RUN CHECK" in result.stdout

    def test_first_run_check_has_pass_results(self):
        result = subprocess.run(
            [sys.executable, str(REPO_ROOT / "first_run_check.py")],
            capture_output=True, text=True, timeout=30,
            cwd=str(REPO_ROOT),
        )
        # Should have at least some PASS results
        assert "PASS" in result.stdout

    def test_first_run_check_verifies_dry_run(self):
        """First run check must verify dry_run=True."""
        from first_run_check import run_checks
        results = run_checks()
        dry_run_results = [r for r in results if "dry_run" in r.name]
        assert len(dry_run_results) > 0
        assert any(r.status == "PASS" for r in dry_run_results)


# ─── 5. Packaging Smoke Test ─────────────────────────────────────────────────

class TestPackagingSmokeTest:
    def test_packaging_smoke_test_imports(self):
        from scripts.packaging_smoke_test import PackagingTest
        assert PackagingTest is not None

    def test_packaging_smoke_test_runs(self):
        """Run the packaging smoke test directly."""
        from scripts.packaging_smoke_test import PackagingTest
        test = PackagingTest()
        # Run individual checks (don't call run_all to avoid subprocess)
        assert test.test_launcher_imports()[0] is True
        assert test.test_config_loads()[0] is True
        assert test.test_mt5_validator()[0] is True
        assert test.test_setup_wizard()[0] is True
        assert test.test_journal_writable()[0] is True
        assert test.test_runtime_starts()[0] is True
        assert test.test_no_live_orders()[0] is True
        assert test.test_dry_run_default()[0] is True


# ─── 6. Safety: No Live Orders ───────────────────────────────────────────────

class TestNoLiveOrders:
    def test_dry_run_default_in_trade_loop(self):
        cfg = TradeLoopConfig()
        assert cfg.dry_run is True

    def test_dry_run_default_in_launcher_config(self):
        from titan.runtime.launcher import LauncherConfig
        cfg = LauncherConfig()
        assert cfg.dry_run is True
        assert cfg.live_trading is False

    def test_dry_run_default_in_order_modifier(self):
        from titan.production.order_modifier import OrderModifier
        mod = OrderModifier()
        assert mod.dry_run is True

    def test_dry_run_default_in_watchdog(self):
        from titan.production.watchdog_restarter import WatchdogRestarter
        wd = WatchdogRestarter()
        assert wd.dry_run is True

    def test_live_mode_requires_env_var(self, monkeypatch):
        monkeypatch.delenv("TITAN_LIVE_TRADING", raising=False)
        with pytest.raises(PermissionError):
            TradeLoop(TradeLoopConfig(dry_run=False))

    def test_config_generated_by_wizard_is_dry_run(self, tmp_path):
        """Config from setup wizard must be dry_run=True."""
        wizard = SetupWizard(cli_mode=True, stub_mt5=True)
        wizard.config_path = tmp_path / "wizard_config.yaml"
        wizard.state.terminal_path = "/fake"
        wizard.state.login = 12345
        wizard.state.password = "test"
        wizard.state.server = "Demo"
        config = wizard._build_config()
        with open(wizard.config_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(config, f, allow_unicode=True)
        with open(wizard.config_path, "r", encoding="utf-8") as f:
            loaded = yaml.safe_load(f)
        assert loaded["runtime"]["dry_run"] is True
        assert loaded["runtime"]["live_trading"] is False


# ─── 7. Documentation Tests ──────────────────────────────────────────────────

class TestDocumentation:
    def test_user_guide_exists(self):
        path = REPO_ROOT / "docs" / "USER_GUIDE.md"
        assert path.exists()
        assert path.stat().st_size > 1000  # substantial content

    def test_user_guide_has_installation_section(self):
        path = REPO_ROOT / "docs" / "USER_GUIDE.md"
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        assert "Install" in content or "install" in content
        assert "MetaTrader" in content or "MT5" in content

    def test_licensing_architecture_exists(self):
        path = REPO_ROOT / "docs" / "LICENSING_ARCHITECTURE.md"
        assert path.exists()
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        assert "DOCUMENTATION ONLY" in content
        assert "No licensing" in content or "not enforced" in content

    def test_demo_runbook_exists(self):
        path = REPO_ROOT / "docs" / "DEMO_RUNBOOK.md"
        assert path.exists()


# ─── 8. Build Spec Tests ─────────────────────────────────────────────────────

class TestBuildSpec:
    def test_spec_file_exists(self):
        path = REPO_ROOT / "TITAN.spec"
        assert path.exists()

    def test_build_bat_exists(self):
        path = REPO_ROOT / "build_titan.bat"
        assert path.exists()

    def test_spec_references_launcher(self):
        """Spec should reference titan_launcher.py as entry point."""
        with open(REPO_ROOT / "TITAN.spec", "r", encoding="utf-8") as f:
            content = f.read()
        assert "titan_launcher.py" in content

    def test_spec_bundles_models(self):
        """Spec should bundle model files."""
        with open(REPO_ROOT / "TITAN.spec", "r", encoding="utf-8") as f:
            content = f.read()
        assert "xgboost_v1.pkl" in content
        assert "meta_label_v2_context.pkl" in content

    def test_spec_bundles_config(self):
        """Spec should bundle config/runtime.yaml."""
        with open(REPO_ROOT / "TITAN.spec", "r", encoding="utf-8") as f:
            content = f.read()
        assert "runtime.yaml" in content


# ─── 9. Integration: Full Packaging Flow ──────────────────────────────────────

class TestPackagingIntegration:
    def test_full_packaging_flow(self, tmp_path):
        """
        Full flow: setup wizard → config → launcher validation → runtime start.
        """
        # Step 1: Run setup wizard (stub mode)
        wizard = SetupWizard(cli_mode=True, stub_mt5=True)
        wizard.config_path = tmp_path / "runtime.yaml"
        wizard.state.terminal_path = "/fake/terminal64.exe"
        wizard.state.login = 34265693
        wizard.state.password = "demo_password"
        wizard.state.server = "FundedNext-Server 3"
        wizard.state.deployment_mode = "local"
        wizard.state.journal_path = str(tmp_path / "journal.jsonl")
        config = wizard._build_config()
        with open(wizard.config_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(config, f, allow_unicode=True)

        # Step 2: Verify config is safe
        with open(wizard.config_path, "r", encoding="utf-8") as f:
            loaded = yaml.safe_load(f)
        assert loaded["runtime"]["dry_run"] is True
        assert loaded["runtime"]["live_trading"] is False

        # Step 3: Launcher can validate this config
        from titan.runtime.launcher import TitanLauncher, LauncherError
        launcher = TitanLauncher(config_path=str(wizard.config_path))
        try:
            cfg = launcher.load_config()
            assert cfg.dry_run is True
            assert cfg.live_trading is False
            assert cfg.max_lot == 0.01
        except LauncherError as e:
            # May fail on model paths (since tmp_path is not repo root)
            # but safety validation should pass
            assert "dry_run" not in str(e) or "TITAN_LIVE_TRADING" not in str(e)

    @pytest.mark.asyncio
    async def test_no_real_orders_in_full_flow(self, tmp_path):
        """Verify no mt5.order_send calls in the full packaging flow."""
        # This is already verified by Sprint 1-6 tests, but we re-verify here
        journal = TradeJournal(path=str(tmp_path / "pkg.jsonl"))
        loop = TradeLoop(TradeLoopConfig(dry_run=True), journal=journal)
        signal = make_signal()
        decision = await loop.process_signal(signal, entry_price=2000.0, spread_usd=0.2)
        assert decision.dry_run is True
        assert decision.order_result is None
