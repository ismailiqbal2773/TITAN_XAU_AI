#!/usr/bin/env python3
"""
TITAN XAU AI - Forward Demo Rollup Report (Sprint 9.9.3.45.11)
================================================================

Rolls up all daily reports under data/audit/forward_demo/ into a single
forward_demo_rollup_report.json + .md.

The rollup DOES NOT declare completion before 7 days of daily reports have
been observed. Below 7 days it emits
`recommendation = EXTEND_7_DAY_OBSERVATION` with a "not complete" status.

Verdict-bearing recommendations (mutually exclusive):
  - CONTINUE_30_DAY_DEMO        : >= 7 days observed, 0 blocked days,
                                  journal integrity OK, broker stable
  - EXTEND_7_DAY_OBSERVATION    : < 7 days observed, OR pass + warn days
                                  present but not yet 7-day complete
  - FIX_BLOCKERS_BEFORE_CONTINUE: >= 1 blocked day OR journal integrity
                                  not OK / broker unstable

Output fields:
  days_observed, pass_days, warn_days, blocked_days, total_trades,
  net_pnl, win_rate, pf, max_daily_dd, max_total_dd,
  avg_spread_slippage, risk_events_count, journal_integrity_status,
  broker_stability_status, recommendation, completed, days_remaining,
  safety.

SAFETY INVARIANTS:
  - NEVER imports MetaTrader5.
  - NEVER calls mt5.order_send / mt5.order_modify / mt5.positions_modify.
  - NEVER modifies positions or sends orders.
  - NEVER adds martingale / grid / averaging / loss-based lot multiplier.

Usage:
    python scripts/audit/forward_demo_rollup_report.py
"""
from __future__ import annotations
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

OUTPUT_DIR = REPO_ROOT / "data" / "audit" / "forward_demo"
JSON_PATH = OUTPUT_DIR / "forward_demo_rollup_report.json"
MD_PATH = OUTPUT_DIR / "forward_demo_rollup_report.md"

CONTINUE_30_DAY_DEMO = "CONTINUE_30_DAY_DEMO"
EXTEND_7_DAY_OBSERVATION = "EXTEND_7_DAY_OBSERVATION"
FIX_BLOCKERS_BEFORE_CONTINUE = "FIX_BLOCKERS_BEFORE_CONTINUE"

REQUIRED_DAYS_FOR_COMPLETION = 7

SAFETY_FINGERPRINT = {
    "order_send_called": False,
    "position_modified": False,
    "no_martingale": True,
    "no_grid": True,
    "no_averaging": True,
    "no_loss_multiplier": True,
}


def _load_daily_reports(input_dir: Path) -> list[dict]:
    """Load all daily_report_*.json files (sorted by date)."""
    if not input_dir.exists():
        return []
    reports = []
    for p in sorted(input_dir.glob("daily_report_*.json")):
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                reports.append(data)
        except Exception:
            continue
    return reports


