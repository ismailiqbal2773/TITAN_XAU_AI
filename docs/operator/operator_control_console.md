# TITAN XAU AI — Operator Control Console (Sprint 9.9.3.35)

## Purpose

The Operator Control Console is a **safe operator-facing command center** that gives one Windows-friendly entrypoint for release-candidate checks, reports, observation summaries, and safety status.

It is intentionally narrow:

- **No live trading.** Live trading remains `BLOCKED`.
- **No market execution.** Market execution is NOT available from this console.
- **No `DEMO_MICRO_EXECUTE`.** The console does not expose the demo micro execution path.
- **No raw probe.** The console does not run `raw_mt5_probe.py`.
- **No repeatability execution.** The console does not run `demo_micro_repeatability.py`.
- **No MetaTrader5 import.** The console does not import the `MetaTrader5` Python package.
- **No order_send.** The console never calls `mt5.order_send` or any adapter execution method.
- **No lot changes.** The console never changes `max_lot` (hard cap `0.01`).
- **No model changes.** The console never retrains, replaces champions, or changes strategies.

## Files

| Artifact | Path |
|---|---|
| Console module | `titan/production/operator_control_console.py` |
| CLI | `scripts/operator/titan_operator.py` |
| Windows helper | `run_titan_operator.bat` |
| Console tests | `titan/tests/test_operator_control_console.py` |
| CLI tests | `titan/tests/test_titan_operator_cli.py` |
| Command report JSON | `data/audit/operator/operator_command_report.json` |
| Command report MD | `data/audit/operator/operator_command_report.md` |

## Command List

| Command | What it does |
|---|---|
| `status` | Summarize current RC mode, live-blocked, dry-run/demo-only, broker registry, component status. |
| `rc-check` | Call `ProductionRuntimeAssembly.build_status()` and return `RC_READY` / `RC_READY_WITH_WARNINGS` / `RC_BLOCKED`. |
| `safety-check` | Confirm `live_trading_enabled=False`, `mt5_order_send_allowed=False`, `max_lot <= 0.01`, `max_open_positions <= 1`, FundedNext Free Trial blocked, raw evidence ignored. |
| `broker-status` | Summarize the broker registry: MetaQuotes-Demo VERIFIED_FOR_DEMO_MICRO, FBS-Demo REJECTED/LOW, FundedNext Free Trial DO_NOT_USE, Exness Demo PENDING, ICMarkets Demo PENDING. |
| `observation-report` | Generate the forward observation report. Journals are optional — missing journals produce a warning, not a failure. |
| `daily-scorecard` | Generate the daily observation scorecard. Returns `INSUFFICIENT_DATA` when no journals exist. Accepts `--since-hours` (default 24). |
| `full-audit` | Run safe report generation only: production assembly report, forward observation report, daily observation scorecard, redacted registry presence check. |
| `help` | List available commands and safe usage. |

## Windows Usage

### Option A — Batch helper (recommended for operators)

Double-click `run_titan_operator.bat` or run from a terminal:

```
run_titan_operator.bat
```

The batch helper will:

1. Activate the existing virtual environment if found (`venv`, `.venv`, or `env`).
2. Show a menu:
   - `1 STATUS`
   - `2 RC CHECK`
   - `3 SAFETY CHECK`
   - `4 BROKER STATUS`
   - `5 FULL AUDIT`
   - `6 HELP`
   - `0 EXIT`
3. Call `scripts/operator/titan_operator.py` with the selected command.

The batch helper **does not expose a live trading option** and **does not expose a market execution option**.

### Option B — Direct CLI

```
python scripts/operator/titan_operator.py status
python scripts/operator/titan_operator.py rc-check
python scripts/operator/titan_operator.py safety-check
python scripts/operator/titan_operator.py broker-status
python scripts/operator/titan_operator.py observation-report
python scripts/operator/titan_operator.py daily-scorecard --since-hours 24
python scripts/operator/titan_operator.py full-audit
python scripts/operator/titan_operator.py help
```

### JSON output

Every command supports `--json`:

```
python scripts/operator/titan_operator.py status --json
```

The JSON payload is the full `OperatorCommandResult` dataclass.

## What Each Command Means

### `status`

Summarizes the current release-candidate mode and safety state in one line:

- RC mode (`DRY_RUN`, `DEMO_OBSERVATION`, `DEMO_MICRO_OPERATOR`, `LIVE_BLOCKED`)
- `live_blocked` (true when `live_trading_enabled=False`)
- `dry_run`
- `demo_only`
- components loaded / total
- broker registry size

Returns `blockers` for any hard safety violation. Returns `warnings` for non-critical drift (e.g. broker status drift).

### `rc-check`

Calls `ProductionRuntimeAssembly.build_status()` and returns the assembly verdict:

- `RC_READY` — all components loaded, all safety gates enabled, no blockers, no warnings.
- `RC_READY_WITH_WARNINGS` — components loaded, but warnings present (e.g. broker status notes).
- `RC_BLOCKED` — at least one blocker (missing component, live trading enabled, MT5 order_send allowed, lot cap exceeded, position cap exceeded).

The console re-checks the hard invariants and will downgrade the verdict to `RC_BLOCKED` if any invariant is violated, even if the underlying assembly reported `RC_READY`.

### `safety-check`

Confirms every hard safety gate:

- `live_trading_enabled=False`
- `mt5_order_send_allowed=False`
- `max_lot <= 0.01`
- `max_open_positions <= 1`
- `dry_run=True`
- `demo_only=True`
- FundedNext Free Trial `BLOCKED`
- Raw runtime evidence ignored (no raw probe, no repeatability)

