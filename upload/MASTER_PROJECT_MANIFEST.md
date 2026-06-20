# TITAN XAU AI — MASTER PROJECT MANIFEST
# Generated: June 20, 2026
# Total Files: 1,146
# This file is the complete ownership document for the entire project.

---

## 1. COMPLETE FOLDER TREE

```
/home/z/my-project/
│
├── PROJECT_CONTEXT.md              Master AI context map
├── project_memory.md               Detailed project memory
├── worklog.md                      Shared session work log
├── .cursorrules                    Cursor IDE rules
├── MASTER_PROJECT_MANIFEST.md      THIS FILE
├── FILE_CHECKSUM_REPORT.md         SHA256 checksums for all files
├── PROJECT_RECOVERY_GUIDE.md       How to rebuild from ZIP
│
├── titan/                          MAIN CODEBASE (12,168 lines production)
│   ├── __init__.py
│   ├── main.py                     (472 lines) TitanSystem orchestrator
│   ├── conftest.py                 MT5 mock injection
│   ├── mt5_stub.py                 MT5 stub for Linux
│   ├── MetaTrader5.py              MT5 re-export
│   ├── pytest.ini                  Test configuration
│   ├── requirements.txt            Python dependencies
│   │
│   ├── config/
│   │   └── titan.yaml              System configuration (brokers, risk, etc.)
│   │
│   ├── ai/                         AI MODELS (6 files, 1,614 lines)
│   │   ├── __init__.py
│   │   ├── base_model.py           (149) IModel ABC, Prediction, ModelMetadata
│   │   ├── xgboost_model.py        (214) XGBoost wrapper, ONNX export
│   │   ├── lstm_model.py           (230) PyTorch LSTM (2 layers, 128 hidden)
│   │   ├── transformer_model.py    (254) Multi-head attention (8 heads, 6 layers)
│   │   ├── ensemble_voter.py       (410) Weighted voting + Optuna HPO (B2 fix)
│   │   └── model_registry.py       (221) SHA-256 content-addressed registry
│   │
│   ├── api/                        API SERVER
│   │   ├── __init__.py
│   │   └── server.py               (222) FastAPI, 10+ endpoints, WebSocket
│   │
│   ├── backtest/                   BACKTEST ENGINE
│   │   ├── __init__.py
│   │   └── engine.py               (358) TickReplayExecutor, CostEngine (5 costs)
│   │
│   ├── broker/                     BROKER COMPATIBILITY
│   │   ├── __init__.py
│   │   └── engine.py               (316) 6 brokers, 9 properties, symbol resolution
│   │
│   ├── ceo/                        CEO SUPERVISOR
│   │   ├── __init__.py
│   │   └── supervisor.py           (412) 8 detectors, 5 actions, GREEN/YELLOW/RED
│   │
│   ├── compliance/                 PROP FIRM COMPLIANCE (4 files, 1,224 lines)
│   │   ├── __init__.py
│   │   ├── profiles.py             (311) FTMO, FundedNext, E8, The5ers, FundingPips
│   │   ├── rule_engine.py          (528) 14 compliance rules
│   │   ├── engine.py               (232) ComplianceEngine wrapper
│   │   └── audit.py                (153) SQLite audit log
│   │
│   ├── database/                   DATABASE LAYER
│   │   ├── __init__.py
│   │   └── layer.py                (413) SQLite (7 tables), Redis cache, 5 repos
│   │
│   ├── execution/                  EXECUTION ENGINE
│   │   ├── __init__.py
│   │   └── engine.py               (410) Async dispatch, idempotency LRU, retry
│   │
│   ├── licensing/                  LICENSING (5 files, 1,456 lines)
│   │   ├── __init__.py
│   │   ├── fingerprint.py          (235) 6-component hardware fingerprint
│   │   ├── jwt_license.py          (264) HS256 JWT, 3 tiers (M/Q/Y)
│   │   ├── store.py                (309) SQLite license store, anti-tamper
│   │   ├── activation.py           (360) Online + offline activation
│   │   └── guard.py                (288) Runtime enforcement, heartbeat
│   │
│   ├── market_data/                MARKET DATA
│   │   ├── __init__.py
│   │   └── engine.py               (314) 10 quality gates, SpreadMonitor
│   │
│   ├── monte_carlo/                MONTE CARLO
│   │   ├── __init__.py
│   │   └── engine.py               (145) 3 randomization dims, Survival Score
│   │
│   ├── observability/              OBSERVABILITY
│   │   ├── __init__.py
│   │   └── metrics.py              (164) 25+ Prometheus metrics, AlertManager
│   │
│   ├── regime/                     REGIME DETECTION
│   │   ├── __init__.py
│   │   └── engine.py               (512) 3-model vote (HMM+Logit+Heuristic)
│   │
│   ├── risk/                       RISK ENGINE
│   │   ├── __init__.py
│   │   └── engine.py               (433) 12 controls, 4 modes, kill-switch
│   │
│   ├── strategies/                 TRADING STRATEGIES (3 files, 851 lines)
│   │   ├── __init__.py
│   │   ├── trend_engine.py         (316) 5 patterns, R-multiple
│   │   ├── range_engine.py         (270) BB+RSI+ATR+Hurst
│   │   └── volatility_engine.py    (265) ATR breakout, news-aware
│   │
│   ├── stress_test/                STRESS TESTING
│   │   ├── __init__.py
│   │   └── engine.py               (219) 6 scenarios
│   │
│   ├── tests/                      TEST SUITE (17 files, 4,464 lines, 364 tests)
│   │   ├── __init__.py
│   │   ├── test_ai_layer.py
│   │   ├── test_broker.py
│   │   ├── test_ceo.py
│   │   ├── test_compliance.py
│   │   ├── test_database.py
│   │   ├── test_execution.py
│   │   ├── test_infrastructure.py
│   │   ├── test_licensing.py
│   │   ├── test_market_data.py
│   │   ├── test_range_strategy.py
│   │   ├── test_regime.py
│   │   ├── test_risk.py
│   │   ├── test_training.py
│   │   ├── test_trend_strategy.py
│   │   ├── test_validation_framework.py
│   │   ├── test_volatility_engine.py
│   │   └── test_weighting.py
│   │
│   ├── training/                   TRAINING PIPELINE (5 files, 1,961 lines)
│   │   ├── __init__.py
│   │   ├── data_acquisition.py     (363) 4-source pipeline
│   │   ├── historical_ingestion.py (304) Multi-year bulk loader
│   │   ├── feature_engine.py       (535) 61 features + scalers + selector
│   │   ├── dataset_validator.py    (529) 12 checks + PurgedKFold + split
│   │   └── quality_scorer.py       (232) 5-dimensional 0-100 scoring
│   │
│   ├── validator/                  VALIDATOR FRAMEWORK
│   │   ├── __init__.py
│   │   └── engine.py               (153) 8 suites, 144 checks, certification
│   │
│   ├── walk_forward/               WALK-FORWARD (B1/B4 FIXED)
│   │   ├── __init__.py
│   │   └── engine.py               (173) Anchored+rolling, purge+embargo
│   │
│   ├── weighting/                  DYNAMIC WEIGHTING
│   │   ├── __init__.py
│   │   └── engine.py               (317) 4 algorithms + Meta-Bandit
│   │
│   └── data/                       DATA STORAGE
│       └── sources/
│           ├── dukascopy/          REAL Dukascopy data (783,085 bars)
│           │   ├── daily/          587 daily parquet files
│           │   └── XAUUSD_M1_*.parquet  Monthly merged files
│           ├── exness_mt5/         (empty — no data yet)
│           ├── icmarkets_mt5/      (empty — no data yet)
│           ├── pepperstone/        (empty — no data yet)
│           ├── truefx/             (empty — no data yet)
│           └── kaggle/             (empty — no data yet)
│
├── scripts/                        GENERATION SCRIPTS (54 .py + 47 .js)
│   ├── real_data/                  Real data download scripts
│   │   ├── fast_download.py        Fast parallel Dukascopy downloader
│   │   ├── dukascopy_v2.py         Production Dukascopy downloader
│   │   ├── dukascopy_download.py   Original downloader
│   │   ├── download_incremental.py Incremental downloader
│   │   └── calibrated_generator.py (DEPRECATED — do not use)
│   ├── full_pipeline.py            Full training+validation pipeline
│   ├── competition_report.py       Competition validation PDF generator
│   ├── real_data_audit.py          Real data audit script
│   ├── real_data_audit_report.py   Real data audit report generator
│   ├── pretraining_audit/          Pre-training audit report
│   ├── blocker_remediation/        B1-B5 fix report
│   └── [module_name]/              Per-module report generators (18 dirs)
│       ├── build_pdf.py            PDF generator
│       ├── merge_pdf.py            PDF merger (cover + body)
│       ├── build_docx.js           DOCX generator (Node.js)
│       ├── render_diagrams.js      HTML diagram renderer (Playwright)
│       └── diagrams/               HTML + PNG diagrams
│
└── download/                       DELIVERABLES
    ├── TITAN_*.pdf                 26 PDF reports
    ├── TITAN_*.docx                22 DOCX reports
    ├── TITAN_*.json                3 JSON artifacts
    ├── TITAN_SPLIT_1.zip           41 MB (part 1 of 4)
    ├── TITAN_SPLIT_2.zip           40 MB (part 2 of 4)
    ├── TITAN_SPLIT_3.zip           38 MB (part 3 of 4)
    ├── TITAN_SPLIT_4.zip           27 MB (part 4 of 4)
    └── README.md                   Download directory README
```

