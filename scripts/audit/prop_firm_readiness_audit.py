#!/usr/bin/env python3
"""
TITAN XAU AI — Prop Firm Readiness Audit
=========================================

Runs the :class:`PropFirmRuleEngine` against every prop-firm profile declared
in ``config/prop_firm_profiles.yaml`` and emits an overall readiness verdict
plus a JSON + Markdown report.

The audit is pure Python. It NEVER imports MetaTrader5, NEVER calls
``mt5.order_send``, and NEVER submits orders. It only reads configuration
YAML and writes structured audit reports.

Verdicts:
  - ``PROP_FIRM_READY``       : every profile passes (READY or
                                READY_WITH_UNKNOWN_NON_CRITICAL).
  - ``PROP_FIRM_NEEDS_WORK``  : at least one profile is READY_WITH_UNKNOWN
                                _NON_CRITICAL and no profile is BLOCKED.
  - ``PROP_FIRM_BLOCKED``     : at least one profile is BLOCKED.

Reports are written to:
  - ``data/audit/prop_firm/prop_firm_readiness_audit.json``
  - ``data/audit/prop_firm/prop_firm_readiness_audit.md``

Safety invariants (HARD — enforced by the audit and by every profile):
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
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

OUTPUT_DIR = REPO_ROOT / "data" / "audit" / "prop_firm"
JSON_PATH = OUTPUT_DIR / "prop_firm_readiness_audit.json"
MD_PATH = OUTPUT_DIR / "prop_firm_readiness_audit.md"

PROFILES_PATH = REPO_ROOT / "config" / "prop_firm_profiles.yaml"

PROP_FIRM_READY: str = "PROP_FIRM_READY"
PROP_FIRM_NEEDS_WORK: str = "PROP_FIRM_NEEDS_WORK"
PROP_FIRM_BLOCKED: str = "PROP_FIRM_BLOCKED"
# Sprint 9.9.3.45.8.7: new verdict for active profiles pass but legacy need review
PROP_FIRM_READY_WITH_LEGACY_REVIEW: str = "PROP_FIRM_READY_WITH_LEGACY_REVIEW"


def _strip(src: str) -> str:
    """Strip string literals and comments from Python source for regex
    inspection of the audit's own code."""
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
    """Detect actual banned *logic*, not the safety-field declarations."""
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


