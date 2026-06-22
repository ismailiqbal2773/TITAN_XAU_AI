"""
Tests for Sprint 2 production modules:
  - trade_loop.py
  - position_sync.py
  - cold_start.py
  - integration test: feature_stream → inference → risk → dry_run order
"""
from __future__ import annotations

import asyncio
import os
import time
import pytest
import numpy as np
from unittest.mock import MagicMock, AsyncMock, patch

from titan.production.inference import InferenceEngine, Signal, Direction
from titan.production.trade_loop import (
    TradeLoop, TradeLoopConfig, TradeDecision,
    MAX_LOT_CAP, MAX_OPEN_POSITIONS,
)
from titan.production.position_sync import (
    PositionSync, BrokerPosition, SyncReport,
)
from titan.production.cold_start import ColdStartReconciler, ColdStartReport


# ─── Helpers ──────────────────────────────────────────────────────────────────

def make_signal(direction: Direction = Direction.LONG,
                confidence: float = 0.75,
                meta_confidence: float = 0.80,
                is_tradeable: bool = True) -> Signal:
    """Build a synthetic Signal for testing."""
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


# ─── trade_loop.py ────────────────────────────────────────────────────────────

class TestTradeLoopConfig:
    def test_dry_run_defaults_true(self):
        cfg = TradeLoopConfig()
        assert cfg.dry_run is True, "dry_run MUST default to True"

    def test_max_lot_cap(self):
        cfg = TradeLoopConfig(max_lot=0.10)
        assert cfg.max_lot == MAX_LOT_CAP == 0.01, "max_lot must be clamped to 0.01"

    def test_max_open_positions_cap(self):
        cfg = TradeLoopConfig(max_open_positions=5)
        assert cfg.max_open_positions == MAX_OPEN_POSITIONS == 1

    def test_live_mode_requires_env_var(self, monkeypatch):
        monkeypatch.delenv("TITAN_LIVE_TRADING", raising=False)
        with pytest.raises(PermissionError, match="TITAN_LIVE_TRADING"):
            TradeLoop(TradeLoopConfig(dry_run=False))

    def test_live_mode_with_env_var(self, monkeypatch):
        monkeypatch.setenv("TITAN_LIVE_TRADING", "1")
        loop = TradeLoop(TradeLoopConfig(dry_run=False))
        assert loop.config.dry_run is False


class TestTradeLoopRejections:
    """Verify every rejection rule fires correctly."""

    @pytest.mark.asyncio
    async def test_reject_non_tradeable_signal(self):
        loop = TradeLoop(TradeLoopConfig(dry_run=True))
        sig = make_signal(is_tradeable=False)
        d = await loop.process_signal(sig, entry_price=2000.0, spread_usd=0.2)
        assert not d.accepted
        assert d.reject_reason == "signal_not_tradeable"

    @pytest.mark.asyncio
    async def test_reject_flat_direction(self):
        loop = TradeLoop(TradeLoopConfig(dry_run=True))
        sig = make_signal(direction=Direction.FLAT, is_tradeable=True)
        d = await loop.process_signal(sig, entry_price=2000.0, spread_usd=0.2)
        assert not d.accepted
        assert d.reject_reason == "direction_is_flat"

    @pytest.mark.asyncio
    async def test_reject_news_halt(self):
        loop = TradeLoop(TradeLoopConfig(dry_run=True, news_halt_active=True))
        sig = make_signal()
        d = await loop.process_signal(sig, entry_price=2000.0, spread_usd=0.2)
        assert not d.accepted
        assert d.reject_reason == "news_halt_active"

    @pytest.mark.asyncio
    async def test_reject_spread_too_high(self):
        loop = TradeLoop(TradeLoopConfig(dry_run=True, max_spread_usd=0.50))
        sig = make_signal()
        d = await loop.process_signal(sig, entry_price=2000.0, spread_usd=0.80)
        assert not d.accepted
        assert "spread_too_high" in d.reject_reason
        assert "0.80" in d.reject_reason

    @pytest.mark.asyncio
    async def test_reject_max_open_positions(self):
        loop = TradeLoop(TradeLoopConfig(dry_run=True))
        loop._open_position_count = 1  # already at cap
        sig = make_signal()
        d = await loop.process_signal(sig, entry_price=2000.0, spread_usd=0.2)
        assert not d.accepted
        assert "max_open_positions_reached" in d.reject_reason

    @pytest.mark.asyncio
    async def test_reject_execution_halted(self):
        loop = TradeLoop(TradeLoopConfig(dry_run=True))
        mock_exec = MagicMock()
        mock_exec.is_halted = True
        sig = make_signal()
        d = await loop.process_signal(sig, entry_price=2000.0, spread_usd=0.2,
                                       execution_engine=mock_exec)
        assert not d.accepted
        assert d.reject_reason == "execution_engine_halted"


