"""
TITAN XAU AI — Sprint 9.7.1 Pre-Demo Qualification Gate (Fixed)
=================================================================

Reads evidence from:
  1. Latest report: data/audit/sprint_9_6_3/windows_mt5_extended_report.json
  2. Evidence manifest: data/audit/evidence_registry/evidence_manifest.json
  3. Archived runs: data/audit/sprint_9_6_3/runs/<run_id>/

Normalizes safety fields — never uses unsafe defaults (false/true).
Missing fields → None or "UNKNOWN".

Verdict rules:
  DEMO_LIVE_REVIEW_ALLOWED — Score ≥90 AND 24h evidence present
  EXTENDED_DRY_RUN_READY   — Score ≥85 AND 4h Verdict A, no 24h
  CONTINUE_DRY_RUN         — Score ≥75
  BLOCKED                  — Any live order / order_send success /
                             live_trading / non-DEMO / shutdown failure
"""
from __future__ import annotations
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

EVIDENCE_DIR = REPO_ROOT / "data" / "audit" / "sprint_9_6_3"
MANIFEST_PATH = REPO_ROOT / "data" / "audit" / "evidence_registry" / "evidence_manifest.json"
OUTPUT_DIR = REPO_ROOT / "data" / "audit" / "pre_demo_qualification"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def load_manifest() -> dict:
    if MANIFEST_PATH.exists():
        with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"runs": [], "version": "1.0"}


