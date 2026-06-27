# Sprint 9.9.3 — Stress PnL Loss Root Cause Audit
**Timestamp UTC:** 2026-06-27T01:30:22.757349+00:00
**Source report:** `data/audit/virtual_lifecycle/virtual_lifecycle_report.json`
**Source journal:** `data/audit/virtual_lifecycle/virtual_lifecycle_journal.jsonl`
**Source audit ID:** `sprint_9_8_1_virtual_lifecycle_fixed`
**Source verdict:** `VIRTUAL_LIFECYCLE_READY`
**Source demo gate:** `DEMO_MICRO_READY`

## Important
- This audit is **READ-ONLY** — no code, strategy, or model changes were made.
- All mitigations listed below are **recommendations for future sprints**, not implementations.
- **DEMO_MICRO_EXECUTE was NOT run.**
- **Trading strategy was NOT changed.**

## Summary
| Metric | Value |
|---|---|
| Total scenarios | 17 |
| NORMAL scenarios | 9 |
| STRESS scenarios | 8 |
| Profitable scenarios | 9 |
| Losing scenarios | 8 |
| Total profit (net PnL) | 96.1 |
| Total loss (net PnL) | -52.0 |
| Combined net PnL | 44.1 |
| STRESS net PnL | -11.5 |
| STRESS win rate | 25.0% |
| STRESS profit factor | 0.63 |
| STRESS max DD (USD) | 19.0 |
| STRESS cost drag % | 91.67% |
| NORMAL cost drag % | 8.85% |

## Why Losing Scenarios Reduced Quality Despite Good Overall Profit
Combined net PnL is **+$44.1** (positive headline), but STRESS net PnL is **-$11.5** with 25% win rate and 0.63 profit factor. Stress cost drag is **91.67%** (vs 8.85% in NORMAL), meaning almost all gross PnL is consumed by costs in stress conditions. Two CRITICAL scenarios (**HIGH_VOLATILITY** and **AMBIGUOUS_CANDLE**) lost **-$21.4 combined** despite reaching MFE of +$30 and +$25 respectively — extreme profit giveback. These losses are masked by the profitable NORMAL scenarios but represent a real risk if the strategy encounters sustained volatility shocks in production.

## The 8 Losing Scenarios (Root Cause Classification)
| # | Scenario | Category | Direction | Close Reason | Gross PnL | Net PnL | R | MFE | MAE | Severity | Root Causes |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | HIGH_VOLATILITY | STRESS | BUY | SL_HIT | -10.0 | -10.8 | -1.0 | 30 | 20 | CRITICAL | volatility_shock, exit_delay_profit_giveback, weak_alpha_accepted |
| 2 | AMBIGUOUS_CANDLE | STRESS | BUY | SL_HIT | -10.0 | -10.600000000000001 | -1.0 | 25 | 15 | HIGH | weak_alpha_accepted, exit_delay_profit_giveback, bad_session_liquidity |
| 3 | BUY_SL | NORMAL | BUY | SL_HIT | -10.0 | -10.600000000000001 | -1.0 | 5 | 11 | MEDIUM | weak_alpha_accepted, spread_slippage_cost |
| 4 | SELL_SL | NORMAL | SELL | SL_HIT | -10.0 | -10.600000000000001 | -1.0 | 5 | 11 | MEDIUM | weak_alpha_accepted, spread_slippage_cost |
| 5 | EQUITY_PROTECTION | STRESS | BUY | EQUITY_PROTECTION_EXIT | -5.0 | -5.6 | -0.5 | 0.0 | 0.0 | MEDIUM | broker_execution_condition, weak_alpha_accepted |
| 6 | CAPITAL_PRESERVATION | STRESS | BUY | CAPITAL_PRESERVATION_EXIT | -2.0 | -2.5999999999999996 | -0.2 | 0.0 | 0.0 | LOW | broker_execution_condition, weak_alpha_accepted |
| 7 | REGIME_FLIP_BUY | STRESS | BUY | REGIME_RISK_EXIT | 0.0 | -0.6 | 0.0 | 0.0 | 0.0 | LOW | regime_misclassification, tighter_regime_flip_exit |
| 8 | REGIME_FLIP_SELL | STRESS | SELL | REGIME_RISK_EXIT | 0.0 | -0.6 | 0.0 | 0.0 | 0.0 | LOW | regime_misclassification, tighter_regime_flip_exit |

