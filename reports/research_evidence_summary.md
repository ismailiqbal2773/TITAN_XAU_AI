# TITAN XAU AI — Research Evidence Summary

> **Generated:** 2026-06-23
> **Source:** Existing repository JSON reports only (no new research)
> **Git Commit:** `6ed1072`

---

## 1. Walk-Forward Results

### F7 Yearly Baseline (REBUILD = Truth)

| Year | AUC | Win Rate | Profit Factor | Sharpe (daily) | CAGR | Max DD % | Trades |
|------|-----|----------|---------------|-----------------|------|----------|--------|
| 2023 | 0.780 | 72.80% | 4.12 | 2.18 | 1.85 | 3.18% | 2,840 |
| 2024 | 0.770 | 71.50% | 3.87 | 1.96 | 1.42 | 3.62% | 2,980 |
| 2025 | 0.750 | 69.20% | 3.32 | 1.68 | 0.95 | 4.45% | 2,710 |
| 2026 | 0.730 | 67.10% | 2.84 | 1.34 | 0.58 | 5.28% | 2,520 |

**Aggregate (Rebuild):** AUC=0.750, WR=69.27%, PF=3.34, Sharpe=1.66, CAGR=0.98, MaxDD=4.45%, Trades=2,736

**Live (after haircut):** AUC=0.712, WR=66.70%, PF=2.65, Sharpe=1.46, CAGR=0.87, MaxDD=5.01%, Trades=2,462

### Walk-Forward Validation (4 folds, frozen-model)

| Window | Train Years | Test Year | AUC | Win Rate | PF | Sharpe (ann.) | Max DD | Trades |
|--------|-------------|-----------|-----|----------|-----|---------------|--------|--------|
| 1 | 2020-2022 | 2023 | 0.858 | 86.33% | 14.63 | 55.04 | 0.000003% | 3,832 |
| 2 | 2020-2023 | 2024 | 0.835 | 85.03% | 11.74 | 55.05 | 0.000006% | 3,628 |
| 3 | 2020-2024 | 2025 | 0.794 | 78.74% | 7.65 | 48.89 | 0.000010% | 4,106 |
| 4 | 2020-2025 | 2026 | 0.787 | 75.96% | 5.40 | 37.93 | 0.000013% | 2,105 |

> ⚠️ **Note:** WFA Sharpe values are H1-bar annualized (mathematically inflated). Daily Sharpe ≈ 2.33 (frozen) vs 1.66 (rebuild).

- **Number of folds:** 4
- **Best fold:** Window 1 (2023 test) — AUC=0.858, PF=14.63
- **Worst fold:** Window 4 (2026 test) — AUC=0.787, PF=5.40

### Final Gate S3 Walk-Forward (IC-based)

| Train → Test | Train Samples | Test Samples | Accuracy | AUC | IC | Pass? |
|--------------|--------------|-------------|----------|-----|-----|-------|
| 2020-2022 → 2023 | 16,674 | 5,900 | 0.687 | 0.747 | 0.528 | ✓ |
| 2020-2023 → 2024 | 22,574 | 5,880 | 0.712 | 0.775 | 0.559 | ✓ |
| 2020-2024 → 2025 | 28,454 | 5,863 | 0.717 | 0.780 | 0.566 | ✓ |
| 2020-2025 → 2026 | 34,317 | 2,707 | 0.710 | 0.778 | 0.551 | ✓ |

---

## 2. Cross-Broker Validation

| Broker | H1 Bars | H1 Coverage | Spread (pts) | Account Type | Server | Pass 95%? |
|--------|---------|-------------|--------------|--------------|--------|-----------|
| Exness | 38,215 | 119.08% | 73.33 | Real | Exness-MT5Real3 | ✓ |
| IC Markets | 38,244 | 98.93% | 2.23 | Demo | ICMarkets-Demo | ✓ |
| FBS | 36,782 | 95.20% | 25.93 | Demo | FBS-Demo | ✓ |
| FundedNext | 14,460 | 37.80% | 25.53 | Demo | FundedNext-Server 3 | ✗ |

**Total real bars acquired:** 1,202,944 across 4 brokers + Dukascopy

> ⚠️ FundedNext H1 coverage is only 37.8% — below 95% threshold. Cross-broker backtest translation risk accepted.

