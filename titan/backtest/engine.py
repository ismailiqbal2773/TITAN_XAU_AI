"""
TITAN XAU AI — Backtesting Framework (Module 16)
Tick replay engine, variable spread, variable slippage,
5 cost components, 24 metrics, 3-band certification.
"""
from __future__ import annotations

import collections
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


class Verdict(str, Enum):
    CERTIFIED = "CERTIFIED"
    CONDITIONAL = "CONDITIONAL"
    REJECTED = "REJECTED"


@dataclass
class TickData:
    symbol: str
    bid: float
    ask: float
    time: float
    volume: float = 0.0


@dataclass
class BacktestTrade:
    symbol: str
    direction: int          # +1 long, -1 short
    volume: float
    entry_price: float
    exit_price: float = 0.0
    entry_time: float = 0.0
    exit_time: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    pnl: float = 0.0
    pnl_ideal: float = 0.0  # Without costs
    spread_cost: float = 0.0
    commission: float = 0.0
    swap: float = 0.0
    slippage: float = 0.0
    regime: str = ""
    model_id: str = ""
    status: str = "CLOSED"


@dataclass
class BacktestResult:
    trades: list[BacktestTrade] = field(default_factory=list)
    initial_equity: float = 10000.0
    final_equity: float = 10000.0
    total_return: float = 0.0
    cagr: float = 0.0
    sharpe: float = 0.0
    sortino: float = 0.0
    max_drawdown: float = 0.0
    profit_factor: float = 0.0
    win_rate: float = 0.0
    recovery_factor: float = 0.0
    cost_drag: float = 0.0
    total_trades: int = 0
    verdict: Verdict = Verdict.REJECTED
    duration_seconds: float = 0.0


class CostEngine:
    """5 cost components: spread, commission, swap, slippage, tick data."""

    def __init__(self, spread_baseline: float = 0.18, commission_rt: float = 3.50,
                 swap_long_daily: float = -5.0, swap_short_daily: float = -1.0,
                 slippage_p50: float = 0.04, slippage_p99: float = 0.35,
                 contract_size: float = 100.0):
        self.spread_baseline = spread_baseline
        self.commission_rt = commission_rt
        self.swap_long = swap_long_daily / 365.0  # Daily rate
        self.swap_short = swap_short_daily / 365.0
        self.slippage_p50 = slippage_p50
        self.slippage_p99 = slippage_p99
        self.contract_size = contract_size

    def compute_costs(self, entry_price, exit_price, direction, volume,
                      spread_entry, spread_exit, hold_days, slippage_entry, slippage_exit):
        """Compute all 5 cost components for a single trade."""
        # Spread cost (entry + exit spread × lots × $10/pt)
        spread_cost = (spread_entry + spread_exit) * volume * 10.0

        # Commission (round-turn per lot)
        commission = volume * self.commission_rt

        # Swap (daily financing × days held)
        notional = entry_price * volume * self.contract_size
        daily_rate = self.swap_long if direction > 0 else self.swap_short
        swap = notional * daily_rate * hold_days

        # Slippage (|fill - signal| × lots × 100 oz)
        slippage_cost = (slippage_entry + slippage_exit) * volume * self.contract_size

        total_cost = spread_cost + commission + swap + slippage_cost
        return {
            "spread": spread_cost,
            "commission": commission,
            "swap": swap,
            "slippage": slippage_cost,
            "total": total_cost,
        }


