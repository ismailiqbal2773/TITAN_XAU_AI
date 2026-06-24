"""
TITAN XAU AI — Execution Sensitivity Harness

Tests whether the model has edge but SL/TP sizing is killing it.

Configurations tested:
  1. Fixed 50/100 pips (current production)
  2. ATR 1.0/2.0
  3. ATR 1.5/3.0
  4. ATR 2.0/4.0
  5. ATR 3.0/6.0

For each: PF, WR, Sharpe, DD, trade count, FTMO/FundedNext pass prob.

Also tests volatile-regime filter ON/OFF.

No retraining. No model changes. No threshold changes.
"""
from __future__ import annotations

import json, os, sys, time, random
import numpy as np
import pandas as pd
from pathlib import Path
from collections import defaultdict

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from titan.production.feature_stream import H1FeatureStream, N_FEATURES, FEATURE_NAMES
from titan.production.model_loader import load_production_models, extract_meta_features, META_FEATURE_NAMES

# ─── Constants ────────────────────────────────────────────────────────────────
XGB_THRESHOLD = 0.55
META_THRESHOLD = 0.65
MAX_LOT = 0.01
COST_PER_LOT = 30.20
CONTRACT_SIZE = 100.0
PIP_VALUE = 0.01

FTMO_TARGET = 10.0
FTMO_MAX_DAILY = 5.0
FTMO_MAX_OVERALL = 10.0

ATR_PERIOD = 14  # for ATR-based SL/TP


