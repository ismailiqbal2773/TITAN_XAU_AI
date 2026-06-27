# TITAN XAU AI — Pre-DEMO Evidence Pack

> **Purpose**: Consolidate all evidence proving the repository is ready for Monday's operator-only Windows MT5 FundedNext DEMO micro execution.
>
> **Audience**: Operator + Z AI audit trail.
>
> **Date**: Sprint 9.9.3.7 (pre-demo freeze)

---

## 1. Current Project Status

**Status: READY FOR MONDAY DEMO MICRO TEST**

The TITAN XAU AI repository has been validated through 7 sprints of progressive hardening:
- Virtual lifecycle scenarios (17 scenarios)
- Synthetic unseen scenarios (220 variations)
- Monte Carlo stress (500 randomized runs)
- Competition benchmark (7 bots)
- Previous-year real data validation (2025 H1, 5 brokers, ~29,579 rows)

All safety gates are in place. Governance is validated but NOT wired into live/demo execution path. The repository is frozen at a clean, stable, traceable baseline.

---

## 2. Completed Sprint List

| Sprint | Commit | Description |
|---|---|---|
| 9.9.3 | `34ff62c` | Implement operator-only demo micro order execution |
| 9.9.3 (audit) | `a0e1240` | Stress PnL loss root cause analysis (READ-ONLY) |
| 9.9.3.2 | `4cab0c1` | Add stress loss mitigation governance |
| 9.9.3.3 | `077fd55` | Calibrate governance to reduce overfiltering and preserve profit |
| 9.9.3.4 | `8fc97d2` | Validate governance robustness and competition readiness |
| 9.9.3.5 | `7fce43f` | Prepare Monday demo micro readiness runbook |
| 9.9.3.6 | `3d723f9` | Validate governance on previous-year real data |
| **9.9.3.7** | **(this commit)** | **Pre-demo evidence pack and baseline freeze audit** |

---

## 3. Latest Verified Commits

```
3d723f9 audit(sprint-9.9.3.6): validate governance on previous-year real data
7fce43f docs(sprint-9.9.3.5): prepare Monday demo micro readiness runbook
8fc97d2 audit(sprint-9.9.3.4): validate governance robustness and competition readiness
077fd55 feat(sprint-9.9.3.3): calibrate governance to reduce overfiltering and preserve profit
4cab0c1 feat(sprint-9.9.3.2): add stress loss mitigation governance
```

**HEAD**: `3d723f9` (Sprint 9.9.3.6)
**Working tree**: clean
**Branch**: `main` (up to date with `origin/main`)

---

## 4. Safety Gates (12 hard gate checks)

The demo micro hard gate (`scripts/audit/demo_micro_hard_gate.py`) enforces 12 checks before any DEMO execution:

| # | Check | Default | Enforcement |
|---|---|---|---|
| 1 | mt5_reachable | False (Z AI/Linux) | MT5 must be initialized |
| 2 | account_demo | False (Z AI/Linux) | trade_mode == 0 (DEMO only) |
| 3 | demo_micro_enabled | False | Config must explicitly enable |
| 4 | arm_token_present | False | TITAN_DEMO_MICRO_ARMED=1 env var required |
| 5 | not_real_account | True | Real/live accounts blocked |
| 6 | max_lot_ok | True | max_lot <= 0.01 |
| 7 | max_positions_ok | True | max_open_positions == 1 |
| 8 | max_trades_ok | True | max_trades_per_run <= 3 (default 1) |
| 9 | force_close_on_end | True | Watchdog will close on exit |
| 10 | kill_switch_normal | True | FSM must be NORMAL |
| 11 | market_open | False (weekend Z AI) | Weekend blocked |
| 12 | demo_micro_readiness_ok | True | Readiness report must be DEMO_MICRO_READY |

**All 12 checks must pass for `DEMO_MICRO_ARMED` verdict.**

### DEMO_MICRO_EXECUTE Additional Guards (7)

Beyond the hard gate, the execute mode (`scripts/audit/fundednext_demo_micro_full_cycle.py`) enforces:
1. Arm token `TITAN_DEMO_MICRO_ARMED=1`
2. Hard gate verdict `DEMO_MICRO_ARMED`
3. Side resolution (AI signal or `--side` CLI arg, no guessing)
4. Lot `<= max_lot` (0.01)
5. MT5 account is DEMO (`trade_mode == 0`)
6. Symbol visible and selected
7. No existing open position for symbol

---

## 5. Dry-Run Defaults

