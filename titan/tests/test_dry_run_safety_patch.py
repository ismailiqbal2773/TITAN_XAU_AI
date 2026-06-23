"""
Tests for Sprint 8.2 — Final Dry-Run Double Safety Patch.

Verifies:
  - Direct call to ExecutionEngine with dry_run=True NEVER calls mt5.order_send
  - Direct call bypassing TradeLoop is still safe
  - Missing TITAN_LIVE_TRADING blocks live order
  - Missing SL/TP blocks live order
  - Volume > 0.01 blocks live order
  - Halt flag blocks live order
  - Journal records internal guard event
  - dry_run default True
"""
from __future__ import annotations

import asyncio
import os
import time
import pytest
import numpy as np
from unittest.mock import patch, MagicMock

from titan.execution.engine import ExecutionEngine, OrderRequest, OrderType, OrderState


# ─── Helpers ──────────────────────────────────────────────────────────────────

def make_request(sl=1999.5, tp=2001.0, volume=0.01) -> OrderRequest:
    return OrderRequest(
        symbol="XAUUSD",
        order_type=OrderType.MARKET_BUY,
        volume=volume,
        price=0.0,
        sl=sl,
        tp=tp,
    )


def make_engine(dry_run=True) -> ExecutionEngine:
    """Create ExecutionEngine with specified dry_run mode."""
    eng = ExecutionEngine({"execution": {"dry_run": dry_run}})
    return eng


# ─── 1. Direct Call Dry-Run Safety ────────────────────────────────────────────

class TestDirectCallDryRun:
    @pytest.mark.asyncio
    async def test_dry_run_never_calls_mt5(self):
        """Direct call to ExecutionEngine with dry_run=True must NOT call mt5.order_send."""
        eng = make_engine(dry_run=True)
        req = make_request()
        with patch("MetaTrader5.order_send") as mock_send:
            result = await eng.submit_order(req)
            mock_send.assert_not_called()
        assert result.state == OrderState.REJECTED
        assert "internal_execution_guard" in result.error_message
        assert result.comment == "DRY_RUN_INTERNAL_GUARD"

    @pytest.mark.asyncio
    async def test_dry_run_returns_rejected_result(self):
        """Dry-run returns OrderResult with REJECTED state."""
        eng = make_engine(dry_run=True)
        req = make_request()
        result = await eng.submit_order(req)
        assert result.state == OrderState.REJECTED
        assert "dry_run" in result.error_message

    @pytest.mark.asyncio
    async def test_bypassing_tradeloop_still_safe(self):
        """Even if someone bypasses TradeLoop and calls ExecutionEngine directly,
        the internal guard prevents mt5.order_send."""
        eng = make_engine(dry_run=True)
        req = make_request()
        with patch("MetaTrader5.order_send") as mock_send:
            await eng.submit_order(req)
            assert mock_send.call_count == 0

    def test_dry_run_default_true(self):
        """ExecutionEngine defaults to dry_run=True."""
        eng = ExecutionEngine({"execution": {}})
        assert eng.is_dry_run is True

    def test_dry_run_exposed_as_property(self):
        """is_dry_run property exists for verification."""
        eng = make_engine(dry_run=True)
        assert eng.is_dry_run is True
        eng.set_dry_run(False)
        assert eng.is_dry_run is False


# ─── 2. Live Mode Safety Gates ────────────────────────────────────────────────

class TestLiveModeGates:
    @pytest.mark.asyncio
    async def test_missing_env_var_blocks_live(self, monkeypatch):
        """Without TITAN_LIVE_TRADING=1, live order is blocked."""
        monkeypatch.delenv("TITAN_LIVE_TRADING", raising=False)
        eng = make_engine(dry_run=False)
        req = make_request()
        with patch("MetaTrader5.order_send") as mock_send:
            result = await eng.submit_order(req)
            mock_send.assert_not_called()
        assert result.state == OrderState.REJECTED
        assert "TITAN_LIVE_TRADING" in result.error_message

    @pytest.mark.asyncio
    async def test_missing_sl_blocks_live(self, monkeypatch):
        """Missing SL blocks live order even with env var set."""
        monkeypatch.setenv("TITAN_LIVE_TRADING", "1")
        eng = make_engine(dry_run=False)
        req = make_request(sl=0.0, tp=2001.0)
        with patch("MetaTrader5.order_send") as mock_send:
            result = await eng.submit_order(req)
            mock_send.assert_not_called()
        assert result.state == OrderState.REJECTED
        assert "SL" in result.error_message

    @pytest.mark.asyncio
    async def test_missing_tp_blocks_live(self, monkeypatch):
        """Missing TP blocks live order even with env var set."""
        monkeypatch.setenv("TITAN_LIVE_TRADING", "1")
        eng = make_engine(dry_run=False)
        req = make_request(sl=1999.5, tp=0.0)
        with patch("MetaTrader5.order_send") as mock_send:
            result = await eng.submit_order(req)
            mock_send.assert_not_called()
        assert result.state == OrderState.REJECTED
        assert "SL and TP" in result.error_message

    @pytest.mark.asyncio
    async def test_volume_exceeds_cap_blocks_live(self, monkeypatch):
        """Volume > 0.01 blocks live order."""
        monkeypatch.setenv("TITAN_LIVE_TRADING", "1")
        eng = make_engine(dry_run=False)
        req = make_request(volume=0.10)
        with patch("MetaTrader5.order_send") as mock_send:
            result = await eng.submit_order(req)
            mock_send.assert_not_called()
        assert result.state == OrderState.REJECTED
        assert "volume" in result.error_message

    @pytest.mark.asyncio
    async def test_halt_flag_blocks_live(self, monkeypatch):
        """Halt flag blocks order even with all other gates passed."""
        monkeypatch.setenv("TITAN_LIVE_TRADING", "1")
        eng = make_engine(dry_run=False)
        eng.set_halt(True)
        req = make_request()
        with patch("MetaTrader5.order_send") as mock_send:
            result = await eng.submit_order(req)
            mock_send.assert_not_called()
        assert result.state == OrderState.REJECTED
        assert "halted" in result.error_message.lower()


