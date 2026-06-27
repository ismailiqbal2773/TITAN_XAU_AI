# Sprint 9.9.3.3 — Governance Threshold Sweep

**Timestamp UTC:** 2026-06-27T02:20:21.841743+00:00
**Source report:** `data/audit/virtual_lifecycle/virtual_lifecycle_report.json`
**Synthetic scenarios tested:** 12

## Methodology
- Tested combinations of: meta_block, meta_throttle, atr_block, atr_throttle, spread_block, flip_block, risk_mult_warn.
- Each combination scored using competition-style objective function.
- Best config = highest score (not necessarily zero losses).

## RETAIL_SAFE

**Total combinations tested:** 150

**Best score:** 95.66

**Best config:**

```json
{
  "min_meta_confidence_block": 0.55,
  "min_meta_confidence": 0.7,
  "min_meta_confidence_throttle": 0.7,
  "max_atr_percentile_block": 92,
  "max_atr_percentile_throttle": 85,
  "max_spread_usd_block": 0.8,
  "max_regime_flip_prob_block": 0.75,
  "risk_multiplier_in_warn_vol": 0.75
}
```

### Top 5 Configurations

| Rank | Score | Net PnL | Max DD | PF | Blocked | Missed Profit | Avoided Loss | Overfilter Ratio |
|---|---|---|---|---|---|---|---|---|
| 1 | 95.66 | 115.3 | 0.0 | inf | 16 | 0.8 | 104.0 | 0.0077 |
| 2 | 95.66 | 115.3 | 0.0 | inf | 16 | 0.8 | 104.0 | 0.0077 |
| 3 | 95.66 | 115.3 | 0.0 | inf | 16 | 0.8 | 104.0 | 0.0077 |
| 4 | 95.66 | 115.3 | 0.0 | inf | 16 | 0.8 | 104.0 | 0.0077 |
| 5 | 95.66 | 115.3 | 0.0 | inf | 16 | 0.8 | 104.0 | 0.0077 |

## PROP_FIRM_STRICT

**Total combinations tested:** 150

**Best score:** 94.79

**Best config:**

```json
{
  "min_meta_confidence_block": 0.55,
  "min_meta_confidence": 0.7,
  "min_meta_confidence_throttle": 0.7,
  "max_atr_percentile_block": 92,
  "max_atr_percentile_throttle": 85,
  "max_spread_usd_block": 0.8,
  "max_regime_flip_prob_block": 0.75,
  "risk_multiplier_in_warn_vol": 0.75
}
```

### Top 5 Configurations

| Rank | Score | Net PnL | Max DD | PF | Blocked | Missed Profit | Avoided Loss | Overfilter Ratio |
|---|---|---|---|---|---|---|---|---|
| 1 | 94.79 | 103.85 | 0.0 | inf | 16 | 0.8 | 104.0 | 0.0077 |
| 2 | 94.79 | 103.85 | 0.0 | inf | 16 | 0.8 | 104.0 | 0.0077 |
| 3 | 94.79 | 103.85 | 0.0 | inf | 16 | 0.8 | 104.0 | 0.0077 |
| 4 | 94.79 | 103.85 | 0.0 | inf | 16 | 0.8 | 104.0 | 0.0077 |
| 5 | 94.79 | 103.85 | 0.0 | inf | 16 | 0.8 | 104.0 | 0.0077 |

## INSTITUTIONAL_CAPITAL_PROTECTION

**Total combinations tested:** 150

**Best score:** 94.79

**Best config:**

```json
{
  "min_meta_confidence_block": 0.55,
  "min_meta_confidence": 0.7,
  "min_meta_confidence_throttle": 0.7,
  "max_atr_percentile_block": 92,
  "max_atr_percentile_throttle": 85,
  "max_spread_usd_block": 0.8,
  "max_regime_flip_prob_block": 0.75,
  "risk_multiplier_in_warn_vol": 0.75
}
```

### Top 5 Configurations

| Rank | Score | Net PnL | Max DD | PF | Blocked | Missed Profit | Avoided Loss | Overfilter Ratio |
|---|---|---|---|---|---|---|---|---|
| 1 | 94.79 | 103.85 | 0.0 | inf | 16 | 0.8 | 104.0 | 0.0077 |
| 2 | 94.79 | 103.85 | 0.0 | inf | 16 | 0.8 | 104.0 | 0.0077 |
| 3 | 94.79 | 103.85 | 0.0 | inf | 16 | 0.8 | 104.0 | 0.0077 |
| 4 | 94.79 | 103.85 | 0.0 | inf | 16 | 0.8 | 104.0 | 0.0077 |
| 5 | 94.79 | 103.85 | 0.0 | inf | 16 | 0.8 | 104.0 | 0.0077 |

