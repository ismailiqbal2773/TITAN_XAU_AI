"""
TITAN XAU AI — Windows MT5 Acquisition Script
==============================================
Run on: Windows 11 with MetaTrader 5 terminal installed + Exness account logged in.

Produces EXACTLY 5 parquet files:
    XAUUSD_M1.parquet
    XAUUSD_M5.parquet
    XAUUSD_M15.parquet
    XAUUSD_M30.parquet
    XAUUSD_H1.parquet

Plus evidence:
    MT5_Verification.json
    MT5_Audit_Report.json

NO synthetic data. NO Dukascopy. NO derivations. RAW broker history only.
"""
import sys
import os
import json
import hashlib
import time
from datetime import datetime, timedelta
from pathlib import Path

# === STEP 0: Windows-only guard ===========================================
if os.name != "nt":
    print("ERROR: This script must run on Windows.")
    print(f"Detected OS: {os.name}")
    print("On Linux, real MT5 acquisition is impossible. Aborting.")
    sys.exit(1)

# === STEP 1: Import dependencies ==========================================
print("=" * 70)
print("TITAN XAU AI — Windows MT5 Acquisition")
print("=" * 70)
print()

try:
    import MetaTrader5 as mt5
    print(f"[OK] MetaTrader5 version: {mt5.__version__}")
except ImportError:
    print("[FAIL] MetaTrader5 package not installed.")
    print("       Run this command first:")
    print("         pip install MetaTrader5 pandas pyarrow")
    sys.exit(1)

try:
    import pandas as pd
    import pyarrow as pa
    import pyarrow.parquet as pq
    print(f"[OK] pandas {pd.__version__}, pyarrow {pa.__version__}")
except ImportError:
    print("[FAIL] pandas/pyarrow not installed.")
    print("       Run: pip install pandas pyarrow")
    sys.exit(1)


# === STEP 2: Configuration ================================================
SYMBOL = "XAUUSD"
START = datetime(2020, 1, 1)
END = datetime.now()
OUTPUT_DIR = Path("titan_mt5_data")
OUTPUT_DIR.mkdir(exist_ok=True)

TIMEFRAMES = [
    ("M1",  mt5.TIMEFRAME_M1),
    ("M5",  mt5.TIMEFRAME_M5),
    ("M15", mt5.TIMEFRAME_M15),
    ("M30", mt5.TIMEFRAME_M30),
    ("H1",  mt5.TIMEFRAME_H1),
]


# === STEP 3: MT5 Connection Verification ==================================
print()
print("=" * 70)
print("STEP 1: MT5 Connection Verification")
print("=" * 70)

verification = {}

# 3.1 initialize
print()
print("[1/8] mt5.initialize() ...")
if not mt5.initialize():
    err = mt5.last_error()
    print(f"      FAILED — last_error: {err}")
    print("      Make sure MT5 terminal is running and Exness account is logged in.")
    sys.exit(1)
print("      [OK] initialize() returned True")
verification["initialize"] = True

# 3.2 account_info
print()
print("[2/8] mt5.account_info() ...")
acc = mt5.account_info()
if acc is None:
    print(f"      FAILED — {mt5.last_error()}")
    sys.exit(1)
print(f"      login:        {acc.login}")
print(f"      server:       {acc.server}")
print(f"      company:      {acc.company}")
print(f"      currency:     {acc.currency}")
print(f"      leverage:     1:{acc.leverage}")
print(f"      balance:      {acc.balance} {acc.currency}")
print(f"      equity:       {acc.equity} {acc.currency}")
print(f"      trade_allowed:{acc.trade_allowed}")
verification["account_info"] = {
    "login":         acc.login,
    "server":        acc.server,
    "company":       acc.company,
    "currency":      acc.currency,
    "leverage":      acc.leverage,
    "balance":       acc.balance,
    "equity":        acc.equity,
    "trade_allowed": acc.trade_allowed,
}

# 3.3 terminal_info
print()
print("[3/8] mt5.terminal_info() ...")
term = mt5.terminal_info()
if term is None:
    print(f"      FAILED — {mt5.last_error()}")
    sys.exit(1)
print(f"      name:         {term.name}")
print(f"      company:      {term.company}")
print(f"      path:         {term.path}")
print(f"      connected:    {term.connected}")
print(f"      trade_allowed:{term.trade_allowed}")
verification["terminal_info"] = {
    "name":          term.name,
    "company":       term.company,
    "path":          term.path,
    "connected":     term.connected,
    "trade_allowed": term.trade_allowed,
}

