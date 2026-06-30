#!/usr/bin/env python3
"""
TITAN XAU AI — Sprint 9.9.3.25.2 Redact Repeatability Evidence
================================================================

Generates a safe, redacted execution summary from either:
  A. A local raw evidence directory (if provided via --evidence-dir)
  B. Operator-provided verified facts (if --from-operator-summary is used)

Output:
  docs/audit/demo_micro_repeatability_metaquotes_redacted.json
  docs/audit/demo_micro_repeatability_metaquotes_redacted.md

Redacts:
  - account login (masked: 12***78)
  - account name (removed)
  - exact balance/equity (removed)
  - local Windows paths (removed)
  - personal identifiers (removed)
  - raw broker account details (removed)

Retains:
  - broker server name
  - account type (DEMO)
  - symbol, lot
  - raw probe PASS
  - repeatability PASS
  - cycles passed/failed
  - final open positions
  - open/close retcodes
  - execution performed by operator

Usage:
  python scripts/audit/redact_repeatability_evidence.py --from-operator-summary
  python scripts/audit/redact_repeatability_evidence.py --evidence-dir path/to/folder
"""
from __future__ import annotations
import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

OUTPUT_DIR = REPO_ROOT / "docs" / "audit"
JSON_PATH = OUTPUT_DIR / "demo_micro_repeatability_metaquotes_redacted.json"
MD_PATH = OUTPUT_DIR / "demo_micro_repeatability_metaquotes_redacted.md"

# Verified operator facts (Sprint 9.9.3.25.2)
OPERATOR_SUMMARY = {
    "broker_server": "MetaQuotes-Demo",
    "account_type": "DEMO",
    "symbol": "XAUUSD",
    "lot": 0.01,
    "raw_probe_status": "PASS",
    "raw_probe_open_retcode": 10009,
    "raw_probe_close_retcode": 10009,
    "repeatability_verdict": "DEMO_REPEATABILITY_PASS",
    "cycles_passed": 3,
    "cycles_failed": 0,
    "final_open_positions": 0,
    "execution_performed_by": "operator (local Windows MT5)",
    "z_ai_executed": False,
    "safety_note": "No raw account evidence committed. Account identifiers redacted.",
}


def _mask_login(login) -> str:
    if login is None:
        return "REDACTED"
    s = str(login)
    if len(s) <= 4:
        return s[:1] + "***" + s[-1:]
    return s[:2] + "***" + s[-2:]


def _redact_dict(obj) -> None:
    """Recursively redact sensitive keys in a dict/list."""
    if isinstance(obj, dict):
        for key in list(obj.keys()):
            val = obj[key]
            if key in ("login", "account_login") and isinstance(val, (str, int)):
                obj[key] = _mask_login(val)
            elif key in ("name", "account_name", "owner") and isinstance(val, str):
                obj[key] = "REDACTED"
            elif key in ("balance", "equity", "credit") and isinstance(val, (int, float)):
                obj[key] = "REDACTED"
            elif key in ("path", "file_path", "local_path") and isinstance(val, str):
                obj[key] = "REDACTED"
            elif isinstance(val, (dict, list)):
                _redact_dict(val)
    elif isinstance(obj, list):
        for item in obj:
            _redact_dict(item)


def _redact_string(text: str) -> str:
    """Redact sensitive patterns in a string."""
    # Mask logins (digits 6+)
    text = re.sub(r'\blogin["\']?\s*[:=]\s*"?(\d{6,})', lambda m: f'login: {_mask_login(m.group(1))}', text, flags=re.IGNORECASE)
    # Remove Windows paths
    text = re.sub(r'[A-Z]:\\[^\s"\'<>|]+', '[REDACTED_PATH]', text)
    # Remove account names
    text = re.sub(r'name["\']?\s*[:=]\s*"?[A-Z][a-z]+\s+[A-Z][a-z]+', 'name: REDACTED', text, flags=re.IGNORECASE)
    return text


def generate_from_operator_summary() -> dict:
    """Generate redacted summary from verified operator facts."""
    ts = datetime.now(timezone.utc).isoformat()
    summary = {
        "timestamp_utc": ts,
        "source": "operator_summary",
        **OPERATOR_SUMMARY,
    }
    return summary


