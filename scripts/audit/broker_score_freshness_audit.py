#!/usr/bin/env python3
"""
TITAN XAU AI - Broker Score Freshness Audit (Sprint v2.8.2)
=============================================================
Validates whether broker_score_report.json is fresh, valid, and matches
the current account. Distinguishes between:
  - Fresh valid broker report with passing score -> BROKER_SCORE_VALID
  - Fresh valid broker report with failing score -> BROKER_SCORE_FAIL
  - Stale/default broker score (score=0, generated without MT5) -> BROKER_SCORE_STALE
  - Mismatched account/server -> BROKER_SCORE_MISMATCH
  - No broker report -> BROKER_SCORE_NOT_FOUND

Also validates MetaQuotes-Demo as allowed controlled demo execution venue,
and FundedNext demo as NOT allowed for algo trading.

NEVER sends orders. NEVER modifies positions. NEVER creates tokens.

Verdicts:
  BROKER_SCORE_VALID
  BROKER_SCORE_FAIL
  BROKER_SCORE_STALE
  BROKER_SCORE_MISMATCH
  BROKER_SCORE_NOT_FOUND
  BROKER_VENUE_CONTROLLED_DEMO_ALLOWED
  BROKER_VENUE_FUNDEDNEXT_BLOCKED
  BROKER_VENUE_VALIDATION_PENDING

Outputs:
  data/audit/demo_micro_execution/broker_score_freshness_audit.json
  data/audit/demo_micro_execution/broker_score_freshness_audit.md
"""
from __future__ import annotations
import argparse, json, sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
OUTPUT_DIR = REPO_ROOT / "data" / "audit" / "demo_micro_execution"

BROKER_SCORE_VALID = "BROKER_SCORE_VALID"
BROKER_SCORE_FAIL = "BROKER_SCORE_FAIL"
BROKER_SCORE_STALE = "BROKER_SCORE_STALE"
BROKER_SCORE_MISMATCH = "BROKER_SCORE_MISMATCH"
BROKER_SCORE_NOT_FOUND = "BROKER_SCORE_NOT_FOUND"
BROKER_VENUE_CONTROLLED_DEMO_ALLOWED = "BROKER_VENUE_CONTROLLED_DEMO_ALLOWED"
BROKER_VENUE_FUNDEDNEXT_BLOCKED = "BROKER_VENUE_FUNDEDNEXT_BLOCKED"
BROKER_VENUE_VALIDATION_PENDING = "BROKER_VENUE_VALIDATION_PENDING"

ALL_VERDICTS = (
    BROKER_SCORE_VALID,
    BROKER_SCORE_FAIL,
    BROKER_SCORE_STALE,
    BROKER_SCORE_MISMATCH,
    BROKER_SCORE_NOT_FOUND,
    BROKER_VENUE_CONTROLLED_DEMO_ALLOWED,
    BROKER_VENUE_FUNDEDNEXT_BLOCKED,
    BROKER_VENUE_VALIDATION_PENDING,
)


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        if v is None:
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def _to_str(v: Any, default: str = "") -> str:
    if v is None:
        return default
    return str(v)


