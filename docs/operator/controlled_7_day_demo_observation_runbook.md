# TITAN XAU AI - Controlled 7-Day Demo Observation Runbook (Sprint 9.9.3.42)

## Purpose

This runbook defines the exact operator sequence for a controlled 7-day
demo observation of TITAN XAU AI in dry_run mode.

**This does NOT prove world no.1, live readiness, or commercial
multi-broker capability.** Live trading remains BLOCKED.

## Pre-Conditions

Before starting 7-day observation, the following must be true:

- **CTO audit verdict:** `CTO_READY_WITH_WARNINGS` (0 blockers)
- **Pre-observation verdict:** `DEMO_OBSERVATION_READY_WITH_WARNINGS` (0 blockers)
- **Approved warning:** `REGIME_GATE_WIRED_BUT_PLACEHOLDER_CONTEXT`
  - This is acceptable for controlled 7-day dry-run observation only.
  - It does NOT allow live trading, commercial readiness, world-class
    claim, or multi-broker claim.
- **Dry run only:** `runtime.dry_run=true`
- **Live trading blocked:** `runtime.live_trading=false`
- **MetaQuotes-Demo only:** Current controlled 7-day observation uses
  MetaQuotes-Demo as the only allowed broker.
- **Blocked brokers:** FundedNext Free Trial (DO_NOT_USE), FBS-Demo (REJECTED)
- **Pending brokers:** Exness Demo, ICMarkets Demo (not yet verified)
- **Unknown broker:** Requires compatibility proof before use

## Operator Sequence

### Step 1: Run First-Run Wizard

```
run_titan_first_run.bat
```

Verify:
- Overall status: PASS or WARN (not FAIL)
- No blockers

### Step 2: Run Start Check

```
python scripts/operator/start_7_day_demo_observation.py --check-only
```

Verify:
- Observation status: `READY_TO_START`
- 0 blockers
- 0 unapproved warnings
- Approved warnings may include `REGIME_GATE_WIRED_BUT_PLACEHOLDER_CONTEXT`

### Step 3: Start 7-Day Observation

```
python scripts/operator/start_7_day_demo_observation.py --start
```

Verify:
- Observation status: `STARTED`
- Session start report written to:
  - `data/audit/observation_7day/observation_session_start.json`
  - `data/audit/observation_7day/observation_session_start.md`

### Step 4: Start TITAN Runtime in Dry-Run Mode

```
python titan_launcher.py
```

Verify:
- Launcher logs "dry_run: True"
- Launcher logs "live_trading: False"
- Runtime starts the 6 async loops
- Journal events are written to `data/runtime/titan_journal.jsonl`

### Step 5: Run Daily Scorecard (Every 24 Hours)

Every 24 hours, run the daily scorecard:

```
python scripts/operator/run_daily_observation_scorecard.py --day 1 --since-hours 24
python scripts/operator/run_daily_observation_scorecard.py --day 2 --since-hours 24
python scripts/operator/run_daily_observation_scorecard.py --day 3 --since-hours 24
python scripts/operator/run_daily_observation_scorecard.py --day 4 --since-hours 24
python scripts/operator/run_daily_observation_scorecard.py --day 5 --since-hours 24
python scripts/operator/run_daily_observation_scorecard.py --day 6 --since-hours 24
python scripts/operator/run_daily_observation_scorecard.py --day 7 --since-hours 24
```

Or use the Windows helper:
```
run_titan_7_day_observation.bat
```
Select option 2 (RUN DAILY SCORECARD), enter the day number.

### Step 6: Finalize 7-Day Report (After Day 7)

After completing day 7, run the finalizer:

```
python scripts/operator/finalize_7_day_demo_observation.py
```

Or use the Windows helper:
```
run_titan_7_day_observation.bat
```
Select option 3 (FINALIZE 7-DAY REPORT).

## Verdict Definitions

### Daily Scorecard Verdicts

