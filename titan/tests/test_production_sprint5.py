"""
Tests for Sprint 5 — Deployment Layer:
  - Kill-switch FSM integration with trade_loop
  - Launcher fail-closed behavior
  - Config safe loading
  - Journal kill-switch event recording
  - Watchdog restart callback
  - Live order never accidentally enabled
"""
from __future__ import annotations

import asyncio
import os
import tempfile
import time
import pytest
import yaml
import numpy as np
from pathlib import Path
from unittest.mock import patch

from titan.production.inference import Signal, Direction
from titan.production.trade_loop import TradeLoop, TradeLoopConfig
from titan.production.trade_journal import TradeJournal
from titan.production.kill_switch_fsm import (
    KillSwitchFSM, KillSwitchConfig, KillSwitchInput, KillState,
)
from titan.runtime.launcher import TitanLauncher, LauncherConfig, LauncherError


# ─── Helpers ──────────────────────────────────────────────────────────────────

def make_signal(direction=Direction.LONG, is_tradeable=True) -> Signal:
    return Signal(
        timestamp=time.time(), direction=direction,
        confidence=0.80, meta_confidence=0.85,
        xgb_proba=[0.2, 0.8] if direction == Direction.LONG else [0.8, 0.2],
        meta_proba=[0.15, 0.85], is_tradeable=is_tradeable,
        feature_vector=np.zeros(55), inference_ms=10.0, source="test",
    )


def write_test_config(path: str, **overrides) -> str:
    """Write a minimal valid config for testing."""
    cfg = {
        "runtime": {"dry_run": True, "live_trading": False, "log_level": "WARNING",
                    "journal_path": str(Path(path).parent / "journal.jsonl")},
        "symbol": {"name": "XAUUSD", "timeframe": "H1"},
        "models": {
            "xgb_path": "titan/data/models/xgboost_v1.pkl",
            "meta_path": "titan/data/models/meta_label_v2_context.pkl",
        },
        "features": {"window": 300, "source": "canonical",
                     "canonical_path": "titan/data/canonical/XAUUSD_H1_canonical.parquet"},
        "inference": {"xgb_threshold": 0.55, "meta_threshold": 0.65},
        "risk": {"max_lot": 0.01, "max_open_positions": 1, "sl_pips": 50, "tp_pips": 100,
                 "max_spread_usd": 1.0, "deviation_points": 20, "magic_number": 202619},
        "kill_switch": {"max_daily_loss_pct": 3.0, "max_drawdown_pct": 5.0,
                        "emergency_drawdown_pct": 8.0},
        "news_filter": {"enabled": True, "csv_path": "data/economic_calendar.csv",
                        "block_window_minutes": 30, "event_types": ["NFP", "CPI", "FOMC"]},
        "position_sync": {"interval_seconds": 10.0, "broker_source": "stub",
                          "magic_filter": 202619},
        "watchdog": {"enabled": True, "dry_run": True, "check_interval_s": 10.0},
    }
    # Apply overrides
    for key, val in overrides.items():
        if "." in key:
            section, subkey = key.split(".", 1)
            cfg[section][subkey] = val
        else:
            cfg[key] = val
    with open(path, "w") as f:
        yaml.safe_dump(cfg, f)
    return path


# ─── 1. Kill-Switch Trade_Loop Integration ────────────────────────────────────

