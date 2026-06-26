# Sprint 9.8 — Virtual Lifecycle Report

**Verdict: VIRTUAL_LIFECYCLE_READY**

**Order_send used: False**

## Metrics

| Metric | Value |
|---|---|
| total_virtual_entries | 17 |
| open_positions | 0 |
| closed_positions | 17 |
| sl_closes | 4 |
| tp_closes | 3 |
| ai_exit_closes | 10 |
| profit_lock_closes | 1 |
| timeout_closes | 1 |
| gross_pnl_total | 55.0 |
| net_pnl_total | 44.1 |
| win_rate_net | 52.94 |
| profit_factor_net | 1.85 |
| max_drawdown_net | 54.64 |
| avg_r | 0.3235 |
| expectancy_net | 2.5941 |
| avg_holding_time | 0.0 |
| mfe_avg | 7.4706 |
| mae_avg | 3.6471 |
| cost_drag_total | 10.9 |
| cost_drag_pct | 19.82 |
| journal_integrity | True |

## Scenarios (17)

| Scenario | Direction | Reason | Gross | Net | R |
|---|---|---|---|---|---|
| BUY_TP | BUY | TP_HIT | 20.00 | 19.40 | 2.00 |
| BUY_SL | BUY | SL_HIT | -10.00 | -10.60 | -1.00 |
| SELL_TP | SELL | TP_HIT | 20.00 | 19.40 | 2.00 |
| SELL_SL | SELL | SL_HIT | -10.00 | -10.60 | -1.00 |
| BUY_AI_EXIT | BUY | AI_EXIT_CLOSE | 10.00 | 9.40 | 1.00 |
| SELL_AI_EXIT | SELL | AI_EXIT_CLOSE | 10.00 | 9.40 | 1.00 |
| REGIME_FLIP_BUY | BUY | REGIME_RISK_EXIT | 0.00 | -0.60 | 0.00 |
| REGIME_FLIP_SELL | SELL | REGIME_RISK_EXIT | 0.00 | -0.60 | 0.00 |
| ALPHA_DECAY | BUY | ALPHA_DECAY_EXIT | 1.00 | 0.40 | 0.10 |
| AMBIGUOUS_CANDLE | BUY | SL_HIT | -10.00 | -10.60 | -1.00 |
| SPREAD_SPIKE_TP | BUY | TP_HIT | 20.00 | 18.90 | 2.00 |
| HIGH_VOLATILITY | BUY | SL_HIT | -10.00 | -10.80 | -1.00 |
| MAX_HOLDING | BUY | MAX_HOLDING_EXIT | 5.00 | 4.40 | 0.50 |
| PROFIT_LOCK | BUY | PROFIT_LOCK_EXIT | 15.00 | 14.40 | 1.50 |
| STALE_EXIT | BUY | STALE_POSITION_EXIT | 1.00 | 0.40 | 0.10 |
| EQUITY_PROTECTION | BUY | EQUITY_PROTECTION_EXIT | -5.00 | -5.60 | -0.50 |
| CAPITAL_PRESERVATION | BUY | CAPITAL_PRESERVATION_EXIT | -2.00 | -2.60 | -0.20 |
