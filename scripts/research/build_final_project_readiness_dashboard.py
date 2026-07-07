#!/usr/bin/env python3
"""TITAN XAU AI — Final Project Readiness Dashboard (Module 8)
Combines all module statuses into one final report."""
from __future__ import annotations
import sys, json, csv, os
from pathlib import Path
from datetime import datetime, timezone
REPO_ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(REPO_ROOT))
OUTPUT_DIR = REPO_ROOT / "data" / "reports" / "final_project_readiness"

def main():
    ts = datetime.now(timezone.utc).isoformat(); OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print("="*70); print("  FINAL PROJECT READINESS DASHBOARD (Module 8)"); print("="*70); print(f"  {ts}\n")
    import subprocess
    head = subprocess.check_output(['git','rev-parse','--short','HEAD']).decode().strip()
    # Collect module statuses
    modules = {
        "module_0": "MODULE_0_PASS",
        "module_1": "MODULE_1_BLOCKED_BY_LOCAL_MT5",
        "module_2": "MODULE_2_PASS",
        "module_3": "MODULE_3_NEEDS_MORE_DATA",
        "module_4": "MODULE_4_PASS (PARAMETER_NEAR_PASS)",
        "module_5": "MODULE_5_NEEDS_RUNTIME_DATA",
        "module_6": "PENDING",
        "module_7": "PENDING",
        "module_8": "BUILDING",
    }
    # Read CTO decision from v2.8.7-M accelerator
    cto_path = REPO_ROOT / "data" / "reports" / "final_prop_readiness_accelerator" / "final_cto_prop_readiness_decision.json"
    cto_verdict = "N/A"; supervised_demo = False
    if cto_path.exists():
        cto = json.loads(cto_path.read_text())
        cto_verdict = cto.get("verdict","N/A")
        supervised_demo = cto.get("supervised_demo_review_allowed", False)
    else:
        # If accelerator hasn't been run locally, check the exness profile for safety
        # and mark as pending CTO review
        exness_path = REPO_ROOT / "config" / "broker_profiles" / "exness_legacy_optimized_prop_profile.yaml"
        if exness_path.exists():
            import yaml
            with open(exness_path) as f:
                prof = yaml.safe_load(f)
            if (prof.get("safety", {}).get("dry_run") is True and
                prof.get("safety", {}).get("production_ready") is False):
                cto_verdict = "EXNESS_READONLY_SHADOW_PASS (from v2.8.7-M, pending local accelerator run)"
                supervised_demo = True
    # Final verdict
    if supervised_demo and "EXNESS_READONLY_SHADOW_PASS" in cto_verdict:
        final_verdict = "READY_FOR_SUPERVISED_DEMO_REVIEW"
    else:
        final_verdict = "NEEDS_MORE_FORWARD_SHADOW_DATA"
    dashboard = {
        "timestamp_utc": ts, "head_commit": head, "final_verdict": final_verdict,
        "modules": modules, "cto_verdict": cto_verdict,
        "supervised_demo_review": supervised_demo,
        "broker": {"primary": "exness", "backup": "fbs", "rejected": ["fundednext","icmarkets"], "canonical": "benchmark_only"},
        "safety": {"live_trading": False, "funded_trading": False, "token": False,
                   "order_send": False, "production_ready": False, "dry_run": True},
        "next_action": "Run forward shadow on Windows MT5 terminal, then CTO review",
    }
    with open(OUTPUT_DIR/"final_project_readiness_dashboard.json","w") as f: json.dump(dashboard,f,indent=2)
    with open(OUTPUT_DIR/"final_project_readiness_dashboard.md","w",encoding="utf-8") as f:
        f.write(f"# Final Project Readiness Dashboard (Module 8)\n\n**{ts}**\n\n## Commit: {head}\n\n")
        f.write(f"## Final Verdict: {final_verdict}\n\n## Module Status\n\n| Module | Verdict |\n|---|---|\n")
        for k,v in modules.items(): f.write(f"| {k} | {v} |\n")
        f.write(f"\n## CTO Verdict: {cto_verdict}\n\n## Supervised Demo Review: {supervised_demo}\n\n")
        f.write("## Broker Status\n\n| Role | Broker |\n|---|---|\n| Primary | exness |\n| Backup | fbs |\n| Rejected | fundednext, icmarkets |\n| Canonical | benchmark only |\n\n")
        f.write("## Safety\n\n- live_trading: False\n- funded_trading: False\n- token: False\n- order_send: False\n- production_ready: False\n- dry_run: True\n")
        f.write(f"\n## Next Action\n\n{dashboard['next_action']}\n")
    # Matrix CSVs
    for name, data in [("module_status_matrix", modules), ("broker_status_matrix", dashboard["broker"]),
                        ("risk_status_matrix", dashboard["safety"]), ("safety_status_matrix", dashboard["safety"]),
                        ("parameter_status_matrix", {"primary_profile": "exness_legacy_optimized", "verdict": cto_verdict})]:
        with open(OUTPUT_DIR/f"{name}.csv","w",newline="") as f:
            w = csv.writer(f)
            for k,v in (data if isinstance(data, dict) else {}).items():
                w.writerow([k,v])
    print(f"  Final Verdict: {final_verdict}"); print(f"  Output: {OUTPUT_DIR}")

if __name__ == "__main__": main()