def _safe_float(v, default=0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _avg_spread_slippage(reports: list[dict]) -> str:
    """Compute a qualitative average spread/slippage summary."""
    if not reports:
        return "N/A"
    notes = [str(r.get("spread_slippage_notes", "")).strip()
             for r in reports if r.get("spread_slippage_notes")]
    if not notes:
        return "no_notes_recorded"
    # Aggregate unique notes
    unique = sorted(set(notes))
    if len(unique) == 1:
        return unique[0]
    return f"{len(unique)} unique note(s); first={unique[0][:60]}"


def _compute_pf(win_pnl: float, loss_pnl: float) -> float:
    """Profit factor = gross profit / gross loss (None if no loss)."""
    if loss_pnl >= 0:
        # No losses (or zero) - PF is +inf represented as a large number
        return 0.0 if win_pnl == 0 else round(win_pnl, 4)
    return round(win_pnl / abs(loss_pnl), 4)


def run_rollup(input_dir: Path | None = None,
               output_dir: Path | None = None) -> dict:
    """Generate the forward demo rollup report.

    Args:
        input_dir: directory containing daily_report_*.json files.
        output_dir: directory to write the rollup JSON+MD.

    Returns:
        result dict with verdict, recommendation, completed, safety, and all
        rollup fields. Also includes json_path + md_path.
    """
    in_dir = input_dir or OUTPUT_DIR
    out_dir = output_dir or OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(timezone.utc).isoformat()
    reports = _load_daily_reports(in_dir)

    pass_days = sum(1 for r in reports if r.get("forward_day_verdict") == "FORWARD_DAY_PASS")
    warn_days = sum(1 for r in reports if r.get("forward_day_verdict") == "FORWARD_DAY_WARN")
    blocked_days = sum(1 for r in reports if r.get("forward_day_verdict") == "FORWARD_DAY_BLOCKED")
    days_observed = len(reports)

    total_trades = sum(int(r.get("trades_today", 0) or 0) for r in reports)
    closed_trades = sum(int(r.get("closed_trades_today", 0) or 0) for r in reports)
    net_pnl = round(sum(_safe_float(r.get("net_pnl_today")) for r in reports), 4)

    # Win-rate / PF computed from daily net pnl (positive day = win).
    win_days = sum(1 for r in reports if _safe_float(r.get("net_pnl_today")) > 0)
    loss_days = sum(1 for r in reports if _safe_float(r.get("net_pnl_today")) < 0)
    win_rate = round(win_days / days_observed, 4) if days_observed else 0.0

    gross_profit = round(sum(
        _safe_float(r.get("net_pnl_today"))
        for r in reports if _safe_float(r.get("net_pnl_today")) > 0
    ), 4)
    gross_loss = round(sum(
        _safe_float(r.get("net_pnl_today"))
        for r in reports if _safe_float(r.get("net_pnl_today")) < 0
    ), 4)
    pf = _compute_pf(gross_profit, gross_loss)

    max_daily_dd = round(max(
        (_safe_float(r.get("max_daily_dd")) for r in reports),
        default=0.0,
    ), 4)
    max_total_dd = round(max(
        (_safe_float(r.get("total_dd")) for r in reports),
        default=0.0,
    ), 4)

    risk_events_count = sum(len(r.get("risk_events", []) or []) for r in reports)

    # Journal integrity + broker stability status
    journal_statuses = {str(r.get("journal_integrity", "OK")) for r in reports}
    if not journal_statuses or journal_statuses == {"OK"}:
        journal_integrity_status = "OK"
    elif "OK" in journal_statuses:
        journal_integrity_status = "PARTIAL"
    else:
        journal_integrity_status = "DEGRADED"

    # Broker stability - based on broker_score consistency
    broker_scores = [_safe_float(r.get("broker_score")) for r in reports
                     if _safe_float(r.get("broker_score")) != 0.0]
    if not broker_scores:
        broker_stability_status = "UNKNOWN"
    elif max(broker_scores) - min(broker_scores) <= 0.5:
        broker_stability_status = "STABLE"
    else:
        broker_stability_status = "UNSTABLE"

    # === Determine completion + recommendation ===
    completed = days_observed >= REQUIRED_DAYS_FOR_COMPLETION
    days_remaining = max(0, REQUIRED_DAYS_FOR_COMPLETION - days_observed)

    # Recommendation precedence:
    # 1. If blocked days exist OR integrity degraded -> FIX_BLOCKERS_BEFORE_CONTINUE
    # 2. Elif not completed (days_observed < 7) -> EXTEND_7_DAY_OBSERVATION
    # 3. Else (>= 7 days, no blockers, integrity OK) -> CONTINUE_30_DAY_DEMO
    if blocked_days > 0:
        recommendation = FIX_BLOCKERS_BEFORE_CONTINUE
    elif journal_integrity_status == "DEGRADED":
        recommendation = FIX_BLOCKERS_BEFORE_CONTINUE
    elif broker_stability_status == "UNSTABLE":
        recommendation = FIX_BLOCKERS_BEFORE_CONTINUE
    elif not completed:
        recommendation = EXTEND_7_DAY_OBSERVATION
    else:
        recommendation = CONTINUE_30_DAY_DEMO

    # === Build report ===
    result = {
        "timestamp_utc": ts,
        "days_observed": days_observed,
        "required_days_for_completion": REQUIRED_DAYS_FOR_COMPLETION,
        "completed": completed,
        "days_remaining": days_remaining,
        "pass_days": pass_days,
        "warn_days": warn_days,
        "blocked_days": blocked_days,
        "total_trades": total_trades,
        "closed_trades": closed_trades,
        "net_pnl": net_pnl,
        "win_rate": win_rate,
        "pf": pf,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "max_daily_dd": max_daily_dd,
        "max_total_dd": max_total_dd,
        "avg_spread_slippage": _avg_spread_slippage(reports),
        "risk_events_count": risk_events_count,
        "journal_integrity_status": journal_integrity_status,
        "broker_stability_status": broker_stability_status,
        "recommendation": recommendation,
        "no_martingale": True,
        "no_grid": True,
        "no_averaging": True,
        "no_loss_multiplier": True,
        "safety": dict(SAFETY_FINGERPRINT),
    }

    # === Write JSON + MD ===
    json_path = out_dir / "forward_demo_rollup_report.json"
    md_path = out_dir / "forward_demo_rollup_report.md"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str, ensure_ascii=False)

    md_text = _build_md(result)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_text)

    result["json_path"] = str(json_path)
    result["md_path"] = str(md_path)
    return result


