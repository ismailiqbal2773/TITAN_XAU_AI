#!/usr/bin/env python3
"""
TITAN XAU AI - Latest Execution Receipt Diagnostic (Sprint 9.9.3.45.5)
=======================================================================
Passive diagnostic: read data/runtime/demo_micro_execution_receipt.json
and query MT5 to verify whether the receipt resolves to a real open or
closed trade. No order_send. No modification.

Verdicts:
  - RECEIPT_RESOLVED_OPEN: receipt detected_position_ticket is currently
    in positions_get.
  - RECEIPT_RESOLVED_CLOSED: receipt trade found in history_deals_get
    or history_orders_get but not in positions_get.
  - RECEIPT_PENDING_HISTORY: receipt detected_position_ticket is in
    positions_get but history_deals_get/orders_get does not yet show
    the trade.
  - RECEIPT_NOT_FOUND: receipt file does not exist.
  - RECEIPT_INCONSISTENT: receipt exists but none of receipt order/deal/
    position can be found in positions_get or history.

Output:
  data/audit/demo_micro_execution/latest_receipt_diagnostic.json
  data/audit/demo_micro_execution/latest_receipt_diagnostic.md
"""
from __future__ import annotations
import argparse, json, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
OUTPUT_DIR = REPO_ROOT / "data" / "audit" / "demo_micro_execution"
RECEIPT_PATH = REPO_ROOT / "data" / "runtime" / "demo_micro_execution_receipt.json"

TITAN_MAGIC = 202619
TITAN_COMMENT = "TITAN_DEMO_MICRO"


