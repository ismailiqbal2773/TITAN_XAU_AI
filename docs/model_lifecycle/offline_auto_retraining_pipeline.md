# TITAN XAU AI - Offline Auto Retraining Pipeline (Sprint 9.9.3.37)

## Purpose

This document defines the offline auto-retraining candidate pipeline: how
retraining is planned, validated, and registered **without** replacing the
champion model and **without** touching live/demo execution.

The pipeline is **candidate-only**. It produces retraining job specs and
candidate metadata. It does not run real training. It does not deploy. It
does not promote. It does not replace the champion.

## Scope

This policy applies to:

- `titan/production/offline_retraining_pipeline.py`
- `titan/production/retraining_trigger_monitor.py`
- `scripts/audit/offline_retraining_report.py`

It does **not** modify:

- Live trading flags (live trading remains `BLOCKED`)
- Execution logic
- Strategy entry logic
- Lot sizes
- Champion model artifact
- MT5 execution adapter
- Any runtime config consumed by the live trade loop

## What Triggers Retraining

Retraining may be triggered by the following signals, evaluated by
`RetrainingTriggerMonitor`:

| Trigger | Description |
|---|---|
| `SCHEDULED` | Time-based: retraining interval reached (default 90 days). |
| `PERFORMANCE_DECAY` | Current sharpe dropped 30%+ below baseline sharpe. |
| `CALIBRATION_DRIFT` | Brier score increased by 0.05+ above baseline. |
| `REGIME_SHIFT` | Regime-shift confidence >= 70%. |
| `BROKER_DEGRADATION` | Winrate dropped 10%+ below baseline. |
| `MANUAL_OPERATOR_REQUEST` | Operator-initiated retraining. |

Each trigger evaluation returns a `RetrainingTriggerSignal` with a
`recommended` field capped at `NEEDS_REVIEW`. The monitor never recommends
`RECOMMEND_RETRAINING` directly - it always defers to operator review.

## What Happens Automatically

The following happen **automatically** when the pipeline runs:

1. Trigger monitor evaluates runtime metrics and produces signals.
2. If a signal is `INSUFFICIENT_DATA`, no trigger fires (warning only).
3. If a signal is `NEEDS_REVIEW`, the trigger is recorded in the report.
4. The pipeline creates a `RetrainingJobSpec` with `dry_run=True` and
   `training_enabled=False` defaults.
5. The pipeline validates the spec (dataset manifest, feature set, label
   policy, champion reference).
6. If validation passes, the spec is marked `READY_FOR_OFFLINE_TRAINING`
   (metadata only - no actual training).
7. If a registry is provided, candidate metadata is registered as
   `CANDIDATE` in `ModelRegistry`.

## What Never Happens Automatically

The following **never** happen automatically:

- **Real training execution.** No `.fit()`, `train_model()`, `retrain()`,
  or `run_hpo()` calls.
- **Model artifact creation.** No pickle/joblib/torch save operations.
- **Champion replacement.** `champion_replaced` is hardcoded to `False`
  in `RetrainingJobResult.__post_init__`.
- **Auto-promotion.** Candidates are registered as `CANDIDATE` only.
- **Live runtime config modification.** `runtime.yaml` is never touched.
- **Live trading enablement.** Live trading remains `BLOCKED`.
- **MT5 order submission.** No `mt5.order_send` calls.
- **DEMO_MICRO_EXECUTE.** Not invoked.
- **HPO / backtest optimization.** Not invoked.

## Candidate-Only Policy

The pipeline may **only** register candidates. It cannot:

- Deploy a candidate to live runtime.
- Replace the champion model.
- Trade.
- Modify live runtime config.
- Bypass `ModelLifecycleGovernance`.
- Auto-promote any candidate to any stage.

Every candidate is registered as `CANDIDATE` in `ModelRegistry`. Promotion
to `SHADOW`, `CHALLENGER`, or `CHAMPION` requires explicit operator approval
through `ModelRegistry.require_manual_champion_promotion()` (for champion)
or `ModelRegistry.promote_to_challenger()` (for challenger).

## Champion Replacement Policy

Champion replacement is **forbidden** in this pipeline.

- `RetrainingJobResult.champion_replaced` is forced to `False` in
  `__post_init__` regardless of input.
- The pipeline never calls `ModelRegistry.require_manual_champion_promotion()`.
- The pipeline never calls `ModelRegistry.promote_to_challenger()`.
- Champion replacement requires explicit operator action outside the
  pipeline, with `manual_approval_flag=True` and an operator name.

## Manual Approval Requirement

Every transition that moves a candidate closer to champion requires
explicit operator approval:

- `CANDIDATE` -> `SHADOW`: requires `ModelLifecycleGovernance.evaluate_candidate()`
  to return `NEEDS_REVIEW` (not `BLOCKED`), followed by operator sign-off.
- `SHADOW` -> `CHALLENGER`: requires `ModelRegistry.promote_to_challenger()`
  with an operator name.
- `CHALLENGER` -> `CHAMPION`: requires
  `ModelRegistry.require_manual_champion_promotion()` with
  `manual_approval_flag=True` and an operator name.

The pipeline itself does not perform any of these transitions. It only
registers candidates.

## Dataset Manifest Requirement

A retraining job spec must include a `dataset_manifest_path` pointing to a
JSON manifest file with the following required fields:

- `dataset_id`: unique identifier for the dataset.
- `symbol`: e.g. `XAUUSD`.
- `timeframe`: e.g. `H1`.
- `rows`: number of rows in the dataset.
- `date_range`: object with `start` and `end` ISO timestamps.
- `train_test_split`: object with `train_start`, `train_end`, `test_start`,
  `test_end` ISO timestamps (anti-leakage requirement).
- `leakage_check_status`: must be `PASS`.

Missing or invalid manifest blocks the job spec. The pipeline reads the
manifest as JSON metadata only - it never loads the actual data files.

## Anti-Leakage Requirement

Anti-leakage is enforced at multiple levels:

1. **Dataset manifest:** Must declare `train_test_split` and
   `leakage_check_status=PASS`.
2. **Candidate registration:** `AlphaFactoryGovernance.reject_if_leakage_flags()`
   quarantines candidates with leakage flags.
3. **Lifecycle governance:** `ModelLifecycleGovernance.quarantine()` is
   invoked when leakage flags are detected during candidate evaluation.
4. **Reality gap metrics:** Required by `AlphaFactoryGovernance.require_reality_gap_metrics()`
   to detect backtest-vs-live divergence.

## Walk-Forward Requirement

A candidate must pass walk-forward validation before being marked
`READY_FOR_SHADOW`. The pipeline does not run walk-forward validation
itself - it requires the candidate's metrics to include
`walk_forward_status=PASS` (set by external validation tooling).

## Broker Split Requirement

A candidate must pass broker-split validation before being marked
`READY_FOR_SHADOW`. The pipeline does not run broker-split validation
itself - it requires the candidate's metrics to include
`broker_split_status=PASS` (set by external validation tooling).

## Shadow Validation Requirement

A candidate must complete shadow validation (168 hours minimum) before
being considered for challenger promotion. The pipeline does not run
shadow validation itself - it requires the candidate's metrics to include
`shadow_status=PASS` and `shadow_hours >= 168` (set by external shadow
runner).

## Rollback Requirement

If a newly promoted champion exhibits issues in production, the operator
may roll back to the previous champion by:

1. `ModelRegistry.reject_model(new_champion_id, reason="rollback")` or
   `ModelRegistry.quarantine_model(new_champion_id, reason="rollback")`.
2. `ModelRegistry.require_manual_champion_promotion(previous_champion_id,
   approved_by="operator", manual_approval_flag=True)` to restore the
   previous champion.

The pipeline does not perform rollback automatically. Rollback is always
operator-initiated.

## Trigger Monitor Policy

The `RetrainingTriggerMonitor` evaluates runtime metrics and produces
`RetrainingTriggerSignal` objects. The monitor:

- **Recommends** retraining triggers (NEEDS_REVIEW at most).
- **Cannot** launch training automatically.
- **Cannot** modify runtime config.
- **Returns** `INSUFFICIENT_DATA` when sample count is below 100.
- **Caps** recommendations at `NEEDS_REVIEW` - never `RECOMMEND_RETRAINING`.

The monitor's `recommend_trigger()` method aggregates all signals and
returns the most severe one. If all signals are `INSUFFICIENT_DATA`, the
aggregate recommendation is `INSUFFICIENT_DATA` (no trigger).

## Report Generation

`scripts/audit/offline_retraining_report.py` generates a report at
`data/audit/model_lifecycle/offline_retraining_report.{json,md}` containing:

- Trigger monitor status (per-trigger signals + aggregate).
- Retraining job readiness (training disabled, dry-run default).
- Candidate registration status (CANDIDATE stage, registry not updated).
- Champion replacement status (always False).
- Training execution status (always False / 0).
- Blockers and warnings.
- Final verdict: `RETRAINING_PIPELINE_READY`, `RETRAINING_PIPELINE_WARNINGS`,
  or `RETRAINING_PIPELINE_BLOCKED`.

The report is regenerated on each run and never modifies any model
artifact, runtime config, or live trading flag.

## Safety Invariants

The following invariants are enforced by code and verified by tests:

- No MetaTrader5 import.
- No `mt5.order_send` calls.
- No `MT5ExecutionAdapter()` instantiation.
- No `DEMO_MICRO_EXECUTE` invocation.
- No `raw_mt5_probe` invocation.
- No `demo_micro_repeatability` invocation.
- No model training execution (`.fit()`, `train_model()`, `retrain()`,
  `run_hpo()`).
- No HPO execution.
- No backtest optimization execution.
- No model artifact creation (no `pickle.dump`, `joblib.dump`, `torch.save`).
- No model artifact loading (no `pickle.load`, `joblib.load`, `torch.load`).
- No champion replacement (`champion_replaced` hardcoded False).
- No auto-promotion at any stage.
- No live runtime config modification.
- No lot size changes.
- No strategy entry logic changes.

## File Inventory

| File | Purpose |
|---|---|
| `titan/production/offline_retraining_pipeline.py` | Retraining job spec, validation, candidate registration |
| `titan/production/retraining_trigger_monitor.py` | Trigger signal evaluation |
| `scripts/audit/offline_retraining_report.py` | Report writer |
| `titan/tests/test_offline_retraining_pipeline.py` | Tests for pipeline |
| `titan/tests/test_retraining_trigger_monitor.py` | Tests for trigger monitor |
| `titan/tests/test_offline_retraining_report.py` | Tests for report writer |
| `docs/model_lifecycle/offline_auto_retraining_pipeline.md` | This document |
