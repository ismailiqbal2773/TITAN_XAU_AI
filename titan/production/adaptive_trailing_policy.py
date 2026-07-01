"""
TITAN XAU AI - Adaptive Trailing Policy (Sprint 9.9.3.45.8)
=============================================================
Mathematically controlled adaptive trailing policy using R-multiple,
ATR/noise buffer, regime type, spread/stop-level buffers, and
hysteresis/cooldown.

NEVER widens SL. NEVER removes TP. NEVER sends orders directly.

Core definitions:
  R = abs(entry_price - initial_sl)
  profit_distance = favorable price movement from entry
  profit_R = profit_distance / R
  ATR_noise = current ATR or fallback volatility estimate
  MFE = max favorable excursion
  MAE = max adverse excursion
  spread_buffer = current spread * configurable multiplier
  stop_level_buffer = broker stop/freeze minimum
  structure_buffer = recent swing high/low buffer if available

Policy phases:
  Phase 0 - Initial Protection:
    No SL movement immediately after entry.
    Minimum hold time before any SL move.
    Minimum monitor iterations before any SL move.

  Phase 1 - Noise Filter:
    If profit_R < breakeven_trigger_R, action=HOLD.
    If profit_distance < max(ATR_noise * atr_noise_multiplier,
                              spread_buffer, stop_level_buffer),
       action=HOLD.

  Phase 2 - Soft Breakeven:
    Only after profit_R >= breakeven_trigger_R.
    Move SL to entry + small positive buffer only if:
      - current price is beyond noise threshold
      - spread normal
      - no high-impact news/spread spike flag
      - favorable-only check passes

  Phase 3 - Adaptive Trail:
    Only after profit_R >= trailing_trigger_R.
    New SL for BUY:
      current_price - max(ATR_noise * regime_multiplier,
                           structure_buffer, spread_buffer,
                           stop_level_buffer)
    New SL for SELL:
      current_price + max(ATR_noise * regime_multiplier,
                          structure_buffer, spread_buffer,
                          stop_level_buffer)
    Trend regime multiplier: 1.5 to 2.5 ATR
    Range regime multiplier: 0.8 to 1.2 ATR
    High-volatility multiplier: 2.0 to 3.0 ATR or HOLD until higher R

  Phase 4 - Profit Lock:
    Only after profit_R >= profit_lock_trigger_R.
    Lock part of open profit but leave room:
      BUY SL >= entry + locked_R * R
      SELL SL <= entry - locked_R * R

Anti-whipsaw controls:
  - minimum_profit_R_before_any_sl_move
  - minimum_hold_seconds_before_trailing
  - minimum_monitor_iterations_before_trailing
  - sl_update_cooldown_seconds
  - minimum_sl_step_distance
  - ATR/noise buffer
  - spread spike block
  - broker stop/freeze-level buffer
  - hysteresis: do not modify SL unless new SL improves current SL by
    at least minimum_sl_step_distance
  - no repeated modify on every tick
  - no SL widening
  - TP preserved
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


# Policy modes
class PolicyMode(str, Enum):
    CONSERVATIVE = "conservative"
    BALANCED = "balanced"
    AGGRESSIVE = "aggressive"
    BALANCED_CONSERVATIVE = "balanced_conservative"  # default for proof/demo


# Regime types
class Regime(str, Enum):
    TREND = "trend"
    RANGE = "range"
    HIGH_VOL = "high_vol"
    UNKNOWN = "unknown"


# SL actions (mirrors SLAction from demo_micro_position_manager)
class PolicyAction(str, Enum):
    HOLD = "HOLD"
    MOVE_TO_BREAKEVEN = "MOVE_TO_BREAKEVEN"
    TRAIL = "TRAIL"
    PROFIT_LOCK = "PROFIT_LOCK"
    BLOCKED = "BLOCKED"


# Phase labels
PHASE_0_INITIAL_PROTECTION = "PHASE_0_INITIAL_PROTECTION"
PHASE_1_NOISE_FILTER = "PHASE_1_NOISE_FILTER"
PHASE_2_SOFT_BREAKEVEN = "PHASE_2_SOFT_BREAKEVEN"
PHASE_3_ADAPTIVE_TRAIL = "PHASE_3_ADAPTIVE_TRAIL"
PHASE_4_PROFIT_LOCK = "PHASE_4_PROFIT_LOCK"


# Mode presets (defaults). All values are tunable.
MODE_PRESETS = {
    PolicyMode.CONSERVATIVE: {
        "breakeven_trigger_R": 1.0,
        "trailing_trigger_R": 2.0,
        "profit_lock_trigger_R": 3.0,
        "breakeven_buffer_R": 0.1,
        "locked_R": 1.0,
        "min_hold_seconds": 120,
        "min_monitor_iterations": 5,
        "cooldown_seconds": 90,
        "minimum_sl_step_distance_atr_multiple": 0.3,
        "atr_noise_multiplier": 1.0,
        "trend_atr_multiplier": 2.5,
        "range_atr_multiplier": 1.2,
        "high_vol_atr_multiplier": 3.0,
        "high_vol_hold_until_R": 2.5,
        "spread_spike_threshold_atr": 0.5,
        "spread_buffer_multiplier": 1.5,
    },
    PolicyMode.BALANCED: {
        "breakeven_trigger_R": 1.0,
        "trailing_trigger_R": 1.75,
        "profit_lock_trigger_R": 3.0,
        "breakeven_buffer_R": 0.1,
        "locked_R": 1.2,
        "min_hold_seconds": 60,
        "min_monitor_iterations": 3,
        "cooldown_seconds": 60,
        "minimum_sl_step_distance_atr_multiple": 0.25,
        "atr_noise_multiplier": 1.0,
        "trend_atr_multiplier": 2.0,
        "range_atr_multiplier": 1.0,
        "high_vol_atr_multiplier": 2.5,
        "high_vol_hold_until_R": 2.0,
        "spread_spike_threshold_atr": 0.5,
        "spread_buffer_multiplier": 1.5,
    },
    PolicyMode.AGGRESSIVE: {
        "breakeven_trigger_R": 0.75,
        "trailing_trigger_R": 1.5,
        "profit_lock_trigger_R": 2.5,
        "breakeven_buffer_R": 0.05,
        "locked_R": 1.5,
        "min_hold_seconds": 30,
        "min_monitor_iterations": 2,
        "cooldown_seconds": 30,
        "minimum_sl_step_distance_atr_multiple": 0.2,
        "atr_noise_multiplier": 0.8,
        "trend_atr_multiplier": 1.5,
        "range_atr_multiplier": 0.8,
        "high_vol_atr_multiplier": 2.0,
        "high_vol_hold_until_R": 1.5,
        "spread_spike_threshold_atr": 0.6,
        "spread_buffer_multiplier": 1.2,
    },
    # Default for proof/demo: balanced thresholds with conservative hold/cooldown
    PolicyMode.BALANCED_CONSERVATIVE: {
        "breakeven_trigger_R": 1.0,
        "trailing_trigger_R": 1.75,
        "profit_lock_trigger_R": 3.0,
        "breakeven_buffer_R": 0.1,
        "locked_R": 1.2,
        "min_hold_seconds": 60,
        "min_monitor_iterations": 3,
        "cooldown_seconds": 60,
        "minimum_sl_step_distance_atr_multiple": 0.25,
        "atr_noise_multiplier": 1.0,
        "trend_atr_multiplier": 2.0,
        "range_atr_multiplier": 1.0,
        "high_vol_atr_multiplier": 2.5,
        "high_vol_hold_until_R": 2.0,
        "spread_spike_threshold_atr": 0.5,
        "spread_buffer_multiplier": 1.5,
    },
}


@dataclass
class PolicyDecision:
    """Output of a single AdaptiveTrailingPolicy.evaluate() call.

    Every monitor decision must populate all fields for auditability.
    """
    phase: str = PHASE_0_INITIAL_PROTECTION
    action: PolicyAction = PolicyAction.HOLD
    profit_distance: float = 0.0
    profit_R: float = 0.0
    R: float = 0.0
    ATR_noise: float = 0.0
    regime: Regime = Regime.UNKNOWN
    spread_buffer: float = 0.0
    stop_level_buffer: float = 0.0
    structure_buffer: float = 0.0
    trailing_distance: float = 0.0
    old_sl: float = 0.0
    proposed_sl: float = 0.0
    final_sl: float = 0.0
    tp_preserved: bool = True
    favorable: bool = True
    no_widening: bool = True
    reason: str = ""
    anti_whipsaw_blocks: list[str] = field(default_factory=list)
    timestamp_utc: str = ""

    def __post_init__(self):
        if not self.timestamp_utc:
            self.timestamp_utc = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        d = asdict(self)
        d["action"] = self.action.value
        d["regime"] = self.regime.value
        return d


class AdaptiveTrailingPolicy:
    """Adaptive trailing policy with anti-whipsaw controls.

    NEVER sends orders. Returns PolicyDecision only.
    Favorable-only: BUY SL only moves up, SELL SL only moves down.
    NEVER widens SL. NEVER removes TP.
    """

    def __init__(self, mode: PolicyMode = PolicyMode.BALANCED_CONSERVATIVE,
                 **overrides):
        self.mode = mode
        preset = dict(MODE_PRESETS.get(mode, MODE_PRESETS[PolicyMode.BALANCED_CONSERVATIVE]))
        # Apply overrides
        for k, v in overrides.items():
            if k in preset:
                preset[k] = v
        for k, v in preset.items():
            setattr(self, k, v)

    def evaluate(self, *, direction: str,
                 entry_price: float,
                 initial_sl: float,
                 current_price: float,
                 current_sl: float,
                 current_tp: float,
                 atr: float = 0.0,
                 spread: float = 0.0,
                 stops_level_points: int = 0,
                 point: float = 0.01,
                 regime: Regime = Regime.UNKNOWN,
                 structure_buffer: float = 0.0,
                 hold_seconds: int = 0,
                 monitor_iterations: int = 0,
                 seconds_since_last_modify: int = 0,
                 spread_spike_flag: bool = False,
                 news_flag: bool = False,
                 mfe: float = 0.0,
                 mae: float = 0.0) -> PolicyDecision:
        """Evaluate position and return policy decision.

        NEVER sends orders. Returns PolicyDecision only.
        """
        decision = PolicyDecision(
            old_sl=current_sl,
            proposed_sl=current_sl,
            final_sl=current_sl,
            regime=regime,
            structure_buffer=structure_buffer,
        )

        if direction not in ("BUY", "SELL"):
            decision.action = PolicyAction.BLOCKED
            decision.anti_whipsaw_blocks.append(f"Invalid direction: {direction}")
            decision.reason = f"BLOCKED: invalid direction"
            return decision

        # Compute R = abs(entry - initial_sl)
        R = abs(entry_price - initial_sl) if initial_sl > 0 else 0.0
        decision.R = R

        # Compute profit_distance and profit_R
        if direction == "BUY":
            profit_distance = current_price - entry_price
        else:
            profit_distance = entry_price - current_price
        decision.profit_distance = profit_distance
        profit_R = (profit_distance / R) if R > 0 else 0.0
        decision.profit_R = profit_R

        # ATR noise (fallback to 0.5 * R if ATR not provided)
        atr_noise = atr if atr > 0 else (0.5 * R if R > 0 else 0.5)
        decision.ATR_noise = atr_noise

        # Spread buffer
        spread_buffer = spread * self.spread_buffer_multiplier
        decision.spread_buffer = spread_buffer

        # Stop level buffer
        stop_level_buffer = stops_level_points * point if stops_level_points > 0 else 0.0
        decision.stop_level_buffer = stop_level_buffer

        # === Phase 0: Initial Protection ===
        # No SL movement immediately after entry.
        if hold_seconds < self.min_hold_seconds:
            decision.phase = PHASE_0_INITIAL_PROTECTION
            decision.action = PolicyAction.HOLD
            decision.anti_whipsaw_blocks.append(
                f"MIN_HOLD_TIME_NOT_REACHED: hold_seconds={hold_seconds} < min_hold_seconds={self.min_hold_seconds}"
            )
            decision.reason = (f"Phase 0: hold_seconds={hold_seconds} below "
                               f"min_hold_seconds={self.min_hold_seconds}")
            return decision

        if monitor_iterations < self.min_monitor_iterations:
            decision.phase = PHASE_0_INITIAL_PROTECTION
            decision.action = PolicyAction.HOLD
            decision.anti_whipsaw_blocks.append(
                f"MIN_MONITOR_ITERATIONS_NOT_REACHED: monitor_iterations={monitor_iterations} < min_monitor_iterations={self.min_monitor_iterations}"
            )
            decision.reason = (f"Phase 0: monitor_iterations={monitor_iterations} below "
                               f"min_monitor_iterations={self.min_monitor_iterations}")
            return decision

        # === Phase 1: Noise Filter ===
        # If profit_R < breakeven_trigger_R, action=HOLD.
        if profit_R < self.breakeven_trigger_R:
            decision.phase = PHASE_1_NOISE_FILTER
            decision.action = PolicyAction.HOLD
            decision.anti_whipsaw_blocks.append(
                f"PROFIT_R_BELOW_BREAKEVEN_TRIGGER: profit_R={profit_R:.4f} < breakeven_trigger_R={self.breakeven_trigger_R}"
            )
            decision.reason = (f"Phase 1: profit_R={profit_R:.4f} below "
                               f"breakeven_trigger_R={self.breakeven_trigger_R}")
            return decision

        # If profit_distance < max(ATR_noise * atr_noise_multiplier,
        #                           spread_buffer, stop_level_buffer), HOLD
        noise_threshold = max(
            atr_noise * self.atr_noise_multiplier,
            spread_buffer,
            stop_level_buffer,
        )
        if profit_distance < noise_threshold:
            decision.phase = PHASE_1_NOISE_FILTER
            decision.action = PolicyAction.HOLD
            decision.anti_whipsaw_blocks.append(
                f"PROFIT_DISTANCE_BELOW_NOISE_THRESHOLD: profit_distance={profit_distance:.4f} < noise_threshold={noise_threshold:.4f}"
            )
            decision.reason = (f"Phase 1: profit_distance={profit_distance:.4f} below "
                               f"noise_threshold={noise_threshold:.4f}")
            return decision

        # Spread spike block (anti-whipsaw)
        if spread_spike_flag:
            decision.phase = PHASE_1_NOISE_FILTER
            decision.action = PolicyAction.HOLD
            decision.anti_whipsaw_blocks.append(
                "SPREAD_SPIKE_FLAG_ACTIVE: spread spike detected, HOLD"
            )
            decision.reason = "Phase 1: spread spike flag active, HOLD"
            return decision

        # News flag block (anti-whipsaw)
        if news_flag:
            decision.phase = PHASE_1_NOISE_FILTER
            decision.action = PolicyAction.HOLD
            decision.anti_whipsaw_blocks.append(
                "NEWS_FLAG_ACTIVE: high-impact news, HOLD"
            )
            decision.reason = "Phase 1: news flag active, HOLD"
            return decision

        # === High-volatility regime: HOLD until higher R threshold ===
        if regime == Regime.HIGH_VOL and profit_R < self.high_vol_hold_until_R:
            decision.phase = PHASE_1_NOISE_FILTER
            decision.action = PolicyAction.HOLD
            decision.anti_whipsaw_blocks.append(
                f"HIGH_VOL_REGIME_HOLD: profit_R={profit_R:.4f} < high_vol_hold_until_R={self.high_vol_hold_until_R}"
            )
            decision.reason = (f"Phase 1: high_vol regime, profit_R={profit_R:.4f} below "
                               f"high_vol_hold_until_R={self.high_vol_hold_until_R}")
            return decision

        # === Cooldown check (anti-whipsaw) ===
        # If we modified recently, HOLD unless this is a profit-lock trigger
        # (profit-lock is more aggressive and overrides cooldown for safety)
        if (seconds_since_last_modify < self.cooldown_seconds
                and profit_R < self.profit_lock_trigger_R):
            decision.phase = PHASE_1_NOISE_FILTER
            decision.action = PolicyAction.HOLD
            decision.anti_whipsaw_blocks.append(
                f"COOLDOWN_ACTIVE: seconds_since_last_modify={seconds_since_last_modify} < cooldown_seconds={self.cooldown_seconds}"
            )
            decision.reason = (f"Phase 1: cooldown active, "
                               f"seconds_since_last_modify={seconds_since_last_modify}")
            return decision

        # === Phase 4: Profit Lock (check before Phase 2/3 since it's higher priority) ===
        if profit_R >= self.profit_lock_trigger_R:
            decision.phase = PHASE_4_PROFIT_LOCK
            locked_R_value = self.locked_R * R
            if direction == "BUY":
                proposed_sl = entry_price + locked_R_value
            else:
                proposed_sl = entry_price - locked_R_value
            decision.proposed_sl = proposed_sl
            decision.action = PolicyAction.PROFIT_LOCK
            decision.trailing_distance = abs(current_price - proposed_sl)
            decision.reason = (f"Phase 4: profit_R={profit_R:.4f} >= "
                               f"profit_lock_trigger_R={self.profit_lock_trigger_R}, "
                               f"locked_R={self.locked_R}")
            return self._finalize_decision(decision, direction, current_sl,
                                            current_tp, current_price, atr_noise,
                                            stop_level_buffer)

        # === Phase 3: Adaptive Trail ===
        if profit_R >= self.trailing_trigger_R:
            decision.phase = PHASE_3_ADAPTIVE_TRAIL
            # Determine regime multiplier
            if regime == Regime.TREND:
                regime_multiplier = self.trend_atr_multiplier
            elif regime == Regime.RANGE:
                regime_multiplier = self.range_atr_multiplier
            elif regime == Regime.HIGH_VOL:
                regime_multiplier = self.high_vol_atr_multiplier
            else:
                # Default to balanced/trend multiplier
                regime_multiplier = self.trend_atr_multiplier

            trailing_distance = max(
                atr_noise * regime_multiplier,
                structure_buffer,
                spread_buffer,
                stop_level_buffer,
            )
            decision.trailing_distance = trailing_distance

            if direction == "BUY":
                proposed_sl = current_price - trailing_distance
            else:
                proposed_sl = current_price + trailing_distance
            decision.proposed_sl = proposed_sl
            decision.action = PolicyAction.TRAIL
            decision.reason = (f"Phase 3: profit_R={profit_R:.4f} >= "
                               f"trailing_trigger_R={self.trailing_trigger_R}, "
                               f"regime={regime.value}, multiplier={regime_multiplier}, "
                               f"trailing_distance={trailing_distance:.4f}")
            return self._finalize_decision(decision, direction, current_sl,
                                            current_tp, current_price, atr_noise,
                                            stop_level_buffer)

        # === Phase 2: Soft Breakeven ===
        if profit_R >= self.breakeven_trigger_R:
            decision.phase = PHASE_2_SOFT_BREAKEVEN
            breakeven_buffer_value = self.breakeven_buffer_R * R if R > 0 else 0.1
            if direction == "BUY":
                proposed_sl = entry_price + breakeven_buffer_value
            else:
                proposed_sl = entry_price - breakeven_buffer_value
            decision.proposed_sl = proposed_sl
            decision.action = PolicyAction.MOVE_TO_BREAKEVEN
            decision.trailing_distance = abs(current_price - proposed_sl)
            decision.reason = (f"Phase 2: profit_R={profit_R:.4f} >= "
                               f"breakeven_trigger_R={self.breakeven_trigger_R}, "
                               f"breakeven_buffer_R={self.breakeven_buffer_R}")
            return self._finalize_decision(decision, direction, current_sl,
                                            current_tp, current_price, atr_noise,
                                            stop_level_buffer)

        # Fallback HOLD (should not reach here, but defensive)
        decision.phase = PHASE_1_NOISE_FILTER
        decision.action = PolicyAction.HOLD
        decision.reason = "Phase 1: fallback HOLD (no trigger met)"
        return decision

    def _finalize_decision(self, decision: PolicyDecision, direction: str,
                            current_sl: float, current_tp: float,
                            current_price: float, atr_noise: float,
                            stop_level_buffer: float) -> PolicyDecision:
        """Apply anti-whipsaw checks: favorable-only, no-widening, hysteresis,
        stop-level buffer, TP preserve.

        If any check fails, downgrades action to HOLD (or BLOCKED if
        proposed SL would widen).
        """
        proposed_sl = decision.proposed_sl

        # TP preserved (always true since policy never touches TP)
        decision.tp_preserved = True

        # Favorable-only check
        if direction == "BUY":
            favorable = proposed_sl > current_sl
        else:
            favorable = (proposed_sl < current_sl) or current_sl == 0
        decision.favorable = favorable

        if not favorable:
            decision.anti_whipsaw_blocks.append(
                f"UNFAVORABLE_SL: proposed_sl={proposed_sl} not favorable vs current_sl={current_sl} (direction={direction})"
            )
            decision.action = PolicyAction.HOLD
            decision.final_sl = current_sl
            decision.reason += " | BLOCKED: unfavorable SL"
            return decision

        # No widening check
        if direction == "BUY":
            no_widening = proposed_sl >= current_sl
        else:
            no_widening = (proposed_sl <= current_sl) or current_sl == 0
        decision.no_widening = no_widening

        if not no_widening:
            decision.anti_whipsaw_blocks.append(
                f"SL_WIDENING_BLOCKED: proposed_sl={proposed_sl} widens current_sl={current_sl} (direction={direction})"
            )
            decision.action = PolicyAction.BLOCKED
            decision.final_sl = current_sl
            decision.reason += " | BLOCKED: SL widening"
            return decision

        # Hysteresis / minimum step distance
        min_step = max(
            self.minimum_sl_step_distance_atr_multiple * atr_noise,
            decision.spread_buffer,
            stop_level_buffer,
        )
        if direction == "BUY":
            step_distance = proposed_sl - current_sl
        else:
            step_distance = current_sl - proposed_sl if current_sl > 0 else proposed_sl

        if step_distance < min_step:
            decision.anti_whipsaw_blocks.append(
                f"MINIMUM_STEP_NOT_MET: step_distance={step_distance:.4f} < min_step={min_step:.4f}"
            )
            decision.action = PolicyAction.HOLD
            decision.final_sl = current_sl
            decision.reason += f" | HOLD: minimum step not met ({step_distance:.4f} < {min_step:.4f})"
            return decision

        # Stop-level buffer check
        if stop_level_buffer > 0:
            if direction == "BUY":
                if (current_price - proposed_sl) < stop_level_buffer:
                    decision.anti_whipsaw_blocks.append(
                        f"STOP_LEVEL_TOO_CLOSE: (current_price - proposed_sl)={current_price - proposed_sl:.4f} < stop_level_buffer={stop_level_buffer:.4f}"
                    )
                    decision.action = PolicyAction.HOLD
                    decision.final_sl = current_sl
                    decision.reason += " | HOLD: stop level too close"
                    return decision
            else:
                if (proposed_sl - current_price) < stop_level_buffer:
                    decision.anti_whipsaw_blocks.append(
                        f"STOP_LEVEL_TOO_CLOSE: (proposed_sl - current_price)={proposed_sl - current_price:.4f} < stop_level_buffer={stop_level_buffer:.4f}"
                    )
                    decision.action = PolicyAction.HOLD
                    decision.final_sl = current_sl
                    decision.reason += " | HOLD: stop level too close"
                    return decision

        # All checks passed - finalize
        decision.final_sl = proposed_sl
        return decision
