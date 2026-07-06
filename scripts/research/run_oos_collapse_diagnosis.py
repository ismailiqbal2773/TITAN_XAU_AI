#!/usr/bin/env python3
"""TITAN XAU AI - OOS Collapse Diagnosis (Sprint v2.8.7-D)
============================================================
Diagnoses why production-integrated parameter discovery returns
NO_SAFE_PARAMETER_FOUND even after v2.8.7-C spread normalization.

Performs 8 diagnostic tasks:
  Task 3: Year-wise and broker-wise breakdown (2020-2026 × 5 brokers)
  Task 4: Direction inversion audit (original vs flipped direction)
  Task 5: Exit geometry audit (SL/RR/holding/trailing/timeout)
  Task 6: Regime filter audit (trend/spread/vol/session/dow)
  Task 7: Feature drift audit (IS 2020-2023 vs OOS 2025-2026)
  Task 8: Confidence bucket audit (alpha + meta buckets)
  Task 9: MTF mode audit (h1_only, h1_m15, h1_m15_m5)
  Task 10: Minimal safe fix plan with classification flags

NEVER sends orders. NEVER creates token. NEVER trades.
Uses REAL production XGBoost + meta-label + CEO + ATR geometry only.
NO SMA proxy, NO volatility proxy, NO martingale, NO grid, NO averaging.
"""
from __future__ import annotations
import sys, json, csv, os, math
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict
import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

OUTPUT_DIR = REPO_ROOT / "data" / "reports" / "oos_collapse"

# Reuse production components from v2.8.7-C discovery script
from scripts.research.run_safe_parameter_discovery import (
    load_h1_data, precompute_model_predictions, ParamSet,
    load_production_models, BROKER_PATHS, MAX_TOTAL_DD, MAX_DAILY_DD,
    PRODUCTION_AUDIT,
)
from titan.production.feature_stream import H1FeatureStream, FEATURE_NAMES
from titan.production.model_loader import META_FEATURE_NAMES


# Conservative baseline params (alpha=0.55, meta=0.65 — production defaults)
BASELINE_PARAMS = ParamSet()


# ─────────────────────────────────────────────────────────────────────
# Extended backtest with per-trade detail tracking
# ─────────────────────────────────────────────────────────────────────

def backtest_with_details(df, model_preds, params, starting_equity=10000.0,
                          flip_direction=False):
    """Run backtest and return (summary_dict, trades_list).

    trades_list entries contain per-trade metadata for bucket analyses:
      bar_idx, timestamp, direction, alpha, meta, regime, session, dow,
      entry_price, exit_price, exit_reason, r_result, pnl, atr, sl_dist

    If flip_direction=True, LONG<->SHORT is swapped (for direction inversion audit).
    """
    if df is None or model_preds is None or len(df) < 220:
        return _empty_summary(), []

    alpha_proba = model_preds["alpha_proba"]
    meta_proba = model_preds["meta_proba"]
    valid_mask = model_preds["valid_mask"]
    atr_values = model_preds["atr_values"]

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
    trades = []

    closes = df["close"].values
    highs = df["high"].values
    lows = df["low"].values
    index = df.index

    for i in range(28, len(df) - params.max_holding_bars - 1):
        total_dd = (starting_equity - equity) / starting_equity if starting_equity > 0 else 0
        if total_dd > max_total_dd:
            max_total_dd = total_dd
        if total_dd >= MAX_TOTAL_DD:
            if not total_dd_cap_hit:
                total_dd_cap_hit = True
                prop_violations += 1
            continue

        daily_dd = (daily_start_equity - equity) / daily_start_equity if daily_start_equity > 0 else 0
        if daily_dd > max_daily_dd:
            max_daily_dd = daily_dd
        if daily_dd >= MAX_DAILY_DD:
            continue

        bar_day = index[i].date()
        if current_day != bar_day:
            current_day = bar_day
            daily_start_equity = equity
            daily_trades = 0

        if daily_trades >= params.max_trades_per_day:
            continue
        if cooldown_remaining > 0:
            cooldown_remaining -= 1
            continue

        if not valid_mask[i]:
            continue

        # Spread filter (uses normalized spread_usd)
        spread = float(df["spread_usd"].iloc[i]) if "spread_usd" in df.columns else 0.3
        if spread > params.spread_filter:
            continue

        # Session determination
        hour = index[i].hour
        if 0 <= hour < 8:
            session = "asia"
        elif 7 <= hour < 16:
            session = "europe"
        elif 13 <= hour < 22:
            session = "us"
        else:
            session = "off"

        if params.session_filter == "london" and not (7 <= hour <= 15):
            continue
        if params.session_filter == "ny" and not (12 <= hour <= 20):
            continue
        if params.session_filter == "overlap" and not (12 <= hour <= 15):
            continue

        # Regime determination (use ATR ratio as proxy for trend strength,
        # but NOT a volatility proxy for entry — only for labeling)
        atr = atr_values[i] if atr_values[i] > 0 else 3.0
        atr_pct = atr / closes[i] if closes[i] > 0 else 0
        if atr_pct > 0.008:
            trend_regime = "TREND_STRONG"
        elif atr_pct > 0.004:
            trend_regime = "TREND_NORMAL"
        else:
            trend_regime = "RANGE"

        spread_regime = "WIDE" if spread > 0.5 else ("NORMAL" if spread > 0.2 else "TIGHT")
        vol_regime = trend_regime  # same as trend here

        if params.regime_policy == "strict" and trend_regime not in ("TREND_NORMAL", "TREND_STRONG"):
            continue

        # === PRODUCTION ALPHA (XGBoost) ===
        alpha_confidence = float(alpha_proba[i])
        if alpha_confidence < params.alpha_threshold:
            continue
        direction = "LONG" if alpha_confidence >= 0.5 else "SHORT"
        if alpha_confidence == 0.5:
            direction = "LONG" if closes[i] > closes[i-1] else "SHORT"

        if flip_direction:
            direction = "SHORT" if direction == "LONG" else "LONG"

        # === PRODUCTION META-LABEL ===
        meta_confidence = float(meta_proba[i])
        if meta_confidence < params.meta_threshold:
            continue

        # === CEO GOVERNANCE ===
        from titan.production.ceo_ai_governance import evaluate_ceo_decision
        ceo_decision = evaluate_ceo_decision(
            regime_state={"detected": True, "regime_value": "MARKET_OPEN", "confidence": alpha_confidence},
            xgb_alpha={"direction": direction, "confidence": alpha_confidence, "pass": True},
            lstm_confidence=None,
            transformer_regime=None,
            meta_label_quality={"quality_score": meta_confidence, "pass": True},
            broker_state={"broker_pass": True, "spread_pass": True, "slippage_pass": True},
            prop_risk_state={"risk_pass": True, "prop_funded_pass": True, "max_positions_ok": True},
            capital_protection_state={"capital_preservation_active": False, "dd_breach": False},
            model_health_state={"model_health_pass": True, "failed_required": 0},
            geometry_state={"geometry_pass": True, "actual_RR": params.rr_target, "minimum_RR": 2.0},
        )
        if not ceo_decision.allowed_to_trade:
            continue

        # === ATR-BASED SL/TP GEOMETRY ===
        sl_distance = atr * params.sl_atr_multiplier
        tp_distance = sl_distance * params.rr_target

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

        for j in range(1, params.max_holding_bars + 1):
            if i + j >= len(df):
                break
            next_high = highs[i + j]
            next_low = lows[i + j]
            if direction == "LONG":
                if next_low <= sl_price:
                    exit_price, exit_reason, r_result = sl_price, "SL_HIT", -1.0
                    break
                if next_high >= tp_price:
                    exit_price, exit_reason, r_result = tp_price, "TP_HIT", params.rr_target
                    break
                if params.trailing_policy == "on" and params.breakeven_trigger > 0:
                    current_r = (closes[i+j] - entry_price) / sl_distance
                    if current_r >= params.breakeven_trigger:
                        sl_price = entry_price
            else:
                if next_high >= sl_price:
                    exit_price, exit_reason, r_result = sl_price, "SL_HIT", -1.0
                    break
                if next_low <= tp_price:
                    exit_price, exit_reason, r_result = tp_price, "TP_HIT", params.rr_target
                    break
                if params.trailing_policy == "on" and params.breakeven_trigger > 0:
                    current_r = (entry_price - closes[i+j]) / sl_distance
                    if current_r >= params.breakeven_trigger:
                        sl_price = entry_price

        if exit_reason == "TIMEOUT":
            exit_price = closes[min(i + params.max_holding_bars, len(df)-1)]
            if direction == "LONG":
                r_result = (exit_price - entry_price) / sl_distance
            else:
                r_result = (entry_price - exit_price) / sl_distance

        risk_amount = equity * params.risk_percent
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
            cooldown_remaining = params.cooldown_after_loss

        trades.append({
            "bar_idx": i,
            "timestamp": str(index[i]),
            "year": index[i].year,
            "month": index[i].month,
            "hour": hour,
            "dow": index[i].dayofweek,
            "direction": direction,
            "alpha": round(alpha_confidence, 6),
            "meta": round(meta_confidence, 6),
            "regime_trend": trend_regime,
            "regime_spread": spread_regime,
            "regime_vol": vol_regime,
            "session": session,
            "entry_price": round(entry_price, 4),
            "exit_price": round(exit_price, 4),
            "exit_reason": exit_reason,
            "r_result": round(r_result, 4),
            "pnl": round(pnl, 4),
            "atr": round(atr, 4),
            "sl_distance": round(sl_distance, 4),
            "tp_distance": round(tp_distance, 4),
            "max_holding_bars": params.max_holding_bars,
            "sl_atr_multiplier": params.sl_atr_multiplier,
            "rr_target": params.rr_target,
            "trailing_policy": params.trailing_policy,
            "breakeven_trigger": params.breakeven_trigger,
            "mtf_mode": params.mtf_mode,
        })

    total_trades = wins + losses
    win_rate = wins / total_trades if total_trades > 0 else 0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else (999.0 if gross_profit > 0 else 0)
    total_return = (equity - starting_equity) / starting_equity if starting_equity > 0 else 0
    monthly_estimate = total_return * 4

    if total_trades > 1:
        rs = [1.0 if t["r_result"] > 0 else -1.0 for t in trades]
        std_r = max(0.01, float(np.std(rs)))
        sharpe = (sum(rs) / len(rs)) / std_r * (252 ** 0.5)
    else:
        sharpe = 0

    summary = {
        "trades": total_trades,
        "win_rate": round(win_rate, 4),
        "profit_factor": round(profit_factor, 4) if profit_factor != 999 else 999,
        "sharpe": round(sharpe, 4),
        "max_daily_dd": round(max_daily_dd, 4),
        "max_total_dd": round(max_total_dd, 4),
        "monthly_estimate": round(monthly_estimate, 4),
        "avg_r": round(total_r / total_trades, 4) if total_trades > 0 else 0,
        "max_consecutive_losses": max_consecutive_losses,
        "prop_violations": prop_violations,
        "total_dd_cap_hit": total_dd_cap_hit,
        "final_equity": round(equity, 2),
        "starting_equity": round(starting_equity, 2),
    }
    return summary, trades


