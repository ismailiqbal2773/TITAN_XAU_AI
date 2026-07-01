#!/usr/bin/env python3
"""
TITAN XAU AI - Manage Demo Micro Position (Sprint 9.9.3.45.6)
=============================================================
NEVER sends orders in check-only or preview mode.
--apply-once is gated for local operator only. Z AI must NOT run it.

Sprint 9.9.3.45.6 changes:
  - Full apply-once gate with all checks:
    * valid local operator token
    * --confirm-local-operator
    * --confirm-managed-trailing
    * MetaQuotes-Demo
    * DEMO account (trade_mode == 0)
    * XAUUSD
    * magic 202619
    * comment TITAN_DEMO_MICRO
    * one open TITAN position only
    * TP preserved
    * SL favorable-only
    * SL not equal to current SL if action is MODIFY
    * no widening SL
  - If action is HOLD, do not send modification.
  - If breakeven/trailing/profit-lock triggers, build TRADE_ACTION_SLTP
    request and call mt5.order_send exactly once in local apply mode.
  - Records: sl_modify_attempted, sl_modify_retcode, old_sl, new_sl,
    tp_preserved, modify_reason, modify_success.
  - Preview trailing still uses Sprint 9.9.3.45.5 double-scan pattern.
"""
from __future__ import annotations
import argparse, json, sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
OUTPUT_DIR = REPO_ROOT / "data" / "audit" / "demo_micro_execution"

TITAN_MAGIC = 202619
TITAN_COMMENT = "TITAN_DEMO_MICRO"
TITAN_SYMBOL = "XAUUSD"


def run_check_only() -> dict:
    ts = datetime.now(timezone.utc).isoformat()
    from titan.production.demo_micro_position_manager import DemoMicroPositionManager
    mgr = DemoMicroPositionManager()
    return {
        "timestamp_utc": ts,
        "mode": "check_only",
        "verdict": "MANAGE_CHECK_PASS",
        "manager_available": True,
        "breakeven_trigger": mgr.breakeven_trigger,
        "trailing_trigger": mgr.trailing_trigger,
        "profit_lock_trigger": mgr.profit_lock_trigger,
        "next_action": "Run --preview-trailing to see SL modification recommendations",
    }


