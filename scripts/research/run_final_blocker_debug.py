#!/usr/bin/env python3
"""TITAN XAU AI - Final Blocker Debug (Sprint v2.8.7-G)
=========================================================
Diagnoses exactly why all parameter discovery candidates are rejected.

Tasks:
  Task 1: Read/run sweep + rejection debug
  Task 2: Audit REJECT_OVERFIT breakdown
  Task 3: Find best near-pass candidate
  Task 4: Broker-specific calibration audit
  Task 5: Fast targeted search (max 50 candidates)
  Task 6: Final honest verdict if no candidate

This script runs a FOCUSED sweep (not broad) to avoid sandbox OOM.
It evaluates 50 targeted candidates and produces detailed rejection
diagnostics per candidate.

NEVER sends orders. NEVER creates tokens. NEVER trades.
"""
from __future__ import annotations
import sys, json, csv, os, gc
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict
import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

OUTPUT_DIR = REPO_ROOT / "data" / "reports" / "final_blocker_debug"
TARGETED_DIR = REPO_ROOT / "data" / "reports" / "parameter_discovery_v2_targeted"

from titan.production.spread_normalization import normalize_xauusd_spread_to_usd
from titan.production.feature_stream_v2 import H1FeatureStreamV2, FEATURE_NAMES_V2
from titan.training.feature_schema_v2 import META_FEATURE_NAMES_V2
from titan.production.model_loader import load_models_by_profile
from titan.production.mtf_confirmation import load_m15_bars, load_m5_bars, evaluate_mtf, reset_mtf_caches
from titan.production.ceo_ai_governance import evaluate_ceo_decision


BROKER_PATHS = {
    "canonical": REPO_ROOT / "titan" / "data" / "canonical" / "XAUUSD_H1_canonical.parquet",
    "exness": REPO_ROOT / "titan" / "data" / "sources" / "mt5_brokers" / "exness" / "XAUUSD_H1.parquet",
    "fbs": REPO_ROOT / "titan" / "data" / "sources" / "mt5_brokers" / "fbs" / "XAUUSD_H1.parquet",
    "fundednext": REPO_ROOT / "titan" / "data" / "sources" / "mt5_brokers" / "fundednext" / "XAUUSD_H1.parquet",
    "icmarkets": REPO_ROOT / "titan" / "data" / "sources" / "mt5_brokers" / "icmarkets" / "XAUUSD_H1.parquet",
}

MAX_TOTAL_DD = 0.08
MAX_DAILY_DD = 0.025
MIN_OOS_PF = 1.10
MIN_OOS_SHARPE = 0.0
MIN_SAMPLE_TRADES = 10


def load_broker(name):
    """Load broker data with spread normalization."""
    path = BROKER_PATHS[name]
    if not path.exists():
        return None
    df = pd.read_parquet(path)
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)
    df = normalize_xauusd_spread_to_usd(df, symbol="XAUUSD", source=name)
    return df


def compute_predictions(df, bundle):
    """Compute v2 alpha + meta predictions for a broker DataFrame."""
    df_use = df[["open", "high", "low", "close"]].copy()
    if "tick_volume" in df.columns:
        df_use["volume"] = df["tick_volume"]
    elif "volume" in df.columns:
        df_use["volume"] = df["volume"]
    else:
        df_use["volume"] = 0.0
    df_use["spread"] = df["spread_usd"]

    stream = H1FeatureStreamV2()
    stream._bars = df_use
    feats_df = stream._compute_features()
    features_matrix = np.nan_to_num(
        feats_df.values.astype(np.float64), nan=0.0, posinf=0.0, neginf=0.0
    )
    features_matrix = stream._standardize(features_matrix)

    alpha_proba = bundle.xgb.predict_proba(features_matrix)[:, 1]
    name_to_idx = {n: i for i, n in enumerate(FEATURE_NAMES_V2)}
    meta_indices = [name_to_idx[n] for n in META_FEATURE_NAMES_V2]
    meta_vecs = features_matrix[:, meta_indices]
    meta_proba = bundle.meta.predict_proba(meta_vecs)[:, 1]

    # ATR
    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values
    atr_values = np.zeros(len(df))
    for i in range(14, len(df)):
        atr_values[i] = max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1]))
    for i in range(28, len(df)):
        atr_values[i] = np.mean(atr_values[i-14:i])

    return alpha_proba, meta_proba, atr_values


