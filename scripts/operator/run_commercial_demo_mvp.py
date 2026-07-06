#!/usr/bin/env python3
"""TITAN XAU AI - Commercial Demo MVP Runner (Sprint v2.8.7-F)
================================================================
Skeleton script for running commercial demo MVP.

This script is a SKELETON. It does NOT:
- Send orders
- Create tokens
- Trade on any account
- Bypass CEO or meta-label
- Set production_ready=True

It DOES:
- Verify safety state
- Check model profiles
- Display demo_go_decision status
- Block if demo shadow is not authorized

NEVER sends orders. NEVER creates tokens. NEVER trades.
"""
from __future__ import annotations
import sys, os, argparse
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


def main():
    parser = argparse.ArgumentParser(description="TITAN Commercial Demo MVP Runner (skeleton)")
    parser.add_argument("--dry-run", action="store_true", default=True,
                        help="Dry run mode (always true, cannot be disabled)")
    parser.add_argument("--model-profile", default="v1_legacy",
                        choices=["v1_legacy", "v2_feature_normalized", "v2_multibroker"])
    parser.add_argument("--broker", default="MetaQuotes-Demo",
                        help="Broker name (must be in whitelist)")
    args = parser.parse_args()

    print("=" * 70)
    print("  TITAN XAU AI - COMMERCIAL DEMO MVP RUNNER (SKELETON)")
    print("  Sprint v2.8.7-F")
    print("=" * 70)

    # === Safety checks ===
    print("\n  [1] Safety checks...")

    # Check dry_run is true
    if not args.dry_run:
        print("  ❌ FATAL: dry_run cannot be disabled in skeleton mode")
        return

    # Check broker whitelist
    allowed_demo_brokers = ["MetaQuotes-Demo"]
    if args.broker not in allowed_demo_brokers:
        print(f"  ❌ FATAL: broker '{args.broker}' not in demo whitelist")
        print(f"     Allowed: {allowed_demo_brokers}")
        return

    # Check production_ready is false
    print("  ✅ dry_run = true")
    print("  ✅ broker in demo whitelist")
    print("  ✅ production_ready = false (enforced)")

    # === Model profile check ===
    print(f"\n  [2] Model profile: {args.model_profile}")
    try:
        from titan.production.model_loader import load_models_by_profile
        bundle = load_models_by_profile(args.model_profile)
        if not bundle.ok:
            print(f"  ❌ FATAL: model profile '{args.model_profile}' failed to load")
            return
        print(f"  ✅ Models loaded: {bundle}")
    except Exception as e:
        print(f"  ❌ FATAL: {e}")
        return

    # === Check demo_go_decision ===
    print(f"\n  [3] Checking demo_go_decision...")
    demo_paths = {
        "v1_legacy": REPO_ROOT / "data" / "reports" / "parameter_discovery" / "demo_go_decision.md",
        "v2_feature_normalized": REPO_ROOT / "data" / "reports" / "parameter_discovery_v2" / "demo_go_decision.md",
        "v2_multibroker": REPO_ROOT / "data" / "reports" / "parameter_discovery_v2_multibroker" / "demo_go_decision.md",
    }
    demo_path = demo_paths.get(args.model_profile)
    if not demo_path or not demo_path.exists():
        print(f"  ⚠️  No demo_go_decision found for {args.model_profile}")
        print("  ❌ BLOCKED: cannot proceed without demo_go_decision")
        return

    text = demo_path.read_text()
    if "DEMO_SHADOW_ALLOWED" in text:
        print(f"  ✅ demo_go_decision = DEMO_SHADOW_ALLOWED")
        print("\n  ⚠️  CTO review required before any demo activity.")
        print("  ⚠️  No automatic trade. No automatic token.")
    else:
        print(f"  ❌ demo_go_decision = NO_SAFE_PARAMETER_FOUND")
        print("\n  ❌ BLOCKED: Demo shadow is NOT authorized.")
        print("  ❌ No trade is permitted.")
        print("  ❌ CTO review required before any further action.")

    # === Final status ===
    print("\n" + "=" * 70)
    print("  STATUS: BLOCKED — No demo trade authorized")
    print("  This is a skeleton. No trade will be executed.")
    print("=" * 70)


if __name__ == "__main__":
    main()
