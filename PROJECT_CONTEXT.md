# TITAN XAU AI — MASTER PROJECT CONTEXT

> **File Purpose:** Yeh file AI ke liye ek "Map" hai. Naya session start hone par
> AI ko sirf yeh file padhni hai aur poora project context samajh aa jayega.
>
> **Last Updated:** June 20, 2026 — 14:25 UTC
> **Project Phase:** Real Data Acquisition Audit (Phase 2 of Competition Validation)
> **Status:** 783,085 REAL M1 bars downloaded. 31 months covered. Missing months being downloaded.

---

## 1. PROJECT OVERVIEW

### Kya Hai?
**TITAN XAU AI** ek institutional-grade AI trading system hai jo XAUUSD (Gold/USD)
par trade karta hai. Yeh 3 AI models (XGBoost + LSTM + Transformer) ka ensemble
use karta hai, ek CEO supervisor module se governed, with full risk management,
prop firm compliance, licensing, aur validation frameworks.

### End Goal?
TITAN ko **Development Status → Competition Validation Status** tak le jana.
Matlab:
- 5+ years REAL historical data par train karna (NO synthetic data)
- Institutional validation thresholds pass karna:
  - Sharpe > 2.0, PF > 2.0, MDD < 5%, WR > 55%
  - WFE > 0.85, MC Survival > 95%, RoR < 1%, Validator > 90
- 30-day forward demo trading ke liye ready karna

### Current Phase?
**Real Data Acquisition Audit** — Previous competition validation REJECT hua
kyunki usme synthetic/calibrated data use hua tha. Ab sirf REAL Dukascopy tick
data download kar rahe hain.

**Latest Progress (June 20, 2026):**
- **783,085 REAL M1 bars** downloaded (ZERO synthetic)
- **584 trading days** covered
- **31 months** across 5 calendar years (2020-2024)
- 2023 aur 2024 COMPLETE (24 months)
- 2020-2022 partial (missing months being downloaded)

---

## 2. TECH STACK

### Language & Runtime
| Component | Version | Notes |
|-----------|---------|-------|
| Python | 3.12.13 | CPython, Linux x86_64 |
| asyncio | stdlib | Concurrent operations |
| Type hints | PEP 604 | `str | None` style throughout |

### Core Libraries (All Installed ✅)
| Library | Version | Purpose |
|---------|---------|---------|
| pandas | 2.x | Data manipulation, OHLCV bars |
| numpy | 1.26+ | Numerical computation |
| requests | 2.32.5 | HTTP (Dukascopy download) |
| pyarrow | 24.0.0 | Parquet read/write |
| lzma | stdlib | .bi5 tick data decompression |
| reportlab | — | PDF report generation |
| python-docx | — | DOCX report generation |
| optuna | 4.9.0 | Hyperparameter optimization (B2 fix) |
| pytest | 8.x | Test framework |

### Missing Libraries (with fallbacks)
| Library | Purpose | Fallback |
|---------|---------|----------|
| xgboost | Gradient-boosted trees | sklearn GradientBoostingClassifier |
| torch | LSTM + Transformer | sklearn LogisticRegression |
| structlog | Structured logging | (causes 2 test collection errors) |
| MetaTrader5 | Broker connection | mt5_stub.py (Linux) |

---

## 3. FOLDER STRUCTURE