## Per-Scenario Root Cause + Mitigation Detail

### 1. HIGH_VOLATILITY (STRESS)
- **Direction:** BUY
- **Entry / Close:** 2000 → 1990 (SL_HIT)
- **Gross / Net PnL:** -10.0 / -10.8
- **R-multiple:** -1.0  |  **MFE:** 30  |  **MAE:** 20
- **Costs:** spread=0.005, commission=0.302, slippage=2.0, swap=0, total=2.307 (23.07% drag)
- **Severity:** CRITICAL
- **Root causes:**
  - volatility_shock
  - exit_delay_profit_giveback
  - weak_alpha_accepted
- **Recommended mitigations:**
  - volatility shock filter: block entries when ATR percentile > 90 (current regime has 30-point swing)
  - earlier break-even: move SL to BE when MFE >= 1.0R (currently +30 unrealized then SL hit = -1.0R giveback)
  - faster partial close: take 50% at +1R, lock 25% more at +2R (current partial plan not aggressive enough in high-vol)
  - trailing stop: tighten trail to 0.5R in high-vol regime (vs current 1.0R)
  - spread/slippage block: max_spread_usd < 0.40 in high-vol (was 0.50)
- **Notes:**
  - Position was +$30 profit but ended at SL = -1.0R. Worst giveback in test set.

### 2. AMBIGUOUS_CANDLE (STRESS)
- **Direction:** BUY
- **Entry / Close:** 2000 → 1990 (SL_HIT)
- **Gross / Net PnL:** -10.0 / -10.600000000000001
- **R-multiple:** -1.0  |  **MFE:** 25  |  **MAE:** 15
- **Costs:** spread=0.003, commission=0.302, slippage=2.0, swap=0, total=2.305 (23.05% drag)
- **Severity:** HIGH
- **Root causes:**
  - weak_alpha_accepted
  - exit_delay_profit_giveback
  - bad_session_liquidity
- **Recommended mitigations:**
  - stricter alpha threshold: require meta_conf >= 0.70 on ambiguous candle patterns
  - earlier break-even: move SL to BE at +1.0R (was +25 unrealized then -10 at SL)
  - no-trade filter: skip entry if candle range > 2.0 * ATR AND direction ambiguous (close near middle)
  - faster partial close: lock 50% at +1R for ambiguous-candle entries
  - tighter regime-flip exit: any opposite-direction 1-bar momentum > 1.5 ATR → close immediately
- **Notes:**
  - Strong directional bias but gave back 100%+ of MFE. Exit policy too loose.

### 3. BUY_SL (NORMAL)
- **Direction:** BUY
- **Entry / Close:** 2000 → 1990 (SL_HIT)
- **Gross / Net PnL:** -10.0 / -10.600000000000001
- **R-multiple:** -1.0  |  **MFE:** 5  |  **MAE:** 11
- **Costs:** spread=0.003, commission=0.302, slippage=2.0, swap=0, total=2.305 (23.05% drag)
- **Severity:** MEDIUM
- **Root causes:**
  - weak_alpha_accepted
  - spread_slippage_cost
- **Recommended mitigations:**
  - stricter alpha threshold: meta_conf >= 0.70 for entries (currently 0.65)
  - spread/slippage block: skip if spread > 0.30 USD (currently allows up to 1.00)
  - earlier break-even: move SL to BE at +0.5R (currently +1.0R) to reduce stop-out cost
  - faster partial close: take 25% at +0.5R to recoup spread/commission
  - disable strategy in that regime if win_rate < 35% over rolling 50 trades
