"""TITAN XAU AI - Sprint 9.9.3.45.1 Managed Trade Orchestrator Tests"""
from __future__ import annotations
import sys
from pathlib import Path
import pytest
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
from titan.production.demo_micro_managed_trade_orchestrator import ManagedTradeOrchestrator

class TestOrchestrator:
    def test_01_monitor_closed_position(self):
        orch = ManagedTradeOrchestrator()
        result = orch.monitor_position(
            position_ticket=12345, direction="BUY", entry_price=2000.0,
            current_sl=1990.0, current_tp=2010.0, current_price=2000.0, is_open=False,
        )
        assert result.verdict == "MANAGED_DEMO_MICRO_COMPLETED"
        assert result.final_position_status == "CLOSED"

    def test_02_monitor_open_position_breakeven(self):
        orch = ManagedTradeOrchestrator()
        result = orch.monitor_position(
            position_ticket=12345, direction="BUY", entry_price=2000.0,
            current_sl=1990.0, current_tp=2010.0, current_price=2001.5, is_open=True,
        )
        assert result.breakeven_triggered is True
        assert len(result.sl_modify_previews) >= 1

    def test_03_monitor_open_position_trailing(self):
        orch = ManagedTradeOrchestrator()
        result = orch.monitor_position(
            position_ticket=12345, direction="BUY", entry_price=2000.0,
            current_sl=1990.0, current_tp=2010.0, current_price=2002.5, is_open=True,
        )
        assert result.trailing_triggered is True

    def test_04_tp_preserved(self):
        orch = ManagedTradeOrchestrator()
        result = orch.monitor_position(
            position_ticket=12345, direction="BUY", entry_price=2000.0,
            current_sl=1990.0, current_tp=2010.0, current_price=2003.0, is_open=True,
        )
        for preview in result.sl_modify_previews:
            assert preview["tp"] == 2010.0

    def test_05_sl_favorable_only(self):
        orch = ManagedTradeOrchestrator()
        result = orch.monitor_position(
            position_ticket=12345, direction="BUY", entry_price=2000.0,
            current_sl=1990.0, current_tp=2010.0, current_price=2003.0, is_open=True,
        )
        for preview in result.sl_modify_previews:
            assert preview["favorable"] is True
            assert preview["new_sl"] >= preview["current_sl"]

    def test_06_no_martingale(self):
        orch = ManagedTradeOrchestrator()
        result = orch.monitor_position(
            position_ticket=12345, direction="BUY", entry_price=2000.0,
            current_sl=1990.0, current_tp=2010.0, current_price=2003.0, is_open=True,
        )
        result_dict = str(result.to_dict()).lower()
        assert "martingale" not in result_dict or "no martingale" in result_dict
