#!/usr/bin/env python3
"""
TITAN XAU AI - 7-Day Demo Observation Controller (Sprint 9.9.3.42)
==================================================================

Controlled 7-day demo observation start controller.

Usage:
    python scripts/operator/start_7_day_demo_observation.py --check-only
    python scripts/operator/start_7_day_demo_observation.py --start

NEVER imports MetaTrader5.
NEVER sends orders.
NEVER runs DEMO_MICRO_EXECUTE.
NEVER runs raw_mt5_probe.

Default behavior is --check-only (safe refusal mode).
--start only proceeds if ALL gates pass.
"""
from __future__ import annotations
import argparse, json, re, subprocess, sys, uuid
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
OUTPUT_DIR = REPO_ROOT / "data" / "audit" / "observation_7day"

# Approved warnings for 7-day dry-run observation
APPROVED_WARNINGS = {
    "REGIME_GATE_WIRED_BUT_PLACEHOLDER_CONTEXT",
    "git_clean_hint",  # git dirty is non-blocking
    "virtualenv",      # venv not active is non-blocking
    "release_docs",    # optional docs missing is non-blocking
    "MetaQuotes-Demo verified",  # informational broker status
    "FundedNext Free Trial remains DO_NOT_USE",  # informational broker status
    "FBS-Demo remains REJECTED",  # informational broker status
    "operator must run execution locally",  # informational
}


def _git_head_short() -> str:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=10,
        )
        return r.stdout.strip() if r.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def _read_config_runtime() -> dict:
    """Read runtime config values from runtime.yaml."""
    config_path = REPO_ROOT / "config" / "runtime.yaml"
    if not config_path.exists():
        return {}
    content = config_path.read_text(encoding="utf-8")
    runtime_section = re.search(r"^runtime:\s*\n((?:\s+\S.*\n)*)", content, re.MULTILINE)
    if not runtime_section:
        return {}
    rt = runtime_section.group(1)
    dry_match = re.search(r"^\s*dry_run:\s*(\w+)", rt, re.MULTILINE)
    live_match = re.search(r"^\s*live_trading:\s*(\w+)", rt, re.MULTILINE)
    return {
        "dry_run": dry_match.group(1).lower() == "true" if dry_match else True,
        "live_trading": live_match.group(1).lower() == "true" if live_match else False,
    }


def _check_safe_path_exposure() -> list[str]:
    """Check if order_send/DEMO_MICRO_EXECUTE/raw_probe are reachable from safe paths."""
    issues = []
    safe_modules = [
        "titan/production/operator_control_console.py",
        "titan/production/first_run_wizard.py",
        "titan/production/broker_observation_gate.py",
        "titan/production/production_runtime_assembly.py",
        "scripts/operator/titan_operator.py",
        "scripts/operator/titan_first_run.py",
        "scripts/operator/start_7_day_demo_observation.py",
        "scripts/operator/run_daily_observation_scorecard.py",
        "scripts/operator/finalize_7_day_demo_observation.py",
    ]
    for rel in safe_modules:
        path = REPO_ROOT / rel
        if not path.exists():
            continue
        src = path.read_text(encoding="utf-8")
        code = re.sub(r'"""[\s\S]*?"""', '""', src)
        code = re.sub(r"'''[\s\S]*?'''", "''", code)
        code = re.sub(r'r"[^"]*"', '""', code)
        code = re.sub(r"r'[^']*'", "''", code)
        code = re.sub(r'"(?:[^"\\]|\\.)*"', '""', code)
        code = re.sub(r"'(?:[^'\\]|\\.)*'", "''", code)
        if re.search(r"\bmt5\.order_send\s*\(", code):
            issues.append(f"{rel} calls mt5.order_send")
        if re.search(r"(?<!['\"])\b(DEMO_MICRO_EXECUTE|run_demo_micro|execute_demo_micro)\s*\(", code):
            issues.append(f"{rel} calls DEMO_MICRO_EXECUTE")
        if re.search(r"(?<!['\"])\b(run_raw_probe|raw_mt5_probe)\s*\(", code):
            issues.append(f"{rel} calls raw_mt5_probe")
    return issues


def _filter_approved_warnings(warnings: list[str]) -> tuple[list[str], list[str]]:
    """Split warnings into approved and unapproved."""
    approved = []
    unapproved = []
    for w in warnings:
        is_approved = False
        for aw in APPROVED_WARNINGS:
            if aw.lower() in w.lower():
                is_approved = True
                break
        if is_approved:
            approved.append(w)
        else:
            unapproved.append(w)
    return approved, unapproved


