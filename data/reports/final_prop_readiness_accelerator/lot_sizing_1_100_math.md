# 1:100 Lot Sizing Math (Sprint v2.8.7-M)

**Timestamp:** 2026-07-11T06:38:53.193789+00:00

## Verdict: LOT_SIZING_PASS

## Formula

```
risk_amount = equity * risk_percent
sl_distance = abs(entry - stop_loss)
estimated_loss_per_lot = sl_distance * 100 oz
lot_size = risk_amount / estimated_loss_per_lot
notional = entry_price * 100 * lot_size
margin = notional / leverage(100)
margin_usage = margin / equity
```

## Sample Calculations

| Entry | ATR | SL Dist | Risk $ | Lot | Margin | Margin Usage | Loss=Risk? | Not 0.01? | Safe? |
|---|---|---|---|---|---|---|---|---|---|
| $2000 | 5 | 10 | $1250.0 | 1.25 | $2500.0 | 0.0250 | ✅ | ✅ | ✅ |
| $3000 | 8 | 16 | $1250.0 | 0.7812 | $2343.75 | 0.0234 | ✅ | ✅ | ✅ |
| $4000 | 12 | 24 | $1250.0 | 0.5208 | $2083.33 | 0.0208 | ✅ | ✅ | ✅ |
| $5000 | 15 | 30 | $1250.0 | 0.4167 | $2083.33 | 0.0208 | ✅ | ✅ | ✅ |