Returns `SAFETY_OK` if all gates pass, otherwise `SAFETY_BLOCKED` with a list of `blockers`.

### `broker-status`

Summarizes the broker registry from `titan/production/broker_compatibility_matrix.py`:

- MetaQuotes-Demo — `PASS` / VERIFIED_FOR_DEMO_MICRO
- FBS-Demo — `REJECT` / LOW priority (retcode 10006)
- FundedNext Free Trial — `BLOCKED` / DO_NOT_USE
- Exness Demo — `PENDING`
- ICMarkets Demo — `PENDING`

Returns `BROKER_REGISTRY_OK` when MetaQuotes is verified and FundedNext is blocked. Returns `BROKER_REGISTRY_DRIFT` with `blockers` otherwise.

### `observation-report`

Generates `data/audit/forward_observation/forward_observation_report.{json,md}`.

- Journals are **optional**. Missing journals are reported in `warnings`, not `blockers`.
- The console never imports MT5 and never executes trades.
- Accepts `--since-hours` to filter the observation window.

### `daily-scorecard`

Generates `data/audit/forward_observation/daily_demo_observation_scorecard.{json,md}`.

- Returns `INSUFFICIENT_DATA` if no journals exist.
- Accepts `--since-hours` (default 24).
- Never imports MT5 and never executes trades.

### `full-audit`

Runs safe report generation only:

1. `data/audit/production_assembly/production_assembly_report.{json,md}`
2. `data/audit/forward_observation/forward_observation_report.{json,md}`
3. `data/audit/forward_observation/daily_demo_observation_scorecard.{json,md}`
4. Redacted registry presence check at `docs/audit/demo_micro_repeatability_metaquotes_redacted.{json,md}`

Returns `FULL_AUDIT_OK` when all reports generate successfully. Returns `FULL_AUDIT_BLOCKED` with `blockers` if any report generation fails.

### `help`

Lists all available commands and the safe workflow. Returns `HELP_OK`.

## Safe Workflow Before Observation

Operators should run the commands in this order before any long observation window:

1. `status` — verify RC mode and live-blocked.
2. `safety-check` — confirm all safety gates closed.
3. `broker-status` — confirm MetaQuotes verified, FundedNext blocked.
4. `rc-check` — confirm `RC_READY` or `RC_READY_WITH_WARNINGS`.
5. `observation-report` — generate observation report.
6. `daily-scorecard` — generate daily scorecard.
7. `full-audit` — generate all reports.

After the workflow completes, observation may begin. Operators must continue to **not** enable live trading, **not** import MetaTrader5, and **not** send any orders from this console.

## What NOT to Run

The operator control console is intentionally narrow. Do **not** run any of the following from this console:

- `DEMO_MICRO_EXECUTE` — not exposed
- `raw_mt5_probe.py` — not exposed
- `demo_micro_repeatability.py` — not exposed
- `demo_micro_full_cycle.py` — not exposed
- Any live trading command — not exposed
- Any market execution command — not exposed
- Any lot/size override — not exposed
- Any model retraining — not exposed
- Any champion replacement — not exposed
- Any strategy change — not exposed

If you need any of the above, run them from their own dedicated scripts **outside** the operator console, and only after explicit operator approval.

## Privacy Warning

- Never commit raw journal files that contain private account data (account numbers, balances, login IDs, server names tied to a real account).
- Always use the redacted registries (e.g. `docs/audit/demo_micro_repeatability_metaquotes_redacted.{json,md}`) when sharing evidence externally.
- The operator console never prints or persists raw runtime evidence.

## Raw Runtime Evidence Warning

Raw runtime evidence (full MT5 retcodes, full broker snapshots, full order responses) is **ignored** by the operator console. The console only reads:

- `titan/production/broker_compatibility_matrix.py` (static broker facts)
- `titan/production/production_runtime_assembly.py` (assembly status)
- `scripts/audit/forward_observation_report.py` (journal-derived observation summary)
- `scripts/audit/daily_demo_observation_runner.py` (journal-derived daily scorecard)
- `scripts/audit/production_assembly_report.py` (assembly report)
- `docs/audit/demo_micro_repeatability_metaquotes_redacted.{json,md}` (already-redacted evidence)

The console does **not** read:

- Raw MT5 terminal logs
- Raw journal files containing unredacted account data
- Raw order responses with private fields
- Raw broker server snapshots

## Live Trading Remains Blocked

Live trading is hardcoded to `False` in the underlying `ProductionRuntimeAssembly`. The operator console does not expose any flag, switch, or command to enable live trading. To enable live trading, operators would need to modify source code and re-run — which is explicitly out of scope for this sprint.

## Market Execution Not Available from Operator Console

Market execution is **not** available from the operator console. The console:

- Does not import `MetaTrader5`.
- Does not call `mt5.order_send`.
- Does not call `MT5ExecutionAdapter.send_open_order` or `send_close_order`.
- Does not expose `DEMO_MICRO_EXECUTE`.
- Does not run `raw_mt5_probe.py`.
- Does not run `demo_micro_repeatability.py`.

## Command Report

Every command writes a combined operator command report to:

- `data/audit/operator/operator_command_report.json`
- `data/audit/operator/operator_command_report.md`

The report captures:

- Last command run
- `OperatorCommandResult` (command, ok, verdict, message, reports_generated, blockers, warnings, next_steps, timestamp_utc)
- Safety assertions (`live_trading_enabled=False`, `mt5_order_send_allowed=False`, `metatrader5_imported=False`, `market_execution_run=False`, `demo_micro_execute_run=False`)
- General warnings

The report is overwritten on each command. It is intended as a quick "what was the last command run" audit trail, not a permanent log.
