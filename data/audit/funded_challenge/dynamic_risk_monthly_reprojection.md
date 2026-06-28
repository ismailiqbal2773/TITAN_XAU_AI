# Sprint 9.9.3.10 — Dynamic Risk Monthly Reprojection

**Timestamp:** 2026-06-28T15:35:37.964142+00:00
**Data source:** Sprint 9.9.3.8 chunk files (26 chunks, 5 brokers, 2020-2025)
**Starting equity:** $10,000.0

## PROP_FIRM_STRICT — Monthly Target Hit Rate by Risk Mode

| Risk Mode | Months | 5% Hit | 8% Hit | 10% Hit | DD Breaches | Max DD% | Avg Month% | Best Month% | Worst Month% |
|---|---|---|---|---|---|---|---|---|---|
| fixed_0.01_lot | 295 | 0.0% | 0.0% | 0.0% | 0 | 0.71% | 0.83% | 4.39% | -0.28% |
| 0.25pct_equity | 295 | 2.37% | 0.34% | 0.0% | 0 | 1.77% | 1.67% | 8.13% | -0.58% |
| 0.50pct_equity | 295 | 7.8% | 2.71% | 0.34% | 0 | 3.55% | 2.59% | 11.36% | -0.89% |
| 0.75pct_equity | 295 | 12.88% | 5.08% | 2.03% | 0 | 5.32% | 3.23% | 13.96% | -1.08% |
| 1.00pct_equity | 295 | 16.27% | 7.46% | 4.07% | 0 | 7.1% | 3.73% | 18.09% | -1.21% |
| 1.25pct_equity | 295 | 20.0% | 8.81% | 5.42% | 0 | 8.88% | 4.14% | 21.98% | -1.3% |
| 1.50pct_equity | 295 | 22.71% | 9.49% | 6.44% | 36 | 10.65% | 4.48% | 25.67% | -1.37% |

## Funded Account Rule Analysis

### Standard Rules (Daily DD 5%, Total DD 10%)

| Risk Mode | 10% Hit Rate | DD Breaches | Max DD% | Verdict |
|---|---|---|---|---|
| fixed_0.01_lot | 0.0% | 0 | 0.71% | SUITABLE |
| 0.25pct_equity | 0.0% | 0 | 1.77% | SUITABLE |
| 0.50pct_equity | 0.34% | 0 | 3.55% | SUITABLE |
| 0.75pct_equity | 2.03% | 0 | 5.32% | SUITABLE |
| 1.00pct_equity | 4.07% | 0 | 7.1% | SUITABLE |
| 1.25pct_equity | 5.42% | 0 | 8.88% | SUITABLE |
| 1.50pct_equity | 6.44% | 36 | 10.65% | UNSUITABLE |

### Stricter Rules (Daily DD 4%, Total DD 8%)

| Risk Mode | DD Breaches | Breach Rate | Max DD% | Verdict |
|---|---|---|---|---|
| fixed_0.01_lot | 0 | 0.0% | 0.71% | SUITABLE |
| 0.25pct_equity | 0 | 0.0% | 1.77% | SUITABLE |
| 0.50pct_equity | 0 | 0.0% | 3.55% | SUITABLE |
| 0.75pct_equity | 0 | 0.0% | 5.32% | SUITABLE |
| 1.00pct_equity | 0 | 0.0% | 7.1% | SUITABLE |
| 1.25pct_equity | 240 | 81.36% | 8.88% | UNSUITABLE |
| 1.50pct_equity | 360 | 122.03% | 10.65% | UNSUITABLE |

## Recommendations

- **Funded challenge risk mode:** 1.00pct_equity
- **Institutional risk mode:** 0.50pct_equity
- **Retail safe risk mode:** 0.25pct_equity
- **Monthly 10% realistic:** NO
- **Weekly 10% realistic:** NO
- **Fixed 0.01 too conservative:** YES
- **Monday DEMO should remain 0.01:** YES

## Broker Comparison (1.00% equity risk, PROP_FIRM_STRICT)

- **Best broker:** fundednext
- **Worst broker:** canonical

## Auto-Lot Simulation (Task 2)

**Formula:** Lot Size = (Equity × Risk%) / SL Loss Per Lot

**Safety caps:**
- broker_min_lot 0.01
- broker_max_lot 1.0
- lot_step 0.01
- max_open_positions 1
- max_daily_DD 5%
- max_total_DD 10%
- governance risk multiplier
- block if SL cannot be estimated

**Wired into live/demo:** NO (simulation only)

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
| no_martingale_grid_averaging | YES |
| working_tree_clean | YES |
