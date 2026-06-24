"""
TITAN XAU AI — Sprint 9.2 Capital Protection Unit Tests
"""
from __future__ import annotations
import pytest

from titan.production.capital_protection import (
    RecoveryMode, RecoveryConfig,
    CapitalPreservation, CapitalPreservationConfig,
    ProfitLock, ProfitLockConfig,
    EquityProtection,
)
from titan.production.trade_journal import TradeJournal, EventType


@pytest.fixture
def journal(tmp_path):
    return TradeJournal(path=str(tmp_path / "cap.jsonl"), session_id="cap_test")


# ════════════════════════════════════════════════════════════════════════════
# RecoveryMode
# ════════════════════════════════════════════════════════════════════════════
class TestRecoveryMode:
    @pytest.fixture
    def recovery(self, journal):
        return RecoveryMode(
            config=RecoveryConfig(
                losing_streak_threshold=3,
                min_confidence_threshold=0.75,
                recovery_target_trades=2,
                risk_multiplier=0.5,
            ),
            journal=journal,
        )

    def test_initial_state_not_active(self, recovery):
        assert recovery.is_active is False
        assert recovery.risk_multiplier == 1.0

    def test_activates_after_threshold_losses(self, recovery):
        recovery.record_loss()
        recovery.record_loss()
        assert recovery.is_active is False
        recovery.record_loss()
        assert recovery.is_active is True

    def test_activation_journaled(self, recovery, journal):
        for _ in range(3):
            recovery.record_loss()
        records = journal.read_all()
        activations = [r for r in records
                       if r.get("event_type") == EventType.RECOVERY_MODE.value
                       and r["data"].get("event") == "activated"]
        assert len(activations) == 1

    def test_deactivates_after_target_wins(self, recovery):
        for _ in range(3):
            recovery.record_loss()
        assert recovery.is_active is True
        recovery.record_win()
        assert recovery.is_active is True  # need 2 wins
        recovery.record_win()
        assert recovery.is_active is False

    def test_deactivation_journaled(self, recovery, journal):
        for _ in range(3):
            recovery.record_loss()
        recovery.record_win()
        recovery.record_win()
        records = journal.read_all()
        deactivations = [r for r in records
                         if r.get("event_type") == EventType.RECOVERY_MODE.value
                         and r["data"].get("event") == "deactivated"]
        assert len(deactivations) == 1

    def test_risk_multiplier_when_active(self, recovery):
        for _ in range(3):
            recovery.record_loss()
        assert recovery.risk_multiplier == 0.5

    def test_risk_multiplier_when_inactive(self, recovery):
        assert recovery.risk_multiplier == 1.0

    def test_should_allow_trade_in_recovery(self, recovery):
        for _ in range(3):
            recovery.record_loss()
        # In recovery, only high-confidence trades allowed
        assert recovery.should_allow_trade(0.80) is True
        assert recovery.should_allow_trade(0.70) is False
        assert recovery.should_allow_trade(0.75) is True  # exactly threshold

    def test_should_allow_trade_when_not_in_recovery(self, recovery):
        # Not in recovery — any confidence OK
        assert recovery.should_allow_trade(0.10) is True
        assert recovery.should_allow_trade(0.90) is True

    def test_loss_resets_wins_in_recovery(self, recovery):
        for _ in range(3):
            recovery.record_loss()
        recovery.record_win()
        recovery.record_loss()  # resets win counter
        assert recovery.state.consecutive_wins_in_recovery == 0
        assert recovery.is_active is True  # still in recovery


# ════════════════════════════════════════════════════════════════════════════
# CapitalPreservation
# ════════════════════════════════════════════════════════════════════════════
class TestCapitalPreservation:
    @pytest.fixture
    def cap_pres(self, journal):
        return CapitalPreservation(
            config=CapitalPreservationConfig(
                trigger_dd_pct=8.0,
                halt_new_entries_dd_pct=9.0,
                risk_multiplier=0.25,
            ),
            journal=journal,
        )

    def test_initial_state_not_active(self, cap_pres):
        assert cap_pres.is_active is False
        assert cap_pres.new_entries_halted is False
        assert cap_pres.risk_multiplier == 1.0

    def test_activates_at_trigger_dd(self, cap_pres):
        cap_pres.update(7.9)
        assert cap_pres.is_active is False
        cap_pres.update(8.0)
        assert cap_pres.is_active is True
        assert cap_pres.risk_multiplier == 0.25

    def test_halt_new_entries_at_halt_threshold(self, cap_pres):
        cap_pres.update(8.5)
        assert cap_pres.new_entries_halted is False
        cap_pres.update(9.0)
        assert cap_pres.new_entries_halted is True
        assert cap_pres.should_allow_new_entry() is False

    def test_deactivates_when_dd_falls_below_trigger(self, cap_pres):
        cap_pres.update(8.5)
        assert cap_pres.is_active is True
        cap_pres.update(7.0)
        assert cap_pres.is_active is False
        assert cap_pres.risk_multiplier == 1.0

    def test_activation_journaled(self, cap_pres, journal):
        cap_pres.update(8.5)
        records = journal.read_all()
        activations = [r for r in records
                       if r.get("event_type") == EventType.CAPITAL_PRESERVATION.value
                       and r["data"].get("event") == "activated"]
        assert len(activations) == 1

    def test_deactivation_journaled(self, cap_pres, journal):
        cap_pres.update(8.5)
        cap_pres.update(7.0)
        records = journal.read_all()
        deactivations = [r for r in records
                         if r.get("event_type") == EventType.CAPITAL_PRESERVATION.value
                         and r["data"].get("event") == "deactivated"]
        assert len(deactivations) == 1

    def test_halt_event_journaled(self, cap_pres, journal):
        cap_pres.update(9.5)  # triggers both activation and halt
        records = journal.read_all()
        halt_events = [r for r in records
                       if r.get("event_type") == EventType.CAPITAL_PRESERVATION.value
                       and r["data"].get("event") == "new_entries_halted"]
        assert len(halt_events) == 1


