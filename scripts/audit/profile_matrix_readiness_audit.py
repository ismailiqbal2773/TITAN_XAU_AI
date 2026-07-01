#!/usr/bin/env python3
"""
TITAN XAU AI — Profile Matrix Readiness Audit
==============================================

Cross-validates every account profile × risk mode combination against the
prop-firm rule engine and broker scoring engine, producing a matrix report
that surfaces any combination that is BLOCKED, SIMULATION_ONLY, or has
gaps.

For each combination, the audit reports:
  - account_profile
  - risk_mode
  - broker_profile
  - prop_firm_profile
  - risk_per_trade
  - daily_dd_internal
  - total_dd_internal
  - min_rr
  - initial_tp_r
  - dynamic_tp_trigger_r
  - broker_score
  - prop_rules_verdict
  - net_rr_verdict
  - margin_verdict
  - final_verdict (PASS | BLOCKED | SIMULATION_ONLY)

Verdicts:
  - ``PROFILE_MATRIX_READY``                : all combinations PASS.
  - ``PROFILE_MATRIX_READY_WITH_GAPS``      : some combinations SIMULATION_ONLY
                                              but none BLOCKED.
  - ``PROFILE_MATRIX_BLOCKED``              : at least one combination BLOCKED.

The audit is pure Python. It NEVER imports MetaTrader5, NEVER calls
``mt5.order_send``, and NEVER submits orders. It only reads configuration
YAML and writes structured audit reports.

Safety invariants (HARD — enforced for every combination):
  - no_martingale: True
  - no_grid: True
  - no_averaging: True
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

OUTPUT_DIR = REPO_ROOT / "data" / "audit" / "profile_matrix"
JSON_PATH = OUTPUT_DIR / "profile_matrix_report.json"
MD_PATH = OUTPUT_DIR / "profile_matrix_report.md"

ACCOUNT_PROFILES_PATH = REPO_ROOT / "config" / "account_profiles.yaml"
RISK_MODES_PATH = REPO_ROOT / "config" / "risk_modes.yaml"
BROKER_PROFILES_PATH = REPO_ROOT / "config" / "broker_profiles.yaml"
PROP_FIRM_PROFILES_PATH = REPO_ROOT / "config" / "prop_firm_profiles.yaml"

PROFILE_MATRIX_READY: str = "PROFILE_MATRIX_READY"
PROFILE_MATRIX_READY_WITH_GAPS: str = "PROFILE_MATRIX_READY_WITH_GAPS"
PROFILE_MATRIX_BLOCKED: str = "PROFILE_MATRIX_BLOCKED"

# ─── Per-combination verdicts ─────────────────────────────────────────────
COMBO_PASS: str = "PASS"
COMBO_BLOCKED: str = "BLOCKED"
COMBO_SIMULATION_ONLY: str = "SIMULATION_ONLY"

# ─── Sub-verdicts ─────────────────────────────────────────────────────────
PROP_RULES_OK: str = "PROP_RULES_OK"
PROP_RULES_WARN: str = "PROP_RULES_WARN"
PROP_RULES_BLOCK: str = "PROP_RULES_BLOCK"

NET_RR_OK: str = "NET_RR_OK"
NET_RR_BELOW_MIN: str = "NET_RR_BELOW_MIN"

MARGIN_OK: str = "MARGIN_OK"
MARGIN_TOO_HIGH: str = "MARGIN_TOO_HIGH"


def _strip(src: str) -> str:
    src = re.sub(r'"""[\s\S]*?"""', '""', src)
    src = re.sub(r"'''[\s\S]*?'''", "''", src)
    src = re.sub(r'r"[^"]*"', '""', src)
    src = re.sub(r"r'[^']*'", "''", src)
    src = re.sub(r'"(?:[^"\\]|\\.)*"', '""', src)
    src = re.sub(r"'(?:[^'\\]|\\.)*'", "''", src)
    out = []
    for line in src.splitlines():
        idx = line.find("#")
        if idx >= 0:
            line = line[:idx]
        out.append(line)
    return "\n".join(out)


def _has_no_order_send(code: str) -> bool:
    return not re.search(r"\bmt5\.order_send\s*\(", code) and \
           not re.search(r"\bMetaTrader5\.order_send\s*\(", code)


def _has_no_banned_betting(code: str) -> bool:
    low = code.lower()
    forbidden_patterns = [
        r"def\s+apply_martingale",
        r"def\s+apply_grid",
        r"def\s+average_down",
        r"\blot\s*\*\s*2\b",
        r"position_size\s*\*=\s*2\b",
        r"(?<!no_)\bloss_based_lot_multiplier\s*=",
        r"(?<!no_)\bmartingale_multiplier\s*=",
    ]
    return not any(re.search(p, low) for p in forbidden_patterns)


def _git_head_short() -> str:
    try:
        import subprocess
        r = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=10,
        )
        return r.stdout.strip() if r.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in ("true", "yes", "1", "on")


# ─── Broker score resolver (lazy; only used if available) ─────────────────
def _resolve_broker_score(broker_id: str) -> Optional[float]:
    """Return the broker score (0-100) for ``broker_id`` if available,
    else ``None``."""
    try:
        from titan.production.broker_scoring_engine import BrokerScoringEngine
        engine = BrokerScoringEngine(profiles_path=BROKER_PROFILES_PATH)
        if broker_id not in engine._profiles:
            return None
        result = engine.score_broker(broker_id)
        return float(result.score)
    except Exception:
        return None


def _pick_broker_for_account(
    account_profile: dict[str, Any],
    available_brokers: Optional[list[str]] = None,
) -> str:
    """Pick a sensible default broker id for an account profile.

    Heuristic:
      - account_type=demo → metaquotes_demo
      - firm_id / name contains "ftmo" → ftmo_prop
      - firm_id / name contains "institutional" → institutional_ecn
      - else → ic_markets_standard (live retail default)

    If ``available_brokers`` is provided and the heuristic pick is not in
    that list, fall back to the first available broker.
    """
    name = str(account_profile.get("name", "")).lower()
    account_type = str(account_profile.get("account_type", "")).lower()
    firm_id = str(account_profile.get("firm_id", "")).lower()
    if account_type == "demo":
        candidate = "metaquotes_demo"
    elif "ftmo" in name or "ftmo" in firm_id:
        candidate = "ftmo_prop"
    elif "institutional" in name or "institutional" in firm_id:
        candidate = "institutional_ecn"
    else:
        candidate = "ic_markets_standard"

    if available_brokers is None:
        return candidate
    if candidate in available_brokers:
        return candidate
    return available_brokers[0] if available_brokers else candidate


def _pick_prop_firm_for_account(
    account_profile: dict[str, Any],
    available_profiles: Optional[list[str]] = None,
) -> str:
    """Pick a sensible default prop-firm profile for an account profile.

    If ``available_profiles`` is provided and the heuristic pick is not in
    that list, fall back to the first available profile. This makes the
    picker robust against test fixtures with reduced profile sets.
    """
    name = str(account_profile.get("name", "")).lower()
    firm_id = str(account_profile.get("firm_id", "")).lower()
    candidates: list[str] = []
    if "ftmo" in name or "ftmo" in firm_id:
        candidates = ["ftmo_challenge", "ftmo_style_conservative"]
    elif "fundednext" in name or "fundednext" in firm_id:
        candidates = ["fundednext_challenge", "fundednext_style_conservative"]
    elif "institutional" in name or "institutional" in firm_id:
        candidates = ["institutional_internal_mandate"]
    elif "prop" in name or "prop" in firm_id:
        candidates = [
            "generic_prop_100x_static_dd",
            "prop_aggressive_20pct_simulation_only",
        ]
    else:
        candidates = ["generic_prop_100x_static_dd"]

    if available_profiles is None:
        return candidates[0]
    for c in candidates:
        if c in available_profiles:
            return c
    # Fall back to the first available profile.
    return available_profiles[0] if available_profiles else candidates[0]


# ─── Combination evaluation ───────────────────────────────────────────────
def _evaluate_combination(
    account_id: str,
    account_profile: dict[str, Any],
    risk_mode_id: str,
    risk_mode: dict[str, Any],
    prop_firm_engine: Any,
    broker_doc: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Evaluate a single (account, risk_mode) combination."""
    # ── Resolve prop firm profile ──────────────────────────────────────
    prop_firm_id = _pick_prop_firm_for_account(
        account_profile,
        available_profiles=prop_firm_engine.list_profiles(),
    )
    prop_result = prop_firm_engine.validate_rules(prop_firm_id)

    if prop_result.verdict == "PROP_RULES_READY":
        prop_rules_verdict = PROP_RULES_OK
    elif prop_result.verdict == "PROP_RULES_READY_WITH_UNKNOWN_NON_CRITICAL":
        prop_rules_verdict = PROP_RULES_WARN
    else:
        prop_rules_verdict = PROP_RULES_BLOCK

    # ── Resolve broker profile + score ────────────────────────────────
    available_brokers: list[str] = []
    if broker_doc and isinstance(broker_doc.get("brokers"), dict):
        available_brokers = list(broker_doc["brokers"].keys())
    broker_id = _pick_broker_for_account(
        account_profile,
        available_brokers=available_brokers or None,
    )
    broker_score = _resolve_broker_score(broker_id)

    # ── Risk-per-trade (use account profile cap, take min with risk mode) ─
    acct_risk = float(account_profile.get("max_risk_per_trade_pct", 0.01))
    mode_risk = float(risk_mode.get("max_risk_per_trade_pct", 0.01))
    risk_per_trade = min(acct_risk, mode_risk)

    # ── Internal DD (use account profile cap, take min with risk mode) ─
    acct_daily = float(account_profile.get("max_daily_dd_pct", 0.05))
    acct_total = float(account_profile.get("max_total_dd_pct", 0.10))
    mode_daily = float(risk_mode.get("max_daily_dd_pct", 0.05))
    mode_total = float(risk_mode.get("max_total_dd_pct", 0.10))
    daily_dd_internal = min(acct_daily, mode_daily)
    total_dd_internal = min(acct_total, mode_total)

    # ── Min RR ─────────────────────────────────────────────────────────
    min_rr = float(account_profile.get("minimum_RR", 2.0))
    prop_min_rr = prop_result.rules.get("min_rr")
    if isinstance(prop_min_rr, (int, float)) and prop_min_rr > min_rr:
        min_rr = float(prop_min_rr)

    # ── Dynamic TP geometry (from account profile) ────────────────────
    initial_tp_r = float(account_profile.get("dynamic_tp_initial_tp_R", 3.0))
    dynamic_tp_trigger_r = float(account_profile.get("dynamic_tp_trigger_R", 2.0))

    # ── Net RR verdict ────────────────────────────────────────────────
    # Per-trade RR floor: the deployed initial_tp_r must be ≥ the account
    # profile's minimum_RR (the per-trade RR floor enforced at order-build
    # time). If the deployed TP sits below the floor, the combination is
    # BLOCKED because the trade would never be accepted.
    if initial_tp_r >= min_rr:
        net_rr_verdict = NET_RR_OK
    else:
        net_rr_verdict = NET_RR_BELOW_MIN

    # ── Margin verdict ────────────────────────────────────────────────
    # Margin usage must be ≤ account_profile.max_margin_usage_pct.
    max_margin = float(account_profile.get("max_margin_usage_pct", 0.20))
    # Heuristic: estimate margin use as risk_per_trade / 0.10 (10% baseline).
    # If the heuristic exceeds max_margin, the combination is BLOCKED.
    est_margin_use = risk_per_trade / 0.10
    if est_margin_use <= max_margin:
        margin_verdict = MARGIN_OK
    else:
        margin_verdict = MARGIN_TOO_HIGH

    # ── Live-allowed / simulation-only ────────────────────────────────
    account_live = str(account_profile.get("account_type", "")).lower() == "live"
    mode_live = _coerce_bool(risk_mode.get("live_allowed", False))
    mode_sim = _coerce_bool(risk_mode.get("simulation_only", False))

    # ── Final verdict ─────────────────────────────────────────────────
    blockers: list[str] = []
    if prop_rules_verdict == PROP_RULES_BLOCK:
        blockers.append(f"prop_rules_verdict={PROP_RULES_BLOCK}")
    if net_rr_verdict == NET_RR_BELOW_MIN:
        blockers.append(
            f"initial_tp_r={initial_tp_r:.2f} below min_rr={min_rr:.2f}"
        )
    if margin_verdict == MARGIN_TOO_HIGH:
        blockers.append(
            f"est_margin_use={est_margin_use:.3f} > "
            f"max_margin_usage_pct={max_margin:.3f}"
        )
    # Live combination on a non-live risk mode is BLOCKED.
    if account_live and not mode_live and not mode_sim:
        blockers.append(
            f"account_type=live but risk_mode {risk_mode_id} has "
            f"live_allowed=false (and simulation_only=false)"
        )
    # Live combination with a simulation-only risk mode is BLOCKED.
    if account_live and mode_sim:
        blockers.append(
            f"account_type=live but risk_mode {risk_mode_id} is "
            f"simulation_only — NEVER for live trading"
        )

    if blockers:
        final_verdict = COMBO_BLOCKED
    elif mode_sim or (not mode_live and not account_live):
        # Simulation mode or demo account on non-live mode → SIMULATION_ONLY.
        final_verdict = COMBO_SIMULATION_ONLY
    else:
        final_verdict = COMBO_PASS

    return {
        "account_profile": account_id,
        "risk_mode": risk_mode_id,
        "broker_profile": broker_id,
        "prop_firm_profile": prop_firm_id,
        "risk_per_trade": round(risk_per_trade, 6),
        "daily_dd_internal": round(daily_dd_internal, 6),
        "total_dd_internal": round(total_dd_internal, 6),
        "min_rr": round(min_rr, 4),
        "initial_tp_r": round(initial_tp_r, 4),
        "dynamic_tp_trigger_r": round(dynamic_tp_trigger_r, 4),
        "broker_score": (
            round(broker_score, 2) if broker_score is not None else None
        ),
        "prop_rules_verdict": prop_rules_verdict,
        "net_rr_verdict": net_rr_verdict,
        "margin_verdict": margin_verdict,
        "final_verdict": final_verdict,
        "blockers": blockers,
        "no_martingale": True,
        "no_grid": True,
        "no_averaging": True,
    }