- **Notes:**
  - Baseline SL test — expected loss (-10 gross + 0.6 cost). Loss is within R-model, but cost drag compounds in stress.

### 4. SELL_SL (NORMAL)
- **Direction:** SELL
- **Entry / Close:** 2000 → 2010 (SL_HIT)
- **Gross / Net PnL:** -10.0 / -10.600000000000001
- **R-multiple:** -1.0  |  **MFE:** 5  |  **MAE:** 11
- **Costs:** spread=0.003, commission=0.302, slippage=2.0, swap=0, total=2.305 (23.05% drag)
- **Severity:** MEDIUM
- **Root causes:**
  - weak_alpha_accepted
  - spread_slippage_cost
- **Recommended mitigations:**
  - stricter alpha threshold: meta_conf >= 0.70 for entries (currently 0.65)
  - spread/slippage block: skip if spread > 0.30 USD (currently allows up to 1.00)
  - earlier break-even: move SL to BE at +0.5R (currently +1.0R) to reduce stop-out cost
  - faster partial close: take 25% at +0.5R to recoup spread/commission
  - disable strategy in that regime if win_rate < 35% over rolling 50 trades
- **Notes:**
  - Baseline SL test — expected loss (-10 gross + 0.6 cost). Loss is within R-model, but cost drag compounds in stress.

### 5. EQUITY_PROTECTION (STRESS)
- **Direction:** BUY
- **Entry / Close:** 2000 → 1995 (EQUITY_PROTECTION_EXIT)
- **Gross / Net PnL:** -5.0 / -5.6
- **R-multiple:** -0.5  |  **MFE:** 0.0  |  **MAE:** 0.0
- **Costs:** spread=0.003, commission=0.302, slippage=2.0, swap=0, total=2.305 (46.1% drag)
- **Severity:** MEDIUM
- **Root causes:**
  - broker_execution_condition
  - weak_alpha_accepted
- **Recommended mitigations:**
  - disable strategy in that regime when equity protection is engaged (capital_preservation state)
  - reduce risk multiplier to 0.25 when equity-protection threshold is within 2% of trigger
  - no-trade filter: block new entries when daily DD > 50% of equity-protection threshold
  - earlier break-even: when in equity-protection zone, force BE at +0.3R instead of +1.0R
- **Notes:**
  - This is CORRECT BEHAVIOR — equity protection triggered before SL. Smaller loss (-5) than SL (-10).

### 6. CAPITAL_PRESERVATION (STRESS)
- **Direction:** BUY
- **Entry / Close:** 2000 → 1998 (CAPITAL_PRESERVATION_EXIT)
- **Gross / Net PnL:** -2.0 / -2.5999999999999996
- **R-multiple:** -0.2  |  **MFE:** 0.0  |  **MAE:** 0.0
- **Costs:** spread=0.003, commission=0.302, slippage=2.0, swap=0, total=2.305 (115.25% drag)
- **Severity:** LOW
- **Root causes:**
  - broker_execution_condition
  - weak_alpha_accepted
- **Recommended mitigations:**
  - disable strategy in that regime when capital_preservation state active (allow_new_entries=false)
  - reduce risk multiplier to 0.0 when capital_preservation active (config already does this)
  - no-trade filter: block ALL new entries when account health < 25 (capital_preservation profile)
  - faster exit on capital_preservation: trigger exit at -0.3R (not -0.5R) in capital_preservation mode
- **Notes:**
  - CORRECT BEHAVIOR — capital preservation correctly minimized loss (-2 vs SL -10).

### 7. REGIME_FLIP_BUY (STRESS)
- **Direction:** BUY
- **Entry / Close:** 2000 → 2000 (REGIME_RISK_EXIT)
- **Gross / Net PnL:** 0.0 / -0.6
- **R-multiple:** 0.0  |  **MFE:** 0.0  |  **MAE:** 0.0
- **Costs:** spread=0.003, commission=0.302, slippage=2.0, swap=0, total=2.305 (100.0% drag)
- **Severity:** LOW
- **Root causes:**
  - regime_misclassification
  - tighter_regime_flip_exit
