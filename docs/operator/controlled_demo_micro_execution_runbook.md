# TITAN XAU AI - Controlled Demo Micro Execution Runbook (Sprint 9.9.3.44)

## Purpose

This runbook defines the exact operator sequence for a controlled demo
micro execution on MetaQuotes-Demo. **This is DEMO ONLY. Real accounts
are blocked. Z AI must NOT execute any order.**

## Pre-Conditions

Before any demo micro execution:

- **Demo micro readiness:** `DEMO_MICRO_READY_WITH_WARNINGS` or better
- **Environment freeze:** Local Windows environment frozen and matching
- **Environment drift gate:** Not BLOCKED
- **Model parity:** Not FAIL (PASS or NOT_ACCEPTABLE acceptable)
- **Active model hash:** Matches frozen signature
- **Live trading:** BLOCKED (false)
- **Dry run:** True
- **Broker:** MetaQuotes-Demo only
- **Max lot:** 0.01
- **Max open positions:** 1
- **Current open positions:** 0

## Operator Sequence

### Step 1: Run Readiness Check

```
python scripts/operator/check_demo_micro_readiness.py --check-only
```

Verify: `DEMO_MICRO_READY_WITH_WARNINGS` or better, 0 blockers.

### Step 2: Run Gate Check

```
python scripts/operator/run_controlled_demo_micro_execution.py --check-only
```

Verify: `DEMO_MICRO_GATE_PASS` or `DEMO_MICRO_GATE_PASS_WITH_WARNINGS`, 0 blockers.

### Step 3: Dry-Arm

```
python scripts/operator/run_controlled_demo_micro_execution.py --dry-arm
```

Verify: Gate armed, no order sent.

### Step 4: Build Request Preview

```
python scripts/operator/run_controlled_demo_micro_execution.py --build-request
```

Review the generated order request preview at:
`data/audit/demo_micro_execution/demo_micro_order_request_preview.json`

Verify: No order was sent. Preview only.

### Step 5: Check Force-Close Readiness

```
python scripts/operator/check_demo_micro_force_close_readiness.py
```

Verify: `DEMO_MICRO_FORCE_CLOSE_READY`.

### Step 6: Execute Once (LOCAL OPERATOR ONLY — NOT Z AI)

**Z AI must NOT run this command.** The local operator on their Windows
machine may run:

```
python scripts/operator/run_controlled_demo_micro_execution.py --execute-once \
  --i-understand-demo-risk \
  --confirm-symbol XAUUSD \
  --confirm-lot 0.01 \
  --confirm-broker MetaQuotes-Demo \
  --confirm-one-order-only \
  --confirm-not-live \
  --confirm-environment-locked \
  --confirm-model-parity-pass
```

All confirmation flags are required. Missing any flag causes refusal.

## Safety Rules

- **Demo only:** Real accounts are blocked
- **MetaQuotes-Demo only:** No other broker
- **Max lot 0.01:** Hard cap
- **One order only:** No martingale, grid, or averaging
- **No overnight/weekend hold** unless explicitly approved in a future sprint
- **Environment must match frozen local Windows signature**
- **Model hash drift blocks execution**
- **Model parity must not fail**
- **XGBoost parity NOT_AVAILABLE is acceptable** only while active original
  XGBoost is unchanged, hash-locked, and inference passes
- **Dependency/model/self-healing audits must not be blocked**
- **Z AI must not execute orders**

## How to Stop/Kill Runtime

1. Press `Ctrl+C` to stop the TITAN runtime
2. If position remains open, manually close it in MT5 terminal
3. Run kill-switch flatten command if available
4. Verify no open positions remain

## How to Verify No Open Positions

Check `position_sync.open_positions` — must be empty (0 positions).

## How to Collect Audit Reports

All audit reports are written to `data/audit/demo_micro_execution/`:
- `demo_micro_execution_check.json/md` — gate check report
- `demo_micro_order_request_preview.json/md` — order preview
- `force_close_readiness.json/md` — force-close readiness

## What Files Are Safe to Commit

- Source code changes
- Audit report JSON/MD files (do NOT contain raw account data)
- Documentation

## Raw/Private Journal Files Must NOT Be Committed

- `data/runtime/titan_journal.jsonl` — raw runtime journal
- `data/audit/demo_micro/demo_micro_journal.jsonl` — raw demo micro journal
- `.env` — environment file
- Any file containing MT5 login/password/server/account

## No Live/Commercial/World No.1 Claim

**Demo micro execution does NOT prove:**
- Live trading readiness
- Commercial capability
- World no.1 proof
- Real market performance

**Live trading remains BLOCKED.**
