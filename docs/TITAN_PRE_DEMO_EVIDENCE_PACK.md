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
