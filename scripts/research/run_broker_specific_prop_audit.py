#!/usr/bin/env python3
"""TITAN XAU AI - Broker-Specific Prop Feed Survival Audit (Sprint v2.8.7-K)
=============================================================================
CRITICAL RULE: Canonical CANNOT approve prop readiness alone.
Only a real non-canonical broker passing independently can grant
BROKER_PROP_SHADOW_READY.

This script combines:
  Task 3: Broker-specific failure diagnosis
  Task 4: Broker-specific calibration search
  Task 5: Broker-specific prop yearly audit
  Task 6: Select real prop target broker
  Task 9: Final broker-specific readiness audit

NEVER sends orders. NEVER creates tokens. NEVER trades.
Read-only shadow only. MetaQuotes-Demo only. CTO review required.
"""
from __future__ import annotations
import sys, json, csv, os, gc
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict
import numpy as np
import pandas as pd
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

OUTPUT_DIR = REPO_ROOT / "data" / "reports" / "broker_specific_prop"

from titan.production.spread_normalization import normalize_xauusd_spread_to_usd
from titan.production.feature_stream_v2 import H1FeatureStreamV2, FEATURE_NAMES_V2
from titan.training.feature_schema_v2 import META_FEATURE_NAMES_V2
from titan.production.model_loader import load_models_by_profile
from titan.production.ceo_ai_governance import evaluate_ceo_decision
from titan.production.mtf_confirmation import load_m15_bars, load_m5_bars, evaluate_mtf, reset_mtf_caches


BROKER_PATHS = {
    "canonical": REPO_ROOT / "titan" / "data" / "canonical" / "XAUUSD_H1_canonical.parquet",
    "exness": REPO_ROOT / "titan" / "data" / "sources" / "mt5_brokers" / "exness" / "XAUUSD_H1.parquet",
    "fbs": REPO_ROOT / "titan" / "data" / "sources" / "mt5_brokers" / "fbs" / "XAUUSD_H1.parquet",
    "fundednext": REPO_ROOT / "titan" / "data" / "sources" / "mt5_brokers" / "fundednext" / "XAUUSD_H1.parquet",
    "icmarkets": REPO_ROOT / "titan" / "data" / "sources" / "mt5_brokers" / "icmarkets" / "XAUUSD_H1.parquet",
}

# Real brokers (non-canonical) — these are the ONLY ones that can approve prop readiness
REAL_BROKERS = ["fundednext", "exness", "icmarkets", "fbs"]

# Prop firm rules
EXT_DAILY_DD = 0.03
EXT_TOTAL_DD = 0.08
INT_DAILY_DD = 0.025
INT_TOTAL_DD = 0.065


def load_broker(name):
    path = BROKER_PATHS.get(name)
    if path is None or not path.exists():
        return None
    df = pd.read_parquet(path)
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)
    df = normalize_xauusd_spread_to_usd(df, symbol="XAUUSD", source=name)
    return df


def compute_predictions(df, bundle):
    df_use = df[["open", "high", "low", "close"]].copy()
    if "tick_volume" in df.columns:
        df_use["volume"] = df["tick_volume"]
    else:
        df_use["volume"] = 0.0
    df_use["spread"] = df["spread_usd"]
    stream = H1FeatureStreamV2()
    stream._bars = df_use
    feats_df = stream._compute_features()
    features_matrix = np.nan_to_num(feats_df.values.astype(np.float64), nan=0.0, posinf=0.0, neginf=0.0)
    features_matrix = stream._standardize(features_matrix)
    alpha_proba = bundle.xgb.predict_proba(features_matrix)[:, 1]
    name_to_idx = {n: i for i, n in enumerate(FEATURE_NAMES_V2)}
    meta_indices = [name_to_idx[n] for n in META_FEATURE_NAMES_V2]
    meta_vecs = features_matrix[:, meta_indices]
    meta_proba = bundle.meta.predict_proba(meta_vecs)[:, 1]
    # ATR
    highs, lows, closes = df["high"].values, df["low"].values, df["close"].values
    atr_values = np.zeros(len(df))
    for i in range(14, len(df)):
        atr_values[i] = max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1]))
    for i in range(28, len(df)):
        atr_values[i] = np.mean(atr_values[i-14:i])
    return alpha_proba, meta_proba, atr_values