def _load_receipt() -> Optional[dict]:
    if not RECEIPT_PATH.exists():
        return None
    try:
        with open(RECEIPT_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def run_diagnostic() -> dict:
    ts = datetime.now(timezone.utc).isoformat()
    ok_checks = []
    blockers = []
    warnings = []
    findings = {
        "receipt_path": str(RECEIPT_PATH),
        "receipt_exists": False,
        "receipt_success": None,
        "receipt_order_send_result_order": None,
        "receipt_order_send_result_deal": None,
        "receipt_detected_position_ticket": None,
        "receipt_detected_position_identifier": None,
        "receipt_resolved_history_position_id": None,
        "open_position_match": False,
        "history_deal_match": False,
        "history_order_match": False,
        "resolved_open": False,
        "resolved_closed": False,
        "pending_history": False,
    }

    receipt = _load_receipt()
    if not receipt:
        findings["receipt_exists"] = False
        return {
            "timestamp_utc": ts,
            "verdict": "RECEIPT_NOT_FOUND",
            "ok_checks": ok_checks,
            "blockers": blockers,
            "warnings": warnings,
            "findings": findings,
            "safety": {"order_send_called": False, "position_modified": False},
        }

    findings["receipt_exists"] = True
    findings["receipt_success"] = receipt.get("success", False)
    findings["receipt_order_send_result_order"] = receipt.get("order_send_result_order") or receipt.get("order_ticket")
    findings["receipt_order_send_result_deal"] = receipt.get("order_send_result_deal") or receipt.get("deal_ticket")
    findings["receipt_detected_position_ticket"] = receipt.get("detected_position_ticket")
    findings["receipt_detected_position_identifier"] = receipt.get("detected_position_identifier")
    findings["receipt_resolved_history_position_id"] = receipt.get("resolved_history_position_id")
    findings["receipt_position_id"] = receipt.get("position_id")
    findings["receipt_timestamp"] = receipt.get("timestamp_utc", "")
    findings["receipt_execution_mode"] = receipt.get("execution_mode", "")
    findings["receipt_account_server"] = receipt.get("account_server", "")
    ok_checks.append(f"Receipt loaded: success={receipt.get('success', False)}")

    try:
        import MetaTrader5 as mt5
        if not mt5.initialize():
            blockers.append("MT5 initialize failed")
            return {
                "timestamp_utc": ts,
                "verdict": "RECEIPT_INCONSISTENT",
                "ok_checks": ok_checks,
                "blockers": blockers,
                "warnings": warnings,
                "findings": findings,
                "safety": {"order_send_called": False, "position_modified": False},
            }
        ok_checks.append("MT5 initialized (passive read-only)")

        # Account info
        acc = mt5.account_info()
        if acc:
            findings["account_server"] = getattr(acc, "server", "unknown")
            findings["account_trade_mode"] = getattr(acc, "trade_mode", -1)

        # Parse receipt timestamp for history window
        try:
            receipt_dt = datetime.fromisoformat(receipt.get("timestamp_utc", "").replace("Z", "+00:00"))
        except Exception:
            receipt_dt = datetime.now(timezone.utc)
        from_dt = receipt_dt - timedelta(minutes=30)
        to_dt = datetime.now(timezone.utc) + timedelta(minutes=1)

        # Query open positions
        positions = mt5.positions_get(symbol="XAUUSD")
        open_positions_list = list(positions) if positions else []
        findings["open_positions_count"] = len(open_positions_list)
        # Find any open position whose ticket/identifier matches receipt
        receipt_tickets = []
        for k in ("detected_position_ticket", "detected_position_identifier", "position_id"):
            v = receipt.get(k)
            if v and isinstance(v, int) and v > 0:
                receipt_tickets.append(v)
        # Also include receipt order_send_result_order as a possible position ticket (operator's bug case)
        order_val = receipt.get("order_send_result_order") or receipt.get("order_ticket")
        if order_val and isinstance(order_val, int) and order_val > 0:
            receipt_tickets.append(order_val)

        for p in open_positions_list:
            pt = getattr(p, "ticket", 0)
            pi = getattr(p, "identifier", pt)
            pmagic = getattr(p, "magic", 0)
            pcomment = getattr(p, "comment", "") or ""
            if pt in receipt_tickets or pi in receipt_tickets:
                findings["open_position_match"] = True
                findings["open_position_ticket"] = pt
                findings["open_position_identifier"] = pi
                findings["open_position_magic"] = pmagic
                findings["open_position_comment"] = pcomment
                ok_checks.append(f"Open position match: ticket={pt} identifier={pi} magic={pmagic}")
                break
            # Also match by magic+comment if receipt detected_position_ticket is None
            if pmagic == TITAN_MAGIC and TITAN_COMMENT in pcomment and not receipt.get("detected_position_ticket"):
                findings["open_position_match"] = True
                findings["open_position_ticket"] = pt
                findings["open_position_identifier"] = pi
                findings["open_position_magic"] = pmagic
                findings["open_position_comment"] = pcomment
                ok_checks.append(f"Open position match by magic+comment: ticket={pt}")
                break

        # Query history deals
        history_deals = []
        try:
            hd = mt5.history_deals_get(from_dt, to_dt)
            if hd:
                history_deals = list(hd)
        except Exception as e:
            warnings.append(f"history_deals_get error: {e}")
        findings["history_deals_count"] = len(history_deals)

        # Query history orders
        history_orders = []
        try:
            ho = mt5.history_orders_get(from_dt, to_dt)
            if ho:
                history_orders = list(ho)
        except Exception as e:
            warnings.append(f"history_orders_get error: {e}")
        findings["history_orders_count"] = len(history_orders)

        # Resolve history: match by receipt order/deal/position tickets
        receipt_deal = receipt.get("order_send_result_deal") or receipt.get("deal_ticket")
        receipt_order = receipt.get("order_send_result_order") or receipt.get("order_ticket")
        receipt_position_id = receipt.get("detected_position_identifier") or receipt.get("resolved_history_position_id") or receipt.get("position_id")

        matching_history_deal = None
        matching_history_order = None
        history_position_id = None

        # Match by deal ticket
        if receipt_deal and isinstance(receipt_deal, int) and receipt_deal > 0:
            for d in history_deals:
                if getattr(d, "ticket", 0) == receipt_deal:
                    matching_history_deal = d
                    history_position_id = getattr(d, "position_id", 0) or None
                    break
        # Match by order ticket
        if not matching_history_deal and receipt_order and isinstance(receipt_order, int) and receipt_order > 0:
            for o in history_orders:
                if getattr(o, "ticket", 0) == receipt_order:
                    matching_history_order = o
                    history_position_id = getattr(o, "position_id", 0) or None
                    break
            for d in history_deals:
                if getattr(d, "order", 0) == receipt_order:
                    matching_history_deal = d
                    history_position_id = getattr(d, "position_id", 0) or None
                    break
        # Match by position_id
        if not matching_history_deal and not matching_history_order and receipt_position_id and isinstance(receipt_position_id, int) and receipt_position_id > 0:
            for d in history_deals:
                if getattr(d, "position_id", 0) == receipt_position_id:
                    matching_history_deal = d
                    history_position_id = receipt_position_id
                    break
            if not matching_history_deal:
                for o in history_orders:
                    if getattr(o, "position_id", 0) == receipt_position_id:
                        matching_history_order = o
                        history_position_id = receipt_position_id
                        break

        if matching_history_deal is not None:
            findings["history_deal_match"] = True
            findings["history_deal_ticket"] = getattr(matching_history_deal, "ticket", 0)
            findings["history_deal_position_id"] = getattr(matching_history_deal, "position_id", 0)
            findings["history_deal_entry"] = getattr(matching_history_deal, "entry", -1)
            findings["history_deal_profit"] = getattr(matching_history_deal, "profit", 0)
            findings["history_deal_comment"] = getattr(matching_history_deal, "comment", "")
            ok_checks.append(f"History deal match: ticket={findings['history_deal_ticket']} position_id={findings['history_deal_position_id']}")
        if matching_history_order is not None:
            findings["history_order_match"] = True
            findings["history_order_ticket"] = getattr(matching_history_order, "ticket", 0)
            findings["history_order_position_id"] = getattr(matching_history_order, "position_id", 0)
            findings["history_order_sl"] = getattr(matching_history_order, "sl", 0)
            findings["history_order_tp"] = getattr(matching_history_order, "tp", 0)
            ok_checks.append(f"History order match: ticket={findings['history_order_ticket']} position_id={findings['history_order_position_id']}")

        mt5.shutdown()

        # Determine resolution
        findings["resolved_open"] = findings["open_position_match"]
        findings["resolved_closed"] = findings["history_deal_match"] or findings["history_order_match"]
        findings["pending_history"] = findings["open_position_match"] and not findings["resolved_closed"]

        if findings["resolved_open"] and findings["resolved_closed"]:
            # Position is open AND we have history (entry deal visible) - resolved open
            verdict = "RECEIPT_RESOLVED_OPEN"
        elif findings["resolved_open"]:
            # Open but history not yet visible - pending
            verdict = "RECEIPT_PENDING_HISTORY"
        elif findings["resolved_closed"]:
            # Not open but history shows the trade - closed
            verdict = "RECEIPT_RESOLVED_CLOSED"
        else:
            # Receipt exists but nothing matches
            verdict = "RECEIPT_INCONSISTENT"
            warnings.append(
                "Receipt exists but no open position and no history deal/order matches "
                "receipt order/deal/position tickets. Receipt may be stale or broker "
                "did not register the trade."
            )

    except ImportError:
        verdict = "RECEIPT_INCONSISTENT"
        blockers.append("MetaTrader5 not available")
        findings["mt5_available"] = False
    except Exception as e:
        verdict = "RECEIPT_INCONSISTENT"
        blockers.append(f"Diagnostic error: {e}")

    return {
        "timestamp_utc": ts,
        "verdict": verdict,
        "ok_checks": ok_checks,
        "blockers": blockers,
        "warnings": warnings,
        "findings": findings,
        "safety": {"order_send_called": False, "position_modified": False},
    }


def write_report(result: dict) -> dict:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUTPUT_DIR / "latest_receipt_diagnostic.json"
    md_path = OUTPUT_DIR / "latest_receipt_diagnostic.md"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str, ensure_ascii=False)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# TITAN XAU AI - Latest Execution Receipt Diagnostic\n\n")
        f.write(f"**Verdict:** **{result['verdict']}**\n\n")
        f.write(f"**Timestamp:** {result['timestamp_utc']}\n\n")
        findings = result.get("findings", {})
        f.write("## Receipt Fields\n\n")
        f.write("| Field | Value |\n|---|---|\n")
        receipt_fields = [
            "receipt_exists", "receipt_success",
            "receipt_order_send_result_order", "receipt_order_send_result_deal",
            "receipt_detected_position_ticket", "receipt_detected_position_identifier",
            "receipt_resolved_history_position_id", "receipt_position_id",
            "receipt_timestamp", "receipt_execution_mode", "receipt_account_server",
        ]
        for k in receipt_fields:
            if k in findings:
                f.write(f"| {k} | {findings[k]} |\n")
        f.write("\n## MT5 Resolution\n\n")
        f.write("| Field | Value |\n|---|---|\n")
        resolution_fields = [
            "open_positions_count", "open_position_match", "open_position_ticket",
            "open_position_identifier", "open_position_magic", "open_position_comment",
            "history_deals_count", "history_deal_match", "history_deal_ticket",
            "history_deal_position_id", "history_deal_entry", "history_deal_profit",
            "history_deal_comment",
            "history_orders_count", "history_order_match", "history_order_ticket",
            "history_order_position_id", "history_order_sl", "history_order_tp",
            "resolved_open", "resolved_closed", "pending_history",
        ]
        for k in resolution_fields:
            if k in findings:
                f.write(f"| {k} | {findings[k]} |\n")
        if result.get("ok_checks"):
            f.write("\n## OK Checks\n\n")
            for c in result["ok_checks"]:
                f.write(f"- {c}\n")
        if result.get("warnings"):
            f.write("\n## Warnings\n\n")
            for w in result["warnings"]:
                f.write(f"- {w}\n")
        if result.get("blockers"):
            f.write("\n## Blockers\n\n")
            for b in result["blockers"]:
                f.write(f"- **{b}**\n")
        f.write("\n## Safety\n\n")
        f.write("- order_send_called: False\n")
        f.write("- position_modified: False\n")
    return {"json_path": str(json_path), "md_path": str(md_path)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Latest execution receipt diagnostic (passive)")
    args = parser.parse_args()
    print("=" * 70)
    print("  TITAN XAU AI - Latest Execution Receipt Diagnostic (Sprint 9.9.3.45.5)")
    print("=" * 70)
    result = run_diagnostic()
    report = write_report(result)
    print(f"\n  Verdict: {result['verdict']}")
    print(f"  Receipt exists: {result.get('findings', {}).get('receipt_exists', False)}")
    print(f"  Resolved open: {result.get('findings', {}).get('resolved_open', False)}")
    print(f"  Resolved closed: {result.get('findings', {}).get('resolved_closed', False)}")
    print(f"  Pending history: {result.get('findings', {}).get('pending_history', False)}")
    print(f"\n  JSON: {report['json_path']}")
    print(f"  MD:   {report['md_path']}")
    print("\n" + "=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
