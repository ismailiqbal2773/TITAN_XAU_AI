"""
TITAN XAU AI — Sprint 9.0 PropFirmProfileManager Unit Tests
"""
from __future__ import annotations
import json
import os
import tempfile
from pathlib import Path

import pytest
import yaml

from titan.production.prop_firm_manager import (
    PropFirmProfileManager,
    FirmProfile,
    HARD_MAX_LOT_CAP,
    HARD_MAX_OPEN_POSITIONS,
    apply_profile_to_kill_switch,
    apply_profile_to_trade_loop,
    apply_profile_to_atr,
)
from titan.production.trade_journal import TradeJournal, EventType


REPO_ROOT = Path(__file__).resolve().parents[2]
PROFILES_YAML = REPO_ROOT / "config" / "prop_firm_profiles.yaml"


@pytest.fixture
def journal(tmp_path):
    return TradeJournal(path=str(tmp_path / "test_journal.jsonl"), session_id="test")


@pytest.fixture
def mgr(journal):
    return PropFirmProfileManager(
        profiles_path=str(PROFILES_YAML),
        journal=journal,
    )


# ─── Profile loading ─────────────────────────────────────────────────────────

class TestProfileLoading:
    def test_load_ftmo_challenge(self, mgr):
        p = mgr.load_profile("ftmo_challenge")
        assert p.profile_id == "ftmo_challenge"
        assert p.firm_id == "ftmo"
        assert p.profit_target_pct == 0.10
        assert p.max_daily_loss_pct == 0.05
        assert p.max_total_loss_pct == 0.10
        assert p.min_trading_days == 4
        assert p.consistency_rule_enabled is True
        assert p.consistency_pct == 0.40
        assert p.atr_profile == "challenge"

    def test_load_fundednext_challenge(self, mgr):
        p = mgr.load_profile("fundednext_challenge")
        assert p.firm_id == "fundednext"
        assert p.profit_target_pct == 0.10
        assert p.consistency_rule_enabled is False
        assert p.drawdown_mode == "static"

    def test_load_fundednext_funded_uses_trailing(self, mgr):
        p = mgr.load_profile("fundednext_funded")
        assert p.drawdown_mode == "trailing"
        assert p.profit_target_pct == 0.0
        assert p.atr_profile == "production_aggressive"

    def test_load_the5ers_challenge(self, mgr):
        p = mgr.load_profile("the5ers_challenge")
        assert p.max_daily_loss_pct == 0.04
        assert p.max_total_loss_pct == 0.06
        assert p.news_blackout_minutes == 2
        assert p.hedging_allowed is False

    def test_load_myfundedfx_challenge(self, mgr):
        p = mgr.load_profile("myfundedfx_challenge")
        assert p.firm_id == "myfundedfx"
        assert p.profit_target_pct == 0.08
        assert p.min_trading_days == 3
        assert p.atr_profile == "balanced"

    def test_load_ftmo_funded(self, mgr):
        p = mgr.load_profile("ftmo_funded")
        assert p.drawdown_mode == "trailing"
        assert p.profit_target_pct == 0.0
        assert p.atr_profile == "production_aggressive"

    def test_load_custom(self, mgr):
        p = mgr.load_profile("custom")
        assert p.firm_id == "custom"
        assert p.drawdown_mode == "hybrid"

    def test_load_custom_with_overrides(self, mgr):
        p = mgr.load_profile("custom", custom_overrides={
            "profit_target_pct": 0.15,
            "max_daily_loss_pct": 0.03,
        })
        assert p.profit_target_pct == 0.15
        assert p.max_daily_loss_pct == 0.03

    def test_all_8_profiles_loadable(self, mgr):
        """Verify all 8 profiles from the spec load successfully."""
        expected = [
            "ftmo_challenge", "ftmo_verification", "ftmo_funded",
            "fundednext_challenge", "fundednext_funded",
            "the5ers_challenge", "myfundedfx_challenge", "custom",
        ]
        for pid in expected:
            p = mgr.load_profile(pid)
            assert p.profile_id == pid


# ─── Fail-closed behavior ────────────────────────────────────────────────────

class TestFailClosed:
    def test_profile_none_refuses(self, mgr):
        with pytest.raises(ValueError, match="cannot be 'none'"):
            mgr.load_profile("none")

    def test_profile_empty_refuses(self, mgr):
        with pytest.raises(ValueError):
            mgr.load_profile("")

    def test_profile_auto_refuses_direct_load(self, mgr):
        with pytest.raises(ValueError, match="auto"):
            mgr.load_profile("auto")

    def test_unknown_profile_refuses(self, mgr):
        with pytest.raises(KeyError):
            mgr.load_profile("nonexistent_profile")

    def test_refuse_event_journaled(self, mgr, journal):
        try:
            mgr.load_profile("nonexistent")
        except KeyError:
            pass
        records = journal.read_all()
        refuse_events = [r for r in records if r.get("event_type") == EventType.PROFILE_REFUSED.value]
        assert len(refuse_events) >= 1


