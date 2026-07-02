#!/usr/bin/env python3
"""
TITAN XAU AI - Archive Micro Proof Pass (Sprint 9.9.3.45.9)
============================================================

Archives the MICRO_PROOF_PASS evidence bundle into a timestamped archive
directory under data/audit/demo_micro/micro_proof_pass_<timestamp>/.

The archiver reads three artifacts produced by the demo micro execution
pipeline:

  - data/runtime/demo_micro_execution_receipt.json
      (the official execution receipt produced by run_managed_demo_micro_trade)
  - data/audit/demo_micro_execution/latest_receipt_diagnostic.json
      (receipt-vs-history diagnostic produced by diagnose_latest_execution_receipt)
  - data/audit/demo_micro_execution/post_trade_forensics.json
      (forensics verdict produced by collect_demo_micro_trade_forensics)

The archiver verifies that forensics verdict == DEMO_MICRO_EVIDENCE_PASS
(which maps to MICRO_PROOF_PASS). If forensics verdict is anything else,
the archiver MUST return MICRO_PROOF_ARCHIVE_BLOCKED and MUST NOT create
any archive directory.

When archiving succeeds the following files are written to the archive dir:
  - demo_micro_execution_receipt.json   (copy of receipt)
  - latest_receipt_diagnostic.json      (copy of diagnostic)
  - post_trade_forensics.json           (copy of forensics)
  - micro_proof_summary.json            (generated summary)
  - micro_proof_summary.md              (generated summary)

Verdicts:
  - MICRO_PROOF_ARCHIVED         : archive successfully created
  - MICRO_PROOF_ARCHIVE_BLOCKED  : pre-conditions not met (no receipt,
                                   forensics not PASS, read error, etc.)

SAFETY INVARIANTS:
  - NEVER imports MetaTrader5.
  - NEVER calls mt5.order_send / mt5.order_modify / mt5.positions_modify.
  - NEVER modifies positions or sends orders.
  - NEVER adds martingale / grid / averaging / loss-based lot multiplier.
  - Safety fields: order_send_called=False, position_modified=False,
    no_martingale=True.

Usage:
    python scripts/audit/archive_micro_proof_pass.py
"""
from __future__ import annotations
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

RECEIPT_PATH = REPO_ROOT / "data" / "runtime" / "demo_micro_execution_receipt.json"
DIAGNOSTIC_PATH = REPO_ROOT / "data" / "audit" / "demo_micro_execution" / "latest_receipt_diagnostic.json"
FORENSICS_PATH = REPO_ROOT / "data" / "audit" / "demo_micro_execution" / "post_trade_forensics.json"
ARCHIVE_ROOT = REPO_ROOT / "data" / "audit" / "demo_micro"

MICRO_PROOF_ARCHIVED = "MICRO_PROOF_ARCHIVED"
MICRO_PROOF_ARCHIVE_BLOCKED = "MICRO_PROOF_ARCHIVE_BLOCKED"

# Forensics verdict that maps to MICRO_PROOF_PASS.
REQUIRED_FORENSICS_VERDICT = "DEMO_MICRO_EVIDENCE_PASS"

# Safety fingerprint emitted on every result. These MUST always be False/True
# respectively - this script never sends orders, never modifies positions, and
# never uses forbidden recovery patterns - the safety fingerprint below
# certifies no_martingale=True and no grid / averaging / loss-based lot
# multipliers.
SAFETY_FINGERPRINT = {
    "order_send_called": False,
    "position_modified": False,
    "no_martingale": True,
}


def _load_json(path: Path) -> dict:
    """Load a JSON file, raising FileNotFoundError if missing."""
    if not path.exists():
        raise FileNotFoundError(f"Required artifact missing: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _blocked(reason: str, **extra) -> dict:
    """Construct a MICRO_PROOF_ARCHIVE_BLOCKED result."""
    result = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "verdict": MICRO_PROOF_ARCHIVE_BLOCKED,
        "blockers": [reason],
        "ok_checks": [],
        "warnings": [],
        "safety": dict(SAFETY_FINGERPRINT),
    }
    result.update(extra)
    return result


def _build_summary(
    receipt: dict,
    diagnostic: dict,
    forensics: dict,
    archive_dir: Path,
    files_archived: list,
) -> dict:
    """Build the micro_proof_summary.json structure."""
    findings = forensics.get("findings", {}) if isinstance(forensics.get("findings"), dict) else {}
    return {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "verdict": MICRO_PROOF_ARCHIVED,
        "forensics_verdict": forensics.get("verdict"),
        "required_forensics_verdict": REQUIRED_FORENSICS_VERDICT,
        "receipt_success": receipt.get("success"),
        "diagnostic_verdict": diagnostic.get("verdict"),
        "receipt_match_found": findings.get("receipt_match_found"),
        "fallback_used": findings.get("fallback_used"),
        "entry_deals_count": findings.get("entry_deals_count"),
        "exit_deals_count": findings.get("exit_deals_count"),
        "open_positions_count": findings.get("open_positions_count"),
        "archive_dir": str(archive_dir),
        "files_archived": files_archived,
        "safety": dict(SAFETY_FINGERPRINT),
    }