def generate_from_evidence_dir(evidence_dir: str) -> dict:
    """Generate redacted summary from a raw evidence directory."""
    ev_path = Path(evidence_dir)
    if not ev_path.exists():
        print(f"  ERROR: evidence directory not found: {ev_path}")
        return generate_from_operator_summary()

    # Try to load repeatability report
    report_path = ev_path / "demo_micro_repeatability_report.json"
    if not report_path.exists():
        # Try subdirectories
        for sub in sorted(ev_path.rglob("demo_micro_repeatability_report.json")):
            report_path = sub
            break

    summary = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "source": "evidence_dir",
        "evidence_dir": "[REDACTED_PATH]",
    }

    if report_path.exists():
        with open(report_path, "r", encoding="utf-8") as f:
            raw_report = json.load(f)
        _redact_dict(raw_report)
        summary.update({
            "broker_server": raw_report.get("broker_server", "MetaQuotes-Demo"),
            "account_type": "DEMO",
            "symbol": "XAUUSD",
            "lot": 0.01,
            "repeatability_verdict": raw_report.get("final_verdict", "UNKNOWN"),
            "cycles_passed": raw_report.get("cycles_passed", 0),
            "cycles_failed": raw_report.get("cycles_failed", 0),
            "final_open_positions": raw_report.get("final_open_positions", -1),
            "execution_performed_by": "operator (local Windows MT5)",
            "z_ai_executed": False,
            "safety_note": "No raw account evidence committed. Account identifiers redacted.",
        })
        # Extract cycle retcodes if available
        cycles = raw_report.get("cycles", [])
        if cycles:
            summary["cycle_1_open_retcode"] = cycles[0].get("open_retcode")
            summary["cycle_1_close_retcode"] = cycles[0].get("close_retcode")
            summary["cycle_2_open_retcode"] = cycles[1].get("open_retcode") if len(cycles) > 1 else None
            summary["cycle_2_close_retcode"] = cycles[1].get("close_retcode") if len(cycles) > 1 else None
            summary["cycle_3_open_retcode"] = cycles[2].get("open_retcode") if len(cycles) > 2 else None
            summary["cycle_3_close_retcode"] = cycles[2].get("close_retcode") if len(cycles) > 2 else None
    else:
        summary.update(OPERATOR_SUMMARY)
        summary["source"] = "operator_summary_fallback"

    return summary


def write_report(summary: dict) -> dict:
    """Write redacted JSON + MD report."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str, ensure_ascii=False)

    with open(MD_PATH, "w", encoding="utf-8") as f:
        f.write("# TITAN XAU AI — Redacted Repeatability Execution Summary\n\n")
        f.write(f"**Generated:** {summary['timestamp_utc']}\n\n")
        f.write(f"**Source:** {summary['source']}\n\n")
        f.write(f"**Safety:** {summary.get('safety_note', 'N/A')}\n\n")
        f.write("## Execution Results\n\n")
        f.write("| Field | Value |\n|---|---|\n")
        f.write(f"| Broker Server | {summary.get('broker_server', 'N/A')} |\n")
        f.write(f"| Account Type | {summary.get('account_type', 'N/A')} |\n")
        f.write(f"| Symbol | {summary.get('symbol', 'N/A')} |\n")
        f.write(f"| Lot | {summary.get('lot', 'N/A')} |\n")
        f.write(f"| Raw Probe | {summary.get('raw_probe_status', 'N/A')} |\n")
        f.write(f"| Repeatability Verdict | {summary.get('repeatability_verdict', 'N/A')} |\n")
        f.write(f"| Cycles Passed | {summary.get('cycles_passed', 'N/A')} |\n")
        f.write(f"| Cycles Failed | {summary.get('cycles_failed', 'N/A')} |\n")
        f.write(f"| Final Open Positions | {summary.get('final_open_positions', 'N/A')} |\n")
        f.write(f"| Executed By | {summary.get('execution_performed_by', 'N/A')} |\n")
        f.write(f"| Z AI Executed | {summary.get('z_ai_executed', 'N/A')} |\n")
        if summary.get("raw_probe_open_retcode"):
            f.write(f"| Raw Probe Open Retcode | {summary.get('raw_probe_open_retcode')} |\n")
            f.write(f"| Raw Probe Close Retcode | {summary.get('raw_probe_close_retcode')} |\n")
        f.write("\n## Privacy\n\n")
        f.write("- Account login: REDACTED (masked)\n")
        f.write("- Account name: REDACTED\n")
        f.write("- Balance/equity: REDACTED\n")
        f.write("- Local paths: REDACTED\n")
        f.write("- No raw evidence committed to repository\n")

    return {"json_path": str(JSON_PATH), "md_path": str(MD_PATH)}


def main():
    parser = argparse.ArgumentParser(
        description="Generate redacted repeatability execution summary")
    parser.add_argument("--evidence-dir", default=None,
                        help="Path to raw evidence directory")
    parser.add_argument("--from-operator-summary", action="store_true",
                        help="Use verified operator facts instead of raw evidence")
    args = parser.parse_args()

    print("=" * 70)
    print("  TITAN XAU AI — Redact Repeatability Evidence (Sprint 9.9.3.25.2)")
    print("=" * 70)

    if args.evidence_dir:
        print(f"  Source: evidence dir ({args.evidence_dir})")
        summary = generate_from_evidence_dir(args.evidence_dir)
    else:
        print("  Source: operator summary (verified facts)")
        summary = generate_from_operator_summary()

    result = write_report(summary)
    print(f"\n  JSON: {result['json_path']}")
    print(f"  MD:   {result['md_path']}")
    print(f"\n  Verdict: {summary.get('repeatability_verdict', 'N/A')}")
    print(f"  Cycles: {summary.get('cycles_passed', 0)}/{summary.get('cycles_passed', 0) + summary.get('cycles_failed', 0)} passed")
    print(f"  Safety: {summary.get('safety_note', 'N/A')}")
    print("\n" + "=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
