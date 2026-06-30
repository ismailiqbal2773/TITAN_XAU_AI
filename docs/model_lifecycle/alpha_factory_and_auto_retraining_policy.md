# TITAN XAU AI - Alpha Factory and Auto Retraining Policy (Sprint 9.9.3.36)

## Purpose

This document defines the institutional policy for the alpha factory, auto
calibration, auto retraining governance, the model registry, and the
champion/challenger lifecycle.

The goal is to provide a **safe, auditable foundation** for future alpha
discovery, calibration, and retraining work — without ever automatically
deploying, replacing, or promoting a model into the live runtime.

## Scope

This policy applies to:

- `titan/production/model_lifecycle_governance.py`
- `titan/production/auto_calibration_governance.py`
- `titan/production/alpha_factory_governance.py`
- `titan/production/model_registry.py`
- `scripts/audit/model_lifecycle_report.py`

It does **not** modify:

- Live trading flags (live trading remains `BLOCKED`)
- Execution logic
- Strategy entry logic
- Lot sizes
- Champion model artifact
- MT5 execution adapter
- Any runtime config consumed by the live trade loop

## Alpha Factory Purpose

The alpha factory is a **candidate generation and registration** layer only.

It may:

- Register new alpha candidates (feature sets, label variants, model
  variants, ensemble variants, threshold variants, regime specialists,
  exit policy variants).
- Validate candidate metadata.
- Reject candidates with leakage flags.
- Require walk-forward validation.
- Require broker-split validation.
- Require reality-gap metrics.
- Mark candidates as `READY_FOR_SHADOW` once all gates pass.

It may **not**:

- Deploy a candidate.
- Replace the champion model.
- Trade.
- Modify live runtime config.
- Bypass `ModelLifecycleGovernance`.
- Promote a candidate to champion.
- Auto-promote any candidate to any stage.

## Auto Calibration Policy

Auto calibration governance produces **recommendations only**.

It may:

- Evaluate calibration metrics (Brier score, ECE, sample count).
- Recommend threshold adjustments (clamped to a safe delta).
- Recommend probability recalibration.
- Block calibration if live mode is active.
- Block calibration if sample count is below the minimum.
- Surface calibration warnings for operator review.

It may **not**:

- Auto-apply any calibration change. `apply_automatically` is hardcoded
  to `False` and cannot be overridden.
- Apply calibration while live mode is active.
- Apply calibration with insufficient samples.
- Bypass operator review.

## Auto Retraining Policy

There is **no auto retraining** in this sprint.

Retraining governance is intentionally absent. Any future retraining must:

1. Be explicitly approved by the operator.
2. Produce a candidate model registered in the `ModelRegistry`.
3. Pass through `ModelLifecycleGovernance.evaluate_candidate()`.
4. Pass walk-forward, broker-split, calibration, and drawdown gates.
5. Be promoted to challenger (not champion) first.
6. Run in shadow mode for a minimum of 168 hours (7 days).
7. Only then be considered for champion promotion, which requires
   explicit `manual_approval_flag=True` and an operator name.

## Champion / Challenger Lifecycle

The lifecycle stages are:

| Stage | Meaning |
|---|---|
| `CHAMPION` | The single currently-deployed model. Exactly one champion is allowed at any time. |
| `CHALLENGER` | A model that has passed candidate gates and is being evaluated for promotion. |
| `CANDIDATE` | A newly registered model. Default stage for all new registrations. |
| `SHADOW` | A model running in shadow mode (observation only, no live execution). |
| `REJECTED` | A model that failed governance and will not be considered further. |
| `RETIRED` | A model that was previously champion or challenger and has been retired. |
| `QUARANTINED` | A model suspected of leakage or critical issues. Cannot be promoted. |

Promotion rules:

- `CANDIDATE` -> `SHADOW` requires passing all governance gates.
- `SHADOW` -> `CHALLENGER` requires operator approval.
- `CHALLENGER` -> `CHAMPION` requires explicit `manual_approval_flag=True`
  and an operator name.
- `QUARANTINED` cannot transition to any other stage without operator
  intervention and root-cause resolution.
- Auto-promotion is **forbidden** at every stage.

## Shadow Validation Requirements

A candidate must complete shadow validation before being considered for
challenger promotion. Shadow validation requirements:

1. **Minimum duration:** 168 hours (7 days) of continuous shadow observation.
2. **No safety blocks:** Zero `SAFETY_BLOCK_OBSERVED` events during the
   shadow window.
3. **Final open positions:** Zero open positions at the end of shadow.
4. **Reality gap metrics:** `reality_gap_sharpe` and `reality_gap_drawdown`
   must be present and within acceptable bounds.
5. **Walk-forward status:** `PASS`.
6. **Broker-split status:** `PASS`.

Shadow validation never executes trades. It observes the candidate's
decisions against live market data without submitting orders.

## Manual Approval Gate

Every transition that moves a model closer to champion requires explicit
operator approval:

- `CANDIDATE` -> `SHADOW` requires `ModelLifecycleGovernance.evaluate_candidate()`
  to return `NEEDS_REVIEW` (not `BLOCKED`), followed by operator sign-off.
- `SHADOW` -> `CHALLENGER` requires `ModelRegistry.promote_to_challenger()`
  with an operator name.
- `CHALLENGER` -> `CHAMPION` requires
  `ModelRegistry.require_manual_champion_promotion()` with
  `manual_approval_flag=True` and an operator name.

If `manual_approval_flag` is `False` or missing, the call raises
`PermissionError` and no promotion occurs.

