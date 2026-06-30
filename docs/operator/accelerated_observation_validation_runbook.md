# TITAN XAU AI - Accelerated Observation Validation Runbook (Sprint 9.9.3.42.1)

## Purpose

This runbook explains how to use the accelerated observation validation
harness for same-day technical validation. **This does NOT replace true
7-day forward observation.** It only allows same-day technical validation.

## What It Proves

- The observation pipeline (ForwardObservationEngine, ObservationScorecardEngine) works correctly
- The institutional pipeline (SignalExecutionBridge, RegimeDetection, BrokerCompatibilityMatrix, RuntimeHealthMonitor, SecurityGate) produces correct journal events
- The broker observation gate correctly allows MetaQuotes-Demo and blocks others
- The daily scorecard and finalizer pipelines work correctly
- No forbidden execution evidence (order_send, live_trading, DEMO_MICRO_EXECUTE, raw_mt5_probe) appears
- The dry-run runtime produces signals, intents, and dry-run orders safely

## What It Does NOT Prove

- Real 7-day forward observation results
- Live trading readiness
- Commercial multi-broker capability
- World no.1 trading system proof
- Real market performance
- Real broker fill quality
- Real slippage/spread behavior

## Exact Commands

### Check-Only Mode (Default)

```
python scripts/operator/run_accelerated_observation_validation.py --check-only
```

Verifies dry_run=true, live_trading=false, broker gate passes.

### Real Short Observation Mode

```
python scripts/operator/run_accelerated_observation_validation.py --real-short --minutes 60
```

Runs a short dry-run observation window (minimum 30 minutes configured).
Produces `real_short_observation_report.{json,md}`.

**Warning:** This is NOT full 7-day forward evidence.

### Replay Validation Mode

```
python scripts/operator/run_accelerated_observation_validation.py --replay --days 7
```

Generates replay-style validation from canonical data.
Produces `replay_7day_validation.{json,md}`.

**Warning:** This is historical replay, NOT real forward evidence.

### Combined Mode

```
python scripts/operator/run_accelerated_observation_validation.py --combined --minutes 60 --replay-days 7
```

Runs both modes and produces a final accelerated report.
Produces `accelerated_observation_final_report.{json,md}`.

### Accelerated Scorecard

```
python scripts/operator/run_accelerated_observation_scorecard.py
```

Reads accelerated observation reports and produces a scorecard that
clearly separates real_short, replay, and true_forward metrics.

## Safe Modes

All modes are safe:
- dry_run only
- live_trading=false
- No MT5 order_send
- No DEMO_MICRO_EXECUTE
- No raw_mt5_probe
- No market execution adapter
- No live orders

## How to Interpret PASS / WARN / FAIL

### Real Short Verdicts

| Verdict | Meaning |
|---|---|
| `REAL_SHORT_PASS` | Short observation produced signals/intents safely |
| `REAL_SHORT_WARN` | Short observation has warnings (e.g. regime placeholder) |
| `REAL_SHORT_FAIL` | Forbidden evidence detected (order_send, live_trading) |
| `REAL_SHORT_INSUFFICIENT_DATA` | No signals or intents generated |

### Replay Verdicts

| Verdict | Meaning |
|---|---|
| `REPLAY_VALIDATION_PASS` | Replay produced signals/intents safely |
| `REPLAY_VALIDATION_WARN` | Replay has warnings (e.g. regime placeholder, not real forward) |
| `REPLAY_VALIDATION_FAIL` | Forbidden evidence detected |
| `REPLAY_VALIDATION_INSUFFICIENT_DATA` | No signals generated in replay |

### Combined Verdicts

| Verdict | Meaning |
|---|---|
| `ACCELERATED_VALIDATION_PASS` | Both modes passed with no warnings |
| `ACCELERATED_VALIDATION_PASS_WITH_WARNINGS` | Both modes passed with approved warnings only |
| `ACCELERATED_VALIDATION_FAIL` | Forbidden evidence or unapproved warnings |
| `ACCELERATED_VALIDATION_INSUFFICIENT_DATA` | Insufficient data in both modes |

## Approved Warnings

The following warnings are approved for accelerated validation:

- `REGIME_GATE_WIRED_BUT_PLACEHOLDER_CONTEXT` — Regime gate uses placeholder scores
- `REPLAY_NOT_REAL_FORWARD_EVIDENCE` — Replay is not real forward observation
- `REAL_SHORT_NOT_FULL_7_DAY_EVIDENCE` — Short observation is not full 7-day

Any other warning is unapproved and blocks PASS.

## When Controlled Demo Micro Readiness Can Be Considered

Controlled demo micro readiness may be considered ONLY after:

1. Accelerated validation passes (PASS or PASS_WITH_WARNINGS)
2. True 7-day forward observation is completed separately
3. Operator explicitly approves in writing
4. Live trading remains BLOCKED throughout

## Live Trading Still Blocked

**Live trading remains BLOCKED.** There is no path in the accelerated
validation harness by which live trading can be enabled.

## World No.1 Claim Still Not Allowed

**Do NOT claim world no.1, live readiness, or commercial capability
based on accelerated validation.** Accelerated validation is technical
pipeline validation only. It does not prove real market performance.
