# TITAN XAU AI - Auto Lot Sizing Audit (v2.8.5-D.1/E)

**Verdict:** **AUTO_LOT_SIZING_PASS**

**Timestamp:** 2026-07-03T09:24:01.683300+00:00

**Blockers:** 0


## Warnings

- BUILD_REQUEST_AUTO_LOT_MISSING: run build-request to populate

## OK Checks

- DEMO_SAFE basic: final_lot=0.01 (<= 0.01)
- Equity growth increases raw_lot: 0.5 -> 2.0
- Risk percent constant across calculations
- Invalid SL blocks
- Invalid tick value blocks
- Invalid equity blocks
- Drawdown reduces risk_amount
- Daily DD hard limit blocks
- Total DD cap blocks
- CEO risk_multiplier=0.5 reduces risk_amount
- CEO risk_multiplier capped at 1.0
- Capital preservation reduces risk_amount
- Loss streak does not increase lot
- Broker lot step rounds down: raw=5.0 rounded=5.0
- Max open positions blocks
- No martingale: lot does not increase after loss (equity dropped)

## Safety

- order_send_called: False
- position_modified: False
- token_created: False
