# TITAN XAU AI - Windows RC Package Guide (Sprint 9.9.3.40)

## Purpose

This guide explains how a non-technical operator uses the TITAN XAU AI
Release Candidate (RC) package on Windows. The RC package is safe by
design: it never enables live trading, never exposes market execution,
and never asks for credentials.

## What Is the RC Package?

The RC package is a folder (`TITAN_XAU_AI_RC/`) containing everything
the operator needs to:

- Run the first-run wizard
- Run the operator console
- Check RC status
- Check safety status
- Check broker registry
- Run a full audit
- Read clear instructions

The package is built by `scripts/release/build_windows_rc_package.py`.
It is **not** an installer — it is a folder the operator copies onto
their Windows machine.

## How to Run the First-Run Wizard

The first-run wizard verifies the RC environment is safe and ready.

1. Open the `TITAN_XAU_AI_RC/` folder in File Explorer.
2. Double-click `run_titan_first_run.bat`.
3. The wizard runs 12 checks and prints a summary:
   - **PASS** — RC environment is ready.
   - **WARN** — RC environment has warnings (review before proceeding).
   - **FAIL** — RC environment is blocked (resolve blockers before proceeding).
4. The wizard writes a report to:
   - `data/audit/operator/first_run_wizard_report.json`
   - `data/audit/operator/first_run_wizard_report.md`

If the wizard reports FAIL, contact your TITAN administrator with the
report before proceeding.

## How to Run the Operator Console

The operator console is the safe RC command center.

1. Open the `TITAN_XAU_AI_RC/` folder in File Explorer.
2. Double-click `run_titan_operator.bat`.
3. A menu appears with 9 options:
   - `1 STATUS` — Show current RC mode + safety state
   - `2 RC CHECK` — Verify release candidate readiness
   - `3 SAFETY CHECK` — Confirm all safety gates closed
   - `4 BROKER STATUS` — Show broker registry
   - `5 OBSERVATION REPORT` — Generate forward observation report
   - `6 DAILY SCORECARD` — Generate daily observation scorecard
   - `7 FULL AUDIT` — Run all safe reports
   - `8 HELP` — Show available commands
   - `0 EXIT` — Quit the console

4. Type the number of the command you want to run and press Enter.
5. The console prints the result and returns to the menu.

## How to Run Safe RC Checks

The recommended safe workflow is:

1. Run `run_titan_first_run.bat` first. Verify PASS or WARN.
2. Run `run_titan_operator.bat`.
3. Select `1 STATUS` to verify RC mode and live-blocked.
4. Select `3 SAFETY CHECK` to confirm all safety gates closed.
5. Select `4 BROKER STATUS` to confirm MetaQuotes-Demo verified and
   FundedNext blocked.
6. Select `2 RC CHECK` to confirm RC_READY or RC_READY_WITH_WARNINGS.
7. Select `7 FULL AUDIT` to generate all safe reports.

After this workflow completes, the RC environment is ready for
observation. The operator may begin observation only after explicitly
accepting the RC package in writing.

## What Is Included

The RC package includes:

| File | Purpose |
|---|---|
| `run_titan_operator.bat` | Windows operator console launcher |
| `run_titan_first_run.bat` | Windows first-run wizard launcher |
| `scripts/operator/titan_operator.py` | Operator console CLI |
| `scripts/operator/titan_first_run.py` | First-run wizard CLI |
| `docs/operator/operator_control_console.md` | Operator console docs |
| `docs/release/production_release_candidate_plan.md` | RC plan |
| `docs/release/windows_rc_package_guide.md` | This document |
| `docs/audit/master_integration_gap_report.md` | Integration audit |
| `docs/audit/demo_micro_execution_registry.md` | Demo micro registry |
| `docs/audit/demo_forward_observation_plan.md` | Observation plan |
| `docs/audit/daily_demo_observation_checklist.md` | Daily checklist |
| `docs/audit/demo_micro_repeatability_metaquotes_redacted.md` | Redacted evidence (MD) |
| `docs/audit/demo_micro_repeatability_metaquotes_redacted.json` | Redacted evidence (JSON) |
| `requirements.txt` | Python dependencies |
| `first_run_check.py` | Legacy first-run check |
| `RELEASE_MANIFEST.json` | Package manifest |
| `README_FIRST_RUN.md` | First-run instructions |
| `SAFETY_NOTICE.md` | Safety notice |

## What Is Intentionally Excluded

The RC package **does NOT include**:

