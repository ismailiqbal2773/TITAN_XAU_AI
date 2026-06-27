# Sprint 9.9 — DEMO Micro Operator Runbook

## Overview

This runbook provides exact commands for running the FundedNext DEMO micro full-cycle test on Windows.

**Sprint 9.9.3 — ACTUAL DEMO MT5 ORDER EXECUTION IS NOW IMPLEMENTED.**

- `DRY_ARM_CHECK_ONLY` — checks gates, sends NO orders. Safe to run anywhere.
- `DEMO_MICRO_EXECUTE` — operator-only. **Actually opens AND closes ONE DEMO MT5 order.**
  Requires `TITAN_DEMO_MICRO_ARMED=1` env var + DEMO account + hard gate `DEMO_MICRO_ARMED`.

**Z AI must NEVER run DEMO_MICRO_EXECUTE. Only the operator may execute this on their Windows machine.**

## Prerequisites

1. Windows 10/11 with Python 3.12+
2. MetaTrader5 terminal running and logged into FundedNext **DEMO** account
3. XAUUSD visible in Market Watch
4. TITAN_XAU_AI repo cloned and up to date
5. Python package `MetaTrader5` installed: `pip install MetaTrader5`

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
- [ ] Emergency stop instructions are **understood** (see below)
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
- `DEMO_MICRO_BLOCKED` → arm token not set (normal before arming) or `demo_micro.enabled=false`
- `MARKET_CLOSED` → market is closed, wait for open hours
- `DEMO_MICRO_ARMED` → all checks pass, ready to execute

## Step 4: Run DRY_ARM_CHECK_ONLY

```cmd
python scripts/audit/fundednext_demo_micro_full_cycle.py --mode DRY_ARM_CHECK_ONLY
```

This runs all checks without sending any orders. Verify:
- `order_send_called: false`
- `final_verdict` shows BLOCKED (without arm) or ARMED (with arm)

## Step 5: Enable DEMO Micro in Config

Manually edit `config/runtime.yaml`:

```yaml
demo_micro:
  enabled: true        # change from false to true
```

Re-run Step 3 — hard gate should now report `demo_micro_enabled: True`.

## Step 6: Set Arm Token

```cmd
set TITAN_DEMO_MICRO_ARMED=1
```

Verify:

```cmd
echo %TITAN_DEMO_MICRO_ARMED%
```

Expected: `1`

## Step 7: Run Actual Controlled DEMO Test

### Option A: Short BUY test (60-second hold, recommended first run)

```cmd
python scripts/audit/fundednext_demo_micro_full_cycle.py --mode DEMO_MICRO_EXECUTE --max-trades 1 --max-duration-minutes 5 --max-hold-seconds 60 --symbol XAUUSD --lot 0.01 --side BUY
```

### Option B: Short SELL test

```cmd
python scripts/audit/fundednext_demo_micro_full_cycle.py --mode DEMO_MICRO_EXECUTE --max-trades 1 --max-duration-minutes 5 --max-hold-seconds 60 --symbol XAUUSD --lot 0.01 --side SELL
```

### Option C: Standard 4-hour test (default)

```cmd
python scripts/audit/fundednext_demo_micro_full_cycle.py --mode DEMO_MICRO_EXECUTE --max-trades 1 --max-duration-minutes 240 --symbol XAUUSD --lot 0.01 --side BUY
```

### CLI Arguments Reference

| Argument | Required | Default | Description |
|---|---|---|---|
| `--mode` | Yes | `DRY_ARM_CHECK_ONLY` | `DRY_ARM_CHECK_ONLY` or `DEMO_MICRO_EXECUTE` |
| `--max-trades` | No | `1` | Max trades per run (hard cap 3) |
| `--max-duration-minutes` | No | `240` | Max duration in minutes |
| `--symbol` | No | `XAUUSD` | Symbol to trade |
| `--lot` | No | `0.01` | Lot size (max 0.01) |
| `--side` | **Conditional** | None | `BUY` or `SELL`. Required if no AI signal available. |
| `--max-hold-seconds` | No | None | Close position after N seconds (operator test mode) |
| `--force-close-on-end` | No | `true` | Force-close any remaining position on exit |

### Side Resolution Logic

The harness resolves trade side as follows:

1. Try to load latest AI signal from `data/runtime/titan_journal.jsonl`
2. If signal is BUY or SELL and < 5 minutes old, use that
3. Otherwise, use `--side` CLI argument
4. If neither is available, **BLOCKED** with `DEMO_MICRO_BLOCKED` (refuses to guess)

## Step 8: Post-Run Verification

After the test completes:

1. Verify `open positions remaining: 0` in the report
2. Verify `final_verdict: DEMO_FULL_CYCLE_PASS`
3. Inspect report files:
   - `data/audit/demo_micro/demo_micro_report.json`
   - `data/audit/demo_micro/demo_micro_report.md`
   - `data/audit/demo_micro/demo_micro_journal.jsonl`

## Step 9: Disable DEMO Micro

After the test, restore safe defaults:

```cmd
:: Clear arm token
set TITAN_DEMO_MICRO_ARMED=
```

Manually edit `config/runtime.yaml`:

```yaml
demo_micro:
  enabled: false       # change back to false
```

Re-run hard gate to verify:

```cmd
python scripts/audit/demo_micro_hard_gate.py
```

Expected: `DEMO_MICRO_BLOCKED` with reason `demo_micro.enabled=false (config)`.

## Emergency Stop Instructions

### How to Stop the Script Mid-Run

- Press `Ctrl+C` in the CMD window
- OR set the emergency stop env var in another CMD window:

```cmd
set TITAN_DEMO_MICRO_EMERGENCY_STOP=1
```

The monitor loop checks this env var every ~1 second and triggers close on next iteration.

### Force-Close Watchdog Behavior

The harness monitors the open position and triggers close when ANY of the following occur:

- `--max-hold-seconds` reached (operator test mode)
- `--max-duration-minutes` reached (absolute cap)
- Floating loss exceeds `max_total_loss_pct` of initial balance (0.50% default)
- Kill switch escalates to `HALT_NEW_TRADES`, `FLATTEN_ONLY`, or `EMERGENCY_STOP`
- `TITAN_DEMO_MICRO_EMERGENCY_STOP=1` env var is set
- Position disappears externally (closed by operator in MT5)

### Close Order Logic

- BUY position → closed with SELL market order (same volume, current bid)
- SELL position → closed with BUY market order (same volume, current ask)
- Exactly ONE close attempt is made (no retry on failure)
- If close fails → `DEMO_MANUAL_REVIEW_REQUIRED`

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
- The hard gate blocks non-DEMO accounts (trade_mode != 0), but always double-check manually

## Output Files

After each run, check:

- `data/audit/demo_micro/demo_micro_report.json` — main report (full result dict)
- `data/audit/demo_micro/demo_micro_report.md` — markdown summary
- `data/audit/demo_micro/demo_micro_journal.jsonl` — full event journal (JSONL, append-only)
- `data/audit/demo_micro/demo_micro_hard_gate_report.json` — hard gate results
- `data/audit/demo_micro/demo_micro_hard_gate_report.md` — hard gate markdown

### Report Fields (Sprint 9.9.3)

| Field | Description |
|---|---|
| `final_verdict` | PASS / FAIL / BLOCKED / MANUAL_REVIEW_REQUIRED |
| `order_send_called` | True if any order_send was attempted |
| `order_send_attempts` | Number of open order attempts (always 1 max) |
| `order_send_success` | Number of successful open orders |
| `close_attempts` | Number of close order attempts (always 1 max) |
| `close_success` | Number of successful close orders |
| `open_positions_remaining` | Open positions remaining after run (must be 0 for PASS) |
| `gross_pnl` | Gross profit/loss |
| `spread_cost` | Spread cost |
| `commission_cost` | Commission cost |
| `slippage_cost` | Slippage cost |
| `swap_cost` | Swap cost |
| `net_pnl` | Net profit/loss (gross - all costs) |
| `holding_seconds` | Time position was held |
| `open_price` | Position open price |
| `close_price` | Position close price |
| `max_floating_dd` | Maximum floating drawdown observed |
| `close_reason` | Why the position was closed |
| `emergency_stop` | True if emergency stop triggered |

### Journal Events (Sprint 9.9.3)