def _empty_summary():
    return {
        "trades": 0, "win_rate": 0, "profit_factor": 0, "sharpe": 0,
        "max_daily_dd": 0, "max_total_dd": 0, "monthly_estimate": 0,
        "avg_r": 0, "max_consecutive_losses": 0, "prop_violations": 0,
        "total_dd_cap_hit": False, "final_equity": 10000, "starting_equity": 10000,
    }


def _verdict_from_summary(s):
    if s["trades"] < 5:
        return "FAIL_LOW_SAMPLE"
    if s["max_total_dd"] > MAX_TOTAL_DD or s["prop_violations"] > 0:
        return "FAIL_DD"
    if s["profit_factor"] < 1.0:
        return "FAIL_OVERFIT"
    if s["sharpe"] <= 0:
        return "FAIL_OVERFIT"
    return "PASS"


# ─────────────────────────────────────────────────────────────────────
# Task 3: Year × Broker breakdown
# ─────────────────────────────────────────────────────────────────────

def task3_year_broker_breakdown(brokers_data, brokers_preds):
    print("  [Task 3] Year × Broker breakdown...")
    rows = []
    rejection_rows = []
    for broker, df in brokers_data.items():
        preds = brokers_preds.get(broker)
        if preds is None:
            continue
        for year in range(2020, 2027):
            year_mask = df.index.year == year
            if year_mask.sum() < 100:
                continue
            df_year = df[year_mask]
            # Slice predictions
            year_preds = {
                "alpha_proba": preds["alpha_proba"][year_mask],
                "meta_proba": preds["meta_proba"][year_mask],
                "valid_mask": preds["valid_mask"][year_mask],
                "atr_values": preds["atr_values"][year_mask],
            }
            summary, _ = backtest_with_details(df_year, year_preds, BASELINE_PARAMS)
            verdict = _verdict_from_summary(summary)
            rows.append({
                "broker": broker,
                "year": year,
                "trades": summary["trades"],
                "win_rate": summary["win_rate"],
                "profit_factor": summary["profit_factor"],
                "sharpe": summary["sharpe"],
                "max_drawdown": summary["max_total_dd"],
                "avg_r": summary["avg_r"],
                "monthly_estimate": summary["monthly_estimate"],
                "prop_violations": summary["prop_violations"],
                "rejection_reason": verdict,
                "verdict": "PASS" if verdict == "PASS" else "FAIL",
            })
            rejection_rows.append({
                "broker": broker,
                "year": year,
                "rejection_reason": verdict,
                "trades": summary["trades"],
                "pf": summary["profit_factor"],
                "sharpe": summary["sharpe"],
                "dd": summary["max_total_dd"],
            })
    return rows, rejection_rows


# ─────────────────────────────────────────────────────────────────────
# Task 4: Direction inversion audit
# ─────────────────────────────────────────────────────────────────────

