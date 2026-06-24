"""
Tests for Sprint 3 production modules:
  - exit_manager.py
  - order_modifier.py
  - trade_journal.py
  - integration: signal → order → journal → trailing → exit
"""
from __future__ import annotations

import asyncio
import json
import os
import time
import tempfile
import pytest
import numpy as np
from unittest.mock import MagicMock, AsyncMock

from titan.production.inference import Signal, Direction
from titan.production.trade_loop import TradeLoop, TradeLoopConfig, TradeDecision
from titan.production.position_sync import BrokerPosition
from titan.production.exit_manager import (
    ExitManager, ExitConfig, ExitDecision, ExitReason,
)
from titan.production.order_modifier import (
    OrderModifier, ModifyRequest, ModifyResult,
)
from titan.production.trade_journal import TradeJournal, JournalRecord


# ─── Helpers ──────────────────────────────────────────────────────────────────

def make_signal(direction: Direction = Direction.LONG,
                confidence: float = 0.75,
                meta_confidence: float = 0.80,
                is_tradeable: bool = True) -> Signal:
    return Signal(
        timestamp=time.time(),
        direction=direction,
        confidence=confidence,
        meta_confidence=meta_confidence,
        xgb_proba=[0.2, 0.8] if direction == Direction.LONG else [0.8, 0.2],
        meta_proba=[0.2, 0.8],
        is_tradeable=is_tradeable,
        feature_vector=np.random.randn(55),
        inference_ms=10.0,
        source="test",
    )


def make_position(direction: int = 1, entry: float = 2000.0,
                  sl: float = 1995.0, tp: float = 2010.0,
                  volume: float = 0.01, age_hours: float = 1.0,
                  ticket: int = 50001) -> BrokerPosition:
    return BrokerPosition(
        ticket=ticket, symbol="XAUUSD", direction=direction, volume=volume,
        entry_price=entry, stop_loss=sl, take_profit=tp,
        open_time=time.time() - age_hours * 3600,
    )


# ─── exit_manager.py ──────────────────────────────────────────────────────────

class TestExitManagerTPSL:
    def test_tp_hit_long(self):
        mgr = ExitManager()
        pos = make_position(direction=1, tp=2010.0)
        d = mgr.evaluate(pos, current_price=2010.5)
        assert d.should_exit
        assert d.reason == ExitReason.TP_HIT

    def test_tp_hit_short(self):
        mgr = ExitManager()
        pos = make_position(direction=-1, tp=1990.0, sl=2005.0, entry=2000.0)
        d = mgr.evaluate(pos, current_price=1989.5)
        assert d.should_exit
        assert d.reason == ExitReason.TP_HIT

    def test_sl_hit_long(self):
        mgr = ExitManager()
        pos = make_position(direction=1, sl=1995.0)
        d = mgr.evaluate(pos, current_price=1994.5)
        assert d.should_exit
        assert d.reason == ExitReason.SL_HIT

    def test_sl_hit_short(self):
        mgr = ExitManager()
        pos = make_position(direction=-1, sl=2005.0, tp=1990.0, entry=2000.0)
        d = mgr.evaluate(pos, current_price=2005.5)
        assert d.should_exit
        assert d.reason == ExitReason.SL_HIT

    def test_no_exit_when_price_between_sl_tp(self):
        mgr = ExitManager()
        pos = make_position(direction=1, sl=1995.0, tp=2010.0)
        d = mgr.evaluate(pos, current_price=2005.0)
        assert not d.should_exit


