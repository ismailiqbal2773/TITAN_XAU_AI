"""
TITAN XAU AI — Sprint 9.7.1 Evidence Snapshot Registrar
=========================================================

Registers historical evidence snapshots into the evidence manifest.
Supports manual registration of known commits (30-min, 4-hour) and
auto-archiving of new validator runs.

Usage:
    python scripts/audit/register_evidence_snapshot.py --register-historical
    python scripts/audit/register_evidence_snapshot.py --register-latest
"""
from __future__ import annotations
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

MANIFEST_PATH = REPO_ROOT / "data" / "audit" / "evidence_registry" / "evidence_manifest.json"
RUNS_DIR = REPO_ROOT / "data" / "audit" / "sprint_9_6_3" / "runs"
LATEST_REPORT = REPO_ROOT / "data" / "audit" / "sprint_9_6_3" / "windows_mt5_extended_report.json"


def load_manifest() -> dict:
    if MANIFEST_PATH.exists():
        with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"runs": [], "version": "1.0"}


def save_manifest(manifest: dict):
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, default=str)


def classify_duration(duration_s: float) -> str:
    if duration_s >= 80000:
        return "24h"
    if duration_s >= 10000:
        return "4h"
    if duration_s >= 1500:
        return "30min"
    return "custom"


def normalize_bool(val, default=None):
    """Normalize a value to True/False/None — never use unsafe defaults."""
    if val is True or val is False:
        return val
    if val is None:
        return default
    if isinstance(val, str):
        if val.lower() in ("true", "1", "yes"):
            return True
        if val.lower() in ("false", "0", "no"):
            return False
    return default


def register_historical():
    """Register known historical evidence from operator-confirmed commits."""
    manifest = load_manifest()
    existing_ids = {r.get("run_id") for r in manifest["runs"]}

    historical_runs = [
        {
            "run_id": "historical_30min_077ae74",
            "source_commit": "077ae74",
            "duration_class": "30min",
            "duration_minutes": 30,
            "duration_actual_s": 1805.0,
            "verdict": "A",
            "platform": "Windows",
            "account_type": "DEMO",
            "dry_run_normalized": True,
            "live_trading_normalized": False,
            "env_live_trading": "0",
            "order_send_called": 0,
            "order_send_success": 0,
            "live_orders_executed": 0,
            "shutdown_clean": True,
            "runtime_ended_early": False,
            "heartbeat_count": 60,
            "signals_generated": 2,
            "decisions_generated": 2,
            "dry_run_orders": 2,
            "atr_evidence": True,
            "journal_integrity_ok": True,
            "timestamps_utc_ok": True,
            "cpu_status": "available",
            "memory_growth_kb": None,
            "created_utc": "2026-06-25T00:00:00+00:00",
            "registration_method": "historical_manual",
        },
        {
            "run_id": "historical_4h_9832e7f",
            "source_commit": "9832e7f",
            "duration_class": "4h",
            "duration_minutes": 240,
            "duration_actual_s": 14402.98,
            "verdict": "A",
            "platform": "Windows",
            "account_type": "DEMO",
            "dry_run_normalized": True,
            "live_trading_normalized": False,
            "env_live_trading": "0",
            "order_send_called": 0,
            "order_send_success": 0,
            "live_orders_executed": 0,
            "shutdown_clean": True,
            "runtime_ended_early": False,
            "heartbeat_count": 478,
            "signals_generated": 5,
            "decisions_generated": 5,
            "dry_run_orders": 5,
            "atr_evidence": True,
            "journal_integrity_ok": True,
            "timestamps_utc_ok": True,
            "cpu_status": "available",
            "memory_growth_kb": 4357.0,
            "created_utc": "2026-06-25T00:00:00+00:00",
            "registration_method": "historical_manual",
        },
    ]

    added = 0
    for run in historical_runs:
        if run["run_id"] not in existing_ids:
            manifest["runs"].append(run)
            added += 1
            print(f"  Registered: {run['run_id']} ({run['duration_class']}, verdict={run['verdict']})")
        else:
            print(f"  Already registered: {run['run_id']}")

    save_manifest(manifest)
    print(f"\n  Total runs in manifest: {len(manifest['runs'])}")
    print(f"  Added: {added}")
    return manifest


