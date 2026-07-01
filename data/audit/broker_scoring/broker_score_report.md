# TITAN XAU AI — Broker Score Report

**Generated:** 2026-07-01T15:40:52.523595+00:00

Scores every broker in `config/broker_profiles.yaml` against 14 weighted execution-quality dimensions. Brokers present in the historical frozen-balanced validation CSV but missing from the YAML are scored using synthetic profiles.

## Hard Safety Invariants

| Invariant | Value |
|---|---|
| never_calls_mt5_order_send | True |
| no_martingale | True |
| no_grid | True |
| no_averaging | True |
| pure_python | True |

## Summary

| Metric | Value |
|---|---|
| Total brokers scored | 7 |
| BROKER_SCORING_READY (>=85) | 2 |
| BROKER_SCORING_NEEDS_WORK (70-84) | 5 |
| BROKER_SCORING_BLOCKED (<70) | 0 |
| Synthetic profiles injected | exness, fundednext, fbs |

## Audit Verdicts Supported

- `BROKER_SCORING_READY`
- `BROKER_SCORING_NEEDS_WORK`
- `BROKER_SCORING_BLOCKED`

## Broker Score Table

| Broker | Score | Verdict | Spread | Slippage | Commission | StopLevel | FreezeLevel | FillMode | NetImpact | PropCompatible | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|
| FundedNext (synthetic from historical CSV) | 87.06 | BROKER_SCORING_READY | 97.1 | 90.0 | 40.0 | 70.0 | 100.0 | 100.0 | 96.8 | yes |  |
| MetaQuotes-Demo | 86.26 | BROKER_SCORING_READY | 94.6 | 90.0 | 100.0 | 50.0 | 100.0 | 100.0 | 67.1 | yes |  |
| Exness (synthetic from historical CSV) | 84.83 | BROKER_SCORING_NEEDS_WORK | 98.2 | 90.0 | 30.0 | 70.0 | 100.0 | 100.0 | 82.9 | yes |  |
| FBS (synthetic from historical CSV) | 84.22 | BROKER_SCORING_NEEDS_WORK | 96.4 | 85.0 | 40.0 | 60.0 | 100.0 | 100.0 | 81.6 | yes |  |
| IC Markets Standard | 82.71 | BROKER_SCORING_NEEDS_WORK | 98.2 | 90.0 | 30.0 | 50.0 | 100.0 | 100.0 | 81.4 | yes |  |
| Institutional ECN | 78.50 | BROKER_SCORING_NEEDS_WORK | 100.0 | 95.0 | 55.0 | 80.0 | 100.0 | 100.0 | 50.0 | yes | historical validation weak or missing |
| FTMO | 75.00 | BROKER_SCORING_NEEDS_WORK | 100.0 | 90.0 | 40.0 | 70.0 | 100.0 | 100.0 | 50.0 | yes | historical validation weak or missing |

## Score Components (14 weighted dimensions)

- `spread_score`
- `slippage_score`
- `commission_score`
- `swap_score`
- `stop_level_score`
- `freeze_level_score`
- `filling_mode_score`
- `lot_step_score`
- `symbol_suffix_score`
- `execution_profile_score`
- `historical_validation_score`
- `broker_split_validation_score`
- `net_expectancy_impact_score`
- `prop_funded_compatibility_score`

## Per-Broker Detail

### Exness (synthetic from historical CSV) (`exness`)

- **Score:** 84.83
- **Verdict:** BROKER_CAUTION
- **Prop-funded compatible:** True
- **Historical source:** exness
- **Historical verdict:** PASS

#### Component breakdown

| Component | Score | Weight |
|---|---|---|
| spread_score | 98.21 | 0.1500 |
| slippage_score | 90.00 | 0.1000 |
| commission_score | 30.00 | 0.0800 |
| swap_score | 20.00 | 0.0500 |
| stop_level_score | 70.00 | 0.0700 |
| freeze_level_score | 100.00 | 0.0500 |
| filling_mode_score | 100.00 | 0.0500 |
| lot_step_score | 100.00 | 0.0400 |
| symbol_suffix_score | 100.00 | 0.0300 |
| execution_profile_score | 89.55 | 0.0800 |
| historical_validation_score | 100.00 | 0.1000 |
| broker_split_validation_score | 100.00 | 0.0700 |
| net_expectancy_impact_score | 82.87 | 0.0800 |
| prop_funded_compatibility_score | 100.00 | 0.0500 |

### FBS (synthetic from historical CSV) (`fbs`)

- **Score:** 84.22
- **Verdict:** BROKER_CAUTION
- **Prop-funded compatible:** True
- **Historical source:** fbs
- **Historical verdict:** PASS

#### Component breakdown

| Component | Score | Weight |
|---|---|---|
| spread_score | 96.43 | 0.1500 |
| slippage_score | 85.00 | 0.1000 |
| commission_score | 40.00 | 0.0800 |
| swap_score | 30.00 | 0.0500 |
| stop_level_score | 60.00 | 0.0700 |
| freeze_level_score | 100.00 | 0.0500 |
| filling_mode_score | 100.00 | 0.0500 |
| lot_step_score | 100.00 | 0.0400 |
| symbol_suffix_score | 100.00 | 0.0300 |
| execution_profile_score | 85.36 | 0.0800 |
| historical_validation_score | 100.00 | 0.1000 |
| broker_split_validation_score | 100.00 | 0.0700 |
| net_expectancy_impact_score | 81.61 | 0.0800 |
| prop_funded_compatibility_score | 100.00 | 0.0500 |

### FTMO (`ftmo_prop`)

