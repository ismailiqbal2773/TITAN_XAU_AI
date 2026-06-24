"""
TITAN XAU AI — Sprint 9.2 Integration Tests

Verify that capital_protection.enabled=false preserves old behavior, and
that capital_protection.enabled=true initializes all engines correctly
without breaking dry_run / live_trading safety guards.
"""
from __future__ import annotations
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


class TestCapitalProtectionDisabled:
    """When capital_protection.enabled=false, no behavior change."""

    def test_runtime_yaml_default_disabled(self):
        with open(REPO_ROOT / "config" / "runtime.yaml", "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        assert cfg["capital_protection"]["enabled"] is False

    def test_dry_run_flag_unchanged(self):
        with open(REPO_ROOT / "config" / "runtime.yaml", "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        assert cfg["runtime"]["dry_run"] is True
        assert cfg["runtime"]["live_trading"] is False

    def test_max_lot_hard_cap_unchanged(self):
        from titan.production.trade_loop import MAX_LOT_CAP
        assert MAX_LOT_CAP == 0.01


class TestCapitalProtectionConfig:
    """Verify config schema parses correctly."""

    def test_config_has_required_sections(self):
        with open(REPO_ROOT / "config" / "runtime.yaml", "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        cp = cfg["capital_protection"]
        assert "enabled" in cp
        assert "weights" in cp
        assert "recovery" in cp
        assert "capital_preservation" in cp
        assert "profit_lock" in cp
        assert "health_profiles" in cp

    def test_health_profiles_count(self):
        with open(REPO_ROOT / "config" / "runtime.yaml", "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        profiles = cfg["capital_protection"]["health_profiles"]
        assert len(profiles) == 5
        # Check all 5 expected profile names
        assert "normal" in profiles
        assert "slight_reduction" in profiles
        assert "defensive" in profiles
        assert "recovery_mode" in profiles
        assert "capital_preservation" in profiles

    def test_weights_sum_close_to_one(self):
        with open(REPO_ROOT / "config" / "runtime.yaml", "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        w = cfg["capital_protection"]["weights"]
        total = sum(w.values())
        assert 0.9 <= total <= 1.1


class TestEventTypes:
    """Verify all new event types exist."""

    def test_all_sprint_9_2_event_types_exist(self):
        from titan.production.trade_journal import EventType
        assert EventType.ACCOUNT_HEALTH.value == "ACCOUNT_HEALTH"
        assert EventType.HEALTH_TRANSITION.value == "HEALTH_TRANSITION"
        assert EventType.RECOVERY_MODE.value == "RECOVERY_MODE"
        assert EventType.CAPITAL_PRESERVATION.value == "CAPITAL_PRESERVATION"
        assert EventType.PROFIT_LOCK.value == "PROFIT_LOCK"
        assert EventType.EQUITY_PROTECTION.value == "EQUITY_PROTECTION"
        assert EventType.RISK_PROFILE_CHANGED.value == "RISK_PROFILE_CHANGED"


class TestModulesImport:
    """Verify all new modules import cleanly."""

    def test_account_health_engine_imports(self):
        from titan.production.account_health_engine import (
            AccountHealthEngine, AccountHealthInput, HealthWeights,
            AccountHealthScore, score_to_band,
        )
        assert AccountHealthEngine is not None

    def test_dynamic_risk_engine_imports(self):
        from titan.production.dynamic_risk_engine import (
            DynamicRiskEngine, DynamicRiskEvaluation, RiskProfile,
            DEFAULT_PROFILES,
        )
        assert DynamicRiskEngine is not None
        assert len(DEFAULT_PROFILES) == 5

    def test_capital_protection_imports(self):
        from titan.production.capital_protection import (
            RecoveryMode, RecoveryConfig,
            CapitalPreservation, CapitalPreservationConfig,
            ProfitLock, ProfitLockConfig,
            EquityProtection,
        )
        assert RecoveryMode is not None
        assert CapitalPreservation is not None
        assert ProfitLock is not None
        assert EquityProtection is not None


class TestEndToEndFlow:
    """End-to-end: health → dynamic risk → recovery → capital preservation."""

    def test_full_lifecycle(self, tmp_path):
        from titan.production.account_health_engine import (
            AccountHealthEngine, AccountHealthInput,
        )
        from titan.production.dynamic_risk_engine import DynamicRiskEngine
        from titan.production.capital_protection import (
            RecoveryMode, RecoveryConfig,
            CapitalPreservation, CapitalPreservationConfig,
        )
        from titan.production.trade_journal import TradeJournal, EventType

        journal = TradeJournal(
            path=str(tmp_path / "e2e.jsonl"),
            session_id="e2e_test",
        )
        health_engine = AccountHealthEngine(journal=journal)
        dynamic_risk = DynamicRiskEngine(journal=journal)
        recovery = RecoveryMode(
            config=RecoveryConfig(losing_streak_threshold=3, recovery_target_trades=2),
            journal=journal,
        )
        cap_pres = CapitalPreservation(
            config=CapitalPreservationConfig(trigger_dd_pct=8.0, halt_new_entries_dd_pct=9.0),
            journal=journal,
        )

        # ── Phase 1: Normal trading (high health) ──
        inp = AccountHealthInput(
            daily_dd_pct=0.0, total_dd_pct=0.0,
            consecutive_losses=0, winning_streak=3,
            equity_slope=0.3, kill_switch_state="NORMAL",
        )
        score = health_engine.evaluate(inp)
        risk = dynamic_risk.evaluate(score.score)
        assert score.band == "normal"
        assert risk.profile.name == "normal"
        assert risk.allow_new_entries is True

        # ── Phase 2: 3 consecutive losses → recovery activates ──
        recovery.record_loss()
        recovery.record_loss()
        recovery.record_loss()
        assert recovery.is_active is True

        # Health score drops due to consecutive_losses
        inp2 = AccountHealthInput(
            consecutive_losses=3, kill_switch_state="NORMAL",
        )
        score2 = health_engine.evaluate(inp2)
        risk2 = dynamic_risk.evaluate(score2.score)
        # Score should be lower (but exact band depends on weights)
        assert score2.score < score.score

        # ── Phase 3: Capital preservation activates at 8% DD ──
        cap_pres.update(8.5)
        assert cap_pres.is_active is True
        assert cap_pres.risk_multiplier == 0.25

        # ── Phase 4: 2 winning trades → recovery deactivates ──
        recovery.record_win()
        recovery.record_win()
        assert recovery.is_active is False

        # ── Phase 5: DD drops → capital preservation deactivates ──
        cap_pres.update(5.0)
        assert cap_pres.is_active is False

        # Verify all event types were journaled
        records = journal.read_all()
        event_types = set(r.get("event_type", "") for r in records)
        assert EventType.ACCOUNT_HEALTH.value in event_types
        assert EventType.RECOVERY_MODE.value in event_types
        assert EventType.CAPITAL_PRESERVATION.value in event_types