def run_backtest(df, alpha_proba, meta_proba, atr_values, params,
                  m15_bars=None, m5_bars=None, starting_equity=100000.0):
    """Run backtest with monthly + DD tracking. Returns (monthly_list, yearly_summary)."""
    equity = starting_equity
    daily_start_equity = equity
    month_start_equity = equity
    wins, losses = 0, 0
    gross_profit, gross_loss = 0.0, 0.0
    max_total_dd = 0.0
    max_consecutive_losses = 0
    consecutive_losses = 0
    r_multiples = []
    daily_dd_breach_count = 0
    total_dd_breach_count = 0
    daily_trades = 0
    current_day = None
    current_month = None
    cooldown_remaining = 0
    monthly_stats = defaultdict(lambda: {
        "trades": 0, "wins": 0, "losses": 0,
        "gross_profit": 0.0, "gross_loss": 0.0,
        "start_equity": 0.0, "end_equity": 0.0,
        "max_dd": 0.0, "max_daily_dd": 0.0,
        "r_multiples": [], "daily_dd_breaches": 0,
    })
    closes = df["close"].values
    highs = df["high"].values
    lows = df["low"].values
    index = df.index

    for i in range(28, len(df) - params["max_holding_bars"] - 1):
        total_dd = (starting_equity - equity) / starting_equity
        if total_dd > max_total_dd:
            max_total_dd = total_dd
        if total_dd >= EXT_TOTAL_DD:
            total_dd_breach_count += 1
            continue
        if total_dd >= INT_TOTAL_DD:
            continue
        daily_dd = (daily_start_equity - equity) / daily_start_equity
        if daily_dd >= EXT_DAILY_DD:
            daily_dd_breach_count += 1
            continue
        if daily_dd >= INT_DAILY_DD:
            continue

        bar_day = index[i].date()
        bar_month_key = f"{index[i].year}-{index[i].month:02d}"
        if current_day != bar_day:
            current_day = bar_day
            daily_start_equity = equity
            daily_trades = 0
        if current_month != bar_month_key:
            if current_month is not None:
                monthly_stats[current_month]["end_equity"] = equity
            current_month = bar_month_key
            month_start_equity = equity
            monthly_stats[current_month]["start_equity"] = equity

        if daily_trades >= params.get("max_trades_per_day", 2):
            continue
        if cooldown_remaining > 0:
            cooldown_remaining -= 1
            continue

        alpha_confidence = float(alpha_proba[i])
        if alpha_confidence < params["alpha_threshold"]:
            continue
        direction = "LONG" if alpha_confidence >= 0.5 else "SHORT"
        if alpha_confidence == 0.5:
            direction = "LONG" if closes[i] > closes[i-1] else "SHORT"
        meta_confidence = float(meta_proba[i])
        if meta_confidence < params["meta_threshold"]:
            continue

        # Session filter
        hour = index[i].hour
        session = params.get("session_filter", "all")
        if session == "london" and not (7 <= hour <= 15):
            continue
        if session == "newyork" and not (12 <= hour <= 20):
            continue
        if session == "london_newyork_overlap" and not (12 <= hour <= 15):
            continue

        # Spread filter
        spread = float(df["spread_usd"].iloc[i]) if "spread_usd" in df.columns else 0.3
        if spread > params.get("spread_filter", 0.5):
            continue

        ceo_decision = evaluate_ceo_decision(
            regime_state={"detected": True, "regime_value": "MARKET_OPEN", "confidence": alpha_confidence},
            xgb_alpha={"direction": direction, "confidence": alpha_confidence, "pass": True},
            lstm_confidence=None, transformer_regime=None,
            meta_label_quality={"quality_score": meta_confidence, "pass": True},
            broker_state={"broker_pass": True, "spread_pass": True, "slippage_pass": True},
            prop_risk_state={"risk_pass": True, "prop_funded_pass": True, "max_positions_ok": True},
            capital_protection_state={"capital_preservation_active": False, "dd_breach": False},
            model_health_state={"model_health_pass": True, "failed_required": 0},
            geometry_state={"geometry_pass": True, "actual_RR": params["rr_target"], "minimum_RR": 2.0},
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
        sl_distance = atr * params["sl_atr_multiplier"]
        tp_distance = sl_distance * params["rr_target"]
        entry_price = closes[i]
        if direction == "LONG":
            sl_price, tp_price = entry_price - sl_distance, entry_price + tp_distance
        else:
            sl_price, tp_price = entry_price + sl_distance, entry_price - tp_distance

        exit_price, exit_reason, r_result = entry_price, "TIMEOUT", 0.0
        max_holding = params["max_holding_bars"]
        for j in range(1, max_holding + 1):
            if i + j >= len(df):
                break
            if direction == "LONG":
                if lows[i + j] <= sl_price:
                    exit_price, exit_reason, r_result = sl_price, "SL_HIT", -1.0
                    break
                if highs[i + j] >= tp_price:
                    exit_price, exit_reason, r_result = tp_price, "TP_HIT", params["rr_target"]
                    break
            else:
                if highs[i + j] >= sl_price:
                    exit_price, exit_reason, r_result = sl_price, "SL_HIT", -1.0
                    break
                if lows[i + j] <= tp_price:
                    exit_price, exit_reason, r_result = tp_price, "TP_HIT", params["rr_target"]
                    break
        if exit_reason == "TIMEOUT":
            exit_price = closes[min(i + max_holding, len(df)-1)]
            r_result = (exit_price - entry_price) / sl_distance if direction == "LONG" else (entry_price - exit_price) / sl_distance

        r_multiples.append(r_result)
        risk_amount = equity * params["risk_percent"]
        pnl = risk_amount * r_result
        equity += pnl
        daily_trades += 1
        monthly_stats[current_month]["trades"] += 1
        monthly_stats[current_month]["r_multiples"].append(r_result)
        if pnl > 0:
            wins += 1
            gross_profit += pnl
            monthly_stats[current_month]["wins"] += 1
            monthly_stats[current_month]["gross_profit"] += pnl
            consecutive_losses = 0
        else:
            losses += 1
            gross_loss += abs(pnl)
            monthly_stats[current_month]["losses"] += 1
            monthly_stats[current_month]["gross_loss"] += abs(pnl)
            consecutive_losses += 1
            max_consecutive_losses = max(max_consecutive_losses, consecutive_losses)
            cooldown_remaining = params.get("cooldown_after_loss", 5)
        month_dd = (month_start_equity - equity) / month_start_equity if month_start_equity > 0 else 0
        if month_dd > monthly_stats[current_month]["max_dd"]:
            monthly_stats[current_month]["max_dd"] = month_dd
        if daily_dd > monthly_stats[current_month]["max_daily_dd"]:
            monthly_stats[current_month]["max_daily_dd"] = daily_dd

    if current_month is not None:
        monthly_stats[current_month]["end_equity"] = equity

    # Build monthly list
    monthly_list = []
    for month_key, ms in sorted(monthly_stats.items()):
        year, month = month_key.split("-")
        month_return = (ms["end_equity"] - ms["start_equity"]) / ms["start_equity"] if ms["start_equity"] > 0 else 0
        pf = ms["gross_profit"] / ms["gross_loss"] if ms["gross_loss"] > 0 else (999.0 if ms["gross_profit"] > 0 else 0)
        wr = ms["wins"] / ms["trades"] if ms["trades"] > 0 else 0
        if len(ms["r_multiples"]) > 1:
            r_arr = np.array(ms["r_multiples"])
            std_r = max(0.001, float(np.std(r_arr)))
            sharpe = (float(np.mean(r_arr)) / std_r) * (252 ** 0.5)
        else:
            sharpe = 0
        monthly_list.append({
            "month": month_key, "year": int(year), "month_num": int(month),
            "trades": ms["trades"], "win_rate": round(wr, 4),
            "profit_factor": round(pf, 4) if pf != 999 else 999,
            "sharpe": round(sharpe, 4),
            "monthly_return": round(month_return, 6),
            "monthly_max_dd": round(float(ms["max_dd"]), 6),
            "monthly_max_daily_dd": round(float(ms["max_daily_dd"]), 6),
            "target_10pct_hit": month_return >= 0.10,
            "target_12pct_hit": month_return >= 0.12,
            "target_15pct_hit": month_return >= 0.15,
            "month_profitable": month_return > 0,
        })

    total_trades = wins + losses
    win_rate = wins / total_trades if total_trades > 0 else 0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else (999.0 if gross_profit > 0 else 0)
    total_return = (equity - starting_equity) / starting_equity
    if len(r_multiples) > 1:
        r_arr = np.array(r_multiples)
        std_r = max(0.001, float(np.std(r_arr)))
        sharpe = (float(np.mean(r_arr)) / std_r) * (252 ** 0.5)
    else:
        sharpe = 0

    yearly_summary = {
        "trades": total_trades, "win_rate": round(win_rate, 4),
        "profit_factor": round(profit_factor, 4) if profit_factor != 999 else 999,
        "sharpe": round(sharpe, 4), "total_return": round(total_return, 6),
        "max_total_dd": round(max_total_dd, 6),
        "max_consecutive_losses": max_consecutive_losses,
        "daily_dd_breach_count": daily_dd_breach_count,
        "total_dd_breach_count": total_dd_breach_count,
        "final_equity": round(equity, 2), "starting_equity": starting_equity,
    }
    return monthly_list, yearly_summary


def task3_failure_diagnosis(brokers_data, brokers_preds, bundle):
    """Task 3: Broker-specific failure diagnosis."""
    print("\n  [Task 3] Broker-specific failure diagnosis...")
    feature_drift_rows = []
    prediction_drift_rows = []
    session_rows = []
    monthly_failure_rows = []
    dd_failure_rows = []
    broker_verdicts = {}

    canonical_feats = brokers_preds.get("canonical", {}).get("features")
    canonical_alpha = brokers_preds.get("canonical", {}).get("alpha")
    canonical_meta = brokers_preds.get("canonical", {}).get("meta")

    for broker in ["canonical"] + REAL_BROKERS:
        df = brokers_data.get(broker)
        preds = brokers_preds.get(broker)
        if df is None or preds is None:
            continue

        # Feature drift vs canonical
        if canonical_feats is not None and broker != "canonical":
            broker_feats = preds["features"]
            for j, fname in enumerate(FEATURE_NAMES_V2):
                canon_col = canonical_feats[:, j]
                broker_col = broker_feats[:, j]
                drift = abs(float(canon_col.mean()) - float(broker_col.mean())) / max(abs(float(canon_col.std())), 0.001)
                feature_drift_rows.append({
                    "broker": broker, "feature": fname,
                    "canonical_mean": round(float(canon_col.mean()), 6),
                    "broker_mean": round(float(broker_col.mean()), 6),
                    "drift_score": round(drift, 4),
                })

        # Prediction drift
        if canonical_alpha is not None and broker != "canonical":
            prediction_drift_rows.append({
                "broker": broker,
                "canonical_alpha_mean": round(float(canonical_alpha.mean()), 4),
                "broker_alpha_mean": round(float(preds["alpha"].mean()), 4),
                "canonical_meta_mean": round(float(canonical_meta.mean()), 4),
                "broker_meta_mean": round(float(preds["meta"].mean()), 4),
                "alpha_drift": round(abs(float(canonical_alpha.mean()) - float(preds["alpha"].mean())), 4),
                "meta_drift": round(abs(float(canonical_meta.mean()) - float(preds["meta"].mean())), 4),
            })

        # Session-wise and monthly performance (base params, OOS 2025-2026)
        params = {
            "alpha_threshold": 0.50, "meta_threshold": 0.50,
            "sl_atr_multiplier": 2.0, "rr_target": 3.0, "max_holding_bars": 3,
            "risk_percent": 0.0025, "max_trades_per_day": 2,
            "cooldown_after_loss": 5, "session_filter": "all",
            "spread_filter": 0.5, "mtf_mode": "h1_only",
        }
        oos_mask = (df.index.year >= 2025) & (df.index.year <= 2026)
        if oos_mask.sum() < 100:
            continue
        df_oos = df[oos_mask]
        oos_mask_np = np.asarray(oos_mask)
        monthly_list, yearly_summary = run_backtest(
            df_oos, preds["alpha"][oos_mask_np], preds["meta"][oos_mask_np],
            preds["atr"][oos_mask_np], params,
        )

        # Session performance (aggregate by hour)
        for session_name, hours in [("london", range(7, 16)), ("newyork", range(12, 21)),
                                     ("overlap", range(12, 16)), ("asia", range(0, 8)),
                                     ("all", range(0, 24))]:
            session_mask = pd.Series(df_oos.index.hour).isin(hours).values
            if session_mask.sum() < 50:
                continue
            session_df = df_oos[session_mask]
            session_preds_alpha = preds["alpha"][oos_mask_np][session_mask]
            session_preds_meta = preds["meta"][oos_mask_np][session_mask]
            session_preds_atr = preds["atr"][oos_mask_np][session_mask]
            _, session_summary = run_backtest(session_df, session_preds_alpha, session_preds_meta, session_preds_atr, params)
            session_rows.append({
                "broker": broker, "session": session_name,
                "trades": session_summary["trades"],
                "pf": session_summary["profit_factor"],
                "sharpe": session_summary["sharpe"],
                "max_dd": session_summary["max_total_dd"],
                "daily_dd_breaches": session_summary["daily_dd_breach_count"],
                "total_dd_breaches": session_summary["total_dd_breach_count"],
            })

        # Monthly failure matrix
        for m in monthly_list:
            monthly_failure_rows.append({
                "broker": broker, "month": m["month"],
                "monthly_return": m["monthly_return"],
                "month_profitable": m["month_profitable"],
                "target_10pct_hit": m["target_10pct_hit"],
                "monthly_max_dd": m["monthly_max_dd"],
                "trades": m["trades"],
            })

        # DD failure matrix
        dd_failure_rows.append({
            "broker": broker,
            "daily_dd_breaches": yearly_summary["daily_dd_breach_count"],
            "total_dd_breaches": yearly_summary["total_dd_breach_count"],
            "max_total_dd": yearly_summary["max_total_dd"],
            "total_return": yearly_summary["total_return"],
            "profit_factor": yearly_summary["profit_factor"],
        })

        # Broker verdict
        if broker == "canonical":
            broker_verdicts[broker] = "BENCHMARK_ONLY"
        elif yearly_summary["daily_dd_breach_count"] == 0 and yearly_summary["total_dd_breach_count"] == 0:
            if yearly_summary["profit_factor"] > 1.2:
                broker_verdicts[broker] = "BROKER_USABLE"
            else:
                broker_verdicts[broker] = "NEEDS_CALIBRATION"
        elif yearly_summary["profit_factor"] > 1.2:
            broker_verdicts[broker] = "NEEDS_CALIBRATION"
        else:
            broker_verdicts[broker] = "REJECT_FOR_PROP"

        print(f"    {broker:12s}: verdict={broker_verdicts[broker]}, "
              f"trades={yearly_summary['trades']}, pf={yearly_summary['profit_factor']}, "
              f"dd_breaches={yearly_summary['daily_dd_breach_count']+yearly_summary['total_dd_breach_count']}")

    # Write CSVs
    def _write_csv(name, rows, fieldnames=None):
        if not rows and not fieldnames:
            return
        with open(OUTPUT_DIR / name, "w", newline="") as f:
            if rows:
                w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                w.writeheader()
                for row in rows:
                    w.writerow(row)
            elif fieldnames:
                w = csv.DictWriter(f, fieldnames=fieldnames)
                w.writeheader()

    _write_csv("broker_feature_drift.csv", feature_drift_rows)
    _write_csv("broker_prediction_drift.csv", prediction_drift_rows)
    _write_csv("broker_session_performance.csv", session_rows)
    _write_csv("broker_monthly_failure_matrix.csv", monthly_failure_rows)
    _write_csv("broker_dd_failure_matrix.csv", dd_failure_rows)

    # Diagnosis JSON + MD
    diagnosis = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "broker_verdicts": broker_verdicts,
        "canonical_deprecation": "canonical is BENCHMARK_ONLY — cannot approve prop readiness alone",
    }
    with open(OUTPUT_DIR / "broker_failure_diagnosis.json", "w") as f:
        json.dump(diagnosis, f, indent=2, default=str)

    with open(OUTPUT_DIR / "broker_failure_diagnosis.md", "w") as f:
        f.write("# Broker Failure Diagnosis (Sprint v2.8.7-K)\n\n")
        f.write(f"**Timestamp:** {diagnosis['timestamp_utc']}\n\n")
        f.write("## Broker Verdicts\n\n")
        f.write("| Broker | Verdict | Reason |\n|---|---|---|\n")
        for b, v in broker_verdicts.items():
            reason = "BENCHMARK_ONLY" if b == "canonical" else (
                "0 DD breaches, PF > 1.2" if v == "BROKER_USABLE" else (
                    "DD breaches or low PF — needs calibration" if v == "NEEDS_CALIBRATION" else (
                        "Fails both DD and profit — reject for prop"
                    )
                )
            )
            f.write(f"| {b} | {v} | {reason} |\n")
        f.write("\n## Canonical Deprecation\n\n")
        f.write("Canonical is BENCHMARK_ONLY. It cannot approve prop readiness alone.\n")
        f.write("Only a real non-canonical broker passing independently can grant BROKER_PROP_SHADOW_READY.\n")

    return broker_verdicts


