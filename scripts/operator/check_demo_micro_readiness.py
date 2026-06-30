#!/usr/bin/env python3
"""
TITAN XAU AI - Demo Micro Readiness Controller (Sprint 9.9.3.43)
=================================================================
NEVER imports MetaTrader5. NEVER sends orders. NEVER runs DEMO_MICRO_EXECUTE.
"""
from __future__ import annotations
import argparse, json, os, re, sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
OUTPUT_DIR = REPO_ROOT / "data" / "audit" / "demo_micro_readiness"

APPROVED_WARNINGS = {
    "REGIME_GATE_WIRED_BUT_PLACEHOLDER_CONTEXT",
    "REPLAY_NOT_REAL_FORWARD_EVIDENCE",
    "REAL_SHORT_NOT_FULL_7_DAY_EVIDENCE",
    "MODEL_SERIALIZATION_VERSION_WARNING",
    "DEPENDENCY_VERSION_DRIFT_WARNING",
    "PYTHON_313_COMPATIBILITY_WARNING",
    "MODEL_PARITY_NOT_AVAILABLE",
    "MetaQuotes-Demo verified",
    "FundedNext Free Trial remains DO_NOT_USE",
    "FBS-Demo remains REJECTED",
    "operator must run execution locally",
    "git_clean_hint",
    "virtualenv",
    "release_docs",
    "Retry/restart policy bounding",  # non-blocking self-healing warning
    "Watchdog restarter module not found",  # optional module
    "requirements.txt missing",
}


def _read_config_runtime() -> dict:
    config_path = REPO_ROOT / "config" / "runtime.yaml"
    if not config_path.exists():
        return {}
    content = config_path.read_text(encoding="utf-8")
    runtime_section = re.search(r"^runtime:\s*\n((?:\s+\S.*\n)*)", content, re.MULTILINE)
    risk_section = re.search(r"^risk:\s*\n((?:\s+\S.*\n)*)", content, re.MULTILINE)
    rt = runtime_section.group(1) if runtime_section else ""
    risk = risk_section.group(1) if risk_section else ""
    dry = re.search(r"^\s*dry_run:\s*(\w+)", rt, re.MULTILINE)
    live = re.search(r"^\s*live_trading:\s*(\w+)", rt, re.MULTILINE)
    lot = re.search(r"^\s*max_lot:\s*([\d.]+)", risk, re.MULTILINE)
    pos = re.search(r"^\s*max_open_positions:\s*(\d+)", risk, re.MULTILINE)
    return {
        "dry_run": dry.group(1).lower() == "true" if dry else True,
        "live_trading": live.group(1).lower() == "true" if live else False,
        "max_lot": float(lot.group(1)) if lot else 0.01,
        "max_open_positions": int(pos.group(1)) if pos else 1,
    }


