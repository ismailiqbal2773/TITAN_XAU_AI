# TITAN XAU AI — User Guide

> **For non-technical users.** No Python knowledge required.

---

## What is TITAN?

TITAN is an AI trading assistant for XAUUSD (Gold). It runs on your computer alongside MetaTrader 5 (MT5) and helps you test trading strategies on a **demo account** (no real money).

**Important:** TITAN runs in **dry_run mode** by default. This means it generates trading signals but does NOT place real orders. You can watch what TITAN would do without any risk.

---

## System Requirements

| Requirement | Minimum |
|-------------|---------|
| Operating System | Windows 10 or 11 (64-bit) |
| MetaTrader 5 | Version 5.0.45 or newer |
| MT5 Demo Account | Any broker (FundedNext, Exness, IC Markets, FBS) |
| RAM | 4 GB |
| Disk Space | 500 MB |
| Internet | Required for MT5 connection |

---

## Step 1: Install MetaTrader 5

1. Download MT5 from your broker's website
   - FundedNext: https://fundednext.com
   - Exness: https://exness.com
   - IC Markets: https://icmarkets.com
2. Run the MT5 installer
3. Open MT5 and log in to your **demo account**
   - Login: your demo account number (e.g., 34265693)
   - Password: your demo account password
   - Server: your broker's demo server (e.g., FundedNext-Server 3)
4. Verify XAUUSD (Gold) appears in Market Watch
   - View → Market Watch
   - Right-click → Show All
   - Find "XAUUSD" or "GOLD"

---

## Step 2: Install TITAN

### Option A: Use TITAN.exe (Easiest — No Python Required)