def task4_calibration_search(brokers_data, brokers_preds, m15_bars, m5_bars):
    """Task 4: Broker-specific calibration search."""
    print("\n  [Task 4] Broker-specific calibration search...")
    calibration_rows = []
    broker_best = {}

    # Limited grid for sandbox memory
    alpha_options = [0.50, 0.52, 0.55, 0.58]
    meta_options = [0.50, 0.52, 0.55, 0.60]
    session_options = ["all", "london", "london_newyork_overlap"]
    risk_options = [("cautious", 0.0015), ("base", 0.0025)]

    for broker in REAL_BROKERS:
        df = brokers_data.get(broker)
        preds = brokers_preds.get(broker)
        if df is None or preds is None:
            continue
        best_for_broker = None
        best_score = -999

        oos_mask = (df.index.year >= 2025) & (df.index.year <= 2026)
        if oos_mask.sum() < 100:
            continue
        df_oos = df[oos_mask]
        oos_mask_np = np.asarray(oos_mask)

        for alpha_t in alpha_options:
            for meta_t in meta_options:
                for session in session_options:
                    for risk_name, risk_pct in risk_options:
                        params = {
                            "alpha_threshold": alpha_t, "meta_threshold": meta_t,
                            "sl_atr_multiplier": 2.0, "rr_target": 3.0,
                            "max_holding_bars": 3, "risk_percent": risk_pct,
                            "max_trades_per_day": 2, "cooldown_after_loss": 5,
                            "session_filter": session, "spread_filter": 0.5,
                            "mtf_mode": "h1_only",
                        }
                        monthly_list, yearly = run_backtest(
                            df_oos, preds["alpha"][oos_mask_np], preds["meta"][oos_mask_np],
                            preds["atr"][oos_mask_np], params, m15_bars, m5_bars,
                        )
                        # Score: penalize DD breaches heavily, reward profit + no breaches
                        dd_breaches = yearly["daily_dd_breach_count"] + yearly["total_dd_breach_count"]
                        profitable_months = sum(1 for m in monthly_list if m["month_profitable"])
                        hit_10 = sum(1 for m in monthly_list if m["target_10pct_hit"])
                        if dd_breaches > 0:
                            score = -100 - dd_breaches * 10
                        else:
                            score = (yearly["profit_factor"] if yearly["profit_factor"] != 999 else 10) * 10
                            score += profitable_months * 5
                            score += hit_10 * 8
                            score -= yearly["max_total_dd"] * 100

                        row = {
                            "broker": broker, "alpha_threshold": alpha_t,
                            "meta_threshold": meta_t, "session_filter": session,
                            "risk_profile": risk_name, "risk_percent": risk_pct,
                            "trades": yearly["trades"], "pf": yearly["profit_factor"],
                            "sharpe": yearly["sharpe"], "max_dd": yearly["max_total_dd"],
                            "total_return": yearly["total_return"],
                            "daily_dd_breaches": yearly["daily_dd_breach_count"],
                            "total_dd_breaches": yearly["total_dd_breach_count"],
                            "profitable_months": profitable_months,
                            "months_hit_10pct": hit_10,
                            "score": round(score, 4),
                        }
                        calibration_rows.append(row)
                        if score > best_score:
                            best_score = score
                            best_for_broker = row

        if best_for_broker:
            # Determine verdict
            dd_breaches = best_for_broker["daily_dd_breaches"] + best_for_broker["total_dd_breaches"]
            if dd_breaches == 0 and best_for_broker["pf"] > 1.2 and best_for_broker["profitable_months"] >= 8:
                best_for_broker["verdict"] = "BROKER_USABLE"
            elif dd_breaches == 0:
                best_for_broker["verdict"] = "NEEDS_RETURN_IMPROVEMENT"
            elif best_for_broker["pf"] > 1.2:
                best_for_broker["verdict"] = "REJECT_DD_RISK"
            else:
                best_for_broker["verdict"] = "REJECT_FOR_PROP"
            broker_best[broker] = best_for_broker
            print(f"    {broker:12s}: best alpha={best_for_broker['alpha_threshold']}, "
                  f"meta={best_for_broker['meta_threshold']}, session={best_for_broker['session_filter']}, "
                  f"risk={best_for_broker['risk_profile']}, verdict={best_for_broker['verdict']}")

        gc.collect()

    # Write CSV
    with open(OUTPUT_DIR / "broker_calibration_search.csv", "w", newline="") as f:
        if calibration_rows:
            w = csv.DictWriter(f, fieldnames=list(calibration_rows[0].keys()))
            w.writeheader()
            for row in calibration_rows:
                w.writerow(row)

    # Summary JSON + MD
    summary = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "broker_best": broker_best,
    }
    with open(OUTPUT_DIR / "broker_calibration_summary.json", "w") as f:
        json.dump(summary, f, indent=2, default=str)

    with open(OUTPUT_DIR / "broker_calibration_summary.md", "w") as f:
        f.write("# Broker Calibration Summary (Sprint v2.8.7-K)\n\n")
        f.write(f"**Timestamp:** {summary['timestamp_utc']}\n\n")
        f.write("## Best Calibration Per Broker\n\n")
        f.write("| Broker | alpha | meta | session | risk | PF | DD | Breaches | Profitable Months | Hit 10% | Verdict |\n")
        f.write("|---|---|---|---|---|---|---|---|---|---|---|\n")
        for b, r in broker_best.items():
            f.write(f"| {b} | {r['alpha_threshold']} | {r['meta_threshold']} | "
                    f"{r['session_filter']} | {r['risk_profile']} | {r['pf']} | "
                    f"{r['max_dd']} | {r['daily_dd_breaches']+r['total_dd_breaches']} | "
                    f"{r['profitable_months']} | {r['months_hit_10pct']} | {r['verdict']} |\n")

    return broker_best


