# TITAN XAU AI — NEXT SESSION HANDOVER GUIDE
# ============================================
# Purpose: Continue project in next chat session without losing context.
# Start point: Feature Engineering (already built, needs full run + save)
# End goal: Model Training (ONLY after user confirmation)

---

## 📋 PROJECT STATE SUMMARY

### Completed Phases
1. ✅ Data Acquisition (4 brokers + Dukascopy = 2.92M real bars)
2. ✅ Data Preprocessing (316K canonical bars, anti-overfit)
3. ✅ Feature Pipeline Adapter (built, tested, pushed to GitHub)

### GitHub Repository
- URL: https://github.com/ismailiqbal2773/TITAN_XAU_AI
- Latest commit: 8687ed0 (feature pipeline adapter)
- All code + data + audits pushed

### Current Commit History
```
8687ed0 feat: feature pipeline adapter (canonical → architect's FeatureEngine)
bd77966 feat: world-class preprocessing pipeline (10 modules + 17 tests)
c17833b feat: real MT5 data from 4 brokers + audit reports + Windows acquisition script
9870c68 Add files via upload (user's MT5 data uploads)
2f6d26e chore: exclude large ZIPs from git tracking (GitHub 100MB limit)
```

---

## 🚀 STEP-BY-STEP GUIDE FOR NEXT SESSION

### Step 1: Clone Repository (fresh start, no memory issues)
```bash
cd /tmp
rm -rf titan_next
git clone https://github.com/ismailiqbal2773/TITAN_XAU_AI.git titan_next
cd titan_next
```

### Step 2: Install Dependencies
```bash
/home/z/.venv/bin/python -m pip install pyarrow pandas numpy py7zr \
    aiosqlite redis structlog pyyaml optuna
```

### Step 3: Verify State
```bash
# Check canonical data exists
ls titan/data/canonical/
# Expected: XAUUSD_H1/M5/M15/M30_canonical.parquet (4 files)

# Check feature pipeline exists
ls titan/preprocessing/feature_pipeline.py
# Expected: file exists

# Check architect's feature engine exists
ls titan/training/feature_engine.py
wc -l titan/training/feature_engine.py
# Expected: 534 lines
```

### Step 4: Fix Default Path in feature_pipeline.py
The feature_pipeline.py has a hardcoded path that needs updating:
```bash
# Fix the PROJECT_ROOT path
sed -i 's|PROJECT_ROOT = Path("/tmp/titan_audit")|PROJECT_ROOT = Path("/tmp/titan_next")|' \
    titan/preprocessing/feature_pipeline.py
```

### Step 5: Run Feature Pipeline (H1 first)
```bash
# IMPORTANT: Use timeout to avoid bash tool issues
PYTHONPATH=/tmp/titan_next timeout 30 /home/z/.venv/bin/python -m \
    titan.preprocessing.feature_pipeline H1
```

**Expected output:**
```
STEP 1: Load canonical data
  Loaded 38,234 bars from XAUUSD_H1_canonical.parquet
STEP 2: Generate features (architect's engine)
  Running architect's FeatureEngine...
  Generated 63 features × 37,164 bars
    price: 8 features
    technical: 18 features
    volatility: 10 features
    microstructure: 8 features
    time: 10 features
    lag: 7 features
  Dropped 0 rows with NaN (warmup period)
STEP 3: Split train/val/test (purge + embargo)
  Split (purge=60, embargo=10):
    Train: 26,014 bars
    Val:   5,505 bars
    Test:  5,505 bars
STEP 4: Fit scalers on TRAIN ONLY
STEP 5: Apply scaler
STEP 6: Feature selection
  Kept: ~50 / 63 features
STEP 7: Save feature parquets
```

### Step 6: Run on All Timeframes
```bash
for tf in M5 M15 M30 H1; do
    PYTHONPATH=/tmp/titan_next timeout 30 /home/z/.venv/bin/python -m \
        titan.preprocessing.feature_pipeline $tf
done
```

### Step 7: Verify Feature Outputs
```bash
ls titan/data/features/
# Expected files:
# XAUUSD_H1_X_train.parquet, XAUUSD_H1_y_train.parquet
# XAUUSD_H1_X_val.parquet, XAUUSD_H1_y_val.parquet
# XAUUSD_H1_X_test.parquet, XAUUSD_H1_y_test.parquet
# (same for M5, M15, M30)
```

### Step 8: Commit + Push Features
```bash
git add titan/data/features/
git commit -m "feat: feature parquets for M5/M15/M30/H1 (train/val/test splits)"
TOKEN="<USE_FRESH_GITHUB_PAT>"  # Old token may be expired
git remote remove origin
git remote add origin "https://x-access-token:${TOKEN}@github.com/ismailiqbal2773/TITAN_XAU_AI.git"
git push origin main
git remote remove origin
git remote add origin "https://github.com/ismailiqbal2773/TITAN_XAU_AI.git"
```

