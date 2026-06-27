# Sprint 9.9.3.5 — Monday DEMO Micro Readiness & Safety Runbook

> **Purpose**: Prepare the repository for Monday's operator-only Windows MT5 FundedNext DEMO micro execution without changing trading behavior.
>
> **Scope**: This runbook covers ONE controlled 0.01 lot DEMO micro lifecycle:
> open → sync → controlled close → report.
>
> **Audience**: Operator only. **Z AI must NEVER run DEMO_MICRO_EXECUTE.**

---

## ⚠️ CRITICAL WARNINGS — READ BEFORE PROCEEDING

### 🚫 DO NOT RUN ON WEEKEND / MARKET CLOSED

- **XAUUSD market is closed Saturday and Sunday** (UTC).
- Running `DEMO_MICRO_EXECUTE` on a weekend will be blocked by the hard gate
  (`market_open: False`), but **do not attempt it** — it wastes time and
  risks leaving config in a half-enabled state.
- **Wait until Monday 00:00 UTC** (Sunday 19:00 EST / Monday 05:00 PKT) at the
  earliest. Optimal liquidity begins at London open (07:00 UTC) and continues
  through New York close (21:00 UTC).

### 🚫 DO NOT WIRE GOVERNANCE INTO LIVE/DEMO TRADE_LOOP YET

- Sprint 9.9.3.2–9.9.3.4 added the **StressLossGovernanceEngine** and validated
  it on 220 virtual scenarios + 500 Monte Carlo runs + 7-bot benchmark.
- Governance is currently **opt-in only** via the `--governance` flag on
  `virtual_lifecycle_validator.py`. It is **NOT wired into**:
  - `titan/production/trade_loop.py`
  - `scripts/audit/fundednext_demo_micro_full_cycle.py`
  - `titan/runtime/launcher.py`
- **Do not wire governance into live/demo execution until**:
  1. The Monday DEMO micro lifecycle proof passes (open → sync → close → report).
  2. The operator confirms the report shows `final_verdict: DEMO_FULL_CYCLE_PASS`.
  3. A separate sprint explicitly approves governance wiring.

### 🚫 OTHER STRICT PROHIBITIONS

- **Do NOT run `DEMO_MICRO_EXECUTE` on a real/live account.**
- **Do NOT change `runtime.dry_run` to `false`** for this test.
- **Do NOT change `runtime.live_trading` to `true`** for this test.
- **Do NOT set `TITAN_LIVE_TRADING=1`** for this test.
- **Do NOT increase `demo_micro.max_lot` above 0.01.**
- **Do NOT increase `demo_micro.max_open_positions` above 1.**
- **Do NOT increase `demo_micro.max_trades_per_run` above 1.**
- **Do NOT retrain models.**
- **Do NOT add martingale, grid, averaging, or lot escalation.**
- **Do NOT run `DEMO_MICRO_EXECUTE` more than once per session.**

---

## ✅ Pre-Monday Repository Verification (Already Completed)

The following checks were verified before this runbook was committed:

| Check | Status |
|---|---|
| Repo clean, latest commit `8fc97d2` | ✅ PASS |
| `first_run_check.py` — 12 PASS, 1 WARN, 0 FAIL | ✅ PASS |
| `pytest titan/tests/test_demo_micro_hard_gate.py` — 25 passed | ✅ PASS |
| `pytest titan/tests/test_fundednext_demo_micro_harness.py` — 63 passed, 1 skipped | ✅ PASS |
| `pytest titan/tests/test_stress_loss_governance.py` — 58 passed | ✅ PASS |
| `runtime.dry_run: true` (default) | ✅ PASS |
| `runtime.live_trading: false` (default) | ✅ PASS |
| `demo_micro.enabled: false` (default) | ✅ PASS |
| `demo_micro.max_lot: 0.01` | ✅ PASS |
| `demo_micro.max_open_positions: 1` | ✅ PASS |
| `demo_micro.max_trades_per_run: 1` | ✅ PASS |
| `demo_micro.force_close_on_end: true` | ✅ PASS |
| `demo_micro.allow_weekend: false` | ✅ PASS |
| No GitHub PAT tokens in tracked files or git history | ✅ PASS |
| `DEMO_MICRO_EXECUTE` guards: DEMO account, enabled, arm token, lot ≤ 0.01, positions ≤ 1, trades ≤ 1, market open | ✅ PASS (7 guards) |
| Hard gate verdict on Z AI / Linux: `DEMO_MICRO_BLOCKED` | ✅ PASS (correct fail-closed) |
| `DRY_ARM_CHECK_ONLY` verdict on Z AI / Linux: `DEMO_MICRO_BLOCKED`, `order_send_called: False` | ✅ PASS |

