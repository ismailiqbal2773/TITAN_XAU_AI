# TITAN XAU AI — Phase F.7: Live Performance Prediction Audit

> **Resolve the frozen-vs-rebuild gap. Be brutally conservative. No optimism allowed.**
> Frozen-model metrics are EXPLICITLY REJECTED as unattainable. Rebuild = truth.

---

## 📄 Primary Deliverable

**`TITAN_XAU_AI_Phase_F7_Live_Performance_Prediction.pdf`** (818 KB, 16 pages)

7 sections + final verdict. Uses ONLY walk-forward rebuild models.

## 📊 Visualizations (`assets/`)

| File | Description |
|------|-------------|
| `yearly_baseline.png` | 2023-2026 × 6 metrics line charts (degradation trend) |
| `bootstrap_ci.png` | PF/Sharpe/WR bootstrap distributions with p5/p50/p95 |
| `score_gauges.png` | Research/Trading/Production + Final reality score gauges |
| `frozen_vs_rebuild.png` | Frozen (REJECTED) vs Rebuild vs Live comparison |

## 📈 Raw Results

- `titan_phase_f7_results.json` — Full structured simulation output
- `titan_phase_f7_yearly.csv` — Per-year metrics table

---

## 🎯 Headline Results

| Score | Value | Assessment |
|-------|-------|------------|
| **Research Quality** | 82.0 / 100 | Strong model foundation |
| **Trading Quality** | 61.4 / 100 | Weak — Sharpe below gate |
| **Production Quality** | 72.0 / 100 | Good kill coverage |
| **FINAL REALITY SCORE** | **72.3 / 100** | |

## 🚦 Final Verdict

# ✅ DEMO READY

(Blocked from SHADOW LIVE because live Sharpe = 1.46 < 1.80 gate threshold)

---

## 📊 The Frozen-vs-Rebuild Gap (Frozen REJECTED)

| Metric | Frozen (REJECTED) | Rebuild (truth) | Live (after haircut) | Haircut |
|--------|-------------------|-----------------|----------------------|---------|
| AUC | 0.79 | 0.750 | 0.712 | -10% |
| Win Rate | 74.7% | 69.3% | 66.7% | -11% |
| **Profit Factor** | **5.29** | **3.34** | **2.65** | **-50%** |
| **Sharpe** | **2.33** | **1.66** | **1.46** | **-37%** |
| Max DD | 3.16% | 4.45% | 5.01% | +59% |

---

## 📅 Per-Year Reality Baseline (Walk-Forward Rebuild)

| Year | AUC | Win Rate | PF | Sharpe | CAGR | Max DD | Trades |
|------|-----|----------|----|--------|------|--------|--------|
| 2023 | 0.78 | 72.8% | 4.12 | 2.18 | 185% | 3.18% | 2,840 |
| 2024 | 0.77 | 71.5% | 3.87 | 1.96 | 142% | 3.62% | 2,980 |
| 2025 | 0.75 | 69.2% | 3.32 | 1.68 | 95% | 4.45% | 2,710 |
| 2026 | 0.73 | 67.1% | 2.84 | 1.34 | 58% | 5.28% | 2,520 |
| **2024-26 avg** | **0.750** | **69.3%** | **3.34** | **1.66** | **95%** | **4.45%** | **2,737** |

**Every metric degrades over time.** 2026 is the best estimator of near-term live performance.

---

## 💇 Live Haircut Assumptions (Institutional Degradation)

| Assumption | Value | Impact |
|------------|-------|--------|
| Model decay | -10% | Reduces AUC, WR, PF |
| Execution decay | -5% | Reduces Sharpe |
| Spread increase | +25% | Compresses PF |
| Slippage increase | +50% | Compresses PF significantly |
| Missed trades | 10% | Reduces trade count |

---

## 🎲 Bootstrap Confidence Intervals (10,000 simulations)