---

## 2. EVERY SOURCE FILE

### Production Code (39 modules, 12,168 lines)

| File | Lines | Purpose |
|------|-------|---------|
| titan/main.py | 472 | TitanSystem orchestrator, 14-component DI |
| titan/ai/base_model.py | 149 | IModel ABC, Prediction, ModelMetadata |
| titan/ai/xgboost_model.py | 214 | XGBoost wrapper, ONNX export |
| titan/ai/lstm_model.py | 230 | PyTorch LSTM (2 layers, 128 hidden) |
| titan/ai/transformer_model.py | 254 | Multi-head attention (8 heads, 6 layers) |
| titan/ai/ensemble_voter.py | 410 | Weighted voting + Optuna HPO |
| titan/ai/model_registry.py | 221 | SHA-256 content-addressed registry |
| titan/api/server.py | 222 | FastAPI, 10+ endpoints, WebSocket |
| titan/backtest/engine.py | 358 | TickReplayExecutor, CostEngine |
| titan/broker/engine.py | 316 | 6 brokers, 9 properties |
| titan/ceo/supervisor.py | 412 | 8 detectors, 5 actions |
| titan/compliance/profiles.py | 311 | 5 prop firms |
| titan/compliance/rule_engine.py | 528 | 14 compliance rules |
| titan/compliance/engine.py | 232 | ComplianceEngine wrapper |
| titan/compliance/audit.py | 153 | SQLite audit log |
| titan/database/layer.py | 413 | SQLite + Redis, 5 repositories |
| titan/execution/engine.py | 410 | Async dispatch, idempotency |
| titan/licensing/fingerprint.py | 235 | 6-component hardware fingerprint |
| titan/licensing/jwt_license.py | 264 | HS256 JWT, 3 tiers |
| titan/licensing/store.py | 309 | SQLite license store |
| titan/licensing/activation.py | 360 | Online + offline activation |
| titan/licensing/guard.py | 288 | Runtime enforcement |
| titan/market_data/engine.py | 314 | 10 quality gates |
| titan/monte_carlo/engine.py | 145 | Monte Carlo simulation |
| titan/observability/metrics.py | 164 | 25+ Prometheus metrics |
| titan/regime/engine.py | 512 | 3-model vote regime detection |
| titan/risk/engine.py | 433 | 12 controls, kill-switch |
| titan/strategies/trend_engine.py | 316 | 5 trend patterns |
| titan/strategies/range_engine.py | 270 | BB+RSI+ATR+Hurst |
| titan/strategies/volatility_engine.py | 265 | ATR breakout |
| titan/stress_test/engine.py | 219 | 6 stress scenarios |
| titan/training/data_acquisition.py | 363 | 4-source pipeline |
| titan/training/historical_ingestion.py | 304 | Multi-year loader |
| titan/training/feature_engine.py | 535 | 61 features + scalers + selector |
| titan/training/dataset_validator.py | 529 | 12 checks + PurgedKFold |
| titan/training/quality_scorer.py | 232 | 5-dimensional scoring |
| titan/validator/engine.py | 153 | 8 suites, 144 checks |
| titan/walk_forward/engine.py | 173 | Anchored+rolling WFA |
| titan/weighting/engine.py | 317 | 4 algorithms + Meta-Bandit |

