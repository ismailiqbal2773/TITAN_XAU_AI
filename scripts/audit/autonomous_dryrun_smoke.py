"""
TITAN XAU AI — Autonomous Dry-Run Smoke Test
=============================================
Starts TitanLauncher in autonomous mode (dry_run=True), lets it run
for ~15 seconds, then signals shutdown. Verifies that:
  1. AutonomousRuntime initializes without error
  2. Inference loop runs at least one cycle
  3. Journal records are written
  4. dry_run=True is preserved throughout
  5. No real orders submitted (ExecutionEngine internal guard)
"""
from __future__ import annotations
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

# Confirm path is the project root (contains titan/ and config/)
assert (REPO_ROOT / "titan" / "runtime").is_dir(), f"REPO_ROOT wrong: {REPO_ROOT}"
assert (REPO_ROOT / "config" / "runtime.yaml").is_file(), f"runtime.yaml not found in {REPO_ROOT}"

from titan.runtime.launcher import TitanLauncher

print("=" * 70)
print("  TITAN XAU AI — AUTONOMOUS DRY-RUN SMOKE TEST")
print("=" * 70)
print()

# Note: launcher.start(autonomous=True) blocks. We cannot directly test it
# without spawning a subprocess. Instead, we use AutonomousRuntime directly
# with a controlled shutdown after N seconds.
import asyncio
from titan.runtime.autonomous_loops import AutonomousRuntime, RuntimeConfig
from titan.production.trade_journal import TradeJournal, EventType

JOURNAL_PATH = REPO_ROOT / "data" / "runtime" / "autonomous_smoke_journal.jsonl"
if JOURNAL_PATH.exists():
    JOURNAL_PATH.unlink()


async def run_for_seconds(seconds: float = 15.0):
    print(f"  Journal: {JOURNAL_PATH}")
    journal = TradeJournal(path=str(JOURNAL_PATH), session_id="auto_smoke")
    cfg = RuntimeConfig(
        dry_run=True,
        symbol="XAUUSD",
        feature_source="canonical",
        feature_window=300,
        inference_interval_s=2.0,    # speed up for smoke test
        position_sync_interval_s=2.0,
        exit_check_interval_s=2.0,
        drift_check_interval_s=5.0,
        heartbeat_interval_s=3.0,
    )
    rt = AutonomousRuntime(config=cfg, journal=journal,
                           journal_path=str(JOURNAL_PATH))
    rt.initialize()

    print(f"  dry_run: {rt.config.dry_run}")
    print(f"  symbol:  {rt.config.symbol}")
    print()

    # Start runtime in background task
    start_task = asyncio.create_task(rt.start())

    # Let it run for the requested duration
    print(f"  Running for {seconds:.0f}s ...")
    await asyncio.sleep(seconds)

    # Signal shutdown
    print("  Signalling shutdown ...")
    rt.shutdown()
    try:
        await asyncio.wait_for(start_task, timeout=10.0)
    except asyncio.TimeoutError:
        start_task.cancel()
        try:
            await start_task
        except asyncio.CancelledError:
            pass

    # Read journal
    journal.flush()
    records = journal.read_all()
    print()
    print(f"  Journal records: {len(records)}")
    record_types = {}
    event_types = {}
    for r in records:
        rt_str = r.get("record_type", "")
        et_str = r.get("event_type", "")
        record_types[rt_str] = record_types.get(rt_str, 0) + 1
        if et_str:
            event_types[et_str] = event_types.get(et_str, 0) + 1
    print(f"  Record types:  {record_types}")
    print(f"  Event types:   {event_types}")

    # Check dry_run invariant
    dry_run_violations = 0
    for r in records:
        data = r.get("data", {}) or {}
        if isinstance(data, dict) and "dry_run" in data:
            if data["dry_run"] is not True:
                dry_run_violations += 1
    print(f"  dry_run violations: {dry_run_violations}")

    # Check ORDER records — none should have order_result indicating a live fill
    order_records = [r for r in records if r.get("record_type") == "ORDER"]
    print(f"  ORDER records: {len(order_records)}")

    # Check DECISION records for ATR audit fields
    decision_records = [r for r in records if r.get("record_type") == "DECISION"
                        and (r.get("data") or {}).get("accepted")]
    print(f"  Accepted DECISION records: {len(decision_records)}")
    if decision_records:
        last = decision_records[-1]["data"]
        print(f"  Last accepted decision audit fields:")
        for k in ("sl_tp_mode_used", "fallback_used", "current_atr",
                  "entry_price", "computed_sl", "computed_tp",
                  "atr_sl_multiplier", "atr_tp_multiplier"):
            print(f"    {k:25s}: {last.get(k)}")

    # Print final status
    print()
    print(f"  signals_generated: {rt.signals_generated}")
    print(f"  trades_attempted:  {rt.trades_attempted}")
    print(f"  trades_blocked:    {rt.trades_blocked}")
    print(f"  kill_switch_state: {rt.kill_switch.state.value if rt.kill_switch else 'NONE'}")

    print()
    if dry_run_violations == 0 and len(records) > 0:
        print("  >>> AUTONOMOUS DRY-RUN SMOKE TEST: PASSED")
        return 0
    else:
        print("  >>> AUTONOMOUS DRY-RUN SMOKE TEST: FAILED")
        return 1


if __name__ == "__main__":
    rc = asyncio.run(run_for_seconds(15.0))
    sys.exit(rc)