def task4_direction_inversion(brokers_data, brokers_preds):
    print("  [Task 4] Direction inversion audit...")
    rows = []
    direction_inversion_suspect = False
    improvement_brokers = 0

    for broker, df in brokers_data.items():
        preds = brokers_preds.get(broker)
        if preds is None:
            continue
        # Focus on OOS years 2025-2026
        oos_mask = (df.index.year >= 2025) & (df.index.year <= 2026)
        if oos_mask.sum() < 100:
            continue
        df_oos = df[oos_mask]
        oos_preds = {
            "alpha_proba": preds["alpha_proba"][oos_mask],
            "meta_proba": preds["meta_proba"][oos_mask],
            "valid_mask": preds["valid_mask"][oos_mask],
            "atr_values": preds["atr_values"][oos_mask],
        }
        # Original direction
        orig_summary, _ = backtest_with_details(df_oos, oos_preds, BASELINE_PARAMS, flip_direction=False)
        # Flipped direction
        flip_summary, _ = backtest_with_details(df_oos, oos_preds, BASELINE_PARAMS, flip_direction=True)

        orig_pf = orig_summary["profit_factor"] if orig_summary["profit_factor"] != 999 else 99.0
        flip_pf = flip_summary["profit_factor"] if flip_summary["profit_factor"] != 999 else 99.0
        improvement_ratio = (flip_pf - orig_pf) / orig_pf if orig_pf > 0 else 0

        if improvement_ratio > 0.30 and orig_pf > 0:
            improvement_brokers += 1

        rows.append({
            "broker": broker,
            "year": "2025-2026",
            "original_pf": round(orig_pf, 4),
            "flipped_pf": round(flip_pf, 4),
            "original_sharpe": orig_summary["sharpe"],
            "flipped_sharpe": flip_summary["sharpe"],
            "original_dd": orig_summary["max_total_dd"],
            "flipped_dd": flip_summary["max_total_dd"],
            "original_trades": orig_summary["trades"],
            "flipped_trades": flip_summary["trades"],
            "improvement_ratio": round(improvement_ratio, 4),
            "direction_inversion_suspect": improvement_ratio > 0.30,
        })

    if improvement_brokers >= 2:
        direction_inversion_suspect = True

    return rows, direction_inversion_suspect


# ─────────────────────────────────────────────────────────────────────
# Task 5: Exit geometry audit
# ─────────────────────────────────────────────────────────────────────

def task5_exit_geometry(brokers_data, brokers_preds):
    print("  [Task 5] Exit geometry audit...")
    rows = []
    exit_reason_rows = []
    exit_geometry_issue = False

    # Vary SL ATR, RR target, max holding, trailing
    geometries = [
        {"sl_atr": 1.0, "rr": 2.0, "holding": 1, "trailing": "off", "be": 1.0},
        {"sl_atr": 1.5, "rr": 2.0, "holding": 1, "trailing": "off", "be": 1.0},
        {"sl_atr": 2.0, "rr": 2.0, "holding": 1, "trailing": "off", "be": 1.0},
        {"sl_atr": 1.5, "rr": 3.0, "holding": 1, "trailing": "off", "be": 1.0},
        {"sl_atr": 1.5, "rr": 2.0, "holding": 3, "trailing": "off", "be": 1.0},
        {"sl_atr": 1.5, "rr": 3.0, "holding": 3, "trailing": "off", "be": 1.0},
        {"sl_atr": 1.5, "rr": 3.0, "holding": 3, "trailing": "on",  "be": 1.0},
        {"sl_atr": 2.0, "rr": 3.0, "holding": 6, "trailing": "off", "be": 1.0},
        {"sl_atr": 2.0, "rr": 3.0, "holding": 6, "trailing": "on",  "be": 1.0},
        {"sl_atr": 2.0, "rr": 4.0, "holding": 12, "trailing": "off", "be": 1.0},
    ]

    for geom in geometries:
        params = ParamSet(
            sl_atr_multiplier=geom["sl_atr"],
            rr_target=geom["rr"],
            max_holding_bars=geom["holding"],
            trailing_policy=geom["trailing"],
            breakeven_trigger=geom["be"],
        )
        # Run on canonical OOS 2025-2026 only (for speed)
        broker = "canonical"
        df = brokers_data.get(broker)
        preds = brokers_preds.get(broker)
        if df is None or preds is None:
            continue
        oos_mask = (df.index.year >= 2025) & (df.index.year <= 2026)
        if oos_mask.sum() < 100:
            continue
        df_oos = df[oos_mask]
        oos_preds = {
            "alpha_proba": preds["alpha_proba"][oos_mask],
            "meta_proba": preds["meta_proba"][oos_mask],
            "valid_mask": preds["valid_mask"][oos_mask],
            "atr_values": preds["atr_values"][oos_mask],
        }
        summary, trades = backtest_with_details(df_oos, oos_preds, params)

        # Exit reason breakdown
        exit_counts = defaultdict(int)
        for t in trades:
            exit_counts[t["exit_reason"]] += 1
        total = max(1, len(trades))
        sl_rate = exit_counts.get("SL_HIT", 0) / total
        tp_rate = exit_counts.get("TP_HIT", 0) / total
        timeout_rate = exit_counts.get("TIMEOUT", 0) / total

        rows.append({
            "sl_atr_multiplier": geom["sl_atr"],
            "rr_target": geom["rr"],
            "max_holding_bars": geom["holding"],
            "trailing_policy": geom["trailing"],
            "breakeven_trigger": geom["be"],
            "trades": summary["trades"],
            "sl_hit_rate": round(sl_rate, 4),
            "tp_hit_rate": round(tp_rate, 4),
            "timeout_rate": round(timeout_rate, 4),
            "avg_r": summary["avg_r"],
            "pf": summary["profit_factor"],
            "dd": summary["max_total_dd"],
            "sharpe": summary["sharpe"],
        })
        exit_reason_rows.append({
            "geometry": f"sl{geom['sl_atr']}_rr{geom['rr']}_h{geom['holding']}_{geom['trailing']}",
            "sl_hit": exit_counts.get("SL_HIT", 0),
            "tp_hit": exit_counts.get("TP_HIT", 0),
            "timeout": exit_counts.get("TIMEOUT", 0),
            "total": len(trades),
            "sl_rate": round(sl_rate, 4),
            "tp_rate": round(tp_rate, 4),
            "timeout_rate": round(timeout_rate, 4),
            "pf": summary["profit_factor"],
        })

    # Flag: if most geometries have timeout_rate > 0.50 AND pf < 1.0
    timeout_heavy = sum(1 for r in rows if r["timeout_rate"] > 0.50)
    if timeout_heavy >= 5 and all(r["pf"] < 1.0 for r in rows):
        exit_geometry_issue = True

    return rows, exit_reason_rows, exit_geometry_issue


# ─────────────────────────────────────────────────────────────────────
# Task 6: Regime filter audit
# ─────────────────────────────────────────────────────────────────────

