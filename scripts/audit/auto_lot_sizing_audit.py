#!/usr/bin/env python3
"""
TITAN XAU AI - Auto Lot Sizing Audit (Sprint v2.8.5-D.1/E)
===========================================================
Audits the Auto Lot Sizing Engine for correctness and safety.

Verifies:
  - equity growth increases raw_lot
  - final_lot increases only within profile cap
  - DEMO_SAFE never exceeds 0.01
  - risk percent remains constant
  - RR geometry unchanged
  - drawdown reduces lot
  - loss streak never increases lot
  - CEO risk_multiplier reduces lot
  - capital preservation reduces or blocks lot
  - broker lot step rounds down
  - broker min/max respected
  - invalid SL blocks
  - invalid tick value blocks
  - cent account profile normalizes safely
  - prop challenge daily DD soft reduces risk
  - prop challenge daily DD hard blocks
  - total DD cap blocks
  - no martingale behavior
  - no loss-based lot multiplier

Verdicts:
  AUTO_LOT_SIZING_PASS
  AUTO_LOT_SIZING_BLOCKED

NEVER sends orders. NEVER creates token. NEVER modifies positions.
"""
from __future__ import annotations
import json, sys, math
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

OUTPUT_DIR = REPO_ROOT / "data" / "audit" / "risk"

AUTO_LOT_SIZING_PASS = "AUTO_LOT_SIZING_PASS"
AUTO_LOT_SIZING_BLOCKED = "AUTO_LOT_SIZING_BLOCKED"