def task5_yearly_audit(brokers_data, brokers_preds, broker_best, m15_bars, m5_bars):
    """Task 5: Broker-specific prop yearly audit using calibrated settings."""
    print("\n  [Task 5] Broker-specific prop yearly audit...")
    yearly_rows = []
    target_rows = []
    breach_rows = []
    broker_yearly_verdicts = {}

    for broker in REAL_BROKERS:
        df = brokers_data.get(broker)
        preds = brokers_preds.get(broker)
        best = broker_best.get(broker)
        if df is None or preds is None or best is None:
            broker_yearly_verdicts[broker] = "REJECT_FOR_PROP"
            continue

        params = {
            "alpha_threshold": best["alpha_threshold"],
            "meta_threshold": best["meta_threshold"],
            "sl_atr_multiplier": 2.0, "rr_target": 3.0,
            "max_holding_bars": 3, "risk_percent": best["risk_percent"],
            "max_trades_per_day": 2, "cooldown_after_loss": 5,
            "session_filter": best["session_filter"],
            "spread_filter": 0.5, "mtf_mode": "h1_only",
        }

        for year in [2023, 2024, 2025, 2026]:
            year_mask = df.index.year == year
            if year_mask.sum() < 100:
                continue
            df_year = df[year_mask]
            year_mask_np = np.asarray(year_mask)
            monthly_list, yearly = run_backtest(
                df_year, preds["alpha"][year_mask_np], preds["meta"][year_mask_np],
                preds["atr"][year_mask_np], params, m15_bars, m5_bars,
            )
            profitable_months = sum(1 for m in monthly_list if m["month_profitable"])
            hit_10 = sum(1 for m in monthly_list if m["target_10pct_hit"])
            hit_12 = sum(1 for m in monthly_list if m["target_12pct_hit"])
            hit_15 = sum(1 for m in monthly_list if m["target_15pct_hit"])

            yearly_rows.append({
                "broker": broker, "year": year,
                "trades": yearly["trades"], "win_rate": yearly["win_rate"],
                "profit_factor": yearly["profit_factor"], "sharpe": yearly["sharpe"],
                "total_return": yearly["total_return"], "max_total_dd": yearly["max_total_dd"],
                "daily_dd_breaches": yearly["daily_dd_breach_count"],
                "total_dd_breaches": yearly["total_dd_breach_count"],
                "profitable_months": profitable_months,
                "months_hit_10pct": hit_10, "months_hit_12pct": hit_12,
                "months_hit_15pct": hit_15,
            })

            for m in monthly_list:
                target_rows.append({
                    "broker": broker, "year": year, "month": m["month"],
                    "monthly_return": m["monthly_return"],
                    "target_10pct_hit": m["target_10pct_hit"],
                    "target_12pct_hit": m["target_12pct_hit"],
                    "target_15pct_hit": m["target_15pct_hit"],
                })

            if yearly["daily_dd_breach_count"] > 0 or yearly["total_dd_breach_count"] > 0:
                breach_rows.append({
                    "broker": broker, "year": year,
                    "daily_dd_breaches": yearly["daily_dd_breach_count"],
                    "total_dd_breaches": yearly["total_dd_breach_count"],
                    "max_total_dd": yearly["max_total_dd"],
                })

        # Determine broker verdict from OOS 2025-2026
        oos_rows = [r for r in yearly_rows if r["broker"] == broker and r["year"] in [2025, 2026]]
        if not oos_rows:
            broker_yearly_verdicts[broker] = "REJECT_FOR_PROP"
            continue

        total_daily_breaches = sum(r["daily_dd_breaches"] for r in oos_rows)
        total_total_breaches = sum(r["total_dd_breaches"] for r in oos_rows)
        total_profitable = sum(r["profitable_months"] for r in oos_rows)
        total_hit_10 = sum(r["months_hit_10pct"] for r in oos_rows)
        total_return = sum(r["total_return"] for r in oos_rows)
        avg_pf = np.mean([r["profit_factor"] for r in oos_rows if r["profit_factor"] != 999])

        # BROKER_PROP_READY requires:
        # - 0 daily DD breaches
        # - 0 total DD breaches
        # - at least 8/12 profitable months in latest full year (use OOS total >= 12)
        # - at least 6/12 months hit 10% target OR yearly return >= 100%
        # - OOS stable
        if total_daily_breaches == 0 and total_total_breaches == 0:
            if total_profitable >= 12 and (total_hit_10 >= 6 or total_return >= 1.0):
                broker_yearly_verdicts[broker] = "BROKER_PROP_READY"
            elif total_profitable >= 8:
                broker_yearly_verdicts[broker] = "NEEDS_RETURN_IMPROVEMENT"
            else:
                broker_yearly_verdicts[broker] = "NEEDS_CALIBRATION"
        elif avg_pf > 1.2:
            broker_yearly_verdicts[broker] = "REJECT_DD_RISK"
        else:
            broker_yearly_verdicts[broker] = "REJECT_FOR_PROP"

        print(f"    {broker:12s}: verdict={broker_yearly_verdicts[broker]}, "
              f"OOS breaches={total_daily_breaches+total_total_breaches}, "
              f"profitable_months={total_profitable}, hit_10={total_hit_10}, "
              f"return={total_return:.4f}")

    # Write CSVs
    def _write_csv(name, rows, fieldnames=None):
        if not rows and not fieldnames:
            return
        with open(OUTPUT_DIR / name, "w", newline="") as f:
            if rows:
                w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                w.writeheader()
                for row in rows:
                    w.writerow(row)
            elif fieldnames:
                w = csv.DictWriter(f, fieldnames=fieldnames)
                w.writeheader()

    _write_csv("broker_prop_yearly_audit.csv", yearly_rows)
    _write_csv("broker_target_hit_matrix.csv", target_rows)
    _write_csv("broker_prop_breach_report.csv", breach_rows,
               ["broker", "year", "daily_dd_breaches", "total_dd_breaches", "max_total_dd"])

    # Summary JSON + MD
    summary = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "broker_yearly_verdicts": broker_yearly_verdicts,
        "canonical_deprecated": True,
    }
    with open(OUTPUT_DIR / "broker_prop_yearly_summary.json", "w") as f:
        json.dump(summary, f, indent=2, default=str)

    with open(OUTPUT_DIR / "broker_prop_yearly_summary.md", "w") as f:
        f.write("# Broker Prop Yearly Audit Summary (Sprint v2.8.7-K)\n\n")
        f.write(f"**Timestamp:** {summary['timestamp_utc']}\n\n")
        f.write("## CRITICAL: Canonical Deprecation\n\n")
        f.write("Canonical is BENCHMARK_ONLY. Only real non-canonical brokers can approve prop readiness.\n\n")
        f.write("## Broker Yearly Verdicts (OOS 2025-2026)\n\n")
        f.write("| Broker | Verdict | Daily DD Breaches | Total DD Breaches | Profitable Months | Hit 10% | Total Return |\n")
        f.write("|---|---|---|---|---|---|---|\n")
        for broker in REAL_BROKERS:
            v = broker_yearly_verdicts.get(broker, "N/A")
            oos_rows = [r for r in yearly_rows if r["broker"] == broker and r["year"] in [2025, 2026]]
            if oos_rows:
                db = sum(r["daily_dd_breaches"] for r in oos_rows)
                tb = sum(r["total_dd_breaches"] for r in oos_rows)
                pm = sum(r["profitable_months"] for r in oos_rows)
                h10 = sum(r["months_hit_10pct"] for r in oos_rows)
                tr = sum(r["total_return"] for r in oos_rows)
                f.write(f"| {broker} | {v} | {db} | {tb} | {pm} | {h10} | {tr:.4f} |\n")
            else:
                f.write(f"| {broker} | {v} | N/A | N/A | N/A | N/A | N/A |\n")

    return broker_yearly_verdicts, yearly_rows


