# TITAN XAU AI - Demo Proof Operator Checklist
**Generated:** 2026-07-01T15:39:20.322600+00:00
**Profile:** prop_funded_safe
**Broker:** MetaQuotes-Demo (score >= 85)

## Pre-Execution Checklist

### 1. MT5 Terminal
- [ ] MT5 terminal is open and running
- [ ] MT5 is connected to MetaQuotes-Demo server
- [ ] Auto-trading is ENABLED in MT5 terminal

### 2. Account Verification
- [ ] Account type is DEMO (not real/live)
- [ ] Account server contains 'MetaQuotes-Demo'
- [ ] Account balance is sufficient for 0.01 lot XAUUSD
- [ ] Leverage is set to 1:100

### 3. Symbol Verification
- [ ] XAUUSD symbol is available in Market Watch
- [ ] Current spread is <= 0.35 (max threshold)
- [ ] No spread spike or news event active

### 4. Position Safety
- [ ] Open TITAN positions = 0 (run check_open_positions.py)
- [ ] No orphan positions from previous runs
- [ ] No other EAs trading on this account

### 5. Profile Selection
- [ ] Selected profile: prop_funded_safe
- [ ] NO aggressive profile selected
- [ ] NO aggressive 20% profile (simulation-only)

### 6. Risk Limits
- [ ] Risk per trade: 0.5% (0.005)
- [ ] Internal daily DD stop: 2.0%
- [ ] Internal total DD stop: 6.0%
- [ ] External daily DD limit: 3.0%
- [ ] External total DD limit: 8.0%
- [ ] Max open positions: 1
- [ ] Lot size: 0.01 (fixed for proof)

### 7. SL/TP Geometry
- [ ] ATR SL multiplier: 1.5
- [ ] Initial TP R: 3.0
- [ ] Minimum RR: 2.0
- [ ] Dynamic TP trigger R: 2.0
- [ ] Breakeven trigger R: 1.0
- [ ] Trailing trigger R: 1.75
- [ ] Profit lock trigger R: 3.0

### 8. Safety Gates
- [ ] dry_run: true in config/runtime.yaml
- [ ] live_trading: false in config/runtime.yaml
- [ ] TITAN_LIVE_TRADING env var is NOT set
- [ ] No execution token created by Z AI
- [ ] Token will be created by operator only

### 9. Execution Preparation
- [ ] Final demo readiness audit: FINAL_DEMO_PROOF_READY
- [ ] Build-request: PASS
- [ ] Operator has read and understood all risk limits
- [ ] Operator understands: execution requires separate human action
- [ ] Operator has emergency close plan ready

### 10. What NOT to Do
- [ ] DO NOT use aggressive profile for demo proof
- [ ] DO NOT increase lot above 0.01
- [ ] DO NOT allow more than 1 open position
- [ ] DO NOT disable dry_run safety
- [ ] DO NOT enable live trading
- [ ] DO NOT use real account
- [ ] DO NOT use non-MetaQuotes-Demo broker

## Execution Command (Operator Only)
```
python scripts/operator/create_local_operator_execution_token.py --symbol XAUUSD --lot 0.01 --broker MetaQuotes-Demo --expiry-minutes 10

python scripts/operator/run_managed_demo_micro_trade.py \
  --execute-and-monitor \
  --i-understand-demo-risk \
  --confirm-symbol XAUUSD \
  --confirm-lot 0.01 \
  --confirm-broker MetaQuotes-Demo \
  --confirm-one-order-only \
  --confirm-not-live \
  --confirm-environment-locked \
  --confirm-model-parity-pass \
  --confirm-local-operator \
  --confirm-managed-trailing \
  --prop-funded-profile prop_funded_safe \
  --use-adaptive-trailing \
  --use-dynamic-tp-extension \
  --monitor-duration-minutes 30 \
  --monitor-interval-seconds 5
```

## After Execution
- [ ] Verify receipt written
- [ ] Run diagnose_latest_execution_receipt.py
- [ ] Run collect_demo_micro_trade_forensics.py
- [ ] Check monitor iterations > 1
- [ ] Check final position status
- [ ] Document results for 7-day forward demo plan

## Safety Invariants
- no_martingale: True
- no_grid: True
- no_averaging: True
- no_loss_based_lot_multiplier: True
- Execution requires operator token (not created by Z AI)
- This checklist does NOT trade. It only prints instructions.