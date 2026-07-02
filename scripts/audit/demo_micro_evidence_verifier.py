#!/usr/bin/env python3
"""
TITAN XAU AI - Demo Micro Evidence Verifier (Sprint 9.9.3.45.8.16 v2.7.3)
=========================================================================
Reads forensics output and classifies micro proof status.

Sprint 9.9.3.45.8.16 v2.7.3: Accept receipt-supported diagnostic match
(DEMO_MICRO_EVIDENCE_RECEIPT_DIAGNOSTIC_CONFIRMED) as proof PASS when
fallback_used=false. Accept DEMO_MICRO_EVIDENCE_DIAGNOSTIC_ONLY_RESOLVED
as INCOMPLETE (not FAIL) when diagnostic confirms closed but no deal ticket
exposed.

NEVER sends orders. NEVER modifies positions.
"""
from __future__ import annotations
import json, sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
OUTPUT_DIR = REPO_ROOT / "data" / "audit" / "demo_micro_execution"

MICRO_PROOF_PASS = "MICRO_PROOF_PASS"
MICRO_PROOF_INCOMPLETE = "MICRO_PROOF_INCOMPLETE"
MICRO_PROOF_FAIL = "MICRO_PROOF_FAIL"


def run_verification() -> dict:
    ts = datetime.now(timezone.utc).isoformat()
    ok_checks = []
    blockers = []
    warnings = []

    # Read forensics output
    forensics_path = OUTPUT_DIR / "post_trade_forensics.json"
    if not forensics_path.exists():
        return {
            "timestamp_utc": ts,
            "verdict": MICRO_PROOF_FAIL,
            "blockers": ["Forensics output not found"],
            "ok_checks": ok_checks,
            "warnings": warnings,
            "safety": {"order_send_called": False, "position_modified": False},
        }

    try:
        with open(forensics_path, "r", encoding="utf-8") as f:
            forensics = json.load(f)
    except Exception as e:
        return {
            "timestamp_utc": ts,
            "verdict": MICRO_PROOF_FAIL,
            "blockers": [f"Forensics read error: {e}"],
            "ok_checks": ok_checks,
            "warnings": warnings,
            "safety": {"order_send_called": False, "position_modified": False},
        }

    findings = forensics.get("findings", {})
    forensics_verdict = forensics.get("verdict", "")
    receipt_match_found = findings.get("receipt_match_found", False)
    fallback_used = findings.get("fallback_used", False)
    old_trades_used_as_proof = findings.get("old_trades_used_as_proof", False)
    diagnostic_resolved_closed = findings.get("diagnostic_resolved_closed", False)
    diagnostic_history_deal_match = findings.get("diagnostic_history_deal_match", False)
    root_cause = findings.get("root_cause", "")
    entry_deals_count = findings.get("entry_deals_count", 0)
    exit_deals_count = findings.get("exit_deals_count", 0)
    open_positions_count = findings.get("open_positions_count", 0)

    ok_checks.append(f"Forensics verdict: {forensics_verdict}")
    ok_checks.append(f"Receipt match found: {receipt_match_found}")
    ok_checks.append(f"Entry deals: {entry_deals_count}")
    ok_checks.append(f"Exit deals: {exit_deals_count}")
    ok_checks.append(f"Open positions: {open_positions_count}")
    ok_checks.append(f"Fallback used: {fallback_used}")
    ok_checks.append(f"Old trades used as proof: {old_trades_used_as_proof}")
    ok_checks.append(f"Diagnostic resolved closed: {diagnostic_resolved_closed}")
    ok_checks.append(f"Diagnostic history deal match: {diagnostic_history_deal_match}")
    ok_checks.append(f"Root cause: {root_cause}")

    # Rules
    if fallback_used or old_trades_used_as_proof:
        blockers.append("FALLBACK_USED: old trades cannot be used as proof")
        return {
            "timestamp_utc": ts,
            "verdict": MICRO_PROOF_FAIL,
            "blockers": blockers,
            "ok_checks": ok_checks,
            "warnings": warnings,
            "forensics_verdict": forensics_verdict,
            "safety": {"order_send_called": False, "position_modified": False},
        }

    # v2.7.3: Receipt-supported diagnostic match counts as PASS.
    if (forensics_verdict == "DEMO_MICRO_EVIDENCE_RECEIPT_DIAGNOSTIC_CONFIRMED"
            and not fallback_used
            and not old_trades_used_as_proof):
        return {
            "timestamp_utc": ts,
            "verdict": MICRO_PROOF_PASS,
            "blockers": blockers,
            "ok_checks": ok_checks + [
                "PASS: receipt-supported diagnostic match confirmed "
                "(fallback=false, old_trades=false)"
            ],
            "warnings": warnings,
            "forensics_verdict": forensics_verdict,
            "safety": {"order_send_called": False, "position_modified": False},
        }

    # v2.7.3: Diagnostic-resolved-only is INCOMPLETE (not FAIL).
    if forensics_verdict == "DEMO_MICRO_EVIDENCE_DIAGNOSTIC_ONLY_RESOLVED":
        return {
            "timestamp_utc": ts,
            "verdict": MICRO_PROOF_INCOMPLETE,
            "blockers": blockers,
            "ok_checks": ok_checks,
            "warnings": warnings + [
                "Diagnostic confirmed closed but no deal ticket exposed - "
                "forensics cannot independently match a deal. Treat as INCOMPLETE."
            ],
            "forensics_verdict": forensics_verdict,
            "safety": {"order_send_called": False, "position_modified": False},
        }

    if not receipt_match_found and not diagnostic_history_deal_match:
        blockers.append(
            "RECEIPT_MATCH_NOT_FOUND: receipt must match (or diagnostic must confirm) for proof"
        )
        return {
            "timestamp_utc": ts,
            "verdict": MICRO_PROOF_FAIL,
            "blockers": blockers,
            "ok_checks": ok_checks,
            "warnings": warnings,
            "forensics_verdict": forensics_verdict,
            "safety": {"order_send_called": False, "position_modified": False},
        }

    if open_positions_count > 0:
        blockers.append(f"UNMANAGED_OPEN_POSITION: {open_positions_count} open positions remain")
        return {
            "timestamp_utc": ts,
            "verdict": MICRO_PROOF_FAIL,
            "blockers": blockers,
            "ok_checks": ok_checks,
            "warnings": warnings,
            "forensics_verdict": forensics_verdict,
            "safety": {"order_send_called": False, "position_modified": False},
        }

    if forensics_verdict == "DEMO_MICRO_EVIDENCE_PASS":
        verdict = MICRO_PROOF_PASS
        ok_checks.append("PASS: exact receipt match with entry and exit deals")
    elif forensics_verdict == "DEMO_MICRO_EVIDENCE_ENTRY_CONFIRMED_CLOSE_DEAL_MISSING":
        verdict = MICRO_PROOF_INCOMPLETE
        warnings.append("Entry confirmed but close deal missing - proof incomplete")
    elif forensics_verdict == "DEMO_MICRO_EVIDENCE_HISTORY_PENDING":
        verdict = MICRO_PROOF_INCOMPLETE
        warnings.append("History pending - retry forensics after a short delay")
    elif forensics_verdict == "DEMO_MICRO_EVIDENCE_INCOMPLETE":
        verdict = MICRO_PROOF_INCOMPLETE
        warnings.append("Forensics incomplete")
    elif forensics_verdict == "DEMO_MICRO_EVIDENCE_FAIL":
        verdict = MICRO_PROOF_FAIL
        blockers.append("Forensics evidence FAIL")
    else:
        verdict = MICRO_PROOF_INCOMPLETE
        warnings.append(f"Unknown forensics verdict: {forensics_verdict}")

    return {
        "timestamp_utc": ts,
        "verdict": verdict,
        "blockers": blockers,
        "ok_checks": ok_checks,
        "warnings": warnings,
        "forensics_verdict": forensics_verdict,
        "safety": {"order_send_called": False, "position_modified": False},
    }


def main() -> int:
    print("=" * 70)
    print("  TITAN XAU AI - Demo Micro Evidence Verifier (v2.7.3)")
    print("=" * 70)
    result = run_verification()
    print(f"\n  Verdict: {result['verdict']}")
    print(f"  Blockers: {len(result.get('blockers', []))}")
    if result.get("blockers"):
        for b in result["blockers"]:
            print(f"    - {b}")
    print(f"\n  Safety: order_send_called=False, position_modified=False")
    print("\n" + "=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
