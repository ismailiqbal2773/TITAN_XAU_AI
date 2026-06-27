# Sprint 9.9.3.4 — Competition Benchmark Report

**Timestamp UTC:** 2026-06-27T03:31:45.311495+00:00

## Ranking by Competition Score

| Rank | Bot | Total PnL | Max DD | PF | Win Rate | Trade Count | Score |
|---|---|---|---|---|---|---|---|
| 1 | trend_only | $78.79 | $22.42 | 1.7503 | 72.73% | 55 | 67.02 |
| 2 | TITAN_9_9_3_3_PROP_FIRM_STRICT | $62.57 | $14.8775 | 2.0306 | 79.31% | 58 | 66.91 |
| 3 | fixed_threshold | $20.36 | $36.29 | 1.2529 | 64.71% | 34 | 53.17 |
| 4 | mean_reversion_only | $6.23 | $26.25 | 1.1068 | 67.65% | 34 | 52.67 |
| 5 | buy_and_hold_half_risk | $-35.23 | $57.19 | 0.868 | 55.0% | 220 | 38.56 |
| 6 | random_entry_half_risk | $-56.88 | $59.515 | 0.6427 | 51.89% | 106 | 38.1 |
| 7 | baseline_xgb_no_gov | $-70.47 | $114.38 | 0.868 | 55.0% | 220 | 30.0 |

**TITAN beats all bots:** False

## TITAN Detailed Metrics

| Metric | Value |
|---|---|
| Total PnL | $62.57 |
| Max DD | $14.8775 |
| PF | 2.0306 |
| Win rate | 79.31% |
| Trade count | 58 |
| Blocked count | 162 |
| Blocked winners | 75 |
| Blocked losers | 87 |
| Missed profit | $238.52 |
| Avoided loss | $460.59 |
| Overfiltering ratio | 0.5179 |

### Competition Score Breakdown

| Component | Score |
|---|---|
| net_pnl_quality | 6.26 |
| max_dd_control | 17.02 |
| profit_factor_expectancy | 7.73 |
| stress_survival | 15.0 |
| profit_retention | 5.49 |
| overfiltering_control | 7.41 |
| trade_frequency_sufficiency | 3.0 |
| explainability_completeness | 5.0 |
| **TOTAL** | **66.91 / 100** |

### Exit Action Counts

| Action | Count |
|---|---|
| HOLD | 38 |
| MOVE_BE | 17 |
| PARTIAL_CLOSE | 3 |
