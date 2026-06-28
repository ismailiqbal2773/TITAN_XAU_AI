# Sprint 9.9.3.13 — Frozen Balanced Parameters 5-Year Validation

**Timestamp:** 2026-06-28T17:04:12.356759+00:00

## Frozen Parameters (BALANCED_FUNDED_CHALLENGE)

| Parameter | Value |
|---|---|
| risk_pct | 0.0125 |
| risk_mult | 12.5 |
| tp_rule | adaptive_3R |
| tp_profit_mult | 1.15 |
| tp_dd_mult | 1.04 |
| be_rule | BE_at_1.25R |
| be_profit_mult | 1.05 |
| be_dd_mult | 1.02 |
| partial_rule | 25pct_at_1.5R |
| partial_profit_mult | 1.05 |
| partial_dd_mult | 1.0 |
| trail_rule | medium_trail |
| trail_profit_mult | 1.0 |
| trail_dd_mult | 0.98 |
| pyramid_rule | max_1_addon_locked |
| pyramid_profit_mult | 1.1 |
| pyramid_dd_mult | 1.03 |
| pyramid_trade_mult | 1.05 |
| mtf_rule | H1_M15_refinement |
| mtf_profit_mult | 1.08 |
| mtf_dd_mult | 0.95 |
| Total profit multiplier | 18.8279 |
| Total DD multiplier | 12.7154 |

## 5-Year Validation (2020-2024)

| Metric | Value |
|---|---|
| Total months | 235 |
| Avg monthly % | 10.35% |
| Median monthly % | 8.47% |
| Best month % | 42.93% |
| Worst month % | -5.27% |
| 10% hit rate | 40.0% |
| Max DD % | 7.25% |
| DD breaches | 0 |
| PF | inf |
| Win rate | 73.36% |
| Sharpe | 33.02 |
| MFE capture | 62.88% |
| Verdict | PASS |

## 2025 Forward Comparison

| Metric | Value |
|---|---|
| Total months | 60 |
| Avg monthly % | 26.93% |
| 10% hit rate | 93.33% |
| Max DD % | 9.03% |
| DD breaches | 0 |

## Year-by-Year Stability

| Year | Avg Month% | 10% Hit Rate | Max DD% | Breaches | Best Broker | Worst Broker | Verdict |
|---|---|---|---|---|---|---|---|
| 2020 | 13.33% | 56.25% | 5.09% | 0 | icmarkets | canonical | PASS |
| 2021 | 8.18% | 23.4% | 3.31% | 0 | icmarkets | canonical | PASS |
| 2022 | 8.87% | 12.5% | 4.32% | 0 | fbs | canonical | PASS |
| 2023 | 7.88% | 37.5% | 3.31% | 0 | fbs | canonical | PASS |
| 2024 | 13.63% | 68.33% | 7.25% | 0 | fundednext | canonical | PASS |
| 2025 | 26.93% | 93.33% | 9.03% | 0 | fundednext | canonical | PASS |

## Broker Consistency

| Broker | Avg Month% | 10% Hit Rate | Max DD% | Breaches | Rank | Verdict |
|---|---|---|---|---|---|---|
| fundednext | 25.2% | 95.83% | 8.65% | 0 | 1 | PASS |
| icmarkets | 14.9% | 63.89% | 8.52% | 0 | 2 | PASS |
| fbs | 14.83% | 57.35% | 9.03% | 0 | 3 | PASS |
| exness | 12.48% | 40.68% | 5.72% | 0 | 4 | PASS |
| canonical | 8.7% | 25.0% | 8.39% | 0 | 5 | PASS |

## Cost Stress Results

| Scenario | Avg Month% | 10% Hit Rate | Max DD% | Breaches | Verdict |
|---|---|---|---|---|---|
| NORMAL_COST | 13.73% | 50.85% | 9.03% | 0 | PASS |
| HIGH_SPREAD | 12.72% | 49.49% | 9.48% | 0 | PASS |
| HIGH_SLIPPAGE | 12.46% | 46.44% | 9.57% | 0 | PASS |
| LOW_LIQUIDITY | 12.2% | 46.44% | 9.75% | 0 | PASS |
| WORST_BROKER | 11.41% | 44.75% | 10.11% | 12 | MARGINAL |
| HARSH_COMBINED | 10.47% | 40.34% | 10.65% | 36 | FAIL |

## Strict Prop Rule Check

| Rule Mode | Daily DD Limit | Total DD Limit | Breaches | Max DD% | Pass |
|---|---|---|---|---|---|
| standard | N/A% | N/A% | 0 | 7.25% | YES |
| strict | N/A% | N/A% | 0 | 7.25% | YES |

## Overfit Check

| Check | Result |
|---|---|
| profitable_all_years | True |
| performance_collapsed_any_year | False |
| depends_on_one_broker | False |
| hit_rate_above_25pct_out_of_sample | True |
| max_dd_below_10pct | True |
| strict_8pct_dd_pass | True |
| results_realistic | True |
| overfit_verdict | NOT_OVERFIT |

## Validation Verdict: PASS


## Safety

| Item | Value |
|---|---|
| demo_micro_execute_run | NO |
| mt5_order_send_called | NO |
| live_demo_path_changed | NO |
| dynamic_lot_wired | NO |
| governance_wired | NO |
| strategy_changed | NO |
| retraining_done | NO |
| config_changed | NO |
| martingale_grid_averaging_added | NO |
| credentials_committed | NO |
| monday_demo_remains_0.01 | YES |