def run_preview_trailing() -> dict:
    """Sprint 9.9.3.45.5: Stale-preview-safe trailing preview.

    Re-reads positions_get TWICE if necessary:
      1. Initial scan finds candidate TITAN positions.
      2. For each candidate, immediately re-reads positions_get to
         verify the ticket still exists. If the position has
         disappeared between scans, returns POSITION_DISAPPEARED_DURING_PREVIEW
         and does NOT emit an actionable SLTP preview.
    """
    ts = datetime.now(timezone.utc).isoformat()
    from titan.production.demo_micro_position_manager import DemoMicroPositionManager
    from titan.production.demo_micro_sl_modify_builder import DemoMicroSLModifyBuilder

    mgr = DemoMicroPositionManager()
    builder = DemoMicroSLModifyBuilder()

    recommendations = []
    warnings = []
    disappeared_tickets = []
    found_count = 0
    verified_count = 0

    try:
        import MetaTrader5 as mt5
        if mt5.initialize():
            # === First scan: find candidate TITAN positions ===
            positions = mt5.positions_get(symbol="XAUUSD")
            candidates = []
            if positions:
                for p in positions:
                    magic = getattr(p, "magic", 0)
                    if magic != TITAN_MAGIC:
                        continue  # Ignore non-TITAN positions
                    candidates.append(p)
            found_count = len(candidates)

            if found_count == 0:
                mt5.shutdown()
                return {
                    "timestamp_utc": ts,
                    "mode": "preview_trailing",
                    "verdict": "NO_POSITION_FOUND",
                    "recommendations": [],
                    "count": 0,
                    "found_count": 0,
                    "verified_count": 0,
                    "disappeared_tickets": [],
                    "warnings": warnings,
                    "important_note": "No open TITAN_DEMO_MICRO position found. No preview generated.",
                }

            # === Second scan: verify each candidate still exists ===
            # Re-read positions_get to ensure ticket is still open
            verify_positions = mt5.positions_get(symbol="XAUUSD")
            verify_tickets = set()
            if verify_positions:
                for vp in verify_positions:
                    if getattr(vp, "magic", 0) == TITAN_MAGIC:
                        verify_tickets.add(getattr(vp, "ticket", 0))

            for p in candidates:
                ticket = getattr(p, "ticket", 0)
                if ticket not in verify_tickets:
                    # Position disappeared between first and second scan
                    disappeared_tickets.append(ticket)
                    warnings.append(
                        f"POSITION_DISAPPEARED_DURING_PREVIEW: ticket {ticket} was found in "
                        "initial scan but not in verification scan. No actionable SLTP preview emitted."
                    )
                    continue
                verified_count += 1
                direction = "BUY" if getattr(p, "type", 1) == 0 else "SELL"
                entry = getattr(p, "price_open", 0)
                current = getattr(p, "price_current", 0)
                sl = getattr(p, "sl", 0)
                tp = getattr(p, "tp", 0)

                rec = mgr.evaluate(
                    direction=direction, entry_price=entry,
                    current_price=current, current_sl=sl, current_tp=tp,
                )
                preview = builder.build_preview(
                    ticket=ticket, new_sl=rec.new_sl, tp=tp,
                    favorable=rec.favorable, reason=rec.reason,
                    blockers=rec.blockers,
                )
                recommendations.append({
                    "ticket": ticket,
                    "direction": direction,
                    "entry": entry,
                    "current": current,
                    "current_sl": sl,
                    "recommended_sl": rec.new_sl,
                    "action": rec.action.value,
                    "preview": preview,
                    "verified_alive": True,
                    "verification_method": "positions_get_double_scan",
                })
            mt5.shutdown()
    except ImportError:
        warnings.append("MetaTrader5 not available - preview limited")
    except Exception as e:
        warnings.append(f"Preview error: {e}")

    # Determine verdict
    if disappeared_tickets and not recommendations:
        # All candidates disappeared
        verdict = "POSITION_CLOSED_BEFORE_PREVIEW"
    elif disappeared_tickets and recommendations:
        # Some disappeared, some verified
        verdict = "PREVIEW_GENERATED_WITH_WARNINGS"
    elif recommendations:
        verdict = "PREVIEW_GENERATED"
    else:
        verdict = "NO_POSITION_FOUND"

    return {
        "timestamp_utc": ts,
        "mode": "preview_trailing",
        "verdict": verdict,
        "recommendations": recommendations,
        "count": len(recommendations),
        "found_count": found_count,
        "verified_count": verified_count,
        "disappeared_tickets": disappeared_tickets,
        "warnings": warnings,
        "important_note": "This is a PREVIEW only. No mt5.order_send was called. No position was modified. "
                          "Recommendations are only emitted for positions verified alive via double-scan.",
    }


