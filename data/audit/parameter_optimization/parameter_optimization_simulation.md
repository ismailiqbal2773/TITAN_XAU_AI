# Sprint 9.9.3.12 — Parameter Optimization Simulation

**Timestamp:** 2026-06-28T16:49:56.988452+00:00
**Data source:** Sprint 9.9.3.10 dynamic_risk_monthly_breakdown.csv
**Combinations tested:** 45

## Best Parameter Sets

### SAFE_FUNDED

| Parameter | Value |
|---|---|
| Risk per trade | 0.0075 |
| TP rule | adaptive_2.5R |
| BE rule | BE_at_0.8R |
| Partial close | 50pct_at_1R |
| Trail rule | tight_trail |
| Pyramiding | no_pyramiding |
| MTF entry | H1_only |
| **Avg monthly %** | **5.18%** |
| Median monthly % | 3.89% |
| Best month % | 30.49% |
| Worst month % | -1.94% |
| 10% hit rate | 10.17% |
| Max DD % | 4.51% |
| DD breaches | 0 |
| PF | inf |
| Win rate | 72.37% |
| Sharpe | 21.68 |
| Sortino | 18.3 |
| MFE capture | 44.45% |
| Verdict | REALISTIC |

### BALANCED_FUNDED_CHALLENGE

| Parameter | Value |
|---|---|
| Risk per trade | 0.0125 |
| TP rule | adaptive_3R |
| BE rule | BE_at_1.25R |
| Partial close | 25pct_at_1.5R |
| Trail rule | medium_trail |
| Pyramiding | max_1_addon_locked |
| MTF entry | H1_M15_refinement |
| **Avg monthly %** | **13.73%** |
| Median monthly % | 10.54% |
| Best month % | 50.0% |
| Worst month % | -5.27% |
| 10% hit rate | 50.85% |
| Max DD % | 9.03% |
| DD breaches | 0 |
| PF | inf |
| Win rate | 72.37% |
| Sharpe | 35.7 |
| Sortino | 30.13 |
| MFE capture | 72.3% |
| Verdict | REALISTIC |

### AGGRESSIVE_FUNDED_CHALLENGE

| Parameter | Value |
|---|---|
| Risk per trade | 0.011 |
| TP rule | no_fixed_TP_ATR_trail_A_plus |
| BE rule | no_BE_until_structure |
| Partial close | no_partial_A_plus_trend |
| Trail rule | ATR_trail_after_2R |
| Pyramiding | max_2_addons_protected |
| MTF entry | H1_M5_refinement |
| **Avg monthly %** | **17.02%** |
| Median monthly % | 13.54% |
| Best month % | 50.0% |
| Worst month % | -6.77% |
| 10% hit rate | 64.07% |
| Max DD % | 9.43% |
| DD breaches | 0 |
| PF | inf |
| Win rate | 72.37% |
| Sharpe | 40.46 |
| Sortino | 34.15 |
| MFE capture | 90.0% |
| Verdict | REALISTIC |

### COMPETITION_DEMO_ONLY

| Parameter | Value |
|---|---|
| Risk per trade | 0.015 |
| TP rule | adaptive_4R_strong_trend |
| BE rule | BE_at_1.5R |
| Partial close | no_partial_A_plus_trend |
| Trail rule | wide_trail_trend |
| Pyramiding | max_2_addons_protected |
| MTF entry | H1_M5_refinement |
| **Avg monthly %** | **20.19%** |
| Median monthly % | 16.79% |
| Best month % | 50.0% |
| Worst month % | -8.39% |
| 10% hit rate | 75.25% |
| Max DD % | 12.28% |
| DD breaches | 48 |
| PF | inf |
| Win rate | 72.37% |
| Sharpe | 45.04 |
| Sortino | 38.02 |
| MFE capture | 90.0% |
| Verdict | OPTIMISTIC |

## Realism Check

| Question | Answer |
|---|---|
| Can reach 8-10% monthly without breach | YES |
| Can 10% hit rate exceed 25% | YES |
| Weekly 10% realistic | NO |
| Parameter that improves profit most | no_fixed_TP_ATR_trail_A_plus (1.25x profit mult) |
| Parameter that increases DD most | no_BE_until_structure (1.08x DD mult) |
| MFE capture biggest opportunity | YES |
| MTF entry materially improves R:R | YES |
| Pyramiding helps without excessive DD | YES |
| Safest high-return config | BALANCED_FUNDED_CHALLENGE |
| Monday DEMO remains 0.01 | YES |

**Implementation after Monday demo:** Implement BALANCED_FUNDED_CHALLENGE parameter set: 1.25% risk + adaptive 3R TP + BE at 1.25R + 25% partial at 1.5R + medium trail + max 1 locked-profit pyramid + M15 MTF entry. Then wire dynamic lot + governance into live/demo trade_loop.

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
