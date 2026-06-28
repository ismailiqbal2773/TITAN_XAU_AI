# Sprint 9.9.3.8 — Multi-Year Real Data Validation

**Timestamp:** 2026-06-28T14:12:49.550829+00:00
**Chunks processed:** 26
**Sources:** canonical, exness, fbs, fundednext, icmarkets
**Years:** 2020, 2021, 2022, 2023, 2024, 2025
**Timeframe:** H1
**Total rows tested:** 152,161

## Combined Results (All Years, All Sources)

| Config | Net PnL | Max DD | PF | Win% | Trades | Sharpe | Profit% |
|---|---|---|---|---|---|---|---|
| NO_GOVERNANCE | $-43250.07 | $2127.71 | 0.6273 | 36.72% | 22575 | -5.8923 | -432.5% |
| SPRINT_9_9_3_2_PROP_FIRM_STRICT | $25812.9 | $75.92 | 4.5146 | 68.38% | 8038 | 7.806 | 258.13% |
| SPRINT_9_9_3_3_RETAIL_SAFE | $36915.16 | $98.44 | 4.4082 | 69.79% | 11284 | 7.9997 | 369.15% |
| SPRINT_9_9_3_3_PROP_FIRM_STRICT | $27781.94 | $79.05 | 5.0272 | 70.68% | 8830 | 8.2777 | 277.82% |
| SPRINT_9_9_3_3_INSTITUTIONAL | $19685.99 | $87.88 | 4.3839 | 68.39% | 7258 | 7.4011 | 196.86% |

## Year-by-Year Summary (PROP_FIRM_STRICT)

| Year | Net PnL | Max DD | PF | Win% | Trades | Target 10% |
|---|---|---|---|---|---|---|
| 2020 | $2350.98 | $40.96 | 5.338 | 67.76% | 887 | YES |
| 2021 | $2242.82 | $27.0 | 4.1508 | 71.63% | 1181 | YES |
| 2022 | $2606.02 | $35.91 | 3.8886 | 70.75% | 1340 | YES |
| 2023 | $2476.13 | $27.44 | 4.6801 | 74.98% | 1363 | YES |
| 2024 | $5375.79 | $58.17 | 4.6154 | 70.67% | 1967 | YES |
| 2025 | $12730.2 | $79.05 | 5.9287 | 68.55% | 2092 | YES |

## Broker Split (PROP_FIRM_STRICT, All Years)

| Broker | Net PnL | Max DD | PF | Win% | Trades |
|---|---|---|---|---|---|
| canonical | $3936.08 | $67.05 | 5.138 | 65.47% | 1309 |
| exness | $4945.97 | $50.3 | 7.5383 | 82.77% | 1219 |
| icmarkets | $7751.39 | $75.21 | 4.5899 | 69.79% | 2770 |
| fundednext | $4055.08 | $75.85 | 5.546 | 68.91% | 936 |
| fbs | $7093.42 | $79.05 | 4.3152 | 69.22% | 2596 |

## Cost Stress Summary (PROP_FIRM_STRICT, All Years)

| Scenario | Net PnL | Max DD | PF | Win% | Trades | Target |
|---|---|---|---|---|---|---|
| NORMAL_COST | $27781.94 | $79.05 | 5.0272 | 70.68% | 8830 | YES |
| HIGH_SPREAD | $20010.01 | $83.56 | 4.4262 | 69.48% | 6596 | YES |
| HIGH_SLIPPAGE | $20046.07 | $97.05 | 2.8294 | 59.28% | 8358 | YES |
| LOW_LIQUIDITY | $17445.28 | $92.83 | 3.3272 | 63.53% | 6566 | YES |
| WORST_BROKER | $13244.71 | $86.91 | 2.9021 | 60.32% | 5517 | YES |
| HARSH_COMBINED | $9771.22 | $111.68 | 2.7219 | 60.32% | 4128 | YES |

## Funded Target Summary

| Config | Years Tested | Years Target Achieved | Years Rule Breach | Pass Rate |
|---|---|---|---|---|
| NO_GOVERNANCE | 6 | 0 | 6 | 0.0% |
| SPRINT_9_9_3_2_PROP_FIRM_STRICT | 6 | 6 | 0 | 100.0% |
| SPRINT_9_9_3_3_RETAIL_SAFE | 6 | 6 | 0 | 100.0% |
| SPRINT_9_9_3_3_PROP_FIRM_STRICT | 6 | 6 | 0 | 100.0% |
| SPRINT_9_9_3_3_INSTITUTIONAL | 6 | 6 | 0 | 100.0% |

## Lower Timeframe Availability

**M30 total rows:** 325,459

**M15 total rows:** 459,477

**M5 total rows:** 501,955

**Recommendation:** defer_to_next_sprint

**Note:** M5/M15/M30 full validation deferred to next sprint. 2025 lightweight validation feasible.

## Safety

| Item | Value |
|---|---|
| demo_micro_execute_run | NO |
| mt5_order_send_called | NO |
| live_demo_path_changed | NO |
| governance_wired | NO |
| strategy_changed | NO |
| config_changed | NO |
| models_retrained | NO |
| no_martingale_grid_averaging | YES |
| working_tree_clean | YES |
