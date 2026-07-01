# TITAN XAU AI - Prop/Funded Optimization Report

**Verdict:** **PROP_FUNDED_READY_CONSERVATIVE**

**Timestamp:** 2026-07-01T15:26:53.051343+00:00

**Best Safe Profile:** prop_funded_safe

**Best Growth Profile:** 

**Aggressive 20% Status:** NOT_PROVEN

**Recommended First Demo:** prop_funded_safe

## Profile Metrics

| Profile | Monthly% | Yearly% | MaxDD% | PF | Sharpe | Sortino | WR% | Score | Verdict | Executable | SimOnly |
|---|---|---|---|---|---|---|---|---|---|---|---|
| prop_funded_safe | 5.18 | 62.16 | 4.51 | 1.63 | 3.33 | 16.97 | 72.37 | 82.0 | PROP_FUNDED_READY_CONSERVATIVE | True | False |
| prop_funded_growth | 8.7 | 104.4 | 5.72 | 4.85 | 7.81 | 16.97 | 65.45 | 82.0 | PROP_FUNDED_READY_CONSERVATIVE | True | False |
| prop_funded_aggressive_20pct_simulation | 17.02 | 204.24 | 9.43 | 4.52 | 8.28 | 34.15 | 68.38 | 19.0 | PROP_FUNDED_AGGRESSIVE_SIMULATION_ONLY | False | True |

## Detailed Parameters

### prop_funded_safe

**Purpose:** Safest funded profile - capital preservation first

**Evidence:** ATR_1.5/3.0 + SAFE_FUNDED + frozen_balanced_validation

| Parameter | Value |
|---|---|
| risk_per_trade_pct | 0.005 |
| confidence_threshold | 0.5 |
| atr_sl_multiplier | 1.5 |
| tp_multiplier_initial_tp_R | 3.0 |
| minimum_rr | 2.0 |
| dynamic_tp_trigger_R | 2.0 |
| breakeven_trigger_R | 1.0 |
| trailing_trigger_R | 1.75 |
| profit_lock_trigger_R | 3.0 |
| internal_daily_dd_pct | 2.0 |
| internal_total_dd_pct | 6.0 |
| daily_dd_breach_count | 0 |
| total_dd_breach_count | 0 |
| wfe | 0.85 |
| monte_carlo_survival | 95.0 |
| broker_score | 86.0 |
| spread_cost | 3.5 |
| slippage_cost | 0.4 |
| commission_cost | 0.07 |
| optimizer_score | 82.0 |
| verdict | PROP_FUNDED_READY_CONSERVATIVE |
| reason |  |

### prop_funded_growth

**Purpose:** Best practical challenge/funded profile - maximize return without DD breach

**Evidence:** BALANCED_FUNDED_CHALLENGE + canonical_frozen_balanced + multiyear_PROP_FIRM_STRICT

| Parameter | Value |
|---|---|
| risk_per_trade_pct | 0.0075 |
| confidence_threshold | 0.5 |
| atr_sl_multiplier | 1.5 |
| tp_multiplier_initial_tp_R | 3.0 |
| minimum_rr | 2.0 |
| dynamic_tp_trigger_R | 2.0 |
| breakeven_trigger_R | 1.0 |
| trailing_trigger_R | 1.75 |
| profit_lock_trigger_R | 3.0 |
| internal_daily_dd_pct | 2.5 |
| internal_total_dd_pct | 7.0 |
| daily_dd_breach_count | 0 |
| total_dd_breach_count | 0 |
| wfe | 0.8 |
| monte_carlo_survival | 88.0 |
| broker_score | 86.0 |
| spread_cost | 3.5 |
| slippage_cost | 0.4 |
| commission_cost | 0.07 |
| optimizer_score | 82.0 |
| verdict | PROP_FUNDED_READY_CONSERVATIVE |
| reason |  |

### prop_funded_aggressive_20pct_simulation

**Purpose:** Test whether 20% monthly is possible - SIMULATION ONLY

**Evidence:** AGGRESSIVE_FUNDED_CHALLENGE + multiyear_PROP_FIRM_STRICT

| Parameter | Value |
|---|---|
| risk_per_trade_pct | 0.011 |
| confidence_threshold | 0.5 |
| atr_sl_multiplier | 1.5 |
| tp_multiplier_initial_tp_R | 3.0 |
| minimum_rr | 2.0 |
| dynamic_tp_trigger_R | 2.0 |
| breakeven_trigger_R | 1.0 |
| trailing_trigger_R | 1.75 |
| profit_lock_trigger_R | 3.0 |
| internal_daily_dd_pct | 2.5 |
| internal_total_dd_pct | 7.0 |
| daily_dd_breach_count | 1 |
| total_dd_breach_count | 1 |
| wfe | 0.65 |
| monte_carlo_survival | 72.0 |
| broker_score | 86.0 |
| spread_cost | 3.5 |
| slippage_cost | 0.4 |
| commission_cost | 0.07 |
| optimizer_score | 19.0 |
| verdict | PROP_FUNDED_AGGRESSIVE_SIMULATION_ONLY |
| reason |  |


## Safety

- no_martingale: True
- no_grid: True
- no_averaging: True
- no_loss_based_lot_multiplier: True
- order_send_called: False
- position_modified: False
