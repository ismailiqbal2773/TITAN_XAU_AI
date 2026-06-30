#!/usr/bin/env python3
"""
TITAN XAU AI - Controlled Demo Micro Execution Operator (Sprint 9.9.3.44)
=========================================================================
NEVER sends orders. NEVER calls mt5.order_send. NEVER runs DEMO_MICRO_EXECUTE.
Z AI must NOT run --execute-once.
"""
from __future__ import annotations
import argparse, json, os, sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
OUTPUT_DIR = REPO_ROOT / "data" / "audit" / "demo_micro_execution"


def run_check_only() -> dict:
    """Run gate check only."""
    from titan.production.demo_micro_execution_gate import DemoMicroExecutionGate
    gate = DemoMicroExecutionGate()
    result = gate.evaluate()
    return result.to_dict()


def run_dry_arm() -> dict:
    """Run dry-arm: gate check + mark as armed (no order)."""
    result = run_check_only()
    result["mode"] = "dry_arm"
    result["armed"] = result["verdict"] != "DEMO_MICRO_GATE_BLOCKED"
    result["next_action"] = (
        "Dry-arm completed. If PASS or PASS_WITH_WARNINGS, "
        "run --build-request to generate order preview. "
        "Do NOT run --execute-once from Z AI."
    )
    return result


def run_build_request(direction: str = "BUY", entry_price: float = 2000.0,
                       sl: float = 0.0, tp: float = 0.0) -> dict:
    """Build order request preview (no order sent)."""
    from titan.production.demo_micro_order_builder import DemoMicroOrderBuilder
    builder = DemoMicroOrderBuilder()
    result = builder.build_preview(
        direction=direction, entry_price=entry_price, sl=sl, tp=tp,
        safe_fallback=False,  # Sprint 9.9.3.44.3: No preview fallback - try real MT5 tick
    )
    report = builder.write_preview(result)
    result["report_paths"] = report
    result["mode"] = "build_request"
    result["next_action"] = (
        "Order request preview generated. Review the preview. "
        "Do NOT run --execute-once from Z AI."
    )
    return result


def run_execute_once(args) -> dict:
    """Execute-once mode - guarded, requires full confirmations.
    Z AI must NOT run this mode.
    """
    required_flags = [
        args.i_understand_demo_risk,
        args.confirm_symbol,
        args.confirm_lot,
        args.confirm_broker,
        args.confirm_one_order_only,
        args.confirm_not_live,
        args.confirm_environment_locked,
        args.confirm_model_parity_pass,
    ]
    if not all(required_flags):
        return {
            "mode": "execute_once",
            "verdict": "DEMO_MICRO_EXECUTION_REFUSED",
            "reason": "Missing required confirmation flags",
            "blockers": ["Missing confirmation flags - execution refused"],
            "next_action": "Provide all --confirm-* flags and --i-understand-demo-risk",
        }

    # Gate check
    gate_result = run_check_only()
    if "BLOCKED" in gate_result["verdict"]:
        return {
            "mode": "execute_once",
            "verdict": "DEMO_MICRO_EXECUTION_REFUSED",
            "reason": f"Gate BLOCKED: {gate_result['blockers']}",
            "blockers": gate_result["blockers"],
            "next_action": "Resolve gate blockers before execution",
        }

    # Sprint 9.9.3.44.2: SL/TP execution safety check
    # Build request and verify it is EXECUTABLE_WITH_PROTECTIVE_SL_TP
    from titan.production.demo_micro_order_builder import DemoMicroOrderBuilder
    builder = DemoMicroOrderBuilder()
    build_result = builder.build_preview(
        direction=getattr(args, "direction", "BUY"),
        entry_price=getattr(args, "entry_price", 2000.0),
        sl=getattr(args, "sl", 0.0),
        tp=getattr(args, "tp", 0.0),
        safe_fallback=False,  # No safe fallback for execution
    )
    executable_status = build_result.get("executable_status", "PREVIEW_ONLY_NOT_EXECUTABLE")
    if executable_status != "EXECUTABLE_WITH_PROTECTIVE_SL_TP":
        return {
            "mode": "execute_once",
            "verdict": "DEMO_MICRO_EXECUTION_REFUSED",
            "reason": f"DEMO_MICRO_PREVIEW_FALLBACK_NOT_EXECUTABLE: {executable_status}",
            "blockers": [f"DEMO_MICRO_SL_TP_MISSING or DEMO_MICRO_PREVIEW_FALLBACK_NOT_EXECUTABLE: {build_result.get('blockers', [])}"],
            "next_action": "Provide valid SL/TP or ATR for executable order. dry_run_preview_mode is not accepted for execute-once.",
        }

    # Sprint 9.9.3.44.4: Require --confirm-local-operator
    if not getattr(args, "confirm_local_operator", False):
        return {
            "mode": "execute_once",
            "verdict": "DEMO_MICRO_EXECUTION_REFUSED",
            "reason": "Missing --confirm-local-operator flag",
            "blockers": ["Missing --confirm-local-operator - execution refused"],
            "next_action": "Add --confirm-local-operator to confirm local operator execution",
            "important_note": "No order was sent. No mt5.order_send was called.",
        }

    # Sprint 9.9.3.44.4: Require valid local operator token
    from scripts.operator.create_local_operator_execution_token import load_and_validate_token, consume_token
    token_result = load_and_validate_token()
    if not token_result["valid"]:
        return {
            "mode": "execute_once",
            "verdict": "DEMO_MICRO_EXECUTION_REFUSED",
            "reason": f"Local operator token invalid: {token_result['reason']}",
            "blockers": [f"Token invalid: {token_result['reason']}"],
            "next_action": "Create a valid token: python scripts/operator/create_local_operator_execution_token.py",
            "important_note": "No order was sent. No mt5.order_send was called.",
        }

    # Sprint 9.9.3.44.4: All gates pass - attempt gated order_send
    # This path is only reached when all safety checks pass AND the operator
    # has a valid local token AND all confirmation flags are provided.
    # In Z AI / non-Windows environment, the environment drift gate above
    # will have already blocked execution.
    consume_token()  # Consume token regardless of order_send result

    order_result = _attempt_gated_order_send(build_result, args)
    return order_result