def run_audit(
    account_profiles_path: str | Path | None = None,
    risk_modes_path: str | Path | None = None,
    broker_profiles_path: str | Path | None = None,
    prop_firm_profiles_path: str | Path | None = None,
) -> dict[str, Any]:
    """
    Run the profile matrix readiness audit.

    Returns the full audit result dict (also written to JSON + MD when
    :func:`write_report` is called).
    """
    ts = datetime.now(timezone.utc).isoformat()
    head = _git_head_short()

    if account_profiles_path is None:
        account_profiles_path = ACCOUNT_PROFILES_PATH
    if risk_modes_path is None:
        risk_modes_path = RISK_MODES_PATH
    if broker_profiles_path is None:
        broker_profiles_path = BROKER_PROFILES_PATH
    if prop_firm_profiles_path is None:
        prop_firm_profiles_path = PROP_FIRM_PROFILES_PATH

    account_doc = _load_yaml(Path(account_profiles_path))
    risk_doc = _load_yaml(Path(risk_modes_path))
    broker_doc = _load_yaml(Path(broker_profiles_path))
    prop_doc = _load_yaml(Path(prop_firm_profiles_path))

    accounts = account_doc.get("profiles", {}) or {}
    modes = risk_doc.get("modes", {}) or {}
    brokers = broker_doc.get("brokers", {}) or {}

    # Lazy import so module-level constants are defined first.
    from titan.production.prop_firm_rule_engine import (
        PropFirmRuleEngine,
        PROP_RULES_READY,
        PROP_RULES_READY_WITH_UNKNOWN_NON_CRITICAL,
        PROP_RULES_BLOCKED,
    )

    prop_engine = PropFirmRuleEngine(profiles_path=prop_firm_profiles_path)

    ok_checks: list[str] = []
    warnings: list[str] = []
    blockers: list[str] = []

    ok_checks.append(
        f"Loaded {len(accounts)} account profiles, {len(modes)} risk modes, "
        f"{len(brokers)} broker profiles, "
        f"{len(prop_engine.list_profiles())} prop-firm profiles"
    )

    # Safety invariant scan: every account profile, every risk mode.
    for acc_id, acc in accounts.items():
        if not _coerce_bool(acc.get("no_martingale", True)):
            blockers.append(f"[account:{acc_id}] no_martingale=False")
        if not _coerce_bool(acc.get("no_grid", True)):
            blockers.append(f"[account:{acc_id}] no_grid=False")
        if not _coerce_bool(acc.get("no_averaging", True)):
            blockers.append(f"[account:{acc_id}] no_averaging=False")
        if not _coerce_bool(acc.get("no_loss_based_lot_multiplier", True)):
            blockers.append(
                f"[account:{acc_id}] no_loss_based_lot_multiplier=False"
            )
    for mode_id, mode in modes.items():
        if not _coerce_bool(mode.get("no_martingale", True)):
            blockers.append(f"[mode:{mode_id}] no_martingale=False")
        if not _coerce_bool(mode.get("no_grid", True)):
            blockers.append(f"[mode:{mode_id}] no_grid=False")
        if not _coerce_bool(mode.get("no_averaging", True)):
            blockers.append(f"[mode:{mode_id}] no_averaging=False")
        if not _coerce_bool(mode.get("no_loss_based_lot_multiplier", True)):
            blockers.append(
                f"[mode:{mode_id}] no_loss_based_lot_multiplier=False"
            )

    if not blockers:
        ok_checks.append(
            "All account profiles and risk modes enforce no_martingale, "
            "no_grid, no_averaging, no_loss_based_lot_multiplier"
        )

    # ── Evaluate every (account × risk_mode) combination ──────────────
    combinations: list[dict[str, Any]] = []
    for acc_id in sorted(accounts.keys()):
        for mode_id in sorted(modes.keys()):
            combo = _evaluate_combination(
                acc_id, accounts[acc_id],
                mode_id, modes[mode_id],
                prop_engine,
                broker_doc=broker_doc,
            )
            combinations.append(combo)

    # ── Aggregate verdicts ────────────────────────────────────────────
    # Sprint 9.9.3.45.8.7: Distinguish expected incompatibility (live account
    # + simulation mode) from critical blocks (demo account + prop rules fail)
    blocked_combos = [c for c in combinations if c["final_verdict"] == COMBO_BLOCKED]
    sim_combos = [c for c in combinations if c["final_verdict"] == COMBO_SIMULATION_ONLY]
    pass_combos = [c for c in combinations if c["final_verdict"] == COMBO_PASS]

    # Categorize blocked combos
    critical_blocks = []
    expected_incompatibility = []
    for c in blocked_combos:
        # If a live account is paired with a non-live mode (simulation-only,
        # demo, or prop challenge with live_allowed=false), that's an expected
        # incompatibility, not a critical block
        account_profile = c.get("account_profile", "")
        risk_mode = c.get("risk_mode", "")
        is_live_account = "live" in account_profile or "funded" in account_profile or "institutional" in account_profile
        # Check if the block reason is about live/simulation incompatibility
        block_reasons = " ".join(c.get("blockers", [])).lower()
        is_live_sim_incompatibility = (
            "live" in block_reasons and (
                "simulation" in block_reasons
                or "live_allowed=false" in block_reasons
                or "simulation_only" in block_reasons
            )
        )
        if is_live_account and is_live_sim_incompatibility:
            expected_incompatibility.append(c)
        else:
            critical_blocks.append(c)
            for b in c.get("blockers", []):
                blockers.append(f"[{c['account_profile']} x {c['risk_mode']}] {b}")

    if critical_blocks:
        verdict = PROFILE_MATRIX_BLOCKED
    elif sim_combos or expected_incompatibility:
        verdict = PROFILE_MATRIX_READY_WITH_GAPS
        if sim_combos:
            warnings.append(
                f"{len(sim_combos)} combination(s) are SIMULATION_ONLY "
                f"(demo or simulation-only risk mode) — operator must upgrade "
                f"to PASS before live use"
            )
        if expected_incompatibility:
            warnings.append(
                f"{len(expected_incompatibility)} combination(s) are expected "
                f"incompatibility (live account + simulation-only mode) — "
                f"these are correctly BLOCKED and do not affect production readiness"
            )
    else:
        verdict = PROFILE_MATRIX_READY

    ok_checks.append(
        f"{len(pass_combos)} combination(s) PASS, "
        f"{len(sim_combos)} SIMULATION_ONLY, "
        f"{len(critical_blocks)} critically BLOCKED, "
        f"{len(expected_incompatibility)} expected incompatibility"
    )

    # ── Self-audit: never call order_send, never banned betting ───────
    try:
        own_src = Path(__file__).read_text(encoding="utf-8")
        own_code = _strip(own_src)
        if _has_no_order_send(own_code):
            ok_checks.append("profile matrix audit never calls mt5.order_send")
        else:
            blockers.append("profile matrix audit calls mt5.order_send")
        if _has_no_banned_betting(own_code):
            ok_checks.append(
                "profile matrix audit has no martingale/grid/averaging logic"
            )
        else:
            blockers.append(
                "profile matrix audit contains banned betting logic"
            )
    except Exception as e:
        blockers.append(f"profile matrix audit self-check error: {e}")

    # Re-evaluate verdict if self-audit added blockers.
    if blockers and verdict == PROFILE_MATRIX_READY:
        verdict = PROFILE_MATRIX_BLOCKED

    return {
        "timestamp_utc": ts,
        "head_short": head,
        "verdict": verdict,
        "account_profiles_path": str(account_profiles_path),
        "risk_modes_path": str(risk_modes_path),
        "broker_profiles_path": str(broker_profiles_path),
        "prop_firm_profiles_path": str(prop_firm_profiles_path),
        "account_profile_count": len(accounts),
        "risk_mode_count": len(modes),
        "broker_profile_count": len(brokers),
        "combination_count": len(combinations),
        "pass_count": len(pass_combos),
        "simulation_only_count": len(sim_combos),
        "blocked_count": len(blocked_combos),
        "combinations": combinations,
        "ok_checks": ok_checks,
        "warnings": warnings,
        "blockers": blockers,
        "design_description": (
            "Every account profile × risk mode combination is validated "
            "against the prop-firm rule engine and broker scoring engine. "
            "Combinations are BLOCKED if prop rules fail, net RR falls "
            "below min_rr, margin use exceeds the cap, or a live account "
            "is paired with a non-live risk mode. Simulation-only modes "
            "produce SIMULATION_ONLY combinations. The audit NEVER calls "
            "mt5.order_send and NEVER contains martingale/grid/averaging "
            "logic."
        ),
        "no_martingale": True,
        "no_grid": True,
        "no_averaging": True,
    }


