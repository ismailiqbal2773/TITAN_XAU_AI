"""
TITAN XAU AI — Real Dukascopy XAUUSD M1 Data Downloader (Production Grade).

Downloads REAL tick data from Dukascopy's free public datafeed, aggregates
to M1 OHLCV+spread bars, and persists to per-day parquet files with resume
capability. NO synthetic data. NO calibration. NO random walk expansion.

Features:
- Resume: skips already-downloaded days
- Weekend/holiday auto-skip (forex closed Sat/Sun)
- Rate-limit aware: exponential backoff on 503/502
- Per-day parquet persistence (robust to interruption)
- Big-endian .bi5 LZMA decompression (20-byte tick records)
- M1 aggregation from tick-level bid/ask data
- Source separation: stored under data/sources/dukascopy/

Dukascopy tick record format (20 bytes, big-endian):
  int32 timestamp_ms (offset from hour start)
  int32 ask (price × 1000)
  int32 bid (price × 1000)
  float32 ask_volume
  float32 bid_volume
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
PRICE_SCALE = 1000  # XAUUSD has 3 decimal places
STORAGE_DIR = Path("/home/z/my-project/titan/data/sources/dukascopy")
DAILY_DIR = STORAGE_DIR / "daily"
DAILY_DIR.mkdir(parents=True, exist_ok=True)

REQUEST_TIMEOUT = 45
MAX_RETRIES = 5
BASE_SLEEP = 0.15  # 150ms between requests (polite rate limit)


def download_hour_ticks(year: int, month: int, day: int, hour: int) -> Optional[bytes]:
    """Download one hour of tick data. Returns raw .bi5 bytes or None (no data)."""
    # Dukascopy uses 0-indexed months in URL (Jan=00)
    url = f"{DUKASCOPY_BASE}/{SYMBOL}/{year}/{month-1:02d}/{day:02d}/{hour:02d}h_ticks.bi5"
    sleep = BASE_SLEEP
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(url, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200:
                time.sleep(BASE_SLEEP)
                return resp.content
            elif resp.status_code == 404:
                return None  # No data (weekend/holiday/after-hours)
            elif resp.status_code in (502, 503):
                # Rate limited — exponential backoff
                sleep_time = sleep * (2 ** attempt)
                log.debug(f"HTTP {resp.status_code} for {url}, backing off {sleep_time:.1f}s")
                time.sleep(sleep_time)
                sleep *= 2
            else:
                log.warning(f"HTTP {resp.status_code} for {url}")
                time.sleep(sleep)
        except requests.RequestException as e:
            sleep_time = sleep * (2 ** attempt)
            log.debug(f"Request error for {url}: {e}, retry in {sleep_time:.1f}s")
            time.sleep(sleep_time)
            sleep *= 2
    return None


def decompress_ticks(bi5_data: bytes, hour_start_ms: int) -> pd.DataFrame:
    """Decompress .bi5 and parse tick records. Big-endian 20-byte records."""
    if not bi5_data or len(bi5_data) == 0:
        return pd.DataFrame()
    try:
        decompressed = lzma.decompress(bi5_data)
    except lzma.LZMAError:
        return pd.DataFrame()
    tick_size = 20
    n_ticks = len(decompressed) // tick_size
    if n_ticks == 0:
        return pd.DataFrame()
    arr = np.frombuffer(decompressed, dtype=np.uint8, count=n_ticks * tick_size).reshape(n_ticks, tick_size)
    # Big-endian parsing
    ts_offset_ms = arr[:, 0:4].copy().view('>i4').flatten().astype(np.int64)
    ts_ms = ts_offset_ms + np.int64(hour_start_ms)
    ask_raw = arr[:, 4:8].copy().view('>i4').flatten()
    bid_raw = arr[:, 8:12].copy().view('>i4').flatten()
    ask_vol = arr[:, 12:16].copy().view('>f4').flatten()
    bid_vol = arr[:, 16:20].copy().view('>f4').flatten()
    bid = bid_raw.astype(np.float64) / PRICE_SCALE
    ask = ask_raw.astype(np.float64) / PRICE_SCALE
    mid = (bid + ask) / 2.0
    spread = ask - bid
    ask_vol = np.where(np.isfinite(ask_vol), ask_vol.astype(np.float64), 0.0)
    bid_vol = np.where(np.isfinite(bid_vol), bid_vol.astype(np.float64), 0.0)
    ts = pd.to_datetime(ts_ms, unit="ms", utc=True)
    return pd.DataFrame({
        "timestamp": ts, "bid": bid, "ask": ask, "mid": mid, "spread": spread,
        "bid_volume": bid_vol, "ask_volume": ask_vol,
    }).set_index("timestamp")


def aggregate_to_m1(ticks_df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate tick data to M1 OHLCV bars with mean spread."""
    if ticks_df.empty:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume", "spread"])
    agg = ticks_df.resample("1min").agg({
        "mid": ["first", "max", "min", "last"],
        "spread": "mean",
    })
    agg.columns = ["open", "high", "low", "close", "spread"]
    agg = agg.dropna(subset=["open"])
    # Volume = tick count per bar (most reliable volume metric for Dukascopy)
    tick_counts = ticks_df.resample("1min").size().reindex(agg.index).fillna(0)
    agg["volume"] = tick_counts.astype(float)
    # Ensure OHLC integrity
    agg["high"] = agg[["open", "high", "close"]].max(axis=1)
    agg["low"] = agg[["open", "low", "close"]].min(axis=1)
    return agg[["open", "high", "low", "close", "volume", "spread"]]