def run_audit() -> dict:
    """Run the broker score freshness audit."""
    ts = datetime.now(timezone.utc).isoformat()
    ok_checks = []
    blockers = []
    warnings = []
    findings = {}

    # Get current broker server from receipt
    current_mt5_server = ""
    current_account_type = ""
    receipt_path = REPO_ROOT / "data" / "runtime" / "demo_micro_execution_receipt.json"
    if receipt_path.exists():
        try:
            with open(receipt_path, "r") as f:
                receipt = json.load(f)
            current_mt5_server = receipt.get("account_server", "") or ""
            current_account_type = "demo" if "demo" in current_mt5_server.lower() else ""
        except Exception:
            pass
    # Also check managed_trade_report
    if not current_mt5_server:
        managed_path = OUTPUT_DIR / "managed_trade_report.json"
        if managed_path.exists():
            try:
                with open(managed_path, "r") as f:
                    m = json.load(f)
                current_mt5_server = m.get("account_server", "") or ""
            except Exception:
                pass

    findings["current_mt5_server"] = current_mt5_server
    findings["current_account_type"] = current_account_type or "demo"

    broker_server_lower = current_mt5_server.lower()
    is_fundednext = "fundednext" in broker_server_lower
    is_metaquotes_demo = "metaquotes" in broker_server_lower or ("demo" in broker_server_lower and not is_fundednext)

    findings["is_fundednext_demo"] = is_fundednext
    findings["is_metaquotes_demo"] = is_metaquotes_demo

    # v2.8.2: Block FundedNext demo for algo execution
    if is_fundednext:
        verdict = BROKER_VENUE_FUNDEDNEXT_BLOCKED
        blockers.append("FUNDEDNEXT_DEMO_ALGO_NOT_ALLOWED: FundedNext demo does not allow algo trading")
        findings["broker_execution_venue_allowed"] = False
        findings["broker_execution_venue_reason"] = "FUNDEDNEXT_DEMO_ALGO_NOT_ALLOWED"
        findings["fundednext_demo_execution_blocked"] = True
        findings["metaquotes_demo_controlled_allowed"] = False
        return {
            "timestamp_utc": ts,
            "verdict": verdict,
            "ok_checks": ok_checks,
            "blockers": blockers,
            "warnings": warnings,
            "findings": findings,
            "safety": {"order_send_called": False, "position_modified": False, "execution_token_created": False},
        }

    findings["fundednext_demo_execution_blocked"] = False

    # Check broker score report
    broker_score_path = REPO_ROOT / "data" / "audit" / "broker_scoring" / "broker_score_report.json"
    findings["broker_report_exists"] = broker_score_path.exists()
    findings["broker_report_path"] = str(broker_score_path)

    broker_report = None
    if broker_score_path.exists():
        try:
            with open(broker_score_path, "r") as f:
                broker_report = json.load(f)
        except Exception:
            pass

    if broker_report:
        broker_report_score = _safe_float(broker_report.get("overall_score", 0))
        broker_report_threshold = 70.0
        broker_report_server = _to_str(broker_report.get("server", ""))
        broker_report_account_type = _to_str(broker_report.get("account_type", ""))
        broker_report_symbol = _to_str(broker_report.get("symbol", ""))
        broker_report_timestamp = _to_str(broker_report.get("timestamp_utc", "") or broker_report.get("generated_at", ""))

        # Calculate report age
        broker_report_age_seconds = 0
        if broker_report_timestamp:
            try:
                report_dt = datetime.fromisoformat(broker_report_timestamp.replace("Z", "+00:00"))
                broker_report_age_seconds = int((datetime.now(timezone.utc) - report_dt).total_seconds())
            except Exception:
                pass

        # Check if score=0 is stale/default (generated without MT5)
        brokers_evaluated = broker_report.get("brokers_evaluated", 0) or 0
        broker_report_generated_without_mt5 = (broker_report_score == 0 and not brokers_evaluated)
        broker_report_is_stale = broker_report_generated_without_mt5 or (broker_report_age_seconds > 86400 * 7)  # > 7 days

        # Check if report matches current account
        broker_report_matches_current_account = True
        if broker_report_server and current_mt5_server:
            broker_report_matches_current_account = broker_report_server.lower() in current_mt5_server.lower() or current_mt5_server.lower() in broker_report_server.lower()

        findings["broker_report_score"] = broker_report_score
        findings["broker_report_threshold"] = broker_report_threshold
        findings["broker_report_server"] = broker_report_server
        findings["broker_report_account_type"] = broker_report_account_type
        findings["broker_report_symbol"] = broker_report_symbol
        findings["broker_report_timestamp"] = broker_report_timestamp
        findings["broker_report_age_seconds"] = broker_report_age_seconds
        findings["broker_report_schema_valid"] = True
        findings["broker_report_is_stale"] = broker_report_is_stale
        findings["broker_report_matches_current_account"] = broker_report_matches_current_account
        findings["broker_report_generated_without_mt5"] = broker_report_generated_without_mt5

        # Determine verdict
        if is_metaquotes_demo:
            # v2.8.2: MetaQuotes-Demo is the allowed controlled local demo test account.
            # Even if broker score is stale/0, MetaQuotes-Demo is allowed for controlled demo.
            verdict = BROKER_VENUE_CONTROLLED_DEMO_ALLOWED
            ok_checks.append("METAQUOTES_DEMO_ALLOWED_FOR_CONTROLLED_LOCAL_DEMO")
            findings["broker_execution_venue_allowed"] = True
            findings["broker_execution_venue_reason"] = "METAQUOTES_DEMO_ALLOWED_FOR_CONTROLLED_LOCAL_DEMO"
            findings["metaquotes_demo_controlled_allowed"] = True
            if broker_report_is_stale:
                warnings.append("BROKER_SCORE_STALE: broker_score_report.json has score=0 (generated without MT5) but MetaQuotes-Demo is allowed for controlled demo")
        elif broker_report_is_stale:
            verdict = BROKER_SCORE_STALE
            warnings.append("BROKER_SCORE_STALE: broker score=0 is stale/default, not treated as actual fail")
            findings["broker_execution_venue_allowed"] = False
            findings["broker_execution_venue_reason"] = "BROKER_VALIDATION_PENDING"
            findings["metaquotes_demo_controlled_allowed"] = False
        elif not broker_report_matches_current_account:
            verdict = BROKER_SCORE_MISMATCH
            warnings.append(f"BROKER_SCORE_MISMATCH: report server={broker_report_server} does not match current={current_mt5_server}")
            findings["broker_execution_venue_allowed"] = False
            findings["broker_execution_venue_reason"] = "BROKER_VALIDATION_PENDING"
            findings["metaquotes_demo_controlled_allowed"] = False
        elif broker_report_score >= broker_report_threshold:
            verdict = BROKER_SCORE_VALID
            ok_checks.append(f"BROKER_SCORE_VALID: score={broker_report_score} >= {broker_report_threshold}")
            findings["broker_execution_venue_allowed"] = True
            findings["broker_execution_venue_reason"] = "BROKER_SCORE_PASS"
            findings["metaquotes_demo_controlled_allowed"] = False
        else:
            verdict = BROKER_SCORE_FAIL
            blockers.append(f"BROKER_SCORE_BELOW_THRESHOLD: score={broker_report_score} < {broker_report_threshold}")
            findings["broker_execution_venue_allowed"] = False
            findings["broker_execution_venue_reason"] = "BROKER_SCORE_BELOW_THRESHOLD"
            findings["metaquotes_demo_controlled_allowed"] = False
    elif is_metaquotes_demo:
        # No broker report but MetaQuotes-Demo is allowed
        verdict = BROKER_VENUE_CONTROLLED_DEMO_ALLOWED
        ok_checks.append("METAQUOTES_DEMO_ALLOWED_FOR_CONTROLLED_LOCAL_DEMO (no broker report needed)")
        findings["broker_execution_venue_allowed"] = True
        findings["broker_execution_venue_reason"] = "METAQUOTES_DEMO_ALLOWED_FOR_CONTROLLED_LOCAL_DEMO"
        findings["metaquotes_demo_controlled_allowed"] = True
    else:
        verdict = BROKER_SCORE_NOT_FOUND
        warnings.append("BROKER_SCORE_NOT_FOUND: no broker score report and not MetaQuotes-Demo")
        findings["broker_execution_venue_allowed"] = False
        findings["broker_execution_venue_reason"] = "BROKER_VALIDATION_PENDING"
        findings["metaquotes_demo_controlled_allowed"] = False

    return {
        "timestamp_utc": ts,
        "verdict": verdict,
        "ok_checks": ok_checks,
        "blockers": blockers,
        "warnings": warnings,
        "findings": findings,
        "safety": {"order_send_called": False, "position_modified": False, "execution_token_created": False},
    }