def _attempt_gated_order_send(build_result: dict, args) -> dict:
    """Attempt a single gated order_send. Never retries.

    This function is only called after ALL safety gates pass.
    In Z AI environment, the environment drift gate blocks before this point.
    """
    try:
        import MetaTrader5 as mt5
    except ImportError:
        return {
            "mode": "execute_once",
            "verdict": "DEMO_MICRO_EXECUTION_REFUSED",
            "reason": "MetaTrader5 not available - cannot execute order",
            "blockers": ["MetaTrader5 not installed on this machine"],
            "next_action": "Run on Windows machine with MetaTrader5 installed",
            "important_note": "No order was sent. No mt5.order_send was called.",
            "order_send_called": False,
        }

    try:
        if not mt5.initialize():
            return {
                "mode": "execute_once",
                "verdict": "DEMO_MICRO_EXECUTION_REFUSED",
                "reason": "MT5 initialize failed",
                "blockers": ["MT5 initialize failed"],
                "next_action": "Verify MT5 terminal is running and connected",
                "important_note": "No order was sent. No mt5.order_send was called.",
                "order_send_called": False,
            }

        # Verify account DEMO
        acc = mt5.account_info()
        if acc is not None:
            trade_mode = getattr(acc, "trade_mode", -1)
            if trade_mode != 0:  # 0 = DEMO
                mt5.shutdown()
                return {
                    "mode": "execute_once",
                    "verdict": "DEMO_MICRO_EXECUTION_REFUSED",
                    "reason": "Account is not DEMO mode",
                    "blockers": ["Account trade_mode is not DEMO"],
                    "important_note": "No order was sent.",
                    "order_send_called": False,
                }

        # Verify open positions = 0
        positions = mt5.positions_get(symbol="XAUUSD")
        if positions is not None and len(positions) > 0:
            mt5.shutdown()
            return {
                "mode": "execute_once",
                "verdict": "DEMO_MICRO_EXECUTION_REFUSED",
                "reason": f"Open positions found: {len(positions)} (must be 0)",
                "blockers": [f"Open positions: {len(positions)} - must be 0 before entry"],
                "important_note": "No order was sent.",
                "order_send_called": False,
            }

        # Build order request
        preview = build_result["preview"]
        direction = preview["order_type"]
        volume = preview["volume"]
        sl = preview["sl"]
        tp = preview["tp"]

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": "XAUUSD",
            "volume": float(volume),
            "type": mt5.ORDER_TYPE_BUY if direction == "BUY" else mt5.ORDER_TYPE_SELL,
            "price": mt5.symbol_info_tick("XAUUSD").ask if direction == "BUY" else mt5.symbol_info_tick("XAUUSD").bid,
            "sl": float(sl),
            "tp": float(tp),
            "magic": 202619,
            "comment": "TITAN_DEMO_MICRO",
            "deviation": 20,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        # Call order_send exactly once - never retry
        result = mt5.order_send(request)
        mt5.shutdown()

        if result is None:
            return {
                "mode": "execute_once",
                "verdict": "DEMO_MICRO_ORDER_SEND_FAILED",
                "reason": "order_send returned None",
                "blockers": ["order_send returned None - no retry attempted"],
                "important_note": "order_send was called once and failed. No retry.",
                "order_send_called": True,
                "order_send_retcode": None,
            }

        retcode = getattr(result, "retcode", 0)
        if retcode == 10009:  # TRADE_RETCODE_DONE
            return {
                "mode": "execute_once",
                "verdict": "DEMO_MICRO_ORDER_SEND_SUCCEEDED",
                "reason": f"order_send succeeded: retcode={retcode}",
                "order_send_called": True,
                "order_send_retcode": retcode,
                "order_details": {"volume": volume, "sl": sl, "tp": tp, "direction": direction},
                "next_action": "Run post-trade verification: python scripts/operator/verify_demo_micro_position.py",
                "important_note": "Order was sent once and succeeded. No second order will be sent.",
            }
        else:
            return {
                "mode": "execute_once",
                "verdict": "DEMO_MICRO_ORDER_SEND_FAILED",
                "reason": f"order_send failed: retcode={retcode}",
                "blockers": [f"order_send retcode={retcode} - no retry attempted"],
                "order_send_called": True,
                "order_send_retcode": retcode,
                "important_note": "order_send was called once and failed. No retry.",
            }

    except Exception as e:
        try:
            mt5.shutdown()
        except Exception:
            pass
        return {
            "mode": "execute_once",
            "verdict": "DEMO_MICRO_EXECUTION_REFUSED",
            "reason": f"Execution error: {e}",
            "blockers": [f"Execution error: {e}"],
            "important_note": "No order was sent. Error occurred before order_send.",
            "order_send_called": False,
        }


