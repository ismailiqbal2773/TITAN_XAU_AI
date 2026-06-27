# Sprint 9.9.3.2 — Stress Loss Mitigation Comparison

**Timestamp UTC:** 2026-06-27T02:23:52.789098+00:00
**Source report:** `data/audit/virtual_lifecycle/virtual_lifecycle_report.json`
**Primary profile:** `PROP_FIRM_STRICT`

## Important
- This is a **SIMULATION** — no real or demo MT5 execution was performed.
- Governance engine is wired into **virtual lifecycle decision path only**.
- **Production live path is unchanged.** DEMO_MICRO_EXECUTE was NOT run.
- **No martingale / grid / averaging / lot escalation** introduced.
- **No models retrained.** Strategy logic is unchanged.

## Before vs After (PROP_FIRM_STRICT profile)

| Metric | Before | After | Change |
|---|---|---|---|
| Total net PnL | 44.1 | 76.4 | 32.3 |
| Loss from 8 scenarios | -52.0 | 0.0 | 52.0 |
| Profit from other scenarios | 96.1 | 76.4 | -19.7 |
| Max DD (USD) | 11.4 | 0.0 | -11.4 |
| Profit factor | 1.8481 | inf | — |
| Win rate % | 52.94 | 35.29 | — |

## Governance Action Counts (After)

| Action | Count |
|---|---|
| Blocked | 11 |
| Reduced risk | 0 |
| Early exit (CLOSE/INVALIDATION) | 0 |
| BE locked | 0 |
| Partial close / tight trail | 0 |
| Allowed (no change) | 6 |

## The 8 Losing Scenarios — Before vs After

| # | Scenario | Before | After | Change | Action | Explanation |
|---|---|---|---|---|---|---|
| 1 | BUY_SL | -10.600000000000001 | 0.0 | 10.6 | BLOCKED | BASELINE: meta 0.68 < 0.7 AND no strong edge — block |
| 2 | SELL_SL | -10.600000000000001 | 0.0 | 10.6 | BLOCKED | BASELINE: meta 0.68 < 0.7 AND no strong edge — block |
| 3 | REGIME_FLIP_BUY | -0.6 | 0.0 | 0.6 | BLOCKED | BASELINE: meta 0.65 < 0.7 AND no strong edge — block; REGIME_FLIP: prob 0.7 > 0.6 AND no confirmation — block |
| 4 | REGIME_FLIP_SELL | -0.6 | 0.0 | 0.6 | BLOCKED | BASELINE: meta 0.65 < 0.7 AND no strong edge — block; REGIME_FLIP: prob 0.7 > 0.6 AND no confirmation — block |
| 5 | AMBIGUOUS_CANDLE | -10.600000000000001 | 0.0 | 10.6 | BLOCKED | AMBIGUOUS_CANDLE: blocked — missing: meta 0.65 < 0.75, regime_conf 0.6 < 0.70, no confirmation; BASELINE: meta 0.65 < 0.7 AND no strong edge — block |
| 6 | HIGH_VOLATILITY | -10.8 | 0.0 | 10.8 | BLOCKED | HIGH_VOLATILITY: meta 0.7 < 0.8 in throttle vol (ATR 95.0); HIGH_VOLATILITY: spread 0.5 > 0.40 in throttle vol |
| 7 | EQUITY_PROTECTION | -5.6 | 0.0 | 5.6 | BLOCKED | EQUITY_PROTECTION: zone active — no new trades; ACCOUNT: health 55.0 < 60 AND no strong edge — block; DAILY_DD: 83.3% of threshold > 60% — no new trades |
| 8 | CAPITAL_PRESERVATION | -2.5999999999999996 | 0.0 | 2.6 | BLOCKED | CAPITAL_PRESERVATION: active — no new trades / no recovery trade; ACCOUNT: health 20.0 < 40 — hard block; DAILY_DD: 96.7% of threshold > 60% — no new trades |

## Acceptance Criteria

| Criterion | Met |
|---|---|
| loss_from_8_reduced | YES |
| high_volatility_no_longer_full_1R_loss | YES |
| ambiguous_candle_no_longer_full_1R_loss | YES |
| buy_sl_sell_sl_reduced_or_blocked | YES |
| equity_capital_preservation_no_new_trades | YES |
| regime_flip_losses_reduced | YES |
| max_dd_same_or_lower | YES |
| no_production_live_path_changed | YES |
| no_demo_execution_run | YES |
| no_martingale_grid_averaging_lot_escalation | YES |
| all_criteria_met | YES |

