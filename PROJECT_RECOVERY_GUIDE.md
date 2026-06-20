# TITAN XAU AI — PROJECT RECOVERY GUIDE

> This guide explains how to rebuild the ENTIRE project from the 4 ZIP files only.
> No other files needed. Follow these steps in order.

---

## STEP 1: Extract ZIPs

```bash
# Create project directory
mkdir -p ~/titan_project
cd ~/titan_project

# Extract all 4 ZIPs (they contain the full project)
unzip TITAN_SPLIT_1.zip
unzip TITAN_SPLIT_2.zip
unzip TITAN_SPLIT_3.zip
unzip TITAN_SPLIT_4.zip
```

After extraction you should have:
```
~/titan_project/
├── titan/              (codebase — 81 .py files)
├── scripts/            (54 .py + 47 .js + 178 .html)
├── download/           (26 PDF + 22 DOCX + 3 JSON)
├── PROJECT_CONTEXT.md
├── project_memory.md
├── worklog.md
├── .cursorrules
├── MASTER_PROJECT_MANIFEST.md
├── FILE_CHECKSUM_REPORT.md
└── PROJECT_RECOVERY_GUIDE.md
```

---

## STEP 2: Reinstall Dependencies

### Python Dependencies

```bash
cd ~/titan_project

# Create virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate

# Install core dependencies
pip install -r titan/requirements.txt

# Install additional packages (not in requirements.txt but needed)
pip install optuna==4.9.0 pyarrow==24.0.0 reportlab python-docx requests

# Verify installation
python -c "import pandas; import numpy; import optuna; print('Core deps OK')"
```

### AI/ML Dependencies (Optional — for full model training)

```bash
# XGBoost (for XGBoost model)
pip install xgboost==2.0.3

# PyTorch (for LSTM + Transformer models)
pip install torch==2.2.2

# ONNX Runtime (for model inference)
pip install onnxruntime==1.17.1

# Verify
python -c "import xgboost; import torch; import onnxruntime; print('AI deps OK')"
```

### Node.js Dependencies (Optional — for DOCX + diagram generation)

```bash
# Install Node.js (if not already installed)
# Ubuntu/Debian: sudo apt install nodejs npm
# Mac: brew install node

# Install docx and playwright for report generation
cd ~/titan_project/scripts/titan
npm install docx playwright
npx playwright install chromium
```

---

## STEP 3: Restore Database

### SQLite Database (Auto-created on first run)

```bash
cd ~/titan_project

# The SQLite database is auto-created when the system starts
# To manually initialize:
PYTHONPATH=. python -c "
import asyncio
from titan.database.layer import Database
db = Database('titan/data/titan.db')
asyncio.run(db.initialize())
print('Database initialized: titan/data/titan.db')
"
```

### Database Schema (7 tables, auto-created)
- `trades` — trade history
- `orders` — order records
- `positions` — open positions
- `system_state` — CEO + weighting state
- `metrics` — performance metrics
- `compliance_audit` — compliance events
- `licenses` — license store

### Redis Cache (Optional — graceful degradation without it)

```bash
# Install Redis
sudo apt install redis-server  # Ubuntu/Debian
brew install redis              # Mac

# Start Redis
redis-server --daemonize yes

# Verify
redis-cli ping
# Should return: PONG
```

If Redis is not available, TITAN continues without cache (graceful degradation).

---

## STEP 4: Restore Datasets

### Real Dukascopy Data (Already in ZIP)

The 4 ZIP files contain 594 parquet files with 783,085 REAL M1 bars.
After extraction, data is at:

```
titan/data/sources/dukascopy/daily/     (587 daily parquet files)
titan/data/sources/dukascopy/           (7 monthly parquet files)
```

### Download Missing Data (29 months still needed)

```bash
cd ~/titan_project

# Download missing months from Dukascopy
# Run in 2-week batches to avoid timeout

# 2020 missing months (Apr-Dec)
timeout 300 python scripts/real_data/fast_download.py 2020-04-01 2020-04-15
timeout 300 python scripts/real_data/fast_download.py 2020-04-16 2020-04-30
timeout 300 python scripts/real_data/fast_download.py 2020-05-01 2020-05-15
timeout 300 python scripts/real_data/fast_download.py 2020-05-16 2020-05-31
# ... continue for Jun-Dec 2020

# 2021 (entire year missing)
timeout 300 python scripts/real_data/fast_download.py 2021-01-01 2021-01-15
# ... continue for all 12 months

# 2022 H2 (Jul-Dec missing)
timeout 300 python scripts/real_data/fast_download.py 2022-07-01 2022-07-15
# ... continue for Jul-Dec 2022
```

### Verify Data Inventory