### Utility Files
| File | Purpose |
|------|---------|
| titan/__init__.py | Package init |
| titan/conftest.py | MT5 mock injection for Linux |
| titan/mt5_stub.py | MT5 stub for non-Windows testing |
| titan/MetaTrader5.py | MT5 re-export |

---

## 3. EVERY TEST FILE (17 files, 4,464 lines, 364 tests)

| File | Tests | Covers |
|------|-------|--------|
| titan/tests/test_ai_layer.py | 25 | AI models, ensemble, registry |
| titan/tests/test_broker.py | 9 | Broker compatibility |
| titan/tests/test_ceo.py | 24 | CEO supervisor |
| titan/tests/test_compliance.py | 69 | Prop firm compliance |
| titan/tests/test_database.py | 8 | Database layer (needs structlog) |
| titan/tests/test_execution.py | 13 | Execution engine |
| titan/tests/test_infrastructure.py | 18 | API, observability (needs structlog) |
| titan/tests/test_licensing.py | 47 | JWT, activation, guard |
| titan/tests/test_market_data.py | 19 | Market data engine |
| titan/tests/test_range_strategy.py | 6 | Range strategy |
| titan/tests/test_regime.py | 17 | Regime detection |
| titan/tests/test_risk.py | 11 | Risk engine |
| titan/tests/test_training.py | 77 | Training pipeline (B1-B5 fixes) |
| titan/tests/test_trend_strategy.py | 6 | Trend strategy |
| titan/tests/test_validation_framework.py | 22 | Backtest, WFA, MC, stress, validator |
| titan/tests/test_volatility_engine.py | 7 | Volatility strategy |
| titan/tests/test_weighting.py | 23 | Weighting engine |

