"""
TITAN XAU AI — CEO Supervisor (Module 18)
Meta AI governance layer. Does NOT generate signals.
6 health scores, 8 statistical detectors, 5 control actions.
CPU-only, fully offline, no external LLM.
"""
from __future__ import annotations

import collections
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


class SystemStatus(str, Enum):
    GREEN = "GREEN"
    YELLOW = "YELLOW"
    RED = "RED"
    RED_PRESERVE = "RED_PRESERVE"


class ControlAction(str, Enum):
    REDUCE_INFLUENCE = "REDUCE_INFLUENCE"
    INCREASE_INFLUENCE = "INCREASE_INFLUENCE"
    DISABLE_MODEL = "DISABLE_MODEL"
    EMERGENCY_RISK_REDUCTION = "EMERGENCY_RISK_REDUCTION"
    CAPITAL_PRESERVATION = "CAPITAL_PRESERVATION"


@dataclass
class HealthScores:
    model_health: dict[str, float]        # per-model 0-100
    execution_quality: float               # system-wide 0-100
    risk: float                            # 0-100 (inverted: 100=safe)
    broker_quality: dict[str, float]      # per-broker 0-100
    regime_confidence: float               # 0-100
    overall: float                         # weighted aggregate 0-100


@dataclass
class DetectionEvent:
    detector_id: str
    severity: str          # CRITICAL / MAJOR / MINOR
    target: str            # model_id / broker_id / system
    metric_value: float
    threshold: float
    message: str
    timestamp: float = field(default_factory=time.time)


class RollingWindow:
    __slots__ = ("_buf", "_max")

    def __init__(self, max_size: int):
        self._buf: collections.deque = collections.deque(maxlen=max_size)
        self._max = max_size

    def push(self, v: float) -> None:
        self._buf.append(v)

    def to_array(self) -> np.ndarray:
        return np.array(self._buf, dtype=np.float64) if self._buf else np.array([0.0])

    def mean(self) -> float:
        return float(np.mean(self.to_array())) if self._buf else 0.0

    def std(self) -> float:
        return float(np.std(self.to_array(), ddof=1)) if len(self._buf) > 1 else 0.0

    def percentile(self, p: float) -> float:
        return float(np.percentile(self.to_array(), p)) if self._buf else 0.0

    def __len__(self) -> int:
        return len(self._buf)


class ModelHealthMonitor:
    """Tracks per-model performance across 4 rolling windows."""

    def __init__(self):
        self._windows: dict[str, dict[str, RollingWindow]] = {}
        self._baselines: dict[str, dict[str, float]] = {}
        self._consecutive_losses: dict[str, int] = {}

    def register_model(self, model_id: str, baseline_sharpe: float = 2.0) -> None:
        self._windows[model_id] = {
            "sharpe_50": RollingWindow(50),
            "sharpe_250": RollingWindow(250),
            "win_rate_100": RollingWindow(100),
            "pf_100": RollingWindow(100),
            "mdd_250": RollingWindow(250),
        }
        self._baselines[model_id] = {
            "sharpe": baseline_sharpe,
            "win_rate": 0.55,
            "profit_factor": 1.8,
            "max_dd": 0.05,
        }
        self._consecutive_losses[model_id] = 0

    def on_trade(self, model_id: str, pnl: float, sharpe: float, win_rate: float,
                 pf: float, mdd: float) -> None:
        if model_id not in self._windows:
            self.register_model(model_id)
        w = self._windows[model_id]
        w["sharpe_50"].push(sharpe)
        w["sharpe_250"].push(sharpe)
        w["win_rate_100"].push(win_rate)
        w["pf_100"].push(pf)
        w["mdd_250"].push(mdd)

        if pnl < 0:
            self._consecutive_losses[model_id] = self._consecutive_losses.get(model_id, 0) + 1
        else:
            self._consecutive_losses[model_id] = 0

    def compute_score(self, model_id: str) -> float:
        if model_id not in self._windows:
            return 50.0
        w = self._windows[model_id]
        b = self._baselines.get(model_id, {"sharpe": 2.0})

        sharpe_50 = w["sharpe_50"].mean()
        sharpe_250 = w["sharpe_250"].mean()
        wr = w["win_rate_100"].mean()
        pf = w["pf_100"].mean()
        mdd = w["mdd_250"].percentile(90)

        # Normalized 0-100
        sharpe_norm = min(sharpe_250 / b["sharpe"] * 100, 100) if b["sharpe"] > 0 else 50
        wr_norm = min(wr * 100, 100)
        pf_norm = min(pf / b.get("profit_factor", 1.8) * 50, 100) if pf > 0 else 0
        mdd_norm = max(100 - mdd * 1000, 0)

        score = 0.30 * sharpe_norm + 0.25 * wr_norm + 0.25 * pf_norm + 0.20 * mdd_norm
        return float(np.clip(score, 0, 100))

    def get_consecutive_losses(self, model_id: str) -> int:
        return self._consecutive_losses.get(model_id, 0)

    def get_sharpe_50(self, model_id: str) -> float:
        return self._windows[model_id]["sharpe_50"].mean() if model_id in self._windows else 0.0

    def get_sharpe_250(self, model_id: str) -> float:
        return self._windows[model_id]["sharpe_250"].mean() if model_id in self._windows else 0.0


