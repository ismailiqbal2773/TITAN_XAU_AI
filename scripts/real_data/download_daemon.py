#!/usr/bin/env python3
"""
TITAN Real Data Background Downloader (Daemon)
================================================
Runs the canonical fast_download.py in sequential 2-week batches,
logging progress + appending to worklog. Designed to be launched in
background and continue running across many bash timeouts.

Usage:
    nohup python scripts/real_data/download_daemon.py > scripts/real_data/_archive/daemon.out 2>&1 &

The daemon:
  - Reads missing-date inventory
  - Picks next 2-week batch (10 trading days)
  - Runs fast_download on that batch
  - Records progress to download_progress.json
  - Repeats until no missing dates remain
  - Stops if a 'STOP' file appears
"""
import json
import subprocess
import sys
import time
from datetime import date, timedelta
from pathlib import Path

PROJECT = Path("/home/z/my-project")
DAILY = PROJECT / "titan" / "data" / "sources" / "dukascopy" / "daily"
PROGRESS_FILE = PROJECT / "scripts" / "real_data" / "download_progress.json"
STOP_FILE = PROJECT / "scripts" / "real_data" / "STOP"
PYTHON = "/home/z/.venv/bin/python"
DOWNLOADER = PROJECT / "scripts" / "real_data" / "fast_download.py"


def load_present_dates() -> set:
    """Return set of YYYY-MM-DD strings for non-empty parquet files."""
    present = set()
    for f in DAILY.glob("XAUUSD_M1_*.parquet"):
        try:
            import pandas as pd
            df = pd.read_parquet(f, columns=["open"])
            if len(df) > 0:
                present.add(f.stem.split("_")[-1])
        except Exception:
            pass
    return present


def list_missing(start: date, end: date, present: set) -> list:
    missing = []
    d = start
    while d <= end:
        if d.weekday() < 5 and d.isoformat() not in present:
            missing.append(d)
        d += timedelta(days=1)
    return missing


def run_batch(start_iso: str, end_iso: str) -> dict:
    cmd = [PYTHON, str(DOWNLOADER), start_iso, end_iso, "--no-merge"]
    print(f"[daemon] $ {' '.join(cmd)}", flush=True)
    t0 = time.time()
    try:
        proc = subprocess.run(cmd, cwd=str(PROJECT), capture_output=True,
                              text=True, timeout=600)
        elapsed = time.time() - t0
        # Parse last JSON line of stdout
        last_line = ""
        for line in reversed(proc.stdout.strip().split("\n")):
            if line.strip().startswith("{"):
                last_line = line.strip()
                break
        try:
            result = json.loads(last_line) if last_line else {}
        except Exception:
            result = {}
        result["elapsed"] = round(elapsed, 1)
        result["stdout_tail"] = proc.stdout[-500:]
        result["stderr_tail"] = proc.stderr[-500:]
        return result
    except subprocess.TimeoutExpired:
        return {"error": "timeout", "elapsed": 600}


def main():
    print(f"[daemon] Start at {time.strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
    START = date(2020, 1, 1)
    END = date(2024, 12, 31)

    iteration = 0
    while True:
        if STOP_FILE.exists():
            print("[daemon] STOP file detected. Exiting.", flush=True)
            break

        present = load_present_dates()
        missing = list_missing(START, END, present)
        print(f"[daemon] {len(present)} days present, {len(missing)} missing",
              flush=True)
        if not missing:
            print("[daemon] All trading days covered. Done.", flush=True)
            # Trigger final monthly merge
            subprocess.run([PYTHON, str(DOWNLOADER), "2024-12-30", "2024-12-31"],
                           cwd=str(PROJECT), capture_output=True, text=True,
                           timeout=120)
            break

        # Take next 14 days of missing
        batch = missing[:14]
        batch_start = batch[0]
        batch_end = batch[-1]
        print(f"[daemon] Batch {iteration+1}: {batch_start} → {batch_end} "
              f"({len(batch)} days)", flush=True)

        result = run_batch(batch_start.isoformat(), batch_end.isoformat())
        # Save progress
        progress = {
            "iteration": iteration + 1,
            "batch_start": batch_start.isoformat(),
            "batch_end": batch_end.isoformat(),
            "batch_size": len(batch),
            "result": result,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        with open(PROGRESS_FILE, "w") as f:
            json.dump(progress, f, indent=2, default=str)
        print(f"[daemon] Batch {iteration+1} done: "
              f"ok={result.get('days_ok', '?')} "
              f"empty={result.get('days_empty', '?')} "
              f"bars={result.get('total_bars', '?')} "
              f"({result.get('elapsed', '?')}s)", flush=True)

        iteration += 1
        # brief pause between batches
        time.sleep(2)

    print(f"[daemon] Finished at {time.strftime('%Y-%m-%d %H:%M:%S')}",
          flush=True)


if __name__ == "__main__":
    main()
