"""Tests for CEO Supervisor"""
import pytest
import numpy as np
from titan.ceo.supervisor import (
    CEOSupervisor, SystemStatus, ControlAction, HealthScores,
    DetectionEvent, ModelHealthMonitor, DetectionEngine,
    DecisionEngine, ActionEngine, RollingWindow,
)


@pytest.fixture
def model_ids():
    return ["xgboost", "lstm", "transformer", "rl_manager"]


@pytest.fixture
def ceo(model_ids):
    return CEOSupervisor(model_ids)


class TestSystemStatus:
    def test_values(self):
        assert SystemStatus.GREEN == "GREEN"
        assert SystemStatus.YELLOW == "YELLOW"
        assert SystemStatus.RED == "RED"
        assert SystemStatus.RED_PRESERVE == "RED_PRESERVE"


class TestRollingWindow:
    def test_push_and_evict(self):
        w = RollingWindow(5)
        for i in range(10):
            w.push(float(i))
        assert len(w) == 5
        assert w.mean() == pytest.approx(7.0)

    def test_percentile(self):
        w = RollingWindow(100)
        for i in range(100):
            w.push(float(i + 1))
        assert w.percentile(50) == pytest.approx(50.5, abs=2)


class TestModelHealthMonitor:
    def test_register_model(self, model_ids):
        mon = ModelHealthMonitor()
        for mid in model_ids:
            mon.register_model(mid, baseline_sharpe=2.0)
        # Should not crash

    def test_on_trade_updates(self, model_ids):
        mon = ModelHealthMonitor()
        mon.register_model("xgboost")
        mon.on_trade("xgboost", pnl=100, sharpe=2.5, win_rate=0.6, pf=1.8, mdd=0.03)
        assert mon.get_sharpe_50("xgboost") == pytest.approx(2.5)
        assert mon.get_consecutive_losses("xgboost") == 0

    def test_consecutive_losses(self):
        mon = ModelHealthMonitor()
        mon.register_model("lstm")
        mon.on_trade("lstm", pnl=-50, sharpe=-0.5, win_rate=0.4, pf=0.8, mdd=0.05)
        mon.on_trade("lstm", pnl=-30, sharpe=-0.3, win_rate=0.3, pf=0.7, mdd=0.06)
        mon.on_trade("lstm", pnl=-20, sharpe=-0.2, win_rate=0.2, pf=0.6, mdd=0.07)
        assert mon.get_consecutive_losses("lstm") == 3

    def test_compute_score(self):
        mon = ModelHealthMonitor()
        mon.register_model("xgboost", baseline_sharpe=2.0)
        for i in range(10):
            mon.on_trade("xgboost", pnl=100, sharpe=2.5, win_rate=0.6, pf=2.0, mdd=0.02)
        score = mon.compute_score("xgboost")
        assert 0 <= score <= 100


class TestDetectionEngine:
    def test_degradation_detected(self):
        mon = ModelHealthMonitor()
        mon.register_model("xgboost", baseline_sharpe=3.0)
        # High Sharpe in W250
        for _ in range(250):
            mon.on_trade("xgboost", pnl=100, sharpe=3.0, win_rate=0.6, pf=2.0, mdd=0.02)
        # Low Sharpe in W50 (degradation)
        for _ in range(50):
            mon.on_trade("xgboost", pnl=-50, sharpe=1.0, win_rate=0.3, pf=0.5, mdd=0.05)

        det = DetectionEngine(mon)
        events = det.run_all(["xgboost"], risk_score=90, eqs=90, regime_conf=85)
        # Should detect degradation (D1) or overfitting (D4) or instability (D3)
        assert len(events) > 0

    def test_instability_detected(self):
        mon = ModelHealthMonitor()
        mon.register_model("lstm")
        for _ in range(5):
            mon.on_trade("lstm", pnl=-50, sharpe=-0.5, win_rate=0.0, pf=0.0, mdd=0.05)
        det = DetectionEngine(mon)
        events = det.run_all(["lstm"], risk_score=90, eqs=90, regime_conf=85)
        instability = [e for e in events if e.detector_id == "D3_INSTABILITY"]
        assert len(instability) == 1
        assert instability[0].severity == "CRITICAL"

    def test_risk_detected(self):
        mon = ModelHealthMonitor()
        mon.register_model("xgboost")
        det = DetectionEngine(mon)
        events = det.run_all(["xgboost"], risk_score=50, eqs=90, regime_conf=85)
        risk_events = [e for e in events if e.detector_id == "D6_RISK"]
        assert len(risk_events) == 1

    def test_no_events_when_healthy(self):
        mon = ModelHealthMonitor()
        mon.register_model("xgboost")
        for _ in range(100):
            mon.on_trade("xgboost", pnl=100, sharpe=2.5, win_rate=0.6, pf=2.0, mdd=0.02)
        det = DetectionEngine(mon)
        events = det.run_all(["xgboost"], risk_score=95, eqs=95, regime_conf=90)
        assert len(events) == 0