# ════════════════════════════════════════════════════════════════════════════
# ProfitLock
# ════════════════════════════════════════════════════════════════════════════
class TestProfitLock:
    @pytest.fixture
    def profit_lock(self, journal):
        return ProfitLock(
            config=ProfitLockConfig(
                enabled=True,
                lock_distance_pct=2.0,
                trail_distance_pct=1.0,
            ),
            initial_balance=10000.0,
            journal=journal,
        )

    def test_initial_state_not_locked(self, profit_lock):
        assert profit_lock.is_locked is False
        assert profit_lock.locked_equity == 10000.0
        assert profit_lock.peak_equity == 10000.0

    def test_activates_after_lock_distance_gain(self, profit_lock):
        profit_lock.update(10199.0)  # +1.99% — not yet
        assert profit_lock.is_locked is False
        profit_lock.update(10200.0)  # +2.0% — activates
        assert profit_lock.is_locked is True
        # locked = peak * (1 - trail/100) = 10200 * 0.99 = 10098
        assert profit_lock.locked_equity == pytest.approx(10098.0, abs=0.01)

    def test_activation_journaled(self, profit_lock, journal):
        profit_lock.update(10200.0)
        records = journal.read_all()
        activations = [r for r in records
                       if r.get("event_type") == EventType.PROFIT_LOCK.value
                       and r["data"].get("event") == "activated"]
        assert len(activations) == 1

    def test_locked_equity_never_decreases(self, profit_lock):
        profit_lock.update(10500.0)  # peak rises, lock trails up
        first_locked = profit_lock.locked_equity
        profit_lock.update(10100.0)  # equity drops, but lock stays
        assert profit_lock.locked_equity == first_locked

    def test_locked_equity_rises_with_new_peak(self, profit_lock, journal):
        profit_lock.update(10200.0)  # activate lock
        first_locked = profit_lock.locked_equity
        profit_lock.update(10500.0)  # new peak → trail up
        assert profit_lock.locked_equity > first_locked
        # Verify raised event journaled
        records = journal.read_all()
        raised = [r for r in records
                  if r.get("event_type") == EventType.PROFIT_LOCK.value
                  and r["data"].get("event") == "locked_equity_raised"]
        assert len(raised) >= 1

    def test_is_below_locked_detection(self, profit_lock):
        profit_lock.update(10200.0)  # lock at 10098
        assert profit_lock.is_below_locked(10050.0) is True
        assert profit_lock.is_below_locked(10100.0) is False

    def test_disabled_config_means_no_locking(self, journal):
        pl = ProfitLock(
            config=ProfitLockConfig(enabled=False),
            initial_balance=10000.0,
            journal=journal,
        )
        pl.update(11000.0)
        assert pl.is_locked is False


# ════════════════════════════════════════════════════════════════════════════
# EquityProtection
# ════════════════════════════════════════════════════════════════════════════
class TestEquityProtection:
    @pytest.fixture
    def equity_prot(self, journal):
        return EquityProtection(initial_balance=10000.0, journal=journal)

    def test_initial_state(self, equity_prot):
        state = equity_prot.state
        assert state.initial_balance == 10000.0
        assert state.highest_equity == 10000.0
        assert state.current_equity == 10000.0
        assert state.drawdown_from_peak_pct == 0.0
        assert state.drawdown_from_initial_pct == 0.0

    def test_tracks_new_peak(self, equity_prot):
        equity_prot.update(10500.0)
        assert equity_prot.state.highest_equity == 10500.0

    def test_drawdown_calculation(self, equity_prot):
        equity_prot.update(10500.0)
        equity_prot.update(10000.0)
        state = equity_prot.state
        # DD from peak: (10500 - 10000) / 10500 = 4.76%
        assert state.drawdown_from_peak_pct == pytest.approx(4.76, abs=0.01)
        # DD from initial: 0% (equity = initial)
        assert state.drawdown_from_initial_pct == 0.0

    def test_recovery_target_is_peak(self, equity_prot):
        equity_prot.update(10800.0)
        assert equity_prot.state.recovery_target == 10800.0

    def test_journals_equity_protection_events(self, equity_prot, journal):
        equity_prot.update(10500.0)
        records = journal.read_all()
        ep_events = [r for r in records
                     if r.get("event_type") == EventType.EQUITY_PROTECTION.value]
        assert len(ep_events) >= 1

    def test_locked_equity_passthrough(self, equity_prot):
        equity_prot.update(10500.0, locked_equity=10300.0)
        assert equity_prot.state.locked_equity == 10300.0