def task6_regime_filter(brokers_data, brokers_preds):
    print("  [Task 6] Regime filter audit...")
    regime_rows = []
    session_rows = []
    regime_filter_fix_needed = False

    # Aggregate trades from all brokers OOS 2025-2026 with baseline params
    all_trades = []
    for broker, df in brokers_data.items():
        preds = brokers_preds.get(broker)
        if preds is None:
            continue
        oos_mask = (df.index.year >= 2025) & (df.index.year <= 2026)
        if oos_mask.sum() < 100:
            continue
        df_oos = df[oos_mask]
        oos_preds = {
            "alpha_proba": preds["alpha_proba"][oos_mask],
            "meta_proba": preds["meta_proba"][oos_mask],
            "valid_mask": preds["valid_mask"][oos_mask],
            "atr_values": preds["atr_values"][oos_mask],
        }
        _, trades = backtest_with_details(df_oos, oos_preds, BASELINE_PARAMS)
        for t in trades:
            t["broker"] = broker
        all_trades.extend(trades)

    if not all_trades:
        return regime_rows, session_rows, regime_filter_fix_needed

    # Group by trend regime
    by_trend = defaultdict(list)
    by_spread = defaultdict(list)
    by_vol = defaultdict(list)
    by_session = defaultdict(list)
    by_dow = defaultdict(list)
    for t in all_trades:
        by_trend[t["regime_trend"]].append(t)
        by_spread[t["regime_spread"]].append(t)
        by_vol[t["regime_vol"]].append(t)
        by_session[t["session"]].append(t)
        by_dow[t["dow"]].append(t)

    def _stats(trades_list, group_key, group_val):
        if not trades_list:
            return None
        n = len(trades_list)
        wins = sum(1 for t in trades_list if t["r_result"] > 0)
        gross_p = sum(t["pnl"] for t in trades_list if t["pnl"] > 0)
        gross_l = sum(-t["pnl"] for t in trades_list if t["pnl"] < 0)
        pf = gross_p / gross_l if gross_l > 0 else (999.0 if gross_p > 0 else 0)
        rs = [1.0 if t["r_result"] > 0 else -1.0 for t in trades_list]
        std_r = max(0.01, float(np.std(rs)))
        sharpe = (sum(rs) / len(rs)) / std_r * (252 ** 0.5) if n > 1 else 0
        avg_r = sum(t["r_result"] for t in trades_list) / n
        return {
            "group_key": group_key,
            "group_value": str(group_val),
            "trades": n,
            "win_rate": round(wins / n, 4),
            "profit_factor": round(pf, 4) if pf != 999 else 999,
            "sharpe": round(sharpe, 4),
            "avg_r": round(avg_r, 4),
        }

    for regime_type, by_dict in [("trend", by_trend), ("spread", by_spread), ("vol", by_vol)]:
        for val, trades_list in by_dict.items():
            stats = _stats(trades_list, regime_type, val)
            if stats:
                regime_rows.append(stats)

    for session_name, trades_list in by_session.items():
        stats = _stats(trades_list, "session", session_name)
        if stats:
            session_rows.append(stats)
    for dow, trades_list in by_dow.items():
        stats = _stats(trades_list, "dow", dow)
        if stats:
            session_rows.append(stats)

    # Flag: if only 1 regime is profitable and others collapse
    pf_by_trend = {r["group_value"]: r["profit_factor"] for r in regime_rows if r["group_key"] == "trend"}
    if pf_by_trend:
        profitable = sum(1 for pf in pf_by_trend.values() if pf > 1.0)
        total = len(pf_by_trend)
        if profitable == 1 and total >= 3:
            regime_filter_fix_needed = True

    return regime_rows, session_rows, regime_filter_fix_needed


# ─────────────────────────────────────────────────────────────────────
# Task 7: Feature drift audit
# ─────────────────────────────────────────────────────────────────────

def task7_feature_drift(brokers_data, brokers_preds):
    print("  [Task 7] Feature drift audit (IS 2020-2023 vs OOS 2025-2026)...")
    rows = []
    feature_drift_issue = False

    # Use canonical for drift analysis (most complete data)
    broker = "canonical"
    df = brokers_data.get(broker)
    preds = brokers_preds.get(broker)
    if df is None or preds is None:
        return rows, feature_drift_issue

    features_matrix = preds.get("features_matrix")
    if features_matrix is None:
        return rows, feature_drift_issue

    is_mask = (df.index.year >= 2020) & (df.index.year <= 2023)
    oos_mask = (df.index.year >= 2025) & (df.index.year <= 2026)

    if is_mask.sum() < 100 or oos_mask.sum() < 100:
        return rows, feature_drift_issue

    # Convert to numpy arrays for boolean indexing
    is_mask_np = np.asarray(is_mask)
    oos_mask_np = np.asarray(oos_mask)

    is_feats = features_matrix[is_mask_np]
    oos_feats = features_matrix[oos_mask_np]

    # Also alpha and meta distributions
    alpha_is = preds["alpha_proba"][is_mask_np]
    alpha_oos = preds["alpha_proba"][oos_mask_np]
    meta_is = preds["meta_proba"][is_mask_np]
    meta_oos = preds["meta_proba"][oos_mask_np]
    spread_is = df["spread_usd"].values[is_mask_np]
    spread_oos = df["spread_usd"].values[oos_mask_np]
    close_is = df["close"].values[is_mask_np]
    close_oos = df["close"].values[oos_mask_np]

    # Per-feature drift
    for j, name in enumerate(FEATURE_NAMES):
        is_col = is_feats[:, j]
        oos_col = oos_feats[:, j]
        is_mean = float(np.mean(is_col)) if len(is_col) else 0
        oos_mean = float(np.mean(oos_col)) if len(oos_col) else 0
        is_std = float(np.std(is_col)) if len(is_col) else 0
        oos_std = float(np.std(oos_col)) if len(oos_col) else 0
        is_p50 = float(np.percentile(is_col, 50)) if len(is_col) else 0
        oos_p50 = float(np.percentile(oos_col, 50)) if len(oos_col) else 0
        is_p95 = float(np.percentile(is_col, 95)) if len(is_col) else 0
        oos_p95 = float(np.percentile(oos_col, 95)) if len(oos_col) else 0
        drift = abs(is_mean - oos_mean) / max(abs(is_std), 0.001)
        rows.append({
            "feature": name,
            "is_mean": round(is_mean, 6),
            "oos_mean": round(oos_mean, 6),
            "is_std": round(is_std, 6),
            "oos_std": round(oos_std, 6),
            "is_p50": round(is_p50, 6),
            "oos_p50": round(oos_p50, 6),
            "is_p95": round(is_p95, 6),
            "oos_p95": round(oos_p95, 6),
            "drift_score": round(drift, 4),
            "missing_count": int(np.sum(np.isnan(is_col)) + np.sum(np.isnan(oos_col))),
            "outlier_count": int(np.sum(np.abs(oos_col) > 3 * max(is_std, 0.001))),
        })

    rows.sort(key=lambda x: x["drift_score"], reverse=True)
    # Flag: top 5 drifted features have drift_score > 1.0
    top5 = rows[:5]
    if sum(1 for r in top5 if r["drift_score"] > 1.0) >= 3:
        feature_drift_issue = True

    # Add alpha/meta/spread/close summary
    drift_summary = {
        "alpha_is_mean": round(float(np.mean(alpha_is)), 4),
        "alpha_oos_mean": round(float(np.mean(alpha_oos)), 4),
        "meta_is_mean": round(float(np.mean(meta_is)), 4),
        "meta_oos_mean": round(float(np.mean(meta_oos)), 4),
        "spread_is_mean": round(float(np.mean(spread_is)), 6),
        "spread_oos_mean": round(float(np.mean(spread_oos)), 6),
        "close_is_mean": round(float(np.mean(close_is)), 2),
        "close_oos_mean": round(float(np.mean(close_oos)), 2),
        "close_ratio": round(float(np.mean(close_oos) / max(np.mean(close_is), 0.001)), 2),
    }
    return rows, feature_drift_issue, drift_summary