---

## 📋 Monday Operator Pre-Execute Checklist (MUST VERIFY ALL)

Before running `DEMO_MICRO_EXECUTE`, verify ALL of the following:

- [ ] Today is **Monday through Friday** (NOT Saturday or Sunday)
- [ ] Current time is between **07:00 UTC and 21:00 UTC** (London open to NY close)
- [ ] MT5 terminal is running and logged into **FundedNext DEMO** account
- [ ] Account shows **"DEMO"** or **"Demo"** in MT5 terminal title bar
- [ ] Server is **FundedNext-Server** (DEMO, not live)
- [ ] Symbol **XAUUSD** is visible in Market Watch
- [ ] Spread is **≤ 1.0 USD** (check bid/ask in Market Watch)
- [ ] **No existing open positions** on the account (Trade tab is empty)
- [ ] Lot size will be **0.01** (hard cap, cannot be exceeded)
- [ ] Max trades will be **1** (hard cap, cannot be exceeded)
- [ ] Force-close is **enabled** (default in config)
- [ ] Emergency stop instructions are **understood** (see below)
- [ ] **No real/live account** is logged in anywhere
- [ ] `TITAN_LIVE_TRADING` env var is **NOT set** to 1
- [ ] `runtime.dry_run` is **true** in config/runtime.yaml
- [ ] `runtime.live_trading` is **false** in config/runtime.yaml

---

## 🖥️ Exact Windows CMD Commands

### Step 1: Open CMD and Activate Virtual Environment

```cmd
cd /d "D:\Forex project\TITAN_XAU_AI"
myenv\Scripts\activate
```

Verify activation — prompt should show `(myenv)` prefix:
```cmd
echo %VIRTUAL_ENV%
```
Expected: `D:\Forex project\TITAN_XAU_AI\myenv`

### Step 2: Pull Latest Code and Verify Clean State

```cmd
git pull origin main
git status
git log --oneline -3
```

Expected:
- `git pull`: `Already up to date.` or fast-forward to latest commit
- `git status`: `nothing to commit, working tree clean`
- `git log --oneline -3`: shows `8fc97d2 audit(sprint-9.9.3.4)...` as HEAD (or newer)

If `git status` shows modified files, **STOP** and run:
```cmd
git stash
git pull origin main
```

### Step 3: Run First Run Check

```cmd
python first_run_check.py
```

Expected: **12+ PASS, 0 FAIL** (1 WARN on MT5 connection is normal before MT5 starts).
If any FAIL appears, **STOP** and fix before proceeding.

### Step 4: Verify MT5 Connection

Ensure MT5 terminal is running and logged into FundedNext DEMO, then:

```cmd
python -c "import MetaTrader5 as mt5; print('initialize:', mt5.initialize()); print('account:', mt5.account_info()); mt5.shutdown()"
```

Expected:
- `initialize: True`
- `account:` shows an `_AccountInfo` object with `trade_mode: 0` (DEMO)

If `initialize: False`:
- Verify MT5 terminal is running
- Verify login credentials are correct
- Restart MT5 terminal and retry

### Step 5: Verify No Open XAUUSD Positions

```cmd
python -c "import MetaTrader5 as mt5; mt5.initialize(); positions = mt5.positions_get(symbol='XAUUSD'); print('positions:', positions); mt5.shutdown()"
```

Expected: `positions: ()` or `positions: []` (empty tuple/list).

If positions exist, **manually close them in MT5 terminal** before proceeding:
1. Open MT5 terminal
2. Click "Trade" tab at bottom
3. Right-click each open position → "Close Position"
4. Re-run the command above to verify

### Step 6: Verify Config Defaults

