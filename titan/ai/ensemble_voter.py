"""
TITAN XAU AI — Ensemble Voter (Module 9e)
Weighted voting from 4 models (XGBoost + LSTM + Transformer + RL).
Confidence threshold, quorum check, dynamic weight support.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from .base_model import IModel, Prediction, ModelType, ModelStatus

logger = logging.getLogger(__name__)


@dataclass
class EnsembleResult:
    """Final ensemble voting result."""
    direction: int               # +1 long, -1 short, 0 flat
    confidence: float            # 0.0 - 1.0
    agreeing_models: int         # how many models agreed
    total_models: int            # total models that voted
    weights_used: dict[str, float] = field(default_factory=dict)
    individual_predictions: list[Prediction] = field(default_factory=list)
    quorum_met: bool = True
    evaluation_time_ms: float = 0.0
    timestamp: float = field(default_factory=time.time)


class EnsembleVoter:
    """
    Ensemble voting layer.
    - Weighted voting: each model's vote × its weight
    - Confidence threshold: signal executes only if confidence ≥ threshold
    - Quorum: at least 2/4 models must agree
    - Dynamic weights: set_weights() called by Weighting Engine (M19)
    """

    def __init__(self, config: dict = None):
        cfg = config or {}
        self._models: dict[str, IModel] = {}
        self._weights: dict[str, float] = {}
        self._default_weight = 0.25  # Equal 25% each
        self._min_confidence = cfg.get("min_confidence", 0.65)
        self._quorum = cfg.get("quorum", 3)  # 3 of 4 must agree (configurable)
        self._total_votes = 0
        self._executed_signals = 0

    def register_model(self, model: IModel, weight: float = None) -> None:
        """Register a model with the ensemble."""
        self._models[model.model_id] = model
        self._weights[model.model_id] = weight if weight is not None else self._default_weight
        logger.info(
            f"Model registered: {model.model_id} "
            f"(type={model.model_type.value}, weight={self._weights[model.model_id]:.2f})"
        )

    def set_weights(self, weights: dict[str, float]) -> None:
        """Set dynamic weights (called by Weighting Engine M19)."""
        for model_id, weight in weights.items():
            if model_id in self._weights:
                self._weights[model_id] = max(0.0, min(1.0, weight))
        # Normalize weights to sum to 1.0
        total = sum(self._weights.values())
        if total > 0:
            for k in self._weights:
                self._weights[k] /= total
        logger.info(f"Weights updated: {self._weights}")

    def disable_model(self, model_id: str) -> None:
        """Disable a model (weight = 0). Called by CEO Supervisor."""
        if model_id in self._weights:
            self._weights[model_id] = 0.0
            logger.warning(f"Model disabled: {model_id}")

    def enable_model(self, model_id: str, weight: float = None) -> None:
        """Re-enable a previously disabled model."""
        if model_id in self._weights:
            self._weights[model_id] = weight if weight else self._default_weight
            logger.info(f"Model re-enabled: {model_id} (weight={self._weights[model_id]:.2f})")

    def vote(self, features: dict[str, np.ndarray] = None) -> EnsembleResult:
        """
        Run all models and compute weighted ensemble vote.
        features: dict mapping model_id → input features.
        If None, uses default features for all models.
        """
        start = time.perf_counter()
        self._total_votes += 1

        predictions: list[Prediction] = []
        active_models = 0

        for model_id, model in self._models.items():
            weight = self._weights.get(model_id, 0.0)

            # Skip disabled models (weight = 0)
            if weight <= 0.0:
                continue

            if model.status != ModelStatus.READY:
                logger.warning(f"Model {model_id} not ready (status={model.status.value})")
                continue

            # Get features for this model
            if features and model_id in features:
                feat = features[model_id]
            else:
                # Generate dummy features for testing
                if model.model_type in (ModelType.LSTM, ModelType.TRANSFORMER):
                    feat = np.random.randn(60, 87).astype(np.float32) * 0.01
                else:
                    feat = np.random.randn(87).astype(np.float32) * 0.01

            pred = model.predict(feat)
            pred.confidence *= weight  # Weight the confidence
            predictions.append(pred)
            active_models += 1

        if not predictions:
            return EnsembleResult(
                direction=0, confidence=0.0,
                agreeing_models=0, total_models=0,
                quorum_met=False,
                evaluation_time_ms=(time.perf_counter() - start) * 1000,
            )

        # Weighted vote
        direction_scores = {-1: 0.0, 0: 0.0, 1: 0.0}
        for pred in predictions:
            direction_scores[pred.direction] += pred.confidence

        # Best direction
        best_direction = max(direction_scores, key=direction_scores.get)
        best_score = direction_scores[best_direction]

        # Count agreeing models (unweighted)
        agreeing = sum(1 for p in predictions if p.direction == best_direction)

        # Total confidence (normalized)
        total_weight = sum(self._weights.get(p.model_id, 0) for p in predictions)
        confidence = best_score / total_weight if total_weight > 0 else 0.0

        # Quorum check
        quorum_met = agreeing >= min(self._quorum, active_models)

        # Confidence threshold
        if confidence < self._min_confidence:
            best_direction = 0  # Flat if below threshold
            quorum_met = False

        elapsed_ms = (time.perf_counter() - start) * 1000

        if best_direction != 0 and quorum_met:
            self._executed_signals += 1

        return EnsembleResult(
            direction=best_direction,
            confidence=confidence,
            agreeing_models=agreeing,
            total_models=active_models,
            weights_used={k: v for k, v in self._weights.items() if v > 0},
            individual_predictions=predictions,
            quorum_met=quorum_met,
            evaluation_time_ms=elapsed_ms,
        )

    @property
    def registered_models(self) -> list[str]:
        return list(self._models.keys())

    @property
    def active_models(self) -> int:
        return sum(1 for w in self._weights.values() if w > 0)

    @property
    def current_weights(self) -> dict[str, float]:
        return dict(self._weights)

    @property
    def stats(self) -> dict:
        return {
            "total_votes": self._total_votes,
            "executed_signals": self._executed_signals,
            "active_models": self.active_models,
        }


# ─── B2: Optuna-based HPO for XGBoost / LSTM / Transformer ──────────────
# Time-series-safe optimization: each trial uses PurgedKFold (from
# titan.training.dataset_validator) with a purge gap = max(target_horizons)
# to prevent label leakage during hyperparameter evaluation.


import logging
_hpo_logger = logging.getLogger(__name__ + ".hpo")


@dataclass
class HPOTrial:
    """Record of a single HPO trial."""
    trial_num: int
    params: dict
    score: float
    train_rows: int = 0
    val_rows: int = 0
    duration_seconds: float = 0.0


@dataclass
class HPOResult:
    """Result of an Optuna HPO run."""
    best_params: dict
    best_score: float
    n_trials: int
    trials: list[HPOTrial] = field(default_factory=list)
    model_type: str = ""
    duration_seconds: float = 0.0
    storage_path: str | None = None

    def to_dict(self) -> dict:
        return {
            "best_params": self.best_params,
            "best_score": round(self.best_score, 6),
            "n_trials": self.n_trials,
            "model_type": self.model_type,
            "duration_seconds": round(self.duration_seconds, 3),
            "storage_path": self.storage_path,
            "trials": [
                {"trial_num": t.trial_num, "params": t.params,
                 "score": round(t.score, 6)}
                for t in self.trials
            ],
        }


class HyperparameterOptimizer:
    """Optuna-based HPO with time-series-safe cross-validation.

    Wraps Optuna to search hyperparameter spaces for XGBoost, LSTM, and
    Transformer models. Each trial evaluates hyperparameters using
    PurgedKFold (purge = max target horizon) to prevent label leakage.

    The optimizer is CPU-only and stores trials in an in-memory Optuna
    journal (no external DB required). For persistence, pass a storage
    path (SQLite) and the trials will be resumable.
    """

    # Per-model search spaces (conservative, CPU-friendly)
    XGBOOST_SPACE = {
        "max_depth": (3, 8),
        "learning_rate": (0.01, 0.3),
        "n_estimators": (100, 500),
        "min_child_weight": (1, 10),
        "subsample": (0.6, 1.0),
        "colsample_bytree": (0.6, 1.0),
    }
    LSTM_SPACE = {
        "hidden_size": (32, 128),
        "num_layers": (1, 3),
        "learning_rate": (0.0001, 0.01),
        "batch_size": (16, 64),
        "dropout": (0.0, 0.4),
    }
    TRANSFORMER_SPACE = {
        "num_heads": (2, 8),
        "num_layers": (2, 6),
        "hidden_size": (32, 128),
        "learning_rate": (0.0001, 0.01),
        "batch_size": (16, 64),
        "dropout": (0.0, 0.4),
    }

    def __init__(self, n_trials: int = 20, purge: int = 60,
                 embargo: int = 10, n_splits: int = 3,
                 storage_path: str | None = None, seed: int = 42):
        """
        Parameters
        ----------
        n_trials : int
            Number of Optuna trials to run.
        purge : int
            Bars to drop between train and val in each fold. Should
            equal max(target_horizons).
        embargo : int
            Bars to drop after each val_end.
        n_splits : int
            Number of purged k-fold splits.
        storage_path : str | None
            If set, Optuna persists trials to this SQLite path (resumable).
        seed : int
            Random seed for reproducibility.
        """
        self.n_trials = n_trials
        self.purge = purge
        self.embargo = embargo
        self.n_splits = n_splits
        self.storage_path = storage_path
        self.seed = seed

    def optimize_xgboost(self, X, y) -> HPOResult:
        """Optimize XGBoost hyperparameters. X: (n, features), y: (n,)."""
        return self._optimize("xgboost", X, y)

    def optimize_lstm(self, X, y) -> HPOResult:
        """Optimize LSTM hyperparameters. X: (n, seq, features), y: (n,)."""
        return self._optimize("lstm", X, y)

    def optimize_transformer(self, X, y) -> HPOResult:
        """Optimize Transformer hyperparameters. X: (n, seq, features), y: (n,)."""
        return self._optimize("transformer", X, y)

    def _optimize(self, model_type: str, X, y) -> HPOResult:
        import time
        try:
            import optuna
            optuna.logging.set_verbosity(optuna.logging.WARNING)
        except ImportError as e:
            raise ImportError(
                "optuna is required for HPO. Install with: pip install optuna"
            ) from e
        from titan.training.dataset_validator import PurgedKFold

        n = len(X) if hasattr(X, "__len__") else X.shape[0]
        if n < 100:
            raise ValueError(
                f"Too few samples for HPO: {n} (need ≥ 100)"
            )

        space = {
            "xgboost": self.XGBOOST_SPACE,
            "lstm": self.LSTM_SPACE,
            "transformer": self.TRANSFORMER_SPACE,
        }[model_type]

        sampler = optuna.samplers.TPESampler(seed=self.seed)
        study = optuna.create_study(
            direction="maximize",
            sampler=sampler,
            storage=self.storage_path,
            study_name=f"titan_hpo_{model_type}",
            load_if_exists=self.storage_path is not None,
        )

        trials_log: list[HPOTrial] = []
        t0 = time.perf_counter()

        def objective(trial):
            params = {}
            for k, (lo, hi) in space.items():
                if isinstance(lo, int) and isinstance(hi, int):
                    params[k] = trial.suggest_int(k, lo, hi)
                else:
                    params[k] = trial.suggest_float(k, lo, hi, log=(k == "learning_rate"))
            # Time-series-safe cross-validation
            kf = PurgedKFold(n_splits=self.n_splits, purge=self.purge,
                             embargo=self.embargo)
            folds = kf.split(n)
            fold_scores: list[float] = []
            for fold in folds.folds:
                tr_start, tr_end = fold.train_start, fold.train_end
                te_start, te_end = fold.test_start, fold.test_end
                if tr_end - tr_start < 10 or te_end - te_start < 5:
                    continue
                X_tr = _slice(X, tr_start, tr_end)
                y_tr = _slice(y, tr_start, tr_end)
                X_te = _slice(X, te_start, te_end)
                y_te = _slice(y, te_start, te_end)
                score = _evaluate_model(model_type, params, X_tr, y_tr, X_te, y_te)
                fold_scores.append(score)
            if not fold_scores:
                return 0.0
            mean_score = float(np.mean(fold_scores))
            trials_log.append(HPOTrial(
                trial_num=len(trials_log) + 1,
                params=params,
                score=mean_score,
                train_rows=tr_end - tr_start,
                val_rows=te_end - te_start,
            ))
            return mean_score

        study.optimize(objective, n_trials=self.n_trials, show_progress_bar=False)
        elapsed = time.perf_counter() - t0
        best = study.best_trial
        return HPOResult(
            best_params=best.params,
            best_score=best.value,
            n_trials=len(trials_log),
            trials=trials_log,
            model_type=model_type,
            duration_seconds=elapsed,
            storage_path=self.storage_path,
        )


def _slice(arr, start: int, end: int):
    """Slice array-like (numpy, list, DataFrame) by index range."""
    if hasattr(arr, "iloc"):
        return arr.iloc[start:end]
    return arr[start:end]


def _evaluate_model(model_type: str, params: dict, X_tr, y_tr, X_te, y_te) -> float:
    """Evaluate a model with given params on a single fold. Returns accuracy."""
    try:
        import numpy as np
        # Convert to numpy for consistent indexing
        X_tr_np = np.asarray(X_tr)
        y_tr_np = np.asarray(y_tr)
        X_te_np = np.asarray(X_te)
        y_te_np = np.asarray(y_te)
        # Coerce labels to int (3-class: 0/1/2)
        y_tr_int = _discretize_targets(y_tr_np)
        y_te_int = _discretize_targets(y_te_np)
        if model_type == "xgboost":
            return _eval_xgboost(params, X_tr_np, y_tr_int, X_te_np, y_te_int)
        elif model_type == "lstm":
            return _eval_lstm(params, X_tr_np, y_tr_int, X_te_np, y_te_int)
        else:
            return _eval_transformer(params, X_tr_np, y_tr_int, X_te_np, y_te_int)
    except Exception as e:
        _hpo_logger.debug(f"HPO trial failed: {e}")
        return 0.0


def _discretize_targets(y: np.ndarray, threshold: float = 0.0) -> np.ndarray:
    """Convert continuous returns to 3-class labels: 0 (short), 1 (flat), 2 (long)."""
    classes = np.ones(len(y), dtype=int)
    classes[y > threshold] = 2
    classes[y < -threshold] = 0
    return classes


def _eval_xgboost(params: dict, X_tr, y_tr, X_te, y_te) -> float:
    """Train a lightweight XGBoost on the fold and return validation accuracy."""
    try:
        import xgboost as xgb
    except ImportError:
        from sklearn.ensemble import GradientBoostingClassifier
        clf = GradientBoostingClassifier(
            n_estimators=min(100, int(params.get("n_estimators", 100))),
            max_depth=int(params.get("max_depth", 5)),
            learning_rate=float(params.get("learning_rate", 0.05)),
            random_state=42,
        )
        clf.fit(X_tr, y_tr)
        return float(clf.score(X_te, y_te))
    # Cap n_estimators for HPO speed
    p = dict(params)
    p["n_estimators"] = min(int(p["n_estimators"]), 100)
    p["tree_method"] = "hist"
    p["n_jobs"] = 2
    p["seed"] = 42
    p["objective"] = "multi:softprob"
    p["num_class"] = 3
    p["eval_metric"] = "mlogloss"
    p["verbosity"] = 0
    dtr = xgb.DMatrix(X_tr, label=y_tr)
    dte = xgb.DMatrix(X_te, label=y_te)
    bst = xgb.train(p, dtr, num_boost_round=p["n_estimators"])
    preds = bst.predict(dte)
    pred_classes = np.argmax(preds, axis=1)
    return float((pred_classes == y_te).mean())


def _eval_lstm(params: dict, X_tr, y_tr, X_te, y_te) -> float:
    """Train a lightweight LSTM on the fold and return validation accuracy."""
    try:
        import torch
        import torch.nn as nn
    except ImportError:
        # Fallback: use sklearn LogisticRegression as a stand-in
        from sklearn.linear_model import LogisticRegression
        # Flatten if 3D
        if X_tr.ndim == 3:
            X_tr_flat = X_tr.reshape(X_tr.shape[0], -1)
            X_te_flat = X_te.reshape(X_te.shape[0], -1)
        else:
            X_tr_flat, X_te_flat = X_tr, X_te
        clf = LogisticRegression(max_iter=200, random_state=42)
        clf.fit(X_tr_flat, y_tr)
        return float(clf.score(X_te_flat, y_te))
    # Build a tiny LSTM
    hidden = int(params.get("hidden_size", 32))
    layers = int(params.get("num_layers", 1))
    lr = float(params.get("learning_rate", 0.001))
    dropout = float(params.get("dropout", 0.0))
    epochs = 3  # cap for HPO speed
    if X_tr.ndim == 2:
        # Treat as (n, features) → add a synthetic seq dim of 1
        X_tr = X_tr[:, np.newaxis, :]
        X_te = X_te[:, np.newaxis, :]
    input_size = X_tr.shape[2]
    class _Net(nn.Module):
        def __init__(self):
            super().__init__()
            self.lstm = nn.LSTM(input_size, hidden, layers,
                                dropout=dropout, batch_first=True)
            self.fc = nn.Linear(hidden, 3)
        def forward(self, x):
            _, (h, _) = self.lstm(x)
            return self.fc(h[-1])
    torch.manual_seed(42)
    net = _Net()
    opt = torch.optim.Adam(net.parameters(), lr=lr)
    crit = nn.CrossEntropyLoss()
    # Mini-batch
    bs = min(int(params.get("batch_size", 32)), len(X_tr))
    net.train()
    for ep in range(epochs):
        for i in range(0, len(X_tr), bs):
            xb = torch.FloatTensor(X_tr[i:i+bs])
            yb = torch.LongTensor(y_tr[i:i+bs])
            opt.zero_grad()
            out = net(xb)
            loss = crit(out, yb)
            loss.backward()
            opt.step()
    net.eval()
    with torch.no_grad():
        out = net(torch.FloatTensor(X_te))
        preds = out.argmax(dim=1).numpy()
    return float((preds == y_te).mean())


def _eval_transformer(params: dict, X_tr, y_tr, X_te, y_te) -> float:
    """Train a lightweight Transformer on the fold and return validation accuracy.

    For CPU HPO speed, we delegate to the LSTM evaluator with transformer-
    style hyperparameters mapped to the LSTM-style architecture. The
    real Transformer (titan.ai.transformer_model) is trained separately
    with the best params found here.
    """
    return _eval_lstm(params, X_tr, y_tr, X_te, y_te)


__all__ = [
    "EnsembleVoter", "EnsembleResult",
]
__all__.extend([
    "HyperparameterOptimizer", "HPOResult", "HPOTrial",
])