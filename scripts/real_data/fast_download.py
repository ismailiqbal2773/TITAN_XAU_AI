#!/usr/bin/env python3
"""
TITAN XAU AI — Real Dukascopy M1 XAUUSD Downloader (SCHEMA-ALIGNED)
====================================================================

Single-purpose, no-duplicate script. Downloads REAL tick data from
Dukascopy public datafeed and aggregates to M1 OHLCV+spread parquet files
matching the project's EXISTING schema (verified from existing files):

    titan/data/sources/dukascopy/daily/XAUUSD_M1_YYYY-MM-DD.parquet

Existing schema (MUST match exactly):
    Index:  timestamp (datetime64[ns, UTC]) — bar start, UTC
    Columns (all float64):
        open, high, low, close  — mid-price OHLC
        volume                  — tick count in bar (stored as float64)
        spread                  — mean (ask-bid) in price units

Dukascopy datafeed format (verified 2026-06):
    URL: https://datafeed.dukascopy.com/datafeed/XAUUSD/{YYYY}/{MM0idx}/{DD}/{HH}h_ticks.bi5
    Encoding: LZMA-compressed big-endian uint32 array, 5 fields × 4 bytes = 20 bytes/tick
    Fields: (timestamp_offset_ms, ask_raw, bid_raw, ask_volume, bid_volume)
    Price scaling: divide raw by 1000.0 (XAUUSD has 3 decimal places)

Usage:
    python fast_download.py YYYY-MM-DD YYYY-MM-DD
    python fast_download.py 2020-04-01 2020-04-15     # 2-week batch
    python fast_download.py 2021-01-01 2021-01-31     # full month

Features:
    - Resume-safe: skips dates already present and non-empty
    - Retry with exponential backoff (max 4 retries)
    - Parallel hour-fetch within a day (8 workers)
    - Daily parquet output (atomic rename on completion)
    - Never overwrites existing non-empty daily file (idempotent)
    - Logs missing/empty days for follow-up
    - NO synthetic data, NO placeholders

Blocker safety: designed to run inside `timeout 300`. If killed mid-day,
partial in-progress file is left in .partial/ and re-tried next run.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import lzma
import struct
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import requests

# ----------------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------------
PROJECT_ROOT = Path("/home/z/my-project")
OUTPUT_DIR = PROJECT_ROOT / "titan" / "data" / "sources" / "dukascopy" / "daily"
PARTIAL_DIR = PROJECT_ROOT / "titan" / "data" / "sources" / "dukascopy" / ".partial"
LOG_FILE = PROJECT_ROOT / "scripts" / "real_data" / "download_log.csv"

BASE_URL = "https://datafeed.dukascopy.com/datafeed/XAUUSD"
SYMBOL = "XAUUSD"
TIMEOUT_SEC = 20
MAX_WORKERS = 24    # 24 hours in parallel — max throughput
MAX_RETRIES = 3
BACKOFF_BASE = 1.5  # seconds

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
PARTIAL_DIR.mkdir(parents=True, exist_ok=True)


# ----------------------------------------------------------------------------
# HTTP fetch with retry
# ----------------------------------------------------------------------------
def fetch_bi5(url: str) -> bytes | None:
    """Fetch a .bi5 file. Returns decompressed bytes or None if 404/empty."""
    last_err = None
    for attempt in range(MAX_RETRIES):
        try:
            r = requests.get(url, timeout=TIMEOUT_SEC)
            if r.status_code == 404:
                return None  # market closed / no data for this hour
            if r.status_code == 200 and len(r.content) > 0:
                try:
                    return lzma.decompress(r.content)
                except lzma.LZMAError:
                    last_err = "LZMAError"
                    continue
            last_err = f"HTTP {r.status_code}"
        except (requests.Timeout, requests.ConnectionError) as e:
            last_err = type(e).__name__
        time.sleep(BACKOFF_BASE * (2 ** attempt))
    sys.stderr.write(f"  ! FAILED {url}  ({last_err})\n")
    return None


# ----------------------------------------------------------------------------
# Tick parsing
# ----------------------------------------------------------------------------
def parse_ticks(raw: bytes, day_date: datetime, hour: int) -> list[tuple]:
    """Parse decompressed tick bytes into (ts_ms, ask, bid, avol, bvol) tuples.

    CRITICAL: Dukascopy tick timestamp offsets are RELATIVE TO THE HOUR START,
    not day start. We compute hour_start_ms = day_start + hour*3600s.
    """
    if not raw or len(raw) < 20:
        return []
    n = len(raw) // 20
    ticks = []
    unpack = struct.Struct(">LLLLL").unpack_from
    # Hour start in epoch ms (UTC)
    hour_start_ms = int(day_date.timestamp() * 1000) + (hour * 3_600_000)
    for i in range(n):
        off, ask_raw, bid_raw, avol, bvol = unpack(raw, i * 20)
        ts_ms = hour_start_ms + off
        ticks.append((ts_ms, ask_raw / 1000.0, bid_raw / 1000.0, avol, bvol))
    return ticks


# ----------------------------------------------------------------------------
# Per-day download + M1 aggregation
# ----------------------------------------------------------------------------
def fetch_day_hours(day_date: datetime) -> list[tuple]:
    """Fetch all 24 hours for one day in parallel. Returns list of (hour, ticks)."""
    yyyy = f"{day_date.year:04d}"
    mm = f"{day_date.month - 1:02d}"   # Dukascopy uses 0-indexed month!
    dd = f"{day_date.day:02d}"
    out = []
    urls = [(h, f"{BASE_URL}/{yyyy}/{mm}/{dd}/{h:02d}h_ticks.bi5") for h in range(24)]

    with cf.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(fetch_bi5, u): h for h, u in urls}
        for fut in cf.as_completed(futures):
            h = futures[fut]
            raw = fut.result()
            if raw:
                # Pass hour to parse_ticks so offset is computed from hour start
                ticks = parse_ticks(raw, day_date, h)
                if ticks:
                    out.append((h, ticks))
    out.sort(key=lambda x: x[0])
    return out


def aggregate_m1(day_date: datetime, hour_ticks: list[tuple]) -> pd.DataFrame:
    """Build M1 OHLCV+spread DataFrame for one day, matching existing schema.

    Existing schema:
        Index: timestamp (datetime64[ns, UTC])
        Columns: open, high, low, close, volume, spread  (all float64)
    """
    all_ticks = []
    for _, ticks in hour_ticks:
        all_ticks.extend(ticks)
    if not all_ticks:
        return pd.DataFrame()

    df = pd.DataFrame(
        all_ticks, columns=["ts_ms", "ask", "bid", "avol", "bvol"]
    )
    # Bucket by minute: floor ts_ms to minute boundary
    df["minute_ms"] = (df["ts_ms"] // 60_000) * 60_000
    df["mid"] = (df["ask"] + df["bid"]) / 2.0
    df["spread"] = (df["ask"] - df["bid"]).clip(lower=0)

    agg = df.groupby("minute_ms", as_index=False).agg(
        open=("mid", "first"),
        high=("mid", "max"),
        low=("mid", "min"),
        close=("mid", "last"),
        volume=("ts_ms", "count"),
        spread=("spread", "mean"),
    )
    # Convert minute_ms back to datetime UTC and set as index
    agg["timestamp"] = pd.to_datetime(agg["minute_ms"], unit="ms", utc=True)
    agg = agg.set_index("timestamp")[
        ["open", "high", "low", "close", "volume", "spread"]
    ].astype("float64")
    return agg


def write_daily_parquet(df: pd.DataFrame, day_date: datetime) -> Path:
    """Atomically write one day's M1 bars to parquet, preserving index."""
    fname = f"{SYMBOL}_M1_{day_date.strftime('%Y-%m-%d')}.parquet"
    final_path = OUTPUT_DIR / fname
    partial_path = PARTIAL_DIR / fname
    # Use pandas to_parquet (preserves DatetimeIndex) — matches existing files
    df.to_parquet(partial_path, engine="pyarrow", compression="snappy")
    partial_path.rename(final_path)
    return final_path


