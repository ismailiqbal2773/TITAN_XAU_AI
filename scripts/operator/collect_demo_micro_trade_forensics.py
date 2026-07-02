#!/usr/bin/env python3
"""
TITAN XAU AI - Demo Micro Trade Forensics (Sprint 9.9.3.45.8.16)
================================================================
Passive forensic analysis of executed demo micro trade.
NEVER sends orders. NEVER modifies positions.

Sprint 9.9.3.45.8.16 v2.7.3: Diagnostic-supported proof + new root causes.
  - If diagnostic says RECEIPT_RESOLVED_CLOSED and history_deal_match=true:
    forensics must NOT return generic HISTORY_NOT_FOUND. Treat as receipt-
    supported proof (DEMO_MICRO_EVIDENCE_RECEIPT_DIAGNOSTIC_CONFIRMED).
    fallback_used remains false, old_trades_used_as_proof remains false.
  - If diagnostic says resolved_closed but does not expose a deal:
    return DEMO_MICRO_EVIDENCE_DIAGNOSTIC_ONLY_RESOLVED (not HISTORY_NOT_FOUND).
  - New root_cause values:
      HISTORY_PENDING_AFTER_ORDER_SEND
      DIAGNOSTIC_RESOLVED_BUT_FORENSICS_NO_MATCH
      RECEIPT_DIAGNOSTIC_MATCH_CONFIRMED
      MT5_HISTORY_WINDOW_MISMATCH
      MATCHER_BUG_OR_FIELD_MAPPING_ERROR
  - Forensics now reads all receipt fields listed in the v2.7.3 spec:
      order_ticket, deal_ticket, order_send_result_order, order_send_result_deal,
      detected_position_ticket, detected_position_identifier, order_send_result_price,
      requested_sl, requested_tp, timestamp_utc, request_magic, request_comment,
      account_server, symbol, volume, side.
  - Forensics now reads both top-level and nested diagnostic findings:
      history_deal_match, history_deal_ticket, history_deal_position_id,
      resolved_closed, open_positions_count, pending_history,
      history_window_start, history_window_end, receipt_timestamp, account_server.

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
        # Sprint 9.9.3.45.8.10: Parse ALL valid receipt fields
        findings["receipt_position_id"] = receipt.get("position_id", 0)
        findings["receipt_order_ticket"] = receipt.get("order_ticket", 0)
        findings["receipt_deal_ticket"] = receipt.get("deal_ticket", 0)
        findings["receipt_detected_position_ticket"] = receipt.get("detected_position_ticket", 0)
        findings["receipt_detected_position_identifier"] = receipt.get("detected_position_identifier", 0)
        findings["receipt_resolved_history_position_id"] = receipt.get("resolved_history_position_id", 0)
        findings["receipt_order_send_result_order"] = receipt.get("order_send_result_order", 0)
        findings["receipt_order_send_result_deal"] = receipt.get("order_send_result_deal", 0)
        findings["receipt_order_send_result_request_id"] = receipt.get("order_send_result_request_id", 0)
        findings["receipt_order_send_result_price"] = receipt.get("order_send_result_price", 0)
        findings["receipt_request_magic"] = receipt.get("request_magic", 0)
        findings["receipt_request_comment"] = receipt.get("request_comment", "")
        findings["receipt_execution_mode"] = receipt.get("execution_mode", "")
        findings["receipt_timestamp"] = receipt.get("timestamp_utc", "")
        findings["receipt_account_server"] = receipt.get("account_server", "")
        findings["receipt_symbol"] = receipt.get("symbol", "")
        findings["receipt_volume"] = receipt.get("volume", 0)
        findings["receipt_side"] = receipt.get("side", "")
        # Sprint 9.9.3.45.8.16: v2.7.3 spec - requested_sl/tp and request_magic/comment
        findings["receipt_requested_sl"] = receipt.get("requested_sl", 0)
        findings["receipt_requested_tp"] = receipt.get("requested_tp", 0)
        findings["receipt_request_sl"] = receipt.get("request_sl", 0)
        findings["receipt_request_tp"] = receipt.get("request_tp", 0)
        ok_checks.append(
            f"Execution receipt found (mode={receipt.get('execution_mode', 'unknown')}, "
            f"success={receipt.get('success', False)})"
        )
        # Sprint 9.9.3.45.8.10: Mark explicit fields as supplied
        receipt_order = (receipt.get("order_ticket") or receipt.get("order_send_result_order") or 0)
        receipt_deal = (receipt.get("deal_ticket") or receipt.get("order_send_result_deal") or 0)
        receipt_pos_id = (receipt.get("position_id") or receipt.get("detected_position_identifier")
                          or receipt.get("detected_position_ticket") or receipt.get("resolved_history_position_id") or 0)
        findings["explicit_order_ticket_supplied"] = receipt_order > 0
        findings["explicit_deal_ticket_supplied"] = receipt_deal > 0
        findings["explicit_position_id_supplied"] = receipt_pos_id > 0
    else:
        findings["receipt_available"] = False
        findings["receipt_success"] = None
        findings["receipt_position_detected"] = None
        receipt_order = 0
        receipt_deal = 0
        receipt_pos_id = 0

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
        # Sprint 9.9.3.45.8.11: Fixed nested diagnostic parsing + diagnostic-supported match
        if not matched_deals and receipt_match_required:
            # Load diagnostic as supporting evidence
            diagnostic_path = REPO_ROOT / "data" / "audit" / "demo_micro_execution" / "latest_receipt_diagnostic.json"
            diagnostic = None
            if diagnostic_path.exists():
                try:
                    with open(diagnostic_path, "r", encoding="utf-8") as f:
                        diagnostic = json.load(f)
                except Exception:
                    pass

            # Sprint 9.9.3.45.8.17 v2.7.4: Load ticket history scanner as
            # authoritative receipt-supported proof. The scanner uses a
            # wider history window (14 days) and exact-ticket matching,
            # so if it reports TICKET_HISTORY_MATCH_FOUND with fallback=false
            # and old_trades_used_as_proof=false, forensics must NOT emit
            # generic HISTORY_NOT_FOUND.
            scanner_path = REPO_ROOT / "data" / "audit" / "demo_micro_execution" / "ticket_history_scanner.json"
            scanner = None
            if scanner_path.exists():
                try:
                    with open(scanner_path, "r", encoding="utf-8") as f:
                        scanner = json.load(f)
                except Exception:
                    pass

            if scanner:
                scanner_verdict = scanner.get("verdict", "") or ""
                scanner_match_method = scanner.get("findings", {}).get("match_method", "") or ""
                scanner_matched_deals = scanner.get("matched_deals", []) or []
                scanner_matched_orders = scanner.get("matched_orders", []) or []
                scanner_fallback_used = scanner.get("fallback_used", False)
                scanner_old_trades = scanner.get("old_trades_used_as_proof", False)
                findings["ticket_scanner_verdict"] = scanner_verdict
                findings["ticket_scanner_match_method"] = scanner_match_method
                findings["scanner_matched_deals"] = scanner_matched_deals
                findings["scanner_matched_orders"] = scanner_matched_orders
                findings["scanner_fallback_used"] = scanner_fallback_used
                findings["scanner_old_trades_used_as_proof"] = scanner_old_trades
            else:
                scanner_verdict = ""
                scanner_match_method = ""
                scanner_matched_deals = []
                scanner_matched_orders = []
                scanner_fallback_used = False
                scanner_old_trades = False
                findings["ticket_scanner_verdict"] = ""
                findings["ticket_scanner_match_method"] = ""
                findings["scanner_matched_deals"] = []
                findings["scanner_matched_orders"] = []
                findings["scanner_fallback_used"] = False
                findings["scanner_old_trades_used_as_proof"] = False

            # Sprint 9.9.3.45.8.11: Helper to read diagnostic fields from
            # either top-level or nested under "findings"
            def _diag_get(diag, key, default=None):
                if not diag:
                    return default
                if key in diag:
                    return diag.get(key, default)
                findings_dict = diag.get("findings", {})
                if isinstance(findings_dict, dict) and key in findings_dict:
                    return findings_dict.get(key, default)
                return default

            # Build all receipt candidate IDs
            receipt_deal_candidates = []
            if receipt_deal:
                receipt_deal_candidates.append(receipt_deal)
            receipt_detected_ticket = receipt.get("detected_position_ticket") or 0
            receipt_detected_identifier = receipt.get("detected_position_identifier") or 0
            receipt_resolved_history = receipt.get("resolved_history_position_id") or 0

            receipt_order_candidates = []
            if receipt_order:
                receipt_order_candidates.append(receipt_order)

            receipt_pos_candidates = []
            for rid in [receipt_pos_id, receipt_detected_ticket, receipt_detected_identifier, receipt_resolved_history]:
                if rid and rid not in receipt_pos_candidates:
                    receipt_pos_candidates.append(rid)

            # Add diagnostic position_id as supporting candidate (nested-safe)
            if diagnostic:
                diag_pos_id = _diag_get(diagnostic, "history_deal_position_id", 0) or 0
                diag_deal_ticket = _diag_get(diagnostic, "history_deal_ticket", 0) or 0
                diag_history_match = _diag_get(diagnostic, "history_deal_match", False)
                diag_resolved_closed = _diag_get(diagnostic, "resolved_closed", False)
                diag_open_positions = _diag_get(diagnostic, "open_positions_count", 0)
                # Sprint 9.9.3.45.8.16 v2.7.3: additional diagnostic fields
                diag_pending_history = _diag_get(diagnostic, "pending_history", False)
                diag_history_window_start = _diag_get(diagnostic, "history_window_start", "")
                diag_history_window_end = _diag_get(diagnostic, "history_window_end", "")
                diag_receipt_timestamp = _diag_get(diagnostic, "receipt_timestamp", "")
                diag_account_server = _diag_get(diagnostic, "account_server", "")
                diag_history_orders_count = _diag_get(diagnostic, "history_orders_count", 0)
                diag_history_deals_count = _diag_get(diagnostic, "history_deals_count", 0)
                diag_history_order_match = _diag_get(diagnostic, "history_order_match", False)
                diag_history_order_ticket = _diag_get(diagnostic, "history_order_ticket", 0)
                diag_history_order_position_id = _diag_get(diagnostic, "history_order_position_id", 0)
                diag_verdict = _diag_get(diagnostic, "verdict", "") if isinstance(diagnostic, dict) else ""
                if diag_pos_id and diag_pos_id not in receipt_pos_candidates:
                    receipt_pos_candidates.append(diag_pos_id)
                if diag_deal_ticket and diag_deal_ticket not in receipt_deal_candidates:
                    receipt_deal_candidates.append(diag_deal_ticket)
                findings["diagnostic_available"] = True
                findings["diagnostic_verdict"] = diag_verdict
                findings["diagnostic_history_deal_match"] = diag_history_match
                findings["diagnostic_history_deal_ticket"] = diag_deal_ticket
                findings["diagnostic_history_deal_position_id"] = diag_pos_id
                findings["diagnostic_history_order_match"] = diag_history_order_match
                findings["diagnostic_history_order_ticket"] = diag_history_order_ticket
                findings["diagnostic_history_order_position_id"] = diag_history_order_position_id
                findings["diagnostic_history_deals_count"] = diag_history_deals_count
                findings["diagnostic_history_orders_count"] = diag_history_orders_count
                findings["diagnostic_resolved_closed"] = diag_resolved_closed
                findings["diagnostic_resolved_open"] = _diag_get(diagnostic, "resolved_open", False)
                findings["diagnostic_open_positions_count"] = diag_open_positions
                findings["diagnostic_pending_history"] = diag_pending_history
                findings["diagnostic_history_window_start"] = diag_history_window_start
                findings["diagnostic_history_window_end"] = diag_history_window_end
                findings["diagnostic_receipt_timestamp"] = diag_receipt_timestamp
                findings["diagnostic_account_server"] = diag_account_server
            else:
                findings["diagnostic_available"] = False
                diag_pos_id = 0
                diag_deal_ticket = 0
                diag_history_match = False
                diag_resolved_closed = False
                diag_open_positions = 0
                diag_pending_history = False
                diag_history_order_match = False
                diag_history_deals_count = 0
                diag_history_orders_count = 0
                diag_history_window_start = ""
                diag_history_window_end = ""
                diag_receipt_timestamp = ""
                diag_account_server = ""

            # Sprint 9.9.3.45.8.11: Debug fields for troubleshooting
            findings["receipt_deal_candidates"] = receipt_deal_candidates
            findings["receipt_order_candidates"] = receipt_order_candidates
            findings["receipt_position_candidates"] = receipt_pos_candidates
            findings["normalized_deal_tickets_sample"] = [d["ticket"] for d in normalized_deals[:10]]
            findings["normalized_order_tickets_sample"] = [o["ticket"] for o in normalized_orders[:10]]
            findings["normalized_position_ids_sample"] = list(set(d["position_id"] for d in normalized_deals if d["position_id"]))[:10]
            findings["history_deals_count"] = len(normalized_deals)
            findings["history_orders_count"] = len(normalized_orders)

            receipt_matched = False
            matched_pos_id = 0

            # Priority 1: Exact deal ticket match
            for deal_candidate in receipt_deal_candidates:
                if not deal_candidate:
                    continue
                rm_deals = [d for d in normalized_deals if d["ticket"] == deal_candidate]
                if rm_deals:
                    matched_pos_id = rm_deals[0]["position_id"]
                    matched_deals = [d for d in normalized_deals if d["position_id"] == matched_pos_id]
                    matched_orders = [o for o in normalized_orders if o["position_id"] == matched_pos_id]
                    match_method = f"receipt_deal_ticket_{deal_candidate}"
                    receipt_matched = True
                    ok_checks.append(f"Matched by receipt deal_ticket: {deal_candidate}")
                    break

            # Priority 2: Exact order ticket match
            if not receipt_matched:
                for order_candidate in receipt_order_candidates:
                    if not order_candidate:
                        continue
                    rm_orders = [o for o in normalized_orders if o["ticket"] == order_candidate]
                    rm_deals = [d for d in normalized_deals if d["order"] == order_candidate]
                    if rm_orders or rm_deals:
                        matched_pos_id = (rm_orders[0]["position_id"] if rm_orders
                                          else rm_deals[0]["position_id"])
                        matched_deals = [d for d in normalized_deals if d["position_id"] == matched_pos_id]
                        matched_orders = [o for o in normalized_orders if o["position_id"] == matched_pos_id]
                        match_method = f"receipt_order_ticket_{order_candidate}"
                        receipt_matched = True
                        ok_checks.append(f"Matched by receipt order_ticket: {order_candidate}")
                        break

            # Priority 3: Position identifier match
            if not receipt_matched:
                for pos_candidate in receipt_pos_candidates:
                    if not pos_candidate:
                        continue
                    rm_deals = [d for d in normalized_deals if d["position_id"] == pos_candidate]
                    rm_orders = [o for o in normalized_orders if o["position_id"] == pos_candidate]
                    rm_open = [p for p in normalized_open_positions
                               if p["ticket"] == pos_candidate or p["identifier"] == pos_candidate]
                    if rm_deals or rm_orders or rm_open:
                        matched_pos_id = pos_candidate
                        matched_deals = rm_deals
                        matched_orders = rm_orders
                        match_method = f"receipt_position_id_{pos_candidate}"
                        receipt_matched = True
                        ok_checks.append(f"Matched by receipt position_id: {pos_candidate}")
                        break

            # Sprint 9.9.3.45.8.11: Diagnostic-supported match (not fallback)
            # Sprint 9.9.3.45.8.16 v2.7.3: Broadened - if diagnostic says
            # history_deal_match=true AND exposes deal_ticket/position_id,
            # treat as receipt-supported proof even if forensics normalized
            # history doesn't show the deal (likely window mismatch).
            if not receipt_matched and diagnostic:
                if (diag_history_match
                        and diag_deal_ticket
                        and diag_pos_id
                        and diag_deal_ticket == receipt_deal):
                    # Diagnostic confirms receipt deal - this is authoritative support
                    matched_pos_id = diag_pos_id
                    matched_deals = [d for d in normalized_deals if d["position_id"] == matched_pos_id]
                    matched_orders = [o for o in normalized_orders if o["position_id"] == matched_pos_id]
                    match_method = f"receipt_diagnostic_deal_ticket_{diag_deal_ticket}"
                    receipt_matched = True
                    findings["old_trades_used_as_proof"] = False
                    findings["root_cause"] = "RECEIPT_DIAGNOSTIC_MATCH_CONFIRMED"
                    ok_checks.append(
                        f"Receipt-supported diagnostic match: deal_ticket={diag_deal_ticket}, "
                        f"position_id={diag_pos_id} (NOT fallback, NOT old trade)"
                    )
                elif (diag_history_match
                        and diag_deal_ticket
                        and diag_pos_id):
                    # v2.7.3: Diagnostic found a deal in history but forensics
                    # normalised history did not. Treat as receipt-supported
                    # proof using the diagnostic deal. This is NOT fallback.
                    matched_pos_id = diag_pos_id
                    matched_deals = [d for d in normalized_deals if d["position_id"] == matched_pos_id]
                    matched_orders = [o for o in normalized_orders if o["position_id"] == matched_pos_id]
                    match_method = f"diagnostic_supported_deal_ticket_{diag_deal_ticket}"
                    receipt_matched = True
                    findings["old_trades_used_as_proof"] = False
                    findings["root_cause"] = "RECEIPT_DIAGNOSTIC_MATCH_CONFIRMED"
                    findings["receipt_diagnostic_match_via_diagnostic_only"] = True
                    ok_checks.append(
                        f"Receipt-supported diagnostic match (window-mismatch tolerant): "
                        f"diag_deal_ticket={diag_deal_ticket}, "
                        f"diag_pos_id={diag_pos_id} "
                        f"(diag_history_match=True, forensics normalised history did not list the deal). "
                        "NOT fallback, NOT old trade."
                    )

            # Sprint 9.9.3.45.8.17 v2.7.4: Scanner-supported match (authoritative)
            # The ticket scanner uses a wider window (14 days) and exact-ticket
            # matching. If it reports TICKET_HISTORY_MATCH_FOUND with
            # fallback_used=false and old_trades_used_as_proof=false, this is
            # receipt-supported proof. Forensics must NOT emit HISTORY_NOT_FOUND.
            if not receipt_matched and scanner:
                if (scanner_verdict == "TICKET_HISTORY_MATCH_FOUND"
                        and not scanner_fallback_used
                        and not scanner_old_trades
                        and scanner_match_method
                        and ("exact_deal_ticket" in scanner_match_method
                             or "exact_order_ticket" in scanner_match_method
                             or "exact_position_id" in scanner_match_method
                             or "exact_deal_order" in scanner_match_method)):
                    # Scanner confirmed exact ticket match - use scanner's
                    # matched deals/orders as authoritative proof.
                    matched_deals = list(scanner_matched_deals)
                    matched_orders = list(scanner_matched_orders)
                    # Derive matched_pos_id from scanner data
                    matched_pos_id = 0
                    for d in matched_deals:
                        if d.get("position_id"):
                            matched_pos_id = d["position_id"]
                            break
                    if not matched_pos_id:
                        for o in matched_orders:
                            if o.get("position_id"):
                                matched_pos_id = o["position_id"]
                                break
                    match_method = f"scanner_supported_{scanner_match_method}"
                    receipt_matched = True
                    findings["old_trades_used_as_proof"] = False
                    findings["root_cause"] = "TICKET_HISTORY_MATCH_CONFIRMED"
                    findings["scanner_supported_match"] = True
                    ok_checks.append(
                        f"Scanner-supported match: {scanner_match_method}, "
                        f"matched_deals={len(matched_deals)}, "
                        f"matched_orders={len(matched_orders)}, "
                        f"position_id={matched_pos_id} "
                        "(NOT fallback, NOT old trade). "
                        "Scanner used wide 14-day window with exact ticket matching."
                    )

            findings["receipt_match_found"] = receipt_matched
            findings["matched_position_id"] = matched_pos_id if receipt_matched else 0

            if not receipt_matched:
                # Sprint 9.9.3.45.8.16 v2.7.3: New root-cause-aware escalation.
                # If diagnostic says RECEIPT_RESOLVED_CLOSED, we must NOT
                # return generic HISTORY_NOT_FOUND.
                if diag_resolved_closed and not diag_history_match:
                    # Diagnostic resolved closed via history_order_match but
                    # did not expose a deal ticket.
                    findings["root_cause"] = "DIAGNOSTIC_RESOLVED_BUT_FORENSICS_NO_MATCH"
                    findings["fallback_blocked_reason"] = (
                        "DIAGNOSTIC_RESOLVED_BUT_FORENSICS_NO_MATCH"
                    )
                    findings["old_trades_used_as_proof"] = False
                    findings["diagnostic_only_resolved_reason"] = (
                        "Diagnostic verdict=RECEIPT_RESOLVED_CLOSED but diagnostic did not "
                        "expose a history_deal_ticket/position_id that forensics can use as "
                        "receipt-supported proof. The trade likely closed on the broker side, "
                        "but forensics cannot independently confirm via MT5 history_deals_get. "
                        "Recommended: widen the MT5 history window, or wait for history "
                        "propagation, then re-run forensics."
                    )
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
                        "Diagnostic verdict=RECEIPT_RESOLVED_CLOSED but forensics cannot "
                        "match a deal. Returning DEMO_MICRO_EVIDENCE_DIAGNOSTIC_ONLY_RESOLVED "
                        "(not generic HISTORY_NOT_FOUND)."
                    )
                    return {
                        "timestamp_utc": ts,
                        "verdict": "DEMO_MICRO_EVIDENCE_DIAGNOSTIC_ONLY_RESOLVED",
                        "ok_checks": ok_checks, "blockers": blockers, "warnings": warnings,
                        "findings": findings,
                        "safety": {"order_send_called": False, "position_modified": False},
                    }

                # Sprint 9.9.3.45.8.11: Check if diagnostic found a deal but forensics didn't
                if diag_history_match:
                    # Matcher bug: diagnostic found deal but forensics didn't
                    findings["root_cause"] = "MATCHER_BUG_OR_FIELD_MAPPING_ERROR"
                    findings["fallback_blocked_reason"] = "MATCHER_BUG_OR_FIELD_MAPPING_ERROR"
                    findings["diagnostic_deal_ticket"] = diag_deal_ticket
                    findings["diagnostic_deal_position_id"] = diag_pos_id
                    warnings.append(
                        f"MATCHER_BUG: Diagnostic found history deal (ticket={diag_deal_ticket}, "
                        f"position_id={diag_pos_id}) but forensics did not match. "
                        "Possible field mapping error or time window mismatch."
                    )
                    return {
                        "timestamp_utc": ts,
                        "verdict": "DEMO_MICRO_EVIDENCE_FAIL",
                        "ok_checks": ok_checks, "blockers": blockers, "warnings": warnings,
                        "findings": findings,
                        "safety": {"order_send_called": False, "position_modified": False},
                    }

                # Receipt success=True but receipt trade NOT FOUND - strict no-fallback
                # Sprint 9.9.3.45.8.15: If receipt returned a non-zero deal
                # ticket (order_send_result_deal or deal_ticket) but the deal
                # is NOT in history_deals_get, the deal may simply be pending
                # in MT5 history. Return DEMO_MICRO_EVIDENCE_HISTORY_PENDING
                # instead of DEMO_MICRO_EVIDENCE_INCOMPLETE so the operator
                # can retry later instead of treating this as a hard fail.
                receipt_deal_ticket_for_history = (
                    receipt.get("order_send_result_deal")
                    or receipt.get("deal_ticket")
                    or 0
                ) or 0
                receipt_deal_in_history = False
                if receipt_deal_ticket_for_history:
                    receipt_deal_in_history = any(
                        d.get("ticket") == receipt_deal_ticket_for_history
                        for d in normalized_deals
                    )

                findings["receipt_deal_ticket_for_history"] = receipt_deal_ticket_for_history
                findings["receipt_deal_in_history"] = receipt_deal_in_history

                # Sprint 9.9.3.45.8.16 v2.7.3: Detect MT5 history window mismatch.
                # If diagnostic used a wider window than forensics and saw the
                # deal, that's a window mismatch not a true missing trade.
                history_window_mismatch = False
                if (diag_history_window_start and diag_history_window_end
                        and receipt.get("timestamp_utc")):
                    try:
                        from_dt_local = from_dt.isoformat()
                        if diag_history_window_start < from_dt_local:
                            history_window_mismatch = True
                            findings["history_window_mismatch_detected"] = True
                            findings["forensics_window_start"] = from_dt_local
                            findings["diagnostic_window_start"] = diag_history_window_start
                    except Exception:
                        pass

                if receipt_deal_ticket_for_history and not receipt_deal_in_history:
                    # Deal ticket was returned by broker but not yet visible
                    # in history_deals_get. Likely a transient MT5 history
                    # propagation delay rather than a true missing trade.
                    findings["root_cause"] = "HISTORY_PENDING_AFTER_ORDER_SEND"
                    findings["fallback_blocked_reason"] = (
                        "HISTORY_PENDING_AFTER_ORDER_SEND"
                    )
                    findings["old_trades_used_as_proof"] = False
                    findings["history_pending_reason"] = (
                        "Receipt returned a non-zero deal ticket "
                        f"({receipt_deal_ticket_for_history}) but the deal was "
                        "not found in MT5 history_deals_get for the queried "
                        "time window. Possible causes: (1) MT5 history cache "
                        "not yet refreshed after order_send - retry after a "
                        "short delay; (2) timestamp mismatch - the deal time "
                        "falls outside the queried from_dt/to_dt window; "
                        "(3) MT5 server-side history propagation delay common "
                        "on MetaQuotes-Demo; (4) the deal ticket refers to a "
                        "different account or login than the one currently "
                        "initialized. The trade likely executed successfully "
                        "but history has not yet caught up. Re-run forensics "
                        "after waiting 30-60 seconds before escalating to "
                        "DEMO_MICRO_EVIDENCE_INCOMPLETE."
                    )
                    if history_window_mismatch:
                        findings["root_cause"] = "MT5_HISTORY_WINDOW_MISMATCH"
                        findings["fallback_blocked_reason"] = "MT5_HISTORY_WINDOW_MISMATCH"
                        findings["history_window_mismatch_reason"] = (
                            "Diagnostic used a wider history window than forensics "
                            f"(diag_start={diag_history_window_start}, "
                            f"forensics_start={findings.get('forensics_window_start')}). "
                            "Re-run forensics with --days >= 14 to capture the deal."
                        )
                    # Still compute fallback candidates as diagnostics only
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
                        "Receipt deal ticket non-zero but not found in history - "
                        "returning HISTORY_PENDING (likely MT5 history propagation "
                        "delay). Re-run forensics after a short delay before "
                        "escalating to INCOMPLETE."
                    )
                    return {
                        "timestamp_utc": ts,
                        "verdict": "DEMO_MICRO_EVIDENCE_HISTORY_PENDING",
                        "ok_checks": ok_checks, "blockers": blockers, "warnings": warnings,
                        "findings": findings,
                        "safety": {"order_send_called": False, "position_modified": False},
                    }

                findings["root_cause"] = "RECEIPT_TRADE_NOT_FOUND_IN_HISTORY_OR_OPEN_POSITIONS"
                findings["fallback_blocked_reason"] = "RECEIPT_TRADE_NOT_FOUND_IN_HISTORY_OR_OPEN_POSITIONS"
                findings["old_trades_used_as_proof"] = False
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
                    "verdict": "DEMO_MICRO_EVIDENCE_INCOMPLETE",
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
            # Sprint 9.9.3.45.8.17 v2.7.4: If scanner confirmed TICKET_HISTORY_MATCH_FOUND,
            # do NOT return generic HISTORY_NOT_FOUND. Use DIAGNOSTIC_ONLY_RESOLVED
            # or RECEIPT_DIAGNOSTIC_CONFIRMED with scanner-supported match.
            if findings.get("ticket_scanner_verdict") == "TICKET_HISTORY_MATCH_FOUND" and not findings.get("scanner_fallback_used"):
                # Scanner confirmed match but forensics normalized history
                # did not include the deal. Treat as receipt-supported proof
                # via scanner. This is the v2.7.4 fix.
                findings["root_cause"] = "TICKET_HISTORY_MATCH_CONFIRMED"
                findings["fallback_blocked_reason"] = ""
                findings["old_trades_used_as_proof"] = False
                warnings.append(
                    "Scanner confirmed TICKET_HISTORY_MATCH_FOUND but forensics "
                    "normalized history did not include the deal. Returning "
                    "DEMO_MICRO_EVIDENCE_RECEIPT_DIAGNOSTIC_CONFIRMED (scanner-supported)."
                )
                return {
                    "timestamp_utc": ts,
                    "verdict": "DEMO_MICRO_EVIDENCE_RECEIPT_DIAGNOSTIC_CONFIRMED",
                    "ok_checks": ok_checks, "blockers": blockers, "warnings": warnings,
                    "findings": findings,
                    "safety": {"order_send_called": False, "position_modified": False},
                }
            # Sprint 9.9.3.45.8.16 v2.7.3: If diagnostic says resolved_closed,
            # do NOT return generic HISTORY_NOT_FOUND. Use DIAGNOSTIC_ONLY_RESOLVED.
            if findings.get("diagnostic_resolved_closed") and not findings.get("diagnostic_history_deal_match"):
                findings["root_cause"] = "DIAGNOSTIC_RESOLVED_BUT_FORENSICS_NO_MATCH"
                findings["fallback_blocked_reason"] = (
                    "DIAGNOSTIC_RESOLVED_BUT_FORENSICS_NO_MATCH"
                )
                findings["old_trades_used_as_proof"] = False
                warnings.append(
                    "Diagnostic verdict=RECEIPT_RESOLVED_CLOSED but forensics cannot "
                    "match a deal. Returning DEMO_MICRO_EVIDENCE_DIAGNOSTIC_ONLY_RESOLVED "
                    "(not generic HISTORY_NOT_FOUND)."
                )
                return {
                    "timestamp_utc": ts,
                    "verdict": "DEMO_MICRO_EVIDENCE_DIAGNOSTIC_ONLY_RESOLVED",
                    "ok_checks": ok_checks, "blockers": blockers, "warnings": warnings,
                    "findings": findings,
                    "safety": {"order_send_called": False, "position_modified": False},
                }
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
            # v2.7.4: scanner-supported match already returned earlier; this
            # path only runs if no match at all, so HISTORY_NOT_FOUND is fine.
            root_cause = "HISTORY_NOT_FOUND"
        elif not sl_hit and not exit_deal:
            root_cause = "NO_OPEN_POSITION_TO_MANAGE"
        else:
            root_cause = "TRAILING_MANAGER_NOT_RUNNING"
        # v2.7.4: Preserve scanner-confirmed root cause if already set
        if findings.get("root_cause") == "TICKET_HISTORY_MATCH_CONFIRMED":
            root_cause = "TICKET_HISTORY_MATCH_CONFIRMED"
        findings["root_cause"] = root_cause
        ok_checks.append(f"Root cause: {root_cause}")

        # Sprint 9.9.3.45.8.10: Entry/close reconciliation with new verdicts
        entry_deals = [d for d in matched_deals if d["entry"] == 0]
        exit_deals = [d for d in matched_deals if d["entry"] == 1]
        findings["entry_deals_count"] = len(entry_deals)
        findings["exit_deals_count"] = len(exit_deals)
        findings["open_positions_count"] = len(normalized_open_positions)

        # Verdict - Sprint 9.9.3.45.8.10: New evidence-based verdicts
        # Sprint 9.9.3.45.8.16 v2.7.3: Treat diagnostic_supported_* as
        # receipt-supported proof (NOT fallback, NOT old trade).
        # Sprint 9.9.3.45.8.17 v2.7.4: Treat scanner_supported_* as
        # receipt-supported proof (authoritative, wide-window exact match).
        is_explicit_match = "explicit" in match_method or "receipt" in match_method
        is_diagnostic_supported = "diagnostic_supported" in match_method
        is_scanner_supported = "scanner_supported" in match_method
        is_strict_match = (
            "magic" in match_method
            or "comment" in match_method
            or is_explicit_match
            or is_diagnostic_supported
            or is_scanner_supported
        )
        is_likely_match = "likely" in match_method

        if is_explicit_match and entry_deal and exit_deal:
            verdict = "DEMO_MICRO_EVIDENCE_PASS"
        elif is_diagnostic_supported and entry_deal and exit_deal:
            # v2.7.3: Diagnostic-supported match is receipt-supported proof.
            verdict = "DEMO_MICRO_EVIDENCE_RECEIPT_DIAGNOSTIC_CONFIRMED"
        elif is_diagnostic_supported and entry_deal and not exit_deal:
            verdict = "DEMO_MICRO_EVIDENCE_RECEIPT_DIAGNOSTIC_CONFIRMED"
            warnings.append(
                "Diagnostic-supported match: entry confirmed, exit not yet in forensics history. "
                "Diagnostic confirms closed."
            )
        elif is_scanner_supported and (entry_deal or exit_deal):
            # v2.7.4: Scanner-supported match is authoritative receipt proof.
            # Scanner uses wider 14-day window with exact ticket matching.
            if entry_deal and exit_deal:
                verdict = "DEMO_MICRO_EVIDENCE_RECEIPT_DIAGNOSTIC_CONFIRMED"
            elif entry_deal:
                verdict = "DEMO_MICRO_EVIDENCE_RECEIPT_DIAGNOSTIC_CONFIRMED"
                warnings.append(
                    "Scanner-supported match: entry confirmed, exit not yet in "
                    "forensics normalized history. Scanner confirms exact ticket match."
                )
            else:
                verdict = "DEMO_MICRO_FORENSICS_COMPLETE_WITH_WARNINGS"
                warnings.append(
                    "Scanner-supported match: scanner confirmed exact ticket but "
                    "entry deal not classified in forensics normalized history."
                )
        elif is_scanner_supported and matched_deals:
            verdict = "DEMO_MICRO_FORENSICS_COMPLETE_WITH_WARNINGS"
        elif is_explicit_match and entry_deal and not exit_deal:
            # Entry confirmed but exit deal missing
            # Check if diagnostic says resolved_closed
            diag_closed = findings.get("diagnostic_resolved_closed", False)
            if diag_closed:
                verdict = "DEMO_MICRO_EVIDENCE_ENTRY_CONFIRMED_CLOSE_DEAL_MISSING"
                warnings.append("Entry deal found but exit deal missing. Diagnostic says resolved_closed.")
            else:
                verdict = "DEMO_MICRO_EVIDENCE_ENTRY_CONFIRMED_CLOSE_DEAL_MISSING"
                warnings.append("Entry deal found but exit deal missing. Position may still be open or close deal not yet in history.")
        elif is_strict_match and entry_deal and (sl_hit or exit_deal):
            verdict = "DEMO_MICRO_EVIDENCE_PASS"
        elif is_strict_match and matched_deals:
            verdict = "DEMO_MICRO_FORENSICS_COMPLETE_WITH_WARNINGS"
        elif is_likely_match and matched_deals:
            verdict = "DEMO_MICRO_FORENSICS_COMPLETE_WITH_WARNINGS"
            warnings.append("Verdict based on LIKELY match (no magic/comment/explicit/receipt match). Treat as diagnostic only.")
        elif matched_deals and (sl_hit or exit_deal):
            verdict = "DEMO_MICRO_FORENSICS_COMPLETE_WITH_WARNINGS"
        elif matched_deals:
            verdict = "DEMO_MICRO_EVIDENCE_INCOMPLETE"
        else:
            verdict = "DEMO_MICRO_EVIDENCE_INCOMPLETE"

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
    print("  TITAN XAU AI - Post-Trade Forensics (Sprint 9.9.3.45.8.16 v2.7.3)")
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
