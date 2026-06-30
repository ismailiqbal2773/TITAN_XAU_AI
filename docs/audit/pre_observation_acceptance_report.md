# TITAN XAU AI — Pre-Observation Acceptance Report (Sprint 9.9.3.41)

## Purpose

This report is the **brutally honest** pre-observation acceptance audit.
It answers one question: **Is TITAN truly ready for controlled 7-day demo
observation?**

The answer, based on source-level inspection of every relevant file, is
reported as a go/no-go verdict.

## What Is Ready

The following dimensions are fully ready for 7-day demo observation:

- **Sprint/module inventory**: All 46 modules exist. Critical institutional
  pipeline modules are wired into `AutonomousRuntime`.
- **End-to-end runtime chain**: All 18 chain links are PRESENT or PARTIAL.
  No critical link is ABSENT.
- **Logical contradiction audit**: Zero contradictions. No old Sprint 5-8
  bypass path. No auto-promotion. No auto-calibration apply. No unsafe
  batch commands. No MetaTrader5 import in safe modules. No order_send in
  safe modules.
- **Mathematical consistency**: All formulas and constraints are consistent.
  max_lot=0.01, max_open_positions=1, ATR multipliers valid, confidence
  thresholds in [0,1], kill switch thresholds sane, observation scorecard
  blocks on open positions and returns INSUFFICIENT_DATA when no events.
- **Configuration consistency**: runtime.dry_run=true, runtime.live_trading=false,
  max_lot=0.01, max_open_positions=1, demo_micro.enabled=false, broker
  registry matches (MetaQuotes PASS, FundedNext BLOCKED, FBS REJECT),
  model lifecycle governance has enforce_no_auto_promotion, retraining
  training_enabled defaults False.
- **Windows RC package safety**: All batch files exist, package builder
  exists, operator batch exposes only safe commands, first-run wizard
  does not import MetaTrader5, does not ask for credentials, does not
  expose live trading, package builder excludes raw evidence and .env.
- **Demo monitoring readiness**: All 26 required monitoring event types
  present. ForwardObservationEngine wired into runtime (real-time event
  recording). ObservationScorecardEngine accessible from runtime.
  Scorecard returns INSUFFICIENT_DATA when no events. Scorecard considers
  final_open_positions. Journal uses append-only JSONL buffer.

## What Is Warning

There are currently **zero warnings**. All audit areas pass cleanly.

## What Is Blocked

There are currently **zero blockers**. The verdict is
`DEMO_OBSERVATION_READY`.

## What Is Safe for Demo Observation

The following are safe for 7-day demo observation:

1. **Dry-run mode only.** `runtime.dry_run=true` is enforced. No real
   orders will be sent.
2. **Live trading blocked.** `runtime.live_trading=false` is enforced.
   The launcher refuses to start if `live_trading=true` without
   `TITAN_LIVE_TRADING=1` env var.
3. **Max lot cap 0.01.** Hard-coded in `TradeLoop` and `ExecutionIntent`.
4. **Max open positions 1.** Hard-coded in `TradeLoop`.
5. **Institutional pipeline wired.** `SignalExecutionBridge` is called
   before `TradeLoop`. Blocked intents skip `TradeLoop` entirely.
6. **Exit pipeline wired.** `PositionLifecycleEngine` + `ExitIntentBridge`
   run before `ExitManager` (final safety layer).
7. **Observation wired.** `ForwardObservationEngine` records real runtime
   events. `ObservationScorecardEngine` scores them.
8. **Operator console safe.** Only 9 safe commands exposed. No live
   trading, no market execution, no DEMO_MICRO_EXECUTE.
9. **First-run wizard safe.** No MetaTrader5 import, no credentials
   requested, no live trading exposed.
10. **Windows RC package safe.** Raw evidence and credentials excluded.
    Only safe commands in batch files.

## What Is Not Safe

The following are NOT safe and must NOT be used during 7-day demo
observation:

1. **Live trading.** Must remain BLOCKED.
2. **Market execution.** NOT available from operator console or RC package.
3. **DEMO_MICRO_EXECUTE.** NOT exposed.
4. **Raw MT5 probe.** NOT exposed.
5. **Repeatability execution.** NOT exposed.
6. **Model retraining.** NOT exposed.
7. **HPO.** NOT exposed.
8. **Champion replacement.** Requires explicit operator approval via
   `ModelRegistry.require_manual_champion_promotion()` with
   `manual_approval_flag=True`.
9. **Calibration auto-apply.** Forbidden. `apply_automatically` is
   hardcoded False.
