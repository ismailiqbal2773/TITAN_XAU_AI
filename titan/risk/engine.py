"""
TITAN XAU AI — Risk Engine (Module 4)
Production implementation: 12 risk controls, 4 risk modes,
emergency kill-switch <500ms, MDD enforcement, position management.
"""
from __future__ import annotations

import asyncio
import collections
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import MetaTrader5 as mt5
import numpy as np

logger = logging.getLogger(__name__)


class RiskMode(str, Enum):
    NORMAL = "NORMAL"
    AGGRESSIVE = "AGGRESSIVE"    # Reduced size, tighter stops
    DEFENSIVE = "DEFENSIVE"      # 50% size, widened stops, no new entries
    EMERGENCY = "EMERGENCY"      # Flatten all, halt new entries


class RiskDecision(str, Enum):
    ALLOW = "ALLOW"
    REDUCE_SIZE = "REDUCE_SIZE"
    VETO = "VETO"
    FLATTEN = "FLATTEN"


@dataclass
class RiskState:
    """Current risk state snapshot."""
    equity: float
    balance: float
    margin: float
    margin_level: float       # margin_level = equity / margin * 100
    floating_pnl: float
    open_positions: int
    total_exposure: float     # total lots open
    daily_pnl: float
    max_drawdown_pct: float   # current MDD %
    daily_drawdown_pct: float # today's DD %
    risk_utilization: float   # 0-1, how much of daily risk budget used
    mode: RiskMode
    kill_switch_armed: bool


@dataclass
class RiskSignal:
    """Signal from strategy, to be evaluated by risk engine."""
    symbol: str
    direction: int             # +1 long, -1 short
    proposed_volume: float
    entry_price: float
    stop_loss: float
    take_profit: float
    confidence: float = 0.0
    model_id: str = "ensemble"


@dataclass
class RiskEvaluation:
    """Result of risk evaluation."""
    decision: RiskDecision
    adjusted_volume: float
    reason: str
    controls_checked: int
    controls_failed: list[str] = field(default_factory=list)
    evaluation_time_ms: float = 0.0


class EquityTracker:
    """Tracks equity curve for drawdown calculation."""

    def __init__(self, initial_equity: float):
        self._initial_equity = initial_equity
        self._peak_equity = initial_equity
        self._start_of_day_equity = initial_equity
        self._equity_history: collections.deque = collections.deque(maxlen=100000)
        self._daily_pnl_history: collections.deque = collections.deque(maxlen=365)

    def update(self, equity: float) -> None:
        self._equity_history.append({
            "time": time.time(),
            "equity": equity,
        })
        if equity > self._peak_equity:
            self._peak_equity = equity

    def reset_daily(self, current_equity: float) -> None:
        """Called at start of new trading day."""
        daily_pnl = current_equity - self._start_of_day_equity
        self._daily_pnl_history.append(daily_pnl)
        self._start_of_day_equity = current_equity

    @property
    def max_drawdown_pct(self) -> float:
        """Current drawdown from peak equity."""
        if self._peak_equity <= 0:
            return 0.0
        current = self._equity_history[-1]["equity"] if self._equity_history else self._initial_equity
        dd = (self._peak_equity - current) / self._peak_equity * 100
        return max(dd, 0.0)

    @property
    def daily_drawdown_pct(self) -> float:
        """Today's drawdown from start-of-day equity."""
        if self._start_of_day_equity <= 0:
            return 0.0
        current = self._equity_history[-1]["equity"] if self._equity_history else self._initial_equity
        dd = (self._start_of_day_equity - current) / self._start_of_day_equity * 100
        return max(dd, 0.0)

    @property
    def start_of_day_equity(self) -> float:
        return self._start_of_day_equity

    @property
    def peak_equity(self) -> float:
        return self._peak_equity

    @property
    def initial_equity(self) -> float:
        return self._initial_equity