class TestDecisionEngine:
    def test_green_when_healthy(self):
        dec = DecisionEngine()
        scores = HealthScores(
            model_health={"xgb": 95}, execution_quality=95,
            risk=95, broker_quality={"b": 95}, regime_confidence=90, overall=95,
        )
        status = dec.decide(scores, [])
        assert status == SystemStatus.GREEN

    def test_yellow_when_moderate(self):
        dec = DecisionEngine()
        scores = HealthScores(
            model_health={"xgb": 75}, execution_quality=85,
            risk=85, broker_quality={"b": 85}, regime_confidence=80, overall=78,
        )
        status = dec.decide(scores, [])
        assert status == SystemStatus.YELLOW

    def test_red_when_critical(self):
        dec = DecisionEngine()
        scores = HealthScores(
            model_health={"xgb": 50}, execution_quality=60,
            risk=50, broker_quality={"b": 60}, regime_confidence=50, overall=50,
        )
        event = DetectionEvent("D1", "CRITICAL", "xgb", 0.5, 1.0, "test")
        status = dec.decide(scores, [event])
        assert status == SystemStatus.RED


class TestActionEngine:
    def test_yellow_actions(self):
        engine = ActionEngine()
        scores = HealthScores(
            model_health={"xgb": 70, "lstm": 90}, execution_quality=80,
            risk=80, broker_quality={"b": 80}, regime_confidence=80, overall=75,
        )
        actions = engine.get_actions_for_status(SystemStatus.YELLOW, scores, [])
        assert any(a[0] == ControlAction.REDUCE_INFLUENCE for a in actions)

    def test_red_actions(self):
        engine = ActionEngine()
        scores = HealthScores(
            model_health={"xgb": 40, "lstm": 90}, execution_quality=60,
            risk=50, broker_quality={"b": 60}, regime_confidence=50, overall=45,
        )
        actions = engine.get_actions_for_status(SystemStatus.RED, scores, [])
        assert any(a[0] == ControlAction.DISABLE_MODEL for a in actions)
        assert any(a[0] == ControlAction.EMERGENCY_RISK_REDUCTION for a in actions)

    def test_preserve_actions(self):
        engine = ActionEngine()
        scores = HealthScores(
            model_health={"xgb": 30}, execution_quality=40,
            risk=30, broker_quality={"b": 40}, regime_confidence=30, overall=30,
        )
        actions = engine.get_actions_for_status(SystemStatus.RED_PRESERVE, scores, [])
        assert any(a[0] == ControlAction.CAPITAL_PRESERVATION for a in actions)


class TestCEOSupervisor:
    def test_initial_status_green(self, ceo):
        assert ceo.status == SystemStatus.GREEN

    def test_run_cycle_healthy(self, ceo, model_ids):
        for mid in model_ids:
            for _ in range(10):
                ceo.on_trade(mid, pnl=100, sharpe=2.5, win_rate=0.6, pf=2.0, mdd=0.02)
        status, scores = ceo.run_cycle(risk_score=95, eqs=95, regime_conf=90)
        assert status == SystemStatus.GREEN
        assert scores.overall > 0

    def test_run_cycle_degraded(self, ceo, model_ids):
        for _ in range(10):
            ceo.on_trade("xgboost", pnl=-100, sharpe=-1.0, win_rate=0.1, pf=0.3, mdd=0.08)
        status, scores = ceo.run_cycle(risk_score=50, eqs=50, regime_conf=40)
        assert status in [SystemStatus.RED, SystemStatus.YELLOW]

    def test_cycle_count_increments(self, ceo):
        ceo.run_cycle()
        assert ceo.cycle_count == 1
        ceo.run_cycle()
        assert ceo.cycle_count == 2

    def test_does_not_generate_signals(self, ceo):
        """CEO must NOT have any entry/exit methods."""
        assert not hasattr(ceo, "generate_signal")
        assert not hasattr(ceo, "place_order")
        assert not hasattr(ceo, "execute_trade")

    def test_no_rl_in_ceo(self, ceo):
        """CEO must NOT use RL — only statistical detectors."""
        import inspect
        source = inspect.getsource(type(ceo))
        assert "torch" not in source.lower()
        assert "policy" not in source.lower()
        assert "reward_function" not in source.lower()