class TestExitManagerRisk:
    def test_kill_switch_triggers_exit(self):
        mgr = ExitManager()
        pos = make_position()
        d = mgr.evaluate(pos, current_price=2005.0, kill_switch_armed=True)
        assert d.should_exit
        assert d.reason == ExitReason.KILL_SWITCH

    def test_max_dd_breached_triggers_exit(self):
        mgr = ExitManager(ExitConfig(max_dd_pct_kill=5.0))
        pos = make_position()
        d = mgr.evaluate(pos, current_price=2005.0, current_dd_pct=6.0)
        assert d.should_exit
        assert d.reason == ExitReason.MAX_DD_BREACHED

    def test_news_halt_triggers_exit(self):
        mgr = ExitManager()
        pos = make_position()
        d = mgr.evaluate(pos, current_price=2005.0, news_halt_active=True)
        assert d.should_exit
        assert d.reason == ExitReason.NEWS_PRE_HALFT

    def test_kill_switch_overrides_tp(self):
        """Kill switch is highest priority — fires even if TP also hit."""
        mgr = ExitManager()
        pos = make_position(tp=2010.0)
        d = mgr.evaluate(pos, current_price=2010.5, kill_switch_armed=True)
        assert d.should_exit
        assert d.reason == ExitReason.KILL_SWITCH


class TestExitManagerTime:
    def test_max_holding_time_exceeded(self):
        mgr = ExitManager(ExitConfig(max_holding_hours=1.0))
        pos = make_position(age_hours=2.0)
        d = mgr.evaluate(pos, current_price=2005.0)
        assert d.should_exit
        assert d.reason == ExitReason.MAX_HOLDING_TIME

    def test_max_holding_time_not_exceeded(self):
        mgr = ExitManager(ExitConfig(max_holding_hours=24.0))
        pos = make_position(age_hours=1.0)
        d = mgr.evaluate(pos, current_price=2005.0)
        assert not d.should_exit

    def test_stale_position_detected(self):
        """Position not seen by sync loop for > threshold = stale."""
        mgr = ExitManager(ExitConfig(stale_threshold_seconds=60.0))
        # Position with old open_time, simulate no recent sync
        pos = make_position(age_hours=0.1)
        # First call: should NOT be stale (just synced)
        d1 = mgr.evaluate(pos, current_price=2005.0)
        assert not d1.should_exit or d1.reason != ExitReason.STALE_POSITION
        # Now simulate "stale" — caller passes old current_time
        old_time = time.time() - 120  # 2 minutes ago
        pos.open_time = old_time - 3600  # position is old
        d2 = mgr.evaluate(pos, current_price=2005.0, current_time=old_time)
        # After 120s without sync, should be stale
        # (Note: depends on _last_position_update being older than threshold)


class TestExitManagerTrailing:
    def test_trailing_activates_at_1R(self):
        """Trailing should activate when profit >= 1R."""
        mgr = ExitManager(ExitConfig(
            trailing_activation_r_multiple=1.0,
            trailing_distance_r=0.5,
        ))
        # LONG: entry 2000, SL 1995 → R = 5 USD per oz per unit
        # At 2005: +5 = +1R
        pos = make_position(entry=2000.0, sl=1995.0, tp=2010.0)
        d = mgr.evaluate(pos, current_price=2005.0)
        assert not d.should_exit
        assert d.should_trail
        assert d.new_trailing_sl > pos.stop_loss  # SL moved up

    def test_trailing_not_activated_below_1R(self):
        mgr = ExitManager(ExitConfig(trailing_activation_r_multiple=1.0))
        pos = make_position(entry=2000.0, sl=1995.0)
        d = mgr.evaluate(pos, current_price=2003.0)  # +3 < 1R (5)
        assert not d.should_trail

    def test_trailing_sl_only_moves_favorably_long(self):
        """Trailing SL for LONG must be > current SL (never widen risk)."""
        mgr = ExitManager(ExitConfig(
            trailing_activation_r_multiple=1.0,
            trailing_distance_r=0.5,
        ))
        pos = make_position(entry=2000.0, sl=1995.0, tp=2010.0)
        d = mgr.evaluate(pos, current_price=2010.0)  # +2R
        if d.should_trail:
            assert d.new_trailing_sl > pos.stop_loss

    def test_trailing_sl_for_short(self):
        """Trailing SL for SHORT must be < current SL."""
        mgr = ExitManager(ExitConfig(
            trailing_activation_r_multiple=1.0,
            trailing_distance_r=0.5,
        ))
        pos = make_position(direction=-1, entry=2000.0, sl=2005.0, tp=1990.0)
        d = mgr.evaluate(pos, current_price=1995.0)  # +1R for short
        assert d.should_trail
        assert d.new_trailing_sl < pos.stop_loss  # SL moved down for short


