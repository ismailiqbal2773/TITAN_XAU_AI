# TITAN XAU AI - Sprint 9.9.3.45.7 Final Managed Demo Proof Checklist

**Sprint:** 9.9.3.45.7 (PROOF sprint, not a feature sprint)
**Baseline commit:** `c56b132 fix(demo): enforce continuous managed monitoring and trailing apply gates`
**Sprint goal:** Validate one final local managed demo proof run on the operator's Windows MT5 MetaQuotes-Demo account, then produce RC decision: `DEMO_FUNCTIONAL_RC_READY` or `DEMO_FUNCTIONAL_RC_BLOCKED`.

---

## CRITICAL SAFETY RULES

**Z AI MUST NOT:**
- Run `--execute-and-monitor`
- Run `--execute-once`
- Run `--apply-once`
- Call `mt5.order_send`
- Modify positions
- Enable live trading
- Use real account
- Use FundedNext/FBS/unknown brokers
- Increase lot above 0.01
- Allow more than one open position
- Add martingale/grid/averaging
- Retrain or replace models
- Change strategy/model

**Only the local Windows operator may run `--execute-and-monitor`** on the MetaQuotes-Demo account.

**Allowed lot policy (future, NOT this proof):**
- equity-based position sizing (later)
- volatility-adjusted sizing (later)
- confidence-adjusted sizing (later)
- drawdown-reduced sizing (later)
- **Current proof: fixed 0.01 lot only**

**Forbidden (forever):**
- loss-after-loss lot increase
- martingale multiplier
- grid multiplier
- averaging-down multiplier
- recovery multiplier

---

## OPERATOR LOCAL PROOF SEQUENCE

### Step 1: Pull latest

```cmd
cd /d "D:\Forex project\TITAN_XAU_AI"
myenv\Scripts\activate
git pull --ff-only origin main
git log --oneline -5
git status
```

**Expected top commit:**
```
c56b132 fix(demo): enforce continuous managed monitoring and trailing apply gates
```

**Expected `git status`:** clean working tree (no modifications).

If `git pull` fails or `git status` shows modifications: **STOP. Do not execute.**

---

### Step 2: Passive safety checks

Run all of these BEFORE creating a token or executing. If ANY fails, do NOT execute.

#### 2a. Passive MT5 position read

```cmd
python -c "import MetaTrader5 as mt5; mt5.initialize(); pos=mt5.positions_get(symbol='XAUUSD') or []; print('open_positions=', len(pos)); [print(p.ticket,p.symbol,p.volume,p.price_open,p.sl,p.tp,p.magic,p.comment,p.profit) for p in pos]; mt5.shutdown()"
```

**Expected:** `open_positions= 0`

If `open_positions > 0`: **STOP.** Close any orphan positions manually via MT5 terminal before proceeding. Do NOT proceed with stale positions.

#### 2b. Readiness audit

```cmd
python scripts/audit/demo_micro_managed_monitor_readiness_audit.py
```

**Required verdict:** `MANAGED_MONITOR_READY` (17 OK checks, 0 blockers)

#### 2c. Simulations (4 scenarios)

```cmd
python scripts/operator/simulate_managed_trailing_path.py --scenario loss
python scripts/operator/simulate_managed_trailing_path.py --scenario breakeven
python scripts/operator/simulate_managed_trailing_path.py --scenario trailing
python scripts/operator/simulate_managed_trailing_path.py --scenario profit-lock
```

**Required:**
- `loss` => `SIMULATION_HOLD` / action `HOLD`
- `breakeven` => `SIMULATION_MODIFY` / action `MOVE_TO_BREAKEVEN`
- `trailing` => `SIMULATION_MODIFY` / action `TRAIL`
- `profit-lock` => `SIMULATION_MODIFY` / action `PROFIT_LOCK`
- All scenarios: `tp_preserved=True`, `favorable=True`, `no_widening=True`

#### 2d. Managed trade safe-mode checks