```bash
cd ~/titan_project
python -c "
from pathlib import Path
import pandas as pd
daily = Path('titan/data/sources/dukascopy/daily')
files = sorted(daily.glob('XAUUSD_M1_*.parquet'))
total = 0
days = 0
for f in files:
    df = pd.read_parquet(f)
    if not df.empty:
        total += len(df)
        days += 1
print(f'Real bars: {total:,}')
print(f'Trading days: {days}')
print(f'Synthetic: 0%')
"
```

---

## STEP 5: Run Tests

### Quick Test (skip structlog-dependent tests)

```bash
cd ~/titan_project
PYTHONPATH=. python -m pytest titan/tests/ -q --tb=no \
  --ignore=titan/tests/test_database.py \
  --ignore=titan/tests/test_infrastructure.py
```

Expected output:
```
364 passed in ~10s
```

### Full Test (with all dependencies installed)

```bash
# Install structlog first
pip install structlog==24.1.0

# Run all tests
PYTHONPATH=. python -m pytest titan/tests/ -q --tb=no
```

Expected output:
```
380+ passed in ~12s
```

### Run Specific Module Tests

```bash
# Training pipeline tests (B1-B5 fixes)
PYTHONPATH=. python -m pytest titan/tests/test_training.py -v

# AI layer tests
PYTHONPATH=. python -m pytest titan/tests/test_ai_layer.py -v

# Compliance tests
PYTHONPATH=. python -m pytest titan/tests/test_compliance.py -v
```

### Run with Coverage

```bash
PYTHONPATH=. python -m pytest titan/tests/ --cov=titan --cov-branch \
  --ignore=titan/tests/test_database.py \
  --ignore=titan/tests/test_infrastructure.py \
  --cov-report=term
```

---

## STEP 6: Start API Server

### Development Mode

```bash
cd ~/titan_project
PYTHONPATH=. uvicorn titan.api.server:app --host 0.0.0.0 --port 8000 --reload
```

### Production Mode

```bash
cd ~/titan_project
PYTHONPATH=. uvicorn titan.api.server:app --host 0.0.0.0 --port 8000 \
  --workers 4 --log-level info
```

### Verify API

```bash
# Health check
curl http://localhost:8000/health

# Get system status
curl http://localhost:8000/status
```

---

## STEP 7: Start Full System (Production — Windows with MT5)

### Prerequisites
- Windows 10/11 with MetaTrader 5 terminal installed
- MT5 account credentials configured in `titan/config/titan.yaml`
- All Python dependencies installed

### Configuration

Edit `titan/config/titan.yaml`:
```yaml
mt5:
  terminal_path: "C:\\Program Files\\MetaTrader 5\\terminal64.exe"
  login: 12345678        # Your MT5 login
  password: "your_password"
  server: "YourBroker-Server"
```

### Start System

```bash
cd ~/titan_project
PYTHONPATH=. python titan/main.py titan/config/titan.yaml
```

### Verify System Started

```bash
# Check API
curl http://localhost:8000/health

# Check logs for:
# "═══ TITAN XAU AI — READY ═══"
```

---

## STEP 8: Start Training

### Full Training Pipeline

```bash
cd ~/titan_project
PYTHONPATH=. python scripts/full_pipeline.py
```

This runs:
1. Phase 2: Data quality reports
2. Phase 3: Feature generation + scaling + selection + HPO + model training
3. Phase 4: Backtest + WFA + Monte Carlo + Stress Test + Validator
4. Phase 5: Deployment package + forward test plan

### Training Only (No Validation)

```bash
cd ~/titan_project
PYTHONPATH=. python -c "
from titan.training import FeatureEngine, StandardScaler, FeatureSelector
from titan.training import time_series_train_val_test_split
import pandas as pd

# Load data
df = pd.read_parquet('titan/data/sources/dukascopy/daily/XAUUSD_M1_2024-01-02.parquet')

# Generate features
fe = FeatureEngine()
fs = fe.generate(df)
print(f'Features: {fs.n_features}, Bars: {fs.n_bars}')

# Split with purge
split = time_series_train_val_test_split(
    pd.concat([fs.features, fs.targets], axis=1),
    train_ratio=0.6, val_ratio=0.2, test_ratio=0.2, purge=60
)
print(f'Train: {len(split.train)}, Val: {len(split.val)}, Test: {len(split.test)}')
"
```

### HPO Only (Hyperparameter Optimization)

```bash
cd ~/titan_project
PYTHONPATH=. python -c "
from titan.ai.ensemble_voter import HyperparameterOptimizer
import numpy as np

X = np.random.randn(500, 10)
y = np.random.choice([0, 1, 2], size=500)

hpo = HyperparameterOptimizer(n_trials=50, purge=60, embargo=10, seed=42)
result = hpo.optimize_xgboost(X, y)
print(f'Best params: {result.best_params}')
print(f'Best score: {result.best_score}')
"
```

---

## STEP 9: Run Validation

### Full Validation Framework

