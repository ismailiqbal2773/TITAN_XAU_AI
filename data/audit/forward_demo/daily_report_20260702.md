# TITAN XAU AI - Forward Demo Daily Report

**Date (UTC):** 20260702
**Generated:** 2026-07-02T04:07:49.336714+00:00
**Verdict:** **FORWARD_DAY_WARN**

## Account + Profile

| Field | Value |
|---|---|
| date | 20260702 |
| profile | prop_funded_safe |
| account_server | metaquotes-demo |
| account_type | demo |
| broker_score | 0.0 |

## Positions + Trades

| Field | Value |
|---|---|
| open_positions_count | 0 |
| titan_magic_positions_count | 0 |
| trades_today | 0 |
| closed_trades_today | 0 |
| net_pnl_today | 0.0 |
| rejected_signals | 0 |

## Risk

| Field | Value |
|---|---|
| max_daily_dd | 0.0 |
| total_dd | 0.0 |
| risk_events | 0 |

## Integrity

| Field | Value |
|---|---|
| journal_integrity | OK |
| receipt_integrity | OK |
| no_martingale | True |
| no_grid | True |
| no_averaging | True |
| no_loss_multiplier | True |

## Warnings

- NO_TRADES_TODAY: no trades were placed or closed today - observation may continue but flag for review

## OK Checks

- Account is DEMO (metaquotes-demo)
- Profile approved: prop_funded_safe
- Open TITAN positions: 0 (<= 1)
- max_daily_dd=0.0000 <= 0.0300
- No old fallback trade used as proof
- No martingale / grid / averaging / loss-based lot multiplier

## Safety

| Field | Value |
|---|---|
| order_send_called | False |
| position_modified | False |
| no_martingale | True |

## Notes

- This daily report is OBSERVATION ONLY.
- The generator NEVER imports MetaTrader5, NEVER sends orders, NEVER modifies positions.
- No martingale / grid / averaging / loss-based lot multipliers.