---

## 4. EVERY CONFIG FILE

| File | Purpose |
|------|---------|
| titan/config/titan.yaml | System config: brokers, risk, licensing, compliance |
| titan/pytest.ini | Test configuration (asyncio_mode=auto) |
| titan/requirements.txt | Python dependencies (24 packages) |
| .cursorrules | Cursor IDE rules |

---

## 5. EVERY REPORT

### PDF Reports (26 files)
1. TITAN_XAU_AI_Architecture_v1.0.pdf
2. TITAN_XAU_AI_Architecture_v2.0.pdf
3. TITAN_Broker_Compatibility_Engine_v1.0.pdf
4. TITAN_Institutional_Execution_Engine_v1.0.pdf
5. TITAN_Institutional_Risk_Engine_v1.0.pdf
6. TITAN_Adaptive_Regime_Detection_System_v1.0.pdf
7. TITAN_Institutional_Trend_Following_Strategy_v1.0.pdf
8. TITAN_Mean_Reversion_Strategy_v1.0.pdf
9. TITAN_Hybrid_AI_Stack_v1.0.pdf
10. TITAN_Institutional_Backtesting_Framework_v1.0.pdf
11. TITAN_Walk_Forward_Testing_Framework_v1.0.pdf
12. TITAN_Monte_Carlo_Framework_v1.0.pdf
13. TITAN_Stress_Testing_Framework_v1.0.pdf
14. TITAN_Validator_Specification_v1.0.pdf
15. TITAN_Retraining_Framework_v1.0.pdf
16. TITAN_Meta_AI_CEO_Supervisor_v1.0.pdf
17. TITAN_Live_Intelligent_Model_Weighting_Engine_v1.0.pdf
18. TITAN_Execution_Cost_Intelligence_v1.0.pdf
19. TITAN_Commercial_Licensing_Architecture_v1.0.pdf
20. TITAN_Production_Readiness_Review_v1.0.pdf
21. TITAN_Production_Ready_v1.1_REMEDIATION_COMPLETE.pdf
22. TITAN_Production_Ready_v2.0_WORLD_CLASS.pdf
23. TITAN_Pre_Training_Audit_Report_v1.0.pdf
24. TITAN_Blocker_Remediation_BeforeAfter_v1.0.pdf
25. TITAN_Competition_Validation_Report_v1.0.pdf
26. TITAN_Real_Data_Acquisition_Audit_v1.0.pdf