```
/home/z/my-project/
│
├── PROJECT_CONTEXT.md          ← YEH FILE (AI ke liye master map)
├── project_memory.md           ← Detailed project memory (439 lines)
├── worklog.md                  ← Shared work log (sab sessions ka record)
├── .cursorrules                ← Cursor IDE rules (optional)
│
├── titan/                      ← MAIN CODEBASE (12,169 lines production)
│   ├── main.py                 (472) TitanSystem orchestrator, 14-component DI
│   ├── conftest.py             MT5 mock injection for Linux
│   ├── mt5_stub.py             MT5 stub for non-Windows testing
│   ├── pytest.ini
│   ├── requirements.txt
│   │
│   ├── ai/                     AI MODELS (6 files, ~1,264 lines)
│   │   ├── base_model.py       (149) IModel ABC, Prediction, ModelMetadata
│   │   ├── xgboost_model.py    (214) XGBoost wrapper, ONNX export
│   │   ├── lstm_model.py       (230) PyTorch LSTM (2 layers, 128 hidden)
│   │   ├── transformer_model.py(254) Multi-head attention (8 heads, 6 layers)
│   │   ├── ensemble_voter.py   (410) Weighted voting + HPO (B2 fix)
│   │   └── model_registry.py   (221) SHA-256, champion/challenger
│   │
│   ├── backtest/engine.py      (358) TickReplayExecutor, CostEngine
│   ├── broker/engine.py        (316) 6 brokers, 9 properties
│   ├── ceo/supervisor.py       (412) 8 detectors, 5 actions
│   │
│   ├── compliance/             PROP FIRM COMPLIANCE (4 files, 1,247 lines)
│   │   ├── profiles.py         (311) 5 firms: FTMO, FundedNext, E8, The5ers, FundingPips
│   │   ├── rule_engine.py      (528) 14 compliance rules
│   │   ├── engine.py           (232) ComplianceEngine wrapper
│   │   └── audit.py            (153) SQLite audit log
│   │
│   ├── config/titan.yaml       System config
│   │
│   ├── data/sources/           REAL data by source (NO synthetic)
│   │   └── dukascopy/          Dukascopy REAL tick data
│   │       ├── daily/          Per-day parquet (584 files, 783,085 bars)
│   │       └── XAUUSD_M1_YYYY-MM.parquet  Monthly merged files
│   │
│   ├── database/layer.py       (413) SQLite (7 tables), Redis cache
│   ├── execution/engine.py     (410) Async dispatch, idempotency
│   │
│   ├── licensing/              LICENSING (5 files, 1,481 lines)
│   │   ├── fingerprint.py      (235) 6-component hardware fingerprint
│   │   ├── jwt_license.py      (264) HS256 JWT, 3 tiers (M/Q/Y)
│   │   ├── store.py            (309) SQLite license store, anti-tamper
│   │   ├── activation.py       (360) Online + offline activation
│   │   └── guard.py            (288) Runtime enforcement, heartbeat
│   │
│   ├── market_data/engine.py   (314) 10 quality gates
│   ├── monte_carlo/engine.py   (145) Monte Carlo simulation
│   ├── observability/metrics.py(164) 25+ Prometheus metrics
│   ├── regime/engine.py        (512) 3-model vote (HMM+Logit+Heuristic)
│   ├── risk/engine.py          (433) 12 controls, kill-switch
│   │
│   ├── strategies/             TRADING STRATEGIES (3 files, 851 lines)
│   │   ├── trend_engine.py     (316) 5 patterns, R-multiple
│   │   ├── range_engine.py     (270) BB+RSI+ATR+Hurst
│   │   └── volatility_engine.py(265) ATR breakout
│   │
│   ├── stress_test/engine.py   (219) 6 scenarios
│   │
│   ├── tests/                  TEST SUITE (17 files, 4,464 lines, 364 tests)
│   │   ├── test_training.py    (76 tests — B1-B5 fixes)
│   │   └── ...                 16 other test files
│   │
│   ├── training/               TRAINING PIPELINE (5 files, 1,608 lines)
│   │   ├── data_acquisition.py (363) 4-source pipeline
│   │   ├── historical_ingestion.py (304) Multi-year loader
│   │   ├── feature_engine.py   (535) 61 features + StandardScaler + RobustScaler + FeatureSelector
│   │   ├── dataset_validator.py(529) 12 checks + PurgedKFold + time_series_split
│   │   └── quality_scorer.py   (232) 5-dimensional 0-100 scoring
│   │
│   ├── validator/engine.py     (153) 8 suites, 144 checks
│   ├── walk_forward/engine.py  (173) Anchored+rolling, purge+embargo (B1/B4 FIXED)
│   └── weighting/engine.py     (317) 4 algorithms + Meta-Bandit
│
├── scripts/                    GENERATION SCRIPTS
│   ├── real_data/              Real data download scripts
│   │   ├── dukascopy_v2.py     Production Dukascopy downloader
│   │   ├── fast_download.py    Fast parallel downloader (RESUME capable)
│   │   └── download_incremental.py
│   ├── full_pipeline.py        Full training+validation pipeline
│   ├── competition_report.py   Competition validation PDF generator
│   └── ...                     Other report generators
│
└── download/                   DELIVERABLES (54 files)
    ├── TITAN_*.pdf             26 PDF reports (Goldman Sachs style)
    ├── TITAN_*.docx            22 DOCX reports
    ├── *.json                  3 JSON artifacts
    └── TITAN_*.zip             3 ZIP archives
```

---

## 4. CURRENT STATUS (LATEST — June 20, 2026 14:25 UTC)

### ✅ COMPLETED

**22 Production Modules (12,169 lines):**
- M01-M08: Broker, Market Data, Execution, Risk, Regime, 3 Strategies
- M09-M14: AI Stack (XGBoost, LSTM, Transformer, Ensemble, Registry)
- M15-M16: CEO Supervisor, Weighting Engine
- M17-M21: Validator, Backtest, WFA, Monte Carlo, Stress Test
- M22-M25: Database, API, Observability, Main Orchestrator

