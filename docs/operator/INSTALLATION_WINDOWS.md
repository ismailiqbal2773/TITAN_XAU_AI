# TITAN XAU AI — Windows Installation Guide

**Sprint v2.8.7-F**
**Status: SKELETON — Not for production use**

## Prerequisites

### Required Software
1. **Python 3.10+** (3.12 recommended)
   - Download from https://python.org
   - Check "Add Python to PATH" during installation

2. **MetaTrader 5 Terminal** (for live data, Windows only)
   - Download from your broker (Exness, FBS, ICMarkets, etc.)
   - Install and login to your demo account

3. **Git** (for cloning the repository)
   - Download from https://git-scm.com

### Required Python Packages
```
pip install pandas numpy scikit-learn xgboost pyarrow MetaTrader5 pyyaml
```

## Installation Steps

### Step 1: Clone Repository
```cmd
git clone https://github.com/ismailiqbal2773/TITAN_XAU_AI.git
cd TITAN_XAU_AI
```

### Step 2: Install Dependencies
```cmd
pip install -r requirements.txt
```

### Step 3: Verify Installation
```cmd
python -c "from titan.production.model_loader import load_production_models; b = load_production_models(); print(f'Models loaded: {b.ok}')"
```

### Step 4: Verify Safety State
```cmd
python -c "
from titan.production.model_registry import get_default_profile_name
print(f'Default profile: {get_default_profile_name()}')
assert get_default_profile_name() == 'v1_legacy'
print('Safety check: PASS')
"
```

### Step 5: Run Commercial MVP Readiness Audit
```cmd
python scripts/audit/final_commercial_mvp_readiness_audit.py
```

## Configuration

### Commercial Profile
Edit `config/commercial_profile.yaml`:
- Set `license_key` (when available)
- Set `expiry_date` (when available)
- Set `machine_id` (when bound)
- Keep `dry_run: true`, `live_trading: false`, `funded_trading: false`

### License Policy
Edit `config/license_policy.yaml`:
- Configure tier settings (when activated)
- Keep `block_live_without_license: true`
- Keep `block_funded_without_license: true`

## MT5 Data Acquisition

### Acquire Historical Data
```cmd
python scripts/real_data/titan_mt5_acquire.py
```

This script:
- Connects to MT5 terminal
- Downloads XAUUSD M1/M5/M15/M30/H1 data
- Saves to `titan_mt5_data/` folder
- Generates verification JSON

### Verify Data
```cmd
python scripts/real_data/comprehensive_audit.py
```

## Running Research (No Trade)

### Parameter Discovery
```cmd
python scripts/research/run_safe_parameter_discovery.py --model-profile v2_feature_normalized --mode fast --max-candidates 50 --early-stop --progress-every 1 --profile prop_funded_safe --risk-percent-grid 0.0025,0.005 --max-lot 0.01 --timeframes H1,M15,M5 --brokers canonical,exness,fbs,fundednext,icmarkets --include-dukascopy --conservative
```

### Broker Generalization Audit
```cmd
python scripts/research/run_broker_generalization_audit_v2.py
```

### OOS Collapse Diagnosis
```cmd
python scripts/research/run_oos_collapse_diagnosis.py
```

## Troubleshooting

### MT5 Not Connecting
- Ensure MT5 terminal is running
- Check your internet connection
- Verify broker server is accessible
- Try restarting MT5 terminal

### Models Not Loading
- Check `titan/data/models/` directory
- Verify model files exist (xgboost_v1.pkl, etc.)
- Check Python version compatibility

### Memory Errors
- Reduce `--max-candidates` to 30 or less
- Reduce number of brokers to 3
- Close other applications
- Use a machine with >=8GB RAM for full 5-broker sweeps

## Safety Checklist

Before running ANY script:

- [ ] `dry_run` is true in config
- [ ] `live_trading` is false in config
- [ ] `funded_trading` is false in config
- [ ] `production_ready` is false
- [ ] No execution tokens created
- [ ] Broker is MetaQuotes-Demo (not live/funded)
- [ ] CTO has reviewed the runbook

## Support

For issues:
1. Check the worklog at `worklog.md`
2. Review audit reports in `data/reports/`
3. Contact the development team

## No Trade Policy

**This software does NOT trade.** It is research-only. No live trading,
no funded trading, no automated execution. All trades require explicit
operator action and CTO approval.
