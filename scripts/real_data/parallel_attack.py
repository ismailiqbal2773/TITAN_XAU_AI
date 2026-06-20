#!/usr/bin/env python3
"""
TITAN Aggressive Parallel Downloader
=====================================
Downloads many days IN PARALLEL using threads. Designed to maximize
throughput within a single bash tool call (~5 min window).

Strategy:
  - Read missing_dates.txt
  - Skip days already downloaded
  - Download up to N days in parallel (default 16)
  - Each day = independent thread (24 hours fetched in parallel within)
  - Print progress every 30s
  - Save state on completion

Usage:
    timeout 280 python scripts/real_data/parallel_attack.py [max_days]
"""
import sys, time, json, concurrent.futures as cf
from datetime import datetime
from pathlib import Path
import pandas as pd

PROJECT = Path("/home/z/my-project")
DAILY = PROJECT / "titan" / "data" / "sources" / "dukascopy" / "daily"
MISSING_FILE = PROJECT / "scripts" / "real_data" / "missing_dates.txt"
STATE_FILE = PROJECT / "scripts" / "real_data" / "attack_state.json"

sys.path.insert(0, str(PROJECT))
from scripts.real_data.fast_download import download_day_fast, _is_complete


def download_one_day(ymd: str) -> dict:
    """Download a single day. Returns status dict."""
    y, m, d = int(ymd[:4]), int(ymd[5:7]), int(ymd[8:10])
    path = DAILY / f"XAUUSD_M1_{ymd}.parquet"
    if _is_complete(path):
        return {"date": ymd, "status": "cached", "bars": 0}
    try:
        df = download_day_fast(y, m, d)
        if df is None or df.empty:
            return {"date": ymd, "status": "empty", "bars": 0}
        df.to_parquet(path)
        return {"date": ymd, "status": "ok", "bars": len(df)}
    except Exception as e:
        return {"date": ymd, "status": "error", "bars": 0, "err": str(e)[:100]}


def main():
    max_days = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    parallel = int(sys.argv[2]) if len(sys.argv) > 2 else 12

    # Load missing
    if not MISSING_FILE.exists():
        print("[attack] missing_dates.txt not found. Regenerating...")
        # Quick regen
        from datetime import date, timedelta
        present = set()
        for f in DAILY.glob("XAUUSD_M1_*.parquet"):
            try:
                df = pd.read_parquet(f, columns=["open"])
                if len(df) > 0:
                    present.add(f.stem.split("_")[-1])
            except Exception:
                pass
        missing = []
        d = date(2020, 1, 1)
        while d <= date(2024, 12, 31):
            if d.weekday() < 5 and d.isoformat() not in present:
                missing.append(d.isoformat())
            d += timedelta(days=1)
        with open(MISSING_FILE, "w") as f:
            f.write("\n".join(missing))
        print(f"[attack] Regenerated: {len(missing)} missing")

    with open(MISSING_FILE) as f:
        all_missing = [l.strip() for l in f if l.strip()]

    # Filter out days that got downloaded since last run
    todo = [d for d in all_missing if not _is_complete(DAILY / f"XAUUSD_M1_{d}.parquet")]
    todo = todo[:max_days]
    print(f"[attack] {len(all_missing)} total missing, {len(todo)} to download "
          f"this round, parallel={parallel}", flush=True)
    print(f"[attack] Range: {todo[0]} → {todo[-1]}", flush=True)

    t0 = time.time()
    results = {"ok": 0, "cached": 0, "empty": 0, "error": 0, "bars": 0}
    completed = 0
    errors = []

    with cf.ThreadPoolExecutor(max_workers=parallel) as pool:
        futures = {pool.submit(download_one_day, ymd): ymd for ymd in todo}
        for fut in cf.as_completed(futures):
            ymd = futures[fut]
            try:
                r = fut.result()
                results[r["status"]] = results.get(r["status"], 0) + 1
                results["bars"] += r["bars"]
                completed += 1
                if r["status"] == "error":
                    errors.append(r)
                if completed % 5 == 0 or completed == len(todo):
                    el = time.time() - t0
                    print(f"[attack] [{completed}/{len(todo)}] "
                          f"ok={results['ok']} empty={results['empty']} "
                          f"err={results['error']} bars={results['bars']:,} "
                          f"({el:.0f}s, {completed/el*60:.1f} days/min)",
                          flush=True)
            except Exception as e:
                results["error"] += 1
                errors.append({"date": ymd, "err": str(e)[:100]})

    elapsed = time.time() - t0
    print(f"\n[attack] DONE in {elapsed:.0f}s ({elapsed/60:.1f} min)", flush=True)
    print(f"[attack] ok={results['ok']} cached={results['cached']} "
          f"empty={results['empty']} error={results['error']} "
          f"bars={results['bars']:,}", flush=True)
    if errors:
        print(f"[attack] Errors ({len(errors)}):")
        for e in errors[:10]:
            print(f"  - {e['date']}: {e.get('err','?')}")

    # Save state
    state = {
        "timestamp": datetime.now().isoformat(),
        "elapsed_s": round(elapsed, 1),
        "results": results,
        "errors": errors[:50],
        "range_done": f"{todo[0]} → {todo[-1]}" if todo else "n/a",
    }
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, default=str)
    print(f"[attack] State saved: {STATE_FILE}", flush=True)


if __name__ == "__main__":
    main()
