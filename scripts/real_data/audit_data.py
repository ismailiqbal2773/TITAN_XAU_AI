#!/usr/bin/env python3
"""
TITAN XAU AI — Real Data Audit Script
=======================================

Single source of truth for data inventory. NO duplicates.
Reads all parquet files from titan/data/sources/dukascopy/daily/ and produces:
  - Total bars / days / months / years
  - Coverage % vs expected weekdays (2020-03-01 → 2024-12-31)
  - Missing days list (top 20)
  - Duplicate timestamps check
  - Price range / spread stats
  - Regime coverage (COVID 2020, Ukraine 2022, SVB 2023, Fed tightening, etc.)
  - Schema validation (every file must have timestamp index + 6 float cols)
  - Output: JSON + console summary

Usage:
    python scripts/real_data/audit_data.py
    python scripts/real_data/audit_data.py --json /path/to/output.json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

PROJECT_ROOT = Path("/home/z/my-project")
DATA_DIR = PROJECT_ROOT / "titan" / "data" / "sources" / "dukascopy" / "daily"

# Target coverage window: 2020-03-01 → 2024-12-31 (project's stated range)
EXPECTED_START = date(2020, 3, 1)
EXPECTED_END = date(2024, 12, 31)

# Regime events to verify
REGIMES = [
    ("COVID-2020",          date(2020, 3, 1),   date(2020, 4, 30)),
    ("Ukraine-War-2022",    date(2022, 2, 24),  date(2022, 3, 31)),
    ("Fed-Tightening-H1",   date(2022, 6, 1),   date(2022, 12, 31)),
    ("SVB-Banking-2023",    date(2023, 3, 8),   date(2023, 3, 31)),
    ("Inflation-Spike",     date(2022, 6, 1),   date(2023, 3, 31)),
    ("Gold-Trend-2024",     date(2024, 1, 1),   date(2024, 12, 31)),
    ("Range-2023-H2",       date(2023, 7, 1),   date(2023, 12, 31)),
    ("Range-2023-H1",       date(2023, 1, 1),   date(2023, 6, 30)),
]


def expected_weekdays(start: date, end: date) -> set[str]:
    out = set()
    cur = start
    while cur <= end:
        if cur.weekday() < 5:
            out.add(cur.isoformat())
        cur += timedelta(days=1)
    return out


def audit_data() -> dict:
    """Run full audit and return results dict."""
    print(f"Scanning: {DATA_DIR}")
    files = sorted(DATA_DIR.glob("XAUUSD_M1_*.parquet"))
    print(f"Found {len(files)} daily parquet files")

    # Index file by date string
    file_by_date: dict[str, Path] = {}
    for f in files:
        # Filename: XAUUSD_M1_YYYY-MM-DD.parquet
        d = f.stem.split("_")[-1]
        file_by_date[d] = f

    # Expected vs actual
    expected = expected_weekdays(EXPECTED_START, EXPECTED_END)
    present = set(file_by_date.keys())
    missing = sorted(expected - present)
    extra = sorted(present - expected)  # files outside expected range

    # Read every file and aggregate stats
    total_bars = 0
    total_volume = 0
    dup_ts_count = 0
    schema_mismatches = []
    price_min = float("inf")
    price_max = float("-inf")
    spread_sum = 0.0
    spread_count = 0
    per_year_stats: dict[str, dict] = {}

    print(f"Reading {len(files)} files...")
    for i, f in enumerate(files, 1):
        try:
            df = pd.read_parquet(f)
        except Exception as e:
            schema_mismatches.append({"file": f.name, "error": str(e)})
            continue

        # Schema check
        expected_cols = {"open", "high", "low", "close", "volume", "spread"}
        if set(df.columns) != expected_cols:
            schema_mismatches.append({
                "file": f.name,
                "error": f"columns={list(df.columns)} (expected {sorted(expected_cols)})"
            })
            continue
        if df.index.name != "timestamp" or "UTC" not in str(df.index.dtype):
            schema_mismatches.append({
                "file": f.name,
                "error": f"index={df.index.name}/{df.index.dtype} (expected timestamp/datetime64[ns, UTC])"
            })
            continue

        # Dup check
        if df.index.duplicated().any():
            dup_ts_count += int(df.index.duplicated().sum())

        n = len(df)
        total_bars += n
        total_volume += int(df["volume"].sum()) if "volume" in df.columns else 0
        price_min = min(price_min, float(df["low"].min()))
        price_max = max(price_max, float(df["high"].max()))
        spread_sum += float(df["spread"].sum())
        spread_count += n

        # Per-year aggregation — robust parse: extract YYYY from filename
        # Filename format: XAUUSD_M1_YYYY-MM-DD.parquet
        parts = f.stem.split("_")
        date_str = parts[-1]  # YYYY-MM-DD
        year = date_str[:4] if len(date_str) >= 4 else "unknown"
        if year not in per_year_stats:
            per_year_stats[year] = {"files": 0, "bars": 0, "min": float("inf"), "max": float("-inf")}
        per_year_stats[year]["files"] += 1
        per_year_stats[year]["bars"] += n
        per_year_stats[year]["min"] = min(per_year_stats[year]["min"], float(df["low"].min()))
        per_year_stats[year]["max"] = max(per_year_stats[year]["max"], float(df["high"].max()))

        if i % 100 == 0:
            print(f"  ... {i}/{len(files)} files processed, {total_bars:,} bars so far")

    # Coverage percentage
    coverage_pct = (len(present) / len(expected) * 100.0) if expected else 0.0

    # Regime coverage
    regime_results = []
    for name, r_start, r_end in REGIMES:
        r_expected = expected_weekdays(r_start, r_end)
        r_present = {d for d in r_expected if d in file_by_date}
        r_pct = (len(r_present) / len(r_expected) * 100.0) if r_expected else 0.0
        regime_results.append({
            "name": name,
            "start": r_start.isoformat(),
            "end": r_end.isoformat(),
            "expected_days": len(r_expected),
            "present_days": len(r_present),
            "coverage_pct": round(r_pct, 2),
        })

    return {
        "audit_timestamp": datetime.utcnow().isoformat() + "Z",
        "data_dir": str(DATA_DIR),
        "total_files": len(files),
        "total_bars": total_bars,
        "total_volume": total_volume,
        "coverage_pct": round(coverage_pct, 2),
        "expected_weekdays": len(expected),
        "present_weekdays": len(present),
        "missing_weekdays_count": len(missing),
        "missing_weekdays_top20": missing[:20],
        "extra_files_outside_range": extra,
        "duplicate_timestamps_total": dup_ts_count,
        "schema_mismatches": schema_mismatches,
        "price_range": {
            "min": round(price_min, 4) if price_min != float("inf") else None,
            "max": round(price_max, 4) if price_max != float("-inf") else None,
        },
        "spread_stats": {
            "mean": round(spread_sum / spread_count, 6) if spread_count > 0 else None,
            "samples": spread_count,
        },
        "per_year": per_year_stats,
        "regime_coverage": regime_results,
        "expected_window": {
            "start": EXPECTED_START.isoformat(),
            "end": EXPECTED_END.isoformat(),
        },
    }


def print_summary(r: dict):
    print()
    print("=" * 70)
    print("  TITAN XAU AI — REAL DATA AUDIT SUMMARY")
    print("=" * 70)
    print(f"  Audit time:       {r['audit_timestamp']}")
    print(f"  Data dir:         {r['data_dir']}")
    print(f"  Total files:      {r['total_files']}")
    print(f"  Total M1 bars:    {r['total_bars']:,}")
    print(f"  Total volume:     {r['total_volume']:,}")
    print()
    print(f"  Expected window:  {r['expected_window']['start']} → {r['expected_window']['end']}")
    print(f"  Expected weekdays:{r['expected_weekdays']}")
    print(f"  Present weekdays: {r['present_weekdays']}")
    print(f"  Coverage:         {r['coverage_pct']}%")
    print(f"  Missing weekdays: {r['missing_weekdays_count']}")
    print()
    print(f"  Price range:      ${r['price_range']['min']} → ${r['price_range']['max']}")
    print(f"  Spread mean:      ${r['spread_stats']['mean']}  ({r['spread_stats']['samples']:,} samples)")
    print()
    print(f"  Duplicate ts:     {r['duplicate_timestamps_total']}")
    print(f"  Schema mismatches:{len(r['schema_mismatches'])}")
    if r["schema_mismatches"]:
        for m in r["schema_mismatches"][:5]:
            print(f"    - {m['file']}: {m['error']}")

    print()
    print("  Per-year breakdown:")
    for year in sorted(r["per_year"].keys()):
        s = r["per_year"][year]
        print(f"    {year}: {s['files']:3d} files, {s['bars']:>8,} bars, "
              f"${s['min']:.2f} → ${s['max']:.2f}")

    print()
    print("  Regime coverage:")
    for rg in r["regime_coverage"]:
        status = "✓" if rg["coverage_pct"] >= 95 else ("~" if rg["coverage_pct"] >= 50 else "✗")
        print(f"    {status} {rg['name']:<25} {rg['present_days']:3d}/{rg['expected_days']:3d} "
              f"({rg['coverage_pct']:5.2f}%)  [{rg['start']} → {rg['end']}]")

    if r["missing_weekdays_top20"]:
        print()
        print(f"  Top 20 missing weekdays (out of {r['missing_weekdays_count']} total):")
        for d in r["missing_weekdays_top20"]:
            print(f"    - {d}")

    print()
    print("=" * 70)
    # Pass/Fail
    passed = (
        r["coverage_pct"] >= 95.0 and
        r["duplicate_timestamps_total"] == 0 and
        len(r["schema_mismatches"]) == 0
    )
    verdict = "PASS (READY FOR TRAINING)" if passed else "FAIL (NEEDS MORE DATA)"
    print(f"  VERDICT: {verdict}")
    print("=" * 70)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", type=str, default=None,
                        help="Write JSON output to this path")
    parser.add_argument("--quiet", action="store_true",
                        help="Suppress console summary")
    args = parser.parse_args()

    result = audit_data()
    if not args.quiet:
        print_summary(result)
    if args.json:
        out_path = Path(args.json)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as f:
            json.dump(result, f, indent=2, default=str)
        print(f"\nJSON written: {out_path}")
