#!/usr/bin/env python3
"""
TITAN XAU AI - Trailing Manager Verification Audit (Sprint 9.9.3.45.8.16 v2.7.3)
=========================================================================
Investigates why forensics ``root_cause`` reports
``TRAILING_MANAGER_NOT_RUNNING`` and classifies whether that label is
warranted by the available evidence.

Sprint 9.9.3.45.8.13 fix: Trigger flags are now computed from actual
profit_R, NOT from managed report's breakeven_triggered/trailing_triggered
flags. The managed report flags may be set incorrectly or refer to a
different evaluation context. The audit must use the actual profit_R
to determine whether a trigger SHOULD have fired.

Sprint 9.9.3.45.8.16 v2.7.3: Planned-RR receipt fallback.
  When forensics cannot provide profit_R (history incomplete), the audit
  must compute basic planned_RR geometry from the receipt's
  entry/SL/TP/side fields. The actual profit_R remains unknown, but the
  planned_RR allows the audit to reason about whether trailing/dynamic TP
  would have had a chance to trigger at the planned TP.

  New fields added:
    - planned_RR
    - actual_RR_from_receipt
    - entry_price  (already existed, now also sourced from receipt)
    - sl_price     (sourced from receipt's requested_sl)
    - tp_price     (sourced from receipt's requested_tp)
    - receipt_geometry_valid
    - profit_R_source ("forensics" | "receipt_planned" | "unknown")
    - mfe_available
    - close_price_available

  New verdict:
    TRAILING_MANAGER_WARN_INSUFFICIENT_PATH_EVIDENCE
      - profit_R not computable (no exit price, no MFE), but the position
        is closed. Trailing may or may not have triggered - we cannot tell
        because there is no tick path / MFE evidence.
      - NOT a hard BLOCK unless trigger reached and manager failed.

Verdicts
--------
  - TRAILING_MANAGER_OK_NO_TRIGGER: position closed before any trailing
    threshold was reached (profit_R < breakeven_trigger_R), so no SL
    modification expected.
  - TRAILING_MANAGER_OK_TRIGGERED: trailing/breakeven was triggered and
    SL modification occurred.
  - TRAILING_MANAGER_WARN_INSUFFICIENT_EVIDENCE: legacy verdict - cannot
    determine whether trailing should have triggered (kept for back-compat
    with existing tests).
  - TRAILING_MANAGER_WARN_INSUFFICIENT_PATH_EVIDENCE: v2.7.3 - profit_R
    not computable but position is closed; tick path / MFE evidence is
    missing. NOT a hard block.
  - TRAILING_MANAGER_BLOCKED_NOT_RUNNING: profit_R >= breakeven_trigger_R
    AND monitor_iterations >= min AND hold_seconds >= min AND
    sl_modification_events = 0.

IMPORTANT: This audit NEVER blocks merely because sl_modification_events == 0.
It blocks ONLY when profit_R reached a trigger threshold AND monitor had
enough iterations/time AND no SL modification happened.

NEVER calls mt5.order_send. NEVER modifies positions.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

OUTPUT_DIR = REPO_ROOT / "data" / "audit" / "demo_micro_execution"
RECEIPT_PATH = REPO_ROOT / "data" / "runtime" / "demo_micro_execution_receipt.json"
FORENSICS_PATH = OUTPUT_DIR / "post_trade_forensics.json"
MANAGED_TRADE_REPORT_PATH = OUTPUT_DIR / "managed_trade_report.json"

# Verdict constants
TRAILING_MANAGER_OK_NO_TRIGGER = "TRAILING_MANAGER_OK_NO_TRIGGER"
TRAILING_MANAGER_OK_TRIGGERED = "TRAILING_MANAGER_OK_TRIGGERED"
TRAILING_MANAGER_WARN_INSUFFICIENT_EVIDENCE = "TRAILING_MANAGER_WARN_INSUFFICIENT_EVIDENCE"
TRAILING_MANAGER_WARN_INSUFFICIENT_PATH_EVIDENCE = "TRAILING_MANAGER_WARN_INSUFFICIENT_PATH_EVIDENCE"
TRAILING_MANAGER_BLOCKED_NOT_RUNNING = "TRAILING_MANAGER_BLOCKED_NOT_RUNNING"

ALL_VERDICTS = (
    TRAILING_MANAGER_OK_NO_TRIGGER,
    TRAILING_MANAGER_OK_TRIGGERED,
    TRAILING_MANAGER_WARN_INSUFFICIENT_EVIDENCE,
    TRAILING_MANAGER_WARN_INSUFFICIENT_PATH_EVIDENCE,
    TRAILING_MANAGER_BLOCKED_NOT_RUNNING,
)


def _load_json(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (ValueError, TypeError):
        return default


def _to_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (ValueError, TypeError):
        return default


def _to_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes", "y")
    return default


def _compute_profit_R(entry_price: float, exit_price: float,
                       entry_sl: float, side: str) -> Optional[float]:
    if entry_price <= 0 or exit_price <= 0 or entry_sl <= 0:
        return None
    risk = abs(entry_price - entry_sl)
    if risk <= 0:
        return None
    side_upper = (side or "").strip().upper()
    if side_upper == "BUY":
        return (exit_price - entry_price) / risk
    if side_upper == "SELL":
        return (entry_price - exit_price) / risk
    return (exit_price - entry_price) / risk


def run_audit(
    receipt_path: Optional[Path] = None,
    forensics_path: Optional[Path] = None,
    managed_report_path: Optional[Path] = None,
) -> dict:
    ts = datetime.now(timezone.utc).isoformat()
    ok_checks: list[str] = []
    blockers: list[str] = []
    warnings: list[str] = []
    findings: dict[str, Any] = {}

    receipt_path = receipt_path or RECEIPT_PATH
    forensics_path = forensics_path or FORENSICS_PATH
    managed_report_path = managed_report_path or MANAGED_TRADE_REPORT_PATH

    receipt = _load_json(receipt_path)
    forensics = _load_json(forensics_path)
    managed_report = _load_json(managed_report_path)

    findings["receipt_path"] = str(receipt_path)
    findings["forensics_path"] = str(forensics_path)
    findings["managed_trade_report_path"] = str(managed_report_path)
    findings["receipt_available"] = receipt is not None
    findings["forensics_available"] = forensics is not None
    findings["managed_trade_report_available"] = managed_report is not None

    # === Forensics root_cause ===
    forensics_findings: dict = {}
    forensics_root_cause = ""
    if forensics is not None:
        forensics_findings = forensics.get("findings", {}) or {}
        forensics_root_cause = forensics_findings.get("root_cause", "") or ""
    findings["forensics_root_cause"] = forensics_root_cause
    findings["forensics_root_cause_is_trailing_not_running"] = (
        forensics_root_cause == "TRAILING_MANAGER_NOT_RUNNING"
    )

    # === Managed trade report fields ===
    if managed_report is not None:
        monitor_iterations = _to_int(managed_report.get("monitor_iterations"))
        monitor_duration_seconds = _to_float(managed_report.get("monitor_duration_seconds"))
        # Sprint 9.9.3.45.8.13: Read managed report trigger flags but do NOT
        # use them as primary evidence. Use profit_R instead.
        managed_breakeven_triggered = _to_bool(managed_report.get("breakeven_triggered"))
        managed_trailing_triggered = _to_bool(managed_report.get("trailing_triggered"))
        managed_profit_lock_triggered = _to_bool(managed_report.get("profit_lock_triggered"))
        monitor_stop_reason = managed_report.get("monitor_stop_reason", "") or ""
        final_position_status = managed_report.get("final_position_status", "") or ""
        adaptive_cfg = managed_report.get("adaptive_trailing_config", {}) or {}
    else:
        monitor_iterations = 0
        monitor_duration_seconds = 0.0
        managed_breakeven_triggered = False
        managed_trailing_triggered = False
        managed_profit_lock_triggered = False
        monitor_stop_reason = ""
        final_position_status = ""
        adaptive_cfg = {}

    # === Adaptive trailing thresholds (with sane defaults) ===
    breakeven_trigger_R = _to_float(adaptive_cfg.get("breakeven_trigger_R"), 1.0)
    trailing_trigger_R = _to_float(adaptive_cfg.get("trailing_trigger_R"), 1.75)
    profit_lock_trigger_R = _to_float(adaptive_cfg.get("profit_lock_trigger_R"), 3.0)
    dynamic_tp_trigger_R = _to_float(adaptive_cfg.get("tp_extension_trigger_R"), 2.0)
    min_hold_seconds = _to_int(adaptive_cfg.get("min_hold_seconds"), 60)
    min_monitor_iterations = _to_int(adaptive_cfg.get("min_monitor_iterations"), 3)

    # === Forensics-derived evidence ===
    sl_modification_events = _to_int(forensics_findings.get("sl_modification_events"))
    sl_hit_detected = _to_bool(forensics_findings.get("sl_hit_detected"))
    realized_pl = _to_float(forensics_findings.get("realized_pl"))
    entry_sl = _to_float(forensics_findings.get("entry_sl"))
    entry_tp = _to_float(forensics_findings.get("entry_tp"))
    entry_deal = forensics_findings.get("entry_deal") or {}
    exit_deal = forensics_findings.get("exit_deal") or {}
    mfe_raw = forensics_findings.get("mfe")

    # === Receipt-derived side and geometry (v2.7.3) ===
    side = ""
    receipt_entry_price = 0.0
    receipt_sl_price = 0.0
    receipt_tp_price = 0.0
    if receipt is not None:
        side = receipt.get("side", "") or ""
        receipt_entry_price = _to_float(
            receipt.get("order_send_result_price")
            or receipt.get("detected_position_entry_price")
        )
        receipt_sl_price = _to_float(
            receipt.get("requested_sl")
            if receipt.get("requested_sl") is not None
            else receipt.get("request_sl")
        )
        receipt_tp_price = _to_float(
            receipt.get("requested_tp")
            if receipt.get("requested_tp") is not None
            else receipt.get("request_tp")
        )
    findings["side"] = side
    findings["receipt_entry_price"] = receipt_entry_price
    findings["receipt_sl_price"] = receipt_sl_price
    findings["receipt_tp_price"] = receipt_tp_price

    # === Compute profit_R from entry/exit prices ===
    # Prefer forensics entry_deal price; fall back to receipt entry price.
    forensics_entry_price = _to_float(entry_deal.get("price")) if entry_deal else 0.0
    entry_price = forensics_entry_price or receipt_entry_price
    exit_price = _to_float(exit_deal.get("price")) if exit_deal else 0.0
    # Prefer forensics entry_sl/tp; fall back to receipt sl/tp.
    sl_price = entry_sl if entry_sl > 0 else receipt_sl_price
    tp_price = entry_tp if entry_tp > 0 else receipt_tp_price
    profit_R = _compute_profit_R(entry_price, exit_price, sl_price, side)

    # === v2.7.3: Planned RR from receipt geometry ===
    # If we have entry/SL/TP from the receipt, compute the planned RR.
    # This does NOT tell us the actual profit_R (which requires the close
    # price), but it tells us whether the trade was PLANNED with enough
    # room for trailing/dynamic TP to ever trigger.
    planned_RR: Optional[float] = None
    receipt_geometry_valid = False
    if entry_price > 0 and sl_price > 0 and tp_price > 0:
        side_upper = (side or "").strip().upper()
        if side_upper == "BUY":
            risk_dist = entry_price - sl_price
            reward_dist = tp_price - entry_price
        elif side_upper == "SELL":
            risk_dist = sl_price - entry_price
            reward_dist = entry_price - tp_price
        else:
            risk_dist = 0.0
            reward_dist = 0.0
        if risk_dist > 0:
            planned_RR = round(reward_dist / risk_dist, 6)
            receipt_geometry_valid = reward_dist > 0
    findings["planned_RR"] = planned_RR
    findings["actual_RR_from_receipt"] = planned_RR  # alias for clarity
    findings["receipt_geometry_valid"] = receipt_geometry_valid

    # === MFE-based profit_R when MFE is provided ===
    mfe_profit_R: Optional[float] = None
    if mfe_raw is not None:
        try:
            mfe_val = _to_float(mfe_raw)
            if mfe_val < 100:  # treat as R-multiple
                mfe_profit_R = mfe_val
            elif sl_price > 0 and entry_price > 0:
                risk = abs(entry_price - sl_price)
                if risk > 0:
                    mfe_profit_R = mfe_val / risk
        except (ValueError, TypeError):
            pass

    # === Hold seconds ===
    hold_seconds = monitor_duration_seconds

    # === Sprint 9.9.3.45.8.13: Compute trigger flags from ACTUAL profit_R ===
    # NOT from managed report flags. Managed report flags may be incorrect.
    best_profit_R: Optional[float] = None
    profit_evidence_values = [v for v in (profit_R, mfe_profit_R) if v is not None]
    if profit_evidence_values:
        best_profit_R = max(profit_evidence_values)
        profit_R_source = "forensics"
    elif planned_RR is not None:
        # v2.7.3: No actual profit_R, but we have planned_RR.
        # We CANNOT use planned_RR as a trigger proxy - it just tells us
        # the trade was planned with room for trailing to trigger. The
        # actual price path is unknown.
        profit_R_source = "receipt_planned"
    else:
        profit_R_source = "unknown"

    # Compute trigger flags from actual profit_R
    if best_profit_R is not None:
        breakeven_triggered = best_profit_R >= breakeven_trigger_R
        trailing_triggered = best_profit_R >= trailing_trigger_R
        dynamic_tp_triggered = best_profit_R >= dynamic_tp_trigger_R
        profit_lock_triggered = best_profit_R >= profit_lock_trigger_R
    else:
        # Cannot compute profit_R - fall back to managed report flags as secondary
        breakeven_triggered = managed_breakeven_triggered
        trailing_triggered = managed_trailing_triggered
        dynamic_tp_triggered = False
        profit_lock_triggered = managed_profit_lock_triggered

    # SL modification expected only if a trigger was reached based on actual profit_R
    sl_modification_expected = bool(
        breakeven_triggered or trailing_triggered or profit_lock_triggered
    )
    sl_modification_occurred = sl_modification_events > 0

    # Monitor conditions
    monitor_iterations_sufficient = monitor_iterations >= min_monitor_iterations
    hold_seconds_sufficient = hold_seconds >= min_hold_seconds

    # === Populate findings ===
    findings["monitor_iterations"] = monitor_iterations
    findings["monitor_duration_seconds"] = monitor_duration_seconds
    findings["hold_seconds"] = hold_seconds
    findings["breakeven_trigger_R"] = breakeven_trigger_R
    findings["trailing_trigger_R"] = trailing_trigger_R
    findings["dynamic_tp_trigger_R"] = dynamic_tp_trigger_R
    findings["profit_lock_trigger_R"] = profit_lock_trigger_R
    findings["min_monitor_iterations"] = min_monitor_iterations
    findings["min_hold_seconds"] = min_hold_seconds
    findings["managed_breakeven_triggered"] = managed_breakeven_triggered
    findings["managed_trailing_triggered"] = managed_trailing_triggered
    findings["managed_profit_lock_triggered"] = managed_profit_lock_triggered
    findings["breakeven_triggered"] = breakeven_triggered
    findings["trailing_triggered"] = trailing_triggered
    findings["dynamic_tp_triggered"] = dynamic_tp_triggered
    findings["profit_lock_triggered"] = profit_lock_triggered
    findings["sl_modification_expected"] = sl_modification_expected
    findings["sl_modification_events"] = sl_modification_events
    findings["sl_modification_occurred"] = sl_modification_occurred
    findings["entry_price"] = entry_price
    findings["exit_price"] = exit_price
    findings["entry_sl"] = entry_sl
    findings["entry_tp"] = entry_tp
    findings["sl_price"] = sl_price
    findings["tp_price"] = tp_price
    findings["profit_R"] = profit_R
    findings["profit_R_computable"] = profit_R is not None
    findings["profit_R_source"] = profit_R_source
    findings["mfe_profit_R"] = mfe_profit_R
    findings["best_profit_R"] = best_profit_R
    findings["monitor_iterations_sufficient"] = monitor_iterations_sufficient
    findings["hold_seconds_sufficient"] = hold_seconds_sufficient
    findings["sl_hit_detected"] = sl_hit_detected
    findings["realized_pl"] = realized_pl
    findings["monitor_stop_reason"] = monitor_stop_reason
    findings["final_position_status"] = final_position_status
    # v2.7.3: receipt geometry + path-evidence flags
    findings["mfe_available"] = mfe_raw is not None
    findings["close_price_available"] = exit_price > 0

    # === VERDICT LOGIC (Sprint 9.9.3.45.8.13: profit_R-first) ===
    verdict: str = TRAILING_MANAGER_WARN_INSUFFICIENT_EVIDENCE
    manager_expected_reason = ""
    manager_not_expected_reason = ""
    final_verdict_reason = ""

    if best_profit_R is not None:
        # profit_R is computable - use it as primary evidence
        if sl_modification_expected and sl_modification_occurred:
            # Trigger reached and SL was modified
            verdict = TRAILING_MANAGER_OK_TRIGGERED
            manager_expected_reason = (
                f"profit_R={best_profit_R:.4f} >= breakeven_trigger_R={breakeven_trigger_R}"
            )
            final_verdict_reason = (
                f"Trigger reached (profit_R={best_profit_R:.4f}) and SL modification occurred "
                f"(sl_modification_events={sl_modification_events})"
            )
            ok_checks.append(final_verdict_reason)

        elif sl_modification_expected and not sl_modification_occurred:
            # Trigger reached but SL not modified
            manager_expected_reason = (
                f"profit_R={best_profit_R:.4f} >= breakeven_trigger_R={breakeven_trigger_R}"
            )
            if monitor_iterations_sufficient and hold_seconds_sufficient:
                # All conditions met for SL modification but it didn't happen
                verdict = TRAILING_MANAGER_BLOCKED_NOT_RUNNING
                final_verdict_reason = (
                    f"BLOCKED: profit_R={best_profit_R:.4f} >= breakeven_trigger_R={breakeven_trigger_R} "
                    f"AND monitor_iterations={monitor_iterations} >= {min_monitor_iterations} "
                    f"AND hold_seconds={hold_seconds} >= {min_hold_seconds} "
                    f"but sl_modification_events=0"
                )
                blockers.append(final_verdict_reason)
            else:
                # Trigger reached but monitor/hold conditions not met
                verdict = TRAILING_MANAGER_WARN_INSUFFICIENT_EVIDENCE
                final_verdict_reason = (
                    f"WARN: profit_R={best_profit_R:.4f} reached threshold but "
                    f"monitor/hold conditions not met "
                    f"(monitor_iterations={monitor_iterations}, hold_seconds={hold_seconds})"
                )
                warnings.append(final_verdict_reason)

        elif not sl_modification_expected:
            # No trigger reached - SL modification NOT expected
            verdict = TRAILING_MANAGER_OK_NO_TRIGGER
            manager_not_expected_reason = (
                f"profit_R={best_profit_R:.4f} < breakeven_trigger_R={breakeven_trigger_R} "
                f"(also < trailing_trigger_R={trailing_trigger_R}, "
                f"< dynamic_tp_trigger_R={dynamic_tp_trigger_R}, "
                f"< profit_lock_trigger_R={profit_lock_trigger_R})"
            )
            final_verdict_reason = (
                f"OK_NO_TRIGGER: profit_R={best_profit_R:.4f} did not reach any threshold "
                f"(breakeven={breakeven_trigger_R}, trailing={trailing_trigger_R}, "
                f"dynamic_tp={dynamic_tp_trigger_R}, profit_lock={profit_lock_trigger_R}). "
                f"No SL modification expected."
            )
            ok_checks.append(final_verdict_reason)
            ok_checks.append(
                f"sl_modification_events={sl_modification_events} is acceptable "
                f"because no trigger was reached"
            )

    else:
        # profit_R not computable - use managed report flags as fallback
        trigger_fired_from_managed = bool(
            managed_breakeven_triggered or managed_trailing_triggered or managed_profit_lock_triggered
        )
        if trigger_fired_from_managed and sl_modification_occurred:
            verdict = TRAILING_MANAGER_OK_TRIGGERED
            final_verdict_reason = (
                "Managed report trigger flags fired and SL modification occurred "
                f"(sl_modification_events={sl_modification_events})"
            )
            ok_checks.append(final_verdict_reason)
        elif trigger_fired_from_managed and not sl_modification_occurred:
            if monitor_iterations_sufficient and hold_seconds_sufficient:
                verdict = TRAILING_MANAGER_BLOCKED_NOT_RUNNING
                final_verdict_reason = (
                    "BLOCKED: managed report trigger flags fired but sl_modification_events=0 "
                    f"(monitor_iterations={monitor_iterations}, hold_seconds={hold_seconds})"
                )
                blockers.append(final_verdict_reason)
            else:
                verdict = TRAILING_MANAGER_WARN_INSUFFICIENT_EVIDENCE
                final_verdict_reason = (
                    "WARN: managed report trigger flags fired but monitor/hold not met"
                )
                warnings.append(final_verdict_reason)
        elif final_position_status == "CLOSED" and not sl_hit_detected:
            # v2.7.3: Position closed without SL hit, profit_R not computable.
            # If we have planned_RR from receipt, we can reason that trailing
            # COULD have triggered at the planned TP - but without tick path /
            # MFE evidence, we cannot say whether it SHOULD have. Use the new
            # WARN_INSUFFICIENT_PATH_EVIDENCE verdict (NOT a hard block).
            verdict = TRAILING_MANAGER_WARN_INSUFFICIENT_PATH_EVIDENCE
            final_verdict_reason = (
                "WARN_INSUFFICIENT_PATH_EVIDENCE: position closed without SL hit, "
                "profit_R not computable, no MFE/tick path evidence. "
                f"planned_RR={planned_RR}, receipt_geometry_valid={receipt_geometry_valid}. "
                "Trailing may or may not have triggered - cannot determine from "
                "available evidence. NOT a hard block."
            )
            warnings.append(final_verdict_reason)
        else:
            # v2.7.3: Use new path-evidence verdict when no managed report
            # trigger fired and no exit price is available.
            if planned_RR is not None and not exit_price:
                verdict = TRAILING_MANAGER_WARN_INSUFFICIENT_PATH_EVIDENCE
                final_verdict_reason = (
                    "WARN_INSUFFICIENT_PATH_EVIDENCE: profit_R not computable (no exit price, "
                    "no MFE). Receipt provides planned_RR="
                    f"{planned_RR} (geometry_valid={receipt_geometry_valid}), but tick "
                    "path / MFE evidence is missing. Trailing trigger cannot be determined. "
                    "NOT a hard block."
                )
                warnings.append(final_verdict_reason)
            else:
                verdict = TRAILING_MANAGER_WARN_INSUFFICIENT_EVIDENCE
                final_verdict_reason = (
                    "WARN: cannot determine if trailing should have triggered "
                    "(profit_R not computable)"
                )
                warnings.append(final_verdict_reason)

    findings["manager_expected_reason"] = manager_expected_reason
    findings["manager_not_expected_reason"] = manager_not_expected_reason
    findings["final_verdict_reason"] = final_verdict_reason

    # Monitor loop status
    monitor_loop_called = monitor_iterations > 0
    findings["monitor_loop_called"] = monitor_loop_called
    if monitor_loop_called:
        ok_checks.append(f"Monitor loop was called (monitor_iterations={monitor_iterations})")
    else:
        warnings.append("Monitor loop was not called (monitor_iterations=0)")

    return {
        "timestamp_utc": ts,
        "verdict": verdict,
        "ok_checks": ok_checks,
        "blockers": blockers,
        "warnings": warnings,
        "findings": findings,
        "safety": {
            "order_send_called": False,
            "position_modified": False,
            "no_martingale": True,
            "no_grid": True,
            "no_averaging": True,
        },
    }


def write_report(result: dict) -> dict:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUTPUT_DIR / "trailing_manager_verification.json"
    md_path = OUTPUT_DIR / "trailing_manager_verification.md"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str, ensure_ascii=False)

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# TITAN XAU AI - Trailing Manager Verification Audit\n\n")
        f.write(f"**Verdict:** **{result['verdict']}**\n\n")
        f.write(f"**Timestamp:** {result['timestamp_utc']}\n\n")
        f.write("## Findings\n\n")
        f.write("| Check | Value |\n|---|---|\n")
        fnd = result.get("findings", {})
        for k in (
            "profit_R", "best_profit_R", "breakeven_trigger_R", "trailing_trigger_R",
            "dynamic_tp_trigger_R", "profit_lock_trigger_R",
            "breakeven_triggered", "trailing_triggered", "dynamic_tp_triggered",
            "profit_lock_triggered", "sl_modification_expected", "sl_modification_events",
            "sl_modification_occurred", "monitor_iterations", "hold_seconds",
            "monitor_iterations_sufficient", "hold_seconds_sufficient",
            "manager_expected_reason", "manager_not_expected_reason", "final_verdict_reason",
            # v2.7.3: planned RR + receipt geometry fields
            "planned_RR", "actual_RR_from_receipt",
            "entry_price", "sl_price", "tp_price",
            "receipt_geometry_valid", "profit_R_source",
            "mfe_available", "close_price_available",
        ):
            if k in fnd:
                f.write(f"| {k} | {fnd[k]} |\n")
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
        f.write("\n## Safety\n\n")
        f.write("- order_send_called: False\n")
        f.write("- position_modified: False\n")
        f.write("- no_martingale: True\n")
        f.write("- no_grid: True\n")
        f.write("- no_averaging: True\n")

    return {"json_path": str(json_path), "md_path": str(md_path)}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Trailing manager verification audit (no MT5, no order_send)"
    )
    parser.add_argument("--receipt-path", type=Path, default=None)
    parser.add_argument("--forensics-path", type=Path, default=None)
    parser.add_argument("--managed-report-path", type=Path, default=None)
    args = parser.parse_args()

    print("=" * 70)
    print("  TITAN XAU AI - Trailing Manager Verification Audit (v2.7.3)")
    print("=" * 70)
    result = run_audit(
        receipt_path=args.receipt_path,
        forensics_path=args.forensics_path,
        managed_report_path=args.managed_report_path,
    )
    report = write_report(result)
    print(f"\n  Verdict: {result['verdict']}")
    print(f"  OK checks: {len(result.get('ok_checks', []))}")
    print(f"  Warnings:  {len(result.get('warnings', []))}")
    print(f"  Blockers:  {len(result.get('blockers', []))}")
    fnd = result.get("findings", {})
    print(f"\n  profit_R: {fnd.get('profit_R', 'N/A')}")
    print(f"  best_profit_R: {fnd.get('best_profit_R', 'N/A')}")
    print(f"  planned_RR: {fnd.get('planned_RR', 'N/A')}")
    print(f"  profit_R_source: {fnd.get('profit_R_source', 'unknown')}")
    print(f"  receipt_geometry_valid: {fnd.get('receipt_geometry_valid', False)}")
    print(f"  mfe_available: {fnd.get('mfe_available', False)}")
    print(f"  close_price_available: {fnd.get('close_price_available', False)}")
    print(f"  breakeven_trigger_R: {fnd.get('breakeven_trigger_R', 'N/A')}")
    print(f"  sl_modification_events: {fnd.get('sl_modification_events', 0)}")
    print(f"  sl_modification_expected: {fnd.get('sl_modification_expected', False)}")
    print(f"  final_verdict_reason: {fnd.get('final_verdict_reason', 'N/A')}")
    if result.get("blockers"):
        print("\n  Blockers:")
        for b in result["blockers"]:
            print(f"    - {b}")
    print(f"\n  JSON: {report['json_path']}")
    print(f"  MD:   {report['md_path']}")
    print("\n" + "=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
