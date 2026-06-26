# Sprint 9.9 — DEMO Micro Operator Runbook

## Overview

This runbook provides exact commands for running the FundedNext DEMO micro full-cycle test on Windows.

**Z AI must NEVER run DEMO_MICRO_EXECUTE. Only the operator may execute this on their Windows machine.**

## Prerequisites

1. Windows 10/11 with Python 3.12+
2. MetaTrader5 terminal running and logged into FundedNext **DEMO** account
3. XAUUSD visible in Market Watch
4. TITAN_XAU_AI repo cloned and up to date

## Pre-Execute Checklist (MUST VERIFY ALL)

Before running DEMO_MICRO_EXECUTE, verify ALL of the following:

- [ ] MT5 terminal is running
- [ ] Account is **DEMO** (not real/live)
- [ ] Server is **FundedNext DEMO**
- [ ] Symbol **XAUUSD** visible in Market Watch
- [ ] Market is **open** (not weekend)
- [ ] Spread is **≤ 1.0 USD**
- [ ] **No existing open positions** on the account
- [ ] Lot size is **0.01**
- [ ] Max trades is **1**
- [ ] Force-close is **enabled**
- [ ] Emergency stop instructions are **understood**
- [ ] **No real/live account** is logged in anywhere

## Step 1: Prepare Environment

Open Windows CMD:

```cmd
cd /d "D:\Forex project\TITAN_XAU_AI"
myenv\Scripts\activate
git pull origin main
git status
```

## Step 2: Verify Safety

```cmd
python first_run_check.py
```

Expected: 12+ PASS, 0 FAIL

## Step 3: Run Hard Gate Check

```cmd
python scripts/audit/demo_micro_hard_gate.py
```

Check output:
- `DEMO_MICRO_BLOCKED` → arm token not set (normal before arming)
- `MARKET_CLOSED` → market is closed, wait for open hours
- `DEMO_MICRO_ARMED` → all checks pass, ready to execute

## Step 4: Run DRY_ARM_CHECK_ONLY

```cmd
python scripts/audit/fundednext_demo_micro_full_cycle.py --mode DRY_ARM_CHECK_ONLY
```

This runs all checks without sending any orders. Verify:
- `order_send_called: false`
- `final_verdict` shows BLOCKED (without arm) or ARMED (with arm)

## Step 5: Run DEMO_MICRO_EXECUTE (OPERATOR ONLY)

**⚠️ ONLY after all pre-execute checklist items are verified:**

```cmd
set TITAN_DEMO_MICRO_ARMED=1
python scripts/audit/fundednext_demo_micro_full_cycle.py --mode DEMO_MICRO_EXECUTE --max-trades 1 --max-duration-minutes 240 --symbol XAUUSD --lot 0.01
```

## Emergency Stop Instructions

### How to Stop the Script
- Press `Ctrl+C` in the CMD window
- The force-close watchdog will attempt to close any open DEMO position
- A partial report will be generated at `data/audit/demo_micro/demo_micro_report.json`

### Force-Close Watchdog Behavior
- If position remains open after `max_duration_minutes` (240), it will be force-closed
- If equity loss exceeds `max_total_loss_pct` (0.50%), position will be force-closed
- If kill switch escalates, position will be force-closed
- Every close attempt is journaled

### If DEMO_MANUAL_REVIEW_REQUIRED Appears
1. **Stop immediately** — do NOT start another run
2. Check `data/audit/demo_micro/demo_micro_report.json` for details
3. Check `data/audit/demo_micro/demo_micro_journal.jsonl` for all events
4. **Manually close any remaining open DEMO positions** in MT5 terminal:
   - Open MT5 terminal
   - Go to Trade tab
   - Find any open XAUUSD position
   - Right-click → Close Position
5. Do NOT proceed to another run until ALL positions are closed
6. Send the report files to Z AI for analysis

### How to Manually Inspect MT5 Open Positions
1. Open MT5 terminal
2. Click "Trade" tab at bottom
3. Verify no open positions exist
4. If positions exist, close them manually

### NEVER Run on Real/Live Account
- Always verify account shows "DEMO" or "Demo" in MT5 terminal
- Never set `TITAN_LIVE_TRADING=1` for demo micro tests
- Never change `runtime.dry_run` to `false` for demo micro tests
- The hard gate will block non-DEMO accounts, but always double-check manually

## Output Files

After each run, check:
- `data/audit/demo_micro/demo_micro_report.json` — main report
- `data/audit/demo_micro/demo_micro_report.md` — markdown summary
- `data/audit/demo_micro/demo_micro_journal.jsonl` — full event journal
- `data/audit/demo_micro/demo_micro_hard_gate_report.json` — hard gate results

## Safety Guarantees

| Rule | Enforcement |
|---|---|
| DEMO account only | Hard gate blocks non-DEMO |
| Max lot 0.01 | Config + hard gate |
| Max 1 open position | Config + harness |
| Max 1-3 trades per run | Config + harness |
| Force-close on end | Watchdog + config |
| No martingale/grid | Not implemented — impossible |
| No lot escalation | Hard cap 0.01 |
| Arm token required | `TITAN_DEMO_MICRO_ARMED=1` env var |
| Z AI cannot execute | Z AI environment has no MT5 |
| Weekend blocked | `allow_weekend: false` + market_open check |
| High spread blocked | `max_spread_usd: 1.0` + hard gate check |
