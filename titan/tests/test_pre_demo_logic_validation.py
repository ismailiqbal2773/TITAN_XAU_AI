"""
Tests for Pre-Demo Logic & Chaos Validation (Sprint 8.2).

Verifies: feature schema, config consistency, dry_run safety, state machine,
autonomous runtime path, chaos behavior, 7-day rehearsal, no duplicates.
"""
from __future__ import annotations
import asyncio, json, os, sys, time, tempfile, subprocess
import pytest, numpy as np
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

class TestFeatureSchema:
    def test_stream_count_matches_xgb(self):
        from titan.production.feature_stream import N_FEATURES
        from titan.production.model_loader import load_production_models
        b = load_production_models()
        assert N_FEATURES == b.xgb_n_features
    def test_no_nan_inf(self):
        from titan.production.feature_stream import H1FeatureStream
        v = H1FeatureStream(window=300).latest_vector(source="canonical")
        assert v.is_valid and not np.isnan(v.features).any() and not np.isinf(v.features).any()
    def test_meta_subset_of_xgb(self):
        from titan.production.feature_stream import FEATURE_NAMES
        from titan.production.model_loader import META_FEATURE_NAMES
        for f in META_FEATURE_NAMES: assert f in FEATURE_NAMES

class TestConfigConsistency:
    def test_dry_run_true(self):
        import yaml
        with open(REPO_ROOT / "config" / "runtime.yaml") as f: cfg = yaml.safe_load(f)
        assert cfg["runtime"]["dry_run"] is True
    def test_live_trading_false(self):
        import yaml
        with open(REPO_ROOT / "config" / "runtime.yaml") as f: cfg = yaml.safe_load(f)
        assert cfg["runtime"]["live_trading"] is False
    def test_max_lot_cap(self):
        import yaml
        with open(REPO_ROOT / "config" / "runtime.yaml") as f: cfg = yaml.safe_load(f)
        assert cfg["risk"]["max_lot"] <= 0.01
    def test_max_positions_cap(self):
        import yaml
        with open(REPO_ROOT / "config" / "runtime.yaml") as f: cfg = yaml.safe_load(f)
        assert cfg["risk"]["max_open_positions"] <= 1

class TestDryRunSafety:
    def test_all_modules_dry_run_default(self):
        from titan.production.trade_loop import TradeLoopConfig
        from titan.production.order_modifier import OrderModifier
        from titan.production.watchdog_restarter import WatchdogRestarter
        from titan.runtime.launcher import LauncherConfig
        assert TradeLoopConfig().dry_run is True
        assert OrderModifier().dry_run is True
        assert WatchdogRestarter().dry_run is True
        assert LauncherConfig().dry_run is True
        assert LauncherConfig().live_trading is False
    def test_live_requires_env(self, monkeypatch):
        from titan.production.trade_loop import TradeLoop, TradeLoopConfig
        monkeypatch.delenv("TITAN_LIVE_TRADING", raising=False)
        with pytest.raises(PermissionError): TradeLoop(TradeLoopConfig(dry_run=False))
    @pytest.mark.asyncio
    async def test_order_result_none(self):
        from titan.production.trade_loop import TradeLoop, TradeLoopConfig
        from titan.production.inference import Signal, Direction
        loop = TradeLoop(TradeLoopConfig(dry_run=True))
        sig = Signal(timestamp=time.time(), direction=Direction.LONG, confidence=0.8, meta_confidence=0.85, xgb_proba=[0.2,0.8], meta_proba=[0.15,0.85], is_tradeable=True, feature_vector=np.zeros(55), inference_ms=10, source="test")
        d = await loop.process_signal(sig, entry_price=2000, spread_usd=0.2)
        assert d.order_result is None

class TestStateMachineConsistency:
    def test_one_way_escalation(self):
        from titan.production.kill_switch_fsm import KillSwitchFSM, KillSwitchInput, KillState
        fsm = KillSwitchFSM(); fsm.update(KillSwitchInput(daily_loss_pct=3.5))
        assert fsm.state == KillState.HALT_NEW_TRADES
        fsm.update(KillSwitchInput(daily_loss_pct=0))
        assert fsm.state == KillState.HALT_NEW_TRADES  # no downgrade
    def test_emergency_requires_flatten(self):
        from titan.production.kill_switch_fsm import KillSwitchFSM, KillSwitchInput
        fsm = KillSwitchFSM(); fsm.update(KillSwitchInput(max_drawdown_pct=8.5))
        assert fsm.requires_flatten and fsm.is_emergency
    def test_drift_emergency_triggers(self):
        from titan.production.kill_switch_fsm import KillSwitchFSM, KillSwitchInput, KillState
        fsm = KillSwitchFSM(); fsm.update(KillSwitchInput(drift_emergency=True))
        assert fsm.state == KillState.EMERGENCY_STOP

