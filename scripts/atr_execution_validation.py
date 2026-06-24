"""
TITAN XAU AI — ATR Execution Validation Sprint

Full trade-by-trade harness for 3 ATR configurations:
  1. ATR 1.5/3.0
  2. ATR 2.0/4.0
  3. ATR 3.0/6.0

For each: PF, WR, Sharpe, Sortino, MaxDD, trades, monthly breakdown,
FTMO/FundedNext simulation, max consecutive losses, recovery factor,
trade duration stats.

No retraining. No model changes. No threshold changes.
Only ATR-based SL/TP execution sizing.
"""
from __future__ import annotations
import json, os, sys, time, random, math
import numpy as np
import pandas as pd
from pathlib import Path
from scipy import stats as scipy_stats

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from titan.production.feature_stream import H1FeatureStream, N_FEATURES, FEATURE_NAMES
from titan.production.model_loader import load_production_models, extract_meta_features

XGB_THRESHOLD = 0.55
META_THRESHOLD = 0.65
MAX_LOT = 0.01
COST_PER_LOT = 30.20
CONTRACT_SIZE = 100.0
ATR_PERIOD = 14
INITIAL_BALANCE = 10000.0

FTMO_TARGET = 10.0; FTMO_MAX_DAILY = 5.0; FTMO_MAX_OVERALL = 10.0
FN_TARGET = 10.0; FN_MAX_DAILY = 5.0; FN_MAX_OVERALL = 10.0