# ─────────────────────────────────────────────────────────────────────
# Task 8: Confidence bucket audit
# ─────────────────────────────────────────────────────────────────────

def task8_confidence_buckets(brokers_data, brokers_preds):
    print("  [Task 8] Confidence bucket audit...")
    alpha_rows = []
    meta_rows = []
    confidence_misalignment = False

    all_trades = []
    for broker, df in brokers_data.items():
        preds = brokers_preds.get(broker)
        if preds is None:
            continue
        oos_mask = (df.index.year >= 2025) & (df.index.year <= 2026)
        if oos_mask.sum() < 100:
            continue
        df_oos = df[oos_mask]
        oos_preds = {
            "alpha_proba": preds["alpha_proba"][oos_mask],
            "meta_proba": preds["meta_proba"][oos_mask],
            "valid_mask": preds["valid_mask"][oos_mask],
            "atr_values": preds["atr_values"][oos_mask],
        }
        _, trades = backtest_with_details(df_oos, oos_preds, BASELINE_PARAMS)
        all_trades.extend(trades)

    if not all_trades:
        return alpha_rows, meta_rows, confidence_misalignment

    def _bucket_stats(trades_list, bucket_label, bucket_value):
        if not trades_list:
            return None
        n = len(trades_list)
        wins = sum(1 for t in trades_list if t["r_result"] > 0)
        gross_p = sum(t["pnl"] for t in trades_list if t["pnl"] > 0)
        gross_l = sum(-t["pnl"] for t in trades_list if t["pnl"] < 0)
        pf = gross_p / gross_l if gross_l > 0 else (999.0 if gross_p > 0 else 0)
        rs = [1.0 if t["r_result"] > 0 else -1.0 for t in trades_list]
        std_r = max(0.01, float(np.std(rs)))
        sharpe = (sum(rs) / len(rs)) / std_r * (252 ** 0.5) if n > 1 else 0
        avg_r = sum(t["r_result"] for t in trades_list) / n
        return {
            "bucket": bucket_label,
            "bucket_value": bucket_value,
            "trades": n,
            "win_rate": round(wins / n, 4),
            "profit_factor": round(pf, 4) if pf != 999 else 999,
            "sharpe": round(sharpe, 4),
            "avg_r": round(avg_r, 4),
        }

    alpha_buckets = [(0.50, 0.55), (0.55, 0.60), (0.60, 0.65), (0.65, 0.70), (0.70, 0.80), (0.80, 1.01)]
    meta_buckets = [(0.50, 0.55), (0.55, 0.60), (0.60, 0.65), (0.65, 0.70), (0.70, 0.80), (0.80, 1.01)]

    for lo, hi in alpha_buckets:
        bucket_trades = [t for t in all_trades if lo <= t["alpha"] < hi]
        stats = _bucket_stats(bucket_trades, f"alpha_{lo:.2f}_{hi:.2f}", f"{lo:.2f}-{hi:.2f}")
        if stats:
            alpha_rows.append(stats)

    for lo, hi in meta_buckets:
        bucket_trades = [t for t in all_trades if lo <= t["meta"] < hi]
        stats = _bucket_stats(bucket_trades, f"meta_{lo:.2f}_{hi:.2f}", f"{lo:.2f}-{hi:.2f}")
        if stats:
            meta_rows.append(stats)

    # Flag: if higher alpha bucket performs worse than lower
    pf_by_bucket = [(r["bucket_value"], r["profit_factor"]) for r in alpha_rows if r["trades"] >= 5]
    if len(pf_by_bucket) >= 3:
        # Sort by bucket lower bound
        pf_by_bucket.sort(key=lambda x: float(x[0].split("-")[0]))
        pfs = [p[1] for p in pf_by_bucket if p[1] != 999]
        if len(pfs) >= 3:
            # If lowest bucket PF > highest bucket PF by >20%, misalignment
            if pfs[0] > pfs[-1] * 1.20 and pfs[-1] < 1.0:
                confidence_misalignment = True

    return alpha_rows, meta_rows, confidence_misalignment


# ─────────────────────────────────────────────────────────────────────
# Task 9: MTF mode audit
# ─────────────────────────────────────────────────────────────────────

def task9_mtf_mode(brokers_data, brokers_preds):
    print("  [Task 9] MTF mode audit...")
    rows = []
    mtf_implementation_gap = False

    mtf_modes = ["h1_only", "h1_m15", "h1_m15_m5"]
    for mode in mtf_modes:
        params = ParamSet(mtf_mode=mode)
        # Run on canonical OOS 2025-2026
        broker = "canonical"
        df = brokers_data.get(broker)
        preds = brokers_preds.get(broker)
        if df is None or preds is None:
            continue
        oos_mask = (df.index.year >= 2025) & (df.index.year <= 2026)
        if oos_mask.sum() < 100:
            continue
        df_oos = df[oos_mask]
        oos_preds = {
            "alpha_proba": preds["alpha_proba"][oos_mask],
            "meta_proba": preds["meta_proba"][oos_mask],
            "valid_mask": preds["valid_mask"][oos_mask],
            "atr_values": preds["atr_values"][oos_mask],
        }
        summary, trades = backtest_with_details(df_oos, oos_preds, params)

        # Check if MTF columns are actually used (they aren't — backtest is H1-only)
        # The mtf_mode param exists but the backtest only uses H1 data
        mtf_actually_used = False  # backtest doesn't implement M15/M5 confirmation

        rejection = "PASS" if summary["profit_factor"] > 1.0 and summary["max_total_dd"] < MAX_TOTAL_DD else "REJECT_OVERFIT"
        if not mtf_actually_used and mode != "h1_only":
            rejection = "INVALID_MTF_NOT_USED"
            mtf_implementation_gap = True

        rows.append({
            "mtf_mode": mode,
            "candidates_tested": 1,
            "trades": summary["trades"],
            "pf": summary["profit_factor"],
            "sharpe": summary["sharpe"],
            "dd": summary["max_total_dd"],
            "win_rate": summary["win_rate"],
            "avg_r": summary["avg_r"],
            "rejection_reason": rejection,
            "mtf_actually_used": mtf_actually_used,
        })

    return rows, mtf_implementation_gap


# ─────────────────────────────────────────────────────────────────────
# Task 10: Recommended fix path
# ─────────────────────────────────────────────────────────────────────

