#!/usr/bin/env python3
"""
TITAN XAU AI - MT5 Ticket History Scanner (Sprint 9.9.3.45.8.16 v2.7.3)
=========================================================================
Passive read-only MT5 history scanner that searches by exact deal ticket,
order ticket, deal.order, or position_id across a wide time window.

NEVER sends orders. NEVER modifies positions. NEVER creates execution tokens.

Default behavior:
  - Read data/runtime/demo_micro_execution_receipt.json
  - Extract all candidate tickets from receipt fields
  - Search MT5 history with a wide window:
      receipt_timestamp - 14 days  to  now + 1 day
  - Scan all deals and orders for exact ticket matches
  - magic/comment/symbol are reported only as diagnostics, NEVER as proof

Optional CLI inputs:
  --deal-ticket   exact deal ticket to search
  --order-ticket  exact order ticket to search
  --position-id   exact position_id to search
  --days          override window size (default 14 days back)

Verdicts:
  TICKET_HISTORY_MATCH_FOUND       - exact deal/order/position_id found
  TICKET_HISTORY_PENDING           - receipt has tickets but MT5 unavailable
                                     or history is empty (transient)
  TICKET_HISTORY_NOT_FOUND         - MT5 queried, no match anywhere
  TICKET_HISTORY_MT5_UNAVAILABLE   - MetaTrader5 module not installed

Outputs:
  data/audit/demo_micro_execution/ticket_history_scanner.json
  data/audit/demo_micro_execution/ticket_history_scanner.md
"""
from __future__ import annotations
import argparse, json, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

RECEIPT_PATH = REPO_ROOT / "data" / "runtime" / "demo_micro_execution_receipt.json"
OUTPUT_DIR = REPO_ROOT / "data" / "audit" / "demo_micro_execution"

# Verdict constants
TICKET_HISTORY_MATCH_FOUND = "TICKET_HISTORY_MATCH_FOUND"
TICKET_HISTORY_PENDING = "TICKET_HISTORY_PENDING"
TICKET_HISTORY_NOT_FOUND = "TICKET_HISTORY_NOT_FOUND"
TICKET_HISTORY_MT5_UNAVAILABLE = "TICKET_HISTORY_MT5_UNAVAILABLE"

ALL_VERDICTS = (
    TICKET_HISTORY_MATCH_FOUND,
    TICKET_HISTORY_PENDING,
    TICKET_HISTORY_NOT_FOUND,
    TICKET_HISTORY_MT5_UNAVAILABLE,
)


def _load_receipt(path: Optional[Path] = None) -> Optional[dict]:
    p = path or RECEIPT_PATH
    if not p.exists():
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _extract_receipt_tickets(receipt: dict) -> dict:
    """Pull all candidate tickets from receipt fields.

    Returns dict with keys: deal_tickets, order_tickets, position_ids.
    Each is a list of ints (deduped, > 0).
    """
    deal_tickets: list[int] = []
    order_tickets: list[int] = []
    position_ids: list[int] = []

    def _add(lst: list[int], v: Any) -> None:
        try:
            iv = int(v) if v is not None else 0
            if iv > 0 and iv not in lst:
                lst.append(iv)
        except (TypeError, ValueError):
            pass

    if not receipt:
        return {"deal_tickets": [], "order_tickets": [], "position_ids": []}

    # Deal ticket candidates
    _add(deal_tickets, receipt.get("deal_ticket"))
    _add(deal_tickets, receipt.get("order_send_result_deal"))

    # Order ticket candidates
    _add(order_tickets, receipt.get("order_ticket"))
    _add(order_tickets, receipt.get("order_send_result_order"))

    # Position id candidates
    _add(position_ids, receipt.get("position_id"))
    _add(position_ids, receipt.get("detected_position_ticket"))
    _add(position_ids, receipt.get("detected_position_identifier"))
    _add(position_ids, receipt.get("resolved_history_position_id"))

    return {
        "deal_tickets": deal_tickets,
        "order_tickets": order_tickets,
        "position_ids": position_ids,
    }


def _normalize_deal(d: Any) -> dict:
    return {
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
    }


def _normalize_order(o: Any) -> dict:
    return {
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
    }


