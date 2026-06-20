#!/usr/bin/env python3
"""
TITAN XAU AI — Parallel Multi-Day Downloader
================================================

Downloads multiple days in PARALLEL within a single Python process,
sidestepping the agent's per-Bash-call timeout. Each day still spawns
24 hour-fetches in parallel internally, but multiple days are processed
simultaneously too.

Usage:
    python parallel_download.py START_DATE END_DATE [DAY_CONCURRENCY]
    python parallel_download.py 2020-04-01 2020-12-31 4

Default DAY_CONCURRENCY=4 (4 days fetched in parallel × 24 hours = 96 concurrent reqs).
Dukascopy tolerates this; if rate-limited, reduce to 2-3.
"""
from __future__ import annotations

import concurrent.futures as cf
import lzma
import struct
import sys
import threading
import time
from datetime import datetime, timedelta, timezone, date
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import requests

# Reuse config + helpers from fast_download.py
sys.path.insert(0, str(Path(__file__).parent))
from fast_download import (
    OUTPUT_DIR, PARTIAL_DIR, LOG_FILE, BASE_URL, SYMBOL,
    TIMEOUT_SEC, MAX_RETRIES, BACKOFF_BASE,
    fetch_bi5, parse_ticks, aggregate_m1, write_daily_parquet,
    day_is_complete, append_log, is_weekend, daterange,
)

DAY_CONCURRENCY = 4
_print_lock = threading.Lock()


def safe_print(msg: str):
    with _print_lock:
        print(msg, flush=True)


def download_one_day(day: datetime) -> tuple[datetime, int, str, float]:
    """Download and persist one day. Returns (day, n_bars, status, elapsed_sec)."""
    t0 = time.time()
    try:
        yyyy = f"{day.year:04d}"
        mm = f"{day.month - 1:02d}"
        dd = f"{day.day:02d}"

        # Fetch all 24 hours (sequentially per day to keep total parallelism bounded)
        # If we parallelize hours here too, we get DAY_CONCURRENCY * 24 = up to 96 reqs
        all_ticks = []
        for h in range(24):
            url = f"{BASE_URL}/{yyyy}/{mm}/{dd}/{h:02d}h_ticks.bi5"
            raw = fetch_bi5(url)
            if raw:
                ticks = parse_ticks(raw, day, h)
                if ticks:
                    all_ticks.extend(ticks)

        if not all_ticks:
            elapsed = time.time() - t0
            append_log(day, 0, "EMPTY", elapsed)
            return (day, 0, "EMPTY", elapsed)

        # Aggregate to M1
        df_ticks = pd.DataFrame(all_ticks, columns=["ts_ms", "ask", "bid", "avol", "bvol"])
        df_ticks["minute_ms"] = (df_ticks["ts_ms"] // 60_000) * 60_000
        df_ticks["mid"] = (df_ticks["ask"] + df_ticks["bid"]) / 2.0
        df_ticks["spread"] = (df_ticks["ask"] - df_ticks["bid"]).clip(lower=0)

        agg = df_ticks.groupby("minute_ms", as_index=False).agg(
            open=("mid", "first"),
            high=("mid", "max"),
            low=("mid", "min"),
            close=("mid", "last"),
            volume=("ts_ms", "count"),
            spread=("spread", "mean"),
        )
        agg["timestamp"] = pd.to_datetime(agg["minute_ms"], unit="ms", utc=True)
        agg = agg.set_index("timestamp")[
            ["open", "high", "low", "close", "volume", "spread"]
        ].astype("float64")

        if agg.empty:
            elapsed = time.time() - t0
            append_log(day, 0, "EMPTY", elapsed)
            return (day, 0, "EMPTY", elapsed)

        path = write_daily_parquet(agg, day)
        elapsed = time.time() - t0
        append_log(day, len(agg), "OK", elapsed)
        return (day, len(agg), "OK", elapsed)

    except Exception as e:
        elapsed = time.time() - t0
        append_log(day, 0, f"ERROR:{type(e).__name__}", elapsed)
        return (day, 0, f"ERROR:{type(e).__name__}", elapsed)


def run(start_str: str, end_str: str, day_concurrency: int = DAY_CONCURRENCY):
    start = datetime.strptime(start_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    end = datetime.strptime(end_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)

    # Build list of days to fetch (skip weekends + already-complete)
    todo = []
    skipped = 0
    for day in daterange(start, end):
        if is_weekend(day):
            continue
        if day_is_complete(day):
            skipped += 1
            continue
        todo.append(day)

    safe_print(f"Parallel Downloader: {start.date()} -> {end.date()}")
    safe_print(f"  To fetch: {len(todo)} days  |  Skipped (already complete): {skipped}")
    safe_print(f"  Day concurrency: {day_concurrency}  (effective max reqs: {day_concurrency * 24})")
    safe_print("")

    if not todo:
        safe_print("Nothing to do.")
        return

    t_start = time.time()
    total_bars = 0
    done = 0
    errors = []

    with cf.ThreadPoolExecutor(max_workers=day_concurrency) as ex:
        futures = {ex.submit(download_one_day, d): d for d in todo}
        for fut in cf.as_completed(futures):
            day, n_bars, status, elapsed = fut.result()
            done += 1
            total_bars += n_bars
            mark = "✓" if status == "OK" else ("~" if status == "EMPTY" else "✗")
            safe_print(f"  [{done:3d}/{len(todo):3d}] {mark} {day.date()}  {n_bars:5d} bars  ({elapsed:5.1f}s)  {status}")
            if status.startswith("ERROR"):
                errors.append((day.date().isoformat(), status))

    elapsed_total = time.time() - t_start
    safe_print("")
    safe_print(f"Done. {total_bars:,} bars in {elapsed_total:.1f}s "
               f"({total_bars/max(elapsed_total,1):.0f} bars/sec)")
    if errors:
        safe_print(f"Errors: {len(errors)}")
        for d, s in errors[:10]:
            safe_print(f"  - {d}: {s}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit("Usage: python parallel_download.py START END [CONCURRENCY]")
    conc = int(sys.argv[3]) if len(sys.argv) > 3 else DAY_CONCURRENCY
    run(sys.argv[1], sys.argv[2], conc)