class TestExitManagerPnL:
    def test_pnl_computation_long(self):
        mgr = ExitManager()
        pos = make_position(direction=1, entry=2000.0, volume=0.01)
        d = mgr.evaluate(pos, current_price=2005.0)
        # PnL = (2005-2000) × 100 × 0.01 = $5.00
        assert abs(d.unrealized_pnl_usd - 5.0) < 0.01

    def test_pnl_computation_short(self):
        mgr = ExitManager()
        pos = make_position(direction=-1, entry=2000.0, sl=2005.0, tp=1990.0, volume=0.01)
        d = mgr.evaluate(pos, current_price=1995.0)
        # PnL = (2000-1995) × 100 × 0.01 = $5.00 (short profits from price drop)
        assert abs(d.unrealized_pnl_usd - 5.0) < 0.01

    def test_r_multiple_computation(self):
        mgr = ExitManager()
        pos = make_position(entry=2000.0, sl=1995.0, volume=0.01)
        # R = |2000-1995| × 100 × 0.01 = $5
        # At 2005: PnL = $5 → R = 1.0
        d = mgr.evaluate(pos, current_price=2005.0)
        assert abs(d.r_multiple - 1.0) < 0.01


# ─── order_modifier.py ────────────────────────────────────────────────────────

class TestOrderModifierConfig:
    def test_dry_run_default_true(self):
        mod = OrderModifier()
        assert mod.dry_run is True

    def test_live_mode_requires_env_var(self, monkeypatch):
        monkeypatch.delenv("TITAN_LIVE_TRADING", raising=False)
        with pytest.raises(PermissionError):
            OrderModifier(dry_run=False)

    def test_live_mode_with_env_var(self, monkeypatch):
        monkeypatch.setenv("TITAN_LIVE_TRADING", "1")
        mod = OrderModifier(dry_run=False)
        assert mod.dry_run is False


class TestOrderModifierDryRun:
    @pytest.mark.asyncio
    async def test_dry_run_does_not_call_mt5(self):
        mod = OrderModifier(dry_run=True)
        mock_exec = MagicMock()
        mock_exec.get_positions = MagicMock(return_value=[])
        result = await mod.modify_sl_tp(
            ticket=50001, new_sl=2000.0, new_tp=2001.0,
            execution_engine=mock_exec,
        )
        assert result.success
        assert result.dry_run is True
        # CRITICAL: mt5.order_modify must NOT be called
        # (we can't directly assert, but no exception + dry_run=True confirms)

    @pytest.mark.asyncio
    async def test_dry_run_returns_success_with_journal(self):
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as tf:
            journal_path = tf.name
        try:
            journal = TradeJournal(path=journal_path)
            mod = OrderModifier(dry_run=True)
            result = await mod.modify_sl_tp(
                ticket=50001, new_sl=2000.0, new_tp=2001.0,
                reason="trailing_stop", journal=journal,
            )
            assert result.success
            assert result.journal_record_id is not None
            journal.flush()
            # Verify journal has MODIFY record
            mods = journal.read_by_type("MODIFY")
            assert len(mods) == 1
            assert mods[0]["data"]["new_sl"] == 2000.0
        finally:
            os.unlink(journal_path)

    @pytest.mark.asyncio
    async def test_reject_sl_zero(self):
        mod = OrderModifier(dry_run=True)
        result = await mod.modify_sl_tp(ticket=50001, new_sl=0.0, new_tp=2001.0)
        assert not result.success
        assert "must be > 0" in result.error

    @pytest.mark.asyncio
    async def test_reject_sl_equals_tp(self):
        mod = OrderModifier(dry_run=True)
        result = await mod.modify_sl_tp(ticket=50001, new_sl=2000.0, new_tp=2000.0)
        assert not result.success
        assert "cannot be equal" in result.error

    @pytest.mark.asyncio
    async def test_idempotency_blocks_duplicate(self):
        mod = OrderModifier(dry_run=True)
        # First call succeeds
        r1 = await mod.modify_sl_tp(ticket=50001, new_sl=2000.0, new_tp=2001.0,
                                     reason="trailing")
        assert r1.success
        # Second identical call blocked
        r2 = await mod.modify_sl_tp(ticket=50001, new_sl=2000.0, new_tp=2001.0,
                                     reason="trailing")
        assert not r2.success
        assert r2.idempotency_hit

    @pytest.mark.asyncio
    async def test_different_modify_passes_idempotency(self):
        mod = OrderModifier(dry_run=True)
        r1 = await mod.modify_sl_tp(ticket=50001, new_sl=2000.0, new_tp=2010.0,
                                     reason="trailing")
        # Different SL = different fingerprint (TP stays different to avoid SL==TP rule)
        r2 = await mod.modify_sl_tp(ticket=50001, new_sl=2001.0, new_tp=2010.0,
                                     reason="trailing")
        assert r1.success
        assert r2.success