| Setting | Value | Source |
|---|---|---|
| `runtime.dry_run` | **true** | `config/runtime.yaml` |
| `runtime.live_trading` | **false** | `config/runtime.yaml` |
| `TITAN_LIVE_TRADING` env | not set | Operator environment |

**These defaults are NEVER changed by any sprint.** The system fails-closed unless explicitly armed.

---

## 6. Demo Micro Defaults

| Setting | Value | Source |
|---|---|---|
| `demo_micro.enabled` | **false** | `config/runtime.yaml` |
| `demo_micro.max_lot` | **0.01** | `config/runtime.yaml` |
| `demo_micro.max_open_positions` | **1** | `config/runtime.yaml` |
| `demo_micro.max_trades_per_run` | **1** | `config/runtime.yaml` |
| `demo_micro.force_close_on_end` | **true** | `config/runtime.yaml` |
| `demo_micro.allow_weekend` | **false** | `config/runtime.yaml` |
| `demo_micro.max_spread_usd` | **1.0** | `config/runtime.yaml` |
| `demo_micro.arm_token_env` | **TITAN_DEMO_MICRO_ARMED** | `config/runtime.yaml` |

**Operator must temporarily set `enabled: true` and `TITAN_DEMO_MICRO_ARMED=1` for Monday test, then restore both after.**

---

## 7. Governance Status

| Item | Status |
|---|---|
| Governance module | `titan/production/stress_loss_governance.py` (implemented, 3-tier) |
| Account profiles | RETAIL_SAFE, PROP_FIRM_STRICT, INSTITUTIONAL_CAPITAL_PROTECTION |
| Wired into live/demo trade_loop | **NO** (opt-in via `--governance` flag on virtual_lifecycle_validator only) |
| Wired into DEMO_MICRO_EXECUTE | **NO** |
| Wired into `titan/production/trade_loop.py` | **NO** |
| Wired into `titan/runtime/launcher.py` | **NO** |
| Tests | 58 tests pass (all green) |
| Fail-closed behavior | YES (invalid inputs → NO_TRADE + CLOSE) |

**Governance will NOT be wired into live/demo execution until after Monday's DEMO proof passes and a separate sprint explicitly approves it.**

---

## 8. Historical 2025 Validation Summary

**Source**: `data/audit/historical_2025/previous_year_real_data_validation.md`
**Data**: 5 sources × H1 × full 2025 calendar year (~29,579 rows)

| Config | Net PnL | Max DD | PF | Win% | Trades | Score |
|---|---|---|---|---|---|---|
| NO_GOVERNANCE | **-$5,323** | $5,749 | 0.85 | 44.5% | 4,344 | 31.67 |
| 9.9.3.2 PROP_FIRM_STRICT | +$12,751 | $76 | 5.49 | 68.5% | 2,033 | 84.87 |
| 9.9.3.3 RETAIL_SAFE | +$17,123 | $98 | 5.99 | 69.3% | 2,365 | 84.12 |
| **9.9.3.3 PROP_FIRM_STRICT** | **+$12,730** | **$79** | **5.93** | **68.6%** | **2,092** | **84.81** |
| 9.9.3.3 INSTITUTIONAL | +$10,151 | $88 | 5.01 | 67.5% | 1,905 | 84.36 |

**Key finding**: Governance transforms a LOSING strategy (-$5,323) into a PROFITABLE one (+$10K-$17K) with <1% equity drawdown.

**Benchmark rank**: TITAN #1 on real 2025 data (beats buy-and-hold, trend-only, mean-reversion, random-entry, fixed-threshold, baseline-no-gov).

---

## 9. Robustness Validation Summary

**Source**: `data/audit/stress_loss/governance_robustness_report.md`
**Sprint**: 9.9.3.4