def run_scan(
    receipt_path: Optional[Path] = None,
    deal_ticket: int = 0,
    order_ticket: int = 0,
    position_id: int = 0,
    days: int = 14,
) -> dict:
    """Run the ticket history scanner. NEVER calls mt5.order_send.

    Returns dict with verdict, findings, matched_deals, matched_orders,
    fallback_used, old_trades_used_as_proof, safety.
    """
    ts = datetime.now(timezone.utc).isoformat()
    ok_checks: list[str] = []
    blockers: list[str] = []
    warnings: list[str] = []
    findings: dict[str, Any] = {}

    receipt = _load_receipt(receipt_path)
    findings["receipt_path"] = str(receipt_path or RECEIPT_PATH)
    findings["receipt_available"] = receipt is not None

    # CLI-provided tickets override receipt-extracted tickets
    cli_deal = int(deal_ticket) if deal_ticket else 0
    cli_order = int(order_ticket) if order_ticket else 0
    cli_pos = int(position_id) if position_id else 0
    findings["cli_deal_ticket"] = cli_deal
    findings["cli_order_ticket"] = cli_order
    findings["cli_position_id"] = cli_pos

    receipt_tickets = _extract_receipt_tickets(receipt or {})
    findings["receipt_deal_tickets"] = receipt_tickets["deal_tickets"]
    findings["receipt_order_tickets"] = receipt_tickets["order_tickets"]
    findings["receipt_position_ids"] = receipt_tickets["position_ids"]

    # Final candidate lists (CLI takes priority but receipt candidates
    # are also searched to provide complete diagnostics)
    deal_candidates = list(receipt_tickets["deal_tickets"])
    if cli_deal and cli_deal not in deal_candidates:
        deal_candidates.insert(0, cli_deal)
    order_candidates = list(receipt_tickets["order_tickets"])
    if cli_order and cli_order not in order_candidates:
        order_candidates.insert(0, cli_order)
    position_candidates = list(receipt_tickets["position_ids"])
    if cli_pos and cli_pos not in position_candidates:
        position_candidates.insert(0, cli_pos)

    findings["deal_candidates"] = deal_candidates
    findings["order_candidates"] = order_candidates
    findings["position_candidates"] = position_candidates

    # Determine history window: receipt_timestamp - 14 days to now + 1 day
    receipt_ts = ""
    if receipt:
        receipt_ts = receipt.get("timestamp_utc", "") or ""
    findings["receipt_timestamp"] = receipt_ts

    try:
        if receipt_ts:
            receipt_dt = datetime.fromisoformat(receipt_ts.replace("Z", "+00:00"))
        else:
            receipt_dt = datetime.now(timezone.utc)
    except Exception:
        receipt_dt = datetime.now(timezone.utc)

    days_back = max(int(days), 1)
    from_dt = receipt_dt - timedelta(days=days_back)
    to_dt = datetime.now(timezone.utc) + timedelta(days=1)
    findings["history_window_start"] = from_dt.isoformat()
    findings["history_window_end"] = to_dt.isoformat()
    findings["window_days_back"] = days_back

    if not (deal_candidates or order_candidates or position_candidates):
        warnings.append(
            "No ticket candidates available (receipt missing or empty and no CLI tickets)."
        )

    # Try MT5
    try:
        import MetaTrader5 as mt5
    except ImportError:
        findings["mt5_available"] = False
        verdict = TICKET_HISTORY_MT5_UNAVAILABLE
        warnings.append("MetaTrader5 not available - cannot scan history")
        return {
            "timestamp_utc": ts,
            "verdict": verdict,
            "ok_checks": ok_checks,
            "blockers": blockers,
            "warnings": warnings,
            "findings": findings,
            "matched_deals": [],
            "matched_orders": [],
            "fallback_used": False,
            "old_trades_used_as_proof": False,
            "safety": {
                "order_send_called": False,
                "position_modified": False,
                "execution_token_created": False,
            },
        }

    try:
        if not mt5.initialize():
            findings["mt5_available"] = False
            blockers.append("MT5 initialize failed")
            verdict = TICKET_HISTORY_MT5_UNAVAILABLE
            return {
                "timestamp_utc": ts,
                "verdict": verdict,
                "ok_checks": ok_checks,
                "blockers": blockers,
                "warnings": warnings,
                "findings": findings,
                "matched_deals": [],
                "matched_orders": [],
                "fallback_used": False,
                "old_trades_used_as_proof": False,
                "safety": {
                    "order_send_called": False,
                    "position_modified": False,
                    "execution_token_created": False,
                },
            }
        findings["mt5_available"] = True
        ok_checks.append("MT5 initialized (passive read-only)")

        acc = mt5.account_info()
        if acc:
            findings["account_server"] = getattr(acc, "server", "unknown")
            findings["account_login_hash"] = hash(getattr(acc, "login", 0)) & 0xFFFFFFFF

        # Query ALL deals in the wide window
        all_deals_raw = mt5.history_deals_get(from_dt, to_dt)
        all_deals = list(all_deals_raw) if all_deals_raw else []
        findings["total_deals_in_window"] = len(all_deals)

        # Query ALL orders in the wide window
        all_orders_raw = mt5.history_orders_get(from_dt, to_dt)
        all_orders = list(all_orders_raw) if all_orders_raw else []
        findings["total_orders_in_window"] = len(all_orders)

        mt5.shutdown()

        normalized_deals = [_normalize_deal(d) for d in all_deals]
        normalized_orders = [_normalize_order(o) for o in all_orders]
        findings["normalized_deal_tickets_sample"] = [d["ticket"] for d in normalized_deals[:20]]
        findings["normalized_order_tickets_sample"] = [o["ticket"] for o in normalized_orders[:20]]
        findings["normalized_position_ids_sample"] = list(
            set(d["position_id"] for d in normalized_deals if d["position_id"])
        )[:20]

        # === Exact match search ===
        matched_deals: list[dict] = []
        matched_orders: list[dict] = []
        match_method = ""

        # 1. Exact deal ticket match
        for cand in deal_candidates:
            if not cand:
                continue
            for d in normalized_deals:
                if d["ticket"] == cand:
                    matched_deals.append(d)
                    match_method = match_method or f"exact_deal_ticket_{cand}"
                    ok_checks.append(f"Exact deal ticket match: {cand}")

        # 2. Exact order ticket match (search orders + deals.order)
        for cand in order_candidates:
            if not cand:
                continue
            for o in normalized_orders:
                if o["ticket"] == cand:
                    matched_orders.append(o)
                    match_method = match_method or f"exact_order_ticket_{cand}"
                    ok_checks.append(f"Exact order ticket match (orders): {cand}")
            for d in normalized_deals:
                if d["order"] == cand and d not in matched_deals:
                    matched_deals.append(d)
                    match_method = match_method or f"exact_deal_order_{cand}"
                    ok_checks.append(f"Exact deal.order match: {cand}")

        # 3. Exact position_id match (search deals + orders)
        for cand in position_candidates:
            if not cand:
                continue
            for d in normalized_deals:
                if d["position_id"] == cand and d not in matched_deals:
                    matched_deals.append(d)
                    match_method = match_method or f"exact_position_id_{cand}"
                    ok_checks.append(f"Exact position_id match (deals): {cand}")
            for o in normalized_orders:
                if o["position_id"] == cand and o not in matched_orders:
                    matched_orders.append(o)
                    match_method = match_method or f"exact_position_id_{cand}"
                    ok_checks.append(f"Exact position_id match (orders): {cand}")

        # Dedupe matched_deals by ticket
        seen_deal_tickets = set()
        deduped_deals = []
        for d in matched_deals:
            if d["ticket"] not in seen_deal_tickets:
                seen_deal_tickets.add(d["ticket"])
                deduped_deals.append(d)
        matched_deals = deduped_deals

        # Dedupe matched_orders by ticket
        seen_order_tickets = set()
        deduped_orders = []
        for o in matched_orders:
            if o["ticket"] not in seen_order_tickets:
                seen_order_tickets.add(o["ticket"])
                deduped_orders.append(o)
        matched_orders = deduped_orders

        findings["match_method"] = match_method
        findings["matched_deals_count"] = len(matched_deals)
        findings["matched_orders_count"] = len(matched_orders)

        # Diagnostic-only: deals sharing magic/comment/symbol with receipt
        # (NOT proof, only context for the operator)
        diagnostic_related_deals: list[dict] = []
        if receipt:
            receipt_magic = receipt.get("request_magic", 0) or 0
            receipt_symbol = receipt.get("symbol", "") or ""
            receipt_comment = receipt.get("request_comment", "") or ""
            for d in normalized_deals:
                if d in matched_deals:
                    continue
                related = False
                if receipt_magic and d["magic"] == receipt_magic:
                    related = True
                if receipt_symbol and d["symbol"] == receipt_symbol:
                    related = True
                if receipt_comment and receipt_comment in (d["comment"] or ""):
                    related = True
                if related:
                    diagnostic_related_deals.append({
                        "ticket": d["ticket"],
                        "position_id": d["position_id"],
                        "magic": d["magic"],
                        "symbol": d["symbol"],
                        "comment": d["comment"],
                        "match_reason": "magic_or_symbol_or_comment",
                    })
        findings["diagnostic_related_deals_count"] = len(diagnostic_related_deals)
        findings["diagnostic_related_deals_sample"] = diagnostic_related_deals[:10]

        # === Verdict ===
        if matched_deals or matched_orders:
            verdict = TICKET_HISTORY_MATCH_FOUND
            ok_checks.append(
                f"TICKET_HISTORY_MATCH_FOUND: matched_deals={len(matched_deals)}, "
                f"matched_orders={len(matched_orders)}, method={match_method}"
            )
        elif not (deal_candidates or order_candidates or position_candidates):
            # No tickets to search for
            verdict = TICKET_HISTORY_NOT_FOUND
            warnings.append("No ticket candidates to search for (receipt missing or empty).")
        elif len(normalized_deals) == 0 and len(normalized_orders) == 0:
            # MT5 returned empty history even with a wide window - pending
            verdict = TICKET_HISTORY_PENDING
            warnings.append(
                "MT5 history_deals_get and history_orders_get returned empty for the "
                "wide window. Likely MT5 history propagation delay or wrong account."
            )
        else:
            verdict = TICKET_HISTORY_NOT_FOUND
            warnings.append(
                "No exact ticket match found in MT5 history. Diagnostic-related deals "
                "(by magic/symbol/comment) are listed as diagnostics only and are NOT "
                "treated as proof."
            )

    except Exception as e:
        verdict = TICKET_HISTORY_MT5_UNAVAILABLE
        blockers.append(f"MT5 scan error: {e}")
        findings["mt5_available"] = False
        matched_deals = []
        matched_orders = []

    return {
        "timestamp_utc": ts,
        "verdict": verdict,
        "ok_checks": ok_checks,
        "blockers": blockers,
        "warnings": warnings,
        "findings": findings,
        "matched_deals": matched_deals,
        "matched_orders": matched_orders,
        "fallback_used": False,
        "old_trades_used_as_proof": False,
        "safety": {
            "order_send_called": False,
            "position_modified": False,
            "execution_token_created": False,
        },
    }