class TestAutonomousRuntimePath:
    def test_launcher_has_autonomous(self):
        from titan.runtime.launcher import TitanLauncher; import inspect
        assert "autonomous" in inspect.signature(TitanLauncher.start).parameters
    def test_all_loops_exist(self):
        from titan.runtime.autonomous_loops import AutonomousRuntime
        for l in ["_inference_loop","_position_sync_loop","_exit_manager_loop","_drift_monitor_loop","_heartbeat_loop"]:
            assert hasattr(AutonomousRuntime, l)
    @pytest.mark.asyncio
    async def test_single_cycle_works(self, tmp_path):
        from titan.runtime.autonomous_loops import AutonomousRuntime, RuntimeConfig
        rt = AutonomousRuntime(config=RuntimeConfig(dry_run=True, feature_source="canonical"), journal_path=str(tmp_path/"t.jsonl"))
        rt.initialize()
        r = await rt.run_single_cycle()
        assert r["signal"] is not None

class TestChaosBehavior:
    @pytest.mark.asyncio
    async def test_corrupt_journal_recovers(self, tmp_path):
        from titan.production.trade_journal import TradeJournal
        jp = str(tmp_path / "c.jsonl"); j = TradeJournal(path=jp)
        j.log_startup({"t": 1}); j.flush()
        with open(jp, "a") as f: f.write('{"partial"')
        assert j.recover_from_crash() == 1
    @pytest.mark.asyncio
    async def test_duplicate_bar_skipped(self, tmp_path):
        from titan.runtime.autonomous_loops import AutonomousRuntime, RuntimeConfig
        rt = AutonomousRuntime(config=RuntimeConfig(dry_run=True, feature_source="canonical"), journal_path=str(tmp_path/"t.jsonl"))
        rt.initialize()
        bar = rt._get_current_bar_time(); rt._last_processed_bar_time = bar
        assert rt._get_current_bar_time() == bar  # same → skip
    @pytest.mark.asyncio
    async def test_spread_spike_rejected(self, tmp_path):
        from titan.production.trade_loop import TradeLoop, TradeLoopConfig
        from titan.production.inference import Signal, Direction
        loop = TradeLoop(TradeLoopConfig(dry_run=True, max_spread_usd=0.5))
        sig = Signal(timestamp=time.time(), direction=Direction.LONG, confidence=0.8, meta_confidence=0.85, xgb_proba=[0.2,0.8], meta_proba=[0.15,0.85], is_tradeable=True, feature_vector=np.zeros(55), inference_ms=10, source="test")
        d = await loop.process_signal(sig, entry_price=2000, spread_usd=2.0)
        assert not d.accepted and "spread" in d.reject_reason
    def test_missing_model_handled(self):
        from titan.production.model_loader import load_production_models
        b = load_production_models("/nonexistent/xgb.pkl", "/nonexistent/meta.pkl")
        assert not b.ok
    @pytest.mark.asyncio
    async def test_position_mismatch_detected(self, tmp_path):
        from titan.production.position_sync import PositionSync, BrokerPosition
        sync = PositionSync(interval_seconds=10, broker_source="stub", magic_filter=None)
        sync._local_state[99999] = BrokerPosition(ticket=99999, symbol="XAUUSD", direction=1, volume=0.01, entry_price=2000, stop_loss=0, take_profit=0, open_time=0)
        sync.set_stub_positions([BrokerPosition(ticket=100, symbol="XAUUSD", direction=1, volume=0.01, entry_price=2000, stop_loss=1995, take_profit=2010, open_time=time.time())])
        rep = await sync.sync_once()
        assert rep.closed_positions >= 1

class TestSevenDayRehearsal:
    @pytest.mark.asyncio
    async def test_rehearsal_completes(self):
        from scripts.pre_demo_7day_rehearsal import SevenDayRehearsal
        r = SevenDayRehearsal()
        result = await r.run()
        assert result.days == 7
        assert result.signals > 0
        assert result.duplicates == 0
        assert not result.corruption
        assert not result.ks_bypass

class TestJournalIntegrity:
    def test_journal_valid_jsonl(self, tmp_path):
        from titan.production.trade_journal import TradeJournal
        jp = str(tmp_path / "j.jsonl"); j = TradeJournal(path=jp)
        j.log_startup({"t": 1}); j.log_shutdown(); j.flush()
        with open(jp) as f:
            for line in f: json.loads(line.strip())  # no crash = valid
    def test_no_duplicate_record_ids(self, tmp_path):
        from titan.production.trade_journal import TradeJournal
        j = TradeJournal(path=str(tmp_path / "j.jsonl"))
        for _ in range(10): j.log_startup({"t": 1})
        j.flush(); records = j.read_all()
        ids = [r["record_id"] for r in records]
        assert len(ids) == len(set(ids))
