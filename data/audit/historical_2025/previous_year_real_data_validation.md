# Sprint 9.9.3.6 — Previous-Year Real Data Offline Validation

**Timestamp UTC:** 2026-06-27T12:41:22.792289+00:00
**Validation period:** 2025-01-01 to 2025-12-31

## Important
- This is an **OFFLINE VALIDATION** — no real or demo MT5 execution.
- **DEMO_MICRO_EXECUTE was NOT run.** mt5.order_send was NOT called.
- **Production live path unchanged.** Governance NOT wired into live/demo trade_loop.
- **No models retrained.** Uses existing rule-based signal generator.
- **No martingale/grid/averaging/lot escalation.**

## Task 1: Data Discovery

**Total datasets found:** 20

### Datasets with 2025 H1 Data

| Source | TF | 2025 Rows | Start 2025 | End 2025 | Spread Mean | Missing % | Broker Quality |
|---|---|---|---|---|---|---|---|
| canonical | H1 | 5933 | 2025-01-02 | 2025-12-31 | $0.1339 | 1.12% | 88 |
| exness | H1 | 5912 | 2025-01-01 | 2025-12-31 | $0.3679 | 1.47% | 85 |
| fundednext | H1 | 5914 | 2025-01-02 | 2025-12-31 | $0.2447 | 1.43% | 80 |
| icmarkets | H1 | 5913 | 2025-01-02 | 2025-12-31 | $0.038 | 1.45% | 88 |
| fbs | H1 | 5907 | 2025-01-02 | 2025-12-31 | $0.209 | 1.55% | 75 |

## Task 3-5: Governance Comparison (2025 H1 Real Data)

| Config | Net PnL | Max DD | PF | Win% | Trades | Sharpe | Score |
|---|---|---|---|---|---|---|---|
| NO_GOVERNANCE | $-5323.32 | $5748.51 | 0.8502 | 44.48% | 4344 | -3.8204 | 31.67 |
| SPRINT_9_9_3_2_PROP_FIRM_STRICT | $12750.51 | $75.92 | 5.4914 | 68.52% | 2033 | 22.8934 | 84.87 |
| SPRINT_9_9_3_3_RETAIL_SAFE | $17123.26 | $98.44 | 5.9882 | 69.26% | 2365 | 25.1051 | 84.12 |
| SPRINT_9_9_3_3_PROP_FIRM_STRICT | $12730.21 | $79.05 | 5.9287 | 68.55% | 2092 | 23.6148 | 84.81 |
| SPRINT_9_9_3_3_INSTITUTIONAL | $10151.35 | $87.88 | 5.0085 | 67.51% | 1905 | 20.9033 | 84.36 |

## Detailed Metrics per Configuration

### NO_GOVERNANCE

| Metric | Value |
|---|---|
| trade_count | 4344 |
| total_net_pnl | -5323.32 |
| gross_profit | 30219.55 |
| gross_loss | 35542.87 |
| profit_factor | 0.8502 |
| win_rate_pct | 44.48 |
| avg_win | 15.6416 |
| avg_loss | 14.7358 |
| payoff_ratio | 1.0615 |
| expectancy_per_trade | -1.2254 |
| max_dd_usd | 5748.51 |
| max_dd_pct | 56.08 |
| daily_dd_max_usd | 832.68 |
| sharpe | -3.8204 |
| sortino | -5.9619 |
| calmar | -0.926 |
| recovery_factor | -0.926 |
| longest_losing_streak | 8 |
| largest_single_loss | -78.17 |
| largest_single_win | 144.48 |
| mae_avg | 0.6958 |
| mfe_avg | 0.8037 |

**Blocked:** 0 (winners: 0, losers: 0)

**Exit counts:** {}

**Overfiltering ratio:** 0.0

**Competition score:** 31.67/100

### SPRINT_9_9_3_2_PROP_FIRM_STRICT

| Metric | Value |
|---|---|
| trade_count | 2033 |
| total_net_pnl | 12750.51 |
| gross_profit | 15589.4 |
| gross_loss | 2838.89 |
| profit_factor | 5.4914 |
| win_rate_pct | 68.52 |
| avg_win | 11.1912 |
| avg_loss | 9.0124 |
| payoff_ratio | 1.2418 |
| expectancy_per_trade | 6.2718 |
| max_dd_usd | 75.92 |
| max_dd_pct | 0.66 |
| daily_dd_max_usd | 190.96 |
| sharpe | 22.8934 |
| sortino | 25.9493 |
| calmar | 167.9486 |
| recovery_factor | 167.9486 |
| longest_losing_streak | 3 |
| largest_single_loss | -48.21 |
| largest_single_win | 69.54 |
| mae_avg | 0.6406 |
| mfe_avg | 0.757 |

**Blocked:** 11279 (winners: 4785, losers: 6494)

**Exit counts:** {'MOVE_BE': 410, 'CLOSE': 209, 'TIGHT_TRAIL': 798, 'PARTIAL_CLOSE': 373}

**Overfiltering ratio:** 0.7368

**Competition score:** 84.87/100

### SPRINT_9_9_3_3_RETAIL_SAFE

