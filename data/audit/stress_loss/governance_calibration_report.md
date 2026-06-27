# Sprint 9.9.3.3 — Governance Calibration Report

**Timestamp UTC:** 2026-06-27T02:20:21.843331+00:00
**Source report:** `data/audit/virtual_lifecycle/virtual_lifecycle_report.json`

## Important
- This is a **SIMULATION** — no real or demo MT5 execution.
- **DEMO_MICRO_EXECUTE was NOT run.**
- **Production live path unchanged.** No martingale/grid/averaging/lot escalation.
- **No models retrained.**

## Root Cause of Overfiltering (Sprint 9.9.3.2)

Sprint 9.9.3.2 used single-tier hard blocks for many conditions:
- ATR > 92 (PROP_FIRM_STRICT) → hard block (missed HV_STRONG_ALPHA winners)
- meta < 0.70 → hard block (missed borderline winners with positive expected edge)
- broker_quality < 70 → hard block (missed trades where broker was just OK)
- regime_flip > 0.60 → hard block (missed false-alarm flip scenarios)

Result: 11 of 17 scenarios blocked, $19.7 profit missed, only $52 loss avoided (overfiltering ratio 0.38).

## Best Calibrated Config (PROP_FIRM_STRICT)

```json
{
  "min_meta_confidence_block": 0.55,
  "min_meta_confidence": 0.7,
  "min_meta_confidence_throttle": 0.7,
  "max_atr_percentile_block": 92,
  "max_atr_percentile_throttle": 85,
  "max_spread_usd_block": 0.8,
  "max_regime_flip_prob_block": 0.75,
  "risk_multiplier_in_warn_vol": 0.75
}
```

## Before vs Sprint 9.9.3.2 vs Sprint 9.9.3.3

| Metric | Before | Sprint 9.9.3.2 | Sprint 9.9.3.3 |
|---|---|---|---|
| Total net PnL | 44.1 | 76.4 | 103.85 |
| Loss from 8 scenarios | -52.0 | 0.0 | 0.0 |
| Max DD | 11.4 | 0.0 | 0.0 |
| Profit factor | 1.8481 | inf | inf |
| Executed win rate % | 52.94 | 35.29 | 100.0 |
| Opportunity win rate % | 52.94 | 52.94 | 51.72 |
| Blocked count | 0 | 11 | 16 |
| Blocked winners | 0 | 5 | 2 |
| Blocked losers | 0 | 6 | 14 |
| Missed profit | 0.0 | 19.7 | 0.8 |
| Avoided loss | 0.0 | 52.0 | 104.0 |
| Overfiltering ratio | 0.0 | 0.38 | 0.0077 |
| Profit retention % | 100.0 | 79.5 | 79.7 |
| Loss reduction % | 0.0 | 100.0 | 100.0 |
| Trade frequency | 1.0 | 0.353 | 0.4483 |
| EV per executed trade | — | 12.73 | 7.9885 |
| Loss reduction efficiency | — | — | 130.0 |
| Competition score | 69.44 | 91.71 | 94.79 |

## Competition Score Breakdown (Sprint 9.9.3.3)

| Component | Weight | Score |
|---|---|---|
| net_pnl_quality | — | 20.0 |
| max_dd_control | — | 20.0 |
| profit_factor_expectancy | — | 15.0 |
| stress_loss_reduction | — | 15.0 |
| profit_retention | — | 7.97 |
| overfiltering_control | — | 9.96 |
| trade_frequency_sufficiency | — | 1.85 |
| explainability_completeness | — | 5.0 |
| **TOTAL** | **/100** | **94.79** |

## The 8 Losing Scenarios — Before vs Sprint 9.9.3.3

| # | Scenario | Before | After 9.9.3.3 | Change | Action | Risk Mult |
|---|---|---|---|---|---|---|
| 1 | BUY_SL | -10.600000000000001 | 0.0 | 10.6 | BLOCKED | 0.0 |
| 2 | SELL_SL | -10.600000000000001 | 0.0 | 10.6 | BLOCKED | 0.0 |
| 3 | REGIME_FLIP_BUY | -0.6 | 0.0 | 0.6 | BLOCKED | 0.0 |
| 4 | REGIME_FLIP_SELL | -0.6 | 0.0 | 0.6 | BLOCKED | 0.0 |
| 5 | AMBIGUOUS_CANDLE | -10.600000000000001 | 0.0 | 10.6 | BLOCKED | 0.0 |
| 6 | HIGH_VOLATILITY | -10.8 | 0.0 | 10.8 | BLOCKED | 0.0 |
| 7 | EQUITY_PROTECTION | -5.6 | 0.0 | 5.6 | BLOCKED | 0.0 |
| 8 | CAPITAL_PRESERVATION | -2.5999999999999996 | 0.0 | 2.6 | BLOCKED | 0.0 |

## Synthetic Unseen Scenarios (Anti-Overfit Validation)

| # | Scenario | Expected PnL | After 9.9.3.3 | Allowed | Blocked Winner | Blocked Loser |
|---|---|---|---|---|---|---|
| 1 | HV_STRONG_ALPHA | 8.0 | 2.0 | True | False | False |
| 2 | HV_WEAK_ALPHA | -10.0 | 0.0 | False | False | True |
| 3 | AMB_WITH_CONF | 6.0 | 3.0 | True | False | False |
| 4 | AMB_NO_CONF | -8.0 | 0.0 | False | False | True |
| 5 | FLIP_FALSE_ALARM | 5.0 | 2.5 | True | False | False |
| 6 | FLIP_TRUE_REVERSAL | -10.0 | 0.0 | False | False | True |
| 7 | HI_SPREAD_HI_EDGE | 6.0 | 3.0 | True | False | False |
| 8 | LO_SPREAD_WEAK_ALPHA | -8.0 | 0.0 | False | False | True |
| 9 | BROKER_GOOD | 5.0 | 2.5 | True | False | False |
| 10 | BROKER_POOR | -7.0 | 0.0 | False | False | True |
| 11 | LIQ_GOOD | 5.0 | 5.0 | True | False | False |
| 12 | LIQ_BAD | -9.0 | 0.0 | False | False | True |

## Acceptance Criteria

| Criterion | Met |
|---|---|
| loss_from_8_materially_reduced | YES |
| profit_retention_improved_vs_9932 | YES |
| overfiltering_ratio_decreased | YES |
| competition_score_improved | YES |
| max_dd_acceptable | YES |
| blocked_losers_more_than_blocked_winners | YES |
| synthetic_anti_overfit_pass | YES |
| all_criteria_met | YES |

## Safety Confirmation

| Item | Value |
|---|---|
| demo_micro_execute_run | NO |
| live_demo_path_changed | NO |
| martingale_added | NO |
| grid_added | NO |
| averaging_added | NO |
| lot_escalation_added | NO |
| models_retrained | NO |
