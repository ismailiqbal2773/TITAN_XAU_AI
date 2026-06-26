"""
TITAN XAU AI — Sprint 9.8.1 Demo Micro Readiness Gate
=======================================================

Reads virtual lifecycle report and evaluates demo micro readiness.
"""
from __future__ import annotations
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

REPORT_PATH = REPO_ROOT / "data" / "audit" / "virtual_lifecycle" / "virtual_lifecycle_report.json"
OUTPUT_DIR = REPO_ROOT / "data" / "audit" / "demo_micro_readiness"


def evaluate(report: dict) -> tuple[str, str, dict]:
    """Returns (verdict, reason, details)."""
    checks = {}

    checks["virtual_lifecycle_ready"] = report.get("verdict") == "VIRTUAL_LIFECYCLE_READY"
    checks["order_send_not_used"] = report.get("order_send_used") is False
    checks["live_not_touched"] = report.get("live_execution_touched") is False

    combined = report.get("combined_metrics", {})
    normal = report.get("normal_metrics", {})

    checks["net_pnl_positive"] = combined.get("net_pnl_total", 0) > 0
    checks["pf_above_1_2"] = combined.get("profit_factor_net", 0) >= 1.2
    checks["wr_above_40"] = combined.get("win_rate_net", 0) >= 40
    checks["expectancy_positive"] = combined.get("expectancy_net", 0) > 0
    checks["cost_drag_under_35"] = combined.get("cost_drag_pct", 100) <= 35
    checks["normal_dd_under_5"] = normal.get("max_drawdown_pct_of_start_equity", 100) <= 5.0

    all_pass = all(checks.values())
    normal_dd_pass = checks["normal_dd_under_5"]

    if not all([checks["virtual_lifecycle_ready"], checks["order_send_not_used"],
                checks["live_not_touched"], checks["net_pnl_positive"],
                checks["pf_above_1_2"], checks["wr_above_40"],
                checks["expectancy_positive"], checks["cost_drag_under_35"]]):
        failed = [k for k, v in checks.items() if not v]
        return "DEMO_MICRO_BLOCKED", f"Failed: {', '.join(failed)}", checks
    elif not normal_dd_pass:
        return "NEEDS_RISK_REVIEW", f"Normal DD {normal.get('max_drawdown_pct_of_start_equity', 0):.2f}% > 5%", checks
    else:
        return "DEMO_MICRO_READY", "All checks passed", checks


def main():
    print("=" * 78)
    print("  TITAN XAU AI — Sprint 9.8.1 Demo Micro Readiness Gate")
    print("=" * 78)

    if not REPORT_PATH.exists():
        print("\n  ✗ Virtual lifecycle report not found — run validator first")
        print(f"    Expected: {REPORT_PATH}")
        return

    with open(REPORT_PATH, "r", encoding="utf-8") as f:
        report = json.load(f)

    verdict, reason, checks = evaluate(report)

    print(f"\n── Demo Micro Readiness Evaluation ──")
    for k, v in checks.items():
        print(f"  [{'✓' if v else '✗'}] {k}: {v}")
    print(f"\n  VERDICT: {verdict}")
    print(f"  REASON:  {reason}")

    # Save report
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = {
        "audit": "sprint_9_8_1_demo_micro_readiness_gate",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "verdict": verdict,
        "reason": reason,
        "checks": checks,
        "source_report": str(REPORT_PATH),
    }
    json_path = OUTPUT_DIR / "demo_micro_readiness_report.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, default=str)

    md_path = OUTPUT_DIR / "demo_micro_readiness_report.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# Sprint 9.8.1 — Demo Micro Readiness Gate\n\n")
        f.write(f"**Verdict: {verdict}**\n\n")
        f.write(f"**Reason: {reason}**\n\n")
        f.write(f"## Checks\n\n| Check | Passed |\n|---|---|\n")
        for k, v in checks.items():
            f.write(f"| {k} | {'✓' if v else '✗'} |\n")

    print(f"\n  JSON: {json_path}")
    print(f"  MD:   {md_path}")


if __name__ == "__main__":
    main()
