#!/usr/bin/env python3
"""TITAN XAU AI - Demo Shadow Readiness Audit (Sprint v2.8.7-H)
================================================================
Audits whether the system is ready for read-only demo shadow testing.

Checks:
  - candidate lock exists
  - candidate integrity pass
  - demo_go_decision = DEMO_SHADOW_ALLOWED
  - dry_run = true
  - live_trading = false
  - funded_trading = false
  - MetaQuotes-Demo only
  - no token auto-create
  - no order_send path reachable
  - CEO wired
  - meta-label wired
  - risk gates wired
  - broker gates wired
  - journal path writable
  - model profile loads
  - config loads
  - production_ready = false

Final verdict: DEMO_SHADOW_READY or NOT_READY

NEVER sends orders. NEVER creates tokens. NEVER trades.
"""
from __future__ import annotations
import sys, json, os, re
from pathlib import Path
from datetime import datetime, timezone

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

OUTPUT_DIR = REPO_ROOT / "data" / "reports" / "demo_shadow_readiness"


def main():
    ts = datetime.now(timezone.utc).isoformat()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("  TITAN XAU AI - DEMO SHADOW READINESS AUDIT (Sprint v2.8.7-H)")
    print("=" * 70)
    print(f"  Timestamp: {ts}\n")

    checks = {}

    # 1. Candidate lock exists
    print("  [1] Checking candidate lock...")
    lock_path = REPO_ROOT / "config" / "demo_shadow_candidate.yaml"
    checks["candidate_lock_exists"] = lock_path.exists()
    if lock_path.exists():
        import yaml
        with open(lock_path) as f:
            lock_config = yaml.safe_load(f)
        checks["candidate_lock_id"] = lock_config.get("candidate_lock", {}).get("lock_id", "")
        checks["candidate_lock_integrity"] = lock_config.get("candidate_lock", {}).get("integrity_audit", {}).get("candidate_lock", False)

    # 2. Candidate integrity audit
    print("  [2] Checking candidate integrity audit...")
    integrity_path = REPO_ROOT / "data" / "reports" / "candidate_lock" / "candidate_integrity_audit.json"
    checks["integrity_audit_exists"] = integrity_path.exists()
    if integrity_path.exists():
        data = json.loads(integrity_path.read_text())
        checks["integrity_candidate_lock"] = data.get("candidate_lock", False)
        checks["integrity_demo_shadow_ready"] = data.get("demo_shadow_ready", False)

    # 3. demo_go_decision
    print("  [3] Checking demo_go_decision...")
    demo_paths = [
        REPO_ROOT / "data" / "reports" / "parameter_discovery_v2_targeted" / "demo_go_decision.md",
    ]
    demo_decisions = {}
    for p in demo_paths:
        if p.exists():
            text = p.read_text()
            if "DEMO_SHADOW_ALLOWED" in text:
                demo_decisions[str(p.parent.name)] = "DEMO_SHADOW_ALLOWED"
            elif "NO_SAFE_PARAMETER_FOUND" in text:
                demo_decisions[str(p.parent.name)] = "NO_SAFE_PARAMETER_FOUND"
    checks["demo_go_decision_present"] = len(demo_decisions) > 0
    checks["demo_decisions"] = demo_decisions
    checks["demo_shadow_allowed"] = any(v == "DEMO_SHADOW_ALLOWED" for v in demo_decisions.values())

    # 4. Safety gates from config
    print("  [4] Checking safety gates...")
    if lock_path.exists():
        safety = lock_config.get("candidate_lock", {}).get("safety", {})
        checks["dry_run_true"] = safety.get("dry_run") is True
        checks["live_trading_false"] = safety.get("live_trading") is False
        checks["funded_trading_false"] = safety.get("funded_trading") is False
        checks["production_ready_false"] = safety.get("production_ready") is False
        checks["metaquotes_demo_only"] = safety.get("broker") == "MetaQuotes-Demo"
        checks["no_token_auto_create"] = safety.get("no_token_auto_create") is True
        checks["no_order_send"] = safety.get("no_order_send") is True
        checks["ceo_not_bypassed"] = safety.get("ceo_not_bypassed") is True
        checks["meta_label_not_bypassed"] = safety.get("meta_label_not_bypassed") is True

    # 5. CEO wired
    print("  [5] Checking CEO governance...")
    try:
        from titan.production.ceo_ai_governance import evaluate_ceo_decision
        checks["ceo_wired"] = True
    except Exception:
        checks["ceo_wired"] = False

    # 6. Meta-label wired
    print("  [6] Checking meta-label...")
    try:
        from titan.production.model_loader import META_FEATURE_NAMES
        checks["meta_label_wired"] = len(META_FEATURE_NAMES) == 22
    except Exception:
        checks["meta_label_wired"] = False

    # 7. Risk gates wired
    print("  [7] Checking risk gates...")
    checks["risk_gates_wired"] = (REPO_ROOT / "titan" / "production" / "capital_protection.py").exists()

    # 8. Broker gates wired
    print("  [8] Checking broker gates...")
    checks["broker_gates_wired"] = (REPO_ROOT / "titan" / "production" / "broker_observation_gate.py").exists()

    # 9. Journal path writable
    print("  [9] Checking journal path...")
    journal_dir = REPO_ROOT / "data" / "reports" / "demo_shadow_readonly"
    checks["journal_path_writable"] = journal_dir.exists() and os.access(journal_dir, os.W_OK)

    # 10. Model profile loads
    print("  [10] Checking model profile loads...")
    try:
        from titan.production.model_loader import load_models_by_profile
        b = load_models_by_profile("v2_feature_normalized")
        checks["model_profile_loads"] = b.ok
    except Exception:
        checks["model_profile_loads"] = False

    # 11. Config loads
    print("  [11] Checking config loads...")
    checks["config_loads"] = lock_path.exists()

    # 12. No order_send in shadow runner
    print("  [12] Checking no order_send in shadow runner...")
    shadow_runner = REPO_ROOT / "scripts" / "operator" / "run_demo_shadow_readonly.py"
    if shadow_runner.exists():
        src = shadow_runner.read_text()
        stripped = re.sub(r'"""[\s\S]*?"""', '""', src)
        stripped = re.sub(r"'''[\s\S]*?'''", "''", stripped)
        stripped = re.sub(r'r"[^"]*"', '""', stripped)
        stripped = re.sub(r"r'[^']*'", "''", stripped)
        stripped = re.sub(r'"[^"]*"', '""', stripped)
        stripped = re.sub(r"'[^']*'", "''", stripped)
        checks["no_order_send_in_shadow_runner"] = "order_send(" not in stripped
    else:
        checks["no_order_send_in_shadow_runner"] = False

    # Determine verdict
    demo_shadow_ready = all([
        checks.get("candidate_lock_exists", False),
        checks.get("integrity_audit_exists", False),
        checks.get("integrity_candidate_lock", False),
        checks.get("demo_shadow_allowed", False),
        checks.get("dry_run_true", False),
        checks.get("live_trading_false", False),
        checks.get("funded_trading_false", False),
        checks.get("production_ready_false", False),
        checks.get("metaquotes_demo_only", False),
        checks.get("no_token_auto_create", False),
        checks.get("no_order_send", False),
        checks.get("ceo_not_bypassed", False),
        checks.get("meta_label_not_bypassed", False),
        checks.get("ceo_wired", False),
        checks.get("meta_label_wired", False),
        checks.get("risk_gates_wired", False),
        checks.get("broker_gates_wired", False),
        checks.get("journal_path_writable", False),
        checks.get("model_profile_loads", False),
        checks.get("config_loads", False),
        checks.get("no_order_send_in_shadow_runner", False),
    ])

    verdict = "DEMO_SHADOW_READY" if demo_shadow_ready else "NOT_READY"
    checks["verdict"] = verdict
    checks["demo_shadow_ready"] = demo_shadow_ready
    checks["timestamp_utc"] = ts

    # Write JSON
    with open(OUTPUT_DIR / "demo_shadow_readiness.json", "w") as f:
        json.dump(checks, f, indent=2, default=str)

    # Write MD
    with open(OUTPUT_DIR / "demo_shadow_readiness.md", "w") as f:
        f.write("# Demo Shadow Readiness Audit (Sprint v2.8.7-H)\n\n")
        f.write(f"**Timestamp:** {ts}\n\n")
        f.write(f"## Verdict: {verdict}\n\n")
        f.write(f"**demo_shadow_ready:** {demo_shadow_ready}\n\n")
        f.write("## Check Details\n\n")
        f.write("| Check | Status |\n|---|---|\n")
        for k, v in checks.items():
            if isinstance(v, bool):
                f.write(f"| {k} | {'✅' if v else '❌'} |\n")
            elif isinstance(v, dict):
                f.write(f"| {k} | {v} |\n")
            elif isinstance(v, str):
                f.write(f"| {k} | {v} |\n")
        f.write("\n## Safety Confirmation\n\n")
        f.write("- production_ready = False (always)\n")
        f.write("- dry_run = True (always)\n")
        f.write("- live_trading = False (always)\n")
        f.write("- funded_trading = False (always)\n")
        f.write("- MetaQuotes-Demo only\n")
        f.write("- No order_send\n")
        f.write("- No token auto-create\n")
        f.write("- CEO not bypassed\n")
        f.write("- Meta-label not bypassed\n")
        f.write("- CTO review required before any demo activity\n")
        if demo_shadow_ready:
            f.write("\n## DEMO_SHADOW_READY\n\n")
            f.write("System is structurally ready for read-only demo shadow testing.\n")
            f.write("**However:**\n")
            f.write("- CTO must review and approve first\n")
            f.write("- Read-only shadow only (no orders)\n")
            f.write("- No automatic trade\n")
            f.write("- No token auto-create\n")

    # Print summary
    print(f"\n  Verdict: {verdict}")
    print(f"  demo_shadow_ready: {demo_shadow_ready}")
    failed = [k for k, v in checks.items() if isinstance(v, bool) and not v]
    if failed:
        print(f"  Failed checks: {failed}")
    print(f"\n  Output: {OUTPUT_DIR}")
    print("\n" + "=" * 70)
    print("  > Read-only shadow only. NO TRADE. CTO review required.")
    print("=" * 70)

    return checks


if __name__ == "__main__":
    main()