---

## 3. Calibration Results

| Model | Brier Score | ECE (Cal Error) |
|-------|-------------|-----------------|
| XGBoost (L1) | 0.1677 | 0.0354 |
| Meta-Label (L2) | 0.1867 | 0.0792 |

- XGBoost calibration is good (ECE < 0.05)
- Meta-label calibration is acceptable but degrading (ECE approaching 0.10 kill threshold per F5)
- F9-C projects ECE crosses 0.10 kill threshold by 2026

---

## 4. Alpha Validation Results

### Permutation Test
- **p-value:** 0.0 (15 trials)
- **Verdict:** GENUINE
- Original accuracy: 0.7099 vs permuted mean: 0.5113 (max: 0.5415)

### Confusion Matrix
| | Predicted UP | Predicted DOWN |
|---|---|---|
| **Actual UP** | TP=2,006 | FN=838 |
| **Actual DOWN** | FP=736 | TN=1,925 |

- **Precision:** 0.7316
- **Recall:** 0.7053
- **F1 Score:** 0.7182
- **AUC:** 0.7775
- **Balanced Accuracy:** 0.7144

### Random Label Test
- Accuracy: 0.4955 (expected ~0.50)
- AUC: 0.4973 (expected ~0.50)
- IC: -0.0047 (expected ~0.0)
- ✓ Confirms model is NOT learning noise

### Alpha Decay (frozen-model, filtering sweep)

| Filter % | PF | Win Rate | Sharpe (ann.) | Max DD | Trades |
|----------|-----|----------|----------------|--------|--------|
| 0% | 5.29 | 74.65% | 36.96 | 3.16% | 4,087 |
| 10% | 5.56 | 75.42% | 38.03 | 3.16% | 3,881 |
| 20% | 5.81 | 76.20% | 39.08 | 3.16% | 3,626 |
| 30% | 6.44 | 78.06% | 41.28 | 3.16% | 3,272 |
| 40% | 7.17 | 79.95% | 43.91 | 3.16% | 2,773 |
| 50% | 7.74 | 80.86% | 46.46 | 3.16% | 1,980 |

### Alpha Decay Rate (from F9-A)
- **AUC decay:** -2.18%/year (half-life ~23 years)
- **Sharpe decay:** -12.84%/year (half-life ~3.9 years)
- **Sharpe is the binding constraint** — decays 6× faster than AUC

### Feature Ablation (Final Gate S1)

| Feature Removed | AUC | IC | PF | Impact |
|----------------|-----|-----|-----|--------|
| Baseline (none removed) | 0.778 | 0.553 | 4.42 | — |
| close_pos_in_range | 0.776 | 0.549 | 4.40 | -0.02 AUC |
| upper_wick_ratio | 0.772 | 0.539 | 4.39 | -0.06 AUC |
| lower_wick_ratio | 0.773 | 0.541 | 4.29 | -0.05 AUC |
| **Remove all 3** | **0.670** | **0.347** | **2.31** | **-0.108 AUC, -2.11 PF** |

> Top 3 microstructure features carry 47.74% of PF.

---

## 5. Reality Audit Results

### Frozen-Model Metrics (REJECTED — inflated by H1 annualization)

| Metric | Frozen Value | Note |
|--------|-------------|------|
| Sharpe (annualized) | 36.96 | SUSPICIOUS (>10) |
| Sharpe (daily) | 2.33 | Frozen daily |
| Profit Factor | 5.29 | SUSPICIOUS (>5) |
| Win Rate | 74.65% | — |
| Max Drawdown | 3.16% | — |
| Trades | 4,087 | — |
| Final Equity | $1,572,152 | — |

### Rebuild Metrics (TRUTH per F8)

| Metric | Rebuild | Live (haircut) |
|--------|---------|----------------|
| AUC | 0.750 | 0.712 |
| Win Rate | 69.27% | 66.70% |
| Profit Factor | 3.34 | 2.65 |
| Sharpe (daily) | 1.66 | 1.46 |
| CAGR | 0.98 | 0.87 |
| Max Drawdown | 4.45% | 5.01% |
| Trades/year | 2,736 | 2,462 |

### Reality Gap

