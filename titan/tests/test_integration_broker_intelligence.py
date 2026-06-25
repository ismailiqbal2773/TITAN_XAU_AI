"""
TITAN XAU AI — Sprint 9.5 Integration Tests

Verify:
  - broker_intelligence.enabled=false preserves old behavior
  - dry_run + live_trading flags unchanged
  - All engines optional (None defaults)
  - End-to-end: detect → score → select profile → adapt risk → protect
"""
from __future__ import annotations
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


class TestDisabledDefault:
    """When broker_intelligence.enabled=false, no behavior change."""

    def test_runtime_yaml_default_disabled(self):
        with open(REPO_ROOT / "config" / "runtime.yaml", "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        assert cfg["broker_intelligence"]["enabled"] is False

    def test_dry_run_flag_unchanged(self):
        with open(REPO_ROOT / "config" / "runtime.yaml", "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        assert cfg["runtime"]["dry_run"] is True
        assert cfg["runtime"]["live_trading"] is False

    def test_max_lot_hard_cap_unchanged(self):
        from titan.production.trade_loop import MAX_LOT_CAP
        assert MAX_LOT_CAP == 0.01


class TestEventTypes:
    """Verify all 8 new event types exist."""

    def test_all_sprint_9_5_event_types_exist(self):
        from titan.production.trade_journal import EventType
        assert EventType.BROKER_DETECTED.value == "BROKER_DETECTED"
        assert EventType.BROKER_SCORE_UPDATED.value == "BROKER_SCORE_UPDATED"
        assert EventType.BROKER_PROFILE_SELECTED.value == "BROKER_PROFILE_SELECTED"
        assert EventType.EXECUTION_PROFILE_CHANGED.value == "EXECUTION_PROFILE_CHANGED"
        assert EventType.EXECUTION_WARNING.value == "EXECUTION_WARNING"
        assert EventType.EXECUTION_DEGRADED.value == "EXECUTION_DEGRADED"
        assert EventType.BROKER_UNSAFE.value == "BROKER_UNSAFE"
        assert EventType.EXECUTION_RECOVERED.value == "EXECUTION_RECOVERED"


class TestModulesImport:
    """Verify all new modules import cleanly."""

    def test_broker_intelligence_imports(self):
        from titan.production.broker_intelligence import (
            BrokerIntelligenceLayer, BrokerInfo, SYMBOL_PATTERNS,
        )
        assert BrokerIntelligenceLayer is not None

    def test_broker_quality_engine_imports(self):
        from titan.production.broker_quality_engine import (
            BrokerQualityEngine, BrokerQualityInput, BrokerQualityScore,
            score_to_band,
        )
        assert BrokerQualityEngine is not None

    def test_execution_profile_imports(self):
        from titan.production.execution_profile import (
            ExecutionProfileSelector, ExecutionProfile, PROFILES,
        )
        assert ExecutionProfileSelector is not None
        assert len(PROFILES) == 9

    def test_broker_risk_adapter_imports(self):
        from titan.production.broker_risk_adapter import (
            BrokerRiskAdapter, RiskAdaptation,
        )
        assert BrokerRiskAdapter is not None

    def test_broker_score_history_imports(self):
        from titan.production.broker_score_history import (
            BrokerScoreHistory, HistoryBucket,
        )
        assert BrokerScoreHistory is not None

    def test_execution_self_protection_imports(self):
        from titan.production.execution_self_protection import (
            ExecutionSelfProtection, SelfProtectionConfig, ProtectionState,
        )
        assert ExecutionSelfProtection is not None


class TestEndToEndFlow:
    """End-to-end: detect → score → select → adapt → protect."""

    def test_full_lifecycle_institutional_broker(self, tmp_path):
        from titan.production.broker_intelligence import (
            BrokerIntelligenceLayer, BrokerInfo,
        )
        from titan.production.broker_quality_engine import (
            BrokerQualityEngine, BrokerQualityInput,
        )
        from titan.production.execution_profile import ExecutionProfileSelector
        from titan.production.broker_risk_adapter import BrokerRiskAdapter
        from titan.production.execution_self_protection import (
            ExecutionSelfProtection, SelfProtectionConfig,
        )
        from titan.production.trade_journal import TradeJournal, EventType

        journal = TradeJournal(
            path=str(tmp_path / "e2e.jsonl"),
            session_id="e2e_test",
        )

        # Step 1: Detect broker (ICMarkets ECN)
        layer = BrokerIntelligenceLayer(journal=journal)
        from dataclasses import dataclass

        @dataclass
        class FakeAcc:
            company: str = "IC Markets"
            server: str = "ICMarkets-ECN"
            login: int = 12345
            trade_mode: int = 2  # REAL
            leverage: int = 500
            balance: float = 10000.0
            margin_mode: int = 1

        @dataclass
        class FakeSymbol:
            digits: int = 2
            point: float = 0.01
            spread: int = 5  # very tight
            trade_contract_size: float = 100.0
            volume_min: float = 0.01
            volume_max: float = 100.0
            volume_step: float = 0.01
            trade_freeze_level: int = 0
            trade_stops_level: int = 0
            trade_tick_value: float = 1.0
            trade_tick_size: float = 0.01
            trade_mode: int = 1
            filling_mode: int = 6

        info = layer.detect_from_account_info(FakeAcc(), FakeSymbol())
        assert info is not None
        assert info.is_ecn is True

        # Step 2: Score broker quality (institutional)
        quality_engine = BrokerQualityEngine(journal=journal)
        score = quality_engine.evaluate(BrokerQualityInput(
            spread_usd=0.05, spread_mean_usd=0.05, spread_std_usd=0.01,
            slippage_mean_pips=0, latency_mean_ms=20,
            connection_uptime_pct=100, symbol_health=100,
        ))
        assert score.band == "institutional"

        # Step 3: Select execution profile
        selector = ExecutionProfileSelector(journal=journal)
        profile = selector.select(score, info)
        assert profile.name == "ultra_low_spread"

        # Step 4: Adapt risk
        adapter = BrokerRiskAdapter(journal=journal)
        adaptation = adapter.adapt(score, profile)
        assert adaptation.risk_multiplier == 1.0  # institutional keeps full risk

        # Step 5: Self-protection (clean)
        protection = ExecutionSelfProtection(
            config=SelfProtectionConfig(), journal=journal,
        )
        action = protection.evaluate(spread_usd=0.05, latency_ms=20)
        assert action.action == "none"

        # Verify all event types journaled
        records = journal.read_all()
        event_types = set(r.get("event_type", "") for r in records)
        assert EventType.BROKER_DETECTED.value in event_types
        assert EventType.BROKER_SCORE_UPDATED.value in event_types
        assert EventType.BROKER_PROFILE_SELECTED.value in event_types

    def test_full_lifecycle_unsafe_broker(self, tmp_path):
        from titan.production.broker_intelligence import BrokerIntelligenceLayer
        from titan.production.broker_quality_engine import (
            BrokerQualityEngine, BrokerQualityInput,
        )
        from titan.production.execution_profile import ExecutionProfileSelector, PROFILES
        from titan.production.broker_risk_adapter import BrokerRiskAdapter
        from titan.production.execution_self_protection import (
            ExecutionSelfProtection, SelfProtectionConfig,
        )
        from titan.production.trade_loop import TradeLoopConfig, MAX_LOT_CAP
        from titan.production.trade_journal import TradeJournal, EventType

        journal = TradeJournal(
            path=str(tmp_path / "unsafe.jsonl"),
            session_id="unsafe_test",
        )

        # Score: unsafe
        quality_engine = BrokerQualityEngine(journal=journal)
        score = quality_engine.evaluate(BrokerQualityInput(
            spread_usd=5.0, spread_mean_usd=5.0, spread_std_usd=2.0,
            spread_spike_count=15, slippage_mean_pips=25,
            requote_rate=0.25, rejection_rate=0.25,
            latency_mean_ms=1500, gap_count=8,
            connection_uptime_pct=70, symbol_health=40,
        ))
        assert score.band == "unsafe"

        # Select: unsafe profile
        selector = ExecutionProfileSelector(journal=journal)
        profile = selector.select(score)
        assert profile.name == "unsafe"
        assert profile.allow_new_entries is False

        # Adapt: zero risk
        adapter = BrokerRiskAdapter(journal=journal)
        adaptation = adapter.adapt(score, profile)
        assert adaptation.risk_multiplier == 0.0
        assert adaptation.allow_new_entries is False

        # Apply to trade loop
        loop_cfg = TradeLoopConfig(dry_run=True)
        adapter.apply_to_trade_loop(adaptation, loop_cfg)
        assert loop_cfg.max_lot == 0.0  # unsafe zeroes lot

        # Self-protection: should escalate
        protection = ExecutionSelfProtection(
            config=SelfProtectionConfig(), journal=journal,
        )
        action = protection.evaluate(
            spread_usd=5.0, latency_ms=1500, rejection_rate=0.25,
        )
        # Should be at least degraded (likely unsafe due to rejection_rate)
        assert action.action in ("degraded", "unsafe")
        assert action.risk_multiplier < 1.0