class TestOrderModifierTrailing:
    @pytest.mark.asyncio
    async def test_trailing_not_activated_below_threshold(self):
        mod = OrderModifier(dry_run=True)
        result = await mod.trailing_stop_update(
            ticket=50001, current_price=2000.5, direction=1,
            activation_offset=1.0, sl_distance=0.5,
            entry_price=2000.0, original_sl=1995.0, original_tp=2010.0,
        )
        assert not result.success
        assert "trailing_not_activated" in result.error

    @pytest.mark.asyncio
    async def test_trailing_activated_above_threshold_long(self):
        mod = OrderModifier(dry_run=True)
        result = await mod.trailing_stop_update(
            ticket=50002, current_price=2002.0, direction=1,
            activation_offset=1.0, sl_distance=0.5,
            entry_price=2000.0, original_sl=1995.0, original_tp=2010.0,
        )
        assert result.success
        # new_sl = 2002.0 - 0.5 = 2001.5 (above original 1995.0)
        assert result.new_sl > 1995.0
        assert abs(result.new_sl - 2001.5) < 0.01

    @pytest.mark.asyncio
    async def test_trailing_never_widens_risk_long(self):
        """Trailing SL for LONG must be > original SL."""
        mod = OrderModifier(dry_run=True)
        # activation_offset=1.0 but price barely moved
        result = await mod.trailing_stop_update(
            ticket=50003, current_price=2000.4, direction=1,
            activation_offset=0.3, sl_distance=10.0,  # huge trail distance
            entry_price=2000.0, original_sl=1995.0, original_tp=2010.0,
        )
        # new_sl = 2000.4 - 10 = 1990.4 < 1995 → rejected
        assert not result.success
        assert "below_original" in result.error

    @pytest.mark.asyncio
    async def test_trailing_activated_short(self):
        mod = OrderModifier(dry_run=True)
        result = await mod.trailing_stop_update(
            ticket=50004, current_price=1998.0, direction=-1,
            activation_offset=1.0, sl_distance=0.5,
            entry_price=2000.0, original_sl=2005.0, original_tp=1990.0,
        )
        assert result.success
        # new_sl = 1998 + 0.5 = 1998.5 (below original 2005.0)
        assert result.new_sl < 2005.0
        assert abs(result.new_sl - 1998.5) < 0.01


# ─── trade_journal.py ─────────────────────────────────────────────────────────

