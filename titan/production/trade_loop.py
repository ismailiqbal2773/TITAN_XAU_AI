"""
TITAN XAU AI — Trade Loop (Production Sprint 2)

Wires: Signal (from inference.py) → RiskEngine.evaluate() → OrderRequest → ExecutionEngine.submit_order()

SAFETY RULES (enforced by design):
  1. dry_run=True by DEFAULT. No real orders without explicit config flag.
  2. max_lot = 0.01 (cap, cannot be raised without code change).
  3. max_open_positions = 1 (one position at a time).
  4. SL and TP MANDATORY on every order (reject if missing/zero).
  5. Spread guard: reject if spread_usd > max_spread_usd.
  6. News halt: reject if news_halt_active flag is True.
  7. Halt flag: reject if ExecutionEngine.is_halted.

The trade_loop is async to match ExecutionEngine.submit_order signature.
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

from titan.production.inference import Signal, Direction

logger = logging.getLogger(__name__)

# ─── Hard safety constants (cannot be overridden at runtime) ─────────────────
MAX_LOT_CAP = 0.01                  # Hard ceiling — never trade > 0.01 lot
MAX_OPEN_POSITIONS = 1              # One position at a time
DEFAULT_SL_PIPS = 50                # 50 pips = $0.50 on XAUUSD (2-digit) / $5.00 (3-digit)
DEFAULT_TP_PIPS = 100               # 100 pips = 1:2 RR
DEFAULT_MAX_SPREAD_USD = 1.0        # Reject if spread > $1.00
DEFAULT_DEVITATION_POINTS = 20      # Max slippage in points


@dataclass
class TradeLoopConfig:
    """Trade loop configuration. dry_run=True by default."""
    dry_run: bool = True                    # SAFETY: must be explicitly set to False to trade live
    max_lot: float = MAX_LOT_CAP            # Hard cap 0.01
    max_open_positions: int = MAX_OPEN_POSITIONS
    sl_pips: float = DEFAULT_SL_PIPS        # Used when sl_mode="fixed"
    tp_pips: float = DEFAULT_TP_PIPS        # Used when sl_mode="fixed"
    max_spread_usd: float = DEFAULT_MAX_SPREAD_USD
    deviation_points: int = DEFAULT_DEVITATION_POINTS
    magic_number: int = 202619
    comment: str = "TITAN"
    news_halt_active: bool = False          # Toggled by news_filter (Sprint 4)
    require_live_config_flag: bool = True   # Require TITAN_LIVE_TRADING=1 env var when dry_run=False
    # ── ATR-based SL/TP (Sprint 8.4) ──
    sl_mode: str = "atr"                    # "fixed" | "atr" (default: atr)
    atr_sl_multiplier: float = 2.0          # SL = atr_sl_multiplier × ATR (balanced)
    atr_tp_multiplier: float = 4.0          # TP = atr_tp_multiplier × ATR (balanced)

    def __post_init__(self):
        # Hard enforce caps regardless of constructor args
        if self.max_lot > MAX_LOT_CAP:
            logger.warning(f"max_lot {self.max_lot} exceeds cap, clamping to {MAX_LOT_CAP}")
            self.max_lot = MAX_LOT_CAP
        if self.max_open_positions > MAX_OPEN_POSITIONS:
            logger.warning(f"max_open_positions {self.max_open_positions} exceeds cap, clamping to {MAX_OPEN_POSITIONS}")
            self.max_open_positions = MAX_OPEN_POSITIONS


@dataclass
class TradeDecision:
    """Result of evaluating a Signal through the trade loop."""
    accepted: bool
    reject_reason: Optional[str] = None
    signal: Optional[Signal] = None
    risk_decision: Optional[str] = None       # ALLOW / VETO / REDUCE_SIZE / FLATTEN
    adjusted_volume: float = 0.0
    order_request: Optional[dict] = None      # OrderRequest as dict (for logging)
    order_result: Optional[dict] = None       # ExecutionEngine result (None in dry_run)
    evaluation_ms: float = 0.0
    dry_run: bool = True
    # ── Sprint 8.5 ATR Audit Fields (hard evidence for every decision) ──
    current_atr: float = 0.0                  # ATR(14) at signal time
    sl_tp_mode_used: str = ""                 # "atr" | "fixed" (what actually ran)
    sl_mode_configured: str = ""              # what was configured (for diff vs used)
    atr_sl_multiplier: float = 0.0            # multiplier loaded at runtime
    atr_tp_multiplier: float = 0.0
    atr_sl_distance: float = 0.0              # sl_distance in price units
    atr_tp_distance: float = 0.0
    fallback_used: bool = False               # TRUE if ATR configured but fixed-pip used
    fallback_reason: str = ""                 # "" | "atr_zero" | "atr_nan" | "mode_fixed" | "exception"
    entry_price: float = 0.0                  # price used for SL/TP computation
    computed_sl: float = 0.0                  # final SL passed to order_request
    computed_tp: float = 0.0                  # final TP passed to order_request
    # ── Sprint 9.3.1 Capital Protection Context (journaled on DECISION) ──
    health_score: Optional[float] = None      # 0-100 from AccountHealthEngine
    health_band: str = ""                     # normal | slight_reduction | defensive | recovery_mode | capital_preservation
    risk_profile: str = ""                    # dynamic risk profile name
    risk_multiplier: float = 1.0              # 0.0-1.0 from DynamicRiskEngine
    recovery_mode_active: bool = False        # True if RecoveryMode.is_active
    capital_preservation_active: bool = False # True if CapitalPreservation.is_active
    profit_lock_active: bool = False          # True if ProfitLock.is_locked
    prop_profile_id: str = ""                 # active prop firm profile id (if any)
    challenge_status: Optional[dict] = None   # latest CHALLENGE_STATUS snapshot

    def __repr__(self) -> str:
        if self.accepted:
            return (f"TradeDecision(ACCEPTED, vol={self.adjusted_volume}, "
                    f"dry_run={self.dry_run}, risk={self.risk_decision})")
        return f"TradeDecision(REJECTED: {self.reject_reason})"


class TradeLoop:
    """
    Async trade loop. Consumes Signal objects from inference.py.

    Usage:
        loop = TradeLoop(config=TradeLoopConfig(dry_run=True))
        decision = await loop.process_signal(signal, entry_price=2000.0,
                                              spread_usd=0.20,
                                              risk_engine=risk_engine,
                                              execution_engine=exec_engine)
    """

    def __init__(self, config: Optional[TradeLoopConfig] = None,
                 journal=None,
                 kill_switch=None):
        self.config = config or TradeLoopConfig()
        self.journal = journal  # Optional TradeJournal for logging
        self.kill_switch = kill_switch  # Optional KillSwitchFSM
        self._open_position_count = 0
        # Verify safety: if dry_run=False, require explicit env var
        if not self.config.dry_run and self.config.require_live_config_flag:
            import os
            flag = os.environ.get("TITAN_LIVE_TRADING", "0")
            if flag != "1":
                raise PermissionError(
                    "dry_run=False requires TITAN_LIVE_TRADING=1 environment variable. "
                    "Set this flag explicitly to enable live order submission."
                )
        logger.info(f"TradeLoop initialized: {self.config}")

    # ─── Public API ─────────────────────────────────────────────────────

    async def process_signal(
        self,
        signal: Signal,
        entry_price: float,
        spread_usd: float,
        risk_engine=None,
        execution_engine=None,
        current_equity: float = 10000.0,
        account_state: Optional[dict] = None,
        current_atr: float = 0.0,
        # ── Sprint 9.3.1 Capital Protection Context (optional, default None) ──
        health_score: Optional[float] = None,
        health_band: str = "",
        risk_profile: str = "",
        risk_multiplier: Optional[float] = None,
        recovery_mode_active: bool = False,
        capital_preservation_active: bool = False,
        profit_lock_active: bool = False,
        prop_profile_id: str = "",
        challenge_status: Optional[dict] = None,
    ) -> TradeDecision:
        """
        Process a Signal through the full trade chain.

        Args:
            signal: Output from InferenceEngine.generate()
            entry_price: Current ask (for LONG) or bid (for SHORT)
            spread_usd: Current spread in USD
            risk_engine: RiskEngine instance (optional — uses stub if None)
            execution_engine: ExecutionEngine instance (optional — uses stub if None)
            current_equity: Account equity for sizing
            account_state: Optional dict with balance/margin/margin_level/etc.
        """
        t0 = time.perf_counter()

        # Sprint 9.3.1: stash capital-protection context on self so _reject()
        # can include it on rejected TradeDecision records too. Cleared in
        # finally below to avoid leaking across calls.
        self._current_context = {
            "health_score": health_score,
            "health_band": health_band,
            "risk_profile": risk_profile,
            "risk_multiplier": (1.0 if risk_multiplier is None else float(risk_multiplier)),
            "recovery_mode_active": recovery_mode_active,
            "capital_preservation_active": capital_preservation_active,
            "profit_lock_active": profit_lock_active,
            "prop_profile_id": prop_profile_id,
            "challenge_status": challenge_status,
        }

        # ── PRE-CHECK 0: Kill-switch FSM state ──
        if self.kill_switch is not None:
            ks_state = self.kill_switch.state
            if not self.kill_switch.allows_new_trades:
                # HALT_NEW_TRADES / FLATTEN_ONLY / EMERGENCY_STOP → block
                reason = f"kill_switch_{ks_state.value.lower()}"
                if self.kill_switch.is_emergency:
                    reason = "kill_switch_emergency_stop"
                elif self.kill_switch.requires_flatten:
                    reason = "kill_switch_flatten_only"
                elif ks_state.value == "HALT_NEW_TRADES":
                    reason = "kill_switch_halt_new_trades"
                # Journal the block
                if self.journal is not None:
                    from titan.production.trade_journal import EventType
                    self.journal.log_event(EventType.KILL_SWITCH_BLOCK, {
                        "kill_switch_state": ks_state.value,
                        "signal_direction": signal.direction.name,
                        "reason": reason,
                    })
                return self._reject(signal, reason, t0)
            # If CAUTION → reduce size (configurable; for now, half the volume)
            if ks_state.value == "CAUTION":
                # Reduce proposed volume by 50% in caution state
                original_max = self.config.max_lot
                self.config.max_lot = max(original_max / 2, 0.01)
                logger.warning(
                    f"Kill-switch CAUTION — reducing max_lot to {self.config.max_lot}"
                )

        # ── PRE-CHECK 1: Tradeable signal ──
        if not signal.is_tradeable:
            return self._reject(signal, "signal_not_tradeable", t0)
        if signal.direction == Direction.FLAT:
            return self._reject(signal, "direction_is_flat", t0)

        # ── PRE-CHECK 2: News halt ──
        if self.config.news_halt_active:
            return self._reject(signal, "news_halt_active", t0)

        # ── PRE-CHECK 3: Spread guard ──
        if spread_usd > self.config.max_spread_usd:
            return self._reject(signal,
                f"spread_too_high ({spread_usd:.4f} > {self.config.max_spread_usd})", t0)

        # ── PRE-CHECK 4: Max open positions ──
        if self._open_position_count >= self.config.max_open_positions:
            return self._reject(signal,
                f"max_open_positions_reached ({self._open_position_count}/{self.config.max_open_positions})", t0)

        # ── PRE-CHECK 5: Halt flag on execution engine ──
        if execution_engine is not None and getattr(execution_engine, "is_halted", False):
            return self._reject(signal, "execution_engine_halted", t0)

        # ── Compute SL/TP ──
        direction_int = 1 if signal.direction == Direction.LONG else -1
        sl, tp, atr_audit = self._compute_sl_tp(entry_price, direction_int, current_atr)
        if sl == 0.0 or tp == 0.0:
            return self._reject(signal, "sl_tp_computation_failed", t0)

        # ── RISK EVALUATION ──
        proposed_volume = self.config.max_lot
        risk_decision_str = "ALLOW"
        adjusted_volume = proposed_volume

        if risk_engine is not None:
            try:
                from titan.risk.engine import RiskSignal
                rs = RiskSignal(
                    symbol="XAUUSD",
                    direction=direction_int,
                    proposed_volume=proposed_volume,
                    entry_price=entry_price,
                    stop_loss=sl,
                    take_profit=tp,
                    confidence=signal.confidence,
                    model_id="xgboost_v1",
                )
                risk_eval = risk_engine.evaluate(rs)
                risk_decision_str = risk_eval.decision.value
                adjusted_volume = risk_eval.adjusted_volume

                if risk_decision_str == "VETO":
                    return self._reject(signal,
                        f"risk_veto: {risk_eval.reason}", t0,
                        risk_decision=risk_decision_str)
                if risk_decision_str == "FLATTEN":
                    return self._reject(signal,
                        f"risk_flatten: {risk_eval.reason}", t0,
                        risk_decision=risk_decision_str)
                # REDUCE_SIZE: use adjusted_volume (already set above)
                # ALLOW: use proposed_volume
                if risk_decision_str == "ALLOW":
                    adjusted_volume = proposed_volume
            except Exception as e:
                logger.error(f"RiskEngine.evaluate failed: {e}")
                return self._reject(signal, f"risk_engine_error: {e}", t0)
        # else: stub mode — assume ALLOW with proposed_volume

        # Hard cap on volume (defense in depth)
        adjusted_volume = min(adjusted_volume, self.config.max_lot)

        # ── BUILD ORDER REQUEST ──
        # Import OrderType lazily — avoid hard dependency on MetaTrader5
        try:
            from titan.execution.engine import OrderType
            order_type = (OrderType.MARKET_BUY if signal.direction == Direction.LONG
                          else OrderType.MARKET_SELL)
            order_type_name = order_type.name
        except ImportError:
            # Fallback for environments without MetaTrader5 (e.g., Linux dev)
            order_type_name = "MARKET_BUY" if signal.direction == Direction.LONG else "MARKET_SELL"

        order_request_dict = {
            "symbol": "XAUUSD",
            "order_type": order_type_name,
            "volume": adjusted_volume,
            "price": 0.0,                # 0 = market order
            "sl": sl,
            "tp": tp,
            "deviation": self.config.deviation_points,
            "magic": self.config.magic_number,
            "comment": self.config.comment,
            "idempotency_key": str(uuid.uuid4()),
        }

        # ── FINAL SL/TP GUARD ──
        if sl == 0.0 or tp == 0.0:
            return self._reject(signal, "sl_tp_missing_at_submission", t0,
                                risk_decision=risk_decision_str,
                                adjusted_volume=adjusted_volume)

        # ── DRY RUN: log and return without submitting ──
        if self.config.dry_run:
            elapsed = (time.perf_counter() - t0) * 1000.0
            logger.info(
                f"[DRY RUN] Would submit: {order_type_name} {adjusted_volume} lot "
                f"XAUUSD @ {entry_price:.2f} SL={sl:.2f} TP={tp:.2f} "
                f"(risk={risk_decision_str})"
            )
            decision = TradeDecision(
                accepted=True,
                signal=signal,
                risk_decision=risk_decision_str,
                adjusted_volume=adjusted_volume,
                order_request=order_request_dict,
                order_result=None,
                evaluation_ms=elapsed,
                dry_run=True,
                # ── Sprint 8.5 ATR audit fields (hard evidence) ──
                current_atr=atr_audit["current_atr"],
                sl_tp_mode_used=atr_audit["sl_tp_mode_used"],
                sl_mode_configured=atr_audit["sl_mode_configured"],
                atr_sl_multiplier=atr_audit["atr_sl_multiplier"],
                atr_tp_multiplier=atr_audit["atr_tp_multiplier"],
                atr_sl_distance=atr_audit["atr_sl_distance"],
                atr_tp_distance=atr_audit["atr_tp_distance"],
                fallback_used=atr_audit["fallback_used"],
                fallback_reason=atr_audit["fallback_reason"],
                entry_price=atr_audit["entry_price"],
                computed_sl=atr_audit["computed_sl"],
                computed_tp=atr_audit["computed_tp"],
                # ── Sprint 9.3.1 Capital Protection context ──
                health_score=health_score,
                health_band=health_band,
                risk_profile=risk_profile,
                risk_multiplier=(1.0 if risk_multiplier is None else float(risk_multiplier)),
                recovery_mode_active=recovery_mode_active,
                capital_preservation_active=capital_preservation_active,
                profit_lock_active=profit_lock_active,
                prop_profile_id=prop_profile_id,
                challenge_status=challenge_status,
            )
            # Journal the decision + order
            if self.journal is not None:
                self.journal.log_decision(decision)
                self.journal.log_order(decision)
            return decision

        # ── LIVE: submit to ExecutionEngine ──
        if execution_engine is None:
            return self._reject(signal, "no_execution_engine_for_live_order", t0,
                                risk_decision=risk_decision_str,
                                adjusted_volume=adjusted_volume)

        try:
            from titan.execution.engine import OrderRequest, OrderType
            req = OrderRequest(
                symbol="XAUUSD",
                order_type=(OrderType.MARKET_BUY if signal.direction == Direction.LONG
                           else OrderType.MARKET_SELL),
                volume=adjusted_volume,
                price=0.0,
                sl=sl,
                tp=tp,
                deviation=self.config.deviation_points,
                magic=self.config.magic_number,
                comment=self.config.comment,
                idempotency_key=order_request_dict["idempotency_key"],
            )
            result = await execution_engine.submit_order(req)
            elapsed = (time.perf_counter() - t0) * 1000.0

            # Update open position count if filled
            from titan.execution.engine import OrderState
            if result.state in (OrderState.FILLED, OrderState.PARTIALLY_FILLED):
                self._open_position_count += 1

            return TradeDecision(
                accepted=(result.state in (OrderState.FILLED, OrderState.PARTIALLY_FILLED)),
                reject_reason=None if result.state == OrderState.FILLED else f"order_state={result.state.value}",
                signal=signal,
                risk_decision=risk_decision_str,
                adjusted_volume=adjusted_volume,
                order_request=order_request_dict,
                order_result={
                    "retcode": result.retcode,
                    "order_id": result.order_id,
                    "state": result.state.value,
                    "price": result.price,
                    "volume": result.volume,
                    "latency_ms": result.latency_ms,
                },
                evaluation_ms=elapsed,
                dry_run=False,
                # ── Sprint 8.5 ATR audit fields (hard evidence) ──
                current_atr=atr_audit["current_atr"],
                sl_tp_mode_used=atr_audit["sl_tp_mode_used"],
                sl_mode_configured=atr_audit["sl_mode_configured"],
                atr_sl_multiplier=atr_audit["atr_sl_multiplier"],
                atr_tp_multiplier=atr_audit["atr_tp_multiplier"],
                atr_sl_distance=atr_audit["atr_sl_distance"],
                atr_tp_distance=atr_audit["atr_tp_distance"],
                fallback_used=atr_audit["fallback_used"],
                fallback_reason=atr_audit["fallback_reason"],
                entry_price=atr_audit["entry_price"],
                computed_sl=atr_audit["computed_sl"],
                computed_tp=atr_audit["computed_tp"],
                # ── Sprint 9.3.1 Capital Protection context ──
                health_score=health_score,
                health_band=health_band,
                risk_profile=risk_profile,
                risk_multiplier=(1.0 if risk_multiplier is None else float(risk_multiplier)),
                recovery_mode_active=recovery_mode_active,
                capital_preservation_active=capital_preservation_active,
                profit_lock_active=profit_lock_active,
                prop_profile_id=prop_profile_id,
                challenge_status=challenge_status,
            )
        except ImportError as e:
            return self._reject(signal, f"execution_engine_import_error: {e}", t0,
                                risk_decision=risk_decision_str,
                                adjusted_volume=adjusted_volume)
        except Exception as e:
            logger.error(f"submit_order failed: {e}")
            return self._reject(signal, f"submit_order_error: {e}", t0,
                                risk_decision=risk_decision_str,
                                adjusted_volume=adjusted_volume)

    def notify_position_closed(self) -> None:
        """Called by position_sync when a position closes — decrements counter."""
        if self._open_position_count > 0:
            self._open_position_count -= 1

    @property
    def open_position_count(self) -> int:
        return self._open_position_count

    # ─── Internal helpers ───────────────────────────────────────────────

    def _compute_sl_tp(self, entry_price: float, direction: int,
                       current_atr: float = 0.0) -> tuple[float, float, dict]:
        """
        Compute SL/TP prices with full audit metadata.

        If sl_mode="atr" and current_atr > 0 and isfinite:
            SL = entry ∓ (atr_sl_multiplier × ATR)
            TP = entry ± (atr_tp_multiplier × ATR)
            mode_used = "atr", fallback_used = False

        If sl_mode="atr" but current_atr <= 0 or NaN:
            FALLBACK to fixed-pip mode (legacy behaviour)
            SL = entry ∓ (sl_pips × $0.01)
            TP = entry ± (tp_pips × $0.01)
            mode_used = "fixed", fallback_used = True
            fallback_reason = "atr_zero" | "atr_nan"

        If sl_mode="fixed":
            SL = entry ∓ (sl_pips × $0.01)
            TP = entry ± (tp_pips × $0.01)
            mode_used = "fixed", fallback_used = False
            fallback_reason = "mode_fixed"

        Returns: (sl, tp, audit_dict)
        """
        import math

        sl_mode_configured = self.config.sl_mode
        atr_sl_mult = float(self.config.atr_sl_multiplier)
        atr_tp_mult = float(self.config.atr_tp_multiplier)

        # Determine fallback conditions explicitly
        atr_unavailable = False
        fallback_reason = ""
        if sl_mode_configured == "atr":
            if current_atr is None or not math.isfinite(float(current_atr)):
                atr_unavailable = True
                fallback_reason = "atr_nan"
            elif float(current_atr) <= 0.0:
                atr_unavailable = True
                fallback_reason = "atr_zero"

        if sl_mode_configured == "atr" and not atr_unavailable:
            atr_val = float(current_atr)
            sl_distance = atr_sl_mult * atr_val
            tp_distance = atr_tp_mult * atr_val
            mode_used = "atr"
            fallback_used = False
            logger.debug(
                f"ATR SL/TP: ATR={atr_val:.4f} "
                f"SL_dist={sl_distance:.4f} TP_dist={tp_distance:.4f}"
            )
        else:
            # Fixed pip mode (fallback when ATR configured but unavailable,
            # OR when operator explicitly set sl_mode="fixed")
            pip_value = 0.01
            sl_distance = self.config.sl_pips * pip_value
            tp_distance = self.config.tp_pips * pip_value
            mode_used = "fixed"
            fallback_used = (sl_mode_configured == "atr")  # only true when atr was desired
            if not fallback_used:
                fallback_reason = "mode_fixed"
            logger.warning(
                f"SL/TP FALLBACK to fixed-pip: configured={sl_mode_configured} "
                f"mode_used=fixed fallback_used={fallback_used} "
                f"reason={fallback_reason} current_atr={current_atr} "
                f"sl_dist={sl_distance:.4f} tp_dist={tp_distance:.4f}"
            )

        if direction == 1:  # LONG
            sl = entry_price - sl_distance
            tp = entry_price + tp_distance
        else:                # SHORT
            sl = entry_price + sl_distance
            tp = entry_price - tp_distance

        sl = round(sl, 5)
        tp = round(tp, 5)

        audit = {
            "current_atr": float(current_atr) if (current_atr is not None and math.isfinite(float(current_atr))) else 0.0,
            "sl_tp_mode_used": mode_used,
            "sl_mode_configured": sl_mode_configured,
            "atr_sl_multiplier": atr_sl_mult,
            "atr_tp_multiplier": atr_tp_mult,
            "atr_sl_distance": float(sl_distance),
            "atr_tp_distance": float(tp_distance),
            "fallback_used": bool(fallback_used),
            "fallback_reason": fallback_reason,
            "entry_price": float(entry_price),
            "computed_sl": float(sl),
            "computed_tp": float(tp),
        }
        return sl, tp, audit

    def _reject(self, signal: Signal, reason: str, t0: float,
                risk_decision: Optional[str] = None,
                adjusted_volume: float = 0.0) -> TradeDecision:
        elapsed = (time.perf_counter() - t0) * 1000.0
        logger.info(f"Signal rejected: {reason}")
        # Sprint 9.3.1: pull capital-protection context from current call
        ctx = getattr(self, "_current_context", {}) or {}
        decision = TradeDecision(
            accepted=False,
            reject_reason=reason,
            signal=signal,
            risk_decision=risk_decision,
            adjusted_volume=adjusted_volume,
            evaluation_ms=elapsed,
            dry_run=self.config.dry_run,
            # Sprint 9.3.1 context fields (None defaults if not set)
            health_score=ctx.get("health_score"),
            health_band=ctx.get("health_band", ""),
            risk_profile=ctx.get("risk_profile", ""),
            risk_multiplier=ctx.get("risk_multiplier", 1.0),
            recovery_mode_active=ctx.get("recovery_mode_active", False),
            capital_preservation_active=ctx.get("capital_preservation_active", False),
            profit_lock_active=ctx.get("profit_lock_active", False),
            prop_profile_id=ctx.get("prop_profile_id", ""),
            challenge_status=ctx.get("challenge_status"),
        )
        # Journal the rejection
        if self.journal is not None:
            self.journal.log_decision(decision)
        return decision


if __name__ == "__main__":
    # Smoke test
    import asyncio
    from titan.production.inference import InferenceEngine

    async def main():
        print("=" * 70)
        print("TITAN TradeLoop — Dry-Run Smoke Test")
        print("=" * 70)
        loop = TradeLoop(config=TradeLoopConfig(dry_run=True))
        engine = InferenceEngine()
        signal = engine.generate(source="canonical")
        print(f"\nSignal: {signal}")
        decision = await loop.process_signal(
            signal=signal,
            entry_price=2000.0,
            spread_usd=0.20,
            current_equity=10000.0,
        )
        print(f"\nDecision: {decision}")
        if decision.order_request:
            print(f"\nOrderRequest:")
            for k, v in decision.order_request.items():
                print(f"  {k}: {v}")

    asyncio.run(main())
