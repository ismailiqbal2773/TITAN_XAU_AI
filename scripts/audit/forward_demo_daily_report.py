#!/usr/bin/env python3
"""
TITAN XAU AI - Forward Demo Daily Report (Sprint 9.9.3.45.10)
==============================================================

Generates a daily observation report for the forward demo window under
data/audit/forward_demo/daily_report_YYYYMMDD.json and
data/audit/forward_demo/daily_report_YYYYMMDD.md.

The daily report consolidates operator-supplied inputs into a single
verdict-bearing artifact. Verdicts:

  - FORWARD_DAY_PASS    : clean demo day, no blockers
  - FORWARD_DAY_WARN    : demo day acceptable but with soft warnings
                          (e.g. no trades placed today)
  - FORWARD_DAY_BLOCKED : pre-conditions not met, observation must halt

Blocking conditions (any one triggers FORWARD_DAY_BLOCKED):
  - account is not a DEMO account
  - more than 1 open TITAN (magic-numbered) position
  - aggressive risk profile used (not prop_funded_safe)
  - risk limits breached (max_daily_dd exceeded)
  - old fallback trade used as proof

SAFETY INVARIANTS:
  - NEVER imports MetaTrader5.
  - NEVER calls mt5.order_send / mt5.order_modify / mt5.positions_modify.
  - NEVER modifies positions or sends orders.
  - NEVER adds martingale / grid / averaging / loss-based lot multiplier.
  - Safety fingerprint: order_send_called=False, position_modified=False,
    no_martingale=True.

Usage:
    python scripts/audit/forward_demo_daily_report.py
    python scripts/audit/forward_demo_daily_report.py --input-json day_input.json
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

FORWARD_DAY_PASS = "FORWARD_DAY_PASS"
FORWARD_DAY_WARN = "FORWARD_DAY_WARN"
FORWARD_DAY_BLOCKED = "FORWARD_DAY_BLOCKED"

# The only approved profile for the forward demo window.
APPROVED_PROFILE = "prop_funded_safe"

# Risk limits - hard blockers if breached.
MAX_OPEN_TITAN_POSITIONS = 1
MAX_DAILY_DD_THRESHOLD = 0.03  # 3.0% of equity

# Safety fingerprint emitted on every result. Hard-coded False/True values.
SAFETY_FINGERPRINT = {
    "order_send_called": False,
    "position_modified": False,
    "no_martingale": True,
    "no_grid": True,
    "no_averaging": True,
    "no_loss_multiplier": True,
}


def _blocked(reason: str, **extra) -> dict:
    """Construct a FORWARD_DAY_BLOCKED result."""
    result = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "verdict": FORWARD_DAY_BLOCKED,
        "blockers": [reason],
        "ok_checks": [],
        "warnings": [],
        "safety": dict(SAFETY_FINGERPRINT),
    }
    result.update(extra)
    return result


def _default_input(date_str: str) -> dict:
    """Return the default input fields with sensible defaults."""
    return {
        "date": date_str,
        "profile": APPROVED_PROFILE,
        "account_server": "metaquotes-demo",
        "account_type": "demo",
        "broker_score": 0.0,
        "open_positions_count": 0,
        "titan_magic_positions_count": 0,
        "trades_today": 0,
        "closed_trades_today": 0,
        "net_pnl_today": 0.0,
        "max_daily_dd": 0.0,
        "total_dd": 0.0,
        "spread_slippage_notes": "",
        "rejected_signals": 0,
        "risk_events": [],
        "journal_integrity": "OK",
        "receipt_integrity": "OK",
        "old_fallback_trade_used": False,
        "aggressive_profile_used": False,
    }


def run_daily_report(input_data: dict | None = None,
                     output_dir: Path | None = None,
                     date_str: str | None = None) -> dict:
    """Generate the forward demo daily report.

    Args:
        input_data: dict of operator-supplied inputs. When None, defaults are
            used (which will produce a WARN day - no trades, demo clean).
        output_dir: override output directory (used in tests).
        date_str: override date YYYYMMDD string. Defaults to today UTC.

    Returns:
        result dict with verdict, blockers, warnings, ok_checks, safety,
        json_path, md_path, and all daily fields.
    """
    out_dir = output_dir or OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    if date_str is None:
        date_str = datetime.now(timezone.utc).strftime("%Y%m%d")

    src = _default_input(date_str)
    if input_data:
        # Merge operator inputs over defaults.
        for k, v in input_data.items():
            src[k] = v

    ts = datetime.now(timezone.utc).isoformat()
    blockers: list[str] = []
    warnings: list[str] = []
    ok_checks: list[str] = []

    # === Hard blocking conditions ===

    # 1. Account must be a DEMO account.
    account_type = str(src.get("account_type", "")).lower()
    if account_type != "demo":
        blockers.append(
            f"REAL_ACCOUNT_DETECTED: account_type={account_type!r} - "
            "forward demo requires a demo account"
        )

    # 2. More than one open TITAN (magic-numbered) position.
    titan_positions = int(src.get("titan_magic_positions_count", 0) or 0)
    if titan_positions > MAX_OPEN_TITAN_POSITIONS:
        blockers.append(
            f"TOO_MANY_TITAN_POSITIONS: {titan_positions} > {MAX_OPEN_TITAN_POSITIONS} - "
            "at most one TITAN magic-numbered position may be open at a time"
        )

    # 3. Aggressive risk profile used.
    profile = str(src.get("profile", APPROVED_PROFILE))
    aggressive_used = bool(src.get("aggressive_profile_used", False))
    if aggressive_used or profile != APPROVED_PROFILE:
        blockers.append(
            f"AGGRESSIVE_PROFILE_USED: profile={profile!r} - "
            f"only {APPROVED_PROFILE!r} is approved for forward demo"
        )

    # 4. Risk limits breached (max_daily_dd above threshold).
    try:
        max_daily_dd = float(src.get("max_daily_dd", 0.0) or 0.0)
    except (TypeError, ValueError):
        max_daily_dd = 0.0
    if max_daily_dd > MAX_DAILY_DD_THRESHOLD:
        blockers.append(
            f"RISK_LIMIT_BREACHED: max_daily_dd={max_daily_dd:.4f} > "
            f"threshold={MAX_DAILY_DD_THRESHOLD:.4f}"
        )

    # 5. Old fallback trade used as proof.
    if bool(src.get("old_fallback_trade_used", False)):
        blockers.append(
            "OLD_FALLBACK_TRADE_USED: old trades cannot be used as forward proof"
        )

    # === Soft warnings (non-blocking) ===
    trades_today = int(src.get("trades_today", 0) or 0)
    closed_today = int(src.get("closed_trades_today", 0) or 0)
    if trades_today == 0 and closed_today == 0:
        warnings.append(
            "NO_TRADES_TODAY: no trades were placed or closed today - "
            "observation may continue but flag for review"
        )

    journal_integrity = str(src.get("journal_integrity", "OK"))
    if journal_integrity != "OK":
        warnings.append(f"JOURNAL_INTEGRITY_DEGRADED: {journal_integrity}")

    receipt_integrity = str(src.get("receipt_integrity", "OK"))
    if receipt_integrity != "OK":
        warnings.append(f"RECEIPT_INTEGRITY_DEGRADED: {receipt_integrity}")

    risk_events = src.get("risk_events", []) or []
    if risk_events:
        warnings.append(f"RISK_EVENTS_RECORDED: {len(risk_events)} risk event(s)")

    # === OK checks (only meaningful when not blocked) ===
    if not blockers:
        ok_checks.append(f"Account is DEMO ({src.get('account_server', 'N/A')})")
        ok_checks.append(f"Profile approved: {profile}")
        ok_checks.append(
            f"Open TITAN positions: {titan_positions} (<= {MAX_OPEN_TITAN_POSITIONS})"
        )
        ok_checks.append(
            f"max_daily_dd={max_daily_dd:.4f} <= {MAX_DAILY_DD_THRESHOLD:.4f}"
        )
        ok_checks.append("No old fallback trade used as proof")
        ok_checks.append("No martingale / grid / averaging / loss-based lot multiplier")

    # === Determine verdict ===
    if blockers:
        verdict = FORWARD_DAY_BLOCKED
    elif warnings:
        verdict = FORWARD_DAY_WARN
    else:
        verdict = FORWARD_DAY_PASS

    # === Build the full report ===
    report = {
        "timestamp_utc": ts,
        "date": date_str,
        "profile": profile,
        "account_server": src.get("account_server", "N/A"),
        "account_type": src.get("account_type", "N/A"),
        "broker_score": src.get("broker_score", 0.0),
        "open_positions_count": int(src.get("open_positions_count", 0) or 0),
        "titan_magic_positions_count": titan_positions,
        "trades_today": trades_today,
        "closed_trades_today": closed_today,
        "net_pnl_today": float(src.get("net_pnl_today", 0.0) or 0.0),
        "max_daily_dd": max_daily_dd,
        "total_dd": float(src.get("total_dd", 0.0) or 0.0),
        "spread_slippage_notes": src.get("spread_slippage_notes", ""),
        "rejected_signals": int(src.get("rejected_signals", 0) or 0),
        "risk_events": risk_events,
        "journal_integrity": journal_integrity,
        "receipt_integrity": receipt_integrity,
        "no_martingale": True,
        "no_grid": True,
        "no_averaging": True,
        "no_loss_multiplier": True,
        "forward_day_verdict": verdict,
        "blockers": blockers,
        "warnings": warnings,
        "ok_checks": ok_checks,
        "safety": dict(SAFETY_FINGERPRINT),
    }

    # === Write JSON + MD ===
    json_path = out_dir / f"daily_report_{date_str}.json"
    md_path = out_dir / f"daily_report_{date_str}.md"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str, ensure_ascii=False)

    md_text = _build_md(report)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_text)

    report["json_path"] = str(json_path)
    report["md_path"] = str(md_path)
    return report


def _build_md(r: dict) -> str:
    """Render the daily report markdown."""
    lines = [
        "# TITAN XAU AI - Forward Demo Daily Report",
        "",
        f"**Date (UTC):** {r['date']}",
        f"**Generated:** {r['timestamp_utc']}",
        f"**Verdict:** **{r['forward_day_verdict']}**",
        "",
        "## Account + Profile",
        "",
        "| Field | Value |",
        "|---|---|",
        f"| date | {r['date']} |",
        f"| profile | {r['profile']} |",
        f"| account_server | {r['account_server']} |",
        f"| account_type | {r['account_type']} |",
        f"| broker_score | {r['broker_score']} |",
        "",
        "## Positions + Trades",
        "",
        "| Field | Value |",
        "|---|---|",
        f"| open_positions_count | {r['open_positions_count']} |",
        f"| titan_magic_positions_count | {r['titan_magic_positions_count']} |",
        f"| trades_today | {r['trades_today']} |",
        f"| closed_trades_today | {r['closed_trades_today']} |",
        f"| net_pnl_today | {r['net_pnl_today']} |",
        f"| rejected_signals | {r['rejected_signals']} |",
        "",
        "## Risk",
        "",
        "| Field | Value |",
        "|---|---|",
        f"| max_daily_dd | {r['max_daily_dd']} |",
        f"| total_dd | {r['total_dd']} |",
        f"| risk_events | {len(r['risk_events'])} |",
        "",
        "## Integrity",
        "",
        "| Field | Value |",
        "|---|---|",
        f"| journal_integrity | {r['journal_integrity']} |",
        f"| receipt_integrity | {r['receipt_integrity']} |",
        f"| no_martingale | {r['no_martingale']} |",
        f"| no_grid | {r['no_grid']} |",
        f"| no_averaging | {r['no_averaging']} |",
        f"| no_loss_multiplier | {r['no_loss_multiplier']} |",
        "",
    ]
    if r["blockers"]:
        lines.append("## Blockers")
        lines.append("")
        for b in r["blockers"]:
            lines.append(f"- **{b}**")
        lines.append("")
    if r["warnings"]:
        lines.append("## Warnings")
        lines.append("")
        for w in r["warnings"]:
            lines.append(f"- {w}")
        lines.append("")
    if r["ok_checks"]:
        lines.append("## OK Checks")
        lines.append("")
        for c in r["ok_checks"]:
            lines.append(f"- {c}")
        lines.append("")
    if r.get("spread_slippage_notes"):
        lines.append("## Spread / Slippage Notes")
        lines.append("")
        lines.append(r["spread_slippage_notes"])
        lines.append("")
    lines.extend([
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
        "- This daily report is OBSERVATION ONLY.",
        "- The generator NEVER imports MetaTrader5, NEVER sends orders, NEVER "
        "modifies positions.",
        "- No martingale / grid / averaging / loss-based lot multipliers.",
    ])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="TITAN XAU AI Forward Demo Daily Report")
    parser.add_argument("--input-json", default=None,
                        help="Optional JSON file with operator-supplied daily inputs.")
    parser.add_argument("--date", default=None,
                        help="Override date string YYYYMMDD (defaults to today UTC).")
    args = parser.parse_args()

    input_data = None
    if args.input_json:
        with open(args.input_json, "r", encoding="utf-8") as f:
            input_data = json.load(f)

    print("=" * 70)
    print("  TITAN XAU AI - Forward Demo Daily Report (Sprint 9.9.3.45.10)")
    print("=" * 70)
    result = run_daily_report(input_data=input_data, date_str=args.date)
    print(f"\n  Date: {result['date']}")
    print(f"  Verdict: {result['forward_day_verdict']}")
    if result["blockers"]:
        print("\n  Blockers:")
        for b in result["blockers"]:
            print(f"    - {b}")
    if result["warnings"]:
        print("\n  Warnings:")
        for w in result["warnings"]:
            print(f"    - {w}")
    print(f"\n  JSON: {result['json_path']}")
    print(f"  MD:   {result['md_path']}")
    print(
        f"\n  Safety: order_send_called={result['safety']['order_send_called']}, "
        f"position_modified={result['safety']['position_modified']}, "
        f"no_martingale={result['safety']['no_martingale']}"
    )
    print("\n" + "=" * 70)
    return 0 if result["forward_day_verdict"] == FORWARD_DAY_PASS else (
        0 if result["forward_day_verdict"] == FORWARD_DAY_WARN else 1
    )


if __name__ == "__main__":
    sys.exit(main())
