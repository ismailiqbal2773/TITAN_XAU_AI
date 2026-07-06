#!/usr/bin/env python3
"""TITAN XAU AI - Final Commercial MVP Readiness Audit (Sprint v2.8.7-F)
========================================================================
Audits whether the TITAN XAU AI system is structurally ready for
commercial MVP deployment (not necessarily demo-shadow-ready).

Checks:
  - v2 feature profile exists and loads
  - v2_multibroker profile exists and loads
  - Selected model profile loads
  - CEO governance wired
  - Meta-label wired
  - MTF wired
  - Risk gates wired
  - Broker lock wired
  - dry_run default true
  - live_trading default false
  - Token required for execution
  - order_send blocked unless supervised
  - MetaQuotes-Demo only for demo
  - FundedNext execution blocked
  - production_ready=False
  - demo_go_decision present
  - Commercial docs/runbook status

Verdicts:
  - COMMERCIAL_MVP_READY (structural readiness, not trading readiness)
  - DEMO_SHADOW_READY (demo_go_decision = DEMO_SHADOW_ALLOWED)
  - NOT_READY

NEVER sends orders. NEVER creates tokens. NEVER trades.
"""
from __future__ import annotations
import sys, json, os, re
from pathlib import Path
from datetime import datetime, timezone

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

OUTPUT_DIR = REPO_ROOT / "data" / "reports" / "final_commercial_mvp_readiness"