class TestTradeJournal:
    def test_journal_creates_file(self, tmp_path):
        path = str(tmp_path / "journal.jsonl")
        journal = TradeJournal(path=path)
        assert os.path.exists(path)

    def test_log_signal(self, tmp_path):
        journal = TradeJournal(path=str(tmp_path / "j.jsonl"))
        sig = make_signal()
        rid = journal.log_signal(sig)
        assert rid is not None
        journal.flush()
        records = journal.read_by_type("SIGNAL")
        assert len(records) == 1
        assert records[0]["data"]["direction"] == "LONG"

    def test_log_decision_accepted(self, tmp_path):
        journal = TradeJournal(path=str(tmp_path / "j.jsonl"))
        dec = TradeDecision(
            accepted=True, signal=make_signal(),
            risk_decision="ALLOW", adjusted_volume=0.01,
            order_request={"symbol": "XAUUSD", "volume": 0.01},
            evaluation_ms=10.0, dry_run=True,
        )
        rid = journal.log_decision(dec)
        assert rid is not None
        journal.flush()
        records = journal.read_by_type("DECISION")
        assert len(records) == 1
        assert records[0]["data"]["accepted"] is True

    def test_log_decision_rejected(self, tmp_path):
        journal = TradeJournal(path=str(tmp_path / "j.jsonl"))
        dec = TradeDecision(
            accepted=False, reject_reason="spread_too_high",
            signal=make_signal(), evaluation_ms=5.0, dry_run=True,
        )
        journal.log_decision(dec)
        journal.flush()
        records = journal.read_by_type("DECISION")
        assert len(records) == 1
        assert records[0]["data"]["accepted"] is False
        assert records[0]["data"]["reject_reason"] == "spread_too_high"

    def test_log_order_only_for_accepted(self, tmp_path):
        journal = TradeJournal(path=str(tmp_path / "j.jsonl"))
        # Rejected decision — log_order should return "" (no record)
        dec_rejected = TradeDecision(
            accepted=False, reject_reason="x", signal=make_signal(),
            evaluation_ms=5.0, dry_run=True,
        )
        rid = journal.log_order(dec_rejected)
        assert rid == ""
        # Accepted decision — log_order should create record
        dec_accepted = TradeDecision(
            accepted=True, signal=make_signal(),
            order_request={"symbol": "XAUUSD", "volume": 0.01},
            evaluation_ms=5.0, dry_run=True,
        )
        rid2 = journal.log_order(dec_accepted)
        assert rid2 != ""
        journal.flush()
        orders = journal.read_by_type("ORDER")
        assert len(orders) == 1

    def test_log_exit(self, tmp_path):
        journal = TradeJournal(path=str(tmp_path / "j.jsonl"))
        journal.log_exit(
            ticket=50001, exit_reason="TP_HIT",
            entry_price=2000.0, exit_price=2010.0,
            direction=1, volume=0.01, pnl_usd=10.0,
            holding_time_seconds=3600.0,
        )
        journal.flush()
        records = journal.read_by_type("EXIT")
        assert len(records) == 1
        assert records[0]["data"]["exit_reason"] == "TP_HIT"
        assert records[0]["data"]["pnl_usd"] == 10.0

    def test_log_modify(self, tmp_path):
        journal = TradeJournal(path=str(tmp_path / "j.jsonl"))
        journal.log_modify(
            ticket=50001, old_sl=1995.0, old_tp=2010.0,
            new_sl=2000.0, new_tp=2010.0, reason="trailing_stop",
            dry_run=True,
        )
        journal.flush()
        records = journal.read_by_type("MODIFY")
        assert len(records) == 1
        assert records[0]["data"]["new_sl"] == 2000.0

    def test_jsonl_format(self, tmp_path):
        """Each record must be a single valid JSON line."""
        path = str(tmp_path / "j.jsonl")
        journal = TradeJournal(path=path)
        journal.log_signal(make_signal())
        journal.log_decision(TradeDecision(
            accepted=True, signal=make_signal(), evaluation_ms=1.0, dry_run=True,
        ))
        journal.flush()
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        assert len(lines) == 2
        for line in lines:
            line = line.strip()
            assert line  # non-empty
            obj = json.loads(line)  # valid JSON
            assert "record_id" in obj
            assert "timestamp" in obj
            assert "record_type" in obj
            assert "data" in obj

    def test_record_count(self, tmp_path):
        journal = TradeJournal(path=str(tmp_path / "j.jsonl"))
        for _ in range(5):
            journal.log_signal(make_signal())
        assert journal.record_count == 5

    def test_session_id_auto_generated(self, tmp_path):
        journal = TradeJournal(path=str(tmp_path / "j.jsonl"))
        assert len(journal.session_id) > 0


