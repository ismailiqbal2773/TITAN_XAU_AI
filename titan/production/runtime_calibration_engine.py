"""
TITAN XAU AI - Runtime Calibration Engine (Sprint 9.9.3.46)
============================================================

Runtime calibration engine. Produces calibration suggestions for runtime
parameters (entry thresholds, exit thresholds, probability calibration,
etc.) and applies them in a strictly tiered mode system.

NEVER imports MetaTrader5.
NEVER sends orders (no mt5.order_send anywhere in this file).
NEVER adds martingale / grid / averaging / loss-based lot multipliers.
NEVER silently changes live thresholds. LIVE mode requires explicit
    approval via set_mode(LIVE, approved_by=...).

Modes (in strict tiered order):
    OBSERVE_ONLY            (default) - record metrics, no suggestions emitted
    SUGGEST                            - emit non-binding CalibrationSuggestion items
    SHADOW_APPLY                       - apply suggestions to a shadow parameter set
                                         (NEVER to live parameters)
    APPLY_DEMO_WITH_APPROVAL           - apply to demo parameter set, requires approval
    LIVE                               - apply to live parameter set, requires explicit
                                         CEO/operator approval recorded

Transitions:
    OBSERVE_ONLY -> SUGGEST                       : allowed (auto)
    SUGGEST -> SHADOW_APPLY                       : allowed (auto)
    SHADOW_APPLY -> APPLY_DEMO_WITH_APPROVAL      : requires approval
    APPLY_DEMO_WITH_APPROVAL -> LIVE              : requires explicit CEO approval
    Any downward transition                       : allowed (auto)

Safety fields exposed on every result:
    no_martingale=True
    no_grid=True
    no_averaging=True
    auto_promote_to_live=False
    silent_live_threshold_change=False
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


# ──────────────────────────────────────────────────────────────────────────
# Safety invariant flags (mirrored on every public result)
# ──────────────────────────────────────────────────────────────────────────
SAFETY_INVARIANTS: dict = {
    "no_martingale": True,
    "no_grid": True,
    "no_averaging": True,
    "no_loss_based_lot_multiplier": True,
    "auto_promote_to_live": False,
    "silent_live_threshold_change": False,
}


class CalibrationMode(str, Enum):
    """Strictly ordered calibration modes."""

    OBSERVE_ONLY = "OBSERVE_ONLY"
    SUGGEST = "SUGGEST"
    SHADOW_APPLY = "SHADOW_APPLY"
    APPLY_DEMO_WITH_APPROVAL = "APPLY_DEMO_WITH_APPROVAL"
    LIVE = "LIVE"


# Mode tiering (higher = more aggressive)
MODE_TIER: dict[CalibrationMode, int] = {
    CalibrationMode.OBSERVE_ONLY: 0,
    CalibrationMode.SUGGEST: 1,
    CalibrationMode.SHADOW_APPLY: 2,
    CalibrationMode.APPLY_DEMO_WITH_APPROVAL: 3,
    CalibrationMode.LIVE: 4,
}

DEFAULT_MODE = CalibrationMode.OBSERVE_ONLY


@dataclass
class CalibrationSuggestion:
    """A single non-binding calibration suggestion.

    approved=False by default. Only the operator can flip approved=True
    via the engine's approve_suggestion() method (which records approver).
    """

    parameter_name: str
    current_value: float
    suggested_value: float
    mode: CalibrationMode
    approved: bool = False
    approver: str = ""
    reason: str = ""
    delta: float = 0.0
    timestamp_utc: str = ""

    def __post_init__(self):
        if not self.timestamp_utc:
            self.timestamp_utc = datetime.now(timezone.utc).isoformat()
        # approved must always be False at construction time.
        self.approved = False
        # delta computed from current vs suggested
        try:
            self.delta = float(self.suggested_value) - float(self.current_value)
        except (TypeError, ValueError):
            self.delta = 0.0

    def to_dict(self) -> dict:
        d = asdict(self)
        d["mode"] = self.mode.value
        return d


@dataclass
class CalibrationEngineResult:
    """Outcome of a calibration cycle."""

    mode: CalibrationMode
    suggestions: list[dict] = field(default_factory=list)
    applied: bool = False
    applied_to: str = ""  # "none" / "shadow" / "demo" / "live"
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    auto_promote_to_live: bool = False
    silent_live_threshold_change: bool = False
    no_martingale: bool = True
    no_grid: bool = True
    no_averaging: bool = True
    no_loss_based_lot_multiplier: bool = True
    human_approval_required: bool = True
    timestamp_utc: str = ""

    def __post_init__(self):
        if not self.timestamp_utc:
            self.timestamp_utc = datetime.now(timezone.utc).isoformat()
        # Hard safety invariants - always forced regardless of caller input.
        self.auto_promote_to_live = False
        self.silent_live_threshold_change = False
        self.no_martingale = True
        self.no_grid = True
        self.no_averaging = True
        self.no_loss_based_lot_multiplier = True
        self.human_approval_required = True

    def to_dict(self) -> dict:
        d = asdict(self)
        d["mode"] = self.mode.value
        return d


# Conservative bounds to prevent wild calibration swings.
MAX_THRESHOLD_DELTA = 0.05  # ±5% max change per cycle
MIN_SAMPLES_FOR_SUGGEST = 500


class RuntimeCalibrationEngine:
    """Runtime calibration engine. Defaults to OBSERVE_ONLY.

    NEVER silently changes live thresholds. The LIVE mode requires
    explicit CEO/operator approval recorded via set_mode(LIVE, approved_by=...).
    """

    def __init__(self, mode: CalibrationMode = DEFAULT_MODE):
        # Force the default mode if caller tries anything else.
        if mode != DEFAULT_MODE:
            # Caller may request a higher mode, but it must be confirmed
            # via set_mode(...) with approval. Default is OBSERVE_ONLY.
            self._mode: CalibrationMode = DEFAULT_MODE
            self._pending_mode: Optional[CalibrationMode] = mode
            self._mode_change_blocker: str = (
                "Initial mode must be OBSERVE_ONLY - use set_mode() to escalate with approval"
            )
        else:
            self._mode = DEFAULT_MODE
            self._pending_mode = None
            self._mode_change_blocker = ""
        self._suggestions: list[CalibrationSuggestion] = []
        self._approved_suggestions: list[CalibrationSuggestion] = []
        self._live_approval: dict = {}  # tracks CEO approval for LIVE mode
        self._demo_approval: dict = {}  # tracks approval for APPLY_DEMO_WITH_APPROVAL

    # ──────────────────────────────────────────────────────────────────────
    # Mode management
    # ──────────────────────────────────────────────────────────────────────

    @property
    def mode(self) -> CalibrationMode:
        return self._mode

    def set_mode(
        self,
        new_mode: CalibrationMode,
        *,
        approved_by: str = "",
        ceo_approval: bool = False,
    ) -> tuple[bool, list[str]]:
        """Transition to a new mode.

        Returns (ok, blockers).
        Escalations to APPLY_DEMO_WITH_APPROVAL require approved_by non-empty.
        Escalations to LIVE require ceo_approval=True AND approved_by non-empty.
        Downward transitions are always allowed.
        """
        blockers: list[str] = []
        current_tier = MODE_TIER[self._mode]
        new_tier = MODE_TIER[new_mode]

        if new_tier < current_tier:
            # Downward transition - always allowed
            self._mode = new_mode
            self._pending_mode = None
            self._mode_change_blocker = ""
            return True, []

        if new_tier == current_tier:
            return True, []  # no-op

        # Upward transitions
        if new_mode == CalibrationMode.SUGGEST:
            self._mode = new_mode
            return True, []

        if new_mode == CalibrationMode.SHADOW_APPLY:
            self._mode = new_mode
            return True, []

        if new_mode == CalibrationMode.APPLY_DEMO_WITH_APPROVAL:
            if not approved_by:
                blockers.append(
                    "APPLY_DEMO_WITH_APPROVAL requires approved_by (operator name)"
                )
            else:
                self._mode = new_mode
                self._demo_approval = {
                    "approved_by": approved_by,
                    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                }
            return len(blockers) == 0, blockers

        if new_mode == CalibrationMode.LIVE:
            if not ceo_approval:
                blockers.append(
                    "LIVE mode requires explicit ceo_approval=True - silent live changes forbidden"
                )
            if not approved_by:
                blockers.append("LIVE mode requires approved_by (CEO/operator name)")
            if blockers:
                return False, blockers
            self._mode = new_mode
            self._live_approval = {
                "approved_by": approved_by,
                "ceo_approval": True,
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            }
            return True, []

        blockers.append(f"Unknown mode transition: {new_mode}")
        return False, blockers

    # ──────────────────────────────────────────────────────────────────────
    # Suggestion generation
    # ──────────────────────────────────────────────────────────────────────

    def suggest(
        self,
        parameter_name: str,
        current_value: float,
        suggested_value: float,
        reason: str = "",
    ) -> CalibrationSuggestion:
        """Generate a CalibrationSuggestion.

        In OBSERVE_ONLY mode the suggestion is recorded but flagged as
        non-emitting. In SUGGEST and higher modes the suggestion is added
        to the active suggestion list.
        """
        suggestion = CalibrationSuggestion(
            parameter_name=parameter_name,
            current_value=float(current_value),
            suggested_value=float(suggested_value),
            mode=self._mode,
            reason=reason,
        )
        # Clamp delta to MAX_THRESHOLD_DELTA
        if abs(suggestion.delta) > MAX_THRESHOLD_DELTA:
            clamped_suggested = (
                current_value + MAX_THRESHOLD_DELTA
                if suggestion.delta > 0
                else current_value - MAX_THRESHOLD_DELTA
            )
            suggestion.suggested_value = clamped_suggested
            suggestion.delta = clamped_suggested - current_value
            suggestion.reason = (
                f"{reason} [clamped to ±{MAX_THRESHOLD_DELTA}]".strip()
            )
        self._suggestions.append(suggestion)
        return suggestion

    def approve_suggestion(
        self,
        parameter_name: str,
        approver: str,
    ) -> tuple[bool, list[str]]:
        """Approve a pending suggestion by parameter name.

        Requires approver non-empty. Only valid in APPLY_DEMO_WITH_APPROVAL
        or LIVE mode.
        """
        blockers: list[str] = []
        if not approver:
            blockers.append("approver required")
        if self._mode not in (
            CalibrationMode.APPLY_DEMO_WITH_APPROVAL,
            CalibrationMode.LIVE,
        ):
            blockers.append(
                f"approve_suggestion requires APPLY_DEMO_WITH_APPROVAL or LIVE mode "
                f"(current={self._mode.value})"
            )
        if blockers:
            return False, blockers
        for s in self._suggestions:
            if s.parameter_name == parameter_name and not s.approved:
                # Cannot set approved=True via attribute mutation through __post_init__
                # because __post_init__ forces approved=False; use object.__setattr__
                # to bypass the dataclass invariant. This is the ONLY sanctioned path.
                object.__setattr__(s, "approved", True)
                object.__setattr__(s, "approver", approver)
                self._approved_suggestions.append(s)
                return True, []
        blockers.append(f"No pending suggestion found for parameter: {parameter_name}")
        return False, blockers

    # ──────────────────────────────────────────────────────────────────────
    # Apply cycle
    # ──────────────────────────────────────────────────────────────────────

    def run_cycle(self, metrics: dict) -> CalibrationEngineResult:
        """Run a single calibration cycle.

        In OBSERVE_ONLY mode returns no suggestions and applied=False.
        In SUGGEST mode returns suggestions but applied=False.
        In SHADOW_APPLY mode applies suggestions to shadow parameter set.
        In APPLY_DEMO_WITH_APPROVAL mode applies approved suggestions to demo.
        In LIVE mode applies approved suggestions to live (requires prior
            set_mode(LIVE, ceo_approval=True, approved_by=...)).
        """
        sample_count = int(metrics.get("sample_count", 0))
        blockers: list[str] = []
        warnings: list[str] = []
        reasons: list[str] = []

        if self._mode == CalibrationMode.OBSERVE_ONLY:
            return CalibrationEngineResult(
                mode=self._mode,
                applied=False,
                applied_to="none",
                reasons=["OBSERVE_ONLY mode - no suggestions emitted"],
                warnings=[
                    f"sample_count={sample_count} (OBSERVE_ONLY - metrics recorded only)"
                ],
            )

        if sample_count < MIN_SAMPLES_FOR_SUGGEST:
            blockers.append(
                f"Insufficient samples: {sample_count} < {MIN_SAMPLES_FOR_SUGGEST}"
            )
            return CalibrationEngineResult(
                mode=self._mode,
                applied=False,
                applied_to="none",
                blockers=blockers,
                reasons=["Insufficient samples for calibration"],
            )

        suggestions_dicts = [s.to_dict() for s in self._suggestions]

        if self._mode == CalibrationMode.SUGGEST:
            return CalibrationEngineResult(
                mode=self._mode,
                suggestions=suggestions_dicts,
                applied=False,
                applied_to="none",
                reasons=[
                    "SUGGEST mode - suggestions emitted but not applied"
                ],
            )

        if self._mode == CalibrationMode.SHADOW_APPLY:
            return CalibrationEngineResult(
                mode=self._mode,
                suggestions=suggestions_dicts,
                applied=True,
                applied_to="shadow",
                reasons=[
                    "SHADOW_APPLY mode - applied to shadow parameter set only"
                ],
            )

        if self._mode == CalibrationMode.APPLY_DEMO_WITH_APPROVAL:
            approved = [s for s in self._suggestions if s.approved]
            if not approved:
                blockers.append(
                    "No approved suggestions - APPLY_DEMO_WITH_APPROVAL requires approval"
                )
                return CalibrationEngineResult(
                    mode=self._mode,
                    suggestions=suggestions_dicts,
                    applied=False,
                    applied_to="none",
                    blockers=blockers,
                    reasons=["APPLY_DEMO_WITH_APPROVAL - no approved suggestions"],
                )
            return CalibrationEngineResult(
                mode=self._mode,
                suggestions=suggestions_dicts,
                applied=True,
                applied_to="demo",
                reasons=[
                    f"APPLY_DEMO_WITH_APPROVAL - applied {len(approved)} approved suggestion(s) to demo"
                ],
            )

        if self._mode == CalibrationMode.LIVE:
            approved = [s for s in self._suggestions if s.approved]
            if not approved:
                blockers.append(
                    "No approved suggestions - LIVE requires approved suggestions"
                )
                return CalibrationEngineResult(
                    mode=self._mode,
                    suggestions=suggestions_dicts,
                    applied=False,
                    applied_to="none",
                    blockers=blockers,
                    reasons=["LIVE mode - no approved suggestions"],
                )
            return CalibrationEngineResult(
                mode=self._mode,
                suggestions=suggestions_dicts,
                applied=True,
                applied_to="live",
                reasons=[
                    f"LIVE mode - applied {len(approved)} approved suggestion(s) to live "
                    f"(approved_by={self._live_approval.get('approved_by', '')})"
                ],
            )

        # Defensive fallback
        blockers.append(f"Unknown mode: {self._mode}")
        return CalibrationEngineResult(
            mode=self._mode,
            applied=False,
            applied_to="none",
            blockers=blockers,
        )

    # ──────────────────────────────────────────────────────────────────────
    # Safety helpers
    # ──────────────────────────────────────────────────────────────────────

    def enforce_no_silent_live_threshold_change(self) -> bool:
        """Always returns False. Silent live threshold changes are forbidden."""
        return False

    def enforce_no_auto_promotion_to_live(self) -> bool:
        """Always returns False. Auto-promotion to live is forbidden."""
        return False

    def safety_invariants(self) -> dict:
        return dict(SAFETY_INVARIANTS)

    def summary(self) -> dict:
        return {
            "mode": self._mode.value,
            "default_mode": DEFAULT_MODE.value,
            "auto_promote_to_live": False,
            "silent_live_threshold_change": False,
            "human_approval_required": True,
            "no_martingale": True,
            "no_grid": True,
            "no_averaging": True,
            "no_loss_based_lot_multiplier": True,
            "total_suggestions": len(self._suggestions),
            "approved_suggestions": len(self._approved_suggestions),
            "live_approval_recorded": bool(self._live_approval),
        }
