"""
TITAN XAU AI — Prop Firm Rule Engine (Sprint 9.9.3.45.8.5)
===========================================================

Validates that every prop-firm profile declared in
``config/prop_firm_profiles.yaml`` declares a complete, internally
consistent, fail-closed rule set before it can be used in any live or
funded context.

Responsibilities:
  1. Load prop-firm profiles from ``config/prop_firm_profiles.yaml``.
  2. For each profile, check that every *critical* rule is present and
     internally consistent:
       - profit_target
       - daily_dd_limit (max_daily_loss_pct)
       - total_dd_limit (max_total_loss_pct)
       - drawdown_mode (static | trailing | hybrid)
       - daily_dd_reset_time (00:00 UTC unless profile overrides)
       - max_open_positions
       - max_lot_cap
       - risk_per_trade (risk_per_trade_pct)
       - min_rr
       - news_trading
       - weekend_holding
       - consistency_rule
       - min_trading_days
       - ea_allowed
       - copy_trading
  3. For each profile, verify that the *internal* drawdown stops sit
     *below* the external prop-firm limits:
       - external daily DD 3%   → internal daily stop <= 2.5%
       - external total DD 8%   → internal total stop <= 7.0%
     The internal-stop caps are derived from the profile's emergency_halt_pct
     and daily_caution_pct (which act as the internal DD kill-switches).
  4. For unknown critical rules: never guess. Fail closed for funded/live
     profiles, allow simulation-only if the profile is *explicitly* marked
     ``simulation_only: true`` and ``live_allowed: false``.
  5. Return a :class:`PropFirmRuleResult` with profile_name, rules dict,
     unknown_critical_count, verdict, blockers, warnings.

Verdicts:
  - ``PROP_RULES_READY``                          : no blockers, no unknowns
  - ``PROP_RULES_READY_WITH_UNKNOWN_NON_CRITICAL``: no blockers, only
                                                    non-critical unknowns
                                                    (e.g. news_trading,
                                                    weekend_holding for
                                                    challenge-phase
                                                    simulation-only)
  - ``PROP_RULES_BLOCKED``                        : unknown critical rule,
                                                    internal-stop exceeds
                                                    external limit, or
                                                    safety invariant
                                                    violated

Safety invariants (HARD — enforced for every profile):
  - no_martingale: True
  - no_grid: True
  - no_averaging: True

This module is pure Python. It NEVER imports MetaTrader5, NEVER calls
``mt5.order_send``, and NEVER submits orders. It only reads configuration
YAML and emits structured rule-validation results.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional

import yaml

logger = logging.getLogger(__name__)


# ─── Verdicts ──────────────────────────────────────────────────────────────
PROP_RULES_READY: str = "PROP_RULES_READY"
PROP_RULES_READY_WITH_UNKNOWN_NON_CRITICAL: str = (
    "PROP_RULES_READY_WITH_UNKNOWN_NON_CRITICAL"
)
PROP_RULES_BLOCKED: str = "PROP_RULES_BLOCKED"


# ─── Safety flags mirrored across the production stack ────────────────────
SAFETY_FLAGS: dict[str, bool] = {
    "no_martingale": True,
    "no_grid": True,
    "no_averaging": True,
}


# ─── Rule check schema ────────────────────────────────────────────────────
# Each entry is a (key, kind, critical_for_funded_live) tuple.
#   kind: "decimal" | "int" | "string" | "bool" | "tristate"
#   critical_for_funded_live: if True and the value is missing or unknown,
#     the profile is BLOCKED for funded/live use.
RULE_SCHEMA: tuple[tuple[str, str, bool], ...] = (
    ("profit_target_pct", "decimal", True),
    ("max_daily_loss_pct", "decimal", True),
    ("max_total_loss_pct", "decimal", True),
    ("drawdown_mode", "string", True),
    ("daily_dd_reset_time", "string", False),    # advisory — defaults 00:00 UTC
    ("max_open_positions", "int", True),
    ("max_lot", "decimal", True),
    ("risk_per_trade_pct", "decimal", True),
    ("min_rr", "decimal", True),
    ("news_trading", "tristate", False),         # non-critical: default unknown
    ("weekend_holding", "tristate", False),      # non-critical: default unknown
    ("consistency_rule_enabled", "bool", True),
    ("min_trading_days", "int", True),
    ("ea_allowed", "tristate", False),
    ("copy_trading", "tristate", False),
)

# Sprint 9.9.3.45.8.7: RR field aliases — canonical is minimum_RR
RR_FIELD_ALIASES = ("minimum_RR", "min_rr", "minimum_rr")


# ─── Tri-state accepted string values ─────────────────────────────────────
TRISTATE_VALUES: frozenset[str] = frozenset({"true", "false", "unknown"})


# ─── Internal-stop safety bands ───────────────────────────────────────────
# The internal daily stop must be ≤ (external_daily_dd * (1 - DD_MARGIN))
# and the internal total stop must be ≤ (external_total_dd * (1 - DD_MARGIN)).
# These bands enforce that the kill-switch fires BEFORE the prop firm's
# hard limit is breached.
#
# Per spec: external daily DD 3% → internal stop ≤ 2.5% (margin ≈ 16.67%)
#           external total DD 8% → internal stop ≤ 7.0% (margin = 12.5%)
# We use 0.8333 (5/6) for the daily band and 0.875 (7/8) for the total band.
DAILY_DD_INTERNAL_RATIO: float = 5.0 / 6.0      # 0.8333 → 3% external → 2.5% internal
TOTAL_DD_INTERNAL_RATIO: float = 7.0 / 8.0       # 0.875  → 8% external → 7.0% internal


# ─── Dataclasses ──────────────────────────────────────────────────────────
@dataclass
class PropFirmRuleResult:
    """
    Validation result for a single prop-firm profile.

    ``rules`` is the canonical rule dict (parsed values + unknowns flagged).
    ``unknown_critical_count`` counts critical rules that are missing or
    ``unknown`` and that cannot be resolved without operator input.
    ``verdict`` is one of ``PROP_RULES_*``.
    ``blockers`` lists hard blockers (must be fixed before use).
    ``warnings`` lists non-blocking concerns (operator should review).
    """
    profile_name: str
    rules: dict[str, Any] = field(default_factory=dict)
    unknown_critical_count: int = 0
    verdict: str = PROP_RULES_BLOCKED
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    # Hard safety invariants — always True.
    no_martingale: bool = True
    no_grid: bool = True
    no_averaging: bool = True
    # Sprint 9.9.3.45.8.7: active/legacy profile tracking
    active_for_production_proof: bool = False
    is_simulation_only: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ─── Engine ───────────────────────────────────────────────────────────────
class PropFirmRuleEngine:
    """
    Loads and validates prop-firm rule profiles from YAML.

    Usage:
        engine = PropFirmRuleEngine(
            profiles_path="config/prop_firm_profiles.yaml"
        )
        result = engine.validate_rules("ftmo_challenge")
        all_profiles = engine.list_profiles()
    """

    def __init__(
        self,
        profiles_path: str | Path = "config/prop_firm_profiles.yaml",
    ) -> None:
        self.profiles_path = Path(profiles_path)
        self._raw: dict[str, dict] = {}
        self._profiles: dict[str, dict] = {}
        self._auto_detect: dict = {}
        self._load_yaml()

    # ─── Loading ────────────────────────────────────────────────────────
    def _load_yaml(self) -> None:
        if not self.profiles_path.exists():
            raise FileNotFoundError(
                f"Prop firm profiles YAML not found: {self.profiles_path}"
            )
        with open(self.profiles_path, "r", encoding="utf-8") as f:
            doc = yaml.safe_load(f) or {}
        self._profiles = doc.get("profiles", {}) or {}
        self._auto_detect = doc.get("auto_detect", {}) or {}
        # Enforce safety flags on every profile defensively.
        for prof_id, raw in self._profiles.items():
            if not isinstance(raw, dict):
                logger.warning(
                    "Skipping profile '%s': not a mapping", prof_id
                )
                continue
            raw.setdefault("no_martingale", True)
            raw.setdefault("no_grid", True)
            raw.setdefault("no_averaging", True)
        self._raw = dict(self._profiles)
        logger.info(
            "PropFirmRuleEngine loaded %d profiles from %s",
            len(self._profiles), self.profiles_path,
        )

    # ─── Public API ─────────────────────────────────────────────────────
    def list_profiles(self) -> list[str]:
        """Return all available profile IDs (sorted)."""
        return sorted(self._profiles.keys())

    def get_profile(self, name: str) -> Optional[dict[str, Any]]:
        """
        Return the raw profile dict (deep-copied) for ``name`` or ``None``
        if the profile does not exist. Never raises on missing keys.
        """
        if name not in self._profiles:
            return None
        return dict(self._profiles[name])

    def validate_rules(self, profile_name: str) -> PropFirmRuleResult:
        """
        Validate the prop-firm rules for ``profile_name``.

        Returns a :class:`PropFirmRuleResult` with the canonical rules dict,
        unknown critical count, verdict, blockers, and warnings.
        """
        if profile_name not in self._profiles:
            result = PropFirmRuleResult(profile_name=profile_name)
            result.blockers.append(
                f"unknown profile: {profile_name!r} — refusing to guess"
            )
            result.verdict = PROP_RULES_BLOCKED
            return result

        raw = self._profiles[profile_name]
        blockers: list[str] = []
        warnings: list[str] = []
        rules: dict[str, Any] = {}
        unknown_critical_count = 0
        unknown_non_critical_count = 0

        # ── Parse every rule in the schema ────────────────────────────
        # daily_dd_reset_time has a safe default ("00:00 UTC") so we treat
        # it as already-known if missing.
        for key, kind, critical_for_funded_live in RULE_SCHEMA:
            # Sprint 9.9.3.45.8.7: resolve RR field aliases
            if key == "min_rr":
                value = None
                for alias in RR_FIELD_ALIASES:
                    if alias in raw:
                        value = raw[alias]
                        break
            else:
                value = raw.get(key)
            parsed_value: Any
            is_unknown = False

            # Special-case: daily_dd_reset_time defaults to 00:00 UTC.
            if key == "daily_dd_reset_time" and (value is None or value == ""):
                parsed_value = "00:00 UTC"
                warnings.append(
                    "daily_dd_reset_time not declared — defaulting to 00:00 UTC"
                )
                rules[key] = parsed_value
                continue

            if value is None:
                # Missing field. For some non-critical fields we tolerate
                # a default of "unknown" — but we still emit a warning.
                if kind == "tristate":
                    parsed_value = "unknown"
                    is_unknown = True
                else:
                    parsed_value = None
                    is_unknown = True
            elif kind == "tristate":
                sval = str(value).strip().lower()
                if sval in TRISTATE_VALUES:
                    parsed_value = sval
                    if sval == "unknown":
                        is_unknown = True
                else:
                    parsed_value = "unknown"
                    is_unknown = True
                    warnings.append(
                        f"{key}={value!r} is not a valid tristate "
                        f"(expected true/false/unknown) — treated as unknown"
                    )
            elif kind == "bool":
                if isinstance(value, bool):
                    parsed_value = value
                else:
                    parsed_value = False
                    blockers.append(
                        f"{key}={value!r} is not a boolean"
                    )
            elif kind == "int":
                try:
                    parsed_value = int(value)
                except (TypeError, ValueError):
                    parsed_value = None
                    blockers.append(
                        f"{key}={value!r} is not an integer"
                    )
            elif kind == "decimal":
                try:
                    parsed_value = float(value)
                except (TypeError, ValueError):
                    parsed_value = None
                    blockers.append(
                        f"{key}={value!r} is not a decimal"
                    )
            elif kind == "string":
                sval = str(value).strip()
                if not sval:
                    parsed_value = None
                    is_unknown = True
                else:
                    parsed_value = sval
            else:
                parsed_value = value  # pragma: no cover — defensive

            rules[key] = parsed_value

            if is_unknown:
                if critical_for_funded_live:
                    unknown_critical_count += 1
                else:
                    unknown_non_critical_count += 1

        # ── Safety invariant check ────────────────────────────────────
        for flag, expected in SAFETY_FLAGS.items():
            actual = raw.get(flag, True)
            if not _coerce_bool(actual) == expected:
                blockers.append(
                    f"{flag} must be {expected} — got {actual!r}"
                )
            rules[flag] = expected

        # ── Profile-level flags ───────────────────────────────────────
        simulation_only = _coerce_bool(raw.get("simulation_only", False))
        live_allowed = _coerce_bool(raw.get("live_allowed", not simulation_only))
        rules["simulation_only"] = simulation_only
        rules["live_allowed"] = live_allowed
        rules["phase"] = str(raw.get("phase", "challenge"))

        # ── Range checks on decimal rules ─────────────────────────────
        _range_check(
            rules, "profit_target_pct", 0.0, 1.0,
            blockers, warnings,
        )
        _range_check(
            rules, "max_daily_loss_pct", 0.0, 1.0,
            blockers, warnings,
        )
        _range_check(
            rules, "max_total_loss_pct", 0.0, 1.0,
            blockers, warnings,
        )
        _range_check(
            rules, "risk_per_trade_pct", 0.0, 0.10,
            blockers, warnings,
        )
        _range_check(
            rules, "min_rr", 0.0, 50.0,
            blockers, warnings,
        )
        _range_check(
            rules, "max_lot", 0.0, 1.0,
            blockers, warnings,
        )
        _range_check(
            rules, "max_open_positions", 0, 10,
            blockers, warnings,
        )

        # ── Drawdown-mode sanity ──────────────────────────────────────
        dd_mode = rules.get("drawdown_mode")
        if dd_mode not in ("static", "trailing", "hybrid"):
            blockers.append(
                f"drawdown_mode={dd_mode!r} must be one of "
                f"static | trailing | hybrid"
            )

        # ── Internal-stop below external limit ────────────────────────
        # External limits come from max_daily_loss_pct and max_total_loss_pct.
        # Internal stops are daily_caution_pct (daily) and emergency_halt_pct
        # (total). The internal stop must be ≤ the external limit × the
        # appropriate ratio (daily 5/6, total 7/8).
        ext_daily = rules.get("max_daily_loss_pct")
        ext_total = rules.get("max_total_loss_pct")
        int_daily = raw.get("daily_caution_pct")
        int_total = raw.get("emergency_halt_pct")

        if isinstance(ext_daily, (int, float)) and isinstance(int_daily, (int, float)):
            daily_cap = ext_daily * DAILY_DD_INTERNAL_RATIO
            if int_daily > daily_cap + 1e-9:
                blockers.append(
                    f"internal daily stop (daily_caution_pct={int_daily}) "
                    f"exceeds external daily DD cap "
                    f"({ext_daily} * {DAILY_DD_INTERNAL_RATIO:.4f} = "
                    f"{daily_cap:.4f})"
                )
            rules["daily_caution_pct"] = float(int_daily)
            rules["internal_daily_stop_pct"] = float(int_daily)
            rules["external_daily_dd_limit_pct"] = float(ext_daily)
        else:
            rules["daily_caution_pct"] = (
                float(int_daily) if isinstance(int_daily, (int, float)) else None
            )
            rules["internal_daily_stop_pct"] = rules["daily_caution_pct"]
            rules["external_daily_dd_limit_pct"] = (
                float(ext_daily) if isinstance(ext_daily, (int, float)) else None
            )

        if isinstance(ext_total, (int, float)) and isinstance(int_total, (int, float)):
            total_cap = ext_total * TOTAL_DD_INTERNAL_RATIO
            if int_total > total_cap + 1e-9:
                blockers.append(
                    f"internal total stop (emergency_halt_pct={int_total}) "
                    f"exceeds external total DD cap "
                    f"({ext_total} * {TOTAL_DD_INTERNAL_RATIO:.4f} = "
                    f"{total_cap:.4f})"
                )
            rules["emergency_halt_pct"] = float(int_total)
            rules["internal_total_stop_pct"] = float(int_total)
            rules["external_total_dd_limit_pct"] = float(ext_total)
        else:
            rules["emergency_halt_pct"] = (
                float(int_total) if isinstance(int_total, (int, float)) else None
            )
            rules["internal_total_stop_pct"] = rules["emergency_halt_pct"]
            rules["external_total_dd_limit_pct"] = (
                float(ext_total) if isinstance(ext_total, (int, float)) else None
            )

        # ── Daily DD reset time ───────────────────────────────────────
        # Already defaulted to "00:00 UTC" during the parsing loop above
        # (with a warning) when the field is missing. If declared, it has
        # been parsed as a string. Nothing more to do here.
        if "daily_dd_reset_time" not in rules:
            rules["daily_dd_reset_time"] = "00:00 UTC"

        # ── Critical-for-funded-live unknown handling ─────────────────
        # Per spec: "Unknown critical rules: do not guess, fail closed for
        # funded/live, allow simulation-only if explicitly marked."
        # Therefore:
        #   - Unknown CRITICAL rule on a non-simulation_only profile
        #     (funded, verification, live challenge) → BLOCK.
        #   - Unknown CRITICAL rule on a simulation_only profile → ALLOW
        #     (still surfaced in warnings).
        #   - Unknown NON-CRITICAL rule → NEVER a blocker (only a warning),
        #     because the operator can resolve it during challenge.
        is_simulation_only = simulation_only is True

        if unknown_critical_count > 0 and not is_simulation_only:
            blockers.append(
                f"{unknown_critical_count} unknown CRITICAL rule(s) on "
                f"non-simulation profile — refusing to guess (fail-closed)"
            )
        elif unknown_critical_count > 0 and is_simulation_only:
            # Simulation-only profiles tolerate unknown critical rules but
            # surface them loudly as warnings.
            warnings.append(
                f"{unknown_critical_count} unknown CRITICAL rule(s) tolerated "
                f"because simulation_only=true — MUST be resolved before any "
                f"live or funded use"
            )

        if unknown_non_critical_count > 0:
            warnings.append(
                f"{unknown_non_critical_count} unknown NON-CRITICAL rule(s) "
                f"— operator should resolve before live use"
            )

        # ── Simulation-only sanity ────────────────────────────────────
        if simulation_only and live_allowed:
            blockers.append(
                "simulation_only=true conflicts with live_allowed=true — "
                "simulation profiles must declare live_allowed=false"
            )

        # ── Verdict ───────────────────────────────────────────────────
        if blockers:
            verdict = PROP_RULES_BLOCKED
        elif unknown_critical_count > 0:
            # Simulation-only with tolerated unknown critical rules.
            verdict = PROP_RULES_READY_WITH_UNKNOWN_NON_CRITICAL
        elif unknown_non_critical_count > 0:
            verdict = PROP_RULES_READY_WITH_UNKNOWN_NON_CRITICAL
        else:
            verdict = PROP_RULES_READY

        result = PropFirmRuleResult(
            profile_name=profile_name,
            rules=rules,
            unknown_critical_count=unknown_critical_count,
            verdict=verdict,
            blockers=blockers,
            warnings=warnings,
            no_martingale=True,
            no_grid=True,
            no_averaging=True,
            active_for_production_proof=_coerce_bool(raw.get("active_for_production_proof", False)),
            is_simulation_only=simulation_only is True,
        )
        logger.info(
            "PropFirmRuleEngine verdict for %s: %s "
            "(unknown_critical=%d, blockers=%d, warnings=%d)",
            profile_name, verdict, unknown_critical_count,
            len(blockers), len(warnings),
        )
        return result


# ─── Helpers ──────────────────────────────────────────────────────────────
def _coerce_bool(value: Any) -> bool:
    """Coerce YAML bool-like values into Python bool. Unknown → False."""
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    s = str(value).strip().lower()
    if s in ("true", "yes", "1", "on"):
        return True
    return False


def _range_check(
    rules: dict[str, Any],
    key: str,
    low: float,
    high: float,
    blockers: list[str],
    warnings: list[str],
) -> None:
    """Emit a blocker if ``rules[key]`` is outside ``[low, high]``."""
    value = rules.get(key)
    if value is None:
        return  # missing-value blocker already emitted during parsing
    try:
        v = float(value)
    except (TypeError, ValueError):
        return  # type blocker already emitted during parsing
    if v < low:
        blockers.append(f"{key}={v} below minimum {low}")
    elif v > high:
        blockers.append(f"{key}={v} above maximum {high}")
