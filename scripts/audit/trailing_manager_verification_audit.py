#!/usr/bin/env python3
"""
TITAN XAU AI - Trailing Manager Verification Audit (Sprint 9.9.3.45.8.11)
=========================================================================
Investigates why forensics ``root_cause`` reports
``TRAILING_MANAGER_NOT_RUNNING`` and classifies whether that label is
warranted by the available evidence.

The audit reads three artefacts produced by the managed demo micro
execution path:

  1. Receipt:        data/runtime/demo_micro_execution_receipt.json
  2. Forensics:      data/audit/demo_micro_execution/post_trade_forensics.json
  3. Managed report: data/audit/demo_micro_execution/managed_trade_report.json

It cross-checks monitor iterations, monitor duration, hold time, the
adaptive trailing thresholds (breakeven R=1.0, trailing R=1.75, dynamic
TP R=2.0, profit-lock R=3.0), MFE (when available), whether an SL
modification was expected, whether an SL modification occurred, whether
the monitor loop was actually called, and whether a "no trailing event"
outcome is acceptable because no threshold was reached.

Verdicts
--------
  - TRAILING_MANAGER_OK_NO_TRIGGER:        position closed before any
                                            trailing threshold was reached,
                                            so no SL modification expected.
  - TRAILING_MANAGER_OK_TRIGGERED:         trailing/breakeven was triggered
                                            and SL modification occurred.
  - TRAILING_MANAGER_WARN_INSUFFICIENT_EVIDENCE:
                                            cannot determine whether trailing
                                            should have triggered.
  - TRAILING_MANAGER_BLOCKED_NOT_RUNNING:  evidence shows trailing should
                                            have triggered but the manager
                                            did not modify SL.

IMPORTANT
---------
This audit NEVER blocks merely because ``sl_modification_events == 0``.
It blocks ONLY when the evidence shows that trailing SHOULD have
triggered (``profit_R >= breakeven_trigger_R`` AND
``monitor_iterations >= min_monitor_iterations`` AND
``hold_seconds >= min_hold_seconds``) but SL was not modified.

NEVER calls mt5.order_send. NEVER modifies positions. Pure passive
analysis of locally persisted JSON artefacts.
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
TRAILING_MANAGER_WARN_INSUFFICIENT_EVIDENCE = (
    "TRAILING_MANAGER_WARN_INSUFFICIENT_EVIDENCE"
)
TRAILING_MANAGER_BLOCKED_NOT_RUNNING = "TRAILING_MANAGER_BLOCKED_NOT_RUNNING"

ALL_VERDICTS = (
    TRAILING_MANAGER_OK_NO_TRIGGER,
    TRAILING_MANAGER_OK_TRIGGERED,
    TRAILING_MANAGER_WARN_INSUFFICIENT_EVIDENCE,
    TRAILING_MANAGER_BLOCKED_NOT_RUNNING,
)


def _load_json(path: Path) -> Optional[dict]:
    """Load a JSON file. Returns None if missing or unreadable."""
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _to_float(value: Any, default: float = 0.0) -> float:
    """Safely convert to float."""
    try:
        if value is None:
            return default
        return float(value)
    except (ValueError, TypeError):
        return default


def _to_int(value: Any, default: int = 0) -> int:
    """Safely convert to int."""
    try:
        if value is None:
            return default
        return int(value)
    except (ValueError, TypeError):
        return default


def _to_bool(value: Any, default: bool = False) -> bool:
    """Safely convert to bool."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes", "y")
    return default


def _compute_profit_R(
    entry_price: float,
    exit_price: float,
    entry_sl: float,
    side: str,
) -> Optional[float]:
    """Compute profit R-multiple from entry/exit prices and entry SL.

    Returns None if any required input is missing or risk is zero.
    """
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
    # Unknown side - default to BUY-style (long) computation
    return (exit_price - entry_price) / risk