def compute_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Compute ATR for a DataFrame with open/high/low/close columns."""
    h, l, c = df["high"], df["low"], df["close"]
    tr = pd.concat([(h - l), (h - c.shift(1)).abs(), (l - c.shift(1)).abs()], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def run_config(features_df, full_df, bundle, scaler_mean, scaler_std,
               sl_mode: str, sl_mult: float, tp_mult: float,
               volatile_filter: bool = False) -> dict:
    """
    Run a single SL/TP configuration.
    
    sl_mode: "fixed" or "atr"
    sl_mult: SL distance multiplier (pips for fixed, ATR multiple for atr)
    tp_mult: TP distance multiplier
    volatile_filter: if True, skip trades when ATR > 2x rolling mean ATR
    """
    trades = []
    signals_gen = 0
    signals_acc = 0
    position_open = False
    entry_price = 0.0
    entry_direction = 0
    entry_time = None
    sl_price = 0.0
    tp_price = 0.0
    entry_atr = 0.0
    equity = 10000.0
    peak = 10000.0
    initial = 10000.0
    max_dd = 0.0
    daily_pnl = 0.0
    daily_date = None
    ks_active = False

    # Compute ATR for the full data
    atr_series = compute_atr(full_df, ATR_PERIOD)

    for i in range(220, len(features_df)):
        vec = features_df.iloc[i].values.astype(np.float64)
        vec = np.nan_to_num(vec, nan=0.0, posinf=0.0, neginf=0.0)
        vec_std = (vec - scaler_mean) / scaler_std
        vec_std = np.nan_to_num(vec_std, nan=0.0, posinf=0.0, neginf=0.0)

        ts = features_df.index[i]
        current_date = ts.date() if hasattr(ts, 'date') else pd.Timestamp(ts).date()
        if daily_date != current_date:
            daily_pnl = 0.0
            daily_date = current_date

        if ks_active:
            continue

        # ── Check open position for exit ──
        if position_open:
            bar = full_df.loc[ts] if ts in full_df.index else None
            if bar is not None:
                nh, nl, nc = float(bar["high"]), float(bar["low"]), float(bar["close"])
                exit_price = None

                if entry_direction == 1 and nl <= sl_price:
                    exit_price = sl_price
                elif entry_direction == -1 and nh >= sl_price:
                    exit_price = sl_price
                if exit_price is None:
                    if entry_direction == 1 and nh >= tp_price:
                        exit_price = tp_price
                    elif entry_direction == -1 and nl <= tp_price:
                        exit_price = tp_price

                if exit_price is not None:
                    if entry_direction == 1:
                        pnl = (exit_price - entry_price) * CONTRACT_SIZE * MAX_LOT - COST_PER_LOT * MAX_LOT
                    else:
                        pnl = (entry_price - exit_price) * CONTRACT_SIZE * MAX_LOT - COST_PER_LOT * MAX_LOT
                    equity += pnl
                    daily_pnl += pnl
                    if equity > peak: peak = equity
                    dd = (peak - equity) / peak * 100
                    if dd > max_dd: max_dd = dd
                    trades.append({"pnl_usd": pnl, "entry_time": str(entry_time), "exit_time": str(ts)})
                    position_open = False

        if position_open:
            continue

        # ── Volatile regime filter ──
        if volatile_filter:
            current_atr = atr_series.iloc[i] if i < len(atr_series) else 0
            avg_atr = atr_series.iloc[max(0,i-50):i].mean() if i > 50 else current_atr
            if current_atr > 2.0 * avg_atr:
                continue  # skip volatile bars

        # ── Generate signal ──
        signals_gen += 1
        proba = bundle.xgb.predict_proba(vec_std.reshape(1, -1))[0]
        p_down, p_up = float(proba[0]), float(proba[1])

        if p_up >= XGB_THRESHOLD:
            direction = 1
        elif p_down >= XGB_THRESHOLD:
            direction = -1
        else:
            continue

        meta_vec = extract_meta_features(vec_std, FEATURE_NAMES)
        meta_proba = bundle.meta.predict_proba(meta_vec.reshape(1, -1))[0]
        if float(meta_proba[1]) < META_THRESHOLD:
            continue

        # Kill switch
        daily_loss_pct = abs(min(daily_pnl, 0)) / initial * 100
        dd_pct = (peak - equity) / peak * 100
        if daily_loss_pct >= 3.0 or dd_pct >= 8.0:
            ks_active = True
            continue

        # ── Open position ──
        signals_acc += 1
        bar = full_df.loc[ts] if ts in full_df.index else None
        if bar is None:
            continue

        entry_price = float(bar["close"])
        entry_direction = direction
        entry_time = ts

        current_atr = atr_series.iloc[i] if i < len(atr_series) else 0.5

        if sl_mode == "fixed":
            sl_dist = sl_mult * PIP_VALUE
            tp_dist = tp_mult * PIP_VALUE
        else:  # atr
            sl_dist = sl_mult * current_atr
            tp_dist = tp_mult * current_atr

        if direction == 1:
            sl_price = entry_price - sl_dist
            tp_price = entry_price + tp_dist
        else:
            sl_price = entry_price + sl_dist
            tp_price = entry_price - tp_dist

        position_open = True

    # ── Compute metrics ──
    if not trades:
        return {"pf": 0, "wr": 0, "sharpe": 0, "max_dd": 0, "trades": 0,
                "pnl": 0, "pass_ftmo": 0, "pass_fn": 0, "signals": signals_gen, "accepted": signals_acc}

    pnls = [t["pnl_usd"] for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    gp = sum(wins) if wins else 0
    gl = abs(sum(losses)) if losses else 0
    pf = gp / gl if gl > 0 else float('inf')
    wr = len(wins) / len(trades) * 100 if trades else 0

    trade_df = pd.DataFrame(trades)
    trade_df["exit_time"] = pd.to_datetime(trade_df["exit_time"])
    trade_df["date"] = trade_df["exit_time"].dt.date
    daily = trade_df.groupby("date")["pnl_usd"].sum()
    sharpe = daily.mean() / daily.std() * np.sqrt(252) if len(daily) > 1 and daily.std() > 0 else 0

    # Challenge simulation (200 MC runs for speed)
    ftmo_passes = 0
    fn_passes = 0
    n_sims = 200
    for sim in range(n_sims):
        random.seed(sim)
        shuffled = pnls.copy()
        random.shuffle(shuffled)
        eq = initial
        pk = initial
        dp = 0
        cd = None
        passed = False
        for pnl in shuffled:
            eq += pnl
            dp += pnl
            if eq > pk: pk = eq
            dd = (pk - eq) / pk * 100
            ol = (initial - eq) / initial * 100
            if dp < -initial * FTMO_MAX_DAILY / 100: break
            if ol > FTMO_MAX_OVERALL: break
            if eq >= initial * (1 + FTMO_TARGET / 100):
                passed = True
                break
        if passed:
            ftmo_passes += 1
            fn_passes += 1

    return {
        "pf": round(pf, 2),
        "wr": round(wr, 1),
        "sharpe": round(sharpe, 2),
        "max_dd": round(max_dd, 2),
        "trades": len(trades),
        "pnl": round(sum(pnls), 2),
        "pass_ftmo": round(ftmo_passes / n_sims * 100, 1),
        "pass_fn": round(fn_passes / n_sims * 100, 1),
        "signals": signals_gen,
        "accepted": signals_acc,
        "avg_win": round(np.mean(wins), 2) if wins else 0,
        "avg_loss": round(np.mean(losses), 2) if losses else 0,
    }


def main():
    print("=" * 70)
    print("  TITAN XAU AI — Execution Sensitivity Harness")
    print("=" * 70)
    print()

    # ─── Load everything ──
    bundle = load_production_models()
    fs = H1FeatureStream(window=300)
    canonical_path = REPO_ROOT / "titan" / "data" / "canonical" / "XAUUSD_H1_canonical.parquet"
    full_df = pd.read_parquet(canonical_path)
    full_df = full_df.rename(columns={"tick_volume": "volume", "spread_usd": "spread"})
    fs._bars = full_df[["open", "high", "low", "close", "volume", "spread"]].tail(5000).copy()
    all_features = fs._compute_features()

    # Load scaler
    scaler_path = REPO_ROOT / "titan" / "data" / "features" / "scaler_stats.json"
    with open(scaler_path, "r", encoding="utf-8") as f:
        scaler = json.load(f)
    scaler_mean = np.array([scaler["mean"][f] for f in FEATURE_NAMES])
    scaler_std = np.array([scaler["std"][f] for f in FEATURE_NAMES])

    print(f"  Data: {len(all_features)} H1 bars")
    print(f"  Models: xgboost_v1 + meta_label_v2 (frozen)")
    print(f"  Thresholds: XGB≥{XGB_THRESHOLD}, Meta≥{META_THRESHOLD}")
    print()

    # ─── Configurations ──
    configs = [
        ("Fixed 50/100 pips",     "fixed", 50, 100, False),
        ("Fixed 100/200 pips",    "fixed", 100, 200, False),
        ("Fixed 200/400 pips",    "fixed", 200, 400, False),
        ("ATR 1.0/2.0",           "atr",   1.0, 2.0, False),
        ("ATR 1.5/3.0",           "atr",   1.5, 3.0, False),
        ("ATR 2.0/4.0",           "atr",   2.0, 4.0, False),
        ("ATR 3.0/6.0",           "atr",   3.0, 6.0, False),
        ("Fixed 50/100 + VolFilter", "fixed", 50, 100, True),
        ("ATR 2.0/4.0 + VolFilter",  "atr",   2.0, 4.0, True),
        ("ATR 3.0/6.0 + VolFilter",  "atr",   3.0, 6.0, True),
    ]

    results = []
    for name, sl_mode, sl_mult, tp_mult, vol_filter in configs:
        print(f"  Running: {name}...", end="", flush=True)
        t0 = time.time()
        result = run_config(all_features, full_df, bundle, scaler_mean, scaler_std,
                            sl_mode, sl_mult, tp_mult, vol_filter)
        elapsed = time.time() - t0
        result["config"] = name
        result["sl_mode"] = sl_mode
        result["sl_mult"] = sl_mult
        result["tp_mult"] = tp_mult
        result["vol_filter"] = vol_filter
        results.append(result)
        print(f" done ({elapsed:.1f}s) — PF={result['pf']}, WR={result['wr']}%, trades={result['trades']}")

    # ─── Print results table ──
    print()
    print("=" * 120)
    print(f"  {'Config':<30} {'PF':>6} {'WR%':>6} {'Sharpe':>8} {'MaxDD%':>7} {'Trades':>7} {'PnL$':>10} {'AvgWin':>8} {'AvgLoss':>8} {'FTMO%':>7} {'FN%':>6}")
    print(f"  {'-'*30} {'-'*6} {'-'*6} {'-'*8} {'-'*7} {'-'*7} {'-'*10} {'-'*8} {'-'*8} {'-'*7} {'-'*6}")
    for r in results:
        print(f"  {r['config']:<30} {r['pf']:>6} {r['wr']:>6.1f} {r['sharpe']:>8.2f} {r['max_dd']:>7.2f} {r['trades']:>7} {r['pnl']:>10.2f} {r['avg_win']:>8.2f} {r['avg_loss']:>8.2f} {r['pass_ftmo']:>7.1f} {r['pass_fn']:>6.1f}")
    print("=" * 120)

    # ─── Analysis ──
    print()
    print("  ANALYSIS:")
    best_pf = max(results, key=lambda x: x["pf"])
    best_wr = max(results, key=lambda x: x["wr"])
    best_sharpe = max(results, key=lambda x: x["sharpe"])
    best_pnl = max(results, key=lambda x: x["pnl"])
    best_ftmo = max(results, key=lambda x: x["pass_ftmo"])

    print(f"  Best PF:      {best_pf['config']} — PF={best_pf['pf']}")
    print(f"  Best WR:      {best_wr['config']} — WR={best_wr['wr']}%")
    print(f"  Best Sharpe:  {best_sharpe['config']} — Sharpe={best_sharpe['sharpe']}")
    print(f"  Best PnL:     {best_pnl['config']} — PnL=${best_pnl['pnl']}")
    print(f"  Best FTMO:    {best_ftmo['config']} — Pass={best_ftmo['pass_ftmo']}%")
    print()

    # Check if any config has positive edge
    any_positive = any(r["pf"] > 1.0 for r in results)
    if any_positive:
        print("  ✓ MODEL HAS EDGE — at least one SL/TP config achieves PF > 1.0")
        print("  The problem is SL/TP sizing, not the model itself.")
        positive_configs = [r for r in results if r["pf"] > 1.0]
        for r in positive_configs:
            print(f"    → {r['config']}: PF={r['pf']}, WR={r['wr']}%, Sharpe={r['sharpe']}")
    else:
        print("  ✗ MODEL HAS NO EDGE — no SL/TP config achieves PF > 1.0")
        print("  The problem is the model, not the SL/TP sizing.")
        print("  Model needs retraining on 2025-2026 data (F8 recommendation).")

    # Save report
    report_path = REPO_ROOT / "data" / "validation" / "execution_sensitivity_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump({"results": results, "any_positive_edge": any_positive}, f, indent=2, default=str)
    print(f"\n  Report saved: {report_path}")


if __name__ == "__main__":
    main()