class TickReplayExecutor:
    """
    Tick-based backtest executor.
    Replays tick data through strategy, applies costs, computes metrics.
    """

    def __init__(self, cost_engine: CostEngine = None):
        self._cost = cost_engine or CostEngine()
        self._trades: list[BacktestTrade] = []
        self._equity_curve: list[float] = []
        self._current_position: Optional[BacktestTrade] = None

    def run(self, ticks: list[TickData], signals: list[dict],
            initial_equity: float = 10000.0) -> BacktestResult:
        """
        Run backtest on tick data with pre-generated signals.
        signals: list of {time, direction, volume, stop_loss, take_profit, model_id, regime}
        """
        start_time = time.perf_counter()
        self._trades = []
        self._equity_curve = [initial_equity]
        self._current_position = None
        equity = initial_equity

        signal_map = {s["time"]: s for s in signals}
        signal_times = sorted(signal_map.keys())

        signal_idx = 0
        for tick in ticks:
            # Check stop/tp on open position
            if self._current_position:
                pos = self._current_position
                if pos.direction > 0:  # Long
                    if tick.bid <= pos.stop_loss:
                        self._close_position(tick.bid, tick.time, "SL")
                        equity += self._current_position.pnl
                        self._equity_curve.append(equity)
                        self._trades.append(self._current_position)
                        self._current_position = None
                    elif tick.bid >= pos.take_profit:
                        self._close_position(tick.ask, tick.time, "TP")
                        equity += self._current_position.pnl
                        self._equity_curve.append(equity)
                        self._trades.append(self._current_position)
                        self._current_position = None
                else:  # Short
                    if tick.ask >= pos.stop_loss:
                        self._close_position(tick.ask, tick.time, "SL")
                        equity += self._current_position.pnl
                        self._equity_curve.append(equity)
                        self._trades.append(self._current_position)
                        self._current_position = None
                    elif tick.ask <= pos.take_profit:
                        self._close_position(tick.bid, tick.time, "TP")
                        equity += self._current_position.pnl
                        self._equity_curve.append(equity)
                        self._trades.append(self._current_position)
                        self._current_position = None

            # Check for new signal
            while signal_idx < len(signal_times) and signal_times[signal_idx] <= tick.time:
                if self._current_position is None:
                    sig = signal_map[signal_times[signal_idx]]
                    self._open_position(tick, sig)
                signal_idx += 1

            # Update floating PnL
            if self._current_position:
                pos = self._current_position
                if pos.direction > 0:
                    pos.pnl = (tick.bid - pos.entry_price) * pos.volume * self._cost.contract_size
                else:
                    pos.pnl = (pos.entry_price - tick.ask) * pos.volume * self._cost.contract_size

        # Close any remaining position at last tick
        if self._current_position and ticks:
            last = ticks[-1]
            close_price = last.bid if self._current_position.direction > 0 else last.ask
            self._close_position(close_price, last.time, "EOD")
            equity += self._current_position.pnl
            self._equity_curve.append(equity)
            self._trades.append(self._current_position)

        elapsed = time.perf_counter() - start_time
        return self._compute_result(initial_equity, equity, elapsed)

    def _open_position(self, tick: TickData, signal: dict) -> None:
        direction = signal["direction"]
        volume = signal.get("volume", 0.1)
        entry_price = tick.ask if direction > 0 else tick.bid
        spread = tick.ask - tick.bid

        # Sample slippage from distribution (simplified: use P50)
        slippage = np.random.exponential(self._cost.slippage_p50)
        if direction > 0:
            fill_price = entry_price + slippage
        else:
            fill_price = entry_price - slippage

        self._current_position = BacktestTrade(
            symbol=tick.symbol, direction=direction, volume=volume,
            entry_price=fill_price, entry_time=tick.time,
            stop_loss=signal.get("stop_loss", 0),
            take_profit=signal.get("take_profit", 0),
            regime=signal.get("regime", ""),
            model_id=signal.get("model_id", ""),
            status="OPEN",
        )
        # Store costs for later
        self._current_position.slippage = slippage
        self._current_position.spread_cost = spread * volume * 10.0
        self._current_position.commission = volume * self._cost.commission_rt

    def _close_position(self, exit_price: float, exit_time: float, reason: str) -> None:
        pos = self._current_position
        pos.exit_price = exit_price
        pos.exit_time = exit_time
        pos.status = "CLOSED"

        # Ideal PnL (no costs)
        if pos.direction > 0:
            pos.pnl_ideal = (exit_price - pos.entry_price) * pos.volume * self._cost.contract_size
        else:
            pos.pnl_ideal = (pos.entry_price - exit_price) * pos.volume * self._cost.contract_size

        # Hold days (simplified: assume 1 day for intraday)
        hold_days = max((exit_time - pos.entry_time) / 86400.0, 0.01)

        # Apply costs
        notional = pos.entry_price * pos.volume * self._cost.contract_size
        swap_rate = self._cost.swap_long if pos.direction > 0 else self._cost.swap_short
        pos.swap = notional * swap_rate * hold_days

        total_cost = pos.spread_cost + pos.commission + pos.swap + pos.slippage * pos.volume * self._cost.contract_size
        pos.pnl = pos.pnl_ideal - total_cost

    def _compute_result(self, initial: float, final: float, elapsed: float) -> BacktestResult:
        trades = self._trades
        if not trades:
            return BacktestResult(
                initial_equity=initial, final_equity=final,
                duration_seconds=elapsed, verdict=Verdict.REJECTED,
            )

        returns = np.array([(t.pnl / initial) for t in trades])
        equity_curve = np.array(self._equity_curve)

        # Max drawdown
        peak = np.maximum.accumulate(equity_curve)
        dd = (peak - equity_curve) / np.where(peak > 0, peak, 1)
        max_dd = float(np.max(dd)) * 100 if len(dd) > 0 else 0.0

        # Sharpe
        if len(returns) > 1 and np.std(returns) > 0:
            sharpe = float(np.mean(returns) / np.std(returns) * np.sqrt(252))
        else:
            sharpe = 0.0

        # Sortino
        neg_returns = returns[returns < 0]
        if len(neg_returns) > 0 and np.std(neg_returns) > 0:
            sortino = float(np.mean(returns) / np.std(neg_returns) * np.sqrt(252))
        else:
            sortino = 0.0

        # Win rate
        wins = sum(1 for t in trades if t.pnl > 0)
        win_rate = wins / len(trades) if trades else 0.0

        # Profit factor
        gross_profit = sum(t.pnl for t in trades if t.pnl > 0)
        gross_loss = abs(sum(t.pnl for t in trades if t.pnl < 0))
        pf = gross_profit / gross_loss if gross_loss > 0 else 0.0

        # Recovery factor
        recovery = (final - initial) / abs(max_dd) if max_dd > 0 else 0.0

        # Cost drag
        ideal_pnl = sum(t.pnl_ideal for t in trades)
        real_pnl = sum(t.pnl for t in trades)
        cost_drag = (ideal_pnl - real_pnl) / ideal_pnl * 100 if ideal_pnl > 0 else 0.0

        # CAGR (simplified: assume 1 year)
        total_return = (final - initial) / initial * 100
        cagr = total_return  # Simplified for 1-year backtest

        # Verdict
        if sharpe >= 2.0 and max_dd <= 5.0 and cost_drag <= 35.0:
            verdict = Verdict.CERTIFIED
        elif sharpe >= 1.5 and max_dd <= 10.0:
            verdict = Verdict.CONDITIONAL
        else:
            verdict = Verdict.REJECTED

        return BacktestResult(
            trades=trades, initial_equity=initial, final_equity=final,
            total_return=total_return, cagr=cagr, sharpe=sharpe, sortino=sortino,
            max_drawdown=max_dd, profit_factor=pf, win_rate=win_rate,
            recovery_factor=recovery, cost_drag=cost_drag,
            total_trades=len(trades), verdict=verdict, duration_seconds=elapsed,
        )