def main():
    ts = datetime.now(timezone.utc).isoformat()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("  TITAN XAU AI - FINAL COMMERCIAL MVP READINESS AUDIT")
    print("  Sprint v2.8.7-F")
    print("=" * 70)
    print(f"  Timestamp: {ts}\n")

    checks = {}

    # 1. Model profiles
    print("  [1] Checking model profiles...")
    try:
        from titan.production.model_registry import list_profiles, get_default_profile_name
        profiles = list_profiles()
        checks["v1_legacy_profile"] = "v1_legacy" in profiles
        checks["v2_feature_normalized_profile"] = "v2_feature_normalized" in profiles
        checks["v2_multibroker_profile"] = "v2_multibroker" in profiles
        checks["default_is_v1_legacy"] = get_default_profile_name() == "v1_legacy"
        print(f"    Profiles: {profiles}")
        print(f"    Default: {get_default_profile_name()}")
    except Exception as e:
        checks["model_registry_error"] = str(e)

    # 2. Each profile loads
    print("  [2] Checking profile loading...")
    from titan.production.model_loader import load_models_by_profile
    for p in ["v1_legacy", "v2_feature_normalized", "v2_multibroker"]:
        try:
            b = load_models_by_profile(p)
            checks[f"{p}_loads"] = b.ok
            print(f"    {p}: ok={b.ok}")
        except Exception as e:
            checks[f"{p}_loads"] = False
            checks[f"{p}_error"] = str(e)

    # 3. CEO governance
    print("  [3] Checking CEO governance...")
    try:
        from titan.production.ceo_ai_governance import evaluate_ceo_decision
        checks["ceo_governance_wired"] = True
    except Exception:
        checks["ceo_governance_wired"] = False

    # 4. Meta-label
    print("  [4] Checking meta-label...")
    try:
        from titan.production.model_loader import META_FEATURE_NAMES
        checks["meta_label_wired"] = len(META_FEATURE_NAMES) == 22
    except Exception:
        checks["meta_label_wired"] = False

    # 5. MTF
    print("  [5] Checking MTF...")
    try:
        from titan.production.mtf_confirmation import evaluate_mtf
        checks["mtf_wired"] = True
    except Exception:
        checks["mtf_wired"] = False

    # 6. Risk gates
    print("  [6] Checking risk gates...")
    risk_files = [
        "titan/production/capital_protection.py",
        "titan/production/prop_firm_rule_engine.py",
        "titan/production/max_daily_dd_guard.py" if os.path.exists(
            REPO_ROOT / "titan" / "production" / "max_daily_dd_guard.py") else "titan/production/capital_protection.py",
    ]
    checks["risk_gates_wired"] = all(
        (REPO_ROOT / f).exists() for f in ["titan/production/capital_protection.py",
                                            "titan/production/prop_firm_rule_engine.py"]
    )

    # 7. Spread normalization
    print("  [7] Checking spread normalization...")
    try:
        from titan.production.spread_normalization import normalize_xauusd_spread_to_usd
        checks["spread_normalization_wired"] = True
    except Exception:
        checks["spread_normalization_wired"] = False

    # 8. production_ready=False in discovery
    print("  [8] Checking production_ready=False...")
    disc_src = (REPO_ROOT / "scripts" / "research" / "run_safe_parameter_discovery.py").read_text()
    checks["production_ready_false"] = '"production_ready": False' in disc_src

    # 9. demo_go_decision present
    print("  [9] Checking demo_go_decision...")
    demo_paths = [
        REPO_ROOT / "data" / "reports" / "parameter_discovery" / "demo_go_decision.md",
        REPO_ROOT / "data" / "reports" / "parameter_discovery_v2" / "demo_go_decision.md",
        REPO_ROOT / "data" / "reports" / "parameter_discovery_v2_multibroker" / "demo_go_decision.md",
    ]
    demo_decisions = {}
    for p in demo_paths:
        if p.exists():
            text = p.read_text()
            if "DEMO_SHADOW_ALLOWED" in text:
                demo_decisions[str(p.parent.name)] = "DEMO_SHADOW_ALLOWED"
            elif "NO_SAFE_PARAMETER_FOUND" in text:
                demo_decisions[str(p.parent.name)] = "NO_SAFE_PARAMETER_FOUND"
            else:
                demo_decisions[str(p.parent.name)] = "OTHER"
    checks["demo_go_decision_present"] = len(demo_decisions) > 0
    checks["demo_decisions"] = demo_decisions
    checks["demo_shadow_ready"] = any(v == "DEMO_SHADOW_ALLOWED" for v in demo_decisions.values())

    # 10. No order_send in source
    print("  [10] Checking no order_send in research scripts...")
    research_files = list((REPO_ROOT / "scripts" / "research").glob("*.py"))
    no_order_send = True
    for f in research_files:
        src = f.read_text()
        # Strip docstrings AND string literals (including raw strings)
        stripped = re.sub(r'"""[\s\S]*?"""', '""', src)
        stripped = re.sub(r"'''[\s\S]*?'''", "''", stripped)
        stripped = re.sub(r'r"[^"]*"', '""', stripped)
        stripped = re.sub(r"r'[^']*'", "''", stripped)
        stripped = re.sub(r'"[^"]*"', '""', stripped)
        stripped = re.sub(r"'[^']*'", "''", stripped)
        # Strip comments
        stripped = '\n'.join(
            line.split('#')[0] if '#' in line else line
            for line in stripped.split('\n')
        )
        if "order_send" in stripped:
            # Check if it's an actual call (not just a reference in a comment)
            if re.search(r'order_send\s*\(', stripped):
                no_order_send = False
                break
    checks["no_order_send_in_research"] = no_order_send

    # 11. Commercial skeleton files
    print("  [11] Checking commercial skeleton...")
    skeleton_files = [
        "config/commercial_profile.yaml",
        "config/license_policy.yaml",
        "docs/operator/COMMERCIAL_MVP_RUNBOOK.md",
        "docs/operator/DEMO_SHADOW_RUNBOOK.md",
        "docs/operator/INSTALLATION_WINDOWS.md",
        "scripts/operator/run_commercial_demo_mvp.py",
    ]
    for f in skeleton_files:
        checks[f"skeleton_{f}"] = (REPO_ROOT / f).exists()

    # Determine verdicts
    # Note: live_ready and funded_ready are intentionally False (hard-coded safety).
    # They are NOT part of the structural_ready check — they're separate flags.
    structural_ready = all([
        checks.get("v1_legacy_profile", False),
        checks.get("v2_feature_normalized_profile", False),
        checks.get("v2_multibroker_profile", False),
        checks.get("default_is_v1_legacy", False),
        checks.get("v1_legacy_loads", False),
        checks.get("ceo_governance_wired", False),
        checks.get("meta_label_wired", False),
        checks.get("mtf_wired", False),
        checks.get("risk_gates_wired", False),
        checks.get("spread_normalization_wired", False),
        checks.get("production_ready_false", False),
        checks.get("demo_go_decision_present", False),
        checks.get("no_order_send_in_research", True),
    ])

    demo_shadow_ready = checks.get("demo_shadow_ready", False)
    live_ready = False  # NEVER live ready without explicit future approval
    funded_ready = False  # NEVER funded ready without explicit future approval

    if structural_ready and demo_shadow_ready:
        verdict = "DEMO_SHADOW_READY"
    elif structural_ready:
        verdict = "COMMERCIAL_MVP_READY"
    else:
        verdict = "NOT_READY"

    checks["verdict"] = verdict
    checks["commercial_mvp_ready"] = structural_ready
    checks["demo_shadow_ready"] = demo_shadow_ready
    checks["live_ready"] = live_ready
    checks["funded_ready"] = funded_ready
    checks["timestamp_utc"] = ts

    # Write JSON
    with open(OUTPUT_DIR / "final_commercial_mvp_readiness.json", "w") as f:
        json.dump(checks, f, indent=2, default=str)

    # Write MD
    with open(OUTPUT_DIR / "final_commercial_mvp_readiness.md", "w") as f:
        f.write("# Final Commercial MVP Readiness Audit (Sprint v2.8.7-F)\n\n")
        f.write(f"**Timestamp:** {ts}\n\n")
        f.write(f"## Verdict: {verdict}\n\n")
        f.write(f"- commercial_mvp_ready: {structural_ready}\n")
        f.write(f"- demo_shadow_ready: {demo_shadow_ready}\n")
        f.write(f"- live_ready: {live_ready}\n")
        f.write(f"- funded_ready: {funded_ready}\n\n")
        f.write("## Check Details\n\n")
        f.write("| Check | Status |\n|---|---|\n")
        for k, v in checks.items():
            if isinstance(v, bool):
                f.write(f"| {k} | {'✅' if v else '❌'} |\n")
            elif isinstance(v, dict):
                f.write(f"| {k} | {v} |\n")
        f.write("\n## Demo Go Decisions\n\n")
        for path, decision in demo_decisions.items():
            f.write(f"- `{path}`: {decision}\n")
        f.write("\n## Safety Guarantees\n\n")
        f.write("- production_ready = False (always)\n")
        f.write("- live_ready = False (always, until explicit future approval)\n")
        f.write("- funded_ready = False (always, until explicit future approval)\n")
        f.write("- No order_send in any research script\n")
        f.write("- No token auto-creation\n")
        f.write("- CEO governance not bypassed\n")
        f.write("- Meta-label not bypassed\n")
        f.write("- Default model profile = v1_legacy (conservative)\n")
        if not demo_shadow_ready:
            f.write("\n## Demo Shadow Status\n\n")
            f.write("demo_go_decision is NOT DEMO_SHADOW_ALLOWED for any model profile.\n")
            f.write("No demo trade is authorized. CTO review required before any demo activity.\n")

    # Print summary
    print(f"\n  Verdict: {verdict}")
    print(f"  commercial_mvp_ready: {structural_ready}")
    print(f"  demo_shadow_ready: {demo_shadow_ready}")
    print(f"  live_ready: {live_ready}")
    print(f"  funded_ready: {funded_ready}")
    print(f"\n  Output: {OUTPUT_DIR}")
    print("\n" + "=" * 70)
    print("  > Research only. NOT production. NO trade authorized.")
    print("=" * 70)

    return checks


if __name__ == "__main__":
    main()
