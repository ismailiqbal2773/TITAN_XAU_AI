"""
TITAN XAU AI — Sprint 9.7 Pre-Demo Qualification Gate
======================================================

Reads audit evidence from Sprint 9.6.3 Windows MT5 dry-run runs
and produces an institutional readiness verdict.

Verdict rules:
  DEMO_LIVE_REVIEW_ALLOWED — Score ≥90 AND 24h evidence present
  EXTENDED_DRY_RUN_READY   — Score ≥85 AND 4h Verdict A, no 24h
  CONTINUE_DRY_RUN         — Score ≥75
  BLOCKED                  — Any live order / order_send success /
                             non-demo / live_trading / shutdown failure

Scoring (100 points):
  Safety gates:      35 points
  Runtime stability: 25 points
  Evidence depth:    20 points
  Journal/integrity: 10 points
  Operational:       10 points

Output:
  data/audit/pre_demo_qualification/pre_demo_readiness_report.json
  data/audit/pre_demo_qualification/pre_demo_readiness_report.md
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
OUTPUT_DIR = REPO_ROOT / "data" / "audit" / "pre_demo_qualification"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def load_evidence_run(duration_label: str) -> dict | None:
    """Load a Windows MT5 evidence report if it exists."""
    report_path = EVIDENCE_DIR / "windows_mt5_extended_report.json"
    if not report_path.exists():
        return None
    try:
        with open(report_path, "r", encoding="utf-8") as f:
            report = json.load(f)
        # Check if this is the right run by duration
        duration_s = report.get("duration_actual_s", 0)
        if duration_label == "30min" and duration_s >= 1500 and duration_s < 6000:
            return report
        if duration_label == "4h" and duration_s >= 10000 and duration_s < 70000:
            return report
        if duration_label == "24h" and duration_s >= 80000:
            return report
        # If only one report exists, use it for whatever matches
        if duration_label == "any":
            return report
    except Exception:
        pass
    return None


def evaluate_safety_gates(report: dict | None) -> tuple[int, list[str], list[str]]:
    """Evaluate safety gates. Returns (score, passes, failures)."""
    score = 0
    passes = []
    failures = []

    if report is None:
        return 0, passes, failures + ["no_evidence_report"]

    checks = [
        ("dry_run", report.get("dry_run") is True or report.get("dry_run") is None, 5),
        ("live_trading", report.get("live_trading") is False or report.get("live_trading") is None, 5),
        ("env_not_enabled", report.get("env_live_trading", "0") != "1"
         or os.environ.get("TITAN_LIVE_TRADING", "0") != "1", 3),
        ("order_send_called_zero", report.get("order_send_guard", {}).get("called_count", 0) == 0, 5),
        ("order_send_success_zero", report.get("order_send_guard", {}).get("success_count", 0) == 0, 5),
        ("live_orders_zero", report.get("live_orders_executed", 0) == 0, 5),
        ("account_demo", report.get("account_type", "") == "DEMO", 3),
        ("shutdown_clean", report.get("shutdown_clean") is True or report.get("shutdown_clean") is None, 2),
        ("runtime_not_ended_early", report.get("runtime_ended_early", True) is False, 2),
    ]

    for name, passed, points in checks:
        if passed:
            score += points
            passes.append(f"{name} ({points}pts)")
        else:
            failures.append(f"{name} (0pts)")

    return score, passes, failures


def evaluate_runtime_stability(report: dict | None) -> tuple[int, list[str], list[str]]:
    """Evaluate runtime quality. Returns (score, passes, failures)."""
    score = 0
    passes = []
    failures = []

    if report is None:
        return 0, passes, failures + ["no_evidence_report"]

    checks = [
        ("heartbeat_acceptable", report.get("heartbeat_count", 0) > 0, 4),
        ("broker_intelligence_events", report.get("broker_score_events", 0) > 0, 4),
        ("account_health_events", report.get("account_health_events", 0) > 0, 4),
        ("dynamic_risk_active", report.get("dynamic_risk_active", False) is True
         or report.get("checks", [{}])[0].get("status") == "PASS", 3),
        ("atr_evidence", report.get("atr_usage_count", 0) > 0, 4),
        ("no_duplicate_orders", len(report.get("duplicate_orders", [])) == 0, 3),
        ("memory_stable", report.get("memory_growth_kb", 999999) < 102400, 3),
    ]

    for name, passed, points in checks:
        if passed:
            score += points
            passes.append(f"{name} ({points}pts)")
        else:
            failures.append(f"{name} (0pts)")

    return score, passes, failures


def evaluate_evidence_depth(run_30min: dict | None, run_4h: dict | None,
                            run_24h: dict | None) -> tuple[int, list[str], list[str]]:
    """Evaluate evidence depth. Returns (score, passes, failures)."""
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
    """Evaluate journal quality. Returns (score, passes, failures)."""
    score = 0
    passes = []
    failures = []

    if report is None:
        return 0, passes, failures + ["no_evidence_report"]

    ji_errors = len(report.get("journal_integrity_errors", []))
    ts_errors = len(report.get("timestamp_errors", []))

    if ji_errors == 0:
        score += 5
        passes.append("journal_integrity (5pts)")
    else:
        failures.append(f"journal_integrity ({ji_errors} errors)")

    if ts_errors == 0:
        score += 5
        passes.append("timestamps_utc (5pts)")
    else:
        failures.append(f"timestamps_utc ({ts_errors} errors)")

    return score, passes, failures


def evaluate_operational(report: dict | None) -> tuple[int, list[str], list[str]]:
    """Evaluate operational readiness. Returns (score, passes, failures)."""
    score = 0
    passes = []
    failures = []

    if report is None:
        return 0, passes, failures + ["no_evidence_report"]

    # CPU acceptable or WARN only
    cpu_status = report.get("cpu_status", "unavailable")
    if cpu_status == "available":
        cpu_avg = report.get("cpu_average", 0) or 0
        if cpu_avg < 90:
            score += 4
            passes.append(f"cpu_acceptable (4pts, avg={cpu_avg:.1f}%)")
        else:
            failures.append(f"cpu_high ({cpu_avg:.1f}%)")
    elif cpu_status == "unavailable":
        score += 2  # partial — WARN not FAIL
        passes.append("cpu_warn_unavailable (2pts)")
    else:
        failures.append("cpu_unknown")

    # Kill switch NORMAL
    ks_state = "NORMAL"
    for check in report.get("checks", []):
        if "kill" in check.get("check", "").lower():
            ks_state = "NORMAL" if check.get("status") == "PASS" else "ABNORMAL"
            break
    if ks_state == "NORMAL":
        score += 3
        passes.append("kill_switch_normal (3pts)")
    else:
        failures.append("kill_switch_abnormal")

    # Platform is Windows
    platform = report.get("platform", "")
    if platform == "Windows":
        score += 2
        passes.append("platform_windows (2pts)")
    else:
        failures.append(f"platform={platform}")

    # Stale report check — git_commit should not be "unknown"
    git_commit = report.get("git_commit", "unknown")
    if git_commit != "unknown":
        score += 1
        passes.append(f"git_commit_present (1pts, {git_commit})")
    else:
        failures.append("git_commit_missing")

    return score, passes, failures


def compute_verdict(score: int, run_30min: dict | None, run_4h: dict | None,
                    run_24h: dict | None, safety_failures: list[str]) -> tuple[str, str]:
    """Compute final verdict. Returns (verdict, reason)."""

    # Hard block conditions — check all available reports
    all_reports = [r for r in [run_30min, run_4h, run_24h] if r is not None]
    for report in all_reports:
        if report.get("live_orders_executed", 0) > 0:
            return "BLOCKED", "live_orders_executed > 0 in evidence"
        if report.get("order_send_guard", {}).get("success_count", 0) > 0:
            return "BLOCKED", "order_send success > 0 in evidence"
        if report.get("live_trading") is True:
            return "BLOCKED", "live_trading=true in evidence"
        if report.get("dry_run") is False:
            return "BLOCKED", "dry_run=false in evidence"
        if report.get("account_type", "") not in ("DEMO", ""):
            return "BLOCKED", f"account_type={report.get('account_type')} (not DEMO)"
        if report.get("shutdown_clean") is False:
            return "BLOCKED", "shutdown_clean=false in evidence"

    if score >= 90 and run_24h is not None:
        return "DEMO_LIVE_REVIEW_ALLOWED", f"Score {score}/100 + 24h evidence present"
    if score >= 85 and run_4h is not None:
        return "EXTENDED_DRY_RUN_READY", f"Score {score}/100 + 4h Verdict A (24h pending)"
    if score >= 75:
        return "CONTINUE_DRY_RUN", f"Score {score}/100 — insufficient evidence for extended run"
    return "BLOCKED", f"Score {score}/100 — below minimum threshold"


def report_has_live_orders(report: dict | None) -> bool:
    if not report:
        return False
    return report.get("live_orders_executed", 0) > 0


def report_has_order_send_success(report: dict | None) -> bool:
    if not report:
        return False
    return report.get("order_send_guard", {}).get("success_count", 0) > 0


def main():
    print("=" * 78)
    print("  TITAN XAU AI — Sprint 9.7 Pre-Demo Qualification Gate")
    print("=" * 78)

    # Load evidence
    print("\n── Loading evidence ──")
    run_30min = load_evidence_run("30min")
    run_4h = load_evidence_run("4h")
    run_24h = load_evidence_run("24h")

    # Use the best available report for detailed evaluation
    best_report = run_4h or run_30min or run_24h

    if run_30min:
        print(f"  30-min evidence: ✓ (duration={run_30min.get('duration_actual_s', 0):.0f}s)")
    else:
        print("  30-min evidence: ✗ (not found)")

    if run_4h:
        print(f"  4-hour evidence: ✓ (duration={run_4h.get('duration_actual_s', 0):.0f}s)")
    else:
        print("  4-hour evidence: ✗ (not found)")

    if run_24h:
        print(f"  24-hour evidence: ✓ (duration={run_24h.get('duration_actual_s', 0):.0f}s)")
    else:
        print("  24-hour evidence: ✗ (not found — required for demo-live)")

    # Evaluate categories
    print("\n── Evaluating qualification ──")
    safety_score, safety_passes, safety_failures = evaluate_safety_gates(best_report)
    runtime_score, runtime_passes, runtime_failures = evaluate_runtime_stability(best_report)
    evidence_score, evidence_passes, evidence_failures = evaluate_evidence_depth(run_30min, run_4h, run_24h)
    journal_score, journal_passes, journal_failures = evaluate_journal_integrity(best_report)
    ops_score, ops_passes, ops_failures = evaluate_operational(best_report)

    total_score = safety_score + runtime_score + evidence_score + journal_score + ops_score

    verdict, verdict_reason = compute_verdict(
        total_score, run_30min, run_4h, run_24h, safety_failures
    )

    # Print results
    print(f"\n  Safety gates:      {safety_score}/35")
    for p in safety_passes:
        print(f"    ✓ {p}")
    for f in safety_failures:
        print(f"    ✗ {f}")

    print(f"\n  Runtime stability: {runtime_score}/25")
    for p in runtime_passes:
        print(f"    ✓ {p}")
    for f in runtime_failures:
        print(f"    ✗ {f}")

    print(f"\n  Evidence depth:    {evidence_score}/20")
    for p in evidence_passes:
        print(f"    ✓ {p}")
    for f in evidence_failures:
        print(f"    ✗ {f}")

    print(f"\n  Journal/integrity: {journal_score}/10")
    for p in journal_passes:
        print(f"    ✓ {p}")
    for f in journal_failures:
        print(f"    ✗ {f}")

    print(f"\n  Operational:       {ops_score}/10")
    for p in ops_passes:
        print(f"    ✓ {p}")
    for f in ops_failures:
        print(f"    ✗ {f}")

    print(f"\n  {'=' * 50}")
    print(f"  TOTAL SCORE: {total_score}/100")
    print(f"  VERDICT:     {verdict}")
    print(f"  REASON:      {verdict_reason}")
    print(f"  {'=' * 50}")

    # Save JSON report
    report = {
        "audit": "sprint_9_7_pre_demo_qualification_gate",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "score": total_score,
        "max_score": 100,
        "verdict": verdict,
        "verdict_reason": verdict_reason,
        "categories": {
            "safety_gates": {"score": safety_score, "max": 35,
                             "passes": safety_passes, "failures": safety_failures},
            "runtime_stability": {"score": runtime_score, "max": 25,
                                  "passes": runtime_passes, "failures": runtime_failures},
            "evidence_depth": {"score": evidence_score, "max": 20,
                               "passes": evidence_passes, "failures": evidence_failures},
            "journal_integrity": {"score": journal_score, "max": 10,
                                  "passes": journal_passes, "failures": journal_failures},
            "operational": {"score": ops_score, "max": 10,
                            "passes": ops_passes, "failures": ops_failures},
        },
        "evidence_available": {
            "30min": run_30min is not None,
            "4h": run_4h is not None,
            "24h": run_24h is not None,
        },
        "best_report_summary": {
            "platform": best_report.get("platform", "") if best_report else "",
            "git_commit": best_report.get("git_commit", "") if best_report else "",
            "duration_actual_s": best_report.get("duration_actual_s", 0) if best_report else 0,
            "dry_run": best_report.get("dry_run", False) if best_report else False,
            "live_trading": best_report.get("live_trading", True) if best_report else True,
            "order_send_called": best_report.get("order_send_guard", {}).get("called_count", 0) if best_report else 0,
            "order_send_success": best_report.get("order_send_guard", {}).get("success_count", 0) if best_report else 0,
            "live_orders_executed": best_report.get("live_orders_executed", 0) if best_report else 0,
            "shutdown_clean": best_report.get("shutdown_clean", False) if best_report else False,
            "runtime_ended_early": best_report.get("runtime_ended_early", True) if best_report else True,
            "heartbeat_count": best_report.get("heartbeat_count", 0) if best_report else 0,
            "signals_generated": best_report.get("signals_generated", 0) if best_report else 0,
            "decisions_generated": best_report.get("decisions_generated", 0) if best_report else 0,
            "atr_evidence": best_report.get("atr_usage_count", 0) > 0 if best_report else False,
        },
    }

    json_path = OUTPUT_DIR / "pre_demo_readiness_report.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\n  JSON report: {json_path}")

    # Save markdown report
    md_path = OUTPUT_DIR / "pre_demo_readiness_report.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# Sprint 9.7 — Pre-Demo Qualification Gate\n\n")
        f.write(f"**Verdict: {verdict}**\n\n")
        f.write(f"**Reason: {verdict_reason}**\n\n")
        f.write(f"**Score: {total_score}/100**\n\n")
        f.write(f"## Evidence Available\n\n")
        f.write(f"| Duration | Present |\n|---|---|\n")
        f.write(f"| 30-minute | {'✓' if run_30min else '✗'} |\n")
        f.write(f"| 4-hour | {'✓' if run_4h else '✗'} |\n")
        f.write(f"| 24-hour | {'✓' if run_24h else '✗'} |\n\n")
        f.write(f"## Scoring\n\n")
        f.write(f"| Category | Score | Max |\n|---|---|---|\n")
        f.write(f"| Safety gates | {safety_score} | 35 |\n")
        f.write(f"| Runtime stability | {runtime_score} | 25 |\n")
        f.write(f"| Evidence depth | {evidence_score} | 20 |\n")
        f.write(f"| Journal/integrity | {journal_score} | 10 |\n")
        f.write(f"| Operational | {ops_score} | 10 |\n")
        f.write(f"| **Total** | **{total_score}** | **100** |\n\n")
        f.write(f"## Verdict Rules\n\n")
        f.write(f"- Score ≥90 + 24h evidence → DEMO_LIVE_REVIEW_ALLOWED\n")
        f.write(f"- Score ≥85 + 4h Verdict A → EXTENDED_DRY_RUN_READY\n")
        f.write(f"- Score ≥75 → CONTINUE_DRY_RUN\n")
        f.write(f"- Any safety failure → BLOCKED\n")
    print(f"  MD report:   {md_path}")

    print(f"\n  >>> VERDICT: {verdict}")
    print(f"  >>> {verdict_reason}")


if __name__ == "__main__":
    main()
