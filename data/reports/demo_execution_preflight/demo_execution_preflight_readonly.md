# Demo Execution Preflight Read-Only (Module 7)

**2026-07-07T06:56:20.805293+00:00**

## Verdict: DEMO_EXECUTION_BLOCKED_PENDING_CTO_APPROVAL

Demo execution is BLOCKED. CTO approval and operator token are required.

## Checks

| Check | Value |
|---|---|
| cto_approval_file_missing | True |
| operator_token_missing | True |
| production_ready_false | True |
| live_trading_false | True |
| funded_trading_false | True |
| dry_run_true | True |
| order_send_disabled | True |
| max_lot_cap | 0.01 |
| max_open_positions | 1 |
| max_trades_per_day | 2 |
| emergency_stop_available | True |
| kill_switch_available | True |
| daily_dd_limit | 0.03 |
| total_dd_limit | 0.08 |
| margin_cap | 0.2 |
| broker_allowed | exness |
| symbol_allowed | XAUUSD |

## Safety
- No token
- No order_send
- No trading activation
- CTO approval required
- Operator token required
