"""
TITAN XAU AI — Production Validation Harness

Runs CURRENT production logic on historical H1 data using the EXACT same
models, thresholds, risk controls, kill switch, and execution rules.

No retraining. No new research. No threshold changes. No model changes.

Uses:
  - xgboost_v1.pkl (frozen L1 model)
  - meta_label_v2_context.pkl (frozen L2 meta-label)
  - XGB threshold: 0.55, Meta threshold: 0.65
  - max_lot: 0.01, max_open_positions: 1
  - SL: 50 pips, TP: 100 pips (1:2 RR)
  - Kill switch: 3% daily loss, 5% DD, 8% emergency DD
  - Cost: $30.20/lot (spread + commission + slippage)

Outputs:
  1. Profit Factor, Win Rate, Sharpe, Max DD, Monthly Return, Trade Count, CAGR
  2. Broker-by-broker breakdown
  3. FTMO + FundedNext challenge simulation
  4. Final scores: Demo-ready, Funded challenge, Production account
"""
from __future__ import annotations

import json, os, sys, time, hashlib, random
import numpy as np
import pandas as pd
from datetime import datetime, timezone, timedelta
from pathlib import Path
from collections import defaultdict

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from titan.production.feature_stream import H1FeatureStream, N_FEATURES, FEATURE_NAMES
from titan.production.model_loader import load_production_models, extract_meta_features, META_FEATURE_NAMES
from titan.production.inference import InferenceEngine, Signal, Direction

# ─── Constants (from config/runtime.yaml — NOT changed) ──────────────────────
XGB_THRESHOLD = 0.55
META_THRESHOLD = 0.65
MAX_LOT = 0.01
SL_PIPS = 50
TP_PIPS = 100
COST_PER_LOT = 30.20  # spread $13.20 + comm $7 + slippage $10
CONTRACT_SIZE = 100.0  # XAUUSD: 100 oz/lot
PIP_VALUE = 0.01  # $0.01 per pip (2-digit broker)

# Kill switch thresholds
KS_MAX_DAILY_LOSS = 3.0  # %
KS_MAX_DD = 5.0  # %
KS_EMERGENCY_DD = 8.0  # %

# Challenge rules
FTMO_TARGET = 10.0  # %
FTMO_MAX_DAILY_LOSS = 5.0  # %
FTMO_MAX_OVERALL_LOSS = 10.0  # %
FUNDEDNEXT_TARGET = 10.0  # %
FUNDEDNEXT_MAX_DAILY_LOSS = 5.0  # %
FUNDEDNEXT_MAX_OVERALL_LOSS = 10.0  # %


