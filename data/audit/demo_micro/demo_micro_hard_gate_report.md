# Sprint 9.9 — Demo Micro Hard Gate

**Verdict: DEMO_MICRO_BLOCKED**

## Checks

| Check | Passed |
|---|---|
| mt5_reachable | ✗ |
| account_demo | ✗ |
| demo_micro_enabled | ✗ |
| arm_token_present | ✗ |
| not_real_account | ✓ |
| max_lot_ok | ✓ |
| max_positions_ok | ✓ |
| max_trades_ok | ✓ |
| force_close_on_end | ✓ |
| kill_switch_normal | ✓ |
| market_open | ✓ |
| demo_micro_readiness_ok | ✓ |

## Reasons

- MT5 not reachable (Linux or not installed)
- demo_micro.enabled=false (default)
- TITAN_DEMO_MICRO_ARMED not set to 1
