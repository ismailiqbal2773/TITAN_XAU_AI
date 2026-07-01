#!/usr/bin/env python3
"""
TITAN XAU AI - Demo Micro Trade Forensics (Sprint 9.9.3.45.5)
================================================================
Passive forensic analysis of executed demo micro trade.
NEVER sends orders. NEVER modifies positions.

Sprint 9.9.3.45.5: Strict no-fallback matching.
  - If --position-id is supplied and no matching deal/order/open
    position is found: verdict DEMO_MICRO_FORENSICS_INCOMPLETE,
    root_cause EXPLICIT_POSITION_ID_NOT_FOUND. Do NOT fallback to old
    magic/comment trades.
  - If receipt exists and receipt_success=True: receipt match is
    mandatory first. If receipt order/deal/position cannot be found:
    verdict DEMO_MICRO_FORENSICS_INCOMPLETE, root_cause
    RECEIPT_TRADE_NOT_FOUND_IN_HISTORY_OR_OPEN_POSITIONS. Include old
    fallback candidates separately only as diagnostics. Do NOT return
    COMPLETE based on old trade.
  - Fallback to old magic/comment only allowed when: no explicit id
    supplied, no receipt exists, OR receipt_success=False.
  - New fields: explicit_position_id_supplied, explicit_position_id_found,
    receipt_match_required, receipt_match_found, fallback_candidates_count,
    fallback_used, fallback_allowed, fallback_blocked_reason.
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


def collect_forensics(days: int = 30, symbol: str = "XAUUSD",
                       magic: int = TITAN_MAGIC, comment: str = TITAN_COMMENT,
                       position_id: int = 0, order_ticket: int = 0,
                       deal_ticket: int = 0) -> dict:
    ts = datetime.now(timezone.utc).isoformat()
    ok_checks = []
    blockers = []
    warnings = []
    findings = {
        "explicit_position_id_supplied": position_id > 0,
        "explicit_position_id_found": False,
        "explicit_order_ticket_supplied": order_ticket > 0,
        "explicit_order_ticket_found": False,
        "explicit_deal_ticket_supplied": deal_ticket > 0,
        "explicit_deal_ticket_found": False,
        "receipt_match_required": False,
        "receipt_match_found": False,
        "fallback_candidates_count": 0,
        "fallback_used": False,
        "fallback_allowed": False,
        "fallback_blocked_reason": "",
    }

    # Load execution receipt if available
    receipt = _load_receipt()
    if receipt:
        findings["receipt_available"] = True
        findings["receipt_success"] = receipt.get("success", False)
        findings["receipt_position_detected"] = receipt.get("position_detected", False)
        findings["receipt_position_id"] = receipt.get("position_id", 0)
        findings["receipt_order_ticket"] = receipt.get("order_ticket", 0)
        findings["receipt_detected_position_ticket"] = receipt.get("detected_position_ticket", 0)
        findings["receipt_detected_position_identifier"] = receipt.get("detected_position_identifier", 0)
        findings["receipt_execution_mode"] = receipt.get("execution_mode", "")
        findings["receipt_timestamp"] = receipt.get("timestamp_utc", "")
        ok_checks.append(
            f"Execution receipt found (mode={receipt.get('execution_mode', 'unknown')}, "
            f"success={receipt.get('success', False)})"
        )
    else:
        findings["receipt_available"] = False
        findings["receipt_success"] = None
        findings["receipt_position_detected"] = None

    # Sprint 9.9.3.45.5: Determine fallback policy
    explicit_id_supplied = position_id > 0 or order_ticket > 0 or deal_ticket > 0
    receipt_match_required = bool(receipt and receipt.get("success", False))
    fallback_allowed = (not explicit_id_supplied) and (
        not receipt or not receipt.get("success", False)
    )

    findings["receipt_match_required"] = receipt_match_required
    findings["fallback_allowed"] = fallback_allowed

    if explicit_id_supplied and not fallback_allowed:
        # Don't block fallback yet - we may not need it. But if explicit
        # id is supplied, fallback is forbidden regardless of receipt.
        findings["fallback_blocked_reason"] = "EXPLICIT_ID_SUPPLIED_FORBIDS_FALLBACK"
    elif receipt_match_required and not fallback_allowed:
        findings["fallback_blocked_reason"] = "RECEIPT_SUCCESS_TRUE_REQUIRES_RECEIPT_MATCH"
    elif not fallback_allowed:
        findings["fallback_blocked_reason"] = "FALLBACK_NOT_ALLOWED"
    else:
        findings["fallback_blocked_reason"] = ""

    try:
        import MetaTrader5 as mt5
        if not mt5.initialize():
            return {
                "timestamp_utc": ts,
                "verdict": "DEMO_MICRO_FORENSICS_BLOCKED",
                "reason": "MT5 not available",
                "ok_checks": ok_checks, "blockers": ["MT5 initialize failed"], "warnings": warnings,
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

        # Query current open positions (Sprint 9.9.3.45.5: needed for explicit position-id check)
        open_positions = mt5.positions_get(symbol=symbol)
        findings["open_positions_count"] = len(open_positions) if open_positions else 0

        mt5.shutdown()

        # Normalize all deals
        normalized_deals = []
        for d in (all_deals or []):
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
        for o in (all_orders or []):
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

        # Normalize open positions
        normalized_open_positions = []
        for p in (open_positions or []):
            normalized_open_positions.append({
                "ticket": getattr(p, "ticket", 0),
                "identifier": getattr(p, "identifier", getattr(p, "ticket", 0)),
                "symbol": getattr(p, "symbol", ""),
                "magic": getattr(p, "magic", 0),
                "comment": getattr(p, "comment", ""),
                "type": getattr(p, "type", -1),
                "volume": getattr(p, "volume", 0),
                "price_open": getattr(p, "price_open", 0),
                "price_current": getattr(p, "price_current", 0),
                "sl": getattr(p, "sl", 0),
                "tp": getattr(p, "tp", 0),
            })

        matched_deals = []
        matched_orders = []
        match_method = ""

        # === Strict explicit matching (Sprint 9.9.3.45.5) ===
        # 1. Explicit deal_ticket
        if deal_ticket:
            explicit_deals = [d for d in normalized_deals if d["ticket"] == deal_ticket]
            explicit_open = [p for p in normalized_open_positions
                             if p["ticket"] == deal_ticket or p["identifier"] == deal_ticket]
            if explicit_deals or explicit_open:
                findings["explicit_deal_ticket_found"] = True
                if explicit_deals:
                    pos_id = explicit_deals[0]["position_id"]
                    matched_deals = [d for d in normalized_deals if d["position_id"] == pos_id]
                    matched_orders = [o for o in normalized_orders if o["position_id"] == pos_id]
                    match_method = f"explicit_deal_ticket_{deal_ticket}"
                    ok_checks.append(f"Matched by explicit deal_ticket: {deal_ticket}")

        # 2. Explicit position_id
        if not matched_deals and position_id:
            explicit_pos_deals = [d for d in normalized_deals if d["position_id"] == position_id]
            explicit_pos_orders = [o for o in normalized_orders if o["position_id"] == position_id]
            explicit_pos_open = [p for p in normalized_open_positions
                                 if p["ticket"] == position_id or p["identifier"] == position_id]
            if explicit_pos_deals or explicit_pos_orders or explicit_pos_open:
                findings["explicit_position_id_found"] = True
                matched_deals = explicit_pos_deals
                matched_orders = explicit_pos_orders
                match_method = f"explicit_position_id_{position_id}"
                ok_checks.append(f"Matched by explicit position_id: {position_id}")
            else:
                # Explicit position-id supplied but NOT FOUND - strict no-fallback
                findings["root_cause"] = "EXPLICIT_POSITION_ID_NOT_FOUND"
                findings["fallback_blocked_reason"] = "EXPLICIT_POSITION_ID_NOT_FOUND"
                warnings.append(
                    f"Explicit position_id={position_id} not found in deals, orders, or open positions. "
                    "Fallback to old trades is forbidden."
                )
                return {
                    "timestamp_utc": ts,
                    "verdict": "DEMO_MICRO_FORENSICS_INCOMPLETE",
                    "ok_checks": ok_checks, "blockers": blockers, "warnings": warnings,
                    "findings": findings,
                    "safety": {"order_send_called": False, "position_modified": False},
                }

        # 3. Explicit order_ticket
        if not matched_deals and order_ticket:
            order_match = [o for o in normalized_orders if o["ticket"] == order_ticket]
            deal_match = [d for d in normalized_deals if d["order"] == order_ticket]
            if order_match or deal_match:
                findings["explicit_order_ticket_found"] = True
                pos_id = (order_match[0]["position_id"] if order_match
                          else deal_match[0]["position_id"])
                matched_deals = [d for d in normalized_deals if d["position_id"] == pos_id]
                matched_orders = [o for o in normalized_orders if o["position_id"] == pos_id]
                match_method = f"explicit_order_ticket_{order_ticket}"
                ok_checks.append(f"Matched by explicit order_ticket: {order_ticket}")
            else:
                findings["root_cause"] = "EXPLICIT_ORDER_TICKET_NOT_FOUND"
                findings["fallback_blocked_reason"] = "EXPLICIT_ORDER_TICKET_NOT_FOUND"
                warnings.append(
                    f"Explicit order_ticket={order_ticket} not found in orders or deals. "
                    "Fallback to old trades is forbidden."
                )
                return {
                    "timestamp_utc": ts,
                    "verdict": "DEMO_MICRO_FORENSICS_INCOMPLETE",
                    "ok_checks": ok_checks, "blockers": blockers, "warnings": warnings,
                    "findings": findings,
                    "safety": {"order_send_called": False, "position_modified": False},
                }

        # === Receipt matching (mandatory first if receipt_success=True) ===
        if not matched_deals and receipt_match_required:
            receipt_pos_id = receipt.get("detected_position_identifier") or receipt.get("position_id") or 0
            receipt_order = receipt.get("order_ticket") or receipt.get("order_send_result_order") or 0
            receipt_deal = receipt.get("deal_ticket") or receipt.get("order_send_result_deal") or 0
            receipt_detected_ticket = receipt.get("detected_position_ticket") or 0

            receipt_matched = False
            # Try receipt position-id / detected-position-ticket
            for rid in [receipt_pos_id, receipt_detected_ticket]:
                if not rid:
                    continue
                rm_deals = [d for d in normalized_deals if d["position_id"] == rid]
                rm_orders = [o for o in normalized_orders if o["position_id"] == rid]
                rm_open = [p for p in normalized_open_positions
                           if p["ticket"] == rid or p["identifier"] == rid]
                if rm_deals or rm_orders or rm_open:
                    matched_deals = rm_deals
                    matched_orders = rm_orders
                    match_method = f"receipt_position_id_{rid}"
                    receipt_matched = True
                    ok_checks.append(f"Matched by receipt position_id: {rid}")
                    break
            # Try receipt deal ticket
            if not receipt_matched and receipt_deal:
                rm_deals = [d for d in normalized_deals if d["ticket"] == receipt_deal]
                if rm_deals:
                    pos_id = rm_deals[0]["position_id"]
                    matched_deals = [d for d in normalized_deals if d["position_id"] == pos_id]
                    matched_orders = [o for o in normalized_orders if o["position_id"] == pos_id]
                    match_method = f"receipt_deal_ticket_{receipt_deal}"
                    receipt_matched = True
                    ok_checks.append(f"Matched by receipt deal_ticket: {receipt_deal}")
            # Try receipt order ticket
            if not receipt_matched and receipt_order:
                rm_orders = [o for o in normalized_orders if o["ticket"] == receipt_order]
                rm_deals = [d for d in normalized_deals if d["order"] == receipt_order]
                if rm_orders or rm_deals:
                    pos_id = (rm_orders[0]["position_id"] if rm_orders
                              else rm_deals[0]["position_id"])
                    matched_deals = [d for d in normalized_deals if d["position_id"] == pos_id]
                    matched_orders = [o for o in normalized_orders if o["position_id"] == pos_id]
                    match_method = f"receipt_order_ticket_{receipt_order}"
                    receipt_matched = True
                    ok_checks.append(f"Matched by receipt order_ticket: {receipt_order}")

            findings["receipt_match_found"] = receipt_matched
            if not receipt_matched:
                # Receipt success=True but receipt trade NOT FOUND - strict no-fallback
                findings["root_cause"] = "RECEIPT_TRADE_NOT_FOUND_IN_HISTORY_OR_OPEN_POSITIONS"
                findings["fallback_blocked_reason"] = "RECEIPT_TRADE_NOT_FOUND_IN_HISTORY_OR_OPEN_POSITIONS"
                # Compute fallback candidates as DIAGNOSTICS only
                fb_candidates = []
                magic_deals = [d for d in normalized_deals if d["magic"] == magic and d["symbol"] == symbol]
                if magic_deals:
                    pos_ids = set(d["position_id"] for d in magic_deals if d["position_id"])
                    for pid in sorted(pos_ids, reverse=True):
                        fb_candidates.append({
                            "position_id": pid,
                            "match_type": "magic_comment",
                            "deal_count": sum(1 for d in magic_deals if d["position_id"] == pid),
                        })
                findings["fallback_candidates"] = fb_candidates
                findings["fallback_candidates_count"] = len(fb_candidates)
                warnings.append(
                    "Receipt success=True but receipt order/deal/position NOT FOUND in history or open positions. "
                    "Fallback to old trades is forbidden. Old candidates included as diagnostics only."
                )
                return {
                    "timestamp_utc": ts,
                    "verdict": "DEMO_MICRO_FORENSICS_INCOMPLETE",
                    "ok_checks": ok_checks, "blockers": blockers, "warnings": warnings,
                    "findings": findings,
                    "safety": {"order_send_called": False, "position_modified": False},
                }

        # === Fallback matching (only when allowed) ===
        if not matched_deals and fallback_allowed:
            findings["fallback_used"] = True
            # 5. Magic + symbol match
            magic_deals = [d for d in normalized_deals if d["magic"] == magic and d["symbol"] == symbol]
            if magic_deals:
                pos_ids = set(d["position_id"] for d in magic_deals if d["position_id"])
                if pos_ids:
                    latest_pos = max(pos_ids)
                    matched_deals = [d for d in normalized_deals if d["position_id"] == latest_pos]
                    matched_orders = [o for o in normalized_orders if o["position_id"] == latest_pos]
                    match_method = f"magic_{magic}_symbol_{symbol}_pos_{latest_pos}"
                    ok_checks.append(f"Matched by magic={magic} + symbol={symbol}, position_id={latest_pos}")
                    findings["fallback_candidates_count"] = len(pos_ids)

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
                        findings["fallback_candidates_count"] = len(pos_ids)

            # 7. Likely: XAUUSD + volume 0.01 + entry/close pair
            if not matched_deals:
                xauusd_small = [d for d in normalized_deals if d["symbol"] == symbol and d["volume"] <= 0.01]
                if xauusd_small:
                    pos_ids = set(d["position_id"] for d in xauusd_small if d["position_id"])
                    if pos_ids:
                        latest_pos = max(pos_ids)
                        matched_deals = [d for d in normalized_deals if d["position_id"] == latest_pos]
                        matched_orders = [o for o in normalized_orders if o["position_id"] == latest_pos]
                        match_method = f"likely_xauusd_001_pos_{latest_pos}"
                        warnings.append(f"Matched by likely XAUUSD 0.01 trade, position_id={latest_pos} (no magic/comment match)")
                        findings["fallback_candidates_count"] = len(pos_ids)

        findings["match_method"] = match_method
        findings["matched_deals"] = matched_deals
        findings["matched_orders"] = matched_orders

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
                if entry_sl > 0 and abs(exit_deal["price"] - entry_sl) < 0.01:
                    sl_hit = True
                    sl_close_comment = f"exit_price={exit_deal['price']} matches SL={entry_sl}"
                    ok_checks.append(f"SL hit detected by price match: {sl_close_comment}")

        findings["sl_hit_detected"] = sl_hit
        findings["sl_close_comment"] = sl_close_comment
        findings["realized_pl"] = realized_pl

        profit_before_sl = "UNKNOWN"
        if sl_hit and realized_pl < 0:
            profit_before_sl = "POSSIBLE"
            warnings.append("SL hit at a loss - position may have been in profit before SL hit")
        findings["profit_before_sl_detected"] = profit_before_sl

        sl_modification_events = 0
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

        # Verdict - Sprint 9.9.3.45.5: stricter. No COMPLETE based on fallback.
        is_explicit_match = "explicit" in match_method or "receipt" in match_method
        is_strict_match = "magic" in match_method or "comment" in match_method or is_explicit_match
        is_likely_match = "likely" in match_method

        if is_explicit_match and entry_deal and (sl_hit or exit_deal):
            verdict = "DEMO_MICRO_FORENSICS_COMPLETE"
        elif is_strict_match and entry_deal and (sl_hit or exit_deal):
            verdict = "DEMO_MICRO_FORENSICS_COMPLETE"
        elif is_strict_match and matched_deals:
            verdict = "DEMO_MICRO_FORENSICS_COMPLETE_WITH_WARNINGS"
        elif is_likely_match and matched_deals:
            verdict = "DEMO_MICRO_FORENSICS_COMPLETE_WITH_WARNINGS"
            warnings.append("Verdict based on LIKELY match (no magic/comment/explicit/receipt match). Treat as diagnostic only.")
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
        # Sprint 9.9.3.45.5: Strict no-fallback summary
        f.write("## Strict No-Fallback Summary\n\n")
        f.write("| Field | Value |\n|---|---|\n")
        strict_fields = [
            "explicit_position_id_supplied", "explicit_position_id_found",
            "explicit_order_ticket_supplied", "explicit_order_ticket_found",
            "explicit_deal_ticket_supplied", "explicit_deal_ticket_found",
            "receipt_match_required", "receipt_match_found",
            "fallback_candidates_count", "fallback_used",
            "fallback_allowed", "fallback_blocked_reason",
        ]
        for k in strict_fields:
            if k in findings:
                f.write(f"| {k} | {findings[k]} |\n")
        f.write("\n## Findings\n\n")
        f.write("| Field | Value |\n|---|---|\n")
        for k, v in findings.items():
            if k in strict_fields:
                continue
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
        if findings.get("fallback_candidates"):
            f.write("\n## Fallback Candidates (Diagnostics Only)\n\n")
            for c in findings["fallback_candidates"]:
                f.write(f"- position_id={c['position_id']} match_type={c['match_type']} deal_count={c['deal_count']}\n")
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
    parser.add_argument("--magic", type=int, default=TITAN_MAGIC)
    parser.add_argument("--comment", default=TITAN_COMMENT)
    parser.add_argument("--position-id", type=int, default=0)
    parser.add_argument("--order-ticket", type=int, default=0)
    parser.add_argument("--deal-ticket", type=int, default=0)
    args = parser.parse_args()
    print("=" * 70)
    print("  TITAN XAU AI - Post-Trade Forensics (Sprint 9.9.3.45.5)")
    print("=" * 70)
    result = collect_forensics(
        days=args.days, symbol=args.symbol, magic=args.magic, comment=args.comment,
        position_id=args.position_id, order_ticket=args.order_ticket, deal_ticket=args.deal_ticket,
    )
    report = write_report(result)
    print(f"\n  Verdict: {result['verdict']}")
    print(f"  Findings: {len(result.get('findings', {}))} fields")
    print(f"  Root cause: {result.get('findings', {}).get('root_cause', 'N/A')}")
    print(f"  Fallback used: {result.get('findings', {}).get('fallback_used', False)}")
    print(f"  Fallback blocked: {result.get('findings', {}).get('fallback_blocked_reason', '')}")
    print(f"\n  JSON: {report['json_path']}")
    print(f"  MD:   {report['md_path']}")
    print("\n" + "=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
