# Sprint 9.9.2 — Demo Micro Hard Gate (Config Fix)

**Verdict: DEMO_MICRO_BLOCKED**

## Config Diagnostics

| Field | Value |
|---|---|
| config_path_used | /home/z/my-project/TITAN_XAU_AI/config/runtime.yaml |
| demo_micro_config_found | True |
| demo_micro_enabled_raw | False |
| demo_micro_enabled_effective | False |

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
- demo_micro.enabled=False (config)
- TITAN_DEMO_MICRO_ARMED not set to 1