def _check_apply_once_gates(args, mt5) -> tuple[bool, list, list, dict]:
    """Sprint 9.9.3.45.6: Run all apply-once gates.

    Returns (passed, blockers, ok_checks, info).
    """
    blockers = []
    ok_checks = []
    info = {}

    # 1. confirm-local-operator
    if not getattr(args, "confirm_local_operator", False):
        blockers.append("Missing --confirm-local-operator")
    else:
        ok_checks.append("confirm-local-operator present")

    # 2. confirm-managed-trailing
    if not getattr(args, "confirm_managed_trailing", False):
        blockers.append("Missing --confirm-managed-trailing")
    else:
        ok_checks.append("confirm-managed-trailing present")

    if blockers:
        return False, blockers, ok_checks, info

    # 3. Local operator token
    from scripts.operator.create_local_operator_execution_token import load_and_validate_token
    token_result = load_and_validate_token()
    if not token_result["valid"]:
        blockers.append(f"LOCAL_TOKEN_INVALID: {token_result['reason']}")
        return False, blockers, ok_checks, info
    ok_checks.append("Local operator token valid")

    # 4. MT5 initialize
    try:
        if not mt5.initialize():
            blockers.append("MT5 initialize failed")
            return False, blockers, ok_checks, info
    except Exception as e:
        blockers.append(f"MT5 initialize error: {e}")
        return False, blockers, ok_checks, info
    ok_checks.append("MT5 initialized")

    try:
        # 5. Account DEMO + MetaQuotes-Demo
        acc = mt5.account_info()
        if acc is None:
            blockers.append("account_info returned None")
            return False, blockers, ok_checks, info
        server = getattr(acc, "server", "unknown")
        trade_mode = getattr(acc, "trade_mode", -1)
        info["account_server"] = server
        info["account_trade_mode"] = trade_mode
        if trade_mode != 0:
            blockers.append(f"ACCOUNT_NOT_DEMO: trade_mode={trade_mode}")
            return False, blockers, ok_checks, info
        ok_checks.append(f"Account DEMO (trade_mode=0)")
        if "MetaQuotes-Demo" not in server:
            blockers.append(f"BROKER_NOT_METAQUOTES_DEMO: server={server}")
            return False, blockers, ok_checks, info
        ok_checks.append(f"Broker: {server}")

        # 6. One open TITAN position only
        positions = mt5.positions_get(symbol=TITAN_SYMBOL)
        titan_positions = []
        if positions:
            for p in positions:
                if getattr(p, "magic", 0) == TITAN_MAGIC:
                    titan_positions.append(p)
        if len(titan_positions) == 0:
            blockers.append("NO_OPEN_TITAN_POSITION")
            return False, blockers, ok_checks, info
        if len(titan_positions) > 1:
            blockers.append(f"MULTIPLE_TITAN_POSITIONS: {len(titan_positions)}")
            return False, blockers, ok_checks, info
        position = titan_positions[0]
        info["position_ticket"] = getattr(position, "ticket", 0)
        info["position_magic"] = getattr(position, "magic", 0)
        info["position_comment"] = getattr(position, "comment", "")
        info["position_symbol"] = getattr(position, "symbol", "")
        info["position_type"] = getattr(position, "type", -1)
        ok_checks.append(f"One open TITAN position: ticket={info['position_ticket']}")

        # 7. magic and comment match
        if info["position_magic"] != TITAN_MAGIC:
            blockers.append(f"MAGIC_MISMATCH: {info['position_magic']}")
            return False, blockers, ok_checks, info
        if TITAN_COMMENT not in (info["position_comment"] or ""):
            blockers.append(f"COMMENT_MISMATCH: {info['position_comment']}")
            return False, blockers, ok_checks, info
        if info["position_symbol"] != TITAN_SYMBOL:
            blockers.append(f"SYMBOL_MISMATCH: {info['position_symbol']}")
            return False, blockers, ok_checks, info
        ok_checks.append("magic/comment/symbol verified")

        return True, blockers, ok_checks, info
    finally:
        # Caller responsible for shutdown
        pass


