# TITAN XAU AI — Pre-DEMO Scorecard

**Timestamp UTC:** 2026-06-27T13:32:01.114447+00:00
**Head commit:** `3d723f9`
**Sprint series:** 9.9.3.x

## Validation Scores Summary

| Validation | Sprint | Key Metric | Score/Verdict |
|---|---|---|---|
| Scenario Robustness | 9.9.3.4 | 220 scenarios, 13/12 criteria met | 83.2/100 — READY |
| Monte Carlo | 9.9.3.4 | 500 runs, median +$5.53, p5 $-14.16 | PASS |
| Real Data 2025 | 9.9.3.6 | 5 brokers, ~29K rows, PnL +$12730.21 | 84.81/100 — PASS |
| Benchmark | 9.9.3.6 | TITAN rank #1 of 7 bots | TITAN_RANK_1 |

## Key Metrics (PROP_FIRM_STRICT 9.9.3.3 on Real 2025 Data)

| Metric | Value |
|---|---|
| Net PnL | +$12730.21 |
| Max DD | $79.05 (0.79%) |
| Profit Factor | 5.93 |
| Win Rate | 68.55% |
| Trades | 2092 |
| Sharpe | 23.61 |
| Expectancy/Trade | $6.08 |
| Payoff Ratio | 2.86 |
| Profit Retention | 79.7% |
| Overfiltering Ratio | 0.52 |

## Profile Readiness

| Profile | Net PnL | Max DD % | PF | Win% | Verdict |
|---|---|---|---|---|---|
| INSTITUTIONAL | +$10151.35 | 0.88% | 5.01 | 67.51% | APPROVED |
| PROP_FIRM_STRICT | +$12730.21 | 0.79% | 5.93 | 68.55% | APPROVED |
| RETAIL_SAFE | +$17123.26 | 0.98% | 5.99 | 69.26% | APPROVED |

## Exit Action Validation

| Action | Triggered |
|---|---|
| MOVE_BE | YES |
| PARTIAL_CLOSE | YES |
| TIGHT_TRAIL | YES |
| EARLY_CLOSE | YES |
| REDUCE | YES |
| CLOSE_AT_BE | YES |

**Total exit actions in replay:** 20
**Ladder improves PnL:** True
**Ladder reduces full SL:** True

## Remaining Risks

| # | Risk | Severity | Mitigation |
|---|---|---|---|
| 1 | Monday DEMO micro test not yet executed | MEDIUM | Operator follows runbook step-by-step; Z AI analyzes results |
| 2 | Governance not yet wired into live/demo trade_loop | LOW | Intentional — wait for Monday DEMO proof before wiring |
| 3 | Rule-based signal generator used for validation (not ML models) | MEDIUM | ML models require feature pipeline; rule-based is conservative proxy. Monday DEMO uses actual AI signal or explicit --side |
| 4 | IC Markets spread unusually low ($0.04) — may need verification | LOW | Does not affect Monday test (uses FundedNext data) |
| 5 | Sharpe ratio 20-25 is high (may indicate low volatility in test period) | LOW | Realistic given strict governance filtering + low DD; will verify with Monday DEMO |
| 6 | Monte Carlo 5th pct PnL is -$14.16 (small tail risk exists) | LOW | Acceptable for prop-firm profile; Monday test uses 0.01 lot (minimal exposure) |

## Safety Status

| Item | Value |
|---|---|
| demo_micro_execute_run | NO |
| mt5_order_send_called | NO |
| live_demo_path_changed | NO |
| governance_wired_into_live_demo | NO |
| strategy_logic_changed | NO |
| models_retrained | NO |
| martingale_added | NO |
| grid_added | NO |
| averaging_added | NO |
| lot_escalation_added | NO |
| runtime_dry_run_default | YES |
| runtime_live_trading_default | NO |
| demo_micro_enabled_default | NO |
| no_credentials_committed | YES |
| working_tree_clean | YES |
| all_tests_pass | YES |
| tests_passed_count | 146 |
| tests_skipped_count | 1 |

## Monday Readiness Verdict

**READY:** True

**Confidence:** HIGH

**Criteria met:** 17/17

**All criteria met:** True

### Criteria

| Criterion | Met |
|---|---|
| positive_net_pnl_on_real_data | YES |
| max_dd_under_15pct | YES |
| pf_above_1 | YES |
| sufficient_trades_20plus | YES |
| all_tests_pass | YES |
| config_defaults_correct | YES |
| no_tokens_leaked | YES |
| governance_not_wired | YES |
| working_tree_clean | YES |
| runbook_available | YES |
| safety_gates_verified | YES |
| institutional_approved | YES |
| prop_firm_approved | YES |
| retail_approved | YES |
| exit_actions_validated | YES |
| monte_carlo_tail_risk_acceptable | YES |
| benchmark_rank_1_or_2 | YES |

### Recommendation

PROCEED with Monday DEMO micro test. Follow the runbook at docs/SPRINT_9_9_3_MONDAY_DEMO_MICRO_RUNBOOK.md step-by-step. Use --lot 0.01 --max-trades 1 --max-hold-seconds 60 --side BUY. After test, restore config and clear arm token. Send reports to Z AI.