def write_report(result: dict) -> dict:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUTPUT_DIR / "ticket_history_scanner.json"
    md_path = OUTPUT_DIR / "ticket_history_scanner.md"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str, ensure_ascii=False)

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# TITAN XAU AI - MT5 Ticket History Scanner (v2.7.3)\n\n")
        f.write("**Passive read-only scan. No order_send. No position modification.**\n\n")
        f.write(f"**Verdict:** **{result['verdict']}**\n\n")
        f.write(f"**Timestamp:** {result['timestamp_utc']}\n\n")

        findings = result.get("findings", {}) or {}
        f.write("## Search Targets\n\n")
        f.write("| Field | Value |\n|---|---|\n")
        for k in [
            "receipt_available", "receipt_timestamp",
            "cli_deal_ticket", "cli_order_ticket", "cli_position_id",
            "receipt_deal_tickets", "receipt_order_tickets", "receipt_position_ids",
            "deal_candidates", "order_candidates", "position_candidates",
        ]:
            if k in findings:
                f.write(f"| {k} | {findings[k]} |\n")

        f.write("\n## History Window\n\n")
        f.write("| Field | Value |\n|---|---|\n")
        for k in [
            "history_window_start", "history_window_end",
            "window_days_back", "total_deals_in_window",
            "total_orders_in_window", "account_server",
        ]:
            if k in findings:
                f.write(f"| {k} | {findings[k]} |\n")

        f.write("\n## Match Results\n\n")
        f.write("| Field | Value |\n|---|---|\n")
        for k in [
            "match_method", "matched_deals_count", "matched_orders_count",
            "diagnostic_related_deals_count",
        ]:
            if k in findings:
                f.write(f"| {k} | {findings[k]} |\n")

        if result.get("matched_deals"):
            f.write("\n## Matched Deals (Exact Ticket Match)\n\n")
            f.write("| ticket | order | position_id | type | entry | price | profit | symbol | magic | comment |\n")
            f.write("|---|---|---|---|---|---|---|---|---|---|\n")
            for d in result["matched_deals"]:
                f.write(
                    f"| {d['ticket']} | {d['order']} | {d['position_id']} | "
                    f"{d['type']} | {d['entry']} | {d['price']} | {d['profit']} | "
                    f"{d['symbol']} | {d['magic']} | {d['comment']} |\n"
                )

        if result.get("matched_orders"):
            f.write("\n## Matched Orders (Exact Ticket Match)\n\n")
            f.write("| ticket | position_id | type | sl | tp | price | symbol | magic | comment |\n")
            f.write("|---|---|---|---|---|---|---|---|---|\n")
            for o in result["matched_orders"]:
                f.write(
                    f"| {o['ticket']} | {o['position_id']} | {o['type']} | "
                    f"{o['sl']} | {o['tp']} | {o['price']} | {o['symbol']} | "
                    f"{o['magic']} | {o['comment']} |\n"
                )

        if findings.get("diagnostic_related_deals_sample"):
            f.write("\n## Diagnostic-Related Deals (NOT proof - magic/symbol/comment only)\n\n")
            f.write("| ticket | position_id | magic | symbol | comment | match_reason |\n")
            f.write("|---|---|---|---|---|---|\n")
            for d in findings["diagnostic_related_deals_sample"]:
                f.write(
                    f"| {d['ticket']} | {d['position_id']} | {d['magic']} | "
                    f"{d['symbol']} | {d['comment']} | {d['match_reason']} |\n"
                )

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
        f.write("- execution_token_created: False\n")
        f.write("- fallback_used: False (magic/symbol/comment are diagnostic only)\n")
        f.write("- old_trades_used_as_proof: False\n")

    return {"json_path": str(json_path), "md_path": str(md_path)}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="MT5 ticket history scanner (passive read-only, no order_send)"
    )
    parser.add_argument("--deal-ticket", type=int, default=0)
    parser.add_argument("--order-ticket", type=int, default=0)
    parser.add_argument("--position-id", type=int, default=0)
    parser.add_argument("--days", type=int, default=14)
    parser.add_argument("--receipt", type=str, default="",
                        help="Override receipt JSON path")
    args = parser.parse_args()

    receipt_path = Path(args.receipt) if args.receipt else None

    print("=" * 70)
    print("  TITAN XAU AI - MT5 Ticket History Scanner (v2.7.3)")
    print("  (passive read-only - no order_send, no modification)")
    print("=" * 70)

    result = run_scan(
        receipt_path=receipt_path,
        deal_ticket=args.deal_ticket,
        order_ticket=args.order_ticket,
        position_id=args.position_id,
        days=args.days,
    )
    report = write_report(result)

    print(f"\n  Verdict: {result['verdict']}")
    print(f"  Receipt available: {result['findings'].get('receipt_available', False)}")
    print(f"  MT5 available: {result['findings'].get('mt5_available', False)}")
    print(f"  Match method: {result['findings'].get('match_method', '')}")
    print(f"  Matched deals: {result['findings'].get('matched_deals_count', 0)}")
    print(f"  Matched orders: {result['findings'].get('matched_orders_count', 0)}")
    print(f"  Diagnostic-related deals: {result['findings'].get('diagnostic_related_deals_count', 0)}")
    print(f"  Fallback used: {result.get('fallback_used', False)}")
    print(f"  Old trades used as proof: {result.get('old_trades_used_as_proof', False)}")
    print(f"\n  JSON: {report['json_path']}")
    print(f"  MD:   {report['md_path']}")
    print("\n" + "=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
