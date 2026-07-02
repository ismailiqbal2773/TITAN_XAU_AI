"""TITAN XAU AI - Selected Profile Resolver (Sprint 9.9.3.45.8.17 v2.7.4)
==========================================================================
Resolves the currently-selected profile using a consistent priority chain
across build-request, entry-gate audit, autonomous readiness audit, and
production closure audit.

Priority (highest first):
  1. CLI --prop-funded-profile (operator's explicit selection)
  2. CLI --account-profile
  3. managed_trade_report.json (account_profile or prop_funded_profile)
  4. demo_micro_execution_receipt.json (account_profile or prop_funded_profile)
  5. final_demo_proof_readiness_report.json (selected_profile)
  6. config default (retail_demo_micro)

Returns a dict with:
  - selected_profile: str
  - selected_profile_source: str
  - prop_funded_safe_active: bool
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Optional


def resolve_selected_profile(
    repo_root: Path,
    cli_prop_funded_profile: str = "",
    cli_account_profile: str = "",
) -> dict:
    """Resolve the currently-selected profile.

    NEVER sends orders. NEVER modifies positions. NEVER creates tokens.
    """
    audit_dir = repo_root / "data" / "audit" / "demo_micro_execution"
    runtime_dir = repo_root / "data" / "runtime"
    demo_readiness_dir = repo_root / "data" / "audit" / "demo_readiness"

    # 1. CLI --prop-funded-profile
    if cli_prop_funded_profile:
        return {
            "selected_profile": cli_prop_funded_profile,
            "selected_profile_source": "cli_prop_funded_profile",
            "prop_funded_safe_active": cli_prop_funded_profile == "prop_funded_safe",
        }

    # 2. CLI --account-profile
    if cli_account_profile:
        return {
            "selected_profile": cli_account_profile,
            "selected_profile_source": "cli_account_profile",
            "prop_funded_safe_active": cli_account_profile == "prop_funded_safe",
        }

    # 3. managed_trade_report.json
    # v2.7.4: Prefer prop_funded_profile over account_profile when both exist,
    # because prop_funded_profile is the CLI-selected safer profile.
    managed_path = audit_dir / "managed_trade_report.json"
    if managed_path.exists():
        try:
            with open(managed_path, "r", encoding="utf-8") as f:
                m = json.load(f)
            p = m.get("prop_funded_profile") or m.get("account_profile") or ""
            if p:
                return {
                    "selected_profile": p,
                    "selected_profile_source": "managed_trade_report",
                    "prop_funded_safe_active": p == "prop_funded_safe",
                }
        except Exception:
            pass

    # 4. latest receipt
    receipt_path = runtime_dir / "demo_micro_execution_receipt.json"
    if receipt_path.exists():
        try:
            with open(receipt_path, "r", encoding="utf-8") as f:
                r = json.load(f)
            p = r.get("prop_funded_profile") or r.get("account_profile") or ""
            if p:
                return {
                    "selected_profile": p,
                    "selected_profile_source": "latest_receipt",
                    "prop_funded_safe_active": p == "prop_funded_safe",
                }
        except Exception:
            pass

    # 5. final_demo_proof_readiness_report.json
    final_demo_path = demo_readiness_dir / "final_demo_proof_readiness_report.json"
    if final_demo_path.exists():
        try:
            with open(final_demo_path, "r", encoding="utf-8") as f:
                fd = json.load(f)
            p = fd.get("selected_profile") or fd.get("account_profile") or ""
            if p:
                return {
                    "selected_profile": p,
                    "selected_profile_source": "final_demo_readiness",
                    "prop_funded_safe_active": p == "prop_funded_safe",
                }
        except Exception:
            pass

    # 6. config default
    return {
        "selected_profile": "retail_demo_micro",
        "selected_profile_source": "config_default",
        "prop_funded_safe_active": False,
    }
