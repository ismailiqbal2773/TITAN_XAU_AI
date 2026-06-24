"""
TITAN XAU AI — Sprint 9.0 Integration Tests

Verify that prop_firm.enabled=false preserves old behavior, and that
prop_firm.enabled=true loads profiles correctly without breaking
dry_run / live_trading safety guards.
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from titan.production.prop_firm_manager import (
    PropFirmProfileManager,
    HARD_MAX_LOT_CAP,
)
from titan.production.trade_journal import TradeJournal
from titan.production.trade_loop import TradeLoopConfig, MAX_LOT_CAP
from titan.production.kill_switch_fsm import KillSwitchConfig


class TestPropFirmDisabled:
    """When prop_firm.enabled=false, no behavior change."""

    def test_runtime_yaml_default_disabled(self):
        with open(REPO_ROOT / "config" / "runtime.yaml", "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        assert cfg["prop_firm"]["enabled"] is False
        assert cfg["prop_firm"]["profile"] == "none"

    def test_dry_run_flag_unchanged(self):
        with open(REPO_ROOT / "config" / "runtime.yaml", "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        assert cfg["runtime"]["dry_run"] is True
        assert cfg["runtime"]["live_trading"] is False

    def test_max_lot_hard_cap_unchanged(self):
        # Hard cap in trade_loop.py is still 0.01
        assert MAX_LOT_CAP == 0.01
        # PropFirmProfileManager hard cap matches
        assert HARD_MAX_LOT_CAP == 0.01


class TestPropFirmEnabled:
    """When prop_firm.enabled=true, profile is loaded correctly."""

    @pytest.fixture
    def mgr(self, tmp_path):
        journal = TradeJournal(
            path=str(tmp_path / "integration.jsonl"),
            session_id="integration_test",
        )
        return PropFirmProfileManager(
            profiles_path=str(REPO_ROOT / "config" / "prop_firm_profiles.yaml"),
            journal=journal,
        )

    def test_ftmo_thresholds_applied(self, mgr):
        from titan.production.prop_firm_manager import apply_profile_to_kill_switch
        ks_cfg = KillSwitchConfig()
        p = mgr.load_profile("ftmo_challenge")
        apply_profile_to_kill_switch(p, ks_cfg)
        # FTMO: 5% daily, 10% overall
        assert ks_cfg.max_daily_loss_pct == 5.0
        assert ks_cfg.max_drawdown_pct == 10.0
        # Old defaults (3.0 / 5.0) must be overridden
        assert ks_cfg.max_daily_loss_pct != 3.0

    def test_fundednext_thresholds_applied(self, mgr):
        from titan.production.prop_firm_manager import apply_profile_to_kill_switch
        ks_cfg = KillSwitchConfig()
        p = mgr.load_profile("fundednext_challenge")
        apply_profile_to_kill_switch(p, ks_cfg)
        assert ks_cfg.max_daily_loss_pct == 5.0
        assert ks_cfg.max_drawdown_pct == 10.0

    def test_the5ers_news_blackout_applied(self, mgr):
        p = mgr.load_profile("the5ers_challenge")
        assert p.news_blackout_minutes == 2  # 5ers-specific

    def test_myfundedfx_profile_exists(self, mgr):
        p = mgr.load_profile("myfundedfx_challenge")
        assert p.firm_id == "myfundedfx"
        assert p.min_trading_days == 3
        assert p.profit_target_pct == 0.08

    def test_max_lot_hard_cap_cannot_be_exceeded(self, mgr):
        """Even if profile requests higher max_lot, hard cap wins."""
        from titan.production.prop_firm_manager import apply_profile_to_trade_loop
        loop_cfg = TradeLoopConfig()
        p = mgr.load_profile("custom", custom_overrides={"max_lot": 0.5})
        apply_profile_to_trade_loop(p, loop_cfg)
        assert loop_cfg.max_lot == 0.01  # capped
        assert loop_cfg.max_lot <= MAX_LOT_CAP


class TestDryRunSafetyUnchanged:
    """Verify dry_run / live_trading flags are NOT changed by prop firm layer."""

    def test_dry_run_still_true_in_runtime_yaml(self):
        with open(REPO_ROOT / "config" / "runtime.yaml", "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        assert cfg["runtime"]["dry_run"] is True
        assert cfg["runtime"]["live_trading"] is False

    def test_execution_engine_guard_still_active(self):
        # Verify execution engine still has dry_run guard
        from titan.execution.engine import ExecutionEngine
        ee = ExecutionEngine({"execution": {"dry_run": True}})
        assert ee.is_dry_run is True

    def test_trade_loop_dry_run_default(self):
        cfg = TradeLoopConfig()
        assert cfg.dry_run is True


class TestChallengeStatusEventEmitted:
    """Verify CHALLENGE_STATUS event can be emitted."""

    def test_event_type_exists(self):
        from titan.production.trade_journal import EventType
        assert EventType.CHALLENGE_STATUS.value == "CHALLENGE_STATUS"

    def test_event_emitted_via_scorecard(self, tmp_path):
        from titan.production.challenge_scorecard import (
            ChallengeScorecard, ChallengeState,
        )
        from datetime import datetime, timezone, timedelta

        journal = TradeJournal(
            path=str(tmp_path / "status.jsonl"),
            session_id="status_test",
        )
        mgr = PropFirmProfileManager(
            profiles_path=str(REPO_ROOT / "config" / "prop_firm_profiles.yaml"),
            journal=journal,
        )
        sc = ChallengeScorecard(journal=journal)
        profile = mgr.load_profile("ftmo_challenge")
        now = datetime.now(timezone.utc)
        state = ChallengeState(
            initial_balance=100000.0,
            current_balance=100000.0,
            current_equity=100000.0,
            peak_equity=100000.0,
            start_of_day_balance=100000.0,
            today_realized_pnl=0.0,
            today_unrealized_pnl=0.0,
            largest_single_day_profit=0.0,
            total_realized_pnl=0.0,
            challenge_start_date=now - timedelta(days=2),
            now=now,
        )
        sc.evaluate(profile, state)
        records = journal.read_all()
        status_events = [r for r in records if r.get("event_type") == "CHALLENGE_STATUS"]
        assert len(status_events) == 1
        data = status_events[0]["data"]
        assert data["profile_id"] == "ftmo_challenge"
        assert "readiness_score" in data
        assert "rule_breaches" in data