class TestTradeLoopSLTP:
    """Verify SL/TP computation and mandatory inclusion."""

    @pytest.mark.asyncio
    async def test_long_sl_tp(self):
        loop = TradeLoop(TradeLoopConfig(dry_run=True, sl_pips=50, tp_pips=100))
        sl, tp = loop._compute_sl_tp(entry_price=2000.0, direction=1)
        # LONG: SL below entry, TP above entry
        assert sl < 2000.0
        assert tp > 2000.0
        assert abs(sl - 1999.50) < 0.01   # 50 pips × $0.01 = $0.50
        assert abs(tp - 2001.00) < 0.01   # 100 pips × $0.01 = $1.00

    @pytest.mark.asyncio
    async def test_short_sl_tp(self):
        loop = TradeLoop(TradeLoopConfig(dry_run=True, sl_pips=50, tp_pips=100))
        sl, tp = loop._compute_sl_tp(entry_price=2000.0, direction=-1)
        # SHORT: SL above entry, TP below entry
        assert sl > 2000.0
        assert tp < 2000.0
        assert abs(sl - 2000.50) < 0.01
        assert abs(tp - 1999.00) < 0.01

    @pytest.mark.asyncio
    async def test_order_request_includes_sl_and_tp(self):
        loop = TradeLoop(TradeLoopConfig(dry_run=True))
        sig = make_signal(direction=Direction.LONG)
        d = await loop.process_signal(sig, entry_price=2000.0, spread_usd=0.2)
        assert d.accepted
        assert d.order_request is not None
        assert d.order_request["sl"] > 0
        assert d.order_request["tp"] > 0
        assert d.order_request["sl"] != d.order_request["tp"]

    @pytest.mark.asyncio
    async def test_order_request_volume_capped_at_0_01(self):
        loop = TradeLoop(TradeLoopConfig(dry_run=True))
        sig = make_signal()
        d = await loop.process_signal(sig, entry_price=2000.0, spread_usd=0.2)
        assert d.accepted
        assert d.order_request["volume"] <= MAX_LOT_CAP
        assert d.order_request["volume"] == 0.01


class TestTradeLoopDryRun:
    """Verify dry_run behavior — NO real orders submitted."""

    @pytest.mark.asyncio
    async def test_dry_run_does_not_call_submit_order(self):
        loop = TradeLoop(TradeLoopConfig(dry_run=True))
        mock_exec = MagicMock()
        mock_exec.is_halted = False
        mock_exec.submit_order = AsyncMock()
        sig = make_signal()
        d = await loop.process_signal(sig, entry_price=2000.0, spread_usd=0.2,
                                       execution_engine=mock_exec)
        assert d.accepted
        assert d.dry_run is True
        assert d.order_result is None
        # CRITICAL: submit_order must NOT be called in dry_run
        mock_exec.submit_order.assert_not_called()

    @pytest.mark.asyncio
    async def test_dry_run_decision_has_order_request(self):
        loop = TradeLoop(TradeLoopConfig(dry_run=True))
        sig = make_signal(direction=Direction.SHORT)
        d = await loop.process_signal(sig, entry_price=2000.0, spread_usd=0.2)
        assert d.accepted
        assert d.order_request is not None
        assert d.order_request["order_type"] == "MARKET_SELL"
        assert d.order_request["symbol"] == "XAUUSD"
        assert d.order_request["magic"] == 202619
        assert len(d.order_request["idempotency_key"]) > 0

    @pytest.mark.asyncio
    async def test_dry_run_increments_no_position_count(self):
        loop = TradeLoop(TradeLoopConfig(dry_run=True))
        sig = make_signal()
        d = await loop.process_signal(sig, entry_price=2000.0, spread_usd=0.2)
        assert d.accepted
        # In dry_run, position counter should NOT increment (no real fill)
        assert loop.open_position_count == 0

    @pytest.mark.asyncio
    async def test_notify_position_closed(self):
        loop = TradeLoop(TradeLoopConfig(dry_run=True))
        loop._open_position_count = 1
        loop.notify_position_closed()
        assert loop.open_position_count == 0