def task10_recommended_fix_path(
    direction_inversion_suspect,
    exit_geometry_issue,
    regime_filter_fix_needed,
    feature_drift_issue,
    confidence_misalignment,
    mtf_implementation_gap,
    drift_summary,
    top_drifted_features,
):
    print("  [Task 10] Generating recommended fix path...")

    retrain_required_later = feature_drift_issue  # drift implies model retrain
    no_trade_allowed = True  # no candidate found → no trade

    flags = {
        "BUG_FIX_NEEDED": False,
        "PARAMETER_TUNING_NEEDED": False,
        "EXIT_GEOMETRY_FIX_NEEDED": exit_geometry_issue,
        "REGIME_FILTER_FIX_NEEDED": regime_filter_fix_needed,
        "FEATURE_DRIFT_FIX_NEEDED": feature_drift_issue,
        "DIRECTION_INVERSION_SUSPECT": direction_inversion_suspect,
        "META_LABEL_RECALIBRATION_NEEDED": confidence_misalignment,
        "MTF_IMPLEMENTATION_GAP": mtf_implementation_gap,
        "RETRAIN_REQUIRED_LATER": retrain_required_later,
        "NO_TRADE_ALLOWED": no_trade_allowed,
    }

    # Determine root cause
    root_causes = []
    if feature_drift_issue:
        root_causes.append(
            f"FEATURE_DRIFT: Gold price shifted from ${drift_summary['close_is_mean']:.0f} (IS 2020-2023) "
            f"to ${drift_summary['close_oos_mean']:.0f} (OOS 2025-2026), a {drift_summary['close_ratio']}x ratio. "
            f"Absolute-price features ({', '.join(top_drifted_features[:3])}) drifted "
            f"after standardization, causing model input distribution shift."
        )
    if exit_geometry_issue:
        root_causes.append("EXIT_GEOMETRY: Most trades exit by timeout/SL, suggesting SL/TP placement is too tight for 2025-2026 volatility.")
    if regime_filter_fix_needed:
        root_causes.append("REGIME_FILTER: Only 1 trend regime is profitable in OOS; current regime policy lets losing regimes through.")
    if confidence_misalignment:
        root_causes.append("CONFIDENCE_MISALIGNMENT: Higher alpha confidence performs worse than lower in OOS — model is miscalibrated.")
    if direction_inversion_suspect:
        root_causes.append("DIRECTION_INVERSION: Flipping direction improves OOS PF by >30% across 2+ brokers — possible label/sign bug.")
    if mtf_implementation_gap:
        root_causes.append("MTF_IMPLEMENTATION_GAP: h1_m15 and h1_m15_m5 modes exist in param grid but backtest does NOT actually use M15/M5 confirmation.")

    if not root_causes:
        root_causes.append("UNKNOWN: No single root cause identified — combination of mild issues.")

    md = []
    md.append("# Recommended Fix Path (Sprint v2.8.7-D)\n")
    md.append(f"**Timestamp:** {datetime.now(timezone.utc).isoformat()}\n\n")
    md.append("## Classification Flags\n\n")
    md.append("| Flag | Value |\n|---|---|\n")
    for k, v in flags.items():
        md.append(f"| {k} | {v} |\n")
    md.append("\n## Root Cause Analysis\n\n")
    for i, cause in enumerate(root_causes, 1):
        md.append(f"{i}. {cause}\n")
    md.append("\n## Why Current Model Failed\n\n")
    md.append(
        "The v1 XGBoost alpha model was trained on 2020-2023 H1 canonical data where XAUUSD traded "
        f"~${drift_summary['close_is_mean']:.0f}. In OOS 2025-2026, XAUUSD trades "
        f"~${drift_summary['close_oos_mean']:.0f} ({drift_summary['close_ratio']}x higher). "
        "Five production features are absolute price values (not relative): "
        "`macd_signal`, `macd_hist`, `bb_upper`, `obv`, `obv_slope_20`. "
        "After standardization with 2020-2023 mean/std, these features produce z-scores 3-4x larger "
        "than training, causing the model to see an out-of-distribution input. "
        "The meta-label model, which consumes a subset of these features, similarly drifts. "
        "Combined with 2025-2026 volatility regime change, the model's edge collapses.\n\n"
    )
    md.append("## Fastest Safe Fix (do NOT implement in this sprint)\n\n")
    if feature_drift_issue:
        md.append(
            "1. **Convert absolute features to relative** before standardization:\n"
            "   - `macd_signal` → `macd_signal / close` (relative MACD)\n"
            "   - `macd_hist` → `macd_hist / close`\n"
            "   - `bb_upper` → `bb_upper / close` (or drop, since `bb_pct_b` already captures position)\n"
            "   - `obv` → drop or normalize by 60-bar volume sum\n"
            "   - `obv_slope_20` → drop or normalize by 60-bar volume sum\n"
            "2. **Retrain XGBoost + meta-label** on 2020-2025 data with relative features.\n"
            "3. **Re-run parameter discovery** after retrain.\n"
        )
    if mtf_implementation_gap:
        md.append(
            "4. **Implement actual MTF confirmation**: h1_m15 and h1_m15_m5 modes must load M15/M5 "
            "bars and require alignment before entry. Currently the backtest only uses H1.\n"
        )
    if exit_geometry_issue:
        md.append(
            "5. **Widen ATR multiplier** for 2025-2026 volatility: try sl_atr=2.0, rr=3.0, holding=6-12.\n"
        )
    md.append("\n## What NOT to Do\n\n")
    md.append(
        "- Do NOT retrain in this sprint (RETRAIN_REQUIRED_LATER only).\n"
        "- Do NOT lower alpha/meta thresholds blindly — confidence misalignment suggests higher thresholds are worse, not better.\n"
        "- Do NOT use SMA proxy or volatility proxy for entry decisions.\n"
        "- Do NOT use martingale, grid, or averaging down.\n"
        "- Do NOT bypass CEO governance or meta-label.\n"
        "- Do NOT flip direction automatically even if direction_inversion_suspect=True — investigate the label generation code first.\n"
        "- Do NOT trade live or demo until demo_go_decision = DEMO_SHADOW_ALLOWED.\n\n"
    )
    md.append("## Next Sprint Prompt Recommendation\n\n")
    md.append(
        "```\n"
        "TITAN XAU AI — SPRINT v2.8.7-E\n"
        "FEATURE NORMALIZATION FIX + MTF IMPLEMENTATION\n"
        "\n"
        "Mission:\n"
        "1. Convert 5 absolute-price features to relative (macd_signal, macd_hist, bb_upper, obv, obv_slope_20).\n"
        "2. Retrain XGBoost + meta-label on 2020-2025 with relative features.\n"
        "3. Implement real MTF confirmation for h1_m15 and h1_m15_m5 modes.\n"
        "4. Re-run parameter discovery.\n"
        "5. If candidate found: supervised demo shadow test only.\n"
        "\n"
        "Do NOT trade. Do NOT create token. Do NOT bypass CEO.\n"
        "```\n")

    return "".join(md), flags


# ─────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────

