#!/usr/bin/env python3
"""
TITAN XAU AI - Windows RC Package Builder (Sprint 9.9.3.40)
=============================================================

Builds a local Release Candidate package folder (NOT an installer).

Output: dist/TITAN_XAU_AI_RC/

The package contains everything a non-technical operator needs to:
  - Run first-run wizard
  - Run operator console
  - Check RC status
  - Check safety status
  - Check broker registry
  - Run full audit
  - Read clear instructions

The package NEVER contains:
  - Raw evidence (demo_micro_journal.jsonl, raw_mt5_working_profile.json, etc.)
  - .env / API keys / account credentials
  - Live trading options
  - Market execution options
  - DEMO_MICRO_EXECUTE

NEVER imports MetaTrader5. NEVER sends orders.
"""
from __future__ import annotations
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = REPO_ROOT / "dist" / "TITAN_XAU_AI_RC"


# ─── Files to INCLUDE in the RC package ──────────────────────────────────
INCLUDE_FILES = [
    "run_titan_operator.bat",
    "run_titan_first_run.bat",
    "scripts/operator/titan_operator.py",
    "scripts/operator/titan_first_run.py",
    "docs/operator/operator_control_console.md",
    "docs/release/production_release_candidate_plan.md",
    "docs/release/windows_rc_package_guide.md",
    "docs/audit/master_integration_gap_report.md",
    "docs/audit/demo_micro_execution_registry.md",
    "docs/audit/demo_forward_observation_plan.md",
    "docs/audit/daily_demo_observation_checklist.md",
    "docs/audit/demo_micro_repeatability_metaquotes_redacted.md",
    "docs/audit/demo_micro_repeatability_metaquotes_redacted.json",
    "requirements.txt",
    "README.md",
    "first_run_check.py",
]

# ─── Files to EXPLICITLY EXCLUDE (defense in depth) ─────────────────────
EXCLUDE_PATTERNS = [
    "data/audit/demo_micro/pass_evidence/",
    "data/audit/demo_micro/demo_micro_journal.jsonl",
    "data/audit/demo_micro/demo_micro_repeatability_journal.jsonl",
    "data/audit/demo_micro/raw_mt5_working_profile.json",
    "data/audit/demo_micro/broker_execution_profile.json",
    ".env",
    ".env.local",
    "config/mt5_credentials.yaml",
    "data/credentials/",
    "data/private/",
]


def _is_excluded(rel_path: str) -> bool:
    """True if the given relative path matches an exclude pattern."""
    rel = rel_path.replace("\\", "/")
    for pattern in EXCLUDE_PATTERNS:
        if pattern in rel or rel.startswith(pattern):
            return True
    return False