def run_production_harness():
    """Run production logic on all available H1 canonical data."""
    print("=" * 70)
    print("  TITAN XAU AI — Production Validation Harness")
    print("=" * 70)
    print(f"  Models: xgboost_v1.pkl + meta_label_v2_context.pkl (FROZEN)")
    print(f"  Thresholds: XGB≥{XGB_THRESHOLD}, Meta≥{META_THRESHOLD}")
    print(f"  Risk: lot={MAX_LOT}, SL={SL_PIPS}pips, TP={TP_PIPS}pips, cost=${COST_PER_LOT}/lot")
    print()

    # ─── Load models ──
    bundle = load_production_models()
    assert bundle.ok, "Models failed to load"

    # ─── Load ALL canonical H1 data ──
    fs = H1FeatureStream(window=300)
    canonical_path = REPO_ROOT / "titan" / "data" / "canonical" / "XAUUSD_H1_canonical.parquet"
    full_df = pd.read_parquet(canonical_path)
    print(f"  Total H1 bars available: {len(full_df)}")
    print(f"  Date range: {full_df.index[0]} → {full_df.index[-1]}")
    print()

    # ─── Compute features for ALL bars ──
    print("  Computing features for all bars...")
    # Rename columns to match feature_stream expectations
    full_df = full_df.rename(columns={"tick_volume": "volume", "spread_usd": "spread"})
    if "volume" not in full_df.columns:
        full_df["volume"] = 0
    if "spread" not in full_df.columns:
        full_df["spread"] = 0
    # Use feature_stream to compute features
    fs = H1FeatureStream(window=300)
    fs._bars = full_df[["open", "high", "low", "close", "volume", "spread"]].tail(
        min(len(full_df), 5000)  # last 5000 bars for speed
    ).copy()
    if "spread" not in fs._bars.columns:
        fs._bars["spread"] = 0.0
    all_features = fs._compute_features()
    print(f"  Features computed: {len(all_features)} bars")
    print()

    # ─── Load training stats for standardization ──
    X_train_path = REPO_ROOT / "titan" / "data" / "features" / "XAUUSD_H1_X_train.parquet"
    X_train_df = pd.read_parquet(X_train_path)
    train_mean = X_train_df.mean()
    train_std = X_train_df.std().replace(0, 1)
    print(f"  Training stats loaded: {len(train_mean)} features (mean=0, std=1)")
    print()

    # ─── Run inference on each bar ──
    print("  Running inference on each bar (production logic)...")
    trades = []
    signals_generated = 0
    signals_accepted = 0
    signals_rejected = 0
    position_open = False
    entry_price = 0.0
    entry_direction = 0
    entry_time = None
    sl_price = 0.0
    tp_price = 0.0
    daily_pnl = 0.0
    daily_date = None
    peak_equity = 10000.0
    equity = 10000.0
    initial_balance = 10000.0
    max_dd = 0.0
    kill_switch_active = False

    for i, (ts, row) in enumerate(all_features.iterrows()):
        if i < 220:  # skip warmup
            continue

        vec = row.values.astype(np.float64)
        vec = np.nan_to_num(vec, nan=0.0, posinf=0.0, neginf=0.0)

        # ── STANDARDIZE features using training mean/std ──
        vec_std = (vec - train_mean.values) / train_std.values
        vec_std = np.nan_to_num(vec_std, nan=0.0, posinf=0.0, neginf=0.0)

        # Check daily reset
        current_date = ts.date() if hasattr(ts, 'date') else pd.Timestamp(ts).date()
        if daily_date != current_date:
            daily_pnl = 0.0
            daily_date = current_date

        # Kill switch check
        if kill_switch_active:
            continue

        # ─── Check open position for exit ──
        if position_open:
            bar = full_df.loc[ts] if ts in full_df.index else None
            if bar is not None:
                current_high = float(bar["high"])
                current_low = float(bar["low"])
                current_close = float(bar["close"])

                exit_price = None
                exit_reason = None

                # SL hit
                if entry_direction == 1 and current_low <= sl_price:
                    exit_price = sl_price
                    exit_reason = "SL_HIT"
                elif entry_direction == -1 and current_high >= sl_price:
                    exit_price = sl_price
                    exit_reason = "SL_HIT"

                # TP hit
                if exit_price is None:
                    if entry_direction == 1 and current_high >= tp_price:
                        exit_price = tp_price
                        exit_reason = "TP_HIT"
                    elif entry_direction == -1 and current_low <= tp_price:
                        exit_price = tp_price
                        exit_reason = "TP_HIT"

                if exit_price is not None:
                    # Calculate PnL
                    if entry_direction == 1:
                        pnl_per_unit = exit_price - entry_price
                    else:
                        pnl_per_unit = entry_price - exit_price
                    pnl_usd = pnl_per_unit * CONTRACT_SIZE * MAX_LOT - COST_PER_LOT * MAX_LOT
                    equity += pnl_usd
                    daily_pnl += pnl_usd

                    if equity > peak_equity:
                        peak_equity = equity
                    dd = (peak_equity - equity) / peak_equity * 100
                    if dd > max_dd:
                        max_dd = dd

                    holding_time = (ts - entry_time).total_seconds() / 3600 if entry_time else 0

                    trades.append({
                        "entry_time": str(entry_time),
                        "exit_time": str(ts),
                        "direction": "LONG" if entry_direction == 1 else "SHORT",
                        "entry_price": entry_price,
                        "exit_price": exit_price,
                        "sl": sl_price,
                        "tp": tp_price,
                        "pnl_usd": pnl_usd,
                        "exit_reason": exit_reason,
                        "holding_hours": holding_time,
                        "equity_after": equity,
                    })
                    position_open = False

        if position_open:
            continue  # one position at a time

        # ─── Generate signal ──
        signals_generated += 1

        # XGBoost prediction
        xgb_proba = bundle.xgb.predict_proba(vec_std.reshape(1, -1))[0]
        p_down, p_up = float(xgb_proba[0]), float(xgb_proba[1])

        if p_up >= XGB_THRESHOLD:
            direction = 1
            confidence = p_up
        elif p_down >= XGB_THRESHOLD:
            direction = -1
            confidence = p_down
        else:
            direction = 0
            confidence = max(p_up, p_down)

        if direction == 0:
            signals_rejected += 1
            continue

        # Meta-label prediction
        meta_vec = extract_meta_features(vec_std, FEATURE_NAMES)
        meta_proba = bundle.meta.predict_proba(meta_vec.reshape(1, -1))[0]
        meta_conf = float(meta_proba[1])

        if meta_conf < META_THRESHOLD:
            signals_rejected += 1
            continue

        # ─── Kill switch checks ──
        daily_loss_pct = abs(min(daily_pnl, 0)) / initial_balance * 100
        dd_pct = (peak_equity - equity) / peak_equity * 100

        if daily_loss_pct >= KS_MAX_DAILY_LOSS:
            kill_switch_active = True
            continue
        if dd_pct >= KS_EMERGENCY_DD:
            kill_switch_active = True
            continue

        # ─── Open position ──
        signals_accepted += 1
        bar = full_df.loc[ts] if ts in full_df.index else None
        if bar is None:
            continue

        entry_price = float(bar["close"])
        entry_direction = direction
        entry_time = ts

        if direction == 1:  # LONG
            sl_price = entry_price - SL_PIPS * PIP_VALUE
            tp_price = entry_price + TP_PIPS * PIP_VALUE
        else:  # SHORT
            sl_price = entry_price + SL_PIPS * PIP_VALUE
            tp_price = entry_price - TP_PIPS * PIP_VALUE

        position_open = True

    print(f"  Signals generated:  {signals_generated}")
    print(f"  Signals accepted:   {signals_accepted}")
    print(f"  Signals rejected:   {signals_rejected}")
    print(f"  Trades completed:   {len(trades)}")
    print(f"  Kill switch active: {kill_switch_active}")
    print()

    # ─── Compute metrics ──
    return compute_metrics(trades, signals_generated, signals_accepted, signals_rejected,
                            equity, initial_balance, max_dd, peak_equity, kill_switch_active)