def download_day(year: int, month: int, day: int) -> pd.DataFrame:
    """Download all 24 hours of tick data for one day, return M1 bars."""
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
    if not all_ticks:
        return pd.DataFrame()
    full = pd.concat(all_ticks).sort_index()
    full = full[~full.index.duplicated(keep="last")]
    return aggregate_to_m1(full)


def get_trading_days(start_date: str, end_date: str) -> list[tuple[int, int, int]]:
    """Generate list of (year, month, day) for Mon-Fri in date range."""
    start = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    end = datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    days = []
    cur = start
    while cur <= end:
        if cur.weekday() < 5:  # Mon-Fri
            days.append((cur.year, cur.month, cur.day))
        cur += timedelta(days=1)
    return days


def download_range(start_date: str, end_date: str, max_workers: int = 3) -> dict:
    """Download real XAUUSD M1 data for a date range with resume capability.

    Each day is saved to a separate parquet file. Already-downloaded days
    are skipped. After all days are downloaded, monthly merged files are
    created for convenient loading.
    """
    days = get_trading_days(start_date, end_date)
    log.info(f"Downloading {len(days)} trading days from {start_date} to {end_date}")
    log.info(f"Storage: {DAILY_DIR}")

    results = []
    days_processed = 0
    days_with_data = 0
    total_bars = 0
    total_ticks = 0
    t0 = time.perf_counter()

    # Process days sequentially (rate-limit friendly) with resume
    for i, (y, m, d) in enumerate(days):
        ymd = f"{y:04d}-{m:02d}-{d:02d}"
        daily_path = DAILY_DIR / f"XAUUSD_M1_{ymd}.parquet"
        # Resume: skip if already downloaded
        if daily_path.exists():
            df = pd.read_parquet(daily_path)
            days_processed += 1
            if len(df) > 0:
                days_with_data += 1
                total_bars += len(df)
                results.append({"date": ymd, "bars": len(df), "status": "cached"})
            else:
                results.append({"date": ymd, "bars": 0, "status": "cached_empty"})
            if (i + 1) % 50 == 0:
                elapsed = time.perf_counter() - t0
                log.info(f"  [{i+1}/{len(days)}] {ymd}: cached ({total_bars} bars total, {elapsed:.0f}s)")
            continue

        # Download
        try:
            df = download_day(y, m, d)
            if df is None or df.empty:
                days_processed += 1
                results.append({"date": ymd, "bars": 0, "status": "no_data"})
                # Save empty marker to avoid re-trying
                pd.DataFrame().to_parquet(daily_path)
                continue
            df.to_parquet(daily_path)
            days_processed += 1
            days_with_data += 1
            total_bars += len(df)
            results.append({"date": ymd, "bars": len(df), "status": "downloaded"})
            if (i + 1) % 10 == 0:
                elapsed = time.perf_counter() - t0
                rate = (i + 1) / elapsed if elapsed > 0 else 0
                eta = (len(days) - i - 1) / rate if rate > 0 else 0
                log.info(f"  [{i+1}/{len(days)}] {ymd}: {len(df)} bars "
                         f"({total_bars} total, {elapsed:.0f}s, ETA {eta:.0f}s)")
        except Exception as e:
            log.error(f"  [{i+1}/{len(days)}] {ymd}: ERROR — {e}")
            results.append({"date": ymd, "bars": 0, "status": f"error: {e}"})

    # Merge daily files into monthly parquets
    log.info("Merging daily files into monthly parquets...")
    monthly: dict[str, list[pd.DataFrame]] = {}
    for r in results:
        if r["bars"] == 0:
            continue
        daily_path = DAILY_DIR / f"XAUUSD_M1_{r['date']}.parquet"
        if not daily_path.exists():
            continue
        df = pd.read_parquet(daily_path)
        if df.empty:
            continue
        ym = r["date"][:7]
        monthly.setdefault(ym, []).append(df)
    monthly_paths = []
    for ym, frames in sorted(monthly.items()):
        merged = pd.concat(frames).sort_index()
        merged = merged[~merged.index.duplicated(keep="last")]
        out_path = STORAGE_DIR / f"XAUUSD_M1_{ym}.parquet"
        merged.to_parquet(out_path)
        monthly_paths.append(str(out_path))
        log.info(f"  {ym}: {len(merged)} bars → {out_path.name}")

    elapsed = time.perf_counter() - t0
    summary = {
        "source": "dukascopy",
        "symbol": "XAUUSD",
        "timeframe": "M1",
        "start_date": start_date,
        "end_date": end_date,
        "days_total": len(days),
        "days_processed": days_processed,
        "days_with_data": days_with_data,
        "days_no_data": days_processed - days_with_data,
        "total_bars": total_bars,
        "monthly_files": len(monthly_paths),
        "duration_seconds": round(elapsed, 1),
        "daily_results": results,
        "monthly_paths": monthly_paths,
    }
    with open(STORAGE_DIR / "download_summary.json", "w") as f:
        json.dump(summary, f, indent=2)
    log.info(f"Done: {days_with_data}/{days_processed} days, {total_bars} bars, {elapsed:.0f}s")
    return summary


if __name__ == "__main__":
    import sys
    start = sys.argv[1] if len(sys.argv) > 1 else "2020-01-01"
    end = sys.argv[2] if len(sys.argv) > 2 else "2024-12-31"
    summary = download_range(start, end)
    print(f"\nBars: {summary['total_bars']}")
    print(f"Days with data: {summary['days_with_data']}/{summary['days_processed']}")