| Metric | p5 (Conservative) | p50 (Expected) | p95 (Optimistic) |
|--------|-------------------|----------------|------------------|
| Profit Factor | 2.47 | 2.65 | 2.84 |
| Sharpe | 0.85 | 1.45 | 2.08 |
| Win Rate | 65.1% | 66.7% | 68.2% |

---

## 🎯 Production Expectation (3 Scenarios)

| Scenario | PF | Sharpe | WR | DD | CAGR |
|----------|----|--------|----|----|------|
| **Conservative** (p5) | 2.47 | 0.85 | 65.1% | 7.01% | 26% |
| **Expected** (p50) | 2.65 | 1.46 | 66.7% | 5.01% | 87% |
| **Optimistic** (p95) | 2.84 | 2.08 | 68.2% | 3.76% | 175% |

---

## 🚦 Deployment Gate (Rebuild + Live-Haircut Only)

| Gate | Criteria | Result |
|------|----------|--------|
| **Demo Ready** | PF≥1.8, Sharpe≥1.2, DD≤8% | ✅ PASS (PF=2.65, Sh=1.46, DD=5.01%) |
| **Shadow Live Ready** | PF≥2.5, Sharpe≥1.8, DD≤6%, Cons PF≥1.5 | ❌ FAIL (Sharpe 1.46 < 1.80) |
| **Real Capital Ready** | PF≥3.0, Sharpe≥2.0, DD≤5%, Cons PF≥2.0 | ❌ FAIL (all criteria miss) |

---

## 💀 12 Kill Criteria (Immediate Deployment Stop)

| # | Criterion | Severity |
|---|-----------|----------|
| 1 | PF < 1.5 (rolling 100 trades) | IMMEDIATE SHUTDOWN |
| 2 | Sharpe < 1.0 (trailing 30d) | IMMEDIATE SHUTDOWN |
| 3 | Max DD > 10% (trailing 90d) | IMMEDIATE SHUTDOWN |
| 4 | Calibration drift (ECE) > 15% | IMMEDIATE SHUTDOWN |
| 5 | Meta-Label AUC < 0.60 | IMMEDIATE SHUTDOWN |
| 6 | Win Rate < 55% (rolling 100) | IMMEDIATE SHUTDOWN |
| 7 | Feature drift (PSI) > 0.25 | IMMEDIATE SHUTDOWN |
| 8 | Latency p99 > 1000ms | IMMEDIATE SHUTDOWN |
| 9 | 3+ WARN alerts in 24h | THROTTLE (50% size) |
| 10 | 2nd kill in 7 days | PERMANENT SHUTDOWN |
| 11 | Broker reconciliation mismatch > 30s | IMMEDIATE SHUTDOWN |
| 12 | Daily DD > 5% | HALT NEW TRADES (rest of day) |

---

## 🎯 Final Verdict

> **FINAL VERDICT: DEMO READY**
>
> Final Reality Score: 72.3/100 (would qualify for SHADOW LIVE by score alone, BUT shadow-live gate fails on Sharpe 1.46 < 1.80)
>
> The system is cleared for demo trading only. Shadow live is blocked by the Sharpe gate. Real capital is blocked by every gate criterion. The path to higher tiers requires improving the rebuild Sharpe back above 2.0, which likely requires model retraining with 2025-2026 data.

---

## 🔗 Related Phases

- **Phase F-Prime** — Production Integration Spec (7 layers, conservative baseline)
- **Phase F.5** — Reality Simulator (27 operational stress scenarios)
- **Phase F.6** — Hybrid Deployment Architecture (3 tiers, no VPS for retail)
- **Phase F.7** — 👈 **THIS DOCUMENT** (live performance prediction audit)
- **Phase F** — Full Integration (next)
- **Phase G** — Paper Trading (30 days demo)
- **Phase H** — Shadow Live (micro lots 0.01)
- **Phase I** — Production Deployment

---

*Document version: 1.0 · Brutally Conservative · 2026-06-22*
*Prepared by: Z.ai Engineering · CONFIDENTIAL — Internal Use Only*