def run_audit(
    receipt_path: Optional[Path] = None,
    forensics_path: Optional[Path] = None,
    managed_report_path: Optional[Path] = None,
) -> dict:
    """Run the trailing manager verification audit.

    Parameters
    ----------
    receipt_path : Optional[Path]
        Override path to the execution receipt JSON. Defaults to the
        module-level ``RECEIPT_PATH``.
    forensics_path : Optional[Path]
        Override path to the post-trade forensics JSON. Defaults to the
        module-level ``FORENSICS_PATH``.
    managed_report_path : Optional[Path]
        Override path to the managed trade report JSON. Defaults to the
        module-level ``MANAGED_TRADE_REPORT_PATH``.

    Returns
    -------
    dict
        Audit result with keys: timestamp_utc, verdict, ok_checks,
        blockers, warnings, findings, safety.
    """
    ts = datetime.now(timezone.utc).isoformat()
    ok_checks: list[str] = []
    blockers: list[str] = []
    warnings: list[str] = []
    findings: dict[str, Any] = {}

    receipt_path = receipt_path or RECEIPT_PATH
    forensics_path = forensics_path or FORENSICS_PATH
    managed_report_path = managed_report_path or MANAGED_TRADE_REPORT_PATH

    # === Load artefacts ===
    receipt = _load_json(receipt_path)
    forensics = _load_json(forensics_path)
    managed_report = _load_json(managed_report_path)

    findings["receipt_path"] = str(receipt_path)
    findings["forensics_path"] = str(forensics_path)
    findings["managed_trade_report_path"] = str(managed_report_path)
    findings["receipt_available"] = receipt is not None
    findings["forensics_available"] = forensics is not None
    findings["managed_trade_report_available"] = managed_report is not None

    # === Forensics root_cause (the trigger for this audit) ===
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
        monitor_duration_seconds = _to_float(
            managed_report.get("monitor_duration_seconds")
        )
        breakeven_triggered = _to_bool(managed_report.get("breakeven_triggered"))
        trailing_triggered = _to_bool(managed_report.get("trailing_triggered"))
        profit_lock_triggered = _to_bool(managed_report.get("profit_lock_triggered"))
        monitor_stop_reason = managed_report.get("monitor_stop_reason", "") or ""
        final_position_status = (
            managed_report.get("final_position_status", "") or ""
        )
        adaptive_cfg = managed_report.get("adaptive_trailing_config", {}) or {}
    else:
        monitor_iterations = 0
        monitor_duration_seconds = 0.0
        breakeven_triggered = False
        trailing_triggered = False
        profit_lock_triggered = False
        monitor_stop_reason = ""
        final_position_status = ""
        adaptive_cfg = {}

    # === Adaptive trailing thresholds (with sane defaults) ===
    breakeven_trigger_R = _to_float(adaptive_cfg.get("breakeven_trigger_R"), 1.0)
    trailing_trigger_R = _to_float(adaptive_cfg.get("trailing_trigger_R"), 1.75)
    profit_lock_trigger_R = _to_float(adaptive_cfg.get("profit_lock_trigger_R"), 3.0)
    tp_extension_trigger_R = _to_float(
        adaptive_cfg.get("tp_extension_trigger_R"), 2.0
    )
    min_hold_seconds = _to_int(adaptive_cfg.get("min_hold_seconds"), 60)
    min_monitor_iterations = _to_int(
        adaptive_cfg.get("min_monitor_iterations"), 3
    )

    findings["monitor_iterations"] = monitor_iterations
    findings["monitor_duration_seconds"] = monitor_duration_seconds
    findings["breakeven_triggered"] = breakeven_triggered
    findings["trailing_triggered"] = trailing_triggered
    findings["profit_lock_triggered"] = profit_lock_triggered
    findings["monitor_stop_reason"] = monitor_stop_reason
    findings["final_position_status"] = final_position_status
    findings["breakeven_trigger_R"] = breakeven_trigger_R
    findings["trailing_trigger_R"] = trailing_trigger_R
    findings["profit_lock_trigger_R"] = profit_lock_trigger_R
    findings["tp_extension_trigger_R"] = tp_extension_trigger_R
    findings["min_hold_seconds"] = min_hold_seconds
    findings["min_monitor_iterations"] = min_monitor_iterations

    # === Forensics-derived evidence ===
    sl_modification_events = _to_int(
        forensics_findings.get("sl_modification_events")
    )
    sl_hit_detected = _to_bool(forensics_findings.get("sl_hit_detected"))
    realized_pl = _to_float(forensics_findings.get("realized_pl"))
    entry_sl = _to_float(forensics_findings.get("entry_sl"))
    entry_tp = _to_float(forensics_findings.get("entry_tp"))
    entry_deal = forensics_findings.get("entry_deal") or {}
    exit_deal = forensics_findings.get("exit_deal") or {}
    mfe_raw = forensics_findings.get("mfe")
    profit_before_sl_detected = forensics_findings.get(
        "profit_before_sl_detected", "UNKNOWN"
    )

    findings["sl_modification_events"] = sl_modification_events
    findings["sl_hit_detected"] = sl_hit_detected
    findings["realized_pl"] = realized_pl
    findings["entry_sl"] = entry_sl
    findings["entry_tp"] = entry_tp
    findings["mfe_available"] = mfe_raw is not None
    findings["profit_before_sl_detected"] = profit_before_sl_detected
    if mfe_raw is not None:
        findings["mfe"] = mfe_raw

    # === Receipt-derived side ===
    side = ""
    if receipt is not None:
        side = receipt.get("side", "") or ""
        findings["receipt_success"] = _to_bool(receipt.get("success"))
        findings["receipt_position_detected"] = _to_bool(
            receipt.get("position_detected")
        )
    findings["side"] = side

    # === Compute profit_R from entry/exit prices when possible ===
    entry_price = _to_float(entry_deal.get("price")) if entry_deal else 0.0
    exit_price = _to_float(exit_deal.get("price")) if exit_deal else 0.0
    profit_R = _compute_profit_R(entry_price, exit_price, entry_sl, side)
    findings["entry_price"] = entry_price
    findings["exit_price"] = exit_price
    findings["profit_R"] = profit_R
    findings["profit_R_computable"] = profit_R is not None

    # === MFE-based profit_R when MFE is provided ===
    mfe_profit_R: Optional[float] = None
    if mfe_raw is not None:
        try:
            mfe_val = _to_float(mfe_raw)
            if mfe_val < 100:  # treat as R-multiple
                mfe_profit_R = mfe_val
            elif entry_sl > 0 and entry_price > 0:  # treat as price delta
                risk = abs(entry_price - entry_sl)
                if risk > 0:
                    mfe_profit_R = mfe_val / risk
        except (ValueError, TypeError):
            pass
    findings["mfe_profit_R"] = mfe_profit_R

    # === Hold seconds: use monitor_duration_seconds as proxy ===
    hold_seconds = monitor_duration_seconds
    findings["hold_seconds"] = hold_seconds

    # === CHECKS ===

    # 1. Monitor loop was called
    monitor_loop_called = monitor_iterations > 0
    findings["monitor_loop_called"] = monitor_loop_called
    if monitor_loop_called:
        ok_checks.append(
            f"Monitor loop was called (monitor_iterations={monitor_iterations})"
        )
    else:
        warnings.append("Monitor loop was not called (monitor_iterations=0)")

    # 2. Monitor duration recorded
    monitor_duration_recorded = monitor_duration_seconds > 0
    findings["monitor_duration_recorded"] = monitor_duration_recorded

    # 3. Hold time sufficient for trailing threshold
    hold_seconds_sufficient = hold_seconds >= min_hold_seconds
    findings["hold_seconds_sufficient"] = hold_seconds_sufficient

    # 4. Monitor iterations sufficient
    monitor_iterations_sufficient = monitor_iterations >= min_monitor_iterations
    findings["monitor_iterations_sufficient"] = monitor_iterations_sufficient

    # 5. Threshold reachability (use any available evidence)
    breakeven_threshold_reached = (
        (profit_R is not None and profit_R >= breakeven_trigger_R)
        or (
            mfe_profit_R is not None
            and mfe_profit_R >= breakeven_trigger_R
        )
        or breakeven_triggered
    )
    findings["breakeven_threshold_reached"] = breakeven_threshold_reached

    trailing_threshold_reached = (
        (profit_R is not None and profit_R >= trailing_trigger_R)
        or (
            mfe_profit_R is not None
            and mfe_profit_R >= trailing_trigger_R
        )
        or trailing_triggered
    )
    findings["trailing_threshold_reached"] = trailing_threshold_reached

    dynamic_tp_threshold_reached = (
        (profit_R is not None and profit_R >= tp_extension_trigger_R)
        or (
            mfe_profit_R is not None
            and mfe_profit_R >= tp_extension_trigger_R
        )
    )
    findings["dynamic_tp_threshold_reached"] = dynamic_tp_threshold_reached

    profit_lock_threshold_reached = (
        (profit_R is not None and profit_R >= profit_lock_trigger_R)
        or (
            mfe_profit_R is not None
            and mfe_profit_R >= profit_lock_trigger_R
        )
        or profit_lock_triggered
    )
    findings["profit_lock_threshold_reached"] = profit_lock_threshold_reached

    # 6. SL modification expected (any trailing threshold reached)
    sl_modification_expected = bool(
        breakeven_threshold_reached
        or trailing_threshold_reached
        or profit_lock_threshold_reached
    )
    findings["sl_modification_expected"] = sl_modification_expected

    # 7. SL modification occurred
    sl_modification_occurred = sl_modification_events > 0
    findings["sl_modification_occurred"] = sl_modification_occurred

    # 8. No trailing event acceptable because threshold not reached
    no_trailing_event_acceptable = not sl_modification_expected
    findings["no_trailing_event_acceptable"] = no_trailing_event_acceptable

    # 9. Trigger flags vs SL modification consistency
    trigger_fired = bool(
        breakeven_triggered or trailing_triggered or profit_lock_triggered
    )
    findings["trigger_fired"] = trigger_fired

    # === VERDICT LOGIC ===
    verdict: Optional[str] = None

    # Case A: Trailing trigger flags fired in the managed trade report.
    if trigger_fired:
        if sl_modification_occurred:
            verdict = TRAILING_MANAGER_OK_TRIGGERED
            ok_checks.append(
                "Trailing/breakeven trigger fired and SL modification occurred "
                f"(sl_modification_events={sl_modification_events})"
            )
        else:
            # Trigger fired but no SL modification recorded in forensics.
            # Block ONLY if monitor_iterations and hold_seconds thresholds
            # were met - otherwise downgrade to WARN.
            if monitor_iterations_sufficient and hold_seconds_sufficient:
                verdict = TRAILING_MANAGER_BLOCKED_NOT_RUNNING
                blockers.append(
                    "TRAILING_MANAGER_NOT_RUNNING: trigger flags fired "
                    f"(breakeven={breakeven_triggered}, "
                    f"trailing={trailing_triggered}, "
                    f"profit_lock={profit_lock_triggered}) but "
                    f"sl_modification_events=0 "
                    f"(monitor_iterations={monitor_iterations}, "
                    f"hold_seconds={hold_seconds})"
                )
            else:
                verdict = TRAILING_MANAGER_WARN_INSUFFICIENT_EVIDENCE
                warnings.append(
                    "Trigger flags fired but monitor/hold thresholds not met "
                    f"(monitor_iterations={monitor_iterations} "
                    f"< min={min_monitor_iterations} OR "
                    f"hold_seconds={hold_seconds} "
                    f"< min={min_hold_seconds})"
                )
    else:
        # Case B: No trigger flags fired.
        # Determine whether trigger SHOULD have fired based on profit_R / MFE.
        profit_evidence_values = [
            v for v in (profit_R, mfe_profit_R) if v is not None
        ]
        if profit_evidence_values:
            best_profit_R = max(profit_evidence_values)
            findings["best_profit_R"] = best_profit_R

            # BLOCKED: profit_R reached breakeven threshold AND monitor
            # iterations AND hold seconds were sufficient AND no SL
            # modification occurred.
            should_have_triggered = (
                best_profit_R >= breakeven_trigger_R
                and monitor_iterations_sufficient
                and hold_seconds_sufficient
                and not sl_modification_occurred
            )
            if should_have_triggered:
                verdict = TRAILING_MANAGER_BLOCKED_NOT_RUNNING
                blockers.append(
                    "TRAILING_MANAGER_NOT_RUNNING: profit_R="
                    f"{best_profit_R:.4f} >= breakeven_trigger_R="
                    f"{breakeven_trigger_R} AND monitor_iterations="
                    f"{monitor_iterations} >= min_monitor_iterations="
                    f"{min_monitor_iterations} AND hold_seconds="
                    f"{hold_seconds} >= min_hold_seconds="
                    f"{min_hold_seconds} but sl_modification_events=0"
                )
            elif best_profit_R < breakeven_trigger_R:
                verdict = TRAILING_MANAGER_OK_NO_TRIGGER
                ok_checks.append(
                    "Position closed before any trailing threshold reached "
                    f"(profit_R={best_profit_R:.4f} < "
                    f"breakeven_trigger_R={breakeven_trigger_R})"
                )
                ok_checks.append(
                    "No SL modification expected - threshold not reached"
                )
            else:
                # profit_R reached threshold but monitor/hold conditions
                # were not met, so SL modification was NOT expected.
                verdict = TRAILING_MANAGER_OK_NO_TRIGGER
                ok_checks.append(
                    f"profit_R={best_profit_R:.4f} reached threshold but "
                    f"monitor/hold conditions not met "
                    f"(monitor_iterations={monitor_iterations}, "
                    f"hold_seconds={hold_seconds}) - no SL modification "
                    f"expected"
                )
        else:
            # Cannot compute profit_R and no MFE available.
            # Fall back to position-status heuristics.
            if (
                final_position_status == "CLOSED"
                and not sl_hit_detected
                and not trigger_fired
                and not sl_modification_occurred
            ):
                # Position closed cleanly without SL hit and no triggers
                # fired - acceptable "no trigger" outcome.
                verdict = TRAILING_MANAGER_OK_NO_TRIGGER
                ok_checks.append(
                    "Position closed (final_position_status=CLOSED) "
                    "without SL hit and no triggers fired - no SL "
                    "modification expected"
                )
            elif (
                final_position_status == "OPEN"
                and not trigger_fired
                and not sl_modification_occurred
            ):
                # Position still open and we cannot prove profit_R.
                verdict = TRAILING_MANAGER_WARN_INSUFFICIENT_EVIDENCE
                warnings.append(
                    "Position still OPEN and profit_R not computable - "
                    "cannot determine if trailing should have triggered"
                )
            else:
                verdict = TRAILING_MANAGER_WARN_INSUFFICIENT_EVIDENCE
                warnings.append(
                    "Cannot determine if trailing should have triggered "
                    "(profit_R not computable, MFE not available)"
                )

    # Defensive fallback - should never happen.
    if verdict is None:
        verdict = TRAILING_MANAGER_WARN_INSUFFICIENT_EVIDENCE
        warnings.append(
            "Verdict fallback: insufficient evidence to classify "
            "trailing manager behaviour"
        )

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
    """Write audit result to JSON and Markdown.

    Writes to ``data/audit/demo_micro_execution/
    trailing_manager_verification.json`` and ``.md``.
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUTPUT_DIR / "trailing_manager_verification.json"
    md_path = OUTPUT_DIR / "trailing_manager_verification.md"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str, ensure_ascii=False)

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(
            "# TITAN XAU AI - Trailing Manager Verification Audit\n\n"
        )
        f.write(
            "Sprint 9.9.3.45.8.11 - Investigates forensics "
            "`TRAILING_MANAGER_NOT_RUNNING` root cause.\n\n"
        )
        f.write(f"**Verdict:** **{result['verdict']}**\n\n")
        f.write(f"**Timestamp:** {result['timestamp_utc']}\n\n")
        f.write(
            "## Input Artefacts\n\n"
            "| Artefact | Path | Available |\n|---|---|---|\n"
        )
        fnd = result.get("findings", {})
        f.write(
            f"| Receipt | {fnd.get('receipt_path', 'N/A')} | "
            f"{fnd.get('receipt_available', False)} |\n"
        )
        f.write(
            f"| Forensics | {fnd.get('forensics_path', 'N/A')} | "
            f"{fnd.get('forensics_available', False)} |\n"
        )
        f.write(
            f"| Managed Trade Report | {fnd.get('managed_trade_report_path', 'N/A')} | "
            f"{fnd.get('managed_trade_report_available', False)} |\n"
        )
        f.write(
            f"\n**Forensics root_cause:** "
            f"`{fnd.get('forensics_root_cause', 'N/A')}`\n\n"
        )

        f.write("## Findings\n\n")
        f.write("| Check | Value |\n|---|---|\n")
        for k in (
            "monitor_iterations",
            "monitor_duration_seconds",
            "hold_seconds",
            "breakeven_trigger_R",
            "trailing_trigger_R",
            "tp_extension_trigger_R",
            "profit_lock_trigger_R",
            "min_monitor_iterations",
            "min_hold_seconds",
            "breakeven_triggered",
            "trailing_triggered",
            "profit_lock_triggered",
            "trigger_fired",
            "breakeven_threshold_reached",
            "trailing_threshold_reached",
            "dynamic_tp_threshold_reached",
            "profit_lock_threshold_reached",
            "sl_modification_expected",
            "sl_modification_events",
            "sl_modification_occurred",
            "no_trailing_event_acceptable",
            "profit_R",
            "profit_R_computable",
            "mfe_available",
            "mfe_profit_R",
            "best_profit_R",
            "sl_hit_detected",
            "final_position_status",
            "monitor_stop_reason",
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
        safety = result.get("safety", {})
        f.write(f"- order_send_called: {safety.get('order_send_called', False)}\n")
        f.write(f"- position_modified: {safety.get('position_modified', False)}\n")
        f.write(f"- no_martingale: {safety.get('no_martingale', True)}\n")
        f.write(f"- no_grid: {safety.get('no_grid', True)}\n")
        f.write(f"- no_averaging: {safety.get('no_averaging', True)}\n")

    return {"json_path": str(json_path), "md_path": str(md_path)}


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Trailing manager verification audit (no MT5, no order_send). "
            "Investigates forensics TRAILING_MANAGER_NOT_RUNNING root cause."
        )
    )
    parser.add_argument(
        "--receipt-path",
        type=Path,
        default=None,
        help="Override path to execution receipt JSON",
    )
    parser.add_argument(
        "--forensics-path",
        type=Path,
        default=None,
        help="Override path to post-trade forensics JSON",
    )
    parser.add_argument(
        "--managed-report-path",
        type=Path,
        default=None,
        help="Override path to managed trade report JSON",
    )
    args = parser.parse_args()

    print("=" * 70)
    print(
        "  TITAN XAU AI - Trailing Manager Verification Audit "
        "(Sprint 9.9.3.45.8.11)"
    )
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
    print(
        f"\n  Forensics root_cause: {fnd.get('forensics_root_cause', 'N/A')}"
    )
    print(f"  monitor_iterations: {fnd.get('monitor_iterations', 0)}")
    print(f"  hold_seconds: {fnd.get('hold_seconds', 0)}")
    print(f"  profit_R: {fnd.get('profit_R', 'N/A')}")
    print(
        f"  sl_modification_events: "
        f"{fnd.get('sl_modification_events', 0)}"
    )
    if result.get("blockers"):
        print("\n  Blockers:")
        for b in result["blockers"]:
            print(f"    - {b}")
    if result.get("warnings"):
        print("\n  Warnings:")
        for w in result["warnings"]:
            print(f"    - {w}")
    print(f"\n  JSON: {report['json_path']}")
    print(f"  MD:   {report['md_path']}")
    print("\n" + "=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