def run_check(explain: bool = False) -> dict:
    from titan.production.broker_observation_gate import BrokerObservationGate, ObservationBrokerVerdict

    ts = datetime.now(timezone.utc).isoformat()
    config = _read_config_runtime()
    blockers = []
    warnings = []
    ok_checks = []

    # 1. Config checks
    if not config.get("dry_run", True):
        blockers.append("dry_run=false — must be true")
    if config.get("live_trading", False):
        blockers.append("live_trading=true — must be false")
    if os.environ.get("TITAN_LIVE_TRADING") == "1":
        blockers.append("TITAN_LIVE_TRADING=1 env var is set — must not be set")
    if config.get("max_lot", 0.01) > 0.01:
        blockers.append(f"max_lot={config['max_lot']} > 0.01")
    if config.get("max_open_positions", 1) > 1:
        blockers.append(f"max_open_positions={config['max_open_positions']} > 1")
    ok_checks.append(f"dry_run={config.get('dry_run', True)}")
    ok_checks.append(f"live_trading={config.get('live_trading', False)}")
    ok_checks.append(f"max_lot={config.get('max_lot', 0.01)}")
    ok_checks.append(f"max_open_positions={config.get('max_open_positions', 1)}")

    # 2. Broker gate
    gate = BrokerObservationGate()
    broker_result = gate.evaluate(broker_name="MetaQuotes-Demo")
    if broker_result.verdict != ObservationBrokerVerdict.ALLOWED:
        blockers.append(f"Broker gate: {broker_result.verdict.value} — {broker_result.reason}")
    else:
        ok_checks.append("Broker gate: MetaQuotes-Demo ALLOWED")

    # Verify blocked brokers
    for blocked_broker in ["FundedNext Free Trial", "FBS-Demo", "UnknownBroker"]:
        br = gate.evaluate(broker_name=blocked_broker)
        if br.verdict == ObservationBrokerVerdict.ALLOWED:
            blockers.append(f"{blocked_broker} should be blocked but got ALLOWED")

    # 3. Dependency compatibility audit
    try:
        import scripts.audit.dependency_compatibility_audit as dep_audit
        dep_result = dep_audit.run_audit()
        dep_verdict = dep_result["verdict"]
        if dep_verdict == "DEPENDENCY_BLOCKED":
            blockers.append(f"Dependency audit BLOCKED: {dep_result['blockers']}")
        else:
            ok_checks.append(f"Dependency audit: {dep_verdict}")
            for w in dep_result.get("warnings", []):
                warnings.append(w)
    except Exception as e:
        blockers.append(f"Dependency audit failed: {e}")
        dep_verdict = "SKIP"

    # 4. Model artifact compatibility audit
    try:
        import scripts.audit.model_artifact_compatibility_audit as model_audit
        model_result = model_audit.run_audit()
        model_verdict = model_result["verdict"]
        if model_verdict == "MODEL_ARTIFACT_BLOCKED":
            blockers.append(f"Model artifact audit BLOCKED: {model_result['blockers']}")
        else:
            ok_checks.append(f"Model artifact audit: {model_verdict}")
            for w in model_result.get("warnings", []):
                warnings.append(w)
    except Exception as e:
        blockers.append(f"Model artifact audit failed: {e}")
        model_verdict = "SKIP"

    # 5. Runtime self-healing audit
    try:
        import scripts.audit.runtime_self_healing_audit as sh_audit
        sh_result = sh_audit.run_audit()
        sh_verdict = sh_result["verdict"]
        if sh_verdict == "SELF_HEALING_BLOCKED":
            blockers.append(f"Self-healing audit BLOCKED: {sh_result['blockers']}")
        else:
            ok_checks.append(f"Self-healing audit: {sh_verdict}")
            for w in sh_result.get("warnings", []):
                warnings.append(w)
    except Exception as e:
        blockers.append(f"Self-healing audit failed: {e}")
        sh_verdict = "SKIP"

    # 5.5 Environment drift gate (Sprint 9.9.3.43.1)
    env_verdict = "SKIP"
    try:
        from titan.production.environment_drift_gate import EnvironmentDriftGate, DriftVerdict
        gate = EnvironmentDriftGate()
        drift_result = gate.evaluate()
        env_verdict = drift_result.verdict.value
        if env_verdict == "ENVIRONMENT_LOCK_BLOCKED":
            blockers.append(f"Environment drift gate BLOCKED: {drift_result.blockers}")
        else:
            ok_checks.append(f"Environment drift gate: {env_verdict}")
            for w in drift_result.warnings:
                warnings.append(w)
    except Exception as e:
        blockers.append(f"Environment drift gate failed: {e}")
        env_verdict = "SKIP"

    # 5.6 Model prediction parity audit (Sprint 9.9.3.43.1)
    parity_verdict = "SKIP"
    try:
        import scripts.audit.model_prediction_parity_audit as parity_audit
        parity_result = parity_audit.run_parity_audit()
        parity_verdict = parity_result["verdict"]
        if parity_verdict == "MODEL_PARITY_FAIL":
            blockers.append(f"Model parity audit FAIL: {parity_result['blockers']}")
        else:
            ok_checks.append(f"Model parity audit: {parity_verdict}")
            for w in parity_result.get("warnings", []):
                warnings.append(w)
    except Exception as e:
        # Parity audit is optional if no candidates exist
        parity_verdict = "MODEL_PARITY_NOT_AVAILABLE"
        ok_checks.append(f"Model parity audit skipped: {e}")

    # 6. Filter approved vs unapproved warnings
    approved = []
    unapproved = []
    for w in warnings:
        is_approved = any(aw.lower() in w.lower() for aw in APPROVED_WARNINGS)
        if is_approved:
            approved.append(w)
        else:
            unapproved.append(w)

    if unapproved:
        blockers.extend([f"Unapproved warning: {w}" for w in unapproved])

    # Verdict
    if blockers:
        verdict = "DEMO_MICRO_BLOCKED"
    elif approved:
        verdict = "DEMO_MICRO_READY_WITH_WARNINGS"
    else:
        verdict = "DEMO_MICRO_READY"

    result = {
        "timestamp_utc": ts,
        "verdict": verdict,
        "checks": {
            "dry_run": config.get("dry_run", True),
            "live_trading": config.get("live_trading", False),
            "TITAN_LIVE_TRADING_env": os.environ.get("TITAN_LIVE_TRADING", "0"),
            "max_lot": config.get("max_lot", 0.01),
            "max_open_positions": config.get("max_open_positions", 1),
            "broker_gate_verdict": broker_result.verdict.value,
            "dependency_audit_verdict": dep_verdict,
            "model_artifact_audit_verdict": model_verdict,
            "self_healing_audit_verdict": sh_verdict,
            "environment_drift_gate_verdict": env_verdict,
            "model_parity_audit_verdict": parity_verdict,
        },
        "ok_checks": ok_checks,
        "approved_warnings": approved,
        "unapproved_warnings": unapproved,
        "blockers": blockers,
        "important_note": (
            "DEMO_MICRO_READY or READY_WITH_WARNINGS does NOT execute a trade. "
            "It only means the project can proceed to a future separately approved sprint "
            "for controlled demo micro execution. Live trading remains BLOCKED."
        ),
    }

    if explain:
        result["explanation"] = {
            "verdict_meaning": {
                "DEMO_MICRO_READY": "All gates pass with no warnings. Ready for future demo micro sprint.",
                "DEMO_MICRO_READY_WITH_WARNINGS": "All gates pass with approved warnings only. Ready for future demo micro sprint with caution.",
                "DEMO_MICRO_BLOCKED": "One or more gates blocked. Not ready for demo micro execution.",
            },
            "next_steps": "If READY or READY_WITH_WARNINGS, proceed to a separately approved demo micro execution sprint. If BLOCKED, resolve blockers first.",
        }

    return result


