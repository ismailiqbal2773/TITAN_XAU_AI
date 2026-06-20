"""
TITAN XAU AI — Dynamic Weighting Engine (Module 19)
No fixed weights. 4 algorithms compete via Meta-Bandit.
Bayesian + Weighted Voting + Thompson Sampling MAB + Online Linear.
CPU-only, NumPy, no GPU, no cloud.
"""
from __future__ import annotations

import collections
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

MODELS = ("xgboost", "lstm", "transformer", "rl_manager")
ALGORITHMS = ("bayesian", "weighted_voting", "mab_thompson", "online_linear")


class WeightingAlgorithm(str, Enum):
    BAYESIAN = "bayesian"
    WEIGHTED_VOTING = "weighted_voting"
    MAB_THOMPSON = "mab_thompson"
    ONLINE_LINEAR = "online_linear"


@dataclass
class ModelMetrics:
    """7 performance metrics per model."""
    accuracy: float = 0.5
    profit_factor: float = 1.0
    sharpe: float = 0.0
    dd_contribution: float = 0.0
    slippage_sensitivity: float = 0.0
    latency_sensitivity: float = 0.0
    regime_performance: float = 0.5


@dataclass
class WeightingInputs:
    """8 inputs from NATS + CEO."""
    predictions: dict = field(default_factory=dict)
    confidence: dict = field(default_factory=dict)
    regime: str = "trend"
    eqs: float = 90.0
    risk_score: float = 90.0
    broker_score: float = 90.0
    ceo_caps: dict = field(default_factory=dict)
    ceo_disabled: set = field(default_factory=set)


@dataclass
class ModelWeights:
    """4 weights, sum=1.0, each in [0, cap]."""
    weights: dict[str, float]
    algorithm_used: str
    regime: str
    timestamp: float = field(default_factory=time.time)


# ─── IWeightingAlgorithm Interface ───

class IWeightingAlgorithm(ABC):
    @abstractmethod
    def compute_weights(self, metrics: dict[str, ModelMetrics],
                        inputs: WeightingInputs) -> dict[str, float]:
        pass

    @abstractmethod
    def update(self, model_id: str, outcome: float) -> None:
        pass


# ─── Algorithm 1: Bayesian Weighting ───

class BayesianWeighting(IWeightingAlgorithm):
    """Beta-Binomial conjugate prior. Sample from posterior → weights."""

    def __init__(self, alpha0: float = 1.0, beta0: float = 1.0):
        self._priors = {m: (alpha0, beta0) for m in MODELS}

    def compute_weights(self, metrics, inputs):
        samples = {}
        for m in MODELS:
            a, b = self._priors[m]
            samples[m] = float(np.random.beta(a, b))
        total = sum(samples.values())
        return {m: s / total for m, s in samples.items()} if total > 0 else {m: 0.25 for m in MODELS}

    def update(self, model_id, outcome):
        a, b = self._priors[model_id]
        if outcome > 0:
            self._priors[model_id] = (a + 1, b)
        else:
            self._priors[model_id] = (a, b + 1)


# ─── Algorithm 2: Weighted Voting ───

class WeightedVoting(IWeightingAlgorithm):
    """Exponential weighting: weight ∝ exp(λ × Sharpe)."""

    def __init__(self, lam: float = 2.0, decay: float = 0.95):
        self._lam = lam
        self._ewma = {m: 0.0 for m in MODELS}
        self._decay = decay

    def compute_weights(self, metrics, inputs):
        exp_vals = {m: float(np.exp(self._lam * self._ewma[m])) for m in MODELS}
        total = sum(exp_vals.values())
        return {m: v / total for m, v in exp_vals.items()} if total > 0 else {m: 0.25 for m in MODELS}

    def update(self, model_id, outcome):
        self._ewma[model_id] = self._decay * self._ewma[model_id] + (1 - self._decay) * outcome


# ─── Algorithm 3: Thompson Sampling MAB ───

class ThompsonSamplingMAB(IWeightingAlgorithm):
    """Multi-Armed Bandit with Thompson Sampling. Optimal exploration-exploitation."""

    def __init__(self, tau: float = 0.5):
        self._arms = {m: (1.0, 1.0) for m in MODELS}  # Beta(1,1) uniform
        self._tau = tau

    def compute_weights(self, metrics, inputs):
        samples = {}
        for m in MODELS:
            a, b = self._arms[m]
            conf = inputs.confidence.get(m, 0.5)
            samples[m] = float(np.random.beta(a * (1 + conf), b))
        vals = np.array(list(samples.values()))
        exp_vals = np.exp(vals / self._tau)
        weights = exp_vals / exp_vals.sum()
        return dict(zip(MODELS, weights))

    def update(self, model_id, reward):
        a, b = self._arms[model_id]
        if reward > 0.5:
            self._arms[model_id] = (a + 1, b)
        else:
            self._arms[model_id] = (a, b + 1)


# ─── Algorithm 4: Online Linear Regression ───