```cmd
python scripts/operator/run_managed_demo_micro_trade.py --check-only
python scripts/operator/run_managed_demo_micro_trade.py --dry-arm
python scripts/operator/run_managed_demo_micro_trade.py --build-request
python scripts/operator/manage_demo_micro_position.py --check-only
python scripts/operator/manage_demo_micro_position.py --preview-trailing
```

**Required:**
- `check-only` => `MANAGED_DEMO_MICRO_READY`
- `dry-arm` => `MANAGED_DEMO_MICRO_READY`
- `build-request` => `PASS` (executable_status = `EXECUTABLE_WITH_PROTECTIVE_SL_TP`)
- `manage check-only` => `MANAGE_CHECK_PASS`
- `preview-trailing` => `NO_POSITION_FOUND` (found=0, verified=0)

**Note:** On Z AI (Linux) environment these return `MANAGED_DEMO_MICRO_BLOCKED` due to environment drift gate. On the local Windows operator machine with the frozen environment signature, they should return `MANAGED_DEMO_MICRO_READY` and `PASS`.

If any check returns `BLOCKED` or `FAIL`: **STOP. Do NOT execute.**

---

### Step 3: Create fresh local operator token

Run ONLY after all gates in Step 2 pass:

```cmd
python scripts/operator/create_local_operator_execution_token.py --symbol XAUUSD --lot 0.01 --broker MetaQuotes-Demo --expiry-minutes 10
```

**Expected:** Token created at `data/runtime/operator_tokens/demo_micro_execute_once.token` with 10-minute expiry.

**Token contains:** created_utc, expires_utc, git_commit, machine_signature, symbol, lot, broker, token_hash, consumed=False. **No secrets.**

If token creation fails: **STOP. Do NOT execute.**

---

### Step 4: Run exactly one managed demo proof trade

**Run ONLY locally on the Windows operator machine.**

```cmd
python scripts/operator/run_managed_demo_micro_trade.py --execute-and-monitor --i-understand-demo-risk --confirm-symbol XAUUSD --confirm-lot 0.01 --confirm-broker MetaQuotes-Demo --confirm-one-order-only --confirm-not-live --confirm-environment-locked --confirm-model-parity-pass --confirm-local-operator --confirm-managed-trailing --monitor-duration-minutes 30 --monitor-interval-seconds 5
```

**Hard requirements during execution:**

| Requirement | How to verify |
|---|---|
| Exactly one `order_send` for entry | Check `order_send_called=True`, `order_send_retcode=10009`, single receipt write |
| No second entry | Receipt written once; no duplicate receipts |
| No retry entry | `execution_attempted=True` only once |
| Monitor stays attached while position open | `monitor_iterations > 1` if position stayed open beyond one interval |
| Monitor iterations recorded | `monitor_iterations` field present in managed_trade_report.json |
| HOLD does not modify | `sl_modify_attempts` empty during HOLD evaluations |
| If trigger reached, SLTP modify attempted exactly once per decision step | Each `sl_modify_attempts[i]` corresponds to one decision step |
| TP preserved | Every `sl_modify_attempts[i].tp_preserved=True` |
| SL favorable-only | Every `sl_modify_attempts[i].new_sl >= old_sl` (BUY) or `<=` (SELL) |
| No widening SL | `UNFAVORABLE_SL_BLOCKED` / `SL_WIDENING_BLOCKED` never in blockers |
| No martingale/grid/averaging | No lot increase above 0.01; no second position |

**If execution fails (any of above violated):** Document the failure, do NOT retry execution, run Step 5 evidence collection anyway, return `DEMO_FUNCTIONAL_RC_BLOCKED`.

---

### Step 5: Post-trade evidence collection

After `--execute-and-monitor` returns (whether success or failure), run:

#### 5a. Read receipt

```cmd
type data\runtime\demo_micro_execution_receipt.json
```

