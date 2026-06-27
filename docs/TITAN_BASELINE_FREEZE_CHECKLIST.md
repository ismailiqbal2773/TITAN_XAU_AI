# TITAN XAU AI — Baseline Freeze Checklist

> **Purpose**: Confirm the repository is frozen at a clean, stable, traceable baseline before Monday's DEMO micro test.
>
> **Audience**: Operator + Z AI audit trail.
>
> **Date**: Sprint 9.9.3.7 (pre-demo freeze)

---

## Freeze Checklist (All Items Must Be Verified)

### 1. Config Defaults

| # | Item | Expected | Verified | Method |
|---|---|---|---|---|
| 1.1 | `runtime.dry_run` | `true` | YES | `python -c "import yaml; print(yaml.safe_load(open('config/runtime.yaml'))['runtime']['dry_run'])"` |
| 1.2 | `runtime.live_trading` | `false` | YES | `python -c "import yaml; print(yaml.safe_load(open('config/runtime.yaml'))['runtime']['live_trading'])"` |
| 1.3 | `demo_micro.enabled` | `false` | YES | `python -c "import yaml; print(yaml.safe_load(open('config/runtime.yaml'))['demo_micro']['enabled'])"` |
| 1.4 | `demo_micro.max_lot` | `0.01` | YES | `python -c "import yaml; print(yaml.safe_load(open('config/runtime.yaml'))['demo_micro']['max_lot'])"` |
| 1.5 | `demo_micro.max_open_positions` | `1` | YES | `python -c "import yaml; print(yaml.safe_load(open('config/runtime.yaml'))['demo_micro']['max_open_positions'])"` |
| 1.6 | `demo_micro.max_trades_per_run` | `1` | YES | `python -c "import yaml; print(yaml.safe_load(open('config/runtime.yaml'))['demo_micro']['max_trades_per_run'])"` |
| 1.7 | `demo_micro.allow_weekend` | `false` | YES | `python -c "import yaml; print(yaml.safe_load(open('config/runtime.yaml'))['demo_micro']['allow_weekend'])"` |
| 1.8 | `demo_micro.force_close_on_end` | `true` | YES | `python -c "import yaml; print(yaml.safe_load(open('config/runtime.yaml'))['demo_micro']['force_close_on_end'])"` |

### 2. Security — No Credentials/Tokens

| # | Item | Expected | Verified | Method |
|---|---|---|---|---|
| 2.1 | No GitHub PAT in tracked files | 0 actual tokens | YES | `git ls-files \| xargs grep -l "github_pat_11BZIGHBA0HUl9Sy"` → only placeholder `[REDACTED:github_token]...` in NEXT_SESSION_GUIDE.md |
| 2.2 | No GitHub PAT in git history | 0 matches | YES | `git log --all -p \| grep -c "github_pat_11BZIGHBA0HUl9Sy"` → 0 |
| 2.3 | No `TITAN_DEMO_MICRO_ARMED=1` in tracked files | not stored | YES | env var is operator-set, not committed |
| 2.4 | No `TITAN_LIVE_TRADING=1` in tracked files | not stored | YES | env var is operator-set, not committed |
| 2.5 | No MT5 credentials in config | empty placeholders | YES | `config/runtime.yaml` mt5 section has `login: 0`, `password: ""`, `server: ""` |

### 3. Execution Path — No Live/Demo Wiring Changes

| # | Item | Expected | Verified | Method |
|---|---|---|---|---|
| 3.1 | Governance NOT wired into `titan/production/trade_loop.py` | not imported | YES | `grep -c "stress_loss_governance" titan/production/trade_loop.py` → 0 |
| 3.2 | Governance NOT wired into `scripts/audit/fundednext_demo_micro_full_cycle.py` | not imported | YES | `grep -c "stress_loss_governance" scripts/audit/fundednext_demo_micro_full_cycle.py` → 0 |
| 3.3 | Governance NOT wired into `titan/runtime/launcher.py` | not imported | YES | `grep -c "stress_loss_governance" titan/runtime/launcher.py` → 0 |
| 3.4 | Governance only in `titan/production/stress_loss_governance.py` + tests + audit scripts | isolated | YES | governance module is standalone, opt-in via `--governance` flag |
| 3.5 | `DEMO_MICRO_EXECUTE` not run by Z AI | not run | YES | no MT5 on Z AI/Linux, `_get_mt5()` returns None |
| 3.6 | `mt5.order_send` not called in any Z AI execution | not called | YES | Z AI environment has no MetaTrader5 package |

### 4. Strategy Logic — No Changes

| # | Item | Expected | Verified | Method |
|---|---|---|---|---|
| 4.1 | No martingale added | not present | YES | `grep -r "martingale" titan/ scripts/ --include="*.py"` → only in comments/docs |
| 4.2 | No grid added | not present | YES | `grep -r "def _grid" titan/ scripts/ --include="*.py"` → 0 |
| 4.3 | No averaging added | not present | YES | `grep -r "def _averaging" titan/ scripts/ --include="*.py"` → 0 |
| 4.4 | No lot escalation | not present | YES | `grep -r "lot \*= 2" titan/ scripts/ --include="*.py"` → 0 |
| 4.5 | No models retrained | not run | YES | no model files modified in recent commits |
| 4.6 | No strategy logic changed | unchanged | YES | `trade_loop.py`, `execution_engine`, `inference.py` not modified in 9.9.3.x sprints |

