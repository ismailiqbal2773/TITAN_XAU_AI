# TITAN XAU AI — Project Memory File

> **Last Updated:** June 20, 2026 — 14:25 UTC
> **Session:** Real Data Acquisition Audit (Continued)
> **Status:** 783,085 REAL M1 bars acquired (31 months, 584 trading days). Missing months being downloaded.

---

## 1. PROJECT OVERVIEW

**What:** TITAN XAU AI is an institutional-grade AI trading system for XAUUSD (Gold/USD). It uses three AI models (XGBoost, LSTM, Transformer) in an ensemble, supervised by a CEO module, with full risk management, compliance, licensing, and validation frameworks.

**End Goal:** Move TITAN from development status to **Competition Validation Status** — a production-ready trading system that passes institutional validation thresholds (Sharpe > 2.0, PF > 2.0, MDD < 5%, WFE > 0.85, MC Survival > 95%, RoR < 1%, Validator Score > 90) and is ready for 30-day forward testing on a demo MT5 account.

**Current Phase:** Real data acquisition audit. Previous competition validation was REJECTED because it used calibrated/synthetic data. The user demands 100% REAL historical market data — zero synthetic data allowed.

---

## 2. TECH STACK

### Languages & Runtime
- **Python 3.12.13** (CPython on Linux x86_64)
- **asyncio** for concurrent operations
- **Type hints** throughout (PEP 604 `str | None` style)

### Core Libraries
| Library | Version | Purpose |
|---------|---------|---------|
| pandas | 2.x | Data manipulation, OHLCV bars |
| numpy | 1.26+ | Numerical computation |
| requests | 2.32.5 | HTTP downloads (Dukascopy) |
| lzma | stdlib | .bi5 tick data decompression |
| pyarrow | 24.0.0 | Parquet read/write |
| pyzmq | — | (not used directly) |
| reportlab | — | PDF report generation |
| pytest | 8.x | Test framework |
| pytest-asyncio | — | Async test support |
| optuna | 4.9.0 | Hyperparameter optimization (B2 fix) |

### AI/ML Libraries
| Library | Purpose | Status |
|---------|---------|--------|
| xgboost | Gradient-boosted trees model | Available |
| torch (PyTorch) | LSTM + Transformer models | NOT installed in current env |
| onnxruntime | ONNX model inference | Available |
| scikit-learn | Fallback models, metrics | Available |

### Infrastructure
| Component | Purpose |
|-----------|---------|
| SQLite (aiosqlite) | Primary database (trades, orders, state, licenses, compliance audit) |
| Redis | Cache layer (graceful degradation if unavailable) |
| FastAPI + uvicorn | REST API + WebSocket |
| Prometheus + structlog | Observability (structlog NOT installed in current env) |
| MetaTrader5 | Broker connection (Windows production; mt5_stub.py on Linux) |