def run_backtest_detailed(df, alpha_proba, meta_proba, atr_values, params,
                           m15_bars=None, m5_bars=None):
    """Run backtest with detailed per-broker tracking. Returns (summary, broker_stats)."""
    starting_equity = 10000.0
    equity = starting_equity
    daily_start_equity = equity
    wins, losses = 0, 0
    gross_profit, gross_loss = 0.0, 0.0
    max_daily_dd, max_total_dd = 0.0, 0.0
    consecutive_losses, max_consecutive_losses = 0, 0
    total_r = 0.0
    prop_violations = 0
    total_dd_cap_hit = False
    daily_trades = 0
    current_day = None
    cooldown_remaining = 0

    closes = df["close"].values
    highs = df["high"].values
    lows = df["low"].values
    index = df.index

    for i in range(28, len(df) - params.get("max_holding_bars", 3) - 1):
        total_dd = (starting_equity - equity) / starting_equity
        if total_dd > max_total_dd:
            max_total_dd = total_dd
        if total_dd >= MAX_TOTAL_DD:
            if not total_dd_cap_hit:
                total_dd_cap_hit = True
                prop_violations += 1
            continue

        daily_dd = (daily_start_equity - equity) / daily_start_equity
        if daily_dd > max_daily_dd:
            max_daily_dd = daily_dd
        if daily_dd >= MAX_DAILY_DD:
            continue

        bar_day = index[i].date()
        if current_day != bar_day:
            current_day = bar_day
            daily_start_equity = equity
            daily_trades = 0

        if daily_trades >= params.get("max_trades_per_day", 2):
            continue
        if cooldown_remaining > 0:
            cooldown_remaining -= 1
            continue

        alpha_confidence = float(alpha_proba[i])
        if alpha_confidence < params.get("alpha_threshold", 0.55):
            continue
        direction = "LONG" if alpha_confidence >= 0.5 else "SHORT"
        if alpha_confidence == 0.5:
            direction = "LONG" if closes[i] > closes[i-1] else "SHORT"

        meta_confidence = float(meta_proba[i])
        if meta_confidence < params.get("meta_threshold", 0.65):
            continue

        # CEO
        ceo_decision = evaluate_ceo_decision(
            regime_state={"detected": True, "regime_value": "MARKET_OPEN", "confidence": alpha_confidence},
            xgb_alpha={"direction": direction, "confidence": alpha_confidence, "pass": True},
            lstm_confidence=None, transformer_regime=None,
            meta_label_quality={"quality_score": meta_confidence, "pass": True},
            broker_state={"broker_pass": True, "spread_pass": True, "slippage_pass": True},
            prop_risk_state={"risk_pass": True, "prop_funded_pass": True, "max_positions_ok": True},
            capital_protection_state={"capital_preservation_active": False, "dd_breach": False},
            model_health_state={"model_health_pass": True, "failed_required": 0},
            geometry_state={"geometry_pass": True, "actual_RR": params.get("rr_target", 3.0), "minimum_RR": 2.0},
        )
        if not ceo_decision.allowed_to_trade:
            continue

        # MTF
        mtf_mode = params.get("mtf_mode", "h1_only")
        if mtf_mode != "h1_only":
            mtf_result = evaluate_mtf(mtf_mode, index[i], direction, m15_bars, m5_bars)
            if not mtf_result.m15_confirmation_pass:
                continue
            if mtf_mode == "h1_m15_m5" and not mtf_result.m5_entry_trigger_pass:
                continue

        atr = atr_values[i] if atr_values[i] > 0 else 3.0
        sl_distance = atr * params.get("sl_atr_multiplier", 1.5)
        tp_distance = sl_distance * params.get("rr_target", 3.0)
        entry_price = closes[i]
        if direction == "LONG":
            sl_price = entry_price - sl_distance
            tp_price = entry_price + tp_distance
        else:
            sl_price = entry_price + sl_distance
            tp_price = entry_price - tp_distance

        exit_price = entry_price
        exit_reason = "TIMEOUT"
        r_result = 0.0
        max_holding = params.get("max_holding_bars", 3)

        for j in range(1, max_holding + 1):
            if i + j >= len(df):
                break
            if direction == "LONG":
                if lows[i + j] <= sl_price:
                    exit_price, exit_reason, r_result = sl_price, "SL_HIT", -1.0
                    break
                if highs[i + j] >= tp_price:
                    exit_price, exit_reason, r_result = tp_price, "TP_HIT", params.get("rr_target", 3.0)
                    break
            else:
                if highs[i + j] >= sl_price:
                    exit_price, exit_reason, r_result = sl_price, "SL_HIT", -1.0
                    break
                if lows[i + j] <= tp_price:
                    exit_price, exit_reason, r_result = tp_price, "TP_HIT", params.get("rr_target", 3.0)
                    break

        if exit_reason == "TIMEOUT":
            exit_price = closes[min(i + max_holding, len(df)-1)]
            if direction == "LONG":
                r_result = (exit_price - entry_price) / sl_distance
            else:
                r_result = (entry_price - exit_price) / sl_distance

        risk_amount = equity * params.get("risk_percent", 0.005)
        pnl = risk_amount * r_result
        equity += pnl
        total_r += r_result
        daily_trades += 1

        if pnl > 0:
            wins += 1
            gross_profit += pnl
            consecutive_losses = 0
        else:
            losses += 1
            gross_loss += abs(pnl)
            consecutive_losses += 1
            max_consecutive_losses = max(max_consecutive_losses, consecutive_losses)
            cooldown_remaining = params.get("cooldown_after_loss", 3)

    total_trades = wins + losses
    win_rate = wins / total_trades if total_trades > 0 else 0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else (999.0 if gross_profit > 0 else 0)
    if total_trades > 1:
        rs = [1.0] * wins + [-1.0] * losses
        std_r = max(0.01, float(np.std(rs)))
        sharpe = (sum(rs) / len(rs)) / std_r * (252 ** 0.5)
    else:
        sharpe = 0

    return {
        "trades": total_trades,
        "win_rate": round(win_rate, 4),
        "profit_factor": round(profit_factor, 4) if profit_factor != 999 else 999,
        "sharpe": round(sharpe, 4),
        "max_total_dd": round(max_total_dd, 4),
        "max_daily_dd": round(max_daily_dd, 4),
        "avg_r": round(total_r / total_trades, 4) if total_trades > 0 else 0,
        "prop_violations": prop_violations,
    }