### DOCX Reports (22 files)
(Same titles as PDFs, in Word format)

### JSON Artifacts (3 files)
1. TITAN_Competition_Validation_Results.json
2. TITAN_Feature_Selection_Report_v1.0.json
3. TITAN_Real_Data_Audit_Results.json

---

## 6. EVERY DATASET

### Real Data (Dukascopy — 100% REAL, 0% synthetic)
| Item | Value |
|------|-------|
| Source | Dukascopy (datafeed.dukascopy.com) |
| Storage | titan/data/sources/dukascopy/daily/ |
| Daily files | 587 parquet files |
| Monthly files | 7 parquet files |
| Total M1 bars | 783,085 |
| Date range | 2020-03-01 to 2024-12-31 |
| Trading days | 584 |
| Months covered | 31 |
| Months missing | 29 (2020 partial, 2021 all, 2022 H2) |
| Synthetic data | 0% |
| Format | Parquet (OHLCV + spread) |

### Empty Source Directories (awaiting data)
- titan/data/sources/exness_mt5/
- titan/data/sources/icmarkets_mt5/
- titan/data/sources/pepperstone/
- titan/data/sources/truefx/
- titan/data/sources/kaggle/

---

## 7. EVERY SCRIPT

### Python Scripts (54 files)
| Script | Purpose |
|--------|---------|
| scripts/real_data/fast_download.py | Fast parallel Dukascopy downloader (resume) |
| scripts/real_data/dukascopy_v2.py | Production Dukascopy downloader |
| scripts/real_data/dukascopy_download.py | Original downloader |
| scripts/real_data/download_incremental.py | Incremental downloader |
| scripts/real_data/calibrated_generator.py | DEPRECATED — do not use |
| scripts/full_pipeline.py | Full training+validation pipeline |
| scripts/competition_report.py | Competition validation PDF generator |
| scripts/real_data_audit.py | Real data audit script |
| scripts/real_data_audit_report.py | Audit report generator |
| scripts/pretraining_audit/build_pdf.py | Pre-training audit PDF |
| scripts/blocker_remediation/build_pdf.py | B1-B5 fix report PDF |
| scripts/titan/build_pdf.py | Architecture v1 PDF |
| scripts/titan-v2/build_pdf.py | Architecture v2 PDF |
| scripts/broker_engine/build_pdf.py | Broker module PDF |
| scripts/exec_engine/build_pdf.py | Execution module PDF |
| scripts/risk_engine/build_pdf.py | Risk module PDF |
| scripts/regime/build_pdf.py | Regime module PDF |
| scripts/trend_strategy/build_pdf.py | Trend strategy PDF |
| scripts/mean_reversion/build_pdf.py | Range strategy PDF |
| scripts/hybrid_ai/build_pdf.py | AI stack PDF |
| scripts/backtest/build_pdf.py | Backtest framework PDF |
| scripts/wfa/build_pdf.py | Walk-forward PDF |
| scripts/mc/build_pdf.py | Monte Carlo PDF |
| scripts/stress/build_pdf.py | Stress test PDF |
| scripts/validator/build_pdf.py | Validator PDF |
| scripts/retraining/build_pdf.py | Retraining PDF |
| scripts/ceo/build_pdf.py | CEO supervisor PDF |
| scripts/weighting/build_pdf.py | Weighting engine PDF |
| scripts/cost_intel/build_pdf.py | Execution cost intelligence PDF |
| scripts/licensing/build_pdf.py | Licensing PDF |
| scripts/readiness/build_pdf.py | Production readiness v1 PDF |
| scripts/readiness-v1.1/build_pdf.py | Production readiness v1.1 PDF |
| scripts/readiness-v2/build_pdf.py | Production readiness v2 PDF |
| scripts/titan/content_part1.py | Architecture content part 1 |
| scripts/titan/content_part2.py | Architecture content part 2 |
| (+ 19 merge_pdf.py files) | PDF mergers for each module |

