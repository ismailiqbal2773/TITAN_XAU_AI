#!/usr/bin/env python3
"""
TITAN Yahoo Finance Gold Proxy Acquisition
============================================
Acquires GLD ETF daily data from Yahoo Finance v8 chart API as an
INDEPENDENT third-party reference for cross-validating XAUUSD price
trends. GLD tracks gold spot (XAUUSD) with ~1-day lag and ETF expense
ratio (~0.40% annualized).

This is NOT used as primary training data — only as a sanity check
that our Dukascopy XAUUSD prices are aligned with publicly observable
gold prices.

Storage:
    titan/data/sources/yahoo_gld/XAUUSD_D1_Yahoo.parquet
"""
import sys
import time
import json
from pathlib import Path
from datetime import datetime, timezone

import pandas as pd
import requests

PROJECT = Path("/home/z/my-project")
OUT = PROJECT / "titan" / "data" / "sources" / "yahoo_gld"
OUT.mkdir(parents=True, exist_ok=True)


def fetch_yahoo(symbol: str, period1: int, period2: int, interval: str = "1d"):
    """Fetch historical data from Yahoo Finance v8 chart API."""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    params = {
        "period1": period1,
        "period2": period2,
        "interval": interval,
        "events": "div,split",
    }
    headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"}
    r = requests.get(url, params=params, headers=headers, timeout=20)
    r.raise_for_status()
    j = r.json()
    result = j["chart"]["result"][0]
    ts = result["timestamp"]
    quote = result["indicators"]["quote"][0]
    df = pd.DataFrame({
        "timestamp": pd.to_datetime(ts, unit="s", utc=True),
        "open": quote["open"],
        "high": quote["high"],
        "low": quote["low"],
        "close": quote["close"],
        "volume": quote["volume"],
    })
    return df.set_index("timestamp")


def main():
    print("=" * 70)
    print("TITAN Yahoo Finance Gold Proxy Acquisition")
    print("=" * 70)
    # Range: 2020-01-01 to 2024-12-31
    p1 = int(datetime(2020, 1, 1, tzinfo=timezone.utc).timestamp())
    p2 = int(datetime(2024, 12, 31, tzinfo=timezone.utc).timestamp())

    print(f"Symbols: GLD (gold ETF proxy for XAUUSD)")
    print(f"Range:   2020-01-01 → 2024-12-31 (daily)")
    print()

    for sym in ["GLD", "XAUUSD=X"]:
        try:
            print(f"  Fetching {sym}...")
            df = fetch_yahoo(sym, p1, p2, "1d")
            print(f"    OK: {len(df)} bars")
            print(f"    Date range: {df.index[0]} → {df.index[-1]}")
            print(f"    Last close: ${df['close'].iloc[-1]:.2f}")
            path = OUT / f"{sym.replace('=','_')}_D1_Yahoo.parquet"
            df.to_parquet(path)
            print(f"    Saved: {path}")
        except Exception as e:
            print(f"    FAILED: {type(e).__name__}: {str(e)[:100]}")
        time.sleep(1)

    # List output
    print()
    print("Output directory:")
    for f in sorted(OUT.glob("*.parquet")):
        df = pd.read_parquet(f)
        print(f"  {f.name}: {len(df)} bars")


if __name__ == "__main__":
    main()
