"""
TITAN XAU AI — Real XAUUSD M1 Data Acquisition from Dukascopy.

Downloads tick data from Dukascopy's free public datafeed, aggregates
to M1 OHLCV bars, and persists to parquet partitioned by year-month.

Dukascopy tick data URL format:
  https://datafeed.dukascopy.com/datafeed/XAUUSD/{YYYY}/{MM}/{DD}/{HH}h_ticks.bi5

Each .bi5 file is LZMA-compressed binary containing 20-byte tick records:
  int32 timestamp (ms since epoch, offset to start of hour)
  int32 bid (as price × 1e-3)
  int32 ask (as price × 1e-3)
  float32 bid_volume
  float32 ask_volume

We aggregate ticks to M1 OHLCV + mean spread.
"""
from __future__ import annotations

import io
import json
import logging
import lzma
import struct
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

DUKASCOPY_BASE = "https://datafeed.dukascopy.com/datafeed"
SYMBOL = "XAUUSD"
# Dukascopy price scale for XAUUSD (3 decimal places)
PRICE_SCALE = 1000
REQUEST_TIMEOUT = 60
MAX_RETRIES = 5
RATE_LIMIT_SLEEP = 0.2  # 200ms between requests to avoid rate limiting


def download_hour_ticks(year: int, month: int, day: int, hour: int) -> Optional[bytes]:
    """Download one hour of tick data from Dukascopy. Returns raw bytes or None.

    Note: Dukascopy uses 0-indexed months in the URL (Jan=00, Feb=01, ...).
    The `month` parameter here is 1-indexed (Jan=1) and converted internally.
    """
    url = f"{DUKASCOPY_BASE}/{SYMBOL}/{year}/{month-1:02d}/{day:02d}/{hour:02d}h_ticks.bi5"
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(url, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200:
                return resp.content
            elif resp.status_code == 404:
                return None  # No data for this hour (weekend/holiday)
            else:
                log.warning(f"HTTP {resp.status_code} for {url} (attempt {attempt+1})")
        except requests.RequestException as e:
            log.warning(f"Request error for {url}: {e} (attempt {attempt+1})")
        time.sleep(0.5 * (attempt + 1))
    return None


def decompress_ticks(bi5_data: bytes, hour_start_ms: int) -> pd.DataFrame:
    """Decompress .bi5 LZMA data and parse tick records.

    Dukascopy tick record format (20 bytes, big-endian):
      int32 timestamp (ms offset from hour start)
      int32 ask (price × PRICE_SCALE)
      int32 bid (price × PRICE_SCALE)
      float32 ask_volume
      float32 bid_volume
    """
    if not bi5_data or len(bi5_data) == 0:
        return pd.DataFrame()
    try:
        decompressed = lzma.decompress(bi5_data)
    except lzma.LZMAError as e:
        log.warning(f"LZMA decompress failed: {e}")
        return pd.DataFrame()
    tick_size = 20
    n_ticks = len(decompressed) // tick_size
    if n_ticks == 0:
        return pd.DataFrame()
    # Parse with numpy for speed. Dukascopy uses BIG-ENDIAN.
    arr = np.frombuffer(decompressed, dtype=np.uint8, count=n_ticks * tick_size).reshape(n_ticks, tick_size)
    # Timestamp is int32 (ms offset from hour start) — big-endian, convert to int64 to avoid overflow
    ts_offset_ms = arr[:, 0:4].copy().view('>i4').flatten().astype(np.int64)
    ts_ms = ts_offset_ms + np.int64(hour_start_ms)
    # Field order is: ask, bid (NOT bid, ask) — verified empirically. Big-endian int32.
    ask_raw = arr[:, 4:8].copy().view('>i4').flatten()
    bid_raw = arr[:, 8:12].copy().view('>i4').flatten()
    # Volumes are big-endian float32
    ask_vol = arr[:, 12:16].copy().view('>f4').flatten()
    bid_vol = arr[:, 16:20].copy().view('>f4').flatten()
    # Convert prices
    bid = bid_raw.astype(np.float64) / PRICE_SCALE
    ask = ask_raw.astype(np.float64) / PRICE_SCALE
    mid = (bid + ask) / 2.0
    spread = ask - bid
    # Replace any non-finite volumes with 0
    ask_vol = np.where(np.isfinite(ask_vol), ask_vol.astype(np.float64), 0.0)
    bid_vol = np.where(np.isfinite(bid_vol), bid_vol.astype(np.float64), 0.0)
    ts = pd.to_datetime(ts_ms, unit="ms", utc=True)
    return pd.DataFrame({
        "timestamp": ts,
        "bid": bid,
        "ask": ask,
        "mid": mid,
        "spread": spread,
        "bid_volume": bid_vol,
        "ask_volume": ask_vol,
    }).set_index("timestamp")


def aggregate_to_m1(ticks_df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate tick data to M1 OHLCV bars."""
    if ticks_df.empty:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume", "spread"])
    # Resample to 1-minute bars
    agg = ticks_df.resample("1min").agg({
        "mid": ["first", "max", "min", "last"],
        "bid_volume": "sum",
        "ask_volume": "sum",
        "spread": "mean",
    })
    # Flatten multi-index columns
    agg.columns = ["open", "high", "low", "close", "bid_volume", "ask_volume", "spread"]
    # Drop bars with no ticks (NaN open)
    agg = agg.dropna(subset=["open"])
    # Volume: use tick count (more reliable than Dukascopy's float volumes)
    tick_counts = ticks_df.resample("1min").size().reindex(agg.index).fillna(0)
    agg["volume"] = tick_counts.astype(float)
    agg = agg[["open", "high", "low", "close", "volume", "spread"]]
    return agg


def download_day(year: int, month: int, day: int) -> pd.DataFrame:
    """Download all 24 hours of tick data for one day, return M1 bars."""
    # Compute hour start timestamps in ms since epoch
    day_start = datetime(year, month, day, tzinfo=timezone.utc)
    all_ticks = []
    for hour in range(24):
        hour_start = day_start + timedelta(hours=hour)
        hour_start_ms = int(hour_start.timestamp() * 1000)
        bi5 = download_hour_ticks(year, month, day, hour)
        if bi5 is None:
            continue
        ticks_df = decompress_ticks(bi5, hour_start_ms)
        if not ticks_df.empty:
            all_ticks.append(ticks_df)
        time.sleep(RATE_LIMIT_SLEEP)
    if not all_ticks:
        return pd.DataFrame()
    full = pd.concat(all_ticks).sort_index()
    # Remove duplicate timestamps (rare but possible)
    full = full[~full.index.duplicated(keep="last")]
    return aggregate_to_m1(full)


def download_range(start_date: str, end_date: str,
                    storage_dir: str = "/home/z/my-project/titan/data/xauusd_real",
                    max_workers: int = 2) -> dict:
    """Download XAUUSD M1 data for a date range. Returns summary stats.

    Downloads day-by-day, aggregates to M1, persists to parquet partitioned
    by year-month. Skips weekends and holidays automatically (404s).
    """
    storage = Path(storage_dir)
    storage.mkdir(parents=True, exist_ok=True)
    start = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    end = datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    days = []
    cur = start
    while cur <= end:
        # Skip Saturdays (5) and Sundays (6) — forex closed
        if cur.weekday() < 5:
            days.append((cur.year, cur.month, cur.day))
        cur += timedelta(days=1)
    log.info(f"Downloading {len(days)} trading days from {start_date} to {end_date}")

    # Process in batches by month for persistence
    bars_by_month: dict[str, list[pd.DataFrame]] = {}
    errors: list[str] = []
    days_processed = 0
    days_with_data = 0
    total_bars = 0
    t0 = time.perf_counter()

    # Use ThreadPoolExecutor for parallel downloads (I/O bound)
    def fetch_day(ymd):
        y, m, d = ymd
        try:
            return ymd, download_day(y, m, d)
        except Exception as e:
            return ymd, None

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(fetch_day, ymd): ymd for ymd in days}
        for fut in as_completed(futures):
            ymd, day_bars = fut.result()
            days_processed += 1
            if day_bars is None or day_bars.empty:
                continue
            days_with_data += 1
            total_bars += len(day_bars)
            ym = f"{ymd[0]}-{ymd[1]:02d}"
            bars_by_month.setdefault(ym, []).append(day_bars)
            if days_processed % 50 == 0:
                elapsed = time.perf_counter() - t0
                rate = days_processed / elapsed
                log.info(f"  Processed {days_processed}/{len(days)} days "
                         f"({days_with_data} with data, {total_bars} bars), "
                         f"rate={rate:.1f} days/s")

    # Persist by month
    output_paths = []
    for ym, day_frames in sorted(bars_by_month.items()):
        if not day_frames:
            continue
        month_df = pd.concat(day_frames).sort_index()
        month_df = month_df[~month_df.index.duplicated(keep="last")]
        out_path = storage / f"XAUUSD_M1_{ym}.parquet"
        month_df.to_parquet(out_path)
        output_paths.append(str(out_path))
        log.info(f"  Persisted {ym}: {len(month_df)} bars → {out_path.name}")

    elapsed = time.perf_counter() - t0
    summary = {
        "start_date": start_date,
        "end_date": end_date,
        "days_total": len(days),
        "days_processed": days_processed,
        "days_with_data": days_with_data,
        "days_no_data": days_processed - days_with_data,
        "total_bars": total_bars,
        "output_paths": output_paths,
        "duration_seconds": round(elapsed, 1),
        "errors": errors,
    }
    log.info(f"Done: {days_with_data}/{days_processed} days, {total_bars} bars, "
             f"{elapsed:.1f}s")
    return summary


if __name__ == "__main__":
    import sys
    start = sys.argv[1] if len(sys.argv) > 1 else "2024-01-01"
    end = sys.argv[2] if len(sys.argv) > 2 else "2024-03-31"
    summary = download_range(start, end)
    print(json.dumps(summary, indent=2))