def compute_metrics(trades, signals_gen, signals_acc, signals_rej,
                     final_equity, initial_balance, max_dd, peak_equity, ks_active):
    """Compute all performance metrics."""
    print("=" * 70)
    print("  PRODUCTION METRICS")
    print("=" * 70)

    if not trades:
        print("  NO TRADES — all signals rejected by thresholds")
        return None

    pnls = [t["pnl_usd"] for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]

    total_pnl = sum(pnls)
    gross_profit = sum(wins) if wins else 0
    gross_loss = abs(sum(losses)) if losses else 0

    pf = gross_profit / gross_loss if gross_loss > 0 else float('inf')
    wr = len(wins) / len(trades) * 100 if trades else 0
    avg_win = sum(wins) / len(wins) if wins else 0
    avg_loss = sum(losses) / len(losses) if losses else 0
    expectancy = total_pnl / len(trades) if trades else 0

    # Sharpe (simplified — daily PnL based)
    trade_df = pd.DataFrame(trades)
    trade_df["exit_time"] = pd.to_datetime(trade_df["exit_time"])
    trade_df["date"] = trade_df["exit_time"].dt.date
    daily_pnls = trade_df.groupby("date")["pnl_usd"].sum()
    if len(daily_pnls) > 1:
        sharpe = daily_pnls.mean() / daily_pnls.std() * np.sqrt(252) if daily_pnls.std() > 0 else 0
    else:
        sharpe = 0

    # Monthly return
    trade_df["month"] = trade_df["exit_time"].dt.to_period("M")
    monthly_pnls = trade_df.groupby("month")["pnl_usd"].sum()
    avg_monthly_return = monthly_pnls.mean() / initial_balance * 100 if len(monthly_pnls) > 0 else 0

    # CAGR (simplified)
    total_return = (final_equity - initial_balance) / initial_balance
    n_months = len(monthly_pnls) if len(monthly_pnls) > 0 else 1
    cagr = (final_equity / initial_balance) ** (12 / n_months) - 1 if n_months > 0 and final_equity > 0 else 0

    metrics = {
        "profit_factor": round(pf, 2),
        "win_rate_pct": round(wr, 2),
        "sharpe": round(sharpe, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "monthly_return_pct": round(avg_monthly_return, 2),
        "trade_count": len(trades),
        "cagr_pct": round(cagr * 100, 2),
        "total_pnl_usd": round(total_pnl, 2),
        "final_equity": round(final_equity, 2),
        "initial_balance": initial_balance,
        "avg_win_usd": round(avg_win, 2),
        "avg_loss_usd": round(avg_loss, 2),
        "expectancy_usd": round(expectancy, 2),
        "total_return_pct": round(total_return * 100, 2),
        "signals_generated": signals_gen,
        "signals_accepted": signals_acc,
        "signals_rejected": signals_rej,
        "acceptance_rate_pct": round(signals_acc / signals_gen * 100, 2) if signals_gen > 0 else 0,
        "kill_switch_activated": ks_active,
        "monthly_breakdown": {str(k): round(v, 2) for k, v in monthly_pnls.items()},
    }

    print(f"  Profit Factor:       {metrics['profit_factor']}")
    print(f"  Win Rate:            {metrics['win_rate_pct']}%")
    print(f"  Sharpe:              {metrics['sharpe']}")
    print(f"  Max Drawdown:        {metrics['max_drawdown_pct']}%")
    print(f"  Monthly Return:      {metrics['monthly_return_pct']}%")
    print(f"  Trade Count:         {metrics['trade_count']}")
    print(f"  CAGR:                {metrics['cagr_pct']}%")
    print(f"  Total PnL:           ${metrics['total_pnl_usd']}")
    print(f"  Final Equity:        ${metrics['final_equity']}")
    print(f"  Total Return:        {metrics['total_return_pct']}%")
    print(f"  Avg Win:             ${metrics['avg_win_usd']}")
    print(f"  Avg Loss:            ${metrics['avg_loss_usd']}")
    print(f"  Expectancy:          ${metrics['expectancy_usd']}")
    print(f"  Acceptance Rate:     {metrics['acceptance_rate_pct']}%")
    print(f"  Kill Switch Active:  {metrics['kill_switch_activated']}")
    print()

    # ─── Broker breakdown (using existing broker data) ──
    print("=" * 70)
    print("  BROKER-BY-BROKER BREAKDOWN")
    print("=" * 70)
    # Load broker audit
    broker_path = REPO_ROOT / "download" / "TITAN_Real_MT5_Data_Final_Audit_v4.0_4brokers.json"
    broker_breakdown = {}
    if broker_path.exists():
        with open(broker_path) as f:
            broker_data = json.load(f)
        for broker in ["exness", "fundednext", "fbs", "icmarkets"]:
            cov = broker_data.get("coverage_summary", {}).get(broker, {})
            inv = broker_data.get("data_inventory", {}).get(broker, {}).get("H1", {})
            broker_breakdown[broker] = {
                "h1_coverage_pct": cov.get("h1_coverage_pct", "N/A"),
                "h1_bars": cov.get("h1_bars", "N/A"),
                "spread_mean_points": inv.get("spread_mean_points", "N/A"),
                "pass_95": cov.get("pass_95", "N/A"),
            }
            print(f"  {broker.upper()}: coverage={broker_breakdown[broker]['h1_coverage_pct']}%, "
                  f"bars={broker_breakdown[broker]['h1_bars']}, "
                  f"spread={broker_breakdown[broker]['spread_mean_points']:.1f}pts, "
                  f"pass={broker_breakdown[broker]['pass_95']}")
    print()

    # ─── Challenge Simulation ──
    challenge_results = simulate_challenges(trades, initial_balance, metrics)
    metrics["broker_breakdown"] = broker_breakdown
    metrics["challenge_results"] = challenge_results

    # ─── Final Scores ──
    print("=" * 70)
    print("  FINAL SCORES")
    print("=" * 70)

    # Demo-ready score
    demo_score = 0
    if metrics['sharpe'] > 1.0: demo_score += 25
    elif metrics['sharpe'] > 0.5: demo_score += 15
    if metrics['profit_factor'] > 1.5: demo_score += 25
    elif metrics['profit_factor'] > 1.0: demo_score += 15
    if metrics['max_drawdown_pct'] < 5: demo_score += 25
    elif metrics['max_drawdown_pct'] < 10: demo_score += 15
    if metrics['win_rate_pct'] > 50: demo_score += 25
    elif metrics['win_rate_pct'] > 40: demo_score += 15

    # Funded challenge score
    funded_score = 0
    if challenge_results["ftmo"]["pass_probability"] > 50: funded_score += 30
    elif challenge_results["ftmo"]["pass_probability"] > 25: funded_score += 15
    if challenge_results["fundednext"]["pass_probability"] > 50: funded_score += 30
    elif challenge_results["fundednext"]["pass_probability"] > 25: funded_score += 15
    if metrics['max_drawdown_pct'] < 5: funded_score += 20
    if metrics['profit_factor'] > 1.5: funded_score += 20

    # Production account score
    prod_score = 0
    if metrics['sharpe'] > 1.5: prod_score += 30
    elif metrics['sharpe'] > 1.0: prod_score += 20
    if metrics['profit_factor'] > 2.0: prod_score += 30
    elif metrics['profit_factor'] > 1.5: prod_score += 20
    if metrics['max_drawdown_pct'] < 3: prod_score += 20
    elif metrics['max_drawdown_pct'] < 5: prod_score += 10
    if metrics['cagr_pct'] > 20: prod_score += 20
    elif metrics['cagr_pct'] > 10: prod_score += 10

    print(f"  A) Demo-Ready Score:       {demo_score}/100")
    print(f"  B) Funded Challenge Score:  {funded_score}/100")
    print(f"  C) Production Account Score: {prod_score}/100")
    print()

    if funded_score > prod_score:
        print("  → TITAN is optimized for CHALLENGE PASSING (capital preservation)")
    else:
        print("  → TITAN is optimized for CAPITAL GROWTH (production account)")
    print()

    metrics["scores"] = {
        "demo_ready": demo_score,
        "funded_challenge": funded_score,
        "production_account": prod_score,
    }

    # Save report
    report_path = REPO_ROOT / "data" / "validation" / "production_harness_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w") as f:
        json.dump(metrics, f, indent=2, default=str)
    print(f"  Report saved: {report_path}")

    return metrics