# ─── position_sync.py ─────────────────────────────────────────────────────────

class TestPositionSync:
    @pytest.mark.asyncio
    async def test_sync_once_with_empty_broker(self):
        sync = PositionSync(interval_seconds=10, broker_source="stub")
        sync.set_stub_positions([])
        report = await sync.sync_once()
        assert report.broker_positions == 0
        assert report.new_positions == 0
        assert report.is_clean is True

    @pytest.mark.asyncio
    async def test_sync_detects_new_position(self):
        sync = PositionSync(interval_seconds=10, broker_source="stub", magic_filter=None)
        sync.set_stub_positions([
            BrokerPosition(ticket=1001, symbol="XAUUSD", direction=1, volume=0.01,
                           entry_price=2000.0, stop_loss=1995.0, take_profit=2010.0,
                           open_time=time.time()),
        ])
        report = await sync.sync_once()
        assert report.new_positions == 1
        assert sync.position_count == 1
        assert sync.open_positions[0].ticket == 1001

    @pytest.mark.asyncio
    async def test_sync_detects_closed_position(self):
        sync = PositionSync(interval_seconds=10, broker_source="stub", magic_filter=None)
        # First sync: broker has 1 position
        sync.set_stub_positions([
            BrokerPosition(ticket=1001, symbol="XAUUSD", direction=1, volume=0.01,
                           entry_price=2000.0, stop_loss=1995.0, take_profit=2010.0,
                           open_time=time.time()),
        ])
        await sync.sync_once()
        assert sync.position_count == 1
        # Second sync: broker has 0 positions (position closed)
        sync.set_stub_positions([])
        report = await sync.sync_once()
        assert report.closed_positions == 1
        assert sync.position_count == 0

    @pytest.mark.asyncio
    async def test_sync_detects_modified_position(self):
        sync = PositionSync(interval_seconds=10, broker_source="stub", magic_filter=None)
        sync.set_stub_positions([
            BrokerPosition(ticket=1001, symbol="XAUUSD", direction=1, volume=0.01,
                           entry_price=2000.0, stop_loss=1995.0, take_profit=2010.0,
                           open_time=time.time()),
        ])
        await sync.sync_once()
        # Modify: SL tightened
        sync.set_stub_positions([
            BrokerPosition(ticket=1001, symbol="XAUUSD", direction=1, volume=0.01,
                           entry_price=2000.0, stop_loss=1997.0, take_profit=2010.0,
                           open_time=time.time()),
        ])
        report = await sync.sync_once()
        assert report.modified_positions == 1
        assert sync.open_positions[0].stop_loss == 1997.0

    @pytest.mark.asyncio
    async def test_callback_fires_on_close(self):
        callback_called = []
        async def on_close():
            callback_called.append(True)
        sync = PositionSync(interval_seconds=10, broker_source="stub",
                            on_position_closed=on_close, magic_filter=None)
        sync.set_stub_positions([
            BrokerPosition(ticket=1001, symbol="XAUUSD", direction=1, volume=0.01,
                           entry_price=2000.0, stop_loss=1995.0, take_profit=2010.0,
                           open_time=time.time()),
        ])
        await sync.sync_once()
        sync.set_stub_positions([])
        await sync.sync_once()
        assert len(callback_called) == 1

    @pytest.mark.asyncio
    async def test_magic_filter(self):
        sync = PositionSync(interval_seconds=10, broker_source="stub", magic_filter=202619)
        sync.set_stub_positions([
            BrokerPosition(ticket=1, symbol="XAUUSD", direction=1, volume=0.01,
                           entry_price=2000, stop_loss=0, take_profit=0, open_time=0, magic=202619),
            BrokerPosition(ticket=2, symbol="XAUUSD", direction=1, volume=0.01,
                           entry_price=2000, stop_loss=0, take_profit=0, open_time=0, magic=999999),
        ])
        report = await sync.sync_once()
        # Only TITAN magic (202619) positions are synced
        assert report.broker_positions == 1
        assert sync.position_count == 1


# ─── cold_start.py ────────────────────────────────────────────────────────────

