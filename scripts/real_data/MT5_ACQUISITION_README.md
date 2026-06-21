# TITAN XAU AI — Windows MT5 Acquisition Package

## What this package does
Acquires REAL XAUUSD history directly from Exness MT5 terminal on Windows.
NO synthetic data. NO Dukascopy derivation. RAW broker history only.

## Files in this package
- `titan_mt5_acquire.py` — Python script (run on Windows)
- `RUN_ON_WINDOWS.bat` — One-click launcher
- `README.md` — This file

## Output files produced (in `titan_mt5_data/` folder)
```
titan_mt5_data/
├── XAUUSD_M1.parquet        ← Raw M1 bars
├── XAUUSD_M5.parquet        ← Raw M5 bars
├── XAUUSD_M15.parquet       ← Raw M15 bars
├── XAUUSD_M30.parquet       ← Raw M30 bars
├── XAUUSD_H1.parquet        ← Raw H1 bars
├── MT5_Verification.json    ← Connection proof (login, server, etc.)
└── MT5_Audit_Report.json    ← Full audit + verdict
```

## Prerequisites (one-time setup)

### 1. Install Python 3.10+
Download from: https://www.python.org/downloads/
During install, check "Add Python to PATH".

### 2. Install required Python packages
Open **Command Prompt** (Win+R → `cmd` → Enter) and run:
```cmd
pip install MetaTrader5 pandas pyarrow
```

### 3. Make sure MetaTrader 5 terminal is ready
- Open MetaTrader 5 terminal
- Login to Exness REAL account
- Confirm XAUUSD symbol is visible in Market Watch
  (View → Market Watch, or press Ctrl+M)

## Acquisition procedure

### Method 1: One-click (recommended)
1. Download all 3 files to a folder, e.g., `C:\titan\`
2. Double-click `RUN_ON_WINDOWS.bat`
3. Wait 15-30 minutes for full download
4. Output appears in `C:\titan\titan_mt5_data\`

### Method 2: Manual
1. Open Command Prompt
2. Navigate to script folder:
   ```cmd
   cd C:\titan
   ```
3. Run script:
   ```cmd
   python titan_mt5_acquire.py
   ```
4. Wait for completion (15-30 minutes)
5. Output appears in `titan_mt5_data\` subfolder

## What the script does (in order)

### Step 1: MT5 Connection Verification (8 checks)
1. `mt5.initialize()` returns True
2. `mt5.account_info()` returns login/server/currency/leverage/balance
3. `mt5.terminal_info()` returns terminal name/path/connected status
4. `mt5.symbol_select("XAUUSD", True)` succeeds
5. `mt5.symbol_info("XAUUSD")` returns digits/point/spread/contract_size
6. Broker server name captured
7. Account type detected (real/demo)
8. Available history depth probed

Saves → `MT5_Verification.json`

### Step 2: Real MT5 Data Download (5 timeframes)
For each timeframe (M1, M5, M15, M30, H1):
- Calls `mt5.copy_rates_range()` in quarterly chunks (90 days each)
- Builds DataFrame with raw MT5 columns: time, open, high, low, close, tick_volume, spread, real_volume
- Deduplicates by timestamp (keeps last)
- Sorts by timestamp
- Saves as single parquet file: `XAUUSD_<TF>.parquet`
- Computes SHA-256 hash

### Step 3: Data Quality Audit
For each timeframe:
- Total bars
- First/last timestamp
- Coverage % (vs expected Mon-Fri trading days 2020-today)
- Missing days count + sample list
- Duplicate rows count
- Weekend rows count
- Spread statistics (min/max/mean/median/std)
- Historical events verification:
  - COVID 2020 (Mar-Apr 2020)
  - Ukraine War 2022 (Feb-Mar 2022)
  - SVB Banking Crisis 2023 (Mar 2023)
  - Gold Rally 2024 (Mar-Dec 2024)

### Step 4: Final Verdict
Pass conditions (based on M1 primary):
- Coverage >= 95%
- Real MT5 Data >= 95% (always true — direct MT5 download)
- Synthetic Data = 0% (always true — no synthetic created)

Output: `REAL_MT5_DATA_VERIFIED` or `DATA_REJECTED`

Saves → `MT5_Audit_Report.json`

## Evidence collection procedure

After script completes:

### Step A: Verify output files exist
```cmd
cd C:\titan\titan_mt5_data
dir
```
You should see 7 files:
```
XAUUSD_M1.parquet
XAUUSD_M5.parquet
XAUUSD_M15.parquet
XAUUSD_M30.parquet
XAUUSD_H1.parquet
MT5_Verification.json
MT5_Audit_Report.json
```

### Step B: Inspect audit report
```cmd
type MT5_Audit_Report.json
```
Look for the `"verdict"` field at the bottom — should say `REAL_MT5_DATA_VERIFIED`.

### Step C: Inspect verification
```cmd
type MT5_Verification.json
```
Confirm:
- `initialize`: true
- `account_info.login`: your Exness login number
- `account_info.server`: contains "Exness"
- `account_info.company`: "Exness" or similar
- `symbol_info.name`: "XAUUSD"

### Step D: ZIP the entire folder
Right-click `titan_mt5_data` folder → Send to → Compressed (zipped) folder
→ produces `titan_mt5_data.zip`

### Step E: Share the ZIP back
Upload `titan_mt5_data.zip` to the AI agent for final analysis.

## Troubleshooting

### Error: "No matching distribution found for MetaTrader5"
Cause: You're trying to install on Linux/macOS.
Fix: MetaTrader5 only runs on Windows. Use a Windows machine.

### Error: "mt5.initialize() FAILED"
Cause: MT5 terminal not running, or Exness account not logged in.
Fix:
1. Open MetaTrader 5 terminal
2. Login to Exness (File → Login to Trade Account)
3. Wait for connection (bottom-right corner shows connection status)
4. Re-run the script

### Error: "symbol_select FAILED"
Cause: XAUUSD symbol not in Market Watch.
Fix:
1. In MT5 terminal, press Ctrl+M (Market Watch)
2. Right-click → Show All
3. Find XAUUSD, make sure it's visible
4. Re-run the script

### Warning: "No M1 history available for full 2020-2024 range"
Cause: Exness limits M1 history depth (typically 2 years).
Fix:
- Accept reduced coverage (script will still run, just with lower coverage %)
- OR contact Exness support to enable extended history
- OR run on a different broker with deeper M1 history

### Script runs but bars = 0
Cause: No history available for this symbol/account.
Fix:
1. In MT5 terminal, open XAUUSD chart (File → New Chart → XAUUSD)
2. Wait a few minutes for history to load
3. Try pressing Ctrl+End in the chart to force history download
4. Re-run the script

## Notes

- **RAW data only**: No transformations, no broker derivations, no synthetic generation.
- **Direct MT5 API**: Uses official `mt5.copy_rates_range()` — same as any professional MT5 EA.
- **Deterministic**: Same script + same account = same output every time.
- **Reproducible**: SHA-256 hashes in audit report allow third-party verification.
- **Time required**: 15-30 minutes for full 5-year × 5-timeframe download.

## Contact
After running script, share `titan_mt5_data.zip` with AI agent for final analysis.