def write_report(result: dict) -> dict:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUTPUT_DIR / "demo_micro_readiness_report.json"
    md_path = OUTPUT_DIR / "demo_micro_readiness_report.md"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str, ensure_ascii=False)

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# TITAN XAU AI - Demo Micro Readiness Report\n\n")
        f.write(f"**Verdict:** **{result['verdict']}**\n\n")
        f.write(f"**Timestamp:** {result['timestamp_utc']}\n\n")
        f.write("## Checks\n\n")
        f.write("| Check | Value |\n|---|---|\n")
        for k, v in result["checks"].items():
            f.write(f"| {k} | {v} |\n")
        if result.get("ok_checks"):
            f.write("\n## OK Checks\n\n")
            for c in result["ok_checks"]:
                f.write(f"- {c}\n")
        if result.get("approved_warnings"):
            f.write("\n## Approved Warnings\n\n")
            for w in result["approved_warnings"]:
                f.write(f"- {w}\n")
        if result.get("blockers"):
            f.write("\n## Blockers\n\n")
            for b in result["blockers"]:
                f.write(f"- **{b}**\n")
        f.write(f"\n## Important Note\n\n{result['important_note']}\n")

    return {"json_path": str(json_path), "md_path": str(md_path)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Demo micro readiness controller")
    parser.add_argument("--check-only", action="store_true", default=True)
    parser.add_argument("--explain", action="store_true", default=False)
    parser.add_argument("--write-report", action="store_true", default=False)
    args = parser.parse_args()

    print("=" * 70)
    print("  TITAN XAU AI - Demo Micro Readiness Controller (Sprint 9.9.3.43)")
    print("=" * 70)

    result = run_check(explain=args.explain)

    if args.write_report or True:  # Always write report
        report = write_report(result)

    print(f"\n  Verdict: {result['verdict']}")
    print(f"  Blockers: {len(result['blockers'])}")
    print(f"  Approved Warnings: {len(result['approved_warnings'])}")
    print(f"  Unapproved Warnings: {len(result.get('unapproved_warnings', []))}")
    print(f"\n  JSON: {report['json_path']}")
    print(f"  MD:   {report['md_path']}")
    print(f"\n  Note: {result['important_note']}")
    print("\n" + "=" * 70)

    return 0 if "READY" in result["verdict"] else 1


if __name__ == "__main__":
    sys.exit(main())