### 5. Repository State

| # | Item | Expected | Verified | Method |
|---|---|---|---|---|
| 5.1 | Working tree clean | clean | YES | `git status` → "nothing to commit, working tree clean" |
| 5.2 | Branch up to date with origin/main | up to date | YES | `git status` → "Your branch is up to date with 'origin/main'" |
| 5.3 | HEAD at expected commit | `3d723f9` | YES | `git log --oneline -1` → "3d723f9 audit(sprint-9.9.3.6)..." |
| 5.4 | All required commits present | 7 sprints | YES | `git log --oneline -8` shows all 9.9.3.x commits |
| 5.5 | No untracked files in titan/ or scripts/ | clean | YES | only `data/audit/` reports may be generated (expected) |

### 6. Test Suite

| # | Item | Expected | Verified | Method |
|---|---|---|---|---|
| 6.1 | `first_run_check.py` | 0 FAIL | YES | 12 PASS, 1 WARN, 0 FAIL |
| 6.2 | `test_demo_micro_hard_gate.py` | all pass | YES | 25 passed |
| 6.3 | `test_fundednext_demo_micro_harness.py` | all pass | YES | 63 passed, 1 skipped (Windows-only) |
| 6.4 | `test_stress_loss_governance.py` | all pass | YES | 58 passed |
| 6.5 | Total tests | 146+ | YES | 146 passed, 1 skipped |

### 7. Safety Gates

| # | Item | Expected | Verified | Method |
|---|---|---|---|---|
| 7.1 | Hard gate blocks on Z AI/Linux | DEMO_MICRO_BLOCKED | YES | `python scripts/audit/demo_micro_hard_gate.py` → BLOCKED |
| 7.2 | DRY_ARM_CHECK_ONLY sends no orders | order_send_called=False | YES | `python scripts/audit/fundednext_demo_micro_full_cycle.py --mode DRY_ARM_CHECK_ONLY` |
| 7.3 | DEMO_MICRO_EXECUTE has 7 guards | all present | YES | verified in code: arm token, hard gate, side, lot, DEMO account, symbol, no existing position |
| 7.4 | Fail-closed on invalid inputs | YES | YES | governance engine returns NO_TRADE + CLOSE on invalid inputs |

---

## Freeze Verification Commands

Run these on Monday before starting the DEMO test to re-verify the freeze:

```cmd
cd /d "D:\Forex project\TITAN_XAU_AI"
myenv\Scripts\activate
git pull origin main
git status
git log --oneline -3

python first_run_check.py
python -m pytest titan/tests/test_demo_micro_hard_gate.py -q
python -m pytest titan/tests/test_fundednext_demo_micro_harness.py -q
python -m pytest titan/tests/test_stress_loss_governance.py -q

python -c "import yaml; c=yaml.safe_load(open('config/runtime.yaml')); print('dry_run:', c['runtime']['dry_run']); print('live_trading:', c['runtime']['live_trading']); print('demo_micro.enabled:', c['demo_micro']['enabled']); print('max_lot:', c['demo_micro']['max_lot'])"

python scripts/audit/demo_micro_hard_gate.py
python scripts/audit/fundednext_demo_micro_full_cycle.py --mode DRY_ARM_CHECK_ONLY
```

**Expected results:**
- `git status`: clean
- `git log --oneline -1`: `3d723f9 audit(sprint-9.9.3.6)...` (or newer)
- `first_run_check.py`: 12 PASS, 1 WARN, 0 FAIL
- All 3 test files: all pass
- Config: dry_run=True, live_trading=False, demo_micro.enabled=False, max_lot=0.01
- Hard gate: DEMO_MICRO_BLOCKED (correct fail-closed)
- DRY_ARM_CHECK_ONLY: order_send_called=False

---

## Freeze Status

**FROZEN**

All 35 checklist items verified. The repository is at a clean, stable, traceable baseline. No changes to execution path, strategy logic, or config defaults. No tokens leaked. All tests pass.

**The baseline is frozen until after Monday's DEMO micro test is complete and Z AI has analyzed the results.**

---

## Post-Monday Unfreeze Procedure

After the Monday DEMO test:
1. Operator sends report files to Z AI
2. Z AI analyzes results
3. If `final_verdict: DEMO_FULL_CYCLE_PASS`:
   - Z AI may propose wiring governance into live/demo trade_loop in a future sprint
   - Baseline unfreezes for next sprint cycle
4. If `final_verdict: DEMO_MANUAL_REVIEW_REQUIRED` or `DEMO_FULL_CYCLE_FAIL`:
   - Do NOT unfreeze
   - Investigate root cause
   - Fix in a new sprint before retrying

**The baseline remains frozen until explicit unfreeze approval.**