class RiskEngine:
    """
    Institutional Risk Engine with 12 controls and 4 modes.
    Kill-switch SLA: flatten all positions in <500ms.
    """

    def __init__(self, config: dict, execution_engine=None):
        risk_cfg = config.get("risk", {})
        self._max_daily_dd = risk_cfg.get("max_daily_drawdown", 5.0)
        self._max_overall_dd = risk_cfg.get("max_overall_drawdown", 10.0)
        self._max_per_trade_risk = risk_cfg.get("max_per_trade_risk", 1.0)
        self._max_concurrent = risk_cfg.get("max_concurrent_positions", 5)
        self._kill_switch_latency_ms = risk_cfg.get("kill_switch_latency_ms", 500)
        self._margin_alert = risk_cfg.get("margin_alert_threshold", 200)
        self._correlation_threshold = risk_cfg.get("correlation_threshold", 0.85)

        self._execution = execution_engine
        self._mode = RiskMode.NORMAL
        self._kill_switch_armed = False
        self._veto_count = 0
        self._allow_count = 0
        self._reduce_count = 0
        self._flatten_count = 0

        # Initialize equity tracker
        account_info = mt5.account_info()
        initial = account_info.balance if account_info else 10000.0
        self._equity_tracker = EquityTracker(initial)

    def get_state(self) -> RiskState:
        """Get current risk state snapshot."""
        account = mt5.account_info()
        positions = mt5.positions_get()

        equity = account.equity if account else 0.0
        balance = account.balance if account else 0.0
        margin = account.margin if account else 0.0
        margin_level = account.margin_level if account and margin > 0 else 999.0
        floating = account.profit if account else 0.0
        num_positions = len(positions) if positions else 0
        total_exposure = sum(p.volume for p in positions) if positions else 0.0

        self._equity_tracker.update(equity)

        return RiskState(
            equity=equity,
            balance=balance,
            margin=margin,
            margin_level=margin_level,
            floating_pnl=floating,
            open_positions=num_positions,
            total_exposure=total_exposure,
            daily_pnl=equity - self._equity_tracker.start_of_day_equity,
            max_drawdown_pct=self._equity_tracker.max_drawdown_pct,
            daily_drawdown_pct=self._equity_tracker.daily_drawdown_pct,
            risk_utilization=self._calculate_risk_utilization(equity),
            mode=self._mode,
            kill_switch_armed=self._kill_switch_armed,
        )

    def evaluate(self, signal: RiskSignal) -> RiskEvaluation:
        """
        Evaluate signal against 12 risk controls.
        Returns ALLOW / REDUCE_SIZE / VETO / FLATTEN.
        """
        start = time.perf_counter()
        state = self.get_state()
        failed_controls = []
        adjusted_volume = signal.proposed_volume

        # Control 1: Max daily drawdown
        if state.daily_drawdown_pct >= self._max_daily_dd:
            failed_controls.append("C1_MAX_DAILY_DD")
            self._trigger_emergency()
            return self._veto(state, failed_controls, start)

        # Control 2: Max overall drawdown
        if state.max_drawdown_pct >= self._max_overall_dd:
            failed_controls.append("C2_MAX_OVERALL_DD")
            self._trigger_emergency()
            return self._veto(state, failed_controls, start)

        # Control 3: Per-trade risk cap
        risk_amount = self._calculate_trade_risk(signal, state)
        max_risk = state.equity * (self._max_per_trade_risk / 100)
        if risk_amount > max_risk:
            # Reduce volume to fit risk budget
            if risk_amount > 0:
                adjusted_volume = signal.proposed_volume * (max_risk / risk_amount)
                adjusted_volume = max(adjusted_volume, 0.01)
                failed_controls.append("C3_PER_TRADE_RISK (reduced)")
            else:
                failed_controls.append("C3_PER_TRADE_RISK")
                return self._veto(state, failed_controls, start)

        # Control 4: Max concurrent positions
        if state.open_positions >= self._max_concurrent:
            failed_controls.append("C4_MAX_POSITIONS")
            return self._veto(state, failed_controls, start)

        # Control 5: Margin level alert
        if state.margin_level < self._margin_alert:
            if state.margin_level < 100:
                failed_controls.append("C5_MARGIN_CRITICAL")
                self._trigger_emergency()
                return self._veto(state, failed_controls, start)
            failed_controls.append("C5_MARGIN_ALERT (reduced)")
            adjusted_volume *= 0.5

        # Control 6: Kill switch armed
        if self._kill_switch_armed:
            failed_controls.append("C6_KILL_SWITCH")
            return self._veto(state, failed_controls, start)

        # Control 7: Risk mode check
        if self._mode == RiskMode.EMERGENCY:
            failed_controls.append("C7_EMERGENCY_MODE")
            return self._veto(state, failed_controls, start)
        elif self._mode == RiskMode.DEFENSIVE:
            adjusted_volume *= 0.5
            failed_controls.append("C7_DEFENSIVE_MODE (reduced)")

        # Control 8: Daily risk budget utilization
        if state.risk_utilization > 0.8:
            adjusted_volume *= 0.5
            failed_controls.append("C8_RISK_BUDGET (reduced)")

        # Control 9: Soft daily DD limit (70% of max)
        if state.daily_drawdown_pct >= self._max_daily_dd * 0.7:
            adjusted_volume *= 0.5
            failed_controls.append("C9_SOFT_DD_LIMIT (reduced)")

        # Control 10: Position size sanity (max 5 lots)
        if adjusted_volume > 5.0:
            adjusted_volume = 5.0
            failed_controls.append("C10_MAX_LOT (capped)")

        # Control 11: Negative equity protection
        if state.equity <= 0:
            failed_controls.append("C11_NEGATIVE_EQUITY")
            self._trigger_emergency()
            return self._veto(state, failed_controls, start)

        # Control 12: Spread check (don't enter during news widening)
        tick = mt5.symbol_info_tick(signal.symbol)
        if tick:
            spread = tick.ask - tick.bid
            if spread > 1.0:  # > 1 USD spread = news event
                failed_controls.append("C12_HIGH_SPREAD")
                return self._veto(state, failed_controls, start)

        elapsed_ms = (time.perf_counter() - start) * 1000

        if failed_controls:
            self._reduce_count += 1
            return RiskEvaluation(
                decision=RiskDecision.REDUCE_SIZE,
                adjusted_volume=adjusted_volume,
                reason=f"Reduced: {', '.join(failed_controls)}",
                controls_checked=12,
                controls_failed=failed_controls,
                evaluation_time_ms=elapsed_ms,
            )

        self._allow_count += 1
        return RiskEvaluation(
            decision=RiskDecision.ALLOW,
            adjusted_volume=signal.proposed_volume,
            reason="All 12 controls passed",
            controls_checked=12,
            controls_failed=[],
            evaluation_time_ms=elapsed_ms,
        )

    async def emergency_flatten(self) -> float:
        """
        Emergency kill-switch: flatten ALL positions.
        Must complete in <500ms.
        """
        start = time.perf_counter()
        self._kill_switch_armed = True
        self._mode = RiskMode.EMERGENCY

        logger.critical("KILL-SWITCH TRIGGERED — EMERGENCY FLATTEN")

        if self._execution:
            closed = await self._execution.close_all_positions()
        else:
            # Direct MT5 flatten
            positions = mt5.positions_get()
            closed = 0
            if positions:
                for pos in positions:
                    close_type = (
                        mt5.ORDER_TYPE_SELL if pos.type == mt5.POSITION_TYPE_BUY
                        else mt5.ORDER_TYPE_BUY
                    )
                    tick = mt5.symbol_info_tick(pos.symbol)
                    price = tick.bid if close_type == mt5.ORDER_TYPE_SELL else tick.ask
                    request = {
                        "action": mt5.TRADE_ACTION_DEAL,
                        "symbol": pos.symbol,
                        "volume": pos.volume,
                        "type": close_type,
                        "position": pos.ticket,
                        "price": price,
                        "deviation": 50,
                        "magic": pos.magic,
                        "comment": "TITAN KILL-SWITCH",
                        "type_filling": mt5.ORDER_FILLING_IOC,
                    }
                    result = mt5.order_send(request)
                    if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                        closed += 1

        elapsed_ms = (time.perf_counter() - start) * 1000
        self._flatten_count += 1

        logger.critical(
            f"KILL-SWITCH COMPLETE: {closed} positions flattened "
            f"in {elapsed_ms:.1f}ms (SLA: {self._kill_switch_latency_ms}ms)"
        )

        if elapsed_ms > self._kill_switch_latency_ms:
            logger.error(
                f"KILL-SWITCH SLA VIOLATION: {elapsed_ms:.1f}ms > "
                f"{self._kill_switch_latency_ms}ms"
            )

        return elapsed_ms

    def set_mode(self, mode: RiskMode) -> None:
        """Set risk mode (called by CEO Supervisor)."""
        old_mode = self._mode
        self._mode = mode
        logger.info(f"Risk mode changed: {old_mode.value} → {mode.value}")

        if mode == RiskMode.EMERGENCY:
            self._kill_switch_armed = True

    def reset_kill_switch(self) -> None:
        """Reset kill switch (manual, after review)."""
        self._kill_switch_armed = False
        self._mode = RiskMode.NORMAL
        logger.info("Kill switch reset — risk mode back to NORMAL")

    def _trigger_emergency(self) -> None:
        """Internal trigger for emergency mode."""
        self._kill_switch_armed = True
        self._mode = RiskMode.EMERGENCY

    def _calculate_trade_risk(self, signal: RiskSignal, state: RiskState) -> float:
        """Calculate risk amount for a trade in account currency."""
        if signal.direction > 0:  # Long
            risk_per_unit = signal.entry_price - signal.stop_loss
        else:  # Short
            risk_per_unit = signal.stop_loss - signal.entry_price

        if risk_per_unit <= 0:
            return 0.0

        # For XAUUSD: 1 lot = 100 oz, so risk = risk_per_unit * 100 * volume
        return risk_per_unit * 100 * signal.proposed_volume

    def _calculate_risk_utilization(self, equity: float) -> float:
        """Calculate how much of daily risk budget is used."""
        daily_dd = self._equity_tracker.daily_drawdown_pct
        if self._max_daily_dd <= 0:
            return 0.0
        return min(daily_dd / self._max_daily_dd, 1.0)

    def _veto(
        self, state: RiskState, failed: list[str], start: float
    ) -> RiskEvaluation:
        self._veto_count += 1
        elapsed_ms = (time.perf_counter() - start) * 1000
        return RiskEvaluation(
            decision=RiskDecision.VETO,
            adjusted_volume=0.0,
            reason=f"Vetoed: {', '.join(failed)}",
            controls_checked=12,
            controls_failed=failed,
            evaluation_time_ms=elapsed_ms,
        )

    @property
    def mode(self) -> RiskMode:
        return self._mode

    @property
    def kill_switch_armed(self) -> bool:
        return self._kill_switch_armed

    @property
    def stats(self) -> dict:
        return {
            "allows": self._allow_count,
            "reduces": self._reduce_count,
            "vetoes": self._veto_count,
            "flattens": self._flatten_count,
        }