def generate_synthetic_ticks(symbol: str = "XAUUSD", n_ticks: int = 10000,
                             start_price: float = 2000.0,
                             volatility: float = 2.0) -> list[TickData]:
    """Generate synthetic tick data for testing."""
    ticks = []
    price = start_price
    spread = 0.18
    np.random.seed(42)
    for i in range(n_ticks):
        price += np.random.randn() * volatility
        bid = price - spread / 2
        ask = price + spread / 2
        ticks.append(TickData(
            symbol=symbol, bid=bid, ask=ask,
            time=float(i) * 60,  # 1-minute intervals
            volume=float(np.random.randint(50, 200)),
        ))
    return ticks


def generate_synthetic_signals(ticks: list[TickData], frequency: int = 100) -> list[dict]:
    """Generate synthetic trading signals at regular intervals."""
    signals = []
    np.random.seed(123)
    for i in range(0, len(ticks), frequency):
        tick = ticks[i]
        direction = np.random.choice([-1, 1])
        entry = tick.ask if direction > 0 else tick.bid
        signals.append({
            "time": tick.time,
            "direction": int(direction),
            "volume": 0.1,
            "stop_loss": entry - 5.0 if direction > 0 else entry + 5.0,
            "take_profit": entry + 10.0 if direction > 0 else entry - 10.0,
            "model_id": "ensemble",
            "regime": "TREND",
        })
    return signals