class TestColdStart:
    @pytest.mark.asyncio
    async def test_cold_start_clean(self):
        sync = PositionSync(interval_seconds=10, broker_source="stub", magic_filter=None)
        sync.set_stub_positions([
            BrokerPosition(ticket=1001, symbol="XAUUSD", direction=1, volume=0.01,
                           entry_price=2000.0, stop_loss=1995.0, take_profit=2010.0,
                           open_time=time.time()),
        ])
        reconciler = ColdStartReconciler(position_sync=sync)
        report = await reconciler.reconcile()
        assert report.broker_positions == 1
        assert report.local_state_built == 1
        assert report.orphan_positions_cleared == 0
        assert report.state_drifts_corrected == 0
        assert report.is_clean is True

    @pytest.mark.asyncio
    async def test_cold_start_clears_orphans(self):
        sync = PositionSync(interval_seconds=10, broker_source="stub", magic_filter=None)
        # Local state has stale position
        sync._local_state[99999] = BrokerPosition(
            ticket=99999, symbol="XAUUSD", direction=1, volume=0.01,
            entry_price=2000, stop_loss=0, take_profit=0, open_time=0
        )
        # Broker has different position
        sync.set_stub_positions([
            BrokerPosition(ticket=1001, symbol="XAUUSD", direction=1, volume=0.01,
                           entry_price=2000.0, stop_loss=1995.0, take_profit=2010.0,
                           open_time=time.time()),
        ])
        reconciler = ColdStartReconciler(position_sync=sync)
        report = await reconciler.reconcile()
        assert report.orphan_positions_cleared == 1
        assert report.local_state_built == 1
        assert sync.position_count == 1
        assert sync.open_positions[0].ticket == 1001

    @pytest.mark.asyncio
    async def test_cold_start_detects_drift(self):
        sync = PositionSync(interval_seconds=10, broker_source="stub", magic_filter=None)
        # Local state has wrong volume
        sync._local_state[1001] = BrokerPosition(
            ticket=1001, symbol="XAUUSD", direction=1, volume=0.02,
            entry_price=2000, stop_loss=1995, take_profit=2010, open_time=0
        )
        # Broker has correct volume
        sync.set_stub_positions([
            BrokerPosition(ticket=1001, symbol="XAUUSD", direction=1, volume=0.01,
                           entry_price=2000.0, stop_loss=1995.0, take_profit=2010.0,
                           open_time=time.time()),
        ])
        reconciler = ColdStartReconciler(position_sync=sync)
        report = await reconciler.reconcile()
        assert report.state_drifts_corrected == 1
        assert report.is_clean is False
        # After reconcile, local should match broker
        assert sync.open_positions[0].volume == 0.01

    @pytest.mark.asyncio
    async def test_cold_start_no_duplicate_trades(self):
        """After cold start, TradeLoop should see existing position and not duplicate."""
        sync = PositionSync(interval_seconds=10, broker_source="stub", magic_filter=None)
        sync.set_stub_positions([
            BrokerPosition(ticket=1001, symbol="XAUUSD", direction=1, volume=0.01,
                           entry_price=2000.0, stop_loss=1995.0, take_profit=2010.0,
                           open_time=time.time()),
        ])
        reconciler = ColdStartReconciler(position_sync=sync)
        await reconciler.reconcile()
        # Now TradeLoop should be aware of existing position
        loop = TradeLoop(TradeLoopConfig(dry_run=True))
        loop._open_position_count = sync.position_count  # Wire sync → loop
        sig = make_signal()
        d = await loop.process_signal(sig, entry_price=2000.0, spread_usd=0.2)
        assert not d.accepted
        assert "max_open_positions_reached" in d.reject_reason

    @pytest.mark.asyncio
    async def test_cold_start_empty_broker(self):
        sync = PositionSync(interval_seconds=10, broker_source="stub", magic_filter=None)
        sync.set_stub_positions([])
        reconciler = ColdStartReconciler(position_sync=sync)
        report = await reconciler.reconcile()
        assert report.broker_positions == 0
        assert report.is_clean is True


# ─── INTEGRATION TEST ─────────────────────────────────────────────────────────

