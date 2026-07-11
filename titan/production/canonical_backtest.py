"""TITAN XAU AI — Canonical Backtest Engine V3 (v2.8.7-P2.2)
=============================================================

Single authoritative backtest engine. v2.2 hardens:
  - ALL entry decisions delegated to CanonicalDecisionEngine via HistoricalAdapter
  - No inline alpha/meta gating, no hard-coded CEO states, no independent
    risk-governor construction — all come from the engine
  - Uses titan.production.instrument_valuation.price_delta_to_money for ALL
    monetary conversions
  - InstrumentSpec must be explicitly supplied (None fails closed)
  - Exact cost ledger: pnl_net = pnl_gross - total_cost
  - r_net = pnl_net / risk_amount
  - Gap handling on holding bars
  - Net PF = sum(pos net) / abs(sum(neg net))

The backtest retains ONLY:
  - chronological data iteration
  - entry/exit simulation
  - monetary accounting
  - equity/state updates
  - performance metrics

NEVER sends orders. NEVER creates tokens. NEVER trades.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, List
from datetime import datetime, timezone
import math
import numpy as np
import pandas as pd

from titan.production.direction_logic import interpret_direction
from titan.production.instrument_valuation import (
    InstrumentSpec, validate_instrument_spec,
    price_delta_to_money, compute_lot_size,
)
from titan.production.canonical_decision_engine import CanonicalDecision
from titan.production.decision_adapters import HistoricalAdapter
from titan.production.corrected_adaptive_threshold_v2 import SafetyStateV2
from titan.production.risk_governor import DAILY_LIMIT, TOTAL_LIMIT


@dataclass
class TradeV3:
    entry_bar: int
    entry_price: float
    exit_price: float
    exit_reason: str
    direction: str
    r_gross: float
    r_net: float
    pnl_gross: float
    pnl_net: float
    commission: float
    entry_spread_cost: float
    exit_spread_cost: float
    entry_slippage_cost: float
    exit_slippage_cost: float
    swap: float
    total_cost: float
    holding_bars: int
    timestamp_entry: str
    timestamp_exit: str
    lot_size: float = 0.0
    risk_amount: float = 0.0
    actual_risk_percent: float = 0.0
    monetary_loss_at_sl: float = 0.0
    regime: str = ""
    setup: str = ""
    alpha_proba: float = 0.0
    meta_proba: float = 0.0
    fold: int = 0
    trade_id: str = ""
    sl_price: float = 0.0
    tp_price: float = 0.0
    equity_before: float = 0.0
    equity_after: float = 0.0
    daily_dd_before: float = 0.0
    total_dd_before: float = 0.0
    decision_id: str = ""
    approved_risk: float = 0.0


@dataclass
class BacktestResultV3:
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    net_profit: float = 0.0
    pf_gross: float = 0.0
    pf_net: float = 0.0
    max_total_dd: float = 0.0
    max_daily_dd: float = 0.0
    daily_dd_breaches: int = 0
    total_dd_breaches: int = 0
    max_consecutive_losses: int = 0
    sharpe: float = 0.0
    sortino: float = 0.0
    calmar: float = 0.0
    recovery_factor: float = 0.0
    expectancy: float = 0.0
    total_return: float = 0.0
    total_commission: float = 0.0
    total_spread_cost: float = 0.0
    total_slippage_cost: float = 0.0
    total_swap: float = 0.0
    final_equity: float = 0.0
    starting_equity: float = 0.0
    equity_peak: float = 0.0
    max_monetary_dd: float = 0.0
    exposure_time: float = 0.0
    avg_holding_bars: float = 0.0


def validate_inputs_v3(df, alpha, meta, atr, instrument: Optional[InstrumentSpec]) -> dict:
    if df is None or len(df) == 0:
        return {"valid": False, "error": "empty DataFrame"}
    for col in ["open", "high", "low", "close"]:
        if col not in df.columns:
            return {"valid": False, "error": f"missing column: {col}"}
    if "spread_usd" not in df.columns:
        return {"valid": False, "error": "missing spread_usd"}
    for col in ["open", "high", "low", "close", "spread_usd"]:
        if df[col].isna().any():
            return {"valid": False, "error": f"NaN in {col}"}
        if np.isinf(df[col].values).any():
            return {"valid": False, "error": f"inf in {col}"}
    if atr is None or np.all(atr <= 0):
        return {"valid": False, "error": "ATR invalid"}
    n = len(df)
    if len(alpha) != n or len(meta) != n or len(atr) != n:
        return {"valid": False, "error": "length mismatch"}
    if not isinstance(df.index, pd.DatetimeIndex):
        return {"valid": False, "error": "not DatetimeIndex"}
    if not df.index.is_monotonic_increasing:
        return {"valid": False, "error": "not monotonic"}
    if df.index.duplicated().any():
        return {"valid": False, "error": "duplicate timestamps"}
    if instrument is None:
        return {"valid": False, "error": "instrument_spec_missing"}
    ok, msg = validate_instrument_spec(instrument)
    if not ok:
        return {"valid": False, "error": msg}
    return {"valid": True, "error": ""}


def run_backtest_v3(
    df: pd.DataFrame,
    alpha_proba: np.ndarray,
    meta_proba: np.ndarray,
    atr_values: np.ndarray,
    params: dict,
    instrument: Optional[InstrumentSpec] = None,
    starting_equity: float = 100000.0,
    fold: int = 0,
    regime_labels: Optional[np.ndarray] = None,
    safety_state: Optional[SafetyStateV2] = None,
) -> tuple[List[TradeV3], BacktestResultV3]:
    """Canonical backtest using CanonicalDecisionEngine for ALL entry decisions.

    If `instrument` is None or invalid, fails closed.
    If `safety_state` is None, builds a minimal valid state from params.
    """
    val = validate_inputs_v3(df, alpha_proba, meta_proba, atr_values, instrument)
    if not val["valid"]:
        return [], BacktestResultV3(starting_equity=starting_equity, final_equity=starting_equity)

    assert instrument is not None

    # Build safety state if not provided
    if safety_state is None:
        safety_state = _build_default_safety_state(params)

    # Build HistoricalAdapter
    adapter = HistoricalAdapter(
        instrument=instrument,
        config=params,
        safety_state=safety_state,
        equity=starting_equity,
        equity_peak=starting_equity,
        daily_peak=starting_equity,
        daily_start_equity=starting_equity,
    )

    equity = starting_equity
    equity_peak = starting_equity
    daily_peak = starting_equity
    daily_start = starting_equity

    wins = losses = 0
    gross_profit = gross_loss = 0.0
    net_profit = 0.0
    max_total_dd = 0.0
    max_daily_dd = 0.0
    max_consecutive_losses = 0
    consecutive_losses = 0
    daily_dd_breaches = 0
    total_dd_breaches = 0
    daily_dd_breached = False
    total_dd_breached = False
    total_commission = 0.0
    total_spread = 0.0
    total_slippage = 0.0
    total_swap = 0.0
    max_monetary_dd = 0.0

    daily_trades = 0
    current_day = None
    cooldown = 0
    r_net_list = []
    trades: List[TradeV3] = []
    daily_equity = {}

    closes = df["close"].values
    opens = df["open"].values
    highs = df["high"].values
    lows = df["low"].values
    spreads = df["spread_usd"].values
    index = df.index

    max_holding = params.get("max_holding_bars", 3)
    max_trades_day = params.get("max_trades_per_day", 2)
    cooldown_after_loss = params.get("cooldown_after_loss", 5)
    spread_filter = params.get("spread_filter", 1.0)
    commission_per_lot = params.get("commission_per_lot", 7.0)
    slippage_pts = params.get("slippage_points", 0.5)
    swap_per_bar = params.get("swap_per_bar", 0.0)
    sl_mult = params.get("sl_atr_multiplier", 2.0)
    rr_target = params.get("rr_target", 3.0)

    trade_counter = 0

    # Pre-compute base alpha threshold for performance pre-filter
    base_alpha_threshold = params.get("alpha_threshold", 0.55)

    # Start from bar 30 to ensure sufficient distribution samples (>= 30) for adaptive policy
    for i in range(30, len(df) - max_holding - 2):
        # Daily reset
        bar_day = index[i].date()
        if current_day != bar_day:
            if current_day is not None:
                daily_equity[current_day] = equity
            current_day = bar_day
            daily_start = equity
            daily_peak = equity
            daily_trades = 0
            daily_dd_breached = False

        # DD checks
        if equity > equity_peak:
            equity_peak = equity
        total_dd = (equity_peak - equity) / equity_peak if equity_peak > 0 else 0
        if total_dd > max_total_dd:
            max_total_dd = total_dd
            max_monetary_dd = equity_peak - equity
        if total_dd >= TOTAL_LIMIT:
            if not total_dd_breached:
                total_dd_breaches += 1
                total_dd_breached = True
            continue
        else:
            total_dd_breached = False

        if equity > daily_peak:
            daily_peak = equity
        daily_dd = (daily_peak - equity) / daily_peak if daily_peak > 0 else 0
        if daily_dd > max_daily_dd:
            max_daily_dd = daily_dd
        if daily_dd >= DAILY_LIMIT:
            if not daily_dd_breached:
                daily_dd_breaches += 1
                daily_dd_breached = True
            continue

        if daily_trades >= max_trades_day:
            continue
        if cooldown > 0:
            cooldown -= 1
            continue

        # ===== ALL ENTRY DECISIONS VIA CanonicalDecisionEngine =====
        # Update adapter with current equity/peaks
        adapter.equity = equity
        adapter.equity_peak = equity_peak
        adapter.daily_peak = daily_peak
        adapter.daily_start_equity = daily_start
        adapter.loss_streak = consecutive_losses

        atr = float(atr_values[i])
        spread = float(spreads[i])

        # Performance pre-filter: skip bars where dir_confidence < base_alpha_threshold.
        # The engine's effective threshold is always >= base_alpha_threshold, so these
        # bars would be rejected by the engine anyway. This is NOT decision logic —
        # it's a performance optimization. The engine still makes the actual decision
        # with adaptive thresholds for all bars that pass this pre-filter.
        p_up = float(alpha_proba[i])
        dir_conf = max(p_up, 1.0 - p_up)
        if dir_conf < base_alpha_threshold:
            continue

        # Entry at next bar open
        entry_bar = i + 1
        if entry_bar >= len(df):
            continue
        entry_price_ref = float(opens[entry_bar])

        # Build recent distributions for adaptive policy (real model predictions)
        # Use all bars from start to current to ensure >= 30 samples
        alpha_dist = alpha_proba[0:i + 1]
        meta_dist = meta_proba[0:i + 1]

        # Update adapter safety state with current DD values
        adapter.safety_state.dd_state = {
            "current_dd": float(total_dd), "daily_dd": float(daily_dd),
        }
        adapter.safety_state.external_daily_dd = float(daily_dd)
        adapter.safety_state.external_total_dd = float(total_dd)
        adapter.safety_state.loss_streak = consecutive_losses
        adapter.safety_state.alpha_distribution = [float(x) for x in alpha_dist if np.isfinite(x)]
        adapter.safety_state.meta_distribution = [float(x) for x in meta_dist if np.isfinite(x)]

        decision = adapter.evaluate_bar(
            df=df, i=i,
            alpha_proba=float(alpha_proba[i]),
            meta_proba=float(meta_proba[i]),
            atr_value=atr,
            entry_price=entry_price_ref,
            spread=spread,
            timestamp=str(index[i]),
            alpha_dist=alpha_dist,
            meta_dist=meta_dist,
        )

        # Only proceed if engine approved a signal
        if decision.final_decision != "HISTORICAL_SIGNAL":
            continue

        # Engine approved — use its values for entry
        approved_risk = decision.approved_risk
        direction = decision.direction
        sl_price = decision.sl_price
        tp_price = decision.tp_price
        lot = decision.lot_size
        monetary_loss_at_sl = decision.monetary_loss_at_sl
        risk_amount = decision.risk_amount

        # Compute actual entry price (with spread + slippage)
        if direction == "LONG":
            entry_price = float(opens[entry_bar]) + spread + slippage_pts
        else:
            entry_price = float(opens[entry_bar]) - spread - slippage_pts
        # Recompute SL/TP from actual entry
        sl_distance = atr * sl_mult
        tp_distance = sl_distance * rr_target
        if direction == "LONG":
            sl_price = entry_price - sl_distance
            tp_price = entry_price + tp_distance
        else:
            sl_price = entry_price + sl_distance
            tp_price = entry_price - tp_distance

        # ===== Entry/Exit Simulation (retained in backtest) =====
        exit_price = entry_price
        exit_reason = "TIMEOUT"
        r_gross = 0.0
        holding = 0
        actual_exit_bar = entry_bar

        for j in range(0, max_holding + 1):
            bar_idx = entry_bar + j
            if bar_idx >= len(df):
                break
            holding = j + 1 if j > 0 else 1
            actual_exit_bar = bar_idx

            if j > 0:
                if direction == "LONG" and float(opens[bar_idx]) <= sl_price:
                    exit_price = float(opens[bar_idx])
                    exit_reason = "SL_GAP"
                    break
                if direction == "SHORT" and float(opens[bar_idx]) >= sl_price:
                    exit_price = float(opens[bar_idx])
                    exit_reason = "SL_GAP"
                    break

            if direction == "LONG":
                if float(lows[bar_idx]) <= sl_price:
                    exit_price = sl_price
                    exit_reason = "SL_HIT"
                    break
                if float(highs[bar_idx]) >= tp_price:
                    exit_price = tp_price
                    exit_reason = "TP_HIT"
                    break
            else:
                if float(highs[bar_idx]) >= sl_price:
                    exit_price = sl_price
                    exit_reason = "SL_HIT"
                    break
                if float(lows[bar_idx]) <= tp_price:
                    exit_price = tp_price
                    exit_reason = "TP_HIT"
                    break

        if exit_reason == "TIMEOUT":
            last = min(entry_bar + max_holding, len(df) - 1)
            actual_exit_bar = last
            exit_price = float(closes[last])

        # ===== Monetary Accounting (retained in backtest) =====
        if direction == "LONG":
            price_delta = exit_price - entry_price
        else:
            price_delta = entry_price - exit_price
        pnl_gross = price_delta_to_money(instrument, price_delta, lot)

        entry_spread_cost = price_delta_to_money(instrument, spread, lot)
        exit_spread_cost = price_delta_to_money(instrument, spread, lot)
        entry_slip = price_delta_to_money(instrument, slippage_pts, lot)
        exit_slip = price_delta_to_money(instrument, slippage_pts, lot)
        commission = commission_per_lot * lot
        swap = swap_per_bar * lot * holding

        total_cost = entry_spread_cost + exit_spread_cost + entry_slip + exit_slip + commission + swap
        pnl_net = pnl_gross - total_cost
        r_net = pnl_net / max(risk_amount, 0.001)
        r_gross = pnl_gross / max(risk_amount, 0.001)

        actual_risk_percent = monetary_loss_at_sl / equity if equity > 0 else 0.0
        equity_before = equity
        equity += pnl_net
        daily_trades += 1

        # Update peaks
        if equity > equity_peak:
            equity_peak = equity
        if equity > daily_peak:
            daily_peak = equity
        td_now = (equity_peak - equity) / equity_peak if equity_peak > 0 else 0
        if td_now > max_total_dd:
            max_total_dd = td_now
            max_monetary_dd = equity_peak - equity
        dd_now = (daily_peak - equity) / daily_peak if daily_peak > 0 else 0
        if dd_now > max_daily_dd:
            max_daily_dd = dd_now

        gross_profit += pnl_gross if pnl_gross > 0 else 0
        gross_loss += abs(pnl_gross) if pnl_gross < 0 else 0
        net_profit += pnl_net
        total_commission += commission
        total_spread += entry_spread_cost + exit_spread_cost
        total_slippage += entry_slip + exit_slip
        total_swap += swap
        r_net_list.append(r_net)

        if pnl_net > 0:
            wins += 1
            consecutive_losses = 0
        else:
            losses += 1
            consecutive_losses += 1
            max_consecutive_losses = max(max_consecutive_losses, consecutive_losses)
            cooldown = cooldown_after_loss

        trade_counter += 1
        trade_id = f"t{fold:02d}_{trade_counter:05d}"
        regime_label = ""
        if regime_labels is not None and i < len(regime_labels):
            regime_label = str(regime_labels[i])

        trades.append(TradeV3(
            entry_bar=entry_bar, entry_price=round(entry_price, 4),
            exit_price=round(exit_price, 4), exit_reason=exit_reason,
            direction=direction,
            r_gross=round(r_gross, 6), r_net=round(r_net, 6),
            pnl_gross=round(pnl_gross, 2), pnl_net=round(pnl_net, 2),
            commission=round(commission, 2),
            entry_spread_cost=round(entry_spread_cost, 2),
            exit_spread_cost=round(exit_spread_cost, 2),
            entry_slippage_cost=round(entry_slip, 2),
            exit_slippage_cost=round(exit_slip, 2),
            swap=round(swap, 2), total_cost=round(total_cost, 2),
            holding_bars=holding,
            timestamp_entry=str(index[entry_bar]),
            timestamp_exit=str(index[actual_exit_bar]),
            lot_size=round(lot, 4),
            risk_amount=round(risk_amount, 2),
            actual_risk_percent=round(actual_risk_percent, 6),
            monetary_loss_at_sl=round(monetary_loss_at_sl, 2),
            regime=regime_label, setup=decision.setup_selected or "",
            alpha_proba=round(float(alpha_proba[i]), 6),
            meta_proba=round(float(meta_proba[i]), 6),
            fold=fold, trade_id=trade_id,
            sl_price=round(sl_price, 4), tp_price=round(tp_price, 4),
            equity_before=round(equity_before, 2),
            equity_after=round(equity, 2),
            daily_dd_before=round(dd_now, 6),
            total_dd_before=round(td_now, 6),
            decision_id=decision.decision_id,
            approved_risk=approved_risk,
        ))

    if current_day is not None:
        daily_equity[current_day] = equity

    # Metrics computation (retained in backtest)
    pos_net = sum(t.pnl_net for t in trades if t.pnl_net > 0)
    neg_net = abs(sum(t.pnl_net for t in trades if t.pnl_net < 0))
    pf_gross = gross_profit / gross_loss if gross_loss > 0 else (999.0 if gross_profit > 0 else 0)
    pf_net = pos_net / neg_net if neg_net > 0 else (999.0 if pos_net > 0 else 0)

    total_trades = wins + losses
    win_rate = wins / total_trades if total_trades > 0 else 0
    total_return = (equity - starting_equity) / starting_equity

    if len(daily_equity) > 1:
        eq_series = pd.Series(list(daily_equity.values()))
        daily_rets = eq_series.pct_change().dropna()
        if len(daily_rets) > 0 and daily_rets.std() > 0:
            sharpe = float(daily_rets.mean() / daily_rets.std() * (252 ** 0.5))
            downside = daily_rets[daily_rets < 0]
            if len(downside) > 0 and downside.std() > 0:
                sortino = float(daily_rets.mean() / downside.std() * (252 ** 0.5))
            else:
                sortino = 0.0
        else:
            sharpe = sortino = 0.0
    else:
        sharpe = sortino = 0.0

    if len(trades) > 0 and starting_equity > 0 and equity != starting_equity:
        first_ts = pd.Timestamp(trades[0].timestamp_entry)
        last_ts = pd.Timestamp(trades[-1].timestamp_exit)
        years = max((last_ts - first_ts).total_seconds() / (365.25 * 24 * 3600), 0.001)
        cagr = (equity / starting_equity) ** (1 / years) - 1 if years > 0 else 0
    else:
        cagr = 0
    calmar = cagr / max(max_total_dd, 0.001) if max_total_dd > 0 else 0
    recovery = net_profit / max(max_monetary_dd, 1) if max_monetary_dd > 0 else 0
    expectancy = float(np.mean(r_net_list)) if r_net_list else 0
    avg_hold = float(np.mean([t.holding_bars for t in trades])) if trades else 0

    metrics = BacktestResultV3(
        total_trades=total_trades, wins=wins, losses=losses,
        win_rate=round(win_rate, 4),
        gross_profit=round(gross_profit, 2), gross_loss=round(gross_loss, 2),
        net_profit=round(net_profit, 2),
        pf_gross=round(pf_gross, 4) if pf_gross != 999 else 999,
        pf_net=round(pf_net, 4) if pf_net != 999 else 999,
        max_total_dd=round(max_total_dd, 6), max_daily_dd=round(max_daily_dd, 6),
        daily_dd_breaches=daily_dd_breaches, total_dd_breaches=total_dd_breaches,
        max_consecutive_losses=max_consecutive_losses,
        sharpe=round(sharpe, 4), sortino=round(sortino, 4),
        calmar=round(calmar, 4), recovery_factor=round(recovery, 4),
        expectancy=round(expectancy, 4), total_return=round(total_return, 6),
        total_commission=round(total_commission, 2),
        total_spread_cost=round(total_spread, 2),
        total_slippage_cost=round(total_slippage, 2),
        total_swap=round(total_swap, 2),
        final_equity=round(equity, 2), starting_equity=starting_equity,
        equity_peak=round(equity_peak, 2),
        max_monetary_dd=round(max_monetary_dd, 2),
        exposure_time=round(sum(t.holding_bars for t in trades) / max(len(df), 1), 4),
        avg_holding_bars=round(avg_hold, 2),
    )
    return trades, metrics


def _build_default_safety_state(params: dict) -> SafetyStateV2:
    """Build a minimal valid SafetyStateV2 for backtest mode.

    In backtest mode, we don't have a live account store or broker intelligence.
    We build a state with explicit values that are appropriate for historical replay:
      - All safety flags = True (historical mode assumes safe conditions)
      - DD values = 0 (no open positions at start)
      - Calibration = from params

    NOTE: This is NOT a safe literal — it's an explicit declaration that
    historical replay assumes safe conditions. In shadow mode, the real
    ShadowAccountStateStore and component monitors provide actual values.
    """
    return SafetyStateV2(
        dd_state={"current_dd": 0.0, "daily_dd": 0.0},
        margin_state={"margin_usage": 0.0, "margin_safe": True},
        prop_risk_state={"prop_pass": True, "prop_violations": 0},
        capital_protection={"active": False, "dd_breach": False},
        broker_intelligence={"broker_pass": True, "spread_pass": True},
        execution_health={"healthy": True},
        model_health={"model_health_pass": True},
        spread_state={"current_spread": 0.15, "average_spread": 0.15},
        volatility_state={"current_atr": 5.0, "average_atr": 5.0, "regime": "STABLE_RANGE"},
        loss_streak=0, signal_drought_hours=0,
        regime_confidence=0.7,
        alpha_distribution=[0.55] * 50,
        meta_distribution=[0.55] * 50,
        recent_shadow_evidence={"false_negative_rate": 0, "sample_size": 50},
        external_daily_dd=0.0, external_total_dd=0.0,
        calibration_metrics={"brier_score": 0.20, "calibration_slope": 1.0, "calibration_intercept": 0.0},
        regime="STABLE_RANGE", market_data_stale=False,
    )


__all__ = [
    "InstrumentSpec", "TradeV3", "BacktestResultV3",
    "validate_instrument_spec", "compute_monetary_loss_per_lot", "compute_lot_size",
    "price_delta_to_money",
    "validate_inputs_v3", "run_backtest_v3",
    "valid_xauusd_instrument_spec",
]