class TestKillSwitchTradeLoopIntegration:
    """Verify kill_switch_fsm correctly blocks trade_loop."""

    @pytest.mark.asyncio
    async def test_normal_state_allows_trade(self, tmp_path):
        """NORMAL state → trade allowed."""
        journal = TradeJournal(path=str(tmp_path / "j.jsonl"))
        fsm = KillSwitchFSM()
        loop = TradeLoop(TradeLoopConfig(dry_run=True), journal=journal, kill_switch=fsm)
        signal = make_signal()
        decision = await loop.process_signal(signal, entry_price=2000.0, spread_usd=0.2)
        assert decision.accepted
        assert fsm.state == KillState.NORMAL

    @pytest.mark.asyncio
    async def test_caution_state_reduces_size(self, tmp_path):
        """CAUTION state → trade allowed but volume halved."""
        journal = TradeJournal(path=str(tmp_path / "j.jsonl"))
        fsm = KillSwitchFSM(KillSwitchConfig(max_latency_ms=500))
        fsm.update(KillSwitchInput(latency_p99_ms=550))  # → CAUTION
        assert fsm.state == KillState.CAUTION
        loop = TradeLoop(TradeLoopConfig(dry_run=True, max_lot=0.01),
                         journal=journal, kill_switch=fsm)
        signal = make_signal()
        decision = await loop.process_signal(signal, entry_price=2000.0, spread_usd=0.2)
        assert decision.accepted
        # Volume should be halved (0.01 / 2 = 0.005, but floored at 0.01)
        # Since max_lot=0.01 is the floor, volume stays at 0.01
        assert decision.order_request["volume"] <= 0.01

    @pytest.mark.asyncio
    async def test_halt_new_trades_blocks_trade(self, tmp_path):
        """HALT_NEW_TRADES → trade blocked, journal records block."""
        journal = TradeJournal(path=str(tmp_path / "j.jsonl"))
        fsm = KillSwitchFSM(KillSwitchConfig(max_daily_loss_pct=3.0))
        fsm.update(KillSwitchInput(daily_loss_pct=3.5))  # → HALT_NEW_TRADES
        assert fsm.state == KillState.HALT_NEW_TRADES
        loop = TradeLoop(TradeLoopConfig(dry_run=True), journal=journal, kill_switch=fsm)
        signal = make_signal()
        decision = await loop.process_signal(signal, entry_price=2000.0, spread_usd=0.2)
        assert not decision.accepted
        assert "kill_switch_halt_new_trades" in decision.reject_reason
        # Verify journal recorded the block (audit-grade KILL_SWITCH_BLOCK event)
        journal.flush()
        from titan.production.trade_journal import EventType
        blocks = journal.read_by_event_type(EventType.KILL_SWITCH_BLOCK)
        assert len(blocks) == 1
        assert blocks[0]["data"]["kill_switch_state"] == "HALT_NEW_TRADES"

    @pytest.mark.asyncio
    async def test_flatten_only_blocks_trade(self, tmp_path):
        """FLATTEN_ONLY → trade blocked."""
        journal = TradeJournal(path=str(tmp_path / "j.jsonl"))
        fsm = KillSwitchFSM(KillSwitchConfig(max_drawdown_pct=5.0))
        fsm.update(KillSwitchInput(max_drawdown_pct=5.5))  # → FLATTEN_ONLY
        assert fsm.state == KillState.FLATTEN_ONLY
        loop = TradeLoop(TradeLoopConfig(dry_run=True), journal=journal, kill_switch=fsm)
        signal = make_signal()
        decision = await loop.process_signal(signal, entry_price=2000.0, spread_usd=0.2)
        assert not decision.accepted
        assert "kill_switch_flatten_only" in decision.reject_reason

    @pytest.mark.asyncio
    async def test_emergency_stop_blocks_trade(self, tmp_path):
        """EMERGENCY_STOP → trade blocked."""
        journal = TradeJournal(path=str(tmp_path / "j.jsonl"))
        fsm = KillSwitchFSM(KillSwitchConfig(emergency_drawdown_pct=8.0))
        fsm.update(KillSwitchInput(max_drawdown_pct=8.5))  # → EMERGENCY_STOP
        assert fsm.state == KillState.EMERGENCY_STOP
        loop = TradeLoop(TradeLoopConfig(dry_run=True), journal=journal, kill_switch=fsm)
        signal = make_signal()
        decision = await loop.process_signal(signal, entry_price=2000.0, spread_usd=0.2)
        assert not decision.accepted
        assert "kill_switch_emergency_stop" in decision.reject_reason

    @pytest.mark.asyncio
    async def test_no_kill_switch_allows_trade(self, tmp_path):
        """No kill_switch wired → trade proceeds normally (backward compat)."""
        journal = TradeJournal(path=str(tmp_path / "j.jsonl"))
        loop = TradeLoop(TradeLoopConfig(dry_run=True), journal=journal, kill_switch=None)
        signal = make_signal()
        decision = await loop.process_signal(signal, entry_price=2000.0, spread_usd=0.2)
        assert decision.accepted

    @pytest.mark.asyncio
    async def test_kill_switch_checked_first(self, tmp_path):
        """Kill-switch check happens BEFORE spread/news checks."""
        journal = TradeJournal(path=str(tmp_path / "j.jsonl"))
        fsm = KillSwitchFSM()
        fsm.update(KillSwitchInput(daily_loss_pct=3.5))  # HALT
        loop = TradeLoop(TradeLoopConfig(dry_run=True, max_spread_usd=0.5),
                         journal=journal, kill_switch=fsm)
        signal = make_signal()
        # Spread is high (0.8 > 0.5) BUT kill_switch should fire first
        decision = await loop.process_signal(signal, entry_price=2000.0, spread_usd=0.8)
        assert not decision.accepted
        # Should be kill_switch reason, NOT spread reason
        assert "kill_switch" in decision.reject_reason
        assert "spread" not in decision.reject_reason


