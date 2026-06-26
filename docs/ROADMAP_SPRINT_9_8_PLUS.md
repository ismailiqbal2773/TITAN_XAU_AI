# TITAN XAU AI — Architecture Roadmap (Sprint 9.8+)

## Sprint 9.8: Virtual Trade Lifecycle + AI Exit Validation
**Status: COMPLETE**

- Virtual Position Ledger (open/update/close)
- Net Profit Engine (gross - spread - commission - slippage - swap)
- SL/TP hit detection with ambiguous candle handling
- AI Exit integration (advisory close for virtual positions)
- 25 scenario test matrix
- Virtual lifecycle validator with metrics

## Sprint 9.9: FundedNext DEMO Micro Full-Cycle Test
**Status: PLANNED**

- Run TITAN on FundedNext DEMO with 0.01 lot
- Full signal-to-close cycle with real MT5 bars
- Virtual position ledger tracks all trades
- Verify dry_run=true, no order_send, no live execution
- Collect 24-hour DEMO evidence

## Sprint 9.10: Performance Analytics + Net Profit Engine
**Status: PLANNED**

- Full performance analytics dashboard
- Trade-by-trade net PnL breakdown
- Cost analysis (spread, commission, slippage, swap)
- Win rate, profit factor, Sharpe, Sortino, max DD
- Monthly performance breakdown
- Compare gross vs net performance

## Sprint 9.11: Dynamic SL/TP + Trade Management Intelligence Shadow Mode
**Status: PLANNED**

- AI-driven SL/TP adjustment in shadow mode
- Adaptive trailing based on regime + volatility
- Partial profit taking at configurable R levels
- Break-even logic driven by statistical justification
- All changes tracked in virtual ledger first

## Sprint 9.12: Market Structure Scenario Engine + Alpha/Regime Conflict Governance
**Status: PLANNED**

- Market structure detection (trend/range/breakout/reversal)
- Alpha-regime conflict detection and governance
- Risk reduction when regime contradicts alpha
- CEO AI governance for regime-aware decisions
- Scenario-based stress testing

## Sprint 9.13: Historical Replay + Scenario Stress Test Matrix
**Status: PLANNED**

- Replay historical data through full TITAN pipeline
- Scenario stress test matrix (COVID, Ukraine, SVB, gold rally)
- Backtest AI Exit decisions against historical outcomes
- Validate virtual ledger PnL against historical prices
- Generate institutional-grade stress test report

## Sprint 9.14: Controlled Demo Activation
**Status: PLANNED**

- Switch from dry_run=true to demo execution mode
- Real MT5 orders on DEMO account (not live)
- Virtual ledger + real DEMO position reconciliation
- TITAN_LIVE_TRADING=1 enabled for DEMO only
- All safety gates verified before activation

## Sprint 9.15: 7-day Demo Forward Qualification
**Status: PLANNED**

- 7-day continuous DEMO trading
- Daily PnL, win rate, max DD monitoring
- Kill switch stability verification
- Journal integrity over 7 days
- Capital protection event tracking
- Pre-funded qualification gate

## Sprint 9.16: 30-day Demo Forward Qualification
**Status: PLANNED**

- 30-day continuous DEMO trading
- Full month performance analytics
- Regime transition stability
- Alpha decay measurement
- Cost analysis over 30 days
- Funded account readiness gate

## Sprint 9.17: Production Packaging + Licensing + Commercial Hardening
**Status: PLANNED**

- Production packaging (TITAN.exe)
- Hardware-locked licensing
- Commercial deployment guide
- Operator training documentation
- Final institutional audit
- Production go-live checklist

---

## Architecture Rules (Locked)

1. **No gross-profit booking** — net profit only (after all costs)
2. **Known scenarios handled explicitly** — unknown scenarios fail-safe
3. **Regime-alpha conflict = risk protection first** — never trade against regime
4. **No blind SL** — SL must be ATR-based or AI-justified
5. **No blind TP** — TP must be ATR-based or AI-adjusted
6. **No unknown market trading** — if regime is unclear, don't trade
7. **No live action without governance approval** — CEO AI must approve
8. **dry_run safety preserved** — never weaken dry_run guard
9. **max_lot=0.01 hard cap** — never exceed institutional limit
10. **All decisions journaled** — every signal, decision, order, exit, cost