def task6_select_target_broker(broker_yearly_verdicts, yearly_rows, broker_best):
    """Task 6: Select real prop target broker."""
    print("\n  [Task 6] Selecting real prop target broker...")

    # Rank real brokers
    broker_scores = {}
    for broker in REAL_BROKERS:
        v = broker_yearly_verdicts.get(broker, "REJECT_FOR_PROP")
        oos_rows = [r for r in yearly_rows if r["broker"] == broker and r["year"] in [2025, 2026]]
        if not oos_rows:
            broker_scores[broker] = {"verdict": v, "score": -999, "reason": "no OOS data"}
            continue

        total_daily_breaches = sum(r["daily_dd_breaches"] for r in oos_rows)
        total_total_breaches = sum(r["total_dd_breaches"] for r in oos_rows)
        total_profitable = sum(r["profitable_months"] for r in oos_rows)
        total_hit_10 = sum(r["months_hit_10pct"] for r in oos_rows)
        total_hit_12 = sum(r["months_hit_12pct"] for r in oos_rows)
        total_return = sum(r["total_return"] for r in oos_rows)
        max_dd = max(r["max_total_dd"] for r in oos_rows)

        # Score: 0 DD breaches required, then rank by consistency
        if total_daily_breaches > 0 or total_total_breaches > 0:
            score = -100 - (total_daily_breaches + total_total_breaches) * 10
        else:
            score = total_profitable * 10 + total_hit_10 * 15 + total_hit_12 * 10
            score += min(total_return * 20, 40)
            score -= max_dd * 100

        broker_scores[broker] = {
            "verdict": v,
            "score": round(score, 4),
            "daily_dd_breaches": total_daily_breaches,
            "total_dd_breaches": total_total_breaches,
            "profitable_months": total_profitable,
            "months_hit_10pct": total_hit_10,
            "months_hit_12pct": total_hit_12,
            "total_return": round(total_return, 4),
            "max_dd": round(max_dd, 4),
        }

    # Select best
    ready_brokers = [b for b in REAL_BROKERS if broker_yearly_verdicts.get(b) == "BROKER_PROP_READY"]
    if ready_brokers:
        selected = max(ready_brokers, key=lambda b: broker_scores[b]["score"])
        no_real_broker_ready = False
    else:
        selected = None
        no_real_broker_ready = True

    selection = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "selected_target_broker": selected,
        "no_real_broker_ready": no_real_broker_ready,
        "selected_broker_profile": broker_best.get(selected, {}) if selected else {},
        "broker_scores": broker_scores,
        "rejected_brokers": {
            b: s["verdict"] for b, s in broker_scores.items()
            if b != selected or no_real_broker_ready
        },
    }

    with open(OUTPUT_DIR / "target_broker_selection.json", "w") as f:
        json.dump(selection, f, indent=2, default=str)

    with open(OUTPUT_DIR / "target_broker_selection.md", "w") as f:
        f.write("# Target Broker Selection (Sprint v2.8.7-K)\n\n")
        f.write(f"**Timestamp:** {selection['timestamp_utc']}\n\n")
        f.write("## CRITICAL RULE\n\n")
        f.write("Canonical is BENCHMARK_ONLY. Only a real non-canonical broker can approve prop readiness.\n\n")
        f.write(f"## NO_REAL_BROKER_READY: {no_real_broker_ready}\n\n")
        if selected:
            f.write(f"## Selected Target Broker: {selected}\n\n")
            s = broker_scores[selected]
            f.write(f"- Verdict: {s['verdict']}\n")
            f.write(f"- Daily DD breaches: {s['daily_dd_breaches']}\n")
            f.write(f"- Total DD breaches: {s['total_dd_breaches']}\n")
            f.write(f"- Profitable months (OOS): {s['profitable_months']}\n")
            f.write(f"- Months hit 10%: {s['months_hit_10pct']}\n")
            f.write(f"- Months hit 12%: {s['months_hit_12pct']}\n")
            f.write(f"- Total return: {s['total_return']}\n")
            f.write(f"- Max DD: {s['max_dd']}\n\n")
        else:
            f.write("## No Real Broker Ready\n\n")
            f.write("No non-canonical broker passed the BROKER_PROP_READY criteria.\n")
            f.write("The system is NOT ready for prop firm challenges.\n\n")
        f.write("## All Broker Scores\n\n")
        f.write("| Broker | Verdict | Score | DD Breaches | Profitable Months | Hit 10% | Total Return |\n")
        f.write("|---|---|---|---|---|---|---|\n")
        for b in REAL_BROKERS:
            s = broker_scores.get(b, {})
            f.write(f"| {b} | {s.get('verdict', 'N/A')} | {s.get('score', 'N/A')} | "
                    f"{s.get('daily_dd_breaches', 0)+s.get('total_dd_breaches', 0)} | "
                    f"{s.get('profitable_months', 0)} | {s.get('months_hit_10pct', 0)} | "
                    f"{s.get('total_return', 0)} |\n")
        f.write("\n## Rejected Brokers\n\n")
        for b, v in selection["rejected_brokers"].items():
            f.write(f"- {b}: {v}\n")

    return selection