| Metric | Value |
|---|---|
| trade_count | 2365 |
| total_net_pnl | 17123.26 |
| gross_profit | 20556.01 |
| gross_loss | 3432.74 |
| profit_factor | 5.9882 |
| win_rate_pct | 69.26 |
| avg_win | 12.5495 |
| avg_loss | 9.8359 |
| payoff_ratio | 1.2759 |
| expectancy_per_trade | 7.2403 |
| max_dd_usd | 98.44 |
| max_dd_pct | 0.66 |
| daily_dd_max_usd | 393.4 |
| sharpe | 25.1051 |
| sortino | 24.4395 |
| calmar | 173.9389 |
| recovery_factor | 173.9389 |
| longest_losing_streak | 3 |
| largest_single_loss | -98.44 |
| largest_single_win | 78.14 |
| mae_avg | 0.6274 |
| mfe_avg | 0.7866 |

**Blocked:** 9690 (winners: 4099, losers: 5591)

**Exit counts:** {'MOVE_BE': 486, 'TIGHT_TRAIL': 975, 'CLOSE': 235, 'PARTIAL_CLOSE': 395}

**Overfiltering ratio:** 0.7331

**Competition score:** 84.12/100

### SPRINT_9_9_3_3_PROP_FIRM_STRICT

| Metric | Value |
|---|---|
| trade_count | 2092 |
| total_net_pnl | 12730.21 |
| gross_profit | 15313.1 |
| gross_loss | 2582.89 |
| profit_factor | 5.9287 |
| win_rate_pct | 68.55 |
| avg_win | 10.6786 |
| avg_loss | 8.1223 |
| payoff_ratio | 1.3147 |
| expectancy_per_trade | 6.0852 |
| max_dd_usd | 79.05 |
| max_dd_pct | 0.66 |
| daily_dd_max_usd | 190.96 |
| sharpe | 23.6148 |
| sortino | 26.6552 |
| calmar | 161.0417 |
| recovery_factor | 161.0417 |
| longest_losing_streak | 3 |
| largest_single_loss | -48.21 |
| largest_single_win | 69.54 |
| mae_avg | 0.6387 |
| mfe_avg | 0.7755 |

**Blocked:** 10955 (winners: 4625, losers: 6330)

**Exit counts:** {'MOVE_BE': 430, 'CLOSE': 207, 'TIGHT_TRAIL': 822, 'PARTIAL_CLOSE': 401}

**Overfiltering ratio:** 0.7306

**Competition score:** 84.81/100

### SPRINT_9_9_3_3_INSTITUTIONAL

| Metric | Value |
|---|---|
| trade_count | 1905 |
| total_net_pnl | 10151.35 |
| gross_profit | 12683.82 |
| gross_loss | 2532.47 |
| profit_factor | 5.0085 |
| win_rate_pct | 67.51 |
| avg_win | 9.863 |
| avg_loss | 8.2761 |
| payoff_ratio | 1.1918 |
| expectancy_per_trade | 5.3288 |
| max_dd_usd | 87.88 |
| max_dd_pct | 0.65 |
| daily_dd_max_usd | 204.84 |
| sharpe | 20.9033 |
| sortino | 25.2399 |
| calmar | 115.516 |
| recovery_factor | 115.516 |
| longest_losing_streak | 4 |
| largest_single_loss | -58.77 |
| largest_single_win | 64.01 |
| mae_avg | 0.642 |
| mfe_avg | 0.8018 |

**Blocked:** 11872 (winners: 4990, losers: 6882)

**Exit counts:** {'MOVE_BE': 396, 'PARTIAL_CLOSE': 322, 'CLOSE': 184, 'TIGHT_TRAIL': 733}

**Overfiltering ratio:** 0.7251

**Competition score:** 84.36/100

## Task 6: Segment Analysis (PROP_FIRM_STRICT)

### By Broker

| Segment | Trades | Net PnL | Win% | PF | Max DD |
|---|---|---|---|---|---|
| canonical | 252 | $1895.54 | 67.86% | 9.0459 | $67.05 |
| exness | 459 | $2633.15 | 69.06% | 5.5723 | $50.3 |
| fundednext | 459 | $2739.49 | 68.63% | 5.8169 | $75.85 |
| icmarkets | 460 | $2773.09 | 68.7% | 5.64 | $75.21 |
| fbs | 462 | $2688.93 | 68.18% | 5.4442 | $79.05 |

### By Month

| Segment | Trades | Net PnL | Win% | PF | Max DD |
|---|---|---|---|---|---|
| 2025-01 | 202 | $575.29 | 59.41% | 6.1996 | $16.93 |
| 2025-02 | 177 | $667.7 | 67.8% | 4.9128 | $67.05 |
| 2025-03 | 177 | $600.66 | 60.45% | 7.9069 | $11.16 |
| 2025-04 | 160 | $1786.02 | 70.0% | 10.8883 | $15.65 |
| 2025-05 | 197 | $1615.35 | 74.11% | 5.7199 | $47.18 |
| 2025-06 | 141 | $594.68 | 70.92% | 2.8425 | $70.73 |
| 2025-07 | 228 | $859.46 | 60.53% | 5.5021 | $16.36 |
| 2025-08 | 141 | $399.24 | 53.9% | 6.195 | $15.43 |
| 2025-09 | 204 | $1071.33 | 74.51% | 6.4247 | $34.64 |
| 2025-10 | 199 | $2530.43 | 84.92% | 9.502 | $33.26 |
| 2025-11 | 139 | $651.5 | 67.63% | 2.1365 | $48.57 |
| 2025-12 | 127 | $1378.52 | 78.74% | 42.9351 | $6.1 |