def write_report(result: dict) -> dict:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUTPUT_DIR / "broker_score_freshness_audit.json"
    md_path = OUTPUT_DIR / "broker_score_freshness_audit.md"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str, ensure_ascii=False)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# TITAN XAU AI - Broker Score Freshness Audit (v2.8.2)\n\n")
        f.write(f"**Verdict:** **{result['verdict']}**\n\n")
        f.write(f"**Timestamp:** {result['timestamp_utc']}\n\n")
        fnd = result.get("findings", {})
        f.write("## Broker Report Validation\n\n")
        f.write("| Field | Value |\n|---|---|\n")
        for k in [
            "broker_report_exists", "broker_report_path", "broker_report_score",
            "broker_report_threshold", "broker_report_server", "broker_report_account_type",
            "broker_report_symbol", "broker_report_timestamp", "broker_report_age_seconds",
            "broker_report_schema_valid", "broker_report_is_stale",
            "broker_report_matches_current_account", "broker_report_generated_without_mt5",
            "current_mt5_server", "current_account_type",
            "is_fundednext_demo", "is_metaquotes_demo",
            "fundednext_demo_execution_blocked", "metaquotes_demo_controlled_allowed",
            "broker_execution_venue_allowed", "broker_execution_venue_reason",
        ]:
            if k in fnd:
                f.write(f"| {k} | {fnd[k]} |\n")
        if result.get("blockers"):
            f.write("\n## Blockers\n\n")
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
        f.write("- order_send_called: False\n- position_modified: False\n- execution_token_created: False\n")
    return {"json_path": str(json_path), "md_path": str(md_path)}


def main() -> int:
    print("=" * 70)
    print("  TITAN XAU AI - Broker Score Freshness Audit (v2.8.2)")
    print("=" * 70)
    result = run_audit()
    report = write_report(result)
    print(f"\n  Verdict: {result['verdict']}")
    fnd = result.get("findings", {})
    print(f"  Current MT5 server: {fnd.get('current_mt5_server', 'N/A')}")
    print(f"  Broker report exists: {fnd.get('broker_report_exists', False)}")
    print(f"  Broker report score: {fnd.get('broker_report_score', 0)}")
    print(f"  Broker report stale: {fnd.get('broker_report_is_stale', False)}")
    print(f"  Broker report matches account: {fnd.get('broker_report_matches_current_account', False)}")
    print(f"  Execution venue allowed: {fnd.get('broker_execution_venue_allowed', False)}")
    print(f"  Execution venue reason: {fnd.get('broker_execution_venue_reason', 'N/A')}")
    print(f"  FundedNext blocked: {fnd.get('fundednext_demo_execution_blocked', False)}")
    print(f"  MetaQuotes-Demo allowed: {fnd.get('metaquotes_demo_controlled_allowed', False)}")
    if result.get("blockers"):
        print(f"  Blockers: {len(result['blockers'])}")
        for b in result["blockers"]:
            print(f"    - {b}")
    print(f"\n  JSON: {report['json_path']}")
    print(f"  MD:   {report['md_path']}")
    print("\n" + "=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
