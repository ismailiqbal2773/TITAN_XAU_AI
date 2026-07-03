# TITAN XAU AI — MTF M5/M15/H1 Validation Runbook (v2.8.6)

## Architecture

```
Regime Detection
  → Timeframe / Strategy Mode Selection
  → H1 Context (higher timeframe bias)
  → M15 Confirmation (setup/structure)
  → M5 Entry Timing (trigger/momentum)
  → Alpha Direction / Edge (XGBoost, threshold 0.55)
  → Meta-label Trade Quality (LogisticRegression, threshold 0.65)
  → CEO Governance (final approval/block)
  → Risk / Prop / Broker / Geometry Gates
  → Supervised Token-Gated Execution
```

## Timeframe Roles

| Timeframe | Role | Model | Notes |
|-----------|------|-------|-------|
| H1 | Higher timeframe context/bias | XGBoost + meta-label (validated) | 55 features, standardized |
| M15 | Setup confirmation | Rule-based (no separate model) | Candle direction, SMA(10), spread |
| M5 | Entry timing trigger | Rule-based (no separate model) | Momentum, wick check, spread |

## Safety Rules

- Alpha threshold: 0.55 (NEVER lowered)
- Meta-label threshold: 0.65 (NEVER lowered)
- CEO must approve before any execution
- M5/M15 are rule-based confirmation only (no separate trained models)
- cached_fallback signal CANNOT pass
- No martingale/grid/averaging/loss multiplier
- Max lot 0.01 (DEMO_SAFE cap)
- Daily DD: 1% soft, 2% hard
- Total DD cap: 8%
- RR minimum: 2.0, preferred: 3.0

## Commands

### Offline Reality-Close Report

```powershell
python scripts/research/run_mtf_reality_close_report.py --profile prop_funded_safe --risk-percent 0.005 --max-lot 0.01 --conservative --timeframes H1,M15,M5
```

### Live Read-Only Build-Request (MTF mode)

```powershell
python scripts/operator/run_managed_demo_micro_trade.py --build-request --timeframe-mode mtf_m5_m15_h1 --prop-funded-profile prop_funded_safe --use-adaptive-trailing --use-dynamic-tp-extension
```

### Live Read-Only Build-Request (H1-only mode, default)

```powershell
python scripts/operator/run_managed_demo_micro_trade.py --build-request --prop-funded-profile prop_funded_safe --use-adaptive-trailing --use-dynamic-tp-extension
```

## GO/NO-GO Conditions

**GO (build-request PASS):**
- signal_source = live_mt5_fresh
- is_fresh_signal = True
- cache_used = False
- regime_policy_allowed = True
- h1_context_pass = True
- m15_confirmation_pass = True
- m5_entry_trigger_pass = True
- alpha_pass = True (confidence >= 0.55)
- meta_label_pass = True (confidence >= 0.65)
- CEO allowed_to_trade = True
- execution_now_allowed = False
- execution_blocker = OPERATOR_ARM_TOKEN_REQUIRED

**NO-GO (build-request BLOCKED):**
- Any of the above conditions not met
- Cached or partial signal
- Regime blocked (holiday/dead market/spread expansion)
- Alpha or meta-label below threshold
- CEO blocked

## Disclaimer

Backtest estimate is not a guarantee. Forward demo still required.
Token/trade allowed only after final activation READY_SUPERVISED.