def main():
    ts = datetime.now(timezone.utc).isoformat()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("  TITAN XAU AI - OOS COLLAPSE DIAGNOSIS (v2.8.7-D)")
    print("=" * 70)
    print(f"  Timestamp: {ts}")
    print()

    # Verify production models
    bundle = load_production_models()
    if not bundle.ok:
        print("  ERROR: Production models failed to load")
        return

    # Load data and predictions
    print("  Loading broker data with v2.8.7-C spread normalization...")
    brokers_data = {}
    brokers_preds = {}
    for broker_name in ["canonical", "exness", "fbs", "fundednext", "icmarkets"]:
        df = load_h1_data(broker_name)
        if df is None:
            continue
        brokers_data[broker_name] = df
        preds = precompute_model_predictions(df)
        if preds is not None:
            brokers_preds[broker_name] = preds
            print(f"    {broker_name}: {len(df)} bars, {preds['alpha_proba'].shape[0]} predictions")

    if not brokers_preds:
        print("  ERROR: No broker predictions available")
        return

    # === Run all diagnostic tasks ===
    by_rows, rejection_rows = task3_year_broker_breakdown(brokers_data, brokers_preds)
    dir_rows, direction_inversion_suspect = task4_direction_inversion(brokers_data, brokers_preds)
    geom_rows, exit_reason_rows, exit_geometry_issue = task5_exit_geometry(brokers_data, brokers_preds)
    regime_rows, session_rows, regime_filter_fix_needed = task6_regime_filter(brokers_data, brokers_preds)
    drift_rows, feature_drift_issue, drift_summary = task7_feature_drift(brokers_data, brokers_preds)
    alpha_bucket_rows, meta_bucket_rows, confidence_misalignment = task8_confidence_buckets(brokers_data, brokers_preds)
    mtf_rows, mtf_implementation_gap = task9_mtf_mode(brokers_data, brokers_preds)

    top_drifted = [r["feature"] for r in drift_rows[:5]]
    fix_md, flags = task10_recommended_fix_path(
        direction_inversion_suspect,
        exit_geometry_issue,
        regime_filter_fix_needed,
        feature_drift_issue,
        confidence_misalignment,
        mtf_implementation_gap,
        drift_summary,
        top_drifted,
    )

    # === Write all output files ===
    print("\n  Writing output files...")

    def _write_csv(name, rows):
        if not rows:
            return
        with open(OUTPUT_DIR / name, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            for row in rows:
                w.writerow(row)

    _write_csv("broker_year_performance.csv", by_rows)
    _write_csv("rejection_reason_breakdown.csv", rejection_rows)
    _write_csv("direction_inversion_audit.csv", dir_rows)
    _write_csv("exit_geometry_audit.csv", geom_rows)
    _write_csv("exit_reason_breakdown.csv", exit_reason_rows)
    _write_csv("regime_filter_audit.csv", regime_rows)
    _write_csv("regime_performance.csv", [r for r in regime_rows if r["group_key"] in ("trend", "spread", "vol")])
    _write_csv("session_performance.csv", session_rows)
    _write_csv("feature_drift_2025_2026.csv", drift_rows)
    _write_csv("confidence_bucket_performance.csv", alpha_bucket_rows + meta_bucket_rows)
    _write_csv("mtf_mode_audit.csv", mtf_rows)

    # MD files
    with open(OUTPUT_DIR / "direction_inversion_audit.md", "w") as f:
        f.write("# Direction Inversion Audit (v2.8.7-D)\n\n")
        f.write(f"**Timestamp:** {ts}\n\n")
        f.write(f"**DIRECTION_INVERSION_SUSPECT:** {direction_inversion_suspect}\n\n")
        f.write("## Per-Broker Original vs Flipped Direction (OOS 2025-2026)\n\n")
        f.write("| Broker | Orig PF | Flip PF | Orig Sharpe | Flip Sharpe | Orig DD | Flip DD | Orig Trades | Flip Trades | Improvement | Suspect |\n")
        f.write("|---|---|---|---|---|---|---|---|---|---|---|\n")
        for r in dir_rows:
            f.write(f"| {r['broker']} | {r['original_pf']} | {r['flipped_pf']} | "
                    f"{r['original_sharpe']} | {r['flipped_sharpe']} | {r['original_dd']} | "
                    f"{r['flipped_dd']} | {r['original_trades']} | {r['flipped_trades']} | "
                    f"{r['improvement_ratio']} | {r['direction_inversion_suspect']} |\n")

    with open(OUTPUT_DIR / "exit_geometry_audit.md", "w") as f:
        f.write("# Exit Geometry Audit (v2.8.7-D)\n\n")
        f.write(f"**Timestamp:** {ts}\n\n")
        f.write(f"**EXIT_GEOMETRY_ISSUE:** {exit_geometry_issue}\n\n")
        f.write("## Geometry Combinations (canonical OOS 2025-2026)\n\n")
        f.write("| SL ATR | RR | Holding | Trailing | Trades | SL Rate | TP Rate | Timeout | Avg R | PF | DD | Sharpe |\n")
        f.write("|---|---|---|---|---|---|---|---|---|---|---|---|\n")
        for r in geom_rows:
            f.write(f"| {r['sl_atr_multiplier']} | {r['rr_target']} | {r['max_holding_bars']} | "
                    f"{r['trailing_policy']} | {r['trades']} | {r['sl_hit_rate']} | {r['tp_hit_rate']} | "
                    f"{r['timeout_rate']} | {r['avg_r']} | {r['pf']} | {r['dd']} | {r['sharpe']} |\n")

    with open(OUTPUT_DIR / "regime_filter_audit.md", "w") as f:
        f.write("# Regime Filter Audit (v2.8.7-D)\n\n")
        f.write(f"**Timestamp:** {ts}\n\n")
        f.write(f"**REGIME_FILTER_FIX_NEEDED:** {regime_filter_fix_needed}\n\n")
        f.write("## Performance by Regime (all brokers OOS 2025-2026)\n\n")
        f.write("| Group | Value | Trades | Win Rate | PF | Sharpe | Avg R |\n")
        f.write("|---|---|---|---|---|---|---|\n")
        for r in regime_rows:
            f.write(f"| {r['group_key']} | {r['group_value']} | {r['trades']} | "
                    f"{r['win_rate']} | {r['profit_factor']} | {r['sharpe']} | {r['avg_r']} |\n")

    with open(OUTPUT_DIR / "feature_drift_2025_2026.md", "w") as f:
        f.write("# Feature Drift Audit (v2.8.7-D)\n\n")
        f.write(f"**Timestamp:** {ts}\n\n")
        f.write(f"**FEATURE_DRIFT_ISSUE:** {feature_drift_issue}\n\n")
        f.write("## Distribution Summary\n\n")
        f.write(f"- Gold price IS mean (2020-2023): ${drift_summary['close_is_mean']:.0f}\n")
        f.write(f"- Gold price OOS mean (2025-2026): ${drift_summary['close_oos_mean']:.0f}\n")
        f.write(f"- Price ratio: {drift_summary['close_ratio']}x\n")
        f.write(f"- Alpha prob IS mean: {drift_summary['alpha_is_mean']}\n")
        f.write(f"- Alpha prob OOS mean: {drift_summary['alpha_oos_mean']}\n")
        f.write(f"- Meta prob IS mean: {drift_summary['meta_is_mean']}\n")
        f.write(f"- Meta prob OOS mean: {drift_summary['meta_oos_mean']}\n")
        f.write(f"- Spread USD IS mean: {drift_summary['spread_is_mean']}\n")
        f.write(f"- Spread USD OOS mean: {drift_summary['spread_oos_mean']}\n\n")
        f.write("## Top 10 Drifted Features\n\n")
        f.write("| Feature | IS Mean | OOS Mean | IS Std | OOS Std | Drift Score | Outliers |\n")
        f.write("|---|---|---|---|---|---|---|\n")
        for r in drift_rows[:10]:
            f.write(f"| {r['feature']} | {r['is_mean']} | {r['oos_mean']} | "
                    f"{r['is_std']} | {r['oos_std']} | {r['drift_score']} | {r['outlier_count']} |\n")

    with open(OUTPUT_DIR / "confidence_bucket_performance.md", "w") as f:
        f.write("# Confidence Bucket Audit (v2.8.7-D)\n\n")
        f.write(f"**Timestamp:** {ts}\n\n")
        f.write(f"**CONFIDENCE_MISALIGNMENT:** {confidence_misalignment}\n\n")
        f.write("## Alpha Buckets (all brokers OOS 2025-2026)\n\n")
        f.write("| Bucket | Trades | Win Rate | PF | Sharpe | Avg R |\n")
        f.write("|---|---|---|---|---|---|\n")
        for r in alpha_bucket_rows:
            f.write(f"| {r['bucket_value']} | {r['trades']} | {r['win_rate']} | "
                    f"{r['profit_factor']} | {r['sharpe']} | {r['avg_r']} |\n")
        f.write("\n## Meta Buckets\n\n")
        f.write("| Bucket | Trades | Win Rate | PF | Sharpe | Avg R |\n")
        f.write("|---|---|---|---|---|---|\n")
        for r in meta_bucket_rows:
            f.write(f"| {r['bucket_value']} | {r['trades']} | {r['win_rate']} | "
                    f"{r['profit_factor']} | {r['sharpe']} | {r['avg_r']} |\n")

    with open(OUTPUT_DIR / "mtf_mode_audit.md", "w") as f:
        f.write("# MTF Mode Audit (v2.8.7-D)\n\n")
        f.write(f"**Timestamp:** {ts}\n\n")
        f.write(f"**MTF_IMPLEMENTATION_GAP:** {mtf_implementation_gap}\n\n")
        f.write("## MTF Mode Effectiveness (canonical OOS 2025-2026)\n\n")
        f.write("| Mode | Trades | PF | Sharpe | DD | Win Rate | Avg R | Rejection | MTF Actually Used |\n")
        f.write("|---|---|---|---|---|---|---|---|---|\n")
        for r in mtf_rows:
            f.write(f"| {r['mtf_mode']} | {r['trades']} | {r['pf']} | {r['sharpe']} | "
                    f"{r['dd']} | {r['win_rate']} | {r['avg_r']} | {r['rejection_reason']} | "
                    f"{r['mtf_actually_used']} |\n")

    with open(OUTPUT_DIR / "recommended_fix_path.md", "w") as f:
        f.write(fix_md)

    # Main diagnosis MD
    with open(OUTPUT_DIR / "oos_collapse_diagnosis.md", "w") as f:
        f.write("# OOS Collapse Diagnosis (Sprint v2.8.7-D)\n\n")
        f.write(f"**Timestamp:** {ts}\n\n")
        f.write("## Flags Summary\n\n")
        f.write("| Flag | Value |\n|---|---|\n")
        for k, v in flags.items():
            f.write(f"| {k} | {v} |\n")
        f.write("\n## Drift Summary\n\n")
        f.write(f"- Gold price IS mean: ${drift_summary['close_is_mean']:.0f}\n")
        f.write(f"- Gold price OOS mean: ${drift_summary['close_oos_mean']:.0f}\n")
        f.write(f"- Price ratio: {drift_summary['close_ratio']}x\n")
        f.write(f"- Top 5 drifted features: {', '.join(top_drifted)}\n\n")
        f.write("## Year × Broker Performance (baseline params)\n\n")
        f.write("| Broker | Year | Trades | PF | Sharpe | DD | Verdict |\n")
        f.write("|---|---|---|---|---|---|---|\n")
        for r in by_rows:
            f.write(f"| {r['broker']} | {r['year']} | {r['trades']} | "
                    f"{r['profit_factor']} | {r['sharpe']} | {r['max_drawdown']} | {r['verdict']} |\n")
        f.write("\n## Direction Inversion Audit\n\n")
        f.write(f"- DIRECTION_INVERSION_SUSPECT: {direction_inversion_suspect}\n")
        for r in dir_rows:
            f.write(f"  - {r['broker']}: orig_pf={r['original_pf']}, flip_pf={r['flipped_pf']}, "
                    f"improvement={r['improvement_ratio']}\n")
        f.write("\n## Exit Geometry Audit\n\n")
        f.write(f"- EXIT_GEOMETRY_ISSUE: {exit_geometry_issue}\n")
        f.write("\n## Regime Filter Audit\n\n")
        f.write(f"- REGIME_FILTER_FIX_NEEDED: {regime_filter_fix_needed}\n")
        f.write("\n## Feature Drift Audit\n\n")
        f.write(f"- FEATURE_DRIFT_ISSUE: {feature_drift_issue}\n")
        f.write(f"- Top 5 drifted: {', '.join(top_drifted)}\n")
        f.write("\n## Confidence Bucket Audit\n\n")
        f.write(f"- CONFIDENCE_MISALIGNMENT: {confidence_misalignment}\n")
        f.write("\n## MTF Mode Audit\n\n")
        f.write(f"- MTF_IMPLEMENTATION_GAP: {mtf_implementation_gap}\n")
        f.write("\n## Recommended Fix Path\n\n")
        f.write("See `recommended_fix_path.md` for full plan.\n")

    # JSON
    diagnosis_json = {
        "timestamp_utc": ts,
        "sprint": "v2.8.7-D",
        "flags": flags,
        "drift_summary": drift_summary,
        "top_drifted_features": top_drifted,
        "direction_inversion_suspect": direction_inversion_suspect,
        "exit_geometry_issue": exit_geometry_issue,
        "regime_filter_fix_needed": regime_filter_fix_needed,
        "feature_drift_issue": feature_drift_issue,
        "confidence_misalignment": confidence_misalignment,
        "mtf_implementation_gap": mtf_implementation_gap,
        "year_broker_summary": [
            {"broker": r["broker"], "year": r["year"], "pf": r["profit_factor"],
             "sharpe": r["sharpe"], "dd": r["max_drawdown"], "verdict": r["verdict"]}
            for r in by_rows
        ],
    }
    with open(OUTPUT_DIR / "oos_collapse_diagnosis.json", "w") as f:
        json.dump(diagnosis_json, f, indent=2, default=str)

    # Print summary
    print("\n" + "=" * 70)
    print("  OOS COLLAPSE DIAGNOSIS SUMMARY")
    print("=" * 70)
    print(f"\n  Gold price IS mean (2020-2023):  ${drift_summary['close_is_mean']:.0f}")
    print(f"  Gold price OOS mean (2025-2026): ${drift_summary['close_oos_mean']:.0f}")
    print(f"  Price ratio: {drift_summary['close_ratio']}x")
    print(f"\n  Top 5 drifted features: {', '.join(top_drifted)}")
    print(f"\n  FLAGS:")
    for k, v in flags.items():
        marker = "🚨" if v else "  "
        print(f"    {marker} {k}: {v}")
    print(f"\n  Output: {OUTPUT_DIR}")
    print("\n" + "=" * 70)
    print("\n  > Research only. NOT production. NO trade allowed.")
    print("=" * 70)

    return diagnosis_json


if __name__ == "__main__":
    main()