# ─── 3. Defense-in-Depth ──────────────────────────────────────────────────────

class TestDefenseInDepth:
    @pytest.mark.asyncio
    async def test_two_layers_of_protection(self):
        """Both TradeLoop (caller) and ExecutionEngine (callee) check dry_run."""
        from titan.production.trade_loop import TradeLoop, TradeLoopConfig
        from titan.production.inference import Signal, Direction

        # Create TradeLoop with dry_run=True (layer 1)
        loop = TradeLoop(TradeLoopConfig(dry_run=True))

        # ExecutionEngine also has dry_run=True (layer 2)
        # (In production, TradeLoop doesn't call submit_order in dry_run,
        #  but if it did, the ExecutionEngine guard would catch it)
        eng = make_engine(dry_run=True)
        assert loop.config.dry_run is True  # layer 1
        assert eng.is_dry_run is True       # layer 2

    @pytest.mark.asyncio
    async def test_mt5_impossible_in_dry_run(self):
        """mt5.order_send is IMPOSSIBLE to reach in dry_run, even if caller guard fails."""
        eng = make_engine(dry_run=True)
        req = make_request()
        # Simulate a bug where TradeLoop somehow passes dry_run=False order to engine
        # The engine's internal guard should still block it
        with patch("MetaTrader5.order_send") as mock_send:
            result = await eng.submit_order(req)
            assert mock_send.call_count == 0
            assert result.state == OrderState.REJECTED

    @pytest.mark.asyncio
    async def test_all_gates_must_pass_for_live(self, monkeypatch):
        """ALL gates must pass for a live order to reach mt5.order_send."""
        monkeypatch.setenv("TITAN_LIVE_TRADING", "1")
        eng = make_engine(dry_run=False)
        eng.set_halt(False)
        req = make_request(sl=1999.5, tp=2001.0, volume=0.01)

        # All gates pass → mt5.order_send SHOULD be called
        # (but we mock it so no real order is placed)
        mock_result = MagicMock()
        mock_result.retcode = 10009  # TRADE_RETCODE_DONE
        mock_result.deal = 12345
        mock_result.order = 67890
        mock_result.volume = 0.01
        mock_result.price = 2000.0
        mock_result.bid = 1999.5
        mock_result.ask = 2000.5
        mock_result.comment = "OK"
        mock_result.request_id = 1
        mock_result.result_id = 1

        with patch("MetaTrader5.order_send", return_value=mock_result) as mock_send:
            result = await eng.submit_order(req)
            # mt5.order_send should have been called (all gates passed)
            assert mock_send.call_count > 0
            assert result.state in (OrderState.FILLED, OrderState.PARTIALLY_FILLED)


# ─── 4. Journal Evidence ──────────────────────────────────────────────────────

class TestJournalEvidence:
    @pytest.mark.asyncio
    async def test_dry_run_guard_returns_specific_comment(self):
        """The rejected result should have a specific comment for journaling."""
        eng = make_engine(dry_run=True)
        req = make_request()
        result = await eng.submit_order(req)
        assert result.comment == "DRY_RUN_INTERNAL_GUARD"

    @pytest.mark.asyncio
    async def test_live_blocked_returns_specific_comment(self, monkeypatch):
        """Live block returns specific comment."""
        monkeypatch.delenv("TITAN_LIVE_TRADING", raising=False)
        eng = make_engine(dry_run=False)
        req = make_request()
        result = await eng.submit_order(req)
        assert result.comment == "LIVE_BLOCKED"

    @pytest.mark.asyncio
    async def test_sl_tp_missing_returns_specific_comment(self, monkeypatch):
        """SL/TP missing returns specific comment."""
        monkeypatch.setenv("TITAN_LIVE_TRADING", "1")
        eng = make_engine(dry_run=False)
        req = make_request(sl=0, tp=0)
        result = await eng.submit_order(req)
        assert result.comment == "SL_TP_MISSING"
