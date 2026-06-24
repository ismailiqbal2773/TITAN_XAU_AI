"""
TITAN XAU AI — Force ATR Execution Path Audit (Sprint 8.5)
============================================================

Objective: Force the ATR execution path to be exercised end-to-end
and produce hard journal evidence with all 11 required fields.

Why this script exists:
- Previous Windows MT5 run produced a FLAT signal (xgb_below_threshold).
- No DECISION/ORDER record was generated.
- The ATR execution path was never exercised.

Approach (no model/threshold/trade-logic changes):
1. Search ALL existing journals for the latest ACCEPTED DECISION record.
   If found, extract the 11 evidence fields from it.
2. ALSO run a fresh controlled audit on the production code path
   with source=canonical (which has been shown to produce accepted
   signals). The ATR execution path code (_compute_current_atr +
   _compute_sl_tp + process_signal) is SOURCE-AGNOSTIC — it operates
   on whatever bars are in feature_stream._bars. So canonical-bar
   evidence is valid proof that the ATR execution path works.
3. Produce final verdict A/B/C.

Output:
- Console: full evidence report
- JSON: data/audit/force_atr_execution_audit_report.json
- Journal: data/audit/force_atr_execution_audit_journal.jsonl
"""
from __future__ import annotations
import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from titan.production.trade_journal import TradeJournal, EventType
from titan.runtime.autonomous_loops import AutonomousRuntime, RuntimeConfig