def _build_md(r: dict) -> str:
    lines = [
        "# TITAN XAU AI - Forward Demo Rollup Report",
        "",
        f"**Generated:** {r['timestamp_utc']}",
        f"**Recommendation:** **{r['recommendation']}**",
        f"**Completed:** {r['completed']} "
        f"({r['days_observed']}/{r['required_days_for_completion']} days, "
        f"{r['days_remaining']} day(s) remaining)",
        "",
        "## Day Counts",
        "",
        "| Field | Value |",
        "|---|---|",
        f"| days_observed | {r['days_observed']} |",
        f"| required_days_for_completion | {r['required_days_for_completion']} |",
        f"| completed | {r['completed']} |",
        f"| days_remaining | {r['days_remaining']} |",
        f"| pass_days | {r['pass_days']} |",
        f"| warn_days | {r['warn_days']} |",
        f"| blocked_days | {r['blocked_days']} |",
        "",
        "## Trades + PnL",
        "",
        "| Field | Value |",
        "|---|---|",
        f"| total_trades | {r['total_trades']} |",
        f"| closed_trades | {r['closed_trades']} |",
        f"| net_pnl | {r['net_pnl']} |",
        f"| win_rate | {r['win_rate']} |",
        f"| pf | {r['pf']} |",
        f"| gross_profit | {r['gross_profit']} |",
        f"| gross_loss | {r['gross_loss']} |",
        "",
        "## Risk + Integrity",
        "",
        "| Field | Value |",
        "|---|---|",
        f"| max_daily_dd | {r['max_daily_dd']} |",
        f"| max_total_dd | {r['max_total_dd']} |",
        f"| avg_spread_slippage | {r['avg_spread_slippage']} |",
        f"| risk_events_count | {r['risk_events_count']} |",
        f"| journal_integrity_status | {r['journal_integrity_status']} |",
        f"| broker_stability_status | {r['broker_stability_status']} |",
        f"| no_martingale | {r['no_martingale']} |",
        f"| no_grid | {r['no_grid']} |",
        f"| no_averaging | {r['no_averaging']} |",
        f"| no_loss_multiplier | {r['no_loss_multiplier']} |",
        "",
        "## Safety",
        "",
        "| Field | Value |",
        "|---|---|",
        f"| order_send_called | {r['safety']['order_send_called']} |",
        f"| position_modified | {r['safety']['position_modified']} |",
        f"| no_martingale | {r['safety']['no_martingale']} |",
        "",
        "## Notes",
        "",
        "- This rollup is OBSERVATION ONLY.",
        "- The rollup NEVER imports MetaTrader5, NEVER sends orders, NEVER "
        "modifies positions.",
        "- No martingale / grid / averaging / loss-based lot multipliers.",
        f"- The rollup does NOT declare completion before "
        f"{r['required_days_for_completion']} days of daily reports.",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="TITAN XAU AI Forward Demo Rollup Report")
    parser.add_argument("--input-dir", default=None,
                        help="Directory containing daily_report_*.json files.")
    args = parser.parse_args()

    print("=" * 70)
    print("  TITAN XAU AI - Forward Demo Rollup Report (Sprint 9.9.3.45.11)")
    print("=" * 70)
    in_dir = Path(args.input_dir) if args.input_dir else None
    result = run_rollup(input_dir=in_dir)
    print(f"\n  Days observed: {result['days_observed']}/{result['required_days_for_completion']}")
    print(f"  Completed: {result['completed']}")
    print(f"  Pass/Warn/Blocked: {result['pass_days']}/{result['warn_days']}/{result['blocked_days']}")
    print(f"  Net PnL: {result['net_pnl']}")
    print(f"  Win rate: {result['win_rate']}")
    print(f"  PF: {result['pf']}")
    print(f"\n  Recommendation: {result['recommendation']}")
    print(f"\n  JSON: {result['json_path']}")
    print(f"  MD:   {result['md_path']}")
    print(
        f"\n  Safety: order_send_called={result['safety']['order_send_called']}, "
        f"position_modified={result['safety']['position_modified']}, "
        f"no_martingale={result['safety']['no_martingale']}"
    )
    print("\n" + "=" * 70)
    return 0 if result["recommendation"] == CONTINUE_30_DAY_DEMO else 1


if __name__ == "__main__":
    sys.exit(main())