- **Recommended mitigations:**
  - no-trade filter: block entries within N bars of regime-flip signal
  - stricter alpha threshold per regime: require meta_conf >= 0.70 in transitional regime
  - reduce risk multiplier to 0.5 in transitional regime
  - faster regime-flip exit: trigger close on first regime probability > 0.6 (vs current > 0.7)
- **Notes:**
  - Loss is small (only cost). But signal was wrong-direction or noise — entry filter should reject.

### 8. REGIME_FLIP_SELL (STRESS)
- **Direction:** SELL
- **Entry / Close:** 2000 → 2000 (REGIME_RISK_EXIT)
- **Gross / Net PnL:** 0.0 / -0.6
- **R-multiple:** 0.0  |  **MFE:** 0.0  |  **MAE:** 0.0
- **Costs:** spread=0.003, commission=0.302, slippage=2.0, swap=0, total=2.305 (100.0% drag)
- **Severity:** LOW
- **Root causes:**
  - regime_misclassification
  - tighter_regime_flip_exit
- **Recommended mitigations:**
  - no-trade filter: block entries within N bars of regime-flip signal
  - stricter alpha threshold per regime: require meta_conf >= 0.70 in transitional regime
  - reduce risk multiplier to 0.5 in transitional regime
  - faster regime-flip exit: trigger close on first regime probability > 0.6 (vs current > 0.7)
- **Notes:**
  - Loss is small (only cost). But signal was wrong-direction or noise — entry filter should reject.

## Root Cause Frequency
| Root Cause | Count |
|---|---|
| weak_alpha_accepted | 6 |
| exit_delay_profit_giveback | 2 |
| spread_slippage_cost | 2 |
| broker_execution_condition | 2 |
| regime_misclassification | 2 |
| tighter_regime_flip_exit | 2 |
| volatility_shock | 1 |
| bad_session_liquidity | 1 |