```cmd
python -c "import yaml; cfg = yaml.safe_load(open('config/runtime.yaml', encoding='utf-8')); print('dry_run:', cfg['runtime']['dry_run']); print('live_trading:', cfg['runtime']['live_trading']); print('demo_micro.enabled:', cfg['demo_micro']['enabled']); print('max_lot:', cfg['demo_micro']['max_lot'])"
```

Expected output:
```
dry_run: True
live_trading: False
demo_micro.enabled: False
max_lot: 0.01
```

If any value differs, **STOP** — config has been modified. Restore from git:
```cmd
git checkout config/runtime.yaml
```

### Step 7: Run Hard Gate Check (Before Enabling demo_micro)

```cmd
python scripts/audit/demo_micro_hard_gate.py
```

Expected: `VERDICT: DEMO_MICRO_BLOCKED` with reasons:
- `demo_micro.enabled=False (config)`
- `TITAN_DEMO_MICRO_ARMED not set to 1`

This is correct fail-closed behavior. **Do not proceed if verdict is `DEMO_MICRO_ARMED`** at this stage.

### Step 8: Temporarily Enable demo_micro in Config

Manually edit `config/runtime.yaml` — change ONLY the `enabled` field:

```yaml
demo_micro:
  enabled: true        # change from false to true (TEMPORARY)
```

**Do NOT change any other field.** Save the file.

Verify:
```cmd
python -c "import yaml; cfg = yaml.safe_load(open('config/runtime.yaml', encoding='utf-8')); print('demo_micro.enabled:', cfg['demo_micro']['enabled'])"
```

Expected: `demo_micro.enabled: True`

### Step 9: Set Arm Token

```cmd
set TITAN_DEMO_MICRO_ARMED=1
```

Verify:
```cmd
echo %TITAN_DEMO_MICRO_ARMED%
```

Expected: `1`

### Step 10: Run Hard Gate Check (After Enabling)

```cmd
python scripts/audit/demo_micro_hard_gate.py
```

Expected: `VERDICT: DEMO_MICRO_ARMED` with all checks passing:
```
[✓] mt5_reachable: True
[✓] account_demo: True
[✓] demo_micro_enabled: True
[✓] arm_token_present: True
[✓] not_real_account: True
[✓] max_lot_ok: True
[✓] max_positions_ok: True
[✓] max_trades_ok: True
[✓] force_close_on_end: True
[✓] kill_switch_normal: True
[✓] market_open: True
[✓] demo_micro_readiness_ok: True
```

If any check shows `[✗]`, **STOP** and fix before proceeding.

### Step 11: Run DRY_ARM_CHECK_ONLY (Final Dry Check)

```cmd
python scripts/audit/fundednext_demo_micro_full_cycle.py --mode DRY_ARM_CHECK_ONLY
```

Expected:
- `Gate verdict: DEMO_MICRO_ARMED`
- `order_send_called: false`
- `final_verdict: DEMO_MICRO_ARMED`
- Message: `DRY_ARM_CHECK_ONLY — no orders sent. Execute would be ARMED.`

**If this shows BLOCKED or attempts order_send, DO NOT proceed to Step 12.**

### Step 12: Run DEMO_MICRO_EXECUTE (OPERATOR ONLY — ONE TIME ONLY)

**⚠️ This is the ONLY step that sends a real DEMO MT5 order.**

```cmd
python scripts/audit/fundednext_demo_micro_full_cycle.py --mode DEMO_MICRO_EXECUTE --max-trades 1 --max-duration-minutes 5 --max-hold-seconds 60 --symbol XAUUSD --lot 0.01 --side BUY
```

**Parameters explained:**
- `--mode DEMO_MICRO_EXECUTE` — operator-only execute mode
- `--max-trades 1` — exactly ONE trade (hard cap)
- `--max-duration-minutes 5` — max 5 minutes for the whole cycle
- `--max-hold-seconds 60` — close position after 60 seconds (short controlled test)
- `--symbol XAUUSD` — Gold vs USD
- `--lot 0.01` — minimum lot (hard cap, cannot exceed)
- `--side BUY` — explicit BUY direction (no AI signal guessing)

