#!/usr/bin/env python3
"""
TITAN Real Data Background Downloader v2 (In-Process)
======================================================
Runs entirely in one process — no subprocess. Continuously downloads
missing dates in batches, periodically saving progress + state so we
can resume on restart. Designed for long-running single bash session.

Strategy:
  - Loop: pick next 14-day batch of missing trading days, download
  - Every batch: print + log progress
  - Every 5 batches: re-scan for missing (in case some came in)
  - On Ctrl-C or STOP file: clean exit, save state

Usage:
    timeout 590 python scripts/real_data/download_v2.py
    (runs ~10 minutes per invocation, then exits cleanly)
"""
import json
import signal
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

PROJECT = Path("/home/z/my-project")
DAILY = PROJECT / "titan" / "data" / "sources" / "dukascopy" / "daily"
STATE_FILE = PROJECT / "scripts" / "real_data" / "daemon_state.json"
STOP_FILE = PROJECT / "scripts" / "real_data" / "STOP"

# Use the canonical downloader's functions directly
sys.path.insert(0, str(PROJECT))
from scripts.real_data.fast_download import (
    download_range_fast, _is_complete, DAILY as FD_DAILY
)

assert FD_DAILY == DAILY, "Daily dir mismatch!"

START = date(2020, 1, 1)
END = date(2024, 12, 31)
BATCH_SIZE = 7  # 7 days per batch = ~7 min, fits in 10-min tool window


def list_missing_dates() -> list:
    """Find missing trading days."""
    present = set()
    for f in DAILY.glob("XAUUSD_M1_*.parquet"):
        try:
            df = pd.read_parquet(f, columns=["open"])
            if len(df) > 0:
                present.add(f.stem.split("_")[-1])
        except Exception:
            pass
    missing = []
    d = START
    while d <= END:
        if d.weekday() < 5 and d.isoformat() not in present:
            missing.append(d)
        d += timedelta(days=1)
    return missing


def save_state(state: dict):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, default=str)


def main(max_minutes: int = 9):
    t_start = time.time()
    deadline = t_start + max_minutes * 60
    print(f"[v2] Start at {time.strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
    print(f"[v2] Will run for up to {max_minutes} minutes", flush=True)

    iteration = 0
    total_bars = 0
    total_ok = 0
    total_empty = 0

    while time.time() < deadline:
        if STOP_FILE.exists():
            print("[v2] STOP file detected. Exiting.", flush=True)
            break

        missing = list_missing_dates()
        if not missing:
            print("[v2] All trading days covered. Done!", flush=True)
            # Final merge
            print("[v2] Running final monthly merge...", flush=True)
            download_range_fast("2024-12-30", "2024-12-31", merge=True)
            break

        batch = missing[:BATCH_SIZE]
        bs = batch[0].isoformat()
        be = batch[-1].isoformat()
        print(f"[v2] Batch {iteration+1}: {bs} → {be} "
              f"({len(batch)} days, {len(missing)} still missing)", flush=True)

        try:
            result = download_range_fast(bs, be, merge=False)
            total_bars += result.get("total_bars", 0)
            total_ok += result.get("days_ok", 0)
            total_empty += result.get("days_empty", 0)
            print(f"[v2] Batch {iteration+1} done: "
                  f"ok={result.get('days_ok',0)} "
                  f"empty={result.get('days_empty',0)} "
                  f"bars={result.get('total_bars',0):,}", flush=True)
        except Exception as e:
            print(f"[v2] Batch {iteration+1} FAILED: {e}", flush=True)

        save_state({
            "iteration": iteration + 1,
            "total_bars_downloaded": total_bars,
            "total_days_ok": total_ok,
            "total_days_empty": total_empty,
            "last_batch": f"{bs} → {be}",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "elapsed_minutes": round((time.time() - t_start) / 60, 2),
        })
        iteration += 1

    elapsed = time.time() - t_start
    print(f"\n[v2] Session done: {iteration} batches, "
          f"{total_bars:,} bars, {total_ok} new days, "
          f"{total_empty} empty. {elapsed/60:.1f} min", flush=True)


if __name__ == "__main__":
    # Allow time-budget argument
    mins = int(sys.argv[1]) if len(sys.argv) > 1 else 9
    main(max_minutes=mins)