def run_check_only() -> dict:
    """Run all checks and return results without starting observation."""
    from titan.production.broker_observation_gate import (
        BrokerObservationGate, ObservationBrokerVerdict,
    )
    from titan.production.production_runtime_assembly import (
        ProductionRuntimeAssembly, ProductionRuntimeMode,
    )

    session_id = str(uuid.uuid4())[:12]
    ts = datetime.now(timezone.utc).isoformat()
    head_short = _git_head_short()

    results = {
        "session_id": session_id,
        "timestamp_utc": ts,
        "repo_commit": head_short,
        "mode": "check_only",
        "checks": {},
        "blockers": [],
        "approved_warnings": [],
        "unapproved_warnings": [],
        "observation_status": "CHECK_ONLY",
        "next_operator_action": "",
    }

    # 1. Config checks
    config = _read_config_runtime()
    results["checks"]["dry_run"] = config.get("dry_run", True)
    results["checks"]["live_trading"] = config.get("live_trading", False)

    if not config.get("dry_run", True):
        results["blockers"].append("dry_run=false in runtime.yaml — must be true")
    if config.get("live_trading", False):
        results["blockers"].append("live_trading=true in runtime.yaml — must be false")

    # 2. Broker gate check
    gate = BrokerObservationGate()
    # For controlled 7-day observation, broker must be MetaQuotes-Demo
    broker_result = gate.evaluate(broker_name="MetaQuotes-Demo")
    results["checks"]["broker_gate_verdict"] = broker_result.verdict.value
    results["checks"]["broker_name"] = broker_result.broker_name
    results["checks"]["broker_observation_eligible"] = broker_result.observation_eligible
    results["checks"]["broker_operator_message"] = broker_result.reason

    if broker_result.verdict != ObservationBrokerVerdict.ALLOWED:
        results["blockers"].append(
            f"Broker gate verdict={broker_result.verdict.value}: {broker_result.reason}"
        )

    # Verify FundedNext, FBS, Exness, ICMarkets, unknown are blocked
    for blocked_broker in ["FundedNext Free Trial", "FBS-Demo", "Exness Demo", "ICMarkets Demo", "UnknownBroker"]:
        br = gate.evaluate(broker_name=blocked_broker)
        if br.verdict == ObservationBrokerVerdict.ALLOWED:
            results["blockers"].append(
                f"Broker {blocked_broker} should be blocked but got ALLOWED"
            )

    # 3. ProductionRuntimeAssembly check
    asm = ProductionRuntimeAssembly(mode=ProductionRuntimeMode.DRY_RUN)
    status = asm.build_status()
    results["checks"]["rc_verdict"] = status.verdict.value
    if status.blockers:
        results["blockers"].extend(status.blockers)
    # Collect warnings from assembly
    asm_warnings = list(status.warnings)

    # 4. CTO repo consistency audit
    try:
        import scripts.audit.cto_repo_consistency_audit as cto_audit
        cto_result = cto_audit.write_report()
        with open(cto_result["json_path"]) as f:
            cto_data = json.load(f)
        results["checks"]["cto_verdict"] = cto_data["verdict"]
        if cto_data["blockers"]:
            results["blockers"].extend(cto_data["blockers"])
        cto_warnings = cto_data.get("warnings", [])
    except Exception as e:
        results["checks"]["cto_verdict"] = "SKIP"
        cto_warnings = [f"CTO audit skipped: {e}"]

    # 5. Pre-observation acceptance audit
    try:
        import scripts.audit.pre_observation_acceptance_audit as pre_audit
        pre_result = pre_audit.write_report()
        with open(pre_result["json_path"]) as f:
            pre_data = json.load(f)
        results["checks"]["pre_observation_verdict"] = pre_data["verdict"]
        if pre_data["blockers"]:
            results["blockers"].extend(pre_data["blockers"])
        pre_warnings = pre_data.get("warnings", [])
    except Exception as e:
        results["checks"]["pre_observation_verdict"] = "SKIP"
        pre_warnings = [f"Pre-observation audit skipped: {e}"]

    # 6. Safe path exposure check
    exposure_issues = _check_safe_path_exposure()
    if exposure_issues:
        results["blockers"].extend(exposure_issues)

    # 7. Collect all warnings and filter approved
    all_warnings = asm_warnings + cto_warnings + pre_warnings
    approved, unapproved = _filter_approved_warnings(all_warnings)
    results["approved_warnings"] = approved
    results["unapproved_warnings"] = unapproved

    # Unapproved warnings are blockers for --start
    if unapproved:
        results["blockers"].extend([f"Unapproved warning: {w}" for w in unapproved])

    # 8. Determine observation status
    if results["blockers"]:
        results["observation_status"] = "BLOCKED"
        results["next_operator_action"] = "Resolve blockers before starting 7-day observation"
    elif results["unapproved_warnings"]:
        results["observation_status"] = "BLOCKED"
        results["next_operator_action"] = "Resolve unapproved warnings before starting"
    else:
        results["observation_status"] = "READY_TO_START"
        results["next_operator_action"] = (
            "All gates pass. Run with --start to begin 7-day observation. "
            "Then run daily scorecard every 24 hours."
        )

    return results