### Step 9: STOP — Ask User for Training Confirmation
```
Feature engineering complete. Ready for model training.
Should I start training? (XGBoost + LSTM + Transformer)
User must confirm before training begins.
```

---

## 🏗️ ARCHITECT COMPLIANCE CHECKLIST

The next session MUST follow architect's design:

### Feature Engineering (M28.3)
- ✅ Use architect's `titan/training/feature_engine.py` (DO NOT modify)
- ✅ 6 feature groups: price, technical, volatility, microstructure, time, lag
- ✅ 63 features total (8+18+10+8+10+7)
- ✅ 4 targets: target_ret_1, target_ret_5, target_ret_15, target_ret_60

### Scaling (M28.3 — B3 fix)
- ✅ StandardScaler with ±5σ clip (train-only fit)
- ✅ RobustScaler with ±5σ clip (train-only fit)
- ✅ Both in `titan/training/feature_engine.py`

### Feature Selection (M28.3 — B5 fix)
- ✅ Drop zero-variance features (threshold=1e-10)
- ✅ Drop high-correlation features (|r|>0.95)
- ✅ Train-only fit (no leakage)

### Train/Val/Test Split (M28.3 — B4 fix)
- ✅ Purge gap = 60 bars (prevents label leakage)
- ✅ Embargo = 10 bars (extra safety)
- ✅ 70% train / 15% val / 15% test

### Model Training (M28.3 — B2 fix)
- ✅ Use architect's `titan/ai/xgboost_model.py`, `lstm_model.py`, `transformer_model.py`
- ✅ HPO via Optuna with PurgedKFold CV (purge=60)
- ✅ NO random shuffling, NO leakage

---

## 📁 KEY FILE LOCATIONS

### Production Code
```
titan/training/feature_engine.py     # Architect's feature engine (534 lines)
titan/training/dataset_validator.py  # Dataset validation (529 lines)
titan/training/quality_scorer.py     # Quality scoring (232 lines)
titan/ai/xgboost_model.py            # XGBoost model (214 lines)
titan/ai/lstm_model.py               # LSTM model (230 lines)
titan/ai/transformer_model.py        # Transformer model (254 lines)
titan/ai/ensemble_voter.py           # Ensemble + HPO (410 lines)
```

### Preprocessing (NEW — built this session)
```
titan/preprocessing/__init__.py
titan/preprocessing/schema_unifier.py
titan/preprocessing/spread_normalizer.py
titan/preprocessing/outlier_detector.py
titan/preprocessing/gap_filler.py
titan/preprocessing/deduplicator.py
titan/preprocessing/regime_tagger.py
titan/preprocessing/class_balancer.py
titan/preprocessing/canonical_merger.py
titan/preprocessing/pipeline.py
titan/preprocessing/feature_pipeline.py  # ← ADAPTER (run this next)
```

### Data
```
titan/data/sources/mt5_brokers/     # 4 broker raw data (READ-ONLY)
  ├── exness/        (7 files)
  ├── fundednext/    (7 files)
  ├── fbs/           (6 files, no M1)
  └── icmarkets/     (7 files)
titan/data/canonical/               # Preprocessed canonical datasets
  ├── XAUUSD_H1_canonical.parquet   (38,234 bars)
  ├── XAUUSD_M30_canonical.parquet  (76,069 bars)
  ├── XAUUSD_M15_canonical.parquet  (100,645 bars)
  └── XAUUSD_M5_canonical.parquet   (101,092 bars)
titan/data/features/                # ← TO BE CREATED (feature parquets)
```

### Configs
```
titan/config/titan.yaml             # Main config
titan/pytest.ini                    # Test config
titan/requirements.txt              # Python dependencies
```

### Tests
```
titan/tests/test_preprocessing.py   # 17 tests (all pass)
titan/tests/test_training.py        # 77 tests (feature engine + pipeline)
titan/tests/test_ai_layer.py        # 25 tests (AI models)
```

---

## ⚠️ KNOWN ISSUES + FIXES

### Issue 1: Bash Tool Timeouts
**Problem:** Long-running Python scripts timeout the bash tool (~5min limit).
**Fix:** Use `timeout 30` wrapper, run in small chunks.

### Issue 2: feature_pipeline.py Path
**Problem:** `PROJECT_ROOT` hardcoded to `/tmp/titan_audit`.
**Fix:** Run `sed` command in Step 4 above to update path.

### Issue 3: Memory Usage
**Problem:** Large DataFrames cause memory issues when doing `X.notna().all(axis=1) & y.notna()`.
**Fix:** Already fixed in feature_pipeline.py — uses separate masks:
```python
X_valid = X.notna().all(axis=1)
y_valid = y.notna()
valid_mask = X_valid & y_valid
```

### Issue 4: GitHub Token Expiry
**Problem:** Fine-grained PAT may expire between sessions.
**Fix:** User provides fresh token in next session if push fails.

---

