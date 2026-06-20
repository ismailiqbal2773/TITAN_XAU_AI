"""
TITAN XAU AI — Tests for Risk Engine
Tests for EquityTracker, RiskMode, RiskSignal, control logic.
"""
import pytest
from titan.risk.engine import (
    RiskEngine,
    RiskMode,
    RiskDecision,
    RiskSignal,
    EquityTracker,
)


@pytest.fixture
def config():
    return {
        "risk": {
            "max_daily_drawdown": 5.0,
            "max_overall_drawdown": 10.0,
            "max_per_trade_risk": 1.0,
            "max_concurrent_positions": 5,
            "kill_switch_latency_ms": 500,
            "margin_alert_threshold": 200,
            "correlation_threshold": 0.85,
        },
    }


class TestRiskMode:
    def test_mode_values(self):
        assert RiskMode.NORMAL == "NORMAL"
        assert RiskMode.AGGRESSIVE == "AGGRESSIVE"
        assert RiskMode.DEFENSIVE == "DEFENSIVE"
        assert RiskMode.EMERGENCY == "EMERGENCY"


class TestRiskDecision:
    def test_decision_values(self):
        assert RiskDecision.ALLOW == "ALLOW"
        assert RiskDecision.REDUCE_SIZE == "REDUCE_SIZE"
        assert RiskDecision.VETO == "VETO"
        assert RiskDecision.FLATTEN == "FLATTEN"


class TestEquityTracker:
    def test_initial_state(self):
        t = EquityTracker(10000.0)
        assert t.initial_equity == 10000.0
        assert t.peak_equity == 10000.0
        assert t.start_of_day_equity == 10000.0

    def test_peak_updates_on_higher_equity(self):
        t = EquityTracker(10000.0)
        t.update(10500.0)
        assert t.peak_equity == 10500.0

    def test_drawdown_calculation(self):
        t = EquityTracker(10000.0)
        t.update(10500.0)  # Peak at 10500
        t.update(10000.0)  # DD = (10500-10000)/10500 = 4.76%
        assert t.max_drawdown_pct == pytest.approx(4.76, abs=0.1)

    def test_daily_drawdown(self):
        t = EquityTracker(10000.0)
        t.update(10000.0)
        t.update(9800.0)  # 2% daily DD
        assert t.daily_drawdown_pct == pytest.approx(2.0, abs=0.1)

    def test_reset_daily(self):
        t = EquityTracker(10000.0)
        t.update(10000.0)
        t.update(9800.0)
        t.reset_daily(9800.0)
        assert t.start_of_day_equity == 9800.0

    def test_zero_drawdown_on_peak(self):
        t = EquityTracker(10000.0)
        t.update(10000.0)
        assert t.max_drawdown_pct == 0.0
        assert t.daily_drawdown_pct == 0.0


class TestRiskSignal:
    def test_long_signal(self):
        s = RiskSignal(
            symbol="XAUUSD", direction=1, proposed_volume=0.5,
            entry_price=2000.0, stop_loss=1990.0, take_profit=2020.0,
        )
        assert s.direction == 1
        assert s.proposed_volume == 0.5

    def test_short_signal(self):
        s = RiskSignal(
            symbol="XAUUSD", direction=-1, proposed_volume=0.3,
            entry_price=2000.0, stop_loss=2010.0, take_profit=1980.0,
        )
        assert s.direction == -1
        assert s.stop_loss > s.entry_price  # Short: SL above entry