1. Download `TITAN_Setup.exe` from the GitHub releases page
2. Double-click to install
3. TITAN installs to `C:\TITAN\`
4. A desktop shortcut is created automatically

### Option B: Use Python (For Advanced Users)

1. Install Python 3.12+ from https://python.org
   - **Important:** Check "Add Python to PATH" during installation
2. Download TITAN from GitHub:
   ```
   git clone https://github.com/ismailiqbal2773/TITAN_XAU_AI.git
   cd TITAN_XAU_AI
   ```
3. Install dependencies:
   ```
   pip install -r titan\requirements.txt
   pip install pyarrow structlog aiosqlite pytest-asyncio
   ```

---

## Step 3: First-Time Setup

### Run the Setup Wizard

**Using TITAN.exe:**
1. Double-click the TITAN desktop shortcut
2. The Setup Wizard starts automatically on first run
3. Follow the on-screen prompts

**Using Python:**
```
python titan\setup\setup_wizard.py
```

### Wizard Steps

The wizard will ask you:

1. **Locate MT5 Terminal**
   - TITAN auto-detects MT5 installation
   - If not found, enter the path manually (usually `C:\Program Files\MetaTrader 5\terminal64.exe`)

2. **Validate MT5 Installation**
   - TITAN checks if MT5 is properly installed

3. **Validate Demo Account**
   - Enter your demo account login, password, and server
   - TITAN verifies the account is a DEMO account (refuses real accounts)

4. **Select Deployment Mode**
   - **Local PC** (recommended for demo testing)
   - **VPS** (for 24/7 unattended operation)
   - **Institute** (for multi-account management)

5. **Configure Journal Location**
   - Default: `data/runtime/titan_journal.jsonl`
   - The journal records all TITAN activity

6. **Save Configuration**
   - TITAN saves settings to `config/runtime.yaml`

---

## Step 4: Run TITAN

### Starting TITAN

**Using TITAN.exe:**
1. Double-click the TITAN desktop shortcut
2. TITAN validates environment, config, models, and MT5
3. TITAN starts in dry_run mode

**Using Python:**
```
python titan_launcher.py
```

**Using TITAN.bat:**
```
Double-click TITAN.bat
```

### What TITAN Does

When running, TITAN:
1. Connects to your MT5 demo account
2. Generates trading signals every hour (H1 timeframe)
3. Checks each signal against risk rules
4. Creates dry_run orders (NO real orders placed)
5. Records everything to the journal
6. Monitors for safety conditions (kill-switch, news, drift)

### Stopping TITAN

- Press `Ctrl+C` in the TITAN window
- Or close the window
- TITAN shuts down safely and saves the journal

---

## Step 5: Monitor TITAN

### Journal Location

All TITAN activity is recorded in:
```
data/runtime/titan_journal.jsonl
```

Each line is a JSON record. You can open this file in any text editor.

### Daily Reports

TITAN generates daily reports:
```
data/reports/daily_report_YYYY-MM-DD.json
```

### Weekly Reports

```
data/reports/weekly_report_YYYY-MM-DD.json
```

### Dashboard

The Grafana dashboard spec is at:
```
monitoring/forward_test_dashboard.json
```

To use with Grafana:
1. Install Grafana (https://grafana.com)
2. Import the dashboard spec
3. Point data source to the journal JSONL file

---

## Understanding dry_run Mode

### What dry_run Means

| Action | dry_run=True (Default) | dry_run=False (Live) |
|--------|------------------------|----------------------|
| Signal generation | ✓ Runs | ✓ Runs |
| Risk checks | ✓ Runs | ✓ Runs |
| Order creation | ✓ Simulated | ✓ Real |
| MT5 order_send | ✗ NOT called | ✓ Called |
| Position tracking | ✓ Stub mode | ✓ MT5 polling |
| Journal logging | ✓ Full | ✓ Full |

### How to Verify dry_run is Active

1. Check `config/runtime.yaml`:
   ```yaml
   runtime:
     dry_run: true        # MUST be true
     live_trading: false  # MUST be false
   ```

2. Run the first-run check:
   ```
   python first_run_check.py
   ```
   Look for: `✓ [PASS] dry_run mode: True (safe)`

### Switching to Live Mode (NOT RECOMMENDED)

**Do NOT switch to live mode until:**
- You have run TITAN in dry_run for at least 30 days
- You understand all the risks
- You have verified all safety systems work

To enable live mode:
1. Edit `config/runtime.yaml`:
   ```yaml
   runtime:
     dry_run: false
     live_trading: true
   ```
2. Set environment variable:
   ```
   set TITAN_LIVE_TRADING=1
   ```
3. Run TITAN — it will ask for confirmation

---

## Kill-Switch States

TITAN has a 5-state kill-switch that protects your account:

| State | What Happens | When It Triggers |
|-------|-------------|------------------|
| NORMAL | Trading allowed | Default state |
| CAUTION | Trading allowed, smaller size | High latency, model drift |
| HALT_NEW_TRADES | No new trades | Daily loss > 3%, news event |
| FLATTEN_ONLY | No new trades, close existing | Drawdown > 5% |
| EMERGENCY_STOP | Close everything immediately | Drawdown > 8%, extreme latency |

### How to Reset Kill-Switch

If the kill-switch triggers, TITAN will not trade until you reset it:

1. Stop TITAN (Ctrl+C)
2. Investigate the cause (check journal for KILL_SWITCH_TRANSITION events)
3. Fix the issue
4. Restart TITAN — kill-switch resets to NORMAL on restart

---

## Troubleshooting

### TITAN Won't Start

**Problem:** "Config file not found"

**Solution:**
1. Run the setup wizard: `python titan\setup\setup_wizard.py`
2. Or copy the template: `copy config\runtime.yaml.example config\runtime.yaml`

---

**Problem:** "MT5 validation failed"

**Solution:**
1. Make sure MT5 is running and logged in
2. Check the terminal path in config
3. Run the MT5 validator: `python -m titan.setup.mt5_validator`

---

**Problem:** "Model files missing"

**Solution:**
1. Verify files exist in `titan/data/models/`
2. If missing, re-download from GitHub or restore from backup

---

**Problem:** "dry_run is False — UNSAFE"

**Solution:**
1. Edit `config/runtime.yaml`
2. Set `dry_run: true` and `live_trading: false`
3. Run first-run check: `python first_run_check.py`

### TITAN Starts But No Signals

**Problem:** TITAN runs but generates no tradeable signals

**Cause:** This is normal. TITAN only generates signals when XGBoost confidence ≥ 0.55 AND meta-label confidence ≥ 0.65. On many bars, neither threshold is met.

**Solution:**
1. Check the journal for SIGNAL records
2. Look at the `is_tradeable` field — if False, the signal was correctly rejected
3. Wait — TITAN may generate signals only a few times per day

### Kill-Switch Keeps Triggering

**Problem:** Kill-switch triggers frequently

**Solution:**
1. Check the journal for KILL_SWITCH_TRANSITION events
2. Look at the `trigger` field — it tells you why
3. Common causes:
   - High latency → use a VPS closer to broker
   - High spread → avoid trading during news
   - Model drift → may need retraining (contact support)
4. Adjust thresholds in `config/runtime.yaml` under `kill_switch:` section

### MT5 Connection Drops

**Problem:** TITAN loses MT5 connection

**Solution:**
1. Check if MT5 terminal is still running
2. Check internet connection
3. Restart MT5 terminal
4. Restart TITAN

---

## FAQ

### Q: Will TITAN place real orders?

**A:** NO. TITAN runs in dry_run mode by default. No real orders are placed. To enable live trading, you must explicitly set `dry_run: false` in config AND set the `TITAN_LIVE_TRADING=1` environment variable.

### Q: Can TITAN trade on a real account?

**A:** TITAN refuses to connect to real accounts. The MT5 demo adapter validates account type and blocks real accounts. This is a safety feature.

### Q: How much money do I need?

**A:** TITAN works with any demo account balance. For live trading (future), start with at least $1,000 and use 0.01 lot size (the maximum TITAN allows).

### Q: Does TITAN work on Mac/Linux?

**A:** TITAN requires Windows for MT5 connection. On Mac/Linux, TITAN can run in stub mode (no live data) for testing purposes.

### Q: How long should I run the demo?

**A:** At least 30 days. This gives you enough data to evaluate TITAN's performance and verify all safety systems work correctly.

### Q: Can I change the risk settings?

**A:** Yes. Edit `config/runtime.yaml` under the `risk:` section. But do NOT change `max_lot` above 0.01 — this is a hard safety cap.

---

## Getting Help

If you encounter issues:

1. Check this User Guide
2. Read the Demo Runbook: `docs/DEMO_RUNBOOK.md`
3. Run the first-run check: `python first_run_check.py`
4. Run the packaging smoke test: `python scripts/packaging_smoke_test.py`
5. Check the journal for error events
6. Contact support with your journal file attached

---

## Safety Reminders

- ✅ TITAN runs in dry_run mode by default (NO real orders)
- ✅ TITAN refuses to connect to real accounts
- ✅ TITAN has a 5-state kill-switch that protects your account
- ✅ TITAN journals every action for audit
- ✅ Max lot size is 0.01 (hard cap, cannot be changed)
- ✅ Max 1 open position at a time (hard cap)
- ✅ SL and TP are mandatory on every order
- ✅ News filter blocks trades around high-impact events

**Do NOT:**
- ❌ Change `dry_run` to `false` without 30 days of demo testing
- ❌ Try to bypass the kill-switch
- ❌ Change `max_lot` above 0.01
- ❌ Run TITAN on a real account
- ❌ Ignore kill-switch warnings

---

*Document version: 1.0 · Sprint 7.5 · 2026-06-23*
*For technical documentation, see docs/DEMO_RUNBOOK.md*
