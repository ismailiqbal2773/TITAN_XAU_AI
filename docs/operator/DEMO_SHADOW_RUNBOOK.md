# TITAN XAU AI — Demo Shadow Runbook

**Sprint v2.8.7-F**
**Status: NOT AUTHORIZED — demo_go_decision = NO_SAFE_PARAMETER_FOUND**

## When Is Demo Shadow Allowed?

Demo shadow testing is ONLY allowed when:

1. `demo_go_decision = DEMO_SHADOW_ALLOWED` in the latest parameter discovery run
2. CTO has reviewed and approved the candidate parameters
3. Operator has explicitly created an execution token
4. Broker is MetaQuotes-Demo (no live/funded brokers)
5. Max lot size = 0.01
6. Max 2 trades per day
7. Max total drawdown = 8%
8. Max daily drawdown = 2.5%

## Current Status

As of Sprint v2.8.7-F:

| Model Profile | demo_go_decision | Trades Authorized |
|---|---|---|
| v1_legacy | NO_SAFE_PARAMETER_FOUND | ❌ No |
| v2_feature_normalized | NO_SAFE_PARAMETER_FOUND | ❌ No |
| v2_multibroker | NO_SAFE_PARAMETER_FOUND | ❌ No |

**No demo shadow testing is authorized.**

## Demo Shadow Procedure (When Authorized)

If and when demo_go_decision becomes DEMO_SHADOW_ALLOWED:

### Step 1: CTO Review
- CTO reviews `final_candidate_params.json`
- CTO verifies all acceptance criteria met
- CTO signs off on candidate parameters

### Step 2: Operator Setup
- Operator creates local execution token (NOT automatic)
- Operator configures MetaQuotes-Demo broker
- Operator verifies dry_run=true initially

### Step 3: Shadow Test
- Run in shadow mode (no real orders)
- Compare model predictions vs actual market
- Monitor for 7-30 days minimum
- Verify OOS performance matches backtest

### Step 4: Gradual Activation
- Only after shadow test confirms performance
- Start with 0.01 lot, 1 trade/day
- Gradually increase to 0.01 lot, 2 trades/day
- Monitor drawdown daily

### Step 5: Review Gates
- If any daily DD > 2.5% → stop
- If total DD > 8% → stop
- If 3 consecutive losses → stop
- If prop violation → stop

## Safety Rules

- **NEVER** trade on a live or funded account
- **NEVER** bypass CEO governance
- **NEVER** bypass meta-label filter
- **NEVER** increase lot size without CTO approval
- **NEVER** remove the daily trade limit
- **NEVER** set production_ready=True
