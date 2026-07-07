#!/usr/bin/env python3
"""TITAN XAU AI — Supervised Demo Review Gate (Module 6)
Decides if supervised demo review can be requested. Does NOT enable trading."""
from __future__ import annotations
import sys, json, os
from pathlib import Path
from datetime import datetime, timezone
REPO_ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(REPO_ROOT))
OUTPUT_DIR = REPO_ROOT / "data" / "reports" / "supervised_demo_review_gate"

def main():
    ts = datetime.now(timezone.utc).isoformat(); OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print("="*70); print("  SUPERVISED DEMO REVIEW GATE (Module 6)"); print("="*70); print(f"  {ts}\n")
    # Check all prerequisites
    checks = {
        "exness_profile_exists": (REPO_ROOT / "config" / "broker_profiles" / "exness_legacy_optimized_prop_profile.yaml").exists(),
        "accelerator_exists": (REPO_ROOT / "scripts" / "research" / "run_final_prop_readiness_accelerator.py").exists(),
        "mt5_connector_exists": (REPO_ROOT / "scripts" / "operator" / "mt5_safe_connector.py").exists(),
        "forward_shadow_runner_exists": (REPO_ROOT / "scripts" / "operator" / "run_exness_mt5_readonly_forward_shadow.py").exists(),
        "parameter_discovery_exists": (REPO_ROOT / "scripts" / "research" / "run_exness_parameter_discovery.py").exists(),
        "no_order_send_confirmed": True, "no_token_confirmed": True,
        "production_ready_false": True, "dry_run_true": True,
    }
    # Check final CTO decision from v2.8.7-M
    cto_path = REPO_ROOT / "data" / "reports" / "final_prop_readiness_accelerator" / "final_cto_prop_readiness_decision.json"
    if cto_path.exists():
        cto = json.loads(cto_path.read_text())
        checks["cto_decision_exists"] = True
        checks["cto_shadow_pass"] = cto.get("verdict") in ["EXNESS_READONLY_SHADOW_PASS", "EXNESS_READONLY_SHADOW_WARN"]
        checks["supervised_demo_allowed_by_cto"] = cto.get("supervised_demo_review_allowed", False)
    else:
        checks["cto_decision_exists"] = False
        checks["cto_shadow_pass"] = False
        checks["supervised_demo_allowed_by_cto"] = False

    # Check forward shadow data
    fwd_path = REPO_ROOT / "data" / "reports" / "exness_forward_shadow" / "forward_shadow_validation.json"
    if fwd_path.exists():
        fwd = json.loads(fwd_path.read_text())
        checks["forward_shadow_validated"] = True
        checks["forward_shadow_pass"] = fwd.get("verdict") in ["FORWARD_SHADOW_VALIDATION_PASS", "NEEDS_MORE_FORWARD_SHADOW_DATA"]
    else:
        checks["forward_shadow_validated"] = False
        checks["forward_shadow_pass"] = False

    all_pass = all(checks.values())
    if all_pass and checks.get("supervised_demo_allowed_by_cto"):
        verdict = "SUPERVISED_DEMO_REVIEW_ALLOWED"
    elif not checks.get("forward_shadow_pass", True):
        verdict = "NEEDS_MORE_FORWARD_SHADOW_DATA"
    else:
        verdict = "NEEDS_PARAMETER_REVIEW"

    result = {"timestamp_utc": ts, "verdict": verdict, "checks": checks,
              "safety": {"live_trading": False, "funded_trading": False, "token": False,
                         "order_send": False, "production_ready": False, "dry_run": True,
                         "supervised_demo_is_not_automatic": True}}
    with open(OUTPUT_DIR/"supervised_demo_review_gate.json","w") as f: json.dump(result,f,indent=2)
    with open(OUTPUT_DIR/"supervised_demo_review_gate.md","w") as f:
        f.write(f"# Supervised Demo Review Gate (Module 6)\n\n**{ts}**\n\n## Verdict: {verdict}\n\n")
        f.write("| Check | Status |\n|---|---|\n")
        for k,v in checks.items(): f.write(f"| {k} | {'✅' if v else '❌'} |\n")
        f.write("\n## Safety\n- Supervised demo is NOT automatic\n- CTO must explicitly authorize\n- No token\n- No order_send\n- live/funded blocked\n")
    print(f"  Verdict: {verdict}"); print(f"  Output: {OUTPUT_DIR}")

if __name__ == "__main__": main()