# ─── Auto-detection ──────────────────────────────────────────────────────────

class TestAutoDetect:
    def test_auto_detect_ftmo(self, mgr):
        class FakeAcc:
            company = "FTMO Broker"
            server = "FTMO-Server"
        suggestion = mgr.auto_detect(FakeAcc())
        assert suggestion == "ftmo_challenge"

    def test_auto_detect_fundednext(self, mgr):
        class FakeAcc:
            company = "FundedNext Technologies"
            server = "FundedNext-Server"
        suggestion = mgr.auto_detect(FakeAcc())
        assert suggestion == "fundednext_challenge"

    def test_auto_detect_the5ers(self, mgr):
        class FakeAcc:
            company = "The 5ers"
            server = "5ers-Server"
        suggestion = mgr.auto_detect(FakeAcc())
        assert suggestion == "the5ers_challenge"

    def test_auto_detect_myfundedfx(self, mgr):
        class FakeAcc:
            company = "MyFundedFX LLC"
            server = "MyFundedFX-Server"
        suggestion = mgr.auto_detect(FakeAcc())
        assert suggestion == "myfundedfx_challenge"

    def test_auto_detect_no_match_returns_none(self, mgr):
        class FakeAcc:
            company = "Unknown Broker XYZ"
            server = "unknown-server"
        suggestion = mgr.auto_detect(FakeAcc())
        assert suggestion is None

    def test_auto_detect_none_account_info(self, mgr):
        suggestion = mgr.auto_detect(None)
        assert suggestion is None

    def test_auto_detect_does_not_apply(self, mgr):
        """auto_detect must not change active_profile."""
        class FakeAcc:
            company = "FTMO Broker"
        mgr.auto_detect(FakeAcc())
        assert mgr.active_profile is None
        assert mgr.active_profile_id is None

    def test_auto_detect_journaled_as_suggestion(self, mgr, journal):
        class FakeAcc:
            company = "FTMO Broker"
        mgr.auto_detect(FakeAcc())
        records = journal.read_all()
        suggestions = [r for r in records if r.get("event_type") == EventType.PROFILE_SUGGESTION.value]
        assert len(suggestions) >= 1
        assert suggestions[0]["data"]["suggestion"] == "ftmo_challenge"

    def test_apply_suggestion_loads_profile(self, mgr):
        class FakeAcc:
            company = "FTMO Broker"
        suggestion = mgr.auto_detect(FakeAcc())
        p = mgr.apply_suggestion(suggestion)
        assert p.profile_id == "ftmo_challenge"
        assert mgr.active_profile_id == "ftmo_challenge"


# ─── Lock / unlock ───────────────────────────────────────────────────────────

class TestLockUnlock:
    def test_lock_prevents_switch(self, mgr):
        mgr.load_profile("ftmo_challenge")
        mgr.lock()
        with pytest.raises(PermissionError, match="locked"):
            mgr.load_profile("fundednext_challenge")

    def test_lock_allows_same_profile(self, mgr):
        mgr.load_profile("ftmo_challenge")
        mgr.lock()
        # Re-loading same profile should work
        p = mgr.load_profile("ftmo_challenge")
        assert p.profile_id == "ftmo_challenge"

    def test_unlock_requires_reason(self, mgr):
        mgr.load_profile("ftmo_challenge")
        mgr.lock()
        with pytest.raises(ValueError):
            mgr.unlock("")
        with pytest.raises(ValueError):
            mgr.unlock(None)

    def test_unlock_with_reason(self, mgr):
        mgr.load_profile("ftmo_challenge")
        mgr.lock()
        mgr.unlock("operator: switching to fundednext after passing FTMO")
        assert mgr.is_locked is False
        # Now switching should work
        p = mgr.load_profile("fundednext_challenge")
        assert p.profile_id == "fundednext_challenge"

    def test_unlock_journaled(self, mgr, journal):
        mgr.load_profile("ftmo_challenge")
        mgr.lock()
        mgr.unlock("test reason")
        records = journal.read_all()
        unlock_events = [r for r in records if r.get("event_type") == EventType.PROFILE_UNLOCKED.value]
        assert len(unlock_events) == 1
        assert unlock_events[0]["data"]["reason"] == "test reason"

    def test_locked_event_journaled(self, mgr, journal):
        mgr.load_profile("ftmo_challenge")
        mgr.lock()
        records = journal.read_all()
        lock_events = [r for r in records if r.get("event_type") == EventType.PROFILE_LOCKED.value]
        assert len(lock_events) == 1