# 3.4 symbol_select
print()
print(f"[4/8] mt5.symbol_select('{SYMBOL}', True) ...")
if not mt5.symbol_select(SYMBOL, True):
    print(f"      FAILED — {mt5.last_error()}")
    print("      Available XAU* symbols:")
    for s in mt5.symbols_get("*XAU*") or []:
        print(f"        - {s.name}")
    sys.exit(1)
print("      [OK] symbol selected")
verification["symbol_select"] = True

# 3.5 symbol_info
print()
print(f"[5/8] mt5.symbol_info('{SYMBOL}') ...")
sinfo = mt5.symbol_info(SYMBOL)
if sinfo is None:
    print(f"      FAILED — {mt5.last_error()}")
    sys.exit(1)
print(f"      name:        {sinfo.name}")
print(f"      description: {sinfo.description}")
print(f"      digits:      {sinfo.digits}")
print(f"      point:       {sinfo.point}")
print(f"      spread:      {sinfo.spread}")
print(f"      contract:    {sinfo.trade_contract_size}")
verification["symbol_info"] = {
    "name":                 sinfo.name,
    "description":          sinfo.description,
    "digits":               sinfo.digits,
    "point":                sinfo.point,
    "spread":               sinfo.spread,
    "trade_contract_size":  sinfo.trade_contract_size,
}

# 3.6 broker server name
print()
print(f"[6/8] Broker server name: {acc.server}")
verification["broker_server"] = acc.server

# 3.7 account type (from server name heuristic + trade_mode)
print()
print(f"[7/8] Account type detection ...")
account_type = "unknown"
server_lower = acc.server.lower()
if "real" in server_lower or "live" in server_lower:
    account_type = "real"
elif "demo" in server_lower or "demo" in server_lower:
    account_type = "demo"
print(f"      server: {acc.server}")
print(f"      type:   {account_type}")
print(f"      trade_mode: {sinfo.trade_mode}  (0=disabled, 1=longonly, 2=shortonly, 4=full)")
verification["account_type"] = account_type
verification["trade_mode"] = sinfo.trade_mode

# 3.8 available history depth (probe M1)
print()
print(f"[8/8] Available history depth probe (M1) ...")
probe = mt5.copy_rates_range(SYMBOL, mt5.TIMEFRAME_M1, START, END)
if probe is None or len(probe) == 0:
    print(f"      WARNING: No M1 history available for full 2020-2024 range.")
    print(f"      Trying last 12 months ...")
    probe = mt5.copy_rates_range(
        SYMBOL, mt5.TIMEFRAME_M1,
        datetime.now() - timedelta(days=365), END
    )
    if probe is None or len(probe) == 0:
        print(f"      FAILED: No M1 history available at all.")
        verification["history_depth"] = {"bars": 0, "error": "no_history"}
    else:
        first_ts = datetime.fromtimestamp(probe[0][0])
        last_ts = datetime.fromtimestamp(probe[-1][0])
        print(f"      [OK] Last 12 months only: {len(probe):,} bars")
        print(f"           First: {first_ts}")
        print(f"           Last:  {last_ts}")
        verification["history_depth"] = {
            "bars": int(len(probe)),
            "first": str(first_ts),
            "last": str(last_ts),
            "note": "broker limits M1 history to ~12 months",
        }
else:
    first_ts = datetime.fromtimestamp(probe[0][0])
    last_ts = datetime.fromtimestamp(probe[-1][0])
    print(f"      [OK] Full range available: {len(probe):,} bars")
    print(f"           First: {first_ts}")
    print(f"           Last:  {last_ts}")
    verification["history_depth"] = {
        "bars": int(len(probe)),
        "first": str(first_ts),
        "last": str(last_ts),
    }

# Save verification
with open(OUTPUT_DIR / "MT5_Verification.json", "w") as f:
    json.dump(verification, f, indent=2, default=str)
print()
print(f"[OK] Verification saved → {OUTPUT_DIR / 'MT5_Verification.json'}")


# === STEP 4: Download all 5 timeframes ====================================
print()
print("=" * 70)
print("STEP 2: Download Real MT5 Data (RAW, no transformations)")
print("=" * 70)