def day_is_complete(day_date: datetime) -> bool:
    """Check if a non-empty daily parquet already exists."""
    fname = f"{SYMBOL}_M1_{day_date.strftime('%Y-%m-%d')}.parquet"
    p = OUTPUT_DIR / fname
    if not p.exists():
        return False
    try:
        pf = pq.ParquetFile(p)
        return pf.metadata.num_rows > 0
    except Exception:
        return False


# Known XAUUSD market holidays where Dukascopy returns no/empty data.
# Format: ISO date strings. We treat these as "complete" so they're skipped.
KNOWN_HOLIDAYS = {
    "2020-04-10",  # Good Friday 2020
    "2020-12-25",  # Christmas
    "2021-01-01",  # New Year
    "2021-12-24",  # Christmas Eve
    "2021-12-31",  # New Year Eve
    "2022-04-15",  # Good Friday 2022
    "2022-12-26",  # Christmas (observed)
    "2023-04-07",  # Good Friday 2023
    "2023-12-25",  # Christmas
    "2024-01-01",  # New Year
    "2024-03-29",  # Good Friday 2024
    "2024-12-25",  # Christmas
}


def is_known_holiday(day_date: datetime) -> bool:
    return day_date.strftime("%Y-%m-%d") in KNOWN_HOLIDAYS