def _build_summary_md(summary: dict) -> str:
    """Render micro_proof_summary.md from the summary dict."""
    lines = [
        "# TITAN XAU AI - Micro Proof Pass Archive Summary",
        "",
        f"**Generated:** {summary['timestamp_utc']}",
        f"**Verdict:** {summary['verdict']}",
        f"**Forensics verdict:** {summary['forensics_verdict']}",
        f"**Required forensics verdict:** {summary['required_forensics_verdict']}",
        f"**Archive dir:** `{summary['archive_dir']}`",
        "",
        "## Receipt + Diagnostic + Forensics",
        "",
        "| Field | Value |",
        "|---|---|",
        f"| receipt.success | {summary['receipt_success']} |",
        f"| diagnostic.verdict | {summary['diagnostic_verdict']} |",
        f"| forensics.verdict | {summary['forensics_verdict']} |",
        f"| findings.receipt_match_found | {summary['receipt_match_found']} |",
        f"| findings.fallback_used | {summary['fallback_used']} |",
        f"| findings.entry_deals_count | {summary['entry_deals_count']} |",
        f"| findings.exit_deals_count | {summary['exit_deals_count']} |",
        f"| findings.open_positions_count | {summary['open_positions_count']} |",
        "",
        "## Archived Files",
        "",
    ]
    for f in summary["files_archived"]:
        lines.append(f"- {f}")
    lines.extend([
        "",
        "## Safety",
        "",
        "| Field | Value |",
        "|---|---|",
        f"| order_send_called | {summary['safety']['order_send_called']} |",
        f"| position_modified | {summary['safety']['position_modified']} |",
        f"| no_martingale | {summary['safety']['no_martingale']} |",
        "",
        "## Notes",
        "",
        "- This archive is READ-ONLY evidence preservation.",
        "- The archiver NEVER imports MetaTrader5, NEVER sends orders, "
        "NEVER modifies positions.",
        "- No martingale / grid / averaging / loss-based lot multipliers.",
    ])
    return "\n".join(lines) + "\n"