**Required fields to verify:**
- `success: true`
- `execution_mode: "execute_and_monitor"`
- `symbol: "XAUUSD"`, `volume: 0.01`, `side: "BUY"` (or SELL)
- `request_magic: 202619`, `request_comment: "TITAN_DEMO_MICRO"`
- `requested_sl` and `requested_tp` (non-null, > 0)
- `order_send_result_retcode: 10009`
- `order_send_result_comment: "TRADE_RETCODE_DONE"`
- `order_send_result_order` (non-null if broker returned it)
- `order_send_result_deal` (non-null if broker returned it)
- `detected_position_ticket` (non-null after detection)
- `detected_position_identifier` (non-null after detection)
- `position_open_verified: true` (if position was open)
- `position_detected: true`

#### 5b. Read managed trade report

```cmd
type data\audit\demo_micro_execution\managed_trade_report.md
```

**Required:**
- `mode: execute_and_monitor`
- `verdict: MANAGED_DEMO_MICRO_STARTED` (if position still open at timeout) OR `MANAGED_DEMO_MICRO_COMPLETED` (if position closed) OR `MANAGED_DEMO_MICRO_COMPLETED_WITH_WARNINGS` (if position disappeared)
- `order_send_called: True`
- `order_send_retcode: 10009`
- `receipt_written: True`
- `position_detected: True`
- `monitor_started: True`
- `monitor_iterations` field present
- `monitor_stop_reason` field present (`TIMEOUT`, `POSITION_CLOSED`, `KILL_SWITCH_BLOCKED`, `ERROR`, or `POSITION_DISAPPEARED_WITHOUT_HISTORY`)
- `final_position_status` field present (`OPEN`, `CLOSED`, or `UNKNOWN`)
- `final_position_source` field present

#### 5c. Diagnose latest receipt

```cmd
python scripts/operator/diagnose_latest_execution_receipt.py
type data\audit\demo_micro_execution\latest_receipt_diagnostic.md
```

**Required verdict:** `RECEIPT_RESOLVED_OPEN` (if position still open) OR `RECEIPT_RESOLVED_CLOSED` (if position closed) OR `RECEIPT_PENDING_HISTORY` (if open but history not yet visible)

**BLOCKED verdicts:** `RECEIPT_NOT_FOUND`, `RECEIPT_INCONSISTENT` => RC_BLOCKED

#### 5d. Forensics (no explicit position-id; let it match by receipt)

```cmd
python scripts/operator/collect_demo_micro_trade_forensics.py --days 30 --symbol XAUUSD --magic 202619 --comment TITAN_DEMO_MICRO
type data\audit\demo_micro_execution\post_trade_forensics.md
```

**Required:**
- `verdict: DEMO_MICRO_FORENSICS_COMPLETE` or `DEMO_MICRO_FORENSICS_COMPLETE_WITH_WARNINGS`
- `fallback_used: False`
- `match_method` includes `receipt_` or `magic_` or `comment_` (not `likely_`)
- `entry_deal`, `exit_deal` (if closed), `entry_sl`, `entry_tp` populated

**BLOCKED verdicts:** `DEMO_MICRO_FORENSICS_INCOMPLETE` with `fallback_used=True` => RC_BLOCKED

#### 5e. Manage position preview (post-trade)

```cmd
python scripts/operator/manage_demo_micro_position.py --preview-trailing
type data\audit\demo_micro_execution\manage_position_report.md
```

**Required:**
- If position still open: `verdict: PREVIEW_GENERATED` with `verified_count=1`, `found_count=1`, `disappeared_tickets=[]`
- If position closed: `verdict: NO_POSITION_FOUND` with `found_count=0`, `verified_count=0`
- If position disappeared between scans: `verdict: POSITION_CLOSED_BEFORE_PREVIEW` with `disappeared_tickets` populated

**BLOCKED:** `PREVIEW_GENERATED` with `verified_count=0` (stale preview) => RC_BLOCKED

#### 5f. Final passive MT5 position read

```cmd
python -c "import MetaTrader5 as mt5; mt5.initialize(); pos=mt5.positions_get(symbol='XAUUSD') or []; print('open_positions=', len(pos)); [print(p.ticket,p.symbol,p.volume,p.price_open,p.sl,p.tp,p.magic,p.comment,p.profit) for p in pos]; mt5.shutdown()"
```