**Commercial Layer (2 modules, 2,728 lines):**
- M26: Licensing (hardware-locked JWT, online+offline, 3 tiers)
- M27: Compliance (5 prop firms, 14 rules)

**Training Pipeline (5 files, 1,608 lines):**
- Data acquisition, feature engine (61 features + scalers + selector)
- Dataset validator (12 checks + PurgedKFold)
- Quality scorer (5-dimensional)

**B1-B5 Blocker Fixes (ALL VERIFIED):**
- B1: Anchored WFA true expanding window ✅
- B2: Optuna HPO for XGBoost/LSTM/Transformer ✅
- B3: StandardScaler + RobustScaler (train-only fit) ✅
- B4: Purge/embargo + time_series_split + PurgedKFold ✅
- B5: FeatureSelector (drops |r|>0.95 + zero-variance) ✅

**Test Suite:** 364 tests, 0 regressions, ~10s runtime

**Real Data Downloaded:**
- **783,085 REAL M1 bars** (ZERO synthetic)
- **584 trading days**
- **31 months** across 5 calendar years

**Deliverables:** 26 PDFs, 22 DOCXs, 3 JSONs, 3 ZIPs

### 🔄 IN PROGRESS — Real Data Download

**Months WITH data (31 months):**
- 2020-03 (11 days — COVID crash) ✅
- 2022-01 to 2022-06 (partial — Ukraine war + Fed tightening) ✅
- 2023-01 to 2023-12 (COMPLETE — 12 months) ✅
- 2024-01 to 2024-12 (COMPLETE — 12 months) ✅

**Months MISSING (still need to download):**
- 2020: Jan, Feb, Apr, May, Jun, Jul, Aug, Sep, Oct, Nov, Dec (11 months)
- 2021: Jan-Dec (ENTIRE YEAR — 12 months)
- 2022: Jul, Aug, Sep, Oct, Nov, Dec (6 months)

### ⏳ NEXT STEPS (Exact tasks in priority order)

**STEP 1: Download missing months from Dukascopy**
```bash
cd /home/z/my-project
# 2-week batches to avoid timeout (each batch ~3-5 min)
timeout 300 python scripts/real_data/fast_download.py 2020-04-01 2020-04-15
timeout 300 python scripts/real_data/fast_download.py 2020-04-16 2020-04-30
# ... continue for all missing months
# Resume capability: already-downloaded days are skipped
```

**STEP 2: Generate audit reports (after all data downloaded)**
- Coverage Report
- Missing Data Report
- Duplicate Report
- Broker Difference Report
- Spread Analysis
- Commission Analysis
- Slippage Calibration
- Market Regime Analysis

**STEP 3: Verify regime coverage in downloaded data**
- COVID 2020 (Mar-Apr 2020)
- Ukraine War 2022 (Feb-Mar 2022)
- Banking Crisis 2023 (Mar 2023 — SVB, Credit Suisse)
- Fed Tightening (2022-2023)
- High Inflation, Extreme Vol, Long Trends, Long Ranges

**STEP 4: Run audits on real data**
- Data Quality Audit (DataQualityScorer)
- Dataset Validator (DatasetValidator — 12 checks)
- Leakage Audit (V11 + lag/target shift)
- Feature Audit (FeatureEngine — 61 features)

**STEP 5: Compute final scores**
- Bars per source, Ticks per source, Coverage %, Missing %
- Quality Score (0-100), Data Quality Grade (A+ to F)

**STEP 6: Output verdict**
- REAL DATA VERIFIED (if Quality ≥90, Coverage ≥95%, Real ≥95%, Synthetic =0%)
- DATA REJECTED (otherwise)

**STEP 7: After data verified — re-run competition validation**
- Phase 3: Train XGBoost + LSTM + Transformer on REAL data
- Phase 4: Backtest + WFA + MC + Stress + Validator with real costs
- Phase 5: Deployment package + 30-day forward test plan
- Output: PASS or FAIL

---

## 5. KEY RULES (AI KO HAMESHA YAAD RAKHNA)

### 🚫 STRICT PROHIBITIONS
1. **NO synthetic data** — zero tolerance, ever
2. **NO random walk expansion** — no calibrating small datasets
3. **NO new architecture** — use existing codebase only
4. **NO new modules** — extend existing files only
5. **NO assumptions** — measure everything, don't guess
6. **NO synthetic success metrics** — only real measured results

### ✅ MANDATORY RULES
1. **CPU-only, fully offline** — no paid APIs, no cloud, no external LLM
2. **All files under `/home/z/my-project/`**
3. **Scripts saved to `scripts/` before execution**
4. **Deliverables to `download/`**
5. **Single worklog** — `worklog.md` (append-only)
6. **Match user's language** (English for English, Hindi for Hindi)
7. **Update project_memory.md after major tasks**

