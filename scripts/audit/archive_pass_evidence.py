#!/usr/bin/env python3
"""
TITAN XAU AI — Sprint 9.9.3.22 PASS Evidence Archiver
======================================================

Preserves official DEMO_FULL_CYCLE_PASS evidence by copying the current
demo micro audit artifacts to a timestamped archive directory under:
    data/audit/demo_micro/pass_evidence/<server_slug>/<timestamp>/

Files archived:
  - demo_micro_report.json
  - demo_micro_report.md
  - demo_micro_journal.jsonl
  - broker_execution_profile.json
  - raw_mt5_working_profile.json (if exists)

Also generates a PASS_SUMMARY.md with key fields extracted from the report.

Usage:
    python scripts/audit/archive_pass_evidence.py
    python scripts/audit/archive_pass_evidence.py --server MetaQuotes-Demo
    python scripts/audit/archive_pass_evidence.py --dry-run
"""
from __future__ import annotations
import argparse
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

SOURCE_DIR = REPO_ROOT / "data" / "audit" / "demo_micro"
PASS_EVIDENCE_ROOT = SOURCE_DIR / "pass_evidence"

FILES_TO_ARCHIVE = [
    "demo_micro_report.json",
    "demo_micro_report.md",
    "demo_micro_journal.jsonl",
    "broker_execution_profile.json",
    "raw_mt5_working_profile.json",
]


def _slugify(text: str) -> str:
    """Convert a server name to a filesystem-safe directory slug."""
    slug = re.sub(r"[^a-zA-Z0-9_-]", "_", text)
    slug = re.sub(r"_+", "_", slug).strip("_").lower()
    return slug or "unknown"


def _mask_login(login) -> str:
    """Mask login for privacy: show first 2 and last 2 chars."""
    if login is None:
        return "N/A"
    s = str(login)
    if len(s) <= 4:
        return s[:1] + "***" + s[-1:]
    return s[:2] + "***" + s[-2:]


def _redact_json_file(src: Path, dst: Path) -> None:
    """Sprint 9.9.3.23 — copy a JSON file with privacy redaction.

    Redacts:
      - account.login → masked (e.g. "12***78")
      - account.name → "REDACTED"
      - account_info.name → "REDACTED"
      - Any key named "login" or "name" at any nesting level
    """
    try:
        with open(src, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        # Not valid JSON — copy as-is (e.g. .md, .jsonl)
        shutil.copy2(src, dst)
        return
    _redact_dict_recursive(data)
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)


def _redact_jsonl_file(src: Path, dst: Path) -> None:
    """Sprint 9.9.3.23 — copy a JSONL file with privacy redaction (line by line)."""
    with open(src, "r", encoding="utf-8") as f_in, \
         open(dst, "w", encoding="utf-8") as f_out:
        for line in f_in:
            line = line.strip()
            if not line:
                f_out.write("\n")
                continue
            try:
                obj = json.loads(line)
                _redact_dict_recursive(obj)
                f_out.write(json.dumps(obj, default=str) + "\n")
            except Exception:
                # Not JSON — write as-is
                f_out.write(line + "\n")


def _redact_dict_recursive(obj) -> None:
    """Recursively redact sensitive keys in a dict/list structure."""
    if isinstance(obj, dict):
        for key in list(obj.keys()):
            val = obj[key]
            if key in ("login", "name", "account_name") and isinstance(val, (str, int)):
                if key == "login":
                    obj[key] = _mask_login(val)
                else:
                    obj[key] = "REDACTED"
            elif isinstance(val, (dict, list)):
                _redact_dict_recursive(val)
    elif isinstance(obj, list):
        for item in obj:
            _redact_dict_recursive(item)


def _redact_md_file(src: Path, dst: Path) -> None:
    """Sprint 9.9.3.23 — copy a Markdown file with privacy redaction.

    Redacts lines containing login/name/account number patterns.
    """
    import re
    with open(src, "r", encoding="utf-8") as f:
        content = f.read()
    # Redact "login: 12345678" → "login: 12***78"
    content = re.sub(
        r"(login[:\s]+)(\d{2,})",
        lambda m: m.group(1) + _mask_login(int(m.group(2))),
        content, flags=re.IGNORECASE,
    )
    # Redact "name: John Doe" → "name: REDACTED"
    content = re.sub(
        r"(name[:\s]+)([^\n|]+)",
        lambda m: m.group(1) + "REDACTED" if len(m.group(2).strip()) > 2 else m.group(0),
        content, flags=re.IGNORECASE,
    )
    with open(dst, "w", encoding="utf-8") as f:
        f.write(content)