### JavaScript Scripts (47 files)
- 22 build_docx.js files (DOCX generators using Node.js docx library)
- 22 render_diagrams.js files (HTML diagram renderers using Playwright)
- 3 additional JS files in scripts/titan/

---

## 8. EVERY DEPENDENCY

### Python Dependencies (from titan/requirements.txt)
| Package | Version | Purpose |
|---------|---------|---------|
| asyncio | 3.4.3 | Async operations |
| MetaTrader5 | 5.0.45 | Broker connection (Windows) |
| numpy | 1.26.4 | Numerical computation |
| scipy | 1.12.0 | Scientific computing |
| pandas | 2.2.1 | Data manipulation |
| sqlalchemy | 2.0.29 | Database ORM |
| aiosqlite | 0.20.0 | Async SQLite |
| redis | 5.0.3 | Cache layer |
| fastapi | 0.110.0 | REST API framework |
| uvicorn | 0.29.0 | ASGI server |
| pydantic | 2.6.4 | Data validation |
| xgboost | 2.0.3 | Gradient-boosted trees |
| torch | 2.2.2 | LSTM + Transformer |
| onnxruntime | 1.17.1 | ONNX model inference |
| pytest | 8.1.1 | Test framework |
| pytest-asyncio | 0.23.6 | Async test support |
| pytest-cov | 4.1.0 | Coverage measurement |
| prometheus-client | 0.20.0 | Metrics |
| structlog | 24.1.0 | Structured logging |
| pyyaml | 6.0.1 | YAML config parsing |

### Additional Installed Packages (not in requirements.txt)
| Package | Version | Purpose |
|---------|---------|---------|
| optuna | 4.9.0 | Hyperparameter optimization (B2 fix) |
| pyarrow | 24.0.0 | Parquet read/write |
| reportlab | — | PDF report generation |
| python-docx | — | DOCX report generation |
| requests | 2.32.5 | HTTP downloads |

### Node.js Dependencies (for DOCX + diagram generation)
- docx (npm package for Word document generation)
- playwright (for HTML→PNG diagram rendering)

---

## 9. EVERY ENVIRONMENT VARIABLE

| Variable | Purpose | Required? |
|----------|---------|-----------|
| TITAN_JWT_SECRET | JWT signing secret for licensing (≥16 chars) | YES (production) |
| PYTHONPATH | Must include /home/z/my-project | YES (testing) |
| MT5_TERMINAL_PATH | Path to MT5 terminal64.exe | Windows only |
| MT5_LOGIN | MT5 account login | Production |
| MT5_PASSWORD | MT5 account password | Production |
| MT5_SERVER | MT5 broker server | Production |

---

## 10. EVERY COMMAND

### Startup Commands
```bash
# Start full TITAN system (production — Windows with MT5)
cd /home/z/my-project
python titan/main.py titan/config/titan.yaml

# Start API server only
cd /home/z/my-project
uvicorn titan.api.server:app --host 0.0.0.0 --port 8000
```

### Test Commands
```bash
# Run all tests (skip structlog-dependent tests on Linux)
cd /home/z/my-project
PYTHONPATH=/home/z/my-project python -m pytest titan/tests/ -q --tb=no \
  --ignore=titan/tests/test_database.py \
  --ignore=titan/tests/test_infrastructure.py

# Run specific module tests
PYTHONPATH=/home/z/my-project python -m pytest titan/tests/test_training.py -v

# Run with coverage
PYTHONPATH=/home/z/my-project python -m pytest titan/tests/ --cov=titan --cov-branch \
  --ignore=titan/tests/test_database.py --ignore=titan/tests/test_infrastructure.py
```