### 🧠 ARCHITECTURE RULES
1. RL NOT in CEO layer (Bayesian + MAB + statistical detectors only)
2. RL only in M12 Trade Manager
3. Champion/Challenger governance (no live auto-deploy)
4. No fixed weights (4 algorithms + Meta-Bandit)
5. Graceful degradation for Redis, MT5, broker

### 📊 DATA RULES
1. Real Data ≥ 95%
2. Synthetic Data = 0%
3. Coverage ≥ 95%
4. Quality Score ≥ 90/100
5. Each source stored separately: `titan/data/sources/{source}/`

### 🎨 REPORT STYLE
- Navy #14213D, Crimson #C8102E, Gold #B8860B
- Green #1E7D3A (PASS), Red #C8102E (FAIL)
- Liberation Serif/Sans/Mono fonts

### 🔒 DUKASCOPY DOWNLOAD
- .bi5 = LZMA compressed, BIG-ENDIAN binary
- Tick = 20 bytes: int32 ts_ms, int32 ASK, int32 BID, float32 ask_vol, float32 bid_vol
- URL month = 0-indexed (Jan=00)
- Price scale = 1000
- Rate limit: ~4 sec/day, use `timeout 300`, 2-week batches
- Resume: skip already-downloaded days

---

## 6. KNOWN ISSUES

| Issue | Impact | Fix |
|-------|--------|-----|
| `structlog` not installed | test_database.py + test_infrastructure.py errors | `pip install structlog` |
| `torch` not installed | LSTM/Transformer use sklearn fallback | `pip install torch` |
| `xgboost` not installed | XGBoost uses sklearn fallback | `pip install xgboost` |
| MT5 not on Linux | Broker/risk live paths can't test | mt5_stub.py (automatic) |
| Dukascopy rate limiting | Downloads slow (~4 sec/day) | Exponential backoff + resume |
| Tool timeout | Long downloads timeout Bash tool | `timeout 300` wrapper, 2-week batches |

---

## 7. SCORE HISTORY

| Audit | Score | Verdict | Reason |
|-------|-------|---------|--------|
| Pre-Training Audit | 67.5/100 | NOT READY | B1-B5 blockers |
| Post B1-B5 Remediation | 94.6/100 | READY | All blockers fixed |
| Competition Validation (calibrated) | 58.9/100 | FAIL | Used synthetic data |
| Real Data Acquisition Audit | IN PROGRESS | — | 783K bars downloaded, more needed |

---

## 8. IMPORTANT COMMANDS

### Download Real Data
```bash
cd /home/z/my-project
timeout 300 python scripts/real_data/fast_download.py 2020-04-01 2020-04-15
```

### Run Tests
```bash
cd /home/z/my-project
PYTHONPATH=/home/z/my-project python -m pytest titan/tests/ -q --tb=no \
  --ignore=titan/tests/test_database.py \
  --ignore=titan/tests/test_infrastructure.py
```

### Check Data Inventory
```bash
cd /home/z/my-project
python -c "
from pathlib import Path
import pandas as pd
daily = Path('titan/data/sources/dukascopy/daily')
files = sorted(daily.glob('XAUUSD_M1_*.parquet'))
total = sum(len(pd.read_parquet(f)) for f in files if not pd.read_parquet(f).empty)
print(f'Real bars: {total:,}')
"
```

---

## 9. AI BEHAVIOR GUIDELINES

### Naya session start hone par:
1. **Pehle yeh file padho** — PROJECT_CONTEXT.md
2. **Phir project_memory.md padho** — detailed context
3. **worklog.md ka last entry padho** — kya hua last time
4. **Data inventory check karo** — kitna data download hua
5. **User ko bolo** — current status aur next steps

### Jab user bole "continue":
1. Last task check karo (worklog.md se)
2. Data inventory check karo
3. Next step execute karo (bina puche)
4. Progress report karo

---

## 10. FILE LOCATIONS

| File | Path |
|------|------|
| **THIS FILE** | `/home/z/my-project/PROJECT_CONTEXT.md` |
| Detailed Memory | `/home/z/my-project/project_memory.md` |
| Worklog | `/home/z/my-project/worklog.md` |
| Cursor Rules | `/home/z/my-project/.cursorrules` |
| Codebase | `/home/z/my-project/titan/` |
| Real Data | `/home/z/my-project/titan/data/sources/dukascopy/daily/` |
| Scripts | `/home/z/my-project/scripts/` |
| Reports | `/home/z/my-project/download/` |
| Config | `/home/z/my-project/titan/config/titan.yaml` |

> **NOTE:** Codebase originally at `/tmp/my-project/titan/` but copied to
> `/home/z/my-project/titan/` for writable access. Always use `/home/z/my-project/`.
