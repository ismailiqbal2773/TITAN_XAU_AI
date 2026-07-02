# TITAN XAU AI - Backtest Parameter Binding Report

**Verdict:** **BACKTEST_BINDING_READY_WITH_GAPS**

**Timestamp:** 2026-07-02T07:21:54.824953+00:00

## Summary

| Metric | Value |
|---|---|
| Total parameters checked | 32 |
| Parameters bound | 15 |
| Parameters safe default | 17 |
| Parameters needs review | 0 |
| Critical parameters unbound | 0 |
| Artifacts scanned | 269 |
| Score impact | Score capped at 92 due to 17 safe defaults |

## Artifact Paths Used

- `/home/z/my-project/TITAN_XAU_AI/data/validation/atr_execution_validation_report.json`
- `/home/z/my-project/TITAN_XAU_AI/data/audit/virtual_lifecycle/virtual_lifecycle_report.json`
- `/home/z/my-project/TITAN_XAU_AI/data/audit/frozen_balanced_validation/broker_validation.csv`
- `/home/z/my-project/TITAN_XAU_AI/config/runtime.yaml`
- `/home/z/my-project/TITAN_XAU_AI/data/audit/demo_micro/pass_evidence/metaquotes-demo/20260702T072046Z/broker_execution_profile.json`
- `/home/z/my-project/TITAN_XAU_AI/data/audit/parameter_optimization/best_parameter_sets.csv`
- `/home/z/my-project/TITAN_XAU_AI/titan/data/models/xgboost_v1.pkl`
- `/home/z/my-project/TITAN_XAU_AI/titan/data/hpo/best_params_xgb.json`

## Parameter Details

| Parameter | Value | Source | Critical | Status | Metric |
|---|---|---|---|---|---|
| atr_sl_multiplier | 1.5 | BACKTEST_VALIDATED | YES | VALIDATED | PF=1.63, Sharpe=3.33, Sortino=16.97, MaxDD=1.52%, Trades=183 |
| tp_multiplier_initial_tp_R | 3.0 | BACKTEST_VALIDATED | YES | VALIDATED | PF=1.63, Sharpe=3.33, Sortino=16.97, MaxDD=1.52%, Trades=183 |
| minimum_RR | 2.0 | BACKTEST_VALIDATED | YES | VALIDATED | PF=1.63, Sharpe=3.33, Sortino=16.97, MaxDD=1.52%, Trades=183 |
| dynamic_tp_trigger_R | 2.0 | BACKTEST_VALIDATED | YES | VALIDATED | avg_monthly=5.18%, PF=inf, WR=72.37%, MaxDD=4.51%, verdict=R |
| breakeven_trigger_R | 1.0 | SAFE_DEFAULT | no | NEEDS_BACKTEST_BINDING |  |
| trailing_trigger_R | 1.75 | SAFE_DEFAULT | no | NEEDS_BACKTEST_BINDING |  |
| profit_lock_trigger_R | 3.0 | SAFE_DEFAULT | no | NEEDS_BACKTEST_BINDING |  |
| tp_extension_trigger_R | 2.0 | SAFE_DEFAULT | no | NEEDS_BACKTEST_BINDING |  |
| tp_extension_R | 1.0 | SAFE_DEFAULT | no | NEEDS_BACKTEST_BINDING |  |
| tp_extension_atr_mult | 2.0 | SAFE_DEFAULT | no | NEEDS_BACKTEST_BINDING |  |
| trend_atr_multiplier | 2.0 | SAFE_DEFAULT | no | NEEDS_BACKTEST_BINDING |  |
| range_atr_multiplier | 1.0 | SAFE_DEFAULT | no | NEEDS_BACKTEST_BINDING |  |
| high_vol_atr_multiplier | 2.5 | SAFE_DEFAULT | no | NEEDS_BACKTEST_BINDING |  |
| min_hold_seconds | 60 | SAFE_DEFAULT | no | NEEDS_BACKTEST_BINDING |  |
| min_monitor_iterations | 3 | SAFE_DEFAULT | no | NEEDS_BACKTEST_BINDING |  |
| sl_update_cooldown_seconds | 60 | SAFE_DEFAULT | no | NEEDS_BACKTEST_BINDING |  |
| tp_extension_cooldown_seconds | 120 | SAFE_DEFAULT | no | NEEDS_BACKTEST_BINDING |  |
| locked_R | 1.2 | SAFE_DEFAULT | no | NEEDS_BACKTEST_BINDING |  |
| breakeven_buffer_R | 0.1 | SAFE_DEFAULT | no | NEEDS_BACKTEST_BINDING |  |
| risk_per_trade_pct | 0.0075 | BACKTEST_VALIDATED | YES | VALIDATED | avg_monthly=5.18%, PF=inf, WR=72.37%, MaxDD=4.51%, verdict=R |
| max_daily_dd_pct | 0.03 | BROKER_SPLIT_VALIDATED | YES | VALIDATED | avg_monthly=8.7%, PF=4.85, WR=65.45%, MaxDD=8.39%, verdict=P |
| max_total_dd_pct | 0.08 | BROKER_SPLIT_VALIDATED | YES | VALIDATED | avg_monthly=8.7%, PF=4.85, WR=65.45%, MaxDD=8.39%, verdict=P |
| max_lot | 0.01 | SAFE_DEFAULT | no | NEEDS_BACKTEST_BINDING |  |
| confidence_threshold | 0.5 | HPO_VALIDATED | YES | VALIDATED | max_depth=7, lr=0.01754437325582038, n_est=397 |
| target_net_RR | 3.0 | BACKTEST_VALIDATED | no | VALIDATED | closed=17, net_pnl=44.1, WR=52.94%, PF=1.85 |
| max_spread_threshold | 0.35 | BROKER_SPLIT_VALIDATED | YES | VALIDATED | spread=0.35, slippage=0.02, verdict=SUCCESS |
| max_slippage_threshold | 0.02 | BROKER_SPLIT_VALIDATED | YES | VALIDATED | spread=0.35, slippage=0.02, verdict=SUCCESS |
| commission_assumption | 7.0 | SAFE_DEFAULT | no | NEEDS_BACKTEST_BINDING |  |
| spread_cost_assumption | 0.35 | BROKER_SPLIT_VALIDATED | no | VALIDATED | spread=0.35, slippage=0.02, verdict=SUCCESS |
| timeframe | H1 | BACKTEST_VALIDATED | no | VALIDATED | timeframe=H1 |
| model_family | xgboost | BACKTEST_VALIDATED | no | VALIDATED | size=1930KB |
| model_version | v1 | BACKTEST_VALIDATED | no | VALIDATED | size=1930KB |