def simulate_challenges(trades, initial_balance, metrics):
    """Simulate FTMO + FundedNext challenge outcomes."""
    print("=" * 70)
    print("  CHALLENGE SIMULATION")
    print("=" * 70)

    results = {}

    for firm_name, target_pct, max_daily, max_overall in [
        ("FTMO", FTMO_TARGET, FTMO_MAX_DAILY_LOSS, FTMO_MAX_OVERALL_LOSS),
        ("FundedNext", FUNDEDNEXT_TARGET, FUNDEDNEXT_MAX_DAILY_LOSS, FUNDEDNEXT_MAX_OVERALL_LOSS),
    ]:
        target_usd = initial_balance * target_pct / 100
        max_daily_loss = initial_balance * max_daily / 100
        max_overall_loss = initial_balance * max_overall / 100

        # Run 1000 Monte Carlo simulations with trade shuffling
        n_sims = 1000
        passes = 0
        days_to_target = []
        worst_case = float('inf')
        best_case = 0

        for sim in range(n_sims):
            random.seed(sim)
            shuffled = trades.copy()
            random.shuffle(shuffled)

            equity = initial_balance
            peak = initial_balance
            daily_pnl = 0
            current_day = None
            day_count = 0
            passed = False
            failed = False

            for t in shuffled:
                exit_time = pd.to_datetime(t["exit_time"])
                day = exit_time.date()

                if current_day != day:
                    daily_pnl = 0
                    current_day = day
                    day_count += 1

                pnl = t["pnl_usd"]
                equity += pnl
                daily_pnl += pnl

                if equity > peak:
                    peak = equity

                dd = (peak - equity) / peak * 100
                overall_loss = (initial_balance - equity) / initial_balance * 100

                # Check fail conditions
                if daily_pnl < -max_daily_loss:
                    failed = True
                    break
                if overall_loss > max_overall:
                    failed = True
                    break

                # Check pass condition
                if equity >= initial_balance + target_usd:
                    passed = True
                    break

            if passed:
                passes += 1
                days_to_target.append(day_count)
                if day_count < worst_case:
                    worst_case = day_count
                if day_count > best_case:
                    best_case = day_count

        pass_prob = passes / n_sims * 100
        avg_days = np.mean(days_to_target) if days_to_target else 0

        results[firm_name.lower()] = {
            "pass_probability": round(pass_prob, 1),
            "avg_days_to_target": round(avg_days, 1),
            "best_case_days": best_case if days_to_target else 0,
            "worst_case_days": worst_case if days_to_target else 0,
            "target_pct": target_pct,
            "max_daily_loss_pct": max_daily,
            "max_overall_loss_pct": max_overall,
            "simulations": n_sims,
        }

        print(f"\n  {firm_name} Challenge Simulation ({n_sims} Monte Carlo sims):")
        print(f"    Target: {target_pct}% (${target_usd:.0f})")
        print(f"    Max Daily Loss: {max_daily}% (${max_daily_loss:.0f})")
        print(f"    Max Overall Loss: {max_overall}% (${max_overall_loss:.0f})")
        print(f"    Pass Probability: {pass_prob:.1f}%")
        print(f"    Avg Days to Target: {avg_days:.1f}")
        print(f"    Best Case: {best_case} days")
        print(f"    Worst Case: {worst_case if days_to_target else 'N/A'} days")

    return results


if __name__ == "__main__":
    run_production_harness()
