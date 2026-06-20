#!/usr/bin/env python3
"""
TITAN Persistent Background Downloader
======================================
Forks itself into background, runs many small batches sequentially,
logs to a file. Survives parent bash session timeouts.

Usage:
    nohup /home/z/.venv/bin/python scripts/real_data/bg_download.py \
        > scripts/real_data/_archive/bg.out 2>&1 &
    echo $!
"""
import sys, os, time, json, concurrent.futures as cf
from datetime import datetime, date, timedelta
from pathlib import Path
import pandas as pd

PROJECT = Path("/home/z/my-project")
DAILY = PROJECT / "titan" / "data" / "sources" / "dukascopy" / "daily"
LOGFILE = PROJECT / "scripts" / "real_data" / "bg_progress.log"
STOPF = PROJECT / "scripts" / "real_data" / "STOP_BG"

sys.path.insert(0, str(PROJECT))
from scripts.real_data.fast_download import download_day_fast, _is_complete


def get_missing():
    present = set()
    for f in DAILY.glob("XAUUSD_M1_*.parquet"):
        try:
            df = pd.read_parquet(f, columns=["open"])
            if len(df) > 0:
                present.add(f.stem.split("_")[-1])
        except Exception:
            pass
    all_td = []
    d = date(2020, 1, 1)
    while d <= date(2024, 12, 31):
        if d.weekday() < 5:
            all_td.append(d.isoformat())
        d += timedelta(days=1)
    return [d for d in all_td if d not in present]


def log(msg):
    line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOGFILE, "a") as f:
        f.write(line + "\n")


def download_day(ymd):
    y, m, d = int(ymd[:4]), int(ymd[5:7]), int(ymd[8:10])
    path = DAILY / f"XAUUSD_M1_{ymd}.parquet"
    if _is_complete(path):
        return ("cached", 0)
    try:
        df = download_day_fast(y, m, d)
        if df is None or df.empty:
            return ("empty", 0)
        df.to_parquet(path)
        return ("ok", len(df))
    except Exception as e:
        return ("error", 0)


def main():
    log("=== BG DOWNLOADER START ===")
    t0 = time.time()
    grand_ok = 0
    grand_bars = 0
    grand_empty = 0
    iteration = 0

    while True:
        if STOPF.exists():
            log("STOP file detected — exiting")
            break

        missing = get_missing()
        if not missing:
            log("ALL DAYS COVERED — DONE!")
            break

        batch = missing[:30]
        log(f"Batch {iteration+1}: {len(batch)} days, {len(missing)} total missing. "
            f"Range: {batch[0]} → {batch[-1]}")

        with cf.ThreadPoolExecutor(max_workers=18) as pool:
            futures = {pool.submit(download_day, ymd): ymd for ymd in batch}
            batch_ok = batch_bars = batch_empty = batch_err = 0
            for fut in cf.as_completed(futures):
                status, bars = fut.result()
                if status == "ok":
                    batch_ok += 1
                    batch_bars += bars
                elif status == "empty":
                    batch_empty += 1
                elif status == "error":
                    batch_err += 1
            grand_ok += batch_ok
            grand_bars += batch_bars
            grand_empty += batch_empty
            elapsed = time.time() - t0
            log(f"  Batch {iteration+1} done: ok={batch_ok} empty={batch_empty} "
                f"err={batch_err} bars={batch_bars:,}. "
                f"Cumulative: ok={grand_ok} bars={grand_bars:,} "
                f"empty={grand_empty} ({elapsed:.0f}s)")

        iteration += 1
        time.sleep(1)  # brief pause

    log(f"=== BG DOWNLOADER FINISHED ===")
    log(f"Total: {grand_ok} days, {grand_bars:,} bars, "
        f"{grand_empty} empty (holidays). {time.time()-t0:.0f}s")
    # Final merge
    log("Running final monthly merge...")
    try:
        from scripts.real_data.fast_download import merge_monthly
        merge_monthly()
        log("Monthly merge done.")
    except Exception as e:
        log(f"Merge failed: {e}")


if __name__ == "__main__":
    main()