def run_archive(
    receipt_path: Path | None = None,
    diagnostic_path: Path | None = None,
    forensics_path: Path | None = None,
    archive_root: Path | None = None,
) -> dict:
    """Archive the MICRO_PROOF_PASS evidence bundle.

    Args:
        receipt_path: override path to receipt JSON (used in tests)
        diagnostic_path: override path to diagnostic JSON (used in tests)
        forensics_path: override path to forensics JSON (used in tests)
        archive_root: override parent dir for the archive subdirectory

    Returns:
        result dict with at minimum: timestamp_utc, verdict, blockers,
        ok_checks, warnings, safety. When verdict == MICRO_PROOF_ARCHIVED
        the dict also contains archive_dir, files_archived, json_path,
        md_path.
    """
    r_path = receipt_path or RECEIPT_PATH
    d_path = diagnostic_path or DIAGNOSTIC_PATH
    f_path = forensics_path or FORENSICS_PATH
    a_root = archive_root or ARCHIVE_ROOT

    # 1. Receipt must exist and load.
    try:
        receipt = _load_json(r_path)
    except FileNotFoundError as e:
        return _blocked(f"RECEIPT_NOT_FOUND: {e}")
    except Exception as e:
        return _blocked(f"RECEIPT_READ_ERROR: {e}")

    # 2. Diagnostic must exist and load.
    try:
        diagnostic = _load_json(d_path)
    except FileNotFoundError as e:
        return _blocked(f"DIAGNOSTIC_NOT_FOUND: {e}")
    except Exception as e:
        return _blocked(f"DIAGNOSTIC_READ_ERROR: {e}")

    # 3. Forensics must exist and load.
    try:
        forensics = _load_json(f_path)
    except FileNotFoundError as e:
        return _blocked(f"FORENSICS_NOT_FOUND: {e}")
    except Exception as e:
        return _blocked(f"FORENSICS_READ_ERROR: {e}")

    # 4. Forensics verdict must equal DEMO_MICRO_EVIDENCE_PASS.
    forensics_verdict = forensics.get("verdict", "")
    if forensics_verdict != REQUIRED_FORENSICS_VERDICT:
        return _blocked(
            f"FORENSICS_NOT_PASS: forensics verdict is {forensics_verdict!r}, "
            f"required {REQUIRED_FORENSICS_VERDICT!r}",
            forensics_verdict=forensics_verdict,
        )

    # 5. Fallback must never have been used as proof.
    findings = forensics.get("findings", {}) if isinstance(forensics.get("findings"), dict) else {}
    if findings.get("fallback_used"):
        return _blocked(
            "FALLBACK_USED: old trades cannot be archived as MICRO_PROOF_PASS",
            forensics_verdict=forensics_verdict,
        )

    # 6. Open positions must be 0 at archive time.
    if findings.get("open_positions_count", 0) and findings.get("open_positions_count") is not None:
        try:
            if int(findings.get("open_positions_count")) > 0:
                return _blocked(
                    f"UNMANAGED_OPEN_POSITION: {findings.get('open_positions_count')} "
                    "open positions remain",
                    forensics_verdict=forensics_verdict,
                )
        except (TypeError, ValueError):
            pass

    # 7. Build the archive directory with a UTC timestamp.
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive_dir = a_root / f"micro_proof_pass_{timestamp}"
    archive_dir.mkdir(parents=True, exist_ok=True)

    # 8. Copy the three artifacts into the archive.
    files_archived: list[str] = []
    try:
        shutil.copy2(r_path, archive_dir / "demo_micro_execution_receipt.json")
        files_archived.append("demo_micro_execution_receipt.json")
    except Exception as e:
        return _blocked(f"RECEIPT_COPY_FAILED: {e}", archive_dir=str(archive_dir))

    try:
        shutil.copy2(d_path, archive_dir / "latest_receipt_diagnostic.json")
        files_archived.append("latest_receipt_diagnostic.json")
    except Exception as e:
        return _blocked(f"DIAGNOSTIC_COPY_FAILED: {e}", archive_dir=str(archive_dir))

    try:
        shutil.copy2(f_path, archive_dir / "post_trade_forensics.json")
        files_archived.append("post_trade_forensics.json")
    except Exception as e:
        return _blocked(f"FORENSICS_COPY_FAILED: {e}", archive_dir=str(archive_dir))

    # 9. Generate micro_proof_summary.json + .md.
    summary = _build_summary(receipt, diagnostic, forensics, archive_dir, files_archived)
    json_path = archive_dir / "micro_proof_summary.json"
    md_path = archive_dir / "micro_proof_summary.md"
    try:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, default=str, ensure_ascii=False)
        md_text = _build_summary_md(summary)
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md_text)
    except Exception as e:
        return _blocked(f"SUMMARY_WRITE_FAILED: {e}", archive_dir=str(archive_dir))

    return {
        "timestamp_utc": summary["timestamp_utc"],
        "verdict": MICRO_PROOF_ARCHIVED,
        "archive_dir": str(archive_dir),
        "files_archived": files_archived,
        "json_path": str(json_path),
        "md_path": str(md_path),
        "forensics_verdict": forensics_verdict,
        "ok_checks": [
            "Receipt loaded",
            "Diagnostic loaded",
            "Forensics loaded",
            f"Forensics verdict == {REQUIRED_FORENSICS_VERDICT}",
            "fallback_used == False",
            "open_positions_count == 0",
            "Archive directory created",
            "Artifacts copied",
            "Summary JSON + MD written",
        ],
        "blockers": [],
        "warnings": [],
        "safety": dict(SAFETY_FINGERPRINT),
    }


def main() -> int:
    print("=" * 70)
    print("  TITAN XAU AI - Archive MICRO_PROOF_PASS (Sprint 9.9.3.45.9)")
    print("=" * 70)
    result = run_archive()
    print(f"\n  Verdict: {result['verdict']}")
    if result.get("archive_dir"):
        print(f"  Archive dir: {result['archive_dir']}")
        print(f"  Files archived: {result.get('files_archived', [])}")
        print(f"  Summary JSON: {result.get('json_path')}")
        print(f"  Summary MD:   {result.get('md_path')}")
    if result.get("blockers"):
        print("\n  Blockers:")
        for b in result["blockers"]:
            print(f"    - {b}")
    print(
        f"\n  Safety: order_send_called={result['safety']['order_send_called']}, "
        f"position_modified={result['safety']['position_modified']}, "
        f"no_martingale={result['safety']['no_martingale']}"
    )
    print("\n" + "=" * 70)
    return 0 if result["verdict"] == MICRO_PROOF_ARCHIVED else 1


if __name__ == "__main__":
    sys.exit(main())
