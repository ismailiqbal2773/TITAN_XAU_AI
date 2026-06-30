# TITAN XAU AI - Environment Freeze & Dependency Drift Runbook (Sprint 9.9.3.43.1)

## Why Auto-Updating Trading Libraries Is Dangerous

Auto-updating trading libraries (xgboost, scikit-learn, pandas, numpy)
can silently break model compatibility. A minor version change in
scikit-learn can change LogisticRegression internals, causing
InconsistentVersionWarning and potentially different predictions.
A major version change in XGBoost can change the serialized model format,
making the model unloadable.

**Never auto pip install or auto-upgrade inside the trading runtime.**

## Why Auto pip install Must Not Run Inside Trading Runtime

The trading runtime must be deterministic. If it auto-installs packages,
the environment changes between runs, making results non-reproducible.
This can cause:
- Model loading failures
- Prediction differences
- Silent strategy changes
- Non-deterministic behavior

## How to Freeze the Current Working Environment

```
python scripts/audit/freeze_current_environment.py
```

This generates:
- `config/environment/requirements_observed_lock.txt` — observed package versions
- `config/environment/environment_signature.json` — full signature with hashes
- `config/environment/environment_signature.md` — human-readable signature

**Do NOT overwrite `requirements.txt` automatically.** The lock file is
for observation only. To update `requirements.txt`, the operator must
explicitly review and approve the change.

## How to Check Drift Before Demo Execution

The `EnvironmentDriftGate` (titan/production/environment_drift_gate.py)
compares the current runtime environment against the frozen signature.
It detects:
- Missing critical packages
- Changed major/minor package versions
- Python version drift
- Model file hash drift
- Model file missing
- Unknown/unfrozen environment

The demo micro readiness controller (`check_demo_micro_readiness.py`)
includes the drift gate as a required check. If the drift gate returns
`ENVIRONMENT_LOCK_BLOCKED`, demo micro readiness is blocked.

## How to Handle XGBoost/sklearn Warnings

1. **Freeze the environment** to capture the current working state.
2. **Run model artifact compatibility audit** to verify models load and inference passes.
3. **Run model normalization** to create candidate artifacts in current-environment format.
4. **Run prediction parity audit** to verify candidates produce same predictions as originals.
5. **If parity passes**, the warnings are controlled — the models work correctly despite version mismatch.
6. **If parity fails**, future model replacement is BLOCKED until parity is resolved.

## Normalized Candidates Are Not Active Models

Normalized candidate artifacts are stored in `data/model_candidates/normalized_artifacts/`.
They are NOT active production models. They must NOT replace active artifacts without:
1. Prediction parity proof
2. Separate operator approval
3. Explicit model registry update

## Model Replacement Requires Parity Pass and Separate Approval

Model replacement is a separate process that requires:
1. Prediction parity audit passing (MODEL_PARITY_PASS or MODEL_PARITY_PASS_WITH_WARNINGS)
2. Explicit operator approval via ModelRegistry.require_manual_champion_promotion()
3. No auto-promotion, no auto-replacement

## Crash Impossible Claim Forbidden

The system does NOT claim crash is impossible. The correct claim is:

**"Crash-tolerant fail-closed runtime with bounded recovery."**

The system:
- Catches runtime exceptions
- Fails closed (no order_send after failure)
- Has bounded recovery (no infinite restart)
- Journals all failure events
- Escalates to kill-switch on repeated failures

## Live Trading Remains Blocked

Live trading remains BLOCKED. There is no path in this sprint by which
live trading can be enabled.
