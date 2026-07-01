"""
TITAN XAU AI - Alpha Candidate Generator (research layer)
=========================================================

Generates *candidate* alpha variants for offline research and shadow
evaluation. Candidates are pure metadata records — no model is trained,
no order is sent, no live runtime is touched.

Safety invariants (enforced structurally):
    * NEVER imports MetaTrader5.
    * NEVER calls mt5.order_send / any broker order API.
    * NEVER adds martingale, grid, averaging, or loss_based_lot_multiplier.
    * NEVER auto-enables live trading. Every candidate defaults to
      status="CANDIDATE" and may only be promoted through the
      AlphaEvaluator + AlphaRegistry pipeline with explicit human approval.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Optional


# ──────────────────────────────────────────────────────────────────────────
# Safety contract (constant — surfaced in every persisted record)
# ──────────────────────────────────────────────────────────────────────────
SAFETY_CONTRACT: dict[str, bool] = {
    "no_martingale": True,
    "no_grid": True,
    "no_averaging": True,
    "no_loss_based_lot_multiplier": True,
    "no_auto_live": True,
    "no_order_send": True,
}


@dataclass
class AlphaCandidate:
    """A single alpha candidate (metadata only — never executable live).

    Attributes
    ----------
    name : str
        Short human-readable identifier (unique within a registry).
    description : str
        Free-form description of the alpha idea / formula.
    formula_type : str
        Categorical label, e.g. "MOMENTUM", "MEAN_REVERSION", "REGIME",
        "ENSEMBLE_VOTER", "EXIT_POLICY".
    parameters : dict
        Hyper-parameters of the candidate (lookback, threshold, etc.).
    status : str
        Lifecycle status. Defaults to "CANDIDATE". Promotion is governed
        by AlphaEvaluator — never set to a live status here.
    safety : dict
        Frozen safety flags (martingale / grid / averaging / auto-live /
        order_send). Always populated from SAFETY_CONTRACT.
    created_utc : str
        ISO-8601 UTC timestamp of registration.
    """

    name: str
    description: str
    formula_type: str
    parameters: dict[str, Any] = field(default_factory=dict)
    status: str = "CANDIDATE"
    safety: dict[str, bool] = field(default_factory=lambda: dict(SAFETY_CONTRACT))
    created_utc: str = ""
    source: str = "research"
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.created_utc:
            self.created_utc = datetime.now(timezone.utc).isoformat()
        # Re-affirm the safety contract every time a candidate is
        # instantiated — guarantees the flags cannot be silently disabled.
        self.safety = dict(SAFETY_CONTRACT) | {
            k: v for k, v in self.safety.items() if k not in SAFETY_CONTRACT
        }
        # Hard invariant: live status is never set at construction time.
        forbidden_live_statuses = {
            "APPROVED_FOR_LIVE",
            "LIVE",
            "LIVE_PENDING_HUMAN",
        }
        if self.status in forbidden_live_statuses:
            raise ValueError(
                f"AlphaCandidate cannot be constructed with live status "
                f"'{self.status}'. Promotion to live requires explicit "
                f"human approval via AlphaEvaluator."
            )

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["safety"] = dict(self.safety)
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AlphaCandidate":
        return cls(
            name=data["name"],
            description=data.get("description", ""),
            formula_type=data.get("formula_type", "UNKNOWN"),
            parameters=dict(data.get("parameters", {}) or {}),
            status=data.get("status", "CANDIDATE"),
            safety=dict(data.get("safety", SAFETY_CONTRACT)),
            created_utc=data.get("created_utc", ""),
            source=data.get("source", "research"),
            notes=data.get("notes", ""),
        )


# ──────────────────────────────────────────────────────────────────────────
# Generator
# ──────────────────────────────────────────────────────────────────────────
class AlphaCandidateGenerator:
    """Generates candidate alphas from a small built-in template library.

    The generator is deterministic and offline. It does NOT:
        * fetch market data
        * train any model
        * call any broker API
        * enable live trading
    """

    DEFAULT_TEMPLATES: list[dict[str, Any]] = [
        {
            "name": "momentum_h1_roc",
            "description": "Rate-of-change momentum on H1 close, threshold-gated.",
            "formula_type": "MOMENTUM",
            "parameters": {"lookback": 14, "threshold": 0.0015, "timeframe": "H1"},
        },
        {
            "name": "mean_reversion_m15_zscore",
            "description": "Z-score mean reversion on M15 with regime filter.",
            "formula_type": "MEAN_REVERSION",
            "parameters": {"lookback": 30, "z_threshold": 2.0, "timeframe": "M15"},
        },
        {
            "name": "regime_specialist_trending",
            "description": "Regime-specialist alpha active only in trending regimes.",
            "formula_type": "REGIME",
            "parameters": {"regime": "TRENDING", "min_confidence": 0.65},
        },
        {
            "name": "ensemble_voter_three_model",
            "description": "Ensemble voter combining LSTM, XGBoost, and transformer signals.",
            "formula_type": "ENSEMBLE_VOTER",
            "parameters": {"voters": ["lstm_v2", "xgboost_v2", "transformer_v1"], "quorum": 2},
        },
        {
            "name": "exit_policy_adaptive_trailing",
            "description": "Adaptive trailing exit policy variant for existing positions.",
            "formula_type": "EXIT_POLICY",
            "parameters": {"atr_multiple": 1.8, "tighten_after_mfe_r": 1.0},
        },
    ]

    def __init__(self, templates: Optional[list[dict[str, Any]]] = None) -> None:
        self._templates = list(templates) if templates is not None else [
            dict(t) for t in self.DEFAULT_TEMPLATES
        ]

    # ── public API ────────────────────────────────────────────────────
    def generate_candidates(self) -> list[AlphaCandidate]:
        """Generate AlphaCandidate objects from the configured templates.

        Every returned candidate has status="CANDIDATE" — never a live
        status. The returned list is independent of the templates (deep
        copy of parameters).
        """
        out: list[AlphaCandidate] = []
        for tpl in self._templates:
            params = {k: v for k, v in tpl.get("parameters", {}).items()}
            cand = AlphaCandidate(
                name=tpl["name"],
                description=tpl.get("description", ""),
                formula_type=tpl.get("formula_type", "UNKNOWN"),
                parameters=params,
                status="CANDIDATE",
                source=tpl.get("source", "research"),
                notes=tpl.get("notes", ""),
            )
            out.append(cand)
        return out

    def register_candidate(
        self,
        candidate: AlphaCandidate,
        registry: "AlphaRegistry",  # noqa: F821 — forward type hint
    ) -> "AlphaRegistry":  # noqa: F821
        """Register a single candidate into an AlphaRegistry.

        This does NOT promote the candidate — it stays at status="CANDIDATE"
        until the AlphaEvaluator runs. Returns the registry for chaining.
        """
        # Import locally to avoid an import cycle at module load.
        from titan.research.alpha_factory.alpha_registry import AlphaRegistry  # type: ignore

        if not isinstance(registry, AlphaRegistry):
            raise TypeError("registry must be an AlphaRegistry instance")
        if candidate.status != "CANDIDATE":
            raise ValueError(
                f"register_candidate only accepts status='CANDIDATE'; "
                f"got '{candidate.status}'. Use AlphaEvaluator to promote."
            )
        registry.register(candidate)
        return registry

    # ── safety surface ────────────────────────────────────────────────
    @staticmethod
    def safety_contract() -> dict[str, bool]:
        """Return the immutable safety contract."""
        return dict(SAFETY_CONTRACT)