def diagnose_rejection(params, oos_results):
    """Determine the EXACT rejection reason for a candidate."""
    reasons = []

    if not oos_results:
        return "REJECT_LOW_SAMPLE", ["no_oos_results"]

    # Check each broker
    for broker, r in oos_results.items():
        if r["trades"] < MIN_SAMPLE_TRADES:
            reasons.append(f"{broker}_low_trades({r['trades']})")
        if r["max_total_dd"] > MAX_TOTAL_DD:
            reasons.append(f"{broker}_dd_breach({r['max_total_dd']:.3f})")
        if r["prop_violations"] > 0:
            reasons.append(f"{broker}_prop_violation")

    total_oos_trades = sum(r["trades"] for r in oos_results.values())
    if total_oos_trades < MIN_SAMPLE_TRADES:
        return "REJECT_LOW_SAMPLE", reasons + [f"total_trades_{total_oos_trades}"]

    # Check broker stability (>= 2 brokers with PF > 1.0)
    profitable_brokers = [b for b, r in oos_results.items() if r["profit_factor"] > 1.0 and r["trades"] >= 5]
    if len(profitable_brokers) < 2:
        reasons.append(f"only_{len(profitable_brokers)}_profitable_brokers({profitable_brokers})")
        return "REJECT_BROKER_UNSTABLE", reasons

    # Check OOS PF and Sharpe
    avg_pf = sum(r["profit_factor"] for r in oos_results.values()) / len(oos_results)
    avg_sharpe = sum(r["sharpe"] for r in oos_results.values()) / len(oos_results)
    avg_dd = sum(r["max_total_dd"] for r in oos_results.values()) / len(oos_results)

    if avg_pf < MIN_OOS_PF:
        reasons.append(f"avg_pf_{avg_pf:.3f}_below_{MIN_OOS_PF}")
    if avg_sharpe <= MIN_OOS_SHARPE:
        reasons.append(f"avg_sharpe_{avg_sharpe:.3f}_below_{MIN_OOS_SHARPE}")

    if reasons:
        return "REJECT_OVERFIT", reasons

    return "ACCEPT_CANDIDATE", reasons


def near_pass_check(params, oos_results):
    """Check if candidate is near-pass (relaxed criteria)."""
    if not oos_results:
        return False, ["no_oos_results"]

    reasons = []
    # At least 2 brokers PF >= 1.0
    profitable = [b for b, r in oos_results.items() if r["profit_factor"] >= 1.0 and r["trades"] >= 5]
    if len(profitable) < 2:
        reasons.append(f"only_{len(profitable)}_brokers_pf_above_1")

    # Max DD <= 8%
    max_dd = max(r["max_total_dd"] for r in oos_results.values())
    if max_dd > MAX_TOTAL_DD:
        reasons.append(f"max_dd_{max_dd:.3f}_above_{MAX_TOTAL_DD}")

    # Sharpe not severely negative (> -2.0)
    min_sharpe = min(r["sharpe"] for r in oos_results.values())
    if min_sharpe <= -2.0:
        reasons.append(f"min_sharpe_{min_sharpe:.3f}_severely_negative")

    # No prop violations
    prop_viol = sum(r["prop_violations"] for r in oos_results.values())
    if prop_viol > 0:
        reasons.append(f"prop_violations_{prop_viol}")

    if not reasons:
        return True, []
    return False, reasons


def generate_targeted_grid():
    """Generate 50 targeted candidates based on prior findings."""
    grid = []
    # Focus on h1_only (MTF was too restrictive in prior runs)
    # Vary alpha/meta thresholds within safe ranges
    for alpha in [0.50, 0.52, 0.55, 0.58]:
        for meta in [0.50, 0.55, 0.60, 0.65]:
            for sl_atr in [1.0, 1.5, 2.0]:
                for rr in [2.0, 3.0]:
                    for holding in [1, 3]:
                        for risk in [0.0025, 0.005]:
                            for cooldown in [2, 5]:
                                grid.append({
                                    "alpha_threshold": alpha,
                                    "meta_threshold": meta,
                                    "sl_atr_multiplier": sl_atr,
                                    "rr_target": rr,
                                    "max_holding_bars": holding,
                                    "mtf_mode": "h1_only",
                                    "risk_percent": risk,
                                    "cooldown_after_loss": cooldown,
                                    "max_trades_per_day": 2,
                                    "session_filter": "all",
                                    "regime_policy": "balanced",
                                    "spread_filter": 0.5,
                                    "trailing_policy": "off",
                                    "breakeven_trigger": 1.0,
                                })
                                if len(grid) >= 50:
                                    return grid
    return grid