| Verdict | Meaning |
|---|---|
| `PASS` | All checks pass, no warnings, no open positions |
| `WARN` | Warnings present (e.g. regime placeholder, observation gaps) but no blockers |
| `FAIL` | Forbidden evidence found (order_send, live_trading, DEMO_MICRO_EXECUTE, raw_mt5_probe) OR open positions at day end |
| `INSUFFICIENT_DATA` | No journal events found for the period |

### Final 7-Day Verdicts

| Verdict | Meaning |
|---|---|
| `SEVEN_DAY_OBSERVATION_PASS` | All 7 days passed with no warnings |
| `SEVEN_DAY_OBSERVATION_PASS_WITH_WARNINGS` | All 7 days passed with approved warnings only |
| `SEVEN_DAY_OBSERVATION_FAIL` | Forbidden evidence, open positions, or daily FAIL |
| `SEVEN_DAY_OBSERVATION_INSUFFICIENT_DATA` | Missing days or no data |

## What Counts as PASS / WARN / FAIL / INSUFFICIENT_DATA

- **PASS:** 0 blockers, 0 warnings, 0 open positions, 0 forbidden evidence
- **WARN:** 0 blockers, approved warnings only (e.g. regime placeholder), 0 open positions
- **FAIL:** Any forbidden evidence (order_send, live_trading, DEMO_MICRO_EXECUTE, raw_mt5_probe) OR open positions > 0 at day end
- **INSUFFICIENT_DATA:** No journal events or missing days

## System Restart Handling

If the system restarts during the 7-day observation:

1. **Do NOT panic.** The journal is append-only and preserves all events.
2. **Verify dry_run is still true:** Check `config/runtime.yaml`.
3. **Verify live_trading is still false:** Check `config/runtime.yaml`.
4. **Restart the runtime:** `python titan_launcher.py`
5. **Continue the daily scorecard schedule.** Do not skip days.
6. **If a day was missed** (no journal events for 24+ hours), the daily
   scorecard for that day will return `INSUFFICIENT_DATA`.
7. **Document the restart** in your operator notes with timestamp and reason.

## Safe to Commit

The following files are safe to commit to git:

- `data/audit/observation_7day/observation_session_start.json` (session metadata)
- `data/audit/observation_7day/observation_session_start.md`
- `data/audit/observation_7day/day_N_scorecard.json` (daily scorecards)
- `data/audit/observation_7day/day_N_scorecard.md`
- `data/audit/observation_7day/final_7_day_observation_report.json`
- `data/audit/observation_7day/final_7_day_observation_report.md`
- Any source code changes (if needed for fixes)

## Never Commit (Raw/Private Evidence)

The following must NEVER be committed to git:

- `data/runtime/titan_journal.jsonl` (raw runtime journal — may contain account data)
- `data/audit/demo_micro/demo_micro_journal.jsonl` (raw demo micro journal)
- `data/audit/demo_micro/demo_micro_repeatability_journal.jsonl` (raw repeatability journal)
- `data/audit/demo_micro/raw_mt5_working_profile.json` (raw broker profile)
- `data/audit/demo_micro/broker_execution_profile.json` (raw broker profile)
- `data/audit/demo_micro/pass_evidence/` (raw pass evidence)
- `.env` (environment file — may contain secrets)
- Any file containing MT5 login, password, server, account number, or balance
- Any file containing API keys

## Clear Note

**This 7-day observation does NOT prove:**
- World no.1 trading system
- Live trading readiness
- Commercial multi-broker capability
- World-class multi-regime capability (regime gate uses placeholder context)

**This 7-day observation DOES verify:**
- The institutional pipeline is wired and produces correct journal events
- The operator console and first-run wizard work safely
- The broker observation gate correctly allows MetaQuotes-Demo only
- No forbidden execution evidence (order_send, live_trading, DEMO_MICRO_EXECUTE, raw_mt5_probe) appears
- No open positions remain at day end
- The daily scorecard correctly tracks observation quality

**Live trading remains BLOCKED.**