- **Score:** 75.00
- **Verdict:** BROKER_CAUTION
- **Prop-funded compatible:** True
- **Historical source:** ftmo
- **Historical verdict:** 
- **Notes:** historical validation weak or missing

#### Component breakdown

| Component | Score | Weight |
|---|---|---|
| spread_score | 100.00 | 0.1500 |
| slippage_score | 90.00 | 0.1000 |
| commission_score | 40.00 | 0.0800 |
| swap_score | 24.00 | 0.0500 |
| stop_level_score | 70.00 | 0.0700 |
| freeze_level_score | 100.00 | 0.0500 |
| filling_mode_score | 100.00 | 0.0500 |
| lot_step_score | 100.00 | 0.0400 |
| symbol_suffix_score | 100.00 | 0.0300 |
| execution_profile_score | 90.00 | 0.0800 |
| historical_validation_score | 50.00 | 0.1000 |
| broker_split_validation_score | 50.00 | 0.0700 |
| net_expectancy_impact_score | 50.00 | 0.0800 |
| prop_funded_compatibility_score | 100.00 | 0.0500 |

### FundedNext (synthetic from historical CSV) (`fundednext`)

- **Score:** 87.06
- **Verdict:** BROKER_APPROVED
- **Prop-funded compatible:** True
- **Historical source:** fundednext
- **Historical verdict:** PASS

#### Component breakdown

| Component | Score | Weight |
|---|---|---|
| spread_score | 97.14 | 0.1500 |
| slippage_score | 90.00 | 0.1000 |
| commission_score | 40.00 | 0.0800 |
| swap_score | 30.00 | 0.0500 |
| stop_level_score | 70.00 | 0.0700 |
| freeze_level_score | 100.00 | 0.0500 |
| filling_mode_score | 100.00 | 0.0500 |
| lot_step_score | 100.00 | 0.0400 |
| symbol_suffix_score | 100.00 | 0.0300 |
| execution_profile_score | 89.29 | 0.0800 |
| historical_validation_score | 100.00 | 0.1000 |
| broker_split_validation_score | 100.00 | 0.0700 |
| net_expectancy_impact_score | 96.79 | 0.0800 |
| prop_funded_compatibility_score | 100.00 | 0.0500 |

### IC Markets Standard (`ic_markets_standard`)

- **Score:** 82.71
- **Verdict:** BROKER_CAUTION
- **Prop-funded compatible:** True
- **Historical source:** icmarkets
- **Historical verdict:** PASS

#### Component breakdown

| Component | Score | Weight |
|---|---|---|
| spread_score | 98.21 | 0.1500 |
| slippage_score | 90.00 | 0.1000 |
| commission_score | 30.00 | 0.0800 |
| swap_score | 16.00 | 0.0500 |
| stop_level_score | 50.00 | 0.0700 |
| freeze_level_score | 100.00 | 0.0500 |
| filling_mode_score | 100.00 | 0.0500 |
| lot_step_score | 100.00 | 0.0400 |
| symbol_suffix_score | 100.00 | 0.0300 |
| execution_profile_score | 84.55 | 0.0800 |
| historical_validation_score | 100.00 | 0.1000 |
| broker_split_validation_score | 100.00 | 0.0700 |
| net_expectancy_impact_score | 81.37 | 0.0800 |
| prop_funded_compatibility_score | 100.00 | 0.0500 |

### Institutional ECN (`institutional_ecn`)

- **Score:** 78.50
- **Verdict:** BROKER_CAUTION
- **Prop-funded compatible:** True
- **Historical source:** institutional
- **Historical verdict:** 
- **Notes:** historical validation weak or missing

#### Component breakdown

| Component | Score | Weight |
|---|---|---|
| spread_score | 100.00 | 0.1500 |
| slippage_score | 95.00 | 0.1000 |
| commission_score | 55.00 | 0.0800 |
| swap_score | 40.00 | 0.0500 |
| stop_level_score | 80.00 | 0.0700 |
| freeze_level_score | 100.00 | 0.0500 |
| filling_mode_score | 100.00 | 0.0500 |
| lot_step_score | 100.00 | 0.0400 |
| symbol_suffix_score | 100.00 | 0.0300 |
| execution_profile_score | 93.75 | 0.0800 |
| historical_validation_score | 50.00 | 0.1000 |
| broker_split_validation_score | 50.00 | 0.0700 |
| net_expectancy_impact_score | 50.00 | 0.0800 |
| prop_funded_compatibility_score | 100.00 | 0.0500 |

### MetaQuotes-Demo (`metaquotes_demo`)

- **Score:** 86.26
- **Verdict:** BROKER_APPROVED
- **Prop-funded compatible:** True
- **Historical source:** canonical
- **Historical verdict:** PASS

#### Component breakdown

| Component | Score | Weight |
|---|---|---|
| spread_score | 94.64 | 0.1500 |
| slippage_score | 90.00 | 0.1000 |
| commission_score | 100.00 | 0.0800 |
| swap_score | 30.00 | 0.0500 |
| stop_level_score | 50.00 | 0.0700 |
| freeze_level_score | 100.00 | 0.0500 |
| filling_mode_score | 100.00 | 0.0500 |
| lot_step_score | 100.00 | 0.0400 |
| symbol_suffix_score | 100.00 | 0.0300 |
| execution_profile_score | 83.66 | 0.0800 |
| historical_validation_score | 100.00 | 0.1000 |
| broker_split_validation_score | 100.00 | 0.0700 |
| net_expectancy_impact_score | 67.10 | 0.0800 |
| prop_funded_compatibility_score | 80.00 | 0.0500 |