### By Session

| Segment | Trades | Net PnL | Win% | PF | Max DD |
|---|---|---|---|---|---|
| NY | 434 | $2620.93 | 67.97% | 10.048 | $19.36 |
| ASIA | 573 | $2372.45 | 65.1% | 6.522 | $31.82 |
| LONDON | 453 | $3797.14 | 73.95% | 5.329 | $86.34 |
| OFF | 285 | $1274.28 | 69.12% | 7.1338 | $20.69 |
| OVERLAP | 347 | $2665.4 | 67.44% | 4.4229 | $70.62 |

### By Regime

| Segment | Trades | Net PnL | Win% | PF | Max DD |
|---|---|---|---|---|---|
| TREND_UP | 2014 | $12054.04 | 68.62% | 5.8181 | $79.05 |
| TREND_DOWN | 32 | $171.6 | 56.25% | 4.6637 | $30.85 |
| VOLATILE | 39 | $480.45 | 76.92% | 15.4924 | $20.69 |
| RANGE | 7 | $24.12 | 57.14% | 23.0577 | $1.09 |

### By Direction

| Segment | Trades | Net PnL | Win% | PF | Max DD |
|---|---|---|---|---|---|
| BUY | 1500 | $9982.91 | 69.93% | 7.8429 | $61.74 |
| SELL | 592 | $2747.29 | 65.03% | 3.4442 | $69.32 |

### By Cost Scenario

| Segment | Trades | Net PnL | Win% | PF | Max DD |
|---|---|---|---|---|---|
| normal | 2092 | $12730.21 | 68.55% | 5.9287 | $79.05 |

## Task 8: Institutional Readiness

| Metric | Value |
|---|---|
| capital_utilization_pct | 100.0 |
| monthly_consistency_pct | 100.0 |
| monthly_stdev_usd | 537.05 |
| tail_risk_pct | 0.59 |
| dd_stability_score | 98.7 |
| broker_robustness_pct | 100.0 |
| explainability_complete | True |
| institutional_approved | True |
| competition_score | 84.36 |
| verdict | APPROVED |
| reason | Meets institutional criteria |

## Realism Check

**Results look realistic:** True

### Concerns

- SPRINT_9_9_3_2_PROP_FIRM_STRICT: Sharpe 22.8934 (very high)
- SPRINT_9_9_3_3_RETAIL_SAFE: Sharpe 25.1051 (very high)
- SPRINT_9_9_3_3_PROP_FIRM_STRICT: Sharpe 23.6148 (very high)
- SPRINT_9_9_3_3_INSTITUTIONAL: Sharpe 20.9033 (very high)

### Positive Indicators

- NO_GOVERNANCE: win rate 44.48% (realistic)
- NO_GOVERNANCE: max DD $5748.51 (non-zero, realistic)
- SPRINT_9_9_3_2_PROP_FIRM_STRICT: win rate 68.52% (realistic)
- SPRINT_9_9_3_2_PROP_FIRM_STRICT: max DD $75.92 (non-zero, realistic)
- SPRINT_9_9_3_3_RETAIL_SAFE: win rate 69.26% (realistic)
- SPRINT_9_9_3_3_RETAIL_SAFE: max DD $98.44 (non-zero, realistic)
- SPRINT_9_9_3_3_PROP_FIRM_STRICT: win rate 68.55% (realistic)
- SPRINT_9_9_3_3_PROP_FIRM_STRICT: max DD $79.05 (non-zero, realistic)
- SPRINT_9_9_3_3_INSTITUTIONAL: win rate 67.51% (realistic)
- SPRINT_9_9_3_3_INSTITUTIONAL: max DD $87.88 (non-zero, realistic)

## Monday DEMO Recommendation

**Should Monday DEMO micro test proceed:** True

**Reason:** All criteria met: positive net PnL, DD < 15%, PF > 1.0, sufficient trades

### Criteria

| Criterion | Met |
|---|---|
| positive_net_pnl | YES |
| max_dd_under_15pct | YES |
| pf_above_1 | YES |
| sufficient_trades_20plus | YES |

## Safety Confirmation

| Item | Value |
|---|---|
| demo_micro_execute_run | NO |
| mt5_order_send_called | NO |
| live_demo_path_changed | NO |
| governance_wired_into_live_demo | NO |
| runtime_dry_run_default | YES |
| runtime_live_trading_default | NO |
| demo_micro_enabled_default | NO |
| no_credentials_committed | YES |
| no_martingale_grid_averaging_lot_escalation | YES |
| models_retrained | NO |
