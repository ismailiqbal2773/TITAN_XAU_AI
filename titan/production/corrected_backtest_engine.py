"""TITAN XAU AI — Corrected Backtest Engine (Sprint v2.8.7-P1)
===============================================================
Fixes all backtest integrity bugs from v2.8.7-P:
  1. True peak-to-trough drawdown using high-water mark
  2. Next-bar-open entry (no lookahead)
  3. Daily peak-to-trough drawdown
  4. Commission, spread, slippage costs
  5. Conservative same-bar SL/TP resolution (SL first)
  6. Daily DD limit = 2% (not 3%)
  7. Gross and post-cost metrics reported separately

NEVER sends orders. NEVER creates tokens. NEVER trades.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
import numpy as np
import pandas as pd


# Corrected DD limits per spec
EXT_DAILY_DD_LIMIT = 0.02   # 2% daily (was 3%)
EXT_TOTAL_DD_LIMIT = 0.08   # 8% total

# Internal protection stages
DAILY_CAUTION = 0.010
DAILY_RECOVERY = 0.013
DAILY_BLOCK_ENTRIES = 0.016
DAILY_EMERGENCY = 0.018

TOTAL_RECOVERY = 0.040
TOTAL_CAPITAL_PRESERVATION = 0.055
TOTAL_BLOCK_ENTRIES = 0.065
TOTAL_EMERGENCY_LOCK = 0.072


@dataclass
class TradeResult:
    """Result of a single trade."""
    entry_bar: int
    entry_price: float
    exit_price: float
    exit_reason: str
    direction: str
    r_result: float
    pnl_gross: float
    commission_cost: float
    spread_cost: float
    slippage_cost: float
    pnl_net: float
    timestamp_entry: str
    timestamp_exit: str
    holding_bars: int


@dataclass
class BacktestMetrics:
    """Corrected backtest metrics with true DD and cost accounting."""
    # Trade stats
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0
    # Profit
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    net_profit: float = 0.0
    profit_factor_gross: float = 0.0
    profit_factor_net: float = 0.0
    # Risk
    max_total_dd: float = 0.0          # True peak-to-trough
    max_daily_dd: float = 0.0          # True daily peak-to-trough
    daily_dd_breaches: int = 0
    total_dd_breaches: int = 0
    max_consecutive_losses: int = 0
    # Performance
    sharpe: float = 0.0
    sortino: float = 0.0
    calmar: float = 0.0
    recovery_factor: float = 0.0
    avg_trade: float = 0.0
    expectancy: float = 0.0
    total_return: float = 0.0
    # Costs
    total_commission: float = 0.0
    total_spread_cost: float = 0.0
    total_slippage_cost: float = 0.0
    # Final
    final_equity: float = 0.0
    starting_equity: float = 0.0
    equity_peak: float = 0.0


def run_corrected_backtest(
    df: pd.DataFrame,
    alpha_proba: np.ndarray,
    meta_proba: np.ndarray,
    atr_values: np.ndarray,
    params: dict,
    starting_equity: float = 100000.0,
    commission_per_lot: float = 7.0,
    slippage_points: float = 0.5,
    contract_size: int = 100,
) -> tuple[list, BacktestMetrics]:
    """Run corrected backtest with true equity accounting.

    Fixes:
      1. Peak-to-trough DD using running high-water mark
      2. Next-bar-open entry (entry_bar = i+1, entry_price = open[i+1])
      3. Daily peak tracking for true daily DD
      4. Commission, spread, slippage costs
      5. Conservative same-bar SL/TP (SL assumed hit first)
      6. Daily DD limit = 2%
      7. Gross and net PnL separated

    Returns (list_of_trades, BacktestMetrics)
    """
    equity = starting_equity
    equity_peak = starting_equity       # Running HWM for total DD
    daily_start_equity = starting_equity
    daily_peak = starting_equity        # Daily HWM for true daily DD

    wins = losses = 0
    gross_profit = gross_loss = 0.0
    net_profit = 0.0
    max_total_dd = 0.0
    max_daily_dd = 0.0
    max_consecutive_losses = 0
    consecutive_losses = 0
    daily_dd_breaches = 0
    total_dd_breaches = 0
    total_commission = 0.0
    total_spread_cost = 0.0
    total_slippage_cost = 0.0

    daily_trades = 0
    current_day = None
    cooldown_remaining = 0

    r_multiples_net = []
    r_multiples_gross = []
    trades = []

    closes = df["close"].values
    opens = df["open"].values
    highs = df["high"].values
    lows = df["low"].values
    index = df.index

    alpha_t = params.get("alpha_threshold", 0.50)
    meta_t = params.get("meta_threshold", 0.50)
    risk_pct = params.get("risk_percent", 0.0125)
    sl_mult = params.get("sl_atr_multiplier", 2.0)
    rr_target = params.get("rr_target", 3.0)
    max_holding = params.get("max_holding_bars", 3)
    max_trades_day = params.get("max_trades_per_day", 2)
    cooldown = params.get("cooldown_after_loss", 5)
    spread_filter = params.get("spread_filter", 0.5)

    for i in range(28, len(df) - max_holding - 2):
        # === True total DD (peak-to-trough) ===
        if equity > equity_peak:
            equity_peak = equity
        total_dd = (equity_peak - equity) / equity_peak if equity_peak > 0 else 0
        if total_dd > max_total_dd:
            max_total_dd = total_dd
        if total_dd >= EXT_TOTAL_DD_LIMIT:
            total_dd_breaches += 1
            continue

        # === True daily DD (daily peak-to-trough) ===
        if equity > daily_peak:
            daily_peak = equity
        daily_dd = (daily_peak - equity) / daily_peak if daily_peak > 0 else 0
        if daily_dd > max_daily_dd:
            max_daily_dd = daily_dd
        if daily_dd >= EXT_DAILY_DD_LIMIT:
            daily_dd_breaches += 1
            continue

        # === Daily reset BEFORE evaluating first trade of new day ===
        bar_day = index[i].date()
        if current_day != bar_day:
            current_day = bar_day
            daily_start_equity = equity
            daily_peak = equity     # Reset daily peak
            daily_trades = 0

        if daily_trades >= max_trades_day:
            continue
        if cooldown_remaining > 0:
            cooldown_remaining -= 1
            continue

        # === Signal on CLOSED bar i ===
        alpha_confidence = float(alpha_proba[i])
        if alpha_confidence < alpha_t:
            continue
        direction = "LONG" if alpha_confidence >= 0.5 else "SHORT"
        meta_confidence = float(meta_proba[i])
        if meta_confidence < meta_t:
            continue

        # Spread filter (broker-normalized)
        spread = float(df["spread_usd"].iloc[i]) if "spread_usd" in df.columns else 0.3
        if spread > spread_filter:
            continue

        # CEO governance
        from titan.production.ceo_ai_governance import evaluate_ceo_decision
        ceo = evaluate_ceo_decision(
            regime_state={"detected": True, "regime_value": "MARKET_OPEN", "confidence": alpha_confidence},
            xgb_alpha={"direction": direction, "confidence": alpha_confidence, "pass": True},
            lstm_confidence=None, transformer_regime=None,
            meta_label_quality={"quality_score": meta_confidence, "pass": True},
            broker_state={"broker_pass": True, "spread_pass": True, "slippage_pass": True},
            prop_risk_state={"risk_pass": True, "prop_funded_pass": True, "max_positions_ok": True},
            capital_protection_state={"capital_preservation_active": False, "dd_breach": False},
            model_health_state={"model_health_pass": True, "failed_required": 0},
            geometry_state={"geometry_pass": True, "actual_RR": rr_target, "minimum_RR": 2.0},
        )
        if not ceo.allowed_to_trade:
            continue

        atr = atr_values[i] if atr_values[i] > 0 else 3.0
        sl_distance = atr * sl_mult
        tp_distance = sl_distance * rr_target

        # === Entry at NEXT bar open (no lookahead) ===
        entry_bar = i + 1
        if entry_bar >= len(df):
            continue
        # Direction-aware spread: long entry at ask, short entry at bid
        if direction == "LONG":
            entry_price = opens[entry_bar] + spread  # Ask
        else:
            entry_price = opens[entry_bar] - spread  # Bid

        # Apply slippage
        if direction == "LONG":
            entry_price += slippage_points
        else:
            entry_price -= slippage_points

        if direction == "LONG":
            sl_price = entry_price - sl_distance
            tp_price = entry_price + tp_distance
        else:
            sl_price = entry_price + sl_distance
            tp_price = entry_price - tp_distance

        # === Exit simulation with conservative same-bar resolution ===
        exit_price = entry_price
        exit_reason = "TIMEOUT"
        r_result_gross = 0.0
        holding_bars_actual = 0

        for j in range(1, max_holding + 1):
            bar_idx = entry_bar + j
            if bar_idx >= len(df):
                break
            holding_bars_actual = j
            # Conservative: check SL FIRST (pessimistic)
            if direction == "LONG":
                if lows[bar_idx] <= sl_price:
                    exit_price = sl_price
                    exit_reason = "SL_HIT"
                    r_result_gross = -1.0
                    break
                if highs[bar_idx] >= tp_price:
                    exit_price = tp_price
                    exit_reason = "TP_HIT"
                    r_result_gross = rr_target
                    break
            else:
                if highs[bar_idx] >= sl_price:
                    exit_price = sl_price
                    exit_reason = "SL_HIT"
                    r_result_gross = -1.0
                    break
                if lows[bar_idx] <= tp_price:
                    exit_price = tp_price
                    exit_reason = "TP_HIT"
                    r_result_gross = rr_target
                    break

        if exit_reason == "TIMEOUT":
            last_bar = min(entry_bar + max_holding, len(df) - 1)
            exit_price = closes[last_bar]
            if direction == "LONG":
                r_result_gross = (exit_price - entry_price) / sl_distance
            else:
                r_result_gross = (entry_price - exit_price) / sl_distance

        # === Cost accounting ===
        # Direction-aware exit spread: long exit at bid, short exit at ask
        if direction == "LONG":
            exit_price_net = exit_price - spread  # Exit at bid
        else:
            exit_price_net = exit_price + spread  # Exit at ask

        # Net R result after costs
        if direction == "LONG":
            r_result_net = (exit_price_net - entry_price) / sl_distance
        else:
            r_result_net = (entry_price - exit_price_net) / sl_distance

        risk_amount = equity * risk_pct
        pnl_gross = risk_amount * r_result_gross
        pnl_net = risk_amount * r_result_net
        commission_cost = commission_per_lot * (risk_amount / (sl_distance * contract_size))
        spread_cost = risk_amount * (2 * spread / sl_distance)  # Entry + exit spread
        slippage_cost = risk_amount * (slippage_points / sl_distance)
        pnl_net -= commission_cost

        equity += pnl_net
        daily_trades += 1

        # Update peaks
        if equity > equity_peak:
            equity_peak = equity
        if equity > daily_peak:
            daily_peak = equity

        gross_profit_val = pnl_gross if pnl_gross > 0 else 0
        gross_loss_val = abs(pnl_gross) if pnl_gross < 0 else 0
        gross_profit += gross_profit_val
        gross_loss += gross_loss_val
        net_profit += pnl_net
        total_commission += commission_cost
        total_spread_cost += spread_cost
        total_slippage_cost += slippage_cost

        r_multiples_gross.append(r_result_gross)
        r_multiples_net.append(r_result_net)

        if pnl_net > 0:
            wins += 1
            consecutive_losses = 0
        else:
            losses += 1
            consecutive_losses += 1
            max_consecutive_losses = max(max_consecutive_losses, consecutive_losses)
            cooldown_remaining = cooldown

        trades.append(TradeResult(
            entry_bar=entry_bar, entry_price=round(entry_price, 4),
            exit_price=round(exit_price, 4), exit_reason=exit_reason,
            direction=direction, r_result=round(r_result_net, 4),
            pnl_gross=round(pnl_gross, 2), commission_cost=round(commission_cost, 2),
            spread_cost=round(spread_cost, 2), slippage_cost=round(slippage_cost, 2),
            pnl_net=round(pnl_net, 2),
            timestamp_entry=str(index[entry_bar]),
            timestamp_exit=str(index[min(entry_bar + holding_bars_actual, len(df) - 1)]),
            holding_bars=holding_bars_actual,
        ))

    # Compute metrics
    total_trades = wins + losses
    win_rate = wins / total_trades if total_trades > 0 else 0
    pf_gross = gross_profit / gross_loss if gross_loss > 0 else (999.0 if gross_profit > 0 else 0)
    pf_net = (gross_profit - total_commission - total_spread_cost - total_slippage_cost) / \
             (gross_loss + total_commission + total_spread_cost + total_slippage_cost) \
             if (gross_loss + total_commission + total_spread_cost + total_slippage_cost) > 0 \
             else (999.0 if gross_profit > 0 else 0)
    total_return = (equity - starting_equity) / starting_equity

    if len(r_multiples_net) > 1:
        r_arr = np.array(r_multiples_net)
        mean_r = float(np.mean(r_arr))
        std_r = max(0.001, float(np.std(r_arr)))
        sharpe = (mean_r / std_r) * (252 ** 0.5)
        # Sortino: only downside deviation
        downside = r_arr[r_arr < 0]
        downside_std = max(0.001, float(np.std(downside))) if len(downside) > 0 else std_r
        sortino = (mean_r / downside_std) * (252 ** 0.5)
    else:
        sharpe = 0
        sortino = 0

    calmar = total_return / max(max_total_dd, 0.001) if max_total_dd > 0 else 0
    recovery_factor = total_return / max(max_total_dd, 0.001) if max_total_dd > 0 else 0
    avg_trade = net_profit / total_trades if total_trades > 0 else 0
    expectancy = np.mean(r_multiples_net) if r_multiples_net else 0

    metrics = BacktestMetrics(
        total_trades=total_trades, wins=wins, losses=losses,
        win_rate=round(win_rate, 4),
        gross_profit=round(gross_profit, 2), gross_loss=round(gross_loss, 2),
        net_profit=round(net_profit, 2),
        profit_factor_gross=round(pf_gross, 4) if pf_gross != 999 else 999,
        profit_factor_net=round(pf_net, 4) if pf_net != 999 else 999,
        max_total_dd=round(max_total_dd, 6),
        max_daily_dd=round(max_daily_dd, 6),
        daily_dd_breaches=daily_dd_breaches,
        total_dd_breaches=total_dd_breaches,
        max_consecutive_losses=max_consecutive_losses,
        sharpe=round(sharpe, 4), sortino=round(sortino, 4),
        calmar=round(calmar, 4), recovery_factor=round(recovery_factor, 4),
        avg_trade=round(avg_trade, 2), expectancy=round(float(expectancy), 4),
        total_return=round(total_return, 6),
        total_commission=round(total_commission, 2),
        total_spread_cost=round(total_spread_cost, 2),
        total_slippage_cost=round(total_slippage_cost, 2),
        final_equity=round(equity, 2), starting_equity=starting_equity,
        equity_peak=round(equity_peak, 2),
    )
    return trades, metrics


__all__ = [
    "TradeResult", "BacktestMetrics", "run_corrected_backtest",
    "EXT_DAILY_DD_LIMIT", "EXT_TOTAL_DD_LIMIT",
    "DAILY_CAUTION", "DAILY_RECOVERY", "DAILY_BLOCK_ENTRIES", "DAILY_EMERGENCY",
    "TOTAL_RECOVERY", "TOTAL_CAPITAL_PRESERVATION", "TOTAL_BLOCK_ENTRIES", "TOTAL_EMERGENCY_LOCK",
]