class TestIntegration:
    """End-to-end: feature_stream → inference → risk → dry_run order"""

    @pytest.mark.asyncio
    async def test_full_chain_dry_run(self):
        """
        Full pipeline on canonical H1 data:
          canonical bars → 55 features → XGB → meta → Signal → trade_loop (dry_run)
        """
        engine = InferenceEngine()
        loop = TradeLoop(TradeLoopConfig(dry_run=True))

        # Generate signal from canonical data
        signal = engine.generate(source="canonical")
        assert signal is not None
        assert signal.feature_vector is not None
        assert signal.feature_vector.shape == (55,)

        # Process through trade loop
        decision = await loop.process_signal(
            signal=signal,
            entry_price=2000.0,
            spread_usd=0.20,
            current_equity=10000.0,
        )

        # Verify decision structure
        assert isinstance(decision, TradeDecision)
        assert decision.signal is signal
        assert decision.dry_run is True
        # Either accepted (with valid order_request) or rejected (with reason)
        if decision.accepted:
            assert decision.order_request is not None
            assert decision.order_request["sl"] > 0
            assert decision.order_request["tp"] > 0
            assert decision.order_request["volume"] <= 0.01
            assert decision.order_request["symbol"] == "XAUUSD"
            assert decision.order_request["magic"] == 202619
            # CRITICAL: no order_result in dry_run
            assert decision.order_result is None
        else:
            assert decision.reject_reason is not None

    @pytest.mark.asyncio
    async def test_full_chain_with_forced_tradeable_signal(self):
        """Force a tradeable signal to verify the dry-run order is built correctly."""
        engine = InferenceEngine()
        loop = TradeLoop(TradeLoopConfig(dry_run=True))

        # Force a tradeable LONG signal (bypass inference thresholds)
        signal = make_signal(direction=Direction.LONG, confidence=0.80,
                             meta_confidence=0.85, is_tradeable=True)

        decision = await loop.process_signal(
            signal=signal,
            entry_price=2000.0,
            spread_usd=0.20,
        )

        assert decision.accepted
        assert decision.dry_run is True
        assert decision.order_request is not None
        assert decision.order_request["order_type"] == "MARKET_BUY"
        assert decision.order_request["volume"] == 0.01
        assert decision.order_request["sl"] > 0
        assert decision.order_request["tp"] > 0
        assert decision.order_request["sl"] < 2000.0  # LONG: SL below entry
        assert decision.order_request["tp"] > 2000.0  # LONG: TP above entry
        assert decision.order_result is None  # dry_run = no submission

    @pytest.mark.asyncio
    async def test_full_chain_with_forced_short_signal(self):
        """Force a tradeable SHORT signal."""
        loop = TradeLoop(TradeLoopConfig(dry_run=True))
        signal = make_signal(direction=Direction.SHORT, confidence=0.80,
                             meta_confidence=0.85, is_tradeable=True)
        decision = await loop.process_signal(
            signal=signal,
            entry_price=2000.0,
            spread_usd=0.20,
        )
        assert decision.accepted
        assert decision.order_request["order_type"] == "MARKET_SELL"
        assert decision.order_request["sl"] > 2000.0  # SHORT: SL above entry
        assert decision.order_request["tp"] < 2000.0  # SHORT: TP below entry

    @pytest.mark.asyncio
    async def test_can_system_create_valid_demo_order_request(self):
        """ANSWER TO USER QUESTION: can system create a valid demo order request?"""
        loop = TradeLoop(TradeLoopConfig(dry_run=True))
        signal = make_signal(direction=Direction.LONG, is_tradeable=True)
        decision = await loop.process_signal(
            signal=signal,
            entry_price=2000.0,
            spread_usd=0.20,
        )
        # Valid demo order request must have:
        assert decision.accepted, "Order should be accepted"
        req = decision.order_request
        assert req is not None, "OrderRequest must be built"
        assert req["symbol"] == "XAUUSD", "Symbol must be XAUUSD"
        assert req["volume"] == 0.01, "Volume must be 0.01 (cap)"
        assert req["sl"] > 0, "SL must be > 0 (mandatory)"
        assert req["tp"] > 0, "TP must be > 0 (mandatory)"
        assert req["sl"] != req["tp"], "SL and TP must differ"
        assert req["magic"] == 202619, "Magic number must identify TITAN"
        assert len(req["idempotency_key"]) > 0, "Idempotency key must be set"
        assert decision.dry_run is True, "Must be dry_run in tests"
        assert decision.order_result is None, "No real order submitted"
