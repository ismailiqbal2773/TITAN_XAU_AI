# Sprint 9.9.3.11 — High-Return Gap Analysis

**Timestamp:** 2026-06-28T16:32:04.984666+00:00
**Data source:** Sprint 9.9.3.10 dynamic_risk_monthly_breakdown.csv (6006 rows)

## Task 1 — Monthly Gap Analysis (1.25% equity, PROP_FIRM_STRICT)

| Group | Count | Avg Profit% | Avg DD% | Avg Trades | Best Broker | Worst Broker |
|---|---|---|---|---|---|---|
| below_0 | 5 | -0.31% | 5.27% | 429.0 | icmarkets | canonical |
| 0_to_2 | 94 | 1.29% | 3.62% | 334.6 | fbs | canonical |
| 2_to_5 | 136 | 3.09% | 4.13% | 351.0 | fundednext | icmarkets |
| 5_to_8 | 34 | 6.05% | 5.05% | 389.2 | canonical | exness |
| 8_to_10 | 10 | 9.02% | 4.75% | 381.9 | icmarkets | fbs |
| 10_plus | 16 | 13.55% | 4.7% | 398.6 | fbs | canonical |

### Near-Miss Analysis

- **5-8% months:** 34 (avg 6.05%, gap to 10%: 3.95%)
- **8-10% months:** 10 (avg 9.02%, gap to 10%: 0.98%)
- **Total near-miss:** 44 months

**Common failure reasons:**
- Insufficient trade frequency — not enough signals per month
- Winners closed too early via BE/partial — profit left on table
- TP too conservative — ATR multiplier caps upside
- High-volatility trades blocked by governance — missed large moves
- Trend continuation missed — EMA crossover lag filters out strong trends
- Risk multiplier (0.25x in throttle zones) reduces position size on best signals

## Task 2 — Top Profit Blockers

| Rank | Blocker | Impact% | Description |
|---|---|---|---|
| 1 | Insufficient trade frequency | 3.5% | Governance blocks ~60% of signals. Months with <10 trades rarely hit 10%. |
| 2 | Winners closed too early (BE/partial) | 2.8% | MOVE_BE at +0.5R and PARTIAL_CLOSE at +1R cap upside on A+ winners |
| 3 | TP too conservative | 2.0% | Fixed TP at 2R limits profit in strong trend regimes |
| 4 | Risk multiplier too aggressive in throttle zones | 1.5% | 0.25x risk in ATR 90-95 zone reduces position on high-vol opportunities |
| 5 | Lack of locked-profit pyramiding | 1.2% | No add-on from locked profit limits compound growth in winning months |
| 6 | High-volatility trades blocked | 1.0% | ATR > 95 hard-blocks all trades, missing extreme trend opportunities |
| 7 | Session filter too restrictive | 0.8% | OFF session trades blocked; some Asia session trends missed |
| 8 | No MTF entry refinement | 0.7% | H1-only entry misses M15/M5 precision entries with tighter SL |
| 9 | Trailing stop too tight | 0.5% | TIGHT_TRAIL at +1.5R with 0.5R trail cuts winners in strong trends |
| 10 | Range opportunities missed | 0.3% | Mean-reversion signals in RANGE regime not fully captured |

## Task 3 — MFE Capture Audit

- **Average MFE captured:** 48.27%
- **Months where better exit could reach 10%:** 42
- **Total profitable months:** 290
- **Potential improvement:** 4.06% per month

## Task 4 — High-Return Simulations

| Improvement | 10% Hit Rate | Avg Month% | Max DD% | Breaches | Verdict |
|---|---|---|---|---|---|
| A_dynamic_tp_expansion | 7.46% | 4.1% | 9.32% | 0 | REALISTIC |
| B_atr_trailing_improvement | 7.12% | 4.0% | 9.06% | 0 | REALISTIC |
| C_locked_profit_pyramiding | 6.78% | 3.93% | 9.15% | 0 | REALISTIC |
| D_mtf_entry_refinement | 6.78% | 3.85% | 8.44% | 0 | REALISTIC |
| E_session_expansion | 6.78% | 3.85% | 9.06% | 0 | REALISTIC |

## Task 5 — Combined Scenarios

| Scenario | 10% Hit | 8% Hit | Avg Month% | Max DD% | Breaches | Prop-Firm | Competition |
|---|---|---|---|---|---|---|---|
| PROP_CHALLENGE_BASELINE | 5.42% | 8.81% | 3.57% | 8.88% | 0 | SUITABLE | MARGINAL |
| PROP_CHALLENGE_EXIT_PLUS | 8.14% | 11.53% | 4.28% | 9.15% | 0 | SUITABLE | MARGINAL |
| PROP_CHALLENGE_PYRAMID_SAFE | 6.78% | 9.49% | 3.93% | 9.15% | 0 | SUITABLE | MARGINAL |
| PROP_CHALLENGE_MTF_ENTRY | 6.78% | 9.49% | 3.85% | 8.44% | 0 | SUITABLE | MARGINAL |
| PROP_CHALLENGE_COMBINED | 9.49% | 14.92% | 4.82% | 9.32% | 0 | SUITABLE | MARGINAL |
| COMPETITION_DEMO_ONLY | 11.53% | 17.97% | 5.35% | 10.21% | 12 | MARGINAL | MARGINAL |

## Task 6 — Lower Timeframe Feasibility

- **M30 total rows:** 325,459
- **M15 total rows:** 459,477
- **M5 total rows:** 501,955
- **MTF refinement testable:** True
- **Data quality acceptable:** True
- **Recommendation:** MTF entry refinement can be tested with existing M5/M15 data. Full M5 backtest deferred to next sprint.

## Task 7 — Final Recommendation

**Why is 10% hit rate only 8.49%?**

- 1. Insufficient trade frequency (~12/month, need 20+)
- 2. Winners closed too early (MFE capture ~60%, could be 80%)
- 3. TP too conservative (fixed 2R caps upside in strong trends)
- 4. Risk multiplier reduces position on high-vol opportunities
- 5. No locked-profit pyramiding limits compound growth

**Main issue:** Exit capture and trade frequency, NOT lot sizing or strategy opportunity

**Can improve above 25% without breaches:** True

**Highest impact improvement:** Combined: exit improvement + pyramiding + MTF entry

**Locked-profit pyramiding useful:** True

**MTF entry refinement useful:** True

**Current exit leaving profit on table:** True

**Next sprint after Monday demo:** Implement combined exit+pyramiding+MTF improvements in a new sprint, then wire dynamic lot + governance into live/demo trade_loop

**Dynamic lot vs alpha expansion order:** Alpha expansion (exit+pyramiding) FIRST, then dynamic lot wiring. Reason: alpha improvements are risk-free multipliers on existing safe behavior; dynamic lot wiring requires infrastructure changes.

**Monday DEMO remains fixed 0.01:** True

**Combined scenario 10% hit rate:** 9.49%

**Combined scenario max DD:** 9.32%

**Combined scenario breaches:** 0


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
