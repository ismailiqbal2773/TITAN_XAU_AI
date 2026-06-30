#!/usr/bin/env python3
"""
TITAN XAU AI - Demo Micro Trade Forensics (Sprint 9.9.3.45.2)
================================================================
Passive forensic analysis of executed demo micro trade.
NEVER sends orders. NEVER modifies positions.

Sprint 9.9.3.45.2: Fixed matching bug. Now supports explicit
position_id/order_ticket/deal_ticket matching, execution receipt
matching, robust position_id grouping, SL close detection from
comment "[sl ...]", and order SL/TP capture.
"""
from __future__ import annotations
import argparse, hashlib, json, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
OUTPUT_DIR = REPO_ROOT / "data" / "audit" / "demo_micro_execution"
RECEIPT_PATH = REPO_ROOT / "data" / "runtime" / "demo_micro_execution_receipt.json"


def _load_receipt() -> Optional[dict]:
    if not RECEIPT_PATH.exists():
        return None
    try:
        with open(RECEIPT_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def collect_forensics(days: int = 30, symbol: str = "XAUUSD",
                       magic: int = 202619, comment: str = "TITAN_DEMO_MICRO",
                       position_id: int = 0, order_ticket: int = 0,
                       deal_ticket: int = 0) -> dict:
    ts = datetime.now(timezone.utc).isoformat()
    ok_checks = []
    blockers = []
    warnings = []
    findings = {}

    # Load execution receipt if available
    receipt = _load_receipt()
    if receipt:
        findings["receipt_available"] = True
        findings["receipt_success"] = receipt.get("success", False)
        findings["receipt_position_detected"] = receipt.get("position_detected", False)
        findings["receipt_position_id"] = receipt.get("position_id", 0)
        findings["receipt_order_ticket"] = receipt.get("order_ticket", 0)
        findings["receipt_execution_mode"] = receipt.get("execution_mode", "")
        findings["receipt_timestamp"] = receipt.get("timestamp_utc", "")
        ok_checks.append(f"Execution receipt found (mode={receipt.get('execution_mode', 'unknown')}, success={receipt.get('success', False)})")
        # Sprint 9.9.3.45.4: Use receipt position_id/order_ticket FIRST (newest receipt priority)
        if not position_id and receipt.get("position_id"):
            position_id = receipt["position_id"]
            ok_checks.append(f"Using position_id from receipt: {position_id}")
        if not order_ticket and receipt.get("order_ticket"):
            order_ticket = receipt["order_ticket"]
            ok_checks.append(f"Using order_ticket from receipt: {order_ticket}")
        if not deal_ticket and receipt.get("deal_ticket"):
            deal_ticket = receipt["deal_ticket"]
            ok_checks.append(f"Using deal_ticket from receipt: {deal_ticket}")
    else:
        findings["receipt_available"] = False
        findings["receipt_success"] = None
        findings["receipt_position_detected"] = None

    try:
        import MetaTrader5 as mt5
        if not mt5.initialize():
            return {
                "timestamp_utc": ts,
                "verdict": "DEMO_MICRO_FORENSICS_BLOCKED",
                "reason": "MT5 not available",
                "ok_checks": ok_checks, "blockers": ["MT5 initialize failed"], "warnings": [],
                "findings": findings,
            }

        # Account info
        acc = mt5.account_info()
        if acc:
            findings["account_server"] = getattr(acc, "server", "unknown")
            findings["account_trade_mode"] = getattr(acc, "trade_mode", -1)
            ok_checks.append(f"Account server: {findings['account_server']}")

        # Query ALL deals in the time window
        from_dt = datetime.now(timezone.utc) - timedelta(days=days)
        to_dt = datetime.now(timezone.utc)
        all_deals = mt5.history_deals_get(from_dt, to_dt)
        findings["total_deals_in_window"] = len(all_deals) if all_deals else 0

        # Query ALL orders in the time window
        all_orders = mt5.history_orders_get(from_dt, to_dt)
        findings["total_orders_in_window"] = len(all_orders) if all_orders else 0

        mt5.shutdown()

        if not all_deals:
            warnings.append("No deals found in history window")
            findings["root_cause"] = "HISTORY_NOT_FOUND"
            return {
                "timestamp_utc": ts,
                "verdict": "DEMO_MICRO_FORENSICS_INCOMPLETE",
                "ok_checks": ok_checks, "blockers": blockers, "warnings": warnings,
                "findings": findings,
                "safety": {"order_send_called": False, "position_modified": False},
            }

        # Normalize all deals
        normalized_deals = []
        for d in all_deals:
            normalized_deals.append({
                "ticket": getattr(d, "ticket", 0),
                "order": getattr(d, "order", 0),
                "position_id": getattr(d, "position_id", 0),
                "type": getattr(d, "type", -1),
                "entry": getattr(d, "entry", -1),
                "price": getattr(d, "price", 0),
                "profit": getattr(d, "profit", 0),
                "volume": getattr(d, "volume", 0),
                "comment": getattr(d, "comment", ""),
                "magic": getattr(d, "magic", 0),
                "symbol": getattr(d, "symbol", ""),
                "time": getattr(d, "time", 0),
            })

        # Normalize all orders
        normalized_orders = []
        if all_orders:
            for o in all_orders:
                normalized_orders.append({
                    "ticket": getattr(o, "ticket", 0),
                    "position_id": getattr(o, "position_id", 0),
                    "type": getattr(o, "type", -1),
                    "sl": getattr(o, "sl", 0),
                    "tp": getattr(o, "tp", 0),
                    "price": getattr(o, "price", 0),
                    "volume_initial": getattr(o, "volume_initial", 0),
                    "comment": getattr(o, "comment", ""),
                    "magic": getattr(o, "magic", 0),
                    "symbol": getattr(o, "symbol", ""),
                    "time_setup": getattr(o, "time_setup", 0),
                    "time_done": getattr(o, "time_done", 0),
                })

        # Matching priority:
        # 1. Explicit deal_ticket
        # 2. Explicit position_id
        # 3. Explicit order_ticket
        # 4. Receipt position_id/order_ticket
        # 5. Magic + symbol
        # 6. Comment contains TITAN_DEMO_MICRO + symbol
        # 7. Likely: XAUUSD + volume 0.01 + entry/close pair

        matched_deals = []
        matched_orders = []
        match_method = ""

        # 1. Explicit deal_ticket
        if deal_ticket:
            matched_deals = [d for d in normalized_deals if d["ticket"] == deal_ticket]
            if matched_deals:
                # Find the position_id from this deal and get all deals with same position_id
                pos_id = matched_deals[0]["position_id"]
                matched_deals = [d for d in normalized_deals if d["position_id"] == pos_id]
                matched_orders = [o for o in normalized_orders if o["position_id"] == pos_id]
                match_method = f"explicit_deal_ticket_{deal_ticket}"
                ok_checks.append(f"Matched by explicit deal_ticket: {deal_ticket}")

        # 2. Explicit position_id
        if not matched_deals and position_id:
            matched_deals = [d for d in normalized_deals if d["position_id"] == position_id]
            matched_orders = [o for o in normalized_orders if o["position_id"] == position_id]
            if matched_deals:
                match_method = f"explicit_position_id_{position_id}"
                ok_checks.append(f"Matched by explicit position_id: {position_id}")

        # 3. Explicit order_ticket
        if not matched_deals and order_ticket:
            # Find the position_id from this order
            order_match = [o for o in normalized_orders if o["ticket"] == order_ticket]
            if order_match:
                pos_id = order_match[0]["position_id"]
                matched_deals = [d for d in normalized_deals if d["position_id"] == pos_id]
                matched_orders = [o for o in normalized_orders if o["position_id"] == pos_id]
                match_method = f"explicit_order_ticket_{order_ticket}"
                ok_checks.append(f"Matched by explicit order_ticket: {order_ticket}")

        # 5. Magic + symbol match
        if not matched_deals:
            magic_deals = [d for d in normalized_deals if d["magic"] == magic and d["symbol"] == symbol]
            if magic_deals:
                # Group by position_id
                pos_ids = set(d["position_id"] for d in magic_deals if d["position_id"])
                if pos_ids:
                    # Take the latest position_id
                    latest_pos = max(pos_ids)
                    matched_deals = [d for d in normalized_deals if d["position_id"] == latest_pos]
                    matched_orders = [o for o in normalized_orders if o["position_id"] == latest_pos]
                    match_method = f"magic_{magic}_symbol_{symbol}_pos_{latest_pos}"
                    ok_checks.append(f"Matched by magic={magic} + symbol={symbol}, position_id={latest_pos}")

        # 6. Comment match
        if not matched_deals:
            comment_deals = [d for d in normalized_deals if comment in d.get("comment", "") and d["symbol"] == symbol]
            if comment_deals:
                pos_ids = set(d["position_id"] for d in comment_deals if d["position_id"])
                if pos_ids:
                    latest_pos = max(pos_ids)
                    matched_deals = [d for d in normalized_deals if d["position_id"] == latest_pos]
                    matched_orders = [o for o in normalized_orders if o["position_id"] == latest_pos]
                    match_method = f"comment_{comment}_pos_{latest_pos}"
                    ok_checks.append(f"Matched by comment '{comment}', position_id={latest_pos}")

        # 7. Likely: XAUUSD + volume 0.01 + entry/close pair
        likely_deals = []
        if not matched_deals:
            xauusd_small = [d for d in normalized_deals if d["symbol"] == symbol and d["volume"] <= 0.01]
            if xauusd_small:
                pos_ids = set(d["position_id"] for d in xauusd_small if d["position_id"])
                if pos_ids:
                    latest_pos = max(pos_ids)
                    likely_deals = [d for d in normalized_deals if d["position_id"] == latest_pos]
                    matched_deals = likely_deals
                    matched_orders = [o for o in normalized_orders if o["position_id"] == latest_pos]
                    match_method = f"likely_xauusd_001_pos_{latest_pos}"
                    warnings.append(f"Matched by likely XAUUSD 0.01 trade, position_id={latest_pos} (no magic/comment match)")

        findings["match_method"] = match_method
        findings["matched_deals"] = matched_deals
        findings["matched_orders"] = matched_orders
        findings["likely_deals"] = likely_deals

        if not matched_deals:
            findings["root_cause"] = "HISTORY_NOT_FOUND"
            warnings.append("No matching TITAN or likely deals found in history")
            return {
                "timestamp_utc": ts,
                "verdict": "DEMO_MICRO_FORENSICS_INCOMPLETE",
                "ok_checks": ok_checks, "blockers": blockers, "warnings": warnings,
                "findings": findings,
                "safety": {"order_send_called": False, "position_modified": False},
            }

        # Analyze matched deals
        entry_deal = None
        exit_deal = None
        for d in matched_deals:
            if d["entry"] == 0:  # DEAL_ENTRY_IN
                entry_deal = d
            elif d["entry"] == 1:  # DEAL_ENTRY_OUT
                exit_deal = d

        findings["entry_deal"] = entry_deal
        findings["exit_deal"] = exit_deal

        if entry_deal:
            ok_checks.append(f"Entry deal found: ticket={entry_deal['ticket']}, price={entry_deal['price']}")

        # Capture SL/TP from entry order
        entry_sl = 0.0
        entry_tp = 0.0
        if matched_orders:
            for o in matched_orders:
                if o.get("sl", 0) > 0 or o.get("tp", 0) > 0:
                    entry_sl = o["sl"]
                    entry_tp = o["tp"]
                    break
        findings["entry_sl"] = entry_sl
        findings["entry_tp"] = entry_tp
        if entry_sl > 0:
            ok_checks.append(f"Entry SL captured: {entry_sl}")
        if entry_tp > 0:
            ok_checks.append(f"Entry TP captured: {entry_tp}")

        # Detect SL hit
        sl_hit = False
        sl_close_comment = ""
        realized_pl = 0.0
        if exit_deal:
            realized_pl = exit_deal.get("profit", 0)
            exit_comment = exit_deal.get("comment", "").lower()
            if "[sl" in exit_comment or "sl " in exit_comment:
                sl_hit = True
                sl_close_comment = exit_deal.get("comment", "")
                ok_checks.append(f"SL hit detected: {sl_close_comment}")
            else:
                # Check if exit price matches SL
                if entry_sl > 0 and abs(exit_deal["price"] - entry_sl) < 0.01:
                    sl_hit = True
                    sl_close_comment = f"exit_price={exit_deal['price']} matches SL={entry_sl}"
                    ok_checks.append(f"SL hit detected by price match: {sl_close_comment}")

        findings["sl_hit_detected"] = sl_hit
        findings["sl_close_comment"] = sl_close_comment
        findings["realized_pl"] = realized_pl

        # Detect profit before SL (MFE/MAE unknown without tick data)
        profit_before_sl = "UNKNOWN"
        if sl_hit and realized_pl < 0:
            # SL hit at a loss - position may have been in profit before
            profit_before_sl = "POSSIBLE"
            warnings.append("SL hit at a loss - position may have been in profit before SL hit")
        findings["profit_before_sl_detected"] = profit_before_sl

        # SL modification events
        sl_modification_events = 0
        # Check if any orders have different SL than entry order (modification)
        if matched_orders and len(matched_orders) > 1:
            for o in matched_orders[1:]:
                if o.get("sl", 0) != entry_sl and o.get("sl", 0) > 0:
                    sl_modification_events += 1
        findings["sl_modification_events"] = sl_modification_events
        if sl_modification_events == 0:
            ok_checks.append("SL modification events: 0 (no trailing/breakeven applied)")
        else:
            warnings.append(f"SL modification events: {sl_modification_events}")

        findings["trailing_active"] = sl_modification_events > 0
        findings["breakeven_active"] = sl_modification_events > 0

        # Root cause
        if sl_modification_events == 0 and sl_hit:
            root_cause = "TRAILING_MANAGER_NOT_RUNNING"
        elif not matched_deals:
            root_cause = "HISTORY_NOT_FOUND"
        elif not sl_hit and not exit_deal:
            root_cause = "NO_OPEN_POSITION_TO_MANAGE"
        else:
            root_cause = "TRAILING_MANAGER_NOT_RUNNING"
        findings["root_cause"] = root_cause
        ok_checks.append(f"Root cause: {root_cause}")

        # Verdict
        is_exact_match = "magic" in match_method or "comment" in match_method or "explicit" in match_method or "receipt" in match_method
        if is_exact_match and entry_deal and (sl_hit or exit_deal):
            verdict = "DEMO_MICRO_FORENSICS_COMPLETE"
        elif matched_deals and (sl_hit or exit_deal):
            verdict = "DEMO_MICRO_FORENSICS_COMPLETE_WITH_WARNINGS"
        elif matched_deals:
            verdict = "DEMO_MICRO_FORENSICS_COMPLETE_WITH_WARNINGS"
        else:
            verdict = "DEMO_MICRO_FORENSICS_INCOMPLETE"

    except ImportError:
        verdict = "DEMO_MICRO_FORENSICS_INCOMPLETE"
        warnings.append("MetaTrader5 not available - forensics limited to local files")
        findings["root_cause"] = "MT5_HISTORY_UNAVAILABLE"
    except Exception as e:
        verdict = "DEMO_MICRO_FORENSICS_BLOCKED"
        blockers.append(f"Forensics error: {e}")

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
    json_path = OUTPUT_DIR / "post_trade_forensics.json"
    md_path = OUTPUT_DIR / "post_trade_forensics.md"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str, ensure_ascii=False)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# TITAN XAU AI - Post-Trade Forensics\n\n")
        f.write(f"**Verdict:** **{result['verdict']}**\n\n")
        f.write(f"**Timestamp:** {result['timestamp_utc']}\n\n")
        findings = result.get("findings", {})
        f.write("## Findings\n\n")
        f.write("| Field | Value |\n|---|---|\n")
        for k, v in findings.items():
            if not isinstance(v, (list, dict)):
                f.write(f"| {k} | {v} |\n")
        if findings.get("entry_deal"):
            ed = findings["entry_deal"]
            f.write("\n## Entry Deal\n\n")
            f.write(f"- Ticket: {ed['ticket']}\n")
            f.write(f"- Position ID: {ed['position_id']}\n")
            f.write(f"- Price: {ed['price']}\n")
            f.write(f"- Volume: {ed['volume']}\n")
            f.write(f"- Comment: {ed['comment']}\n")
            f.write(f"- Magic: {ed['magic']}\n")
        if findings.get("exit_deal"):
            xd = findings["exit_deal"]
            f.write("\n## Exit Deal\n\n")
            f.write(f"- Ticket: {xd['ticket']}\n")
            f.write(f"- Price: {xd['price']}\n")
            f.write(f"- Profit: {xd['profit']}\n")
            f.write(f"- Comment: {xd['comment']}\n")
        if findings.get("entry_sl", 0) > 0 or findings.get("entry_tp", 0) > 0:
            f.write(f"\n## Entry SL/TP\n\n")
            f.write(f"- SL: {findings.get('entry_sl', 'N/A')}\n")
            f.write(f"- TP: {findings.get('entry_tp', 'N/A')}\n")
        if findings.get("root_cause"):
            f.write(f"\n## Root Cause\n\n{findings['root_cause']}\n")
        if result.get("warnings"):
            f.write("\n## Warnings\n\n")
            for w in result["warnings"]:
                f.write(f"- {w}\n")
        if result.get("ok_checks"):
            f.write("\n## OK Checks\n\n")
            for c in result["ok_checks"]:
                f.write(f"- {c}\n")
    return {"json_path": str(json_path), "md_path": str(md_path)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Demo micro trade forensics")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--symbol", default="XAUUSD")
    parser.add_argument("--magic", type=int, default=202619)
    parser.add_argument("--comment", default="TITAN_DEMO_MICRO")
    parser.add_argument("--position-id", type=int, default=0)
    parser.add_argument("--order-ticket", type=int, default=0)
    parser.add_argument("--deal-ticket", type=int, default=0)
    args = parser.parse_args()
    print("=" * 70)
    print("  TITAN XAU AI - Post-Trade Forensics (Sprint 9.9.3.45.2)")
    print("=" * 70)
    result = collect_forensics(
        days=args.days, symbol=args.symbol, magic=args.magic, comment=args.comment,
        position_id=args.position_id, order_ticket=args.order_ticket, deal_ticket=args.deal_ticket,
    )
    report = write_report(result)
    print(f"\n  Verdict: {result['verdict']}")
    print(f"  Findings: {len(result.get('findings', {}))} fields")
    print(f"  Root cause: {result.get('findings', {}).get('root_cause', 'N/A')}")
    print(f"\n  JSON: {report['json_path']}")
    print(f"  MD:   {report['md_path']}")
    print("\n" + "=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