### Report Generation
- **ReportLab** for PDF reports (Goldman Sachs white paper style: navy #14213D + crimson #C8102E + serif fonts)
- **python-docx** for DOCX reports
- Liberation Serif/Sans/Mono fonts (Times/Helvetica/Courier equivalents)

---

## 3. COMPLETED TASKS

### Architecture & Modules (22 modules, 12,797 lines production code)

| Module | File | Lines | Description |
|--------|------|-------|-------------|
| M01 Broker | `broker/engine.py` | 316 | 6-broker detection, 9 properties, symbol resolution |
| M02 Market Data | `market_data/engine.py` | 314 | 10 quality gates, RollingWindow, SpreadMonitor |
| M03 Execution | `execution/engine.py` | 410 | Async dispatch, idempotency LRU, retry, close_all |
| M04 Risk | `risk/engine.py` | 433 | 12 controls, 4 modes, kill-switch <500ms |
| M05 Regime | `regime/engine.py` | 512 | 3-model vote (HMM+Logit+Heuristic), 4 regimes |
| M06 Trend Strategy | `strategies/trend_engine.py` | 316 | 5 patterns, R-multiple, adaptive sizing |
| M07 Range Strategy | `strategies/range_engine.py` | 270 | BB+RSI+ATR+Hurst, smart recovery |
| M08 Volatility | `strategies/volatility_engine.py` | 265 | ATR breakout, news-aware, vol-of-vol |
| M09 AI Base | `ai/base_model.py` | 149 | IModel ABC, Prediction, ModelMetadata |
| M10 XGBoost | `ai/xgboost_model.py` | 214 | XGBoost wrapper, ONNX export, CPU `tree_method=hist` |
| M11 LSTM | `ai/lstm_model.py` | 230 | PyTorch LSTM (2 layers, 128 hidden), ONNX export |
| M12 Transformer | `ai/transformer_model.py` | 254 | Multi-head attention (8 heads, 6 layers), ONNX export |
| M13 Ensemble Voter | `ai/ensemble_voter.py` | 190+220 | Weighted voting, quorum 3/4 + HPO (B2 fix) |
| M14 Model Registry | `ai/model_registry.py` | 221 | SHA-256 content-addressed, champion/challenger |
| M15 CEO Supervisor | `ceo/supervisor.py` | 412 | 8 detectors, 5 actions, GREEN/YELLOW/RED/RED_PRESERVE |
| M16 Weighting Engine | `weighting/engine.py` | 317 | 4 algorithms + Meta-Bandit, no fixed weights |
| M17 Validator | `validator/engine.py` | 153 | 8 suites, 144 checks, 3-band certification |
| M18 Backtest | `backtest/engine.py` | 358 | Tick replay, 5 cost components, 24 metrics |
| M19 Walk-Forward | `walk_forward/engine.py` | 173 | Anchored/rolling, WFE, purge+embargo (B1/B4 fix) |
| M20 Monte Carlo | `monte_carlo/engine.py` | 145 | 3 randomization dims, Survival Score |
| M21 Stress Test | `stress_test/engine.py` | 219 | 6 scenarios (flash crash, spread, lag, disconnect, vol, gap) |
| M22 Database | `database/layer.py` | 413 | SQLite (7 tables), Redis cache, 5 repositories |
| M23 API | `api/server.py` | 222 | FastAPI, 10+ endpoints, WebSocket |
| M24 Observability | `observability/metrics.py` | 164 | 25+ Prometheus metrics, structured logging |
| M25 Main | `main.py` | 472 | TitanSystem orchestrator, 14-component DI |

### Commercial Layer (2 modules, 2,728 lines)

| Module | File | Lines | Description |
|--------|------|-------|-------------|
| M26 Licensing | `licensing/` (5 files) | 1,481 | Hardware-locked JWT licensing, online+offline activation, 3 tiers |
| M27 Compliance | `compliance/` (4 files) | 1,247 | 5 prop firms (FTMO, FundedNext, E8, The5ers, Funding Pips), 14 rules |

### Training Pipeline (1 module, 5 files, 1,608 lines)

| File | Lines | Description |
|------|-------|-------------|
| `training/data_acquisition.py` | 363 | 4-source pipeline (MT5/CSV/Parquet/Synthetic) |
| `training/historical_ingestion.py` | 304 | Multi-year bulk ingestion, M1→higher-tf aggregation |
| `training/feature_engine.py` | 535 | 61 features × 6 groups + StandardScaler + RobustScaler + FeatureSelector (B3/B5 fix) |
| `training/dataset_validator.py` | 529 | 12 checks + time_series_train_val_test_split + PurgedKFold (B4 fix) |
| `training/quality_scorer.py` | 232 | 5-dimensional 0-100 scoring (A+ to F grade) |

### Pre-Training Blocker Fixes (B1-B5, all verified)

| Blocker | Fix | File Modified | Tests Added |
|---------|-----|---------------|-------------|
| B1: Anchored WFA broken | True expanding window (train_start=0, train_end grows) | `walk_forward/engine.py` | 4 |
| B2: No HPO | Optuna-based HPO with PurgedKFold CV for XGBoost/LSTM/Transformer | `ai/ensemble_voter.py` | 7 |
| B3: No feature scaling | StandardScaler + RobustScaler (train-only fit, ±5σ clip) | `training/feature_engine.py` | 8 |
| B4: No purge/embargo | purge+embargo on WFA + time_series_train_val_test_split + PurgedKFold | `walk_forward/engine.py`, `training/dataset_validator.py` | 9 |
| B5: Feature redundancy | FeatureSelector drops |r|>0.95 + zero-variance; report generated | `training/feature_engine.py` | 8 |

### Test Suite
- **364 tests** collected (2 collection errors due to missing `structlog` dependency — env issue, not code)
- **0 regressions** from B1-B5 fixes
- Test runtime: ~10 seconds

### Deliverables Generated (51 files in `/home/z/my-project/download/`)
- 26 PDF reports (Goldman Sachs white paper style)
- 22 DOCX reports
- 3 JSON artifacts (feature selection report, competition validation results, etc.)

### Real Data Acquired (Dukascopy — NO synthetic data)
- **783,085 REAL M1 bars** (ZERO synthetic)
- **584 trading days** downloaded
- **31 months** covered across 5 calendar years (2020-2024)
- Stored per-day at: `titan/data/sources/dukascopy/daily/XAUUSD_M1_YYYY-MM-DD.parquet`
- Monthly merged files at: `titan/data/sources/dukascopy/XAUUSD_M1_YYYY-MM.parquet`

**Months WITH data (31 months):**
- 2020-03 (11 days — COVID crash)
- 2022-01 to 2022-06 (partial — Ukraine war + Fed tightening)
- 2023-01 to 2023-12 (COMPLETE — 12 months)
- 2024-01 to 2024-12 (COMPLETE — 12 months)

**Months MISSING (need to download):**
- 2020: Jan, Feb, Apr-Dec (11 months)
- 2021: Jan-Dec (ENTIRE YEAR — 12 months)
- 2022: Jul-Dec (6 months)

---

## 4. CURRENT STATUS / IN-PROGRESS (LATEST — June 20, 2026 14:25 UTC)

### What We Are Working On
**Real Data Acquisition Audit** — Downloading REAL Dukascopy XAUUSD M1 tick data.
Previous competition validation was REJECTED because it used synthetic data.

### Latest Progress
- **783,085 REAL M1 bars** downloaded (ZERO synthetic)
- **584 trading days** covered
- **31 months** across 5 calendar years (2020-2024)
- 2023 and 2024 are COMPLETE (24 months fully covered)
- All calibrated/synthetic data has been DELETED

### Months WITH data (31 months):
- 2020-03 (11 days — COVID crash)
- 2022-01 to 2022-06 (partial — Ukraine war + Fed tightening)
- 2023-01 to 2023-12 (COMPLETE — 12 months)
- 2024-01 to 2024-12 (COMPLETE — 12 months)

### Months MISSING (need to download):
- 2020: Jan, Feb, Apr-Dec (11 months)
- 2021: Jan-Dec (ENTIRE YEAR — 12 months)
- 2022: Jul-Dec (6 months)

### Where We Stopped
Downloads were timing out due to Dukascopy rate limiting (~4 sec/day).
The downloader (`scripts/real_data/fast_download.py`) has resume capability —
it skips already-downloaded days automatically.

---

## 5. NEXT STEPS

### Immediate (in priority order)

1. **Download missing months from Dukascopy**
   ```bash
   cd /home/z/my-project
   python scripts/real_data/fast_download.py 2020-04-01 2020-12-31
   python scripts/real_data/fast_download.py 2021-01-01 2021-12-31
   python scripts/real_data/fast_download.py 2022-01-01 2022-01-31
   python scripts/real_data/fast_download.py 2022-04-01 2022-12-31
   python scripts/real_data/fast_download.py 2023-10-01 2023-12-31
   ```
   Note: Dukascopy rate-limits to ~4 sec/day. Full 5-year download takes ~2-3 hours. Run in 2-week batches to avoid timeouts.

2. **Try alternative data sources for cross-validation**
   - TrueFX (free CSV tick data)
   - Kaggle gold datasets
   - Tickstory (free Dukascopy exporter)
   - Pepperstone MT5 (if MT5 available)

3. **Generate required audit reports** (after data download complete):
   - Coverage Report
   - Missing Data Report
   - Duplicate Report
   - Broker Difference Report
   - Spread Analysis
   - Commission Analysis
   - Slippage Calibration
   - Market Regime Analysis

4. **Verify regime coverage** in the downloaded data:
   - COVID 2020 (Mar-Apr 2020 — gold flash crash)
   - Ukraine War 2022 (Feb-Mar 2022 — gold spike to $2070)
   - Banking Crisis 2023 (Mar 2023 — SVB collapse, Credit Suisse)
   - Fed Tightening Cycle (2022-2023 — rate hikes)
   - High Inflation Period (2022 — gold volatility)
   - Extreme Volatility (any period with ATR > 2x average)
   - Long Trend Periods (sustained directional moves)
   - Long Range Periods (consolidation, low ADX)

5. **Run audits on real data:**
   - Data Quality Audit (using `titan.training.quality_scorer.DataQualityScorer`)
   - Dataset Validator (using `titan.training.dataset_validator.DatasetValidator`)
   - Leakage Audit (V11 check + lag/target shift verification)
   - Feature Audit (using `titan.training.feature_engine.FeatureEngine`)

6. **Compute final scores:**
   - Bars per source
   - Ticks per source
   - Coverage %
   - Missing %
   - Quality Score (0-100)
   - Data Quality Grade (A+ to F)

7. **Output verdict:** REAL DATA VERIFIED or DATA REJECTED
   - PASS only if: Quality Score ≥ 90, Coverage ≥ 95%, Real Data ≥ 95%, Synthetic = 0%

### After Data Verification (DO NOT START YET)
- Re-run Phase 3 (Model Training) on REAL data only
- Re-run Phase 4 (Institutional Validation) on REAL data only
- Re-run Phase 5 (Forward Test Readiness)
- Generate new Competition Validation Report

---

## 6. KEY DECISIONS & RULES

### Architecture Rules (MUST FOLLOW)
1. **No new architecture** — use existing TITAN codebase only
2. **No new modules** — extend existing files, do not create new module directories
3. **No new specifications** — implement, don't design
4. **CPU-only, fully offline** — no paid APIs, no external LLM, no cloud dependency
5. **RL NOT in CEO layer** — CEO uses Bayesian + MAB + statistical detectors only (user's explicit decision)
6. **RL only in M12 Trade Manager** — position scaling, exit policy, trailing stops
7. **Champion/Challenger governance** — no live auto-deploy of retrained models
8. **No fixed weights** — Weighting Engine uses 4 competing algorithms + Meta-Bandit

### Data Rules (CURRENT PHASE — STRICT)
1. **NO synthetic data** — zero tolerance
2. **NO random walk expansion** — no calibrating small datasets
3. **NO calibration of small datasets** — real data only
4. **Each source stored separately** — `titan/data/sources/{source}/`
5. **Real Data ≥ 95%** of total dataset
6. **Synthetic Data = 0%**
7. **Coverage ≥ 95%** of trading days
8. **Quality Score ≥ 90/100**

### Coding Rules
1. **Script Persistence Rule** — all generation scripts saved to `/home/z/my-project/scripts/` before execution
2. **File Output Rule** — all deliverables saved to `/home/z/my-project/download/`
3. **All files under `/home/z/my-project/`** — never write outside this base path
4. **Single worklog file** — `/home/z/my-project/worklog.md` (append-only, all agents share)
5. **Page Break Rule** — PDF: page breaks only between cover/TOC/body; no breaks within body
6. **Character Safety Rule** — PDF: no Unicode escape sequences; use ReportLab tags for bold/super/subscript
7. **Language Consistency Rule** — match user's language (English) for all outputs
8. **Content Depth Rule** — paragraphs ≥ 3-5 sentences; sections ≥ 150-200 words

### File Structure
```
/home/z/my-project/
├── titan/                          # Main codebase (12,797 lines production)
│   ├── ai/                         # AI models (6 files)
│   ├── api/                        # FastAPI server
│   ├── backtest/                   # Tick replay backtest engine
│   ├── broker/                     # 6-broker compatibility
│   ├── ceo/                        # CEO supervisor
│   ├── compliance/                 # Prop firm compliance (5 firms)
│   ├── config/                     # titan.yaml configuration
│   ├── data/                       # Data storage
│   │   └── sources/                # REAL data by source
│   │       ├── dukascopy/          # Dukascopy REAL tick data
│   │       │   └── daily/          # Per-day parquet files (450 days)
│   │       ├── exness_mt5/
│   │       ├── icmarkets_mt5/
│   │       ├── pepperstone/
│   │       ├── truefx/
│   │       └── kaggle/
│   ├── database/                   # SQLite + Redis layer
│   ├── execution/                  # Order execution engine
│   ├── licensing/                  # JWT licensing (5 files)
│   ├── market_data/                # Market data ingestion
│   ├── monte_carlo/                # Monte Carlo simulation
│   ├── observability/              # Prometheus metrics
│   ├── regime/                     # Regime detection (HMM+Logit+Heuristic)
│   ├── risk/                       # Risk engine (12 controls)
│   ├── strategies/                 # 3 strategies (trend/range/volatility)
│   ├── stress_test/                # 6 stress scenarios
│   ├── tests/                      # 364 tests (4,465 lines)
│   ├── training/                   # Training pipeline (5 files, B1-B5 fixes)
│   ├── validator/                  # 8-suite validator framework
│   ├── walk_forward/               # Walk-forward analysis (B1/B4 fixed)
│   ├── weighting/                  # Dynamic model weighting
│   ├── main.py                     # TitanSystem orchestrator
│   ├── conftest.py                 # MT5 mock for Linux testing
│   ├── mt5_stub.py                 # MT5 stub for non-Windows
│   └── MetaTrader5.py              # MT5 re-export
├── scripts/                        # Generation scripts (persisted)
│   ├── real_data/                  # Real data download scripts
│   │   ├── dukascopy_v2.py         # Production Dukascopy downloader
│   │   ├── fast_download.py        # Fast parallel downloader (resume capable)
│   │   └── download_incremental.py # Incremental downloader
│   ├── full_pipeline.py            # Full training+validation pipeline
│   ├── competition_report.py       # Competition validation PDF generator
│   ├── blocker_remediation/        # B1-B5 fix report generator
│   ├── pretraining_audit/          # Pre-training audit report generator
│   └── ...                         # Other report generators
├── download/                       # Deliverables (51 files)
│   ├── TITAN_*.pdf                 # 26 PDF reports
│   ├── TITAN_*.docx                # 22 DOCX reports
│   └── *.json                      # 3 JSON artifacts
├── worklog.md                      # Shared work log (append-only)
└── project_memory.md               # THIS FILE
```

### Key Palette (Goldman Sachs White Paper Style)
- Navy: `#14213D` (primary)
- Crimson: `#C8102E` (accent)
- Gold: `#B8860B` (highlights)
- Green: `#1E7D3A` (PASS)
- Red: `#C8102E` (FAIL)
- Fonts: Liberation Serif (body), Liberation Sans (headings), Liberation Mono (code)

---

## 7. KNOWN ISSUES / BUGS

### Environment Issues (NOT code bugs)
1. **`structlog` not installed** — causes `test_database.py` and `test_infrastructure.py` collection errors. Install with: `pip install structlog`
2. **`torch` (PyTorch) not installed** — LSTM and Transformer models cannot be fully trained in this environment. HPO still works (uses sklearn fallback). Install with: `pip install torch`
3. **`xgboost` not installed** — XGBoost model falls back to sklearn GradientBoostingClassifier. Install with: `pip install xgboost`
4. **MT5 not available on Linux** — `conftest.py` injects `mt5_stub.py` for testing. Production requires Windows with MT5 terminal installed.

### Dukascopy Rate Limiting
- Dukascopy's datafeed server (`datafeed.dukascopy.com`) rate-limits requests
- 502/503 errors occur when too many requests are made too quickly
- Download speed: ~4 seconds per trading day with 6 parallel hour-downloads
- Full 5-year download (~1300 trading days) takes ~1.5 hours
- **Mitigation:** exponential backoff in `fast_download.py`, resume capability, 150ms base sleep between requests

### Previous Competition Validation (REJECTED)
- **Reason:** Used calibrated/synthetic data (2,760 real bars + 2.6M calibrated bars)
- **User feedback:** "Only 2,760 real bars used. Majority of dataset was synthetic."
- **Fix:** Delete ALL calibrated data, download REAL data only. All calibrated data has been deleted from `titan/data/xauusd_real/`.

### Dukascopy .bi5 Format (SOLVED)
- **Issue:** Initial parsing produced wrong prices/timestamps
- **Root cause:** Dukascopy uses BIG-ENDIAN byte order; numpy defaults to little-endian on x86
- **Fix:** Use `'>i4'` (big-endian int32) and `'>f4'` (big-endian float32) in numpy view
- **Field order:** timestamp_ms, ASK (not bid), BID, ask_volume, bid_volume
- **Month indexing:** URL uses 0-indexed months (Jan=00, Feb=01, ...)

### Tool Timeout Issues
- Bash tool calls frequently timeout when downloading data (long-running operations)
- **Mitigation:** Use `timeout 300` wrapper for download commands, run in 2-week batches
- Background `nohup` processes sometimes die silently — check with `ps aux | grep python`

---

## 8. IMPORTANT COMMANDS REFERENCE

### Download Real Data
```bash
cd /home/z/my-project
# Download 2 weeks at a time (avoids timeout)
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

### Generate Report PDF
```bash
cd /home/z/my-project
python scripts/{report_name}/build_pdf.py
```

### Update This File
Whenever a major task is completed, update this `project_memory.md` file with:
- New completed tasks
- Updated current status
- New next steps
- Any new issues discovered

---

## 9. SCORE HISTORY

| Audit | Score | Verdict | Date |
|-------|-------|---------|------|
| Pre-Training Audit | 67.5/100 | NOT READY FOR TRAINING | June 2026 |
| Post B1-B5 Remediation | 94.6/100 | READY FOR TRAINING | June 2026 |
| Competition Validation (calibrated data) | 58.9/100 | FAIL (rejected — synthetic data) | June 2026 |
| Real Data Acquisition Audit | IN PROGRESS | 783,085 REAL bars downloaded, more needed | June 20, 2026 |

---

## 10. CONTACT / CONTEXT

- **Codebase location:** `/home/z/my-project/titan/`
- **Deliverables:** `/home/z/my-project/download/`
- **Scripts:** `/home/z/my-project/scripts/`
- **Worklog:** `/home/z/my-project/worklog.md`
- **This file:** `/home/z/my-project/project_memory.md`

> **NOTE:** The codebase was originally at `/tmp/my-project/titan/` but was copied to `/home/z/my-project/titan/` for writable access. All work should reference `/home/z/my-project/titan/`.