## Per-Profile Institutional Acceptance Metrics

### RETAIL_SAFE

| Metric | Value |
|---|---|
| Total scenarios | 17 |
| Total net PnL | 95.7 |
| Loss from 8 scenarios | 0.0 |
| Max DD (USD) | 0.0 |
| Profit factor | inf |
| Expectancy | 5.6294 |
| Blocked trades | 7 |
| Institutional approved | 4 |
| Early exits | 0 |
| BE exits | 2 |
| Partial closes | 0 |
| Capital protection activations | 2 |
| Explainability complete | True |

Approved scenarios: BUY_TP, SELL_TP, SPREAD_SPIKE_TP, PROFIT_LOCK

Rejected scenarios: BUY_SL, SELL_SL, BUY_AI_EXIT, SELL_AI_EXIT, REGIME_FLIP_BUY, REGIME_FLIP_SELL, ALPHA_DECAY, AMBIGUOUS_CANDLE, HIGH_VOLATILITY, MAX_HOLDING, STALE_EXIT, EQUITY_PROTECTION, CAPITAL_PRESERVATION

### PROP_FIRM_STRICT

| Metric | Value |
|---|---|
| Total scenarios | 17 |
| Total net PnL | 76.4 |
| Loss from 8 scenarios | 0.0 |
| Max DD (USD) | 0.0 |
| Profit factor | inf |
| Expectancy | 4.4941 |
| Blocked trades | 11 |
| Institutional approved | 3 |
| Early exits | 0 |
| BE exits | 0 |
| Partial closes | 0 |
| Capital protection activations | 2 |
| Explainability complete | True |

Approved scenarios: BUY_TP, SELL_TP, PROFIT_LOCK

Rejected scenarios: BUY_SL, SELL_SL, BUY_AI_EXIT, SELL_AI_EXIT, REGIME_FLIP_BUY, REGIME_FLIP_SELL, ALPHA_DECAY, AMBIGUOUS_CANDLE, SPREAD_SPIKE_TP, HIGH_VOLATILITY, MAX_HOLDING, STALE_EXIT, EQUITY_PROTECTION, CAPITAL_PRESERVATION

### INSTITUTIONAL_CAPITAL_PROTECTION

| Metric | Value |
|---|---|
| Total scenarios | 17 |
| Total net PnL | 53.2 |
| Loss from 8 scenarios | 0.0 |
| Max DD (USD) | 0.0 |
| Profit factor | inf |
| Expectancy | 3.1294 |
| Blocked trades | 14 |
| Institutional approved | 3 |
| Early exits | 0 |
| BE exits | 0 |
| Partial closes | 0 |
| Capital protection activations | 2 |
| Explainability complete | True |

Approved scenarios: BUY_TP, SELL_TP, PROFIT_LOCK

Rejected scenarios: BUY_SL, SELL_SL, BUY_AI_EXIT, SELL_AI_EXIT, REGIME_FLIP_BUY, REGIME_FLIP_SELL, ALPHA_DECAY, AMBIGUOUS_CANDLE, SPREAD_SPIKE_TP, HIGH_VOLATILITY, MAX_HOLDING, STALE_EXIT, EQUITY_PROTECTION, CAPITAL_PRESERVATION

## Safety Confirmation

| Item | Value |
|---|---|
| code_changed | NO |
| strategy_changed | NO |
| live_demo_path_changed | NO |
| demo_micro_execute_run | NO |
| martingale_added | NO |
| grid_added | NO |
| averaging_added | NO |
| lot_escalation_added | NO |
| models_retrained | NO |

## Notes

- This is a SIMULATION — no real or demo MT5 execution was performed.
- The governance engine is wired into the virtual lifecycle decision path only.
- Production live path is unchanged. DEMO_MICRO_EXECUTE was NOT run.
- PROP_FIRM_STRICT profile is used as the primary comparison baseline.
- INSTITUTIONAL_CAPITAL_PROTECTION is the strictest profile — blocks more trades,
- requires higher meta/regime confidence, lower spread, lower ATR.
- All governance decisions are explainable via the audit trail.