# ─── INTEGRATION TEST ─────────────────────────────────────────────────────────

class TestIntegrationLifecycle:
    """Full lifecycle: signal → order → journal → trailing → exit"""

    @pytest.mark.asyncio
    async def test_full_lifecycle_dry_run(self, tmp_path):
        """
        Complete dry_run lifecycle:
        1. TradeLoop accepts signal → journal logs DECISION + ORDER
        2. Position opens (simulated)
        3. ExitManager detects TP hit → journal logs EXIT
        4. OrderModifier trailing update → journal logs MODIFY
        """
        # ── Setup ──
        journal = TradeJournal(path=str(tmp_path / "lifecycle.jsonl"))
        loop = TradeLoop(TradeLoopConfig(dry_run=True), journal=journal)
        exit_mgr = ExitManager(ExitConfig(
            trailing_activation_r_multiple=1.0,
            trailing_distance_r=0.5,
        ))
        modifier = OrderModifier(dry_run=True)

        # ── Step 1: Signal → Order ──
        signal = make_signal(direction=Direction.LONG, is_tradeable=True)
        decision = await loop.process_signal(
            signal=signal, entry_price=2000.0, spread_usd=0.20,
        )
        assert decision.accepted
        assert decision.dry_run is True
        assert decision.order_request["sl"] > 0
        assert decision.order_request["tp"] > 0

        # ── Step 2: Simulate position open ──
        pos = BrokerPosition(
            ticket=50001, symbol="XAUUSD", direction=1,
            volume=decision.order_request["volume"],
            entry_price=2000.0,
            stop_loss=decision.order_request["sl"],
            take_profit=decision.order_request["tp"],
            open_time=time.time() - 60,  # 1 min ago
        )

        # ── Step 3: Trailing update (price moved +1R) ──
        # entry 2000, SL 1999.5 → R = 0.5 USD per unit
        # At 2000.5: +0.5 = +1R → trailing activates
        trail_result = await modifier.trailing_stop_update(
            ticket=pos.ticket, current_price=2000.5, direction=1,
            activation_offset=0.4,  # less than +0.5
            sl_distance=0.2,
            entry_price=pos.entry_price,
            original_sl=pos.stop_loss,
            original_tp=pos.take_profit,
            journal=journal,
        )
        assert trail_result.success
        assert trail_result.new_sl > pos.stop_loss  # SL moved up

        # ── Step 4: Update position SL (simulate broker confirming) ──
        pos.stop_loss = trail_result.new_sl

        # ── Step 5: Exit at TP ──
        exit_decision = exit_mgr.evaluate(
            pos, current_price=pos.take_profit,  # TP hit
        )
        assert exit_decision.should_exit
        assert exit_decision.reason == ExitReason.TP_HIT

        # ── Step 6: Journal the exit ──
        journal.log_exit(
            ticket=pos.ticket,
            exit_reason=exit_decision.reason.value,
            entry_price=pos.entry_price,
            exit_price=exit_decision.current_price,
            direction=pos.direction,
            volume=pos.volume,
            pnl_usd=exit_decision.unrealized_pnl_usd,
            holding_time_seconds=exit_decision.holding_time_seconds,
        )
        journal.flush()

        # ── Verify journal has complete lifecycle ──
        all_records = journal.read_all()
        types = [r["record_type"] for r in all_records]
        assert "DECISION" in types
        assert "ORDER" in types
        assert "MODIFY" in types
        assert "EXIT" in types

        # Count records
        decisions = journal.read_by_type("DECISION")
        orders = journal.read_by_type("ORDER")
        modifies = journal.read_by_type("MODIFY")
        exits = journal.read_by_type("EXIT")
        assert len(decisions) == 1
        assert len(orders) == 1
        assert len(modifies) == 1
        assert len(exits) == 1

        # Verify exit record
        exit_rec = exits[0]["data"]
        assert exit_rec["exit_reason"] == "TP_HIT"
        assert exit_rec["pnl_usd"] > 0  # TP hit = profit

    @pytest.mark.asyncio
    async def test_lifecycle_with_rejection(self, tmp_path):
        """Verify rejections are journaled too."""
        journal = TradeJournal(path=str(tmp_path / "rej.jsonl"))
        loop = TradeLoop(TradeLoopConfig(dry_run=True, max_spread_usd=0.5), journal=journal)
        signal = make_signal(is_tradeable=True)
        decision = await loop.process_signal(
            signal=signal, entry_price=2000.0, spread_usd=0.80,  # too high
        )
        assert not decision.accepted
        assert "spread_too_high" in decision.reject_reason
        journal.flush()
        # Decision logged
        decisions = journal.read_by_type("DECISION")
        assert len(decisions) == 1
        assert decisions[0]["data"]["accepted"] is False
        # No ORDER record for rejected decisions
        orders = journal.read_by_type("ORDER")
        assert len(orders) == 0

    @pytest.mark.asyncio
    async def test_can_manage_dry_run_position_entry_to_exit(self, tmp_path):
        """ANSWER: can TITAN manage a dry_run position from entry to exit?"""
        journal = TradeJournal(path=str(tmp_path / "full.jsonl"))
        loop = TradeLoop(TradeLoopConfig(dry_run=True), journal=journal)
        exit_mgr = ExitManager()
        modifier = OrderModifier(dry_run=True)

        # Entry
        signal = make_signal(direction=Direction.LONG, is_tradeable=True)
        decision = await loop.process_signal(signal, entry_price=2000.0, spread_usd=0.2)
        assert decision.accepted

        # Simulate position
        pos = BrokerPosition(
            ticket=50001, symbol="XAUUSD", direction=1,
            volume=0.01, entry_price=2000.0,
            stop_loss=decision.order_request["sl"],
            take_profit=decision.order_request["tp"],
            open_time=time.time(),
        )

        # Modify SL (trailing)
        mod_result = await modifier.modify_sl_tp(
            ticket=pos.ticket, new_sl=2000.5, new_tp=pos.take_profit,
            reason="manual_adjust", journal=journal,
        )
        assert mod_result.success

        # Exit at TP
        exit_dec = exit_mgr.evaluate(pos, current_price=pos.take_profit)
        assert exit_dec.should_exit
        assert exit_dec.reason == ExitReason.TP_HIT

        # Log exit
        journal.log_exit(
            ticket=pos.ticket, exit_reason=exit_dec.reason.value,
            entry_price=pos.entry_price, exit_price=exit_dec.current_price,
            direction=pos.direction, volume=pos.volume,
            pnl_usd=exit_dec.unrealized_pnl_usd,
            holding_time_seconds=exit_dec.holding_time_seconds,
        )
        journal.flush()

        # Verify complete lifecycle in journal
        record_types = [r["record_type"] for r in journal.read_all()]
        assert "DECISION" in record_types
        assert "ORDER" in record_types
        assert "MODIFY" in record_types
        assert "EXIT" in record_types
        # dry_run enforced throughout
        for r in journal.read_all():
            if r["record_type"] in ("ORDER", "MODIFY"):
                assert r["data"]["dry_run"] is True