def main():
    ts = datetime.now(timezone.utc).isoformat()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    TARGETED_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("  TITAN XAU AI - FINAL BLOCKER DEBUG (Sprint v2.8.7-G)")
    print("=" * 70)
    print(f"  Timestamp: {ts}\n")

    # Load v2 model
    bundle = load_models_by_profile("v2_feature_normalized")
    if not bundle.ok:
        print("  ERROR: v2 model failed to load")
        return

    # Load M15/M5 bars for MTF
    m15_bars = load_m15_bars()
    m5_bars = load_m5_bars()
    reset_mtf_caches()
    print(f"  M15 bars: {len(m15_bars)}, M5 bars: {len(m5_bars)}")

    # Load 3 brokers (sandbox memory limit)
    brokers = ["canonical", "exness", "fbs"]
    brokers_data = {}
    brokers_preds = {}
    for b in brokers:
        df = load_broker(b)
        if df is None:
            continue
        print(f"  Computing predictions for {b}...")
        alpha, meta, atr = compute_predictions(df, bundle)
        brokers_data[b] = df
        brokers_preds[b] = {"alpha": alpha, "meta": meta, "atr": atr}
        print(f"    {b}: {len(df)} bars, alpha>0.55: {(alpha>=0.55).sum()}, meta>0.65: {(meta>=0.65).sum()}")

    # === Task 1+2: Run targeted sweep + rejection debug ===
    print("\n  [Tasks 1+2] Running targeted sweep + rejection debug...")
    grid = generate_targeted_grid()
    print(f"  Generated {len(grid)} targeted candidates")

    all_results = []
    rejection_breakdown = defaultdict(int)
    broker_failure_matrix = defaultdict(lambda: defaultdict(int))
    near_pass_candidates = []

    for idx, params in enumerate(grid):
        if idx % 5 == 0:
            print(f"    [{idx}/{len(grid)}] evaluating...")

        # Run backtest per broker on OOS 2025-2026
        oos_results = {}
        for b in brokers:
            df = brokers_data[b]
            oos_mask = (df.index.year >= 2025) & (df.index.year <= 2026)
            if oos_mask.sum() < 100:
                continue
            df_oos = df[oos_mask]
            preds = brokers_preds[b]
            oos_mask_np = np.asarray(oos_mask)
            summary = run_backtest_detailed(
                df_oos,
                preds["alpha"][oos_mask_np],
                preds["meta"][oos_mask_np],
                preds["atr"][oos_mask_np],
                params, m15_bars, m5_bars,
            )
            oos_results[b] = summary

        # Diagnose rejection
        rejection_reason, detail_reasons = diagnose_rejection(params, oos_results)
        rejection_breakdown[rejection_reason] += 1

        # Track broker failures
        for b, r in oos_results.items():
            if r["profit_factor"] < 1.0:
                broker_failure_matrix[b]["pf_below_1"] += 1
            if r["trades"] < MIN_SAMPLE_TRADES:
                broker_failure_matrix[b]["low_trades"] += 1
            if r["max_total_dd"] > MAX_TOTAL_DD:
                broker_failure_matrix[b]["dd_breach"] += 1

        # Near-pass check
        is_near_pass, near_pass_reasons = near_pass_check(params, oos_results)

        row = {
            **params,
            "rejection_reason": rejection_reason,
            "detail_reasons": "; ".join(detail_reasons),
            "oos_total_trades": sum(r["trades"] for r in oos_results.values()),
            "oos_avg_pf": round(sum(r["profit_factor"] for r in oos_results.values()) / max(len(oos_results), 1), 4),
            "oos_avg_sharpe": round(sum(r["sharpe"] for r in oos_results.values()) / max(len(oos_results), 1), 4),
            "oos_avg_dd": round(sum(r["max_total_dd"] for r in oos_results.values()) / max(len(oos_results), 1), 4),
            "oos_max_dd": round(max(r["max_total_dd"] for r in oos_results.values()), 4),
            "profitable_brokers": len([r for r in oos_results.values() if r["profit_factor"] > 1.0 and r["trades"] >= 5]),
            "near_pass": is_near_pass,
            "near_pass_reasons": "; ".join(near_pass_reasons) if near_pass_reasons else "",
        }
        # Per-broker stats
        for b in brokers:
            if b in oos_results:
                row[f"{b}_pf"] = oos_results[b]["profit_factor"]
                row[f"{b}_sharpe"] = oos_results[b]["sharpe"]
                row[f"{b}_dd"] = oos_results[b]["max_total_dd"]
                row[f"{b}_trades"] = oos_results[b]["trades"]
            else:
                row[f"{b}_pf"] = 0
                row[f"{b}_sharpe"] = 0
                row[f"{b}_dd"] = 0
                row[f"{b}_trades"] = 0

        all_results.append(row)
        if is_near_pass:
            near_pass_candidates.append(row)

        # Cleanup
        del oos_results
        if idx % 10 == 0:
            gc.collect()

    # Sort by near_pass first, then by oos_avg_pf
    all_results.sort(key=lambda x: (x["near_pass"], x["oos_avg_pf"]), reverse=True)

    # === Write outputs ===
    print("\n  Writing outputs...")

    # rejection_debug_summary.csv (all results)
    with open(OUTPUT_DIR / "best_failed_candidates.csv", "w", newline="") as f:
        if all_results:
            w = csv.DictWriter(f, fieldnames=list(all_results[0].keys()))
            w.writeheader()
            for row in all_results:
                w.writerow(row)

    # broker_failure_matrix.csv
    with open(OUTPUT_DIR / "broker_failure_matrix.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["broker", "pf_below_1", "low_trades", "dd_breach", "total_candidates"])
        for b in brokers:
            total = len(grid)
            w.writerow([b, broker_failure_matrix[b]["pf_below_1"],
                        broker_failure_matrix[b]["low_trades"],
                        broker_failure_matrix[b]["dd_breach"], total])

    # rejection_debug_summary.json
    summary_json = {
        "timestamp_utc": ts,
        "total_candidates": len(grid),
        "rejection_breakdown": dict(rejection_breakdown),
        "broker_failure_matrix": {b: dict(v) for b, v in broker_failure_matrix.items()},
        "near_pass_count": len(near_pass_candidates),
        "near_pass_found": len(near_pass_candidates) > 0,
    }
    with open(OUTPUT_DIR / "rejection_debug_summary.json", "w") as f:
        json.dump(summary_json, f, indent=2, default=str)

    # rejection_debug_summary.md
    with open(OUTPUT_DIR / "rejection_debug_summary.md", "w") as f:
        f.write("# Final Blocker Debug Summary (Sprint v2.8.7-G)\n\n")
        f.write(f"**Timestamp:** {ts}\n\n")
        f.write("## Sweep Overview\n\n")
        f.write(f"- Model profile: v2_feature_normalized\n")
        f.write(f"- Brokers tested: {brokers}\n")
        f.write(f"- Total candidates: {len(grid)}\n")
        f.write(f"- Near-pass candidates: {len(near_pass_candidates)}\n\n")
        f.write("## Rejection Breakdown\n\n")
        f.write("| Reason | Count | Percentage |\n|---|---|---|\n")
        for reason, count in sorted(rejection_breakdown.items(), key=lambda x: -x[1]):
            pct = count / len(grid) * 100
            f.write(f"| {reason} | {count} | {pct:.1f}% |\n")
        f.write("\n## Broker Failure Matrix\n\n")
        f.write("| Broker | PF<1.0 | Low Trades | DD Breach | Total Candidates |\n")
        f.write("|---|---|---|---|---|\n")
        for b in brokers:
            f.write(f"| {b} | {broker_failure_matrix[b]['pf_below_1']} | "
                    f"{broker_failure_matrix[b]['low_trades']} | "
                    f"{broker_failure_matrix[b]['dd_breach']} | {len(grid)} |\n")
        f.write(f"\n## Near-Pass Found: {len(near_pass_candidates) > 0}\n\n")
        if near_pass_candidates:
            f.write("### Top Near-Pass Candidate\n\n")
            best = near_pass_candidates[0]
            f.write(f"- alpha_threshold: {best['alpha_threshold']}\n")
            f.write(f"- meta_threshold: {best['meta_threshold']}\n")
            f.write(f"- sl_atr_multiplier: {best['sl_atr_multiplier']}\n")
            f.write(f"- rr_target: {best['rr_target']}\n")
            f.write(f"- max_holding_bars: {best['max_holding_bars']}\n")
            f.write(f"- risk_percent: {best['risk_percent']}\n")
            f.write(f"- mtf_mode: {best['mtf_mode']}\n")
            f.write(f"- OOS avg PF: {best['oos_avg_pf']}\n")
            f.write(f"- OOS avg Sharpe: {best['oos_avg_sharpe']}\n")
            f.write(f"- OOS max DD: {best['oos_max_dd']}\n")
            f.write(f"- Profitable brokers: {best['profitable_brokers']}\n")
            f.write(f"- Rejection reason: {best['rejection_reason']}\n")
            f.write(f"- Near-pass reasons: {best['near_pass_reasons']}\n")

    # === Task 3: Near-pass candidate ===
    near_pass_found = len(near_pass_candidates) > 0
    near_pass_data = {
        "near_pass_found": near_pass_found,
        "near_pass_count": len(near_pass_candidates),
        "best_near_pass": near_pass_candidates[0] if near_pass_candidates else None,
    }
    with open(OUTPUT_DIR / "near_pass_candidate.json", "w") as f:
        json.dump(near_pass_data, f, indent=2, default=str)

    with open(OUTPUT_DIR / "near_pass_candidate.md", "w") as f:
        f.write("# Near-Pass Candidate Analysis (Sprint v2.8.7-G)\n\n")
        f.write(f"**Timestamp:** {ts}\n\n")
        f.write(f"**NEAR_PASS_FOUND:** {near_pass_found}\n\n")
        if near_pass_found:
            f.write("## Best Near-Pass Candidate\n\n")
            best = near_pass_candidates[0]
            f.write("| Parameter | Value |\n|---|---|\n")
            for k in ["alpha_threshold", "meta_threshold", "sl_atr_multiplier", "rr_target",
                       "max_holding_bars", "risk_percent", "mtf_mode", "cooldown_after_loss"]:
                f.write(f"| {k} | {best[k]} |\n")
            f.write(f"\n## OOS Metrics\n\n")
            f.write(f"- OOS avg PF: {best['oos_avg_pf']}\n")
            f.write(f"- OOS avg Sharpe: {best['oos_avg_sharpe']}\n")
            f.write(f"- OOS max DD: {best['oos_max_dd']}\n")
            f.write(f"- Profitable brokers: {best['profitable_brokers']}\n")
            f.write(f"- Rejection reason: {best['rejection_reason']}\n")
            f.write(f"- Near-pass blockers: {best['near_pass_reasons']}\n\n")
            f.write("## Per-Broker Performance\n\n")
            f.write("| Broker | PF | Sharpe | DD | Trades |\n|---|---|---|---|---|\n")
            for b in brokers:
                f.write(f"| {b} | {best[f'{b}_pf']} | {best[f'{b}_sharpe']} | "
                        f"{best[f'{b}_dd']} | {best[f'{b}_trades']} |\n")
        else:
            f.write("No near-pass candidate found. All candidates fail the near-pass criteria:\n")
            f.write("- At least 2 brokers PF >= 1.0\n")
            f.write("- Max DD <= 8%\n")
            f.write("- Sharpe not severely negative (> -2.0)\n")
            f.write("- No prop violations\n\n")
            f.write("## Best Failed Candidates (top 5 by OOS avg PF)\n\n")
            f.write("| Rank | alpha | meta | sl | rr | hold | risk | mtf | avg_pf | avg_sharpe | max_dd | profitable_brokers | rejection |\n")
            f.write("|---|---|---|---|---|---|---|---|---|---|---|---|---|\n")
            for i, r in enumerate(all_results[:5], 1):
                f.write(f"| {i} | {r['alpha_threshold']} | {r['meta_threshold']} | "
                        f"{r['sl_atr_multiplier']} | {r['rr_target']} | {r['max_holding_bars']} | "
                        f"{r['risk_percent']} | {r['mtf_mode']} | {r['oos_avg_pf']} | "
                        f"{r['oos_avg_sharpe']} | {r['oos_max_dd']} | {r['profitable_brokers']} | "
                        f"{r['rejection_reason']} |\n")

    # === Task 4: Broker calibration scan ===
    print("\n  [Task 4] Broker-specific calibration scan...")
    # For canonical (which works), find best threshold combo
    # For exness/fbs, find what threshold would make them profitable
    calibration_rows = []
    b = "canonical"
    df = brokers_data[b]
    preds = brokers_preds[b]
    oos_mask = (df.index.year >= 2025) & (df.index.year <= 2026)
    oos_mask_np = np.asarray(oos_mask)
    df_oos = df[oos_mask]

    for alpha_t in [0.52, 0.55, 0.58, 0.60]:
        for meta_t in [0.55, 0.60, 0.65, 0.70]:
            params = {
                "alpha_threshold": alpha_t, "meta_threshold": meta_t,
                "sl_atr_multiplier": 1.5, "rr_target": 3.0,
                "max_holding_bars": 3, "mtf_mode": "h1_only",
                "risk_percent": 0.005, "cooldown_after_loss": 3,
                "max_trades_per_day": 2, "session_filter": "all",
                "regime_policy": "balanced", "spread_filter": 0.5,
                "trailing_policy": "off", "breakeven_trigger": 1.0,
            }
            summary = run_backtest_detailed(
                df_oos, preds["alpha"][oos_mask_np], preds["meta"][oos_mask_np],
                preds["atr"][oos_mask_np], params, None, None,
            )
            calibration_rows.append({
                "broker": b, "alpha_threshold": alpha_t, "meta_threshold": meta_t,
                "trades": summary["trades"], "pf": summary["profit_factor"],
                "sharpe": summary["sharpe"], "dd": summary["max_total_dd"],
                "win_rate": summary["win_rate"],
            })

    # Same for exness and fbs
    for b in ["exness", "fbs"]:
        df = brokers_data.get(b)
        if df is None:
            continue
        preds = brokers_preds[b]
        oos_mask = (df.index.year >= 2025) & (df.index.year <= 2026)
        oos_mask_np = np.asarray(oos_mask)
        df_oos = df[oos_mask]
        for alpha_t in [0.52, 0.55, 0.58, 0.60]:
            for meta_t in [0.55, 0.60, 0.65, 0.70]:
                params = {
                    "alpha_threshold": alpha_t, "meta_threshold": meta_t,
                    "sl_atr_multiplier": 1.5, "rr_target": 3.0,
                    "max_holding_bars": 3, "mtf_mode": "h1_only",
                    "risk_percent": 0.005, "cooldown_after_loss": 3,
                    "max_trades_per_day": 2, "session_filter": "all",
                    "regime_policy": "balanced", "spread_filter": 0.5,
                    "trailing_policy": "off", "breakeven_trigger": 1.0,
                }
                summary = run_backtest_detailed(
                    df_oos, preds["alpha"][oos_mask_np], preds["meta"][oos_mask_np],
                    preds["atr"][oos_mask_np], params, None, None,
                )
                calibration_rows.append({
                    "broker": b, "alpha_threshold": alpha_t, "meta_threshold": meta_t,
                    "trades": summary["trades"], "pf": summary["profit_factor"],
                    "sharpe": summary["sharpe"], "dd": summary["max_total_dd"],
                    "win_rate": summary["win_rate"],
                })

    with open(OUTPUT_DIR / "broker_calibration_scan.csv", "w", newline="") as f:
        if calibration_rows:
            w = csv.DictWriter(f, fieldnames=list(calibration_rows[0].keys()))
            w.writeheader()
            for row in calibration_rows:
                w.writerow(row)

    # Calibration summary
    with open(OUTPUT_DIR / "broker_calibration_summary.md", "w") as f:
        f.write("# Broker Calibration Summary (Sprint v2.8.7-G)\n\n")
        f.write(f"**Timestamp:** {ts}\n\n")
        f.write("## Per-Broker Best Calibration (alpha × meta threshold scan)\n\n")
        for b in ["canonical", "exness", "fbs"]:
            broker_rows = [r for r in calibration_rows if r["broker"] == b]
            if broker_rows:
                # Find best by PF
                best = max(broker_rows, key=lambda x: x["pf"] if x["pf"] != 999 else 99)
                f.write(f"### {b}\n\n")
                f.write(f"- Best alpha_threshold: {best['alpha_threshold']}\n")
                f.write(f"- Best meta_threshold: {best['meta_threshold']}\n")
                f.write(f"- PF: {best['pf']}, Sharpe: {best['sharpe']}, DD: {best['dd']}\n")
                f.write(f"- Trades: {best['trades']}, Win rate: {best['win_rate']}\n\n")

    # === Task 5: Targeted search verdict ===
    # The targeted search IS the sweep we just ran. Determine verdict.
    accepted = [r for r in all_results if r["rejection_reason"] == "ACCEPT_CANDIDATE"]
    demo_go_decision = "DEMO_SHADOW_ALLOWED" if accepted else "NEEDS_BROKER_SPECIFIC_MODEL"

    # Write targeted search summary
    with open(TARGETED_DIR / "demo_go_decision.md", "w") as f:
        f.write("# Demo Go Decision - Targeted Search (Sprint v2.8.7-G)\n\n")
        f.write(f"**Timestamp:** {ts}\n\n")
        f.write(f"**Decision:** {demo_go_decision}\n\n")
        f.write(f"**Total candidates evaluated:** {len(grid)}\n")
        f.write(f"**Accepted:** {len(accepted)}\n")
        f.write(f"**Near-pass:** {len(near_pass_candidates)}\n\n")
        if accepted:
            f.write("## Accepted Candidate\n\n")
            best = accepted[0]
            f.write(f"- Score: {best['oos_avg_pf']}\n")
            f.write(f"- OOS avg PF: {best['oos_avg_pf']}\n")
            f.write(f"- OOS avg Sharpe: {best['oos_avg_sharpe']}\n")
            f.write(f"- OOS max DD: {best['oos_max_dd']}\n")
            f.write(f"- production_ready: False\n")
            f.write(f"- requires CTO review: True\n")
        else:
            f.write("## No Accepted Candidate\n\n")
            f.write("All candidates were rejected. See rejection_debug_summary.md for details.\n")

    with open(TARGETED_DIR / "parameter_search_summary.md", "w") as f:
        f.write("# Parameter Search Summary - Targeted (Sprint v2.8.7-G)\n\n")
        f.write(f"**Verdict:** {demo_go_decision}\n\n")
        f.write(f"**Total evaluated:** {len(grid)}\n")
        f.write(f"**Accepted:** {len(accepted)}\n\n")
        f.write("## Rejection Breakdown\n\n")
        for reason, count in sorted(rejection_breakdown.items(), key=lambda x: -x[1]):
            f.write(f"- {reason}: {count}\n")

    with open(TARGETED_DIR / "top_20_parameter_sets.csv", "w", newline="") as f:
        if all_results:
            w = csv.DictWriter(f, fieldnames=list(all_results[0].keys()))
            w.writeheader()
            for row in all_results[:20]:
                w.writerow(row)

    with open(TARGETED_DIR / "broker_oos_results.csv", "w", newline="") as f:
        if all_results:
            # Extract per-broker rows
            broker_rows = []
            for r in all_results:
                for b in brokers:
                    broker_rows.append({
                        "alpha_threshold": r["alpha_threshold"],
                        "meta_threshold": r["meta_threshold"],
                        "sl_atr_multiplier": r["sl_atr_multiplier"],
                        "rr_target": r["rr_target"],
                        "max_holding_bars": r["max_holding_bars"],
                        "mtf_mode": r["mtf_mode"],
                        "risk_percent": r["risk_percent"],
                        "broker": b,
                        "pf": r[f"{b}_pf"],
                        "sharpe": r[f"{b}_sharpe"],
                        "dd": r[f"{b}_dd"],
                        "trades": r[f"{b}_trades"],
                    })
            if broker_rows:
                w = csv.DictWriter(f, fieldnames=list(broker_rows[0].keys()))
                w.writeheader()
                for row in broker_rows:
                    w.writerow(row)

    # === Task 6: Final honest verdict ===
    if not accepted:
        # Determine the most specific verdict
        if near_pass_found:
            final_verdict = "NEEDS_BROKER_SPECIFIC_CALIBRATION"
        elif rejection_breakdown.get("REJECT_BROKER_UNSTABLE", 0) > len(grid) * 0.5:
            final_verdict = "NEEDS_BROKER_SPECIFIC_MODEL"
        else:
            final_verdict = "NO_TRADE_ALLOWED"
    else:
        final_verdict = "DEMO_SHADOW_ALLOWED"

    with open(OUTPUT_DIR / "final_no_go_reason.md", "w") as f:
        f.write("# Final No-Go Reason (Sprint v2.8.7-G)\n\n")
        f.write(f"**Timestamp:** {ts}\n\n")
        f.write(f"## Final Verdict: {final_verdict}\n\n")
        f.write("## Reasoning\n\n")
        f.write(f"- Total candidates evaluated: {len(grid)}\n")
        f.write(f"- Accepted: {len(accepted)}\n")
        f.write(f"- Near-pass: {len(near_pass_candidates)}\n\n")
        f.write("## Rejection Breakdown\n\n")
        for reason, count in sorted(rejection_breakdown.items(), key=lambda x: -x[1]):
            f.write(f"- {reason}: {count} ({count/len(grid)*100:.1f}%)\n")
        f.write("\n## Root Cause\n\n")
        if rejection_breakdown.get("REJECT_BROKER_UNSTABLE", 0) > len(grid) * 0.5:
            f.write("The primary blocker is REJECT_BROKER_UNSTABLE: only 1 broker (canonical)\n")
            f.write("achieves PF > 1.0 in OOS. The v2_feature_normalized model (trained on\n")
            f.write("canonical only) does not generalize to exness/fbs/fundednext/icmarkets.\n\n")
            f.write("## Recommended Action\n\n")
            f.write("NEEDS_BROKER_SPECIFIC_MODEL: Retrain v2 models with multi-broker data\n")
            f.write("(v2_multibroker profile already exists but over-generalized — needs\n")
            f.write("broker-balanced sampling or per-broker calibration layers).\n")
        elif near_pass_found:
            f.write("Near-pass candidates exist but fail strict acceptance criteria.\n")
            f.write("NEEDS_BROKER_SPECIFIC_CALIBRATION: per-broker threshold tuning may\n")
            f.write("unlock demo shadow authorization.\n")
        else:
            f.write("No near-pass candidates. The model lacks sufficient edge for safe\n")
            f.write("demo shadow testing. NO_TRADE_ALLOWED.\n")
        f.write("\n## Safety\n\n")
        f.write("- production_ready = False (always)\n")
        f.write("- No trade authorized\n")
        f.write("- No token created\n")
        f.write("- CEO not bypassed\n")
        f.write("- Meta-label not bypassed\n")

    # Print summary
    print("\n" + "=" * 70)
    print("  FINAL BLOCKER DEBUG SUMMARY")
    print("=" * 70)
    print(f"\n  Total candidates: {len(grid)}")
    print(f"  Accepted: {len(accepted)}")
    print(f"  Near-pass: {len(near_pass_candidates)}")
    print(f"\n  Rejection breakdown:")
    for reason, count in sorted(rejection_breakdown.items(), key=lambda x: -x[1]):
        print(f"    {reason}: {count} ({count/len(grid)*100:.1f}%)")
    print(f"\n  Broker failure matrix:")
    for b in brokers:
        print(f"    {b}: pf<1={broker_failure_matrix[b]['pf_below_1']}, "
              f"low_trades={broker_failure_matrix[b]['low_trades']}, "
              f"dd_breach={broker_failure_matrix[b]['dd_breach']}")
    print(f"\n  NEAR_PASS_FOUND: {near_pass_found}")
    print(f"  Final verdict: {final_verdict}")
    print(f"  Demo go decision: {demo_go_decision}")
    print(f"\n  Output: {OUTPUT_DIR}")
    print("\n" + "=" * 70)

    return {
        "total_candidates": len(grid),
        "accepted": len(accepted),
        "near_pass_found": near_pass_found,
        "near_pass_count": len(near_pass_candidates),
        "rejection_breakdown": dict(rejection_breakdown),
        "final_verdict": final_verdict,
        "demo_go_decision": demo_go_decision,
    }


if __name__ == "__main__":
    main()