def register_latest():
    """Register the latest validator report if it exists."""
    if not LATEST_REPORT.exists():
        print("  No latest report found — skipping")
        return load_manifest()

    with open(LATEST_REPORT, "r", encoding="utf-8") as f:
        report = json.load(f)

    run_id = report.get("run_id", f"run_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}")
    duration_s = report.get("duration_actual_s", 0) or report.get("duration_actual_s", 0)
    duration_class = classify_duration(duration_s)

    # Normalized safety fields — derive from multiple sources, never use unsafe defaults
    dry_run = normalize_bool(report.get("dry_run"))
    if dry_run is None:
        # Check safety_audit or checks
        safety = report.get("safety_audit", {})
        if safety.get("dry_run") is not None:
            dry_run = safety["dry_run"]
        elif any("dry_run" in c.get("check", "") and c.get("status") == "PASS" for c in report.get("checks", [])):
            dry_run = True

    live_trading = normalize_bool(report.get("live_trading"))
    if live_trading is None:
        safety = report.get("safety_audit", {})
        if safety.get("live_trading") is not None:
            live_trading = safety["live_trading"]
        else:
            live_trading = False  # safe default — always false in dry_run

    shutdown_clean = normalize_bool(report.get("shutdown_clean"))
    if shutdown_clean is None:
        safety = report.get("safety_audit", {})
        if safety.get("shutdown_clean") is not None:
            shutdown_clean = safety["shutdown_clean"]

    entry = {
        "run_id": run_id,
        "source_commit": report.get("git_commit", "unknown"),
        "duration_class": duration_class,
        "duration_minutes": report.get("duration_minutes", 0),
        "duration_actual_s": duration_s,
        "verdict": report.get("verdict", "UNKNOWN"),
        "platform": report.get("platform", "UNKNOWN"),
        "account_type": report.get("account_type", report.get("safety_audit", {}).get("account_type", "UNKNOWN")),
        "dry_run_normalized": dry_run,
        "live_trading_normalized": live_trading,
        "env_live_trading": report.get("env_live_trading",
                                       report.get("safety_audit", {}).get("env_live_trading", "0")),
        "order_send_called": report.get("order_send_guard", {}).get("called_count", 0),
        "order_send_success": report.get("order_send_guard", {}).get("success_count", 0),
        "live_orders_executed": report.get("live_orders_executed", 0),
        "shutdown_clean": shutdown_clean,
        "runtime_ended_early": report.get("runtime_ended_early", None),
        "heartbeat_count": report.get("heartbeat_count", 0),
        "signals_generated": report.get("signals_generated", 0),
        "decisions_generated": report.get("decisions_generated", 0),
        "dry_run_orders": report.get("dry_run_orders", 0),
        "atr_evidence": report.get("atr_usage_count", 0) > 0,
        "journal_integrity_ok": len(report.get("journal_integrity_errors", [])) == 0,
        "timestamps_utc_ok": len(report.get("timestamp_errors", [])) == 0,
        "cpu_status": report.get("cpu_status", "unavailable"),
        "memory_growth_kb": report.get("memory_growth_kb"),
        "created_utc": report.get("start_utc", datetime.now(timezone.utc).isoformat()),
        "registration_method": "auto_latest",
    }

    # Archive report copy
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    with open(run_dir / "report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)

    manifest = load_manifest()
    existing_ids = {r.get("run_id") for r in manifest["runs"]}
    if run_id not in existing_ids:
        manifest["runs"].append(entry)
        save_manifest(manifest)
        print(f"  Registered: {run_id} ({duration_class}, verdict={entry['verdict']})")
    else:
        # Update existing entry
        for i, r in enumerate(manifest["runs"]):
            if r["run_id"] == run_id:
                manifest["runs"][i] = entry
                break
        save_manifest(manifest)
        print(f"  Updated: {run_id}")

    print(f"\n  Total runs in manifest: {len(manifest['runs'])}")
    return manifest


def main():
    parser = argparse.ArgumentParser(description="Register evidence snapshots")
    parser.add_argument("--register-historical", action="store_true",
                        help="Register known historical evidence (30-min, 4-hour)")
    parser.add_argument("--register-latest", action="store_true",
                        help="Register latest validator report")
    args = parser.parse_args()

    print("=" * 60)
    print("  TITAN Evidence Snapshot Registrar")
    print("=" * 60)

    if args.register_historical:
        register_historical()
    elif args.register_latest:
        register_latest()
    else:
        # Default: register both
        register_historical()
        register_latest()


if __name__ == "__main__":
    main()