def run_audit(
    profiles_path: str | Path | None = None,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    """
    Run the prop firm readiness audit.

    Args:
        profiles_path: override path to ``prop_firm_profiles.yaml``. If
            ``None``, defaults to ``config/prop_firm_profiles.yaml`` under
            the repo root.
        output_dir: override output directory. If ``None``, defaults to
            ``data/audit/prop_firm`` under the repo root.

    Returns:
        A dict with the full audit result (also written to JSON + MD).
    """
    ts = datetime.now(timezone.utc).isoformat()
    head = _git_head_short()

    if profiles_path is None:
        profiles_path = PROFILES_PATH
    profiles_path = Path(profiles_path)

    # Lazy import so module-level constants are defined first.
    from titan.production.prop_firm_rule_engine import (
        PropFirmRuleEngine,
        PROP_RULES_READY,
        PROP_RULES_READY_WITH_UNKNOWN_NON_CRITICAL,
        PROP_RULES_BLOCKED,
    )

    engine = PropFirmRuleEngine(profiles_path=profiles_path)

    profile_results: list[dict[str, Any]] = []
    ok_checks: list[str] = []
    warnings: list[str] = []
    blockers: list[str] = []

    ok_checks.append(
        f"PropFirmRuleEngine loaded {len(engine.list_profiles())} profiles "
        f"from {profiles_path}"
    )

    any_blocked = False
    any_needs_work = False
    any_legacy_review = False
    active_count = 0
    inactive_count = 0
    active_blocked_count = 0
    inactive_review_count = 0

    for prof_id in engine.list_profiles():
        result = engine.validate_rules(prof_id)
        d = result.to_dict()
        profile_results.append(d)

        is_active = d.get("active_for_production_proof", False)
        if is_active:
            active_count += 1
        else:
            inactive_count += 1

        if result.verdict == PROP_RULES_BLOCKED:
            if is_active:
                any_blocked = True
                active_blocked_count += 1
                for b in result.blockers:
                    blockers.append(f"[{prof_id}] {b}")
            else:
                # Inactive/legacy profile blocked - don't block production, just review
                any_legacy_review = True
                inactive_review_count += 1
                for b in result.blockers:
                    warnings.append(f"[{prof_id}] LEGACY_REVIEW: {b}")
        elif result.verdict == PROP_RULES_READY_WITH_UNKNOWN_NON_CRITICAL:
            if is_active:
                any_needs_work = True
                for w in result.warnings:
                    warnings.append(f"[{prof_id}] {w}")
            else:
                any_legacy_review = True
                for w in result.warnings:
                    warnings.append(f"[{prof_id}] LEGACY: {w}")
        elif result.verdict == PROP_RULES_READY:
            ok_checks.append(f"[{prof_id}] {'ACTIVE' if is_active else 'LEGACY'} PROP_RULES_READY")
        # Safety invariant assertions.
        if not result.no_martingale:
            blockers.append(f"[{prof_id}] no_martingale=False (safety violation)")
            any_blocked = True
        if not result.no_grid:
            blockers.append(f"[{prof_id}] no_grid=False (safety violation)")
            any_blocked = True
        if not result.no_averaging:
            blockers.append(f"[{prof_id}] no_averaging=False (safety violation)")
            any_blocked = True

    # ── Verdict ──────────────────────────────────────────────────────
    # Sprint 9.9.3.45.8.7: Only active profiles can block production proof
    if any_blocked:
        verdict = PROP_FIRM_BLOCKED
    elif any_legacy_review and not any_needs_work:
        verdict = PROP_FIRM_READY_WITH_LEGACY_REVIEW
    elif any_needs_work:
        verdict = PROP_FIRM_NEEDS_WORK
    else:
        verdict = PROP_FIRM_READY

    # ── Self-audit: this script must not call order_send or have
    #    banned betting logic.
    try:
        own_src = Path(__file__).read_text(encoding="utf-8")
        own_code = _strip(own_src)
        if _has_no_order_send(own_code):
            ok_checks.append("prop firm audit never calls mt5.order_send")
        else:
            blockers.append("prop firm audit calls mt5.order_send")
        if _has_no_banned_betting(own_code):
            ok_checks.append("prop firm audit has no martingale/grid/averaging logic")
        else:
            blockers.append("prop firm audit contains banned betting logic")
    except Exception as e:
        blockers.append(f"prop firm audit self-check error: {e}")

    result = {
        "timestamp_utc": ts,
        "head_short": head,
        "verdict": verdict,
        "profiles_path": str(profiles_path),
        "profile_count": len(profile_results),
        "active_profiles_count": active_count,
        "inactive_legacy_profiles_count": inactive_count,
        "active_profiles_blocked_count": active_blocked_count,
        "inactive_legacy_review_count": inactive_review_count,
        "profiles": profile_results,
        "ok_checks": ok_checks,
        "warnings": warnings,
        "blockers": blockers,
        "design_description": (
            "Every prop-firm profile is validated by PropFirmRuleEngine. "
            "Critical unknown rules fail closed for funded/live profiles. "
            "Simulation-only profiles (explicitly marked) may ship with "
            "unknown non-critical rules. Internal DD stops must sit below "
            "external prop-firm limits. The audit NEVER calls mt5.order_send "
            "and NEVER contains martingale/grid/averaging logic."
        ),
        "no_martingale": True,
        "no_grid": True,
        "no_averaging": True,
    }

    # Re-evaluate verdict if self-audit added blockers.
    if blockers and verdict == PROP_FIRM_READY:
        verdict = PROP_FIRM_BLOCKED
        result["verdict"] = verdict

    return result


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
    json_path = out_dir / "prop_firm_readiness_audit.json"
    md_path = out_dir / "prop_firm_readiness_audit.md"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str, ensure_ascii=False)

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# TITAN XAU AI - Prop Firm Readiness Audit\n\n")
        f.write(f"**Verdict:** **{result['verdict']}**\n\n")
        f.write(f"**Design:** {result['design_description']}\n\n")
        f.write(f"**Timestamp:** {result['timestamp_utc']}\n\n")
        f.write(f"**Head:** {result['head_short']}\n\n")
        f.write(
            f"**Profiles:** {result['profile_count']} (from "
            f"`{result['profiles_path']}`)\n\n"
        )
        f.write("## Per-profile verdicts\n\n")
        f.write("| Profile | Verdict | Unknown Critical | Blockers | Warnings |\n")
        f.write("|---|---|---|---|---|\n")
        for p in result["profiles"]:
            f.write(
                f"| {p['profile_name']} | {p['verdict']} | "
                f"{p['unknown_critical_count']} | "
                f"{len(p['blockers'])} | {len(p['warnings'])} |\n"
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

        f.write("\n## Per-profile detail\n\n")
        for p in result["profiles"]:
            f.write(f"### {p['profile_name']}\n\n")
            f.write(f"- **Verdict:** {p['verdict']}\n")
            f.write(f"- **Unknown critical:** {p['unknown_critical_count']}\n")
            f.write(f"- **Blockers:** {len(p['blockers'])}\n")
            f.write(f"- **Warnings:** {len(p['warnings'])}\n")
            f.write(
                f"- **no_martingale / no_grid / no_averaging:** "
                f"{p['no_martingale']} / {p['no_grid']} / {p['no_averaging']}\n"
            )
            if p["blockers"]:
                f.write("\n  **Blockers:**\n")
                for b in p["blockers"]:
                    f.write(f"  - {b}\n")
            if p["warnings"]:
                f.write("\n  **Warnings:**\n")
                for w in p["warnings"]:
                    f.write(f"  - {w}\n")
            f.write("\n")

        f.write(
            "\n**The audit NEVER calls mt5.order_send and NEVER contains "
            "martingale/grid/averaging logic.**\n"
        )

    return {"json_path": str(json_path), "md_path": str(md_path)}


def main() -> int:
    print("=" * 70)
    print("  TITAN XAU AI - Prop Firm Readiness Audit")
    print("=" * 70)
    result = run_audit()
    report = write_report(result)
    print(f"\n  Verdict: {result['verdict']}")
    print(f"  Profiles: {result['profile_count']}")
    print(f"  Blockers: {len(result['blockers'])}")
    print(f"  Warnings: {len(result['warnings'])}")
    print(f"\n  JSON: {report['json_path']}")
    print(f"  MD:   {report['md_path']}")
    print("\n" + "=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