## 🎯 TRAINING PHASE CHECKLIST (after user confirms)

When user says "start training", follow this exact sequence:

### 1. Load Feature Parquets
```python
import pandas as pd
train_X = pd.read_parquet('titan/data/features/XAUUSD_H1_X_train.parquet')
train_y = pd.read_parquet('titan/data/features/XAUUSD_H1_y_train.parquet')
# Same for val, test
```

### 2. Train XGBoost (architect's model)
```python
from titan.ai.xgboost_model import XGBoostModel
model = XGBoostModel()
model.fit(train_X, train_y, val_X, val_y)
```

### 3. Train LSTM (architect's model)
```python
from titan.ai.lstm_model import LSTMModel
model = LSTMModel()
model.fit(train_X, train_y, val_X, val_y)
```

### 4. Train Transformer (architect's model)
```python
from titan.ai.transformer_model import TransformerModel
model = TransformerModel()
model.fit(train_X, train_y, val_X, val_y)
```

### 5. Ensemble + HPO (architect's ensemble_voter)
```python
from titan.ai.ensemble_voter import EnsembleVoter, HyperparameterOptimizer
# HPO with PurgedKFold (purge=60)
hpo = HyperparameterOptimizer(n_trials=50, purge=60, embargo=10)
```

### 6. Save Trained Models
```python
# Save to titan/data/models/
model.save('titan/data/models/xgboost_v1.pkl')
```

### 7. Run Validation Framework
```python
from titan.validator.engine import ValidatorFramework
vf = ValidatorFramework()
result = vf.run()
# Must pass: Sharpe>2.0, PF>2.0, MDD<5%, WFE>0.85, MC>95%, RoR<1%
```

---

## 📊 EXPECTED RESULTS

### Feature Pipeline Output (H1)
- Train: 26,014 bars × ~50 features (after selection)
- Val: 5,505 bars × ~50 features
- Test: 5,505 bars × ~50 features
- Total: ~37K bars ready for training

### Training Targets
- target_ret_1: next 1-bar return (primary)
- target_ret_5: next 5-bar return
- target_ret_15: next 15-bar return
- target_ret_60: next 60-bar return

### Model Architecture (architect's design)
- XGBoost: gradient-boosted trees (214 lines)
- LSTM: 2 layers, 128 hidden (230 lines)
- Transformer: 8 heads, 6 layers (254 lines)
- Ensemble: weighted voting + Meta-Bandit (410 lines)

---

## 🔒 SECURITY NOTES

### GitHub Token
- Old token: `github_pat_11BZIGHBA0UQTdrkCfF2wr_...` (may expire)
- If push fails with 403, ask user for fresh PAT
- Token scope needed: `Contents: Read and write` + `Metadata: Read-only`
- Fine-grained PAT, repository access: only `TITAN_XAU_AI`

### Original Data Protection
- `titan/data/sources/mt5_brokers/` = READ-ONLY (never modify)
- `titan/data/canonical/` = preprocessed output (can regenerate)
- `titan/data/features/` = feature output (can regenerate)
- `titan/data/models/` = trained models (to be created)

---

## 📝 CONTEXT TO SHARE WITH NEXT SESSION

Paste this at the start of next session:

```
TITAN XAU AI project continue karna hai. GitHub repo:
https://github.com/ismailiqbal2773/TITAN_XAU_AI

Latest commit: 8687ed0 (feature pipeline adapter pushed)

NEXT_TASK: Feature pipeline run + save parquets, then STOP for training confirmation.

INSTRUCTIONS:
1. Clone repo to /tmp/titan_next
2. Read /tmp/titan_next/NEXT_SESSION_GUIDE.md for full steps
3. Follow Step 1-8 exactly
4. After Step 8, STOP and ask: "Should I start model training?"
5. Do NOT start training without user confirmation

ARCHITECT COMPLIANCE:
- Use titan/training/feature_engine.py (DO NOT MODIFY)
- 6 feature groups, 63 features
- Train-only scaler fit, purge=60, embargo=10
- 70/15/15 split

CRITICAL: Original broker data (titan/data/sources/mt5_brokers/) is READ-ONLY.
Never modify originals. All outputs go to separate folders.
```

---

## ✅ VERIFICATION CHECKLIST

Before ending this session, verify:
- [x] feature_pipeline.py committed + pushed to GitHub (commit 8687ed0)
- [x] NEXT_SESSION_GUIDE.md created (this file)
- [x] worklog.md updated with Task ID 17
- [x] All canonical datasets on GitHub
- [x] All preprocessing modules on GitHub
- [x] All MT5 broker data on GitHub
- [x] All audit reports on GitHub

Next session needs:
- [ ] Fresh GitHub PAT (if old one expired)
- [ ] Run feature_pipeline.py on 4 timeframes
- [ ] Save feature parquets
- [ ] Commit + push features
- [ ] STOP for training confirmation

---

END OF GUIDE