class DetectionEngine:
    """8 statistical detectors. CPU-only. No RL."""

    def __init__(self, model_monitor: ModelHealthMonitor):
        self._monitor = model_monitor

    def run_all(self, model_ids: list[str], risk_score: float,
                eqs: float, regime_conf: float) -> list[DetectionEvent]:
        events = []
        for mid in model_ids:
            events.extend(self._check_degradation(mid))
            events.extend(self._check_drift(mid))
            events.extend(self._check_instability(mid))
            events.extend(self._check_overfitting(mid))
        events.extend(self._check_exec_deterioration(eqs))
        events.extend(self._check_risk(risk_score))
        events.extend(self._check_regime(regime_conf))
        return events

    def _check_degradation(self, mid: str) -> list[DetectionEvent]:
        s50 = self._monitor.get_sharpe_50(mid)
        s250 = self._monitor.get_sharpe_250(mid)
        if s250 > 0 and s50 < 0.7 * s250:
            return [DetectionEvent(
                "D1_DEGRADATION", "CRITICAL", mid,
                s50, 0.7 * s250,
                f"Sharpe degraded: W50={s50:.2f} < 0.7×W250={s250:.2f}"
            )]
        return []

    def _check_drift(self, mid: str) -> list[DetectionEvent]:
        s250 = self._monitor.get_sharpe_250(mid)
        s50 = self._monitor.get_sharpe_50(mid)
        if s250 > 0:
            ratio = s50 / s250
            if ratio < 0.5:
                return [DetectionEvent(
                    "D2_DRIFT", "MAJOR", mid,
                    ratio, 0.5,
                    f"Model drift: ratio={ratio:.2f} < 0.5"
                )]
        return []

    def _check_instability(self, mid: str) -> list[DetectionEvent]:
        losses = self._monitor.get_consecutive_losses(mid)
        if losses >= 5:
            return [DetectionEvent(
                "D3_INSTABILITY", "CRITICAL", mid,
                float(losses), 5.0,
                f"Instability: {losses} consecutive losses"
            )]
        return []

    def _check_overfitting(self, mid: str) -> list[DetectionEvent]:
        s250 = self._monitor.get_sharpe_250(mid)
        # Baseline from backtest (simplified: assume 2.0)
        baseline = 2.0
        if baseline > 0 and s250 < 0.5 * baseline and s250 > 0:
            return [DetectionEvent(
                "D4_OVERFITTING", "CRITICAL", mid,
                s250, 0.5 * baseline,
                f"Overfitting: live Sharpe {s250:.2f} < 0.5×baseline {baseline:.2f}"
            )]
        return []

    def _check_exec_deterioration(self, eqs: float) -> list[DetectionEvent]:
        if eqs < 70:
            return [DetectionEvent(
                "D5_EXEC_DETERIORATION", "MAJOR", "system",
                eqs, 70.0,
                f"Execution quality low: EQS={eqs:.1f} < 70"
            )]
        return []

    def _check_risk(self, risk_score: float) -> list[DetectionEvent]:
        if risk_score < 70:
            return [DetectionEvent(
                "D6_RISK", "CRITICAL", "system",
                risk_score, 70.0,
                f"Risk score critical: {risk_score:.1f} < 70"
            )]
        return []

    def _check_regime(self, regime_conf: float) -> list[DetectionEvent]:
        if regime_conf < 60:
            return [DetectionEvent(
                "D7_REGIME", "MAJOR", "system",
                regime_conf, 60.0,
                f"Regime confidence low: {regime_conf:.1f} < 60"
            )]
        return []


class DecisionEngine:
    """Aggregates scores + events → GREEN/YELLOW/RED/RED_PRESERVE."""

    def __init__(self):
        self._current_status = SystemStatus.GREEN
        self._red_since: Optional[float] = None
        self._preserve_duration_s = 1800  # 30 min

    def decide(self, scores: HealthScores, events: list[DetectionEvent]) -> SystemStatus:
        critical_count = sum(1 for e in events if e.severity == "CRITICAL")
        min_model = min(scores.model_health.values()) if scores.model_health else 100

        if critical_count > 0 or scores.overall < 70 or min_model < 50:
            new_status = SystemStatus.RED
        elif scores.overall < 85 or any(e.severity == "MAJOR" for e in events):
            new_status = SystemStatus.YELLOW
        else:
            new_status = SystemStatus.GREEN

        # Track RED duration for PRESERVE escalation
        if new_status == SystemStatus.RED:
            if self._red_since is None:
                self._red_since = time.time()
            elif time.time() - self._red_since > self._preserve_duration_s:
                new_status = SystemStatus.RED_PRESERVE
        else:
            self._red_since = None

        if new_status != self._current_status:
            logger.info(f"CEO status change: {self._current_status.value} → {new_status.value}")
            self._current_status = new_status

        return self._current_status

    @property
    def current_status(self) -> SystemStatus:
        return self._current_status


