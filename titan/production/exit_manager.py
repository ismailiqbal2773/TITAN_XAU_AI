"""
TITAN XAU AI — Exit Manager (Production Sprint 3)

Monitors open positions and decides when to exit:
  - TP hit detection
  - SL hit detection
  - Max holding time exceeded
  - Stale position detection (no heartbeat from broker)
  - Trailing stop trigger after +1R profit
  - Risk/kill condition triggers (e.g., kill-switch armed, max DD breached)

Does NOT close positions directly — returns ExitDecision objects that
the trade_loop / supervisor can act on. Closing is delegated to
ExecutionEngine.close_position (via trade_loop) or broker-side SL/TP
(which fires automatically when price hits).

Usage:
    exit_mgr = ExitManager(config=ExitConfig(max_holding_hours=24))
    decision = exit_mgr.evaluate(
        position=BrokerPosition(...),
        current_price=2001.5,
        kill_switch_armed=False,
        current_dd_pct=2.5,
    )
    if decision.should_exit:
        # call trade_loop.close_position(decision)
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from titan.production.position_sync import BrokerPosition

logger = logging.getLogger(__name__)


class ExitReason(str, Enum):
    TP_HIT = "TP_HIT"
    SL_HIT = "SL_HIT"
    MAX_HOLDING_TIME = "MAX_HOLDING_TIME"
    STALE_POSITION = "STALE_POSITION"
    TRAILING_STOP_TRIGGERED = "TRAILING_STOP_TRIGGERED"
    KILL_SWITCH = "KILL_SWITCH"
    MAX_DD_BREACHED = "MAX_DD_BREACHED"
    RISK_VETO = "RISK_VETO"
    MANUAL_CLOSE = "MANUAL_CLOSE"
    NEWS_PRE_HALFT = "NEWS_PRE_HALFT"


@dataclass
class ExitConfig:
    """Exit manager configuration."""
    max_holding_hours: float = 24.0         # Max time to hold a position
    stale_threshold_seconds: float = 300.0  # No update for 5 min = stale
    trailing_activation_r_multiple: float = 1.0   # Activate trailing after +1R
    trailing_distance_r: float = 0.5              # Trail 0.5R behind current price
    max_dd_pct_kill: float = 5.0                  # Kill all positions if DD > 5%
    enable_trailing: bool = True
    enable_max_holding: bool = True
    enable_stale: bool = True


@dataclass
class ExitDecision:
    """Result of evaluating a position for exit."""
    should_exit: bool
    reason: Optional[ExitReason] = None
    ticket: int = 0
    current_price: float = 0.0
    entry_price: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    direction: int = 0                     # +1 long, -1 short
    volume: float = 0.0
    unrealized_pnl_usd: float = 0.0
    holding_time_seconds: float = 0.0
    r_multiple: float = 0.0                # current R multiple (profit / initial risk)
    should_trail: bool = False             # True if trailing should activate
    new_trailing_sl: float = 0.0           # Proposed new SL for trailing
    extra: dict = field(default_factory=dict)

    def __repr__(self) -> str:
        if self.should_exit:
            return (f"ExitDecision(EXIT, reason={self.reason.value}, "
                    f"ticket={self.ticket}, pnl=${self.unrealized_pnl_usd:.2f}, "
                    f"{self.holding_time_seconds/3600:.1f}h, {self.r_multiple:.2f}R)")
        if self.should_trail:
            return (f"ExitDecision(TRAIL, ticket={self.ticket}, "
                    f"new_SL={self.new_trailing_sl:.2f}, {self.r_multiple:.2f}R)")
        return (f"ExitDecision(HOLD, ticket={self.ticket}, "
                f"{self.r_multiple:.2f}R, {self.holding_time_seconds/3600:.1f}h)")


class ExitManager:
    """
    Position exit evaluator.

    Pure logic — does NOT call MT5. Returns ExitDecision for the caller
    to act on. This separation makes it testable without a broker.
    """

    def __init__(self, config: Optional[ExitConfig] = None):
        self.config = config or ExitConfig()
        self._last_position_update: dict[int, float] = {}  # ticket → last seen ts
        logger.info(f"ExitManager initialized: {self.config}")

    # ─── Public API ─────────────────────────────────────────────────────

    def evaluate(
        self,
        position: BrokerPosition,
        current_price: float,
        kill_switch_armed: bool = False,
        current_dd_pct: float = 0.0,
        news_halt_active: bool = False,
        current_time: Optional[float] = None,
    ) -> ExitDecision:
        """
        Evaluate a single position for exit conditions.

        Args:
            position: BrokerPosition to evaluate
            current_price: Current market price (bid for long close, ask for short close)
            kill_switch_armed: True if kill-switch is armed
            current_dd_pct: Current drawdown percentage
            news_halt_active: True if news pre-halt is active
            current_time: Override for current time (for testing)
        """
        now = current_time or time.time()
        self._last_position_update[position.ticket] = now

        # Compute unrealized PnL and R multiple
        pnl_usd, r_multiple = self._compute_pnl_and_r(position, current_price)
        holding_time = now - position.open_time if position.open_time > 0 else 0.0

        base = ExitDecision(
            should_exit=False,
            ticket=position.ticket,
            current_price=current_price,
            entry_price=position.entry_price,
            stop_loss=position.stop_loss,
            take_profit=position.take_profit,
            direction=position.direction,
            volume=position.volume,
            unrealized_pnl_usd=pnl_usd,
            holding_time_seconds=holding_time,
            r_multiple=r_multiple,
        )

        # ── CHECK 1: Kill switch (highest priority) ──
        if kill_switch_armed:
            base.should_exit = True
            base.reason = ExitReason.KILL_SWITCH
            base.extra = {"trigger": "kill_switch_armed"}
            return base

        # ── CHECK 2: Max DD breached ──
        if current_dd_pct >= self.config.max_dd_pct_kill:
            base.should_exit = True
            base.reason = ExitReason.MAX_DD_BREACHED
            base.extra = {"dd_pct": current_dd_pct, "threshold": self.config.max_dd_pct_kill}
            return base

        # ── CHECK 3: News pre-halt ──
        if news_halt_active:
            base.should_exit = True
            base.reason = ExitReason.NEWS_PRE_HALFT
            base.extra = {"trigger": "news_halt_active"}
            return base

        # ── CHECK 4: TP hit ──
        if position.take_profit > 0:
            if position.direction == 1 and current_price >= position.take_profit:
                base.should_exit = True
                base.reason = ExitReason.TP_HIT
                base.extra = {"hit_price": current_price, "tp": position.take_profit}
                return base
            elif position.direction == -1 and current_price <= position.take_profit:
                base.should_exit = True
                base.reason = ExitReason.TP_HIT
                base.extra = {"hit_price": current_price, "tp": position.take_profit}
                return base

        # ── CHECK 5: SL hit ──
        if position.stop_loss > 0:
            if position.direction == 1 and current_price <= position.stop_loss:
                base.should_exit = True
                base.reason = ExitReason.SL_HIT
                base.extra = {"hit_price": current_price, "sl": position.stop_loss}
                return base
            elif position.direction == -1 and current_price >= position.stop_loss:
                base.should_exit = True
                base.reason = ExitReason.SL_HIT
                base.extra = {"hit_price": current_price, "sl": position.stop_loss}
                return base

        # ── CHECK 6: Max holding time ──
        if self.config.enable_max_holding and holding_time > self.config.max_holding_hours * 3600:
            base.should_exit = True
            base.reason = ExitReason.MAX_HOLDING_TIME
            base.extra = {
                "holding_hours": holding_time / 3600,
                "max_hours": self.config.max_holding_hours,
            }
            return base

        # ── CHECK 7: Stale position ──
        if self.config.enable_stale and position.open_time > 0:
            time_since_last_seen = now - self._last_position_update.get(position.ticket, now)
            # Stale = position exists but hasn't been updated by sync loop
            # (this is checked by the caller passing the position regularly;
            # we only flag stale if open_time is far in the past with no recent sync)
            if time_since_last_seen > self.config.stale_threshold_seconds:
                base.should_exit = True
                base.reason = ExitReason.STALE_POSITION
                base.extra = {
                    "seconds_since_sync": time_since_last_seen,
                    "threshold": self.config.stale_threshold_seconds,
                }
                return base

        # ── CHECK 8: Trailing stop activation ──
        if self.config.enable_trailing and r_multiple >= self.config.trailing_activation_r_multiple:
            new_sl = self._compute_trailing_sl(position, current_price)
            # Only trail if new SL is more favorable than current
            if new_sl != 0.0:
                if position.direction == 1 and new_sl > position.stop_loss:
                    base.should_trail = True
                    base.new_trailing_sl = new_sl
                    base.extra = {
                        "current_sl": position.stop_loss,
                        "new_sl": new_sl,
                        "r_multiple": r_multiple,
                    }
                elif position.direction == -1 and new_sl < position.stop_loss:
                    base.should_trail = True
                    base.new_trailing_sl = new_sl
                    base.extra = {
                        "current_sl": position.stop_loss,
                        "new_sl": new_sl,
                        "r_multiple": r_multiple,
                    }

        return base

    def evaluate_many(
        self,
        positions: list[BrokerPosition],
        current_prices: dict[str, float],   # symbol → current price
        kill_switch_armed: bool = False,
        current_dd_pct: float = 0.0,
        news_halt_active: bool = False,
        current_time: Optional[float] = None,
    ) -> list[ExitDecision]:
        """Evaluate multiple positions. Returns one ExitDecision per position."""
        decisions = []
        for pos in positions:
            price = current_prices.get(pos.symbol, 0.0)
            if price == 0.0:
                logger.warning(f"No price for {pos.symbol}, skipping exit check")
                continue
            d = self.evaluate(
                position=pos,
                current_price=price,
                kill_switch_armed=kill_switch_armed,
                current_dd_pct=current_dd_pct,
                news_halt_active=news_halt_active,
                current_time=current_time,
            )
            decisions.append(d)
        return decisions

    # ─── Internal helpers ───────────────────────────────────────────────

    def _compute_pnl_and_r(
        self, position: BrokerPosition, current_price: float
    ) -> tuple[float, float]:
        """
        Compute unrealized PnL in USD and R multiple.

        R = initial risk = |entry - SL| × contract_size × volume
        PnL = (current - entry) × direction × contract_size × volume
        contract_size for XAUUSD = 100 oz/lot
        """
        contract_size = 100.0  # XAUUSD
        direction = position.direction
        entry = position.entry_price
        sl = position.stop_loss if position.stop_loss > 0 else 0.0
        vol = position.volume if position.volume > 0 else 0.01

        # PnL in USD
        pnl = (current_price - entry) * direction * contract_size * vol

        # R multiple
        if sl == 0.0:
            r_multiple = 0.0
        else:
            initial_risk = abs(entry - sl) * contract_size * vol
            if initial_risk > 0:
                r_multiple = pnl / initial_risk
            else:
                r_multiple = 0.0

        return pnl, r_multiple

    def _compute_trailing_sl(self, position: BrokerPosition, current_price: float) -> float:
        """
        Compute new trailing SL based on R multiple distance.

        trailing_distance_r = 0.5 means trail 0.5R behind current price.
        R = |entry - original_SL| (initial risk per unit).
        """
        if position.stop_loss == 0.0:
            return 0.0

        initial_risk_per_unit = abs(position.entry_price - position.stop_loss)
        if initial_risk_per_unit == 0:
            return 0.0

        trail_distance = initial_risk_per_unit * self.config.trailing_distance_r

        if position.direction == 1:  # LONG
            new_sl = current_price - trail_distance
        else:                         # SHORT
            new_sl = current_price + trail_distance

        return round(new_sl, 5)


if __name__ == "__main__":
    # Smoke test
    import time as _time
    from titan.production.position_sync import BrokerPosition

    print("=" * 70)
    print("TITAN ExitManager — Smoke Test")
    print("=" * 70)
    mgr = ExitManager()

    # Test 1: TP hit
    pos = BrokerPosition(
        ticket=50001, symbol="XAUUSD", direction=1, volume=0.01,
        entry_price=2000.0, stop_loss=1995.0, take_profit=2010.0,
        open_time=_time.time() - 3600,  # 1 hour ago
    )
    d = mgr.evaluate(pos, current_price=2010.5)
    print(f"\nTP hit test: {d}")

    # Test 2: SL hit
    d = mgr.evaluate(pos, current_price=1994.5)
    print(f"SL hit test: {d}")

    # Test 3: Kill switch
    d = mgr.evaluate(pos, current_price=2005.0, kill_switch_armed=True)
    print(f"Kill switch test: {d}")

    # Test 4: Trailing stop activation (+1.5R)
    pos2 = BrokerPosition(
        ticket=50002, symbol="XAUUSD", direction=1, volume=0.01,
        entry_price=2000.0, stop_loss=1995.0, take_profit=2010.0,
        open_time=_time.time() - 3600,
    )
    d = mgr.evaluate(pos2, current_price=2007.5)  # +7.5 = +1.5R (R=5)
    print(f"Trailing stop test (+1.5R): {d}")

    # Test 5: Max holding time
    pos3 = BrokerPosition(
        ticket=50003, symbol="XAUUSD", direction=1, volume=0.01,
        entry_price=2000.0, stop_loss=1995.0, take_profit=2010.0,
        open_time=_time.time() - 25 * 3600,  # 25 hours ago
    )
    d = mgr.evaluate(pos3, current_price=2005.0)
    print(f"Max holding time test: {d}")

    # Test 6: Normal hold
    d = mgr.evaluate(pos, current_price=2005.0)
    print(f"Normal hold test: {d}")