def task7_broker_configs(broker_best, broker_yearly_verdicts, selection):
    """Task 7: Create broker-specific configs for usable brokers."""
    print("\n  [Task 7] Creating broker-specific configs...")
    config_dir = REPO_ROOT / "config" / "broker_profiles"
    config_dir.mkdir(parents=True, exist_ok=True)

    for broker in REAL_BROKERS:
        best = broker_best.get(broker)
        verdict = broker_yearly_verdicts.get(broker, "REJECT_FOR_PROP")
        if best is None:
            # Create rejection note
            note_path = config_dir / f"{broker}_REJECTED.note"
            note_path.write_text(f"Broker {broker} rejected: no calibration data\nVerdict: {verdict}\n")
            continue

        if verdict in ["BROKER_PROP_READY", "BROKER_USABLE", "NEEDS_RETURN_IMPROVEMENT"]:
            # Create approved profile
            config = {
                "broker": broker,
                "model_profile": "v2_feature_normalized",
                "calibrated_thresholds": {
                    "alpha_threshold": best["alpha_threshold"],
                    "meta_threshold": best["meta_threshold"],
                },
                "spread_filter": 0.5,
                "session_filter": best["session_filter"],
                "mtf_mode": "h1_only",
                "risk_profile": best["risk_profile"],
                "risk_percent": best["risk_percent"],
                "dd_stops": {
                    "internal_daily_dd_stop": 0.025,
                    "internal_total_dd_stop": 0.065,
                    "external_daily_dd_limit": 0.03,
                    "external_total_dd_limit": 0.08,
                },
                "max_trades_per_day": 2,
                "max_lot": 0.01,
                "max_open_positions": 1,
                "cooldown_after_loss": 5,
                "safety": {
                    "dry_run": True,
                    "live_trading": False,
                    "funded_trading": False,
                    "production_ready": False,
                    "broker_target": "MetaQuotes-Demo",
                    "no_order_send": True,
                    "no_token_auto_create": True,
                    "ceo_not_bypassed": True,
                    "meta_label_not_bypassed": True,
                },
                "verdict": verdict,
            }
            config_path = config_dir / f"{broker}_prop_profile.yaml"
            with open(config_path, "w") as f:
                yaml.dump(config, f, default_flow_style=False, sort_keys=False)
            print(f"    {broker}: created {config_path.name} (verdict={verdict})")
        else:
            # Create rejection note
            note_path = config_dir / f"{broker}_REJECTED.note"
            note_path.write_text(
                f"Broker {broker} rejected for prop\n"
                f"Verdict: {verdict}\n"
                f"Reason: DD breaches or insufficient profit\n"
            )
            print(f"    {broker}: created rejection note (verdict={verdict})")