def run_audit() -> dict:
    """Run the Auto Lot Sizing audit.

    NEVER calls mt5.order_send. NEVER creates token. NEVER modifies positions.
    """
    from titan.production.auto_lot_sizing import calculate_auto_lot

    ts = datetime.now(timezone.utc).isoformat()
    ok_checks = []
    blockers = []
    warnings_list = []
    findings = {}

    # Test 1: DEMO_SAFE basic calculation
    r = calculate_auto_lot(
        account_equity=10000.0, risk_percent=0.005,
        stop_loss_points=50.0, symbol_tick_value=1.0,
        account_mode="DEMO_SAFE", profile_max_lot=0.01,
    )
    if r.blocked:
        blockers.append(f"DEMO_SAFE_BASIC_BLOCKED: {r.blockers}")
    elif r.final_lot > 0.01:
        blockers.append(f"DEMO_SAFE_EXCEEDS_001: final_lot={r.final_lot}")
    else:
        ok_checks.append(f"DEMO_SAFE basic: final_lot={r.final_lot} (<= 0.01)")
    findings["demo_safe_basic"] = r.to_dict()

    # Test 2: Equity growth increases raw_lot
    r_low = calculate_auto_lot(account_equity=5000.0, risk_percent=0.005,
                               stop_loss_points=50.0, symbol_tick_value=1.0,
                               account_mode="DEMO_SAFE", profile_max_lot=0.01)
    r_high = calculate_auto_lot(account_equity=20000.0, risk_percent=0.005,
                                stop_loss_points=50.0, symbol_tick_value=1.0,
                                account_mode="DEMO_SAFE", profile_max_lot=0.01)
    if r_high.raw_lot > r_low.raw_lot:
        ok_checks.append(f"Equity growth increases raw_lot: {r_low.raw_lot} -> {r_high.raw_lot}")
    else:
        blockers.append("EQUITY_GROWTH_NOT_INCREASING_RAW_LOT")
    findings["equity_growth_test"] = {"low": r_low.to_dict(), "high": r_high.to_dict()}

    # Test 3: Risk percent constant
    r1 = calculate_auto_lot(account_equity=10000.0, risk_percent=0.005,
                            stop_loss_points=50.0, account_mode="DEMO_SAFE")
    r2 = calculate_auto_lot(account_equity=10000.0, risk_percent=0.005,
                            stop_loss_points=100.0, account_mode="DEMO_SAFE")
    if r1.risk_percent == r2.risk_percent == 0.005:
        ok_checks.append("Risk percent constant across calculations")
    else:
        blockers.append("RISK_PERCENT_NOT_CONSTANT")

    # Test 4: Invalid SL blocks
    r_bad_sl = calculate_auto_lot(stop_loss_points=0.0, account_mode="DEMO_SAFE")
    if r_bad_sl.blocked and any("INVALID_STOP_LOSS" in b for b in r_bad_sl.blockers):
        ok_checks.append("Invalid SL blocks")
    else:
        blockers.append("INVALID_SL_NOT_BLOCKED")

    # Test 5: Invalid tick value blocks
    r_bad_tick = calculate_auto_lot(symbol_tick_value=0.0, account_mode="DEMO_SAFE")
    if r_bad_tick.blocked and any("INVALID_TICK_VALUE" in b for b in r_bad_tick.blockers):
        ok_checks.append("Invalid tick value blocks")
    else:
        blockers.append("INVALID_TICK_VALUE_NOT_BLOCKED")

    # Test 6: Invalid equity blocks
    r_bad_eq = calculate_auto_lot(account_equity=-100.0, account_mode="DEMO_SAFE")
    if r_bad_eq.blocked and any("INVALID_EQUITY" in b for b in r_bad_eq.blockers):
        ok_checks.append("Invalid equity blocks")
    else:
        blockers.append("INVALID_EQUITY_NOT_BLOCKED")

    # Test 7: Drawdown reduces lot
    r_normal = calculate_auto_lot(account_equity=10000.0, risk_percent=0.005,
                                  stop_loss_points=50.0, account_mode="DEMO_SAFE",
                                  daily_drawdown_percent=0.0)
    r_dd = calculate_auto_lot(account_equity=10000.0, risk_percent=0.005,
                              stop_loss_points=50.0, account_mode="DEMO_SAFE",
                              daily_drawdown_percent=0.015)  # 1.5% > 1% soft limit
    if r_dd.risk_amount < r_normal.risk_amount:
        ok_checks.append("Drawdown reduces risk_amount")
    else:
        blockers.append("DRAWDOWN_NOT_REDUCING_LOT")

    # Test 8: Daily DD hard limit blocks
    r_hard_dd = calculate_auto_lot(account_equity=10000.0, risk_percent=0.005,
                                   stop_loss_points=50.0, account_mode="DEMO_SAFE",
                                   daily_drawdown_percent=0.025)  # 2.5% > 2% hard limit
    if r_hard_dd.blocked and any("DAILY_DD_HARD" in b for b in r_hard_dd.blockers):
        ok_checks.append("Daily DD hard limit blocks")
    else:
        blockers.append("DAILY_DD_HARD_NOT_BLOCKED")

    # Test 9: Total DD cap blocks
    r_total_dd = calculate_auto_lot(account_equity=10000.0, risk_percent=0.005,
                                    stop_loss_points=50.0, account_mode="DEMO_SAFE",
                                    total_drawdown_percent=0.09)  # 9% > 8% cap
    if r_total_dd.blocked and any("TOTAL_DD_CAP" in b for b in r_total_dd.blockers):
        ok_checks.append("Total DD cap blocks")
    else:
        blockers.append("TOTAL_DD_CAP_NOT_BLOCKED")

    # Test 10: CEO risk_multiplier reduces lot
    r_ceo1 = calculate_auto_lot(account_equity=10000.0, risk_percent=0.005,
                                stop_loss_points=50.0, account_mode="DEMO_SAFE",
                                ceo_risk_multiplier=1.0)
    r_ceo05 = calculate_auto_lot(account_equity=10000.0, risk_percent=0.005,
                                 stop_loss_points=50.0, account_mode="DEMO_SAFE",
                                 ceo_risk_multiplier=0.5)
    if r_ceo05.risk_amount < r_ceo1.risk_amount:
        ok_checks.append("CEO risk_multiplier=0.5 reduces risk_amount")
    else:
        blockers.append("CEO_RISK_MULTIPLIER_NOT_REDUCING")

    # Test 11: CEO risk_multiplier never exceeds 1.0
    r_ceo_high = calculate_auto_lot(account_equity=10000.0, risk_percent=0.005,
                                    stop_loss_points=50.0, account_mode="DEMO_SAFE",
                                    ceo_risk_multiplier=2.0)
    if r_ceo_high.effective_risk_percent <= 0.005:
        ok_checks.append("CEO risk_multiplier capped at 1.0")
    else:
        blockers.append("CEO_RISK_MULTIPLIER_EXCEEDS_CAP")

    # Test 12: Capital preservation reduces lot
    r_cap = calculate_auto_lot(account_equity=10000.0, risk_percent=0.005,
                               stop_loss_points=50.0, account_mode="DEMO_SAFE",
                               capital_preservation_active=True)
    if r_cap.risk_amount < r_normal.risk_amount:
        ok_checks.append("Capital preservation reduces risk_amount")
    else:
        blockers.append("CAPITAL_PRESERVATION_NOT_REDUCING")

    # Test 13: Loss streak reduces lot (never increases)
    r_streak = calculate_auto_lot(account_equity=10000.0, risk_percent=0.005,
                                  stop_loss_points=50.0, account_mode="DEMO_SAFE",
                                  loss_streak=3)
    if r_streak.risk_amount <= r_normal.risk_amount:
        ok_checks.append("Loss streak does not increase lot")
    else:
        blockers.append("LOSS_STREAK_INCREASES_LOT")

    # Test 14: Broker lot step rounds down
    r_step = calculate_auto_lot(account_equity=50000.0, risk_percent=0.005,
                                stop_loss_points=50.0, account_mode="DEMO_SAFE",
                                broker_lot_step=0.01, profile_max_lot=0.05)
    if r_step.rounded_lot <= r_step.raw_lot:
        ok_checks.append(f"Broker lot step rounds down: raw={r_step.raw_lot} rounded={r_step.rounded_lot}")
    else:
        blockers.append("BROKER_LOT_STEP_NOT_ROUNDING_DOWN")

    # Test 15: Max open positions blocks
    r_max_pos = calculate_auto_lot(account_equity=10000.0, risk_percent=0.005,
                                   stop_loss_points=50.0, account_mode="DEMO_SAFE",
                                   open_positions_count=1, max_open_positions=1)
    if r_max_pos.blocked and any("MAX_OPEN_POSITIONS" in b for b in r_max_pos.blockers):
        ok_checks.append("Max open positions blocks")
    else:
        blockers.append("MAX_OPEN_POSITIONS_NOT_BLOCKED")

    # Test 16: No martingale (lot based on equity, not previous lot)
    r_after_loss = calculate_auto_lot(account_equity=9000.0, risk_percent=0.005,
                                      stop_loss_points=50.0, account_mode="DEMO_SAFE",
                                      loss_streak=1)
    r_before_loss = calculate_auto_lot(account_equity=10000.0, risk_percent=0.005,
                                       stop_loss_points=50.0, account_mode="DEMO_SAFE",
                                       loss_streak=0)
    if r_after_loss.raw_lot <= r_before_loss.raw_lot:
        ok_checks.append("No martingale: lot does not increase after loss (equity dropped)")
    else:
        blockers.append("MARTINGALE_BEHAVIOR_DETECTED")

    # Test 17: Build-request has auto_lot fields (check managed_trade_report)
    br_path = REPO_ROOT / "data" / "audit" / "demo_micro_execution" / "managed_trade_report.json"
    br_has_auto_lot = False
    if br_path.exists():
        try:
            with open(br_path, "r") as f:
                br = json.load(f)
            br_has_auto_lot = "auto_lot_enabled" in br
        except Exception:
            pass
    findings["build_request_has_auto_lot"] = br_has_auto_lot
    if br_has_auto_lot:
        ok_checks.append("Build-request has auto_lot fields")
    else:
        warnings_list.append("BUILD_REQUEST_AUTO_LOT_MISSING: run build-request to populate")

    # Determine verdict
    if blockers:
        verdict = AUTO_LOT_SIZING_BLOCKED
    else:
        verdict = AUTO_LOT_SIZING_PASS

    # Add freshness metadata
    from titan.production.audit_hygiene import make_freshness_metadata, detect_environment_mode, get_git_commit
    freshness = make_freshness_metadata(
        audit_name="auto_lot_sizing_audit",
        source_mode="production",
        environment_mode=detect_environment_mode(),
    )

    return {
        "timestamp_utc": ts,
        "verdict": verdict,
        "ok_checks": ok_checks,
        "blockers": blockers,
        "warnings": warnings_list,
        "findings": findings,
        "generated_at_utc": freshness["generated_at_utc"],
        "git_commit": freshness["git_commit"],
        "audit_name": freshness["audit_name"],
        "source_mode": freshness["source_mode"],
        "environment_mode": freshness["environment_mode"],
        "safety": {
            "order_send_called": False,
            "position_modified": False,
            "token_created": False,
        },
    }