class OnlineLinearRegression(IWeightingAlgorithm):
    """Online SGD on 7-feature → weight mapping."""

    def __init__(self, lr: float = 0.01):
        self._W = np.zeros((4, 7))  # 4 models × 7 metrics
        self._lr = lr
        self._epoch = 0

    def compute_weights(self, metrics, inputs):
        features = np.array([
            [metrics[m].accuracy, metrics[m].profit_factor, metrics[m].sharpe,
             metrics[m].dd_contribution, metrics[m].slippage_sensitivity,
             metrics[m].latency_sensitivity, metrics[m].regime_performance]
            for m in MODELS
        ])  # 4×7
        raw = self._W @ features.T  # 4×4
        logits = np.diag(raw)
        exp_vals = np.exp(logits - logits.max())
        weights = exp_vals / exp_vals.sum()
        return dict(zip(MODELS, weights))

    def update(self, model_id, outcome):
        self._epoch += 1
        lr = self._lr / np.sqrt(1 + self._epoch)
        idx = list(MODELS).index(model_id)
        # Simple gradient: move weight toward outcome
        self._W[idx] += lr * outcome

    def update_gradient(self, gradient: np.ndarray):
        self._epoch += 1
        lr = self._lr / np.sqrt(1 + self._epoch)
        self._W -= lr * gradient


# ─── Meta-Bandit: selects best algorithm per regime ───

class MetaBandit:
    """Thompson Sampling over 4 algorithms, per regime."""

    REGIMES = ("trend", "range", "volatile", "news")

    def __init__(self):
        self._posteriors = {
            regime: {algo: (1.0, 1.0) for algo in ALGORITHMS}
            for regime in self.REGIMES
        }
        self._quality_threshold = 0.0

    def select_algorithm(self, regime: str) -> str:
        if regime not in self._posteriors:
            regime = "trend"
        samples = {}
        for algo in ALGORITHMS:
            a, b = self._posteriors[regime][algo]
            samples[algo] = float(np.random.beta(a, b))
        return max(samples, key=samples.get)

    def update(self, algo_id: str, regime: str, quality: float) -> None:
        if regime not in self._posteriors:
            regime = "trend"
        a, b = self._posteriors[regime][algo_id]
        if quality > self._quality_threshold:
            self._posteriors[regime][algo_id] = (a + 1, b)
        else:
            self._posteriors[regime][algo_id] = (a, b + 1)

    def get_best_algorithm(self, regime: str) -> str:
        if regime not in self._posteriors:
            regime = "trend"
        means = {algo: a / (a + b) for algo, (a, b) in self._posteriors[regime].items()}
        return max(means, key=means.get)


# ─── Main Engine ───

class WeightingEngine:
    """
    Main orchestrator. Computes dynamic weights every 60s.
    No fixed weights. Meta-Bandit selects best algorithm per regime.
    """

    def __init__(self, ensemble_voter=None, ceo_supervisor=None):
        self._algos: dict[str, IWeightingAlgorithm] = {
            "bayesian": BayesianWeighting(),
            "weighted_voting": WeightedVoting(),
            "mab_thompson": ThompsonSamplingMAB(),
            "online_linear": OnlineLinearRegression(),
        }
        self._meta_bandit = MetaBandit()
        self._ensemble = ensemble_voter
        self._ceo = ceo_supervisor
        self._current_weights: Optional[ModelWeights] = None
        self._cycle_count = 0

    def run_cycle(self, metrics: dict[str, ModelMetrics],
                  inputs: WeightingInputs) -> ModelWeights:
        self._cycle_count += 1

        # 1. Run all 4 algorithms
        algo_weights = {
            name: algo.compute_weights(metrics, inputs)
            for name, algo in self._algos.items()
        }

        # 2. Meta-Bandit selects best for current regime
        selected = self._meta_bandit.select_algorithm(inputs.regime)
        weights = algo_weights[selected]

        # 3. Apply CEO directives (caps + disabled)
        weights = self._apply_ceo_directives(weights, inputs)

        # 4. Normalize
        weights = self._normalize(weights)

        result = ModelWeights(
            weights=weights,
            algorithm_used=selected,
            regime=inputs.regime,
        )

        # 5. Emit to ensemble voter
        if self._ensemble:
            self._ensemble.set_weights(weights)

        self._current_weights = result
        return result

    def _apply_ceo_directives(self, w: dict, inputs: WeightingInputs) -> dict:
        for m in MODELS:
            if m in inputs.ceo_disabled:
                w[m] = 0.0
            elif m in inputs.ceo_caps:
                w[m] = min(w[m], inputs.ceo_caps[m])
        return w

    @staticmethod
    def _normalize(w: dict) -> dict:
        total = sum(w.values())
        if total == 0:
            active = [m for m in MODELS if w[m] > 0]
            if not active:
                return {m: 0.25 for m in MODELS}
            n = len(active)
            return {m: (1.0 / n if w[m] > 0 else 0.0) for m in MODELS}
        return {m: v / total for m, v in w.items()}

    def on_trade_outcome(self, model_id: str, reward: float, regime: str,
                         weight_quality: float = 0.0) -> None:
        """Feedback loop — update all algorithms + Meta-Bandit."""
        for algo in self._algos.values():
            algo.update(model_id, reward)

        if self._current_weights:
            self._meta_bandit.update(self._current_weights.algorithm_used, regime, weight_quality)

    @property
    def current_weights(self) -> Optional[ModelWeights]:
        return self._current_weights

    @property
    def cycle_count(self) -> int:
        return self._cycle_count

    @property
    def meta_bandit_best(self) -> dict[str, str]:
        return {r: self._meta_bandit.get_best_algorithm(r) for r in MetaBandit.REGIMES}