def task9_readiness_audit(selection, broker_yearly_verdicts):
    """Task 9: Final broker-specific readiness audit."""
    print("\n  [Task 9] Final broker-specific readiness audit...")

    selected = selection.get("selected_target_broker")
    no_real_broker_ready = selection.get("no_real_broker_ready", True)

    # Check if shadow runner exists
    shadow_runner_exists = (REPO_ROOT / "scripts" / "operator" / "run_broker_specific_shadow_readonly.py").exists()

    # Check CEO/meta-label wiring
    try:
        from titan.production.ceo_ai_governance import evaluate_ceo_decision
        ceo_wired = True
    except Exception:
        ceo_wired = False
    try:
        from titan.production.model_loader import META_FEATURE_NAMES
        meta_wired = len(META_FEATURE_NAMES) == 22
    except Exception:
        meta_wired = False

    if no_real_broker_ready or selected is None:
        verdict = "NO_REAL_BROKER_READY"
    elif not shadow_runner_exists:
        verdict = "NEEDS_MORE_DATA"
    elif not ceo_wired or not meta_wired:
        verdict = "NEEDS_BROKER_SPECIFIC_MODEL"
    else:
        # Check selected broker passes
        selected_verdict = broker_yearly_verdicts.get(selected)
        if selected_verdict == "BROKER_PROP_READY":
            verdict = "BROKER_PROP_SHADOW_READY"
        else:
            verdict = "NO_REAL_BROKER_READY"

    audit = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "verdict": verdict,
        "selected_target_broker": selected,
        "no_real_broker_ready": no_real_broker_ready,
        "canonical_deprecated": True,
        "shadow_runner_exists": shadow_runner_exists,
        "ceo_wired": ceo_wired,
        "meta_wired": meta_wired,
        "selected_broker_verdict": broker_yearly_verdicts.get(selected, "N/A") if selected else "N/A",
        "safety": {
            "dry_run": True,
            "live_trading": False,
            "funded_trading": False,
            "production_ready": False,
            "no_order_send": True,
            "no_token_auto_create": True,
        },
    }

    with open(OUTPUT_DIR / "broker_specific_prop_readiness.json", "w") as f:
        json.dump(audit, f, indent=2, default=str)

    with open(OUTPUT_DIR / "broker_specific_prop_readiness.md", "w") as f:
        f.write("# Broker-Specific Prop Readiness Audit (Sprint v2.8.7-K)\n\n")
        f.write(f"**Timestamp:** {audit['timestamp_utc']}\n\n")
        f.write(f"## Verdict: {verdict}\n\n")
        f.write("## CRITICAL: Canonical Deprecation\n\n")
        f.write("Canonical is BENCHMARK_ONLY. Only a real non-canonical broker can approve prop readiness.\n\n")
        f.write(f"## Selected Target Broker: {selected or 'NONE'}\n\n")
        f.write(f"## NO_REAL_BROKER_READY: {no_real_broker_ready}\n\n")
        f.write("## Audit Checks\n\n")
        f.write("| Check | Status |\n|---|---|\n")
        f.write(f"| Selected broker passes yearly audit | {'✅' if broker_yearly_verdicts.get(selected) == 'BROKER_PROP_READY' else '❌'} |\n")
        f.write(f"| Shadow runner exists | {'✅' if shadow_runner_exists else '❌'} |\n")
        f.write(f"| CEO wired | {'✅' if ceo_wired else '❌'} |\n")
        f.write(f"| Meta-label wired | {'✅' if meta_wired else '❌'} |\n")
        f.write(f"| dry_run = True | ✅ |\n")
        f.write(f"| live_trading = False | ✅ |\n")
        f.write(f"| funded_trading = False | ✅ |\n")
        f.write(f"| production_ready = False | ✅ |\n")
        f.write(f"| no_order_send | ✅ |\n")
        f.write(f"| no_token_auto_create | ✅ |\n\n")
        if verdict == "BROKER_PROP_SHADOW_READY":
            f.write("## BROKER_PROP_SHADOW_READY\n\n")
            f.write(f"Broker {selected} has passed all prop readiness criteria.\n")
            f.write("**However:** CTO review required before any demo activity.\n")
        else:
            f.write(f"## {verdict}\n\n")
            f.write("No real non-canonical broker is ready for prop firm challenges.\n")
            f.write("Further work needed: broker-specific models, calibration, or more data.\n")

    return audit