Expected output:
```
>>> DEMO_MICRO_EXECUTE result: DEMO_FULL_CYCLE_PASS
>>> Net PnL: <small number, may be positive or negative>
>>> Open positions remaining: 0
```

### Step 13: Verify No Open Positions Remain

```cmd
python -c "import MetaTrader5 as mt5; mt5.initialize(); positions = mt5.positions_get(symbol='XAUUSD'); print('positions:', positions); mt5.shutdown()"
```

Expected: `positions: ()` or `positions: []` (empty).

**If positions remain, MANUALLY CLOSE THEM in MT5 terminal immediately.**

### Step 14: Inspect Reports

```cmd
type data\audit\demo_micro\demo_micro_report.json
type data\audit\demo_micro\demo_micro_report.md
type data\audit\demo_micro\demo_micro_journal.jsonl
```

Verify in `demo_micro_report.json`:
- `"final_verdict": "DEMO_FULL_CYCLE_PASS"`
- `"order_send_called": true`
- `"order_send_attempts": 1`
- `"order_send_success": 1`
- `"close_attempts": 1`
- `"close_success": 1`
- `"open_positions_remaining": 0`

---

## 🧹 Cleanup After Test (MANDATORY)

### Step 15: Clear Arm Token

```cmd
set TITAN_DEMO_MICRO_ARMED=
```

Verify:
```cmd
echo %TITAN_DEMO_MICRO_ARMED%
```

Expected: empty output (`ECHO is off.`).

### Step 16: Restore Config (Disable demo_micro)

Manually edit `config/runtime.yaml` — change `enabled` back to `false`:

```yaml
demo_micro:
  enabled: false       # change back to false
```

OR restore from git (preferred — guaranteed clean):
```cmd
git checkout config/runtime.yaml
```

Verify:
```cmd
python -c "import yaml; cfg = yaml.safe_load(open('config/runtime.yaml', encoding='utf-8')); print('demo_micro.enabled:', cfg['demo_micro']['enabled'])"
```

Expected: `demo_micro.enabled: False`

### Step 17: Verify Hard Gate is BLOCKED Again

```cmd
python scripts/audit/demo_micro_hard_gate.py
```

Expected: `VERDICT: DEMO_MICRO_BLOCKED` with reason `demo_micro.enabled=False (config)`.

### Step 18: Archive Reports (Optional)

If you want to keep the Monday test reports for your records:

```cmd
mkdir data\audit\demo_micro\monday_test
copy data\audit\demo_micro\demo_micro_report.json data\audit\demo_micro\monday_test\
copy data\audit\demo_micro\demo_micro_report.md data\audit\demo_micro\monday_test\
copy data\audit\demo_micro\demo_micro_journal.jsonl data\audit\demo_micro\monday_test\
```

To restore fresh reports for next session:
```cmd
python scripts/audit/demo_micro_hard_gate.py
python scripts/audit/fundednext_demo_micro_full_cycle.py --mode DRY_ARM_CHECK_ONLY
```

### Step 19: Final Git Status Check

```cmd
git status
```