| Event | Description |
|---|---|
| `DEMO_MICRO_ORDER_REQUESTED` | Order request built and about to be sent |
| `DEMO_MICRO_ORDER_SENT` | order_send returned success |
| `DEMO_MICRO_ORDER_FAILED` | order_send returned failure |
| `DEMO_MICRO_POSITION_SYNCED` | Position confirmed via positions_get |
| `DEMO_MICRO_POSITION_SYNC_FAILED` | Position not found within sync timeout |
| `DEMO_MICRO_MONITOR_HEARTBEAT` | Periodic monitor heartbeat (every 30s) |
| `DEMO_MICRO_POSITION_CLOSE_REQUESTED` | Close request initiated |
| `DEMO_MICRO_POSITION_CLOSED` | Close order succeeded |
| `DEMO_MICRO_CLOSE_FAILED` | Close order failed |
| `DEMO_MICRO_FULL_CYCLE_PASS` | Final verdict: PASS |
| `DEMO_MICRO_MANUAL_REVIEW_REQUIRED` | Final verdict: manual review needed |
| `DEMO_MICRO_EXECUTE_BLOCKED` | Execute was blocked before any order |

## Safety Guarantees

| Rule | Enforcement |
|---|---|
| DEMO account only | Hard gate blocks non-DEMO + execute double-checks `trade_mode == 0` |
| Max lot 0.01 | Config + hard gate + execute explicit check |
| Max 1 open position | Config + harness refuses if existing position found |
| Max 1-3 trades per run | Config + harness hard cap (always sends exactly 1) |
| No duplicate orders | Open order_send is called exactly once (never retried) |
| Force-close on end | Watchdog + config + close policy |
| No martingale/grid/averaging | Not implemented — impossible |
| No lot escalation | Hard cap 0.01, no `lot *= 2` logic |
| Arm token required | `TITAN_DEMO_MICRO_ARMED=1` env var checked first |
| Hard gate required | `DEMO_MICRO_ARMED` verdict checked second |
| Z AI cannot execute | Z AI env has no MetaTrader5 — `_get_mt5()` returns None |
| Weekend blocked | `allow_weekend: false` + `market_open` check |
| High spread blocked | `max_spread_usd: 1.0` + execute explicit check |
| Stale tick blocked | Execute checks tick age < 60s |
| Symbol not visible | Execute checks `symbol_info().visible` and calls `symbol_select` |
| Position sync verified | Execute verifies exactly one matching position before monitoring |
| Close uses opposite side | BUY→SELL, SELL→BUY (same volume) |
| Never PASS with open position | `open_positions_remaining == 0` required for PASS |

## Troubleshooting

### `DEMO_MICRO_BLOCKED: Arm token not present`

→ Run `set TITAN_DEMO_MICRO_ARMED=1` in the same CMD window before running the harness.

### `DEMO_MICRO_BLOCKED: demo_micro.enabled=false (config)`

→ Edit `config/runtime.yaml`, change `demo_micro.enabled` to `true`.

### `DEMO_MICRO_BLOCKED: Hard gate: DEMO_MICRO_BLOCKED`

→ Run `python scripts/audit/demo_micro_hard_gate.py` and inspect which check failed.

### `DEMO_MICRO_BLOCKED: No AI signal and no --side provided`

→ Pass `--side BUY` or `--side SELL` explicitly.

### `DEMO_MICRO_BLOCKED: Account is NOT DEMO`

→ Stop immediately. Switch MT5 terminal to a DEMO account before re-running.

### `DEMO_MICRO_BLOCKED: Existing open position`

→ Close any existing XAUUSD position in MT5 terminal before re-running.

### `DEMO_MICRO_BLOCKED: Spread too high`

→ Wait for spread to drop below `max_spread_usd` (default 1.0 USD).

### `DEMO_FULL_CYCLE_FAIL: order_send failed`

→ Inspect `retcode` in the journal. Common causes:
- `10004` (REQUOTE) → try again later
- `10006` (REJECT) → broker rejected; check symbol/lot/comment
- `10018` (CANCELLED) → check with broker

### `DEMO_MANUAL_REVIEW_REQUIRED: Position sync failed`

→ Order was sent but position did not appear in MT5 within 5 seconds.
   Manually verify in MT5 Trade tab whether position exists.
   If yes, close manually. If no, contact broker.

### `DEMO_MANUAL_REVIEW_REQUIRED: Close failed`

→ Close order_send failed. Position likely still open.
   Manually close the position in MT5 Trade tab.

## Warning

**Only run on FundedNext DEMO.**
**Never run on real/live account.**
**Z AI must NEVER run DEMO_MICRO_EXECUTE.**
