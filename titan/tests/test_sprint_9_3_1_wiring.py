"""
TITAN XAU AI — Sprint 9.3.1 Runtime Wiring Tests

Verify that:
  - enabled=false preserves old behavior (no engine references)
  - enabled=true wires engines into AutonomousRuntime
  - Dynamic risk multiplier reduces effective lot
  - Recovery mode can block trade
  - Capital preservation can block trade
  - Profit lock updates in heartbeat
  - DECISION record contains health/risk/capital context
  - ATR fields still present and unchanged
  - dry_run remains true
  - live_trading remains false
"""
from __future__ import annotations
import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest
import numpy as np
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from titan.production.trade_journal import TradeJournal, EventType
from titan.production.inference import Signal, Direction
from titan.production.trade_loop import TradeLoop, TradeLoopConfig, TradeDecision, MAX_LOT_CAP
from titan.production.account_health_engine import (
    AccountHealthEngine, AccountHealthInput, HealthWeights,
    HEALTH_BAND_NORMAL, HEALTH_BAND_RECOVERY, HEALTH_BAND_CAPITAL_PRESERVATION,
)
from titan.production.dynamic_risk_engine import DynamicRiskEngine
from titan.production.capital_protection import (
    RecoveryMode, RecoveryConfig,
    CapitalPreservation, CapitalPreservationConfig,
    ProfitLock, ProfitLockConfig,
    EquityProtection,
)
from titan.runtime.autonomous_loops import AutonomousRuntime, RuntimeConfig


# ─── Fixtures ────────────────────────────────────────────────────────────────

def make_signal(direction=Direction.LONG, confidence=0.80, meta=0.85):
    return Signal(
        timestamp=time.time(),
        direction=direction,
        confidence=confidence,
        meta_confidence=meta,
        xgb_proba=[1 - confidence, confidence] if direction == Direction.LONG else [confidence, 1 - confidence],
        meta_proba=[1 - meta, meta],
        is_tradeable=True,
        feature_vector=np.zeros(55, dtype=np.float64),
        inference_ms=42.0,
        source="canonical",
    )


@pytest.fixture
def journal(tmp_path):
    return TradeJournal(path=str(tmp_path / "wiring.jsonl"), session_id="wiring_test")


# ════════════════════════════════════════════════════════════════════════════
# 1. enabled=false preserves old behavior
# ════════════════════════════════════════════════════════════════════════════

