# Exness Stress Test (Sprint v2.8.7-M)

**Timestamp:** 2026-07-11T06:38:54.100454+00:00

## Verdict: STRESS_PASS

- Worst scenario: 3_initial_losses
- Worst DD: 0.0472
- Worst margin: 0.0985

## Scenario Results

| Scenario | Return | PF | Max DD | DD Breaches | Margin Max | Verdict |
|---|---|---|---|---|---|---|
| baseline | 0.9067 | 1.1848 | 0.0000 | 0 | 0.0984 | PASS |
| spread_x1_5 | 0.0000 | 0 | 0.0000 | 0 | 0.0000 | PASS |
| spread_x2 | 0.0000 | 0 | 0.0000 | 0 | 0.0000 | PASS |
| slippage_conservative | 0.1820 | 1.0476 | 0.0040 | 0 | 0.0985 | PASS |
| signal_20pct_degraded | 0.6808 | 1.1844 | 0.0125 | 0 | 0.0984 | PASS |
| 3_initial_losses | 0.7921 | 1.1705 | 0.0472 | 0 | 0.0984 | PASS |
| rr_10pct_reduced | 0.6549 | 1.1464 | 0.0000 | 0 | 0.0984 | PASS |