| Excluded | Reason |
|---|---|
| `data/audit/demo_micro/pass_evidence/` | Raw pass evidence (private) |
| `data/audit/demo_micro/demo_micro_journal.jsonl` | Raw journal (private account data) |
| `data/audit/demo_micro/demo_micro_repeatability_journal.jsonl` | Raw journal (private account data) |
| `data/audit/demo_micro/raw_mt5_working_profile.json` | Raw broker profile (private) |
| `data/audit/demo_micro/broker_execution_profile.json` | Raw broker profile (private) |
| `.env` | Environment file (may contain secrets) |
| `.env.local` | Local environment file (may contain secrets) |
| `config/mt5_credentials.yaml` | MT5 credentials (private) |
| `data/credentials/` | Credentials directory (private) |
| `data/private/` | Private data directory |

If any of these files appear in the package, **do not use the package**.
Contact your TITAN administrator immediately.

## Safety Rules

1. **Live trading remains BLOCKED.** The `live_trading` flag in
   `config/runtime.yaml` is `false`. The launcher refuses to start if it
   is `true` without explicit operator confirmation.
2. **Market execution is NOT available.** The operator console and
   first-run wizard do not expose any market execution command.
3. **DEMO_MICRO_EXECUTE is NOT exposed.** The operator console and
   first-run wizard do not invoke `demo_micro_full_cycle.py` or
   `demo_micro_repeatability.py`.
4. **Raw MT5 probe is NOT exposed.** The operator console and first-run
   wizard do not invoke `raw_mt5_probe.py`.
5. **Repeatability execution is NOT exposed.** The operator console and
   first-run wizard do not invoke repeatability runners.
6. **Order send is NOT exposed.** No safe module imports `MetaTrader5`
   or calls `mt5.order_send`.
7. **Model retraining is NOT exposed.** No retraining execution occurs
   from this package.
8. **HPO is NOT exposed.** No hyperparameter optimization occurs from
   this package.
9. **Max lot cap is 0.01.** Hard-coded in `TradeLoop` and
   `ExecutionIntent`.
10. **Max open positions cap is 1.** Hard-coded in `TradeLoop`.
11. **No martingale / grid / averaging / lot escalation.** Verified
    absent.
12. **FundedNext Free Trial remains BLOCKED.** Verified in
    `broker_compatibility_matrix.py`.
13. **FBS-Demo remains REJECTED.** Verified in
    `broker_compatibility_matrix.py`.
14. **MetaQuotes-Demo is the only verified broker for demo micro.**
    Verified in `broker_compatibility_matrix.py`.

## Privacy Rules

- No raw account data is included in this package.
- No `.env` file is included.
- No credentials are included.
- No API keys are included.
- No personal account/login/balance evidence is included.
- All evidence files in this package are already redacted.
- The package never asks for account password.
- The package never asks for API key.

## No Live Trading

**Live trading remains BLOCKED.**

There is no path in this package by which live trading can be enabled.
Enabling live trading requires source code modification outside this
package and explicit operator approval. This is by design.

## No Market Execution from Package

The operator console and first-run wizard do not expose any market
execution command. The package never imports `MetaTrader5` and never
calls `mt5.order_send`.

## No Raw Evidence Included

The RC package intentionally excludes all raw evidence files. The only
evidence files included are already-redacted JSON and MD files in
`docs/audit/`. If any raw journal or broker profile file appears in the
package, do not use it.

## Observation Starts Only After RC Package Acceptance

Observation may begin only after the operator:

1. Runs the first-run wizard (`run_titan_first_run.bat`) and verifies
   PASS or WARN.
2. Runs the operator console (`run_titan_operator.bat`) and verifies:
   - STATUS shows `RC_READY` or `RC_READY_WITH_WARNINGS`
   - SAFETY CHECK shows `SAFETY_OK`
   - BROKER STATUS shows MetaQuotes-Demo verified and FundedNext blocked
3. Reviews the master integration audit report.
4. Explicitly accepts the RC package in writing.

## Live Trading Remains Blocked

**Live trading remains BLOCKED.** This is the single most important
safety invariant. There is no path in this package by which live
trading can be enabled. Enabling live trading requires source code
modification outside this package and explicit operator approval.

## Support

If the first-run wizard reports FAIL, contact your TITAN administrator
with the report at `data/audit/operator/first_run_wizard_report.md`.

## File Inventory

| File | Purpose |
|---|---|
| `titan/production/first_run_wizard.py` | First-run wizard module |
| `scripts/operator/titan_first_run.py` | First-run wizard CLI |
| `run_titan_first_run.bat` | Windows first-run wizard launcher |
| `run_titan_operator.bat` | Windows operator console launcher |
| `scripts/release/build_windows_rc_package.py` | RC package builder |
| `docs/release/windows_rc_package_guide.md` | This document |
| `titan/tests/test_first_run_wizard.py` | First-run wizard tests |
| `titan/tests/test_titan_first_run_cli.py` | First-run CLI tests |
| `titan/tests/test_windows_rc_package.py` | RC package builder tests |