def run_start() -> dict:
    """Run check-only first, then start if all gates pass."""
    results = run_check_only()
    results["mode"] = "start"

    if results["blockers"]:
        results["observation_status"] = "START_REFUSED"
        results["next_operator_action"] = "START REFUSED — resolve blockers first"
        return results

    if results["unapproved_warnings"]:
        results["observation_status"] = "START_REFUSED"
        results["next_operator_action"] = "START REFUSED — resolve unapproved warnings first"
        return results

    # All gates pass — "start" observation session
    results["observation_status"] = "STARTED"
    results["start_timestamp_utc"] = datetime.now(timezone.utc).isoformat()
    results["next_operator_action"] = (
        "Observation session STARTED. Run daily scorecard every 24 hours: "
        "python scripts/operator/run_daily_observation_scorecard.py --day 1 --since-hours 24. "
        "After 7 days, finalize: python scripts/operator/finalize_7_day_demo_observation.py"
    )
    return results


def write_report(results: dict) -> dict:
    """Write session start report."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUTPUT_DIR / "observation_session_start.json"
    md_path = OUTPUT_DIR / "observation_session_start.md"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, default=str, ensure_ascii=False)

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# TITAN XAU AI - 7-Day Observation Session Start\n\n")
        f.write(f"**Session ID:** {results['session_id']}\n\n")
        f.write(f"**Timestamp:** {results['timestamp_utc']}\n\n")
        f.write(f"**Repo Commit:** `{results['repo_commit']}`\n\n")
        f.write(f"**Mode:** {results['mode']}\n\n")
        f.write(f"**Observation Status:** **{results['observation_status']}**\n\n")
        f.write("## Checks\n\n")
        f.write("| Check | Value |\n|---|---|\n")
        for k, v in results["checks"].items():
            f.write(f"| {k} | {v} |\n")
        f.write(f"\n## Dry Run: {results['checks'].get('dry_run', 'N/A')}\n\n")
        f.write(f"## Live Trading: {results['checks'].get('live_trading', 'N/A')}\n\n")
        f.write(f"## Broker Gate Verdict: {results['checks'].get('broker_gate_verdict', 'N/A')}\n\n")
        f.write(f"**Broker Operator Message:** {results['checks'].get('broker_operator_message', 'N/A')}\n\n")
        f.write(f"## CTO Audit Verdict: {results['checks'].get('cto_verdict', 'N/A')}\n\n")
        f.write(f"## Pre-Observation Verdict: {results['checks'].get('pre_observation_verdict', 'N/A')}\n\n")
        if results["approved_warnings"]:
            f.write("## Approved Warnings\n\n")
            for w in results["approved_warnings"]:
                f.write(f"- {w}\n")
            f.write("\n")
        if results["blockers"]:
            f.write("## Blockers\n\n")
            for b in results["blockers"]:
                f.write(f"- **{b}**\n")
            f.write("\n")
        if results.get("unapproved_warnings"):
            f.write("## Unapproved Warnings\n\n")
            for w in results["unapproved_warnings"]:
                f.write(f"- **{w}**\n")
            f.write("\n")
        f.write("## Next Operator Action\n\n")
        f.write(f"{results['next_operator_action']}\n\n")
        f.write("## Safety\n\n")
        f.write("- Live trading remains BLOCKED.\n")
        f.write("- Dry run only.\n")
        f.write("- MetaQuotes-Demo only for current controlled 7-day observation.\n")
        f.write("- No order_send, no DEMO_MICRO_EXECUTE, no raw_mt5_probe.\n")

    return {"json_path": str(json_path), "md_path": str(md_path)}


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="start_7_day_demo_observation",
        description="Controlled 7-day demo observation controller",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        default=True,
        help="Run all checks without starting (default)",
    )
    parser.add_argument(
        "--start",
        action="store_true",
        default=False,
        help="Start observation session if all gates pass",
    )
    args = parser.parse_args()

    print("=" * 70)
    print("  TITAN XAU AI - 7-Day Demo Observation Controller (Sprint 9.9.3.42)")
    print("=" * 70)

    if args.start:
        results = run_start()
    else:
        results = run_check_only()

    report = write_report(results)

    print(f"\n  Session ID: {results['session_id']}")
    print(f"  Mode: {results['mode']}")
    print(f"  Status: {results['observation_status']}")
    print(f"  Blockers: {len(results['blockers'])}")
    print(f"  Approved Warnings: {len(results['approved_warnings'])}")
    if results.get("unapproved_warnings"):
        print(f"  Unapproved Warnings: {len(results['unapproved_warnings'])}")
    print(f"\n  JSON: {report['json_path']}")
    print(f"  MD:   {report['md_path']}")
    print(f"\n  Next: {results['next_operator_action']}")
    print("\n" + "=" * 70)

    return 0 if results["observation_status"] in ("READY_TO_START", "STARTED") else 1


if __name__ == "__main__":
    sys.exit(main())