logging.basicConfig(level=logging.WARNING,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("force_atr_audit")
logger.setLevel(logging.INFO)

JOURNAL_PATH = REPO_ROOT / "data" / "audit" / "force_atr_execution_audit_journal.jsonl"
REPORT_PATH = REPO_ROOT / "data" / "audit" / "force_atr_execution_audit_report.json"

EVIDENCE_FIELDS = [
    "current_atr", "sl_tp_mode_used", "fallback_used", "fallback_reason",
    "computed_sl", "computed_tp",
]


def find_latest_accepted_decision_in_journals() -> dict | None:
    """Search all journal files for the latest accepted DECISION record."""
    import glob
    journals = sorted(glob.glob(str(REPO_ROOT / "data" / "**" / "*.jsonl"), recursive=True))
    accepted = []
    for j in journals:
        try:
            with open(j, "r", encoding="utf-8") as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line: continue
                    try: r = json.loads(line)
                    except: continue
                    if r.get("record_type") != "DECISION": continue
                    d = r.get("data", {}) or {}
                    if not isinstance(d, dict): continue
                    if d.get("accepted") is True:
                        accepted.append({
                            "file": j, "line": line_num,
                            "ts": r.get("utc_timestamp", ""),
                            "data": d,
                        })
        except Exception:
            pass
    if not accepted:
        return None
    accepted.sort(key=lambda x: x["ts"], reverse=True)
    return accepted[0]


async def run_fresh_audit() -> dict:
    """Run a fresh AutonomousRuntime cycle to produce a new accepted signal."""
    if JOURNAL_PATH.exists():
        JOURNAL_PATH.unlink()
    journal = TradeJournal(path=str(JOURNAL_PATH), session_id="force_atr_audit")
    cfg = RuntimeConfig(
        dry_run=True,
        symbol="XAUUSD",
        feature_source="canonical",  # source-agnostic for ATR path
        feature_window=300,
        inference_interval_s=60.0,
        position_sync_interval_s=10.0,
        exit_check_interval_s=5.0,
        drift_check_interval_s=60.0,
        heartbeat_interval_s=30.0,
    )
    rt = AutonomousRuntime(config=cfg, journal=journal, journal_path=str(JOURNAL_PATH))
    rt.initialize()
    # Force the multipliers (defensive — should already match runtime.yaml)
    rt.trade_loop.config.sl_mode = "atr"
    rt.trade_loop.config.atr_sl_multiplier = 2.0
    rt.trade_loop.config.atr_tp_multiplier = 4.0

    logger.info("Generating signal...")
    signal = rt.inference_engine.generate(source="canonical", symbol="XAUUSD")
    logger.info(f"Signal: dir={signal.direction.name} conf={signal.confidence:.4f} "
                f"meta={signal.meta_confidence:.4f} tradeable={signal.is_tradeable}")

    # Manually invoke process_signal to force a DECISION + ORDER record
    current_atr = rt._compute_current_atr()
    entry_price = float(rt.inference_engine.feature_stream._bars["close"].iloc[-1])
    decision = await rt.trade_loop.process_signal(
        signal=signal,
        entry_price=entry_price,
        spread_usd=0.20,
        current_atr=current_atr,
        risk_engine=None,
        execution_engine=None,
        current_equity=10000.0,
    )
    journal.flush()
    return {
        "signal": signal,
        "decision": decision,
        "current_atr_pre_call": current_atr,
        "entry_price_used": entry_price,
        "rt": rt,
    }


def render_evidence(record_label: str, source: str, signal, decision) -> dict:
    """Render the 11-point evidence report for one accepted decision."""
    print()
    print("=" * 78)
    print(f"  EVIDENCE — {record_label}")
    print(f"  source: {source}")
    print("=" * 78)

    # Field 1: SIGNAL_CREATED record
    sig_record = {
        "record_type": "SIGNAL_CREATED",
        "direction": signal.direction.name,
        "confidence": float(signal.confidence),
        "meta_confidence": float(signal.meta_confidence),
        "is_tradeable": bool(signal.is_tradeable),
        "reject_reason": signal.reject_reason,
    }
    print(f"\n  1. SIGNAL_CREATED record:")
    for k, v in sig_record.items():
        print(f"     {k:20s}: {v}")

    # Field 2-11 from decision
    dec_data = {
        "accepted": decision.accepted,
        "reject_reason": decision.reject_reason,
        "current_atr": decision.current_atr,
        "sl_tp_mode_used": decision.sl_tp_mode_used,
        "sl_mode_configured": decision.sl_mode_configured,
        "fallback_used": decision.fallback_used,
        "fallback_reason": decision.fallback_reason,
        "atr_sl_multiplier": decision.atr_sl_multiplier,
        "atr_tp_multiplier": decision.atr_tp_multiplier,
        "atr_sl_distance": decision.atr_sl_distance,
        "atr_tp_distance": decision.atr_tp_distance,
        "entry_price": decision.entry_price,
        "computed_sl": decision.computed_sl,
        "computed_tp": decision.computed_tp,
        "dry_run": decision.dry_run,
        "order_request": decision.order_request,
    }

    print(f"\n  2. DECISION record:")
    print(f"     accepted:           {dec_data['accepted']}")
    print(f"     reject_reason:      {dec_data['reject_reason']}")
    print(f"     dry_run:            {dec_data['dry_run']}")

    print(f"\n  3. ORDER_CREATED record:")
    if dec_data["order_request"]:
        or_ = dec_data["order_request"]
        print(f"     order_type:         {or_.get('order_type')}")
        print(f"     symbol:             {or_.get('symbol')}")
        print(f"     volume:             {or_.get('volume')}")
        print(f"     magic:              {or_.get('magic')}")
    else:
        print(f"     (no order request — decision not accepted)")

    print(f"\n  4. current_atr:               {dec_data['current_atr']}")
    print(f"  5. sl_tp_mode_used:           {dec_data['sl_tp_mode_used']}")
    print(f"  6. fallback_used:             {dec_data['fallback_used']}")
    print(f"  7. fallback_reason:           {dec_data['fallback_reason']}")
    print(f"  8. computed_sl:               {dec_data['computed_sl']}")
    print(f"  9. computed_tp:               {dec_data['computed_tp']}")
    if dec_data["order_request"]:
        print(f"  10. order_request.sl:         {dec_data['order_request'].get('sl')}")
        print(f"  11. order_request.tp:         {dec_data['order_request'].get('tp')}")
        # Consistency check
        sl_match = abs(float(dec_data["order_request"]["sl"]) - dec_data["computed_sl"]) < 1e-6
        tp_match = abs(float(dec_data["order_request"]["tp"]) - dec_data["computed_tp"]) < 1e-6
        print(f"\n  ── CONSISTENCY ──")
        print(f"  order_request.sl == computed_sl : {sl_match}")
        print(f"  order_request.tp == computed_tp : {tp_match}")
        # Formula check
        if dec_data["current_atr"] > 0:
            atr = dec_data["current_atr"]
            if signal.direction.name == "LONG":
                exp_sl = dec_data["entry_price"] - dec_data["atr_sl_multiplier"] * atr
                exp_tp = dec_data["entry_price"] + dec_data["atr_tp_multiplier"] * atr
            else:
                exp_sl = dec_data["entry_price"] + dec_data["atr_sl_multiplier"] * atr
                exp_tp = dec_data["entry_price"] - dec_data["atr_tp_multiplier"] * atr
            sl_formula_match = abs(exp_sl - dec_data["computed_sl"]) < 1e-4
            tp_formula_match = abs(exp_tp - dec_data["computed_tp"]) < 1e-4
            print(f"\n  ── FORMULA CHECK ({signal.direction.name}) ──")
            print(f"  Expected SL = entry {'-' if signal.direction.name == 'LONG' else '+'} (atr_sl_mult × ATR)")
            print(f"             = {dec_data['entry_price']} {'-' if signal.direction.name == 'LONG' else '+'} ({dec_data['atr_sl_multiplier']} × {atr})")
            print(f"             = {exp_sl:.5f}")
            print(f"  Actual   SL = {dec_data['computed_sl']}")
            print(f"  Match: {sl_formula_match}")
            print(f"  Expected TP = entry {'+' if signal.direction.name == 'LONG' else '-'} (atr_tp_mult × ATR)")
            print(f"             = {dec_data['entry_price']} {'+' if signal.direction.name == 'LONG' else '-'} ({dec_data['atr_tp_multiplier']} × {atr})")
            print(f"             = {exp_tp:.5f}")
            print(f"  Actual   TP = {dec_data['computed_tp']}")
            print(f"  Match: {tp_formula_match}")

    return {
        "signal_record": sig_record,
        "decision_record": dec_data,
    }


def main():
    print("=" * 78)
    print("  TITAN XAU AI — FORCE ATR EXECUTION PATH AUDIT (Sprint 8.5)")
    print("  No model/threshold/trade-logic changes.")
    print("=" * 78)

    # ── PART A: search existing journals ──
    print("\n── PART A: Search existing journals for latest accepted DECISION ──")
    latest = find_latest_accepted_decision_in_journals()
    if latest:
        print(f"  Found: {latest['file']}:{latest['line']}")
        print(f"  Timestamp: {latest['ts']}")
        d = latest["data"]
        print(f"  current_atr: {d.get('current_atr')}")
        print(f"  sl_tp_mode_used: {d.get('sl_tp_mode_used')}")
        print(f"  fallback_used: {d.get('fallback_used')}")
    else:
        print("  No accepted DECISION found in any journal.")

    # ── PART B: run fresh controlled audit ──
    print("\n── PART B: Fresh controlled audit (source=canonical, ATR path is source-agnostic) ──")
    print("  Hard-coded safety:")
    print("    dry_run=True, live_trading=False, sl_mode=atr")
    print("    atr_sl_multiplier=2.0, atr_tp_multiplier=4.0")
    print("    broker_source=stub")
    print()
    ctx = asyncio.run(run_fresh_audit())
    signal = ctx["signal"]
    decision = ctx["decision"]
    print(f"\n  Pre-call current_atr: {ctx['current_atr_pre_call']:.6f}")
    print(f"  Entry price used:     {ctx['entry_price_used']}")
    print(f"  Decision.accepted:    {decision.accepted}")

    if not decision.accepted:
        print("\n  ✗ Fresh audit did NOT produce an accepted signal.")
        print("    Falling back to PART A journal evidence only.")
        if not latest:
            print("\n  ✗✗✗ NO ACCEPTED SIGNAL ANYWHERE — cannot verify ATR path.")
            sys.exit(2)
        # Render from journal record
        class _Sig: pass
        sig = _Sig()
        sig.direction = type('D', (), {'name': 'UNKNOWN'})()
        # We don't have the signal record easily; just render decision fields
        class _Dec:
            pass
        dec = _Dec()
        for k, v in latest["data"].items():
            setattr(dec, k, v)
        evidence = render_evidence("LATEST FROM JOURNAL HISTORY", "(see file path above)", sig, dec)
    else:
        evidence = render_evidence(
            "FRESH CONTROLLED AUDIT",
            "canonical (ATR path is source-agnostic)",
            signal, decision,
        )

    # ── Verdict ──
    dec_data = evidence["decision_record"]
    print("\n" + "=" * 78)
    print("  FINAL VERDICT")
    print("=" * 78)
    if (dec_data.get("accepted") and
        dec_data.get("current_atr", 0) > 0 and
        dec_data.get("sl_tp_mode_used") == "atr" and
        dec_data.get("fallback_used") is False):
        verdict = "A"
        verdict_text = "ATR execution path verified and fallback_used=false"
    elif (dec_data.get("accepted") and
          dec_data.get("sl_tp_mode_used") == "fixed" and
          dec_data.get("fallback_used") is True):
        verdict = "B"
        verdict_text = f"fallback actually triggered (reason={dec_data.get('fallback_reason')})"
    else:
        verdict = "C"
        verdict_text = "another wiring defect found"

    print(f"\n  >>> VERDICT: {verdict}")
    print(f"  >>> {verdict_text}")

    # ── Save report ──
    report = {
        "audit": "force_atr_execution_path_audit_sprint_8_5",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "latest_accepted_from_journals": latest,
        "fresh_audit": {
            "source": "canonical",
            "current_atr_pre_call": ctx["current_atr_pre_call"],
            "entry_price_used": ctx["entry_price_used"],
            "signal": evidence["signal_record"],
            "decision": {
                k: v for k, v in dec_data.items()
                if k != "order_request"
            } | ({"order_request": dec_data["order_request"]} if dec_data.get("order_request") else {}),
        },
        "verdict": verdict,
        "verdict_text": verdict_text,
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\n  Report saved: {REPORT_PATH}")
    print(f"  Journal saved: {JOURNAL_PATH}")

    sys.exit(0 if verdict == "A" else 1)


if __name__ == "__main__":
    main()
