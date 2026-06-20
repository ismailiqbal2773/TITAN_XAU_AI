"""
Incremental real data downloader — saves after each day for robustness.
Downloads business days only, persists to per-day parquet, then merges.
"""
import sys, os, time, json, logging
sys.path.insert(0, '/home/z/my-project')
from pathlib import Path
from datetime import datetime, timezone, timedelta
from scripts.real_data.dukascopy_download import download_day, RATE_LIMIT_SLEEP
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

STORAGE = Path("/home/z/my-project/titan/data/xauusd_real")
DAILY_DIR = STORAGE / "daily"
DAILY_DIR.mkdir(parents=True, exist_ok=True)


def download_incremental(start_date: str, end_date: str):
    """Download day-by-day, saving each day's parquet immediately."""
    start = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    end = datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    days = []
    cur = start
    while cur <= end:
        if cur.weekday() < 5:  # Mon-Fri
            days.append(cur)
        cur += timedelta(days=1)
    log.info(f"Downloading {len(days)} trading days {start_date} to {end_date}")
    results = []
    t0 = time.perf_counter()
    for i, day in enumerate(days):
        ymd = day.strftime("%Y-%m-%d")
        daily_path = DAILY_DIR / f"XAUUSD_M1_{ymd}.parquet"
        if daily_path.exists():
            log.info(f"  [{i+1}/{len(days)}] {ymd}: already exists, skipping")
            df = pd.read_parquet(daily_path)
            results.append({"date": ymd, "bars": len(df), "status": "cached"})
            continue
        try:
            df = download_day(day.year, day.month, day.day)
            if df is None or df.empty:
                log.info(f"  [{i+1}/{len(days)}] {ymd}: no data (holiday)")
                results.append({"date": ymd, "bars": 0, "status": "no_data"})
                continue
            df.to_parquet(daily_path)
            elapsed = time.perf_counter() - t0
            log.info(f"  [{i+1}/{len(days)}] {ymd}: {len(df)} bars saved "
                     f"({elapsed:.0f}s elapsed)")
            results.append({"date": ymd, "bars": len(df), "status": "downloaded"})
        except Exception as e:
            log.error(f"  [{i+1}/{len(days)}] {ymd}: FAILED — {e}")
            results.append({"date": ymd, "bars": 0, "status": f"error: {e}"})
    # Merge all daily files into monthly parquets
    log.info("Merging daily files into monthly parquets...")
    monthly: dict[str, list[pd.DataFrame]] = {}
    for r in results:
        if r["bars"] == 0:
            continue
        daily_path = DAILY_DIR / f"XAUUSD_M1_{r['date']}.parquet"
        if not daily_path.exists():
            continue
        df = pd.read_parquet(daily_path)
        ym = r["date"][:7]
        monthly.setdefault(ym, []).append(df)
    output_paths = []
    for ym, frames in sorted(monthly.items()):
        merged = pd.concat(frames).sort_index()
        merged = merged[~merged.index.duplicated(keep="last")]
        out_path = STORAGE / f"XAUUSD_M1_{ym}.parquet"
        merged.to_parquet(out_path)
        output_paths.append(str(out_path))
        log.info(f"  Merged {ym}: {len(merged)} bars → {out_path.name}")
    total_bars = sum(r["bars"] for r in results)
    elapsed = time.perf_counter() - t0
    summary = {
        "start_date": start_date, "end_date": end_date,
        "days_total": len(days), "days_with_data": sum(1 for r in results if r["bars"] > 0),
        "total_bars": total_bars, "duration_seconds": round(elapsed, 1),
        "output_paths": output_paths, "daily_results": results,
    }
    with open(STORAGE / "download_summary.json", "w") as f:
        json.dump(summary, f, indent=2)
    log.info(f"Done: {summary['days_with_data']}/{len(days)} days, {total_bars} bars, {elapsed:.0f}s")
    return summary


if __name__ == "__main__":
    start = sys.argv[1] if len(sys.argv) > 1 else "2024-01-01"
    end = sys.argv[2] if len(sys.argv) > 2 else "2024-01-12"
    download_incremental(start, end)