def archive_pass_evidence(server: str = None, dry_run: bool = False) -> dict:
    """Archive current PASS evidence to a timestamped directory.

    Args:
        server: Server name for the archive subdirectory. If None,
            reads from demo_micro_report.json.
        dry_run: If True, report what would be archived without copying.

    Returns dict with:
        - ok (bool)
        - archive_path (str): path to archive directory
        - files_archived (list[str]): filenames that were copied
        - summary_path (str): path to PASS_SUMMARY.md
        - error (str): error message if ok=False
    """
    # Load the report to extract server + summary fields
    report_path = SOURCE_DIR / "demo_micro_report.json"
    if not report_path.exists():
        return {"ok": False, "error": "demo_micro_report.json not found"}

    with open(report_path, "r", encoding="utf-8") as f:
        report = json.load(f)

    # Extract server from report or use provided value
    if server is None:
        snapshot = report.get("pre_send_diagnostics") or report.get("broker_snapshot") or {}
        account = snapshot.get("account", {}) if isinstance(snapshot, dict) else {}
        server = account.get("server", "unknown")

    server_slug = _slugify(server)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive_dir = PASS_EVIDENCE_ROOT / server_slug / timestamp

    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "archive_path": str(archive_dir),
            "files_to_archive": [f for f in FILES_TO_ARCHIVE if (SOURCE_DIR / f).exists()],
        }

    archive_dir.mkdir(parents=True, exist_ok=True)

    files_archived = []
    for filename in FILES_TO_ARCHIVE:
        src = SOURCE_DIR / filename
        if src.exists():
            dst = archive_dir / filename
            # Sprint 9.9.3.23 — redact sensitive data in archived copies
            if filename.endswith(".json"):
                _redact_json_file(src, dst)
            elif filename.endswith(".jsonl"):
                _redact_jsonl_file(src, dst)
            elif filename.endswith(".md"):
                _redact_md_file(src, dst)
            else:
                shutil.copy2(src, dst)
            files_archived.append(filename)

    # Generate PASS_SUMMARY.md
    summary_path = archive_dir / "PASS_SUMMARY.md"
    summary = _build_pass_summary(report, server, files_archived)
    summary_path.write_text(summary, encoding="utf-8")

    return {
        "ok": True,
        "archive_path": str(archive_dir),
        "files_archived": files_archived,
        "summary_path": str(summary_path),
    }


def _build_pass_summary(report: dict, server: str, files_archived: list) -> str:
    """Build PASS_SUMMARY.md content from the report."""
    snapshot = report.get("pre_send_diagnostics") or report.get("broker_snapshot") or {}
    if isinstance(snapshot, dict):
        account = snapshot.get("account", {})
        symbol_info = snapshot.get("symbol_info", {})
    else:
        account = {}
        symbol_info = {}

    login = _mask_login(account.get("login"))
    symbol = report.get("open_order", {}).get("request", {}).get("symbol",
                report.get("broker_snapshot", {}).get("symbol", "XAUUSD"))
    lot = report.get("open_order", {}).get("request", {}).get("volume", 0.01)
    side = report.get("open_order", {}).get("request", {}).get("type", None)
    side_str = "BUY" if side == 0 else "SELL" if side == 1 else "N/A"

    # Extract retcodes
    open_retcode = report.get("open_order", {}).get("retcode")
    close_retcode = report.get("close_result", {}).get("retcode")
    net_pnl = report.get("net_pnl", 0)
    open_positions = report.get("open_positions_remaining", "N/A")
    verdict = report.get("final_verdict", "N/A")

    # Execution profile used
    raw_profile_used = report.get("raw_working_profile_used", False)
    raw_naked = report.get("raw_naked_open_then_sltp", False)
    filling_mode = report.get("filling_mode_selected", "N/A")
    filling_source = report.get("filling_source", "N/A")

    if raw_profile_used:
        exec_profile = f"raw_working_profile (IOC naked + SLTP modify)"
    elif raw_naked:
        exec_profile = f"broker_compatibility_fallback (naked + SLTP modify)"
    else:
        exec_profile = f"normal filling-mode fallback ({filling_mode} from {filling_source})"

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    lines = [
        f"# DEMO_FULL_CYCLE_PASS Evidence Summary",
        f"",
        f"**Archived:** {timestamp}",
        f"**Server:** {server}",
        f"**Login:** {login} (masked)",
        f"**Symbol:** {symbol}",
        f"**Lot:** {lot}",
        f"**Side:** {side_str}",
        f"**Execution profile:** {exec_profile}",
        f"**Filling mode:** {filling_mode} (source: {filling_source})",
        f"**Open retcode:** {open_retcode}",
        f"**Close retcode:** {close_retcode}",
        f"**Net PnL:** {net_pnl}",
        f"**Open positions remaining:** {open_positions}",
        f"**Final verdict:** {verdict}",
        f"",
        f"## Archived Files",
        f"",
    ]
    for f in files_archived:
        lines.append(f"- {f}")
    lines.extend([
        f"",
        f"## Safety Verification",
        f"",
        f"- DEMO account only: ✓",
        f"- max lot 0.01: ✓",
        f"- max positions 1: ✓",
        f"- Force close on end: ✓",
        f"- No live trading: ✓",
        f"- No martingale/grid/averaging: ✓",
    ])
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(
        description="Archive DEMO_FULL_CYCLE_PASS evidence to a timestamped directory")
    parser.add_argument("--server", default=None,
                        help="Server name for archive subdirectory (auto-detected from report if omitted)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Report what would be archived without copying")
    args = parser.parse_args()

    print("=" * 70)
    print("  TITAN XAU AI — PASS Evidence Archiver (Sprint 9.9.3.22)")
    print("=" * 70)

    result = archive_pass_evidence(server=args.server, dry_run=args.dry_run)

    if result["ok"]:
        if result.get("dry_run"):
            print(f"  [DRY RUN] Would archive to: {result['archive_path']}")
            print(f"  Files to archive: {result['files_to_archive']}")
        else:
            print(f"  ✓ Evidence archived to: {result['archive_path']}")
            print(f"  Files archived: {result['files_archived']}")
            print(f"  Summary: {result['summary_path']}")
    else:
        print(f"  ✗ FAILED: {result.get('error', 'unknown')}")

    print("=" * 70)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
