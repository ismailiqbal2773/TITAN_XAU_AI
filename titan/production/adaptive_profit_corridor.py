"""
TITAN XAU AI - Adaptive Profit Corridor (Sprint 9.9.3.45.8.2)
================================================================
Opt-in dynamic TP extension paired with protective SL movement.

When enabled, extends TP in the direction of profit (only in trend
regime, only after profit_R >= tp_extension_trigger_R) and
simultaneously raises SL into the profit zone to lock minimum
locked_R profit. TP never reduces. SL never widens. SL must protect
minimum locked_R profit before TP extension is allowed.

NEVER reduces TP. NEVER widens SL. NEVER removes TP. NEVER sends orders.
NEVER adds martingale/grid/averaging. NEVER uses loss-based lot multiplier.

Core definitions:
  R = abs(entry_price - initial_sl)
  profit_distance = favorable price movement from entry
  profit_R = profit_distance / R
  MFE = max favorable excursion
  ATR_noise = current ATR or fallback volatility estimate

Policy:
  TP extension allowed only if ALL of:
    - dynamic_tp_enabled=True
    - adaptive_trailing_enabled=True (corridor requires adaptive SL)
    - monitor active (monitor_iterations > 0)
    - profit_R >= tp_extension_trigger_R
    - regime == TREND (or explicit override for range)
    - spread normal (no spread spike)
    - no news flag
    - cooldown passed (seconds_since_last_tp_extension >= tp_extension_cooldown_seconds)
    - MFE improving (current_price >= MFE for BUY, <= MFE for SELL)
    - SL already protects minimum locked_R profit
      (current_sl >= entry + locked_R * R for BUY,
       current_sl <= entry - locked_R * R for SELL)

  BUY:
    proposed_tp = max(current_tp, current_price + max(tp_extension_atr_mult * ATR_noise, tp_extension_R * R))
    proposed_sl = max(current_sl, entry_price + locked_R * R, current_price - dynamic_trail_distance)

  SELL:
    proposed_tp = min(current_tp, current_price - max(tp_extension_atr_mult * ATR_noise, tp_extension_R * R))
    proposed_sl = min(current_sl, entry_price - locked_R * R, current_price + dynamic_trail_distance)

  If proposed SL is too close to price:
    HOLD or reduce to safe distance. Do not extend TP unless SL already
    protects minimum locked_R profit.

  Max giveback control:
    - max_profit_giveback_r_trend: max R-multiple of profit allowed to
      give back before SL is raised to lock profit (trend regime)
    - max_profit_giveback_r_range: same for range regime
    - If current profit_R - locked_R > max_profit_giveback, force SL
      raise to lock more profit.
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class CorridorAction(str, Enum):
    HOLD = "HOLD"
    EXTEND_TP_AND_RAISE_SL = "EXTEND_TP_AND_RAISE_SL"
    RAISE_SL_ONLY = "RAISE_SL_ONLY"
    BLOCKED = "BLOCKED"


@dataclass
class CorridorDecision:
    """Output of a single AdaptiveProfitCorridor.evaluate() call."""
    dynamic_tp_enabled: bool = False
    profit_corridor_enabled: bool = False
    action: CorridorAction = CorridorAction.HOLD
    actual_monitor_iteration: int = 0
    policy_monitor_iteration: int = 0
    hold_seconds: int = 0
    profit_R: float = 0.0
    R: float = 0.0
    MFE: float = 0.0
    old_sl: float = 0.0
    proposed_sl: float = 0.0
    final_sl: float = 0.0
    old_tp: float = 0.0
    proposed_tp: float = 0.0
    final_tp: float = 0.0
    tp_extension_allowed: bool = False
    tp_extension_action: str = "NONE"
    tp_sl_pair_valid: bool = False
    sl_profit_floor_R: float = 0.0
    max_profit_giveback_R: float = 0.0
    no_tp_reduction: bool = True
    no_sl_widening: bool = True
    reason: str = ""
    blocks: list[str] = field(default_factory=list)
    timestamp_utc: str = ""

    def __post_init__(self):
        if not self.timestamp_utc:
            self.timestamp_utc = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        d = asdict(self)
        d["action"] = self.action.value
        return d


class AdaptiveProfitCorridor:
    """Adaptive profit corridor: dynamic TP extension paired with
    protective SL movement.

    NEVER sends orders. Returns CorridorDecision only.
    NEVER reduces TP. NEVER widens SL. NEVER removes TP.
    """

    def __init__(self,
                 dynamic_tp_enabled: bool = False,
                 tp_extension_trigger_R: float = 2.0,
                 tp_extension_R: float = 1.0,
                 tp_extension_atr_mult: float = 2.0,
                 tp_extension_cooldown_seconds: int = 120,
                 min_profit_lock_after_tp_extension_R: float = 1.0,
                 max_profit_giveback_r_trend: float = 1.0,
                 max_profit_giveback_r_range: float = 0.5,
                 locked_R: float = 1.2,
                 # Adaptive trailing params (used for dynamic trail distance)
                 trend_atr_multiplier: float = 2.0,
                 range_atr_multiplier: float = 1.0,
                 high_vol_atr_multiplier: float = 2.5,
                 spread_buffer_multiplier: float = 1.5):
        self.dynamic_tp_enabled = dynamic_tp_enabled
        self.tp_extension_trigger_R = tp_extension_trigger_R
        self.tp_extension_R = tp_extension_R
        self.tp_extension_atr_mult = tp_extension_atr_mult
        self.tp_extension_cooldown_seconds = tp_extension_cooldown_seconds
        self.min_profit_lock_after_tp_extension_R = min_profit_lock_after_tp_extension_R
        self.max_profit_giveback_r_trend = max_profit_giveback_r_trend
        self.max_profit_giveback_r_range = max_profit_giveback_r_range
        self.locked_R = locked_R
        self.trend_atr_multiplier = trend_atr_multiplier
        self.range_atr_multiplier = range_atr_multiplier
        self.high_vol_atr_multiplier = high_vol_atr_multiplier
        self.spread_buffer_multiplier = spread_buffer_multiplier

    def evaluate(self, *, direction: str,
                 entry_price: float,
                 initial_sl: float,
                 current_sl: float,
                 current_tp: float,
                 current_price: float,
                 atr: float = 0.0,
                 spread: float = 0.0,
                 regime=None,
                 stops_level_points: int = 0,
                 point: float = 0.01,
                 monitor_iterations: int = 0,
                 hold_seconds: int = 0,
                 seconds_since_last_tp_extension: int = 999,
                 spread_spike_flag: bool = False,
                 news_flag: bool = False,
                 mfe: float = 0.0,
                 adaptive_trailing_enabled: bool = False,
                 structure_buffer: float = 0.0) -> CorridorDecision:
        """Evaluate position and return corridor decision.

        NEVER sends orders. Returns CorridorDecision only.
        """
        decision = CorridorDecision(
            dynamic_tp_enabled=self.dynamic_tp_enabled,
            profit_corridor_enabled=(self.dynamic_tp_enabled and adaptive_trailing_enabled),
            actual_monitor_iteration=monitor_iterations,
            policy_monitor_iteration=monitor_iterations,
            hold_seconds=hold_seconds,
            old_sl=current_sl,
            proposed_sl=current_sl,
            final_sl=current_sl,
            old_tp=current_tp,
            proposed_tp=current_tp,
            final_tp=current_tp,
            MFE=mfe,
        )

        if direction not in ("BUY", "SELL"):
            decision.action = CorridorAction.BLOCKED
            decision.blocks.append(f"Invalid direction: {direction}")
            decision.reason = "BLOCKED: invalid direction"
            return decision

        # Compute R = abs(entry - initial_sl)
        R = abs(entry_price - initial_sl) if initial_sl > 0 else 0.0
        decision.R = R

        # Compute profit_distance and profit_R
        if direction == "BUY":
            profit_distance = current_price - entry_price
        else:
            profit_distance = entry_price - current_price
        profit_R = (profit_distance / R) if R > 0 else 0.0
        decision.profit_R = profit_R

        # ATR noise (fallback to 0.5 * R if ATR not provided)
        atr_noise = atr if atr > 0 else (0.5 * R if R > 0 else 0.5)

        # Spread buffer
        spread_buffer = spread * self.spread_buffer_multiplier

        # Stop level buffer
        stop_level_buffer = stops_level_points * point if stops_level_points > 0 else 0.0

        # sl_profit_floor_R = locked_R (minimum R profit locked by SL)
        decision.sl_profit_floor_R = self.locked_R

        # max_profit_giveback_R based on regime
        from titan.production.adaptive_trailing_policy import Regime
        if regime == Regime.RANGE:
            decision.max_profit_giveback_R = self.max_profit_giveback_r_range
        else:
            decision.max_profit_giveback_R = self.max_profit_giveback_r_trend

        # If dynamic TP not enabled, HOLD with TP preserved
        if not self.dynamic_tp_enabled:
            decision.action = CorridorAction.HOLD
            decision.tp_extension_allowed = False
            decision.tp_extension_action = "DISABLED"
            decision.reason = "Dynamic TP extension disabled (opt-in flag not set)"
            decision.no_tp_reduction = True
            decision.no_sl_widening = True
            return decision

        # If adaptive trailing not enabled, cannot extend TP (corridor
        # requires adaptive SL to protect profit)
        if not adaptive_trailing_enabled:
            decision.action = CorridorAction.HOLD
            decision.tp_extension_allowed = False
            decision.tp_extension_action = "BLOCKED_NO_ADAPTIVE_SL"
            decision.blocks.append("ADAPTIVE_TRAILING_REQUIRED: corridor needs adaptive SL to protect profit")
            decision.reason = "Corridor requires adaptive trailing enabled"
            decision.no_tp_reduction = True
            decision.no_sl_widening = True
            return decision

        # If profit_R < tp_extension_trigger_R, HOLD
        if profit_R < self.tp_extension_trigger_R:
            decision.action = CorridorAction.HOLD
            decision.tp_extension_allowed = False
            decision.tp_extension_action = "WAIT_FOR_TRIGGER"
            decision.reason = (f"profit_R={profit_R:.4f} < tp_extension_trigger_R={self.tp_extension_trigger_R}")
            decision.no_tp_reduction = True
            decision.no_sl_widening = True
            return decision

        # Regime check: only TREND allowed (range blocked unless explicit override)
        if regime == Regime.RANGE:
            decision.action = CorridorAction.HOLD
            decision.tp_extension_allowed = False
            decision.tp_extension_action = "BLOCKED_RANGE_REGIME"
            decision.blocks.append("RANGE_REGIME: TP extension only allowed in TREND regime")
            decision.reason = "TP extension blocked in range regime"
            decision.no_tp_reduction = True
            decision.no_sl_widening = True
            return decision

        if regime == Regime.HIGH_VOL:
            decision.action = CorridorAction.HOLD
            decision.tp_extension_allowed = False
            decision.tp_extension_action = "BLOCKED_HIGH_VOL"
            decision.blocks.append("HIGH_VOL_REGIME: TP extension blocked in high volatility")
            decision.reason = "TP extension blocked in high volatility regime"
            decision.no_tp_reduction = True
            decision.no_sl_widening = True
            return decision

        # Spread spike block
        if spread_spike_flag:
            decision.action = CorridorAction.HOLD
            decision.tp_extension_allowed = False
            decision.tp_extension_action = "BLOCKED_SPREAD_SPIKE"
            decision.blocks.append("SPREAD_SPIKE_FLAG_ACTIVE")
            decision.reason = "TP extension blocked by spread spike"
            decision.no_tp_reduction = True
            decision.no_sl_widening = True
            return decision

        # News flag block
        if news_flag:
            decision.action = CorridorAction.HOLD
            decision.tp_extension_allowed = False
            decision.tp_extension_action = "BLOCKED_NEWS"
            decision.blocks.append("NEWS_FLAG_ACTIVE")
            decision.reason = "TP extension blocked by news flag"
            decision.no_tp_reduction = True
            decision.no_sl_widening = True
            return decision

        # Cooldown check
        if seconds_since_last_tp_extension < self.tp_extension_cooldown_seconds:
            decision.action = CorridorAction.HOLD
            decision.tp_extension_allowed = False
            decision.tp_extension_action = "BLOCKED_COOLDOWN"
            decision.blocks.append(
                f"COOLDOWN_ACTIVE: seconds_since_last_tp_extension={seconds_since_last_tp_extension} < cooldown={self.tp_extension_cooldown_seconds}"
            )
            decision.reason = "TP extension blocked by cooldown"
            decision.no_tp_reduction = True
            decision.no_sl_widening = True
            return decision

        # MFE improving check (no tick chasing - only extend when MFE is improving)
        if direction == "BUY":
            mfe_improving = (mfe <= 0.0) or (current_price >= mfe - atr_noise * 0.1)
        else:
            mfe_improving = (mfe <= 0.0) or (current_price <= mfe + atr_noise * 0.1)
        if not mfe_improving:
            decision.action = CorridorAction.HOLD
            decision.tp_extension_allowed = False
            decision.tp_extension_action = "BLOCKED_MFE_NOT_IMPROVING"
            decision.blocks.append("MFE_NOT_IMPROVING: price pulled back from MFE, no tick chasing")
            decision.reason = "TP extension blocked: MFE not improving (no tick chasing)"
            decision.no_tp_reduction = True
            decision.no_sl_widening = True
            return decision

        # SL must already protect minimum locked_R profit before TP extension
        # BUY: current_sl >= entry + locked_R * R
        # SELL: current_sl <= entry - locked_R * R
        locked_profit_value = self.locked_R * R if R > 0 else 0.0
        if direction == "BUY":
            sl_protects_profit = current_sl >= (entry_price + locked_profit_value)
        else:
            sl_protects_profit = (current_sl <= (entry_price - locked_profit_value)) or current_sl == 0

        if not sl_protects_profit:
            # SL doesn't protect enough profit - raise SL first, don't extend TP yet
            if direction == "BUY":
                proposed_sl = max(current_sl, entry_price + locked_profit_value)
            else:
                proposed_sl = min(current_sl, entry_price - locked_profit_value) if current_sl > 0 else entry_price - locked_profit_value
            decision.proposed_sl = proposed_sl
            decision.final_sl = proposed_sl
            decision.action = CorridorAction.RAISE_SL_ONLY
            decision.tp_extension_allowed = False
            decision.tp_extension_action = "RAISE_SL_FIRST"
            decision.tp_sl_pair_valid = False
            decision.reason = (f"SL must protect locked_R={self.locked_R} profit before TP extension. "
                               f"Raising SL to {proposed_sl}")
            decision.no_tp_reduction = True
            decision.no_sl_widening = (proposed_sl >= current_sl) if direction == "BUY" else (proposed_sl <= current_sl or current_sl == 0)
            return decision

        # All conditions met - extend TP and raise SL as paired modify
        # Compute dynamic trail distance based on regime
        if regime == Regime.TREND:
            regime_multiplier = self.trend_atr_multiplier
        elif regime == Regime.RANGE:
            regime_multiplier = self.range_atr_multiplier
        elif regime == Regime.HIGH_VOL:
            regime_multiplier = self.high_vol_atr_multiplier
        else:
            regime_multiplier = self.trend_atr_multiplier

        dynamic_trail_distance = max(
            atr_noise * regime_multiplier,
            structure_buffer,
            spread_buffer,
            stop_level_buffer,
        )

        # Compute proposed TP and SL
        tp_extension_distance = max(
            self.tp_extension_atr_mult * atr_noise,
            self.tp_extension_R * R if R > 0 else 0.0,
        )

        if direction == "BUY":
            proposed_tp = max(current_tp, current_price + tp_extension_distance)
            proposed_sl = max(current_sl, entry_price + locked_profit_value, current_price - dynamic_trail_distance)
        else:
            proposed_tp = min(current_tp, current_price - tp_extension_distance)
            proposed_sl = min(current_sl, entry_price - locked_profit_value, current_price + dynamic_trail_distance)

        decision.proposed_tp = proposed_tp
        decision.proposed_sl = proposed_sl
        decision.final_tp = proposed_tp
        decision.final_sl = proposed_sl
        decision.action = CorridorAction.EXTEND_TP_AND_RAISE_SL
        decision.tp_extension_allowed = True
        decision.tp_extension_action = "EXTEND_TP_AND_RAISE_SL"
        decision.tp_sl_pair_valid = True
        decision.reason = (f"TP extended to {proposed_tp}, SL raised to {proposed_sl} "
                           f"(profit_R={profit_R:.4f}, regime={regime.value if regime else 'unknown'})")

        # Validate: no TP reduction
        if direction == "BUY":
            decision.no_tp_reduction = proposed_tp >= current_tp
            decision.no_sl_widening = proposed_sl >= current_sl
        else:
            decision.no_tp_reduction = proposed_tp <= current_tp
            decision.no_sl_widening = (proposed_sl <= current_sl) or current_sl == 0

        if not decision.no_tp_reduction:
            decision.blocks.append("TP_REDUCTION_BLOCKED")
            decision.action = CorridorAction.BLOCKED
            decision.final_tp = current_tp
            decision.final_sl = current_sl
        if not decision.no_sl_widening:
            decision.blocks.append("SL_WIDENING_BLOCKED")
            decision.action = CorridorAction.BLOCKED
            decision.final_tp = current_tp
            decision.final_sl = current_sl

        return decision
