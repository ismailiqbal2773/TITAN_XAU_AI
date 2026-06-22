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
    sl_pips: float = DEFAULT_SL_PIPS
    tp_pips: float = DEFAULT_TP_PIPS
    max_spread_usd: float = DEFAULT_MAX_SPREAD_USD
    deviation_points: int = DEFAULT_DEVITATION_POINTS
    magic_number: int = 202619
    comment: str = "TITAN"
    news_halt_active: bool = False          # Toggled by news_filter (Sprint 4)
    require_live_config_flag: bool = True   # Require TITAN_LIVE_TRADING=1 env var when dry_run=False

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

    def __init__(self, config: Optional[TradeLoopConfig] = None):
        self.config = config or TradeLoopConfig()
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
        sl, tp = self._compute_sl_tp(entry_price, direction_int)
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
            return TradeDecision(
                accepted=True,
                signal=signal,
                risk_decision=risk_decision_str,
                adjusted_volume=adjusted_volume,
                order_request=order_request_dict,
                order_result=None,
                evaluation_ms=elapsed,
                dry_run=True,
            )

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

    def _compute_sl_tp(self, entry_price: float, direction: int) -> tuple[float, float]:
        """
        Compute SL/TP prices from pip distances.
        XAUUSD pip = $0.01 (2-digit broker) or $0.001 (3-digit broker).
        We use $0.01 per pip (conservative — wider SL on 3-digit brokers).
        """
        pip_value = 0.01
        sl_distance = self.config.sl_pips * pip_value
        tp_distance = self.config.tp_pips * pip_value
        if direction == 1:  # LONG
            sl = entry_price - sl_distance
            tp = entry_price + tp_distance
        else:                # SHORT
            sl = entry_price + sl_distance
            tp = entry_price - tp_distance
        return round(sl, 5), round(tp, 5)

    def _reject(self, signal: Signal, reason: str, t0: float,
                risk_decision: Optional[str] = None,
                adjusted_volume: float = 0.0) -> TradeDecision:
        elapsed = (time.perf_counter() - t0) * 1000.0
        logger.info(f"Signal rejected: {reason}")
        return TradeDecision(
            accepted=False,
            reject_reason=reason,
            signal=signal,
            risk_decision=risk_decision,
            adjusted_volume=adjusted_volume,
            evaluation_ms=elapsed,
            dry_run=self.config.dry_run,
        )


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