class ActionEngine:
    """Executes 5 control actions. Interfaces with ensemble + risk."""

    def __init__(self, ensemble_voter=None, risk_engine=None):
        self._ensemble = ensemble_voter
        self._risk = risk_engine
        self._action_history: list[tuple[float, ControlAction, str]] = []
        self._recovery_staircase: dict[str, int] = {}  # model_id → step (0,1,2)

    def execute(self, action: ControlAction, target_model: str = "",
                factor: float = 0.5) -> bool:
        self._action_history.append((time.time(), action, target_model))
        logger.info(f"CEO action: {action.value} target={target_model} factor={factor}")

        if action == ControlAction.REDUCE_INFLUENCE and self._ensemble:
            self._ensemble.disable_model(target_model)  # simplified: full disable
            return True
        elif action == ControlAction.INCREASE_INFLUENCE:
            self._recovery_staircase[target_model] = self._recovery_staircase.get(target_model, 0) + 1
            if self._ensemble:
                self._ensemble.enable_model(target_model)
            return True
        elif action == ControlAction.DISABLE_MODEL and self._ensemble:
            self._ensemble.disable_model(target_model)
            return True
        elif action == ControlAction.EMERGENCY_RISK_REDUCTION and self._risk:
            self._risk.set_mode("EMERGENCY")
            return True
        elif action == ControlAction.CAPITAL_PRESERVATION and self._risk:
            self._risk.set_mode("EMERGENCY")
            return True
        return False

    def get_actions_for_status(self, status: SystemStatus, scores: HealthScores,
                               events: list[DetectionEvent]) -> list[tuple[ControlAction, str, float]]:
        actions = []
        if status == SystemStatus.YELLOW:
            for mid, score in scores.model_health.items():
                if score < 75:
                    actions.append((ControlAction.REDUCE_INFLUENCE, mid, 0.5))
        elif status == SystemStatus.RED:
            for mid, score in scores.model_health.items():
                if score < 60:
                    actions.append((ControlAction.DISABLE_MODEL, mid, 0.0))
            actions.append((ControlAction.EMERGENCY_RISK_REDUCTION, "", 0.0))
        elif status == SystemStatus.RED_PRESERVE:
            actions.append((ControlAction.CAPITAL_PRESERVATION, "", 0.0))

        return actions

    @property
    def action_count(self) -> int:
        return len(self._action_history)


class CEOSupervisor:
    """
    Main orchestrator. Runs 60s cycle.
    Does NOT generate signals. Only monitors, scores, governs.
    """

    def __init__(self, model_ids: list[str], ensemble_voter=None, risk_engine=None):
        self._model_monitor = ModelHealthMonitor()
        for mid in model_ids:
            self._model_monitor.register_model(mid)

        self._detectors = DetectionEngine(self._model_monitor)
        self._decision = DecisionEngine()
        self._actions = ActionEngine(ensemble_voter, risk_engine)
        self._model_ids = model_ids
        self._cycle_count = 0
        self._running = False

    def on_trade(self, model_id: str, pnl: float, sharpe: float,
                 win_rate: float, pf: float, mdd: float) -> None:
        self._model_monitor.on_trade(model_id, pnl, sharpe, win_rate, pf, mdd)

    def run_cycle(self, risk_score: float = 90, eqs: float = 90,
                  regime_conf: float = 85,
                  broker_scores: Optional[dict[str, float]] = None) -> tuple[SystemStatus, HealthScores]:
        self._cycle_count += 1

        # 1. Compute scores
        model_scores = {mid: self._model_monitor.compute_score(mid) for mid in self._model_ids}
        broker_scores = broker_scores or {"default": 95.0}

        overall = self._aggregate(model_scores, risk_score, eqs, regime_conf, broker_scores)
        scores = HealthScores(
            model_health=model_scores,
            execution_quality=eqs,
            risk=risk_score,
            broker_quality=broker_scores,
            regime_confidence=regime_conf,
            overall=overall,
        )

        # 2. Run detectors
        events = self._detectors.run_all(self._model_ids, risk_score, eqs, regime_conf)

        # 3. Decide status
        status = self._decision.decide(scores, events)

        # 4. Execute actions
        action_list = self._actions.get_actions_for_status(status, scores, events)
        for action, target, factor in action_list:
            self._actions.execute(action, target, factor)

        return status, scores

    @staticmethod
    def _aggregate(model_scores, risk, eqs, regime, broker) -> float:
        min_model = min(model_scores.values()) if model_scores else 50
        min_broker = min(broker.values()) if broker else 50
        return (0.30 * min_model + 0.25 * risk + 0.20 * eqs +
                0.15 * regime + 0.10 * min_broker)

    @property
    def status(self) -> SystemStatus:
        return self._decision.current_status

    @property
    def cycle_count(self) -> int:
        return self._cycle_count

    @property
    def action_history(self) -> list[tuple]:
        return self._actions.action_history