def run_apply_once(args) -> dict:
    """Sprint 9.9.3.45.6: Gated SL modification. Z AI must NOT run this.

    Full gate chain:
      1. confirm-local-operator
      2. confirm-managed-trailing
      3. valid local operator token
      4. MT5 initialize
      5. account DEMO + MetaQuotes-Demo
      6. one open TITAN position only
      7. magic/comment/symbol match
      8. evaluate position -> if HOLD, no modification
      9. if MODIFY: TP preserve, favorable-only, SL != current, no widening
     10. call mt5.order_send (TRADE_ACTION_SLTP) exactly once
    """
    ts = datetime.now(timezone.utc).isoformat()
    blockers = []
    ok_checks = []
    info = {}

    # 1. confirm-local-operator
    if not getattr(args, "confirm_local_operator", False):
        return {
            "mode": "apply_once",
            "verdict": "MANAGE_REFUSED",
            "blockers": ["Missing --confirm-local-operator"],
            "important_note": "No modification was sent.",
            "timestamp_utc": ts,
        }

    # 2. confirm-managed-trailing
    if not getattr(args, "confirm_managed_trailing", False):
        return {
            "mode": "apply_once",
            "verdict": "MANAGE_REFUSED",
            "blockers": ["Missing --confirm-managed-trailing"],
            "important_note": "No modification was sent.",
            "timestamp_utc": ts,
        }

    # 3. Local operator token
    from scripts.operator.create_local_operator_execution_token import load_and_validate_token
    token_result = load_and_validate_token()
    if not token_result["valid"]:
        return {
            "mode": "apply_once",
            "verdict": "MANAGE_REFUSED",
            "blockers": [f"LOCAL_TOKEN_INVALID: {token_result['reason']}"],
            "important_note": "No modification was sent.",
            "timestamp_utc": ts,
        }
    ok_checks.append("Local operator token valid")

    # 4. MT5 import + initialize
    try:
        import MetaTrader5 as mt5
    except ImportError:
        return {
            "mode": "apply_once",
            "verdict": "MANAGE_REFUSED",
            "blockers": ["MT5_NOT_AVAILABLE: MetaTrader5 not installed"],
            "important_note": "No modification was sent.",
            "timestamp_utc": ts,
            "ok_checks": ok_checks,
        }

    try:
        if not mt5.initialize():
            return {
                "mode": "apply_once",
                "verdict": "MANAGE_REFUSED",
                "blockers": ["MT5 initialize failed"],
                "important_note": "No modification was sent.",
                "timestamp_utc": ts,
                "ok_checks": ok_checks,
            }
        ok_checks.append("MT5 initialized")

        # 5. Account DEMO + MetaQuotes-Demo
        acc = mt5.account_info()
        if acc is None:
            return {
                "mode": "apply_once",
                "verdict": "MANAGE_REFUSED",
                "blockers": ["account_info returned None"],
                "important_note": "No modification was sent.",
                "timestamp_utc": ts,
                "ok_checks": ok_checks,
            }
        server = getattr(acc, "server", "unknown")
        trade_mode = getattr(acc, "trade_mode", -1)
        info["account_server"] = server
        info["account_trade_mode"] = trade_mode
        if trade_mode != 0:
            return {
                "mode": "apply_once",
                "verdict": "MANAGE_REFUSED",
                "blockers": [f"ACCOUNT_NOT_DEMO: trade_mode={trade_mode}"],
                "important_note": "No modification was sent. Real account blocked.",
                "timestamp_utc": ts,
                "ok_checks": ok_checks,
                "info": info,
            }
        ok_checks.append("Account DEMO (trade_mode=0)")
        if "MetaQuotes-Demo" not in server:
            return {
                "mode": "apply_once",
                "verdict": "MANAGE_REFUSED",
                "blockers": [f"BROKER_NOT_METAQUOTES_DEMO: server={server}"],
                "important_note": "No modification was sent. Non-MetaQuotes-Demo blocked.",
                "timestamp_utc": ts,
                "ok_checks": ok_checks,
                "info": info,
            }
        ok_checks.append(f"Broker: {server}")

        # 6. One open TITAN position only
        positions = mt5.positions_get(symbol=TITAN_SYMBOL)
        titan_positions = []
        if positions:
            for p in positions:
                if getattr(p, "magic", 0) == TITAN_MAGIC:
                    titan_positions.append(p)
        if len(titan_positions) == 0:
            return {
                "mode": "apply_once",
                "verdict": "MANAGE_REFUSED",
                "blockers": ["NO_OPEN_TITAN_POSITION"],
                "important_note": "No modification was sent. No open TITAN position.",
                "timestamp_utc": ts,
                "ok_checks": ok_checks,
                "info": info,
            }
        if len(titan_positions) > 1:
            return {
                "mode": "apply_once",
                "verdict": "MANAGE_REFUSED",
                "blockers": [f"MULTIPLE_TITAN_POSITIONS: {len(titan_positions)}"],
                "important_note": "No modification was sent. Multiple positions blocked.",
                "timestamp_utc": ts,
                "ok_checks": ok_checks,
                "info": info,
            }
        position = titan_positions[0]
        position_ticket = getattr(position, "ticket", 0)
        position_magic = getattr(position, "magic", 0)
        position_comment = getattr(position, "comment", "")
        position_symbol = getattr(position, "symbol", "")
        ok_checks.append(f"One open TITAN position: ticket={position_ticket}")

        # 7. magic/comment/symbol match
        if position_magic != TITAN_MAGIC:
            return {
                "mode": "apply_once",
                "verdict": "MANAGE_REFUSED",
                "blockers": [f"MAGIC_MISMATCH: {position_magic}"],
                "important_note": "No modification was sent. Magic mismatch.",
                "timestamp_utc": ts,
                "ok_checks": ok_checks,
                "info": info,
            }
        if TITAN_COMMENT not in (position_comment or ""):
            return {
                "mode": "apply_once",
                "verdict": "MANAGE_REFUSED",
                "blockers": [f"COMMENT_MISMATCH: {position_comment}"],
                "important_note": "No modification was sent. Comment mismatch.",
                "timestamp_utc": ts,
                "ok_checks": ok_checks,
                "info": info,
            }
        if position_symbol != TITAN_SYMBOL:
            return {
                "mode": "apply_once",
                "verdict": "MANAGE_REFUSED",
                "blockers": [f"SYMBOL_MISMATCH: {position_symbol}"],
                "important_note": "No modification was sent. Symbol mismatch.",
                "timestamp_utc": ts,
                "ok_checks": ok_checks,
                "info": info,
            }
        ok_checks.append("magic/comment/symbol verified")

        # 8. Evaluate position
        from titan.production.demo_micro_position_manager import DemoMicroPositionManager, SLAction
        mgr = DemoMicroPositionManager()
        direction = "BUY" if getattr(position, "type", 1) == 0 else "SELL"
        entry_price = float(getattr(position, "price_open", 0) or 0)
        current_price = float(getattr(position, "price_current", 0) or 0)
        current_sl = float(getattr(position, "sl", 0) or 0)
        current_tp = float(getattr(position, "tp", 0) or 0)
        rec = mgr.evaluate(
            direction=direction, entry_price=entry_price,
            current_price=current_price, current_sl=current_sl,
            current_tp=current_tp,
        )
        info["sl_action"] = rec.action.value
        info["new_sl"] = rec.new_sl
        info["current_sl"] = current_sl
        info["current_tp"] = current_tp
        info["favorable"] = rec.favorable
        info["reason"] = rec.reason

        # If HOLD, do not send modification
        if rec.action == SLAction.HOLD:
            return {
                "mode": "apply_once",
                "verdict": "MANAGE_HOLD_NO_MODIFY",
                "blockers": [],
                "ok_checks": ok_checks + [f"Action HOLD: {rec.reason}"],
                "info": info,
                "sl_modify_attempted": False,
                "sl_modify_retcode": 0,
                "old_sl": current_sl,
                "new_sl": current_sl,
                "tp_preserved": True,
                "modify_reason": rec.reason,
                "modify_success": False,
                "important_note": "Action HOLD - no modification sent. mt5.order_send NOT called.",
                "timestamp_utc": ts,
            }

        # If BLOCKED, do not send modification
        if rec.action == SLAction.BLOCKED:
            return {
                "mode": "apply_once",
                "verdict": "MANAGE_REFUSED",
                "blockers": rec.blockers,
                "ok_checks": ok_checks,
                "info": info,
                "sl_modify_attempted": False,
                "sl_modify_retcode": 0,
                "old_sl": current_sl,
                "new_sl": current_sl,
                "tp_preserved": True,
                "modify_reason": f"BLOCKED: {rec.reason}",
                "modify_success": False,
                "important_note": "Action BLOCKED - no modification sent.",
                "timestamp_utc": ts,
            }

        # 9. TP preserve check
        if rec.tp != current_tp:
            return {
                "mode": "apply_once",
                "verdict": "MANAGE_REFUSED",
                "blockers": ["TP_NOT_PRESERVED"],
                "ok_checks": ok_checks,
                "info": info,
                "sl_modify_attempted": False,
                "sl_modify_retcode": 0,
                "old_sl": current_sl,
                "new_sl": rec.new_sl,
                "tp_preserved": False,
                "modify_reason": "TP_NOT_PRESERVED",
                "modify_success": False,
                "important_note": "TP not preserved - modification blocked.",
                "timestamp_utc": ts,
            }
        ok_checks.append("TP preserved")

        # Favorable-only check
        if not rec.favorable:
            return {
                "mode": "apply_once",
                "verdict": "MANAGE_REFUSED",
                "blockers": ["UNFAVORABLE_SL_BLOCKED"],
                "ok_checks": ok_checks,
                "info": info,
                "sl_modify_attempted": False,
                "sl_modify_retcode": 0,
                "old_sl": current_sl,
                "new_sl": rec.new_sl,
                "tp_preserved": True,
                "modify_reason": "UNFAVORABLE_SL_BLOCKED",
                "modify_success": False,
                "important_note": "SL move unfavorable - modification blocked.",
                "timestamp_utc": ts,
            }
        ok_checks.append("SL move favorable")

        # SL != current SL (no-op check)
        if rec.new_sl == current_sl:
            return {
                "mode": "apply_once",
                "verdict": "MANAGE_HOLD_NO_MODIFY",
                "blockers": [],
                "ok_checks": ok_checks + ["SL equals current SL - no modification needed"],
                "info": info,
                "sl_modify_attempted": False,
                "sl_modify_retcode": 0,
                "old_sl": current_sl,
                "new_sl": current_sl,
                "tp_preserved": True,
                "modify_reason": "SL_EQUALS_CURRENT_NO_MODIFY",
                "modify_success": False,
                "important_note": "SL equals current - no modification sent.",
                "timestamp_utc": ts,
            }

        # No widening SL (for BUY: new_sl must be >= current_sl;
        # for SELL: new_sl must be <= current_sl). Already enforced by
        # favorable check, but double-check explicitly.
        if direction == "BUY" and rec.new_sl < current_sl:
            return {
                "mode": "apply_once",
                "verdict": "MANAGE_REFUSED",
                "blockers": [f"SL_WIDENING_BLOCKED: new_sl={rec.new_sl} < current_sl={current_sl}"],
                "ok_checks": ok_checks,
                "info": info,
                "sl_modify_attempted": False,
                "sl_modify_retcode": 0,
                "old_sl": current_sl,
                "new_sl": rec.new_sl,
                "tp_preserved": True,
                "modify_reason": "SL_WIDENING_BLOCKED",
                "modify_success": False,
                "important_note": "SL widening blocked.",
                "timestamp_utc": ts,
            }
        if direction == "SELL" and current_sl > 0 and rec.new_sl > current_sl:
            return {
                "mode": "apply_once",
                "verdict": "MANAGE_REFUSED",
                "blockers": [f"SL_WIDENING_BLOCKED: new_sl={rec.new_sl} > current_sl={current_sl}"],
                "ok_checks": ok_checks,
                "info": info,
                "sl_modify_attempted": False,
                "sl_modify_retcode": 0,
                "old_sl": current_sl,
                "new_sl": rec.new_sl,
                "tp_preserved": True,
                "modify_reason": "SL_WIDENING_BLOCKED",
                "modify_success": False,
                "important_note": "SL widening blocked.",
                "timestamp_utc": ts,
            }
        ok_checks.append("No SL widening")

        # 10. Build TRADE_ACTION_SLTP request and call mt5.order_send exactly once
        modify_request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "symbol": TITAN_SYMBOL,
            "position": int(position_ticket),
            "sl": float(rec.new_sl),
            "tp": float(current_tp),
        }
        try:
            modify_result = mt5.order_send(modify_request)
        except Exception as e:
            return {
                "mode": "apply_once",
                "verdict": "MANAGE_MODIFY_FAILED",
                "blockers": [f"order_send exception: {e}"],
                "ok_checks": ok_checks,
                "info": info,
                "sl_modify_attempted": True,
                "sl_modify_retcode": 0,
                "old_sl": current_sl,
                "new_sl": rec.new_sl,
                "tp_preserved": True,
                "modify_reason": f"ORDER_SEND_EXCEPTION: {e}",
                "modify_success": False,
                "modify_request": modify_request,
                "important_note": "mt5.order_send raised exception. Modification failed.",
                "timestamp_utc": ts,
            }

        retcode = int(getattr(modify_result, "retcode", 0) or 0) if modify_result else 0
        modify_success = retcode == 10009
        modify_reason = "TRADE_RETCODE_DONE" if modify_success else f"retcode={retcode}"

        if modify_success:
            verdict = "MANAGE_MODIFY_SUCCESS"
            note = "SL modification applied successfully via mt5.order_send (TRADE_ACTION_SLTP)."
        else:
            verdict = "MANAGE_MODIFY_FAILED"
            note = f"SL modification failed. retcode={retcode}."

        return {
            "mode": "apply_once",
            "verdict": verdict,
            "blockers": [] if modify_success else [f"MODIFY_FAILED: retcode={retcode}"],
            "ok_checks": ok_checks,
            "info": info,
            "sl_modify_attempted": True,
            "sl_modify_retcode": retcode,
            "old_sl": current_sl,
            "new_sl": rec.new_sl,
            "tp_preserved": True,
            "modify_reason": modify_reason,
            "modify_success": modify_success,
            "modify_request": modify_request,
            "important_note": note,
            "timestamp_utc": ts,
        }
    finally:
        try:
            mt5.shutdown()
        except Exception:
            pass