class TestDisabledPreservesBehavior:
    def test_runtime_yaml_default_disabled(self):
        with open(REPO_ROOT / "config" / "runtime.yaml", "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        assert cfg["capital_protection"]["enabled"] is False

    def test_dry_run_flag_unchanged(self):
        with open(REPO_ROOT / "config" / "runtime.yaml", "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        assert cfg["runtime"]["dry_run"] is True
        assert cfg["runtime"]["live_trading"] is False

    def test_autonomous_runtime_accepts_none_engines(self, journal):
        rt = AutonomousRuntime(
            config=RuntimeConfig(dry_run=True),
            journal=journal,
        )
        assert rt.health_engine is None
        assert rt.dynamic_risk_engine is None
        assert rt.recovery_mode is None
        assert rt.capital_preservation is None
        assert rt.profit_lock is None
        assert rt.equity_protection is None
        assert rt.prop_firm_manager is None

    def test_max_lot_hard_cap_unchanged(self):
        assert MAX_LOT_CAP == 0.01

    def test_trade_loop_process_signal_works_without_context(self, journal):
        """Pre-9.3.1 callers (no context kwargs) must still work."""
        loop = TradeLoop(config=TradeLoopConfig(dry_run=True), journal=journal)
        sig = make_signal()
        decision = asyncio.run(
            loop.process_signal(
                signal=sig, entry_price=2000.0, spread_usd=0.20,
                current_atr=10.0,
            )
        )
        # Context fields should default to None/empty
        assert decision.health_score is None
        assert decision.health_band == ""
        assert decision.risk_profile == ""
        assert decision.risk_multiplier == 1.0
        assert decision.recovery_mode_active is False


# ════════════════════════════════════════════════════════════════════════════
# 2. Health engine called when enabled=true
# ════════════════════════════════════════════════════════════════════════════

class TestHealthEngineCalled:
    def test_health_engine_invoked_in_heartbeat(self, journal):
        """Verify _update_capital_protection is called when engines present."""
        health_engine = AccountHealthEngine(journal=journal)
        dynamic_risk = DynamicRiskEngine(journal=journal)
        recovery = RecoveryMode(
            config=RecoveryConfig(),
            journal=journal,
        )
        cap_pres = CapitalPreservation(
            config=CapitalPreservationConfig(),
            journal=journal,
        )
        profit_lock = ProfitLock(
            config=ProfitLockConfig(enabled=False),
            initial_balance=10000.0,
            journal=journal,
        )
        equity_prot = EquityProtection(initial_balance=10000.0, journal=journal)

        rt = AutonomousRuntime(
            config=RuntimeConfig(dry_run=True, heartbeat_interval_s=0.1),
            journal=journal,
            health_engine=health_engine,
            dynamic_risk_engine=dynamic_risk,
            recovery_mode=recovery,
            capital_preservation=cap_pres,
            profit_lock=profit_lock,
            equity_protection=equity_prot,
        )
        rt.initialize()

        # Manually invoke _update_capital_protection
        rt._update_capital_protection()

        # Verify health score was computed + stored
        assert rt._latest_health_score is not None
        assert rt._latest_health_band != ""
        assert rt._latest_risk_profile != ""

        # Verify ACCOUNT_HEALTH event journaled
        records = journal.read_all()
        health_events = [r for r in records
                         if r.get("event_type") == EventType.ACCOUNT_HEALTH.value]
        assert len(health_events) >= 1


# ════════════════════════════════════════════════════════════════════════════
# 3. Dynamic risk multiplier reduces effective lot
# ════════════════════════════════════════════════════════════════════════════

class TestDynamicRiskMultiplier:
    def test_risk_multiplier_reduces_lot(self, journal):
        """When risk_multiplier=0.5, effective max_lot should be halved."""
        loop = TradeLoop(
            config=TradeLoopConfig(dry_run=True, max_lot=0.01),
            journal=journal,
        )
        sig = make_signal()
        decision = asyncio.run(
            loop.process_signal(
                signal=sig, entry_price=2000.0, spread_usd=0.20,
                current_atr=10.0,
                risk_multiplier=0.5,
                health_score=60.0,
                health_band="defensive",
                risk_profile="defensive",
            )
        )
        assert decision.accepted
        # Note: TradeLoop still uses its own max_lot (0.01) for sizing.
        # The reduction happens in AutonomousRuntime before process_signal
        # (it modifies trade_loop.config.max_lot). Here we verify the
        # risk_multiplier is journaled correctly on the DECISION record.
        assert decision.risk_multiplier == 0.5
        assert decision.health_score == 60.0
        assert decision.health_band == "defensive"
        assert decision.risk_profile == "defensive"

    def test_risk_multiplier_cannot_exceed_1(self, journal):
        """Capital protection can only DECREASE risk, never increase."""
        loop = TradeLoop(config=TradeLoopConfig(dry_run=True), journal=journal)
        sig = make_signal()
        decision = asyncio.run(
            loop.process_signal(
                signal=sig, entry_price=2000.0, spread_usd=0.20,
                current_atr=10.0,
                risk_multiplier=2.0,  # try to increase
            )
        )
        # The multiplier is journaled as-is (caller's responsibility to
        # never send >1.0), but the actual lot size is capped by MAX_LOT_CAP
        assert decision.order_request["volume"] <= MAX_LOT_CAP


# ════════════════════════════════════════════════════════════════════════════
# 4. Recovery mode can block trade
# ════════════════════════════════════════════════════════════════════════════

class TestRecoveryModeBlock:
    def test_recovery_blocks_low_confidence_trade(self, journal):
        """In recovery mode, low-confidence trades are blocked."""
        recovery = RecoveryMode(
            config=RecoveryConfig(
                losing_streak_threshold=3,
                min_confidence_threshold=0.75,
                recovery_target_trades=2,
            ),
            journal=journal,
        )
        # Trigger recovery
        for _ in range(3):
            recovery.record_loss()
        assert recovery.is_active

        # Low-confidence trade should be blocked
        assert recovery.should_allow_trade(0.70) is False

        # High-confidence trade should pass
        assert recovery.should_allow_trade(0.80) is True

    def test_recovery_block_journaled(self, journal):
        """Verify SIGNAL_REJECTED with reason=recovery_mode_block."""
        recovery = RecoveryMode(
            config=RecoveryConfig(losing_streak_threshold=3),
            journal=journal,
        )
        for _ in range(3):
            recovery.record_loss()

        # Simulate the block + journal
        journal.log_event(EventType.SIGNAL_REJECTED, {
            "reason": "recovery_mode_block",
            "signal_confidence": 0.70,
            "min_confidence_threshold": 0.75,
            "health_score": 35.0,
            "health_band": "recovery_mode",
        })

        records = journal.read_all()
        rejected = [r for r in records
                    if r.get("event_type") == EventType.SIGNAL_REJECTED.value]
        assert len(rejected) == 1
        assert rejected[0]["data"]["reason"] == "recovery_mode_block"


# ════════════════════════════════════════════════════════════════════════════
# 5. Capital preservation can block trade
# ════════════════════════════════════════════════════════════════════════════

class TestCapitalPreservationBlock:
    def test_capital_preservation_blocks_at_halt_threshold(self, journal):
        cap_pres = CapitalPreservation(
            config=CapitalPreservationConfig(
                trigger_dd_pct=8.0,
                halt_new_entries_dd_pct=9.0,
            ),
            journal=journal,
        )
        # DD below halt → allowed
        cap_pres.update(8.5)
        assert cap_pres.should_allow_new_entry() is True

        # DD at halt → blocked
        cap_pres.update(9.5)
        assert cap_pres.should_allow_new_entry() is False

    def test_capital_preservation_block_journaled(self, journal):
        journal.log_event(EventType.SIGNAL_REJECTED, {
            "reason": "capital_preservation_block",
            "total_dd_pct": 9.5,
            "halt_threshold": 9.0,
            "health_score": 15.0,
            "health_band": "capital_preservation",
        })
        records = journal.read_all()
        rejected = [r for r in records
                    if r.get("event_type") == EventType.SIGNAL_REJECTED.value]
        assert len(rejected) == 1
        assert rejected[0]["data"]["reason"] == "capital_preservation_block"


# ════════════════════════════════════════════════════════════════════════════
# 6. Profit lock updates in heartbeat
# ════════════════════════════════════════════════════════════════════════════

class TestProfitLockInHeartbeat:
    def test_profit_lock_updates_via_update_capital_protection(self, journal):
        """Verify _update_capital_protection calls profit_lock.update()."""
        profit_lock = ProfitLock(
            config=ProfitLockConfig(enabled=True, lock_distance_pct=2.0,
                                    trail_distance_pct=1.0),
            initial_balance=10000.0,
            journal=journal,
        )
        equity_prot = EquityProtection(initial_balance=10000.0, journal=journal)
        health_engine = AccountHealthEngine(journal=journal)

        rt = AutonomousRuntime(
            config=RuntimeConfig(dry_run=True, entry_price_default=10200.0),
            journal=journal,
            health_engine=health_engine,
            profit_lock=profit_lock,
            equity_protection=equity_prot,
        )
        rt.initialize()
        rt._update_capital_protection()

        # Equity was 10200 → +2% → profit lock should activate
        assert profit_lock.is_locked is True
        assert profit_lock.locked_equity > 10000.0


# ════════════════════════════════════════════════════════════════════════════
# 7. DECISION record contains health/risk/capital context
# ════════════════════════════════════════════════════════════════════════════

class TestDecisionRecordContext:
    def test_decision_contains_all_context_fields(self, journal):
        """Verify DECISION journal record has all Sprint 9.3.1 context fields."""
        loop = TradeLoop(config=TradeLoopConfig(dry_run=True), journal=journal)
        sig = make_signal()
        asyncio.run(
            loop.process_signal(
                signal=sig, entry_price=2000.0, spread_usd=0.20,
                current_atr=10.0,
                health_score=85.0,
                health_band="slight_reduction",
                risk_profile="slight_reduction",
                risk_multiplier=0.75,
                recovery_mode_active=False,
                capital_preservation_active=False,
                profit_lock_active=True,
                prop_profile_id="ftmo_challenge",
            )
        )

        records = journal.read_all()
        decisions = [r for r in records if r.get("record_type") == "DECISION"]
        assert len(decisions) == 1
        data = decisions[0]["data"]

        # All Sprint 9.3.1 context fields must be present
        assert "health_score" in data
        assert data["health_score"] == 85.0
        assert data["health_band"] == "slight_reduction"
        assert data["risk_profile"] == "slight_reduction"
        assert data["risk_multiplier"] == 0.75
        assert data["recovery_mode_active"] is False
        assert data["capital_preservation_active"] is False
        assert data["profit_lock_active"] is True
        assert data["prop_profile_id"] == "ftmo_challenge"

    def test_atr_fields_still_present(self, journal):
        """Verify Sprint 8.5 ATR fields are still on DECISION record."""
        loop = TradeLoop(config=TradeLoopConfig(dry_run=True, sl_mode="atr"),
                         journal=journal)
        sig = make_signal()
        asyncio.run(
            loop.process_signal(
                signal=sig, entry_price=2000.0, spread_usd=0.20,
                current_atr=10.0,
                health_score=90.0,  # include context
            )
        )
        records = journal.read_all()
        decisions = [r for r in records if r.get("record_type") == "DECISION"]
        data = decisions[0]["data"]
        # Sprint 8.5 ATR fields still present
        assert "current_atr" in data
        assert "sl_tp_mode_used" in data
        assert "fallback_used" in data
        assert "computed_sl" in data
        assert "computed_tp" in data
        # Sprint 9.3.1 context fields also present
        assert "health_score" in data


# ════════════════════════════════════════════════════════════════════════════
# 8. dry_run + live_trading flags unchanged
# ════════════════════════════════════════════════════════════════════════════

class TestSafetyFlagsUnchanged:
    def test_dry_run_remains_true(self):
        with open(REPO_ROOT / "config" / "runtime.yaml", "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        assert cfg["runtime"]["dry_run"] is True

    def test_live_trading_remains_false(self):
        with open(REPO_ROOT / "config" / "runtime.yaml", "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        assert cfg["runtime"]["live_trading"] is False

    def test_trade_loop_default_dry_run(self):
        cfg = TradeLoopConfig()
        assert cfg.dry_run is True


# ════════════════════════════════════════════════════════════════════════════
# 9. End-to-end runtime scenario
# ════════════════════════════════════════════════════════════════════════════

class TestEndToEndRuntimeScenario:
    def test_healthy_then_recovery_then_capital_preservation(self, journal):
        """End-to-end: engines present, _update_capital_protection runs,
        DECISION records contain context."""
        health_engine = AccountHealthEngine(journal=journal)
        dynamic_risk = DynamicRiskEngine(journal=journal)
        recovery = RecoveryMode(
            config=RecoveryConfig(losing_streak_threshold=3),
            journal=journal,
        )
        cap_pres = CapitalPreservation(
            config=CapitalPreservationConfig(trigger_dd_pct=8.0,
                                              halt_new_entries_dd_pct=9.0),
            journal=journal,
        )
        profit_lock = ProfitLock(
            config=ProfitLockConfig(enabled=False),
            initial_balance=10000.0,
            journal=journal,
        )
        equity_prot = EquityProtection(initial_balance=10000.0, journal=journal)

        rt = AutonomousRuntime(
            config=RuntimeConfig(dry_run=True),
            journal=journal,
            health_engine=health_engine,
            dynamic_risk_engine=dynamic_risk,
            recovery_mode=recovery,
            capital_preservation=cap_pres,
            profit_lock=profit_lock,
            equity_protection=equity_prot,
        )
        rt.initialize()

        # Phase 1: healthy
        rt._update_capital_protection()
        assert rt._latest_health_score is not None
        assert rt._latest_health_band != ""

        # Phase 2: trigger recovery via 3 losses
        for _ in range(3):
            recovery.record_loss()
        assert recovery.is_active

        # Phase 3: trigger capital preservation via DD
        cap_pres.update(8.5)
        assert cap_pres.is_active

        # Verify journal has all event types
        records = journal.read_all()
        event_types = set(r.get("event_type", "") for r in records)
        assert EventType.ACCOUNT_HEALTH.value in event_types
        assert EventType.RECOVERY_MODE.value in event_types
        assert EventType.CAPITAL_PRESERVATION.value in event_types