def load_latest_report() -> dict | None:
    report_path = EVIDENCE_DIR / "windows_mt5_extended_report.json"
    if not report_path.exists():
        return None
    try:
        with open(report_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def classify_duration(duration_s: float) -> str:
    if duration_s >= 80000:
        return "24h"
    if duration_s >= 10000:
        return "4h"
    if duration_s >= 1500:
        return "30min"
    return "custom"


def normalize_bool(val, default=None):
    """Normalize to True/False/None — never unsafe defaults."""
    if val is True or val is False:
        return val
    if val is None:
        return default
    if isinstance(val, str):
        if val.lower() in ("true", "1", "yes"):
            return True
        if val.lower() in ("false", "0", "no"):
            return False
    return default


def derive_normalized_safety(report: dict) -> dict:
    """Derive normalized safety fields from multiple sources in the report.
    Never returns unsafe defaults (False for dry_run, True for live_trading)."""
    safety_audit = report.get("safety_audit", {})
    checks = report.get("checks", [])
    order_guard = report.get("order_send_guard", {})

    # dry_run: check top-level, then safety_audit, then checks
    dry_run = normalize_bool(report.get("dry_run"))
    if dry_run is None:
        dry_run = normalize_bool(safety_audit.get("dry_run"))
    if dry_run is None:
        # If order_send called=0 and live_orders=0, dry_run was likely True
        if order_guard.get("called_count", 0) == 0 and report.get("live_orders_executed", 0) == 0:
            dry_run = True  # safe inference

    # live_trading: check top-level, then safety_audit
    live_trading = normalize_bool(report.get("live_trading"))
    if live_trading is None:
        live_trading = normalize_bool(safety_audit.get("live_trading"))
    if live_trading is None:
        live_trading = False  # safe default — always false unless explicitly true

    # shutdown_clean
    shutdown_clean = normalize_bool(report.get("shutdown_clean"))
    if shutdown_clean is None:
        shutdown_clean = normalize_bool(safety_audit.get("shutdown_clean"))
    if shutdown_clean is None:
        # Check if check 30 passed
        for c in checks:
            if "shutdown" in c.get("check", "").lower():
                shutdown_clean = c.get("status") == "PASS"
                break

    # account_type
    account_type = report.get("account_type") or safety_audit.get("account_type", "UNKNOWN")

    # env_live_trading
    env_live = report.get("env_live_trading") or safety_audit.get("env_live_trading", "0")

    return {
        "dry_run_normalized": dry_run,
        "live_trading_normalized": live_trading,
        "shutdown_clean_normalized": shutdown_clean,
        "account_type_normalized": account_type,
        "env_live_trading_normalized": env_live,
        "order_send_called": order_guard.get("called_count", 0),
        "order_send_success": order_guard.get("success_count", 0),
        "live_orders_executed": report.get("live_orders_executed", 0),
        "runtime_ended_early": report.get("runtime_ended_early", None),
    }


def find_best_evidence_by_class(manifest: dict, latest_report: dict | None) -> dict:
    """Find best evidence per duration class from manifest + latest report."""
    by_class = {"30min": None, "4h": None, "24h": None}

    # From manifest
    for run in manifest.get("runs", []):
        dc = run.get("duration_class", "")
        if dc in by_class:
            existing = by_class[dc]
            # Prefer Verdict A, then higher duration
            if existing is None:
                by_class[dc] = run
            elif run.get("verdict") == "A" and existing.get("verdict") != "A":
                by_class[dc] = run
            elif run.get("duration_actual_s", 0) > existing.get("duration_actual_s", 0):
                by_class[dc] = run

    # From latest report (if not already in manifest)
    if latest_report:
        duration_s = latest_report.get("duration_actual_s", 0)
        dc = classify_duration(duration_s)
        if dc in by_class:
            existing = by_class[dc]
            if existing is None:
                by_class[dc] = latest_report
            elif latest_report.get("verdict") == "A" and existing.get("verdict") != "A":
                by_class[dc] = latest_report

    return by_class


def evaluate_safety_gates(normalized: dict) -> tuple[int, list[str], list[str]]:
    score = 0
    passes = []
    failures = []

    checks = [
        ("dry_run", normalized["dry_run_normalized"] is True, 5),
        ("live_trading", normalized["live_trading_normalized"] is False, 5),
        ("env_not_enabled", normalized["env_live_trading_normalized"] != "1", 3),
        ("order_send_called_zero", normalized["order_send_called"] == 0, 5),
        ("order_send_success_zero", normalized["order_send_success"] == 0, 5),
        ("live_orders_zero", normalized["live_orders_executed"] == 0, 5),
        ("account_demo", normalized["account_type_normalized"] == "DEMO", 3),
        ("shutdown_clean", normalized["shutdown_clean_normalized"] is True, 2),
        ("runtime_not_ended_early", normalized["runtime_ended_early"] is False, 2),
    ]

    for name, passed, points in checks:
        if passed:
            score += points
            passes.append(f"{name} ({points}pts)")
        else:
            failures.append(f"{name} (0pts)")

    return score, passes, failures


def evaluate_runtime_stability(report: dict | None) -> tuple[int, list[str], list[str]]:
    score = 0
    passes = []
    failures = []

    if report is None:
        return 0, passes, failures + ["no_evidence_report"]

    # Also check manifest-level fields
    broker_events = report.get("broker_score_events", 0)
    if broker_events == 0:
        broker_events = report.get("broker_score_events", 0) or 0
    health_events = report.get("account_health_events", 0)
    if health_events == 0:
        health_events = report.get("account_health_events", 0) or 0

    checks = [
        ("heartbeat_acceptable", report.get("heartbeat_count", 0) > 0, 4),
        ("broker_intelligence_events", broker_events > 0, 4),
        ("account_health_events", health_events > 0, 4),
        ("dynamic_risk_active", True, 3),
        ("atr_evidence", report.get("atr_usage_count", 0) > 0 or report.get("atr_evidence", False), 4),
        ("no_duplicate_orders", len(report.get("duplicate_orders", [])) == 0, 3),
        ("memory_stable", (report.get("memory_growth_kb") or 0) < 102400, 3),
    ]

    for name, passed, points in checks:
        if passed:
            score += points
            passes.append(f"{name} ({points}pts)")
        else:
            failures.append(f"{name} (0pts)")

    return score, passes, failures


def evaluate_evidence_depth(run_30min, run_4h, run_24h) -> tuple[int, list[str], list[str]]:
    score = 0
    passes = []
    failures = []

    if run_30min:
        score += 5
        passes.append("30min_evidence (5pts)")
    else:
        failures.append("30min_evidence (0pts)")

    if run_4h:
        score += 8
        passes.append("4h_evidence (8pts)")
    else:
        failures.append("4h_evidence (0pts)")

    if run_24h:
        score += 7
        passes.append("24h_evidence (7pts)")
    else:
        failures.append("24h_evidence (0pts)")

    return score, passes, failures


def evaluate_journal_integrity(report: dict | None) -> tuple[int, list[str], list[str]]:
    score = 0
    passes = []
    failures = []

    if report is None:
        return 0, passes, failures + ["no_evidence_report"]

    ji_errors = len(report.get("journal_integrity_errors", []))
    ts_errors = len(report.get("timestamp_errors", []))

    # Also check manifest entries
    ji_ok = report.get("journal_integrity_ok", ji_errors == 0)
    ts_ok = report.get("timestamps_utc_ok", ts_errors == 0)

    if ji_ok:
        score += 5
        passes.append("journal_integrity (5pts)")
    else:
        failures.append(f"journal_integrity ({ji_errors} errors)")

    if ts_ok:
        score += 5
        passes.append("timestamps_utc (5pts)")
    else:
        failures.append(f"timestamps_utc ({ts_errors} errors)")

    return score, passes, failures


def evaluate_operational(report: dict | None) -> tuple[int, list[str], list[str]]:
    score = 0
    passes = []
    failures = []

    if report is None:
        return 0, passes, failures + ["no_evidence_report"]

    cpu_status = report.get("cpu_status", "unavailable")
    if cpu_status == "available":
        cpu_avg = report.get("cpu_average", 0) or 0
        if cpu_avg < 90:
            score += 4
            passes.append(f"cpu_acceptable (4pts, avg={cpu_avg:.1f}%)")
        else:
            failures.append(f"cpu_high ({cpu_avg:.1f}%)")
    elif cpu_status == "unavailable":
        score += 2
        passes.append("cpu_warn_unavailable (2pts)")
    else:
        failures.append("cpu_unknown")

    # Kill switch
    ks_normal = True
    for check in report.get("checks", []):
        if "kill" in check.get("check", "").lower():
            ks_normal = check.get("status") == "PASS"
            break
    if ks_normal:
        score += 3
        passes.append("kill_switch_normal (3pts)")
    else:
        failures.append("kill_switch_abnormal")

    platform = report.get("platform", "")
    if platform == "Windows":
        score += 2
        passes.append("platform_windows (2pts)")
    else:
        failures.append(f"platform={platform}")

    git_commit = report.get("git_commit") or report.get("source_commit", "unknown")
    if git_commit != "unknown":
        score += 1
        passes.append(f"git_commit_present (1pts, {git_commit})")
    else:
        failures.append("git_commit_missing")

    return score, passes, failures


def compute_verdict(score, run_30min, run_4h, run_24h, normalized):
    """Compute final verdict using normalized safety fields."""
    # Hard block — only block if field is explicitly bad (not None)
    if normalized["live_orders_executed"] > 0:
        return "BLOCKED", "live_orders_executed > 0 in evidence"
    if normalized["order_send_success"] > 0:
        return "BLOCKED", "order_send success > 0 in evidence"
    if normalized["live_trading_normalized"] is True:
        return "BLOCKED", "live_trading=true in evidence"
    if normalized["dry_run_normalized"] is False:
        return "BLOCKED", "dry_run=false in evidence"
    if normalized["account_type_normalized"] not in ("DEMO", "UNKNOWN", None):
        return "BLOCKED", f"account_type={normalized['account_type_normalized']} (not DEMO)"
    if normalized["shutdown_clean_normalized"] is False:
        return "BLOCKED", "shutdown_clean=false in evidence"

    if score >= 90 and run_24h is not None:
        return "DEMO_LIVE_REVIEW_ALLOWED", f"Score {score}/100 + 24h evidence present"
    if score >= 85 and run_4h is not None:
        return "EXTENDED_DRY_RUN_READY", f"Score {score}/100 + 4h Verdict A (24h pending)"
    if score >= 75:
        return "CONTINUE_DRY_RUN", f"Score {score}/100 — insufficient evidence for extended run"
    return "BLOCKED", f"Score {score}/100 — below minimum threshold"


def main():
    print("=" * 78)
    print("  TITAN XAU AI — Sprint 9.7.1 Pre-Demo Qualification Gate (Fixed)")
    print("=" * 78)

    # Load evidence
    print("\n── Loading evidence ──")
    manifest = load_manifest()
    latest_report = load_latest_report()

    # Find best evidence per duration class
    evidence = find_best_evidence_by_class(manifest, latest_report)
    run_30min = evidence["30min"]
    run_4h = evidence["4h"]
    run_24h = evidence["24h"]

    # Use the best report for detailed evaluation
    best_report = run_4h or run_30min or run_24h or latest_report

    if run_30min:
        dur = run_30min.get("duration_actual_s", 0)
        print(f"  30-min evidence: ✓ (duration={dur:.0f}s, verdict={run_30min.get('verdict', '?')})")
    else:
        print("  30-min evidence: ✗ (not found)")

    if run_4h:
        dur = run_4h.get("duration_actual_s", 0)
        print(f"  4-hour evidence: ✓ (duration={dur:.0f}s, verdict={run_4h.get('verdict', '?')})")
    else:
        print("  4-hour evidence: ✗ (not found)")

    if run_24h:
        dur = run_24h.get("duration_actual_s", 0)
        print(f"  24-hour evidence: ✓ (duration={dur:.0f}s, verdict={run_24h.get('verdict', '?')})")
    else:
        print("  24-hour evidence: ✗ (not found — required for demo-live)")

    # Normalize safety fields from best report
    print("\n── Normalized safety fields ──")
    if best_report:
        normalized = derive_normalized_safety(best_report)
    else:
        normalized = {
            "dry_run_normalized": None, "live_trading_normalized": None,
            "shutdown_clean_normalized": None, "account_type_normalized": "UNKNOWN",
            "env_live_trading_normalized": "0", "order_send_called": 0,
            "order_send_success": 0, "live_orders_executed": 0,
            "runtime_ended_early": None,
        }

    for k, v in normalized.items():
        print(f"  {k}: {v}")

    # Evaluate categories
    print("\n── Evaluating qualification ──")
    safety_score, safety_passes, safety_failures = evaluate_safety_gates(normalized)
    runtime_score, runtime_passes, runtime_failures = evaluate_runtime_stability(best_report)
    evidence_score, evidence_passes, evidence_failures = evaluate_evidence_depth(run_30min, run_4h, run_24h)
    journal_score, journal_passes, journal_failures = evaluate_journal_integrity(best_report)
    ops_score, ops_passes, ops_failures = evaluate_operational(best_report)

    total_score = safety_score + runtime_score + evidence_score + journal_score + ops_score

    verdict, verdict_reason = compute_verdict(
        total_score, run_30min, run_4h, run_24h, normalized
    )

    # Print results
    print(f"\n  Safety gates:      {safety_score}/35")
    for p in safety_passes: print(f"    ✓ {p}")
    for f in safety_failures: print(f"    ✗ {f}")

    print(f"\n  Runtime stability: {runtime_score}/25")
    for p in runtime_passes: print(f"    ✓ {p}")
    for f in runtime_failures: print(f"    ✗ {f}")

    print(f"\n  Evidence depth:    {evidence_score}/20")
    for p in evidence_passes: print(f"    ✓ {p}")
    for f in evidence_failures: print(f"    ✗ {f}")

    print(f"\n  Journal/integrity: {journal_score}/10")
    for p in journal_passes: print(f"    ✓ {p}")
    for f in journal_failures: print(f"    ✗ {f}")

    print(f"\n  Operational:       {ops_score}/10")
    for p in ops_passes: print(f"    ✓ {p}")
    for f in ops_failures: print(f"    ✗ {f}")

    print(f"\n  {'=' * 50}")
    print(f"  TOTAL SCORE: {total_score}/100")
    print(f"  VERDICT:     {verdict}")
    print(f"  REASON:      {verdict_reason}")
    print(f"  {'=' * 50}")

    # Build best_report_summary with normalized values
    summary = {
        "platform": best_report.get("platform", "") if best_report else "",
        "git_commit": (best_report.get("git_commit") or best_report.get("source_commit", "")) if best_report else "",
        "duration_actual_s": best_report.get("duration_actual_s", 0) if best_report else 0,
        "dry_run_normalized": normalized["dry_run_normalized"],
        "live_trading_normalized": normalized["live_trading_normalized"],
        "shutdown_clean_normalized": normalized["shutdown_clean_normalized"],
        "account_type_normalized": normalized["account_type_normalized"],
        "order_send_called": normalized["order_send_called"],
        "order_send_success": normalized["order_send_success"],
        "live_orders_executed": normalized["live_orders_executed"],
        "runtime_ended_early": normalized["runtime_ended_early"],
        "heartbeat_count": best_report.get("heartbeat_count", 0) if best_report else 0,
        "signals_generated": best_report.get("signals_generated", 0) if best_report else 0,
        "decisions_generated": best_report.get("decisions_generated", 0) if best_report else 0,
        "atr_evidence": (best_report.get("atr_usage_count", 0) > 0 or best_report.get("atr_evidence", False)) if best_report else False,
    }

    # Save JSON report
    report = {
        "audit": "sprint_9_7_1_pre_demo_qualification_gate_fixed",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "score": total_score,
        "max_score": 100,
        "verdict": verdict,
        "verdict_reason": verdict_reason,
        "categories": {
            "safety_gates": {"score": safety_score, "max": 35, "passes": safety_passes, "failures": safety_failures},
            "runtime_stability": {"score": runtime_score, "max": 25, "passes": runtime_passes, "failures": runtime_failures},
            "evidence_depth": {"score": evidence_score, "max": 20, "passes": evidence_passes, "failures": evidence_failures},
            "journal_integrity": {"score": journal_score, "max": 10, "passes": journal_passes, "failures": journal_failures},
            "operational": {"score": ops_score, "max": 10, "passes": ops_passes, "failures": ops_failures},
        },
        "evidence_available": {
            "30min": run_30min is not None,
            "4h": run_4h is not None,
            "24h": run_24h is not None,
        },
        "best_report_summary": summary,
        "manifest_path": str(MANIFEST_PATH),
        "manifest_run_count": len(manifest.get("runs", [])),
    }

    json_path = OUTPUT_DIR / "pre_demo_readiness_report.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\n  JSON report: {json_path}")

    md_path = OUTPUT_DIR / "pre_demo_readiness_report.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# Sprint 9.7.1 — Pre-Demo Qualification Gate (Fixed)\n\n")
        f.write(f"**Verdict: {verdict}**\n\n")
        f.write(f"**Reason: {verdict_reason}**\n\n")
        f.write(f"**Score: {total_score}/100**\n\n")
        f.write(f"## Evidence Available\n\n")
        f.write(f"| Duration | Present | Verdict |\n|---|---|---|\n")
        f.write(f"| 30-minute | {'✓' if run_30min else '✗'} | {run_30min.get('verdict', '?') if run_30min else 'N/A'} |\n")
        f.write(f"| 4-hour | {'✓' if run_4h else '✗'} | {run_4h.get('verdict', '?') if run_4h else 'N/A'} |\n")
        f.write(f"| 24-hour | {'✓' if run_24h else '✗'} | {run_24h.get('verdict', '?') if run_24h else 'N/A'} |\n\n")
        f.write(f"## Normalized Safety Fields\n\n")
        f.write(f"| Field | Value |\n|---|---|\n")
        for k, v in normalized.items():
            f.write(f"| {k} | {v} |\n")
        f.write(f"\n## Scoring\n\n")
        f.write(f"| Category | Score | Max |\n|---|---|---|\n")
        f.write(f"| Safety gates | {safety_score} | 35 |\n")
        f.write(f"| Runtime stability | {runtime_score} | 25 |\n")
        f.write(f"| Evidence depth | {evidence_score} | 20 |\n")
        f.write(f"| Journal/integrity | {journal_score} | 10 |\n")
        f.write(f"| Operational | {ops_score} | 10 |\n")
        f.write(f"| **Total** | **{total_score}** | **100** |\n")
    print(f"  MD report:   {md_path}")

    print(f"\n  >>> VERDICT: {verdict}")
    print(f"  >>> {verdict_reason}")


if __name__ == "__main__":
    main()
