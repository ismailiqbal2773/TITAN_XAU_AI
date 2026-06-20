#!/usr/bin/env python3
"""
TITAN XAU AI — Budget-Aware Batch Downloader
================================================

Downloads as many missing days as possible within a wall-clock budget.
Auto-skips weekends and already-downloaded days. Designed to fit in
the agent's per-Bash-call timeout (~110s safe budget).

Usage:
    python budget_download.py [WALL_BUDGET_SEC] [MAX_DAYS]

Default: 90 second budget, max 8 days per call.
"""
from __future__ import annotations

import sys
import time
from datetime import datetime, timedelta, timezone, date
from pathlib import Path

# Reuse helpers
sys.path.insert(0, str(Path(__file__).parent))
from fast_download import (
    OUTPUT_DIR, day_is_complete, is_weekend, is_known_holiday,
    fetch_day_hours, aggregate_m1, write_daily_parquet, append_log,
)

# Target windows (in priority order)
WINDOWS = [
    (date(2020, 4, 1), date(2020, 12, 31)),   # 2020 Q2-Q4 (COVID era)
    (date(2021, 1, 1), date(2021, 12, 31)),   # 2021 full year
    (date(2022, 7, 1), date(2022, 12, 31)),   # 2022 H2 (Fed tightening)
]


def find_next_missing(max_days: int = 8) -> list[datetime]:
    """Find next N missing weekdays across our target windows."""
    missing = []
    for start, end in WINDOWS:
        cur = start
        while cur <= end and len(missing) < max_days:
            if cur.weekday() < 5:
                dt = datetime(cur.year, cur.month, cur.day, tzinfo=timezone.utc)
                if is_known_holiday(dt):
                    continue
                if not day_is_complete(dt):
                    missing.append(dt)
            cur += timedelta(days=1)
        if len(missing) >= max_days:
            break
    return missing


def run(budget_sec: float, max_days: int):
    print(f"TITAN Budget Downloader  budget={budget_sec}s  max_days={max_days}")
    todo = find_next_missing(max_days)
    print(f"  To fetch: {len(todo)} days")
    if not todo:
        print("  Nothing to do — all target windows complete!")
        return

    t_start = time.time()
    total_bars = 0
    done = 0
    for day in todo:
        elapsed = time.time() - t_start
        remaining = budget_sec - elapsed
        if remaining < 30:  # not enough time for another day
            print(f"  ⏱  Budget exhausted ({elapsed:.0f}s elapsed, {remaining:.0f}s left)")
            break

        t_day = time.time()
        hour_ticks = fetch_day_hours(day)
        if not hour_ticks:
            print(f"  {day.date()}  EMPTY (holiday?)")
            append_log(day, 0, "EMPTY", time.time() - t_day)
            done += 1
            continue

        df = aggregate_m1(day, hour_ticks)
        if df.empty:
            print(f"  {day.date()}  EMPTY after aggregation")
            append_log(day, 0, "EMPTY", time.time() - t_day)
            done += 1
            continue

        path = write_daily_parquet(df, day)
        day_elapsed = time.time() - t_day
        total_bars += len(df)
        done += 1
        print(f"  {day.date()}  {len(df):5d} bars  ({day_elapsed:5.1f}s)  -> {path.name}")

    total_elapsed = time.time() - t_start
    print()
    print(f"Done. {done}/{len(todo)} days, {total_bars:,} bars in {total_elapsed:.1f}s")


if __name__ == "__main__":
    budget = float(sys.argv[1]) if len(sys.argv) > 1 else 90.0
    max_days = int(sys.argv[2]) if len(sys.argv) > 2 else 8
    run(budget, max_days)