## Mitigation Backlog (Ranked by Frequency)
| # | Mitigation | Frequency | Applies to Scenarios |
|---|---|---|---|
| 1 | stricter alpha threshold: meta_conf >= 0.70 for entries (currently 0.65) | 2 | BUY_SL, SELL_SL |
| 2 | spread/slippage block: skip if spread > 0.30 USD (currently allows up to 1.00) | 2 | BUY_SL, SELL_SL |
| 3 | earlier break-even: move SL to BE at +0.5R (currently +1.0R) to reduce stop-out cost | 2 | BUY_SL, SELL_SL |
| 4 | faster partial close: take 25% at +0.5R to recoup spread/commission | 2 | BUY_SL, SELL_SL |
| 5 | disable strategy in that regime if win_rate < 35% over rolling 50 trades | 2 | BUY_SL, SELL_SL |
| 6 | no-trade filter: block entries within N bars of regime-flip signal | 2 | REGIME_FLIP_BUY, REGIME_FLIP_SELL |
| 7 | stricter alpha threshold per regime: require meta_conf >= 0.70 in transitional regime | 2 | REGIME_FLIP_BUY, REGIME_FLIP_SELL |
| 8 | reduce risk multiplier to 0.5 in transitional regime | 2 | REGIME_FLIP_BUY, REGIME_FLIP_SELL |
| 9 | faster regime-flip exit: trigger close on first regime probability > 0.6 (vs current > 0.7) | 2 | REGIME_FLIP_BUY, REGIME_FLIP_SELL |
| 10 | volatility shock filter: block entries when ATR percentile > 90 (current regime has 30-point swing) | 1 | HIGH_VOLATILITY |
| 11 | earlier break-even: move SL to BE when MFE >= 1.0R (currently +30 unrealized then SL hit = -1.0R giveback) | 1 | HIGH_VOLATILITY |
| 12 | faster partial close: take 50% at +1R, lock 25% more at +2R (current partial plan not aggressive enough in high-vol) | 1 | HIGH_VOLATILITY |
| 13 | trailing stop: tighten trail to 0.5R in high-vol regime (vs current 1.0R) | 1 | HIGH_VOLATILITY |
| 14 | spread/slippage block: max_spread_usd < 0.40 in high-vol (was 0.50) | 1 | HIGH_VOLATILITY |
| 15 | stricter alpha threshold: require meta_conf >= 0.70 on ambiguous candle patterns | 1 | AMBIGUOUS_CANDLE |
| 16 | earlier break-even: move SL to BE at +1.0R (was +25 unrealized then -10 at SL) | 1 | AMBIGUOUS_CANDLE |
| 17 | no-trade filter: skip entry if candle range > 2.0 * ATR AND direction ambiguous (close near middle) | 1 | AMBIGUOUS_CANDLE |
| 18 | faster partial close: lock 50% at +1R for ambiguous-candle entries | 1 | AMBIGUOUS_CANDLE |
| 19 | tighter regime-flip exit: any opposite-direction 1-bar momentum > 1.5 ATR → close immediately | 1 | AMBIGUOUS_CANDLE |
| 20 | disable strategy in that regime when equity protection is engaged (capital_preservation state) | 1 | EQUITY_PROTECTION |
| 21 | reduce risk multiplier to 0.25 when equity-protection threshold is within 2% of trigger | 1 | EQUITY_PROTECTION |
| 22 | no-trade filter: block new entries when daily DD > 50% of equity-protection threshold | 1 | EQUITY_PROTECTION |
| 23 | earlier break-even: when in equity-protection zone, force BE at +0.3R instead of +1.0R | 1 | EQUITY_PROTECTION |
| 24 | disable strategy in that regime when capital_preservation state active (allow_new_entries=false) | 1 | CAPITAL_PRESERVATION |
| 25 | reduce risk multiplier to 0.0 when capital_preservation active (config already does this) | 1 | CAPITAL_PRESERVATION |
| 26 | no-trade filter: block ALL new entries when account health < 25 (capital_preservation profile) | 1 | CAPITAL_PRESERVATION |
| 27 | faster exit on capital_preservation: trigger exit at -0.3R (not -0.5R) in capital_preservation mode | 1 | CAPITAL_PRESERVATION |

## Profitable Scenarios (for Reference)
| Scenario | Category | Net PnL | R | Close Reason |
|---|---|---|---|---|
| BUY_TP | NORMAL | 19.4 | 2.0 | TP_HIT |
| SELL_TP | NORMAL | 19.4 | 2.0 | TP_HIT |
| BUY_AI_EXIT | NORMAL | 9.399999999999999 | 1.0 | AI_EXIT_CLOSE |
| SELL_AI_EXIT | NORMAL | 9.399999999999999 | 1.0 | AI_EXIT_CLOSE |
| ALPHA_DECAY | STRESS | 0.39999999999999997 | 0.1 | ALPHA_DECAY_EXIT |
| SPREAD_SPIKE_TP | STRESS | 18.9 | 2.0 | TP_HIT |
| MAX_HOLDING | NORMAL | 4.4 | 0.5 | MAX_HOLDING_EXIT |
| PROFIT_LOCK | NORMAL | 14.399999999999999 | 1.5 | PROFIT_LOCK_EXIT |
| STALE_EXIT | NORMAL | 0.39999999999999997 | 0.1 | STALE_POSITION_EXIT |

## Safety Confirmation
| Item | Value |
|---|---|
| Code changed | NO |
| Strategy changed | NO |
| DEMO_MICRO_EXECUTE run | NO |

## Next Steps
1. Review this report with the team.
2. Prioritize CRITICAL mitigations first (HIGH_VOLATILITY, AMBIGUOUS_CANDLE).
3. Implement mitigations in a future sprint (NOT this one).
4. Re-run virtual_lifecycle_validator.py after each mitigation to verify improvement.
5. Do NOT retrain models or change trading strategy without separate sprint approval.