**Required:**
- If `final_position_status=OPEN`: `open_positions=1` with matching ticket
- If `final_position_status=CLOSED`: `open_positions=0`
- If `final_position_status=UNKNOWN`: investigate (RC_BLOCKED)

---

## RC DECISION RULES

### Return `DEMO_FUNCTIONAL_RC_READY` only if ALL of:

| # | Requirement | Source |
|---|---|---|
| 1 | Execution receipt exists | `data/runtime/demo_micro_execution_receipt.json` |
| 2 | Receipt resolves open or closed | `diagnose_latest_execution_receipt.py` verdict |
| 3 | Forensics matches latest receipt/position | `collect_demo_micro_trade_forensics.py` match_method |
| 4 | No old-trade fallback used | `fallback_used: False` in forensics findings |
| 5 | `monitor_started=True` | managed_trade_report.json |
| 6 | `monitor_iterations > 1` if position stayed open beyond one interval | managed_trade_report.json |
| 7 | `final_position_status` is truthful | Cross-check with final `positions_get` |
| 8 | If trigger reached, SL modification event recorded | `sl_modify_attempts` non-empty |
| 9 | If trigger not reached, HOLD events recorded correctly | `monitor_events` contain HOLD entries |
| 10 | TP preserved | Every `sl_modify_attempts[i].tp_preserved=True` |
| 11 | SL favorable-only | Every `sl_modify_attempts[i].new_sl >= old_sl` (BUY) or `<=` (SELL) |
| 12 | No open orphan position remains after close, or if still open, monitor/final status says OPEN with current positions_get evidence | Final `positions_get` count vs `final_position_status` |
| 13 | No martingale/grid/averaging | No lot > 0.01; no second position; no recovery stacking in events |
| 14 | No more than one position | Final `positions_get` count <= 1 |
| 15 | No real account | `account_trade_mode: 0` in receipt |
| 16 | MetaQuotes-Demo only | `account_server` contains `MetaQuotes-Demo` |
| 17 | 0.01 lot only | `volume: 0.01` in receipt |

### Return `DEMO_FUNCTIONAL_RC_BLOCKED` if ANY of:

| # | Failure | Source |
|---|---|---|
| 1 | Receipt missing | `diagnose_latest_execution_receipt.py` returns `RECEIPT_NOT_FOUND` |
| 2 | Receipt cannot resolve | `RECEIPT_INCONSISTENT` |
| 3 | Forensics uses old trade fallback | `fallback_used: True` |
| 4 | Monitor exits after one HOLD while open | `monitor_iterations == 1` AND `final_position_status == OPEN` AND `monitor_stop_reason != POSITION_CLOSED` |
| 5 | Final OPEN without positions_get evidence | `final_position_status=OPEN` but final `positions_get` count = 0 |
| 6 | SL modify fails when trigger is reached | `sl_modify_attempts[i].modify_success=False` |
| 7 | Stale preview appears | `preview-trailing` returns `PREVIEW_GENERATED` with `verified_count=0` |
| 8 | Open orphan position remains unmanaged | Final `positions_get` count > 0 but `final_position_status != OPEN` |
| 9 | Any broker/account/risk gate fails | Receipt shows non-DEMO trade_mode or non-MetaQuotes-Demo server |
| 10 | Lot > 0.01 | Receipt `volume > 0.01` |
| 11 | More than one position | Final `positions_get` count > 1 |
| 12 | Martingale/grid/averaging detected | Any lot increase or second position |

---

## FINAL REPORT TEMPLATE

After completing the proof sequence, fill out this report:

```
Sprint 9.9.3.45.7 - Final Managed Demo Proof Report
====================================================

Baseline commit: c56b132 fix(demo): enforce continuous managed monitoring and trailing apply gates
Operator machine: <Windows machine signature>
MT5 server: MetaQuotes-Demo
Account trade_mode: 0 (DEMO)

Pre-trade:
  open_positions: 0
  readiness_audit_verdict: MANAGED_MONITOR_READY
  simulation_loss: SIMULATION_HOLD / HOLD
  simulation_breakeven: SIMULATION_MODIFY / MOVE_TO_BREAKEVEN
  simulation_trailing: SIMULATION_MODIFY / TRAIL
  simulation_profit_lock: SIMULATION_MODIFY / PROFIT_LOCK
  check_only_verdict: MANAGED_DEMO_MICRO_READY
  dry_arm_verdict: MANAGED_DEMO_MICRO_READY
  build_request_verdict: PASS
  manage_check_only_verdict: MANAGE_CHECK_PASS
  preview_trailing_verdict: NO_POSITION_FOUND
  token_created: yes/no

Execute-and-monitor:
  verdict: <MANAGED_DEMO_MICRO_STARTED|COMPLETED|COMPLETED_WITH_WARNINGS|BLOCKED|FAILED>
  order_send_retcode: 10009
  receipt_written: yes
  receipt_path: data/runtime/demo_micro_execution_receipt.json

Receipt diagnostic:
  verdict: <RECEIPT_RESOLVED_OPEN|RECEIPT_RESOLVED_CLOSED|RECEIPT_PENDING_HISTORY|RECEIPT_NOT_FOUND|RECEIPT_INCONSISTENT>
  latest_position_id: <ticket>
  latest_deal: <deal_ticket>
  latest_order: <order_ticket>

Monitor lifecycle:
  monitor_started: yes
  monitor_iterations: <N>
  monitor_duration_seconds: <S>
  monitor_stop_reason: <TIMEOUT|POSITION_CLOSED|KILL_SWITCH_BLOCKED|ERROR|POSITION_DISAPPEARED_WITHOUT_HISTORY>
  final_position_status: <OPEN|CLOSED|UNKNOWN>
  final_position_source: <positions_get|history_deals_get|positions_get_empty_history_empty>
  final_positions_get_count: <0 or 1>
  final_history_match_found: yes/no

SL modifications:
  HOLD_events_count: <N>
  MODIFY_attempts_count: <N>
  breakeven_modify_success: yes/no/not-triggered
  trailing_modify_success: yes/no/not-triggered
  profit_lock_modify_success: yes/no/not-triggered
  TP_preserved: yes
  favorable_only: yes

Forensics:
  verdict: <DEMO_MICRO_FORENSICS_COMPLETE|COMPLETE_WITH_WARNINGS|INCOMPLETE|BLOCKED>
  match_method: <receipt_...|magic_...|comment_...|explicit_...|likely_...>
  fallback_used: no
  entry_deal: <deal_ticket>
  exit_deal: <deal_ticket or null>
  entry_price: <price>
  entry_sl: <sl>
  entry_tp: <tp>
  exit_price: <price or null>
  realized_pl: <profit or null>
  sl_hit_detected: yes/no
  sl_modification_events: <N>

Final state:
  final_open_positions: 0 or 1
  unrealized_pl: <profit or null>

RC verdict: <DEMO_FUNCTIONAL_RC_READY|DEMO_FUNCTIONAL_RC_BLOCKED>

Pushed: yes/no (no code changes needed for proof sprint)
Working tree clean: yes/no
```

---

## Z AI ROLE (this sprint)

Z AI does NOT run execute-and-monitor. Z AI does NOT call mt5.order_send. Z AI's role is:

1. Verify the repo state matches the baseline (`c56b132`).
2. Run all passive Z AI-safe checks (readiness audit, simulations, check-only, dry-arm, build-request, manage check, preview-trailing) to confirm everything still works in the Z AI environment.
3. Confirm all relevant test suites pass (no regressions).
4. Provide this checklist to the operator.
5. Wait for the operator to run the local proof sequence on Windows and report results.
6. Apply the RC decision rules to the operator's reported evidence.
7. Return `DEMO_FUNCTIONAL_RC_READY` or `DEMO_FUNCTIONAL_RC_BLOCKED` based on operator's evidence.

If no code changes are needed (which is the expected case for a proof sprint), Z AI does NOT create a new commit.