10. **FundedNext Free Trial.** Must remain BLOCKED / DO_NOT_USE.

## What Must Remain Blocked Before Live Trading

The following must remain BLOCKED before live trading is even considered:

1. **Live trading flag** — `runtime.live_trading` must remain `false`.
2. **Max lot cap** — `risk.max_lot` must remain `0.01`.
3. **Max open positions cap** — `risk.max_open_positions` must remain `1`.
4. **No martingale / grid / averaging / lot escalation.**
5. **FundedNext Free Trial** — must remain `BLOCKED`.
6. **FBS-Demo** — must remain `REJECT`.
7. **No DEMO_MICRO_EXECUTE from operator console.**
8. **No raw_mt5_probe from operator console.**
9. **No auto champion promotion.**
10. **No auto calibration apply.**
11. **No model training execution.**
12. **No model artifact creation.**
13. **No MetaTrader5 import in safe modules.**
14. **No `mt5.order_send` in safe modules.**

## Operator Checklist Before 7-Day Demo

Before starting 7-day demo observation, the operator must:

1. **Run the first-run wizard.**
   - Double-click `run_titan_first_run.bat`.
   - Verify overall status is PASS or WARN (not FAIL).
   - Review the report at `data/audit/operator/first_run_wizard_report.md`.

2. **Run the operator console.**
   - Double-click `run_titan_operator.bat`.
   - Select `1 STATUS` — verify RC_READY or RC_READY_WITH_WARNINGS.
   - Select `3 SAFETY CHECK` — verify SAFETY_OK.
   - Select `4 BROKER STATUS` — verify MetaQuotes-Demo verified and
     FundedNext blocked.
   - Select `2 RC CHECK` — verify RC_READY.
   - Select `7 FULL AUDIT` — generate all safe reports.

3. **Review the pre-observation acceptance audit.**
   - Run `python scripts/audit/pre_observation_acceptance_audit.py`.
   - Verify verdict is `DEMO_OBSERVATION_READY` or
     `DEMO_OBSERVATION_READY_WITH_WARNINGS` (not BLOCKED).
   - Review the report at
     `data/audit/pre_observation/pre_observation_acceptance_audit.md`.

4. **Review the master integration audit.**
   - Run `python scripts/audit/master_integration_audit.py`.
   - Verify verdict is `INTEGRATION_READY` or
     `INTEGRATION_READY_WITH_WARNINGS` (not BLOCKED).
   - Review the report at
     `data/audit/master_integration/master_integration_audit.md`.

5. **Explicitly accept the RC package in writing.**
   - Sign and date a statement accepting the RC package for 7-day
     demo observation.
   - Include the HEAD commit hash from the audit reports.

6. **Start the autonomous runtime in dry_run mode.**
   - `python titan_launcher.py` (defaults to dry_run=true).
   - Verify the launcher logs "dry_run: True" and "live_trading: False".

7. **Monitor daily.**
   - Every 24 hours, run `python scripts/audit/daily_demo_observation_runner.py`.
   - Review the daily scorecard grade.
   - Verify `final_open_positions = 0` at end of each day.
   - Verify no safety blocks occurred.

8. **Do NOT enable live trading.**
   - Live trading remains BLOCKED for the entire 7-day observation.
   - Do not modify `config/runtime.yaml` to set `live_trading: true`.
   - Do not set `TITAN_LIVE_TRADING=1` env var.

9. **Do NOT run DEMO_MICRO_EXECUTE.**
   - The operator console does not expose it.
   - Do not invoke `demo_micro_full_cycle.py` directly.

10. **At the end of 7 days, run the final audit.**
    - Run `python scripts/audit/pre_observation_acceptance_audit.py` again.
    - Run `python scripts/audit/master_integration_audit.py` again.
    - Verify both verdicts are still READY or READY_WITH_WARNINGS.
    - Verify `final_open_positions = 0` across all 7 days.
    - Verify zero safety blocks across all 7 days.

## Final Verdict

**DEMO_OBSERVATION_READY**

TITAN is ready for controlled 7-day demo observation in dry_run mode.
Live trading remains BLOCKED. Market execution is NOT available.

## File Inventory

| File | Purpose |
|---|---|
| `scripts/audit/pre_observation_acceptance_audit.py` | Audit writer |
| `docs/audit/pre_observation_acceptance_report.md` | This document |
| `titan/tests/test_pre_observation_acceptance_audit.py` | Tests for audit writer |
| `data/audit/pre_observation/pre_observation_acceptance_audit.json` | Generated JSON report |
| `data/audit/pre_observation/pre_observation_acceptance_audit.md` | Generated MD report |