# ----------------------------------------------------------------------------
# Main loop
# ----------------------------------------------------------------------------
def daterange(start: datetime, end: datetime):
    cur = start
    while cur <= end:
        yield cur
        cur += timedelta(days=1)


def is_weekend(d: datetime) -> bool:
    return d.weekday() >= 5


def append_log(day: datetime, bars: int, status: str, elapsed: float):
    line = f"{day.strftime('%Y-%m-%d')},{bars},{status},{elapsed:.2f}\n"
    with open(LOG_FILE, "a") as f:
        f.write(line)


def run(start_str: str, end_str: str):
    start = datetime.strptime(start_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    end = datetime.strptime(end_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    print(f"TITAN Real Data Downloader (SCHEMA-ALIGNED)")
    print(f"  Range:   {start.date()} -> {end.date()}")
    print(f"  Output:  {OUTPUT_DIR}")
    print(f"  Workers: {MAX_WORKERS}  Timeout: {TIMEOUT_SEC}s  Retries: {MAX_RETRIES}")
    print()

    total = 0
    skipped = 0
    failed_days = []
    t_start = time.time()

    for day in daterange(start, end):
        if is_weekend(day):
            continue
        if is_known_holiday(day):
            skipped += 1
            continue
        if day_is_complete(day):
            skipped += 1
            continue

        t_day = time.time()
        hour_ticks = fetch_day_hours(day)
        if not hour_ticks:
            print(f"  {day.date()}  EMPTY (no ticks — likely holiday)")
            append_log(day, 0, "EMPTY", time.time() - t_day)
            failed_days.append(day.date())
            continue

        df = aggregate_m1(day, hour_ticks)
        if df.empty:
            print(f"  {day.date()}  EMPTY after aggregation")
            append_log(day, 0, "EMPTY", time.time() - t_day)
            failed_days.append(day.date())
            continue

        path = write_daily_parquet(df, day)
        elapsed = time.time() - t_day
        total += len(df)
        print(f"  {day.date()}  {len(df):5d} bars  ({elapsed:5.2f}s)  -> {path.name}")
        append_log(day, len(df), "OK", elapsed)

    print()
    print(f"Done. {total:,} new bars written. {skipped} days skipped (already present).")
    if failed_days:
        print(f"Empty/holiday days ({len(failed_days)}):")
        for d in failed_days:
            print(f"  - {d}")
    print(f"Total elapsed: {time.time() - t_start:.1f}s")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("Usage: python fast_download.py YYYY-MM-DD YYYY-MM-DD")
    run(sys.argv[1], sys.argv[2])