def write_report(result: dict) -> dict:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUTPUT_DIR / "manage_position_report.json"
    md_path = OUTPUT_DIR / "manage_position_report.md"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str, ensure_ascii=False)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# TITAN XAU AI - Manage Demo Micro Position\n\n")
        f.write(f"**Mode:** {result.get('mode', 'unknown')}\n\n")
        f.write(f"**Verdict:** **{result.get('verdict', 'UNKNOWN')}**\n\n")
        f.write(f"**Timestamp:** {result.get('timestamp_utc', '')}\n\n")
        # Sprint 9.9.3.45.5: Stale-preview fields
        f.write("## Verification Summary\n\n")
        f.write("| Field | Value |\n|---|---|\n")
        f.write(f"| found_count | {result.get('found_count', 'N/A')} |\n")
        f.write(f"| verified_count | {result.get('verified_count', 'N/A')} |\n")
        f.write(f"| disappeared_tickets | {result.get('disappeared_tickets', [])} |\n")
        # Sprint 9.9.3.45.6: Apply-once fields
        if result.get("mode") == "apply_once":
            f.write("\n## Apply-Once Summary\n\n")
            f.write("| Field | Value |\n|---|---|\n")
            f.write(f"| sl_modify_attempted | {result.get('sl_modify_attempted', 'N/A')} |\n")
            f.write(f"| sl_modify_retcode | {result.get('sl_modify_retcode', 'N/A')} |\n")
            f.write(f"| old_sl | {result.get('old_sl', 'N/A')} |\n")
            f.write(f"| new_sl | {result.get('new_sl', 'N/A')} |\n")
            f.write(f"| tp_preserved | {result.get('tp_preserved', 'N/A')} |\n")
            f.write(f"| modify_reason | {result.get('modify_reason', 'N/A')} |\n")
            f.write(f"| modify_success | {result.get('modify_success', 'N/A')} |\n")
        if result.get("recommendations"):
            f.write("\n## Recommendations (Verified Alive)\n\n")
            for r in result["recommendations"]:
                f.write(f"- Ticket: {r['ticket']}, Action: {r['action']}, "
                        f"Current SL: {r['current_sl']}, Recommended SL: {r['recommended_sl']}, "
                        f"Verified: {r.get('verified_alive', False)}\n")
        if result.get("warnings"):
            f.write("\n## Warnings\n\n")
            for w in result["warnings"]:
                f.write(f"- {w}\n")
        if result.get("important_note"):
            f.write(f"\n## Note\n\n{result['important_note']}\n")
    return {"json_path": str(json_path), "md_path": str(md_path)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage demo micro position")
    parser.add_argument("--check-only", action="store_true", default=True)
    parser.add_argument("--preview-trailing", action="store_true", default=False)
    parser.add_argument("--apply-once", action="store_true", default=False)
    parser.add_argument("--confirm-local-operator", action="store_true", default=False)
    parser.add_argument("--confirm-managed-trailing", action="store_true", default=False)
    args = parser.parse_args()

    print("=" * 70)
    print("  TITAN XAU AI - Manage Demo Micro Position (Sprint 9.9.3.45.6)")
    print("=" * 70)

    if args.apply_once:
        result = run_apply_once(args)
    elif args.preview_trailing:
        result = run_preview_trailing()
    else:
        result = run_check_only()

    report = write_report(result)
    print(f"\n  Mode: {result.get('mode', 'check_only')}")
    print(f"  Verdict: {result.get('verdict', 'UNKNOWN')}")
    print(f"  Found: {result.get('found_count', 'N/A')}  Verified: {result.get('verified_count', 'N/A')}")
    if result.get("mode") == "apply_once":
        print(f"  Modify attempted: {result.get('sl_modify_attempted', False)}  "
              f"Success: {result.get('modify_success', False)}  "
              f"Retcode: {result.get('sl_modify_retcode', 0)}")
    print(f"\n  JSON: {report['json_path']}")
    print(f"  MD:   {report['md_path']}")
    print("\n" + "=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
