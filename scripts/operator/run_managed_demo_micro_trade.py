#!/usr/bin/env python3
"""
TITAN XAU AI - Managed Demo Micro Trade Operator (Sprint 9.9.3.45.1)
=====================================================================
Orchestrates: gate check -> build request -> execute once -> monitor.
Z AI must NOT run --execute-and-monitor.
"""
from __future__ import annotations
import argparse, json, sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
OUTPUT_DIR = REPO_ROOT / "data" / "audit" / "demo_micro_execution"


def run_check_only() -> dict:
    ts = datetime.now(timezone.utc).isoformat()
    from titan.production.demo_micro_execution_gate import DemoMicroExecutionGate
    gate = DemoMicroExecutionGate()
    gate_result = gate.evaluate()
    return {
        "timestamp_utc": ts,
        "mode": "check_only",
        "verdict": "MANAGED_DEMO_MICRO_READY" if "PASS" in gate_result.verdict.value else "MANAGED_DEMO_MICRO_BLOCKED",
        "gate_verdict": gate_result.verdict.value,
        "gate_blockers": gate_result.blockers,
        "next_action": "Run --dry-arm to arm managed trade",
    }


def run_dry_arm() -> dict:
    result = run_check_only()
    result["mode"] = "dry_arm"
    result["armed"] = "PASS" in result.get("gate_verdict", "")
    result["next_action"] = "Run --build-request to generate executable order preview"
    return result


def run_build_request(direction: str = "BUY", entry_price: float = 2000.0,
                       sl: float = 0.0, tp: float = 0.0) -> dict:
    ts = datetime.now(timezone.utc).isoformat()
    from titan.production.demo_micro_order_builder import DemoMicroOrderBuilder
    builder = DemoMicroOrderBuilder()
    build_result = builder.build_preview(
        direction=direction, entry_price=entry_price, sl=sl, tp=tp,
        safe_fallback=False,
    )
    return {
        "timestamp_utc": ts,
        "mode": "build_request",
        "verdict": build_result["verdict"],
        "executable_status": build_result.get("executable_status"),
        "preview": build_result.get("preview"),
        "next_action": "If EXECUTABLE_WITH_PROTECTIVE_SL_TP, run --execute-and-monitor locally",
    }


def run_execute_and_monitor(args) -> dict:
    """Execute and monitor. Z AI must NOT run this."""
    required_flags = [
        getattr(args, "i_understand_demo_risk", False),
        getattr(args, "confirm_symbol", ""),
        getattr(args, "confirm_lot", 0.0),
        getattr(args, "confirm_broker", ""),
        getattr(args, "confirm_one_order_only", False),
        getattr(args, "confirm_not_live", False),
        getattr(args, "confirm_environment_locked", False),
        getattr(args, "confirm_model_parity_pass", False),
        getattr(args, "confirm_local_operator", False),
        getattr(args, "confirm_managed_trailing", False),
    ]
    if not all(required_flags):
        return {
            "mode": "execute_and_monitor",
            "verdict": "MANAGED_DEMO_MICRO_BLOCKED",
            "blockers": ["Missing required confirmation flags"],
            "important_note": "No order was sent. No mt5.order_send was called.",
        }

    # Token check
    from scripts.operator.create_local_operator_execution_token import load_and_validate_token
    token_result = load_and_validate_token()
    if not token_result["valid"]:
        return {
            "mode": "execute_and_monitor",
            "verdict": "MANAGED_DEMO_MICRO_BLOCKED",
            "blockers": [f"Token invalid: {token_result['reason']}"],
            "important_note": "No order was sent.",
        }

    # Gate check
    gate_result = run_check_only()
    if "BLOCKED" in gate_result["gate_verdict"]:
        return {
            "mode": "execute_and_monitor",
            "verdict": "MANAGED_DEMO_MICRO_BLOCKED",
            "blockers": gate_result["gate_blockers"],
            "important_note": "No order was sent.",
        }

    # In Z AI / non-Windows, MT5 not available
    return {
        "mode": "execute_and_monitor",
        "verdict": "MANAGED_DEMO_MICRO_BLOCKED",
        "blockers": ["Z AI / non-local environment - execute-and-monitor must be run locally by operator"],
        "important_note": "No order was sent. No mt5.order_send was called.",
    }


def write_report(result: dict) -> dict:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUTPUT_DIR / "managed_trade_report.json"
    md_path = OUTPUT_DIR / "managed_trade_report.md"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str, ensure_ascii=False)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# TITAN XAU AI - Managed Demo Micro Trade Report\n\n")
        f.write(f"**Mode:** {result.get('mode', 'unknown')}\n\n")
        f.write(f"**Verdict:** **{result.get('verdict', 'UNKNOWN')}**\n\n")
        f.write(f"**Timestamp:** {result.get('timestamp_utc', '')}\n\n")
        if result.get("blockers"):
            f.write("## Blockers\n\n")
            for b in result["blockers"]:
                f.write(f"- **{b}**\n")
        if result.get("next_action"):
            f.write(f"\n## Next Action\n\n{result['next_action']}\n")
    return {"json_path": str(json_path), "md_path": str(md_path)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Managed demo micro trade operator")
    parser.add_argument("--check-only", action="store_true", default=True)
    parser.add_argument("--dry-arm", action="store_true", default=False)
    parser.add_argument("--build-request", action="store_true", default=False)
    parser.add_argument("--execute-and-monitor", action="store_true", default=False)
    parser.add_argument("--direction", default="BUY")
    parser.add_argument("--entry-price", type=float, default=2000.0)
    parser.add_argument("--sl", type=float, default=0.0)
    parser.add_argument("--tp", type=float, default=0.0)
    parser.add_argument("--i-understand-demo-risk", action="store_true", default=False)
    parser.add_argument("--confirm-symbol", default="")
    parser.add_argument("--confirm-lot", type=float, default=0.0)
    parser.add_argument("--confirm-broker", default="")
    parser.add_argument("--confirm-one-order-only", action="store_true", default=False)
    parser.add_argument("--confirm-not-live", action="store_true", default=False)
    parser.add_argument("--confirm-environment-locked", action="store_true", default=False)
    parser.add_argument("--confirm-model-parity-pass", action="store_true", default=False)
    parser.add_argument("--confirm-local-operator", action="store_true", default=False)
    parser.add_argument("--confirm-managed-trailing", action="store_true", default=False)
    parser.add_argument("--duration-minutes", type=int, default=30)
    parser.add_argument("--interval-seconds", type=int, default=5)
    args = parser.parse_args()

    print("=" * 70)
    print("  TITAN XAU AI - Managed Demo Micro Trade (Sprint 9.9.3.45.1)")
    print("=" * 70)

    if args.execute_and_monitor:
        result = run_execute_and_monitor(args)
    elif args.dry_arm:
        result = run_dry_arm()
    elif args.build_request:
        result = run_build_request(args.direction, args.entry_price, args.sl, args.tp)
    else:
        result = run_check_only()

    report = write_report(result)
    print(f"\n  Mode: {result.get('mode', 'check_only')}")
    print(f"  Verdict: {result.get('verdict', 'UNKNOWN')}")
    print(f"  Blockers: {len(result.get('blockers', []))}")
    print(f"\n  JSON: {report['json_path']}")
    print(f"  MD:   {report['md_path']}")
    print("\n" + "=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