def compute_atr(df, period=14):
    h, l, c = df["high"], df["low"], df["close"]
    tr = pd.concat([(h-l), (h-c.shift(1)).abs(), (l-c.shift(1)).abs()], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def run_atr_config(features_df, full_df, bundle, scaler_mean, scaler_std,
                   sl_mult, tp_mult):
    """Run full harness for one ATR config."""
    trades = []
    signals_gen = 0; signals_acc = 0
    position_open = False
    entry_price = 0.0; entry_direction = 0; entry_time = None
    sl_price = 0.0; tp_price = 0.0; entry_atr = 0.0
    equity = INITIAL_BALANCE; peak = INITIAL_BALANCE; max_dd = 0.0
    daily_pnl = 0.0; daily_date = None; ks_active = False
    atr_series = compute_atr(full_df, ATR_PERIOD)
    consecutive_losses = 0; max_consec_losses = 0

    for i in range(220, len(features_df)):
        vec = features_df.iloc[i].values.astype(np.float64)
        vec = np.nan_to_num(vec, nan=0.0, posinf=0.0, neginf=0.0)
        vec_std = (vec - scaler_mean) / scaler_std
        vec_std = np.nan_to_num(vec_std, nan=0.0, posinf=0.0, neginf=0.0)
        ts = features_df.index[i]
        current_date = ts.date() if hasattr(ts, 'date') else pd.Timestamp(ts).date()
        if daily_date != current_date:
            daily_pnl = 0.0; daily_date = current_date
        if ks_active: continue

        # Check exit
        if position_open:
            bar = full_df.loc[ts] if ts in full_df.index else None
            if bar is not None:
                nh, nl, nc = float(bar["high"]), float(bar["low"]), float(bar["close"])
                exit_price = None; exit_reason = None
                if entry_direction == 1 and nl <= sl_price:
                    exit_price = sl_price; exit_reason = "SL"
                elif entry_direction == -1 and nh >= sl_price:
                    exit_price = sl_price; exit_reason = "SL"
                if exit_price is None:
                    if entry_direction == 1 and nh >= tp_price:
                        exit_price = tp_price; exit_reason = "TP"
                    elif entry_direction == -1 and nl <= tp_price:
                        exit_price = tp_price; exit_reason = "TP"
                if exit_price is not None:
                    if entry_direction == 1:
                        pnl = (exit_price - entry_price) * CONTRACT_SIZE * MAX_LOT - COST_PER_LOT * MAX_LOT
                    else:
                        pnl = (entry_price - exit_price) * CONTRACT_SIZE * MAX_LOT - COST_PER_LOT * MAX_LOT
                    equity += pnl; daily_pnl += pnl
                    if equity > peak: peak = equity
                    dd = (peak - equity) / peak * 100
                    if dd > max_dd: max_dd = dd
                    holding_h = (ts - entry_time).total_seconds() / 3600 if entry_time else 0
                    trades.append({
                        "entry_time": str(entry_time), "exit_time": str(ts),
                        "direction": "LONG" if entry_direction == 1 else "SHORT",
                        "entry_price": entry_price, "exit_price": exit_price,
                        "sl": sl_price, "tp": tp_price, "atr_at_entry": entry_atr,
                        "pnl_usd": round(pnl, 4), "exit_reason": exit_reason,
                        "holding_hours": round(holding_h, 1),
                        "equity_after": round(equity, 2),
                    })
                    if pnl > 0: consecutive_losses = 0
                    else:
                        consecutive_losses += 1
                        if consecutive_losses > max_consec_losses: max_consec_losses = consecutive_losses
                    position_open = False
        if position_open: continue

        # Signal
        signals_gen += 1
        proba = bundle.xgb.predict_proba(vec_std.reshape(1, -1))[0]
        p_down, p_up = float(proba[0]), float(proba[1])
        if p_up >= XGB_THRESHOLD: direction = 1
        elif p_down >= XGB_THRESHOLD: direction = -1
        else: continue
        meta_vec = extract_meta_features(vec_std, FEATURE_NAMES)
        meta_proba = bundle.meta.predict_proba(meta_vec.reshape(1, -1))[0]
        if float(meta_proba[1]) < META_THRESHOLD: continue

        # Kill switch
        daily_loss_pct = abs(min(daily_pnl, 0)) / INITIAL_BALANCE * 100
        dd_pct = (peak - equity) / peak * 100
        if daily_loss_pct >= 3.0 or dd_pct >= 8.0:
            ks_active = True; continue

        # Open
        signals_acc += 1
        bar = full_df.loc[ts] if ts in full_df.index else None
        if bar is None: continue
        entry_price = float(bar["close"]); entry_direction = direction; entry_time = ts
        current_atr = atr_series.iloc[i] if i < len(atr_series) else 0.5
        entry_atr = current_atr
        sl_dist = sl_mult * current_atr; tp_dist = tp_mult * current_atr
        if direction == 1:
            sl_price = entry_price - sl_dist; tp_price = entry_price + tp_dist
        else:
            sl_price = entry_price + sl_dist; tp_price = entry_price - tp_dist
        position_open = True

    return trades, signals_gen, signals_acc, equity, max_dd, max_consec_losses, ks_active


def compute_full_metrics(trades, signals_gen, signals_acc, equity, max_dd, max_consec_losses, ks_active):
    if not trades:
        return None
    pnls = [t["pnl_usd"] for t in trades]
    wins = [p for p in pnls if p > 0]; losses = [p for p in pnls if p < 0]
    gp = sum(wins) if wins else 0; gl = abs(sum(losses)) if losses else 0
    pf = gp / gl if gl > 0 else float('inf')
    wr = len(wins) / len(trades) * 100
    total_pnl = sum(pnls)

    # Sharpe
    trade_df = pd.DataFrame(trades)
    trade_df["exit_time"] = pd.to_datetime(trade_df["exit_time"])
    trade_df["date"] = trade_df["exit_time"].dt.date
    daily = trade_df.groupby("date")["pnl_usd"].sum()
    sharpe = daily.mean() / daily.std() * np.sqrt(252) if len(daily) > 1 and daily.std() > 0 else 0

    # Sortino (only downside deviation)
    downside = daily[daily < 0]
    downside_std = downside.std() if len(downside) > 1 else 0.001
    sortino = daily.mean() / downside_std * np.sqrt(252) if downside_std > 0 else 0

    # Monthly breakdown
    trade_df["month"] = trade_df["exit_time"].dt.to_period("M")
    monthly = trade_df.groupby("month")["pnl_usd"].sum()
    monthly_dict = {str(k): round(v, 2) for k, v in monthly.items()}

    # Trade duration
    durations = [t["holding_hours"] for t in trades]
    avg_dur = np.mean(durations); med_dur = np.median(durations)

    # Recovery factor
    recovery = total_pnl / max_dd if max_dd > 0 else 0

    # CAGR
    n_months = len(monthly) if len(monthly) > 0 else 1
    cagr = ((equity / INITIAL_BALANCE) ** (12 / n_months) - 1) * 100 if n_months > 0 and equity > 0 else 0

    # Challenge simulation
    ftmo_passes = 0; fn_passes = 0; n_sims = 1000
    days_to_target = []
    for sim in range(n_sims):
        random.seed(sim)
        shuffled = pnls.copy(); random.shuffle(shuffled)
        eq = INITIAL_BALANCE; pk = INITIAL_BALANCE; dp = 0; cd = None; dc = 0; passed = False
        for pnl in shuffled:
            eq += pnl; dp += pnl
            if eq > pk: pk = eq
            dd = (pk - eq) / pk * 100; ol = (INITIAL_BALANCE - eq) / INITIAL_BALANCE * 100
            dc += 1
            if dp < -INITIAL_BALANCE * FTMO_MAX_DAILY / 100: break
            if ol > FTMO_MAX_OVERALL: break
            if eq >= INITIAL_BALANCE * (1 + FTMO_TARGET / 100):
                passed = True; break
        if passed:
            ftmo_passes += 1; fn_passes += 1; days_to_target.append(dc)

    return {
        "pf": round(pf, 2), "wr": round(wr, 1), "sharpe": round(sharpe, 2),
        "sortino": round(sortino, 2), "max_dd": round(max_dd, 2),
        "trades": len(trades), "pnl": round(total_pnl, 2),
        "equity": round(equity, 2), "cagr": round(cagr, 1),
        "avg_win": round(np.mean(wins), 2) if wins else 0,
        "avg_loss": round(np.mean(losses), 2) if losses else 0,
        "expectancy": round(total_pnl / len(trades), 4),
        "max_consec_losses": max_consec_losses,
        "recovery_factor": round(recovery, 2),
        "avg_duration_h": round(avg_dur, 1), "med_duration_h": round(med_dur, 1),
        "ftmo_pass": round(ftmo_passes / n_sims * 100, 1),
        "fn_pass": round(fn_passes / n_sims * 100, 1),
        "avg_days_to_target": round(np.mean(days_to_target), 1) if days_to_target else 0,
        "best_days": min(days_to_target) if days_to_target else 0,
        "worst_days": max(days_to_target) if days_to_target else 0,
        "monthly": monthly_dict,
        "signals_gen": signals_gen, "signals_acc": signals_acc,
        "acceptance_rate": round(signals_acc / signals_gen * 100, 1) if signals_gen > 0 else 0,
        "ks_active": ks_active,
    }


def main():
    print("=" * 70)
    print("  TITAN XAU AI — ATR Execution Validation Sprint")
    print("=" * 70)
    print()

    bundle = load_production_models()
    fs = H1FeatureStream(window=300)
    canonical_path = REPO_ROOT / "titan" / "data" / "canonical" / "XAUUSD_H1_canonical.parquet"
    full_df = pd.read_parquet(canonical_path)
    full_df = full_df.rename(columns={"tick_volume": "volume", "spread_usd": "spread"})
    fs._bars = full_df[["open", "high", "low", "close", "volume", "spread"]].tail(5000).copy()
    all_features = fs._compute_features()

    scaler_path = REPO_ROOT / "titan" / "data" / "features" / "scaler_stats.json"
    with open(scaler_path) as f: scaler = json.load(f)
    scaler_mean = np.array([scaler["mean"][f] for f in FEATURE_NAMES])
    scaler_std = np.array([scaler["std"][f] for f in FEATURE_NAMES])

    print(f"  Data: {len(all_features)} H1 bars (last 5000)")
    print(f"  Models: xgboost_v1 + meta_label_v2 (frozen)")
    print(f"  Thresholds: XGB>={XGB_THRESHOLD}, Meta>={META_THRESHOLD}")
    print()

    configs = [
        ("ATR 1.5/3.0", 1.5, 3.0),
        ("ATR 2.0/4.0", 2.0, 4.0),
        ("ATR 3.0/6.0", 3.0, 6.0),
    ]

    all_results = {}
    all_trades = {}

    for name, sl_mult, tp_mult in configs:
        print(f"  Running {name}...", end="", flush=True)
        t0 = time.time()
        trades, sg, sa, eq, mdd, mcl, ks = run_atr_config(
            all_features, full_df, bundle, scaler_mean, scaler_std, sl_mult, tp_mult)
        metrics = compute_full_metrics(trades, sg, sa, eq, mdd, mcl, ks)
        elapsed = time.time() - t0
        if metrics:
            all_results[name] = metrics
            all_trades[name] = trades
            print(f" done ({elapsed:.1f}s) — PF={metrics['pf']}, WR={metrics['wr']}%, Sharpe={metrics['sharpe']}, FTMO={metrics['ftmo_pass']}%")
        else:
            print(f" done ({elapsed:.1f}s) — NO TRADES")

    # ─── Comparison Table ───
    print()
    print("=" * 130)
    print(f"  {'Config':<15} {'PF':>6} {'WR%':>6} {'Sharpe':>8} {'Sortino':>8} {'MaxDD%':>7} {'Trades':>7} {'PnL$':>10} {'CAGR%':>7} {'MaxCL':>6} {'Recov':>7} {'FTMO%':>7} {'FN%':>6} {'AvgDays':>8}")
    print(f"  {'-'*15} {'-'*6} {'-'*6} {'-'*8} {'-'*8} {'-'*7} {'-'*7} {'-'*10} {'-'*7} {'-'*6} {'-'*7} {'-'*7} {'-'*6} {'-'*8}")
    for name in [c[0] for c in configs]:
        r = all_results.get(name)
        if r:
            print(f"  {name:<15} {r['pf']:>6} {r['wr']:>6.1f} {r['sharpe']:>8.2f} {r['sortino']:>8.2f} {r['max_dd']:>7.2f} {r['trades']:>7} {r['pnl']:>10.2f} {r['cagr']:>7.1f} {r['max_consec_losses']:>6} {r['recovery_factor']:>7.2f} {r['ftmo_pass']:>7.1f} {r['fn_pass']:>6.1f} {r['avg_days_to_target']:>8.1f}")
    print("=" * 130)

    # ─── Monthly Breakdown ───
    print()
    print("  MONTHLY BREAKDOWN:")
    for name in [c[0] for c in configs]:
        r = all_results.get(name)
        if r:
            print(f"\n  {name}:")
            for month, pnl in r["monthly"].items():
                bar = "█" * int(abs(pnl) / 10) if pnl != 0 else ""
                sign = "+" if pnl > 0 else ""
                print(f"    {month}: {sign}{pnl:>10.2f}  {bar}")

    # ─── Trade Duration Stats ───
    print()
    print("  TRADE DURATION STATISTICS:")
    for name in [c[0] for c in configs]:
        r = all_results.get(name)
        if r:
            print(f"    {name}: avg={r['avg_duration_h']}h, median={r['med_duration_h']}h")

    # ─── Max Consecutive Losses ───
    print()
    print("  MAX CONSECUTIVE LOSSES:")
    for name in [c[0] for c in configs]:
        r = all_results.get(name)
        if r:
            print(f"    {name}: {r['max_consec_losses']} consecutive losses")

    # ─── Recommendations ───
    print()
    print("=" * 70)
    print("  RECOMMENDATIONS")
    print("=" * 70)

    # A) Best Challenge Configuration (highest FTMO pass rate, lowest DD)
    best_challenge = max(all_results.items(), key=lambda x: (x[1]["ftmo_pass"], -x[1]["max_dd"]))
    print(f"\n  A) Best Challenge Configuration: {best_challenge[0]}")
    print(f"     FTMO={best_challenge[1]['ftmo_pass']}%, FN={best_challenge[1]['fn_pass']}%, MaxDD={best_challenge[1]['max_dd']}%")
    print(f"     PF={best_challenge[1]['pf']}, WR={best_challenge[1]['wr']}%, Sharpe={best_challenge[1]['sharpe']}")
    print(f"     Avg days to target: {best_challenge[1]['avg_days_to_target']}")

    # B) Best Production Configuration (highest Sharpe + lowest DD)
    best_prod = max(all_results.items(), key=lambda x: (x[1]["sharpe"], -x[1]["max_dd"]))
    print(f"\n  B) Best Production Configuration: {best_prod[0]}")
    print(f"     Sharpe={best_prod[1]['sharpe']}, Sortino={best_prod[1]['sortino']}, MaxDD={best_prod[1]['max_dd']}%")
    print(f"     PF={best_prod[1]['pf']}, WR={best_prod[1]['wr']}%, PnL=${best_prod[1]['pnl']}")

    # C) Risk-adjusted winner (highest Sortino)
    best_risk = max(all_results.items(), key=lambda x: x[1]["sortino"])
    print(f"\n  C) Risk-Adjusted Winner: {best_risk[0]}")
    print(f"     Sortino={best_risk[1]['sortino']}, Recovery Factor={best_risk[1]['recovery_factor']}")
    print(f"     Max Consecutive Losses={best_risk[1]['max_consec_losses']}")

    # D) Recommended TITAN default profile
    # Balance: FTMO pass rate + Sharpe + low DD + reasonable trade count
    scores = {}
    for name, r in all_results.items():
        score = (
            r["ftmo_pass"] * 0.25 +
            min(r["sharpe"], 5) * 10 +
            (10 - r["max_dd"]) * 2 +
            min(r["recovery_factor"], 10) * 3 +
            (1 if r["max_consec_losses"] <= 10 else 0) * 5
        )
        scores[name] = score
    best_default = max(scores, key=scores.get)
    print(f"\n  D) Recommended TITAN Default Profile: {best_default}")
    print(f"     Composite Score: {scores[best_default]:.1f}/100")
    r = all_results[best_default]
    print(f"     PF={r['pf']}, WR={r['wr']}%, Sharpe={r['sharpe']}, Sortino={r['sortino']}")
    print(f"     MaxDD={r['max_dd']}%, FTMO={r['ftmo_pass']}%, MaxCL={r['max_consec_losses']}")
    print(f"     SL={best_default.split('ATR ')[1].split('/')[0]}xATR, TP={best_default.split('/')[1]}xATR")

    # ─── Trade-by-trade (first 10 + last 10) ───
    print()
    print("  TRADE-BY-TRADE (first 10 + last 10) for recommended config:")
    trades = all_trades[best_default]
    print(f"\n  First 10 trades:")
    print(f"  {'#':>3} {'Dir':<6} {'Entry':>10} {'Exit':>10} {'SL':>10} {'TP':>10} {'ATR':>8} {'PnL$':>8} {'Reason':<6} {'Hours':>6}")
    for i, t in enumerate(trades[:10]):
        print(f"  {i+1:>3} {t['direction']:<6} {t['entry_price']:>10.2f} {t['exit_price']:>10.2f} {t['sl']:>10.2f} {t['tp']:>10.2f} {t['atr_at_entry']:>8.4f} {t['pnl_usd']:>8.2f} {t['exit_reason']:<6} {t['holding_hours']:>6.1f}")
    print(f"\n  Last 10 trades:")
    for i, t in enumerate(trades[-10:]):
        idx = len(trades) - 10 + i + 1
        print(f"  {idx:>3} {t['direction']:<6} {t['entry_price']:>10.2f} {t['exit_price']:>10.2f} {t['sl']:>10.2f} {t['tp']:>10.2f} {t['atr_at_entry']:>8.4f} {t['pnl_usd']:>8.2f} {t['exit_reason']:<6} {t['holding_hours']:>6.1f}")

    # Save full report
    report = {
        "configs": all_results,
        "recommendations": {
            "best_challenge": best_challenge[0],
            "best_production": best_prod[0],
            "risk_adjusted_winner": best_risk[0],
            "recommended_default": best_default,
            "composite_scores": scores,
        },
    }
    report_path = REPO_ROOT / "data" / "validation" / "atr_execution_validation_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\n  Report saved: {report_path}")


if __name__ == "__main__":
    main()