def build_package() -> dict:
    """Build the RC package. Returns a dict with build summary."""
    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    included = []
    skipped_missing = []
    excluded = []

    for rel in INCLUDE_FILES:
        if _is_excluded(rel):
            excluded.append(rel)
            continue
        src = REPO_ROOT / rel
        if not src.exists():
            skipped_missing.append(rel)
            continue
        dst = OUTPUT_DIR / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        included.append(rel)

    # Write RELEASE_MANIFEST.json
    manifest = {
        "built_utc": datetime.now(timezone.utc).isoformat(),
        "package_name": "TITAN_XAU_AI_RC",
        "package_version": "9.9.3.40",
        "included_files": included,
        "skipped_missing": skipped_missing,
        "excluded_patterns": EXCLUDE_PATTERNS,
        "safety": {
            "live_trading_enabled": False,
            "market_execution_available": False,
            "demo_micro_execute_exposed": False,
            "raw_mt5_probe_exposed": False,
            "metatrader5_imported": False,
            "orders_sent": 0,
            "raw_evidence_included": False,
            "credentials_included": False,
            "env_file_included": False,
        },
        "general_warnings": [
            "This RC package is for non-technical operators.",
            "Live trading remains BLOCKED.",
            "Market execution is NOT available from this package.",
            "DEMO_MICRO_EXECUTE is NOT exposed.",
            "Raw evidence files are NOT included.",
            "Credentials and API keys are NOT included.",
            "Observation may begin only after the operator accepts the RC package.",
        ],
    }
    manifest_path = OUTPUT_DIR / "RELEASE_MANIFEST.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, default=str, ensure_ascii=False)

    # Write README_FIRST_RUN.md
    readme_path = OUTPUT_DIR / "README_FIRST_RUN.md"
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write("# TITAN XAU AI - First-Run Instructions\n\n")
        f.write(f"**Package Version:** 9.9.3.40\n\n")
        f.write(f"**Built:** {manifest['built_utc']}\n\n")
        f.write("## Quick Start\n\n")
        f.write("1. **Run the first-run wizard** (recommended first step):\n")
        f.write("   ```\n")
        f.write("   Double-click run_titan_first_run.bat\n")
        f.write("   ```\n\n")
        f.write("2. **Run the operator console** (after first-run wizard passes):\n")
        f.write("   ```\n")
        f.write("   Double-click run_titan_operator.bat\n")
        f.write("   ```\n\n")
        f.write("## What the Operator Console Can Do\n\n")
        f.write("- STATUS - Show current RC mode + safety state\n")
        f.write("- RC CHECK - Verify release candidate readiness\n")
        f.write("- SAFETY CHECK - Confirm all safety gates closed\n")
        f.write("- BROKER STATUS - Show broker registry\n")
        f.write("- OBSERVATION REPORT - Generate forward observation report\n")
        f.write("- DAILY SCORECARD - Generate daily observation scorecard\n")
        f.write("- FULL AUDIT - Run all safe reports\n")
        f.write("- HELP - Show available commands\n\n")
        f.write("## What the Operator Console CANNOT Do\n\n")
        f.write("- Live trading is BLOCKED\n")
        f.write("- Market execution is NOT available\n")
        f.write("- DEMO_MICRO_EXECUTE is NOT exposed\n")
        f.write("- Raw MT5 probe is NOT exposed\n")
        f.write("- Repeatability execution is NOT exposed\n")
        f.write("- Order send is NOT exposed\n")
        f.write("- Model retraining is NOT exposed\n")
        f.write("- HPO is NOT exposed\n\n")
        f.write("## Safety\n\n")
        f.write("- Live trading remains BLOCKED at all times.\n")
        f.write("- The package never asks for account password or API key.\n")
        f.write("- The package never imports MetaTrader5.\n")
        f.write("- The package never sends orders.\n")
        f.write("- Raw evidence files are NOT included in this package.\n\n")
        f.write("## Privacy\n\n")
        f.write("- No raw account data is included.\n")
        f.write("- No `.env` file is included.\n")
        f.write("- No credentials are included.\n")
        f.write("- All evidence in this package is already redacted.\n\n")
        f.write("## Observation\n\n")
        f.write("Observation may begin only after the operator accepts this RC package.\n")
        f.write("Run STATUS, SAFETY CHECK, and RC CHECK to verify readiness before observation.\n\n")
        f.write("## Documentation\n\n")
        f.write("- `docs/release/windows_rc_package_guide.md` - Full package guide\n")
        f.write("- `docs/release/production_release_candidate_plan.md` - RC plan\n")
        f.write("- `docs/audit/master_integration_gap_report.md` - Integration audit\n")
        f.write("- `docs/operator/operator_control_console.md` - Operator console docs\n\n")
        f.write("## Support\n\n")
        f.write("If the first-run wizard reports FAIL, contact your TITAN administrator\n")
        f.write("with the report at `data/audit/operator/first_run_wizard_report.md`.\n")

    # Write SAFETY_NOTICE.md
    safety_path = OUTPUT_DIR / "SAFETY_NOTICE.md"
    with open(safety_path, "w", encoding="utf-8") as f:
        f.write("# TITAN XAU AI - Safety Notice\n\n")
        f.write(f"**Package Version:** 9.9.3.40\n\n")
        f.write(f"**Built:** {manifest['built_utc']}\n\n")
        f.write("## Read Before Use\n\n")
        f.write("This Release Candidate (RC) package is **safe by design**.\n\n")
        f.write("### Hard Safety Invariants\n\n")
        f.write("1. **Live trading is BLOCKED.** The `live_trading` flag in `config/runtime.yaml` is `false` and the launcher refuses to start if it is `true` without explicit operator confirmation.\n")
        f.write("2. **Market execution is NOT available.** The operator console and first-run wizard do not expose any market execution command.\n")
        f.write("3. **DEMO_MICRO_EXECUTE is NOT exposed.** The operator console and first-run wizard do not invoke `demo_micro_full_cycle.py` or `demo_micro_repeatability.py`.\n")
        f.write("4. **Raw MT5 probe is NOT exposed.** The operator console and first-run wizard do not invoke `raw_mt5_probe.py`.\n")
        f.write("5. **Repeatability execution is NOT exposed.** The operator console and first-run wizard do not invoke repeatability runners.\n")
        f.write("6. **Order send is NOT exposed.** No safe module imports `MetaTrader5` or calls `mt5.order_send`.\n")
        f.write("7. **Model retraining is NOT exposed.** No retraining execution occurs from this package.\n")
        f.write("8. **HPO is NOT exposed.** No hyperparameter optimization occurs from this package.\n")
        f.write("9. **Max lot cap is 0.01.** Hard-coded in `TradeLoop` and `ExecutionIntent`.\n")
        f.write("10. **Max open positions cap is 1.** Hard-coded in `TradeLoop`.\n")
        f.write("11. **No martingale / grid / averaging / lot escalation.** Verified absent.\n")
        f.write("12. **FundedNext Free Trial remains BLOCKED.** Verified in `broker_compatibility_matrix.py`.\n")
        f.write("13. **FBS-Demo remains REJECTED.** Verified in `broker_compatibility_matrix.py`.\n")
        f.write("14. **MetaQuotes-Demo is the only verified broker for demo micro.** Verified in `broker_compatibility_matrix.py`.\n")
        f.write("\n")
        f.write("### Privacy\n\n")
        f.write("- No raw account data is included in this package.\n")
        f.write("- No `.env` file is included.\n")
        f.write("- No credentials are included.\n")
        f.write("- No API keys are included.\n")
        f.write("- No personal account/login/balance evidence is included.\n")
        f.write("- All evidence files in this package are already redacted.\n")
        f.write("\n")
        f.write("### Observation\n\n")
        f.write("Observation may begin only after the operator:\n")
        f.write("1. Runs the first-run wizard (`run_titan_first_run.bat`) and verifies PASS or WARN.\n")
        f.write("2. Runs the operator console (`run_titan_operator.bat`) and verifies:\n")
        f.write("   - STATUS shows `RC_READY` or `RC_READY_WITH_WARNINGS`\n")
        f.write("   - SAFETY CHECK shows `SAFETY_OK`\n")
        f.write("   - BROKER STATUS shows MetaQuotes-Demo verified and FundedNext blocked\n")
        f.write("3. Reviews the master integration audit report.\n")
        f.write("4. Explicitly accepts the RC package in writing.\n")
        f.write("\n")
        f.write("### Live Trading\n\n")
        f.write("**Live trading remains BLOCKED.**\n\n")
        f.write("There is no path in this package by which live trading can be enabled.\n")
        f.write("Enabling live trading requires source code modification outside this package\n")
        f.write("and explicit operator approval. This is by design.\n")
        f.write("\n")
        f.write("### Contact\n\n")
        f.write("If any safety check fails, contact your TITAN administrator before proceeding.\n")

    return {
        "output_dir": str(OUTPUT_DIR),
        "included_count": len(included),
        "skipped_missing": skipped_missing,
        "excluded_count": len(excluded),
        "manifest_path": str(manifest_path),
        "readme_path": str(readme_path),
        "safety_notice_path": str(safety_path),
    }


def main() -> int:
    print("=" * 70)
    print("  TITAN XAU AI - Windows RC Package Builder (Sprint 9.9.3.40)")
    print("=" * 70)
    result = build_package()
    print(f"\n  Output:       {result['output_dir']}")
    print(f"  Included:     {result['included_count']} files")
    print(f"  Skipped:      {len(result['skipped_missing'])} missing")
    if result["skipped_missing"]:
        for s in result["skipped_missing"]:
            print(f"    - {s}")
    print(f"  Excluded:     {result['excluded_count']} files (raw evidence / credentials)")
    print(f"\n  Manifest:     {result['manifest_path']}")
    print(f"  README:       {result['readme_path']}")
    print(f"  Safety notice:{result['safety_notice_path']}")
    print("\n" + "=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