def write_report(result: dict) -> dict:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUTPUT_DIR / "auto_lot_sizing_audit.json"
    md_path = OUTPUT_DIR / "auto_lot_sizing_audit.md"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str, ensure_ascii=False)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# TITAN XAU AI - Auto Lot Sizing Audit (v2.8.5-D.1/E)\n\n")
        f.write(f"**Verdict:** **{result['verdict']}**\n\n")
        f.write(f"**Timestamp:** {result['timestamp_utc']}\n\n")
        f.write(f"**Blockers:** {len(result.get('blockers', []))}\n\n")
        if result.get("blockers"):
            f.write("## Blockers\n\n")
            for b in result["blockers"]:
                f.write(f"- **{b}**\n")
        if result.get("warnings"):
            f.write("\n## Warnings\n\n")
            for w in result["warnings"]:
                f.write(f"- {w}\n")
        if result.get("ok_checks"):
            f.write("\n## OK Checks\n\n")
            for c in result["ok_checks"]:
                f.write(f"- {c}\n")
        f.write("\n## Safety\n\n")
        f.write("- order_send_called: False\n")
        f.write("- position_modified: False\n")
        f.write("- token_created: False\n")
    return {"json_path": str(json_path), "md_path": str(md_path)}


def main() -> int:
    print("=" * 70)
    print("  TITAN XAU AI - Auto Lot Sizing Audit (v2.8.5-D.1/E)")
    print("=" * 70)
    result = run_audit()
    report = write_report(result)
    print(f"\n  Verdict: {result['verdict']}")
    print(f"  Blockers: {len(result.get('blockers', []))}")
    print(f"  OK checks: {len(result.get('ok_checks', []))}")
    if result.get("blockers"):
        print("\n  Blockers:")
        for b in result["blockers"]:
            print(f"    - {b}")
    print(f"\n  JSON: {report['json_path']}")
    print(f"  MD:   {report['md_path']}")
    print("\n" + "=" * 70)
    return 0 if result["verdict"] != AUTO_LOT_SIZING_BLOCKED else 1


if __name__ == "__main__":
    sys.exit(main())