## No Auto Live Deployment Rule

There is **no path** in this sprint by which a model is automatically
deployed to the live runtime.

Specifically:

- `ModelLifecycleGovernance.enforce_no_auto_promotion()` always returns `False`.
- `AlphaFactoryGovernance.never_promote_to_champion()` always returns `False`.
- `AutoCalibrationGovernance.enforce_no_auto_apply()` always returns `False`.
- `ModelRegistry.require_manual_champion_promotion()` raises `PermissionError`
  unless `manual_approval_flag=True`.
- `CalibrationGovernanceResult.apply_automatically` is forced to `False`
  in `__post_init__` regardless of input.

The live runtime config (`config/runtime.yaml`) is never modified by any
of these modules.

## Leakage Prevention

Leakage is the single most critical risk in alpha research. The following
controls are in place:

1. Any candidate with non-empty `leakage_flags` is immediately quarantined
   by `AlphaFactoryGovernance.reject_if_leakage_flags()` and
   `ModelLifecycleGovernance.quarantine()`.
2. Quarantined models cannot be promoted to any other stage without
   operator intervention and root-cause resolution.
3. The `ModelLifecycleReport` explicitly lists quarantined models and
   their quarantine reasons.
4. The alpha factory requires `reality_gap_sharpe` and
   `reality_gap_drawdown` metrics to detect backtest-vs-live divergence
   that may indicate leakage.

## Broker Split Requirement

A candidate must pass broker-split validation before being marked
`READY_FOR_SHADOW`.

Broker-split validation requires the candidate to be evaluated against
multiple brokers (e.g. MetaQuotes-Demo, Exness Demo, ICMarkets Demo) to
ensure the strategy is not overfit to a single broker's data feed.

Status values:

- `PASS` - Candidate passed broker-split validation.
- `FAIL` - Candidate failed broker-split validation. Blocked.
- `PENDING` - Broker-split validation not yet run. Blocked.

## Walk-Forward Requirement

A candidate must pass walk-forward validation before being marked
`READY_FOR_SHADOW`.

Walk-forward validation requires the candidate to be evaluated across
multiple non-overlapping time windows, with metrics aggregated across
windows. This detects time-period overfitting.

Status values:

- `PASS` - Candidate passed walk-forward validation.
- `FAIL` - Candidate failed walk-forward validation. Blocked.
- `PENDING` - Walk-forward validation not yet run. Blocked.

## Drawdown Protection Requirement

A candidate's out-of-sample maximum drawdown must not be significantly
worse than the champion's.

Tolerances:

- Up to 2% worse drawdown (`MAX_DRAWDOWN_TOLERANCE = 0.02`): warning only.
- 2% to 5% worse drawdown: `NEEDS_REVIEW`.
- More than 5% worse drawdown (`MAX_DRAWDOWN_BLOCK = 0.05`): `BLOCKED`.

This protects against candidates that achieve higher returns at the cost
of unacceptable drawdown depth.

## Rollback Policy

If a newly promoted champion exhibits issues in production, the operator
may roll back to the previous champion by:

1. Calling `ModelRegistry.reject_model(new_champion_id, reason="rollback")`
   or `ModelRegistry.quarantine_model(new_champion_id, reason="rollback")`.
2. Calling `ModelRegistry.require_manual_champion_promotion(
   previous_champion_id, approved_by="operator",
   manual_approval_flag=True)` to restore the previous champion.

The registry retains metadata for all previously registered models,
including retired champions, so rollback is always possible as long as
the previous champion's artifact is still available on disk.

The registry itself never loads model binaries - it only tracks metadata.
Operator must ensure the previous champion's artifact file is intact
before initiating a rollback.

## Report Generation

`scripts/audit/model_lifecycle_report.py` generates a report at
`data/audit/model_lifecycle/model_lifecycle_report.{json,md}` containing:

- Current champion metadata (if any).
- List of candidates.
- List of challengers.
- Calibration governance status.
- Alpha factory governance status.
- Lifecycle governance status.
- Blocked promotions.
- Manual approval requirements.
- Final verdict: `MODEL_LIFECYCLE_READY`, `MODEL_LIFECYCLE_WARNINGS`,
  or `MODEL_LIFECYCLE_BLOCKED`.

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
- No model training execution.
- No HPO execution.
- No backtest optimization execution.
- No champion replacement without explicit operator approval.
- No auto-promotion at any stage.
- No auto-apply of calibration.
- No modification of live runtime config.
- No lot size changes.
- No strategy entry logic changes.

## File Inventory

| File | Purpose |
|---|---|
| `titan/production/model_lifecycle_governance.py` | Champion/challenger lifecycle governance |
| `titan/production/auto_calibration_governance.py` | Calibration recommendation governance |
| `titan/production/alpha_factory_governance.py` | Alpha candidate registration and validation |
| `titan/production/model_registry.py` | Metadata-only model registry |
| `scripts/audit/model_lifecycle_report.py` | Report writer |
| `titan/tests/test_model_lifecycle_governance.py` | Tests for lifecycle governance |
| `titan/tests/test_auto_calibration_governance.py` | Tests for calibration governance |
| `titan/tests/test_alpha_factory_governance.py` | Tests for alpha factory governance |
| `titan/tests/test_model_registry.py` | Tests for model registry |
| `titan/tests/test_model_lifecycle_report.py` | Tests for report writer |
| `docs/model_lifecycle/alpha_factory_and_auto_retraining_policy.md` | This document |