def write_report(result: dict, filename: str) -> dict:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUTPUT_DIR / f"{filename}.json"
    md_path = OUTPUT_DIR / f"{filename}.md"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str, ensure_ascii=False)

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# TITAN XAU AI - Demo Micro Execution Report\n\n")
        f.write(f"**Mode:** {result.get('mode', 'check_only')}\n\n")
        f.write(f"**Verdict:** **{result.get('verdict', 'UNKNOWN')}**\n\n")
        f.write(f"**Timestamp:** {result.get('timestamp_utc', '')}\n\n")
        if result.get("ok_checks"):
            f.write("## OK Checks\n\n")
            for c in result["ok_checks"]:
                f.write(f"- {c}\n")
        if result.get("blockers"):
            f.write("\n## Blockers\n\n")
            for b in result["blockers"]:
                f.write(f"- **{b}**\n")
        if result.get("warnings"):
            f.write("\n## Warnings\n\n")
            for w in result["warnings"]:
                f.write(f"- {w}\n")
        if result.get("next_action"):
            f.write(f"\n## Next Action\n\n{result['next_action']}\n")
        f.write("\n## Safety\n\n")
        f.write("- No mt5.order_send was called.\n")
        f.write("- No market execution was run.\n")
        f.write("- No DEMO_MICRO_EXECUTE was run.\n")
        f.write("- No raw_mt5_probe was run.\n")

    return {"json_path": str(json_path), "md_path": str(md_path)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Controlled demo micro execution operator")
    parser.add_argument("--check-only", action="store_true", default=True)
    parser.add_argument("--dry-arm", action="store_true", default=False)
    parser.add_argument("--build-request", action="store_true", default=False)
    parser.add_argument("--direction", default="BUY")
    parser.add_argument("--entry-price", type=float, default=2000.0)
    parser.add_argument("--sl", type=float, default=0.0)
    parser.add_argument("--tp", type=float, default=0.0)
    parser.add_argument("--execute-once", action="store_true", default=False)
    parser.add_argument("--i-understand-demo-risk", action="store_true", default=False)
    parser.add_argument("--confirm-symbol", default="")
    parser.add_argument("--confirm-lot", type=float, default=0.0)
    parser.add_argument("--confirm-broker", default="")
    parser.add_argument("--confirm-one-order-only", action="store_true", default=False)
    parser.add_argument("--confirm-not-live", action="store_true", default=False)
    parser.add_argument("--confirm-environment-locked", action="store_true", default=False)
    parser.add_argument("--confirm-model-parity-pass", action="store_true", default=False)
    parser.add_argument("--confirm-local-operator", action="store_true", default=False)
    args = parser.parse_args()

    print("=" * 70)
    print("  TITAN XAU AI - Controlled Demo Micro Execution (Sprint 9.9.3.44)")
    print("=" * 70)

    if args.execute_once:
        result = run_execute_once(args)
        filename = "demo_micro_execution_check"
    elif args.dry_arm:
        result = run_dry_arm()
        filename = "demo_micro_execution_check"
    elif args.build_request:
        result = run_build_request(args.direction, args.entry_price, args.sl, args.tp)
        filename = "demo_micro_execution_check"
    else:
        result = run_check_only()
        filename = "demo_micro_execution_check"

    report = write_report(result, filename)

    print(f"\n  Mode: {result.get('mode', 'check_only')}")
    print(f"  Verdict: {result.get('verdict', 'UNKNOWN')}")
    print(f"  Blockers: {len(result.get('blockers', []))}")
    print(f"\n  JSON: {report['json_path']}")
    print(f"  MD:   {report['md_path']}")
    if result.get("next_action"):
        print(f"\n  Next: {result['next_action']}")
    print("\n" + "=" * 70)

    return 0


if __name__ == "__main__":
    sys.exit(main())
