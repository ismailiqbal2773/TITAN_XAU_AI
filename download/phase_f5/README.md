# TITAN XAU AI — Phase F.5: Reality Simulator

> **Institutional-grade pre-live validation focused on operational robustness.**
> Assume the system trades real money tomorrow. Be brutally honest.

---

## 📄 Primary Deliverable

**`TITAN_XAU_AI_Phase_F5_Reality_Simulator.pdf`** (1.1 MB, 37 pages)

9 chapters + 1 appendix covering all 27 stress scenarios across 6 categories.

## 📊 Visualizations (`assets/`)

| File | Description |
|------|-------------|
| `failure_matrix.png` | 27 scenarios × 6 metrics heatmap (red = KILL or <60% baseline) |
| `recovery_matrix.png` | Recovery time per scenario, sorted descending |
| `score_gauges.png` | Production + Real Capital readiness gauges |
| `category_radar.png` | Per-category resilience radar (4 axes) |

## 📈 Raw Results

- `titan_phase_f5_results.json` — Full structured simulation output
- `titan_phase_f5_results.csv` — Flat table for spreadsheet analysis

---

## 🎯 Headline Results

| Score | Value | Verdict |
|-------|-------|---------|
| **Production Readiness** | **54.0 / 100** | Demo Ready |
| **Real Capital Readiness** | **24.0 / 100** | **Not Ready** |

**27 scenarios · 16 killed (59% kill rate) · Survival 40.7%**

---

## 🚦 The Five-Tier Verdict Ladder

| Tier | Score | Verdict | TITAN Status |
|------|-------|---------|--------------|
| 1 | 0–44 | Not Ready | ← Capital Score 24.0 |
| 2 | 45–59 | Demo Ready | ← Production Score 54.0 |
| 3 | 60–74 | Shadow Live Ready | Not achieved |
| 4 | 75–89 | Small Capital Ready | Not achieved |
| 5 | 90–100 | Institutional Ready | Not achieved |

---

## 🏗️ Six Stress Categories

| # | Category | Scenarios | Killed | Survival |
|---|----------|-----------|--------|----------|
| 1 | Latency Stress | 6 (50/100/250/500/1000/1500ms) | 4 | 33% |
| 2 | Broker Failure | 4 (1/5/10/20% rejection) | 0 | 100% |
| 3 | Data Integrity | 4 (missing/delayed/duplicate/out-of-order) | 3 | 25% |
| 4 | Market Events | 4 (NFP/CPI/FOMC/flash crash) | 4 | 0% |
| 5 | Infrastructure | 5 (VPS restart/disconnect/crash/db lock/corruption) | 3 | 40% |
| 6 | Trade Execution | 4 (partial/slippage/spread/sync) | 3 | 25% |
| **Total** | | **27** | **16** | **40.7%** |

---

## 💀 The 16 Kill Scenarios

1. **+250ms latency** → PF<1.5 (PF=1.22)
2. **+500ms latency** → PF<1.5 (PF=0.73)
3. **+1000ms latency** → PF<1.5, WR<60%, latency>1000ms (PF=0.40, WR=57%)
4. **+1500ms latency** → PF<1.5, WR<60%, latency>1000ms (PF=0.28, WR=49.8%)
5. **Delayed candles** → PF<1.5 (equivalent to +500ms latency)
6. **Duplicate candles** → PSI>0.25, ECE>0.10
7. **Out-of-order timestamps** → PSI>0.25, ECE>0.10
8. **NFP** → PF<1.5 (PF=1.61, DD=9.05%)
9. **CPI** → PF<1.5 (PF=1.94, DD=8.14%)
10. **FOMC** → PF<1.5 (PF=0.81, DD=12.67%)
11. **Flash crash** → PF<1.5 (PF=0.60, DD=19.91%)
12. **Internet disconnect** → latency>1000ms (p99=2312ms)
13. **Process crash** → PF<1.5, WR<60% (orphaned positions)
14. **Model file corruption** → Hash check fails; process never starts
15. **Slippage spikes** → PF<1.5 (PF=0.94)
16. **Spread explosions** → PF<1.5 (PF=0.53)
17. **Position sync failures** → Operational kill (reconciliation broken)

---

## 🛠️ Hardening Roadmap (12 measures)

| ID | Priority | Measure | Kills Prevented | Effort |
|----|----------|---------|-----------------|--------|
| H1 | **P0** | News-event pre-halt (calendar + 30min halt) | NFP, CPI, FOMC (3) | 3 days |
| H2 | **P0** | Co-located broker connection | 4 latency kills | 7 days |
| H3 | **P0** | Data feed validation (duplicate + out-of-order) | 2 data integrity kills | 2 days |
| H4 | **P0** | Process supervisor + state recovery | 1-2 infrastructure kills | 5 days |
| H5 | **P0** | Broker-side hard SL on every position | Infrastructure severity | 3 days |
| H6 | P1 | Reconciliation cadence 30s → 5s | Sync failure severity | 1 day |
| H7 | P1 | L1 dead-zone tightening | Latency margin | 1 day |
| H8 | P1 | Dual-VPS with health-check failover | 2 infrastructure kills | 10 days |
| H9 | P1 | On-call rotation + incident runbook | All recovery times | 14 days |
| H10 | P1 | Grafana dashboard deployment | Earlier detection | 5 days |
| H11 | P2 | Model risk officer sign-off | Operational readiness | 7 days |
| H12 | P2 | 30d demo + 30d shadow live | Validates all hardening | 60 days |

**Total time to Capital Deployment Ready: 90–120 days.**

---

## 📈 Expected Score Trajectory

| Stage | Production Score | Capital Score | Verdict |
|-------|------------------|---------------|---------|
| Now (Phase F.5 complete) | 54.0 | 24.0 | Demo Ready / Not Ready |
| After P0 (20 days) | ~75 | ~55 | Small Capital / Demo |
| After P1 (50 days) | ~85 | ~70 | Small Capital / Shadow Live |
| After P2 (110 days) | ~90 | ~85 | Institutional / Small Capital |
| After 90d live Kelly 10% | ~92 | ~92 | Institutional / Institutional |

---

## 🎯 Final Verdict

> **TITAN XAU AI, as specified in Phase F-Prime and stress-tested in Phase F.5, is cleared for demo trading only (Production 54.0) and is NOT cleared for real money (Capital 24.0). The path to Capital Deployment Ready requires 90-120 days of focused engineering hardening across 12 specific measures, after which the system is projected to reach Institutional Ready (90+).**

---

## 🔗 Related Phases

- **Phase F-Prime** — Production Integration Spec (7 layers, conservative baseline)
- **Phase F.5** — 👈 **THIS DOCUMENT** (reality simulator, 27 stress scenarios)
- **Phase F** — Full Integration (next, post-P0 hardening)
- **Phase G** — Paper Trading (30 days demo)
- **Phase H** — Shadow Live (micro lots 0.01)
- **Phase I** — Production Deployment

---

*Document version: 1.0 · Brutal · 2026-06-22*
*Prepared by: Z.ai Engineering · CONFIDENTIAL — Internal Use Only*
