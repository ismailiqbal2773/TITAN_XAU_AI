"""
TITAN XAU AI - Alpha Registry (research layer)
==============================================

Persists alpha candidates and their evaluations to a JSON file under
``data/audit/alpha_factory/alpha_registry.json``.

The registry is the *single source of truth* for which alphas exist and
what their current lifecycle status is. It is read by:
    * the audit script (``scripts/research/run_alpha_factory_audit.py``)
    * the operator console (read-only)
    * downstream shadow / demo orchestrators (read-only)

The registry NEVER:
    * imports MetaTrader5
    * calls mt5.order_send
    * deploys an alpha to a live runtime
    * adds martingale / grid / averaging / loss_based_lot_multiplier
"""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from titan.research.alpha_factory.alpha_candidate_generator import (
    AlphaCandidate,
    SAFETY_CONTRACT as CAND_SAFETY,
)
from titan.research.alpha_factory.alpha_evaluator import (
    AlphaEvaluation,
    AlphaStatus,
    ALL_STATUSES,
    SAFETY_CONTRACT as EV_SAFETY,
)


# ──────────────────────────────────────────────────────────────────────────
# Default persistence path
# ──────────────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_REGISTRY_PATH = REPO_ROOT / "data" / "audit" / "alpha_factory" / "alpha_registry.json"


class AlphaRegistry:
    """JSON-backed registry of alpha candidates and their evaluations.

    The registry is intentionally simple — a dict-of-records serialized
    to a single JSON file. Concurrency control is the responsibility of
    the caller (single-writer model in the audit / research CLI).
    """

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path: Path = Path(path) if path is not None else DEFAULT_REGISTRY_PATH
        self._candidates: dict[str, AlphaCandidate] = {}
        self._evaluations: dict[str, AlphaEvaluation] = {}
        self._load()

    # ── public API ────────────────────────────────────────────────────
    def register(self, candidate: AlphaCandidate) -> AlphaCandidate:
        """Register a new candidate. Rejects duplicates.

        The candidate's status must be ``CANDIDATE`` — promotion is the
        evaluator's job, not the registry's.
        """
        if candidate.name in self._candidates:
            raise ValueError(f"Alpha already registered: {candidate.name}")
        if candidate.status != "CANDIDATE":
            raise ValueError(
                f"register() only accepts status='CANDIDATE'; "
                f"got '{candidate.status}' for '{candidate.name}'."
            )
        # Re-affirm safety contract on the way in.
        candidate.safety = dict(CAND_SAFETY) | {
            k: v for k, v in candidate.safety.items() if k not in CAND_SAFETY
        }
        self._candidates[candidate.name] = candidate
        self._save()
        return candidate

    def get_candidate(self, name: str) -> Optional[AlphaCandidate]:
        return self._candidates.get(name)

    def get_evaluation(self, name: str) -> Optional[AlphaEvaluation]:
        return self._evaluations.get(name)

    def get_status(self, name: str) -> Optional[str]:
        """Return the current lifecycle status for an alpha.

        If an evaluation exists, its status wins; otherwise the candidate's
        CANDIDATE status is returned. Returns None if the alpha is unknown.
        """
        if name not in self._candidates:
            return None
        ev = self._evaluations.get(name)
        if ev is not None:
            return ev.status
        return self._candidates[name].status

    def list_all(self) -> list[dict[str, Any]]:
        """List every alpha with its candidate metadata + evaluation (if any)."""
        out: list[dict[str, Any]] = []
        for name, cand in self._candidates.items():
            ev = self._evaluations.get(name)
            out.append(
                {
                    "name": name,
                    "description": cand.description,
                    "formula_type": cand.formula_type,
                    "parameters": dict(cand.parameters),
                    "candidate_status": cand.status,
                    "evaluation_status": ev.status if ev is not None else None,
                    "current_status": self.get_status(name),
                    "safety": dict(cand.safety),
                    "created_utc": cand.created_utc,
                    "evaluated_utc": ev.evaluated_utc if ev is not None else None,
                }
            )
        return out

    def get_approved_for_demo(self) -> list[str]:
        """Return names of alphas whose evaluation status is APPROVED_FOR_DEMO.

        (Excludes APPROVED_FOR_LIVE_PENDING_HUMAN — those have already
        advanced past the demo gate.)
        """
        return [
            name
            for name, ev in self._evaluations.items()
            if ev.status == AlphaStatus.APPROVED_FOR_DEMO
        ]

    def get_pending_human_live(self) -> list[str]:
        """Return names of alphas awaiting explicit human live approval."""
        return [
            name
            for name, ev in self._evaluations.items()
            if ev.status == AlphaStatus.APPROVED_FOR_LIVE_PENDING_HUMAN
        ]

    def store_evaluation(self, evaluation: AlphaEvaluation) -> AlphaEvaluation:
        """Attach (or overwrite) the evaluation for a registered candidate.

        The evaluation's safety contract is re-affirmed on write.
        """
        name = evaluation.alpha_name
        if name not in self._candidates:
            raise ValueError(
                f"Cannot store evaluation for unregistered alpha: {name}"
            )
        if evaluation.status not in ALL_STATUSES:
            raise ValueError(
                f"Unknown evaluation status: {evaluation.status!r}. "
                f"Expected one of {ALL_STATUSES}."
            )
        evaluation.safety = dict(EV_SAFETY) | {
            k: v for k, v in evaluation.safety.items() if k not in EV_SAFETY
        }
        self._evaluations[name] = evaluation
        self._save()
        return evaluation

    # ── persistence ───────────────────────────────────────────────────
    def _save(self) -> None:
        payload = self._to_payload()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, sort_keys=True)
        tmp.replace(self.path)

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            with self.path.open("r", encoding="utf-8") as f:
                payload = json.load(f)
        except (OSError, json.JSONDecodeError):
            # Treat corrupted registry as empty — never raise during load.
            return
        for c in payload.get("candidates", []):
            try:
                cand = AlphaCandidate.from_dict(c)
            except Exception:
                continue
            self._candidates[cand.name] = cand
        for e in payload.get("evaluations", []):
            try:
                ev = AlphaEvaluation.from_dict(e)
            except Exception:
                continue
            self._evaluations[ev.alpha_name] = ev

    def _to_payload(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "generated_utc": datetime.now(timezone.utc).isoformat(),
            "safety_contract": dict(CAND_SAFETY),
            "candidates": [c.to_dict() for c in self._candidates.values()],
            "evaluations": [e.to_dict() for e in self._evaluations.values()],
            "summary": {
                "total_candidates": len(self._candidates),
                "total_evaluations": len(self._evaluations),
                "by_status": self._count_by_status(),
            },
        }

    def _count_by_status(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for name in self._candidates:
            st = self.get_status(name) or "UNKNOWN"
            counts[st] = counts.get(st, 0) + 1
        return counts

    # ── safety surface ────────────────────────────────────────────────
    @staticmethod
    def safety_contract() -> dict[str, bool]:
        return dict(CAND_SAFETY)
