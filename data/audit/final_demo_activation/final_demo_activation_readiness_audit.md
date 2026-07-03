# TITAN XAU AI - Final Demo Activation Readiness Audit (v2.8.5)

**Verdict:** **FINAL_DEMO_ACTIVATION_READY_SUPERVISED**

**Final demo activation allowed:** **True**

**Timestamp:** 2026-07-03T06:10:17.070339+00:00

**Blockers:** 0

**Warnings:** 5

## Environment

| Field | Value |
|---|---|
| python_version | 3.12.13 |
| platform | Linux-5.10.134-013.8.3.kangaroo.al8.x86_64-x86_64-with-glibc2.41 |
| is_windows | False |
| git_commit | 93d3b294417b |
| git_branch | main |
| git_dirty | True |

## MT5 Environment (read-only)

| Field | Value |
|---|---|
| mt5_available | False |
| initialized | False |
| account_server |  |
| account_type |  |
| symbol_available | False |
| spread_usd | 0.0 |
| open_positions_count | 0 |
| open_xauusd_positions | 0 |
| pending_orders_count | 0 |
| pending_xauusd_orders | 0 |
| error | MetaTrader5 not installed: No module named 'MetaTrader5' |

## Required Gates

| Gate | Verdict | Pass |
|---|---|---|
| model_health | MODEL_ARTIFACT_HEALTH_PASS_WITH_WARNINGS | True |
| feature_parity | FEATURE_PARITY_PASS | True |
| runtime_safety | RUNTIME_SAFETY_GATE_PASS | True |
| growth_profile | PROP_CHALLENGE_GROWTH_PROFILE_PASS | True |
| production_closure | PRODUCTION_CLOSURE_READY_WITH_SAFE_DEFAULTS | True |
| autonomous_readiness |  | False |
| build_request | PASS | True |
| execution_geometry |  | N/A |

## Build-Request Status

| Field | Value |
|---|---|
| mode | build_request |
| verdict | PASS |
| normalized_verdict | PASS |
| request_status | READY_FOR_SUPERVISED_OPERATOR_ARM |
| execution_now_allowed | False |
| execution_blocker | OPERATOR_ARM_TOKEN_REQUIRED |

## Operator Token

| Field | Value |
|---|---|
| token_exists | False |
| stale | False |
| age_seconds | 0 |

## Receipt/Forensics

| Field | Value |
|---|---|
| active_receipt_exists | False |
| stale_receipt_non_blocking | True |


## Warnings

- NON_WINDOWS_ENVIRONMENT: Linux - audit can run but execution requires Windows MetaQuotes-Demo MT5 terminal
- GIT_WORKING_TREE_DIRTY: uncommitted changes present
- MT5_NOT_AVAILABLE: MetaTrader5 module not installed. Audit can run in read-only mode but MT5 environment checks skipped. Operator must run this audit on Windows with MT5 terminal running.
- AUTONOMOUS_READINESS_AUDIT_MISSING - run autonomous_demo_readiness_audit.py
- EXECUTION_GEOMETRY_AUDIT_MISSING - non-blocking

## OK Checks

- Git commit: 93d3b294417b
- No stale operator token
- Model health: MODEL_ARTIFACT_HEALTH_PASS_WITH_WARNINGS, failed_required=0
- Feature parity: FEATURE_PARITY_PASS
- Runtime safety: RUNTIME_SAFETY_GATE_PASS
- Growth profile: PROP_CHALLENGE_GROWTH_PROFILE_PASS
- Production closure: PRODUCTION_CLOSURE_READY_WITH_SAFE_DEFAULTS, blockers=0
- Build-request: PASS, request_status=READY_FOR_SUPERVISED_OPERATOR_ARM, execution_now_allowed=False, execution_blocker=OPERATOR_ARM_TOKEN_REQUIRED
- Max lot: 0.01
- Max open positions: 1
- Base risk per trade: 0.005
- Min RR: 2.0
- Preferred RR: 3.0
- Forbidden strategy disabled: martingale
- Forbidden strategy disabled: grid
- Forbidden strategy disabled: averaging_down
- Forbidden strategy disabled: loss_based_lot_multiplier
- Forbidden strategy disabled: forced_recovery
- Forbidden strategy disabled: lot_increase_after_loss
- No active receipt

## Safety

- order_send_called: False
- position_modified: False
- token_created: False

> This audit is READ-ONLY. It never calls mt5.order_send, never creates tokens, never modifies positions.