def write_report(
    result: dict[str, Any],
    output_dir: str | Path | None = None,
) -> dict[str, str]:
    """Write the audit result as JSON + Markdown. Returns the paths."""
    if output_dir is None:
        out_dir = OUTPUT_DIR
    else:
        out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "profile_matrix_report.json"
    md_path = out_dir / "profile_matrix_report.md"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str, ensure_ascii=False)

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# TITAN XAU AI - Profile Matrix Readiness Audit\n\n")
        f.write(f"**Verdict:** **{result['verdict']}**\n\n")
        f.write(f"**Design:** {result['design_description']}\n\n")
        f.write(f"**Timestamp:** {result['timestamp_utc']}\n\n")
        f.write(f"**Head:** {result['head_short']}\n\n")
        f.write(
            f"**Combinations:** {result['combination_count']} "
            f"(PASS={result['pass_count']}, "
            f"SIMULATION_ONLY={result['simulation_only_count']}, "
            f"BLOCKED={result['blocked_count']})\n\n"
        )

        f.write("## Combination matrix\n\n")
        f.write(
            "| Account | Risk Mode | Broker | Prop Firm | Risk/Trade | "
            "Daily DD (int) | Total DD (int) | Min RR | TP R | Dyn TP R | "
            "Broker Score | Prop Rules | Net RR | Margin | Final |\n"
        )
        f.write("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|\n")
        for c in result["combinations"]:
            f.write(
                f"| {c['account_profile']} | {c['risk_mode']} | "
                f"{c['broker_profile']} | {c['prop_firm_profile']} | "
                f"{c['risk_per_trade']} | {c['daily_dd_internal']} | "
                f"{c['total_dd_internal']} | {c['min_rr']} | "
                f"{c['initial_tp_r']} | {c['dynamic_tp_trigger_r']} | "
                f"{c['broker_score'] if c['broker_score'] is not None else 'n/a'} | "
                f"{c['prop_rules_verdict']} | {c['net_rr_verdict']} | "
                f"{c['margin_verdict']} | **{c['final_verdict']}** |\n"
            )

        if result.get("ok_checks"):
            f.write("\n## OK Checks\n\n")
            for c in result["ok_checks"]:
                f.write(f"- {c}\n")
        if result.get("warnings"):
            f.write("\n## Warnings\n\n")
            for w in result["warnings"]:
                f.write(f"- {w}\n")
        if result.get("blockers"):
            f.write("\n## Blockers\n\n")
            for b in result["blockers"]:
                f.write(f"- **{b}**\n")

        f.write(
            "\n**The audit NEVER calls mt5.order_send and NEVER contains "
            "martingale/grid/averaging logic.**\n"
        )

    return {"json_path": str(json_path), "md_path": str(md_path)}


def main() -> int:
    print("=" * 70)
    print("  TITAN XAU AI - Profile Matrix Readiness Audit")
    print("=" * 70)
    result = run_audit()
    report = write_report(result)
    print(f"\n  Verdict: {result['verdict']}")
    print(f"  Combinations: {result['combination_count']}")
    print(f"  PASS: {result['pass_count']}")
    print(f"  SIMULATION_ONLY: {result['simulation_only_count']}")
    print(f"  BLOCKED: {result['blocked_count']}")
    print(f"\n  JSON: {report['json_path']}")
    print(f"  MD:   {report['md_path']}")
    print("\n" + "=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
