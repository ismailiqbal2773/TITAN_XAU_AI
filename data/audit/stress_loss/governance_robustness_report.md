# Sprint 9.9.3.4 — Governance Robustness Report

**Timestamp UTC:** 2026-06-27T03:31:45.309774+00:00
**Random seed:** 20261993 (deterministic)
**Scenario count:** 220

## Important
- This is a **SIMULATION** — no real or demo MT5 execution.
- **DEMO_MICRO_EXECUTE was NOT run.**
- **Production live path unchanged.** No martingale/grid/averaging/lot escalation.
- **No models retrained.**

## Scenario Distribution

### By Regime

| Regime | Count |
|---|---|
| LOW_LIQUIDITY | 36 |
| TREND_UP | 26 |
| BREAKOUT | 35 |
| RANGE | 34 |
| HIGH_VOL | 31 |
| TREND_DOWN | 29 |
| TRANSITION | 29 |

### By Broker

| Broker | Count |
|---|---|
| FundedNext | 58 |
| Exness | 39 |
| IC Markets | 47 |
| Dukascopy | 35 |
| FBS | 41 |

### By Session

| Session | Count |
|---|---|
| ASIA | 42 |
| LONDON | 47 |
| NY | 40 |
| OVERLAP | 49 |
| OFF | 42 |

### By Liquidity

| Liquidity | Count |
|---|---|
| GOOD | 77 |
| NORMAL | 64 |
| POOR | 79 |

## Walk-Forward Replay: NO_GOV vs 9.9.3.2 vs 9.9.3.3

| Configuration | Net PnL | Max DD | PF | Trade Freq | Blocked W/L | Missed Profit | Avoided Loss | Overfilter | Score |
|---|---|---|---|---|---|---|---|---|---|
| NO_GOVERNANCE | -70.47 | 114.38 | 0.868 | 100.0% | 0/0 | 0 | 0 | 0.0 | 40.0 |
| SPRINT_9_9_3_2_RETAIL_SAFE | 40.345 | 40.3925 | 1.2861 | 46.8% | 57/60 | 193.73 | 329.56 | 0.5878 | 56.89 |
| SPRINT_9_9_3_2_PROP_FIRM_STRICT | 29.3625 | 26.4575 | 1.4836 | 17.7% | 94/87 | 333.03 | 460.59 | 0.7231 | 56.08 |
| SPRINT_9_9_3_2_INSTITUTIONAL_CAPITAL_PROTECTION | 8.0 | 0.0 | inf | 1.4% | 118/99 | 447.22 | 533.69 | 0.838 | 66.61 |
| SPRINT_9_9_3_3_RETAIL_SAFE | 52.7275 | 37.09 | 1.3739 | 52.3% | 45/60 | 149.48 | 329.56 | 0.4536 | 59.57 |
| SPRINT_9_9_3_3_PROP_FIRM_STRICT | 62.57 | 14.8775 | 2.0306 | 26.4% | 75/87 | 238.52 | 460.59 | 0.5179 | 66.91 |
| SPRINT_9_9_3_3_INSTITUTIONAL_CAPITAL_PROTECTION | 53.505 | 3.0 | 18.835 | 10.4% | 99/98 | 331.42 | 522.8 | 0.6339 | 72.37 |

## Trade Frequency Analysis

| Profile | Allowed | Blocked | Trade Freq | Monthly Trades | Capital Idle | Acceptance |
|---|---|---|---|---|---|---|
| RETAIL_SAFE | 115 | 105 | 52.27% | 115 | 47.7% | retail_preserves_opportunities: YES |
| PROP_FIRM_STRICT | 58 | 162 | 26.36% | 58 | 73.6% | prop_firm_not_inactive: YES |
| INSTITUTIONAL_CAPITAL_PROTECTION | 23 | 197 | 10.45% | 23 | 89.5% | institutional_capital_efficient: YES |

## Exit Management Replay

| Metric | Value |
|---|---|
| Total exit actions triggered | 20 |
| PnL with ladder | 62.57 |
| PnL without ladder | -35.23 |
| Full SL events with ladder | 6 |
| Full SL events without ladder | 17 |
| MFE captured with ladder | 123.28 |
| MFE captured without ladder | 463.22 |
| Ladder improves PnL | True |
| Ladder reduces full SL | True |
| Ladder captures MFE better | False |

### Exit Action Breakdown

| Action | Count |
|---|---|
| MOVE_BE | 17 |
| PARTIAL_CLOSE | 3 |

## Robustness Verdict

**Ready for live/demo wiring:** True

**Confidence:** HIGH

**Final competition score:** 66.91 / 100

**Score improvement vs no governance:** +26.91

**Score improvement vs Sprint 9.9.3.2:** +10.83

**Monte Carlo 5th pct PnL:** $-14.16

**Monte Carlo worst PnL:** $-34.31

**Monte Carlo worst DD:** $58.95

**TITAN competitive vs bots:** True

**TITAN rank:** #2

**Criteria met:** 13/12

**Monte Carlo median PnL:** $5.53

**Trade frequency score:** 3.0 / 5

**Metrics look realistic:** True

### Acceptance Criteria

| Criterion | Met |
|---|---|
| governance_improves_score_out_of_sample | YES |
| max_dd_controlled | YES |
| missed_profit_reasonable | YES |
| overfiltering_reasonable | YES |
| trade_frequency_acceptable | YES |
| exit_actions_trigger_in_replay | YES |
| monte_carlo_5th_pct_acceptable | YES |
| monte_carlo_median_positive | YES |
| titan_competitive_vs_bots | YES |
| ladder_improves_pnl | YES |
| ladder_reduces_full_sl | YES |
| titan_lower_dd_than_baseline | YES |
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