Expected: `nothing to commit, working tree clean` (if you didn't archive reports)
OR only `data/audit/demo_micro/` files modified (if you ran the test).

**Do NOT commit `config/runtime.yaml` with `demo_micro.enabled: true`.**

---

## 🚨 Emergency Stop Instructions

### How to Stop the Script Mid-Run

- Press `Ctrl+C` in the CMD window
- OR set the emergency stop env var in another CMD window:

```cmd
set TITAN_DEMO_MICRO_EMERGENCY_STOP=1
```

The monitor loop checks this env var every ~1 second and triggers close on next iteration.

### Force-Close Watchdog Behavior

The harness monitors the open position and triggers close when ANY of the following occur:
- `--max-hold-seconds` reached (60s in this test)
- `--max-duration-minutes` reached (5 min absolute cap)
- Floating loss exceeds `max_total_loss_pct` (0.50% default)
- Kill switch escalates to `HALT_NEW_TRADES`, `FLATTEN_ONLY`, or `EMERGENCY_STOP`
- `TITAN_DEMO_MICRO_EMERGENCY_STOP=1` env var is set
- Position disappears externally (closed by operator in MT5)

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

---

## 🔒 Safety Guarantees (Verified by Tests)

| Rule | Enforcement | Test |
|---|---|---|
| DEMO account only | Hard gate + execute double-checks `trade_mode == 0` | `test_87_no_order_send_on_non_demo_account` |
| Max lot 0.01 | Config + hard gate + execute explicit check | `test_63_blocks_lot_over_max` |
| Max 1 open position | Config + harness refuses if existing position found | `test_64_blocks_existing_open_position` |
| Max 1 trade per run | Config + harness hard cap (always sends exactly 1) | `test_65_sends_exactly_one_open_order` |
| No duplicate orders | Open order_send called exactly once (never retried) | `test_66_does_not_duplicate_open_order` |
| Force-close on end | Watchdog + config + close policy | `test_42_force_close_max_duration_config` |
| No martingale/grid/averaging | Not implemented — impossible | `test_36_no_martingale_grid_averaging` |
| No lot escalation | Hard cap 0.01, no `lot *= 2` logic | `test_37_no_lot_escalation` |
| Arm token required | `TITAN_DEMO_MICRO_ARMED=1` env var checked first | `test_86_no_order_send_without_arm` |
| Hard gate required | `DEMO_MICRO_ARMED` verdict checked second | `test_84_no_order_send_without_hard_gate_armed` |
| Z AI cannot execute | Z AI env has no MetaTrader5 — `_get_mt5()` returns None | `test_89_z_ai_never_runs_live_mt5` |
| Weekend blocked | `allow_weekend: false` + `market_open` check | hard gate check #11 |
| High spread blocked | `max_spread_usd: 1.0` + execute explicit check | hard gate check + execute spread check |
| Stale tick blocked | Execute checks tick age < 60s | execute tick freshness check |
| Symbol not visible | Execute checks `symbol_info().visible` and calls `symbol_select` | execute symbol check |
| Position sync verified | Execute verifies exactly one matching position before monitoring | `test_73_position_sync_success` |
| Close uses opposite side | BUY→SELL, SELL→BUY (same volume) | `test_68_buy_close_uses_sell`, `test_69_sell_close_uses_buy` |
| Never PASS with open position | `open_positions_remaining == 0` required for PASS | `test_72_open_position_remaining_not_pass` |

---

## 📊 What to Send to Z AI After Monday Test

After completing the Monday DEMO micro test, send Z AI the following files:

1. `data/audit/demo_micro/demo_micro_report.json` — main report
2. `data/audit/demo_micro/demo_micro_report.md` — markdown summary
3. `data/audit/demo_micro/demo_micro_journal.jsonl` — full event journal
4. `data/audit/demo_micro/demo_micro_hard_gate_report.json` — hard gate results

**In your message, include:**
- Did `final_verdict` show `DEMO_FULL_CYCLE_PASS`?
- What was the `net_pnl` value?
- Were there any issues during the test?
- Did the position close cleanly within 60 seconds?
- Were there any unexpected errors in the journal?

Z AI will analyze the results and recommend next steps (e.g., wiring governance into live trade_loop in a future sprint).

---

## 📚 Related Documentation

- `docs/SPRINT_9_9_DEMO_MICRO_OPERATOR_RUNBOOK.md` — original operator runbook (Sprint 9.9.3)
- `data/audit/stress_loss/governance_robustness_report.md` — Sprint 9.9.3.4 robustness validation
- `data/audit/stress_loss/governance_calibration_report.md` — Sprint 9.9.3.3 calibration results
- `data/audit/stress_loss/stress_loss_root_cause_report.md` — Sprint 9.9.3 stress loss audit

---

## ⚠️ Final Reminder

**This runbook prepares for ONE controlled 0.01 DEMO micro lifecycle.**

- Open → Sync → Controlled Close → Report
- That's it. No more, no less.
- Do not attempt multiple runs in one session.
- Do not increase lot size.
- Do not increase max trades.
- Do not leave `demo_micro.enabled: true` after the test.
- Do not leave `TITAN_DEMO_MICRO_ARMED=1` set after the test.

**Once the Monday proof passes**, Z AI can proceed to wire governance into the live trade_loop in a future sprint — but only after explicit operator approval.
