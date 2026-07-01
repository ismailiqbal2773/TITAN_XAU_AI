# TITAN XAU AI - Final Demo Proof Readiness Audit

**Verdict:** **FINAL_DEMO_PROOF_READY**

**Selected Profile:** prop_funded_safe

**Timestamp:** 2026-07-01T15:41:01.548462+00:00

## Selected Profile Metrics

| Metric | Value |
|---|---|
| selected_profile | prop_funded_safe |
| monthly_return_estimate | 5.18 |
| max_dd | 4.51 |
| pf | 1.63 |
| sharpe | 3.33 |
| sortino | 16.97 |
| wfe | 0.85 |
| monte_carlo_survival | 95.0 |
| risk_per_trade_pct | 0.005 |
| internal_daily_dd_pct | 2.0 |
| internal_total_dd_pct | 6.0 |
| broker_score | 86.0 |
| optimizer_score | 82.0 |
| optimizer_verdict | PROP_FUNDED_READY_CONSERVATIVE |

## OK Checks

- Selected profile: prop_funded_safe
- Aggressive 20% profile is simulation-only and not executable
- Risk per trade: 0.005 <= 0.005
- Internal daily DD: 2.0% <= 2.0%
- Internal total DD: 6.0% <= 6.0%
- External daily DD limit: 3.0%
- Max DD: 4.51% <= 8.0%
- Max open positions: 1
- Leverage assumption: 100
- Minimum RR: 2.0 >= 2.0
- Initial TP R: 3.0 >= 3.0
- Dynamic TP trigger R: 2.0
- ATR SL multiplier: 1.5
- Confidence threshold: 0.5
- Broker score: 86.0 >= 85
- Optimizer verdict: PROP_FUNDED_READY_CONSERVATIVE
- Backtest binding: 15/32 validated, 0 critical unbound
- dry_run: true (safe default)
- live_trading: false (safe default)
- No execution token exists (clean state)
- No martingale/grid/averaging/loss_based_lot in production modules

## Safety

- order_send_called: False
- position_modified: False
- token_created: False
- no_martingale: True
- no_grid: True
- no_averaging: True
- no_loss_based_lot_multiplier: True