# ─── Hard safety caps ────────────────────────────────────────────────────────

class TestHardCaps:
    def test_max_lot_capped_at_0_01(self, mgr):
        """Profile max_lot > 0.01 must be capped."""
        p = mgr.load_profile("ftmo_challenge")
        # All YAML profiles use max_lot=0.01, but let's verify the cap logic
        assert p.effective_max_lot <= HARD_MAX_LOT_CAP
        assert p.effective_max_lot == 0.01

    def test_max_lot_capped_when_profile_requests_larger(self, mgr):
        """Force a profile with larger max_lot and verify cap.
        The profile's max_lot field itself is capped at construction time
        (defense in depth) — effective_max_lot and max_lot both reflect
        the hard cap. This is intentional: the profile never carries
        a value > HARD_MAX_LOT_CAP, so downstream consumers can't
        accidentally use the raw value."""
        p = mgr.load_profile("custom", custom_overrides={"max_lot": 0.5})
        # Both max_lot and effective_max_lot must be ≤ HARD_MAX_LOT_CAP
        assert p.max_lot <= HARD_MAX_LOT_CAP
        assert p.effective_max_lot == 0.01  # capped

    def test_max_open_positions_capped_at_1(self, mgr):
        p = mgr.load_profile("custom", custom_overrides={"max_open_positions": 10})
        assert p.effective_max_open_positions == HARD_MAX_OPEN_POSITIONS


# ─── Apply to components ─────────────────────────────────────────────────────

class TestApplyToComponents:
    def test_apply_to_kill_switch_overrides_thresholds(self, mgr):
        from titan.production.kill_switch_fsm import KillSwitchConfig
        ks_cfg = KillSwitchConfig()
        p = mgr.load_profile("ftmo_challenge")
        apply_profile_to_kill_switch(p, ks_cfg)
        # FTMO challenge: 5% daily, 10% overall
        assert ks_cfg.max_daily_loss_pct == 5.0
        assert ks_cfg.max_drawdown_pct == 10.0
        assert ks_cfg.emergency_daily_loss_pct == 8.0  # emergency_halt_pct

    def test_apply_to_trade_loop_max_lot(self, mgr):
        from titan.production.trade_loop import TradeLoopConfig
        loop_cfg = TradeLoopConfig()
        p = mgr.load_profile("ftmo_challenge")
        apply_profile_to_trade_loop(p, loop_cfg)
        assert loop_cfg.max_lot == 0.01  # capped

    def test_apply_to_atr_uses_profile_atr_mapping(self, mgr):
        from titan.production.trade_loop import TradeLoopConfig
        loop_cfg = TradeLoopConfig()
        # ftmo_challenge → atr_profile=challenge → 1.5/3.0
        p = mgr.load_profile("ftmo_challenge")
        apply_profile_to_atr(p, loop_cfg)
        assert loop_cfg.atr_sl_multiplier == 1.5
        assert loop_cfg.atr_tp_multiplier == 3.0

    def test_apply_to_atr_funded_profile(self, mgr):
        from titan.production.trade_loop import TradeLoopConfig
        loop_cfg = TradeLoopConfig()
        # ftmo_funded → atr_profile=production_aggressive → 3.0/6.0
        p = mgr.load_profile("ftmo_funded")
        apply_profile_to_atr(p, loop_cfg)
        assert loop_cfg.atr_sl_multiplier == 3.0
        assert loop_cfg.atr_tp_multiplier == 6.0


# ─── Journal events ──────────────────────────────────────────────────────────

class TestJournalEvents:
    def test_profile_loaded_event(self, mgr, journal):
        mgr.load_profile("ftmo_challenge")
        records = journal.read_all()
        loaded = [r for r in records if r.get("event_type") == EventType.PROFILE_LOADED.value]
        assert len(loaded) == 1
        assert loaded[0]["data"]["profile_id"] == "ftmo_challenge"

    def test_profile_switched_event(self, mgr, journal):
        mgr.load_profile("ftmo_challenge")
        mgr.unlock("test")
        mgr.load_profile("fundednext_challenge")
        records = journal.read_all()
        switched = [r for r in records if r.get("event_type") == EventType.PROFILE_SWITCHED.value]
        assert len(switched) == 1
        assert switched[0]["data"]["to_profile"] == "fundednext_challenge"