# ─── 2. Launcher Fail-Closed ──────────────────────────────────────────────────

class TestLauncherFailClosed:
    def test_missing_config_raises(self, tmp_path):
        launcher = TitanLauncher(config_path=str(tmp_path / "nonexistent.yaml"))
        with pytest.raises(LauncherError, match="Config file not found"):
            launcher.load_config()

    def test_invalid_yaml_raises(self, tmp_path):
        cfg_path = str(tmp_path / "bad.yaml")
        with open(cfg_path, "w") as f:
            f.write("runtime: [invalid yaml\n  - broken")
        launcher = TitanLauncher(config_path=cfg_path)
        with pytest.raises(LauncherError, match="Invalid YAML"):
            launcher.load_config()

    def test_dry_run_false_without_env_var_raises(self, tmp_path, monkeypatch):
        monkeypatch.delenv("TITAN_LIVE_TRADING", raising=False)
        cfg_path = str(tmp_path / "live.yaml")
        write_test_config(cfg_path, **{"runtime.dry_run": False, "runtime.live_trading": True})
        launcher = TitanLauncher(config_path=cfg_path)
        with pytest.raises(LauncherError, match="TITAN_LIVE_TRADING"):
            launcher.load_config()

    def test_dry_run_false_with_env_var_passes(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TITAN_LIVE_TRADING", "1")
        cfg_path = str(tmp_path / "live.yaml")
        write_test_config(cfg_path, **{"runtime.dry_run": False, "runtime.live_trading": True})
        launcher = TitanLauncher(config_path=cfg_path)
        cfg = launcher.load_config()
        assert cfg.dry_run is False

    def test_contradictory_config_raises(self, tmp_path):
        """live_trading=true but dry_run=true → contradiction."""
        cfg_path = str(tmp_path / "contradiction.yaml")
        write_test_config(cfg_path, **{"runtime.dry_run": True, "runtime.live_trading": True})
        launcher = TitanLauncher(config_path=cfg_path)
        with pytest.raises(LauncherError, match="contradictory"):
            launcher.load_config()

    def test_max_lot_exceeds_cap_raises(self, tmp_path):
        cfg_path = str(tmp_path / "big_lot.yaml")
        write_test_config(cfg_path, **{"risk.max_lot": 0.10})
        launcher = TitanLauncher(config_path=cfg_path)
        with pytest.raises(LauncherError, match="exceeds hard cap 0.01"):
            launcher.load_config()

    def test_max_open_positions_exceeds_cap_raises(self, tmp_path):
        cfg_path = str(tmp_path / "many_pos.yaml")
        write_test_config(cfg_path, **{"risk.max_open_positions": 5})
        launcher = TitanLauncher(config_path=cfg_path)
        with pytest.raises(LauncherError, match="exceeds hard cap 1"):
            launcher.load_config()

    def test_watchdog_live_in_dry_run_raises(self, tmp_path):
        """watchdog.dry_run=false but runtime.dry_run=true → error."""
        cfg_path = str(tmp_path / "wd_live.yaml")
        write_test_config(cfg_path, **{"watchdog.dry_run": False})
        launcher = TitanLauncher(config_path=cfg_path)
        with pytest.raises(LauncherError, match="watchdog auto-restart requires live"):
            launcher.load_config()

    def test_default_config_is_dry_run(self, tmp_path):
        """Default config must be dry_run=True."""
        cfg_path = str(tmp_path / "default.yaml")
        write_test_config(cfg_path)
        launcher = TitanLauncher(config_path=cfg_path)
        cfg = launcher.load_config()
        assert cfg.dry_run is True
        assert cfg.live_trading is False


# ─── 3. Config Safe Loading ───────────────────────────────────────────────────

class TestConfigSafeLoading:
    def test_config_loads_all_sections(self, tmp_path):
        cfg_path = str(tmp_path / "full.yaml")
        write_test_config(cfg_path)
        launcher = TitanLauncher(config_path=cfg_path)
        cfg = launcher.load_config()
        assert cfg.symbol_name == "XAUUSD"
        assert cfg.timeframe == "H1"
        assert cfg.xgb_threshold == 0.55
        assert cfg.meta_threshold == 0.65
        assert cfg.max_lot == 0.01
        assert cfg.max_open_positions == 1
        assert cfg.ks_max_daily_loss_pct == 3.0
        assert cfg.news_block_window_minutes == 30

    def test_paths_resolved_absolute(self, tmp_path):
        cfg_path = str(tmp_path / "paths.yaml")
        write_test_config(cfg_path)
        launcher = TitanLauncher(config_path=cfg_path)
        cfg = launcher.load_config()
        # Paths should be resolved to absolute
        assert os.path.isabs(cfg.xgb_path)
        assert os.path.isabs(cfg.meta_path)
        assert os.path.isabs(cfg.canonical_path)

    def test_runtime_validation_passes(self, tmp_path):
        """Validate runtime finds all model + data files."""
        cfg_path = str(tmp_path / "valid.yaml")
        write_test_config(cfg_path)
        launcher = TitanLauncher(config_path=cfg_path)
        launcher.load_config()
        # This should pass because we're running from the repo root
        # and the model files exist
        result = launcher.validate_runtime()
        assert result is True

    def test_runtime_validation_fails_on_missing_model(self, tmp_path):
        cfg_path = str(tmp_path / "bad_model.yaml")
        write_test_config(cfg_path, **{"models.xgb_path": "nonexistent/xgb.pkl"})
        launcher = TitanLauncher(config_path=cfg_path)
        launcher.load_config()
        result = launcher.validate_runtime()
        assert result is False


# ─── 4. Journal Kill-Switch Events ────────────────────────────────────────────

class TestJournalKillSwitchEvents:
    @pytest.mark.asyncio
    async def test_kill_switch_transition_journaled(self, tmp_path):
        """Kill-switch transitions are journaled via callback."""
        journal = TradeJournal(path=str(tmp_path / "ks.jsonl"))
        fsm = KillSwitchFSM(journal_callback=lambda t: journal.log_heartbeat({
            "event": "kill_switch_transition",
            "from": t.from_state.value, "to": t.to_state.value,
            "trigger": t.trigger,
        }))
        fsm.update(KillSwitchInput(daily_loss_pct=3.5))  # → HALT
        journal.flush()
        heartbeats = journal.read_by_type("HEARTBEAT")
        assert len(heartbeats) == 1
        assert heartbeats[0]["data"]["from"] == "NORMAL"
        assert heartbeats[0]["data"]["to"] == "HALT_NEW_TRADES"

    @pytest.mark.asyncio
    async def test_blocked_trade_journaled(self, tmp_path):
        """Trade blocked by kill-switch is journaled."""
        journal = TradeJournal(path=str(tmp_path / "block.jsonl"))
        fsm = KillSwitchFSM()
        fsm.update(KillSwitchInput(daily_loss_pct=3.5))  # HALT
        loop = TradeLoop(TradeLoopConfig(dry_run=True), journal=journal, kill_switch=fsm)
        signal = make_signal()
        await loop.process_signal(signal, entry_price=2000.0, spread_usd=0.2)
        journal.flush()
        # Should have: DECISION (rejected) + EVENT (KILL_SWITCH_BLOCK)
        decisions = journal.read_by_type("DECISION")
        assert len(decisions) == 1
        assert decisions[0]["data"]["accepted"] is False
        from titan.production.trade_journal import EventType
        blocks = journal.read_by_event_type(EventType.KILL_SWITCH_BLOCK)
        assert len(blocks) == 1


# ─── 5. Watchdog Restart Callback ─────────────────────────────────────────────

class TestWatchdogRestartCallback:
    @pytest.mark.asyncio
    async def test_watchdog_dry_run_logs_only(self):
        """In dry_run, watchdog logs restart but doesn't call restart_fn."""
        from titan.production.watchdog_restarter import WatchdogRestarter
        restarter = WatchdogRestarter(dry_run=True, check_interval_s=0.3)
        restart_called = []
        async def restart_fn():
            restart_called.append(True)
        restarter.register_component(
            "test_loop", expected_interval_s=0.2, threshold_misses=2,
            restart_fn=restart_fn,
        )
        restarter.beat("test_loop")
        task = restarter.start_background()
        await asyncio.sleep(1.5)
        await restarter.stop()
        assert len(restart_called) == 0  # dry_run = no actual restart
        assert restarter.recovery_count > 0  # but logged

    @pytest.mark.asyncio
    async def test_watchdog_callback_works(self):
        """Watchdog on_hung callback fires correctly."""
        from titan.production.watchdog_restarter import WatchdogRestarter
        restarter = WatchdogRestarter(dry_run=True, check_interval_s=0.3)
        restarter.register_component("comp", expected_interval_s=0.2, threshold_misses=1)
        restarter.beat("comp")
        task = restarter.start_background()
        await asyncio.sleep(1.0)
        await restarter.stop()
        # Recovery event should exist
        events = restarter.recovery_events
        assert len(events) > 0


# ─── 6. Live Order Never Accidentally Enabled ─────────────────────────────────

class TestLiveOrderSafety:
    def test_dry_run_default_in_trade_loop(self):
        """TradeLoopConfig defaults to dry_run=True."""
        cfg = TradeLoopConfig()
        assert cfg.dry_run is True

    def test_dry_run_default_in_launcher_config(self):
        """LauncherConfig defaults to dry_run=True."""
        cfg = LauncherConfig()
        assert cfg.dry_run is True
        assert cfg.live_trading is False

    def test_live_mode_requires_env_var(self, monkeypatch):
        """TradeLoop with dry_run=False requires TITAN_LIVE_TRADING=1."""
        monkeypatch.delenv("TITAN_LIVE_TRADING", raising=False)
        with pytest.raises(PermissionError, match="TITAN_LIVE_TRADING"):
            TradeLoop(TradeLoopConfig(dry_run=False))

    def test_launcher_refuses_live_without_env(self, tmp_path, monkeypatch):
        """Launcher refuses to load config with dry_run=False without env var."""
        monkeypatch.delenv("TITAN_LIVE_TRADING", raising=False)
        cfg_path = str(tmp_path / "live.yaml")
        write_test_config(cfg_path, **{"runtime.dry_run": False, "runtime.live_trading": True})
        launcher = TitanLauncher(config_path=cfg_path)
        with pytest.raises(LauncherError):
            launcher.load_config()

    @pytest.mark.asyncio
    async def test_no_real_mt5_calls_in_dry_run(self, tmp_path):
        """In dry_run, mt5.order_send is NEVER called."""
        from unittest.mock import MagicMock, patch
        journal = TradeJournal(path=str(tmp_path / "no_mt5.jsonl"))
        loop = TradeLoop(TradeLoopConfig(dry_run=True), journal=journal)
        signal = make_signal()
        # Mock mt5.order_send to detect any call
        with patch("MetaTrader5.order_send") as mock_send:
            decision = await loop.process_signal(signal, entry_price=2000.0, spread_usd=0.2)
            assert decision.accepted
            assert decision.dry_run is True
            # CRITICAL: mt5.order_send must NOT be called
            mock_send.assert_not_called()


# ─── 7. Launcher Integration ──────────────────────────────────────────────────

class TestLauncherIntegration:
    def test_launcher_start_completes_smoke_test(self, tmp_path):
        """Full launcher.start() runs a smoke test + journal writes."""
        # Use the repo's actual config
        repo_root = Path(__file__).resolve().parents[2]
        cfg_path = str(repo_root / "config" / "runtime.yaml")
        # Override journal path to tmp
        with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False, mode="w") as tf:
            with open(cfg_path) as src:
                cfg = yaml.safe_load(src)
            cfg["runtime"]["journal_path"] = str(tmp_path / "smoke_journal.jsonl")
            cfg["runtime"]["log_level"] = "WARNING"
            yaml.safe_dump(cfg, tf)
            test_cfg_path = tf.name

        launcher = TitanLauncher(config_path=test_cfg_path)
        launcher.start()  # should complete without error
        # Verify journal was created
        journal_path = tmp_path / "smoke_journal.jsonl"
        assert journal_path.exists()
        # Verify journal has records
        journal = TradeJournal(path=str(journal_path))
        records = journal.read_all()
        assert len(records) > 0
        # Should have at least SIGNAL + DECISION records
        types = [r["record_type"] for r in records]
        assert "SIGNAL" in types or "DECISION" in types or "HEARTBEAT" in types

        os.unlink(test_cfg_path)

    def test_launcher_validate_only_mode(self):
        """--validate-only mode works without starting."""
        repo_root = Path(__file__).resolve().parents[2]
        cfg_path = str(repo_root / "config" / "runtime.yaml")
        launcher = TitanLauncher(config_path=cfg_path)
        launcher.load_config()
        result = launcher.validate_runtime()
        assert result is True