| Metric | Rebuild | Live | Gap |
|--------|---------|------|-----|
| Sharpe | 1.66 | 1.46 | -0.20 (12.0%) |
| PF | 3.34 | 2.65 | -0.69 (20.7%) |
| Win Rate | 69.27% | 66.70% | -2.57pp |
| Max DD | 4.45% | 5.01% | +0.56pp |

### Cost Assumptions

| Component | $/lot |
|-----------|-------|
| Spread | $13.20 |
| Commission | $7.00 |
| Slippage | $10.00 |
| Swap | $0.00 |
| **Total** | **$30.20** |

> Previous audit underestimated costs by 4.18× ($7.23/lot → $30.20/lot)

### F8 Reality Gap Closure

| Metric | Value |
|--------|-------|
| Current Live Sharpe | 1.46 |
| Optimized Sharpe (all levers) | 1.58 |
| Target (shadow-live gate) | 1.80 |
| Remaining gap | 0.22 (12.5%) |
| Feasible without retraining? | **NO** |
| Best single lever | Execution co-location (+0.15 Sharpe) |
| Recommendation | Choice C: Retrain Required |

### F7 Bootstrap (10,000 samples)

| Metric | p5 | p50 | p95 | Mean | Std |
|--------|-----|-----|-----|------|-----|
| Sharpe | 0.85 | 1.45 | 2.08 | 1.46 | 0.37 |
| PF | 2.47 | 2.65 | 2.84 | 2.65 | 0.11 |
| Win Rate | 0.6515 | 0.6673 | 0.6824 | 0.6671 | 0.0094 |

### F7 Production Expectation

| Scenario | PF | Sharpe | Win Rate | Max DD | CAGR |
|----------|-----|--------|----------|--------|------|
| Conservative (p5) | 2.47 | 0.85 | 65.15% | 7.01% | 0.26 |
| Expected (p50) | 2.65 | 1.45 | 66.73% | 5.01% | 0.87 |
| Optimistic (p95) | 2.84 | 2.08 | 68.24% | 3.76% | 1.75 |

---

## 6. Model Comparison

| Model | Features | Test AUC | Test Acc | IC | Notes |
|-------|----------|----------|----------|-----|-------|
| LSTM Clean | 22 (micro+price) | 0.7808 | 0.7095 | 0.5582 | Best AUC |
| XGBoost Micro | 9 (microstructure) | 0.7754 | 0.7141 | 0.5455 | Production L1 |
| LogReg Price | 13 (price) | 0.7702 | 0.7095 | 0.5312 | Reference |
| Transformer | all | 0.9790 | — | — | ⚠️ Likely overfitted (val AUC 0.993) |
| Meta-Label v2 | 22 | — | — | — | Logistic Regression, Brier=0.187 |
| LightGBM | — | — | — | — | Trained via HPO, not in inference chain |

### Prediction Correlations

| | XGB(micro) | LR(price) | LSTM(clean) | TF(conf) |
|---|---|---|---|---|
| XGB(micro) | 1.00 | 0.91 | 0.96 | -0.006 |
| LR(price) | 0.91 | 1.00 | 0.96 | 0.00005 |
| LSTM(clean) | 0.96 | 0.96 | 1.00 | -0.004 |
| TF(conf) | -0.006 | 0.00005 | -0.004 | 1.00 |

> ⚠️ XGB↔LSTM correlation = 0.96, XGB↔LR = 0.91 — NO error diversification. Transformer is uncorrelated but likely overfitted.

### Model Diversity Verdict
- Max prediction correlation: 0.953
- Max error correlation: 0.984
- Verdict: **ENSEMBLE_NEEDS_REDESIGN**

---

## 7. Stress Test + Monte Carlo

### F5 Reality Simulator (27 scenarios)

| Metric | Baseline |
|--------|----------|
| AUC | 0.76 |
| Profit Factor | 3.87 |
| Win Rate | 71.20% |
| Daily Sharpe | 1.96 |
| Max DD | 3.62% |
| Trades/day | 12 |
| Avg Spread | 0.18 pips |
| Avg Slippage | 0.18 pips |
| Latency p95 | 187ms |

**Kill thresholds:** PF floor=1.5, WR floor=60%, ECE limit=0.10, PSI kill=0.25, latency p99 kill=1000ms

- Total scenarios: 27
- Kill-switch activated: 16 scenarios (59.3%)
- Worst case: Model file corruption (PF=0.00, Sharpe=0.00)

