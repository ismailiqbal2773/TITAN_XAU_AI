#!/usr/bin/env python3
"""
TITAN Broker Data Acquisition (HistData.com)
=============================================
Linux-compatible alternative to MT5 broker history downloads.

HistData.com provides REAL historical XAUUSD M1 OHLC data sourced
from Dukascopy feed (same underlying interbank rates). While not
literally per-broker (Exness/ICMarkets), this data represents the
industry-standard interbank baseline that brokers mark up.

We use this as a SECOND INDEPENDENT SOURCE alongside our direct
Dukascopy download for cross-validation purposes.

Storage:
    titan/data/sources/histdata/daily/XAUUSD_M1_YYYY-MM-DD.parquet

Schema (same as Dukascopy):
    timestamp (index), open, high, low, close, volume, spread

Note: HistData M1 ASCII files don't include spread, so we set
spread=NaN for these. Use this for cross-source price validation
only, not for spread analysis.
"""
import sys
import time
import io
import zipfile
import concurrent.futures as cf
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests

PROJECT = Path("/home/z/my-project")
OUT = PROJECT / "titan" / "data" / "sources" / "histdata" / "daily"
OUT.mkdir(parents=True, exist_ok=True)

BASE = "https://www.histdata.com/get.php"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
    "Referer": "https://www.histdata.com/download-free-forex-data/",
}


def download_month(year: int, month: int) -> pd.DataFrame | None:
    """Download one month of M1 XAUUSD data from HistData.com."""
    form = {
        "tk": "",
        "date": str(year),
        "datemonth": f"{year}{month:02d}",
        "platform": "ASCII",
        "timeframe": "M1",
        "fxpair": "XAUUSD",
    }
    for attempt in range(3):
        try:
            r = requests.post(BASE, data=form, headers=HEADERS, timeout=60)
            if r.status_code != 200:
                time.sleep(2 * (attempt + 1))
                continue
            # Response is a ZIP file
            if not r.content.startswith(b"PK"):
                time.sleep(2 * (attempt + 1))
                continue
            z = zipfile.ZipFile(io.BytesIO(r.content))
            # Find the .csv inside
            csv_names = [n for n in z.namelist() if n.endswith(".csv")]
            if not csv_names:
                continue
            with z.open(csv_names[0]) as f:
                # HistData ASCII format: datetime;open;high;low;close;volume
                # datetime: YYYYMMDD HHMMSS
                df = pd.read_csv(
                    f, sep=";", header=None,
                    names=["datetime", "open", "high", "low", "close", "volume"],
                    parse_dates=["datetime"],
                    date_format="%Y%m%d %H%M%S",
                )
                df = df.set_index("datetime")
                df.index.name = "timestamp"
                df.index = df.index.tz_localize("UTC")
                # Match Dukascopy schema
                df["spread"] = float("nan")
                df = df[["open", "high", "low", "close", "volume", "spread"]]
                return df
        except Exception as e:
            print(f"    attempt {attempt+1} err: {type(e).__name__}: {str(e)[:60]}")
            time.sleep(2 * (attempt + 1))
    return None


def save_monthly_as_daily(df: pd.DataFrame, year: int, month: int) -> int:
    """Split monthly DataFrame into daily parquet files. Returns file count."""
    count = 0
    for day_str, day_df in df.groupby(df.index.date):
        ymd = day_str.isoformat()
        path = OUT / f"XAUUSD_M1_{ymd}.parquet"
        if path.exists():
            existing = pd.read_parquet(path)
            if len(existing) >= len(day_df):
                continue
        day_df.to_parquet(path)
        count += 1
    return count


def run(start_year: int = 2020, end_year: int = 2024):
    print(f"[histdata] Acquiring XAUUSD M1 from HistData.com")
    print(f"[histdata] Range: {start_year}-{end_year}")
    print(f"[histdata] Output: {OUT}")
    print()

    t0 = time.time()
    total_bars = 0
    total_days = 0
    failed = []

    months = [(y, m) for y in range(start_year, end_year + 1)
              for m in range(1, 13)]

    # Sequential download (HistData rate-limits aggressively)
    for i, (y, m) in enumerate(months, 1):
        ym = f"{y}-{m:02d}"
        print(f"[histdata] [{i}/{len(months)}] {ym}...", end=" ", flush=True)
        df = download_month(y, m)
        if df is None or df.empty:
            print("EMPTY")
            failed.append(ym)
            time.sleep(2)
            continue
        n_days = save_monthly_as_daily(df, y, m)
        total_bars += len(df)
        total_days += n_days
        print(f"{len(df):,} bars  {n_days} days")
        # Rate limit
        time.sleep(1.5)

    elapsed = time.time() - t0
    print()
    print(f"[histdata] DONE in {elapsed:.0f}s")
    print(f"[histdata] Total bars: {total_bars:,}")
    print(f"[histdata] Total days: {total_days}")
    print(f"[histdata] Failed months: {len(failed)}")
    if failed:
        print(f"[histdata] Failed: {failed}")


if __name__ == "__main__":
    sy = int(sys.argv[1]) if len(sys.argv) > 1 else 2020
    ey = int(sys.argv[2]) if len(sys.argv) > 2 else 2024
    run(sy, ey)