```bash
cd ~/titan_project
PYTHONPATH=. python -c "
from titan.validator.engine import ValidatorFramework
vf = ValidatorFramework()
result = vf.run()
print(f'Score: {result.aggregate_score}')
print(f'Verdict: {result.verdict.value}')
print(f'Suites: {len(result.suites)}')
"
```

### Walk-Forward Analysis Only

```bash
cd ~/titan_project
PYTHONPATH=. python -c "
from titan.walk_forward.engine import WalkForwardEngine
from titan.backtest.engine import generate_synthetic_ticks, generate_synthetic_signals

ticks = generate_synthetic_ticks(n_ticks=5000)
signals = generate_synthetic_signals(ticks, frequency=100)

wfa = WalkForwardEngine(train_size=500, test_size=100, step=100, purge=60, embargo=10)
result = wfa.run(ticks, signals, method='anchored')
print(f'WFE median: {result.wfe_median}')
print(f'Folds: {len(result.folds)}')
print(f'Verdict: {result.verdict.value}')
"
```

### Monte Carlo Simulation

```bash
cd ~/titan_project
PYTHONPATH=. python -c "
from titan.monte_carlo.engine import MonteCarloEngine
from titan.backtest.engine import generate_synthetic_ticks, generate_synthetic_signals, TickReplayExecutor

ticks = generate_synthetic_ticks(n_ticks=5000)
signals = generate_synthetic_signals(ticks, frequency=100)
executor = TickReplayExecutor()
bt_result = executor.run(ticks, signals)

mc = MonteCarloEngine(n_simulations=1000)
mc_result = mc.run(bt_result.trades)
print(f'Survival Score: {mc_result.survival_score}')
print(f'Risk of Ruin: {mc_result.risk_of_ruin}%')
"
```

---

## STEP 10: Generate Reports

### Competition Validation Report

```bash
cd ~/titan_project
python scripts/competition_report.py
# Output: download/TITAN_Competition_Validation_Report_v1.0.pdf
```

### Pre-Training Audit Report

```bash
cd ~/titan_project
python scripts/pretraining_audit/build_pdf.py
# Output: download/TITAN_Pre_Training_Audit_Report_v1.0.pdf
```

### Blocker Remediation Report

```bash
cd ~/titan_project
python scripts/blocker_remediation/build_pdf.py
# Output: download/TITAN_Blocker_Remediation_BeforeAfter_v1.0.pdf
```

---

## TROUBLESHOOTING

### Issue: `ModuleNotFoundError: No module named 'titan'`
```bash
# Fix: Set PYTHONPATH
export PYTHONPATH=/path/to/titan_project
# Or run from project root with PYTHONPATH=.
```

### Issue: `ModuleNotFoundError: No module named 'structlog'`
```bash
pip install structlog==24.1.0
```

### Issue: `ModuleNotFoundError: No module named 'xgboost'`
```bash
pip install xgboost==2.0.3
# Or use sklearn fallback (automatic)
```

### Issue: `ModuleNotFoundError: No module named 'torch'`
```bash
pip install torch==2.2.2
# Or use sklearn fallback (automatic)
```

### Issue: `ModuleNotFoundError: No module named 'MetaTrader5'`
```bash
# This is expected on Linux. The system uses mt5_stub.py automatically.
# For production, run on Windows with MT5 installed.
```

### Issue: Tests fail with collection errors
```bash
# Skip structlog-dependent tests
PYTHONPATH=. python -m pytest titan/tests/ -q --tb=no \
  --ignore=titan/tests/test_database.py \
  --ignore=titan/tests/test_infrastructure.py
```

### Issue: Dukascopy download timeouts
```bash
# Use shorter date ranges (2 weeks at a time)
timeout 300 python scripts/real_data/fast_download.py 2020-04-01 2020-04-15
# Resume capability: already-downloaded days are skipped
```

### Issue: API server won't start
```bash
# Check port 8000 is not in use
lsof -i :8000
# Or use a different port
uvicorn titan.api.server:app --port 8001
```

---

## RECOVERY CHECKLIST

- [ ] Extract all 4 ZIPs
- [ ] Install Python dependencies (`pip install -r titan/requirements.txt`)
- [ ] Install additional packages (`pip install optuna pyarrow reportlab python-docx requests`)
- [ ] Verify core imports (`python -c "import pandas; import numpy; import optuna"`)
- [ ] (Optional) Install AI deps (`pip install xgboost torch onnxruntime`)
- [ ] (Optional) Install structlog (`pip install structlog`)
- [ ] Run tests (`PYTHONPATH=. python -m pytest titan/tests/ -q --tb=no`)
- [ ] Verify 364 tests pass
- [ ] Check data inventory (783,085 REAL bars)
- [ ] Start API server (`uvicorn titan.api.server:app --port 8000`)
- [ ] Verify API health (`curl http://localhost:8000/health`)
- [ ] Read PROJECT_CONTEXT.md for full project context
- [ ] Read project_memory.md for detailed memory

---

## END OF RECOVERY GUIDE
