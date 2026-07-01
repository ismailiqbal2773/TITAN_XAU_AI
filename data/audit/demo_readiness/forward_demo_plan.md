# TITAN XAU AI - 7-Day Forward Demo Plan

**Profile:** prop_funded_safe
**Broker:** MetaQuotes-Demo
**Lot:** 0.01 (fixed for proof)
**Leverage:** 1:100

## Risk Limits

| Limit | Value |
|---|---|
| Risk per trade | 0.5% |
| Internal daily DD stop | 2.0% |
| Internal total DD stop | 6.0% |
| External daily DD limit | 3.0% |
| External total DD limit | 8.0% |
| Max open positions | 1 |
| Max lot | 0.01 |

## Schedule

### Day 0: Readiness Check
- [ ] Run final_demo_proof_readiness_audit.py (must be READY)
- [ ] Run build-request with prop_funded_safe (must PASS)
- [ ] Run check_open_positions.py (must be SAFE_NO_OPEN_POSITIONS)
- [ ] Read operator checklist
- [ ] Create execution token (operator only)
- [ ] Execute first managed trade
- [ ] Verify receipt, monitor, forensics

### Days 1-7: Demo Observation
- [ ] Monitor daily for open positions, DD, spread/slippage
- [ ] Record daily metrics (see below)
- [ ] Max one open trade at a time
- [ ] No manual override except emergency close
- [ ] Daily DD stop at 2%
- [ ] Total DD stop at 6%
- [ ] Weekly stop if abnormal broker behavior (spread spike, requote flood)

### Daily Report Template
```
Day N:
  Trades: X
  Net PnL: $X.XX
  Current DD: X.XX%
  Max DD today: X.XX%
  Spread avg: X.XX
  Slippage avg: X.XX
  Broker score: XX
  Rejected signals: X
  Risk events: [list]
  Journal integrity: OK/BROKEN
  Open positions at EOD: 0/1
```

### After 7 Days
- [ ] Review all daily reports
- [ ] Check: 0 DD breaches
- [ ] Check: 0 journal integrity failures
- [ ] Check: broker score remained >= 85
- [ ] Decision: continue to 30-day demo OR fix blockers

## Safety Invariants
- no_martingale: True
- no_grid: True
- no_averaging: True
- no_loss_based_lot_multiplier: True
- Execution requires operator token (not created by Z AI)
- 20% monthly is NOT a target for this proof
- This plan does NOT trade. It only documents the observation schedule.