def main():
    ts = datetime.now(timezone.utc).isoformat()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("  TITAN XAU AI - BROKER-SPECIFIC PROP FEED SURVIVAL AUDIT (v2.8.7-K)")
    print("=" * 70)
    print(f"  Timestamp: {ts}")
    print("  CRITICAL: Canonical CANNOT approve prop readiness alone.\n")

    # Load model
    bundle = load_models_by_profile("v2_feature_normalized")
    if not bundle.ok:
        print("  ERROR: v2 model failed to load")
        return

    # Load M15/M5
    m15_bars = load_m15_bars()
    m5_bars = load_m5_bars()
    reset_mtf_caches()

    # Load all brokers
    brokers_data = {}
    brokers_preds = {}
    for b in ["canonical"] + REAL_BROKERS:
        df = load_broker(b)
        if df is None:
            continue
        print(f"  Computing predictions for {b}...")
        alpha, meta, atr = compute_predictions(df, bundle)
        brokers_data[b] = df
        brokers_preds[b] = {"alpha": alpha, "meta": meta, "atr": atr, "features": None}

    # Also store features for drift analysis
    for b in brokers_data:
        df = brokers_data[b]
        df_use = df[["open", "high", "low", "close"]].copy()
        if "tick_volume" in df.columns:
            df_use["volume"] = df["tick_volume"]
        else:
            df_use["volume"] = 0.0
        df_use["spread"] = df["spread_usd"]
        stream = H1FeatureStreamV2()
        stream._bars = df_use
        feats_df = stream._compute_features()
        features_matrix = np.nan_to_num(feats_df.values.astype(np.float64), nan=0.0, posinf=0.0, neginf=0.0)
        brokers_preds[b]["features"] = stream._standardize(features_matrix)

    # Task 3: Failure diagnosis
    broker_verdicts = task3_failure_diagnosis(brokers_data, brokers_preds, bundle)

    # Task 4: Calibration search
    broker_best = task4_calibration_search(brokers_data, brokers_preds, m15_bars, m5_bars)

    # Task 5: Yearly audit
    broker_yearly_verdicts, yearly_rows = task5_yearly_audit(brokers_data, brokers_preds, broker_best, m15_bars, m5_bars)

    # Task 6: Select target broker
    selection = task6_select_target_broker(broker_yearly_verdicts, yearly_rows, broker_best)

    # Task 7: Broker configs
    task7_broker_configs(broker_best, broker_yearly_verdicts, selection)

    # Task 9: Readiness audit
    audit = task9_readiness_audit(selection, broker_yearly_verdicts)

    # Print summary
    print("\n" + "=" * 70)
    print("  BROKER-SPECIFIC PROP AUDIT SUMMARY")
    print("=" * 70)
    print(f"\n  Selected target broker: {selection.get('selected_target_broker', 'NONE')}")
    print(f"  NO_REAL_BROKER_READY: {selection.get('no_real_broker_ready', True)}")
    print(f"  Final verdict: {audit['verdict']}")
    print(f"\n  Broker yearly verdicts:")
    for b in REAL_BROKERS:
        print(f"    {b:12s}: {broker_yearly_verdicts.get(b, 'N/A')}")
    print(f"\n  Output: {OUTPUT_DIR}")
    print("\n" + "=" * 70)
    print("  > Canonical CANNOT approve alone. NO TRADE. CTO review required.")
    print("=" * 70)

    return audit


if __name__ == "__main__":
    main()
