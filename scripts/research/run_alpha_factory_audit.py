"""
TITAN XAU AI - Alpha Factory Audit Script
=========================================

Audits the alpha-factory research layer and emits a JSON verdict report
to ``data/audit/demo_micro_execution/alpha_factory_audit.json``.

The audit verifies that:
    * the alpha factory modules import cleanly
    * the AlphaStatus vocabulary is intact (all six expected statuses)
    * the generator never produces live-status candidates
    * the evaluator exposes ``never_auto_approve_live()`` returning False
    * the registry persists to ``data/audit/alpha_factory/alpha_registry.json``
    * no module imports MetaTrader5 or calls ``order_send``
    * no martingale / grid / averaging / loss_based_lot_multiplier is
      present in source code

Verdicts:
    * ALPHA_FACTORY_READY           — modules present, statuses valid,
                                      no auto-live, at least one candidate
                                      registered.
    * ALPHA_FACTORY_NEEDS_CANDIDATES — modules present and statuses valid,
                                      but the registry has zero candidates.
    * ALPHA_FACTORY_BLOCKED         — one or more structural / safety
                                      invariants failed.

NEVER imports MetaTrader5. NEVER calls mt5.order_send. NEVER sends orders.
"""
from __future__ import annotations

import importlib
import inspect
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from titan.research.alpha_factory.alpha_candidate_generator import (  # noqa: E402
    AlphaCandidate,
    AlphaCandidateGenerator,
    SAFETY_CONTRACT as CAND_SAFETY,
)
from titan.research.alpha_factory.alpha_evaluator import (  # noqa: E402
    ALL_STATUSES,
    AlphaEvaluator,
    AlphaStatus,
    SAFETY_CONTRACT as EV_SAFETY,
)
from titan.research.alpha_factory.alpha_registry import (  # noqa: E402
    AlphaRegistry,
    DEFAULT_REGISTRY_PATH,
)

REPORT_PATH = REPO_ROOT / "data" / "audit" / "demo_micro_execution" / "alpha_factory_audit.json"

EXPECTED_STATUSES = {
    AlphaStatus.CANDIDATE,
    AlphaStatus.REJECTED_OVERFIT,
    AlphaStatus.REJECTED_COST_ADJUSTED,
    AlphaStatus.VALIDATED_SHADOW_ONLY,
    AlphaStatus.APPROVED_FOR_DEMO,
    AlphaStatus.APPROVED_FOR_LIVE_PENDING_HUMAN,
}

FORBIDDEN_PATTERNS = [
    r"import\s+MetaTrader5",
    r"from\s+MetaTrader5",
    r"\bmt5\.order_send\s*\(",
    r"\bmartingale\b(?!\s*[:=]\s*False)",
    r"\bgrid_(?:step|level|order)\b",
    r"\baveraging_(?:down|up)\b",
    r"\bloss_based_lot_multiplier\b(?!\s*[:=]\s*True)",
    r"\bdef\s+martingale\b",
    r"\bdef\s+grid\b",
    r"\bdef\s+averaging\b",
]

MODULE_PATHS = {
    "alpha_candidate_generator": REPO_ROOT / "titan" / "research" / "alpha_factory" / "alpha_candidate_generator.py",
    "alpha_evaluator": REPO_ROOT / "titan" / "research" / "alpha_factory" / "alpha_evaluator.py",
    "alpha_registry": REPO_ROOT / "titan" / "research" / "alpha_factory" / "alpha_registry.py",
}