### Monte Carlo (10,000 simulations, frozen-model)

| Metric | Mean | Median | p5 | p95 | p99 |
|--------|------|--------|-----|-----|-----|
| Profit Factor | 5.31 | 5.30 | 4.80 | 5.84 | — |
| Sharpe (ann.) | 37.04 | 37.06 | 34.64 | 39.37 | — |
| Max DD % | 2.47% | 2.35% | — | 3.44% | 4.03% |

- Survival rate (PF > 1): 100.0%
- Verdict: PASS

> ⚠️ Monte Carlo uses frozen-model annualized metrics. Rebuild-consistent Sharpe is 1.66, not 37.

---

## 8. Final Trading Metrics (Reconciled)

| Metric | Frozen (REJECTED) | Rebuild (TRUTH) | Live (Haircut) | Source |
|--------|-------------------|-----------------|----------------|--------|
| Profit Factor | 5.29 | 3.34 | 2.65 | F7 Reality Audit |
| Sharpe (daily) | 2.33 | 1.66 | 1.46 | F7 yearly baseline |
| Sortino | -4.33 | N/A | N/A | Competition Validation (old, pre-rebuild) |
| Calmar | N/A | N/A | N/A | Not computed for rebuild |
| Max Drawdown | 3.16% | 4.45% | 5.01% | F7 |
| Win Rate | 74.65% | 69.27% | 66.70% | F7 |
| Expectancy | $244/lot | N/A | N/A | Execution Safety Layer (frozen) |
| CAGR | N/A | 0.98 | 0.87 | F7 |
| Return | 1572% (frozen) | 98% | 87% | F7 |

### Bootstrap Confidence Intervals (Live)

| Metric | p5 (conservative) | p50 (expected) | p95 (optimistic) |
|--------|-------------------|----------------|-------------------|
| Sharpe | 0.85 | 1.45 | 2.08 |
| PF | 2.47 | 2.65 | 2.84 |
| Win Rate | 65.15% | 66.73% | 68.24% |
| Max DD | 7.01% | 5.01% | 3.76% |
| CAGR | 0.26 | 0.87 | 1.75 |

---

## 9. Missing Evidence

| Metric | Status | Notes |
|--------|--------|-------|
| Sortino ratio | ⚠️ Found but STALE | Only in Competition Validation (pre-rebuild, value=-4.33, likely incorrect) |
| Calmar ratio | ✗ Missing | Referenced in Pre-HPO objective audit but no computed value |
| Expectancy (rebuild) | ✗ Missing | Only available for frozen-model ($244/lot). Rebuild expectancy not computed. |
| OOS score per model | ✗ Partial | Only validation AUC available (no separate OOS test set scores per model) |
| Per-broker performance | ✗ Missing | Only coverage + spread data per broker. No per-broker PnL/Sharpe/WR. |
| Calibration slope | ✗ Missing | Only Brier + ECE available. No reliability slope (ideal=1.0). |
| Sortino (rebuild) | ✗ Missing | Not computed for rebuild metrics |
| Calmar (rebuild) | ✗ Missing | Not computed for rebuild metrics |

---

## Summary

TITAN's research evidence is **extensive but has known gaps**:

1. **Walk-forward validation** is strong: 4 folds, all pass, AUC 0.75-0.86, IC 0.53-0.57
2. **Alpha is genuine**: permutation test p=0.0, random label test confirms no noise learning
3. **Reality gap is quantified**: Sharpe 1.66 (rebuild) → 1.46 (live), gap 12%
4. **Shadow-live gate NOT met**: 1.46 < 1.80 required, gap 0.22, requires retrain
5. **Model diversity is poor**: XGB↔LSTM correlation 0.96, ensemble needs redesign
6. **Safety systems are comprehensive**: 27 stress scenarios, 16 kill-switch activations, 100% MC survival
7. **Missing metrics**: Sortino, Calmar, per-broker performance, calibration slope, rebuild expectancy

**Key recommendation from existing reports:** Deploy demo NOW with current config (dry_run), retrain L1 XGBoost with 2025-2026 data in parallel, retry shadow-live gate after retrain + 30-day demo.

---

*Report generated from existing repository JSON evidence only. No new research, retraining, or computation performed.*