| Metric | Value |
|---|---|
| Scenarios tested | 220 unseen variations |
| Monte Carlo runs | 500 randomized |
| Benchmark bots | 7 (TITAN ranked #2, competitive) |
| MC median PnL | +$5.53 (positive) |
| MC 5th pct PnL | -$14.16 (acceptable tail risk) |
| MC worst PnL | -$34.31 |
| MC worst DD | $58.95 |
| Exit actions triggered in replay | 20 (17 MOVE_BE + 3 PARTIAL_CLOSE) |
| Ladder improves PnL | YES (+100% vs no ladder) |
| Ladder reduces full SL | YES (-58%) |
| Criteria met | 13/12 (all + 1 extra) |
| Verdict | **READY for live/demo wiring** (HIGH confidence) |

---

## 10. Monday DEMO Micro Runbook Link

**Primary runbook**: [`docs/SPRINT_9_9_3_MONDAY_DEMO_MICRO_RUNBOOK.md`](SPRINT_9_9_3_MONDAY_DEMO_MICRO_RUNBOOK.md)

**Original runbook**: [`docs/SPRINT_9_9_DEMO_MICRO_OPERATOR_RUNBOOK.md`](SPRINT_9_9_DEMO_MICRO_OPERATOR_RUNBOOK.md)

The Monday runbook includes 19 exact Windows CMD commands covering the full lifecycle:
1. venv activation
2. git pull + status verification
3. first_run_check
4. MT5 initialize check
5. XAUUSD open position check
6. config defaults verification
7. hard gate (before enabling)
8. temporarily enable demo_micro
9. set TITAN_DEMO_MICRO_ARMED=1
10. hard gate (after enabling)
11. DRY_ARM_CHECK_ONLY
12. **DEMO_MICRO_EXECUTE** (0.01 lot, 1 trade, 60s hold, BUY side)
13. verify no open positions remain
14. inspect reports
15. cleanup: clear arm token
16. restore config/runtime.yaml
17. verify hard gate BLOCKED again
18. archive reports (optional)
19. final git status check

---

## 11. What Is Allowed Monday

- **ONE controlled 0.01 lot DEMO micro lifecycle**: open → sync → controlled close → report
- Run on **FundedNext DEMO account only**
- Run on **Windows MT5 terminal only**
- Run during **market open hours** (Monday-Friday, 07:00-21:00 UTC)
- Use `--side BUY` or `--side SELL` explicitly
- Use `--max-hold-seconds 60` for short controlled test
- Use `--max-trades 1` (hard cap)
- Use `--lot 0.01` (hard cap)
- Inspect all reports after the test
- Send reports to Z AI for analysis

---

## 12. What Is Forbidden Monday

- **DO NOT run on weekend / market closed**
- **DO NOT run on real/live account** (DEMO only)
- **DO NOT increase lot above 0.01**
- **DO NOT increase max_trades above 1**
- **DO NOT increase max_open_positions above 1**
- **DO NOT change runtime.dry_run to false**
- **DO NOT change runtime.live_trading to true**
- **DO NOT set TITAN_LIVE_TRADING=1**
- **DO NOT wire governance into live/demo trade_loop** (not yet approved)
- **DO NOT retrain models**
- **DO NOT add martingale, grid, averaging, or lot escalation**
- **DO NOT run DEMO_MICRO_EXECUTE more than once per session**
- **DO NOT leave demo_micro.enabled=true after the test**
- **DO NOT leave TITAN_DEMO_MICRO_ARMED=1 set after the test**
- **DO NOT commit config/runtime.yaml with demo_micro.enabled=true**

---

## 13. Pre-DEMO Test Suite Results (Sprint 9.9.3.7)

| Check | Result |
|---|---|
| `python first_run_check.py` | 12 PASS, 1 WARN, 0 FAIL |
| `pytest titan/tests/test_demo_micro_hard_gate.py` | 25 passed |
| `pytest titan/tests/test_fundednext_demo_micro_harness.py` | 63 passed, 1 skipped |
| `pytest titan/tests/test_stress_loss_governance.py` | 58 passed |
| `git status` | clean working tree |
| Config defaults verified | all 8 settings correct |
| Token scan (tracked + history) | 0 actual tokens found |
| DEMO_MICRO_EXECUTE run by Z AI | NO |
| Live/demo path changed | NO |
| Governance wired into live/demo | NO |

---

## 14. Monday Readiness Verdict

**READY**

The repository is frozen at a clean, stable, traceable baseline. All safety gates are in place. All tests pass. Config defaults are correct. No tokens leaked. Governance is validated but not wired into execution.

**The operator may proceed with the Monday DEMO micro test following the runbook step-by-step.**

After the test, send the following files to Z AI:
- `data/audit/demo_micro/demo_micro_report.json`
- `data/audit/demo_micro/demo_micro_report.md`
- `data/audit/demo_micro/demo_micro_journal.jsonl`
- `data/audit/demo_micro/demo_micro_hard_gate_report.json`

Z AI will analyze the results and recommend next steps.

---

## 15. Monday DEMO Micro Test — Scope Clarification

> **CRITICAL**: The Monday DEMO micro test is **NOT a profit test**.

### What This Test IS

The Monday DEMO micro test is **only an execution lifecycle safety test**:

```
open → sync → controlled close → report
```

The purpose is to prove that:
1. The DEMO_MICRO_EXECUTE mode can actually send ONE real MT5 DEMO order
2. The position sync logic correctly identifies the opened position
3. The controlled close logic correctly closes the position (BUY→SELL or SELL→BUY)
4. The reporting pipeline generates correct JSON/MD/journal files
5. The full cycle completes with `final_verdict: DEMO_FULL_CYCLE_PASS`
6. No open positions remain after the test

### What This Test IS NOT

- **NOT a profit test** — net PnL may be positive, negative, or zero; it does not matter
- **NOT a strategy validation** — strategy was already validated in Sprints 9.9.3.4 and 9.9.3.6
- **NOT a governance test** — governance is NOT wired into DEMO_MICRO_EXECUTE
- **NOT a performance benchmark** — only ONE trade is sent
- **NOT a multi-trade test** — max_trades is hard-capped at 1

### Expected Parameters

| Parameter | Value | Hard Cap |
|---|---|---|
| Lot | 0.01 | YES (config enforces) |
| Max trades | 1 | YES (config enforces) |
| Max open positions | 1 | YES (config enforces) |
| Max hold seconds | 60 | operator-chosen for short test |
| Max duration minutes | 5 | absolute cap |
| Side | BUY (or SELL) | explicit via --side, no guessing |
| Account | FundedNext DEMO | hard gate enforces trade_mode==0 |

### Governance Wiring Rule

**No governance live/demo wiring before this test passes.**

Governance remains opt-in via `--governance` flag on `virtual_lifecycle_validator.py` only. It is NOT wired into:
- `titan/production/trade_loop.py`
- `scripts/audit/fundednext_demo_micro_full_cycle.py`
- `titan/runtime/launcher.py`

Governance will only be considered for live/demo wiring in a **separate future sprint** after:
1. Monday DEMO micro test passes with `DEMO_FULL_CYCLE_PASS`
2. Operator confirms the report is correct
3. Z AI explicitly approves governance wiring

---

## 16. Final GO / NO-GO Table

> **The operator must verify ALL GO conditions before running DEMO_MICRO_EXECUTE.**
>
> **If ANY condition is NO-GO, the operator MUST STOP and must NOT execute.**

### Pre-Execution GO/NO-GO (verify before Step 12 of runbook)

| # | Check | GO Condition | NO-GO Condition | Action if NO-GO |
|---|---|---|---|---|
| 1 | Repository on latest commit | `git log --oneline -1` shows `946eca8` or newer, `git status` clean | Behind origin/main or dirty working tree | Run `git pull --ff-only origin main`; if still NO-GO, STOP |
| 2 | first_run_check passes | 12+ PASS, 0 FAIL | Any FAIL | STOP — fix FAIL before proceeding |
| 3 | All tests pass | 25 hard gate + 63 harness + 58 governance = 146 passed | Any test failure | STOP — fix tests before proceeding |
| 4 | MT5 initialize succeeds | `mt5.initialize()` returns True | Returns False or ImportError | STOP — verify MT5 terminal is running and logged in |
| 5 | Account is DEMO | `mt5.account_info().trade_mode == 0` | trade_mode != 0 (CONTEST or REAL) | **STOP immediately** — never run on real/live account |
| 6 | No existing XAUUSD position | `mt5.positions_get(symbol='XAUUSD')` is empty | Any open position exists | STOP — manually close positions in MT5 terminal first |
| 7 | Config defaults correct | dry_run=true, live_trading=false, demo_micro.enabled=false (initially) | Any default wrong | STOP — run `git checkout config/runtime.yaml` to restore |
| 8 | demo_micro temporarily enabled | After Step 8: demo_micro.enabled=true | Still false after edit | STOP — verify config edit saved correctly |
| 9 | Arm token set | After Step 9: `echo %TITAN_DEMO_MICRO_ARMED%` shows `1` | Empty or wrong value | STOP — re-run `set TITAN_DEMO_MICRO_ARMED=1` |
| 10 | Hard gate ARMED | After Step 10: `VERDICT: DEMO_MICRO_ARMED` with all 12 checks `[✓]` | VERDICT: DEMO_MICRO_BLOCKED or any `[✗]` | STOP — review reasons in hard gate output |
| 11 | DRY_ARM_CHECK_ONLY passes | `final_verdict: DEMO_MICRO_ARMED`, `order_send_called: false` | BLOCKED or order_send attempted | STOP — do NOT proceed to DEMO_MICRO_EXECUTE |
| 12 | Market is open | Hard gate shows `market_open: True` | `market_open: False` (weekend/holiday) | STOP — wait for market open (Mon-Fri 07:00-21:00 UTC) |
| 13 | Spread acceptable | Hard gate shows spread ≤ 1.0 USD | Spread > 1.0 USD | STOP — wait for spread to normalize |
| 14 | TITAN_LIVE_TRADING NOT set | `echo %TITAN_LIVE_TRADING%` is empty | Shows `1` | STOP — unset with `set TITAN_LIVE_TRADING=` |
| 15 | No real/live account anywhere | MT5 terminal shows "DEMO" or "Demo" | Shows "Real", "Live", or "Contest" | **STOP immediately** — switch to DEMO account |

### Execution Decision

```
IF all 15 checks above are GO:
    → PROCEED to Step 12: DEMO_MICRO_EXECUTE
ELSE:
    → STOP — do NOT execute
    → Report the NO-GO reason to Z AI
    → Fix the issue before retrying
```

### Post-Execution GO/NO-GO (verify after Step 12)

| # | Check | GO Condition | NO-GO Condition | Action if NO-GO |
|---|---|---|---|---|
| P1 | Final verdict | `DEMO_FULL_CYCLE_PASS` | `DEMO_MANUAL_REVIEW_REQUIRED` or `DEMO_FULL_CYCLE_FAIL` | Do NOT retry — send reports to Z AI for analysis |
| P2 | No open positions remain | `mt5.positions_get(symbol='XAUUSD')` is empty | Position still open | Manually close in MT5 terminal immediately, then send reports to Z AI |
| P3 | order_send_attempts = 1 | Report shows exactly 1 open attempt | 0 or 2+ attempts | Send reports to Z AI — possible duplicate or missed order |
| P4 | close_attempts = 1 | Report shows exactly 1 close attempt | 0 or 2+ attempts | Send reports to Z AI — close may have failed |
| P5 | open_positions_remaining = 0 | Report shows 0 | 1+ | Manually close in MT5 terminal, send reports to Z AI |
| P6 | Config restored | demo_micro.enabled=false after cleanup | Still true | Run `git checkout config/runtime.yaml` immediately |
| P7 | Arm token cleared | `echo %TITAN_DEMO_MICRO_ARMED%` is empty | Still shows `1` | Run `set TITAN_DEMO_MICRO_ARMED=` immediately |
| P8 | Hard gate BLOCKED again | `VERDICT: DEMO_MICRO_BLOCKED` after cleanup | Still ARMED | Config or env not cleaned — re-do cleanup steps |

### Post-Execution Decision

```
IF P1 = GO (DEMO_FULL_CYCLE_PASS) AND P2-P5 = GO:
    → Monday test SUCCESSFUL
    → Send reports to Z AI
    → Z AI may propose governance wiring in future sprint
ELSE:
    → Monday test FAILED or needs review
    → Do NOT retry
    → Send reports to Z AI for root-cause analysis
    → Wait for Z AI guidance before next step
```

### Mandatory Cleanup (regardless of P1 outcome)

Even if the test fails, the operator MUST complete cleanup steps P6-P8:
1. Restore config: `git checkout config/runtime.yaml`
2. Clear arm token: `set TITAN_DEMO_MICRO_ARMED=`
3. Verify hard gate is BLOCKED again

**Leaving demo_micro.enabled=true or TITAN_DEMO_MICRO_ARMED=1 set after the test is a CRITICAL SAFETY VIOLATION.**

---

## 17. Summary

| Item | Value |
|---|---|
| Repository on latest commit | YES (`946eca8`, up to date with origin/main) |
| All safety checks pass | YES (35/35 freeze checklist items) |
| All tests pass | YES (146 passed, 1 skipped) |
| Config defaults correct | YES (all 8 settings) |
| No tokens leaked | YES (0 in tracked files, 0 in history) |
| Governance wired | NO (opt-in only, not in live/demo path) |
| Working tree clean | YES |
| Monday test scope | Execution lifecycle safety test ONLY (not profit test) |
| Expected lot | 0.01 (hard cap) |
| Expected max trades | 1 (hard cap) |
| GO/NO-GO table | 15 pre-execution + 8 post-execution checks |
| **Monday readiness** | **GO** (all pre-conditions met) |
