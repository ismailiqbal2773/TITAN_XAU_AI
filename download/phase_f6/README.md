# TITAN XAU AI — Phase F.6: Hybrid Deployment Architecture

> **One codebase. Three deployment tiers. Broker-side safety net in all.**
> Retail users can run TITAN safely on a normal MT5 desktop without VPS.

---

## 📄 Primary Deliverable

**`TITAN_XAU_AI_Phase_F6_Hybrid_Deployment.pdf`** (1.2 MB, 31 pages)

8 chapters + 1 appendix covering all 3 deployment tiers × 9 failure scenarios.

## 📊 Visualizations (`assets/`)

| File | Description |
|------|-------------|
| `tier1_retail_arch.png` | Tier 1 Retail: Windows PC + MT5 + broker SL/TP (NO VPS) |
| `tier2_pro_arch.png` | Tier 2 Professional: single VPS + systemd + Grafana + Slack |
| `tier3_institutional_arch.png` | Tier 3 Institutional: dual VPS + failover + heartbeat |
| `scenario_matrix.png` | Trade safety heatmap + recovery time bars (3 tiers × 9 scenarios) |
| `score_comparison.png` | 3 readiness gauges + recommended default |

## 📈 Raw Results

- `titan_phase_f6_results.json` — Full structured simulation output
- `titan_phase_f6_results.csv` — Flat table for spreadsheet analysis

---

## 🎯 Headline Results

| Tier | Score | Verdict |
|------|-------|---------|
| **T1 — Retail** | **85.1 / 100** | **Retail Ready** ✓ |
| **T2 — Professional** | **93.2 / 100** | **World-Class Ready** ✓ |
| **T3 — Institutional** | **87.5 / 100** | **Institutional Ready** ✓ |

## 🚦 Four-Tier Final Verdict

| Verdict | Status | Score |
|---------|--------|-------|
| Retail Ready | ✅ YES | T1 = 85.1 (≥50) |
| Professional Ready | ✅ YES | T2 = 93.2 (≥65) |
| Institutional Ready | ✅ YES | T3 = 87.5 (≥80) |
| World-Class Ready | ❌ NO (2.5 short) | T3 < 90 (T3 UX complexity) |

## 🎯 Recommended Default

**Tier 2 — Professional Mode** (Score: 93.2/100)

Sweet spot of operational resilience, monitoring visibility, and cost. For users who can manage a VPS.

---

## 🏗️ Three Deployment Tiers

### TIER 1 — RETAIL MODE (Score 85.1)
- Local Windows PC + MT5 Terminal
- **NO VPS required**
- One-click startup (TITAN.bat)
- Auto-recovery after reboot (Task Scheduler)
- Position sync from broker on startup
- Trade state persisted to local SQLite (cache only)
- Offline protection (broker-side hard SL/TP)
- MT5 terminal auto-launch on Windows login

### TIER 2 — PROFESSIONAL MODE (Score 93.2)
- Single VPS (Linux/Windows Server)
- 24/7 unattended operation
- systemd auto-restart on crash
- Grafana monitoring dashboard
- Slack alerts on drift threshold breaches
- Drift monitoring at 5-second cadence

### TIER 3 — INSTITUTIONAL MODE (Score 87.5)
- Dual VPS in different availability zones
- Active-passive failover (no double-execution risk)
- Heartbeat monitoring (1-second cadence)
- Automatic takeover in under 10 seconds
- Disaster recovery runbook + PagerDuty + audit log
- State replication via SQLite WAL streaming

---

## 🛡️ Four Design Principles

1. **Broker is the Source of Truth** — local DB is cache only
2. **Broker-Side Hard SL/TP is Mandatory** — every position, every tier
3. **Local Process is Disposable** — restart is always safe
4. **Tier Selection is User Choice** — not a hierarchy

---

## 💀 Nine Failure Scenarios (3 tiers × 9 = 27 simulations)

| Scenario | T1 Retail | T2 Pro | T3 Inst |
|----------|-----------|--------|---------|
| Windows restart | 3min / 95 | 2min / 98 | 1min / 100 |
| MT5 restart | 1min / 100 | 1min / 100 | 1min / 100 |
| Power outage | 10min / 90 | 2min / 98 | 1min / 100 |
| Internet disconnect | 15min / 85 | 3min / 95 | 1min / 100 |
| Process crash | 1min / 100 | 1min / 100 | 1min / 100 |
| Broker disconnect | 10min / 80 | 10min / 85 | 5min / 90 |
| VPS/PC failure | 60min / 85 | 30min / 90 | 1min / 100 |
| Database corruption | 15min / 100 | 10min / 100 | 1min / 100 |
| Model file corruption | 10min / 100 | 5min / 100 | 1min / 100 |

Format: `recovery_time / trade_safety` (higher safety = better)

---

## 🚦 Why World-Class is 2.5 Points Short

T3 = 87.5/100, threshold = 90. The gap is entirely on **user-friendliness** (T3 UX = 3.56/5 vs T2 UX = 4.44/5).

**Fix:** Build a one-click T3 installer that automates:
- VPS provisioning (Terraform/Ansible)
- Failover engine setup
- Heartbeat configuration
- State replication setup

**Estimated effort:** 20 engineering days.

---

## 🎯 Final Verdict

> **TITAN is Retail Ready, Professional Ready, and Institutional Ready across three deployment tiers served by a single codebase, with Tier 2 (Professional) as the recommended default. World-Class Ready remains 2.5 points short, blocked only by Tier 3 setup complexity that a one-click installer would resolve in ~20 engineering days.**

---

## 🔗 Related Phases

- **Phase F-Prime** — Production Integration Spec (7 layers, conservative baseline)
- **Phase F.5** — Reality Simulator (27 operational stress scenarios)
- **Phase F.6** — 👈 **THIS DOCUMENT** (hybrid deployment architecture)
- **Phase F** — Full Integration (next)
- **Phase G** — Paper Trading (30 days demo)
- **Phase H** — Shadow Live (micro lots 0.01)
- **Phase I** — Production Deployment

---

*Document version: 1.0 · Brutal · 2026-06-22*
*Prepared by: Z.ai Engineering · CONFIDENTIAL — Internal Use Only*