def _read_source(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _strip_docstrings_and_comments(src: str) -> str:
    """Remove triple-quoted docstrings and # comments from source text.

    This lets the forbidden-pattern scan focus on actual code and not
    flag documentation lines that mention the very patterns we forbid.
    """
    cleaned = re.sub(r'"""[\s\S]*?"""', "", src)
    cleaned = re.sub(r"'''[\s\S]*?'''", "", cleaned)
    out_lines: list[str] = []
    for line in cleaned.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if "#" in line:
            line = line.split("#", 1)[0]
        out_lines.append(line)
    return "\n".join(out_lines)


def _scan_forbidden_patterns() -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for mod_name, path in MODULE_PATHS.items():
        src = _read_source(path)
        code_only = _strip_docstrings_and_comments(src)
        for pat in FORBIDDEN_PATTERNS:
            for line_no, line in enumerate(code_only.splitlines(), start=1):
                if re.search(pat, line, flags=re.IGNORECASE):
                    findings.append(
                        {
                            "module": mod_name,
                            "path": str(path.relative_to(REPO_ROOT)),
                            "line": line_no,
                            "pattern": pat,
                            "sample": line.strip()[:160],
                        }
                    )
    return findings


def run_audit() -> dict[str, Any]:
    """Run the alpha-factory audit and return the verdict payload."""
    checks: dict[str, Any] = {}
    blockers: list[str] = []

    # ── 1. Modules import ─────────────────────────────────────────────
    try:
        importlib.import_module("titan.research.alpha_factory.alpha_candidate_generator")
        importlib.import_module("titan.research.alpha_factory.alpha_evaluator")
        importlib.import_module("titan.research.alpha_factory.alpha_registry")
        checks["modules_import"] = True
    except Exception as exc:  # noqa: BLE001
        checks["modules_import"] = False
        blockers.append(f"Module import failed: {exc!r}")

    # ── 2. All six statuses present ──────────────────────────────────
    statuses_present = set(ALL_STATUSES)
    checks["all_statuses_present"] = statuses_present == EXPECTED_STATUSES
    checks["statuses_found"] = sorted(statuses_present)
    checks["statuses_expected"] = sorted(EXPECTED_STATUSES)
    if not checks["all_statuses_present"]:
        blockers.append("Status vocabulary incomplete")

    # ── 3. No auto-live ──────────────────────────────────────────────
    try:
        ev = AlphaEvaluator()
        no_auto_live = ev.never_auto_approve_live() is False
    except Exception:  # noqa: BLE001
        no_auto_live = False
    checks["no_auto_live"] = bool(no_auto_live)
    if not no_auto_live:
        blockers.append("Evaluator never_auto_approve_live() did not return False")

    # Also confirm: no candidate can be constructed with a live status.
    live_blocked = True
    try:
        AlphaCandidate(
            name="should_fail",
            description="live status",
            formula_type="MOMENTUM",
            parameters={},
            status="APPROVED_FOR_LIVE",
        )
        live_blocked = False
    except ValueError:
        live_blocked = True
    except Exception:  # noqa: BLE001
        live_blocked = False
    checks["candidate_rejects_live_status"] = bool(live_blocked)
    if not live_blocked:
        blockers.append("AlphaCandidate accepted a live status at construction")

    # ── 4. Safety contract present in all modules ────────────────────
    safety_ok = (
        CAND_SAFETY.get("no_martingale") is True
        and CAND_SAFETY.get("no_grid") is True
        and CAND_SAFETY.get("no_averaging") is True
        and CAND_SAFETY.get("no_loss_based_lot_multiplier") is True
        and CAND_SAFETY.get("no_auto_live") is True
        and CAND_SAFETY.get("no_order_send") is True
        and EV_SAFETY.get("no_martingale") is True
        and EV_SAFETY.get("no_grid") is True
        and EV_SAFETY.get("no_averaging") is True
    )
    checks["safety_contract_intact"] = bool(safety_ok)
    if not safety_ok:
        blockers.append("Safety contract flags missing or False")

    # ── 5. Forbidden pattern scan ────────────────────────────────────
    findings = _scan_forbidden_patterns()
    checks["forbidden_pattern_findings"] = findings
    checks["no_forbidden_patterns"] = len(findings) == 0
    if findings:
        blockers.append(
            f"Forbidden patterns detected in {len(findings)} location(s)"
        )

    # ── 6. Generator produces candidates with status=CANDIDATE ───────
    try:
        gen = AlphaCandidateGenerator()
        cands = gen.generate_candidates()
        all_candidate = all(c.status == "CANDIDATE" for c in cands)
        all_safety_ok = all(
            c.safety.get("no_martingale") is True
            and c.safety.get("no_grid") is True
            and c.safety.get("no_averaging") is True
            and c.safety.get("no_auto_live") is True
            for c in cands
        )
        checks["generator_produces_candidates"] = len(cands) > 0
        checks["generator_all_candidate_status"] = bool(all_candidate)
        checks["generator_all_safety_ok"] = bool(all_safety_ok)
        if not all_candidate or not all_safety_ok:
            blockers.append("Generator produced unsafe or non-CANDIDATE candidates")
    except Exception as exc:  # noqa: BLE001
        checks["generator_produces_candidates"] = False
        blockers.append(f"Generator failed: {exc!r}")

    # ── 7. Registry path configured ──────────────────────────────────
    checks["registry_path"] = str(DEFAULT_REGISTRY_PATH.relative_to(REPO_ROOT))
    checks["registry_path_exists"] = DEFAULT_REGISTRY_PATH.parent.exists()

    # ── 8. Registry candidate count (drives verdict) ─────────────────
    try:
        registry = AlphaRegistry()
        checks["registry_candidate_count"] = len(registry.list_all())
    except Exception as exc:  # noqa: BLE001
        checks["registry_candidate_count"] = 0
        blockers.append(f"Registry load failed: {exc!r}")

    # ── 9. Source-level audit (no order_send / no mt5 import) ────────
    src_scan_ok = True
    for mod_name, path in MODULE_PATHS.items():
        src = _read_source(path)
        if "import MetaTrader5" in src or "from MetaTrader5" in src:
            src_scan_ok = False
            blockers.append(f"{mod_name}: MetaTrader5 import detected")
        # detect any actual mt5.order_send call (not the negation flag)
        for line in src.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if re.search(r"\bmt5\.order_send\s*\(", stripped) and "no_order_send" not in stripped:
                src_scan_ok = False
                blockers.append(f"{mod_name}: mt5.order_send call detected")
    checks["source_scan_clean"] = bool(src_scan_ok)

    # ── Verdict ───────────────────────────────────────────────────────
    if blockers:
        verdict = "ALPHA_FACTORY_BLOCKED"
    elif checks.get("registry_candidate_count", 0) == 0:
        verdict = "ALPHA_FACTORY_NEEDS_CANDIDATES"
    else:
        verdict = "ALPHA_FACTORY_READY"

    return {
        "verdict": verdict,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
        "blockers": blockers,
        "safety_contract": dict(CAND_SAFETY),
    }


def write_report(report: Optional[dict[str, Any]] = None, path: Optional[Path] = None) -> Path:
    """Persist the audit report to ``data/audit/demo_micro_execution/alpha_factory_audit.json``."""
    if report is None:
        report = run_audit()
    out_path = Path(path) if path is not None else REPORT_PATH
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(out_path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, sort_keys=True)
    tmp.replace(out_path)
    return out_path


def main() -> int:
    report = run_audit()
    out = write_report(report)
    print(f"[alpha_factory_audit] verdict={report['verdict']}")
    print(f"[alpha_factory_audit] blockers={report['blockers']}")
    print(f"[alpha_factory_audit] report={out}")
    if report["verdict"] == "ALPHA_FACTORY_BLOCKED":
        return 2
    if report["verdict"] == "ALPHA_FACTORY_NEEDS_CANDIDATES":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