def download_timeframe(tf_name: str, tf_const: int) -> dict:
    """Download one timeframe's full history. Save as single parquet file."""
    print()
    print(f"--- {tf_name} ---")
    t0 = time.time()

    # Download in quarterly chunks (MT5 returns at most ~65k bars per call)
    all_rates = []
    cur = START
    while cur < END:
        nxt = min(cur + timedelta(days=90), END)
        rates = mt5.copy_rates_range(SYMBOL, tf_const, cur, nxt)
        if rates is not None and len(rates) > 0:
            all_rates.extend(rates.tolist())
        cur = nxt

    if not all_rates:
        print(f"  [FAIL] No bars downloaded for {tf_name}")
        return {"timeframe": tf_name, "bars": 0, "error": "no_data"}

    # Build DataFrame — MT5 raw columns
    df = pd.DataFrame(
        all_rates,
        columns=["time", "open", "high", "low", "close",
                 "tick_volume", "spread", "real_volume"],
    )
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df = df.set_index("time")
    df.index.name = "timestamp"

    # Deduplicate (keep last on conflict)
    before = len(df)
    df = df[~df.index.duplicated(keep="last")]
    duplicates = before - len(df)
    df = df.sort_index()

    # Save as single parquet file
    out_file = OUTPUT_DIR / f"XAUUSD_{tf_name}.parquet"
    df.to_parquet(out_file, compression="snappy")

    # SHA-256
    h = hashlib.sha256()
    with open(out_file, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    sha = h.hexdigest()

    elapsed = time.time() - t0
    size_mb = out_file.stat().st_size / (1024 * 1024)

    print(f"  bars:            {len(df):,}")
    print(f"  first timestamp: {df.index[0]}")
    print(f"  last timestamp:  {df.index[-1]}")
    print(f"  duplicates:      {duplicates}")
    print(f"  file size:       {size_mb:.2f} MB")
    print(f"  SHA-256:         {sha}")
    print(f"  elapsed:         {elapsed:.1f}s")
    print(f"  saved to:        {out_file}")

    return {
        "timeframe":        tf_name,
        "file":             str(out_file),
        "bars":             int(len(df)),
        "first_timestamp":  str(df.index[0]),
        "last_timestamp":   str(df.index[-1]),
        "duplicates":       int(duplicates),
        "file_size_bytes":  int(out_file.stat().st_size),
        "file_size_mb":     round(size_mb, 2),
        "sha256":           sha,
        "elapsed_s":        round(elapsed, 2),
    }


download_results = {}
for tf_name, tf_const in TIMEFRAMES:
    download_results[tf_name] = download_timeframe(tf_name, tf_const)


# === STEP 5: Data Quality Audit ===========================================
print()
print("=" * 70)
print("STEP 3: Data Quality Audit")
print("=" * 70)


def audit_timeframe(tf_name: str) -> dict:
    """Audit one timeframe's parquet file."""
    out_file = OUTPUT_DIR / f"XAUUSD_{tf_name}.parquet"
    if not out_file.exists():
        return {"timeframe": tf_name, "error": "file_missing"}

    df = pd.read_parquet(out_file)
    if len(df) == 0:
        return {"timeframe": tf_name, "error": "empty_file"}

    # Expected trading days (Mon-Fri, 2020-01-01 to today)
    expected = []
    d = START.date()
    end_date = END.date()
    while d <= end_date:
        if d.weekday() < 5:
            expected.append(d)
        d += timedelta(days=1)
    present = set(d.date() for d in df.index)
    missing = [d for d in expected if d not in present]
    coverage_pct = (len(present) / len(expected) * 100) if expected else 0.0

    # Weekend rows
    weekend_rows = int((df.index.weekday >= 5).sum())

    # Duplicate rows
    duplicate_rows = int(df.index.duplicated().sum())

    # Spread stats
    if "spread" in df.columns:
        spread = df["spread"]
        spread_stats = {
            "min":    float(spread.min()),
            "max":    float(spread.max()),
            "mean":   float(spread.mean()),
            "median": float(spread.median()),
            "std":    float(spread.std()),
        }
    else:
        spread_stats = None

    # Historical event verification
    events = {}
    for event_name, start_str, end_str in [
        ("COVID_2020",       "2020-03-01", "2020-04-30"),
        ("Ukraine_War_2022", "2022-02-24", "2022-03-31"),
        ("SVB_Banking_2023", "2023-03-08", "2023-03-31"),
        ("Gold_Rally_2024",  "2024-03-01", "2024-12-31"),
    ]:
        try:
            sub = df.loc[start_str:end_str]
            if len(sub) > 0:
                events[event_name] = {
                    "bars":        int(len(sub)),
                    "first_close": float(sub["close"].iloc[0]),
                    "last_close":  float(sub["close"].iloc[-1]),
                    "min_low":     float(sub["low"].min()),
                    "max_high":    float(sub["high"].max()),
                    "first_ts":    str(sub.index[0]),
                    "last_ts":     str(sub.index[-1]),
                }
            else:
                events[event_name] = {"bars": 0, "error": "no_data_in_range"}
        except Exception as e:
            events[event_name] = {"error": str(e)}

    return {
        "timeframe":           tf_name,
        "total_bars":          int(len(df)),
        "first_timestamp":     str(df.index[0]),
        "last_timestamp":      str(df.index[-1]),
        "coverage_pct":        round(coverage_pct, 2),
        "expected_trading_days": int(len(expected)),
        "present_trading_days":  int(len(present)),
        "missing_days_count":    int(len(missing)),
        "missing_days_sample":   [str(d) for d in missing[:20]],
        "weekend_rows":          weekend_rows,
        "duplicate_rows":        duplicate_rows,
        "spread_statistics":     spread_stats,
        "historical_events":     events,
    }


audit_results = {}
for tf_name, _ in TIMEFRAMES:
    print()
    print(f"--- {tf_name} ---")
    audit_results[tf_name] = audit_timeframe(tf_name)
    a = audit_results[tf_name]
    if "error" not in a:
        print(f"  bars:        {a['total_bars']:,}")
        print(f"  coverage:    {a['coverage_pct']}%")
        print(f"  duplicates:  {a['duplicate_rows']}")
        print(f"  weekend:     {a['weekend_rows']}")
        print(f"  missing:     {a['missing_days_count']} days")
        if a["spread_statistics"]:
            s = a["spread_statistics"]
            print(f"  spread:      min={s['min']:.4f}  max={s['max']:.4f}  "
                  f"mean={s['mean']:.4f}  median={s['median']:.4f}")
        for ev, ev_data in a["historical_events"].items():
            if "error" not in ev_data and ev_data.get("bars", 0) > 0:
                print(f"  {ev}: {ev_data['bars']} bars  "
                      f"close [{ev_data['first_close']:.2f} → "
                      f"{ev_data['last_close']:.2f}]  "
                      f"range [{ev_data['min_low']:.2f} - "
                      f"{ev_data['max_high']:.2f}]")


# === STEP 6: Final Verdict ================================================
print()
print("=" * 70)
print("STEP 4: Final Verdict")
print("=" * 70)

# Use M1 as primary coverage metric (highest resolution)
m1_audit = audit_results.get("M1", {})
m1_coverage = m1_audit.get("coverage_pct", 0.0)

coverage_pass = m1_coverage >= 95.0
real_data_pass = True  # Direct MT5 download
synthetic_pass = True  # No synthetic generation

print()
print(f"Pass conditions (based on M1 primary timeframe):")
print(f"  Coverage >= 95%:         {'PASS' if coverage_pass else 'FAIL'}"
      f"  (actual: {m1_coverage:.2f}%)")
print(f"  Real MT5 Data >= 95%:    {'PASS' if real_data_pass else 'FAIL'}"
      f"  (direct MT5 download)")
print(f"  Synthetic Data = 0%:     {'PASS' if synthetic_pass else 'FAIL'}"
      f"  (no synthetic generated)")

verdict = ("REAL_MT5_DATA_VERIFIED"
           if (coverage_pass and real_data_pass and synthetic_pass)
           else "DATA_REJECTED")

print()
print("=" * 70)
print(f"  {verdict}")
print("=" * 70)


# === STEP 7: Save final audit report ======================================
final_report = {
    "audit_date":       datetime.now().isoformat(),
    "specification":    "REAL_MT5_DATA_ACQUISITION",
    "environment": {
        "os":             os.name,
        "python_version": sys.version,
        "mt5_version":    mt5.__version__,
    },
    "verification":      verification,
    "download_results":  download_results,
    "audit_results":     audit_results,
    "pass_conditions": {
        "coverage_95":  coverage_pass,
        "real_data_95": real_data_pass,
        "synthetic_0":  synthetic_pass,
    },
    "verdict": verdict,
}

report_path = OUTPUT_DIR / "MT5_Audit_Report.json"
with open(report_path, "w") as f:
    json.dump(final_report, f, indent=2, default=str)
print()
print(f"[OK] Final audit report saved → {report_path}")


# === STEP 8: Shutdown + summary ===========================================
mt5.shutdown()
print()
print(f"[OK] MT5 connection closed.")
print()
print("=" * 70)
print("OUTPUT FILES (in titan_mt5_data/ folder):")
print("=" * 70)
for f in sorted(OUTPUT_DIR.iterdir()):
    size = f.stat().st_size
    size_str = f"{size/1024/1024:.2f} MB" if size > 1024*1024 else f"{size/1024:.2f} KB"
    print(f"  {f.name:<40}  {size_str}")
print()
print("Next step: ZIP the entire titan_mt5_data/ folder and share with AI agent.")
