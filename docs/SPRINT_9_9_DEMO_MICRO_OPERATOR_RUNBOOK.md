# Sprint 9.9 — DEMO Micro Operator Runbook

## Overview

This runbook provides exact commands for running the FundedNext DEMO micro full-cycle test on Windows.

**Z AI must NEVER run DEMO_MICRO_EXECUTE. Only the operator may execute this on their Windows machine.**

## Prerequisites

1. Windows 10/11 with Python 3.12+
2. MetaTrader5 terminal running and logged into FundedNext DEMO account
3. XAUUSD visible in Market Watch
4. TITAN_XAU_AI repo cloned and up to date

## Step 1: Prepare Environment

Open Windows CMD:

```cmd
cd /d "D:\Forex project\TITAN_XAU_AI"
myenv\Scripts\activate
git pull origin main
```

## Step 2: Verify Safety

```cmd
python first_run_check.py
```

Expected: 12 PASS, 1 WARN (MT5 Linux → should be PASS on Windows), 0 FAIL

## Step 3: Run Hard Gate Check

```cmd
python scripts/audit/demo_micro_hard_gate.py
```

This checks all safety gates without sending any orders. Expected on Windows DEMO:
- `DEMO_MICRO_BLOCKED` if `TITAN_DEMO_MICRO_ARMED` not set (normal — safe)
- `MARKET_CLOSED` if weekend
- `DEMO_MICRO_ARMED` if all checks pass and arm token is set

## Step 4: Run DRY_ARM_CHECK_ONLY

```cmd
python scripts/audit/fundednext_demo_micro_full_cycle.py --mode DRY_ARM_CHECK_ONLY
```

This runs all checks without sending any orders. Safe to run anytime.

## Step 5: Run DEMO_MICRO_EXECUTE (OPERATOR ONLY)

**Only run this when:**
- MT5 terminal is running and logged into FundedNext **DEMO** account
- Market is open (not weekend)
- You have verified the hard gate passes
- You understand this will open a real 0.01 lot DEMO order

```cmd
set TITAN_DEMO_MICRO_ARMED=1
python scripts/audit/fundednext_demo_micro_full_cycle.py --mode DEMO_MICRO_EXECUTE --max-trades 1 --max-duration-minutes 240 --symbol XAUUSD --lot 0.01
```

## Emergency Stop

### How to Stop the Script
- Press `Ctrl+C` in the CMD window
- The force-close watchdog will attempt to close any open DEMO position
- A partial report will be generated

### Force-Close Watchdog Behavior
- If position remains open after `max_duration_minutes`, it will be force-closed
- If equity loss exceeds `max_total_loss_pct` (0.50%), position will be force-closed
- If kill switch escalates, position will be force-closed
- Every close attempt is journaled

### If DEMO_MANUAL_REVIEW_REQUIRED Appears
1. Check `data/audit/demo_micro/demo_micro_report.json` for details
2. Check `data/audit/demo_micro/demo_micro_journal.jsonl` for all events
3. Manually close any remaining open DEMO positions in MT5 terminal
4. Do NOT proceed to another run until all positions are closed
5. Contact Z AI for analysis if needed

### How to Verify No Real/Live Account Is Used
1. Check MT5 terminal — account should show "DEMO" or "Demo"
2. Check `demo_micro_hard_gate_report.json` — `account_demo` must be `true`
3. Check `demo_micro_report.json` — `account_type` must be `DEMO`
4. Never set `TITAN_LIVE_TRADING=1` for demo micro tests
5. Never change `runtime.dry_run` to `false` for demo micro tests

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
