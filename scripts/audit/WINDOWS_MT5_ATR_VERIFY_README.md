# Windows MT5 ATR Verification — Operator Guide

**Purpose**: Verify the TITAN XAU AI production ATR SL/TP path end-to-end against **real MT5 H1 bars** on Windows, with `dry_run=true` (no real orders).

**Estimated time**: 10 minutes (5-minute runtime + setup)

---

## Prerequisites

1. **Windows 10/11** with Python 3.12+
2. **MetaTrader5 Python package** installed:
   ```cmd
   pip install MetaTrader5 pandas numpy xgboost pyarrow pyyaml
   ```
3. **MT5 terminal** running and logged into Exness (or any broker with XAUUSD H1 history)
4. **XAUUSD symbol** visible in MT5 Market Watch (right-click → Show All → find XAUUSD)
5. **Repo at latest commit**:
   ```cmd
   cd C:\path\to\TITAN_XAU_AI
   git pull origin main
   ```

---

## Run Procedure

### Step 1 — Verify config (do NOT modify)

Open `config\runtime.yaml` and confirm these flags are set:

```yaml
runtime:
  dry_run: true
  live_trading: false

features:
  source: mt5

risk:
  sl_mode: atr
  atr_sl_multiplier: 2.0
  atr_tp_multiplier: 4.0
```

> The verification script also hard-codes these values as a safety net. Even if `runtime.yaml` drifts, the script forces the correct values for the test run.

### Step 2 — Run the verification script

```cmd
cd C:\path\to\TITAN_XAU_AI
python scripts\audit\windows_mt5_atr_verify.py --minutes 5
```

For a longer run (recommended for thorough verification):

```cmd
python scripts\audit\windows_mt5_atr_verify.py --minutes 10
```

### Step 3 — Watch the output

The script will:

1. Print the **MT5 connectivity pre-check** (login, server, company, XAUUSD found).
2. Print the **hard-coded verification config** (dry_run, source, sl_mode, multipliers).
3. Print the **scaler_loaded** status (must be True with 55 features).
4. **Generate one signal from MT5 bars** — prints bars loaded + signal direction.
5. **Compute current_atr from real MT5 bars** — prints the value (should be 5-30 range for XAUUSD H1).
6. **Run AutonomousRuntime for N minutes** — heartbeats every 30s, inference every 60s.
7. **Shutdown gracefully**.
8. Print the **10-point evidence report**.
9. Print the **final verdict (A/B/C)**.
10. Save a JSON report to `data\audit\windows_mt5_atr_verify_report.json`.

### Step 4 — Interpret the verdict

| Verdict | Meaning | Action |
|---|---|---|
| **A** | Windows MT5 dry-run ATR production path VERIFIED | Proceed to Phase 2 (demo account challenge) |
| **B** | ATR fallback still happens | Send the script's console output + JSON report back. Check `fallback_reason` in DECISION records. |
| **C** | Another runtime bug remains | Send the script's console output + JSON report back. Include the full stack trace if any. |

---

## What the script verifies (10-point evidence)

1. **MT5 bars loaded** — `mt5.initialize()` succeeded, XAUUSD found, ≥15 bars loaded into `feature_stream._bars`.
2. **scaler_loaded = true** — `feature_stream._scaler_loaded == True`, 55 features loaded from `scaler_stats.json`.
3. **current_atr > 0** — ATR(14) computed from real MT5 bars (not 0.0).
4. **sl_tp_mode_used = atr** — journal DECISION record carries this field.
5. **fallback_used = false** — journal DECISION record carries this field; no fallback warning logged.
6. **signal generated** — SIGNAL record present in journal.
7. **ORDER created in dry_run only** — if signal accepted, ORDER record present with `dry_run=True`. ExecutionEngine internal guard prevents `mt5.order_send` calls.
8. **No real mt5.order_send** — verified via dry_run invariant (0 violations across all records carrying `dry_run` field).
9. **HEARTBEAT stable** — last 5 heartbeats printed; kill_switch_state stays NORMAL.
10. **kill_switch_state = NORMAL** — final state at shutdown.

---

## Output artifacts

After the run, the operator should send back:

1. **Console output** (copy-paste the full stdout from the script).
2. **`data\audit\windows_mt5_atr_verify_report.json`** — full machine-readable evidence.
3. **`data\runtime\windows_mt5_atr_verify.jsonl`** — raw journal records (optional, large).

These three artifacts are sufficient for Z AI to confirm verdict A and proceed to Phase 2 planning.

---

## Troubleshooting

### "MetaTrader5 package not installed"
```cmd
pip install MetaTrader5
```
If installation fails, ensure Python is 64-bit (32-bit Python can't load MT5).

### "mt5.initialize() failed"
- Make sure MT5 terminal is **running** (not just installed).
- Make sure you're **logged in** to a broker account.
- Try running MT5 as Administrator.
- Check the MT5 terminal logs tab for errors.

### "XAUUSD symbol not found"
- In MT5 terminal: right-click the Market Watch → **Show All**.
- Scroll to find `XAUUSD` (broker may name it `XAUUSD.m`, `XAUUSD.r`, `GOLD`, etc.).
- If broker uses a different name, edit `scripts\audit\windows_mt5_atr_verify.py` line ~127 and replace `"XAUUSD"` with your broker's symbol name.

### "bars_loaded_initial: 0" or low count
- MT5 may need to download H1 history. In MT5 terminal:
  - Open **View → Symbols → XAUUSD → Request** to download history.
  - Or just leave MT5 running for a few minutes — it downloads history automatically.
- Re-run the script.

### "scaler_loaded: False"
- Verify `titan\data\features\scaler_stats.json` exists.
- If missing, the script still runs but predictions will be deflated. Run:
  ```cmd
  python scripts\compute_scaler_stats.py
  ```

### Verdict B (ATR fallback)
- Check `fallback_reason` in journal DECISION records:
  - `"atr_zero"` → ATR came back as 0 (insufficient bars or NaN — wait for more bars).
  - `"atr_nan"` → ATR was NaN (data quality issue — check MT5 history).
  - `"mode_fixed"` → `sl_mode` was somehow set to `"fixed"` (config drift — re-check `runtime.yaml`).

### Verdict C (another runtime bug)
- Send the full console output + JSON report + journal JSONL back to Z AI.
- Include any Python traceback visible in the console.

---

## Hard safety guarantees (built into the script)

The script does NOT:
- Set `dry_run=False`
- Set `live_trading=True`
- Change ATR multipliers
- Change SL/TP formulas
- Call `mt5.order_send` directly (ExecutionEngine internal guard rejects when `dry_run=True`)
- Modify models, thresholds, or risk parameters

The script DOES:
- Run `AutonomousRuntime` with the production code path
- Read real MT5 H1 bars into `feature_stream._bars`
- Compute `current_atr` via `_compute_current_atr()` (the production helper)
- Pass `current_atr` to `TradeLoop.process_signal()` (which uses `_compute_sl_tp()` to compute ATR-based SL/TP)
- Write journal records with all 12 Sprint 8.5 audit fields
- Verify `dry_run=True` on every record carrying the field

---

## After successful verification (verdict A)

Send back:
1. Console output (full stdout)
2. `data\audit\windows_mt5_atr_verify_report.json`

Z AI will then produce the **Phase 2 — Demo Account Challenge Validation Plan** tailored to your MT5 broker (Exness) and ATR profile (balanced 2.0/4.0).
