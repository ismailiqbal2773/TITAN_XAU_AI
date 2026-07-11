"""TITAN XAU AI — Canonical Backtest Engine V3 (Sprint v2.8.7-P1.2)
====================================================================
Single authoritative backtest engine. Fixes:
  - Gap logic on holding bars (not entry bar — entry is at open)
  - InstrumentSpec (no hard-coded contract size)
  - Risk governor integration
  - Per-trade cost tracking (entry spread, exit spread, entry slippage, exit slippage)
  - Net PF = sum(pos net) / abs(sum(neg net))
  - Daily equity curve for Sharpe/Sortino
  - Direction logic (threshold on directional confidence)

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
from titan.production.risk_governor import (
    govern_risk, RiskGovernorInput,
    DAILY_LIMIT, TOTAL_LIMIT,
)


@dataclass
class InstrumentSpec:
    """Validated instrument specification."""
    tick_size: float = 0.01
    tick_value: float = 1.0
    contract_size: float = 100.0   # 100 oz for XAUUSD
    volume_min: float = 0.01
    volume_max: float = 100.0
    volume_step: float = 0.01
    account_currency: str = "USD"
    symbol_currency: str = "USD"


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


def validate_inputs_v3(df, alpha, meta, atr, instrument: InstrumentSpec) -> dict:
    """Validate all inputs. Fail closed on any invalid data."""
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
    if instrument.contract_size <= 0:
        return {"valid": False, "error": "invalid contract_size"}
    return {"valid": True, "error": ""}


def run_backtest_v3(
    df: pd.DataFrame,
    alpha_proba: np.ndarray,
    meta_proba: np.ndarray,
    atr_values: np.ndarray,
    params: dict,
    instrument: InstrumentSpec = InstrumentSpec(),
    starting_equity: float = 100000.0,
) -> tuple[List[TradeV3], BacktestResultV3]:
    """Canonical backtest with risk governor, gap handling, and full cost tracking."""
    val = validate_inputs_v3(df, alpha_proba, meta_proba, atr_values, instrument)
    if not val["valid"]:
        return [], BacktestResultV3(starting_equity=starting_equity, final_equity=starting_equity)

    from titan.production.ceo_ai_governance import evaluate_ceo_decision

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
    trades = []
    daily_equity = {}  # date -> equity at end of day

    closes = df["close"].values
    opens = df["open"].values
    highs = df["high"].values
    lows = df["low"].values
    spreads = df["spread_usd"].values
    index = df.index

    alpha_t = params.get("alpha_threshold", 0.55)
    meta_t = params.get("meta_threshold", 0.50)
    risk_pct = params.get("risk_percent", 0.003)
    sl_mult = params.get("sl_atr_multiplier", 2.0)
    rr_target = params.get("rr_target", 3.0)
    max_holding = params.get("max_holding_bars", 3)
    max_trades_day = params.get("max_trades_per_day", 2)
    cooldown_after_loss = params.get("cooldown_after_loss", 5)
    spread_filter = params.get("spread_filter", 1.0)
    commission_per_lot = params.get("commission_per_lot", 7.0)
    slippage_pts = params.get("slippage_points", 0.5)
    swap_per_bar = params.get("swap_per_bar", 0.0)
    setup_class = params.get("setup_class", "A")

    for i in range(28, len(df) - max_holding - 2):
        # DG1: Reset daily FIRST
        bar_day = index[i].date()
        if current_day != bar_day:
            if current_day is not None:
                daily_equity[current_day] = equity
            current_day = bar_day
            daily_start = equity
            daily_peak = equity
            daily_trades = 0
            daily_dd_breached = False

        # DD after reset
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

        # DG3: Direction logic
        p_up = float(alpha_proba[i])
        direction, dir_confidence = interpret_direction(p_up)
        if dir_confidence < alpha_t:
            continue

        meta_conf = float(meta_proba[i])
        if meta_conf < meta_t:
            continue

        spread = float(spreads[i])
        if spread > spread_filter:
            continue

        # CEO
        ceo = evaluate_ceo_decision(
            regime_state={"detected": True, "regime_value": "MARKET_OPEN", "confidence": dir_confidence},
            xgb_alpha={"direction": direction, "confidence": dir_confidence, "pass": True},
            lstm_confidence=None, transformer_regime=None,
            meta_label_quality={"quality_score": meta_conf, "pass": True},
            broker_state={"broker_pass": True, "spread_pass": True, "slippage_pass": True},
            prop_risk_state={"risk_pass": True, "prop_funded_pass": True, "max_positions_ok": True},
            capital_protection_state={"capital_preservation_active": False, "dd_breach": False},
            model_health_state={"model_health_pass": True, "failed_required": 0},
            geometry_state={"geometry_pass": True, "actual_RR": rr_target, "minimum_RR": 2.0},
        )
        if not ceo.allowed_to_trade:
            continue

        atr = float(atr_values[i])
        if atr <= 0:
            continue
        sl_distance = atr * sl_mult
        tp_distance = sl_distance * rr_target

        # Risk governor
        gov_inp = RiskGovernorInput(
            equity=equity, equity_peak=equity_peak,
            daily_peak=daily_peak, daily_start_equity=daily_start,
            proposed_risk=risk_pct, setup_class=setup_class,
            existing_risk=0.0, loss_streak=consecutive_losses,
            regime_risk_modifier=1.0, broker_risk_modifier=1.0,
            prop_risk_pass=True, capital_protection_active=False,
        )
        gov_out = govern_risk(gov_inp)
        if not gov_out.approved:
            continue
        approved_risk = gov_out.approved_risk

        # Entry at next bar open
        entry_bar = i + 1
        if entry_bar >= len(df):
            continue
        # Direction-aware spread
        if direction == "LONG":
            entry_price = float(opens[entry_bar]) + spread + slippage_pts
        else:
            entry_price = float(opens[entry_bar]) - spread - slippage_pts

        if direction == "LONG":
            sl_price = entry_price - sl_distance
            tp_price = entry_price + tp_distance
        else:
            sl_price = entry_price + sl_distance
            tp_price = entry_price - tp_distance

        # Exit simulation: scan from entry_bar (j=0 = entry bar itself)
        exit_price = entry_price
        exit_reason = "TIMEOUT"
        r_gross = 0.0
        holding = 0
        actual_exit_bar = entry_bar  # Default to entry bar

        for j in range(0, max_holding + 1):
            bar_idx = entry_bar + j
            if bar_idx >= len(df):
                break
            holding = j + 1 if j > 0 else 1
            actual_exit_bar = bar_idx

            # Gap check on HOLDING bars (j > 0): open gaps beyond SL
            if j > 0:
                if direction == "LONG" and float(opens[bar_idx]) <= sl_price:
                    exit_price = float(opens[bar_idx])  # Fill at gap open
                    exit_reason = "SL_GAP"
                    r_gross = (exit_price - entry_price) / sl_distance
                    break
                if direction == "SHORT" and float(opens[bar_idx]) >= sl_price:
                    exit_price = float(opens[bar_idx])
                    exit_reason = "SL_GAP"
                    r_gross = (entry_price - exit_price) / sl_distance
                    break

            # Normal SL/TP check (conservative: SL first)
            if direction == "LONG":
                if float(lows[bar_idx]) <= sl_price:
                    exit_price = sl_price
                    exit_reason = "SL_HIT"
                    r_gross = -1.0
                    break
                if float(highs[bar_idx]) >= tp_price:
                    exit_price = tp_price
                    exit_reason = "TP_HIT"
                    r_gross = rr_target
                    break
            else:
                if float(highs[bar_idx]) >= sl_price:
                    exit_price = sl_price
                    exit_reason = "SL_HIT"
                    r_gross = -1.0
                    break
                if float(lows[bar_idx]) <= tp_price:
                    exit_price = tp_price
                    exit_reason = "TP_HIT"
                    r_gross = rr_target
                    break

        if exit_reason == "TIMEOUT":
            last = min(entry_bar + max_holding, len(df) - 1)
            exit_price = float(closes[last])
            r_gross = (exit_price - entry_price) / sl_distance if direction == "LONG" \
                      else (entry_price - exit_price) / sl_distance

        # Direction-aware exit spread
        if direction == "LONG":
            exit_price_net = exit_price - spread - slippage_pts
        else:
            exit_price_net = exit_price + spread + slippage_pts

        # Costs (calculated BEFORE r_net so commission/swap can be included)
        risk_amount = equity * approved_risk
        lot = risk_amount / (sl_distance * instrument.contract_size)
        commission = commission_per_lot * lot
        entry_spread_cost = risk_amount * (spread / sl_distance)
        exit_spread_cost = risk_amount * (spread / sl_distance)
        entry_slip = risk_amount * (slippage_pts / sl_distance)
        exit_slip = risk_amount * (slippage_pts / sl_distance)
        swap = swap_per_bar * lot * holding
        total_cost = commission + entry_spread_cost + exit_spread_cost + entry_slip + exit_slip + swap

        # Net R: includes spread, slippage, commission, swap
        r_net = (exit_price_net - entry_price) / sl_distance if direction == "LONG" \
                else (entry_price - exit_price_net) / sl_distance
        # Subtract commission and swap in R terms
        commission_in_r = commission / max(risk_amount, 0.001)
        swap_in_r = swap / max(risk_amount, 0.001)
        r_net = r_net - commission_in_r - swap_in_r

        pnl_gross = risk_amount * r_gross
        pnl_net = risk_amount * r_net

        equity += pnl_net
        daily_trades += 1

        # Update peaks immediately
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

        trades.append(TradeV3(
            entry_bar=entry_bar, entry_price=round(entry_price, 4),
            exit_price=round(exit_price, 4), exit_reason=exit_reason,
            direction=direction,
            r_gross=round(r_gross, 4), r_net=round(r_net, 4),
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
        ))

    if current_day is not None:
        daily_equity[current_day] = equity

    # Net PF: sum(pos net) / abs(sum(neg net))
    pos_net = sum(t.pnl_net for t in trades if t.pnl_net > 0)
    neg_net = abs(sum(t.pnl_net for t in trades if t.pnl_net < 0))
    pf_gross = gross_profit / gross_loss if gross_loss > 0 else (999.0 if gross_profit > 0 else 0)
    pf_net = pos_net / neg_net if neg_net > 0 else (999.0 if pos_net > 0 else 0)

    total_trades = wins + losses
    win_rate = wins / total_trades if total_trades > 0 else 0
    total_return = (equity - starting_equity) / starting_equity

    # Sharpe from daily equity
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

    # CAGR from actual timestamps
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


__all__ = [
    "InstrumentSpec", "TradeV3", "BacktestResultV3",
    "validate_inputs_v3", "run_backtest_v3",
]