### Data Download Commands
```bash
# Download real Dukascopy data (2-week batches to avoid timeout)
cd /home/z/my-project
timeout 300 python scripts/real_data/fast_download.py 2020-04-01 2020-04-15

# Check data inventory
python -c "
from pathlib import Path
import pandas as pd
daily = Path('titan/data/sources/dukascopy/daily')
files = sorted(daily.glob('XAUUSD_M1_*.parquet'))
total = sum(len(pd.read_parquet(f)) for f in files if not pd.read_parquet(f).empty)
print(f'Real bars: {total:,}')
"
```

### Training Commands
```bash
# Run full training + validation pipeline
cd /home/z/my-project
PYTHONPATH=/home/z/my-project python scripts/full_pipeline.py

# Run HPO only (XGBoost)
PYTHONPATH=/home/z/my-project python -c "
from titan.ai.ensemble_voter import HyperparameterOptimizer
import numpy as np
hpo = HyperparameterOptimizer(n_trials=50, purge=60, embargo=10)
result = hpo.optimize_xgboost(X_train, y_train)
print(result.best_params, result.best_score)
"
```

### Validation Commands
```bash
# Run validator framework
PYTHONPATH=/home/z/my-project python -c "
from titan.validator.engine import ValidatorFramework
vf = ValidatorFramework()
result = vf.run()
print(f'Score: {result.aggregate_score}, Verdict: {result.verdict.value}')
"

# Run walk-forward analysis
PYTHONPATH=/home/z/my-project python -c "
from titan.walk_forward.engine import WalkForwardEngine
wfa = WalkForwardEngine(train_size=500, test_size=100, step=100, purge=60, embargo=10)
result = wfa.run(ticks, signals, method='anchored')
print(f'WFE: {result.wfe_median}, Folds: {len(result.folds)}')
"
```

### Report Generation Commands
```bash
# Generate competition validation report
cd /home/z/my-project
python scripts/competition_report.py

# Generate pre-training audit report
python scripts/pretraining_audit/build_pdf.py

# Generate blocker remediation report
python scripts/blocker_remediation/build_pdf.py
```

### Deployment Commands
```bash
# Install dependencies
pip install -r titan/requirements.txt
pip install optuna pyarrow reportlab python-docx requests

# Initialize database
PYTHONPATH=/home/z/my-project python -c "
import asyncio
from titan.database.layer import Database
db = Database('data/titan.db')
asyncio.run(db.initialize())
"

# Verify system startup
PYTHONPATH=/home/z/my-project python -c "
from titan.main import TitanSystem
system = TitanSystem('titan/config/titan.yaml')
print('TITAN system initialized successfully')
"
```

---

## 11. ZIP ARCHIVES

| Archive | Size | Contents |
|---------|------|----------|
| TITAN_SPLIT_1.zip | 41 MB | Architecture PDFs + large data files |
| TITAN_SPLIT_2.zip | 40 MB | Module PDFs + DOCXs |
| TITAN_SPLIT_3.zip | 38 MB | More DOCXs + JS scripts + HTML diagrams |
| TITAN_SPLIT_4.zip | 27 MB | Python code + REAL data + context files |
| **TOTAL** | **146 MB** | **1,016 files** |

### Download Paths
```
/home/z/my-project/download/TITAN_SPLIT_1.zip
/home/z/my-project/download/TITAN_SPLIT_2.zip
/home/z/my-project/download/TITAN_SPLIT_3.zip
/home/z/my-project/download/TITAN_SPLIT_4.zip
```

---

## 12. PROJECT STATISTICS

| Metric | Value |
|--------|-------|
| Production code lines | 12,168 |
| Test code lines | 4,464 |
| Total Python files | 81 (titan/) + 54 (scripts/) = 135 |
| Total JavaScript files | 47 |
| Total HTML diagrams | 178 |
| Total test count | 364 |
| Total modules | 39 (38 modules + main.py) |
| Missing modules | 0 |
| PDF reports | 26 |
| DOCX reports | 22 |
| JSON artifacts | 3 |
| REAL data bars | 783,085 |
| REAL data files | 594 parquet |
| Synthetic data | 0% |
| ZIP archives | 4 (146 MB total) |

---

## END OF MANIFEST
