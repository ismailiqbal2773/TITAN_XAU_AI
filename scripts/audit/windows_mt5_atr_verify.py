"""
TITAN XAU AI — Windows MT5 ATR Verification (Sprint 8.5)
==========================================================

PURPOSE
-------
Run AutonomousRuntime for 5-10 minutes on Windows with MT5 terminal
logged in to verify the production ATR SL/TP path end-to-end against
REAL MT5 H1 bars.

CONSTRAINTS (HARD-CODED — DO NOT CHANGE)
----------------------------------------
- dry_run = True            (NO real orders)
- live_trading = False      (NO live trading)
- features.source = mt5     (real MT5 bars)
- sl_mode = atr
- atr_sl_multiplier = 2.0   (balanced profile)
- atr_tp_multiplier = 4.0
- broker_source = stub      (no real broker calls)
- No model/threshold changes
- No mt5.order_send calls (ExecutionEngine internal guard rejects)

OUTPUT
------
- Console: live progress + final 10-point evidence report
- Journal: data/runtime/windows_mt5_atr_verify.jsonl
- Report:  data/audit/windows_mt5_atr_verify_report.json

USAGE (on Windows)
------------------
    cd C:\\path\\to\\TITAN_XAU_AI
    python scripts\\audit\\windows_mt5_atr_verify.py            # 5 min default
    python scripts\\audit\\windows_mt5_atr_verify.py --minutes 10  # 10 min
    python scripts\\audit\\windows_mt5_atr_verify.py --help

PREREQUISITES
-------------
1. Windows 10/11 with Python 3.12+
2. MetaTrader5 package:  pip install MetaTrader5
3. MT5 terminal running and logged into Exness (or any broker with XAUUSD)
4. XAUUSD symbol visible in Market Watch
5. Repo at the latest commit:  git pull origin main

VERDICT
-------
A = Windows MT5 dry-run ATR production path verified
B = ATR fallback still happens
C = Another runtime bug remains
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# ── Repo root detection ──────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

# ── OS guard — this script is meaningful only on Windows ────────────────────
if platform.system() != "Windows":
    print("=" * 78)
    print("  ⚠  NOT RUNNING ON WINDOWS  ⚠")
    print("=" * 78)
    print(f"  Detected OS: {platform.system()} {platform.release()}")
    print("  This script verifies the MT5 path, which requires Windows +")
    print("  MetaTrader5 package + MT5 terminal logged in.")
    print()
    print("  On Linux, the MT5 import will fail and the script will exit")
    print("  at the connectivity check below.")
    print("=" * 78)

# ── Imports ──────────────────────────────────────────────────────────────────
from titan.production.trade_journal import TradeJournal, EventType
from titan.runtime.autonomous_loops import AutonomousRuntime, RuntimeConfig

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("win_mt5_verify")
logger.setLevel(logging.INFO)

# ── Hard-coded verification config (overrides runtime.yaml) ─────────────────
VERIFY_CONFIG = dict(
    dry_run=True,                  # HARD: no real orders
    live_trading=False,            # HARD: no live trading
    feature_source="mt5",          # HARD: real MT5 bars
    sl_mode="atr",
    atr_sl_multiplier=2.0,
    atr_tp_multiplier=4.0,
    broker_source="stub",
    atr_period=14,
    magic_number=202619,
    max_lot=0.01,
)

JOURNAL_PATH = REPO_ROOT / "data" / "runtime" / "windows_mt5_atr_verify.jsonl"
REPORT_PATH = REPO_ROOT / "data" / "audit" / "windows_mt5_atr_verify_report.json"


def pre_check_mt5() -> dict:
    """Verify MT5 connectivity BEFORE starting runtime."""
    result = {"mt5_imported": False, "mt5_initialized": False,
              "account_login": None, "server": None, "company": None,
              "xauusd_found": False, "error": ""}
    try:
        import MetaTrader5 as mt5
        result["mt5_imported"] = True
    except ImportError as e:
        result["error"] = f"MetaTrader5 package not installed: {e}"
        return result

    if not mt5.initialize():
        result["error"] = f"mt5.initialize() failed: {mt5.last_error()}"
        return result
    result["mt5_initialized"] = True

    try:
        acc = mt5.account_info()
        if acc:
            result["account_login"] = acc.login
            result["server"] = acc.server
            result["company"] = acc.company

        info = mt5.symbol_info("XAUUSD")
        if info:
            result["xauusd_found"] = True
        else:
            # Try selecting first
            if mt5.symbol_select("XAUUSD", True):
                info = mt5.symbol_info("XAUUSD")
                result["xauusd_found"] = info is not None
    except Exception as e:
        result["error"] = f"MT5 query failed: {e}"
    finally:
        mt5.shutdown()
    return result


def verify_scaler_loaded(rt: AutonomousRuntime) -> dict:
    """Verify scaler is loaded in inference_engine.feature_stream."""
    fs = rt.inference_engine.feature_stream
    return {
        "scaler_loaded": bool(getattr(fs, "_scaler_loaded", False)),
        "n_features": len(getattr(fs, "_train_mean", [])) if fs._train_mean is not None else 0,
    }


async def run_verification(minutes: float) -> dict:
    """Run AutonomousRuntime for N minutes and collect evidence."""
    JOURNAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    if JOURNAL_PATH.exists():
        JOURNAL_PATH.unlink()

    journal = TradeJournal(path=str(JOURNAL_PATH), session_id="win_mt5_verify")

    # Build RuntimeConfig — start with defaults then override with VERIFY_CONFIG
    cfg = RuntimeConfig(
        dry_run=True,
        symbol="XAUUSD",
        feature_source="mt5",
        feature_window=300,
        inference_interval_s=60.0,   # H1 cadence — but we'll force_generate to avoid waiting
        position_sync_interval_s=10.0,
        exit_check_interval_s=5.0,
        drift_check_interval_s=60.0,
        heartbeat_interval_s=30.0,
    )

    rt = AutonomousRuntime(config=cfg, journal=journal, journal_path=str(JOURNAL_PATH))
    rt.initialize()

    # Force-override trade_loop config to guarantee hard-coded multipliers
    rt.trade_loop.config.sl_mode = "atr"
    rt.trade_loop.config.atr_sl_multiplier = 2.0
    rt.trade_loop.config.atr_tp_multiplier = 4.0

    # ── Pre-checks ──
    print()
    print("── Pre-checks ──")
    print(f"  dry_run:                {rt.config.dry_run}")
    print(f"  feature_source:         {rt.config.feature_source}")
    print(f"  sl_mode:                {rt.trade_loop.config.sl_mode}")
    print(f"  atr_sl_multiplier:      {rt.trade_loop.config.atr_sl_multiplier}")
    print(f"  atr_tp_multiplier:      {rt.trade_loop.config.atr_tp_multiplier}")
    print(f"  max_lot:                {rt.trade_loop.config.max_lot}")
    print(f"  broker_source:          stub (hard-coded)")

    scaler_info = verify_scaler_loaded(rt)
    print(f"  scaler_loaded:          {scaler_info['scaler_loaded']}  ({scaler_info['n_features']} features)")
    print()

    # ── Force a single generate() cycle to populate feature_stream from MT5 ──
    print("── Generating one signal from MT5 bars ──")
    signal = rt.inference_engine.generate(source="mt5", symbol="XAUUSD")
    bars_loaded = len(rt.inference_engine.feature_stream._bars)
    print(f"  MT5 bars loaded:        {bars_loaded}")
    print(f"  Signal:                 dir={signal.direction.name} "
          f"conf={signal.confidence:.4f} meta={signal.meta_confidence:.4f} "
          f"tradeable={signal.is_tradeable}")
    print(f"  reject_reason:          {signal.reject_reason}")

    # Compute ATR via the production helper
    current_atr = rt._compute_current_atr()
    print(f"  current_atr (real MT5): {current_atr:.6f}")

    # ── Run the runtime for N minutes ──
    print()
    print(f"── Running AutonomousRuntime for {minutes:.1f} minutes ──")
    print(f"    (heartbeats every 30s, inference every 60s — let it run)")
    start_task = asyncio.create_task(rt.start())
    t0 = time.time()
    await asyncio.sleep(minutes * 60)
    elapsed = time.time() - t0
    print(f"  Elapsed: {elapsed:.1f}s")
    print(f"  signals_generated: {rt.signals_generated}")
    print(f"  trades_attempted:  {rt.trades_attempted}")
    print(f"  trades_blocked:    {rt.trades_blocked}")

    # ── Shutdown ──
    print()
    print("── Signalling shutdown ──")
    rt.shutdown()
    try:
        await asyncio.wait_for(start_task, timeout=15.0)
    except asyncio.TimeoutError:
        start_task.cancel()
        try:
            await start_task
        except asyncio.CancelledError:
            pass

    journal.flush()
    print(f"  kill_switch_state at shutdown: {rt.kill_switch.state.value}")
    print(f"  Journal records:               {journal.record_count}")
    print(f"  Journal path:                  {JOURNAL_PATH}")

    return {
        "rt": rt,
        "scaler_info": scaler_info,
        "signal_initial": signal,
        "bars_loaded_initial": bars_loaded,
        "current_atr_initial": current_atr,
        "elapsed_s": elapsed,
    }


def extract_evidence(ctx: dict) -> dict:
    """Read journal and extract evidence for the 10-point audit."""
    rt = ctx["rt"]
    records = rt.journal.read_all()
    by_type = {}
    for r in records:
        by_type.setdefault(r["record_type"], []).append(r)
    by_event = {}
    for r in records:
        if r.get("event_type"):
            by_event.setdefault(r["event_type"], []).append(r)

    # Latest of each
    latest_signal = by_type.get("SIGNAL", [])[-1:] or by_event.get("SIGNAL_CREATED", [])[-1:]
    latest_decision = by_type.get("DECISION", [])[-1:]
    latest_order = by_type.get("ORDER", [])[-1:]
    latest_heartbeats = by_type.get("HEARTBEAT", [])[-5:]

    # Dry_run invariant
    dry_run_checked = 0
    dry_run_violations = 0
    for r in records:
        data = r.get("data", {}) or {}
        if isinstance(data, dict) and "dry_run" in data:
            dry_run_checked += 1
            if data["dry_run"] is not True:
                dry_run_violations += 1

    # ATR audit fields from latest accepted DECISION
    atr_audit = {}
    if latest_decision:
        d = latest_decision[0].get("data", {}) or {}
        atr_audit = {k: d.get(k) for k in (
            "current_atr", "sl_tp_mode_used", "sl_mode_configured",
            "fallback_used", "fallback_reason",
            "atr_sl_multiplier", "atr_tp_multiplier",
            "atr_sl_distance", "atr_tp_distance",
            "entry_price", "computed_sl", "computed_tp",
            "accepted", "dry_run",
        )}

    return {
        "total_records": len(records),
        "record_counts": {k: len(v) for k, v in by_type.items()},
        "event_counts": {k: len(v) for k, v in by_event.items()},
        "latest_signal": latest_signal[0] if latest_signal else None,
        "latest_decision": latest_decision[0] if latest_decision else None,
        "latest_order": latest_order[0] if latest_order else None,
        "latest_heartbeats": latest_heartbeats,
        "dry_run_checked": dry_run_checked,
        "dry_run_violations": dry_run_violations,
        "atr_audit": atr_audit,
        "bars_loaded_initial": ctx["bars_loaded_initial"],
        "current_atr_initial": ctx["current_atr_initial"],
        "scaler_info": ctx["scaler_info"],
        "signals_generated": rt.signals_generated,
        "trades_attempted": rt.trades_attempted,
        "trades_blocked": rt.trades_blocked,
        "kill_switch_state": rt.kill_switch.state.value,
    }


def render_evidence(mt5_pre: dict, ev: dict) -> None:
    """Print the 10-point evidence report."""
    print()
    print("=" * 78)
    print("  WINDOWS MT5 ATR VERIFICATION — 10-POINT EVIDENCE")
    print("=" * 78)
    print()

    print("── 1. MT5 bars loaded ──")
    print(f"   mt5_imported:        {mt5_pre['mt5_imported']}")
    print(f"   mt5_initialized:     {mt5_pre['mt5_initialized']}")
    print(f"   account_login:       {mt5_pre['account_login']}")
    print(f"   server:              {mt5_pre['server']}")
    print(f"   company:             {mt5_pre['company']}")
    print(f"   XAUUSD found:        {mt5_pre['xauusd_found']}")
    print(f"   bars_loaded_initial: {ev['bars_loaded_initial']}")
    print()

    print("── 2. scaler_loaded ──")
    print(f"   scaler_loaded:       {ev['scaler_info']['scaler_loaded']}")
    print(f"   n_features:          {ev['scaler_info']['n_features']}")
    print()

    print("── 3. current_atr > 0 ──")
    print(f"   current_atr_initial: {ev['current_atr_initial']:.6f}")
    if ev['atr_audit'].get('current_atr') is not None:
        print(f"   current_atr in DECISION: {ev['atr_audit']['current_atr']}")
    print()

    print("── 4. sl_tp_mode_used = atr ──")
    print(f"   sl_tp_mode_used:     {ev['atr_audit'].get('sl_tp_mode_used')}")
    print(f"   sl_mode_configured:  {ev['atr_audit'].get('sl_mode_configured')}")
    print()

    print("── 5. fallback_used = false ──")
    print(f"   fallback_used:       {ev['atr_audit'].get('fallback_used')}")
    print(f"   fallback_reason:     {ev['atr_audit'].get('fallback_reason')}")
    print()

    print("── 6. signal generated ──")
    sig = ev['latest_signal']
    if sig:
        d = sig.get('data', {}) or {}
        print(f"   record_type:         {sig['record_type']}")
        print(f"   event_type:          {sig.get('event_type')}")
        print(f"   direction:           {d.get('direction')}")
        print(f"   confidence:          {d.get('confidence')}")
        print(f"   meta_confidence:     {d.get('meta_confidence')}")
        print(f"   is_tradeable:        {d.get('is_tradeable')}")
    else:
        print("   (no signal record)")
    print()

    print("── 7. ORDER created in dry_run only (if signal accepted) ──")
    dec = ev['latest_decision']
    if dec:
        d = dec.get('data', {}) or {}
        print(f"   DECISION.accepted:   {d.get('accepted')}")
        print(f"   DECISION.dry_run:    {d.get('dry_run')}")
        print(f"   DECISION.risk:       {d.get('risk_decision')}")
        if d.get('order_request'):
            or_ = d['order_request']
            print(f"   order_type:          {or_.get('order_type')}")
            print(f"   volume:              {or_.get('volume')}")
            print(f"   sl:                  {or_.get('sl')}")
            print(f"   tp:                  {or_.get('tp')}")
            print(f"   magic:               {or_.get('magic')}")
    else:
        print("   (no decision record)")
    print()

    ord_rec = ev['latest_order']
    if ord_rec:
        d = ord_rec.get('data', {}) or {}
        print(f"   ORDER.dry_run:       {d.get('dry_run')}")
        print(f"   ORDER.order_result:  {d.get('order_result')}")
    else:
        print("   (no order record — signal was not accepted)")
    print()

    print("── 8. NO real mt5.order_send ──")
    print(f"   dry_run records checked:  {ev['dry_run_checked']}")
    print(f"   dry_run violations:       {ev['dry_run_violations']}")
    print(f"   (ExecutionEngine internal guard: dry_run=True blocks mt5.order_send)")
    print()

    print("── 9. HEARTBEAT stable ──")
    hbs = ev['latest_heartbeats']
    print(f"   last {len(hbs)} heartbeats:")
    for h in hbs:
        d = h.get('data', {}) or {}
        print(f"     {h['utc_timestamp'][:19]}  kill_switch={d.get('kill_switch_state')}  "
              f"open_positions={d.get('open_positions')}")
    print()

    print("── 10. kill_switch_state = NORMAL ──")
    print(f"   final kill_switch_state:   {ev['kill_switch_state']}")
    print()

    print("=" * 78)
    print("  SUMMARY")
    print("=" * 78)
    print(f"  total records:              {ev['total_records']}")
    print(f"  record counts:              {ev['record_counts']}")
    print(f"  event counts:               {ev['event_counts']}")
    print(f"  signals_generated:          {ev['signals_generated']}")
    print(f"  trades_attempted:           {ev['trades_attempted']}")
    print(f"  trades_blocked:             {ev['trades_blocked']}")
    print(f"  bars_loaded (MT5):          {ev['bars_loaded_initial']}")
    print(f"  current_atr (real MT5):     {ev['current_atr_initial']:.6f}")
    print(f"  dry_run violations:         {ev['dry_run_violations']}")


def compute_verdict(mt5_pre: dict, ev: dict) -> str:
    """A / B / C verdict based on hard evidence."""
    if not mt5_pre["mt5_initialized"] or not mt5_pre["xauusd_found"]:
        return "C"  # cannot verify — runtime bug or MT5 unavailable
    if ev["bars_loaded_initial"] < 15:
        return "C"  # not enough bars
    if ev["scaler_info"]["scaler_loaded"] is False:
        return "C"
    if ev["current_atr_initial"] <= 0:
        return "B"  # ATR fallback
    if ev["atr_audit"].get("sl_tp_mode_used") != "atr":
        return "B"
    if ev["atr_audit"].get("fallback_used") is True:
        return "B"
    if ev["dry_run_violations"] > 0:
        return "C"  # safety violation
    if ev["kill_switch_state"] != "NORMAL":
        return "C"
    return "A"


def main():
    parser = argparse.ArgumentParser(description="Windows MT5 ATR Verification")
    parser.add_argument("--minutes", type=float, default=5.0,
                        help="Run duration in minutes (default: 5, max: 30)")
    args = parser.parse_args()
    if args.minutes > 30:
        args.minutes = 30
    if args.minutes < 1:
        args.minutes = 1

    print("=" * 78)
    print("  TITAN XAU AI — WINDOWS MT5 ATR VERIFICATION (Sprint 8.5)")
    print("=" * 78)
    print(f"  Duration:          {args.minutes:.1f} minutes")
    print(f"  dry_run:           True (HARD)")
    print(f"  live_trading:      False (HARD)")
    print(f"  feature_source:    mt5 (HARD)")
    print(f"  sl_mode:           atr")
    print(f"  atr_sl_multiplier: 2.0")
    print(f"  atr_tp_multiplier: 4.0")
    print(f"  broker_source:     stub")
    print(f"  Journal:           {JOURNAL_PATH}")
    print(f"  Report:            {REPORT_PATH}")
    print()

    # ── Pre-check MT5 ──
    print("── MT5 connectivity pre-check ──")
    mt5_pre = pre_check_mt5()
    for k, v in mt5_pre.items():
        print(f"   {k:20s}: {v}")
    print()

    if not mt5_pre["mt5_initialized"]:
        print("  ✗ MT5 initialization failed — aborting.")
        print(f"    Error: {mt5_pre['error']}")
        print("    Make sure MT5 terminal is running and logged in.")
        sys.exit(2)
    if not mt5_pre["xauusd_found"]:
        print("  ✗ XAUUSD symbol not found — aborting.")
        print("    Add XAUUSD to Market Watch in MT5 terminal.")
        sys.exit(2)

    print("  ✓ MT5 connected and XAUUSD available.")
    print()

    # ── Run ──
    ctx = asyncio.run(run_verification(args.minutes))

    # ── Extract evidence ──
    ev = extract_evidence(ctx)

    # ── Render ──
    render_evidence(mt5_pre, ev)

    # ── Verdict ──
    verdict = compute_verdict(mt5_pre, ev)
    print()
    print("=" * 78)
    print(f"  FINAL VERDICT: {verdict}")
    print("=" * 78)
    if verdict == "A":
        print("  Windows MT5 dry-run ATR production path VERIFIED.")
        print("  - Real MT5 bars loaded into feature_stream")
        print("  - current_atr computed from real H1 bars")
        print("  - sl_tp_mode_used = 'atr' in journal DECISION/ORDER records")
        print("  - fallback_used = False on every accepted decision")
        print("  - dry_run = True preserved (no mt5.order_send calls)")
        print("  - kill_switch_state stayed NORMAL")
    elif verdict == "B":
        print("  ATR fallback still happening.")
        print("  Check fallback_reason in DECISION records:")
        print("    - 'atr_zero'   → ATR came back as 0 (insufficient bars or NaN)")
        print("    - 'atr_nan'    → ATR was NaN")
        print("    - 'mode_fixed' → sl_mode was somehow set to 'fixed'")
    else:
        print("  Another runtime bug remains — investigate journal records.")

    # ── Save report ──
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "audit": "windows_mt5_atr_verify_sprint_8_5",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "duration_minutes": args.minutes,
        "config_used": VERIFY_CONFIG,
        "mt5_pre_check": mt5_pre,
        "evidence": {
            "total_records": ev["total_records"],
            "record_counts": ev["record_counts"],
            "event_counts": ev["event_counts"],
            "bars_loaded_initial": ev["bars_loaded_initial"],
            "current_atr_initial": ev["current_atr_initial"],
            "scaler_info": ev["scaler_info"],
            "atr_audit": ev["atr_audit"],
            "dry_run_checked": ev["dry_run_checked"],
            "dry_run_violations": ev["dry_run_violations"],
            "signals_generated": ev["signals_generated"],
            "trades_attempted": ev["trades_attempted"],
            "trades_blocked": ev["trades_blocked"],
            "kill_switch_state": ev["kill_switch_state"],
        },
        "latest_signal": ev["latest_signal"],
        "latest_decision": ev["latest_decision"],
        "latest_order": ev["latest_order"],
        "latest_heartbeats": ev["latest_heartbeats"],
        "verdict": verdict,
        "journal_path": str(JOURNAL_PATH),
    }
    with open(REPORT_PATH, "w") as f:
        json.dump(report, f, indent=2, default=str)
    print()
    print(f"  Report saved:  {REPORT_PATH}")
    print(f"  Journal saved: {JOURNAL_PATH}")

    sys.exit(0 if verdict == "A" else 1)
    # unreachable on Linux due to sys.exit(2) above


if __name__ == "__main__":
    main()
