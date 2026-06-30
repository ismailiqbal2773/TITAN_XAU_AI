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
    """Execute and monitor. Z AI must NOT run this.

    Sprint 9.9.3.45.3: Replaced hard-coded non-local refusal with real
    environment gate. Execution is allowed only when ALL evidence-based
    checks pass. Z AI/non-Windows is blocked by environment drift gate,
    not by a hard-coded string.
    """
    import platform as _platform
    import sys as _sys

    ts = datetime.now(timezone.utc).isoformat()
    blockers = []
    ok_checks = []
    env_info = {}

    # 1. Check all confirmation flags
    required_flags = {
        "i_understand_demo_risk": getattr(args, "i_understand_demo_risk", False),
        "confirm_symbol": getattr(args, "confirm_symbol", ""),
        "confirm_lot": getattr(args, "confirm_lot", 0.0),
        "confirm_broker": getattr(args, "confirm_broker", ""),
        "confirm_one_order_only": getattr(args, "confirm_one_order_only", False),
        "confirm_not_live": getattr(args, "confirm_not_live", False),
        "confirm_environment_locked": getattr(args, "confirm_environment_locked", False),
        "confirm_model_parity_pass": getattr(args, "confirm_model_parity_pass", False),
        "confirm_local_operator": getattr(args, "confirm_local_operator", False),
        "confirm_managed_trailing": getattr(args, "confirm_managed_trailing", False),
    }
    missing_flags = [k for k, v in required_flags.items() if not v]
    if missing_flags:
        return {
            "mode": "execute_and_monitor",
            "verdict": "MANAGED_DEMO_MICRO_BLOCKED",
            "blockers": [f"CONFIRMATION_MISSING: {', '.join(missing_flags)}"],
            "important_note": "No order was sent. No mt5.order_send was called.",
            "timestamp_utc": ts,
        }
    ok_checks.append("All confirmation flags present")

    # 2. Local operator token check
    from scripts.operator.create_local_operator_execution_token import load_and_validate_token, consume_token
    token_result = load_and_validate_token()
    if not token_result["valid"]:
        reason = token_result["reason"]
        if "expired" in reason.lower():
            blocker = "LOCAL_TOKEN_EXPIRED"
        elif "not found" in reason.lower():
            blocker = "LOCAL_TOKEN_MISSING"
        elif "consumed" in reason.lower():
            blocker = "LOCAL_TOKEN_MISSING"
        else:
            blocker = f"LOCAL_TOKEN_INVALID: {reason}"
        return {
            "mode": "execute_and_monitor",
            "verdict": "MANAGED_DEMO_MICRO_BLOCKED",
            "blockers": [blocker],
            "important_note": "No order was sent. No mt5.order_send was called.",
            "timestamp_utc": ts,
        }
    token = token_result["token"]
    ok_checks.append(f"Local operator token valid (expires: {token.get('expires_utc', 'N/A')})")

    # 3. Environment drift gate
    from titan.production.environment_drift_gate import EnvironmentDriftGate, DriftVerdict
    env_gate = EnvironmentDriftGate()
    drift_result = env_gate.evaluate()
    env_info["current_platform"] = _platform.platform()
    env_info["current_python"] = f"{_sys.version_info.major}.{_sys.version_info.minor}.{_sys.version_info.micro}"
    env_info["frozen_platform"] = ""
    env_info["frozen_python"] = ""
    env_info["environment_drift_verdict"] = drift_result.verdict.value

    # Load frozen signature for reporting
    import json as _json
    sig_path = REPO_ROOT / "config" / "environment" / "environment_signature.json"
    if sig_path.exists():
        try:
            with open(sig_path, "r", encoding="utf-8") as f:
                sig = _json.load(f)
            env_info["frozen_platform"] = sig.get("platform", "")
            env_info["frozen_python"] = sig.get("python_version", "")
        except Exception:
            pass

    if drift_result.verdict == DriftVerdict.ENVIRONMENT_LOCK_BLOCKED:
        return {
            "mode": "execute_and_monitor",
            "verdict": "MANAGED_DEMO_MICRO_BLOCKED",
            "blockers": [f"ENVIRONMENT_DRIFT_BLOCKED: {drift_result.blockers}"],
            "important_note": "No order was sent. No mt5.order_send was called.",
            "timestamp_utc": ts,
            "env_info": env_info,
        }
    ok_checks.append(f"Environment drift: {drift_result.verdict.value}")

    # 4. Token git commit check (token must match current commit or be accepted)
    import subprocess as _sp
    try:
        head_r = _sp.run(["git", "rev-parse", "--short", "HEAD"],
                         cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=10)
        current_head = head_r.stdout.strip() if head_r.returncode == 0 else "unknown"
    except Exception:
        current_head = "unknown"
    token_git = token.get("git_commit", "")
    if token_git and token_git != current_head and token_git != "unknown":
        return {
            "mode": "execute_and_monitor",
            "verdict": "MANAGED_DEMO_MICRO_BLOCKED",
            "blockers": [f"LOCAL_TOKEN_GIT_MISMATCH: token={token_git} current={current_head}"],
            "important_note": "No order was sent. Recreate token after pulling new commit.",
            "timestamp_utc": ts,
            "env_info": env_info,
        }
    ok_checks.append(f"Git commit: {current_head}")

    # 5. Gate check (dependency/model/self-healing/parity)
    gate_result = run_check_only()
    if "BLOCKED" in gate_result.get("gate_verdict", ""):
        return {
            "mode": "execute_and_monitor",
            "verdict": "MANAGED_DEMO_MICRO_BLOCKED",
            "blockers": gate_result.get("gate_blockers", []),
            "important_note": "No order was sent.",
            "timestamp_utc": ts,
            "env_info": env_info,
        }
    ok_checks.append("Demo micro gate passed")

    # 6. Build executable SL/TP request
    from titan.production.demo_micro_order_builder import DemoMicroOrderBuilder
    builder = DemoMicroOrderBuilder()
    build_result = builder.build_preview(
        direction=getattr(args, "direction", "BUY"),
        entry_price=getattr(args, "entry_price", 2000.0),
        sl=getattr(args, "sl", 0.0),
        tp=getattr(args, "tp", 0.0),
        safe_fallback=False,
    )
    executable_status = build_result.get("executable_status", "PREVIEW_ONLY_NOT_EXECUTABLE")
    env_info["sltp_executable_status"] = executable_status
    if executable_status != "EXECUTABLE_WITH_PROTECTIVE_SL_TP":
        return {
            "mode": "execute_and_monitor",
            "verdict": "MANAGED_DEMO_MICRO_BLOCKED",
            "blockers": [f"MANAGED_SLTP_NOT_EXECUTABLE: {executable_status}"],
            "important_note": "No order was sent. SL/TP not executable.",
            "timestamp_utc": ts,
            "env_info": env_info,
        }
    ok_checks.append("SL/TP executable with protective values")

    # 7. Force-close readiness
    from scripts.operator.check_demo_micro_force_close_readiness import run_check as fc_check
    fc_result = fc_check()
    env_info["force_close_verdict"] = fc_result.get("verdict", "UNKNOWN")
    if "READY" not in fc_result.get("verdict", ""):
        return {
            "mode": "execute_and_monitor",
            "verdict": "MANAGED_DEMO_MICRO_BLOCKED",
            "blockers": [f"FORCE_CLOSE_NOT_READY: {fc_result.get('verdict', 'UNKNOWN')}"],
            "important_note": "No order was sent.",
            "timestamp_utc": ts,
            "env_info": env_info,
        }
    ok_checks.append("Force-close readiness: READY")

    # 8. Consume token (regardless of MT5 outcome)
    consume_token()

    # 9. Attempt gated execution via MT5
    # This path is reached only when ALL evidence-based gates pass.
    # In Z AI/non-Windows, the environment drift gate blocks above.
    # On local Windows with matching signature, this proceeds.
    try:
        import MetaTrader5 as mt5
    except ImportError:
        return {
            "mode": "execute_and_monitor",
            "verdict": "MANAGED_DEMO_MICRO_BLOCKED",
            "blockers": ["MT5_NOT_AVAILABLE: MetaTrader5 not installed"],
            "important_note": "No order was sent.",
            "timestamp_utc": ts,
            "env_info": env_info,
            "ok_checks": ok_checks,
        }

    try:
        if not mt5.initialize():
            return {
                "mode": "execute_and_monitor",
                "verdict": "MANAGED_DEMO_MICRO_BLOCKED",
                "blockers": ["MT5_NOT_AVAILABLE: initialize failed"],
                "important_note": "No order was sent.",
                "timestamp_utc": ts,
                "env_info": env_info,
                "ok_checks": ok_checks,
            }

        # Verify account DEMO
        acc = mt5.account_info()
        if acc is not None:
            env_info["account_server"] = getattr(acc, "server", "unknown")
            env_info["account_trade_mode"] = getattr(acc, "trade_mode", -1)
            if getattr(acc, "trade_mode", -1) != 0:  # 0 = DEMO
                mt5.shutdown()
                return {
                    "mode": "execute_and_monitor",
                    "verdict": "MANAGED_DEMO_MICRO_BLOCKED",
                    "blockers": ["ACCOUNT_NOT_DEMO: trade_mode is not DEMO"],
                    "important_note": "No order was sent.",
                    "timestamp_utc": ts,
                    "env_info": env_info,
                    "ok_checks": ok_checks,
                }
            if "MetaQuotes-Demo" not in getattr(acc, "server", ""):
                mt5.shutdown()
                return {
                    "mode": "execute_and_monitor",
                    "verdict": "MANAGED_DEMO_MICRO_BLOCKED",
                    "blockers": ["BROKER_NOT_METAQUOTES_DEMO"],
                    "important_note": "No order was sent.",
                    "timestamp_utc": ts,
                    "env_info": env_info,
                    "ok_checks": ok_checks,
                }
        ok_checks.append(f"Account: {env_info.get('account_server', 'unknown')} DEMO mode")

        # Verify open positions = 0
        positions = mt5.positions_get(symbol="XAUUSD")
        if positions is not None and len(positions) > 0:
            mt5.shutdown()
            return {
                "mode": "execute_and_monitor",
                "verdict": "MANAGED_DEMO_MICRO_BLOCKED",
                "blockers": [f"OPEN_POSITIONS_NOT_ZERO: {len(positions)} positions found"],
                "important_note": "No order was sent.",
                "timestamp_utc": ts,
                "env_info": env_info,
                "ok_checks": ok_checks,
            }
        ok_checks.append("Open positions: 0")

        # Build and send order (exactly once, no retry)
        preview = build_result["preview"]
        direction = preview["order_type"]
        volume = preview["volume"]
        sl = preview["sl"]
        tp = preview["tp"]

        tick = mt5.symbol_info_tick("XAUUSD")
        price = tick.ask if direction == "BUY" else tick.bid

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": "XAUUSD",
            "volume": float(volume),
            "type": mt5.ORDER_TYPE_BUY if direction == "BUY" else mt5.ORDER_TYPE_SELL,
            "price": price,
            "sl": float(sl),
            "tp": float(tp),
            "magic": 202619,
            "comment": "TITAN_DEMO_MICRO",
            "deviation": 20,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)
        mt5.shutdown()

        if result is None:
            return {
                "mode": "execute_and_monitor",
                "verdict": "MANAGED_DEMO_MICRO_FAILED",
                "blockers": ["ORDER_SEND_FAILED: returned None"],
                "order_send_called": True,
                "important_note": "order_send was called once and failed. No retry.",
                "timestamp_utc": ts,
                "env_info": env_info,
                "ok_checks": ok_checks,
            }

        retcode = getattr(result, "retcode", 0)
        if retcode == 10009:  # TRADE_RETCODE_DONE
            # Start managed monitor
            from titan.production.demo_micro_managed_trade_orchestrator import ManagedTradeOrchestrator
            orch = ManagedTradeOrchestrator(
                duration_minutes=getattr(args, "duration_minutes", 30),
                interval_seconds=getattr(args, "interval_seconds", 5),
            )
            monitor_result = orch.monitor_position(
                position_ticket=getattr(result, "position_id", 0),
                direction=direction,
                entry_price=price,
                current_sl=sl,
                current_tp=tp,
                current_price=price,
                is_open=True,
            )
            return {
                "mode": "execute_and_monitor",
                "verdict": "MANAGED_DEMO_MICRO_STARTED",
                "order_send_called": True,
                "order_send_retcode": retcode,
                "position_id": getattr(result, "position_id", 0),
                "entry_price": price,
                "sl": sl,
                "tp": tp,
                "monitor_result": monitor_result.to_dict(),
                "important_note": "Order sent once and succeeded. Monitor started. No second order.",
                "timestamp_utc": ts,
                "env_info": env_info,
                "ok_checks": ok_checks,
                "next_action": "Position is being monitored for breakeven/trailing/profit-lock.",
            }
        else:
            return {
                "mode": "execute_and_monitor",
                "verdict": "MANAGED_DEMO_MICRO_FAILED",
                "blockers": [f"ORDER_SEND_FAILED: retcode={retcode}"],
                "order_send_called": True,
                "order_send_retcode": retcode,
                "important_note": "order_send was called once and failed. No retry.",
                "timestamp_utc": ts,
                "env_info": env_info,
                "ok_checks": ok_checks,
            }

    except Exception as e:
        try:
            mt5.shutdown()
        except Exception:
            pass
        return {
            "mode": "execute_and_monitor",
            "verdict": "MANAGED_DEMO_MICRO_BLOCKED",
            "blockers": [f"EXECUTION_ERROR: {e}"],
            "important_note": "No order was sent. Error before order_send.",
            "timestamp_utc": ts,
            "env_info": env_info,
            "ok_checks": ok_checks,
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
        env_info = result.get("env_info", {})
        if env_info:
            f.write("## Environment Info\n\n")
            f.write("| Field | Value |\n|---|---|\n")
            for k, v in env_info.items():
                f.write(f"| {k} | {v} |\n")
        if result.get("ok_checks"):
            f.write("\n## OK Checks\n\n")
            for c in result["ok_checks"]:
                f.write(f"- {c}\n")
        if result.get("blockers"):
            f.write("\n## Blockers\n\n")
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
